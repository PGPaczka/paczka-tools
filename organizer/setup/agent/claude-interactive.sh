#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

command -v claude >/dev/null 2>&1 || {
  echo "Brak 'claude' w PATH." >&2
  exit 1
}

export PACZKA_AGENT_HOST="claude"
# Świadomie BEZ domyślnego PACZKA_LLM_RELATE_BACKEND=claude_cli. Polityka kosztowa
# (config/thresholds.yaml: llm) kieruje classify i relate na codex_cli, żeby praca
# klasyfikacyjna szła na limit ChatGPT, a limit koordynatora zostawał na planowanie.
# Wymuszenie backendu Claude to świadoma decyzja człowieka na jedną sesję:
#   PACZKA_LLM_RELATE_BACKEND=claude_cli just claude
export PACZKA_LLM_RELATE_BACKEND="${PACZKA_LLM_RELATE_BACKEND:-}"
[ -n "$PACZKA_LLM_RELATE_BACKEND" ] || unset PACZKA_LLM_RELATE_BACKEND

cd "$ORGANIZER"
exec claude "$@"
