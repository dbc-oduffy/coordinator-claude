#!/usr/bin/env bash
# bin/check-bin-sh-polyglot.sh — Tripwire: BIN-SH-POLYGLOT-INVARIANT
#
# Purpose: Enforces the invariant that every member of the coordinator/bin/
# sh/python polyglot class carries (a) line 1 == #!/bin/sh and (b) the
# verbatim trampoline line:
#   ''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
#
# Greppable token: BIN-SH-POLYGLOT-INVARIANT
#
# Detection model — CONTENT-first, NOT extension-based:
#   Enumerate ALL regular files directly under coordinator/bin/ and classify
#   each as polyglot-class or out-of-scope by reading its content:
#     - A file is IN-CLASS iff it contains the verbatim trampoline within the
#       first 20 lines (has_trampoline). Trampoline past line 20 is invisible
#       to sh at exec time — it would be treated as body code, not a re-exec.
#     - This check script (check-bin-sh-polyglot.sh) is SKIPPED from the scan
#       because its source contains the trampoline as a data string (TRAMPOLINE=
#       variable and comment), which would self-classify it as in-class. The
#       script is not itself a sh/python polyglot CLI — it is a pure bash tool.
#     - Pure #!/bin/sh tools WITHOUT the trampoline are NOT in-class and are
#       silently skipped. A pure-#!/bin/sh non-polyglot is a valid other class.
#     - #!/usr/bin/env python3 allowlisted scripts (age-sweep-lessons.py, etc.)
#       have no trampoline and are silently skipped.
#   For each IN-CLASS file, BOTH invariants are asserted:
#     (a) line 1 == #!/bin/sh  (shebang-flip caught statically)
#     (b) trampoline within first 20 lines (already required for membership)
#   This avoids the predecessor check-windows-python-shebang.sh extension-glob
#   bug: extensionless CLIs (cross-repo-memo, coordinator-lesson-promote,
#   coordinator-queue-append, install-sentinel-write) are INVISIBLE to *.py globs
#   and produced false-negatives in the predecessor. Content-first classification
#   catches them correctly. (state/lessons.md:220, load-bearing.)
#
# Spec backlink: docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md
# Doctrine: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline
#
# Usage:
#   check-bin-sh-polyglot.sh [--staged]
#
#   (no flag)   Scan all regular files directly under coordinator/bin/ on disk.
#   --staged    Scope scan to files that are both staged (git diff --cached)
#               AND directly under coordinator/bin/. Suitable for pre-commit hooks.
#
# Exit codes:
#   0 — OK: every polyglot-class member has #!/bin/sh + verbatim trampoline
#   1 — VIOLATION: one or more polyglot-class members are missing #!/bin/sh or
#       the verbatim trampoline line
#
# Output:
#   stdout — human-readable status (OK or VIOLATION lines)
#   stderr — error messages only
#
# Negative-spec (hard-won):
#   - Does NOT pre-filter by extension — extensionless CLIs are in-class.
#   - Does NOT flag non-polyglot files (no trampoline in first 20 lines).
#   - Does NOT flag pure-#!/bin/sh files that lack the trampoline.
#   - Does NOT scan subdirectories — only directly under coordinator/bin/.
#   - Does NOT require GNU coreutils — bash 3.2 + BSD portable (DR-148).
#   - Does NOT scan itself (self-skip: this script's own path is excluded).

set -uo pipefail

# ---------------------------------------------------------------------------
# Parse arguments (model: check-windows-python-shebang.sh interface)
# ---------------------------------------------------------------------------

MODE="full"

for arg in "$@"; do
    case "$arg" in
        --staged)
            MODE="staged"
            ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^#[[:space:]]\{0,1\}//' || true
            exit 0
            ;;
        *)
            printf 'check-bin-sh-polyglot.sh: unknown argument: %s\n' "$arg" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve bin/ directory and THIS_SCRIPT (for self-skip in the scan loop)
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$SCRIPT_DIR"
# Resolve the absolute path of this script so we can skip it during the scan.
# This script contains the TRAMPOLINE string as a data value (the TRAMPOLINE=
# variable below) and in the comment above — those would cause self-classification
# as in-class, which is incorrect. The script is a pure bash tool, not a polyglot CLI.
THIS_SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# The verbatim trampoline string every polyglot-class member must contain.
# Single quotes inside the string make inline quoting awkward; store in a var.
TRAMPOLINE="''''exec \"\$(command -v python3 || command -v python || command -v py)\" \"\$0\" \"\$@\" #'''"

# ---------------------------------------------------------------------------
# Build file list to inspect
# ---------------------------------------------------------------------------

# _candidate_paths: emit ALL regular files directly under BIN_DIR (non-recursive).
# In staged mode, further filter to those staged in git. No extension filtering.
_candidate_paths() {
    if [ "$MODE" = "staged" ]; then
        GIT_ROOT="$(git -C "$BIN_DIR" rev-parse --show-toplevel 2>/dev/null)" || {
            printf 'check-bin-sh-polyglot.sh: ERROR — not a git repo\n' >&2
            return 0
        }
        BIN_PREFIX="$(git -C "$BIN_DIR" rev-parse --show-prefix 2>/dev/null)" || BIN_PREFIX=""
        STAGED="$(git -C "$GIT_ROOT" diff --cached --name-only 2>/dev/null)" || STAGED=""
        if [ -z "$STAGED" ]; then
            return 0
        fi
        # Filter: staged files directly under BIN_PREFIX (no sub-directory slash).
        # Prefix-strip before glob-match to avoid treating metacharacters as wildcards.
        printf '%s\n' "$STAGED" | while IFS= read -r rel; do
            stripped="${rel#$BIN_PREFIX}"
            if [ "$stripped" != "$rel" ]; then
                base="$stripped"
                case "$base" in
                    */*)
                        # skip — in a subdirectory
                        ;;
                    *)
                        echo "${BIN_DIR}/${base}"
                        ;;
                esac
            fi
        done
    else
        # Full scan: ALL regular files directly in BIN_DIR (NOT recursive).
        # The 'for f in *' glob includes extensionless CLIs — that is intentional.
        for f in "${BIN_DIR}"/*; do
            [ -f "$f" ] && echo "$f"
        done
    fi
}

# ---------------------------------------------------------------------------
# Classification helpers (DR-148 portable — no grep -P, no bash 4 features)
# ---------------------------------------------------------------------------

# _line1 <file>: emit line 1 of the file.
_line1() {
    head -1 "$1" 2>/dev/null
}

# _has_trampoline <file>: returns 0 if the file contains the verbatim trampoline
# within its first 20 lines. Checking only the header region matters: a trampoline
# after python imports (e.g. line 50) would pass a full-file grep but fail at
# exec time under sh, because sh reads the file top-to-bottom and would try to
# exec a Python import statement. All valid bearers have the trampoline by line 15.
# Review: code-reviewer — trampoline position must be near top (Finding D)
_has_trampoline() {
    head -20 "$1" 2>/dev/null | grep -qF "$TRAMPOLINE" 2>/dev/null
}

# _has_sh_shebang <file>: returns 0 if line 1 is exactly #!/bin/sh.
_has_sh_shebang() {
    first="$(_line1 "$1")"
    case "$first" in
        "#!/bin/sh") return 0 ;;
        *)           return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

# Accumulate offenders as newline-separated string (bash 3.2: no arrays needed).
OFFENDERS=""

_add_offender() {
    local reason="$1" path="$2"
    local entry="  $path  ($reason)"
    if [ -z "$OFFENDERS" ]; then
        OFFENDERS="$entry"
    else
        OFFENDERS="${OFFENDERS}
${entry}"
    fi
}

# Use heredoc redirect (not pipe) so the loop body runs in the parent shell and
# $OFFENDERS accumulates correctly — bash 3.2 has no lastpipe option.
while IFS= read -r filepath; do
    [ -f "$filepath" ] || continue

    # Self-skip: this script's own path contains the TRAMPOLINE string as a data
    # value (variable assignment + comment), so it would self-classify as in-class.
    # It is a pure bash tool, not a sh/python polyglot CLI. Skip it explicitly.
    # Review: code-reviewer — self-classification via data-copy (Finding C)
    [ "$filepath" = "$THIS_SCRIPT" ] && continue

    has_tramp=0
    _has_trampoline "$filepath" && has_tramp=1

    # Membership predicate: a file is IN-CLASS iff it contains the verbatim
    # trampoline within its first 20 lines. Pure-#!/bin/sh tools without the
    # trampoline are a different class and are NOT our concern. The OR-has_sh leg
    # is dropped to avoid false-positives on future pure-#!/bin/sh non-polyglots.
    # Review: code-reviewer — membership = has-trampoline-only (Finding C)
    if [ "$has_tramp" -eq 0 ]; then
        continue  # not in the polyglot class — skip
    fi

    # Now it IS in-class. Assert line 1 == #!/bin/sh (shebang-flip detection).
    # The trampoline is already confirmed present by the membership test above.
    if ! _has_sh_shebang "$filepath"; then
        _add_offender "missing #!/bin/sh on line 1" "$filepath"
    fi
    # Both present: OK — no action needed.

done <<EOF
$(_candidate_paths)
EOF

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

if [ -z "$OFFENDERS" ]; then
    printf 'OK: all coordinator/bin/ sh/python polyglot members have #!/bin/sh + trampoline\n'
    exit 0
fi

printf 'VIOLATION: BIN-SH-POLYGLOT-INVARIANT — the following coordinator/bin/ file(s)\n'
printf '  are in the sh/python polyglot class but are missing #!/bin/sh on line 1 and/or\n'
printf '  the verbatim trampoline line.\n'
printf '  See: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline\n'
printf '  Plan: docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md\n'
printf '\n'
printf '%s\n' "$OFFENDERS"
exit 1
