"""Testy B2: podpisy tekstu i ekstrakcja małych dokumentów z tmp_path.

Biblioteki dokumentów są prawdziwe; tylko pytesseract dostaje atrapę bez procesu OCR.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import docx
import pymupdf
import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from orglib import textextract


@pytest.fixture(autouse=True)
def fake_ocr(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Podmienia wyłącznie pytesseract i zabrania niezamówionego OCR."""
    real_module = textextract._module
    recognize = Mock(side_effect=lambda *a, **kw: pytest.fail("nieoczekiwane OCR"))

    def module(name: str):
        if name == "pytesseract":
            return SimpleNamespace(image_to_string=recognize)
        return real_module(name)

    monkeypatch.setattr(textextract, "_module", module)
    return recognize


def _pdf(path: Path, text: str = "") -> Path:
    """Tworzy jednostronicowy PDF z warstwą tekstową albo pustą stroną skanu."""
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=200)
        if text:
            page.insert_text((20, 30), text, fontsize=10)
        document.save(path)
    return path


@pytest.fixture()
def png(tmp_path: Path) -> Path:
    """Tworzy prawdziwy, mały obraz rastrowy."""
    path = tmp_path / "obraz.png"
    with Image.new("RGB", (32, 24), "white") as image:
        image.paste("black", (0, 0, 12, 16))
        image.save(path)
    return path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  Ala\tma\n kota\r\n i\u00a0psa  ", "ala ma kota i psa"),
        ("Ala, MA—kota! (123)_+", "ala ma kota 123"),
        ("Zażółć GĘŚLĄ JAŹŃ; ĄĆĘŁŃÓŚŹŻ", "zażółć gęślą jaźń ąćęłńóśźż"),
        ("mięk\u00adki dywiz", "miękki dywiz"),
        ("ＡＢＣ ① ﬁ Z\u0307", "abc 1 fi ż"),
        ("Straße", "strasse"),
        ("", ""),
        (" \n\t!?—\u00ad", ""),
    ],
)
def test_normalize_text(text: str, expected: str) -> None:
    """Normalizacja zachowuje litery i cyfry, usuwając różnice formatowania."""
    assert textextract.normalize_text(text) == expected


def test_normalized_text_hash_matches_sha256_and_formatting() -> None:
    """Hash dotyczy znormalizowanej treści zakodowanej w UTF-8."""
    expected = hashlib.sha256("zażółć gęślą jaźń".encode("utf-8")).hexdigest()
    assert textextract.normalized_text_hash(" ZAŻÓŁĆ, gęślą\nJAŹŃ! ") == expected
    assert textextract.normalized_text_hash("zażółć gęślą jaźń") == expected
    assert textextract.normalized_text_hash("inna treść") != expected


@pytest.mark.parametrize("text", ["", "   \n\t", "!?—\u00ad"])
def test_empty_text_has_no_signatures(text: str) -> None:
    """Brak treści nie tworzy fałszywego podpisu podobieństwa."""
    assert textextract.normalized_text_hash(text) is None
    assert textextract.simhash(text) is None


@pytest.mark.parametrize("bits", [32, 64])
def test_simhash_has_fixed_hex_length_and_ignores_formatting(bits: int) -> None:
    """Podpis jest deterministycznym hexem o zadanej długości."""
    signature = textextract.simhash("Ala ma kota", bits=bits)
    assert re.fullmatch(r"[0-9a-f]{%d}" % (bits // 4), signature)
    assert signature == textextract.simhash(" ALA, ma\nkota!", bits=bits)


def test_simhash_distinguishes_small_edit_from_unrelated_text() -> None:
    """Jedna zmiana słowa jest bliższa oryginałowi niż obcy temat."""
    original = (
        "Algorytm sortowania dzieli tablicę na mniejsze fragmenty i porównuje kolejne "
        "elementy następnie scala uporządkowane części w całość analiza złożoności "
        "uwzględnia liczbę operacji oraz pamięć potrzebną do przechowania danych "
        "struktury drzewiaste pozwalają sprawnie wyszukiwać klucze w dużych zbiorach"
    )
    unrelated = (
        "Na patelni rozgrzewamy oliwę dodajemy cebulę czosnek pomidory bazylię "
        "oraz pieprz gotujemy sos pod przykryciem makaron odcedzamy mieszamy "
        "z warzywami posypujemy serem podajemy obiad na talerzach udekorowanych "
        "świeżymi ziołami deser przygotowujemy ze śmietany truskawek cukru wanilii"
    )
    base = textextract.simhash(original)
    near = textextract.hamming_distance(base, textextract.simhash(original.replace("dużych", "małych")))
    far = textextract.hamming_distance(base, textextract.simhash(unrelated))
    assert near <= 10
    assert far >= 20
    assert far >= near + 10


@pytest.mark.parametrize("bits", [0, -8, 7, 31, 65])
def test_simhash_rejects_invalid_bits(bits: int) -> None:
    """Szerokość podpisu musi być dodatnią wielokrotnością ośmiu."""
    with pytest.raises(ValueError, match="bits"):
        textextract.simhash("tekst", bits=bits)


@pytest.mark.parametrize("shingle", [0, -1])
def test_simhash_rejects_invalid_shingle(shingle: int) -> None:
    """Nie można budować n-gramów o niedodatniej długości."""
    with pytest.raises(ValueError, match="shingle"):
        textextract.simhash("tekst", shingle=shingle)


def test_hamming_distance_counts_bits() -> None:
    """XOR 0f i 33 to 3c, czyli dokładnie cztery ustawione bity."""
    assert textextract.hamming_distance("0f", "33") == 4
    assert textextract.hamming_distance("ff", "ff") == 0
    with pytest.raises(ValueError, match="różnej długości"):
        textextract.hamming_distance("0f", "f")


def test_extraction_is_frozen_and_has_text_uses_normalization() -> None:
    """Wynik jest niemutowalny, a sama interpunkcja nie jest treścią."""
    result = textextract.Extraction("Żółć", "text")
    assert result.has_text
    assert not result.ocr_done
    assert not result.truncated
    assert not textextract.Extraction(" \n!?\u00ad", "empty").has_text
    with pytest.raises(FrozenInstanceError):
        result.text = "zmiana"


def test_pdf_text_layer_avoids_ocr(tmp_path: Path, fake_ocr: Mock) -> None:
    """Dostatecznie długa warstwa tekstowa nie wymaga OCR."""
    text = "\n".join(["Algorithms and data structures lecture."] * 5)
    result = textextract.extract(_pdf(tmp_path / "tekst.pdf", text), "pdf")
    assert result.method == "pdf_text"
    assert textextract.normalize_text(result.text) == textextract.normalize_text(text)
    assert not result.ocr_done
    fake_ocr.assert_not_called()


def test_scanned_pdf_uses_ocr(tmp_path: Path, fake_ocr: Mock) -> None:
    """Pusta warstwa PDF uruchamia atrapę OCR na prawdziwym obrazie strony."""
    fake_ocr.side_effect = None
    fake_ocr.return_value = "Rozpoznana treść skanu"
    result = textextract.extract(_pdf(tmp_path / "skan.pdf"), "pdf", ocr_lang="pol")
    assert result == textextract.Extraction("Rozpoznana treść skanu", "pdf_ocr", ocr_done=True)
    fake_ocr.assert_called_once()
    assert isinstance(fake_ocr.call_args.args[0], Image.Image)
    assert fake_ocr.call_args.kwargs == {"lang": "pol"}


@pytest.mark.parametrize("recognized", ["", "Kot", "Ala ma kota"])
def test_short_pdf_keeps_text_when_ocr_is_not_longer(
    tmp_path: Path, fake_ocr: Mock, recognized: str
) -> None:
    """OCR krótszy lub równy warstwie tekstowej nie zastępuje jej wyniku."""
    fake_ocr.side_effect = None
    fake_ocr.return_value = recognized
    result = textextract.extract(_pdf(tmp_path / "krotki.pdf", "Ala ma kota"), "pdf")
    assert result.method == "pdf_text"
    assert result.text.strip() == "Ala ma kota"
    assert not result.ocr_done
    fake_ocr.assert_called_once()


def test_scanned_pdf_without_ocr_is_empty(tmp_path: Path, fake_ocr: Mock) -> None:
    """Wyłączenie OCR pozostawia skan bez tekstu, ale bez błędu."""
    result = textextract.extract(_pdf(tmp_path / "skan.pdf"), "pdf", ocr=False)
    assert result == textextract.Extraction("", "empty")
    fake_ocr.assert_not_called()


def test_pdf_plumber_fallback_is_selected_when_longer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_ocr: Mock
) -> None:
    """Alternatywny parser wygrywa wyłącznie dzięki bogatszej treści."""
    path = _pdf(tmp_path / "uklad.pdf", "Kot")
    # Różnicę parserów izolujemy na wyniku fallbacku; PyMuPDF czyta realny PDF.
    fallback = Mock(return_value="Znacznie bogatszy opis wykładu")
    monkeypatch.setattr(textextract, "_pdf_plumber_text", fallback)
    result = textextract.extract(path, "pdf", ocr_min_chars=10)
    assert result == textextract.Extraction(fallback.return_value, "pdf_plumber")
    fallback.assert_called_once()
    fake_ocr.assert_not_called()


def test_docx_includes_paragraphs_and_table(tmp_path: Path) -> None:
    """DOCX udostępnia zarówno akapity, jak i komórki tabel."""
    path = tmp_path / "notatki.docx"
    document = docx.Document()
    document.add_paragraph("Pierwszy akapit")
    document.add_paragraph("Drugi akapit")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Lewa komórka"
    table.cell(0, 1).text = "Prawa komórka"
    document.save(path)
    result = textextract.extract(path, "docx")
    assert result.method == "docx"
    assert result.text.splitlines() == ["Pierwszy akapit", "Drugi akapit", "Lewa komórka", "Prawa komórka"]


def test_pptx_includes_shape_and_speaker_notes(tmp_path: Path) -> None:
    """Notatka prelegenta nie ginie przy odczycie kształtów slajdu."""
    path = tmp_path / "wyklad.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    shape.text = "Treść slajdu"
    slide.notes_slide.notes_text_frame.text = "Notatka prelegenta"
    presentation.save(path)
    result = textextract.extract(path, "pptx")
    assert result.method == "pptx"
    assert "Treść slajdu" in result.text
    assert "Notatka prelegenta" in result.text


@pytest.mark.parametrize(
    ("suffix", "kind", "encoding"),
    [(".txt", "text", "utf-8"), (".txt", "text", "cp1250"),
     (".csv", "xlsx", "utf-8"), (".py", "code", "utf-8")],
)
def test_plain_text_decoding(tmp_path: Path, suffix: str, kind: str, encoding: str) -> None:
    """Tekst, kod i CSV zachowują polskie znaki w obu kodowaniach."""
    path = tmp_path / f"tekst{suffix}"
    text = "Zażółć gęślą jaźń;liczba\nŁódź;42"
    path.write_bytes(text.encode(encoding))
    assert textextract.extract(path, kind) == textextract.Extraction(text, "text")


@pytest.mark.parametrize(
    ("suffix", "kind"),
    [(".rtf", "docx"), (".zip", "archive"), (".mp4", "media"), (".bin", "other")],
)
def test_unsupported_formats(tmp_path: Path, suffix: str, kind: str) -> None:
    """Nieobsługiwany format jest pustym wynikiem, a nie awarią odczytu."""
    path = tmp_path / f"plik{suffix}"
    path.write_bytes(b"nieobslugiwany format")
    assert textextract.extract(path, kind) == textextract.Extraction("", "unsupported")


@pytest.mark.parametrize(("ocr", "ocr_images"), [(True, False), (False, True)])
def test_image_ocr_requires_both_options(png: Path, fake_ocr: Mock, ocr: bool, ocr_images: bool) -> None:
    """Obraz wymaga jednocześnie zgody na OCR i OCR obrazów."""
    assert textextract.extract(png, "image", ocr=ocr, ocr_images=ocr_images).method == "unsupported"
    fake_ocr.assert_not_called()


@pytest.mark.parametrize(("text", "method"), [("Treść obrazu", "image_ocr"), ("", "empty")])
def test_image_ocr(png: Path, fake_ocr: Mock, text: str, method: str) -> None:
    """OCR obrazu raportuje wykonanie także wtedy, gdy nie rozpoznał tekstu."""
    fake_ocr.side_effect = None
    fake_ocr.return_value = text
    assert textextract.extract(png, "image", ocr_images=True) == textextract.Extraction(text, method, ocr_done=True)
    fake_ocr.assert_called_once()
    assert fake_ocr.call_args.kwargs == {"lang": "pol+eng"}


def test_svg_is_unsupported_even_with_ocr(tmp_path: Path, fake_ocr: Mock) -> None:
    """Grafika wektorowa nie trafia do rastrowego OCR."""
    path = tmp_path / "rysunek.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    assert textextract.extract(path, "image", ocr_images=True).method == "unsupported"
    fake_ocr.assert_not_called()


@pytest.mark.parametrize(("text", "truncated"), [("123456789", True), ("12345", False)])
def test_max_chars_truncation(tmp_path: Path, text: str, truncated: bool) -> None:
    """Limit znaków ucina głowę, a dokładna długość limitu nie oznacza ucięcia."""
    path = tmp_path / "tekst.txt"
    path.write_text(text, encoding="utf-8")
    assert textextract.extract(path, "text", max_chars=5) == textextract.Extraction(text[:5], "text", truncated=truncated)


def test_empty_supported_format(tmp_path: Path) -> None:
    """Obsługiwany plik bez alfanumerycznej treści ma metodę empty."""
    path = tmp_path / "pusty.txt"
    path.write_text(" \n!?", encoding="utf-8")
    result = textextract.extract(path, "text")
    assert result.method == "empty"
    assert not result.has_text


def test_perceptual_hash_of_png(png: Path) -> None:
    """Prawdziwy PNG daje powtarzalny podpis obrazu zapisany jako hex."""
    signature = textextract.perceptual_hash(png)
    assert re.fullmatch(r"[0-9a-f]{16}", signature)
    assert textextract.perceptual_hash(png) == signature


def test_perceptual_hash_of_non_image_is_none(tmp_path: Path) -> None:
    """Niepoprawny obraz nie podnosi wyjątku podczas liczenia phasha."""
    path = tmp_path / "falszywy.png"
    path.write_text("To nie obraz", encoding="utf-8")
    assert textextract.perceptual_hash(path) is None
    assert textextract.perceptual_hash(tmp_path / "brak.png") is None


@pytest.mark.parametrize(("suffix", "kind"), [(".pdf", "pdf"), (".docx", "docx"), (".pptx", "pptx")])
def test_corrupt_document_raises_extraction_error(tmp_path: Path, suffix: str, kind: str) -> None:
    """Awaria pojedynczego dokumentu jest opakowana w ExtractionError."""
    path = tmp_path / f"uszkodzony{suffix}"
    path.write_bytes(b"to nie jest dokument")
    with pytest.raises(textextract.ExtractionError):
        textextract.extract(path, kind)


def test_pdf_plumber_failure_keeps_text_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_ocr: Mock
) -> None:
    """Awaria parsera awaryjnego nie unieważnia tekstu przeczytanego przez PyMuPDF."""
    path = _pdf(tmp_path / "krotki.pdf", "Ala ma kota")
    broken = Mock(side_effect=textextract.ExtractionError("pdfplumber padł"))
    monkeypatch.setattr(textextract, "_pdf_plumber_text", broken)
    result = textextract.extract(path, "pdf", ocr=False)
    assert result.method == "pdf_text"
    assert result.text.strip() == "Ala ma kota"
    broken.assert_called_once()
    fake_ocr.assert_not_called()


def test_pdf_ocr_failure_is_reported_not_silenced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skan, którego nie dało się rozpoznać, ma być błędem, a nie pustym wynikiem."""
    path = _pdf(tmp_path / "skan.pdf")
    monkeypatch.setattr(
        textextract, "_pdf_ocr_text", Mock(side_effect=textextract.ExtractionError("brak tesseractu"))
    )
    with pytest.raises(textextract.ExtractionError, match="brak tesseractu"):
        textextract.extract(path, "pdf")


# --------------------------------------------------------------------------- #
# Arkusze, OpenDocument i stare formaty binarne przez zewnętrzny konwerter
# --------------------------------------------------------------------------- #


def test_xlsx_includes_sheet_names_and_cells(tmp_path: Path) -> None:
    """Arkusz wnosi do klasyfikacji nazwy zakładek i treść komórek."""
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "oceny.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Kolokwium 1"
    sheet.append(["Nazwisko", "Punkty"])
    sheet.append(["Kowalski", 42])
    workbook.save(path)
    result = textextract.extract(path, "xlsx")
    assert result.method == "xlsx"
    assert "Kolokwium 1" in result.text
    assert "Nazwisko | Punkty" in result.text
    assert "Kowalski | 42" in result.text


def test_xls_is_routed_to_xlrd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stary arkusz czyta xlrd, a nie zewnętrzny konwerter."""
    path = tmp_path / "stary.xls"
    path.write_bytes(b"udawany xls")
    reader = Mock(return_value="Arkusz1\nDane | 7")
    monkeypatch.setattr(textextract, "_xls_text", reader)
    result = textextract.extract(path, "xlsx")
    assert result == textextract.Extraction("Arkusz1\nDane | 7", "xls")
    reader.assert_called_once()


@pytest.mark.parametrize(("suffix", "kind"), [(".odt", "docx"), (".ods", "xlsx"), (".odp", "pptx")])
def test_odf_documents(tmp_path: Path, suffix: str, kind: str) -> None:
    """Rodzina OpenDocument idzie jedną ścieżką przez odfpy."""
    pytest.importorskip("odf")
    from odf.opendocument import OpenDocumentText
    from odf.text import H, P

    path = tmp_path / f"dokument{suffix}"
    document = OpenDocumentText()
    heading = H(outlinelevel=1, text="Sprawozdanie z laboratorium")
    document.text.addElement(heading)
    paragraph = P(text="Pomiary wykonano w semestrze zimowym")
    document.text.addElement(paragraph)
    document.save(str(path))
    result = textextract.extract(path, kind)
    assert result.method == "odf"
    assert "Sprawozdanie z laboratorium" in result.text
    assert "Pomiary wykonano w semestrze zimowym" in result.text


def test_ppsx_is_read_by_python_pptx(tmp_path: Path) -> None:
    """Pokaz .ppsx to ten sam OOXML co .pptx — nie wymaga konwertera."""
    path = tmp_path / "pokaz.ppsx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    shape.text = "Pokaz z wykładu"
    presentation.save(path)
    result = textextract.extract(path, "pptx")
    assert result.method == "pptx"
    assert "Pokaz z wykładu" in result.text


@pytest.mark.parametrize(
    ("suffix", "kind", "binary"),
    [(".doc", "docx", "catdoc"), (".ppt", "pptx", "catppt"), (".pps", "pptx", "catppt")],
)
def test_legacy_binary_uses_external_converter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, kind: str, binary: str
) -> None:
    """Stary format binarny woła właściwą binarkę z pakietu catdoc, bez powłoki."""
    path = tmp_path / f"stary{suffix}"
    path.write_bytes(b"binarny format")
    monkeypatch.setattr(textextract.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="Wykład 3\n".encode("utf-8"), stderr=b""))
    monkeypatch.setattr(textextract.subprocess, "run", run)
    result = textextract.extract(path, kind)
    assert result == textextract.Extraction("Wykład 3\n", "converter")
    argv = run.call_args.args[0]
    assert argv[0] == binary
    # Bez jawnego kodowania źródłowego catdoc zakłada cp1252 i polskie znaki
    # zamieniają się w krzaki — sprawdzone na realnym pliku ze źródeł.
    assert argv[1:5] == ["-s", textextract.DEFAULT_LEGACY_CHARSET, "-d", "utf-8"]
    assert Path(argv[-1]).is_absolute()
    assert run.call_args.kwargs["timeout"] > 0


@pytest.mark.parametrize(("suffix", "kind"), [(".doc", "docx"), (".ppt", "pptx"), (".pps", "pptx")])
def test_missing_converter_is_visible_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, kind: str
) -> None:
    """Brak pakietu catdoc daje osobną metodę, a nie błąd i nie ciche 'unsupported'."""
    path = tmp_path / f"stary{suffix}"
    path.write_bytes(b"binarny format")
    monkeypatch.setattr(textextract.shutil, "which", lambda name: None)
    run = Mock(side_effect=AssertionError("nie wolno wołać nieobecnego konwertera"))
    monkeypatch.setattr(textextract.subprocess, "run", run)
    assert textextract.extract(path, kind) == textextract.Extraction("", "no_converter")
    run.assert_not_called()


def test_converter_failure_is_extraction_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Konwerter, który się uruchomił i zawiódł, to awaria pliku, nie brak obsługi."""
    path = tmp_path / "uszkodzony.doc"
    path.write_bytes(b"binarny format")
    monkeypatch.setattr(textextract.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        textextract.subprocess, "run",
        Mock(return_value=SimpleNamespace(returncode=1, stdout=b"", stderr="nie ten format\n".encode("utf-8"))),
    )
    with pytest.raises(textextract.ExtractionError, match="catdoc"):
        textextract.extract(path, "docx")


@pytest.mark.parametrize(("suffix", "kind"), [(".xlsx", "xlsx"), (".odt", "docx"), (".ods", "xlsx")])
def test_corrupt_sheet_or_odf_raises_extraction_error(tmp_path: Path, suffix: str, kind: str) -> None:
    """Uszkodzony arkusz i uszkodzony OpenDocument zgłaszają awarię pojedynczego pliku."""
    path = tmp_path / f"uszkodzony{suffix}"
    path.write_bytes(b"to nie jest dokument")
    with pytest.raises(textextract.ExtractionError):
        textextract.extract(path, kind)
