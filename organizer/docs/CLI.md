# Paczka Organizer z wiersza poleceń

Cała droga od stosu cudzych paczek do materiałów w repo: **jakie komendy, w jakiej
kolejności i po czym poznać, że etap się udał**. Wersja z interfejsem — te same
etapy, ale w przeglądarce — jest w `studio/README.md`.

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
zadziała (`just subject-prepare 3 AK`).

### 2.2 Klasyfikacja deterministyczna (zero kosztu)

```bash
just subject-classify 3 AKO --dry-run   # rozkład decyzji, nic nie zapisuje
just subject-classify 3 AKO
# → plan.det.jsonl (decyzje) + unresolved.jsonl (to, czego reguły nie rozstrzygnęły)
```

Siła sygnału **jest** pewnością decyzji: nazwa pliku 0.95, najbliższy katalog
0.90, sama głowa tekstu 0.74. Progi siedzą w `config/thresholds.yaml`.

### 2.3 Podobieństwo treści

```bash
just subject-relate 3 AKO                       # near_duplicate / older_version → relations
.venv/bin/python scripts/near_dupe.py --all     # globalnie, dla całego indeksu
```

(Globalny przebieg idzie skryptem wprost: recepta `subject-relate` wymaga
semestru i skrótu, a `--all` ich właśnie nie ma.)

Podobieństwo **nie** oznacza duplikatu: zapisujemy relację i zostawiamy oba pliki.

### 2.4 Resztki do modelu (tanio, poza limitem Anthropic)

```bash
just subject-ai-resolve 3 AKO --dry-run   # ile pozycji i do jakiego backendu
just subject-ai-resolve 3 AKO
# → plan.ai.jsonl
```

Model dostaje **wyłącznie** to, czego reguły nie rozstrzygnęły (zwykle kilka
procent). Backend wybiera `config/thresholds.yaml: llm` — domyślnie `codex_cli`.

### 2.5 Jeden plan

```bash
just subject-plan 3 AKO
# → plan.jsonl (+ zapis decyzji do bazy; JSONL jest eksportem)
```

Nagłówek `_meta` planu zawiera `plan_hash` — odcisk, którym posługują się
kolejne etapy. Plan poprawia się przez **ponowne zbudowanie**, nigdy przez
edycję pliku: po ręcznej zmianie odcisk przestaje się zgadzać i bramka to wyłapie.

### 2.6 Bramka: czy plan wolno wykonać

```bash
just subject-validate 3 AKO
# → validation.jsonl; kod wyjścia 0 = przechodzi, 2 = PLAN ODRZUCONY, 1 = błąd
just subject-validate 3 AKO --strict     # ostrzeżenia też blokują
```

Sprawdza schemat linii, bezpieczeństwo i kolizje ścieżek, zgodność kategorii,
progi pewności, nazwy odtwarzalne na Windowsie, nadpisanie ground truth oraz
pokazuje dry-run diff drzewa.

### 2.7 Przegląd okiem

```bash
just subject-review 3 AKO
# → reports/AKO/review.html — samowystarczalna strona (miniatury w środku)
```

Kolejność sekcji wynika z tego, co blokuje: ustalenia walidacji → `needs_review`
→ `unresolved` → klastry podobieństwa z diffem → media → drzewo po zmianie.

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

---

## 3. Co dalej z materiałami

```bash
just status                  # przedmioty × etapy po zmianach
just synapse                 # vault dla grafu (20_WORK/synapse/vault)
just synapse-view            # vault + generator + podgląd w viewerze
```

Graf pokazuje **rodzaj** powiązania między materiałami (near-duplicate, starsza
wersja, „to samo zadanie”) — kontrakt i czytanie grafu: `docs/SYNAPSE.md`.

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
```

Opis warstw i uzasadnienie każdej z nich: `README.md`, sekcja „Testy: pięć warstw”.

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
