"""S4.1: odnajdywanie się studia i grafu po tym samym identyfikatorze treści.

Graf synapse i studio patrzą na ten sam indeks, ale mówią o nim innym językiem:
studio zna `sha256`, graf zna `id` notatki w vaulcie. Ten moduł tłumaczy jedno na
drugie — **bez zgadywania**: gdy tłumaczenie nie jest jednoznaczne, zwraca listę
kandydatów i decyzję zostawia człowiekowi.

Podstawą jest kontrakt id z ``synapse_vault``: nazwa pliku notatki kończy się
``sha256[:ID_SHA_PREFIX]``. Mapę budujemy z NAZW PLIKÓW vaulta (bez czytania ich
treści), więc jest dokładnie tym, z czego powstał graf, a koszt to jedno
przejście po katalogu.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .synapse_vault import ID_SHA_PREFIX

#: Id notatki pliku kończy się skrótem sha256 (hex). Nic innego nas tu nie interesuje:
#: notatki semestru i przedmiotu nie odpowiadają żadnej pojedynczej treści.
_SHA_SUFFIX = re.compile(rf"-([0-9a-f]{{{ID_SHA_PREFIX}}})$")


def sha_prefix_of_node(node_id: str) -> str | None:
    """Skrót sha z id notatki albo ``None``, gdy to węzeł semestru/przedmiotu."""
    match = _SHA_SUFFIX.search(str(node_id).strip())
    return match.group(1) if match else None


def scan_vault(vault_root: Path) -> dict[str, list[str]]:
    """Mapa ``sha256[:8]`` → lista id notatek, zbudowana z nazw plików vaulta."""
    index: dict[str, list[str]] = {}
    root = Path(vault_root)
    if not root.is_dir():
        return index
    for path in root.rglob("*.md"):
        prefix = sha_prefix_of_node(path.stem)
        if prefix is not None:
            index.setdefault(prefix, []).append(path.stem)
    for ids in index.values():
        ids.sort()
    return index


def nodes_for_sha(index: Mapping[str, list[str]], sha256: str) -> list[str]:
    """Id notatek odpowiadających treści (zwykle jedna; pusto = treści nie ma w vaulcie)."""
    return list(index.get(str(sha256)[:ID_SHA_PREFIX], ()))


def shas_for_node(conn: sqlite3.Connection, node_id: str) -> list[str]:
    """Treści pasujące do id węzła — po skrócie sha, prosto z indeksu.

    Zwykle dokładnie jedna. Kilka oznacza kolizję skrótu w bazie i wtedy wołający
    ma pokazać wybór, a nie wybrać za człowieka.
    """
    prefix = sha_prefix_of_node(node_id)
    if prefix is None:
        return []
    rows = conn.execute(
        "SELECT sha256 FROM content WHERE sha256 >= ? AND sha256 < ? ORDER BY sha256",
        (prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)),
    ).fetchall()
    return [str(row["sha256"]) for row in rows]


def deep_link(node_id: str) -> str:
    """Adres grafu z zaznaczonym węzłem — viewer czyta id z fragmentu URL-a."""
    return f"/graf#{node_id}"
