#!/usr/bin/env bash
# verify-templates-setup-sync.sh — Check/fix byte-identity between live ~/.claude/setup helpers
# and their coordinator/templates/setup/ mirrors.
#
# Usage:
#   verify-templates-setup-sync.sh          Diff each pair; report mismatches; exit non-zero on any mismatch.
#   verify-templates-setup-sync.sh --fix    Copy live → template (one-way; template tracks live).
#
# Pairs verified:
#   ~/.claude/setup/publish.sh                    ↔  coordinator/templates/setup/publish.sh
#   ~/.claude/setup/publish_sync.py               ↔  coordinator/templates/setup/publish_sync.py
#   ~/.claude/setup/publish-targets.example.sh    ↔  coordinator/templates/setup/publish-targets.example.sh
#   ~/.claude/setup/.percolate-identity.example   ↔  coordinator/templates/setup/.percolate-identity.example
#   ~/.claude/setup/percolate-hooks/README.md     ↔  coordinator/templates/setup/percolate-hooks/README.md
#
# When neither file in a pair exists yet, the pair is skipped (exit 0 with a message).
# This graceful-no-files behaviour matches the no-consumer pattern in other verify-*-sync.sh
# scripts: the verifier is authored before the files it will eventually verify.
#
# Spec backlink: docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md § Step 3

set -euo pipefail

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TEMPLATES_SETUP="$PLUGIN_ROOT/templates/setup"
LIVE_SETUP="$CLAUDE_HOME/setup"

MODE="${1:-verify}"

# Pairs: "live_name template_name" (relative filenames; both dirs rooted above)
PAIRS=(
    "publish.sh publish.sh"
    "publish_sync.py publish_sync.py"
    "publish-targets.example.sh publish-targets.example.sh"
    ".percolate-identity.example .percolate-identity.example"
    "percolate-hooks/README.md percolate-hooks/README.md"
)

EXIT_CODE=0
ANY_CHECKED=0

for pair in "${PAIRS[@]}"; do
    live_name="${pair%% *}"
    tmpl_name="${pair##* }"
    live_path="$LIVE_SETUP/$live_name"
    tmpl_path="$TEMPLATES_SETUP/$tmpl_name"

    live_exists=0
    tmpl_exists=0
    [ -f "$live_path" ] && live_exists=1
    [ -f "$tmpl_path" ] && tmpl_exists=1

    if [ "$live_exists" -eq 0 ] && [ "$tmpl_exists" -eq 0 ]; then
        # Neither side exists yet — graceful skip.
        echo "NOT_PRESENT  $live_name (neither live nor template exists yet — Step 1 will create them)"
        continue
    fi

    if [ "$live_exists" -eq 0 ]; then
        echo "LIVE_MISSING $live_name (template exists but live copy absent at $live_path)"
        EXIT_CODE=1
        continue
    fi

    if [ "$tmpl_exists" -eq 0 ]; then
        if [ "$MODE" = "--fix" ]; then
            mkdir -p "$(dirname "$tmpl_path")"
            cp "$live_path" "$tmpl_path"
            echo "COPIED       $live_name → templates/setup/$tmpl_name"
            ANY_CHECKED=1
        else
            echo "TMPL_MISSING $live_name (live exists but template absent at $tmpl_path)"
            EXIT_CODE=1
        fi
        continue
    fi

    ANY_CHECKED=1

    # Both exist — diff for byte identity.
    if diff -q "$live_path" "$tmpl_path" >/dev/null 2>&1; then
        echo "OK           $live_name"
    else
        if [ "$MODE" = "--fix" ]; then
            cp "$live_path" "$tmpl_path"
            echo "FIXED        $live_name → templates/setup/$tmpl_name"
        else
            echo "MISMATCH     $live_name"
            EXIT_CODE=1
        fi
    fi
done

if [ "$ANY_CHECKED" -eq 0 ] && [ "$EXIT_CODE" -eq 0 ]; then
    echo "no files present — nothing to verify (Step 1 will create the live and template copies)"
fi

exit $EXIT_CODE
