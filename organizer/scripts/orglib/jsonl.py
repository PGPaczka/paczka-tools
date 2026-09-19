"""Wspólne czytanie i atomowy zapis JSONL — jeden kontrakt dla wszystkich etapów.

Powstało po realnej awarii (2026-09-19): `near_dupe.py` czytał manifest przez
``read_text().splitlines()``, a głowa tekstu wyekstrahowana z PDF-a zawierała
**U+2028 LINE SEPARATOR**. ``json.dumps(..., ensure_ascii=False)`` zapisuje ten znak
surowo — jest legalny wewnątrz stringa JSON — a ``str.splitlines()`` traktuje go
(razem z U+2029, U+0085, \\v, \\f i separatorami \\x1c-\\x1e) jako koniec linii.
Skutek: 2570 linii manifestu rozpadło się na 2573 kawałki i etap padał na
„Unterminated string”.

**Linie JSONL rozdziela wyłącznie ``\\n``.** Iteracja po uchwycie pliku robi dokładnie
to — i dlatego jest tu jedyną dozwoloną metodą. Trzy inne etapy miały własne, poprawne
kopie tej funkcji; czwarta kopia była subtelnie inna. Stąd jeden moduł.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Czyta plik JSONL; każda linia musi być obiektem JSON. Puste linie pomija."""
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: niepoprawny JSON ({exc})") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: linia nie jest obiektem JSON")
            rows.append(row)
    return rows


def write_atomic(rows: Iterable[Mapping[str, Any]], output: Path, *, prefix: str = ".jsonl-") -> None:
    """Zapisuje cały plik przez plik tymczasowy + ``os.replace``.

    Przerwany zapis nie może zostawić obciętego artefaktu: poprzednia wersja ma
    przetrwać w całości albo zostać zastąpiona w całości.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=prefix, suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
