#!/usr/bin/env bash
# compare-repomaps.sh — Side-by-side comparison of our repomap vs Aider's
#
# Usage: compare-repomaps.sh [--profile PROFILE] [--budget BUDGET] PROJECT_ROOT
#
# Requires: aider installed (uv tool install aider-chat)
# Developer diagnostic only — not part of the CI pipeline.

set -euo pipefail

PROFILE="balanced"
BUDGET=4000
PROJECT_ROOT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="$2"; shift 2 ;;
        --budget)  BUDGET="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--profile PROFILE] [--budget BUDGET] PROJECT_ROOT"
            echo "Profiles: infra, code, balanced (default)"
            exit 0
            ;;
        *)
            if [[ -z "$PROJECT_ROOT" ]]; then
                PROJECT_ROOT="$1"
            else
                echo "Error: unexpected argument '$1'" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$PROJECT_ROOT" ]]; then
    echo "Error: PROJECT_ROOT required" >&2
    echo "Usage: $0 [--profile PROFILE] [--budget BUDGET] PROJECT_ROOT" >&2
    exit 1
fi

if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: $PROJECT_ROOT is not a directory" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Our Repomap (profile: $PROFILE, budget: $BUDGET) ==="
python3 "$SCRIPT_DIR/generate-repomap.py" \
    --project-root "$PROJECT_ROOT" \
    --budget "$BUDGET" \
    --profile "$PROFILE" \
    --output /dev/stdout 2>/dev/null \
    | grep -E '^## ' \
    | head -20 \
    | sed 's/^## //'

echo ""
echo "=== Aider Repomap ==="
if command -v aider &>/dev/null; then
    (cd "$PROJECT_ROOT" && aider --show-repo-map 2>/dev/null) \
        | grep -E '^\S' \
        | head -20
else
    echo "(aider not installed — run: uv tool install aider-chat)"
fi

echo ""
echo "=== Overlap ==="
OUR_FILES=$(python3 "$SCRIPT_DIR/generate-repomap.py" \
    --project-root "$PROJECT_ROOT" \
    --budget "$BUDGET" \
    --profile "$PROFILE" \
    --output /dev/stdout 2>/dev/null \
    | grep -E '^## ' \
    | head -20 \
    | sed 's/^## //' \
    | sort)

if command -v aider &>/dev/null; then
    AIDER_FILES=$(cd "$PROJECT_ROOT" && aider --show-repo-map 2>/dev/null \
        | grep -E '^\S' \
        | head -20 \
        | sort)
    if [[ -n "$OUR_FILES" && -n "$AIDER_FILES" ]]; then
        OVERLAP=$(comm -12 <(printf '%s\n' "$OUR_FILES") <(printf '%s\n' "$AIDER_FILES") | wc -l)
        OUR_COUNT=$(printf '%s\n' "$OUR_FILES" | wc -l)
        AIDER_COUNT=$(printf '%s\n' "$AIDER_FILES" | wc -l)
        echo "$OVERLAP files in common (ours: $OUR_COUNT, aider: $AIDER_COUNT)"
    else
        echo "(insufficient data — one or both repomaps returned empty results)"
    fi
else
    echo "(skipped — aider not installed)"
fi
