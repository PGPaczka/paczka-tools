"""B1: wycinek manifestu jednego przedmiotu z indeksu SQLite, bez skanu źródeł.

Materiałów nie otwiera. Jedyne pliki czytane z dysku to głowy tekstu zapisane
wcześniej przez etap extract (B2) w ``work`` — trafiają do pola ``text_head``,
żeby klasyfikacja AI (B5) widziała treść, a nie samą nazwę pliku.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional, Sequence

import typer

from orglib import config, db
from orglib.llm_client import truncate_head
from orglib.subject_manifest import build_manifest

app = typer.Typer(add_completion=False, help=__doc__)


def _text_head_limit() -> int:
    """Ile bajtów głowy tekstu wchodzi do manifestu (ten sam próg, co wsad do modelu)."""
    llm = config.load_thresholds().get("llm") or {}
    return int(llm.get("max_text_head_bytes", 2048))


def _text_heads(
    conn: sqlite3.Connection, wanted: set[str], paths: config.Paths, limit: int
) -> dict[str, str]:
    """Głowy tekstu z etapu extract (B2) dla treści obecnych w manifeście.

    Czyta wyłącznie pliki wyprodukowane przez ``extract_text.py`` w ``work``.
    Wpis wskazujący drzewo materiałów (źródła, repo docelowe, media) jest
    pomijany — manifest nie jest ścieżką do czytania materiałów bokiem.
    Brak pliku, brak ekstrakcji i pusty tekst dają po prostu brak klucza.
    """
    if not wanted or limit < 1:
        return {}
    protected = [Path(os.path.abspath(p)) for p in (paths.sources, paths.target_repo, paths.media)]
    heads: dict[str, str] = {}
    for row in conn.execute(
        "SELECT sha256, extracted_text_path FROM content WHERE extracted_text_path IS NOT NULL"
    ):
        sha = str(row["sha256"])
        if sha not in wanted:
            continue
        path = Path(str(row["extracted_text_path"]))
        if not path.is_absolute():
            path = paths.work / path
        absolute = Path(os.path.abspath(path))
        if any(absolute.is_relative_to(root) for root in protected):
            continue
        try:
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        head = truncate_head(text, limit).strip()
        if head:
            heads[sha] = head
    return heads


def default_output(subject: config.Subject, subjects: Sequence[config.Subject]) -> Path:
    """Nie nadpisuj raportu innego semestru/grupy o tym samym skrócie."""
    root = config.ORGANIZER_ROOT / "reports"
    if sum(s.skrot.casefold() == subject.skrot.casefold() for s in subjects) > 1:
        root = root / f"SEM{subject.semester}" / subject.grupa
    return root / subject.skrot / "manifest_slice.jsonl"


def _check_output(output: Path, database: Path, paths: config.Paths) -> None:
    resolved = output.resolve()
    for protected in (paths.sources, paths.target_repo, paths.media):
        if resolved.is_relative_to(protected.resolve()) or Path(
            os.path.abspath(output)
        ).is_relative_to(Path(os.path.abspath(protected))):
            raise ValueError(f"zapis raportu w chronionym drzewie jest zabroniony: {output}")
        # SQLite mode=ro może potrzebować plików pomocniczych WAL/SHM.
        # Baza operacyjna nie może z tego powodu leżeć w drzewie materiałów.
        if database.resolve().is_relative_to(protected.resolve()) or Path(
            os.path.abspath(database)
        ).is_relative_to(Path(os.path.abspath(protected))):
            raise ValueError(f"baza w chronionym drzewie jest zabroniona: {database}")
    if resolved == database.resolve() or (
        output.exists() and database.exists() and output.samefile(database)
    ):
        raise ValueError("manifest nie może nadpisać bazy danych")
    if output.is_symlink():
        raise ValueError(f"plik wyjściowy nie może być symlinkiem: {output}")


def _write_atomic(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=".manifest-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@app.command()
def prepare(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Dokładny katalog wyjściowy manifest_slice.jsonl."
    ),
) -> None:
    """Przygotuj kandydatów; nie klasyfikuj, nie zmieniaj statusów ani materiałów."""
    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")
        output = (
            out_dir / "manifest_slice.jsonl"
            if out_dir is not None else default_output(subject, subjects)
        )
        _check_output(output, database, paths)
        # db.connect ustawia WAL i może tworzyć bazę. Ten etap ma tylko czytać.
        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            version = db.current_schema_version(conn)
            if version != db.SCHEMA_VERSION:
                raise ValueError(
                    f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}"
                )
            rows = build_manifest(conn, subject, subjects)
            heads = _text_heads(
                conn, {str(row["sha256"]) for row in rows}, paths, _text_head_limit()
            )
        finally:
            conn.close()
        for row in rows:
            head = heads.get(str(row["sha256"]))
            if head:
                row["text_head"] = head
        _write_atomic(rows, output)
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd przygotowania manifestu: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"manifest: {output}")
    typer.echo(
        f"przedmiot: SEM{subject.semester}/{subject.grupa}/{subject.skrot} · "
        f"treści: {len(rows)} · review: {sum(r['needs_review'] for r in rows)}"
    )


if __name__ == "__main__":
    app()
