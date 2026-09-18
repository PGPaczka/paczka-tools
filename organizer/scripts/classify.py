"""B3: klasyfikacja deterministyczna i heurystyczna jednego przedmiotu, bez AI i bez kosztu.

Kontrakt:

- wejście — ``reports/.../manifest_slice.jsonl`` z ``prepare_subject.py`` (B1); jedna
  linia = jedna **treść** (sha256) wraz z prowenancją i głową tekstu z etapu extract (B2);
- wyjście obok manifestu:
  ``plan.det.jsonl``  — decyzje reguł, zgodne z ``prompts/plan_line.schema.json``,
  ``unresolved.jsonl`` — to, czego reguły nie rozstrzygnęły, w kształcie manifestu
  (można je podać wprost jako ``--manifest`` do ``ai_resolve.py``);
- baza czytana WYŁĄCZNIE po to, żeby poznać ground truth (``classifications`` z
  ``run_id='ground_truth'``, czyli treści już leżące w paczce). Nic nie zapisuje.

Świadomie **nie** zmienia statusów w bazie. Decyzja klasyfikacyjna jest tania i w pełni
odtwarzalna z manifestu (żadnego wywołania modelu, żadnego czytania materiałów), więc
plan tekstowy jest tu jedynym potrzebnym stanem — a review człowieka (B9) i ``apply``
(B10) mają pracować na jednym, przeglądalnym artefakcie, nie na dwóch rozjeżdżających
się źródłach prawdy. Zapisy do ``classifications``/``plan_items`` należą do etapów,
które faktycznie ruszają materiały.

Ten etap nie wykonuje ``apply`` i nie dotyka materiałów (AGENTS.md, reguły twarde).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import jsonschema
import typer

from orglib import config, db
from orglib.classify import GroundTruth, classify_row, load_rules, unambiguous_labels

app = typer.Typer(add_completion=False, help=__doc__)

#: Nazwa wpisywana przez ``scan_target.py`` w ``classifications.run_id`` dla ground truth.
GROUND_TRUTH_RUN_ID = "ground_truth"

_SCHEMA_PATH = config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json"

PLAN_NAME = "plan.det.jsonl"
UNRESOLVED_NAME = "unresolved.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: niepoprawny JSON ({exc})") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: linia nie jest obiektem JSON")
            rows.append(row)
    return rows


def load_ground_truth(database: Path) -> dict[str, GroundTruth]:
    """Treści leżące już w paczce — czytane read-only, bez tworzenia bazy."""
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        version = db.current_schema_version(conn)
        if version != db.SCHEMA_VERSION:
            raise ValueError(
                f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}"
            )
        rows = conn.execute(
            "SELECT sha256, semester, subject_key, category, target_relative_path, is_outdated "
            "FROM classifications WHERE run_id = ?",
            (GROUND_TRUTH_RUN_ID,),
        ).fetchall()
    finally:
        conn.close()
    return {
        str(row["sha256"]): GroundTruth(
            target_relative_path=str(row["target_relative_path"] or ""),
            semester=int(row["semester"]) if row["semester"] is not None else None,
            subject_key=str(row["subject_key"]) if row["subject_key"] is not None else None,
            category=str(row["category"]) if row["category"] is not None else None,
            is_outdated=bool(row["is_outdated"]),
        )
        for row in rows
        if row["target_relative_path"]
    }


def write_atomic(rows: list[dict[str, Any]], output: Path) -> None:
    """Nadpisuje wynik w całości — etap jest deterministyczny, więc nie dopisuje."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=".classify-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@app.command()
def classify(
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
    no_ground_truth: bool = typer.Option(
        False, "--no-ground-truth", help="Pomiń odczyt bazy (klasyfikacja bez wiedzy o paczce)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Policz decyzje i pokaż podsumowanie; nie zapisuj plików."
    ),
) -> None:
    """Rozstrzygnij regułami, co się da; resztę zostaw AI (B5) i człowiekowi."""
    from prepare_subject import default_output as manifest_default  # wspólna konwencja ścieżek

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()

        manifest_path = manifest or manifest_default(subject, subjects)
        if not manifest_path.is_file():
            raise ValueError(f"brak manifestu: {manifest_path} — najpierw `just subject-prepare`")
        target_dir = out_dir if out_dir is not None else manifest_path.parent
        plan_path = target_dir / PLAN_NAME
        unresolved_path = target_dir / UNRESOLVED_NAME
        for output in (plan_path, unresolved_path):
            config.check_output_target(output, paths)

        ground_truth: dict[str, GroundTruth] = {}
        if not no_ground_truth:
            database = db_path if db_path is not None else paths.work_db
            if not database.is_file():
                raise ValueError(
                    f"brak bazy: {database} — użyj --no-ground-truth albo wykonaj first-pass"
                )
            config.check_output_target(database, paths, symlink_ok=True)
            ground_truth = load_ground_truth(database)

        rules = load_rules()
        safe_labels = unambiguous_labels(subject, subjects)
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        rows = read_jsonl(manifest_path)
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    decisions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    actions: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    review = 0
    seen: set[str] = set()
    failed: list[tuple[str, str]] = []

    for row in rows:
        sha = str(row.get("sha256") or row.get("source_sha256") or "")
        if sha in seen:
            continue  # jedna treść = jedna decyzja (jak w ai_resolve.py)
        seen.add(sha)
        try:
            outcome = classify_row(
                row,
                subject=subject,
                rules=rules,
                ground_truth=ground_truth,
                safe_labels=safe_labels,
            )
            if outcome.decision is not None:
                jsonschema.validate(outcome.decision, schema)
        except (ValueError, KeyError, jsonschema.ValidationError) as exc:
            failed.append((sha or "(bez sha256)", str(exc)))
            continue
        if outcome.decision is not None:
            decisions.append(outcome.decision)
            actions[outcome.decision["action"]] += 1
            categories[outcome.decision["category"]] += 1
            review += bool(outcome.decision["needs_review"])
        if outcome.unresolved is not None:
            unresolved.append(outcome.unresolved)

    typer.echo(
        f"przedmiot: SEM{subject.semester}/{subject.grupa}/{subject.skrot} · "
        f"manifest: {len(rows)} · treści: {len(seen)} · ground truth: {len(ground_truth)}"
    )
    typer.echo(
        f"rozstrzygnięte: {len(decisions)} · "
        f"akcje: {', '.join(f'{k}={v}' for k, v in sorted(actions.items())) or 'brak'} · "
        f"needs_review: {review} · unresolved (do AI): {len(unresolved)} · błędy: {len(failed)}"
    )
    if categories:
        typer.echo("kategorie: " + ", ".join(f"{k}={v}" for k, v in sorted(categories.items())))
    for sha, message in failed[:10]:
        typer.echo(f"  BŁĄD {sha[:12]}… {message}", err=True)

    if dry_run:
        typer.echo("dry-run: nic nie zapisano")
    else:
        try:
            write_atomic(decisions, plan_path)
            write_atomic(unresolved, unresolved_path)
        except OSError as exc:
            typer.echo(f"Błąd zapisu: {exc}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"plan deterministyczny: {plan_path}")
        typer.echo(f"do rozstrzygnięcia przez AI: {unresolved_path}")

    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
