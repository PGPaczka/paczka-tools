# Synapse × Paczka Organizer — kontrakt danych

Jak indeks organizera zamienia się w graf, który pokazuje **rodzaj** powiązania między
materiałami. Generator: `scripts/synapse_export.py` (`just synapse`), model:
`scripts/orglib/synapse_vault.py`, źródła narzędzia: **`studio/graf/`** (w repo, wciągnięte
`git subtree` z gałęzi `feat/paczka-integration` repo `Billypl/synapse`).

## Czym jest synapse (i czym NIE jest lokalna kopia)

`Billypl/synapse` to **działająca aplikacja**: `Synapse.Generator` (.NET) skanuje katalog
notatek `.md`, czyta YAML front matter przez konfigurowalne mapowanie, rozwiązuje
`[[wikilinki]]` i buduje `graph.json`; `synapse-viewer` (Svelte) go wyświetla; `deploy/`
stawia to na RPi z regeneracją po `git push` na vault.

**Uwaga na pułapkę:** `~/dev/synapse` na tej maszynie to jeden commit z 2026-08-04 —
bundle z Claude Design sprzed implementacji, z danymi zaszytymi w `seedNotes()`.
Pierwsze podejście do C3 mapowało dane właśnie na niego i trafiło w próżnię (cofnięte
w `8fc5fb1`). **Kontrakt bierz z kodu w `studio/graf/`, który pochodzi z repo zdalnego.**

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

## Gdzie mieszka kod grafu (2026-09-22)

Źródła generatora i viewera są **w tym repo**, w `studio/graf/` — wciągnięte przez
`git subtree` (1,5 MB, 153 pliki) z gałęzi `feat/paczka-integration`. Powód: graf jest
przerobiony pod nas (schemat v2, typy węzłów, rodzaje krawędzi, czytelność przy 4 tysiącach
węzłów, naprawiony deep link), a te zmiany żyły wyłącznie w lokalnym klonie i przepadłyby
razem z nim.

`organizer/vendor/synapse` zostaje jako **klon upstreamu** (dalej poza gitem) — służy
tylko do synchronizacji:

```bash
# z korzenia paczka-tools
git subtree pull --prefix=organizer/studio/graf --squash organizer/vendor/synapse feat/paczka-integration
git subtree push --prefix=organizer/studio/graf organizer/vendor/synapse feat/paczka-integration
# potem z klona: git -C organizer/vendor/synapse push origin feat/paczka-integration
```

**Osadzenie w studiu (S4.1).** `just studio-graf` buduje ze źródeł w `studio/graf/` viewer z `--base=/graf/`
(assety pod prefiksem, `/graph.json` i `/vault/...` zostają bezwzględne — serwuje je
backend studia prosto z `20_WORK`). Studio nie kopiuje vaulta do `public/`: notatki idą
z `work` przez helper containmentu. Tłumaczenie `sha256` ↔ `id` notatki: `orglib/graph_link.py`,
po kontrakcie `synapse_vault.ID_SHA_PREFIX` (id notatki pliku kończy się `sha256[:8]`).

## Model: cztery typy węzłów

```
semester (7) ←belongs_to— subject (98) ←belongs_to— category (127) ←belongs_to— file (4 083)
                                                                          ↕ near_duplicate / older_version
```

Relacja zawierania jest zapisywana **na dziecku** (`belongs_to`), nie na rodzicu: przedmiot
miewa tysiące plików, a jedna pozycja na notatkę trzyma front matter mały.

**Kategoria jest poziomem POŚREDNIM** (decyzja użytkownika 2026-09-23). Bez niej przedmiot
był gwiazdą o dwóch i pół tysiącach szprych: nie dawało się odczytać, co jest czym, a każda
szprycha biegła przez pół grafu — sam ich rysunek zjadał klatki na telefonie. Z kategorią
przedmiot pokazuje kilka skupisk podpisanych `Kolokwia`, `Laboratoria`, `Wykład`…, a pliki
leżą przy swojej kategorii, więc krawędzie są krótkie i lokalne. Kategorie bez ani jednego
pliku nie są eksportowane.

| pole | `semester` | `subject` | `category` | `file` |
|---|---|---|---|---|
| `id` = nazwa pliku | `sem3` | `sem3-ako` | `sem3-ako-kat-kolokwia` | `ako-{nazwa}-{sha8}` |
| `title` | `Semestr 3` | `AKO` (sam skrót) | `Kolokwia · AKO` | nazwa pliku (źródłowego albo docelowego) |
| `category` | `semestr` | `SEM1`…`SEM7` | nazwa kategorii | kategoria z `syntax.yaml` |
| `level` | — | 1–3 wg stanu prac | j.w. dla swoich plików | 1 = w paczce · 2 = plan pewny · 3 = wymaga człowieka |
| `status` | zbiorczy | `completed`/`in-progress`/`not-started` | zbiorczy dla swoich plików | j.w. wg etapu potoku |
| `tags` | `semestr`, `semN` | `semN`, skrót (`ako`), grupa, formy, katedra | `semN`, skrót, `kategoria-…` | `semN`, skrót, `rodzaj-…`, `kategoria-…`, `akcja-…`, `metoda-…`, `rok-…`, `w-paczce` |
| `relations` | — | `belongs_to` → semestr | `belongs_to` → przedmiot | `belongs_to` → **kategoria** + relacje z B6 |

Treść notatki pliku niesie **podgląd**: obraz albo pierwszą stronę PDF-a
(`![podgląd](/api/preview/<sha>/image?width=720)`), a dla plików tekstowych kilka
pierwszych linijek zakończonych `…` i adnotacją `_fragment — całość w studiu_`, żeby
urwany tekst wyglądał na urwany. Na końcu jest odnośnik `[Otwórz w studiu](/?sha=<sha>)`. Adresy są
względne, więc działają wtedy, gdy viewera serwuje studio — czyli tam, gdzie te dane mają
sens; w upstreamowym demo po prostu ich nie ma.

Rozmiar też: z wiersza w `files`, a gdy go nie ma — ze `stat` pliku w paczce. Podawany
jest w bajtach poniżej kilobajta, bo zaokrąglanie robiło z 271 B „0 kB". Pusty rozmiar
znaczy „nie wiem", nie „mało".

Nazwa pliku bierze się z kopii źródłowej, a gdy jej nie ma — ze **ścieżki docelowej**
z decyzji. Ground truth opisuje materiały leżące już w paczce, których nikt nie indeksował
jako plików źródłowych: 890 takich treści nazywało się w grafie skrótem sha.

`title` przedmiotu to **sam skrót**: w grafie jest to podpis przy węźle, a
„AKO — Architektura Komputerów" zasłania sąsiadów. Pełna nazwa zostaje aliasem (czyli
wyszukiwarka ją znajduje) i pierwszą linią treści notatki.

Wstawka `-kat-` w id kategorii nie jest ozdobnikiem: bez niej kategoria o nazwie zbieżnej
ze skrótem innego przedmiotu dałaby kolizję id, a kolizja w tym vaulcie to ostrzeżenie
`duplicate-id` i notatka, która przestaje być celem relacji.

Tag semestru (`sem3`), skrót przedmiotu (`ako`) i `kategoria-…` niesie **każdy poziom
poniżej** tego, co nazywa: kategorie i pliki mają `sem3` i `ako`, pliki mają dodatkowo
`kategoria-kolokwia`. To one pozwalają wybrać w viewerze zakres „semestr → przedmiot →
kategoria" trzema kliknięciami — `category` do tego nie służy, bo `SEM3` mają wyłącznie przedmioty
i filtr po niej pokazuje przedmioty bez ich materiałów.

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
cd studio/graf/synapse-viewer && npm install && npm run dev
```

`just synapse-view` robi trzy rzeczy: eksportuje vault, przepuszcza go przez generator do
`studio/graf/synapse-viewer/public/graph.json` i kopiuje same `.md` do `public/vault/`
— bez tej kopii panel szczegółów pokazuje sam wyciąg zamiast treści notatki.

Uwaga: generowanie do `public/graph.json` nadpisuje ich przykładowy graf w klonie.
Te pliki są u nas **ignorowane** (`.gitignore`), więc tryb samodzielny niczego nie brudzi;
studio czyta swój graf wyłącznie z `20_WORK/synapse/`.

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
