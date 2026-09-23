"""C3: eksport indeksu do vaulta `synapse` — semestry, przedmioty i pliki jako graf.

Kontrakt wejściowy jest cudzy i opisany w `docs/SYNAPSE.md`; ten skrypt produkuje katalog
`.md`, który `Synapse.Generator` zamienia w `graph.json` dla viewera.

Co trafia do vaulta (decyzja użytkownika 2026-09-19):

- **węzły**: semestr → przedmiot → plik; plik tylko wtedy, gdy ma DECYZJĘ w bazie
  (ground truth albo plan). Surowe materiały bez decyzji nie zaśmiecają grafu paczki;
- **krawędzie**: `belongs_to` (szkielet hierarchii) oraz relacje z etapu B6
  (`near_duplicate`, `older_version`, `related`) z ich pewnością;
- **ghost**: relacja do treści BEZ decyzji zostaje zapisana jako cel spoza vaulta, więc
  generator zrobi z niej ghost node — „istnieje duplikat poza paczką” jest widoczne.
  `--include-unassigned` zamienia te ghosty w zwykłe notatki.

Vault **nie jest repozytorium gita** — to widok bieżącego stanu, nie historia zmian
(historia decyzji jest w bazie, historia materiałów w repo paczki). Dlatego generator
uruchamiaj z `--no-git`.

Baza jest czytana w trybie `mode=ro`. Materiałów nie dotyka.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db
from orglib.synapse_vault import (
    EDGE_BELONGS_TO,
    LEVEL_NEEDS_HUMAN,
    NODE_FILE,
    NODE_SEMESTER,
    NODE_SUBJECT,
    STATUS_TODO,
    Note,
    Relation,
    dedupe_ids,
    file_id,
    file_level,
    file_status,
    render_note,
    semester_id,
    slugify,
    subject_id,
    subject_level,
    subject_status,
    unassigned_id,
    vault_readme,
)

app = typer.Typer(add_completion=False, help=__doc__)

GROUND_TRUTH_RUN_ID = "ground_truth"


def _date(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def load_index(
    conn: sqlite3.Connection,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, list[sqlite3.Row]], dict[str, str]]:
    """Decyzje, relacje, kopie plików i rodzaje treści — cztery zapytania, bez pętli po plikach."""
    decisions = {
        str(row["sha256"]): dict(row)
        for row in conn.execute("SELECT * FROM classifications")
    }
    relations = [
        dict(row)
        for row in conn.execute(
            "SELECT source_sha256, target_sha256, relation_type, confidence, reason FROM relations"
        )
    ]
    files: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute(
        "SELECT sha256, source_package, source_relative_path, modified_date, size_bytes "
        "FROM files WHERE sha256 IS NOT NULL ORDER BY source_package, source_relative_path"
    ):
        files[str(row["sha256"])].append(row)
    kinds = {
        str(row["sha256"]): str(row["content_kind"] or "other")
        for row in conn.execute("SELECT sha256, content_kind FROM content")
    }
    return decisions, relations, files, kinds


def build_notes(
    *,
    subjects: list[config.Subject],
    decisions: dict[str, dict[str, Any]],
    relations: list[dict[str, Any]],
    files: dict[str, list[sqlite3.Row]],
    kinds: dict[str, str],
    auto_apply: float,
    include_unassigned: bool,
    scope: tuple[int, str] | None = None,
) -> list[Note]:
    """Cały vault jako lista notatek. Czysta funkcja nad wynikiem zapytań."""
    ambiguous = {
        s.skrot.casefold()
        for s in subjects
        if sum(1 for other in subjects if other.skrot.casefold() == s.skrot.casefold()) > 1
    }
    subject_ids = {
        (s.semester, s.skrot): subject_id(
            s.semester, s.skrot, s.grupa, ambiguous=s.skrot.casefold() in ambiguous
        )
        for s in subjects
    }
    in_scope = (
        (lambda sem, skrot: (sem, skrot) == scope) if scope else (lambda sem, skrot: True)
    )

    # ── pliki ────────────────────────────────────────────────────────────────
    file_ids: dict[str, str] = {}
    file_notes: list[Note] = []
    for sha, decision in sorted(decisions.items()):
        semester, skrot = int(decision["semester"]), str(decision["subject_key"])
        if not in_scope(semester, skrot) or (semester, skrot) not in subject_ids:
            continue
        copies = files.get(sha, [])
        filename = Path(str(copies[0]["source_relative_path"])).name if copies else sha[:12]
        note_id = file_id(skrot, sha, filename)
        file_ids[sha] = note_id

    for sha, decision in sorted(decisions.items()):
        if sha not in file_ids:
            continue
        semester, skrot = int(decision["semester"]), str(decision["subject_key"])
        copies = files.get(sha, [])
        filename = Path(str(copies[0]["source_relative_path"])).name if copies else sha[:12]
        in_package = str(decision["run_id"]) == GROUND_TRUTH_RUN_ID
        category = str(decision["category"] or "inne")
        kind = kinds.get(sha, "other")
        action = str(decision["action"] or "")
        confidence = float(decision["confidence"] or 0.0)
        dates = sorted({_date(row["modified_date"]) for row in copies if row["modified_date"]})

        tags = [f"sem{semester}", slugify(skrot, limit=16), f"rodzaj-{kind}",
                f"kategoria-{slugify(category, limit=20)}"]
        if action:
            tags.append(f"akcja-{action}")
        if decision["classification_method"]:
            tags.append(f"metoda-{decision['classification_method']}")
        if decision["year"]:
            tags.append(f"rok-{decision['year']}")
        if in_package:
            tags.append("w-paczce")
        if decision["needs_review"]:
            tags.append("do-przegladu")

        provenance = "\n".join(
            f"- `{row['source_package']}/{row['source_relative_path']}`" for row in copies[:12]
        ) or "_brak kopii w indeksie_"
        size = int(copies[0]["size_bytes"]) if copies else 0
        body = "\n".join([
            f"**{filename}** · `{kind}` · {size / 1024:.0f} kB",
            "",
            f"- Decyzja: **{action or 'brak'}** → `{decision['target_relative_path']}`",
            f"- Kategoria: `{category}` · pewność **{confidence:.2f}** "
            f"· metoda `{decision['classification_method']}`",
            f"- Uzasadnienie: {decision['reason'] or '—'}",
            f"- sha256: `{sha}`",
            "",
            f"## Prowenancja ({len(copies)} kopii)",
            "",
            provenance,
        ])
        file_notes.append(Note(
            id=file_ids[sha],
            title=filename,
            type=NODE_FILE,
            category=category,
            level=file_level(
                in_package=in_package,
                needs_review=bool(decision["needs_review"]),
                confidence=confidence,
                auto_apply=auto_apply,
            ),
            status=file_status(action, in_package=in_package),
            tags=tags,
            aliases=[filename] if filename != file_ids[sha] else [],
            modified=dates[-1] if dates else _date(decision["decided_at"]),
            relations=[Relation(subject_ids[(semester, skrot)], EDGE_BELONGS_TO)],
            body=body,
            folder=f"sem{semester}/{slugify(skrot, limit=16)}",
        ))

    notes_by_id = {note.id: note for note in file_notes}

    # ── relacje podobieństwa (B6) ────────────────────────────────────────────
    unassigned: dict[str, str] = {}
    for relation in relations:
        source, target = str(relation["source_sha256"]), str(relation["target_sha256"])
        left, right = file_ids.get(source), file_ids.get(target)
        if left is None and right is None:
            continue  # obie strony poza paczką — to nie jest graf paczki
        kind = str(relation["relation_type"])
        confidence = relation["confidence"]

        if left is not None and right is not None:
            notes_by_id[left].relations.append(Relation(right, kind, confidence))
            continue

        # jedna strona bez decyzji → cel spoza vaulta (ghost), żeby było widać, że istnieje
        owner_id = left if left is not None else right
        other_sha = target if left is not None else source
        copies = files.get(other_sha, [])
        other_name = Path(str(copies[0]["source_relative_path"])).name if copies else ""
        ghost_target = unassigned.setdefault(other_sha, unassigned_id(other_sha, other_name))
        notes_by_id[owner_id].relations.append(Relation(ghost_target, kind, confidence))

    if include_unassigned:
        for sha, note_id in sorted(unassigned.items()):
            copies = files.get(sha, [])
            filename = Path(str(copies[0]["source_relative_path"])).name if copies else sha[:12]
            file_notes.append(Note(
                id=note_id,
                title=filename,
                type=NODE_FILE,
                category="nieprzypisane",
                level=LEVEL_NEEDS_HUMAN,
                status=STATUS_TODO,
                tags=["nieprzypisane", f"rodzaj-{kinds.get(sha, 'other')}"],
                modified=_date(copies[0]["modified_date"]) if copies else "",
                body="\n".join([
                    f"**{filename}** — treść bez decyzji w żadnym przedmiocie.",
                    "",
                    f"- sha256: `{sha}`",
                    f"- kopii w źródłach: {len(copies)}",
                    "",
                    "Trafiła tu, bo jest podobna do materiału z paczki. Dopóki nikt nie",
                    "przypisze jej do przedmiotu, nie ma decyzji ani miejsca docelowego.",
                ]),
                folder="nieprzypisane",
            ))

    # ── przedmioty i semestry ────────────────────────────────────────────────
    per_subject: dict[tuple[int, str], dict[str, int]] = defaultdict(
        lambda: {"ground_truth": 0, "planned": 0, "needs_review": 0}
    )
    for decision in decisions.values():
        key = (int(decision["semester"]), str(decision["subject_key"]))
        if str(decision["run_id"]) == GROUND_TRUTH_RUN_ID:
            per_subject[key]["ground_truth"] += 1
        else:
            per_subject[key]["planned"] += 1
            per_subject[key]["needs_review"] += 1 if decision["needs_review"] else 0

    subject_notes: list[Note] = []
    semesters: dict[int, list[config.Subject]] = defaultdict(list)
    for subject in subjects:
        semesters[subject.semester].append(subject)
        key = (subject.semester, subject.skrot)
        if scope and key != scope:
            continue
        counts = per_subject.get(key, {"ground_truth": 0, "planned": 0, "needs_review": 0})
        # Skrót przedmiotu jest tym samym tagiem, który niosą jego pliki: jedno
        # kliknięcie w grafie wybiera przedmiot RAZEM z materiałami, a nie osobno.
        tags = [
            f"sem{subject.semester}",
            slugify(subject.skrot, limit=16),
            f"grupa-{slugify(subject.grupa, limit=20)}",
        ]
        tags += [f"forma-{form.lower()}" for form in subject.forms]
        if subject.katedra:
            tags.append(f"katedra-{slugify(subject.katedra, limit=16)}")
        if counts["needs_review"]:
            tags.append("do-przegladu")
        subject_notes.append(Note(
            id=subject_ids[key],
            title=f"{subject.skrot} — {subject.nazwa.replace('_', ' ')}",
            type=NODE_SUBJECT,
            category=f"SEM{subject.semester}",
            level=subject_level(**counts),
            status=subject_status(**counts),
            tags=tags,
            aliases=[subject.skrot, subject.nazwa.replace("_", " ")],
            relations=[Relation(semester_id(subject.semester), EDGE_BELONGS_TO)],
            body="\n".join([
                f"**{subject.nazwa.replace('_', ' ')}** · semestr {subject.semester} "
                f"· grupa `{subject.grupa}`" + (f" · katedra `{subject.katedra}`" if subject.katedra else ""),
                "",
                f"- Katalog docelowy: `{subject.target_dir}`",
                f"- Formy zajęć: {', '.join(subject.forms) or 'brak w katalogu'}",
                f"- W paczce (ground truth): **{counts['ground_truth']}** treści",
                f"- Zaplanowane decyzje: **{counts['planned']}** "
                f"(do obejrzenia: {counts['needs_review']})",
            ]),
            folder=f"sem{subject.semester}",
        ))

    semester_notes: list[Note] = []
    for semester in sorted(semesters):
        members = semesters[semester]
        if scope and semester != scope[0]:
            continue
        totals = {"ground_truth": 0, "planned": 0, "needs_review": 0}
        for subject in members:
            counts = per_subject.get((semester, subject.skrot))
            if counts:
                for key_name in totals:
                    totals[key_name] += counts[key_name]
        semester_notes.append(Note(
            id=semester_id(semester),
            title=f"Semestr {semester}",
            type=NODE_SEMESTER,
            category="semestr",
            status=subject_status(**totals),
            tags=["semestr", f"sem{semester}"],
            body="\n".join([
                f"**Semestr {semester}** — {len(members)} przedmiotów w katalogu.",
                "",
                f"- W paczce (ground truth): **{totals['ground_truth']}** treści",
                f"- Zaplanowane decyzje: **{totals['planned']}** "
                f"(do obejrzenia: {totals['needs_review']})",
            ]),
        ))

    return dedupe_ids([*semester_notes, *subject_notes, *file_notes])


def write_vault(notes: list[Note], root: Path, generated_at: str) -> dict[str, int]:
    """Nadpisuje vault w całości — jest generowany, więc stare notatki nie mogą zostać."""
    if root.exists():
        for stale in sorted(root.rglob("*.md")):
            stale.unlink()
    root.mkdir(parents=True, exist_ok=True)
    for note in notes:
        target = root / note.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_note(note), encoding="utf-8")
    # README leży OBOK vaulta, nie w nim: skaner traktuje każdy `.md` jako notatkę,
    # więc README w środku stałby się węzłem-sierotą w grafie.
    (root.parent / f"README-{root.name}.md").write_text(
        vault_readme(notes, generated_at), encoding="utf-8"
    )
    kinds: dict[str, int] = defaultdict(int)
    for note in notes:
        kinds[note.type] += 1
    return dict(kinds)


@app.command()
def export(
    semester: Optional[int] = typer.Option(None, "--semester", min=1, max=7,
                                           help="Zawęź do jednego przedmiotu (z --skrot)."),
    skrot: Optional[str] = typer.Option(None, "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Domyślnie work/synapse/vault."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    include_unassigned: bool = typer.Option(
        False, "--include-unassigned",
        help="Zamień ghosty (materiał bez decyzji) w zwykłe notatki.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Policz notatki; nie zapisuj."),
) -> None:
    """Zbuduj vault dla synapse z indeksu; nie dotykaj materiałów."""
    try:
        paths = config.load_paths()
        subjects = config.iter_subjects()
        scope = None
        if semester is not None or skrot is not None:
            if semester is None or skrot is None:
                raise ValueError("zawężenie wymaga i --semester, i --skrot")
            subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
            scope = (subject.semester, subject.skrot)
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")
        root = out_dir if out_dir is not None else paths.work / "synapse" / "vault"
        config.check_output_target(root, paths)
        auto_apply = float((config.load_thresholds().get("confidence") or {}).get("auto_apply", 0.9))

        conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            version = db.current_schema_version(conn)
            if version != db.SCHEMA_VERSION:
                raise ValueError(
                    f"nieobsługiwana schema_version={version}; oczekiwano {db.SCHEMA_VERSION}"
                )
            decisions, relations, files, kinds = load_index(conn)
        finally:
            conn.close()

        notes = build_notes(
            subjects=subjects, decisions=decisions, relations=relations, files=files,
            kinds=kinds, auto_apply=auto_apply, include_unassigned=include_unassigned,
            scope=scope,
        )
        for note in notes:
            note.validate()
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd eksportu: {exc}", err=True)
        raise typer.Exit(code=1)

    by_type: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    ghosts: set[str] = set()
    known = {note.id for note in notes}
    for note in notes:
        by_type[note.type] += 1
        for relation in note.relations:
            by_kind[relation.kind] += 1
            if relation.target not in known:
                ghosts.add(relation.target)

    typer.echo(
        "węzły: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
        + f" · razem {len(notes)}"
    )
    typer.echo(
        "relacje: " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
        + f" · cele spoza vaulta (ghost): {len(ghosts)}"
    )
    if dry_run:
        typer.echo("dry-run: nic nie zapisano")
        return

    try:
        counts = write_vault(notes, root, db.now_iso())
    except OSError as exc:
        typer.echo(f"Błąd zapisu vaulta: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"vault: {root} ({sum(counts.values())} notatek)")
    typer.echo(
        "graf: dotnet run --project vendor/synapse/Synapse.Generator/Synapse.Generator "
        f"-- --vault {root} --out vendor/synapse/synapse-viewer/public/graph.json --no-git"
    )


if __name__ == "__main__":
    app()
