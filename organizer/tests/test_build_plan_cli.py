"""CLI B7: plan na dysku i w bazie. Najważniejsze: czego zapis NIE MOŻE ruszyć."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

import build_plan as cli
from orglib import config, db
from orglib.jsonl import read_jsonl
from orglib.plan_build import META_KEY

runner = CliRunner()
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_GT = "c" * 64
TARGET = "paczka/SEM3/AKO_Architektura_Komputerów/kolokwia/kol_02/main.c"


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
    for sha in (SHA_A, SHA_B, SHA_GT):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "text"})
    # Ground truth: treść leżąca już w paczce, zapisana przez scan_target.
    db.upsert_classification(conn, {
        "sha256": SHA_GT, "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_Architektura_Komputerów/egzamin/x.pdf",
        "is_outdated": 0, "classification_method": "manual", "confidence": 1.0,
        "run_id": "ground_truth", "decided_at": "2026-09-17T00:00:00Z",
    })
    conn.commit()
    conn.close()
    return paths


def decision(sha, **overrides):
    row = {
        "schema_version": 1, "source_sha256": sha, "action": "copy", "target_rel": TARGET,
        "category": "kolokwia", "year": None, "related_to": None, "relation": None,
        "confidence": 0.95, "method": "heuristic", "model": "deterministic",
        "reason": "test", "needs_review": False,
    }
    row.update(overrides)
    return row


@pytest.fixture
def inputs(tmp_path):
    base = tmp_path / "reports"
    base.mkdir()
    (base / "manifest_slice.jsonl").write_text(
        "".join(
            json.dumps({"sha256": sha, "source_path": path}, ensure_ascii=False) + "\n"
            for sha, path in (
                (SHA_A, "P/AKO/kol2/Zadanie 1/main.c"),
                (SHA_B, "P/AKO/kol2/Zadanie 2/main.c"),
                (SHA_GT, "P/AKO/egzamin/x.pdf"),
            )
        ),
        encoding="utf-8",
    )
    (base / "plan.det.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in (
                decision(SHA_A), decision(SHA_B),
                decision(SHA_GT, action="skip", category="egzamin",
                         target_rel="paczka/SEM3/AKO_Architektura_Komputerów/egzamin/x.pdf",
                         method="deterministic", confidence=1.0),
            )
        ),
        encoding="utf-8",
    )
    return base


def invoke(inputs, *args):
    return runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO",
        "--manifest", str(inputs / "manifest_slice.jsonl"), *args,
    ])


def rows_of(database, table, order):
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]
    finally:
        conn.close()


def test_writes_the_plan_file_with_a_header_first(workspace, inputs):
    result = invoke(inputs)

    assert result.exit_code == 0, result.output
    lines = read_jsonl(inputs / "plan.jsonl")
    assert META_KEY in lines[0]
    meta = lines[0][META_KEY]
    assert meta["items"] == 3 and meta["subject_key"] == "AKO"
    assert len(meta["plan_hash"]) == 64
    assert all(META_KEY not in line for line in lines[1:])
    # Kolizja `main.c` rozstrzygnięta katalogiem źródłowym.
    targets = sorted(line["target_rel"] for line in lines[1:] if line["action"] == "copy")
    assert targets == [
        "paczka/SEM3/AKO_Architektura_Komputerów/kolokwia/kol_02/Zadanie 1/main.c",
        "paczka/SEM3/AKO_Architektura_Komputerów/kolokwia/kol_02/Zadanie 2/main.c",
    ]


def test_ground_truth_row_is_never_overwritten(workspace, inputs):
    """Klucz `classifications` to samo sha256 — zapis planu mógłby skasować jedyny
    ślad, że materiał już leży w paczce. Ten test jest po to, żeby nie mógł."""
    assert invoke(inputs).exit_code == 0

    rows = {row["sha256"]: row for row in rows_of(workspace.work_db, "classifications", "sha256")}
    assert rows[SHA_GT]["run_id"] == "ground_truth"
    assert rows[SHA_GT]["classification_method"] == "manual"
    assert rows[SHA_A]["run_id"].startswith("plan:")
    assert rows[SHA_A]["action"] == "copy" and rows[SHA_A]["needs_review"] == 0


def test_plan_items_carry_every_decision_including_media_and_skip(workspace, inputs):
    (inputs / "plan.det.jsonl").write_text(
        json.dumps(decision(SHA_A, action="media", target_rel="90_MEDIA/AKO/a.mp3",
                            category="inne"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert invoke(inputs).exit_code == 0

    items = rows_of(workspace.work_db, "plan_items", "sha256")
    assert [(item["action"], item["status"]) for item in items] == [("media", "planned")]


def test_rerunning_replaces_the_subject_slice_instead_of_piling_up(workspace, inputs):
    assert invoke(inputs).exit_code == 0
    first = rows_of(workspace.work_db, "classifications", "sha256")
    # Druga wersja planu: jedna treść mniej.
    (inputs / "plan.det.jsonl").write_text(
        json.dumps(decision(SHA_A), ensure_ascii=False) + "\n", encoding="utf-8"
    )

    assert invoke(inputs).exit_code == 0

    second = {row["sha256"] for row in rows_of(workspace.work_db, "classifications", "sha256")}
    assert len(first) == 3
    # Zostaje nowa decyzja i ground truth; nieaktualna decyzja znika.
    assert second == {SHA_A, SHA_GT}


def test_no_db_writes_only_the_file(workspace, inputs):
    result = invoke(inputs, "--no-db")

    assert result.exit_code == 0, result.output
    assert (inputs / "plan.jsonl").is_file()
    assert rows_of(workspace.work_db, "plan_items", "sha256") == []


def test_dry_run_writes_nothing_at_all(workspace, inputs):
    before = workspace.work_db.read_bytes()

    result = invoke(inputs, "--dry-run")

    assert result.exit_code == 0, result.output
    assert not (inputs / "plan.jsonl").exists()
    assert workspace.work_db.read_bytes() == before


def test_relations_are_attached_when_the_export_is_there(workspace, inputs):
    (inputs / "relations.jsonl").write_text(
        json.dumps({
            "schema_version": 1, "source_sha256": SHA_A, "target_sha256": SHA_B,
            "relation_type": "older_version", "confidence": 0.8,
            "detection_method": "near_dupe:simhash", "reason": "test",
        }) + "\n",
        encoding="utf-8",
    )

    assert invoke(inputs).exit_code == 0

    lines = {line["source_sha256"]: line for line in read_jsonl(inputs / "plan.jsonl")[1:]}
    assert lines[SHA_A]["relation"] == "older_version"
    assert lines[SHA_A]["related_to"] == SHA_B


def test_missing_deterministic_plan_says_what_to_run(workspace, inputs):
    (inputs / "plan.det.jsonl").unlink()

    result = invoke(inputs)

    assert result.exit_code == 1
    assert "subject-classify" in result.output


def test_missing_manifest_is_an_error(workspace, tmp_path):
    result = runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO", "--manifest", str(tmp_path / "nie_ma.jsonl"),
    ])

    assert result.exit_code == 1
    assert "brak manifestu" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_the_plan_into_material_trees(workspace, inputs, tree):
    forbidden = getattr(workspace, tree) / "plan"

    result = invoke(inputs, "--out-dir", str(forbidden))

    assert result.exit_code == 1
    assert not forbidden.exists()
