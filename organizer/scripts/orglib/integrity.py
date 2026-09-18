"""Kontrole spójności: operacyjny indeks i niezmienność źródeł.

Dwie rzeczy w tym projekcie są nieodtwarzalne albo kosztowne do odtworzenia:
``00_SOURCES`` (materiały, których nikt już nie wyprodukuje) i ``organizer.sqlite``
(budowany przyrostowo przez wiele etapów, w przebiegach rozłożonych na tygodnie).
Testy pilnują KODU, ale nic nie pilnowało STANU tych dwóch.

* :func:`index_findings` — czy baza jest wewnętrznie spójna. Świadomie **nie**
  sprawdza tego, co już gwarantuje schemat: klucze obce (``PRAGMA
  foreign_keys=ON`` w :func:`orglib.db.connect`), unikalność ``(source_package,
  source_relative_path)`` i listy ``CHECK``. Powtarzanie tego byłoby teatrem.
  Sprawdza za to więzy, których SQLite wyrazić nie potrafi: ``files.sha256`` nie
  jest kluczem obcym, ``duplicate_of`` może tworzyć łańcuchy, a plik z głową
  tekstu może zniknąć z dysku niezależnie od bazy.
* :func:`sources_findings` — czy źródła są nadal takie, jakie zapisał skan.
  Guard w hookach pilnuje ZAMIARU (blokuje komendę); ta kontrola sprawdza
  SKUTEK — również zmiany wprowadzone poza agentami.

Obie funkcje tylko czytają. Zwracają listę :class:`Finding`; decyzja, co z tym
zrobić, należy do wołającego (CLI ``scripts/doctor.py``, sonda w testach).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from orglib import db, kinds

#: Waga znaleziska. ``error`` łamie niezmiennik, ``warning`` da się naprawić
#: komendą, ``info`` to obserwacja bez działania.
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")


@dataclass(frozen=True)
class Finding:
    """Jedno naruszenie (albo obserwacja) z kontroli spójności."""

    check: str
    detail: str
    count: int
    severity: str = "error"
    hint: str | None = None

    def __str__(self) -> str:
        prefix = {"error": "BŁĄD", "warning": "UWAGA", "info": "info"}[self.severity]
        tail = f" — {self.hint}" if self.hint else ""
        return f"{prefix} {self.check}: {self.detail} (n={self.count}){tail}"


def _count(conn: sqlite3.Connection, sql: str, *params: object) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if not isinstance(row, sqlite3.Row) else row[0])


def index_findings(conn: sqlite3.Connection, *, work_root: Path | None = None) -> list[Finding]:
    """Więzy indeksu, których schemat SQLite nie potrafi wyrazić.

    ``work_root`` włącza kontrolę plików z wyekstrahowanym tekstem: ścieżki
    w ``content.extracted_text_path`` są względne wobec katalogu ``work``.
    """
    findings: list[Finding] = []

    orphan_files = _count(
        conn,
        "SELECT COUNT(*) FROM files f WHERE f.sha256 IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM content c WHERE c.sha256 = f.sha256)",
    )
    if orphan_files:
        findings.append(Finding(
            "plik_bez_tresci",
            "pliki z sha256, dla których nie ma wiersza w content",
            orphan_files,
            hint="uruchom ponownie hash_files.py",
        ))

    hashed_without_sha = _count(
        conn,
        "SELECT COUNT(*) FROM files WHERE sha256 IS NULL AND status NOT IN ('discovered', 'error')",
    )
    if hashed_without_sha:
        findings.append(Finding(
            "status_bez_sha256",
            "pliki poza statusem 'discovered' bez policzonego sha256",
            hashed_without_sha,
        ))

    signatures_missing = _count(
        conn,
        "SELECT COUNT(*) FROM files f JOIN content c ON c.sha256 = f.sha256 "
        "WHERE f.status = 'extracted' AND c.extracted_text_path IS NOT NULL "
        "AND f.normalized_text_hash IS NULL",
    )
    if signatures_missing:
        findings.append(Finding(
            "brak_podpisow_tekstu",
            "pliki z wyekstrahowanym tekstem, ale bez normalized_text_hash",
            signatures_missing,
            hint="uruchom extract_text.py --force dla tych treści",
        ))

    # Wiszącego `duplicate_of` NIE sprawdzamy: pilnuje go klucz obcy
    # (sprawdzone — próba wstawienia takiego wiersza kończy się IntegrityError).
    # Łańcuchów i samowskazania FK już nie zabrania, więc te zostają.
    duplicate_chain = _count(
        conn,
        "SELECT COUNT(*) FROM folders d JOIN folders t ON t.folder_path = d.duplicate_of "
        "WHERE t.duplicate_of IS NOT NULL",
    )
    if duplicate_chain:
        findings.append(Finding(
            "lancuch_duplikatow",
            "duplicate_of wskazuje katalog, który sam jest duplikatem",
            duplicate_chain,
            hint="dedup ma wskazywać reprezentanta wprost; uruchom fold_hash.py ponownie",
        ))

    self_duplicate = _count(
        conn, "SELECT COUNT(*) FROM folders WHERE duplicate_of = folder_path"
    )
    if self_duplicate:
        findings.append(Finding(
            "duplikat_samego_siebie", "katalog wskazany jako własny duplikat", self_duplicate
        ))

    stale_kinds = 0
    expected: dict[str, str] = {}
    for row in conn.execute(
        "SELECT sha256, extension FROM files WHERE sha256 IS NOT NULL ORDER BY file_id"
    ):
        sha = str(row["sha256"])
        if sha not in expected:
            expected[sha] = kinds.content_kind_for(row["extension"])
    for row in conn.execute("SELECT sha256, content_kind FROM content"):
        sha = str(row["sha256"])
        if sha in expected and str(row["content_kind"] or "") != expected[sha]:
            stale_kinds += 1
    if stale_kinds:
        findings.append(Finding(
            "nieaktualny_content_kind",
            "treści, których rodzaj nie zgadza się z aktualną mapą rozszerzeń",
            stale_kinds,
            severity="warning",
            hint="db_admin.py refresh-kinds --apply",
        ))

    if work_root is not None:
        missing_text = 0
        for row in conn.execute(
            "SELECT extracted_text_path FROM content WHERE extracted_text_path IS NOT NULL"
        ):
            stored = str(row["extracted_text_path"])
            path = Path(stored)
            if not path.is_absolute():
                path = Path(work_root) / path
            if not path.is_file():
                missing_text += 1
        if missing_text:
            findings.append(Finding(
                "brak_pliku_tekstu",
                "wpisy content wskazujące nieistniejący plik z głową tekstu",
                missing_text,
                hint="uruchom extract_text.py ponownie (odtworzy brakujące pliki)",
            ))

    errors = _count(conn, "SELECT COUNT(*) FROM files WHERE status = 'error'")
    if errors:
        findings.append(Finding(
            "pliki_w_bledzie",
            "pliki pozostawione w statusie 'error'",
            errors,
            severity="info",
            hint="etap z opcją --retry-errors podejmie je ponownie",
        ))

    # Treść znana wyłącznie z repo docelowego (ground truth ze `scan_target.py`)
    # NIE ma wiersza w `files` i to jest poprawne — `files` opisuje źródła.
    # Zgłaszamy dopiero treść, do której nie prowadzi ani plik, ani wpis `applied`.
    orphan_content = _count(
        conn,
        "SELECT COUNT(*) FROM content c "
        "WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.sha256 = c.sha256) "
        "AND NOT EXISTS (SELECT 1 FROM applied a WHERE a.sha256 = c.sha256)",
    )
    if orphan_content:
        findings.append(Finding(
            "tresc_bez_pliku",
            "treści, do których nie prowadzi ani plik źródłowy, ani wpis applied",
            orphan_content,
            severity="info",
        ))

    return findings


def sources_findings(conn: sqlite3.Connection, sources_root: Path) -> list[Finding]:
    """Czy źródła są nadal takie, jakie zapisał skan (reguła twarda nr 1).

    Porównuje z dyskiem to, co indeks zapamiętał: istnienie katalogów i plików
    oraz ``size_bytes``/``modified_date`` każdego pliku. Wykrywa skasowanie,
    nadpisanie, obcięcie i samo dotknięcie pliku.

    Czego świadomie NIE wykrywa: plików DOPISANYCH do źródeł. Dorzucenie nowej
    paczki jest normalną pracą użytkownika, a nie szkodą — nowe katalogi
    najwyższego poziomu raportujemy tylko jako ``info``, żeby było wiadomo, że
    indeks jest nieaktualny.
    """
    findings: list[Finding] = []
    sources_root = Path(sources_root)

    missing_packages: list[str] = []
    for row in conn.execute("SELECT package_name FROM source_packages ORDER BY package_name"):
        if not (sources_root / str(row["package_name"])).is_dir():
            missing_packages.append(str(row["package_name"]))
    if missing_packages:
        findings.append(Finding(
            "brak_paczki",
            f"paczki zapisane w indeksie, których nie ma na dysku: {', '.join(missing_packages[:5])}",
            len(missing_packages),
        ))

    missing_folders = 0
    for row in conn.execute("SELECT folder_path FROM folders"):
        if not (sources_root / str(row["folder_path"])).is_dir():
            missing_folders += 1
    if missing_folders:
        findings.append(Finding(
            "brak_katalogu", "katalogi z indeksu nieobecne na dysku", missing_folders
        ))

    missing_files = 0
    changed_size = 0
    changed_mtime = 0
    for row in conn.execute(
        "SELECT source_package, source_relative_path, size_bytes, modified_date FROM files"
    ):
        resolved = config_resolve(sources_root, row)
        if resolved is None:
            continue
        try:
            stat_result = resolved.stat()
        except OSError:
            missing_files += 1
            continue
        if int(stat_result.st_size) != int(row["size_bytes"] or 0):
            changed_size += 1
        recorded = row["modified_date"]
        if recorded and db.mtime_iso(db.mtime_seconds(int(stat_result.st_mtime_ns))) != recorded:
            changed_mtime += 1

    if missing_files:
        findings.append(Finding(
            "brak_pliku", "pliki z indeksu nieobecne na dysku", missing_files
        ))
    if changed_size:
        findings.append(Finding(
            "zmieniony_rozmiar", "pliki o rozmiarze innym niż zapisany w indeksie", changed_size
        ))
    if changed_mtime:
        findings.append(Finding(
            "zmieniony_czas",
            "pliki o czasie modyfikacji innym niż zapisany w indeksie",
            changed_mtime,
            hint="samo dotknięcie pliku też łamie regułę read-only",
        ))

    known = {
        str(row["package_name"])
        for row in conn.execute("SELECT package_name FROM source_packages")
    }
    try:
        on_disk = {entry.name for entry in os.scandir(sources_root) if entry.is_dir()}
    except OSError:
        on_disk = set()
    new_packages = sorted(on_disk - known)
    if new_packages:
        findings.append(Finding(
            "nowa_paczka",
            f"katalogi w źródłach spoza indeksu: {', '.join(new_packages[:5])}",
            len(new_packages),
            severity="info",
            hint="uruchom scan.py, żeby je zaindeksować",
        ))

    return findings


def config_resolve(sources_root: Path, row: sqlite3.Row) -> Path | None:
    """Ścieżka pliku źródłowego z wiersza indeksu, z kontrolą wyjścia poza korzeń."""
    from orglib import config

    return config.resolve_within_sources(
        sources_root, str(row["source_package"]), str(row["source_relative_path"])
    )


def worst_severity(findings: list[Finding]) -> str | None:
    """Najcięższa waga w zestawie znalezisk albo ``None``, gdy nic nie znaleziono."""
    for severity in SEVERITIES:
        if any(finding.severity == severity for finding in findings):
            return severity
    return None
