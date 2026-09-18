"""B8: bramka przed `apply` — sprawdza plan i pokazuje, co zrobiłby z drzewem.

Kontrakt:

- wejście — jeden albo kilka plików planu (``plan.jsonl`` z B7, a do czasu jego
  powstania ``plan.det.jsonl`` z B3 i ``plan.ai.jsonl`` z B5); linie muszą być zgodne
  z ``prompts/plan_line.schema.json``;
- wyjście — ``validation.jsonl`` obok planu (ustalenia dla review B9) i podsumowanie
  na stdout, w tym **dry-run diff**: ile plików i katalogów plan dołożyłby do paczki;
- kod wyjścia — ``0`` plan przechodzi, ``2`` plan ma błędy i **nie wolno go wykonać**,
  ``1`` błąd przygotowania (brak pliku, nieznany przedmiot). ``--strict`` traktuje
  ostrzeżenia jak błędy.

Bazę czyta wyłącznie po ground truth (tabela ``applied``), żeby wiedzieć, pod którymi
ścieżkami leży już ręcznie ułożony materiał. Niczego nie zapisuje do bazy i nie dotyka
materiałów — to jest kontrola, nie naprawa.
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
from orglib.classify import load_rules
from orglib.plan_lint import Finding, summarize, tree_diff, validate_rows

app = typer.Typer(add_completion=False, help=__doc__)

REPORT_NAME = "validation.jsonl"

#: Kolejność szukania planu, gdy nie podano `--plan`. B7 jeszcze nie istnieje, więc
#: do tego czasu sensownym domyślnym wejściem jest plan deterministyczny z B3.
_PLAN_CANDIDATES = ("plan.jsonl", "plan.det.jsonl")

_SCHEMA_PATH = config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json"
_MEDIA_ROOT = "90_MEDIA"


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


def load_ground_truth(database: Path) -> dict[str, str]:
    """Ścieżka docelowa → sha256 tego, co już leży w paczce (zapisał `scan_target`)."""
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        version = db.current_schema_version(conn)
        if version != db.SCHEMA_VERSION:
            raise ValueError(
                f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}"
            )
        return {
            str(row["target_relative_path"]): str(row["sha256"])
            for row in conn.execute("SELECT target_relative_path, sha256 FROM applied")
        }
    finally:
        conn.close()


def write_report(findings: list[Finding], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=".validation-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for finding in findings:
                handle.write(json.dumps(finding.as_row(), ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@app.command()
def validate(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    plan: list[Path] = typer.Option(
        [], "--plan", help="Plik planu; można podać kilka (det + ai). Domyślnie plan.jsonl albo plan.det.jsonl."
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    no_ground_truth: bool = typer.Option(
        False, "--no-ground-truth", help="Pomiń kontrolę nadpisania tego, co już leży w paczce."
    ),
    report: Optional[Path] = typer.Option(
        None, "--report", help=f"Gdzie zapisać ustalenia; domyślnie {REPORT_NAME} obok planu."
    ),
    strict: bool = typer.Option(False, "--strict", help="Ostrzeżenia też blokują."),
    show: int = typer.Option(20, "--show", min=0, help="Ile ustaleń wypisać na stdout."),
) -> None:
    """Sprawdź plan; kod wyjścia różny od zera ma zatrzymać `apply`."""
    from prepare_subject import default_output as manifest_default

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()
        base = manifest_default(subject, subjects).parent

        plans = list(plan)
        if not plans:
            plans = [base / name for name in _PLAN_CANDIDATES if (base / name).is_file()][:1]
        if not plans:
            raise ValueError(
                f"brak planu w {base} — uruchom `just subject-classify` albo podaj --plan"
            )
        missing = [str(path) for path in plans if not path.is_file()]
        if missing:
            raise ValueError(f"brak pliku planu: {', '.join(missing)}")

        rows: list[dict[str, Any]] = []
        for path in plans:
            rows.extend(read_jsonl(path))
        report_path = report if report is not None else plans[0].parent / REPORT_NAME
        config.check_output_target(report_path, paths)

        ground_truth: dict[str, str] = {}
        if not no_ground_truth:
            database = db_path if db_path is not None else paths.work_db
            if not database.is_file():
                raise ValueError(
                    f"brak bazy: {database} — użyj --no-ground-truth albo wykonaj first-pass"
                )
            ground_truth = load_ground_truth(database)

        rules = load_rules()
        thresholds = config.load_thresholds().get("confidence") or {}
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    findings: list[Finding] = []
    for number, row in enumerate(rows, start=1):
        try:
            jsonschema.validate(row, schema)
        except jsonschema.ValidationError as exc:
            findings.append(Finding(
                "error", "schemat", f"linia {number}: {exc.message}",
                source_sha256=str(row.get("source_sha256") or "") or None,
                target_rel=str(row.get("target_rel") or "") or None,
            ))
    findings.extend(validate_rows(
        rows,
        subject=subject,
        rules=rules,
        auto_apply=float(thresholds.get("auto_apply", 0.90)),
        review_min=float(thresholds.get("review_min", 0.70)),
        media_root=_MEDIA_ROOT,
        ground_truth=ground_truth,
    ))

    counts = summarize(findings)
    diff = tree_diff(rows)
    actions = Counter(str(row.get("action")) for row in rows)
    review = sum(1 for row in rows if row.get("needs_review"))

    typer.echo(
        f"plan: {', '.join(str(p) for p in plans)} · pozycje: {len(rows)} · "
        f"akcje: {', '.join(f'{k}={v}' for k, v in sorted(actions.items())) or 'brak'} · "
        f"needs_review: {review}"
    )
    typer.echo(
        f"dry-run: {len(diff['files'])} plików w {len(diff['folders'])} katalogach "
        f"pod {subject.target_dir}"
    )
    typer.echo(f"ustalenia: błędy {counts['error']}, ostrzeżenia {counts['warning']}")
    by_code = Counter(f"{f.level}:{f.code}" for f in findings)
    for code, count in sorted(by_code.items()):
        typer.echo(f"  {code}: {count}")
    for finding in findings[:show]:
        where = f" [{finding.target_rel}]" if finding.target_rel else ""
        typer.echo(f"  {finding.level.upper()} {finding.code}: {finding.message}{where}")
    if len(findings) > show:
        typer.echo(f"  … i {len(findings) - show} więcej — pełna lista w raporcie")

    try:
        write_report(findings, report_path)
    except OSError as exc:
        typer.echo(f"Błąd zapisu raportu: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"raport: {report_path}")

    blocking = counts["error"] + (counts["warning"] if strict else 0)
    if blocking:
        typer.echo(f"PLAN ODRZUCONY: {blocking} blokujących ustaleń — nie wykonuj apply", err=True)
        raise typer.Exit(code=2)
    typer.echo("plan przechodzi walidację")


if __name__ == "__main__":
    app()
