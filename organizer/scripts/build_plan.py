"""B7: jeden plan przedmiotu — z decyzji reguł, modelu i relacji.

Kontrakt:

- wejście — ``plan.det.jsonl`` (B3), opcjonalnie ``plan.ai.jsonl`` (B5), opcjonalnie
  ``relations.jsonl`` (B6) oraz ``manifest_slice.jsonl`` (B1), z którego bierzemy
  ścieżki źródłowe potrzebne do rozstrzygania kolizji;
- wyjście — ``plan.jsonl`` obok manifestu: pierwsza linia to nagłówek ``{"_meta": …}``
  z ``plan_hash``, dalej po jednej decyzji na treść (``prompts/plan_line.schema.json``);
- baza — decyzje trafiają do ``classifications``, a pozycje planu do ``plan_items``
  (decyzja użytkownika 2026-09-19: **baza jest źródłem prawdy, JSONL jej eksportem**).

Zapis do bazy jest podmianą wycinka jednego przedmiotu i **nigdy nie dotyka wierszy
ground truth** (``run_id='ground_truth'``): klucz tabeli to samo ``sha256``, więc bez tej
reguły plan skasowałby jedyny zapis o tym, że materiał już leży w paczce.

Sam plan niczego nie kopiuje. Bramką przed `apply` jest ``validate_plan.py`` (B8),
a zgodę wydaje człowiek.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db
from orglib.jsonl import read_jsonl, write_atomic
from orglib.plan_build import META_KEY, build

app = typer.Typer(add_completion=False, help=__doc__)

PLAN_NAME = "plan.jsonl"
GROUND_TRUTH_RUN_ID = "ground_truth"


def _load_optional(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path) if path.is_file() else []


def _decision_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Odsiewa nagłówek ``_meta``, gdy ktoś poda na wejściu gotowy plan."""
    return [row for row in rows if META_KEY not in row]


def write_to_database(
    database: Path,
    *,
    rows: list[dict[str, Any]],
    semester: int,
    subject_key: str,
    run_id: str,
    decided_at: str,
) -> dict[str, int]:
    """Podmienia wycinek przedmiotu w ``classifications`` i ``plan_items``.

    Zwraca liczniki do podsumowania. Treści opisane już przez ground truth pomijamy:
    ich wiersz mówi, gdzie leżą w paczce, i jest cenniejszy niż powtórzenie decyzji
    „pomiń, bo już jest”.
    """
    conn = db.connect(database)
    try:
        protected = {
            str(row["sha256"])
            for row in conn.execute(
                "SELECT sha256 FROM classifications WHERE run_id = ?", (GROUND_TRUTH_RUN_ID,)
            )
        }
        shas = [str(row["source_sha256"]) for row in rows]
        conn.execute("BEGIN")
        try:
            conn.execute(
                "DELETE FROM classifications WHERE semester = ? AND subject_key = ? AND run_id <> ?",
                (semester, subject_key, GROUND_TRUTH_RUN_ID),
            )
            conn.executemany(
                "DELETE FROM plan_items WHERE sha256 = ? AND plan_run_id LIKE 'plan:%'",
                [(sha,) for sha in shas],
            )
            written = 0
            for row in rows:
                sha = str(row["source_sha256"])
                if sha not in protected:
                    conn.execute(
                        "INSERT INTO classifications (sha256, semester, subject_key, year, category,"
                        " target_relative_path, is_outdated, classification_method, confidence,"
                        " model_name, run_id, decided_at, action, reason, needs_review)"
                        " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            sha, semester, subject_key, row.get("year"), row.get("category"),
                            row.get("target_rel"), row.get("method"), row.get("confidence"),
                            row.get("model"), run_id, decided_at, row.get("action"),
                            row.get("reason"), int(bool(row.get("needs_review"))),
                        ),
                    )
                    written += 1
                conn.execute(
                    "INSERT INTO plan_items (sha256, target_relative_path, action, status, plan_run_id)"
                    " VALUES (?, ?, ?, 'planned', ?)"
                    " ON CONFLICT (sha256, target_relative_path) DO UPDATE SET"
                    " action = excluded.action, status = excluded.status,"
                    " plan_run_id = excluded.plan_run_id",
                    (sha, row.get("target_rel"), row.get("action"), run_id),
                )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        return {"classifications": written, "ground_truth_kept": len(set(shas) & protected),
                "plan_items": len(rows)}
    finally:
        conn.close()


@app.command()
def build_plan(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Domyślnie manifest_slice.jsonl z prepare_subject.py."
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Katalog wyjściowy; domyślnie katalog manifestu."
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    no_db: bool = typer.Option(False, "--no-db", help="Nie zapisuj do bazy (sam eksport JSONL)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Policz i pokaż; nic nie zapisuj."),
) -> None:
    """Scal decyzje w jeden plan; nie kopiuj materiałów i nie wykonuj apply."""
    from prepare_subject import default_output as manifest_default

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()

        manifest_path = manifest or manifest_default(subject, subjects)
        if not manifest_path.is_file():
            raise ValueError(f"brak manifestu: {manifest_path} — najpierw `just subject-prepare`")
        base = manifest_path.parent
        det_path = base / "plan.det.jsonl"
        if not det_path.is_file():
            raise ValueError(
                f"brak planu deterministycznego: {det_path} — najpierw `just subject-classify`"
            )
        ai_path = base / "plan.ai.jsonl"
        relations_path = base / "relations.jsonl"

        target_dir = out_dir if out_dir is not None else base
        plan_path = target_dir / PLAN_NAME
        config.check_output_target(plan_path, paths)

        manifest_rows = read_jsonl(manifest_path)
        source_paths = {
            str(row["sha256"]): str(row.get("source_path") or "")
            for row in manifest_rows
            if row.get("sha256")
        }
        deterministic = _decision_rows(read_jsonl(det_path))
        ai_rows = _decision_rows(_load_optional(ai_path))
        relations = _load_optional(relations_path)

        result = build(
            deterministic=deterministic,
            ai=ai_rows,
            relations=relations,
            source_paths=source_paths,
            subject_key=subject.skrot,
            semester=subject.semester,
            grupa=subject.grupa,
            target_dir=subject.target_dir,
            inputs={
                det_path.name: len(deterministic),
                ai_path.name: len(ai_rows),
                relations_path.name: len(relations),
            },
            created_at=db.now_iso(),
        )
    except (KeyError, ValueError, OSError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    meta = result.meta
    typer.echo(
        f"przedmiot: SEM{subject.semester}/{subject.grupa}/{subject.skrot} · "
        f"wejście: {', '.join(f'{k}={v}' for k, v in meta['inputs'].items())}"
    )
    typer.echo(
        f"plan: {meta['items']} pozycji · "
        f"akcje: {', '.join(f'{k}={v}' for k, v in meta['actions'].items())} · "
        f"needs_review: {meta['needs_review']} · z relacją: {meta['with_relation']}"
    )
    typer.echo(
        f"kolizje rozstrzygnięte katalogiem źródłowym: {meta['disambiguated']} · "
        f"konflikty decyzji: {meta['conflicts']} · plan_hash: {meta['plan_hash'][:12]}…"
    )
    for note in result.disambiguated[:5]:
        typer.echo(f"  {note['from']} → {note['to']}")
    for conflict in result.conflicts[:5]:
        typer.echo(
            f"  KONFLIKT {conflict['source_sha256'][:12]}…: zostaje {conflict['kept']}, "
            f"odrzucone {conflict['dropped']}"
        )

    if dry_run:
        typer.echo("dry-run: nic nie zapisano")
        return

    try:
        write_atomic(result.as_lines(), plan_path, prefix=".plan-")
    except OSError as exc:
        typer.echo(f"Błąd zapisu planu: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"plan: {plan_path}")

    if no_db:
        typer.echo("baza pominięta (--no-db): plan istnieje tylko jako plik")
        return
    try:
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — użyj --no-db albo wykonaj first-pass")
        config.check_output_target(database, paths, symlink_ok=True)
        counts = write_to_database(
            database,
            rows=result.rows,
            semester=subject.semester,
            subject_key=subject.skrot,
            run_id=f"plan:{meta['plan_hash'][:12]}",
            decided_at=meta["created_at"],
        )
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd zapisu do bazy: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"baza: classifications={counts['classifications']} "
        f"(ground truth nietknięty: {counts['ground_truth_kept']}), "
        f"plan_items={counts['plan_items']}"
    )


if __name__ == "__main__":
    app()
