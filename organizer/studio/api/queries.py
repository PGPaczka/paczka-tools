"""Odczyt indeksu na potrzeby widoku — jedyne miejsce, w którym studio pisze SQL.

Pulpit celowo woła ``status_report.collect`` zamiast powtarzać jego zapytania:
gdyby liczby w przeglądarce rozjechały się z ``just status``, nie dałoby się
powiedzieć, która wersja jest prawdziwa (``studio/AGENTS.md``, reguła 1). Z tego
samego powodu progi pewności biorą się z ``config/thresholds.yaml``, a nie
z literałów rozsypanych po widoku.

Kształt odpowiedzi jest płaski i już policzony — front ma go wyświetlić, nie
dosumować.
"""

from __future__ import annotations

import fnmatch
import sqlite3
from typing import Any, Mapping, Sequence

import status_report
from orglib import config
from orglib.review import TEXT_KINDS, build_clusters

#: run_id, pod którym scan_target zapisuje treści leżące już w repo produktu.
GROUND_TRUTH_RUN_ID = status_report.GROUND_TRUTH_RUN_ID

#: Kolejność etapów w kolejce pracy — ta sama, której używa `reports/STATUS.md`.
STAGE_ORDER = status_report.STAGE_ORDER

#: Pusty wpis przedmiotu (przedmiot, którego nikt jeszcze nie tknął).
_EMPTY_ENTRY: dict[str, Any] = {
    "ground_truth": 0, "planned": 0, "needs_review": 0,
    "actions": {}, "decided_at": None, "run_id": None,
}

#: Kolumny jednej pozycji listy: treść + jej decyzja + JEDEN reprezentatywny plik.
#: Reprezentantem jest plik o najmniejszym ``file_id`` — ta sama treść bywa
#: zmaterializowana w kilkunastu paczkach, a lista pokazuje pozycje treści, nie
#: pozycje kopii.
_ITEM_COLUMNS = """
    c.sha256                                AS sha256,
    c.content_kind                          AS content_kind,
    c.extracted_text_path IS NOT NULL       AS has_text,
    c.ocr_done                              AS ocr_done,
    cl.semester                             AS semester,
    cl.subject_key                          AS subject_key,
    cl.category                             AS category,
    cl.slot                                 AS slot,
    cl.target_relative_path                 AS target_relative_path,
    cl.action                               AS action,
    cl.reason                               AS reason,
    cl.confidence                           AS confidence,
    cl.classification_method                AS classification_method,
    cl.needs_review                         AS needs_review,
    cl.is_outdated                          AS is_outdated,
    cl.run_id                               AS run_id,
    cl.decided_at                           AS decided_at,
    f.file_id                               AS file_id,
    f.source_package                        AS source_package,
    f.source_relative_path                  AS source_relative_path,
    f.filename                              AS filename,
    f.extension                             AS extension,
    f.size_bytes                            AS size_bytes,
    f.modified_date                         AS modified_date,
    f.status                                AS file_status,
    (SELECT COUNT(*) FROM files WHERE sha256 = c.sha256)     AS copies
"""

_ITEM_FROM = """
FROM content AS c
LEFT JOIN classifications AS cl ON cl.sha256 = c.sha256
LEFT JOIN files AS f ON f.file_id = (SELECT MIN(file_id) FROM files WHERE sha256 = c.sha256)
"""


def subject_payload(subject: config.Subject) -> dict[str, Any]:
    """Tożsamość przedmiotu tak, jak widzi ją katalog (``config/subjects.yaml``)."""
    return {
        "semester": subject.semester,
        "skrot": subject.skrot,
        "nazwa": subject.nazwa,
        "grupa": subject.grupa,
        "target_dir": subject.target_dir,
        "forms": list(subject.forms),
        "aliases": list(subject.aliases),
    }


def _entry_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Liczniki jednego przedmiotu + etap, dokładnie jak w `reports/STATUS.md`."""
    actions = {str(name): int(count) for name, count in dict(entry["actions"]).items()}
    return {
        "stage": status_report.stage_of(dict(entry)),
        "ground_truth": int(entry["ground_truth"]),
        "planned": int(entry["planned"]),
        "needs_review": int(entry["needs_review"]),
        "actions": actions,
        "decided_at": entry["decided_at"],
        "run_id": entry.get("run_id"),
    }


def dashboard(
    conn: sqlite3.Connection,
    subjects: Sequence[config.Subject],
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pulpit: globalne liczniki, przedmioty × etapy i kolejka „co następne”."""
    auto_apply, review_min = confidence_limits(thresholds)
    data = status_report.collect(conn)
    rows: list[dict[str, Any]] = []
    for subject in sorted(subjects, key=lambda s: (s.semester, s.grupa, s.skrot)):
        entry = data["per_subject"].get((subject.semester, subject.skrot), _EMPTY_ENTRY)
        rows.append({**subject_payload(subject), **_entry_payload(entry)})
    by_stage: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGE_ORDER}
    for row in rows:
        by_stage[row["stage"]].append(row)
    return {
        "thresholds": {"auto_apply": auto_apply, "review_min": review_min},
        "totals": {
            "packages": data["packages"],
            "folders": data["folders"],
            "duplicate_folders": data["duplicate_folders"],
            "files": data["files"],
            "files_by_status": data["files_by_status"],
            "contents": data["contents"],
            "with_text": data["with_text"],
            "relations": data["relations"],
            "plan_items": data["plan_items"],
            "applied": data["applied"],
            "subjects": len(rows),
        },
        "subjects": rows,
        "queue": [
            {
                "stage": stage,
                "count": len(by_stage[stage]),
                "subjects": [
                    {"semester": r["semester"], "skrot": r["skrot"], "nazwa": r["nazwa"],
                     "grupa": r["grupa"], "needs_review": r["needs_review"],
                     "planned": r["planned"], "ground_truth": r["ground_truth"]}
                    for r in by_stage[stage]
                ],
            }
            for stage in STAGE_ORDER
        ],
    }


def confidence_limits(thresholds: Mapping[str, Any] | None) -> tuple[float, float]:
    """Progi pewności z ``config/thresholds.yaml`` — jedno miejsce dla wszystkich widoków."""
    confidence = dict((thresholds or {}).get("confidence") or {})
    return float(confidence.get("auto_apply", 0.90)), float(confidence.get("review_min", 0.70))


def _confidence_bucket(value: float | None, auto_apply: float, review_min: float) -> str:
    """Kubełek pewności wg ``config/thresholds.yaml`` — nazwy jak w tamtych progach."""
    if value is None:
        return "brak"
    if value >= auto_apply:
        return "auto"
    if value >= review_min:
        return "review"
    return "unresolved"


def subject_detail(
    conn: sqlite3.Connection,
    subject: config.Subject,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Jeden przedmiot: liczniki pulpitu + rozbicie na kategorie, metody i pewność."""
    auto_apply, review_min = confidence_limits(thresholds)

    entry = status_report.collect(conn)["per_subject"].get(
        (subject.semester, subject.skrot), _EMPTY_ENTRY
    )
    rows = conn.execute(
        "SELECT category, action, classification_method, confidence, needs_review, is_outdated "
        "FROM classifications WHERE semester = ? AND subject_key = ? AND run_id <> ?",
        (subject.semester, subject.skrot, GROUND_TRUTH_RUN_ID),
    ).fetchall()

    categories: dict[str, dict[str, Any]] = {}
    methods: dict[str, int] = {}
    buckets: dict[str, int] = {"auto": 0, "review": 0, "unresolved": 0, "brak": 0}
    outdated = 0
    for row in rows:
        name = str(row["category"] or "—")
        bucket = categories.setdefault(
            name, {"category": name, "count": 0, "needs_review": 0, "min_confidence": None}
        )
        bucket["count"] += 1
        bucket["needs_review"] += 1 if row["needs_review"] else 0
        value = None if row["confidence"] is None else float(row["confidence"])
        if value is not None:
            current = bucket["min_confidence"]
            bucket["min_confidence"] = value if current is None else min(current, value)
        methods[str(row["classification_method"] or "—")] = (
            methods.get(str(row["classification_method"] or "—"), 0) + 1
        )
        buckets[_confidence_bucket(value, auto_apply, review_min)] += 1
        outdated += 1 if row["is_outdated"] else 0

    ground_truth_rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM classifications "
        "WHERE semester = ? AND subject_key = ? AND run_id = ? GROUP BY category",
        (subject.semester, subject.skrot, GROUND_TRUTH_RUN_ID),
    ).fetchall()

    return {
        "subject": subject_payload(subject),
        **_entry_payload(entry),
        "outdated": outdated,
        "categories": sorted(categories.values(), key=lambda c: (-c["count"], c["category"])),
        "methods": dict(sorted(methods.items())),
        "confidence": {
            "thresholds": {"auto_apply": auto_apply, "review_min": review_min},
            "buckets": buckets,
        },
        "ground_truth_categories": {
            str(row["category"] or "—"): int(row["n"]) for row in ground_truth_rows
        },
    }


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
        "relations": [dict(r) for r in relations],
        "plan_items": [dict(p) for p in plan],
        "applied": [dict(a) for a in applied],
        "manual_decision": None if manual is None else dict(manual),
    }


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


def _read_text_head(path: str | None, max_bytes: int = 4096) -> str | None:
    """Czyta początek wyekstrahowanego tekstu. Zwraca None gdy pliku nie ma."""
    if not path:
        return None
    from pathlib import Path
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError:
        return None


def cluster_diff(
    conn: sqlite3.Connection,
    left_sha: str,
    right_sha: str,
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
        left_text_path["extracted_text_path"] if left_text_path else None
    )
    right_text = _read_text_head(
        right_text_path["extracted_text_path"] if right_text_path else None
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
