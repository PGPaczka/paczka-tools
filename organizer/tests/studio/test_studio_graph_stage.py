"""Q1: przebudowa grafu ze studia — bez wychodzenia do terminala."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api import runner
from studio.api.app import create_app


def test_graph_rebuild_is_two_commands_export_then_generator(tmp_path) -> None:
    """Dane grafu powstają w dwóch krokach i tylko te dwa są potrzebne.

    Budowania frontu NIE ma w tej liście celowo: viewer czyta `graph.json` z `work`
    przy starcie, więc po zmianie decyzji wystarczy odświeżyć DANE (zgłoszone
    2026-09-24: „czy jak coś wyklikam, to odświeży się na grafie").
    """
    komendy = runner.graph_commands(db_path=tmp_path / "index.sqlite")

    assert len(komendy) == 2
    eksport, generator = komendy
    assert eksport[1].endswith("synapse_export.py")
    assert "dotnet" in generator[0]
    assert "--no-git" in generator


def test_graph_rebuild_passes_absolute_paths(tmp_path) -> None:
    """Ścieżki są bezwzględne, bo generator startuje z innym katalogiem roboczym."""
    _, generator = runner.graph_commands(db_path=tmp_path / "index.sqlite")

    vault = Path(generator[generator.index("--vault") + 1])
    out = Path(generator[generator.index("--out") + 1])

    assert vault.is_absolute() and out.is_absolute()
    assert out.name == "graph.json"
    assert vault.name == "vault"


def test_export_flags_are_accepted_by_the_real_parser(tmp_path) -> None:
    """Ten sam kontrakt co dla etapów przedmiotu: argv konfrontowane z parserem."""
    import click
    from typer.main import get_command

    import synapse_export

    eksport, _ = runner.graph_commands(db_path=tmp_path / "index.sqlite")
    komenda = get_command(synapse_export.app)
    ctx = click.Context(komenda)

    # parse_args nie uruchamia eksportu — sprawdza wyłącznie, czy flagi istnieją
    komenda.parse_args(ctx, eksport[2:])


def _ramki(strumien) -> list[str]:
    return [frag for frag in strumien]


def test_chain_stops_at_the_first_failure(tmp_path) -> None:
    """Generator nie ma po co startować, gdy eksport vaulta padł.

    Uruchomiony na starym vaulcie zbudowałby graf ze STARYCH danych i wyglądałoby to
    na sukces — najgorszy możliwy wynik przy odświeżaniu widoku.
    """
    padnij = [sys.executable, "-c", "import sys; print('eksport padł'); sys.exit(3)"]
    nie_ruszaj = [sys.executable, "-c", "print('TEGO NIE POWINNO BYĆ')"]

    tekst = "".join(_ramki(runner.stream_all([padnij, nie_ruszaj])))

    assert "eksport padł" in tekst
    assert "TEGO NIE POWINNO BYĆ" not in tekst
    assert '"code": 3' in tekst


def test_chain_reports_one_done_when_both_succeed() -> None:
    ok = [sys.executable, "-c", "print('gotowe')"]

    tekst = "".join(_ramki(runner.stream_all([ok, ok])))

    assert tekst.count("event: done") == 1
    assert '"code": 0' in tekst


# --- endpoint HTTP ----------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Workspace w kształcie, jaki daje `config/paths.yaml` — jak w pozostałych testach."""
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    paths.work_thumbnails.mkdir(parents=True)
    db.connect(paths.work_db).close()
    return paths


@pytest.fixture
def client(workspace):
    app = create_app(workspace.work_db, paths=workspace, subjects=[], thresholds={})
    # Kontekst, a nie samo `TestClient(app)`: dopiero on uruchamia lifespan, czyli
    # sprawdzenie `schema_version`. Bez tego test omija połowę tego, co robi start.
    with TestClient(app) as test_client:
        yield test_client


def test_rebuild_endpoint_streams_the_log(client, monkeypatch) -> None:
    """Przebudowa idzie POST-em i oddaje log oraz kod wyjścia tym samym kanałem co etapy."""
    monkeypatch.setattr(
        runner, "graph_commands",
        lambda *, db_path, work_dir=None: [[sys.executable, "-c", "print('gotowe')"]],
    )

    response = client.post("/api/graph/rebuild")

    assert response.status_code == 200
    assert "gotowe" in response.text
    assert "event: done" in response.text and '"code": 0' in response.text


def test_rebuild_accepts_only_post(client) -> None:
    """Przebudowa zapisuje do `work`, więc nie może wisieć pod GET-em.

    Sprawdzamy TABLICĘ TRAS, a nie kod odpowiedzi na GET: studio montuje statyczny
    front pod `/`, więc każdy nietrafiony GET kończy się i tak czterysta czwórką —
    taki test przechodziłby również wtedy, gdyby endpointu w ogóle nie było.
    """
    trasy = [r for r in client.app.routes if getattr(r, "path", None) == "/api/graph/rebuild"]

    assert trasy, "endpoint przebudowy zniknął z aplikacji"
    assert trasy[0].methods == {"POST"}
