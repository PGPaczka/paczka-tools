"""CLI B9: strona przeglądu. Sprawdzamy, że jest kompletna, bezpieczna i nic nie psuje.

„Bezpieczna” znaczy tu dwie rzeczy: nazwy plików ze źródeł trafiają do HTML-a jako
TEKST (nie znaczniki), a ze źródeł wyłącznie czytamy.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser

import pytest
from typer.testing import CliRunner

import review_report as cli
from orglib import config

runner = CliRunner()
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_IMG_1 = "c" * 64
SHA_IMG_2 = "d" * 64


class Balanced(HTMLParser):
    """Minimalna kontrola poprawności: żaden znacznik nie zostaje otwarty."""

    VOID = {"img", "br", "meta", "input", "hr", "link"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            self.stack.remove(tag)


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
    paths.work_extracted_text.mkdir(parents=True)
    (paths.sources / "P" / "AKO").mkdir(parents=True)
    monkeypatch.setattr(config, "load_paths", lambda: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    return paths


def write(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def plan_row(sha, **overrides):
    row = {
        "schema_version": 1, "source_sha256": sha, "action": "copy",
        "target_rel": f"paczka/SEM3/AKO_Architektura_Komputerów/kolokwia/{sha[:4]}.pdf",
        "category": "kolokwia", "year": None, "related_to": None, "relation": None,
        "confidence": 0.95, "method": "heuristic", "model": "deterministic",
        "reason": "test", "needs_review": False,
    }
    row.update(overrides)
    return row


@pytest.fixture
def inputs(tmp_path, workspace):
    base = tmp_path / "reports"
    base.mkdir()
    write(base / "manifest_slice.jsonl", [
        {"sha256": SHA_A, "source_path": "P/AKO/a.txt", "content_kind": "text", "size_bytes": 10},
        {"sha256": SHA_B, "source_path": "P/AKO/b.txt", "content_kind": "text", "size_bytes": 12},
    ])
    write(base / "plan.jsonl", [
        {"_meta": {"subject_key": "AKO", "semester": 3, "target_dir": "paczka/SEM3/AKO_X",
                   "plan_hash": "f" * 64, "created_at": "2026-09-19T00:00:00Z"}},
        plan_row(SHA_A, needs_review=True, confidence=0.74),
        plan_row(SHA_B),
    ])
    write(base / "relations.jsonl", [{
        "source_sha256": SHA_A, "target_sha256": SHA_B,
        "relation_type": "older_version", "confidence": 0.9,
    }])
    write(base / "unresolved.jsonl", [
        {"sha256": "e" * 64, "source_path": "P/AKO/zagadka.zip", "content_kind": "archive",
         "classify_reasons": ["brak_sygnalu_kategorii"]}
    ])
    (workspace.work_extracted_text / f"{SHA_A}.txt").write_text(
        "wykład 1\nlinia druga\nstara wersja\n", encoding="utf-8"
    )
    (workspace.work_extracted_text / f"{SHA_B}.txt").write_text(
        "wykład 1\nlinia druga\nnowa wersja z dopiskiem\n", encoding="utf-8"
    )
    return base


def invoke(inputs, *args):
    return runner.invoke(cli.app, [
        "--semester", "3", "--skrot", "AKO",
        "--manifest", str(inputs / "manifest_slice.jsonl"), *args,
    ])


def test_page_has_every_section_and_a_real_diff(workspace, inputs):
    result = invoke(inputs)

    assert result.exit_code == 0, result.output
    page = (inputs / "review.html").read_text(encoding="utf-8")
    for heading in ("Ustalenia walidacji", "Pozycje do obejrzenia", "Nierozstrzygnięte",
                    "Podobne treści", "Poza paczkę", "Drzewo po zmianie"):
        assert heading in page
    # Diff naprawdę porównał teksty z etapu extract, a nie wypisał komunikat zastępczy.
    # Szukamy pojedynczych słów: `difflib.HtmlDiff` zamienia spacje na `&nbsp;`.
    assert "dopiskiem" in page and "diff_add" in page
    assert "brak wyekstrahowanego tekstu" not in page
    assert "starsza kontra nowsza wersja" in page
    assert "zagadka.zip" in page

    parser = Balanced()
    parser.feed(page)
    assert parser.stack == [], f"niedomknięte znaczniki: {parser.stack[:5]}"


def test_file_names_from_the_sources_are_escaped(workspace, tmp_path, inputs):
    """Nazwy plików pochodzą z cudzych paczek — do HTML-a mają trafić jako tekst."""
    evil = '<script>alert("x")</script>.pdf'
    write(inputs / "manifest_slice.jsonl", [
        {"sha256": SHA_A, "source_path": f"P/AKO/{evil}", "content_kind": "text", "size_bytes": 10},
    ])
    write(inputs / "plan.jsonl", [
        {"_meta": {"subject_key": "AKO", "semester": 3, "plan_hash": "f" * 64}},
        plan_row(SHA_A, needs_review=True),
    ])

    assert invoke(inputs).exit_code == 0

    page = (inputs / "review.html").read_text(encoding="utf-8")
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_images_get_thumbnails_and_the_sources_stay_untouched(workspace, inputs):
    pillow = pytest.importorskip("PIL.Image")
    for sha, name, color in ((SHA_IMG_1, "skan1.png", (200, 30, 30)),
                             (SHA_IMG_2, "skan2.png", (200, 34, 30))):
        image = pillow.new("RGB", (64, 48), color)
        image.save(workspace.sources / "P" / "AKO" / name)
    write(inputs / "manifest_slice.jsonl", [
        {"sha256": SHA_IMG_1, "source_path": "P/AKO/skan1.png", "content_kind": "image",
         "size_bytes": 100},
        {"sha256": SHA_IMG_2, "source_path": "P/AKO/skan2.png", "content_kind": "image",
         "size_bytes": 100},
    ])
    write(inputs / "plan.jsonl", [
        {"_meta": {"subject_key": "AKO", "semester": 3, "plan_hash": "f" * 64}},
        plan_row(SHA_IMG_1), plan_row(SHA_IMG_2),
    ])
    write(inputs / "relations.jsonl", [{
        "source_sha256": SHA_IMG_1, "target_sha256": SHA_IMG_2,
        "relation_type": "near_duplicate", "confidence": 0.8,
    }])
    before = {p: p.read_bytes() for p in (workspace.sources / "P" / "AKO").iterdir()}

    assert invoke(inputs).exit_code == 0

    page = (inputs / "review.html").read_text(encoding="utf-8")
    assert page.count("data:image/jpeg;base64,") == 2
    assert sorted(p.name for p in workspace.work_thumbnails.iterdir()) == [
        f"{SHA_IMG_1}.jpg", f"{SHA_IMG_2}.jpg",
    ]
    assert {p: p.read_bytes() for p in (workspace.sources / "P" / "AKO").iterdir()} == before


def test_thumbnail_is_reused_on_the_second_run(workspace, inputs):
    """Miniatura liczy się RAZ NA TREŚĆ — ta sama zasada, co w etapie extract."""
    pytest.importorskip("PIL.Image")
    from PIL import Image

    for name, color in (("skan1.png", (10, 10, 10)), ("skan2.png", (12, 10, 10))):
        Image.new("RGB", (32, 32), color).save(workspace.sources / "P" / "AKO" / name)
    write(inputs / "manifest_slice.jsonl", [
        {"sha256": SHA_IMG_1, "source_path": "P/AKO/skan1.png", "content_kind": "image",
         "size_bytes": 100},
        {"sha256": SHA_IMG_2, "source_path": "P/AKO/skan2.png", "content_kind": "image",
         "size_bytes": 100},
    ])
    write(inputs / "plan.jsonl", [
        {"_meta": {"subject_key": "AKO", "semester": 3, "plan_hash": "f" * 64}},
        plan_row(SHA_IMG_1), plan_row(SHA_IMG_2),
    ])
    # Miniatury powstają tylko tam, gdzie są potrzebne: w klastrze do porównania.
    write(inputs / "relations.jsonl", [{
        "source_sha256": SHA_IMG_1, "target_sha256": SHA_IMG_2,
        "relation_type": "near_duplicate", "confidence": 0.8,
    }])
    assert invoke(inputs).exit_code == 0
    cache = workspace.work_thumbnails / f"{SHA_IMG_1}.jpg"
    stamp = cache.stat().st_mtime_ns

    assert invoke(inputs).exit_code == 0

    assert cache.stat().st_mtime_ns == stamp, "miniatura ma być liczona raz na treść"


def test_missing_text_says_what_to_run_instead_of_pretending(workspace, inputs):
    for sha in (SHA_A, SHA_B):
        (workspace.work_extracted_text / f"{sha}.txt").unlink()

    assert invoke(inputs).exit_code == 0

    page = (inputs / "review.html").read_text(encoding="utf-8")
    assert "just extract" in page


def test_validation_errors_are_shown_and_flagged_in_the_summary(workspace, inputs):
    write(inputs / "validation.jsonl", [
        {"level": "error", "code": "kolizja_celu", "message": "dwie treści w jedną ścieżkę",
         "target_rel": "paczka/SEM3/AKO_X/kolokwia/a.pdf", "source_sha256": SHA_A},
    ])

    result = invoke(inputs)

    assert result.exit_code == 0, result.output
    assert "PLAN NIE PRZECHODZI" in result.output
    page = (inputs / "review.html").read_text(encoding="utf-8")
    assert "plan odrzucony przez walidację" in page and "kolizja_celu" in page


def test_missing_plan_says_what_to_run(workspace, inputs):
    (inputs / "plan.jsonl").unlink()

    result = invoke(inputs)

    assert result.exit_code == 1
    assert "subject-plan" in result.output


@pytest.mark.parametrize("tree", ["sources", "target_repo", "media"])
def test_refuses_to_write_into_material_trees(workspace, inputs, tree):
    forbidden = getattr(workspace, tree) / "przeglad"

    result = invoke(inputs, "--out-dir", str(forbidden))

    assert result.exit_code == 1
    assert not forbidden.exists()
