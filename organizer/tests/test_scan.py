"""Testy skanu źródeł: wiersze plików/katalogów, wykrywanie zmian, drzewo i CLI.

Wszystko dzieje się w tmp_path — testy nigdy nie dotykają prawdziwego 00_SOURCES
ani 20_WORK.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import scan
from orglib import db

runner = CliRunner()


@pytest.fixture()
def sources(tmp_path: Path) -> Path:
    """Sztuczne źródła: dwie paczki, zagnieżdżenie, pusty katalog i same śmieci."""
    root = tmp_path / "00_SOURCES"
    p1 = root / "P1"
    (p1 / "sub" / "deep").mkdir(parents=True)
    (p1 / "empty").mkdir()
    (p1 / ".cache").mkdir()

    (p1 / "a.PDF").write_text("aaa", encoding="utf-8")
    (p1 / "readme").write_text("r", encoding="utf-8")
    (p1 / "sub" / "b.txt").write_text("bb", encoding="utf-8")
    (p1 / "sub" / "deep" / "c.txt").write_text("cccc", encoding="utf-8")
    (p1 / "Thumbs.db").write_text("x", encoding="utf-8")
    (p1 / "~$lock.docx").write_text("x", encoding="utf-8")
    (p1 / ".hidden.txt").write_text("x", encoding="utf-8")
    (p1 / ".cache" / "inside.txt").write_text("x", encoding="utf-8")
    os.symlink(p1 / "a.PDF", p1 / "link.pdf")
    os.symlink(p1 / "sub", p1 / "linkdir")

    p2 = root / "P2"
    p2.mkdir()
    (p2 / "x.md").write_text("mmmmm", encoding="utf-8")
    return root


@pytest.fixture()
def conn(tmp_path: Path):
    """Świeża baza w tmp_path z założonym schematem."""
    connection = db.connect(tmp_path / "organizer.sqlite")
    yield connection
    connection.close()


def _files(connection: sqlite3.Connection, package: str = "P1") -> dict[str, sqlite3.Row]:
    """Wiersze plików paczki, kluczowane ścieżką względną."""
    rows = connection.execute(
        "SELECT * FROM files WHERE source_package = ?", (package,)
    ).fetchall()
    return {str(row["source_relative_path"]): row for row in rows}


def _folders(connection: sqlite3.Connection, package: str = "P1") -> dict[str, sqlite3.Row]:
    """Wiersze katalogów paczki, kluczowane folder_path."""
    rows = connection.execute(
        "SELECT * FROM folders WHERE source_package = ?", (package,)
    ).fetchall()
    return {str(row["folder_path"]): row for row in rows}


def _mark_hashed(connection: sqlite3.Connection) -> None:
    """Udaje wynik dalszych etapów: nadaje hashe i status 'hashed' plikom i katalogom."""
    with connection:
        connection.execute("UPDATE files SET sha256 = 'a' || file_id, status = 'hashed'")
        connection.execute("UPDATE folders SET tree_hash = 'th', status = 'hashed'")


# --- pierwszy skan ------------------------------------------------------------


def test_first_scan_inserts_files(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_package(conn, sources / "P1", "P1")

    files = _files(conn)

    assert sorted(files) == ["a.PDF", "readme", "sub/b.txt", "sub/deep/c.txt"]
    assert files["sub/deep/c.txt"]["folder_path"] == "P1/sub/deep"
    assert files["a.PDF"]["folder_path"] == "P1"
    assert files["a.PDF"]["extension"] == "pdf"
    assert files["readme"]["extension"] is None
    assert files["a.PDF"]["filename"] == "a.PDF"
    assert files["sub/deep/c.txt"]["size_bytes"] == 4
    assert files["a.PDF"]["modified_date"].endswith("Z")
    assert {row["status"] for row in files.values()} == {"discovered"}


def test_first_scan_skips_junk_hidden_and_symlinks(
    conn: sqlite3.Connection, sources: Path
) -> None:
    stats = scan.scan_package(conn, sources / "P1", "P1")

    assert stats.skipped_ignored == 2  # Thumbs.db, ~$lock.docx
    assert stats.skipped_hidden == 2  # .hidden.txt, .cache/
    assert stats.skipped_symlinks == 2  # link.pdf, linkdir
    assert stats.errors == 0
    assert "P1/.cache" not in _folders(conn)


def test_folder_stats_are_recursive(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_package(conn, sources / "P1", "P1")

    folders = _folders(conn)

    assert sorted(folders) == ["P1", "P1/empty", "P1/sub", "P1/sub/deep"]
    assert folders["P1"]["file_count"] == 4
    assert folders["P1"]["total_bytes"] == 3 + 1 + 2 + 4
    assert folders["P1/sub"]["file_count"] == 2
    assert folders["P1/sub"]["total_bytes"] == 6
    assert folders["P1/empty"]["file_count"] == 0
    assert folders["P1/empty"]["total_bytes"] == 0
    assert folders["P1/empty"]["max_mtime"] is None
    assert folders["P1"]["max_mtime"].endswith("Z")
    assert all(row["structural_signature"] for row in folders.values())
    assert folders["P1"]["structural_signature"] != folders["P1/sub"]["structural_signature"]


def test_package_row_keeps_manual_columns(conn: sqlite3.Connection, sources: Path) -> None:
    db.upsert(
        conn,
        "source_packages",
        {"package_name": "P1", "drive_url": "https://drive/x", "notes": "ręczna notatka"},
        conflict=("package_name",),
    )

    scan.scan_package(conn, sources / "P1", "P1")

    row = conn.execute("SELECT * FROM source_packages WHERE package_name = 'P1'").fetchone()
    assert row["drive_url"] == "https://drive/x"
    assert row["notes"] == "ręczna notatka"
    assert row["local_path"] == str(sources / "P1")


# --- re-run: wykrywanie zmian -------------------------------------------------


def test_rescan_without_changes_writes_nothing(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)

    stats = scan.scan_package(conn, sources / "P1", "P1")

    assert (stats.files_new, stats.files_changed, stats.files_unchanged) == (0, 0, 4)
    assert (stats.folders_written, stats.folders_unchanged) == (0, 4)
    assert {row["status"] for row in _files(conn).values()} == {"hashed"}
    assert all(row["sha256"] for row in _files(conn).values())
    assert {row["status"] for row in _folders(conn).values()} == {"hashed"}
    assert {row["tree_hash"] for row in _folders(conn).values()} == {"th"}


def test_changed_file_resets_itself_and_its_ancestors(
    conn: sqlite3.Connection, sources: Path
) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)
    (sources / "P1" / "sub" / "deep" / "c.txt").write_text("cccc-dopisane", encoding="utf-8")

    stats = scan.scan_package(conn, sources / "P1", "P1")

    files = _files(conn)
    folders = _folders(conn)
    assert (stats.files_changed, stats.files_unchanged, stats.files_new) == (1, 3, 0)
    assert files["sub/deep/c.txt"]["sha256"] is None
    assert files["sub/deep/c.txt"]["status"] == "discovered"
    assert files["sub/deep/c.txt"]["size_bytes"] == len("cccc-dopisane")
    assert files["a.PDF"]["sha256"] is not None and files["a.PDF"]["status"] == "hashed"
    for ancestor in ("P1", "P1/sub", "P1/sub/deep"):
        assert folders[ancestor]["tree_hash"] is None, ancestor
        assert folders[ancestor]["status"] == "discovered", ancestor
    assert folders["P1/empty"]["tree_hash"] == "th"
    assert folders["P1/empty"]["status"] == "hashed"
    assert stats.folders_written == 3


def test_new_file_is_added_without_touching_the_rest(
    conn: sqlite3.Connection, sources: Path
) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)
    (sources / "P1" / "sub" / "nowy.TXT").write_text("n", encoding="utf-8")

    stats = scan.scan_package(conn, sources / "P1", "P1")

    files = _files(conn)
    assert (stats.files_new, stats.files_unchanged, stats.files_changed) == (1, 4, 0)
    assert files["sub/nowy.TXT"]["extension"] == "txt"
    assert files["sub/nowy.TXT"]["status"] == "discovered"
    assert files["sub/b.txt"]["status"] == "hashed"
    assert _folders(conn)["P1/sub/deep"]["tree_hash"] == "th"
    assert stats.folders_written == 2  # P1 i P1/sub


def test_missing_file_is_reported_not_deleted(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    (sources / "P1" / "a.PDF").unlink()

    stats = scan.scan_package(conn, sources / "P1", "P1")

    assert stats.files_missing == 1
    assert "a.PDF" in _files(conn)
    assert len(_files(conn)) == 4


def test_missing_folder_is_reported_not_deleted(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    (sources / "P1" / "empty").rmdir()

    stats = scan.scan_package(conn, sources / "P1", "P1")

    assert stats.folders_missing == 1
    assert "P1/empty" in _folders(conn)


# --- snapshot drzewa ----------------------------------------------------------


def test_sources_tree_lists_folders_only(conn: sqlite3.Connection, sources: Path) -> None:
    scan.scan_sources(conn, sources, scan.discover_packages(sources)[0])

    text = scan.render_sources_tree(conn)

    assert "Paczki: 2 · katalogi: 5 · pliki: 5 · rozmiar: 15 B" in text
    assert "- P1/  (4 plików, 10 B)" in text
    assert "  - empty/  (0 plików, 0 B)" in text
    assert "  - sub/  (2 plików, 6 B)" in text
    assert "    - deep/  (1 plików, 4 B)" in text
    assert "- P2/  (1 plików, 5 B)" in text
    assert "a.PDF" not in text
    assert text.index("- P1/") < text.index("  - empty/") < text.index("- P2/")


def test_sources_tree_ignores_row_insertion_order(
    conn: sqlite3.Connection, sources: Path, tmp_path: Path
) -> None:
    scan.scan_sources(conn, sources, scan.discover_packages(sources)[0])
    first = scan.render_sources_tree(conn)

    other = db.connect(tmp_path / "w-innej-kolejnosci.sqlite")
    try:
        for table, conflict in (
            ("source_packages", ("package_name",)),
            ("folders", ("folder_path",)),
            ("files", ("source_package", "source_relative_path")),
        ):
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            rows.reverse()
            for row in rows:
                row.pop("file_id", None)
            db.upsert_many(other, table, rows, conflict=conflict)
        second = scan.render_sources_tree(other)
    finally:
        other.close()

    assert second == first
    assert scan.render_sources_tree(conn) == first


def test_human_bytes_units() -> None:
    assert scan._human_bytes(0) == "0 B"
    assert scan._human_bytes(1023) == "1023 B"
    assert scan._human_bytes(1024) == "1.0 KiB"
    assert scan._human_bytes(1536 * 1024) == "1.5 MiB"


# --- CLI ----------------------------------------------------------------------


def test_cli_scans_everything_and_writes_tree(tmp_path: Path, sources: Path) -> None:
    database = tmp_path / "db.sqlite"
    tree = tmp_path / "SOURCES_TREE.md"

    result = runner.invoke(
        scan.app,
        ["--db", str(database), "--sources", str(sources), "--tree", str(tree)],
    )

    assert result.exit_code == 0, result.output
    assert tree.exists()
    connection = db.connect(database, init=False)
    try:
        assert connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 5
        assert connection.execute("SELECT COUNT(*) AS n FROM folders").fetchone()["n"] == 5
        assert connection.execute("SELECT COUNT(*) AS n FROM source_packages").fetchone()["n"] == 2
    finally:
        connection.close()


def test_cli_default_tree_is_a_report(
    tmp_path: Path, sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    organizer_root = tmp_path / "organizer"
    monkeypatch.setattr(scan.config, "ORGANIZER_ROOT", organizer_root)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        scan.app,
        ["--db", str(tmp_path / "db.sqlite"), "--sources", str(sources)],
    )

    assert result.exit_code == 0, result.output
    tree = organizer_root / "reports" / "SOURCES_TREE.md"
    assert "P1" in tree.read_text(encoding="utf-8")
    assert not (organizer_root / "docs").exists()


def test_cli_package_filter_scans_only_selected(tmp_path: Path, sources: Path) -> None:
    database = tmp_path / "db.sqlite"

    result = runner.invoke(
        scan.app,
        ["--db", str(database), "--sources", str(sources), "--package", "P1", "--no-tree"],
    )

    assert result.exit_code == 0, result.output
    connection = db.connect(database, init=False)
    try:
        rows = connection.execute("SELECT package_name FROM source_packages").fetchall()
        packages = [row["package_name"] for row in rows]
        assert packages == ["P1"]
        assert connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 4
    finally:
        connection.close()


def test_cli_no_tree_skips_generation(tmp_path: Path, sources: Path) -> None:
    database = tmp_path / "db.sqlite"
    tree = tmp_path / "SOURCES_TREE.md"

    result = runner.invoke(
        scan.app, ["--db", str(database), "--sources", str(sources), "--no-tree"]
    )

    assert result.exit_code == 0, result.output
    assert not tree.exists()
    assert "drzewo:" not in result.output


def test_cli_rejects_tree_and_no_tree_together(tmp_path: Path, sources: Path) -> None:
    result = runner.invoke(
        scan.app,
        [
            "--db",
            str(tmp_path / "db.sqlite"),
            "--sources",
            str(sources),
            "--tree",
            str(tmp_path / "t.md"),
            "--no-tree",
        ],
    )

    assert result.exit_code == 2


def test_cli_refuses_missing_sources(tmp_path: Path) -> None:
    result = runner.invoke(
        scan.app,
        ["--db", str(tmp_path / "db.sqlite"), "--sources", str(tmp_path / "nie-ma"), "--no-tree"],
    )

    assert result.exit_code == 1
    assert not (tmp_path / "db.sqlite").exists()


def test_cli_refuses_unknown_package(tmp_path: Path, sources: Path) -> None:
    result = runner.invoke(
        scan.app,
        ["--db", str(tmp_path / "db.sqlite"), "--sources", str(sources), "--package", "P9"],
    )

    assert result.exit_code == 1
    assert "P9" in result.output
    assert not (tmp_path / "db.sqlite").exists()


# --- rozdzielczość czasu i podpis struktury -----------------------------------


def test_touch_within_the_same_second_changes_nothing(
    conn: sqlite3.Connection, sources: Path
) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)
    target = sources / "P1" / "sub" / "b.txt"
    same_second = os.stat(target).st_mtime_ns // 1_000_000_000 * 1_000_000_000 + 900_000_000
    os.utime(target, ns=(same_second, same_second))

    stats = scan.scan_package(conn, sources / "P1", "P1")

    assert (stats.files_changed, stats.files_unchanged, stats.files_new) == (0, 4, 0)
    assert stats.folders_written == 0
    assert _files(conn)["sub/b.txt"]["status"] == "hashed"
    assert {row["tree_hash"] for row in _folders(conn).values()} == {"th"}


def test_mtime_crossing_a_second_resets_file_and_ancestors(
    conn: sqlite3.Connection, sources: Path
) -> None:
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)
    target = sources / "P1" / "sub" / "deep" / "c.txt"
    later = (os.stat(target).st_mtime_ns // 1_000_000_000 + 5) * 1_000_000_000
    os.utime(target, ns=(later, later))

    stats = scan.scan_package(conn, sources / "P1", "P1")

    folders = _folders(conn)
    assert stats.files_changed == 1
    assert _files(conn)["sub/deep/c.txt"]["status"] == "discovered"
    assert _files(conn)["sub/deep/c.txt"]["sha256"] is None
    for ancestor in ("P1", "P1/sub", "P1/sub/deep"):
        assert folders[ancestor]["tree_hash"] is None, ancestor
        assert folders[ancestor]["status"] == "discovered", ancestor
    assert folders["P1/empty"]["tree_hash"] == "th"


def test_identical_sibling_folders_share_structural_signature(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    package = tmp_path / "src-bliznieta" / "P9"
    # ten sam układ i rozmiary, mtime różne TYLKO w ułamku sekundy
    for name, fraction in (("kopia_a", 123_000_000), ("kopia_b", 789_000_000)):
        folder = package / name
        folder.mkdir(parents=True)
        (folder / "plik.txt").write_text("tresc", encoding="utf-8")
        stamp = 1_700_000_000 * 1_000_000_000 + fraction
        os.utime(folder / "plik.txt", ns=(stamp, stamp))

    scan.scan_package(conn, package, "P9")

    folders = _folders(conn, "P9")
    assert (
        folders["P9/kopia_a"]["structural_signature"]
        == folders["P9/kopia_b"]["structural_signature"]
    )
    assert folders["P9/kopia_a"]["max_mtime"] == folders["P9/kopia_b"]["max_mtime"]
    assert folders["P9"]["structural_signature"] != folders["P9/kopia_a"]["structural_signature"]


# --- wpisy, których nie da się odczytać ---------------------------------------

posix_permissions = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="test wymaga uprawnień POSIX i użytkownika innego niż root",
)


@posix_permissions
def test_unreadable_directory_is_error_and_keeps_its_files(
    conn: sqlite3.Connection, sources: Path
) -> None:
    closed = sources / "P1" / "zamkniety"
    closed.mkdir()
    (closed / "tajne.txt").write_text("t", encoding="utf-8")
    scan.scan_package(conn, sources / "P1", "P1")
    _mark_hashed(conn)

    closed.chmod(0o000)
    try:
        stats = scan.scan_package(conn, sources / "P1", "P1")
    finally:
        closed.chmod(0o755)

    folders = _folders(conn)
    assert stats.errors == 1
    assert stats.files_missing == 0
    assert stats.folders_missing == 0
    assert "zamkniety/tajne.txt" in _files(conn)
    assert folders["P1/zamkniety"]["status"] == "error"
    assert folders["P1/zamkniety"]["file_count"] is None
    assert folders["P1/zamkniety"]["total_bytes"] is None
    assert folders["P1/zamkniety"]["max_mtime"] is None
    assert folders["P1/zamkniety"]["structural_signature"] is None
    assert folders["P1/zamkniety"]["tree_hash"] is None
    # przodek: status błędu i brak podpisu, ale liczby z czytelnej części
    assert folders["P1"]["status"] == "error"
    assert folders["P1"]["structural_signature"] is None
    assert folders["P1"]["file_count"] == 4
    assert folders["P1"]["total_bytes"] == 10
    # rodzeństwo nietknięte
    assert folders["P1/sub"]["status"] == "hashed"
    assert folders["P1/sub"]["tree_hash"] == "th"


@posix_permissions
def test_unreadable_directory_is_rewritten_on_every_run(
    conn: sqlite3.Connection, sources: Path
) -> None:
    closed = sources / "P1" / "zamkniety"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        scan.scan_package(conn, sources / "P1", "P1")
        stats = scan.scan_package(conn, sources / "P1", "P1")
    finally:
        closed.chmod(0o755)

    # NULL == NULL nie może udawać „bez zmian”: P1 i P1/zamkniety piszemy zawsze,
    # reszta poddrzewa (empty, sub, sub/deep) zostaje bez zapisu
    assert stats.folders_written == 2
    assert stats.folders_unchanged == 3
    assert stats.errors == 1


@pytest.mark.skipif(
    sys.getfilesystemencoding().lower() not in {"utf-8", "utf8"},
    reason="test zakłada system plików w UTF-8",
)
def test_non_utf8_name_is_skipped(conn: sqlite3.Connection, sources: Path) -> None:
    raw_name = os.path.join(os.fsencode(sources / "P1" / "sub"), b"zle\xb3imie.txt")
    with open(raw_name, "wb") as handle:
        handle.write(b"x")
    try:
        stats = scan.scan_package(conn, sources / "P1", "P1")
    finally:
        os.remove(raw_name)

    assert stats.errors == 1
    assert sorted(_files(conn)) == ["a.PDF", "readme", "sub/b.txt", "sub/deep/c.txt"]
    assert _folders(conn)["P1/sub"]["file_count"] == 2


def test_discover_packages_skips_symlinks_and_hidden(tmp_path: Path) -> None:
    root = tmp_path / "src"
    (root / "P1").mkdir(parents=True)
    (root / ".ukryta").mkdir()
    (root / "luzny.txt").write_text("x", encoding="utf-8")
    os.symlink(root / "P1", root / "P1-dowiazanie")

    names, skipped = scan.discover_packages(root)

    assert names == ["P1"]
    assert skipped == 1


def test_cli_partial_scan_exits_with_three_after_writing(tmp_path: Path) -> None:
    root = tmp_path / "src"
    (root / "P1").mkdir(parents=True)
    (root / "P1" / "a.txt").write_text("a", encoding="utf-8")
    os.symlink(root / "P1", root / "P1-dowiazanie")
    database = tmp_path / "db.sqlite"

    result = runner.invoke(
        scan.app, ["--db", str(database), "--sources", str(root), "--no-tree"]
    )

    assert result.exit_code == 3
    assert "skan częściowy" in result.output
    connection = db.connect(database, init=False)
    try:
        assert connection.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 1
    finally:
        connection.close()
