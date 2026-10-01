"""Q2: scalenie dwóch treści — „to jest ten sam materiał, zostaje jedna kopia".

Dotąd studio umiało tylko rozstrzygnąć klaster: kanoniczna zostaje, reszta dostaje
`skip` z notatką. Notatka jest tekstem dla człowieka — nic maszynowego nie łączyło
pominiętej treści z tą, która ją wchłonęła, więc graf i raporty tego nie widziały.
Scalenie zapisuje oba ślady: decyzję (`skip`) i relację w `relations`.

Relacja musi PRZEŻYĆ ponowne liczenie relacji (`just relate`) — inaczej ręczna praca
znikałaby po każdym przebiegu potoku. To pilnuje test na końcu pliku, wołając prawdziwy
`replace_own_relations`, a nie sprawdzając nazwę metody.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from orglib.decisions import GROUND_TRUTH_RUN_ID
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdef"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W", "C"), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)]


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
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "wyklad",
            "target_relative_path": f"paczka/SEM3/AKO/wyklad/p{i}.pdf",
            "classification_method": "heuristic", "confidence": 0.8,
            "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
            "action": "copy", "needs_review": 1, "is_outdated": 0,
        })
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


def _merge(client, canonical: str, absorbed: list[str], **extra):
    return client.post("/api/decisions/merge", json={
        "canonical_sha256": canonical, "absorbed": absorbed, **extra,
    })


def _relacje(db_path, sha: str) -> list[dict]:
    conn = db.connect(db_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM relations WHERE source_sha256 = ? OR target_sha256 = ?", (sha, sha),
    )]
    conn.close()
    return rows


# --- co scalenie zapisuje ---------------------------------------------------

def test_absorbed_content_is_skipped(client) -> None:
    assert _merge(client, SHA["a"], [SHA["b"]]).status_code == 200

    wchloniety = client.get(f"/api/items/{SHA['b']}").json()["item"]
    kanoniczna = client.get(f"/api/items/{SHA['a']}").json()["item"]

    assert wchloniety["action"] == "skip"
    # Kanoniczna nie zmienia się: scalenie mówi o tej DRUGIEJ treści.
    assert kanoniczna["action"] == "copy"


def test_merge_leaves_a_machine_readable_relation(client, index) -> None:
    """Bez wiersza w `relations` scalenie byłoby tylko notatką — graf by go nie zobaczył."""
    _merge(client, SHA["a"], [SHA["b"]])

    relacje = _relacje(index, SHA["b"])

    assert len(relacje) == 1
    relacja = relacje[0]
    assert relacja["source_sha256"] == SHA["b"] and relacja["target_sha256"] == SHA["a"]
    assert relacja["relation_type"] == "near_duplicate"
    assert relacja["confidence"] == 1.0


def test_older_version_is_a_different_relation(client, index) -> None:
    _merge(client, SHA["a"], [SHA["b"]], relation="older_version")

    assert _relacje(index, SHA["b"])[0]["relation_type"] == "older_version"


def test_merge_takes_several_contents_at_once(client) -> None:
    body = _merge(client, SHA["a"], [SHA["b"], SHA["c"]]).json()

    assert body["merged"] == 2
    assert client.get(f"/api/items/{SHA['c']}").json()["item"]["action"] == "skip"


def test_merging_twice_changes_nothing(client, index) -> None:
    """Ten sam ruch dwa razy to jedna relacja — inaczej lista relacji by puchła."""
    _merge(client, SHA["a"], [SHA["b"]])
    drugie = _merge(client, SHA["a"], [SHA["b"]])

    assert drugie.status_code == 200
    assert len(_relacje(index, SHA["b"])) == 1


# --- czego scalić nie wolno -------------------------------------------------

def test_content_cannot_absorb_itself(client) -> None:
    assert _merge(client, SHA["a"], [SHA["a"]]).status_code == 422


def test_empty_list_is_refused(client) -> None:
    assert _merge(client, SHA["a"], []).status_code == 422


def test_unknown_content_is_404(client) -> None:
    assert _merge(client, SHA["a"], ["9" * 64]).status_code == 404


def test_ground_truth_is_never_absorbed(client, index) -> None:
    """Materiał leżący w paczce nie znika dlatego, że ktoś uznał inny plik za lepszy."""
    odpowiedz = _merge(client, SHA["a"], [SHA["f"]])

    assert odpowiedz.status_code == 409
    assert _relacje(index, SHA["f"]) == []


def test_an_unknown_relation_kind_is_refused(client) -> None:
    assert _merge(client, SHA["a"], [SHA["b"]], relation="wymyslona").status_code == 422


# --- najważniejsze: ręczna praca przeżywa potok -----------------------------

def test_recomputing_relations_does_not_erase_a_merge(client, index) -> None:
    """`just relate` podmienia WŁASNY wycinek — ręczne scalenie ma zostać nietknięte."""
    import near_dupe as near_dupe_cli

    _merge(client, SHA["a"], [SHA["b"]])

    conn = db.connect(index)
    skasowane = near_dupe_cli.replace_own_relations(conn, [], {SHA["a"], SHA["b"]})
    conn.close()

    assert skasowane == 0
    assert len(_relacje(index, SHA["b"])) == 1
