"""B7: scalenie decyzji w jeden plan. Czysta funkcja — bez bazy i bez filesystemu.

Wejście: linie planu deterministycznego (B3) i planu AI (B5), relacje (B6) oraz mapa
``sha256 -> ścieżka źródłowa`` z manifestu (B1). Wyjście: jeden plan z rozstrzygniętymi
kolizjami, dopiętymi relacjami i nagłówkiem ``_meta`` (w tym ``plan_hash``).

Trzy rzeczy, których nie da się zrobić na poziomie pojedynczej decyzji, więc są tutaj:

1. **Pierwszeństwo źródeł decyzji.** Ta sama treść może mieć decyzję z reguł i z modelu
   (np. po ponownym uruchomieniu z ``--ignore-det-plan``). Wygrywa metoda wyżej
   w :data:`METHOD_PRIORITY`: człowiek > deterministyka > heurystyka > model. Przegrana
   decyzja nie znika po cichu — wraca w ``conflicts`` do podsumowania.
2. **Kolizje ścieżek docelowych.** Klasyfikator zachowuje oryginalne nazwy plików, więc
   23 różne treści potrafią trafić w jedno ``kolokwia/kol_02/main.c``. Rozstrzygamy je
   **katalogiem źródłowym** (decyzja użytkownika 2026-09-19): nazwa pliku nic nie znaczy,
   znaczenie niesie katalog (``Zadanie 23/``, ``5.4/``), a przy okazji komplet plików
   jednego rozwiązania zostaje razem. Dokładamy kolejne poziomy w górę, dopóki grupa nie
   jest jednoznaczna; w ostateczności krótki skrót sha256 — nigdy ciche pominięcie treści.
3. **Relacje.** Plan ma jedno pole ``related_to``, więc wybieramy JEDNĄ relację: najpierw
   „ta treść jest starszą wersją czegoś” (to jest realna wskazówka dla review), potem
   najmocniejsze ``near_duplicate``. ``older_version`` jest skierowana, więc niesie ją
   wyłącznie STARSZA strona — zapisana przy nowszej czytałaby się odwrotnie. Nowsza
   treść zostaje bez relacji w planie; pełny obraz w obie strony ma tabela ``relations``
   i to z niej korzysta review (B9).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

#: Im niższa liczba, tym mocniejsze źródło decyzji.
METHOD_PRIORITY: dict[str, int] = {"manual": 0, "deterministic": 1, "heuristic": 2, "llm": 3}

#: Klucz linii nagłówkowej planu. Nie jest decyzją, więc nie podlega schematowi linii.
META_KEY = "_meta"

#: Ile poziomów katalogów źródłowych wolno dołożyć, zanim sięgniemy po skrót sha256.
MAX_DISAMBIGUATION_LEVELS = 3

#: Znaki, których nie wolno wstawić do nazwy katalogu (Windows) — patrz `orglib.plan_lint`.
_UNSAFE = re.compile(r'[<>:"|?*\x00-\x1f\\/]')


@dataclass
class BuildResult:
    """Plan gotowy do zapisu plus to, co trzeba pokazać człowiekowi."""

    rows: list[dict[str, Any]]
    meta: dict[str, Any]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    disambiguated: list[dict[str, Any]] = field(default_factory=list)

    def as_lines(self) -> list[dict[str, Any]]:
        return [{META_KEY: self.meta}, *self.rows]


def sanitize_segment(name: str) -> str:
    """Nazwa katalogu źródłowego przerobiona na segment, który powstanie na Windowsie.

    Katalogi w źródłach są mniej ucywilizowane niż nazwy plików (pomiar 2026-09-19:
    328 kończy się kropką albo spacją, 26 zawiera znak z ``<>:"|?*``), a my wstawiamy
    je do ścieżki docelowej — więc czyścimy je tutaj, zamiast pozwolić, żeby validator
    (B8) odrzucił cały plan.
    """
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(". ")
    return cleaned or "bez_nazwy"


def method_of(row: Mapping[str, Any]) -> str:
    return str(row.get("method") or "llm")


def merge_decisions(
    *sources: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Jedna decyzja na treść; przy dwóch wygrywa mocniejsza metoda. Zwraca (plan, konflikty)."""
    best: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for source in sources:
        for row in source:
            sha = str(row.get("source_sha256") or "")
            if not sha:
                raise ValueError(f"linia planu bez source_sha256: {row!r}")
            current = best.get(sha)
            if current is None:
                best[sha] = dict(row)
                continue
            new_rank = METHOD_PRIORITY.get(method_of(row), 99)
            old_rank = METHOD_PRIORITY.get(method_of(current), 99)
            winner, loser = (row, current) if new_rank < old_rank else (current, row)
            best[sha] = dict(winner)
            conflicts.append({
                "source_sha256": sha,
                "kept": method_of(winner),
                "dropped": method_of(loser),
                "kept_target": winner.get("target_rel"),
                "dropped_target": loser.get("target_rel"),
            })
    return [best[sha] for sha in sorted(best)], conflicts


def _source_segments(path: str | None) -> list[str]:
    """Katalogi ścieżki źródłowej od najbliższego plikowi (bez nazwy paczki)."""
    if not path:
        return []
    parts = list(PurePosixPath(path).parent.parts)
    return [sanitize_segment(part) for part in reversed(parts)]


def resolve_collisions(
    rows: Sequence[Mapping[str, Any]], source_paths: Mapping[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rozdziela treści, które trafiły w jedną ścieżkę. Zwraca (plan, opis rozstrzygnięć).

    Dokładamy poziom katalogu źródłowego POD katalogiem kategorii, a nie doklejamy do
    nazwy pliku: pliki jednego rozwiązania (``main.c`` + ``func.asm``) mają zostać razem,
    a limit długości ścieżki (240 znaków) jest już dziś w zasięgu.
    """
    out = [dict(row) for row in rows]
    by_target: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(out):
        if str(row.get("action")) in ("copy", "media"):
            by_target[str(row.get("target_rel"))].append(index)

    notes: list[dict[str, Any]] = []
    for target, indexes in sorted(by_target.items()):
        shas = {str(out[i].get("source_sha256")) for i in indexes}
        if len(shas) < 2:
            continue
        parent = str(PurePosixPath(target).parent)
        filename = PurePosixPath(target).name
        for level in range(1, MAX_DISAMBIGUATION_LEVELS + 1):
            proposals = {}
            for index in indexes:
                segments = _source_segments(source_paths.get(str(out[index].get("source_sha256"))))
                chosen = list(reversed(segments[:level])) or []
                proposals[index] = "/".join([parent, *chosen, filename])
            if len({(proposals[i], out[i].get("source_sha256")) for i in indexes}) == len(
                set(proposals.values())
            ):
                break
        else:  # ostatnia deska ratunku: skrót treści — brzydki, ale zawsze jednoznaczny
            proposals = {
                index: "/".join([parent, str(out[index].get("source_sha256"))[:8], filename])
                for index in indexes
            }
        for index in indexes:
            if proposals[index] != target:
                notes.append({
                    "source_sha256": out[index].get("source_sha256"),
                    "from": target,
                    "to": proposals[index],
                })
            out[index]["target_rel"] = proposals[index]
    return out, notes


def attach_relations(
    rows: Sequence[Mapping[str, Any]], relations: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Dopina JEDNĄ relację na treść: najpierw „jestem starszą wersją”, potem near-dupe."""
    best: dict[str, tuple[int, float, str, str]] = {}
    for relation in relations:
        source = str(relation.get("source_sha256") or "")
        target = str(relation.get("target_sha256") or "")
        kind = str(relation.get("relation_type") or "")
        try:
            confidence = float(relation.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        candidates = [(source, target)] if kind == "older_version" else [(source, target), (target, source)]
        for owner, other in candidates:
            rank = 0 if kind == "older_version" and owner == source else 1
            current = best.get(owner)
            if current is None or (rank, -confidence) < (current[0], -current[1]):
                best[owner] = (rank, confidence, other, kind)

    out: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        found = best.get(str(row.get("source_sha256")))
        if found and not row.get("related_to"):
            row["related_to"] = found[2]
            row["relation"] = found[3]
        out.append(row)
    return out


def plan_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    """Odcisk planu: sha256 po kanonicznej postaci decyzji, posortowanych po treści.

    Kolejność linii w pliku nie ma prawa zmienić odcisku — inaczej `apply`/`verify`
    nie mogłyby stwierdzić, że wykonują dokładnie ten plan, który zaakceptował człowiek.
    """
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: str(r.get("source_sha256"))):
        payload = {key: value for key, value in row.items() if key != META_KEY}
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build(
    *,
    deterministic: Iterable[Mapping[str, Any]],
    ai: Iterable[Mapping[str, Any]] = (),
    relations: Iterable[Mapping[str, Any]] = (),
    source_paths: Mapping[str, str],
    subject_key: str,
    semester: int,
    grupa: str,
    target_dir: str,
    inputs: Mapping[str, int],
    created_at: str,
) -> BuildResult:
    """Cały krok B7 jako jedno wywołanie; kolejność etapów jest tu istotna."""
    merged, conflicts = merge_decisions(deterministic, ai)
    resolved, notes = resolve_collisions(merged, source_paths)
    rows = attach_relations(resolved, relations)
    actions: dict[str, int] = defaultdict(int)
    for row in rows:
        actions[str(row.get("action"))] += 1
    meta = {
        "schema_version": 1,
        "subject_key": subject_key,
        "semester": semester,
        "grupa": grupa,
        "target_dir": target_dir,
        "created_at": created_at,
        "inputs": dict(inputs),
        "items": len(rows),
        "actions": dict(sorted(actions.items())),
        "needs_review": sum(1 for row in rows if row.get("needs_review")),
        "with_relation": sum(1 for row in rows if row.get("related_to")),
        "disambiguated": len(notes),
        "conflicts": len(conflicts),
        "plan_hash": plan_hash(rows),
    }
    return BuildResult(rows=rows, meta=meta, conflicts=conflicts, disambiguated=notes)
