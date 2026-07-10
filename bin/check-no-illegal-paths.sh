#!/usr/bin/env bash
# check-no-illegal-paths.sh — backstop gate: scan tracked + staged paths for NTFS-illegal chars.
#
# PURPOSE: Catch NTFS-illegal path components in the git tree before they reach
# origin/main and block Windows checkout. Complements the PreToolUse
# block-illegal-filename hook (which catches agent Bash/Write/Edit calls); this
# script catches human `git mv` and any non-agent write the hook cannot observe.
# Intended to run as: (a) a pre-commit hook step and (b) a merge gate.
#
# Usage: check-no-illegal-paths.sh [<repo-root>]
#
#   <repo-root> — optional explicit repo root; absent → auto-discover via
#                 `git rev-parse --show-toplevel` (safe to run from any subdir).
#
# Scans:
#   tracked  — git ls-tree -r --name-only HEAD
#   staged   — git diff --cached --name-only
#
# Predicate: csn_check from lib/coordinator-safe-name.sh (the canonical SoT
# for the NTFS-illegal charset). Do NOT re-hardcode the charset here — the lib
# is the single source of truth.
#
# Checks every path COMPONENT, not just the basename: a colon in a directory
# name is equally illegal on NTFS as one in a filename.
#
# Exit 0 — all paths clean.
# Exit 1 — one or more illegal path components found (offending paths on stderr).
# Exit 2 — setup error (lib not found, not in a git repo).
#
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D2 (AC6)
# Realises: AC6 commit/merge backstop

# ---------------------------------------------------------------------------
# Bash version guard — MUST be the first executable statement so the guard
# is reachable on bash 3.2 (syntax parses on 3.2; runtime requires ≥4).
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    printf 'check-no-illegal-paths: bash ≥4 required (got: %s). Install via brew on macOS.\n' \
        "${BASH_VERSION:-unknown}" >&2
    exit 2
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate lib/coordinator-safe-name.sh relative to this script's directory.
# BASH_SOURCE[0] is the resolved path of this script (not caller's cwd).
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_LIB="${_SCRIPT_DIR}/lib/coordinator-safe-name.sh"
if [ ! -f "$_LIB" ]; then
    printf 'check-no-illegal-paths: lib not found at %s\n' "$_LIB" >&2
    exit 2
fi
# shellcheck source=lib/coordinator-safe-name.sh
# Review: code-reviewer F11 — use . (POSIX) instead of source for sibling consistency
. "$_LIB"

# ---------------------------------------------------------------------------
# Resolve repo root (explicit arg first, then git auto-discover)
# ---------------------------------------------------------------------------
if [ -n "${1:-}" ]; then
    _REPO_ROOT="$(cd "$1" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)" || {
        printf 'check-no-illegal-paths: "%s" is not inside a git repo\n' "$1" >&2
        exit 2
    }
else
    _REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        printf 'check-no-illegal-paths: not inside a git repo (cwd: %s)\n' "$PWD" >&2
        exit 2
    }
fi

# ---------------------------------------------------------------------------
# Collect all tracked + staged paths (deduplicated, empty-repo safe)
# ---------------------------------------------------------------------------
_all_paths="$(
    {
        git -C "$_REPO_ROOT" ls-tree -r --name-only HEAD 2>/dev/null || true
        git -C "$_REPO_ROOT" diff --cached --name-only 2>/dev/null || true
    } | sort -u
)"

# ---------------------------------------------------------------------------
# Check each path component for NTFS-illegal chars via csn_check (the SoT)
# ---------------------------------------------------------------------------
_found=0

while IFS= read -r _path; do
    [ -z "$_path" ] && continue

    # Split on '/' — every component must be individually legal.
    IFS='/' read -ra _components <<< "$_path"
    for _component in "${_components[@]}"; do
        [ -z "$_component" ] && continue
        # csn_check exits 0 (clean) or non-zero + stderr message (illegal).
        # Suppress csn_check's own stderr; we emit our own path-aware message.
        if ! csn_check "$_component" 2>/dev/null; then
            printf 'ILLEGAL PATH: %s  (component "%s" contains an NTFS-illegal char)\n' \
                "$_path" "$_component" >&2
            _found=1
        fi
    done
done <<< "$_all_paths"

if [ "$_found" -eq 0 ]; then
    printf 'check-no-illegal-paths: all tracked+staged paths are clean.\n' >&2
fi

exit "$_found"
