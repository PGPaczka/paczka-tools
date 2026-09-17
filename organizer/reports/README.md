# Raporty organizera

Ten katalog zawiera wersjonowane wyniki i stan pracy, nie dokumentację kodu
(ta znajduje się w `../docs/`).

| Ścieżka | Przeznaczenie |
|---|---|
| `HANDOFF.md` | Stan przekazania sesji; część automatyczną odświeża `just handoff`. |
| `SOURCES_TREE.md` | Snapshot drzewa źródeł generowany przez `scripts/scan.py`. |
| `inventory.jsonl`, `dedup_summary.md` | Wyniki `scripts/dedup_report.py`. |
| `folder_overlap.csv` | Wynik `scripts/fold_hash.py`. |
| `bootstrap/` | Historyczne raporty wstępnej oceny rozmiarów i duplikatów. |

Raporty w `bootstrap/` zachowują oryginalną treść, w tym ścieżki zapisane
przez narzędzia przed reorganizacją katalogów. Nie są bieżącą konfiguracją
ani skryptami do uruchomienia.

Bazy i duże artefakty robocze pozostają poza repo — ich lokalizacje określa
`../config/paths.yaml`. Reorganizacja raportów nie wymaga ponownego skanu.
