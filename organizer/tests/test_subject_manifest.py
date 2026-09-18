"""B1: testy tylko na syntetycznym indeksie, bez dostępu do materiałów."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from orglib import config, db
from orglib.subject_manifest import build_manifest

A = "a" * 64
B = "b" * 64


def add_file(conn, path, sha=A, status="hashed", size=10, content=True):
    package, relative = path.split("/", 1)
    db.upsert(conn, "source_packages", {"package_name": package}, conflict=("package_name",))
    parent = db.folder_path_for(package, relative)
    for folder in reversed([PurePosixPath(parent), *PurePosixPath(parent).parents]):
        if str(folder) != ".":
            db.upsert_folder(conn, {"folder_path": str(folder), "source_package": package})
    db.upsert_file(conn, {
        "source_package": package, "source_relative_path": relative,
        "folder_path": parent, "filename": PurePosixPath(relative).name,
        "sha256": sha, "size_bytes": size, "status": status,
    })
    if content and sha is not None:
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "index.sqlite")
    yield connection
    connection.close()


@pytest.fixture
def subjects():
    return config.iter_subjects()


def manifest(conn, subjects, semester=3, skrot="AKO", grupa=None):
    subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
    return build_manifest(conn, subject, subjects)


@pytest.mark.parametrize("path", [
    "P/SEM3/AK/a.pdf",
    "P/sem_3/ako/a.pdf",
    "P/semestr 3/Architektura Komputerow/a.pdf",
    "P/semestr III/ARCHITEKTURA_KOMPUTERÓW/a.pdf",
    "P/semester-3/deep/AKO2020/a.pdf",
    "P/SEM3/deep/AK_2020_wyklad.pdf",
    "AKO2021/SEM3/a.pdf",
])
def test_aliases_names_and_arbitrary_depth(conn, subjects, path):
    add_file(conn, path)
    rows = manifest(conn, subjects)
    assert len(rows) == 1
    assert rows[0]["source_paths"] == [path]
    assert rows[0]["source_path"] == path
    assert rows[0]["subject_key"] == "AKO"
    assert rows[0]["needs_review"] is False
    assert rows[0]["sha256"] == rows[0]["source_sha256"] == A


@pytest.mark.parametrize("path", [
    "P/SEM7/AK/a.pdf", "P/SEM30/AK/a.pdf",
    "P/SEM3/PAK/a.pdf", "P/SEM3/AKOW/a.pdf", "P/SEM3/backup.txt",
    "P/Magisterskie_SEM3/AK/a.pdf",
])
def test_does_not_guess_other_semester_or_substring(conn, subjects, path):
    add_file(conn, path)
    assert manifest(conn, subjects) == []


def test_missing_semester_and_conflicting_semesters_need_review(conn, subjects):
    add_file(conn, "P/AK/a.pdf")
    add_file(conn, "P/SEM3/SEM7/AK/b.pdf", B)
    rows = manifest(conn, subjects)
    assert len(rows) == 2
    assert "missing_semester" in rows[0]["review_reasons"]
    assert "conflicting_semesters" in rows[1]["review_reasons"]
    assert all(row["needs_review"] for row in rows)


def test_alias_collision_across_semesters_is_not_resolved_by_canonical_priority(conn, subjects):
    add_file(conn, "P/JAI/a.pdf")
    assert manifest(conn, subjects, 3, "JAII")[0]["needs_review"]
    assert manifest(conn, subjects, 2, "JAI")[0]["needs_review"]
    add_file(conn, "P/SEM3/JAI/b.pdf", B)
    assert not manifest(conn, subjects, 3, "JAII")[1]["needs_review"]
    assert len(manifest(conn, subjects, 2, "JAI")) == 1


def test_canonical_shortcut_over_alias_within_semester(conn, subjects):
    ako = config.find_subject(3, "AKO", subjects)
    other = replace(ako, skrot="OTHER", nazwa="Inny_Przedmiot", aliases=("AKO",))
    pool = [ako, other]
    add_file(conn, "P/SEM3/AKO/a.pdf")
    assert len(build_manifest(conn, ako, pool)) == 1
    assert build_manifest(conn, other, pool) == []


def test_same_alias_within_semester_needs_review(conn, subjects):
    ako = config.find_subject(3, "AKO", subjects)
    other = replace(ako, skrot="OTHER", nazwa="Inny_Przedmiot", aliases=("AK",))
    add_file(conn, "P/SEM3/AK/a.pdf")
    assert build_manifest(conn, ako, [ako, other])[0]["needs_review"]


def test_groups_and_full_name_resolve_sem7_si(conn, subjects):
    kask = "KASK_Architektura_Systemów_Komputerowych"
    kt = "KT_Teleinformatyka"
    add_file(conn, f"SRC/SEM7/{kask}/SI/a.pdf")
    add_file(conn, "SRC/SEM7/KT/SI/b.pdf", B)
    assert [r["sha256"] for r in manifest(conn, subjects, 7, "SI", kask)] == [A]
    assert [r["sha256"] for r in manifest(conn, subjects, 7, "SI", kt)] == [B]
    assert not manifest(conn, subjects, 7, "SI", kask)[0]["needs_review"]


def test_missing_group_is_review_not_guess(conn, subjects):
    add_file(conn, "SRC/SEM7/SI/a.pdf")
    for group in ("KASK_Architektura_Systemów_Komputerowych", "KT_Teleinformatyka"):
        row = manifest(conn, subjects, 7, "SI", group)[0]
        assert "ambiguous_subject" in row["review_reasons"]


def test_full_name_has_priority_over_same_shortcut(conn, subjects):
    add_file(conn, "SRC/SEM7/SI_Serwisy_Internetowe_NET/a.pdf")
    assert not manifest(conn, subjects, 7, "SI", "KASK_Architektura_Systemów_Komputerowych")[0]["needs_review"]
    assert manifest(conn, subjects, 7, "SI", "KT_Teleinformatyka") == []


def test_competing_subject_in_package_name_is_review(conn, subjects):
    # P jest faktycznym przedmiotem SEM7, nie neutralną nazwą fixture.
    add_file(conn, "P/SEM7/SI_Serwisy_Internetowe_NET/a.pdf")
    row = manifest(conn, subjects, 7, "SI", "KASK_Architektura_Systemów_Komputerowych")[0]
    assert "ambiguous_subject" in row["review_reasons"]


def test_similar_shortcuts_do_not_match(conn, subjects):
    add_file(conn, "SRC/SEM2/JAII/a.pdf")
    assert manifest(conn, subjects, 2, "JAI") == []


def test_provenance_all_copies_and_unique_representative(conn, subjects):
    add_file(conn, "P/SEM3/AK/a.pdf")
    add_file(conn, "Q/generic/a.pdf")
    add_file(conn, "R/broken/a.pdf", status="error")
    conn.execute("UPDATE folders SET duplicate_of='Q/generic' WHERE folder_path='P/SEM3'")
    conn.commit()
    row = manifest(conn, subjects)[0]
    assert row["source_paths"] == ["P/SEM3/AK/a.pdf", "Q/generic/a.pdf", "R/broken/a.pdf"]
    assert row["matched_source_paths"] == ["P/SEM3/AK/a.pdf"]
    assert row["source_path"] == "Q/generic/a.pdf"
    assert not row["needs_review"]


def test_only_duplicate_copies_cannot_be_extracted(conn, subjects):
    add_file(conn, "P/SEM3/AK/a.pdf")
    add_file(conn, "Q/anchor/b.pdf", B)
    conn.execute("UPDATE folders SET duplicate_of='Q/anchor' WHERE folder_path='P/SEM3'")
    conn.commit()
    row = manifest(conn, subjects)[0]
    assert row["source_path"] is None
    assert "no_unique_source" in row["review_reasons"]


@pytest.mark.parametrize("status,sha,content", [
    ("error", A, True), ("discovered", A, True),
    ("hashed", None, False), ("hashed", "bad-hash", True), ("hashed", A, False),
])
def test_skip_unusable_index_entries(conn, subjects, status, sha, content):
    add_file(conn, "P/SEM3/AK/a.pdf", sha, status, content=content)
    assert manifest(conn, subjects) == []


def test_conflicting_provenance_and_size_flagged(conn, subjects):
    add_file(conn, "P/SEM3/AK/a.pdf", size=20)
    add_file(conn, "Q/SEM2/PO/a.pdf", size=10)
    row = manifest(conn, subjects)[0]
    assert row["needs_review"]
    assert "conflicting_source_subjects" in row["review_reasons"]
    assert "inconsistent_sizes" in row["review_reasons"]
    assert row["size_bytes"] == 20  # rozmiar reprezentanta, nie mniejszej kopii


def test_conflicting_groups_need_review_even_with_full_subject_name(conn, subjects):
    add_file(conn, "SRC/SEM7/KASK/KT/SI_Serwisy_Internetowe_NET/a.pdf")
    row = manifest(conn, subjects, 7, "SI", "KASK_Architektura_Systemów_Komputerowych")[0]
    assert "conflicting_groups" in row["review_reasons"]


def test_sorted_repeatable_no_database_writes(conn, subjects):
    add_file(conn, "P/SEM3/AK/b.pdf", B)
    add_file(conn, "P/SEM3/AK/a.pdf", A, status="verified")
    before = list(conn.iterdump())
    statements = []
    conn.set_trace_callback(statements.append)
    rows = manifest(conn, subjects)
    assert rows == manifest(conn, subjects)
    assert [r["sha256"] for r in rows] == [A, B]
    assert all(s.lstrip().startswith("SELECT") for s in statements)
    assert len(statements) == 6  # trzy zbiorcze SELECT na przebieg, bez N+1
    conn.set_trace_callback(None)
    assert list(conn.iterdump()) == before


def test_reject_traversal_in_index(conn, subjects):
    add_file(conn, "P/SEM3/AK/a.pdf")
    conn.execute("UPDATE files SET source_relative_path='../SEM3/AK/a.pdf'")
    with pytest.raises(ValueError, match="niebezpieczna"):
        manifest(conn, subjects)
