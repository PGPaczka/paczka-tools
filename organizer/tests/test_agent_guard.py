"""Testy wspólnego hooka chroniącego 00_SOURCES."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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
