# Testy: pięć warstw i po co każda z nich

Co sprawdza każda warstwa testów organizera, dlaczego akurat ten podział i co
świadomie zostało poza nim.

Zasada nadrzędna: **jeśli coś nie działa, test ma być czerwony.** Nie łagodzimy
asercji, żeby przeszła — naprawiamy to, co ją psuje. Pominięcie (`skip`) jest
dozwolone wyłącznie przy braku lokalnych DANYCH, nigdy przy braku sprawności.

| Warstwa | Marker | Co sprawdza | Kiedy czerwona |
|---|---|---|---|
| Kontrakt kodu | *(brak)* | logika na atrapach, `tmp_path`, deterministycznie | błąd w logice |
| Środowisko | `environment` | realne biblioteki i binarki, wersje minimalne | brak/zepsuta zależność |
| Kontrakt CLI | `cli_contract` | argv backendów AI kontra parser prawdziwego CLI | zła albo źle umieszczona flaga |
| E2E | `e2e` | cały łańcuch etapów na syntetycznej paczce | rozjazd styku między skryptami |
| Sonda | `probe` | realny STAN: spójność indeksu, niezmienność źródeł, `target_repo` | naruszony niezmiennik; brak danych = skip |
| Własności | *(brak)* | granica ścieżek dla KAŻDEGO wejścia (Hypothesis) | wejście, które ucieka poza korzeń |
| Mutacyjna | *(osobno)* | czy testy w ogóle coś łapią (`tests/mutations/*.yaml`) | kontrakt przestał być pilnowany |

```bash
just test        # wszystko (~35 s)
just test-fast   # sam kontrakt kodu, do pętli edycja-test
just env-check   # realne zależności
just cli-check   # zgodność z zewnętrznymi CLI (bez promptów, bez kosztu)
just e2e         # pełny łańcuch na syntetycznej paczce
just probe       # sondy na Twoich realnych danych
just index-check # spójność operacyjnego indeksu (kontrola STANU, nie kodu)
just sources-check # czy źródła są nadal takie, jakie zapisał skan
just mutate-check  # psuje kopię repo i sprawdza, czy testy robią się czerwone
```

Dwie ostatnie recepty nie są testami kodu — sprawdzają **stan** dwóch rzeczy,
których nie da się odtworzyć tanio: `organizer.sqlite` (budowany przyrostowo
przez wiele przebiegów) i `00_SOURCES`. Guard w hookach pilnuje *zamiaru*
(blokuje komendę), `sources-check` sprawdza *skutek* — także zmiany wprowadzone
poza agentami. Obie kontrole czytają bazę w trybie `mode=ro` i kończą kodem 1,
gdy znajdą naruszenie; pełny przebieg na 48 tys. plików trwa poniżej 2 s.

Każda z tych warstw powstała po konkretnej wpadce, nie „na zapas":

- **środowisko** — `catdoc` zwracał polskie znaki jako krzaki (cp1252 zamiast
  cp1250), a testy z atrapą nie miały prawa tego pokazać;
- **kontrakt CLI** — backend budował `codex --ignore-user-config exec …`, czego
  prawdziwe CLI nie przyjmowało; backend nigdy nie zadziałał end-to-end przy
  komplecie zielonych testów;
- **e2e** — `text_head` z etapu extract musi dotrzeć do manifestu, inaczej
  klasyfikator AI widzi samą nazwę pliku; żaden test pojedynczego etapu tego
  styku nie obejmował.

Testy z atrapami i testy realnego środowiska **celowo się uzupełniają**: pierwsze
mówią, co kod zamierza zrobić, drugie — czy narzędzie faktycznie to przyjmuje.
Listy kontraktowe (słowa mutujące w guardzie, formaty, backendy) są w testach
wypisane **wprost**, a nie czytane z implementacji: parametryzacja po liście
z kodu jest pusta, bo jej skrócenie skraca też zestaw przypadków.

Nowe zależności i nowe zewnętrzne narzędzia dopisuj razem z kontrolą w warstwie
`environment` albo `cli_contract` — i sprawdź mutacyjnie, że po ich usunięciu
testy naprawdę czerwienieją.

`just mutate-check` to odpowiedź na pytanie „czy te testy cokolwiek dają". Każdy
plik w `tests/mutations/` psuje jedno zachowanie produkcyjne i wymaga, żeby testy
to wyłapały; wynik `PRZEPUSZCZONE` oznacza dziurę w pokryciu, nie awarię kodu.
Dopisując kontrakt wart pilnowania, dopisz tam mutację — raz udowodniony kontrakt
daje się wtedy powtórzyć bez pamiętania, co dokładnie się psuło.

Nazwy plików i katalogów mają własny zestaw (`tests/unit/test_special_names.py`)
zbudowany na **zmierzonym** rozkładzie źródeł, nie na wyobrażeniu o nim: 98%
plików ma spację, 38% nawias, 63% polskie znaki, a dwa zaczynają się od myślnika.

Świadomie **nie** ma tu: progu pokrycia (mierzy wykonane linie, nie to, czy
asercje cokolwiek znaczą — 615 zielonych testów przy niepilnowanej serializacji
hashy jest tego dowodem), snapshotów generowanych raportów (nie wchodzą do
gita — patrz `reports/README.md`, kolumna „W repo”), benchmarków (etapy uruchamiane ręcznie i rzadko) ani
testów chaosu (WAL i transakcje partiami już to trzymają).

Konfiguracja pytesta (markery, `testpaths`, `pythonpath`) jest w `pyproject.toml`,
sekcja `[tool.pytest.ini_options]`. Pliki testów leżą w pięciu katalogach pod
`tests/`: `unit/` (kontrakt kodu + środowisko + własności), `cli/` (kontrakt CLI),
`e2e/` (cały łańcuch), `studio/` (API i front studia) i `synapse/` (eksport grafu);
obok nich `tests/mutations/` (YAML-e dla `mutate-check`) i `tests/fixtures/`
(dane wejściowe współdzielone przez testy).
