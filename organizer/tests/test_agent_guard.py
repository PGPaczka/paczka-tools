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
    # Mutacja jest tu poza źródłami: one-liner czyta 00_SOURCES, a zapisuje do /tmp.
    # Guard patrzy na argumenty wywołania, nie na sam fakt zapisu w komendzie.
    pytest.param(
        "python3 -c \"import pathlib;"
        " open('/tmp/raport.txt','w').write(str(list(pathlib.Path('../../00_SOURCES').iterdir())))\"",
        id="python-read-sources-write-elsewhere",
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
