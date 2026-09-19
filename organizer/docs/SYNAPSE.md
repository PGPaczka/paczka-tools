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
just synapse                      # vault w 20_WORK/synapse/vault (+ README obok)
just synapse --include-unassigned # razem z materiałem bez decyzji
just vendor-check                 # nasz vault przez PRAWDZIWY generator + walidacja schematem

# graf i podgląd
dotnet run --project vendor/synapse/Synapse.Generator/Synapse.Generator -c Release -- \
  --vault ../../20_WORK/synapse/vault \
  --out vendor/synapse/synapse-viewer/public/graph.json --no-git
cd vendor/synapse/synapse-viewer && npm install && npm run dev
```

Uwaga: generowanie do `public/graph.json` nadpisuje ich przykładowy graf w klonie.
To plik śledzony w tamtym repo — po zabawie `git -C vendor/synapse checkout -- synapse-viewer/public`.

## Zmierzone na realnych danych (2026-09-19)

4 189 węzłów (7 semestrów + 98 przedmiotów + 4 084 pliki), 5 469 krawędzi
(4 182 `belongs_to`, 1 183 `near_duplicate`, 104 `older_version`), 128 ghostów,
**0 ostrzeżeń, 0 sierot**, `graph.json` przechodzi walidację `graph.schema.v2.json`.
Generowanie vaulta i grafu: kilka sekund.
