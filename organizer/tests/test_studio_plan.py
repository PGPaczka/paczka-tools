"""S3: plan, bramka i wykonanie z poziomu studia.

Najważniejszy test w tym pliku to ten, w którym **żądanie `apply` przy planie
odrzuconym przez bramkę kończy się odmową po stronie serwera** — nie wyszarzeniem
przycisku. Ukrycie przycisku nie jest zabezpieczeniem (``studio/AGENTS.md``,
reguła 6), a żeby to naprawdę sprawdzić, trzeba wysłać żądanie tak, jak zrobiłby
to ktoś, kto interfejsu nie używa.

Etapy uruchamiamy jako PRAWDZIWY podproces CLI (tak jak studio w produkcji), więc
te testy chodzą po realnych skryptach `apply.py`/`validate_plan.py` — atrapa
pokazałaby tylko, co studio zamierza wywołać.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

from orglib import config, db
from orglib.hashes import sha256_file
from studio.api import planning, runner
from studio.api.app import create_app
from tests.test_apply import CONTENT, SUBJECT_DIR, _row, _write_plan

THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [
    config.Subject(
        semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W", "C", "L"),
        aliases=(), instancja=None, strumien=None, profil=None, katedra=None,
    )
]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Źródła, repo docelowe, baza i katalog raportów — jak u `apply`, ale dla studia."""
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    (paths.sources / "P" / "SEM3").mkdir(parents=True)
    paths.target_paczka.mkdir(parents=True)
    # Repo docelowe jest prawdziwym klonem na gałęzi przedmiotu — `apply` sprawdza
    # to u siebie i studio nie ma żadnej drogi, żeby ten warunek ominąć.
    subprocess.run(["git", "init", "-q", "-b", "subject/AKO", str(paths.target_repo)], check=True)
    for key, value in (("user.email", "test@example.invalid"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(paths.target_repo), "config", key, value], check=True)
    (paths.target_repo / "README.md").write_text("paczka\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(paths.target_repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(paths.target_repo), "commit", "-qm", "init"], check=True)
    # `reports/{SKROT}` liczy się względem ORGANIZER_ROOT — podstawiamy katalog testu,
    # żeby plan nie lądował w repo.
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    monkeypatch.setattr(planning.config, "ORGANIZER_ROOT", tmp_path / "organizer")

    # Etapy idą PRAWDZIWYM podprocesem, a jego nie da się monkeypatchować: własny
    # katalog konfiguracji jest jedynym sposobem, żeby `apply` w teście widział
    # workspace z tmp_path, a nie prawdziwe materiały.
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("subjects", "syntax", "thresholds"):
        shutil.copy2(config.CONFIG_DIR / f"{name}.yaml", config_dir / f"{name}.yaml")
    (config_dir / "paths.yaml").write_text(
        yaml.safe_dump({
            "sources": str(paths.sources), "work": str(paths.work),
            "media": str(paths.media), "target_repo": str(paths.target_repo),
            "target_paczka_subdir": "paczka", "work_db": "index.sqlite",
            "work_extracted_text": "extracted_text", "work_thumbnails": "thumbnails",
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv(config.CONFIG_DIR_ENV, str(config_dir))

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


def write_plan(workspace, rows) -> str:
    paths, _ = workspace
    plan = config.ORGANIZER_ROOT / "reports" / "AKO" / "plan.jsonl"
    return _write_plan(plan, rows)


def good_rows(shas) -> list[dict]:
    return [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/wspólne/lab_03/lab_3.5.asm"),
        _row(shas["b"], f"{SUBJECT_DIR}/laboratoria/wspólne/lab_03/lab_3.6.asm"),
    ]


@pytest.fixture
def client(workspace):
    paths, _ = workspace
    app = create_app(paths.work_db, paths=paths, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as test_client:
        yield test_client


def frames(response) -> list[tuple[str, dict]]:
    """Rozbiera strumień SSE na (zdarzenie, ładunek)."""
    out: list[tuple[str, dict]] = []
    for chunk in response.text.split("\n\n"):
        match = re.match(r"event: (\w+)\ndata: (.*)", chunk.strip(), re.DOTALL)
        if match:
            out.append((match.group(1), json.loads(match.group(2))))
    return out


def exit_code(response) -> int:
    done = [payload for event, payload in frames(response) if event == "done"]
    assert done, f"etap nie zakończył się ramką done: {response.text[:400]}"
    return int(done[-1]["code"])


# --- S3.1/S3.3/S3.4: co widok wie przed decyzją ---------------------------

def test_without_a_plan_there_is_nothing_to_apply(client) -> None:
    body = client.get("/api/plan/3/AKO").json()

    assert body["plan"] is None
    assert body["can_apply"] is False and "brak planu" in body["reason"]


def test_a_clean_plan_reports_what_would_land_in_the_package(client, workspace) -> None:
    paths, shas = workspace
    digest = write_plan(workspace, good_rows(shas))

    body = client.get("/api/plan/3/AKO").json()

    assert body["plan"]["plan_hash"] == digest and body["plan"]["items"] == 2
    assert body["validation"]["blocking"] == 0
    assert body["diff"]["new"] == 2 and body["diff"]["conflict"] == 0
    assert body["can_apply"] is True


def test_a_rejected_plan_says_so_instead_of_offering_apply(client, workspace) -> None:
    paths, shas = workspace
    write_plan(workspace, [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/x.asm", confidence=0.2, needs_review=True)
    ])

    body = client.get("/api/plan/3/AKO").json()

    assert body["validation"]["blocking"] > 0
    assert body["can_apply"] is False
    assert body["validation"]["findings"][0]["level"] == "error"


def test_content_already_in_the_package_is_not_a_second_copy(client, workspace) -> None:
    paths, shas = workspace
    rows = good_rows(shas)
    write_plan(workspace, rows)
    target = paths.target_repo / rows[0]["target_rel"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(CONTENT["a"])

    body = client.get("/api/plan/3/AKO").json()

    assert body["diff"]["present"] == 1 and body["diff"]["new"] == 1


def test_a_foreign_file_under_the_target_path_blocks_apply(client, workspace) -> None:
    paths, shas = workspace
    rows = good_rows(shas)
    write_plan(workspace, rows)
    target = paths.target_repo / rows[0]["target_rel"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"recznie ulozony material")

    body = client.get("/api/plan/3/AKO").json()

    assert body["diff"]["conflict"] == 1
    assert body["can_apply"] is False
    assert body["diff"]["blockers"][0]["state"] == "conflict"


def test_the_tree_shows_the_plan_and_the_ground_truth_side_by_side(client, workspace) -> None:
    paths, shas = workspace
    rows = good_rows(shas)
    write_plan(workspace, rows + [
        _row(shas["a"], f"{SUBJECT_DIR}/inne/nieznane.asm", action="skip", needs_review=True),
    ])
    conn = db.connect(paths.work_db)
    db.record_applied(conn, {
        "target_relative_path": f"{SUBJECT_DIR}/egzamin/stary.pdf", "sha256": shas["b"],
        "action": "copy", "plan_hash": "ground_truth:1:1", "applied_at": "2026-01-01T00:00:00Z",
    })
    conn.commit()
    conn.close()

    tree = client.get("/api/plan/3/AKO/tree").json()

    states = {
        entry["state"]
        for folder in tree["folders"]
        for entry in folder["files"]
    }
    assert states == {"new", "ground_truth"}
    assert [item["action"] for item in tree["homeless"]] == ["skip"]


# --- S3.6: bramka jest po stronie serwera ---------------------------------

def test_apply_of_a_rejected_plan_is_refused_by_the_server(client, workspace) -> None:
    """Sedno S3: żądanie wysłane z pominięciem interfejsu też musi się odbić."""
    paths, shas = workspace
    digest = write_plan(workspace, [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/x.asm", confidence=0.2, needs_review=True)
    ])

    response = client.post(
        "/api/plan/3/AKO/run",
        json={"stage": "apply", "confirm": True, "plan_hash": digest},
    )

    assert response.status_code == 409
    assert "bramki" in json.dumps(response.json(), ensure_ascii=False)
    assert not list(paths.target_paczka.rglob("*.asm")), "bramka przepuściła kopiowanie"


def test_apply_without_confirmation_does_not_start(client, workspace) -> None:
    paths, shas = workspace
    digest = write_plan(workspace, good_rows(shas))

    response = client.post("/api/plan/3/AKO/run", json={"stage": "apply", "plan_hash": digest})

    assert response.status_code == 409 and "potwierdzenia" in response.json()["detail"]
    assert not list(paths.target_paczka.rglob("*.asm"))


def test_confirmation_is_bound_to_a_concrete_plan(client, workspace) -> None:
    """Plan przebudowany po akceptacji nie jest „tym samym planem”."""
    paths, shas = workspace
    write_plan(workspace, good_rows(shas))

    response = client.post(
        "/api/plan/3/AKO/run",
        json={"stage": "apply", "confirm": True, "plan_hash": "f" * 64},
    )

    assert response.status_code == 409 and "innego planu" in response.json()["detail"]
    assert not list(paths.target_paczka.rglob("*.asm"))


def test_an_unknown_stage_is_not_a_command(client, workspace) -> None:
    write_plan(workspace, good_rows(workspace[1]))

    response = client.post("/api/plan/3/AKO/run", json={"stage": "rm -rf /"})

    assert response.status_code == 422


def test_build_argv_refuses_a_stage_outside_the_list() -> None:
    with pytest.raises(runner.UnknownStage):
        runner.build_argv("cokolwiek", subject=SUBJECTS[0], db_path=config.ORGANIZER_ROOT)


def test_every_stage_flag_is_accepted_by_the_real_script() -> None:
    """Argv konfrontowane z PARSEREM etapu, nie z naszym wyobrażeniem o nim.

    Powstało po wpadce z etapem `review`: studio dokładało mu `--db` i `--plan`,
    których `review_report.py` nie zna, więc etap startował i natychmiast odbijał
    się od parsera. To ta sama klasa błędu, co historyczne `--ignore-user-config`
    w backendach AI (`tests/test_cli_contract.py`).
    """
    import importlib

    from typer.testing import CliRunner as TyperRunner

    typer_runner = TyperRunner()
    for stage, spec in runner.STAGE_SCRIPTS.items():
        argv = runner.build_argv(
            stage, subject=SUBJECTS[0], db_path=config.ORGANIZER_ROOT / "x.sqlite",
            plan_path=config.ORGANIZER_ROOT / "plan.jsonl", plan_hash="abc", grupa="Wspolne",
        )
        module = importlib.import_module(spec["script"].removesuffix(".py"))
        help_text = typer_runner.invoke(module.app, ["--help"]).output
        flags = {part for part in argv if part.startswith("--")}
        unknown = {flag for flag in flags if flag not in help_text}
        assert not unknown, f"etap {stage}: {spec['script']} nie zna {sorted(unknown)}"


def test_apply_argv_carries_the_confirmation_and_the_hash() -> None:
    argv = runner.build_argv(
        "apply", subject=SUBJECTS[0], db_path=config.ORGANIZER_ROOT / "x.sqlite",
        plan_path=config.ORGANIZER_ROOT / "plan.jsonl", plan_hash="abc123",
    )

    assert "--yes" in argv and argv[argv.index("--expect-hash") + 1] == "abc123"
    assert argv[1].endswith("apply.py")


# --- S3.5: etapy jako podproces CLI ---------------------------------------

def test_validate_runs_as_a_subprocess_and_streams_its_output(client, workspace) -> None:
    write_plan(workspace, good_rows(workspace[1]))

    response = client.post("/api/plan/3/AKO/run", json={"stage": "validate"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = [payload["text"] for event, payload in frames(response) if event == "line"]
    assert any("plan przechodzi walidację" in line for line in lines), lines
    assert exit_code(response) == 0


def test_a_rejected_plan_comes_back_with_exit_code_2(client, workspace) -> None:
    """Kod wyjścia etapu jest wynikiem, nie treść logu."""
    paths, shas = workspace
    write_plan(workspace, [
        _row(shas["a"], f"{SUBJECT_DIR}/laboratoria/x.asm", confidence=0.2, needs_review=True)
    ])

    response = client.post("/api/plan/3/AKO/run", json={"stage": "validate"})

    assert exit_code(response) == 2


def test_apply_of_a_clean_plan_copies_through_the_real_cli(client, workspace) -> None:
    paths, shas = workspace
    rows = good_rows(shas)
    digest = write_plan(workspace, rows)

    response = client.post(
        "/api/plan/3/AKO/run",
        json={"stage": "apply", "confirm": True, "plan_hash": digest},
    )

    assert exit_code(response) == 0, response.text
    for row in rows:
        target = paths.target_repo / row["target_rel"]
        assert target.is_file() and sha256_file(target) == row["source_sha256"]

    after = client.get("/api/plan/3/AKO").json()
    assert after["diff"]["present"] == 2 and after["diff"]["new"] == 0
