"""Testy hashy: niezależność od kolejności wejścia i czułość na zmianę treści."""

from __future__ import annotations

import hashlib
from pathlib import Path

from orglib import hashes

PAIRS = [("a/x.pdf", "11" * 32), ("b/y.pdf", "22" * 32), ("c/z.pdf", "33" * 32)]


def test_tree_hash_ignores_input_order() -> None:
    assert hashes.tree_hash(PAIRS) == hashes.tree_hash(reversed(PAIRS))


def test_tree_hash_changes_when_one_sha_changes() -> None:
    changed = [(PAIRS[0][0], "44" * 32), *PAIRS[1:]]

    assert hashes.tree_hash(PAIRS) != hashes.tree_hash(changed)


def test_tree_hash_changes_when_file_is_renamed() -> None:
    renamed = [("a/inna.pdf", PAIRS[0][1]), *PAIRS[1:]]

    assert hashes.tree_hash(PAIRS) != hashes.tree_hash(renamed)


def test_content_set_hash_ignores_input_order_and_names() -> None:
    shas = [pair[1] for pair in PAIRS]

    assert hashes.content_set_hash(shas) == hashes.content_set_hash(reversed(shas))


def test_content_set_hash_is_a_multiset() -> None:
    once = hashes.content_set_hash(["11" * 32])
    twice = hashes.content_set_hash(["11" * 32, "11" * 32])

    assert once != twice


def test_structural_signature_ignores_input_order() -> None:
    entries = [("a/x.pdf", 10, 1), ("b/y.pdf", 20, 2)]

    assert hashes.structural_signature(entries) == hashes.structural_signature(reversed(entries))


def test_structural_signature_reacts_to_size_and_mtime() -> None:
    base = [("a/x.pdf", 10, 1)]

    assert hashes.structural_signature(base) != hashes.structural_signature([("a/x.pdf", 11, 1)])
    assert hashes.structural_signature(base) != hashes.structural_signature([("a/x.pdf", 10, 2)])


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "plik.bin"
    payload = b"zazolc gesla jazn" * 10_000
    path.write_bytes(payload)

    assert hashes.sha256_file(path) == hashlib.sha256(payload).hexdigest()
    assert hashes.sha256_file(path, chunk=7) == hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
# Wektory złote: kontrakt SERIALIZACJI, nie tylko spójność funkcji ze sobą
# --------------------------------------------------------------------------- #
#
# Pozostałe testy w tym pliku porównują wynik funkcji z wynikiem tej samej
# funkcji (kolejność bez znaczenia, zmiana treści zmienia hash). Audyt 2026-09-18
# pokazał, że to za mało: zamiana separatorów `\0`/`\n` na `|`/`;` we wszystkich
# trzech funkcjach przechodziła CAŁY zestaw testów repo na zielono. A to twardy
# kontrakt — `folders.tree_hash` leży w bazie, więc zmiana formatu unieważnia
# istniejący indeks po cichu, a separator bez NUL dopuszcza kolizje ścieżek
# (`a/b` + `c` kontra `a` + `b/c`).
#
# Wartości poniżej wyprowadzono RĘCZNIE z formatu opisanego w docstringach
# `orglib/hashes.py`, nie z wywołania tych funkcji.

#: sha256 z b"a.pdf\0<64×'1'>\na/b.pdf\0<64×'2'>\n"
GOLDEN_TREE_HASH = "36be8bd8ffe56cdd8fe897e68d5f8c29b5ec7fcde1c4116eb7005c95966ad51d"

#: sha256 z b"<64×'1'>\n<64×'2'>\n"
GOLDEN_CONTENT_SET_HASH = "f5404fd407075eb9ef6261cbfc12da4cbe2906c3a04dcffd2be12daa6a475c89"

#: sha256 z b"a.pdf\0 0\0 1700000000\n sub/b.pdf\0 10\0 1700000001\n" (bez spacji)
GOLDEN_STRUCTURAL_SIGNATURE = "61706b743165a9521faa6da122601fbca7b402fdbcb432035d235d54779619a5"

SHA_A = "1" * 64
SHA_B = "2" * 64


def test_tree_hash_matches_golden_vector() -> None:
    """Format `relpath\\0sha\\n` jest kontraktem zapisanym w bazie, nie szczegółem."""
    assert hashes.tree_hash([("a.pdf", SHA_A), ("sub/b.pdf", SHA_B)]) == GOLDEN_TREE_HASH


def test_content_set_hash_matches_golden_vector() -> None:
    """Format `sha\\n` — multizbiór treści bez nazw plików."""
    assert hashes.content_set_hash([SHA_A, SHA_B]) == GOLDEN_CONTENT_SET_HASH


def test_structural_signature_matches_golden_vector() -> None:
    """Format `relpath\\0size\\0mtime\\n`; mtime w SEKUNDACH (patrz docstring)."""
    entries = [("a.pdf", 0, 1_700_000_000), ("sub/b.pdf", 10, 1_700_000_001)]
    assert hashes.structural_signature(entries) == GOLDEN_STRUCTURAL_SIGNATURE


def test_separator_prevents_path_collision() -> None:
    """NUL jako separator jest po to, by dwa różne drzewa nie dały tego samego hasha.

    Bez znaku, którego nie ma w nazwach plików, para (`a/b`, `c`) i (`a`, `b/c`)
    skleiłaby się do identycznego strumienia bajtów.
    """
    first = hashes.tree_hash([("a/b", SHA_A), ("c", SHA_B)])
    second = hashes.tree_hash([("a", SHA_A), ("b/c", SHA_B)])
    assert first != second
