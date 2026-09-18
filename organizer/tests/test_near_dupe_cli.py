"""CLI B6: izolowany indeks w tmp_path; sprawdzamy zapis do bazy i eksport.

Najważniejsze tu nie jest „czy znalazł relacje” (to warstwa `tests/test_near_dupe.py`),
tylko **co robi z cudzymi wierszami** — etap podmienia wyłącznie własny wycinek.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

import near_dupe as cli
from orglib import config, db
from orglib.near_dupe import METHOD_PREFIX

runner = CliRunner()
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_OUTSIDE = "e" * 64


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
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3/AKO", "source_package": "P"})
    for index, (sha, simhash) in enumerate(
        [(SHA_A, "0000000000000000"), (SHA_B, "0000000000000001"), (SHA_OUTSIDE, "ffffffffffffffff")]
    ):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/AKO/plik{index}.pdf",
            "folder_path": "P/SEM3/AKO", "size_bytes": 10, "sha256": sha,
            "simhash": simhash, "status": "extracted",
        })
    conn.commit()
    conn.close()
    return paths


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "manifest_slice.jsonl"
    path.write_text(
        "".join(
            json.dumps({"sha256": sha, "source_paths": [f"P/SEM3/AKO/plik.pdf"]}) + "\n"
            for sha in (SHA_A, SHA_B)
        ),
        encoding="utf-8",
    )
    return path


def invoke(manifest, out_dir, *args):
    return runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO",
        "--manifest", str(manifest), "--out-dir", str(out_dir), *args,
    ])


def relations(database):
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM relations ORDER BY source_sha256")]
    finally:
        conn.close()


def test_writes_relations_to_the_database_and_exports_them(workspace, manifest, tmp_path):
    out = tmp_path / "out"

    result = invoke(manifest, out)

    assert result.exit_code == 0, result.output
    rows = relations(workspace.work_db)
    assert len(rows) == 1
    assert rows[0]["source_sha256"] == SHA_A and rows[0]["target_sha256"] == SHA_B
    assert rows[0]["relation_type"] == "near_duplicate"
    assert rows[0]["detection_method"] == f"{METHOD_PREFIX}:simhash"

    exported = [json.loads(line) for line in (out / "relations.jsonl").read_text("utf-8").splitlines()]
    assert len(exported) == 1
    assert exported[0]["source_sha256"] == rows[0]["source_sha256"]
    assert exported[0]["schema_version"] == 1


def test_rerun_is_byte_identical_and_does_not_multiply_rows(workspace, manifest, tmp_path):
    out = tmp_path / "out"
    assert invoke(manifest, out).exit_code == 0
    first = (out / "relations.jsonl").read_bytes()

    assert invoke(manifest, out).exit_code == 0

    assert (out / "relations.jsonl").read_bytes() == first
    assert len(relations(workspace.work_db)) == 1


def test_replaces_only_its_own_rows(workspace, manifest, tmp_path):
    """Podmiana wycinka: znikają TYLKO nieaktualne wiersze tego etapu z tego zakresu."""
    conn = db.connect(workspace.work_db)
    # (1) cudza metoda w tym samym zakresie — decyzja człowieka (B14);
    db.upsert_relation(conn, {
        "source_sha256": SHA_A, "target_sha256": SHA_B, "relation_type": "related",
        "confidence": 1.0, "detection_method": "manual", "reason": "decyzja człowieka",
    })
    # (2) własny, ale NIEAKTUALNY wiersz z tego zakresu — ma zniknąć;
    db.upsert_relation(conn, {
        "source_sha256": SHA_A, "target_sha256": SHA_B, "relation_type": "older_version",
        "confidence": 0.5, "detection_method": f"{METHOD_PREFIX}:simhash", "reason": "stare",
    })
    # (3) własny wiersz spoza zakresu — nie nasza sprawa, zostaje.
    db.upsert_relation(conn, {
        "source_sha256": SHA_A, "target_sha256": SHA_OUTSIDE, "relation_type": "near_duplicate",
        "confidence": 0.7, "detection_method": f"{METHOD_PREFIX}:phash", "reason": "inny zakres",
    })
    conn.commit()
    conn.close()

    assert invoke(manifest, tmp_path / "out").exit_code == 0

    rows = {(r["relation_type"], r["detection_method"]): r for r in relations(workspace.work_db)}
    assert ("related", "manual") in rows, "decyzja człowieka nie może zniknąć"
    assert ("near_duplicate", f"{METHOD_PREFIX}:phash") in rows, "para spoza zakresu zostaje"
    assert ("older_version", f"{METHOD_PREFIX}:simhash") not in rows, "nieaktualny wiersz miał zniknąć"
    assert ("near_duplicate", f"{METHOD_PREFIX}:simhash") in rows


def test_dry_run_changes_nothing(workspace, manifest, tmp_path):
    before = workspace.work_db.read_bytes()

    result = invoke(manifest, tmp_path / "out", "--dry-run")

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "out").exists()
    assert workspace.work_db.read_bytes() == before


def test_warns_when_nothing_has_signatures_yet(workspace, manifest, tmp_path):
    conn = db.connect(workspace.work_db)
    conn.execute("UPDATE files SET simhash = NULL")
    conn.commit()
    conn.close()

    result = invoke(manifest, tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "just extract" in result.output
    assert relations(workspace.work_db) == []


def test_all_without_output_directory_is_refused(workspace, tmp_path):
    result = runner.invoke(cli.app, ["--all"])

    assert result.exit_code == 1
    assert "--out-dir" in result.output


def test_subject_without_semester_is_refused(workspace, manifest, tmp_path):
    result = runner.invoke(cli.app, ["--manifest", str(manifest), "--out-dir", str(tmp_path / "o")])

    assert result.exit_code == 1
    assert "--semester" in result.output


def test_missing_manifest_is_an_error(workspace, tmp_path):
    result = invoke(tmp_path / "nie_ma.jsonl", tmp_path / "out")

    assert result.exit_code == 1
    assert "brak manifestu" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_export_into_material_trees(workspace, manifest, tree):
    forbidden = getattr(workspace, tree) / "raport"

    result = invoke(manifest, forbidden)

    assert result.exit_code == 1
    assert "chronionym drzewie" in result.output
    assert not forbidden.exists()


def test_year_from_source_paths_makes_it_an_older_version(workspace, tmp_path):
    """Rok bierze się ze ŚCIEŻEK w indeksie, nie z manifestu — tak samo jak w B3."""
    conn = db.connect(workspace.work_db)
    conn.execute(
        "UPDATE files SET source_relative_path = ? WHERE sha256 = ?",
        ("SEM3/AKO/2019/plik0.pdf", SHA_A),
    )
    conn.execute(
        "UPDATE files SET source_relative_path = ? WHERE sha256 = ?",
        ("SEM3/AKO/2021/plik1.pdf", SHA_B),
    )
    conn.commit()
    conn.close()
    manifest_path = tmp_path / "manifest_slice.jsonl"
    manifest_path.write_text(
        "".join(json.dumps({"sha256": sha}) + "\n" for sha in (SHA_A, SHA_B)), encoding="utf-8"
    )

    assert invoke(manifest_path, tmp_path / "out").exit_code == 0

    rows = relations(workspace.work_db)
    assert [r["relation_type"] for r in rows] == ["older_version"]
    assert rows[0]["source_sha256"] == SHA_A and rows[0]["target_sha256"] == SHA_B
