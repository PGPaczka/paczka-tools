# CLAUDE.md — adapter Claude Code

**Najpierw przeczytaj i stosuj `AGENTS.md`.** To kanoniczne źródło zasad
projektu. Ten plik zawiera wyłącznie ustawienia i politykę specyficzną dla
Claude Code; w razie konfliktu wygrywa `AGENTS.md`.

Sesję uruchamiaj przez:

```bash
just claude
```

Launcher ustawia katalog roboczy na `paczka-tools/organizer/`; projektowe
uprawnienia, hooki i plugin muxer są w `.claude/settings.json`. Argumenty idą
wprost do CLI (`just claude --resume`, `just claude -p "pytanie"`). Pełna
instrukcja startu obu agentów — z trybami sandboxu Codeksa i sposobem
potwierdzenia konta — jest w `README.md`, sekcja „Agenci interaktywni”.

## Claude workspace

- Dodatkowe katalogi wynikają z `config/paths.yaml`; lokalne bezwzględne ścieżki
  generuje `setup/install.sh` do `paczka-tools/.claude/settings.local.json`.
- Wspólny guard źródeł znajduje się w `.agents/hooks/guard-sources.py`.
- Skille organizera są w `.claude/skills/`.
- Agenci Claude-specyficzni są w `.claude/agents/`.

## Polityka koordynatora i muxera

Claude jest domyślnym interaktywnym koordynatorem projektu. Fable/Opus podejmuje
decyzje architektoniczne i ocenia wyniki; objętościową pracę deleguj.

**Zasada kosztowa: limit Anthropic idzie na myślenie, nie na przepisywanie.**
Praca klasyfikacyjna i powtarzalna — taka, której efekt widać w wyniku jednego
wywołania `-p` i da się sprawdzić wobec schematu — ma trafiać na konto OpenAI
(`codex_cli`) albo Google (`agy_cli`), a Claude ma ją **zlecać i oceniać**, nie
wykonywać. Konkretnie:

- klasyfikacja resztek przedmiotu → `just subject-ai-resolve SEM SKROT`
  (skrypt `scripts/ai_resolve.py`, backend z `config/thresholds.yaml: llm`);
  skill `/organizer-ai-resolve` jest tylko opakowaniem na tę komendę i **nie wolno**
  mu klasyfikować pozycji w sesji ani forkować do tego podagenta;
- jednorazowe zadanie tekstowe wg gotowego wzorca → agent `codex` (OpenAI)
  albo `agy` (Gemini);
- ocena wyniku, decyzje o strukturze, rozstrzyganie sporów → zostaje w Opusie.

Gdy jakość taniego backendu nie wystarcza, eskaluj **jawnie** i powiedz o tym
użytkownikowi z przykładami — wybór droższego modelu to jego decyzja kosztowa,
nie Twoja wygoda.

| Zadanie | Agent | Model |
|---|---|---|
| eksploracja repo, logi, raporty | `muxer:scout` | Haiku |
| uruchamianie skryptów/testów | `muxer:runner` | Haiku |
| prosty kod/boilerplate | `python-pro` / `muxer:writer` | Sonnet |
| trudna logika pipeline'u | `muxer:builder` | Opus |
| SQLite i zapytania | `sql-pro` | Sonnet |
| testy | `test-automator` | Sonnet |
| dokumentacja | `documentation-engineer`, `readme-generator` | Haiku |
| review implementacji/planu | `muxer:reviewer` | Opus |
| zewnętrzny GPT | agent `codex` | OpenAI Codex |
| masowy tekst / Gemini | agent `agy` | Gemini flash |

`muxer:arbiter` i `muxer:oracle` uruchamiaj tylko na wyraźne życzenie
użytkownika. Delegowany agent zwraca maksymalnie 30 linii podsumowania.

## Zewnętrzny Codex z sesji Claude

Bazowy `~/.codex/config.toml` jest czysty: `model_provider = "openai"`. Bloki
`claude-code-router` zostały z niego usunięte 2026-09-18 (router nie działał, a jego
wpisy psuły Codeksa: `codex doctor` nie mógł dosięgnąć `127.0.0.1:3456`, a podstawiony
katalog modeli powodował ostrzeżenie o braku metadanych `gpt-6-astra`). Kopia
sprzed zmiany leży w `~/.codex/config.toml.pre-ccr-removal-*`.

Delegacja OpenAI używa więc `codex exec -c model_provider="openai"`, a **nie**
`--ignore-user-config`. Ta flaga odcina `[hooks.state]`, przez co Codex przestaje
uruchamiać `.codex/hooks.json` i guard chroniący `00_SOURCES` milknie — sprawdzone
różnicowo. Jawne `-c model_provider=...` chroni konto tak samo, a hooki zostają.
Tak robi agent `.claude/agents/codex.md` i backend `codex_cli`
w `scripts/orglib/llm_client.py`.

Nie używaj `muxer:codex`: jego historyczna komenda nie odpowiada obecnemu CLI.
Do delegacji używaj agenta projektu `codex`.

Interaktywne przejęcie pracy przez GPT jest innym trybem niż delegacja:

```bash
just codex
```

Ten launcher używa profilu `paczka-openai` i nie zmienia globalnego routera.
Ustawia również `PACZKA_LLM_RELATE_BACKEND=codex_cli`, więc skrypty uruchomione
z tej sesji nie wrócą niejawnie do Claude dla zadania `relate`.

## Gemini / Antigravity

Agent `agy` w trybie headless z sandboxem nie może samodzielnie używać narzędzi.
Treść wejściową wklejaj do promptu; duże wsady obsługuje
`scripts/orglib/llm_client.py`. Nie używaj `muxer:gemini`: sam agent istnieje, ale
szuka binarki `gemini`, której na tej maszynie nie ma — Gemini stoi tu pod `agy`.

## Skille Claude

- `/organizer-first-pass`
- `/organizer-subject SKROT SEMESTR`
- `/organizer-ai-resolve SKROT SEMESTR`
- `/organizer-review SKROT SEMESTR`
- `/organizer-ship SKROT SEMESTR`

Skille są wygodnymi adapterami. Źródłem procesu są `AGENTS.md`, `justfile` i
skrypty; Codex ma dostęp do tych samych procedur przez `.agents/skills`.

## Obowiązki na końcu kroku

Stosuj sekcję „Git, stan i handoff” z `AGENTS.md`: aktualizuj `TODO.md`, uruchom
`just handoff` i uzupełnij ręczną część `reports/HANDOFF.md`.
