"""Q7: kolejka decyzji mówi, że ta sama treść leży pod kilkoma nazwami.

Widać to dziś dopiero po wejściu w szczegóły treści, a to jest informacja, która
zmienia decyzję: „ten sam plik pod czterema nazwami" znaczy, że nazwa w paczce jest
wyborem, a nie faktem.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api.app import create_app

SHA_WIELE = "1" * 64
SHA_JEDNA = "2" * 64
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)]
NAZWY = [
    "Kopia zerówka2013_B.jpg",
    "zerówka2013_B.jpg",
    "AiSD_2012_egzamin_zerowy_grupa_B.jpg",
]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    db.upsert_content(conn, {"sha256": SHA_WIELE, "content_kind": "image"})
    for i, nazwa in enumerate(NAZWY):
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": f"SEM3/kat{i}/{nazwa}",
            "folder_path": "P/SEM3", "filename": nazwa, "extension": ".jpg",
            "size_bytes": 100, "sha256": SHA_WIELE, "status": "extracted",
        })
    db.upsert_content(conn, {"sha256": SHA_JEDNA, "content_kind": "pdf"})
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/sam.pdf",
        "folder_path": "P/SEM3", "filename": "sam.pdf", "extension": ".pdf",
        "size_bytes": 100, "sha256": SHA_JEDNA, "status": "extracted",
    })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def test_item_lists_all_its_names(client) -> None:
    body = client.get(f"/api/items/{SHA_WIELE}").json()

    assert body["names"] == sorted(NAZWY)


def test_item_suggests_the_most_telling_name(client) -> None:
    body = client.get(f"/api/items/{SHA_WIELE}").json()

    assert body["suggested_name"] == "AiSD_2012_egzamin_zerowy_grupa_B.jpg"


def test_a_single_name_needs_no_suggestion(client) -> None:
    """Jedna nazwa to nie wybór — podpowiedź byłaby tylko szumem w panelu."""
    body = client.get(f"/api/items/{SHA_JEDNA}").json()

    assert body["names"] == ["sam.pdf"]
    assert body["suggested_name"] is None
