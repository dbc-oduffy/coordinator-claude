#!/usr/bin/env bash
# query-records.sh — Thin shell wrapper for query-records.js
#
# Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W2
#
# Usage: query-records.sh --type <type> [options...]
# All arguments are forwarded verbatim to the Node script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# There is no nodew.exe equivalent; shell-level suppression is impossible here.
# Console-flash suppression for this invocation is machine-belt territory
# (ConPTY/ConHost delegation, Chunk 5 of the flash-elimination plan).
# See: lib/spawn-hidden.sh § "Node on Windows".
node "$SCRIPT_DIR/query-records.js" "$@" # verify-no-console-flash: allow
