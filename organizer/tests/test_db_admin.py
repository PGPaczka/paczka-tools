"""Testy CLI administracyjnego: przeliczenie content_kind po zmianie mapy rozszerzeń.

Baza żyje wyłącznie w tmp_path; nic nie dotyka realnego indeksu ani materiałów.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import db_admin
from orglib import db

runner = CliRunner()


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "organizer.sqlite"
    conn = db.connect(path)
    conn.close()
    return path


def _seed(path: Path, *, sha: str, extension: str, kind: str, relpath: str | None = None) -> None:
    """Zasiewa jedną treść i jej plik w statusie 'hashed'."""
    conn = db.connect(path, init=False)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P", "source_package": "P"})
    db.upsert_content(conn, {"sha256": sha, "content_kind": kind})
    db.upsert_file(conn, {
        "source_package": "P",
        "source_relative_path": relpath or f"plik.{extension}",
        "folder_path": "P",
        "filename": f"plik.{extension}",
        "extension": extension,
        "size_bytes": 1,
        "sha256": sha,
        "status": "hashed",
    })
    conn.close()


def _kind(path: Path, sha: str) -> str:
    conn = sqlite3.connect(path)
    try:
        return str(conn.execute("SELECT content_kind FROM content WHERE sha256 = ?", (sha,)).fetchone()[0])
    finally:
        conn.close()


def test_dry_run_reports_without_writing(database: Path) -> None:
    """Bez --apply komenda tylko raportuje; baza zostaje nietknięta."""
    _seed(database, sha="a" * 64, extension="jfif", kind="other")
    result = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(database)])
    assert result.exit_code == 0, result.output
    assert "other -> image: 1" in result.output
    assert "treści do zmiany: 1" in result.output
    assert "dry-run" in result.output
    assert _kind(database, "a" * 64) == "other"


def test_apply_updates_kind_and_is_idempotent(database: Path) -> None:
    """--apply przelicza rodzaj, a powtórzenie nie ma już nic do roboty."""
    _seed(database, sha="b" * 64, extension="ppsx", kind="other")
    first = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(database), "--apply"])
    assert first.exit_code == 0, first.output
    assert "zapisane: 1" in first.output
    assert _kind(database, "b" * 64) == "pptx"
    second = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(database)])
    assert "treści do zmiany: 0" in second.output


def test_unchanged_kinds_are_left_alone(database: Path) -> None:
    """Treść z poprawnym rodzajem nie jest ruszana."""
    _seed(database, sha="c" * 64, extension="pdf", kind="pdf")
    result = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(database), "--apply"])
    assert result.exit_code == 0, result.output
    assert "treści do zmiany: 0" in result.output
    assert _kind(database, "c" * 64) == "pdf"


def test_first_extension_wins_like_hash_stage(database: Path) -> None:
    """Przy kilku rozszerzeniach tej samej treści wygrywa pierwsza ścieżka — jak w hash_files."""
    sha = "d" * 64
    _seed(database, sha=sha, extension="jfif", kind="other", relpath="a_pierwszy.jfif")
    _seed(database, sha=sha, extension="bin", kind="other", relpath="z_drugi.bin")
    result = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(database), "--apply"])
    assert result.exit_code == 0, result.output
    assert _kind(database, sha) == "image"


def test_missing_database_exits_one(tmp_path: Path) -> None:
    """Nieistniejąca baza kończy się kodem 1 i nie jest zakładana po cichu."""
    missing = tmp_path / "nie-ma.sqlite"
    result = runner.invoke(db_admin.app, ["refresh-kinds", "--db", str(missing)])
    assert result.exit_code == 1
    assert "brak bazy" in result.output
    assert not missing.exists()
