#!/usr/bin/env bash
# verify-preamble-sync.sh — Check/fix/list project-rag-preamble sentinel blocks across plugin consumers.
#
# Usage:
#   verify-preamble-sync.sh          Verify all consumers match the canonical snippet. Exit non-zero on mismatch.
#   verify-preamble-sync.sh --fix    Overwrite mismatched sentinel blocks with the canonical snippet.
#   verify-preamble-sync.sh --list   List all consumer files containing the BEGIN sentinel.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
#   <!-- END project-rag-preamble -->
#
# A file is a "consumer" only if it has the BEGIN sentinel on its own line (i.e., the sentinel
# is the actual block opener, not merely mentioned in prose). The CLAUDE.md tripwire stanza
# mentions the sentinel inline in a backtick span and is therefore NOT a consumer.

set -euo pipefail

BEGIN_SENTINEL='<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->'
END_SENTINEL='<!-- END project-rag-preamble -->'

# Resolve plugin root: from env var, or relative to this script's location.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/project-rag-preamble.md"

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
    local results=""
    # First find candidates that contain the sentinel string at all.
    local candidates
    candidates="$(grep -rlF "$BEGIN_SENTINEL" "$PLUGIN_ROOT" 2>/dev/null || true)"
    [ -z "$candidates" ] && return 0

    while IFS= read -r f; do
        # Check that the file has at least one line where the trimmed content IS the sentinel.
        # Use awk with index() for fixed-string matching (avoids regex metacharacter issues
        # with parentheses and dots in the sentinel string — grep -Eq escaping is unreliable
        # on Windows/Git Bash for strings containing '(' and ')').
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

# --- --list mode ---
if [ "$MODE" = "--list" ]; then
    echo "$CONSUMERS"
    exit 0
fi

# --- extract sentinel block content from a file ---
# Prints the lines strictly between BEGIN and END sentinels (exclusive).
# Uses index() in awk for fixed-string matching to avoid regex metacharacter issues.
extract_block() {
    local file="$1"
    awk -v begin="$BEGIN_SENTINEL" -v end="$END_SENTINEL" '
        index($0, begin) { found=1; next }
        index($0, end)   { found=0; next }
        found            { print }
    ' "$file"
}

# Read snippet body: skip the first line (comment header) and any following blank line.
# The snippet file structure is:
#   line 1: <!-- canonical source ... -->
#   line 2: (blank)
#   line 3+: preamble text
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
