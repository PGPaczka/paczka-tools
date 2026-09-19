"""``python -m studio.api`` — launcher, którego wołają `just studio` i `just studio-dev`.

Kody wyjścia są częścią kontraktu (tak jak w `validate_plan`):
``2`` = odmowa startu (adres spoza pętli zwrotnej), ``1`` = błąd środowiska
(brak bazy, zła ``schema_version``), ``0`` = serwer wystartował albo `--check`
przeszedł.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .database import SchemaMismatch
from .server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    AddressRefused,
    ensure_loopback,
    preflight,
    serve,
)

cli = typer.Typer(add_completion=False, help=__doc__)


@cli.command()
def main(
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Wyłącznie adres pętli zwrotnej."),
    port: int = typer.Option(DEFAULT_PORT, "--port", help="Port nasłuchu."),
    reload: bool = typer.Option(False, "--reload", help="Przeładowanie po zmianie kodu (dev)."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    check: bool = typer.Option(
        False, "--check", help="Tylko preflight: adres i baza. Nie zajmuje portu."
    ),
    log_level: str = typer.Option("info", "--log-level", help="Poziom logów uvicorna."),
) -> None:
    """Uruchamia backend studia na loopbacku (faza S0: wyłącznie odczyt)."""
    try:
        address = ensure_loopback(host)
    except AddressRefused as exc:
        typer.echo(f"Odmowa startu: {exc}", err=True)
        raise typer.Exit(code=2)

    if check:
        try:
            database = db_path if db_path is not None else _default_db()
            version = preflight(database)
        except (SchemaMismatch, FileNotFoundError, KeyError, ValueError, OSError) as exc:
            typer.echo(f"Preflight nieudany: {exc}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"ok: {address}:{port} · baza {database} · schema_version={version}")
        return

    try:
        serve(host=host, port=port, reload=reload, db_path=db_path, log_level=log_level)
    except (SchemaMismatch, FileNotFoundError, KeyError, ValueError, OSError) as exc:
        typer.echo(f"Studio nie wystartowało: {exc}", err=True)
        raise typer.Exit(code=1)


def _default_db() -> Path:
    """Ścieżka bazy z ``config/paths.yaml`` — ten sam plik, który czyta cały potok."""
    from orglib import config

    return config.load_paths().work_db


if __name__ == "__main__":
    cli()
