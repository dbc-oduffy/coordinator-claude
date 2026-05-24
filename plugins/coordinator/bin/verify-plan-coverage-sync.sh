#!/usr/bin/env bash
# verify-plan-coverage-sync.sh — Check/fix/list plan-coverage-check-consumption sentinel blocks across reviewer consumers.
#
# Usage:
#   verify-plan-coverage-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-plan-coverage-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-plan-coverage-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->
#   <!-- END plan-coverage-check-consumption -->
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

# Review: code-reviewer — node is required by sentinel-blocks-cli.js (extract_block); missing node caused a confusing runtime error rather than a clear startup failure.
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: node not found on PATH (required for sentinel-blocks-cli.js)" >&2
    exit 2
fi

# Self-claim: source coordinator session lib for touch tracking.
# Spec backlink: ~/.claude/plugins/coordinator/snippets/plan-coverage-check-consumption.md
# Best-effort — no-op if lib absent or no active session.
_CS_LIB="$(cd "$(dirname "$0")/.." && pwd)/lib/coordinator-session.sh"
[[ ! -f "$_CS_LIB" ]] && _CS_LIB="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"
if [[ -f "$_CS_LIB" ]]; then
    # shellcheck source=/dev/null
    source "$_CS_LIB"
    _CS_LIB_LOADED=1
else
    _CS_LIB_LOADED=0
fi

_cs_claim_if_session() {
    # Delegate to the shared lib helper (env-var fast path; falls back to a
    # live-session scan only on old Claude Code). Single source of truth in
    # lib/coordinator-session.sh::cs_self_claim.
    [[ "$_CS_LIB_LOADED" -eq 0 ]] && return 0
    command -v cs_self_claim &>/dev/null || return 0  # version-skew guard
    cs_self_claim "$1"
}

BEGIN_SENTINEL='<!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->'
END_SENTINEL='<!-- END plan-coverage-check-consumption -->'

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/plan-coverage-check-consumption.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# machine-local resolver (mirrors bin/verify-ue-overrides.sh § resolve_key)
# ---------------------------------------------------------------------------
# Used to resolve the holodeck sibling-repo path from the per-machine registry
# rather than hardcoding /x/claude-unreal-holodeck. Env var HOLODECK_REPO_ROOT
# still takes precedence (env > registry > skip) for ad-hoc overrides.
ML_BIN=""
if command -v machine-local >/dev/null 2>&1; then
    ML_BIN="machine-local"
elif [[ -x "$HOME/.claude/bin/machine-local" ]]; then
    ML_BIN="$HOME/.claude/bin/machine-local"
elif [[ -x "$SCRIPT_DIR/machine-local" ]]; then
    ML_BIN="$SCRIPT_DIR/machine-local"
fi

# Resolve a machine-local key; print empty string on miss (caller decides whether
# to fail or skip). Unlike verify-ue-overrides.sh's resolve_key (which is fail-loud),
# this variant is skip-friendly: the holodeck sibling repo is an optional consumer,
# and a missing key should let the script continue with the other consumers.
resolve_key_or_empty() {
    local key="$1"
    [[ -z "$ML_BIN" ]] && return 0
    "$ML_BIN" get "$key" 2>/dev/null || true
}

MODE="${1:-verify}"

# Review: code-reviewer — unknown MODE values silently fell through to the verify path; guard ensures callers get an error on typos.
case "${MODE}" in verify|--fix|--list) ;;
  *) echo "ERROR: unknown argument '${MODE}'" >&2; exit 2 ;; esac

# --- hardcoded consumer list ---
# These are the 5 reviewer prompt files that carry the plan-coverage-check-consumption sentinel:
#   the Staff Engineer (staff-eng), the Game Dev Reviewer (staff-game-dev), the Data Science Reviewer (staff-data-sci), the Front-End Reviewer (senior-front-end), the Director of Engineering (eng-director).
# Spec backlink: docs/plans/2026-05-18-plan-coverage-checker.md § Snippet — snippets/plan-coverage-check-consumption.md
HARDCODED_CONSUMERS=(
    "$PLUGIN_ROOT/agents/staff-eng.md"
    "$PLUGIN_ROOT/../game-dev/agents/staff-game-dev.md"
    "$PLUGIN_ROOT/../data-science/agents/staff-data-sci.md"
    "$PLUGIN_ROOT/../web-dev/agents/senior-front-end.md"
    "$PLUGIN_ROOT/agents/eng-director.md"
)

# Resolve holodeck sibling repo: env var override wins, otherwise machine-local
# registry key repos.claude_unreal_holodeck, otherwise skip the consumer.
# Spec backlink: docs/wiki/machine-local-registry.md § Registered keys
_HOLODECK_ROOT="${HOLODECK_REPO_ROOT:-$(resolve_key_or_empty "repos.claude_unreal_holodeck")}"
if [[ -n "$_HOLODECK_ROOT" ]]; then
    HARDCODED_CONSUMERS+=("$_HOLODECK_ROOT/game-dev/agents/staff-game-dev.md")
else
    echo "NOTE-repos.claude_unreal_holodeck: key unset and HOLODECK_REPO_ROOT empty — skipping holodeck sibling consumer" >&2
fi

# --- find consumers ---
find_consumers() {
    for f in "${HARDCODED_CONSUMERS[@]}"; do
        if [ ! -f "$f" ]; then
            # Review: code-reviewer — SKIPPED warning was suppressed in --list mode, but stderr won't pollute --list stdout; always emit.
            echo "SKIPPED (not found): $f" >&2
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

# Read snippet body: skip the first two lines (comment header + blank) and the surrounding sentinel lines.
# The canonical snippet file has: line 1 = comment header, line 2 = blank, line 3 = BEGIN sentinel,
# lines 4..N-1 = body, line N = END sentinel.
# We want just the body (lines 4..N-1) to compare/inject between the sentinels in consumer files.
# Review: code-reviewer — hardcoded sentinel in awk would silently mismatch if END_SENTINEL drifts; use the variable.
SNIPPET_BODY="$(awk -v end_sentinel="$END_SENTINEL" 'NR>3 && $0 != end_sentinel' "$SNIPPET_FILE")"

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
