# CLAUDE.md — zasady pracy nad Paczka Organizer

Ten plik jest czytany przez Claude Code (i obowiązuje odpowiednio dla Codexa —
zasady są model-agnostyczne). Trzymaj się go bez wyjątków. Krótkie odpowiedniki
tych reguł są też w `AGENTS.md`.

Mapa repozytoriów i organizacji (gdzie co żyje, dokąd trafia wynik):
`docs/ORGANIZACJA.md`. Architektura: `docs/ARCHITEKTURA_FINALv1.md`.
Ten projekt żyje w `paczka-tools/organizer/` i **tu odpalasz sesję**. Materiały
produkujesz jako PR-y (branch `subject/{SKROT}`) do klona repo docelowego wskazanego
w `config/paths.yaml: target_repo` (dziś `10_NEW/PaczkaInfaPG`, katalog `paczka/`).
Nigdy nie commitujesz binariów tutaj.

## Workspace (ścieżki TYLKO z `config/paths.yaml`)

| Klucz | Dziś | Reguła |
|---|---|---|
| `sources` | `../../00_SOURCES` | READ-ONLY. Hook `.claude/hooks/guard-sources.py` blokuje zapis. |
| `target_repo` + `target_paczka_subdir` | `../../10_NEW/PaczkaInfaPG` + `paczka` | tylko branch `subject/{SKROT}`, nigdy `master`; zmiany tylko przez `apply` |
| `work` | `../../20_WORK` | SQLite, extracted_text, thumbnails — odtwarzalne, poza gitem |
| `media` | `../../90_MEDIA` | duże media wyjęte z paczki, poza gitem |

## Reguły twarde (nigdy ich nie łam)

1. **`00_SOURCES/` jest READ-ONLY.** Nigdy nie modyfikuj, nie przenoś, nie kasuj
   plików źródłowych. Źródła leżą POZA repo (obok klona) i mają być nietknięte.
2. **`paczka/` w `target_repo` (produkt) jest kanoniczna.** To tam trafia wynik (`apply`).
   Ręcznie ułożone materiały to GROUND TRUTH — nie ruszaj ich nazw ani lokalizacji
   bez wyraźnej instrukcji.
3. **Deterministycznie najpierw, AI na końcu.** Jeśli plik da się przypisać po
   ścieżce/nazwie/strukturze — robi to skrypt, nie model. AI dotyka wyłącznie
   przypadków `unresolved`.
4. **Dokładne duplikaty tylko po hashu** (plik: sha256; folder: tree_hash).
   Nigdy nie traktuj plików "podobnych" jak duplikatów. Podobne => relacja, oba
   zostają.
5. **Nigdy nie kasuj niczego automatycznie.** Dedup jest logiczny (w bazie/planie),
   nie fizyczny.
6. **Jeden przedmiot na raz.** Kontekst przedmiotu wystarcza. **Skrót NIE jest
   unikalny** — tożsamość = (semestr, skrót). Semestr bierzesz ze ścieżki docelowej
   i to on rozstrzyga kolizje (AK, PO, SI, SK, ASK...). Patrz `config/subjects.yaml`.
7. **Każdy skopiowany plik zachowuje provenance** (z jakich źródeł pochodzi).
8. **Confidence za niskie => `unresolved`.** AI nie zgaduje. Progi w
   `config/thresholds.yaml` (≥0.90 auto, 0.70–0.90 review, <0.70 unresolved).
9. **Plan przed zmianami.** Agent (AI) NIE dotyka filesystemu — jego jedynym
   wyjściem jest `plan.jsonl`. Zmiany na dysku wykonuje wyłącznie skrypt `apply`
   PO Twojej akceptacji.
10. **`outdated/` to decyzja semantyczna**, zawsze przez review — nigdy z automatu
    z podobieństwa. Nowsza wersja tego samego => starsza to `older_version`, nie
    `outdated`.
11. **Media (duże wideo/audio) nie wchodzą do paczki.** Idą do `90_MEDIA/` (poza
    repo) + wpis w `inne/nagrania.txt`. Patrz `config/syntax.yaml`.
12. **Ścieżki do katalogów poza repo tylko z `config/paths.yaml`.** Żadnych
    hardkodowanych `../../…` w skryptach, skillach ani promptach.

## Model operacyjny (jak pracujesz)

Pracujesz w pętli **jeden przedmiot = jedno zadanie**, z człowiekiem jako bramką
**raz na przedmiot**, nie raz na plik:

1. Napisz/uruchom skrypty deterministyczne (scan → hash → dedup → extract →
   classify → plan) dla danego przedmiotu — **sam, bez pytania o każdy plik**.
2. Dla resztek (`unresolved`) użyj AI (Claude/Codex) — tylko dane tego przedmiotu.
3. Wyprodukuj **listę zmian do weryfikacji**: `plan.jsonl` + diff (near-dupe) +
   provenance + lista `unresolved`. **Zatrzymaj się.**
4. Poczekaj na akceptację człowieka (PR lub lokalnie).
5. Dopiero po OK: `apply` → `verify` → commity semantyczne (`plan`→`apply`→`docs`)
   → PR zamykający issue.

Nie wykonuj `apply`, dopóki plan nie przeszedł walidatora i akceptacji.

## Kontrakt I/O (wymienność Claude/Codex)

- Wejście AI: wycinek manifestu przedmiotu (`manifest_slice.jsonl`) + wyciągnięty
  tekst (głowa ~1–2 KB/plik) + struktura docelowa + zasady.
- Wyjście AI: `plan.jsonl` (jedna decyzja/linia) zgodny ze schematem.
- Model chowamy za `scripts/orglib/llm_client.py` (backend: anthropic / openai / `claude -p` /
  `codex exec` / `agy -p` — wybór per zadanie w `config/thresholds.yaml: llm`). Skrypty nie
  wiedzą, jaki model odpowiada.

## Minimalizacja tokenów

- Dedup przed extract przed classify. Nie przetwarzaj tej samej treści dwa razy.
- Nigdy nie wysyłaj binariów — tylko nazwa + ścieżka + głowa tekstu.
- Cache decyzji po `sha256` — nie pytaj modelu drugi raz o tę samą treść.
- Struktura/zasady raz na sesję, nie przy każdym pliku.
- Poddrzewa `duplicate_of` pomijają extract/OCR/classify/AI.

## Polityka koordynatora (Claude Code, plugin muxer)

Sesja działa na Fable (kredyty extra usage). Fable **koordynuje**: dekomponuje,
pisze briefy, ocenia raporty, podejmuje decyzje architektoniczne. Objętościową
robotę wykonują tańsze modele z limitu Pro:

| Zadanie | Kto | Model |
|---|---|---|
| eksploracja repo, czytanie/streszczanie logów, docs, raportów | `muxer:scout` | Haiku |
| uruchamianie skryptów/testów, streszczanie ich outputu | `muxer:runner` | Haiku |
| pisanie skryptów pipeline'u — proste (scan, hash, raporty, CLI, boilerplate, testy wg wzorca) | `python-pro` / `muxer:writer` | Sonnet (domyślnie) |
| pisanie skryptów pipeline'u — trudne (dedup, classify, plan, validator, apply, llm_client) | `muxer:builder` | Opus |
| schemat SQLite, zapytania raportowe | `sql-pro` | Sonnet |
| testy hashy, dedupu, validatora | `test-automator` | Sonnet |
| README/STATUS/provenance/docs | `documentation-engineer`, `readme-generator` | Haiku |
| weryfikacja pracy subagentów, review planu | `muxer:reviewer` | Opus |
| masowe `classify_one` (setki wywołań) | **poza sesją**: `scripts/ai_resolve.py` przez `llm_client`; backend z `thresholds.yaml: llm.classify` | Gemini flash (`agy_cli`, domyślnie); alternatywnie `codex_cli` / `claude_cli` Haiku |
| proste skrypty/testy wg gotowego wzorca, gdy limit Pro się kończy; równoległe strumienie | `codex` (agent projektu, `codex exec`) | GPT / Codex (limit ChatGPT Plus) |
| streszczanie dużych logów, raportów, drzew katalogów; masowe przetwarzanie tekstu | `agy` (agent projektu, `agy -p`) | Gemini flash (student pack) |
| drugie zdanie o planie / skrypcie spoza Anthropic | `codex` lub `agy` | GPT / Gemini |
| trudne `relate_cluster`, decyzje `outdated`, architektura | koordynator / `muxer:arbiter` | Fable (krótko) |

Biling: konto **Claude Pro** (nie Max) + kredyty extra usage. **Tylko Fable bierze z kredytów
extra usage** (główna pętla, `muxer:arbiter`, `muxer:oracle`). Opus/Sonnet/Haiku idą z limitu
Pro, który jest mały — dlatego wolumen zdejmują CLI spoza Anthropic: `codex exec` (ChatGPT Plus)
i `agy -p` (Antigravity CLI = Gemini, Google AI student pack) — zero tokenów Anthropic za ich
pracę. Zasady: proste buildy Sonnet albo `codex`; Opus tylko tam, gdzie jest logika z wieloma
decyzjami; `muxer:reviewer` (Opus) weryfikuje także pracę `codex`/`agy` — weryfikator nigdy nie
jest tańszy niż wykonawca; `arbiter`/`oracle` tylko na wyraźne życzenie użytkownika.
Uwaga: `muxer:gemini` szuka binarki `gemini` (brak na tej maszynie) — używaj agenta `agy`;
`muxer:codex` woła `--full-auto`, którego codex-cli ≥0.154 nie ma — używaj agenta `codex`.

**Pułapka bilingowa (zweryfikowana 2026-09-17, sprawdź, zanim uznasz delegację za darmową):**
`claude-code-router` przejął `~/.codex/config.toml` i kieruje `codex` przez proxy `127.0.0.1:3456`
na `Claude Code API/claude-sonnet-5`. Bez `--ignore-user-config` **`codex exec` zjada limit
Anthropic, nie ChatGPT Plus** — czyli delegacja „za darmo" kosztuje podwójnie. Agent `codex`
ma tę flagę na stałe i raportuje linię `provider:` jako dowód (`provider: openai` = dobrze).
`agy` nie ma proxy i idzie na konto Google, ale w trybie `-p` z `--sandbox` **nie może użyć
żadnego narzędzia** (uprawnienia auto-odrzucane, `jetski: no output produced`) — dlatego treść
plików wkleja się do promptu, a nie każe mu się ich szukać.

Kontrakt delegacji:
- Subagent zwraca **zwięzłe podsumowanie (≤30 linii)** — nigdy surowe pliki ani listingi.
  Bulk treści nie może trafić do kontekstu koordynatora.
- Koordynator **nie otwiera sam plików z `sources`** i nie czyta binariów. Pyta skrypty/bazę.
- CLI zewnętrzne (`codex`, `agy`): brief zapisany narzędziem Write do pliku w `/tmp` (heredoc
  w Bash z tekstem ścieżki źródeł blokuje hook `guard-sources`); sandbox read-only domyślnie,
  `workspace-write` tylko w organizerze lub klonie `target_repo`, nigdy zapis do `sources`.
  Agent AI w `ai_resolve.py` zawsze read-only + wymuszony schemat JSON (reguła 9).
- Brief jest samowystarczalny: kontrakt z `docs/ARCHITEKTURA_FINALv1.md`, kryteria akceptacji,
  ścieżki z `config/paths.yaml`. Najpierw jeden wzorcowy skrypt (zreviewowany), potem replikacja.
- Wzorzec: Research → Plan → Execute → Review → Ship = `scan…plan` → `validate` → **review
  (👤 STOP raz na przedmiot)** → `apply`/`verify` → PR. Skille: `/organizer-first-pass`,
  `/organizer-subject`, `/organizer-ai-resolve`, `/organizer-review`, `/organizer-ship`
  (`.claude/skills/`).
- Git: `plan.jsonl`, `manual_decisions.jsonl`, provenance operacyjne → commit **tutaj**.
  Materiały → **tylko** przez `apply` na branchu `subject/{SKROT}` w `target_repo`, potem PR.
  Nigdy `git push --force`, nigdy merge własnego PR.

## Źródło prawdy i git

- `20_WORK/organizer.sqlite` = operacyjne źródło prawdy (poza gitem, odtwarzalne).
- Do gita: `config/`, `prompts/`, `plan.jsonl`, `manual_decisions.jsonl`,
  provenance, raporty. **Ręczne decyzje eksportuj do
  `reports/manual_decisions.jsonl`** — muszą przeżyć przebudowę bazy.
- **Kod, config, docs, testy organizera (to repo): małe commity, bez pytania.** Każda
  działająca, przetestowana sekcja (np. schemat, `scan.py`, `hash.py`) = osobny commit
  od razu po zielonych testach/review. Nie zostawiaj działającej pracy niecommitowanej.
- **Materiały przedmiotu (`target_repo`): commit per przedmiot, po `verify`.** Nie
  commituj stanów pośrednich planu/apply.

## TODO.md — lista zadań do odhaczania

`TODO.md` w korzeniu projektu to plan pracy (skrypty, narzędzia, kolejne kroki).
Obowiązki Claude Code:
- Na starcie sesji przeczytaj `TODO.md`, żeby wiedzieć, gdzie jesteśmy.
- Po ukończeniu pozycji **odhacz ją samodzielnie** (`- [x]`, z datą) i dopisz
  nowe pozycje, które wynikły z pracy. Nie pytaj o zgodę na odhaczenie.
- Zmiana `TODO.md` wchodzi do tego samego commita co ukończona praca.
- Nie usuwaj pozycji; nieaktualne oznacz `~~tekst~~` z powodem.
