#!/usr/bin/env bash
# generate.sh — Synapse vault pull-and-regenerate
#
# For the Forgejo-as-intermediary flow: the vault lives on Forgejo,
# the RPi clones it and regenerates on demand (cron or webhook).
#
# Handles its own flock-based locking — safe to call from cron and webhook
# concurrently; the second caller logs and exits without re-running.
#
# Install at: /opt/synapse/generate.sh
# Make executable: chmod +x /opt/synapse/generate.sh

set -euo pipefail

# ── Configuration (override via environment) ──────────────────────────────────

SYNAPSE_BRANCH="${SYNAPSE_BRANCH:-main}"
SYNAPSE_GENERATOR_BIN="${SYNAPSE_GENERATOR_BIN:-/opt/synapse/Synapse.Generator}"
VAULT_DIR="${VAULT_DIR:-/opt/synapse/vault}"
SYNAPSE_CONFIG="${SYNAPSE_CONFIG:-/opt/synapse/generator.config.json}"
SYNAPSE_OUTPUT="${SYNAPSE_OUTPUT:-/opt/synapse/viewer/graph.json}"
SYNAPSE_LOG="${SYNAPSE_LOG:-/var/log/synapse-generator.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/synapse-generator.lock}"

# ── Helpers ───────────────────────────────────────────────────────────────────

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$SYNAPSE_LOG"
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    exec 9>"$LOCK_FILE"
    if ! flock --nonblock 9; then
        log "INFO  Generator already running (lock held). Skipping this trigger."
        return 0
    fi

    log "INFO  ── Synapse generation started ──────────────────────────────"
    local start_ts
    start_ts=$(date +%s)

    # ── Pull latest vault from Forgejo ────────────────────────────────────────

    log "INFO  Fetching origin/$SYNAPSE_BRANCH into $VAULT_DIR"
    git -C "$VAULT_DIR" fetch --quiet origin
    git -C "$VAULT_DIR" reset --hard "origin/$SYNAPSE_BRANCH"

    # ── Run generator ─────────────────────────────────────────────────────────

    log "INFO  Running generator: $SYNAPSE_GENERATOR_BIN"
    local gen_output
    gen_output=$("$SYNAPSE_GENERATOR_BIN" \
        --vault  "$VAULT_DIR" \
        --config "$SYNAPSE_CONFIG" \
        --out    "$SYNAPSE_OUTPUT" 2>&1)
    local gen_exit=$?

    if [[ $gen_exit -ne 0 ]]; then
        log "ERROR Generator exited with code $gen_exit"
        log "      Output: $gen_output"
    else
        log "INFO  $gen_output"
        local end_ts elapsed
        end_ts=$(date +%s)
        elapsed=$(( end_ts - start_ts ))
        log "INFO  graph.json + search-index.json written (${elapsed}s)"
    fi

    log "INFO  ── Synapse generation complete ─────────────────────────────"
}

main "$@" || log "ERROR Unexpected error in generate.sh (exit code $?)."
