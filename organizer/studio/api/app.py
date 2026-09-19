"""Aplikacja FastAPI studia. Faza S0: każdy endpoint jest tylko do odczytu.

Fabryka :func:`create_app` dostaje ścieżkę bazy, żeby test mógł podstawić własną,
a `just studio` nie musiał nic konfigurować. Sprawdzenie ``schema_version``
siedzi w ``lifespan``, nie w module: uvicorn z ``--reload`` importuje aplikację
w podprocesie, więc kontrola na poziomie importu milczałaby dokładnie w tym
trybie, w którym pracuje się najczęściej.

Czego tu NIE ma i mieć nie będzie w tej fazie: jakiegokolwiek endpointu zapisu,
CORS-a (dev działa przez proxy Vite, więc przeglądarka i tak widzi jedno
źródło) i serwowania plików źródłowych (to S1.3, z containmentem ścieżek).
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from orglib import config

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

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(_PLACEHOLDER)

    return app
