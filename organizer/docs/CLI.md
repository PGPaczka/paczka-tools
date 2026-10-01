# Paczka Organizer z wiersza poleceń

Cała droga od stosu cudzych paczek do materiałów w repo: **jakie komendy, w jakiej
kolejności i po czym poznać, że etap się udał**. Wersja z interfejsem — te same
etapy, ale w przeglądarce — jest w `studio/README.md`.

Jeśli robisz to pierwszy raz, zacznij od [`PIPELINE.md`](PIPELINE.md): tam jest,
**co dany etap znaczy** i czemu plan buduje się dwa razy. Tutaj są same komendy.

Zasady, na których stoi ten proces (`AGENTS.md`), w trzech zdaniach: `00_SOURCES`
jest tylko do odczytu, nic nie jest kasowane, a materiały ruszają się dopiero po
zaakceptowaniu konkretnego planu. Każda komenda niżej albo czyta, albo pisze do
`20_WORK` — z jednym wyjątkiem, `just subject-apply --yes`, który jako jedyny
dotyka repo paczki.

Wszystko uruchamiasz z katalogu `paczka-tools/organizer/`.

---

## Mapa: co z czym się łączy

```
źródła (00_SOURCES, read-only)
   │  scan → hash → fold-hash → dedup-report → extract
   ▼
indeks 20_WORK/organizer.sqlite  ◄── scan-target (ground truth z repo paczki)
   │  subject-prepare → subject-classify → subject-relate → subject-ai-resolve
   ▼
plan przedmiotu (reports/{SKROT}/plan.jsonl)
   │  subject-validate  (bramka: kod 2 = nie wykonuj)
   │  subject-review    (strona do obejrzenia okiem)
   ▼
   ⟨ Twoja akceptacja konkretnego planu ⟩
   │  subject-apply --yes --expect-hash … → subject-verify
   ▼
repo paczki, gałąź subject/{SKROT}   → commit i PR robisz Ty
```

Indeks jest odtwarzalny i leży poza gitem; plany, raporty i decyzje są tekstowe
i wersjonowane.

---

## 0. Raz na maszynę

```bash
bash setup/install.sh --with-apt   # venv, zależności, narzędzia systemowe
just agent-doctor                  # kontrola: CLI, konta, ścieżki z paths.yaml
just db-init                       # pusty indeks w 20_WORK/organizer.sqlite
```

Ścieżki do katalogów spoza repo są **wyłącznie** w `config/paths.yaml` — jeśli
Twój układ katalogów jest inny, popraw ten plik, a nie skrypty.

Na inny workspace (np. kopię do eksperymentów) wskazujesz całym katalogiem
konfiguracji, bez dotykania repo:

```bash
PACZKA_CONFIG_DIR=/ścieżka/do/innego/config just status
```

---

## 1. Pierwszy przebieg: poznaj, co masz

Te cztery etapy dotyczą **całości** źródeł i wystarczy je zrobić raz (kolejne
przebiegi dopisują tylko nowe rzeczy).

```bash
just scan                    # katalogi i pliki → tabele folders/files
just hash                    # sha256 każdego pliku (status: hashed)
just fold-hash               # podpisy katalogów: tree_hash, content_set_hash
just dedup-report            # które katalogi są duplikatami (logicznie, bez kasowania)
just extract                 # tekst, simhash, perceptual hash (status: extracted)
```

Przydatne warianty:

```bash
just scan --package "Paczka 3 sem"    # tylko jedna paczka źródłowa
just hash --retry-errors              # ponów pliki, które padły
just extract --no-ocr                 # bez tesseractu (szybciej)
just extract --ocr-images             # OCR także dla obrazów (opt-in, jest ich dużo)
just extract --retry-errors           # ponów nierozpoznane skany
```

### 1.1 Szczegóły skryptów i formaty

| Skrypt | Wznawialność / uwagi |
|---|---|
| `scan.py` | pomija niezmienione poddrzewa; kod `3` = skan częściowy (coś pominięto — nieczytelny katalog, nazwa spoza UTF-8, błąd stat — zapis i tak się odbył), `1` = zły katalog źródeł/nieznana paczka, `2` = sprzeczne opcje |
| `hash_files.py` | batch domyślnie 200; `--retry-errors` cofa `error` na `discovered` |
| `fold_hash.py` | dwa przejścia (FK); próg z `config/thresholds.yaml`; `--no-overlap` pomija `reports/folder_overlap.csv` |
| `dedup_report.py` | tylko odczyt bazy → `reports/dedup_summary.md`, `reports/inventory.jsonl` |
| `scan_target.py` | `--limit`/`--batch`; tylko odczyt, nie modyfikuje `target_repo` |
| `extract_text.py` | praca raz na sha256 (druga kopia i re-run biorą tekst z dysku, `--force` wymusza ponownie); `--text-dir` wskazujący wnętrze `00_SOURCES`/`target_repo`/`90_MEDIA` kończy się kodem 2; OCR awaryjny tylko dla PDF bez warstwy tekstowej (`--no-ocr` wyłącza, `--ocr-images` dokłada obrazy); brak tekstu (archiwum, media, skan bez OCR) ≠ błąd |
| `db_admin.py refresh-kinds` | przelicza `content.content_kind` z mapy `orglib/kinds.py`; potrzebne po dopisaniu rozszerzenia do mapy; dry-run domyślnie, zapis dopiero z `--apply` |

Formaty i czym są czytane: PDF → PyMuPDF (+ pdfplumber awaryjnie, + OCR dla
skanów), `.docx` → python-docx, `.pptx`/`.ppsx` → python-pptx, `.xlsx`/`.xlsm`
→ openpyxl, `.xls` → xlrd, `.odt`/`.ods`/`.odp` → odfpy, `.csv` i tekst/kod →
wprost (UTF-8, awaryjnie cp1250), obrazy → phash (+ OCR na żądanie). Stare
formaty binarne `.doc`/`.ppt`/`.pps` wymagają systemowego pakietu `catdoc`
(`catdoc`, `catppt`; instaluje go `setup/install.sh --with-apt`) — bez niego
wynik ma metodę `no_converter`. Konwerter dostaje jawne kodowanie źródłowe
`--legacy-charset` (domyślnie `cp1250`): bez tego `catdoc` zakłada cp1252
i polskie znaki zamieniają się w krzaki (sprawdzone na realnym pliku ze źródeł).

Do gita trafiają: `reports/SOURCES_TREE.md`, `reports/dedup_summary.md`,
`reports/inventory.jsonl`, `reports/folder_overlap.csv`,
`reports/bootstrap/bootstrap_rmlint.txt`. Poza gitem: `20_WORK/organizer.sqlite`
(operacyjne źródło prawdy, odtwarzalne przez re-run). Wynik pierwszego
przebiegu na całości źródeł: 14 paczek, 48 049 plików, 37,0 GiB, z czego 18 426
unikalnych treści i 17,9 GiB kopii (48,4%).

`python scripts/llm_client.py --task classify|relate --prompt-file PLIK|-` —
cienki CLI nad `orglib/llm_client.py` (backend anthropic/openai/`claude -p`/
`codex exec`/`agy -p` z `config/thresholds.yaml: llm`, cache po sha256 promptu
w `20_WORK/ai_cache.sqlite`); smoke test backendów, nieużywany w automatycznym
cyklu per-przedmiot.

Po drodze warto poznać ground truth, czyli to, co już leży poukładane w repo
paczki — inaczej plan zaproponuje skopiowanie rzeczy, które tam są:

```bash
just scan-target             # wczytuje paczka/ z target_repo do tabeli applied
```

**Sprawdzenie stanu (nie kodu):**

```bash
just index-check             # spójność indeksu
just sources-check           # czy źródła są nadal takie, jak je zapisał skan
just status                  # reports/STATUS.md: 98 przedmiotów × etapy
```

`status_report.py` liczy stan z indeksu: ile treści jest już w paczce (ground
truth), ile ma plan, ile czeka na obejrzenie i czego nikt jeszcze nie tknął.
Ground truth jest liczony osobno od planu — inaczej raport twierdziłby, że
przedmiot jest zrobiony, choć to tylko materiały ułożone ręcznie lata temu.

---

## 2. Cykl jednego przedmiotu

Pracujesz **jednym przedmiotem naraz**; tożsamość to `(semestr, skrót)`, a gdy
skrót jest wieloznaczny — dodatkowo `--grupa` (np. SEM7 SI).

### 2.1 Wycinek indeksu

```bash
just subject-prepare 3 AKO
# → reports/AKO/manifest_slice.jsonl
```

Nie otwiera materiałów, nie woła AI, nie zmienia statusów. Alias przedmiotu też
zadziała (`just subject-prepare 3 AK`). Baza jest otwierana w trybie SQLite
`mode=ro`/`query_only`, bez inicjalizacji schematu — skrypt nic nie zapisuje.

Kolizję skrótu w obrębie semestru rozstrzyga `--grupa`:

```bash
just subject-prepare 7 SI --grupa KASK_Architektura_Systemów_Komputerowych
just subject-prepare 3 AKO --help
```

Jeżeli kanoniczny skrót powtarza się w katalogu przedmiotów, ścieżka wyjścia
zawiera pełną tożsamość — `reports/SEM{semester}/{grupa}/{SKROT}/manifest_slice.jsonl`
zamiast `reports/{SKROT}/manifest_slice.jsonl` — więc kolejne przygotowanie
SI/WFI/SK nie nadpisuje raportu innego przedmiotu. Opcje `--db PLIK`
i `--out-dir KATALOG` wskazują indeks i katalog wyjściowy jawnie (`--out-dir`
omija automatyczny podział); raport zapisuje się atomowo, błąd zapisu zostawia
poprzedni plik. Zapis pod `sources`, `target_repo`, `media` (także przez
symlink), nadpisanie bazy oraz symlink jako wyjście są odrzucane — baza też nie
może leżeć w tych chronionych drzewach (SQLite potrzebuje plików WAL/SHM).

**Kontrakt manifestu v1:** jeden obiekt JSON na SHA-256, stabilny porządek
i bajtowo identyczny wynik dla tego samego indeksu i konfiguracji —
`schema_version`, `sha256`/`source_sha256` (równe), `semester`, `subject_key`
(kanoniczny skrót), `grupa`, `target_dir`, `source_paths` (wszystkie
zindeksowane kopie, też poza dopasowanym przedmiotem i w folderach-duplikatach),
`matched_source_paths` (zdrowe kopie kandydujące), `source_path` (preferowana
zdrowa kopia spoza poddrzew `duplicate_of` do przyszłej ekstrakcji; `null` =
brak takiej kopii i wymaga review), `content_kind`, `size_bytes`, `needs_review`,
`review_reasons`, oraz opcjonalny `text_head` (głowa tekstu z etapu extract/B2,
obcięta do `config/thresholds.yaml: llm.max_text_head_bytes`; brak klucza =
treść bez ekstrakcji albo bez tekstu). Bez wcześniejszego `just extract`
klasyfikator AI (B5) widzi wyłącznie nazwy i ścieżki plików.

Dopasowanie wykorzystuje pełne tokeny skrótu, aliasu lub nazwy w komponentach
ścieżki (również nazwie paczki/pliku), bez rozróżniania wielkości liter,
separatorów i polskich znaków — rozpoznaje m.in. `SEM3`, `sem_3`, `semestr III`.
Jawny inny semestr/grupa wyklucza dopasowanie; brak semestru, kolizja nazw,
sprzeczne pochodzenie albo rozmiary oznaczają review. **B1 nie jest
klasyfikatorem**: nie nadaje confidence, kategorii ani zgody na kopiowanie, i nie
używa fuzzy ani treści dokumentów. Wpisy bez poprawnego hasha, bez `content`,
w stanie `discovered`/`error` nie inicjują kandydatury. Semestry magisterskie
pozostają poza zakresem (D3).

### 2.2 Klasyfikacja deterministyczna (zero kosztu)

```bash
just subject-classify 3 AKO --dry-run   # rozkład decyzji, nic nie zapisuje
just subject-classify 3 AKO
# → plan.det.jsonl (decyzje) + unresolved.jsonl (to, czego reguły nie rozstrzygnęły)
```

Siła sygnału **jest** pewnością decyzji: nazwa pliku 0.95, najbliższy katalog
0.90, sama głowa tekstu 0.74. Progi siedzą w `config/thresholds.yaml`.

Kolejność rozstrzygania: treść już leżąca w paczce (ground truth,
`classifications`, `run_id='ground_truth'`) → artefakt kompilacji
(`syntax.yaml: ignore`; w źródłach to 14,2% plików) → media poza paczkę →
słowa kluczowe kategorii (`syntax.yaml: categories.*.keywords`) szukane w
nazwie pliku, w najbliższym katalogu ze ścieżki i w głowie tekstu z etapu
extract. Nazwy plików zostają oryginalne — kanoniczna nazwa z `syntax.yaml`
wymaga TEMATU, którego nie da się wyprowadzić bez zgadywania (miękkie
ostrzeżenie dla walidatora, nie błąd). Skrypt niczego nie zapisuje do bazy
(czyta ją wyłącznie po ground truth) i jest w pełni odtwarzalny: ten sam
manifest daje bajt w bajt ten sam plan.

### 2.3 Podobieństwo treści

```bash
just subject-relate 3 AKO                       # near_duplicate / older_version → relations
.venv/bin/python scripts/near_dupe.py --all     # globalnie, dla całego indeksu
```

(Globalny przebieg idzie skryptem wprost: recepta `subject-relate` wymaga
semestru i skrótu, a `--all` ich właśnie nie ma.)

Podobieństwo **nie** oznacza duplikatu: zapisujemy relację i zostawiamy oba pliki.

Trzy warstwy sygnału z etapu extract: równość `normalized_text_hash` (to samo
w innym opakowaniu, pewność 1.0), simhash w progu Hamminga (materiał z
dopiskiem/poprawką) i phash dla obrazów. Kandydatów dobiera przez pasma
bitowe (zasada szufladkowa/LSH), a nie „każdy z każdym". Gdy obie treści mają
rozpoznany, różny rok — starsza dostaje relację `older_version` wskazującą
nowszą; w przeciwnym razie zostaje symetryczne `near_duplicate`, zapisane raz.
Niczego nie kasuje i **niczego nie oznacza jako `outdated`** — to decyzja
człowieka (reguła twarda nr 10). Zapis do tabeli `relations` jest **podmianą
własnego wycinka**: kasuje wyłącznie wiersze z `detection_method` zaczynającym
się od `near_dupe:` i tylko dla par z przetwarzanego zakresu, więc ręczne
decyzje (`subject-decide`, B14) zostają.

### 2.4 Resztki do modelu (tanio, poza limitem Anthropic)

```bash
just subject-ai-resolve 3 AKO --dry-run   # ile pozycji i do jakiego backendu
just subject-ai-resolve 3 AKO --limit 10  # próbka: oceń jakość, zanim puścisz resztę
just subject-ai-resolve 3 AKO
# → plan.ai.jsonl
```

Model dostaje **wyłącznie** to, czego reguły nie rozstrzygnęły (zwykle kilka
procent). Backend wybiera `config/thresholds.yaml: llm` — domyślnie `codex_cli`,
więc klasyfikacja nie obciąża limitu koordynatora.

Zapisuje jedną linię na sha256, walidowaną wobec `prompts/plan_line.schema.json`.
Gdy obok leży `plan.det.jsonl` z 2.2, do modelu idą **dokładnie** te treści,
których w nim nie ma (`--ignore-det-plan` wyłącza tę bramkę, `--det-plan`
wskazuje inny plik). Progi `confidence` z `config/thresholds.yaml` są wiążące:
deklaracja modelu nie przepchnie pozycji obok review.

### 2.5 Jeden plan

```bash
just subject-plan 3 AKO
# → plan.jsonl (+ zapis decyzji do bazy; JSONL jest eksportem)
```

Nagłówek `_meta` planu zawiera `plan_hash` — odcisk, którym posługują się
kolejne etapy. Plan poprawia się przez **ponowne zbudowanie**, nigdy przez
edycję pliku: po ręcznej zmianie odcisk przestaje się zgadzać i bramka to wyłapie.

Łączy `plan.det.jsonl`, `plan.ai.jsonl` i `relations.jsonl`. Przy dwóch
decyzjach o tej samej treści wygrywa mocniejsza metoda (człowiek >
deterministyka > heurystyka > model), a odrzucona trafia do podsumowania.
Kolizje ścieżek rozstrzyga **katalog źródłowy** (`kol_02/Zadanie 23/main.c`),
więc komplet plików jednego rozwiązania zostaje razem; przy nierozstrzygalnej
kolizji wchodzi krótki skrót sha256 — żadna treść nie znika po cichu. Od tego
etapu **źródłem prawdy jest baza**: decyzje lądują w `classifications`,
pozycje planu w `plan_items`, a `plan.jsonl` jest ich eksportem do gita. Zapis
podmienia wycinek jednego przedmiotu i nigdy nie dotyka wierszy ground truth.

### 2.6 Bramka: czy plan wolno wykonać

```bash
just subject-validate 3 AKO
# → validation.jsonl; kod wyjścia 0 = przechodzi, 2 = PLAN ODRZUCONY, 1 = błąd
just subject-validate 3 AKO --strict     # ostrzeżenia też blokują
```

Sprawdza schemat linii, bezpieczeństwo i kolizje ścieżek, zgodność kategorii,
progi pewności, nazwy odtwarzalne na Windowsie, nadpisanie ground truth oraz
pokazuje dry-run diff drzewa.

Repo klonują studenci, więc na Windowsie są twardym błędem: znak `<>:"|?*`,
nazwa zastrzeżona (`CON`, `COM1`…), końcowa kropka/spacja i ścieżka dłuższa
niż 240 znaków. Niezgodność nazwy z konwencją (`lab_3` zamiast `lab_03`) jest
tylko **ostrzeżeniem**, bo da się ją poprawić automatycznie.

### 2.7 Przegląd okiem

```bash
just subject-review 3 AKO
# → reports/AKO/review.html — samowystarczalna strona (miniatury w środku)
```

Kolejność sekcji wynika z tego, co blokuje: ustalenia walidacji → `needs_review`
→ `unresolved` → klastry podobieństwa z diffem → media → drzewo po zmianie.
W klastrach jest to, czego nie rozstrzygnie żadna heurystyka: diff HTML
(`difflib.HtmlDiff`) dla tekstu albo dwie miniatury obok siebie dla skanów.
Strona niczego nie zatwierdza — zgoda na `apply` to osobna, jawna decyzja.

Ręczne decyzje z przeglądu zapisujesz tą samą biblioteką, której używa studio:

```bash
just subject-decide record <sha256> classify -s 3 -k AKO -c wyklad -a copy
just subject-decide record <sha256> skip -n "artefakt kompilacji"
just subject-decide list
just subject-decide undo          # cofa najnowszą decyzję
```

Decyzja ląduje w `manual_decisions` **i** w `classifications`
(`classification_method='manual'`, `confidence=1.0`) oraz w eksporcie
`reports/manual_decisions.jsonl`. Po decyzjach przebuduj plan (2.5) i ponów bramkę.

### 2.8 Wykonanie planu

To jedyny moment, w którym coś rusza materiały. Domyślnie **nic się nie kopiuje**:

```bash
just subject-apply 3 AKO                 # DRY-RUN: co by zrobił + apply_snapshot.json
```

Dopiero po obejrzeniu tego i po Twojej zgodzie:

```bash
git -C ../../10_NEW/PaczkaInfaPG switch -c subject/AKO      # gałąź przedmiotu
just subject-apply 3 AKO --yes --expect-hash 080b597c7a37…  # odcisk z planu
```

Co ten etap gwarantuje:

- bramka z 2.6 jest wykonywana **ponownie** tym samym kodem — plan odrzucony to
  kod 2 i zero kopii, niezależnie od tego, co pokazał wcześniejszy `validate`;
- `--expect-hash` przypina wykonanie do planu, który zaakceptowałeś; przebudowany
  plan jest odmową, a nie „tym samym planem”;
- plik o **innej** treści pod ścieżką docelową zatrzymuje cały przebieg (żadnych
  częściowych zapisów); plik o tej samej treści to „już jest” i powtórzony `apply`
  nic nie robi;
- brak pliku źródłowego też jest odmową — to znaczy, że indeks rozjechał się ze
  źródłami (`just sources-check`);
- **`apply` nie commituje.**

Flagi, które czasem są potrzebne: `--create-branch` (przełącz/utwórz gałąź
przedmiotu), `--allow-dirty` (powtórzenie przerwanego przebiegu), `--no-git`
(repo docelowe nie jest klonem).

### 2.9 Dowód, że się udało

```bash
just subject-verify 3 AKO
# → verification.jsonl; kod 0 = zgadza się z planem, 2 = NIE commituj
just subject-verify 3 AKO --strict    # pliki spoza planu też blokują
```

`verify` liczy sha256 **po kopii** i porównuje z planem — audyt `apply` to zapis
intencji, a nie dowód. Zielony `verify` przestawia pliki na status `verified`
i dopiero wtedy commitujesz materiały na gałęzi przedmiotu (PR i merge robisz Ty).

Zmierzone na realnym planie AKO (2519 pozycji, dry-run, 2026-09-22): 1497 do
skopiowania, 0 kolizji, 0 brakujących źródeł, 2,1 s. Dalsze skrypty B12–B13 są
nadal do implementacji.

---

## 3. Co dalej z materiałami

```bash
just status                  # przedmioty × etapy po zmianach
just synapse                 # vault dla grafu (20_WORK/synapse/vault)
just synapse-view            # vault + generator + podgląd w viewerze
```

Graf pokazuje **rodzaj** powiązania między materiałami (`belongs_to`,
`near_duplicate`, `older_version`) i pewność z etapu 2.3 — kontrakt i czytanie
grafu: `docs/SYNAPSE.md`. To osobna aplikacja użytkownika: generator .NET
+ viewer Svelte. Źródła obu są **w tym repo**, w `studio/graf/` — od commita
`ce3d933` jako kod pierwszej ręki, nie `git subtree` ani vendor: nie ma upstreamu,
do którego cokolwiek wraca, więc zmieniamy je u siebie bez oglądania się na
`Billypl/synapse`. Marker testowy nazywa się historycznie `vendor`, ale
`just vendor-check` uruchamia generator z `studio/graf/`.

---

## 4. Kody wyjścia i co po nich zrobić

| Kod | Etap | Znaczenie | Co zrobić |
|---:|---|---|---|
| `0` | wszystkie | etap przeszedł | następny krok |
| `1` | wszystkie | błąd przygotowania (brak pliku, bazy, nieznany przedmiot) | popraw wejście i powtórz |
| `2` | `subject-validate` | **plan odrzucony** | napraw przyczynę, przebuduj plan |
| `2` | `subject-apply` | odmowa: bramka, gałąź, kolizja treści, brak źródła | przeczytaj komunikat; nic nie zostało skopiowane |
| `2` | `subject-verify` | paczka **nie** zgadza się z planem | **nie commituj**; sprawdź, co podmieniło pliki |

---

## 5. Kontrole i testy

```bash
just test                    # wszystko
just test-fast               # sam kontrakt kodu (szybka pętla)
just env-check               # realne biblioteki i binarki
just cli-check               # argv wobec parserów prawdziwych CLI
just e2e                     # cały łańcuch na syntetycznej paczce
just probe                   # sondy na realnych danych (tylko odczyt)
just mutate-check            # czy testy w ogóle coś łapią (33 zapisane kontrakty)
just vendor-check            # nasz vault przez PRAWDZIWY generator (marker 'vendor' to nazwa historyczna — generator leży w studio/graf/, nie w żadnym vendor/)
```

Opis warstw i uzasadnienie każdej z nich: `docs/TESTY.md`.

---

## 6. Gdy coś nie wychodzi

- **`PLAN ODRZUCONY`** — przeczytaj `reports/{SKROT}/validation.jsonl`; najczęstsza
  przyczyna to kolizja celu (dwie treści o tej samej nazwie) albo pewność poniżej
  progu przy `action: copy`.
- **`apply` mówi o gałęzi** — repo docelowe stoi na innej niż `subject/{SKROT}`.
  To celowe: materiały jednego przedmiotu nie mieszają się z cudzą pracą.
- **`apply` zgłasza brak pliku źródłowego** — indeks pamięta plik, którego już nie
  ma. `just sources-check` pokaże skalę rozjazdu.
- **`verify` na czerwono** — pod ścieżką planu leży inna treść. Nie commituj;
  najpierw ustal, co ją podmieniło.
- **Guard blokuje komendę** — hook odmawia każdej komendzie powłoki, której *tekst*
  zawiera ścieżkę źródeł razem ze słowem mutującym (także w komunikacie commita).
  Użyj przekierowania `>` zamiast `tee`, a do edycji plików — edytora, nie powłoki.
