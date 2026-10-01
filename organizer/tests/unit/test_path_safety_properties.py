"""Własności granicy ścieżek: dla KAŻDEGO wejścia, nie tylko dla wymyślonych przykładów.

Cztery funkcje w tym projekcie decydują, czy wolno coś przeczytać albo zapisać:
`resolve_within_sources`, `check_output_target`, `_safe_path` i `folder_path_for`.
Testy przykładowe pokrywają z definicji to, co przyszło autorowi do głowy — a tu
liczy się wejście, którego NIE wymyślił: `..` w środku, ścieżka absolutna, NUL,
backslash z Windows, nazwa udająca flagę, sztuczki z normalizacją Unicode.

Każdy test formułuje JEDNĄ własność, która musi zachodzić zawsze. Hypothesis
szuka kontrprzykładu i — gdy go znajdzie — pokazuje najkrótszy.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from orglib import config, db
from orglib.subject_manifest import _safe_path

#: Kawałki nazw, z których składamy ścieżki: zwykłe, ale też te niebezpieczne.
SEGMENT = st.sampled_from([
    "a", "plik.pdf", "SEM3", "AKO", "..", ".", "", "/", "//", "\\", "\x00",
    " ", "-rf", "--output", "ą", "Á", "‮", "x" * 80, "..\\..", "....//",
])

#: Ścieżka jako sklejka kilku takich kawałków.
PATHISH = st.lists(SEGMENT, min_size=1, max_size=5).map("/".join)

#: To samo, ale zawsze absolutne. Generujemy wprost, zamiast odsiewać przez
#: `assume` — filtrowanie zniekształciłoby rozkład i spowolniło generowanie.
ABSOLUTE_PATHISH = st.lists(SEGMENT, min_size=1, max_size=4).map(lambda parts: "/" + "/".join(parts))


@settings(max_examples=300, deadline=None)
@given(package=PATHISH, relative=PATHISH)
def test_resolve_within_sources_never_escapes_the_root(package: str, relative: str) -> None:
    """Własność: wynik jest albo ``None``, albo ścieżką WEWNĄTRZ korzenia źródeł.

    Nie ma trzeciej możliwości. To jedyna funkcja, przez którą etapy potoku
    zamieniają wpis z bazy na ścieżkę do odczytu materiału.
    """
    root = Path("/workspace/00_SOURCES")
    try:
        resolved = config.resolve_within_sources(root, package, relative)
    except ValueError:
        return  # jawne odrzucenie wejścia jest w porządku
    if resolved is None:
        return
    normalized = Path(os.path.normpath(resolved))
    assert normalized == root or normalized.is_relative_to(root), (
        f"ucieczka poza korzeń: {package!r} + {relative!r} -> {resolved}"
    )


@settings(max_examples=200, deadline=None)
@given(relative=ABSOLUTE_PATHISH)
def test_absolute_relative_path_is_always_rejected(relative: str) -> None:
    """Własność: ścieżka absolutna w indeksie NIGDY nie daje wyniku.

    Wpis absolutny to błąd danych — gdyby przeszedł, etap czytałby plik spoza
    katalogu źródeł, o którym baza nic nie wie.
    """
    assert config.resolve_within_sources(Path("/workspace/00_SOURCES"), "P1", relative) is None


@pytest.fixture(scope="module")
def protected_workspace(tmp_path_factory) -> config.Paths:
    """Katalogi chronione zakładane RAZ na moduł (Hypothesis nie resetuje fixtur)."""
    return _paths(tmp_path_factory.mktemp("workspace"))


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(extra=PATHISH)
def test_output_inside_protected_tree_is_always_rejected(
    protected_workspace: config.Paths, extra: str
) -> None:
    """Własność: cokolwiek doklejonego do drzewa materiałów jest odrzucane.

    Bramka zapisu nie może zależeć od kształtu reszty ścieżki.
    """
    paths = protected_workspace
    for protected in (paths.sources, paths.target_repo, paths.media):
        candidate = Path(str(protected) + "/" + extra)
        try:
            config.check_output_target(candidate, paths)
        except ValueError:
            continue
        # Brak wyjątku wolno zaakceptować TYLKO wtedy, gdy po normalizacji
        # ścieżka naprawdę wyszła poza drzewo chronione (np. przez `..`).
        normalized = Path(os.path.normpath(candidate))
        assert not normalized.is_relative_to(Path(os.path.abspath(protected))), (
            f"przepuszczony zapis w chronionym drzewie: {candidate}"
        )


@settings(max_examples=300, deadline=None)
@given(package=PATHISH, relative=PATHISH)
def test_safe_path_output_is_always_a_clean_relative_path(package: str, relative: str) -> None:
    """Własność: albo ``ValueError``, albo ścieżka bez ``..``, bez NUL i bez backslasha.

    `_safe_path` buduje ścieżkę, którą dostaje do ręki przyszła ekstrakcja —
    wynik musi być bezpieczny bez dalszego sprawdzania.
    """
    try:
        result = _safe_path(package, relative)
    except ValueError:
        return
    assert "\x00" not in result and "\\" not in result
    assert not result.startswith("/")
    assert ".." not in Path(result).parts
    assert "" not in Path(result).parts


@settings(max_examples=300, deadline=None)
@given(package=st.text(min_size=1, max_size=20), relative=PATHISH)
def test_folder_path_always_starts_with_its_package(package: str, relative: str) -> None:
    """Własność: katalog pliku zawsze zaczyna się nazwą swojej paczki.

    Na tym stoi całe wiązanie plików z katalogami w bazie (i skip poddrzew
    duplikatów, który porównuje prefiksy).
    """
    assume("/" not in package and package.strip())
    try:
        folder = db.folder_path_for(package, relative)
    except ValueError:
        return
    assert folder == package or folder.startswith(package + "/")


def _paths(tmp_path: Path) -> config.Paths:
    roots = {name: tmp_path / name for name in ("sources", "work", "media", "target")}
    for root in roots.values():
        root.mkdir(exist_ok=True)
    return config.Paths(
        sources=roots["sources"], work=roots["work"], media=roots["media"],
        target_repo=roots["target"], target_paczka=roots["target"] / "paczka",
        work_db=roots["work"] / "organizer.sqlite",
        work_extracted_text=roots["work"] / "text",
        work_thumbnails=roots["work"] / "thumbs",
    )
