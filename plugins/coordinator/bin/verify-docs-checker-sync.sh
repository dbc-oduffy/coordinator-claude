#!/usr/bin/env bash
# verify-docs-checker-sync.sh — Check/fix/list docs-checker-consumption sentinel blocks across reviewer consumers.
#
# Usage:
#   verify-docs-checker-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-docs-checker-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-docs-checker-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN docs-checker-consumption (synced from snippets/docs-checker-consumption.md) -->
#   <!-- END docs-checker-consumption -->
#
# A file is a "consumer" only if it has the BEGIN sentinel on its own line (i.e., the sentinel
# is the actual block opener, not merely mentioned in prose). The CLAUDE.md tripwire stanza
# mentions the sentinel inline in a backtick span and is therefore NOT a consumer.

set -euo pipefail

BEGIN_SENTINEL='<!-- BEGIN docs-checker-consumption (synced from snippets/docs-checker-consumption.md) -->'
END_SENTINEL='<!-- END docs-checker-consumption -->'

# Resolve plugin root: from env var, or relative to this script's location.
# SCRIPT_DIR is always set (needed by extract_block shim regardless of CLAUDE_PLUGIN_ROOT).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/docs-checker-consumption.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

MODE="${1:-verify}"

# --- hardcoded consumer list ---
# These are the 5 live reviewer prompt files that carry the docs-checker-consumption sentinel.
# PLUGIN_ROOT resolves to the coordinator plugin dir (e.g. ~/.claude/plugins/coordinator-claude/coordinator).
# Sibling plugins are one level up: $PLUGIN_ROOT/../game-dev, $PLUGIN_ROOT/../data-science, etc.
# The holodeck game-dev copy is listed for completeness; if the file does not exist it is skipped.
HARDCODED_CONSUMERS=(
    "$PLUGIN_ROOT/agents/staff-eng.md"
    "$PLUGIN_ROOT/../game-dev/agents/staff-game-dev.md"
    "$PLUGIN_ROOT/../data-science/agents/staff-data-sci.md"
    "$PLUGIN_ROOT/../web-dev/agents/senior-front-end.md"
    "$PLUGIN_ROOT/../../claude-unreal-holodeck/game-dev/agents/staff-game-dev.md"
)

# --- find consumers ---
# A consumer is a file where the BEGIN sentinel appears as a standalone line.
# For the hardcoded list: include files that exist AND have the sentinel.
# The --list mode shows all hardcoded paths that exist with the sentinel.
find_consumers() {
    for f in "${HARDCODED_CONSUMERS[@]}"; do
        if [ ! -f "$f" ]; then
            if [ "$MODE" != "--list" ]; then
                echo "SKIPPED (not found): $f" >&2
            fi
            continue
        fi
        # Check that the file has at least one line where the trimmed content IS the sentinel.
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

# --- --list mode ---
if [ "$MODE" = "--list" ]; then
    echo "$CONSUMERS"
    exit 0
fi

# --- extract sentinel block content from a file ---
# Delegates to sentinel-blocks-cli.js (bin/lib/sentinel-blocks-cli.js) so the extraction
# logic is shared with verify-preamble-sync.sh and refresh-queries.js — one source of truth.
extract_block() {
    local file="$1"
    node "$SCRIPT_DIR/lib/sentinel-blocks-cli.js" extract "$file" "$BEGIN_SENTINEL" "$END_SENTINEL"
}

# Read snippet body: skip the first line (comment header) and any following blank line.
# The snippet file structure is:
#   line 1: <!-- canonical source ... -->
#   line 2: (blank)
#   line 3+: docs-checker-consumption text
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
            # Replace content between sentinels with the snippet body.
            # Python is the most reliable cross-platform tool for multi-line string replacement.
            python3 - "$consumer" "$BEGIN_SENTINEL" "$END_SENTINEL" "$SNIPPET_BODY" <<'PYEOF'
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
        else
            echo "MISMATCH     $consumer"
            EXIT_CODE=1
        fi
    fi
done <<< "$CONSUMERS"

exit $EXIT_CODE
