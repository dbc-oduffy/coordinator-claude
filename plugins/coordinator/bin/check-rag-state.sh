#!/usr/bin/env bash
# check-rag-state.sh — detect project-RAG freshness and print a single token to stdout.
#
# Purpose: centralise the RAG-state detection logic shared by update-docs, enrich-and-review,
# and project-orientation.sh — each caller invokes this helper and gates repomap generation
# on the result. Full gating doctrine: docs/wiki/repomap-rag-gating.md
#
# Spec backlink: docs/plans/2026-05-09-skill-consolidation-pass.md § T2
#
# Output (stdout, one token):
#   absent   — no project-RAG MCP tool is registered in this session
#   stale    — RAG present but staleness banner was emitted at session start (W1 hook)
#   fresh    — RAG present and freshness marker is current
#   unknown  — could not determine state from bash-readable signals
#
# Exit codes:
#   0 — state is one of: absent, stale, fresh
#   1 — state is unknown (callers should treat as stale)
#
# Negative spec: this script does NOT perform any MCP tool calls; it only reads bash-readable
# marker files and environment variables. MCP availability cannot be probed from bash.

set -euo pipefail

# ── Marker file locations ────────────────────────────────────────────────────
# The W1 hook (project-rag-detect.*) writes these markers at session open.
# Location preference: CLAUDE_PLUGIN_ROOT if set, else ~/.claude heuristic.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/coordinator-claude/coordinator}"
RAG_STATE_MARKER="${CLAUDE_RAG_STATE_FILE:-${PLUGIN_ROOT}/tasks/.rag-state}"

# ── 1. Check env var fast-path ───────────────────────────────────────────────
# A caller or hook may inject RAG_STATE directly (e.g., in test harnesses).
if [ -n "${RAG_STATE:-}" ]; then
    case "$RAG_STATE" in
        absent|stale|fresh)
            echo "$RAG_STATE"
            exit 0
            ;;
        unknown)
            echo "unknown"
            exit 1
            ;;
    esac
fi

# ── 2. Read marker file written by W1 hook ───────────────────────────────────
if [ -f "$RAG_STATE_MARKER" ]; then
    state=$(head -1 "$RAG_STATE_MARKER" | tr -d '[:space:]')
    case "$state" in
        absent|stale|fresh)
            echo "$state"
            exit 0
            ;;
        unknown)
            echo "unknown"
            exit 1
            ;;
        *)
            # Marker file has unrecognised content — fall through to unknown
            ;;
    esac
fi

# ── 3. Fallback: marker absent → unknown ────────────────────────────────────
# Without a marker file we cannot determine RAG state from bash.
# Callers treat unknown == stale (conservative: generate as fallback rather
# than silently skip). Exiting 1 signals callers to apply the stale branch.
echo "unknown"
exit 1
