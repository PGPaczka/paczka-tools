"""Stałe i fragmenty SQL dzielone przez kilka domen zapytań.

Leżą osobno, bo nie należą do jednej domeny: ``_ITEM_COLUMNS`` czyta lista
pozycji, diff klastra i wyszukiwanie. Dwie kopie tego SELECT-a rozjechałyby się
przy pierwszej zmianie kolumny, a wtedy ta sama treść miałaby inny kształt
w zależności od tego, przez który widok się do niej doszło.
"""

from __future__ import annotations

import status_report

#: Ile znaków głowy tekstu wysyłamy do widoku (podgląd i diff klastra). Tyle
#: wystarcza, żeby rozpoznać dokument; całość leży w ``work`` dla tego, kto chce czytać.
PREVIEW_TEXT_LIMIT = 4096

#: run_id, pod którym scan_target zapisuje treści leżące już w repo produktu.
GROUND_TRUTH_RUN_ID = status_report.GROUND_TRUTH_RUN_ID

#: Kolumny jednej pozycji listy: treść + jej decyzja + JEDEN reprezentatywny plik.
#: Reprezentantem jest plik o najmniejszym ``file_id`` — ta sama treść bywa
#: zmaterializowana w kilkunastu paczkach, a lista pokazuje pozycje treści, nie
#: pozycje kopii.
_ITEM_COLUMNS = """
    c.sha256                                AS sha256,
    c.content_kind                          AS content_kind,
    c.extracted_text_path IS NOT NULL       AS has_text,
    c.ocr_done                              AS ocr_done,
    cl.semester                             AS semester,
    cl.subject_key                          AS subject_key,
    cl.category                             AS category,
    cl.slot                                 AS slot,
    cl.target_relative_path                 AS target_relative_path,
    cl.action                               AS action,
    cl.reason                               AS reason,
    cl.confidence                           AS confidence,
    cl.classification_method                AS classification_method,
    cl.needs_review                         AS needs_review,
    cl.is_outdated                          AS is_outdated,
    cl.run_id                               AS run_id,
    cl.decided_at                           AS decided_at,
    f.file_id                               AS file_id,
    f.source_package                        AS source_package,
    f.source_relative_path                  AS source_relative_path,
    f.folder_path                           AS folder_path,
    f.filename                              AS filename,
    f.extension                             AS extension,
    f.size_bytes                            AS size_bytes,
    f.modified_date                         AS modified_date,
    f.status                                AS file_status,
    (SELECT COUNT(*) FROM files WHERE sha256 = c.sha256)     AS copies
"""

_ITEM_FROM = """
FROM content AS c
LEFT JOIN classifications AS cl ON cl.sha256 = c.sha256
LEFT JOIN files AS f ON f.file_id = (SELECT MIN(file_id) FROM files WHERE sha256 = c.sha256)
"""
