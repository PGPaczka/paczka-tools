"""B10: `apply` kopiuje dokładnie zaakceptowany plan — albo nie kopiuje nic.

To jedyny etap, który zapisuje materiały, więc testy pilnują nie tego, że „działa”,
tylko czego NIE robi: nie rusza źródeł, nie nadpisuje cudzej treści, nie wykonuje
planu odrzuconego przez bramkę i nie wykonuje planu innego niż zaakceptowany.
Każdy z tych warunków ma osobny test, bo każdy z nich osobno chroni materiały.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import apply as apply_cli
from orglib import config, db, plan_apply
from orglib.hashes import sha256_file
from orglib.plan_build import plan_hash

runner = CliRunner()

SUBJECT_DIR = "paczka/SEM3/AKO_Architektura_Komputerów"
CONTENT = {
    "a": "; lab 3.5 — kod studenta\nmov ax, 1\n".encode("utf-8"),
    "b": b"%PDF-1.4 tresc wykladu\n",
}


def _row(sha: str, target_rel: str, **override) -> dict:
    """Linia planu w kształcie, który przechodzi bramkę B8 (wzór z realnego planu AKO)."""
    row = {
        "action": "copy",
        "category": "laboratoria",
        "confidence": 0.95,
        "method": "heuristic",
        "model": "deterministic",
        "needs_review": False,
        "reason": "kategoria laboratoria wg: nazwa pliku",
        "related_to": None,
        "relation": None,
        "schema_version": 1,
        "source_sha256": sha,
        "target_rel": target_rel,
        "year": "2019",
    }
    row.update(override)
    return row


def _write_plan(path: Path, rows: list[dict]) -> str:
    """Zapisuje plan z nagłówkiem `_meta` (jak B7) i zwraca jego odcisk."""
    digest = plan_hash(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"_meta": {
            "schema_version": 1, "subject_key": "AKO", "semester": 3, "grupa": "Wspolne",
            "target_dir": SUBJECT_DIR, "created_at": "2026-09-22T10:00:00Z",
            "items": len(rows), "plan_hash": digest,
        }}, ensure_ascii=False, sort_keys=True) + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return digest


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Źródła + repo docelowe + baza; przedmiot AKO bierzemy z REALNEGO subjects.yaml."""
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    (paths.sources / "P" / "SEM3").mkdir(parents=True)
    paths.target_paczka.mkdir(parents=True)
    monkeypatch.setattr(config, "load_paths", lambda: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")

    shas: dict[str, str] = {}
    conn = db.connect(paths.work_db)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for name, payload in CONTENT.items():
        source = paths.sources / "P" / "SEM3" / f"plik_{name}.asm"
        source.write_bytes(payload)
        sha = sha256_file(source)
        shas[name] = sha
        db.upsert_content(conn, {"sha256": sha, "content_kind": "code"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/plik_{name}.asm",
            "folder_path": "P/SEM3", "filename": f"plik_{name}.asm", "extension": ".asm",
            "size_bytes": len(payload), "sha256": sha, "status": "extracted",
        })
    conn.commit()
    conn.close()
    return paths, shas


@pytest.fixture
def plan_file(workspace, tmp_path):
    paths, shas = workspace
    rows = [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/wspólne/lab_03/lab_3.5.asm"),
        _row(shas["b"], f"{SUBJECT_DIR}/laboratoria/wspólne/lab_03/lab_3.6.asm"),
    ]
    path = tmp_path / "reports" / "AKO" / "plan.jsonl"
    digest = _write_plan(path, rows)
    return path, digest, rows


def run(plan: Path, *args: str):
    return runner.invoke(
        apply_cli.app,
        ["--semester", "3", "--skrot", "AKO", "--plan", str(plan), "--no-git", *args],
    )


def source_fingerprint(paths: config.Paths) -> dict[str, tuple[str, int]]:
    """Hash i mtime każdego pliku źródłowego — reguła twarda nr 1 ma być sprawdzalna."""
    return {
        str(path.relative_to(paths.sources)): (sha256_file(path), path.stat().st_mtime_ns)
        for path in sorted(paths.sources.rglob("*")) if path.is_file()
    }


# --- silnik: co plan ZROBIŁBY z drzewem ------------------------------------

def test_new_file_is_planned_for_copy(workspace, plan_file) -> None:
    paths, _ = workspace
    _, _, rows = plan_file
    conn = db.connect(paths.work_db)
    try:
        copies = plan_apply.copies_by_sha(conn, [r["source_sha256"] for r in rows])
    finally:
        conn.close()

    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)

    assert [op.state for op in operations] == [plan_apply.NEW, plan_apply.NEW]
    assert all(op.source is not None and op.source.is_file() for op in operations)


def test_same_content_already_in_place_is_not_a_copy(workspace, plan_file) -> None:
    """Powtórzony `apply` ma nic nie robić, a nie kopiować drugi raz."""
    paths, shas = workspace
    _, _, rows = plan_file
    target = paths.target_repo / rows[0]["target_rel"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(CONTENT["a"])

    conn = db.connect(paths.work_db)
    try:
        copies = plan_apply.copies_by_sha(conn, [r["source_sha256"] for r in rows])
    finally:
        conn.close()
    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)

    assert operations[0].state == plan_apply.PRESENT and not operations[0].blocking


def test_other_content_under_the_target_path_blocks(workspace, plan_file) -> None:
    """Reguła twarda nr 2 i nr 6: cudzej treści nie nadpisujemy ani nie kasujemy."""
    paths, _ = workspace
    _, _, rows = plan_file
    target = paths.target_repo / rows[0]["target_rel"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"recznie ulozony material")

    conn = db.connect(paths.work_db)
    try:
        copies = plan_apply.copies_by_sha(conn, [r["source_sha256"] for r in rows])
    finally:
        conn.close()
    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)

    assert operations[0].state == plan_apply.CONFLICT and operations[0].blocking


def test_missing_source_blocks_instead_of_silently_skipping(workspace, plan_file) -> None:
    paths, shas = workspace
    _, _, rows = plan_file
    (paths.sources / "P" / "SEM3" / "plik_a.asm").unlink()

    conn = db.connect(paths.work_db)
    try:
        copies = plan_apply.copies_by_sha(conn, [r["source_sha256"] for r in rows])
    finally:
        conn.close()
    operations = plan_apply.plan_operations(rows, paths=paths, copies=copies)

    assert operations[0].state == plan_apply.MISSING_SOURCE and operations[0].blocking


@pytest.mark.parametrize("target_rel", [
    "../poza-repo.txt",
    "/etc/passwd",
    "paczka/../../ucieczka.txt",
    "inne_repo/plik.txt",
])
def test_target_outside_the_package_is_refused(workspace, plan_file, target_rel) -> None:
    """Ostatnia bramka przed dyskiem: plan pisze wyłącznie do katalogu paczki."""
    paths, shas = workspace
    rows = [_row(shas["a"], target_rel)]

    operations = plan_apply.plan_operations(
        rows, paths=paths, copies={shas["a"]: [("P", "SEM3/plik_a.asm")]}
    )

    assert operations[0].state == plan_apply.OUTSIDE and operations[0].blocking


def test_actions_other_than_copy_write_nothing(workspace) -> None:
    paths, shas = workspace
    rows = [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/x.asm", action="skip"),
        _row(shas["b"], "90_MEDIA/AKO/nagranie.mp4", action="media"),
    ]

    assert plan_apply.plan_operations(rows, paths=paths, copies={}) == []


def test_copy_is_atomic_and_keeps_the_original_untouched(workspace, plan_file) -> None:
    paths, shas = workspace
    _, _, rows = plan_file
    before = source_fingerprint(paths)
    source = paths.sources / "P" / "SEM3" / "plik_a.asm"
    operation = plan_apply.Operation(
        shas["a"], rows[0]["target_rel"], paths.target_repo / rows[0]["target_rel"],
        source, plan_apply.NEW,
    )

    plan_apply.copy_operation(operation)

    assert sha256_file(operation.target) == shas["a"]
    assert source_fingerprint(paths) == before
    assert not list(operation.target.parent.glob(".apply-*"))


# --- CLI: bramka, zgoda, audyt --------------------------------------------

def test_dry_run_is_the_default_and_copies_nothing(workspace, plan_file) -> None:
    paths, _ = workspace
    plan, digest, _ = plan_file

    result = run(plan, "--db", str(paths.work_db))

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert not list((paths.target_paczka).rglob("*.asm"))
    snapshot = json.loads((plan.parent / "apply_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["plan_hash"] == digest and snapshot["counts"]["new"] == 2


def test_yes_copies_and_writes_the_audit_trail(workspace, plan_file) -> None:
    paths, shas = workspace
    plan, digest, rows = plan_file

    result = run(plan, "--db", str(paths.work_db), "--yes")

    assert result.exit_code == 0, result.output
    for row in rows:
        target = paths.target_repo / row["target_rel"]
        assert target.is_file() and sha256_file(target) == row["source_sha256"]

    conn = db.connect(paths.work_db)
    try:
        applied = {r["target_relative_path"]: dict(r) for r in conn.execute("SELECT * FROM applied")}
        statuses = {str(r["status"]) for r in conn.execute("SELECT status FROM files")}
    finally:
        conn.close()
    assert set(applied) == {row["target_rel"] for row in rows}
    assert all(entry["plan_hash"] == digest for entry in applied.values())
    assert statuses == {"applied"}


def test_sources_are_untouched_by_apply(workspace, plan_file) -> None:
    """Reguła twarda nr 1 — sprawdzana po hashach I czasach modyfikacji."""
    paths, _ = workspace
    plan, _, _ = plan_file
    before = source_fingerprint(paths)

    run(plan, "--db", str(paths.work_db), "--yes")

    assert source_fingerprint(paths) == before


def test_a_plan_rejected_by_the_gate_copies_nothing(workspace, plan_file, tmp_path) -> None:
    """Bramka B8 jest wykonywana TUTAJ, nie tylko w `validate_plan`."""
    paths, shas = workspace
    # Pewność poniżej progu auto_apply przy action=copy — błąd bramki (B8).
    rows = [_row(shas["a"], f"{SUBJECT_DIR}/laboratoria/wspólne/lab_03/lab_3.5.asm",
                 confidence=0.2, needs_review=True)]
    plan = tmp_path / "reports" / "AKO" / "plan_zly.jsonl"
    _write_plan(plan, rows)

    result = run(plan, "--db", str(paths.work_db), "--yes")

    assert result.exit_code == 2
    assert "PLAN ODRZUCONY" in result.output + result.stderr
    assert not list(paths.target_paczka.rglob("*.asm"))


def test_a_different_plan_than_accepted_is_refused(workspace, plan_file) -> None:
    """Zgoda człowieka dotyczy KONKRETNEGO planu, nie „planu w ogóle”."""
    paths, _ = workspace
    plan, digest, _ = plan_file

    result = run(plan, "--db", str(paths.work_db), "--yes", "--expect-hash", "f" * 64)

    assert result.exit_code == 2
    assert "ODMOWA" in result.output + result.stderr
    assert not list(paths.target_paczka.rglob("*.asm"))


def test_a_conflict_stops_the_whole_run(workspace, plan_file) -> None:
    """Jedna kolizja zatrzymuje CAŁY przebieg — żadnych częściowych zapisów."""
    paths, _ = workspace
    plan, _, rows = plan_file
    target = paths.target_repo / rows[0]["target_rel"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"recznie ulozony material")

    result = run(plan, "--db", str(paths.work_db), "--yes")

    assert result.exit_code == 2
    assert target.read_bytes() == b"recznie ulozony material"
    assert not (paths.target_repo / rows[1]["target_rel"]).exists()


def test_running_apply_twice_changes_nothing(workspace, plan_file) -> None:
    paths, _ = workspace
    plan, _, rows = plan_file
    run(plan, "--db", str(paths.work_db), "--yes")
    target = paths.target_repo / rows[0]["target_rel"]
    stamp = target.stat().st_mtime_ns

    result = run(plan, "--db", str(paths.work_db), "--yes")

    assert result.exit_code == 0, result.output
    assert "skopiowano: 0" in result.output
    assert target.stat().st_mtime_ns == stamp


def test_apply_does_not_commit_materials(workspace, plan_file) -> None:
    """Commit należy do człowieka PO `verify` — apply ma zostawić zmiany w drzewie."""
    paths, _ = workspace
    plan, _, _ = plan_file
    subprocess.run(["git", "init", "-q", "-b", "subject/AKO", str(paths.target_repo)], check=True)
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(paths.target_repo), "config", key, value], check=True)
    (paths.target_repo / "README.md").write_text("paczka\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(paths.target_repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(paths.target_repo), "commit", "-qm", "init"], check=True)

    result = runner.invoke(apply_cli.app, [
        "--semester", "3", "--skrot", "AKO", "--plan", str(plan),
        "--db", str(paths.work_db), "--yes",
    ])

    assert result.exit_code == 0, result.output
    log = subprocess.run(["git", "-C", str(paths.target_repo), "log", "--oneline"],
                         capture_output=True, text=True)
    # Jedyny commit to ten z fixture'u — `apply` nie dołożył własnego.
    assert len(log.stdout.strip().splitlines()) == 1
    assert log.stdout.strip().endswith("init")
    status = subprocess.run(["git", "-C", str(paths.target_repo), "status", "--porcelain"],
                            capture_output=True, text=True)
    assert "paczka/" in status.stdout


def test_the_wrong_branch_refuses_to_apply(workspace, plan_file) -> None:
    """Jeden przedmiot = jedna gałąź; kopiowanie na cudzą gałąź to odmowa."""
    paths, _ = workspace
    plan, _, _ = plan_file
    subprocess.run(["git", "init", "-q", "-b", "master", str(paths.target_repo)], check=True)

    result = runner.invoke(apply_cli.app, [
        "--semester", "3", "--skrot", "AKO", "--plan", str(plan),
        "--db", str(paths.work_db), "--yes",
    ])

    assert result.exit_code == 2
    assert "subject/AKO" in result.output + result.stderr
    assert not list(paths.target_paczka.rglob("*.asm"))
