"""Q2: konflikty ścieżek docelowych widoczne i do naprawienia w studiu.

Bramka planu wykrywa `kolizja_celu` i `nadpisanie_ground_truth`, ale dopiero przy
`validate` i wyłącznie jako tekst — naprawiało się je poza studiem. Ta lista liczy
konflikty z ŻYWEJ bazy (`classifications`), a nie z pliku planu, żeby zmiana nazwy
gasiła konflikt od razu, bez czekania na ponowne zbudowanie planu.

Dwa rodzaje konfliktu, obie naprawialne tym samym ruchem (zmiana nazwy):
- `plan` — dwie zaplanowane treści celują w jedną ścieżkę;
- `applied` — zaplanowana treść celuje w plik, który już leży w paczce.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcdef"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECTS = [
    config.Subject(semester=3, skrot="AKO", nazwa="Architektura_Komputerów",
                   forms=("W", "C"), aliases=(), instancja=None, strumien=None,
                   profil=None, katedra=None),
    config.Subject(semester=3, skrot="SO", nazwa="Systemy_Operacyjne",
                   forms=("W",), aliases=(), instancja=None, strumien=None,
                   profil=None, katedra=None),
]
AKO = "paczka/SEM3/AKO/wyklad"


def _klas(sha, target, *, skrot="AKO", action="copy"):
    return {
        "sha256": sha, "semester": 3, "subject_key": skrot, "category": "wyklad",
        "target_relative_path": target, "classification_method": "heuristic",
        "confidence": 0.8, "run_id": "plan:x", "decided_at": "2026-09-01T00:00:00Z",
        "action": action, "needs_review": 0, "is_outdated": 0,
    }


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
            "size_bytes": 100 + i, "sha256": sha, "status": "extracted",
        })
    # a i b biją się o jeden plik; c stoi obok i nie ma z tym nic wspólnego
    db.upsert_classification(conn, _klas(SHA["a"], f"{AKO}/wyklad1.pdf"))
    db.upsert_classification(conn, _klas(SHA["b"], f"{AKO}/Wyklad1.pdf"))
    db.upsert_classification(conn, _klas(SHA["c"], f"{AKO}/wyklad2.pdf"))
    # d celuje w plik, który już leży w paczce (ground truth z `applied`)
    db.upsert_classification(conn, _klas(SHA["d"], f"{AKO}/lezy_juz.pdf"))
    db.upsert(conn, "applied", {
        "sha256": SHA["e"], "target_relative_path": f"{AKO}/lezy_juz.pdf",
        "action": "copy", "plan_hash": "h", "applied_at": "2026-09-01T00:00:00Z",
    }, conflict=("target_relative_path",))
    # pominięte nie tworzy konfliktu: ono nigdzie nie trafi
    db.upsert_classification(conn, _klas(SHA["f"], f"{AKO}/wyklad2.pdf", action="skip"))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(index):
    app = create_app(index, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def _konflikty(client, **params):
    return client.get("/api/plan/conflicts", params=params).json()


# --- co jest konfliktem -----------------------------------------------------

def test_two_contents_on_one_path_are_a_conflict(client) -> None:
    body = _konflikty(client)

    plan = [k for k in body["conflicts"] if k["kind"] == "plan"]
    assert len(plan) == 1
    assert {c["sha256"] for c in plan[0]["contents"]} == {SHA["a"], SHA["b"]}


def test_letter_case_does_not_hide_a_conflict(client) -> None:
    """`wyklad1.pdf` i `Wyklad1.pdf` to na Windowsie jeden plik, czyli cicha strata."""
    plan = [k for k in _konflikty(client)["conflicts"] if k["kind"] == "plan"]

    assert len(plan) == 1, "różnica samej wielkości liter została uznana za dwie ścieżki"


def test_a_path_already_in_the_package_is_a_conflict(client) -> None:
    applied = [k for k in _konflikty(client)["conflicts"] if k["kind"] == "applied"]

    assert len(applied) == 1
    assert applied[0]["path"].endswith("lezy_juz.pdf")
    assert [c["sha256"] for c in applied[0]["contents"]] == [SHA["d"]]
    assert applied[0]["applied_sha256"] == SHA["e"]


def test_skipped_content_does_not_collide(client) -> None:
    """`skip` nigdzie nie trafi, więc nie ma o co się bić — inaczej lista byłaby pełna duchów."""
    sciezki = [k["path"] for k in _konflikty(client)["conflicts"]]

    assert not any(p.endswith("wyklad2.pdf") for p in sciezki)


def test_conflicts_carry_what_is_needed_to_choose(client) -> None:
    """Widok ma dać wybrać bez wchodzenia w każdą treść z osobna."""
    plan = [k for k in _konflikty(client)["conflicts"] if k["kind"] == "plan"][0]

    tresc = plan["contents"][0]
    for pole in ("sha256", "filename", "source_relative_path", "size_bytes", "confidence"):
        assert pole in tresc, f"brak pola {pole}"


# --- zakres -----------------------------------------------------------------

def test_conflicts_can_be_narrowed_to_one_subject(client) -> None:
    assert _konflikty(client, semester=3, skrot="AKO")["total"] == 2
    assert _konflikty(client, semester=3, skrot="SO")["total"] == 0


def test_total_counts_conflicts_not_contents(client) -> None:
    body = _konflikty(client)

    assert body["total"] == len(body["conflicts"]) == 2


# --- naprawa w miejscu ------------------------------------------------------

def test_renaming_one_side_clears_the_conflict(client) -> None:
    """To jest cały sens liczenia z bazy: naprawa widać od razu, bez ponownego planu."""
    client.post("/api/decisions/rename", json={"sha256": SHA["b"], "filename": "wyklad1b.pdf"})

    body = _konflikty(client)

    assert [k for k in body["conflicts"] if k["kind"] == "plan"] == []
