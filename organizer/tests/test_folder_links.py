"""Q3: ręczne powiązanie katalogów między paczkami.

Dedup katalogów (`folders.duplicate_of`) jest deterministyczny: liczy się z `tree_hash`,
czyli z DOKŁADNEJ równości poddrzewa. Człowiek widzi więcej — że „AKO2020/wyklady" w jednej
paczce to ten sam materiał co „ako_stare/w" w drugiej, choć pliki różnią się dwoma skanami.

Dlatego powiązanie ręczne jest OSOBNYM bytem i **nie** wchodzi do `duplicate_of`:
`db.files_pending` wycina poddrzewa duplikatów z extract/classify, więc potraktowanie
ręcznej pary jak duplikatu po cichu wyrzuciłoby z potoku pliki, które są tylko po jednej
stronie. Powiązanie ma podpowiadać, nie kasować.
"""

from __future__ import annotations

import pytest

from orglib import db, folder_links


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "index.sqlite")
    db.upsert(connection, "source_packages", {"package_name": "P1"}, conflict=("package_name",))
    db.upsert(connection, "source_packages", {"package_name": "P2"}, conflict=("package_name",))
    for sciezka, paczka in (
        ("P1/AKO2020", "P1"), ("P1/AKO2020/wyklady", "P1"),
        ("P2/ako_stare", "P2"), ("P2/ako_stare/w", "P2"),
    ):
        db.upsert_folder(connection, {"folder_path": sciezka, "source_package": paczka})
    connection.commit()
    yield connection
    connection.close()


def test_schema_knows_the_new_table(conn) -> None:
    """Migracja: tabela ma powstać także w bazie, która już istniała."""
    assert db.SCHEMA_VERSION >= 3
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_folder_links'"
    ).fetchone() is not None


def test_link_is_stored_in_one_canonical_order(conn) -> None:
    """A≡B i B≡A to jedno powiązanie — inaczej lista rosłaby w dwóch kierunkach."""
    folder_links.link(conn, "P2/ako_stare/w", "P1/AKO2020/wyklady", decided_by="test")
    folder_links.link(conn, "P1/AKO2020/wyklady", "P2/ako_stare/w", decided_by="test")

    wszystkie = folder_links.all_links(conn)

    assert len(wszystkie) == 1
    assert wszystkie[0]["folder_a"] < wszystkie[0]["folder_b"]


def test_link_is_visible_from_both_sides(conn) -> None:
    folder_links.link(conn, "P1/AKO2020/wyklady", "P2/ako_stare/w", decided_by="test")

    assert folder_links.partners(conn, "P1/AKO2020/wyklady") == {"P2/ako_stare/w"}
    assert folder_links.partners(conn, "P2/ako_stare/w") == {"P1/AKO2020/wyklady"}


def test_kind_says_how_strong_the_claim_is(conn) -> None:
    folder_links.link(conn, "P1/AKO2020", "P2/ako_stare", kind="related", decided_by="test")

    assert folder_links.all_links(conn)[0]["kind"] == "related"


def test_an_unknown_kind_is_refused(conn) -> None:
    with pytest.raises(ValueError):
        folder_links.link(conn, "P1/AKO2020", "P2/ako_stare", kind="wymyslony", decided_by="test")


def test_a_folder_cannot_be_linked_to_itself(conn) -> None:
    with pytest.raises(ValueError):
        folder_links.link(conn, "P1/AKO2020", "P1/AKO2020", decided_by="test")


def test_an_unknown_folder_is_refused(conn) -> None:
    """Literówka w ścieżce ma boleć od razu, a nie zostać martwym wierszem w bazie."""
    with pytest.raises(LookupError):
        folder_links.link(conn, "P1/AKO2020", "P2/nie_ma_takiego", decided_by="test")


def test_relinking_updates_instead_of_duplicating(conn) -> None:
    folder_links.link(conn, "P1/AKO2020", "P2/ako_stare", kind="related", decided_by="test")
    folder_links.link(conn, "P1/AKO2020", "P2/ako_stare", kind="duplicate",
                      decided_by="test", note="jednak to samo")

    wszystkie = folder_links.all_links(conn)

    assert len(wszystkie) == 1
    assert wszystkie[0]["kind"] == "duplicate" and wszystkie[0]["note"] == "jednak to samo"


def test_unlink_removes_the_pair_regardless_of_order(conn) -> None:
    folder_links.link(conn, "P1/AKO2020", "P2/ako_stare", decided_by="test")

    assert folder_links.unlink(conn, "P2/ako_stare", "P1/AKO2020") is True
    assert folder_links.all_links(conn) == []
    assert folder_links.unlink(conn, "P2/ako_stare", "P1/AKO2020") is False


# --- czego powiązanie NIE robi ---------------------------------------------

def test_manual_link_does_not_touch_duplicate_of(conn) -> None:
    """To jest sedno: `files_pending` wycina poddrzewa `duplicate_of` z potoku.

    Gdyby ręczna para tam trafiła, pliki obecne tylko po jednej stronie zniknęłyby
    z extract i classify bez śladu w żadnym raporcie.
    """
    folder_links.link(conn, "P1/AKO2020/wyklady", "P2/ako_stare/w", decided_by="test")

    duplikaty = conn.execute(
        "SELECT COUNT(*) AS n FROM folders WHERE duplicate_of IS NOT NULL"
    ).fetchone()["n"]

    assert duplikaty == 0
