"""S3: plan przedmiotu widziany przez studio — drzewo, diff i wynik bramki.

Widok planu nie liczy niczego po swojemu. Ustalenia bierze z tej samej bramki co
`validate_plan` (``orglib.plan_gate``), a to, co `apply` zrobiłby z dyskiem — z tego
samego silnika co `apply` (``orglib.plan_apply``). Dzięki temu „przycisk jest
martwy” i „skrypt odmawia” to jedna i ta sama decyzja, a nie dwie, które mogą się
rozjechać.

Źródłem planu jest PLIK ``reports/{SKROT}/plan.jsonl`` (z jego nagłówkiem
``plan_hash``), bo to on jest wejściem `apply` — nie zapytanie do bazy.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from orglib import config, plan_apply, plan_gate
from orglib.plan_build import plan_hash
from orglib.plan_lint import summarize, tree_diff

#: Nazwy plików planu w kolejności szukania — ta sama, co w `validate_plan`/`apply`.
PLAN_CANDIDATES = ("plan.jsonl",)

#: Ile ustaleń i pozycji oddajemy widokowi. Reszta zostaje w raportach.
FINDING_LIMIT = 200
OPERATION_LIMIT = 200

#: Akcje, które NIE kładą pliku w paczce — to jest lista „nie ma jeszcze miejsca”.
HOMELESS_ACTIONS = ("skip", "quarantine")


def plan_dir(subject: config.Subject, subjects: Sequence[config.Subject]) -> Path:
    """Katalog raportów przedmiotu — liczony tak samo jak w `prepare_subject`."""
    root = config.ORGANIZER_ROOT / "reports"
    if sum(s.skrot.casefold() == subject.skrot.casefold() for s in subjects) > 1:
        root = root / f"SEM{subject.semester}" / subject.grupa
    return root / subject.skrot


def find_plan(subject: config.Subject, subjects: Sequence[config.Subject]) -> Path | None:
    """Plik planu przedmiotu albo ``None``, gdy jeszcze go nie zbudowano."""
    base = plan_dir(subject, subjects)
    for name in PLAN_CANDIDATES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def overview(
    conn: sqlite3.Connection,
    subject: config.Subject,
    subjects: Sequence[config.Subject],
    paths: config.Paths,
    *,
    rules: Any,
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    """Wszystko, czego widok potrzebuje przed decyzją o `apply` — policzone raz."""
    plan_path = find_plan(subject, subjects)
    if plan_path is None:
        return {
            "subject": {"semester": subject.semester, "skrot": subject.skrot,
                        "nazwa": subject.nazwa, "grupa": subject.grupa,
                        "target_dir": subject.target_dir},
            "plan": None,
            "can_apply": False,
            "reason": "brak planu — zbuduj go etapem `plan`",
        }

    rows, metas = plan_gate.read_plan([plan_path])
    digest = plan_hash(rows)
    confidence = dict(thresholds.get("confidence") or {})
    ground_truth = {
        str(row["target_relative_path"]): str(row["sha256"])
        for row in conn.execute("SELECT target_relative_path, sha256 FROM applied")
    }
    findings = plan_gate.evaluate(
        rows, metas,
        subject=subject, rules=rules,
        auto_apply=float(confidence.get("auto_apply", 0.90)),
        review_min=float(confidence.get("review_min", 0.70)),
        ground_truth=ground_truth,
    )
    counts = summarize(findings)
    blocking = plan_gate.blocking_count(findings)

    copies = plan_apply.copies_by_sha(conn, [str(row.get("source_sha256")) for row in rows])
    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)
    states = plan_apply.summarize(operations)
    blockers = [op for op in operations if op.blocking]

    actions: dict[str, int] = {}
    for row in rows:
        name = str(row.get("action") or "—")
        actions[name] = actions.get(name, 0) + 1

    diff = tree_diff(rows)
    return {
        "subject": {"semester": subject.semester, "skrot": subject.skrot,
                    "nazwa": subject.nazwa, "grupa": subject.grupa,
                    "target_dir": subject.target_dir},
        "plan": {
            "path": str(plan_path),
            "plan_hash": digest,
            "declared_hash": str((metas[0] if metas else {}).get("plan_hash") or ""),
            "created_at": str((metas[0] if metas else {}).get("created_at") or ""),
            "items": len(rows),
            "actions": dict(sorted(actions.items())),
            "needs_review": sum(1 for row in rows if row.get("needs_review")),
        },
        "validation": {
            "errors": counts["error"],
            "warnings": counts["warning"],
            "blocking": blocking,
            "findings": [finding.as_row() for finding in findings[:FINDING_LIMIT]],
            "truncated": max(len(findings) - FINDING_LIMIT, 0),
        },
        "diff": {
            "files": len(diff["files"]),
            "folders": len(diff["folders"]),
            "new": states["new"],
            "present": states["present"],
            "conflict": states["conflict"],
            "missing_source": states["missing_source"],
            "outside": states["outside"],
            "blockers": [op.as_row() for op in blockers[:OPERATION_LIMIT]],
        },
        # `apply` i tak sprawdzi to u siebie; tutaj jest po to, żeby widok nie
        # zachęcał do kliknięcia, które musi się skończyć odmową.
        "can_apply": blocking == 0 and not blockers,
        "reason": (
            "plan odrzucony przez bramkę" if blocking else
            "pozycje nie do wykonania bezpiecznie" if blockers else ""
        ),
    }


def homeless(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pozycje, które nie dostają miejsca w drzewie: pominięte, kwarantanna, do obejrzenia."""
    out: list[dict[str, Any]] = []
    for row in rows:
        action = str(row.get("action") or "")
        review = bool(row.get("needs_review"))
        if action in HOMELESS_ACTIONS or review:
            out.append({
                "sha256": str(row.get("source_sha256") or ""),
                "action": action or None,
                "category": row.get("category"),
                "reason": row.get("reason"),
                "confidence": row.get("confidence"),
                "needs_review": review,
                "target_rel": row.get("target_rel"),
            })
    return out


def target_tree(
    conn: sqlite3.Connection,
    subject: config.Subject,
    subjects: Sequence[config.Subject],
    paths: config.Paths,
) -> dict[str, Any]:
    """Drzewo docelowe przedmiotu: co już leży w paczce i co dołoży plan.

    Stan pliku bierze się z tego samego silnika, co wykonanie (``plan_apply``):
    ``new`` dojdzie, ``present`` już jest, ``conflict`` zatrzyma `apply`.
    Do tego ``ground_truth`` — materiał ułożony ręcznie, którego plan nie dotyka.
    """
    plan_path = find_plan(subject, subjects)
    rows: list[dict[str, Any]] = []
    if plan_path is not None:
        rows, _ = plan_gate.read_plan([plan_path])

    copies = plan_apply.copies_by_sha(conn, [str(row.get("source_sha256")) for row in rows])
    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)
    entries: dict[str, dict[str, Any]] = {}
    for operation in operations:
        entries[operation.target_rel] = {
            "state": operation.state, "sha256": operation.sha256, "detail": operation.detail,
        }
    prefix = subject.target_dir.rstrip("/") + "/"
    for row in conn.execute(
        "SELECT target_relative_path, sha256 FROM applied WHERE target_relative_path LIKE ?",
        (prefix + "%",),
    ):
        path = str(row["target_relative_path"])
        entries.setdefault(path, {"state": "ground_truth", "sha256": str(row["sha256"]),
                                  "detail": "materiał już ułożony w paczce"})

    folders: dict[str, dict[str, Any]] = {}
    for path, entry in sorted(entries.items()):
        parent = str(PurePosixPath(path).parent)
        node = folders.setdefault(parent, {"path": parent, "files": [], "states": {}})
        node["files"].append({"name": PurePosixPath(path).name, "path": path, **entry})
        node["states"][entry["state"]] = node["states"].get(entry["state"], 0) + 1

    # Pozycjom bez miejsca dokładamy nazwę pliku: bez niej „przenieś tu” nie ma
    # jak zbudować ścieżki docelowej, a widok musiałby ją zgadywać ze ścieżki źródła.
    unplaced = homeless(rows)
    names = {
        str(row["sha256"]): str(row["filename"] or "")
        for row in conn.execute(
            "SELECT sha256, filename, MIN(file_id) FROM files "
            "WHERE sha256 IS NOT NULL GROUP BY sha256"
        )
    }
    for item in unplaced:
        item["filename"] = names.get(item["sha256"]) or PurePosixPath(
            str(item.get("target_rel") or item["sha256"])
        ).name

    return {
        "target_dir": subject.target_dir,
        "folders": [folders[key] for key in sorted(folders)],
        "files": sum(len(node["files"]) for node in folders.values()),
        "homeless": unplaced,
    }
