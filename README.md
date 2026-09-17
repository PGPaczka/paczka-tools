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
[`multi-folder-downloader/README.md`](multi-folder-downloader/README.md).

### ects_extractor
Skrypty do ekstrakcji informacji o przedmiotach i tworzenia struktury folderów.
Lista przedmiotów jest w `ects_extractor/data/`; zasady uruchamiania i ograniczenia:
[`ects_extractor/README.md`](ects_extractor/README.md).

### gitignore-generator
Generator pliku `.gitignore` dla repozytorium.

### img-to-pdf-merger
Skrypt Python do łączenia obrazów w jeden plik PDF.

## Zasady układu plików

- Każde narzędzie zachowuje własny katalog; małe, samodzielne skrypty nie
  potrzebują dodatkowej warstwy `src/`.
- `README.md` jest punktem wejścia do dokumentacji narzędzia.
- Kod pomocniczy trafia do `scripts/`, a testy do `tests/`, gdy są potrzebne.
- Dane ECTS są w `ects_extractor/data/`. Wyniki organizera są w
  `organizer/reports/`, historyczne raporty w `reports/bootstrap/`,
  a dokumentacja techniczna w `organizer/docs/`.
- `multi-folder-downloader/cookies/` i `state/` zawierają wyłącznie lokalne
  dane, nie kod. Cookies, bazy, logi i pliki tymczasowe pozostają ignorowane
  przez Git; pobrane materiały żyją poza repo.
