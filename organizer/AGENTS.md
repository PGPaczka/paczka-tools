# AGENTS.md — wspólne zasady Paczka Organizer

To jest **kanoniczne, model-agnostyczne źródło instrukcji** dla Claude Code,
OpenAI Codex, Gemini/Antigravity i kolejnych agentów. Adaptery konkretnego
narzędzia (`CLAUDE.md`, `GEMINI.md`, `.claude/`, `.codex/`) mogą dodawać
ustawienia techniczne, ale nie mogą osłabiać reguł z tego pliku.

Projekt żyje w `paczka-tools/organizer/` i **z tego katalogu uruchamiaj sesje**.
Mapa repozytoriów: `docs/ORGANIZACJA.md`. Architektura:
`docs/ARCHITEKTURA_FINALv1.md`. Stan pracy: `TODO.md` i `reports/HANDOFF.md`.

## Role agentów — nie mieszaj ich

1. **Coding agent / koordynator** może zmieniać kod, config, testy, dokumentację
   i tekstowe raporty w tym repo. Uruchamia skrypty i testy, ale nie kopiuje
   ręcznie materiałów do paczki.
2. **Classification agent** jest czystą funkcją
   `manifest_slice.jsonl → plan.jsonl`. Nie chodzi po filesystemie i nie
   modyfikuje plików poza wskazanym tekstowym wynikiem.
3. **Skrypty pipeline'u** jako jedyne czytają masowo źródła, zapisują
   `20_WORK`, a po akceptacji wykonują `apply` do repo docelowego.
4. **Człowiek** zatwierdza plan przed `apply` i merguje PR. Agent nigdy nie
   interpretuje milczenia jako zgody.

Zdanie „agent nie dotyka filesystemu” dotyczy classification agenta, nie coding
agenta pracującego nad implementacją organizera.

## Workspace — ścieżki tylko z configu

Wszystkie ścieżki poza repo pobieraj wyłącznie z `config/paths.yaml`:

| Klucz | Rola | Zapis |
|---|---|---|
| `sources` | archiwum starych paczek (`00_SOURCES`) | **nigdy** |
| `target_repo` + `target_paczka_subdir` | kanoniczna paczka docelowa | tylko `apply`, branch `subject/{SKROT}` |
| `work` | SQLite, extracted text, thumbnails, cache | przez skrypty |
| `media` | duże audio/wideo poza repo | przez `apply`/media stage |

Nie hardkoduj `../../…` w Pythonie, promptach, skillach ani testach.

## Reguły twarde

1. **`00_SOURCES` jest READ-ONLY.** Nigdy nie modyfikuj, przenoś, kasuj,
   rozpakowuj ani zmieniaj uprawnień plików źródłowych.
2. **`paczka/` w `target_repo` jest kanoniczna.** Ręcznie ułożone materiały to
   ground truth; nie zmieniaj ich nazw ani lokalizacji bez instrukcji.
3. **Deterministycznie najpierw, AI na końcu.** AI obsługuje tylko
   `unresolved`.
4. **Dokładne duplikaty tylko po hashu:** plik `sha256`, folder `tree_hash`.
5. **Podobieństwo nie oznacza duplikatu.** Zapisz relację i zachowaj oba pliki.
6. **Nigdy nie kasuj automatycznie.** Dedup jest logiczny w bazie/planie.
7. **Jeden przedmiot na raz.** Tożsamość to co najmniej `(semestr, skrót)`;
   gdy istnieje kolizja, użyj także `grupa` z `config/subjects.yaml`.
8. **Każda kopia zachowuje provenance:** `source_sha256` i `source_paths`.
9. **Nie zgaduj.** Niska pewność oznacza `needs_review=true` albo
   `action=quarantine`; progi są w `config/thresholds.yaml`.
10. **`outdated/` jest decyzją człowieka.** Starsza wersja może dostać relację
    `older_version`, ale nie automatyczne `outdated`.
11. **Duże media nie trafiają do paczki.** Kieruj je do `90_MEDIA` i dodaj wpis
    w `inne/nagrania.txt`.
12. **Plan przed zmianami materiałów.** `apply` wolno uruchomić tylko po
    walidacji planu i jawnej akceptacji użytkownika.
13. **Bez destrukcyjnego gita.** Nigdy `git push --force`, samodzielnego merge
    własnego PR, `git clean` ani resetowania cudzych zmian.
14. **Nie obchodź sandboxu i hooków.** Nie używaj flag wyłączających ochronę,
    jeśli użytkownik nie zażądał tego wprost.
15. **Ręczne powiązanie katalogów jest decyzją człowieka i ma pierwszeństwo przed
    heurystyką, ale niczego nie wycina.** `manual_folder_links` mówi „te dwa katalogi
    to ten sam materiał", czego automatyczny dedup (`folders.duplicate_of` z `tree_hash`)
    nie widzi, bo tamten wymaga równości poddrzewa co do bitu. Powiązania NIE wolno
    wpisywać do `duplicate_of` ani używać do pomijania plików: `db.files_pending` wycina
    poddrzewa duplikatów z extract i classify, więc pliki obecne tylko po jednej stronie
    zniknęłyby z potoku bez śladu. Powiązanie podpowiada (decyzja hurtem obejmuje drugi
    katalog po jawnym zaznaczeniu) i pokazuje się w raporcie przeglądu.

Wspólny guard źródeł: `.agents/hooks/guard-sources.py`. Claude wywołuje go z
`.claude/settings.json`, a Codex z repozytoryjnego `.codex/hooks.json`.

Guard blokuje mutację źródeł także wtedy, gdy nie wygląda ona jak `rm`: kod
podany interpreterowi wprost (`python3 -c`, `perl -e`, `node -e`, heredoc na
stdin), `python3 -m zipfile`, `find -delete`, zapis wskazany flagą (`cp -t`,
`sort -o`), cel kopiowania stojący nie na końcu komendy, archiwizatory
(`zip`, `7z`, `tar -c`) z celem w źródłach, każda podkomenda `git` spoza listy
wyłącznie czytających (także wskazana przez `-C`/`--work-tree`) i wymuszone
nadpisanie `>|`.

**Guard nie zależy od nazwy narzędzia.** Hosty nazywają powłokę różnie (Claude:
`Bash`, Codex: `shell`/`local_shell`), a komenda bywa listą argumentów zamiast
stringiem. Hook reaguje na TREŚĆ zdarzenia, a matchery w `.claude/settings.json`
i `.codex/hooks.json` są odpowiednio szerokie — wcześniejsze `elif tool ==
"Bash"` sprawiało, że dla narzędzi Codeksa hook kończył bez ani jednej kontroli.

Czysty odczyt źródeł przechodzi — łącznie z `tar -xf` rozpakowującym **ze**
źródeł gdzie indziej, `grep -f` czytającym stamtąd wzorce, `git -C … log` i
jednolinijkowcem, który źródła czyta. **Zwężenie z 2026-09-18:** kod inline,
który jednocześnie wymienia katalog źródeł i zawiera czasownik mutujący, jest
blokowany nawet wtedy, gdy mutacja dotyczy pliku poza źródłami — przy ścieżce
schowanej w zmiennej albo w `os.chdir` nie da się tego rzetelnie rozstrzygnąć.
Wynik takiego odczytu wyprowadzaj przekierowaniem powłoki (`> /tmp/raport.txt`)
albo skryptem w `scripts/`; oba warianty są dozwolone i objęte testami.

Obie strony kompromisu pilnuje `tests/test_agent_guard.py`; przy zmianach
w hooku dopisuj tam zarówno próbę obejścia, jak i wariant odczytu, który ma
nadal działać. Listy słów mutujących są w testach **wypisane wprost**, a nie
czytane z hooka: parametryzacja po liście z implementacji jest pusta, bo jej
skrócenie skraca też zestaw przypadków (sprawdzone — dało się wyciąć listy do
dwóch słów przy 32 zielonych testach). Osobny test pilnuje, że hook jest
w ogóle **podpięty** w configach obu hostów.

Guard jest ostatnią barierą, nie pierwszą: dopasowuje ścieżki po tekście
komendy, więc świadomie zaciemniony zapis (`base64`, własny skrypt) go ominie —
to nie jest zaproszenie do próbowania (reguła 14).

## Model operacyjny

Pracuj w pętli **jeden przedmiot = jedno zadanie**, z jedną bramką człowieka:

1. przygotuj wycinek manifestu;
2. extract → classify deterministyczny;
3. AI tylko dla `unresolved`;
4. build plan → validate → dry-run diff;
5. przygotuj review i **zatrzymaj się**;
6. po jawnej akceptacji: snapshot → apply → verify;
7. provenance, commity semantyczne, PR; merge robi użytkownik.

Wzorzec pracy nad kodem:
**Research → Plan → Execute → Review → Ship**. Najpierw znajdź istniejący
wzorzec, potem minimalna implementacja, testy specyficzne, szersza walidacja,
aktualizacja `TODO.md` i handoff.

## Kontrakt AI

- Wejście: manifest jednego przedmiotu, nazwy/ścieżki, głowa tekstu do limitu,
  struktura docelowa i reguły.
- Wyjście: JSON/JSONL zgodny ze schematem, jedna decyzja na `sha256`.
- Modele są za `scripts/orglib/llm_client.py`; kod pipeline'u nie zależy od
  providera.
- Backend wybiera `config/thresholds.yaml: llm` lub jawna opcja zadania.
- Zewnętrzne CLI dla klasyfikacji działają read-only, ze schematem wyniku i
  cache po hash promptu.

## Minimalizacja kontekstu i kosztu

- dedup przed extract przed classify;
- nigdy nie wysyłaj binariów do modelu;
- używaj `text_head`, raportów i zapytań do SQLite zamiast surowych drzew;
- poddrzewa `duplicate_of` pomijają extract/OCR/AI;
- cache decyzji po `sha256`;
- delegowany agent zwraca podsumowanie do 30 linii, nie pełne listingi;
- trudniejszy model tylko do decyzji semantycznych i review.

## Wspólne uruchamianie agentów

Nie uruchamiaj narzędzi „gołą” komendą, jeśli dostępny jest launcher projektu:

```bash
just claude          # Claude Code + .claude setup
just codex           # Codex/OpenAI, dev: organizer + 20_WORK writable
just codex-read      # Codex read-only
just codex-ship      # Codex z target_repo/media writable, tylko po akceptacji
just agent-doctor
```

Argumenty dopisuje się bez `--` (`just codex-read "streść HANDOFF"`) — recepty
`codex-read`/`codex-ship` dodają go same, a drugi psuje wywołanie. Rozpisana
instrukcja startu jest w `README.md`, sekcja „Agenci interaktywni”.

`just codex` wymaga profilu `paczka-openai`, tworzonego przez
`just agent-setup`. Launcher odmawia startu, jeśli profil nie wskazuje
`model_provider = "openai"`. Profil jest niezależny od tego, co ktoś ustawi
w bazowym `~/.codex/config.toml`, więc interaktywny Codex zawsze idzie na OpenAI.

Do bazowego configu Codeksa nie wolno wpuszczać proxy przekierowującego ruch na
inne konto (np. `claude-code-router`): delegacja z Claude szłaby wtedy po cichu
na limit Anthropic, a obejście tego flagą `--ignore-user-config` wyłącza razem
z konfiguracją użytkownika sekcję `[hooks.state]` — czyli guard `00_SOURCES`
w Codeksie. Zamiast flagi wymuszaj konto jawnie: `-c model_provider="openai"`.

Nigdy nie dodawaj `sources` jako writable root Codexa. Tryb `codex-ship` dodaje
wyłącznie `work`, `target_repo` i `media`.

Backend zadań AI bierze się z `config/thresholds.yaml: llm` — domyślnie zarówno
`classify`, jak i `relate` idą na `codex_cli`: praca klasyfikacyjna ma obciążać
konto ChatGPT, a limit koordynatora zostawać na planowanie i ocenę wyników.
Koordynator, który klasyfikuje materiały we własnej sesji zamiast uruchomić
`just subject-ai-resolve`, łamie tę zasadę.

`just codex` ustawia `PACZKA_LLM_RELATE_BACKEND=codex_cli` (zgodnie z domyślną
polityką). `just claude` **nie** nadpisuje backendu — inaczej samo uruchomienie
sesji Claude po cichu przenosiłoby `relate` na limit Anthropic. Skierowanie
zadania na Claude jest świadomą decyzją człowieka na jedną sesję:
`PACZKA_LLM_RELATE_BACKEND=claude_cli just claude`.

To jawny override procesu, nie automatyczny fallback. Użytkownik może go
nadpisać własną zmienną `PACZKA_LLM_<TASK>_BACKEND` lub
`PACZKA_LLM_<TASK>_MODEL`.

## Skille i procedury

Kanoniczne procedury organizera pozostają w `.claude/skills/organizer-*`.
Codex widzi te same katalogi przez `.agents/skills/` — nie utrzymuj dwóch kopii.
Treść skillu musi opisywać workflow i komendy projektu, a integracje konkretnego
hosta traktować jako opcjonalne adaptery.

Agent sam dobiera skille do zleconego zadania; użytkownik nie musi wpisywać
slash command ani `$skill-name`. Parametry takie jak skrót, semestr i manifest
ustal z jednoznacznego kontekstu zadania, a o brakujące zapytaj — nie wykonuj
komend z niewypełnionymi placeholderami. Claude ma
`disable-model-invocation: false`, a Codex
`agents/openai.yaml: policy.allow_implicit_invocation: true`.
Automatyczny wybór procedury nie rozszerza zakresu zadania: nadal wymagaj
jawnej akceptacji konkretnego planu przed `apply`; nie rozpoczynaj sam nowego
przedmiotu ani nie traktuj wyboru skillu jako zgody na commit materiałów,
push lub PR. Lokalne commity zmian narzędzi reguluje sekcja „Git, stan i handoff”.

Metadane współdzielonych skilli sprawdzaj przez `just skills-check` (również
objęte `just test`). Projektowy walidator zna używane rozszerzenia Claude,
w tym `argument-hint` i `disable-model-invocation`. Ogólny `quick_validate.py`
z systemowego skill-creator ma węższą listę pól — jego błąd „unexpected keys”
nie jest powodem do usuwania ustawień hosta. Nie zmieniaj globalnego walidatora.

Jeśli host nie obsługuje skillu lub subagenta, wykonaj tę samą procedurę przez
`just` i skrypty. Poprawność pipeline'u nie może zależeć od slash command.

## Subagenci

Role Codexa są w repozytoryjnym `.codex/agents/*.toml`. Model dziedziczą z
centralnego `.codex/config.toml`, natomiast reasoning i sandbox są przypisane
per rola:

- `explorer`, `reviewer` — `read-only`;
- `runner`, `python_pro`, `sql_pro`, `test_automator`,
  `documentation_engineer`, `readme_generator` — `workspace-write`.

Subagent z `workspace-write` nadal podlega wszystkim regułom tego pliku,
hookowi i sandboxowi sesji nadrzędnej. Nie dostaje zgody na `apply`, commit,
zapis do `00_SOURCES` ani zmianę materiałów tylko dlatego, że może pisać kod.

Claude ma równoległe role w `.claude/agents/` oraz pluginie muxer. Delegatory
Claude `codex` i `agy` nie są kopiowane jako role Codexa: ich zadaniem jest
uruchomienie zewnętrznego CLI z sesji Claude, a wewnątrz Codexa tworzyłyby
zbędną rekurencyjną delegację.

## Git, stan i handoff

- `20_WORK/organizer.sqlite` jest operacyjnym źródłem prawdy poza gitem.
- Do gita trafiają kod, config, prompty, tekstowe plany, ręczne decyzje,
  provenance i raporty przeznaczone do wersjonowania.
- Kod/config/skrypty/docs/testy oraz tekstowe raporty techniczne tego repo:
  po testach i przeglądzie diffu **domyślnie wykonaj lokalny commit** małego,
  logicznego zakresu, bez dodatkowego pytania. Użytkownik może jawnie zlecić
  pozostawienie zmian bez commita. Nie dodawaj cudzych, niepowiązanych zmian,
  sekretów ani danych lokalnych. W pracy delegowanej commit wykonuje koordynator.
- Domyślne commity narzędzi **nie obejmują materiałów**, niezależnie od ich
  położenia. Materiały przedmiotu: wyłącznie w dotychczas zatwierdzonym procesie,
  po jawnej akceptacji planu przed `apply`, z commitem dopiero po pomyślnym
  `verify`, na branchu przedmiotu. Nigdy razem z commitem narzędzi.
- **Komunikaty commitów pisz po angielsku** (decyzja użytkownika z 2026-09-23).
  Dotyczy tytułu i treści; reszta dokumentacji repo zostaje po polsku. Starsze,
  polskie commity zostają takie, jakie są — przepisywanie opublikowanej historii
  kosztuje więcej, niż daje.
- Push i utworzenie PR wymagają osobnego polecenia; merge robi użytkownik.
- Nie cofaj ani nie nadpisuj niepowiązanych zmian użytkownika.

Na starcie:

1. przeczytaj `TODO.md`;
2. przeczytaj `reports/HANDOFF.md`, jeśli istnieje;
3. sprawdź `git status --short` i ostatnie commity;
4. zweryfikuj, czy poprzedni agent nie zostawił pracy częściowej.

Po każdym większym, spójnym kroku:

1. odhacz/dopisz `TODO.md` z datą;
2. uruchom `just handoff`;
3. uzupełnij ręczną część `reports/HANDOFF.md`: cel, testy, następna czynność,
   blokery i stan akceptacji;
4. nie zapisuj „plan zaakceptowany”, jeśli nie ma jawnej zgody użytkownika.

`reports/HANDOFF.md` jest kontraktem przekazania stanu między Claude, Codex i
człowiekiem. Historia czatu nie jest źródłem prawdy.

## Walidacja i zakończenie

- Zaczynaj od testów najbliższych zmienionemu kodowi, potem szerszy zestaw.
- Nie naprawiaj niepowiązanych błędów; zgłoś je oddzielnie.
- Nie deklaruj powodzenia bez rzeczywiście uruchomionych kontroli.

**Każdy znaleziony błąd, którego testy nie złapały, kończy się nowym testem.**
Reguła jest wiążąca i dotyczy tak samo błędu zgłoszonego przez użytkownika, jak
znalezionego przez agenta, w cudzym i we własnym kodzie. Kolejność jest zawsze ta
sama:

1. **najpierw test, potem poprawka** — napisz test odtwarzający dokładnie ten
   przypadek i zobacz, że jest CZERWONY. Test, którego nie widziałeś czerwonego,
   niczego nie dowodzi (patrz pułapka niżej);
2. dopiero potem popraw kod i sprawdź, że test jest zielony;
3. wybierz warstwę adekwatną do przyczyny (README, „Testy: pięć warstw"):
   kontrakt kodu dla logiki, `environment` dla brakującej biblioteki lub binarki,
   `cli_contract` dla argumentów zewnętrznego CLI, `e2e` dla styku między
   etapami, `probe` dla stanu realnych danych;
4. gdy błąd dotyczył kontraktu wartego pilnowania na stałe (separator, lista
   słów, kolejność reguł, pole w kontrakcie międzyetapowym), dopisz mutację do
   `tests/mutations/*.yaml` i sprawdź `just mutate-check` — ma wyjść `WYKRYTE`;
5. w opisie testu napisz, **po jakiej wpadce powstał**. To jedyna forma, w której
   ta wiedza przetrwa; komentarz „sprawdza X" nie mówi, dlaczego X jest ważne.

Nie wolno „naprawić" błędu samą zmianą testu ani zawęzić asercji, żeby przeszła
(decyzja użytkownika: *jeśli coś nie działa, ma być czerwone*). Pułapki, na które
ten projekt już się nadział, więc nie sprawdzaj ich ponownie własnym kosztem:
test przez cały potok potrafi nie pilnować zabezpieczenia, bo dostaje dane
oczyszczone przez wcześniejszy etap (sprawdzaj też jednostkowo, na surowym
wejściu), a parametryzacja po liście z implementacji jest pusta, gdy ktoś tę
listę skróci (wypisuj wartości w teście wprost).
- Po walidacji i aktualizacji stanu zapisz zmiany narzędzi w lokalnych commitach
  zgodnie z powyższą polityką; w podsumowaniu podaj ich identyfikatory.
- Końcowy raport zawiera: zmienione pliki, wynik testów, nierozwiązane ryzyka
  i dokładny następny krok.
