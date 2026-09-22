"""S4.1: studio i graf odnajdują się po tym samym identyfikatorze treści.

Graf zna `id` notatki, studio zna `sha256`. Tłumaczenie stoi na kontrakcie
`synapse_vault`: id notatki pliku kończy się `sha256[:ID_SHA_PREFIX]`. Te testy
pilnują obu kierunków i tego, że **wieloznaczność nie jest zgadywana**, a serwowanie
vaulta nie staje się boczną drogą do plików spoza `work`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from orglib import config, db, graph_link
from orglib.synapse_vault import ID_SHA_PREFIX, file_id, subject_id
from studio.api.app import create_app

SHA = {
    "a": "09c8e27e" + "0" * 56,
    "b": "1b2c3d4e" + "1" * 56,
}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [
    config.Subject(
        semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
        instancja=None, strumien=None, profil=None, katedra=None,
    )
]


@pytest.fixture
def workspace(tmp_path):
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    vault = paths.work / "synapse" / "vault" / "sem3"
    vault.mkdir(parents=True)
    for name, sha in SHA.items():
        note = file_id("AKO", sha, f"plik_{name}.pdf")
        (vault / f"{note}.md").write_text(f"---\ntitle: {name}\n---\nsha256: `{sha}`\n", encoding="utf-8")
    (vault.parent / "sem3.md").write_text("---\ntitle: SEM3\n---\n", encoding="utf-8")
    (paths.work / "synapse" / "graph.json").write_text(
        json.dumps({"schemaVersion": 1, "nodes": [], "edges": []}), encoding="utf-8"
    )

    conn = db.connect(paths.work_db)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for name, sha in SHA.items():
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/plik_{name}.pdf",
            "folder_path": "P/SEM3", "filename": f"plik_{name}.pdf", "extension": ".pdf",
            "size_bytes": 10, "sha256": sha, "status": "extracted",
        })
    conn.commit()
    conn.close()
    return paths


@pytest.fixture
def client(workspace):
    app = create_app(workspace.work_db, paths=workspace, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as test_client:
        yield test_client


# --- tłumaczenie identyfikatorów ------------------------------------------

def test_node_id_carries_the_sha_prefix() -> None:
    """To jest CAŁY kontrakt tłumaczenia — reszta modułu z niego wynika."""
    node = file_id("AKO", SHA["a"], "wyklad1.pdf")

    assert node.endswith(SHA["a"][:ID_SHA_PREFIX])
    assert graph_link.sha_prefix_of_node(node) == SHA["a"][:ID_SHA_PREFIX]


def test_subject_and_semester_nodes_point_at_no_content() -> None:
    assert graph_link.sha_prefix_of_node(subject_id(3, "AKO")) is None
    assert graph_link.sha_prefix_of_node("sem3") is None


def test_vault_is_indexed_from_file_names(workspace) -> None:
    index = graph_link.scan_vault(workspace.work / "synapse" / "vault")

    assert set(index) == {sha[:ID_SHA_PREFIX] for sha in SHA.values()}
    assert graph_link.nodes_for_sha(index, SHA["a"])[0].endswith(SHA["a"][:ID_SHA_PREFIX])


def test_missing_vault_is_empty_not_an_error(tmp_path) -> None:
    assert graph_link.scan_vault(tmp_path / "nie-ma") == {}


# --- studio → graf ---------------------------------------------------------

def test_content_resolves_to_its_node(client) -> None:
    body = client.get(f"/api/graph/node/{SHA['a']}").json()

    assert body["nodes"][0].endswith(SHA["a"][:ID_SHA_PREFIX])
    assert body["url"] == f"/graf#{body['nodes'][0]}"


def test_content_outside_the_vault_is_404(client) -> None:
    response = client.get("/api/graph/node/" + "f" * 64)

    assert response.status_code == 404
    assert "graf" in response.json()["detail"]


def test_subject_has_its_own_node(client) -> None:
    body = client.get("/api/graph/subject/3/AKO").json()

    assert body["node"] == subject_id(3, "AKO")
    assert body["url"].startswith("/graf#")


# --- graf → studio ---------------------------------------------------------

def test_node_resolves_back_to_the_content(client) -> None:
    node = client.get(f"/api/graph/node/{SHA['b']}").json()["nodes"][0]

    body = client.get(f"/api/graph/content/{node}").json()

    assert body["sha256"] == SHA["b"]
    assert body["item"]["filename"] == "plik_b.pdf"


def test_a_node_without_content_is_404_not_a_guess(client) -> None:
    assert client.get("/api/graph/content/sem3-ako").status_code == 404


def test_an_ambiguous_prefix_returns_candidates_instead_of_choosing(client, workspace) -> None:
    """Dwie treści o tym samym skrócie sha to wybór dla człowieka, nie losowanie."""
    twin = SHA["a"][:ID_SHA_PREFIX] + "9" * 56
    conn = db.connect(workspace.work_db)
    db.upsert_content(conn, {"sha256": twin, "content_kind": "pdf"})
    conn.commit()
    conn.close()
    node = file_id("AKO", SHA["a"], "plik_a.pdf")

    body = client.get(f"/api/graph/content/{node}").json()

    assert set(body["candidates"]) == {SHA["a"], twin}
    assert body["sha256"] is None and body["item"] is None


# --- serwowanie grafu ------------------------------------------------------

def test_status_says_what_is_missing(client) -> None:
    body = client.get("/api/graph/status").json()

    assert body["notes"] == len(SHA)
    assert body["graph_json"].endswith("graph.json")
    assert body["hint"] == "just studio-graf"


def test_graph_json_is_served_where_the_viewer_looks_for_it(client) -> None:
    response = client.get("/graph.json")

    assert response.status_code == 200 and response.json()["schemaVersion"] == 1


def test_vault_notes_are_served_read_only(client) -> None:
    node = file_id("AKO", SHA["a"], "plik_a.pdf")

    response = client.get(f"/vault/sem3/{node}.md")

    assert response.status_code == 200
    assert SHA["a"] in response.text


@pytest.mark.parametrize("path", [
    # Kropki MUSZĄ być zakodowane: klient HTTP (httpx, przeglądarka) normalizuje
    # `..` w adresie PRZED wysłaniem, więc wersja niezakodowana nigdy nie dociera
    # do serwera i niczego nie dowodzi — mutacja containmentu przechodziła przez
    # taki test bez mrugnięcia (2026-09-22).
    "%2e%2e/%2e%2e/index.sqlite",
    "sem3/%2e%2e/%2e%2e/%2e%2e/tajne.md",
    "%2e%2e/synapse/graph.json",
])
def test_vault_is_not_a_side_door_to_other_files(client, path) -> None:
    """Podgląd vaulta chodzi przez ten sam helper containmentu, co reszta studia."""
    assert client.get(f"/vault/{path}").status_code == 404


def test_a_symlink_out_of_the_vault_is_refused(client, workspace) -> None:
    """Dowiązanie w vaulcie nie może stać się drogą do materiałów."""
    secret = workspace.sources / "tajne.md"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("materiał źródłowy", encoding="utf-8")
    (workspace.work / "synapse" / "vault" / "link.md").symlink_to(secret)

    assert client.get("/vault/link.md").status_code == 404


def test_only_markdown_comes_out_of_the_vault(client) -> None:
    assert client.get("/vault/sem3/cokolwiek.txt").status_code == 404


def test_graf_explains_itself_when_the_viewer_is_not_built(workspace, monkeypatch, tmp_path) -> None:
    """`vendor/` jest poza gitem, więc brak viewera to normalny stan świeżego klona."""
    from studio.api import app as app_module

    monkeypatch.setattr(app_module, "VIEWER_DIST", tmp_path / "nie-zbudowany")
    app = create_app(workspace.work_db, paths=workspace, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as client:
        response = client.get("/graf")

    assert response.status_code == 503
    assert "just studio-graf" in response.text


def test_a_built_viewer_is_served_under_graf(workspace, monkeypatch, tmp_path) -> None:
    """Samo `/graf` (bez ukośnika) to adres, który człowiek wpisuje — ma prowadzić do viewera."""
    from studio.api import app as app_module

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>viewer</title>", encoding="utf-8")
    monkeypatch.setattr(app_module, "VIEWER_DIST", dist)
    app = create_app(workspace.work_db, paths=workspace, subjects=SUBJECTS, thresholds=THRESHOLDS)

    with TestClient(app) as client:
        redirect = client.get("/graf", follow_redirects=False)
        page = client.get("/graf/")

    assert redirect.status_code == 307 and redirect.headers["location"] == "/graf/"
    assert page.status_code == 200 and "viewer" in page.text
