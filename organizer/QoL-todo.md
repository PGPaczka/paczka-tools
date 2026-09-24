# QoL-todo — wygoda pracy w studiu

Lista z sesji 2026-09-24. Każdy punkt ma **stan zweryfikowany w kodzie i danych**
(nie z pamięci), czego brakuje i jak to zrobić. Odhaczaj tutaj; reguły procesu są
w `AGENTS.md`, stan podprojektu w `studio/TODO-studio.md`.

---

## Q1. Zmiany wyklikane w studiu widoczne bez terminala

**Stan.** Decyzja zapisana w studiu od razu zmienia liczby w studiu (widoki czytają
bazę na bieżąco), ale **graf jest migawką**: `graph.json` powstaje offline z vaulta,
więc do zobaczenia zmiany trzeba dziś wyjść do terminala po `just studio-graf`.
Ze studia da się uruchomić tylko: `plan`, `validate`, `review`, `apply-dry`, `apply`,
`verify` (`studio/api/runner.py: STAGE_SCRIPTS`).

**Czego brakuje.** Etapu „przebuduj graf” w studiu.

**Jak.** Nowy etap `graph`: `scripts/synapse_export.py` → generator .NET. Budowania
frontu NIE trzeba — viewer czyta `graph.json` z `20_WORK` przy starcie, więc dane
odświeżają się bez przebudowy paczki JS. Przycisk w zakładce `graf` + odświeżenie
iframe po zakończeniu.

- [x] etap `graph` w runnerze (`graph_commands` + `stream_all`, z testem argv wobec
      prawdziwego parsera i testem „łańcuch pęka na pierwszym błędzie")
- [x] przycisk i log na żywo w zakładce `graf`
- [x] po sukcesie: przeładowanie osadzonego viewera i odświeżenie licznika notatek

---

## Q2. Ile da się zrobić w samym studiu

**Stan (co już jest).** Decyzja pojedyncza i hurtem po katalogu, kategoria, **zmiana
ścieżki docelowej** (`t`), pominięcie, kwarantanna, `outdated`, cofanie, rozstrzyganie
klastrów (wersja kanoniczna / starsza), „przenieś tu” w drzewie planu, uruchamianie
etapów i `apply` za bramką. Zapis idzie przez `manual_decisions` — ten sam kod co CLI.

**Czego brakuje do „wszystkiego”.**

- [x] zmiana nazwy pliku docelowego jako osobna operacja — `POST /api/decisions/rename`
      (`orglib.decisions.rename_target`) plus klawisz `r` w kolejce decyzji. Katalog jest
      pokazany, ale nieedytowalny; nazwy sprawdza `plan_lint` (te same reguły co bramka),
      a kolizję z inną treścią zgłasza 409 — porównanie bez względu na wielkość liter,
      bo paczkę klonuje się też na Windowsie. Ta sama nazwa = brak zapisu.
- [x] scalanie treści (merge) — `POST /api/decisions/merge`; wchłonięte dostają `skip`,
      a powiązanie ląduje w `relations` (`detection_method=manual_merge`), więc widzi je graf
      i raporty, nie tylko notatka. Ręczne scalenie przeżywa `just relate`, bo przeliczanie
      kasuje wyłącznie własne wiersze `near_dupe:%` — pilnuje tego test wołający prawdziwe
      `replace_own_relations`. W klastrach przycisk scala zamiast tylko pomijać, z wyborem
      „ten sam materiał / starsze wersje”.
- [x] rozstrzyganie konfliktów ścieżek docelowych z poziomu widoku planu —
      `GET /api/plan/conflicts` liczy je z żywej bazy (nie z pliku planu), więc zmiana nazwy
      gasi konflikt bez ponownego budowania planu. Dwa rodzaje: dwie zaplanowane treści
      w jednej ścieżce oraz zderzenie z plikiem, który już leży w paczce (`applied`).
      W widoku planu sekcja „Konflikty ścieżek” pokazuje obie strony (nazwa, rozmiar,
      pewność, ścieżka źródłowa) i pozwala zmienić nazwę w miejscu.
      **Na dzisiejszych danych jest ich zero** — `build_plan.resolve_collisions` rozstrzyga
      kolizje automatycznie przy budowie planu, więc to siatka bezpieczeństwa dla ręcznych
      zmian, nie naprawa istniejącego bałaganu. Sprawdzone na podstawionych kolizjach
      w kopii bazy, w tym różniących się samą wielkością liter.
- [ ] porównanie diffów dwóch dowolnych treści, nie tylko w obrębie klastra

---

## Q3. Ręczne powiązanie katalogów między paczkami

**Stan.** Katalogi mają `duplicate_of` z podpisu strukturalnego (deterministycznie),
treści mają relacje `near_duplicate` / `older_version`. **Ręcznego wskazania
„folderA ≡ folderB” nie ma.**

**Jak.** Tabela `manual_folder_links` (folder_a, folder_b, kind, decided_at, note),
zapis przez studio, a klasyfikacja i raport przeglądu traktują taką parę jak
`duplicate_of`. Wymaga migracji schematu (v2 → v3) i reguły w `AGENTS.md`, że to
decyzja człowieka, więc ma pierwszeństwo przed heurystyką.

- [ ] migracja schematu + zapis w orglib
- [ ] widok „powiąż katalogi” w studiu (dwie listy + podgląd zawartości obu)
- [ ] użycie powiązania w klasyfikacji i w raporcie przeglądu

---

## Q4. Zmiana nazw w paczce kanonicznej bez psucia powiązań

**Stan.** Decyzja trzyma `target_relative_path`. Ręczne przeniesienie pliku w paczce
rozjeżdża podgląd, rozmiar i `verify` — sprawdzone.

**Jak.** Operacja „zmień nazwę / przenieś w paczce” wykonywana PRZEZ studio: zmiana na
dysku plus aktualizacja `target_relative_path` w jednej transakcji, z wpisem w
`manual_decisions`. Nigdy odwrotnie (najpierw dysk, potem baza).

- [ ] endpoint i widok zmiany nazwy w drzewie docelowym
- [ ] test: po zmianie `verify` jest zielony, a podgląd nadal działa

---

## Q5. OCR obrazów

**Stan.** OCR działa tylko awaryjnie dla PDF-ów bez warstwy tekstowej: `ocr_done=1`
dla **197** treści. Obrazów jest **5 937** i mają **0** wyekstrahowanego tekstu —
`--ocr-images` istnieje, ale nigdy nie było uruchomione (jest opt-in, bo wolne).

**Dlaczego to ważne.** Bez tekstu zdjęcia porównują się percepcyjnie (`perceptual_hash`,
6 910 plików), więc dwie białe kartki są „podobne”, choć dotyczą różnych rzeczy.

**Jak.** Przebieg `just extract --ocr-images` na obrazach (oszacować czas na próbce),
potem ponowne liczenie relacji. Warto rozważyć próg: OCR tylko dla obrazów powyżej
pewnego rozmiaru i z dużą ilością krawędzi (skan kartki), a nie dla memów.

- [ ] pomiar czasu OCR na próbce 50 obrazów
- [ ] przebieg na całości + relacje policzone ponownie
- [ ] near-dupe dla obrazów: wymagaj zgodności tekstu, nie tylko pikseli

---

## Q6. Łączenie po treści i po kontekście, nie po pikselach

**Stan.** Relacje liczy `near_dupe.py` z podpisów treści; ścieżka źródłowa nie jest
dziś sygnałem.

**Jak.** Dołożyć sygnał kontekstu: wspólny katalog-liść (`kol1/`, `lab_05/`) podnosi
pewność relacji i grupuje pliki jako „ten sam materiał”. To jest tania i mocna
przesłanka — katalog już niesie decyzję człowieka sprzed lat.

- [ ] sygnał „wspólny katalog” w `near_dupe`
- [ ] próg: katalog + zgodny tekst = `near_duplicate`; sam katalog = `related`

---

## Q7. Ten sam hash, inna nazwa

**Stan — to już działa.** Plik jest adresowany `sha256`, więc dwie kopie o różnych
nazwach to **jedna treść** z dwiema pozycjami w prowenancji. W bazie jest **613** treści
mających więcej niż jedną nazwę (rekordzista: 81 różnych nazw).

**Czego brakuje.** Widać to dopiero po wejściu w notatkę. Przydałoby się:

- [ ] w kolejce decyzji: „ta treść występuje pod 3 nazwami” + lista
- [ ] podpowiedź wyboru najlepszej nazwy (najdłuższa sensowna, bez `(1)`, `kopia`)

---

## Q8. Metadane plików

**Stan — sprawdzone na próbce 400 obrazów: EXIF praktycznie nie istnieje.** Tylko 5
plików ma jakikolwiek EXIF, **ani jeden nie ma daty**. Zdjęcia przeszły przez
komunikatory, które metadane czyszczą. Za to `modified_date` mamy dla **48 049 z 48 049**
plików.

**Wniosek.** Grupowanie „ten sam aparat, ten sam dzień” odpada. Zostaje data modyfikacji
i katalog — i to katalog jest mocniejszy (patrz Q6).

- [ ] grupowanie „zrobione tego samego dnia w tym samym katalogu” jako podpowiedź w klastrach

---

## Q9. Głębszy poziom w grafie: konkretne kolokwium / laboratorium

**Stan.** Hierarchia kończy się na kategorii: `semestr → przedmiot → kategoria → plik`.
Pliki jednej labki leżą obok siebie, ale nic nie mówi, że należą do `lab_05`.

**Jak.** Dołożyć poziom z katalogu-liścia ścieżki źródłowej (`lab_05`, `kol1`) jako
węzeł między kategorią a plikami — tak samo jak kategorię dołożyliśmy między przedmiot
a pliki. Tam, gdzie katalogu nie ma, pliki wiszą bezpośrednio na kategorii.

- [ ] węzeł `group` w eksporcie (tylko gdy katalog-liść jest wspólny dla ≥2 plików)
- [ ] czwarty poziom w wyborze zakresu w viewerze
