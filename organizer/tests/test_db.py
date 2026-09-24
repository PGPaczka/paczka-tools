"""Testy warstwy SQLite: schemat, UPSERT-y, maszyna stanów, kolejki etapów i CLI.

Wszystko dzieje się w tmp_path — testy nigdy nie dotykają prawdziwego 20_WORK.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import db_admin
from orglib import db


@pytest.fixture()
def conn(tmp_path: Path):
    """Świeża baza w tmp_path z założonym schematem."""
    connection = db.connect(tmp_path / "organizer.sqlite")
    yield connection
    connection.close()


def _seed_package(connection: sqlite3.Connection, package: str = "P1") -> None:
    """Wstawia paczkę i jej katalog korzeniowy (korzeń ma folder_path == package_name)."""
    db.upsert(connection, "source_packages", {"package_name": package}, conflict=("package_name",))
    db.upsert_folder(connection, {"folder_path": package, "source_package": package})


def _seed_file(
    connection: sqlite3.Connection,
    package: str = "P1",
    relpath: str = "a.pdf",
    folder_path: str | None = None,
    **extra: object,
) -> int:
    """Wstawia plik i zwraca jego file_id.

    ``relpath`` jest ścieżką WZGLĘDEM KATALOGU PACZKI (bez nazwy paczki),
    a ``folder_path`` domyślnie wyliczamy z niej tak jak zrobi to skrypt scan.
    """
    row: dict[str, object] = {
        "source_package": package,
        "source_relative_path": relpath,
        "folder_path": folder_path or db.folder_path_for(package, relpath),
        "filename": Path(relpath).name,
        "size_bytes": 10,
    }
    row.update(extra)
    db.upsert_file(connection, row)
    return int(
        connection.execute(
            "SELECT file_id FROM files WHERE source_package = ? AND source_relative_path = ?",
            (package, relpath),
        ).fetchone()["file_id"]
    )


def _seed_content(connection: sqlite3.Connection, sha: str) -> None:
    """Wstawia wiersz treści o podanym sha256."""
    db.upsert_content(connection, {"sha256": sha, "content_kind": "pdf"})


# --- schemat -----------------------------------------------------------------


def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    first = db.connect(path)
    first.close()
    second = db.connect(path)

    versions = [row["version"] for row in second.execute("SELECT version FROM schema_version")]
    second.close()

    assert versions == [db.SCHEMA_VERSION]


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    connection = db.connect(path)
    with connection:
        connection.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (db.SCHEMA_VERSION + 1, db.now_iso()),
        )
    connection.close()

    with pytest.raises(RuntimeError, match="schema_version"):
        db.connect(path)


def test_table_counts_lists_all_data_tables(conn: sqlite3.Connection) -> None:
    counts = db.table_counts(conn)

    # Liczba wynika z `TABLES`, a nie z przepisanej ręcznie stałej: nowa tabela ma
    # dopisać się tutaj sama, a pilnuje tego test porównujący TABLES ze schematem.
    assert len(counts) == len(db.TABLES)
    assert set(counts) == set(db.TABLES)
    assert set(counts.values()) == {0}


def test_tables_match_real_schema(conn: sqlite3.Connection) -> None:
    """Nowa tabela schematu musi trafić do TABLES, inaczej statystyki ją przemilczą."""
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    # sqlite_sequence jest wewnętrzną tabelą SQLite dla AUTOINCREMENT.
    assert tables - {"schema_version", "sqlite_sequence"} == set(db.TABLES)


def test_foreign_keys_are_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_file(
            conn,
            {
                "source_package": "brak-takiej-paczki",
                "source_relative_path": "x.pdf",
                "folder_path": "brak-takiej-paczki",
                "size_bytes": 1,
            },
        )


# --- UPSERT-y ----------------------------------------------------------------


def test_upsert_file_is_idempotent_and_updates_size(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    _seed_file(conn, relpath="a.pdf", size_bytes=10)
    _seed_file(conn, relpath="a.pdf", size_bytes=99)

    rows = conn.execute("SELECT size_bytes FROM files").fetchall()

    assert len(rows) == 1
    assert rows[0]["size_bytes"] == 99


def test_upsert_file_without_status_does_not_rewind(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn)
    db.advance_status(conn, file_id, "hashed")

    _seed_file(conn, size_bytes=42)

    assert db._file_status(conn, file_id) == "hashed"


def test_upsert_rejects_bad_identifiers(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        db.upsert(conn, "files; DROP TABLE files", {"sha256": "x"}, conflict=("sha256",))
    with pytest.raises(ValueError):
        db.upsert(conn, "content", {"sha256": "x"}, conflict=("nie_ma_takiej",))


def test_upsert_many_handles_mixed_column_sets(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    rows = [
        {
            "source_package": "P1",
            "source_relative_path": "a.pdf",
            "folder_path": "P1",
            "size_bytes": 10,
        },
        {
            "source_package": "P1",
            "source_relative_path": "b.pdf",
            "folder_path": "P1",
            "size_bytes": 20,
            "extension": "pdf",
        },
    ]

    written = db.upsert_many(
        conn, "files", rows, conflict=("source_package", "source_relative_path")
    )

    stored = {
        row["source_relative_path"]: row
        for row in conn.execute("SELECT * FROM files ORDER BY source_relative_path")
    }
    assert written == 2
    assert stored["a.pdf"]["extension"] is None
    assert stored["b.pdf"]["extension"] == "pdf"
    assert stored["b.pdf"]["size_bytes"] == 20


def test_upsert_many_updates_existing_rows(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    _seed_file(conn, relpath="a.pdf", size_bytes=10)

    db.upsert_many(
        conn,
        "files",
        # kolumny NOT NULL (folder_path) muszą być w wierszu — INSERT sprawdza je
        # zanim dojdzie do rozstrzygnięcia konfliktu
        [
            {
                "source_package": "P1",
                "source_relative_path": "a.pdf",
                "folder_path": "P1",
                "size_bytes": 99,
            }
        ],
        conflict=("source_package", "source_relative_path"),
    )

    rows = conn.execute("SELECT size_bytes FROM files").fetchall()
    assert [row["size_bytes"] for row in rows] == [99]


def test_upsert_many_of_nothing_writes_nothing(conn: sqlite3.Connection) -> None:
    assert db.upsert_many(conn, "files", [], conflict=("source_package",)) == 0


def test_upsert_many_is_atomic(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    rows = [
        {
            "source_package": "P1",
            "source_relative_path": "dobry.pdf",
            "folder_path": "P1",
            "size_bytes": 10,
        },
        # brak size_bytes (NOT NULL) — ten wiersz wywali cały wsad
        {"source_package": "P1", "source_relative_path": "zly.pdf", "folder_path": "P1"},
    ]

    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_many(conn, "files", rows, conflict=("source_package", "source_relative_path"))

    assert conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 0


def test_upsert_many_unknown_column_rolls_back_whole_batch(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    rows = [
        {
            "source_package": "P1",
            "source_relative_path": "a.pdf",
            "folder_path": "P1",
            "size_bytes": 10,
        },
        {"source_package": "P1", "source_relative_path": "b.pdf", "nie_ma_takiej": 1},
    ]

    with pytest.raises(sqlite3.OperationalError):
        db.upsert_many(conn, "files", rows, conflict=("source_package", "source_relative_path"))

    assert conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 0


def test_relations_reject_self_reference(conn: sqlite3.Connection) -> None:
    _seed_content(conn, "a" * 64)

    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_relation(
            conn,
            {
                "source_sha256": "a" * 64,
                "target_sha256": "a" * 64,
                "relation_type": "near_duplicate",
            },
        )


def test_plan_items_allow_many_targets_per_content(conn: sqlite3.Connection) -> None:
    _seed_content(conn, "b" * 64)
    for target in ("paczka/SEM3/AKO_x/a.pdf", "paczka/SEM4/SI_y/a.pdf"):
        db.upsert_plan_item(
            conn,
            {
                "sha256": "b" * 64,
                "target_relative_path": target,
                "action": "copy",
                "plan_run_id": "run-1",
            },
        )

    assert conn.execute("SELECT COUNT(*) AS n FROM plan_items").fetchone()["n"] == 2


def test_record_applied_keys_on_target_path(conn: sqlite3.Connection) -> None:
    _seed_content(conn, "c" * 64)
    row = {
        "target_relative_path": "paczka/SEM3/AKO_x/a.pdf",
        "sha256": "c" * 64,
        "action": "copy",
        "plan_hash": "h1",
        "applied_at": db.now_iso(),
    }
    db.record_applied(conn, row)
    db.record_applied(conn, {**row, "plan_hash": "h2"})

    rows = conn.execute("SELECT plan_hash FROM applied").fetchall()

    assert [r["plan_hash"] for r in rows] == ["h2"]


# --- maszyna stanów ----------------------------------------------------------


def test_advance_status_moves_forward(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn)

    db.advance_status(conn, file_id, "hashed")
    db.advance_status(conn, file_id, "classified")  # skok o kilka kroków jest OK

    assert db._file_status(conn, file_id) == "classified"


def test_advance_status_rejects_unknown_status(conn: sqlite3.Connection) -> None:
    """Literówka ma dawać diagnozę nieznanego statusu, nie błąd wyszukiwania w krotce."""
    _seed_package(conn)
    file_id = _seed_file(conn)

    with pytest.raises(ValueError, match="nieznany status 'hased'"):
        db.advance_status(conn, file_id, "hased")

    assert db._file_status(conn, file_id) == "discovered"


def test_reset_error_rejects_unknown_status(conn: sqlite3.Connection) -> None:
    """Nieznany cel resetu ma być odrzucony przed zapisem i zachować diagnozę błędu."""
    _seed_package(conn)
    file_id = _seed_file(conn, status="error", error_message="boom")

    with pytest.raises(ValueError, match="nieznany status docelowy 'nieistniejacy'"):
        db.reset_error(conn, file_id, "nieistniejacy")

    row = conn.execute(
        "SELECT status, error_message FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    assert (row["status"], row["error_message"]) == ("error", "boom")


def test_advance_status_rejects_backwards_and_same(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn)
    db.advance_status(conn, file_id, "extracted")

    with pytest.raises(ValueError, match="cofnięcie"):
        db.advance_status(conn, file_id, "hashed")
    with pytest.raises(ValueError, match="ten sam status|już wynosi"):
        db.advance_status(conn, file_id, "extracted")


@pytest.mark.parametrize("start", db.FILE_STATUSES)
def test_error_reachable_from_every_status(conn: sqlite3.Connection, start: str) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn, relpath=f"{start}.pdf", status=start)

    db.advance_status(conn, file_id, db.ERROR_STATUS)

    assert db._file_status(conn, file_id) == db.ERROR_STATUS


def test_error_is_left_only_through_reset_error(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn, status=db.ERROR_STATUS, error_message="boom")

    with pytest.raises(ValueError, match="reset_error"):
        db.advance_status(conn, file_id, "hashed")

    db.reset_error(conn, file_id, "discovered")
    row = conn.execute("SELECT status, error_message FROM files WHERE file_id = ?", (file_id,)).fetchone()

    assert row["status"] == "discovered"
    assert row["error_message"] is None


def test_reset_error_refuses_healthy_file(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    file_id = _seed_file(conn)

    with pytest.raises(ValueError, match="nie jest w stanie 'error'"):
        db.reset_error(conn, file_id, "hashed")


# --- kolejki etapów ----------------------------------------------------------


def _seed_duplicate_tree(connection: sqlite3.Connection) -> None:
    """Paczka z katalogiem-duplikatem, jego podkatalogiem i katalogami niezależnymi."""
    _seed_package(connection)
    for folder, duplicate_of in (
        ("P1/orig", None),
        ("P1/dup", "P1/orig"),
        ("P1/dup/sub", None),
        ("P1/other", None),
        ("P1/dup_x", None),  # nazwa z '_' tuż po prefiksie duplikatu
    ):
        db.upsert_folder(
            connection,
            {"folder_path": folder, "source_package": "P1", "duplicate_of": duplicate_of},
        )
    for folder in ("orig", "dup", "dup/sub", "other", "dup_x"):
        _seed_file(connection, relpath=f"{folder}/f.pdf", status="hashed")


def test_files_pending_hash_returns_discovered(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    _seed_file(conn, relpath="a.pdf")
    hashed_id = _seed_file(conn, relpath="b.pdf")
    db.advance_status(conn, hashed_id, "hashed")

    pending = db.files_pending(conn, "hash")

    assert [row["source_relative_path"] for row in pending] == ["a.pdf"]


def test_files_pending_hash_ignores_duplicate_folders(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    db.upsert_folder(conn, {"folder_path": "P1/orig", "source_package": "P1"})
    db.upsert_folder(
        conn, {"folder_path": "P1/dup", "source_package": "P1", "duplicate_of": "P1/orig"}
    )
    _seed_file(conn, relpath="dup/f.pdf")

    assert len(db.files_pending(conn, "hash")) == 1


def test_files_pending_extract_skips_duplicate_subtrees(conn: sqlite3.Connection) -> None:
    _seed_duplicate_tree(conn)

    folders = {row["folder_path"] for row in db.files_pending(conn, "extract")}

    assert folders == {"P1/orig", "P1/other", "P1/dup_x"}


def test_files_pending_filters_and_limits(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1")
    _seed_package(conn, "P2")
    _seed_file(conn, package="P1", relpath="a.pdf")
    _seed_file(conn, package="P2", relpath="b.pdf")

    assert len(db.files_pending(conn, "hash", source_package="P2")) == 1
    assert len(db.files_pending(conn, "hash", limit=1)) == 1


def test_files_pending_rejects_unknown_stage(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="nieznany etap"):
        db.files_pending(conn, "scan")


def test_file_status_counts_covers_all_statuses(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    _seed_file(conn)

    counts = db.file_status_counts(conn)

    assert counts["discovered"] == 1
    assert counts["verified"] == 0
    assert set(counts) == set(db.FILE_STATUSES) | {db.ERROR_STATUS}


# --- eksport / import ręcznych decyzji ---------------------------------------


def test_manual_decisions_roundtrip(conn: sqlite3.Connection, tmp_path: Path) -> None:
    rows = [
        {
            "sha256": "d" * 64,
            "decision_type": "outdated",
            "target_relative_path": "paczka/SEM3/AKO_x/outdated/a.pdf",
            "relation_override": None,
            "decided_by": "billy",
            "decided_at": db.now_iso(),
            "note": "starsza wersja wykładu — zażółć gęślą jaźń",
        },
        {
            "sha256": "e" * 64,
            "decision_type": "classify",
            "target_relative_path": "paczka/SEM4/SI_y/wyklady/b.pdf",
            "relation_override": None,
            "decided_by": "billy",
            "decided_at": db.now_iso(),
            "note": None,
        },
    ]
    for row in reversed(rows):
        db.upsert_manual_decision(conn, row)

    out = tmp_path / "reports" / "manual_decisions.jsonl"
    assert db.export_manual_decisions(conn, out) == 2

    lines = out.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["sha256"] for line in lines] == ["d" * 64, "e" * 64]
    assert "zażółć" in lines[0]

    fresh = db.connect(tmp_path / "fresh.sqlite")
    try:
        assert db.import_manual_decisions(fresh, out) == 2
        imported = [dict(r) for r in fresh.execute("SELECT * FROM manual_decisions ORDER BY sha256")]
    finally:
        fresh.close()
    original = [dict(r) for r in conn.execute("SELECT * FROM manual_decisions ORDER BY sha256")]

    assert imported == original


# --- CLI ---------------------------------------------------------------------


runner = CliRunner()


def test_cli_init_creates_database(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"

    result = runner.invoke(db_admin.app, ["init", "--db", str(path)])

    assert result.exit_code == 0, result.output
    assert path.exists()
    assert f"schema_version: {db.SCHEMA_VERSION}" in result.output


def test_cli_stats_prints_all_tables(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(path)])

    result = runner.invoke(db_admin.app, ["stats", "--db", str(path)])

    assert result.exit_code == 0, result.output
    for table in db.TABLES:
        assert table in result.output


def test_cli_reset_requires_yes(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(path)])
    before = path.stat().st_mtime_ns

    result = runner.invoke(db_admin.app, ["reset", "--db", str(path)])

    assert result.exit_code != 0
    assert path.exists()
    assert path.stat().st_mtime_ns == before
    assert not list(tmp_path.glob("*.bak-*"))


def test_cli_reset_backs_up_instead_of_deleting(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(path)])
    connection = db.connect(path)
    _seed_package(connection)
    connection.close()

    result = runner.invoke(db_admin.app, ["reset", "--db", str(path), "--yes"])

    assert result.exit_code == 0, result.output
    backups = list(tmp_path.glob("organizer.sqlite.bak-*"))
    assert len(backups) >= 1
    assert path.exists()

    fresh = db.connect(path, init=False)
    try:
        assert db.table_counts(fresh)["source_packages"] == 0
    finally:
        fresh.close()

    old = db.connect(backups[0], init=False)
    try:
        assert db.table_counts(old)["source_packages"] == 1
    finally:
        old.close()


def test_cli_export_and_import_manual(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(path)])
    connection = db.connect(path)
    db.upsert_manual_decision(
        connection,
        {
            "sha256": "f" * 64,
            "decision_type": "skip",
            "decided_by": "billy",
            "decided_at": db.now_iso(),
        },
    )
    connection.close()
    jsonl = tmp_path / "manual.jsonl"

    export = runner.invoke(db_admin.app, ["export-manual", "--db", str(path), "--out", str(jsonl)])
    target = tmp_path / "other.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(target)])
    imp = runner.invoke(db_admin.app, ["import-manual", "--db", str(target), "--in", str(jsonl)])

    assert export.exit_code == 0, export.output
    assert imp.exit_code == 0, imp.output
    assert "wczytane decyzje: 1" in imp.output


# --- konwencja ścieżek, twardość init i CLI na brakujących plikach ------------


def test_folder_path_for_root_and_nested() -> None:
    assert db.folder_path_for("P1", "a.pdf") == "P1"
    assert db.folder_path_for("P1", "sem3/AK/w1.pdf") == "P1/sem3/AK"
    assert db.folder_path_for("P1", "/sem3/w1.pdf") == "P1/sem3"

    with pytest.raises(ValueError):
        db.folder_path_for("P1", "")
    with pytest.raises(ValueError):
        db.folder_path_for("", "a.pdf")


def test_seeded_folder_path_matches_helper(conn: sqlite3.Connection) -> None:
    _seed_package(conn)
    db.upsert_folder(conn, {"folder_path": "P1/sem3", "source_package": "P1"})
    _seed_file(conn, relpath="sem3/w1.pdf")

    row = conn.execute("SELECT folder_path FROM files").fetchone()

    assert row["folder_path"] == "P1/sem3"


def test_newer_schema_version_leaves_database_untouched(tmp_path: Path) -> None:
    path = tmp_path / "przyszla.sqlite"
    future = db.SCHEMA_VERSION + 1
    raw = sqlite3.connect(path)
    with raw:
        raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
        raw.execute("INSERT INTO schema_version VALUES (?, '2026-01-01T00:00:00Z')", (future,))
    raw.close()

    with pytest.raises(RuntimeError, match=f"schema_version={future}"):
        db.connect(path)

    raw = sqlite3.connect(path)
    tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    raw.close()

    assert tables == {"schema_version"}


def test_connect_closes_connection_when_init_fails(tmp_path: Path, monkeypatch) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)  # type: ignore[arg-type]
        opened.append(connection)
        return connection

    def boom(_conn: sqlite3.Connection) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(db.sqlite3, "connect", spy)
    monkeypatch.setattr(db, "init_schema", boom)

    with pytest.raises(RuntimeError, match="boom"):
        db.connect(tmp_path / "x.sqlite")

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_cli_stats_refuses_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "nie-ma.sqlite"

    result = runner.invoke(db_admin.app, ["stats", "--db", str(path)])

    assert result.exit_code == 1
    assert not path.exists()


def test_cli_export_manual_refuses_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "nie-ma.sqlite"

    result = runner.invoke(
        db_admin.app, ["export-manual", "--db", str(path), "--out", str(tmp_path / "o.jsonl")]
    )

    assert result.exit_code == 1
    assert not path.exists()
    assert not (tmp_path / "o.jsonl").exists()


def test_cli_import_manual_refuses_missing_input(tmp_path: Path) -> None:
    path = tmp_path / "organizer.sqlite"
    runner.invoke(db_admin.app, ["init", "--db", str(path)])

    result = runner.invoke(
        db_admin.app, ["import-manual", "--db", str(path), "--in", str(tmp_path / "brak.jsonl")]
    )

    assert result.exit_code == 1


def test_cli_import_manual_refuses_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "nie-ma.sqlite"
    jsonl = tmp_path / "manual.jsonl"
    jsonl.write_text("", encoding="utf-8")

    result = runner.invoke(db_admin.app, ["import-manual", "--db", str(path), "--in", str(jsonl)])

    assert result.exit_code == 1
    assert not path.exists()


def test_cli_init_refuses_non_sqlite_file(tmp_path: Path) -> None:
    path = tmp_path / "to-nie-baza.sqlite"
    path.write_bytes(b"to na pewno nie jest baza sqlite" * 10)

    result = runner.invoke(db_admin.app, ["init", "--db", str(path)])

    assert result.exit_code == 1
    assert "nie jest poprawna baza" in result.output
