"""Czyste funkcje hashujące: pliki i trzy warstwy podpisu katalogu (sekcja 5 architektury).

Wszystkie funkcje katalogowe sortują wejście, więc kolejność podania elementów
nigdy nie wpływa na wynik.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Zwraca sha256 (hex) zawartości pliku, czytając go porcjami po ``chunk`` bajtów."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hash(pairs: Iterable[tuple[str, str]]) -> str:
    """Hash dokładnej zawartości katalogu: sha256 z posortowanych par (relpath, sha256).

    Serializacja: ``f"{relpath}\\0{sha256}\\n"`` w UTF-8. Identyczny tree_hash =
    ten sam zestaw plików pod tymi samymi nazwami (reguła twarda nr 4).
    """
    digest = hashlib.sha256()
    for relpath, sha256 in sorted(pairs):
        digest.update(f"{relpath}\0{sha256}\n".encode("utf-8"))
    return digest.hexdigest()


def content_set_hash(hashes: Iterable[str]) -> str:
    """Hash multizbioru treści katalogu: sha256 z posortowanych sha256 (duplikaty zachowane).

    Serializacja: ``sha + "\\n"``. Ignoruje nazwy i układ plików — wykrywa te same
    treści przełożone do innych podkatalogów.
    """
    digest = hashlib.sha256()
    for sha256 in sorted(hashes):
        digest.update(f"{sha256}\n".encode("utf-8"))
    return digest.hexdigest()


def structural_signature(entries: Iterable[tuple[str, int, int]]) -> str:
    """Tani podpis struktury katalogu: sha256 z posortowanych (relpath, size_bytes, mtime_ns).

    Serializacja: ``f"{relpath}\\0{size}\\0{mtime_ns}\\n"``. Liczony bez czytania
    zawartości plików — służy do szybkiego odsiewania par przed hashowaniem.
    """
    digest = hashlib.sha256()
    for relpath, size_bytes, mtime_ns in sorted(entries):
        digest.update(f"{relpath}\0{size_bytes}\0{mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()
