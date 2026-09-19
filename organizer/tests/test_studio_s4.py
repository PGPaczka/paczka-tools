"""S4: historia decyzji, wyszukiwanie przekrojowe, statystyki na żywo."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from orglib.decisions import GROUND_TRUTH_RUN_ID
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdefgh"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}


def _subject(semester, skrot, nazwa, **kw):
    return config.Subject(
        semester=semester, skrot=skrot, nazwa=nazwa,
        forms=kw.get("forms", ("W", "C")), aliases=(),
        instancja=None, strumien=None, profil=None, katedra=None,
    )


SUBJECTS = [
    _subject(3, "AKO", "Architektura_Komputerów"),
    _subject(2, "PO", "Programowanie_Obiektowe"),
]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for i, (name, sha) in enumerate(SHA.items()):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/p_{name}.pdf",
            "folder_path": "P/SEM3", "filename": f"egzamin_{name}.pdf", "extension": ".pdf",
            "size_bytes": 100 + i, "sha256": sha, "status": "extracted",
        })

    db.upsert_classification(conn, {
        "sha256": SHA["a"], "semester": 3, "subject_key": "AKO", "category": "egzamin",
        "classification_method": "heuristic", "confidence": 0.85,
        "run_id": "plan:x", "decided_at": "2026-09-10T10:00:00Z",
        "action": "copy", "needs_review": 1, "is_outdated": 0,
    })
    db.upsert_classification(conn, {
        "sha256": SHA["b"], "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "classification_method": "ai", "confidence": 0.95,
        "run_id": "plan:y", "decided_at": "2026-09-11T10:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })
    db.upsert_classification(conn, {
        "sha256": SHA["c"], "semester": 2, "subject_key": "PO", "category": "laboratoria",
        "classification_method": "manual", "confidence": 1.0,
        "run_id": "manual_decision", "decided_at": "2026-09-12T10:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })
    db.upsert_classification(conn, {
        "sha256": SHA["d"], "semester": 3, "subject_key": "AKO", "category": "kolokwia",
        "classification_method": "manual", "confidence": 1.0,
        "run_id": GROUND_TRUTH_RUN_ID, "decided_at": "2026-01-01T00:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })

    conn.execute(
        "INSERT INTO manual_decisions (sha256, decision_type, decided_by, decided_at, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (SHA["a"], "classify", "alice", "2026-09-15T08:00:00Z", "poprawka"),
    )
    conn.execute(
        "INSERT INTO manual_decisions (sha256, decision_type, decided_by, decided_at, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (SHA["b"], "skip", "bob", "2026-09-16T09:00:00Z", None),
    )
    conn.execute(
        "INSERT INTO manual_decisions (sha256, decision_type, decided_by, decided_at, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (SHA["c"], "classify", "alice", "2026-09-17T10:00:00Z", "laby PO"),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


# --- S4.2: history ---

class TestHistory:
    def test_history_returns_all(self, client) -> None:
        resp = client.get("/api/decisions/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["decisions"]) == 3
        assert body["decisions"][0]["decided_at"] >= body["decisions"][-1]["decided_at"]

    def test_history_filter_by_author(self, client) -> None:
        resp = client.get("/api/decisions/history?decided_by=alice")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(d["decided_by"] == "alice" for d in body["decisions"])

    def test_history_filter_by_since(self, client) -> None:
        resp = client.get("/api/decisions/history?since=2026-09-16")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        shas = {d["sha256"] for d in body["decisions"]}
        assert SHA["a"] not in shas

    def test_history_pagination(self, client) -> None:
        resp = client.get("/api/decisions/history?limit=1&offset=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["decisions"]) == 1
        assert body["limit"] == 1
        assert body["offset"] == 1

    def test_history_decision_shape(self, client) -> None:
        resp = client.get("/api/decisions/history")
        d = resp.json()["decisions"][0]
        assert "sha256" in d
        assert "decision_type" in d
        assert "decided_by" in d
        assert "decided_at" in d


# --- S4.2: delete decision ---

class TestDeleteDecision:
    def test_delete_removes_manual_decision(self, client) -> None:
        resp = client.delete(f"/api/decisions/{SHA['a']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["undone"]["sha256"] == SHA["a"]
        history = client.get("/api/decisions/history").json()
        assert history["total"] == 2

    def test_delete_removes_manual_classification(self, client) -> None:
        resp = client.delete(f"/api/decisions/{SHA['c']}")
        assert resp.status_code == 200
        detail = client.get(f"/api/items/{SHA['c']}").json()
        assert detail["item"]["run_id"] != "manual_decision"
        assert detail["manual_decision"] is None

    def test_delete_preserves_nonmanual_classification(self, client) -> None:
        resp = client.delete(f"/api/decisions/{SHA['a']}")
        assert resp.status_code == 200
        detail = client.get(f"/api/items/{SHA['a']}").json()
        assert detail["item"]["run_id"] == "plan:x"
        assert detail["manual_decision"] is None

    def test_delete_missing_404(self, client) -> None:
        sha = "f" * 64
        resp = client.delete(f"/api/decisions/{sha}")
        assert resp.status_code == 404


# --- S4.3: search ---

class TestSearch:
    def test_search_by_filename(self, client) -> None:
        resp = client.get("/api/search?q=egzamin_a")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert body["query"] == "egzamin_a"
        shas = {item["sha256"] for item in body["items"]}
        assert SHA["a"] in shas

    def test_search_by_sha_prefix(self, client) -> None:
        prefix = SHA["b"][:12]
        resp = client.get(f"/api/search?q={prefix}")
        assert resp.status_code == 200
        body = resp.json()
        assert any(item["sha256"] == SHA["b"] for item in body["items"])

    def test_search_by_category(self, client) -> None:
        resp = client.get("/api/search?q=laboratoria")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1

    def test_search_by_path(self, client) -> None:
        resp = client.get("/api/search?q=SEM3/p_a")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_search_no_results(self, client) -> None:
        resp = client.get("/api/search?q=nonexistent_zzz_xyz")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_search_limit(self, client) -> None:
        resp = client.get("/api/search?q=egzamin&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 2

    def test_search_requires_query(self, client) -> None:
        resp = client.get("/api/search")
        assert resp.status_code == 422


# --- S4.4: stats ---

class TestStats:
    def test_stats_shape(self, client) -> None:
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "thresholds" in body
        assert "totals" in body
        assert "stages" in body
        assert "methods" in body
        assert "categories" in body
        assert "actions" in body

    def test_stats_thresholds(self, client) -> None:
        body = client.get("/api/stats").json()
        assert body["thresholds"]["auto_apply"] == 0.90
        assert body["thresholds"]["review_min"] == 0.70

    def test_stats_totals(self, client) -> None:
        body = client.get("/api/stats").json()
        totals = body["totals"]
        assert totals["contents"] == 8
        assert totals["files"] == 8
        assert totals["subjects"] == 2
        assert totals["manual_decisions"] == 3

    def test_stats_methods(self, client) -> None:
        body = client.get("/api/stats").json()
        methods = body["methods"]
        assert "heuristic" in methods or "ai" in methods or "manual" in methods

    def test_stats_categories(self, client) -> None:
        body = client.get("/api/stats").json()
        cats = body["categories"]
        assert isinstance(cats, dict)
        assert sum(cats.values()) > 0

    def test_stats_stages(self, client) -> None:
        body = client.get("/api/stats").json()
        stages = body["stages"]
        assert isinstance(stages, dict)
        assert sum(stages.values()) == 2
