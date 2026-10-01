"""Q9: piąty poziom grafu — konkretne laboratorium albo kolokwium.

Hierarchia kończy się dziś na kategorii: `semestr → przedmiot → kategoria → plik`.
Pliki jednej labki leżą obok siebie, ale nic nie mówi, że należą do `lab_05` — a katalog
źródłowy niesie tę informację od lat, za darmo.

Poziom `group` powstaje WYŁĄCZNIE tam, gdzie coś wnosi:
- co najmniej dwa pliki kategorii dzielą katalog-liść (jeden plik to nie skupisko);
- grupa nie obejmuje całej kategorii (wtedy byłby to drugi węzeł o tej samej treści).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import synapse_export as cli
from orglib import config, db

runner = CliRunner()
SHA = {name: name * 64 for name in "abcdef"}
# lab_05: dwa pliki · lab_06: jeden plik · kolokwia: dwa pliki w jednym katalogu (cała kategoria)
ROZKLAD = [
    (SHA["a"], "laboratoria", "SEM3/AKO/Laby/lab_05/zad1.pdf"),
    (SHA["b"], "laboratoria", "SEM3/AKO/Laby/lab_05/zad2.pdf"),
    (SHA["c"], "laboratoria", "SEM3/AKO/Laby/lab_06/zad1.pdf"),
    (SHA["d"], "kolokwia", "SEM3/AKO/kol1/pytania.pdf"),
    (SHA["e"], "kolokwia", "SEM3/AKO/kol1/odpowiedzi.pdf"),
]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    paths = config.Paths(
        sources=tmp_path / "sources", work=tmp_path / "work",
        media=tmp_path / "media", target_repo=tmp_path / "target",
        target_paczka=tmp_path / "target" / "paczka",
        work_db=tmp_path / "work" / "index.sqlite",
        work_extracted_text=tmp_path / "work" / "text",
        work_thumbnails=tmp_path / "work" / "thumbs",
    )
    monkeypatch.setattr(config, "load_paths", lambda: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    conn = db.connect(paths.work_db)
    db.upsert(conn, "source_packages", {"package_name": "P"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P/SEM3", "source_package": "P"})
    for sha, kategoria, sciezka in ROZKLAD:
        db.upsert_content(conn, {"sha256": sha, "content_kind": "pdf"})
        db.upsert_file(conn, {
            "source_package": "P", "source_relative_path": sciezka,
            "folder_path": "P/SEM3", "filename": sciezka.rsplit("/", 1)[-1],
            "extension": ".pdf", "size_bytes": 2048, "sha256": sha, "status": "extracted",
        })
        db.upsert_classification(conn, {
            "sha256": sha, "semester": 3, "subject_key": "AKO", "category": kategoria,
            "target_relative_path": f"paczka/SEM3/AKO_X/{kategoria}/{sha[:4]}.pdf",
            "is_outdated": 0, "classification_method": "heuristic", "confidence": 0.95,
            "run_id": "plan:abc", "decided_at": "2026-09-19T00:00:00Z", "action": "copy",
            "reason": "test", "needs_review": 0,
        })
    conn.commit()
    conn.close()
    return paths


def notes(workspace) -> dict[str, str]:
    root = workspace.work / "synapse" / "vault"
    return {p.stem: p.read_text(encoding="utf-8") for p in root.rglob("*.md")}


def test_a_shared_leaf_folder_becomes_a_node(workspace) -> None:
    wynik = runner.invoke(cli.app, [])
    assert wynik.exit_code == 0, wynik.output

    wszystkie = notes(workspace)
    grupy = [n for n in wszystkie if "-grp-" in n]

    assert grupy == ["sem3-ako-kat-laboratoria-grp-lab-05"]
    assert 'type: "group"' in wszystkie[grupy[0]]


def test_the_group_hangs_off_its_category(workspace) -> None:
    runner.invoke(cli.app, [])

    grupa = notes(workspace)["sem3-ako-kat-laboratoria-grp-lab-05"]

    assert '  - target: "sem3-ako-kat-laboratoria"\n    kind: "belongs_to"' in grupa


def test_files_of_the_group_hang_off_it_instead_of_the_category(workspace) -> None:
    runner.invoke(cli.app, [])

    wszystkie = notes(workspace)
    w_grupie = [t for n, t in wszystkie.items() if n.startswith("ako-zad1-") or n.startswith("ako-zad2-")]
    z_lab05 = [t for t in w_grupie if 'grp-lab-05"\n    kind: "belongs_to"' in t]

    assert len(z_lab05) == 2, "oba pliki lab_05 mają wisieć na grupie"


def test_a_lonely_file_stays_on_the_category(workspace) -> None:
    """Jeden plik to nie skupisko — dodatkowy węzeł tylko wydłużałby ścieżkę do niego."""
    runner.invoke(cli.app, [])

    wszystkie = notes(workspace)
    assert "sem3-ako-kat-laboratoria-grp-lab-06" not in wszystkie


def test_a_group_covering_the_whole_category_is_not_created(workspace) -> None:
    """Obie treści `kolokwia` leżą w `kol1`, więc grupa powtarzałaby kategorię."""
    runner.invoke(cli.app, [])

    wszystkie = notes(workspace)
    assert not [n for n in wszystkie if n.startswith("sem3-ako-kat-kolokwia-grp-")]


def test_the_group_is_selectable_with_its_files(workspace) -> None:
    """Wybór zakresu w viewerze idzie po tagach, więc grupa musi mieć tagi swoich plików."""
    runner.invoke(cli.app, [])

    grupa = notes(workspace)["sem3-ako-kat-laboratoria-grp-lab-05"]

    assert '"sem3"' in grupa and '"ako"' in grupa
    assert '"kategoria-laboratoria"' in grupa
    # Tag `grupa-…` jest ZAJĘTY przez grupę studencką przedmiotu (`grupa-wspolne`),
    # więc katalog źródłowy dostaje własną przestrzeń: `katalog-…`.
    assert '"katalog-lab-05"' in grupa
    assert '"grupa-lab-05"' not in grupa
