#!/usr/bin/env bash
# lib/detect-existing-claude-home.sh — Track A/B classifier for Claude home directories.
#
# Purpose: determine whether a candidate Claude home directory is install-from-zero
# (Track A) or has an existing user structure (Track B), so install logic can choose
# the right path.  Consumed by setup/install logic and tests.
#
# Spec backlink: chunk C7 — Track A/B detection helper (P8)
#
# Decision rules (first match wins, evaluated in order):
#   B1. Git-tracked    — git -C <target> rev-parse --is-inside-work-tree succeeds
#   B2. Plugin present — <target>/plugins/ contains at least one non-trivial entry
#                        (non-empty directory or non-zero file)
#   B3. Substantial CLAUDE.md — <target>/CLAUDE.md exists with >10 non-blank lines
#                        (threshold: 10 is meaningfully above a stub/template comment
#                        header, below a real config.  Documented here so callers can
#                        reason about false-positives in either direction.)
#   → if none: Track A
#
# Usage:
#   bash detect-existing-claude-home.sh [<target-dir>]
#   CLAUDE_CONFIG_DIR=<dir> bash detect-existing-claude-home.sh
#
# Output (stdout): one line of the form:
#   track=A reason: <human explanation>
#   track=B reason: <human explanation>
#
# Exit codes:
#   0 — always (classification result is in stdout, not exit code)
#
# Read-only contract: this script MUST NOT create, modify, or delete anything
# in the target directory.  Idempotent: identical output on repeated runs.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve target directory
# ---------------------------------------------------------------------------
# Priority: $1 (explicit arg) > $CLAUDE_CONFIG_DIR > $HOME/.claude
_resolve_target() {
    if [[ -n "${1:-}" ]]; then
        echo "$1"
    elif [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
        echo "$CLAUDE_CONFIG_DIR"
    else
        echo "${HOME}/.claude"
    fi
}

TARGET="$(_resolve_target "${1:-}")"

# ---------------------------------------------------------------------------
# B1: Git-tracked
# ---------------------------------------------------------------------------
# Intent: is TARGET *itself* a git repo root (not merely a subdir of an ancestor
# repo). `rev-parse --is-inside-work-tree` returns true for any ancestor work tree,
# which false-positives a ~/.claude that lives under a git-tracked $HOME. A repo
# root (incl. worktree/submodule, where .git is a file) has a .git entry; a plain
# subdir of a repo does not. `-e` covers both the dir and file forms.
if [[ -e "$TARGET/.git" ]]; then
    echo "track=B reason: ${TARGET} is git-tracked"
    exit 0
fi

# ---------------------------------------------------------------------------
# B2: Non-default plugins present
# ---------------------------------------------------------------------------
# A vanilla Claude home has no plugins/ dir, or an empty one.
# "Non-trivial entry" means either a non-empty subdirectory or a regular file
# (a plugin installation drops at least one file or creates a populated subdir).
_has_installed_plugin() {
    local plugins_dir="${TARGET}/plugins"
    [[ -d "$plugins_dir" ]] || return 1
    # Check whether any entry in plugins/ is a non-empty directory or a file.
    local entry
    while IFS= read -r -d '' entry; do
        if [[ -f "$entry" ]]; then
            # Any file directly under plugins/ counts as a plugin artifact.
            return 0
        elif [[ -d "$entry" ]]; then
            # A non-empty subdirectory counts as an installed plugin.
            # `-print -quit` emits the first child and exits — no pipe to head,
            # so no SIGPIPE that `set -o pipefail` would propagate as a failure.
            if [[ -n "$(find "$entry" -maxdepth 1 -mindepth 1 -print -quit 2>/dev/null)" ]]; then
                return 0
            fi
        fi
    done < <(find "$plugins_dir" -maxdepth 1 -mindepth 1 -print0 2>/dev/null)
    return 1
}

if _has_installed_plugin; then
    echo "track=B reason: ${TARGET}/plugins/ contains installed plugin(s)"
    exit 0
fi

# ---------------------------------------------------------------------------
# B3: Substantially-edited CLAUDE.md
# ---------------------------------------------------------------------------
# Threshold: > 10 non-blank lines.
# Rationale: a template stub or minimal fresh install header typically has
# ≤ 5 non-blank lines (shebang-style comment block or a single-paragraph
# placeholder).  10 gives comfortable headroom above a stub without false-
# negatives on a config that's been lightly customised.  Callers that need
# a different threshold should invoke with a fixture dir and inspect.
_non_blank_line_count() {
    local file="$1"
    grep -c '[^[:space:]]' "$file" 2>/dev/null || echo 0
}

CLAUDE_MD="${TARGET}/CLAUDE.md"
if [[ -f "$CLAUDE_MD" ]]; then
    count="$(_non_blank_line_count "$CLAUDE_MD")"
    if [[ "$count" -gt 10 ]]; then
        echo "track=B reason: ${TARGET}/CLAUDE.md has ${count} non-blank lines (threshold >10)"
        exit 0
    fi
fi

# ---------------------------------------------------------------------------
# Track A — none of the B conditions fired
# ---------------------------------------------------------------------------
echo "track=A reason: ${TARGET} has no git history, no installed plugins, and no substantial CLAUDE.md"
exit 0
