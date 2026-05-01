#!/usr/bin/env bash
# refresh-queries.sh — Thin shell wrapper for refresh-queries.js
#
# Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2
#
# Usage: refresh-queries.sh [--root <path>] [--check] [--files <glob>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
node "$SCRIPT_DIR/refresh-queries.js" "$@"
