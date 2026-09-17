"""Testy loadera konfiguracji: ścieżki workspace'u i katalog przedmiotów."""

from __future__ import annotations

from pathlib import Path

import pytest

from orglib import config

PATHS_YAML = """\
sources: {sources}
work: {work}
media: {media}
target_repo: {target_repo}
target_paczka_subdir: paczka
work_db: organizer.sqlite
work_extracted_text: extracted_text
work_thumbnails: thumbnails
"""


def _write_paths(tmp_path: Path, **overrides: str) -> Path:
    """Tworzy tymczasowy katalog config/ z własnym paths.yaml."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    values = {
        "sources": str(tmp_path / "00_SOURCES"),
        "work": str(tmp_path / "20_WORK"),
        "media": str(tmp_path / "90_MEDIA"),
        "target_repo": str(tmp_path / "10_NEW" / "Repo"),
    }
    values.update(overrides)
    (config_dir / "paths.yaml").write_text(PATHS_YAML.format(**values), encoding="utf-8")
    return config_dir


def test_load_paths_absolute_and_composed(tmp_path: Path) -> None:
    paths = config.load_paths(_write_paths(tmp_path))

    assert all(
        p.is_absolute()
        for p in (paths.sources, paths.work, paths.media, paths.target_repo, paths.work_db)
    )
    assert paths.sources == tmp_path / "00_SOURCES"
    assert paths.target_paczka == tmp_path / "10_NEW" / "Repo" / "paczka"
    assert paths.work_db == tmp_path / "20_WORK" / "organizer.sqlite"
    assert paths.work_extracted_text == tmp_path / "20_WORK" / "extracted_text"
    assert paths.work_thumbnails == tmp_path / "20_WORK" / "thumbnails"


def test_load_paths_relative_resolved_against_organizer_root(tmp_path: Path) -> None:
    paths = config.load_paths(_write_paths(tmp_path, sources="../../00_SOURCES"))

    assert paths.sources == config.ORGANIZER_ROOT.parent.parent / "00_SOURCES"


def test_load_paths_reports_missing_keys(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "paths.yaml").write_text("sources: /x\n", encoding="utf-8")

    with pytest.raises(KeyError):
        config.load_paths(config_dir)


def test_load_thresholds_has_confidence_gates() -> None:
    thresholds = config.load_thresholds()

    assert thresholds["confidence"]["auto_apply"] == 0.90
    assert thresholds["confidence"]["review_min"] == 0.70


@pytest.fixture(scope="module")
def subjects() -> list[config.Subject]:
    """Prawdziwy katalog przedmiotów z config/subjects.yaml."""
    return config.iter_subjects()


def test_iter_subjects_covers_colliding_shortcuts(subjects: list[config.Subject]) -> None:
    keys = {s.key for s in subjects}

    assert (3, "AK") in keys
    assert (7, "AK") in keys
    assert (7, "SI.") in keys
    assert (4, "SI") in keys


def test_iter_subjects_keeps_aliases(subjects: list[config.Subject]) -> None:
    ak3 = next(s for s in subjects if s.key == (3, "AK"))

    assert "AKO" in ak3.aliases


def test_iter_subjects_dedupes_sdii_in_semester_7(subjects: list[config.Subject]) -> None:
    sdii7 = [s for s in subjects if s.key == (7, "SDII")]

    assert len(sdii7) == 1
    assert sdii7[0].profil == "Architektura_systemów_komputerowych"


def test_iter_subjects_marks_profiles_and_streams(subjects: list[config.Subject]) -> None:
    ak7 = next(s for s in subjects if s.key == (7, "AK"))
    sbd = next(s for s in subjects if s.key == (5, "SBD"))
    pdii7 = next(s for s in subjects if s.key == (7, "PDII"))

    assert ak7.profil == "Inteligentne_systemy_interaktywne"
    assert sbd.strumien == "Systemy"
    assert pdii7.profil is None


def test_iter_subjects_skips_magisterskie(subjects: list[config.Subject]) -> None:
    assert {s.semester for s in subjects} == {1, 2, 3, 4, 5, 6, 7}


def test_find_subject_by_alias_case_insensitive(subjects: list[config.Subject]) -> None:
    assert config.find_subject(3, "ako", subjects).nazwa == "Architektura_Komputerów"
    assert config.find_subject(7, "AK", subjects).nazwa == "Animacja_Komputerowa"
    assert config.find_subject(4, "si", subjects).nazwa == "Sztuczna_Inteligencja"


def test_find_subject_missing_raises(subjects: list[config.Subject]) -> None:
    with pytest.raises(KeyError):
        config.find_subject(1, "NIE_MA", subjects)


def test_target_dir_matches_yaml_template(subjects: list[config.Subject]) -> None:
    ak3 = config.find_subject(3, "AK", subjects)

    assert ak3.target_dir == "paczka/SEM3/(AK)_Architektura_Komputerów"
    assert config.load_yaml("subjects")["meta"]["target_path_template"] == config.TARGET_PATH_TEMPLATE


# --- walidacja kształtu YAML i tożsamości przedmiotu -------------------------


def test_iter_subjects_rejects_unknown_semester_key() -> None:
    data = {"semesters": {"7": {"profiles": {"X": [{"skrot": "A", "nazwa": "A_x"}]}}}}

    with pytest.raises(ValueError, match="'profiles'"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_profile_that_is_not_a_mapping() -> None:
    data = {"semesters": {"7": {"profile": [{"skrot": "A", "nazwa": "A_x"}]}}}

    with pytest.raises(ValueError, match="'profile' musi być mapą"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_profile_entries_that_are_not_a_list() -> None:
    data = {"semesters": {"7": {"profile": {"X": {"skrot": "A", "nazwa": "A_x"}}}}}

    with pytest.raises(ValueError, match="oczekiwano listy przedmiotów"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_non_mapping_semester() -> None:
    data = {"semesters": {"7": "AK"}}

    with pytest.raises(ValueError, match="nieobsługiwany kształt"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_same_key_with_different_name() -> None:
    data = {
        "semesters": {
            "3": [
                {"skrot": "AK", "nazwa": "Architektura_Komputerów"},
                {"skrot": "AK", "nazwa": "Animacja_Komputerowa"},
            ]
        }
    }

    with pytest.raises(ValueError, match=r"\(3, 'AK'\)"):
        config.iter_subjects(data)


def test_iter_subjects_allows_same_entry_in_many_profiles() -> None:
    entry = {"skrot": "SDII", "nazwa": "Seminarium", "forms": ["S"]}
    data = {"semesters": {"7": {"profile": {"A": [dict(entry)], "B": [dict(entry)]}}}}

    subjects = config.iter_subjects(data)

    assert [s.profil for s in subjects] == ["A"]


def test_find_subject_rejects_ambiguous_alias() -> None:
    data = {
        "semesters": {
            "3": [
                {"skrot": "AK", "nazwa": "Architektura_Komputerów", "aliases": ["KOMP"]},
                {"skrot": "GK", "nazwa": "Grafika_Komputerowa", "aliases": ["komp"]},
            ]
        }
    }
    subjects = config.iter_subjects(data)

    with pytest.raises(ValueError, match="wieloznaczne"):
        config.find_subject(3, "KOMP", subjects)


def test_find_subject_prefers_skrot_over_alias() -> None:
    data = {
        "semesters": {
            "3": [
                {"skrot": "GK", "nazwa": "Grafika_Komputerowa", "aliases": []},
                {"skrot": "MII", "nazwa": "Multimedia_I_Interfejsy", "aliases": ["GK"]},
            ]
        }
    }
    subjects = config.iter_subjects(data)

    assert config.find_subject(3, "gk", subjects).nazwa == "Grafika_Komputerowa"
