"""C3: model vaulta dla synapse. Czysta logika — bez bazy, plików i generatora.

Testy pilnują kontraktu narzędzia grafu (`studio/graf`), więc wartości, od których
on zależy, są tu wypisane wprost: dozwolone statusy, `id` będące nazwą pliku, kształt
`relations:` we front matterze. Złamanie ich nie wywala niczego u nas — psuje graf.
"""

from __future__ import annotations

import pytest

from orglib.synapse_vault import (
    EDGE_BELONGS_TO,
    LEVEL_IN_PACKAGE,
    LEVEL_NEEDS_HUMAN,
    LEVEL_PLANNED,
    NODE_FILE,
    NODE_SEMESTER,
    NODE_SUBJECT,
    STATUSES,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_TODO,
    Note,
    Relation,
    dedupe_ids,
    file_id,
    file_level,
    file_status,
    render_note,
    semester_id,
    slugify,
    subject_id,
    subject_level,
    subject_status,
    unassigned_id,
    vault_readme,
)


def note(**overrides) -> Note:
    data = {
        "id": "sem3-ako", "title": "AKO", "type": NODE_SUBJECT, "category": "SEM3",
        "body": "treść", "level": 2, "status": STATUS_ACTIVE, "folder": "sem3",
    }
    data.update(overrides)
    return Note(**data)


# -- kontrakt generatora ----------------------------------------------------


def test_allowed_statuses_are_the_ones_the_generator_accepts() -> None:
    """`ConfigurableFrontmatterMapper` zapisze `null` dla czegokolwiek spoza tej trójki."""
    assert STATUSES == ("not-started", "in-progress", "completed")


def test_identifier_is_the_file_name_so_it_must_be_a_slug() -> None:
    assert note(id="sem3-ako").path == "sem3/sem3-ako.md"
    with pytest.raises(ValueError, match="slugiem"):
        note(id="SEM3 AKO").validate()


def test_status_outside_the_contract_is_rejected_here_not_silently_dropped_there() -> None:
    with pytest.raises(ValueError, match="status"):
        note(status="zrobione").validate()


def test_level_must_be_at_least_one() -> None:
    with pytest.raises(ValueError, match="level"):
        note(level=0).validate()
    note(level=None).validate()   # brak poziomu jest dozwolony


def test_duplicate_ids_are_separated_because_they_are_file_names() -> None:
    """Dwa pliki o tym samym rdzeniu dają generatorowi ostrzeżenie `duplicate-id`."""
    notes = dedupe_ids([note(id="ako-x"), note(id="ako-x"), note(id="ako-y")])

    assert [n.id for n in notes] == ["ako-x", "ako-x-2", "ako-y"]


# -- front matter -----------------------------------------------------------


def test_front_matter_carries_every_field_the_mapper_reads() -> None:
    page = render_note(note(
        tags=["sem3", "do-przegladu"], aliases=["AKO"], modified="2026-09-19",
        relations=[Relation("sem3", EDGE_BELONGS_TO), Relation("ako-y", "near_duplicate", 0.78)],
    ))

    assert page.startswith("---\n")
    assert 'type: "subject"' in page and 'category: "SEM3"' in page
    assert "level: 2" in page and 'status: "in-progress"' in page
    assert 'tags: ["sem3", "do-przegladu"]' in page and 'aliases: ["AKO"]' in page
    assert 'modified: "2026-09-19"' in page
    assert '  - target: "sem3"\n    kind: "belongs_to"' in page
    assert '    confidence: 0.78' in page
    assert page.rstrip().endswith("treść")


def test_relation_without_confidence_omits_the_key() -> None:
    page = render_note(note(relations=[Relation("sem3", EDGE_BELONGS_TO)]))

    assert "confidence" not in page


def test_body_has_no_wikilinks_so_every_edge_keeps_its_kind() -> None:
    """`[[wikilink]]` w treści tworzy krawędź rodzaju `link` — zdublowałaby relację."""
    page = render_note(note(
        body="Zobacz notatkę ako-y (bez wikilinku).",
        relations=[Relation("ako-y", "near_duplicate", 0.9)],
    ))

    assert "[[" not in page


def test_quotes_in_a_title_do_not_break_the_front_matter() -> None:
    assert 'title: "Wykład \\"Polski\\""' in render_note(note(title='Wykład "Polski"'))


# -- identyfikatory ---------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("Architektura Komputerów", "architektura-komputerow"),
    ("Łódź_2019", "lodz-2019"),
    ("   ", "bez-nazwy"),
])
def test_slugify_is_ascii(raw, expected) -> None:
    assert slugify(raw) == expected


def test_identifiers_are_stable_and_unique_per_content() -> None:
    sha = "f2b94817" + "0" * 56

    assert semester_id(3) == "sem3"
    assert subject_id(3, "AKO", "Wspolne") == "sem3-ako"
    assert subject_id(7, "SI", "KASK_Arch", ambiguous=True) == "sem7-si-kask-arch"
    assert file_id("AKO", sha, "lab_03 instrukcja.pdf") == "ako-lab-03-instrukcja-pdf-f2b94817"
    assert unassigned_id(sha, "obraz.png").startswith("nieprzypisane-obraz-png-")


# -- tłumaczenie stanu potoku ----------------------------------------------


@pytest.mark.parametrize("in_package, needs_review, confidence, level", [
    (True, False, 1.0, LEVEL_IN_PACKAGE),
    (False, False, 0.95, LEVEL_PLANNED),
    (False, True, 0.95, LEVEL_NEEDS_HUMAN),
    (False, False, 0.74, LEVEL_NEEDS_HUMAN),
])
def test_file_level_says_how_settled_the_material_is(in_package, needs_review, confidence, level) -> None:
    assert file_level(
        in_package=in_package, needs_review=needs_review,
        confidence=confidence, auto_apply=0.90,
    ) == level


@pytest.mark.parametrize("action, in_package, status", [
    ("copy", False, STATUS_ACTIVE),
    ("media", False, STATUS_ACTIVE),
    ("skip", True, STATUS_DONE),
    ("skip", False, STATUS_TODO),
    ("quarantine", False, STATUS_TODO),
])
def test_file_status_matches_the_pipeline_stage(action, in_package, status) -> None:
    assert file_status(action, in_package=in_package) == status


@pytest.mark.parametrize("counts, status, level", [
    ({"ground_truth": 0, "planned": 0, "needs_review": 0}, STATUS_TODO, LEVEL_NEEDS_HUMAN),
    ({"ground_truth": 12, "planned": 0, "needs_review": 0}, STATUS_DONE, LEVEL_IN_PACKAGE),
    ({"ground_truth": 0, "planned": 40, "needs_review": 0}, STATUS_ACTIVE, LEVEL_PLANNED),
    ({"ground_truth": 12, "planned": 40, "needs_review": 7}, STATUS_ACTIVE, LEVEL_NEEDS_HUMAN),
])
def test_subject_stage_translates_to_the_viewer_vocabulary(counts, status, level) -> None:
    assert subject_status(**counts) == status
    assert subject_level(**counts) == level


# -- README vaulta ----------------------------------------------------------


def test_readme_says_what_level_means_and_that_there_is_no_git() -> None:
    page = vault_readme([note(type=NODE_SEMESTER), note(type=NODE_FILE)], "2026-09-19T00:00:00Z")

    assert "L1" in page and "L3" in page
    assert "nie jest repozytorium gita" in page
    assert "--no-git" in page


def test_small_files_are_not_rounded_down_to_zero():
    """„0 kB" ma znaczyć „nie wiem", a nie „mniej niż pół kilobajta"."""
    from orglib.synapse_vault import human_size

    assert human_size(271) == "271 B"
    assert human_size(4096) == "4 kB"
    assert human_size(579843) == "566 kB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(0) == ""
