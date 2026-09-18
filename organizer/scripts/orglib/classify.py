"""B3: deterministyczna i heurystyczna klasyfikacja jednej treści — czysta funkcja.

Moduł nie czyta materiałów, nie chodzi po filesystemie i nie zmienia bazy. Dostaje
wiersz manifestu (B1), przedmiot z ``subjects.yaml``, reguły z ``syntax.yaml`` oraz
``thresholds.yaml`` i wcześniej odczytany ground truth — zwraca albo linię planu
zgodną z ``prompts/plan_line.schema.json``, albo pozycję `unresolved` dla AI (B5).

Kolejność jest ta z ``AGENTS.md`` (reguła twarda nr 3): najpierw deterministyka,
potem heurystyka, a AI dostaje wyłącznie resztki.

1. **ground truth** — treść jest już w paczce (``classifications.run_id='ground_truth'``,
   zapisane przez ``scan_target.py``): ``skip`` z pewnością 1.0. Tego nie rozstrzyga
   żadna heurystyka ani model, bo to nie jest opinia, tylko stan repo.
2. **artefakt kompilacji** (``syntax.yaml: ignore``): ``skip``. Pomiar źródeł: 14,2%
   plików to wyjście kompilatora (``Debug/``, ``.tlog``, ``.obj``). Nic nie kasujemy —
   plik zostaje w źródłach, a decyzja jest w planie i odwracalna zmianą configu.
3. **brak zdrowego źródła** (``no_unique_source`` z manifestu): ``quarantine`` — nie ma
   z czego kopiować, więc AI też tego nie naprawi; zostaje człowiekowi.
4. **media** — rozszerzenie z ``syntax.yaml: media.extensions``: poza paczkę,
   do ``90_MEDIA`` (reguła twarda nr 11).
5. **heurystyka** — słowa kluczowe kategorii (``syntax.yaml: categories.*.keywords``)
   szukane kolejno w nazwie pliku, w nazwach katalogów na ścieżce i w głowie tekstu
   z etapu extract. Siła sygnału = pewność decyzji (``thresholds.yaml: classify``).
6. **reszta** — ``unresolved``: nic nie zgadujemy (reguła twarda nr 9).

Świadome ograniczenia, żeby następny agent nie „naprawiał” ich przez przypadek:

- **Nazwa pliku zostaje oryginalna.** Kanoniczna nazwa z ``syntax.yaml``
  (``{skrot}_{rok}_wykład_0{nr}-{temat}.pdf``) wymaga TEMATU, którego z nazwy i ścieżki
  nie da się wyprowadzić bez zgadywania. Klasyfikator ustala więc KATALOG docelowy,
  a niezgodność nazwy jest — zgodnie z ``naming_rules`` — miękkim ostrzeżeniem dla
  validatora (B8) i review (B9), nie twardym błędem.
- **Prowadzący rozpoznawany tylko po tytule** (``dr``/``mgr``/``prof``/``inż``/``hab``).
  Pomiar na realnych źródłach: taki wzorzec trafia w 8 z 48 049 plików, a nazwisko bez
  tytułu jest nieodróżnialne od tematu. Wąsko, ale bez fałszywych trafień; listę
  nazwisk (gdy powstanie) wpina się tu, nie w regex.
- **Segmenty ścieżki będące nazwą samego przedmiotu są pomijane** jako sygnał
  kategorii — inaczej ``PGI_Projekt_Grupowy_I`` klasyfikowałby wszystko na ``projekt``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from orglib import config

#: Wersja kontraktu linii planu (``prompts/plan_line.schema.json``).
SCHEMA_VERSION = 1

#: Wartość pola ``model`` dla decyzji podjętych regułami, nie modelem.
RULES_MODEL = "deterministic"

#: Najstarszy rok, który uznajemy za rok materiału (starszych paczek nie ma).
YEAR_MIN = 1990

#: Tytuły naukowe/zawodowe otwierające segment z nazwiskiem prowadzącego.
#: Świadomie ``(?![a-z])`` zamiast ``\b``: w nazwach katalogów separatorem bywa
#: podkreślenie (``mgr_inż_Nowak``), a dla ``\b`` podkreślenie jest znakiem słowa,
#: więc granica by tam nie zaszła i cały wzorzec nigdy by nie trafił.
_TITLE = re.compile(r"^(?:dr|mgr|prof|inz|hab)(?![a-z])[.\s_-]*(.+)$")

#: Rok jako samodzielna liczba czterocyfrowa (nie fragment '20231015').
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

#: Numery slotów. Klucz = pole z ``syntax.yaml: placeholders``, wartość = wzorzec.
#: Trafienie w numer jest RÓWNIEŻ sygnałem kategorii (patrz ``_NUMBER_CATEGORY``).
_NUMBERS: dict[str, re.Pattern[str]] = {
    "nr_laby": re.compile(r"(?<![a-z0-9])lab(?:oratorium)?[_\-. ]?(\d{1,2})(?![0-9])"),
    "nr_kolosa": re.compile(r"(?<![a-z0-9])kol(?:okwium|os)?[_\-. ]?(\d{1,2})(?![0-9])"),
    "nr_wykladu": re.compile(r"(?<![a-z0-9])wyk(?:lad)?[_\-. ]?(\d{1,2})(?![0-9])"),
    "nr_projektu": re.compile(r"(?<![a-z0-9])proj(?:ekt)?[_\-. ]?(\d{1,2})(?![0-9])"),
}

#: Powody review z manifestu (B1), które podważają TOŻSAMOŚĆ materiału, więc zbijają
#: pewność pod próg auto-apply. Reszta powodów manifestu (np. ``missing_semester`` dla
#: przedmiotu o unikalnym skrócie) opisuje ubogą ścieżkę, a nie wątpliwy przedmiot.
IDENTITY_REVIEW_REASONS: frozenset[str] = frozenset(
    {
        "ambiguous_subject",
        "conflicting_semesters",
        "conflicting_groups",
        "conflicting_source_subjects",
        "inconsistent_sizes",
        "no_unique_source",
    }
)

#: Skąd wziął się sygnał kategorii. Trafia wprost do ``reason``, więc nazwy są
#: opisowe: przy review człowiek musi wiedzieć, czemu plik trafił tam, gdzie trafił.
SIGNAL_FILENAME = "nazwa pliku"
SIGNAL_FOLDER_NEAR = "najbliższy katalog na ścieżce"
SIGNAL_FOLDER_FAR = "dalszy katalog na ścieżce"
SIGNAL_TEXT = "głowa tekstu"

#: Która kategoria wynika z trafienia w numer slotu.
_NUMBER_CATEGORY = {
    "nr_laby": "laboratoria",
    "nr_kolosa": "kolokwia",
    "nr_wykladu": "wyklad",
    "nr_projektu": "projekt",
}


def fold(value: str) -> str:
    """Normalizuje tekst do porównań: małe litery, bez diakrytyków, ``ł`` → ``l``.

    Ta sama konwencja co w :mod:`orglib.subject_manifest` — dopasowania nazw
    muszą działać tak samo na obu etapach.
    """
    value = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    return "".join(c for c in value if not unicodedata.combining(c))


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Słowo kluczowe jako PREFIKS na granicy słowa (polska odmiana: 'wykładów')."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(fold(keyword))}[a-z]*")


@dataclass(frozen=True)
class Category:
    """Jedna kategoria z ``syntax.yaml`` widziana oczami klasyfikatora."""

    name: str
    folder: str
    templates: tuple[str, ...]
    forms: frozenset[str]
    keywords: tuple[re.Pattern[str], ...]
    priority: int

    def matches(self, folded: str) -> bool:
        return any(pattern.search(folded) for pattern in self.keywords)


@dataclass(frozen=True)
class Rules:
    """Reguły klasyfikacji złożone z ``syntax.yaml`` i ``thresholds.yaml``."""

    categories: tuple[Category, ...]
    number_padding: int
    media_extensions: frozenset[str]
    media_threshold_bytes: int
    media_target: str
    outdated_folders: frozenset[str]
    ignore_extensions: frozenset[str]
    ignore_folders: frozenset[str]
    ignore_reason: str
    weight_filename: float
    weight_folder: float
    weight_text: float
    conflict_penalty: float
    manifest_review_cap: float
    ground_truth_confidence: float
    media_confidence: float
    ignore_confidence: float
    auto_apply: float
    review_min: float

    def category(self, name: str) -> Category | None:
        for spec in self.categories:
            if spec.name == name:
                return spec
        return None

    @property
    def folder_to_category(self) -> dict[str, str]:
        """Folder kategorii → nazwa kategorii (mapa dla ground truth).

        ``scan_target.py`` zapisuje jako kategorię PIERWSZY segment pod katalogiem
        przedmiotu, więc kategoria zagnieżdżona (``ksiazki`` = ``inne/książki``)
        nie może przejąć swojego korzenia: ``inne`` ma zostać ``inne``.
        """
        mapping: dict[str, str] = {}
        for spec in self.categories:
            if len(PurePosixPath(spec.folder).parts) == 1:
                mapping.setdefault(fold(spec.folder), spec.name)
        for spec in self.categories:
            mapping.setdefault(fold(spec.folder), spec.name)
        return mapping


def load_rules(
    syntax: Mapping[str, Any] | None = None, thresholds: Mapping[str, Any] | None = None
) -> Rules:
    """Czyta reguły z configu. Żadna nazwa folderu ani słowo kluczowe nie jest w kodzie."""
    syntax = dict(syntax if syntax is not None else config.load_yaml("syntax"))
    thresholds = dict(thresholds if thresholds is not None else config.load_thresholds())

    raw_categories = syntax.get("categories") or {}
    if not raw_categories:
        raise ValueError("syntax.yaml: brak sekcji 'categories'")
    categories: list[Category] = []
    for name, spec in raw_categories.items():
        spec = spec or {}
        folder = str(spec.get("folder") or name)
        templates = tuple(str(t) for t in (spec.get("target_templates") or [folder]))
        categories.append(
            Category(
                name=str(name),
                folder=folder,
                templates=templates,
                forms=frozenset(str(f).upper() for f in (spec.get("forms") or ())),
                keywords=tuple(_keyword_pattern(str(k)) for k in (spec.get("keywords") or ())),
                priority=int(spec.get("priority", 999)),
            )
        )
    categories.sort(key=lambda c: (c.priority, c.name))

    meta = syntax.get("meta") or {}
    media = syntax.get("media") or {}
    outdated = syntax.get("outdated") or {}
    ignore = syntax.get("ignore") or {}
    weights = thresholds.get("classify") or {}
    confidence = thresholds.get("confidence") or {}

    outdated_folders = {str(outdated.get("folder") or "outdated")}
    outdated_folders.update(str(f) for f in (outdated.get("legacy_folders") or ()))

    return Rules(
        categories=tuple(categories),
        number_padding=int(meta.get("number_padding", 2)),
        media_extensions=frozenset(f".{str(e).lower().lstrip('.')}" for e in (media.get("extensions") or ())),
        media_threshold_bytes=int(media.get("threshold_bytes", 0)),
        media_target=str(media.get("target_outside_repo") or "90_MEDIA/{skrot}/{opis}"),
        ignore_extensions=frozenset(
            f".{str(e).lower().lstrip('.')}" for e in (ignore.get("extensions") or ())
        ),
        ignore_folders=frozenset(fold(str(f)) for f in (ignore.get("folders") or ())),
        ignore_reason=str(ignore.get("reason") or "artefakt środowiska, nie materiał"),
        outdated_folders=frozenset(fold(f) for f in outdated_folders),
        weight_filename=float(weights.get("weight_filename", 0.92)),
        weight_folder=float(weights.get("weight_folder", 0.86)),
        weight_text=float(weights.get("weight_text", 0.74)),
        conflict_penalty=float(weights.get("conflict_penalty", 0.12)),
        manifest_review_cap=float(weights.get("manifest_review_cap", 0.89)),
        ground_truth_confidence=float(weights.get("ground_truth_confidence", 1.0)),
        media_confidence=float(weights.get("media_confidence", 0.99)),
        ignore_confidence=float(weights.get("ignore_confidence", 0.99)),
        auto_apply=float(confidence.get("auto_apply", 0.90)),
        review_min=float(confidence.get("review_min", 0.70)),
    )


def unambiguous_labels(
    subject: config.Subject, subjects: Sequence[config.Subject] | None = None
) -> frozenset[str]:
    """Nazwy tego przedmiotu, które NIE prowadzą do żadnego innego semestru.

    Rozstrzygają jedną rzecz: czy manifestowe ``missing_semester`` (ścieżka nie
    nazywa semestru) jest realnym ryzykiem pomyłki przedmiotu. Alias ``AK`` prowadzi
    i do Architektury (sem 3), i do Animacji (sem 7) — bez semestru w ścieżce to
    zgadywanka. Ale ścieżka z ``AKO`` albo ``Architektura Komputerów`` jest
    jednoznaczna sama z siebie i nie ma powodu spychać jej do review: na realnym
    manifeście AKO to różnica między 65% a kilkoma procentami pozycji „do obejrzenia”.
    """
    pool = subjects if subjects is not None else config.iter_subjects()
    mine = _subject_labels(subject, include_group=False)
    taken: set[str] = set()
    for other in pool:
        if other.semester == subject.semester:
            continue
        taken |= _subject_labels(other, include_group=False)
    return frozenset(mine - taken)


def allowed_categories(subject: config.Subject, rules: Rules) -> list[str]:
    """Kategorie dopuszczalne przez ``forms`` przedmiotu (kategoria bez ``forms`` pasuje zawsze)."""
    subject_forms = {str(form).upper() for form in subject.forms}
    return [c.name for c in rules.categories if not c.forms or c.forms & subject_forms]


@dataclass(frozen=True)
class GroundTruth:
    """Wiersz ``classifications`` zapisany przez ``scan_target.py`` (stan repo, nie opinia)."""

    target_relative_path: str
    semester: int | None = None
    subject_key: str | None = None
    category: str | None = None
    is_outdated: bool = False


@dataclass
class Outcome:
    """Wynik dla jednej treści: albo linia planu, albo pozycja dla AI."""

    decision: dict[str, Any] | None = None
    unresolved: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)


def render_template(template: str, values: Mapping[str, str], padding: int) -> str | None:
    """Renderuje szablon ścieżki; ``None``, gdy któreś pole jest nieznane.

    Zapis ``0{pole}`` znaczy „numer dopełniony zerami do ``padding``” — dlatego
    ``kol_0{nr_kolosa}`` z numerem 3 daje ``kol_03``, a z numerem 12 ``kol_12``,
    a nie ``kol_012``.
    """
    out: list[str] = []
    for segment in template.split("/"):
        def replace(match: re.Match[str]) -> str:
            name = match.group("name")
            value = values.get(name)
            if value is None or value == "":
                raise KeyError(name)
            if match.group("pad"):
                return str(value).lstrip("0").zfill(padding) if str(value).strip("0") else "0" * padding
            return str(value)

        try:
            out.append(re.sub(r"(?P<pad>0?)\{(?P<name>[a-z_]+)\}", replace, segment))
        except KeyError:
            return None
    return "/".join(out)


def render_best(templates: Sequence[str], values: Mapping[str, str], padding: int) -> str:
    """Pierwszy KOMPLETNY szablon; gdy żadnego nie da się domknąć — ostatni bez braków.

    Ostatni szablon jest z założenia najuboższy (sam folder kategorii), więc jego
    segmenty z nieznanym polem po prostu wypadają. Dzięki temu brak numeru laborki
    daje ``laboratoria`` zamiast wymyślonego ``lab_00``.
    """
    for template in templates:
        rendered = render_template(template, values, padding)
        if rendered is not None:
            return rendered
    segments: list[str] = []
    for segment in templates[-1].split("/"):
        rendered = render_template(segment, values, padding)
        if rendered is not None:
            segments.append(rendered)
    return "/".join(segments)


def detect_year(texts: Iterable[str], today: date | None = None) -> str | None:
    """Rok materiału z nazw i ścieżek. Nie zgaduje: sprzeczne lata dają ``None``.

    Rok akademicki zapisany jako para kolejnych lat (``2023_2024``) sprowadzamy do
    ROKU POCZĄTKOWEGO — tak samo, jak zapisuje go ``syntax.yaml: meta.year_field``.
    """
    limit = (today or date.today()).year + 1
    found = {
        int(match)
        for text in texts
        for match in _YEAR.findall(text)
        if YEAR_MIN <= int(match) <= limit
    }
    if len(found) == 1:
        return str(found.pop())
    if len(found) == 2:
        low, high = sorted(found)
        if high - low == 1:
            return str(low)
    return None


def detect_numbers(folded: str) -> dict[str, str]:
    """Numery slotów (laborka, kolokwium, wykład, projekt) z jednego tekstu."""
    numbers: dict[str, str] = {}
    for name, pattern in _NUMBERS.items():
        matches = {match for match in pattern.findall(folded)}
        if len(matches) == 1:
            numbers[name] = matches.pop()
    return numbers


def detect_prowadzacy(segments: Iterable[str]) -> str | None:
    """Nazwisko prowadzącego z segmentu ścieżki zaczynającego się tytułem."""
    for segment in segments:
        match = _TITLE.match(fold(segment).strip())
        if match:
            name = match.group(1).strip(" ._-")
            if name:
                return name
    return None


def _token_text(value: str) -> str:
    """Tekst sprowadzony do tokenów rozdzielonych spacją: ``(AKO) Architektura`` → ``ako architektura``.

    Ta sama normalizacja, po której dopasowuje :mod:`orglib.subject_manifest` —
    dzięki niej separator w źródle (spacja, podkreślenie, nawias) nie ma znaczenia.
    """
    return " ".join(re.findall(r"[a-z0-9]+", fold(value)))


def _contains_label(text: str, label: str) -> bool:
    """Czy tekst zawiera CAŁY label jako ciąg tokenów (nie fragment słowa)."""
    return bool(label) and f" {label} " in f" {_token_text(text)} "


def _subject_labels(subject: config.Subject, *, include_group: bool = True) -> set[str]:
    """Teksty, po których poznajemy TEN przedmiot w ścieżce.

    ``include_group`` musi być ``False`` przy porównywaniu przedmiotów między sobą:
    grupa (``Wspolne``, ``Systemy``) jest wspólna dla dziesiątek przedmiotów, więc
    zrobiłaby wieloznacznym każdy z nich.
    """
    labels = {_token_text(subject.skrot), _token_text(subject.nazwa)}
    if include_group:
        labels.add(_token_text(subject.grupa))
    labels.update(_token_text(alias) for alias in subject.aliases)
    labels.add(_token_text(f"{subject.skrot}_{subject.nazwa}"))
    return {label for label in labels if label}


def _is_subject_segment(segment: str, labels: set[str]) -> bool:
    """Czy segment ścieżki to nazwa samego przedmiotu (a nie sygnał kategorii)."""
    tokens = _token_text(segment)
    return any(tokens == label or tokens.startswith(f"{label} ") for label in labels)


def is_ignored(path: str, rules: Rules) -> bool:
    """Czy ta ścieżka to artefakt kompilacji/środowiska (``syntax.yaml: ignore``)."""
    pure = PurePosixPath(path)
    if pure.suffix.lower() in rules.ignore_extensions:
        return True
    return any(fold(segment) in rules.ignore_folders for segment in pure.parent.parts)


def _filename(row: Mapping[str, Any]) -> str:
    representative = row.get("source_path") or ""
    paths = row.get("source_paths") or []
    if not representative and paths:
        representative = str(paths[0])
    return PurePosixPath(str(representative)).name


def _paths(row: Mapping[str, Any]) -> list[str]:
    paths = row.get("matched_source_paths") or row.get("source_paths") or []
    return [str(p) for p in paths]


def _scan(text: str, rules: Rules, weight: float) -> tuple[dict[str, float], dict[str, str]]:
    """Słowa kluczowe i numery slotów w JEDNYM tekście, wszystko z tą samą wagą."""
    scores: dict[str, float] = {}
    numbers = detect_numbers(text)
    for spec in rules.categories:
        if spec.matches(text):
            scores[spec.name] = weight
    for field_name in numbers:
        implied = _NUMBER_CATEGORY[field_name]
        if scores.get(implied, 0.0) < weight:
            scores[implied] = weight
    return scores, numbers


def folder_signal(
    paths: Sequence[str], labels: set[str], rules: Rules
) -> tuple[dict[str, tuple[float, str]], dict[str, str], list[str]]:
    """Sygnał z katalogów: wygrywa katalog NAJBLIŻSZY plikowi.

    ``Ćwiczenia/2018/kolokwium2/zad.c`` to zadanie z kolokwium leżące w dziale
    ćwiczeń, a nie remis „ćwiczenia kontra kolokwia”. Dlatego pełną wagę dostaje
    najgłębszy katalog, w którym w ogóle coś trafiło, a płytsze trafienia liczą
    się słabiej (o ``conflict_penalty``) — zostają w grze, gdyby ``forms``
    przedmiotu wykluczyły tę bliższą kategorię.

    Zwraca (wagi kategorii ze źródłem sygnału, numery slotów, segmenty katalogów).
    """
    scores: dict[str, tuple[float, str]] = {}
    numbers: dict[str, str] = {}
    all_segments: list[str] = []
    weak = max(rules.weight_folder - rules.conflict_penalty, 0.0)
    for path in paths:
        segments = [
            segment
            for segment in PurePosixPath(path).parent.parts
            if not _is_subject_segment(segment, labels)
        ]
        all_segments.extend(segments)
        nearest: int | None = None
        for depth, segment in enumerate(reversed(segments)):
            hits, found = _scan(fold(segment), rules, rules.weight_folder)
            if not hits:
                continue
            if nearest is None:
                nearest = depth
            near = depth == nearest
            weight = rules.weight_folder if near else weak
            for name in hits:
                if scores.get(name, (0.0, ""))[0] < weight:
                    scores[name] = (weight, SIGNAL_FOLDER_NEAR if near else SIGNAL_FOLDER_FAR)
            for field_name, value in found.items():
                numbers.setdefault(field_name, value)
    return scores, numbers, all_segments


def _plan_line(
    *,
    sha: str,
    action: str,
    target_rel: str,
    category: str,
    year: str | None,
    confidence: float,
    method: str,
    reason: str,
    needs_review: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": sha,
        "action": action,
        "target_rel": target_rel,
        "category": category,
        "year": year,
        "related_to": None,
        "relation": None,
        "confidence": round(min(max(confidence, 0.0), 1.0), 4),
        "method": method,
        "model": RULES_MODEL,
        "reason": reason[:240],
        "needs_review": needs_review,
    }


def classify_row(
    row: Mapping[str, Any],
    *,
    subject: config.Subject,
    rules: Rules,
    ground_truth: Mapping[str, GroundTruth] | None = None,
    safe_labels: frozenset[str] = frozenset(),
    today: date | None = None,
) -> Outcome:
    """Klasyfikuje JEDNĄ treść manifestu. Nie czyta dysku i nie dotyka bazy.

    ``safe_labels`` to nazwy przedmiotu jednoznaczne w całym katalogu
    (:func:`unambiguous_labels`). Gdy któraś z nich stoi w ścieżce materiału, brak
    semestru w tej ścieżce przestaje być ryzykiem pomyłki przedmiotu i nie zbija
    pewności do review. Domyślnie pusty zbiór, czyli ostrożnie.
    """
    identity_reasons = set(IDENTITY_REVIEW_REASONS)
    sha = str(row.get("sha256") or row.get("source_sha256") or "")
    if not sha:
        raise ValueError(f"pozycja manifestu bez sha256: {row!r}")
    filename = _filename(row)
    paths = _paths(row)
    manifest_reasons = [str(r) for r in (row.get("review_reasons") or [])]
    reasons = list(manifest_reasons)
    if "missing_semester" in manifest_reasons and not any(
        _contains_label(path, label) for path in paths for label in safe_labels
    ):
        identity_reasons.add("missing_semester")

    # 1. Ground truth — stan repo, nie opinia.
    known = (ground_truth or {}).get(sha)
    if known is not None:
        category = rules.folder_to_category.get(fold(known.category or ""), "inne")
        foreign = (
            known.subject_key is not None
            and (known.semester, str(known.subject_key).casefold())
            != (subject.semester, subject.skrot.casefold())
        )
        where = "outdated" if known.is_outdated else category
        reason = f"treść jest już w paczce ({where}): {known.target_relative_path}"
        if foreign:
            reason = f"treść jest już w paczce pod innym przedmiotem: {known.target_relative_path}"
            reasons.append("ground_truth_inny_przedmiot")
        return Outcome(
            decision=_plan_line(
                sha=sha,
                action="skip",
                target_rel=known.target_relative_path,
                category=category,
                year=None,
                confidence=rules.ground_truth_confidence,
                method="deterministic",
                reason=reason,
                needs_review=foreign,
            ),
            reasons=reasons,
        )

    # 2. Artefakty kompilacji — tylko gdy KAŻDA kopia treści nimi jest.
    if paths and all(is_ignored(path, rules) for path in paths):
        return Outcome(
            decision=_plan_line(
                sha=sha,
                action="skip",
                target_rel=f"{subject.target_dir}/inne/{filename}" if filename else subject.target_dir,
                category="inne",
                year=None,
                confidence=rules.ignore_confidence,
                method="deterministic",
                reason=rules.ignore_reason,
                needs_review=False,
            ),
            reasons=reasons,
        )

    # 3. Brak zdrowego źródła — nie ma z czego kopiować; AI tego nie naprawi.
    if not row.get("source_path"):
        reasons.append("brak_zdrowego_zrodla")
        return Outcome(
            decision=_plan_line(
                sha=sha,
                action="quarantine",
                target_rel=f"{subject.target_dir}/inne/{filename}" if filename else subject.target_dir,
                category="inne",
                year=None,
                confidence=0.0,
                method="deterministic",
                reason="wszystkie kopie leżą w poddrzewie duplikatu — brak reprezentanta do kopiowania",
                needs_review=True,
            ),
            reasons=reasons,
        )

    extension = PurePosixPath(filename).suffix.lower()
    size_bytes = int(row.get("size_bytes") or 0)

    # 4. Media poza paczkę (reguła twarda nr 11).
    if extension in rules.media_extensions or str(row.get("content_kind")) == "media":
        target = rules.media_target.replace("{skrot}", subject.skrot).replace("{opis}", filename)
        return Outcome(
            decision=_plan_line(
                sha=sha,
                action="media",
                target_rel=target,
                category="inne",
                year=detect_year([filename, *paths], today),
                confidence=rules.media_confidence,
                method="deterministic",
                reason=f"rozszerzenie {extension or '(brak)'} jest medium — poza paczkę, wpis w inne/nagrania.txt",
                needs_review=False,
            ),
            reasons=reasons,
        )

    # 5. Heurystyka: nazwa pliku > katalogi na ścieżce (od najbliższego) > głowa tekstu.
    allowed = set(allowed_categories(subject, rules))
    labels = _subject_labels(subject)
    folded_name = fold(filename)

    name_scores, numbers = _scan(folded_name, rules, rules.weight_filename)
    scored: dict[str, tuple[float, str]] = {
        name: (weight, SIGNAL_FILENAME) for name, weight in name_scores.items()
    }
    folder_scores, folder_numbers, folder_segments = folder_signal(_paths(row), labels, rules)
    text_scores, _ = _scan(fold(str(row.get("text_head") or "")), rules, rules.weight_text)
    candidates = list(folder_scores.items()) + [
        (name, (weight, SIGNAL_TEXT)) for name, weight in text_scores.items()
    ]
    for name, (weight, signal) in candidates:
        if scored.get(name, (0.0, ""))[0] < weight:
            scored[name] = (weight, signal)
    for field_name, value in folder_numbers.items():
        numbers.setdefault(field_name, value)

    rejected = sorted(name for name in scored if name not in allowed)
    for name in rejected:
        scored.pop(name)
        reasons.append(f"forma_przedmiotu_wyklucza:{name}")

    if not scored:
        reasons.append("brak_sygnalu_kategorii")
        return Outcome(unresolved=_unresolved(row, reasons, None, 0.0), reasons=reasons)

    best = max(weight for weight, _ in scored.values())
    winners = sorted(
        (name for name, (weight, _) in scored.items() if weight == best),
        key=lambda name: (rules.category(name).priority, name),  # type: ignore[union-attr]
    )
    category = winners[0]
    confidence = best
    method = "heuristic"
    if len(winners) > 1:
        confidence -= rules.conflict_penalty
        reasons.append("konflikt_kategorii:" + "+".join(winners))
    capping = [r for r in manifest_reasons if r in identity_reasons]
    if capping:
        confidence = min(confidence, rules.manifest_review_cap)
    if size_bytes > rules.media_threshold_bytes > 0:
        confidence = min(confidence, rules.manifest_review_cap)
        reasons.append("duzy_plik_poza_lista_mediow")

    if confidence < rules.review_min:
        return Outcome(unresolved=_unresolved(row, reasons, category, confidence), reasons=reasons)

    spec = rules.category(category)
    assert spec is not None
    year = detect_year([filename, *paths], today)
    values: dict[str, str] = {"rok": year} if year else {}
    values.update(numbers)
    prowadzacy = detect_prowadzacy(folder_segments)
    if prowadzacy:
        values["prowadzacy"] = prowadzacy
    folder = render_best(spec.templates, values, rules.number_padding)
    target_rel = "/".join(part for part in (subject.target_dir, folder, filename) if part)

    reason = f"kategoria {category} wg: {scored[category][1]}"
    if len(winners) > 1:
        reason += f"; konflikt z {', '.join(winners[1:])}"
    if capping:
        reason += f"; manifest: {', '.join(capping)}"

    return Outcome(
        decision=_plan_line(
            sha=sha,
            action="copy",
            target_rel=target_rel,
            category=category,
            year=year,
            confidence=confidence,
            method=method,
            reason=reason,
            needs_review=confidence < rules.auto_apply,
        ),
        reasons=reasons,
    )


def _unresolved(
    row: Mapping[str, Any], reasons: Sequence[str], category: str | None, confidence: float
) -> dict[str, Any]:
    """Pozycja dla AI (B5): kształt manifestu + ślad po tym, czego reguły nie umiały.

    Zachowuje wszystkie pola manifestu (``text_head``, ``source_paths``, …), więc plik
    ``unresolved.jsonl`` da się podać ``ai_resolve.py`` jako ``--manifest``.
    """
    out = dict(row)
    out["needs_review"] = True
    out["classify_reasons"] = sorted(set(reasons))
    out["classify_best_category"] = category
    out["classify_best_confidence"] = round(confidence, 4)
    return out
