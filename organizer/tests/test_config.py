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

    assert (3, "AKO") in keys
    assert (7, "AK") in keys
    assert (7, "SI") in keys
    assert (4, "SI") in keys


def test_iter_subjects_keeps_aliases(subjects: list[config.Subject]) -> None:
    ako3 = next(s for s in subjects if s.key == (3, "AKO"))

    assert "AK" in ako3.aliases
    assert "AKO2020" in ako3.aliases


def test_iter_subjects_has_single_sdiii_in_semester_7(subjects: list[config.Subject]) -> None:
    """SDII było kiedyś powtórzone w każdym profilu sem7 — dziś jest jeden SDIII (wspolne)."""
    sdiii7 = [s for s in subjects if s.key == (7, "SDIII")]

    assert len(sdiii7) == 1
    assert sdiii7[0].profil is None
    assert "SDII" in sdiii7[0].aliases
    assert not any(s.key == (7, "SDII") for s in subjects)


def test_iter_subjects_marks_profiles_and_streams(subjects: list[config.Subject]) -> None:
    ak7 = next(s for s in subjects if s.key == (7, "AK"))
    sbd = next(s for s in subjects if s.key == (5, "SBD"))
    pdiii7 = next(s for s in subjects if s.key == (7, "PDIII"))

    assert ak7.profil == "Inteligentne_Systemy_Interaktywne"
    assert sbd.strumien == "Systemy"
    assert pdiii7.profil is None
    assert "PDII" in pdiii7.aliases


def test_iter_subjects_marks_katedra_from_profile(subjects: list[config.Subject]) -> None:
    ak7 = next(s for s in subjects if s.key == (7, "AK"))
    pgk7 = next(s for s in subjects if s.key == (7, "PGK"))
    pdiii7 = next(s for s in subjects if s.key == (7, "PDIII"))

    assert ak7.katedra == "KISI"
    assert pgk7.katedra == "KISI"
    assert pdiii7.katedra is None  # wspolne — grupa domyślnie "Wspolne"


def test_no_duplicate_semester_grupa_skrot_keys(subjects: list[config.Subject]) -> None:
    """(semestr, skrot) sam NIE jest już unikalny globalnie (SEM7 SI: KASK vs KT) —
    unikalna jest dopiero (semestr, grupa, skrot); patrz KOLIZJE w subjects.yaml.
    """
    keys = [(s.semester, s.grupa, s.skrot) for s in subjects]

    assert len(keys) == len(set(keys))


def test_every_sem7_subject_has_known_katedra(subjects: list[config.Subject]) -> None:
    # grupa SEM7 to "{katedra}_{profil}" DOKŁADNIE jak katalog w repo (albo
    # "Wspolne" bez profilu) — patrz Subject.grupa / ground truth SEM7/*.
    allowed = {
        "KAIMS_Algorytmy_I_Modelowanie_Systemów",
        "KASK_Architektura_Systemów_Komputerowych",
        "KBD_Bazy_Danych",
        "KISI_Inteligentne_Systemy_Interaktywne",
        "KSG_Systemy_Geoinformatyczne",
        "KT_Teleinformatyka",
        "Wspolne",
    }

    for subject in subjects:
        if subject.semester == 7:
            assert subject.grupa in allowed, subject


def test_every_sem5_sem6_subject_has_known_strumien(subjects: list[config.Subject]) -> None:
    allowed = {"Aplikacje", "Systemy", "Wspolne"}

    for subject in subjects:
        if subject.semester in (5, 6):
            assert subject.grupa in allowed, subject


def test_iter_subjects_skips_magisterskie(subjects: list[config.Subject]) -> None:
    assert {s.semester for s in subjects} == {1, 2, 3, 4, 5, 6, 7}


def test_find_subject_by_alias_case_insensitive(subjects: list[config.Subject]) -> None:
    assert config.find_subject(3, "ako", subjects).nazwa == "Architektura_Komputerów"
    assert config.find_subject(7, "AK", subjects).nazwa == "Animacja_Komputerowa"
    assert config.find_subject(4, "si", subjects).nazwa == "Sztuczna_Inteligencja"


def test_find_subject_missing_raises(subjects: list[config.Subject]) -> None:
    with pytest.raises(KeyError):
        config.find_subject(1, "NIE_MA", subjects)


def test_find_subject_resolves_renamed_skroty_by_old_alias(
    subjects: list[config.Subject],
) -> None:
    assert config.find_subject(3, "AK", subjects).skrot == "AKO"
    assert config.find_subject(3, "ako", subjects).skrot == "AKO"
    assert config.find_subject(1, "HDI", subjects).skrot == "HDMI"
    assert config.find_subject(7, "SDII", subjects).skrot == "SDIII"
    assert config.find_subject(7, "jpnp.", subjects).skrot == "JPNP"


def test_target_dir_matches_yaml_template(subjects: list[config.Subject]) -> None:
    ako3 = config.find_subject(3, "AK", subjects)

    assert ako3.target_dir == "paczka/SEM3/AKO_Architektura_Komputerów"
    assert config.load_yaml("subjects")["meta"]["target_path_template"] == config.TARGET_PATH_TEMPLATE
    assert (
        config.load_yaml("subjects")["meta"]["target_path_template_grouped"]
        == config.TARGET_PATH_TEMPLATE_GROUPED
    )


def test_target_dir_uses_grupa_for_sem5_sem6_sem7(subjects: list[config.Subject]) -> None:
    sbd = config.find_subject(5, "SBD", subjects)
    io = config.find_subject(5, "IO", subjects)
    pgk = config.find_subject(7, "PGK", subjects)
    pdiii = config.find_subject(7, "PDII", subjects)

    assert sbd.target_dir == "paczka/SEM5/Systemy/SBD_Struktury_Baz_Danych"
    assert io.target_dir == "paczka/SEM5/Wspolne/IO_Inżynieria_Oprogramowania"
    assert (
        pgk.target_dir
        == "paczka/SEM7/KISI_Inteligentne_Systemy_Interaktywne/PGK_Projektowanie_Gier_Komputerowych"
    )
    assert pdiii.target_dir == "paczka/SEM7/Wspolne/PDIII_Projekt_Dyplomowy_Inżynierski_II"


def test_target_dir_matches_renamed_ground_truth_dirs(subjects: list[config.Subject]) -> None:
    """PGI/PGII/SEM7-SI dopasowane do katalogów przemianowanych w target_repo
    (branch fix/nazwy-katalogow-przedmiotow — patrz TODO.md A9)."""
    pgi = config.find_subject(5, "PGI", subjects)
    pgii = config.find_subject(6, "PGII", subjects)
    si_kask = config.find_subject(
        7, "SI", subjects, grupa="KASK_Architektura_Systemów_Komputerowych"
    )

    assert pgi.target_dir == "paczka/SEM5/Wspolne/PGI_Projekt_Grupowy_I"
    assert pgii.target_dir == "paczka/SEM6/Wspolne/PGII_Projekt_Grupowy_II"
    assert (
        si_kask.target_dir
        == "paczka/SEM7/KASK_Architektura_Systemów_Komputerowych/SI_Serwisy_Internetowe_NET"
    )


def test_find_subject_sem7_si_ambiguous_without_grupa(subjects: list[config.Subject]) -> None:
    """Bez grupy SEM7 SI jest wieloznaczne (KASK Serwisy_Internetowe_NET vs KT Sieci_IP)."""
    with pytest.raises(ValueError, match="wieloznaczne") as exc:
        config.find_subject(7, "SI", subjects)

    assert "Serwisy_Internetowe_NET" in str(exc.value)
    assert "Sieci_IP" in str(exc.value)


def test_find_subject_sem7_si_resolved_by_grupa(subjects: list[config.Subject]) -> None:
    kask = config.find_subject(
        7, "SI", subjects, grupa="KASK_Architektura_Systemów_Komputerowych"
    )
    kt = config.find_subject(7, "SI", subjects, grupa="KT_Teleinformatyka")

    assert kask.nazwa == "Serwisy_Internetowe_NET"
    assert kt.nazwa == "Sieci_IP"


def test_find_subject_sem7_si_dot_alias_still_unique(subjects: list[config.Subject]) -> None:
    """Stary skrót "SI." żyje jako alias TYLKO na przedmiocie KASK — bez grupy nadal jednoznaczny."""
    assert config.find_subject(7, "SI.", subjects).nazwa == "Serwisy_Internetowe_NET"


def test_find_subject_sem4_si_unaffected_by_sem7_collision(subjects: list[config.Subject]) -> None:
    assert config.find_subject(4, "SI", subjects).nazwa == "Sztuczna_Inteligencja"


# --- walidacja kształtu YAML i tożsamości przedmiotu -------------------------


def test_iter_subjects_rejects_unknown_semester_key() -> None:
    data = {"semesters": {"7": {"profiles": {"X": [{"skrot": "A", "nazwa": "A_x"}]}}}}

    with pytest.raises(ValueError, match="'profiles'"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_profile_that_is_not_a_mapping() -> None:
    data = {"semesters": {"7": {"profile": [{"skrot": "A", "nazwa": "A_x"}]}}}

    with pytest.raises(ValueError, match="'profile' musi być mapą"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_profile_block_that_is_not_a_mapping() -> None:
    data = {"semesters": {"7": {"profile": {"X": [{"skrot": "A", "nazwa": "A_x"}]}}}}

    with pytest.raises(ValueError, match="oczekiwano mapy"):
        config.iter_subjects(data)


def test_iter_subjects_rejects_profile_without_przedmioty_list() -> None:
    data = {"semesters": {"7": {"profile": {"X": {"katedra": "KX", "skrot": "A"}}}}}

    with pytest.raises(ValueError, match="'przedmioty' musi być listą"):
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
    data = {
        "semesters": {
            "7": {
                "profile": {
                    "A": {"katedra": "KA", "przedmioty": [dict(entry)]},
                    "B": {"katedra": "KB", "przedmioty": [dict(entry)]},
                }
            }
        }
    }

    subjects = config.iter_subjects(data)

    assert [(s.profil, s.katedra) for s in subjects] == [("A", "KA")]


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


# --------------------------------------------------------------------------- #
# Realne pliki konfiguracji — nie tylko stuby loadera
# --------------------------------------------------------------------------- #
#
# Testy wyżej podstawiają własny YAML i słusznie: sprawdzają LOADER. Ale audyt
# 2026-09-18 pokazał lukę: usunięcie klucza `media` z prawdziwego
# `config/paths.yaml` nie oblewało niczego, choć każdy skrypt uruchomiony bez
# jawnych ścieżek leci wtedy `KeyError` przy starcie.


def test_real_paths_yaml_loads() -> None:
    """Prawdziwy config/paths.yaml musi dać się wczytać bez podstawiania niczego."""
    paths = config.load_paths()
    for name in ("sources", "work", "media", "target_repo", "target_paczka", "work_db"):
        value = getattr(paths, name)
        assert value.is_absolute(), f"{name} nie jest ścieżką absolutną: {value}"


def test_real_paths_yaml_keeps_trees_separate() -> None:
    """Drzewa workspace'u nie mogą się zagnieżdżać — na tym stoją wszystkie bramki zapisu."""
    paths = config.load_paths()
    roots = {
        "sources": paths.sources, "work": paths.work,
        "media": paths.media, "target_repo": paths.target_repo,
    }
    for first, first_path in roots.items():
        for second, second_path in roots.items():
            if first >= second:
                continue
            assert not first_path.is_relative_to(second_path), f"{first} leży wewnątrz {second}"
            assert not second_path.is_relative_to(first_path), f"{second} leży wewnątrz {first}"


def test_real_thresholds_yaml_has_usable_llm_section() -> None:
    """Backend AI z realnego thresholds.yaml musi być znany klientowi LLM.

    Literówka (`codex-cli` zamiast `codex_cli`) przechodziła wszystkie testy
    i wychodziła dopiero przy pierwszym, PŁATNYM wywołaniu modelu.
    """
    from orglib.llm_client import KNOWN_BACKENDS

    llm = config.load_thresholds()["llm"]
    backends = [llm.get("backend")]
    for task in ("classify", "relate"):
        section = llm.get(task) or {}
        if section.get("backend"):
            backends.append(section["backend"])
    for backend in backends:
        assert backend in KNOWN_BACKENDS, f"nieznany backend w thresholds.yaml: {backend!r}"
