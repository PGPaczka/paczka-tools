"""Skan istniejącej ``paczka/`` w repo produktu = ground truth (krok A7, sekcja 13.7).

Ręcznie ułożone materiały w ``target_repo`` (patrz ``config/paths.yaml:
target_repo`` + ``target_paczka_subdir``) są GROUND TRUTH (reguła twarda nr 2) —
ten skrypt ich NIE modyfikuje, wyłącznie CZYTA i zapisuje do bazy: treść
(``content``), fakt "ta treść już jest w paczce pod tą ścieżką" (``applied``)
oraz klasyfikację ręczną z pewnością 1.0 (``classifications``,
``classification_method='manual'``, ``run_id='ground_truth'``).

Konwencja ``applied.plan_hash`` dla wierszy z tego skryptu
-----------------------------------------------------------
``applied.plan_hash`` to wolna kolumna TEXT (schema.sql) — dla ground trutha
zapisujemy w niej ``"ground_truth:{size_bytes}:{mtime_seconds}"``. Pozwala to
wykryć, czy plik na dysku się zmienił, BEZ liczenia sha256 od nowa.

Dwie fazy, bo hash != klasyfikacja
-----------------------------------
Resume dotyczy WYŁĄCZNIE hashowania: gdy (size, mtime) się nie zmieniło, sha256
bierzemy z ostatniego ``applied`` zamiast liczyć go od nowa. Klasyfikacja jest
NATOMIAST przeliczana KAŻDEGO przebiegu, dla KAŻDEGO pliku — jest tania (sama
arytmetyka na ścieżkach) i musi widzieć całość, bo ta sama treść (sha256) może
dziś leżeć pod kilkoma ścieżkami docelowymi naraz. Dlatego skrypt robi dwa
przejścia:

1. Faza hash/applied — dla każdego pliku (z uwzględnieniem ``--limit``,
   patrz niżej) ustala sha256 (z cache'u albo licząc), zapisuje ``content`` +
   ``applied`` wsadami (jedna transakcja na wsad, content+applied razem).
2. Faza klasyfikacji — po zbudowaniu PEŁNEJ mapy sha256 -> zbiór ścieżek
   (z bieżącego przebiegu ORAZ z bazy, dla plików niewidzianych dziś, np.
   usuniętych z dysku, ale wciąż w ``applied``) każdej treści przypisuje się
   JEDNĄ klasyfikację, liczoną ze ŚCIEŻKI NAJMNIEJSZEJ leksykograficznie po
   segmentach (``path.split('/')``) — reguła deterministyczna niezależna od
   kolejności przebiegu. Pozostałe ścieżki tej samej treści nie dostają
   własnego wiersza w ``classifications`` (klucz naturalny tej tabeli to
   samo sha256 — jedna treść, jedna decyzja). Ta faza też pisze wsadami,
   ale OSOBNO od fazy 1 (wymaga znajomości WSZYSTKICH ścieżek treści, której
   przy stronicowaniu wsadem plików jeszcze nie znamy) — to świadome
   odejście od "jedna transakcja per pełny wsad plików".

``--limit`` a wznawialność
---------------------------
``--limit`` ogranicza WYŁĄCZNIE pliki wymagające hashowania (nowe/zmienione).
Pliki już policzone wcześniej (bez zmian) są zawsze doliczane w całości — dzięki
temu kolejne przebiegi z tym samym ``--limit`` faktycznie przesuwają się do
przodu po kolejnych partiach nowych plików, zamiast w kółko limitować się do
tych samych pierwszych N (dawny problem: limit liczony PRZED filtrem resume).

Semestry magisterskie i foldery poza zakresem
-----------------------------------------------
Katalog ``Magisterskie_SEM{n}`` koduje się jako semestr ``100 + n``.
``config/subjects.yaml`` nie ma dziś ŻADNYCH wpisów dla semestrów >= 100
(``config.iter_subjects()`` pomija sekcję ``magisterskie``) — takie pliki, oraz
foldery ``sources``/``ogolne`` (nie są i nigdy nie będą przedmiotem — to
foldery zbiorcze), trafiają do osobnej listy "poza zakresem": dostają
``content``/``applied``, ale klasyfikacji się dla nich nie sugeruje (dopisanie
aliasu w subjects.yaml i tak by nie pomogło). Prawdziwe niedopasowania
(literówka w skrócie, brakujący alias) trafiają do OSOBNEJ listy — tylko tam
warto szukać brakujących wpisów w subjects.yaml.

Katalog przedmiotu może leżeć głębiej niż bezpośrednio pod semestrem (strumień/
katedra pośrodku, np. ``SEM5/Systemy/{SKROT}_{Nazwa}``, ``SEM7/KISI/{SKROT}_{Nazwa}``)
— patrz :func:`classify_path`: szuka pierwszego z max. 3 kolejnych segmentów po
semestrze, który jednocześnie pasuje do wzorca ``{SKROT}_{Nazwa}`` (kanoniczny,
``config/syntax.yaml: meta.subject_folder``) / ``({SKROT})_{Nazwa}`` (stara
pisownia, wciąż spotykana w źródłach) I rozwiązuje się przez
:func:`orglib.config.find_subject` (pomija po drodze co najwyżej 2 segmenty
pośrednie, których nie zapisujemy).

Usuwanie nieaktualnych wpisów ground truth
--------------------------------------------
Gdy przebieg jest PEŁNYM skanem (``--limit`` nieustawiony), a wiersz w
``applied`` z ``plan_hash`` zaczynającym się od ``ground_truth:`` wskazuje na
ścieżkę, której NIE widzieliśmy podczas tego skanu (plik przeniesiono albo
usunięto z ``paczka/``), wiersz jest KASOWANY z ``applied`` — PRZED fazą 2, żeby
zwycięska ścieżka/klasyfikacja liczyła się wyłącznie z tego, co naprawdę leży
na dysku. To NIE łamie reguły twardej nr 5 ("nigdy nie kasuj niczego
automatycznie"): ta reguła dotyczy plików na dysku (fizycznych źródeł), a
``applied`` dla wierszy ``ground_truth:*`` to WYŁĄCZNIE wyprowadzony,
zwierciadlany zapis stanu ``paczka/`` w danej chwili — nic na dysku nie ginie,
kasujemy tylko nieaktualne echo w bazie. Wiersze z INNYM ``plan_hash``
(np. przyszłego ``apply.py`` z realnego planu) nigdy nie są tykane. Przy
``--limit`` to czyszczenie jest wyłączone (przebieg celowo nie widzi całości).

Uruchamianie: ``python scripts/scan_target.py [opcje]``.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Sequence

import typer

from orglib import config, db, hashes, kinds

app = typer.Typer(
    add_completion=False,
    help="Skan ground-truth istniejącej paczka/ w repo produktu (bez modyfikacji repo).",
)

#: Nazwy plików-śmieci systemowych (jak w scan.py — źródła/repo bywają z Windows).
IGNORED_NAMES: frozenset[str] = frozenset({"Thumbs.db", "desktop.ini"})
_IGNORED_FOLDED: frozenset[str] = frozenset(name.casefold() for name in IGNORED_NAMES)

#: Prefiks plików-blokad pakietu Office (``~$referat.docx``).
OFFICE_LOCK_PREFIX = "~$"

#: Ukryte PLIKI pomijane mimo że nie są katalogami (artefakty gita/macOS, nie treść).
#: Inne kropkowane pliki (np. ``.clang-format``) ZOSTAJĄ — to prawdziwa treść w repo.
_HIDDEN_FILE_NAMES: frozenset[str] = frozenset({".gitkeep", ".DS_Store"})
_HIDDEN_FILE_NAMES_FOLDED: frozenset[str] = frozenset(
    name.casefold() for name in _HIDDEN_FILE_NAMES
)

#: Prefiks plan_hash nadawany przez TEN skrypt (patrz docstring modułu).
GROUND_TRUTH_PREFIX = "ground_truth"

#: Foldery, które NIGDY nie są przedmiotem — niezależnie od tego, czy semestr
#: ma zarejestrowane przedmioty w subjects.yaml (patrz docstring modułu).
_OUT_OF_SCOPE_DIR_NAMES: frozenset[str] = frozenset({"sources", "ogolne"})

_SEM_RE = re.compile(r"^SEM(\d+)$")
_MAGISTERSKIE_RE = re.compile(r"^Magisterskie_SEM(\d+)$")
#: Akceptuje 'SKROT_Nazwa' (kanoniczny, syntax.yaml) i '(SKROT)_Nazwa' (stara pisownia).
_SUBJECT_RE = re.compile(r"^\(?([^)_]+)\)?_(.+)$")

#: Wartość dodawana do numeru semestru magisterskiego, żeby nie kolidował z 1-7.
MAGISTERSKIE_OFFSET = 100

#: Ile kolejnych segmentów po semestrze sprawdzamy w poszukiwaniu katalogu
#: przedmiotu (pomijając co najwyżej 2 pośrednie — strumień/profil).
_MAX_SUBJECT_DEPTH = 3


@dataclass
class Stats:
    """Liczniki jednego przebiegu (do podsumowania na stdout)."""

    seen: int = 0
    skipped_unchanged: int = 0
    hashed: int = 0
    classified: int = 0
    unmatched: int = 0
    errors: int = 0
    #: Suma bajtów WSZYSTKICH widzianych plików w tym przebiegu (z ``stat``,
    #: niezależnie czy plik był hashowany, czy wznowiony z cache'u).
    bytes_total: int = 0
    #: Suma bajtów plików FAKTYCZNIE zahashowanych w tym przebiegu (podzbiór wyżej).
    bytes_hashed: int = 0
    multi_path_content: int = 0
    #: Liczba usuniętych z ``applied`` nieaktualnych wpisów ground truth (patrz
    #: docstring modułu — tylko przy pełnym skanie, bez ``--limit``).
    stale_removed: int = 0
    unique_content: set[str] = field(default_factory=set)
    #: (semestr albo None, ścieżka pod semestrem) — realny brak dopasowania,
    #: kandydat na nowy alias w subjects.yaml.
    unmatched_folders: set[tuple[Optional[int], str]] = field(default_factory=set)
    #: jak wyżej, ale strukturalnie poza zakresem (sources/ogolne/magisterskie) —
    #: dopisanie aliasu i tak by nie pomogło.
    out_of_scope_folders: set[tuple[Optional[int], str]] = field(default_factory=set)

    def summary(self) -> str:
        return (
            f"widziane {self.seen}, bez zmian (pominięte hashowanie) {self.skipped_unchanged}, "
            f"zahashowane {self.hashed}, sklasyfikowane {self.classified}, "
            f"bez dopasowania {self.unmatched}, błędy {self.errors} · "
            f"unikalne treści {len(self.unique_content)}, "
            f"bajty {self.bytes_total} (zahashowane bajty: {self.bytes_hashed}) · "
            f"treści pod kilkoma ścieżkami docelowymi: {self.multi_path_content} "
            "(klasyfikacja wg najmniejszej ścieżki) · "
            f"usunięte nieaktualne wpisy ground truth: {self.stale_removed}"
        )


@dataclass
class Classification:
    """Wynik próby klasyfikacji jednej treści po segmentach ŚCIEŻKI ZWYCIĘZCY."""

    semester: Optional[int] = None
    subject: Optional[config.Subject] = None
    category: Optional[str] = None
    is_outdated: bool = False
    #: (semestr, ścieżka pod semestrem, czy dopisanie aliasu miałoby sens).
    unmatched: Optional[tuple[Optional[int], str, bool]] = None


@dataclass
class _Candidate:
    """Jeden plik ze skanu, przed decyzją hash/resume."""

    abs_path: Path
    parts: tuple[str, ...]
    target_relative_path: str
    size_bytes: int
    mtime_seconds: int
    expected_plan_hash: str
    #: sha256 z poprzedniego przebiegu, gdy plik jest bez zmian (patrz resume).
    resumed_sha: Optional[str] = None


def _warn(message: str) -> None:
    """Ostrzeżenie na stderr (skrypt nigdy nie przerywa się przez jeden zepsuty wpis)."""
    typer.echo(f"uwaga: {message}", err=True)


def _skip_reason(entry: "os.DirEntry[str]") -> Optional[str]:
    """Zwraca powód pominięcia wpisu ('symlink' / 'hidden' / 'ignored') albo ``None``.

    Ukrywanie po kropce dotyczy TYLKO katalogów (``.git``) i wymienionych z
    nazwy plików (``.gitkeep``, ``.DS_Store``) — inne kropkowane pliki (np.
    ``.clang-format``) to prawdziwa treść i zostają.
    """
    name = entry.name
    if entry.is_symlink():
        return "symlink"
    if name.casefold() in _IGNORED_FOLDED or name.startswith(OFFICE_LOCK_PREFIX):
        return "ignored"
    if name.startswith("."):
        if entry.is_dir(follow_symlinks=False):
            return "hidden"
        if name.casefold() in _HIDDEN_FILE_NAMES_FOLDED:
            return "hidden"
    return None


def _extension_of(filename: str) -> Optional[str]:
    """Rozszerzenie bez kropki, małymi literami; ``None`` gdy plik go nie ma."""
    suffix = Path(filename).suffix
    return suffix[1:].casefold() if len(suffix) > 1 else None


def _walk_paczka(paczka_dir: Path, stats: Stats) -> Iterator[tuple[Path, tuple[str, ...], int, int]]:
    """Rekurencyjnie zbiera pliki pod ``paczka_dir``.

    Pomija dowiązania symboliczne (pliki i katalogi), ukryte katalogi,
    ``.gitkeep``/``.DS_Store``, śmieci systemowe i blokady Office. Zwraca
    (ścieżka absolutna, segmenty ścieżki WZGLĘDEM ``paczka_dir`` łącznie z
    nazwą pliku, rozmiar, mtime w pełnych sekundach). Błąd odczytu dolicza się
    do ``stats.errors`` i nie przerywa reszty skanu.
    """

    def _walk(dir_path: Path, rel_parts: tuple[str, ...]) -> Iterator[tuple[Path, tuple[str, ...], int, int]]:
        try:
            with os.scandir(dir_path) as scanner:
                entries = sorted(scanner, key=lambda item: item.name)
        except OSError as exc:
            _warn(f"nie mogę odczytać katalogu {dir_path}: {exc}")
            stats.errors += 1
            return
        for entry in entries:
            if _skip_reason(entry) is not None:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                _warn(f"nie mogę odczytać {entry.path}: {exc}")
                stats.errors += 1
                continue
            child_parts = rel_parts + (entry.name,)
            if is_dir:
                yield from _walk(Path(entry.path), child_parts)
                continue
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError as exc:
                _warn(f"nie mogę odczytać {entry.path}: {exc}")
                stats.errors += 1
                continue
            size_bytes = int(stat_result.st_size)
            mtime_seconds = int(stat_result.st_mtime_ns // 1_000_000_000)
            yield Path(entry.path), child_parts, size_bytes, mtime_seconds

    yield from _walk(paczka_dir, ())


def _parse_semester_dir(name: str) -> Optional[int]:
    """Rozpoznaje 'SEM{n}' -> n albo 'Magisterskie_SEM{n}' -> 100+n; inaczej ``None``."""
    match = _SEM_RE.fullmatch(name)
    if match:
        return int(match.group(1))
    match = _MAGISTERSKIE_RE.fullmatch(name)
    if match:
        return MAGISTERSKIE_OFFSET + int(match.group(1))
    return None


def classify_path(parts: Sequence[str], subjects: Sequence[config.Subject]) -> Classification:
    """Klasyfikuje plik po segmentach ścieżki (względem ``paczka/``, z nazwą pliku).

    Szuka katalogu przedmiotu wśród pierwszych :data:`_MAX_SUBJECT_DEPTH`
    segmentów po semestrze (pomijając po drodze strumień/profil — nie
    zapisywane). Segment tuż za katalogiem przedmiotu to ``category``; gdy to
    dosłownie ``'outdated'``, ustawia ``is_outdated`` i ``category`` to
    KOLEJNY segment (albo ``None``).
    """
    parts = tuple(parts)
    if len(parts) < 2:
        return Classification(unmatched=(None, parts[0] if parts else "<korzeń paczki>", False))

    top = parts[0]
    semester = _parse_semester_dir(top)
    if semester is None:
        return Classification(unmatched=(None, top, False))

    dirs = parts[1:-1]
    has_subjects = any(subject.semester == semester for subject in subjects)

    if not dirs:
        return Classification(
            semester=semester,
            unmatched=(semester, "<brak podfolderu przedmiotu>", has_subjects),
        )

    if dirs[0].casefold() in _OUT_OF_SCOPE_DIR_NAMES:
        return Classification(semester=semester, unmatched=(semester, "/".join(dirs), False))

    if not has_subjects:
        return Classification(semester=semester, unmatched=(semester, "/".join(dirs), False))

    for index, candidate in enumerate(dirs[:_MAX_SUBJECT_DEPTH]):
        match = _SUBJECT_RE.fullmatch(candidate)
        if not match:
            continue
        try:
            subject = config.find_subject(semester, match.group(1), subjects)
        except (KeyError, ValueError):
            continue
        rest = dirs[index + 1 :]
        category = rest[0] if rest else None
        is_outdated = False
        if category == "outdated":
            is_outdated = True
            category = rest[1] if len(rest) > 1 else None
        return Classification(
            semester=semester, subject=subject, category=category, is_outdated=is_outdated
        )

    return Classification(semester=semester, unmatched=(semester, "/".join(dirs), True))


_APPLIED_UPSERT_SQL = (
    "INSERT INTO applied (target_relative_path, sha256, action, plan_hash, applied_at) "
    "VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT (target_relative_path) DO UPDATE SET "
    "sha256 = excluded.sha256, action = excluded.action, plan_hash = excluded.plan_hash, "
    "applied_at = excluded.applied_at"
)

_CLASSIFICATION_UPSERT_SQL = (
    "INSERT INTO classifications (sha256, semester, subject_key, category, "
    "target_relative_path, is_outdated, classification_method, confidence, run_id, decided_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (sha256) DO UPDATE SET "
    "semester = excluded.semester, subject_key = excluded.subject_key, "
    "category = excluded.category, target_relative_path = excluded.target_relative_path, "
    "is_outdated = excluded.is_outdated, classification_method = excluded.classification_method, "
    "confidence = excluded.confidence, run_id = excluded.run_id, decided_at = excluded.decided_at"
)


def _flush_batch(
    conn: sqlite3.Connection,
    content_rows: list[tuple[str, str]],
    applied_rows: list[dict[str, object]],
    classification_rows: list[dict[str, object]],
) -> None:
    """Zapisuje jedną partię (content + applied + classifications) w JEDNEJ transakcji.

    ``content`` idzie ręcznym SQL-em z ``ON CONFLICT DO NOTHING`` (jak w
    hash_files.py) — pierwsze napotkane rozszerzenie dla danej treści wygrywa.
    """
    if not (content_rows or applied_rows or classification_rows):
        return
    with conn:
        for sha256, content_kind in content_rows:
            conn.execute(
                "INSERT INTO content (sha256, content_kind) VALUES (?, ?) "
                "ON CONFLICT (sha256) DO NOTHING",
                (sha256, content_kind),
            )
        for row in applied_rows:
            conn.execute(
                _APPLIED_UPSERT_SQL,
                (
                    row["target_relative_path"],
                    row["sha256"],
                    row["action"],
                    row["plan_hash"],
                    row["applied_at"],
                ),
            )
        for row in classification_rows:
            conn.execute(
                _CLASSIFICATION_UPSERT_SQL,
                (
                    row["sha256"],
                    row["semester"],
                    row["subject_key"],
                    row["category"],
                    row["target_relative_path"],
                    row["is_outdated"],
                    row["classification_method"],
                    row["confidence"],
                    row["run_id"],
                    row["decided_at"],
                ),
            )


def _report_progress(prefix: str, done: int, total: int, started_at: float) -> None:
    """Drukuje postęp partii na stderr."""
    elapsed = time.monotonic() - started_at
    typer.echo(f"scan_target [{prefix}]: {done}/{total}, upłynęło {elapsed:.1f}s", err=True)


def scan_target(
    conn: sqlite3.Connection,
    repo_root: Path,
    paczka_subdir: str,
    subjects: Sequence[config.Subject],
    *,
    batch: int = 200,
    limit: Optional[int] = None,
) -> Stats:
    """Skanuje ``<repo_root>/<paczka_subdir>`` i zapisuje ground truth do bazy.

    Nic nie zapisuje do ``repo_root`` — to wyłącznie odczyt (reguła twarda
    nr 2). ``limit`` ogranicza wyłącznie pliki wymagające (re)hashowania —
    patrz docstring modułu.
    """
    stats = Stats()
    paczka_dir = Path(repo_root) / paczka_subdir
    prefix_len = len(GROUND_TRUTH_PREFIX) + 1

    existing_applied: dict[str, tuple[str, str]] = {
        str(row["target_relative_path"]): (str(row["plan_hash"]), str(row["sha256"]))
        for row in conn.execute(
            "SELECT target_relative_path, plan_hash, sha256 FROM applied "
            "WHERE substr(plan_hash, 1, ?) = ?",
            (prefix_len, f"{GROUND_TRUTH_PREFIX}:"),
        )
    }
    # Zalążek mapy treści -> ścieżki: to, co baza wiedziała PRZED tym przebiegiem
    # (obejmuje też pliki, które dziś zniknęły z dysku — patrz docstring modułu).
    path_to_sha: dict[str, str] = {path: sha for path, (_, sha) in existing_applied.items()}

    walked = sorted(
        _walk_paczka(paczka_dir, stats),
        key=lambda item: (Path(paczka_subdir) / Path(*item[1])).as_posix(),
    )

    # --- Usuwanie nieaktualnych wpisów ground truth (patrz docstring modułu) ----
    # Tylko przy PEŁNYM skanie (bez --limit) — inaczej przebieg celowo nie widzi
    # całości i nie może wiarygodnie stwierdzić, że ścieżka naprawdę zniknęła.
    if limit is None:
        seen_on_disk = {
            (Path(paczka_subdir) / Path(*item[1])).as_posix() for item in walked
        }
        stale_paths = [path for path in existing_applied if path not in seen_on_disk]
        if stale_paths:
            with conn:
                conn.executemany(
                    "DELETE FROM applied WHERE target_relative_path = ?",
                    [(path,) for path in stale_paths],
                )
            for path in stale_paths:
                path_to_sha.pop(path, None)
            stats.stale_removed = len(stale_paths)

    resumable: list[_Candidate] = []
    pending: list[_Candidate] = []
    for abs_path, parts, size_bytes, mtime_seconds in walked:
        target_relative_path = (Path(paczka_subdir) / Path(*parts)).as_posix()
        expected_plan_hash = f"{GROUND_TRUTH_PREFIX}:{size_bytes}:{mtime_seconds}"
        candidate = _Candidate(
            abs_path=abs_path,
            parts=parts,
            target_relative_path=target_relative_path,
            size_bytes=size_bytes,
            mtime_seconds=mtime_seconds,
            expected_plan_hash=expected_plan_hash,
        )
        previous = existing_applied.get(target_relative_path)
        if previous is not None and previous[0] == expected_plan_hash:
            candidate.resumed_sha = previous[1]
            resumable.append(candidate)
        else:
            pending.append(candidate)

    if limit is not None:
        pending = pending[: max(0, int(limit))]

    processed = sorted(resumable + pending, key=lambda c: c.target_relative_path)
    total = len(processed)

    # --- Faza 1: hash (z resume) + content + applied ----------------------------
    content_rows: list[tuple[str, str]] = []
    applied_rows: list[dict[str, object]] = []
    started_at = time.monotonic()

    for done, candidate in enumerate(processed, start=1):
        stats.seen += 1
        stats.bytes_total += candidate.size_bytes
        if candidate.resumed_sha is not None:
            stats.skipped_unchanged += 1
            stats.unique_content.add(candidate.resumed_sha)
            path_to_sha[candidate.target_relative_path] = candidate.resumed_sha
        else:
            try:
                sha256 = hashes.sha256_file(candidate.abs_path)
            except OSError as exc:
                stats.errors += 1
                _warn(f"nie mogę odczytać {candidate.abs_path}: {exc}")
                continue
            content_kind = kinds.content_kind_for(_extension_of(candidate.parts[-1]))
            content_rows.append((sha256, content_kind))
            applied_rows.append(
                {
                    "target_relative_path": candidate.target_relative_path,
                    "sha256": sha256,
                    "action": "copy",
                    "plan_hash": candidate.expected_plan_hash,
                    "applied_at": db.now_iso(),
                }
            )
            stats.hashed += 1
            stats.unique_content.add(sha256)
            stats.bytes_hashed += candidate.size_bytes
            path_to_sha[candidate.target_relative_path] = sha256

        if done % batch == 0:
            _flush_batch(conn, content_rows, applied_rows, [])
            content_rows, applied_rows = [], []
            _report_progress("hash", done, total, started_at)

    _flush_batch(conn, content_rows, applied_rows, [])
    if total and total % batch != 0:
        _report_progress("hash", total, total, started_at)

    # --- Faza 2: klasyfikacja per TREŚĆ (nie per plik) --------------------------
    sha_to_paths: dict[str, set[str]] = {}
    for path, sha in path_to_sha.items():
        sha_to_paths.setdefault(sha, set()).add(path)

    classification_rows: list[dict[str, object]] = []
    class_started = time.monotonic()
    class_total = len(sha_to_paths)

    for class_done, (sha256, paths) in enumerate(sha_to_paths.items(), start=1):
        if len(paths) > 1:
            stats.multi_path_content += 1
        winner = min(paths, key=lambda p: tuple(p.split("/")))
        try:
            winner_parts = Path(winner).relative_to(paczka_subdir).parts
        except ValueError:
            stats.errors += 1
            _warn(
                f"zwycięska ścieżka {winner!r} dla treści {sha256} nie leży pod "
                f"'{paczka_subdir}/' — pomijam klasyfikację tej treści"
            )
            continue
        classification = classify_path(winner_parts, subjects)

        if classification.subject is not None:
            existing_row = conn.execute(
                "SELECT classification_method, run_id FROM classifications WHERE sha256 = ?",
                (sha256,),
            ).fetchone()
            manual_wins = (
                existing_row is not None
                and existing_row["classification_method"] == "manual"
                and existing_row["run_id"] != "ground_truth"
            )
            if not manual_wins:
                classification_rows.append(
                    {
                        "sha256": sha256,
                        "semester": classification.subject.semester,
                        "subject_key": classification.subject.skrot,
                        "category": classification.category,
                        "target_relative_path": winner,
                        "is_outdated": 1 if classification.is_outdated else 0,
                        "classification_method": "manual",
                        "confidence": 1.0,
                        "run_id": "ground_truth",
                        "decided_at": db.now_iso(),
                    }
                )
                stats.classified += 1
        elif classification.unmatched is not None:
            stats.unmatched += 1
            semester, name, in_scope = classification.unmatched
            if in_scope:
                stats.unmatched_folders.add((semester, name))
            else:
                stats.out_of_scope_folders.add((semester, name))

        if class_done % batch == 0:
            _flush_batch(conn, [], [], classification_rows)
            classification_rows = []
            _report_progress("classify", class_done, class_total, class_started)

    _flush_batch(conn, [], [], classification_rows)
    if class_total and class_total % batch != 0:
        _report_progress("classify", class_total, class_total, class_started)

    return stats


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


def _format_folder_list(title: str, folders: set[tuple[Optional[int], str]], suffix: str) -> None:
    """Drukuje jedną listę folderów (posortowaną, unikalną) z podanym sufiksem."""
    if not folders:
        return
    typer.echo(title)
    for semester, name in sorted(
        folders, key=lambda item: (item[0] if item[0] is not None else -1, item[1])
    ):
        sem_label = "brak" if semester is None else str(semester)
        typer.echo(f"  semestr {sem_label}: {name}{suffix}")


@app.command()
def main(
    db_path: Optional[Path] = typer.Option(
        None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml)."
    ),
    target_repo: Optional[Path] = typer.Option(
        None,
        "--target-repo",
        help="Korzeń repo produktu (domyślnie config/paths.yaml: target_repo). "
        "Nazwa podkatalogu materiałów bierze się zawsze z config/paths.yaml.",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Przetwórz co najwyżej N plików WYMAGAJĄCYCH hashowania."
    ),
    batch: int = typer.Option(200, "--batch", help="Ile wierszy zapisywać w jednej transakcji."),
) -> None:
    """Skanuje istniejącą paczka/ w repo produktu jako ground truth (tylko odczyt repo)."""
    if batch < 1:
        typer.echo("--batch musi być >= 1", err=True)
        raise typer.Exit(code=2)

    path = _require_db(db_path)
    paths = config.load_paths()
    repo_root = Path(target_repo) if target_repo is not None else paths.target_repo
    paczka_subdir = paths.target_paczka.name
    paczka_dir = repo_root / paczka_subdir

    if not paczka_dir.is_dir():
        typer.echo(f"brak katalogu paczki: {paczka_dir}", err=True)
        raise typer.Exit(code=1)

    subjects = config.iter_subjects()
    conn = db.connect(path, init=False)
    started = time.perf_counter()
    try:
        typer.echo(f"baza: {path}")
        typer.echo(f"paczka: {paczka_dir}")
        stats = scan_target(conn, repo_root, paczka_subdir, subjects, batch=batch, limit=limit)
    except sqlite3.Error as exc:
        typer.echo(f"błąd bazy danych: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        conn.close()
    elapsed = time.perf_counter() - started

    typer.echo(stats.summary())
    typer.echo(f"czas: {elapsed:.1f}s")
    _format_folder_list(
        "foldery bez dopasowania w subjects.yaml (dopisz alias albo popraw skrót):",
        stats.unmatched_folders,
        "",
    )
    _format_folder_list(
        "foldery poza zakresem klasyfikacji (alias by nie pomógł):",
        stats.out_of_scope_folders,
        " (bez przedmiotu — poza zakresem)",
    )

    if stats.errors > 0:
        raise typer.Exit(code=3)


if __name__ == "__main__":
    app()
