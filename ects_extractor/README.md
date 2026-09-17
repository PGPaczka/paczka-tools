# ECTS extractor

Starsze skrypty do pobrania planu studiów i utworzenia katalogów przedmiotów.

## Układ

- `extract_classes_info.sh` — pobiera XLS i przetwarza go na listę przedmiotów.
- `create_classes_stucture.sh` — tworzy katalogi z podanej listy.
- `data/subjects_formatted.txt` — wersjonowana lista przedmiotów; wynik ekstrakcji.
- `tests/` — test ścieżki wyniku bez sieci (atrapy `curl` i `ssconvert`).

## Ekstrakcja

Wymagane: Bash, `curl`, `ssconvert` (Gnumeric) i GNU awk z obsługą `FPAT`.
Z katalogu tego narzędzia:

```bash
bash extract_classes_info.sh
```

Wynik zawsze trafia do `data/subjects_formatted.txt` obok skryptu,
niezależnie od katalogu uruchomienia. Skrypt nadpisuje tę listę; pliki robocze
`struktura.xls` i `struktura.csv` powstają w bieżącym katalogu.

## Generator struktury — uwaga na katalog docelowy

`create_classes_stucture.sh` przyjmuje ścieżkę listy jako pierwszy argument
(obecnie `data/subjects_formatted.txt`). Ma jednak historyczną, stałą ścieżkę
wyjściową `main_dir="../../../"`, liczoną od **katalogu uruchomienia**.
Przed użyciem ustaw ją w skrypcie na osobny katalog roboczy.

Nie uruchamiaj generatora na kanonicznej paczce ani na `00_SOURCES`.
Historyczne nazwy katalogów nie są kontraktem współczesnego organizera;
aktualna konfiguracja jest w `../organizer/config/`.

## Test lokalny

```bash
python3 -m unittest discover -s tests -v
```

Wymaga Bash i GNU awk, ale nie łączy się z ECTS, nie wymaga `ssconvert`
i nie nadpisuje wersjonowanej listy przedmiotów.
