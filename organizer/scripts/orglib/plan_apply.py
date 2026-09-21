"""B10: co plan zrobiłby z repo paczki i jak to wykonać — bez decyzji i bez kasowania.

Ten moduł zamienia linie planu na listę operacji na plikach i wykonuje je
pojedynczo. Decyzji nie podejmuje żadnych: co ma trafić do paczki, ustalił B3/B5/B7,
a czy wolno to wykonać — bramka B8 (``orglib.plan_gate``).

Zasady, których ten kod pilnuje, bo dotyczą materiałów:

* **ze źródeł tylko czytamy** (reguła twarda nr 1) — kopiujemy, nigdy nie
  przenosimy i nie zmieniamy niczego w ``00_SOURCES``;
* **nic nie nadpisujemy w ciemno** (reguła nr 2 i nr 6): plik docelowy o INNEJ
  treści to odmowa (:data:`CONFLICT`), a nie nadpisanie. Ten sam plik o tej samej
  treści to ``present`` — powtórzony przebieg nie robi nic i nie jest błędem;
* **brak pliku źródłowego to odmowa**, nie cicha strata: indeks rozjechał się ze
  źródłami i naprawia to ``just sources-check``, a nie `apply`;
* **zapis jest atomowy** (kopia obok + ``os.replace``), więc przerwany `apply`
  nie zostawia w paczce pliku uciętego w połowie.

Media (``action='media'``) obsłuży B13 — tutaj są policzone i pominięte, żeby nie
trafiły do repo paczki przez pomyłkę.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import config
from .hashes import sha256_file

#: Stany operacji. Kolejność ma znaczenie w raporcie: najpierw to, co blokuje.
CONFLICT = "conflict"
MISSING_SOURCE = "missing_source"
OUTSIDE = "outside"
NEW = "new"
PRESENT = "present"

#: Stany, które zatrzymują `apply` — żaden plik nie zostanie skopiowany.
BLOCKING_STATES: frozenset[str] = frozenset({CONFLICT, MISSING_SOURCE, OUTSIDE})

#: Akcja planu, która cokolwiek zapisuje do repo paczki.
COPY_ACTION = "copy"


@dataclass(frozen=True)
class Operation:
    """Jedna pozycja planu przełożona na operację na plikach."""

    sha256: str
    target_rel: str
    target: Path | None
    source: Path | None
    state: str
    detail: str = ""

    @property
    def blocking(self) -> bool:
        return self.state in BLOCKING_STATES

    def as_row(self) -> dict[str, Any]:
        """Wiersz do snapshotu/raportu — bez obiektów Path."""
        return {
            "sha256": self.sha256,
            "target_rel": self.target_rel,
            "target": None if self.target is None else str(self.target),
            "source": None if self.source is None else str(self.source),
            "state": self.state,
            "detail": self.detail,
        }


def copies_by_sha(conn, shas: Iterable[str]) -> dict[str, list[tuple[str, str]]]:
    """Materializacje treści z indeksu: sha256 → [(paczka, ścieżka w paczce), …].

    Kolejność jest stabilna (``file_id``), więc ten sam plan wybiera tę samą kopię
    przy każdym przebiegu — inaczej `verify` porównywałby się z czymś innym niż
    `apply` skopiował.
    """
    wanted = {str(sha) for sha in shas}
    if not wanted:
        return {}
    result: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute(
        "SELECT sha256, source_package, source_relative_path FROM files "
        "WHERE sha256 IS NOT NULL ORDER BY file_id"
    ):
        sha = str(row["sha256"])
        if sha in wanted:
            result.setdefault(sha, []).append(
                (str(row["source_package"]), str(row["source_relative_path"]))
            )
    return result


def resolve_target(paths: config.Paths, target_rel: str) -> Path | None:
    """Ścieżka docelowa w repo paczki albo ``None``, gdy plan celuje poza nią.

    Plan podaje ścieżkę względem repo docelowego (``paczka/SEM3/…``), a wolno mu
    pisać wyłącznie do katalogu paczki. Kontrola jest tutaj drugi raz — po B8 —
    bo to ostatni moment przed dotknięciem dysku.
    """
    resolved = config.resolve_within(paths.target_repo, target_rel)
    if resolved is None:
        return None
    paczka = Path(os.path.normpath(paths.target_paczka))
    return resolved if resolved.is_relative_to(paczka) else None


def plan_operations(
    rows: Sequence[Mapping[str, Any]],
    *,
    paths: config.Paths,
    copies: Mapping[str, Sequence[tuple[str, str]]],
) -> list[Operation]:
    """Przekłada linie planu na operacje; niczego nie wykonuje.

    Zwraca operacje WYŁĄCZNIE dla ``action='copy'`` — reszta akcji nie zapisuje
    do repo paczki, więc nie ma tu czego planować.
    """
    operations: list[Operation] = []
    for row in rows:
        if str(row.get("action")) != COPY_ACTION:
            continue
        sha = str(row.get("source_sha256") or "")
        target_rel = str(row.get("target_rel") or "")
        target = resolve_target(paths, target_rel)
        if target is None:
            operations.append(Operation(sha, target_rel, None, None, OUTSIDE,
                                        "ścieżka docelowa wychodzi poza katalog paczki"))
            continue
        source = None
        for package, relative in copies.get(sha, ()):
            candidate = config.resolve_within_sources(paths.sources, package, relative)
            if candidate is not None and candidate.is_file():
                source = candidate
                break
        if source is None:
            operations.append(Operation(sha, target_rel, target, None, MISSING_SOURCE,
                                        "żadna kopia treści nie leży dziś w źródłach"))
            continue
        if target.exists():
            existing = sha256_file(target)
            if existing == sha:
                operations.append(Operation(sha, target_rel, target, source, PRESENT,
                                            "ta sama treść już leży na miejscu"))
            else:
                operations.append(Operation(sha, target_rel, target, source, CONFLICT,
                                            f"pod ścieżką leży INNA treść ({existing[:12]}…)"))
            continue
        operations.append(Operation(sha, target_rel, target, source, NEW))
    return operations


def copy_operation(operation: Operation) -> None:
    """Kopiuje jeden plik atomowo, zachowując czas modyfikacji oryginału.

    Kopia powstaje obok celu i dopiero ``os.replace`` nadaje jej właściwą nazwę:
    przerwanie w połowie zostawia plik tymczasowy, nigdy uciętego materiału.
    """
    if operation.source is None or operation.target is None:
        raise ValueError(f"operacja bez źródła albo celu: {operation.target_rel}")
    target = operation.target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".apply-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        shutil.copy2(operation.source, temporary)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def summarize(operations: Sequence[Operation]) -> dict[str, int]:
    """Ile operacji w każdym stanie (wszystkie stany obecne, także zerowe)."""
    counts = {state: 0 for state in (NEW, PRESENT, CONFLICT, MISSING_SOURCE, OUTSIDE)}
    for operation in operations:
        counts[operation.state] = counts.get(operation.state, 0) + 1
    return counts
