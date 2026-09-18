"""Sonda: `config/subjects.yaml` kontra PRAWDZIWA struktura `paczka/` w `target_repo`.

Jedyny test w tym repo, który czyta `target_repo` (`config/paths.yaml`) — TYLKO
do odczytu, nigdy nie modyfikuje (reguła twarda nr 1/2). Pomijany (`pytest.skip`),
gdy `target_repo/paczka` nie istnieje lokalnie (np. w CI bez klona repo produktu).

Sprawdza w OBIE strony:
1. każdy ``Subject.target_dir`` wskazuje na katalog, który FAKTYCZNIE istnieje
   w repo (poza jawną listą wyjątków — przedmioty bez materiałów w paczce),
2. każdy katalog przedmiotu leżący w repo da się odtworzyć z `subjects.yaml`
   (żeby ground truth nigdy nie miało "cichej" ścieżki, o której klasyfikator
   nie wie).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orglib import config

#: Sonda na REALNYCH danych lokalnych — patrz sekcja „Warstwy testów” w README.
pytestmark = pytest.mark.probe

#: Przedmioty bez materiałów w target_repo (brak katalogu) — świadomy,
#: udokumentowany wyjątek, NIE luka w subjects.yaml.
_ALLOWED_MISSING: frozenset[tuple[int, str]] = frozenset({(2, "WFI"), (3, "WFI")})

#: Nazwy katalogów pod SEM{n}, które nigdy nie są przedmiotem (patrz
#: scripts/scan_target.py: _OUT_OF_SCOPE_DIR_NAMES) — pomijane przy odtwarzaniu
#: listy "prawdziwych" katalogów przedmiotów z dysku.
_NOT_A_SUBJECT_DIR = {"sources"}


def _target_paczka() -> Path | None:
    """Katalog `paczka/` w target_repo, albo `None`, gdy nie ma go NA DYSKU.

    Rozróżnienie jest celowe i wynika z zasady „brak ma być czerwony, nie
    pominięty” (audyt 2026-09-18). Sonda pomija się wyłącznie wtedy, gdy
    lokalnie nie ma klona repo produktu — to brak DANYCH, nie awaria. Natomiast
    config, którego nie da się wczytać (brakujący klucz, zły YAML), jest awarią
    i leci dalej jako błąd: wcześniej `except (FileNotFoundError, KeyError,
    ValueError)` połykał go i sonda cichła w `skip`, maskując zepsuty
    `paths.yaml`.
    """
    paths = config.load_paths()
    return paths.target_paczka if paths.target_paczka.is_dir() else None


def _real_subject_dirs(target_paczka: Path) -> set[str]:
    """Katalogi przedmiotów faktycznie leżące w repo, jako ``paczka/SEM.../...``.

    SEM1-4: katalog przedmiotu leży bezpośrednio pod ``SEM{n}/``. SEM5-7: jeden
    poziom niżej, pod strumieniem/katedrą (``SEM{n}/{grupa}/{skrot}_{nazwa}``).
    Foldery zbiorcze (``sources``) i pliki luzem (nie-katalogi) są pomijane.
    """
    dirs: set[str] = set()
    for sem_dir in sorted(target_paczka.glob("SEM[1-7]")):
        semester = int(sem_dir.name[3:])
        if semester <= 4:
            for child in sem_dir.iterdir():
                if child.is_dir() and child.name not in _NOT_A_SUBJECT_DIR:
                    dirs.add(f"paczka/{sem_dir.name}/{child.name}")
        else:
            for grupa_dir in sem_dir.iterdir():
                if not grupa_dir.is_dir() or grupa_dir.name in _NOT_A_SUBJECT_DIR:
                    continue
                for child in grupa_dir.iterdir():
                    if child.is_dir():
                        dirs.add(f"paczka/{sem_dir.name}/{grupa_dir.name}/{child.name}")
    return dirs


def test_every_subject_target_dir_exists_in_target_repo() -> None:
    """subjects.yaml -> repo: każdy target_dir musi mieć realny odpowiednik na dysku."""
    target_paczka = _target_paczka()
    if target_paczka is None:
        pytest.skip("target_repo niedostępny lokalnie (config/paths.yaml: target_repo)")

    target_repo = target_paczka.parent
    subjects = config.iter_subjects()

    missing = sorted(
        f"{s.key} -> {s.target_dir}"
        for s in subjects
        if s.key not in _ALLOWED_MISSING and not (target_repo / s.target_dir).is_dir()
    )

    assert not missing, "target_dir bez odpowiadającego katalogu w repo:\n" + "\n".join(missing)


def test_every_real_subject_dir_maps_back_to_a_subject() -> None:
    """repo -> subjects.yaml: każdy katalog przedmiotu w repo musi mieć swój wpis."""
    target_paczka = _target_paczka()
    if target_paczka is None:
        pytest.skip("target_repo niedostępny lokalnie (config/paths.yaml: target_repo)")

    subjects = config.iter_subjects()
    known_dirs = {s.target_dir for s in subjects}
    real_dirs = _real_subject_dirs(target_paczka)

    leftovers = sorted(real_dirs - known_dirs)

    assert not leftovers, (
        "katalogi w repo bez odpowiadającego przedmiotu w subjects.yaml:\n"
        + "\n".join(leftovers)
    )
