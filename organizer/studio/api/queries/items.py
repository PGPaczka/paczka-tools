"""Lista treści, jej filtry i katalogi źródłowe — to, po czym chodzi oko.

Kolejność i kubełek pewności liczy SERWER, nie widok: to reguły z configu,
a nie sposób malowania paska (``studio/AGENTS.md``, reguła 1).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from orglib import folder_links
from orglib.naming import best_name

from ._common import GROUND_TRUTH_RUN_ID, _ITEM_COLUMNS, _ITEM_FROM
from .dashboard import _confidence_bucket, confidence_limits


def _item_filters(
    *,
    semester: int | None,
    skrot: str | None,
    category: str | None,
    action: str | None,
    file_status: str | None,
    content_kind: str | None,
    needs_review: bool | None,
    classified: bool | None,
    confidence_min: float | None,
    confidence_max: float | None,
    include_ground_truth: bool,
) -> tuple[str, list[Any]]:
    """Składa WHERE z podanych filtrów; brak filtru = brak warunku."""
    clauses: list[str] = []
    params: list[Any] = []
    if not include_ground_truth:
        clauses.append("(cl.run_id IS NULL OR cl.run_id <> ?)")
        params.append(GROUND_TRUTH_RUN_ID)
    for column, value in (
        ("cl.semester", semester),
        ("cl.subject_key", skrot),
        ("cl.category", category),
        ("cl.action", action),
        ("f.status", file_status),
        ("c.content_kind", content_kind),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if needs_review is not None:
        clauses.append("COALESCE(cl.needs_review, 0) = ?")
        params.append(1 if needs_review else 0)
    if classified is not None:
        clauses.append("cl.sha256 IS NOT NULL" if classified else "cl.sha256 IS NULL")
    if confidence_min is not None:
        clauses.append("cl.confidence >= ?")
        params.append(confidence_min)
    if confidence_max is not None:
        clauses.append("cl.confidence <= ?")
        params.append(confidence_max)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def items(
    conn: sqlite3.Connection,
    *,
    semester: int | None = None,
    skrot: str | None = None,
    category: str | None = None,
    action: str | None = None,
    file_status: str | None = None,
    content_kind: str | None = None,
    needs_review: bool | None = None,
    classified: bool | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    include_ground_truth: bool = False,
    thresholds: Mapping[str, Any] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Lista treści po filtrach, uporządkowana wg tego, co najpilniej wymaga oka.

    Kolejność: najpierw ``needs_review``, potem rosnąca pewność (SQLite stawia
    NULL na początku — treść bez decyzji jest właśnie tym, o czym nikt nic nie
    wie), na końcu ``sha256`` dla stabilności stronicowania.
    """
    where, params = _item_filters(
        semester=semester, skrot=skrot, category=category, action=action,
        file_status=file_status, content_kind=content_kind, needs_review=needs_review,
        classified=classified, confidence_min=confidence_min, confidence_max=confidence_max,
        include_ground_truth=include_ground_truth,
    )
    total = int(conn.execute(f"SELECT COUNT(*) AS n {_ITEM_FROM}{where}", params).fetchone()["n"])
    rows = conn.execute(
        f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM}{where} "
        "ORDER BY COALESCE(cl.needs_review, 0) DESC, cl.confidence ASC, c.sha256 "
        "LIMIT ? OFFSET ?",
        [*params, int(limit), int(offset)],
    ).fetchall()
    auto_apply, review_min = confidence_limits(thresholds)
    return {
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "thresholds": {"auto_apply": auto_apply, "review_min": review_min},
        "items": [_with_bucket(row, auto_apply, review_min) for row in rows],
    }


def _with_bucket(row: sqlite3.Row, auto_apply: float, review_min: float) -> dict[str, Any]:
    """Wiersz listy + kubełek pewności. Kubełek liczy SERWER: to jest reguła z configu,
    a nie sposób malowania paska (``studio/AGENTS.md``, reguła 1)."""
    item = dict(row)
    value = item.get("confidence")
    item["confidence_bucket"] = _confidence_bucket(
        None if value is None else float(value), auto_apply, review_min
    )
    return item


def items_by_folder(
    conn: sqlite3.Connection,
    folder: str,
    thresholds: Mapping[str, Any] | None = None,
    *,
    include_linked: bool = False,
) -> dict[str, Any]:
    """Treści z katalogu źródłowego — do podglądu przed decyzją hurtową.

    `linked_folders` podajemy ZAWSZE, a treści z nich dokładamy tylko na żądanie:
    powiązanie ma być widoczne, zanim człowiek kliknie, ale nigdy nie może po cichu
    rozszerzyć decyzji na cudzy katalog.
    """
    auto_apply, review_min = confidence_limits(thresholds)
    powiazane = sorted(folder_links.partners(conn, folder))
    katalogi = [folder, *powiazane] if include_linked else [folder]

    rows: list[sqlite3.Row] = []
    widziane: set[str] = set()
    for katalog in katalogi:
        for row in conn.execute(
            f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM} "
            "WHERE f.folder_path = ? OR f.source_relative_path LIKE ? || '/%' "
            "ORDER BY f.source_relative_path",
            (katalog, katalog),
        ):
            # Ta sama treść potrafi leżeć w obu katalogach: liczymy ją raz, inaczej
            # „ile pozycji dotknie decyzja" kłamałoby w górę.
            if row["sha256"] in widziane:
                continue
            widziane.add(row["sha256"])
            rows.append(row)

    return {
        "folder": folder,
        "linked_folders": powiazane,
        "included_linked": include_linked,
        "total": len(rows),
        "items": [_with_bucket(row, auto_apply, review_min) for row in rows],
    }


def item_detail(
    conn: sqlite3.Connection, sha256: str, thresholds: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """Jedna treść: decyzja, wszystkie jej kopie, relacje, plan i ślad po apply.

    ``None``, gdy takiej treści nie ma w indeksie — wołający zamienia to na 404.
    """
    row = conn.execute(
        f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM} WHERE c.sha256 = ?", (sha256,)
    ).fetchone()
    if row is None:
        return None
    auto_apply, review_min = confidence_limits(thresholds)
    files = conn.execute(
        "SELECT file_id, source_package, source_relative_path, folder_path, filename, "
        "extension, size_bytes, modified_date, status, error_message "
        "FROM files WHERE sha256 = ? ORDER BY file_id",
        (sha256,),
    ).fetchall()
    names = sorted({
        f["filename"] for f in files if f["filename"] and f["filename"].strip()
    })
    relations = conn.execute(
        "SELECT source_sha256, target_sha256, relation_type, confidence, detection_method, reason "
        "FROM relations WHERE source_sha256 = ? OR target_sha256 = ? "
        "ORDER BY relation_type, confidence DESC",
        (sha256, sha256),
    ).fetchall()
    plan = conn.execute(
        "SELECT target_relative_path, action, status, plan_run_id FROM plan_items "
        "WHERE sha256 = ? ORDER BY target_relative_path",
        (sha256,),
    ).fetchall()
    applied = conn.execute(
        "SELECT target_relative_path, action, plan_hash, applied_at FROM applied "
        "WHERE sha256 = ? ORDER BY target_relative_path",
        (sha256,),
    ).fetchall()
    manual = conn.execute(
        "SELECT * FROM manual_decisions WHERE sha256 = ?", (sha256,)
    ).fetchone()
    return {
        "item": _with_bucket(row, auto_apply, review_min),
        "files": [dict(f) for f in files],
        "names": names,
        "suggested_name": best_name(names) if len(names) > 1 else None,
        "relations": [dict(r) for r in relations],
        "plan_items": [dict(p) for p in plan],
        "applied": [dict(a) for a in applied],
        "manual_decision": None if manual is None else dict(manual),
    }


def folders(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    package: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Katalogi do przeglądania i powiązywania, z ręcznymi powiązaniami każdego z nich.

    `linked_to` bierzemy jednym zapytaniem dla całej strony wyników: przy tysiącach
    katalogów zapytanie na wiersz zamieniłoby listę w setki osobnych odczytów.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if q:
        clauses.append("folder_path LIKE '%' || ? || '%'")
        params.append(q)
    if package:
        clauses.append("source_package = ?")
        params.append(package)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = int(conn.execute(
        f"SELECT COUNT(*) AS n FROM folders{where}", params
    ).fetchone()["n"])

    rows = conn.execute(
        f"SELECT folder_path, source_package, file_count, total_bytes, duplicate_of "
        f"FROM folders{where} "
        f"ORDER BY folder_path ASC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    folder_paths = [row["folder_path"] for row in rows]
    linked_map: dict[str, set[str]] = {fp: set() for fp in folder_paths}

    if folder_paths:
        placeholders = ",".join("?" * len(folder_paths))
        link_rows = conn.execute(
            f"""
            SELECT folder_a, folder_b FROM manual_folder_links
            WHERE folder_a IN ({placeholders}) OR folder_b IN ({placeholders})
            """,
            [*folder_paths, *folder_paths],
        ).fetchall()

        for link_row in link_rows:
            a = link_row["folder_a"]
            b = link_row["folder_b"]
            if a in linked_map:
                linked_map[a].add(b)
            if b in linked_map:
                linked_map[b].add(a)

    # `file_count` i `total_bytes` są puste dla katalogów świeżo po `scan.py`, zanim
    # policzy je `fold_hash` — pusto znaczy „jeszcze nie wiadomo", nie zero.
    wynik = [{
        "folder_path": row["folder_path"],
        "source_package": row["source_package"],
        "file_count": None if row["file_count"] is None else int(row["file_count"]),
        "total_bytes": None if row["total_bytes"] is None else int(row["total_bytes"]),
        "duplicate_of": row["duplicate_of"],
        "linked_to": sorted(linked_map[row["folder_path"]]),
    } for row in rows]

    return {"total": total, "limit": limit, "offset": offset, "folders": wynik}
