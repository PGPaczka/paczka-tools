# Potok od zera do PR — co znaczy każdy etap i jak go przejść

Ten dokument spina trzy istniejące: `docs/CLI.md` mówi **jakie komendy wpisać**,
`studio/README.md` opisuje **widoki studia**, a `AGENTS.md` trzyma **reguły procesu**.
Tutaj jest to, czego nie ma nigdzie indziej: **co dany etap znaczy, jakiej decyzji
od Ciebie wymaga i po czym poznasz, że wyszedł.**

Czytaj po kolei przy pierwszym przedmiocie. Potem wystarczy sekcja 5.

---

## 1. Mapa

```
źródła (00_SOURCES, read-only)
   │  scan → hash → dedup folderów → extract          ← RAZ na całe źródła
   ▼
indeks 20_WORK/organizer.sqlite  ◄── scan-target (ground truth z repo paczki)
   │  prepare → classify → relate → ai-resolve        ← RAZ na przedmiot
   ▼
plan przedmiotu (reports/{SKROT}/plan.jsonl)          ← PROPOZYCJA maszyny
   │
   │  ⟨ PRZEGLĄD: Twoje decyzje → manual_decisions ⟩
   │  plan jeszcze raz  →  validate (bramka)  →  review
   ▼
   ⟨ Twoja akceptacja KONKRETNEGO planu (plan_hash) ⟩
   │  apply --yes --expect-hash … → verify
   ▼
repo paczki, gałąź subject/{SKROT}   → commit i PR robisz Ty
```

Indeks jest odtwarzalny i leży poza gitem. Plany, raporty i decyzje są tekstowe
i wersjonowane — to one są dorobkiem, nie baza.

---

## 2. Słownik — sześć pojęć, bez których reszta nie ma sensu

### Treść, nie plik

Jednostką pracy jest **treść**, adresowana przez `sha256`. Ten sam PDF leżący
w czterech paczkach to **jedna treść z czterema ścieżkami**, czyli jedna decyzja,
nie cztery. Dlatego 48 049 plików w źródłach to 19 337 treści, a plan AKO ma
2519 pozycji, a nie kilkanaście tysięcy.

Konsekwencja, która zaskakuje: zmiana nazwy w paczce to wybór, nie fakt — jedna
treść potrafi leżeć pod 81 różnymi nazwami (rekordzista w tym indeksie).

### Ground truth

Materiały **już ułożone ręcznie** w repo docelowym, wciągnięte do indeksu przez
`scan-target` z `run_id='ground_truth'`. Są chronione na każdym poziomie: decyzja
próbująca je nadpisać kończy się odmową (HTTP 409 w studiu, `GroundTruthConflict`
i kod 2 w CLI). Nigdy ich nie przepisujemy — plan może je najwyżej **pominąć**,
bo treść już jest na miejscu.

### Kategoria

Docelowy folder wewnątrz katalogu przedmiotu, zdefiniowany w `config/syntax.yaml`:
`egzamin`, `kolokwia`, `laboratoria`, `cwiczenia`, `projekt`, `seminarium`,
`wyklad`, `opracowania`, `ksiazki`, `inne` (+ `outdated`). Każda ma `folder`,
szablony ścieżek, formy zajęć, przy których w ogóle ma sens (`forms: [L]` dla
laboratoriów), słowa kluczowe i priorytet rozstrzygający remisy.

**Kategoria jest naturalną porcją pracy.** Przegląd robi się kategoriami —
laboratoria osobno od ćwiczeń — bo to są różne rodzaje materiału i różne pytania.

### `needs_review`

Flaga „maszyna nie jest pewna". Stawia ją klasyfikator, gdy sygnały są sprzeczne
(`konflikt z cwiczenia`), gdy brakuje semestru albo gdy przedmiot jest niejednoznaczny.
**To jest Twoja kolejka pracy.** W AKO takich pozycji jest 69 na 2519 — przegląd
przedmiotu to ich rozstrzygnięcie plus kontrola wyrywkowa reszty, a nie 2519 klików.

### `manual_decisions`

Tabela z **Twoimi** decyzjami. Zapis idzie przez jedną bibliotekę
(`scripts/orglib/decisions.py`), więc studio i CLI robią dokładnie to samo:
wiersz w `manual_decisions`, aktualizacja `classifications` na
`classification_method='manual'`, `confidence=1.0`, i eksport do
`reports/manual_decisions.jsonl` (w gicie — Twoja praca przeżywa przebudowę bazy).

`confidence=1.0` znaczy, że Twoja decyzja bije każdą regułę i każdy model.

### `plan_hash`

Odcisk **zawartości** planu: sha256 po kanonicznej postaci wszystkich decyzji,
posortowanych po treści. Kolejność linii w pliku go nie zmienia.

To jest mechanizm zgody: `apply` wykonuje wyłącznie plan o odcisku, który
zaakceptowałeś (`--expect-hash`). Plan przebudowany po akceptacji ma inny odcisk,
więc dostaje odmowę — **nie** jest traktowany jak „ten sam plan".

---

## 3. Plan ≠ przejrzenie

To jest najczęstsze nieporozumienie, więc osobno.

**`plan.jsonl` to propozycja maszyny. Nikt na nią jeszcze nie patrzył.** Wiersz
planu mówi:

```json
{"source_sha256": "002f6b72…", "action": "copy", "category": "laboratoria",
 "confidence": 0.9, "method": "heuristic",
 "reason": "kategoria laboratoria wg: najbliższy katalog na ścieżce",
 "target_rel": "paczka/SEM3/AKO_…/laboratoria/wspólne/lab_02/21.10.2.png"}
```

To wynik reguł z `syntax.yaml`, modelu AI i relacji podobieństwa — **zero udziału
człowieka**.

**„Przejrzane" znaczy: potwierdziłeś albo nadpisałeś tę propozycję.**

Dlatego **plan buduje się dwa razy**:

```
classify → plan (propozycja) → PRZEGLĄD → decyzje → plan (znowu) → validate → apply
                                                      ↑
                              build_plan scala teraz Twoje decyzje z resztą
```

To nie marnotrawstwo: `build_plan` to czysta operacja scalająca z bazy (sekundy),
a drugi przebieg jest **jedynym** momentem, w którym Twoje poprawki wchodzą do
`plan_hash` — czyli do tego, na co dajesz zgodę.

---

## 4. Etap po etapie

Znacznik mówi, gdzie etap ma przycisk: **[plan]** to zakładka planu przedmiotu,
**[indeks]** to zakładka statystyk. Każdy etap potoku da się dziś uruchomić z przeglądarki;
komendy zostają, bo studio woła dokładnie te same skrypty i przekazuje ich kod wyjścia.

**Jeden etap na raz, na całe studio.** Wszystkie piszą do tej samej bazy, a `scan`,
`hash` i `extract` przemielają ją w całości — więc gdy jeden trwa, pozostałe przyciski
są wyszarzone, a żądanie wysłane z pominięciem interfejsu dostaje odmowę (409) i nic
nie startuje.

### Etapy globalne — raz na całe źródła

| Etap | Co robi | Po czym poznasz | Gdzie |
|---|---|---|---|
| `just scan` | chodzi po `00_SOURCES`, zapisuje każdy plik i katalog | `reports/SOURCES_TREE.md` + liczby w `just status` | [indeks] |
| `just hash` | sha256 każdego pliku → identyczne bajty scalają się w jedną treść | spadek „pliki" → „treści" w `just status` | [indeks] |
| `just fold-hash` | `tree_hash` katalogów: identyczne poddrzewa dostają `duplicate_of` i wypadają z dalszej pracy | liczba katalogów-duplikatów | [indeks] |
| `just extract` | wyciąga tekst z PDF/docx; OCR obrazów jako osobny przełącznik (wolne: ~50 min na całości) | „treści z wyekstrahowanym tekstem" w `just status` | [indeks] |
| `just scan-target` | wciąga **ground truth** z repo paczki | kolumna „w paczce" w `reports/STATUS.md` | [indeks] |
| `just status` | przelicza `reports/STATUS.md` z indeksu | tabela przedmioty × etapy | [indeks] |

Bez `extract` nie ma sensownego `relate`: podobieństwo liczy się z podpisów treści,
a obraz bez OCR porównuje się tylko percepcyjnie — czyli dwie białe kartki wychodzą
„podobne", choć dotyczą różnych rzeczy.

### Etapy przedmiotu

**B1 · `just subject-prepare 3 AKO`** — **[plan: `wycinek`]**
Wycina z indeksu wszystko, co należy do tego przedmiotu.
→ `reports/AKO/manifest_slice.jsonl`. Nic nie zmienia w materiałach.

**B3 · `just subject-classify 3 AKO`** — **[plan: `klasyfikuj`]**
Reguły deterministyczne i heurystyki z `syntax.yaml`: kategoria, rok, ścieżka
docelowa, akcja (`copy`/`skip`/`media`/`quarantine`), pewność i **uzasadnienie**.
Zero kosztu AI.
→ `plan.det.jsonl` (rozstrzygnięte) + `unresolved.jsonl` (bez sygnału).

**B5 · `just subject-ai-resolve 3 AKO`** — **[plan: `AI na resztki`]**
Resztki z `unresolved.jsonl` idą do modelu wskazanego w `config/thresholds.yaml: llm`
— domyślnie `codex_cli`, czyli **konto OpenAI, nie limit koordynatora**. Wznawialne,
z pamięcią podręczną.
→ `plan.ai.jsonl`.

**B6 · `just subject-relate 3 AKO`** — **[plan: `podobieństwo`]**
Podobieństwo treści: simhash/minhash dla tekstu, phash dla obrazów (z kontrolą
zgodności tekstu z OCR), plus sygnał wspólnego katalogu źródłowego.
→ `relations.jsonl` + tabela `relations`. To dzięki temu plan umie powiedzieć
„ta treść już jest w paczce, pomiń".

**B7 · `just subject-plan 3 AKO`** — **[plan: `zbuduj plan`]**
Scala wszystko w **jeden** `plan.jsonl`: decyzje deterministyczne, AI, **Twoje
ręczne**, relacje i ground truth. Rozstrzyga kolizje ścieżek docelowych i liczy
`plan_hash`.
→ `plan.jsonl` z nagłówkiem `_meta`. **Ten etap uruchamiasz ponownie po każdej
partii decyzji** — inaczej Twoje poprawki nie są w planie.

**B8 · `just subject-validate 3 AKO`** — **[plan: `waliduj`]**
Bramka. Sprawdza zgodność `plan_hash` z zawartością, kolizje celów, próby
nadpisania ground truth, lint nazewnictwa.
→ `validation.jsonl`. **Kod 2 = planu NIE WOLNO wykonać.**

**B9 · `just subject-review 3 AKO`** — **[plan: `review.html`]**
Samowystarczalna strona do obejrzenia okiem (miniatury w środku).
→ `reports/AKO/review.html`.

**PRZEGLĄD — [zakładka decyzje]**
Tu pracujesz Ty. Szczegóły w sekcji 5.

**B10 · `just subject-apply 3 AKO`** — **[plan: `apply (dry-run)` / `APPLY`]**
Bez `--yes` to **dry-run**: niczego nie kopiuje, pokazuje diff wykonania.
Z `--yes --expect-hash <odcisk>` kopiuje materiały do repo docelowego na gałąź
`subject/{SKROT}`. Bramka B8 jest wykonywana **jeszcze raz** tutaj.

**B11 · `just subject-verify 3 AKO`** — **[plan: `verify`]**
Przelicza hash tego, co wylądowało, wobec planu.
→ `verification.jsonl`. **Kod 2 = nie commituj materiałów.**

**Graf — [zakładka graf → `przebuduj`]**
Graf jest **migawką**: decyzji nie widać, dopóki nie przeliczysz vaulta i `graph.json`.
Przycisk robi oba kroki. Po przebudowie **porównaj liczby z podsumowania eksportu
z liczbami generatora** — rozjazd znaczy, że vault się nie parsuje. To cicha awaria:
raz rozpadło się 1891 notatek, a każda z osobna wyglądała poprawnie.

---

## 5. Pętla pracy nad jedną kategorią

Studio: `just studio-build && just studio-graf && just studio` → `127.0.0.1:8765`.
(`just studio --check` sprawdza adres i bazę bez zajmowania portu.)

Kolejność kategorii: od najprostszej do najgęstszej w wątpliwości. Dla AKO było to
**ćwiczenia → wykład → kolokwia → opracowania → laboratoria → egzamin → inne**.

**1. Zobacz, z czym masz do czynienia.**
Zakładka **graf** → **Matrix** → komórka `przedmiot × kategoria`. Trzy paski mówią,
ile jest w paczce, ile zaplanowane, ile do przeglądu. Stąd wiesz, czy to dziesięć
minut, czy pół godziny.

**2. Ustaw zakres.**
Lista przedmiotów → przedmiot → klik w kategorię w panelu przedmiotu. Zawęża to
listę pozycji **i kolejkę decyzji**, a wybór przeżywa odświeżenie strony.

**3. Rozstrzygnij sporne.** Klawisz `d`.

| Klawisz | Znaczenie |
|---|---|
| `Enter` | akceptuj propozycję (`copy`) |
| `1`–`9` | akceptuj z inną kategorią |
| `s` / `q` / `m` / `o` | pomiń / kwarantanna / media / nieaktualne |
| `t` / `r` | zmień ścieżkę docelową / samą nazwę |
| `f` | **decyzja dla całego katalogu źródłowego** |
| `u` | cofnij |
| `?` | pełna ściąga na ekranie |

`f` jest tu najważniejszy: kilka tysięcy treści to kilkadziesiąt katalogów
źródłowych. Przed zapisem widzisz katalog, liczbę pozycji i próbkę nazw; pozycje
z ground truth są pomijane.

**Pusta kolejka nie znaczy błędu.** Kategoria bez pozycji `needs_review` (np. AKO
ćwiczenia: 81 pozycji, zero spornych) mówi to wprost. Praca nad taką kategorią to
przejrzenie listy pozycji i drzewa docelowego, nie klikanie w kolejce.

**4. Duplikaty.** Klawisz `c`.
Wskaż wersję kanoniczną; reszta dostaje `skip` albo relację `older_version`.
**Klastry nie są cięte po kategorii** — to samo kolokwium bywa i w `kolokwia`,
i w `inne`. Ten krok z natury wychodzi poza kategorię i tak ma być.

**5. Sprawdź, co wyszło.** Klawisz `p` → **zbuduj plan** → **waliduj**.
Drzewo docelowe: `+` dojdzie, `=` już jest, `·` ground truth, `!` zatrzyma apply.
Sekcja „bez miejsca w drzewie" zbiera `skip` i `quarantine`.

**6. Domknij kategorię.** **apply (dry-run)** — niczego nie kopiuje, pokazuje diff.
To jest moment, w którym kategoria jest przejrzana: propozycja maszyny + Twoje
poprawki + zielona bramka.

**7. Odśwież graf.** Zakładka graf → **przebuduj**. Matrix pokaże kategorię
przesuniętą z „do przeglądu" do „zaplanowane" — najtańsza kontrola postępu.

### Domknięcie przedmiotu

Po wszystkich kategoriach, z zakładki plan: **zbuduj plan** → **waliduj** →
**review.html** → **apply (dry-run)** → (Twoja jawna zgoda) → **APPLY** → **verify**.

**Dlaczego apply dopiero tutaj, a nie po każdej kategorii.** `build_plan`,
`validate_plan`, `apply` i `verify` przyjmują wyłącznie `--semester/--skrot` —
**nie ma filtra kategorii**. `plan_hash` liczy się z zawartości pliku, a bramka
sprawdza go wobec nagłówka, więc ręcznie odfiltrowany plan to obejście bramki,
nie jej użycie. Dry-run z kroku 6 daje to samo poczucie domknięcia bez ruszania
bramkowanej ścieżki.

---

## 6. Bramki i kody wyjścia

| Kod | Etap | Znaczenie | Co zrobić |
|---:|---|---|---|
| `0` | wszystkie | etap przeszedł | następny krok |
| `1` | wszystkie | błąd przygotowania (brak pliku, bazy, nieznany przedmiot) | popraw wejście i powtórz |
| `2` | `subject-validate` | **plan odrzucony** | napraw przyczynę, przebuduj plan |
| `2` | `subject-apply` | odmowa: bramka, gałąź, kolizja, brak źródła | przeczytaj komunikat; **nic nie zostało skopiowane** |
| `2` | `subject-verify` | paczka **nie** zgadza się z planem | **nie commituj**; ustal, co podmieniło pliki |

**Bramka `apply` w studiu jest po stronie serwera.** Wyszarzony przycisk to nie
zabezpieczenie — żądanie wysłane z pominięciem interfejsu też dostaje odmowę (409)
i **żaden podproces nie startuje**. Zgoda dotyczy konkretnego planu: żądanie musi
nieść `plan_hash`, który widziałeś.

---

## 7. Pułapki z historii — warto przeczytać przed pierwszym razem

- **Viewera buduj tylko przez `just studio-graf`** (albo `npm run build -- --base=/graf/`)
  i sprawdzaj pod `127.0.0.1:8765/graf/`. Goły `vite build` wypisuje ścieżki od
  korzenia, więc pod studiem zostaje pusty `<div id="app">` — **bez jednego błędu
  w konsoli**, a `dist/` jest w `.gitignore`, więc `git status` też milczy.
- **Po przebudowie grafu porównaj liczby eksportu z liczbami generatora.** Rozjazd
  znaczy, że vault się nie parsuje. Każda notatka z osobna wygląda wtedy poprawnie.
- **Hook `guard-sources`** odmawia każdej komendzie powłoki, której *tekst* zawiera
  ścieżkę źródeł razem ze słowem mutującym — także w komunikacie commita i w `sed`
  po `TODO.md`. Do edycji plików używaj edytora, nie powłoki.
- **`apply` mówi o gałęzi** — repo docelowe stoi na innej niż `subject/{SKROT}`.
  To celowe: materiały jednego przedmiotu nie mieszają się z cudzą pracą.
- **`--ignore-user-config` w Codeksie odcina hooki**, więc guard źródeł milknie.
  Delegacja używa `-c model_provider="openai"`.

---

## 8. Gdzie co jest

| Chcesz | Plik |
|---|---|
| reguły procesu (kanoniczne) | `AGENTS.md` |
| komendy z wiersza poleceń | `docs/CLI.md` |
| opis widoków studia | `studio/README.md` |
| taksonomia kategorii i nazewnictwo | `config/syntax.yaml` |
| progi pewności i backendy AI | `config/thresholds.yaml` |
| ścieżki poza repo | `config/paths.yaml` |
| stan przedmiotów | `reports/STATUS.md` (generowany) |
| co zostało z poprzedniej sesji | `reports/HANDOFF.md` |
