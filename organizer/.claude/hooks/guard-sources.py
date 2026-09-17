#!/usr/bin/env python3
"""PreToolUse guard: 00_SOURCES jest READ-ONLY.

Blokuje (exit 2) każde wywołanie narzędzia, które mogłoby zmodyfikować katalog
źródeł. Ścieżkę źródeł bierze z config/paths.yaml (klucz `sources`), więc nie
ma tu nic zahardkodowanego. Fail-open: gdy nie umie ocenić, przepuszcza.

Zasady:
  Edit/Write/MultiEdit/NotebookEdit  -> file_path pod sources => BLOK
  Bash                               -> komenda wspomina sources i zawiera
                                        czasownik mutujący / przekierowanie
                                        / cel cp|mv|rsync w sources => BLOK
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORGANIZER = os.path.abspath(os.path.join(HERE, "..", ".."))


def read_sources_path() -> str | None:
    cfg = os.path.join(ORGANIZER, "config", "paths.yaml")
    try:
        with open(cfg, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s*sources\s*:\s*([^#\n]+)", line)
                if m:
                    raw = m.group(1).strip().strip("'\"")
                    return os.path.realpath(os.path.join(ORGANIZER, raw))
    except OSError:
        pass
    return None


def block(reason: str) -> None:
    sys.stderr.write(f"guard-sources: BLOKADA — {reason}. 00_SOURCES jest READ-ONLY (CLAUDE.md, reguła 1).\n")
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}
    sources = read_sources_path()
    if not sources:
        return
    markers = [sources, "00_SOURCES"]

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        fp = inp.get("file_path") or inp.get("notebook_path") or ""
        if not fp:
            return
        real = os.path.realpath(fp if os.path.isabs(fp) else os.path.join(data.get("cwd", os.getcwd()), fp))
        if real == sources or real.startswith(sources + os.sep):
            block(f"{tool} na {fp}")
        return

    if tool != "Bash":
        return
    cmd = inp.get("command", "") or ""
    if not any(m in cmd for m in markers):
        return

    hard = r"(^|[;&|(\s])(rm|rmdir|mv|chmod|chown|chattr|touch|mkdir|truncate|shred|dd|ln|tee|rename|setfacl)(\s|$)"
    if re.search(hard, cmd):
        block(f"komenda mutująca w obrębie źródeł: {cmd[:120]}")
    if re.search(r"(^|\s)(sed|perl)\s+(-[a-zA-Z]*i|--in-place)", cmd):
        block("edycja in-place w obrębie źródeł")
    # przekierowanie do pliku w sources
    for m in re.finditer(r">{1,2}\s*([^\s;&|]+)", cmd):
        if any(k in m.group(1) for k in markers):
            block(f"przekierowanie do {m.group(1)}")
    # cp / rsync / tar -x / unzip z celem w sources
    for seg in re.split(r"[;&|]+", cmd):
        toks = seg.strip().split()
        if not toks:
            continue
        if toks[0] in ("cp", "rsync", "install") and len(toks) >= 3 and any(k in toks[-1] for k in markers):
            block(f"cel kopiowania w źródłach: {toks[-1]}")
        if toks[0] == "tar" and re.search(r"(^|\s)-[a-zA-Z]*x|(\s|^)x", seg) and "-C" in toks:
            dest = toks[toks.index("-C") + 1] if toks.index("-C") + 1 < len(toks) else ""
            if any(k in dest for k in markers):
                block(f"rozpakowanie do źródeł: {dest}")
        if toks[0] == "unzip" and "-d" in toks:
            dest = toks[toks.index("-d") + 1] if toks.index("-d") + 1 < len(toks) else ""
            if any(k in dest for k in markers):
                block(f"rozpakowanie do źródeł: {dest}")
        if toks[0] == "git" and len(toks) > 1 and toks[1] in ("init", "clean", "checkout", "reset") and any(k in seg for k in markers):
            block("operacja git w obrębie źródeł")


if __name__ == "__main__":
    main()
