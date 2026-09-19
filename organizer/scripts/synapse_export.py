"""C3: eksport indeksu organizera do vaulta `synapse` (notatki `.md` z wikilinkami).

Dwa zakresy, bo dwa różne pytania:

- ``--scope subjects`` (domyślny) — **mapa całości**: jedna notatka na przedmiot,
  kolor po semestrze, poziom po tym, ile jeszcze pracy zostało. Krawędź między
  przedmiotami powstaje, gdy łączy je relacja między treściami (ten sam materiał
  krąży po dwóch przedmiotach). 98 notatek, czyli graf, który da się objąć okiem.
- ``--scope subject --skrot AKO`` — **graf relacji materiałów** jednego przedmiotu:
  notatka na treść, krawędzie z tabeli ``relations``. Domyślnie tylko treści, które
  MAJĄ relację (inaczej graf relacji jest polem odosobnionych kropek);
  ``--include-isolated`` dokłada resztę.

Wyjście: katalog vaulta (domyślnie ``work/synapse/{vault}``) z notatkami ``.md``,
``README.md`` opisującym mapowanie i ``synapse.json`` — tym samym kompletem danych
w kształcie ``seedNotes()`` z prototypu, żeby dało się nim nakarmić UI bez parsera
markdown. Vault jest **odtwarzalny**: leży poza gitem, w ``20_WORK``.

Baza jest czytana w trybie ``mode=ro``. Materiałów nie dotyka.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, db
from orglib.synapse import (
    CATEGORY_COLORS,
    Note,
    catalog_colors,
    content_note_id,
    dedupe_ids,
    level_for_content,
    level_for_subject,
    render_markdown,
    slugify,
    status_for_content,
    status_for_subject,
    subject_note_id,
    vault_readme,
    wikilink,
)

app = typer.Typer(add_completion=False, help=__doc__)

GROUND_TRUTH_RUN_ID = "ground_truth"
DEFAULT_VAULT = "paczka"


def _date(value: Any) -> str:
    """Data w formacie, którego używa prototyp (``yyyy-mm-dd``)."""
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def _subject_facts(conn: sqlite3.Connection) -> dict[tuple[int, str], dict[str, Any]]:
    facts: dict[tuple[int, str], dict[str, Any]] = defaultdict(
        lambda: {"ground_truth": 0, "planned": 0, "needs_review": 0,
                 "actions": defaultdict(int), "categories": defaultdict(int), "decided_at": ""}
    )
    for row in conn.execute(
        "SELECT semester, subject_key, run_id, action, needs_review, category, decided_at "
        "FROM classifications"
    ):
        entry = facts[(int(row["semester"]), str(row["subject_key"]))]
        if str(row["run_id"]) == GROUND_TRUTH_RUN_ID:
            entry["ground_truth"] += 1
        else:
            entry["planned"] += 1
            entry["needs_review"] += 1 if row["needs_review"] else 0
            entry["actions"][str(row["action"] or "—")] += 1
        if row["category"]:
            entry["categories"][str(row["category"])] += 1
        entry["decided_at"] = max(entry["decided_at"], _date(row["decided_at"]))
    return facts


def _subject_of_content(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    return {
        str(row["sha256"]): (int(row["semester"]), str(row["subject_key"]))
        for row in conn.execute("SELECT sha256, semester, subject_key FROM classifications")
    }


def _relations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        "SELECT source_sha256, target_sha256, relation_type, confidence, reason FROM relations"
    )]


def subject_notes(conn: sqlite3.Connection, subjects: list[config.Subject]) -> list[Note]:
    """Mapa całości: przedmiot = notatka, wspólne relacje = krawędź."""
    facts = _subject_facts(conn)
    owner = _subject_of_content(conn)
    ambiguous = {
        s.skrot.casefold() for s in subjects
        if sum(1 for other in subjects if other.skrot.casefold() == s.skrot.casefold()) > 1
    }
    identity = {
        (s.semester, s.skrot): subject_note_id(
            s.semester, s.skrot, s.grupa, ambiguous=s.skrot.casefold() in ambiguous
        )
        for s in subjects
    }
    links: dict[tuple[int, str], set[str]] = defaultdict(set)
    shared: dict[tuple[int, str], int] = defaultdict(int)
    for relation in _relations(conn):
        left = owner.get(str(relation["source_sha256"]))
        right = owner.get(str(relation["target_sha256"]))
        if not left or not right or left == right:
            continue
        links[left].add(identity[right])
        links[right].add(identity[left])
        shared[left] += 1
        shared[right] += 1

    notes: list[Note] = []
    for subject in sorted(subjects, key=lambda s: (s.semester, s.grupa, s.skrot)):
        key = (subject.semester, subject.skrot)
        entry = facts.get(key) or {"ground_truth": 0, "planned": 0, "needs_review": 0,
                                   "actions": {}, "categories": {}, "decided_at": ""}
        tags = [f"sem{subject.semester}", f"grupa-{slugify(subject.grupa, limit=24)}"]
        tags += [f"forma-{form.lower()}" for form in subject.forms]
        if subject.katedra:
            tags.append(f"katedra-{slugify(subject.katedra, limit=16)}")
        if entry["needs_review"]:
            tags.append("do-przegladu")
        if not entry["ground_truth"] and not entry["planned"]:
            tags.append("nietkniety")
        actions = ", ".join(f"{k}={v}" for k, v in sorted(dict(entry["actions"]).items())) or "brak"
        categories = ", ".join(
            f"{k}={v}" for k, v in sorted(dict(entry["categories"]).items())
        ) or "brak"
        related = sorted(links[key])
        body = "\n".join([
            f"**{subject.nazwa}** · semestr {subject.semester} · grupa `{subject.grupa}`"
            + (f" · katedra `{subject.katedra}`" if subject.katedra else ""),
            "",
            f"- Katalog docelowy: `{subject.target_dir}`",
            f"- Formy zajęć: {', '.join(subject.forms) or 'brak w katalogu'}",
            f"- W paczce (ground truth): **{entry['ground_truth']}** treści",
            f"- Zaplanowane decyzje: **{entry['planned']}** (do obejrzenia: {entry['needs_review']})",
            f"- Akcje planu: {actions}",
            f"- Kategorie materiałów: {categories}",
            "",
            "## Powiązane przedmioty",
            "",
            ("\n".join(f"- {wikilink(other)}" for other in related)
             if related else "_Brak wspólnych materiałów z innymi przedmiotami._"),
        ])
        note = Note(
            id=identity[key],
            title=f"{subject.skrot} — {subject.nazwa.replace('_', ' ')}",
            category=f"SEM{subject.semester}",
            level=level_for_subject(
                ground_truth=entry["ground_truth"], planned=entry["planned"],
                needs_review=entry["needs_review"],
            ),
            status=status_for_subject(
                ground_truth=entry["ground_truth"], planned=entry["planned"],
                needs_review=entry["needs_review"],
            ),
            tags=tags,
            links=related,
            body=body,
            modified=entry["decided_at"],
            activity=[entry["decided_at"]] if entry["decided_at"] else [],
        )
        note.validate()
        notes.append(note)
    return notes


def content_notes(
    conn: sqlite3.Connection,
    subject: config.Subject,
    *,
    auto_apply: float,
    include_isolated: bool,
) -> list[Note]:
    """Graf relacji materiałów jednego przedmiotu."""
    decisions = {
        str(row["sha256"]): dict(row)
        for row in conn.execute(
            "SELECT * FROM classifications WHERE semester = ? AND subject_key = ?",
            (subject.semester, subject.skrot),
        )
    }
    if not decisions:
        return []
    relations = [
        relation for relation in _relations(conn)
        if str(relation["source_sha256"]) in decisions
        and str(relation["target_sha256"]) in decisions
    ]
    connected: set[str] = set()
    for relation in relations:
        connected.add(str(relation["source_sha256"]))
        connected.add(str(relation["target_sha256"]))

    files: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute(
        "SELECT sha256, source_package, source_relative_path, modified_date, size_bytes, "
        "extension FROM files WHERE sha256 IN (%s)"
        % ",".join("?" * len(decisions)),
        tuple(decisions),
    ):
        files[str(row["sha256"])].append(row)
    kinds = {
        str(row["sha256"]): str(row["content_kind"] or "other")
        for row in conn.execute(
            "SELECT sha256, content_kind FROM content WHERE sha256 IN (%s)"
            % ",".join("?" * len(decisions)),
            tuple(decisions),
        )
    }

    wanted = decisions.keys() if include_isolated else connected
    identity = {
        sha: content_note_id(
            subject.skrot, sha,
            Path(str(files[sha][0]["source_relative_path"])).name if files.get(sha) else "",
        )
        for sha in sorted(wanted)
    }
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        source, target = str(relation["source_sha256"]), str(relation["target_sha256"])
        if source in identity and target in identity:
            by_owner[source].append({**relation, "other": target})
            by_owner[target].append({**relation, "other": source})

    notes: list[Note] = []
    for sha in sorted(wanted):
        decision = decisions[sha]
        copies = files.get(sha, [])
        filename = Path(str(copies[0]["source_relative_path"])).name if copies else sha[:12]
        in_package = str(decision["run_id"]) == GROUND_TRUTH_RUN_ID
        dates = sorted({_date(row["modified_date"]) for row in copies if row["modified_date"]})
        category = str(decision["category"] or "inne")
        kind = kinds.get(sha, "other")
        tags = [f"rodzaj-{kind}", f"akcja-{decision['action'] or 'brak'}",
                f"metoda-{decision['classification_method'] or 'brak'}", f"kategoria-{category}"]
        if decision["year"]:
            tags.append(f"rok-{decision['year']}")
        if in_package:
            tags.append("w-paczce")
        if decision["needs_review"]:
            tags.append("do-przegladu")
        related = sorted({identity[str(r["other"])] for r in by_owner.get(sha, [])})
        relation_lines = [
            f"- {wikilink(identity[str(r['other'])])} — `{r['relation_type']}`, "
            f"pewność {float(r['confidence'] or 0):.2f} ({r['reason']})"
            for r in sorted(by_owner.get(sha, []), key=lambda r: -float(r["confidence"] or 0))
        ]
        provenance = "\n".join(
            f"- `{row['source_package']}/{row['source_relative_path']}`" for row in copies[:12]
        ) or "_brak kopii w indeksie_"
        body = "\n".join([
            f"**{filename}** · `{kind}` · {int(copies[0]['size_bytes']) / 1024:.0f} kB"
            if copies else f"**{filename}** · `{kind}`",
            "",
            f"- Decyzja: **{decision['action'] or 'brak'}** → `{decision['target_relative_path']}`",
            f"- Kategoria: `{category}` · pewność **{float(decision['confidence'] or 0):.2f}** "
            f"· metoda `{decision['classification_method']}`",
            f"- Uzasadnienie: {decision['reason'] or '—'}",
            f"- sha256: `{sha}`",
            "",
            "## Relacje",
            "",
            "\n".join(relation_lines) or "_Brak relacji — treść jest w tym przedmiocie unikalna._",
            "",
            f"## Prowenancja ({len(copies)} kopii)",
            "",
            provenance,
        ])
        note = Note(
            id=identity[sha],
            title=filename,
            category=category,
            level=level_for_content(
                in_package=in_package,
                needs_review=bool(decision["needs_review"]),
                confidence=float(decision["confidence"] or 0.0),
                auto_apply=auto_apply,
            ),
            status=status_for_content(str(decision["action"] or ""), in_package=in_package),
            tags=tags,
            links=related,
            body=body,
            modified=dates[-1] if dates else _date(decision["decided_at"]),
            activity=dates,
        )
        note.validate()
        notes.append(note)
    return notes


def write_vault(notes: list[Note], *, root: Path, vault: str, generated_at: str) -> dict[str, int]:
    """Zapisuje notatki, README i `synapse.json`. Stare notatki vaulta usuwa — jest odtwarzalny."""
    root.mkdir(parents=True, exist_ok=True)
    for stale in sorted(root.rglob("*.md")):
        stale.unlink()
    for note in notes:
        target = root / Path(note.path(vault)).relative_to(vault)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_markdown(note, vault), encoding="utf-8")
    (root / "README.md").write_text(vault_readme(notes, vault, generated_at), encoding="utf-8")
    (root / "synapse.json").write_text(
        json.dumps(
            {
                "vault": vault,
                "generated_at": generated_at,
                "catColors": catalog_colors(notes),
                "notes": [note.as_seed(vault) for note in notes],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"notes": len(notes), "categories": len(catalog_colors(notes))}


@app.command()
def export(
    scope: str = typer.Option("subjects", "--scope", help="subjects (mapa całości) albo subject."),
    semester: Optional[int] = typer.Option(None, "--semester", min=1, max=7),
    skrot: Optional[str] = typer.Option(None, "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    vault: str = typer.Option(DEFAULT_VAULT, "--vault", help="Nazwa vaulta (widoczna w ścieżkach)."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Domyślnie work/synapse/{vault}."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Domyślnie paths.yaml: work_db."),
    include_isolated: bool = typer.Option(
        False, "--include-isolated", help="Zakres subject: dołóż treści bez relacji."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Policz notatki; nie zapisuj."),
) -> None:
    """Zbuduj vault synapse z indeksu; nie dotykaj materiałów."""
    try:
        if scope not in ("subjects", "subject"):
            raise ValueError(f"nieznany zakres {scope!r} — użyj 'subjects' albo 'subject'")
        paths = config.load_paths()
        subjects = config.iter_subjects()
        subject = None
        if scope == "subject":
            if semester is None or skrot is None:
                raise ValueError("zakres 'subject' wymaga --semester i --skrot")
            subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        database = db_path if db_path is not None else paths.work_db
        if not database.is_file():
            raise ValueError(f"brak bazy: {database} — najpierw wykonaj first-pass")
        root = out_dir if out_dir is not None else paths.work / "synapse" / slugify(vault)
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
            notes = (
                subject_notes(conn, subjects) if scope == "subjects"
                else content_notes(conn, subject, auto_apply=auto_apply,
                                   include_isolated=include_isolated)
            )
        finally:
            conn.close()
        notes = dedupe_ids(notes)
    except (KeyError, ValueError, OSError, sqlite3.DatabaseError) as exc:
        typer.echo(f"Błąd eksportu: {exc}", err=True)
        raise typer.Exit(code=1)

    linked = sum(1 for note in notes if note.links)
    levels = defaultdict(int)
    for note in notes:
        levels[note.level] += 1
    typer.echo(
        f"zakres: {scope}" + (f" · {subject.skrot} SEM{subject.semester}" if subject else "")
        + f" · notatki: {len(notes)} · z powiązaniami: {linked}"
    )
    typer.echo(
        "poziomy: " + ", ".join(f"L{level}={levels[level]}" for level in sorted(levels))
        + " · kategorie: " + ", ".join(sorted(catalog_colors(notes)))
    )
    if dry_run:
        typer.echo("dry-run: nic nie zapisano")
        return
    if not notes:
        typer.echo("brak notatek do zapisania — czy ten przedmiot ma decyzje w bazie?", err=True)
        raise typer.Exit(code=1)
    try:
        counts = write_vault(notes, root=root, vault=vault, generated_at=db.now_iso())
    except OSError as exc:
        typer.echo(f"Błąd zapisu vaulta: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"vault: {root} ({counts['notes']} notatek, {counts['categories']} kategorii)")
    typer.echo(f"dla prototypu: {root / 'synapse.json'} (kształt seedNotes)")


if __name__ == "__main__":
    app()
