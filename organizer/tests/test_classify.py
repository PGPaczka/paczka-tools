"""B3: reguły klasyfikacji — kontrakt silnika i wiązanie z realnym configiem.

Dwie warstwy w jednym pliku, świadomie:

* testy na STUBIE configu — sprawdzają zachowanie reguł niezależnie od tego, co
  ktoś dziś wpisał do YAML-a (progi, słowa kluczowe, szablony ścieżek);
* testy czytające REALNE ``config/*.yaml`` i ``prompts/plan_line.schema.json`` —
  pilnują, że stub nie odkleił się od produkcji. Bez nich cała warstwa wyżej
  przechodziłaby na zielono po dowolnej zmianie struktury pliku.

Bez sieci, bez CLI, bez bazy i bez czytania materiałów.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import jsonschema
import pytest
import yaml

from orglib import config
from orglib.classify import (
    GroundTruth,
    IDENTITY_REVIEW_REASONS,
    allowed_categories,
    classify_row,
    detect_numbers,
    detect_prowadzacy,
    detect_year,
    fold,
    is_ignored,
    load_rules,
    render_best,
    render_template,
    unambiguous_labels,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64

SYNTAX = {
    "meta": {"number_padding": 2},
    "categories": {
        "egzamin": {"folder": "egzamin", "priority": 10, "keywords": ["egzamin"]},
        "kolokwia": {
            "folder": "kolokwia",
            "target_templates": ["kolokwia/kol_0{nr_kolosa}", "kolokwia"],
            "forms": ["C", "L", "W"],
            "priority": 20,
            "keywords": ["kolokw"],
        },
        "laboratoria": {
            "folder": "laboratoria",
            "target_templates": [
                "laboratoria/{prowadzacy}/lab_0{nr_laby}",
                "laboratoria/wspólne/lab_0{nr_laby}",
                "laboratoria",
            ],
            "forms": ["L"],
            "priority": 30,
            "keywords": ["lab"],
        },
        "cwiczenia": {
            "folder": "ćwiczenia",
            "target_templates": ["ćwiczenia/{prowadzacy}", "ćwiczenia"],
            "forms": ["C"],
            "priority": 40,
            "keywords": ["cwicz", "cw"],
        },
        "wyklad": {"folder": "wykład", "forms": ["W"], "priority": 60, "keywords": ["wyklad"]},
        "opracowania": {"folder": "opracowania", "priority": 70, "keywords": ["notatk"]},
        "ksiazki": {"folder": "inne/książki", "priority": 80, "keywords": ["ksiazk"]},
        "inne": {"folder": "inne", "priority": 90},
    },
    "ignore": {"reason": "artefakt", "extensions": ["obj", "tlog"], "folders": ["Debug"]},
    "media": {
        "extensions": ["mp3", "mp4"],
        "threshold_bytes": 26214400,
        "target_outside_repo": "90_MEDIA/{skrot}/{opis}",
    },
    "outdated": {"folder": "outdated", "legacy_folders": ["stara_paczka"]},
}

THRESHOLDS = {
    "confidence": {"auto_apply": 0.90, "review_min": 0.70},
    "classify": {
        "weight_filename": 0.95,
        "weight_folder": 0.90,
        "weight_text": 0.74,
        "conflict_penalty": 0.12,
        "manifest_review_cap": 0.89,
        "ground_truth_confidence": 1.0,
        "media_confidence": 0.99,
        "ignore_confidence": 0.99,
    },
}


@pytest.fixture(autouse=True)
def forbid_real_config(monkeypatch, request):
    """Stub musi być jedynym źródłem reguł — poza testami, które jawnie czytają repo."""
    if request.node.get_closest_marker("reads_repo_config"):
        return

    def forbidden(*args, **kwargs):
        pytest.fail("Test reguł nie może czytać realnej konfiguracji")

    monkeypatch.setattr(config, "load_yaml", forbidden)
    monkeypatch.setattr(config, "load_thresholds", forbidden)
    monkeypatch.setattr(config, "load_paths", forbidden)


@pytest.fixture
def rules():
    return load_rules(SYNTAX, THRESHOLDS)


@pytest.fixture
def subject() -> config.Subject:
    return config.Subject(
        semester=3, skrot="TEST", nazwa="Przedmiot_Testowy",
        forms=("W", "C", "L"), aliases=("TST",),
        instancja=None, strumien=None, profil=None, katedra=None,
    )


def manifest_row(**overrides):
    row = {
        "sha256": SHA,
        "source_sha256": SHA,
        "source_path": "P/SEM3/TEST/plik.pdf",
        "source_paths": ["P/SEM3/TEST/plik.pdf"],
        "matched_source_paths": ["P/SEM3/TEST/plik.pdf"],
        "content_kind": "pdf",
        "size_bytes": 1024,
        "needs_review": False,
        "review_reasons": [],
    }
    row.update(overrides)
    return row


def decide(row, subject, rules, **kwargs):
    outcome = classify_row(row, subject=subject, rules=rules, **kwargs)
    assert outcome.decision is not None, f"oczekiwano decyzji, jest unresolved: {outcome.reasons}"
    return outcome.decision


# -- normalizacja i pola pomocnicze -----------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("Wykład", "wyklad"), ("ĆWICZENIA", "cwiczenia"), ("Łódź", "lodz"),
    ("Architektura Komputerów", "architektura komputerow"),
])
def test_fold_removes_case_and_diacritics(raw, expected) -> None:
    assert fold(raw) == expected


@pytest.mark.parametrize("template, values, expected", [
    ("kolokwia/kol_0{nr_kolosa}", {"nr_kolosa": "3"}, "kolokwia/kol_03"),
    ("kolokwia/kol_0{nr_kolosa}", {"nr_kolosa": "12"}, "kolokwia/kol_12"),
    ("kolokwia/kol_0{nr_kolosa}", {"nr_kolosa": "03"}, "kolokwia/kol_03"),
    ("projekt/{rok}_0{nr_projektu}", {"rok": "2020", "nr_projektu": "2"}, "projekt/2020_02"),
    ("ćwiczenia/{prowadzacy}", {"prowadzacy": "nowak"}, "ćwiczenia/nowak"),
])
def test_render_template_pads_only_the_padded_fields(template, values, expected) -> None:
    assert render_template(template, values, 2) == expected


@pytest.mark.parametrize("values", [{}, {"nr_kolosa": ""}, {"inne": "1"}])
def test_render_template_without_value_is_none(values) -> None:
    assert render_template("kolokwia/kol_0{nr_kolosa}", values, 2) is None


def test_render_best_prefers_the_most_specific_complete_template(rules) -> None:
    templates = rules.category("laboratoria").templates

    assert render_best(templates, {"nr_laby": "5", "prowadzacy": "nowak"}, 2) == (
        "laboratoria/nowak/lab_05"
    )
    # Bez prowadzącego wchodzi wariant „wspólne”, a nie ścieżka z dziurą.
    assert render_best(templates, {"nr_laby": "5"}, 2) == "laboratoria/wspólne/lab_05"
    # Bez numeru zostaje sam folder kategorii — numer NIE jest zmyślany.
    assert render_best(templates, {}, 2) == "laboratoria"


def test_render_best_drops_only_the_segment_it_cannot_fill(rules) -> None:
    assert render_best(["a/{brak}/b"], {}, 2) == "a/b"


@pytest.mark.parametrize("texts, expected", [
    (["ako2020/lab.pdf"], "2020"),
    (["paczka 2023_2024/lab.pdf"], "2023"),      # rok akademicki => rok początkowy
    (["2019 i 2024 razem"], None),               # sprzeczne => nie zgadujemy
    (["numer 20231015"], None),                  # fragment dłuższej liczby to nie rok
    (["archiwum 1899"], None),                   # przed YEAR_MIN
    (["plan na 2099"], None),                    # po przyszłym roku
    (["bez roku"], None),
])
def test_detect_year(texts, expected) -> None:
    assert detect_year(texts, today=date(2026, 9, 18)) == expected


@pytest.mark.parametrize("text, expected", [
    ("ako_2020_lab_03_instrukcja", {"nr_laby": "03"}),
    ("lab5zad2", {"nr_laby": "5"}),
    ("kolokwium2", {"nr_kolosa": "2"}),
    ("ako_lab2023_cw6", {}),                     # 'lab2023' to rok, nie numer laborki
    ("lab_01 i lab_02 razem", {}),               # sprzeczne numery => żadnego
    ("wyklad_07", {"nr_wykladu": "07"}),
])
def test_detect_numbers(text, expected) -> None:
    assert detect_numbers(fold(text)) == expected


@pytest.mark.parametrize("segments, expected", [
    (["dr Kowalski"], "kowalski"),
    (["mgr_inz_Nowak"], "inz_nowak"),
    (["Kowalski"], None),                        # samo nazwisko jest nieodróżnialne od tematu
    (["laboratoria"], None),
])
def test_detect_prowadzacy_only_with_a_title(segments, expected) -> None:
    assert detect_prowadzacy(segments) == expected


def test_allowed_categories_follows_forms(subject, rules) -> None:
    assert "laboratoria" in allowed_categories(subject, rules)
    assert "laboratoria" not in allowed_categories(replace(subject, forms=("W",)), rules)
    # Kategoria bez `forms` pasuje zawsze.
    assert {"egzamin", "opracowania", "inne"} <= set(
        allowed_categories(replace(subject, forms=()), rules)
    )


def test_unambiguous_labels_exclude_names_used_in_other_semesters(subject) -> None:
    other = replace(subject, semester=7, nazwa="Inny_Przedmiot", aliases=("TST",))

    labels = unambiguous_labels(subject, [subject, other])

    assert "test przedmiot testowy" in labels
    assert "tst" not in labels          # alias prowadzi też do semestru 7
    assert "test" not in labels         # skrót również (to jest dokładnie kolizja AK/SI)

    # Grupa jest wspólna dla dziesiątek przedmiotów i nie może nikogo unieważnić:
    # przedmiot z innego semestru, ale tej samej grupy, nie zabiera nam żadnej nazwy.
    inna_grupa = config.Subject(
        semester=7, skrot="INNY", nazwa="Inny", forms=(), aliases=(),
        instancja=None, strumien=None, profil=None, katedra=None,
    )
    assert unambiguous_labels(subject, [subject, inna_grupa]) == frozenset(
        {"test", "przedmiot testowy", "test przedmiot testowy", "tst"}
    )


# -- deterministyka ---------------------------------------------------------


def test_ground_truth_wins_over_every_heuristic(subject, rules) -> None:
    row = manifest_row(source_path="P/laboratoria/lab_03/plik.pdf",
                       source_paths=["P/laboratoria/lab_03/plik.pdf"],
                       matched_source_paths=["P/laboratoria/lab_03/plik.pdf"])
    truth = {SHA: GroundTruth(
        target_relative_path="paczka/SEM3/TEST_Przedmiot_Testowy/egzamin/x.pdf",
        semester=3, subject_key="TEST", category="egzamin",
    )}

    decision = decide(row, subject, rules, ground_truth=truth)

    assert decision["action"] == "skip"
    assert decision["confidence"] == 1.0
    assert decision["method"] == "deterministic"
    assert decision["category"] == "egzamin"
    assert decision["target_rel"].endswith("egzamin/x.pdf")
    assert decision["needs_review"] is False


def test_ground_truth_under_another_subject_goes_to_review(subject, rules) -> None:
    truth = {SHA: GroundTruth(
        target_relative_path="paczka/SEM7/INNY_Inny/wykład/x.pdf",
        semester=7, subject_key="INNY", category="wykład",
    )}

    decision = decide(manifest_row(), subject, rules, ground_truth=truth)

    assert decision["action"] == "skip"
    assert decision["needs_review"] is True
    assert "innym przedmiotem" in decision["reason"]


def test_ground_truth_of_a_nested_category_keeps_its_root(subject, rules) -> None:
    """``inne`` nie może stać się ``ksiazki`` tylko dlatego, że książki leżą w ``inne``."""
    truth = {SHA: GroundTruth(
        target_relative_path="paczka/SEM3/TEST_Przedmiot_Testowy/inne/x.pdf",
        semester=3, subject_key="TEST", category="inne",
    )}

    assert decide(manifest_row(), subject, rules, ground_truth=truth)["category"] == "inne"


@pytest.mark.parametrize("path", [
    "P/SEM3/TEST/lab/main.obj",
    "P/SEM3/TEST/lab/x.tlog",
    "P/SEM3/TEST/lab/Debug/main.c",
])
def test_build_artifacts_are_skipped(subject, rules, path) -> None:
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    decision = decide(row, subject, rules)

    assert decision["action"] == "skip"
    assert decision["method"] == "deterministic"
    assert decision["reason"] == "artefakt"
    assert decision["needs_review"] is False


def test_content_with_one_clean_copy_is_not_an_artifact(subject, rules) -> None:
    """Ta sama treść leżąca też poza ``Debug/`` jest materiałem — pomijamy dopiero komplet."""
    paths = ["P/SEM3/TEST/lab/Debug/main.c", "P/SEM3/TEST/laboratoria/main.c"]
    row = manifest_row(source_path=paths[1], source_paths=paths, matched_source_paths=paths)

    decision = decide(row, subject, rules)

    assert decision["action"] == "copy"
    assert decision["category"] == "laboratoria"


def test_media_extension_leaves_the_package(subject, rules) -> None:
    path = "P/SEM3/TEST/Nagrania/wykład_01.mp3"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path],
                       content_kind="media")

    decision = decide(row, subject, rules)

    assert decision["action"] == "media"
    assert decision["target_rel"] == "90_MEDIA/TEST/wykład_01.mp3"
    assert decision["confidence"] == 0.99


def test_content_without_healthy_source_is_quarantined(subject, rules) -> None:
    row = manifest_row(source_path=None, review_reasons=["no_unique_source"])

    decision = decide(row, subject, rules)

    assert decision["action"] == "quarantine"
    assert decision["needs_review"] is True
    assert decision["confidence"] == 0.0


# -- heurystyka -------------------------------------------------------------


def test_filename_signal_is_strong_enough_for_auto(subject, rules) -> None:
    path = "P/SEM3/TEST/materialy/lab_03_instrukcja.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    decision = decide(row, subject, rules)

    assert decision["category"] == "laboratoria"
    assert decision["confidence"] == 0.95
    assert decision["method"] == "heuristic"
    assert decision["needs_review"] is False
    assert decision["target_rel"] == (
        "paczka/SEM3/TEST_Przedmiot_Testowy/laboratoria/wspólne/lab_03/lab_03_instrukcja.pdf"
    )


def test_nearest_folder_beats_the_shallower_one(subject, rules) -> None:
    """``Ćwiczenia/2018/kolokwium2/zad.c`` to kolokwium leżące w dziale ćwiczeń."""
    path = "P/SEM3/TEST/Ćwiczenia/2018/kolokwium2/zad.c"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    decision = decide(row, subject, rules)

    assert decision["category"] == "kolokwia"
    assert decision["confidence"] == 0.90       # bez kary za konflikt — to nie remis
    assert decision["needs_review"] is False
    assert decision["target_rel"].endswith("kolokwia/kol_02/zad.c")


def test_two_categories_in_one_name_cost_the_conflict_penalty(subject, rules) -> None:
    path = "P/SEM3/TEST/x/lab_02_cwiczenie.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    decision = decide(row, subject, rules)

    assert decision["category"] == "kolokwia" or decision["category"] == "laboratoria"
    assert decision["confidence"] == pytest.approx(0.95 - 0.12)
    assert decision["needs_review"] is True
    assert "konflikt" in decision["reason"]


def test_priority_resolves_a_tie(subject, rules) -> None:
    path = "P/SEM3/TEST/x/egzamin_kolokwium.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    # egzamin (priority 10) wygrywa z kolokwia (20) przy identycznej sile sygnału.
    assert decide(row, subject, rules)["category"] == "egzamin"


def test_text_head_alone_never_reaches_auto(subject, rules) -> None:
    row = manifest_row(text_head="Instrukcja do laboratorium numer 3")

    decision = decide(row, subject, rules)

    assert decision["category"] == "laboratoria"
    assert decision["confidence"] == 0.74
    assert decision["needs_review"] is True
    # Numeru z treści nie bierzemy — head tekstu opisuje temat, nie miejsce w strukturze.
    assert decision["target_rel"].endswith("laboratoria/plik.pdf")


def test_form_of_the_subject_rejects_a_category(rules, subject) -> None:
    lecture_only = replace(subject, forms=("W",))
    path = "P/SEM3/TEST/Laby/lab_03/notatki_wlasne.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    decision = decide(row, lecture_only, rules)

    assert decision["category"] == "opracowania"
    outcome = classify_row(row, subject=lecture_only, rules=rules)
    assert "forma_przedmiotu_wyklucza:laboratoria" in outcome.reasons


def test_subject_name_in_the_path_is_not_a_category_signal(rules) -> None:
    """Przedmiot „Projekt Grupowy” nie może klasyfikować wszystkiego na ``projekt``."""
    grupowy = config.Subject(
        semester=5, skrot="PGI", nazwa="Projekt_Grupowy_I", forms=("P",),
        aliases=(), instancja=None, strumien="Wspolne", profil=None, katedra=None,
    )
    path = "P/SEM5/PGI_Projekt_Grupowy_I/plik.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])

    outcome = classify_row(row, subject=grupowy, rules=load_rules(SYNTAX, THRESHOLDS))

    assert outcome.decision is None
    assert "brak_sygnalu_kategorii" in outcome.unresolved["classify_reasons"]


def test_without_any_signal_the_row_goes_to_ai(subject, rules) -> None:
    outcome = classify_row(manifest_row(), subject=subject, rules=rules)

    assert outcome.decision is None
    assert outcome.unresolved["sha256"] == SHA
    assert outcome.unresolved["needs_review"] is True
    assert outcome.unresolved["classify_reasons"] == ["brak_sygnalu_kategorii"]
    # Kształt manifestu zostaje — ten plik da się podać ai_resolve jako --manifest.
    assert outcome.unresolved["source_paths"] == manifest_row()["source_paths"]


def test_conflict_in_text_head_falls_below_review_and_goes_to_ai(subject, rules) -> None:
    outcome = classify_row(
        manifest_row(text_head="kolokwium z laboratorium"), subject=subject, rules=rules
    )

    assert outcome.decision is None
    assert outcome.unresolved["classify_best_confidence"] == pytest.approx(0.74 - 0.12)


# -- powody review z manifestu ---------------------------------------------


def test_identity_doubt_from_the_manifest_blocks_auto(subject, rules) -> None:
    path = "P/SEM3/TEST/lab_03_instrukcja.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path],
                       needs_review=True, review_reasons=["ambiguous_subject"])

    decision = decide(row, subject, rules)

    assert decision["confidence"] == 0.89
    assert decision["needs_review"] is True
    assert "ambiguous_subject" in decision["reason"]


def test_missing_semester_blocks_auto_only_when_the_name_is_ambiguous(subject, rules) -> None:
    path = "P/losowy_katalog/lab_03_instrukcja.pdf"
    row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path],
                       needs_review=True, review_reasons=["missing_semester"])

    # Nazwa przedmiotu nie pada w ścieżce => brak semestru jest realnym ryzykiem.
    assert decide(row, subject, rules)["confidence"] == 0.89

    named = "P/Przedmiot Testowy/lab_03_instrukcja.pdf"
    row_named = manifest_row(source_path=named, source_paths=[named], matched_source_paths=[named],
                             needs_review=True, review_reasons=["missing_semester"])
    decision = decide(row_named, subject, rules,
                      safe_labels=frozenset({"przedmiot testowy"}))

    assert decision["confidence"] == 0.95
    assert decision["needs_review"] is False


def test_identity_reasons_are_the_documented_set() -> None:
    """Lista wypisana wprost: skrócenie jej w kodzie ma czerwienić test, nie chować się."""
    assert set(IDENTITY_REVIEW_REASONS) == {
        "ambiguous_subject",
        "conflicting_semesters",
        "conflicting_groups",
        "conflicting_source_subjects",
        "inconsistent_sizes",
        "no_unique_source",
    }


def test_row_without_sha256_is_an_error(subject, rules) -> None:
    with pytest.raises(ValueError, match="bez sha256"):
        classify_row({"source_path": "P/x.pdf"}, subject=subject, rules=rules)


# -- wiązanie z realnym repo ------------------------------------------------


def real_yaml(name: str) -> dict:
    return yaml.safe_load(
        (config.ORGANIZER_ROOT / "config" / f"{name}.yaml").read_text(encoding="utf-8")
    )


@pytest.mark.reads_repo_config
def test_real_syntax_yaml_has_every_field_the_classifier_reads() -> None:
    syntax = real_yaml("syntax")
    categories = syntax["categories"]

    for name, spec in categories.items():
        assert spec.get("folder"), f"kategoria {name} bez 'folder'"
        assert isinstance(spec.get("priority"), int), f"kategoria {name} bez 'priority'"
        for template in spec.get("target_templates") or []:
            # Szablon MUSI wychodzić z folderu kategorii — inaczej `folder` i
            # `target_templates` zaczęłyby opisywać dwie różne struktury.
            assert template.split("/")[0] == spec["folder"].split("/")[0], (
                f"kategoria {name}: szablon {template!r} nie zaczyna się folderem kategorii"
            )
    priorities = [spec["priority"] for spec in categories.values()]
    assert len(priorities) == len(set(priorities)), "priorytety kategorii muszą być rozłączne"
    assert (syntax["ignore"]["extensions"] and syntax["ignore"]["folders"]), "pusta lista ignore"


@pytest.mark.reads_repo_config
def test_real_thresholds_keep_the_meaning_of_each_weight() -> None:
    thresholds = real_yaml("thresholds")
    weights = thresholds["classify"]
    gates = thresholds["confidence"]

    # Nazwa pliku jest mocniejsza od katalogu, katalog wystarcza na auto,
    # a sama głowa tekstu nigdy nie wystarcza (ale nie spada od razu do AI).
    assert weights["weight_filename"] >= weights["weight_folder"] >= gates["auto_apply"]
    assert gates["review_min"] <= weights["weight_text"] < gates["auto_apply"]
    # Konflikt kategorii musi realnie spychać decyzję pod próg auto.
    assert weights["weight_filename"] - weights["conflict_penalty"] < gates["auto_apply"]
    assert weights["manifest_review_cap"] < gates["auto_apply"]


@pytest.mark.reads_repo_config
def test_real_rules_produce_schema_valid_decisions() -> None:
    """Pełny obieg na realnym configu: decyzja MUSI przejść schemat planu."""
    rules = load_rules()
    schema = yaml.safe_load(
        (config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json").read_text(encoding="utf-8")
    )
    subject = config.find_subject(3, "AKO")
    paths = [
        "P/SEM3/AKO/Laby/lab_03/instrukcja.pdf",
        "P/SEM3/AKO/Egzamin/2019/zadanie.png",
        "P/SEM3/AKO/Nagrania/wyklad.mp3",
        "P/SEM3/AKO/Laby/Debug/a.obj",
    ]
    for path in paths:
        row = manifest_row(source_path=path, source_paths=[path], matched_source_paths=[path])
        decision = classify_row(row, subject=subject, rules=rules).decision
        assert decision is not None, path
        jsonschema.validate(decision, schema)
        assert decision["category"] in schema["properties"]["category"]["enum"]


@pytest.mark.reads_repo_config
def test_real_categories_match_the_plan_schema_and_the_ground_truth_folders() -> None:
    rules = load_rules()
    schema = yaml.safe_load(
        (config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json").read_text(encoding="utf-8")
    )

    assert {c.name for c in rules.categories} == set(schema["properties"]["category"]["enum"])
    # Decyzja użytkownika 2026-09-18, wyprowadzona z pomiaru repo docelowego.
    assert rules.category("egzamin").folder == "egzamin"
    assert rules.category("ksiazki").folder == "inne/książki"
    assert rules.category("seminarium").forms == frozenset({"S"})
    assert "stara paczka" not in rules.outdated_folders  # `stara_paczka` to jeden token
    assert {"outdated", "stara_paczka"} <= set(rules.outdated_folders)


@pytest.mark.reads_repo_config
@pytest.mark.parametrize("path, ignored", [
    ("P/x/Debug/a.c", True), ("P/x/a.obj", True), ("P/x/a.tlog", True),
    ("P/x/a.pdf", False), ("P/laboratoria/main.c", False),
])
def test_real_ignore_list_covers_the_measured_build_artifacts(path, ignored) -> None:
    assert is_ignored(path, load_rules()) is ignored
