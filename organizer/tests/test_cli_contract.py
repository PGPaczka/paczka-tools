"""Kontrakt z ZEWNĘTRZNYMI CLI: czy komendy, które budujemy, są w ogóle przyjmowane.

Reszta testów backendów AI podmienia `runner`, więc sprawdza, co kod *zamierza*
wywołać. Tego jest za mało i projekt zapłacił już za tę lukę: backend `codex_cli`
budował `codex --ignore-user-config exec …`, a w codex-cli 0.154 ta flaga należy
do podkomendy `exec`. Prawdziwe CLI odbijało wywołanie z `error: unexpected
argument`, backend **nigdy nie zadziałał end-to-end**, a wszystkie testy z atrapą
świeciły na zielono. Audyt 2026-09-18 potwierdził, że to samo przeszłoby ponownie:
wstrzyknięcie nieistniejącej flagi do trzech backendów naraz nie oblało żadnego
z 33 testów.

Te testy NIE wysyłają promptu i NIE kosztują tokenów: argv przechwytujemy
atrapą runnera, a potem konfrontujemy je z parserem binarki (`--help`).

Dwa poziomy kontroli, bo CLI różnią się zachowaniem parsera:

1. **Każda długa flaga musi występować w pomocy binarki** — łapie flagę usuniętą
   albo przemianowaną w nowej wersji narzędzia. Działa dla wszystkich trzech.
2. **Parser musi przyjąć całe argv** — łapie dodatkowo złe MIEJSCE flagi
   (dokładnie historyczna wpadka). Możliwe tylko tam, gdzie CLI waliduje
   argumenty mimo `--help`; test sam to wykrywa i pomija poziom 2 dla CLI,
   które przy `--help` połykają wszystko (dziś: `claude`, `agy`).

Marker `cli_contract`: wymaga zainstalowanych CLI, więc jest osobno od testów
kontraktu kodu — ale jak cała warstwa środowiskowa, brak narzędzia ma być
CZERWONY, nie pominięty.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orglib.llm_client import LLMClient, LLMConfig

pytestmark = pytest.mark.cli_contract

#: Backend -> binarka i ewentualna podkomenda, od której zaczyna się argv.
BACKENDS: dict[str, str] = {
    "claude_cli": "claude",
    "codex_cli": "codex",
    "agy_cli": "agy",
}

#: Limit czasu na wywołanie pomocy CLI.
_HELP_TIMEOUT_S = 60


class _ArgvCapture:
    """Atrapa runnera: zapamiętuje argv i zwraca minimalną poprawną odpowiedź."""

    def __init__(self) -> None:
        self.argv: list[str] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.argv = list(argv)
        # codex zapisuje wynik do pliku wskazanego przez `-o`; reszta czyta stdout.
        if "-o" in argv:
            out_index = argv.index("-o")
            if out_index + 1 < len(argv):
                Path(argv[out_index + 1]).write_text('{"ok": true}', encoding="utf-8")
        # Jedna odpowiedź spełniająca wymagania wszystkich trzech backendów:
        # claude czyta `result`, agy wymaga `status`/`response`, codex pliku z `-o`.
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"status": "SUCCESS", "result": "{}", "response": "{}"}', stderr=""
        )


def capture_argv(backend: str, tmp_path: Path) -> list[str]:
    """Zwraca argv, które produkcyjny kod ZBUDOWAŁBY dla danego backendu."""
    capture = _ArgvCapture()
    cfg = LLMConfig(
        default_backend=backend,
        max_text_head_bytes=2048,
        timeout_s=300,
        cache=False,
        task_overrides={},
    )
    client = LLMClient(cfg, cache_path=tmp_path / "cache.sqlite", runner=capture)
    client.complete("classify", "prompt testowy", json=True)
    assert capture.argv, f"backend {backend} nie zbudował żadnej komendy"
    return capture.argv


def run_help(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Uruchamia binarkę z podanym argv; nic nie wysyła, bo ostatni argument to --help."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=_HELP_TIMEOUT_S)


def help_text(binary: str, subcommand: str | None) -> str:
    """Pomoc binarki (i podkomendy, jeśli jest) jako jeden tekst."""
    argv = [binary] + ([subcommand] if subcommand else []) + ["--help"]
    completed = run_help(argv)
    return completed.stdout + completed.stderr


def parser_validates_with_help(binary: str, subcommand: str | None) -> bool:
    """Czy CLI zgłasza nieznaną flagę mimo ``--help`` (wtedy da się sprawdzić całe argv)."""
    argv = [binary] + ([subcommand] if subcommand else [])
    argv += ["--z-pewnoscia-nieistniejaca-flaga", "--help"]
    return run_help(argv).returncode != 0


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_backend_binary_is_installed(backend: str) -> None:
    """Brak CLI backendu jest awarią środowiska, nie powodem do pominięcia testu."""
    binary = BACKENDS[backend]
    assert shutil.which(binary) is not None, (
        f"brak binarki {binary} dla backendu {backend} — patrz README, sekcja Agenci interaktywni"
    )


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_every_flag_we_pass_exists_in_the_cli(backend: str, tmp_path: Path) -> None:
    """Każda długa flaga z produkcyjnego argv występuje w pomocy zainstalowanego CLI."""
    argv = capture_argv(backend, tmp_path)
    binary = argv[0]
    subcommand = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else None
    pomoc = help_text(binary, subcommand)
    if subcommand:
        pomoc += help_text(binary, None)

    flags = [token for token in argv[1:] if token.startswith("--")]
    missing = [flag for flag in flags if flag.split("=")[0] not in pomoc]
    assert not missing, f"{binary}: flagi nieznane temu CLI: {missing}"


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_cli_parser_accepts_the_whole_command(backend: str, tmp_path: Path) -> None:
    """Parser CLI przyjmuje CAŁE argv — łapie też złe MIEJSCE flagi.

    To jest test, którego brak kosztował projekt niedziałający backend: flaga
    poprawna sama w sobie, ale podana przed podkomendą, jest odrzucana.
    """
    argv = capture_argv(backend, tmp_path)
    binary = argv[0]
    subcommand = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else None
    if not parser_validates_with_help(binary, subcommand):
        pytest.skip(
            f"{binary} przy --help nie waliduje argumentów, więc miejsca flag nie da się "
            "sprawdzić bez wysłania promptu (poziom 1 tego pliku nadal obowiązuje)"
        )

    # Prompt i ścieżki plików zastępujemy `--help`: parser sprawdzi flagi,
    # ale nic się nie wykona i nie pójdzie żadne zapytanie do modelu.
    sanitized = [token for token in argv if token != "-"]
    completed = run_help(sanitized + ["--help"])
    assert completed.returncode == 0, (
        f"{binary} odrzuca komendę budowaną przez backend {backend}: "
        f"{(completed.stderr or completed.stdout).strip()[:200]}"
    )


def test_codex_subcommand_flags_are_not_accepted_before_the_subcommand() -> None:
    """Kontrola samej metody: udowadnia, że poziom 2 naprawdę łapie złe miejsce flagi.

    Bez tego testu nie wiedzielibyśmy, czy `test_cli_parser_accepts_the_whole_command`
    cokolwiek sprawdza. Odtwarzamy historyczną wpadkę i wymagamy odrzucenia.
    """
    if shutil.which("codex") is None:
        pytest.fail("brak binarki codex — patrz test_backend_binary_is_installed")
    zle = run_help(["codex", "--ignore-user-config", "exec", "--help"])
    dobre = run_help(["codex", "exec", "--help"])
    assert dobre.returncode == 0, "poprawna komenda codex powinna przejść"
    assert zle.returncode != 0, (
        "codex przyjął flagę podkomendy podaną przed podkomendą — poziom 2 tego pliku "
        "przestał cokolwiek sprawdzać"
    )
