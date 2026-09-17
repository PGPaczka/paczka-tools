#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PROFILE_NAME="${CODEX_PROFILE:-paczka-openai}"
MODEL="${CODEX_MODEL:-gpt-6-astra}"
PROFILE="$CODEX_HOME/$PROFILE_NAME.config.toml"

mkdir -p "$CODEX_HOME"
cat >"$PROFILE" <<EOF
# Generowane przez paczka-tools/organizer/setup/install-agent-profiles.sh.
# Profil interaktywnego Codexa niezależny od claude-code-router.
model_provider = "openai"
model = "$MODEL"
model_reasoning_effort = "high"
forced_login_method = "chatgpt"
EOF

echo "Utworzono profil Codexa: $PROFILE"
if command -v codex >/dev/null 2>&1; then
  codex login status || true
else
  echo "Brak 'codex' w PATH — profil jest gotowy, ale CLI wymaga instalacji." >&2
fi
