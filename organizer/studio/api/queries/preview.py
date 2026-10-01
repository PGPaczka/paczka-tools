"""Podgląd jednej treści: głowa tekstu, obraz i rodzaj podglądu.

Czytamy WYŁĄCZNIE plik wskazany przez indeks i tylko przez helpery
``orglib.preview`` — one pilnują containmentu wobec katalogów ze configu.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from orglib import config, preview as preview_lib

from ._common import PREVIEW_TEXT_LIMIT


def preview(
    conn: sqlite3.Connection,
    sha256: str,
    paths: config.Paths,
    *,
    limit: int = PREVIEW_TEXT_LIMIT,
) -> dict[str, Any] | None:
    """Co da się pokazać o treści: głowa tekstu, obraz i rodzaj podglądu.

    Widok pyta RAZ i wie, co narysować (``preview_kind``: ``page`` dla PDF,
    ``image`` dla obrazu, ``text`` gdy jest sama głowa tekstu, ``none`` gdy nie ma
    nic). Bez tego front zgadywałby po rozszerzeniu — czyli liczyłby regułę,
    której nie policzył backend.
    """
    row = conn.execute(
        "SELECT sha256, content_kind, extracted_text_path, ocr_done FROM content WHERE sha256 = ?",
        (sha256,),
    ).fetchone()
    if row is None:
        return None

    kind = str(row["content_kind"] or "")
    head = preview_lib.text_head(paths, row["extracted_text_path"], limit)
    copies = preview_lib.source_copies(conn, sha256)
    source = preview_lib.first_existing_copy(paths, copies)
    # Materiał bez kopii w źródłach, ale obecny w paczce: podgląd bierze go stamtąd.
    if source is None:
        source = preview_lib.package_copy(paths, conn, sha256)

    has_image = source is not None and (kind in preview_lib.PAGE_KINDS or kind in preview_lib.IMAGE_KINDS)
    # Bez wyekstrahowanego tekstu sięgamy do samego pliku, o ile to tekst: extract
    # nie dotknął ani jednej treści `other` i ponad dwustu `text`/`code`, a przy
    # takiej pozycji panel pokazywał pustkę — nie dało się stwierdzić, czym ona jest.
    if head is None and not has_image and source is not None and kind in preview_lib.SOURCE_TEXT_KINDS:
        head = preview_lib.source_text_head(source, limit)

    if has_image and kind in preview_lib.PAGE_KINDS:
        preview_kind = "page"
    elif has_image:
        preview_kind = "image"
    elif head:
        preview_kind = "text"
    else:
        preview_kind = "none"

    return {
        "sha256": sha256,
        "content_kind": row["content_kind"],
        "text_head": head,
        "has_text": head is not None,
        # Widok ma pokazać, że to WYCINEK: bez tego osiem linijek wygląda jak cały plik.
        "text_truncated": bool(head is not None and len(head) >= limit),
        "text_language": preview_lib.text_language(source.name, kind) if source is not None else None,
        "has_image": has_image,
        "preview_kind": preview_kind,
        "has_thumbnail": (paths.work_thumbnails / f"{sha256}.jpg").is_file(),
        "pages": preview_lib.page_count(source) if (source and kind in preview_lib.PAGE_KINDS) else None,
        "copies": len(copies),
        # Treść z samej paczki nie ma kopii w źródłach — pokazujemy wtedy, skąd
        # NAPRAWDĘ wzięliśmy podgląd, zamiast wywracać się na pustej liście.
        "source_path": f"{copies[0][0]}/{copies[0][1]}" if copies else (
            None if source is None else str(source.relative_to(paths.target_repo))
        ),
        "ocr_done": bool(row["ocr_done"]),
    }


def preview_image(
    conn: sqlite3.Connection,
    sha256: str,
    paths: config.Paths,
    *,
    page: int = 1,
    width: int | None = None,
) -> tuple[bytes, str] | None:
    """Bajty obrazu podglądu i jego typ MIME; ``None``, gdy nie ma czego pokazać.

    PDF renderuje się do PNG, obraz idzie jako miniatura JPEG z ``work/thumbnails``
    (ten sam cache co raport B9). Czytamy WYŁĄCZNIE plik wskazany przez indeks
    i tylko przez helper containmentu.
    """
    row = conn.execute(
        "SELECT content_kind FROM content WHERE sha256 = ?", (sha256,)
    ).fetchone()
    if row is None:
        return None
    kind = str(row["content_kind"] or "")
    source = preview_lib.first_existing_copy(paths, preview_lib.source_copies(conn, sha256))
    if source is None:
        source = preview_lib.package_copy(paths, conn, sha256)
    if source is None:
        return None
    if kind in preview_lib.PAGE_KINDS:
        payload = preview_lib.render_pdf_page(
            source, page=page, width=width or preview_lib.PAGE_WIDTH
        )
        return (payload, "image/jpeg") if payload else None
    if kind in preview_lib.IMAGE_KINDS:
        # Domyślna szerokość idzie z cache (jedna miniatura na treść, liczona raz);
        # każda inna jest renderowana na bieżąco, bo cache ma ustalony rozmiar.
        if width is None or width == preview_lib.THUMBNAIL_SIZE[0]:
            cached = preview_lib.thumbnail(paths, sha256, source)
            if cached is None:
                return None
            try:
                return cached.read_bytes(), "image/jpeg"
            except OSError:
                return None
        payload = preview_lib.render_image(source, width)
        return (payload, "image/jpeg") if payload else None
    return None
