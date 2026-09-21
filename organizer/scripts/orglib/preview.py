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

import sqlite3
from pathlib import Path
from typing import Iterable

from . import config

#: Rozmiar miniatury (dłuższy bok) i jakość JPEG — wspólne z raportem B9.
THUMBNAIL_SIZE: tuple[int, int] = (320, 320)
THUMBNAIL_QUALITY: int = 72

#: Szerokość renderowanej strony PDF w pikselach. Tyle wystarcza, żeby z ekranu
#: rozpoznać, co to za dokument; więcej kosztuje tylko czas i pamięć.
PAGE_WIDTH: int = 1000

#: Rodzaje treści, dla których umiemy pokazać obraz.
IMAGE_KINDS = frozenset({"image"})
PAGE_KINDS = frozenset({"pdf"})


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
    """Renderuje stronę PDF do PNG (PyMuPDF). ``None``, gdy pliku nie da się otworzyć."""
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
            return bytes(pixmap.tobytes("png"))
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
