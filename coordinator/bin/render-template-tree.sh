#!/usr/bin/env bash
# bin/render-template-tree.sh — tree-walker that applies render-template.sh to every
# token-bearing file in a copied template directory tree.
#
# Purpose: copy <src-tree-dir> to <dst-tree-dir>, preserving structure and dotfiles,
# then substitute {{KEY}} tokens in every file that contains them by delegating each
# file to render-template.sh. Files with no {{ tokens are left as plain copies.
#
# Negative-spec inheritance from render-template.sh: NO conditionals, NO loops, NO
# includes, NO defaults, NO escaping of braces, NO whitespace tolerance inside {{ }}.
# This script is a tree-walker ONLY — it does not re-implement or extend the token
# substitution logic. All substitution semantics live in render-template.sh; any
# feature request that would require new substitution semantics belongs there (or in a
# different tool).
#
# Spec backlink: docs/plans/2026-06-22-new-project-bootstrap-skill.md § C2
#
# Usage:
#   render-template-tree.sh <src-tree-dir> <dst-tree-dir> [KEY=VALUE]...
#
# Arguments:
#   <src-tree-dir>   Source template directory (must exist and be readable).
#   <dst-tree-dir>   Destination directory (must NOT already exist or must be empty).
#   KEY=VALUE        Zero or more substitution pairs, passed through to render-template.sh.
#
# Exit codes:
#   0  All token-bearing files rendered successfully; tree copied to dst.
#   1  src dir unreadable, dst dir non-empty, or any per-file render fails.

set -euo pipefail

# ---------------------------------------------------------------------------
# DR-148 bash-version guard — must be reachable on bash 3.2
# (syntax parses on 3.2; arithmetic compound command is POSIX-safe)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: bash >= 4 required; install via brew install bash" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate render-template.sh relative to THIS script — not cwd
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER_SINGLE="${SCRIPT_DIR}/render-template.sh"

if [[ ! -x "$RENDER_SINGLE" ]]; then
    echo "render-template-tree: cannot find executable render-template.sh at: $RENDER_SINGLE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -lt 2 ]]; then
    echo "usage: render-template-tree.sh <src-tree-dir> <dst-tree-dir> [KEY=VALUE]..." >&2
    exit 1
fi

src="$1"
dst="$2"
shift 2
# Remaining positional args are KEY=VALUE pairs — kept in "$@" for pass-through

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ ! -d "$src" ]] || [[ ! -r "$src" ]]; then
    echo "render-template-tree: src dir is not a readable directory: $src" >&2
    exit 1
fi

if [[ -d "$dst" ]]; then
    # Allow existing dir only if it is empty
    if [[ -n "$(ls -A "$dst" 2>/dev/null)" ]]; then
        echo "render-template-tree: dst dir already exists and is non-empty: $dst" >&2
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Copy the entire tree (including dotfiles) to dst
# ---------------------------------------------------------------------------
# cp -a preserves permissions, symlinks, timestamps, and dotfiles.
# BSD cp (macOS) and GNU cp both honour -a.
cp -a "$src/." "$dst/"

# ---------------------------------------------------------------------------
# Render every token-bearing file IN PLACE via render-template.sh
# Null-delimited to handle paths with spaces.
# ---------------------------------------------------------------------------
# We build a NUL-delimited file list in a temp file using process substitution
# (bash 4+ guaranteed by the BASH_VERSINFO guard above) so that:
#   (a) the while body runs in the CURRENT shell, not a pipe subshell, and
#   (b) render-template.sh failures propagate through set -euo pipefail.
#
# NOTE: grep -rlZ is NOT used here because BSD grep on macOS ignores -Z and
# outputs newline-delimited results; find -print0 is POSIX and portable.
file_list="$(mktemp)"
trap 'rm -f "$file_list"' EXIT

# Collect token-bearing files into NUL-delimited file_list.
# The inner loop writes matching paths as NUL-terminated strings.
while IFS= read -r -d '' f; do
    if grep -qF '{{' "$f" 2>/dev/null; then  # Review: code-reviewer — F7: fixed-string for literal {{ matching (BRE ambiguity)
        printf '%s\0' "$f"
    fi
done < <(find "$dst" -type f -print0) > "$file_list"

# Render each token-bearing file in place.
while IFS= read -r -d '' f; do
    "$RENDER_SINGLE" "$f" -o "$f" "$@"
done < "$file_list"

rm -f "$file_list"
trap - EXIT

exit 0
