"""Hashuje pliki oczekujące w kolejce (status 'discovered' -> 'hashed').

Dla każdego pliku liczy sha256, wypełnia ``content.content_kind`` (pierwsze
napotkane rozszerzenie dla danej treści wygrywa — patrz :mod:`orglib.kinds`) i
przestawia plik na status 'hashed'. Błąd odczytu pliku (np. brakujący plik w
źródle) albo ścieżka wychodząca poza katalog źródeł przestawia go na status
'error' i nie przerywa reszty przebiegu.

Wznawialne: zapis do bazy dzieje się partiami (``--batch``), więc przerwanie
w trakcie traci co najwyżej jedną niedokończoną partię (partia w toku jest
zapisywana przed przerwaniem, także przy nieoczekiwanym wyjątku) — ponowne
uruchomienie podejmuje pozostałe pliki w statusie 'discovered'.

Uruchamianie: ``python scripts/hash_files.py [opcje]`` (katalog scripts/ trafia
wtedy na sys.path, więc ``from orglib import ...`` działa bez instalacji pakietu).
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db, hashes, kinds

app = typer.Typer(add_completion=False, help="Hashuje pliki w kolejce 'discovered' -> 'hashed'.")

DB_OPTION = typer.Option(None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml).")


def _db_path(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę bazy: z opcji --db albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().work_db


def _require_db(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę istniejącej bazy albo kończy z kodem 1 (nie zakłada pustego pliku)."""
    path = _db_path(explicit)
    if not path.exists():
        typer.echo(f"brak bazy: {path} — uruchom najpierw 'db_admin.py init'.", err=True)
        raise typer.Exit(code=1)
    return path


def _sources_root(explicit: Optional[Path]) -> Path:
    """Zwraca korzeń źródeł: z opcji --sources albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().sources


def _resolve_within_sources(
    sources_root: Path, source_package: str, source_relative_path: str
) -> Optional[Path]:
    """Wylicza ścieżkę pliku w źródłach, pilnując, że nie wychodzi poza ``sources_root``.

    Zwraca ``None``, gdy ``source_relative_path`` jest bezwzględna albo po
    normalizacji (bez rozwijania dowiązań — patrz ``orglib.config._absolutize``)
    ścieżka ląduje poza ``sources_root``, np. przez ``..``. Taki wpis w bazie
    to błąd danych, nie próba odczytu — plik idzie do statusu 'error'.
    """
    if Path(source_relative_path).is_absolute():
        return None
    candidate = sources_root / source_package / source_relative_path
    normalized = Path(os.path.normpath(candidate))
    root_normalized = Path(os.path.normpath(sources_root))
    if not normalized.is_relative_to(root_normalized):
        return None
    return normalized


def _error_file_ids(conn: sqlite3.Connection, package: Optional[str]) -> list[int]:
    """Zwraca file_id plików obecnie w statusie 'error' (opcjonalnie tylko z jednej paczki)."""
    sql = "SELECT file_id FROM files WHERE status = 'error'"
    params: list[str] = []
    if package is not None:
        sql += " AND source_package = ?"
        params.append(package)
    return [int(row["file_id"]) for row in conn.execute(sql, params)]


def _mb_per_s(bytes_done: int, elapsed: float) -> float:
    """Przepustowość w MB/s (0.0 zamiast dzielenia przez zero na starcie)."""
    if elapsed <= 0:
        return 0.0
    return (bytes_done / (1 << 20)) / elapsed


def _report_progress(done: int, total: int, bytes_done: int, started_at: float) -> None:
    """Drukuje postęp partii na stderr."""
    elapsed = time.monotonic() - started_at
    typer.echo(
        f"hash: {done}/{total} plików, {bytes_done / (1 << 20):.1f} MB, "
        f"{_mb_per_s(bytes_done, elapsed):.1f} MB/s, upłynęło {elapsed:.1f}s",
        err=True,
    )


def _flush_batch(
    conn: sqlite3.Connection,
    successes: list[tuple[int, str, str]],
    errors: list[tuple[int, str]],
) -> None:
    """Zapisuje jedną partię wyników (sukcesy + błędy) w pojedynczej transakcji.

    ``successes`` to (file_id, sha256, content_kind) w kolejności file_id —
    dzięki temu ``ON CONFLICT DO NOTHING`` przy INSERT do content jest
    deterministyczne: pierwsze napotkane rozszerzenie dla danej treści wygrywa.
    """
    if not successes and not errors:
        return
    with conn:
        for file_id, sha256, content_kind in successes:
            conn.execute(
                "INSERT INTO content (sha256, content_kind) VALUES (?, ?) "
                "ON CONFLICT (sha256) DO NOTHING",
                (sha256, content_kind),
            )
            conn.execute(
                "UPDATE files SET sha256 = ?, status = 'hashed', error_message = NULL "
                "WHERE file_id = ?",
                (sha256, file_id),
            )
        for file_id, message in errors:
            conn.execute(
                "UPDATE files SET status = 'error', error_message = ? WHERE file_id = ?",
                (message, file_id),
            )


@app.command()
def main(
    db_path: Optional[Path] = DB_OPTION,
    sources: Optional[Path] = typer.Option(
        None, "--sources", help="Korzeń źródeł (domyślnie z config/paths.yaml)."
    ),
    package: Optional[str] = typer.Option(
        None, "--package", help="Ogranicz do jednej paczki źródłowej (source_package)."
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Przetwórz co najwyżej N plików."),
    batch: int = typer.Option(200, "--batch", help="Ile plików zapisywać w jednej transakcji."),
    retry_errors: bool = typer.Option(
        False,
        "--retry-errors",
        help="Zresetuj pliki w statusie 'error' na 'discovered' przed hashowaniem.",
    ),
) -> None:
    """Liczy sha256 plików w statusie 'discovered' i przesuwa je na 'hashed'."""
    if batch < 1:
        typer.echo("--batch musi być >= 1", err=True)
        raise typer.Exit(code=2)

    path = _require_db(db_path)
    sources_root = _sources_root(sources)
    conn = db.connect(path, init=False)
    started_at = time.monotonic()

    hashed_count = 0
    error_count = 0
    bytes_done = 0
    unique_sha256: set[str] = set()
    successes: list[tuple[int, str, str]] = []
    errors: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal successes, errors
        _flush_batch(conn, successes, errors)
        successes = []
        errors = []

    try:
        stuck_error_ids = _error_file_ids(conn, package)
        previous_errors_count = len(stuck_error_ids)
        if retry_errors:
            for file_id in stuck_error_ids:
                db.reset_error(conn, file_id, "discovered")

        rows = db.files_pending(conn, "hash", source_package=package, limit=limit)
        total = len(rows)

        for done, row in enumerate(rows, start=1):
            try:
                resolved = _resolve_within_sources(
                    sources_root, row["source_package"], row["source_relative_path"]
                )
                if resolved is None:
                    errors.append((row["file_id"], "ścieżka poza katalogiem źródeł"))
                    error_count += 1
                else:
                    try:
                        sha256 = hashes.sha256_file(resolved)
                    except OSError as exc:
                        errors.append((row["file_id"], f"{type(exc).__name__}: {exc}"))
                        error_count += 1
                    else:
                        content_kind = kinds.content_kind_for(row["extension"])
                        successes.append((row["file_id"], sha256, content_kind))
                        hashed_count += 1
                        unique_sha256.add(sha256)
                        bytes_done += int(row["size_bytes"] or 0)
            except KeyboardInterrupt:
                _flush_batch(conn, successes, errors)
                elapsed = time.monotonic() - started_at
                typer.echo(
                    f"przerwano: zahashowane={hashed_count} błędy={error_count} "
                    f"bajty={bytes_done} unikalne_sha256={len(unique_sha256)} "
                    f"czas={elapsed:.1f}s",
                    err=True,
                )
                raise typer.Exit(code=130)
            except Exception:
                # Nieoczekiwany wyjątek: partia zebrana do tej pory i tak trafia
                # do bazy, dopiero potem wyjątek leci dalej (nic się nie gubi).
                _flush_batch(conn, successes, errors)
                raise

            if done % batch == 0:
                flush()
                _report_progress(done, total, bytes_done, started_at)

        flush()
        if total and total % batch != 0:
            _report_progress(total, total, bytes_done, started_at)
    except sqlite3.Error as exc:
        typer.echo(f"błąd bazy danych: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()

    elapsed = time.monotonic() - started_at
    typer.echo(f"zahashowane: {hashed_count}")
    typer.echo(f"błędy: {error_count}")
    typer.echo(f"bajty: {bytes_done}")
    typer.echo(f"unikalne sha256 w tym przebiegu: {len(unique_sha256)}")
    typer.echo(f"czas: {elapsed:.1f}s")
    typer.echo(f"wcześniejsze błędy: {previous_errors_count} — użyj --retry-errors")


if __name__ == "__main__":
    app()
