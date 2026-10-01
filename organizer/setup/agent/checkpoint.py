#!/usr/bin/env python3
"""Odświeża automatyczną część reports/HANDOFF.md."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path


ORGANIZER = Path(__file__).resolve().parents[2]
HANDOFF = ORGANIZER / "reports" / "HANDOFF.md"
TODO = ORGANIZER / "TODO.md"
START = "<!-- BEGIN AUTO -->"
END = "<!-- END AUTO -->"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ORGANIZER,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def first_pending_todo() -> str:
    if not TODO.exists():
        return "(brak TODO.md)"
    for line in TODO.read_text(encoding="utf-8").splitlines():
        if line.startswith("- [ ]") or line.startswith("- [~]"):
            return line
    return "(brak otwartych pozycji)"


def auto_block() -> str:
    status = git("status", "--short") or "(clean)"
    timestamp = os.environ.get("HANDOFF_NOW")
    if not timestamp:
        timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return "\n".join(
        [
            START,
            f"- Odświeżono: {timestamp}",
            f"- Branch: `{git('branch', '--show-current') or '(detached)'}`",
            f"- Commit: `{git('rev-parse', '--short', 'HEAD') or '(brak)'}`",
            "- Git status:",
            "  ```text",
            *[f"  {line}" for line in status.splitlines()],
            "  ```",
            f"- Pierwsze otwarte TODO: {first_pending_todo()}",
            END,
        ]
    )


def main() -> None:
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)
    existing = HANDOFF.read_text(encoding="utf-8") if HANDOFF.exists() else ""
    generated = auto_block()
    if START in existing and END in existing:
        before, remainder = existing.split(START, 1)
        _, after = remainder.split(END, 1)
        content = before.rstrip() + "\n\n" + generated + after
    else:
        manual = existing.strip() or """# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy:
- Aktywny przedmiot `(semestr, skrót, grupa)`:
- Ostatni zakończony krok:
- Wykonane testy:
- Następna dokładna czynność:
- Blokery / otwarte decyzje:
- Stan akceptacji planu: `brak | oczekuje | zaakceptowany`
- Zakazy dla następnego agenta:
"""
        content = manual.rstrip() + "\n\n" + generated + "\n"
    HANDOFF.write_text(content, encoding="utf-8")
    print(HANDOFF.relative_to(ORGANIZER))


if __name__ == "__main__":
    main()
