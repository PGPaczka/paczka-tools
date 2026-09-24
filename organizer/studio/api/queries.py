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
from orglib import config, folder_links, preview as preview_lib
from orglib.naming import best_name
from orglib.review import TEXT_KINDS, build_clusters

#: Ile znaków głowy tekstu wysyłamy do widoku (podgląd i diff klastra). Tyle
#: wystarcza, żeby rozpoznać dokument; całość leży w ``work`` dla tego, kto chce czytać.
PREVIEW_TEXT_LIMIT = 4096

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
    f.folder_path                           AS folder_path,
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


# --- S4.2: decision history ---

def decision_history(
    conn: sqlite3.Connection,
    *,
    decided_by: str | None = None,
    since: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Lista ręcznych decyzji, najnowsze najpierw."""
    clauses: list[str] = []
    params: list[Any] = []
    if decided_by:
        clauses.append("decided_by = ?")
        params.append(decided_by)
    if since:
        clauses.append("decided_at >= ?")
        params.append(since)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    total = int(conn.execute(
        f"SELECT COUNT(*) AS n FROM manual_decisions{where}", params
    ).fetchone()["n"])
    rows = conn.execute(
        f"SELECT * FROM manual_decisions{where} ORDER BY decided_at DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "decisions": [dict(r) for r in rows],
    }


# --- S4.3: cross-search ---

def search(
    conn: sqlite3.Connection,
    query: str,
    thresholds: Mapping[str, Any] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Wyszukiwanie po nazwie pliku, ścieżce, kategorii, sha256."""
    auto_apply, review_min = confidence_limits(thresholds)
    needle = f"%{query}%"
    rows = conn.execute(
        f"SELECT {_ITEM_COLUMNS} {_ITEM_FROM} "
        "WHERE f.filename LIKE ? OR f.source_relative_path LIKE ? "
        "OR cl.category LIKE ? OR c.sha256 LIKE ? "
        "ORDER BY COALESCE(cl.needs_review, 0) DESC, cl.confidence ASC "
        "LIMIT ?",
        (needle, needle, needle, needle, limit),
    ).fetchall()
    return {
        "query": query,
        "total": len(rows),
        "items": [_with_bucket(row, auto_apply, review_min) for row in rows],
    }


# --- S4.4: live stats ---

def live_stats(
    conn: sqlite3.Connection,
    subjects: Sequence[config.Subject],
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Odpowiednik STATUS.md bez generowania pliku."""
    auto_apply, review_min = confidence_limits(thresholds)
    data = status_report.collect(conn)

    stage_counts: dict[str, int] = {}
    for subject in subjects:
        entry = data["per_subject"].get(
            (subject.semester, subject.skrot),
            {"ground_truth": 0, "planned": 0, "needs_review": 0, "actions": {}},
        )
        stage = status_report.stage_of(dict(entry))
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    method_counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT classification_method, COUNT(*) AS n FROM classifications "
        "WHERE run_id <> ? GROUP BY classification_method",
        (GROUND_TRUTH_RUN_ID,),
    ):
        method_counts[str(row["classification_method"] or "—")] = int(row["n"])

    category_counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT category, COUNT(*) AS n FROM classifications "
        "WHERE run_id <> ? GROUP BY category",
        (GROUND_TRUTH_RUN_ID,),
    ):
        category_counts[str(row["category"] or "—")] = int(row["n"])

    action_counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT action, COUNT(*) AS n FROM classifications "
        "WHERE run_id <> ? GROUP BY action",
        (GROUND_TRUTH_RUN_ID,),
    ):
        action_counts[str(row["action"] or "—")] = int(row["n"])

    manual_count = int(conn.execute("SELECT COUNT(*) FROM manual_decisions").fetchone()[0])

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
            "subjects": len(subjects),
            "manual_decisions": manual_count,
        },
        "stages": stage_counts,
        "methods": method_counts,
        "categories": category_counts,
        "actions": action_counts,
    }



def plan_conflicts(
    conn: sqlite3.Connection,
    *,
    semester: int | None = None,
    skrot: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Dwie treści w jednej ścieżce docelowej — albo ścieżka zajęta przez paczkę.

    Bramka planu widzi to samo (`kolizja_celu`, `nadpisanie_ground_truth`), ale dopiero
    przy `validate` i tylko jako tekst. Liczymy z ŻYWEJ bazy, nie z pliku planu, żeby
    zmiana nazwy gasiła konflikt od razu — inaczej naprawa byłaby widoczna dopiero po
    ponownym zbudowaniu planu.

    Konflikty są rzadkie (`build_plan.resolve_collisions` rozstrzyga większość automatycznie),
    więc najpierw pytamy o SAME kolidujące ścieżki, a szczegóły treści dociągamy wyłącznie
    dla nich. Pełne łączenie z `files` dla wszystkich zaplanowanych pozycji trwało 5,5 s.
    """
    clauses = [
        "cl.action IN ('copy', 'media')",
        "cl.target_relative_path IS NOT NULL",
        "cl.target_relative_path <> ''",
    ]
    params: list[Any] = []
    if semester is not None:
        clauses.append("cl.semester = ?")
        params.append(semester)
    if skrot is not None:
        clauses.append("cl.subject_key = ?")
        params.append(skrot)
    where = " AND ".join(clauses)

    # Zwijanie wielkości liter robimy w Pythonie: `lower()` SQLite-a zna tylko ASCII,
    # a nazwy są polskie — Windows i macOS zwijają również „Ł". Zrobione przez funkcję
    # w SQLite kosztowało 1,9 s (miliony wywołań w złączeniu z `applied`); tu czytamy
    # dwie płaskie listy i resztę liczymy na słownikach.
    cele: dict[str, set[str]] = {}
    for row in conn.execute(
        f"SELECT cl.sha256 AS sha256, cl.target_relative_path AS cel "
        f"FROM classifications cl WHERE {where}",
        params,
    ):
        cele.setdefault(str(row["cel"]).lower(), set()).add(str(row["sha256"]))

    sporne = {klucz for klucz, shy in cele.items() if len(shy) > 1}
    zajete = {}
    for row in conn.execute("SELECT target_relative_path AS cel, sha256 FROM applied"):
        klucz = str(row["cel"]).lower()
        kandydaci = cele.get(klucz)
        if kandydaci and kandydaci != {str(row["sha256"])}:
            zajete[klucz] = str(row["sha256"])

    klucze = sorted(sporne | set(zajete))
    total = len(klucze)
    klucze = klucze[:limit]
    if not klucze:
        return {"total": total, "conflicts": []}

    # Szczegóły dociągamy po sha256 — mamy je już z pierwszego odczytu, a `sha256`
    # jest kluczem, więc zapytanie nie skanuje niczego dodatkowo.
    sporne_sha = sorted({sha for klucz in klucze for sha in cele[klucz]})
    miejsca = ",".join("?" * len(sporne_sha))
    wiersze = conn.execute(
        f"""
        SELECT cl.sha256 AS sha256,
               cl.target_relative_path AS target_relative_path,
               cl.category AS category,
               cl.confidence AS confidence,
               cl.classification_method AS classification_method,
               cl.needs_review AS needs_review,
               f.filename AS filename,
               f.source_relative_path AS source_relative_path,
               f.size_bytes AS size_bytes
        FROM classifications cl
        LEFT JOIN files f ON f.file_id = (SELECT MIN(file_id) FROM files WHERE sha256 = cl.sha256)
        WHERE cl.sha256 IN ({miejsca})
        ORDER BY cl.sha256
        """,
        sporne_sha,
    ).fetchall()

    grupy: dict[str, list[Any]] = {}
    for row in wiersze:
        grupy.setdefault(str(row["target_relative_path"]).lower(), []).append(row)

    conflicts: list[dict[str, Any]] = []
    for klucz in klucze:
        tresci = grupy.get(klucz, [])
        if not tresci:
            continue
        conflicts.append({
            # Materiał leżący już w paczce jest poważniejszą przeszkodą niż spór dwóch
            # kandydatów, więc gdy zachodzą oba, mówimy o tym pierwszym.
            "kind": "applied" if klucz in zajete else "plan",
            "path": str(tresci[0]["target_relative_path"]),
            "applied_sha256": zajete.get(klucz),
            "contents": [{
                "sha256": str(row["sha256"]),
                "filename": row["filename"],
                "source_relative_path": row["source_relative_path"],
                "size_bytes": row["size_bytes"],
                "confidence": row["confidence"],
                "classification_method": row["classification_method"],
                "category": row["category"],
                "needs_review": row["needs_review"],
            } for row in tresci],
        })

    return {"total": total, "conflicts": conflicts}


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
    """
    auto_apply, review_min = confidence_limits(thresholds)
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


def preview(
    conn: sqlite3.Connection,
    sha256: str,
    paths: config.Paths,
    *,
    limit: int = PREVIEW_TEXT_LIMIT,
) -> dict[str, Any] | None:
    """Co da się pokazać o treści: głowa tekstu, obraz i rodzaj podglądu.

    Widok pyta RAZ i wie, co narysować (``preview_kind``: ``page`` dla PDF,
    ``image`` dla obrazu, ``text`` gdy jest sama głowa tekstu, ``none`` gdy nie ma
    nic). Bez tego front zgadywałby po rozszerzeniu — czyli liczyłby regułę,
    której nie policzył backend.
    """
    row = conn.execute(
        "SELECT sha256, content_kind, extracted_text_path, ocr_done FROM content WHERE sha256 = ?",
        (sha256,),
    ).fetchone()
    if row is None:
        return None

    kind = str(row["content_kind"] or "")
    head = preview_lib.text_head(paths, row["extracted_text_path"], limit)
    copies = preview_lib.source_copies(conn, sha256)
    source = preview_lib.first_existing_copy(paths, copies)
    # Materiał bez kopii w źródłach, ale obecny w paczce: podgląd bierze go stamtąd.
    if source is None:
        source = preview_lib.package_copy(paths, conn, sha256)

    has_image = source is not None and (kind in preview_lib.PAGE_KINDS or kind in preview_lib.IMAGE_KINDS)
    # Bez wyekstrahowanego tekstu sięgamy do samego pliku, o ile to tekst: extract
    # nie dotknął ani jednej treści `other` i ponad dwustu `text`/`code`, a przy
    # takiej pozycji panel pokazywał pustkę — nie dało się stwierdzić, czym ona jest.
    if head is None and not has_image and source is not None and kind in preview_lib.SOURCE_TEXT_KINDS:
        head = preview_lib.source_text_head(source, limit)

    if has_image and kind in preview_lib.PAGE_KINDS:
        preview_kind = "page"
    elif has_image:
        preview_kind = "image"
    elif head:
        preview_kind = "text"
    else:
        preview_kind = "none"

    return {
        "sha256": sha256,
        "content_kind": row["content_kind"],
        "text_head": head,
        "has_text": head is not None,
        # Widok ma pokazać, że to WYCINEK: bez tego osiem linijek wygląda jak cały plik.
        "text_truncated": bool(head is not None and len(head) >= limit),
        "text_language": preview_lib.text_language(source.name, kind) if source is not None else None,
        "has_image": has_image,
        "preview_kind": preview_kind,
        "has_thumbnail": (paths.work_thumbnails / f"{sha256}.jpg").is_file(),
        "pages": preview_lib.page_count(source) if (source and kind in preview_lib.PAGE_KINDS) else None,
        "copies": len(copies),
        # Treść z samej paczki nie ma kopii w źródłach — pokazujemy wtedy, skąd
        # NAPRAWDĘ wzięliśmy podgląd, zamiast wywracać się na pustej liście.
        "source_path": f"{copies[0][0]}/{copies[0][1]}" if copies else (
            None if source is None else str(source.relative_to(paths.target_repo))
        ),
        "ocr_done": bool(row["ocr_done"]),
    }


def preview_image(
    conn: sqlite3.Connection,
    sha256: str,
    paths: config.Paths,
    *,
    page: int = 1,
    width: int | None = None,
) -> tuple[bytes, str] | None:
    """Bajty obrazu podglądu i jego typ MIME; ``None``, gdy nie ma czego pokazać.

    PDF renderuje się do PNG, obraz idzie jako miniatura JPEG z ``work/thumbnails``
    (ten sam cache co raport B9). Czytamy WYŁĄCZNIE plik wskazany przez indeks
    i tylko przez helper containmentu.
    """
    row = conn.execute(
        "SELECT content_kind FROM content WHERE sha256 = ?", (sha256,)
    ).fetchone()
    if row is None:
        return None
    kind = str(row["content_kind"] or "")
    source = preview_lib.first_existing_copy(paths, preview_lib.source_copies(conn, sha256))
    if source is None:
        source = preview_lib.package_copy(paths, conn, sha256)
    if source is None:
        return None
    if kind in preview_lib.PAGE_KINDS:
        payload = preview_lib.render_pdf_page(
            source, page=page, width=width or preview_lib.PAGE_WIDTH
        )
        return (payload, "image/jpeg") if payload else None
    if kind in preview_lib.IMAGE_KINDS:
        # Domyślna szerokość idzie z cache (jedna miniatura na treść, liczona raz);
        # każda inna jest renderowana na bieżąco, bo cache ma ustalony rozmiar.
        if width is None or width == preview_lib.THUMBNAIL_SIZE[0]:
            cached = preview_lib.thumbnail(paths, sha256, source)
            if cached is None:
                return None
            try:
                return cached.read_bytes(), "image/jpeg"
            except OSError:
                return None
        payload = preview_lib.render_image(source, width)
        return (payload, "image/jpeg") if payload else None
    return None


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
