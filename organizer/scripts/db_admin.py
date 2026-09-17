"""CLI administracyjne bazy organizera: init / reset / stats / eksport decyzji.

Uruchamianie: ``python scripts/db_admin.py <komenda>`` (katalog scripts/ trafia
wtedy na sys.path, więc ``from orglib import ...`` działa bez instalacji pakietu).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db

app = typer.Typer(add_completion=False, help="Administracja bazą 20_WORK/organizer.sqlite.")

DB_OPTION = typer.Option(None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml).")


def _db_path(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę bazy: z opcji --db albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().work_db


def _schema_version(conn: sqlite3.Connection) -> Optional[int]:
    """Odczytuje najwyższą zapisaną wersję schematu."""
    return db.current_schema_version(conn)


def _require_db(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę istniejącej bazy albo kończy z kodem 1 (nie zakłada pustego pliku)."""
    path = _db_path(explicit)
    if not path.exists():
        typer.echo(f"brak bazy: {path} — uruchom najpierw 'db_admin.py init'.", err=True)
        raise typer.Exit(code=1)
    return path


def _require_file(path: Path, what: str) -> Path:
    """Zwraca ścieżkę istniejącego pliku albo kończy z kodem 1."""
    if not path.exists():
        typer.echo(f"brak pliku {what}: {path}", err=True)
        raise typer.Exit(code=1)
    return path


@app.command("init")
def init(db_path: Optional[Path] = DB_OPTION) -> None:
    """Tworzy lub aktualizuje schemat bazy."""
    path = _db_path(db_path)
    try:
        conn = db.connect(path)
    except sqlite3.DatabaseError as exc:
        typer.echo(f"{path}: to nie jest poprawna baza SQLite ({exc})", err=True)
        raise typer.Exit(code=1)
    try:
        typer.echo(f"baza: {path}")
        typer.echo(f"schema_version: {_schema_version(conn)}")
    finally:
        conn.close()


@app.command("reset")
def reset(
    db_path: Optional[Path] = DB_OPTION,
    yes: bool = typer.Option(False, "--yes", help="Wymagane potwierdzenie — bez niego odmawiam."),
) -> None:
    """Odkłada obecną bazę jako kopię .bak-<timestamp> i zakłada nową (nic nie kasuje)."""
    path = _db_path(db_path)
    if not yes:
        typer.echo("reset wymaga --yes; nic nie zrobiłem.", err=True)
        raise typer.Exit(code=2)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{path}{suffix}")
        if source.exists():
            backup = Path(f"{path}.bak-{stamp}{suffix}")
            source.rename(backup)
            typer.echo(f"odłożone: {backup}")

    conn = db.connect(path)
    try:
        typer.echo(f"nowa baza: {path}")
        typer.echo(f"schema_version: {_schema_version(conn)}")
    finally:
        conn.close()


@app.command("stats")
def stats(db_path: Optional[Path] = DB_OPTION) -> None:
    """Drukuje liczności tabel i liczności statusów plików."""
    path = _require_db(db_path)
    conn = db.connect(path, init=False)
    try:
        typer.echo(f"baza: {path}")
        typer.echo("tabele:")
        for table, count in db.table_counts(conn).items():
            typer.echo(f"  {table:<20} {count:>8}")
        typer.echo("statusy plików:")
        for status, count in db.file_status_counts(conn).items():
            typer.echo(f"  {status:<20} {count:>8}")
    finally:
        conn.close()


@app.command("export-manual")
def export_manual(
    db_path: Optional[Path] = DB_OPTION,
    out: Optional[Path] = typer.Option(None, "--out", help="Plik JSONL (domyślnie reports/)."),
) -> None:
    """Eksportuje ręczne decyzje do JSONL (muszą przeżyć przebudowę bazy)."""
    target = out if out is not None else config.ORGANIZER_ROOT / "reports" / "manual_decisions.jsonl"
    conn = db.connect(_require_db(db_path), init=False)
    try:
        count = db.export_manual_decisions(conn, Path(target))
    finally:
        conn.close()
    typer.echo(f"zapisane decyzje: {count} -> {target}")


@app.command("import-manual")
def import_manual(
    db_path: Optional[Path] = DB_OPTION,
    src: Optional[Path] = typer.Option(None, "--in", help="Plik JSONL (domyślnie reports/)."),
) -> None:
    """Wczytuje ręczne decyzje z JSONL do bazy (UPSERT po sha256)."""
    source = src if src is not None else config.ORGANIZER_ROOT / "reports" / "manual_decisions.jsonl"
    path = _require_db(db_path)
    _require_file(Path(source), "z decyzjami")
    conn = db.connect(path)
    try:
        count = db.import_manual_decisions(conn, Path(source))
    finally:
        conn.close()
    typer.echo(f"wczytane decyzje: {count} <- {source}")


if __name__ == "__main__":
    app()
