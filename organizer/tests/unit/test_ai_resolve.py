"""Testy pomocniczych funkcji klasyfikacji AI: manifest, prompt i normalizacja.

Bez CLI, LLM i sieci; dane plikowe powstają wyłącznie w ``tmp_path``.
Konfiguracja i szablon są w pamięci; schemat planu czytamy z repo
(``prompts/plan_line.schema.json``), żeby testy pilnowały realnego kontraktu.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import jsonschema
import pytest

import ai_resolve
from ai_resolve import (
    allowed_categories,
    build_prompt,
    existing_hashes,
    load_schema,
    normalize_decision,
    read_jsonl,
    select_rows,
    wire_schema,
)
from orglib import config
from orglib.llm_client import LLMClient


# -- Dane i izolacja --------------------------------------------------------


SHA = "a" * 64
OTHER_SHA = "b" * 64
CATEGORIES = ("wyklad", "opracowania", "ksiazki", "inne")
TEMPLATE = """Semestr: {{SEMESTER}}
Przedmiot: {{SKROT}} / {{NAZWA}}
Katalog: {{TARGET_DIR}}
Kategorie: {{ALLOWED_CATEGORIES}}
Hash: {{SHA256}}
Plik: {{FILENAME}}
Rozszerzenie: {{EXTENSION}}
Rodzaj: {{CONTENT_KIND}}
Bajty: {{SIZE_BYTES}}
Źródła: {{SOURCE_PATHS}}
Powody: {{REVIEW_REASONS}}
Limit: {{TEXT_HEAD_LIMIT}}
<tekst>{{TEXT_HEAD}}</tekst>
Model: {{MODEL_HINT}}
{"source_sha256":"{{SHA256}}","model":"{{MODEL_HINT}}"}
"""


@pytest.fixture(autouse=True)
def forbid_external_services_and_real_config(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Test nie może wywoływać usług, CLI ani czytać realnej konfiguracji")

    monkeypatch.setattr(LLMClient, "__init__", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(config, "load_yaml", forbidden)
    monkeypatch.setattr(config, "load_paths", forbidden)


@pytest.fixture
def subject() -> config.Subject:
    return config.Subject(
        semester=3,
        skrot="TEST",
        nazwa="Przedmiot_Testowy",
        forms=("W",),
        aliases=(),
        instancja=None,
        strumien=None,
        profil=None,
        katedra=None,
    )


@pytest.fixture
def schema() -> dict[str, Any]:
    # Kanoniczny schemat z repo, nie jego kopia: te testy mają pilnować kontraktu
    # planu, więc muszą się zepsuć, gdy schemat się zmieni, a kod nie.
    return load_schema()


@pytest.fixture
def row() -> dict[str, Any]:
    return {
        "sha256": SHA,
        "source_path": "paczka_testowa/wykład.PDF",
        "source_paths": ["paczka_testowa/wykład.PDF", "kopia/inny.pdf"],
        "needs_review": True,
        "text_head": "Zażółć gęślą jaźń — wykład o pamięci.",
        "content_kind": "document",
        "size_bytes": 1234,
        "review_reasons": ["brak kategorii", "nieznany rok"],
    }


@pytest.fixture
def decision(subject) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_sha256": SHA,
        "action": "copy",
        "target_rel": f"{subject.target_dir}/wykład/wykład.pdf",
        "category": "wyklad",
        "confidence": 0.95,
        "method": "llm",
        "model": "model-testowy",
        "reason": "Nagłówek wykładu w treści.",
        "needs_review": False,
    }


@pytest.fixture
def normalize(row, subject, schema):
    def run(value, **overrides):
        options = {
            "row": row,
            "subject": subject,
            "model": "model-testowy",
            "schema": schema,
            "auto_apply": 0.90,
            "review_min": 0.70,
            "categories": CATEGORIES,
        }
        options.update(overrides)
        result = normalize_decision(value, **options)
        # Każdy poprawny wynik sprawdzamy pełnym, a nie uproszczonym schematem.
        jsonschema.validate(result, schema)
        return result

    return run


# -- read_jsonl -------------------------------------------------------------


def test_read_jsonl_reads_objects_in_order(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    rows = [{"sha256": SHA, "name": "wykład"}, {"sha256": OTHER_SHA}, {}]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    assert read_jsonl(path) == rows


def test_read_jsonl_skips_empty_and_whitespace_lines(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    path.write_text('\n  \n {"index": 1}\n\t\n{"index": 2}\n\n', encoding="utf-8")

    assert read_jsonl(path) == [{"index": 1}, {"index": 2}]


def test_read_jsonl_reports_physical_line_number_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text('{}\n\n{"broken":\n', encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}:3:") as error:
        read_jsonl(path)
    assert isinstance(error.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize("value", ["tekst", 42, 1.5, [], [1], None, True])
def test_read_jsonl_rejects_non_object_with_line_number(tmp_path: Path, value) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text("{}\n\n" + json.dumps(value) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}:3:.*nie jest obiektem"):
        read_jsonl(path)


# -- existing_hashes --------------------------------------------------------


def test_existing_hashes_returns_empty_set_for_missing_file(tmp_path: Path) -> None:
    assert existing_hashes(tmp_path / "missing.jsonl") == set()


def test_existing_hashes_reads_both_keys_and_prefers_source_sha256(tmp_path: Path) -> None:
    path = tmp_path / "plan.jsonl"
    rows = [
        {"source_sha256": SHA, "sha256": "c" * 64},
        {"sha256": OTHER_SHA},
        {"source_sha256": SHA},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    assert existing_hashes(path) == {SHA, OTHER_SHA}


@pytest.mark.parametrize("key", ["source_sha256", "sha256"])
def test_existing_hashes_ignores_non_string_values(tmp_path: Path, key: str) -> None:
    path = tmp_path / "plan.jsonl"
    rows = [{}, *({key: value} for value in [None, 123, True, [], {}, [SHA]]), {key: SHA}]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    assert existing_hashes(path) == {SHA}


# -- select_rows ------------------------------------------------------------


@pytest.mark.parametrize("take_all", [False, True])
def test_select_rows_filters_review_unless_take_all(take_all: bool) -> None:
    manifest = [
        {"sha256": SHA, "needs_review": False},
        {"sha256": OTHER_SHA, "needs_review": True},
        {"sha256": "c" * 64},
    ]

    assert select_rows(manifest, resolved=set(), take_all=take_all) == (
        manifest if take_all else [manifest[1]]
    )


@pytest.mark.parametrize("take_all", [False, True])
def test_select_rows_skips_resolved_and_duplicates_preserving_order(take_all: bool) -> None:
    manifest = [
        {"sha256": "d" * 64, "needs_review": True},
        {"sha256": SHA, "needs_review": True},
        {"source_sha256": OTHER_SHA, "needs_review": True},
        {"source_sha256": "d" * 64, "needs_review": True},
        {"sha256": OTHER_SHA, "needs_review": True},
    ]

    assert select_rows(manifest, resolved={SHA}, take_all=take_all) == [manifest[0], manifest[2]]


def test_select_rows_keeps_review_candidate_after_non_review_duplicate() -> None:
    manifest = [{"sha256": SHA}, {"sha256": SHA, "needs_review": True}]

    assert select_rows(manifest, resolved=set(), take_all=False) == [manifest[1]]


@pytest.mark.parametrize("take_all", [False, True])
@pytest.mark.parametrize("row", [{}, {"sha256": ""}, {"source_sha256": None}, {"sha256": 123}])
def test_select_rows_rejects_missing_or_invalid_hash(row, take_all: bool) -> None:
    with pytest.raises(ValueError, match="bez sha256"):
        select_rows([row], resolved=set(), take_all=take_all)


# -- allowed_categories -----------------------------------------------------


@pytest.fixture
def syntax(monkeypatch):
    # Kontrolowany wariant: kolokwia tylko C/L. Realny YAML dopuszcza też W.
    data = {"categories": {
        "wyklad": {"forms": ["W"]},
        "laboratoria": {"forms": ["L"]},
        "kolokwia": {"forms": ["C", "L"]},
        "cwiczenia": {"forms": ["C"]},
        "opracowania": {"folder": "opracowania"},
        "ksiazki": {"folder": "książki"},
        "inne": {"folder": "inne"},
    }}

    def load_yaml(name):
        assert name == "syntax"
        return data

    monkeypatch.setattr(config, "load_yaml", load_yaml)
    return data


def test_allowed_categories_for_lectures_excludes_labs_and_exercises(subject, syntax) -> None:
    assert allowed_categories(subject) == ["wyklad", "opracowania", "ksiazki", "inne"]


def test_allowed_categories_for_labs_includes_colloquia_but_not_lectures(subject, syntax) -> None:
    assert allowed_categories(replace(subject, forms=("L",))) == [
        "laboratoria", "kolokwia", "opracowania", "ksiazki", "inne",
    ]


def test_allowed_categories_without_forms_always_match(subject, syntax) -> None:
    assert allowed_categories(replace(subject, forms=())) == ["opracowania", "ksiazki", "inne"]


@pytest.mark.parametrize("forms, matches", [(("W",), True), (("C",), True), (("L",), False)])
def test_allowed_categories_matches_any_of_multiple_forms(subject, syntax, forms, matches) -> None:
    syntax["categories"]["kolokwia"]["forms"] = ["W", "C"]

    assert ("kolokwia" in allowed_categories(replace(subject, forms=forms))) is matches


def test_allowed_categories_allows_lecture_colloquia_when_configured(subject, syntax) -> None:
    # Taka lista form jest obecnie w repozytoryjnym syntax.yaml.
    syntax["categories"]["kolokwia"]["forms"] = ["C", "L", "W"]

    assert allowed_categories(subject) == ["wyklad", "kolokwia", "opracowania", "ksiazki", "inne"]


def test_real_syntax_yaml_still_has_the_shape_allowed_categories_depends_on() -> None:
    """Zabezpieczenie przed rozjazdem: testy wyżej stubują ``syntax.yaml``.

    Gdyby ktoś zmienił strukturę pliku (np. przeniósł kategorie pod inny klucz albo
    zamienił ``forms`` na coś innego), tamte testy nadal by przechodziły na stubie,
    a produkcja by się wywaliła. Czytamy więc plik wprost — ``config.load_yaml``
    jest w tym module zablokowany przez fixture.
    """
    import yaml

    data = yaml.safe_load(
        (config.ORGANIZER_ROOT / "config" / "syntax.yaml").read_text(encoding="utf-8")
    )
    categories = data["categories"]

    # Kategorie, na których opiera się kontrakt planu, muszą istnieć…
    assert {"wyklad", "kolokwia", "laboratoria", "cwiczenia", "inne"} <= set(categories)
    # …a enum w schemacie planu i klucze w syntax.yaml muszą opisywać ten sam zbiór.
    assert set(categories) == set(load_schema()["properties"]["category"]["enum"])
    # ``forms`` jest listą liter form zajęć albo go nie ma (kategoria uniwersalna).
    for name, spec in categories.items():
        forms = (spec or {}).get("forms")
        assert forms is None or (
            isinstance(forms, list) and all(isinstance(f, str) and f for f in forms)
        ), f"kategoria {name}: nieoczekiwany kształt forms={forms!r}"


# -- wire_schema ------------------------------------------------------------


@pytest.mark.parametrize("keyword, value", [
    ("pattern", "^[a-z]+$"), ("minimum", 0), ("maximum", 1),
    ("minLength", 1), ("maxLength", 240), ("format", "date"), ("default", None),
])
def test_wire_schema_strips_unsupported_keywords_at_every_depth(keyword, value) -> None:
    original = {
        "type": "object", keyword: value,
        "properties": {"nested": {
            "type": "array", keyword: value,
            "items": {"anyOf": [{"type": "string", keyword: value}, {"type": "null"}]},
        }},
    }
    expected = {
        "type": "object",
        "properties": {"nested": {
            "type": "array",
            "items": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        }},
        "required": ["nested"], "additionalProperties": False,
    }

    assert wire_schema(original) == expected


def test_wire_schema_requires_all_properties_including_optional_fields(schema) -> None:
    result = wire_schema(schema)

    assert set(result["required"]) == set(schema["properties"])
    assert {"year", "related_to", "relation"} <= set(result["required"])


def test_wire_schema_forbids_additional_properties() -> None:
    assert wire_schema({"type": "object", "additionalProperties": True})["additionalProperties"] is False


def test_wire_schema_returns_independent_copy_without_mutating_input(schema) -> None:
    before = deepcopy(schema)
    result = wire_schema(schema)

    assert result is not schema
    assert schema == before
    result["properties"]["action"]["enum"].append("test")
    result["required"].append("test")
    assert schema == before


# -- build_prompt -----------------------------------------------------------


@pytest.mark.parametrize("hash_key", ["sha256", "source_sha256"])
@pytest.mark.parametrize("use_representative", [True, False])
def test_build_prompt_replaces_all_placeholders_and_uses_hash_and_filename(
    row, subject, hash_key, use_representative,
) -> None:
    row.pop("sha256")
    row[hash_key] = SHA
    row["source_paths"] = ["paczka_testowa/pierwszy.pdf", "kopia/drugi.pdf"]
    if not use_representative:
        row.pop("source_path")

    prompt = build_prompt(
        row, subject=subject, template=TEMPLATE, model_hint="model-testowy",
        text_head_limit=200, categories=CATEGORIES,
    )

    assert "{{" not in prompt and "}}" not in prompt
    assert f"Hash: {SHA}" in prompt
    assert f"Plik: {'wykład.PDF' if use_representative else 'pierwszy.pdf'}" in prompt
    assert "Rozszerzenie: .pdf" in prompt
    assert "Kategorie: wyklad, opracowania, ksiazki, inne" in prompt
    assert f"Katalog: {subject.target_dir}" in prompt
    assert f"Przedmiot: {subject.skrot} / {subject.nazwa}" in prompt
    assert "Semestr: 3" in prompt
    assert "Rodzaj: document" in prompt
    assert "Bajty: 1234" in prompt
    assert "Źródła: paczka_testowa/pierwszy.pdf, kopia/drugi.pdf" in prompt
    assert "Powody: brak kategorii, nieznany rok" in prompt
    assert f'<tekst>{row["text_head"]}</tekst>' in prompt
    assert f'{{"source_sha256":"{SHA}","model":"model-testowy"}}' in prompt


@pytest.mark.parametrize("text, limit, expected", [
    ("abcdef", 3, "abc"),
    ("zażółć", 4, "zaż"),
    ("zażółć", 5, "zaż"),
    ("krótki", 100, "krótki"),
])
def test_build_prompt_truncates_text_head_by_utf8_bytes(row, subject, text, limit, expected) -> None:
    row["text_head"] = text
    prompt = build_prompt(
        row, subject=subject, template="<tekst>{{TEXT_HEAD}}</tekst>",
        model_hint="model-testowy", text_head_limit=limit, categories=CATEGORIES,
    )

    assert prompt == f"<tekst>{expected}</tekst>"
    assert len(expected.encode("utf-8")) <= limit


# -- normalize_decision -----------------------------------------------------


@pytest.mark.parametrize("hash_key", ["sha256", "source_sha256"])
def test_normalize_decision_overrides_hash_method_and_model(normalize, decision, hash_key) -> None:
    decision.update(source_sha256=OTHER_SHA, method="manual", model="model-z-odpowiedzi")

    result = normalize(decision, row={hash_key: SHA})

    assert result["source_sha256"] == SHA
    assert result["method"] == "llm"
    assert result["model"] == "model-testowy"


@pytest.mark.parametrize("confidence, action, needs_review", [
    (0.0, "quarantine", True),
    (0.6999, "quarantine", True),
    (0.70, "copy", True),
    (0.8999, "copy", True),
    (0.90, "copy", False),
    (1.0, "copy", False),
])
def test_normalize_decision_enforces_confidence_thresholds(
    normalize, decision, confidence, action, needs_review,
) -> None:
    decision.update(confidence=confidence, needs_review=False)

    result = normalize(decision)

    assert result["confidence"] == confidence
    assert result["action"] == action
    assert result["needs_review"] is needs_review


def test_normalize_decision_uses_supplied_thresholds(normalize, decision) -> None:
    decision["confidence"] = 0.75

    assert normalize(decision, review_min=0.80)["action"] == "quarantine"
    assert normalize(decision, auto_apply=0.75)["needs_review"] is False


def test_normalize_decision_preserves_requested_review_at_high_confidence(normalize, decision) -> None:
    decision["needs_review"] = True

    assert normalize(decision)["needs_review"] is True


def test_normalize_decision_quarantine_always_requires_review(normalize, decision) -> None:
    decision["action"] = "quarantine"

    assert normalize(decision)["needs_review"] is True


def test_normalize_decision_rejects_category_outside_subject_forms(normalize, decision) -> None:
    # laboratoria występują w schemacie, ale nie są dozwolone dla tego przedmiotu.
    decision["category"] = "laboratoria"

    with pytest.raises(ValueError, match="kategoria.*laboratoria.*niedozwolona"):
        normalize(decision)


@pytest.mark.parametrize("target", [None, "", "   ", "\t\n"])
def test_normalize_decision_rejects_copy_with_empty_target(normalize, decision, target) -> None:
    decision["target_rel"] = target

    with pytest.raises(ValueError, match="action=copy bez target_rel"):
        normalize(decision)


def test_normalize_decision_rejects_copy_without_target(normalize, decision) -> None:
    decision.pop("target_rel")

    with pytest.raises(ValueError, match="action=copy bez target_rel"):
        normalize(decision)


def test_normalize_decision_truncates_reason_to_240_characters(normalize, decision) -> None:
    decision["reason"] = "ż" * 241 + "koniec"

    assert normalize(decision)["reason"] == "ż" * 240


def test_normalize_decision_produces_schema_valid_output_without_mutating_input(normalize, decision) -> None:
    before = deepcopy(decision)

    result = normalize(decision)

    assert result is not decision
    assert decision == before
    assert result["year"] is None
    assert result["related_to"] is None
    assert result["relation"] is None


@pytest.mark.parametrize("value", [None, "tekst", 42, []])
def test_normalize_decision_rejects_non_object_response(normalize, value) -> None:
    with pytest.raises(ValueError, match="nie jest obiektem JSON"):
        normalize(value)


def test_normalize_decision_still_validates_against_canonical_constraints(normalize, decision) -> None:
    # Wariant wire_schema usuwa pattern; normalizacja nadal musi go egzekwować.
    with pytest.raises(jsonschema.ValidationError, match="does not match"):
        normalize(decision, row={"sha256": "niepoprawny-hash"})


# --------------------------------------------------------------------------- #
# Bramka zapisu planu (audyt 2026-09-18: nie rozwijała dowiązań symbolicznych)
# --------------------------------------------------------------------------- #


def _paths_for(tmp_path) -> config.Paths:
    """Atrapa workspace'u: wszystkie korzenie w tmp_path, nic realnego."""
    roots = {name: tmp_path / name for name in ("sources", "work", "media", "target")}
    for root in roots.values():
        root.mkdir(exist_ok=True)
    return config.Paths(
        sources=roots["sources"], work=roots["work"], media=roots["media"],
        target_repo=roots["target"], target_paczka=roots["target"] / "paczka",
        work_db=roots["work"] / "organizer.sqlite",
        work_extracted_text=roots["work"] / "text",
        work_thumbnails=roots["work"] / "thumbs",
    )


@pytest.mark.parametrize("protected", ["sources", "target", "media"])
def test_plan_output_in_protected_tree_is_rejected(tmp_path, protected: str) -> None:
    """Zapis planu wprost do drzewa materiałów jest odrzucany."""
    paths = _paths_for(tmp_path)
    target = getattr(paths, {"sources": "sources", "target": "target_repo", "media": "media"}[protected])
    with pytest.raises(ValueError, match="chronionym drzewie"):
        ai_resolve._check_output(target / "plan.ai.jsonl", paths)


@pytest.mark.parametrize("protected", ["sources", "target", "media"])
def test_plan_output_through_symlinked_directory_is_rejected(tmp_path, protected: str) -> None:
    """Katalog-dowiązanie do drzewa materiałów też jest odrzucany.

    To była realna dziura: bramka w ai_resolve używała samego `abspath`, więc
    dowiązanie ją omijało, choć bliźniacza kontrola w prepare_subject blokowała
    ten sam przypadek.
    """
    paths = _paths_for(tmp_path)
    target = getattr(paths, {"sources": "sources", "target": "target_repo", "media": "media"}[protected])
    link = tmp_path / f"skrot-{protected}"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="chronionym drzewie"):
        ai_resolve._check_output(link / "plan.ai.jsonl", paths)


def test_plan_output_as_symlink_file_is_rejected(tmp_path) -> None:
    """Sam plik wyjściowy nie może być dowiązaniem (zapis poszedłby gdzie indziej)."""
    paths = _paths_for(tmp_path)
    link = tmp_path / "plan.ai.jsonl"
    link.symlink_to(tmp_path / "gdzie-indziej.jsonl")
    with pytest.raises(ValueError, match="symlinkiem"):
        ai_resolve._check_output(link, paths)


def test_plan_output_outside_materials_is_allowed(tmp_path) -> None:
    """Zwykły katalog raportów przechodzi — bramka nie może blokować pracy."""
    paths = _paths_for(tmp_path)
    ai_resolve._check_output(tmp_path / "reports" / "AKO" / "plan.ai.jsonl", paths)


def test_prompt_template_placeholders_match_the_code() -> None:
    """Realny szablon promptu i kod muszą znać te same placeholdery.

    Testy budowania promptu używają atrapy szablonu (stała TEMPLATE), więc
    przemianowanie `{{TARGET_DIR}}` w prawdziwym `prompts/classify_ambiguous.md`
    przechodziło wszystkie testy, a do modelu szedł dosłowny `{{TARGET_DIR}}`
    zamiast katalogu docelowego — bez listy kategorii i bez celu (audyt 2026-09-18).
    """
    import re as _re

    template = (config.ORGANIZER_ROOT / "prompts" / "classify_ambiguous.md").read_text(
        encoding="utf-8"
    )
    in_template = set(_re.findall(r"\{\{[A-Z_]+\}\}", template))
    source = (config.ORGANIZER_ROOT / "scripts" / "ai_resolve.py").read_text(encoding="utf-8")
    body = source[source.index("def build_prompt") : source.index("def _thresholds")]
    in_code = set(_re.findall(r'"(\{\{[A-Z_]+\}\})"', body))

    assert in_template == in_code, (
        f"szablon bez wypełnienia w kodzie: {sorted(in_template - in_code)}; "
        f"kod wypełnia nieistniejące: {sorted(in_code - in_template)}"
    )


def test_relate_prompt_template_exists_and_is_not_empty() -> None:
    """Drugi szablon też jest częścią kontraktu — pusty plik to cicha awaria."""
    template = (config.ORGANIZER_ROOT / "prompts" / "relate_cluster.md").read_text(encoding="utf-8")
    assert len(template.strip()) > 100
