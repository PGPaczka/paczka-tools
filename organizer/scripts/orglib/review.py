"""B9: układanie materiału do przeglądu przez człowieka. Czysta funkcja.

Człowiek jest bramką **raz na przedmiot**, nie raz na plik (``AGENTS.md``, model
operacyjny). Ten moduł decyduje więc, co mu w ogóle pokazać i w jakiej kolejności —
tak, żeby decyzja „akceptuję ten plan” była podjęta na podstawie rzeczy, które
naprawdę wymagają oka, a nie 2,5 tysiąca linii JSON-a.

Kolejność sekcji wynika z tego, co blokuje:

1. ustalenia walidacji (B8) — bez nich `apply` i tak nie ruszy;
2. pozycje ``needs_review`` — reguły coś wybrały, ale nie na tyle pewnie, żeby wziąć
   za to odpowiedzialność;
3. ``unresolved`` — ani reguły, ani model nie wiedzą;
4. klastry near-dupe (B6) — „która wersja jest kanoniczna” to pytanie, na które nie
   odpowiada żadna heurystyka; tu potrzebny jest diff albo miniatura;
5. media wychodzące poza paczkę i podgląd drzewa.

Klastry budujemy przez sumowanie rozłącznych zbiorów (union-find): relacje są parami,
a człowiek myśli grupami — „te pięć skanów to jedno kolokwium”, nie „para A-B, para B-C”.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

#: Rodzaje treści, dla których sensowny jest diff tekstu, a nie miniatura.
TEXT_KINDS = frozenset({"pdf", "docx", "pptx", "xlsx", "text", "code"})


@dataclass
class Item:
    """Jedna treść w widoku review: decyzja planu + fakty z manifestu."""

    sha256: str
    action: str
    target_rel: str
    category: str
    confidence: float
    method: str
    reason: str
    needs_review: bool
    source_path: str = ""
    content_kind: str = ""
    size_bytes: int = 0
    related_to: str | None = None
    relation: str | None = None

    @property
    def filename(self) -> str:
        return PurePosixPath(self.source_path or self.target_rel).name


@dataclass
class Cluster:
    """Grupa treści powiązanych relacjami — jedna decyzja człowieka na grupę."""

    members: list[str]
    relations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def strength(self) -> float:
        """Najmocniejsza relacja w klastrze — po niej sortujemy, co pokazać najpierw."""
        return max((float(r.get("confidence") or 0.0) for r in self.relations), default=0.0)

    def has_older_version(self) -> bool:
        return any(r.get("relation_type") == "older_version" for r in self.relations)


@dataclass
class Review:
    """Komplet tego, co trafia na stronę przeglądu."""

    meta: dict[str, Any]
    items: dict[str, Item]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    needs_review: list[Item]
    unresolved: list[dict[str, Any]]
    clusters: list[Cluster]
    media: list[Item]
    tree: list[str]
    counts: dict[str, int]


def _root(parents: dict[str, str], value: str) -> str:
    while parents[value] != value:
        parents[value] = parents[parents[value]]
        value = parents[value]
    return value


def build_clusters(
    relations: Iterable[Mapping[str, Any]], *, known: set[str] | None = None
) -> list[Cluster]:
    """Łączy pary w grupy (union-find) i sortuje: najpierw duże i najpewniejsze.

    ``known`` zawęża do treści obecnych w planie — relacja do czegoś, czego w tym
    przedmiocie nie ma, nie pomaga w decyzji o tym przedmiocie.
    """
    parents: dict[str, str] = {}
    edges: list[dict[str, Any]] = []
    for relation in relations:
        source = str(relation.get("source_sha256") or "")
        target = str(relation.get("target_sha256") or "")
        if not source or not target:
            continue
        if known is not None and (source not in known or target not in known):
            continue
        for value in (source, target):
            parents.setdefault(value, value)
        parents[_root(parents, source)] = _root(parents, target)
        edges.append(dict(relation))

    groups: dict[str, list[str]] = {}
    for value in parents:
        groups.setdefault(_root(parents, value), []).append(value)
    clusters: list[Cluster] = []
    for root, members in groups.items():
        inside = set(members)
        clusters.append(Cluster(
            members=sorted(members),
            relations=[
                edge for edge in edges
                if str(edge.get("source_sha256")) in inside
                and str(edge.get("target_sha256")) in inside
            ],
        ))
    clusters.sort(key=lambda c: (-c.size, -c.strength, c.members[0]))
    return clusters


def build_review(
    *,
    plan: Sequence[Mapping[str, Any]],
    meta: Mapping[str, Any],
    manifest: Sequence[Mapping[str, Any]],
    validation: Sequence[Mapping[str, Any]] = (),
    unresolved: Sequence[Mapping[str, Any]] = (),
    relations: Sequence[Mapping[str, Any]] = (),
) -> Review:
    """Składa widok przeglądu z artefaktów etapów B1/B3/B6/B7/B8."""
    facts = {str(row.get("sha256")): row for row in manifest if row.get("sha256")}
    items: dict[str, Item] = {}
    for row in plan:
        sha = str(row.get("source_sha256") or "")
        if not sha:
            continue
        fact = facts.get(sha, {})
        items[sha] = Item(
            sha256=sha,
            action=str(row.get("action") or ""),
            target_rel=str(row.get("target_rel") or ""),
            category=str(row.get("category") or ""),
            confidence=float(row.get("confidence") or 0.0),
            method=str(row.get("method") or ""),
            reason=str(row.get("reason") or ""),
            needs_review=bool(row.get("needs_review")),
            source_path=str(fact.get("source_path") or ""),
            content_kind=str(fact.get("content_kind") or ""),
            size_bytes=int(fact.get("size_bytes") or 0),
            related_to=row.get("related_to"),
            relation=row.get("relation"),
        )

    errors = [dict(f) for f in validation if str(f.get("level")) == "error"]
    warnings = [dict(f) for f in validation if str(f.get("level")) == "warning"]
    # Najpierw najmniej pewne: to tam decyzja człowieka zmienia najwięcej.
    review_items = sorted(
        (item for item in items.values() if item.needs_review),
        key=lambda item: (item.confidence, item.target_rel),
    )
    media = sorted(
        (item for item in items.values() if item.action == "media"),
        key=lambda item: item.target_rel,
    )
    clusters = build_clusters(relations, known=set(items))
    tree = sorted({
        str(PurePosixPath(item.target_rel).parent)
        for item in items.values()
        if item.action in ("copy", "media")
    })
    counts = {
        "pozycje": len(items),
        "do_kopiowania": sum(1 for i in items.values() if i.action == "copy"),
        "pomijane": sum(1 for i in items.values() if i.action == "skip"),
        "media": len(media),
        "kwarantanna": sum(1 for i in items.values() if i.action == "quarantine"),
        "needs_review": len(review_items),
        "unresolved": len(unresolved),
        "klastry": len(clusters),
        "bledy": len(errors),
        "ostrzezenia": len(warnings),
    }
    return Review(
        meta=dict(meta),
        items=items,
        errors=errors,
        warnings=warnings,
        needs_review=review_items,
        unresolved=[dict(row) for row in unresolved],
        clusters=clusters,
        media=media,
        tree=tree,
        counts=counts,
    )


def pair_for_diff(cluster: Cluster, items: Mapping[str, Item]) -> tuple[Item, Item] | None:
    """Para do pokazania w diffie: przy `older_version` starsza kontra nowsza.

    Dla większego klastra pokazujemy JEDNĄ parę — reprezentanta relacji o najwyższej
    pewności. Reszta członków jest wypisana obok; pełny diff każdego z każdym to
    materiał na osobne narzędzie (TODO C4), nie na stronę do jednej decyzji.
    """
    ranked = sorted(
        cluster.relations,
        key=lambda r: (r.get("relation_type") != "older_version", -float(r.get("confidence") or 0.0)),
    )
    for relation in ranked:
        left = items.get(str(relation.get("source_sha256")))
        right = items.get(str(relation.get("target_sha256")))
        if left and right:
            return left, right
    return None


def is_text(item: Item) -> bool:
    return item.content_kind in TEXT_KINDS


def is_image(item: Item) -> bool:
    return item.content_kind == "image"
