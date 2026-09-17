#!/usr/bin/env python3
"""Cross-agent PreToolUse guard: 00_SOURCES jest READ-ONLY.

Skrypt obsługuje format hooków Claude Code i Codex. Ścieżkę źródeł bierze z
config/paths.yaml, więc nie zawiera zależnych od maszyny ścieżek.
"""

from __future__ import annotations

import json
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ORGANIZER = os.path.abspath(os.path.join(HERE, "..", ".."))


def read_sources_path() -> str | None:
    cfg = os.path.join(ORGANIZER, "config", "paths.yaml")
    try:
        with open(cfg, encoding="utf-8") as handle:
            for line in handle:
                match = re.match(r"^\s*sources\s*:\s*([^#\n]+)", line)
                if match:
                    raw = match.group(1).strip().strip("'\"")
                    return os.path.realpath(os.path.join(ORGANIZER, raw))
    except OSError:
        pass
    return None


def block(reason: str) -> None:
    sys.stderr.write(
        f"guard-sources: BLOKADA — {reason}. "
        "00_SOURCES jest READ-ONLY (AGENTS.md, reguła 1).\n"
    )
    sys.exit(2)


def contains_source_marker(value: str, markers: list[str]) -> bool:
    return any(marker in value for marker in markers)


def guard_file_path(
    tool: str,
    tool_input: dict[str, object],
    sources: str,
    cwd: str,
) -> None:
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not isinstance(raw_path, str) or not raw_path:
        return
    real = os.path.realpath(raw_path if os.path.isabs(raw_path) else os.path.join(cwd, raw_path))
    if real == sources or real.startswith(sources + os.sep):
        block(f"{tool} na {raw_path}")


def guard_patch(command: str, markers: list[str]) -> None:
    for line in command.splitlines():
        match = re.match(r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$", line)
        if not match:
            match = re.match(r"^\*\*\* Move to:\s*(.+)$", line)
        if match and contains_source_marker(match.group(1), markers):
            block(f"apply_patch na {match.group(1)}")


def guard_bash(command: str, markers: list[str]) -> None:
    if not contains_source_marker(command, markers):
        return

    hard = (
        r"(^|[;&|(\s])"
        r"(rm|rmdir|mv|chmod|chown|chattr|touch|mkdir|truncate|shred|dd|ln|tee|rename|setfacl)"
        r"(\s|$)"
    )
    if re.search(hard, command):
        block(f"komenda mutująca w obrębie źródeł: {command[:120]}")
    if re.search(r"(^|\s)(sed|perl)\s+(-[a-zA-Z]*i|--in-place)", command):
        block("edycja in-place w obrębie źródeł")

    for match in re.finditer(r">{1,2}\s*([^\s;&|]+)", command):
        if contains_source_marker(match.group(1), markers):
            block(f"przekierowanie do {match.group(1)}")

    for segment in re.split(r"[;&|]+", command):
        tokens = segment.strip().split()
        if not tokens:
            continue
        if (
            tokens[0] in ("cp", "rsync", "install")
            and len(tokens) >= 3
            and contains_source_marker(tokens[-1], markers)
        ):
            block(f"cel kopiowania w źródłach: {tokens[-1]}")
        if tokens[0] == "tar" and re.search(r"(^|\s)-[a-zA-Z]*x|(\s|^)x", segment) and "-C" in tokens:
            index = tokens.index("-C")
            destination = tokens[index + 1] if index + 1 < len(tokens) else ""
            if contains_source_marker(destination, markers):
                block(f"rozpakowanie do źródeł: {destination}")
        if tokens[0] == "unzip" and "-d" in tokens:
            index = tokens.index("-d")
            destination = tokens[index + 1] if index + 1 < len(tokens) else ""
            if contains_source_marker(destination, markers):
                block(f"rozpakowanie do źródeł: {destination}")
        if (
            tokens[0] == "git"
            and len(tokens) > 1
            and tokens[1] in ("init", "clean", "checkout", "reset")
            and contains_source_marker(segment, markers)
        ):
            block("operacja git w obrębie źródeł")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return
    event_cwd = data.get("cwd", os.getcwd())
    if not isinstance(event_cwd, str):
        event_cwd = os.getcwd()

    sources = read_sources_path()
    if not sources:
        return
    markers = [sources, "00_SOURCES"]

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        guard_file_path(tool, tool_input, sources, event_cwd)
        return

    command = tool_input.get("command", "") or ""
    if not isinstance(command, str):
        return
    if tool == "apply_patch":
        guard_patch(command, markers)
    elif tool == "Bash":
        guard_bash(command, markers)


if __name__ == "__main__":
    main()
