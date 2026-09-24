"""B6: relacje podobieństwa dla jednego przedmiotu (albo całego indeksu).

Kontrakt:

- wejście — podpisy policzone w etapie extract (B2): ``normalized_text_hash``,
  ``simhash``, ``perceptual_hash`` w tabeli ``files``. Zakres bierzemy z manifestu
  przedmiotu (B1) albo, z ``--all``, z całego indeksu;
- wyjście — wiersze w tabeli ``relations`` (źródło prawdy) oraz ich deterministyczny
  eksport ``relations.jsonl`` obok manifestu (ślad w gicie, wsad dla review B9
  i pól ``related_to``/``relation`` w planie B7);
- progi — ``config/thresholds.yaml: near_duplicate``.

Zapis jest **podmianą własnego wycinka**: kasujemy wyłącznie wiersze z
``detection_method`` zaczynającym się od ``near_dupe:``, i tylko dla par, których obie
strony należą do przetwarzanego zbioru. Relacje ręczne (B14) i cudze metody zostają
nietknięte, a ponowny przebieg po zmianie progów nie zostawia po sobie nieaktualnych
par — to ten sam wymóg, który dostał zapis decyzji klasyfikacyjnych do bazy.

Ten etap niczego nie kasuje z materiałów, nie oznacza ``outdated`` (reguła twarda
nr 10) i nie wykonuje ``apply``.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db
from orglib.classify import detect_year
from orglib.jsonl import read_jsonl, write_atomic
from orglib.near_dupe import METHOD_PREFIX, Relation, Signature, build_relations

app = typer.Typer(add_completion=False, help=__doc__)

EXPORT_NAME = "relations.jsonl"


def load_signatures(
    conn: sqlite3.Connection, wanted: set[str] | None
) -> list[Signature]:
    """Podpisy per TREŚĆ (jedna treść = jeden wiersz), z rokiem ze ścieżek źródłowych.

    Podpisy leżą w ``files``, więc ta sama treść ma ich tyle, ile kopii. Biorą się
    z zawartości, więc są identyczne — bierzemy pierwszą niepustą wartość, a rok
    liczymy ze WSZYSTKICH ścieżek tej treści (jedna kopia bywa w katalogu bez roku).
    """
    signatures: dict[str, dict[str, Any]] = {}
    paths: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute(
        "SELECT sha256, source_package, source_relative_path, normalized_text_hash, "
        "simhash, perceptual_hash FROM files WHERE sha256 IS NOT NULL "
        "ORDER BY source_package, source_relative_path"
    ):
        sha = str(row["sha256"])
        if wanted is not None and sha not in wanted:
            continue
        entry = signatures.setdefault(sha, {})
        for column in ("normalized_text_hash", "simhash", "perceptual_hash"):
            if not entry.get(column) and row[column]:
                entry[column] = str(row[column])
        paths[sha].append(f"{row['source_package']}/{row['source_relative_path']}")
    return [
        Signature(
            sha256=sha,
            normalized_text_hash=entry.get("normalized_text_hash"),
            simhash=entry.get("simhash"),
            perceptual_hash=entry.get("perceptual_hash"),
            year=detect_year(paths[sha]),
        )
        for sha, entry in sorted(signatures.items())
    ]


def replace_own_relations(
    conn: sqlite3.Connection, relations: list[Relation], scope: set[str]
) -> int:
    """Podmienia wycinek: kasuje własne pary z zakresu, wstawia nowe. Zwraca liczbę skasowanych.

    Filtrowanie po przynależności do ``scope`` robimy w Pythonie, a nie przez ``IN (…)``
    z tysiącami parametrów — SQLite ma limit zmiennych w zapytaniu, a lista treści
    jednego przedmiotu potrafi mieć ich kilka tysięcy.
    """
    stale = [
        (row["source_sha256"], row["target_sha256"], row["relation_type"])
        for row in conn.execute(
            "SELECT source_sha256, target_sha256, relation_type FROM relations "
            "WHERE detection_method LIKE ?",
            (f"{METHOD_PREFIX}:%",),
        )
        if row["source_sha256"] in scope and row["target_sha256"] in scope
    ]
    with conn:
        conn.executemany(
            "DELETE FROM relations WHERE source_sha256 = ? AND target_sha256 = ? "
            "AND relation_type = ?",
            stale,
        )
        for relation in relations:
            db.upsert_relation(conn, relation.as_row())
    return len(stale)


def write_export(relations: list[Relation], output: Path) -> None:
    """Deterministyczny eksport (posortowany), żeby diff w gicie był czytelny."""
    write_atomic(
        ({"schema_version": 1, **relation.as_row()} for relation in relations),
        output,
        prefix=".relations-",
    )


@app.command()
def relate(
    semester: Optional[int] = typer.Option(None, "--semester", min=1, max=7),
    skrot: Optional[str] = typer.Option(None, "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Domyślnie manifest_slice.jsonl z prepare_subject.py."
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Katalog eksportu; domyślnie katalog manifestu."
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    take_all: bool = typer.Option(
        False, "--all", help="Cały indeks zamiast jednego przedmiotu (wymaga --out-dir)."
    ),
    max_bucket: int = typer.Option(
        1000, "--max-bucket", min=2, help="Bezpiecznik: pomiń kubełek kandydatów większy niż N."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Policz relacje i pokaż podsumowanie; nie zapisuj."
    ),
) -> None:
    """Znajdź near-dupe i starsze wersje; nigdy nie kasuj i nie oznaczaj outdated."""
    from prepare_subject import default_output as manifest_default

    try:
        paths = config.load_paths()
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")
        config.check_output_target(database, paths, symlink_ok=True)

        subject = None
        wanted: set[str] | None = None
        if take_all:
            if out_dir is None:
                raise ValueError("--all wymaga --out-dir (eksport nie należy do żadnego przedmiotu)")
            target_dir = out_dir
        else:
            if semester is None or skrot is None:
                raise ValueError("podaj --semester i --skrot albo użyj --all")
            subjects = config.iter_subjects()
            subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
            manifest_path = manifest or manifest_default(subject, subjects)
            if not manifest_path.is_file():
                raise ValueError(
                    f"brak manifestu: {manifest_path} — najpierw `just subject-prepare`"
                )
            rows = read_jsonl(manifest_path)
            wanted = {str(row["sha256"]) for row in rows if row.get("sha256")}
            target_dir = out_dir if out_dir is not None else manifest_path.parent
        export_path = target_dir / EXPORT_NAME
        config.check_output_target(export_path, paths)

        thresholds = config.load_thresholds().get("near_duplicate") or {}
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        version = db.current_schema_version(conn)
        if version != db.SCHEMA_VERSION:
            typer.echo(
                f"Błąd: nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}",
                err=True,
            )
            raise typer.Exit(code=1)
        signatures = load_signatures(conn, wanted)
    finally:
        conn.close()

    relations, stats = build_relations(
        signatures, thresholds=thresholds, max_bucket=max_bucket
    )
    with_signature = sum(
        1 for s in signatures if s.normalized_text_hash or s.simhash or s.perceptual_hash
    )
    scope = "cały indeks" if take_all else (
        f"SEM{subject.semester}/{subject.grupa}/{subject.skrot}"  # type: ignore[union-attr]
    )
    kinds: dict[str, int] = defaultdict(int)
    for relation in relations:
        kinds[relation.relation_type] += 1

    typer.echo(f"zakres: {scope} · treści: {len(signatures)} · z podpisem: {with_signature}")
    typer.echo(
        f"relacje: {len(relations)} · "
        f"{', '.join(f'{k}={v}' for k, v in sorted(kinds.items())) or 'brak'} · "
        f"trafienia warstw: tekst={stats['normalized_text']}, simhash={stats['simhash']}, "
        f"phash={stats['phash']}"
    )
    if stats.get("phash_odrzucone_tekstem"):
        # Widoczne w podsumowaniu, bo to jedyny moment, w którym widać, ile par
        # „zgodne piksele, inna treść" odsiał OCR (Q5).
        typer.echo(
            f"obrazy odrzucone przez niezgodny tekst: {stats['phash_odrzucone_tekstem']}"
        )
    if with_signature == 0 and signatures:
        typer.echo(
            "UWAGA: żadna treść nie ma podpisów — uruchom najpierw `just extract`", err=True
        )
    if stats["skipped_buckets"]:
        typer.echo(
            f"UWAGA: pominięto {stats['skipped_buckets']} kubełków kandydatów powyżej "
            f"--max-bucket={max_bucket}; część relacji mogła nie zostać znaleziona",
            err=True,
        )

    if dry_run:
        typer.echo("dry-run: nic nie zapisano")
        return

    try:
        conn = db.connect(database)
        try:
            removed = replace_own_relations(conn, relations, {s.sha256 for s in signatures})
        finally:
            conn.close()
        write_export(relations, export_path)
    except (OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd zapisu: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"relations: zapisane {len(relations)}, usunięte nieaktualne {removed}")
    typer.echo(f"eksport: {export_path}")


if __name__ == "__main__":
    app()
