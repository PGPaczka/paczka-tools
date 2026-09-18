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
- Zasady wspólne agentów: [`AGENTS.md`](AGENTS.md); adapter Claude:
  [`CLAUDE.md`](CLAUDE.md)
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

## Skrypty (pierwszy przebieg)

Kolejność uruchamiania (robione raz, na całości źródeł):

1. `python scripts/db_admin.py init` — tworzy/aktualizuje schemat `20_WORK/organizer.sqlite`.
2. `python scripts/scan.py` — statuje paczki źródłowe (`00_SOURCES/`, read-only),
   zapisuje `source_packages`/`folders`/`files` (status `discovered`) i generuje
   `reports/SOURCES_TREE.md`.
3. `python scripts/hash_files.py` — liczy sha256 plików w statusie `discovered`,
   zapisuje `content` (dedup plików), przestawia status na `hashed`.
4. `python scripts/fold_hash.py` — liczy hashe poddrzew, oznacza dokładne
   duplikaty katalogów (`folders.duplicate_of`) i zapisuje `reports/folder_overlap.csv`.
5. `python scripts/dedup_report.py` — liczy z bazy unique vs duplicate (liczby,
   bajty, per paczka) → `reports/dedup_summary.md`, `reports/inventory.jsonl`.
6. `python scripts/scan_target.py` — skanuje istniejącą `paczka/` w repo
   docelowym jako ground truth: content + status `applied` + klasyfikacja
   `manual`, conf=1.0.

| Skrypt | Wejście | Wyjście | Wznawialność / uwagi |
|---|---|---|---|
| `db_admin.py init` | brak (zakłada bazę) | schemat w `20_WORK/organizer.sqlite` | idempotentny; `init` też aktualizuje istniejący schemat |
| `scan.py` | `00_SOURCES/` (read-only) | `source_packages`, `folders`, `files` (`discovered`) + `reports/SOURCES_TREE.md` | wznawialny — pomija niezmienione poddrzewa; exit 3 = skan częściowy (coś pominięto, zapis i tak się odbył), 1 = zły katalog/nieznana paczka, 2 = sprzeczne opcje |
| `hash_files.py` | `files` w statusie `discovered` | `content` (sha256, content_kind), `files` → `hashed` | wznawialny (batch domyślnie 200); `--retry-errors` cofa `error` na `discovered`; `--package`/`--limit` do ograniczenia zakresu |
| `fold_hash.py` | `folders`/`files` z bazy | `folders.duplicate_of`, `reports/folder_overlap.csv` | dwa przejścia (FK); próg z `config/thresholds.yaml`; `--no-overlap` pomija raport |
| `dedup_report.py` | baza (`content`/`files`/`folders`) | `reports/dedup_summary.md`, `reports/inventory.jsonl` | tylko odczyt bazy, bez zapisu do źródeł ani do dysku poza `reports/` |
| `scan_target.py` | `paczka/` w `target_repo` (read-only) | `files` → status `applied`, klasyfikacja `manual` conf=1.0 | `--limit`/`--batch`; nie modyfikuje `target_repo`, tylko odczyt |

Uwagi:

- Wszystkie ścieżki (`00_SOURCES`, `target_repo`, `20_WORK`, `90_MEDIA`) tylko
  z `config/paths.yaml` — nic nie jest hardkodowane w skryptach.
- Źródła (`00_SOURCES/`) są read-only; wspólny hook
  `.agents/hooks/guard-sources.py` blokuje tam zapis w Claude i Codex.
- Nic nie jest fizycznie kasowane. Dedup jest logiczny, w bazie
  (`folders.duplicate_of`) — oba foldery/pliki zostają na dysku.
- Kody wyjścia `scan.py`: `0` pełny skan, `3` skan częściowy (coś pominięto —
  nieczytelny katalog, nazwa spoza UTF-8, błąd stat), `1` zły katalog źródeł
  lub nieznana paczka, `2` sprzeczne opcje.
- Do gita trafiają: `reports/SOURCES_TREE.md`, `reports/dedup_summary.md`,
  `reports/inventory.jsonl`, `reports/folder_overlap.csv`,
  `reports/bootstrap/bootstrap_rmlint.txt`. Poza gitem: `20_WORK/organizer.sqlite`
  (operacyjne źródło prawdy, odtwarzalne przez re-run).
- Wynik pierwszego przebiegu na całości źródeł: 14 paczek, 48 049 plików,
  37,0 GiB, z czego 18 426 unikalnych treści i 17,9 GiB kopii (48,4%).

`python scripts/llm_client.py --task classify|relate --prompt-file PLIK|-` — cienki
CLI nad `orglib/llm_client.py` (backend anthropic/openai/`claude -p`/`codex exec`/`agy -p`
z `config/thresholds.yaml: llm`, cache po sha256 promptu w `20_WORK/ai_cache.sqlite`);
smoke test backendów, nieużywany w automatycznym cyklu per-przedmiot.

## Skrypty cyklu per-przedmiot — gotowe B1, B5

Po pierwszym przebiegu przygotuj wycinek z **istniejącego indeksu SQLite**:

```bash
just subject-prepare 3 AKO
# Stary alias też działa: just subject-prepare 3 AK
# Kolizja SI w SEM7 wymaga grupy:
just subject-prepare 7 SI --grupa KASK_Architektura_Systemów_Komputerowych
just subject-prepare 3 AKO --help
```

`scripts/prepare_subject.py` nie otwiera materiałów, nie wywołuje AI i nie
modyfikuje statusów ani klasyfikacji, w tym ground truth. Baza jest otwierana
w trybie SQLite `mode=ro` / `query_only`, bez inicjalizacji schematu.

Pozycje, których deterministyka nie rozstrzygnęła, domyka klasyfikator AI:

```bash
just subject-ai-resolve 3 AKO --dry-run    # co poszłoby do modelu i jakim backendem
just subject-ai-resolve 3 AKO --limit 10   # próbka: oceń jakość, zanim puścisz resztę
just subject-ai-resolve 3 AKO              # reszta; sha256 już zapisane są pomijane
```

`scripts/ai_resolve.py` zapisuje `plan.ai.jsonl` obok manifestu — jedna linia na
sha256, walidowana wobec `prompts/plan_line.schema.json`. Progi `confidence`
z `config/thresholds.yaml` są wiążące: deklaracja modelu nie przepchnie pozycji
obok review. Backend bierze się z `thresholds.yaml: llm` (domyślnie `codex_cli`),
więc klasyfikacja nie obciąża limitu koordynatora. Skrypt nie dotyka materiałów
i nie wykonuje `apply`.
Opcje `--db PLIK` i `--out-dir KATALOG` pozwalają jawnie wskazać indeks oraz
dokładny katalog wyjściowy. Domyślna baza pochodzi z `config/paths.yaml`.
Raport zapisuje się atomowo; błąd pozostawia poprzedni raport. Zapis pod
`sources`, `target_repo`, `media` (także przez symlink), nadpisanie bazy oraz
symlink jako plik wyjściowy są odrzucane. Również baza nie może leżeć w tych
chronionych drzewach: SQLite może potrzebować pomocniczych plików WAL/SHM.

Domyślnie wynik trafia do `reports/{SKROT}/manifest_slice.jsonl`, np.
`reports/AKO/manifest_slice.jsonl`. Jeżeli kanoniczny skrót powtarza się w
katalogu przedmiotów, ścieżka zawiera pełną tożsamość:
`reports/SEM{semester}/{grupa}/{SKROT}/manifest_slice.jsonl`. Dzięki temu
kolejne przygotowanie SI/WFI/SK nie nadpisuje raportu innego przedmiotu.
Jawny `--out-dir` omija ten automatyczny podział — używaj osobnych katalogów.

**Kontrakt manifestu v1:** jeden obiekt JSON na SHA-256, stabilny porządek
i bajtowo identyczny wynik dla tego samego indeksu i konfiguracji:

- `schema_version`, `sha256`, `source_sha256` (oba hashe równe);
- `semester`, `subject_key` (kanoniczny skrót), `grupa`, `target_dir`;
- `source_paths` — wszystkie zindeksowane kopie treści, także poza
  dopasowanym przedmiotem i w folderach-duplikatach;
- `matched_source_paths` — zdrowe kopie będące kandydatami tego przedmiotu;
- `source_path` — preferowana zdrowa kopia spoza poddrzew `duplicate_of`
  do przyszłej ekstrakcji; `null` oznacza brak takiej kopii i wymaga review;
- `content_kind`, `size_bytes`, `needs_review`, `review_reasons`.

Dopasowanie wykorzystuje pełne tokeny skrótu, aliasu lub nazwy w komponentach
ścieżki (również nazwie paczki/pliku), bez rozróżniania wielkości liter,
separatorów i polskich znaków. Rozpoznaje m.in. `SEM3`, `sem_3`, `semestr III`.
Jawny inny semestr/grupa wyklucza dopasowanie; brak semestru, kolizja nazw,
sprzeczne pochodzenie albo rozmiary oznaczają review. B1 **nie jest
klasyfikatorem**: nie nadaje confidence, kategorii ani zgody na kopiowanie.
Fuzzy i treść dokumentów nie są tu używane; nieznane warianty nazw wymagają
uzupełnienia aliasów lub późniejszego review. Wpisy bez poprawnego hasha,
bez `content`, w stanie `discovered`/`error` nie inicjują kandydatury.
Semestry magisterskie pozostają poza zakresem (D3).

Dalsze skrypty B2–B14 (poza istniejącym B4) są nadal do implementacji.
Nie uruchamiaj jeszcze docelowego Quickstart e2e poniżej.

## Układ

```
paczka-tools/organizer/          # ← tu odpalasz `just claude` lub `just codex`
├── AGENTS.md  CLAUDE.md         # zasady wspólne + adapter Claude/muxer
├── .agents/                     # wspólne hooki + symlinki skills dla Codexa
├── ../.codex/                   # hook, ustawienia multi-agent i role Codexa
├── README.md  SKILLS.md
├── .claude/                     # commitowane: settings.json, hooks/guard-sources.py,
│                                #   agents/ (5 z VoltAgent), skills/ (organizer-*)
├── docs/                        # dokumentacja architektury, organizacji i konfiguracji
├── config/                      # paths.yaml, subjects.yaml, syntax.yaml, thresholds.yaml
├── prompts/                     # prompty AI (classify_ambiguous, relate_cluster)
├── scripts/                     # etapy pipeline (Python)
├── reports/                     # SOURCES_TREE.md, inventory, plany, handoff (w gicie)
│   └── bootstrap/               # historyczne raporty wstępne
└── setup/                       # install.sh, PLUGINS.md, requirements.txt, statusline.sh
```

## Agenci interaktywni

Claude pozostaje domyślnym koordynatorem, ale stan projektu i procedury nie są
zależne od hosta. **Zawsze startuj przez `just`, nie przez gołe `claude`/`codex`** —
launcher wchodzi do katalogu organizera, ustawia zmienne sesji i pilnuje, żeby
Codex nie wystartował na cudzym koncie ani z zapisem do źródeł.

### Raz na maszynę

```bash
bash setup/install.sh        # venv, zależności, plugin muxer, settings.local.json
just agent-setup             # profil ~/.codex/paczka-openai.config.toml
just agent-doctor            # kontrola: CLI, konto Codexa, ścieżki z paths.yaml
```

`agent-doctor` musi skończyć bez `BRAK`/`BŁĄD`. Zgłasza m.in., gdy bazowy
`~/.codex/config.toml` przestał wskazywać OpenAI — wtedy delegacja poszłaby na
cudze konto (patrz „Dlaczego nie `--ignore-user-config`” niżej).

### Claude — koordynator

```bash
just claude                  # sesja interaktywna w paczka-tools/organizer/
just claude --resume         # argumenty idą wprost do CLI
just claude -p "pytanie"     # jednorazowy prompt, bez sesji
```

Sesja dostaje `.claude/settings.json`: plugin muxer, hook `guard-sources.py`,
katalogi robocze z `config/paths.yaml` i deny-listę na `00_SOURCES`. Skille
`organizer-*` są wtedy dostępne jako `/organizer-subject AKO 3` itd.

### Codex — GPT interaktywnie

Trzy tryby, różnią się **wyłącznie** tym, gdzie Codex może pisać:

```bash
just codex-read              # nic nie zapisuje — analiza, drugie zdanie, review
just codex                   # organizer + 20_WORK (domyślny do pracy nad kodem)
just codex-ship              # dodatkowo target_repo i 90_MEDIA — tylko po akceptacji planu
```

Argumenty dopisuje się wprost, **bez `--`** (recepty `codex-read`/`codex-ship` już
go dodają, drugi psuje wywołanie):

```bash
just codex-read "streść reports/HANDOFF.md"    # start z gotowym promptem
just codex --version                            # argumenty idą do CLI
```

`codex-ship` odmówi startu, gdy `target_repo` nie jest klonem gita. **Nigdy** nie
dodawaj `00_SOURCES` jako katalogu zapisywalnego — żaden z trybów tego nie robi.

Że sesja idzie na właściwe konto, potwierdzisz przez `just agent-doctor` (linie
`profil Codexa` i `bazowy config Codexa`) albo `codex doctor` (sekcja
`Configuration` → `model … · openai`). Model zmienisz bez edycji plików:

```bash
CODEX_MODEL=gpt-6-astra just codex
CODEX_PROFILE=inny-profil just codex     # profil musi mieć model_provider = "openai"
```

Launcher czyta `~/.codex/<profil>.config.toml` i **odmawia startu**, jeśli profil
nie wymusza `model_provider = "openai"`. Dzięki temu jest odporny na to, co ktoś
ustawi w bazowym `~/.codex/config.toml`.

### Który model wykonuje pracę AI

Backend zadań pipeline'u bierze się z `config/thresholds.yaml: llm` — domyślnie
`classify` i `relate` idą na `codex_cli`, więc praca klasyfikacyjna obciąża konto
ChatGPT, a limit koordynatora zostaje na planowanie i ocenę. `just claude` tego
nie nadpisuje; skierowanie zadania na Claude to świadoma decyzja na jedną sesję:

```bash
PACZKA_LLM_RELATE_BACKEND=claude_cli just claude
```

### Dlaczego nie `--ignore-user-config`

Flaga wygląda jak wygodny sposób na ominięcie cudzego proxy w bazowym configu
Codeksa, ale odcina też sekcję `[hooks.state]` — a wtedy Codex przestaje
uruchamiać `.codex/hooks.json`, czyli **guard chroniący `00_SOURCES` milknie**.
Konto wymuszaj jawnie: `codex exec -c model_provider="openai" …`.

Wspólne zasady są w `AGENTS.md`, kontrakt przekazania stanu w
`reports/HANDOFF.md`, a deterministyczne operacje w `justfile` i `scripts/`.

Codex ma projektowe subagenty w `../.codex/agents/`: `explorer`, `runner`,
`reviewer`, `python_pro`, `sql_pro`, `test_automator`,
`documentation_engineer` i `readme_generator`. `../.codex/config.toml`
centralnie wybiera ich model i limit równoległości; każda rola ma osobno
przypisany reasoning oraz sandbox. Role analityczne są read-only, a role
implementacyjne zapisują wyłącznie w granicach sandboxu sesji nadrzędnej.

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
pip install -r setup/requirements.txt
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
