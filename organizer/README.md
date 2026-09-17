# organizer (Paczka Organizer)

Projekt w `paczka-tools/` — jednorazowe narzędzie do scalenia kilku starych
studenckich „paczek" materiałów w jedną, uporządkowaną paczkę. Deterministycznie
tam, gdzie się da; AI tylko tam, gdzie trzeba zrozumieć treść. Nie jest
deployowane — uruchamiane na żądanie, produkuje PR-y do repo docelowego
(`config/paths.yaml: target_repo`; dziś `10_NEW/PaczkaInfaPG`, docelowo `paczka-content`).

Rodzeństwo w `paczka-tools/`: `ects_extractor` (buduje strukturę paczki z
oficjalnej strony przedmiotów) — organizer robi to samo, tylko ze starych paczek.

- Architektura: [`docs/ARCHITEKTURA_FINALv1.md`](docs/ARCHITEKTURA_FINALv1.md)
- Struktura repo i organizacji: [`docs/ORGANIZACJA.md`](docs/ORGANIZACJA.md)
- Zasady pracy AI: [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md)
- Setup Claude Code (muxer, agenty, skille, status line): [`setup/PLUGINS.md`](setup/PLUGINS.md),
  ocena źródeł: [`docs/CLAUDE_CODE_SETUP.md`](docs/CLAUDE_CODE_SETUP.md)

## Idea w jednym zdaniu

Skrypty robią wszystko, co da się ustalić deterministycznie (hash, dedup,
klasyfikacja po ścieżce/nazwie); AI dostaje wyłącznie niejednoznaczne resztki,
jeden przedmiot na raz; człowiek zatwierdza plan zanim cokolwiek zostanie
skopiowane. Źródła są read-only, nic nie jest kasowane, provenance zachowane.

## Pipeline

```
scan → hash → dedup (pliki + foldery) → extract → classify (det.) →
  [AI dla unresolved] → plan → validate → [review] → apply → verify
```

Wynik (`apply`) trafia do `paczka/` w klonie repo docelowego, na branchu
`subject/{SKROT}`, i dalej jako PR. Kod i operacyjne raporty zostają tutaj.

## Układ

```
paczka-tools/organizer/          # ← tu odpalasz `claude`
├── CLAUDE.md  AGENTS.md         # zasady pracy AI + polityka koordynatora (muxer)
├── README.md  SKILLS.md
├── .claude/                     # commitowane: settings.json, hooks/guard-sources.py,
│                                #   agents/ (5 z VoltAgent), skills/ (organizer-*)
├── docs/                        # ARCHITEKTURA_FINALv1.md, ORGANIZACJA.md, CLAUDE_CODE_SETUP.md, SOURCES_TREE.md
├── config/                      # paths.yaml, subjects.yaml, syntax.yaml, thresholds.yaml
├── prompts/                     # prompty AI (classify_ambiguous, relate_cluster)
├── scripts/                     # etapy pipeline (Python)
├── reports/                     # eksporty: inventory, plany, provenance-operacyjne (w gicie)
└── setup/                       # install.sh, PLUGINS.md, requirements.txt, statusline.sh
```

Poza gitem — workspace `~/dev/paczka/PaczkaMerge/` (ścieżki w `config/paths.yaml`):
```
00_SOURCES/            # stare paczki (read-only, backup na Drive)
10_NEW/PaczkaInfaPG/   # klon repo docelowego; apply pisze do paczka/ (branch subject/{SKROT})
20_WORK/               # organizer.sqlite, extracted_text, thumbnails
90_MEDIA/              # duże wideo/audio wyjęte z paczki
paczka-tools/          # ten klon
```

Wszystkie ścieżki są w `config/paths.yaml` — organizer działa niezależnie od tego,
gdzie leży checkout repo docelowego.

## Zależności

Wszystko stawia jeden skrypt (idempotentny):
```bash
bash setup/install.sh --with-apt     # pakiety systemowe + muxer + agenty + status line + venv
```
Szczegóły i lista pluginów: `setup/PLUGINS.md`. Poniżej to samo ręcznie.

### Narzędzia systemowe
```bash
# Debian/Ubuntu
sudo apt update && sudo apt install -y \
  rmlint ncdu tesseract-ocr tesseract-ocr-pol poppler-utils rclone
# gh (GitHub CLI): https://github.com/cli/cli#installation
# just (runner): https://github.com/casey/just   (opcjonalnie)
```

- **rmlint** — bootstrap dedup (pliki + `--merge-directories` dla folderów)
- **ncdu** — interaktywny raport rozmiaru (`ncdu -o snapshot.json`)
- **tesseract** (+ `pol`) — OCR na żądanie
- **poppler-utils** — `pdftotext` awaryjnie
- **rclone** — sync z Google Drive
- **gh** — automatyzacja issue/PR (cross-repo do `paczka-content`)

### Python (self-contained w tym folderze)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`setup/requirements.txt`:
```
PyMuPDF            # tekst z PDF (fitz)
pdfplumber         # tekst/tabelki z PDF (awaryjnie)
python-docx        # tekst z DOCX
python-pptx        # tekst ze slajdów PPTX
datasketch         # MinHash + LSH (near-dupe + bucketowanie kandydatów)
imagehash          # perceptual hash obrazów
Pillow             # obrazy / miniatury
rapidfuzz          # fuzzy match nazw / podobieństwo tekstu
blake3             # szybki hash (alternatywa dla sha256)
ocrmypdf           # OCR dokładający warstwę tekstu do PDF
pytesseract        # OCR (backend tesseract)
sqlite-utils       # wygodna praca z SQLite
typer              # CLI
PyYAML             # config
anthropic          # backend AI (Claude) — dla llm_client
openai             # backend AI (Codex) — dla llm_client
```

## Quickstart (docelowo)

```bash
# 0. Bootstrap — poznaj skalę dublowania (nic nie kasuje)
rmlint --merge-directories /ścieżka/do/00_SOURCES
ncdu -o sources_snapshot.json /ścieżka/do/00_SOURCES

# 1. Skan + dedup na całości (mapa)
python scripts/scan.py
python scripts/hash_files.py
python scripts/fold_hash.py
python scripts/dedup_report.py

# 2. Pilotaż jednego przedmiotu e2e (np. AK, sem3)
just subject-start AK 3          # gh issue + branch (w target_repo)
python scripts/prepare_subject.py --semester 3 --skrot AK
# → classify → plan → review → apply → verify
just subject-pr AK 3
```

> Skrypty powstają po zatwierdzeniu architektury — patrz plan działania w
> `docs/ARCHITEKTURA_FINALv1.md`.
