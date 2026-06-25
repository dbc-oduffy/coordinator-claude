#!/usr/bin/env bash
# verify-coordinator-daily-branch-sync.sh — Assert lib↔hook inline mirror byte-equality
# for cs_compute_machine and cs_compute_machine_live.
#
# Usage:
#   verify-coordinator-daily-branch-sync.sh          Verify; exit non-zero + diff on drift.
#   verify-coordinator-daily-branch-sync.sh --fix    (no-op — bodies are inline, not
#                                                     sentinel-block replaceable; report
#                                                     MISMATCH and exit 1 so caller edits
#                                                     both files in lockstep)
#   verify-coordinator-daily-branch-sync.sh --list   List the two monitored files.
#
# Monitored pair:
#   lib/coordinator-daily-branch.sh      (authoritative source)
#   hooks/scripts/block-off-daily-branch.sh  (inline fallback mirror)
#
# Each function body is extracted via awk: captures the lines between
# `<name>() {` and the matching closing `}` (accounting for nesting).
#
# Spec backlink: docs/plans/2026-06-22-persist-machine-slug-registry.md § C1 (AC4)
# Snippet-sync sweep: auto-discovered by /update-docs Phase 11b via glob
#   ~/.claude/plugins/*/*/bin/verify-*-sync.sh

set -euo pipefail

# Bash 4+ guard (mapfile, BASH_VERSINFO — required per DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: bash 4+ required (found ${BASH_VERSION}). brew install bash" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

LIB_FILE="$PLUGIN_ROOT/lib/coordinator-daily-branch.sh"
HOOK_FILE="$PLUGIN_ROOT/hooks/scripts/block-off-daily-branch.sh"

MODE="${1:-verify}"

case "${MODE}" in
    verify|--fix|--list) ;;
    *) echo "ERROR: unknown argument '${MODE}'" >&2; exit 2 ;;
esac

if [[ "$MODE" == "--list" ]]; then
    echo "$LIB_FILE"
    echo "$HOOK_FILE"
    exit 0
fi

# Validate files exist
for f in "$LIB_FILE" "$HOOK_FILE"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: file not found: $f" >&2
        exit 2
    fi
done

# extract_function_body <file> <func_name>
# Prints the lines from `<func_name>() {` through the matching closing `}`.
# Uses awk with a brace-depth counter to handle nested braces correctly.
# Exits 1 if the function is not found in the file.
extract_function_body() {
    local file="$1"
    local func="$2"
    awk -v fn="${func}" '
        BEGIN { depth=0; capturing=0; found=0 }
        # Match the opening line of the function (handles leading whitespace for the inline mirror)
        capturing==0 && $0 ~ "^[[:space:]]*" fn "[[:space:]]*\\(\\)[[:space:]]*\\{" {
            capturing=1
            found=1
            depth=0
        }
        capturing==1 {
            # Count brace depth
            n = split($0, chars, "")
            for (i=1; i<=n; i++) {
                if (chars[i] == "{") depth++
                else if (chars[i] == "}") {
                    depth--
                    if (depth == 0) {
                        print
                        capturing=0
                        exit
                    }
                }
            }
            print
        }
        END { if (!found) exit 1 }
    ' "$file"
}

# normalize_body: strip leading whitespace indentation (normalize the 2-space vs 0-space
# indentation difference between lib top-level and hook inline-mirror indented body).
# Strip a common leading indent: count leading spaces on first non-empty line and remove
# that many spaces from all lines.
normalize_body() {
    awk '
        BEGIN { indent=-1 }
        /^[[:space:]]*$/ { print ""; next }
        indent < 0 {
            match($0, /^[[:space:]]*/)
            indent = RLENGTH
        }
        {
            if (length($0) >= indent)
                print substr($0, indent+1)
            else
                print $0
        }
    '
}

EXIT_CODE=0

for func_name in cs_compute_machine cs_compute_machine_live; do
    # Extract bodies
    lib_body=""
    hook_body=""

    if ! lib_body=$(extract_function_body "$LIB_FILE" "$func_name" 2>/dev/null); then
        echo "MISSING_IN_LIB   $func_name not found in $LIB_FILE" >&2
        EXIT_CODE=1
        continue
    fi

    if ! hook_body=$(extract_function_body "$HOOK_FILE" "$func_name" 2>/dev/null); then
        echo "MISSING_IN_HOOK  $func_name not found in $HOOK_FILE" >&2
        EXIT_CODE=1
        continue
    fi

    # Normalize indentation before comparison
    lib_norm=$(echo "$lib_body" | normalize_body)
    hook_norm=$(echo "$hook_body" | normalize_body)

    if [[ "$lib_norm" == "$hook_norm" ]]; then
        echo "OK               $func_name (lib↔hook agree)"
    else
        echo "MISMATCH         $func_name (lib↔hook differ)"
        echo "--- lib ($LIB_FILE)"
        echo "+++ hook ($HOOK_FILE)"
        diff <(echo "$lib_norm") <(echo "$hook_norm") || true
        if [[ "$MODE" == "--fix" ]]; then
            echo "NOTE: --fix is not supported for inline function mirrors." >&2
            echo "      Edit both files in lockstep to resolve the mismatch." >&2
        fi
        EXIT_CODE=1
    fi
done

exit $EXIT_CODE
