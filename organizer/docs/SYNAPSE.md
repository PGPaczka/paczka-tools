# Synapse × Paczka Organizer — kontrakt danych

Jak indeks organizera zamienia się w graf, który pokazuje **rodzaj** powiązania między
materiałami. Generator: `scripts/synapse_export.py` (`just synapse`), model:
`scripts/orglib/synapse_vault.py`, klon narzędzia: `vendor/synapse` (ignorowany w gicie).

## Czym jest synapse (i czym NIE jest lokalna kopia)

`Billypl/synapse` to **działająca aplikacja**: `Synapse.Generator` (.NET) skanuje katalog
notatek `.md`, czyta YAML front matter przez konfigurowalne mapowanie, rozwiązuje
`[[wikilinki]]` i buduje `graph.json`; `synapse-viewer` (Svelte) go wyświetla; `deploy/`
stawia to na RPi z regeneracją po `git push` na vault.

**Uwaga na pułapkę:** `~/dev/synapse` na tej maszynie to jeden commit z 2026-08-04 —
bundle z Claude Design sprzed implementacji, z danymi zaszytymi w `seedNotes()`.
Pierwsze podejście do C3 mapowało dane właśnie na niego i trafiło w próżnię (cofnięte
w `8fc5fb1`). **Kontrakt bierz z `vendor/synapse`, czyli z klona repo zdalnego.**

## Zmiany wprowadzone w synapse (gałąź `feat/paczka-integration`)

Krawędź umiała powiedzieć tylko, ŻE dwie notatki są połączone. Dodaliśmy:

| co | gdzie |
|---|---|
| `type` na węźle (wolny tekst) | `Domain/Graph/GraphNode.cs`, `ConfigurableFrontmatterMapper`, schemat |
| `kind` + `confidence` na krawędzi | `Domain/Graph/GraphEdge.cs`, `LinkResolver`, `JsonGraphSerializer` |
| `relations:` we front matterze | nowy parser listy map (stary `GetList()` robił `ToString()` na elementach) |
| `--no-git` / `skipGitHistory` | `Program.cs`, `GeneratorPipeline` |
| `schemaVersion` 2 | `schema/graph.schema.v2.json` + `graph-schema.md` |
| rysowanie krawędzi wg rodzaju, legenda, filtry typu i rodzaju, grupowanie w panelu | `synapse-viewer/src/**` |

Przy okazji naprawione **cudze, wcześniejsze usterki**: projekt testów generatora w ogóle
się nie kompilował (`pipeline.Run()` zwraca krotkę), a `GitHistoryReaderTests` porównywał
daty commitów z maszyny autora fixture'ów.

**2026-09-22 (`f84d116`) — deep link viewera nie działał wcale.** Otwarcie `/#<id notatki>`
nie zaznaczało niczego, również poza studiem: `selectedId.subscribe` odpala się raz przy
subskrypcji z wartością początkową (`null`), a handler traktował to jak nawigację i czyścił
hash (`history.replaceState(…, ' ')`) jeszcze zanim `onMount` zdążył go odczytać. Pierwsza
emisja store'a to stan, nie nawigacja — jest teraz pomijana. Bez tej poprawki nie działałaby
soczewka grafu w studiu (S4.1), bo to właśnie fragmentem URL-a studio mówi, który węzeł
zaznaczyć.

**Osadzenie w studiu (S4.1).** `just studio-graf` buduje viewer z `--base=/graf/`
(assety pod prefiksem, `/graph.json` i `/vault/...` zostają bezwzględne — serwuje je
backend studia prosto z `20_WORK`). Studio nie kopiuje vaulta do `public/`: notatki idą
z `work` przez helper containmentu. Tłumaczenie `sha256` ↔ `id` notatki: `orglib/graph_link.py`,
po kontrakcie `synapse_vault.ID_SHA_PREFIX` (id notatki pliku kończy się `sha256[:8]`).

**Znane, nierozstrzygnięte:** przy 4 317 węzłach viewer otwiera widok tak oddalony, że
węzły są pyłkami — tak samo w studiu i poza nim, więc to zachowanie renderera, nie osadzenia.

## Model: trzy typy węzłów

```
semester (7)  ←belongs_to—  subject (98)  ←belongs_to—  file (4 084)
                                                  ↕ near_duplicate / older_version
```

Relacja zawierania jest zapisywana **na dziecku** (`belongs_to`), nie na rodzicu: przedmiot
miewa tysiące plików, a jedna pozycja na notatkę trzyma front matter mały.

| pole | `semester` | `subject` | `file` |
|---|---|---|---|
| `id` = nazwa pliku | `sem3` | `sem3-ako` | `ako-{nazwa}-{sha8}` |
| `title` | `Semestr 3` | `AKO — Architektura Komputerów` | nazwa pliku źródłowego |
| `category` | `semestr` | `SEM1`…`SEM7` | kategoria z `syntax.yaml` |
| `level` | — | 1–3 wg stanu prac | 1 = w paczce · 2 = plan pewny · 3 = wymaga człowieka |
| `status` | zbiorczy | `completed`/`in-progress`/`not-started` | j.w. wg etapu potoku |
| `tags` | — | grupa, formy, katedra | `rodzaj-…`, `akcja-…`, `metoda-…`, `rok-…`, `w-paczce` |
| `relations` | — | `belongs_to` → semestr | `belongs_to` → przedmiot + relacje z B6 |

**Do grafu wchodzą tylko materiały z DECYZJĄ** (ground truth albo plan) — decyzja
użytkownika. Relacja do treści bez decyzji zostaje zapisana jako cel spoza vaulta, więc
generator robi z niej **ghost node**: „istnieje duplikat poza paczką” jest widoczne.
`--include-unassigned` zamienia te ghosty w zwykłe notatki.

## Twarde zasady kontraktu (łatwo złamać, trudno zauważyć)

1. **`id` to nazwa pliku**, nie pole front mattera, i musi być unikalne w całym vaulcie —
   kolizja daje ostrzeżenie `duplicate-id` i jedna z notatek przestaje być celem relacji.
2. **`status` tylko z `not-started` / `in-progress` / `completed`** — cokolwiek innego
   generator po cichu zamienia na `null`. Dlatego `Note.validate()` odrzuca to u nas.
3. **`level` musi być ≥ 1.** Viewer wylicza listę poziomów z danych (poprawione), ale
   schemat wymusza minimum.
4. **W treści notatki nie ma `[[wikilinków]]`** — wikilink tworzy krawędź rodzaju `link`,
   która zdublowałaby relację z front mattera. Nawigację po relacjach robi panel
   szczegółów, pogrupowany po rodzaju.
5. **Vault nie jest repozytorium gita** (decyzja użytkownika): to widok bieżącego stanu,
   nie historia zmian. Generator uruchamiaj z `--no-git`, inaczej wywoła `git log` raz na
   notatkę tylko po to, żeby dostać błąd. Skutek uboczny ich fallbacku: notatka z
   `modified` dostaje jednoelementową historię z tą datą, więc heatmapa nie jest pusta.

Wszystkie pięć jest pilnowanych testami, a punkty 1–2 i rodzaj relacji dodatkowo mutacjami.

## Jak to uruchomić

```bash
just synapse                      # sam vault w 20_WORK/synapse/vault (+ README obok)
just synapse --include-unassigned # razem z materiałem bez decyzji
just vendor-check                 # nasz vault przez PRAWDZIWY generator + walidacja schematem

just synapse-view                 # eksport + generator + notatki dla viewera, jedną komendą
cd vendor/synapse/synapse-viewer && npm install && npm run dev
```

`just synapse-view` robi trzy rzeczy: eksportuje vault, przepuszcza go przez generator do
`vendor/synapse/synapse-viewer/public/graph.json` i kopiuje same `.md` do `public/vault/`
— bez tej kopii panel szczegółów pokazuje sam wyciąg zamiast treści notatki.

Uwaga: generowanie do `public/graph.json` nadpisuje ich przykładowy graf w klonie.
To plik śledzony w tamtym repo — po zabawie `git -C vendor/synapse checkout -- synapse-viewer/public`.

## Zmierzone na realnych danych (2026-09-19)

4 189 węzłów (7 semestrów + 98 przedmiotów + 4 084 pliki), 5 469 krawędzi
(4 182 `belongs_to`, 1 183 `near_duplicate`, 104 `older_version`), 128 ghostów,
**0 ostrzeżeń, 0 sierot**, `graph.json` przechodzi walidację `graph.schema.v2.json`.
Generowanie vaulta i grafu: kilka sekund.

## Co się z tego realnie wyczytuje

Przejechane przeglądarką po całym vaulcie (2026-09-19). Pytania, które mają sens przy
pracy nad paczką, i sposób zadania ich w viewerze:

| Pytanie | Jak zapytać | Odpowiedź dziś |
|---|---|---|
| Co w tym przedmiocie czeka na moją decyzję? | Tagi `#ako` + `#do-przegladu`, tryb **all** | 69 plików w całej paczce ma `level 3` |
| Których przedmiotów nikt jeszcze nie tknął? | Node type `subject` + status **Not started** | 65 z 98; `completed` 32, `in-progress` 1 |
| Co jest duplikatem czego? | Relacja `near duplicate` + **only connected** | 365 plików, 119 klastrów, największy 81 |
| Który plik jest starszą wersją którego? | Relacja `older version` + **only connected** | 102 węzły, 104 krawędzie skierowane |
| Skąd wziął się ten plik i ile ma kopii? | Klik w węzeł → panel „Prowenancja” | pełna lista ścieżek źródłowych |
| Co dokładnie zrobi plan dla tego pliku? | Widok **Cards** | decyzja + ścieżka docelowa + pewność |
| Co wskazuje poza paczkę? | Ghosty (128) — bez filtra typu węzła | duplikaty w materiale bez decyzji |
| Jak duży jest przedmiot i z czego się składa? | Node type `subject` → klik → backlinki | kategorie i liczby w treści notatki |

Do pytań typu „pokaż mi listę” lepszy jest widok **Cards** niż graf: karta pokazuje
kategorię, status, decyzję i tagi bez klikania. Graf odpowiada na pytania o **kształt** —
gdzie są skupiska duplikatów, który przedmiot wisi sam, co wychodzi poza paczkę.

### Granice, o których trzeba wiedzieć

- **Bez „only connected” filtr relacji jest bezużyteczny przy tej skali**: rysuje 4 189
  węzłów, z czego kilka tysięcy bez jednej widocznej krawędzi.
- **119 rozłącznych klastrów rozjeżdża się po dużym obszarze** — po dopasowaniu widoku
  każdy z nich jest plamką. Do konkretnego klastra wchodzi się przez wyszukiwarkę, nie
  przez panoramowanie.
- **Układ całego grafu (4 189 węzłów) liczy się ~12 s.** Domyślny widok to szkielet
  105 węzłów właśnie dlatego.
- **Ghost + filtr typu węzła się wykluczają**: ghost nie ma typu, więc przy aktywnym
  filtrze typu znika. Duplikat, którego bliźniak leży w materiale bez decyzji, przepada
  wtedy razem z nim (508 plików z relacją `near_duplicate` → 365 widocznych).

### Co ten przegląd wykrył w samych danych

- **513 z 1 183 relacji `near_duplicate` to `.xml`↔`.xml`**, a największy klaster (81
  plików) to pliki projektowe Visual Studio (`*.vcxproj.xml`). To szum budowania, nie
  materiał dydaktyczny — kandydat do `ignore` w `syntax.yaml` albo do osobnej kategorii.
- **Słownik kategorii jest rozdwojony**: `wykład` (116) obok `wyklad` (42), `cwiczenia`
  (81) obok `ćwiczenia` (5), do tego `stara_paczka` (196), `sources` (2), `Filozofia`,
  `Prawo_Patentowe`, `Język_Polski`. Część bierze się z nazw katalogów ground truth,
  część z kluczy `syntax.yaml`. W legendzie i filtrach widać to od razu.
- **Mediana pewności duplikatu to 0,67** (min 0,56, max 1,0) — większość par to podobieństwo,
  nie identyczność, więc ręczna ocena jest tu na miejscu.
