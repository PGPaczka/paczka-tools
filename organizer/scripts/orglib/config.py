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

#: Szablon katalogu docelowego przedmiotu (semestry 1-4, bez poziomu grupy).
#: MUSI być zgodny z ``config/subjects.yaml: meta.target_path_template``.
TARGET_PATH_TEMPLATE: str = "paczka/SEM{semester}/{skrot}_{nazwa}"

#: Szablon katalogu docelowego przedmiotu Z poziomem grupy (semestry 5-7:
#: ``grupa`` to strumień dla SEM5/6, katedra dla SEM7 — patrz
#: :attr:`Subject.grupa`). MUSI być zgodny z
#: ``config/subjects.yaml: meta.target_path_template_grouped``.
TARGET_PATH_TEMPLATE_GROUPED: str = "paczka/SEM{semester}/{grupa}/{skrot}_{nazwa}"

#: Semestry, których katalog docelowy ma dodatkowy poziom grupy (strumień/katedra).
_GROUPED_SEMESTERS: frozenset[int] = frozenset({5, 6, 7})

#: Domyślna nazwa grupy, gdy przedmiot nie ma przypisanego strumienia/katedry.
_DEFAULT_GRUPA: str = "Wspolne"


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


def resolve_within_sources(
    sources_root: Path, source_package: str, source_relative_path: str
) -> Path | None:
    """Skleja ścieżkę pliku źródłowego, pilnując, że nie wychodzi poza ``sources_root``.

    Zwraca ``None``, gdy ``source_relative_path`` jest bezwzględna albo gdy po
    normalizacji (bez rozwijania dowiązań — patrz :func:`_absolutize`) ścieżka
    ląduje poza korzeniem źródeł, np. przez ``..``. Taki wpis w bazie to błąd
    danych, nie próba odczytu — wołający ma przestawić plik na status 'error',
    nie czytać go.
    """
    if Path(source_relative_path).is_absolute():
        return None
    candidate = Path(sources_root) / source_package / source_relative_path
    normalized = Path(os.path.normpath(candidate))
    root_normalized = Path(os.path.normpath(sources_root))
    if not normalized.is_relative_to(root_normalized):
        return None
    return normalized


def check_output_target(
    output: Path, paths: Paths, *, extra: Iterable[Path] = (), symlink_ok: bool = False
) -> None:
    """Odrzuca zapis raportu/planu do drzew materiałów — także przez symlink.

    Wspólna bramka dla wszystkich etapów zapisujących pliki tekstowe
    (``prepare_subject``, ``ai_resolve``, kolejne). Powstała po tym, jak dwie
    kopie tej kontroli rozjechały się w praktyce: jedna rozwijała dowiązania
    symboliczne, druga nie, więc katalog będący dowiązaniem do ``00_SOURCES``
    przechodził przez jedną z nich. Sprawdzamy OBA warianty ścieżki:
    ``realpath`` (łapie dowiązanie) i ``abspath`` (łapie ``..`` bez rozwijania).

    ``symlink_ok`` wyłącza zakaz samego pliku-dowiązania: cel zapisu nim być
    nie może, ale np. baza operacyjna wskazana dowiązaniem jest w porządku.
    """
    output = Path(output)
    candidates = [Path(os.path.abspath(output))]
    try:
        candidates.append(output.resolve())
    except OSError:  # pragma: no cover - ścieżka nie do rozwiązania na tym systemie
        pass
    for protected in (paths.sources, paths.target_repo, paths.media, *extra):
        protected_forms = {Path(os.path.abspath(protected))}
        try:
            protected_forms.add(Path(protected).resolve())
        except OSError:  # pragma: no cover
            pass
        for candidate in candidates:
            if any(candidate.is_relative_to(form) for form in protected_forms):
                raise ValueError(f"zapis w chronionym drzewie jest zabroniony: {output}")
    if not symlink_ok and output.is_symlink():
        raise ValueError(f"plik wyjściowy nie może być symlinkiem: {output}")


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
    #: Katedra prowadząca (tylko SEM7, przypisana na poziomie profilu w YAML);
    #: ``None`` dla przedmiotów spoza ``profile`` (klucz ``wspolne``) i dla
    #: pozostałych semestrów.
    katedra: str | None

    @property
    def key(self) -> tuple[int, str]:
        """Klucz tożsamości przedmiotu: (semestr, skrót)."""
        return (self.semester, self.skrot)

    @property
    def grupa(self) -> str:
        """Poziom grupujący pod semestrem: strumień (SEM5/6) albo katedra (SEM7).

        Domyślnie ``"Wspolne"``, gdy przedmiot nie ma przypisanego strumienia/
        katedry (patrz ``config/subjects.yaml: meta.group_levels``). Dla SEM7
        katalog w repo to DOKŁADNIE ``{katedra}_{profil}`` (ground truth, np.
        ``KAIMS_Algorytmy_I_Modelowanie_Systemów``) — nie sama katedra. Dla
        semestrów 1-4 nieużywana — :attr:`target_dir` jej wtedy nie potrzebuje.
        """
        if self.semester == 7:
            return f"{self.katedra}_{self.profil}" if self.katedra else _DEFAULT_GRUPA
        return self.strumien or _DEFAULT_GRUPA

    @property
    def target_dir(self) -> str:
        """Katalog docelowy w repo produktu, np. ``paczka/SEM3/AKO_Architektura_Komputerów``

        albo, dla SEM5-7, ``paczka/SEM5/Systemy/SBD_Struktury_Baz_Danych``.
        """
        if self.semester in _GROUPED_SEMESTERS:
            return TARGET_PATH_TEMPLATE_GROUPED.format(
                semester=self.semester, grupa=self.grupa, skrot=self.skrot, nazwa=self.nazwa
            )
        return TARGET_PATH_TEMPLATE.format(
            semester=self.semester, skrot=self.skrot, nazwa=self.nazwa
        )


def _semester_groups(
    semester: int | str, block: Any
) -> Iterable[tuple[str | None, str | None, list[dict[str, Any]]]]:
    """Rozbija zawartość jednego semestru na krotki (profil | None, katedra | None, wpisy).

    Katedra jest przypisana CAŁEMU profilowi (SEM7, klucz ``profile``), nie
    pojedynczym wpisom — patrz kształt niżej. Nieznany kształt (klucz inny niż
    ``profile`` bez listy, ``profile`` niebędące mapą ``{katedra, przedmioty}``)
    podnosi ``ValueError`` — literówka w YAML ma być głośna, nie przemilczana
    cichym pominięciem przedmiotów.

    Kształt klucza ``profile``::

        profile:
          Nazwa_Profilu:
            katedra: KASK
            przedmioty: [{skrot: ..., nazwa: ..., ...}, ...]
    """
    if isinstance(block, list):
        yield None, None, block
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
                    f"nazwa_profilu -> {{katedra, przedmioty}}, jest {type(value).__name__}"
                )
            for profil, profile_block in value.items():
                if not isinstance(profile_block, dict):
                    raise ValueError(
                        f"subjects.yaml: semestr {semester}, profil {profil!r}: "
                        f"oczekiwano mapy {{katedra, przedmioty}}, "
                        f"jest {type(profile_block).__name__}"
                    )
                entries = profile_block.get("przedmioty")
                if not isinstance(entries, list):
                    raise ValueError(
                        f"subjects.yaml: semestr {semester}, profil {profil!r}: "
                        f"'przedmioty' musi być listą, jest {type(entries).__name__}"
                    )
                katedra = profile_block.get("katedra")
                yield str(profil), (str(katedra) if katedra is not None else None), entries
        elif isinstance(value, list):
            yield None, None, value
        else:
            raise ValueError(
                f"subjects.yaml: semestr {semester}, klucz {key!r}: oczekiwano listy "
                f"przedmiotów albo klucza 'profile', jest {type(value).__name__}"
            )


def _make_subject(
    semester: int, entry: dict[str, Any], profil: str | None, katedra: str | None
) -> Subject:
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
        katedra=katedra,
    )


def iter_subjects(data: dict[str, Any] | None = None) -> list[Subject]:
    """Spłaszcza ``subjects.yaml`` do listy przedmiotów (sekcja ``magisterskie`` pomijana).

    Wpisy powtórzone w wielu profilach (np. SDII w sem 7) deduplikuje po
    (semestr, skrót, nazwa), zachowując pierwszy napotkany profil. Gdy po tej
    deduplikacji ten sam klucz (semestr, skrót, grupa) wskazuje na dwie różne
    nazwy, podnosi ``ValueError`` — w OBRĘBIE tej samej grupy tożsamość
    przedmiotu przestałaby być rozstrzygalna. (semestr, skrót) SAM nie musi
    być globalnie unikalny w obrębie semestru — patrz kolizja SEM7 SI (KASK
    vs KT) w nagłówku ``subjects.yaml``; rozstrzyga ją dopiero grupa (katedra).
    """
    if data is None:
        data = load_yaml("subjects")
    subjects: list[Subject] = []
    seen: set[tuple[int, str, str]] = set()
    by_key: dict[tuple[int, str, str], str] = {}
    for raw_semester, block in (data.get("semesters") or {}).items():
        semester = int(raw_semester)
        for profil, katedra, entries in _semester_groups(raw_semester, block):
            for entry in entries:
                subject = _make_subject(semester, entry, profil, katedra)
                dedup_key = (subject.semester, subject.skrot, subject.nazwa)
                if dedup_key in seen:
                    continue
                group_key = (subject.semester, subject.skrot, subject.grupa)
                previous = by_key.get(group_key)
                if previous is not None:
                    raise ValueError(
                        f"subjects.yaml: klucz {subject.key} w grupie {subject.grupa!r} "
                        f"wskazuje na dwa różne przedmioty: {previous!r} i {subject.nazwa!r} "
                        "— rozróżnij je skrótem"
                    )
                by_key[group_key] = subject.nazwa
                seen.add(dedup_key)
                subjects.append(subject)
    return subjects


def find_subject(
    semester: int,
    skrot: str,
    subjects: Sequence[Subject] | None = None,
    *,
    grupa: str | None = None,
) -> Subject:
    """Znajduje przedmiot po skrócie LUB aliasie (bez rozróżniania wielkości liter).

    Trafienie w skrót ma pierwszeństwo przed trafieniem w alias. Wieloznaczność
    (ta sama szukana wartość pasuje do kilku przedmiotów w tym semestrze) to
    ``ValueError`` — AI/skrypt nie może tu zgadywać. Brak dopasowania: ``KeyError``.

    ``grupa``, gdy podana, zawęża kandydatów do przedmiotów, dla których
    :attr:`Subject.grupa` == ``grupa`` (dokładne dopasowanie stringa — strumień
    dla SEM5/6, ``{katedra}_{profil}`` dla SEM7, inaczej ``"Wspolne"``).
    Rozstrzyga kolizje w obrębie semestru, których sam skrót nie rozstrzyga
    (patrz SEM7 SI: KASK ``Serwisy_Internetowe_NET`` vs KT ``Sieci_IP``).
    """
    needle = skrot.strip().casefold()
    pool = subjects if subjects is not None else iter_subjects()
    by_skrot: list[Subject] = []
    by_alias: list[Subject] = []
    for subject in pool:
        if subject.semester != semester:
            continue
        if grupa is not None and subject.grupa != grupa:
            continue
        if subject.skrot.casefold() == needle:
            by_skrot.append(subject)
        elif any(alias.casefold() == needle for alias in subject.aliases):
            by_alias.append(subject)

    matches = by_skrot or by_alias
    if not matches:
        grupa_suffix = f", grupa={grupa!r}" if grupa is not None else ""
        raise KeyError(f"brak przedmiotu (semestr={semester}, skrot={skrot!r}{grupa_suffix})")
    if len(matches) > 1:
        candidates = [f"{s.nazwa} (grupa={s.grupa!r})" for s in matches]
        raise ValueError(
            f"wieloznaczne dopasowanie (semestr={semester}, skrot={skrot!r}): "
            f"{candidates} — doprecyzuj skrót albo podaj grupę"
        )
    return matches[0]
