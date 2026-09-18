"""Testy kontroli STANU: spójność indeksu i niezmienność źródeł.

Każdy test najpierw ustawia stan zdrowy, potem psuje JEDNĄ rzecz i wymaga
dokładnie tego znaleziska. Bez części „psujemy" kontrola mogłaby zawsze zwracać
pustą listę i wyglądać na działającą.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

import doctor
from orglib import db, integrity

runner = CliRunner()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture()
def workspace(tmp_path: Path):
    """Zdrowy, minimalny stan: dwa pliki w jednej paczce, zahashowane i wyekstrahowane."""
    sources = tmp_path / "sources"
    work = tmp_path / "work"
    text_dir = work / "extracted_text"
    text_dir.mkdir(parents=True)
    conn = db.connect(work / "organizer.sqlite")

    db.upsert(conn, "source_packages", {"package_name": "P1"}, conflict=("package_name",))
    db.upsert_folder(conn, {"folder_path": "P1", "source_package": "P1"})
    for name, payload in (("a.pdf", b"tresc-a"), ("b.txt", b"tresc-b")):
        target = sources / "P1" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        stat_result = target.stat()
        sha = _sha(payload)
        text_path = text_dir / f"{sha}.txt"
        text_path.write_text("glowa tekstu", encoding="utf-8")
        db.upsert_content(conn, {
            "sha256": sha,
            "content_kind": "pdf" if name.endswith(".pdf") else "text",
            "extracted_text_path": text_path.relative_to(work).as_posix(),
        })
        db.upsert_file(conn, {
            "source_package": "P1",
            "source_relative_path": name,
            "folder_path": "P1",
            "filename": name,
            "extension": name.rsplit(".", 1)[1],
            "size_bytes": stat_result.st_size,
            "modified_date": db.mtime_iso(db.mtime_seconds(int(stat_result.st_mtime_ns))),
            "sha256": sha,
            "normalized_text_hash": "n" * 64,
            "status": "extracted",
        })
    yield conn, sources, work
    conn.close()


# --------------------------------------------------------------------------- #
# Spójność indeksu
# --------------------------------------------------------------------------- #


def test_healthy_index_has_no_findings(workspace) -> None:
    """Punkt odniesienia: zdrowy stan nie może generować szumu."""
    conn, _, work = workspace
    assert integrity.index_findings(conn, work_root=work) == []


def test_detects_file_without_content_row(workspace) -> None:
    """`files.sha256` nie jest kluczem obcym — osieroconego pliku nie złapie schemat."""
    conn, _, work = workspace
    with conn:
        conn.execute("UPDATE files SET sha256 = ? WHERE filename = 'a.pdf'", ("f" * 64,))
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "plik_bez_tresci" in checks


def test_detects_status_without_hash(workspace) -> None:
    """Plik poza 'discovered' musi mieć sha256 — inaczej etapy dalej dostaną pustkę."""
    conn, _, work = workspace
    with conn:
        conn.execute("UPDATE content SET sha256 = sha256")  # bez zmian, tylko dla czytelności
        conn.execute("DELETE FROM files WHERE filename = 'b.txt'")
        conn.execute(
            "INSERT INTO files (source_package, source_relative_path, folder_path, size_bytes, "
            "status) VALUES ('P1', 'c.txt', 'P1', 1, 'extracted')"
        )
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "status_bez_sha256" in checks


def test_dangling_duplicate_is_already_impossible(workspace) -> None:
    """Kontrola granicy: wiszącego duplicate_of pilnuje KLUCZ OBCY, nie nasz kod.

    Test istnieje po to, żeby nikt nie dopisał do `integrity.py` kontroli, którą
    baza już wykonuje — powtarzanie gwarancji schematu to teatr, nie ochrona.
    """
    conn, _, _ = workspace
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO folders (folder_path, source_package, duplicate_of) "
                "VALUES ('P1/kopia', 'P1', 'P1/nie-ma')"
            )


def test_detects_chained_duplicates(workspace) -> None:
    """Łańcucha duplikatów FK nie zabrania, a psuje wybór reprezentanta w dedupie."""
    conn, _, work = workspace
    with conn:
        conn.execute("INSERT INTO folders (folder_path, source_package) VALUES ('P1/x', 'P1')")
        conn.execute(
            "INSERT INTO folders (folder_path, source_package, duplicate_of) "
            "VALUES ('P1/kopia', 'P1', 'P1/x')"
        )
        conn.execute("UPDATE folders SET duplicate_of = 'P1' WHERE folder_path = 'P1/x'")
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "lancuch_duplikatow" in checks


def test_detects_self_referencing_duplicate(workspace) -> None:
    """Katalog wskazany jako własny duplikat przechodzi przez FK, a jest bez sensu."""
    conn, _, work = workspace
    with conn:
        conn.execute("UPDATE folders SET duplicate_of = 'P1' WHERE folder_path = 'P1'")
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "duplikat_samego_siebie" in checks


def test_detects_missing_extracted_text_file(workspace) -> None:
    """Baza może wskazywać plik tekstu, którego ktoś posprzątał z 20_WORK."""
    conn, _, work = workspace
    next(iter((work / "extracted_text").glob("*.txt"))).unlink()
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "brak_pliku_tekstu" in checks


def test_detects_stale_content_kind(workspace) -> None:
    """Rodzaj treści rozjechany z mapą rozszerzeń — naprawialny komendą, więc 'warning'."""
    conn, _, work = workspace
    with conn:
        conn.execute("UPDATE content SET content_kind = 'archive' WHERE content_kind = 'pdf'")
    findings = {f.check: f for f in integrity.index_findings(conn, work_root=work)}
    assert "nieaktualny_content_kind" in findings
    assert findings["nieaktualny_content_kind"].severity == "warning"
    assert "refresh-kinds" in (findings["nieaktualny_content_kind"].hint or "")


def test_ground_truth_content_is_not_reported_as_orphan(workspace) -> None:
    """Treść znana tylko z repo docelowego NIE ma pliku źródłowego — i to jest poprawne."""
    conn, _, work = workspace
    sha = "d" * 64
    with conn:
        conn.execute("INSERT INTO content (sha256, content_kind) VALUES (?, 'pdf')", (sha,))
        conn.execute(
            "INSERT INTO applied (target_relative_path, sha256, action, plan_hash, applied_at) "
            "VALUES ('paczka/x.pdf', ?, 'copy', 'ground_truth:1:1', '2026-01-01T00:00:00Z')",
            (sha,),
        )
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "tresc_bez_pliku" not in checks

    with conn:  # ta sama treść bez wpisu applied to już sierota
        conn.execute("DELETE FROM applied WHERE sha256 = ?", (sha,))
    checks = {finding.check for finding in integrity.index_findings(conn, work_root=work)}
    assert "tresc_bez_pliku" in checks


# --------------------------------------------------------------------------- #
# Niezmienność źródeł (reguła twarda nr 1)
# --------------------------------------------------------------------------- #


def test_untouched_sources_have_no_findings(workspace) -> None:
    """Nietknięte źródła nie generują znalezisk — inaczej alarm straciłby znaczenie."""
    conn, sources, _ = workspace
    assert integrity.sources_findings(conn, sources) == []


def test_detects_deleted_source_file(workspace) -> None:
    """Skasowanie materiału to najcięższe naruszenie reguły read-only."""
    conn, sources, _ = workspace
    (sources / "P1" / "a.pdf").unlink()
    checks = {finding.check for finding in integrity.sources_findings(conn, sources)}
    assert "brak_pliku" in checks


def test_detects_overwritten_source_file(workspace) -> None:
    """Nadpisanie zmienia rozmiar — indeks pamięta, ile plik miał mieć."""
    conn, sources, _ = workspace
    (sources / "P1" / "a.pdf").write_bytes(b"zupelnie inna, dluzsza tresc")
    checks = {finding.check for finding in integrity.sources_findings(conn, sources)}
    assert "zmieniony_rozmiar" in checks


def test_detects_touched_source_file(workspace) -> None:
    """Samo dotknięcie pliku (ten sam rozmiar, inny mtime) też łamie regułę."""
    conn, sources, _ = workspace
    target = sources / "P1" / "b.txt"
    stat_result = target.stat()
    os.utime(target, (stat_result.st_atime, stat_result.st_mtime + 3600))
    checks = {finding.check for finding in integrity.sources_findings(conn, sources)}
    assert "zmieniony_czas" in checks


def test_detects_missing_package_directory(workspace) -> None:
    """Zniknięcie całej paczki jest raportowane osobno od pojedynczych plików."""
    conn, sources, _ = workspace
    for item in (sources / "P1").iterdir():
        item.unlink()
    (sources / "P1").rmdir()
    checks = {finding.check for finding in integrity.sources_findings(conn, sources)}
    assert "brak_paczki" in checks


def test_new_package_is_only_informational(workspace) -> None:
    """Dorzucenie nowej paczki to normalna praca użytkownika, nie szkoda."""
    conn, sources, _ = workspace
    (sources / "NowaPaczka").mkdir()
    findings = {f.check: f for f in integrity.sources_findings(conn, sources)}
    assert findings["nowa_paczka"].severity == "info"
    assert integrity.worst_severity(list(findings.values())) == "info"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_reports_clean_state_with_exit_zero(workspace, monkeypatch) -> None:
    """Zdrowy stan kończy się kodem 0 i słowem `czysto`."""
    conn, sources, work = workspace
    monkeypatch.setattr(doctor.config, "load_paths", lambda: _paths(sources, work))
    result = runner.invoke(doctor.app, ["all"])
    assert result.exit_code == 0, result.output
    assert result.output.count("czysto") == 2


def test_cli_exits_nonzero_on_violation(workspace, monkeypatch) -> None:
    """Naruszenie musi dać niezerowy kod wyjścia — inaczej nikt się nie dowie."""
    conn, sources, work = workspace
    (sources / "P1" / "a.pdf").unlink()
    monkeypatch.setattr(doctor.config, "load_paths", lambda: _paths(sources, work))
    result = runner.invoke(doctor.app, ["sources"])
    assert result.exit_code == 1, result.output
    assert "brak_pliku" in result.output


def test_cli_refuses_to_open_missing_database(tmp_path, monkeypatch) -> None:
    """Brak bazy to kod 2 (nie dało się wykonać kontroli), nie cichy sukces."""
    monkeypatch.setattr(doctor.config, "load_paths", lambda: _paths(tmp_path, tmp_path / "puste"))
    result = runner.invoke(doctor.app, ["index"])
    assert result.exit_code == 2
    assert "brak bazy" in result.output


def _paths(sources: Path, work: Path):
    from orglib import config

    return config.Paths(
        sources=sources, work=work, media=work / "media", target_repo=work / "target",
        target_paczka=work / "target" / "paczka", work_db=work / "organizer.sqlite",
        work_extracted_text=work / "extracted_text", work_thumbnails=work / "thumbs",
    )
