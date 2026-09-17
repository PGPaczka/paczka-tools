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
- [ ] A7. Skan istniejącej `paczka/` w `target_repo` = ground truth (lock; hash + ścieżka docelowa → `applied`/klasyfikacja `manual`, conf=1.0)
- [ ] A9. **Decyzja użytkownika:** istniejąca `paczka/` w `target_repo` używa `SEM3/AKO_Architektura_Komputerów` (bez nawiasów, alias AKO), `paczka/SEM1/sources/`, `paczka/ogolne/`, `Magisterskie_SEM2/<Nazwa bez skrótu>` — a `syntax.yaml`/`config.TARGET_PATH_TEMPLATE` zakłada `({SKROT})_{Nazwa}`. Ground truth ma pierwszeństwo (reguła 2): albo zmienić szablon w configu na `{SKROT}_{Nazwa}`, albo świadomie przemianować w repo docelowym. Do rozstrzygnięcia przed B3/B7 (classify/plan). Wykryte 2026-09-17 przy A7.
- [x] ~~A8. `config/taxonomy.yaml`~~ — zbędny: `syntax.yaml` (kategorie, foldery, formy, media) JEST taksonomią; architektura §3/§13 poprawiona (2026-09-17)

## B. Skrypty cyklu per-przedmiot

- [ ] B1. `scripts/prepare_subject.py --semester N --skrot X` — wycinek manifestu przedmiotu (kandydaci po ścieżce/aliasach) → `reports/{SKROT}/manifest_slice.jsonl`
- [ ] B2. `scripts/extract_text.py` — głowa tekstu (PDF/DOCX/PPTX, OCR awaryjnie) do `20_WORK/extracted_text/{sha256}.txt`, `normalized_text_hash`, `simhash`, `phash`; tylko unique, status `extracted`
- [ ] B3. `scripts/classify.py` — deterministyczny + heurystyka (regex lab/kol/egzamin/rok/prowadzący); semestr rozstrzyga skrót; `forms` waliduje; status `classified` albo `unresolved`
- [ ] B4. `scripts/llm_client.py` — backend anthropic / openai / `claude -p` / `codex exec` z `thresholds.yaml: llm`; cache decyzji po sha256
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
- [ ] C6. `setup/install.sh` — sprawdzić, że instaluje rmlint/ncdu/tesseract(+pol)/poppler/gh/just

## D. Pilotaż i przedmioty

- [ ] D1. Pilotaż **AK, sem 3** end-to-end (scan → … → PR); zebrać wnioski do B/C
- [ ] D2. Kolejność dalszych przedmiotów: semestr po semestrze SEM1→SEM7; kolejka i postęp w generowanym `STATUS.md` (nie tutaj)
- [ ] D3. Semestry magisterskie: uzupełnić `subjects.yaml: magisterskie` przed ich przetwarzaniem

## E. Dokumentacja

- [ ] E1. README: sekcja „Skrypty” z realnymi nazwami i kolejnością po A3–A6
- [ ] E2. `docs/SOURCES_TREE.md` (generowany przez `scan.py`)
- [ ] E3. `STATUS.md` (generowany: przedmioty × etapy + liczby)
