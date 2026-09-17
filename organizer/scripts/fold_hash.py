"""Hashowanie katalogów (Merkle) i logiczny dedup poddrzew: sekcja 5 architektury.

Krok 5 potoku, po ``hash_files.py``. Skrypt pracuje WYŁĄCZNIE na bazie — nie
czyta ani jednego pliku ze źródeł (jedyne wejście/wyjście na dysku to raport CSV).
Dedup jest logiczny: nic nie kasujemy (reguła twarda nr 5), a duplikatem może być
tylko poddrzewo o IDENTYCZNYM ``tree_hash`` (reguła twarda nr 4) — nigdy „podobne”.

Przejście 1 (hashe)
-------------------
Dla każdego katalogu zbieramy wszystkie pliki jego PODDRZEWA (czyli także z
podkatalogów) i liczymy:

* ``tree_hash`` = :func:`orglib.hashes.tree_hash` z par ``(relpath, sha256)``,
  gdzie ``relpath`` jest ścieżką pliku **względem TEGO katalogu** (dla korzenia
  paczki jest to po prostu ``source_relative_path``). Dzięki temu to samo
  poddrzewo przeniesione pod innego rodzica ma ten sam ``tree_hash``;
* ``content_set_hash`` = :func:`orglib.hashes.content_set_hash` z samych sha256
  (ta sama treść mimo innych nazw plików).

Trzy rodzaje katalogów dostają oba hashe ``NULL`` i zachowują dotychczasowy
``status``, przez co nie mogą zostać uznane za duplikat ani trafić do raportu
pokrycia:

* **pusty** — 0 plików w poddrzewie;
* **niekompletny** — choć jeden plik w poddrzewie bez ``sha256`` (``hash_files.py``
  jeszcze go nie przerobił);
* **z błędem skanu** — ``status == 'error'`` (``scan.py`` nie zdołał odczytać tego
  katalogu, więc jego poddrzewo jest z definicji niepełne, nawet gdy wszystkie
  ZNANE pliki mają już sha256).

Przejście 1 zawsze zeruje ``duplicate_of``, bo przejście 2 wylicza je od nowa.

Przejście 2 (duplicate_of)
--------------------------
Katalogi grupujemy po ``tree_hash``; w grupie o liczności >= 2 **kanoniczny jest
katalog o najmniejszej KROTCE KOMPONENTÓW ścieżki** (``folder_path.split('/')``),
a pozostałe dostają ``duplicate_of`` = kanoniczny.

Krotka komponentów, a nie zwykły napis: porównanie napisów NIE zachowuje porządku
przy dopisywaniu dziecka, bo spacja, ``(`` czy ``-`` sortują się poniżej ``/``.
Kontrprzykład z prawdziwych źródeł: ``'P/AKO2020' < 'P/AKO2020 (1)'``, ale
``'P/AKO2020/wyklady' > 'P/AKO2020 (1)/wyklady'``. Na krotkach porównanie jest
stabilne: ``tuple(A) < tuple(B)`` implikuje ``tuple(A/rest) < tuple(B/rest)``.

Stąd niezmiennik:

    katalog kanoniczny nigdy nie leży wewnątrz katalogu-duplikatu.

Dowód: gdyby przodek ``A`` kanonicznego ``C = A/rest`` był duplikatem katalogu
``A'`` o ``tuple(A') < tuple(A)``, to ``C' = A'/rest`` miałby to samo poddrzewo co
``C`` i ``tuple(C') < tuple(C)``, więc ``C`` nie byłby kanoniczny. Wyjątkiem
byłoby tylko ``A'`` będące właściwym prefiksem ``A`` — a to niemożliwe, bo
niepuste drzewo nie może być równe swojemu właściwemu poddrzewu.

Niezmiennik jest KRYTYCZNY: :func:`orglib.db.files_pending` wycina poddrzewa
duplikatów, więc kanoniczny katalog schowany pod duplikatem oznaczałby ciche
wypadnięcie jego treści z extract/classify. Dlatego liczymy go jeszcze raz
obronnie (:func:`check_canonical_invariant`) i przy naruszeniu NIC nie zapisujemy.

Przejście 2 jest ZAWSZE globalne, także przy ``--package``: czyta ``tree_hash``
wszystkich katalogów i przelicza ``duplicate_of`` dla wszystkich (w tym kasuje
nieaktualne wskazania spoza filtrowanej paczki). Filtr ogranicza wyłącznie to,
co przelicza przejście 1.

Dwa przejścia są też wymuszone przez FK ``folders.duplicate_of -> folders`` (patrz
komentarz w ``schema.sql``): cel musi istnieć w tabeli, zanim ktokolwiek na niego
wskaże. Każde przejście to jedno ``executemany`` w jednej transakcji.

Raport pokrycia
---------------
Pary katalogów, które NIE są dokładnymi duplikatami, ale dzielą dużą część treści
(„częściowe pokrycie” z sekcji 5), trafiają do ``reports/folder_overlap.csv``.
Próg pochodzi z ``config/thresholds.yaml: folder_overlap.report_min_ratio``.

Uruchamianie: ``python scripts/fold_hash.py [opcje]``.
"""

from __future__ import annotations

import csv
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import typer

from orglib import config, db, hashes

#: sha256 obecny w większej liczbie katalogów-kandydatów niż ten limit pomijamy
#: przy liczeniu pokrycia: to treść „wszechobecna” (puste README, ta sama ikonka),
#: która generuje kwadratową liczbę bezwartościowych par.
MAX_SHARED_FOLDERS = 200

#: Górny limit zliczeń par w raporcie pokrycia. Liczba par rośnie kwadratowo
#: z liczbą katalogów dzielących treść, więc na patologicznych danych raport
#: potrafiłby zjeść godziny i pamięć. Po przekroczeniu limitu CSV pomijamy
#: (z komunikatem), zamiast zawieszać cały przebieg — hashe i dedup są ważniejsze.
MAX_PAIR_INCREMENTS = 5_000_000

#: Zapis wszystkich hashy katalogu w jednym ``executemany`` (przejście 1).
_UPDATE_HASHES_SQL = (
    "UPDATE folders SET tree_hash = ?, content_set_hash = ?, status = ?, duplicate_of = NULL "
    "WHERE folder_path = ?"
)

#: Zapis wskazań na duplikat (przejście 2).
_UPDATE_DUPLICATE_SQL = "UPDATE folders SET duplicate_of = ? WHERE folder_path = ?"

#: Kolumny raportu pokrycia (kolejność jest częścią kontraktu pliku).
OVERLAP_COLUMNS: tuple[str, ...] = (
    "folder_a",
    "folder_b",
    "unique_a",
    "unique_b",
    "common",
    "ratio_min",
    "jaccard",
    "files_a",
    "files_b",
)


@dataclass
class Folder:
    """Wiersz katalogu wczytany do pamięci (bez hashy — te liczymy tutaj)."""

    folder_path: str
    source_package: str
    file_count: int
    total_bytes: int
    status: str


@dataclass
class Subtree:
    """Zagregowane poddrzewo jednego katalogu (pliki tego katalogu i wszystkich niższych)."""

    #: Pary (ścieżka względem TEGO katalogu, sha256) — wejście tree_hash.
    #: Puste, gdy poddrzewo jest niekompletne (patrz :attr:`missing_hash`).
    pairs: list[tuple[str, str]] = field(default_factory=list)
    #: Liczba plików w poddrzewie (także tych bez sha256).
    file_count: int = 0
    #: Czy w poddrzewie jest plik bez sha256 (hash_files.py go jeszcze nie przerobił).
    missing_hash: bool = False

    @property
    def is_empty(self) -> bool:
        """Poddrzewo bez ani jednego pliku."""
        return self.file_count == 0


@dataclass(frozen=True)
class FolderState:
    """Stan katalogu po przejściu 1, czytany GLOBALNIE na potrzeby przejścia 2."""

    tree_hash: Optional[str]
    duplicate_of: Optional[str]
    file_count: int
    total_bytes: int


@dataclass
class HashStats:
    """Liczniki przejścia 1 (do podsumowania na stdout)."""

    total: int = 0
    hashed: int = 0
    empty: int = 0
    incomplete: int = 0
    errors: int = 0


@dataclass(frozen=True)
class OverlapPair:
    """Jedna para katalogów o częściowym pokryciu treści (wiersz raportu CSV)."""

    folder_a: str
    folder_b: str
    unique_a: int
    unique_b: int
    common: int
    ratio_min: float
    jaccard: float
    files_a: int
    files_b: int

    def as_row(self) -> list[object]:
        """Wiersz CSV w kolejności :data:`OVERLAP_COLUMNS` (ułamki na 4 miejsca)."""
        return [
            self.folder_a,
            self.folder_b,
            self.unique_a,
            self.unique_b,
            self.common,
            f"{self.ratio_min:.4f}",
            f"{self.jaccard:.4f}",
            self.files_a,
            self.files_b,
        ]


@dataclass
class OverlapResult:
    """Wynik fazy raportu pokrycia (także wtedy, gdy świadomie ją pominęliśmy)."""

    pairs: list[OverlapPair] = field(default_factory=list)
    #: Ile sha256 pominięto jako zbyt częste (limit ``max_shared_folders``).
    skipped_hashes: int = 0
    #: Ile zliczeń par wymagałby ten przebieg (po odsianiu zbyt częstych sha256).
    increments: int = 0
    #: True, gdy przekroczono :data:`MAX_PAIR_INCREMENTS` i raport NIE powstał.
    aborted: bool = False


# --- wczytanie bazy -----------------------------------------------------------


def _package_filter(column: str, packages: Sequence[str]) -> tuple[str, list[str]]:
    """Buduje fragment ``WHERE`` ograniczający do wskazanych paczek (pusty => bez filtra)."""
    if not packages:
        return "", []
    placeholders = ", ".join("?" * len(packages))
    return f" WHERE {column} IN ({placeholders})", list(packages)


def load_folders(conn: sqlite3.Connection, packages: Sequence[str] = ()) -> dict[str, Folder]:
    """Wczytuje katalogi (jeden SELECT) do słownika folder_path -> :class:`Folder`."""
    where, params = _package_filter("source_package", packages)
    sql = (
        "SELECT folder_path, source_package, file_count, total_bytes, status FROM folders" + where
    )
    return {
        str(row["folder_path"]): Folder(
            folder_path=str(row["folder_path"]),
            source_package=str(row["source_package"]),
            file_count=int(row["file_count"] or 0),
            total_bytes=int(row["total_bytes"] or 0),
            status=str(row["status"]),
        )
        for row in conn.execute(sql, params)
    }


def load_files(conn: sqlite3.Connection, packages: Sequence[str] = ()) -> list[sqlite3.Row]:
    """Wczytuje pliki (jeden SELECT): folder_path, ścieżka względna, sha256, rozmiar."""
    where, params = _package_filter("source_package", packages)
    sql = (
        "SELECT folder_path, source_package, source_relative_path, sha256, size_bytes FROM files"
        + where
    )
    return conn.execute(sql, params).fetchall()


# --- przejście 1: tree_hash / content_set_hash --------------------------------


def ancestor_paths(folder_path: str, source_package: str) -> list[str]:
    """Ścieżki katalogu i wszystkich jego przodków w obrębie paczki, od korzenia w dół.

    Dla ``('P1/a/b', 'P1')`` zwraca ``['P1', 'P1/a', 'P1/a/b']``. Gdy ścieżka nie
    zaczyna się nazwą paczki (wiersz spoza konwencji :func:`orglib.db.folder_path_for`),
    zwraca wyłącznie ją samą — zgadywanie przodków byłoby tu tylko psuciem danych.
    """
    if folder_path == source_package:
        return [folder_path]
    prefix = f"{source_package}/"
    if not folder_path.startswith(prefix):
        return [folder_path]
    paths = [source_package]
    current = source_package
    for part in folder_path[len(prefix) :].split("/"):
        current = f"{current}/{part}"
        paths.append(current)
    return paths


def aggregate_subtrees(
    folders: dict[str, Folder], files: Iterable[sqlite3.Row]
) -> dict[str, Subtree]:
    """Przypisuje każdy plik do WSZYSTKICH jego katalogów-przodków (jedno przejście po plikach).

    Zamiast zapytania na katalog (10k zapytań) idziemy raz po plikach i dla każdego
    doklejamy go do poddrzew jego przodków; koszt to O(pliki × głębokość).
    ``relpath`` skracamy o prefiks katalogu, więc każde poddrzewo widzi ścieżki
    względem siebie.
    """
    subtrees: dict[str, Subtree] = {path: Subtree() for path in folders}
    for row in files:
        folder_path = str(row["folder_path"])
        package = str(row["source_package"])
        relative_path = str(row["source_relative_path"])
        sha256 = row["sha256"]
        # 'P1/a/b' pod paczką 'P1' obcina z 'a/b/plik.pdf' dokładnie tyle znaków,
        # ile ma prefiks 'a/b/' — czyli len(ancestor) - len(package).
        conventional = folder_path == package or folder_path.startswith(f"{package}/")
        for ancestor in ancestor_paths(folder_path, package):
            subtree = subtrees.get(ancestor)
            if subtree is None:
                # Katalog nieobecny w tabeli folders (albo odfiltrowany przez
                # --package) — pomijamy, nic dla niego nie liczymy.
                continue
            subtree.file_count += 1
            if sha256 is None:
                subtree.missing_hash = True
                subtree.pairs.clear()
            elif not subtree.missing_hash:
                offset = len(ancestor) - len(package) if conventional else 0
                subtree.pairs.append((relative_path[offset:], str(sha256)))
    return subtrees


def compute_hashes(
    folders: dict[str, Folder], subtrees: dict[str, Subtree]
) -> tuple[dict[str, tuple[Optional[str], Optional[str]]], HashStats]:
    """Liczy hashe poddrzew; zwraca mapę folder_path -> (tree_hash, content_set_hash) i liczniki.

    Katalog pusty, niekompletny albo w statusie 'error' dostaje parę ``(None, None)``
    — nigdy nie zostanie przez to duplikatem ani kandydatem do raportu pokrycia.
    Status 'error' (nieczytelny katalog wykryty przez ``scan.py``) sprawdzamy jako
    pierwszy: jego poddrzewo jest z definicji niepełne, nawet jeśli wszystkie
    ZNANE pliki mają sha256.
    """
    stats = HashStats(total=len(folders))
    result: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for folder_path in folders:
        subtree = subtrees[folder_path]
        if folders[folder_path].status == db.ERROR_STATUS:
            stats.errors += 1
            result[folder_path] = (None, None)
        elif subtree.is_empty:
            stats.empty += 1
            result[folder_path] = (None, None)
        elif subtree.missing_hash:
            stats.incomplete += 1
            result[folder_path] = (None, None)
        else:
            stats.hashed += 1
            result[folder_path] = (
                hashes.tree_hash(subtree.pairs),
                hashes.content_set_hash(sha for _, sha in subtree.pairs),
            )
    return result, stats


def _status_for(tree_hash: Optional[str], current_status: str) -> str:
    """Status katalogu po przejściu 1: 'hashed', lepkie 'error' albo powrót do 'discovered'."""
    if tree_hash is not None:
        return "hashed"
    return db.ERROR_STATUS if current_status == db.ERROR_STATUS else "discovered"


def write_hashes(
    conn: sqlite3.Connection,
    folders: dict[str, Folder],
    computed: dict[str, tuple[Optional[str], Optional[str]]],
) -> int:
    """Zapisuje hashe katalogów jednym ``executemany`` w jednej transakcji; zwraca liczbę wierszy.

    Katalog z policzonymi hashami dostaje status 'hashed'. Pusty i niekompletny
    WRACA do 'discovered' — nie wolno mu zostawić nieaktualnego 'hashed' z
    poprzedniego przebiegu, skoro teraz hashy nie ma. Jedynym statusem lepkim
    jest 'error' (nieczytelny katalog ze ``scan.py``): opuszcza go dopiero
    ponowny, udany skan. ``duplicate_of`` zawsze idzie do NULL — przejście 2
    wylicza je od zera.
    """
    rows = [
        (
            tree,
            content_set,
            _status_for(tree, folders[folder_path].status),
            folder_path,
        )
        for folder_path, (tree, content_set) in sorted(computed.items())
    ]
    with conn:
        conn.executemany(_UPDATE_HASHES_SQL, rows)
    return len(rows)


# --- przejście 2: duplicate_of ------------------------------------------------


def path_key(folder_path: str) -> list[str]:
    """Klucz porządkujący ścieżkę: KROTKA KOMPONENTÓW, nigdy goły napis.

    Porównanie napisów nie przeżywa dopisania dziecka (``' '``, ``'('``, ``'-'``
    sortują się poniżej ``'/'``), więc wybór kanonicznego katalogu po napisie
    potrafi wsadzić kanoniczny katalog pod duplikat — patrz docstring modułu.
    """
    return folder_path.split("/")


def load_folder_state(conn: sqlite3.Connection) -> dict[str, FolderState]:
    """Wczytuje stan WSZYSTKICH katalogów (jeden SELECT) — przejście 2 jest zawsze globalne.

    Świadomie bez filtra ``--package``: gdyby przebieg czytał tylko jedną paczkę,
    nie miałby jak skasować wskazań ``duplicate_of`` z innych paczek na katalog,
    który właśnie przestał być duplikatem.
    """
    return {
        str(row["folder_path"]): FolderState(
            tree_hash=row["tree_hash"],
            duplicate_of=row["duplicate_of"],
            file_count=int(row["file_count"] or 0),
            total_bytes=int(row["total_bytes"] or 0),
        )
        for row in conn.execute(
            "SELECT folder_path, tree_hash, duplicate_of, file_count, total_bytes FROM folders"
        )
    }


def check_canonical_invariant(duplicates: Mapping[str, str]) -> None:
    """Pilnuje, że żaden katalog kanoniczny nie leży wewnątrz katalogu-duplikatu.

    Naruszenie byłoby cichą utratą treści: :func:`orglib.db.files_pending` wycina
    poddrzewa duplikatów, więc pliki kanonicznej kopii nigdy nie doczekałyby się
    extract/classify. Dlatego zamiast zapisać taki stan podnosimy ``RuntimeError``.
    """
    duplicate_paths = set(duplicates)
    for canonical in sorted(set(duplicates.values())):
        parts = path_key(canonical)
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            if ancestor in duplicate_paths:
                raise RuntimeError(
                    f"naruszony niezmiennik dedupu: kanoniczny katalog {canonical!r} leży "
                    f"pod duplikatem {ancestor!r} (duplikat {ancestor!r} -> "
                    f"{duplicates[ancestor]!r}) — nic nie zapisuję"
                )


def duplicate_map(tree_hashes: Mapping[str, Optional[str]]) -> dict[str, str]:
    """Mapa duplikat -> kanoniczny dla grup o wspólnym ``tree_hash`` i liczności >= 2.

    Kanoniczny to katalog o najmniejszej krotce komponentów ścieżki
    (:func:`path_key`). Katalogi bez ``tree_hash`` (puste, niekompletne, z błędem
    skanu) nie wchodzą do żadnej grupy, więc nigdy nie zostaną ani duplikatem,
    ani celem ``duplicate_of``. Wynik przechodzi przez
    :func:`check_canonical_invariant`, zanim ktokolwiek go zapisze.
    """
    groups: dict[str, list[str]] = {}
    for folder_path, tree in tree_hashes.items():
        if tree is not None:
            groups.setdefault(str(tree), []).append(folder_path)
    duplicates: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        canonical = min(members, key=path_key)
        for member in members:
            if member != canonical:
                duplicates[member] = canonical
    check_canonical_invariant(duplicates)
    return duplicates


def write_duplicates(
    conn: sqlite3.Connection, state: Mapping[str, FolderState], duplicates: Mapping[str, str]
) -> int:
    """Zapisuje ``duplicate_of`` dla wszystkich katalogów; zwraca liczbę ZMIENIONYCH wierszy.

    Zapisujemy tylko różnice wobec stanu w bazie, ale patrzymy na CAŁĄ tabelę —
    dzięki temu katalog, który przestał być duplikatem, dostaje z powrotem NULL,
    nawet jeśli leży poza filtrem ``--package`` tego przebiegu.
    """
    rows = [
        (duplicates.get(folder_path), folder_path)
        for folder_path in sorted(state)
        if duplicates.get(folder_path) != state[folder_path].duplicate_of
    ]
    if rows:
        with conn:
            conn.executemany(_UPDATE_DUPLICATE_SQL, rows)
    return len(rows)


# --- raport częściowego pokrycia ----------------------------------------------


def _parent_path(folder_path: str) -> Optional[str]:
    """Ścieżka katalogu nadrzędnego albo ``None`` dla korzenia paczki."""
    index = folder_path.rfind("/")
    return None if index < 0 else folder_path[:index]


def _covers(ancestor: str, descendant: str) -> bool:
    """Czy ``ancestor`` jest tym samym katalogiem co ``descendant`` albo jego przodkiem."""
    return descendant == ancestor or descendant.startswith(f"{ancestor}/")


def _overlap_candidates(
    folders: dict[str, Folder],
    subtrees: dict[str, Subtree],
    computed: dict[str, tuple[Optional[str], Optional[str]]],
    duplicates: Mapping[str, str],
) -> dict[str, set[str]]:
    """Katalogi brane pod uwagę w raporcie: mają tree_hash, nie są duplikatem, >= 2 treści.

    Klucze idą w porządku leksykograficznym — dzięki temu listy indeksu odwrotnego
    są posortowane i pary powstają od razu w kolejności ``folder_a < folder_b``.
    """
    candidates: dict[str, set[str]] = {}
    for folder_path in sorted(folders):
        if computed[folder_path][0] is None or folder_path in duplicates:
            continue
        shas = {sha for _, sha in subtrees[folder_path].pairs}
        if len(shas) >= 2:
            candidates[folder_path] = shas
    return candidates


def _common_counts(
    candidates: dict[str, set[str]], max_shared_folders: int, max_increments: int
) -> tuple[Optional[Counter[tuple[str, str]]], int, int]:
    """Liczy wspólne treści dla par katalogów przez indeks odwrotny sha256 -> katalogi.

    Zwraca ``(licznik par, pominięte sha256, liczba zliczeń)``. Licznik jest
    ``None``, gdy liczba zliczeń przekracza ``max_increments`` — wtedy raportu nie
    liczymy w ogóle (koszt jest kwadratowy, a hashe i dedup są ważniejsze niż CSV).
    Koszt szacujemy PRZED pętlą, więc limit nigdy nie przekłada się na pracę,
    którą i tak trzeba by wyrzucić.
    """
    index: dict[str, list[str]] = {}
    for folder_path, shas in candidates.items():
        for sha in shas:
            index.setdefault(sha, []).append(folder_path)

    usable = [paths for paths in index.values() if len(paths) <= max_shared_folders]
    skipped = len(index) - len(usable)
    increments = sum(len(paths) * (len(paths) - 1) // 2 for paths in usable)
    if increments > max_increments:
        return None, skipped, increments

    counts: Counter[tuple[str, str]] = Counter()
    for paths in usable:
        for i, first in enumerate(paths):
            for second in paths[i + 1 :]:
                counts[(first, second)] += 1
    return counts, skipped, increments


def _drop_covered_by_parents(
    kept: dict[tuple[str, str], OverlapPair], candidates: dict[str, set[str]]
) -> list[OverlapPair]:
    """Usuwa pary „niemaksymalne”: takie, których para rodziców mówi już to samo.

    Gdy ``(parent(a), parent(b))`` też jest raportowaną parą i ma co najmniej tyle
    samo wspólnych treści, para ``(a, b)`` jest tylko szumem wewnątrz większego
    pokrycia. Decyzje liczymy na zbiorze sprzed usuwania, więc wynik nie zależy od
    kolejności przetwarzania.
    """
    survivors: list[OverlapPair] = []
    for key, pair in kept.items():
        parent_a = _parent_path(pair.folder_a)
        parent_b = _parent_path(pair.folder_b)
        if parent_a is None or parent_b is None:
            survivors.append(pair)
            continue
        if parent_a not in candidates or parent_b not in candidates:
            survivors.append(pair)
            continue
        parent_key = (parent_a, parent_b) if parent_a < parent_b else (parent_b, parent_a)
        parent_pair = kept.get(parent_key)
        if parent_pair is not None and parent_key != key and parent_pair.common >= pair.common:
            continue
        survivors.append(pair)
    return survivors


def overlap_pairs(
    folders: dict[str, Folder],
    subtrees: dict[str, Subtree],
    computed: dict[str, tuple[Optional[str], Optional[str]]],
    duplicates: Mapping[str, str],
    min_ratio: float,
    max_shared_folders: int = MAX_SHARED_FOLDERS,
    max_increments: int = MAX_PAIR_INCREMENTS,
) -> OverlapResult:
    """Wylicza pary katalogów o częściowym pokryciu treści.

    Pokrycie liczymy na ZBIORACH unikalnych sha256 poddrzewa:
    ``ratio_min = wspólne / min(|A|, |B|)``, ``jaccard = wspólne / |A ∪ B|``.
    Pary przodek–potomek pomijamy (potomek z definicji zawiera się w przodku, więc
    ``ratio_min`` byłby zawsze 1.0 i nic by nie wnosił). Wynik jest posortowany
    malejąco po ``ratio_min``, potem po liczbie wspólnych treści i po nazwach.
    Przy przekroczeniu ``max_increments`` zwraca wynik z ``aborted=True`` i pustą
    listą par — to nie jest błąd, tylko świadome odpuszczenie raportu.
    """
    candidates = _overlap_candidates(folders, subtrees, computed, duplicates)
    counts, skipped, increments = _common_counts(candidates, max_shared_folders, max_increments)
    if counts is None:
        return OverlapResult(skipped_hashes=skipped, increments=increments, aborted=True)

    kept: dict[tuple[str, str], OverlapPair] = {}
    for (first, second), common in counts.items():
        if _covers(first, second) or _covers(second, first):
            continue
        unique_a = len(candidates[first])
        unique_b = len(candidates[second])
        ratio_min = common / min(unique_a, unique_b)
        if ratio_min < min_ratio:
            continue
        kept[(first, second)] = OverlapPair(
            folder_a=first,
            folder_b=second,
            unique_a=unique_a,
            unique_b=unique_b,
            common=common,
            ratio_min=ratio_min,
            jaccard=common / (unique_a + unique_b - common),
            files_a=folders[first].file_count,
            files_b=folders[second].file_count,
        )

    survivors = _drop_covered_by_parents(kept, candidates)
    survivors.sort(
        key=lambda pair: (
            -round(pair.ratio_min, 4),
            -pair.common,
            pair.folder_a,
            pair.folder_b,
        )
    )
    return OverlapResult(pairs=survivors, skipped_hashes=skipped, increments=increments)


def write_overlap_csv(path: Path, pairs: Sequence[OverlapPair]) -> Path:
    """Zapisuje raport pokrycia do CSV (UTF-8, końce linii '\\n') i zwraca jego ścieżkę."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(OVERLAP_COLUMNS)
        for pair in pairs:
            writer.writerow(pair.as_row())
    return path


# --- CLI ----------------------------------------------------------------------


app = typer.Typer(
    add_completion=False,
    help="Liczy tree_hash/content_set_hash katalogów i oznacza dokładne duplikaty poddrzew.",
)


def _db_path(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę bazy: z opcji --db albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().work_db


def _require_db(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę istniejącej bazy albo kończy z kodem 1 (nie zakłada pustego pliku)."""
    path = _db_path(explicit)
    if not path.exists():
        typer.echo(f"brak bazy: {path} — uruchom najpierw 'db_admin.py init'.", err=True)
        raise typer.Exit(code=1)
    return path


def _min_ratio() -> float:
    """Próg raportowania pokrycia z config/thresholds.yaml (folder_overlap.report_min_ratio)."""
    thresholds = config.load_thresholds()
    try:
        return float(thresholds["folder_overlap"]["report_min_ratio"])
    except (KeyError, TypeError) as exc:
        raise KeyError(
            "thresholds.yaml: brak folder_overlap.report_min_ratio — uzupełnij konfigurację"
        ) from exc


def _selected_packages(conn: sqlite3.Connection, packages: Sequence[str]) -> list[str]:
    """Waliduje nazwy paczek wobec bazy i zwraca je posortowane (pusta lista = wszystkie)."""
    if not packages:
        return []
    known = {
        str(row["package_name"])
        for row in conn.execute("SELECT package_name FROM source_packages")
    }
    unknown = sorted(set(packages) - known)
    if unknown:
        typer.echo(
            f"brak paczek w bazie: {', '.join(unknown)} "
            f"(dostępne: {', '.join(sorted(known)) or 'brak'})",
            err=True,
        )
        raise typer.Exit(code=1)
    return sorted(set(packages))


def _duplicate_totals(
    state: Mapping[str, FolderState], duplicates: Mapping[str, str]
) -> tuple[int, int, int]:
    """Zwraca (liczba grup, liczba plików, suma bajtów) dla katalogów-duplikatów.

    Liczy z globalnego stanu, bo przejście 2 też jest globalne — przy ``--package``
    podsumowanie dedupu i tak dotyczy całej bazy.
    """
    groups = len(set(duplicates.values()))
    files = sum(state[path].file_count for path in duplicates)
    total_bytes = sum(state[path].total_bytes for path in duplicates)
    return groups, files, total_bytes


@app.command()
def main(
    db_path: Optional[Path] = typer.Option(
        None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml)."
    ),
    packages: Optional[list[str]] = typer.Option(
        None, "--package", help="Ogranicz do tej paczki (można podać wielokrotnie)."
    ),
    overlap_csv: Optional[Path] = typer.Option(
        None, "--overlap-csv", help="Plik raportu pokrycia (domyślnie reports/folder_overlap.csv)."
    ),
    no_overlap: bool = typer.Option(
        False, "--no-overlap", help="Nie licz i nie zapisuj raportu pokrycia."
    ),
) -> None:
    """Liczy hashe poddrzew, oznacza dokładne duplikaty katalogów i raportuje pokrycia."""
    if no_overlap and overlap_csv is not None:
        typer.echo("--overlap-csv i --no-overlap wykluczają się.", err=True)
        raise typer.Exit(code=2)

    path = _require_db(db_path)
    min_ratio = _min_ratio() if not no_overlap else 0.0
    started = time.perf_counter()
    conn = db.connect(path, init=False)
    try:
        typer.echo(f"baza: {path}")
        selected = _selected_packages(conn, packages or ())
        if selected:
            typer.echo(f"paczki: {', '.join(selected)}")

        folders = load_folders(conn, selected)
        files = load_files(conn, selected)
        subtrees = aggregate_subtrees(folders, files)
        computed, stats = compute_hashes(folders, subtrees)
        write_hashes(conn, folders, computed)

        # Przejście 2 czyta CAŁĄ tabelę, także katalogi spoza --package: tylko tak
        # da się skasować nieaktualne wskazania na katalog, który przestał być
        # duplikatem.
        state = load_folder_state(conn)
        duplicates = duplicate_map({path: item.tree_hash for path, item in state.items()})
        write_duplicates(conn, state, duplicates)
        groups, dup_files, dup_bytes = _duplicate_totals(state, duplicates)

        typer.echo(
            f"katalogi: razem {stats.total}, zhashowane {stats.hashed}, puste {stats.empty}, "
            f"niekompletne {stats.incomplete}"
        )
        typer.echo(f"katalogi z błędem skanu: {stats.errors}")
        typer.echo(
            f"duplikaty: grup {groups}, katalogów {len(duplicates)} "
            f"(pliki {dup_files}, bajty {dup_bytes})"
        )

        if no_overlap:
            typer.echo("pokrycie: pominięte (--no-overlap)")
        else:
            # Limit podajemy jawnie (a nie przez domyślny argument), żeby czytać go
            # z modułu w chwili wywołania — testy mogą go wtedy podmienić.
            overlap = overlap_pairs(
                folders,
                subtrees,
                computed,
                duplicates,
                min_ratio,
                max_increments=MAX_PAIR_INCREMENTS,
            )
            if overlap.aborted:
                typer.echo(
                    f"uwaga: raport pokrycia pominięty — wymagałby {overlap.increments} "
                    f"zliczeń par, limit to {MAX_PAIR_INCREMENTS}; zawęź przebieg opcją "
                    "--package albo podnieś MAX_SHARED_FOLDERS",
                    err=True,
                )
                typer.echo(
                    f"pokrycie: POMINIĘTE (zliczeń par {overlap.increments} > "
                    f"{MAX_PAIR_INCREMENTS}), raport nie powstał"
                )
            else:
                target = (
                    Path(overlap_csv)
                    if overlap_csv is not None
                    else config.ORGANIZER_ROOT / "reports" / "folder_overlap.csv"
                )
                write_overlap_csv(target, overlap.pairs)
                typer.echo(
                    f"pokrycie: par {len(overlap.pairs)} (próg ratio_min >= {min_ratio:.2f}), "
                    f"sha256 pominięte jako zbyt częste: {overlap.skipped_hashes}"
                )
                typer.echo(f"raport: {target}")
    finally:
        conn.close()

    typer.echo(f"czas: {time.perf_counter() - started:.2f} s")


if __name__ == "__main__":
    app()
