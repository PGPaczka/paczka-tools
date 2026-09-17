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
