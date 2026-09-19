"""B14: ręczne decyzje — zapis, ochrona ground truth, cofnięcie, eksport."""

from __future__ import annotations

import json
import sqlite3

import pytest

from orglib import db
from orglib.decisions import (
    GROUND_TRUTH_RUN_ID,
    MANUAL_RUN_ID,
    GroundTruthConflict,
    export,
    record_batch,
    record_decision,
    undo_last,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_GT = "d" * 64


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "test.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for sha in (SHA_A, SHA_B, SHA_C, SHA_GT):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/{sha[:4]}.pdf",
            "folder_path": "P/SEM3", "filename": f"{sha[:4]}.pdf", "extension": ".pdf",
            "size_bytes": 100, "sha256": sha, "status": "extracted",
        })
    db.upsert_classification(conn, {
        "sha256": SHA_GT, "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "target_relative_path": "paczka/SEM3/AKO/wyklad/gt.pdf",
        "classification_method": "manual", "confidence": 1.0,
        "run_id": GROUND_TRUTH_RUN_ID, "decided_at": "2026-01-01T00:00:00Z",
        "action": "copy", "needs_review": 0, "is_outdated": 0,
    })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def conn(index):
    c = db.connect(index)
    yield c
    c.close()


def test_classify_writes_to_both_tables(conn):
    result = record_decision(
        conn, sha256=SHA_A, decision_type="classify", decided_by="test",
        semester=3, subject_key="AKO", category="egzamin", action="copy",
        target_relative_path="paczka/SEM3/AKO/egzamin/a.pdf",
    )
    conn.commit()

    assert result["decision_type"] == "classify"

    md = conn.execute("SELECT * FROM manual_decisions WHERE sha256 = ?", (SHA_A,)).fetchone()
    assert md is not None
    assert md["decision_type"] == "classify"
    assert md["decided_by"] == "test"

    cl = conn.execute("SELECT * FROM classifications WHERE sha256 = ?", (SHA_A,)).fetchone()
    assert cl is not None
    assert cl["classification_method"] == "manual"
    assert cl["confidence"] == 1.0
    assert cl["run_id"] == MANUAL_RUN_ID
    assert cl["needs_review"] == 0
    assert cl["action"] == "copy"
    assert cl["category"] == "egzamin"


def test_skip_updates_classification_if_exists(conn):
    db.upsert_classification(conn, {
        "sha256": SHA_B, "semester": 3, "subject_key": "AKO", "category": "inne",
        "classification_method": "heuristic", "confidence": 0.7,
        "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
        "action": "copy", "needs_review": 1, "is_outdated": 0,
    })
    conn.commit()

    record_decision(conn, sha256=SHA_B, decision_type="skip", decided_by="test")
    conn.commit()

    cl = conn.execute("SELECT * FROM classifications WHERE sha256 = ?", (SHA_B,)).fetchone()
    assert cl["action"] == "skip"
    assert cl["confidence"] == 1.0
    assert cl["needs_review"] == 0


def test_skip_without_prior_classification_only_writes_manual(conn):
    record_decision(conn, sha256=SHA_C, decision_type="skip", decided_by="test")
    conn.commit()

    md = conn.execute("SELECT * FROM manual_decisions WHERE sha256 = ?", (SHA_C,)).fetchone()
    assert md is not None

    cl = conn.execute("SELECT * FROM classifications WHERE sha256 = ?", (SHA_C,)).fetchone()
    assert cl is None


def test_ground_truth_is_protected(conn):
    with pytest.raises(GroundTruthConflict):
        record_decision(
            conn, sha256=SHA_GT, decision_type="classify", decided_by="test",
            semester=3, subject_key="AKO", action="copy",
        )


def test_ground_truth_skip_is_also_refused(conn):
    with pytest.raises(GroundTruthConflict):
        record_decision(conn, sha256=SHA_GT, decision_type="skip", decided_by="test")


def test_batch_is_atomic(conn):
    decisions = [
        {"sha256": SHA_A, "decision_type": "classify", "semester": 3,
         "subject_key": "AKO", "category": "wyklad", "action": "copy"},
        {"sha256": SHA_B, "decision_type": "skip"},
    ]
    results = record_batch(conn, decisions, decided_by="batch_test")
    assert len(results) == 2

    count = conn.execute("SELECT COUNT(*) FROM manual_decisions").fetchone()[0]
    assert count == 2


def test_batch_rolls_back_on_ground_truth_conflict(conn):
    decisions = [
        {"sha256": SHA_A, "decision_type": "skip"},
        {"sha256": SHA_GT, "decision_type": "classify", "semester": 3,
         "subject_key": "AKO", "action": "copy"},
    ]
    with pytest.raises(GroundTruthConflict):
        record_batch(conn, decisions, decided_by="test")

    count = conn.execute("SELECT COUNT(*) FROM manual_decisions").fetchone()[0]
    assert count == 0


def test_undo_removes_last_decision(conn):
    record_decision(conn, sha256=SHA_A, decision_type="classify", decided_by="test",
                    semester=3, subject_key="AKO", category="wyklad", action="copy")
    conn.commit()

    undone = undo_last(conn)
    assert undone is not None
    assert undone["sha256"] == SHA_A

    md = conn.execute("SELECT * FROM manual_decisions WHERE sha256 = ?", (SHA_A,)).fetchone()
    assert md is None
    cl = conn.execute("SELECT * FROM classifications WHERE sha256 = ?", (SHA_A,)).fetchone()
    assert cl is None


def test_undo_on_empty_returns_none(conn):
    assert undo_last(conn) is None


def test_export_writes_jsonl(conn, tmp_path):
    record_decision(conn, sha256=SHA_A, decision_type="classify", decided_by="test",
                    semester=3, subject_key="AKO", category="wyklad", action="copy")
    record_decision(conn, sha256=SHA_B, decision_type="skip", decided_by="test",
                    note="nie pasuje")
    conn.commit()

    out = tmp_path / "export.jsonl"
    count = export(conn, out)
    assert count == 2

    lines = out.read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert "sha256" in first
    assert "decision_type" in first
    assert "decided_at" in first


def test_classify_requires_semester_and_subject(conn):
    with pytest.raises(ValueError, match="semester"):
        record_decision(conn, sha256=SHA_A, decision_type="classify",
                        decided_by="test")


def test_invalid_decision_type_is_rejected(conn):
    with pytest.raises(ValueError, match="nieznany"):
        record_decision(conn, sha256=SHA_A, decision_type="invalid",
                        decided_by="test")
