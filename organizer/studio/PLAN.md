# Studio — plan

Widok do **pracy nad paczką**: przeglądania materiałów, porównywania ich i
podejmowania decyzji bez siedzenia w konsoli i domyślania się, co gdzie ma trafić.

Stan: plan przyjęty 2026-09-19. Postęp i zadania: `TODO-studio.md`.
Zasady dla agentów w tym podprojekcie: `AGENTS.md` (kanoniczne) i `CLAUDE.md` (adapter).

## Decyzja: osobny projekt, synapse zostaje soczewką

Studio jest **osobną aplikacją w tym repo** (`organizer/studio/`), a nie rozbudową
synapse. Powody, każdy wynika z tego, czym te dwie rzeczy są:

1. **Kierunek danych.** Synapse to eksport jednokierunkowy: baza → `graph.json` →
   statyczne SPA. Narzędzie do pracy musi **pisać**. Dołożenie zapisu do synapse
   oznacza dołożenie backendu aplikacji, która celowo jest statyczna, i zrobienie
   z cudzego repo forka bez powrotu.
2. **Świeżość.** `graph.json` to snapshot. Przy pracy decyzja ma zmieniać listę
   natychmiast, a nie po kolejnym `just synapse-view`.
3. **Podgląd materiałów.** Studio musi serwować PDF-y i obrazy ze źródeł (do
   odczytu). Synapse nie ma żadnej ścieżki do plików spoza vaulta i **nie powinien
   jej dostać** — to dokładnie ten wektor, którego pilnuje guard.
4. **Upstream.** W `vendor/synapse` mamy dziś czysty, przetestowany kontrakt
   (schema v2 + test wiążący `tests/test_synapse_vendor_contract.py`). Im więcej tam
   dołożymy, tym trudniej wciągnąć zmiany z `Billypl/synapse`.
5. **Bez dublowania.** Studio wystawia `/graf` ze zbudowanym viewerem i mówi mu,
   który węzeł zaznaczyć; klik w węźle wraca deep-linkiem do studia. Wspólny
   identyfikator już istnieje — `id` notatki w vaulcie to nasz stabilny identyfikator
   treści.

Odrzucona alternatywa: **rozbudowa `review.html` bez backendu**. Najtańsza (jedna
sesja), działa offline, ale decyzje trzeba zbierać w przeglądarce i importować
osobno, nie ma podglądu PDF ani pracy przekrojowej po przedmiotach. To pół
narzędzia — sensowne wyłącznie jako plan awaryjny, gdyby faza 0 pokazała, że
backend się nie broni.

## Czego nie budujemy od zera

Baza (`20_WORK/organizer.sqlite`, schema v2) ma już wszystko, na czym taki UI stoi:

| Tabela | Co z niej bierze studio |
|---|---|
| `files`, `content` | ścieżki źródłowe, rozmiary, daty, `sha256`, podpisy, rodzaj treści |
| `classifications` | decyzja: semestr, przedmiot, kategoria, ścieżka docelowa, `action`, `reason`, `confidence`, `needs_review` |
| `relations` | `near_duplicate` / `older_version` / `related` z pewnością i metodą |
| `manual_decisions` | decyzje człowieka (tabela gotowa, CLI to B14) |
| `plan_items`, `applied` | plan i audyt wykonania |

Na dysku są już miniatury (`20_WORK/thumbnails`) i wyekstrahowany tekst
(`20_WORK/extracted_text`). `scripts/orglib/review.py` (B9) układa to, co wymaga
oka: ustalenia walidacji → `needs_review` → `unresolved` → klastry near-dupe → media.
**PyMuPDF jest w zależnościach**, więc podgląd strony PDF renderuje backend — bez pdf.js.

Brakuje jednego: **ścieżki zapisu decyzji**. To jest cały sens studia.

## Architektura

- **Backend:** FastAPI + uvicorn, nasłuch **wyłącznie na `127.0.0.1`**, importuje
  `orglib` — UI nigdy nie liczy sam, reguły zostają w jednym miejscu. Długie etapy
  (extract, classify, build_plan, apply) uruchamiane jako **podproces istniejącego
  CLI** ze streamem logów, nie przepisane.
- **Frontend:** Svelte + Vite — ten sam stos co `synapse-viewer`, więc wiedza
  i komponenty się przenoszą.
- **Podgląd:** jeden endpoint tylko do odczytu, przez wspólny helper z containmentem
  ścieżek, wyłącznie po plikach obecnych w indeksie. Zero zapisu do źródeł, zero
  listowania poza indeksem.
- **Nowe zależności:** `fastapi`, `uvicorn` w `setup/requirements.txt`.
- **Recepty:** `just studio` (serwer + zbudowany frontend), `just studio-dev`
  (uvicorn --reload + vite z proxy).

## Funkcje

### Rdzeń — to, dla czego to powstaje

**Kolejka decyzji.** Jedna pozycja na ekranie: podgląd po lewej, propozycja po
prawej (kategoria, ścieżka docelowa, powód, pewność) plus alternatywy. Klawiatura:
`Enter` akceptuj, `1..9` kategoria, `t` zmień ścieżkę, `s` pomiń, `o` outdated,
`u` cofnij, `?` skąd ta propozycja. Pozycje biorą się z `needs_review`,
`unresolved`, niskiej pewności i kolizji z walidacji (B8).

Najważniejsze w tym widoku jest **działanie hurtem po katalogu źródłowym**:
2 570 treści AKO to nie 2 570 decyzji, tylko kilkadziesiąt katalogów. Po decyzji
studio proponuje to samo dla rodzeństwa i pokazuje, czego dotknie, zanim zapisze.

**Porównywarka klastrów.** Klaster jako siatka kart (miniatura, rozmiar, data,
ścieżka źródłowa); wskazujesz wersję kanoniczną, reszta dostaje `skip` albo
`older_version`. Diff tekstu i dwie miniatury obok siebie już umie `review.py`.
Filtr szumu (np. `*.vcxproj.xml`) — bez niego największy klaster w paczce to 81
plików projektowych Visual Studio.

**Drzewo docelowe.** Po lewej `paczka/SEM3/AKO_.../` w kształcie, jaki będzie po
`apply`; po prawej to, co nie ma jeszcze miejsca. „Przenieś tu” zapisuje decyzję
ręczną (`manual_decisions`, `confidence = 1.0`). To jest bezpośrednia odpowiedź na
„nie chcę się domyślać, co gdzie powinno być”.

### Wokół rdzenia

- **Pulpit:** 98 przedmiotów × etapy, kolejka „co następne”, postęp — te same liczby
  co `just status`, liczone tym samym kodem.
- **Wyszukiwanie przekrojowe** po nazwie, treści, rozszerzeniu, roku, rozmiarze,
  statusie; zapisywane widoki („skany bez OCR”, „>50 MB”, „bez przedmiotu”).
- **Bramka planu:** diff planu (co dojdzie, co się nadpisze, co pominięte) i wynik
  `validate_plan`; kod wyjścia 2 = przycisk `apply` jest martwy, nie „ostrzegawczy”.
- **Historia i cofanie** ręcznych decyzji, z eksportem do JSONL dla gita.
- **Graf jako soczewka:** `/graf` z viewerem synapse, w obie strony po identyfikatorze.

### Czego świadomie nie robimy

- edycji materiałów w UI — jedyna droga do repo paczki to plan → akceptacja → apply;
- przepisywania reguł klasyfikacji do JS;
- logowania, kont i pracy wielu osób — to jest `localhost`, jeden człowiek;
- odtwarzacza nagrań, edytora plików, konwersji formatów.

## Fazy

Każda kończy się czymś, co da się użyć.

| Faza | Zakres | Dowód, że działa |
|---|---|---|
| **S0. Szkielet** | FastAPI + SPA, pulpit przedmiotów, wszystko tylko do odczytu | te same liczby co `just status`; test kontraktu API ↔ orglib |
| **S1. Kolejka decyzji** | najpierw **B14** jako CLI, studio używa tej samej funkcji; podgląd, klawiatura, hurt po katalogu | pierwsza setka decyzji AKO podjęta szybciej niż w konsoli |
| **S2. Porównywarka** | klastry, wersja kanoniczna, filtr szumu | 119 klastrów przerobionych |
| **S3. Plan i apply** | wymaga **B10/B11**; diff planu, bramka, verify | pilotaż AKO (D1) domknięty z UI |
| **S4. Reszta** | graf jako soczewka, historia, zapisane widoki | — |

Studio nie wyprzedza potoku: S1 to B14, S3 to B10/B11 — pozycje, które i tak są
w `TODO.md`. Zabiera z nich konsolę, nie dokłada nowego świata.

## Ryzyka i świadome decyzje

- **Rozrost zakresu.** To jest cała aplikacja. Dlatego S0 jest osobnym, małym
  krokiem: jeśli po nim okaże się, że to nie tędy, tracimy jedną sesję, nie cztery.
- **Baza używana jednocześnie przez CLI i studio.** WAL, jawne sprawdzenie
  `schema_version` przy starcie i czytelny komunikat, gdy zapis trzyma inny proces —
  zamiast bicia się o blokadę.
- **Pokusa policzenia czegoś w JS**, „bo szybciej”. Pierwszy raz, gdy to się stanie,
  mamy dwie klasyfikacje dające różne wyniki. Reguła jest w `AGENTS.md` tego katalogu.
- **Podgląd jako boczna ścieżka do źródeł.** Endpoint podglądu jest read-only,
  ograniczony do plików z indeksu i przepuszczony przez ten sam helper containmentu,
  co reszta potoku. Guard zostaje ostatnią barierą, nie jedyną.
