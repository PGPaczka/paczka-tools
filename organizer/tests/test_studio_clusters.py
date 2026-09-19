"""S2: klastry near-dupe — kontrakt API, rozstrzyganie, filtr szumu."""

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


SUBJECTS = [_subject(3, "AKO", "Architektura_Komputerów")]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for name, sha in SHA.items():
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        if name in ("g", "h"):
            ext = ".xml" if name == "g" else ".pdf"
            fname = "noise.vcxproj.xml" if name == "g" else f"p_{name}.pdf"
        else:
            ext = ".pdf"
            fname = f"p_{name}.pdf"
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/{fname}",
            "folder_path": "P/SEM3", "filename": fname, "extension": ext,
            "size_bytes": 100, "sha256": sha, "status": "extracted",
        })
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "wyklad",
            "target_relative_path": f"paczka/SEM3/AKO/wyklad/{fname}",
            "classification_method": "heuristic", "confidence": 0.75,
            "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
            "action": "copy", "needs_review": 1, "is_outdated": 0,
        })

    db.upsert(conn, "relations", {
        "source_sha256": SHA["a"], "target_sha256": SHA["b"],
        "relation_type": "near_duplicate", "confidence": 0.95,
        "detection_method": "near_dupe:simhash", "reason": "simhash, odległość 1",
    }, conflict=("source_sha256", "target_sha256", "relation_type"))
    db.upsert(conn, "relations", {
        "source_sha256": SHA["b"], "target_sha256": SHA["c"],
        "relation_type": "near_duplicate", "confidence": 0.85,
        "detection_method": "near_dupe:simhash", "reason": "simhash, odległość 2",
    }, conflict=("source_sha256", "target_sha256", "relation_type"))
    db.upsert(conn, "relations", {
        "source_sha256": SHA["d"], "target_sha256": SHA["e"],
        "relation_type": "older_version", "confidence": 0.90,
        "detection_method": "near_dupe:normalized_text", "reason": "ten sam tekst, rok 2023 vs 2024",
    }, conflict=("source_sha256", "target_sha256", "relation_type"))
    db.upsert(conn, "relations", {
        "source_sha256": SHA["g"], "target_sha256": SHA["h"],
        "relation_type": "near_duplicate", "confidence": 0.80,
        "detection_method": "near_dupe:simhash", "reason": "simhash",
    }, conflict=("source_sha256", "target_sha256", "relation_type"))
    # Ground truth on f — for testing resolve conflict
    db.upsert_classification(conn, {
        "sha256": SHA["f"], "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "target_relative_path": "paczka/SEM3/AKO/wyklad/gt.pdf",
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


def test_clusters_endpoint_returns_groups(client) -> None:
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2


def test_cluster_contains_expected_members(client) -> None:
    body = client.get("/api/clusters").json()
    all_members = {sha for cluster in body["clusters"] for m in cluster["members"] for sha in [m["sha256"]]}
    assert SHA["a"] in all_members
    assert SHA["b"] in all_members
    assert SHA["c"] in all_members


def test_cluster_abc_is_merged(client) -> None:
    """a-b and b-c should form a single cluster via union-find transitivity."""
    body = client.get("/api/clusters").json()
    for cluster in body["clusters"]:
        member_shas = {m["sha256"] for m in cluster["members"]}
        if SHA["a"] in member_shas:
            assert SHA["b"] in member_shas
            assert SHA["c"] in member_shas
            assert cluster["size"] == 3
            return
    pytest.fail("cluster with a, b, c not found")


def test_cluster_de_has_older_version(client) -> None:
    body = client.get("/api/clusters").json()
    for cluster in body["clusters"]:
        member_shas = {m["sha256"] for m in cluster["members"]}
        if SHA["d"] in member_shas:
            assert cluster["has_older_version"] is True
            assert cluster["size"] == 2
            return
    pytest.fail("cluster with d, e not found")


def test_clusters_filter_by_semester(client) -> None:
    resp = client.get("/api/clusters?semester=3")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


def test_clusters_filter_by_subject(client) -> None:
    resp = client.get("/api/clusters?skrot=AKO")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


def test_noise_filter_excludes_matching(client) -> None:
    """Noise pattern matching a file path should exclude the whole cluster."""
    without_noise = client.get("/api/clusters").json()["total"]
    with_noise = client.get("/api/clusters?noise=*.vcxproj*").json()["total"]
    assert with_noise < without_noise


def test_resolve_cluster_skips_non_canonical(client) -> None:
    resp = client.post("/api/clusters/resolve", json={
        "canonical_sha256": SHA["a"],
        "members": [SHA["a"], SHA["b"], SHA["c"]],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical"] == SHA["a"]
    assert body["skipped"] == 2

    b_detail = client.get(f"/api/items/{SHA['b']}").json()
    assert b_detail["item"]["action"] == "skip"
    assert b_detail["item"]["confidence"] == 1.0

    c_detail = client.get(f"/api/items/{SHA['c']}").json()
    assert c_detail["item"]["action"] == "skip"


def test_resolve_does_not_delete_data(client) -> None:
    """S2.6: resolution adds decisions, never deletes rows."""
    client.post("/api/clusters/resolve", json={
        "canonical_sha256": SHA["d"],
        "members": [SHA["d"], SHA["e"]],
    })
    d_detail = client.get(f"/api/items/{SHA['d']}").json()
    e_detail = client.get(f"/api/items/{SHA['e']}").json()
    assert d_detail["item"] is not None
    assert e_detail["item"] is not None
    assert e_detail["item"]["action"] == "skip"


def test_resolve_with_ground_truth_is_409(client) -> None:
    resp = client.post("/api/clusters/resolve", json={
        "canonical_sha256": SHA["a"],
        "members": [SHA["a"], SHA["f"]],
    })
    assert resp.status_code == 409


def test_resolve_missing_canonical_is_422(client) -> None:
    resp = client.post("/api/clusters/resolve", json={
        "canonical_sha256": SHA["a"],
        "members": [SHA["b"], SHA["c"]],
    })
    assert resp.status_code == 422


def test_resolve_empty_members_is_422(client) -> None:
    resp = client.post("/api/clusters/resolve", json={
        "canonical_sha256": SHA["a"],
        "members": [],
    })
    assert resp.status_code == 422
