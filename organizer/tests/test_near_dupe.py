"""B6: reguły relacji podobieństwa — kontrakt silnika i wiązanie ze schematem bazy.

Bez bazy, bez CLI, bez materiałów. Podpisy podajemy wprost, bo to etap extract (B2)
decyduje, jak powstają — tu sprawdzamy WYŁĄCZNIE wnioskowanie o relacjach.
"""

from __future__ import annotations

import re

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from orglib import config
from orglib.near_dupe import (
    METHOD_PREFIX,
    Relation,
    Signature,
    bands,
    build_relations,
    confidence_for,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
THRESHOLDS = {"simhash_hamming_max": 3, "phash_hamming_max": 8,
              "phash_text_hamming_max": 12, "simhash_related_max": 8,
              "phash_text_min_chars": 40}


def hexed(value: int) -> str:
    return f"{value:016x}"


def relate(*signatures: Signature, **kwargs):
    return build_relations(signatures, thresholds=THRESHOLDS, **kwargs)


# -- pasma (generowanie kandydatów) -----------------------------------------


@settings(max_examples=300, deadline=None)
@given(
    left=st.integers(min_value=0, max_value=2**64 - 1),
    flips=st.lists(st.integers(min_value=0, max_value=63), min_size=0, max_size=3, unique=True),
)
def test_bands_guarantee_a_shared_band_within_the_limit(left: int, flips: list[int]) -> None:
    """Zasada szufladkowa: przy odległości <= K i K+1 pasmach jedno pasmo MUSI być równe.

    Na tym stoi cały dobór kandydatów — gdyby własność nie zachodziła, etap po cichu
    gubiłby pary zamiast je znajdować, a testy na przykładach by tego nie pokazały.
    """
    right = left
    for bit in flips:
        right ^= 1 << bit

    assert any(a == b for a, b in zip(bands(hexed(left), 4), bands(hexed(right), 4)))


@given(value=st.integers(min_value=0, max_value=2**64 - 1), count=st.integers(1, 9))
def test_bands_are_a_lossless_split(value: int, count: int) -> None:
    """Pasma są rozłączne i pokrywają cały podpis — da się z nich odtworzyć wartość."""
    sizes = [64 // count + (1 if i < 64 % count else 0) for i in range(count)]
    restored = 0
    offset = 0
    for band, size in zip(bands(hexed(value), count), sizes):
        assert 0 <= band < (1 << size)
        restored |= band << offset
        offset += size

    assert restored == value and offset == 64


def test_bands_rejects_a_meaningless_count() -> None:
    with pytest.raises(ValueError, match="liczba pasm"):
        bands(hexed(1), 0)


# -- pewność ----------------------------------------------------------------


def test_confidence_falls_with_distance_and_stays_above_half_at_the_limit() -> None:
    assert confidence_for(0, 3) == 1.0
    assert confidence_for(3, 3) == 0.625
    assert confidence_for(8, 8) == pytest.approx(0.5556, abs=1e-4)
    assert [confidence_for(d, 8) for d in range(9)] == sorted(
        (confidence_for(d, 8) for d in range(9)), reverse=True
    )


# -- warstwy ----------------------------------------------------------------


def test_same_normalized_text_is_a_near_duplicate_with_full_confidence() -> None:
    relations, stats = relate(
        Signature(SHA_A, normalized_text_hash="t"),
        Signature(SHA_B, normalized_text_hash="t"),
    )

    assert [r.relation_type for r in relations] == ["near_duplicate"]
    assert relations[0].confidence == 1.0
    assert relations[0].detection_method == f"{METHOD_PREFIX}:normalized_text"
    assert stats["normalized_text"] == 1


def test_pair_is_stored_once_in_a_stable_direction() -> None:
    """Relacja symetryczna zapisana w obie strony dawałaby dwa wiersze o tym samym sensie."""
    forward, _ = relate(Signature(SHA_A, simhash=hexed(0)), Signature(SHA_B, simhash=hexed(1)))
    backward, _ = relate(Signature(SHA_B, simhash=hexed(1)), Signature(SHA_A, simhash=hexed(0)))

    assert [r.key for r in forward] == [r.key for r in backward]
    assert forward[0].source_sha256 < forward[0].target_sha256


@pytest.mark.parametrize("distance, found", [(0, True), (3, True), (4, False)])
def test_simhash_respects_the_threshold(distance: int, found: bool) -> None:
    other = sum(1 << bit for bit in range(distance))
    relations, _ = relate(Signature(SHA_A, simhash=hexed(0)), Signature(SHA_B, simhash=hexed(other)))

    assert bool(relations) is found


@pytest.mark.parametrize("distance, found", [(0, True), (8, True), (9, False)])
def test_phash_respects_its_own_threshold(distance: int, found: bool) -> None:
    other = sum(1 << bit for bit in range(distance))
    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0)),
        Signature(SHA_B, perceptual_hash=hexed(other)),
    )

    assert bool(relations) is found


# -- obrazy: piksele to za mało, gdy mamy tekst (Q5) -------------------------


def test_two_images_with_different_text_are_not_near_duplicates() -> None:
    """Dwie zapisane kartki wyglądają podobnie — o tym, czy to ten sam materiał,
    decyduje treść. Bez tego „prawie białe" skany zlewają się w jeden klaster.
    """
    daleki_tekst = sum(1 << bit for bit in range(20))

    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0), simhash=hexed(0)),
        Signature(SHA_B, perceptual_hash=hexed(1), simhash=hexed(daleki_tekst)),
    )

    assert relations == []


def test_two_images_with_matching_text_stay_near_duplicates() -> None:
    """Ten sam skan w innej rozdzielczości: piksele bliskie, OCR prawie ten sam."""
    szum_ocr = sum(1 << bit for bit in range(5))

    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0), simhash=hexed(0)),
        Signature(SHA_B, perceptual_hash=hexed(1), simhash=hexed(szum_ocr)),
    )

    assert [r.relation_type for r in relations] == ["near_duplicate"]


def test_a_scrap_of_ocr_text_cannot_veto_a_pixel_match() -> None:
    """Kilkanaście znaków z OCR to szum, nie treść.

    Zmierzone na tej paczce: w odrzuconych parach mediana krótszego tekstu to 205 znaków,
    ale 3% ma poniżej czterdziestu — i tam simhash mówi o przypadkowych literach,
    a nie o materiale. Taka para zostaje przy ocenie po pikselach.
    """
    daleki_tekst = sum(1 << bit for bit in range(20))

    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0), simhash=hexed(0), text_chars=500),
        Signature(SHA_B, perceptual_hash=hexed(1), simhash=hexed(daleki_tekst), text_chars=12),
    )

    assert [r.relation_type for r in relations] == ["near_duplicate"]


def test_long_texts_on_both_sides_still_veto() -> None:
    daleki_tekst = sum(1 << bit for bit in range(20))

    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0), simhash=hexed(0), text_chars=500),
        Signature(SHA_B, perceptual_hash=hexed(1), simhash=hexed(daleki_tekst), text_chars=400),
    )

    assert relations == []


def test_images_without_text_are_judged_by_pixels_alone() -> None:
    """Rysunek, wykres, zdjęcie bez liter — tekstu nie ma i nie będzie.

    Gdyby brak tekstu unieważniał parę, OCR pogorszyłby wynik dla wszystkiego,
    czego nie da się przeczytać.
    """
    relations, _ = relate(
        Signature(SHA_A, perceptual_hash=hexed(0)),
        Signature(SHA_B, perceptual_hash=hexed(1)),
    )

    assert [r.relation_type for r in relations] == ["near_duplicate"]


def test_text_confirmation_only_applies_to_the_pixel_layer() -> None:
    """Równość tekstu po normalizacji zostaje najmocniejszą przesłanką.

    Para znaleziona przez tekst nie może zniknąć dlatego, że piksele są różne.
    """
    relations, _ = relate(
        Signature(SHA_A, normalized_text_hash="x", perceptual_hash=hexed(0),
                  simhash=hexed(0)),
        Signature(SHA_B, normalized_text_hash="x", perceptual_hash=hexed(255),
                  simhash=hexed(sum(1 << bit for bit in range(30)))),
    )

    assert [r.confidence for r in relations] == [1.0]


def test_the_text_confirmation_threshold_is_configurable() -> None:
    odlegly = sum(1 << bit for bit in range(6))
    pary = [
        Signature(SHA_A, perceptual_hash=hexed(0), simhash=hexed(0)),
        Signature(SHA_B, perceptual_hash=hexed(1), simhash=hexed(odlegly)),
    ]

    luzny, _ = build_relations(pary, thresholds={**THRESHOLDS, "phash_text_hamming_max": 8})
    scisly, _ = build_relations(pary, thresholds={**THRESHOLDS, "phash_text_hamming_max": 4})

    assert luzny and not scisly


@pytest.mark.parametrize("empty", [None, ""])
def test_missing_signatures_never_pair_up(empty) -> None:
    """Brak tekstu to nie jest „ten sam tekst” — inaczej całe archiwum byłoby near-dupe.

    Pusty string sprawdzamy osobno od ``None``, bo kolumna w SQLite może trzymać obie
    wartości, a rozróżnienie „puste” kontra „brak” jest dokładnie tym, co odróżnia
    poprawny filtr od takiego, który zrasta wszystkie treści bez tekstu w jedną grupę.
    """
    relations, stats = relate(
        Signature(SHA_A, normalized_text_hash=empty, simhash=empty, perceptual_hash=empty),
        Signature(SHA_B, normalized_text_hash=empty, simhash=empty, perceptual_hash=empty),
        Signature(SHA_C, simhash=hexed(7)),
    )

    assert relations == []
    assert stats == {"normalized_text": 0, "simhash": 0, "phash": 0, "skipped_buckets": 0,
                     "phash_odrzucone_tekstem": 0, "katalog_potwierdzil": 0,
                     "katalog_related": 0}


# -- wspólny katalog jako sygnał kontekstu (Q6) -----------------------------


def test_a_shared_source_folder_strengthens_a_pair() -> None:
    """Katalog niesie decyzję człowieka sprzed lat: `kol1/`, `lab_05/`.

    Dwie treści, które ktoś kiedyś położył obok siebie, to mocniejsza przesłanka
    niż sama bliskość podpisu — i nic nie kosztuje, bo ścieżki już mamy.
    """
    osobno, _ = relate(
        Signature(SHA_A, simhash=hexed(0), folders=frozenset({"P/AKO/lab_05"})),
        Signature(SHA_B, simhash=hexed(1), folders=frozenset({"P/SO/inne"})),
    )
    razem, _ = relate(
        Signature(SHA_A, simhash=hexed(0), folders=frozenset({"P/AKO/lab_05"})),
        Signature(SHA_B, simhash=hexed(1), folders=frozenset({"P/AKO/lab_05"})),
    )

    assert razem[0].confidence > osobno[0].confidence
    assert "katalog" in razem[0].reason


def test_the_bonus_never_pushes_confidence_over_one() -> None:
    relations, _ = relate(
        Signature(SHA_A, normalized_text_hash="t", folders=frozenset({"P/AKO/kol1"})),
        Signature(SHA_B, normalized_text_hash="t", folders=frozenset({"P/AKO/kol1"})),
    )

    assert relations[0].confidence == 1.0


def test_a_near_miss_in_the_same_folder_becomes_related() -> None:
    """Podpis nie mieści się w progu near-dupe, ale pliki leżą w jednym katalogu.

    To jest „powiązane", a nie „duplikat" — i dokładnie tak trzeba to nazwać,
    bo od tej nazwy zależy, czy para trafi do rozstrzygania duplikatów.
    """
    tuz_za_progiem = sum(1 << bit for bit in range(5))

    relations, _ = relate(
        Signature(SHA_A, simhash=hexed(0), folders=frozenset({"P/AKO/lab_05"})),
        Signature(SHA_B, simhash=hexed(tuz_za_progiem), folders=frozenset({"P/AKO/lab_05"})),
    )

    assert [r.relation_type for r in relations] == ["related"]
    assert relations[0].confidence < 0.7


def test_a_near_miss_in_different_folders_is_nothing() -> None:
    """Sam podpis za progiem to za mało — inaczej próg near-dupe przestałby cokolwiek znaczyć."""
    tuz_za_progiem = sum(1 << bit for bit in range(5))

    relations, _ = relate(
        Signature(SHA_A, simhash=hexed(0), folders=frozenset({"P/AKO/lab_05"})),
        Signature(SHA_B, simhash=hexed(tuz_za_progiem), folders=frozenset({"P/SO/inne"})),
    )

    assert relations == []


def test_a_shared_folder_alone_relates_nothing() -> None:
    """Katalog bez żadnego podobieństwa treści to nie relacja.

    Inaczej każdy katalog z dwudziestoma plikami dawałby 190 par „powiązanych",
    czyli szum w miejscu, w którym zapadają decyzje o duplikatach. Grupowanie
    „to leży razem" robi poziom `group` w grafie (Q9), nie tabela relacji.
    """
    relations, _ = relate(
        Signature(SHA_A, folders=frozenset({"P/AKO/lab_05"})),
        Signature(SHA_B, folders=frozenset({"P/AKO/lab_05"})),
    )

    assert relations == []


def test_related_pairs_are_not_duplicates_to_resolve() -> None:
    """`related` nie może wejść do klastrów przeglądu — tam rozstrzyga się duplikaty."""
    from orglib.review import build_clusters

    klastry = build_clusters([
        {"source_sha256": SHA_A, "target_sha256": SHA_B, "relation_type": "related",
         "confidence": 0.4},
    ])

    assert klastry == []


# -- kierunek i rodzaj ------------------------------------------------------


def test_different_years_make_the_older_point_at_the_newer() -> None:
    relations, _ = relate(
        Signature(SHA_B, normalized_text_hash="t", year="2021"),
        Signature(SHA_A, normalized_text_hash="t", year="2019"),
    )

    assert relations[0].relation_type == "older_version"
    assert relations[0].source_sha256 == SHA_A      # 2019
    assert relations[0].target_sha256 == SHA_B      # 2021
    assert "2019 vs 2021" in relations[0].reason


@pytest.mark.parametrize("years", [("2020", "2020"), ("2020", None), (None, None)])
def test_without_two_different_years_it_stays_a_near_duplicate(years) -> None:
    left, right = years
    relations, _ = relate(
        Signature(SHA_A, normalized_text_hash="t", year=left),
        Signature(SHA_B, normalized_text_hash="t", year=right),
    )

    assert relations[0].relation_type == "near_duplicate"


def test_nothing_is_ever_marked_outdated() -> None:
    """Reguła twarda nr 10: `outdated` jest decyzją człowieka, nie wnioskiem z podobieństwa."""
    relations, _ = relate(
        Signature(SHA_A, normalized_text_hash="t", year="2015"),
        Signature(SHA_B, normalized_text_hash="t", year="2024"),
        Signature(SHA_C, normalized_text_hash="t", year="2019"),
    )

    assert relations, "test nic nie sprawdza, jeśli nie powstała żadna relacja"
    assert {r.relation_type for r in relations} <= {"near_duplicate", "older_version"}


def test_the_strongest_layer_wins_for_the_same_pair() -> None:
    """Ta sama para znaleziona dwa razy: równość tekstu bije bliski simhash."""
    relations, stats = relate(
        Signature(SHA_A, normalized_text_hash="t", simhash=hexed(0)),
        Signature(SHA_B, normalized_text_hash="t", simhash=hexed(0b111)),
    )

    assert len(relations) == 1
    assert relations[0].confidence == 1.0
    assert relations[0].detection_method == f"{METHOD_PREFIX}:normalized_text"
    assert stats["simhash"] == 1, "warstwa simhash też trafiła — licznik ma to pokazać"


def test_oversized_bucket_is_skipped_and_reported() -> None:
    """Bezpiecznik ma być WIDOCZNY: pominięcie kubełka nie może być ciche."""
    signatures = [Signature(f"{index:064x}", simhash=hexed(index)) for index in range(20)]

    relations, stats = build_relations(signatures, thresholds=THRESHOLDS, max_bucket=3)

    assert stats["skipped_buckets"] > 0
    assert len(relations) < 20


# -- wiązanie z repo --------------------------------------------------------


def test_relation_types_are_the_ones_the_schema_accepts() -> None:
    """`relations.relation_type` ma CHECK w schemacie — kod nie może produkować innych.

    Czytamy schemat wprost, bo rozjazd tych dwóch list objawiłby się dopiero przy
    zapisie do prawdziwej bazy, na realnym przebiegu.
    """
    schema = (config.ORGANIZER_ROOT / "scripts" / "orglib" / "schema.sql").read_text("utf-8")
    match = re.search(r"relation_type\s+TEXT NOT NULL CHECK \(relation_type IN \(([^)]+)\)\)", schema)
    assert match, "nie znaleziono CHECK dla relation_type w schema.sql"
    allowed = set(re.findall(r"'([a-z_]+)'", match.group(1)))

    produced = set()
    for years in (("2019", "2021"), (None, None)):
        relations, _ = relate(
            Signature(SHA_A, normalized_text_hash="t", year=years[0]),
            Signature(SHA_B, normalized_text_hash="t", year=years[1]),
        )
        produced |= {r.relation_type for r in relations}

    assert produced <= allowed and produced == {"near_duplicate", "older_version"}


def test_real_thresholds_have_the_keys_this_stage_reads() -> None:
    data = yaml.safe_load(
        (config.ORGANIZER_ROOT / "config" / "thresholds.yaml").read_text(encoding="utf-8")
    )["near_duplicate"]

    assert isinstance(data["simhash_hamming_max"], int) and data["simhash_hamming_max"] >= 0
    assert isinstance(data["phash_hamming_max"], int) and data["phash_hamming_max"] >= 0
    # Obrazy znoszą większą odległość niż tekst — inaczej próg phasha nic nie wnosi.
    assert data["phash_hamming_max"] > data["simhash_hamming_max"]
    # Potwierdzenie tekstem (Q5) jest LUŹNIEJSZE niż próg near-dupe dla samego tekstu:
    # OCR dwóch zdjęć tej samej kartki nigdy nie wychodzi identycznie.
    assert data["phash_text_hamming_max"] > data["simhash_hamming_max"]
    # Near-miss w jednym katalogu (Q6) musi być LUŹNIEJSZY niż sam próg near-dupe,
    # inaczej ta warstwa nigdy by się nie odezwała.
    assert data["simhash_related_max"] > data["simhash_hamming_max"]
    assert isinstance(data["phash_text_min_chars"], int) and data["phash_text_min_chars"] > 0


def test_row_shape_matches_the_relations_table() -> None:
    row = Relation(SHA_A, SHA_B, "near_duplicate", 0.9, "x", "y").as_row()

    assert set(row) == {
        "source_sha256", "target_sha256", "relation_type",
        "confidence", "detection_method", "reason",
    }
