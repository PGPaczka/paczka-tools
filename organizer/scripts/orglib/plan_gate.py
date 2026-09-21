"""Bramka przed `apply`: jedno miejsce, w którym plan jest oceniany.

Wydzielone z ``validate_plan.py`` (B8) w chwili, gdy powstał ``apply`` (B10).
Powód jest wprost z ``AGENTS.md``: „plan przed zmianami materiałów”. Gdyby
`apply` miał własną kopię kontroli, bramka przestałaby być bramką — wystarczyłaby
rozjeżdżka jednej reguły, żeby coś, co `validate_plan` odrzuca, zostało jednak
skopiowane. Dlatego oba wołają :func:`evaluate` i oba czytają ten sam wynik.

Moduł niczego nie zapisuje i nie dotyka materiałów — liczy ustalenia.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from . import config
from .jsonl import read_jsonl
from .plan_build import META_KEY, plan_hash
from .plan_lint import Finding, summarize, validate_rows

#: Schemat jednej linii planu — kontrakt międzyetapowy B3/B5/B7 → B8/B10.
#:
#: Liczony ze ścieżki TEGO pliku, a nie z ``config.ORGANIZER_ROOT``: schemat jest
#: zasobem repo i leży obok kodu, a tamtą stałą testy przestawiają na katalog
#: tymczasowy, żeby przekierować RAPORTY. Zbudowany na niej schemat przestawał
#: istnieć dokładnie w teście e2e, czyli tam, gdzie łańcuch etapów jest sprawdzany.
SCHEMA_PATH: Path = Path(__file__).resolve().parents[2] / "prompts" / "plan_line.schema.json"

#: Katalog, do którego plan kieruje duże media (poza repo paczki).
MEDIA_ROOT = "90_MEDIA"


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Wczytuje schemat linii planu."""
    return json.loads(Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


def read_plan(paths: Sequence[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Czyta pliki planu i rozdziela decyzje od nagłówków ``_meta``."""
    rows: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    for path in paths:
        for row in read_jsonl(path):
            if META_KEY in row:
                metas.append(row[META_KEY])
            else:
                rows.append(row)
    return rows, metas


def evaluate(
    rows: Sequence[Mapping[str, Any]],
    metas: Iterable[Mapping[str, Any]],
    *,
    subject: config.Subject,
    rules: Any,
    auto_apply: float,
    review_min: float,
    ground_truth: Mapping[str, str],
    schema: Mapping[str, Any] | None = None,
    media_root: str = MEDIA_ROOT,
) -> list[Finding]:
    """Wszystkie ustalenia o planie: schemat linii, reguły B8 i odcisk nagłówka."""
    document = dict(schema) if schema is not None else load_schema()
    findings: list[Finding] = []
    for number, row in enumerate(rows, start=1):
        try:
            jsonschema.validate(row, document)
        except jsonschema.ValidationError as exc:
            findings.append(Finding(
                "error", "schemat", f"linia {number}: {exc.message}",
                source_sha256=str(row.get("source_sha256") or "") or None,
                target_rel=str(row.get("target_rel") or "") or None,
            ))
    findings.extend(validate_rows(
        rows,
        subject=subject,
        rules=rules,
        auto_apply=auto_apply,
        review_min=review_min,
        media_root=media_root,
        ground_truth=ground_truth,
    ))
    # Odcisk planu z nagłówka musi zgadzać się z zawartością: inaczej plik został
    # zmieniony po zbudowaniu i `apply` wykonałby coś innego, niż zaakceptował człowiek.
    actual = plan_hash(rows)
    for meta in metas:
        declared = str(meta.get("plan_hash") or "")
        if declared and declared != actual:
            findings.append(Finding(
                "error", "plan_hash",
                f"plan_hash z nagłówka ({declared[:12]}…) nie zgadza się z zawartością "
                f"({actual[:12]}…)",
            ))
    return findings


def blocking_count(findings: Sequence[Finding], *, strict: bool = False) -> int:
    """Ile ustaleń zatrzymuje plan. ``strict`` liczy też ostrzeżenia."""
    counts = summarize(findings)
    return counts["error"] + (counts["warning"] if strict else 0)
