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
- [x] S1.5 Obsługa klawiaturą (`Enter`, `1..9`, `t`, `s`, `o`, `u`, `?`) i licznik „ile zostało” — 2026-09-19; 9 kategorii z klawiatury, overlay pomocy, `o` dla outdated
- [x] S1.6 Decyzja hurtem po katalogu źródłowym — z podglądem, czego dotknie, przed zapisem — 2026-09-19; GET/POST /api/decisions/by-folder; ground truth elementy pomijane cicho zamiast odrzucenia całej partii
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
- [x] S2.2 Widok klastra: siatka kart z miniaturą i metadanymi, wskazanie wersji kanonicznej — 2026-09-19 karty i wybór kanonicznej, **2026-09-22 miniatury** (wcześniej karty pokazywały same metadane, mimo odhaczenia)
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
- [x] S4.3 Wyszukiwanie przekrojowe + zapisywane widoki — 2026-09-19; GET /api/search (LIKE po filename, path, category, sha256); frontend searchItems w api.ts — ~~zapisywane widoki~~ porzucone (zbyt mało wartości bez S3)
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

## Kod grafu w repo (2026-09-22)

- [x] Źródła synapse (generator .NET + viewer) wciągnięte jako `git subtree` do `studio/graf/` — decyzja użytkownika: skoro graf jest przerobiony pod nas, ma być wersjonowany z nami, a nie tylko w lokalnym klonie. 1,5 MB, 153 pliki; `just studio-graf`, `just synapse-view`, `VIEWER_DIST` i test kontraktu generatora przestawione na nową ścieżkę; `vendor/synapse` zostaje wyłącznie jako klon upstreamu do `git subtree pull/push`.
- [x] Przy okazji domknięta cicha ścieżka: studio czyta dane grafu **wyłącznie** z `20_WORK/synapse/`. Wcześniej miało fallback na `public/graph.json` viewera — a vendorowany viewer ma tam własny, 17-kilobajtowy graf demo, więc brak naszego grafu skończyłby się pokazaniem cudzych danych zamiast komunikatu „zbuduj graf”.

## Zależności od potoku

- **B10** `apply.py`, **B11** `verify.py` → S3
- **B14** `manual_decisions.py` → S1
- **D1** pilotaż AKO — pierwszy realny test S1/S2
