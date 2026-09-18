"""Testy CLI etapu B2 na syntetycznej bazie i materiałach wyłącznie w tmp_path."""

from __future__ import annotations

import hashlib
import io
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from PIL import Image
from typer.testing import CliRunner

import extract_text
from orglib import config, db, textextract

runner = CliRunner()


@pytest.fixture(autouse=True)
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Paths:
    """Wczytuje realny config, przekierowując wszystkie korzenie do tmp_path."""
    data = config.load_yaml("paths")
    for key in ("sources", "work", "target_repo", "media"):
        root = tmp_path / key
        root.mkdir()
        data[key] = str(root)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "paths.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    loaded = config.load_paths(config_dir)
    monkeypatch.setattr(extract_text.config, "load_paths", lambda: loaded)
    return loaded


@pytest.fixture(autouse=True)
def fake_ocr(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Żaden przypadek nie może uruchomić zewnętrznego tesseractu."""
    real_module = textextract._module
    recognize = Mock(side_effect=lambda *a, **kw: pytest.fail("nieoczekiwane OCR"))

    def module(name: str):
        if name == "pytesseract":
            return SimpleNamespace(image_to_string=recognize)
        return real_module(name)

    monkeypatch.setattr(textextract, "_module", module)
    return recognize


@pytest.fixture()
def conn(paths: config.Paths):
    """Zakłada bazę przy użyciu schematu organizera i zamyka ją po teście."""
    connection = db.connect(paths.work_db)
    yield connection
    connection.close()


def _seed_file(
    conn: sqlite3.Connection,
    paths: config.Paths,
    *,
    package: str = "P1",
    relpath: str = "tekst.txt",
    payload: bytes = b"Tresc wykladu o algorytmach",
    kind: str = "text",
    write: bool = True,
    folder_path: str | None = None,
) -> int:
    """Dodaje zahashowany plik i treść; błędne ścieżki zasiewa tylko w bazie."""
    db.upsert(conn, "source_packages", {"package_name": package}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": package, "source_package": package})
    folder = folder_path or db.folder_path_for(package, relpath)
    db.upsert_folder(conn, {"folder_path": folder, "source_package": package})
    if write:
        target = paths.sources / package / relpath
        assert target.is_relative_to(paths.sources)
        assert ".." not in target.parts
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    db.upsert_content(conn, {"sha256": sha, "content_kind": kind})
    db.upsert_file(conn, {
        "source_package": package,
        "source_relative_path": relpath,
        "folder_path": folder,
        "filename": Path(relpath).name,
        "extension": Path(relpath).suffix.lstrip("."),
        "size_bytes": len(payload),
        "sha256": sha,
        "status": "hashed",
    })
    return int(conn.execute(
        "SELECT file_id FROM files WHERE source_package = ? AND source_relative_path = ?",
        (package, relpath),
    ).fetchone()["file_id"])


def _run(paths: config.Paths, *extra: str):
    """Zawsze przekazuje atrapę źródeł, bazy i wyjścia przez opcje CLI."""
    return runner.invoke(extract_text.app, [
        "--db", str(paths.work_db), "--sources", str(paths.sources),
        "--text-dir", str(paths.work_extracted_text), *extra,
    ])


def _file(conn: sqlite3.Connection, file_id: int) -> sqlite3.Row:
    """Odczytuje stan pliku po przebiegu CLI na osobnym połączeniu."""
    return conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()


def _content(conn: sqlite3.Connection, sha: str) -> sqlite3.Row:
    """Odczytuje wspólny wynik dla jednej treści."""
    return conn.execute("SELECT * FROM content WHERE sha256 = ?", (sha,)).fetchone()


def _png_bytes() -> bytes:
    """Tworzy mały, prawdziwy PNG w pamięci przed zasianiem źródeł."""
    buffer = io.BytesIO()
    with Image.new("RGB", (16, 16), "white") as image:
        image.paste("black", (0, 0, 8, 8))
        image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("outside_work", [False, True])
def test_extracts_text_and_stores_signatures(
    conn: sqlite3.Connection, paths: config.Paths, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, outside_work: bool,
) -> None:
    """Pełny przebieg zapisuje tekst atomowo, podpisy i przenośną ścieżkę."""
    text = "Zażółć gęślą jaźń\nNotatki z wykładu"
    file_id = _seed_file(conn, paths, payload=text.encode("utf-8"))
    with conn:
        conn.execute("UPDATE files SET error_message = 'dawny błąd' WHERE file_id = ?", (file_id,))
    destination = tmp_path / "inne-teksty" if outside_work else paths.work_extracted_text
    replace = Mock(wraps=extract_text.os.replace)
    monkeypatch.setattr(extract_text.os, "replace", replace)

    result = _run(paths, "--text-dir", str(destination))

    assert result.exit_code == 0, result.output
    row = _file(conn, file_id)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    output = destination / f"{sha}.txt"
    assert row["sha256"] == sha
    assert row["status"] == "extracted"
    assert row["error_message"] is None
    assert row["normalized_text_hash"] == textextract.normalized_text_hash(text)
    assert row["simhash"] == textextract.simhash(text)
    assert row["perceptual_hash"] is None
    content = _content(conn, sha)
    expected_path = str(output) if outside_work else output.relative_to(paths.work).as_posix()
    assert content["extracted_text_path"] == expected_path
    assert content["ocr_done"] == 0
    assert output.read_text(encoding="utf-8") == text
    assert list(destination.iterdir()) == [output]
    assert (paths.sources / "P1" / "tekst.txt").read_text(encoding="utf-8") == text
    replace.assert_called_once()
    temporary, target = map(Path, replace.call_args.args)
    assert temporary.parent == target.parent == destination
    assert temporary != target == output
    for line in ("wyekstrahowane pliki: 1", "przerobione treści: 1", "treści z tekstem: 1",
                 "treści bez tekstu: 0", "OCR: 0", "błędy: 0", "czas:"):
        assert line in result.stdout


@pytest.mark.parametrize("batch", [1, 50])
def test_duplicate_content_is_extracted_once(
    conn: sqlite3.Connection, paths: config.Paths, monkeypatch: pytest.MonkeyPatch, batch: int
) -> None:
    """Kopie współdzielą ekstrakcję także po przekroczeniu granicy partii."""
    first = _seed_file(conn, paths, relpath="a.txt")
    second = _seed_file(conn, paths, relpath="b.txt")
    extract = Mock(wraps=textextract.extract)
    monkeypatch.setattr(textextract, "extract", extract)

    result = _run(paths, "--batch", str(batch))

    assert result.exit_code == 0, result.output
    extract.assert_called_once()
    for file_id in (first, second):
        assert _file(conn, file_id)["status"] == "extracted"
        assert _file(conn, file_id)["normalized_text_hash"] is not None
    assert _file(conn, first)["simhash"] == _file(conn, second)["simhash"]
    assert len(list(paths.work_extracted_text.glob("*.txt"))) == 1
    assert "wyekstrahowane pliki: 2" in result.stdout
    assert "przerobione treści: 1" in result.stdout


@pytest.mark.parametrize("force", [False, True])
def test_rerun_uses_disk_unless_forced(
    conn: sqlite3.Connection, paths: config.Paths, monkeypatch: pytest.MonkeyPatch, force: bool
) -> None:
    """Ponownie zakolejkowany plik bierze cache z dysku, chyba że użyto force."""
    file_id = _seed_file(conn, paths)
    first = _run(paths)
    assert first.exit_code == 0, first.output
    sha = _file(conn, file_id)["sha256"]
    output = paths.work_extracted_text / f"{sha}.txt"
    original = output.read_text(encoding="utf-8")
    cached = "Osobna treść z cache na dysku"
    output.write_text(cached, encoding="utf-8")
    with conn:
        conn.execute("UPDATE files SET status = 'hashed' WHERE file_id = ?", (file_id,))
    extract = Mock(wraps=textextract.extract)
    monkeypatch.setattr(textextract, "extract", extract)

    result = _run(paths, *(["--force"] if force else []))

    assert result.exit_code == 0, result.output
    assert extract.call_count == int(force)
    assert f"gotowe z dysku: {int(not force)}" in result.stdout
    expected = original if force else cached
    assert _file(conn, file_id)["normalized_text_hash"] == textextract.normalized_text_hash(expected)
    assert output.read_text(encoding="utf-8") == expected
    assert _file(conn, file_id)["status"] == "extracted"


def test_rerun_without_pending_files_is_noop(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Zakończony plik nie wraca sam do kolejki ekstrakcji."""
    _seed_file(conn, paths)
    assert _run(paths).exit_code == 0
    result = _run(paths)
    assert result.exit_code == 0, result.output
    assert "wyekstrahowane pliki: 0" in result.stdout
    assert "przerobione treści: 0" in result.stdout


def test_limit_leaves_remaining_files_hashed(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Limit ogranicza liczbę plików, pozostawiając resztę w kolejce."""
    ids = [_seed_file(conn, paths, relpath=f"{i}.txt", payload=f"treść {i}".encode()) for i in range(3)]
    result = _run(paths, "--limit", "1")
    assert result.exit_code == 0, result.output
    assert [_file(conn, file_id)["status"] for file_id in ids] == ["extracted", "hashed", "hashed"]


def test_package_filters_queue(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Wybór paczki nie zmienia statusu pliku z innej paczki."""
    first = _seed_file(conn, paths, package="P1")
    second = _seed_file(conn, paths, package="P2")
    result = _run(paths, "--package", "P2")
    assert result.exit_code == 0, result.output
    assert _file(conn, first)["status"] == "hashed"
    assert _file(conn, second)["status"] == "extracted"


def test_batch_one_processes_every_content(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Partie po jednym pliku zapisują wszystkie unikalne treści."""
    ids = [_seed_file(conn, paths, relpath=f"{i}.txt", payload=f"treść {i}".encode()) for i in range(3)]
    result = _run(paths, "--batch", "1")
    assert result.exit_code == 0, result.output
    assert all(_file(conn, file_id)["status"] == "extracted" for file_id in ids)
    assert "przerobione treści: 3" in result.stdout
    assert result.stderr.count("extract:") == 3


def test_duplicate_folder_subtree_is_skipped(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Całe poddrzewo duplikatu jest pomijane, lecz sąsiedni prefiks pozostaje."""
    original = _seed_file(conn, paths, relpath="oryginal/a.txt", payload=b"oryginal")
    direct = _seed_file(conn, paths, relpath="kopia/a.txt", payload=b"duplikat")
    nested = _seed_file(conn, paths, relpath="kopia/podfolder/b.txt", payload=b"potomek")
    neighbour = _seed_file(conn, paths, relpath="kopia_inna/a.txt", payload=b"sasiad")
    with conn:
        conn.execute("UPDATE folders SET duplicate_of = 'P1/oryginal' WHERE folder_path = 'P1/kopia'")
    result = _run(paths)
    assert result.exit_code == 0, result.output
    for file_id in (original, neighbour):
        assert _file(conn, file_id)["status"] == "extracted"
    for file_id in (direct, nested):
        row = _file(conn, file_id)
        assert row["status"] == "hashed"
        assert _content(conn, row["sha256"])["extracted_text_path"] is None
    assert "wyekstrahowane pliki: 2" in result.stdout


@pytest.mark.parametrize(("suffix", "kind"), [(".zip", "archive"), (".doc", "docx"), (".png", "image")])
def test_no_text_is_success(conn: sqlite3.Connection, paths: config.Paths, suffix: str, kind: str) -> None:
    """Archiwum, stary Word i obraz bez OCR kończą etap bez pliku tekstu."""
    payload = _png_bytes() if kind == "image" else b"brak obslugi tekstu"
    file_id = _seed_file(conn, paths, relpath=f"plik{suffix}", payload=payload, kind=kind)
    result = _run(paths)
    assert result.exit_code == 0, result.output
    row = _file(conn, file_id)
    assert row["status"] == "extracted"
    assert row["error_message"] is None
    assert row["normalized_text_hash"] is None
    assert row["simhash"] is None
    if kind == "image":
        assert row["perceptual_hash"] == textextract.perceptual_hash(paths.sources / "P1" / f"plik{suffix}")
        assert row["perceptual_hash"] is not None
    else:
        assert row["perceptual_hash"] is None
    content = _content(conn, row["sha256"])
    assert content["extracted_text_path"] is None
    assert content["ocr_done"] == 0
    assert not list(paths.work_extracted_text.glob("*"))
    assert "treści bez tekstu: 1" in result.stdout
    assert "błędy: 0" in result.stdout


def test_image_ocr_updates_content_and_signatures(
    conn: sqlite3.Connection, paths: config.Paths, fake_ocr: Mock
) -> None:
    """Jawny OCR obrazu zapisuje tekst, phash oraz znacznik w content."""
    file_id = _seed_file(conn, paths, relpath="obraz.png", payload=_png_bytes(), kind="image")
    fake_ocr.side_effect = None
    fake_ocr.return_value = "Rozpoznany wykład"
    result = _run(paths, "--ocr-images", "--ocr-lang", "pol")
    assert result.exit_code == 0, result.output
    row = _file(conn, file_id)
    assert row["status"] == "extracted"
    assert row["normalized_text_hash"] == textextract.normalized_text_hash("Rozpoznany wykład")
    assert row["perceptual_hash"] is not None
    content = _content(conn, row["sha256"])
    assert content["ocr_done"] == 1
    assert (paths.work / content["extracted_text_path"]).read_text(encoding="utf-8") == "Rozpoznany wykład"
    fake_ocr.assert_called_once()
    assert fake_ocr.call_args.kwargs == {"lang": "pol"}
    assert "OCR: 1" in result.stdout


def test_missing_file_is_error_and_does_not_block_queue(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Brak pliku nie uniemożliwia przetworzenia kolejnej treści."""
    missing = _seed_file(conn, paths, write=False)
    good = _seed_file(conn, paths, relpath="dobry.txt", payload=b"inna tresc")
    result = _run(paths)
    assert result.exit_code == 0, result.output
    row = _file(conn, missing)
    assert row["status"] == "error"
    assert "ExtractionError" in row["error_message"]
    assert "FileNotFoundError" in row["error_message"]
    assert _file(conn, good)["status"] == "extracted"
    assert "błędy: 1" in result.stdout


@pytest.mark.parametrize("error", [OSError("awaria odczytu"), textextract.ExtractionError("uszkodzony dokument")])
def test_read_errors_are_saved(
    conn: sqlite3.Connection, paths: config.Paths, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """CLI utrwala oba rodzaje awarii pojedynczego pliku."""
    file_id = _seed_file(conn, paths)
    monkeypatch.setattr(textextract, "extract", Mock(side_effect=error))
    result = _run(paths)
    assert result.exit_code == 0, result.output
    row = _file(conn, file_id)
    assert row["status"] == "error"
    assert row["error_message"] == f"{type(error).__name__}: {error}"


def test_missing_sha_is_error(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Plik bez sha256 nie może wejść do ekstrakcji ani cache."""
    file_id = _seed_file(conn, paths)
    with conn:
        conn.execute("UPDATE files SET sha256 = NULL WHERE file_id = ?", (file_id,))
    result = _run(paths)
    assert result.exit_code == 0, result.output
    assert _file(conn, file_id)["status"] == "error"
    assert "brak sha256" in _file(conn, file_id)["error_message"]


def test_path_escaping_sources_is_rejected_before_reading(
    conn: sqlite3.Connection, paths: config.Paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Segmenty .. wychodzące poza atrapę źródeł nie powodują odczytu pliku."""
    outside = tmp_path / "poza.txt"
    outside.write_text("Nie czytaj", encoding="utf-8")
    relpath = Path("..", "..", outside.name).as_posix()
    file_id = _seed_file(conn, paths, relpath=relpath, write=False, folder_path="P1")
    extract = Mock(side_effect=AssertionError("nie wolno czytać poza źródłami"))
    monkeypatch.setattr(textextract, "extract", extract)
    result = _run(paths)
    assert result.exit_code == 0, result.output
    assert _file(conn, file_id)["status"] == "error"
    assert _file(conn, file_id)["error_message"] == "ścieżka poza katalogiem źródeł"
    extract.assert_not_called()


def test_retry_errors_is_explicit_and_respects_package(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Ponowienie błędów czyści komunikat wyłącznie w wybranej paczce."""
    first = _seed_file(conn, paths, package="P1")
    second = _seed_file(conn, paths, package="P2")
    with conn:
        conn.execute("UPDATE files SET status = 'error', error_message = 'stary błąd'")
    initial = _run(paths)
    assert initial.exit_code == 0, initial.output
    assert all(_file(conn, file_id)["status"] == "error" for file_id in (first, second))
    assert "wcześniejsze błędy: 2" in initial.stdout
    result = _run(paths, "--retry-errors", "--package", "P2")
    assert result.exit_code == 0, result.output
    assert _file(conn, first)["status"] == "error"
    assert _file(conn, second)["status"] == "extracted"
    assert _file(conn, second)["error_message"] is None


@pytest.mark.parametrize("option", ["--batch", "--max-chars", "--max-pages", "--ocr-pages"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_invalid_positive_options_exit_two(paths: config.Paths, option: str, value: str) -> None:
    """Niepoprawne limity są odrzucane jeszcze przed otwarciem bazy."""
    result = _run(paths, option, value)
    assert result.exit_code == 2, result.output
    assert option in result.output


@pytest.mark.parametrize("protected", ["sources", "target_repo", "media"])
def test_output_in_protected_tree_is_rejected(
    conn: sqlite3.Connection, paths: config.Paths, protected: str
) -> None:
    """Ochrona działa na syntetycznych korzeniach załadowanych z paths.yaml."""
    file_id = _seed_file(conn, paths)
    destination = getattr(paths, protected) / "teksty"
    result = _run(paths, "--text-dir", str(destination))
    assert result.exit_code == 2, result.output
    assert "chronionym drzewie" in result.output
    assert not destination.exists()
    assert _file(conn, file_id)["status"] == "hashed"


def test_missing_database_exits_one(paths: config.Paths) -> None:
    """Nieistniejąca baza kończy się kodem 1 i nie jest automatycznie tworzona."""
    result = _run(paths)
    assert result.exit_code == 1, result.output
    assert "brak bazy" in result.output
    assert not paths.work_db.exists()


def test_cli_passes_extraction_options_and_limits_text(
    conn: sqlite3.Connection, paths: config.Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opcje CLI trafiają do ekstraktora, a podpisy opisują zapisaną głowę."""
    file_id = _seed_file(conn, paths, payload=b"abcdefghijk")
    extract = Mock(wraps=textextract.extract)
    monkeypatch.setattr(textextract, "extract", extract)
    result = _run(paths, "--max-chars", "5", "--max-pages", "1", "--no-ocr",
                  "--ocr-images", "--ocr-lang", "eng", "--ocr-pages", "1")
    assert result.exit_code == 0, result.output
    extract.assert_called_once_with(
        paths.sources / "P1" / "tekst.txt", "text", max_chars=5, max_pages=1,
        ocr=False, ocr_images=True, ocr_lang="eng", ocr_max_pages=1,
    )
    row = _file(conn, file_id)
    output = paths.work_extracted_text / f"{row['sha256']}.txt"
    assert output.read_text(encoding="utf-8") == "abcde"
    assert row["normalized_text_hash"] == textextract.normalized_text_hash("abcde")


def test_summary_lists_extraction_methods(conn: sqlite3.Connection, paths: config.Paths) -> None:
    """Podsumowanie pokazuje, czym faktycznie czytano treści (diagnostyka przebiegu)."""
    _seed_file(conn, paths, relpath="a.txt", payload=b"tresc wykladu")
    _seed_file(conn, paths, relpath="b.zip", payload=b"archiwum", kind="archive")
    result = _run(paths)
    assert result.exit_code == 0, result.output
    assert "metody: text=1, unsupported=1" in result.stdout
