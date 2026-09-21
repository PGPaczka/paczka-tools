"""E2E: cały łańcuch etapów na syntetycznej paczce, od skanu po plan AI.

Każdy etap ma własne testy jednostkowe, ale **styków między etapami nie pilnował
nikt**: statusów, które musi zastać następny skrypt, ścieżek zapisywanych
w bazie, pól kontraktu JSONL między `prepare_subject` a `ai_resolve`. To
tutaj wychodzą rozjazdy, których atrapa w teście pojedynczego etapu nie pokaże —
na przykład to, że `text_head` z etapu extract faktycznie dociera do manifestu,
a nie tylko „istnieje w kodzie”.

Cała praca dzieje się w `tmp_path`: syntetyczne źródła, syntetyczne repo
docelowe, własny `paths.yaml`. Żaden prawdziwy katalog materiałów nie jest
czytany. Model AI nie jest wołany — backend dostaje atrapę runnera, więc
przebieg jest deterministyczny i darmowy.

Marker `e2e` (patrz `pytest.ini`, recepta `just e2e`).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

import ai_resolve
import classify
import dedup_report
import extract_text
import fold_hash
import hash_files
import prepare_subject
import scan
from orglib import config, llm_client

pytestmark = pytest.mark.e2e

runner = CliRunner()

#: Treść PDF-u wykładu — bez polskich znaków, bo wbudowana czcionka PyMuPDF ich nie ma.
WYKLAD_TEXT = "Wyklad 1: architektura komputerow, lista rozkazow, potok instrukcji"


def _pdf(path: Path, text: str) -> None:
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 60), text, fontsize=11)
        document.save(path)


def _docx(path: Path, text: str) -> None:
    import docx

    path.parent.mkdir(parents=True, exist_ok=True)
    document = docx.Document()
    document.add_paragraph(text)
    document.save(path)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Paths:
    """Syntetyczny workspace: własny paths.yaml, realny loader, zero prawdziwych materiałów."""
    data = config.load_yaml("paths")
    for key in ("sources", "work", "media", "target_repo"):
        root = tmp_path / key
        root.mkdir()
        data[key] = str(root)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "paths.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    paths = config.load_paths(config_dir)
    for module in (scan, hash_files, fold_hash, dedup_report, extract_text,
                   prepare_subject, classify):
        monkeypatch.setattr(module.config, "load_paths", lambda: paths, raising=False)
    monkeypatch.setattr(config, "load_paths", lambda config_dir=None: paths)
    monkeypatch.setattr(config, "ORGANIZER_ROOT", tmp_path / "organizer")
    return paths


@pytest.fixture()
def sources(workspace: config.Paths) -> config.Paths:
    """Dwie paczki źródłowe: jedna oryginalna, druga z pełną kopią katalogu przedmiotu.

    Taki układ odtwarza realny problem projektu (nakładające się paczki) i pozwala
    sprawdzić, że dedup katalogów faktycznie oszczędza pracę kolejnym etapom.
    """
    root = workspace.sources
    _pdf(root / "PaczkaA" / "SEM3" / "AKO" / "wyklad1.pdf", WYKLAD_TEXT)
    _docx(root / "PaczkaA" / "SEM3" / "AKO" / "lab1.docx", "Laboratorium 1: asembler i rejestry")
    (root / "PaczkaA" / "SEM3" / "AKO" / "notatki.txt").write_text(
        "notatki z cwiczen AKO, rok 2021", encoding="utf-8"
    )
    (root / "PaczkaA" / "SEM3" / "AKO" / "Thumbs.db").write_bytes(b"smieci windows")
    (root / "PaczkaA" / "SEM3" / "AKO" / "archiwum.zip").write_bytes(b"PK\x03\x04udawane")

    # PaczkaB: dokładna kopia katalogu przedmiotu (te same treści, te same nazwy).
    kopia = root / "PaczkaB" / "kopia_zapasowa" / "AKO"
    kopia.mkdir(parents=True)
    for item in (root / "PaczkaA" / "SEM3" / "AKO").iterdir():
        kopia.joinpath(item.name).write_bytes(item.read_bytes())
    return workspace


def _stage(app: Any, *args: str) -> None:
    """Uruchamia etap i wymaga kodu wyjścia 0 — etap, który padł, przerywa łańcuch."""
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"etap padł: {args}\n{result.output}\n{result.exception}"


@pytest.fixture()
def pipeline(sources: config.Paths) -> config.Paths:
    """Przepuszcza syntetyczną paczkę przez cały deterministyczny łańcuch."""
    paths = sources
    db = str(paths.work_db)
    _stage(scan.app, "--db", db, "--sources", str(paths.sources))
    _stage(hash_files.app, "--db", db, "--sources", str(paths.sources))
    _stage(fold_hash.app, "--db", db)
    _stage(
        extract_text.app, "--db", db, "--sources", str(paths.sources),
        "--text-dir", str(paths.work_extracted_text), "--no-ocr",
    )
    return paths


def _rows(paths: config.Paths, sql: str, *params: Any) -> list[sqlite3.Row]:
    conn = sqlite3.connect(paths.work_db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_pipeline_moves_every_file_to_extracted(pipeline: config.Paths) -> None:
    """Po pełnym przebiegu żaden plik nie zostaje w statusie pośrednim ani w błędzie."""
    statuses = {
        row["status"]: row["n"]
        for row in _rows(pipeline, "SELECT status, COUNT(*) n FROM files GROUP BY status")
    }
    assert statuses.get("error", 0) == 0, f"etapy zostawiły błędy: {statuses}"
    assert statuses.get("discovered", 0) == 0, "coś nie zostało zahashowane"
    assert set(statuses) <= {"extracted", "hashed"}, statuses


def test_windows_junk_never_enters_the_index(pipeline: config.Paths) -> None:
    """Śmieci systemowe nie mogą stać się materiałem — zostają odsiane już na skanie."""
    assert _rows(pipeline, "SELECT 1 FROM files WHERE lower(filename) = 'thumbs.db'") == []


def test_duplicate_folder_is_detected_and_skipped_by_later_stages(pipeline: config.Paths) -> None:
    """Kopia katalogu jest oznaczona jako duplikat, a extract jej nie przerabia.

    Styk trzech etapów: fold_hash ustawia `duplicate_of`, `db.files_pending`
    wycina poddrzewo, a extract_text nigdy go nie widzi. Pojedynczy test etapu
    tego nie pokaże.
    """
    duplicates = _rows(pipeline, "SELECT folder_path FROM folders WHERE duplicate_of IS NOT NULL")
    assert duplicates, "kopia katalogu nie została rozpoznana jako duplikat"
    skipped = _rows(
        pipeline,
        "SELECT f.status FROM files f JOIN folders d ON f.folder_path = d.folder_path "
        "WHERE d.duplicate_of IS NOT NULL",
    )
    assert skipped and all(row["status"] == "hashed" for row in skipped), (
        "pliki w duplikacie katalogu nie powinny przechodzić etapu extract"
    )


def test_identical_content_is_extracted_once_across_packages(pipeline: config.Paths) -> None:
    """Ta sama treść w dwóch paczkach ma JEDEN plik tekstu — dedup oszczędza pracę."""
    texts = list(pipeline.work_extracted_text.glob("*.txt"))
    contents = _rows(pipeline, "SELECT sha256 FROM content WHERE extracted_text_path IS NOT NULL")
    assert len(texts) == len(contents)
    for path in texts:
        assert path.stem in {row["sha256"] for row in contents}


def test_manifest_carries_text_head_from_the_extract_stage(pipeline: config.Paths) -> None:
    """Kontrakt B2 -> B1 -> B5: treść wyekstrahowana wcześniej dociera do manifestu.

    To jest cały sens etapu extract: bez `text_head` klasyfikator AI widzi samą
    nazwę pliku. Ten styk łączy trzy skrypty i nie był pilnowany przez nic.
    """
    out_dir = pipeline.work / "manifest"
    _stage(
        prepare_subject.app, "--semester", "3", "--skrot", "AKO",
        "--db", str(pipeline.work_db), "--out-dir", str(out_dir),
    )
    rows = [
        json.loads(line)
        for line in (out_dir / "manifest_slice.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows, "manifest przedmiotu jest pusty — dopasowanie ścieżek nie zadziałało"
    with_text = [row for row in rows if row.get("text_head")]
    assert with_text, "żadna pozycja nie dostała text_head mimo wykonanego etapu extract"
    wyklad = next(row for row in rows if row["source_path"].endswith("wyklad1.pdf"))
    assert "architektura" in wyklad["text_head"].lower()
    # Provenance: obie kopie treści są wymienione, mimo że przerabialiśmy jedną.
    assert len(wyklad["source_paths"]) == 2


def test_deterministic_stage_decides_what_ai_never_sees(pipeline: config.Paths) -> None:
    """Kontrakt B1 -> B3 -> B5: model dostaje DOKŁADNIE to, czego reguły nie rozstrzygnęły.

    Styk, którego nie widać w testach pojedynczych skryptów: plan deterministyczny
    jest dla `ai_resolve` listą „tego już nie pytaj”, a `unresolved.jsonl` ma
    zachować kształt manifestu, żeby dało się go podać modelowi wprost.
    """
    out_dir = pipeline.work / "manifest"
    _stage(
        prepare_subject.app, "--semester", "3", "--skrot", "AKO",
        "--db", str(pipeline.work_db), "--out-dir", str(out_dir),
    )
    manifest_path = out_dir / "manifest_slice.jsonl"
    _stage(
        classify.app, "--semester", "3", "--skrot", "AKO",
        "--db", str(pipeline.work_db), "--manifest", str(manifest_path),
        "--out-dir", str(out_dir),
    )
    # Schemat czytamy przez ai_resolve, bo `config.ORGANIZER_ROOT` jest w tym teście
    # przestawiony na katalog tymczasowy — ścieżka do repo jest zamrożona przy imporcie.
    import jsonschema

    schema = ai_resolve.load_schema()
    plan = [
        json.loads(line)
        for line in (out_dir / "plan.det.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert plan, "etap deterministyczny nie rozstrzygnął niczego"
    for row in plan:
        jsonschema.validate(row, schema)

    by_name = {
        Path(row["target_rel"]).name: row for row in plan if row["action"] == "copy"
    }
    assert by_name["lab1.docx"]["category"] == "laboratoria"
    assert by_name["wyklad1.pdf"]["category"] == "wyklad"

    manifest = ai_resolve.read_jsonl(manifest_path)
    unresolved = ai_resolve.read_jsonl(out_dir / "unresolved.jsonl")
    resolved = ai_resolve.existing_hashes(out_dir / "plan.det.jsonl")
    queue = ai_resolve.select_rows(manifest, resolved=resolved, take_all=False, only_review=False)

    assert {row["sha256"] for row in queue} == {row["sha256"] for row in unresolved}
    assert resolved.isdisjoint({row["sha256"] for row in unresolved})
    # Archiwum bez sygnału w nazwie i bez tekstu to typowa resztka dla modelu.
    assert any(
        row["source_path"].endswith("archiwum.zip") for row in unresolved
    ), [row["source_path"] for row in unresolved]


def test_ai_resolve_consumes_manifest_and_writes_valid_plan(
    pipeline: config.Paths, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ostatni styk: manifest -> klasyfikator -> plan zgodny z realnym schematem.

    Model nie jest wołany: backend dostaje atrapę runnera zwracającą decyzję
    w formacie, którego oczekuje `codex_cli`. Sprawdzamy, że linie planu
    przechodzą walidację REALNYM `prompts/plan_line.schema.json`.
    """
    import jsonschema

    out_dir = pipeline.work / "manifest"
    _stage(
        prepare_subject.app, "--semester", "3", "--skrot", "AKO",
        "--db", str(pipeline.work_db), "--out-dir", str(out_dir),
    )
    manifest = [
        json.loads(line)
        for line in (out_dir / "manifest_slice.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Udaje `codex exec`: zapisuje decyzję do pliku wskazanego przez `-o`."""
        decision = {
            "schema_version": 1,
            "source_sha256": "0" * 64,  # nadpisywane przez ai_resolve z manifestu
            "action": "copy",
            "target_rel": "paczka/SEM3/AKO_Architektura_Komputerow/wyklad/plik.pdf",
            "category": "wyklad",
            "year": None,
            "related_to": None,
            "relation": None,
            "confidence": 0.95,
            "method": "llm",
            "model": "atrapa",
            "reason": "test e2e",
            "needs_review": False,
        }
        if "-o" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps(decision), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(decision), stderr="")

    original_init = llm_client.LLMClient.__init__

    def patched_init(self: Any, cfg: Any, **kwargs: Any) -> None:
        kwargs["runner"] = fake_runner
        kwargs.setdefault("cache_path", tmp_path / "ai-cache.sqlite")
        original_init(self, cfg, **kwargs)

    monkeypatch.setattr(llm_client.LLMClient, "__init__", patched_init)
    monkeypatch.setattr(ai_resolve, "LLMClient", llm_client.LLMClient, raising=False)

    _stage(
        ai_resolve.app, "--semester", "3", "--skrot", "AKO",
        "--manifest", str(out_dir / "manifest_slice.jsonl"),
        "--output", str(out_dir / "plan.ai.jsonl"), "--all",
    )

    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "prompts" / "plan_line.schema.json").read_text(
            encoding="utf-8"
        )
    )
    lines = [
        json.loads(line)
        for line in (out_dir / "plan.ai.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, "klasyfikator nie zapisał ani jednej linii planu"
    known = {row["sha256"] for row in manifest}
    for line in lines:
        jsonschema.validate(line, schema)
        assert line["source_sha256"] in known, (
            "plan odnosi się do treści spoza manifestu — model nie może podmienić tożsamości"
        )


def test_plan_from_b7_can_actually_be_applied_and_verified(
    pipeline: config.Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Styk B7 → B8 → B10 → B11: plan zbudowany przez potok da się WYKONAĆ.

    Każdy z tych etapów ma własne testy na własnym, ręcznie napisanym planie.
    Dopiero tutaj plan pochodzi z `build_plan`, a nie z fixture'u — czyli sprawdzamy,
    że kształt, który produkuje potok, jest tym, który przyjmuje `apply`: ścieżki
    docelowe wobec repo, `source_sha256` odnajdywalne w `files`, odcisk planu
    zgodny między nagłówkiem a wykonaniem.

    Materiały lądują w syntetycznym repo w `tmp_path`; `--no-git`, bo gałąź
    przedmiotu sprawdzają testy B10, a tutaj chodzi o styk etapów.
    """
    import apply as apply_cli
    import build_plan
    import validate_plan
    import verify as verify_cli
    from orglib.hashes import sha256_file

    for module in (build_plan, validate_plan, apply_cli, verify_cli):
        monkeypatch.setattr(module.config, "load_paths", lambda: pipeline, raising=False)

    out_dir = pipeline.work / "manifest"
    _stage(prepare_subject.app, "--semester", "3", "--skrot", "AKO",
           "--db", str(pipeline.work_db), "--out-dir", str(out_dir))
    _stage(classify.app, "--semester", "3", "--skrot", "AKO",
           "--db", str(pipeline.work_db), "--manifest", str(out_dir / "manifest_slice.jsonl"),
           "--out-dir", str(out_dir))
    _stage(build_plan.app, "--semester", "3", "--skrot", "AKO",
           "--db", str(pipeline.work_db), "--manifest", str(out_dir / "manifest_slice.jsonl"),
           "--out-dir", str(out_dir))

    plan_path = out_dir / "plan.jsonl"
    plan_rows = [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines()]
    meta = next(row["_meta"] for row in plan_rows if "_meta" in row)
    copies = [row for row in plan_rows if row.get("action") == "copy"]
    assert copies, "plan nie ma czego skopiować — dalsze etapy nie miałyby sensu"

    # Bramka B8 na planie z potoku: dopiero jej zielone światło uprawnia do apply.
    _stage(validate_plan.app, "--semester", "3", "--skrot", "AKO",
           "--db", str(pipeline.work_db), "--plan", str(plan_path))

    # Dry-run niczego nie kopiuje, ale zostawia snapshot z odciskiem planu.
    _stage(apply_cli.app, "--semester", "3", "--skrot", "AKO", "--db", str(pipeline.work_db),
           "--plan", str(plan_path), "--no-git")
    assert not list(pipeline.target_paczka.rglob("*")), "dry-run dotknął repo paczki"
    snapshot = json.loads((plan_path.parent / "apply_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["plan_hash"] == meta["plan_hash"]

    # Wykonanie przypięte do odcisku, który zaakceptowałby człowiek.
    _stage(apply_cli.app, "--semester", "3", "--skrot", "AKO", "--db", str(pipeline.work_db),
           "--plan", str(plan_path), "--no-git", "--yes", "--expect-hash", meta["plan_hash"])

    for row in copies:
        target = pipeline.target_repo / row["target_rel"]
        assert target.is_file(), f"plan obiecał {row['target_rel']}, a pliku nie ma"
        assert sha256_file(target) == row["source_sha256"]

    _stage(verify_cli.app, "--semester", "3", "--skrot", "AKO", "--db", str(pipeline.work_db),
           "--plan", str(plan_path))

    statuses = {
        str(row["status"]) for row in _rows(pipeline, "SELECT status FROM files WHERE sha256 IN "
                                            f"({','.join('?' * len(copies))})",
                                            *[row["source_sha256"] for row in copies])
    }
    assert statuses == {"verified"}
