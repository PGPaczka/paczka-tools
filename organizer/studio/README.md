# Paczka Studio — ten sam proces, tylko w przeglądarce

Lokalny warsztat nad paczką: przeglądanie materiałów, porównywanie ich i
podejmowanie decyzji bez siedzenia w konsoli. Studio **nie jest drugim potokiem** —
woła ten sam kod co komendy z `docs/CLI.md` i pisze do tej samej bazy. Zabiera
konsolę, nie dokłada nowego świata.

- plan i uzasadnienia decyzji: `PLAN.md`
- stan prac (tam odhaczaj): `TODO-studio.md`
- zasady dla agentów w tym zakresie: `AGENTS.md`, `CLAUDE.md`
- wersja konsolowa tego samego procesu: `../docs/CLI.md`

---

## Start

```bash
just studio-build     # front do postaci, którą serwuje `just studio` (raz po zmianach)
just studio           # http://127.0.0.1:8765
```

Praca nad samym widokiem (przeładowanie backendu + Vite z proxy na `/api`):

```bash
just studio-dev                  # backend 8765, front 5173
just studio-dev 8799 5199        # inne porty
```

Zanim zajmiesz port — preflight (sprawdza adres i bazę, niczego nie uruchamia):

```bash
just studio --check
```

Bez prawdziwych materiałów (syntetyczna baza demo, ~700 plików, ~20 przedmiotów):

```bash
just studio-seed
```

**Serwer stoi wyłącznie na pętli zwrotnej.** Adres spoza `127.0.0.0/8`/`::1`
to odmowa startu z kodem 2, nie ostrzeżenie — `just studio --host 0.0.0.0` nie
wystartuje. Na tym założeniu stoi decyzja, że studio nie ma kont, autoryzacji ani
CORS-a: to narzędzie jednego człowieka na jego maszynie.

---

## Co jest na ekranie

Trzy kolumny: **kolejka** (etapy pracy), **lista przedmiotów** i **panel**, który
zmienia się wraz z wybraną zakładką.

| Zakładka | Do czego służy | Klawisz |
|---|---|---|
| *(pulpit)* | przedmiot: liczniki, kategorie, rozkład pewności, pozycje planu | `b` (powrót) |
| **decyzje** | kolejka „jedna pozycja na ekranie”: podgląd + propozycja + decyzja | `d` |
| **klastry** | grupy near-duplicate, wybór wersji kanonicznej | `c` |
| **historia** | co zmieniłeś dziś, cofanie pojedynczej decyzji | `h` |
| **statystyki** | odpowiednik `reports/STATUS.md` na żywo, bez generowania pliku | — |

Nawigacja po liście przedmiotów: `/` szuka, `j`/`k` (albo strzałki) przewija,
`Enter` otwiera pierwszy wynik, `Esc` czyści filtry.

### Kolejka decyzji

Po lewej **podgląd dokumentu** — renderowana strona PDF (`←`/`→` przewraca
strony), miniatura obrazu albo głowa tekstu z etapu extract. Po prawej propozycja
potoku: kategoria, akcja, pewność, ścieżka docelowa i **powód**, dla którego
reguły tak zdecydowały.

| Klawisz | Decyzja |
|---|---|
| `Enter` | akceptuj propozycję (`copy`) |
| `1`–`9` | akceptuj z wybraną kategorią |
| `s` | pomiń (`skip`) |
| `q` | kwarantanna |
| `m` | media (poza paczkę) |
| `o` | oznacz jako nieaktualne (`outdated`) |
| `u` | cofnij ostatnią decyzję |
| `?` | pomoc |

Decyzja idzie przez tę samą funkcję co `just subject-decide` (`orglib/decisions.py`):
ląduje w `manual_decisions`, w `classifications` (`classification_method='manual'`,
`confidence=1.0`) i w eksporcie `reports/manual_decisions.jsonl`. Wiersze
`run_id='ground_truth'` są chronione — próba nadpisania ręcznie ułożonego
materiału kończy się odmową (HTTP 409), nie zapisem.

Jest też **decyzja hurtem po katalogu źródłowym**: 2 570 treści to nie 2 570
decyzji, tylko kilkadziesiąt katalogów. Przed zapisem widzisz, czego dotknie.

### Klastry

Relacje podobieństwa sklejone w grupy (union-find z `orglib/review.py` — bez
drugiej implementacji). Wskazujesz wersję kanoniczną, reszta dostaje `skip`
albo relację `older_version`. Diff tekstu pokazuje, czym te wersje się różnią.
Filtr szumu (`*.vcxproj*`, `*.sln`, `__pycache__`…) jest w
`config/thresholds.yaml: near_duplicate.noise_patterns` — bez niego największy
klaster w paczce to pliki projektowe Visual Studio.

---

## Czego studio NIE robi

- **nie liczy niczego, czego nie policzył `orglib`** — kategorie, progi, klastry,
  kubełki pewności przychodzą gotowe z API. Pierwsza reguła policzona w JS
  oznacza dwie klasyfikacje dające różne wyniki;
- **nie edytuje materiałów** — jedyna droga do repo paczki to plan → akceptacja →
  `apply`;
- **nie kasuje** niczego w bazie: rozstrzygnięcia dopisują decyzje i relacje;
- nie ma logowania, kont ani pracy wielu osób.

Podgląd sięga po materiały **tylko do odczytu**, wyłącznie po pliki obecne
w indeksie i przez wspólny helper containmentu (`config.resolve_within`): wpis
prowadzący poza swoje drzewo — bezwzględny, przez `..` albo przez dowiązanie —
nie jest czytany. Guard źródeł zostaje ostatnią barierą, nie jedyną.

---

## API (`http://127.0.0.1:8765`)

Odczyt:

| Endpoint | Zwraca |
|---|---|
| `GET /api/health` | czy backend widzi bazę i jej `schema_version` |
| `GET /api/subjects` | pulpit: liczniki, przedmioty × etapy, kolejka „co następne” |
| `GET /api/subjects/{sem}/{skrot}` | jeden przedmiot (409 przy wieloznacznym skrócie) |
| `GET /api/items` | treści po filtrach: status, kategoria, pewność, `needs_review` |
| `GET /api/items/{sha256}` | jedna treść: decyzja, kopie, relacje, plan, ślad `apply` |
| `GET /api/preview/{sha256}` | co da się pokazać: głowa tekstu, rodzaj podglądu, liczba stron |
| `GET /api/preview/{sha256}/image` | strona PDF jako PNG albo miniatura obrazu |
| `GET /api/queue` | kolejka decyzji |
| `GET /api/clusters`, `/api/clusters/diff` | klastry i diff pary |
| `GET /api/search` | wyszukiwanie przekrojowe |
| `GET /api/stats` | liczby jak w `STATUS.md`, liczone `status_report.collect` |
| `GET /api/decisions/history` | historia ręcznych decyzji |

Zapis (wyłącznie decyzje — nigdy materiały):

| Endpoint | Działanie |
|---|---|
| `POST /api/decisions` | jedna decyzja |
| `POST /api/decisions/batch` | partia (atomowo) |
| `POST /api/decisions/by-folder` | decyzja hurtem po katalogu źródłowym |
| `POST /api/decisions/undo` | cofnięcie ostatniej |
| `DELETE /api/decisions/{sha256}` | cofnięcie jednej pozycji |
| `POST /api/clusters/resolve` | rozstrzygnięcie klastra |

---

## Baza współdzielona z CLI

Studio i komendy z `docs/CLI.md` piszą do tego samego `20_WORK/organizer.sqlite`
(WAL). Przy starcie backend sprawdza `schema_version` i odmawia startu, gdy baza
jest z innej wersji schematu — po migracji część zapytań odpowiadałaby, a reszta
milczała, co jest najgorszym rodzajem pomyłki w narzędziu, na którym opiera się
decyzja o `apply`.

Można spokojnie trzymać studio otwarte i równolegle uruchamiać etapy z konsoli;
`odśwież` w nagłówku przelicza liczby z bazy.

---

## Testy

```bash
just test-fast                       # w tym kontrakt API ↔ orglib
just cli-check                       # launcher studia + prawdziwy start serwera
npm --prefix studio/web run test     # vitest
npm --prefix studio/web run check    # svelte-check
```

Dwie kontrole, które nie mogą zniknąć wraz z refaktorem, mają własne mutacje
(`just mutate-check`): odmowa startu na adresie spoza loopbacka
(`tests/mutations/studio-loopback-only.yaml`) i containment ścieżek podglądu
(`tests/mutations/studio-preview-containment.yaml`).

Widoki sprawdzaj **oczami na realnych danych** — przy 4 189 węzłach grafu cztery
realne wady wyszły dopiero w przeglądarce, nie w kodzie ani w testach.

---

## Stan

Zrobione: **S0** (szkielet, tylko odczyt), **S1** (kolejka decyzji z podglądem),
**S2** (porównywarka klastrów), **S4.2–S4.4** (historia, wyszukiwanie, statystyki).

Zostaje: **S3** — drzewo docelowe, diff planu, bramka i uruchamianie etapów z UI
(odblokowane przez B10/B11) — oraz **S4.1**, czyli graf jako soczewka. Szczegóły
i kolejność: `TODO-studio.md`.
