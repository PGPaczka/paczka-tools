"""Statystyki na żywo, historia decyzji i wyszukiwanie — widoki przekrojowe.

``live_stats`` jest odpowiednikiem `reports/STATUS.md` bez generowania pliku,
więc liczby bierze z ``status_report.collect``, a nie z własnych zapytań.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

import status_report
from orglib import config

from ._common import GROUND_TRUTH_RUN_ID, _ITEM_COLUMNS, _ITEM_FROM
from .dashboard import confidence_limits
from .items import _with_bucket


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
