"""Wspólny kontrakt JSONL: co jest linią, a co nie.

Warstwa powstała po awarii z 2026-09-19 (patrz docstring `orglib/jsonl.py`), więc
testy pilnują dokładnie tego, co wtedy zawiodło: znaków, które Python uznaje za
koniec linii, a JSON — za zwykłą treść stringa.
"""

from __future__ import annotations

import json

import pytest

from orglib.jsonl import read_jsonl, write_atomic

#: Znaki, które `str.splitlines()` traktuje jak koniec linii, a które
#: `json.dumps(..., ensure_ascii=False)` zapisuje SUROWO — czyli dokładnie te, które
#: potrafią rozerwać linię JSONL. Wypisane wprost, nie wyliczone z implementacji.
RAW_LINE_LIKE = [" ", " ", "\x85"]

#: Znaki sterujące poniżej 0x20: dla `splitlines()` też są końcem linii, ale JSON
#: je escapuje, więc do pliku trafiają jako `\uXXXX`. Mają przejść zapis i odczyt
#: bez zmiany treści.
ESCAPED_LINE_LIKE = ["\v", "\f", "\x1c", "\x1d", "\x1e"]


@pytest.mark.parametrize("character", RAW_LINE_LIKE)
def test_only_a_newline_separates_records(tmp_path, character) -> None:
    path = tmp_path / "dane.jsonl"
    path.write_text(
        json.dumps({"tekst": f"przed{character}po"}, ensure_ascii=False) + "\n"
        + json.dumps({"tekst": "druga"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = read_jsonl(path)

    assert [row["tekst"] for row in rows] == [f"przed{character}po", "druga"]
    # Dowód, że test nie jest pusty: naiwne dzielenie naprawdę psuje ten plik.
    assert len(path.read_text(encoding="utf-8").splitlines()) > 2


@pytest.mark.parametrize("character", ESCAPED_LINE_LIKE)
def test_escaped_control_characters_survive_a_round_trip(tmp_path, character) -> None:
    path = tmp_path / "dane.jsonl"

    write_atomic([{"tekst": f"przed{character}po"}], path)

    assert read_jsonl(path) == [{"tekst": f"przed{character}po"}]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_blank_lines_are_skipped_and_the_rest_survives(tmp_path) -> None:
    path = tmp_path / "dane.jsonl"
    path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")

    assert read_jsonl(path) == [{"a": 1}, {"a": 2}]


def test_broken_line_names_the_file_and_the_line(tmp_path) -> None:
    path = tmp_path / "dane.jsonl"
    path.write_text('{"a": 1}\nto nie jest json\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"dane\.jsonl:2: niepoprawny JSON"):
        read_jsonl(path)


def test_a_line_that_is_not_an_object_is_rejected(tmp_path) -> None:
    path = tmp_path / "dane.jsonl"
    path.write_text("[1, 2]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="nie jest obiektem"):
        read_jsonl(path)


def test_write_atomic_round_trips_and_sorts_keys(tmp_path) -> None:
    path = tmp_path / "out" / "dane.jsonl"

    write_atomic([{"b": 2, "a": "ą ę"}], path)

    assert path.read_text(encoding="utf-8").startswith('{"a": "ą')
    assert read_jsonl(path) == [{"a": "ą ę", "b": 2}]


def test_failed_write_leaves_the_previous_file_intact(tmp_path) -> None:
    """Przerwany zapis nie może zostawić obciętego artefaktu ani śmiecia .tmp."""
    path = tmp_path / "dane.jsonl"
    write_atomic([{"a": 1}], path)

    # Druga linia wywala serializację dopiero W TRAKCIE zapisu — plik tymczasowy
    # jest już wtedy otwarty i częściowo zapisany.
    with pytest.raises(TypeError):
        write_atomic([{"a": 2}, {"b": object()}], path)

    assert read_jsonl(path) == [{"a": 1}]
    assert list(path.parent.glob("*.tmp")) == []
