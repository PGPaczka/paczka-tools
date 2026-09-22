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

from fastapi import Body, Depends, FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from orglib import config, graph_link
from orglib.classify import load_rules
from orglib.decisions import GroundTruthConflict, record_batch, record_decision, undo_last

from . import ORGANIZER_ROOT, database, planning, queries, runner

#: Zbudowany front (``npm --prefix studio/web run build``). Gdy go nie ma,
#: `/` tłumaczy, co uruchomić — zamiast odpowiadać 404 bez wyjaśnienia.
WEB_DIST: Path = ORGANIZER_ROOT / "studio" / "web" / "dist"

#: Zbudowany viewer synapse (S4.1). Źródła są w repo (`studio/graf/`), ale `dist/`
#: powstaje z builda, więc jego brak to normalny stan świeżego klona — `/graf`
#: tłumaczy wtedy, co uruchomić.
VIEWER_DIST: Path = ORGANIZER_ROOT / "studio" / "graf" / "synapse-viewer" / "dist"

#: Artefakty generatora grafu. Szukamy ich WYŁĄCZNIE w `work`, gdzie pisze je
#: `just studio-graf`. Vendorowany viewer ma w `public/` własny, przykładowy graf
#: (17 kB, dane demo upstreamu) — gdyby był w łańcuchu awaryjnym, studio po cichu
#: pokazywałoby cudzy graf zamiast powiedzieć, że naszego jeszcze nie ma.
_GRAPH_ARTIFACTS = ("graph.json", "search-index.json")

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


_GRAF_PLACEHOLDER = """<!doctype html>
<html lang="pl"><meta charset="utf-8"><title>Graf — Paczka Studio</title>
<body style="font:16px/1.6 system-ui;max-width:42rem;margin:4rem auto;padding:0 1rem">
<h1>Graf nie jest zbudowany</h1>
<p>Studio osadza <strong>zbudowany viewer synapse</strong>. Źródła są w repo
(<code>studio/graf/</code>), ale <code>dist/</code> powstaje z builda.</p>
<pre><code>just studio-graf</code></pre>
<p>Recepta eksportuje vault z indeksu, uruchamia generator i buduje viewer pod
adres <code>/graf</code>. Wymaga toolchainu .NET (generator) i node (viewer).</p>
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
        """Podgląd treści (S1.3): głowa tekstu z `work` + co da się narysować.

        Ścieżki idą przez `config.resolve_within` — wpis prowadzący poza `work`
        (bezwzględny, `..`, dowiązanie) nie jest czytany.
        """
        detail = queries.preview(conn, sha256, resolved_paths)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"brak treści {sha256}")
        return detail

    @app.get("/api/preview/{sha256}/image", tags=["preview"])
    def get_preview_image(
        sha256: str = PathParam(pattern=SHA256_PATTERN),
        page: int = Query(1, ge=1, le=9999, description="Strona PDF (1 = pierwsza)."),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> Response:
        """Strona PDF jako PNG albo miniatura obrazu — wyłącznie z plików z indeksu."""
        rendered = queries.preview_image(conn, sha256, resolved_paths, page=page)
        if rendered is None:
            raise HTTPException(
                status_code=404, detail=f"brak podglądu dla {sha256} (nie ma kopii na dysku?)"
            )
        payload, media_type = rendered
        # Treść jest adresowana sha256, więc nigdy się nie zmienia pod tym adresem.
        return Response(
            content=payload,
            media_type=media_type,
            headers={"cache-control": "private, max-age=86400"},
        )

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
        result = queries.cluster_diff(conn, left, right, resolved_paths, thresholds=limits)
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

    # --- S4: history, search, stats ---

    @app.get("/api/decisions/history", tags=["decisions"])
    def get_decision_history(
        decided_by: Optional[str] = Query(None),
        since: Optional[str] = Query(None, description="ISO-8601 date, np. 2026-09-19"),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Historia ręcznych decyzji (S4.2)."""
        return queries.decision_history(
            conn, decided_by=decided_by, since=since, limit=limit, offset=offset,
        )

    @app.delete("/api/decisions/{sha256}", tags=["decisions"])
    def delete_decision(
        sha256: str = PathParam(pattern=SHA256_PATTERN),
        conn: sqlite3.Connection = Depends(get_rw_conn),
    ) -> dict[str, Any]:
        """Cofa konkretną decyzję po sha256 (S4.2)."""
        row = conn.execute(
            "SELECT * FROM manual_decisions WHERE sha256 = ?", (sha256,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"brak decyzji dla {sha256[:16]}…")
        with conn:
            conn.execute("DELETE FROM manual_decisions WHERE sha256 = ?", (sha256,))
            existing = conn.execute(
                "SELECT run_id FROM classifications WHERE sha256 = ?", (sha256,)
            ).fetchone()
            if existing and str(existing["run_id"]) == "manual_decision":
                conn.execute("DELETE FROM classifications WHERE sha256 = ?", (sha256,))
        return {"undone": dict(row)}

    @app.get("/api/search", tags=["search"])
    def get_search(
        q: str = Query(..., min_length=1, max_length=200),
        limit: int = Query(50, ge=1, le=200),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Wyszukiwanie przekrojowe (S4.3)."""
        return queries.search(conn, q, thresholds=limits, limit=limit)

    @app.get("/api/stats", tags=["stats"])
    def get_stats(
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Statystyki na żywo — odpowiednik STATUS.md (S4.4)."""
        return queries.live_stats(conn, catalog, limits)

    # --- S3: plan, bramka i wykonanie ------------------------------------
    #
    # Bramka jest po stronie SERWERA. Widok może sobie wyszarzyć przycisk, ale to
    # nie jest zabezpieczenie: żądanie `apply` przy planie odrzuconym przez bramkę
    # kończy się tutaj kodem 409 i **żaden podproces nie startuje**
    # (`studio/AGENTS.md`, reguła 6).

    def _subject_or_http(semester: int, skrot: str, grupa: Optional[str]) -> config.Subject:
        try:
            return config.find_subject(semester, skrot, catalog, grupa=grupa)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/plan/{semester}/{skrot}", tags=["plan"])
    def get_plan(
        semester: int = PathParam(ge=1, le=7),
        skrot: str = PathParam(min_length=1, max_length=64),
        grupa: Optional[str] = Query(None),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Plan przedmiotu: nagłówek, ustalenia bramki i co `apply` zrobiłby z dyskiem."""
        subject = _subject_or_http(semester, skrot, grupa)
        return planning.overview(
            conn, subject, catalog, resolved_paths,
            rules=load_rules(), thresholds=limits,
        )

    @app.get("/api/plan/{semester}/{skrot}/tree", tags=["plan"])
    def get_plan_tree(
        semester: int = PathParam(ge=1, le=7),
        skrot: str = PathParam(min_length=1, max_length=64),
        grupa: Optional[str] = Query(None),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Drzewo docelowe przedmiotu + lista tego, co nie ma jeszcze miejsca."""
        subject = _subject_or_http(semester, skrot, grupa)
        return planning.target_tree(conn, subject, catalog, resolved_paths)

    @app.post("/api/plan/{semester}/{skrot}/run", tags=["plan"])
    def run_stage(
        semester: int = PathParam(ge=1, le=7),
        skrot: str = PathParam(min_length=1, max_length=64),
        grupa: Optional[str] = Query(None),
        body: dict[str, Any] = Body(...),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> StreamingResponse:
        """Uruchamia etap potoku jako podproces CLI i strumieniuje jego wyjście (SSE)."""
        subject = _subject_or_http(semester, skrot, grupa)
        stage = str(body.get("stage") or "")
        if stage not in runner.STAGE_SCRIPTS:
            raise HTTPException(
                status_code=422,
                detail=f"nieznany etap {stage!r}; dozwolone: {sorted(runner.STAGE_SCRIPTS)}",
            )

        plan_path = planning.find_plan(subject, catalog)
        digest: str | None = None

        if stage in runner.WRITING_STAGES:
            if body.get("confirm") is not True:
                raise HTTPException(
                    status_code=409,
                    detail="apply wymaga jawnego potwierdzenia konkretnego planu",
                )
            state = planning.overview(
                conn, subject, catalog, resolved_paths,
                rules=load_rules(), thresholds=limits,
            )
            if state["plan"] is None:
                raise HTTPException(status_code=409, detail=state["reason"])
            digest = str(state["plan"]["plan_hash"])
            if str(body.get("plan_hash") or "") != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "zgoda dotyczy innego planu niż ten na dysku "
                        f"(zaakceptowany {str(body.get('plan_hash') or '—')[:12]}…, "
                        f"bieżący {digest[:12]}…) — obejrzyj plan jeszcze raz"
                    ),
                )
            if not state["can_apply"]:
                # To jest TA bramka. Nie startujemy niczego.
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": f"plan nie przechodzi bramki: {state['reason']}",
                        "validation": state["validation"],
                        "diff": state["diff"],
                    },
                )

        argv = runner.build_argv(
            stage, subject=subject, db_path=database_path,
            plan_path=plan_path, plan_hash=digest, grupa=grupa,
        )
        return StreamingResponse(
            runner.stream(argv),
            media_type="text/event-stream",
            headers={"cache-control": "no-store", "x-accel-buffering": "no"},
        )

    # --- S4.1: graf jako soczewka ----------------------------------------
    #
    # Studio nie rysuje grafu drugi raz: serwuje ZBUDOWANY viewer ze źródeł w
    # `studio/graf/` i mówi mu, który węzeł zaznaczyć (`/graf#<id>`). Powrót działa
    # w drugą stronę, bo viewer trzyma zaznaczenie w fragmencie URL-a, a iframe jest
    # tego samego pochodzenia co studio — nie trzeba żadnego dodatkowego kanału.

    def graph_artifact(name: str) -> Path | None:
        candidate = resolved_paths.work / "synapse" / name
        return candidate if candidate.is_file() else None

    def vault_index() -> dict[str, list[str]]:
        """Mapa skrót sha → id notatek, przeliczana po zmianie vaulta."""
        root = resolved_paths.work / "synapse" / "vault"
        stamp = root.stat().st_mtime_ns if root.is_dir() else 0
        cached = getattr(app.state, "vault_index", None)
        if cached is None or cached[0] != stamp:
            app.state.vault_index = (stamp, graph_link.scan_vault(root))
        return app.state.vault_index[1]

    @app.get("/api/graph/status", tags=["graph"])
    def graph_status() -> dict[str, Any]:
        """Czy jest czym pokazać graf i co uruchomić, gdy nie ma."""
        graph = graph_artifact("graph.json")
        index = vault_index()
        return {
            "viewer_built": (VIEWER_DIST / "index.html").is_file(),
            "graph_json": None if graph is None else str(graph),
            "notes": sum(len(ids) for ids in index.values()),
            "hint": "just studio-graf",
        }

    @app.get("/api/graph/node/{sha256}", tags=["graph"])
    def graph_node(
        sha256: str = PathParam(pattern=SHA256_PATTERN),
    ) -> dict[str, Any]:
        """Węzeł grafu odpowiadający treści (albo 404, gdy vault jej nie zna)."""
        nodes = graph_link.nodes_for_sha(vault_index(), sha256)
        if not nodes:
            raise HTTPException(
                status_code=404,
                detail=f"treści {sha256[:12]}… nie ma w vaulcie — odśwież graf (`just studio-graf`)",
            )
        return {"sha256": sha256, "nodes": nodes, "url": graph_link.deep_link(nodes[0])}

    @app.get("/api/graph/subject/{semester}/{skrot}", tags=["graph"])
    def graph_subject(
        semester: int = PathParam(ge=1, le=7),
        skrot: str = PathParam(min_length=1, max_length=64),
        grupa: Optional[str] = Query(None),
    ) -> dict[str, Any]:
        """Węzeł przedmiotu — wejście do grafu z poziomu listy przedmiotów."""
        from orglib.synapse_vault import subject_id

        try:
            subject = config.find_subject(semester, skrot, catalog, grupa=grupa)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        ambiguous = sum(
            1 for other in catalog if other.skrot.casefold() == subject.skrot.casefold()
        ) > 1
        node = subject_id(subject.semester, subject.skrot, subject.grupa, ambiguous=ambiguous)
        return {"node": node, "url": graph_link.deep_link(node)}

    @app.get("/api/graph/content/{node_id}", tags=["graph"])
    def graph_content(
        node_id: str = PathParam(min_length=1, max_length=160),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, Any]:
        """Treść pokazana przez węzeł grafu — droga powrotna do studia."""
        candidates = graph_link.shas_for_node(conn, node_id)
        if not candidates:
            raise HTTPException(
                status_code=404, detail=f"węzeł {node_id} nie wskazuje treści w indeksie"
            )
        detail = queries.item_detail(conn, candidates[0], limits) if len(candidates) == 1 else None
        return {
            "node": node_id,
            "candidates": candidates,
            "sha256": candidates[0] if len(candidates) == 1 else None,
            "item": None if detail is None else detail["item"],
        }

    @app.get("/graph.json", include_in_schema=False)
    @app.get("/search-index.json", include_in_schema=False)
    def graph_data(request: Request) -> Response:
        """Dane grafu tam, gdzie szuka ich viewer (ścieżki w nim są bezwzględne)."""
        name = Path(request.url.path).name
        if name not in _GRAPH_ARTIFACTS:
            raise HTTPException(status_code=404, detail=name)
        artifact = graph_artifact(name)
        if artifact is None:
            raise HTTPException(
                status_code=404, detail=f"brak {name} — zbuduj graf (`just studio-graf`)"
            )
        return FileResponse(artifact, media_type="application/json")

    @app.get("/vault/{note_path:path}", include_in_schema=False)
    def vault_note(note_path: str) -> Response:
        """Treść notatki vaulta dla panelu w viewerze — tylko odczyt, tylko z `work`."""
        if not note_path.endswith(".md"):
            raise HTTPException(status_code=404, detail="vault zawiera wyłącznie notatki .md")
        resolved = config.resolve_within(
            resolved_paths.work, f"synapse/vault/{note_path}"
        )
        if resolved is None or not resolved.is_file():
            raise HTTPException(status_code=404, detail=f"brak notatki {note_path}")
        return FileResponse(resolved, media_type="text/markdown; charset=utf-8")

    if (VIEWER_DIST / "index.html").is_file():
        # Montaż obsługuje `/graf/`; bez tego przekierowania samo `/graf` byłoby 404,
        # a to jest adres, który człowiek wpisuje i który wysyła studio.
        @app.get("/graf", include_in_schema=False)
        def graf_root() -> RedirectResponse:
            return RedirectResponse(url="/graf/")

        app.mount("/graf", StaticFiles(directory=VIEWER_DIST, html=True), name="graf")
    else:
        @app.get("/graf", include_in_schema=False)
        def graf_placeholder() -> HTMLResponse:
            return HTMLResponse(_GRAF_PLACEHOLDER, status_code=503)

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(_PLACEHOLDER)

    return app
