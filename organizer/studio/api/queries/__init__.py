"""Odczyt indeksu na potrzeby widoku — jedyne miejsce, w którym studio pisze SQL.

Pakiet dzieli zapytania po domenach (pulpit, lista pozycji, klastry, plan,
podgląd, statystyki), ale na zewnątrz wygląda jak jeden moduł: ``app.py`` i testy
wołają ``queries.dashboard(...)`` czy ``queries.items(...)`` i nie muszą wiedzieć,
w którym pliku co leży. Dlatego re-eksport poniżej jest wypisany jawnie — zmiana
wewnętrznego podziału nie ma prawa ruszyć wołających.

Kształt odpowiedzi jest płaski i już policzony — front ma go wyświetlić, nie
dosumować.
"""

from __future__ import annotations

from ._common import GROUND_TRUTH_RUN_ID, PREVIEW_TEXT_LIMIT
from .clusters import cluster_diff, clusters, same_day_groups
from .dashboard import (
    STAGE_ORDER,
    confidence_limits,
    dashboard,
    subject_detail,
    subject_payload,
)
from .items import folders, item_detail, items, items_by_folder
from .plan import plan_conflicts
from .preview import preview, preview_image
from .stats import decision_history, live_stats, search

__all__ = [
    "GROUND_TRUTH_RUN_ID",
    "PREVIEW_TEXT_LIMIT",
    "STAGE_ORDER",
    "cluster_diff",
    "clusters",
    "confidence_limits",
    "dashboard",
    "decision_history",
    "folders",
    "item_detail",
    "items",
    "items_by_folder",
    "live_stats",
    "plan_conflicts",
    "preview",
    "preview_image",
    "same_day_groups",
    "search",
    "subject_detail",
    "subject_payload",
]
