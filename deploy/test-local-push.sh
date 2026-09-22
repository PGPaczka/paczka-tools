#!/usr/bin/env bash
# test-local-push.sh — simulate the full RPi push flow locally.
#
# Usage:
#   ./deploy/test-local-push.sh [vault-fixture-path]
#
# If vault-fixture-path is omitted, the script uses the built-in test fixture at
# Synapse.Generator/Synapse.Generator.Tests/Fixtures/Vault (relative to the
# script's parent directory, i.e. the repo root).
#
# The script:
#   1. Creates a temp bare repo and checkout directory.
#   2. Installs the post-receive hook (pointing at the locally published generator).
#   3. Pushes the vault fixture into the bare repo.
#   4. Checks that graph.json was created / updated.
#   5. Cleans up temp directories.
#
# Prerequisites:
#   - Synapse.Generator binary published to Synapse.Generator/publish/Synapse.Generator
#     (run: cd Synapse.Generator && dotnet publish -c Release -r linux-x64 --self-contained)
#   - git available on PATH.

set -euo pipefail

# ── Resolve paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FIXTURE_VAULT="${1:-$REPO_ROOT/Synapse.Generator/Synapse.Generator.Tests/Fixtures/Vault}"
FIXTURE_CONFIG="$REPO_ROOT/Synapse.Generator/Synapse.Generator.Tests/Fixtures/generator.config.json"
GENERATOR_BIN="$REPO_ROOT/Synapse.Generator/publish/Synapse.Generator"
POST_RECEIVE_HOOK="$SCRIPT_DIR/post-receive"

# ── Validate prerequisites ────────────────────────────────────────────────────

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$FIXTURE_VAULT" ]]      || fail "Vault fixture not found: $FIXTURE_VAULT"
[[ -f "$FIXTURE_CONFIG" ]]     || fail "Config fixture not found: $FIXTURE_CONFIG"
[[ -x "$GENERATOR_BIN" ]]      || fail "Generator binary not found or not executable: $GENERATOR_BIN
  Build it with:
    cd '$REPO_ROOT/Synapse.Generator'
    dotnet publish -c Release -r linux-x64 --self-contained -o publish"
[[ -f "$POST_RECEIVE_HOOK" ]]  || fail "post-receive hook not found: $POST_RECEIVE_HOOK"

echo "── Synapse local push simulation ────────────────────────────────────────"
echo "  Vault fixture : $FIXTURE_VAULT"
echo "  Generator     : $GENERATOR_BIN"
echo

# ── Create temp workspace ─────────────────────────────────────────────────────

WORK_DIR="$(mktemp -d /tmp/synapse-test-XXXXXX)"
BARE_REPO="$WORK_DIR/vault.git"
VAULT_CHECKOUT="$WORK_DIR/vault-checkout"
GRAPH_OUT="$WORK_DIR/graph.json"
SYNAPSE_LOG="$WORK_DIR/synapse-generator.log"
LOCK_FILE="$WORK_DIR/synapse-generator.lock"

cleanup() {
    rm -rf "$WORK_DIR"
    echo "Cleaned up $WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$VAULT_CHECKOUT"

echo "Temp workspace : $WORK_DIR"
echo

# ── Initialise bare repo ──────────────────────────────────────────────────────

echo "[1/5] Initialising bare repo at $BARE_REPO"
git init --bare "$BARE_REPO" --quiet

# ── Install post-receive hook ─────────────────────────────────────────────────

echo "[2/5] Installing post-receive hook"
HOOK_DEST="$BARE_REPO/hooks/post-receive"
cp "$POST_RECEIVE_HOOK" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

# Export env vars that the hook reads at runtime.
export SYNAPSE_BRANCH="main"
export SYNAPSE_GENERATOR_BIN="$GENERATOR_BIN"
export VAULT_CHECKOUT="$VAULT_CHECKOUT"
export SYNAPSE_CONFIG="$FIXTURE_CONFIG"
export SYNAPSE_OUTPUT="$GRAPH_OUT"
export SYNAPSE_LOG="$SYNAPSE_LOG"
export LOCK_FILE="$LOCK_FILE"

# ── Clone fixture vault into a local working copy and push ────────────────────

echo "[3/5] Cloning fixture vault and pushing to bare repo"
LOCAL_CLONE="$WORK_DIR/local-clone"

# The fixture vault is a plain directory of .md files, not a git repo.
# We init a fresh repo from it so we can push it.
git init "$LOCAL_CLONE" --quiet
git -C "$LOCAL_CLONE" config user.email "test@local"
git -C "$LOCAL_CLONE" config user.name  "Synapse Test"

# Copy vault files into the clone.
cp -r "$FIXTURE_VAULT"/. "$LOCAL_CLONE/"
git -C "$LOCAL_CLONE" add --all
git -C "$LOCAL_CLONE" commit -m "test: vault fixture" --quiet

git -C "$LOCAL_CLONE" remote add bare "$BARE_REPO"
git -C "$LOCAL_CLONE" push bare "HEAD:refs/heads/main" --quiet

# ── Verify graph.json was produced ───────────────────────────────────────────

echo "[4/5] Verifying graph.json output"
if [[ -f "$GRAPH_OUT" ]]; then
    SIZE=$(wc -c < "$GRAPH_OUT")
    echo "  graph.json written ($SIZE bytes) — OK"
else
    echo "ERROR: graph.json was NOT created. Hook log:" >&2
    cat "$SYNAPSE_LOG" >&2
    exit 1
fi

echo "[5/5] Hook log:"
sed 's/^/  /' "$SYNAPSE_LOG"

echo
echo "── Simulation complete: PASS ─────────────────────────────────────────────"
