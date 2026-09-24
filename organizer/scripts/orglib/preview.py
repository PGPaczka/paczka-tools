"""Podgląd treści: głowa tekstu, miniatura i strona PDF — jedna implementacja.

Powstało dla studia (S1.3), ale miniatury liczył już raport przeglądu (B9), więc
logika leży tutaj, a nie w dwóch miejscach: cache w ``work/thumbnails`` jest
wspólny, a „praca raz na treść” obowiązuje tak samo w HTML-u, jak w API.

Wszystkie ścieżki z bazy przechodzą przez ``config.resolve_within`` /
``config.resolve_within_sources``. Podgląd jest jedyną drogą, którą aplikacja
sięga po materiały, więc wpis prowadzący poza swoje drzewo — bezwzględny, przez
``..`` albo przez dowiązanie — kończy się ``None``, a nie odczytem. To błąd
danych, nie prośba (``studio/AGENTS.md``, reguła 4).

Materiałów NIC tutaj nie zapisuje: jedyny zapis to plik miniatury w ``work``,
katalogu odtwarzalnym z definicji.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Iterable

from . import config

#: Rozmiar miniatury (dłuższy bok) i jakość JPEG — wspólne z raportem B9.
THUMBNAIL_SIZE: tuple[int, int] = (320, 320)
THUMBNAIL_QUALITY: int = 72

#: Jakość JPEG dla renderowanej strony PDF. 82 to próg, powyżej którego rośnie
#: już tylko rozmiar — sprawdzone na skanach i slajdach z tej paczki.
PAGE_QUALITY: int = 82

#: Szerokość renderowanej strony PDF w pikselach. Tyle wystarcza, żeby z ekranu
#: rozpoznać, co to za dokument; więcej kosztuje tylko czas i pamięć.
PAGE_WIDTH: int = 1000

#: Rodzaje treści, dla których umiemy pokazać obraz.
IMAGE_KINDS = frozenset({"image"})
PAGE_KINDS = frozenset({"pdf"})

#: Rodzaje treści, w których plik źródłowy JEST tekstem — więc wolno go pokazać
#: wprost, gdy etap extract go nie dotknął. ``other`` jest tu celowo: ten kubeł
#: opisuje etap potoku, a nie to, czy coś da się przeczytać (leżą w nim m.in.
#: pliki projektowe Visual Studio, czyli zwykły XML).
SOURCE_TEXT_KINDS = frozenset({"text", "code", "other", ""})

#: Ile bajtów źródła wolno powąchać przy rozstrzyganiu „tekst czy binarka".
SNIFF_BYTES: int = 65536

#: Rozszerzenie → język dla kolorowania składni. Rozstrzyga backend, bo to reguła
#: o treści, a front ma nie zgadywać po nazwie (``studio/AGENTS.md``, reguła 1).
TEXT_LANGUAGES: dict[str, str] = {
    ".md": "markdown", ".markdown": "markdown",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".java": "java", ".py": "python", ".rb": "ruby", ".go": "go", ".rs": "rust",
    ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".jsx": "javascript",
    ".php": "php", ".pl": "perl", ".lua": "lua", ".kt": "kotlin", ".swift": "swift",
    ".m": "matlab", ".asm": "x86asm", ".s": "x86asm", ".vhd": "vhdl", ".v": "verilog",
    ".sh": "bash", ".bash": "bash", ".bat": "dos", ".ps1": "powershell",
    ".sql": "sql", ".r": "r", ".scala": "scala", ".f90": "fortran", ".pas": "delphi",
    ".html": "xml", ".htm": "xml", ".xml": "xml", ".xsd": "xml", ".svg": "xml",
    ".vcxproj": "xml", ".csproj": "xml", ".props": "xml", ".config": "xml",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "ini", ".ini": "ini",
    ".css": "css", ".scss": "scss", ".tex": "latex", ".csv": "plaintext",
    ".txt": "plaintext", ".log": "plaintext",
}


def text_language(filename: str, content_kind: str | None) -> str | None:
    """Język do kolorowania składni, albo ``None``, gdy nie ma czego kolorować.

    Tekst wyciągnięty z PDF-a czy docx-a jest wypisem, nie kodem — kolorowanie go
    byłoby kłamstwem o tym, co człowiek ogląda.
    """
    if (content_kind or "") not in SOURCE_TEXT_KINDS:
        return None
    return TEXT_LANGUAGES.get(Path(filename).suffix.lower())


def looks_like_text(raw: bytes) -> str | None:
    """Zdekodowany początek pliku, gdy to tekst; ``None``, gdy bajty są binarne.

    Wysypanie zawartości ``.obj`` na ekran jest gorsze niż uczciwe „nie ma czego
    pokazać", więc decyduje treść, nie rozszerzenie: bajt zerowy albo gęstwina
    znaków sterujących kończy podgląd.
    """
    if not raw:
        return None
    for bom, encoding in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"), (b"\xef\xbb\xbf", "utf-8-sig")):
        if raw.startswith(bom):
            try:
                return raw.decode(encoding, errors="replace")
            except (UnicodeError, LookupError):
                return None
    if b"\x00" in raw:
        return None
    for encoding in ("utf-8", "cp1250"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        control = sum(1 for char in text if ord(char) < 32 and char not in "\t\n\r")
        return None if control > len(text) * 0.02 else text
    return None


def source_text_head(source: Path, limit: int) -> str | None:
    """Głowa tekstu wzięta wprost z pliku źródłowego (tylko do odczytu).

    Potrzebne, bo extract pomija tysiące pozycji (``other`` w całości, część
    ``text``/``code``), a decyzja o nich i tak zapada po tym, co w nich jest.
    """
    try:
        with source.open("rb") as handle:
            raw = handle.read(min(SNIFF_BYTES, max(limit * 4, 1024)))
    except OSError:
        return None
    text = looks_like_text(raw)
    return None if text is None else text[:limit]


def text_head(paths: config.Paths, relative_path: str | None, limit: int) -> str | None:
    """Głowa tekstu z ``work`` (ścieżka z ``content.extracted_text_path``).

    Etap extract (B2) zapisuje ją **względem ``work``** — sklejenie jej z czymkolwiek
    innym daje pusty podgląd na realnych danych, mimo zielonych testów na ścieżce
    bezwzględnej (wpadka S1.3, 2026-09-22).
    """
    if not relative_path:
        return None
    resolved = config.resolve_within(paths.work, relative_path)
    if resolved is None or not resolved.is_file():
        return None
    try:
        return resolved.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def package_copy(paths: config.Paths, conn: sqlite3.Connection, sha256: str) -> Path | None:
    """Kopia treści leżąca w PACZCE, wskazana przez decyzję.

    890 pozycji ground truth nie ma ani jednego wiersza w ``files``: materiał trafił do
    paczki dawno temu i nikt nie indeksował go jako pliku źródłowego. Bez tej ścieżki
    ich podgląd w grafie był zepsutym obrazkiem, choć plik leży na dysku i wolno go
    przeczytać. Ścieżka z bazy przechodzi przez ten sam containment co reszta — wpis
    prowadzący poza repo paczki to błąd danych, nie prośba o odczyt.
    """
    row = conn.execute(
        "SELECT target_relative_path FROM classifications WHERE sha256 = ? "
        "AND target_relative_path IS NOT NULL "
        "ORDER BY (run_id = 'ground_truth') DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    if row is None or not row["target_relative_path"]:
        return None
    candidate = config.resolve_within(paths.target_repo, str(row["target_relative_path"]))
    return candidate if candidate is not None and candidate.is_file() else None


def source_copies(conn: sqlite3.Connection, sha256: str) -> list[tuple[str, str]]:
    """Wszystkie materializacje treści jako pary (paczka, ścieżka względem paczki)."""
    rows = conn.execute(
        "SELECT source_package, source_relative_path FROM files WHERE sha256 = ? ORDER BY file_id",
        (sha256,),
    ).fetchall()
    return [(str(row["source_package"]), str(row["source_relative_path"])) for row in rows]


def first_existing_copy(paths: config.Paths, copies: Iterable[tuple[str, str]]) -> Path | None:
    """Pierwsza kopia treści, która NAPRAWDĘ leży na dysku w drzewie źródeł.

    Treść bez ani jednej istniejącej kopii to normalny stan (wpis prowenancyjny
    z paczki-duplikatu), więc ``None`` nie jest błędem — podgląd po prostu nie ma
    czego pokazać.
    """
    for package, relative in copies:
        candidate = config.resolve_within_sources(paths.sources, package, relative)
        if candidate is not None and candidate.is_file():
            return candidate
    return None


def render_pdf_page(path: Path, *, page: int = 1, width: int = PAGE_WIDTH) -> bytes | None:
    """Renderuje stronę PDF do JPEG (PyMuPDF). ``None``, gdy pliku nie da się otworzyć.

    JPEG, nie PNG: zmierzone na realnym wykładzie AKO przy 1000 px — PNG 1006 KiB,
    JPEG 110 KiB. To jest PODGLĄD, który ma odpowiedzieć na pytanie „co to za
    dokument”, a nie reprodukcja do druku; dziewięciokrotna różnica decyduje o tym,
    czy kolejka decyzji działa na tablecie przez sieć, czy się wlecze.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - PyMuPDF jest twardą zależnością
        return None
    try:
        with pymupdf.open(path) as document:
            if document.page_count == 0:
                return None
            index = min(max(page, 1), document.page_count) - 1
            target = document.load_page(index)
            zoom = width / max(target.rect.width, 1)
            pixmap = target.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return bytes(pixmap.tobytes("jpeg", jpg_quality=PAGE_QUALITY))
    except Exception:
        # Uszkodzony albo zaszyfrowany PDF nie jest awarią narzędzia — podgląd
        # ma wtedy nie pokazać nic, a decyzja i tak należy do człowieka.
        return None


def page_count(path: Path) -> int | None:
    """Liczba stron PDF albo ``None``, gdy pliku nie da się otworzyć."""
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            return int(document.page_count)
    except Exception:
        return None


def render_image(source: Path, width: int) -> bytes | None:
    """Skaluje obraz do zadanej szerokości i zwraca JPEG.

    Używane, gdy widok potrzebuje INNEGO rozmiaru niż miniatura z cache: siatka
    klastra prosi o coś małego, a porównanie dwóch zdjęć obok siebie o coś, na czym
    faktycznie widać różnicę. Nie cache'ujemy tego — cache ma jeden, ustalony rozmiar
    i nie chcemy zaśmiecać go każdą szerokością, jakiej zażyczy sobie przeglądarka.
    """
    try:
        from PIL import Image

        with Image.open(source) as image:
            image = image.convert("RGB")
            if image.width > width:
                image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=THUMBNAIL_QUALITY)
            return buffer.getvalue()
    except Exception:
        return None


def thumbnail(paths: config.Paths, sha256: str, source: Path | None) -> Path | None:
    """Ścieżka miniatury obrazu w ``work/thumbnails``; liczy ją raz, potem czyta z cache."""
    cache = paths.work_thumbnails / f"{sha256}.jpg"
    if cache.is_file():
        return cache
    if source is None or not source.is_file():
        return None
    try:
        from PIL import Image

        cache.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail(THUMBNAIL_SIZE)
            image.save(cache, "JPEG", quality=THUMBNAIL_QUALITY)
    except Exception:
        return None
    return cache
