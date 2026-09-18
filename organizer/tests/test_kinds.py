"""Testy mapowania rozszerzenie -> content_kind."""

from __future__ import annotations

from orglib import config, kinds

# (rozszerzenie, oczekiwany content_kind) — po jednym reprezentancie na grupę.
GROUP_SAMPLES = [
    ("pdf", "pdf"),
    ("doc", "docx"),
    ("docx", "docx"),
    ("odt", "docx"),
    ("rtf", "docx"),
    ("ppt", "pptx"),
    ("pptx", "pptx"),
    ("pps", "pptx"),
    ("ppsx", "pptx"),
    ("odp", "pptx"),
    ("xls", "xlsx"),
    ("xlsx", "xlsx"),
    ("xlsm", "xlsx"),
    ("ods", "xlsx"),
    ("csv", "xlsx"),
    ("png", "image"),
    ("jpg", "image"),
    ("jpeg", "image"),
    ("gif", "image"),
    ("bmp", "image"),
    ("tif", "image"),
    ("tiff", "image"),
    ("webp", "image"),
    ("heic", "image"),
    ("jfif", "image"),
    ("svg", "image"),
    ("txt", "text"),
    ("md", "text"),
    ("tex", "text"),
    ("typ", "text"),
    ("html", "text"),
    ("htm", "text"),
    ("json", "text"),
    ("yaml", "text"),
    ("yml", "text"),
    ("xml", "text"),
    ("log", "text"),
    ("c", "code"),
    ("cpp", "code"),
    ("cc", "code"),
    ("h", "code"),
    ("hpp", "code"),
    ("py", "code"),
    ("java", "code"),
    ("js", "code"),
    ("ts", "code"),
    ("cs", "code"),
    ("sql", "code"),
    ("sh", "code"),
    ("m", "code"),
    ("r", "code"),
    ("go", "code"),
    ("rs", "code"),
    ("kt", "code"),
    ("ipynb", "code"),
    ("asm", "code"),
    ("s", "code"),
    ("v", "code"),
    ("vhd", "code"),
    ("vhdl", "code"),
    ("hs", "code"),
    ("zip", "archive"),
    ("rar", "archive"),
    ("7z", "archive"),
    ("tar", "archive"),
    ("gz", "archive"),
    ("bz2", "archive"),
    ("xz", "archive"),
    ("tgz", "archive"),
    ("mp4", "media"),
    ("mov", "media"),
    ("avi", "media"),
    ("mkv", "media"),
    ("webm", "media"),
    ("wav", "media"),
    ("flac", "media"),
    ("mp3", "media"),
    ("m4a", "media"),
]


def test_group_samples_map_to_expected_kind() -> None:
    for extension, expected in GROUP_SAMPLES:
        assert kinds.content_kind_for(extension) == expected


def test_uppercase_extension_is_lowercased() -> None:
    assert kinds.content_kind_for("PDF") == "pdf"
    assert kinds.content_kind_for("Mp4") == "media"


def test_none_and_empty_extension_is_other() -> None:
    assert kinds.content_kind_for(None) == "other"
    assert kinds.content_kind_for("") == "other"


def test_unknown_extension_is_other() -> None:
    assert kinds.content_kind_for("nieznane_cos") == "other"


def test_media_group_matches_syntax_yaml() -> None:
    syntax = config.load_yaml("syntax")
    media_extensions = {str(ext).lower() for ext in syntax["media"]["extensions"]}
    kinds_media = {ext for ext, kind in kinds._EXTENSION_TO_KIND.items() if kind == "media"}

    assert kinds_media == media_extensions
