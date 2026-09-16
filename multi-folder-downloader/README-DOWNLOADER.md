# Paczka Drive Downloader

Narzędzie do rekurencyjnego pobierania dużego, publicznie dostępnego drzewa Google Drive z zachowaniem oryginalnej struktury katalogów.

Skrypt jest przygotowany pod przypadek, w którym źródłowy folder zawiera dużo zagnieżdżonych folderów, skrótów do folderów, zwykłych plików oraz plików Google Docs / Sheets / Slides, a jednorazowe pobranie przez przeglądarkę lub standardowe `gdown --folder` jest zbyt wolne albo przerywa się na pojedynczym błędzie HTTP 500.

Główny plik:

```text
download_drive_dashboard_sqlite.py
```

Domyślne źródło:

```text
https://drive.google.com/drive/folders/18mN48s232REZ1NAcQC9Lkm4uEBQ5yKK3
```

Domyślny katalog docelowy:

```text
/home/billy/dev/paczka/PaczkaMerge/00_SOURCES
```

> **Ważne:** liczniki w dashboardzie opisane jako **„odkryte”** oznaczają tylko elementy znalezione do tej pory. Dopóki traversal drzewa Google Drive się nie zakończy, nie jest znana ostateczna liczba folderów ani plików.

---

## Najważniejsze funkcje

- zachowanie zagnieżdżonej struktury katalogów Google Drive,
- równoległa praca kilku workerów,
- live dashboard w terminalu przez `rich`,
- bieżący status każdego workera,
- postęp folderu `n/N`,
- postęp konkretnego pliku, np. `38.2 MiB / 91.4 MiB (41%)`,
- wizualizacja aktywnych workerów w drzewie,
- retry z exponential backoff,
- wspólny globalny cooldown po błędach wskazujących na throttling Google,
- trwały checkpoint w SQLite,
- wznowienie po `Ctrl+C`, zamknięciu terminala lub restarcie WSL,
- osobne logowanie permanentnych faili,
- końcowe statystyki,
- obsługa Google Docs / Sheets / Slides przez eksport wykonywany przez `gdown`,
- wykrywanie cykli folderów / shortcutów,
- pomijanie poprawnie pobranych wcześniej plików.

---

## Wymagania

Skrypt jest przeznaczony dla WSL / Linux i Pythona 3.

Zalecane jest osobne virtualenv:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip

python3 -m venv ~/.venvs/gdown
source ~/.venvs/gdown/bin/activate

python -m pip install -U pip
python -m pip install -U 'gdown>=6.1,<7' rich beautifulsoup4
```

Skrypt korzysta z prywatnych elementów API `gdown 6.x`, dlatego wersja główna jest celowo przypięta do `6.x`.

Jeżeli chcesz przeglądać bazę checkpointu z terminala:

```bash
sudo apt install -y sqlite3
```

---

## Uruchomienie

Przejdź do projektu:

```bash
cd /home/billy/dev/paczka/PaczkaMerge
source ~/.venvs/gdown/bin/activate
```

Standardowe uruchomienie:

```bash
python download_drive_dashboard_sqlite.py
```

Jawnie z czterema workerami:

```bash
python download_drive_dashboard_sqlite.py \
  --workers 4 \
  --retries 6
```

Dla obecnego źródła i outputu nie trzeba podawać `--url` ani `--output`, ponieważ są ustawione jako wartości domyślne w skrypcie.

---

## Zalecana liczba workerów

Punkt startowy:

```text
4 workery
```

To kompromis między szybkością a ryzykiem throttlingu / niestabilności endpointów Google Drive.

Jeżeli zaczyna pojawiać się dużo HTTP `429`, `500`, `502`, `503`, `504` albo timeoutów, spróbuj:

```bash
python download_drive_dashboard_sqlite.py --workers 2
```

lub:

```bash
python download_drive_dashboard_sqlite.py --workers 3
```

Jeżeli przez długi czas wszystko działa stabilnie, można eksperymentalnie spróbować `5-6`, ale zwiększanie liczby workerów nie musi przyspieszać pobierania. Google może zacząć mocniej ograniczać ruch.

---

## Dashboard

Dashboard ma trzy główne sekcje.

### 1. Podsumowanie „ODKRYTE DOTYCHCZAS”

Przykład:

```text
ODKRYTE DOTYCHCZAS — to NIE jest finalna liczba; mianowniki rosną podczas traversalu

Czas: 53:02       Ukończone dane: 1.1 GiB
Fails: 97         fail/min (60s): 2
Global backoff: 3.8s

Foldery odkryte: 542
119 / 542 traversed

Pliki odkryte: 311
265 / 311 obsłużonych
```

`542 foldery` oraz `311 plików` to **nie jest liczba wszystkich elementów na Drive**. To liczba elementów odkrytych przez traversal do bieżącej chwili.

Przykładowo podczas działania może być:

```text
168 / 311
243 / 482
391 / 721
```

Dlatego procent może chwilowo spaść, gdy traversal odkryje dużą nową gałąź drzewa.

`fail/min (60s)` oznacza liczbę **nowych permanentnych faili** zarejestrowanych w ciągu ostatnich 60 sekund. Pojedynczy retry nie jest liczony jako fail, jeśli później element pobierze się poprawnie.

---

### 2. Workery

Kolumny są wyświetlane w kolejności:

```text
Worker | Status | Folder | Postęp folderu | Plik | Postęp pliku | Czas
```

Przykład:

```text
W2 | pobieranie 3/6 | SEM3/AiSD | 11/19 | projekt.zip | 42.7 MiB/91.3 MiB (46%) | 02:41
```

Znaczenie kolumn:

- **Worker** — numer workera,
- **Status** — np. `trawersowanie`, `pobieranie`, `retry`, `global backoff`, `FAILED`,
- **Folder** — aktualnie przetwarzany folder,
- **Postęp folderu** — liczba obsłużonych bezpośrednich elementów względem liczby odkrytych w tym folderze,
- **Plik** — aktualnie pobierany plik,
- **Postęp pliku** — pobrane bajty / całkowity rozmiar oraz procent, jeśli Google zwróci rozmiar,
- **Czas** — czas bieżącej operacji workera; przy traversalu jest to czas aktualnego folderu, a przy downloadzie czas aktualnego pliku. Retry i backoff wliczają się do czasu.

---

### 3. Aktywne drzewo

Przykład:

```text
00_SOURCES/
├── ✓ SEM1
├── ◌ SEM2
│   ├── ↻ PO                 ← ↻ W1
│   └── ◌ AiSD               ← ⬇ W3
│       └── ⬇ W3 projekt.zip 42.7 MiB/91.3 MiB (46%)
└── … SEM3
```

Symbole:

```text
✓   folder zakończony
…   pending / jeszcze nieobsłużony
↻   worker aktualnie traversuje folder
⬇   worker pobiera plik z folderu
✗   permanentny fail
⟳   wykryty cykl shortcutów / folderów
◌   folder odkryty / częściowo przetworzony
```

Drzewo nie drukuje bez ograniczeń wszystkich plików i wszystkich gałęzi. Aktywne oraz problematyczne gałęzie są rozwijane, a nieaktywne fragmenty zwijane, aby dashboard pozostał czytelny również przy tysiącach elementów.

---

## Retry i exponential backoff

Domyślnie:

```text
--retries 6
--backoff 2
```

Kolejne opóźnienia mają charakter wykładniczy, mniej więcej:

```text
2 s
4 s
8 s
16 s
32 s
60 s
```

Dodawany jest niewielki losowy jitter, aby workery nie ponawiały requestów dokładnie w tej samej chwili.

Status pokazuje numer aktualnej próby, np.:

```text
pobieranie 1/6
retry 1/6
pobieranie 2/6
retry 2/6
...
```

### Globalny backoff

Przy błędach wyglądających na throttling / chwilowy problem Google, np.:

```text
429
500
502
503
504
timeout
rate limit
quota
```

worker może ustawić wspólny cooldown. Inne workery przed rozpoczęciem kolejnego requestu respektują ten sam deadline.

Dzięki temu nie występuje sytuacja, w której jeden worker dostał sygnał „zwolnij”, ale pozostałe trzy natychmiast wysyłają następne requesty.

Trwające już pobieranie nie jest z tego powodu sztucznie przerywane.

---

## SQLite i wznowienie

Domyślna baza checkpointu:

```text
/home/billy/dev/paczka/PaczkaMerge/download_state.sqlite
```

SQLite przechowuje informacje o odkrytych folderach i plikach oraz ich stanie.

Typowe statusy folderów:

```text
pending
listing
listed
processing
done
failed
cycle
```

Typowe statusy plików:

```text
pending
downloading
done
skipped
failed
```

### Co się dzieje po `Ctrl+C`?

Możesz przerwać program:

```text
Ctrl+C
```

Następnie uruchomić dokładnie to samo:

```bash
python download_drive_dashboard_sqlite.py
```

Skrypt odczyta `download_state.sqlite` i wznowi pracę.

Foldery, których listing został już poprawnie zapisany do SQLite, **nie powinny być ponownie traversowane** tylko dlatego, że program został zrestartowany.

Jeżeli przerwanie nastąpiło dokładnie w trakcie pobierania listingu pojedynczego folderu przed zatwierdzeniem checkpointu, ten jeden folder może zostać odczytany ponownie.

Pliki częściowo pobrane są uruchamiane z `resume=True`; tam, gdzie `gdown` może wykorzystać plik `.part`, transfer będzie kontynuowany.

---

## Ponowienie permanentnych faili

Standardowe ponowne uruchomienie nie próbuje w nieskończoność elementów oznaczonych jako `failed`.

Aby ponownie otworzyć failed foldery i pliki:

```bash
python download_drive_dashboard_sqlite.py --retry-failed
```

---

## Reset checkpointu

Aby usunąć stan traversalu i zbudować indeks od nowa:

```bash
python download_drive_dashboard_sqlite.py --reset-state
```

Ta opcja usuwa checkpoint SQLite, ale nie usuwa katalogu `00_SOURCES`.

Istniejące lokalne pliki są przy ponownym odkryciu pomijane, jeżeli wyglądają na już pobrane.

Ręczne usunięcie checkpointu:

```bash
rm -f \
  /home/billy/dev/paczka/PaczkaMerge/download_state.sqlite \
  /home/billy/dev/paczka/PaczkaMerge/download_state.sqlite-wal \
  /home/billy/dev/paczka/PaczkaMerge/download_state.sqlite-shm
```

---

## Logi

Każde uruchomienie dostaje osobny katalog, np.:

```text
/home/billy/dev/paczka/PaczkaMerge/_download_logs/20260915_215423/
```

W środku znajdują się m.in.:

```text
run.log
failures.csv
summary.json
```

`failures.csv` zawiera m.in.:

```text
kind
full_path
parent_folder
drive_id
url
attempts
error
```

Dzięki temu można ustalić pełną lokalną ścieżkę elementu, Drive ID, bezpośredni link i ostatni błąd.

SQLite pozostaje źródłem prawdy dla checkpointu również wtedy, gdy program został zakończony zanim zdążył zapisać końcowy raport CSV.

---

## Podgląd faili bezpośrednio w SQLite

Instalacja CLI:

```bash
sudo apt install -y sqlite3
```

Otwórz bazę:

```bash
sqlite3 /home/billy/dev/paczka/PaczkaMerge/download_state.sqlite
```

W SQLite:

```sql
.headers on
.mode column
```

Wszystkie failed foldery i pliki razem z linkiem do Drive:

```sql
SELECT
    'folder' AS type,
    status,
    local_path AS path,
    drive_id,
    'https://drive.google.com/drive/folders/' || drive_id AS url,
    attempts,
    last_error AS error
FROM folders
WHERE status IN ('failed', 'cycle')

UNION ALL

SELECT
    'file' AS type,
    status,
    local_path AS path,
    drive_id,
    'https://drive.google.com/open?id=' || drive_id AS url,
    attempts,
    last_error AS error
FROM files
WHERE status = 'failed'

ORDER BY path;
```

Wyjście:

```text
.quit
```

---

## Przydatne zapytania SQLite

Liczba elementów według statusu:

```sql
SELECT status, COUNT(*)
FROM folders
GROUP BY status
ORDER BY status;

SELECT status, COUNT(*)
FROM files
GROUP BY status
ORDER BY status;
```

Liczba permanentnych faili:

```sql
SELECT 'folders' AS type, COUNT(*) AS failed
FROM folders
WHERE status = 'failed'

UNION ALL

SELECT 'files', COUNT(*)
FROM files
WHERE status = 'failed';
```

Pliki nadal oczekujące:

```sql
SELECT local_path, drive_id
FROM files
WHERE status = 'pending'
ORDER BY local_path;
```

Foldery nadal oczekujące na traversal:

```sql
SELECT local_path, drive_id
FROM folders
WHERE status = 'pending'
ORDER BY local_path;
```

---

## Parametry CLI

Pełna pomoc:

```bash
python download_drive_dashboard_sqlite.py --help
```

Najważniejsze opcje:

```text
--url URL
    URL albo ID root folderu Google Drive.

--output PATH
    Lokalny katalog wyjściowy.

--workers N
    Liczba równoległych workerów. Domyślnie 4.

--retries N
    Maksymalna liczba prób dla listingu folderu lub pobrania pliku.

--backoff SECONDS
    Bazowe opóźnienie exponential backoff.

--listing-timeout SECONDS
    Timeout jednego requestu listującego folder.

--state-db PATH
    Niestandardowa ścieżka do SQLite checkpointu.

--retry-failed
    Ponawia elementy wcześniej oznaczone jako failed.

--reset-state
    Kasuje stan traversalu i buduje indeks od nowa.
```

Przykład z innym źródłem i outputem:

```bash
python download_drive_dashboard_sqlite.py \
  --url 'https://drive.google.com/drive/folders/ID_FOLDERU' \
  --output '/home/billy/inny-folder' \
  --workers 3 \
  --retries 8 \
  --backoff 2
```

---

## Struktura danych lokalnie

Skrypt nie flattenuje drzewa. Przykładowo:

```text
Google Drive:

Wszystkie paczki/
├── SEM1/
│   └── Matematyka/
│       └── Wykłady/
│           └── wyklad1.pdf
└── SEM2/
    └── PO/
        └── lab.zip
```

lokalnie pozostaje:

```text
00_SOURCES/
├── SEM1/
│   └── Matematyka/
│       └── Wykłady/
│           └── wyklad1.pdf
└── SEM2/
    └── PO/
        └── lab.zip
```

Jeżeli Google Drive zawiera dwa elementy o identycznej nazwie w jednym folderze, kolejne egzemplarze dostają sufiks, np.:

```text
plik.pdf
plik__dup2.pdf
plik__dup3.pdf
```

To zapobiega nadpisaniu jednego pliku drugim na lokalnym filesystemie.

---

## Pliki Google Docs / Sheets / Slides

Pliki Google-native nie istnieją na Drive jako zwykłe binarne `.docx`, `.xlsx` czy `.pptx`. `gdown` eksportuje je podczas pobierania.

Typowy wynik:

```text
Google Docs   -> .docx
Google Sheets -> .xlsx
Google Slides -> .pptx
```

Niektóre mniej typowe pliki Google-native mogą zachowywać się inaczej zależnie od aktualnych możliwości `gdown` i endpointów Google.

---

## Publiczne uprawnienia

Ta konfiguracja bazuje na anonimowym dostępie do publicznie udostępnionych folderów / plików.

Jeżeli root folder jest publiczny, ale shortcut wskazuje do folderu, którego anonimowy użytkownik nie może otworzyć, ten fragment może zostać oznaczony jako failed.

Najprostszy test konkretnego folderu:

```bash
gdown \
  'https://drive.google.com/drive/folders/ID_FOLDERU' \
  -O '/tmp/gdown-test'
```

Jeżeli pojedynczy folder działa, ale duże drzewo sporadycznie zwraca HTTP 500, zwykle jest to chwilowy problem / throttling endpointu listującego, a nie problem z lokalnym katalogiem.

---

## Znane ograniczenia

1. Skrypt korzysta z nieoficjalnego publicznego widoku folderów Google Drive oraz z prywatnych elementów API `gdown 6.x`. Google lub `gdown` mogą w przyszłości zmienić zachowanie.
2. Nie znamy pełnej liczby folderów i plików przed zakończeniem traversalu, dlatego dashboard pokazuje **odkryte dotychczas**, nie finalny total.
3. Więcej workerów nie zawsze oznacza większą szybkość. Przy publicznym Google Drive agresywna równoległość może pogorszyć sytuację przez throttling.
4. Dostęp publiczny root folderu nie gwarantuje publicznego dostępu do każdego celu shortcutu.
5. `done` / `skipped` opiera się na checkpointach i obecności lokalnego pliku; skrypt nie wykonuje kryptograficznej walidacji zawartości każdego wcześniej pobranego pliku.

---

## Zalecany workflow

Pierwsze uruchomienie:

```bash
python download_drive_dashboard_sqlite.py --workers 4
```

Jeżeli Google zacznie mocno throttlowć:

```bash
python download_drive_dashboard_sqlite.py --workers 2
```

Po `Ctrl+C` albo restarcie WSL:

```bash
python download_drive_dashboard_sqlite.py --workers 4
```

Po zakończeniu głównej kolejki, aby ponowić permanentne błędy:

```bash
python download_drive_dashboard_sqlite.py \
  --workers 2 \
  --retry-failed
```

Następnie sprawdź:

```text
_download_logs/<timestamp>/failures.csv
_download_logs/<timestamp>/summary.json
```

oraz w razie potrzeby samą bazę:

```text
download_state.sqlite
```

---

## Pliki projektu

Docelowo wygodny układ katalogu może wyglądać tak:

```text
PaczkaMerge/
├── 00_SOURCES/
├── download_drive_dashboard_sqlite.py
├── download_state.sqlite
├── README.md
├── .paczka_download_tmp/
└── _download_logs/
    └── YYYYMMDD_HHMMSS/
        ├── run.log
        ├── failures.csv
        └── summary.json
```

`00_SOURCES` zawiera pobrane materiały, `download_state.sqlite` checkpoint, a `_download_logs` historię poszczególnych uruchomień.

