"""Q2: zmiana nazwy pliku docelowego jako osobna operacja.

Dotąd nazwę zmieniało się edycją CAŁEJ ścieżki docelowej (`t` w kolejce decyzji):
łatwo było przy okazji przenieść plik do innego katalogu albo wpisać nazwę, którą
bramka odrzuci dopiero przy `validate`. Ta operacja robi jedną rzecz — zmienia
nazwę w tym samym katalogu — i sprawdza to, co inaczej wyszłoby dopiero w bramce:
nazwy niemożliwe na Windowsie i dwie treści celujące w tę samą ścieżkę.
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
KATALOG = "paczka/SEM3/AKO/wyklad"


def _klasyfikacja(sha: str, target: str | None, **kw) -> dict:
    row = {
        "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "wyklad",
        "classification_method": kw.get("method", "heuristic"), "confidence": 0.8,
        "run_id": kw.get("run_id", "plan:x"), "decided_at": "2026-09-01T00:00:00Z",
        "action": kw.get("action", "copy"), "needs_review": 1, "is_outdated": 0,
    }
    if target is not None:
        row["target_relative_path"] = target
    return row


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
    db.upsert_classification(conn, _klasyfikacja(SHA["a"], f"{KATALOG}/p0.pdf"))
    db.upsert_classification(conn, _klasyfikacja(SHA["b"], f"{KATALOG}/Wyklad1.pdf"))
    # treść zaklasyfikowana, ale bez ścieżki docelowej — nie ma czego zmieniać
    db.upsert_classification(conn, _klasyfikacja(SHA["c"], None, action="skip"))
    # ta sama nazwa, ale w katalogu ćwiczeń — to NIE jest kolizja
    db.upsert_classification(conn, _klasyfikacja(SHA["d"], "paczka/SEM3/AKO/cwiczenia/wspolna.pdf"))
    # materiał leżący już w paczce: ręczna decyzja go nie dotyka
    db.upsert_classification(conn, _klasyfikacja(
        SHA["f"], f"{KATALOG}/gt.pdf", method="manual", run_id=GROUND_TRUTH_RUN_ID,
    ))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def _rename(client, sha: str, filename: str):
    return client.post("/api/decisions/rename", json={"sha256": sha, "filename": filename})


def _cel(client, sha: str) -> str | None:
    return client.get(f"/api/items/{sha}").json()["item"]["target_relative_path"]


# --- szczęśliwa ścieżka -----------------------------------------------------

def test_rename_changes_the_name_and_keeps_the_directory(client) -> None:
    body = _rename(client, SHA["a"], "wyklad_01_wstep.pdf").json()

    assert body["target_relative_path"] == f"{KATALOG}/wyklad_01_wstep.pdf"
    assert body["changed"] is True
    assert _cel(client, SHA["a"]) == f"{KATALOG}/wyklad_01_wstep.pdf"


def test_rename_is_an_ordinary_manual_decision(client) -> None:
    """Zapis idzie tą samą drogą co reszta decyzji — inaczej `apply` by go nie zobaczył."""
    _rename(client, SHA["a"], "nowa.pdf")

    pozycja = client.get(f"/api/items/{SHA['a']}").json()["item"]
    historia = client.get("/api/decisions/history").json()

    assert pozycja["classification_method"] == "manual"
    assert pozycja["needs_review"] == 0
    assert any(d["sha256"] == SHA["a"] for d in historia["decisions"])


def test_rename_to_the_same_name_writes_nothing(client) -> None:
    """Bez tego samo otwarcie i zatwierdzenie pola zamieniałoby heurystykę w decyzję człowieka."""
    body = _rename(client, SHA["a"], "p0.pdf").json()

    assert body["changed"] is False
    assert client.get("/api/decisions/history").json()["decisions"] == []
    assert client.get(f"/api/items/{SHA['a']}").json()["item"]["classification_method"] == "heuristic"


# --- czego ta operacja nie robi --------------------------------------------

@pytest.mark.parametrize("nazwa", ["inne/x.pdf", "../x.pdf", "..", ".", "", "   "])
def test_rename_takes_a_name_not_a_path(client, nazwa) -> None:
    """Przenoszenie to osobna decyzja (pełna ścieżka) — tu zmienia się wyłącznie nazwa."""
    odpowiedz = _rename(client, SHA["a"], nazwa)

    assert odpowiedz.status_code == 422
    assert _cel(client, SHA["a"]) == f"{KATALOG}/p0.pdf"


@pytest.mark.parametrize("nazwa", ["kol1?.pdf", "raport:1.pdf", "CON.pdf", "wyklad .pdf"])
def test_rename_refuses_names_windows_would_lose(client, nazwa) -> None:
    """Te same reguły co w bramce planu (`plan_lint`), tylko zgłoszone od razu."""
    assert _rename(client, SHA["a"], nazwa).status_code == 422


def test_rename_without_a_target_says_there_is_nothing_to_rename(client) -> None:
    odpowiedz = _rename(client, SHA["c"], "cokolwiek.pdf")

    assert odpowiedz.status_code == 404
    assert "ścieżki docelowej" in odpowiedz.json()["detail"]


def test_rename_of_an_unknown_content_is_404(client) -> None:
    assert _rename(client, SHA["e"], "cokolwiek.pdf").status_code == 404


def test_ground_truth_is_not_renamed(client) -> None:
    odpowiedz = _rename(client, SHA["f"], "inna.pdf")

    assert odpowiedz.status_code == 409
    assert "ground_truth" in odpowiedz.json()["detail"]
    assert _cel(client, SHA["f"]) == f"{KATALOG}/gt.pdf"


# --- kolizje ----------------------------------------------------------------

def test_two_contents_cannot_take_the_same_path(client) -> None:
    """Bramka wykrywa to jako `kolizja_celu` dopiero przy `validate` — tu mówimy od razu."""
    odpowiedz = _rename(client, SHA["a"], "Wyklad1.pdf")

    assert odpowiedz.status_code == 409
    assert SHA["b"][:12] in odpowiedz.json()["detail"]
    assert _cel(client, SHA["a"]) == f"{KATALOG}/p0.pdf"


def test_collision_ignores_letter_case(client) -> None:
    """Paczka jedzie do repo klonowanego też na Windowsie: `wyklad1` i `Wyklad1` to jeden plik."""
    assert _rename(client, SHA["a"], "wyklad1.pdf").status_code == 409


def test_collision_is_checked_only_inside_the_target_directory(client) -> None:
    """Ta sama nazwa w innym katalogu to nie kolizja — inaczej paczka miałaby jedną przestrzeń nazw."""
    odpowiedz = _rename(client, SHA["a"], "wspolna.pdf")

    assert odpowiedz.status_code == 200
    assert _cel(client, SHA["a"]) == f"{KATALOG}/wspolna.pdf"


def test_rename_accepts_only_post(client) -> None:
    trasy = [r for r in client.app.routes if getattr(r, "path", None) == "/api/decisions/rename"]

    assert trasy, "endpoint zmiany nazwy zniknął z aplikacji"
    assert trasy[0].methods == {"POST"}
