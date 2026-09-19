"""B9: układ materiału do przeglądu. Czysta logika — bez HTML, plików i bazy."""

from __future__ import annotations

import pytest

from orglib.review import Item, build_clusters, build_review, is_image, is_text, pair_for_diff

SHA = {name: name * 64 for name in "abcde"}


def plan_row(sha, **overrides):
    row = {
        "source_sha256": sha, "action": "copy", "target_rel": f"paczka/X/kolokwia/{sha[:4]}.pdf",
        "category": "kolokwia", "confidence": 0.95, "method": "heuristic",
        "reason": "test", "needs_review": False, "related_to": None, "relation": None,
    }
    row.update(overrides)
    return row


def manifest_row(sha, **overrides):
    row = {"sha256": sha, "source_path": f"P/AKO/{sha[:4]}.pdf", "content_kind": "pdf",
           "size_bytes": 1024}
    row.update(overrides)
    return row


def relation(source, target, kind="near_duplicate", confidence=0.9):
    return {"source_sha256": source, "target_sha256": target,
            "relation_type": kind, "confidence": confidence}


# -- klastry ----------------------------------------------------------------


def test_chained_pairs_become_one_cluster() -> None:
    """Człowiek myśli grupami: „te trzy skany to jedno kolokwium”, nie parami A-B, B-C."""
    clusters = build_clusters([
        relation(SHA["a"], SHA["b"]), relation(SHA["b"], SHA["c"]),
        relation(SHA["d"], SHA["e"]),
    ])

    assert [cluster.members for cluster in clusters] == [
        sorted([SHA["a"], SHA["b"], SHA["c"]]), sorted([SHA["d"], SHA["e"]]),
    ]


def test_clusters_are_ordered_by_size_then_strength() -> None:
    clusters = build_clusters([
        relation(SHA["a"], SHA["b"], confidence=0.71),
        relation(SHA["b"], SHA["c"], confidence=0.72),
        relation(SHA["d"], SHA["e"], confidence=1.0),
    ])

    assert clusters[0].size == 3 and clusters[1].strength == 1.0


def test_relations_to_content_outside_this_subject_are_dropped() -> None:
    """Relacja do czegoś, czego w tym przedmiocie nie ma, nie pomaga w decyzji o nim."""
    clusters = build_clusters(
        [relation(SHA["a"], SHA["b"]), relation(SHA["a"], SHA["e"])],
        known={SHA["a"], SHA["b"]},
    )

    assert [cluster.members for cluster in clusters] == [sorted([SHA["a"], SHA["b"]])]


def test_broken_relation_rows_are_ignored() -> None:
    assert build_clusters([{"source_sha256": "", "target_sha256": SHA["a"]}, {}]) == []


# -- para do diffu ----------------------------------------------------------


def test_older_version_pair_wins_over_a_stronger_near_duplicate() -> None:
    """„Która wersja jest kanoniczna” to pytanie, po które człowiek tu przychodzi."""
    review = build_review(
        plan=[plan_row(SHA["a"]), plan_row(SHA["b"]), plan_row(SHA["c"])],
        meta={}, manifest=[manifest_row(s) for s in (SHA["a"], SHA["b"], SHA["c"])],
        relations=[
            relation(SHA["a"], SHA["b"], confidence=1.0),
            relation(SHA["a"], SHA["c"], "older_version", confidence=0.7),
        ],
    )

    pair = pair_for_diff(review.clusters[0], review.items)

    assert pair is not None
    assert {pair[0].sha256, pair[1].sha256} == {SHA["a"], SHA["c"]}


def test_pair_is_none_when_no_member_is_in_the_plan() -> None:
    review = build_review(plan=[], meta={}, manifest=[], relations=[])
    cluster = build_clusters([relation(SHA["a"], SHA["b"])])[0]

    assert pair_for_diff(cluster, review.items) is None


@pytest.mark.parametrize("kind, text, image", [
    ("pdf", True, False), ("text", True, False), ("code", True, False),
    ("image", False, True), ("archive", False, False), ("media", False, False),
])
def test_content_kind_decides_diff_or_thumbnail(kind, text, image) -> None:
    item = Item(sha256=SHA["a"], action="copy", target_rel="x", category="inne",
                confidence=1.0, method="heuristic", reason="", needs_review=False,
                content_kind=kind)

    assert is_text(item) is text and is_image(item) is image


# -- widok całości ----------------------------------------------------------


def test_review_counts_and_orders_what_matters_first() -> None:
    review = build_review(
        plan=[
            plan_row(SHA["a"], needs_review=True, confidence=0.86),
            plan_row(SHA["b"], needs_review=True, confidence=0.74),
            plan_row(SHA["c"], action="skip"),
            plan_row(SHA["d"], action="media", target_rel="90_MEDIA/AKO/x.mp3"),
        ],
        meta={"subject_key": "AKO"},
        manifest=[manifest_row(s) for s in SHA.values()],
        validation=[
            {"level": "error", "code": "kolizja_celu", "message": "x"},
            {"level": "warning", "code": "numer", "message": "y"},
        ],
        unresolved=[{"sha256": SHA["e"], "classify_reasons": ["brak_sygnalu_kategorii"]}],
    )

    assert review.counts == {
        "pozycje": 4, "do_kopiowania": 2, "pomijane": 1, "media": 1, "kwarantanna": 0,
        "needs_review": 2, "unresolved": 1, "klastry": 0, "bledy": 1, "ostrzezenia": 1,
    }
    # Najmniej pewne na górze — tam decyzja człowieka zmienia najwięcej.
    assert [item.confidence for item in review.needs_review] == [0.74, 0.86]
    assert [item.sha256 for item in review.media] == [SHA["d"]]


def test_review_joins_the_plan_with_facts_from_the_manifest() -> None:
    review = build_review(
        plan=[plan_row(SHA["a"])], meta={},
        manifest=[manifest_row(SHA["a"], source_path="P/AKO/Laby/lab1.pdf", size_bytes=4096)],
    )

    item = review.items[SHA["a"]]
    assert item.source_path == "P/AKO/Laby/lab1.pdf"
    assert item.size_bytes == 4096 and item.filename == "lab1.pdf"


def test_tree_lists_only_folders_that_will_exist() -> None:
    review = build_review(
        plan=[
            plan_row(SHA["a"], target_rel="paczka/X/kolokwia/a.pdf"),
            plan_row(SHA["b"], action="skip", target_rel="paczka/X/nigdy/b.pdf"),
        ],
        meta={}, manifest=[manifest_row(SHA["a"]), manifest_row(SHA["b"])],
    )

    assert review.tree == ["paczka/X/kolokwia"]
