"""Zapis ręcznych decyzji człowieka — biblioteka dla CLI (B14) i studia (S1).

Jedna decyzja dotyka DWÓCH tabel:
- ``manual_decisions`` — trwały zapis przeżywający przebudowę bazy (eksport JSONL);
- ``classifications`` — natychmiastowa aktualizacja widoczna w dashboardzie i planie
  (``classification_method='manual'``, ``confidence=1.0``).

Wiersze ``ground_truth`` w ``classifications`` NIGDY nie są nadpisywane — mają osobny
``run_id`` i mówią, że materiał już leży w paczce. Kolizja sha256 z ground truth
jest sygnalizowana czytelnym błędem, nie cichym pominięciem.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from orglib import config, db, plan_lint

MANUAL_RUN_ID = "manual_decision"
GROUND_TRUTH_RUN_ID = "ground_truth"

DECISION_TYPES = ("classify", "relation", "outdated", "skip", "quarantine")

EXPORT_PATH = config.ORGANIZER_ROOT / "reports" / "manual_decisions.jsonl"


class GroundTruthConflict(ValueError):
    """Próba nadpisania decyzji ground truth."""


class NoTargetPath(LookupError):
    """Treść nie ma ścieżki docelowej, więc nie ma czego przemianować."""


class TargetCollision(ValueError):
    """Inna treść celuje już w tę samą ścieżkę."""


def record_decision(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    decision_type: str,
    decided_by: str,
    semester: Optional[int] = None,
    subject_key: Optional[str] = None,
    category: Optional[str] = None,
    target_relative_path: Optional[str] = None,
    action: Optional[str] = None,
    relation_override: Optional[str] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Zapisuje jedną decyzję do obu tabel. Zwraca podsumowanie.

    Dla ``decision_type='classify'`` wymagane są ``semester``, ``subject_key``
    i ``action``. Pozostałe typy (``skip``, ``quarantine``, ``outdated``,
    ``relation``) potrzebują co najwyżej ``target_relative_path``.
    """
    if decision_type not in DECISION_TYPES:
        raise ValueError(f"nieznany decision_type={decision_type!r}")

    decided_at = db.now_iso()

    if decision_type == "classify":
        if semester is None or subject_key is None:
            raise ValueError("classify wymaga semester i subject_key")
        if action is None:
            action = "copy"
        _guard_ground_truth(conn, sha256)

    db.upsert_manual_decision(conn, {
        "sha256": sha256,
        "decision_type": decision_type,
        "target_relative_path": target_relative_path,
        "relation_override": relation_override,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "note": note,
    })

    if decision_type == "classify":
        row: dict[str, Any] = {
            "sha256": sha256,
            "semester": semester,
            "subject_key": subject_key,
            "classification_method": "manual",
            "confidence": 1.0,
            "run_id": MANUAL_RUN_ID,
            "decided_at": decided_at,
            "action": action,
            "needs_review": 0,
        }
        if category is not None:
            row["category"] = category
        if target_relative_path is not None:
            row["target_relative_path"] = target_relative_path
        db.upsert_classification(conn, row)
    elif decision_type in ("skip", "quarantine"):
        _guard_ground_truth(conn, sha256)
        existing = conn.execute(
            "SELECT semester, subject_key FROM classifications WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if existing is not None:
            db.upsert_classification(conn, {
                "sha256": sha256,
                "semester": int(existing["semester"]),
                "subject_key": str(existing["subject_key"]),
                "classification_method": "manual",
                "confidence": 1.0,
                "run_id": MANUAL_RUN_ID,
                "decided_at": decided_at,
                "action": decision_type,
                "needs_review": 0,
            })

    return {
        "sha256": sha256,
        "decision_type": decision_type,
        "decided_at": decided_at,
    }


def record_batch(
    conn: sqlite3.Connection,
    decisions: list[dict[str, Any]],
    *,
    decided_by: str,
) -> list[dict[str, Any]]:
    """Zapisuje wiele decyzji atomowo. Zwraca listę podsumowań.

    Buduje wszystkie wiersze z góry (z walidacją i ochroną ground truth),
    a potem robi dwa ``upsert_many`` — każdy w jednej transakcji ``with conn:``.
    """
    decided_at = db.now_iso()
    manual_rows: list[dict[str, Any]] = []
    classification_rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for d in decisions:
        sha = d["sha256"]
        dtype = d["decision_type"]
        if dtype not in DECISION_TYPES:
            raise ValueError(f"nieznany decision_type={dtype!r}")

        if dtype == "classify":
            sem = d.get("semester")
            subj = d.get("subject_key")
            if sem is None or subj is None:
                raise ValueError("classify wymaga semester i subject_key")
            _guard_ground_truth(conn, sha)
            classification_rows.append({
                "sha256": sha,
                "semester": sem,
                "subject_key": subj,
                "category": d.get("category"),
                "target_relative_path": d.get("target_relative_path"),
                "classification_method": "manual",
                "confidence": 1.0,
                "run_id": MANUAL_RUN_ID,
                "decided_at": decided_at,
                "action": d.get("action", "copy"),
                "needs_review": 0,
            })
        elif dtype in ("skip", "quarantine"):
            _guard_ground_truth(conn, sha)
            existing = conn.execute(
                "SELECT semester, subject_key FROM classifications WHERE sha256 = ?",
                (sha,),
            ).fetchone()
            if existing is not None:
                classification_rows.append({
                    "sha256": sha,
                    "semester": int(existing["semester"]),
                    "subject_key": str(existing["subject_key"]),
                    "classification_method": "manual",
                    "confidence": 1.0,
                    "run_id": MANUAL_RUN_ID,
                    "decided_at": decided_at,
                    "action": dtype,
                    "needs_review": 0,
                })

        manual_rows.append({
            "sha256": sha,
            "decision_type": dtype,
            "target_relative_path": d.get("target_relative_path"),
            "relation_override": d.get("relation_override"),
            "decided_by": decided_by,
            "decided_at": decided_at,
            "note": d.get("note"),
        })
        results.append({"sha256": sha, "decision_type": dtype, "decided_at": decided_at})

    db.upsert_many(conn, "manual_decisions", manual_rows, conflict=("sha256",))
    if classification_rows:
        db.upsert_many(conn, "classifications", classification_rows, conflict=("sha256",))
    return results


def undo_last(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    """Cofa ostatnią decyzję (najnowszy ``decided_at`` w ``manual_decisions``).

    Kasuje wiersz z ``manual_decisions`` i przywraca ``classifications`` do stanu
    sprzed decyzji (usunięcie wiersza, gdy nie było wcześniejszego zapisu).
    Zwraca ``None``, gdy tabela jest pusta.
    """
    row = conn.execute(
        "SELECT * FROM manual_decisions ORDER BY decided_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    sha = str(row["sha256"])
    with conn:
        conn.execute("DELETE FROM manual_decisions WHERE sha256 = ?", (sha,))
        existing = conn.execute(
            "SELECT run_id FROM classifications WHERE sha256 = ?", (sha,)
        ).fetchone()
        if existing and str(existing["run_id"]) == MANUAL_RUN_ID:
            conn.execute("DELETE FROM classifications WHERE sha256 = ?", (sha,))
    return dict(row)


def export(conn: sqlite3.Connection, path: Optional[Path] = None) -> int:
    """Eksportuje decyzje do JSONL. Wrapper na ``db.export_manual_decisions``."""
    target = Path(path) if path is not None else EXPORT_PATH
    return db.export_manual_decisions(conn, target)


def _guard_ground_truth(conn: sqlite3.Connection, sha256: str) -> None:
    row = conn.execute(
        "SELECT run_id FROM classifications WHERE sha256 = ? AND run_id = ?",
        (sha256, GROUND_TRUTH_RUN_ID),
    ).fetchone()
    if row is not None:
        raise GroundTruthConflict(
            f"sha256={sha256[:16]}… ma run_id=ground_truth — decyzja ręczna "
            "nie może nadpisać materiału, który już leży w paczce"
        )


def rename_target(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    filename: str,
    decided_by: str = "studio",
) -> dict[str, Any]:
    """Zmienia SAMĄ nazwę pliku w ścieżce docelowej; katalog zostaje.

    Osobna operacja, bo edycja całej ścieżki miesza dwie różne decyzje — „to ma się
    nazywać inaczej" i „to ma leżeć gdzie indziej" — i przy okazji pozwala wpisać
    nazwę, którą bramka planu odrzuci dopiero przy `validate`. Reguły nazw biorą się
    stąd, co bramka (``plan_lint``), więc tu i tam obowiązuje jedno prawo.
    """
    row = conn.execute(
        "SELECT semester, subject_key, category, action, target_relative_path "
        "FROM classifications WHERE sha256 = ?",
        (sha256,),
    ).fetchone()
    if row is None:
        raise NoTargetPath(
            f"sha256={sha256[:12]}… nie ma klasyfikacji, więc nie ma ścieżki docelowej do zmiany"
        )
    old_target = row["target_relative_path"]
    if not old_target:
        raise NoTargetPath(
            f"sha256={sha256[:12]}… nie ma ścieżki docelowej — najpierw decyzja o kategorii"
        )

    filename = filename.strip()
    if not filename:
        raise ValueError("nazwa pliku nie może być pusta")
    if "/" in filename or "\\" in filename:
        raise ValueError(
            "ta operacja zmienia wyłącznie nazwę — przeniesienie to edycja całej ścieżki docelowej"
        )
    if filename in (".", ".."):
        raise ValueError("nazwa nie może być `.` ani `..`")
    # `check_windows_name` patrzy na koniec CAŁEGO segmentu, więc spacji przed
    # rozszerzeniem („kol1 .pdf") samo by nie złapało — a to prawie zawsze literówka.
    stem = PurePosixPath(filename).stem
    if stem and stem != stem.rstrip(". "):
        raise ValueError("nazwa przed rozszerzeniem nie może kończyć się spacją ani kropką")

    new_target = str(PurePosixPath(old_target).with_name(filename))
    problems = plan_lint.check_path_safety(new_target) + plan_lint.check_windows_name(new_target)
    if problems:
        raise ValueError(f"nazwa {filename!r}: " + ", ".join(problems))

    # Ta sama nazwa to brak decyzji: zapis zamieniłby cudzą heurystykę w „decyzję człowieka".
    if new_target == old_target:
        return {
            "sha256": sha256,
            "old_path": old_target,
            "target_relative_path": new_target,
            "changed": False,
            "decided_at": None,
        }

    # Wielkość liter pomijamy, bo paczka jedzie do repo klonowanego także na Windowsie
    # i macOS-ie: tam `Wyklad1.pdf` i `wyklad1.pdf` to jeden plik, czyli cicha strata.
    collision = conn.execute(
        "SELECT sha256 FROM classifications "
        "WHERE lower(target_relative_path) = lower(?) AND sha256 <> ?",
        (new_target, sha256),
    ).fetchone()
    if collision is not None:
        raise TargetCollision(
            f"ścieżka {new_target} jest już zajęta przez treść {str(collision['sha256'])[:12]}…"
        )

    # Zapis idzie przez `record_decision`, więc ochrona ground truth i wpis
    # w `manual_decisions` są te same co dla każdej innej ręcznej decyzji.
    result = record_decision(
        conn,
        sha256=sha256,
        decision_type="classify",
        decided_by=decided_by,
        semester=row["semester"],
        subject_key=row["subject_key"],
        category=row["category"],
        target_relative_path=new_target,
        action=row["action"] or "copy",
    )
    return {
        "sha256": sha256,
        "old_path": old_target,
        "target_relative_path": new_target,
        "changed": True,
        "decided_at": result["decided_at"],
    }
