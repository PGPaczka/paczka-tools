#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

failed=0
check_command() {
  local command="$1"
  if command -v "$command" >/dev/null 2>&1; then
    printf 'OK   %-10s %s\n' "$command" "$(command -v "$command")"
  else
    printf 'BRAK %-10s\n' "$command"
    failed=1
  fi
}

check_command git
check_command python3
check_command claude
check_command codex
check_command just

profile="${CODEX_PROFILE:-paczka-openai}"
profile_file="${CODEX_HOME:-$HOME/.codex}/$profile.config.toml"
if [ -f "$profile_file" ] && grep -Eq 'model_provider[[:space:]]*=[[:space:]]*"openai"' "$profile_file"; then
  echo "OK   profil Codexa: $profile_file (OpenAI)"
else
  echo "BRAK/popraw profil Codexa: $profile_file"
  failed=1
fi

[ -d "$SOURCES" ] && echo "OK   sources istnieje (nie jest dodawany jako writable root)" || echo "WARN sources nie istnieje"
[ -d "$WORK" ] && echo "OK   work: $WORK" || echo "WARN work zostanie utworzony przy starcie"
[ -d "$TARGET_REPO/.git" ] && echo "OK   target_repo: $TARGET_REPO" || echo "WARN target_repo nie jest klonem git"

if command -v codex >/dev/null 2>&1; then
  codex login status || failed=1
fi

exit "$failed"
