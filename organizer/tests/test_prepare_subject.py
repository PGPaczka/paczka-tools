"""CLI B1: izolowany indeks i sztuczne ścieżki, nigdy prawdziwe materiały."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

import prepare_subject
from orglib import config, db

runner = CliRunner()
SHA = "a" * 64


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work",
        media=tmp_path / "media", target_repo=tmp_path / "target",
        target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "text",
        work_thumbnails=tmp_path / "work" / "thumbs",
    )
    monkeypatch.setattr(config, "load_paths", lambda: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    conn = db.connect(paths.work_db)
    conn.close()
    return paths


def seed(path):
    conn = db.connect(path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3/AK", "source_package": "P"})
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/AK/a.pdf",
        "folder_path": "P/SEM3/AK", "size_bytes": 10, "sha256": SHA, "status": "hashed",
    })
    db.upsert_content(conn, {"sha256": SHA, "content_kind": "pdf"})
    conn.close()


def invoke(*args):
    return runner.invoke(prepare_subject.app, ["--semester", "3", "--skrot", "AK", *args])


def test_alias_default_output_repeatable_and_readonly(workspace):
    seed(workspace.work_db)
    before = workspace.work_db.read_bytes()
    mtime = workspace.work_db.stat().st_mtime_ns
    result = invoke()
    assert result.exit_code == 0, result.output
    out = config.ORGANIZER_ROOT / "reports/AKO/manifest_slice.jsonl"
    first = out.read_bytes()
    row = json.loads(first)
    assert row["subject_key"] == "AKO"
    assert row["source_sha256"] == SHA
    assert row["source_paths"] == ["P/SEM3/AK/a.pdf"]
    assert not workspace.sources.exists()
    assert invoke().exit_code == 0
    assert out.read_bytes() == first
    assert workspace.work_db.read_bytes() == before
    assert workspace.work_db.stat().st_mtime_ns == mtime


def test_empty_database_and_explicit_output(workspace, tmp_path):
    out = tmp_path / "custom"
    result = invoke("--out-dir", str(out), "--db", str(workspace.work_db))
    assert result.exit_code == 0, result.output
    assert (out / "manifest_slice.jsonl").read_bytes() == b""


@pytest.mark.parametrize("semester,skrot,extra", [
    ("3", "UNKNOWN", []), ("7", "SI", []),
    ("7", "SI", ["--grupa", "UNKNOWN"]), ("8", "AKO", []),
])
def test_invalid_subject_no_output(workspace, semester, skrot, extra):
    result = runner.invoke(prepare_subject.app, [
        "--semester", semester, "--skrot", skrot, *extra,
    ])
    assert result.exit_code != 0
    assert not config.ORGANIZER_ROOT.exists()


@pytest.mark.parametrize("kind", ["missing", "corrupt", "newer", "no_schema"])
def test_bad_database_no_output_or_creation(workspace, tmp_path, kind):
    database = tmp_path / "bad.sqlite"
    if kind == "corrupt":
        database.write_text("not sqlite", encoding="utf-8")
    elif kind == "newer":
        conn = db.connect(database)
        conn.execute("UPDATE schema_version SET version=999")
        conn.commit()
        conn.close()
    elif kind == "no_schema":
        sqlite3.connect(database).close()
    before = database.read_bytes() if database.exists() else None
    result = invoke("--db", str(database))
    assert result.exit_code == 1
    assert "Błąd" in result.output
    assert not config.ORGANIZER_ROOT.exists()
    assert (database.read_bytes() if database.exists() else None) == before


def test_repeated_shortcuts_have_separate_outputs(workspace):
    for semester, group in (
        (4, "Wspolne"), (7, "KASK_Architektura_Systemów_Komputerowych"),
        (7, "KT_Teleinformatyka"),
    ):
        result = runner.invoke(prepare_subject.app, [
            "--semester", str(semester), "--skrot", "SI", "--grupa", group,
        ])
        assert result.exit_code == 0, result.output
        assert (config.ORGANIZER_ROOT / f"reports/SEM{semester}/{group}/SI/manifest_slice.jsonl").exists()


@pytest.mark.parametrize("protected", ["sources", "target_repo", "media"])
@pytest.mark.parametrize("symlink", [False, True])
def test_protected_output_trees(workspace, tmp_path, protected, symlink):
    root = getattr(workspace, protected)
    root.mkdir()
    output = root / "report"
    if symlink:
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        output = link / "report"
    result = invoke("--out-dir", str(output))
    assert result.exit_code == 1
    assert "chronionym" in result.output
    assert list(root.iterdir()) == []


def test_output_cannot_overwrite_database(workspace, tmp_path):
    database = tmp_path / "manifest_slice.jsonl"
    db.connect(database).close()
    before = database.read_bytes()
    result = invoke("--db", str(database), "--out-dir", str(tmp_path))
    assert result.exit_code == 1
    assert database.read_bytes() == before


@pytest.mark.parametrize("protected", ["sources", "target_repo", "media"])
def test_database_in_material_tree_is_rejected_before_open(workspace, protected):
    # Syntetyczny plik, nie prawdziwe materiały.
    root = getattr(workspace, protected)
    root.mkdir()
    database = root / "index.sqlite"
    database.write_bytes(workspace.work_db.read_bytes())
    result = invoke("--db", str(database))
    assert result.exit_code == 1
    assert "baza w chronionym" in result.output
    assert list(root.iterdir()) == [database]


def test_database_hardlink_cannot_be_overwritten(workspace, tmp_path):
    output = tmp_path / "manifest_slice.jsonl"
    output.hardlink_to(workspace.work_db)
    result = invoke("--out-dir", str(tmp_path))
    assert result.exit_code == 1
    assert output.samefile(workspace.work_db)


def test_symlink_leading_out_of_sources_is_still_rejected(workspace, tmp_path):
    workspace.sources.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = workspace.sources / "link"
    link.symlink_to(elsewhere, target_is_directory=True)
    result = invoke("--out-dir", str(link))
    assert result.exit_code == 1
    assert list(elsewhere.iterdir()) == []


def test_cli_connection_really_rejects_database_writes(workspace, monkeypatch):
    def check_connection(conn, subject, subjects):
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        # Nawet po zdjęciu query_only sam tryb połączenia mode=ro zabrania DDL.
        conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE forbidden (x)")
        return []
    monkeypatch.setattr(prepare_subject, "build_manifest", check_connection)
    result = invoke()
    assert result.exit_code == 0, result.output


def test_failed_atomic_write_keeps_previous_report(workspace, tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    manifest = out / "manifest_slice.jsonl"
    manifest.write_text("previous report\n", encoding="utf-8")
    def fail(*args):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(prepare_subject.os, "replace", fail)
    result = invoke("--out-dir", str(out))
    assert result.exit_code == 1
    assert manifest.read_text() == "previous report\n"
    assert list(out.iterdir()) == [manifest]


def test_output_file_symlink_is_rejected(workspace, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    other = tmp_path / "other"
    other.write_text("unchanged", encoding="utf-8")
    (out / "manifest_slice.jsonl").symlink_to(other)
    result = invoke("--out-dir", str(out))
    assert result.exit_code == 1
    assert other.read_text() == "unchanged"


def seed_extracted_text(paths, text, *, stored=None):
    """Dokłada wynik etapu extract (B2) dla treści zasianej przez seed()."""
    target = paths.work_extracted_text / f"{SHA}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    conn = db.connect(paths.work_db)
    db.upsert_content(conn, {
        "sha256": SHA,
        "extracted_text_path": stored or target.relative_to(paths.work).as_posix(),
    })
    conn.close()
    return target


def manifest_row(output=None):
    path = output or config.ORGANIZER_ROOT / "reports/AKO/manifest_slice.jsonl"
    return json.loads(path.read_text(encoding="utf-8"))


def test_text_head_comes_from_extract_stage(workspace):
    """Głowa tekstu z B2 trafia do manifestu, żeby AI widziało treść, nie samą nazwę."""
    seed(workspace.work_db)
    seed_extracted_text(workspace, "Wykład 1: złożoność obliczeniowa\nNotatki")
    assert invoke().exit_code == 0
    assert manifest_row()["text_head"] == "Wykład 1: złożoność obliczeniowa\nNotatki"


def test_text_head_is_truncated_to_threshold(workspace):
    """Do manifestu wchodzi głowa o rozmiarze z thresholds.yaml, nie cały dokument."""
    limit = int((config.load_thresholds()["llm"])["max_text_head_bytes"])
    seed(workspace.work_db)
    seed_extracted_text(workspace, "ą" * limit)
    assert invoke().exit_code == 0
    head = manifest_row()["text_head"]
    assert len(head.encode("utf-8")) <= limit
    assert head == "ą" * (limit // 2)


@pytest.mark.parametrize("kind", ["brak_ekstrakcji", "pusty_tekst", "brak_pliku", "poza_work"])
def test_text_head_absent_without_usable_extraction(workspace, kind):
    """Brak tekstu, brak pliku i wpis w drzewie materiałów nie dają pola text_head."""
    seed(workspace.work_db)
    if kind == "pusty_tekst":
        seed_extracted_text(workspace, "   \n")
    elif kind == "brak_pliku":
        seed_extracted_text(workspace, "treść").unlink()
    elif kind == "poza_work":
        podstawiony = workspace.sources / "podstawiony.txt"
        podstawiony.parent.mkdir(parents=True, exist_ok=True)
        podstawiony.write_text("materiał źródłowy", encoding="utf-8")
        seed_extracted_text(workspace, "treść", stored=str(podstawiony))
    assert invoke().exit_code == 0
    assert "text_head" not in manifest_row()
