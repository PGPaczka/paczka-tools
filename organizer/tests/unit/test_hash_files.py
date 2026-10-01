"""Testy `scripts/hash_files.py`: hashowanie kolejki 'discovered' -> 'hashed'.

Baza i katalog źródeł żyją wyłącznie w tmp_path — nic nie dotyka 00_SOURCES.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import hash_files
from orglib import db, hashes

runner = CliRunner()


@pytest.fixture()
def sources_root(tmp_path: Path) -> Path:
    """Katalog udający korzeń źródeł (odpowiednik 00_SOURCES) w tmp_path."""
    root = tmp_path / "sources"
    root.mkdir()
    return root


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "organizer.sqlite"
    conn = db.connect(path)
    conn.close()
    return path


def _seed_package(conn: sqlite3.Connection, package: str = "P1") -> None:
    db.upsert(conn, "source_packages", {"package_name": package}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": package, "source_package": package})


def _seed_file(
    conn: sqlite3.Connection,
    sources_root: Path,
    *,
    package: str = "P1",
    relpath: str = "a.pdf",
    content: bytes | None = b"hello",
    extension: str | None = None,
    folder_path: str | None = None,
) -> int:
    """Zapisuje plik na dysku (chyba że content=None) i wiersz w bazie; zwraca file_id.

    ``folder_path`` pozwala nadpisać wyliczony katalog — potrzebne przy testowaniu
    ścieżek bezwzględnych/``..``, dla których ``db.folder_path_for`` policzyłby
    katalog spoza zasianego drzewa ``folders`` (FK by tego nie przepuścił).
    """
    if content is not None:
        target = sources_root / package / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        size = len(content)
    else:
        size = 1

    ext = extension if extension is not None else (Path(relpath).suffix.lstrip(".") or None)
    row = {
        "source_package": package,
        "source_relative_path": relpath,
        "folder_path": folder_path or db.folder_path_for(package, relpath),
        "filename": Path(relpath).name,
        "extension": ext,
        "size_bytes": size,
    }
    db.upsert_file(conn, row)
    return int(
        conn.execute(
            "SELECT file_id FROM files WHERE source_package = ? AND source_relative_path = ?",
            (package, relpath),
        ).fetchone()["file_id"]
    )


def _run(db_path: Path, sources_root: Path, *extra: str):
    return runner.invoke(
        hash_files.app,
        ["--db", str(db_path), "--sources", str(sources_root), *extra],
    )


# --- podstawowe hashowanie -----------------------------------------------------


@pytest.mark.parametrize("batch", [0, -1])
def test_cli_rejects_nonpositive_batch(
    db_path: Path, sources_root: Path, batch: int
) -> None:
    """Niepoprawny rozmiar partii ma kończyć się kodem 2 przed hashowaniem pliku."""
    conn = db.connect(db_path, init=False)
    try:
        _seed_package(conn)
        _seed_file(conn, sources_root)
    finally:
        conn.close()

    result = _run(db_path, sources_root, "--batch", str(batch))

    assert result.exit_code == 2, result.output
    assert "--batch musi być >= 1" in result.output


def test_hashes_file_and_sets_status(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="a.pdf", content=b"tresc a")
    conn.close()

    result = _run(db_path, sources_root)

    assert result.exit_code == 0, result.output
    conn = db.connect(db_path, init=False)
    row = conn.execute("SELECT status, sha256, error_message FROM files WHERE source_relative_path='a.pdf'").fetchone()
    conn.close()

    assert row["status"] == "hashed"
    assert row["error_message"] is None
    assert row["sha256"] == hashlib.sha256(b"tresc a").hexdigest()
    assert "zahashowane: 1" in result.output


def test_content_row_created_with_correct_kind(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="a.pdf", content=b"tresc a")
    conn.close()

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    content = conn.execute(
        "SELECT content_kind FROM content WHERE sha256 = ?",
        (hashlib.sha256(b"tresc a").hexdigest(),),
    ).fetchone()
    conn.close()

    assert content["content_kind"] == "pdf"


# --- duplikaty treści: content raz, pierwsze rozszerzenie wygrywa -------------


def test_duplicate_content_creates_single_content_row_first_extension_wins(
    db_path: Path, sources_root: Path
) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    # ten sam bajtowy content, dwa różne rozszerzenia; a.pdf ma niższy file_id.
    first_id = _seed_file(conn, sources_root, relpath="a.pdf", content=b"identyczna tresc")
    second_id = _seed_file(conn, sources_root, relpath="b.docx", content=b"identyczna tresc")
    conn.close()
    assert first_id < second_id

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    sha = hashlib.sha256(b"identyczna tresc").hexdigest()
    rows = conn.execute("SELECT content_kind FROM content WHERE sha256 = ?", (sha,)).fetchall()
    files = conn.execute("SELECT sha256, status FROM files ORDER BY file_id").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["content_kind"] == "pdf"  # pierwszy przetworzony plik (niższy file_id)
    assert all(f["status"] == "hashed" for f in files)
    assert files[0]["sha256"] == files[1]["sha256"] == sha


# --- błędy: brakujący plik ------------------------------------------------------


def test_missing_file_sets_error_status(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="brak.pdf", content=None)
    conn.close()

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    row = conn.execute(
        "SELECT status, error_message FROM files WHERE source_relative_path='brak.pdf'"
    ).fetchone()
    conn.close()

    assert row["status"] == "error"
    assert row["error_message"]
    assert "Error" in row["error_message"]


def test_error_does_not_block_other_files(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="brak.pdf", content=None)
    _seed_file(conn, sources_root, relpath="ok.pdf", content=b"ok")
    conn.close()

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output
    assert "zahashowane: 1" in result.output
    assert "błędy: 1" in result.output


# --- ponowne uruchomienie: brak pracy do wykonania ----------------------------


def test_rerun_is_a_noop(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="a.pdf", content=b"tresc a")
    conn.close()

    first = _run(db_path, sources_root)
    second = _run(db_path, sources_root)

    assert first.exit_code == 0
    assert second.exit_code == 0, second.output
    assert "zahashowane: 0" in second.output
    assert "błędy: 0" in second.output

    conn = db.connect(db_path, init=False)
    pending = db.files_pending(conn, "hash")
    conn.close()
    assert pending == []


# --- filtry: --limit i --package ----------------------------------------------


def test_limit_option_caps_processed_files(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    for i in range(3):
        _seed_file(conn, sources_root, relpath=f"f{i}.pdf", content=f"tresc {i}".encode())
    conn.close()

    result = _run(db_path, sources_root, "--limit", "1")
    assert result.exit_code == 0, result.output
    assert "zahashowane: 1" in result.output

    conn = db.connect(db_path, init=False)
    counts = db.file_status_counts(conn)
    conn.close()
    assert counts["hashed"] == 1
    assert counts["discovered"] == 2


def test_package_option_filters_source_package(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn, "P1")
    _seed_package(conn, "P2")
    _seed_file(conn, sources_root, package="P1", relpath="a.pdf", content=b"z p1")
    _seed_file(conn, sources_root, package="P2", relpath="b.pdf", content=b"z p2")
    conn.close()

    result = _run(db_path, sources_root, "--package", "P2")
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    p1_status = conn.execute(
        "SELECT status FROM files WHERE source_package='P1'"
    ).fetchone()["status"]
    p2_status = conn.execute(
        "SELECT status FROM files WHERE source_package='P2'"
    ).fetchone()["status"]
    conn.close()

    assert p1_status == "discovered"
    assert p2_status == "hashed"


# --- granica partii ------------------------------------------------------------


def test_batch_boundary_processes_all_files(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    for i in range(5):
        _seed_file(conn, sources_root, relpath=f"f{i}.pdf", content=f"unikalna tresc {i}".encode())
    conn.close()

    result = _run(db_path, sources_root, "--batch", "2")

    assert result.exit_code == 0, result.output
    assert "zahashowane: 5" in result.output

    conn = db.connect(db_path, init=False)
    rows = conn.execute("SELECT source_relative_path, sha256, status FROM files").fetchall()
    conn.close()

    assert all(r["status"] == "hashed" for r in rows)
    for row in rows:
        i = int(row["source_relative_path"][1])
        expected = hashlib.sha256(f"unikalna tresc {i}".encode()).hexdigest()
        assert row["sha256"] == expected
    # trzy partie po 2/2/1 pliku -> co najmniej trzy linie postępu na stderr
    assert result.output.count("hash:") >= 3


# --- brak bazy -------------------------------------------------------------


def test_refuses_missing_database(tmp_path: Path, sources_root: Path) -> None:
    result = _run(tmp_path / "nie-ma.sqlite", sources_root)

    assert result.exit_code == 1


# --- Ctrl-C: partia w toku i tak trafia do bazy -------------------------------


def test_keyboard_interrupt_flushes_partial_batch(
    db_path: Path, sources_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    for i in range(5):
        _seed_file(conn, sources_root, relpath=f"f{i}.pdf", content=f"tresc {i}".encode())
    conn.close()

    real_sha256_file = hashes.sha256_file
    calls = {"n": 0}

    def flaky(path: Path) -> str:
        calls["n"] += 1
        if calls["n"] == 4:  # przerwij w trakcie drugiej (niepełnej) partii: f0,f1|f2,f3*
            raise KeyboardInterrupt
        return real_sha256_file(path)

    monkeypatch.setattr(hash_files.hashes, "sha256_file", flaky)

    result = _run(db_path, sources_root, "--batch", "2")

    assert result.exit_code == 130

    conn = db.connect(db_path, init=False)
    counts = db.file_status_counts(conn)
    conn.close()
    # pierwsza pełna partia (f0,f1) zacommitowana na granicy batcha; z drugiej
    # partii f2 zdążył się zahashować (i został wymuszony przez except w pętli
    # nawet bez osiągnięcia granicy), f3 przerwany w trakcie hashowania.
    assert counts["hashed"] == 3
    assert counts["discovered"] == 2


# --- ochrona przed wyjściem poza katalog źródeł -------------------------------


def test_absolute_relative_path_is_rejected(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="/etc/passwd", content=None, folder_path="P1")
    conn.close()

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    row = conn.execute(
        "SELECT status, error_message FROM files WHERE source_relative_path='/etc/passwd'"
    ).fetchone()
    conn.close()

    assert row["status"] == "error"
    assert row["error_message"] == "ścieżka poza katalogiem źródeł"


def test_dotdot_path_escaping_sources_is_rejected(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    outside = sources_root.parent / "poza-sources.txt"
    outside.write_bytes(b"nie powinno byc czytane")
    # source_relative_path wychodzi przez '..' poza sources_root/P1.
    _seed_file(conn, sources_root, relpath="../../poza-sources.txt", content=None, folder_path="P1")
    conn.close()

    result = _run(db_path, sources_root)
    assert result.exit_code == 0, result.output

    conn = db.connect(db_path, init=False)
    row = conn.execute(
        "SELECT status, error_message FROM files WHERE source_relative_path='../../poza-sources.txt'"
    ).fetchone()
    conn.close()

    assert row["status"] == "error"
    assert row["error_message"] == "ścieżka poza katalogiem źródeł"


# --- utrata partii przy nieoczekiwanym wyjątku --------------------------------


def test_unexpected_exception_flushes_batch_then_fails(
    db_path: Path, sources_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    for i in range(3):
        _seed_file(conn, sources_root, relpath=f"f{i}.pdf", content=f"tresc {i}".encode())
    conn.close()

    real_sha256_file = hashes.sha256_file
    calls = {"n": 0}

    def boom(path: Path) -> str:
        calls["n"] += 1
        if calls["n"] == 3:
            raise ValueError("cos poszlo nie tak")
        return real_sha256_file(path)

    monkeypatch.setattr(hash_files.hashes, "sha256_file", boom)

    result = _run(db_path, sources_root, "--batch", "10")

    assert result.exit_code == 1

    conn = db.connect(db_path, init=False)
    counts = db.file_status_counts(conn)
    conn.close()
    assert counts["hashed"] == 2
    assert counts["discovered"] == 1


# --- widoczność i ponawianie zablokowanych błędów -----------------------------


def test_summary_reports_previous_errors(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="a.pdf", content=b"a", extension="pdf")
    with conn:
        conn.execute(
            "UPDATE files SET status = 'error', error_message = 'stary blad' "
            "WHERE source_relative_path = 'a.pdf'"
        )
    conn.close()

    result = _run(db_path, sources_root)

    assert result.exit_code == 0, result.output
    assert "wcześniejsze błędy: 1 — użyj --retry-errors" in result.output
    # bez --retry-errors plik zostaje w błędzie, nie jest ponownie próbowany.
    conn = db.connect(db_path, init=False)
    status = conn.execute("SELECT status FROM files WHERE source_relative_path='a.pdf'").fetchone()["status"]
    conn.close()
    assert status == "error"


def test_retry_errors_resets_and_rehashes(db_path: Path, sources_root: Path) -> None:
    conn = db.connect(db_path, init=False)
    _seed_package(conn)
    _seed_file(conn, sources_root, relpath="a.pdf", content=b"a", extension="pdf")
    with conn:
        conn.execute(
            "UPDATE files SET status = 'error', error_message = 'stary blad' "
            "WHERE source_relative_path = 'a.pdf'"
        )
    conn.close()

    result = _run(db_path, sources_root, "--retry-errors")

    assert result.exit_code == 0, result.output
    assert "wcześniejsze błędy: 1 — użyj --retry-errors" in result.output
    assert "zahashowane: 1" in result.output

    conn = db.connect(db_path, init=False)
    row = conn.execute(
        "SELECT status, error_message, sha256 FROM files WHERE source_relative_path='a.pdf'"
    ).fetchone()
    conn.close()
    assert row["status"] == "hashed"
    assert row["error_message"] is None
    assert row["sha256"] == hashlib.sha256(b"a").hexdigest()
