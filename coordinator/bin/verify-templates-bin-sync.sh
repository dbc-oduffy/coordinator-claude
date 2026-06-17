#!/usr/bin/env bash
# verify-templates-bin-sync.sh — Check/fix byte-identity between live ~/.claude/bin helpers
# and their coordinator/templates/bin/ mirrors.
#
# Usage:
#   verify-templates-bin-sync.sh          Diff each pair; report mismatches; exit non-zero on any mismatch.
#   verify-templates-bin-sync.sh --fix    Copy live → template (one-way; template tracks live).
#
# Pairs verified:
#   ~/.claude/bin/claude_machine_local.py     ↔  coordinator/templates/bin/claude_machine_local.py
#   ~/.claude/bin/claude-machine-local.sh     ↔  coordinator/templates/bin/claude-machine-local.sh
#   ~/.claude/bin/claude-machine-local.ps1    ↔  coordinator/templates/bin/claude-machine-local.ps1
#
# When neither file in a pair exists yet, the pair is skipped (exit 0 with a message).
# This graceful-no-files behaviour matches the no-consumer pattern in other verify-*-sync.sh
# scripts: the verifier is authored before the files it will eventually verify.
#
# Spec backlink: docs/plans/2026-05-20-eager-agent-calibration.md § Chunk 1

set -euo pipefail

# Resolve plugin root: from env var, or relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TEMPLATES_BIN="$PLUGIN_ROOT/templates/bin"
LIVE_BIN="$CLAUDE_HOME/bin"

MODE="${1:-verify}"

# Pairs: "live_name template_name" (relative filenames; both dirs rooted above)
PAIRS=(
    "claude_machine_local.py claude_machine_local.py"
    "claude-machine-local.sh claude-machine-local.sh"
    "claude-machine-local.ps1 claude-machine-local.ps1"
    # Review: code-reviewer (F6) — WARNING: --fix copies live→template for this pair,
    # but _machine_local.py's canonical source is the TEMPLATE (opposite polarity from
    # the claude-home family above). --fix is UNSAFE for this pair without manual review.
    # Canonical direction is template→live; use verify-mode as the gate, hand-resolve divergence.
    # After editing the template, propagate manually: cp plugins/.../templates/bin/_machine_local.py bin/_machine_local.py
    "_machine_local.py _machine_local.py"
)

EXIT_CODE=0
ANY_CHECKED=0

for pair in "${PAIRS[@]}"; do
    live_name="${pair%% *}"
    tmpl_name="${pair##* }"
    live_path="$LIVE_BIN/$live_name"
    tmpl_path="$TEMPLATES_BIN/$tmpl_name"

    live_exists=0
    tmpl_exists=0
    [ -f "$live_path" ] && live_exists=1
    [ -f "$tmpl_path" ] && tmpl_exists=1

    if [ "$live_exists" -eq 0 ] && [ "$tmpl_exists" -eq 0 ]; then
        # Neither side exists yet — graceful skip.
        echo "NOT_PRESENT  $live_name (neither live nor template exists yet — Chunks 3/4 will create them)"
        continue
    fi

    if [ "$live_exists" -eq 0 ]; then
        echo "LIVE_MISSING $live_name (template exists but live copy absent at $live_path)"
        EXIT_CODE=1
        continue
    fi

    if [ "$tmpl_exists" -eq 0 ]; then
        if [ "$MODE" = "--fix" ]; then
            mkdir -p "$TEMPLATES_BIN"
            cp "$live_path" "$tmpl_path"
            echo "COPIED       $live_name → templates/bin/$tmpl_name"
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
            echo "FIXED        $live_name → templates/bin/$tmpl_name"
        else
            echo "MISMATCH     $live_name"
            EXIT_CODE=1
        fi
    fi
done

if [ "$ANY_CHECKED" -eq 0 ] && [ "$EXIT_CODE" -eq 0 ]; then
    echo "no files present — nothing to verify (Chunks 3/4 will create the live and template copies)"
fi

exit $EXIT_CODE
