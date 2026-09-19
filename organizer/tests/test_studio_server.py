"""S0.7: studio nie wystawia indeksu na sieć — i to jest sprawdzane, nie deklarowane.

Cała reszta bezpieczeństwa tego narzędzia opiera się na jednym założeniu: słucha
tylko pętla zwrotna, więc nie ma kont, autoryzacji ani CORS-a. Jeśli ta bramka
kiedyś zmieni się w ostrzeżenie, pozostałe decyzje przestaną się bronić — dlatego
odmowa jest testowana od strony funkcji, launchera i wywołania uvicorna.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from studio.api import server
from studio.api.__main__ import cli

runner = CliRunner()


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "[::1]", "localhost", "LocalHost"])
def test_loopback_addresses_are_allowed(host: str) -> None:
    assert server.ensure_loopback(host) == host.strip()


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.1", "example.com", "", "   ", "studio.local"]
)
def test_everything_outside_the_loopback_is_refused(host: str) -> None:
    with pytest.raises(server.AddressRefused):
        server.ensure_loopback(host)


def test_a_hostname_is_not_resolved_through_dns() -> None:
    """O tym, czy serwer stoi na loopbacku, nie może decydować /etc/hosts ani DNS."""
    with pytest.raises(server.AddressRefused, match="literałem IP"):
        server.ensure_loopback("moja-maszyna.lan")


def test_uvicorn_options_pass_through_the_gate() -> None:
    options = server.uvicorn_options(host="127.0.0.1", port=9000, reload=True)

    assert options["host"] == "127.0.0.1" and options["port"] == 9000
    assert options["app"] == server.APP_FACTORY and options["factory"] is True
    assert options["reload"] is True

    with pytest.raises(server.AddressRefused):
        server.uvicorn_options(host="0.0.0.0")


def test_serve_refuses_before_uvicorn_is_touched(monkeypatch, tmp_path) -> None:
    """Odmowa ma nastąpić PRZED zajęciem gniazda — inaczej port jest już otwarty."""
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda **kwargs: pytest.fail("uvicorn wystartował"))

    with pytest.raises(server.AddressRefused):
        server.serve(host="0.0.0.0", db_path=tmp_path / "index.sqlite")


def test_factory_reads_the_database_from_the_environment(monkeypatch, tmp_path) -> None:
    """Podproces --reload nie dostaje argumentów — ścieżka bazy musi iść środowiskiem."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(server, "create_app", lambda path: seen.setdefault("path", path))
    monkeypatch.setenv(server.DB_ENV, str(tmp_path / "index.sqlite"))

    server.app_factory()

    assert str(seen["path"]) == str(tmp_path / "index.sqlite")


def test_launcher_exits_with_2_on_a_public_address() -> None:
    """Kod 2 = „nie wolno”, tak samo jak w bramce planu (validate_plan)."""
    result = runner.invoke(cli, ["--host", "0.0.0.0", "--check"])

    assert result.exit_code == 2
    assert "Odmowa startu" in result.stderr


def test_launcher_check_reports_the_database(tmp_path) -> None:
    from orglib import db

    db_path = tmp_path / "index.sqlite"
    db.connect(db_path).close()

    result = runner.invoke(cli, ["--check", "--db", str(db_path)])

    assert result.exit_code == 0
    assert f"schema_version={db.SCHEMA_VERSION}" in result.stdout


def test_launcher_check_fails_loudly_without_a_database(tmp_path) -> None:
    result = runner.invoke(cli, ["--check", "--db", str(tmp_path / "nie-ma.sqlite")])

    assert result.exit_code == 1 and "Preflight nieudany" in result.stderr
