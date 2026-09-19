"""Backend studia (FastAPI). Faza S0: wyłącznie odczyt.

``scripts/`` nie jest instalowanym pakietem — moduły potoku (``orglib``,
``status_report``) leżą tam jako moduły najwyższego poziomu i tak są importowane
w całym projekcie (``pytest.ini: pythonpath``). Backend musi je widzieć także
wtedy, gdy uruchamia go uvicorn, więc katalog dokładamy tutaj, raz, przy imporcie
pakietu — zamiast powtarzać tę sztuczkę w każdym module studia.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Korzeń organizera (``paczka-tools/organizer``) — liczony ze ścieżki pliku,
#: nigdy z katalogu roboczego (reguła twarda nr 12: zero hardkodowanych ``../..``).
ORGANIZER_ROOT: Path = Path(__file__).resolve().parents[2]

_SCRIPTS = ORGANIZER_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

__all__ = ["ORGANIZER_ROOT"]
