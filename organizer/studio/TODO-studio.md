# TODO — studio

Zadania podprojektu `organizer/studio/`. Plan i uzasadnienia: `PLAN.md`.
Zadania potoku (B/C/D/E) zostają w `organizer/TODO.md` — tutaj tylko to, co dotyczy
widoku. Pozycje, od których studio zależy, są wypisane jako zależności, nie kopiowane.

**Jak prowadzić ten plik:** odhaczaj `- [x]` dopiero, gdy rzecz działa i ma testy;
w tej samej linii dopisz datę i jedno zdanie o tym, co z tego wynikło — zwłaszcza
gdy coś okazało się inne, niż zakładał plan. Rzeczy porzucone przekreślaj
(`~~…~~`) z powodem, zamiast kasować: powód jest wart więcej niż czysta lista.

## S0. Szkielet (tylko odczyt)

- [ ] S0.1 `fastapi` i `uvicorn` w `setup/requirements.txt`, instalacja w `.venv`, wpis w README (sekcja Zależności)
- [ ] S0.2 `studio/api/` — aplikacja FastAPI: nasłuch wyłącznie `127.0.0.1`, sprawdzenie `schema_version` przy starcie, baza otwierana `mode=ro` dopóki nie ma zapisu
- [ ] S0.3 Endpointy odczytu: `/api/subjects` (przedmioty × etapy), `/api/subjects/{sem}/{skrot}`, `/api/items` (filtry: status, kategoria, pewność, `needs_review`), `/api/items/{sha256}`
- [ ] S0.4 `studio/web/` — Svelte + Vite; pulpit: lista przedmiotów, postęp, kolejka „co następne”
- [ ] S0.5 Recepty `just studio` i `just studio-dev`
- [ ] S0.6 Testy: kontrakt API ↔ `orglib` (te same liczby co `status_report`), warstwa `cli_contract` dla launchera, smoke startu serwera
- [ ] S0.7 Bramka bezpieczeństwa w testach: serwer odmawia startu z adresem innym niż loopback; brak jakiegokolwiek endpointu zapisu w fazie S0

## S1. Kolejka decyzji (pierwszy zapis)

Zależy od: **B14** (`scripts/manual_decisions.py`) — studio musi używać tej samej
funkcji zapisu co CLI, więc CLI powstaje pierwsze.

- [ ] S1.1 B14 w potoku: zapis decyzji do `manual_decisions` + `classifications` (`classification_method='manual'`, `confidence=1.0`), eksport do `reports/manual_decisions.jsonl`
- [ ] S1.2 `/api/decisions` (POST) — cienka warstwa nad funkcją z B14; strażnik na wiersze `run_id='ground_truth'`
- [ ] S1.3 Endpoint podglądu: miniatura z `20_WORK/thumbnails`, strona PDF renderowana PyMuPDF, głowa tekstu z `20_WORK/extracted_text`; wyłącznie pliki z indeksu, przez wspólny helper containmentu
- [ ] S1.4 Widok kolejki: podgląd + propozycja + alternatywy + powód decyzji reguł
- [ ] S1.5 Obsługa klawiaturą (`Enter`, `1..9`, `t`, `s`, `o`, `u`, `?`) i licznik „ile zostało”
- [ ] S1.6 Decyzja hurtem po katalogu źródłowym — z podglądem, czego dotknie, przed zapisem
- [ ] S1.7 Cofanie ostatniej decyzji (i całej operacji hurtowej) jako jedna akcja
- [ ] S1.8 Testy: kontrakt zapisu, odmowa nadpisania ground truth, containment ścieżek podglądu (także na ścieżce względnej i dowiązaniu), e2e „decyzja w UI → wiersz w bazie → linia w eksporcie”
- [ ] S1.9 Mutacja: usunięcie strażnika ground truth albo containmentu podglądu MUSI czerwienić testy

## S2. Porównywarka klastrów

- [ ] S2.1 `/api/clusters` — klastry near-dupe (union-find z `orglib/review.py`, bez drugiej implementacji)
- [ ] S2.2 Widok klastra: siatka kart z miniaturą i metadanymi, wskazanie wersji kanonicznej
- [ ] S2.3 Diff tekstu side-by-side i dwie miniatury obok siebie (przeniesione z `review.py`, nie napisane od nowa)
- [ ] S2.4 Zapis rozstrzygnięcia klastra: kanoniczna zostaje, reszta `skip` / `older_version`
- [ ] S2.5 Filtr szumu (wzorce nazw, np. `*.vcxproj.xml`) — konfigurowalny, nie zaszyty w kodzie
- [ ] S2.6 Testy: rozstrzygnięcie klastra nie kasuje niczego w bazie, tylko dopisuje decyzje i relacje

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
- [ ] S4.2 Historia decyzji: „co zmieniłem dziś”, cofnięcie pojedynczej pozycji
- [ ] S4.3 Wyszukiwanie przekrojowe + zapisywane widoki
- [ ] S4.4 Statystyki na żywo (odpowiednik `STATUS.md` bez generowania pliku)

## Zależności od potoku

- **B10** `apply.py`, **B11** `verify.py` → S3
- **B14** `manual_decisions.py` → S1
- **D1** pilotaż AKO — pierwszy realny test S1/S2
