# Raporty organizera

Ten katalog zawiera wyniki i stan pracy, nie dokumentację kodu (ta znajduje się
w `../docs/`). Część plików jest wersjonowana, część powstaje z każdego przebiegu
potoku i do repo nie wchodzi — kolumna „W repo” mówi które.

| Ścieżka | W repo | Przeznaczenie |
|---|---|---|
| `HANDOFF.md` | tak | Stan przekazania sesji; część automatyczną odświeża `just handoff`. |
| `STATUS.md` | tak | Przedmioty × etapy i kolejka pracy; generuje `scripts/status_report.py` (`just status`). |
| `SOURCES_TREE.md` | tak | Snapshot drzewa źródeł generowany przez `scripts/scan.py`. |
| `dedup_summary.md` | tak | Czytelne podsumowanie `scripts/dedup_report.py`. |
| `bootstrap/` | tak | Jednorazowa ocena rozmiarów i duplikatów z etapu A0; żaden skrypt tego nie odtworzy. |
| `historia/` | tak | Zamknięte listy zadań z pojedynczych sesji, trzymane jako zapis decyzji. |
| `inventory.jsonl` | nie | Ślad źródeł, jedna linia JSON na plik; `scripts/scan.py` (B1), ~19 MB. |
| `folder_overlap.csv` | nie | Pokrycie katalogów; `scripts/fold_hash.py`. |
| `{SKROT}/` | nie | Artefakty jednego przedmiotu: `manifest_slice.jsonl` (B1), `plan.det.jsonl` i `unresolved.jsonl` (B3), `plan.ai.jsonl` (B5), `relations.jsonl` (B6), `plan.jsonl` (B7), `validation.jsonl` (B8), `review.html` (B9). |

Artefakty oznaczone „nie” leżą na dysku po przebiegu potoku, ale `.gitignore` je
pomija: commitowanie zamrażałoby jeden przebieg jako gdyby był źródłem. Odtwarza
je ponowne uruchomienie odpowiedniego etapu.

Raporty w `bootstrap/` zachowują oryginalną treść, w tym ścieżki zapisane
przez narzędzia przed reorganizacją katalogów. Nie są bieżącą konfiguracją
ani skryptami do uruchomienia.

Bazy i duże artefakty robocze pozostają poza repo — ich lokalizacje określa
`../config/paths.yaml`. Reorganizacja raportów nie wymaga ponownego skanu.
