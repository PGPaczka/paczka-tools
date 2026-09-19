"""Połączenie z operacyjnym indeksem — w fazie S0 wyłącznie do odczytu.

Baza jest współdzielona z CLI (``studio/AGENTS.md``, reguła 8), więc studio
otwiera ją tak samo jak ``status_report``: URI z ``mode=ro`` plus
``PRAGMA query_only``. Dwie bariery zamiast jednej, bo to jedyne miejsce, w którym
aplikacja HTTP dotyka pliku, który potok uważa za źródło prawdy.

Połączenie jest zakładane NA ŻĄDANIE i zamykane po odpowiedzi. FastAPI wykonuje
synchroniczną zależność i synchroniczny endpoint w puli wątków — i NIE gwarantuje,
że będzie to ten sam wątek. Dlatego ``check_same_thread=False``: bez tego pierwsze
żądanie do `/api/items` na żywym serwerze kończyło się 500 („SQLite objects created
in a thread can only be used in that same thread”), a `TestClient` tego nie
pokazywał, bo obsługiwał oba kroki w jednym wątku. Bezpieczne, bo każde żądanie ma
własne połączenie i nikt nie używa go równolegle: zależność zakłada je przed
wywołaniem endpointu i zamyka po odpowiedzi.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from orglib import db


class SchemaMismatch(RuntimeError):
    """Baza ma inną wersję schematu, niż obsługuje ten kod."""


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Otwiera indeks w trybie tylko do odczytu (``mode=ro`` + ``query_only``).

    ``mode=ro`` wymaga istniejącego pliku — brak bazy podnosi ``FileNotFoundError``
    z czytelnym komunikatem, a nie ``sqlite3.OperationalError: unable to open``.
    """
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"brak bazy: {path} — najpierw wykonaj first-pass")
    conn = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def check_schema(conn: sqlite3.Connection) -> int:
    """Sprawdza ``schema_version`` i zwraca ją; inna wersja to :class:`SchemaMismatch`.

    Wołane przy starcie serwera, zanim ktokolwiek zobaczy jakąkolwiek liczbę:
    baza po migracji (albo sprzed niej) potrafi odpowiadać na część zapytań i
    milczeć o brakujących kolumnach, a to najgorszy możliwy rodzaj pomyłki
    w narzędziu, na którym opiera się decyzja o `apply`.
    """
    version = db.current_schema_version(conn)
    if version != db.SCHEMA_VERSION:
        raise SchemaMismatch(
            f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION} "
            "— uruchom `just db-init` na tej bazie albo wskaż inną"
        )
    return version


def connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Zależność FastAPI: połączenie ro na czas jednego żądania."""
    conn = open_readonly(db_path)
    try:
        yield conn
    finally:
        conn.close()
