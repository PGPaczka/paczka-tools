# PLUGINS.md — co instalujemy pod sesję organizera i dlaczego

Uzasadnienie i ocena źródeł: `docs/CLAUDE_CODE_SETUP.md`. Zasada: **minimum ruchomych części**,
Fable koordynuje, Haiku/Sonnet/Opus wykonują. Wszystko poniżej stawia `setup/install.sh`.

## Instalujemy

| Co | Skąd | Jak (install.sh) | Po co |
|---|---|---|---|
| **muxer** (plugin, marketplace `muxer-local`) | `DangerousYams/muxer` | klon do `~/.claude/vendor/muxer` → `claude plugin marketplace add` → `claude plugin install muxer@muxer-local` | rdzeń: agenty `muxer:scout/runner/writer/builder/reviewer/arbiter/oracle`, hook SessionStart z polityką routingu, guard PreToolUse pinujący model wbudowanym subagentom, raport kosztów po turze (`/mux`) |
| **5 agentów VoltAgent** | `VoltAgent/awesome-claude-code-subagents` | sparse clone → kopia do `.claude/agents/` (już **commitowane**, z `model:` i `tools:` zaudytowanymi; skrypt kopiuje tylko przy `--refresh-agents`) | `python-pro`, `sql-pro`, `test-automator` (Sonnet) piszą pipeline; `documentation-engineer`, `readme-generator` (Haiku) piszą docs |
| **status line** | `centminmod/my-claude-code-setup` (README) | `setup/statusline.sh` → `~/.claude/statuslines/statusline.sh` + klucz `statusLine` w `~/.claude/settings.json` | podgląd kontekstu i kosztu sesji na żywo |
| **jq** | apt | `--with-apt` | wymagany przez hooki muxera (bez jq hooki po cichu nic nie robią) i status line |
| **rmlint, ncdu, tesseract(+pol), poppler-utils** | apt | `--with-apt` | bootstrap dedupu, raport rozmiaru, OCR na żądanie, `pdftotext` awaryjnie |
| **just** | binarka z GitHub releases | `~/.local/bin/just` | runner komend `subject-start/plan/apply/pr` (opcjonalny) |
| **venv organizera** | `setup/requirements.txt` | `organizer/.venv` | biblioteki pipeline'u |

Konfiguracja projektu (commitowana): `organizer/.claude/settings.json` (env muxera, `enabledPlugins`,
`additionalDirectories`, deny, hook `guard-sources.py`), `organizer/.claude/agents/`, `organizer/.claude/skills/`.
Konfiguracja maszyny (generowana, poza gitem): `paczka-tools/.claude/settings.local.json` z bezwzględnymi
ścieżkami `additionalDirectories` i `Edit(//…/00_SOURCES/**)` w deny.

Zmienne muxera ustawione w `settings.json → env`:
`MUXER_GUARD=on`, `MUXER_BUILTIN_AGENT_MODEL=sonnet` (wbudowane Explore/Plan/general-purpose bez modelu
dostają Sonnet, nie Fable), `MUXER_REPORT=always`, `MUXER_REPORT_MIN_USD=0` (raport po każdej turze),
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (to samo dla subagentów spoza muxera).

## Świadomie pomijamy

| Co | Dlaczego |
|---|---|
| muxer `codex`, `gemini` | osobne klucze OpenAI/Google; jeśli kiedyś — tylko jako backend `llm_client.py`, nie w sesji |
| cały marketplace VoltAgent (154 agenty) | narzut na opisy w kontekście; domyślne `model:` bywają Opus; bierzemy 5 plików z audytem |
| VoltAgent `research-analyst`, `knowledge-synthesizer` | pokrywa je `muxer:scout` / `muxer:researcher` |
| centminmod szablony CLAUDE.md, `.claude/rules`, skille `consult-zai`/`consult-codex`, MCP metryk | mamy własny `CLAUDE.md` pod projekt; MCP wymaga `uv` i osobnego serwera — status line wystarcza |
| shanraisshan/claude-code-best-practice | to dokumentacja; wzorzec Research→Plan→Execute→Review→Ship jest już w `CLAUDE.md` |
| oficjalne pluginy Anthropic (`code-review`, `commit-commands` itd.) | nic z tego nie jest potrzebne do pipeline'u; dokładać punktowo, gdy pojawi się potrzeba |

## Po instalacji — test kosztowy (z `docs/CLAUDE_CODE_SETUP.md`)
1. `cd paczka-tools/organizer && claude` → `/mux` pokazuje tabelę routingu.
2. Małe zadanie: „zaprojektuj `CREATE TABLE` dla `files` + `content` wg ARCHITEKTURA §4, zleć sql-pro”.
3. Raport muxera po turze ma pokazać: Fable = koordynacja (mało tokenów), Sonnet = praca.
