#!/usr/bin/env bash
# query-completions.sh — Thin wrapper for querying completion-log entries.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2
#
# Usage: query-completions.sh [options...]
# All arguments are forwarded verbatim to query-records.sh with --type completion pre-set.
# See query-records.sh --help for option documentation.
set -euo pipefail

# --help / -h intercept — print wrapper-aware usage, then exit.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
query-completions.sh — Query completion-log entries.

Thin wrapper over query-records.sh with --type completion pre-set.
You do not need to pass --type; all other query-records flags are forwarded verbatim.

Usage:
  query-completions.sh [--since <date>] [--where "<expr>"] [--sort <field>]
                       [--limit N] [--older-than <date>] [--root <path>]
                       [--format markdown-list|json|paths]

Examples:
  query-completions.sh --since 7d
  query-completions.sh --where "status=pending-release"
  query-completions.sh --since 2026-05-01 --format json

All flags and filter syntax: query-records.sh (run it directly; --type is the only preset flag).
EOF
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/query-records.sh" --type completion "$@"
