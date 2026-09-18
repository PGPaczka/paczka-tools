# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy: rozpoczęcie sekcji B od kompletnego B1 — skryptu wycinka manifestu i testów. Zakończony spójny zakres, nie cały cykl B1–B14.
- Aktywny przedmiot `(semestr, skrót, grupa)`: brak — implementacja narzędzi na syntetycznych danych; nie uruchamiano pilotażu ani operacyjnej bazy.
- Ostatni zakończony krok: `scripts/prepare_subject.py`, `scripts/orglib/subject_manifest.py` oraz działający `just subject-prepare`. Baza tylko SELECT, `mode=ro` i `query_only`; bez skanu źródeł, zmian statusów, ground truth, AI ani apply.
- Kontrakt B1: manifest v1 ma jeden rekord/SHA-256, pełne `source_paths`, osobne `matched_source_paths`, zdrowego reprezentanta spoza dowolnego przodka `duplicate_of` w `source_path` (albo null + review). Rozmiar pochodzi od reprezentanta; niespójności kopii trafiają do review. To lista kandydatów, nie klasyfikacja.
- Dopasowanie: tokeny skrótu/aliasu/nazwy, normalizacja polskich znaków i separatorów; jawny semestr/grupa zawęża, brak lub konflikt daje review. Priorytet pełnej nazwy/skrótu/aliasu działa w obrębie semestru. `magisterskie` poza zakresem D3. Brak fuzzy; nieznane nazwy nadal wymagają aliasów/przeglądu.
- Ścieżki raportów: dla unikalnego skrótu `reports/{SKROT}/manifest_slice.jsonl`; powtarzany skrót izolowany przez `reports/SEM{semester}/{grupa}/{SKROT}/manifest_slice.jsonl`. Jawny `--out-dir` jest dokładnym katalogiem i wymaga od operatora rozdzielenia raportów. README opisuje pełny kontrakt.
- Bezpieczeństwo zapisu: atomowa podmiana manifestu, bez nadpisania DB (także hardlink), bez pliku-symlinku i bez zapisu w chronionych drzewach również przez symlinki. Baza nie może leżeć w drzewie materiałów ze względu na pomocnicze pliki SQLite WAL/SHM. Ścieżki pochodzenia w indeksie odrzucają traversal.
- Wykonane testy: bazowy zestaw przed zmianami 293/293; nowe jednostkowe i CLI 59/59; końcowy `just test` 352/352; `just skills-check` 5/5; `just --fmt --check`, `git diff --check` i `just subject-prepare 3 AKO --help` bez błędów. Wszystkie nowe testy wyłącznie na syntetycznych indeksach w tmp_path. Nie wykonywano testu na realnych materiałach.
- Skille/delegacja: wykorzystano procedurę implementacji brakującego skryptu ze skillu `organizer-subject`, bez rozpoczynania jego workflow materiałów. Żądane słabsze subagenty nie wykonały pracy: Sonnet odrzucony przez konfigurację reasoning, dwa uruchomienia Fable zakończone `401 Unauthorized` routera; model odziedziczony nieobsługiwany przez narzędzie delegacji. Kod, testy i review wykonał koordynator lokalnie; nie zmieniano routera ani uwierzytelnienia. Niezależny review subagenta pozostaje niewykonany.
- Następna dokładna czynność: B2 — zaimplementować `scripts/extract_text.py` i testy PDF/DOCX/PPTX, cache oraz opcjonalnego OCR. Konsumować manifest v1 po SHA-256, nie ekstrahować z poddrzew duplicate_of; respektować null reprezentanta/review, przed otwarciem ponownie sprawdzać containment źródła i hash. Ścieżki cache tylko z configu; nadal bez apply.
- Blokery / otwarte decyzje: brak blokera dla dalszego kodowania lokalnego. Delegacja wymaga naprawy dostępności/autoryzacji modeli poza zakresem B1. Dalsze etapy B2–B14 (poza B4) i e2e nadal niegotowe.
- Stan akceptacji planu: `brak` — nie przygotowano ani nie zaakceptowano planu migracji materiałów.
- Git: zakres B1 z tym handoffem przeznaczony do lokalnego commita narzędzi po przeglądzie; bez push/PR. Sekcja AUTO jest snapshotem sprzed tego commita. Poprzedni stan infrastruktury/skilli jest w `99250e8`; brak odziedziczonych zmian roboczych.
- Zakazy dla następnego agenta: nie wykonuj apply bez jawnej zgody na konkretny plan; nie dodawaj sources jako writable root; nie zmieniaj routera w ramach B2; nie commituj materiałów razem z narzędziami.

<!-- BEGIN AUTO -->
- Odświeżono: 2026-09-18T01:57:49+02:00
- Branch: `master`
- Commit: `99250e8`
- Git status:
  ```text
  M README.md
   M TODO.md
   M justfile
  ?? scripts/orglib/subject_manifest.py
  ?? scripts/prepare_subject.py
  ?? tests/test_prepare_subject.py
  ?? tests/test_subject_manifest.py
  ```
- Pierwsze otwarte TODO: - [ ] B2. `scripts/extract_text.py` — głowa tekstu (PDF/DOCX/PPTX, OCR awaryjnie) do `20_WORK/extracted_text/{sha256}.txt`, `normalized_text_hash`, `simhash`, `phash`; tylko unique, status `extracted`
<!-- END AUTO -->
