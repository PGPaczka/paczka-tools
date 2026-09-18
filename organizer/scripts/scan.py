"""Skan (stat) paczek źródłowych do bazy: source_packages, folders, files.

Krok 3 potoku (sekcja 13 architektury). Skrypt NIE czyta zawartości plików —
robi wyłącznie ``stat``: rozmiar, czas modyfikacji i podpis strukturalny
poddrzewa (:func:`orglib.hashes.structural_signature`). Hashowanie treści to
osobny etap (``hash_files.py``).

Źródła są READ-ONLY (reguła twarda nr 1): skrypt tylko je czyta. Nic nie kasuje
(reguła nr 5) — plik czy katalog zniknięty z dysku zostaje w bazie i jest
raportowany jako „brak”.

Wykrywanie zmian na re-runie
----------------------------
Ponowny skan porównuje stan z dysku ze stanem w bazie:

* plik o tym samym ``size_bytes`` i ``modified_date`` => ŻADNEGO zapisu
  (status i hashe z dalszych etapów zostają nietknięte);
* katalog o tym samym ``structural_signature`` => żadnego zapisu;
* plik zmieniony => UPSERT, który **cofa status do 'discovered'** i zeruje
  ``sha256``, ``normalized_text_hash``, ``simhash``, ``perceptual_hash``,
  ``error_message``. To JEDYNE dozwolone cofnięcie w maszynie stanów: skoro
  zmieniła się treść źródła, wszystko, co z niej wyliczono, jest nieaktualne.
  Dlatego robimy to UPSERT-em, a nie :func:`orglib.db.advance_status` (ta
  słusznie zabrania cofania). Analogicznie katalog ze zmienionym podpisem traci
  ``tree_hash``, ``content_set_hash`` i ``duplicate_of``.

Uruchamianie: ``python scripts/scan.py [--db PATH] [--package NAZWA]...``
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import typer

from orglib import config, db, hashes

#: Nazwy plików-śmieci systemowych, których nigdy nie wciągamy do bazy
#: (porównanie bez rozróżniania wielkości liter — źródła pochodzą z Windows).
IGNORED_NAMES: frozenset[str] = frozenset({"Thumbs.db", "desktop.ini"})

#: Prefiks plików-blokad pakietu Office (``~$referat.docx``) — artefakt edycji,
#: nie materiał.
OFFICE_LOCK_PREFIX = "~$"

#: Kolumny pliku zerowane, gdy treść źródła się zmieniła (patrz docstring modułu).
_FILE_RESET: dict[str, None] = {
    "sha256": None,
    "normalized_text_hash": None,
    "simhash": None,
    "perceptual_hash": None,
    "error_message": None,
}

#: Kolumny katalogu zerowane, gdy zmienił się podpis strukturalny poddrzewa.
_FOLDER_RESET: dict[str, None] = {
    "tree_hash": None,
    "content_set_hash": None,
    "duplicate_of": None,
}

_IGNORED_FOLDED: frozenset[str] = frozenset(name.casefold() for name in IGNORED_NAMES)


@dataclass
class PackageStats:
    """Licznik jednego przebiegu skanu paczki (do podsumowania na stdout)."""

    package: str
    files_new: int = 0
    files_changed: int = 0
    files_unchanged: int = 0
    files_missing: int = 0
    folders_written: int = 0
    folders_unchanged: int = 0
    folders_missing: int = 0
    skipped_symlinks: int = 0
    skipped_hidden: int = 0
    skipped_ignored: int = 0
    errors: int = 0

    def summary(self) -> str:
        """Jednolinijkowe podsumowanie paczki."""
        return (
            f"{self.package}: pliki nowe {self.files_new}, zmienione {self.files_changed}, "
            f"bez zmian {self.files_unchanged}, brak na dysku {self.files_missing} · "
            f"katalogi zapisane {self.folders_written}, bez zmian {self.folders_unchanged}, "
            f"brak na dysku {self.folders_missing} · pominięte: dowiązania "
            f"{self.skipped_symlinks}, ukryte {self.skipped_hidden}, śmieci "
            f"{self.skipped_ignored}, błędy {self.errors}"
        )


@dataclass
class _Subtree:
    """Zagregowane poddrzewo jednego katalogu (wynik rekurencji)."""

    #: (ścieżka względem TEGO katalogu, rozmiar, mtime w PEŁNYCH SEKUNDACH) — wejście podpisu.
    entries: list[tuple[str, int, int]] = field(default_factory=list)
    total_bytes: int = 0
    max_mtime: Optional[str] = None
    #: True, gdy któregoś katalogu w poddrzewie nie dało się odczytać — wtedy
    #: agregaty opisują tylko czytelną część, więc podpisu nie wolno wyliczyć.
    has_error: bool = False


@dataclass
class _Buffers:
    """Zbiorniki wypełniane przez rekurencję jednej paczki."""

    stats: PackageStats
    file_rows: list[dict[str, object]] = field(default_factory=list)
    folder_records: dict[str, dict[str, object]] = field(default_factory=dict)
    #: folder_path katalogów, których nie dało się odczytać (ich poddrzewo jest
    #: nieznane, więc nie wolno uznać leżących tam wierszy za „brak na dysku”).
    error_folders: set[str] = field(default_factory=set)


def _warn(message: str) -> None:
    """Ostrzeżenie na stderr (skan nigdy nie przerywa się przez jeden zepsuty wpis)."""
    typer.echo(f"uwaga: {message}", err=True)


#: Reguła zaokrąglania mtime i format ISO żyją w ``orglib.db``, bo korzysta z nich
#: także kontrola niezmienności źródeł (``orglib.integrity``). Dwie kopie tej samej
#: reguły rozjechałyby się przy pierwszej zmianie granulacji.
_mtime_seconds = db.mtime_seconds
_mtime_iso = db.mtime_iso


def _is_encodable(name: str) -> bool:
    """Czy nazwa da się zapisać w UTF-8 (nazwy spoza UTF-8 wracają z surogatami)."""
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _extension_of(filename: str) -> Optional[str]:
    """Rozszerzenie bez kropki, małymi literami; ``None`` gdy plik go nie ma."""
    suffix = Path(filename).suffix
    return suffix[1:].casefold() if len(suffix) > 1 else None


def _human_bytes(size: int) -> str:
    """Rozmiar po ludzku, w jednostkach binarnych (deterministycznie, bez locale)."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < 1024.0 or unit == "PiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    raise AssertionError("nieosiągalne")


def _skip_reason(entry: os.DirEntry[str]) -> Optional[str]:
    """Zwraca powód pominięcia wpisu ('symlink' / 'hidden' / 'ignored') albo ``None``."""
    name = entry.name
    if name.startswith("."):
        return "hidden"
    if name.casefold() in _IGNORED_FOLDED or name.startswith(OFFICE_LOCK_PREFIX):
        return "ignored"
    if entry.is_symlink():
        return "symlink"
    return None


def _count_skip(reason: str, stats: PackageStats) -> None:
    """Dolicza pominięcie do właściwego licznika."""
    if reason == "symlink":
        stats.skipped_symlinks += 1
    elif reason == "hidden":
        stats.skipped_hidden += 1
    else:
        stats.skipped_ignored += 1


def discover_packages(sources: Path) -> tuple[list[str], int]:
    """Nazwy paczek = bezpośrednie podkatalogi ``sources``, posortowane.

    Zwraca ``(nazwy, liczba pominiętych wpisów)``. Pomijane (z ostrzeżeniem, poza
    nazwami ukrytymi) są: dowiązania symboliczne — paczka musi być prawdziwym
    katalogiem, inaczej ten sam materiał trafiłby do bazy dwa razy — oraz nazwy
    spoza UTF-8.
    """
    names: list[str] = []
    skipped = 0
    with os.scandir(Path(sources)) as scanner:
        for entry in scanner:
            if entry.name.startswith("."):
                continue
            if not _is_encodable(entry.name):
                _warn(f"pomijam paczkę o nazwie spoza UTF-8: {entry.name!r}")
                skipped += 1
                continue
            if entry.is_symlink():
                _warn(f"pomijam dowiązanie symboliczne na poziomie paczek: {entry.path}")
                skipped += 1
                continue
            if entry.is_dir(follow_symlinks=False):
                names.append(entry.name)
    return sorted(names), skipped


def _scan_dir(dir_path: Path, package: str, folder_rel: str, buffers: _Buffers) -> _Subtree:
    """Rekurencyjnie zbiera poddrzewo katalogu; dopisuje wiersze plików i katalogów.

    ``folder_rel`` to ścieżka katalogu względem korzenia paczki (``''`` dla samego
    korzenia). Zwraca agregaty poddrzewa dla katalogu nadrzędnego.

    Katalog nieczytelny (OSError ze ``scandir``) NIE jest zapisywany jako pusty —
    dostaje status 'error' i puste agregaty, a flaga błędu idzie w górę: każdy
    przodek też ląduje w 'error' i traci ``structural_signature`` (jego poddrzewo
    jest częściowo nieznane), zachowując liczby z czytelnej części.
    """
    stats = buffers.stats
    subtree = _Subtree()
    unreadable = False
    try:
        with os.scandir(dir_path) as scanner:
            entries = sorted(scanner, key=lambda item: item.name)
    except OSError as exc:
        _warn(f"nie mogę odczytać katalogu {dir_path}: {exc}")
        stats.errors += 1
        unreadable = True
        entries = []

    for entry in entries:
        try:
            if not _is_encodable(entry.name):
                _warn(f"pomijam wpis o nazwie spoza UTF-8: {entry.path!r}")
                stats.errors += 1
                continue
            reason = _skip_reason(entry)
            if reason is not None:
                _count_skip(reason, stats)
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            stat_result = None if is_dir else entry.stat(follow_symlinks=False)
        except OSError as exc:
            _warn(f"nie mogę odczytać {entry.path}: {exc}")
            stats.errors += 1
            continue

        child_rel = f"{folder_rel}/{entry.name}" if folder_rel else entry.name
        if is_dir:
            child = _scan_dir(Path(entry.path), package, child_rel, buffers)
            subtree.entries.extend(
                (f"{entry.name}/{rel}", size, mtime) for rel, size, mtime in child.entries
            )
            subtree.total_bytes += child.total_bytes
            subtree.has_error = subtree.has_error or child.has_error
            if child.max_mtime is not None and (
                subtree.max_mtime is None or child.max_mtime > subtree.max_mtime
            ):
                subtree.max_mtime = child.max_mtime
            continue

        assert stat_result is not None
        size_bytes = int(stat_result.st_size)
        mtime_seconds = _mtime_seconds(int(stat_result.st_mtime_ns))
        modified_date = _mtime_iso(mtime_seconds)
        buffers.file_rows.append(
            {
                "source_package": package,
                "source_relative_path": child_rel,
                "folder_path": db.folder_path_for(package, child_rel),
                "filename": entry.name,
                "extension": _extension_of(entry.name),
                "size_bytes": size_bytes,
                "modified_date": modified_date,
            }
        )
        subtree.entries.append((entry.name, size_bytes, mtime_seconds))
        subtree.total_bytes += size_bytes
        if subtree.max_mtime is None or modified_date > subtree.max_mtime:
            # ISO w tym formacie jest rosnący leksykograficznie, więc max ciągów
            # == ISO maksymalnego mtime.
            subtree.max_mtime = modified_date

    folder_path = f"{package}/{folder_rel}" if folder_rel else package
    if unreadable:
        subtree.has_error = True
        buffers.error_folders.add(folder_path)
        record: dict[str, object] = {
            "folder_path": folder_path,
            "source_package": package,
            "file_count": None,
            "total_bytes": None,
            "max_mtime": None,
            "structural_signature": None,
            "status": "error",
        }
    else:
        record = {
            "folder_path": folder_path,
            "source_package": package,
            "file_count": len(subtree.entries),
            "total_bytes": subtree.total_bytes,
            "max_mtime": subtree.max_mtime,
            "structural_signature": (
                None if subtree.has_error else hashes.structural_signature(subtree.entries)
            ),
            "status": "error" if subtree.has_error else "discovered",
        }
    buffers.folder_records[folder_path] = record
    return subtree


def _under_error(folder_path: str, error_folders: set[str]) -> bool:
    """Czy ``folder_path`` leży w poddrzewie katalogu, którego nie dało się odczytać.

    Takiego poddrzewa skan w ogóle nie zobaczył, więc wierszy stamtąd nie wolno
    zgłaszać jako „brak na dysku” (a tym bardziej kasować — reguła twarda nr 5).
    """
    return any(
        folder_path == error or folder_path.startswith(f"{error}/") for error in error_folders
    )


def scan_package(conn, package_dir: Path, package: str) -> PackageStats:
    """Skanuje jedną paczkę i zapisuje różnice do bazy; zwraca liczniki przebiegu.

    Zapis idzie dwoma wsadami (katalogi przed plikami — FK ``files.folder_path``),
    każdy w jednej transakcji.
    """
    stats = PackageStats(package=package)
    buffers = _Buffers(stats=stats)
    _scan_dir(Path(package_dir), package, "", buffers)
    file_rows = buffers.file_rows
    folder_records = buffers.folder_records

    db.upsert(
        conn,
        "source_packages",
        {"package_name": package, "local_path": str(Path(package_dir))},
        conflict=("package_name",),
    )

    # --- katalogi ---
    known_folders = {
        str(row["folder_path"]): row["structural_signature"]
        for row in conn.execute(
            "SELECT folder_path, structural_signature FROM folders WHERE source_package = ?",
            (package,),
        )
    }
    folder_writes: list[dict[str, object]] = []
    for folder_path, record in folder_records.items():
        signature = record["structural_signature"]
        # Brak podpisu = stan nieznany (błąd), więc zapisujemy zawsze — porównanie
        # NULL == NULL nie może udawać „bez zmian”.
        if signature is not None and known_folders.get(folder_path) == signature:
            stats.folders_unchanged += 1
            continue
        folder_writes.append({**record, **_FOLDER_RESET})
    stats.folders_written = db.upsert_many(
        conn, "folders", folder_writes, conflict=("folder_path",)
    )
    gone_folders = sorted(
        path
        for path in set(known_folders) - set(folder_records)
        if not _under_error(path, buffers.error_folders)
    )
    stats.folders_missing = len(gone_folders)
    if gone_folders:
        _warn(
            f"{package}: {len(gone_folders)} katalogów jest w bazie, ale nie ma ich na dysku "
            f"(nic nie kasuję): {', '.join(gone_folders[:5])}"
            f"{' …' if len(gone_folders) > 5 else ''}"
        )

    # --- pliki ---
    known_files = {
        str(row["source_relative_path"]): (row["size_bytes"], row["modified_date"])
        for row in conn.execute(
            "SELECT source_relative_path, size_bytes, modified_date FROM files "
            "WHERE source_package = ?",
            (package,),
        )
    }
    file_writes: list[dict[str, object]] = []
    for row in file_rows:
        previous = known_files.get(str(row["source_relative_path"]))
        if previous is None:
            stats.files_new += 1
            file_writes.append({**row, "status": "discovered"})
        elif previous == (row["size_bytes"], row["modified_date"]):
            stats.files_unchanged += 1
        else:
            stats.files_changed += 1
            file_writes.append({**row, **_FILE_RESET, "status": "discovered"})
    db.upsert_many(
        conn, "files", file_writes, conflict=("source_package", "source_relative_path")
    )
    seen_files = {str(row["source_relative_path"]) for row in file_rows}
    gone_files = sorted(
        relpath
        for relpath in set(known_files) - seen_files
        if not _under_error(db.folder_path_for(package, relpath), buffers.error_folders)
    )
    stats.files_missing = len(gone_files)
    if gone_files:
        _warn(
            f"{package}: {len(gone_files)} plików jest w bazie, ale nie ma ich na dysku "
            f"(nic nie kasuję): {', '.join(gone_files[:5])}"
            f"{' …' if len(gone_files) > 5 else ''}"
        )
    return stats


def scan_sources(conn, sources: Path, packages: Sequence[str]) -> list[PackageStats]:
    """Skanuje wskazane paczki leżące w ``sources`` (po kolei) i zwraca ich liczniki."""
    return [scan_package(conn, Path(sources) / name, name) for name in packages]


def _tree_lines(package: str, rows: Iterable) -> Iterator[str]:
    """Linie drzewa jednej paczki: tylko katalogi, posortowane, wcięcie 2 spacje/poziom."""
    for row in sorted(rows, key=lambda item: str(item["folder_path"]).split("/")):
        parts = str(row["folder_path"]).split("/")
        indent = "  " * (len(parts) - 1)
        count = int(row["file_count"] or 0)
        size = _human_bytes(int(row["total_bytes"] or 0))
        yield f"{indent}- {parts[-1]}/  ({count} plików, {size})"


def render_sources_tree(conn) -> str:
    """Renderuje snapshot drzewa źródeł z BAZY (wszystkie paczki), bez znaczników czasu.

    Wynik jest deterministyczny — dwa wywołania na tej samej bazie dają identyczny
    tekst, więc plik nadaje się do diffowania w gicie. Plików nie wypisujemy
    (pójdą do ``reports/inventory.jsonl``).
    """
    packages = [
        str(row["package_name"])
        for row in conn.execute("SELECT package_name FROM source_packages ORDER BY package_name")
    ]
    totals = conn.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size_bytes), 0) AS bytes FROM files"
    ).fetchone()
    folder_count = int(conn.execute("SELECT COUNT(*) AS n FROM folders").fetchone()["n"])

    lines = [
        "# Snapshot drzewa źródeł",
        "",
        "Generowane przez `scripts/scan.py` — nie edytuj ręcznie.",
        "",
        f"Paczki: {len(packages)} · katalogi: {folder_count} · pliki: {int(totals['files'])} "
        f"· rozmiar: {_human_bytes(int(totals['bytes']))}",
        "",
    ]
    for package in packages:
        rows = conn.execute(
            "SELECT folder_path, file_count, total_bytes FROM folders WHERE source_package = ?",
            (package,),
        ).fetchall()
        lines.extend(_tree_lines(package, rows))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def write_sources_tree(conn, path: Path) -> Path:
    """Zapisuje snapshot drzewa źródeł do pliku Markdown i zwraca jego ścieżkę."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_sources_tree(conn), encoding="utf-8")
    return path


app = typer.Typer(
    add_completion=False,
    help="Skan (stat) paczek źródłowych do bazy: source_packages, folders, files.",
)


def _db_path(explicit: Optional[Path]) -> Path:
    """Zwraca ścieżkę bazy: z opcji --db albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().work_db


def _sources_dir(explicit: Optional[Path]) -> Path:
    """Zwraca katalog źródeł: z opcji --sources albo z config/paths.yaml."""
    return Path(explicit) if explicit is not None else config.load_paths().sources


@app.command()
def scan(
    db_path: Optional[Path] = typer.Option(
        None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml)."
    ),
    packages: Optional[list[str]] = typer.Option(
        None, "--package", help="Skanuj tylko tę paczkę (można podać wielokrotnie)."
    ),
    sources: Optional[Path] = typer.Option(
        None, "--sources", help="Katalog źródeł (domyślnie z config/paths.yaml)."
    ),
    tree: Optional[Path] = typer.Option(
        None, "--tree", help="Plik snapshotu drzewa (domyślnie reports/SOURCES_TREE.md)."
    ),
    no_tree: bool = typer.Option(False, "--no-tree", help="Nie generuj snapshotu drzewa."),
) -> None:
    """Statuje paczki źródłowe i zapisuje różnice do bazy (źródeł nie modyfikuje).

    Kody wyjścia: 0 = skan pełny, 3 = skan CZĘŚCIOWY (coś pominięto: nieczytelny
    katalog, nazwa spoza UTF-8, błąd stat — zapis i tak się odbył), 1 = zły
    katalog źródeł lub nieznana paczka, 2 = sprzeczne opcje.
    """
    if no_tree and tree is not None:
        typer.echo("--tree i --no-tree wykluczają się.", err=True)
        raise typer.Exit(code=2)

    sources_dir = _sources_dir(sources)
    if not sources_dir.is_dir():
        typer.echo(f"brak katalogu źródeł: {sources_dir}", err=True)
        raise typer.Exit(code=1)

    available, skipped_packages = discover_packages(sources_dir)
    if packages:
        unknown = [name for name in packages if name not in available]
        if unknown:
            typer.echo(
                f"brak paczek w {sources_dir}: {', '.join(unknown)} "
                f"(dostępne: {', '.join(available) or 'brak'})",
                err=True,
            )
            raise typer.Exit(code=1)
        selected = [name for name in available if name in set(packages)]
    else:
        selected = available

    target_db = _db_path(db_path)
    started = time.perf_counter()
    conn = db.connect(target_db)
    try:
        typer.echo(f"baza: {target_db}")
        typer.echo(f"źródła: {sources_dir} (paczki: {len(selected)})")
        results = scan_sources(conn, sources_dir, selected)
        for stats in results:
            typer.echo(stats.summary())
        if not no_tree:
            default_tree = config.ORGANIZER_ROOT / "reports" / "SOURCES_TREE.md"
            tree_path = tree if tree is not None else default_tree
            typer.echo(f"drzewo: {write_sources_tree(conn, Path(tree_path))}")
    finally:
        conn.close()

    elapsed = time.perf_counter() - started
    errors = skipped_packages + sum(s.errors for s in results)
    typer.echo(
        "razem: pliki nowe {}, zmienione {}, bez zmian {}, brak {} · katalogi zapisane {} "
        "· błędy {} · czas {:.2f} s".format(
            sum(s.files_new for s in results),
            sum(s.files_changed for s in results),
            sum(s.files_unchanged for s in results),
            sum(s.files_missing for s in results),
            sum(s.folders_written for s in results),
            errors,
            elapsed,
        )
    )
    if errors:
        typer.echo(f"skan częściowy: pominięto {errors} wpisów (szczegóły wyżej).", err=True)
        raise typer.Exit(code=3)


if __name__ == "__main__":
    app()
