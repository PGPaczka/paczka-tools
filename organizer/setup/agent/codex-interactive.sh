#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

usage() {
  cat <<'EOF'
Użycie:
  codex-interactive.sh [--read-only | --ship] [--] [argumenty Codexa...]

Tryby:
  domyślny   workspace-write w organizerze + zapis do 20_WORK
  --read-only bez dodatkowych katalogów zapisu
  --ship     dodatkowo zapis do target_repo i 90_MEDIA; tylko po akceptacji planu

Zmienne:
  CODEX_PROFILE  profil Codexa, domyślnie paczka-openai
  CODEX_MODEL    model, domyślnie gpt-6-astra
EOF
}

mode="dev"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --read-only) mode="read-only"; shift ;;
    --ship) mode="ship"; shift ;;
    --) shift; break ;;
    -h|--help) usage; exit 0 ;;
    *) break ;;
  esac
done

command -v codex >/dev/null 2>&1 || {
  echo "Brak 'codex' w PATH." >&2
  exit 1
}

codex_home="${CODEX_HOME:-$HOME/.codex}"
profile="${CODEX_PROFILE:-paczka-openai}"
profile_file="$codex_home/$profile.config.toml"
model="${CODEX_MODEL:-gpt-6-astra}"

if [ ! -f "$profile_file" ]; then
  echo "Brak profilu $profile_file." >&2
  echo "Uruchom: bash setup/install-agent-profiles.sh" >&2
  exit 2
fi
if ! grep -Eq '^[[:space:]]*model_provider[[:space:]]*=[[:space:]]*"openai"' "$profile_file"; then
  echo "Profil $profile nie wymusza model_provider=\"openai\"; odmawiam startu." >&2
  exit 2
fi

export PACZKA_AGENT_HOST="codex"
export PACZKA_LLM_RELATE_BACKEND="${PACZKA_LLM_RELATE_BACKEND:-codex_cli}"

args=(
  -p "$profile"
  -m "$model"
  -C "$ORGANIZER"
  -a on-request
)

case "$mode" in
  read-only)
    args+=(-s read-only)
    ;;
  dev)
    mkdir -p "$WORK"
    args+=(-s workspace-write --add-dir "$WORK")
    ;;
  ship)
    mkdir -p "$WORK" "$MEDIA"
    [ -d "$TARGET_REPO/.git" ] || {
      echo "target_repo nie jest klonem git: $TARGET_REPO" >&2
      exit 2
    }
    args+=(
      -s workspace-write
      --add-dir "$WORK"
      --add-dir "$TARGET_REPO"
      --add-dir "$MEDIA"
    )
    ;;
esac

cd "$ORGANIZER"
exec codex "${args[@]}" "$@"
