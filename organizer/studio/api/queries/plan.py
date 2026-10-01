"""Konflikty planu — dwie treści celujące w jedną ścieżkę docelową.

Liczone z ŻYWEJ bazy, nie z pliku planu: inaczej naprawa nazwy byłaby widoczna
dopiero po ponownym zbudowaniu planu.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def plan_conflicts(
    conn: sqlite3.Connection,
    *,
    semester: int | None = None,
    skrot: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Dwie treści w jednej ścieżce docelowej — albo ścieżka zajęta przez paczkę.

    Bramka planu widzi to samo (`kolizja_celu`, `nadpisanie_ground_truth`), ale dopiero
    przy `validate` i tylko jako tekst. Liczymy z ŻYWEJ bazy, nie z pliku planu, żeby
    zmiana nazwy gasiła konflikt od razu — inaczej naprawa byłaby widoczna dopiero po
    ponownym zbudowaniu planu.

    Konflikty są rzadkie (`build_plan.resolve_collisions` rozstrzyga większość automatycznie),
    więc najpierw pytamy o SAME kolidujące ścieżki, a szczegóły treści dociągamy wyłącznie
    dla nich. Pełne łączenie z `files` dla wszystkich zaplanowanych pozycji trwało 5,5 s.
    """
    clauses = [
        "cl.action IN ('copy', 'media')",
        "cl.target_relative_path IS NOT NULL",
        "cl.target_relative_path <> ''",
    ]
    params: list[Any] = []
    if semester is not None:
        clauses.append("cl.semester = ?")
        params.append(semester)
    if skrot is not None:
        clauses.append("cl.subject_key = ?")
        params.append(skrot)
    where = " AND ".join(clauses)

    # Zwijanie wielkości liter robimy w Pythonie: `lower()` SQLite-a zna tylko ASCII,
    # a nazwy są polskie — Windows i macOS zwijają również „Ł". Zrobione przez funkcję
    # w SQLite kosztowało 1,9 s (miliony wywołań w złączeniu z `applied`); tu czytamy
    # dwie płaskie listy i resztę liczymy na słownikach.
    cele: dict[str, set[str]] = {}
    for row in conn.execute(
        f"SELECT cl.sha256 AS sha256, cl.target_relative_path AS cel "
        f"FROM classifications cl WHERE {where}",
        params,
    ):
        cele.setdefault(str(row["cel"]).lower(), set()).add(str(row["sha256"]))

    sporne = {klucz for klucz, shy in cele.items() if len(shy) > 1}
    zajete = {}
    for row in conn.execute("SELECT target_relative_path AS cel, sha256 FROM applied"):
        klucz = str(row["cel"]).lower()
        kandydaci = cele.get(klucz)
        if kandydaci and kandydaci != {str(row["sha256"])}:
            zajete[klucz] = str(row["sha256"])

    klucze = sorted(sporne | set(zajete))
    total = len(klucze)
    klucze = klucze[:limit]
    if not klucze:
        return {"total": total, "conflicts": []}

    # Szczegóły dociągamy po sha256 — mamy je już z pierwszego odczytu, a `sha256`
    # jest kluczem, więc zapytanie nie skanuje niczego dodatkowo.
    sporne_sha = sorted({sha for klucz in klucze for sha in cele[klucz]})
    miejsca = ",".join("?" * len(sporne_sha))
    wiersze = conn.execute(
        f"""
        SELECT cl.sha256 AS sha256,
               cl.target_relative_path AS target_relative_path,
               cl.category AS category,
               cl.confidence AS confidence,
               cl.classification_method AS classification_method,
               cl.needs_review AS needs_review,
               f.filename AS filename,
               f.source_relative_path AS source_relative_path,
               f.size_bytes AS size_bytes
        FROM classifications cl
        LEFT JOIN files f ON f.file_id = (SELECT MIN(file_id) FROM files WHERE sha256 = cl.sha256)
        WHERE cl.sha256 IN ({miejsca})
        ORDER BY cl.sha256
        """,
        sporne_sha,
    ).fetchall()

    grupy: dict[str, list[Any]] = {}
    for row in wiersze:
        grupy.setdefault(str(row["target_relative_path"]).lower(), []).append(row)

    conflicts: list[dict[str, Any]] = []
    for klucz in klucze:
        tresci = grupy.get(klucz, [])
        if not tresci:
            continue
        conflicts.append({
            # Materiał leżący już w paczce jest poważniejszą przeszkodą niż spór dwóch
            # kandydatów, więc gdy zachodzą oba, mówimy o tym pierwszym.
            "kind": "applied" if klucz in zajete else "plan",
            "path": str(tresci[0]["target_relative_path"]),
            "applied_sha256": zajete.get(klucz),
            "contents": [{
                "sha256": str(row["sha256"]),
                "filename": row["filename"],
                "source_relative_path": row["source_relative_path"],
                "size_bytes": row["size_bytes"],
                "confidence": row["confidence"],
                "classification_method": row["classification_method"],
                "category": row["category"],
                "needs_review": row["needs_review"],
            } for row in tresci],
        })

    return {"total": total, "conflicts": conflicts}
