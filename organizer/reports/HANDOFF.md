# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy: sekcja B TODO — skrypty cyklu per-przedmiot. Domknięte B2 (etap extract) i B2a (wpięcie `text_head` do manifestu). Nie ruszano pilotażu ani materiałów.
- Aktywny przedmiot `(semestr, skrót, grupa)`: brak — praca narzędziowa. Etap extract sprawdzony smoke testem na syntetycznej paczce w scratchpadzie (PDF tekstowy, PDF-skan, PNG, DOCX, PPTX, TXT, ZIP), nie na realnych źródłach.
- Ostatni zakończony krok: commity `c02b708` (B2) i `146657a` (B2a). Nowe pliki: `scripts/orglib/textextract.py`, `scripts/extract_text.py`, `tests/test_textextract.py`, `tests/test_extract_text.py`; recepta `just extract`.
- Kontrakt B2: wejście = pliki w statusie `hashed` (bez poddrzew `duplicate_of`), wyjście = `20_WORK/extracted_text/{sha256}.txt` + `content.extracted_text_path`/`ocr_done` + `files.normalized_text_hash`/`simhash`/`perceptual_hash`, status `extracted`. Praca liczona RAZ NA TREŚĆ: druga kopia sha256 i ponowny przebieg biorą tekst z dysku (smoke: 1,6 s → 0,2 s), `--force` wymusza ponowną ekstrakcję. Ścieżka w bazie jest zapisywana względem `work`, więc przeniesienie workspace'u jej nie psuje.
- Decyzje B2 do zapamiętania (były świadome, nie przypadkowe):
  1. **OCR wchodzi tylko, gdy realnie dołożył treści.** Krótki, ale poprawny PDF (< 120 znaków po normalizacji) uruchamia tesseract, lecz jego wynik jest odrzucany, jeśli nie jest dłuższy od warstwy tekstowej. Bez tego poprawne, jednostronicowe PDF-y dostawały szum z OCR (zobaczone na smoke teście, poprawione).
  2. **Awaria pdfplumber jest tolerowana, awaria OCR nie.** pdfplumber to druga opinia o układzie strony; nierozpoznany skan ma trafić na `error` i czekać na `--retry-errors`, a nie udawać pustego dokumentu (reguła „nie zgaduj”).
  3. **Brak tekstu ≠ błąd.** Archiwum, media, `.doc`/`.rtf`/`.odt`, `.xlsx` (brak openpyxl w zależnościach) i obraz bez `--ocr-images` przechodzą na `extracted` z metodą `unsupported` i `extracted_text_path = NULL`. OCR obrazów jest opt-in, bo w źródłach jest ich kilkanaście tysięcy.
  4. `simhash` jest **własny i deterministyczny** (blake2b, shingle 3 słów, hex 64 bit), żeby podmiana biblioteki nie zmieniła znaczenia wartości już zapisanych w bazie. Do porównań służy `textextract.hamming_distance` — progi czekają w `thresholds.yaml: near_duplicate` na B6.
- Kontrakt B2a: `prepare_subject.py` dokłada do manifestu **opcjonalne** pole `text_head` (głowa tekstu z `work`, obcięta do `thresholds.yaml: llm.max_text_head_bytes`). Domyka to wiszący kontrakt — `ai_resolve.py` czytał `row["text_head"]`, którego nikt nie produkował, więc klasyfikacja AI szła po samej nazwie pliku. Wpis `extracted_text_path` wskazujący drzewo materiałów jest pomijany: manifest nie może stać się boczną ścieżką do czytania materiałów.
- Delegacja w tym kroku: testy B2 (93 przypadki) napisał Codex na koncie OpenAI (`gpt-6-astra`, zero tokenów Anthropic); implementację i decyzje projektowe wykonał koordynator. Raport Codeksa **nie został wzięty na wiarę** — przegląd potwierdził, że tym razem fixture czyta realny `paths.yaml` i przekierowuje korzenie do `tmp_path` (nie ma zamrożonej kopii configu, jak przy B5), a atrapa OCR twardo zabrania niezamówionego wywołania tesseractu. Koordynator dołożył 2 testy odporności (`pdfplumber`/OCR) i 4 testy `text_head`.
- Polityka kosztowa (nowa, wiążąca): `thresholds.yaml: llm` kieruje `classify` i `relate` na `codex_cli`/`gpt-6-astra`. Koordynator uruchamia klasyfikator i **ocenia** wynik; nie klasyfikuje w sesji i nie forkuje do tego podagenta. `just claude` nie nadpisuje już `PACZKA_LLM_RELATE_BACKEND` — wcześniej samo uruchomienie sesji przenosiło `relate` z powrotem na limit Anthropic. Skierowanie na Claude to świadoma decyzja: `PACZKA_LLM_RELATE_BACKEND=claude_cli just claude`.
- Pułapka do zapamiętania: tryb strukturalny OpenAI odrzuca kanoniczny schemat (`'required' … Missing 'year'`, brak wsparcia dla `pattern`/`minimum`). `wire_schema()` robi wariant „po drucie”; walidacja lokalna zostaje przy oryginale. Nie wysyłaj kanonicznego schematu wprost do `--output-schema`.
- Infrastruktura: `claude-code-router` usunięty z bazowego `~/.codex/config.toml` (kopia `~/.codex/config.toml.pre-ccr-removal-20260918-105323`). Powód krytyczny: obejście proxy flagą `--ignore-user-config` odcina `[hooks.state]`, przez co Codex **przestaje uruchamiać** `.codex/hooks.json` — guard `00_SOURCES` milczy (test różnicowy: bez flagi w logu jest `hook: PreToolUse`, z flagą nie ma). Delegacja używa teraz `-c model_provider="openai"`. Nie przywracaj tej flagi.
- Znany, świadomie zostawiony fałszywy alarm guarda: `tee` jest na liście słów twardo mutujących, więc potok ze źródeł do `tee` poza nimi zostanie zablokowany — używaj przekierowania `>`. Ogólniej hook blokuje każdą komendę Bash, której **tekst** zawiera ścieżkę źródeł razem ze słowem mutującym (także w komunikacie commita); w takich wypadkach używaj narzędzi Edit/Write zamiast powłoki.
- Uruchamianie agentów interaktywnie: rozpisane w `README.md`, sekcja „Agenci interaktywni” (pierwsza konfiguracja, `just claude`, trzy tryby sandboxu Codeksa, przekazywanie argumentów **bez** `--`, potwierdzanie konta). `AGENTS.md` i `CLAUDE.md` tylko tam odsyłają — nie duplikuj tej treści.
- Zakazy dla następnego agenta: nie wykonuj apply bez jawnej zgody na konkretny plan; nie dodawaj sources jako writable root; nie przywracaj `--ignore-user-config` w delegacji Codeksa; nie przestawiaj `classify`/`relate` z powrotem na `claude_cli` bez decyzji użytkownika; nie commituj materiałów razem z narzędziami.
- Wykonane testy: `just test` **559/559** (w tym 96 dla B2 w `tests/test_textextract.py` + `tests/test_extract_text.py` i 6 dla `text_head` w `tests/test_prepare_subject.py`); `just skills-check` 5/5. Smoke test etapu extract na syntetycznej paczce: 7 plików / 7 treści, 6 z tekstem, OCR 2, 0 błędów; drugi przebieg 6 treści z dysku.
- Następna dokładna czynność: **B3 — `scripts/classify.py`** (klasyfikacja deterministyczna + heurystyka regex: lab/kol/egzamin/rok/prowadzący; semestr rozstrzyga kolizje skrótów; `forms` waliduje; status `classified` albo `unresolved`). Wejście ma już komplet sygnałów: ścieżki z B1 i `text_head` z B2.
- Blokery / otwarte decyzje: brak. Znane, świadome ograniczenia B2: `.xlsx` nie jest czytany (brak openpyxl w `setup/requirements.txt`), `ocrmypdf` nie jest zainstalowany (OCR idzie przez `pytesseract` + rasteryzację PyMuPDF), OCR obrazów jest opt-in.
- Git: `c02b708` i `146657a` to lokalne commity narzędzi, bez push i bez PR. Drzewo czyste. Materiałów nie dotykano.
- Stan akceptacji planu: `brak` — nie przygotowano ani nie zaakceptowano planu migracji materiałów.

<!-- BEGIN AUTO -->
- Odświeżono: 2026-09-18T18:23:42+02:00
- Branch: `master`
- Commit: `146657a`
- Git status:
  ```text
  M TODO.md
   M reports/HANDOFF.md
  ```
- Pierwsze otwarte TODO: - [ ] B3. `scripts/classify.py` — deterministyczny + heurystyka (regex lab/kol/egzamin/rok/prowadzący); semestr rozstrzyga skrót; `forms` waliduje; status `classified` albo `unresolved`
<!-- END AUTO -->
