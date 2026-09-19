"""S1: endpointy zapisu decyzji — kontrakt API, ochrona ground truth, cofnięcie."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from orglib.decisions import GROUND_TRUTH_RUN_ID
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdef"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}


def _subject(semester, skrot, nazwa, **kw):
    return config.Subject(
        semester=semester, skrot=skrot, nazwa=nazwa,
        forms=kw.get("forms", ("W", "C")), aliases=(),
        instancja=None, strumien=None, profil=None, katedra=None,
    )


SUBJECTS = [_subject(3, "AKO", "Architektura_Komputerów")]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for i, sha in enumerate(SHA.values()):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/p{i}.pdf",
            "folder_path": "P/SEM3", "filename": f"p{i}.pdf", "extension": ".pdf",
            "size_bytes": 100, "sha256": sha, "status": "extracted",
        })
    # Ground truth — protected from overwrite
    db.upsert_classification(conn, {
        "sha256": SHA["f"], "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "target_relative_path": "paczka/SEM3/AKO/wyklad/gt.pdf",
        "classification_method": "manual", "confidence": 1.0,
        "run_id": GROUND_TRUTH_RUN_ID, "decided_at": "2026-01-01T00:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })
    # Existing classification with needs_review
    db.upsert_classification(conn, {
        "sha256": SHA["b"], "semester": 3, "subject_key": "AKO", "category": "inne",
        "classification_method": "heuristic", "confidence": 0.65,
        "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
        "action": "copy", "needs_review": 1, "is_outdated": 0,
    })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def test_classify_decision_via_api(client) -> None:
    resp = client.post("/api/decisions", json={
        "sha256": SHA["a"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "category": "egzamin",
        "action": "copy",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision_type"] == "classify"
    assert body["sha256"] == SHA["a"]


def test_skip_decision_updates_classification(client) -> None:
    resp = client.post("/api/decisions", json={
        "sha256": SHA["b"],
        "decision_type": "skip",
    })
    assert resp.status_code == 200

    detail = client.get(f"/api/items/{SHA['b']}").json()
    assert detail["item"]["action"] == "skip"
    assert detail["item"]["confidence"] == 1.0


def test_ground_truth_is_409(client) -> None:
    resp = client.post("/api/decisions", json={
        "sha256": SHA["f"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "action": "copy",
    })
    assert resp.status_code == 409
    assert "ground_truth" in resp.json()["detail"]


def test_batch_records_multiple_decisions(client) -> None:
    resp = client.post("/api/decisions/batch", json={
        "decisions": [
            {"sha256": SHA["c"], "decision_type": "classify",
             "semester": 3, "subject_key": "AKO", "category": "wyklad", "action": "copy"},
            {"sha256": SHA["d"], "decision_type": "skip"},
        ],
    })
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_batch_with_ground_truth_is_409(client) -> None:
    resp = client.post("/api/decisions/batch", json={
        "decisions": [
            {"sha256": SHA["e"], "decision_type": "skip"},
            {"sha256": SHA["f"], "decision_type": "classify",
             "semester": 3, "subject_key": "AKO", "action": "copy"},
        ],
    })
    assert resp.status_code == 409


def test_undo_removes_last_decision(client) -> None:
    client.post("/api/decisions", json={
        "sha256": SHA["a"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "category": "wyklad",
        "action": "copy",
    })

    resp = client.post("/api/decisions/undo")
    assert resp.status_code == 200
    assert resp.json()["undone"]["sha256"] == SHA["a"]


def test_undo_on_empty_is_404(client) -> None:
    assert client.post("/api/decisions/undo").status_code == 404


def test_missing_sha256_is_422(client) -> None:
    resp = client.post("/api/decisions", json={
        "decision_type": "classify",
    })
    assert resp.status_code == 422


def test_queue_returns_needs_review_items(client) -> None:
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    if body["items"]:
        assert body["items"][0]["needs_review"] == 1


def test_decision_is_reflected_in_dashboard(client) -> None:
    client.post("/api/decisions", json={
        "sha256": SHA["a"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "category": "egzamin",
        "action": "copy",
        "note": "test decision",
    })

    detail = client.get(f"/api/items/{SHA['a']}").json()
    assert detail["item"]["classification_method"] == "manual"
    assert detail["item"]["confidence"] == 1.0
    assert detail["manual_decision"] is not None
    assert detail["manual_decision"]["decision_type"] == "classify"
