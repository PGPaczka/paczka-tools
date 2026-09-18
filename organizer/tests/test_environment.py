"""Kontrola ŚRODOWISKA: czy zainstalowane zależności naprawdę działają.

Reszta testów używa atrap i sprawdza *kontrakt kodu* — dzięki temu jest
deterministyczna i niezależna od tego, co ktoś ma zainstalowane. Ten plik robi
dokładnie odwrotnie: **nie ma tu ani jednej atrapy**. Każdy test wykonuje realną
pracę realną biblioteką albo realną binarką i porównuje wynik.

Zasada: brakująca albo zepsuta zależność ma być **czerwona**, nie pominięta.
Odinstalowanie `catdoc` czy `tesseract-ocr-pol` musi wywalić ten plik — inaczej
potok po cichu przestaje czytać setki materiałów, a testy dalej świecą na zielono.

Dlatego testy są oznaczone markerem ``environment`` (patrz ``pytest.ini``):
wchodzą do zwykłego ``just test``, a ``just env-check`` uruchamia same te
kontrole. Świadoma praca na maszynie bez pełnego środowiska to
``pytest -m "not environment"`` — wybór jawny, nie domyślny.

Skąd wzięły się te testy: ekstrakcja `.doc` przez `catdoc` wracała z krzakami
(cp1252 zamiast cp1250), a testy z atrapą nie miały prawa tego pokazać.
Zob. TODO B2b.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

from orglib import textextract

pytestmark = pytest.mark.environment

#: Nazwa pakietu z requirements.txt -> nazwa modułu do zaimportowania.
PACKAGE_TO_MODULE: dict[str, str] = {
    "PyMuPDF": "pymupdf",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "Pillow": "PIL",
    "PyYAML": "yaml",
    "sqlite-utils": "sqlite_utils",
    "odfpy": "odf",
}

#: Minimalne wersje, których wymaga KOD (nie „najnowsza, bo tak”).
MINIMUM_VERSIONS: dict[str, tuple[int, ...]] = {
    # Nazwa modułu `pymupdf` (zamiast dawnego `fitz`) istnieje od 1.24;
    # orglib.textextract importuje właśnie ją.
    "pymupdf": (1, 24),
    # xlrd 2.x czyta WYŁĄCZNIE .xls — na tym opiera się dyspozytor formatów.
    # W 1.x ten sam import obsługiwał też .xlsx, co zmieniałoby zachowanie.
    "xlrd": (2, 0),
}

#: Binarki systemowe, bez których potok przestaje czytać część materiałów.
REQUIRED_BINARIES: tuple[str, ...] = ("catdoc", "catppt", "tesseract")

POLISH = "Zażółć gęślą jaźń"

#: Tekst dla PDF-ów budowanych w teście. Świadomie bez polskich znaków: wbudowana
#: czcionka PyMuPDF (Helvetica) nie ma ich w ogóle, więc wpisane tu „ż” wróciłoby
#: jako kropka — to ograniczenie GENEROWANIA testowego PDF-u, nie odczytu.
#: Realne PDF-y ze źródeł mają własne czcionki i czytają się z polskimi znakami
#: (sprawdzone na materiałach). Nie zamieniaj tego na POLISH.
PDF_TEXT = "Sprawozdanie z laboratorium 3"


def _requirements() -> list[str]:
    """Nazwy pakietów z setup/requirements.txt (bez komentarzy i wersji)."""
    path = Path(__file__).resolve().parents[1] / "setup" / "requirements.txt"
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.append(line.split(">=")[0].split("==")[0].strip())
    return names


def _version(module_name: str) -> tuple[int, ...]:
    """Wersja zainstalowanego modułu jako krotka liczb."""
    module = importlib.import_module(module_name)
    raw = getattr(module, "__version__", None) or getattr(module, "VERSION", "")
    if isinstance(raw, tuple):
        return tuple(int(part) for part in raw if str(part).isdigit())
    parts = []
    for chunk in str(raw).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


# --------------------------------------------------------------------------- #
# Zależności Pythona: zainstalowane i w wersji, na której opiera się kod
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("package", _requirements())
def test_declared_dependency_is_installed(package: str) -> None:
    """Każdy pakiet z requirements.txt da się zaimportować w tym środowisku."""
    module_name = PACKAGE_TO_MODULE.get(package, package.replace("-", "_").lower())
    assert importlib.import_module(module_name) is not None


@pytest.mark.parametrize(("module_name", "minimum"), sorted(MINIMUM_VERSIONS.items()))
def test_minimum_version(module_name: str, minimum: tuple[int, ...]) -> None:
    """Wersja biblioteki nie jest starsza niż ta, na której opiera się zachowanie kodu."""
    installed = _version(module_name)
    assert installed >= minimum, f"{module_name} {installed} < wymagane {minimum}"


# --------------------------------------------------------------------------- #
# Biblioteki dokumentów: realny zapis i odczyt, bez atrap
# --------------------------------------------------------------------------- #


def test_pymupdf_reads_text_it_wrote(tmp_path: Path) -> None:
    """PyMuPDF zapisuje i odczytuje warstwę tekstową — podstawa etapu extract."""
    import pymupdf

    path = tmp_path / "srodowisko.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 60), PDF_TEXT, fontsize=14)
        document.save(path)
    result = textextract.extract(path, "pdf", ocr=False)
    assert result.method == "pdf_text"
    assert PDF_TEXT in result.text


def test_pdfplumber_reads_pdf(tmp_path: Path) -> None:
    """Awaryjny parser PDF też działa — to on ratuje pliki o dziwnym układzie."""
    import pdfplumber
    import pymupdf

    path = tmp_path / "plumber.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 60), PDF_TEXT, fontsize=14)
        document.save(path)
    with pdfplumber.open(path) as document:
        assert PDF_TEXT in (document.pages[0].extract_text() or "")


def test_python_docx_round_trip(tmp_path: Path) -> None:
    """python-docx czyta dokument, który sam zapisał."""
    import docx

    path = tmp_path / "srodowisko.docx"
    document = docx.Document()
    document.add_paragraph(POLISH)
    document.save(path)
    assert POLISH in textextract.extract(path, "docx").text


def test_python_pptx_round_trip(tmp_path: Path) -> None:
    """python-pptx czyta prezentację, którą sam zapisał."""
    from pptx import Presentation
    from pptx.util import Inches

    path = tmp_path / "srodowisko.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = POLISH
    presentation.save(path)
    assert POLISH in textextract.extract(path, "pptx").text


def test_openpyxl_round_trip(tmp_path: Path) -> None:
    """openpyxl czyta arkusz, który sam zapisał (odblokowuje .xlsx w potoku)."""
    import openpyxl

    path = tmp_path / "srodowisko.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "Wyniki"
    workbook.active.append([POLISH, 42])
    workbook.save(path)
    text = textextract.extract(path, "xlsx").text
    assert "Wyniki" in text
    assert POLISH in text


def test_odfpy_round_trip(tmp_path: Path) -> None:
    """odfpy czyta OpenDocument, który sam zapisał (.odt/.ods/.odp)."""
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    path = tmp_path / "srodowisko.odt"
    document = OpenDocumentText()
    document.text.addElement(P(text=POLISH))
    document.save(str(path))
    assert POLISH in textextract.extract(path, "docx").text


def test_pillow_and_imagehash_produce_signature(tmp_path: Path) -> None:
    """Pillow + imagehash dają phash — jedyna warstwa porównania dla obrazów."""
    from PIL import Image

    path = tmp_path / "srodowisko.png"
    with Image.new("RGB", (32, 32), "white") as image:
        image.paste("black", (0, 0, 16, 16))
        image.save(path)
    signature = textextract.perceptual_hash(path)
    assert signature is not None and len(signature) == 16


# --------------------------------------------------------------------------- #
# Binarki systemowe: obecne I dające poprawny wynik
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("binary", REQUIRED_BINARIES)
def test_required_binary_is_installed(binary: str) -> None:
    """Brak binarki to awaria środowiska, nie powód do pominięcia testu.

    `catdoc`/`catppt` czytają stare .doc/.ppt/.pps, `tesseract` robi OCR skanów.
    Instaluje je `bash setup/install.sh --with-apt` (pakiety catdoc, tesseract-ocr).
    """
    assert shutil.which(binary) is not None, f"brak {binary} — uruchom setup/install.sh --with-apt"


def test_tesseract_has_polish_language() -> None:
    """Sam tesseract nie wystarczy: bez `pol` skany wracają w kalekiej angielszczyźnie."""
    import pytesseract

    assert "pol" in pytesseract.get_languages(), "brak pakietu tesseract-ocr-pol"


def test_ocr_reads_rendered_page(tmp_path: Path) -> None:
    """Pełna ścieżka OCR (rasteryzacja + tesseract) odczytuje wyrenderowany tekst."""
    import pymupdf

    path = tmp_path / "skan.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 80), "EGZAMIN POPRAWKOWY", fontsize=28)
        pixmap = page.get_pixmap(dpi=200)
        scan = pymupdf.open()
        target = scan.new_page(width=pixmap.width, height=pixmap.height)
        target.insert_image(pymupdf.Rect(0, 0, pixmap.width, pixmap.height), stream=pixmap.tobytes("png"))
        scan.save(path)
        scan.close()
    result = textextract.extract(path, "pdf")
    assert result.method == "pdf_ocr"
    assert result.ocr_done
    assert "EGZAMIN" in result.text.upper()


def test_catdoc_decodes_polish_source_charset(tmp_path: Path) -> None:
    """catdoc zwraca POPRAWNE polskie znaki, a nie krzaki — realny błąd z B2b.

    Stary Word trzyma tekst w 8-bitowym cp1250. Bez jawnego ``-s`` catdoc zakłada
    cp1252 i „Zminimalizować” wraca jako „Zminimalizowaæ”. Test karmi konwerter
    bajtami cp1250 i wymaga, żeby po drugiej stronie wyszedł ten sam polski tekst.
    """
    path = tmp_path / "stary.doc"
    path.write_bytes(POLISH.encode("cp1250"))
    result = textextract.extract(path, "docx")
    assert result.method == "converter"
    assert result.text.strip() == POLISH


def test_catppt_runs_and_reports_version() -> None:
    """catppt (stare .ppt/.pps) jest wykonywalny w tym środowisku."""
    completed = subprocess.run(["catppt", "-V"], capture_output=True, timeout=30)
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    assert "atppt" in output or completed.returncode == 0


def test_extraction_stack_covers_every_declared_format() -> None:
    """Każdy format z mapy rodzajów ma w tym środowisku czym zostać przeczytany.

    Lista jest jawna: dopisanie rozszerzenia do ``orglib.kinds`` bez czytnika ma
    ten test wywalić, a nie po cichu produkować treści bez tekstu.
    """
    readers = {
        ".pdf": lambda: importlib.import_module("pymupdf"),
        ".docx": lambda: importlib.import_module("docx"),
        ".pptx": lambda: importlib.import_module("pptx"),
        ".xlsx": lambda: importlib.import_module("openpyxl"),
        ".xls": lambda: importlib.import_module("xlrd"),
        ".odt": lambda: importlib.import_module("odf.opendocument"),
        ".doc": lambda: shutil.which("catdoc"),
        ".ppt": lambda: shutil.which("catppt"),
    }
    missing = [suffix for suffix, probe in readers.items() if not probe()]
    assert not missing, f"formaty bez czytnika w tym środowisku: {missing}"
