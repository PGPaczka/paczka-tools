"""Aplikacja FastAPI studia.

S0 = endpointy odczytu (dashboard, przedmioty, lista treści).
S1 = ``POST /api/decisions`` — zapis ręcznych decyzji przez ``orglib.decisions``.

Fabryka :func:`create_app` dostaje ścieżkę bazy, żeby test mógł podstawić własną,
a `just studio` nie musiał nic konfigurować. Sprawdzenie ``schema_version``
siedzi w ``lifespan``, nie w module: uvicorn z ``--reload`` importuje aplikację
w podprocesie, więc kontrola na poziomie importu milczałaby dokładnie w tym
trybie, w którym pracuje się najczęściej.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from orglib import config
from orglib.decisions import GroundTruthConflict, record_batch, record_decision, undo_last

from . import ORGANIZER_ROOT, database, queries

#: Zbudowany front (``npm --prefix studio/web run build``). Gdy go nie ma,
#: `/` tłumaczy, co uruchomić — zamiast odpowiadać 404 bez wyjaśnienia.
WEB_DIST: Path = ORGANIZER_ROOT / "studio" / "web" / "dist"

#: sha256 w ścieżce: 64 znaki hex. Wzorzec pilnuje, żeby do SQL nie trafiało
#: nic, co nie jest identyfikatorem treści (odpowiedź 422, nie zapytanie).
SHA256_PATTERN = r"^[0-9a-f]{64}$"

_PLACEHOLDER = """<!doctype html>
<html lang="pl"><meta charset="utf-8"><title>Paczka Studio</title>
<body style="font:16px/1.6 system-ui;max-width:42rem;margin:4rem auto;padding:0 1rem">
<h1>Paczka Studio</h1>
<p>Backend działa, ale nie ma zbudowanego frontu (<code>studio/web/dist</code>).</p>
<ul>
  <li><code>just studio-dev</code> — praca nad widokiem (Vite z proxy na to API),</li>
  <li><code>npm --prefix studio/web run build</code> + <code>just studio</code> — wersja zbudowana.</li>
</ul>
<p>API odpowiada pod <a href="/api/health">/api/health</a>.</p>
</body></html>"""


def create_app(
    db_path: Optional[Path] = None,
    *,
    paths: Optional[config.Paths] = None,
    subjects: Optional[list[config.Subject]] = None,
    thresholds: Optional[dict[str, Any]] = None,
) -> FastAPI:
    """Buduje aplikację czytającą wskazany indeks (domyślnie ``paths.yaml: work_db``)."""
    resolved_paths = paths if paths is not None else config.load_paths()
    database_path = Path(db_path) if db_path is not None else resolved_paths.work_db
    catalog = subjects if subjects is not None else config.iter_subjects()
    limits = thresholds if thresholds is not None else config.load_thresholds()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = database.open_readonly(database_path)
        try:
            app.state.schema_version = database.check_schema(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(
        title="Paczka Studio",
        summary="Widok do pracy nad paczką — faza S0 (tylko odczyt).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.db_path = database_path
    app.state.subjects = catalog
    app.state.thresholds = limits

    def get_conn() -> Iterator[sqlite3.Connection]:
        yield from database.connection(database_path)

    def get_rw_conn() -> Iterator[sqlite3.Connection]:
        conn = database.open_readwrite(database_path)
        try:
            yield conn
        finally:
            conn.close()

    @app.get("/api/health", tags=["studio"])
    def health() -> dict[str, Any]:
        """Czy backend widzi bazę i czy to ta wersja schematu, którą rozumie."""
        return {
            "status": "ok",
            "db": str(database_path),
            "schema_version": getattr(app.state, "schema_version", None),
            "read_only": True,
            "subjects": len(catalog),
        }

    @app.get("/api/subjects", tags=["subjects"])
    def get_subjects(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
        """Pulpit: globalne liczniki, przedmioty × etapy i kolejka „co następne”."""
        return queries.dashboard(conn, catalog, limits)

    @app.get("/api/subjects/{semester}/{skrot}", tags=["subjects"])
    def get_subject(
        semester: int = PathParam(ge=1, le=7),
        skrot: str = PathParam(min_length=1, max_length=64),
        grupa: Optional[str] = Query(
            None, description="Strumień/katedra — rozstrzyga kolizje skrótu w semestrze."
        ),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Jeden przedmiot: liczniki, kategorie, metody klasyfikacji, rozkład pewności."""
        try:
            subject = config.find_subject(semester, skrot, catalog, grupa=grupa)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            # Wieloznaczny skrót (np. SEM7 SI: KASK vs KT) — zgadywać nie wolno.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return queries.subject_detail(conn, subject, limits)

    @app.get("/api/items", tags=["items"])
    def get_items(
        semester: Optional[int] = Query(None, ge=1, le=7),
        skrot: Optional[str] = Query(None, max_length=64),
        category: Optional[str] = Query(None, max_length=64),
        action: Optional[str] = Query(None, pattern="^(copy|quarantine|skip|media)$"),
        file_status: Optional[str] = Query(None, max_length=32, alias="status"),
        content_kind: Optional[str] = Query(None, max_length=32, alias="kind"),
        needs_review: Optional[bool] = Query(None),
        classified: Optional[bool] = Query(None),
        confidence_min: Optional[float] = Query(None, ge=0.0, le=1.0),
        confidence_max: Optional[float] = Query(None, ge=0.0, le=1.0),
        include_ground_truth: bool = Query(False),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Treści po filtrach, w kolejności „co najpilniej wymaga oka”."""
        return queries.items(
            conn, semester=semester, skrot=skrot, category=category, action=action,
            file_status=file_status, content_kind=content_kind, needs_review=needs_review,
            classified=classified, confidence_min=confidence_min, confidence_max=confidence_max,
            include_ground_truth=include_ground_truth, thresholds=limits,
            limit=limit, offset=offset,
        )

    @app.get("/api/items/{sha256}", tags=["items"])
    def get_item(
        sha256: str = PathParam(pattern=SHA256_PATTERN),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Jedna treść: decyzja, wszystkie kopie, relacje, plan i ślad po apply."""
        detail = queries.item_detail(conn, sha256, limits)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"brak treści {sha256} w indeksie")
        return detail

    # --- S1: preview ---

    @app.get("/api/preview/{sha256}", tags=["preview"])
    def get_preview(
        sha256: str = PathParam(pattern=SHA256_PATTERN),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Podgląd treści (S1.3): głowa tekstu, metadane. Bez miniatur jeśli brak plików."""
        row = conn.execute(
            "SELECT sha256, content_kind, extracted_text_path, cas_path "
            "FROM content WHERE sha256 = ?", (sha256,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"brak treści {sha256}")

        text_head = None
        text_path = row["extracted_text_path"]
        if text_path:
            resolved = Path(text_path)
            try:
                real = resolved.resolve(strict=True)
            except (OSError, ValueError):
                real = None
            if real and real.is_file():
                try:
                    text_head = real.read_text(encoding="utf-8", errors="replace")[:4096]
                except OSError:
                    pass

        return {
            "sha256": sha256,
            "content_kind": row["content_kind"],
            "text_head": text_head,
            "has_text": text_head is not None,
            "has_thumbnail": False,
        }

    # --- S1: decisions (write endpoints) ---

    @app.post("/api/decisions", tags=["decisions"])
    def post_decision(
        body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Zapisuje jedną ręczną decyzję (S1.2)."""
        try:
            sha256 = body["sha256"]
            decision_type = body["decision_type"]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"brak wymaganego pola: {exc}") from exc
        try:
            result = record_decision(
                conn,
                sha256=sha256,
                decision_type=decision_type,
                decided_by=body.get("decided_by", "studio"),
                semester=body.get("semester"),
                subject_key=body.get("subject_key"),
                category=body.get("category"),
                target_relative_path=body.get("target_relative_path"),
                action=body.get("action"),
                relation_override=body.get("relation_override"),
                note=body.get("note"),
            )
            conn.commit()
            return result
        except GroundTruthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/decisions/batch", tags=["decisions"])
    def post_decisions_batch(
        body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Zapisuje partię decyzji atomowo (S1.6)."""
        decisions = body.get("decisions", [])
        decided_by = body.get("decided_by", "studio")
        if not decisions:
            raise HTTPException(status_code=422, detail="pusta lista decyzji")
        try:
            results = record_batch(conn, decisions, decided_by=decided_by)
            return {"count": len(results), "decisions": results}
        except GroundTruthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/decisions/undo", tags=["decisions"])
    def post_undo(
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Cofa ostatnią decyzję (S1.7)."""
        undone = undo_last(conn)
        if undone is None:
            raise HTTPException(status_code=404, detail="brak decyzji do cofnięcia")
        return {"undone": undone}

    @app.get("/api/decisions/by-folder", tags=["decisions"])
    def get_items_by_folder(
        folder: str = Query(..., min_length=1),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Treści z danego katalogu źródłowego — podgląd przed decyzją hurtową (S1.6)."""
        return queries.items_by_folder(conn, folder, limits)

    @app.post("/api/decisions/by-folder", tags=["decisions"])
    def post_decisions_by_folder(
        body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Decyzja hurtowa dla wszystkich treści z katalogu źródłowego (S1.6)."""
        folder = body.get("folder")
        decision_type = body.get("decision_type", "skip")
        decided_by = body.get("decided_by", "studio")
        if not folder:
            raise HTTPException(status_code=422, detail="brak pola folder")
        preview = queries.items_by_folder(conn, folder, limits)
        decisions = [
            {"sha256": item["sha256"], "decision_type": decision_type,
             **({k: body[k] for k in ("semester", "subject_key", "category", "action") if k in body})}
            for item in preview["items"]
            if item.get("run_id") != "ground_truth"
        ]
        if not decisions:
            raise HTTPException(status_code=404, detail=f"brak treści w katalogu {folder}")
        try:
            results = record_batch(conn, decisions, decided_by=decided_by)
            return {"folder": folder, "count": len(results), "decisions": results}
        except GroundTruthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # --- S2: clusters ---

    @app.get("/api/clusters", tags=["clusters"])
    def get_clusters(
        semester: Optional[int] = Query(None, ge=1, le=7),
        skrot: Optional[str] = Query(None, max_length=64),
        noise: Optional[str] = Query(None, description="Wzorce szumu oddzielone przecinkiem (fnmatch)"),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Klastry near-dupe (S2.1): grupy treści powiązanych relacjami."""
        noise_patterns = [p.strip() for p in noise.split(",") if p.strip()] if noise else []
        return queries.clusters(
            conn, semester=semester, skrot=skrot,
            noise_patterns=noise_patterns, thresholds=limits,
        )

    @app.get("/api/clusters/diff", tags=["clusters"])
    def get_cluster_diff(
        left: str = Query(..., pattern=SHA256_PATTERN),
        right: str = Query(..., pattern=SHA256_PATTERN),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Porównanie dwóch treści z klastra (S2.3): metadane + głowy tekstu."""
        result = queries.cluster_diff(conn, left, right, thresholds=limits)
        if result is None:
            raise HTTPException(status_code=404, detail="nie znaleziono jednej lub obu treści")
        return result

    @app.post("/api/clusters/resolve", tags=["clusters"])
    def resolve_cluster(
        body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Rozstrzyga klaster: kanoniczna treść zostaje, reszta → skip/older_version (S2.4)."""
        canonical_sha = body.get("canonical_sha256")
        members = body.get("members", [])
        if not canonical_sha or not members:
            raise HTTPException(status_code=422, detail="brak canonical_sha256 lub members")
        if canonical_sha not in members:
            raise HTTPException(status_code=422, detail="canonical_sha256 musi być w members")

        decisions = []
        for sha in members:
            if sha == canonical_sha:
                continue
            decisions.append({
                "sha256": sha,
                "decision_type": "skip",
                "note": f"duplikat kanoniczny: {canonical_sha[:16]}…",
            })
        decided_by = body.get("decided_by", "studio")
        try:
            results = record_batch(conn, decisions, decided_by=decided_by)
            return {"canonical": canonical_sha, "skipped": len(results), "decisions": results}
        except GroundTruthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/queue", tags=["decisions"])
    def get_queue(
        semester: Optional[int] = Query(None, ge=1, le=7),
        skrot: Optional[str] = Query(None, max_length=64),
        limit: int = Query(1, ge=1, le=100),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Następna pozycja do przeglądu (S1.4): treść z najniższą pewnością i needs_review=1."""
        return queries.items(
            conn, semester=semester, skrot=skrot,
            needs_review=True, thresholds=limits,
            limit=limit, offset=0,
        )

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(_PLACEHOLDER)

    return app
