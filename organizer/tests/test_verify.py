"""B11: `verify` liczy hash PO kopii — dopiero to uprawnia do commitu materiałów.

`apply` zapisuje audyt własnej intencji; audyt nie jest dowodem. Te testy pilnują,
że niezgodność treści i brak pliku są CZERWONE (kod 2), a nie „ostrzeżeniem”,
oraz że statusy w bazie idą na `verified` wyłącznie wtedy, gdy paczka naprawdę
zgadza się z planem.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import verify as verify_cli
from orglib import db
from orglib.hashes import sha256_file
from tests.test_apply import (  # fixture'y i wzorzec planu dzielone z B10
    CONTENT,
    SUBJECT_DIR,
    plan_file,
    run as run_apply,
    workspace,
)

runner = CliRunner()


def run_verify(plan, paths, *args: str):
    return runner.invoke(verify_cli.app, [
        "--semester", "3", "--skrot", "AKO", "--plan", str(plan),
        "--db", str(paths.work_db), *args,
    ])


@pytest.fixture
def applied(workspace, plan_file):
    """Stan po udanym `apply` — punkt wyjścia każdego z tych testów."""
    paths, shas = workspace
    plan, digest, rows = plan_file
    result = run_apply(plan, "--db", str(paths.work_db), "--yes")
    assert result.exit_code == 0, result.output
    return paths, plan, digest, rows


def statuses(paths) -> set[str]:
    conn = db.connect(paths.work_db)
    try:
        return {str(row["status"]) for row in conn.execute("SELECT status FROM files")}
    finally:
        conn.close()


def test_a_faithful_copy_passes_and_marks_files_verified(applied) -> None:
    paths, plan, digest, rows = applied

    result = run_verify(plan, paths)

    assert result.exit_code == 0, result.output
    assert "zgadza się z planem" in result.output
    assert statuses(paths) == {"verified"}
    report = (plan.parent / "verification.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(report) == len(rows)


def test_content_changed_after_apply_is_red(applied) -> None:
    """Gdyby to było ostrzeżenie, do repo trafiłby materiał inny niż zaakceptowany."""
    paths, plan, _, rows = applied
    target = paths.target_repo / rows[0]["target_rel"]
    target.write_bytes(b"podmieniona tresc")

    result = run_verify(plan, paths)

    assert result.exit_code == 2
    assert "NIE ZGADZA" in result.output + result.stderr
    assert statuses(paths) == {"applied"}, "statusy nie mogą iść dalej przy niezgodności"


def test_a_missing_file_is_red(applied) -> None:
    paths, plan, _, rows = applied
    (paths.target_repo / rows[0]["target_rel"]).unlink()

    result = run_verify(plan, paths)

    assert result.exit_code == 2
    assert "MISSING" in result.output


def test_a_file_outside_the_plan_warns_but_does_not_block(applied) -> None:
    """W katalogu przedmiotu legalnie lądują rzeczy spoza tego planu (np. B12)."""
    paths, plan, _, _ = applied
    extra = paths.target_repo / SUBJECT_DIR / "paczka_meta" / "README.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("prowenancja\n", encoding="utf-8")

    result = run_verify(plan, paths)

    assert result.exit_code == 0, result.output
    assert "pliki spoza planu: 1" in result.output

    strict = run_verify(plan, paths, "--strict")
    assert strict.exit_code == 2


def test_ground_truth_in_the_subject_folder_is_not_an_extra(applied) -> None:
    """Ręcznie ułożony materiał jest wytłumaczony tabelą `applied`, nie planem."""
    paths, plan, _, _ = applied
    ground = paths.target_repo / SUBJECT_DIR / "egzamin" / "stary.pdf"
    ground.parent.mkdir(parents=True, exist_ok=True)
    ground.write_bytes(b"%PDF-1.4 ground truth\n")
    conn = db.connect(paths.work_db)
    try:
        db.upsert_content(conn, {"sha256": sha256_file(ground), "content_kind": "pdf"})
        db.record_applied(conn, {
            "target_relative_path": f"{SUBJECT_DIR}/egzamin/stary.pdf",
            "sha256": sha256_file(ground), "action": "copy",
            "plan_hash": "ground_truth:1:1", "applied_at": "2026-09-17T00:00:00Z",
        })
        conn.commit()
    finally:
        conn.close()

    result = run_verify(plan, paths)

    assert result.exit_code == 0, result.output
    assert "pliki spoza planu: 0" in result.output


def test_verify_reads_but_does_not_change_materials(applied) -> None:
    paths, plan, _, rows = applied
    before = {
        str(path.relative_to(paths.target_repo)): (sha256_file(path), path.stat().st_mtime_ns)
        for path in sorted(paths.target_paczka.rglob("*")) if path.is_file()
    }

    run_verify(plan, paths)

    after = {
        str(path.relative_to(paths.target_repo)): (sha256_file(path), path.stat().st_mtime_ns)
        for path in sorted(paths.target_paczka.rglob("*")) if path.is_file()
    }
    assert after == before


def test_a_plan_other_than_the_verified_one_is_refused(applied) -> None:
    paths, plan, digest, _ = applied

    result = run_verify(plan, paths, "--expect-hash", "0" * 64)

    assert result.exit_code == 1
    assert "odcisk" in result.output + result.stderr
