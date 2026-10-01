"""Pulpit i karta jednego przedmiotu — liczniki, etapy i rozkład pewności.

Pulpit celowo woła ``status_report.collect`` zamiast powtarzać jego zapytania:
gdyby liczby w przeglądarce rozjechały się z ``just status``, nie dałoby się
powiedzieć, która wersja jest prawdziwa (``studio/AGENTS.md``, reguła 1). Z tego
samego powodu progi pewności biorą się z ``config/thresholds.yaml``, a nie
z literałów rozsypanych po widoku.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

import status_report
from orglib import config

from ._common import GROUND_TRUTH_RUN_ID

#: Kolejność etapów w kolejce pracy — ta sama, której używa `reports/STATUS.md`.
STAGE_ORDER = status_report.STAGE_ORDER

#: Pusty wpis przedmiotu (przedmiot, którego nikt jeszcze nie tknął).
_EMPTY_ENTRY: dict[str, Any] = {
    "ground_truth": 0, "planned": 0, "needs_review": 0,
    "actions": {}, "decided_at": None, "run_id": None,
}


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
