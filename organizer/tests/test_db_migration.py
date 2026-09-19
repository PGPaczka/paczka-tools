"""Migracja schematu 1 → 2 na bazie, której NIE WOLNO odtworzyć od zera.

Operacyjny indeks trzyma stan 48 tys. plików; odtworzenie go to ponowne zahashowanie
kilkudziesięciu GB źródeł. Dlatego migracja musi: zachować dane, dać dokładnie ten sam
kształt co świeża baza i nie zostawić bazy w połowie drogi, gdy coś padnie.

Wersja 1 schematu leży w `tests/fixtures/schema_v1.sql` — to snapshot pliku sprzed
migracji, żeby test nie zależał od historii gita.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from orglib import db

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v1.sql"


def _canonical(sql: str) -> str:
    """Definicja tabeli bez znaczenia białych znaków."""
    collapsed = re.sub(r"\s+", " ", sql)
    return collapsed.replace(" ,", ",").replace("( ", "(").replace(" )", ")")
SHA = "a" * 64


def shape(path: Path) -> dict[str, list[tuple]]:
    """Kształt bazy: kolumny każdej tabeli i nazwy indeksów. To porównujemy."""
    conn = sqlite3.connect(path)
    try:
        tables = sorted(
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        out: dict[str, list[tuple]] = {}
        for table in tables:
            out[table] = [
                (row[1], row[2], row[3], row[4], row[5])       # nazwa, typ, NOT NULL, default, PK
                for row in conn.execute(f"PRAGMA table_info({table})")
            ]
        out["__indexes__"] = sorted(
            (row[0],) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
        )
        # Porównujemy TREŚĆ definicji, nie jej formatowanie: `ALTER TABLE ADD COLUMN`
        # dokleja kolumnę do oryginalnego tekstu, więc różnice w spacjach są nieuniknione
        # i nic nie znaczą — w przeciwieństwie do brakującego CHECK-a, który znaczy wszystko.
        out["__checks__"] = sorted(
            (row[0], _canonical(str(row[1])))
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        return out
    finally:
        conn.close()


@pytest.fixture
def legacy(tmp_path) -> Path:
    """Baza w wersji 1 z danymi w tabelach, których dotyka migracja."""
    path = tmp_path / "stara.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE.read_text(encoding="utf-8"))
    with conn:
        conn.execute("INSERT INTO schema_version VALUES (1, '2026-09-17T00:00:00Z')")
        conn.execute("INSERT INTO content (sha256, content_kind) VALUES (?, 'pdf')", (SHA,))
        conn.execute(
            "INSERT INTO classifications (sha256, semester, subject_key, category, "
            "target_relative_path, classification_method, confidence, run_id, decided_at) "
            "VALUES (?, 3, 'AKO', 'kolokwia', 'paczka/SEM3/AKO_X/kolokwia/a.pdf', 'manual', 1.0, "
            "'ground_truth', '2026-09-17T00:00:00Z')",
            (SHA,),
        )
        conn.execute(
            "INSERT INTO plan_items (sha256, target_relative_path, action, status, plan_run_id) "
            "VALUES (?, 'paczka/SEM3/AKO_X/kolokwia/a.pdf', 'copy', 'validated', 'run-1')",
            (SHA,),
        )
    conn.close()
    return path


def test_fixture_really_is_the_older_schema(legacy: Path) -> None:
    """Gdyby snapshot został podmieniony na nowy, cała reszta pliku nic by nie sprawdzała."""
    conn = sqlite3.connect(legacy)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(classifications)")}
        plan_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'plan_items'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert "action" not in columns and "needs_review" not in columns
    assert "'media'" not in plan_sql


def test_migration_keeps_the_data(legacy: Path) -> None:
    conn = db.connect(legacy)
    try:
        assert db.current_schema_version(conn) == db.SCHEMA_VERSION
        classification = conn.execute("SELECT * FROM classifications").fetchone()
        plan_item = conn.execute("SELECT * FROM plan_items").fetchone()
    finally:
        conn.close()

    # Ground truth przeżywa migrację w komplecie — to jedyny zapis o tym, co leży w paczce.
    assert classification["run_id"] == "ground_truth"
    assert classification["target_relative_path"] == "paczka/SEM3/AKO_X/kolokwia/a.pdf"
    assert classification["confidence"] == 1.0
    # Nowe kolumny mają sensowne wartości domyślne, a nie NULL tam, gdzie NOT NULL.
    assert classification["action"] is None and classification["needs_review"] == 0
    assert plan_item["status"] == "validated" and plan_item["plan_run_id"] == "run-1"


def test_migrated_database_has_exactly_the_shape_of_a_fresh_one(legacy: Path, tmp_path) -> None:
    """Najważniejszy test tego pliku: migracja nie może rozjechać się ze `schema.sql`.

    Klasyczna wpadka migracji polega na tym, że nowa baza i baza zmigrowana zaczynają
    się różnić (brakujący indeks, inny CHECK) — i wychodzi to dopiero na produkcji.
    """
    conn = db.connect(legacy)
    conn.close()
    fresh = tmp_path / "swieza.sqlite"
    conn = db.connect(fresh)
    conn.close()

    assert shape(legacy) == shape(fresh)


def test_migrated_plan_items_accept_the_media_action(legacy: Path) -> None:
    """Sedno migracji `plan_items`: CHECK nie znał akcji, którą plan wystawia."""
    conn = db.connect(legacy)
    try:
        db.upsert_plan_item(conn, {
            "sha256": SHA, "target_relative_path": "90_MEDIA/AKO/nagranie.mp3",
            "action": "media", "status": "planned", "plan_run_id": "run-2",
        })
        actions = {row[0] for row in conn.execute("SELECT action FROM plan_items")}
    finally:
        conn.close()

    assert actions == {"copy", "media"}


def test_statement_splitter_matches_executescript(tmp_path) -> None:
    """Własny podział DDL na polecenia musi dawać to samo, co `executescript`.

    `executescript` odpadł, bo commituje otwartą transakcję (a migracja musi być
    atomowa), ale to on jest wzorcem poprawności — gdyby w schemacie pojawił się
    kiedyś TRIGGER ze średnikami w środku, naiwny podział by go rozciął i ten test
    zrobi się czerwony.
    """
    reference = tmp_path / "wzorzec.sqlite"
    conn = sqlite3.connect(reference)
    conn.executescript((Path(db.__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    conn.close()
    ours = tmp_path / "nasza.sqlite"
    conn = db.connect(ours)
    conn.close()

    reference_shape = shape(reference)
    our_shape = shape(ours)
    del our_shape["schema_version"], reference_shape["schema_version"]
    assert our_shape["__checks__"] == reference_shape["__checks__"]
    assert our_shape["__indexes__"] == reference_shape["__indexes__"]


def test_migration_is_idempotent(legacy: Path) -> None:
    for _ in range(3):
        conn = db.connect(legacy)
        conn.close()

    conn = sqlite3.connect(legacy)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0]
        leftovers = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'plan_items_v%'"
            )
        ]
    finally:
        conn.close()

    assert rows == 1 and leftovers == []


def test_failed_migration_leaves_the_database_on_the_old_version(legacy: Path, monkeypatch) -> None:
    """Przerwana migracja ma się wycofać w całości — nie zostawić połowy."""
    broken = dict(db._MIGRATIONS)
    broken[db.SCHEMA_VERSION] = {
        **broken[db.SCHEMA_VERSION],
        "after": (*broken[db.SCHEMA_VERSION]["after"], "INSERT INTO nie_ma_takiej_tabeli VALUES (1)"),
    }
    monkeypatch.setattr(db, "_MIGRATIONS", broken)

    with pytest.raises(sqlite3.DatabaseError):
        db.connect(legacy)

    conn = sqlite3.connect(legacy)
    conn.row_factory = sqlite3.Row
    try:
        assert db.current_schema_version(conn) == 1
        columns = {row[1] for row in conn.execute("PRAGMA table_info(classifications)")}
        assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 1
    finally:
        conn.close()

    assert "action" not in columns
