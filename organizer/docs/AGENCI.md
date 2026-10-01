# Agenci interaktywni

Jak uruchamiać Claude i Codex nad tym repo, które konto wykonuje pracę AI
w pipeline'u i dlaczego `--ignore-user-config` jest zakazane.

Claude pozostaje domyślnym koordynatorem, ale stan projektu i procedury nie są
zależne od hosta. **Zawsze startuj przez `just`, nie przez gołe `claude`/`codex`** —
launcher wchodzi do katalogu organizera, ustawia zmienne sesji i pilnuje, żeby
Codex nie wystartował na cudzym koncie ani z zapisem do źródeł.

## Raz na maszynę

```bash
bash setup/install.sh        # venv, zależności, plugin muxer, settings.local.json
just agent-setup             # profil ~/.codex/paczka-openai.config.toml
just agent-doctor            # kontrola: CLI, konto Codexa, ścieżki z paths.yaml
```

`agent-doctor` musi skończyć bez `BRAK`/`BŁĄD`. Zgłasza m.in., gdy bazowy
`~/.codex/config.toml` przestał wskazywać OpenAI — wtedy delegacja poszłaby na
cudze konto (patrz „Dlaczego nie `--ignore-user-config`” niżej).

## Claude — koordynator

```bash
just claude                  # sesja interaktywna w paczka-tools/organizer/
just claude --resume         # argumenty idą wprost do CLI
just claude -p "pytanie"     # jednorazowy prompt, bez sesji
```

Sesja dostaje `.claude/settings.json`: plugin muxer, hook `guard-sources.py`,
katalogi robocze z `config/paths.yaml` i deny-listę na `00_SOURCES`. Skille
`organizer-*` są wtedy dostępne jako `/organizer-subject AKO 3` itd.

## Codex — GPT interaktywnie

Trzy tryby, różnią się **wyłącznie** tym, gdzie Codex może pisać:

```bash
just codex-read              # nic nie zapisuje — analiza, drugie zdanie, review
just codex                   # organizer + 20_WORK (domyślny do pracy nad kodem)
just codex-ship              # dodatkowo target_repo i 90_MEDIA — tylko po akceptacji planu
```

Argumenty dopisuje się wprost, **bez `--`** (recepty `codex-read`/`codex-ship` już
go dodają, drugi psuje wywołanie):

```bash
just codex-read "streść reports/HANDOFF.md"    # start z gotowym promptem
just codex --version                            # argumenty idą do CLI
```

`codex-ship` odmówi startu, gdy `target_repo` nie jest klonem gita. **Nigdy** nie
dodawaj `00_SOURCES` jako katalogu zapisywalnego — żaden z trybów tego nie robi.

Że sesja idzie na właściwe konto, potwierdzisz przez `just agent-doctor` (linie
`profil Codexa` i `bazowy config Codexa`) albo `codex doctor` (sekcja
`Configuration` → `model … · openai`). Model zmienisz bez edycji plików:

```bash
CODEX_MODEL=gpt-6-astra just codex
CODEX_PROFILE=inny-profil just codex     # profil musi mieć model_provider = "openai"
```

Launcher czyta `~/.codex/<profil>.config.toml` i **odmawia startu**, jeśli profil
nie wymusza `model_provider = "openai"`. Dzięki temu jest odporny na to, co ktoś
ustawi w bazowym `~/.codex/config.toml`.

## Który model wykonuje pracę AI

Backend zadań pipeline'u bierze się z `config/thresholds.yaml: llm` — domyślnie
`classify` i `relate` idą na `codex_cli`, więc praca klasyfikacyjna obciąża konto
ChatGPT, a limit koordynatora zostaje na planowanie i ocenę. `just claude` tego
nie nadpisuje; skierowanie zadania na Claude to świadoma decyzja na jedną sesję:

```bash
PACZKA_LLM_RELATE_BACKEND=claude_cli just claude
```

## Dlaczego nie `--ignore-user-config`

Flaga wygląda jak wygodny sposób na ominięcie cudzego proxy w bazowym configu
Codeksa, ale odcina też sekcję `[hooks.state]` — a wtedy Codex przestaje
uruchamiać `.codex/hooks.json`, czyli **guard chroniący `00_SOURCES` milknie**.
Konto wymuszaj jawnie: `codex exec -c model_provider="openai" …`.

Wspólne zasady są w `AGENTS.md`, kontrakt przekazania stanu w
`reports/HANDOFF.md`, a deterministyczne operacje w `justfile` i `scripts/`.

Codex ma projektowe subagenty w `../.codex/agents/`: `explorer`, `runner`,
`reviewer`, `python_pro`, `sql_pro`, `test_automator`,
`documentation_engineer` i `readme_generator`. `../.codex/config.toml`
centralnie wybiera ich model i limit równoległości; każda rola ma osobno
przypisany reasoning oraz sandbox. Role analityczne są read-only, a role
implementacyjne zapisują wyłącznie w granicach sandboxu sesji nadrzędnej.

Poza gitem — workspace `~/dev/paczka/PaczkaMerge/` (ścieżki w `config/paths.yaml`):
```
00_SOURCES/            # stare paczki (read-only, backup na Drive)
10_NEW/PaczkaInfaPG/   # klon repo docelowego; apply pisze do paczka/ (branch subject/{SKROT})
20_WORK/               # organizer.sqlite, extracted_text, thumbnails
90_MEDIA/              # duże wideo/audio wyjęte z paczki
paczka-tools/          # ten klon
```

Wszystkie ścieżki są w `config/paths.yaml` — organizer działa niezależnie od tego,
gdzie leży checkout repo docelowego.
