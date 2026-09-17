"""Testy hashowania katalogów: tree_hash/content_set_hash, duplicate_of i raport pokrycia.

Wszystko dzieje się w tmp_path na bazie zasianej przez helpery — testy nigdy nie
dotykają prawdziwego 00_SOURCES ani 20_WORK (fold_hash.py i tak nie czyta plików
źródłowych, jedynym wyjściem na dysk jest CSV).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import pytest
from typer.testing import CliRunner

import fold_hash
from orglib import db, hashes

runner = CliRunner()

#: Rozmiar każdego zasianego pliku (total_bytes katalogów liczy się z niego).
FILE_SIZE = 10


@pytest.fixture()
def conn(tmp_path: Path):
    """Świeża baza w tmp_path z założonym schematem."""
    connection = db.connect(tmp_path / "organizer.sqlite")
    yield connection
    connection.close()


def _seed_package(
    connection: sqlite3.Connection,
    package: str,
    files: Mapping[str, Optional[str]],
    empty_folders: Sequence[str] = (),
) -> None:
    """Zasiewa paczkę: katalogi (z rekurencyjnymi licznikami) i pliki o zadanych sha256.

    ``files`` mapuje ścieżkę względem katalogu paczki na sha256 (``None`` = plik
    jeszcze niezahashowany). ``empty_folders`` to katalogi bez plików, podane jako
    ścieżki względem paczki.
    """
    db.upsert(
        connection, "source_packages", {"package_name": package}, conflict=("package_name",)
    )
    stats: dict[str, list[int]] = {package: [0, 0]}
    for name in empty_folders:
        for ancestor in fold_hash.ancestor_paths(f"{package}/{name}", package):
            stats.setdefault(ancestor, [0, 0])

    rows: list[dict[str, object]] = []
    for relpath, sha256 in sorted(files.items()):
        folder_path = db.folder_path_for(package, relpath)
        for ancestor in fold_hash.ancestor_paths(folder_path, package):
            entry = stats.setdefault(ancestor, [0, 0])
            entry[0] += 1
            entry[1] += FILE_SIZE
        rows.append(
            {
                "source_package": package,
                "source_relative_path": relpath,
                "folder_path": folder_path,
                "filename": Path(relpath).name,
                "size_bytes": FILE_SIZE,
                "sha256": sha256,
                "status": "discovered" if sha256 is None else "hashed",
            }
        )

    for folder_path in sorted(stats):
        db.upsert_folder(
            connection,
            {
                "folder_path": folder_path,
                "source_package": package,
                "file_count": stats[folder_path][0],
                "total_bytes": stats[folder_path][1],
            },
        )
    for row in rows:
        db.upsert_file(connection, row)


def _process(connection: sqlite3.Connection, packages: Sequence[str] = ()) -> dict[str, object]:
    """Uruchamia oba przejścia tak jak CLI i zwraca pośrednie struktury do asercji."""
    folders = fold_hash.load_folders(connection, packages)
    files = fold_hash.load_files(connection, packages)
    subtrees = fold_hash.aggregate_subtrees(folders, files)
    computed, stats = fold_hash.compute_hashes(folders, subtrees)
    fold_hash.write_hashes(connection, folders, computed)
    state = fold_hash.load_folder_state(connection)
    duplicates = fold_hash.duplicate_map({path: item.tree_hash for path, item in state.items()})
    fold_hash.write_duplicates(connection, state, duplicates)
    return {
        "folders": folders,
        "subtrees": subtrees,
        "computed": computed,
        "duplicates": duplicates,
        "stats": stats,
    }


def _rows(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Wiersze katalogów z bazy, kluczowane folder_path."""
    return {
        str(row["folder_path"]): row
        for row in connection.execute("SELECT * FROM folders").fetchall()
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Wczytuje raport pokrycia jako listę słowników."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _pair_keys(pairs: Iterable[fold_hash.OverlapPair]) -> list[tuple[str, str]]:
    """Same pary (folder_a, folder_b) — do zwięzłych asercji."""
    return [(pair.folder_a, pair.folder_b) for pair in pairs]


# --- przejście 1: tree_hash / content_set_hash --------------------------------


def test_ancestor_paths_walks_from_package_root_down() -> None:
    assert fold_hash.ancestor_paths("P1/a/b", "P1") == ["P1", "P1/a", "P1/a/b"]
    assert fold_hash.ancestor_paths("P1", "P1") == ["P1"]


def test_tree_hash_uses_paths_relative_to_the_folder(conn: sqlite3.Connection) -> None:
    # To samo poddrzewo (sub/{a,b}) pod dwoma różnymi rodzicami.
    _seed_package(
        conn,
        "P1",
        {
            "x/sub/a.txt": "sha_a",
            "x/sub/b.txt": "sha_b",
            "y/deep/sub/a.txt": "sha_a",
            "y/deep/sub/b.txt": "sha_b",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["P1/x/sub"]["tree_hash"] == rows["P1/y/deep/sub"]["tree_hash"]
    assert rows["P1/x/sub"]["tree_hash"] == hashes.tree_hash(
        [("a.txt", "sha_a"), ("b.txt", "sha_b")]
    )
    # Rodzice różnią się nazwą katalogu pośredniego, więc ich tree_hash już nie.
    assert rows["P1/x"]["tree_hash"] != rows["P1/y"]["tree_hash"]


def test_root_folder_hashes_bare_relative_paths(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a.txt": "sha_a", "sub/b.txt": "sha_b"})

    _process(conn)
    rows = _rows(conn)

    assert rows["P1"]["tree_hash"] == hashes.tree_hash(
        [("a.txt", "sha_a"), ("sub/b.txt", "sha_b")]
    )
    assert rows["P1"]["content_set_hash"] == hashes.content_set_hash(["sha_a", "sha_b"])
    assert rows["P1"]["status"] == "hashed"


def test_renamed_files_share_content_set_hash_but_not_tree_hash(
    conn: sqlite3.Connection,
) -> None:
    _seed_package(
        conn,
        "P1",
        {
            "orig/w1.pdf": "sha_1",
            "orig/w2.pdf": "sha_2",
            "kopia/wyklad1.pdf": "sha_1",
            "kopia/wyklad2.pdf": "sha_2",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["P1/orig"]["content_set_hash"] == rows["P1/kopia"]["content_set_hash"]
    assert rows["P1/orig"]["tree_hash"] != rows["P1/kopia"]["tree_hash"]
    assert rows["P1/orig"]["duplicate_of"] is None
    assert rows["P1/kopia"]["duplicate_of"] is None


def test_incomplete_subtree_leaves_folder_and_ancestors_null(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/b/done.txt": "sha_a", "a/b/todo.txt": None, "c/ok.txt": "sha_c"})

    result = _process(conn)
    rows = _rows(conn)

    assert rows["P1/a/b"]["tree_hash"] is None
    assert rows["P1/a/b"]["content_set_hash"] is None
    assert rows["P1/a"]["tree_hash"] is None
    assert rows["P1"]["tree_hash"] is None
    # Status niekompletnych zostaje nietknięty, gałąź bez braków hashuje się normalnie.
    assert rows["P1/a/b"]["status"] == "discovered"
    assert rows["P1/c"]["tree_hash"] is not None
    assert rows["P1/c"]["status"] == "hashed"
    stats = result["stats"]
    assert (stats.incomplete, stats.hashed, stats.empty) == (3, 1, 0)


def test_empty_folders_stay_null_and_never_duplicate(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a.txt": "sha_a"}, empty_folders=("pusty1", "pusty2"))

    result = _process(conn)
    rows = _rows(conn)

    for path in ("P1/pusty1", "P1/pusty2"):
        assert rows[path]["tree_hash"] is None
        assert rows[path]["content_set_hash"] is None
        assert rows[path]["duplicate_of"] is None
        assert rows[path]["status"] == "discovered"
    assert result["stats"].empty == 2


def test_error_folders_are_never_hashed_duplicated_nor_reported(
    conn: sqlite3.Connection,
) -> None:
    # P1/b ma tę samą treść co P1/a (pod innymi nazwami), ale scan.py nie zdołał
    # go odczytać — nie wolno go hashować ani zestawiać z czymkolwiek.
    _seed_package(
        conn,
        "P1",
        {
            "a/1.txt": "s1",
            "a/2.txt": "s2",
            "a/3.txt": "s3",
            "b/x1.txt": "s1",
            "b/x2.txt": "s2",
            "b/x3.txt": "s3",
        },
    )
    with conn:
        conn.execute("UPDATE folders SET status = 'error' WHERE folder_path = 'P1/b'")

    result = _process(conn)
    rows = _rows(conn)

    assert rows["P1/b"]["tree_hash"] is None
    assert rows["P1/b"]["content_set_hash"] is None
    assert rows["P1/b"]["status"] == "error"
    assert rows["P1/b"]["duplicate_of"] is None
    assert result["stats"].errors == 1

    pairs = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.50
    ).pairs
    assert all("P1/b" not in key for key in _pair_keys(pairs))


# --- przejście 2: duplicate_of ------------------------------------------------


def test_duplicate_of_points_to_lexicographically_smallest_path(
    conn: sqlite3.Connection,
) -> None:
    _seed_package(
        conn,
        "P1",
        {
            "bbb/f.txt": "sha_f",
            "aaa/f.txt": "sha_f",
            "ccc/f.txt": "sha_f",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["P1/aaa"]["duplicate_of"] is None
    assert rows["P1/bbb"]["duplicate_of"] == "P1/aaa"
    assert rows["P1/ccc"]["duplicate_of"] == "P1/aaa"


def _canonical_never_under_duplicate(rows: Mapping[str, sqlite3.Row]) -> None:
    """Sprawdza niezmiennik: żaden katalog kanoniczny nie leży pod duplikatem."""
    duplicates = {path for path, row in rows.items() if row["duplicate_of"] is not None}
    canonicals = {
        str(row["duplicate_of"]) for row in rows.values() if row["duplicate_of"] is not None
    }
    for canonical in canonicals:
        parts = canonical.split("/")
        ancestors = {"/".join(parts[:i]) for i in range(1, len(parts))}
        assert not (ancestors & duplicates), f"{canonical} leży pod duplikatem"


def test_nested_duplicates_keep_canonical_outside_duplicates(conn: sqlite3.Connection) -> None:
    _seed_package(
        conn,
        "P1",
        {
            "A/sub/f1.txt": "sha_1",
            "A/sub/f2.txt": "sha_2",
            "B/sub/f1.txt": "sha_1",
            "B/sub/f2.txt": "sha_2",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["P1/A"]["duplicate_of"] is None
    assert rows["P1/B"]["duplicate_of"] == "P1/A"
    assert rows["P1/A/sub"]["duplicate_of"] is None
    assert rows["P1/B/sub"]["duplicate_of"] == "P1/A/sub"
    _canonical_never_under_duplicate(rows)


def test_path_key_orders_by_components_not_by_raw_string() -> None:
    # Pułapka: ' ' (0x20) sortuje się poniżej '/' (0x2F), więc porządek napisów
    # odwraca się po dopisaniu dziecka.
    assert "P/AKO2020" < "P/AKO2020 (1)"
    assert "P/AKO2020 (1)/wyklady" < "P/AKO2020/wyklady"
    # Na krotkach komponentów porządek jest stabilny na obu poziomach.
    assert fold_hash.path_key("P/AKO2020") < fold_hash.path_key("P/AKO2020 (1)")
    assert fold_hash.path_key("P/AKO2020/wyklady") < fold_hash.path_key("P/AKO2020 (1)/wyklady")


def test_prefix_names_keep_canonical_outside_duplicates(conn: sqlite3.Connection) -> None:
    # Prawdziwy kształt ze źródeł: 'AKO2020' jest prefiksem 'AKO2020 (1)'.
    # Wybór kanonicznego po napisie wsadziłby kanoniczne 'wyklady' pod duplikat
    # 'P/AKO2020 (1)', a wtedy files_pending('extract') nie zwróciłby NICZEGO.
    _seed_package(
        conn,
        "P",
        {
            "AKO2020/wyklady/w1.pdf": "s1",
            "AKO2020/wyklady/w2.pdf": "s2",
            "AKO2020 (1)/wyklady/w1.pdf": "s1",
            "AKO2020 (1)/wyklady/w2.pdf": "s2",
            "zz/wyklady/w1.pdf": "s1",
            "zz/wyklady/w2.pdf": "s2",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["P/AKO2020"]["duplicate_of"] is None
    assert rows["P/AKO2020 (1)"]["duplicate_of"] == "P/AKO2020"
    assert rows["P/zz"]["duplicate_of"] == "P/AKO2020"
    assert rows["P/AKO2020/wyklady"]["duplicate_of"] is None
    assert rows["P/AKO2020 (1)/wyklady"]["duplicate_of"] == "P/AKO2020/wyklady"
    assert rows["P/zz/wyklady"]["duplicate_of"] == "P/AKO2020/wyklady"
    _canonical_never_under_duplicate(rows)

    # Najważniejsze: kanoniczna kopia treści wciąż stoi w kolejce do extract.
    pending = db.files_pending(conn, "extract")
    assert sorted(str(row["source_relative_path"]) for row in pending) == [
        "AKO2020/wyklady/w1.pdf",
        "AKO2020/wyklady/w2.pdf",
    ]


def test_three_locations_nested_in_a_bigger_duplicated_tree(conn: sqlite3.Connection) -> None:
    # Ten sam układ, ale całe 'top' jest jeszcze raz skopiowane jako 'kopia top'.
    _seed_package(
        conn,
        "Q",
        {
            "top/AKO2020/wyklady/f.pdf": "s1",
            "top/AKO2020 (1)/wyklady/f.pdf": "s1",
            "top/zz/wyklady/f.pdf": "s1",
            "kopia top/AKO2020/wyklady/f.pdf": "s1",
            "kopia top/AKO2020 (1)/wyklady/f.pdf": "s1",
            "kopia top/zz/wyklady/f.pdf": "s1",
        },
    )

    _process(conn)
    rows = _rows(conn)

    assert rows["Q/kopia top"]["duplicate_of"] is None
    assert rows["Q/top"]["duplicate_of"] == "Q/kopia top"
    assert rows["Q/kopia top/AKO2020"]["duplicate_of"] is None
    assert rows["Q/kopia top/AKO2020/wyklady"]["duplicate_of"] is None
    # Wszystkie pozostałe sześć lokalizacji 'wyklady' wskazuje na tę jedną.
    wyklady = {path: row for path, row in rows.items() if path.endswith("/wyklady")}
    assert len(wyklady) == 6
    assert {row["duplicate_of"] for path, row in wyklady.items() if path != "Q/kopia top/AKO2020/wyklady"} == {
        "Q/kopia top/AKO2020/wyklady"
    }
    _canonical_never_under_duplicate(rows)

    pending = db.files_pending(conn, "extract")
    assert [str(row["source_relative_path"]) for row in pending] == [
        "kopia top/AKO2020/wyklady/f.pdf"
    ]


def test_check_canonical_invariant_refuses_canonical_under_duplicate() -> None:
    # Ręcznie zestawiona, niespójna mapa: kanoniczne 'P/b/c' leży pod duplikatem 'P/b'.
    with pytest.raises(RuntimeError, match="niezmiennik"):
        fold_hash.check_canonical_invariant({"P/b": "P/z", "P/a": "P/b/c"})


# --- statusy ------------------------------------------------------------------


def test_stale_hashed_status_is_reset_for_empty_and_incomplete(
    conn: sqlite3.Connection,
) -> None:
    _seed_package(conn, "P1", {"a/done.txt": "sha_a", "a/todo.txt": None}, empty_folders=("pusty",))
    # Symulujemy pozostałość po wcześniejszym przebiegu: oba katalogi mają stary
    # 'hashed' i stary tree_hash, choć teraz nie da się ich policzyć.
    with conn:
        conn.execute(
            "UPDATE folders SET status = 'hashed', tree_hash = 'stary', "
            "content_set_hash = 'stary' WHERE folder_path IN ('P1/a', 'P1/pusty')"
        )

    _process(conn)
    rows = _rows(conn)

    for path in ("P1/a", "P1/pusty"):
        assert rows[path]["tree_hash"] is None
        assert rows[path]["content_set_hash"] is None
        assert rows[path]["status"] == "discovered"


def test_error_status_stays_sticky(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f"})
    with conn:
        conn.execute("UPDATE folders SET status = 'error' WHERE folder_path = 'P1/a'")

    _process(conn)

    assert _rows(conn)["P1/a"]["status"] == "error"


# --- idempotencja -------------------------------------------------------------


def test_rerun_is_idempotent(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f", "b/f.txt": "sha_f", "c/g.txt": "sha_g"})

    _process(conn)
    first = {path: dict(row) for path, row in _rows(conn).items()}
    _process(conn)
    second = {path: dict(row) for path, row in _rows(conn).items()}

    assert first == second


def test_changed_content_releases_a_former_duplicate(conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f", "b/f.txt": "sha_f"})
    _process(conn)
    assert _rows(conn)["P1/b"]["duplicate_of"] == "P1/a"

    with conn:
        conn.execute("UPDATE files SET sha256 = 'sha_inny' WHERE source_relative_path = 'b/f.txt'")
    _process(conn)
    rows = _rows(conn)

    assert rows["P1/b"]["duplicate_of"] is None
    assert rows["P1/a"]["duplicate_of"] is None
    assert rows["P1/a"]["tree_hash"] != rows["P1/b"]["tree_hash"]


# --- raport częściowego pokrycia ----------------------------------------------


@pytest.fixture()
def overlap_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Paczka z trzema katalogami: a∩b = 3 treści (0.75), a∩c = b∩c = 2 treści (0.50)."""
    _seed_package(
        conn,
        "O",
        {
            "a/1.txt": "s1",
            "a/2.txt": "s2",
            "a/3.txt": "s3",
            "a/4.txt": "s4",
            "b/1.txt": "s1",
            "b/2.txt": "s2",
            "b/3.txt": "s3",
            "b/9.txt": "s9",
            "c/1.txt": "s1",
            "c/2.txt": "s2",
            "c/7.txt": "s7",
            "c/8.txt": "s8",
        },
    )
    return conn


def test_overlap_reports_pair_above_threshold_with_correct_numbers(
    overlap_conn: sqlite3.Connection,
) -> None:
    result = _process(overlap_conn)

    overlap = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.60
    )
    pairs = overlap.pairs

    assert overlap.skipped_hashes == 0
    assert not overlap.aborted
    assert _pair_keys(pairs) == [("O/a", "O/b")]
    pair = pairs[0]
    assert (pair.unique_a, pair.unique_b, pair.common) == (4, 4, 3)
    assert pair.ratio_min == pytest.approx(0.75)
    assert pair.jaccard == pytest.approx(0.6)
    assert (pair.files_a, pair.files_b) == (4, 4)


def test_overlap_skips_pairs_below_threshold(overlap_conn: sqlite3.Connection) -> None:
    result = _process(overlap_conn)

    pairs = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.60
    ).pairs

    assert ("O/a", "O/c") not in _pair_keys(pairs)
    assert ("O/b", "O/c") not in _pair_keys(pairs)


def test_overlap_excludes_ancestor_descendant_pairs(overlap_conn: sqlite3.Connection) -> None:
    result = _process(overlap_conn)

    pairs = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.50
    ).pairs

    keys = _pair_keys(pairs)
    assert ("O", "O/a") not in keys
    assert all(not key[1].startswith(f"{key[0]}/") for key in keys)


def test_overlap_skips_too_common_hashes(overlap_conn: sqlite3.Connection) -> None:
    result = _process(overlap_conn)

    overlap = fold_hash.overlap_pairs(
        result["folders"],
        result["subtrees"],
        result["computed"],
        result["duplicates"],
        0.50,
        max_shared_folders=1,
    )

    # Każdy sha256 siedzi w >= 2 katalogach-kandydatach (folder + korzeń paczki),
    # więc przy limicie 1 nie zostaje żadna wspólna treść.
    assert overlap.skipped_hashes > 0
    assert overlap.pairs == []


def test_overlap_drops_pairs_covered_by_their_parents(conn: sqlite3.Connection) -> None:
    # x/inner i y/inner mają te same treści pod innymi nazwami (nie są dokładnymi
    # duplikatami), a ich rodzice różnią się jednym dodatkowym plikiem.
    _seed_package(
        conn,
        "P",
        {
            "x/inner/f1.txt": "s1",
            "x/inner/f2.txt": "s2",
            "x/inner/f3.txt": "s3",
            "x/extra.txt": "s4",
            "y/inner/g1.txt": "s1",
            "y/inner/g2.txt": "s2",
            "y/inner/g3.txt": "s3",
            "y/extra.txt": "s5",
        },
    )
    result = _process(conn)

    pairs = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.50
    ).pairs

    keys = _pair_keys(pairs)
    assert ("P/x", "P/y") in keys
    assert ("P/x/inner", "P/y/inner") not in keys


def test_overlap_csv_is_sorted_and_formatted(tmp_path: Path, overlap_conn: sqlite3.Connection) -> None:
    result = _process(overlap_conn)
    pairs = fold_hash.overlap_pairs(
        result["folders"], result["subtrees"], result["computed"], result["duplicates"], 0.50
    ).pairs
    target = tmp_path / "out" / "folder_overlap.csv"

    fold_hash.write_overlap_csv(target, pairs)
    rows = _read_csv(target)

    assert target.read_text(encoding="utf-8").splitlines()[0] == ",".join(
        fold_hash.OVERLAP_COLUMNS
    )
    assert "\r" not in target.read_text(encoding="utf-8")
    assert [(row["folder_a"], row["folder_b"]) for row in rows] == [
        ("O/a", "O/b"),
        ("O/a", "O/c"),
        ("O/b", "O/c"),
    ]
    assert rows[0]["ratio_min"] == "0.7500"
    assert rows[0]["jaccard"] == "0.6000"
    assert rows[0]["common"] == "3"


def test_overlap_aborts_above_pair_increment_limit(overlap_conn: sqlite3.Connection) -> None:
    result = _process(overlap_conn)

    overlap = fold_hash.overlap_pairs(
        result["folders"],
        result["subtrees"],
        result["computed"],
        result["duplicates"],
        0.50,
        max_increments=0,
    )

    assert overlap.aborted
    assert overlap.pairs == []
    assert overlap.increments > 0


# --- CLI ----------------------------------------------------------------------


def test_cli_hashes_marks_duplicates_and_writes_report(
    tmp_path: Path, overlap_conn: sqlite3.Connection
) -> None:
    database = Path(str(overlap_conn.execute("PRAGMA database_list").fetchone()["file"]))
    overlap_conn.close()
    report = tmp_path / "folder_overlap.csv"

    result = runner.invoke(
        fold_hash.app, ["--db", str(database), "--overlap-csv", str(report)]
    )

    assert result.exit_code == 0, result.output
    assert "katalogi: razem 4" in result.output
    assert report.exists()
    # Próg domyślny (0.50 z thresholds.yaml) przepuszcza wszystkie trzy pary.
    assert len(_read_csv(report)) == 3


def test_cli_no_overlap_skips_the_report(tmp_path: Path, conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f", "b/f.txt": "sha_f"})
    database = Path(str(conn.execute("PRAGMA database_list").fetchone()["file"]))
    conn.close()

    result = runner.invoke(fold_hash.app, ["--db", str(database), "--no-overlap"])

    assert result.exit_code == 0, result.output
    assert "pokrycie: pominięte" in result.output
    assert not (tmp_path / "folder_overlap.csv").exists()
    connection = db.connect(database, init=False)
    try:
        assert _rows(connection)["P1/b"]["duplicate_of"] == "P1/a"
    finally:
        connection.close()


def test_cli_package_filter_leaves_other_packages_untouched(
    tmp_path: Path, conn: sqlite3.Connection
) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f"})
    _seed_package(conn, "P2", {"a/f.txt": "sha_f"})
    database = Path(str(conn.execute("PRAGMA database_list").fetchone()["file"]))
    conn.close()

    result = runner.invoke(
        fold_hash.app, ["--db", str(database), "--package", "P1", "--no-overlap"]
    )

    assert result.exit_code == 0, result.output
    connection = db.connect(database, init=False)
    try:
        rows = _rows(connection)
        assert rows["P1/a"]["tree_hash"] is not None
        assert rows["P2/a"]["tree_hash"] is None
        # Bez filtra P1/a i P2/a byłyby duplikatami — filtr nie może ich połączyć.
        assert rows["P1/a"]["duplicate_of"] is None
    finally:
        connection.close()


def test_cli_rejects_unknown_package(tmp_path: Path, conn: sqlite3.Connection) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f"})
    database = Path(str(conn.execute("PRAGMA database_list").fetchone()["file"]))
    conn.close()

    result = runner.invoke(fold_hash.app, ["--db", str(database), "--package", "P9"])

    assert result.exit_code == 1
    assert "P9" in result.output


def test_cli_refuses_missing_db(tmp_path: Path) -> None:
    result = runner.invoke(fold_hash.app, ["--db", str(tmp_path / "nie-ma.sqlite")])

    assert result.exit_code == 1
    assert not (tmp_path / "nie-ma.sqlite").exists()


def test_cli_rejects_overlap_csv_and_no_overlap_together(tmp_path: Path) -> None:
    result = runner.invoke(
        fold_hash.app,
        [
            "--db",
            str(tmp_path / "db.sqlite"),
            "--overlap-csv",
            str(tmp_path / "o.csv"),
            "--no-overlap",
        ],
    )

    assert result.exit_code == 2


def test_cli_help_lists_options() -> None:
    result = runner.invoke(fold_hash.app, ["--help"])

    assert result.exit_code == 0
    for option in ("--db", "--package", "--overlap-csv", "--no-overlap"):
        assert option in result.output


def test_cli_package_run_clears_stale_duplicate_pointer(
    tmp_path: Path, conn: sqlite3.Connection
) -> None:
    _seed_package(conn, "P1", {"a/f.txt": "sha_f"})
    _seed_package(conn, "P2", {"a/f.txt": "sha_f"})
    database = Path(str(conn.execute("PRAGMA database_list").fetchone()["file"]))
    conn.close()

    first = runner.invoke(fold_hash.app, ["--db", str(database), "--no-overlap"])
    assert first.exit_code == 0, first.output
    connection = db.connect(database, init=False)
    try:
        assert _rows(connection)["P2/a"]["duplicate_of"] == "P1/a"
        # Treść kanonicznej kopii się zmieniła — P2/a przestaje być duplikatem,
        # mimo że kolejny przebieg dotyczy wyłącznie paczki P1.
        with connection:
            connection.execute(
                "UPDATE files SET sha256 = 'sha_inny' WHERE source_package = 'P1'"
            )
    finally:
        connection.close()

    second = runner.invoke(
        fold_hash.app, ["--db", str(database), "--package", "P1", "--no-overlap"]
    )

    assert second.exit_code == 0, second.output
    connection = db.connect(database, init=False)
    try:
        rows = _rows(connection)
        assert rows["P2/a"]["duplicate_of"] is None
        assert rows["P2"]["duplicate_of"] is None
        assert rows["P1/a"]["duplicate_of"] is None
    finally:
        connection.close()


def test_cli_skips_report_above_pair_increment_limit(
    tmp_path: Path, overlap_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Path(str(overlap_conn.execute("PRAGMA database_list").fetchone()["file"]))
    overlap_conn.close()
    report = tmp_path / "folder_overlap.csv"
    monkeypatch.setattr(fold_hash, "MAX_PAIR_INCREMENTS", 0)

    result = runner.invoke(
        fold_hash.app, ["--db", str(database), "--overlap-csv", str(report)]
    )

    # Przekroczony limit to nie błąd: hashe i dedup i tak są zapisane.
    assert result.exit_code == 0, result.output
    assert "POMINIĘTE" in result.output
    assert not report.exists()
    connection = db.connect(database, init=False)
    try:
        assert connection.execute(
            "SELECT COUNT(*) AS n FROM folders WHERE tree_hash IS NOT NULL"
        ).fetchone()["n"] == 4
    finally:
        connection.close()
