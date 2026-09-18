"""CLI administracyjne bazy organizera: init / reset / stats / eksport decyzji / refresh-kinds.

Uruchamianie: ``python scripts/db_admin.py <komenda>`` (katalog scripts/ trafia
wtedy na sys.path, więc ``from orglib import ...`` działa bez instalacji pakietu).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db, kinds

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



@app.command("refresh-kinds")
def refresh_kinds(
    db_path: Optional[Path] = DB_OPTION,
    apply_changes: bool = typer.Option(
        False, "--apply", help="Zapisz zmiany; bez tej flagi tylko raport (dry-run)."
    ),
) -> None:
    """Przelicza ``content.content_kind`` z rozszerzeń wg aktualnej mapy ``orglib.kinds``.

    ``content_kind`` zapisuje etap hash, więc rozszerzenie dopisane później do mapy
    (np. ``.jfif`` jako obraz, ``.ppsx`` jako prezentacja) nie zmienia samo z siebie
    treści już zindeksowanych. Ta komenda domyka różnicę bez ponownego hashowania.
    Reguła wyboru jest ta sama co w ``hash_files.py``: dla treści widzianej
    pod kilkoma rozszerzeniami wygrywa plik o najniższym ``file_id``.
    """
    path = _require_db(db_path)
    conn = db.connect(path, init=False)
    try:
        current = {
            str(row["sha256"]): str(row["content_kind"] or kinds.DEFAULT_KIND)
            for row in conn.execute("SELECT sha256, content_kind FROM content")
        }
        expected: dict[str, str] = {}
        for row in conn.execute(
            # Kolejność MUSI być ta sama co w hash_files.py, gdzie o rodzaju
            # decyduje `ON CONFLICT DO NOTHING` przy wstawianiu w porządku
            # file_id. Sortowanie po ścieżce dawało inny wynik dla treści
            # widzianej pod kilkoma rozszerzeniami — cicha niespójność między
            # etapem hash a tą komendą.
            "SELECT sha256, extension FROM files WHERE sha256 IS NOT NULL "
            "ORDER BY file_id"
        ):
            sha = str(row["sha256"])
            if sha in expected:
                continue
            expected[sha] = kinds.content_kind_for(row["extension"])
        changes = [
            (sha, current[sha], kind)
            for sha, kind in expected.items()
            if sha in current and current[sha] != kind
        ]
        summary: dict[tuple[str, str], int] = {}
        for _, was, becomes in changes:
            summary[(was, becomes)] = summary.get((was, becomes), 0) + 1
        for (was, becomes), count in sorted(summary.items(), key=lambda item: -item[1]):
            typer.echo(f"  {was} -> {becomes}: {count}")
        typer.echo(f"treści do zmiany: {len(changes)}")
        if not apply_changes:
            typer.echo("dry-run — użyj --apply, żeby zapisać")
            return
        with conn:
            conn.executemany(
                "UPDATE content SET content_kind = ? WHERE sha256 = ?",
                [(kind, sha) for sha, _, kind in changes],
            )
        typer.echo(f"zapisane: {len(changes)}")
    except sqlite3.Error as exc:
        typer.echo(f"błąd bazy danych: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()


if __name__ == "__main__":
    app()
