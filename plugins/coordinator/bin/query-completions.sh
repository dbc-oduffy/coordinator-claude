#!/usr/bin/env bash
# query-completions.sh — Thin wrapper for querying completion-log entries.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2
#
# Usage: query-completions.sh [options...]
# All arguments are forwarded verbatim to query-records.sh with --type completion pre-set.
# See query-records.sh --help for option documentation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/query-records.sh" --type completion "$@"
