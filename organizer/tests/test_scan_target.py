"""Testy `scripts/scan_target.py`: ground truth istniejącej paczka/ w repo produktu.

Repo produktu żyje wyłącznie w tmp_path — testy nigdy nie dotykają prawdziwego
10_NEW/PaczkaInfaPG. `config/subjects.yaml` jest PRAWDZIWY (nie mockowany),
więc testy sprawdzają realne aliasy (AKO -> AK) i realne kolizje skrótów.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

import scan_target
from orglib import config, db

runner = CliRunner()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.fixture()
def subjects() -> list[config.Subject]:
    """Prawdziwy katalog przedmiotów z config/subjects.yaml (bez mocków)."""
    return config.iter_subjects()


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """Sztuczne repo produktu: kilka przedmiotów, oba nazewnictwa, śmieci."""
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka"

    (paczka / "SEM3" / "AKO_Architektura_Komputerów" / "wykład").mkdir(parents=True)
    (paczka / "SEM2" / "(PO)_Programowanie_Obiektowe" / "laboratoria").mkdir(parents=True)
    (paczka / "SEM3" / "XYZ_Nieznany").mkdir(parents=True)
    (paczka / "SEM1" / "sources").mkdir(parents=True)
    (paczka / "SEM4" / "SI_Sztuczna_Inteligencja" / "outdated" / "wykład").mkdir(parents=True)

    (paczka / "SEM3" / "AKO_Architektura_Komputerów" / "wykład" / "a.pdf").write_bytes(b"aaa")
    (paczka / "SEM2" / "(PO)_Programowanie_Obiektowe" / "laboratoria" / "b.txt").write_bytes(
        b"bb"
    )
    (paczka / "SEM3" / "XYZ_Nieznany" / "c.pdf").write_bytes(b"ccc")
    (paczka / "SEM1" / "sources" / "d.txt").write_bytes(b"d")
    (paczka / "SEM4" / "SI_Sztuczna_Inteligencja" / "outdated" / "wykład" / "e.pdf").write_bytes(
        b"eeeee"
    )
    (paczka / ".gitkeep").write_bytes(b"")
    (paczka / "Thumbs.db").write_bytes(b"x")
    return root


@pytest.fixture()
def conn(tmp_path: Path):
    """Świeża baza w tmp_path z założonym schematem."""
    connection = db.connect(tmp_path / "organizer.sqlite")
    yield connection
    connection.close()


def _applied(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = connection.execute("SELECT * FROM applied").fetchall()
    return {str(row["target_relative_path"]): row for row in rows}


def _classifications(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = connection.execute("SELECT * FROM classifications").fetchall()
    return {str(row["sha256"]): row for row in rows}


# --- pierwszy skan ------------------------------------------------------------


def test_first_scan_records_content_applied_and_classification(conn, repo_root, subjects):
    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    assert stats.seen == 5
    assert stats.hashed == 5
    assert stats.errors == 0
    assert stats.classified == 3  # AKO(->AK), PO, SI
    assert stats.unmatched == 2  # XYZ_Nieznany (w zakresie), SEM1/sources (poza zakresem)
    assert stats.unmatched_folders == {(3, "XYZ_Nieznany")}
    assert stats.out_of_scope_folders == {(1, "sources")}

    applied = _applied(conn)
    assert set(applied) == {
        "paczka/SEM3/AKO_Architektura_Komputerów/wykład/a.pdf",
        "paczka/SEM2/(PO)_Programowanie_Obiektowe/laboratoria/b.txt",
        "paczka/SEM3/XYZ_Nieznany/c.pdf",
        "paczka/SEM1/sources/d.txt",
        "paczka/SEM4/SI_Sztuczna_Inteligencja/outdated/wykład/e.pdf",
    }
    a_row = applied["paczka/SEM3/AKO_Architektura_Komputerów/wykład/a.pdf"]
    assert a_row["sha256"] == _sha(b"aaa")
    assert a_row["action"] == "copy"
    assert a_row["plan_hash"].startswith("ground_truth:3:")
    assert a_row["applied_at"].endswith("Z")

    contents = {
        row["sha256"]: row["content_kind"]
        for row in conn.execute("SELECT sha256, content_kind FROM content").fetchall()
    }
    assert contents[_sha(b"aaa")] == "pdf"
    assert contents[_sha(b"bb")] == "text"

    classifications = _classifications(conn)
    ak = classifications[_sha(b"aaa")]
    assert (ak["semester"], ak["subject_key"], ak["category"]) == (3, "AK", "wykład")
    assert (ak["classification_method"], ak["confidence"], ak["run_id"]) == (
        "manual",
        1.0,
        "ground_truth",
    )
    assert ak["is_outdated"] == 0

    po = classifications[_sha(b"bb")]
    assert (po["semester"], po["subject_key"], po["category"]) == (2, "PO", "laboratoria")

    si = classifications[_sha(b"eeeee")]
    assert (si["semester"], si["subject_key"], si["category"]) == (4, "SI", "wykład")
    assert si["is_outdated"] == 1  # 'outdated' wykryte, category przesunięta na kolejny segment

    assert _sha(b"ccc") not in classifications  # XYZ_Nieznany
    assert _sha(b"d") not in classifications  # SEM1/sources


def test_junk_hidden_and_lock_files_are_skipped(conn, repo_root, subjects):
    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    assert stats.seen == 5  # .gitkeep i Thumbs.db się nie liczą


def test_classified_equals_ground_truth_row_count(conn, repo_root, subjects):
    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM classifications WHERE run_id = 'ground_truth'"
    ).fetchone()["n"]
    assert stats.classified == count


# --- dotpliki i dowiązania -----------------------------------------------------


def test_dotfiles_content_kept_but_git_and_markers_skipped(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka"
    (paczka / ".git").mkdir(parents=True)
    (paczka / ".git" / "config").write_bytes(b"git-internals")
    (paczka / ".gitkeep").write_bytes(b"")
    (paczka / ".DS_Store").write_bytes(b"macos-junk")
    (paczka / ".clang-format").write_bytes(b"BasedOnStyle: LLVM")

    stats = scan_target.scan_target(conn, root, "paczka", subjects)

    applied = _applied(conn)
    assert "paczka/.clang-format" in applied
    assert not any(path.startswith("paczka/.git/") for path in applied)
    assert "paczka/.gitkeep" not in applied
    assert "paczka/.DS_Store" not in applied
    assert stats.seen == 1
    assert stats.errors == 0


def test_symlinks_are_skipped(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka"
    real_dir = paczka / "real"
    real_dir.mkdir(parents=True)
    (real_dir / "real.txt").write_bytes(b"real-content")
    os.symlink(real_dir / "real.txt", paczka / "link.txt")
    os.symlink(real_dir, paczka / "linkdir")

    stats = scan_target.scan_target(conn, root, "paczka", subjects)

    applied = _applied(conn)
    assert set(applied) == {"paczka/real/real.txt"}
    assert stats.seen == 1


# --- wznawialność: TYLKO hash, klasyfikacja zawsze od nowa ---------------------


def test_rerun_without_changes_skips_only_hashing(conn, repo_root, subjects, monkeypatch):
    scan_target.scan_target(conn, repo_root, "paczka", subjects)

    def _boom(path: Path) -> str:
        raise AssertionError(f"sha256_file nie powinno być wołane dla {path}")

    monkeypatch.setattr(scan_target.hashes, "sha256_file", _boom)

    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    assert stats.skipped_unchanged == 5
    assert stats.hashed == 0
    assert len(stats.unique_content) == 5
    assert stats.classified == 3  # klasyfikacja liczona od nowa mimo braku hashowania


def test_changed_file_is_rehashed(conn, repo_root, subjects):
    scan_target.scan_target(conn, repo_root, "paczka", subjects)
    path = repo_root / "paczka" / "SEM3" / "AKO_Architektura_Komputerów" / "wykład" / "a.pdf"
    new_content = b"zmieniona-tresc"
    path.write_bytes(new_content)

    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    assert stats.hashed == 1
    assert stats.skipped_unchanged == 4
    row = _applied(conn)["paczka/SEM3/AKO_Architektura_Komputerów/wykład/a.pdf"]
    assert row["sha256"] == _sha(new_content)
    assert row["plan_hash"].startswith(f"ground_truth:{len(new_content)}:")


def test_existing_manual_classification_is_preserved(conn, repo_root, subjects):
    sha = _sha(b"aaa")
    db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
    db.upsert_classification(
        conn,
        {
            "sha256": sha,
            "semester": 3,
            "subject_key": "RECZNA-DECYZJA",
            "classification_method": "manual",
            "confidence": 1.0,
            "run_id": "review-2026-09-01",
            "decided_at": db.now_iso(),
        },
    )

    scan_target.scan_target(conn, repo_root, "paczka", subjects)

    row = _classifications(conn)[sha]
    assert row["subject_key"] == "RECZNA-DECYZJA"
    assert row["run_id"] == "review-2026-09-01"


def test_ai_classification_is_overwritten_by_ground_truth(conn, repo_root, subjects):
    sha = _sha(b"aaa")
    db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
    db.upsert_classification(
        conn,
        {
            "sha256": sha,
            "semester": 99,
            "subject_key": "AI-ZGADNIETE",
            "classification_method": "ai",
            "confidence": 0.8,
            "run_id": "ai-run-1",
            "decided_at": db.now_iso(),
        },
    )

    scan_target.scan_target(conn, repo_root, "paczka", subjects)

    row = _classifications(conn)[sha]
    assert row["subject_key"] == "AK"
    assert row["classification_method"] == "manual"
    assert row["run_id"] == "ground_truth"


def test_unmatched_folder_is_classified_after_subject_is_added(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka"
    (paczka / "SEM3" / "ZZZ_Nowy_Przedmiot" / "wyklad").mkdir(parents=True)
    (paczka / "SEM3" / "ZZZ_Nowy_Przedmiot" / "wyklad" / "plik.pdf").write_bytes(b"nowy")

    stats1 = scan_target.scan_target(conn, root, "paczka", subjects)
    assert stats1.unmatched == 1
    assert stats1.unmatched_folders == {(3, "ZZZ_Nowy_Przedmiot/wyklad")}
    assert stats1.classified == 0

    subjects_z_dopiskiem = list(subjects) + [
        config.Subject(
            semester=3,
            skrot="ZZZ",
            nazwa="Nowy_Przedmiot",
            forms=(),
            aliases=(),
            instancja=None,
            strumien=None,
            profil=None,
        )
    ]

    stats2 = scan_target.scan_target(conn, root, "paczka", subjects_z_dopiskiem)

    assert stats2.hashed == 0  # plik bez zmian — resume gate dotyczy TYLKO hashowania
    assert stats2.classified == 1
    row = _classifications(conn)[_sha(b"nowy")]
    assert row["subject_key"] == "ZZZ"


# --- katalog przedmiotu leżący głębiej (strumień/profil pomiędzy) --------------


def test_subject_dir_one_level_below_stream_folder(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka" / "SEM5" / "Systemy" / "SBD_Struktury_Baz_Danych" / "wyklad"
    paczka.mkdir(parents=True)
    (paczka / "f.pdf").write_bytes(b"struktury")

    stats = scan_target.scan_target(conn, root, "paczka", subjects)

    assert stats.classified == 1
    row = _classifications(conn)[_sha(b"struktury")]
    assert (row["semester"], row["subject_key"], row["category"]) == (5, "SBD", "wyklad")


def test_subject_dir_two_levels_below_intermediate_folders(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    # "Systemy" nie pasuje do wzorca (brak '_'); "KAIMS_..." pasuje, ale KAIMS to nie
    # istniejący skrót w subjects.yaml — oba mają być pominięte (max. 2 pominięcia).
    paczka = (
        root
        / "paczka"
        / "SEM7"
        / "Systemy"
        / "KAIMS_Nieprawdziwy_Profil"
        / "PGK_Projektowanie_Gier_Komputerowych"
        / "wyklad"
    )
    paczka.mkdir(parents=True)
    (paczka / "g.pdf").write_bytes(b"gry")

    stats = scan_target.scan_target(conn, root, "paczka", subjects)

    assert stats.classified == 1
    row = _classifications(conn)[_sha(b"gry")]
    assert (row["semester"], row["subject_key"], row["category"]) == (7, "PGK", "wyklad")


# --- ta sama treść pod kilkoma ścieżkami docelowymi ----------------------------


def test_content_under_multiple_paths_uses_smallest_path_deterministically(
    tmp_path: Path, conn, subjects
):
    root = tmp_path / "PaczkaInfaPG"
    paczka = root / "paczka"
    sem2_dir = paczka / "SEM2" / "AISD_Algorytmy_I_Struktury_Danych" / "wyklad"
    sem3_dir = paczka / "SEM3" / "JP_Języki_Programowania" / "wyklad"
    sem2_dir.mkdir(parents=True)
    sem3_dir.mkdir(parents=True)
    (sem2_dir / "x.pdf").write_bytes(b"wspolna-tresc")
    (sem3_dir / "x.pdf").write_bytes(b"wspolna-tresc")

    stats1 = scan_target.scan_target(conn, root, "paczka", subjects)
    assert stats1.multi_path_content == 1
    sha = _sha(b"wspolna-tresc")
    row1 = _classifications(conn)[sha]
    assert row1["subject_key"] == "AISD"
    assert row1["target_relative_path"] == "paczka/SEM2/AISD_Algorytmy_I_Struktury_Danych/wyklad/x.pdf"

    future = time.time() + 100
    os.utime(sem2_dir / "x.pdf", (future, future))

    stats2 = scan_target.scan_target(conn, root, "paczka", subjects)
    assert stats2.hashed == 1  # tylko "dotknięta" kopia SEM2 (ta sama treść)
    row2 = _classifications(conn)[sha]
    assert row2["subject_key"] == row1["subject_key"]
    assert row2["target_relative_path"] == row1["target_relative_path"]


# --- --limit stosowany PO filtrze resume ---------------------------------------


def test_limit_applies_after_resume_filter_and_advances_across_runs(tmp_path: Path, conn, subjects):
    root = tmp_path / "PaczkaInfaPG"
    folder = root / "paczka" / "SEM1" / "AL_Algebra_Liniowa"
    folder.mkdir(parents=True)
    (folder / "a.pdf").write_bytes(b"a")
    (folder / "b.pdf").write_bytes(b"bb")
    (folder / "c.pdf").write_bytes(b"ccc")

    stats1 = scan_target.scan_target(conn, root, "paczka", subjects, limit=1)
    assert stats1.hashed == 1
    assert set(_applied(conn)) == {"paczka/SEM1/AL_Algebra_Liniowa/a.pdf"}

    stats2 = scan_target.scan_target(conn, root, "paczka", subjects, limit=1)
    assert stats2.hashed == 1
    assert set(_applied(conn)) == {
        "paczka/SEM1/AL_Algebra_Liniowa/a.pdf",
        "paczka/SEM1/AL_Algebra_Liniowa/b.pdf",
    }

    stats3 = scan_target.scan_target(conn, root, "paczka", subjects, limit=1)
    assert stats3.hashed == 1
    assert set(_applied(conn)) == {
        "paczka/SEM1/AL_Algebra_Liniowa/a.pdf",
        "paczka/SEM1/AL_Algebra_Liniowa/b.pdf",
        "paczka/SEM1/AL_Algebra_Liniowa/c.pdf",
    }


# --- wsad na granicy batcha -----------------------------------------------------


def test_batch_boundary_does_not_lose_rows(conn, repo_root, subjects):
    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects, batch=2)

    assert stats.hashed == 5
    assert stats.classified == 3
    assert len(_applied(conn)) == 5


# --- bajty: wszystkie widziane vs faktycznie zahashowane -----------------------


def test_bytes_total_counts_all_seen_bytes_hashed_only_new_or_changed(conn, repo_root, subjects):
    stats1 = scan_target.scan_target(conn, repo_root, "paczka", subjects)
    assert stats1.bytes_total == stats1.bytes_hashed  # pierwszy przebieg: wszystko nowe
    total_bytes = stats1.bytes_total
    assert total_bytes == len(b"aaa") + len(b"bb") + len(b"ccc") + len(b"d") + len(b"eeeee")

    stats2 = scan_target.scan_target(conn, repo_root, "paczka", subjects)
    assert stats2.bytes_total == total_bytes  # nadal liczymy WSZYSTKIE widziane bajty
    assert stats2.bytes_hashed == 0  # ale nic nie hashujemy drugi raz


# --- usuwanie nieaktualnych wpisów ground truth --------------------------------


def test_stale_ground_truth_row_removed_when_file_moved(conn, repo_root, subjects):
    scan_target.scan_target(conn, repo_root, "paczka", subjects)
    old_path = repo_root / "paczka" / "SEM3" / "AKO_Architektura_Komputerów" / "wykład" / "a.pdf"
    new_dir = repo_root / "paczka" / "SEM3" / "AKO_Architektura_Komputerów" / "cwiczenia"
    new_dir.mkdir(parents=True)
    old_path.rename(new_dir / "a.pdf")

    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects)

    assert stats.stale_removed == 1
    applied = _applied(conn)
    assert "paczka/SEM3/AKO_Architektura_Komputerów/wykład/a.pdf" not in applied
    assert "paczka/SEM3/AKO_Architektura_Komputerów/cwiczenia/a.pdf" in applied
    row = _classifications(conn)[_sha(b"aaa")]
    assert row["target_relative_path"] == "paczka/SEM3/AKO_Architektura_Komputerów/cwiczenia/a.pdf"
    assert row["category"] == "cwiczenia"
    assert stats.multi_path_content == 0  # stara ścieżka nie zdążyła "podwoić" treści


def test_stale_rows_are_not_touched_when_limit_is_set(conn, repo_root, subjects):
    scan_target.scan_target(conn, repo_root, "paczka", subjects)
    old_path = repo_root / "paczka" / "SEM3" / "AKO_Architektura_Komputerów" / "wykład" / "a.pdf"
    old_path.unlink()

    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects, limit=1)

    assert stats.stale_removed == 0
    assert "paczka/SEM3/AKO_Architektura_Komputerów/wykład/a.pdf" in _applied(conn)


# --- zwycięska ścieżka spoza paczka/ (dane niespójne w bazie) ------------------


def test_winner_path_outside_paczka_subdir_is_skipped_not_raised(conn, repo_root, subjects):
    sha = _sha(b"bb")
    db.upsert_content(conn, {"sha256": sha, "content_kind": "text"})
    db.record_applied(
        conn,
        {
            "target_relative_path": "aaa_spoza_paczki/b.txt",
            "sha256": sha,
            "action": "copy",
            "plan_hash": "ground_truth:2:1",
            "applied_at": db.now_iso(),
        },
    )

    stats = scan_target.scan_target(conn, repo_root, "paczka", subjects, limit=100)

    assert stats.errors >= 1
    assert sha not in _classifications(conn)


# --- CLI -------------------------------------------------------------------------


def test_cli_help() -> None:
    result = runner.invoke(scan_target.app, ["--help"])

    assert result.exit_code == 0
    assert "paczka" in result.output.lower()


def test_cli_refuses_missing_paczka_dir(tmp_path: Path) -> None:
    database = tmp_path / "organizer.sqlite"
    db.connect(database).close()

    result = runner.invoke(
        scan_target.app,
        ["--db", str(database), "--target-repo", str(tmp_path / "nie-ma")],
    )

    assert result.exit_code == 1


def test_cli_refuses_missing_db(tmp_path: Path, repo_root: Path) -> None:
    result = runner.invoke(
        scan_target.app,
        ["--db", str(tmp_path / "brak.sqlite"), "--target-repo", str(repo_root)],
    )

    assert result.exit_code == 1


def test_cli_limit_restricts_processed_files_on_fresh_db(tmp_path: Path, repo_root: Path) -> None:
    database = tmp_path / "organizer.sqlite"
    db.connect(database).close()

    result = runner.invoke(
        scan_target.app,
        ["--db", str(database), "--target-repo", str(repo_root), "--limit", "2"],
    )

    assert result.exit_code == 0, result.output
    connection = db.connect(database, init=False)
    try:
        rows = connection.execute("SELECT target_relative_path FROM applied").fetchall()
        paths = {row["target_relative_path"] for row in rows}
    finally:
        connection.close()
    # kolejność deterministyczna (sort po target_relative_path): SEM1 i SEM2 pierwsze.
    assert paths == {
        "paczka/SEM1/sources/d.txt",
        "paczka/SEM2/(PO)_Programowanie_Obiektowe/laboratoria/b.txt",
    }


def test_cli_exits_3_on_hashing_errors(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "organizer.sqlite"
    db.connect(database).close()

    def _boom(path: Path) -> str:
        raise OSError(f"symulowany błąd odczytu {path}")

    monkeypatch.setattr(scan_target.hashes, "sha256_file", _boom)

    result = runner.invoke(
        scan_target.app,
        ["--db", str(database), "--target-repo", str(repo_root)],
    )

    assert result.exit_code == 3, result.output
