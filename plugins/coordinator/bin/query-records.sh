#!/usr/bin/env bash
# query-records.sh — Thin shell wrapper for query-records.js
#
# Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2
#
# Usage: query-records.sh --type <type> [options...]
# All arguments are forwarded verbatim to the Node script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
node "$SCRIPT_DIR/query-records.js" "$@"
