"""Raport deduplikacji: unikalne vs duplikaty (liczby, bajty, per paczka).

Krok 6 pierwszego przebiegu (sekcja 13 architektury). Skrypt TYLKO czyta bazę
(``20_WORK/organizer.sqlite``) i zapisuje dwa pliki tekstowe do ``reports/``:

* ``dedup_summary.md`` — deterministyczny raport Markdown (bez znaczników
  czasu — dwa przebiegi na tej samej bazie dają identyczny plik, więc nadaje
  się do diffowania w gicie);
* ``inventory.jsonl`` — jedna linia JSON na plik źródłowy: „ślad” 00_SOURCES
  wymagany przez sekcję 3 architektury (P2b), commitowany bez binariów.

Źródła są READ-ONLY, a ten skrypt nawet nie próbuje ich dotknąć — całość
liczona jest z bazy. Baza też nie jest modyfikowana (``db.connect(..., init=False)``).

Uruchamianie: ``python scripts/dedup_report.py [--db PATH] [--out-dir DIR]``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db

app = typer.Typer(
    add_completion=False,
    help="Raport deduplikacji (unique vs duplicate) i inwentarz źródeł z bazy organizera.",
)

#: Ile najgorszych grup duplikatów pokazujemy w sekcji 4.
TOP_GROUPS_LIMIT = 20


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


def _human(size: int) -> str:
    """Rozmiar po ludzku, w jednostkach binarnych (deterministycznie, bez locale).

    Ten sam styl formatowania co ``scan.py: _human_bytes`` — powielony lokalnie,
    żeby ten skrypt nie zależał od prywatnej funkcji cudzego modułu.
    """
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < 1024.0 or unit == "PiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    raise AssertionError("nieosiągalne")


# --- agregaty pomocnicze -------------------------------------------------------


def _sha_aggregates(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Dla każdego zahashowanego sha256: reprezentatywny rozmiar, liczba kopii, przykład.

    ``size`` to rozmiar reprezentatywny (MIN) wśród kopii tej treści — w
    poprawnie działającym potoku wszystkie kopie tej samej treści mają ten sam
    rozmiar, ale realne dane bywają niespójne (zepsuty re-scan, ręczna edycja
    bazy); gdy trafi się sha256 z różnymi rozmiarami kopii, funkcja i tak bierze
    MIN, ale najpierw drukuje ostrzeżenie na stderr, żeby to nie przeszło po
    cichu. ``copies`` to CAŁKOWITA liczba plików o tym sha256 (>=1, nie tylko
    duplikaty); ``example`` to najmniejsza leksykograficznie ścieżka
    ``paczka/relpath`` wśród kopii (deterministyczny wybór).
    """
    inconsistent = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM ("
            "SELECT sha256 FROM files WHERE sha256 IS NOT NULL "
            "GROUP BY sha256 HAVING MIN(size_bytes) != MAX(size_bytes))"
        ).fetchone()["n"]
    )
    if inconsistent:
        typer.echo(
            f"UWAGA: {inconsistent} treści ma kopie o różnych rozmiarach (niespójny scan)",
            err=True,
        )

    rows = conn.execute(
        "SELECT sha256, MIN(size_bytes) AS size_bytes, COUNT(*) AS copies, "
        "MIN(source_package || '/' || source_relative_path) AS example "
        "FROM files WHERE sha256 IS NOT NULL GROUP BY sha256"
    ).fetchall()
    return {
        str(row["sha256"]): {
            "size": int(row["size_bytes"]),
            "copies": int(row["copies"]),
            "example": str(row["example"]),
        }
        for row in rows
    }


def compute_summary(conn: sqlite3.Connection, agg: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Liczby sekcji 1 „Podsumowanie”."""
    totals = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS bytes FROM files"
    ).fetchone()
    files_total = int(totals["n"])
    bytes_total = int(totals["bytes"])

    # Partycja plików na trzy rozłączne zbiory sumujące się do files_total:
    # error (status='error') ma pierwszeństwo, potem hashed (sha256 wypełniony),
    # reszta to pending.
    error_count = int(
        conn.execute("SELECT COUNT(*) AS n FROM files WHERE status = 'error'").fetchone()["n"]
    )
    hashed_count = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE sha256 IS NOT NULL AND status != 'error'"
        ).fetchone()["n"]
    )
    pending_count = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE sha256 IS NULL AND status != 'error'"
        ).fetchone()["n"]
    )
    hashed_bytes = int(
        conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS b FROM files "
            "WHERE sha256 IS NOT NULL AND status != 'error'"
        ).fetchone()["b"]
    )

    unique_count = len(agg)
    unique_bytes = sum(v["size"] for v in agg.values())
    duplicate_copies = hashed_count - unique_count
    duplicate_bytes = hashed_bytes - unique_bytes
    ratio = (duplicate_bytes / hashed_bytes * 100.0) if hashed_bytes else 0.0

    return {
        "files_total": files_total,
        "bytes_total": bytes_total,
        "hashed_count": hashed_count,
        "pending_count": pending_count,
        "error_count": error_count,
        "unique_count": unique_count,
        "unique_bytes": unique_bytes,
        "duplicate_copies": duplicate_copies,
        "duplicate_bytes": duplicate_bytes,
        "ratio": ratio,
    }


def compute_per_package(
    conn: sqlite3.Connection, agg: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Wiersze sekcji 2 „Per paczka”, posortowane po bajtach malejąco."""
    packages = [
        str(row["package_name"])
        for row in conn.execute("SELECT package_name FROM source_packages ORDER BY package_name")
    ]

    sha_packages: dict[str, set[str]] = {}
    for row in conn.execute(
        "SELECT DISTINCT sha256, source_package FROM files WHERE sha256 IS NOT NULL"
    ):
        sha_packages.setdefault(str(row["sha256"]), set()).add(str(row["source_package"]))

    package_shas: dict[str, set[str]] = {}
    for sha, pkgs in sha_packages.items():
        for pkg in pkgs:
            package_shas.setdefault(pkg, set()).add(sha)

    result: list[dict[str, Any]] = []
    for package in packages:
        totals = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS bytes FROM files "
            "WHERE source_package = ?",
            (package,),
        ).fetchone()
        files_count = int(totals["n"])
        bytes_count = int(totals["bytes"])
        # Kopie liczymy TYLKO wśród zahashowanych plików tej paczki — pliki
        # oczekujące/w błędzie (sha256 NULL) nie są niczyją kopią.
        hashed_in_package = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM files WHERE source_package = ? AND sha256 IS NOT NULL",
                (package,),
            ).fetchone()["n"]
        )

        shas = package_shas.get(package, set())
        exclusive = {s for s in shas if len(sha_packages[s]) == 1}
        shared = shas - exclusive
        exclusive_bytes = sum(agg[s]["size"] for s in exclusive)
        copies = hashed_in_package - len(shas)

        result.append(
            {
                "package": package,
                "files": files_count,
                "bytes": bytes_count,
                "exclusive_count": len(exclusive),
                "exclusive_bytes": exclusive_bytes,
                "shared_count": len(shared),
                "copies": copies,
            }
        )

    result.sort(key=lambda row: (-row["bytes"], row["package"]))
    return result


def _topmost_duplicate_folders(dup_rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Filtruje foldery-duplikaty do tych NIEzagnieżdżonych pod innym duplikatem."""
    paths = {str(row["folder_path"]) for row in dup_rows}
    result = []
    for row in dup_rows:
        parts = str(row["folder_path"]).split("/")
        nested = any("/".join(parts[:i]) in paths for i in range(1, len(parts)))
        if not nested:
            result.append(row)
    return result


def compute_duplicate_folders(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    """Liczby sekcji 3 „Katalogi-duplikaty (fold_hash)”; ``None`` gdy fold_hash nie ruszał."""
    any_tree_hash = conn.execute(
        "SELECT 1 FROM folders WHERE tree_hash IS NOT NULL LIMIT 1"
    ).fetchone()
    if any_tree_hash is None:
        return None

    dup_rows = conn.execute(
        "SELECT folder_path, file_count, total_bytes, duplicate_of FROM folders "
        "WHERE duplicate_of IS NOT NULL"
    ).fetchall()
    topmost = _topmost_duplicate_folders(dup_rows)

    return {
        "folder_count": len(topmost),
        "files": sum(int(row["file_count"] or 0) for row in topmost),
        "bytes": sum(int(row["total_bytes"] or 0) for row in topmost),
        "canonical_targets": len({str(row["duplicate_of"]) for row in topmost}),
    }


def compute_top_duplicate_groups(
    agg: dict[str, dict[str, Any]], limit: int = TOP_GROUPS_LIMIT
) -> list[dict[str, Any]]:
    """Wiersze sekcji 4 „Największe grupy duplikatów”: tylko sha256 z >1 kopią."""
    groups = [
        {
            "sha256": sha,
            "size": data["size"],
            "copies": data["copies"],
            "wasted": data["size"] * (data["copies"] - 1),
            "example": data["example"],
        }
        for sha, data in agg.items()
        if data["copies"] > 1
    ]
    groups.sort(key=lambda row: (-row["wasted"], row["sha256"]))
    return groups[:limit]


def compute_kind_stats(
    conn: sqlite3.Connection, agg: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Wiersze sekcji 5 „Rodzaje treści”, posortowane po bajtach unikalnych malejąco."""
    kind_of: dict[str, str] = {
        str(row["sha256"]): str(row["content_kind"]) if row["content_kind"] is not None else "other"
        for row in conn.execute("SELECT sha256, content_kind FROM content")
    }

    per_kind: dict[str, dict[str, int]] = {}
    for sha, data in agg.items():
        kind = kind_of.get(sha, "other")
        bucket = per_kind.setdefault(kind, {"unique_count": 0, "unique_bytes": 0, "total_files": 0})
        bucket["unique_count"] += 1
        bucket["unique_bytes"] += data["size"]
        bucket["total_files"] += data["copies"]

    result = [
        {
            "kind": kind,
            "unique_count": bucket["unique_count"],
            "unique_bytes": bucket["unique_bytes"],
            "copies": bucket["total_files"] - bucket["unique_count"],
        }
        for kind, bucket in per_kind.items()
    ]
    result.sort(key=lambda row: (-row["unique_bytes"], row["kind"]))
    return result


# --- render Markdown ------------------------------------------------------------


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Buduje linie tabeli Markdown (nagłówek + separator + wiersze)."""
    lines = [f"| {' | '.join(headers)} |", f"|{'|'.join('---' for _ in headers)}|"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return lines


def render_dedup_summary(
    summary: dict[str, Any],
    per_package: list[dict[str, Any]],
    folder_dupes: Optional[dict[str, Any]],
    top_groups: list[dict[str, Any]],
    kind_stats: list[dict[str, Any]],
) -> str:
    """Renderuje pełny ``dedup_summary.md`` (deterministyczny — bez znaczników czasu)."""
    lines: list[str] = [
        "# Raport deduplikacji",
        "",
        "Generowane przez `scripts/dedup_report.py` — nie edytuj ręcznie.",
        "",
        "## Podsumowanie",
        "",
        f"- Plików razem: {summary['files_total']} ({_human(summary['bytes_total'])})",
        f"- Zahashowanych: {summary['hashed_count']}",
        f"- Oczekujących na hash: {summary['pending_count']}",
        f"- W błędzie: {summary['error_count']}",
        f"- Unikalnych treści: {summary['unique_count']} ({_human(summary['unique_bytes'])})",
        f"- Kopii-duplikatów: {summary['duplicate_copies']} ({_human(summary['duplicate_bytes'])})",
        f"- Współczynnik duplikacji: {summary['ratio']:.1f}%",
        "",
        "## Per paczka",
        "",
    ]
    lines.extend(
        _md_table(
            ["Paczka", "Pliki", "Bajty", "Unikalne (tylko tu)", "Bajty unikalne", "Współdzielone treści", "Kopie"],
            [
                [
                    row["package"],
                    str(row["files"]),
                    _human(row["bytes"]),
                    str(row["exclusive_count"]),
                    _human(row["exclusive_bytes"]),
                    str(row["shared_count"]),
                    str(row["copies"]),
                ]
                for row in per_package
            ],
        )
    )
    lines.extend(["", "## Katalogi-duplikaty (fold_hash)", ""])
    if folder_dupes is None:
        lines.append("fold_hash jeszcze nie uruchomiony.")
    else:
        lines.extend(
            [
                f"- Katalogów-duplikatów (najwyższego poziomu): {folder_dupes['folder_count']}",
                f"- Plików w nich: {folder_dupes['files']}",
                f"- Bajtów w nich: {_human(folder_dupes['bytes'])}",
                f"- Kanonicznych celów: {folder_dupes['canonical_targets']}",
            ]
        )
    lines.extend(["", "## Największe grupy duplikatów (top 20)", ""])
    lines.extend(
        _md_table(
            ["sha256 (skrót)", "Rozmiar", "Kopie", "Zmarnowane bajty", "Przykład"],
            [
                [
                    row["sha256"][:12],
                    _human(row["size"]),
                    str(row["copies"]),
                    _human(row["wasted"]),
                    row["example"],
                ]
                for row in top_groups
            ],
        )
    )
    lines.extend(["", "## Rodzaje treści", ""])
    lines.extend(
        _md_table(
            ["Rodzaj", "Unikalne treści", "Bajty unikalne", "Kopie"],
            [
                [row["kind"], str(row["unique_count"]), _human(row["unique_bytes"]), str(row["copies"])]
                for row in kind_stats
            ],
        )
    )
    return "\n".join(lines).rstrip("\n") + "\n"


# --- inwentarz (inventory.jsonl) -----------------------------------------------


def _nearest_duplicate_of(folder_path: str, dup_map: dict[str, str]) -> Optional[str]:
    """``duplicate_of`` najbliższego przodka (włącznie z samym ``folder_path``) albo ``None``."""
    parts = folder_path.split("/")
    for i in range(len(parts), 0, -1):
        candidate = "/".join(parts[:i])
        if candidate in dup_map:
            return dup_map[candidate]
    return None


def build_inventory_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Buduje wiersze inwentarza (jedna linia na plik), posortowane po (paczka, ścieżka)."""
    dup_map = {
        str(row["folder_path"]): str(row["duplicate_of"])
        for row in conn.execute(
            "SELECT folder_path, duplicate_of FROM folders WHERE duplicate_of IS NOT NULL"
        )
    }
    kind_of: dict[str, Optional[str]] = {
        str(row["sha256"]): row["content_kind"]
        for row in conn.execute("SELECT sha256, content_kind FROM content")
    }
    copies_of: dict[str, int] = {
        str(row["sha256"]): int(row["n"])
        for row in conn.execute(
            "SELECT sha256, COUNT(*) AS n FROM files WHERE sha256 IS NOT NULL GROUP BY sha256"
        )
    }

    rows: list[dict[str, Any]] = []
    for row in conn.execute(
        "SELECT source_package, source_relative_path, folder_path, size_bytes, "
        "modified_date, sha256, status FROM files "
        "ORDER BY source_package, source_relative_path"
    ):
        sha256 = row["sha256"]
        rows.append(
            {
                "package": str(row["source_package"]),
                "path": str(row["source_relative_path"]),
                "size": int(row["size_bytes"]),
                "mtime": row["modified_date"],
                "sha256": sha256,
                "kind": kind_of.get(sha256) if sha256 is not None else None,
                "status": str(row["status"]),
                "folder_dup_of": _nearest_duplicate_of(str(row["folder_path"]), dup_map),
                "copies": copies_of.get(sha256) if sha256 is not None else None,
            }
        )
    return rows


def write_inventory_jsonl(rows: list[dict[str, Any]], path: Path) -> int:
    """Zapisuje wiersze inwentarza do JSONL (jeden obiekt na linię) i zwraca ich liczbę."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


# --- CLI ------------------------------------------------------------------------


@app.command()
def report(
    db_path: Optional[Path] = typer.Option(
        None, "--db", help="Ścieżka do bazy (domyślnie z config/paths.yaml)."
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Katalog wyjściowy (domyślnie ORGANIZER_ROOT/reports)."
    ),
) -> None:
    """Liczy raport deduplikacji z bazy i zapisuje dedup_summary.md + inventory.jsonl."""
    target_db = _require_db(db_path)
    try:
        conn = db.connect(target_db, init=False)
        try:
            agg = _sha_aggregates(conn)
            summary = compute_summary(conn, agg)
            per_package = compute_per_package(conn, agg)
            folder_dupes = compute_duplicate_folders(conn)
            top_groups = compute_top_duplicate_groups(agg)
            kind_stats = compute_kind_stats(conn, agg)
            markdown = render_dedup_summary(
                summary, per_package, folder_dupes, top_groups, kind_stats
            )
            inventory_rows = build_inventory_rows(conn)
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        # z init=False walidacja schematu nie biegnie przy connect() — błąd
        # "to nie jest baza" ujawnia się dopiero na pierwszym SELECT-cie.
        typer.echo(f"{target_db}: to nie jest poprawna baza SQLite ({exc})", err=True)
        raise typer.Exit(code=1)

    target_out_dir = Path(out_dir) if out_dir is not None else config.ORGANIZER_ROOT / "reports"
    target_out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_out_dir / "dedup_summary.md"
    inventory_path = target_out_dir / "inventory.jsonl"
    summary_path.write_text(markdown, encoding="utf-8")
    written = write_inventory_jsonl(inventory_rows, inventory_path)

    typer.echo(f"raport: {summary_path}")
    typer.echo(f"inwentarz: {inventory_path} ({written} wierszy)")
    typer.echo(
        "plików: {} · unikalnych: {} · duplikaty: {} · współczynnik: {:.1f}%".format(
            summary["files_total"],
            summary["unique_count"],
            _human(summary["duplicate_bytes"]),
            summary["ratio"],
        )
    )


if __name__ == "__main__":
    app()
