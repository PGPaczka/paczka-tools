# CLAUDE.md — adapter Claude Code

**Najpierw przeczytaj i stosuj `AGENTS.md`.** To kanoniczne źródło zasad
projektu. Ten plik zawiera wyłącznie ustawienia i politykę specyficzną dla
Claude Code; w razie konfliktu wygrywa `AGENTS.md`.

Sesję uruchamiaj przez:

```bash
just claude
```

Launcher ustawia katalog roboczy na `paczka-tools/organizer/`; projektowe
uprawnienia, hooki i plugin muxer są w `.claude/settings.json`.

## Claude workspace

- Dodatkowe katalogi wynikają z `config/paths.yaml`; lokalne bezwzględne ścieżki
  generuje `setup/install.sh` do `paczka-tools/.claude/settings.local.json`.
- Wspólny guard źródeł znajduje się w `.agents/hooks/guard-sources.py`.
- Skille organizera są w `.claude/skills/`.
- Agenci Claude-specyficzni są w `.claude/agents/`.

## Polityka koordynatora i muxera

Claude jest domyślnym interaktywnym koordynatorem projektu. Fable/Opus podejmuje
decyzje architektoniczne i ocenia wyniki; objętościową pracę deleguj:

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

Na tej maszynie `claude-code-router` zarządza bazowym
`~/.codex/config.toml`. Dlatego każda delegacja OpenAI przez `codex exec` musi
używać `--ignore-user-config`; agent `.claude/agents/codex.md` i
`scripts/orglib/llm_client.py` mają tę flagę na stałe.

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
`scripts/orglib/llm_client.py`. Nie używaj nieistniejącego `muxer:gemini`.

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
