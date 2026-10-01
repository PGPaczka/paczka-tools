"""Testy raportu deduplikacji: liczby, per-paczka, foldery-duplikaty, inwentarz.

Wszystko dzieje się w tmp_path — testy nigdy nie dotykają prawdziwej bazy ani
prawdziwego 00_SOURCES.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import dedup_report
from orglib import db

runner = CliRunner()

SHA_A = "a" * 64  # współdzielona P1 <-> P2, 2 kopie, pdf
SHA_B = "b" * 64  # wyłączna P1, 2 kopie w tej samej paczce, pdf
SHA_C = "c" * 64  # wyłączna P2, 1 kopia, docx
SHA_D = "d" * 64  # wyłączna P3, 3 kopie, image
SHA_E = "e" * 64  # P1/origfolder, unikalna, pdf
SHA_F = "f" * 64  # P1/dupfolder, unikalna, pdf
SHA_G = "g" * 64  # P1/dupfolder/nested, unikalna, text


def _pkg(connection: sqlite3.Connection, name: str) -> None:
    db.upsert(connection, "source_packages", {"package_name": name}, conflict=("package_name",))


def _folder(connection: sqlite3.Connection, path: str, package: str, **extra: object) -> None:
    db.upsert_folder(connection, {"folder_path": path, "source_package": package, **extra})


def _file(
    connection: sqlite3.Connection,
    package: str,
    relpath: str,
    folder_path: str,
    size: int,
    **extra: object,
) -> None:
    row: dict[str, object] = {
        "source_package": package,
        "source_relative_path": relpath,
        "folder_path": folder_path,
        "filename": Path(relpath).name,
        "size_bytes": size,
    }
    row.update(extra)
    db.upsert_file(connection, row)


def _content(connection: sqlite3.Connection, sha: str, kind: str) -> None:
    db.upsert_content(connection, {"sha256": sha, "content_kind": kind})


def _seed(connection: sqlite3.Connection) -> None:
    """2-3 paczki: sha dzielone/unikalne, plik pending, plik error, foldery-duplikaty zagnieżdżone."""
    for pkg in ("P1", "P2", "P3"):
        _pkg(connection, pkg)
        _folder(connection, pkg, pkg, tree_hash=f"root-{pkg}")

    _folder(connection, "P1/origfolder", "P1", tree_hash="t-orig", file_count=1, total_bytes=500)
    _folder(
        connection,
        "P1/dupfolder",
        "P1",
        tree_hash="t-dup",
        duplicate_of="P1/origfolder",
        file_count=1,
        total_bytes=600,
    )
    _folder(
        connection,
        "P1/dupfolder/nested",
        "P1",
        tree_hash="t-nested",
        duplicate_of="P1/dupfolder",
        file_count=1,
        total_bytes=10,
    )

    _file(connection, "P1", "a.pdf", "P1", 100, sha256=SHA_A, status="hashed")
    _file(connection, "P2", "a2.pdf", "P2", 100, sha256=SHA_A, status="hashed")
    _file(connection, "P1", "b1.pdf", "P1", 200, sha256=SHA_B, status="hashed")
    _file(connection, "P1", "b2.pdf", "P1", 200, sha256=SHA_B, status="hashed")
    _file(connection, "P2", "c.docx", "P2", 50, sha256=SHA_C, status="hashed")
    _file(connection, "P3", "d1.jpg", "P3", 1000, sha256=SHA_D, status="hashed")
    _file(connection, "P3", "d2.jpg", "P3", 1000, sha256=SHA_D, status="hashed")
    _file(connection, "P3", "d3.jpg", "P3", 1000, sha256=SHA_D, status="hashed")
    _file(connection, "P1", "pending.txt", "P1", 30, status="discovered")
    _file(connection, "P2", "broken.pdf", "P2", 40, status="error", error_message="boom")
    _file(
        connection, "P1", "origfolder/orig.pdf", "P1/origfolder", 500, sha256=SHA_E, status="hashed"
    )
    _file(connection, "P1", "dupfolder/dup.pdf", "P1/dupfolder", 600, sha256=SHA_F, status="hashed")
    _file(
        connection,
        "P1",
        "dupfolder/nested/inner.pdf",
        "P1/dupfolder/nested",
        10,
        sha256=SHA_G,
        status="hashed",
    )

    _content(connection, SHA_A, "pdf")
    _content(connection, SHA_B, "pdf")
    _content(connection, SHA_C, "docx")
    _content(connection, SHA_D, "image")
    _content(connection, SHA_E, "pdf")
    _content(connection, SHA_F, "pdf")
    _content(connection, SHA_G, "text")


@pytest.fixture()
def conn(tmp_path: Path):
    connection = db.connect(tmp_path / "organizer.sqlite")
    yield connection
    connection.close()


@pytest.fixture()
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    _seed(conn)
    return conn


# --- compute_summary -----------------------------------------------------------


def test_compute_summary_headline_numbers(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    summary = dedup_report.compute_summary(seeded, agg)

    assert summary["files_total"] == 13
    assert summary["bytes_total"] == 4830
    assert summary["hashed_count"] == 11
    assert summary["pending_count"] == 1
    assert summary["error_count"] == 1
    assert summary["unique_count"] == 7
    assert summary["unique_bytes"] == 2460
    assert summary["duplicate_copies"] == 4
    assert summary["duplicate_bytes"] == 2300
    assert summary["ratio"] == pytest.approx(2300 / 4760 * 100.0)


def test_compute_summary_on_empty_db_does_not_crash(conn: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(conn)
    summary = dedup_report.compute_summary(conn, agg)

    assert summary["files_total"] == 0
    assert summary["ratio"] == 0.0


def test_compute_summary_partition_sums_to_files_total(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    summary = dedup_report.compute_summary(seeded, agg)

    assert (
        summary["hashed_count"] + summary["pending_count"] + summary["error_count"]
        == summary["files_total"]
    )


def test_sha_aggregates_warns_on_inconsistent_sizes(conn: sqlite3.Connection, capsys) -> None:
    _pkg(conn, "P1")
    _folder(conn, "P1", "P1")
    sha = "z" * 64
    _file(conn, "P1", "a.pdf", "P1", 100, sha256=sha, status="hashed")
    _file(conn, "P1", "b.pdf", "P1", 999, sha256=sha, status="hashed")

    agg = dedup_report._sha_aggregates(conn)

    assert agg[sha]["size"] == 100  # nadal MIN
    err = capsys.readouterr().err
    assert "UWAGA: 1 treści ma kopie o różnych rozmiarach (niespójny scan)" in err


def test_sha_aggregates_no_warning_when_sizes_consistent(seeded: sqlite3.Connection, capsys) -> None:
    dedup_report._sha_aggregates(seeded)

    assert "UWAGA" not in capsys.readouterr().err


# --- compute_per_package ---------------------------------------------------------


def test_compute_per_package_exclusive_and_shared(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    rows = dedup_report.compute_per_package(seeded, agg)

    by_pkg = {row["package"]: row for row in rows}
    assert by_pkg["P1"]["files"] == 7
    assert by_pkg["P1"]["bytes"] == 1640
    assert by_pkg["P1"]["exclusive_count"] == 4  # B, E, F, G
    assert by_pkg["P1"]["exclusive_bytes"] == 1310
    assert by_pkg["P1"]["shared_count"] == 1  # A
    assert by_pkg["P1"]["copies"] == 1  # 6 zahashowanych (bez pending.txt) - 5 distinct sha

    assert by_pkg["P2"]["files"] == 3
    assert by_pkg["P2"]["bytes"] == 190
    assert by_pkg["P2"]["exclusive_count"] == 1  # C
    assert by_pkg["P2"]["exclusive_bytes"] == 50
    assert by_pkg["P2"]["shared_count"] == 1  # A
    assert by_pkg["P2"]["copies"] == 0  # 2 zahashowane (bez broken.pdf) - 2 distinct sha

    assert by_pkg["P3"]["files"] == 3
    assert by_pkg["P3"]["bytes"] == 3000
    assert by_pkg["P3"]["exclusive_count"] == 1  # D
    assert by_pkg["P3"]["exclusive_bytes"] == 1000
    assert by_pkg["P3"]["shared_count"] == 0
    assert by_pkg["P3"]["copies"] == 2  # 3 files - 1 distinct sha


def test_compute_per_package_sorted_by_bytes_desc(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    rows = dedup_report.compute_per_package(seeded, agg)

    assert [row["package"] for row in rows] == ["P3", "P1", "P2"]


def test_per_package_copies_sum_matches_summary_when_content_not_shared(
    conn: sqlite3.Connection,
) -> None:
    """Gdy żadna treść nie żyje w dwóch paczkach, suma 'copies' per paczka == duplicate_copies."""
    _pkg(conn, "Q1")
    _pkg(conn, "Q2")
    _folder(conn, "Q1", "Q1")
    _folder(conn, "Q2", "Q2")
    sha_x, sha_y = "x" * 64, "y" * 64
    _file(conn, "Q1", "a1.pdf", "Q1", 10, sha256=sha_x, status="hashed")
    _file(conn, "Q1", "a2.pdf", "Q1", 10, sha256=sha_x, status="hashed")
    _file(conn, "Q2", "b1.pdf", "Q2", 20, sha256=sha_y, status="hashed")
    _content(conn, sha_x, "pdf")
    _content(conn, sha_y, "pdf")

    agg = dedup_report._sha_aggregates(conn)
    summary = dedup_report.compute_summary(conn, agg)
    per_package = dedup_report.compute_per_package(conn, agg)

    assert sum(row["copies"] for row in per_package) == summary["duplicate_copies"] == 1


# --- compute_duplicate_folders ----------------------------------------------------


def test_compute_duplicate_folders_counts_topmost_only(seeded: sqlite3.Connection) -> None:
    result = dedup_report.compute_duplicate_folders(seeded)

    assert result == {
        "folder_count": 1,
        "files": 1,
        "bytes": 600,
        "canonical_targets": 1,
    }


def test_compute_duplicate_folders_none_when_fold_hash_not_run(conn: sqlite3.Connection) -> None:
    db.upsert(conn, "source_packages", {"package_name": "P1"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P1", "source_package": "P1"})

    assert dedup_report.compute_duplicate_folders(conn) is None


# --- compute_top_duplicate_groups -------------------------------------------------


def test_top_duplicate_groups_ordering_and_wasted(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    groups = dedup_report.compute_top_duplicate_groups(agg)

    assert [g["sha256"] for g in groups] == [SHA_D, SHA_B, SHA_A]
    by_sha = {g["sha256"]: g for g in groups}
    assert by_sha[SHA_D] == {
        "sha256": SHA_D,
        "size": 1000,
        "copies": 3,
        "wasted": 2000,
        "example": "P3/d1.jpg",
    }
    assert by_sha[SHA_B]["wasted"] == 200
    assert by_sha[SHA_B]["example"] == "P1/b1.pdf"
    assert by_sha[SHA_A]["wasted"] == 100
    assert by_sha[SHA_A]["example"] == "P1/a.pdf"


def test_top_duplicate_groups_respects_limit(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)

    assert len(dedup_report.compute_top_duplicate_groups(agg, limit=2)) == 2


# --- compute_kind_stats ------------------------------------------------------------


def test_compute_kind_stats_sorted_by_unique_bytes(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    rows = dedup_report.compute_kind_stats(seeded, agg)

    assert [r["kind"] for r in rows] == ["pdf", "image", "docx", "text"]
    by_kind = {r["kind"]: r for r in rows}
    assert by_kind["pdf"] == {"kind": "pdf", "unique_count": 4, "unique_bytes": 1400, "copies": 2}
    assert by_kind["image"] == {"kind": "image", "unique_count": 1, "unique_bytes": 1000, "copies": 2}
    assert by_kind["docx"] == {"kind": "docx", "unique_count": 1, "unique_bytes": 50, "copies": 0}
    assert by_kind["text"] == {"kind": "text", "unique_count": 1, "unique_bytes": 10, "copies": 0}


# --- render_dedup_summary -----------------------------------------------------------


def test_render_dedup_summary_contains_all_sections(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    text = dedup_report.render_dedup_summary(
        dedup_report.compute_summary(seeded, agg),
        dedup_report.compute_per_package(seeded, agg),
        dedup_report.compute_duplicate_folders(seeded),
        dedup_report.compute_top_duplicate_groups(agg),
        dedup_report.compute_kind_stats(seeded, agg),
    )

    for heading in (
        "## Podsumowanie",
        "## Per paczka",
        "## Katalogi-duplikaty (fold_hash)",
        "## Największe grupy duplikatów (top 20)",
        "## Rodzaje treści",
    ):
        assert heading in text
    assert "2026" not in text  # brak znaczników czasu
    assert SHA_D[:12] in text


def test_render_dedup_summary_no_fold_hash_message(conn: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(conn)
    text = dedup_report.render_dedup_summary(
        dedup_report.compute_summary(conn, agg),
        dedup_report.compute_per_package(conn, agg),
        dedup_report.compute_duplicate_folders(conn),
        dedup_report.compute_top_duplicate_groups(agg),
        dedup_report.compute_kind_stats(conn, agg),
    )

    assert "fold_hash jeszcze nie uruchomiony." in text


def test_render_dedup_summary_is_deterministic(seeded: sqlite3.Connection) -> None:
    agg = dedup_report._sha_aggregates(seeded)
    args = (
        dedup_report.compute_summary(seeded, agg),
        dedup_report.compute_per_package(seeded, agg),
        dedup_report.compute_duplicate_folders(seeded),
        dedup_report.compute_top_duplicate_groups(agg),
        dedup_report.compute_kind_stats(seeded, agg),
    )

    assert dedup_report.render_dedup_summary(*args) == dedup_report.render_dedup_summary(*args)


# --- inwentarz -----------------------------------------------------------------


def test_inventory_rows_count_sort_and_fields(seeded: sqlite3.Connection) -> None:
    rows = dedup_report.build_inventory_rows(seeded)

    assert len(rows) == 13
    paths = [(r["package"], r["path"]) for r in rows]
    assert paths == sorted(paths)

    by_path = {(r["package"], r["path"]): r for r in rows}

    a_row = by_path[("P1", "a.pdf")]
    assert a_row["sha256"] == SHA_A
    assert a_row["kind"] == "pdf"
    assert a_row["copies"] == 2
    assert a_row["folder_dup_of"] is None
    assert a_row["status"] == "hashed"
    assert a_row["size"] == 100

    pending_row = by_path[("P1", "pending.txt")]
    assert pending_row["sha256"] is None
    assert pending_row["kind"] is None
    assert pending_row["copies"] is None
    assert pending_row["status"] == "discovered"

    error_row = by_path[("P2", "broken.pdf")]
    assert error_row["status"] == "error"
    assert error_row["sha256"] is None

    dup_row = by_path[("P1", "dupfolder/dup.pdf")]
    assert dup_row["folder_dup_of"] == "P1/origfolder"

    nested_row = by_path[("P1", "dupfolder/nested/inner.pdf")]
    assert nested_row["folder_dup_of"] == "P1/dupfolder"  # NAJBLIŻSZY przodek, nie korzeń

    orig_row = by_path[("P1", "origfolder/orig.pdf")]
    assert orig_row["folder_dup_of"] is None


def test_write_inventory_jsonl_format(seeded: sqlite3.Connection, tmp_path: Path) -> None:
    rows = dedup_report.build_inventory_rows(seeded)
    out = tmp_path / "inventory.jsonl"

    written = dedup_report.write_inventory_jsonl(rows, out)

    assert written == 13
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 13
    first = json.loads(lines[0])
    assert set(first) == {
        "package",
        "path",
        "size",
        "mtime",
        "sha256",
        "kind",
        "status",
        "folder_dup_of",
        "copies",
    }
    # sort_keys=True -> klucze alfabetycznie w surowym tekście linii
    assert lines[0].index('"copies"') < lines[0].index('"path"')


# --- CLI -------------------------------------------------------------------------


def test_cli_writes_reports_and_prints_headline(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite"
    out_dir = tmp_path / "reports"
    connection = db.connect(database)
    _seed(connection)
    connection.close()

    result = runner.invoke(dedup_report.app, ["--db", str(database), "--out-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert (out_dir / "dedup_summary.md").exists()
    assert (out_dir / "inventory.jsonl").exists()
    assert "13" in result.output  # liczba plików
    assert "48.3%" in result.output or "48.3" in result.output


def test_cli_missing_db_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(
        dedup_report.app,
        ["--db", str(tmp_path / "brak.sqlite"), "--out-dir", str(tmp_path / "out")],
    )

    assert result.exit_code == 1
    assert not (tmp_path / "out").exists()


def test_cli_refuses_non_sqlite_file(tmp_path: Path) -> None:
    bad_db = tmp_path / "nie-baza.sqlite"
    bad_db.write_bytes(b"to na pewno nie jest baza sqlite" * 10)

    result = runner.invoke(
        dedup_report.app, ["--db", str(bad_db), "--out-dir", str(tmp_path / "out")]
    )

    assert result.exit_code == 1
    assert "nie jest poprawna baza" in result.output
    assert not (tmp_path / "out").exists()


def test_cli_empty_db_does_not_crash(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite"
    db.connect(database).close()

    result = runner.invoke(
        dedup_report.app, ["--db", str(database), "--out-dir", str(tmp_path / "out")]
    )

    assert result.exit_code == 0, result.output
    text = (tmp_path / "out" / "dedup_summary.md").read_text(encoding="utf-8")
    assert "fold_hash jeszcze nie uruchomiony." in text
    assert (tmp_path / "out" / "inventory.jsonl").read_text(encoding="utf-8") == ""


def test_cli_is_deterministic_across_runs(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite"
    connection = db.connect(database)
    _seed(connection)
    connection.close()
    out_dir = tmp_path / "out"

    runner.invoke(dedup_report.app, ["--db", str(database), "--out-dir", str(out_dir)])
    summary_1 = (out_dir / "dedup_summary.md").read_bytes()
    inventory_1 = (out_dir / "inventory.jsonl").read_bytes()

    runner.invoke(dedup_report.app, ["--db", str(database), "--out-dir", str(out_dir)])
    summary_2 = (out_dir / "dedup_summary.md").read_bytes()
    inventory_2 = (out_dir / "inventory.jsonl").read_bytes()

    assert summary_1 == summary_2
    assert inventory_1 == inventory_2
