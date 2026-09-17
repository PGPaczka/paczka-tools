# paczka-tools

Zbiór narzędzi pomocniczych projektu Paczka. Każde narzędzie jest self-contained
(własne README, zależności, ewentualnie venv). Nic tu nie jest deployowane.

## Narzędzia

### organizer
Scalanie starych „paczek" materiałów (`00_SOURCES`) w jedną uporządkowaną paczkę:
pipeline `scan → hash → dedup → extract → classify → plan → apply → verify`, AI tylko
dla niejednoznacznych resztek, człowiek zatwierdza plan per przedmiot. Zawiera
wspólną konfigurację agentów oraz adaptery Claude Code i Codexa — sesję odpalasz
w `organizer/` przez `just claude` albo `just codex`.
Start: [`organizer/README.md`](organizer/README.md), setup: `bash organizer/setup/install.sh`.

### multi-folder-downloader
Rekurencyjne pobieranie dużego, publicznego drzewa Google Drive z zachowaniem
struktury (checkpoint SQLite, równoległe workery, dashboard, eksport Docs/Sheets).
Produkuje `00_SOURCES` dla organizera. Patrz
[`multi-folder-downloader/README-DOWNLOADER.md`](multi-folder-downloader/README-DOWNLOADER.md).

### ects_extractor
Skrypty do ekstrakcji informacji o przedmiotach i tworzenia struktury folderów.

### gitignore-generator
Generator pliku `.gitignore` dla repozytorium.

### img-to-pdf-merger
Skrypt Python do łączenia obrazów w jeden plik PDF.
