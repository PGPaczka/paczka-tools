"""Q4: zmiana nazwy pliku LEŻĄCEGO JUŻ W PACZCE, bez psucia powiązań.

Ręczne przeniesienie pliku w paczce rozjeżdża trzy rzeczy naraz: podgląd (szuka pliku
pod ścieżką z decyzji), rozmiar w notatce grafu i `verify` (widzi brak pod starą ścieżką
i nadmiarowy plik pod nową). Dlatego zmiana nazwy ma iść PRZEZ studio: dysk i baza
zmieniają się razem albo wcale.

Rozróżnienie, które robi tu całą robotę:
- plik jest już w paczce → ta operacja (dysk + `applied` + decyzja);
- plik jest dopiero zaplanowany → `POST /api/decisions/rename`, bo na dysku go nie ma.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from orglib import config, db, plan_verify
from studio.api.app import create_app

SHA_TEXT = "7" * 64
SHA_INNY = "8" * 64
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}
SUBJECT = config.Subject(
    semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
    instancja=None, strumien=None, profil=None, katedra=None,
)
KATALOG = f"{SUBJECT.target_dir}/wyklad"
STARA = f"{KATALOG}/wyklad_1.txt"
SASIAD = f"{KATALOG}/zajete.txt"
TRESC = "pierwsza linia materiału\ndruga linia\n"


@pytest.fixture
def workspace(tmp_path):
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    (paths.target_repo / KATALOG).mkdir(parents=True)
    (paths.target_repo / STARA).write_text(TRESC, encoding="utf-8")
    (paths.target_repo / SASIAD).write_text("inny materiał\n", encoding="utf-8")
    paths.work_thumbnails.mkdir(parents=True)

    conn = db.connect(paths.work_db)
    for sha, sciezka in ((SHA_TEXT, STARA), (SHA_INNY, SASIAD)):
        db.upsert_content(conn, {"sha256": sha, "content_kind": "text"})
        db.upsert(conn, "applied", {
            "target_relative_path": sciezka, "sha256": sha, "action": "copy",
            "plan_hash": "ground_truth:scan", "applied_at": "2026-09-01T00:00:00Z",
        }, conflict=("target_relative_path",))
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": "wyklad",
            "target_relative_path": sciezka, "classification_method": "manual",
            "confidence": 1.0, "run_id": "ground_truth", "decided_at": "2026-09-01T00:00:00Z",
            "action": "copy", "needs_review": 0, "is_outdated": 0,
        })
    conn.commit()
    conn.close()
    return paths


@pytest.fixture
def client(workspace):
    app = create_app(workspace.work_db, paths=workspace, subjects=[SUBJECT], thresholds=THRESHOLDS)
    with TestClient(app) as c:
        yield c


def _rename(client, sciezka: str, nazwa: str):
    return client.post("/api/package/rename", json={
        "target_relative_path": sciezka, "filename": nazwa,
    })


def _baza(workspace) -> sqlite3.Connection:
    conn = db.connect(workspace.work_db)
    return conn


# --- szczęśliwa ścieżka -----------------------------------------------------

def test_file_moves_on_disk(client, workspace) -> None:
    odpowiedz = _rename(client, STARA, "wyklad_01_wstep.txt")

    assert odpowiedz.status_code == 200
    nowa = workspace.target_repo / KATALOG / "wyklad_01_wstep.txt"
    assert nowa.read_text(encoding="utf-8") == TRESC
    assert not (workspace.target_repo / STARA).exists()


def test_database_follows_the_file(client, workspace) -> None:
    """Dysk i baza zmieniają się razem — inaczej `verify` i podgląd kłamią."""
    _rename(client, STARA, "nowa_nazwa.txt")

    conn = _baza(workspace)
    applied = conn.execute("SELECT target_relative_path FROM applied WHERE sha256 = ?",
                           (SHA_TEXT,)).fetchone()
    decyzja = conn.execute("SELECT target_relative_path FROM classifications WHERE sha256 = ?",
                           (SHA_TEXT,)).fetchone()
    conn.close()

    assert applied["target_relative_path"] == f"{KATALOG}/nowa_nazwa.txt"
    assert decyzja["target_relative_path"] == f"{KATALOG}/nowa_nazwa.txt"


def test_verify_stays_green_after_the_rename(client, workspace) -> None:
    """Najważniejszy test tego kroku: `verify` liczy ground truth z `applied`.

    Gdyby baza została ze starą ścieżką, kontrola zobaczyłaby plik spoza planu
    i spoza ground trutha — czyli paczkę „do niezacommitowania".
    """
    _rename(client, STARA, "po_zmianie.txt")

    conn = _baza(workspace)
    ground_truth = [str(row["target_relative_path"]) for row in conn.execute(
        "SELECT target_relative_path FROM applied WHERE plan_hash LIKE 'ground_truth:%'"
    )]
    conn.close()

    extras = plan_verify.tree_extras([], paths=workspace, subject=SUBJECT, ground_truth=ground_truth)

    assert extras == []


def test_preview_still_works_after_the_rename(client) -> None:
    """Podgląd szuka pliku po ścieżce z decyzji — musi trafić w nową nazwę."""
    _rename(client, STARA, "podglad.txt")

    body = client.get(f"/api/preview/{SHA_TEXT}").json()

    assert "pierwsza linia materiału" in (body["text_head"] or "")


def test_renaming_to_the_same_name_changes_nothing(client, workspace) -> None:
    body = _rename(client, STARA, "wyklad_1.txt").json()

    assert body["changed"] is False
    assert (workspace.target_repo / STARA).is_file()


# --- czego zrobić nie wolno -------------------------------------------------

def test_taken_name_is_refused(client, workspace) -> None:
    odpowiedz = _rename(client, STARA, "zajete.txt")

    assert odpowiedz.status_code == 409
    assert (workspace.target_repo / STARA).is_file(), "przy odmowie plik ma zostać na miejscu"
    assert (workspace.target_repo / SASIAD).read_text(encoding="utf-8") == "inny materiał\n"


def test_unknown_path_is_404(client) -> None:
    assert _rename(client, f"{KATALOG}/nie_ma_takiego.txt", "cokolwiek.txt").status_code == 404


def test_path_outside_the_package_is_refused(client) -> None:
    odpowiedz = _rename(client, "../sekret.txt", "cokolwiek.txt")

    assert odpowiedz.status_code in (404, 422)


@pytest.mark.parametrize("nazwa", ["inne/x.txt", "..", "", "CON.txt", "plik?.txt"])
def test_bad_names_are_refused(client, nazwa) -> None:
    """Te same reguły co przy nazwach w planie — jedno prawo dla obu dróg."""
    assert _rename(client, STARA, nazwa).status_code == 422


def test_a_file_missing_from_disk_is_not_silently_renamed(client, workspace) -> None:
    (workspace.target_repo / STARA).unlink()

    odpowiedz = _rename(client, STARA, "cokolwiek.txt")

    assert odpowiedz.status_code == 404
    conn = _baza(workspace)
    zostalo = conn.execute("SELECT target_relative_path FROM applied WHERE sha256 = ?",
                           (SHA_TEXT,)).fetchone()["target_relative_path"]
    conn.close()
    assert zostalo == STARA, "baza nie może ruszyć, skoro dysk się nie ruszył"


def test_a_failed_move_leaves_nothing_half_done(client, workspace, monkeypatch) -> None:
    """Dysk i baza muszą się rozjechać NIGDY — nawet gdy przeniesienie padnie."""
    import os

    def padnij(*args, **kwargs):
        raise OSError("dysk tylko do odczytu")

    monkeypatch.setattr(os, "replace", padnij)

    odpowiedz = _rename(client, STARA, "nie_uda_sie.txt")

    assert odpowiedz.status_code >= 400
    assert (workspace.target_repo / STARA).is_file()
    conn = _baza(workspace)
    zostalo = conn.execute("SELECT target_relative_path FROM applied WHERE sha256 = ?",
                           (SHA_TEXT,)).fetchone()["target_relative_path"]
    conn.close()
    assert zostalo == STARA


# --- plan zbudowany przed zmianą --------------------------------------------

def test_rename_reports_a_stale_plan(client, workspace) -> None:
    """Plan na dysku ma starą ścieżkę i `plan_hash`, więc nie wolno go edytować.

    Zamiast udawać, że wszystko gra, operacja mówi wprost: zbuduj plan od nowa.
    """
    conn = _baza(workspace)
    db.upsert(conn, "plan_items", {
        "sha256": SHA_TEXT, "target_relative_path": STARA, "action": "copy",
        "status": "planned", "plan_run_id": "plan:x",
    }, conflict=("sha256", "target_relative_path"))
    conn.commit()
    conn.close()

    body = _rename(client, STARA, "po_planie.txt").json()

    assert body["plan_stale"] is True
