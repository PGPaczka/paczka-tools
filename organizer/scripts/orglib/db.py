"""Warstwa dostępu do SQLite: połączenie, schemat, UPSERT-y i maszyna stanów pliku.

Baza (20_WORK/organizer.sqlite) jest operacyjnym źródłem prawdy; jest odtwarzalna,
więc poza gitem. Jedyny prymityw zapisu to :func:`upsert` — reszta to cienkie
wrappery z właściwym kluczem konfliktu.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

#: Wersja DDL w schema.sql. Baza z wyższą wersją jest odrzucana.
SCHEMA_VERSION = 1

#: Statusy pliku w kolejności maszyny stanów (przejścia tylko do przodu).
FILE_STATUSES: tuple[str, ...] = (
    "discovered",
    "hashed",
    "extracted",
    "classified",
    "planned",
    "applied",
    "verified",
)

#: Status awaryjny — osiągalny z każdego stanu, opuszczalny tylko przez reset_error().
ERROR_STATUS = "error"

#: Tabele danych (bez schema_version) — używane w raportach liczności.
TABLES: tuple[str, ...] = (
    "source_packages",
    "folders",
    "files",
    "content",
    "classifications",
    "relations",
    "manual_decisions",
    "plan_items",
    "applied",
)

#: Etap potoku -> status plików, które ten etap ma jeszcze do przerobienia.
STAGE_PENDING_STATUS: dict[str, str] = {
    "hash": "discovered",
    "extract": "hashed",
    "classify": "extracted",
    "plan": "classified",
    "apply": "planned",
    "verify": "applied",
}

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def now_iso() -> str:
    """Bieżący czas jako ISO-8601 UTC z sufiksem 'Z' (konwencja czasu w całej bazie)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mtime_seconds(mtime_ns: int) -> int:
    """Czas modyfikacji w PEŁNYCH sekundach (w dół).

    Cały potok — ``files.modified_date``, podpis strukturalny i kontrola
    niezmienności źródeł — pracuje na tej samej, sekundowej rozdzielczości.
    Inaczej dysk o gorszej granulacji mtime (FAT/exFAT, kopie przez sieć) przy
    każdym porównaniu udawałby zmianę.
    """
    return mtime_ns // 1_000_000_000


def mtime_iso(seconds: int) -> str:
    """ISO-8601 UTC 'Z' z czasu modyfikacji w sekundach; format jak :func:`now_iso`."""
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def folder_path_for(source_package: str, source_relative_path: str) -> str:
    """Wylicza ``files.folder_path`` z paczki i ścieżki pliku względem katalogu paczki.

    Reguła: ``source_package + '/' + dirname(source_relative_path)``; dla pliku
    leżącego w korzeniu paczki zwraca samo ``source_package``.
    """
    if not source_package:
        raise ValueError("source_package nie może być puste")
    relative = str(source_relative_path).strip().lstrip("/")
    if not relative:
        raise ValueError("source_relative_path nie może być puste")
    parent = PurePosixPath(relative).parent
    return source_package if str(parent) == "." else f"{source_package}/{parent}"


def connect(db_path: Path, *, init: bool = True) -> sqlite3.Connection:
    """Otwiera bazę (tworząc katalog nadrzędny) z PRAGMA-mi projektu; domyślnie zakłada schemat."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    if init:
        try:
            init_schema(conn)
        except Exception:
            conn.close()
            raise
    return conn


def current_schema_version(conn: sqlite3.Connection) -> int | None:
    """Zwraca najwyższą zapisaną wersję schematu albo ``None`` (pusta/świeża baza)."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if exists is None:
        return None
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return None if row["v"] is None else int(row["v"])


def init_schema(conn: sqlite3.Connection) -> None:
    """Wykonuje schema.sql i zapisuje wersję schematu. Idempotentne.

    Wersję sprawdza PRZED wykonaniem DDL: baza nowsza niż :data:`SCHEMA_VERSION`
    podnosi ``RuntimeError`` i zostaje nietknięta (starszy kod nie dopisuje jej
    swoich tabel).
    """
    current = current_schema_version(conn)
    if current is not None and current > SCHEMA_VERSION:
        raise RuntimeError(
            f"baza ma schema_version={current}, a ten kod obsługuje {SCHEMA_VERSION} "
            "— zaktualizuj organizer albo użyj innej bazy"
        )
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn:
        conn.executescript(ddl)
        if current is None or current < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, now_iso()),
            )


def _check_ident(name: str) -> str:
    """Waliduje nazwę tabeli/kolumny (trafia wprost do SQL, więc nie może być dowolna)."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"niedozwolona nazwa tabeli/kolumny: {name!r}")
    return name


def _upsert_sql(table: str, columns: Sequence[str], conflict: Sequence[str]) -> str:
    """Buduje INSERT ... ON CONFLICT(...) DO UPDATE dla podanych kolumn."""
    _check_ident(table)
    if not columns:
        raise ValueError(f"upsert do {table}: pusty wiersz")
    for name in (*columns, *conflict):
        _check_ident(name)
    missing = [c for c in conflict if c not in columns]
    if missing:
        raise ValueError(f"upsert do {table}: wiersz nie zawiera kolumn konfliktu {missing}")

    col_list = ", ".join(columns)
    placeholders = ", ".join("?" * len(columns))
    conflict_list = ", ".join(conflict)
    updatable = [c for c in columns if c not in conflict]
    if not updatable:
        tail = "DO NOTHING"
    else:
        tail = "DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in updatable)
    return (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_list}) {tail}"
    )


def upsert(
    conn: sqlite3.Connection, table: str, row: Mapping[str, Any], *, conflict: Sequence[str]
) -> None:
    """Wstawia lub aktualizuje wiersz po kluczu ``conflict``.

    Aktualizowane są WYŁĄCZNIE kolumny obecne w ``row`` — pominięcie kolumny
    zostawia jej dotychczasową wartość nietkniętą.
    """
    columns = list(row.keys())
    sql = _upsert_sql(table, columns, conflict)
    with conn:
        conn.execute(sql, [row[c] for c in columns])


def upsert_many(
    conn: sqlite3.Connection,
    table: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    conflict: Sequence[str],
) -> int:
    """Wsadowy UPSERT wielu wierszy w JEDNEJ transakcji; zwraca liczbę wierszy.

    Wiersze grupuje po ZBIORZE kolumn (nazwy sortowane, więc kolejność kluczy
    w słowniku nie mnoży grup); każda grupa = jedno ``executemany``. Wiersze
    o różnych kolumnach można mieszać — tak jak w :func:`upsert`, aktualizowane są
    wyłącznie kolumny obecne w danym wierszu. Cały wsad jest atomowy: błąd
    w dowolnym wierszu wycofuje całość (skan 50k plików nie może zostawić bazy
    w połowie zapisanej).
    """
    groups: dict[tuple[str, ...], list[list[Any]]] = {}
    count = 0
    for row in rows:
        columns = tuple(sorted(row.keys()))
        groups.setdefault(columns, []).append([row[c] for c in columns])
        count += 1
    if not groups:
        return 0
    # SQL budujemy PRZED transakcją: zła nazwa kolumny ma polecieć, zanim
    # cokolwiek zapiszemy.
    batches = [
        (_upsert_sql(table, columns, conflict), params) for columns, params in groups.items()
    ]
    with conn:
        for sql, params in batches:
            conn.executemany(sql, params)
    return count


def upsert_file(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT pliku po (source_package, source_relative_path).

    Gdy ``row`` nie zawiera ``status``, istniejący status zostaje nietknięty —
    ponowny scan nigdy nie cofa pliku do 'discovered'.
    """
    upsert(conn, "files", row, conflict=("source_package", "source_relative_path"))


def upsert_folder(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT katalogu po folder_path."""
    upsert(conn, "folders", row, conflict=("folder_path",))


def upsert_content(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT treści po sha256."""
    upsert(conn, "content", row, conflict=("sha256",))


def upsert_classification(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT decyzji klasyfikacyjnej po sha256."""
    upsert(conn, "classifications", row, conflict=("sha256",))


def upsert_relation(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT relacji po (source_sha256, target_sha256, relation_type)."""
    upsert(conn, "relations", row, conflict=("source_sha256", "target_sha256", "relation_type"))


def upsert_manual_decision(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT ręcznej decyzji po sha256."""
    upsert(conn, "manual_decisions", row, conflict=("sha256",))


def upsert_plan_item(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT pozycji planu po (sha256, target_relative_path)."""
    upsert(conn, "plan_items", row, conflict=("sha256", "target_relative_path"))


def record_applied(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """UPSERT wpisu audytowego apply po target_relative_path."""
    upsert(conn, "applied", row, conflict=("target_relative_path",))


def _file_status(conn: sqlite3.Connection, file_id: int) -> str:
    """Zwraca bieżący status pliku albo podnosi KeyError, gdy pliku nie ma."""
    row = conn.execute("SELECT status FROM files WHERE file_id = ?", (file_id,)).fetchone()
    if row is None:
        raise KeyError(f"brak pliku file_id={file_id}")
    return str(row["status"])


def advance_status(conn: sqlite3.Connection, file_id: int, new_status: str) -> None:
    """Przesuwa status pliku do przodu (o dowolną liczbę kroków) albo na 'error'.

    Cofnięcie i ustawienie tego samego statusu to ``ValueError``; wyjście ze stanu
    'error' możliwe wyłącznie przez :func:`reset_error`.
    """
    current = _file_status(conn, file_id)
    if new_status == current:
        raise ValueError(
            f"plik {file_id}: status już wynosi {current!r} — przejście do tego samego statusu "
            "jest niedozwolone"
        )
    if new_status != ERROR_STATUS:
        if new_status not in FILE_STATUSES:
            raise ValueError(f"nieznany status {new_status!r}; dozwolone: {FILE_STATUSES + (ERROR_STATUS,)}")
        if current == ERROR_STATUS:
            raise ValueError(
                f"plik {file_id} jest w stanie 'error' — użyj reset_error(), nie advance_status()"
            )
        if FILE_STATUSES.index(new_status) < FILE_STATUSES.index(current):
            raise ValueError(
                f"plik {file_id}: niedozwolone cofnięcie statusu {current!r} -> {new_status!r}"
            )
    with conn:
        conn.execute("UPDATE files SET status = ? WHERE file_id = ?", (new_status, file_id))


def reset_error(conn: sqlite3.Connection, file_id: int, to_status: str) -> None:
    """Wyprowadza plik ze stanu 'error' na wskazany status potoku (i czyści error_message)."""
    current = _file_status(conn, file_id)
    if current != ERROR_STATUS:
        raise ValueError(f"plik {file_id} nie jest w stanie 'error' (jest {current!r})")
    if to_status not in FILE_STATUSES:
        raise ValueError(f"nieznany status docelowy {to_status!r}; dozwolone: {FILE_STATUSES}")
    with conn:
        conn.execute(
            "UPDATE files SET status = ?, error_message = NULL WHERE file_id = ?",
            (to_status, file_id),
        )


def files_pending(
    conn: sqlite3.Connection,
    stage: str,
    *,
    source_package: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Zwraca pliki czekające na dany etap (w statusie poprzedzającym ten etap).

    Poddrzewa katalogów oznaczonych jako ``duplicate_of`` są pomijane (nie robimy
    drugi raz extract/OCR/classify tej samej treści). Wyjątkiem jest etap 'hash' —
    bez hashy żaden katalog nie może zostać uznany za duplikat.
    """
    if stage not in STAGE_PENDING_STATUS:
        raise ValueError(
            f"nieznany etap {stage!r}; dozwolone: {sorted(STAGE_PENDING_STATUS)}"
        )
    params: list[Any] = [STAGE_PENDING_STATUS[stage]]
    sql = "SELECT f.* FROM files AS f WHERE f.status = ?"
    if stage != "hash":
        # Porównanie prefiksu przez substr(), nie LIKE: nazwy katalogów w tym
        # projekcie roją się od '_', który w LIKE jest wieloznacznikiem.
        sql += (
            " AND NOT EXISTS ("
            "SELECT 1 FROM folders AS d WHERE d.duplicate_of IS NOT NULL AND ("
            "f.folder_path = d.folder_path"
            " OR substr(f.folder_path, 1, length(d.folder_path) + 1) = d.folder_path || '/'"
            "))"
        )
    if source_package is not None:
        sql += " AND f.source_package = ?"
        params.append(source_package)
    sql += " ORDER BY f.file_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def export_manual_decisions(conn: sqlite3.Connection, path: Path) -> int:
    """Zapisuje manual_decisions do JSONL (sortowane po sha256) i zwraca liczbę wierszy."""
    rows = conn.execute("SELECT * FROM manual_decisions ORDER BY sha256").fetchall()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def import_manual_decisions(conn: sqlite3.Connection, path: Path) -> int:
    """Wczytuje JSONL ręcznych decyzji (UPSERT po sha256) i zwraca liczbę wierszy."""
    count = 0
    with conn:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            columns = list(row.keys())
            conn.execute(
                _upsert_sql("manual_decisions", columns, ("sha256",)),
                [row[c] for c in columns],
            )
            count += 1
    return count


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Liczność wierszy w każdej tabeli danych."""
    return {
        table: int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
        for table in TABLES
    }


def file_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Liczność plików wg statusu (wszystkie znane statusy, także zerowe)."""
    counts = {status: 0 for status in (*FILE_STATUSES, ERROR_STATUS)}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status"):
        counts[str(row["status"])] = int(row["n"])
    return counts
