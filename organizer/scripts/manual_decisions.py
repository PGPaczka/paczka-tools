"""B14: CLI do zapisu ręcznych decyzji z review.

Decyzja trafia do ``manual_decisions`` (trwały zapis, eksport JSONL) i do
``classifications`` (``classification_method='manual'``, ``confidence=1.0``).

Logika zapisu jest w ``orglib.decisions`` — ten sam moduł importuje studio (S1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db
from orglib.decisions import (
    DECISION_TYPES,
    GroundTruthConflict,
    export,
    record_batch,
    record_decision,
    undo_last,
)

app = typer.Typer(add_completion=False, help=__doc__)

DB_OPTION = typer.Option(None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml).")


def _db_path(explicit: Optional[Path]) -> Path:
    return Path(explicit) if explicit is not None else config.load_paths().work_db


def _require_db(explicit: Optional[Path]) -> Path:
    path = _db_path(explicit)
    if not path.exists():
        typer.echo(f"brak bazy: {path} — uruchom najpierw first-pass", err=True)
        raise typer.Exit(code=1)
    return path


@app.command("record")
def cmd_record(
    sha256: str = typer.Argument(..., help="SHA-256 treści (64 znaki hex)."),
    decision_type: str = typer.Argument(..., help=f"Typ: {', '.join(DECISION_TYPES)}"),
    decided_by: str = typer.Option("human", "--by", help="Kto podjął decyzję."),
    semester: Optional[int] = typer.Option(None, "--semester", "-s", help="Semestr (wymagane dla classify)."),
    subject_key: Optional[str] = typer.Option(None, "--subject", "-k", help="Skrót przedmiotu (wymagane dla classify)."),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Ścieżka docelowa."),
    action: Optional[str] = typer.Option(None, "--action", "-a", help="copy/skip/quarantine/media"),
    note: Optional[str] = typer.Option(None, "--note", "-n"),
    db_path: Optional[Path] = DB_OPTION,
    no_export: bool = typer.Option(False, "--no-export", help="Nie aktualizuj JSONL."),
) -> None:
    """Zapisuje jedną ręczną decyzję."""
    conn = db.connect(_require_db(db_path))
    try:
        result = record_decision(
            conn,
            sha256=sha256,
            decision_type=decision_type,
            decided_by=decided_by,
            semester=semester,
            subject_key=subject_key,
            category=category,
            target_relative_path=target,
            action=action,
            note=note,
        )
        conn.commit()
        typer.echo(f"zapisano: {result['sha256'][:16]}… ({result['decision_type']})")
        if not no_export:
            count = export(conn)
            typer.echo(f"eksport: {count} decyzji")
    except GroundTruthConflict as exc:
        typer.echo(f"odmowa: {exc}", err=True)
        raise typer.Exit(code=2)
    except (ValueError, KeyError) as exc:
        typer.echo(f"błąd: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()


@app.command("batch")
def cmd_batch(
    input_file: Path = typer.Argument(..., help="Plik JSONL z decyzjami."),
    decided_by: str = typer.Option("human", "--by"),
    db_path: Optional[Path] = DB_OPTION,
    no_export: bool = typer.Option(False, "--no-export"),
) -> None:
    """Zapisuje partię decyzji z pliku JSONL (atomowo)."""
    if not input_file.exists():
        typer.echo(f"brak pliku: {input_file}", err=True)
        raise typer.Exit(code=1)

    decisions = []
    for line in input_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            decisions.append(json.loads(line))

    if not decisions:
        typer.echo("plik pusty, nic do zapisania")
        return

    conn = db.connect(_require_db(db_path))
    try:
        results = record_batch(conn, decisions, decided_by=decided_by)
        typer.echo(f"zapisano {len(results)} decyzji")
        if not no_export:
            count = export(conn)
            typer.echo(f"eksport: {count} decyzji")
    except GroundTruthConflict as exc:
        typer.echo(f"odmowa (cała partia wycofana): {exc}", err=True)
        raise typer.Exit(code=2)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        typer.echo(f"błąd: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()


@app.command("undo")
def cmd_undo(
    db_path: Optional[Path] = DB_OPTION,
    no_export: bool = typer.Option(False, "--no-export"),
) -> None:
    """Cofa ostatnią decyzję (najnowsza wg decided_at)."""
    conn = db.connect(_require_db(db_path))
    try:
        undone = undo_last(conn)
        if undone is None:
            typer.echo("brak decyzji do cofnięcia")
            return
        typer.echo(f"cofnięto: {undone['sha256'][:16]}… ({undone['decision_type']})")
        if not no_export:
            count = export(conn)
            typer.echo(f"eksport: {count} decyzji")
    finally:
        conn.close()


@app.command("list")
def cmd_list(
    db_path: Optional[Path] = DB_OPTION,
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Wyświetla ostatnie decyzje."""
    conn = db.connect(_require_db(db_path), init=False)
    try:
        rows = conn.execute(
            "SELECT * FROM manual_decisions ORDER BY decided_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            typer.echo("brak decyzji")
            return
        for row in rows:
            sha = str(row["sha256"])[:16]
            typer.echo(
                f"  {row['decided_at']}  {sha}…  {row['decision_type']:12s}  "
                f"{row['decided_by']}  {row['note'] or ''}"
            )
        typer.echo(f"\n{len(rows)} decyzji (z {limit} ostatnich)")
    finally:
        conn.close()


if __name__ == "__main__":
    app()
