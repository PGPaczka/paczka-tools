"""Near-dupe i grupy „chyba jedna sesja" — materiał do porównania parami.

Union-find robi ``orglib.review.build_clusters``, ten sam, którego używa raport
near-dupe: studio ma pokazywać TE SAME klastry co potok, nie własne.
"""

from __future__ import annotations

import fnmatch
import sqlite3
from typing import Any, Mapping, Sequence

from orglib import config, preview as preview_lib
from orglib.review import TEXT_KINDS, build_clusters

from ._common import PREVIEW_TEXT_LIMIT, _ITEM_COLUMNS, _ITEM_FROM
from .dashboard import confidence_limits
from .items import _with_bucket


def clusters(
    conn: sqlite3.Connection,
    *,
    semester: int | None = None,
    skrot: str | None = None,
    noise_patterns: Sequence[str] = (),
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Klastry near-dupe: union-find z ``orglib.review.build_clusters``.

    Opcjonalne filtry semester/skrot zawężają do relacji, których co najmniej
    jeden koniec ma klasyfikację w danym przedmiocie.
    """
    auto_apply, review_min = confidence_limits(thresholds)

    if semester is not None or skrot is not None:
        clauses: list[str] = []
        params: list[Any] = []
        if semester is not None:
            clauses.append("cl.semester = ?")
            params.append(semester)
        if skrot is not None:
            clauses.append("cl.subject_key = ?")
            params.append(skrot)
        where = " AND ".join(clauses)
        sha_rows = conn.execute(
            f"SELECT DISTINCT cl.sha256 FROM classifications cl WHERE {where}", params
        ).fetchall()
        known = {row["sha256"] for row in sha_rows}
        rel_rows = conn.execute(
            "SELECT source_sha256, target_sha256, relation_type, confidence, "
            "detection_method, reason FROM relations"
        ).fetchall()
        raw_relations = [
            dict(r) for r in rel_rows
            if r["source_sha256"] in known or r["target_sha256"] in known
        ]
    else:
        rel_rows = conn.execute(
            "SELECT source_sha256, target_sha256, relation_type, confidence, "
            "detection_method, reason FROM relations"
        ).fetchall()
        raw_relations = [dict(r) for r in rel_rows]

    groups = build_clusters(raw_relations)

    config_noise = list(
        dict((thresholds or {}).get("near_duplicate") or {}).get("noise_patterns") or []
    )
    all_noise = config_noise + list(noise_patterns)
    if all_noise:
        def _is_noise(path: str) -> bool:
            return any(fnmatch.fnmatch(path, pat) for pat in all_noise)
    else:
        _is_noise = None

    all_shas = {sha for cluster in groups for sha in cluster.members}
    if all_shas:
        placeholders = ",".join("?" * len(all_shas))
        item_rows = conn.execute(
            f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM} WHERE c.sha256 IN ({placeholders})",
            list(all_shas),
        ).fetchall()
        item_map = {row["sha256"]: _with_bucket(row, auto_apply, review_min) for row in item_rows}
    else:
        item_map = {}

    result: list[dict[str, Any]] = []
    for cluster in groups:
        members = []
        skip_cluster = False
        for sha in cluster.members:
            item = item_map.get(sha)
            if item and _is_noise and item.get("source_relative_path"):
                if _is_noise(item["source_relative_path"]):
                    skip_cluster = True
                    break
            members.append(item or {"sha256": sha})
        if skip_cluster:
            continue
        result.append({
            "members": members,
            "relations": cluster.relations,
            "size": cluster.size,
            "strength": cluster.strength,
            "has_older_version": cluster.has_older_version(),
        })

    return {
        "total": len(result),
        "clusters": result,
    }


def _read_text_head(
    paths: config.Paths, path: str | None, max_bytes: int = PREVIEW_TEXT_LIMIT
) -> str | None:
    """Głowa tekstu przez wspólny helper — ścieżka jest WZGLĘDNA wobec ``work``.

    Wcześniej ta funkcja sklejała ścieżkę z bazy wprost, więc diff klastra nigdy
    nie pokazywał tekstu na realnych danych (a test tego nie łapał, bo wpisywał
    ścieżkę bezwzględną). Ta sama wpadka co w podglądzie — teraz obie drogi do
    materiałów prowadzą przez ``orglib.preview.text_head`` i jego containment.
    """
    return preview_lib.text_head(paths, path, max_bytes)


def cluster_diff(
    conn: sqlite3.Connection,
    left_sha: str,
    right_sha: str,
    paths: config.Paths,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Dane do porównania dwóch treści z klastra: metadane + głowy tekstu."""
    auto_apply, review_min = confidence_limits(thresholds)
    placeholders = ",".join("?" * 2)
    rows = conn.execute(
        f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM} WHERE c.sha256 IN ({placeholders})",
        [left_sha, right_sha],
    ).fetchall()
    by_sha = {row["sha256"]: _with_bucket(row, auto_apply, review_min) for row in rows}
    left_item = by_sha.get(left_sha)
    right_item = by_sha.get(right_sha)
    if not left_item or not right_item:
        return None

    left_text_path = conn.execute(
        "SELECT extracted_text_path FROM content WHERE sha256 = ?", (left_sha,)
    ).fetchone()
    right_text_path = conn.execute(
        "SELECT extracted_text_path FROM content WHERE sha256 = ?", (right_sha,)
    ).fetchone()

    left_text = _read_text_head(
        paths, left_text_path["extracted_text_path"] if left_text_path else None
    )
    right_text = _read_text_head(
        paths, right_text_path["extracted_text_path"] if right_text_path else None
    )

    relation = conn.execute(
        "SELECT relation_type, confidence, detection_method, reason "
        "FROM relations WHERE "
        "  (source_sha256 = ? AND target_sha256 = ?) OR "
        "  (source_sha256 = ? AND target_sha256 = ?)",
        (left_sha, right_sha, right_sha, left_sha),
    ).fetchone()

    left_kind = left_item.get("content_kind") or ""
    right_kind = right_item.get("content_kind") or ""

    return {
        "left": left_item,
        "right": right_item,
        "left_text": left_text,
        "right_text": right_text,
        "diff_type": "text" if left_kind in TEXT_KINDS and right_kind in TEXT_KINDS else "meta",
        "relation": dict(relation) if relation else None,
    }


def same_day_groups(
    conn: sqlite3.Connection,
    *,
    semester: int | None = None,
    skrot: str | None = None,
    max_size: int = 20,
    limit: int = 100,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Treści z jednego katalogu i jednego dnia — „chyba jedna sesja" (Q8).

    EXIF w tej paczce nie istnieje (na próbce 400 obrazów ani jeden nie miał daty), więc
    zostaje `modified_date`. Ale w większości katalogów wszystkie pliki mają ten sam dzień,
    bo to data skopiowania paczki — i wtedy taka „grupa" jest tylko parafrazą zdania
    „te pliki leżą razem", które widać i bez niej.

    Dlatego bierzemy WYŁĄCZNIE katalogi, w których data naprawdę rozdziela pliki na kilka
    dni (w tej bazie: 899 grup zamiast 6139), i ucinamy grupy większe niż ``max_size`` —
    kilkadziesiąt plików z jednego dnia to zgrana paczka, nie sesja zdjęciowa.

    ``thresholds`` przyjmujemy dla symetrii z pozostałymi zapytaniami klastrów,
    ale ta grupa nie kubełkuje po `confidence` — nie licz tu progów „na zapas”,
    bo poprzednia wersja robiła to i wynik szedł do kosza.
    """
    clauses = ["f.modified_date IS NOT NULL", "f.sha256 IS NOT NULL"]
    params: list[Any] = []
    if semester is not None:
        clauses.append("cl.semester = ?")
        params.append(semester)
    if skrot is not None:
        clauses.append("cl.subject_key = ?")
        params.append(skrot)
    where = " AND ".join(clauses)

    rows = conn.execute(
        f"""
        SELECT f.folder_path AS folder,
               substr(f.modified_date, 1, 10) AS day,
               f.sha256 AS sha256,
               f.filename AS filename,
               f.size_bytes AS size_bytes,
               f.source_relative_path AS source_relative_path,
               cl.category AS category,
               cl.semester AS semester,
               cl.subject_key AS subject_key,
               cl.confidence AS confidence,
               cl.action AS action,
               cl.needs_review AS needs_review
        FROM files f
        LEFT JOIN classifications cl ON cl.sha256 = f.sha256
        WHERE {where}
        ORDER BY f.folder_path, day, f.file_id
        """,
        params,
    ).fetchall()

    dni_w_katalogu: dict[str, set[str]] = {}
    grupy: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        folder, day = str(row["folder"]), str(row["day"])
        dni_w_katalogu.setdefault(folder, set()).add(day)
        wpis = grupy.setdefault((folder, day), {})
        # Jedna treść może mieć kilka kopii w tym samym katalogu — liczy się raz.
        wpis.setdefault(str(row["sha256"]), {
            "sha256": str(row["sha256"]),
            "filename": row["filename"],
            "source_relative_path": row["source_relative_path"],
            "size_bytes": row["size_bytes"],
            "category": row["category"],
            # Semestr i przedmiot jadą razem z treścią, żeby widok mógł zdecydować
            # o całej sesji bez zgadywania, do którego przedmiotu należy.
            "semester": row["semester"],
            "subject_key": row["subject_key"],
            "confidence": row["confidence"],
            "action": row["action"],
            "needs_review": row["needs_review"],
        })

    sesje = [
        {"folder": folder, "day": day, "contents": list(tresci.values())}
        for (folder, day), tresci in sorted(grupy.items())
        if len(dni_w_katalogu[folder]) > 1 and 1 < len(tresci) <= max_size
    ]
    return {"total": len(sesje), "limit": limit, "groups": sesje[:limit]}
