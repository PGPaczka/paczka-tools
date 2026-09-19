# Synapse × Paczka Organizer — kontrakt danych

Jak indeks organizera (SQLite) mapuje się na model notatek `synapse`, żeby graf
pokazywał realne materiały zamiast zaszytej atrapy.

Generator: `scripts/synapse_export.py` (`just synapse`), mapowanie: `scripts/orglib/synapse.py`.

## Co to jest synapse i czym NIE jest

`~/dev/synapse` (GitHub: `Billypl/synapse`) to **handoff bundle z Claude Design** —
jeden interaktywny prototyp `SynapseVariants.dc.html` plus runtime `support.js`.
To nie jest aplikacja: nie ma `package.json`, buildu ani testów, a dane siedzą na
sztywno w metodzie `seedNotes()`. Własne `CLAUDE.md` tego repo mówi wprost: prototyp
odtwarza się w docelowej technologii, a `seedNotes()` i pola stanu `Component` są
„efektywnym modelem danych”.

Dlatego dopasowanie znaczy tu jedno: **produkujemy dane w kształcie, którego ten model
oczekuje**. Kodu synapse nie zmieniamy — gdy powstanie jego implementacja, ma wczytać
albo vault `.md`, albo gotowy `synapse.json`.

## Kontrakt notatki (odczytany z prototypu)

| pole | typ | uwagi z prototypu |
|---|---|---|
| `id` | slug | cel wikilinków `[[id]]`; musi być unikalny |
| `title` | tekst | nagłówek panelu i etykieta węzła |
| `category` | tekst | kolorowanie węzłów (`catColors`), filtr i rozbicie na dashboardzie |
| `level` | **1 \| 2 \| 3** | filtr zbudowany z literału `[1,2,3]`; fizyka liczy `level*2.2` |
| `status` | `completed` \| `in-progress` \| `not-started` | filtr i statystyki |
| `tags` | lista tekstów | filtry i tryb Venn (`vennDim: 'tag'`) |
| `links` | lista `id` | krawędzie grafu (wychodzące) |
| `path` | tekst | `{vault}/{kategoria}/{id}.md` |
| `body` | markdown | render z `[[wikilinkami]]`, z nich liczone są backlinki |
| `modified` | `yyyy-mm-dd` | sortowanie kart |
| `activity` | lista dat | pasek aktywności notatki |

**Najważniejsze ograniczenie: `level` ma tylko trzy stopnie.** Semestr (1-7) tam nie
wejdzie bez wycięcia sobie filtrów, więc semestr trafia do `category` i do tagów.
Kontraktu pilnuje `Note.validate()` i zapisana mutacja `synapse-level-contract` —
złamanie go nie wywala niczego u nas, tylko po cichu psuje graf u użytkownika.

## Mapowanie typów z bazy

### Zakres `subjects` (domyślny) — mapa całości, 98 notatek

| pole | źródło |
|---|---|
| `id` | `sem{semestr}-{skrót}` (+ grupa, gdy skrót się powtarza, np. SEM7 `SI`) |
| `title` | `{skrót} — {nazwa}` z `config/subjects.yaml` |
| `category` | `SEM1`…`SEM7` |
| `level` | 1 = tylko materiały w paczce · 2 = plan pewny · 3 = wymaga pracy (do przeglądu albo nietknięty) |
| `status` | `completed` (są materiały, nic nie czeka) · `in-progress` (plan w toku) · `not-started` (nic) |
| `tags` | `sem{n}`, `grupa-…`, `forma-w/c/l/p/s`, `katedra-…`, `do-przegladu`, `nietkniety` |
| `links` | inne przedmioty połączone **relacją między treściami** (`relations` × `classifications`) |
| `body` | katalog docelowy, formy, liczby ground truth / planu / akcji / kategorii |

Krawędzie tej mapy są dziś rzadkie i tak ma być: powstają tylko tam, gdzie OBIE
strony relacji mają już przypisany przedmiot (ground truth albo plan). Będzie ich
przybywać z każdym przetworzonym przedmiotem — to jest uczciwy obraz stanu prac,
a nie sztuczne dowiązania „ten sam semestr”.

### Zakres `subject` — graf relacji materiałów jednego przedmiotu

| pole | źródło |
|---|---|
| `id` | `{skrót}-{nazwa-pliku}-{sha256[:8]}` |
| `title` | nazwa pliku źródłowego |
| `category` | kategoria z `config/syntax.yaml` (`wyklad`, `kolokwia`, `laboratoria`, …) |
| `level` | 1 = leży już w paczce · 2 = decyzja powyżej progu `auto_apply` · 3 = review/brak rozstrzygnięcia |
| `status` | `completed` (w paczce) · `in-progress` (zaplanowane `copy`/`media`) · `not-started` (reszta) |
| `tags` | `rodzaj-{content_kind}`, `akcja-{action}`, `metoda-{classification_method}`, `kategoria-…`, `rok-…`, `w-paczce`, `do-przegladu` |
| `links` | `relations` (`near_duplicate`, `older_version`, `related`) |
| `body` | decyzja + uzasadnienie, sha256, relacje jako `[[wikilinki]]` z pewnością, prowenancja (wszystkie kopie w źródłach) |
| `modified` / `activity` | `files.modified_date` — najnowsza i wszystkie kopie; widać, w których rocznikach paczek materiał się pojawiał |

Domyślnie eksportujemy **tylko treści, które mają relację** — to jest graf relacji,
a nie zrzut katalogu; `--include-isolated` dokłada resztę.

## Wynik

```
work/synapse/{vault}/
├── README.md         # co znaczy level, jakie są kategorie i kolory
├── synapse.json      # {vault, generated_at, catColors, notes:[…]} w kształcie seedNotes()
└── {kategoria}/{id}.md
```

Vault jest **generowany i odtwarzalny**: leży w `20_WORK` (poza gitem), a każdy
eksport kasuje poprzednie notatki. Ręczne zmiany w nim nie przetrwają — jeśli mają
przetrwać, ich miejsce jest w bazie (decyzje) albo w `config/*.yaml` (reguły).

## Co musi zrobić implementacja synapse

1. wczytać notatki: albo parsując `.md` (front matter + `[[wikilinki]]`), albo
   biorąc `synapse.json` wprost jako `seedNotes()`;
2. wziąć `catColors` z pliku zamiast trzymać kolory na sztywno w stanie;
3. nie zakładać, że `level` znaczy „trudność” — u nas znaczy „jak bardzo ustalone”;
   opis jest w `README.md` vaulta i w tym pliku;
4. przy edycji notatki pamiętać, że vault jest **generowany** — zapis wymaga drogi
   powrotnej do bazy (kandydat: `manual_decisions`, TODO B14), inaczej zmiana zniknie
   przy kolejnym eksporcie.
