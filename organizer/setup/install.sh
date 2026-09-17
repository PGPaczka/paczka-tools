#!/usr/bin/env bash
# install.sh — jednorazowa, idempotentna instalacja środowiska Paczka Organizer + Claude Code.
#
# Stawia: plugin muxer, status line, jq/rmlint/tesseract (opt-in apt), just, katalogi workspace,
# venv organizera, ustawienia lokalne Claude Code z bezwzględnymi ścieżkami.
# Co i dlaczego: setup/PLUGINS.md. Uruchamiaj z dowolnego miejsca; można wielokrotnie.
#
#   bash setup/install.sh                 # wszystko poza apt i chmod
#   bash setup/install.sh --with-apt      # + sudo apt install (jq rmlint tesseract poppler ncdu)
#   bash setup/install.sh --lock-sources  # + chmod -R a-w na 00_SOURCES (read-only na poziomie FS)
#   bash setup/install.sh --refresh-agents# nadpisz .claude/agents/ świeżą kopią z VoltAgent (UWAGA: gubi audyt)
#   bash setup/install.sh --no-plugins    # pomiń muxer/statusline (np. na maszynie bez Claude Code)
set -euo pipefail

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORGANIZER="$(cd "$SETUP_DIR/.." && pwd)"
TOOLS_ROOT="$(cd "$ORGANIZER/.." && pwd)"
VENDOR="$HOME/.claude/vendor"

WITH_APT=0; LOCK_SOURCES=0; REFRESH_AGENTS=0; NO_PLUGINS=0
for a in "$@"; do
  case "$a" in
    --with-apt) WITH_APT=1 ;;
    --lock-sources) LOCK_SOURCES=1 ;;
    --refresh-agents) REFRESH_AGENTS=1 ;;
    --no-plugins) NO_PLUGINS=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "nieznana flaga: $a" >&2; exit 1 ;;
  esac
done

say()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '   \033[31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. preflight
say "0/8 preflight"
for c in git python3; do command -v "$c" >/dev/null || die "brak: $c"; done
ok "git $(git --version | awk '{print $3}'), python $(python3 --version | awk '{print $2}')"
if command -v claude >/dev/null; then ok "claude $(claude --version 2>/dev/null | head -1)"; else
  warn "brak 'claude' w PATH — pomijam pluginy (jak --no-plugins)"; NO_PLUGINS=1; fi
command -v gh >/dev/null && ok "gh $(gh --version | head -1 | awk '{print $3}')" || warn "brak gh — skille subject-start/ship nie zadziałają"

# ------------------------------------------------------------- 1. paths.yaml
say "1/8 config/paths.yaml → katalogi workspace"
yv() { grep -E "^\s*$1\s*:" "$ORGANIZER/config/paths.yaml" | sed -E 's/^[^:]+:\s*//; s/\s*#.*$//; s/^["'"'"']|["'"'"']$//g' | head -1; }
SRC="$(cd "$ORGANIZER" && realpath -m "$(yv sources)")"
WORK="$(cd "$ORGANIZER" && realpath -m "$(yv work)")"
MEDIA="$(cd "$ORGANIZER" && realpath -m "$(yv media)")"
TARGET="$(cd "$ORGANIZER" && realpath -m "$(yv target_repo)")"
TARGET_SUB="$(yv target_paczka_subdir)"
[ -n "$SRC" ] && [ -n "$WORK" ] && [ -n "$MEDIA" ] && [ -n "$TARGET" ] || die "config/paths.yaml niekompletny"
mkdir -p "$WORK" "$MEDIA"; ok "work:   $WORK"; ok "media:  $MEDIA"
[ -d "$SRC" ] && ok "sources: $SRC ($(find "$SRC" -maxdepth 1 -mindepth 1 -type d | wc -l) paczek)" || warn "sources nie istnieje: $SRC (pobierz przez multi-folder-downloader)"
[ -d "$TARGET/.git" ] && ok "target: $TARGET ($(git -C "$TARGET" remote get-url origin 2>/dev/null || echo 'bez remote'))" || warn "target nie jest klonem git: $TARGET"
[ -d "$TARGET/$TARGET_SUB" ] && ok "target/$TARGET_SUB istnieje" || warn "brak $TARGET/$TARGET_SUB"

# -------------------------------------------------------------------- 2. apt
say "2/8 pakiety systemowe"
APT_PKGS=(jq rmlint ncdu tesseract-ocr tesseract-ocr-pol poppler-utils)
if [ "$WITH_APT" = 1 ]; then
  sudo apt-get update -qq && sudo apt-get install -y -qq "${APT_PKGS[@]}" && ok "apt: ${APT_PKGS[*]}"
else
  missing=(); for p in jq rmlint ncdu tesseract pdftotext; do command -v "$p" >/dev/null || missing+=("$p"); done
  [ "${#missing[@]}" = 0 ] && ok "wszystko jest" || warn "brakuje: ${missing[*]} → uruchom z --with-apt (jq jest WYMAGANE przez hooki muxera)"
fi
# just (runner) — binarka, bez sudo
if command -v just >/dev/null; then ok "just $(just --version | awk '{print $2}')"; else
  mkdir -p "$HOME/.local/bin"
  if curl -fsSL https://just.systems/install.sh | bash -s -- --to "$HOME/.local/bin" >/dev/null 2>&1; then
    ok "just → ~/.local/bin/just (dodaj ~/.local/bin do PATH, jeśli trzeba)"; else warn "instalacja just nie powiodła się (opcjonalny)"; fi
fi

# ------------------------------------------------------------------ 3. muxer
say "3/8 plugin muxer"
if [ "$NO_PLUGINS" = 0 ]; then
  mkdir -p "$VENDOR"
  if [ -d "$VENDOR/muxer/.git" ]; then git -C "$VENDOR/muxer" pull -q --ff-only && ok "muxer zaktualizowany";
  else git clone -q https://github.com/DangerousYams/muxer.git "$VENDOR/muxer" && ok "muxer sklonowany → $VENDOR/muxer"; fi
  if claude plugin marketplace list 2>/dev/null | grep -q "muxer-local"; then ok "marketplace muxer-local już dodany";
  else claude plugin marketplace add "$VENDOR/muxer" >/dev/null && ok "marketplace muxer-local dodany"; fi
  if claude plugin list 2>/dev/null | grep -q "muxer@muxer-local"; then ok "plugin muxer już zainstalowany";
  else claude plugin install muxer@muxer-local --scope user >/dev/null && ok "plugin muxer zainstalowany (scope user)"; fi
  command -v jq >/dev/null || warn "muxer bez jq NIE działa (hooki fail-open) — zainstaluj jq"
else warn "pominięte (--no-plugins)"; fi

# -------------------------------------------------------- 4. agenty VoltAgent
say "4/8 agenty VoltAgent (.claude/agents)"
AGENTS_DIR="$ORGANIZER/.claude/agents"; mkdir -p "$AGENTS_DIR"
declare -A AG=(
  [python-pro]="02-language-specialists/python-pro.md|sonnet|Read, Write, Edit, Bash, Glob, Grep"
  [sql-pro]="02-language-specialists/sql-pro.md|sonnet|Read, Write, Edit, Bash, Glob, Grep"
  [test-automator]="04-quality-security/test-automator.md|sonnet|Read, Write, Edit, Bash, Glob, Grep"
  [documentation-engineer]="06-developer-experience/documentation-engineer.md|haiku|Read, Write, Edit, Glob, Grep"
  [readme-generator]="06-developer-experience/readme-generator.md|haiku|Read, Write, Edit, Glob, Grep"
)
need=0; for n in "${!AG[@]}"; do [ -f "$AGENTS_DIR/$n.md" ] || need=1; done
if [ "$need" = 1 ] || [ "$REFRESH_AGENTS" = 1 ]; then
  VA="$VENDOR/awesome-claude-code-subagents"
  if [ ! -d "$VA/.git" ]; then
    git clone -q --depth 1 --filter=blob:none --sparse https://github.com/VoltAgent/awesome-claude-code-subagents.git "$VA"
    git -C "$VA" sparse-checkout set categories/02-language-specialists categories/04-quality-security categories/06-developer-experience -q
  else git -C "$VA" pull -q --ff-only || true; fi
  for n in "${!AG[@]}"; do
    IFS='|' read -r rel model tools <<<"${AG[$n]}"
    if [ -f "$AGENTS_DIR/$n.md" ] && [ "$REFRESH_AGENTS" = 0 ]; then continue; fi
    python3 - "$VA/categories/$rel" "$AGENTS_DIR/$n.md" "$model" "$tools" "$rel" <<'PY'
import re, sys, pathlib
src, dst, model, tools, rel = sys.argv[1:6]
t = pathlib.Path(src).read_text(encoding="utf-8")
m = re.match(r"^---\n(.*?)\n---\n", t, re.S); fm, body = m.group(1), t[m.end():]
fm = re.sub(r"^model:.*$", f"model: {model}", fm, flags=re.M)
fm = re.sub(r"^tools:.*$", f"tools: {tools}", fm, flags=re.M)
fm += f"\n# źródło: VoltAgent/awesome-claude-code-subagents categories/{rel}; model/tools zaudytowane pod organizer"
pre = """
## Kontekst projektu (Paczka Organizer) — czytaj najpierw

- Pracujesz w `paczka-tools/organizer/`. Zanim cokolwiek zrobisz, przeczytaj `CLAUDE.md` i `AGENTS.md`
  z tego katalogu; ścieżki do katalogów zewnętrznych są TYLKO w `config/paths.yaml`.
- `00_SOURCES` jest READ-ONLY. Nigdy nie zapisuj, nie przenoś, nie kasuj tam niczego.
- Nie otwieraj binariów ze źródeł; pracujesz na kodzie, configu i tekstowych raportach.
- Skrypty muszą być idempotentne i wznawialne (status w SQLite, UPSERT po sha256), zgodnie z
  `docs/ARCHITEKTURA_FINALv1.md`. Nic nie kasuje plików automatycznie.
- Na koniec zwróć **zwięzłe podsumowanie (≤30 linii)**: co zmieniłeś (pliki), jak to sprawdzić,
  co zostało otwarte. Nigdy nie wklejaj całych plików do odpowiedzi — koordynator płaci za każdy token.

"""
pathlib.Path(dst).write_text(f"---\n{fm}\n---\n{pre}{body.lstrip()}", encoding="utf-8")
PY
    ok "$n.md ← $rel (model: $model)"
  done
else ok "5 agentów już jest (commitowane; --refresh-agents nadpisze)"; fi

# ------------------------------------------------------------- 5. status line
say "5/8 status line (~/.claude/statuslines)"
if [ "$NO_PLUGINS" = 0 ]; then
  mkdir -p "$HOME/.claude/statuslines"
  install -m 0755 "$SETUP_DIR/statusline.sh" "$HOME/.claude/statuslines/statusline.sh"
  python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys, pathlib, shutil, time
p = pathlib.Path(sys.argv[1]); d = {}
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8") or "{}")
    shutil.copy(p, p.with_suffix(f".json.bak-{time.strftime('%Y%m%d%H%M%S')}"))
want = {"type": "command", "command": "~/.claude/statuslines/statusline.sh", "padding": 0}
if d.get("statusLine") != want:
    d["statusLine"] = want
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print("   ✔ statusLine dopisany do ~/.claude/settings.json")
else: print("   ✔ statusLine już ustawiony")
PY
else warn "pominięte (--no-plugins)"; fi

# ------------------------------------------ 6. settings.local.json (ścieżki bezwzględne)
say "6/8 paczka-tools/.claude/settings.local.json (ścieżki bezwzględne tej maszyny)"
mkdir -p "$TOOLS_ROOT/.claude"
python3 - "$TOOLS_ROOT/.claude/settings.local.json" "$SRC" "$TARGET" "$WORK" "$MEDIA" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); src, target, work, media = sys.argv[2:6]
d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
perm = d.setdefault("permissions", {})
perm["additionalDirectories"] = [src, target, work, media]
deny = [x for x in perm.get("deny", []) if "00_SOURCES" not in x]
deny.append(f"Edit(//{src.lstrip('/')}/**)")
perm["deny"] = deny
d["_comment"] = "Generowane przez organizer/setup/install.sh z config/paths.yaml. Nie commitować."
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("   ✔", p)
PY

# --------------------------------------------------------------------- 7. venv
say "7/8 venv organizera"
if [ ! -x "$ORGANIZER/.venv/bin/python" ]; then python3 -m venv "$ORGANIZER/.venv" && ok "venv utworzony"; else ok "venv istnieje"; fi
"$ORGANIZER/.venv/bin/pip" install -q --upgrade pip >/dev/null
"$ORGANIZER/.venv/bin/pip" install -q -r "$SETUP_DIR/requirements.txt" && ok "requirements.txt zainstalowane"

# ------------------------------------------------------------- 8. lock sources
say "8/8 ochrona 00_SOURCES"
if [ "$LOCK_SOURCES" = 1 ] && [ -d "$SRC" ]; then chmod -R a-w "$SRC" && ok "chmod -R a-w $SRC"; else ok "hook .claude/hooks/guard-sources.py aktywny w sesji; --lock-sources dołoży chmod"; fi

say "gotowe"
cat <<TXT
   Następny krok:
     cd "$ORGANIZER" && claude
   W sesji: /mux (tabela routingu), potem mały test z setup/PLUGINS.md → sprawdź raport kosztów.
   Skille: /organizer-first-pass, /organizer-subject AK 3, /organizer-review, /organizer-ship.
TXT
