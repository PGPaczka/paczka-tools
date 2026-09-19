"""CLI C3: eksport vaulta z indeksu. Izolowana baza, żadnych prawdziwych materiałów."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import synapse_export as cli
from orglib import config, db

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
            "source_package": "P", "source_relative_path": f"SEM3/AKO/plik{index}.pdf",
            "folder_path": "P/SEM3", "size_bytes": 2048, "sha256": sha,
            "modified_date": f"2026-0{index + 1}-01T00:00:00Z", "status": "extracted",
        })
    # AKO: jedna treść w paczce (ground truth) i trzy decyzje planu.
    db.upsert_classification(conn, {
        "sha256": SHA["a"], "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_X/egzamin/a.pdf", "is_outdated": 0,
        "classification_method": "manual", "confidence": 1.0, "run_id": "ground_truth",
        "decided_at": "2026-09-17T00:00:00Z",
    })
    for sha, category, review in ((SHA["b"], "kolokwia", 0), (SHA["c"], "kolokwia", 1),
                                  (SHA["d"], "laboratoria", 0)):
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": category,
            "target_relative_path": f"paczka/SEM3/AKO_X/{category}/{sha[:4]}.pdf",
            "is_outdated": 0, "classification_method": "heuristic", "confidence": 0.95,
            "run_id": "plan:abc", "decided_at": "2026-09-19T00:00:00Z", "action": "copy",
            "reason": "test", "needs_review": review, "year": "2019",
        })
    db.upsert_relation(conn, {
        "source_sha256": SHA["b"], "target_sha256": SHA["c"],
        "relation_type": "near_duplicate", "confidence": 0.9,
        "detection_method": "near_dupe:simhash", "reason": "simhash, odległość 1",
    })
    conn.commit()
    conn.close()
    return paths


def vault(workspace, name="paczka"):
    return workspace.work / "synapse" / name


def notes_of(root):
    return {path.stem: path.read_text(encoding="utf-8") for path in root.rglob("*.md")
            if path.name != "README.md"}


def test_subject_scope_writes_one_note_per_subject(workspace):
    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0, result.output
    root = vault(workspace)
    notes = notes_of(root)
    assert len(notes) == len(config.iter_subjects())
    ako = notes["sem3-ako"]
    assert 'category: "SEM3"' in ako and 'status: "in-progress"' in ako
    assert "W paczce (ground truth): **1**" in ako
    assert "Zaplanowane decyzje: **3** (do obejrzenia: 1)" in ako
    # Nietknięty przedmiot też ma notatkę — inaczej mapa nie pokazywałaby kolejki.
    assert any('status: "not-started"' in body for body in notes.values())


def test_json_payload_matches_the_prototype_shape(workspace):
    assert runner.invoke(cli.app, []).exit_code == 0

    payload = json.loads((vault(workspace) / "synapse.json").read_text(encoding="utf-8"))
    assert set(payload) == {"vault", "generated_at", "catColors", "notes"}
    assert payload["catColors"]["SEM3"] == "#3fb950"
    note = next(n for n in payload["notes"] if n["id"] == "sem3-ako")
    assert set(note) == {"id", "title", "category", "level", "status", "tags", "links",
                         "path", "body", "modified", "activity"}
    assert note["level"] in (1, 2, 3) and note["status"] in (
        "completed", "in-progress", "not-started"
    )


def test_content_scope_is_a_relation_graph_not_a_file_dump(workspace):
    """Domyślnie tylko treści z relacją — inaczej „graf relacji” to pole samotnych kropek."""
    result = runner.invoke(cli.app, [
        "--scope", "subject", "--semester", "3", "--skrot", "AKO", "--vault", "ako",
    ])

    assert result.exit_code == 0, result.output
    notes = notes_of(vault(workspace, "ako"))
    assert len(notes) == 2, "tylko para połączona relacją"
    body = next(iter(notes.values()))
    assert "## Relacje" in body and "near_duplicate" in body
    assert "[[ako-" in body


def test_isolated_content_is_included_on_demand(workspace):
    result = runner.invoke(cli.app, [
        "--scope", "subject", "--semester", "3", "--skrot", "AKO", "--vault", "ako",
        "--include-isolated",
    ])

    assert result.exit_code == 0, result.output
    assert len(notes_of(vault(workspace, "ako"))) == 4


def test_content_note_carries_provenance_and_the_decision(workspace):
    runner.invoke(cli.app, [
        "--scope", "subject", "--semester", "3", "--skrot", "AKO", "--vault", "ako",
    ])

    body = "\n".join(notes_of(vault(workspace, "ako")).values())
    assert "P/SEM3/AKO/plik" in body, "prowenancja ma być w notatce"
    assert "Decyzja: **copy**" in body and "sha256:" in body
    assert "rodzaj-pdf" in body and "rok-2019" in body


def test_ground_truth_content_is_marked_as_completed(workspace):
    runner.invoke(cli.app, [
        "--scope", "subject", "--semester", "3", "--skrot", "AKO", "--vault", "ako",
        "--include-isolated",
    ])

    notes = notes_of(vault(workspace, "ako"))
    in_package = [body for body in notes.values() if "w-paczce" in body]
    assert len(in_package) == 1
    assert 'status: "completed"' in in_package[0] and "level: 1" in in_package[0]


def test_regenerating_removes_notes_that_no_longer_exist(workspace):
    root = vault(workspace)
    assert runner.invoke(cli.app, []).exit_code == 0
    stray = root / "sem3" / "recznie-dopisana.md"
    stray.write_text("---\nid: \"recznie-dopisana\"\n---\n", encoding="utf-8")

    assert runner.invoke(cli.app, []).exit_code == 0

    assert not stray.exists(), "vault jest generowany — ręczne notatki nie przetrwają"


def test_dry_run_writes_nothing(workspace):
    result = runner.invoke(cli.app, ["--dry-run"])

    assert result.exit_code == 0, result.output
    assert not (workspace.work / "synapse").exists()
    assert "notatki: " in result.output


def test_unknown_scope_is_refused(workspace):
    result = runner.invoke(cli.app, ["--scope", "wszystko"])

    assert result.exit_code == 1
    assert "nieznany zakres" in result.output


def test_subject_scope_requires_the_subject(workspace):
    result = runner.invoke(cli.app, ["--scope", "subject"])

    assert result.exit_code == 1
    assert "--semester" in result.output


def test_subject_without_decisions_is_an_explicit_error(workspace):
    result = runner.invoke(cli.app, [
        "--scope", "subject", "--semester", "1", "--skrot", "AL", "--vault", "al",
    ])

    assert result.exit_code == 1
    assert "decyzje w bazie" in result.output


def test_missing_database_is_an_error(workspace):
    workspace.work_db.unlink()

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 1
    assert "brak bazy" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_into_material_trees(workspace, tree):
    forbidden = getattr(workspace, tree) / "vault"

    result = runner.invoke(cli.app, ["--out-dir", str(forbidden)])

    assert result.exit_code == 1
    assert not forbidden.exists()


def test_database_is_opened_read_only(workspace):
    before = workspace.work_db.read_bytes()

    assert runner.invoke(cli.app, []).exit_code == 0

    assert workspace.work_db.read_bytes() == before
