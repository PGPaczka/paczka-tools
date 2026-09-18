"""Kontrola STANU, nie kodu: spójność indeksu i niezmienność źródeł.

Testy pilnują kodu; ten skrypt pilnuje dwóch rzeczy, których nie da się odtworzyć
tanio: operacyjnego indeksu (budowanego przyrostowo przez wiele przebiegów) i
katalogu źródeł, który ma pozostać nietknięty (reguła twarda nr 1).

    python scripts/doctor.py index      # albo: just index-check
    python scripts/doctor.py sources    # albo: just sources-check
    python scripts/doctor.py all

Kody wyjścia: 0 = czysto (albo same obserwacje ``info``), 1 = znalezione błędy
albo ostrzeżenia, 2 = nie dało się wykonać kontroli (brak bazy, brak źródeł).
Nic nie zapisuje — otwiera bazę w trybie tylko do odczytu.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import typer

from orglib import config, integrity

app = typer.Typer(add_completion=False, help=__doc__)

DB_OPTION = typer.Option(None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml).")


def _open_readonly(database: Path) -> sqlite3.Connection:
    """Otwiera indeks w trybie ro — kontrola nie ma prawa niczego zmienić."""
    if not database.is_file():
        typer.echo(f"brak bazy: {database} — uruchom najpierw first-pass", err=True)
        raise typer.Exit(code=2)
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _report(title: str, findings: list[integrity.Finding]) -> int:
    """Drukuje znaleziska; zwraca 1, gdy jest cokolwiek poważniejszego niż info."""
    typer.echo(f"== {title} ==")
    if not findings:
        typer.echo("  czysto")
        return 0
    for finding in findings:
        typer.echo(f"  {finding}")
    worst = integrity.worst_severity(findings)
    return 1 if worst in ("error", "warning") else 0


@app.command("index")
def check_index(db_path: Optional[Path] = DB_OPTION) -> None:
    """Więzy operacyjnego indeksu, których schemat SQLite nie potrafi wyrazić."""
    paths = config.load_paths()
    conn = _open_readonly(db_path if db_path is not None else paths.work_db)
    try:
        findings = integrity.index_findings(conn, work_root=paths.work)
    finally:
        conn.close()
    raise typer.Exit(code=_report("spójność indeksu", findings))


@app.command("sources")
def check_sources(
    db_path: Optional[Path] = DB_OPTION,
    sources: Optional[Path] = typer.Option(
        None, "--sources", help="Korzeń źródeł (domyślnie z config/paths.yaml)."
    ),
) -> None:
    """Czy źródła są nadal takie, jakie zapisał skan (reguła twarda nr 1)."""
    paths = config.load_paths()
    root = sources if sources is not None else paths.sources
    if not Path(root).is_dir():
        typer.echo(f"brak katalogu źródeł: {root}", err=True)
        raise typer.Exit(code=2)
    conn = _open_readonly(db_path if db_path is not None else paths.work_db)
    try:
        findings = integrity.sources_findings(conn, Path(root))
    finally:
        conn.close()
    raise typer.Exit(code=_report("niezmienność źródeł", findings))


@app.command("all")
def check_all(db_path: Optional[Path] = DB_OPTION) -> None:
    """Obie kontrole naraz; kod wyjścia jest gorszym z dwóch wyników."""
    paths = config.load_paths()
    database = db_path if db_path is not None else paths.work_db
    conn = _open_readonly(database)
    try:
        index = integrity.index_findings(conn, work_root=paths.work)
        sources = (
            integrity.sources_findings(conn, paths.sources)
            if paths.sources.is_dir()
            else [integrity.Finding(
                "brak_zrodel", f"katalog źródeł nie istnieje: {paths.sources}", 1, severity="info"
            )]
        )
    finally:
        conn.close()
    code = max(_report("spójność indeksu", index), _report("niezmienność źródeł", sources))
    raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
