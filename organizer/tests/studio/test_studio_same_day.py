"""Q8: „zrobione tego samego dnia w tym samym katalogu" jako podpowiedź.

EXIF w tej paczce nie istnieje (na próbce 400 obrazów: 5 ma jakikolwiek EXIF, ANI JEDEN
nie ma daty — zdjęcia przeszły przez komunikatory). Zostaje `modified_date`, który mamy
dla 48 049 z 48 049 plików.

Ale sama data w katalogu zwykle NIC nie mówi: w 6642 z 7415 katalogów wszystkie pliki mają
jeden dzień, bo to data skopiowania paczki, nie zrobienia zdjęcia. Dlatego podpowiedź
pokazujemy WYŁĄCZNIE tam, gdzie data naprawdę rozdziela katalog na sesje (w tej bazie:
899 takich grup, mediana 4 treści). Inaczej byłaby to droga parafraza zdania
„te pliki leżą w jednym katalogu", które i tak już widać.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdefgh"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)]
# sesje: w katalogu „zdjecia" dwa dni (to jest sygnał), w „skan" jeden dzień (to nie jest)
ROZKLAD = [
    (SHA["a"], "P/SEM3/zdjecia", "2019-06-12T10:00:00Z"),
    (SHA["b"], "P/SEM3/zdjecia", "2019-06-12T10:01:00Z"),
    (SHA["c"], "P/SEM3/zdjecia", "2019-06-12T10:02:00Z"),
    (SHA["d"], "P/SEM3/zdjecia", "2021-01-30T18:00:00Z"),
    (SHA["e"], "P/SEM3/zdjecia", "2021-01-30T18:05:00Z"),
    (SHA["f"], "P/SEM3/skan", "2024-09-15T12:00:00Z"),
    (SHA["g"], "P/SEM3/skan", "2024-09-15T12:00:00Z"),
    (SHA["h"], "P/SEM3/skan", "2024-09-15T12:00:00Z"),
]


@pytest.fixture
def index(tmp_path):
    db_path = tmp_path / "work" / "index.sqlite"
    conn = db.connect(db_path)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    for katalog in {"P/SEM3/zdjecia", "P/SEM3/skan"}:
        db.upsert_folder(conn, {"folder_path": katalog, "source_package": "P"})
    for sha, katalog, data in ROZKLAD:
        db.upsert_content(conn, {"sha256": sha, "content_kind": "image"})
        nazwa = f"{sha[:3]}.jpg"
        db.upsert_file(conn, {
            "source_package": "P",
            "source_relative_path": f"{katalog.split('/', 1)[1]}/{nazwa}",
            "folder_path": katalog, "filename": nazwa, "extension": ".jpg",
            "size_bytes": 4096, "sha256": sha, "modified_date": data, "status": "extracted",
        })
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "kolokwia",
            "classification_method": "heuristic", "confidence": 0.8, "run_id": "plan:x",
            "decided_at": "2026-09-01T00:00:00Z", "action": "copy", "needs_review": 1,
            "is_outdated": 0,
        })
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def _sesje(client, **params):
    return client.get("/api/clusters/same-day", params=params).json()


def test_a_day_that_splits_a_folder_is_a_session(client) -> None:
    body = _sesje(client)

    dni = {g["day"] for g in body["groups"]}
    assert dni == {"2019-06-12", "2021-01-30"}
    assert body["total"] == 2


def test_the_session_carries_its_contents(client) -> None:
    body = _sesje(client)
    czerwcowa = next(g for g in body["groups"] if g["day"] == "2019-06-12")

    assert {c["sha256"] for c in czerwcowa["contents"]} == {SHA["a"], SHA["b"], SHA["c"]}
    assert czerwcowa["folder"] == "P/SEM3/zdjecia"
    for pole in ("filename", "size_bytes", "category"):
        assert pole in czerwcowa["contents"][0]


def test_a_folder_with_one_day_says_nothing(client) -> None:
    """Jeden dzień w katalogu to data skopiowania paczki, nie sesja zdjęciowa."""
    body = _sesje(client)

    assert all(g["folder"] != "P/SEM3/skan" for g in body["groups"])


def test_a_lonely_file_is_not_a_session(client, index) -> None:
    conn = db.connect(index)
    db.upsert_content(conn, {"sha256": "9" * 64, "content_kind": "image"})
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/zdjecia/sam.jpg",
        "folder_path": "P/SEM3/zdjecia", "filename": "sam.jpg", "extension": ".jpg",
        "size_bytes": 10, "sha256": "9" * 64, "modified_date": "2020-02-02T10:00:00Z",
        "status": "extracted",
    })
    conn.commit()
    conn.close()

    body = _sesje(client)

    assert all(g["day"] != "2020-02-02" for g in body["groups"])


def test_a_whole_package_copied_in_one_day_is_not_a_session(client) -> None:
    """Górny limit jest po to, żeby „sesja" nie znaczyła „cała paczka zgrana w jeden dzień"."""
    body = _sesje(client, max_size=2)

    assert all(len(g["contents"]) <= 2 for g in body["groups"])
    assert "2019-06-12" not in {g["day"] for g in body["groups"]}


def test_sessions_can_be_narrowed_to_one_subject(client) -> None:
    assert _sesje(client, semester=3, skrot="AKO")["total"] == 2
    assert _sesje(client, semester=3, skrot="SO")["total"] == 0
