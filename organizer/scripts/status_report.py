"""E3: `reports/STATUS.md` — przedmioty × etapy, liczone z bazy.

Kolejka pracy w jednym pliku: co już leży w paczce (ground truth), co ma plan, ile
pozycji czeka na człowieka i czego jeszcze nikt nie tknął. Wszystko z operacyjnego
indeksu — od B7 to on jest źródłem prawdy o decyzjach, więc status nie wymaga
przeglądania katalogów z raportami ani ufania temu, że ktoś je odświeżył.

Bazy nie modyfikuje (otwiera ją w trybie ``mode=ro``). Pisze wyłącznie jeden plik
Markdown przeznaczony do wersjonowania.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db

app = typer.Typer(add_completion=False, help=__doc__)

REPORT_NAME = "STATUS.md"
GROUND_TRUTH_RUN_ID = "ground_truth"

#: Etapy przedmiotu od najpilniejszego do najspokojniejszego — kolejność kolejki
#: pracy. Nazwy MUSZĄ pokrywać się z tym, co zwraca :func:`stage_of`; studio
#: (`studio/api/queries.py`) czyta tę stałą zamiast powtarzać własną listę.
STAGE_ORDER: tuple[str, ...] = (
    "plan do przeglądu",
    "plan gotowy",
    "tylko ground truth",
    "nietknięty",
)


def collect(conn: sqlite3.Connection) -> dict[str, Any]:
    """Wszystkie liczby w kilku zapytaniach — bez przeglądania plików."""
    scalar = lambda sql, *args: conn.execute(sql, args).fetchone()[0]  # noqa: E731
    files_by_status = {
        str(row["status"]): int(row["n"])
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status")
    }
    per_subject: dict[tuple[int, str], dict[str, Any]] = defaultdict(
        lambda: {"ground_truth": 0, "planned": 0, "needs_review": 0, "actions": defaultdict(int),
                 "decided_at": None, "run_id": None}
    )
    for row in conn.execute(
        "SELECT semester, subject_key, run_id, action, needs_review, decided_at, COUNT(*) AS n "
        "FROM classifications GROUP BY semester, subject_key, run_id, action, needs_review, decided_at"
    ):
        entry = per_subject[(int(row["semester"]), str(row["subject_key"]))]
        count = int(row["n"])
        if str(row["run_id"]) == GROUND_TRUTH_RUN_ID:
            entry["ground_truth"] += count
            continue
        entry["planned"] += count
        entry["needs_review"] += count if row["needs_review"] else 0
        entry["actions"][str(row["action"] or "—")] += count
        if row["decided_at"] and (entry["decided_at"] or "") < str(row["decided_at"]):
            entry["decided_at"] = str(row["decided_at"])
            entry["run_id"] = str(row["run_id"])
    return {
        "packages": scalar("SELECT COUNT(*) FROM source_packages"),
        "folders": scalar("SELECT COUNT(*) FROM folders"),
        "duplicate_folders": scalar("SELECT COUNT(*) FROM folders WHERE duplicate_of IS NOT NULL"),
        "files": scalar("SELECT COUNT(*) FROM files"),
        "files_by_status": files_by_status,
        "contents": scalar("SELECT COUNT(*) FROM content"),
        "with_text": scalar("SELECT COUNT(*) FROM content WHERE extracted_text_path IS NOT NULL"),
        "relations": scalar("SELECT COUNT(*) FROM relations"),
        "plan_items": scalar("SELECT COUNT(*) FROM plan_items"),
        "applied": scalar("SELECT COUNT(*) FROM applied"),
        "per_subject": per_subject,
    }


def stage_of(entry: dict[str, Any]) -> str:
    """Etap, na którym stoi przedmiot — nazwany tak, jak mówi o nim `TODO.md`."""
    if entry["planned"] and not entry["needs_review"]:
        return "plan gotowy"
    if entry["planned"]:
        return "plan do przeglądu"
    if entry["ground_truth"]:
        return "tylko ground truth"
    return "nietknięty"


def render(data: dict[str, Any], subjects: list[config.Subject], generated_at: str) -> str:
    statuses = ", ".join(
        f"{name}: {count}" for name, count in sorted(data["files_by_status"].items())
    )
    header = [
        "# STATUS — Paczka Organizer",
        "",
        "Plik **generowany** przez `scripts/status_report.py` (`just status`). Nie edytuj ręcznie;",
        "źródłem liczb jest operacyjny indeks SQLite, a nie katalogi z raportami.",
        "",
        f"- Wygenerowano: {generated_at}",
        f"- Źródła: {data['packages']} paczek, {data['folders']} katalogów "
        f"(w tym {data['duplicate_folders']} duplikatów), {data['files']} plików",
        f"- Statusy plików: {statuses or 'brak'}",
        f"- Treści: {data['contents']} unikalnych, {data['with_text']} z wyekstrahowanym tekstem",
        f"- Relacje podobieństwa: {data['relations']} · pozycje planu: {data['plan_items']} · "
        f"wpisy w `applied`: {data['applied']} (dziś w całości ground truth — `apply` jeszcze nie działał)",
        "",
        "## Przedmioty",
        "",
        "`w paczce` = treści rozpoznane w repo docelowym (ground truth). `plan` = decyzje",
        "zapisane przez `just subject-plan`. `do obejrzenia` = pozycje planu z `needs_review`.",
        "",
        "| SEM | grupa | skrót | przedmiot | etap | w paczce | plan | do obejrzenia | kopiuj | pomiń | media | ostatni plan |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    rows = []
    for subject in sorted(subjects, key=lambda s: (s.semester, s.grupa, s.skrot)):
        entry = data["per_subject"].get((subject.semester, subject.skrot))
        entry = entry or {"ground_truth": 0, "planned": 0, "needs_review": 0,
                          "actions": {}, "decided_at": None}
        actions = entry["actions"]
        rows.append(
            f"| {subject.semester} | {subject.grupa} | {subject.skrot} | {subject.nazwa} | "
            f"{stage_of(entry)} | {entry['ground_truth']} | {entry['planned']} | "
            f"{entry['needs_review']} | {actions.get('copy', 0)} | {actions.get('skip', 0)} | "
            f"{actions.get('media', 0)} | {entry['decided_at'] or '—'} |"
        )
    summary = [
        "",
        "## Kolejka",
        "",
    ]
    by_stage: dict[str, list[str]] = defaultdict(list)
    for subject in subjects:
        entry = data["per_subject"].get((subject.semester, subject.skrot), {
            "ground_truth": 0, "planned": 0, "needs_review": 0, "actions": {}, "decided_at": None
        })
        by_stage[stage_of(entry)].append(f"{subject.skrot} (sem {subject.semester})")
    for stage in STAGE_ORDER:
        names = sorted(by_stage.get(stage, []))
        if not names:
            continue
        shown = ", ".join(names[:12]) + (f" … (+{len(names) - 12})" if len(names) > 12 else "")
        summary.append(f"- **{stage}** ({len(names)}): {shown}")
    return "\n".join([*header, *rows, *summary, ""])


@app.command()
def status(
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    output: Optional[Path] = typer.Option(None, "--output", help=f"Domyślnie reports/{REPORT_NAME}."),
) -> None:
    """Przelicz stan pracy z indeksu i zapisz `reports/STATUS.md`."""
    try:
        paths = config.load_paths()
        subjects = config.iter_subjects()
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")
        target = output if output is not None else config.ORGANIZER_ROOT / "reports" / REPORT_NAME
        config.check_output_target(target, paths)

        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            version = db.current_schema_version(conn)
            if version != db.SCHEMA_VERSION:
                raise ValueError(
                    f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}"
                )
            data = collect(conn)
        finally:
            conn.close()
        page = render(data, subjects, db.now_iso())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd generowania statusu: {exc}", err=True)
        raise typer.Exit(code=1)

    started = sum(1 for entry in data["per_subject"].values() if entry["planned"])
    typer.echo(
        f"przedmioty: {len(subjects)} · z planem: {started} · "
        f"treści: {data['contents']} · pozycje planu: {data['plan_items']}"
    )
    typer.echo(f"status: {target}")


if __name__ == "__main__":
    app()
