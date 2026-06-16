#!/usr/bin/env bash
# verify-meta-ask-preamble-sync.sh — Check/fix/list meta-ask-preamble sentinel blocks across plugin consumers.
#
# Usage:
#   verify-meta-ask-preamble-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-meta-ask-preamble-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-meta-ask-preamble-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN meta-ask-preamble (synced from snippets/meta-ask-preamble.md) -->
#   <!-- END meta-ask-preamble -->
#
# A file is a "consumer" only if it has the BEGIN sentinel on its own line (i.e., the sentinel
# is the actual block opener, not merely mentioned in prose). References to the sentinel inline
# in prose or backtick spans are therefore NOT consumers.
#
# Spec backlink: docs/plans/2026-05-20-eager-agent-calibration.md § Chunk 1

set -euo pipefail

# Portable Python resolver: prefer python3, fall back to python (Windows ships no python3).
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

# Node resolver guard (mirrors verify-calibration-sync.sh) — this script shells out
# to node for sentinel-blocks-cli.js below; a bare `node` fails opaquely when node is
# absent or PATH-shadowed. Fail loud with an NODE_BIN override hook.
NODE_BIN="${NODE_BIN:-node}"
if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
    echo "ERROR: node not found (set NODE_BIN to override)" >&2
    exit 2
fi

# Self-claim: source coordinator session lib for touch tracking.
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

BEGIN_SENTINEL='<!-- BEGIN meta-ask-preamble (synced from snippets/meta-ask-preamble.md) -->'
END_SENTINEL='<!-- END meta-ask-preamble -->'

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/meta-ask-preamble.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

MODE="${1:-verify}"

# --- find consumers ---
# A consumer is a file where the BEGIN sentinel appears as a standalone line
# (the entire trimmed line equals the sentinel). This excludes prose references
# where the sentinel is embedded in backtick spans or other inline text.
find_consumers() {
    local candidates
    candidates="$(grep -rlF "$BEGIN_SENTINEL" "$PLUGIN_ROOT" 2>/dev/null || true)"
    [ -z "$candidates" ] && return 0

    while IFS= read -r f; do
        # A file is a consumer only if the trimmed sentinel is its own line AND that line is
        # NOT inside a ``` fenced code block (a fenced occurrence is a documentation example
        # of the convention, not a live consumer block). in_fence tracking mirrors
        # verify-preamble-sync.sh — keep the two in sync.
        if awk -v s="$BEGIN_SENTINEL" '
            { stripped = $0; gsub(/^[[:space:]]+|[[:space:]]+$/, "", stripped) }
            stripped ~ /^```/ { in_fence = !in_fence; next }
            !in_fence && index(stripped, s) && stripped == s { found=1; exit }
            END { exit !found }
        ' "$f" 2>/dev/null; then
            printf '%s\n' "$f"
        fi
    done <<< "$candidates"
}

CONSUMERS="$(find_consumers)"

if [ -z "$CONSUMERS" ]; then
    echo "no consumers detected — nothing to verify"
    exit 0
fi

# --- --list mode ---
if [ "$MODE" = "--list" ]; then
    echo "$CONSUMERS"
    exit 0
fi

# --- extract sentinel block content from a file ---
extract_block() {
    local file="$1"
    "$NODE_BIN" "$SCRIPT_DIR/lib/sentinel-blocks-cli.js" extract "$file" "$BEGIN_SENTINEL" "$END_SENTINEL" # verify-no-console-flash: allow — on-demand sync verifier, not session-hot-path
}

# Read snippet body: NR>2 skips the snippet header (one comment line + one blank line below it).
# Assumption: snippet file structure is line 1 = comment header, line 2 = blank, line 3+ = body.
# Failure mode: if a snippet ever gains an extra leading blank line after its header, source-side
# (this sed strip) and consumer-side (sentinel-blocks-cli raw extract) will diverge → false MISMATCH.
# Long-term fix: extract-snippet-body mode in bin/lib/sentinel-blocks-cli.js. See BS-2026-05-20-013.
SNIPPET_BODY="$(awk 'NR>2' "$SNIPPET_FILE")"

# Normalize: strip trailing whitespace, collapse trailing blank lines.
normalize() {
    printf '%s' "$1" | sed 's/[[:space:]]*$//' | sed -e '/./,$!d' | sed -e :loop -e '/^\n*$/{$d;N;b loop}'
}

SNIPPET_NORM="$(normalize "$SNIPPET_BODY")"

# --- verify / fix modes ---
EXIT_CODE=0

while IFS= read -r consumer; do
    # Check END sentinel exists
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
