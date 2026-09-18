"""B8: kontrola planu przed dotknięciem materiałów. Czysta funkcja, bez filesystemu.

Wejście: linie planu (B3/B5/B7) + fakty, których plan sam o sobie nie wie (przedmiot,
struktura z ``syntax.yaml``, progi, ground truth z indeksu). Wyjście: lista ustaleń.
Etap niczego nie naprawia — ma **zatrzymać** `apply`, gdy plan jest niewykonalny albo
niebezpieczny (``AGENTS.md``: plan przed zmianami materiałów).

Dwa poziomy, bo ``syntax.yaml: naming_rules`` wprost tak każe:

- ``error``  — blokuje `apply`: plan wyszedłby poza paczkę, nadpisał cudzy plik, wstawił
  nazwę nie do odtworzenia na Windowsie albo skopiował coś, czego nikt nie potwierdził;
- ``warning`` — nazwa odbiega od konwencji. To jest auto-poprawialne i ma trafić do
  review, a nie zatrzymywać pracy.

**Nazwy pod Windows** są tu regułą planu, nie testem, bo `paczka-content` klonują
studenci: plik nie do odtworzenia psuje klon, a nie tylko wygląda brzydko. Pomiar
źródeł z 2026-09-19 (48 049 plików) mówi, co realnie grozi: 2 nazwy plików zawierają
znak z ``<>:"|?*`` (np. cudzysłów w tytule wykładu), 177 ścieżek ma ponad 200 znaków,
1 ponad 240. Nazwy kończące się kropką/spacją są w źródłach WYŁĄCZNIE w katalogach
(328), a katalogi docelowe bierzemy z ``syntax.yaml``, nie ze źródeł — regułę i tak
sprawdzamy na każdym segmencie, bo nazwa pliku może się taką stać po każdej zmianie
w budowaniu ścieżki.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from orglib import config
from orglib.classify import Rules, fold

#: Maksymalna długość ścieżki docelowej. Klon repo wchodzi jeszcze w katalog
#: użytkownika, więc zostawiamy zapas do windowsowego limitu 260 znaków.
MAX_TARGET_LENGTH = 240

#: Znaki zakazane w nazwach plików na Windowsie (poza separatorem ścieżki).
WINDOWS_FORBIDDEN = '<>:"|?*'

#: Nazwy urządzeń DOS: plik o takiej nazwie (z dowolnym rozszerzeniem) nie powstanie.
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

_CONTROL = re.compile(r"[\x00-\x1f]")

#: Numer slotu w nazwie katalogu docelowego (lab_03, kol_02) — kontrola dopełnienia.
_SLOT_NUMBER = re.compile(r"^(lab|kol)_(\d+)$")


@dataclass(frozen=True)
class Finding:
    """Jedno ustalenie walidacji; ``level`` decyduje, czy blokuje `apply`."""

    level: str
    code: str
    message: str
    source_sha256: str | None = None
    target_rel: str | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "source_sha256": self.source_sha256,
            "target_rel": self.target_rel,
        }


def _error(code: str, message: str, row: Mapping[str, Any] | None = None) -> Finding:
    return Finding(
        "error", code, message,
        source_sha256=str(row.get("source_sha256")) if row else None,
        target_rel=str(row.get("target_rel")) if row else None,
    )


def _warning(code: str, message: str, row: Mapping[str, Any] | None = None) -> Finding:
    return Finding(
        "warning", code, message,
        source_sha256=str(row.get("source_sha256")) if row else None,
        target_rel=str(row.get("target_rel")) if row else None,
    )


def check_windows_name(target: str) -> list[str]:
    """Powody, dla których ta ścieżka nie powstanie (albo zniknie) na Windowsie."""
    problems: list[str] = []
    if len(target) > MAX_TARGET_LENGTH:
        problems.append(f"ścieżka ma {len(target)} znaków (limit {MAX_TARGET_LENGTH})")
    for segment in PurePosixPath(target).parts:
        if segment != segment.rstrip(". "):
            problems.append(f"segment {segment!r} kończy się kropką albo spacją")
        found = sorted({c for c in segment if c in WINDOWS_FORBIDDEN})
        if found:
            problems.append(f"segment {segment!r} zawiera {''.join(found)!r}")
        if _CONTROL.search(segment):
            problems.append(f"segment {segment!r} zawiera znak sterujący")
        if segment.split(".")[0].upper() in WINDOWS_RESERVED:
            problems.append(f"segment {segment!r} to nazwa zastrzeżona w Windows")
    return problems


def check_path_safety(target: str) -> list[str]:
    """Ścieżka docelowa musi być względna i nie może wychodzić w górę drzewa."""
    problems: list[str] = []
    if not target:
        return ["pusta ścieżka docelowa"]
    if "\\" in target:
        problems.append("separator '\\\\' — ścieżki w planie są POSIX-owe")
    if PurePosixPath(target).is_absolute():
        problems.append("ścieżka bezwzględna")
    parts = target.split("/")
    if any(part in ("", ".", "..") for part in parts):
        problems.append("segment pusty, '.' albo '..'")
    return problems


def _category_folder(rules: Rules, category: str) -> str | None:
    spec = rules.category(category)
    return spec.folder if spec is not None else None


def validate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    subject: config.Subject,
    rules: Rules,
    auto_apply: float,
    review_min: float,
    media_root: str = "90_MEDIA",
    ground_truth: Mapping[str, str] | None = None,
) -> list[Finding]:
    """Wszystkie kontrole planu jednego przedmiotu.

    ``ground_truth`` to mapa ``ścieżka docelowa -> sha256`` tego, co JUŻ leży w paczce
    (tabela ``applied``). Plan, który chce położyć inną treść pod istniejącą ścieżką,
    nadpisałby ręcznie ułożony materiał — to jest twardy błąd, nie ostrzeżenie
    (reguła twarda nr 2).
    """
    findings: list[Finding] = []
    seen_sha: dict[str, int] = {}
    targets: dict[str, str] = {}
    ground_truth = ground_truth or {}

    for number, row in enumerate(rows, start=1):
        sha = str(row.get("source_sha256") or "")
        action = str(row.get("action") or "")
        target = str(row.get("target_rel") or "")
        category = str(row.get("category") or "")

        if not sha:
            findings.append(_error("brak_sha", f"linia {number}: pozycja bez source_sha256"))
            continue
        if sha in seen_sha:
            findings.append(_error(
                "podwojna_decyzja",
                f"treść ma dwie decyzje (linie {seen_sha[sha]} i {number}) — plan musi mieć jedną na sha256",
                row,
            ))
        else:
            seen_sha[sha] = number

        for problem in check_path_safety(target):
            findings.append(_error("sciezka", problem, row))

        # Nazwy sprawdzamy tylko tam, gdzie plan naprawdę utworzy plik.
        if action in ("copy", "media"):
            for problem in check_windows_name(target):
                findings.append(_error("nazwa_windows", problem, row))
            previous = targets.get(target)
            if previous and previous != sha:
                findings.append(_error(
                    "kolizja_celu",
                    f"dwie różne treści trafiają w tę samą ścieżkę (druga: {previous[:12]}…)",
                    row,
                ))
            targets[target] = sha
            existing = ground_truth.get(target)
            if existing and existing != sha:
                findings.append(_error(
                    "nadpisanie_ground_truth",
                    f"pod tą ścieżką leży już inna treść ({existing[:12]}…) ułożona ręcznie",
                    row,
                ))

        if action == "copy":
            if not target.startswith(f"{subject.target_dir}/"):
                findings.append(_error(
                    "poza_przedmiotem",
                    f"cel spoza katalogu przedmiotu ({subject.target_dir})",
                    row,
                ))
            else:
                folder = _category_folder(rules, category)
                rest = target[len(subject.target_dir) + 1:]
                if folder and fold(rest).split("/")[0] != fold(folder).split("/")[0]:
                    findings.append(_error(
                        "kategoria_vs_sciezka",
                        f"kategoria {category!r} (folder {folder!r}) nie zgadza się ze ścieżką {rest!r}",
                        row,
                    ))
                for segment in PurePosixPath(rest).parts:
                    match = _SLOT_NUMBER.match(segment)
                    if match and len(match.group(2)) < rules.number_padding:
                        findings.append(_warning(
                            "numer_bez_dopelnienia",
                            f"segment {segment!r} — numery mają mieć {rules.number_padding} cyfry",
                            row,
                        ))
        elif action == "media" and not target.startswith(f"{media_root}/"):
            findings.append(_error(
                "media_w_paczce",
                f"materiał medialny musi trafić poza paczkę, do {media_root}/",
                row,
            ))

        year = row.get("year")
        if year is not None and not (isinstance(year, str) and len(year) == 4 and year.isdigit()):
            findings.append(_error("rok", f"rok {year!r} nie jest czterocyfrowy", row))

        try:
            confidence = float(row.get("confidence"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            findings.append(_error("pewnosc", "brak liczbowej pewności decyzji", row))
            continue
        if action == "copy" and confidence < review_min:
            findings.append(_error(
                "pewnosc_ponizej_progu",
                f"kopiowanie z pewnością {confidence} poniżej progu review ({review_min})",
                row,
            ))
        if confidence < auto_apply and not row.get("needs_review"):
            findings.append(_error(
                "brak_review",
                f"pewność {confidence} < {auto_apply}, a pozycja nie jest oznaczona do review",
                row,
            ))

    return findings


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {"error": 0, "warning": 0}
    for finding in findings:
        counts[finding.level] = counts.get(finding.level, 0) + 1
    return counts


def tree_diff(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Co plan doda do drzewa: nowe katalogi i pliki, posortowane. Wsad do dry-runu."""
    files = sorted(
        str(row.get("target_rel"))
        for row in rows
        if str(row.get("action")) in ("copy", "media") and row.get("target_rel")
    )
    folders = sorted({str(PurePosixPath(path).parent) for path in files})
    return {"folders": folders, "files": files}
