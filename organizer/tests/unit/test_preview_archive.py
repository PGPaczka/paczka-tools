"""Spis zawartości archiwum jako podgląd. Czysta funkcja — bez bazy i bez API.

Powstało, bo 35% treści z decyzją (1441 z 4083) nie miało w grafie ŻADNEGO podglądu,
a wśród nich wszystkie 36 archiwów. Paczka z kodem laborki mówi, czym jest, dopiero
gdy widać, co ma w środku.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from orglib import preview


def make_zip(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    return path


def test_lists_what_is_inside(tmp_path) -> None:
    archive = make_zip(tmp_path / "lab.zip", ["main.c", "Makefile", "docs/opis.txt"])

    entries, total = preview.archive_head(archive, limit=10)

    assert entries == ["Makefile", "docs/opis.txt", "main.c"], "posortowane, żeby spis był stały"
    assert total == 3


def test_catalogues_are_not_entries(tmp_path) -> None:
    """Wpis katalogu niesie zero informacji o zawartości — liczy się to, co w nim leży."""
    archive = tmp_path / "z.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("src/", b"")
        handle.writestr("src/main.c", b"x")

    entries, total = preview.archive_head(archive, limit=10)

    assert entries == ["src/main.c"]
    assert total == 1


def test_long_archive_is_cut_but_counted(tmp_path) -> None:
    archive = make_zip(tmp_path / "duze.zip", [f"plik{i:03}.txt" for i in range(50)])

    entries, total = preview.archive_head(archive, limit=5)

    assert len(entries) == 5
    assert total == 50, "nagłówek ma mówić prawdę o rozmiarze, nawet gdy lista jest ucięta"


def test_a_file_that_is_not_a_zip_is_not_an_error(tmp_path) -> None:
    """RAR i 7z trafiają tu tak samo jak zip — mają dostać kafelkę, nie wyjątek."""
    fake = tmp_path / "paczka.rar"
    fake.write_bytes(b"Rar!\x1a\x07\x00 nie-zip")

    assert preview.archive_head(fake, limit=10) == ([], 0)


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    assert preview.archive_head(tmp_path / "nie-ma.zip", limit=10) == ([], 0)


def test_a_broken_archive_is_not_an_error(tmp_path) -> None:
    """Obcięty plik z nagłówkiem ZIP-a: `zipfile` rzuca, a podgląd ma milczeć."""
    broken = tmp_path / "obciete.zip"
    broken.write_bytes(b"PK\x03\x04" + b"\x00" * 20)

    assert preview.archive_head(broken, limit=10) == ([], 0)


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_of_nothing_still_counts(tmp_path, limit) -> None:
    archive = make_zip(tmp_path / "z.zip", ["a.txt", "b.txt"])

    entries, total = preview.archive_head(archive, limit=limit)

    assert entries == []
    assert total == 2
