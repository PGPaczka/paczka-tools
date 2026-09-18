"""Deterministyczny wycinek indeksu: kandydaci, nie decyzje klasyfikacyjne.

Nie otwiera materiałów i nie modyfikuje bazy. Dopasowanie jest po pełnych
tokenach (skrót, alias, nazwa), bez fuzzy. Niejednoznaczność zostaje w review.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Sequence

from orglib import config, db

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SEMESTER = re.compile(
    r"\b(?:sem|semestr|semester)\s*(\d+|vii|vi|iv|iii|ii|v|i)\b"
)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}
_HEALTHY = frozenset(db.FILE_STATUSES[1:])


def _tokens(value: str) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return tuple(re.findall(r"[a-z0-9]+", value))


def _identity(subject: config.Subject) -> tuple[int, str, str]:
    return subject.semester, subject.skrot, subject.grupa


def _safe_path(package: str, relative: str) -> str:
    """Nie pozwala przekazać przyszłej ekstrakcji ścieżki wychodzącej ze źródeł."""
    for value in (package, relative):
        if (
            not value
            or "\\" in value
            or "\0" in value
            or PurePosixPath(value).is_absolute()
            or any(p in ("", ".", "..") for p in value.split("/"))
        ):
            raise ValueError(f"niebezpieczna ścieżka w indeksie: {value!r}")
    if "/" in package:
        raise ValueError(f"niepoprawna nazwa paczki: {package!r}")
    return f"{package}/{relative}"


class _Matcher:
    def __init__(self, subjects: Sequence[config.Subject]):
        self.labels: dict[tuple[str, ...], list[tuple[config.Subject, int]]] = defaultdict(list)
        self.groups: dict[tuple[str, ...], set[tuple[int, str]]] = defaultdict(set)
        for s in subjects:
            for label, score in [
                (_tokens(s.nazwa), 3),
                (_tokens(s.skrot), 2),
                *((_tokens(alias), 1) for alias in s.aliases),
            ]:
                if label:
                    self.labels[label].append((s, score))
            if s.semester >= 5:
                self.groups[_tokens(s.grupa)].add((s.semester, s.grupa))
                if s.katedra:
                    self.groups[_tokens(s.katedra)].add((s.semester, s.grupa))
        self.lengths = sorted({len(label) for label in self.labels})

    def match(self, path: str) -> tuple[set[tuple[int, str, str]], set[str]]:
        parts = path.split("/")
        parts[-1] = PurePosixPath(parts[-1]).stem
        components = [_tokens(p) for p in parts]
        # Magisterskie nie są jeszcze ujęte w katalogu (TODO D3).
        if any("magisterskie" in c for c in components):
            return set(), set()
        semesters = set()
        for component in components:
            for match in _SEMESTER.finditer(" ".join(component)):
                value = match.group(1)
                semesters.add(int(value) if value.isdigit() else _ROMAN[value])
        reasons: set[str] = set()
        if not semesters:
            reasons.add("missing_semester")
        elif len(semesters) > 1:
            reasons.add("conflicting_semesters")
        found: set[tuple[int, str, str]] = set()
        groups: dict[int, set[str]] = defaultdict(set)
        for component in components:
            scored: list[tuple[config.Subject, int]] = []
            for length in self.lengths:
                for start in range(len(component) - length + 1):
                    for subject, score in self.labels.get(component[start:start + length], ()):
                        if semesters and subject.semester not in semesters:
                            continue
                        subject_groups = groups[subject.semester]
                        if subject_groups and subject.grupa not in subject_groups:
                            continue
                        if len(subject_groups) > 1:
                            reasons.add("conflicting_groups")
                        scored.append((subject, score))
            # Skrót wygrywa z aliasem tylko W TYM SAMYM semestrze.
            # Bez semestru JAI może oznaczać również JAII/JAIII/JAIV.
            for semester in {s.semester for s, _ in scored}:
                best = max(score for s, score in scored if s.semester == semester)
                found.update(
                    _identity(s) for s, score in scored
                    if s.semester == semester and score == best
                )
            # Grupa ma znaczenie przed komponentem przedmiotu, nie np.
            # w laboratoria/wspólne pod nim.
            for semester, group in self.groups.get(component, ()):
                groups[semester].add(group)
        if len(found) > 1:
            reasons.add("ambiguous_subject")
        return found, reasons


def build_manifest(
    conn: sqlite3.Connection,
    subject: config.Subject,
    subjects: Sequence[config.Subject] | None = None,
) -> list[dict[str, Any]]:
    """Jedna pozycja na SHA-256, pełne provenance i zdrowy reprezentant unique.

    Foldery ``duplicate_of`` są wyłącznie provenance, także przez przodka.
    Jeśli dopasowanie jest tylko w duplikacie, można wybrać zdrową kopię tej
    samej treści poza nim. Brak takiej kopii blokuje ekstrakcję (null + review).
    """
    matcher = _Matcher(list(subjects) if subjects is not None else config.iter_subjects())
    identity = _identity(subject)
    duplicate_folders = {
        str(row["folder_path"])
        for row in conn.execute("SELECT folder_path FROM folders WHERE duplicate_of IS NOT NULL")
    }
    contents = {
        str(row["sha256"]): dict(row)
        for row in conn.execute("SELECT sha256, content_kind FROM content")
    }
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        "SELECT source_package, source_relative_path, size_bytes, sha256, status "
        "FROM files WHERE sha256 IS NOT NULL ORDER BY source_package, source_relative_path"
    ):
        sha = str(row["sha256"])
        if not _SHA.fullmatch(sha) or sha not in contents:
            continue
        item = dict(row)
        path = _safe_path(str(row["source_package"]), str(row["source_relative_path"]))
        item["path"] = path
        item["duplicate"] = any(
            str(parent) in duplicate_folders for parent in PurePosixPath(path).parents
        )
        item["matches"], item["reasons"] = matcher.match(path)
        by_sha[sha].append(item)

    result = []
    for sha, copies in sorted(by_sha.items()):
        healthy = [c for c in copies if c["status"] in _HEALTHY]
        matched = [c for c in healthy if identity in c["matches"]]
        if not matched:
            continue
        reasons = set().union(*(c["reasons"] for c in matched))
        evidence = set().union(*(c["matches"] for c in healthy))
        if evidence - {identity}:
            reasons.add("conflicting_source_subjects")
        sizes = {c["size_bytes"] for c in healthy}
        if len(sizes) != 1:
            reasons.add("inconsistent_sizes")
        unique = [c for c in healthy if not c["duplicate"]]
        # Preferuj dopasowaną ścieżkę, następnie porządek leksykograficzny.
        unique.sort(key=lambda c: (identity not in c["matches"], c["path"]))
        representative = unique[0]["path"] if unique else None
        if representative is None:
            reasons.add("no_unique_source")
        result.append({
            "schema_version": 1,
            "sha256": sha,
            "source_sha256": sha,
            "semester": subject.semester,
            "subject_key": subject.skrot,
            "grupa": subject.grupa,
            "target_dir": subject.target_dir,
            "source_paths": sorted(c["path"] for c in copies),
            "matched_source_paths": sorted(c["path"] for c in matched),
            "source_path": representative,
            "content_kind": contents[sha]["content_kind"],
            "size_bytes": unique[0]["size_bytes"] if unique else min(sizes),
            "needs_review": bool(reasons),
            "review_reasons": sorted(reasons),
        })
    return result
