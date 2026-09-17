# TODO — Paczka Organizer

Lista zadań do odhaczania. Claude Code utrzymuje ją samodzielnie (patrz `CLAUDE.md`,
sekcja „TODO.md”): odhacza po ukończeniu (`- [x] … (RRRR-MM-DD)`), dopisuje nowe
pozycje, nieaktualne przekreśla z powodem. Źródło planu: `docs/ARCHITEKTURA_FINALv1.md`
(sekcja 13). Nazwy skryptów zgodne z README (Quickstart).

Legenda: `[ ]` do zrobienia · `[x]` zrobione · `[~]` w toku · ~~przekreślone~~ nieaktualne

## A. Pierwszy przebieg (fundament, robiony raz)

- [x] A1. Szkielet repo + `config/` (paths, subjects, syntax, thresholds) + Claude Code setup (2026-09-17)
- [x] A2. Model danych — sekcja 4: `scripts/orglib/{schema.sql,db.py,config.py,hashes.py}`, `scripts/db_admin.py`, 70 testów (2026-09-17)
- [x] A2a. Naprawa `config/subjects.yaml` (sem 7: klucz `wspolne`, poprawny YAML) (2026-09-17)
- [x] A0. Bootstrap skali dublowania: `rmlint -D` + `ncdu` na źródłach (tylko raport) → `reports/bootstrap_rmlint.txt`: 47 991 plików, 29 548 kopii, 17,94 GB dubli (~45%); pełne artefakty w `20_WORK/` (2026-09-17)
- [x] A3. `scripts/scan.py` — stat źródeł → `source_packages`, `folders`, `files` (status `discovered`), `structural_signature`; skip niezmienionych poddrzew na re-runie; generuje `docs/SOURCES_TREE.md` (2026-09-17)
- [x] A4. `scripts/hash_files.py` — sha256 → `files.sha256`, `content` (content_kind z `orglib/kinds.py`), status `hashed`; wznawialny, `--retry-errors`, containment ścieżek (2026-09-17)
- [x] A5. `scripts/fold_hash.py` — `tree_hash` / `content_set_hash` → `folders.duplicate_of` (dwa przejścia, FK) + `reports/folder_overlap.csv` (próg z `thresholds.yaml`) (2026-09-17)
- [x] A6. `scripts/dedup_report.py` — unique vs duplicate (liczby, bajty, per paczka) → `reports/dedup_summary.md`, `reports/inventory.jsonl` (2026-09-17)
- [x] A7. `scripts/scan_target.py` — skan istniejącej `paczka/` w `target_repo` = ground truth (lock; hash + ścieżka docelowa → `applied`/klasyfikacja `manual`, conf=1.0) (2026-09-17)
- [x] A9. **Decyzja użytkownika:** szablon docelowy dopasowany do ground truth — `{SKROT}_{Nazwa}` (bez nawiasów) na SEM1-4; SEM5/6 dodatkowy poziom strumienia (`Aplikacje`/`Systemy`/`Wspolne`); SEM7 dodatkowy poziom katedry, w repo katalog to DOKŁADNIE `{KOD}_{profil}` (np. `KAIMS_Algorytmy_I_Modelowanie_Systemów`, nie sama `KAIMS`) albo `Wspolne` bez profilu — `Subject.grupa` = `f"{katedra}_{profil}"`. Skróty przemianowane zgodnie z ground truth (stare jako aliasy): sem1 HDI→HDMI, sem3 AK→AKO, sem3/4/5 JAI→JAII/JAIII/JAIV (sem2 JAI bez zmian), sem6 PGI→PGII, sem6 ZAK→ZAKO, sem7 PDII→PDIII, sem7 SDII (dawniej powtórzone w 6 profilach)→jeden SDIII pod `wspolne`, sem7 KAIMS "JPNP."→JPNP (i usunięta kropka przed NET w nazwie). Dokładna pisownia/wielkość liter dopasowana 1:1 do folderu (probe je wymusza): sem1 HIH→HiH, sem2 PEIM→PEiM, sem2 AISD→AiSD, sem4 SWIM→SWiM, sem4 MPWI→MPwI (stare skróty jako aliasy), sem5/6 `nazwa` PGI/PGII → `PROJEKT_GRUPOWY_I/II` (całe wielkimi literami, jak w repo), profile SEM7 przemianowane na dokładne nazwy folderów (`Algorytmy_I_Modelowanie_Systemów`, `Architektura_Systemów_Komputerowych`, `Bazy_Danych`, `Inteligentne_Systemy_Interaktywne`, `Systemy_Geoinformatyczne`, `Teleinformatyka`). `config.TARGET_PATH_TEMPLATE`/`TARGET_PATH_TEMPLATE_GROUPED` + `Subject.grupa`/`.katedra` w `scripts/orglib/config.py`. **Probe** `tests/test_subjects_vs_target_repo.py` (pomijany bez lokalnego `target_repo`): 98 przedmiotów w obie strony — 0 brakujących target_dir (poza jawną listą wyjątków `{(2,"WFI"),(3,"WFI")}` — brak materiałów), 0 katalogów w repo bez wpisu w `subjects.yaml`. (2026-09-17)
- [x] A10. Po A9 (renames AKO/ZAKO/TRP/HDMI/JAII-IV/PGII/PDIII/SDIII + katedry SEM7) ponowny `scan_target.py` na realnej `target_repo`: **sklasyfikowane 1647 / bez dopasowania 30** (z 1677 unikalnych treści; `bez dopasowania` liczy RAZEM oba poniższe kubełki). ZAKO, TRP, HDMI i jego podprzedmioty (Prawo_Patentowe/Twórczość_Inżynierska/Wiedza_O_Kulturze — trafiają teraz pod HDMI jako `category`) już się dopasowują — z realnych braków (dopisanie aliasu by nie pomogło) zostały:
  - **foldery bez dopasowania (18 treści, prawdziwa luka w strukturze, nie w subjects.yaml):** `SEM{1..6}`: pliki luzem wprost pod semestrem, bez podfolderu przedmiotu (`tutorial_sem_N_*.pdf`, `ranking_nauczycieli_akademickich.pdf`, 17 plików) + `SEM7/KAIMS_Algorytmy_I_Modelowanie_Systemów/CODE_CLEANER_GOLUCH.zip` (plik wprost w katedrze, bez podfolderu przedmiotu).
  - **poza zakresem klasyfikacji (12 treści, strukturalnie nigdy nie będą przedmiotem):** `ogolne/` (skrypty, tutoriale, test.txt), `SEM{1,2,5}/sources/`, `Magisterskie_SEM2/Inżynieria_systemów_informacyjnych/ZBI_…` (magisterskie, por. D3). (2026-09-17)
- [x] A9 runda 3. Użytkownik przemianował ręcznie 3 katalogi w `target_repo` (branch
  `fix/nazwy-katalogow-przedmiotow`, **czeka na merge do mastera przez użytkownika** —
  ten branch to jedyne źródło ground truth dla tej rundy): `PGI_PROJEKT_GRUPOWY_I` →
  `PGI_Projekt_Grupowy_I` (SEM5), `PGII_PROJEKT_GRUPOWY_II` → `PGII_Projekt_Grupowy_II`
  (SEM6), `SI._Serwisy_Internetowe_.NET` → `SI_Serwisy_Internetowe_NET` (SEM7/KASK).
  Dopasowano `subjects.yaml` (`nazwa` PGI/PGII na `Projekt_Grupowy_I/II`; KASK SI
  skrót `"SI."` → `SI`, `nazwa` → `Serwisy_Internetowe_NET`, stary skrót jako
  alias `"SI."`) — co odsłoniło NOWĄ kolizję: SEM7 ma teraz SI dwa razy (KASK
  `Serwisy_Internetowe_NET` vs KT `Sieci_IP`), więc samo (semestr, skrot) w SEM7
  przestało być jednoznaczne. Rozwiązanie: `config.find_subject(..., *, grupa=None)`
  — z `grupa` zawęża kandydatów do `Subject.grupa == grupa` (katedra/profil w
  SEM7, strumień w SEM5/6); `scripts/scan_target.py: classify_path` przekazuje
  jako `grupa` OSTATNI pominięty segment ścieżki (katalog katedry/strumienia) i
  przy `KeyError`/`ValueError` z grupą wraca do wywołania bez niej (nigdy
  odwrotnie — zły traf w grupę nie ma prawa podmienić trafnego dopasowania na
  zgadywankę). `iter_subjects()` też przeliczony: kontrola duplikatów wewnątrz
  YAML teraz kluczuje po (semestr, skrot, grupa), nie samym (semestr, skrot).
  Testy: `tests/test_subjects_vs_target_repo.py` nadal 0/0 (czyta branch z
  renamami). Pełny `scan_target.py` na realnej `target_repo`: **sklasyfikowane
  1647 / bez dopasowania 30** (bez zmiany — te same liczby co A10, bo to
  przemianowania istniejących katalogów, nie nowa treść), **usunięte
  nieaktualne wpisy ground truth: 12** (stare ścieżki sprzed rename). (2026-09-17)
- [x] ~~A8. `config/taxonomy.yaml`~~ — zbędny: `syntax.yaml` (kategorie, foldery, formy, media) JEST taksonomią; architektura §3/§13 poprawiona (2026-09-17)

## B. Skrypty cyklu per-przedmiot

- [ ] B1. `scripts/prepare_subject.py --semester N --skrot X` — wycinek manifestu przedmiotu (kandydaci po ścieżce/aliasach) → `reports/{SKROT}/manifest_slice.jsonl`
- [ ] B2. `scripts/extract_text.py` — głowa tekstu (PDF/DOCX/PPTX, OCR awaryjnie) do `20_WORK/extracted_text/{sha256}.txt`, `normalized_text_hash`, `simhash`, `phash`; tylko unique, status `extracted`
- [ ] B3. `scripts/classify.py` — deterministyczny + heurystyka (regex lab/kol/egzamin/rok/prowadzący); semestr rozstrzyga skrót; `forms` waliduje; status `classified` albo `unresolved`
- [x] B4. `scripts/orglib/llm_client.py` — backend anthropic / openai / `claude -p` / `codex exec` / `agy -p` (Antigravity = Gemini) z `thresholds.yaml: llm` (per zadanie `classify`/`relate`); CLI read-only + schemat JSON; cache decyzji po sha256. `LLMClient.complete()` + `LLMConfig`/`TaskConfig`/`LLMResult`, wyjątki `LLMError`/`LLMTimeout`/`LLMParseError`, `extract_json()` (odporny na płoty markdown/prozę), `truncate_head()`; cienki CLI `scripts/llm_client.py` (typer, wzorzec jak inne skrypty — nie argparse); schemat `prompts/plan_line.schema.json`; cache SQLite `20_WORK/ai_cache.sqlite`; 30 testów w `tests/test_llm_client.py` (mockowany `runner`, zero sieci). Smoke test na kontach: `claude -p`, `codex exec -o`, `agy -p --sandbox` — wszystkie trzy działają (2026-09-17)
- [ ] B5. `prompts/classify_ambiguous.md`, `prompts/relate_cluster.md` + `scripts/ai_resolve.py` (poza sesją, masowo)
- [ ] B6. `scripts/near_dupe.py` — simhash/MinHash/phash → `relations` (near_duplicate / older_version / related); nigdy nie kasuje
- [ ] B7. `scripts/build_plan.py` → `reports/{SKROT}/plan.jsonl` (schema_version, `_meta`, plan_hash)
- [ ] B8. `scripts/validate_plan.py` — schemat, `..`, kolizje targetów, `syntax.yaml` lint, bramka confidence, dry-run diff; exit≠0 blokuje apply
- [ ] B9. Review: `scripts/review_report.py` — diff HTML near-dupe (`difflib.HtmlDiff`), miniatury, lista `unresolved`, `STATUS.md`
- [ ] B10. `scripts/apply.py` — kopiowanie wg planu na branch `subject/{SKROT}` w `target_repo` (snapshot przed), status `applied`
- [ ] B11. `scripts/verify.py` — hash po kopii == sha256, drzewo == plan, status `verified`
- [ ] B12. `scripts/provenance.py` — `reports/provenance.jsonl` + README per przedmiot do `paczka_meta/` + `00_SOURCES/linki.txt` z `source_packages`
- [ ] B13. `scripts/media.py` — pliki > progu → `90_MEDIA/{skrot}/…` + wpis w `inne/nagrania.txt`
- [ ] B14. `scripts/manual_decisions.py` — CLI do zapisu decyzji z review (conf=1.0) + eksport do `reports/manual_decisions.jsonl` (eksport/import już w `db_admin.py`)

## C. Narzędzia i integracje

- [ ] C1. `justfile`: `subject-start / plan / apply / pr` (gh issue + branch w `target_repo`, commity `plan(SKROT)`→`apply(SKROT)`→`docs(SKROT)`)
- [ ] C2. Generator issues z `subjects.yaml` (`gh issue create`, labels semester/subject/status)
- [ ] C3. `synapse` — graf relacji (notatki `.md` z wikilinkami); **po pilotażu**, na realnych danych
- [ ] C4. Pełny diff-viewer near-dupe — **po pilotażu**
- [ ] C5. Skille `.claude/skills/organizer-*` — dopasować do realnych nazw skryptów po B1–B14
- [x] C7. Delegacja multi-model: agenci projektu `codex` (`codex exec`, bez `--full-auto`) i `agy` (Antigravity CLI = Gemini; `muxer:gemini` szuka nieobecnej binarki `gemini`), `GEMINI.md` → `AGENTS.md`, `thresholds.yaml: llm` per zadanie (`classify` → `agy_cli`, `relate` → `claude_cli`), tabela koordynatora i biling (Pro, nie Max) w `CLAUDE.md`, permissions `codex exec`/`agy -p`/`claude -p` w `settings.json` (2026-09-17)
- [x] C8. Smoke test delegacji `codex` i `agy` — **oba agenty poprawione po testach**: (a) `codex exec` bez `--ignore-user-config` szedł przez `claude-code-router` (proxy `127.0.0.1:3456`) na `Claude Code API/claude-sonnet-5`, czyli delegacja „za darmo" zjadała limit Anthropic; z flagą CLI raportuje `provider: openai` (`gpt-6-astra`), zadanie read-only wykonane, `git status` bez zmian; (b) `agy -p --sandbox` w headless auto-odrzuca KAŻDE uprawnienie narzędzia (`read_file`, `command` → `jetski: no output produced`), więc Gemini nie przeczyta pliku sam — działa natomiast wklejenie treści do promptu (zweryfikowane na `AGENTS.md`: poprawne streszczenie, `--sandbox` zachowany, zero narzędzi). Oba ustalenia zapisane w `.claude/agents/{codex,agy}.md` i w `CLAUDE.md` (sekcja „Pułapka bilingowa"). (2026-09-17)
- [ ] C9. Decyzja użytkownika: czy zdjąć przejęcie `codex` przez `claude-code-router` (`~/.claude-code-router/global-profile-takeover.json`, profil `default-codex`), żeby `codex` szedł na OpenAI bez `--ignore-user-config`. Dziś obchodzimy to flagą — działa, ale każdy inny agent/skrypt wołający `codex` bez niej nadal płaci limitem Anthropic.
- [x] C6. `setup/install.sh` — sprawdzone: apt stawia rmlint/ncdu/tesseract(+pol)/poppler/jq/rclone (rclone dopisany), `just` z just.systems, venv z requirements; `gh` tylko wykrywany (instalacja ręczna wg README) (2026-09-17)

## D. Pilotaż i przedmioty

- [ ] D1. Pilotaż **AKO, sem 3** end-to-end (scan → … → PR); zebrać wnioski do B/C
- [ ] D2. Kolejność dalszych przedmiotów: semestr po semestrze SEM1→SEM7; kolejka i postęp w generowanym `STATUS.md` (nie tutaj)
- [ ] D3. Semestry magisterskie: uzupełnić `subjects.yaml: magisterskie` przed ich przetwarzaniem

## E. Dokumentacja

- [x] E1. README: sekcja „Skrypty” z realnymi nazwami i kolejnością po A3–A6 (2026-09-17)
- [x] E2. `docs/SOURCES_TREE.md` (generowany przez `scan.py`; pierwszy snapshot: 14 paczek, 9 540 katalogów, 48 049 plików, 37,0 GiB) (2026-09-17)
- [ ] E3. `STATUS.md` (generowany: przedmioty × etapy + liczby)
