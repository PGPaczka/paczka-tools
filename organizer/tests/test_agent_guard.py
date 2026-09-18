"""Testy wspólnego hooka chroniącego 00_SOURCES.

Hook jest jedyną barierą wspólną dla Claude i Codexa, więc testy pilnują obu stron
kompromisu: mutacja źródeł ma być zablokowana także wtedy, gdy nie wygląda jak
`rm` (kod interpretera, `find -delete`, zapis wskazany flagą), a czysty odczyt ma
przechodzić — fałszywy alarm blokuje normalną pracę i uczy obchodzenia hooka.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ORGANIZER = Path(__file__).resolve().parents[1]
GUARD = ORGANIZER / ".agents" / "hooks" / "guard-sources.py"


def run_guard(tool_name: str, tool_input: dict[str, object]) -> subprocess.CompletedProcess[str]:
    event = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(ORGANIZER),
    }
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=False,
    )


def test_allows_read_only_bash_command_for_sources() -> None:
    result = run_guard("Bash", {"command": "find ../../00_SOURCES -maxdepth 1 -type d"})

    assert result.returncode == 0


def test_blocks_mutating_bash_command_for_sources() -> None:
    result = run_guard("Bash", {"command": "touch ../../00_SOURCES/forbidden"})

    assert result.returncode == 2
    assert "BLOKADA" in result.stderr


def test_blocks_claude_write_tool_for_sources() -> None:
    result = run_guard("Write", {"file_path": "../../00_SOURCES/forbidden"})

    assert result.returncode == 2
    assert "Write" in result.stderr


def test_blocks_codex_apply_patch_for_sources() -> None:
    result = run_guard(
        "apply_patch",
        {
            "command": (
                "*** Begin Patch\n"
                "*** Add File: ../../00_SOURCES/forbidden\n"
                "+bad\n"
                "*** End Patch\n"
            )
        },
    )

    assert result.returncode == 2
    assert "apply_patch" in result.stderr


#: Mutacje, które nie zawierają tokenu `rm`/`mv` i przez to przechodziły przez hook
#: do 2026-09-18. Każda z nich realnie zmienia albo kasuje materiały źródłowe.
DISGUISED_MUTATIONS = [
    pytest.param(
        "python3 -c \"import shutil; shutil.rmtree('../../00_SOURCES/x')\"",
        id="python-shutil-rmtree",
    ),
    pytest.param(
        "python3 -c \"import os; os.remove('../../00_SOURCES/x')\"",
        id="python-os-remove",
    ),
    pytest.param(
        "python3 -c \"open('../../00_SOURCES/x', 'w').write('1')\"",
        id="python-open-write",
    ),
    pytest.param(
        "python3 - <<EOF\nimport os\nos.rename('../../00_SOURCES/a', '../../00_SOURCES/b')\nEOF",
        id="python-heredoc-stdin",
    ),
    pytest.param("perl -e \"unlink('../../00_SOURCES/x')\"", id="perl-unlink"),
    pytest.param(
        "node -e \"require('fs').unlinkSync('../../00_SOURCES/x')\"",
        id="node-unlink-sync",
    ),
    pytest.param("find ../../00_SOURCES -name x -delete", id="find-delete"),
    pytest.param("cp -t ../../00_SOURCES/dir plik.txt", id="cp-target-directory"),
    pytest.param("sort plik.txt -o ../../00_SOURCES/out.txt", id="sort-output-flag"),
    pytest.param("echo x >| ../../00_SOURCES/x", id="forced-clobber-redirect"),
    # Zapis do źródeł ukryty w one-linerze, który poza tym wygląda na odczyt.
    pytest.param(
        "python3 -c \"import pathlib;"
        " pathlib.Path('../../00_SOURCES/x').write_text('nadpisane')\"",
        id="python-pathlib-write-text",
    ),
    # Wyjścia do powłoki z wnętrza kodu nie da się rzetelnie przeanalizować.
    pytest.param(
        "python3 -c \"import os; os.system('rm -rf ../../00_SOURCES/x')\"",
        id="python-shell-out",
    ),
    # Kopiowanie DO źródeł — cel jest drugim argumentem.
    pytest.param(
        "python3 -c \"import shutil; shutil.copy('/tmp/x', '../../00_SOURCES/x')\"",
        id="python-copy-into-sources",
    ),
]


@pytest.mark.parametrize("command", DISGUISED_MUTATIONS)
def test_blocks_mutation_disguised_as_non_shell_operation(command: str) -> None:
    result = run_guard("Bash", {"command": command})

    assert result.returncode == 2, f"przepuszczone: {command!r}"
    assert "BLOKADA" in result.stderr


#: Czysty odczyt źródeł. Te komendy muszą przechodzić — inaczej hook blokuje
#: normalną pracę (skan, hashowanie, ekstrakcja) i traci wiarygodność.
READ_ONLY_COMMANDS = [
    pytest.param("ls -la ../../00_SOURCES", id="ls"),
    pytest.param("grep -r wzorzec ../../00_SOURCES", id="grep"),
    pytest.param(
        "python3 -c \"print(open('../../00_SOURCES/x').read())\"",
        id="python-read",
    ),
    pytest.param(
        "python3 -c \"import pathlib; print(len(list(pathlib.Path('../../00_SOURCES').rglob('*'))))\"",
        id="python-count",
    ),
    # Archiwum ze źródeł jest tu WEJŚCIEM, a rozpakowanie idzie poza nie.
    pytest.param("tar -xf ../../00_SOURCES/a.tar -C /tmp/out", id="tar-read-from-sources"),
    pytest.param("find ../../00_SOURCES -name '*.pdf' -o -name '*.djvu'", id="find-or-expression"),
    pytest.param("cp ../../00_SOURCES/x.pdf /tmp/out/", id="copy-out-of-sources"),
    pytest.param("sha256sum ../../00_SOURCES/x.pdf", id="sha256sum"),
    pytest.param("du -sh ../../00_SOURCES", id="du"),
    pytest.param("grep -f ../../00_SOURCES/wzorce.txt plik.txt", id="grep-pattern-file"),
    # Odczyt źródeł w kodzie inline jest dozwolony, dopóki program NIE zawiera
    # czasownika mutującego — wynik wyprowadzamy przekierowaniem powłoki.
    pytest.param(
        "python3 -c \"import pathlib;"
        " print(list(pathlib.Path('../../00_SOURCES').iterdir()))\" > /tmp/raport.txt",
        id="python-read-sources-redirect-out",
    ),
    pytest.param("python3 scripts/scan.py --root ../../00_SOURCES", id="script-file-over-sources"),
    pytest.param("find ../../00_SOURCES -type f > /tmp/lista.txt", id="redirect-outside-sources"),
    # Kopiowanie ZE źródeł na zewnątrz to normalna praca pipeline'u (etap apply).
    pytest.param(
        "python3 -c \"import shutil; shutil.copy('../../00_SOURCES/x', '/tmp/x')\"",
        id="python-copy-out-of-sources",
    ),
]


@pytest.mark.parametrize("command", READ_ONLY_COMMANDS)
def test_allows_read_only_access_to_sources(command: str) -> None:
    result = run_guard("Bash", {"command": command})

    assert result.returncode == 0, f"fałszywy alarm na: {command!r} ({result.stderr.strip()})"


def test_allows_apply_patch_inside_organizer() -> None:
    result = run_guard(
        "apply_patch",
        {
            "command": (
                "*** Begin Patch\n"
                "*** Update File: README.md\n"
                "@@\n"
                "-old\n"
                "+new\n"
                "*** End Patch\n"
            )
        },
    )

    assert result.returncode == 0


# --------------------------------------------------------------------------- #
# Każde słowo z kontraktu osobno — lista jest JAWNA, nie czytana z implementacji
# --------------------------------------------------------------------------- #

#: Świadomie wypisane wprost. Parametryzacja po liście wyciągniętej z hooka
#: byłaby pusta: skrócenie listy w kodzie skróciłoby też zestaw przypadków i
#: testy dalej świeciłyby na zielono. Audyt pokazał to na żywo — listy dało się
#: wyciąć do dwóch słów przy 32 zielonych testach.
MUTATING_SHELL_WORDS = [
    "rm", "rmdir", "mv", "chmod", "chown", "chattr", "touch", "mkdir",
    "truncate", "shred", "dd", "ln", "tee", "rename", "setfacl",
]


@pytest.mark.parametrize("word", MUTATING_SHELL_WORDS)
def test_blocks_every_mutating_shell_word(word: str) -> None:
    """Każde słowo z kontraktu musi blokować samodzielnie, nie „jako grupa”."""
    result = run_guard("Bash", {"command": f"{word} ../../00_SOURCES/x"})
    assert result.returncode == 2, f"przepuszczone słowo mutujące: {word}"


#: Wywołania mutujące w kodzie podanym interpreterowi — także jawnie wypisane.
INLINE_MUTATION_CALLS = [
    "shutil.rmtree('../../00_SOURCES/x')",
    "os.remove('../../00_SOURCES/x')",
    "os.unlink('../../00_SOURCES/x')",
    "os.rmdir('../../00_SOURCES/x')",
    "os.rename('../../00_SOURCES/x', '/tmp/y')",
    "os.replace('/tmp/y', '../../00_SOURCES/x')",
    "os.chmod('../../00_SOURCES/x', 0o777)",
    "os.makedirs('../../00_SOURCES/nowy')",
    "os.truncate('../../00_SOURCES/x', 0)",
    "shutil.move('/tmp/y', '../../00_SOURCES/x')",
    "shutil.unpack_archive('/tmp/a.zip', '../../00_SOURCES')",
    "pathlib.Path('../../00_SOURCES/x').write_bytes(b'x')",
    "pathlib.Path('../../00_SOURCES/x').symlink_to('/etc/passwd')",
    "open('../../00_SOURCES/x', 'w')",
    "open('../../00_SOURCES/x', 'a')",
]


@pytest.mark.parametrize("call", INLINE_MUTATION_CALLS)
def test_blocks_every_inline_mutation_call(call: str) -> None:
    """Mutacja ukryta w kodzie interpretera jest blokowana dla każdego wywołania."""
    result = run_guard("Bash", {"command": f'python3 -c "import os, shutil, pathlib; {call}"'})
    assert result.returncode == 2, f"przepuszczone wywołanie: {call}"


# --------------------------------------------------------------------------- #
# Obejścia znalezione w audycie 2026-09-18 — każde MUSI pozostać zablokowane
# --------------------------------------------------------------------------- #

AUDIT_BYPASSES = [
    pytest.param("git -C ../../00_SOURCES clean -xfd", id="git-clean-flag-C"),
    pytest.param("git -C ../../00_SOURCES reset --hard", id="git-reset-flag-C"),
    pytest.param("git --work-tree=../../00_SOURCES checkout .", id="git-work-tree"),
    pytest.param(
        "python3 -c \"import shutil; src='../../00_SOURCES'\nshutil.rmtree(src)\"",
        id="path-hidden-in-variable",
    ),
    pytest.param(
        "python3 -c \"import os; os.chdir('../../00_SOURCES'); os.remove('x')\"",
        id="chdir-then-relative-remove",
    ),
    pytest.param("ruby -e \"File.write('../../00_SOURCES/x','y')\"", id="ruby-file-write"),
    pytest.param("cp /tmp/x ../../00_SOURCES/dir/ --no-preserve=mode", id="cp-target-not-last"),
    pytest.param("zip -r ../../00_SOURCES/a.zip /tmp/x", id="zip-into-sources"),
    pytest.param("7z a ../../00_SOURCES/a.7z /tmp/x", id="7z-into-sources"),
    pytest.param("tar -cf ../../00_SOURCES/a.tar /tmp/x", id="tar-create-into-sources"),
    pytest.param("python3 -m zipfile -e a.zip ../../00_SOURCES/dir", id="python-m-zipfile"),
]


@pytest.mark.parametrize("command", AUDIT_BYPASSES)
def test_blocks_bypasses_found_in_audit(command: str) -> None:
    """Regresja na obejściach, które przechodziły przed 2026-09-18."""
    result = run_guard("Bash", {"command": command})
    assert result.returncode == 2, f"obejście znów przechodzi: {command!r}"


# --------------------------------------------------------------------------- #
# Nazwa narzędzia i kształt wejścia nie mogą decydować o ochronie
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tool", ["Bash", "bash", "shell", "local_shell", "run_command", "Nieznane"])
def test_blocks_mutation_regardless_of_tool_name(tool: str) -> None:
    """Hosty nazywają powłokę różnie; guard ma reagować na TREŚĆ, nie na nazwę.

    Wcześniej `elif tool == "Bash"` powodował, że dla narzędzi Codeksa
    (`shell`, `local_shell`) hook kończył bez ani jednej kontroli.
    """
    result = run_guard(tool, {"command": "rm -rf ../../00_SOURCES/x"})
    assert result.returncode == 2, f"brak ochrony dla narzędzia {tool!r}"


def test_blocks_mutation_passed_as_argv_list() -> None:
    """Komenda bywa listą argumentów, nie stringiem — lista też musi być czytana."""
    result = run_guard("local_shell", {"command": ["bash", "-lc", "rm -rf ../../00_SOURCES/x"]})
    assert result.returncode == 2


def test_allows_read_regardless_of_tool_name() -> None:
    """Poszerzenie ochrony nie może zamienić się w blokadę czystego odczytu."""
    result = run_guard("local_shell", {"command": ["bash", "-lc", "ls ../../00_SOURCES"]})
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------- #
# Hook musi być PODPIĘTY — sam poprawny skrypt nikogo nie chroni
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("config_path", "tool_names"),
    [
        (ORGANIZER / ".claude" / "settings.json", ("Bash", "Write", "shell", "local_shell")),
        (ORGANIZER.parent / ".codex" / "hooks.json", ("Bash", "shell", "local_shell")),
    ],
    ids=["claude", "codex"],
)
def test_guard_is_wired_into_host_config(config_path: Path, tool_names: tuple[str, ...]) -> None:
    """Config hosta wywołuje guarda i jego matcher obejmuje narzędzia powłoki.

    Bez tego testu skasowanie sekcji `hooks` zostawiało cały zestaw zielonym,
    a ochrona źródeł znikała po cichu.
    """
    import re

    data = json.loads(config_path.read_text(encoding="utf-8"))
    entries = data.get("hooks", {}).get("PreToolUse", [])
    guarding = [
        entry for entry in entries
        if any("guard-sources" in hook.get("command", "") for hook in entry.get("hooks", []))
    ]
    assert guarding, f"{config_path} nie wywołuje guard-sources.py"
    for name in tool_names:
        assert any(
            re.fullmatch(entry.get("matcher", ""), name) for entry in guarding
        ), f"{config_path}: matcher nie obejmuje narzędzia {name!r}"
