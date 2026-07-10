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

# Review: code-reviewer (F6) — mapfile is bash-4+; fail-loud on 3.2 per DR-148.
if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: bash 4+ required (found ${BASH_VERSION}). brew install bash" >&2
    exit 2
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

NODE_BIN="${NODE_BIN:-node}"
if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
    echo "ERROR: node not found (set NODE_BIN to override)" >&2
    exit 2
fi

# Self-claim: source coordinator session lib for touch tracking.
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
# Best-effort — no-op if lib absent or no active session.
_CS_LIB="$(cd "$(dirname "$0")/.." && pwd)/lib/coordinator-session.sh"
if [[ ! -f "$_CS_LIB" ]]; then
    _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)"
    if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
        _CS_LIB="${CLAUDE_PLUGIN_ROOT}/lib/coordinator-session.sh"
    elif [ -n "$_doe_root" ] && [ -d "$_doe_root/coordinator" ]; then
        _CS_LIB="$_doe_root/coordinator/lib/coordinator-session.sh"
    fi
fi
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

# --- registry-sourced consumer list ---
# Spec backlink: docs/plans/2026-06-15-snippet-sync-consumer-registry.md § C5d
# Review: code-reviewer (F3) — C5d migration was missing spec backlink; added adjacent to REGISTRY_CLI block.
# Review: code-reviewer (F9) — REGISTRY_CLI guard before MODE (unconditional dependency).
REGISTRY_CLI="$SCRIPT_DIR/snippet-registry"
if [[ ! -x "$REGISTRY_CLI" ]]; then
    echo "ERROR: $REGISTRY_CLI not found or not executable — snippet-registry CLI required" >&2
    exit 2
fi

MODE="${1:-verify}"

# Review: code-reviewer (F5) — unknown MODE values were silently falling through to verify path.
case "${MODE}" in verify|--fix|--list) ;;
  *) echo "ERROR: unknown argument '${MODE}'" >&2; exit 2 ;; esac

mapfile -t HARDCODED_CONSUMERS < <("$REGISTRY_CLI" list-consumers prior-art-check-consumption)

# --- find consumers ---
find_consumers() {
    for f in "${HARDCODED_CONSUMERS[@]}"; do
        if [ ! -f "$f" ]; then
            # Review: code-reviewer (F8) — always emit SKIPPED to stderr; stderr won't pollute --list stdout.
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
    "$NODE_BIN" "$SCRIPT_DIR/lib/sentinel-blocks-cli.js" extract "$file" "$BEGIN_SENTINEL" "$END_SENTINEL" # verify-no-console-flash: allow — on-demand sync verifier, not session-hot-path
}

# Review: code-reviewer (F1) — sentinel-anchored extraction; resilient to future header additions.
# Extract body between BEGIN/END sentinels.
SNIPPET_BODY="$(awk -v b="$BEGIN_SENTINEL" -v e="$END_SENTINEL" '$0==b{p=1;next} $0==e{p=0} p' "$SNIPPET_FILE")"

# shellcheck source=../lib/normalize-snippet.sh
source "$SCRIPT_DIR/../lib/normalize-snippet.sh"

SNIPPET_NORM="$(normalize "$SNIPPET_BODY")"

# Fail-loud guard: an empty canonical body means $SNIPPET_FILE is missing its
# BEGIN/END sentinel wrappers (the sentinel-anchored awk above extracts nothing).
# Proceeding would report every consumer OK against empty — and on --fix would
# WIPE every consumer's block. Refuse rather than silently corrupt. (2026-06-19)
if [ -z "$SNIPPET_NORM" ]; then
    echo "ERROR: canonical snippet body is empty — $SNIPPET_FILE is missing its BEGIN/END sentinel wrappers." >&2
    echo "       Expected '$BEGIN_SENTINEL' ... '$END_SENTINEL' around the body. Refusing to verify/fix (would wipe consumer blocks)." >&2
    exit 2
fi

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
            "$PYTHON_BIN" - "$consumer" "$BEGIN_SENTINEL" "$END_SENTINEL" "$SNIPPET_BODY" <<'PYEOF' # verify-no-console-flash: allow — on-demand sync verifier --fix mode, not session-hot-path
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
