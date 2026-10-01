# Zależności

Co trzeba mieć zainstalowane, żeby uruchomić organizer: narzędzia systemowe
i środowisko Pythona.

Wszystko stawia jeden skrypt (idempotentny):
```bash
bash setup/install.sh --with-apt     # pakiety systemowe + muxer + agenty + status line + venv
```
Szczegóły i lista pluginów: `setup/PLUGINS.md`. Poniżej to samo ręcznie.

## Narzędzia systemowe
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
- **Node.js 20+** (`node`, `npm`) — front studia (`studio/web`, Svelte + Vite)

## Python (self-contained w tym folderze)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r setup/requirements.txt
```

Źródłem prawdy o zależnościach Pythona jest `pyproject.toml` — sekcja
`[project.dependencies]` (zależności runtime) i
`[project.optional-dependencies].test` (`pytest`, `hypothesis`). `setup/requirements.txt`
nadal istnieje, pinowany 1:1 z `pyproject.toml` (komentarze „dlaczego" siedzą
tam), bo to jego czyta `setup/install.sh`, instalując pipem do `organizer/.venv`:

```
PyMuPDF>=1.24      # tekst z PDF; od 1.24 moduł nazywa się `pymupdf` (nie `fitz`)
pdfplumber         # tekst/tabelki z PDF (awaryjnie)
python-docx        # tekst z DOCX
python-pptx        # tekst ze slajdów PPTX (także .ppsx)
openpyxl           # tekst z arkuszy XLSX/XLSM
xlrd>=2.0          # tekst ze starych arkuszy XLS (2.x czyta WYŁĄCZNIE .xls)
odfpy              # tekst z OpenDocument (.odt/.ods/.odp)
datasketch         # MinHash + LSH (near-dupe + bucketowanie kandydatów)
imagehash          # perceptual hash obrazów
Pillow             # obrazy / miniatury
rapidfuzz          # fuzzy match nazw / podobieństwo tekstu
blake3             # szybki hash (alternatywa dla sha256)
ocrmypdf           # OCR dokładający warstwę tekstu do PDF (wymaga tesseract)
pytesseract        # OCR (backend tesseract)
sqlite-utils       # wygodna praca z SQLite
typer              # CLI
PyYAML             # config
jsonschema         # walidacja linii planu wg prompts/plan_line.schema.json (validate_plan.py)
anthropic          # backend AI (Claude) — dla llm_client
openai             # backend AI (Codex) — dla llm_client
fastapi            # backend studia (studio/api) — lokalne API nad indeksem
uvicorn            # serwer ASGI studia; nasłuch wyłącznie 127.0.0.1
httpx              # klient HTTP: TestClient FastAPI i smoke startu serwera w testach
pytest             # testy
hypothesis         # własności granicy ścieżek (tests/unit/test_path_safety_properties.py)
```

Stare formaty binarne (`.doc`/`.ppt`/`.pps`) czyta systemowy pakiet `catdoc`
(`catdoc`, `catppt`) — instaluje go `setup/install.sh --with-apt`. Jego brak nie
jest błędem: `extract_text.py` raportuje wtedy metodę `no_converter`.

Dopisując zależność, dopisz ją w obu plikach — `pyproject.toml` jest źródłem
prawdy, `setup/requirements.txt` musi zostać z nim w zgodzie, bo `install.sh`
instaluje właśnie z niego.
