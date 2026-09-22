"""S1.3: podgląd treści w studiu — głowa tekstu, strona PDF, miniatura.

Powstało po tym, jak podgląd „zrobiony” w S1.3 nie pokazywał NICZEGO na realnych
danych, a testy świeciły na zielono: endpoint sklejał ``content.extracted_text_path``
jak ścieżkę wobec katalogu roboczego procesu, podczas gdy etap extract (B2) zapisuje
ją **względem ``work``**, a jedyny test tej ścieżki wpisywał do bazy ścieżkę
bezwzględną — czyli kontrakt, którego potok nigdy nie produkuje.

Drugi powód: podgląd jest jedyną drogą, którą aplikacja sięga po materiały, więc
ma chodzić przez wspólny helper containmentu (``config.resolve_within``). Wpis
w bazie prowadzący poza ``work`` — bezwzględny, przez ``..`` albo przez dowiązanie —
to błąd danych, a nie prośba o przeczytanie czegokolwiek (``studio/AGENTS.md``, reguła 4).
"""

from __future__ import annotations

import pymupdf
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from orglib import config, db
from studio.api.app import create_app

SHA = {name: name * 64 for name in "abcd"}
THRESHOLDS = {"confidence": {"auto_apply": 0.90, "review_min": 0.70}}

SUBJECTS = [
    config.Subject(
        semester=3, skrot="AKO", nazwa="Architektura_Komputerów", forms=("W",), aliases=(),
        instancja=None, strumien=None, profil=None, katedra=None,
    )
]

TEXT = "Architektura Komputerów — wykład 1\nPotokowość i hazardy."


def _pdf(path, text: str) -> None:
    """Minimalny, prawdziwy PDF — podgląd ma renderować stronę, nie atrapę."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=200)
        page.insert_text((20, 40), text)
        document.save(path)


@pytest.fixture
def workspace(tmp_path):
    """Workspace w kształcie, jaki daje `config/paths.yaml`: sources + work obok siebie."""
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work", media=tmp_path / "media",
        target_repo=tmp_path / "target", target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "extracted_text",
        work_thumbnails=tmp_path / "work" / "thumbnails",
    )
    paths.work_extracted_text.mkdir(parents=True)
    paths.work_thumbnails.mkdir(parents=True)
    (paths.sources / "P" / "SEM3").mkdir(parents=True)

    _pdf(paths.sources / "P" / "SEM3" / "w1.pdf", TEXT.splitlines()[0])
    # Prawdziwy obraz, nie wklejone bajty: podgląd ma realnie przejść przez Pillow.
    Image.new("RGB", (40, 30), (32, 64, 128)).save(paths.sources / "P" / "SEM3" / "skan.png")

    conn = db.connect(paths.work_db)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    # a: PDF z wyekstrahowanym tekstem (ścieżka WZGLĘDEM work — kontrakt B2)
    (paths.work_extracted_text / f"{SHA['a']}.txt").write_text(TEXT, encoding="utf-8")
    db.upsert_content(conn, {
        "sha256": SHA["a"], "content_kind": "pdf",
        "extracted_text_path": f"extracted_text/{SHA['a']}.txt",
    })
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/w1.pdf", "folder_path": "P/SEM3",
        "filename": "w1.pdf", "extension": ".pdf", "size_bytes": 100,
        "sha256": SHA["a"], "status": "extracted",
    })
    # b: obraz bez tekstu
    db.upsert_content(conn, {"sha256": SHA["b"], "content_kind": "image"})
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/skan.png", "folder_path": "P/SEM3",
        "filename": "skan.png", "extension": ".png", "size_bytes": 100,
        "sha256": SHA["b"], "status": "extracted",
    })
    # c: treść bez żadnego pliku na dysku (wpis prowenancyjny)
    db.upsert_content(conn, {"sha256": SHA["c"], "content_kind": "pdf"})
    db.upsert_file(conn, {
        "source_package": "P", "source_relative_path": "SEM3/nie-ma.pdf", "folder_path": "P/SEM3",
        "filename": "nie-ma.pdf", "extension": ".pdf", "size_bytes": 100,
        "sha256": SHA["c"], "status": "extracted",
    })
    conn.commit()
    conn.close()
    return paths


@pytest.fixture
def client(workspace):
    app = create_app(workspace.work_db, paths=workspace, subjects=SUBJECTS, thresholds=THRESHOLDS)
    with TestClient(app) as test_client:
        yield test_client


def _set_text_path(workspace, sha: str, value: str) -> None:
    conn = db.connect(workspace.work_db)
    conn.execute("UPDATE content SET extracted_text_path = ? WHERE sha256 = ?", (value, sha))
    conn.commit()
    conn.close()


def test_text_head_comes_from_the_path_the_pipeline_actually_writes(client) -> None:
    """B2 zapisuje ścieżkę WZGLĘDEM `work` — po tym wpadł podgląd w S1.3."""
    body = client.get(f"/api/preview/{SHA['a']}").json()

    assert body["has_text"] is True
    assert "Potokowość" in body["text_head"]


def test_an_absolute_path_in_the_index_is_refused(client, workspace, tmp_path) -> None:
    """Ścieżka bezwzględna w bazie to błąd danych, nie prośba o odczyt."""
    outside = tmp_path / "poza-work.txt"
    outside.write_text("tego nie wolno przeczytać", encoding="utf-8")
    _set_text_path(workspace, SHA["a"], str(outside))

    body = client.get(f"/api/preview/{SHA['a']}").json()

    assert body["has_text"] is False and body["text_head"] is None


def test_a_dotdot_path_cannot_climb_out_of_work(client, workspace, tmp_path) -> None:
    (tmp_path / "sekret.txt").write_text("nie czytaj", encoding="utf-8")
    _set_text_path(workspace, SHA["a"], "../sekret.txt")

    body = client.get(f"/api/preview/{SHA['a']}").json()

    assert body["has_text"] is False and body["text_head"] is None


def test_a_symlink_out_of_work_is_refused(client, workspace) -> None:
    """Dokładnie ta boczna ścieżka do materiałów, której pilnuje guard."""
    target = workspace.sources / "P" / "SEM3" / "tajne.txt"
    target.write_text("materiał źródłowy", encoding="utf-8")
    link = workspace.work_extracted_text / "link.txt"
    link.symlink_to(target)
    _set_text_path(workspace, SHA["a"], "extracted_text/link.txt")

    body = client.get(f"/api/preview/{SHA['a']}").json()

    assert body["has_text"] is False and body["text_head"] is None


def test_preview_renders_the_first_page_of_a_pdf(client) -> None:
    """Decyzja „co to za plik” ma zapadać po obejrzeniu strony, nie nazwy pliku."""
    response = client.get(f"/api/preview/{SHA['a']}/image")

    assert response.status_code == 200
    # JPEG, nie PNG: przy 1000 px ta sama strona to 110 KiB zamiast 1006 KiB.
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8\xff")


def test_preview_serves_an_image_content_as_a_picture(client) -> None:
    response = client.get(f"/api/preview/{SHA['b']}/image")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_the_view_can_ask_for_a_smaller_picture(client) -> None:
    """Siatka klastra pokazuje kilkanaście kart naraz — pełnowymiarowe rendery byłyby
    marnotrawstwem, a na telefonie karą. Stąd `width` przy podglądzie."""
    import io

    from PIL import Image

    small = client.get(f"/api/preview/{SHA['b']}/image", params={"width": 120})
    big = client.get(f"/api/preview/{SHA['b']}/image", params={"width": 600})

    assert small.status_code == 200 and big.status_code == 200
    with Image.open(io.BytesIO(small.content)) as image:
        assert image.width == 40, "obraz 40 px nie jest rozciągany w górę"
    page = client.get(f"/api/preview/{SHA['a']}/image", params={"width": 200})
    with Image.open(io.BytesIO(page.content)) as image:
        assert image.width == 200, "strona PDF ma być renderowana w żądanej szerokości"


def test_an_absurd_width_is_refused_not_rendered(client) -> None:
    assert client.get(f"/api/preview/{SHA['a']}/image", params={"width": 99999}).status_code == 422
    assert client.get(f"/api/preview/{SHA['a']}/image", params={"width": 1}).status_code == 422


def test_preview_image_is_404_when_no_copy_is_on_disk(client) -> None:
    assert client.get(f"/api/preview/{SHA['c']}/image").status_code == 404


def test_preview_says_what_it_can_show(client) -> None:
    """Widok pyta RAZ i wie, co narysować — bez zgadywania po rozszerzeniu."""
    pdf = client.get(f"/api/preview/{SHA['a']}").json()
    image = client.get(f"/api/preview/{SHA['b']}").json()
    nothing = client.get(f"/api/preview/{SHA['c']}").json()

    assert pdf["preview_kind"] == "page" and pdf["has_image"] is True
    assert image["preview_kind"] == "image" and image["has_image"] is True
    assert nothing["preview_kind"] == "none" and nothing["has_image"] is False


def test_unknown_content_is_404(client) -> None:
    assert client.get("/api/preview/" + "0" * 64).status_code == 404
    assert client.get("/api/preview/" + "0" * 64 + "/image").status_code == 404
