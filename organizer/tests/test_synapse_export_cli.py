"""CLI C3: eksport vaulta z indeksu. Izolowana baza, żadnych prawdziwych materiałów."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import synapse_export as cli
from orglib import config, db

runner = CliRunner()
SHA = {name: name * 64 for name in "abcde"}


def frontmatter(path):
    """Prosty odczyt front mattera notatki — bez zależności od YAML-a w testach."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head = text.split("---\n")[1]
    return head, text


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
    # AKO: jedna treść w paczce + dwie z planu. SHA['d'] i SHA['e'] zostają bez decyzji.
    db.upsert_classification(conn, {
        "sha256": SHA["a"], "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_X/egzamin/a.pdf", "is_outdated": 0,
        "classification_method": "manual", "confidence": 1.0, "run_id": "ground_truth",
        "decided_at": "2026-09-17T00:00:00Z",
    })
    for sha, review in ((SHA["b"], 0), (SHA["c"], 1)):
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "kolokwia",
            "target_relative_path": f"paczka/SEM3/AKO_X/kolokwia/{sha[:4]}.pdf",
            "is_outdated": 0, "classification_method": "heuristic", "confidence": 0.95,
            "run_id": "plan:abc", "decided_at": "2026-09-19T00:00:00Z", "action": "copy",
            "reason": "test", "needs_review": review, "year": "2019",
        })
    # relacja wewnątrz paczki oraz relacja wychodząca poza nią (treść bez decyzji)
    db.upsert_relation(conn, {
        "source_sha256": SHA["b"], "target_sha256": SHA["c"],
        "relation_type": "near_duplicate", "confidence": 0.9,
        "detection_method": "near_dupe:simhash", "reason": "simhash",
    })
    db.upsert_relation(conn, {
        "source_sha256": SHA["b"], "target_sha256": SHA["d"],
        "relation_type": "older_version", "confidence": 0.7,
        "detection_method": "near_dupe:simhash", "reason": "rok",
    })
    conn.commit()
    conn.close()
    return paths


def vault(workspace):
    return workspace.work / "synapse" / "vault"


def notes_of(root):
    return {p.stem: p for p in root.rglob("*.md")}


def test_exports_the_three_level_hierarchy(workspace):
    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0, result.output
    notes = notes_of(vault(workspace))
    # 7 semestrów + 98 przedmiotów z katalogu + 3 treści z decyzją
    assert len([n for n in notes if n.startswith("sem") and "-" not in n]) == 7
    assert "sem3-ako" in notes
    files = [n for n in notes if n.startswith("ako-")]
    assert len(files) == 3

    head, _ = frontmatter(notes["sem3-ako"])
    assert 'type: "subject"' in head and 'category: "SEM3"' in head
    assert '  - target: "sem3"\n    kind: "belongs_to"' in head


def test_subject_note_carries_the_same_tag_as_its_files(workspace):
    """Jeden tag wybiera przedmiot RAZEM z jego plikami.

    W grafie semestr da się wybrać tagiem `sem3` (niosą go wszystkie trzy poziomy),
    ale przedmiot nie miał własnego tagu: filtr po `ako` pokazywał pliki bez ich
    przedmiotu. Zgłoszone z tabletu 2026-09-23 razem z prośbą o wybór przedmiotu.
    """
    assert runner.invoke(cli.app, []).exit_code == 0

    notes = notes_of(vault(workspace))
    subject_head, _ = frontmatter(notes["sem3-ako"])
    file_head, _ = frontmatter(
        next(p for name, p in notes.items() if name.startswith("ako-"))
    )

    assert '"ako"' in subject_head, "przedmiot ma nieść swój skrót jako tag"
    assert '"sem3"' in subject_head and '"sem3"' in file_head
    assert '"ako"' in file_head


def test_file_note_points_at_its_subject_and_carries_the_decision(workspace):
    assert runner.invoke(cli.app, []).exit_code == 0

    notes = notes_of(vault(workspace))
    note = next(p for name, p in notes.items() if name.startswith("ako-") and "plik1" in name)
    head, text = frontmatter(note)

    assert 'type: "file"' in head and 'category: "kolokwia"' in head
    assert '    kind: "belongs_to"' in head and '"sem3-ako"' in head
    assert "rok-2019" in head and "akcja-copy" in head
    assert "Decyzja: **copy**" in text and "Prowenancja" in text


def test_relation_inside_the_package_keeps_its_kind_and_confidence(workspace):
    assert runner.invoke(cli.app, []).exit_code == 0

    note = next(p for name, p in notes_of(vault(workspace)).items() if "plik1" in name)
    head, _ = frontmatter(note)

    assert '    kind: "near_duplicate"' in head
    assert "    confidence: 0.9" in head


def test_relation_leaving_the_package_becomes_a_ghost_target(workspace):
    """Materiał bez decyzji ma zostać WIDOCZNY jako ghost, nie zniknąć."""
    assert runner.invoke(cli.app, []).exit_code == 0

    notes = notes_of(vault(workspace))
    head, _ = frontmatter(next(p for name, p in notes.items() if "plik1" in name))

    assert '    kind: "older_version"' in head
    assert 'target: "nieprzypisane-' in head
    # ...ale sama notatka nieprzypisanego materiału domyślnie NIE powstaje
    assert not any(name.startswith("nieprzypisane-") for name in notes)


def test_include_unassigned_turns_ghosts_into_notes(workspace):
    assert runner.invoke(cli.app, ["--include-unassigned"]).exit_code == 0

    notes = notes_of(vault(workspace))
    ghost = next(p for name, p in notes.items() if name.startswith("nieprzypisane-"))
    head, text = frontmatter(ghost)

    assert 'category: "nieprzypisane"' in head and 'status: "not-started"' in head
    assert "bez decyzji" in text


def test_scope_limits_the_export_to_one_subject(workspace):
    result = runner.invoke(cli.app, ["--semester", "3", "--skrot", "AKO"])

    assert result.exit_code == 0, result.output
    notes = notes_of(vault(workspace))
    assert "sem3-ako" in notes
    assert not any(name.startswith("sem1") for name in notes)


def test_readme_lands_next_to_the_vault_not_inside_it(workspace):
    """Każdy `.md` w vaulcie jest notatką — README w środku byłby węzłem-sierotą."""
    assert runner.invoke(cli.app, []).exit_code == 0

    assert not (vault(workspace) / "README.md").exists()
    assert (vault(workspace).parent / "README-vault.md").is_file()


def test_regenerating_removes_notes_that_no_longer_exist(workspace):
    assert runner.invoke(cli.app, []).exit_code == 0
    stray = vault(workspace) / "sem3" / "recznie-dopisana.md"
    stray.write_text("---\ntitle: x\n---\n", encoding="utf-8")

    assert runner.invoke(cli.app, []).exit_code == 0

    assert not stray.exists(), "vault jest generowany — ręczne notatki nie przetrwają"


def test_dry_run_writes_nothing(workspace):
    result = runner.invoke(cli.app, ["--dry-run"])

    assert result.exit_code == 0, result.output
    assert not (workspace.work / "synapse").exists()
    assert "węzły:" in result.output


def test_database_is_not_modified(workspace):
    before = workspace.work_db.read_bytes()

    assert runner.invoke(cli.app, []).exit_code == 0

    assert workspace.work_db.read_bytes() == before


def test_missing_database_is_an_error(workspace):
    workspace.work_db.unlink()

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 1
    assert "brak bazy" in result.output


def test_scope_needs_both_semester_and_skrot(workspace):
    result = runner.invoke(cli.app, ["--skrot", "AKO"])

    assert result.exit_code == 1
    assert "--semester" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_into_material_trees(workspace, tree):
    forbidden = getattr(workspace, tree) / "vault"

    result = runner.invoke(cli.app, ["--out-dir", str(forbidden)])

    assert result.exit_code == 1
    assert not forbidden.exists()
