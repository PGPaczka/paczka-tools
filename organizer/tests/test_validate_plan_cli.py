"""CLI B8: bramka przed `apply`. Najważniejszy jest KOD WYJŚCIA — on blokuje apply."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import validate_plan as cli
from orglib import config, db

runner = CliRunner()
SHA_A = "a" * 64
SHA_B = "b" * 64
TARGET = "paczka/SEM3/AKO_Architektura_Komputerów/laboratoria/wspólne/lab_03/x.pdf"


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


def plan_line(**overrides):
    row = {
        "schema_version": 1, "source_sha256": SHA_A, "action": "copy",
        "target_rel": TARGET, "category": "laboratoria", "year": "2020",
        "confidence": 0.95, "method": "heuristic", "model": "deterministic",
        "reason": "test", "needs_review": False,
    }
    row.update(overrides)
    return row


def write_plan(path, *rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def invoke(tmp_path, *args, plan=None):
    arguments = ["--semester", "3", "--skrot", "AKO", "--no-ground-truth", *args]
    if plan is not None:
        arguments += ["--plan", str(plan)]
    return runner.invoke(cli.app, arguments)


def test_clean_plan_passes_and_writes_a_report(workspace, tmp_path):
    plan = write_plan(tmp_path / "plan.jsonl", plan_line())

    result = invoke(tmp_path, plan=plan)

    assert result.exit_code == 0, result.output
    assert "plan przechodzi walidację" in result.output
    assert (tmp_path / "validation.jsonl").read_text(encoding="utf-8") == ""


def test_broken_plan_blocks_apply_with_exit_code_two(workspace, tmp_path):
    plan = write_plan(tmp_path / "plan.jsonl", plan_line(), plan_line(source_sha256=SHA_B))

    result = invoke(tmp_path, plan=plan)

    assert result.exit_code == 2
    assert "PLAN ODRZUCONY" in result.output
    findings = [json.loads(line) for line in (tmp_path / "validation.jsonl").read_text("utf-8").splitlines()]
    assert [f["code"] for f in findings] == ["kolizja_celu"]


def test_schema_violation_is_reported_as_a_finding(workspace, tmp_path):
    broken = plan_line()
    del broken["confidence"]
    plan = write_plan(tmp_path / "plan.jsonl", broken)

    result = invoke(tmp_path, plan=plan)

    assert result.exit_code == 2
    assert "schemat" in result.output


def test_warnings_alone_pass_unless_strict(workspace, tmp_path):
    unpadded = plan_line(
        target_rel="paczka/SEM3/AKO_Architektura_Komputerów/laboratoria/wspólne/lab_3/x.pdf"
    )
    plan = write_plan(tmp_path / "plan.jsonl", unpadded)

    assert invoke(tmp_path, plan=plan).exit_code == 0
    assert invoke(tmp_path, "--strict", plan=plan).exit_code == 2


def test_several_plan_files_are_validated_together(workspace, tmp_path):
    """Plan deterministyczny i plan AI opisują ten sam przedmiot — sprzeczność między
    nimi (ta sama treść rozstrzygnięta dwa razy) musi wyjść przed `apply`, nie po."""
    det = write_plan(tmp_path / "plan.det.jsonl", plan_line())
    ai = write_plan(tmp_path / "plan.ai.jsonl", plan_line(
        target_rel="paczka/SEM3/AKO_Architektura_Komputerów/inne/x.pdf", category="inne",
        method="llm", model="gpt", confidence=0.95,
    ))

    result = runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO", "--no-ground-truth",
        "--plan", str(det), "--plan", str(ai),
    ])

    assert result.exit_code == 2
    assert "podwojna_decyzja" in result.output


def test_ground_truth_overwrite_is_caught_from_the_index(workspace, tmp_path):
    conn = db.connect(workspace.work_db)
    db.upsert_content(conn, {"sha256": SHA_B, "content_kind": "pdf"})
    db.record_applied(conn, {
        "target_relative_path": TARGET, "sha256": SHA_B, "action": "copy",
        "plan_hash": "ground_truth:1:2", "applied_at": "2026-09-17T00:00:00Z",
    })
    conn.commit()
    conn.close()
    plan = write_plan(tmp_path / "plan.jsonl", plan_line())

    result = runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO", "--plan", str(plan), "--db", str(workspace.work_db),
    ])

    assert result.exit_code == 2
    assert "nadpisanie_ground_truth" in result.output


def test_missing_plan_is_a_preparation_error(workspace, tmp_path):
    result = invoke(tmp_path, plan=tmp_path / "nie_ma.jsonl")

    assert result.exit_code == 1
    assert "brak pliku planu" in result.output


def test_no_plan_at_all_says_what_to_run(workspace, tmp_path):
    result = runner.invoke(cli.app, ["--semester", "3", "--skrot", "AKO", "--no-ground-truth"])

    assert result.exit_code == 1
    assert "subject-classify" in result.output


def test_missing_database_is_an_error_unless_ground_truth_is_skipped(workspace, tmp_path):
    workspace.work_db.unlink()
    plan = write_plan(tmp_path / "plan.jsonl", plan_line())

    blocked = runner.invoke(cli.app, ["--semester", "3", "--skrot", "AKO", "--plan", str(plan)])
    assert blocked.exit_code == 1 and "brak bazy" in blocked.output

    assert invoke(tmp_path, plan=plan).exit_code == 0


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_the_report_into_material_trees(workspace, tmp_path, tree):
    plan = write_plan(tmp_path / "plan.jsonl", plan_line())
    forbidden = getattr(workspace, tree) / "validation.jsonl"

    result = invoke(tmp_path, "--report", str(forbidden), plan=plan)

    assert result.exit_code == 1
    assert not forbidden.exists()
