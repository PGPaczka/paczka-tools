"""S0: API studia czyta indeks — i mówi dokładnie to, co `just status`.

Dwie rzeczy są tu naprawdę sprawdzane. Pierwsza: liczby z endpointów muszą zgadzać
się z `scripts/status_report.py`, bo to jedyna gwarancja, że widok nie zacznie
liczyć po swojemu (``studio/AGENTS.md``, reguła 1). Druga: w fazie S0 nie istnieje
ŻADEN endpoint zapisu — ta kontrola jest tu po to, żeby pierwszy POST musiał
świadomie przejść przez ten test, a nie wślizgnąć się przy okazji.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

import status_report
from orglib import config, db
from studio.api import database, queries
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdef"}

THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}


def _subject(semester: int, skrot: str, nazwa: str, **kwargs) -> config.Subject:
    return config.Subject(
        semester=semester, skrot=skrot, nazwa=nazwa,
        forms=kwargs.get("forms", ("W", "C")), aliases=kwargs.get("aliases", ()),
        instancja=None, strumien=kwargs.get("strumien"), profil=kwargs.get("profil"),
        katedra=kwargs.get("katedra"),
    )


SUBJECTS = [
    _subject(3, "AKO", "Architektura_Komputerów", aliases=("AK",)),
    _subject(3, "SOI", "Systemy_Operacyjne"),
    _subject(5, "SI", "Serwisy_Internetowe", strumien="Aplikacje"),
    _subject(5, "SI", "Sieci_IP", strumien="Sieci"),
]


@pytest.fixture
def index(tmp_path):
    """Mały, ale kompletny indeks: ground truth + plan + relacja + kopie treści."""
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for index_, sha in enumerate(SHA.values()):
        db.upsert_content(conn, {
            "sha256": sha, "content_kind": "pdf",
            "extracted_text_path": f"text/{sha[:4]}.txt" if index_ % 2 == 0 else None,
        })
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/p{index_}.pdf",
            "folder_path": "P/SEM3", "filename": f"p{index_}.pdf", "extension": ".pdf",
            "size_bytes": 100 + index_, "sha256": sha, "status": "extracted",
        })
    # Ta sama treść zmaterializowana drugi raz — lista pokazuje treści, nie kopie.
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/kopia/p0.pdf",
        "folder_path": "P/SEM3", "filename": "p0.pdf", "extension": ".pdf",
        "size_bytes": 100, "sha256": SHA["a"], "status": "extracted",
    })
    db.upsert_classification(conn, {
        "sha256": SHA["a"], "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "target_relative_path": "paczka/SEM3/AKO_X/egzamin/a.pdf", "is_outdated": 0,
        "classification_method": "manual", "confidence": 1.0, "run_id": "ground_truth",
        "decided_at": "2026-09-17T00:00:00Z", "action": "copy", "needs_review": 0,
    })
    plan = (
        (SHA["b"], "wyklad", "copy", 0.95, 0, "deterministic"),
        (SHA["c"], "kolokwia", "copy", 0.74, 1, "heuristic"),
        (SHA["d"], "inne", "skip", 0.60, 1, "ai"),
        (SHA["e"], "wyklad", "media", 0.99, 0, "deterministic"),
    )
    for sha, category, action, confidence, review, method in plan:
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": category,
            "target_relative_path": f"paczka/SEM3/AKO_X/{category}/{sha[:4]}.pdf",
            "is_outdated": 0, "classification_method": method, "confidence": confidence,
            "run_id": "plan:abc123", "decided_at": "2026-09-19T00:00:00Z",
            "action": action, "reason": f"bo {category}", "needs_review": review,
        })
    db.upsert_relation(conn, {
        "source_sha256": SHA["b"], "target_sha256": SHA["c"],
        "relation_type": "near_duplicate", "confidence": 0.91, "detection_method": "simhash",
    })
    db.upsert_plan_item(conn, {
        "sha256": SHA["b"], "target_relative_path": "paczka/SEM3/AKO_X/wyklad/bbbb.pdf",
        "action": "copy", "status": "planned", "plan_run_id": "plan:abc123",
    })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as test_client:
        yield test_client


def collect_reference(index) -> dict:
    """Liczby policzone WPROST przez `status_report` — punkt odniesienia kontraktu."""
    conn = sqlite3.connect(index)
    conn.row_factory = sqlite3.Row
    try:
        return status_report.collect(conn)
    finally:
        conn.close()


def test_health_reports_the_database_it_reads(client, index) -> None:
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["schema_version"] == db.SCHEMA_VERSION
    assert body["read_only"] is True
    assert body["db"] == str(index)


def test_dashboard_totals_match_status_report(client, index) -> None:
    """Gdyby te liczby się rozjechały, nie dałoby się powiedzieć, która jest prawdziwa."""
    reference = collect_reference(index)
    totals = client.get("/api/subjects").json()["totals"]

    for key in ("packages", "folders", "files", "contents", "with_text", "relations",
                "plan_items", "applied", "duplicate_folders"):
        assert totals[key] == reference[key], key
    assert totals["files_by_status"] == reference["files_by_status"]


def test_subject_row_matches_the_status_table(client, index) -> None:
    reference = collect_reference(index)
    entry = reference["per_subject"][(3, "AKO")]
    row = next(s for s in client.get("/api/subjects").json()["subjects"] if s["skrot"] == "AKO")

    assert row["ground_truth"] == entry["ground_truth"] == 1
    assert row["planned"] == entry["planned"] == 4
    assert row["needs_review"] == entry["needs_review"] == 2
    assert row["actions"] == dict(entry["actions"]) == {"copy": 2, "skip": 1, "media": 1}
    assert row["stage"] == status_report.stage_of(dict(entry)) == "plan do przeglądu"
    assert row["target_dir"] == "paczka/SEM3/AKO_Architektura_Komputerów"


def test_queue_uses_the_same_stage_order_as_status_md(client) -> None:
    queue = client.get("/api/subjects").json()["queue"]

    assert [stage["stage"] for stage in queue] == list(status_report.STAGE_ORDER)
    assert sum(stage["count"] for stage in queue) == len(SUBJECTS)
    untouched = next(s for s in queue if s["stage"] == "nietknięty")
    assert {s["skrot"] for s in untouched["subjects"]} == {"SOI", "SI"}


def test_subject_detail_breaks_the_plan_into_what_needs_an_eye(client) -> None:
    body = client.get("/api/subjects/3/AKO").json()

    assert body["subject"]["nazwa"] == "Architektura_Komputerów"
    assert body["planned"] == 4 and body["needs_review"] == 2
    assert {c["category"]: c["count"] for c in body["categories"]} == {
        "wyklad": 2, "kolokwia": 1, "inne": 1
    }
    assert body["methods"] == {"ai": 1, "deterministic": 2, "heuristic": 1}
    # Kubełki pewności wg config/thresholds.yaml, nie wg liczby wpisanej w widoku.
    assert body["confidence"]["buckets"] == {"auto": 2, "review": 1, "unresolved": 1, "brak": 0}
    assert body["confidence"]["thresholds"] == {"auto_apply": 0.90, "review_min": 0.70}
    assert body["ground_truth_categories"] == {"egzamin": 1}


def test_subject_is_found_by_alias_and_missing_one_is_404(client) -> None:
    assert client.get("/api/subjects/3/AK").json()["subject"]["skrot"] == "AKO"
    assert client.get("/api/subjects/3/NIEMA").status_code == 404


def test_ambiguous_skrot_is_refused_not_guessed(client) -> None:
    """SEM5 SI istnieje w dwóch strumieniach — zgadywanie byłoby cichym błędem."""
    assert client.get("/api/subjects/5/SI").status_code == 409

    resolved = client.get("/api/subjects/5/SI", params={"grupa": "Sieci"})
    assert resolved.status_code == 200 and resolved.json()["subject"]["nazwa"] == "Sieci_IP"


def test_items_skip_ground_truth_unless_asked(client) -> None:
    default = client.get("/api/items").json()
    with_gt = client.get("/api/items", params={"include_ground_truth": True}).json()

    assert SHA["a"] not in {item["sha256"] for item in default["items"]}
    assert SHA["a"] in {item["sha256"] for item in with_gt["items"]}
    assert with_gt["total"] == default["total"] + 1


def test_items_are_ordered_by_what_needs_an_eye_first(client) -> None:
    items = client.get("/api/items", params={"classified": True}).json()["items"]

    assert [item["needs_review"] for item in items][:2] == [1, 1]
    assert [item["sha256"] for item in items][:2] == [SHA["d"], SHA["c"]]


def test_item_filters_narrow_the_queue(client) -> None:
    assert client.get("/api/items", params={"needs_review": True}).json()["total"] == 2
    assert client.get("/api/items", params={"category": "wyklad"}).json()["total"] == 2
    assert client.get("/api/items", params={"action": "media"}).json()["total"] == 1
    assert client.get("/api/items", params={"confidence_max": 0.7}).json()["total"] == 1
    assert client.get("/api/items", params={"status": "extracted"}).json()["total"] == 5
    assert client.get("/api/items", params={"classified": False}).json()["total"] == 1
    assert client.get("/api/items", params={"skrot": "AKO"}).json()["total"] == 4


def test_confidence_bucket_comes_from_the_server_not_the_view(client) -> None:
    """Kubełek to reguła z thresholds.yaml — widok ma go pokazać, nie wyliczyć."""
    page = client.get("/api/items", params={"classified": True}).json()
    buckets = {item["sha256"]: item["confidence_bucket"] for item in page["items"]}

    assert page["thresholds"] == {"auto_apply": 0.90, "review_min": 0.70}
    assert buckets[SHA["b"]] == "auto"        # 0.95
    assert buckets[SHA["c"]] == "review"      # 0.74
    assert buckets[SHA["d"]] == "unresolved"  # 0.60
    assert client.get(f"/api/items/{SHA['e']}").json()["item"]["confidence_bucket"] == "auto"


def test_dashboard_carries_the_thresholds_the_view_displays(client) -> None:
    assert client.get("/api/subjects").json()["thresholds"] == {
        "auto_apply": 0.90, "review_min": 0.70
    }


def test_items_page_without_losing_rows(client) -> None:
    everything = client.get("/api/items", params={"limit": 500}).json()
    page = client.get("/api/items", params={"limit": 2, "offset": 2}).json()

    assert page["total"] == everything["total"]
    assert [item["sha256"] for item in page["items"]] == [
        item["sha256"] for item in everything["items"][2:4]
    ]


def test_item_row_carries_the_decision_and_one_representative_file(client) -> None:
    item = client.get(f"/api/items/{SHA['c']}").json()["item"]

    # Katalog źródłowy jedzie razem z pozycją: bez niego widok nie ma jak zaproponować
    # decyzji hurtowej „to samo dla rodzeństwa z tego katalogu" (S1.6).
    assert item["folder_path"] == "P/SEM3"

    assert item["category"] == "kolokwia" and item["action"] == "copy"
    assert item["reason"] == "bo kolokwia" and item["needs_review"] == 1
    assert item["source_relative_path"] == "SEM3/p2.pdf" and item["copies"] == 1


def test_item_detail_shows_every_copy_and_relation(client) -> None:
    detail = client.get(f"/api/items/{SHA['a']}").json()

    assert [f["source_relative_path"] for f in detail["files"]] == [
        "SEM3/p0.pdf", "SEM3/kopia/p0.pdf"
    ]
    assert detail["item"]["copies"] == 2
    assert detail["manual_decision"] is None

    related = client.get(f"/api/items/{SHA['b']}").json()
    assert related["relations"][0]["relation_type"] == "near_duplicate"
    assert related["plan_items"][0]["status"] == "planned"


def test_unknown_content_is_404_and_a_non_sha_is_422(client) -> None:
    assert client.get("/api/items/" + "0" * 64).status_code == 404
    assert client.get("/api/items/nie-jest-sha").status_code == 422


def test_s1_write_endpoints_exist(client) -> None:
    """S1: endpointy zapisu decyzji są wystawione (zastępuje test S0.7 no-write)."""
    paths = {getattr(route, "path", "") for route in client.app.routes}
    assert "/api/decisions" in paths
    assert "/api/decisions/batch" in paths
    assert "/api/decisions/undo" in paths


def test_connection_refuses_writes_even_if_someone_tries(index) -> None:
    conn = database.open_readonly(index)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM classifications")
    finally:
        conn.close()


def test_connection_survives_a_thread_handover(index) -> None:
    """FastAPI woła zależność i endpoint w RÓŻNYCH wątkach puli.

    Sprawdzone na żywym serwerze 2026-09-19: połączenie założone przy
    wchodzeniu w zależność trafiało do innego wątku niż wykonanie endpointu
    i sqlite3 odrzucał zapytanie (`SQLite objects created in a thread can only
    be used in that same thread`). TestClient tego nie pokazał, bo obsłużył
    oba kroki w tym samym wątku — dlatego kontrola jest tutaj, na poziomie
    połączenia, a nie tylko w smoke teście serwera.
    """
    from concurrent.futures import ThreadPoolExecutor

    conn = database.open_readonly(index)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            rows = pool.submit(lambda: conn.execute("SELECT COUNT(*) FROM content").fetchone()).result()
        assert rows[0] == len(SHA)
    finally:
        conn.close()


def test_other_schema_version_refuses_to_start(tmp_path) -> None:
    """Baza sprzed migracji odpowiada na część zapytań i milczy o reszcie — stąd bramka."""
    db_path = tmp_path / "stara.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
        "INSERT INTO schema_version VALUES (1, '2026-01-01T00:00:00Z');"
    )
    conn.commit()
    conn.close()

    with pytest.raises(database.SchemaMismatch):
        with TestClient(create_app(db_path, subjects=SUBJECTS, thresholds=THRESHOLDS)):
            pass


def test_missing_database_says_what_to_run(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="first-pass"):
        with TestClient(create_app(tmp_path / "nie-ma.sqlite", subjects=SUBJECTS,
                                   thresholds=THRESHOLDS)):
            pass


def test_confidence_buckets_follow_the_config_not_the_code(index) -> None:
    """Przesunięcie progu w thresholds.yaml MUSI przesunąć kubełki w widoku."""
    app = create_app(index, subjects=SUBJECTS,
                     thresholds={"confidence": {"auto_apply": 0.99, "review_min": 0.5}})
    with TestClient(app) as client:
        buckets = client.get("/api/subjects/3/AKO").json()["confidence"]["buckets"]

    assert buckets == {"auto": 1, "review": 3, "unresolved": 0, "brak": 0}


def test_stage_order_is_taken_from_status_report() -> None:
    assert queries.STAGE_ORDER is status_report.STAGE_ORDER
