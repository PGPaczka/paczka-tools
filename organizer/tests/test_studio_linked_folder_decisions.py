"""Q3: ręczne powiązanie katalogów ma skutek, a nie tylko wpis w bazie.

Decyzja hurtem po katalogu („to wszystko to laboratoria") jest miejscem, w którym
powiązanie się opłaca: jeśli człowiek powiedział, że dwa katalogi to ten sam materiał,
to decyzja o jednym jest propozycją dla drugiego.

Skutek jest OPT-IN i widoczny przed zapisem: podgląd mówi, ile pozycji dojdzie
z katalogów powiązanych. Cicha decyzja o cudzym katalogu byłaby gorsza niż jej brak.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db, folder_links
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcd"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)]
KAT_A = "P1/AKO2020/wyklady"
KAT_B = "P2/ako_stare/w"


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    for paczka in ("P1", "P2"):
        db.upsert(conn, "source_packages", {"package_name": paczka}, conflict=("package_name",))
    for sciezka, paczka in ((KAT_A, "P1"), (KAT_B, "P2"), ("P2/inne", "P2")):
        db.upsert_folder(conn, {"folder_path": sciezka, "source_package": paczka, "file_count": 1})
    rozklad = [(SHA["a"], KAT_A, "P1", "AKO2020/wyklady/w1.pdf"),
               (SHA["b"], KAT_A, "P1", "AKO2020/wyklady/w2.pdf"),
               (SHA["c"], KAT_B, "P2", "ako_stare/w/stary.pdf"),
               (SHA["d"], "P2/inne", "P2", "inne/luzem.pdf")]
    for sha, katalog, paczka, sciezka in rozklad:
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": paczka, "source_relative_path": sciezka,
            "folder_path": katalog, "filename": sciezka.rsplit("/", 1)[-1],
            "extension": ".pdf", "size_bytes": 10, "sha256": sha, "status": "extracted",
        })
    folder_links.link(conn, KAT_A, KAT_B, decided_by="test")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def test_preview_says_which_folders_are_linked(client) -> None:
    """Zanim cokolwiek zapiszemy, widok ma powiedzieć, co jeszcze wisi na tej decyzji."""
    body = client.get("/api/decisions/by-folder", params={"folder": KAT_A}).json()

    assert body["linked_folders"] == [KAT_B]
    assert body["total"] == 2, "bez zgody powiązany katalog NIE wchodzi do podglądu"


def test_preview_can_include_the_linked_folder(client) -> None:
    body = client.get("/api/decisions/by-folder", params={
        "folder": KAT_A, "include_linked": True,
    }).json()

    assert body["total"] == 3
    assert {i["sha256"] for i in body["items"]} == {SHA["a"], SHA["b"], SHA["c"]}


def _zdecydowane(client) -> set[str]:
    """Treści z zapisaną ręczną decyzją.

    Patrzymy na `manual_decisions`, a nie na `classifications.action`: `skip` dla treści,
    która nie ma jeszcze klasyfikacji, nie ma czego zaktualizować — decyzja istnieje,
    ale kolumna `action` zostaje pusta. To zastane zachowanie `record_batch`.
    """
    return {d["sha256"] for d in client.get("/api/decisions/history").json()["decisions"]}


def test_bulk_decision_stays_in_one_folder_by_default(client) -> None:
    """Domyślnie decyzja dotyczy TEGO katalogu — powiązanie nie może działać po cichu."""
    client.post("/api/decisions/by-folder", json={"folder": KAT_A, "decision_type": "skip"})

    assert _zdecydowane(client) == {SHA["a"], SHA["b"]}


def test_bulk_decision_can_follow_the_link(client) -> None:
    wynik = client.post("/api/decisions/by-folder", json={
        "folder": KAT_A, "decision_type": "skip", "include_linked": True,
    }).json()

    assert wynik["count"] == 3
    # Katalog niepowiązany zostaje nietknięty — powiązanie jest parą, nie siecią.
    assert _zdecydowane(client) == {SHA["a"], SHA["b"], SHA["c"]}


def test_an_unlinked_folder_reports_no_partners(client) -> None:
    body = client.get("/api/decisions/by-folder", params={"folder": "P2/inne"}).json()

    assert body["linked_folders"] == []
