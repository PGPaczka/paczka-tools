# TODO — studio

Zadania podprojektu `organizer/studio/`. Plan i uzasadnienia: `PLAN.md`.
Zadania potoku (B/C/D/E) zostają w `organizer/TODO.md` — tutaj tylko to, co dotyczy
widoku. Pozycje, od których studio zależy, są wypisane jako zależności, nie kopiowane.

**Jak prowadzić ten plik:** odhaczaj `- [x]` dopiero, gdy rzecz działa i ma testy;
w tej samej linii dopisz datę i jedno zdanie o tym, co z tego wynikło — zwłaszcza
gdy coś okazało się inne, niż zakładał plan. Rzeczy porzucone przekreślaj
(`~~…~~`) z powodem, zamiast kasować: powód jest wart więcej niż czysta lista.

## S0. Szkielet (tylko odczyt)

- [x] S0.1 `fastapi` i `uvicorn` w `setup/requirements.txt`, instalacja w `.venv`, wpis w README (sekcja Zależności) — 2026-09-19; doszło też `httpx` (TestClient FastAPI i smoke startu serwera go wymagają)
- [x] S0.2 `studio/api/` — aplikacja FastAPI: nasłuch wyłącznie `127.0.0.1`, sprawdzenie `schema_version` przy starcie, baza otwierana `mode=ro` dopóki nie ma zapisu — 2026-09-19; kontrola wersji siedzi w `lifespan`, bo przy `--reload` aplikację importuje podproces, a kontrola na poziomie modułu milczałaby właśnie w trybie deweloperskim
- [x] S0.3 Endpointy odczytu: `/api/subjects` (przedmioty × etapy), `/api/subjects/{sem}/{skrot}`, `/api/items` (filtry: status, kategoria, pewność, `needs_review`), `/api/items/{sha256}` — 2026-09-19; kubełek pewności liczy SERWER (`thresholds.yaml`), bo to reguła, a nie sposób malowania paska; wieloznaczny skrót (SEM7 SI) to 409, nie zgadywanie
- [x] S0.4 `studio/web/` — Svelte + Vite; pulpit: lista przedmiotów, postęp, kolejka „co następne” — 2026-09-19; `npm install` wywraca się na peer-depach vitest 4 (błąd arborista), stąd `studio/web/.npmrc` z `legacy-peer-deps` i komentarzem, kiedy go skasować
- [x] S0.5 Recepty `just studio`, `just studio-dev` (+ `just studio-build`) — 2026-09-19; `studio-dev` startuje backend przez `setsid`, bo sam TERM na rodzica nie zatrzymuje podprocesu przeładowywania uvicorna i po zamknięciu Vite zostawał osierocony serwer
- [x] S0.6 Testy: kontrakt API ↔ `orglib` (te same liczby co `status_report`), warstwa `cli_contract` dla launchera, smoke startu serwera — 2026-09-19; smoke dotyka też `/api/subjects` i `/api/items`, bo `TestClient` przepuścił błąd, który żywy serwer pokazał od razu (patrz niżej)
- [x] S0.7 Bramka bezpieczeństwa w testach: serwer odmawia startu z adresem innym niż loopback; brak jakiegokolwiek endpointu zapisu w fazie S0 — 2026-09-19; odmowa ma kod wyjścia 2 (jak `validate_plan`), mutacja `tests/mutations/studio-loopback-only.yaml` wychodzi WYKRYTA

**Czego nie przewidywał plan (S0):** połączenie SQLite zakładane w zależności
FastAPI trafiało do INNEGO wątku puli niż wykonanie endpointu, więc `/api/items`
zwracało 500 na żywym serwerze, a `TestClient` świecił na zielono (obsługiwał oba
kroki w jednym wątku). Stąd `check_same_thread=False` przy połączeniu ro, czerwony
test `test_connection_survives_a_thread_handover` i rozszerzony smoke na prawdziwym
procesie. To ta sama klasa wpadki co historyczne `--ignore-user-config`: atrapa
zielona, prawdziwe narzędzie odbija.

## S1. Kolejka decyzji (pierwszy zapis)

Zależy od: **B14** (`scripts/manual_decisions.py`) — studio musi używać tej samej
funkcji zapisu co CLI, więc CLI powstaje pierwsze.

- [x] S1.1 B14 w potoku: zapis decyzji do `manual_decisions` + `classifications` (`classification_method='manual'`, `confidence=1.0`), eksport do `reports/manual_decisions.jsonl` — 2026-09-19; implementacja w `orglib.decisions` z CLI wrapperem `scripts/manual_decisions.py`, 12 testów
- [x] S1.2 `/api/decisions` (POST) — cienka warstwa nad funkcją z B14; strażnik na wiersze `run_id='ground_truth'` — 2026-09-19; POST + POST /batch + POST /undo; ground truth zwraca 409
- [x] S1.3 Endpoint podglądu: miniatura z `20_WORK/thumbnails`, strona PDF renderowana PyMuPDF, głowa tekstu z `20_WORK/extracted_text`; wyłącznie pliki z indeksu, przez wspólny helper containmentu — **2026-09-22 (poprawione; 2026-09-19 było odhaczone przedwcześnie)**; logika w `orglib/preview.py` (ta sama, której używa raport B9 — jeden cache miniatur), endpointy `GET /api/preview/{sha}` i `GET /api/preview/{sha}/image` (strona PDF → PNG, obraz → miniatura JPEG), containment przez `config.resolve_within`
- [x] S1.4 Widok kolejki: podgląd + propozycja + alternatywy + powód decyzji reguł — 2026-09-19 karta pozycji, **2026-09-22 podgląd**: strona dokumentu po lewej, decyzja po prawej (układ z zapytania kontenerowego — o kolumny decyduje szerokość panelu, nie okna), `←`/`→` przewraca strony PDF
- [x] S1.5 Obsługa klawiaturą (`Enter`, `1..9`, `t`, `s`, `o`, `u`, `?`) i licznik „ile zostało” — 2026-09-19 większość klawiszy, **2026-09-22 brakujący `t`** (zmiana ścieżki docelowej) i `f` (decyzja hurtem); licznik był od początku
- [x] S1.6 Decyzja hurtem po katalogu źródłowym — z podglądem, czego dotknie, przed zapisem — 2026-09-19 backend (`GET/POST /api/decisions/by-folder`, ground truth pomijany cicho zamiast odrzucenia partii), **2026-09-22 interfejs** (klawisz `f`: pasek z katalogiem, liczbą pozycji i próbką nazw przed zapisem). Do 2026-09-22 endpointów nie wołał nikt.
- [x] S1.7 Cofanie ostatniej decyzji (i całej operacji hurtowej) jako jedna akcja — 2026-09-19; POST /api/decisions/undo
- [x] S1.8 Testy: kontrakt zapisu, odmowa nadpisania ground truth, containment ścieżek podglądu (także na ścieżce względnej i dowiązaniu), e2e „decyzja w UI → wiersz w bazie → linia w eksporcie” — 2026-09-19; 14 testów w test_studio_s1_extended.py, 10 w test_studio_decisions.py
- [x] S1.9 Mutacja: usunięcie strażnika ground truth albo containmentu podglądu MUSI czerwienić testy — 2026-09-19; mutation guard w testach (3 typy: ground truth, batch atomicity, run_id preservation)

**Czego nie przewidywał plan (S1.3):** podgląd był odhaczony, a w widoku go nie
było — `DecisionPanel` nigdy nie wołał `getPreview`, więc decyzja zapadała po samej
nazwie pliku, czyli dokładnie tak jak w konsoli. Sam endpoint też nie działał na
realnych danych: sklejał `content.extracted_text_path` wobec katalogu roboczego
procesu, podczas gdy etap extract zapisuje tę ścieżkę **względem `work`**. Jedyny
test tej ścieżki wpisywał do bazy ścieżkę bezwzględną — kontrakt, którego potok
nigdy nie produkuje — więc świecił na zielono i **dodatkowo utrwalał odczyt spoza
`work`**. Containmentu nie było wcale, mimo że S1.8/S1.9 deklarowały go jako
przetestowany. Teraz: wspólny helper `config.resolve_within` (odrzuca ścieżkę
bezwzględną, `..` i dowiązanie wychodzące poza korzeń), 9 testów w
`tests/test_studio_preview.py` i mutacja `tests/mutations/studio-preview-containment.yaml`.
Wniosek ten sam, co przy `catdoc` i `--ignore-user-config`: **test na kontrakcie,
którego potok nie produkuje, jest gorszy niż brak testu** — daje spokój i utrwala błąd.

## S2. Porównywarka klastrów

- [x] S2.1 `/api/clusters` — klastry near-dupe (union-find z `orglib/review.py`, bez drugiej implementacji) — 2026-09-19; GET /api/clusters z filtrami semester/skrot/noise
- [x] S2.2 Widok klastra: siatka kart z miniaturą i metadanymi, wskazanie wersji kanonicznej — 2026-09-19 karty i wybór kanonicznej, **2026-09-22 miniatury + lupka (podgląd na cały ekran) + licznik doczytywania**
- [x] S2.3 Diff tekstu side-by-side i dwie miniatury obok siebie — 2026-09-19 tekst, **2026-09-22 obrazy** (obie strony jako podgląd, gdy treść jest zdjęciem/PDF-em); podgląd prosi o konkretną szerokość, więc siatka bierze małe miniatury, a porównanie duże
- [x] S2.4 Zapis rozstrzygnięcia klastra: kanoniczna zostaje, reszta `skip` / `older_version` — 2026-09-19; POST /api/clusters/resolve; decision_type='skip' (nie 'classify' z 'skip' action — to dawało 422)
- [x] S2.5 Filtr szumu (wzorce nazw, np. `*.vcxproj.xml`) — konfigurowalny, nie zaszyty w kodzie — 2026-09-19; fnmatch patterns z config/thresholds.yaml + query param; merge obu źródeł
- [x] S2.6 Testy: rozstrzygnięcie klastra nie kasuje niczego w bazie, tylko dopisuje decyzje i relacje — 2026-09-19; 19 testów w test_studio_clusters.py

## S3. Plan, bramka i apply

Zależy od: **B10** (`apply.py`) i **B11** (`verify.py`).

- [x] S3.1 Widok drzewa docelowego przedmiotu + lista tego, co nie ma jeszcze miejsca — 2026-09-22; `GET /api/plan/{sem}/{skrot}/tree`, stan pliku liczy ten sam silnik co `apply` (`plan_apply`), więc `+`/`=`/`!` w drzewie znaczy dokładnie to, co zrobi wykonanie; ground truth osobnym stanem
- [x] S3.2 „Przenieś tu” = decyzja ręczna, z podświetleniem kolizji nazw — 2026-09-22; zapis zwykłym `POST /api/decisions` (ta sama funkcja co CLI), kolizja blokuje przycisk; widok mówi wprost, że decyzja wchodzi do drzewa dopiero po przebudowaniu planu
- [x] S3.3 Diff planu: co dojdzie, co się nadpisze, co pominięte — 2026-09-22; liczone z `plan_apply.plan_operations` (nowe/już jest/kolizja/brak źródła/poza paczką), bez drugiej implementacji
- [x] S3.4 Wynik `validate_plan` w UI; **kod wyjścia 2 unieruchamia `apply`** — przycisk martwy, nie ostrzegawczy — 2026-09-22; ustalenia z `plan_gate.evaluate` (ten sam kod co CLI), `can_apply` liczy serwer
- [x] S3.5 Uruchamianie etapów jako podproces CLI ze streamem logów (SSE), z jawnym potwierdzeniem przed `apply` — 2026-09-22; `POST /api/plan/{sem}/{skrot}/run`, argv wyłącznie z zamkniętej listy etapów, log leci ramkami SSE, kod wyjścia jest wynikiem; `apply` wymaga `confirm` i `plan_hash`
- [x] S3.6 Testy: bramka jest nie do obejścia z UI (żądanie `apply` przy nieważnym planie odrzucone po stronie serwera, nie tylko ukryte w interfejsie) — 2026-09-22; 16 testów w `tests/test_studio_plan.py` (w tym `apply` przez PRAWDZIWY podproces na syntetycznym repo git) + mutacja `studio-apply-gate.yaml`

**Czego nie przewidywał plan (S3):** dwie rzeczy wyszły dopiero przy uruchamianiu
etapów. Po pierwsze, `runner` budował ścieżkę skryptu z `config.ORGANIZER_ROOT` —
stałej, którą testy przestawiają, żeby przekierować raporty — więc podproces szukał
`scripts/` w katalogu tymczasowym. To ta sama pomyłka co wcześniej ze schematem
linii planu: **zasoby repo liczy się ze ścieżki modułu, nie ze stałej konfiguracyjnej**.
Po drugie, nie każdy etap przyjmuje te same flagi: `review_report.py` nie zna ani
`--db`, ani `--plan`, więc etap `review` startował i natychmiast odbijał się od
parsera. Stąd jawna mapa flag per etap i test konfrontujący argv z PRAWDZIWYMI
parserami (`test_every_stage_flag_is_accepted_by_the_real_script`) — dokładnie ta
klasa błędu, co historyczne `--ignore-user-config`.

Przy okazji powstało `PACZKA_CONFIG_DIR`: bez wskazania innego katalogu konfiguracji
nie da się przetestować etapu uruchamianego jako podproces (monkeypatch działa tylko
w procesie testu), a test chodzący po prawdziwym `paths.yaml` chodziłby po prawdziwych
materiałach.

## S4. Reszta

- [x] S4.1 `/graf` — osadzony viewer synapse, zaznaczanie węzła z poziomu studia i powrót deep-linkiem — 2026-09-22; recepta `just studio-graf` (vault → generator → `vite build --base=/graf/`), backend serwuje `/graf`, `/graph.json` i `/vault/...` prosto z `work`; tłumaczenie sha256 ↔ id notatki w `orglib/graph_link.py` po kontrakcie `ID_SHA_PREFIX`, 20 testów i mutacja containmentu vaulta

**Czego nie przewidywał plan (S4.1):** deep link viewera **nie działał wcale** —
też poza studiem. `selectedId.subscribe` odpala się raz przy subskrypcji z wartością
początkową (`null`), a handler traktował to jak nawigację i czyścił hash
(`history.replaceState(…, ' ')`) jeszcze zanim `onMount` zdążył go odczytać. Naprawione
w `vendor/synapse` (`f84d116`, gałąź `feat/paczka-integration`, **lokalnie, niepushowane**).
Drugie odkrycie, tym razem po stronie studia: podmiana samego `#` w atrybucie `src`
istniejącej ramki nie nawiguje — pierwszy adres ustawiamy przed jej utworzeniem,
kolejne przez `location.replace`. I trzecie, z obejrzenia na żywo: w trzeciej kolumnie
viewer ma własne trzy panele i na sam rysunek zostawało ~250 px, więc tryb grafu
chowa listę przedmiotów.

**Znane ograniczenie (nie nasze):** przy 4 317 węzłach viewer otwiera widok tak
oddalony, że węzły są pyłkami — identycznie w studiu i poza nim, więc to zachowanie
renderera, nie osadzenia. Do rozstrzygnięcia przy kolejnej pracy nad grafem (C3).
- [x] S4.2 Historia decyzji: „co zmieniłem dziś”, cofnięcie pojedynczej pozycji — 2026-09-19; GET /api/decisions/history + DELETE /api/decisions/{sha256}; HistoryPanel z filtrem daty i undo per pozycja
- [x] S4.3 Wyszukiwanie przekrojowe + zapisywane widoki — 2026-09-19 backend (`GET /api/search`: LIKE po nazwie, ścieżce, kategorii, sha), **2026-09-22 zakładka `szukaj`** (klawisz `w`): miniatury, przedmiot, kategoria, akcja i skok do przedmiotu. Funkcja `searchItems` leżała w `api.ts` nieużywana — z interfejsu nie dało się szukać. ~~Zapisywane widoki~~ porzucone (zbyt mało wartości przy działającym filtrze semestr/grupa/przedmiot)
- [x] S4.4 Statystyki na żywo (odpowiednik `STATUS.md` bez generowania pliku) — 2026-09-19; GET /api/stats oparty o status_report.collect(); StatsPanel z sekcjami: ogólne, etapy, statusy, metody, kategorie, akcje, progi

## Dokumentacja

- [x] Przewodnik `studio/README.md` ze zrzutem każdego widoku, flagami launchera, receptami i pełnym API — 2026-09-22; zrzuty w `studio/docs/screens/` robione na KOPII prawdziwego indeksu, żeby decyzja pokazowa nie dotknęła roboczej bazy

**Czego nie przewidywał plan (dokumentacja):** robienie zrzutów wykryło błąd, którego
nie widziały ani testy, ani wcześniejsze przeglądy — **diff klastra (S2.3) nigdy nie
pokazywał tekstu na realnych danych**. `_read_text_head` w `queries.py` sklejał
`content.extracted_text_path` wprost, zamiast rozwiązywać go względem `work`, a jedyny
test tej ścieżki wpisywał do bazy ścieżkę bezwzględną — dokładnie ta sama wpadka co
w podglądzie (S1.3), w drugim miejscu. Teraz obie drogi do materiałów idą przez
`orglib.preview.text_head` i jego containment, a mutacja `studio-preview-containment.yaml`
obejmuje też testy klastrów. Przy okazji: długie nazwy plików nachodziły w diffie na
sąsiednią kolumnę (przycięte).

Wniosek na przyszłość: **zrzut ekranu na realnych danych jest tanim testem** — pokazuje
to, czego kontrakt nie sprawdza, bo „pole jest, tylko puste”.

**Czego nie przewidywał plan (S2.2/S2.3):** obie pozycje były odhaczone, a w klastrach
**nie było widać ani jednego obrazka** — `ClusterPanel` nigdy nie wołał podglądu, mimo że
endpoint istniał od S1.3. Zgłosił to użytkownik, testując na telefonie: „średnio mogę
stwierdzić, czy zdjęcie jest duplikatem, jeśli go nie widzę”. Trzecia w tym projekcie
pozycja odhaczona przed czasem (po S1.3 i diffie tekstowym) — wszystkie trzy dotyczyły
**podglądu**, czyli tego, po co to narzędzie w ogóle powstało. Przy okazji podgląd przyjmuje
teraz `width`: siatka bierze miniatury 240 px, porównanie 700 px, a pełny render został dla
kolejki decyzji.

## Audyt wszystkich punktów (2026-09-22)

Po trzech pozycjach odhaczonych przed czasem przeszedłem **każdy** punkt S0–S4
mechanicznie: dla każdej funkcji z `lib/api.ts` policzyłem, ile komponentów ją woła.
Ta jedna komenda znalazła wszystkie braki w kilka sekund:

```bash
for fn in $(grep -oE "^export (const|async function|function) [a-zA-Z]+" src/lib/api.ts | awk '{print $NF}'); do
  echo "$fn: $(grep -rl "\b$fn\b" src/components src/App.svelte | wc -l)"
done
```

Wynik: **zero użyć** miały `getItemsByFolder`, `postDecisionByFolder` (S1.6)
i `searchItems` (S4.3) — backend był, interfejsu nie było. Do tego brakowało
klawisza `t` z S1.5. Wszystko uzupełnione tego samego dnia.

Reszta punktów potwierdzona jako naprawdę zrobiona: S0.1–S0.7, S1.1–S1.4, S1.7–S1.9,
S2.1, S2.3–S2.6, S3.1–S3.6, S4.1, S4.2, S4.4. Świadomie nieużywane zostają
`getQueue` (kolejka decyzji bierze pozycje przez `/api/items` z tymi samymi filtrami,
więc drugi endpoint jest zbędny) i `getGraphNodeFor` (wejście do grafu prowadzi przez
węzeł przedmiotu; deep link po treści czeka na realną potrzebę).

**Wniosek do stosowania przy każdym kolejnym odhaczeniu:** „endpoint istnieje” to
nie to samo co „funkcja działa”. Sprawdzaj wywołanie w komponencie.

## Kod grafu w repo (2026-09-22)

- [x] Źródła synapse (generator .NET + viewer) wciągnięte jako `git subtree` do `studio/graf/` — decyzja użytkownika: skoro graf jest przerobiony pod nas, ma być wersjonowany z nami, a nie tylko w lokalnym klonie. 1,5 MB, 153 pliki; `just studio-graf`, `just synapse-view`, `VIEWER_DIST` i test kontraktu generatora przestawione na nową ścieżkę; `vendor/synapse` zostaje wyłącznie jako klon upstreamu do `git subtree pull/push`.
- [x] Przy okazji domknięta cicha ścieżka: studio czyta dane grafu **wyłącznie** z `20_WORK/synapse/`. Wcześniej miało fallback na `public/graph.json` viewera — a vendorowany viewer ma tam własny, 17-kilobajtowy graf demo, więc brak naszego grafu skończyłby się pokazaniem cudzych danych zamiast komunikatu „zbuduj graf”.

## Wydajność i praca na tablecie (2026-09-22)

Zgłoszone z tabletu przez tailnet: „dosyć długo wszystko się wczytuje”. Zmierzone
Playwrightem (liczba żądań, rozmiary, czasy) i naprawione u źródła:

| Co | Było | Jest |
|---|---:|---:|
| `graph.json` | 4381 KiB | **241 KiB** (gzip) |
| drzewo planu | 721 KiB | **137 KiB** (gzip) |
| klastry przedmiotu | 432 KiB | **33 KiB** (gzip) |
| pulpit (`/api/subjects`) | 43 KiB | **3 KiB** (gzip) |
| strona PDF w podglądzie | 1006 KiB (PNG) | **110 KiB** (JPEG) |

- gzip włączony dla całej aplikacji; ta wersja Starlette sama pomija
  `text/event-stream` i obrazy, więc log etapu leci dalej na żywo, a JPEG nie jest
  pakowany drugi raz;
- podgląd przyjmuje `width`, a kolejka decyzji prosi o rozmiar dopasowany do ekranu;
- **stronicowanie klastrów i drzewa planu okazało się niepotrzebne** — po kompresji
  oba mieszczą się w kilkudziesięciu kilobajtach. Gdyby kiedyś przestały, kolejnym
  krokiem jest wysyłanie nagłówków klastrów bez członków i dociąganie ich przy
  rozwijaniu.

Do tego dotyk i układ: gesty w grafie (jeden palec przesuwa, dwa skalują; sufit zoomu
2,6 → 6), zwijane panele boczne jako pionowe zakładki, drugi poziom wyboru
(strumień/katedra), zapamiętywanie wyboru w `localStorage` i nagłówek, który przewija
się w poziomie zamiast chować zakładki poza ekran (na 412 px `plan`, `graf`
i `statystyki` były nieklikalne).

## Telefon, tekst i zakres grafu (2026-09-23)

Druga tura zgłoszeń z telefonu i tabletu. Każde znalazło realną wadę, żadnej nie
złapały testy — więc każda dostała test przed poprawką.

- **Wbudowany graf na telefonie ładował sam panel boczny.** Pasek zakładek rozpychał
  całą stronę (`main` miał 769 px przy ekranie 412 px), a zwinięta zakładka panelu
  leżała NA panelu roboczym i zjadała mu lewą krawędź. Układ jest domknięty do
  szerokości ekranu, a panel roboczy zaczyna się za szynami: canvas grafu ma teraz
  pełne 382 px zamiast 192.
- **Pliki md/txt/kod pokazują się jako tekst.** Extract nie dotknął ani jednej treści
  `other` (4537) i ponad dwustu `text`/`code`, więc podgląd bywał pusty przy pozycji,
  o której trzeba było zdecydować. Backend czyta wtedy głowę **samego pliku**, ale
  tylko gdy bajty są tekstem — `.obj` i `.jar` nadal uczciwie mówią „bez podglądu”.
  Język do kolorowania składni ustala backend (`preview.text_language`), a
  `highlight.js` doczytuje się osobnym chunkiem dopiero, gdy jest co pokolorować.
- **Nie dało się oddalić grafu do widoku całości.** Kółko stawało na 0,35, a paczka
  otwiera się przy 0,06 — po pierwszym przybliżeniu nie było jak wrócić i przesuwanie
  między semestrami było zgadywanką. Podłoga zoomu to teraz 0,04.
- **Filtr „SEM3 + pliki” pokazywał przedmioty bez plików.** `category` = `SEM3` mają
  wyłącznie węzły przedmiotów. Viewer dostał wybór **zakresu**: semestr, a pod nim
  przedmiot (lista zawęża się do wybranego semestru), oba działające na tagach, które
  niosą wszystkie trzy poziomy. Eksport dokłada przedmiotowi jego skrót jako tag —
  jedno kliknięcie wybiera przedmiot razem z materiałami. Wejście do przedmiotu samo
  odsłania typ `file`.

## Płynność grafu przy 2,5 tys. węzłów (2026-09-23)

Zgłoszone z ręki: „jak odpalę ako + files, to bardzo laguje cały canvas". Zmierzone
Playwrightem przy dławieniu CPU ×4 (czyli mniej więcej tablet), 2565 widocznych węzłów:

| Co (przerysowania grafu na sekundę) | Było | Jest |
|---|---:|---:|
| przesuwanie po ułożeniu | 4,2 | **16,4** |
| przesuwanie w trakcie układania | 2,8 | **16,0** |
| układanie w ogóle się kończy | nie w 45 s | **~10 s** (≈2,5 s bez dławienia) |

**Poprawka do pierwszej wersji tego wpisu:** podane wcześniej 6,4 → 38,8 kl./s mierzyły
pętlę `requestAnimationFrame` przeglądarki, która tyka 60 razy na sekundę niezależnie od
tego, czy graf się przerysował. Właściwą miarą jest liczba PRZERYSOWAŃ grafu — i ta daje
2,7× zamiast 6×. Wnioski o przyczynach zostają: kolejność poprawek wynikała z profilu,
nie z tej liczby.

Co to powodowało — same rzeczy niewidoczne w kodzie rysującym:

- `graph.nodes.find()` **wewnątrz pętli po krawędziach** (grot strzałki potrzebował
  promienia celu): przy 4 tys. węzłów i tylu samo krawędziach to jedenaście milionów
  porównań NA KLATKĘ. Teraz indeks `Map`, budowany raz na graf;
- `getPositions()` sklejało świeżą tablicę 2565 obiektów przy każdym rysowaniu **i przy
  każdym ruchu myszy**; teraz jedna tablica aktualizowana w miejscu, z licznikiem wersji;
- quadtree do trafiania w węzeł budowany przy KAŻDYM ruchu wskaźnika — teraz tylko wtedy,
  gdy pozycje faktycznie się zmieniły;
- sortowanie wszystkich węzłów co klatkę po to, by dwa narysować na wierzchu;
- każda krawędź miała własną ścieżkę i własny `stroke()` — teraz jeden wsad na wygląd;
- symulacja chłodziła się 220 tyknięć niezależnie od rozmiaru (przy 2,5 tys. węzłów to
  kilkadziesiąt sekund zajętego canvasu) — duży układ stygnie w ~65;
- rysowanie przy każdym tyknięciu symulacji plus odświeżanie minimapy: teraz najwyżej
  co 45 ms i co 200 ms;
- **dotknięcie płótna wstrzymuje układanie**, puszczenie wznawia. Ręka ma pierwszeństwo
  przed fizyką;
- węzeł, który ma na ekranie mniej niż cztery piksele, rysuje się jako kropka w jednej
  wsadowej ścieżce na kolor — pierścień, kropka wewnętrzna i obwódka i tak lądowały na
  tym samym pikselu. Groty strzałek pojawiają się dopiero, gdy są mniejsze od węzła.

Po zgłoszeniu z Pixela 10 Pro (na maksymalnym oddaleniu nadal 2–4 kl./s) doszły dwie
rzeczy celujące w koszt POZA naszym JS-em — bo rysowanie w JS to przy tym grafie 2 ms,
a klatka potrafi trwać ćwierć sekundy:

- **limit gęstości rysowania**: telefon z `devicePixelRatio` 3 malował dziewięć pikseli
  fizycznych na jeden CSS-owy; teraz maksymalnie cztery (dpr 2). Przy obrazie złożonym
  z kropek i włosowatych linii różnicy nie widać, a pracy jest o połowę mniej;
- **samoregulacja**: gdy klatki i tak są wolniejsze niż 33 ms, gęstość schodzi o pół
  kroku (do 1), a gdy graf się uspokoi — wraca. Ostrość spada tylko wtedy, gdy
  alternatywą jest szarpanie;
- **`/graf/?diag=1`** pokazuje liczby z urządzenia: przerysowania na sekundę, czas
  rysowania, liczbę węzłów i krawędzi, zoom oraz realną gęstość pikseli. Bez tego
  „laguje" nie daje się odróżnić od „jest dużo elementów".

**Najdroższa rzecz w całym widoku nie była grafem — była minimapą.** Podgląd z Pixela
(`?diag=1`) pokazał rysowanie grafu w **3,4 ms** przy **2 klatkach na sekundę**: pół
sekundy na klatkę szło poza nasz kod. Minimapa była SVG-iem z jednym `<circle>` na węzeł
i jedną `<line>` na krawędź — blisko **10 000 elementów DOM** — a ramka widoku zmienia
się przy KAŻDEJ klatce przesuwania, więc przeglądarka przemalowywała je wszystkie, bez
przerwy. Teraz to canvas z dwiema warstwami: układ trafia do bitmapy przerysowywanej
tylko przy zmianie pozycji albo filtra, a przesuwanie to jedno przeklejenie bitmapy
i jeden prostokąt. Z minimapy został **1 element DOM zamiast ~9800**.

Wniosek, którego nie dało się wyczytać z kodu grafu: **mierz stronę, nie komponent.**
Graf był szybki (3 ms), a dławił go sąsiad rysujący ten sam zbiór danych drugi raz.

**Drugie zgłoszenie z Pixela — po przybliżeniu.** Odczyt z `?diag=1`: 359 węzłów na
ekranie, ale **2564 krawędzie** i 6 kl./s. Układ jest gwiazdą: każdy plik ma szprychę do
węzła przedmiotu, więc po przybliżeniu rysowały się tysiące linii długich na kilka
ekranów — koszt był w ich RASTERYZACJI (miliony pikseli), nie w liczbie. Teraz przy
przybliżeniu odpada to, czego drugiego końca i tak nie widać (dłuższe niż 1,5 przekątnej
ekranu), a bliskie relacje między sąsiednimi plikami zostają. Zmierzone przy dławieniu
CPU ×4 na ekranie telefonu: 6 → **16 kl./s**, przy 422 krawędziach zamiast 2564.

Przy tym samym zgłoszeniu: **większość węzłów nie miała nazw**, bo próg gęstości liczył
wszystkie węzły przepuszczone przez filtr (2565), a nie te na ekranie (359) — i przy
przedmiocie z 2,5 tys. plików włączał się na zawsze. Teraz liczy ekran, a próg jest
w pikselach: przybliżyłeś na tyle, że widać kółko — widzisz nazwę. Etykiety rysują się
jednym przebiegiem z jednym ustawieniem fontu (to jedna z droższych operacji kontekstu)
i żadna nie chowa się już pod węzłem narysowanym po niej.

Do tego **doostrzenie po uspokojeniu**: obniżona gęstość pikseli wracała do pełnej
dopiero przy następnym rysowaniu, a po puszczeniu palca nikt go nie zlecał — obraz
zostawał rozmyty. Teraz po 650 ms ciszy leci jedna klatka w pełnej ostrości.

Sprawdzone i **odrzucone**: nieprzezroczysty kontekst (`alpha: false`). Wygląda na
darmową oszczędność, a wyszło 4 przerysowania/s zamiast 11 — zmiana cofnięta, komentarz
w kodzie mówi dlaczego.

Wnioski na przyszłość: **najpierw profil, potem optymalizacja** — pierwsze pomiary
wskazywały na rasteryzację, a dopiero profil CPU pokazał, że 57% czasu idzie poza JS,
i dopiero test A/B (rysowanie bez krawędzi / bez węzłów) ustawił kolejność prac. Drugi:
pomiar zrobiony w trakcie układania kłamie — wcześniejsze 4 kl./s mierzyło symulację,
nie przesuwanie. I trzeci, najdroższy: **sprawdź, co właściwie liczy Twój licznik** —
`requestAnimationFrame` tyka 60 razy na sekundę nawet wtedy, gdy graf nie przerysował się
ani razu.

## Kategoria jako poziom grafu (2026-09-23)

Propozycja użytkownika: zamiast wszystkich plików wprost przy przedmiocie — `kolokwia`,
`ćwiczenia`, `laboratoria`, `inne`, a pliki dopiero z nich. Trafiona w obie strony:

- **czytelność**: przedmiot pokazuje siedem podpisanych skupisk zamiast dwóch i pół
  tysiąca szprych, po których nie da się poznać, co jest czym;
- **wydajność**: pliki leżą przy swojej kategorii, więc krawędzie są krótkie i lokalne,
  a nie biegną przez pół grafu. Układanie przedmiotu skróciło się z 10 do 8 s (dławienie
  CPU ×4), przesuwanie zostało na 16 przerysowaniach/s;
- **nawigacja**: zakres w panelu filtrów ma teraz trzeci poziom, a wybór kategorii sam
  odsłania pliki. „SEM3 → AKO → Egzamin" to 147 węzłów zamiast 2571.

Zmiany: `NODE_CATEGORY` i `category_id` w `orglib/synapse_vault.py`, węzły kategorii
w `scripts/synapse_export.py` (bez pustych), `presentNodeTypes`/`nodeTypeScale` w viewerze,
kontrakt w `docs/SYNAPSE.md`.

Przy okazji dwie rzeczy, które wyszły dopiero na realnych danych:

- **tag tożsamości trzeba liczyć w obrębie RODZICA, nie całego poziomu.** „Kolokwia" ma
  każdy przedmiot, więc reguła „tag unikalny wśród węzłów tego typu" dawała kategoriom
  9 nazw na 127. W obrębie przedmiotu `kategoria-kolokwia` jest jednoznaczna. Ta sama
  poprawka odzyskała 11 przedmiotów, których skrót powtarza się w innym semestrze;
- **licznik przy opcji ma mówić, ile zobaczysz po kliknięciu.** „Egzamin · AKO · 303"
  liczyło egzaminy całej paczki, a po wybraniu zostawało 148. Licznik niezgodny z tym,
  co widać, jest gorszy niż jego brak.

Do tego dolna granica „dopasuj widok" zrównana z granicą kółka (0,04): przedmiot z dwoma
tysiącami plików nie mieścił się na ekranie telefonu przy 0,06, więc dopasowanie
pokazywało wycinek i wyglądało na zepsute.

## Kręgosłup hierarchii zawsze widoczny (2026-09-23)

Zgłoszenie: „żeby root (AKO) miał połączenia do dzieci zawsze widoczne i żeby lepiej się
wyróżniał". Trafione — tych krawędzi jest kilkanaście, a niosą najwięcej treści:

- połączenia **kontener → kontener** (semestr → przedmioty, przedmiot → kategorie) nie
  podlegają regule długości ani kadrowaniu; mają też minimalną grubość na ekranie, bo
  grubość liczy się w jednostkach świata i przy oddaleniu linia schodziła poniżej piksela;
- kontenery rysują się **na wierzchu** (wcześniej ginęły pod plikami), z poświatą
  w kolorze kategorii, i nie schodzą poniżej sześciu pikseli promienia;
- rozmiary poziomów rozsunięte: semestr 2,2 · przedmiot 1,7 · kategoria 1,3 · plik 1;
- **podpisy rysowane w przestrzeni ekranu**, a nie świata. To była realna wada: tekst
  skalował się razem z grafem, więc przy widoku całej paczki dwunastopunktowa etykieta
  miała pół piksela i podpisy semestrów po prostu znikały;
- podpisy kontenerów mają pierwszeństwo, ale z budżetem (48). „Zawsze" brzmiało dobrze
  i wyglądało źle: 232 nazwy naraz to ściana, z której nie da się odczytać żadnej.
  Przy tłoku zostają najgrubsze poziomy, reszta wraca po przybliżeniu.

## Podpisy warstwami (2026-09-23)

Dwie uwagi z ręki, obie o tym samym — ile tekstu naraz ma sens:

- **przedmiot podpisany jest skrótem**, nie pełną nazwą. `AKO — Architektura
  Komputerów` przy węźle zasłaniało sąsiadów; pełna nazwa zostaje aliasem (więc
  wyszukiwarka jej nie traci) i pierwszą linią treści notatki;
- **o podpisach rozstrzyga to, czy się MIESZCZĄ.** Cztery wersje tej reguły i trzy
  pierwsze były przybliżeniami tego samego pytania: „zawsze" dało ścianę 232 zlepionych
  nazw; próg przybliżenia czyścił ścianę, ale gasił też siedem nazw kategorii przy
  wybranym jednym przedmiocie; próg liczbowy (do 24 kontenerów) ratował tamten
  przypadek, ale wpuszczał plamę tam, gdzie dziesięć kategorii skupiało się wokół
  jednego przedmiotu. Dopiero układanie prostokątów odpowiada wprost: nazwy są mierzone
  przed rysowaniem, układane w kolejności ważności, a te, które nachodziłyby na już
  położone, odpadają. Progi i budżety zniknęły z kodu.

## Poziomy podpisów i rozdzielanie przedmiotów (2026-09-23)

Dwie uwagi z ręki po obejrzeniu poprzedniej wersji:

- **„Na danym poziomie chcę widzieć WSZYSTKIE etykiety".** Układanie po kolizjach
  pojedynczo podpisywało część przedmiotów, a część nie — co wygląda na usterkę i każe
  zgadywać, czemu akurat te. Teraz decyzja zapada dla całego poziomu: wchodzi w całości
  albo wcale, od najgrubszego. Przy wybranym przedmiocie widać jego siedem kategorii
  nawet przy pełnym oddaleniu, a w gęstwinie poziom milknie cały i wraca po przybliżeniu.
- **„Wiele przedmiotów bardzo się miesza, choć nie ma między nimi połączeń".** To był
  błąd układu, nie rysowania: symulacja kotwiczyła węzły po polu `category`, a u pliku
  znaczy ono rodzaj materiału (`egzamin`, `laboratoria`) i jest wspólne dla całej paczki.
  Egzaminy dziesięciu przedmiotów miały więc jedną kotwicę. Teraz węzeł ciąży do swojego
  RODZICA w hierarchii (`belongs_to`), a vault bez hierarchii zachowuje stare zachowanie.
  Przy wielu grupach kotwice idą po tarczy (słonecznik) zamiast po jednym okręgu — dwieście
  kotwic na okręgu leżało kilka pikseli od siebie i skupiska wracały do siebie.

Przy okazji **cztery czerwone testy viewera zgasły**: `categoryAnchors` (3) i `Viewport`
(1) sprawdzały nieaktualne oczekiwania — wołały funkcję bez środka układu, oczekując
środka ekranu, i pilnowały starej podłogi dopasowania. Suite viewera jest zielony.

## Kotwice zagnieżdżone w hierarchii (2026-09-23)

Poprzednia poprawka („kotwicz po rodzicu, nie po kategorii") rozdzieliła przedmioty,
ale zrobiła to w pół drogi: kotwice dostawały SLOTY na jednej tarczy, w kolejności
napotkania. Kategoria AKO lądowała więc w losowym miejscu — daleko od samego AKO —
i jej szprycha przecinała pół grafu. Zgłoszone z drugiego ekranu: „podkategorie są
wystrzelone w kosmos daleko od przedmiotu".

Teraz pozycje kotwic liczy `hierarchyAnchors`: semestry wokół środka, przedmioty wokół
swojego semestru, kategorie wokół swojego przedmiotu, pliki przy swojej kategorii. Łuk
dziecka jest proporcjonalny do jego wagi (liczby potomków), więc duży przedmiot dostaje
tyle miejsca, ile zajmuje. Vault bez hierarchii dalej używa `categoryAnchors`.

Wniosek: „kotwicz po rodzicu" było dobrą regułą z niedokończoną implementacją — klucz
kotwicy ma sens tylko razem z jej POZYCJĄ liczoną względem rodzica.

## Trzy zgłoszenia znad zbliżenia (2026-09-23)

- **Węzły o nazwach będących skrótem sha (890 sztuk).** Nie błąd rysowania, tylko dane:
  ground truth opisuje materiały leżące JUŻ w paczce, które nigdy nie były indeksowane
  jako pliki źródłowe, więc `files` nie ma dla nich wiersza i eksport nie miał skąd wziąć
  nazwy. Teraz bierze ją ze ścieżki docelowej z decyzji (`content_name`), czyli stamtąd,
  gdzie ten materiał faktycznie leży.
- **Podpisy plików pojawiały się dopiero przy bardzo dużym zbliżeniu.** Zmierzone: przy
  722 plikach na ekranie ani jednej nazwy aż do zoomu 0,594. Powód strukturalny: zasada
  „wszystkie albo nic" przy poziomie plików znaczy „nic", bo siedemset nazw nie zmieści
  się obok siebie przy ŻADNYM powiększeniu. Kontenery (semestr, przedmiot, kategoria)
  zostają przy regule „wszystkie albo nic" — jest ich garstka i częściowe podpisanie
  wygląda tam na usterkę. Pliki dostają tyle podpisów, ile się mieści, w stałej
  kolejności. Do tego mniejsza czcionka (9,5 px), skracanie długich nazw w środku
  (koniec niesie rozszerzenie) i próg promienia 4,5 → 3 px. Wynik: pierwsze nazwy przy
  zoomie 0,267 zamiast 0,594, koszt rysowania 2,6 ms.
- **Duże skupiska odlatywały od przedmiotu.** Promień skupiska rośnie jak
  `odstęp × √liczba`, a odstęp kolizji wynosił 30 — przy 700 plikach robiło to tarczę
  o promieniu półtora tysiąca jednostek. Odstęp 30 → 14, `SPACING` kotwic 26 → 22,
  a ciąg do kotwicy 0,0085 → 0,03: przy 820 odpychania prototypowa stała przegrywała
  i skupisko rozdymało się niezależnie od tego, jak dobrze policzono kotwice.

Podgląd `?diag=1` pokazuje teraz także **liczbę postawionych podpisów** — bez niej te
progi znowu byłyby zgadywaniem.

## Kaskada podpisów i podgląd w notatce (2026-09-24)

- **Podpisy czytało się od końca:** przy oddaleniu widać było nazwy plików, a nazwa ich
  kategorii dopiero po przybliżeniu. Powód: poziom kontenerów jest rygorystyczny, więc
  gdy nie mieścił się w całości, milkł — i zwalniał miejsce plikom, które są zachłanne.
  Kaskada jest teraz jednokierunkowa: poziom, który się nie zmieścił, **zatrzymuje
  wszystkie drobniejsze**. Zmierzone w zakresie kategorii: podpis kategorii od razu,
  nazwy plików od zoomu 0,277.
- **Kliknięcie węzła pokazuje materiał.** Notatka pliku niesie obraz albo pierwszą stronę
  PDF-a (`/api/preview/<sha>/image`), a dla tekstu kilka pierwszych linijek; na końcu
  odnośnik `Otwórz w studiu` (`/?sha=…`), który otwiera wyszukiwanie na tej treści.
  Głowy tekstu czyta `export()`, nie `build_notes` — ta druga zostaje czystą funkcją nad
  wynikiem zapytań.

## Podgląd materiałów z paczki (2026-09-24)

- **Część podglądów była zepsutym obrazkiem.** Nie losowo: dokładnie te 890 treści, które
  nie mają wiersza w `files`, bo leżą wyłącznie w paczce. Podgląd szukał pliku tylko
  w drzewie źródeł. Teraz, gdy tam go nie ma, sięga po ścieżkę docelową z decyzji
  (`preview.package_copy`) — przez ten sam helper containmentu, więc wpis prowadzący poza
  repo paczki dalej kończy się odmową, a nie odczytem. Sprawdzone na realnych danych:
  6/6 wcześniej martwych podglądów działa.
- **Urwany tekst mówi, że jest urwany.** W notatce grafu kończy się `…` i adnotacją
  „fragment — całość w studiu" (839 notatek), a API podglądu zwraca `text_truncated`,
  po którym panel decyzji dopisuje „… to tylko początek pliku".

## Viewer pod telefon (2026-09-24)

Cztery zgłoszenia z jednego ekranu, wszystkie o układzie, nie o danych:

- **legenda i minimapa pod krawędzią** — wysokość szła z `100vh`, która liczy się do
  całego ekranu, a nie do obszaru widocznego nad paskiem adresu. `100dvh` (z `vh` jako
  wartością zapasową dla starszych przeglądarek) trzyma je w kadrze;
- **panel notatki wychodził poza szerokość ekranu** i przewijała się cała strona. Blok
  kodu z podglądem pliku bywa szerszy od telefonu — teraz przewija się sam
  (`overflow-x` na `pre`), a panel ma `max-width: min(640px, 100vw)`;
- **cztery zakładki nie mieszczą się obok wyszukiwarki** — poniżej 720 px zwijają się
  w listę rozwijaną;
- **podgląd `?diag=1` zasłaniał notatkę** — na telefonie startuje zwinięty do plakietki
  z liczbą klatek, dotknięcie rozwija go i zwija z powrotem. To narzędzie pomiarowe,
  więc ustępuje treści, którą mierzy.

## Druga tura poprawek mobilnych (2026-09-24)

- **pasek viewera nadal wystawał** — poniżej 720 px znika nazwa vaulta i skrót `⌘K`,
  a wyszukiwarka oddaje szerokość, więc koło zębate mieści się w kadrze;
- **plakietka `kl./s` zasłaniała `×` panelu notatki** — na wąskim ekranie idzie na lewą
  stronę, obok przycisku filtrów;
- **przycisk szuflady filtrów siedział na tytule panelu** i po zamknięciu wchodził na
  panel notatki — po otwarciu przenosi się na prawą krawędź szuflady;
- **filtry nie przeżywały odświeżenia** — teraz zapisują się w `localStorage`.
  Wczytany wybór jest PRZYCINANY do słownika bieżącego grafu (tagi, typy, kategorie,
  rodzaje relacji): po przebudowie vaulta wpis po nieistniejącym przedmiocie wygasiłby
  widok bez śladu, dlaczego. Pusty wybór nie jest przywracany — wtedy wchodzi widok
  domyślny, czyli szkielet paczki;
- **menu trybów w studiu** poniżej 1100 px też jest listą rozwijaną; przyciski i lista
  czytają z jednej tablicy `MODES`, żeby nie rozjechały się przy kolejnej zmianie;
- **pływające przyciski ustępują otwartej notatce** (propozycja użytkownika): na wąskim
  ekranie mieści się jeden panel, więc przycisk filtrów i plakietka pomiarów znikają,
  gdy notatka jest otwarta, i wracają po jej zamknięciu. Przesuwanie ich w kółko po
  rogach nie miało końca — dopóki dwa panele walczą o ten sam ekran, zawsze coś zasłania
  coś innego.

## „0 kB" w notatkach grafu (2026-09-24)

Jedno pytanie użytkownika, dwie różne przyczyny — warto je rozróżniać:

- **materiały bez wiersza w `files`** (te same 890 co przy nazwach i podglądach) nie
  miały skąd wziąć rozmiaru. Teraz eksport czyta go ze `stat` pliku w paczce;
- **pliki mniejsze niż pół kilobajta** pokazywały „0 kB" przez samo formatowanie:
  `271 / 1024` zaokrąglone do jedności to zero. Dotyczyło 761 notatek, czyli więcej niż
  pierwsza przyczyna. `human_size` podaje bajty poniżej kilobajta i megabajty powyżej,
  a pusty rozmiar znaczy „nie wiem", nie „mało".

Po przebudowie: zero notatek z „0 kB".

Ścieżka `.md` w nagłówku notatki to **ścieżka samej notatki w vaulcie**, nie materiału —
tak działa viewer dla każdego vaulta. Ścieżka materiału jest niżej, przy decyzji
(`paczka/SEM…`) i w sekcji „Prowenancja".

## Zmiana nazwy w paczce z kolejki decyzji (QoL Q2, 2026-09-24)

`POST /api/decisions/rename` i klawisz `r`. Osobna operacja od edycji całej ścieżki (`t`),
bo to dwie różne decyzje: „ma się nazywać inaczej" i „ma leżeć gdzie indziej". Katalog jest
w polu widoczny, ale nieedytowalny, a kursor wchodzi z zaznaczonym rdzeniem nazwy.

Co z tego wyszło:

- **reguły nazw są jedne** — `rename_target` przepuszcza nową ścieżkę przez
  `plan_lint.check_path_safety` i `check_windows_name`, więc nazwa nie do utrzymania na
  Windowsie odbija się w kolejce, a nie dopiero przy `validate`;
- **kolizję porównujemy bez względu na wielkość liter**: paczka jedzie do repo klonowanego
  też na Windowsie i macOS-ie, gdzie `Wyklad1.pdf` i `wyklad1.pdf` to jeden plik, czyli
  cicha strata materiału. Kolizja dotyczy całej ścieżki — ta sama nazwa w innym katalogu
  jest w porządku;
- **ta sama nazwa nie jest decyzją**: bez tego samo otwarcie pola i Enter zamieniałyby
  heurystykę w „decyzję człowieka" z pewnością 1.0;
- zapis idzie przez `record_decision`, więc ochrona `ground_truth` i wpis w
  `manual_decisions` są te same co dla każdej innej decyzji — bez drugiej implementacji.

Pułapka na przyszłość: **dymne sprawdzenie endpointu zapisu na żywej bazie zapisuje**.
Próba „czy kolizja zadziała" trafiła w nazwę, która akurat była wolna, i zostawiła prawdziwą
ręczną decyzję. Odtworzenie wyszło z `plan_items` i z sąsiednich wierszy tego samego przebiegu
planu (`plan:080b597c7a37`), ale na żywej bazie wolno wywoływać tylko warianty jawnie
bezskutkowe (ta sama nazwa) albo takie, które kończą się błędem.

## Zależności od potoku

- **B10** `apply.py`, **B11** `verify.py` → S3
- **B14** `manual_decisions.py` → S1
- **D1** pilotaż AKO — pierwszy realny test S1/S2
