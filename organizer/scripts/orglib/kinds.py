"""Mapowanie rozszerzenia pliku na ``content.content_kind`` ze schema.sql.

Jedno miejsce prawdy o tym, jakie rozszerzenie to jaki rodzaj treści — reszta
potoku (hash, extract, classify) pyta wyłącznie o :func:`content_kind_for`.
"""

from __future__ import annotations

#: Rozszerzenie (bez kropki, małe litery) -> content_kind. Grupa 'media' MUSI
#: być zgodna z ``config/syntax.yaml: media.extensions`` — to jest sprawdzane
#: testem, nie duplikowane ręcznie z YAML (media nie wchodzą do paczki).
_EXTENSION_TO_KIND: dict[str, str] = {
    # pdf
    "pdf": "pdf",
    # docx
    "doc": "docx",
    "docx": "docx",
    "odt": "docx",
    "rtf": "docx",
    # pptx
    "ppt": "pptx",
    "pptx": "pptx",
    "odp": "pptx",
    # xlsx
    "xls": "xlsx",
    "xlsx": "xlsx",
    "ods": "xlsx",
    "csv": "xlsx",
    # image
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "bmp": "image",
    "tif": "image",
    "tiff": "image",
    "webp": "image",
    "heic": "image",
    "svg": "image",
    # text
    "txt": "text",
    "md": "text",
    "tex": "text",
    "typ": "text",
    "html": "text",
    "htm": "text",
    "json": "text",
    "yaml": "text",
    "yml": "text",
    "xml": "text",
    "log": "text",
    # code
    "c": "code",
    "cpp": "code",
    "cc": "code",
    "h": "code",
    "hpp": "code",
    "py": "code",
    "java": "code",
    "js": "code",
    "ts": "code",
    "cs": "code",
    "sql": "code",
    "sh": "code",
    "m": "code",
    "r": "code",
    "go": "code",
    "rs": "code",
    "kt": "code",
    "ipynb": "code",
    "asm": "code",
    "s": "code",
    "v": "code",
    "vhd": "code",
    "vhdl": "code",
    # archive
    "zip": "archive",
    "rar": "archive",
    "7z": "archive",
    "tar": "archive",
    "gz": "archive",
    "bz2": "archive",
    "xz": "archive",
    "tgz": "archive",
    # media (musi być zgodne z config/syntax.yaml: media.extensions)
    "mp4": "media",
    "mov": "media",
    "avi": "media",
    "mkv": "media",
    "webm": "media",
    "wav": "media",
    "flac": "media",
    "mp3": "media",
    "m4a": "media",
}

#: Rodzaj treści, gdy rozszerzenie jest puste/nieznane.
DEFAULT_KIND: str = "other"


def content_kind_for(extension: str | None) -> str:
    """Zwraca ``content_kind`` dla rozszerzenia (bez kropki, wielkość liter obojętna).

    Brak rozszerzenia (``None``/pusty string) albo rozszerzenie spoza mapy
    zwraca :data:`DEFAULT_KIND` ('other') — nigdy nie podnosi wyjątku, bo
    trafia tu każdy plik ze skanu, także taki bez rozszerzenia.
    """
    if not extension:
        return DEFAULT_KIND
    return _EXTENSION_TO_KIND.get(extension.strip().lower(), DEFAULT_KIND)
