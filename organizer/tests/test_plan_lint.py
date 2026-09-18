"""B8: reguły walidacji planu. Czysta logika — bez bazy, CLI i materiałów."""

from __future__ import annotations

import pytest

from orglib import config
from orglib.classify import load_rules
from orglib.plan_lint import (
    MAX_TARGET_LENGTH,
    WINDOWS_RESERVED,
    Finding,
    check_path_safety,
    check_windows_name,
    summarize,
    tree_diff,
    validate_rows,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


@pytest.fixture
def subject() -> config.Subject:
    return config.Subject(
        semester=3, skrot="TEST", nazwa="Przedmiot_Testowy", forms=("W", "L"),
        aliases=(), instancja=None, strumien=None, profil=None, katedra=None,
    )


@pytest.fixture
def rules():
    return load_rules()


def plan_row(**overrides):
    row = {
        "schema_version": 1,
        "source_sha256": SHA_A,
        "action": "copy",
        "target_rel": "paczka/SEM3/TEST_Przedmiot_Testowy/laboratoria/wspólne/lab_03/x.pdf",
        "category": "laboratoria",
        "year": "2020",
        "confidence": 0.95,
        "method": "heuristic",
        "model": "deterministic",
        "reason": "test",
        "needs_review": False,
    }
    row.update(overrides)
    return row


def check(rows, subject, rules, **kwargs):
    return validate_rows(
        rows, subject=subject, rules=rules, auto_apply=0.90, review_min=0.70, **kwargs
    )


def codes(findings):
    return sorted(f.code for f in findings)


# -- nazwy nie do odtworzenia na Windowsie ----------------------------------


@pytest.mark.parametrize("name, fragment", [
    ('Polski - wykład ("a").pdf', 'zawiera'),          # zmierzone: 2 takie nazwy w źródłach
    ("koniec.", "kropką albo spacją"),
    ("koniec ", "kropką albo spacją"),
    ("CON.txt", "zastrzeżona"),
    ("lpt9", "zastrzeżona"),
    ("zwykly plik.pdf", None),
    ("nazwa z kropką w środku.v2.pdf", None),
])
def test_check_windows_name(name, fragment) -> None:
    problems = check_windows_name(f"paczka/SEM3/X/{name}")

    if fragment is None:
        assert problems == []
    else:
        assert any(fragment in problem for problem in problems), problems


def test_too_long_path_is_rejected_with_the_measured_limit() -> None:
    target = "paczka/SEM3/X/" + "a" * MAX_TARGET_LENGTH

    assert any("limit" in problem for problem in check_windows_name(target))
    assert check_windows_name("paczka/SEM3/X/" + "a" * 10) == []


def test_reserved_names_are_the_full_dos_set() -> None:
    """Lista wypisana wprost: skrócenie jej w kodzie ma czerwienić test."""
    assert WINDOWS_RESERVED == {"CON", "PRN", "AUX", "NUL"} | {
        f"COM{i}" for i in range(1, 10)
    } | {f"LPT{i}" for i in range(1, 10)}


@pytest.mark.parametrize("target, broken", [
    ("../poza", True), ("/bezwzgledna", True), ("a//b", True), ("a/../b", True),
    ("a\\b", True), ("", True), ("paczka/SEM3/X/plik.pdf", False),
])
def test_check_path_safety(target, broken) -> None:
    assert bool(check_path_safety(target)) is broken


# -- spójność planu ---------------------------------------------------------


def test_clean_plan_has_no_findings(subject, rules) -> None:
    assert check([plan_row()], subject, rules) == []


def test_two_decisions_for_one_content_are_rejected(subject, rules) -> None:
    findings = check([plan_row(), plan_row(target_rel="paczka/SEM3/TEST_Przedmiot_Testowy/inne/x.pdf",
                               category="inne")], subject, rules)

    assert "podwojna_decyzja" in codes(findings)


def test_two_contents_on_one_path_are_rejected(subject, rules) -> None:
    """Zmierzone na realnym planie AKO: 144 takie kolizje (same pliki `main.c`)."""
    findings = check([plan_row(), plan_row(source_sha256=SHA_B)], subject, rules)

    assert "kolizja_celu" in codes(findings)


def test_the_same_content_may_appear_under_one_path_twice(subject, rules) -> None:
    """Powtórzona linia to podwójna decyzja, ale NIE kolizja — to ta sama treść."""
    findings = check([plan_row(), plan_row()], subject, rules)

    assert "kolizja_celu" not in codes(findings)


def test_overwriting_manually_placed_material_is_an_error(subject, rules) -> None:
    row = plan_row()
    findings = check([row], subject, rules, ground_truth={row["target_rel"]: SHA_B})

    assert "nadpisanie_ground_truth" in codes(findings)


def test_putting_the_same_content_where_it_already_lies_is_fine(subject, rules) -> None:
    row = plan_row()

    assert check([row], subject, rules, ground_truth={row["target_rel"]: SHA_A}) == []


def test_target_outside_the_subject_directory_is_rejected(subject, rules) -> None:
    findings = check([plan_row(target_rel="paczka/SEM3/INNY_Przedmiot/laboratoria/x.pdf")],
                     subject, rules)

    assert "poza_przedmiotem" in codes(findings)


def test_category_must_match_the_folder_on_the_path(subject, rules) -> None:
    findings = check([plan_row(category="wyklad")], subject, rules)

    assert "kategoria_vs_sciezka" in codes(findings)


def test_media_must_leave_the_package(subject, rules) -> None:
    inside = plan_row(action="media", target_rel="paczka/SEM3/TEST_Przedmiot_Testowy/inne/a.mp3",
                      category="inne")
    outside = plan_row(action="media", target_rel="90_MEDIA/TEST/a.mp3", category="inne")

    assert "media_w_paczce" in codes(check([inside], subject, rules))
    assert check([outside], subject, rules) == []


@pytest.mark.parametrize("confidence, needs_review, expected", [
    (0.95, False, []),
    (0.80, True, []),
    (0.80, False, ["brak_review"]),
    (0.50, True, ["pewnosc_ponizej_progu"]),
])
def test_confidence_gate(subject, rules, confidence, needs_review, expected) -> None:
    findings = check([plan_row(confidence=confidence, needs_review=needs_review)], subject, rules)

    assert codes(findings) == expected


def test_quarantine_below_the_threshold_is_allowed(subject, rules) -> None:
    """Bramka dotyczy KOPIOWANIA. Kwarantanna z niską pewnością to poprawny wynik."""
    findings = check(
        [plan_row(action="quarantine", confidence=0.0, needs_review=True)], subject, rules
    )

    assert codes(findings) == []


def test_unpadded_slot_number_is_only_a_warning(subject, rules) -> None:
    findings = check(
        [plan_row(target_rel="paczka/SEM3/TEST_Przedmiot_Testowy/laboratoria/wspólne/lab_3/x.pdf")],
        subject, rules,
    )

    assert [f.level for f in findings] == ["warning"]
    assert codes(findings) == ["numer_bez_dopelnienia"]


@pytest.mark.parametrize("year", ["20", "2020/2021", 2020])
def test_year_must_be_four_digits_or_absent(subject, rules, year) -> None:
    assert "rok" in codes(check([plan_row(year=year)], subject, rules))
    assert "rok" not in codes(check([plan_row(year=None)], subject, rules))


def test_row_without_sha_is_reported_once(subject, rules) -> None:
    findings = check([{"action": "copy", "target_rel": "x", "confidence": 1.0}], subject, rules)

    assert codes(findings) == ["brak_sha"]


# -- podsumowanie i dry-run -------------------------------------------------


def test_summarize_counts_levels() -> None:
    counts = summarize([Finding("error", "a", ""), Finding("warning", "b", ""), Finding("error", "c", "")])

    assert counts == {"error": 2, "warning": 1}


def test_tree_diff_lists_only_what_would_appear() -> None:
    diff = tree_diff([
        plan_row(),
        plan_row(action="skip", target_rel="paczka/SEM3/TEST_Przedmiot_Testowy/inne/pominiete.pdf"),
        plan_row(action="media", target_rel="90_MEDIA/TEST/a.mp3"),
    ])

    assert diff["files"] == [
        "90_MEDIA/TEST/a.mp3",
        "paczka/SEM3/TEST_Przedmiot_Testowy/laboratoria/wspólne/lab_03/x.pdf",
    ]
    assert diff["folders"] == [
        "90_MEDIA/TEST",
        "paczka/SEM3/TEST_Przedmiot_Testowy/laboratoria/wspólne/lab_03",
    ]
