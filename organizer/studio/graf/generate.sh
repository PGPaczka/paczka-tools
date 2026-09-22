#!/usr/bin/env bash
# Sync vault from Forgejo, regenerate graph.json, copy .md files to public/vault/
#
# Usage:
#   ./generate.sh                       # use existing Vault/informatyka clone
#   ./generate.sh --remote <url>        # clone/pull from given URL first
#   ./generate.sh --vault <path>        # override vault directory (default: Vault/informatyka)
#   ./generate.sh --out <path>          # override output graph.json path
#
# Environment variables (alternative to flags):
#   VAULT_REMOTE  — Forgejo repo URL, e.g. http://forgejo:3000/user/informatyka.git
#   VAULT_DIR     — path to vault clone (default: Vault/informatyka)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
VAULT_DIR="${VAULT_DIR:-$SCRIPT_DIR/Vault/informatyka}"
OUT="${OUT:-$SCRIPT_DIR/synapse-viewer/public/graph.json}"
VAULT_REMOTE="${VAULT_REMOTE:-}"
PUBLIC_VAULT="$SCRIPT_DIR/synapse-viewer/public/vault"

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) VAULT_REMOTE="$2"; shift 2 ;;
    --vault)  VAULT_DIR="$2";   shift 2 ;;
    --out)    OUT="$2";         shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── 1. Clone or pull vault ────────────────────────────────────────────────────
if [[ -d "$VAULT_DIR/.git" ]]; then
  echo "→ Pulling vault at $VAULT_DIR"
  git -C "$VAULT_DIR" pull --ff-only --quiet
elif [[ -n "$VAULT_REMOTE" ]]; then
  echo "→ Cloning vault from $VAULT_REMOTE"
  git clone "$VAULT_REMOTE" "$VAULT_DIR"
else
  if [[ ! -d "$VAULT_DIR" ]]; then
    echo "Error: vault not found at $VAULT_DIR and --remote / VAULT_REMOTE not set." >&2
    echo "Provide the Forgejo repo URL: ./generate.sh --remote http://forgejo:3000/user/vault.git" >&2
    exit 1
  fi
  echo "→ Using existing vault at $VAULT_DIR (no git remote configured)"
fi

# ── 2. Run generator ──────────────────────────────────────────────────────────
echo "→ Generating $OUT"

BIN="$SCRIPT_DIR/Synapse.Generator/publish/Synapse.Generator"
DLL="$SCRIPT_DIR/Synapse.Generator/Synapse.Generator/bin/Release/net8.0/Synapse.Generator.dll"
CSPROJ="$SCRIPT_DIR/Synapse.Generator/Synapse.Generator/Synapse.Generator.csproj"

run_generator() {
  "$@" --vault "$VAULT_DIR" --out "$OUT"
}

if [[ -x "$BIN" ]] && "$BIN" --help &>/dev/null 2>&1; then
  run_generator "$BIN"
elif command -v dotnet &>/dev/null; then
  [[ -f "$DLL" ]] || dotnet build "$CSPROJ" -c Release --nologo -q
  run_generator dotnet "$DLL"
else
  echo "Error: Synapse.Generator binary not found and dotnet is not installed." >&2
  exit 1
fi

# ── 3. Sync .md files to public/vault/ ───────────────────────────────────────
echo "→ Syncing .md files to $PUBLIC_VAULT"
mkdir -p "$PUBLIC_VAULT"

if command -v rsync &>/dev/null; then
  rsync -a --delete \
    --include="*/" --include="*.md" --exclude="*" \
    "$VAULT_DIR/" "$PUBLIC_VAULT/"
else
  # Fallback: find + cp (no rsync on some systems)
  find "$VAULT_DIR" -name "*.md" | while IFS= read -r src; do
    rel="${src#$VAULT_DIR/}"
    dst="$PUBLIC_VAULT/$rel"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  done
fi

echo "✓ Done"
