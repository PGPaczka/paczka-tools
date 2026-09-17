"""Loader konfiguracji organizera: ścieżki, progi i katalog przedmiotów.

Jedyne miejsce, w którym kod poznaje ścieżki spoza repo — wszystko pochodzi
z ``config/paths.yaml`` (reguła twarda nr 12: żadnych hardkodowanych ``../../``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

#: Korzeń projektu organizera (katalog nadrzędny ``scripts/``), liczony ze
#: ścieżki tego pliku — nigdy z bieżącego katalogu roboczego.
ORGANIZER_ROOT: Path = Path(__file__).resolve().parents[2]

#: Domyślny katalog z plikami YAML konfiguracji.
CONFIG_DIR: Path = ORGANIZER_ROOT / "config"

#: Szablon katalogu docelowego przedmiotu. MUSI być zgodny z
#: ``config/subjects.yaml: meta.target_path_template``.
TARGET_PATH_TEMPLATE: str = "paczka/SEM{semester}/({skrot})_{nazwa}"


def load_yaml(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Wczytuje ``config/<name>.yaml`` i zwraca słownik (pusty plik => ``{}``)."""
    path = (config_dir or CONFIG_DIR) / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: oczekiwano mapy na najwyższym poziomie")
    return data


@dataclass(frozen=True)
class Paths:
    """Rozwiązane, absolutne ścieżki workspace'u (z ``config/paths.yaml``)."""

    sources: Path
    work: Path
    media: Path
    target_repo: Path
    target_paczka: Path
    work_db: Path
    work_extracted_text: Path
    work_thumbnails: Path


def _absolutize(base: Path, value: str) -> Path:
    """Robi ze ścieżki (względnej wobec ``base``) ścieżkę absolutną i znormalizowaną.

    Świadomie nie używa ``Path.resolve()`` — nie chcemy rozwijać dowiązań
    symbolicznych, a jedynie skleić i złożyć segmenty ``..``.
    """
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return Path(os.path.normpath(path))


def load_paths(config_dir: Path | None = None) -> Paths:
    """Wczytuje ``paths.yaml`` i zwraca absolutne ścieżki workspace'u.

    Ścieżki względne rozwiązywane są wobec :data:`ORGANIZER_ROOT`.
    ``config_dir`` pozwala testom podstawić własny plik konfiguracji.
    """
    data = load_yaml("paths", config_dir)
    missing = [k for k in ("sources", "work", "media", "target_repo") if k not in data]
    if missing:
        raise KeyError(f"paths.yaml: brak kluczy {missing}")

    sources = _absolutize(ORGANIZER_ROOT, data["sources"])
    work = _absolutize(ORGANIZER_ROOT, data["work"])
    media = _absolutize(ORGANIZER_ROOT, data["media"])
    target_repo = _absolutize(ORGANIZER_ROOT, data["target_repo"])
    return Paths(
        sources=sources,
        work=work,
        media=media,
        target_repo=target_repo,
        target_paczka=target_repo / str(data.get("target_paczka_subdir", "paczka")),
        work_db=work / str(data.get("work_db", "organizer.sqlite")),
        work_extracted_text=work / str(data.get("work_extracted_text", "extracted_text")),
        work_thumbnails=work / str(data.get("work_thumbnails", "thumbnails")),
    )


def load_thresholds(config_dir: Path | None = None) -> dict[str, Any]:
    """Wczytuje progi decyzyjne z ``config/thresholds.yaml``."""
    return load_yaml("thresholds", config_dir)


@dataclass(frozen=True)
class Subject:
    """Jeden przedmiot z katalogu. Tożsamość = (semestr, skrót) — skrót sam nie wystarcza."""

    semester: int
    skrot: str
    nazwa: str
    forms: tuple[str, ...]
    aliases: tuple[str, ...]
    instancja: str | None
    strumien: str | None
    profil: str | None

    @property
    def key(self) -> tuple[int, str]:
        """Klucz tożsamości przedmiotu: (semestr, skrót)."""
        return (self.semester, self.skrot)

    @property
    def target_dir(self) -> str:
        """Katalog docelowy w repo produktu, np. ``paczka/SEM3/(AK)_Architektura_Komputerów``."""
        return TARGET_PATH_TEMPLATE.format(
            semester=self.semester, skrot=self.skrot, nazwa=self.nazwa
        )


def _semester_groups(
    semester: int | str, block: Any
) -> Iterable[tuple[str | None, list[dict[str, Any]]]]:
    """Rozbija zawartość jednego semestru na pary (nazwa profilu | None, lista wpisów).

    Nieznany kształt (klucz inny niż ``profile`` bez listy, ``profile`` niebędące
    mapą list) podnosi ``ValueError`` — literówka w YAML ma być głośna, nie
    przemilczana cichym pominięciem przedmiotów.
    """
    if isinstance(block, list):
        yield None, block
        return
    if not isinstance(block, dict):
        raise ValueError(
            f"subjects.yaml: semestr {semester}: nieobsługiwany kształt "
            f"{type(block).__name__} (oczekiwano listy albo mapy)"
        )
    for key, value in block.items():
        if key == "profile":
            if not isinstance(value, dict):
                raise ValueError(
                    f"subjects.yaml: semestr {semester}: klucz 'profile' musi być mapą "
                    f"nazwa_profilu -> lista, jest {type(value).__name__}"
                )
            for profil, entries in value.items():
                if not isinstance(entries, list):
                    raise ValueError(
                        f"subjects.yaml: semestr {semester}, profil {profil!r}: "
                        f"oczekiwano listy przedmiotów, jest {type(entries).__name__}"
                    )
                yield str(profil), entries
        elif isinstance(value, list):
            yield None, value
        else:
            raise ValueError(
                f"subjects.yaml: semestr {semester}, klucz {key!r}: oczekiwano listy "
                f"przedmiotów albo klucza 'profile', jest {type(value).__name__}"
            )


def _make_subject(semester: int, entry: dict[str, Any], profil: str | None) -> Subject:
    """Buduje :class:`Subject` z jednego wpisu YAML."""
    return Subject(
        semester=semester,
        skrot=str(entry["skrot"]),
        nazwa=str(entry["nazwa"]),
        forms=tuple(str(f) for f in entry.get("forms") or ()),
        aliases=tuple(str(a) for a in entry.get("aliases") or ()),
        instancja=(str(entry["instancja"]) if entry.get("instancja") is not None else None),
        strumien=(str(entry["strumien"]) if entry.get("strumien") is not None else None),
        profil=profil,
    )


def iter_subjects(data: dict[str, Any] | None = None) -> list[Subject]:
    """Spłaszcza ``subjects.yaml`` do listy przedmiotów (sekcja ``magisterskie`` pomijana).

    Wpisy powtórzone w wielu profilach (np. SDII w sem 7) deduplikuje po
    (semestr, skrót, nazwa), zachowując pierwszy napotkany profil. Gdy po tej
    deduplikacji ten sam klucz (semestr, skrót) wskazuje na dwie różne nazwy,
    podnosi ``ValueError`` — tożsamość przedmiotu przestałaby być rozstrzygalna.
    """
    if data is None:
        data = load_yaml("subjects")
    subjects: list[Subject] = []
    seen: set[tuple[int, str, str]] = set()
    by_key: dict[tuple[int, str], str] = {}
    for raw_semester, block in (data.get("semesters") or {}).items():
        semester = int(raw_semester)
        for profil, entries in _semester_groups(raw_semester, block):
            for entry in entries:
                subject = _make_subject(semester, entry, profil)
                dedup_key = (subject.semester, subject.skrot, subject.nazwa)
                if dedup_key in seen:
                    continue
                previous = by_key.get(subject.key)
                if previous is not None:
                    raise ValueError(
                        f"subjects.yaml: klucz {subject.key} wskazuje na dwa różne przedmioty: "
                        f"{previous!r} i {subject.nazwa!r} — rozróżnij je skrótem"
                    )
                by_key[subject.key] = subject.nazwa
                seen.add(dedup_key)
                subjects.append(subject)
    return subjects


def find_subject(
    semester: int, skrot: str, subjects: Sequence[Subject] | None = None
) -> Subject:
    """Znajduje przedmiot po skrócie LUB aliasie (bez rozróżniania wielkości liter).

    Trafienie w skrót ma pierwszeństwo przed trafieniem w alias. Wieloznaczność
    (ta sama szukana wartość pasuje do kilku przedmiotów w tym semestrze) to
    ``ValueError`` — AI/skrypt nie może tu zgadywać. Brak dopasowania: ``KeyError``.
    """
    needle = skrot.strip().casefold()
    pool = subjects if subjects is not None else iter_subjects()
    by_skrot: list[Subject] = []
    by_alias: list[Subject] = []
    for subject in pool:
        if subject.semester != semester:
            continue
        if subject.skrot.casefold() == needle:
            by_skrot.append(subject)
        elif any(alias.casefold() == needle for alias in subject.aliases):
            by_alias.append(subject)

    matches = by_skrot or by_alias
    if not matches:
        raise KeyError(f"brak przedmiotu (semestr={semester}, skrot={skrot!r})")
    if len(matches) > 1:
        raise ValueError(
            f"wieloznaczne dopasowanie (semestr={semester}, skrot={skrot!r}): "
            f"{[s.nazwa for s in matches]} — doprecyzuj skrót"
        )
    return matches[0]
