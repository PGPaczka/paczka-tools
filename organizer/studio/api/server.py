"""Launcher studia: bramka adresu, preflight bazy i uruchomienie uvicorna.

Studio jest narzędziem jednego człowieka na jego maszynie: bez kont, bez
autoryzacji, bez CORS-a. Jedyne, co trzyma tę decyzję w ryzach, to adres
nasłuchu — dlatego adres spoza loopbacka **odmawia startu**, a nie ostrzega
(``studio/AGENTS.md``, reguła 3). Gdyby to było ostrzeżenie, pierwszy „tylko na
chwilę, żeby zobaczyć z telefonu” wystawiłby na sieć czytelnię całej paczki.

Nazwy hostów celowo NIE są rozwiązywane przez DNS: adres musi być literałem IP
pętli zwrotnej albo ``localhost``. Rozwiązywanie nazw oznaczałoby, że o tym, czy
serwer stoi na loopbacku, decyduje zawartość ``/etc/hosts`` albo odpowiedź
serwera DNS.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI

from . import ORGANIZER_ROOT, database
from .app import create_app

#: Domyślny adres i port. Port wysoki i „nasz”, żeby nie zderzać się z dev-serwerami.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

#: Nazwa, którą wolno podać zamiast literału IP (zawsze pętla zwrotna).
LOCALHOST = "localhost"

#: Ścieżka bazy dla podprocesu ``--reload``: fabryka nie dostaje argumentów,
#: więc jedyną drogą jest środowisko.
DB_ENV = "PACZKA_STUDIO_DB"

#: Import string dla uvicorna (``factory=True``). Zmiana nazwy modułu albo
#: funkcji MUSI złamać test kontraktu launchera, nie dopiero start serwera.
APP_FACTORY = "studio.api.server:app_factory"


class AddressRefused(ValueError):
    """Adres nasłuchu spoza pętli zwrotnej — start jest odmawiany."""


def ensure_loopback(host: str) -> str:
    """Przepuszcza wyłącznie adres pętli zwrotnej; inaczej :class:`AddressRefused`.

    Akceptuje literał IPv4/IPv6 z ``is_loopback`` (``127.0.0.0/8``, ``::1``),
    zapis w nawiasach (``[::1]``) i nazwę ``localhost``. Wszystko inne — łącznie
    z ``0.0.0.0``, ``::`` i dowolną nazwą DNS — jest odmową.
    """
    candidate = str(host).strip()
    if candidate.casefold() == LOCALHOST:
        return candidate
    literal = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    try:
        address = ipaddress.ip_address(literal)
    except ValueError as exc:
        raise AddressRefused(
            f"adres {host!r} nie jest literałem IP — studio nasłuchuje wyłącznie na "
            f"{DEFAULT_HOST} (albo {LOCALHOST})"
        ) from exc
    if not address.is_loopback:
        raise AddressRefused(
            f"adres {host!r} jest spoza pętli zwrotnej — studio nie wystawia indeksu "
            "na sieć; użyj 127.0.0.1"
        )
    return candidate


def preflight(db_path: Path) -> int:
    """Sprawdza, że baza istnieje i ma właściwy schemat; zwraca ``schema_version``.

    Robione PRZED zajęciem portu, żeby błąd bazy wyglądał jak błąd bazy, a nie jak
    serwer, który wstał i zwraca 500 na każdym żądaniu.
    """
    conn = database.open_readonly(Path(db_path))
    try:
        return database.check_schema(conn)
    finally:
        conn.close()


def app_factory() -> FastAPI:
    """Fabryka dla uvicorna — ścieżkę bazy bierze ze środowiska (podproces ``--reload``)."""
    raw = os.environ.get(DB_ENV)
    return create_app(Path(raw) if raw else None)


def uvicorn_options(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    log_level: str = "info",
) -> dict[str, Any]:
    """Argumenty wywołania uvicorna — jedno miejsce, które test konfrontuje z jego API."""
    return {
        "app": APP_FACTORY,
        "factory": True,
        "host": ensure_loopback(host),
        "port": int(port),
        "reload": bool(reload),
        "log_level": log_level,
        "app_dir": str(ORGANIZER_ROOT),
    }


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    db_path: Optional[Path] = None,
    log_level: str = "info",
) -> None:
    """Sprawdza adres i bazę, po czym oddaje sterowanie uvicornowi."""
    import uvicorn

    options = uvicorn_options(host=host, port=port, reload=reload, log_level=log_level)
    if db_path is not None:
        os.environ[DB_ENV] = str(Path(db_path))
    resolved = Path(os.environ[DB_ENV]) if DB_ENV in os.environ else None
    if resolved is None:
        from orglib import config

        resolved = config.load_paths().work_db
        os.environ[DB_ENV] = str(resolved)
    preflight(resolved)
    uvicorn.run(**options)
