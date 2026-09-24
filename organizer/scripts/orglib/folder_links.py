"""Ręczne powiązania katalogów między paczkami (schema_version 3).

Dedup katalogów (``folders.duplicate_of``) liczy się z ``tree_hash``, czyli z DOKŁADNEJ
równości poddrzewa — i jest wykorzystywany do wycinania poddrzew z potoku
(:func:`orglib.db.files_pending`). Człowiek widzi więcej niż równość bitów: że dwa katalogi
o różnej zawartości to ten sam materiał sprzed lat, w dwóch paczkach.

Dlatego powiązanie ręczne jest osobnym bytem i **niczego nie wycina**. Ma podpowiadać:
decyzja podjęta dla jednego katalogu jest propozycją dla drugiego, a raport przeglądu
pokazuje obie strony razem. Decyzja człowieka ma pierwszeństwo przed heurystyką, ale
nie kosztem cichego pominięcia plików obecnych tylko po jednej stronie.

Para jest NIEUPORZĄDKOWANA: zapisujemy ją zawsze posortowaną (``folder_a < folder_b``,
pilnuje tego CHECK w schemacie), więc „A≡B" i „B≡A" to jeden wiersz.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from orglib import config, db

#: Jak mocne jest twierdzenie człowieka. `duplicate` — ten sam materiał w dwóch paczkach;
#: `related` — te katalogi się ze sobą wiążą (np. ćwiczenia i ich rozwiązania).
LINK_KINDS = ("duplicate", "related")

#: Ślad w gicie. Baza bywa odtwarzana od zera (ponowne hashowanie źródeł), a praca
#: człowieka ma to przeżyć — dokładnie tak jak `manual_decisions.jsonl`.
EXPORT_PATH = config.ORGANIZER_ROOT / "reports" / "manual_folder_links.jsonl"


def _pair(folder_a: str, folder_b: str) -> tuple[str, str]:
    """Para w jednej, kanonicznej kolejności."""
    return (folder_a, folder_b) if folder_a < folder_b else (folder_b, folder_a)


def link(
    conn: sqlite3.Connection,
    folder_a: str,
    folder_b: str,
    *,
    kind: str = "duplicate",
    decided_by: str,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Zapisuje powiązanie dwóch katalogów. Ponowne wywołanie aktualizuje wiersz."""
    if kind not in LINK_KINDS:
        raise ValueError(f"nieznany rodzaj powiązania {kind!r} — dozwolone: {LINK_KINDS}")
    if folder_a == folder_b:
        raise ValueError("katalog nie może być powiązany sam ze sobą")

    for folder in (folder_a, folder_b):
        if conn.execute(
            "SELECT 1 FROM folders WHERE folder_path = ?", (folder,)
        ).fetchone() is None:
            # Literówka w ścieżce ma boleć od razu: martwy wiersz w tej tabeli byłby
            # powiązaniem, którego nikt nigdy nie zobaczy w żadnym widoku.
            raise LookupError(f"nie ma katalogu {folder!r} w indeksie")

    pierwszy, drugi = _pair(folder_a, folder_b)
    wiersz = {
        "folder_a": pierwszy,
        "folder_b": drugi,
        "kind": kind,
        "decided_by": decided_by,
        "decided_at": db.now_iso(),
        "note": note,
    }
    db.upsert(conn, "manual_folder_links", wiersz, conflict=("folder_a", "folder_b"))
    return wiersz


def unlink(conn: sqlite3.Connection, folder_a: str, folder_b: str) -> bool:
    """Usuwa powiązanie niezależnie od podanej kolejności. Zwraca, czy coś skasowano."""
    pierwszy, drugi = _pair(folder_a, folder_b)
    with conn:
        kursor = conn.execute(
            "DELETE FROM manual_folder_links WHERE folder_a = ? AND folder_b = ?",
            (pierwszy, drugi),
        )
    return kursor.rowcount > 0


def all_links(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Wszystkie powiązania, najnowsze najpierw."""
    return [dict(row) for row in conn.execute(
        "SELECT * FROM manual_folder_links ORDER BY decided_at DESC, folder_a"
    )]


def links_for(conn: sqlite3.Connection, folder: str) -> list[dict[str, Any]]:
    """Powiązania dotykające tego katalogu — z obu stron pary."""
    return [dict(row) for row in conn.execute(
        "SELECT * FROM manual_folder_links WHERE folder_a = ? OR folder_b = ? "
        "ORDER BY decided_at DESC",
        (folder, folder),
    )]


def partners(conn: sqlite3.Connection, folder: str) -> set[str]:
    """Katalogi powiązane z tym — bez względu na to, po której stronie pary stoją."""
    return {
        str(row["folder_b"] if row["folder_a"] == folder else row["folder_a"])
        for row in links_for(conn, folder)
    }


def export(conn: sqlite3.Connection, path: Optional[Path] = None) -> int:
    """Zapisuje powiązania do JSONL (posortowane) i zwraca liczbę wierszy."""
    target = Path(path) if path is not None else EXPORT_PATH
    rows = conn.execute(
        "SELECT * FROM manual_folder_links ORDER BY folder_a, folder_b"
    ).fetchall()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def import_links(conn: sqlite3.Connection, path: Optional[Path] = None) -> int:
    """Wczytuje powiązania z JSONL do bazy (UPSERT po parze). Zwraca liczbę wierszy.

    Idzie przez :func:`link`, więc obowiązują te same reguły co przy zapisie ze studia:
    nieznany katalog albo nieznany rodzaj zatrzymuje import zamiast wpisać śmieć.
    """
    source = Path(path) if path is not None else EXPORT_PATH
    count = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        link(
            conn,
            str(row["folder_a"]),
            str(row["folder_b"]),
            kind=str(row.get("kind") or "duplicate"),
            decided_by=str(row.get("decided_by") or "import"),
            note=row.get("note"),
        )
        count += 1
    conn.commit()
    return count
