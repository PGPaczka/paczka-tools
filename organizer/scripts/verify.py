"""B11: kontrola po `apply` — czy w paczce leży dokładnie to, co mówi plan.

Liczy hash KAŻDEGO skopiowanego pliku i porównuje go z ``source_sha256`` z planu,
a potem sprawdza, czy pod katalogiem przedmiotu nie ma plików, których nie tłumaczy
ani plan, ani ground truth. Dopiero zielony `verify` uprawnia do commitu materiałów
(``AGENTS.md``: „commit dopiero po pomyślnym verify”).

Materiałów nie dotyka: czyta pliki i zapisuje raport oraz statusy w bazie.

Kody wyjścia: ``0`` paczka zgadza się z planem, ``2`` NIE zgadza się (nie commituj),
``1`` błąd przygotowania. ``--strict`` traktuje pliki spoza planu jak błąd.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from orglib import config, db, plan_gate, plan_verify
from orglib.plan_build import plan_hash

app = typer.Typer(add_completion=False, help=__doc__)

REPORT_NAME = "verification.jsonl"
_PLAN_CANDIDATES = ("plan.jsonl",)

#: Prefiks, którym `scan_target` oznacza w tabeli `applied` materiał ułożony ręcznie.
GROUND_TRUTH_PREFIX = "ground_truth:"


@app.command()
def verify(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    plan: list[Path] = typer.Option([], "--plan", help="Domyślnie plan.jsonl obok manifestu."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    expect_hash: Optional[str] = typer.Option(
        None, "--expect-hash", help="Sprawdzaj tylko plan o tym odcisku."
    ),
    no_db: bool = typer.Option(False, "--no-db", help="Nie zapisuj statusów (sama kontrola)."),
    strict: bool = typer.Option(False, "--strict", help="Pliki spoza planu też blokują."),
    show: int = typer.Option(20, "--show", min=0, help="Ile pozycji wypisać na stdout."),
) -> None:
    """Sprawdź, że paczka zgadza się z planem; kod 2 = nie commituj materiałów."""
    from prepare_subject import default_output as manifest_default

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()
        base = manifest_default(subject, subjects).parent
        plans = list(plan) or [base / name for name in _PLAN_CANDIDATES if (base / name).is_file()][:1]
        if not plans:
            raise ValueError(f"brak planu w {base} — uruchom `just subject-plan` albo podaj --plan")
        missing = [str(path) for path in plans if not path.is_file()]
        if missing:
            raise ValueError(f"brak pliku planu: {', '.join(missing)}")

        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")

        rows, _ = plan_gate.read_plan(plans)
        digest = plan_hash(rows)
        if expect_hash and expect_hash != digest:
            raise ValueError(
                f"plan ma odcisk {digest[:12]}…, a oczekiwano {expect_hash[:12]}…"
            )
        report_path = plans[0].parent / REPORT_NAME
        config.check_output_target(report_path, paths)
    except (KeyError, ValueError, OSError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    conn = db.connect(database)
    try:
        ground_truth = [
            str(row["target_relative_path"])
            for row in conn.execute(
                "SELECT target_relative_path FROM applied WHERE plan_hash LIKE ?",
                (f"{GROUND_TRUTH_PREFIX}%",),
            )
        ]
        checks = plan_verify.check_rows(rows, paths=paths)
        extras = plan_verify.tree_extras(
            rows, paths=paths, subject=subject, ground_truth=ground_truth
        )
        counts = plan_verify.summarize([*checks, *extras])
        failing = sum(1 for check in checks if check.failing)

        typer.echo(
            f"plan: {', '.join(str(p) for p in plans)} · odcisk {digest[:12]}… · "
            f"sprawdzone: {len(checks)} · zgodne: {counts['ok']}"
        )
        typer.echo(
            f"braki: {counts['missing']} · niezgodne treści: {counts['mismatch']} · "
            f"pliki spoza planu: {counts['extra']}"
        )
        for check in [*(c for c in checks if c.failing), *extras][:show]:
            typer.echo(f"  {check.state.upper()}: {check.target_rel} — {check.detail}")

        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8") as handle:
                for check in [*checks, *extras]:
                    handle.write(json.dumps(check.as_row(), ensure_ascii=False, sort_keys=True) + "\n")
        except OSError as exc:
            typer.echo(f"Błąd zapisu raportu: {exc}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"raport: {report_path}")

        blocking = failing + (counts["extra"] if strict else 0)
        if blocking:
            typer.echo(
                f"PACZKA NIE ZGADZA SIĘ Z PLANEM: {blocking} pozycji — nie commituj materiałów",
                err=True,
            )
            raise typer.Exit(code=2)

        if not no_db:
            for check in checks:
                db.upsert_plan_item(conn, {
                    "sha256": check.sha256,
                    "target_relative_path": check.target_rel,
                    "action": "copy",
                    "status": "verified",
                    "plan_run_id": digest,
                })
                for row in conn.execute(
                    "SELECT file_id, status FROM files WHERE sha256 = ?", (check.sha256,)
                ).fetchall():
                    if str(row["status"]) in ("verified", db.ERROR_STATUS):
                        continue
                    db.advance_status(conn, int(row["file_id"]), "verified")
    finally:
        conn.close()

    typer.echo("paczka zgadza się z planem — materiały można zacommitować na gałęzi przedmiotu")


if __name__ == "__main__":
    app()
