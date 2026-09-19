"""C3: mapowanie indeksu na model notatek `synapse`. Czysta logika.

Testy pilnują przede wszystkim **kontraktu cudzego prototypu** — pól i dozwolonych
wartości odczytanych z `SynapseVariants.dc.html`. Naruszenie go nie wywala niczego
u nas, tylko psuje graf u użytkownika, więc musi być czerwone tutaj.
"""

from __future__ import annotations

import json

import pytest

from orglib.synapse import (
    CATEGORY_COLORS,
    LEVELS,
    STATUSES,
    Note,
    catalog_colors,
    content_note_id,
    dedupe_ids,
    level_for_content,
    level_for_subject,
    render_markdown,
    slugify,
    status_for_content,
    status_for_subject,
    subject_note_id,
    vault_readme,
    wikilink,
)

#: Pola, po które sięga UI prototypu (`n.id`, `n.title`, … w `SynapseVariants.dc.html`).
PROTOTYPE_FIELDS = {
    "id", "title", "category", "level", "status", "tags", "links", "path", "body",
    "modified", "activity",
}


def note(**overrides) -> Note:
    data = {
        "id": "sem3-ako", "title": "AKO", "category": "SEM3", "level": 2,
        "status": "in-progress", "tags": ["sem3"], "links": [], "body": "treść",
        "modified": "2026-09-19", "activity": ["2026-09-19"],
    }
    data.update(overrides)
    return Note(**data)


# -- kontrakt prototypu -----------------------------------------------------


def test_seed_shape_has_exactly_the_fields_the_prototype_reads() -> None:
    assert set(note().as_seed("paczka")) == PROTOTYPE_FIELDS


def test_allowed_values_are_the_ones_the_prototype_hardcodes() -> None:
    """`levelList=[1,2,3].map(...)` i trzy statusy — wypisane wprost, nie wyliczone."""
    assert LEVELS == (1, 2, 3)
    assert STATUSES == ("completed", "in-progress", "not-started")


@pytest.mark.parametrize("level", [0, 4, 7])
def test_level_outside_the_prototype_filter_is_rejected(level) -> None:
    """Semestr (1-7) nie zmieści się w `level` — dlatego idzie do kategorii i tagów."""
    with pytest.raises(ValueError, match="level"):
        note(level=level).validate()


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="status"):
        note(status="zrobione").validate()


def test_identifier_must_be_a_slug_because_wikilinks_stand_on_it() -> None:
    with pytest.raises(ValueError, match="id"):
        note(id="SEM3 AKO").validate()


def test_path_follows_the_vault_convention() -> None:
    assert note(category="SEM3", id="sem3-ako").path("paczka") == "paczka/sem3/sem3-ako.md"


# -- slug i identyfikatory --------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("Architektura Komputerów", "architektura-komputerow"),
    ("Łódź_2019", "lodz-2019"),
    # 48 znaków limitu, obcięcie nie zostawia myślnika na końcu:
    ("KAIMS_Algorytmy_I_Modelowanie_Systemów", "kaims-algorytmy-i-modelowanie-systemow"),
    ("a" * 60, "a" * 48),
    ("   ", "bez-nazwy"),
    ("...", "bez-nazwy"),
])
def test_slugify_is_ascii_and_stable(raw, expected) -> None:
    assert slugify(raw) == expected


def test_subject_id_adds_the_group_only_when_the_abbreviation_repeats() -> None:
    """SI w SEM7 istnieje dwa razy (KASK vs KT) — bez grupy id byłoby niejednoznaczne."""
    assert subject_note_id(3, "AKO", "Wspolne") == "sem3-ako"
    assert subject_note_id(7, "SI", "KASK_Architektura", ambiguous=True) == "sem7-si-kask-architektura"


def test_content_id_keeps_a_readable_part_and_the_hash() -> None:
    identifier = content_note_id("AKO", "f2b94817" + "0" * 56, "lab_03 instrukcja.pdf")

    assert identifier.startswith("ako-lab-03-instrukcja-pdf-")
    assert identifier.endswith("f2b94817")


def test_duplicate_ids_are_separated_because_wikilinks_would_merge_them() -> None:
    notes = dedupe_ids([note(id="ako-x"), note(id="ako-x"), note(id="ako-y")])

    assert [n.id for n in notes] == ["ako-x", "ako-x-2", "ako-y"]


# -- tłumaczenie stanu potoku ----------------------------------------------


@pytest.mark.parametrize("ground_truth, planned, needs_review, status, level", [
    (0, 0, 0, "not-started", 3),        # nikt tego nie tknął
    (12, 0, 0, "completed", 1),         # leży w paczce, planu nie ma
    (0, 40, 0, "in-progress", 2),       # plan pewny, nic w paczce
    (12, 40, 0, "completed", 2),        # plan pewny i materiały już są
    (12, 40, 7, "in-progress", 3),      # plan czeka na człowieka
])
def test_subject_stage_translates_to_the_prototype_vocabulary(
    ground_truth, planned, needs_review, status, level
) -> None:
    assert status_for_subject(
        ground_truth=ground_truth, planned=planned, needs_review=needs_review
    ) == status
    assert level_for_subject(
        ground_truth=ground_truth, planned=planned, needs_review=needs_review
    ) == level


@pytest.mark.parametrize("in_package, needs_review, confidence, level", [
    (True, False, 1.0, 1),
    (False, False, 0.95, 2),
    (False, True, 0.95, 3),
    (False, False, 0.74, 3),
])
def test_content_level_says_how_settled_the_material_is(
    in_package, needs_review, confidence, level
) -> None:
    assert level_for_content(
        in_package=in_package, needs_review=needs_review,
        confidence=confidence, auto_apply=0.90,
    ) == level


@pytest.mark.parametrize("action, in_package, status", [
    ("copy", False, "in-progress"),
    ("media", False, "in-progress"),
    ("skip", True, "completed"),
    ("skip", False, "not-started"),
    ("quarantine", False, "not-started"),
])
def test_content_status_matches_the_pipeline_stage(action, in_package, status) -> None:
    assert status_for_content(action, in_package=in_package) == status


# -- markdown ---------------------------------------------------------------


def test_markdown_carries_the_front_matter_and_the_body() -> None:
    page = render_markdown(note(links=["sem2-peim"], tags=["sem3", "do-przegladu"]), "paczka")

    assert page.startswith("---\n")
    assert 'id: "sem3-ako"' in page and "level: 2" in page
    assert 'links: ["sem2-peim"]' in page and 'tags: ["sem3", "do-przegladu"]' in page
    assert page.rstrip().endswith("treść")


def test_quotes_in_a_title_do_not_break_the_front_matter() -> None:
    page = render_markdown(note(title='Wykład "Polski czy obcy"'), "paczka")

    assert 'title: "Wykład \\"Polski czy obcy\\""' in page


def test_wikilink_is_the_format_the_prototype_renders() -> None:
    assert wikilink("sem3-ako") == "[[sem3-ako]]"
    assert wikilink("sem3-ako", "Architektura") == "[[sem3-ako|Architektura]]"


def test_colors_cover_every_category_that_appears() -> None:
    colors = catalog_colors([note(category="SEM3"), note(category="kolokwia"), note(category="?")])

    assert colors["SEM3"] == CATEGORY_COLORS["SEM3"]
    assert colors["kolokwia"] == CATEGORY_COLORS["kolokwia"]
    assert colors["?"] == "#8b949e", "nieznana kategoria dostaje kolor domyślny, nie brak koloru"


def test_readme_explains_what_level_means_because_it_is_not_obvious() -> None:
    page = vault_readme([note(), note(category="SEM1")], "paczka", "2026-09-19T00:00:00Z")

    assert "[1, 2, 3]" in page and "semestr" in page
    assert "| SEM1 | 1 |" in page and "| SEM3 | 1 |" in page


def test_seed_payload_is_json_serialisable() -> None:
    """`synapse.json` ma dać się wczytać wprost do prototypu — bez własnego parsera."""
    payload = json.dumps([note().as_seed("paczka")], ensure_ascii=False)

    assert json.loads(payload)[0]["path"] == "paczka/sem3/sem3-ako.md"
