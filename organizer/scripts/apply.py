"""B10: wykonanie zaakceptowanego planu — kopiowanie materiałów do repo paczki.

To jest jedyny etap, który zapisuje materiały, więc kontrakt jest wąski:

- **domyślnie nic nie robi.** Bez ``--yes`` liczy i pokazuje, co by zrobił
  (dry-run). Zgoda człowieka dotyczy KONKRETNEGO planu — ``--expect-hash``
  przypina wykonanie do odcisku, który został zaakceptowany;
- **bramka B8 jest wykonywana tutaj ponownie**, tym samym kodem
  (``orglib.plan_gate``). Plan z błędami kończy się kodem 2 i zero kopii;
- pracujemy na branchu ``subject/{SKROT}`` w repo docelowym, przy czystym drzewie
  ``paczka/`` — inaczej nie da się rzetelnie powiedzieć, co dołożył `apply`;
- **snapshot przed zapisem**: `reports/{SKROT}/apply_snapshot.json` z HEAD repo,
  odciskiem planu i listą operacji. Powstaje ZANIM cokolwiek zostanie skopiowane;
- nic nie jest nadpisywane ani kasowane: plik o innej treści pod ścieżką docelową
  to odmowa, plik o tej samej treści to „już jest” i przebieg idzie dalej;
- **commita nie robimy** — należy do człowieka po `verify` (B11).

Kody wyjścia: ``0`` wykonane albo dry-run bez zastrzeżeń, ``2`` odmowa (plan
odrzucony, brudne drzewo, kolizja treści, brak źródła), ``1`` błąd przygotowania.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence

import typer

from orglib import config, db, plan_apply, plan_gate
from orglib.classify import load_rules
from orglib.plan_build import META_KEY, plan_hash

app = typer.Typer(add_completion=False, help=__doc__)

SNAPSHOT_NAME = "apply_snapshot.json"

#: Kolejność szukania planu, gdy nie podano `--plan` (ta sama co w `validate_plan`).
_PLAN_CANDIDATES = ("plan.jsonl",)

#: Gałąź robocza przedmiotu w repo docelowym (AGENTS.md: jeden przedmiot = jedna gałąź).
BRANCH_TEMPLATE = "subject/{skrot}"


def git(repo: Path, *args: str) -> str:
    """Uruchamia gita w repo docelowym i zwraca stdout (bez końcowego znaku nowej linii)."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ValueError(
            f"git {' '.join(args)}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def git_preflight(
    paths: config.Paths, subject: config.Subject, *, create_branch: bool, allow_dirty: bool
) -> dict[str, str]:
    """Sprawdza gałąź i czystość drzewa paczki; zwraca HEAD do snapshotu.

    Czystość sprawdzamy WYŁĄCZNIE dla katalogu paczki: praca nad narzędziami
    w tym samym klonie nie ma blokować kopiowania materiałów, ale brud w samej
    paczce owszem — inaczej snapshot nie mówiłby prawdy o tym, co dołożył `apply`.
    """
    branch_name = BRANCH_TEMPLATE.format(skrot=subject.skrot)
    git(paths.target_repo, "rev-parse", "--is-inside-work-tree")
    # `symbolic-ref`, nie `rev-parse HEAD`: świeży klon bez commitów ma gałąź, ale
    # nie ma HEAD-a, a komunikat ma mówić o gałęzi przedmiotu, nie o argumencie gita.
    current = git(paths.target_repo, "symbolic-ref", "--short", "HEAD")
    if current != branch_name:
        if not create_branch:
            raise ValueError(
                f"repo docelowe stoi na gałęzi {current!r}, a materiały przedmiotu idą na "
                f"{branch_name!r} — przełącz się albo użyj --create-branch"
            )
        existing = subprocess.run(
            ["git", "-C", str(paths.target_repo), "rev-parse", "--verify", branch_name],
            capture_output=True, text=True, check=False,
        )
        git(paths.target_repo, "switch", *( [branch_name] if existing.returncode == 0 else ["-c", branch_name]))
    dirty = git(paths.target_repo, "status", "--porcelain", "--", str(paths.target_paczka))
    if dirty and not allow_dirty:
        raise ValueError(
            f"katalog paczki ma niezacommitowane zmiany ({len(dirty.splitlines())} pozycji) — "
            "zacommituj je albo wycofaj; --allow-dirty powtarza przerwany apply"
        )
    head = subprocess.run(
        ["git", "-C", str(paths.target_repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return {
        "branch": branch_name,
        "head": head.stdout.strip() if head.returncode == 0 else "(bez commitów)",
    }


def write_snapshot(
    path: Path,
    *,
    subject: config.Subject,
    plan_files: Sequence[Path],
    digest: str,
    repo: dict[str, str],
    operations: Sequence[plan_apply.Operation],
) -> None:
    """Zapisuje stan SPRZED kopiowania: bez tego nie da się potem powiedzieć, co doszło."""
    payload = {
        "created_at": db.now_iso(),
        "semester": subject.semester,
        "subject_key": subject.skrot,
        "grupa": subject.grupa,
        "target_dir": subject.target_dir,
        "plan_files": [str(p) for p in plan_files],
        "plan_hash": digest,
        "repo": repo,
        "counts": plan_apply.summarize(operations),
        "operations": [operation.as_row() for operation in operations],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def record_applied(conn, operation: plan_apply.Operation, digest: str) -> None:
    """Audyt jednej kopii: wiersz w `applied`, status plików i pozycji planu."""
    db.record_applied(conn, {
        "target_relative_path": operation.target_rel,
        "sha256": operation.sha256,
        "action": plan_apply.COPY_ACTION,
        "plan_hash": digest,
        "applied_at": db.now_iso(),
    })
    db.upsert_plan_item(conn, {
        "sha256": operation.sha256,
        "target_relative_path": operation.target_rel,
        "action": plan_apply.COPY_ACTION,
        "status": "applied",
        "plan_run_id": digest,
    })
    for row in conn.execute(
        "SELECT file_id, status FROM files WHERE sha256 = ?", (operation.sha256,)
    ).fetchall():
        status = str(row["status"])
        if status in ("applied", "verified", db.ERROR_STATUS):
            continue
        db.advance_status(conn, int(row["file_id"]), "applied")


@app.command()
def apply(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    plan: list[Path] = typer.Option(
        [], "--plan", help=f"Domyślnie {', '.join(_PLAN_CANDIDATES)} obok manifestu."
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    expect_hash: Optional[str] = typer.Option(
        None, "--expect-hash", help="Wykonaj tylko plan o tym odcisku (zgoda dotyczy konkretnego planu)."
    ),
    yes: bool = typer.Option(False, "--yes", help="Wykonaj. Bez tego: dry-run."),
    create_branch: bool = typer.Option(
        False, "--create-branch", help="Przełącz repo docelowe na gałąź przedmiotu (utwórz, gdy brak)."
    ),
    allow_dirty: bool = typer.Option(
        False, "--allow-dirty", help="Pozwól na niezacommitowane zmiany w paczce (powtórzenie apply)."
    ),
    no_git: bool = typer.Option(
        False, "--no-git", help="Pomiń kontrole gita (repo docelowe nie jest klonem)."
    ),
    strict: bool = typer.Option(False, "--strict", help="Ostrzeżenia bramki też blokują."),
    show: int = typer.Option(20, "--show", min=0, help="Ile pozycji wypisać na stdout."),
) -> None:
    """Wykonaj zaakceptowany plan przedmiotu. Bez `--yes` tylko pokazuje, co zrobi."""
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

        rows, metas = plan_gate.read_plan(plans)
        digest = plan_hash(rows)
        if expect_hash and expect_hash != digest:
            typer.echo(
                f"ODMOWA: zaakceptowano plan {expect_hash[:12]}…, a ten plik ma {digest[:12]}… "
                "— zbuduj plan ponownie albo zaakceptuj bieżący",
                err=True,
            )
            raise typer.Exit(code=2)

        snapshot_path = plans[0].parent / SNAPSHOT_NAME
        config.check_output_target(snapshot_path, paths)
        rules = load_rules()
        thresholds = config.load_thresholds().get("confidence") or {}
    except (KeyError, ValueError, OSError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    conn = db.connect(database)
    try:
        ground_truth = {
            str(row["target_relative_path"]): str(row["sha256"])
            for row in conn.execute("SELECT target_relative_path, sha256 FROM applied")
        }
        findings = plan_gate.evaluate(
            rows, metas,
            subject=subject, rules=rules,
            auto_apply=float(thresholds.get("auto_apply", 0.90)),
            review_min=float(thresholds.get("review_min", 0.70)),
            ground_truth=ground_truth,
        )
        blocking = plan_gate.blocking_count(findings, strict=strict)
        if blocking:
            typer.echo(
                f"PLAN ODRZUCONY przez bramkę: {blocking} blokujących ustaleń — nic nie skopiowano.",
                err=True,
            )
            for finding in findings[:show]:
                if finding.level == "error" or strict:
                    typer.echo(f"  {finding.level.upper()} {finding.code}: {finding.message}", err=True)
            typer.echo("Uruchom `just subject-validate` po pełną listę.", err=True)
            raise typer.Exit(code=2)

        try:
            repo = {"branch": "—", "head": "—"} if no_git else git_preflight(
                paths, subject, create_branch=create_branch, allow_dirty=allow_dirty
            )
        except ValueError as exc:
            typer.echo(f"ODMOWA: {exc}", err=True)
            raise typer.Exit(code=2)

        copies = plan_apply.copies_by_sha(conn, [str(row.get("source_sha256")) for row in rows])
        operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)
        counts = plan_apply.summarize(operations)

        try:
            write_snapshot(
                snapshot_path, subject=subject, plan_files=plans, digest=digest,
                repo=repo, operations=operations,
            )
        except OSError as exc:
            typer.echo(f"Błąd zapisu snapshotu: {exc}", err=True)
            raise typer.Exit(code=1)

        typer.echo(
            f"plan: {', '.join(str(p) for p in plans)} · odcisk {digest[:12]}… · "
            f"pozycje: {len(rows)} · do skopiowania: {counts['new']} · "
            f"już na miejscu: {counts['present']}"
        )
        typer.echo(f"gałąź: {repo['branch']} · HEAD {repo['head'][:12]} · snapshot: {snapshot_path}")

        blockers = [operation for operation in operations if operation.blocking]
        if blockers:
            typer.echo(
                f"ODMOWA: {len(blockers)} pozycji nie da się wykonać bezpiecznie "
                f"(kolizja treści: {counts['conflict']}, brak źródła: {counts['missing_source']}, "
                f"poza paczką: {counts['outside']}) — nic nie skopiowano.",
                err=True,
            )
            for operation in blockers[:show]:
                typer.echo(f"  {operation.state}: {operation.target_rel} — {operation.detail}", err=True)
            raise typer.Exit(code=2)

        todo = [operation for operation in operations if operation.state == plan_apply.NEW]
        if not yes:
            for operation in todo[:show]:
                typer.echo(f"  + {operation.target_rel}")
            if len(todo) > show:
                typer.echo(f"  … i {len(todo) - show} więcej")
            typer.echo(
                f"DRY-RUN: nic nie skopiowano. Wykonanie: dodaj --yes "
                f"(najlepiej z --expect-hash {digest[:12]}…)"
            )
            return

        copied = 0
        try:
            for operation in todo:
                plan_apply.copy_operation(operation)
                record_applied(conn, operation, digest)
                copied += 1
        except (OSError, ValueError) as exc:
            typer.echo(
                f"Przerwane po {copied} kopiach: {exc}. Skopiowane pozycje są zapisane "
                "w bazie — ponowny `apply` dokończy resztę.",
                err=True,
            )
            raise typer.Exit(code=1)
        for operation in (op for op in operations if op.state == plan_apply.PRESENT):
            record_applied(conn, operation, digest)
    finally:
        conn.close()

    typer.echo(f"skopiowano: {copied} · bez zmian: {counts['present']} · pominięte akcje: "
               f"{len(rows) - len(operations)}")
    typer.echo("Materiałów NIE zacommitowano. Następny krok: `just subject-verify`, potem commit.")


if __name__ == "__main__":
    app()
