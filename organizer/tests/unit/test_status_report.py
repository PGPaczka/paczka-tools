"""E3: `reports/STATUS.md` liczony z indeksu. Bez dotykania prawdziwej bazy."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import status_report as cli
from orglib import config, db
from status_report import collect, render, stage_of

runner = CliRunner()
SHA = {name: name * 64 for name in "abcd"}


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
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for index, sha in enumerate(SHA.values()):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/p{index}.pdf",
            "folder_path": "P/SEM3", "size_bytes": 10, "sha256": sha, "status": "extracted",
        })
    # Ground truth (scan_target) i plan (build_plan) dla TEGO SAMEGO przedmiotu.
    db.upsert_classification(conn, {
        "sha256": SHA["a"], "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_X/egzamin/a.pdf", "is_outdated": 0,
        "classification_method": "manual", "confidence": 1.0, "run_id": "ground_truth",
        "decided_at": "2026-09-17T00:00:00Z",
    })
    for sha, action, review in ((SHA["b"], "copy", 0), (SHA["c"], "copy", 1), (SHA["d"], "skip", 0)):
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "kolokwia",
            "target_relative_path": f"paczka/SEM3/AKO_X/kolokwia/{sha[:4]}.pdf", "is_outdated": 0,
            "classification_method": "heuristic", "confidence": 0.9, "run_id": "plan:abc123",
            "decided_at": "2026-09-19T00:00:00Z", "action": action, "reason": "t",
            "needs_review": review,
        })
    conn.commit()
    conn.close()
    return paths


def read(workspace):
    import sqlite3

    conn = sqlite3.connect(workspace.work_db)
    conn.row_factory = sqlite3.Row
    try:
        return collect(conn)
    finally:
        conn.close()


def test_ground_truth_is_counted_apart_from_the_plan(workspace) -> None:
    """Mieszanie tych dwóch liczb mówiłoby, że przedmiot jest zrobiony, gdy nie jest."""
    data = read(workspace)

    entry = data["per_subject"][(3, "AKO")]
    assert entry["ground_truth"] == 1
    assert entry["planned"] == 3 and entry["needs_review"] == 1
    assert dict(entry["actions"]) == {"copy": 2, "skip": 1}
    assert entry["decided_at"] == "2026-09-19T00:00:00Z"


def test_global_counters_come_from_the_index(workspace) -> None:
    data = read(workspace)

    assert data["packages"] == 1 and data["files"] == 4 and data["contents"] == 4
    assert data["files_by_status"] == {"extracted": 4}


@pytest.mark.parametrize("entry, stage", [
    ({"planned": 3, "needs_review": 0, "ground_truth": 1}, "plan gotowy"),
    ({"planned": 3, "needs_review": 2, "ground_truth": 1}, "plan do przeglądu"),
    ({"planned": 0, "needs_review": 0, "ground_truth": 5}, "tylko ground truth"),
    ({"planned": 0, "needs_review": 0, "ground_truth": 0}, "nietknięty"),
])
def test_stage_names_match_what_the_numbers_mean(entry, stage) -> None:
    assert stage_of(entry) == stage


def test_report_lists_every_subject_including_untouched_ones(workspace) -> None:
    subjects = config.iter_subjects()

    page = render(read(workspace), subjects, "2026-09-19T00:00:00Z")

    assert page.count("\n| ") >= len(subjects), "każdy przedmiot ma mieć wiersz"
    assert "| 3 | Wspolne | AKO |" in page
    assert "**plan do przeglądu** (1): AKO (sem 3)" in page
    assert "nietknięty" in page


def test_cli_writes_the_report_and_leaves_the_index_alone(workspace, tmp_path) -> None:
    before = workspace.work_db.read_bytes()

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0, result.output
    target = config.ORGANIZER_ROOT / "reports" / "STATUS.md"
    assert "STATUS — Paczka Organizer" in target.read_text(encoding="utf-8")
    assert workspace.work_db.read_bytes() == before


def test_missing_database_is_an_error(workspace) -> None:
    workspace.work_db.unlink()

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 1
    assert "brak bazy" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_into_material_trees(workspace, tree) -> None:
    forbidden = getattr(workspace, tree) / "STATUS.md"

    result = runner.invoke(cli.app, ["--output", str(forbidden)])

    assert result.exit_code == 1
    assert not forbidden.exists()
