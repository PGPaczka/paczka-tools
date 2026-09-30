"""Etapy INDEKSU w studiu + blokada „jeden etap na raz”.

Dwie rzeczy, których wcześniej nie było i których atrapa nie złapie:

1. `scan`, `hash`, `extract` i `status` nie znają `--semester/--skrot`, więc mają
   własne budowanie argv — i ono też musi być skonfrontowane z PRAWDZIWYM parserem
   skryptu, nie z naszym wyobrażeniem o nim (ta sama klasa błędu, co historyczne
   `--ignore-user-config` w backendach AI).
2. Dopóki etapy wpisywało się z konsoli, równoległości pilnowała jedna para rąk.
   Z przyciskami w przeglądarce uruchomienie dwóch naraz to jedno kliknięcie, a one
   piszą do tej samej bazy — więc drugi musi dostać odmowę i **nie wystartować**.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner as TyperRunner

from orglib import config, db
from studio.api import runner
from studio.api.app import create_app

THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [
    config.Subject(
        semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W", "C", "L"),
        aliases=(), instancja=None, strumien=None, profil=None, katedra=None,
    )
]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "index.sqlite"
    db.connect(db_path).close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _wolna_blokada():
    """Blokada jest stanem MODUŁU, więc test, który ją zostawi zajętą, wywraca
    wszystkie następne. Zwalniamy przed i po."""
    runner.release()
    yield
    runner.release()


# --- argv etapów indeksu --------------------------------------------------

def test_global_argv_refuses_a_stage_outside_the_list() -> None:
    with pytest.raises(runner.UnknownStage):
        runner.build_global_argv("cokolwiek", db_path=config.ORGANIZER_ROOT / "x.sqlite")


def test_subject_stages_and_index_stages_do_not_overlap() -> None:
    """Jedna nazwa w dwóch listach znaczyłaby dwie różne komendy pod tym samym
    słowem — a nazwa etapu przychodzi z sieci."""
    assert not set(runner.STAGE_SCRIPTS) & set(runner.GLOBAL_STAGE_SCRIPTS)


def test_every_index_stage_flag_is_accepted_by_the_real_script() -> None:
    typer_runner = TyperRunner()
    for stage, spec in runner.GLOBAL_STAGE_SCRIPTS.items():
        argv = runner.build_global_argv(
            stage, db_path=config.ORGANIZER_ROOT / "x.sqlite", ocr_images=True,
        )
        module = importlib.import_module(spec["script"].removesuffix(".py"))
        help_text = typer_runner.invoke(module.app, ["--help"]).output
        flags = {part for part in argv if part.startswith("--")}
        unknown = {flag for flag in flags if flag not in help_text}
        assert not unknown, f"etap {stage}: {spec['script']} nie zna {sorted(unknown)}"


def test_ocr_images_is_only_for_extract() -> None:
    """`--ocr-images` zna wyłącznie `extract_text.py`; podanie go gdzie indziej
    odbiłoby się od parsera, więc nie wolno go przepuszczać „dla symetrii”."""
    assert "--ocr-images" in runner.build_global_argv(
        "extract", db_path=config.ORGANIZER_ROOT / "x.sqlite", ocr_images=True
    )
    assert "--ocr-images" not in runner.build_global_argv(
        "extract", db_path=config.ORGANIZER_ROOT / "x.sqlite"
    )
    assert "--ocr-images" not in runner.build_global_argv(
        "scan", db_path=config.ORGANIZER_ROOT / "x.sqlite", ocr_images=True
    )


# --- limity czasu ---------------------------------------------------------

def test_long_stages_get_more_than_the_default_hour() -> None:
    """`extract --ocr-images` zajął na tym indeksie 2977 s, czyli 83% domyślnej
    godziny — pierwszy większy zestaw źródeł zostałby ubity w połowie."""
    assert runner.timeout_for("extract") > runner.TIMEOUT_S
    assert runner.timeout_for("scan") > runner.TIMEOUT_S
    assert runner.timeout_for("validate") == runner.TIMEOUT_S


# --- blokada „jeden etap na raz” ------------------------------------------

def test_second_stage_is_refused_while_one_runs(client) -> None:
    runner.acquire("udawany etap")

    response = client.post("/api/pipeline/run", json={"stage": "status"})

    assert response.status_code == 409
    assert "udawany etap" in response.json()["detail"]


def test_refused_stage_does_not_start_a_subprocess(client, monkeypatch) -> None:
    """Odmowa ma zapaść ZANIM cokolwiek ruszy. Gdyby proces wystartował i zaraz
    zginął, w logu wyglądałoby to na awarię skryptu, a nie na zajętą bazę."""
    starty: list[list[str]] = []
    monkeypatch.setattr(
        runner, "stream", lambda argv, **kw: starty.append(list(argv)) or iter(()),
    )
    runner.acquire("udawany etap")

    assert client.post("/api/pipeline/run", json={"stage": "status"}).status_code == 409
    assert starty == []


def test_subject_stage_is_refused_while_an_index_stage_runs(client) -> None:
    """Blokada jest jedna na CAŁE studio, nie jedna na trasę: `classify` jednego
    przedmiotu i `extract` całego indeksu piszą do tej samej bazy."""
    runner.acquire("extract (indeks)")

    response = client.post("/api/plan/3/AKO/run", json={"stage": "plan"})

    assert response.status_code == 409
    assert "extract (indeks)" in response.json()["detail"]


def test_the_lock_is_released_when_the_stream_ends(client) -> None:
    """Inaczej pierwszy uruchomiony etap blokuje studio aż do restartu."""
    assert runner.running() is None

    response = client.post("/api/pipeline/run", json={"stage": "status"})

    assert response.status_code == 200
    assert runner.running() is None


def test_the_lock_is_released_when_the_browser_drops_the_stream() -> None:
    """Ten przypadek jest ważniejszy niż zwykły koniec: zamknięcie karty w trakcie
    `extract` nie może zostawić studia zablokowanego na kilka godzin.

    Sprawdzane na samym opakowaniu, nie przez `TestClient`: klient jest synchroniczny
    i szybki etap zdąży się skończyć, zanim da się cokolwiek zaobserwować w trakcie.
    """
    def niekonczacy_sie():
        while True:
            yield "event: line\ndata: {}\n\n"

    runner.acquire("udawany długi etap")
    strumien = runner.released_after(niekonczacy_sie())
    next(strumien)
    assert runner.running() == "udawany długi etap"

    strumien.close()  # to robi przeglądarka, zamykając połączenie

    assert runner.running() is None


def test_unknown_index_stage_is_422_and_leaves_the_lock_free(client) -> None:
    response = client.post("/api/pipeline/run", json={"stage": "rm -rf"})

    assert response.status_code == 422
    assert runner.running() is None


def test_pipeline_state_lists_stages_and_what_runs(client) -> None:
    body = client.get("/api/pipeline").json()

    assert [entry["stage"] for entry in body["stages"]] == list(runner.GLOBAL_STAGE_SCRIPTS)
    assert body["running"] is None

    runner.acquire("scan (indeks)")
    assert client.get("/api/pipeline").json()["running"] == "scan (indeks)"
