#!/usr/bin/env bash
# verify-prior-art-sync.sh — Check/fix/list prior-art-check-consumption sentinel blocks across reviewer consumers.
#
# Usage:
#   verify-prior-art-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-prior-art-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-prior-art-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN prior-art-check-consumption (synced from snippets/prior-art-check-consumption.md) -->
#   <!-- END prior-art-check-consumption -->
#
# A file is a "consumer" only if it has the BEGIN sentinel on its own line (i.e., the sentinel
# is the actual block opener, not merely mentioned in prose). The CLAUDE.md tripwire stanza
# mentions the sentinel inline in a backtick span and is therefore NOT a consumer.

set -euo pipefail

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

# Self-claim: source coordinator session lib for touch tracking.
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
# Best-effort — no-op if lib absent or no active session.
_CS_LIB="$(cd "$(dirname "$0")/.." && pwd)/lib/coordinator-session.sh"
[[ ! -f "$_CS_LIB" ]] && _CS_LIB="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"
if [[ -f "$_CS_LIB" ]]; then
    # shellcheck source=/dev/null
    source "$_CS_LIB"
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

BEGIN_SENTINEL='<!-- BEGIN prior-art-check-consumption (synced from snippets/prior-art-check-consumption.md) -->'
END_SENTINEL='<!-- END prior-art-check-consumption -->'

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/prior-art-check-consumption.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

MODE="${1:-verify}"

# --- hardcoded consumer list ---
# These are the 5 live reviewer prompt files that carry the prior-art-check-consumption sentinel.
# Mirror of verify-docs-checker-sync.sh consumer list.
HARDCODED_CONSUMERS=(
    "$PLUGIN_ROOT/agents/staff-eng.md"
    "$PLUGIN_ROOT/../game-dev/agents/staff-game-dev.md"
    "$PLUGIN_ROOT/../data-science/agents/staff-data-sci.md"
    "$PLUGIN_ROOT/../web-dev/agents/senior-front-end.md"
    "$PLUGIN_ROOT/../../claude-unreal-holodeck/game-dev/agents/staff-game-dev.md"
)

# --- find consumers ---
find_consumers() {
    for f in "${HARDCODED_CONSUMERS[@]}"; do
        if [ ! -f "$f" ]; then
            if [ "$MODE" != "--list" ]; then
                echo "SKIPPED (not found): $f" >&2
            fi
            continue
        fi
        if awk -v s="$BEGIN_SENTINEL" '
            { stripped = $0; gsub(/^[[:space:]]+|[[:space:]]+$/, "", stripped); if (index(stripped, s) && stripped == s) { found=1; exit } }
            END { exit !found }
        ' "$f" 2>/dev/null; then
            printf '%s\n' "$f"
        fi
    done
}

CONSUMERS="$(find_consumers)"

if [ -z "$CONSUMERS" ]; then
    echo "no consumers found — nothing to verify (run --fix on the consumer files first to insert sentinel blocks)"
    exit 0
fi

if [ "$MODE" = "--list" ]; then
    echo "$CONSUMERS"
    exit 0
fi

extract_block() {
    local file="$1"
    node "$SCRIPT_DIR/lib/sentinel-blocks-cli.js" extract "$file" "$BEGIN_SENTINEL" "$END_SENTINEL"
}

# Read snippet body: skip the first line (comment header) and any following blank line.
SNIPPET_BODY="$(awk 'NR>2' "$SNIPPET_FILE")"

normalize() {
    printf '%s' "$1" | sed 's/[[:space:]]*$//' | sed -e '/./,$!d' | sed -e :loop -e '/^\n*$/{$d;N;b loop}'
}

SNIPPET_NORM="$(normalize "$SNIPPET_BODY")"

EXIT_CODE=0

while IFS= read -r consumer; do
    if ! grep -qF "$END_SENTINEL" "$consumer"; then
        echo "MISSING_END  $consumer"
        EXIT_CODE=1
        continue
    fi

    BLOCK_CONTENT="$(extract_block "$consumer")"
    BLOCK_NORM="$(normalize "$BLOCK_CONTENT")"

    if [ "$BLOCK_NORM" = "$SNIPPET_NORM" ]; then
        echo "OK           $consumer"
    else
        if [ "$MODE" = "--fix" ]; then
            "$PYTHON_BIN" - "$consumer" "$BEGIN_SENTINEL" "$END_SENTINEL" "$SNIPPET_BODY" <<'PYEOF'
import sys, pathlib

fpath = pathlib.Path(sys.argv[1])
begin = sys.argv[2]
end   = sys.argv[3]
body  = sys.argv[4]

lines = fpath.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
in_block = False
for line in lines:
    stripped = line.rstrip("\r\n")
    if stripped == begin:
        out.append(line)
        out.append(body if body.endswith("\n") else body + "\n")
        in_block = True
        continue
    if stripped == end:
        in_block = False
        out.append(line)
        continue
    if not in_block:
        out.append(line)

fpath.write_text("".join(out), encoding="utf-8")
PYEOF
            echo "FIXED        $consumer"
            _cs_claim_if_session "$consumer"
        else
            echo "MISMATCH     $consumer"
            EXIT_CODE=1
        fi
    fi
done <<< "$CONSUMERS"

exit $EXIT_CODE
