"""Czyste funkcje etapu extract: głowa tekstu z dokumentu + podpisy podobieństwa.

Jedno miejsce prawdy o tym, *jak* czytamy treść i *jak* liczymy jej podpisy —
``scripts/extract_text.py`` dokłada wyłącznie kolejkę, bazę i wznawialność.

Warstwy podobieństwa (architektura, sekcja 5) liczone tutaj:

* :func:`normalized_text_hash` — ten sam tekst po normalizacji (re-eksport,
  docx→pdf). To wciąż hash: nowego zdania w środku NIE złapie.
* :func:`simhash` — podobieństwo odporne na wstawki i drobne edycje.
* :func:`perceptual_hash` — obrazy.

Żadna funkcja nie modyfikuje plików wejściowych; wejściem bywa ścieżka
w ``00_SOURCES`` (read-only), więc pliki otwieramy wyłącznie do odczytu.

Zależności opcjonalne (PyMuPDF, pdfplumber, python-docx, python-pptx, openpyxl,
xlrd, odfpy, Pillow, imagehash, pytesseract) ładuje :func:`_module` w momencie
użycia — brak paczki to :class:`ExtractionError` dla JEDNEGO pliku, a nie
wywrócenie całego przebiegu. Stare formaty binarne (.doc/.ppt/.pps) wymagają
systemowego pakietu ``catdoc``; jego brak daje metodę ``no_converter``.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import os
import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

#: Domyślny limit długości zapisywanej głowy tekstu (znaki).
DEFAULT_MAX_CHARS: int = 20_000

#: Domyślny limit stron czytanych z PDF (głowa dokumentu wystarcza do klasyfikacji).
DEFAULT_MAX_PAGES: int = 5

#: Domyślny limit stron poddawanych OCR (OCR jest o rzędy wielkości droższy).
DEFAULT_OCR_MAX_PAGES: int = 2

#: Poniżej tylu znaków znormalizowanego tekstu uznajemy, że warstwy tekstowej nie ma.
DEFAULT_OCR_MIN_CHARS: int = 120

#: Języki przekazywane tesseractowi (materiały są polskie, kod i slajdy bywają angielskie).
DEFAULT_OCR_LANG: str = "pol+eng"

#: DPI rasteryzacji strony PDF przed OCR — kompromis jakość/czas.
_OCR_DPI: int = 200

#: Rozmiar shingla (liczba słów) w :func:`simhash`.
_SHINGLE: int = 3

#: Ile bajtów pliku tekstowego czytamy, zanim utniemy go do ``max_chars`` znaków.
_TEXT_BYTES_PER_CHAR: int = 4

#: Metody ekstrakcji zwracane w :attr:`Extraction.method`.
METHODS: tuple[str, ...] = (
    "pdf_text",
    "pdf_plumber",
    "pdf_ocr",
    "docx",
    "pptx",
    "odf",
    "xlsx",
    "xls",
    "converter",
    "text",
    "image_ocr",
    "unsupported",
    "no_converter",
    "empty",
)

#: Stare formaty binarne Microsoftu -> zewnętrzny konwerter z pakietu ``catdoc``.
#: Żadna biblioteka Pythona ich nie czyta, a konwerter jest opcjonalny: jego brak
#: daje metodę ``no_converter`` (widoczną w podsumowaniu przebiegu), nie błąd.
LEGACY_CONVERTERS: dict[str, str] = {
    ".doc": "catdoc",
    ".ppt": "catppt",
    ".pps": "catppt",
}

#: Kodowanie ŹRÓDŁOWE zakładane dla starych formatów 8-bitowych.
#: Sprawdzone na realnym pliku ze źródeł: bez tego catdoc zakłada cp1252 i polskie
#: znaki zamieniają się w krzaki („Zminimalizowaæ funkcjê” zamiast
#: „Zminimalizować funkcję”). Dla .ppt/.pps flaga jest obojętna (PowerPoint trzyma
#: tekst w UTF-16), ale podajemy ją jednolicie. Korpus jest polski — gdyby kiedyś
#: przyszły materiały zachodnie, jest opcja ``--legacy-charset``.
DEFAULT_LEGACY_CHARSET: str = "cp1250"

#: Limit czasu jednego wywołania zewnętrznego konwertera.
_CONVERTER_TIMEOUT_S: int = 60

#: Ile wierszy arkusza czytamy, zanim uznamy, że głowa wystarczy do klasyfikacji.
_SHEET_MAX_ROWS: int = 200

_WHITESPACE = re.compile(r"\s+")


class ExtractionError(RuntimeError):
    """Nie udało się przeczytać treści TEGO pliku (uszkodzony plik, brak zależności)."""


@dataclass(frozen=True)
class Extraction:
    """Wynik ekstrakcji jednej treści."""

    text: str
    method: str
    #: OCR dał treść, która TRAFIŁA do wyniku. Uruchomienie tesseractu, którego
    #: rezultat odrzuciliśmy na rzecz warstwy tekstowej, zostawia tu ``False``.
    ocr_done: bool = False
    truncated: bool = False

    @property
    def has_text(self) -> bool:
        """Czy została jakakolwiek treść po normalizacji (sam biały znak się nie liczy)."""
        return bool(normalize_text(self.text))


def _module(name: str) -> Any:
    """Importuje zależność opcjonalną albo podnosi :class:`ExtractionError`.

    Wydzielone do osobnej funkcji celowo: testy podmieniają ten jeden punkt
    zamiast instalować cały stos PDF/OCR.
    """
    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - zależy od środowiska
        raise ExtractionError(f"brak zależności {name}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Normalizacja i podpisy
# --------------------------------------------------------------------------- #


def normalize_text(text: str) -> str:
    """Normalizuje tekst do porównań: NFKC, bez interpunkcji, jedna spacja, casefold.

    Interpunkcja i myślniki znikają świadomie — ten sam dokument wyeksportowany
    z DOCX i z PDF różni się dywizami, cudzysłowami i podziałem wierszy, a ma dać
    ten sam :func:`normalized_text_hash`. Cyfry i litery (także polskie) zostają.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")  # miękki dywiz z łamania wierszy w PDF
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return _WHITESPACE.sub(" ", cleaned).strip().casefold()


def normalized_text_hash(text: str) -> str | None:
    """sha256 znormalizowanego tekstu albo ``None``, gdy nie ma czego hashować."""
    normalized = normalize_text(text)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _shingles(words: Sequence[str], size: int = _SHINGLE) -> list[str]:
    """Dzieli słowa na nachodzące n-gramy; krótki tekst zwraca jako pojedyncze słowa."""
    if not words:
        return []
    if len(words) < size:
        return list(words)
    return [" ".join(words[i : i + size]) for i in range(len(words) - size + 1)]


def simhash(text: str, *, bits: int = 64, shingle: int = _SHINGLE) -> str | None:
    """SimHash znormalizowanego tekstu jako hex o stałej długości (``bits``/4 znaków).

    Wagą n-gramu jest liczba jego wystąpień. Zwraca ``None`` dla pustego tekstu —
    porównywanie „braku tekstu" z „brakiem tekstu" dałoby fałszywe near-dupe.
    Implementacja jest własna i deterministyczna (blake2b), żeby wartości w bazie
    nie zmieniły znaczenia przy podmianie biblioteki.
    """
    if bits <= 0 or bits % 8 != 0:
        raise ValueError(f"bits musi być dodatnią wielokrotnością 8, jest {bits}")
    if shingle < 1:
        raise ValueError(f"shingle musi być >= 1, jest {shingle}")
    tokens = _shingles(normalize_text(text).split(), shingle)
    if not tokens:
        return None
    vector = [0] * bits
    for token, weight in Counter(tokens).items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=bits // 8).digest()
        value = int.from_bytes(digest, "big")
        for index in range(bits):
            vector[index] += weight if (value >> index) & 1 else -weight
    result = sum(1 << index for index in range(bits) if vector[index] > 0)
    return f"{result:0{bits // 4}x}"


def hamming_distance(left: str, right: str) -> int:
    """Odległość Hamminga dwóch podpisów hex tej samej długości (simhash/phash)."""
    if len(left) != len(right):
        raise ValueError(f"podpisy różnej długości: {len(left)} vs {len(right)}")
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def perceptual_hash(path: Path) -> str | None:
    """phash obrazu (hex z ``imagehash``) albo ``None``, gdy pliku nie da się otworzyć jako obraz.

    Świadomie łagodne: `.svg` i uszkodzone miniatury mają nie wywracać etapu —
    brak phasha to po prostu brak jednej warstwy porównania.
    """
    image_module = _module("PIL.Image")
    imagehash = _module("imagehash")
    try:
        with image_module.open(path) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Ekstraktory per rodzaj treści
# --------------------------------------------------------------------------- #


def _cut(text: str, max_chars: int) -> tuple[str, bool]:
    """Ucina tekst do ``max_chars`` znaków; zwraca (tekst, czy_ucięty)."""
    text = text.replace("\0", " ")
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def _pdf_text(path: Path, max_chars: int, max_pages: int) -> str:
    """Warstwa tekstowa PDF przez PyMuPDF (pierwsze ``max_pages`` stron)."""
    pymupdf = _module("pymupdf")
    parts: list[str] = []
    length = 0
    try:
        with pymupdf.open(path) as document:
            for number, page in enumerate(document):
                if number >= max_pages or length >= max_chars:
                    break
                chunk = page.get_text("text") or ""
                parts.append(chunk)
                length += len(chunk)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"PyMuPDF: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _pdf_plumber_text(path: Path, max_chars: int, max_pages: int) -> str:
    """Awaryjny odczyt PDF przez pdfplumber (inny parser układu strony)."""
    pdfplumber = _module("pdfplumber")
    parts: list[str] = []
    length = 0
    try:
        with pdfplumber.open(path) as document:
            for number, page in enumerate(document.pages):
                if number >= max_pages or length >= max_chars:
                    break
                chunk = page.extract_text() or ""
                parts.append(chunk)
                length += len(chunk)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"pdfplumber: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _pdf_ocr_text(path: Path, max_chars: int, pages: int, lang: str) -> str:
    """OCR pierwszych ``pages`` stron PDF: rasteryzacja PyMuPDF + tesseract."""
    pymupdf = _module("pymupdf")
    pytesseract = _module("pytesseract")
    image_module = _module("PIL.Image")
    parts: list[str] = []
    length = 0
    try:
        with pymupdf.open(path) as document:
            for number, page in enumerate(document):
                if number >= pages or length >= max_chars:
                    break
                pixmap = page.get_pixmap(dpi=_OCR_DPI)
                with image_module.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                    chunk = pytesseract.image_to_string(image, lang=lang) or ""
                parts.append(chunk)
                length += len(chunk)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"OCR PDF: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _image_ocr_text(path: Path, lang: str) -> str:
    """OCR pojedynczego obrazu."""
    pytesseract = _module("pytesseract")
    image_module = _module("PIL.Image")
    try:
        with image_module.open(path) as image:
            return pytesseract.image_to_string(image, lang=lang) or ""
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"OCR obrazu: {type(exc).__name__}: {exc}") from exc


def _docx_text(path: Path) -> str:
    """Akapity i komórki tabel z DOCX (python-docx nie czyta .doc/.rtf/.odt)."""
    docx = _module("docx")
    try:
        document = docx.Document(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"python-docx: {type(exc).__name__}: {exc}") from exc
    return "\n".join(part for part in parts if part)


def _pptx_text(path: Path) -> str:
    """Tekst kształtów i notatek prelegenta z PPTX (kolejność slajdów zachowana)."""
    pptx = _module("pptx")
    try:
        presentation = pptx.Presentation(str(path))
        parts: list[str] = []
        for slide in presentation.slides:
            for shape in slide.shapes:
                text = getattr(shape, "text", "")
                if text:
                    parts.append(text)
            notes = getattr(slide, "notes_slide", None)
            notes_frame = getattr(notes, "notes_text_frame", None)
            if notes_frame is not None and notes_frame.text:
                parts.append(notes_frame.text)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"python-pptx: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _odf_text(path: Path) -> str:
    """Tekst z formatów OpenDocument (.odt/.ods/.odp) przez odfpy.

    Bierze akapity i nagłówki z całego dokumentu, więc obejmuje też komórki
    tabel i pola tekstowe slajdów — one również składają się z akapitów.
    """
    opendocument = _module("odf.opendocument")
    odf_text = _module("odf.text")
    teletype = _module("odf.teletype")
    try:
        document = opendocument.load(str(path))
        parts = [
            teletype.extractText(element)
            for kind in (odf_text.H, odf_text.P)
            for element in document.getElementsByType(kind)
        ]
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"odfpy: {type(exc).__name__}: {exc}") from exc
    return "\n".join(part for part in parts if part)


def _xlsx_text(path: Path, max_chars: int) -> str:
    """Nazwy arkuszy i głowa komórek z XLSX przez openpyxl (tryb read-only).

    ``data_only=True`` daje ostatnią zapisaną wartość formuły zamiast jej treści —
    do klasyfikacji liczy się to, co widać w arkuszu, nie jak zostało policzone.
    """
    openpyxl = _module("openpyxl")
    parts: list[str] = []
    length = 0
    workbook = None
    try:
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        for sheet in workbook.worksheets:
            parts.append(str(sheet.title))
            for number, row in enumerate(sheet.iter_rows(values_only=True)):
                if number >= _SHEET_MAX_ROWS or length >= max_chars:
                    break
                line = " | ".join(str(cell) for cell in row if cell is not None)
                if line:
                    parts.append(line)
                    length += len(line)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"openpyxl: {type(exc).__name__}: {exc}") from exc
    finally:
        if workbook is not None:
            workbook.close()
    return "\n".join(parts)


def _xls_text(path: Path, max_chars: int) -> str:
    """Nazwy arkuszy i głowa komórek ze starego XLS przez xlrd."""
    xlrd = _module("xlrd")
    parts: list[str] = []
    length = 0
    try:
        book = xlrd.open_workbook(str(path))
        for sheet in book.sheets():
            parts.append(str(sheet.name))
            for number in range(min(sheet.nrows, _SHEET_MAX_ROWS)):
                if length >= max_chars:
                    break
                line = " | ".join(
                    str(value) for value in sheet.row_values(number) if value not in ("", None)
                )
                if line:
                    parts.append(line)
                    length += len(line)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"xlrd: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _converter_text(path: Path, binary: str, charset: str) -> str | None:
    """Tekst ze starego formatu binarnego przez zewnętrzny konwerter (pakiet ``catdoc``).

    Zwraca ``None``, gdy konwertera NIE MA w systemie — brak czytnika dla formatu
    jest stanem środowiska, nie awarią pliku, więc wołający robi z tego
    ``no_converter``. Konwerter, który się uruchomił i zawiódł, to
    :class:`ExtractionError` — tu naprawdę nie udało się przeczytać pliku.
    """
    if shutil.which(binary) is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - stała nazwa binarki, bez powłoki
            [binary, "-s", charset, "-d", "utf-8", str(Path(os.path.abspath(path)))],
            capture_output=True,
            timeout=_CONVERTER_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExtractionError(f"{binary}: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise ExtractionError(f"{binary}: kod {completed.returncode}: {detail[0] if detail else ''}")
    return completed.stdout.decode("utf-8", errors="replace")


def _plain_text(path: Path, max_chars: int) -> str:
    """Plik tekstowy/kod: UTF-8, a przy błędzie cp1250 (stare notatki z Windows)."""
    limit = max(max_chars, 1) * _TEXT_BYTES_PER_CHAR
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit)
    except OSError as exc:
        raise ExtractionError(f"odczyt pliku: {type(exc).__name__}: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1250", errors="replace")


def extract(
    path: Path,
    content_kind: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_pages: int = DEFAULT_MAX_PAGES,
    ocr: bool = True,
    ocr_images: bool = False,
    ocr_lang: str = DEFAULT_OCR_LANG,
    ocr_max_pages: int = DEFAULT_OCR_MAX_PAGES,
    ocr_min_chars: int = DEFAULT_OCR_MIN_CHARS,
    legacy_charset: str | None = None,
) -> Extraction:
    """Zwraca głowę tekstu dla jednej treści zgodnie z jej ``content_kind``.

    OCR jest awaryjny, nie domyślny: uruchamia się dla PDF dopiero wtedy, gdy obie
    ścieżki tekstowe dały mniej niż ``ocr_min_chars`` znaków po normalizacji.
    Awaria pdfplumber jest tolerowana (to tylko druga opinia o układzie strony),
    natomiast awaria OCR leci dalej jako :class:`ExtractionError` — plik bez
    warstwy tekstowej, którego nie dało się rozpoznać, ma trafić na status
    'error' i czekać na ``--retry-errors``, a nie udawać pustego.
    Obrazy wymagają jawnego ``ocr_images`` — w źródłach jest ich kilkanaście
    tysięcy i OCR całości kosztowałby godziny bez związku z klasyfikacją.

    Stare formaty binarne Microsoftu (``.doc``, ``.ppt``, ``.pps``) idą przez
    zewnętrzny konwerter z pakietu ``catdoc``, z kodowaniem źródłowym
    ``legacy_charset``. ``None`` oznacza :data:`DEFAULT_LEGACY_CHARSET` czytane
    w momencie WYWOŁANIA — stała jako domyślna wartość argumentu wiązałaby się
    przy imporcie, więc jej podmiana (np. w teście regresji) nie miałaby skutku. Jego brak w systemie NIE jest
    awarią pliku: wynik ma wtedy metodę ``no_converter``, widoczną w podsumowaniu
    przebiegu, więc doinstalowanie pakietu i ponowny przebieg z ``--force``
    domykają temat bez zmian w kodzie.

    Rodzaje bez sensownej reprezentacji tekstowej (``archive``, ``media``,
    ``other``, a także ``.rtf``, którego nie czyta żadna z zależności projektu)
    zwracają pusty tekst z metodą ``unsupported``. To NIE jest błąd — plik ma
    normalnie przejść na status 'extracted'.
    """
    path = Path(path)
    suffix = path.suffix.casefold()

    if content_kind == "pdf":
        text = _pdf_text(path, max_chars, max_pages)
        method = "pdf_text"
        if len(normalize_text(text)) < ocr_min_chars:
            # pdfplumber jest wyłącznie drugą opinią o układzie strony: jego
            # awaria nie może unieważnić tekstu, który PyMuPDF już przeczytał.
            try:
                fallback = _pdf_plumber_text(path, max_chars, max_pages)
            except ExtractionError:
                fallback = ""
            if len(normalize_text(fallback)) > len(normalize_text(text)):
                text, method = fallback, "pdf_plumber"
        if ocr and len(normalize_text(text)) < ocr_min_chars:
            scanned = _pdf_ocr_text(path, max_chars, ocr_max_pages, ocr_lang)
            # Warstwa tekstowa jest dokładniejsza od OCR, więc wynik OCR wchodzi
            # tylko wtedy, gdy realnie dołożył treści (krótki, ale poprawny PDF
            # nie ma prawa zostać zastąpiony szumem z rozpoznawania obrazu).
            if len(normalize_text(scanned)) > len(normalize_text(text)):
                cut, truncated = _cut(scanned, max_chars)
                return Extraction(cut, "pdf_ocr", ocr_done=True, truncated=truncated)
        cut, truncated = _cut(text, max_chars)
        return Extraction(cut, method if normalize_text(cut) else "empty", truncated=truncated)

    if suffix in LEGACY_CONVERTERS and content_kind in ("docx", "pptx", "xlsx"):
        converted = _converter_text(
            path, LEGACY_CONVERTERS[suffix], legacy_charset or DEFAULT_LEGACY_CHARSET
        )
        if converted is None:
            return Extraction("", "no_converter")
        cut, truncated = _cut(converted, max_chars)
        return Extraction(cut, "converter" if normalize_text(cut) else "empty", truncated=truncated)

    if suffix in (".odt", ".ods", ".odp") and content_kind in ("docx", "pptx", "xlsx"):
        cut, truncated = _cut(_odf_text(path), max_chars)
        return Extraction(cut, "odf" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind == "docx":
        if suffix != ".docx":
            return Extraction("", "unsupported")
        cut, truncated = _cut(_docx_text(path), max_chars)
        return Extraction(cut, "docx" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind == "pptx":
        if suffix not in (".pptx", ".ppsx"):
            return Extraction("", "unsupported")
        cut, truncated = _cut(_pptx_text(path), max_chars)
        return Extraction(cut, "pptx" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind == "xlsx" and suffix == ".xls":
        cut, truncated = _cut(_xls_text(path, max_chars), max_chars)
        return Extraction(cut, "xls" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind == "xlsx" and suffix in (".xlsx", ".xlsm"):
        cut, truncated = _cut(_xlsx_text(path, max_chars), max_chars)
        return Extraction(cut, "xlsx" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind in ("text", "code") or (content_kind == "xlsx" and suffix == ".csv"):
        cut, truncated = _cut(_plain_text(path, max_chars), max_chars)
        return Extraction(cut, "text" if normalize_text(cut) else "empty", truncated=truncated)

    if content_kind == "image":
        if not (ocr and ocr_images) or suffix == ".svg":
            return Extraction("", "unsupported")
        cut, truncated = _cut(_image_ocr_text(path, ocr_lang), max_chars)
        if not normalize_text(cut):
            return Extraction("", "empty", ocr_done=True)
        return Extraction(cut, "image_ocr", ocr_done=True, truncated=truncated)

    return Extraction("", "unsupported")
