#!/usr/bin/env bash
# verify-text-only-sync.sh — Check/fix/list text-only-recovery-preamble sentinel blocks across consumers.
#
# Usage:
#   verify-text-only-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-text-only-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-text-only-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
#   <!-- END text-only-recovery-preamble -->
#
# Patterned on verify-preamble-sync.sh — same extraction primitive (sentinel-blocks-cli.js).

set -euo pipefail

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

BEGIN_SENTINEL='<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->'
END_SENTINEL='<!-- END text-only-recovery-preamble -->'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# This snippet is consumed by both coordinator/* and deep-research/* — search the
# parent plugin tree, not just coordinator.
SEARCH_ROOT="$(cd "$PLUGIN_ROOT/.." && pwd)"
SNIPPET_FILE="$PLUGIN_ROOT/snippets/text-only-recovery-preamble.md"

if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

MODE="${1:-verify}"

find_consumers() {
    local candidates
    candidates="$(grep -rlF "$BEGIN_SENTINEL" "$SEARCH_ROOT" 2>/dev/null || true)"
    [ -z "$candidates" ] && return 0

    while IFS= read -r f; do
        if awk -v s="$BEGIN_SENTINEL" '
            { stripped = $0; gsub(/^[[:space:]]+|[[:space:]]+$/, "", stripped); if (index(stripped, s) && stripped == s) { found=1; exit } }
            END { exit !found }
        ' "$f" 2>/dev/null; then
            printf '%s\n' "$f"
        fi
    done <<< "$candidates"
}

CONSUMERS="$(find_consumers)"

if [ -z "$CONSUMERS" ]; then
    echo "no consumers found — nothing to verify"
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

SNIPPET_BODY="$(awk 'NR>2' "$SNIPPET_FILE")"

normalize() {
    printf '%s' "$1" | sed 's/[[:space:]]*$//' | sed -e '/./,$!d' | sed -e :loop -e '/^\n*$/{$d;N;b loop}'
}

SNIPPET_NORM="$(normalize "$SNIPPET_BODY")"

EXIT_CODE=0
MISMATCH_COUNT=0

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
        else
            echo "MISMATCH     $consumer"
            EXIT_CODE=1
            MISMATCH_COUNT=$((MISMATCH_COUNT + 1))
        fi
    fi
done <<< "$CONSUMERS"

exit $EXIT_CODE
