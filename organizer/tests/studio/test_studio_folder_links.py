"""Q3: powiązywanie katalogów z poziomu studia.

Zapis stoi na `orglib.folder_links` (tam jest kontrakt pary i to, dlaczego powiązanie
NIE jest `duplicate_of`). Tutaj pilnujemy warstwy studia: przeglądania katalogów do
wyboru i czterech ruchów — pokaż, powiąż, wypisz, rozwiąż.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api.app import create_app

THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)]
KATALOGI = [
    ("P1/AKO2020", "P1", 0, None),
    ("P1/AKO2020/wyklady", "P1", 12, None),
    ("P2/ako_stare", "P2", 0, None),
    ("P2/ako_stare/w", "P2", 9, None),
    ("P2/kopia_wykladow", "P2", 12, "P1/AKO2020/wyklady"),
]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    for paczka in ("P1", "P2"):
        db.upsert(conn, "source_packages", {"package_name": paczka}, conflict=("package_name",))
    # Duplikat zapisujemy w drugim przejściu — FK wymaga, żeby cel istniał wcześniej.
    for sciezka, paczka, plikow, _ in KATALOGI:
        db.upsert_folder(conn, {
            "folder_path": sciezka, "source_package": paczka,
            "file_count": plikow, "total_bytes": plikow * 1000,
        })
    for sciezka, paczka, plikow, duplikat in KATALOGI:
        if duplikat:
            db.upsert_folder(conn, {
                "folder_path": sciezka, "source_package": paczka,
                "file_count": plikow, "total_bytes": plikow * 1000, "duplicate_of": duplikat,
            })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def _powiaz(client, a, b, **extra):
    return client.post("/api/folders/links", json={"folder_a": a, "folder_b": b, **extra})


# --- przeglądanie katalogów do wyboru ---------------------------------------

def test_folders_can_be_browsed(client) -> None:
    body = client.get("/api/folders").json()

    assert body["total"] == len(KATALOGI)
    assert {f["folder_path"] for f in body["folders"]} == {k[0] for k in KATALOGI}


def test_folders_can_be_searched_by_fragment(client) -> None:
    """Paczek jest kilkanaście, katalogów tysiące — bez szukania wybór jest bezużyteczny."""
    body = client.get("/api/folders", params={"q": "wyklad"}).json()

    assert {f["folder_path"] for f in body["folders"]} == {"P1/AKO2020/wyklady", "P2/kopia_wykladow"}


def test_folder_row_says_what_is_inside(client) -> None:
    body = client.get("/api/folders", params={"q": "AKO2020/wyklady"}).json()
    katalog = body["folders"][0]

    assert katalog["file_count"] == 12
    assert katalog["source_package"] == "P1"
    assert katalog["duplicate_of"] is None


def test_automatic_duplicate_is_visible_as_such(client) -> None:
    """Automatyczny dedup i ręczne powiązanie to dwie różne rzeczy — widok ma je rozróżniać."""
    body = client.get("/api/folders", params={"q": "kopia"}).json()

    assert body["folders"][0]["duplicate_of"] == "P1/AKO2020/wyklady"


# --- powiązywanie -----------------------------------------------------------

def test_linking_two_folders(client) -> None:
    odpowiedz = _powiaz(client, "P2/ako_stare/w", "P1/AKO2020/wyklady", note="ten sam wykład")

    assert odpowiedz.status_code == 200
    wynik = odpowiedz.json()
    assert wynik["folder_a"] < wynik["folder_b"]
    assert wynik["kind"] == "duplicate"


def test_links_are_listed_and_filtered_by_folder(client) -> None:
    _powiaz(client, "P1/AKO2020/wyklady", "P2/ako_stare/w")
    _powiaz(client, "P1/AKO2020", "P2/ako_stare", kind="related")

    wszystkie = client.get("/api/folders/links").json()
    jeden = client.get("/api/folders/links", params={"folder": "P2/ako_stare"}).json()

    assert wszystkie["total"] == 2
    assert jeden["total"] == 1 and jeden["links"][0]["kind"] == "related"


def test_a_folder_row_carries_its_links(client) -> None:
    """Widok ma od razu pokazać, że katalog jest już z czymś powiązany."""
    _powiaz(client, "P1/AKO2020/wyklady", "P2/ako_stare/w")

    katalog = client.get("/api/folders", params={"q": "AKO2020/wyklady"}).json()["folders"][0]

    assert katalog["linked_to"] == ["P2/ako_stare/w"]


def test_unlinking_works_in_either_order(client) -> None:
    _powiaz(client, "P1/AKO2020/wyklady", "P2/ako_stare/w")

    usuniecie = client.request("DELETE", "/api/folders/links", params={
        "folder_a": "P2/ako_stare/w", "folder_b": "P1/AKO2020/wyklady",
    })

    assert usuniecie.status_code == 200
    assert client.get("/api/folders/links").json()["total"] == 0


def test_unlinking_something_that_is_not_linked_is_404(client) -> None:
    odpowiedz = client.request("DELETE", "/api/folders/links", params={
        "folder_a": "P1/AKO2020", "folder_b": "P2/ako_stare",
    })

    assert odpowiedz.status_code == 404


# --- czego zrobić nie wolno -------------------------------------------------

def test_unknown_folder_is_404(client) -> None:
    assert _powiaz(client, "P1/AKO2020", "P2/nie_ma_takiego").status_code == 404


def test_folder_linked_to_itself_is_422(client) -> None:
    assert _powiaz(client, "P1/AKO2020", "P1/AKO2020").status_code == 422


def test_unknown_kind_is_422(client) -> None:
    assert _powiaz(client, "P1/AKO2020", "P2/ako_stare", kind="wymyslony").status_code == 422
