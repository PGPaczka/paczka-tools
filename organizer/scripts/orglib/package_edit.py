"""Q4: zmiana nazwy materiału LEŻĄCEGO JUŻ W PACZCE — dysk i baza razem albo wcale.

Ręczne przeniesienie pliku w paczce rozjeżdża trzy rzeczy naraz: podgląd (szuka pliku
pod ścieżką z decyzji), rozmiar w notatce grafu i `verify` (widzi brak pod starą ścieżką
i plik spoza planu pod nową). Dlatego operacja idzie przez ten moduł: ``applied``,
``classifications`` i dysk zmieniają się w jednej transakcji.

Kolejność jest celowa. Transakcja (``BEGIN IMMEDIATE``) obejmuje TAKŻE sprawdzenie
zajętości nowej ścieżki, bo między sprawdzeniem a zapisem mogłaby wejść druga sesja
studia. Przeniesienie pliku idzie na końcu, a gdyby zawiódł sam ``COMMIT`` — plik wraca
pod starą nazwę. Stanu „plik przeniesiony, baza nie wie" nie ma ani przez chwilę.

Czego ten moduł NIE robi: nie dotyka planu. ``plan.jsonl`` ma swój ``plan_hash``, więc
edycja w miejscu unieważniłaby go po cichu — zamiast tego wynik niesie ``plan_stale``,
czyli „zbuduj plan od nowa".
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from orglib import config, decisions
from orglib.plan_apply import resolve_target


class NotInPackage(LookupError):
    """Ścieżka nie wskazuje pliku paczki zarejestrowanego w `applied`."""


class TargetTaken(ValueError):
    """Nowa ścieżka jest już zajęta na dysku albo w bazie."""


def rename_in_package(
    conn: sqlite3.Connection,
    *,
    paths: config.Paths,
    target_relative_path: str,
    filename: str,
    decided_by: str = "studio",
) -> dict[str, Any]:
    """Przenosi plik i zatwierdza obie tabele; przy błędzie wycofuje operację.

    Wymaga połączenia bez otwartej transakcji, żeby późniejszy rollback wywołującego
    nie mógł cofnąć samej bazy. Zachowuje pochodzenie wpisów, w tym ground truth.
    Plan zostaje bez zmian: odpowiedź sygnalizuje konieczność jego przebudowania.
    """
    old_path = resolve_target(paths, target_relative_path)
    if old_path is None or not old_path.is_file():
        raise NotInPackage(f"brak pliku w paczce: {target_relative_path}")
    row = conn.execute(
        "SELECT sha256 FROM applied WHERE target_relative_path = ?",
        (target_relative_path,),
    ).fetchone()
    if row is None:
        raise NotInPackage(f"ścieżka nie jest zapisana w applied: {target_relative_path}")

    new_target = decisions.renamed_target(target_relative_path, filename)
    result = {
        "old_path": target_relative_path,
        "target_relative_path": new_target,
        "sha256": row["sha256"],
        "changed": new_target != target_relative_path,
        "plan_stale": False,
        "decided_by": decided_by,
    }
    if not result["changed"]:
        return result

    new_path = resolve_target(paths, new_target)
    if new_path is None:
        raise ValueError(f"nowa ścieżka wychodzi poza paczkę: {new_target}")
    if conn.in_transaction:
        raise ValueError("zmiana nazwy w paczce wymaga osobnej transakcji")

    # Blokada przed sprawdzeniem zajętości chroni przed równoległym zapisem w studiu.
    conn.execute("BEGIN IMMEDIATE")
    moved = False
    try:
        if new_path.exists() or new_path.is_symlink():
            raise TargetTaken(f"ścieżka jest już zajęta na dysku: {new_target}")
        collision = conn.execute(
            "SELECT 1 FROM applied "
            "WHERE lower(target_relative_path) = lower(?) AND target_relative_path <> ? "
            "UNION ALL SELECT 1 FROM classifications "
            "WHERE lower(target_relative_path) = lower(?) AND target_relative_path <> ? "
            "LIMIT 1",
            (new_target, target_relative_path, new_target, target_relative_path),
        ).fetchone()
        if collision is not None:
            raise TargetTaken(f"ścieżka jest już zajęta w bazie: {new_target}")
        if not old_path.is_file():
            raise NotInPackage(f"brak pliku w paczce: {target_relative_path}")
        result["plan_stale"] = conn.execute(
            "SELECT 1 FROM plan_items WHERE target_relative_path = ? LIMIT 1",
            (target_relative_path,),
        ).fetchone() is not None

        updated = conn.execute(
            "UPDATE applied SET target_relative_path = ? "
            "WHERE target_relative_path = ? AND sha256 = ?",
            (new_target, target_relative_path, row["sha256"]),
        )
        if updated.rowcount != 1:
            raise NotInPackage(f"wpis applied zmienił się w trakcie operacji: {target_relative_path}")
        conn.execute(
            "UPDATE classifications SET target_relative_path = ? "
            "WHERE target_relative_path = ? AND sha256 = ?",
            (new_target, target_relative_path, row["sha256"]),
        )
        os.replace(old_path, new_path)
        moved = True
        conn.commit()
    except BaseException:
        try:
            # COMMIT też może zawieść: wtedy przywracamy nazwę na dysku.
            if moved:
                os.replace(new_path, old_path)
        finally:
            conn.rollback()
        raise
    return result
