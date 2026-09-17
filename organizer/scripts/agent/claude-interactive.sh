#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

command -v claude >/dev/null 2>&1 || {
  echo "Brak 'claude' w PATH." >&2
  exit 1
}

export PACZKA_AGENT_HOST="claude"
export PACZKA_LLM_RELATE_BACKEND="${PACZKA_LLM_RELATE_BACKEND:-claude_cli}"

cd "$ORGANIZER"
exec claude "$@"
