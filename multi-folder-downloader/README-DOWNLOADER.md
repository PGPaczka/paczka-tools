# Paczka Drive Downloader

Narzędzie do rekurencyjnego pobierania dużego, publicznie dostępnego drzewa Google Drive z zachowaniem oryginalnej struktury katalogów. Ma trwały checkpoint w SQLite (wznawianie po przerwaniu), równoległych workerów, live dashboard w terminalu, retry z backoffem, wspólny globalny cooldown przy throttlingu Google oraz obsługę plików Google Docs/Sheets/Slides (przez eksport).

Przeznaczone dla WSL / Linux i Pythona 3.

Wszystko — skrypty, konfiguracja, docsy i dane SQLite — mieszka w tym katalogu (`multi-folder-downloader/`), obok repo. Jedyny wyjątek to sam output pobierania (`00_SOURCES/`), który celowo zostaje katalog wyżej — patrz [Struktura projektu](#struktura-projektu).

Główne pliki:

```text
download_drive_dashboard_sqlite.py   # główny downloader + dashboard
diag_drive.py                        # diagnostyka (folder / plik / native) po linku
.gitignore
cookies/
└── cookie_header_to_txt.py          # nagłówek cookie z DevTools -> cookies.txt
state/                                # tworzone automatycznie, checkpoint SQLite
```

Wszystkie komendy poniżej zakładają, że jesteś w `multi-folder-downloader/` (`cd multi-folder-downloader`).

---

## Model działania (ważne)

Skrypt używa dwóch różnych ścieżek dostępu do Google — i to celowo:

- **Listowanie folderów** (`embeddedfolderview`) jest **anonimowe**. Dla publicznego folderu ten endpoint działa bez logowania; jeśli wyślesz do niego cookies, Google odbija żądanie na stronę logowania i zwraca pustkę (folder zostałby błędnie zapisany jako pusty). Dlatego listowanie NIGDY nie używa cookies.
- **Pobieranie plików** używa `gdown` z UA przeglądarki, a przy `--cookies` również z Twoją zalogowaną sesją. Uwierzytelnienie mocno podnosi limity i jest wymagane m.in. dla plików native.
- **Pliki native** (Docs/Sheets/Slides) pobierane są przez bezpośredni endpoint eksportu (`.../export?format=docx|xlsx|pptx`), a nie przez `uc?id=`.

---

## Wymagania

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip

python3 -m venv ~/.venvs/gdown
source ~/.venvs/gdown/bin/activate

python -m pip install -U pip
python -m pip install -U 'gdown>=6.2,<7' rich beautifulsoup4 requests
```

Skrypt korzysta z prywatnych elementów API `gdown 6.x` i wymaga co najmniej **gdown 6.2.0** (wtedy dodano callback `progress=` do live postępu). Wersja jest przypięta do `>=6.2,<7`.

Opcjonalnie do przeglądania checkpointu:

```bash
sudo apt install -y sqlite3
```

---

## Szybki start

Adres źródłowego folderu jest **wymagany** (`--url`). Domyślny katalog wyjściowy to `00_SOURCES/` utworzony o poziom **wyżej** niż skrypt (tworzony automatycznie).

```bash
source ~/.venvs/gdown/bin/activate

python download_drive_dashboard_sqlite.py \
  --url 'https://drive.google.com/drive/folders/ID_FOLDERU' \
  --workers 4
```

Po `Ctrl+C`, zamknięciu terminala lub restarcie WSL uruchom dokładnie tę samą komendę — skrypt wznowi pracę z SQLite.

---

## Uwierzytelnienie (cookies)

Potrzebne, gdy Google throttluje pobieranie (błąd „Cannot retrieve file url / many accesses") albo dla plików native. Uzyskasz je bez instalowania żadnego rozszerzenia. Wszystko lądujące tutaj — sam skrypt konwertujący i wynikowy `cookies.txt` — mieszka w podkatalogu `cookies/`:

1. Wejdź na `drive.google.com` **zalogowany** (nie incognito). Otwórz DevTools (F12) → zakładka **Network** → kliknij dowolny request do `drive.google.com` → sekcja **Request Headers** → skopiuj całą wartość nagłówka `cookie:`.
2. Zamień nagłówek na plik `cookies/cookies.txt`:

   ```bash
   python cookies/cookie_header_to_txt.py
   # ...wklej nagłówek i naciśnij Enter
   ```

   Bez `-o` skrypt zapisuje zawsze obok siebie, czyli w `cookies/cookies.txt`, niezależnie z jakiego katalogu go uruchomisz.

3. Uruchom pobieranie — **`--cookies` nie jest już potrzebne**, `download_drive_dashboard_sqlite.py` sam wykrywa i używa `cookies/cookies.txt`, jeśli ten plik istnieje:

   ```bash
   python download_drive_dashboard_sqlite.py \
     --url 'https://drive.google.com/drive/folders/ID_FOLDERU' \
     --workers 2
   ```

   Żeby wskazać inny plik (np. inne konto), nadal możesz podać `--cookies /inna/sciezka/cookies.txt` jawnie — jawna flaga zawsze wygrywa z auto-wykrywaniem.

Uwagi:

- Plik `cookies/cookies.txt` to praktycznie hasło do Twojego konta — jest w `.gitignore`, dostaje uprawnienia `600`, nie udostępniaj go.
- Cookies wygasają (dni–tygodnie, część rotuje szybciej). Gdy znów zacznie sypać mimo działającej przeglądarki — wygeneruj `cookies/cookies.txt` na nowo (nadpisze poprzedni).
- Cookies dotyczą tylko **pobierania**. Listowanie i tak jest anonimowe.

---

## Diagnostyka: `diag_drive.py`

Jeden skrypt do sprawdzenia, co Google naprawdę zwraca dla danego celu. Typ (folder / plik / native) jest wykrywany automatycznie z linku; można wymusić `--type`.

Podobnie jak główny downloader, `diag_drive.py` sam wykrywa `cookies/cookies.txt`, jeśli plik tam jest — nie trzeba podawać `--cookies` ręcznie:

```bash
# folder (listowanie – zawsze anonimowo)
python diag_drive.py 'https://drive.google.com/drive/folders/ID'

# plik (cookies wykrywane automatycznie z cookies/cookies.txt)
python diag_drive.py 'https://drive.google.com/uc?id=ID'

# native – test eksportu
python diag_drive.py 'https://docs.google.com/document/d/ID/edit'

# samo ID / open?id – typ nieznany, skrypt sam sprawdzi
python diag_drive.py ID

# inny plik cookies niż domyślny
python diag_drive.py 'https://drive.google.com/uc?id=ID' --cookies /inna/sciezka/cookies.txt

# porównanie bez UA przeglądarki
python diag_drive.py 'https://drive.google.com/uc?id=ID' --no-ua
```

Pełna pomoc: `python diag_drive.py --help`.

---

## Dashboard

Cztery sekcje:

1. **ODKRYTE DOTYCHCZAS** — skumulowane liczniki z SQLite (foldery/pliki odkryte i obsłużone, pasek postępu, global backoff). Mianowniki rosną w trakcie traversalu — to NIE jest finalna liczba.
2. **TA SESJA** — liczniki tylko dla bieżącego procesu: pobrane pliki/bajty, prędkość, pominięte, foldery traversowane/wznowione, retry, fails w sesji, `throttling/min` oraz `Global backoff` z powodem.
   - `throttling/min (60s)` = liczba transient-retry z backoffem w ostatnich 60 s. Rośnie, gdy Google ogranicza ruch → rozważ mniej `--workers`. (Lepszy sygnał niż `fail/min`, który liczy tylko permanentne faile.)
3. **Workery** — na worker: status, folder, postęp folderu, plik, postęp pliku, **Ostatni błąd** (na czym worker robi retry) i czas.
4. **Aktywne drzewo** — odkryta struktura z symbolami: `✓` gotowe, `…` pending, `↻` traversowanie, `⬇` pobieranie, `✗` fail, `⟳` cykl, `◌` częściowo.

Fullscreen jest domyślny (mniej migania w Windows Terminal/WSL). `--inline-dashboard` przełącza na tryb inline, `--dashboard-refresh` ustawia maksymalną liczbę odświeżeń/s.

---

## Retry, backoff i globalny cooldown

Domyślnie `--retries 6`, `--backoff 2`, `--max-backoff 300`. Opóźnienia rosną wykładniczo (2, 4, 8, 16, 32, 64, … s) i są przycinane do `--max-backoff`. Uwaga: przy domyślnych `--retries 6` sekwencja dochodzi tylko do ~32 s, więc `--max-backoff` ma znaczenie dopiero przy większej liczbie prób (np. `--retries 9`).

Błędy wyglądające na throttling Google (429/500/502/503/504, „too many users", „many accesses", timeouty itd.) ustawiają **wspólny cooldown** — inne workery przed kolejnym NOWYM requestem respektują ten sam deadline. Trwające pobrania nie są przerywane.

---

## SQLite, wznawianie i tryby napraw

Domyślna baza: `state/download_state.sqlite`, w podkatalogu obok skryptu (czyli w `multi-folder-downloader/state/`, nie w `00_SOURCES/`). Statusy folderów: `pending, listing, listed, processing, done, failed, cycle`. Statusy plików: `pending, downloading, done, skipped, failed`.

Tryby uruchomienia:

```bash
# ponów permanentne faile (foldery i pliki oznaczone jako failed)
python download_drive_dashboard_sqlite.py --url '...' --retry-failed

# przeliste foldery błędnie zapisane jako puste (child_count = 0)
python download_drive_dashboard_sqlite.py --url '...' --relist-empty

# skasuj checkpoint i zbuduj indeks od nowa (nie usuwa 00_SOURCES/)
python download_drive_dashboard_sqlite.py --url '...' --reset-state
```

Podgląd stanu:

```bash
sqlite3 state/download_state.sqlite "SELECT status, COUNT(*) FROM files GROUP BY status;"
sqlite3 state/download_state.sqlite "SELECT status, COUNT(*) FROM folders GROUP BY status;"
sqlite3 state/download_state.sqlite "SELECT COUNT(*) FROM folders WHERE status='done' AND child_count=0;"
```

---

## Rozwiązywanie problemów

**„Cannot retrieve file url … many accesses / check permissions" na WSZYSTKICH plikach, choć w przeglądarce działa.** To throttling anonimowego endpointu Twojego IP. Rozwiązanie: wygeneruj `cookies/cookies.txt` (patrz wyżej — zostanie wykryty automatycznie) i/lub mniej workerów, ewentualnie odczekanie, aż IP ostygnie. Potwierdzenie: `diag_drive.py <link_pliku>` — jeśli zwróci PLIK, cookies załatwiają sprawę; dołóż też UA (skrypt robi to automatycznie).

**Ten sam błąd tylko na plikach, gdzie `open?id=` działa, a `uc?id=` nie.** To plik **native** (Docs/Sheets/Slides). Skrypt pobiera je przez eksport automatycznie; jeśli mimo to failuje, sprawdź `diag_drive.py <link> --type doc|sheet|slide`.

**Foldery lokalnie puste, choć na Drive mają zawartość.** Zostały wylistowane jako puste — najczęściej dlatego, że listowanie dostało stronę logowania (np. gdy wcześniej wysyłano cookies do listowania) albo throttling. Napraw: `--relist-empty`. Potwierdzenie: `diag_drive.py <link_folderu>` (bez cookies) powinno pokazać `RAZEM > 0`.

**Twardy limit per-plik („download quota exceeded").** Dotyczy konkretnego pliku i resetuje się ~24 h. Cookies tego nie obejdą — pomaga kopia pliku na własny Drive i pobranie kopii, albo odczekanie doby.

**Za dużo 429/500 / rośnie `throttling/min`.** Zejdź na `--workers 2` lub `1`. Więcej workerów nie zawsze znaczy szybciej.

---

## Parametry CLI

Pełna pomoc: `python download_drive_dashboard_sqlite.py --help`.

```text
--url URL              (WYMAGANE) URL lub ID root folderu Google Drive.
--output PATH          Katalog wyjściowy. Domyślnie: ../00_SOURCES względem skryptu.
--workers N            Liczba równoległych workerów (domyślnie 4).
--retries N            Maks. prób na listing folderu lub pobranie pliku (6).
--backoff SECONDS      Bazowe opóźnienie exponential backoff (2.0).
--max-backoff SECONDS  Górny limit pojedynczego opóźnienia (300).
--listing-timeout SEC  Timeout jednego requestu listującego folder (90).
--cookies PATH         Netscape cookies.txt (uwierzytelnione pobieranie).
                       Domyślnie: cookies/cookies.txt obok skryptu, jeśli istnieje.
--use-cookies          Użyj własnego cache cookies gdown (~/.cache/gdown).
--dashboard-refresh N  Maks. odświeżeń dashboardu na sekundę (5).
--inline-dashboard     Dashboard inline zamiast alternate-screen.
--state-db PATH        Niestandardowa ścieżka do SQLite checkpointu.
                       Domyślnie: state/download_state.sqlite obok skryptu.
--retry-failed         Ponów elementy oznaczone jako failed.
--relist-empty         Przeliste foldery zapisane jako puste (child_count=0).
--reset-state          Skasuj checkpoint i zbuduj indeks od nowa.
```

---

## Struktura projektu

```text
<root>/                              # np. PaczkaMerge/
├── .gitignore                       # tylko uniwersalne rzeczy (Python/edytor/system) + 00_SOURCES/
├── 00_SOURCES/                      # pobrane materiały (domyślny output, katalog wyżej niż skrypty)
└── multi-folder-downloader/         # skrypty, konfiguracja, docsy i dane SQLite — wszystko razem
    ├── download_drive_dashboard_sqlite.py
    ├── diag_drive.py
    ├── README-DOWNLOADER.md
    ├── .gitignore                   # pełny, samodzielny — sekrety/dane/śmieci tego katalogu
    ├── cookies/                     # skrypt + pliki cookies, osobno od reszty
    │   ├── cookie_header_to_txt.py
    │   ├── cookies.txt              # sekret, lokalny, gitignored
    │   └── header.txt               # opcjonalny input do cookie_header_to_txt.py, gitignored
    ├── state/                       # checkpoint SQLite, osobno od reszty
    │   └── download_state.sqlite
    ├── .paczka_download_tmp/        # tymczasowe pliki pobierania
    └── _download_logs/
        └── YYYYMMDD_HHMMSS/
            ├── run.log
            ├── failures.csv
            └── summary.json
```

`00_SOURCES/` powstaje o poziom wyżej niż skrypty (czyli w `<root>/`), bo to duży zbiór pobranych materiałów, osobny od narzędzia, które go tworzy. Wszystko inne — konfiguracja, cookies, checkpoint SQLite, logi, tymczasowe pliki — zostaje w `multi-folder-downloader/`, każde w swoim podkatalogu. Jeśli chcesz inny układ, wskaż `--output`, `--cookies` i/lub `--state-db` jawnie.

---

## Bezpieczeństwo i git

Repo ma dwa poziomy `.gitignore`:

- `<root>/.gitignore` — tylko uniwersalne, generyczne wzorce (śmieci Pythona, edytora, systemu) plus `00_SOURCES/`, bo ten katalog fizycznie siedzi w rootcie i musi być tam zignorowany.
- `multi-folder-downloader/.gitignore` — pełna, samodzielna kopia ignorująca wszystko specyficzne dla tego narzędzia: `cookies/cookies.txt`, `cookies/header.txt`, `credentials.json`, `token.json`, `state/download_state.sqlite*`, `_download_logs/`, `.paczka_download_tmp/` oraz też śmieci Pythona/edytora (żeby ten katalog działał samodzielnie, nawet gdybyś przeniósł go do innego repo).

Nigdy nie commituj cookies ani pobranych materiałów.

---

## Znane ograniczenia

1. Opiera się na nieoficjalnym publicznym widoku folderów (`embeddedfolderview`) oraz prywatnych elementach API `gdown 6.x` — Google lub `gdown` mogą zmienić zachowanie.
2. Pełna liczba folderów/plików nie jest znana przed końcem traversalu (dashboard pokazuje „odkryte dotychczas").
3. Publiczny dostęp do root nie gwarantuje dostępu do każdego celu skrótu; foldery wymagające dostępu Twojego konta mogą nie listować się przez `embeddedfolderview`.
4. `done`/`skipped` opiera się na checkpoincie i obecności pliku lokalnie — brak kryptograficznej walidacji zawartości.
