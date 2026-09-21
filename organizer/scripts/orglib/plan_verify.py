"""B11: sprawdzenie, że w paczce leży dokładnie to, co mówi plan.

`apply` (B10) kopiuje pliki i zapisuje audyt, ale audyt jest tylko zapisem naszej
własnej intencji. Dopiero policzenie hasha PO kopii dowodzi, że materiał dotarł
w całości — i że pod ścieżką planu leży ta treść, a nie inna. Dlatego commit
materiałów następuje po `verify`, nie po `apply`.

Dwie kontrole, w tej kolejności:

1. **treść**: dla każdej pozycji ``action='copy'`` plik istnieje, a jego sha256
   zgadza się z ``source_sha256``;
2. **drzewo**: pod katalogiem przedmiotu nie ma plików, których nie tłumaczy ani
   plan, ani ground truth. To ostrzeżenie, nie błąd — w katalogu przedmiotu
   legalnie lądują rzeczy spoza tego planu (np. `paczka_meta` z B12) — ale ma być
   widoczne, bo „drzewo == plan” jest wymaganiem tego etapu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from . import config
from .hashes import sha256_file
from .plan_apply import COPY_ACTION, resolve_target

#: Stany pozycji. `missing` i `mismatch` zatrzymują commit materiałów.
OK = "ok"
MISSING = "missing"
MISMATCH = "mismatch"
EXTRA = "extra"

#: Stany, które oznaczają, że paczce NIE wolno zaufać.
FAILING_STATES: frozenset[str] = frozenset({MISSING, MISMATCH})


@dataclass(frozen=True)
class Check:
    """Wynik jednej kontroli."""

    state: str
    target_rel: str
    sha256: str = ""
    detail: str = ""

    @property
    def failing(self) -> bool:
        return self.state in FAILING_STATES

    def as_row(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "target_rel": self.target_rel,
            "sha256": self.sha256,
            "detail": self.detail,
        }


def check_rows(
    rows: Sequence[Mapping[str, Any]], *, paths: config.Paths
) -> list[Check]:
    """Hash po kopii wobec ``source_sha256`` — pozycja po pozycji."""
    checks: list[Check] = []
    for row in rows:
        if str(row.get("action")) != COPY_ACTION:
            continue
        sha = str(row.get("source_sha256") or "")
        target_rel = str(row.get("target_rel") or "")
        target = resolve_target(paths, target_rel)
        if target is None:
            checks.append(Check(MISMATCH, target_rel, sha, "ścieżka wychodzi poza katalog paczki"))
            continue
        if not target.is_file():
            checks.append(Check(MISSING, target_rel, sha, "pliku nie ma w repo paczki"))
            continue
        actual = sha256_file(target)
        if actual != sha:
            checks.append(Check(
                MISMATCH, target_rel, sha, f"w paczce leży treść {actual[:12]}…, plan mówi {sha[:12]}…"
            ))
            continue
        checks.append(Check(OK, target_rel, sha))
    return checks


def tree_extras(
    rows: Sequence[Mapping[str, Any]],
    *,
    paths: config.Paths,
    subject: config.Subject,
    ground_truth: Iterable[str] = (),
) -> list[Check]:
    """Pliki pod katalogiem przedmiotu, których nie tłumaczy plan ani ground truth."""
    root = paths.target_repo / subject.target_dir
    if not root.is_dir():
        return []
    expected = {
        str(row.get("target_rel") or "")
        for row in rows
        if str(row.get("action")) == COPY_ACTION
    }
    expected |= set(ground_truth)
    extras: list[Check] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(PurePosixPath(Path(path).relative_to(paths.target_repo).as_posix()))
        if relative in expected:
            continue
        extras.append(Check(EXTRA, relative, "", "plik spoza planu i spoza ground truth"))
    return extras


def summarize(checks: Sequence[Check]) -> dict[str, int]:
    """Ile kontroli w każdym stanie (wszystkie stany obecne, także zerowe)."""
    counts = {state: 0 for state in (OK, MISSING, MISMATCH, EXTRA)}
    for check in checks:
        counts[check.state] = counts.get(check.state, 0) + 1
    return counts
