"""B6: podobieństwo treści → relacje. Nigdy nie kasuje, nigdy nie oznacza `outdated`.

Moduł jest czystą funkcją: dostaje podpisy policzone w etapie extract (B2) i zwraca
listę relacji. Nie czyta materiałów, nie chodzi po filesystemie, nie dotyka bazy.

Trzy warstwy, w kolejności od najpewniejszej (``AGENTS.md``, reguły twarde 4-6):

1. **ten sam tekst po normalizacji** (``normalized_text_hash``) — to samo w innym
   opakowaniu: docx → pdf, re-eksport, inna nazwa. Pewność 1.0, bo to równość hasza,
   a nie ocena podobieństwa.
2. **simhash w progu Hamminga** — ten sam materiał z dopiskiem, poprawką, inną stroną
   tytułową. Przeżywa wstawki, których równość hasza nie przeżywa.
3. **phash w progu Hamminga** — obrazy: ten sam skan w innej rozdzielczości, zdjęcie
   tej samej kartki.

Progi są w ``config/thresholds.yaml: near_duplicate``. Dokładne duplikaty (równe
``sha256``) NIE są tu obsługiwane — to robi dedup po hashu (A4/A5), a jedna treść
ma w indeksie jeden wiersz, więc taka para nie ma prawa się tu pojawić.

Kierunek relacji:

- ``near_duplicate`` jest symetryczna, więc zapisujemy ją raz, w porządku
  leksykograficznym ``sha256`` — inaczej ta sama para wchodziłaby do bazy dwa razy
  w dwóch kierunkach;
- ``older_version`` jest skierowana: gdy obie treści mają rozpoznany rok i są to
  różne lata, starsza wskazuje na nowszą. To jedyna przesłanka, jakiej używamy —
  data pliku w źródłach opisuje moment skopiowania paczki, nie powstania materiału.

Czego ten etap NIE robi: nie oznacza niczego jako ``outdated`` (reguła twarda nr 10 —
to decyzja człowieka) i niczego nie usuwa (reguła nr 6). Relacja jest informacją dla
planu i review, nie wyrokiem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from orglib.textextract import hamming_distance

#: Prefiks ``relations.detection_method`` dla wszystkiego, co zapisał ten etap.
#: Pozwala nadpisać WYŁĄCZNIE własne wiersze i nie tknąć decyzji ręcznych (B14).
METHOD_PREFIX = "near_dupe"

#: Ile bitów ma podpis (simhash i phash z ``imagehash`` mają po 64).
_DEFAULT_BITS = 64


@dataclass(frozen=True)
class Signature:
    """Podpisy jednej treści — dokładnie to, co etap extract zapisał w indeksie."""

    sha256: str
    normalized_text_hash: str | None = None
    simhash: str | None = None
    perceptual_hash: str | None = None
    #: Rok materiału rozpoznany ze ścieżek (patrz ``orglib.classify.detect_year``).
    year: str | None = None


@dataclass(frozen=True)
class Relation:
    """Jedna relacja gotowa do zapisu w tabeli ``relations`` i do eksportu."""

    source_sha256: str
    target_sha256: str
    relation_type: str
    confidence: float
    detection_method: str
    reason: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_sha256, self.target_sha256, self.relation_type)

    def as_row(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "reason": self.reason,
        }


def bands(value: str, count: int, *, bits: int = _DEFAULT_BITS) -> tuple[int, ...]:
    """Dzieli podpis hex na ``count`` rozłącznych pasm bitowych.

    Zasada szufladkowa: jeśli dwa podpisy różnią się najwyżej ``count - 1`` bitami,
    to co najmniej jedno pasmo mają IDENTYCZNE. Dlatego kandydatów szukamy po
    równości pasm, a nie przez porównanie każdego z każdym — inaczej jeden przedmiot
    z kilkoma tysiącami treści to miliony porównań.
    """
    if count < 1:
        raise ValueError(f"liczba pasm musi być >= 1, jest {count}")
    number = int(value, 16)
    sizes = [bits // count + (1 if index < bits % count else 0) for index in range(count)]
    out: list[int] = []
    offset = 0
    for size in sizes:
        out.append((number >> offset) & ((1 << size) - 1))
        offset += size
    return tuple(out)


def _pairs_by_equality(
    signatures: Sequence[Signature], attribute: str
) -> list[tuple[Signature, Signature, int]]:
    """Pary o IDENTYCZNEJ wartości podpisu (odległość 0)."""
    buckets: dict[str, list[Signature]] = {}
    for signature in signatures:
        value = getattr(signature, attribute)
        if value:
            buckets.setdefault(value, []).append(signature)
    out: list[tuple[Signature, Signature, int]] = []
    for group in buckets.values():
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                out.append((left, right, 0))
    return out


def _pairs_by_distance(
    signatures: Sequence[Signature], attribute: str, limit: int, *, max_bucket: int
) -> tuple[list[tuple[Signature, Signature, int]], int]:
    """Pary w progu Hamminga, z kandydatami z pasm. Zwraca też liczbę pominiętych kubełków.

    ``max_bucket`` jest bezpiecznikiem, nie optymalizacją: gdy tysiące treści mają to
    samo pasmo (tak wygląda np. komplet niemal pustych tekstów), porównanie każdej
    z każdą w tym kubełku potrafi zająć godziny. Taki kubełek pomijamy i MÓWIMY o tym
    w podsumowaniu — ciche zgubienie relacji byłoby gorsze niż jawna luka.
    """
    if limit < 0:
        raise ValueError(f"próg Hamminga musi być >= 0, jest {limit}")
    usable = [s for s in signatures if getattr(s, attribute)]
    if limit == 0:
        return _pairs_by_equality(usable, attribute), 0
    count = limit + 1
    buckets: dict[tuple[int, int], list[Signature]] = {}
    for signature in usable:
        for index, band in enumerate(bands(str(getattr(signature, attribute)), count)):
            buckets.setdefault((index, band), []).append(signature)
    seen: set[tuple[str, str]] = set()
    out: list[tuple[Signature, Signature, int]] = []
    skipped = 0
    for group in buckets.values():
        if len(group) > max_bucket:
            skipped += 1
            continue
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                pair = tuple(sorted((left.sha256, right.sha256)))
                if pair in seen:
                    continue
                seen.add(pair)  # type: ignore[arg-type]
                distance = hamming_distance(
                    str(getattr(left, attribute)), str(getattr(right, attribute))
                )
                if distance <= limit:
                    out.append((left, right, distance))
    return out, skipped


def confidence_for(distance: int, limit: int) -> float:
    """Pewność relacji maleje liniowo z odległością: 1.0 przy zerze, ~0.5 na progu.

    Jedna reguła dla simhasha i phasha, żeby liczba w planie znaczyła to samo
    niezależnie od warstwy, która parę znalazła.
    """
    if limit <= 0:
        return 1.0
    return round(1.0 - distance / (2 * (limit + 1)), 4)


def _relation_for(
    left: Signature, right: Signature, distance: int, limit: int, method: str, detail: str
) -> Relation:
    """Składa relację z pary; rok rozstrzyga kierunek i rodzaj."""
    confidence = confidence_for(distance, limit)
    detection = f"{METHOD_PREFIX}:{method}"
    if left.year and right.year and left.year != right.year:
        older, newer = sorted((left, right), key=lambda s: str(s.year))
        return Relation(
            source_sha256=older.sha256,
            target_sha256=newer.sha256,
            relation_type="older_version",
            confidence=confidence,
            detection_method=detection,
            reason=f"{detail}; rok {older.year} vs {newer.year}",
        )
    first, second = sorted((left, right), key=lambda s: s.sha256)
    return Relation(
        source_sha256=first.sha256,
        target_sha256=second.sha256,
        relation_type="near_duplicate",
        confidence=confidence,
        detection_method=detection,
        reason=detail,
    )


def build_relations(
    signatures: Iterable[Signature],
    *,
    thresholds: Mapping[str, Any] | None = None,
    max_bucket: int = 1000,
) -> tuple[list[Relation], dict[str, int]]:
    """Wszystkie relacje dla podanego zbioru treści + liczniki do podsumowania.

    Gdy tę samą parę znajdzie kilka warstw, zostaje ta o wyższej pewności —
    równość tekstu jest mocniejszym argumentem niż bliski simhash tego samego tekstu.
    """
    thresholds = dict(thresholds or {})
    simhash_max = int(thresholds.get("simhash_hamming_max", 3))
    phash_max = int(thresholds.get("phash_hamming_max", 8))
    items = list(signatures)

    best: dict[tuple[str, str, str], Relation] = {}
    stats = {"normalized_text": 0, "simhash": 0, "phash": 0, "skipped_buckets": 0}

    def remember(relation: Relation, layer: str) -> None:
        current = best.get(relation.key)
        if current is None or relation.confidence > current.confidence:
            best[relation.key] = relation
        stats[layer] += 1

    for left, right, distance in _pairs_by_equality(items, "normalized_text_hash"):
        remember(
            _relation_for(left, right, distance, 0, "normalized_text", "ten sam tekst po normalizacji"),
            "normalized_text",
        )
    pairs, skipped = _pairs_by_distance(items, "simhash", simhash_max, max_bucket=max_bucket)
    stats["skipped_buckets"] += skipped
    for left, right, distance in pairs:
        remember(
            _relation_for(left, right, distance, simhash_max, "simhash", f"simhash, odległość {distance}"),
            "simhash",
        )
    pairs, skipped = _pairs_by_distance(items, "perceptual_hash", phash_max, max_bucket=max_bucket)
    stats["skipped_buckets"] += skipped
    for left, right, distance in pairs:
        remember(
            _relation_for(left, right, distance, phash_max, "phash", f"phash, odległość {distance}"),
            "phash",
        )

    relations = sorted(best.values(), key=lambda r: r.key)
    return relations, stats
