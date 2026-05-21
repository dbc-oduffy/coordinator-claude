#!/bin/bash
# check-mcp-versions.sh — Compare pinned MCP server versions against npm latest
#
# Reads pinned versions from settings.json and reports available updates.
# Designed to be called from /workday-start (Tool Availability section).
#
# Respects a 7-day cooldown via a marker file to avoid hammering npm.
# Pass --force to skip the cooldown.

set -euo pipefail

# Self-claim: source coordinator session lib to register the marker file write.
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
# Best-effort — no-op if lib absent or no active session.
_CS_LIB="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"
if [[ -f "$_CS_LIB" ]]; then
    # shellcheck source=/dev/null
    source "$_CS_LIB" 2>/dev/null || true
    _CS_LIB_LOADED=1
else
    _CS_LIB_LOADED=0
fi

_cs_claim_if_session() {
    [[ "$_CS_LIB_LOADED" -eq 0 ]] && return 0
    local _sids
    _sids="$(cs_live_session_ids 2>/dev/null)" || return 0
    local _sid_count
    if [[ -z "$_sids" ]]; then _sid_count=0
    else _sid_count=$(echo "$_sids" | wc -l | tr -d ' \n'); fi
    if [[ "$_sid_count" -eq 0 ]]; then
        echo "coordinator-session: no active session found — skipping self-claim for $1" >&2
        return 0
    fi
    if [[ "$_sid_count" -gt 1 ]]; then
        echo "coordinator-session: ${_sid_count} live sessions (ambiguous) — skipping self-claim for $1" >&2
        return 0
    fi
    local _sid
    _sid=$(echo "$_sids" | head -1)
    local _sdir
    _sdir=$(_cs_session_dir "$_sid" 2>/dev/null) || return 0
    cs_atomic_dedup_append "${_sdir}/touched.txt" "$1" 2>/dev/null || return 0
}

SETTINGS="$HOME/.claude/settings.json"
MARKER="$HOME/.claude/.mcp-version-check"
COOLDOWN_DAYS=7

# --- Cooldown check ---
if [ "${1:-}" != "--force" ] && [ -f "$MARKER" ]; then
    last_check=$(cat "$MARKER" 2>/dev/null)
    last_epoch=$(date -d "$last_check" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$last_check" +%s 2>/dev/null || { echo "WARNING: could not parse last-check date '$last_check' — treating cooldown as expired" >&2; echo 0; })
    now_epoch=$(date +%s)
    age_days=$(( (now_epoch - last_epoch) / 86400 ))
    if [ "$age_days" -lt "$COOLDOWN_DAYS" ]; then
        echo "MCP versions: checked ${age_days}d ago (cooldown: ${COOLDOWN_DAYS}d). Pass --force to recheck."
        exit 0
    fi
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "MCP versions: jq not found, skipping check."
    exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "MCP versions: npm not found, skipping check."
    exit 0
fi

# --- Extract pinned npm packages from settings.json ---
# Looks for args arrays containing npx invocations with pinned versions (pkg@x.y.z)
updates_available=""

check_package() {
    local pkg="$1"
    local pinned="$2"

    latest=$(npm view "$pkg" version 2>/dev/null) || return 0
    if [ -z "$latest" ]; then
        return 0
    fi

    if [ "$pinned" != "$latest" ]; then
        updates_available="true"
        echo "  - **$pkg**: pinned $pinned → latest $latest"
    fi
}

# Parse mcpServers from settings.json for npx-based servers with pinned versions
# Pattern: @scope/package@version or package@version (not @latest)
pinned_packages=$(jq -r '
    .mcpServers // {} | to_entries[] |
    .value.args // [] | .[] |
    select(test("@[0-9]")) |
    capture("(?<pkg>.+)@(?<ver>[0-9][0-9.]*)$") |
    "\(.pkg) \(.ver)"
' "$SETTINGS" 2>/dev/null)

if [ -z "$pinned_packages" ]; then
    echo "MCP versions: no pinned npm packages found in settings.json."
    date +%Y-%m-%d > "$MARKER"
    _cs_claim_if_session "$MARKER"
    exit 0
fi

echo "MCP version check:"
while IFS=' ' read -r pkg ver; do
    [ -z "$pkg" ] && continue
    check_package "$pkg" "$ver"
done <<< "$pinned_packages"

if [ -z "$updates_available" ]; then
    echo "  All pinned MCP packages are current."
fi

# Update marker
date +%Y-%m-%d > "$MARKER"
_cs_claim_if_session "$MARKER"
