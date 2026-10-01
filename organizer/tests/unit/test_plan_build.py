"""B7: scalanie decyzji w jeden plan. Czysta logika — bez bazy i bez plików."""

from __future__ import annotations

import pytest

from orglib.plan_build import (
    MAX_DISAMBIGUATION_LEVELS,
    META_KEY,
    METHOD_PRIORITY,
    attach_relations,
    build,
    merge_decisions,
    plan_hash,
    resolve_collisions,
    sanitize_segment,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def decision(sha=SHA_A, **overrides):
    row = {
        "schema_version": 1, "source_sha256": sha, "action": "copy",
        "target_rel": "paczka/SEM3/AKO_X/kolokwia/kol_02/main.c", "category": "kolokwia",
        "year": None, "related_to": None, "relation": None, "confidence": 0.9,
        "method": "heuristic", "model": "deterministic", "reason": "test", "needs_review": False,
    }
    row.update(overrides)
    return row


# -- pierwszeństwo decyzji --------------------------------------------------


def test_method_priority_is_the_documented_order() -> None:
    """Kolejność wypisana wprost: człowiek > deterministyka > heurystyka > model."""
    assert sorted(METHOD_PRIORITY, key=METHOD_PRIORITY.get) == [
        "manual", "deterministic", "heuristic", "llm",
    ]


def test_one_decision_per_content_and_the_stronger_method_wins() -> None:
    rows, conflicts = merge_decisions(
        [decision(method="llm", target_rel="paczka/z/modelu.pdf")],
        [decision(method="deterministic", target_rel="paczka/z/regul.pdf")],
    )

    assert [row["target_rel"] for row in rows] == ["paczka/z/regul.pdf"]
    assert conflicts == [{
        "source_sha256": SHA_A, "kept": "deterministic", "dropped": "llm",
        "kept_target": "paczka/z/regul.pdf", "dropped_target": "paczka/z/modelu.pdf",
    }]


def test_a_dropped_decision_is_never_silent() -> None:
    _, conflicts = merge_decisions([decision(method="deterministic")], [decision(method="llm")])

    assert len(conflicts) == 1, "odrzucona decyzja musi zostać zaraportowana"


def test_rows_are_sorted_by_content_so_the_file_is_stable() -> None:
    rows, _ = merge_decisions([decision(SHA_C), decision(SHA_A), decision(SHA_B)])

    assert [row["source_sha256"] for row in rows] == [SHA_A, SHA_B, SHA_C]


def test_line_without_sha_is_an_error() -> None:
    with pytest.raises(ValueError, match="bez source_sha256"):
        merge_decisions([{"action": "copy"}])


# -- kolizje ----------------------------------------------------------------


def test_collision_is_resolved_with_the_source_directory() -> None:
    """Decyzja użytkownika 2026-09-19: znaczenie niesie katalog, nie nazwa pliku."""
    rows, notes = resolve_collisions(
        [decision(SHA_A), decision(SHA_B)],
        {
            SHA_A: "P/AKO/kolokwium2/Zadanie 23/main.c",
            SHA_B: "P/AKO/kolokwium2/funkcjarekurencja/main.c",
        },
    )

    assert [row["target_rel"] for row in rows] == [
        "paczka/SEM3/AKO_X/kolokwia/kol_02/Zadanie 23/main.c",
        "paczka/SEM3/AKO_X/kolokwia/kol_02/funkcjarekurencja/main.c",
    ]
    assert len(notes) == 2 and notes[0]["from"].endswith("kol_02/main.c")


def test_files_of_one_solution_stay_together() -> None:
    """`main.c` i `func.asm` z jednego zadania mają wylądować w JEDNYM katalogu."""
    rows, _ = resolve_collisions(
        [
            decision(SHA_A), decision(SHA_B),
            decision(SHA_C, target_rel="paczka/SEM3/AKO_X/kolokwia/kol_02/func.asm"),
            decision("d" * 64, target_rel="paczka/SEM3/AKO_X/kolokwia/kol_02/func.asm"),
        ],
        {
            SHA_A: "P/AKO/kol2/Zadanie 23/main.c", SHA_B: "P/AKO/kol2/Zadanie 1/main.c",
            SHA_C: "P/AKO/kol2/Zadanie 23/func.asm", "d" * 64: "P/AKO/kol2/Zadanie 1/func.asm",
        },
    )

    by_dir: dict[str, set[str]] = {}
    for row in rows:
        folder, _, name = str(row["target_rel"]).rpartition("/")
        by_dir.setdefault(folder, set()).add(name)
    assert by_dir["paczka/SEM3/AKO_X/kolokwia/kol_02/Zadanie 23"] == {"main.c", "func.asm"}
    assert by_dir["paczka/SEM3/AKO_X/kolokwia/kol_02/Zadanie 1"] == {"main.c", "func.asm"}


def test_deeper_levels_are_added_when_one_is_not_enough() -> None:
    rows, _ = resolve_collisions(
        [decision(SHA_A), decision(SHA_B)],
        {SHA_A: "P/AKO/2018/zadanie/main.c", SHA_B: "P/AKO/2019/zadanie/main.c"},
    )

    assert sorted(row["target_rel"] for row in rows) == [
        "paczka/SEM3/AKO_X/kolokwia/kol_02/2018/zadanie/main.c",
        "paczka/SEM3/AKO_X/kolokwia/kol_02/2019/zadanie/main.c",
    ]


def test_identical_source_directories_fall_back_to_the_content_hash() -> None:
    """Nigdy ciche pominięcie treści: gdy katalogi nie różnicują, wchodzi skrót sha256."""
    rows, _ = resolve_collisions(
        [decision(SHA_A), decision(SHA_B)],
        {SHA_A: "P/AKO/x/main.c", SHA_B: "P/AKO/x/main.c"},
    )

    targets = sorted(row["target_rel"] for row in rows)
    assert targets == [
        f"paczka/SEM3/AKO_X/kolokwia/kol_02/{SHA_A[:8]}/main.c",
        f"paczka/SEM3/AKO_X/kolokwia/kol_02/{SHA_B[:8]}/main.c",
    ]
    assert len(set(targets)) == 2


def test_the_same_content_twice_is_not_a_collision() -> None:
    rows, notes = resolve_collisions([decision(SHA_A), decision(SHA_A)], {SHA_A: "P/x/main.c"})

    assert notes == []
    assert {row["target_rel"] for row in rows} == {"paczka/SEM3/AKO_X/kolokwia/kol_02/main.c"}


def test_skipped_items_do_not_collide_with_anything() -> None:
    """`skip` nic nie tworzy w drzewie, więc jego ścieżka nie jest zajęta."""
    rows, notes = resolve_collisions(
        [decision(SHA_A, action="skip"), decision(SHA_B, action="skip")],
        {SHA_A: "P/x/main.c", SHA_B: "P/y/main.c"},
    )

    assert notes == []
    assert all(row["target_rel"].endswith("kol_02/main.c") for row in rows)


@pytest.mark.parametrize("raw, expected", [
    ('Zadanie "3"', "Zadanie _3_"),
    ("koniec. ", "koniec"),
    ("a/b", "a_b"),
    ("   ", "bez_nazwy"),
    ("Gotowiec 5 (2018)", "Gotowiec 5 (2018)"),
])
def test_source_directory_names_are_made_windows_safe(raw, expected) -> None:
    """Katalogi w źródłach bywają nie do odtworzenia na Windowsie (pomiar: 328 + 26)."""
    assert sanitize_segment(raw) == expected


def test_disambiguation_has_a_hard_limit() -> None:
    assert MAX_DISAMBIGUATION_LEVELS == 3


# -- relacje ----------------------------------------------------------------


def test_being_an_older_version_wins_over_a_near_duplicate() -> None:
    rows = attach_relations(
        [decision(SHA_A)],
        [
            {"source_sha256": SHA_A, "target_sha256": SHA_C,
             "relation_type": "near_duplicate", "confidence": 1.0},
            {"source_sha256": SHA_A, "target_sha256": SHA_B,
             "relation_type": "older_version", "confidence": 0.7},
        ],
    )

    assert rows[0]["relation"] == "older_version" and rows[0]["related_to"] == SHA_B


def test_older_version_is_recorded_only_on_the_older_side() -> None:
    """Kierunek znaczy: „B jest starszą wersją A” zapisane przy A czytałoby się odwrotnie.

    Nowsza treść zostaje więc bez `related_to`. Pełny obraz relacji (w obie strony)
    ma tabela `relations` i `relations.jsonl` — plan niesie jedno, jednoznaczne pole.
    """
    rows = attach_relations(
        [decision(SHA_A), decision(SHA_B)],
        [{"source_sha256": SHA_A, "target_sha256": SHA_B,
          "relation_type": "older_version", "confidence": 0.9}],
    )

    assert rows[0]["relation"] == "older_version" and rows[0]["related_to"] == SHA_B
    assert rows[1]["related_to"] is None


def test_a_symmetric_relation_is_visible_from_both_sides() -> None:
    rows = attach_relations(
        [decision(SHA_A), decision(SHA_B)],
        [{"source_sha256": SHA_A, "target_sha256": SHA_B,
          "relation_type": "near_duplicate", "confidence": 0.9}],
    )

    assert rows[0]["related_to"] == SHA_B and rows[1]["related_to"] == SHA_A


def test_an_existing_relation_in_the_plan_is_not_overwritten() -> None:
    rows = attach_relations(
        [decision(SHA_A, related_to=SHA_C, relation="related")],
        [{"source_sha256": SHA_A, "target_sha256": SHA_B,
          "relation_type": "near_duplicate", "confidence": 1.0}],
    )

    assert rows[0]["related_to"] == SHA_C


# -- odcisk planu -----------------------------------------------------------


def test_plan_hash_ignores_line_order() -> None:
    """Kolejność linii nie zmienia planu — inaczej `verify` nie mogłoby go rozpoznać."""
    assert plan_hash([decision(SHA_A), decision(SHA_B)]) == plan_hash(
        [decision(SHA_B), decision(SHA_A)]
    )


def test_plan_hash_changes_with_any_decision() -> None:
    base = plan_hash([decision(SHA_A)])

    assert plan_hash([decision(SHA_A, target_rel="paczka/inne/x.pdf")]) != base
    assert plan_hash([decision(SHA_A, action="skip")]) != base
    assert plan_hash([decision(SHA_A), decision(SHA_B)]) != base


# -- całość -----------------------------------------------------------------


def test_build_produces_a_header_and_then_the_decisions() -> None:
    result = build(
        deterministic=[decision(SHA_A), decision(SHA_B)],
        relations=[{"source_sha256": SHA_A, "target_sha256": SHA_B,
                    "relation_type": "older_version", "confidence": 0.8}],
        source_paths={SHA_A: "P/AKO/kol2/Zadanie 1/main.c", SHA_B: "P/AKO/kol2/Zadanie 2/main.c"},
        subject_key="AKO", semester=3, grupa="Wspolne", target_dir="paczka/SEM3/AKO_X",
        inputs={"plan.det.jsonl": 2}, created_at="2026-09-19T00:00:00Z",
    )

    lines = result.as_lines()
    assert META_KEY in lines[0] and all(META_KEY not in line for line in lines[1:])
    meta = lines[0][META_KEY]
    assert meta["items"] == 2 and meta["actions"] == {"copy": 2}
    # Relację `older_version` niesie tylko STARSZA strona — patrz test asymetrii niżej.
    assert meta["disambiguated"] == 2 and meta["with_relation"] == 1
    assert meta["plan_hash"] == plan_hash(result.rows)
    assert meta["inputs"] == {"plan.det.jsonl": 2}
