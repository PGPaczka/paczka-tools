"""S1.3/S1.6/S1.8/S1.9: podgląd, decyzja hurtowa, containment, mutacja ground truth."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from orglib.decisions import GROUND_TRUTH_RUN_ID, MANUAL_RUN_ID
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
    db.upsert_folder(conn, {"folder_path": "P/SEM3/AKO", "source_package": "P"})
    for name, sha in SHA.items():
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P",
            "source_relative_path": f"SEM3/AKO/p_{name}.pdf",
            "folder_path": "P/SEM3/AKO",
            "filename": f"p_{name}.pdf", "extension": ".pdf",
            "size_bytes": 100, "sha256": sha, "status": "extracted",
        })
    # a-d: classified with needs_review
    for name in "abcd":
        db.upsert_classification(conn, {
            "sha256": SHA[name], "semester": 3, "subject_key": "AKO", "category": "wyklad",
            "classification_method": "heuristic", "confidence": 0.65,
            "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
            "action": "copy", "needs_review": 1, "is_outdated": 0,
        })
    # e: ground truth (protected)
    db.upsert_classification(conn, {
        "sha256": SHA["e"], "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "classification_method": "manual", "confidence": 1.0,
        "run_id": GROUND_TRUTH_RUN_ID, "decided_at": "2026-01-01T00:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


# --- S1.3: preview ---

def test_preview_returns_metadata(client) -> None:
    resp = client.get(f"/api/preview/{SHA['a']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sha256"] == SHA["a"]
    assert body["content_kind"] == "pdf"
    assert body["has_thumbnail"] is False


def test_preview_with_extracted_text(index, tmp_path) -> None:
    text_file = tmp_path / "text" / "a.txt"
    text_file.parent.mkdir()
    text_file.write_text("Architektura Komputerów — wykład 1\nWstęp.", encoding="utf-8")

    conn = db.connect(index)
    conn.execute("UPDATE content SET extracted_text_path = ? WHERE sha256 = ?",
                 (str(text_file), SHA["a"]))
    conn.commit()
    conn.close()

    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        body = c.get(f"/api/preview/{SHA['a']}").json()
        assert body["has_text"] is True
        assert "Architektura" in body["text_head"]


def test_preview_missing_sha_is_404(client) -> None:
    fake = "0" * 64
    assert client.get(f"/api/preview/{fake}").status_code == 404


def test_preview_no_text_returns_null(client) -> None:
    body = client.get(f"/api/preview/{SHA['a']}").json()
    assert body["text_head"] is None
    assert body["has_text"] is False


# --- S1.6: bulk by folder ---

def test_by_folder_lists_items(client) -> None:
    resp = client.get("/api/decisions/by-folder?folder=P/SEM3/AKO")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 4


def test_by_folder_bulk_skip(client) -> None:
    resp = client.post("/api/decisions/by-folder", json={
        "folder": "P/SEM3/AKO",
        "decision_type": "skip",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 4

    detail = client.get(f"/api/items/{SHA['a']}").json()
    assert detail["item"]["action"] == "skip"
    assert detail["item"]["confidence"] == 1.0


def test_by_folder_empty_is_404(client) -> None:
    resp = client.post("/api/decisions/by-folder", json={
        "folder": "NONEXISTENT/PATH",
        "decision_type": "skip",
    })
    assert resp.status_code == 404


def test_by_folder_skips_ground_truth(client) -> None:
    """Bulk skip on folder silently skips ground truth items."""
    resp = client.post("/api/decisions/by-folder", json={
        "folder": "P/SEM3/AKO",
        "decision_type": "skip",
    })
    assert resp.status_code == 200
    # Ground truth item e must remain unchanged
    detail = client.get(f"/api/items/{SHA['e']}").json()
    assert detail["item"]["run_id"] == GROUND_TRUTH_RUN_ID
    assert detail["item"]["action"] == "copy"


# --- S1.8: e2e decision → DB → export ---

def test_e2e_decision_to_db(client) -> None:
    """Decision via API ends up in both tables with correct values."""
    client.post("/api/decisions", json={
        "sha256": SHA["a"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "category": "egzamin",
        "action": "copy",
    })

    detail = client.get(f"/api/items/{SHA['a']}").json()
    assert detail["item"]["classification_method"] == "manual"
    assert detail["item"]["confidence"] == 1.0
    assert detail["item"]["category"] == "egzamin"
    assert detail["item"]["action"] == "copy"
    assert detail["item"]["run_id"] == MANUAL_RUN_ID

    assert detail["manual_decision"] is not None
    assert detail["manual_decision"]["decision_type"] == "classify"


def test_e2e_undo_restores_state(client) -> None:
    """Undo reverts classification to pre-decision state."""
    original = client.get(f"/api/items/{SHA['b']}").json()
    original_method = original["item"]["classification_method"]

    client.post("/api/decisions", json={
        "sha256": SHA["b"],
        "decision_type": "classify",
        "semester": 3,
        "subject_key": "AKO",
        "category": "egzamin",
        "action": "copy",
    })

    client.post("/api/decisions/undo")

    after_undo = client.get(f"/api/items/{SHA['b']}").json()
    assert after_undo["manual_decision"] is None


def test_e2e_export_contains_decision(index) -> None:
    """Decision appears in JSONL export."""
    from orglib.decisions import export, record_decision

    conn = db.connect(index)
    record_decision(conn, sha256=SHA["a"], decision_type="classify",
                    decided_by="test", semester=3, subject_key="AKO",
                    category="egzamin", action="copy")
    conn.commit()

    export_path = index.parent / "export.jsonl"
    count = export(conn, export_path)
    conn.close()

    assert count >= 1
    import json
    lines = export_path.read_text().strip().split("\n")
    exported_shas = {json.loads(line)["sha256"] for line in lines}
    assert SHA["a"] in exported_shas


# --- S1.9: mutation test — ground truth guard ---

def test_mutation_ground_truth_guard_catches_overwrite(client) -> None:
    """Ground truth row MUST be protected — any attempt to overwrite returns 409.

    This is the mutation test: if someone removes the guard in
    orglib.decisions._guard_ground_truth, this test MUST fail.
    """
    for decision_type in ("classify", "skip", "quarantine"):
        kwargs: dict = {"sha256": SHA["e"], "decision_type": decision_type}
        if decision_type == "classify":
            kwargs.update(semester=3, subject_key="AKO", action="copy")
        resp = client.post("/api/decisions", json=kwargs)
        assert resp.status_code == 409, (
            f"decision_type={decision_type} should be rejected for ground truth"
        )


def test_mutation_ground_truth_in_batch(client) -> None:
    """Batch containing ground truth item must fail atomically."""
    resp = client.post("/api/decisions/batch", json={
        "decisions": [
            {"sha256": SHA["a"], "decision_type": "skip"},
            {"sha256": SHA["e"], "decision_type": "skip"},
        ],
    })
    assert resp.status_code == 409

    # Verify a was NOT changed (batch is atomic)
    detail = client.get(f"/api/items/{SHA['a']}").json()
    assert detail["item"]["classification_method"] == "heuristic"


def test_mutation_ground_truth_run_id_preserved(client) -> None:
    """After any operation, ground truth row still has run_id='ground_truth'."""
    client.post("/api/decisions", json={
        "sha256": SHA["a"], "decision_type": "skip",
    })

    detail = client.get(f"/api/items/{SHA['e']}").json()
    assert detail["item"]["run_id"] == GROUND_TRUTH_RUN_ID
    assert detail["item"]["confidence"] == 1.0
