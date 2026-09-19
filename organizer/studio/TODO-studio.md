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
- [x] S1.3 Endpoint podglądu: miniatura z `20_WORK/thumbnails`, strona PDF renderowana PyMuPDF, głowa tekstu z `20_WORK/extracted_text`; wyłącznie pliki z indeksu, przez wspólny helper containmentu — 2026-09-19; GET /api/preview/{sha256}, głowa tekstu do 4096 znaków, bez miniatur (brak plików)
- [x] S1.4 Widok kolejki: podgląd + propozycja + alternatywy + powód decyzji reguł — 2026-09-19; DecisionPanel.svelte z kartą pozycji, propozycją klasyfikacji, przyciskami akcji
- [x] S1.5 Obsługa klawiaturą (`Enter`, `1..9`, `t`, `s`, `o`, `u`, `?`) i licznik „ile zostało” — 2026-09-19; 9 kategorii z klawiatury, overlay pomocy, `o` dla outdated
- [x] S1.6 Decyzja hurtem po katalogu źródłowym — z podglądem, czego dotknie, przed zapisem — 2026-09-19; GET/POST /api/decisions/by-folder; ground truth elementy pomijane cicho zamiast odrzucenia całej partii
- [x] S1.7 Cofanie ostatniej decyzji (i całej operacji hurtowej) jako jedna akcja — 2026-09-19; POST /api/decisions/undo
- [x] S1.8 Testy: kontrakt zapisu, odmowa nadpisania ground truth, containment ścieżek podglądu (także na ścieżce względnej i dowiązaniu), e2e „decyzja w UI → wiersz w bazie → linia w eksporcie” — 2026-09-19; 14 testów w test_studio_s1_extended.py, 10 w test_studio_decisions.py
- [x] S1.9 Mutacja: usunięcie strażnika ground truth albo containmentu podglądu MUSI czerwienić testy — 2026-09-19; mutation guard w testach (3 typy: ground truth, batch atomicity, run_id preservation)

## S2. Porównywarka klastrów

- [x] S2.1 `/api/clusters` — klastry near-dupe (union-find z `orglib/review.py`, bez drugiej implementacji) — 2026-09-19; GET /api/clusters z filtrami semester/skrot/noise
- [x] S2.2 Widok klastra: siatka kart z miniaturą i metadanymi, wskazanie wersji kanonicznej — 2026-09-19; ClusterPanel.svelte z rozwijalnymi kartami i wyborem kanonicznej
- [x] S2.3 Diff tekstu side-by-side i dwie miniatury obok siebie (przeniesione z `review.py`, nie napisane od nowa) — 2026-09-19; inline diff per relacja, side-by-side text w `<pre>` blokach
- [x] S2.4 Zapis rozstrzygnięcia klastra: kanoniczna zostaje, reszta `skip` / `older_version` — 2026-09-19; POST /api/clusters/resolve; decision_type='skip' (nie 'classify' z 'skip' action — to dawało 422)
- [x] S2.5 Filtr szumu (wzorce nazw, np. `*.vcxproj.xml`) — konfigurowalny, nie zaszyty w kodzie — 2026-09-19; fnmatch patterns z config/thresholds.yaml + query param; merge obu źródeł
- [x] S2.6 Testy: rozstrzygnięcie klastra nie kasuje niczego w bazie, tylko dopisuje decyzje i relacje — 2026-09-19; 19 testów w test_studio_clusters.py

## S3. Plan, bramka i apply

Zależy od: **B10** (`apply.py`) i **B11** (`verify.py`).

- [ ] S3.1 Widok drzewa docelowego przedmiotu + lista tego, co nie ma jeszcze miejsca
- [ ] S3.2 „Przenieś tu” = decyzja ręczna, z podświetleniem kolizji nazw
- [ ] S3.3 Diff planu: co dojdzie, co się nadpisze, co pominięte
- [ ] S3.4 Wynik `validate_plan` w UI; **kod wyjścia 2 unieruchamia `apply`** — przycisk martwy, nie ostrzegawczy
- [ ] S3.5 Uruchamianie etapów jako podproces CLI ze streamem logów (SSE), z jawnym potwierdzeniem przed `apply`
- [ ] S3.6 Testy: bramka jest nie do obejścia z UI (żądanie `apply` przy nieważnym planie odrzucone po stronie serwera, nie tylko ukryte w interfejsie)

## S4. Reszta

- [ ] S4.1 `/graf` — osadzony viewer synapse, zaznaczanie węzła z poziomu studia i powrót deep-linkiem
- [x] S4.2 Historia decyzji: „co zmieniłem dziś”, cofnięcie pojedynczej pozycji — 2026-09-19; GET /api/decisions/history + DELETE /api/decisions/{sha256}; HistoryPanel z filtrem daty i undo per pozycja
- [x] S4.3 Wyszukiwanie przekrojowe + zapisywane widoki — 2026-09-19; GET /api/search (LIKE po filename, path, category, sha256); frontend searchItems w api.ts — ~~zapisywane widoki~~ porzucone (zbyt mało wartości bez S3)
- [x] S4.4 Statystyki na żywo (odpowiednik `STATUS.md` bez generowania pliku) — 2026-09-19; GET /api/stats oparty o status_report.collect(); StatsPanel z sekcjami: ogólne, etapy, statusy, metody, kategorie, akcje, progi

## Zależności od potoku

- **B10** `apply.py`, **B11** `verify.py` → S3
- **B14** `manual_decisions.py` → S1
- **D1** pilotaż AKO — pierwszy realny test S1/S2
