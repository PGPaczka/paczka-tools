"""Kontrakt launchera studia z PRAWDZIWYM procesem i prawdziwym API uvicorna.

Reszta testów studia woła funkcje w tym samym procesie, więc sprawdza, co kod
*zamierza* zrobić. Za mało: projekt zapłacił już raz za tę lukę przy backendach AI
(patrz `tests/test_cli_contract.py`) — argv budowane poprawnie „w intencji” odbijało
się od prawdziwego CLI. Tutaj sprawdzamy trzy rzeczy, których atrapa nie złapie:

1. ``python -m studio.api`` w ogóle da się uruchomić i przyjmuje nasze flagi;
2. odmowa adresu spoza pętli zwrotnej działa na poziomie PROCESU (kod wyjścia 2),
   a nie tylko funkcji;
3. słowa, którymi wołamy uvicorna, są słowami, które uvicorn zna — i serwer
   naprawdę wstaje oraz odpowiada na `/api/health`.

Testy nie wysyłają promptów i nic nie kosztują; wymagają jedynie środowiska
organizera, tak jak reszta warstwy `cli_contract`.
"""

from __future__ import annotations

import inspect
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from orglib import config, db
from studio.api import server

pytestmark = [pytest.mark.cli_contract, pytest.mark.reads_repo_config]

#: Limit na wstanie serwera (import FastAPI + otwarcie bazy).
_BOOT_TIMEOUT_S = 30


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "studio.api", *args],
        cwd=str(cwd or config.ORGANIZER_ROOT),
        capture_output=True, text=True, timeout=120,
    )


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def index(tmp_path) -> Path:
    db_path = tmp_path / "index.sqlite"
    db.connect(db_path).close()
    return db_path


def test_the_launcher_module_runs_and_knows_our_flags() -> None:
    result = _run("--help")

    assert result.returncode == 0, result.stderr
    for flag in ("--host", "--port", "--reload", "--db", "--check"):
        assert flag in result.stdout, f"launcher nie zna flagi {flag}"


def test_a_public_address_is_refused_by_the_real_process() -> None:
    result = _run("--host", "0.0.0.0", "--check")

    assert result.returncode == 2
    assert "Odmowa startu" in result.stderr


def test_preflight_passes_on_a_fresh_index(index: Path) -> None:
    result = _run("--check", "--db", str(index))

    assert result.returncode == 0, result.stderr
    assert f"schema_version={db.SCHEMA_VERSION}" in result.stdout


def test_uvicorn_still_knows_every_word_we_call_it_with() -> None:
    """Zmiana API uvicorna ma być czerwonym testem, nie błędem przy starcie."""
    accepted = set(inspect.signature(__import__("uvicorn").run).parameters)
    options = server.uvicorn_options()

    unknown = set(options) - accepted
    assert not unknown, f"uvicorn.run nie zna argumentów: {sorted(unknown)}"


def test_the_app_factory_string_points_at_something_that_exists() -> None:
    module_name, _, attribute = server.APP_FACTORY.partition(":")
    module = __import__(module_name, fromlist=[attribute])

    assert callable(getattr(module, attribute))


def test_justfile_starts_the_launcher_we_test() -> None:
    """Przemianowanie modułu bez poprawienia `just studio` ma boleć tutaj."""
    justfile = (config.ORGANIZER_ROOT / "justfile").read_text(encoding="utf-8")
    recipes = set(re.findall(r"^([a-z][a-z0-9-]*)[^\n:]*:", justfile, re.MULTILINE))

    assert {"studio", "studio-dev"} <= recipes, f"brak recept studia: {sorted(recipes)}"
    assert justfile.count("-m studio.api") >= 2


def test_the_server_really_starts_and_answers_on_loopback(index: Path) -> None:
    import httpx

    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "studio.api", "--port", str(port), "--db", str(index),
         "--log-level", "warning"],
        cwd=str(config.ORGANIZER_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env={**os.environ},
    )
    try:
        deadline = time.monotonic() + _BOOT_TIMEOUT_S
        body = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"serwer padł przy starcie:\n{process.stdout.read()}")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2.0)
            except httpx.TransportError:
                time.sleep(0.2)
                continue
            assert response.status_code == 200
            body = response.json()
            break
        assert body is not None, "serwer nie odpowiedział w limicie czasu"
        assert body["schema_version"] == db.SCHEMA_VERSION
        assert body["db"] == str(index)

        # Endpointy danych chodzą przez pulę wątków uvicorna — w procesie testowym
        # (TestClient) ten sam kod wykonywał się w jednym wątku i przepuścił błąd
        # połączenia sqlite3 przenoszonego między wątkami. Stąd te trzy żądania.
        for path in ("/api/subjects", "/api/items?limit=5", "/api/items?needs_review=true"):
            data = httpx.get(f"http://127.0.0.1:{port}{path}", timeout=30.0)
            assert data.status_code == 200, f"{path}: {data.status_code} {data.text[:200]}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - serwer nie zareagował
            process.kill()
