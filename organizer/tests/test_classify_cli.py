"""CLI B3: izolowany indeks, sztuczny manifest, nigdy prawdziwe materiały.

Wzorzec izolacji jak w ``tests/test_prepare_subject.py``: workspace w ``tmp_path``,
``config.ORGANIZER_ROOT`` przestawiony na katalog tymczasowy. Reguły i schemat
czytamy PRAWDZIWE — to jest sens tej warstwy: sprawdzić styk skryptu z repo.
"""

from __future__ import annotations

import json
import sqlite3

import jsonschema
import pytest
from typer.testing import CliRunner

import ai_resolve
import classify as classify_cli
from orglib import config, db

runner = CliRunner()
SHA_LAB = "a" * 64
SHA_GT = "b" * 64
SHA_UNKNOWN = "c" * 64
SHA_JUNK = "d" * 64

SCHEMA = json.loads(
    (config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json").read_text(encoding="utf-8")
)


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


@pytest.fixture
def manifest(tmp_path):
    rows = [
        {
            "sha256": SHA_LAB, "source_sha256": SHA_LAB,
            "source_path": "P/SEM3/AKO/Laby/lab_03/instrukcja.pdf",
            "source_paths": ["P/SEM3/AKO/Laby/lab_03/instrukcja.pdf"],
            "matched_source_paths": ["P/SEM3/AKO/Laby/lab_03/instrukcja.pdf"],
            "content_kind": "pdf", "size_bytes": 100,
            "needs_review": False, "review_reasons": [],
        },
        {
            "sha256": SHA_GT, "source_sha256": SHA_GT,
            "source_path": "P/SEM3/AKO/cokolwiek.pdf",
            "source_paths": ["P/SEM3/AKO/cokolwiek.pdf"],
            "matched_source_paths": ["P/SEM3/AKO/cokolwiek.pdf"],
            "content_kind": "pdf", "size_bytes": 200,
            "needs_review": False, "review_reasons": [],
        },
        {
            "sha256": SHA_UNKNOWN, "source_sha256": SHA_UNKNOWN,
            "source_path": "P/SEM3/AKO/readme.txt",
            "source_paths": ["P/SEM3/AKO/readme.txt"],
            "matched_source_paths": ["P/SEM3/AKO/readme.txt"],
            "content_kind": "text", "size_bytes": 10,
            "needs_review": False, "review_reasons": [],
        },
        {
            "sha256": SHA_JUNK, "source_sha256": SHA_JUNK,
            "source_path": "P/SEM3/AKO/Laby/Debug/a.obj",
            "source_paths": ["P/SEM3/AKO/Laby/Debug/a.obj"],
            "matched_source_paths": ["P/SEM3/AKO/Laby/Debug/a.obj"],
            "content_kind": "other", "size_bytes": 300,
            "needs_review": False, "review_reasons": [],
        },
    ]
    path = tmp_path / "manifest_slice.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def seed_ground_truth(database):
    conn = db.connect(database)
    db.upsert_content(conn, {"sha256": SHA_GT, "content_kind": "pdf"})
    db.upsert_classification(conn, {
        "sha256": SHA_GT, "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_Architektura_Komputerów/egzamin/x.pdf",
        "is_outdated": 0, "classification_method": "manual", "confidence": 1.0,
        "run_id": "ground_truth", "decided_at": "2026-09-18T00:00:00Z",
    })
    conn.commit()
    conn.close()


def invoke(manifest, out_dir, *args):
    return runner.invoke(classify_cli.app, [
        "--semester", "3", "--skrot", "AKO",
        "--manifest", str(manifest), "--out-dir", str(out_dir), *args,
    ])


def plan_rows(out_dir):
    return [json.loads(line) for line in (out_dir / "plan.det.jsonl").read_text("utf-8").splitlines()]


def test_writes_both_artifacts_and_leaves_the_index_untouched(workspace, manifest, tmp_path):
    seed_ground_truth(workspace.work_db)
    before = workspace.work_db.read_bytes()
    out = tmp_path / "out"

    result = invoke(manifest, out)

    assert result.exit_code == 0, result.output
    rows = {row["source_sha256"]: row for row in plan_rows(out)}
    assert set(rows) == {SHA_LAB, SHA_GT, SHA_JUNK}
    for row in rows.values():
        jsonschema.validate(row, SCHEMA)
    assert rows[SHA_LAB]["action"] == "copy"
    assert rows[SHA_LAB]["target_rel"].endswith("laboratoria/wspólne/lab_03/instrukcja.pdf")
    assert rows[SHA_GT]["action"] == "skip" and rows[SHA_GT]["confidence"] == 1.0
    assert rows[SHA_JUNK]["action"] == "skip"

    unresolved = [
        json.loads(line)
        for line in (out / "unresolved.jsonl").read_text("utf-8").splitlines()
    ]
    assert [row["sha256"] for row in unresolved] == [SHA_UNKNOWN]
    assert unresolved[0]["needs_review"] is True

    assert workspace.work_db.read_bytes() == before
    assert not workspace.sources.exists()


def test_rerun_is_byte_identical(workspace, manifest, tmp_path):
    seed_ground_truth(workspace.work_db)
    out = tmp_path / "out"

    assert invoke(manifest, out).exit_code == 0
    first = (out / "plan.det.jsonl").read_bytes()
    assert invoke(manifest, out).exit_code == 0

    assert (out / "plan.det.jsonl").read_bytes() == first


def test_dry_run_writes_nothing(workspace, manifest, tmp_path):
    out = tmp_path / "out"

    result = invoke(manifest, out, "--no-ground-truth", "--dry-run")

    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert "dry-run" in result.output


def test_ground_truth_can_be_skipped_without_a_database(workspace, manifest, tmp_path):
    workspace.work_db.unlink()
    out = tmp_path / "out"

    result = invoke(manifest, out, "--no-ground-truth")

    assert result.exit_code == 0, result.output
    # Bez bazy treść z paczki nie jest rozpoznana i idzie normalną ścieżką.
    assert SHA_GT not in {row["source_sha256"] for row in plan_rows(out)}
    assert not workspace.work_db.exists()


def test_missing_database_is_an_error_not_a_fresh_one(workspace, manifest, tmp_path):
    workspace.work_db.unlink()

    result = invoke(manifest, tmp_path / "out")

    assert result.exit_code == 1
    assert "brak bazy" in result.output
    assert not workspace.work_db.exists()
    assert not (tmp_path / "out").exists()


def test_missing_manifest_is_an_error(workspace, tmp_path):
    result = invoke(tmp_path / "nie_ma.jsonl", tmp_path / "out")

    assert result.exit_code == 1
    assert "brak manifestu" in result.output
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_into_material_trees(workspace, manifest, tree):
    forbidden = getattr(workspace, tree) / "raport"

    result = invoke(manifest, forbidden, "--no-ground-truth")

    assert result.exit_code == 1
    assert "chronionym drzewie" in result.output
    assert not forbidden.exists()


def test_symlinked_output_directory_is_refused(workspace, manifest, tmp_path):
    workspace.sources.mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(workspace.sources, target_is_directory=True)

    result = invoke(manifest, link, "--no-ground-truth")

    assert result.exit_code == 1
    assert not any(workspace.sources.iterdir())


@pytest.mark.parametrize("semester, skrot", [("3", "NIE_MA"), ("7", "SI")])
def test_invalid_subject_writes_nothing(workspace, manifest, tmp_path, semester, skrot):
    result = runner.invoke(classify_cli.app, [
        "--semester", semester, "--skrot", skrot,
        "--manifest", str(manifest), "--out-dir", str(tmp_path / "out"),
    ])

    assert result.exit_code == 1
    assert not (tmp_path / "out").exists()


def test_corrupt_manifest_line_is_an_error(workspace, tmp_path):
    bad = tmp_path / "manifest_slice.jsonl"
    bad.write_text('{"sha256": "x"}\nto nie jest json\n', encoding="utf-8")

    result = invoke(bad, tmp_path / "out", "--no-ground-truth")

    assert result.exit_code == 1
    assert "niepoprawny JSON" in result.output


def test_unresolved_file_is_a_manifest_that_ai_resolve_accepts(workspace, manifest, tmp_path):
    """Kontrakt międzyetapowy: to, co B3 zostawia, MUSI dać się podać B5 na wejście."""
    out = tmp_path / "out"
    assert invoke(manifest, out, "--no-ground-truth").exit_code == 0

    rows = ai_resolve.read_jsonl(out / "unresolved.jsonl")
    resolved = ai_resolve.existing_hashes(out / "plan.det.jsonl")
    selected = ai_resolve.select_rows(rows, resolved=resolved, take_all=False)

    # Bez bazy `cokolwiek.pdf` nie jest rozpoznane jako leżące już w paczce,
    # więc — tak samo jak readme.txt — nie ma żadnego sygnału kategorii.
    assert [row["sha256"] for row in selected] == [SHA_GT, SHA_UNKNOWN]
    assert SHA_LAB in resolved


def test_ai_resolve_treats_the_deterministic_plan_as_already_decided(workspace, manifest, tmp_path):
    out = tmp_path / "out"
    assert invoke(manifest, out, "--no-ground-truth").exit_code == 0
    full_manifest = ai_resolve.read_jsonl(manifest)
    resolved = ai_resolve.existing_hashes(out / "plan.det.jsonl")

    # Tak liczy CLI, gdy plan B3 istnieje: nie filtruje po needs_review z manifestu,
    # bo to klasyfikator powiedział, czego nie rozstrzygnął.
    selected = ai_resolve.select_rows(
        full_manifest, resolved=resolved, take_all=False, only_review=False
    )

    # Manifest ma needs_review=False WSZĘDZIE, a mimo to do modelu idą dokładnie te
    # dwie treści, których nie ma w planie B3 — filtr po needs_review by je zgubił.
    assert [row["sha256"] for row in selected] == [SHA_GT, SHA_UNKNOWN]
    assert ai_resolve.select_rows(full_manifest, resolved=resolved, take_all=False) == []


def test_database_is_opened_read_only(workspace, manifest, tmp_path, monkeypatch):
    seed_ground_truth(workspace.work_db)
    opened: list[tuple] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        opened.append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(classify_cli.sqlite3, "connect", spy)
    assert invoke(manifest, tmp_path / "out").exit_code == 0

    assert opened, "etap nie otworzył bazy"
    assert all("mode=ro" in str(args[0]) and kwargs.get("uri") for args, kwargs in opened)
