"""Nazwy plików i katalogów, jakie realnie są w źródłach — przez cały potok.

Zestaw nie jest wymyślony: pochodzi z pomiaru 48 049 plików w indeksie i 59 936
wpisów na dysku (2026-09-18). Rozkład, który wymusił te przypadki:

* spacja w nazwie — 47 289 plików (98%!),
* nawiasy — 18 176, polskie znaki — 30 073, wiele kropek — 5 887,
* przecinek — 405, `#`/`!` — 386, `&`/`$`/`%` — 191,
* ścieżka > 200 znaków — 27, segment > 100 znaków — 5,
* nazwa zaczynająca się od `-` — 2, apostrof — 2,
* forma NFD zamiast NFC — 0 (zmierzone, nie założone: nie ma potrzeby testować),
* nazwa spoza UTF-8 — 0 na dysku, ale kod skanu ma gałąź na ten przypadek
  i do tej pory nikt jej nie sprawdzał.

Dotąd pokryty był wyłącznie wariant, który raz ugryzł projekt (`AKO2020 (1)` —
spacja plus nawias w sortowaniu ścieżek). Ten plik domyka resztę: nazwa ma
przejść przez skan, hash, ekstrakcję i manifest bez zgubienia, obcięcia ani
potraktowania jako flagi wiersza poleceń.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from typer.testing import CliRunner

import extract_text
import hash_files
import prepare_subject
import scan
from orglib import config, textextract

runner = CliRunner()

#: Nazwy plików, które MUSZĄ przejść przez potok bez zmian.
TRUDNE_NAZWY = [
    pytest.param("sprawozdanie, wersja 2.txt", id="przecinek"),
    pytest.param("wyklad #3.txt", id="hash"),
    pytest.param("uwaga! ważne.txt", id="wykrzyknik"),
    pytest.param("R&D oraz 100% wyników.txt", id="ampersand-procent"),
    pytest.param("zadania 'domowe'.txt", id="apostrof"),
    pytest.param("-notatki.txt", id="wiodacy-myslnik"),
    pytest.param("w1.final.v2.txt", id="wiele-kropek"),
    pytest.param("Zażółć gęślą jaźń — wykład.txt", id="polskie-znaki-i-myslnik"),
    pytest.param("AKO2020 (1).txt", id="spacja-i-nawias"),
    pytest.param("a" * 120 + ".txt", id="bardzo-dlugi-segment"),
    pytest.param("sprawozdanie $ 2021 (poprawione).txt", id="dolar-i-nawias"),
]

#: Nazwy KATALOGÓW z tymi samymi pułapkami.
TRUDNE_KATALOGI = [
    pytest.param("AKO 2020 (kopia)", id="spacja-nawias"),
    pytest.param("Ćwiczenia & laboratoria", id="polskie-i-ampersand"),
    pytest.param("materiały, różne", id="przecinek"),
    pytest.param("-tymczasowe", id="wiodacy-myslnik"),
    pytest.param("wykłady 100%", id="procent"),
]


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Paths:
    """Syntetyczny workspace z realnym loaderem configu; nic prawdziwego nie jest czytane."""
    data = config.load_yaml("paths")
    for key in ("sources", "work", "media", "target_repo"):
        (tmp_path / key).mkdir()
        data[key] = str(tmp_path / key)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "paths.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    paths = config.load_paths(config_dir)
    monkeypatch.setattr(config, "load_paths", lambda config_dir=None: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    return paths


def _run(app: Any, *args: str) -> None:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"{args}\n{result.output}\n{result.exception}"


def _index(paths: config.Paths) -> None:
    """Skan + hash + ekstrakcja na syntetycznych źródłach."""
    db_path = str(paths.work_db)
    _run(scan.app, "--db", db_path, "--sources", str(paths.sources))
    _run(hash_files.app, "--db", db_path, "--sources", str(paths.sources))
    _run(
        extract_text.app, "--db", db_path, "--sources", str(paths.sources),
        "--text-dir", str(paths.work_extracted_text), "--no-ocr",
    )


def _rows(paths: config.Paths, sql: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(paths.work_db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("nazwa", TRUDNE_NAZWY)
def test_file_name_survives_scan_hash_and_extract(workspace: config.Paths, nazwa: str) -> None:
    """Nazwa przechodzi przez trzy etapy bez zgubienia, obcięcia i bez roli flagi.

    Wiodący myślnik jest tu najważniejszy: taka nazwa trafia dalej jako argument
    zewnętrznych narzędzi, a `-notatki.txt` potrafi zostać uznane za flagę.
    """
    package = workspace.sources / "P1"
    package.mkdir()
    (package / nazwa).write_text("treść materiału o architekturze komputerów", encoding="utf-8")

    _index(workspace)

    rows = _rows(workspace, "SELECT filename, extension, sha256, status FROM files")
    assert len(rows) == 1, f"plik zniknął albo rozmnożył się: {[dict(r) for r in rows]}"
    row = rows[0]
    assert row["filename"] == nazwa
    assert row["extension"] == "txt"
    assert row["sha256"] and row["status"] == "extracted"
    tekst = _rows(workspace, "SELECT extracted_text_path FROM content")[0]["extracted_text_path"]
    assert tekst, "nie powstała głowa tekstu"
    assert "architekturze" in (workspace.work / tekst).read_text(encoding="utf-8")


@pytest.mark.parametrize("katalog", TRUDNE_KATALOGI)
def test_directory_name_survives_scan(workspace: config.Paths, katalog: str) -> None:
    """Katalog o trudnej nazwie ma poprawny `folder_path` i wiąże się z plikiem."""
    target = workspace.sources / "P1" / katalog
    target.mkdir(parents=True)
    (target / "plik.txt").write_text("treść", encoding="utf-8")

    _index(workspace)

    row = _rows(workspace, "SELECT folder_path, source_relative_path FROM files")[0]
    assert row["folder_path"] == f"P1/{katalog}"
    assert row["source_relative_path"] == f"{katalog}/plik.txt"
    folders = {r["folder_path"] for r in _rows(workspace, "SELECT folder_path FROM folders")}
    assert f"P1/{katalog}" in folders


def test_deeply_nested_long_path_is_indexed(workspace: config.Paths) -> None:
    """Ścieżka > 200 znaków (w źródłach jest ich 27) nie może wypaść ze skanu."""
    segments = ["katalog " + "x" * 40 for _ in range(4)]
    target = workspace.sources.joinpath("P1", *segments)
    target.mkdir(parents=True)
    (target / "materiał końcowy.txt").write_text("treść", encoding="utf-8")

    _index(workspace)

    row = _rows(workspace, "SELECT source_relative_path, status FROM files")[0]
    assert len(row["source_relative_path"]) > 200
    assert row["status"] == "extracted"


def test_leading_dash_reaches_converter_as_absolute_path(
    workspace: config.Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plik `-stary.doc` nie może trafić do konwertera jako flaga.

    Ochroną jest przekazywanie ścieżki ABSOLUTNEJ (zaczyna się od `/`, więc nie
    wygląda jak opcja). Dotąd wynikało to z implementacji, a nie z testu.
    """
    package = workspace.sources / "P1"
    package.mkdir()
    (package / "-stary.doc").write_bytes(b"\xd0\xcf\x11\xe0 udawany binarny doc")

    monkeypatch.setattr(textextract.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="Wykład".encode("utf-8"), stderr=b""))
    monkeypatch.setattr(textextract.subprocess, "run", run)

    _index(workspace)

    argv = run.call_args.args[0]
    sciezka = argv[-1]
    assert Path(sciezka).is_absolute(), f"konwerter dostał ścieżkę względną: {sciezka!r}"
    assert not sciezka.startswith("-"), "nazwa pliku może zostać odczytana jako flaga"
    assert sciezka.endswith("-stary.doc")


def test_name_that_cannot_be_encoded_is_skipped_and_reported(workspace: config.Paths) -> None:
    """Nazwa spoza UTF-8: plik pomijany, skan częściowy (exit 3), reszta indeksowana.

    W dzisiejszych źródłach takich nazw NIE MA (zmierzone), ale gałąź istnieje
    w `scan.py` od początku i do teraz nie miała żadnego testu. Paczka
    wyeksportowana z Windows w cp1250 może ją uruchomić w każdej chwili.
    """
    package = workspace.sources / "P1"
    package.mkdir()
    (package / "poprawny.txt").write_text("treść", encoding="utf-8")
    zla_nazwa = os.fsdecode(b"zle\xff.txt")
    try:
        (package / zla_nazwa).write_text("treść", encoding="utf-8")
    except (OSError, UnicodeEncodeError):  # pragma: no cover - zależy od systemu plików
        pytest.skip("system plików nie przyjmuje nazw spoza UTF-8")

    result = runner.invoke(
        scan.app, ["--db", str(workspace.work_db), "--sources", str(workspace.sources)]
    )

    assert result.exit_code == 3, f"skan częściowy powinien dać kod 3: {result.output}"
    nazwy = {r["filename"] for r in _rows(workspace, "SELECT filename FROM files")}
    assert nazwy == {"poprawny.txt"}, "plik o nazwie spoza UTF-8 nie powinien wejść do indeksu"


def test_special_names_reach_the_subject_manifest(workspace: config.Paths) -> None:
    """Pełna droga do manifestu: nazwa z przecinkiem, myślnikiem i polskimi znakami.

    Manifest jest kontraktem wejściowym klasyfikatora AI — nazwa uszkodzona po
    drodze zmienia decyzję modelu, a `source_path` musi dać się otworzyć.
    """
    subject_dir = workspace.sources / "PaczkaA" / "SEM3" / "AKO"
    subject_dir.mkdir(parents=True)
    nazwy = ["sprawozdanie, wersja 2.txt", "-notatki z ćwiczeń.txt", "w1.final.v2.txt"]
    for index, nazwa in enumerate(nazwy):
        (subject_dir / nazwa).write_text(f"materiał numer {index}", encoding="utf-8")

    _index(workspace)
    out_dir = workspace.work / "manifest"
    _run(
        prepare_subject.app, "--semester", "3", "--skrot", "AKO",
        "--db", str(workspace.work_db), "--out-dir", str(out_dir),
    )

    rows = [
        json.loads(line)
        for line in (out_dir / "manifest_slice.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == len(nazwy)
    w_manifescie = {Path(row["source_path"]).name for row in rows}
    assert w_manifescie == set(nazwy)
    for row in rows:
        assert (workspace.sources / row["source_path"]).is_file(), (
            "ścieżka z manifestu nie prowadzi do istniejącego pliku"
        )
        assert row["text_head"], "nazwa specjalna nie może gubić głowy tekstu"


def test_converter_gets_absolute_path_even_for_relative_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """To `abspath` chroni przed nazwą-flagą, więc test musi podać ścieżkę WZGLĘDNĄ.

    Test wyżej (przez cały potok) tego nie pilnuje: etapy dostają ścieżkę już
    absolutną z `resolve_within_sources`, więc usunięcie `abspath` z konwertera
    nie zmieniało tam wyniku. Sprawdzone mutacyjnie — dlatego ten test istnieje.
    """
    (tmp_path / "-stary.doc").write_bytes(b"\xd0\xcf\x11\xe0 udawany binarny doc")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(textextract.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=b"Wyklad", stderr=b""))
    monkeypatch.setattr(textextract.subprocess, "run", run)

    textextract.extract(Path("-stary.doc"), "docx")

    sciezka = run.call_args.args[0][-1]
    assert Path(sciezka).is_absolute(), f"konwerter dostał ścieżkę względną: {sciezka!r}"
    assert not sciezka.startswith("-")
