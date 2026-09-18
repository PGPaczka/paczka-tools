"""B2: ekstrakcja głowy tekstu z kolejki (status 'hashed' -> 'extracted').

Dla każdego pliku czekającego na etap 'extract' czyta treść zgodnie z jej
``content.content_kind`` (:mod:`orglib.textextract`), zapisuje głowę tekstu do
``20_WORK/extracted_text/{sha256}.txt`` i wypełnia podpisy podobieństwa:
``files.normalized_text_hash``, ``files.simhash``, ``files.perceptual_hash``
oraz ``content.extracted_text_path`` i ``content.ocr_done``.

Praca jest liczona RAZ NA TREŚĆ: druga kopia tego samego sha256 (a także ponowny
przebieg) bierze gotowy plik tekstowy z dysku zamiast otwierać dokument jeszcze
raz. Poddrzewa katalogów oznaczonych ``folders.duplicate_of`` w ogóle tu nie
trafiają — odsiewa je ``db.files_pending``.

Brak tekstu nie jest błędem: archiwum, wideo, obraz bez OCR i ``.doc``/``.rtf``
przechodzą na status 'extracted' z pustym wynikiem (metoda ``unsupported``).
Na status 'error' idą wyłącznie realne awarie odczytu i wpisy ze ścieżką
wychodzącą poza katalog źródeł.

Źródła pozostają read-only — skrypt wyłącznie je czyta, a zapisuje do ``work``.

Uruchamianie: ``python scripts/extract_text.py [opcje]`` albo ``just extract``.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db, kinds, textextract

app = typer.Typer(add_completion=False, help="Ekstrahuje tekst w kolejce 'hashed' -> 'extracted'.")

DB_OPTION = typer.Option(None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml).")


@dataclass(frozen=True)
class _Signatures:
    """Wynik pracy nad JEDNĄ treścią — wspólny dla wszystkich jej kopii."""

    stored_text_path: str | None
    ocr_done: bool
    normalized_text_hash: str | None
    simhash: str | None
    perceptual_hash: str | None
    method: str


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


def _check_text_dir(text_dir: Path, paths: config.Paths) -> None:
    """Nie pozwala pisać wyników do drzew materiałów (źródła, repo docelowe, media)."""
    candidate = Path(os.path.abspath(text_dir))
    for protected in (paths.sources, paths.target_repo, paths.media):
        if candidate.is_relative_to(Path(os.path.abspath(protected))):
            raise ValueError(f"zapis tekstu w chronionym drzewie jest zabroniony: {text_dir}")


def _store_path(text_path: Path, work_root: Path) -> str:
    """Ścieżka zapisywana w bazie: względem ``work`` (przenośna) albo absolutna."""
    absolute = Path(os.path.abspath(text_path))
    root = Path(os.path.abspath(work_root))
    if absolute.is_relative_to(root):
        return absolute.relative_to(root).as_posix()
    return absolute.as_posix()


def _load_path(stored: str, work_root: Path) -> Path:
    """Odwrotność :func:`_store_path` — z wpisu w bazie robi ścieżkę na dysku."""
    path = Path(stored)
    return path if path.is_absolute() else Path(work_root) / path


def _write_text_atomic(text: str, text_path: Path) -> None:
    """Zapisuje głowę tekstu atomowo (tmp + ``os.replace``), żeby przerwanie nie zostawiło połówki."""
    text_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=text_path.parent,
            prefix=f".{text_path.stem}-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, text_path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _content_rows(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Mapa sha256 -> wiersz ``content`` (content_kind, dotychczasowa ekstrakcja)."""
    return {
        str(row["sha256"]): row
        for row in conn.execute(
            "SELECT sha256, content_kind, extracted_text_path, ocr_done FROM content"
        )
    }


def _error_file_ids(conn: sqlite3.Connection, package: Optional[str]) -> list[int]:
    """Zwraca file_id plików obecnie w statusie 'error' (opcjonalnie tylko z jednej paczki)."""
    sql = "SELECT file_id FROM files WHERE status = 'error'"
    params: list[str] = []
    if package is not None:
        sql += " AND source_package = ?"
        params.append(package)
    return [int(row["file_id"]) for row in conn.execute(sql, params)]


def _signatures_from_text(
    text: str,
    *,
    stored_text_path: str | None,
    ocr_done: bool,
    perceptual: str | None,
    method: str,
) -> _Signatures:
    """Liczy podpisy tekstowe (normalized_text_hash, simhash) z gotowej głowy tekstu."""
    return _Signatures(
        stored_text_path=stored_text_path,
        ocr_done=ocr_done,
        normalized_text_hash=textextract.normalized_text_hash(text),
        simhash=textextract.simhash(text),
        perceptual_hash=perceptual,
        method=method,
    )


def _report_progress(done: int, total: int, contents: int, started_at: float) -> None:
    """Drukuje postęp partii na stderr."""
    elapsed = time.monotonic() - started_at
    typer.echo(
        f"extract: {done}/{total} plików, {contents} treści, upłynęło {elapsed:.1f}s",
        err=True,
    )


def _flush_batch(
    conn: sqlite3.Connection,
    successes: list[tuple[int, str, _Signatures]],
    errors: list[tuple[int, str]],
) -> None:
    """Zapisuje jedną partię wyników (content + files + błędy) w pojedynczej transakcji."""
    if not successes and not errors:
        return
    with conn:
        for file_id, sha256, signatures in successes:
            conn.execute(
                "UPDATE content SET extracted_text_path = ?, ocr_done = ? WHERE sha256 = ?",
                (signatures.stored_text_path, int(signatures.ocr_done), sha256),
            )
            conn.execute(
                "UPDATE files SET normalized_text_hash = ?, simhash = ?, perceptual_hash = ?, "
                "status = 'extracted', error_message = NULL WHERE file_id = ?",
                (
                    signatures.normalized_text_hash,
                    signatures.simhash,
                    signatures.perceptual_hash,
                    file_id,
                ),
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
    text_dir: Optional[Path] = typer.Option(
        None, "--text-dir", help="Katalog na teksty (domyślnie work/extracted_text)."
    ),
    package: Optional[str] = typer.Option(
        None, "--package", help="Ogranicz do jednej paczki źródłowej (source_package)."
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Przetwórz co najwyżej N plików."),
    batch: int = typer.Option(50, "--batch", help="Ile plików zapisywać w jednej transakcji."),
    max_chars: int = typer.Option(
        textextract.DEFAULT_MAX_CHARS, "--max-chars", help="Limit długości zapisanej głowy tekstu."
    ),
    max_pages: int = typer.Option(
        textextract.DEFAULT_MAX_PAGES, "--max-pages", help="Ile stron PDF czytać."
    ),
    ocr: bool = typer.Option(
        True, "--ocr/--no-ocr", help="OCR awaryjny dla PDF bez warstwy tekstowej."
    ),
    ocr_images: bool = typer.Option(
        False, "--ocr-images", help="Dodatkowo OCR samodzielnych obrazów (wolne)."
    ),
    ocr_lang: str = typer.Option(
        textextract.DEFAULT_OCR_LANG, "--ocr-lang", help="Języki tesseractu."
    ),
    ocr_pages: int = typer.Option(
        textextract.DEFAULT_OCR_MAX_PAGES, "--ocr-pages", help="Ile stron PDF poddać OCR."
    ),
    force: bool = typer.Option(
        False, "--force", help="Przeekstrahuj treść, nawet jeśli tekst jest już na dysku."
    ),
    retry_errors: bool = typer.Option(
        False, "--retry-errors", help="Zresetuj pliki w statusie 'error' na 'hashed' przed pracą."
    ),
) -> None:
    """Ekstrahuje głowę tekstu i podpisy dla plików w statusie 'hashed'."""
    if batch < 1:
        typer.echo("--batch musi być >= 1", err=True)
        raise typer.Exit(code=2)
    if max_chars < 1 or max_pages < 1 or ocr_pages < 1:
        typer.echo("--max-chars, --max-pages i --ocr-pages muszą być >= 1", err=True)
        raise typer.Exit(code=2)

    path = _require_db(db_path)
    paths = config.load_paths()
    sources_root = Path(sources) if sources is not None else paths.sources
    texts_root = Path(text_dir) if text_dir is not None else paths.work_extracted_text
    try:
        _check_text_dir(texts_root, paths)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    work_root = paths.work

    conn = db.connect(path, init=False)
    started_at = time.monotonic()

    extracted_count = 0
    with_text_count = 0
    ocr_count = 0
    no_text_count = 0
    error_count = 0
    reused_count = 0
    done_contents: dict[str, _Signatures] = {}
    methods: Counter[str] = Counter()
    successes: list[tuple[int, str, _Signatures]] = []
    errors: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal successes, errors
        _flush_batch(conn, successes, errors)
        successes = []
        errors = []

    def signatures_for(sha256: str, content_row: sqlite3.Row | None, source: Path) -> _Signatures:
        """Zwraca podpisy treści, licząc ekstrakcję najwyżej raz na sha256."""
        nonlocal with_text_count, ocr_count, no_text_count, reused_count
        cached = done_contents.get(sha256)
        if cached is not None:
            return cached

        kind = str(
            (content_row["content_kind"] if content_row is not None else None)
            or kinds.DEFAULT_KIND
        )
        perceptual = textextract.perceptual_hash(source) if kind == "image" else None

        stored = str(content_row["extracted_text_path"]) if (
            content_row is not None and content_row["extracted_text_path"]
        ) else None
        if stored and not force:
            existing = _load_path(stored, work_root)
            if existing.is_file():
                text = existing.read_text(encoding="utf-8", errors="replace")
                reused_count += 1
                with_text_count += 1
                result = _signatures_from_text(
                    text,
                    stored_text_path=stored,
                    ocr_done=bool(content_row["ocr_done"]) if content_row is not None else False,
                    perceptual=perceptual,
                    method="reused",
                )
                methods[result.method] += 1
                done_contents[sha256] = result
                return result

        extraction = textextract.extract(
            source,
            kind,
            max_chars=max_chars,
            max_pages=max_pages,
            ocr=ocr,
            ocr_images=ocr_images,
            ocr_lang=ocr_lang,
            ocr_max_pages=ocr_pages,
        )
        if extraction.ocr_done:
            ocr_count += 1
        if extraction.has_text:
            text_path = texts_root / f"{sha256}.txt"
            _write_text_atomic(extraction.text, text_path)
            stored_text_path: str | None = _store_path(text_path, work_root)
            with_text_count += 1
        else:
            stored_text_path = None
            no_text_count += 1
        result = _signatures_from_text(
            extraction.text,
            stored_text_path=stored_text_path,
            ocr_done=extraction.ocr_done,
            perceptual=perceptual,
            method=extraction.method,
        )
        methods[result.method] += 1
        done_contents[sha256] = result
        return result

    try:
        stuck_error_ids = _error_file_ids(conn, package)
        previous_errors_count = len(stuck_error_ids)
        if retry_errors:
            for file_id in stuck_error_ids:
                db.reset_error(conn, file_id, "hashed")

        contents = _content_rows(conn)
        rows = db.files_pending(conn, "extract", source_package=package, limit=limit)
        total = len(rows)

        for done, row in enumerate(rows, start=1):
            try:
                sha256 = row["sha256"]
                resolved = config.resolve_within_sources(
                    sources_root, row["source_package"], row["source_relative_path"]
                )
                if not sha256:
                    errors.append((row["file_id"], "brak sha256 — najpierw hash_files.py"))
                    error_count += 1
                elif resolved is None:
                    errors.append((row["file_id"], "ścieżka poza katalogiem źródeł"))
                    error_count += 1
                else:
                    try:
                        signatures = signatures_for(str(sha256), contents.get(str(sha256)), resolved)
                    except (textextract.ExtractionError, OSError) as exc:
                        errors.append((row["file_id"], f"{type(exc).__name__}: {exc}"))
                        error_count += 1
                    else:
                        successes.append((row["file_id"], str(sha256), signatures))
                        extracted_count += 1
            except KeyboardInterrupt:
                _flush_batch(conn, successes, errors)
                elapsed = time.monotonic() - started_at
                typer.echo(
                    f"przerwano: wyekstrahowane={extracted_count} błędy={error_count} "
                    f"treści={len(done_contents)} czas={elapsed:.1f}s",
                    err=True,
                )
                raise typer.Exit(code=130)
            except Exception:
                # Partia zebrana do tej pory trafia do bazy, dopiero potem wyjątek
                # leci dalej — przerwany przebieg nie gubi zrobionej pracy.
                _flush_batch(conn, successes, errors)
                raise

            if done % batch == 0:
                flush()
                _report_progress(done, total, len(done_contents), started_at)

        flush()
        if total and total % batch != 0:
            _report_progress(total, total, len(done_contents), started_at)
    except sqlite3.Error as exc:
        typer.echo(f"błąd bazy danych: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()

    elapsed = time.monotonic() - started_at
    typer.echo(f"wyekstrahowane pliki: {extracted_count}")
    typer.echo(f"przerobione treści: {len(done_contents)} (w tym gotowe z dysku: {reused_count})")
    typer.echo(f"treści z tekstem: {with_text_count}")
    typer.echo(f"treści bez tekstu: {no_text_count}")
    typer.echo(f"OCR: {ocr_count}")
    if methods:
        typer.echo("metody: " + ", ".join(f"{name}={count}" for name, count in sorted(methods.items())))
    typer.echo(f"błędy: {error_count}")
    typer.echo(f"czas: {elapsed:.1f}s")
    typer.echo(f"wcześniejsze błędy: {previous_errors_count} — użyj --retry-errors")


if __name__ == "__main__":
    app()
