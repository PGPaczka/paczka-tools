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

#: Interpretery, którym można podać kod wprost. Sama lista słów mutujących powłoki
#: ich nie łapie: ``python3 -c "shutil.rmtree('00_SOURCES/x')"`` nie zawiera tokenu
#: ``rm``, a kasuje tak samo skutecznie.
_INTERPRETERS = r"python[0-9.]*|perl|ruby|node|deno|bun|php|pwsh|osascript"

#: Wywołanie interpretera z kodem inline: przez flagę (``-c``/``-e``/``-r``/``--eval``)
#: albo ze stdin (``python3 -`` oraz heredoc ``python3 <<EOF``).
_INLINE_CODE = re.compile(
    rf"(^|[;&|(\s])({_INTERPRETERS})\s+"
    rf"(?:[^;&|]*?\s)?(?:-c|-e|-r|-E|--eval|--exec)(?:\s|=)"
    rf"|(^|[;&|(\s])({_INTERPRETERS})\s+(?:-\s|<<)"
)

#: Operacje niszczące wskazaną ścieżkę. Marker gdziekolwiek w argumentach albo
#: w odbiorniku (``Path('…/x').write_text(…)``) oznacza mutację źródeł.
#: Sufiks ``Sync``/``sync`` pokrywa API Node/Deno (``unlinkSync``).
_DESTRUCTIVE = (
    r"rmtree|removedirs|makedirs|mkdir|rmdir|unlink|remove|rename|renames|replace|rm|move|"
    r"truncate|ftruncate|chmod|chown|lchown|utime|utimes|mknod|mkfifo|"
    r"write_text|write_bytes|writelines|writeFile|appendFile|createWriteStream|touch|"
    r"symlink_to|hardlink_to|extractall|unpack_archive"
)
_DESTRUCTIVE_CALL = re.compile(rf"\b({_DESTRUCTIVE})(?:Sync|sync)?\s*\(([^)]*)", re.IGNORECASE)

#: To samo, ale wywołane na obiekcie: liczy się wyrażenie PRZED kropką.
_DESTRUCTIVE_METHOD = re.compile(rf"\.\s*({_DESTRUCTIVE})(?:Sync|sync)?\s*\(", re.IGNORECASE)

#: Kopiowanie: źródłem wolno być katalogowi źródeł (wynoszenie materiałów na zewnątrz
#: to normalna praca), celem — nie. Liczy się więc dopiero drugi i dalsze argumenty.
_COPY_CALL = re.compile(
    r"\b(copyfile|copytree|copystat|copymode|copy2|copy|cp|symlink|link)"
    r"(?:Sync|sync)?\s*\(([^)]*)",
    re.IGNORECASE,
)

#: ``open(ścieżka, "w"|"a"|"x")`` — otwarcie do zapisu. Tryb bywa drugim argumentem
#: albo słowem kluczowym, więc patrzymy na całą listę argumentów.
_OPEN_FOR_WRITE = re.compile(r"\bopen\s*\(([^)]*['\"][wax][^)]*)", re.IGNORECASE)

#: Wyjście do powłoki z wnętrza kodu — nie da się rzetelnie przeanalizować, więc
#: przy obecności markera blokujemy zachowawczo.
_SHELL_OUT = re.compile(r"\bos\.system\b|\bsubprocess\b|\bpopen\b|\bexecSync\b|\bspawnSync\b")


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


def _statement_before(command: str, end: int) -> str:
    """Fragment wyrażenia poprzedzający wywołanie metody — tam siedzi odbiornik.

    Cofamy się do granicy instrukcji (``;``, nowa linia, przecinek, otwarcie nawiasu
    albo przypisanie), żeby ``Path('…/x').write_text(…)`` dało się odróżnić od
    zapisu gdzie indziej w tej samej komendzie.
    """
    head = command[:end]
    boundary = max(head.rfind(character) for character in ";\n,=")
    return head[boundary + 1 :] if boundary >= 0 else head


def guard_inline_code(command: str, markers: list[str]) -> None:
    """Mutacje ukryte w kodzie podanym interpreterowi (``python3 -c`` itp.)."""
    for call in _DESTRUCTIVE_CALL.finditer(command):
        if contains_source_marker(call.group(2), markers):
            block(f"{call.group(1)}() na źródłach w kodzie interpretera")

    for method in _DESTRUCTIVE_METHOD.finditer(command):
        if contains_source_marker(_statement_before(command, method.start()), markers):
            block(f".{method.group(1)}() na źródłach w kodzie interpretera")

    for copy_call in _COPY_CALL.finditer(command):
        # Pierwszy argument to źródło — wolno nim być katalogowi źródeł.
        destinations = copy_call.group(2).split(",")[1:]
        if contains_source_marker(",".join(destinations), markers):
            block(f"{copy_call.group(1)}() z celem w źródłach")

    for opened in _OPEN_FOR_WRITE.finditer(command):
        if contains_source_marker(opened.group(1), markers):
            block("otwarcie źródła do zapisu w kodzie interpretera")

    if _SHELL_OUT.search(command):
        block("kod interpretera wychodzi do powłoki nad źródłami")


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

    # Kod podany interpreterowi wprost omija listę słów powłoki powyżej.
    if _INLINE_CODE.search(command):
        guard_inline_code(command, markers)

    # `find ... -delete` kasuje bez wywołania `rm`, więc nie ma tokenu do złapania.
    if re.search(r"(^|\s)-delete(\s|$)", command):
        block("find -delete w obrębie źródeł")

    # `>|` (wymuszone nadpisanie mimo noclobber) ma inny kształt niż `>`/`>>`.
    for match in re.finditer(r">{1,2}\|?\s*([^\s;&|]+)", command):
        if contains_source_marker(match.group(1), markers):
            block(f"przekierowanie do {match.group(1)}")

    # Zapis wskazany flagą, a nie pozycją: `cp -t DIR`, `sort -o PLIK`.
    # Świadomie BEZ `-f`/`--file`: tam ścieżka bywa wejściem (`tar -xf źródło.tar`,
    # `grep -f wzorce.txt`), więc blokowanie po niej dawałoby fałszywe alarmy.
    for flag_match in re.finditer(
        r"(?:^|\s)(?:-t|-o|--target-directory|--output|--output-file)(?:\s+|=)([^\s;&|]+)",
        command,
    ):
        if contains_source_marker(flag_match.group(1), markers):
            block(f"zapis wskazany flagą do {flag_match.group(1)}")

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
