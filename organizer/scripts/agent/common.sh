#!/usr/bin/env bash
set -euo pipefail

AGENT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORGANIZER="$(cd "$AGENT_SCRIPT_DIR/../.." && pwd)"

yaml_value() {
  local key="$1"
  grep -E "^[[:space:]]*${key}[[:space:]]*:" "$ORGANIZER/config/paths.yaml" \
    | sed -E 's/^[^:]+:[[:space:]]*//; s/[[:space:]]*#.*$//; s/^["'"'"']|["'"'"']$//g' \
    | head -1
}

resolve_config_path() {
  local key="$1"
  local value
  value="$(yaml_value "$key")"
  [ -n "$value" ] || {
    printf 'Brak klucza %s w config/paths.yaml\n' "$key" >&2
    exit 2
  }
  realpath -m "$ORGANIZER/$value"
}

SOURCES="$(resolve_config_path sources)"
WORK="$(resolve_config_path work)"
MEDIA="$(resolve_config_path media)"
TARGET_REPO="$(resolve_config_path target_repo)"
