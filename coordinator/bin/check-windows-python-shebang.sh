#!/usr/bin/env bash
# bin/check-windows-python-shebang.sh — Tripwire: WINDOWS-PYTHON-SHEBANG
#
# Purpose: Enforces the invariant that no coordinator/bin/ polyglot or test Python
# script carries a #!/usr/bin/env python3 shebang. The correct shebang for
# Windows-compat scripts in this class is #!/usr/bin/env python (with a sh/python
# trampoline or .test.py class marker). A python3 shebang on these files is a
# self-contradiction: it breaks on Windows where only `py` or `python` is on PATH,
# and it contradicts the trampoline whose purpose is to locate python3 or python
# portably at runtime.
#
# Greppable token: WINDOWS-PYTHON-SHEBANG
#
# Detection model — opt-OUT allowlist (broadest-enforceable scope):
#   Every coordinator/bin/ file whose line 1 is #!/usr/bin/env python3 is a
#   VIOLATION, EXCEPT the four legitimately-standalone python3 scripts that are
#   explicitly allowlisted:
#     age-sweep-lessons.py, doctor-catalog-gen.py, doctor-probe-select.py,
#     extract-lessons.py
#   These four are pure-python3 utilities with no Windows-compat trampoline and
#   no .test.py class; all other python3-shebang files in bin/ are by definition
#   in the protected Windows-compat class.
#
#   New legitimately-standalone python3 bin scripts MUST be added to the
#   allowlist in _is_allowlisted_python3() below before committing — opt-out
#   shape, not opt-in, per lessons.md:52 (broadest-enforceable-scope principle).
#
# Spec backlink: docs/plans/2026-06-17-python3-shebang-flip-guard.md
# Doctrine: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline
#
# Usage:
#   check-windows-python-shebang.sh [--staged]
#
#   (no flag)   Scan all Python files under coordinator/bin/ on disk.
#   --staged    Scope scan to files that are both staged (git diff --cached)
#               AND in the coordinator/bin/ directory. Suitable for pre-commit hooks.
#
# Exit codes:
#   0 — OK: no python3-shebang flip found in the protected class
#   1 — VIOLATION: one or more protected-class files carry #!/usr/bin/env python3
#
# Output:
#   stdout — human-readable status (OK or VIOLATION lines)
#   stderr — error messages only
#
# Negative-spec (hard-won):
#   - Does NOT flag the 4 allowlisted python3 scripts (age-sweep-lessons.py,
#     doctor-catalog-gen.py, doctor-probe-select.py, extract-lessons.py).
#   - Does NOT scan outside coordinator/bin/ — only that directory.
#   - Does NOT block on scripts without any Python shebang at all.

set -uo pipefail

# ---------------------------------------------------------------------------
# Parse arguments (model: check-schema-version-bump.sh)
# ---------------------------------------------------------------------------

MODE="full"

for arg in "$@"; do
    case "$arg" in
        --staged)
            MODE="staged"
            ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \?//' || true
            exit 0
            ;;
        *)
            echo "check-windows-python-shebang.sh: unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Resolve bin/ directory
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Build file list to inspect
# ---------------------------------------------------------------------------

# _candidate_paths: emit ALL regular files directly under BIN_DIR to inspect
# (any extension — extensionless trampoline CLIs are in scope).
# Staged mode: staged files directly under BIN_PREFIX (git-root-relative path).
# Full mode: all regular files in BIN_DIR (flat, non-recursive).
_candidate_paths() {
    if [ "$MODE" = "staged" ]; then
        # Get staged file paths (relative to git root), then match against BIN_DIR
        GIT_ROOT="$(git -C "$BIN_DIR" rev-parse --show-toplevel 2>/dev/null)" || {
            echo "check-windows-python-shebang.sh: ERROR — not a git repo" >&2
            return 0
        }
        # Use git show-prefix to get the prefix of BIN_DIR relative to git root
        # (format-agnostic, works on Windows and macOS)
        BIN_PREFIX="$(git -C "$BIN_DIR" rev-parse --show-prefix 2>/dev/null)" || BIN_PREFIX=""
        # BIN_PREFIX already has a trailing slash (or is empty if bin/ IS the git root)
        STAGED="$(git -C "$GIT_ROOT" diff --cached --name-only 2>/dev/null)" || STAGED=""
        if [ -z "$STAGED" ]; then
            return 0
        fi
        # Filter: staged files directly under BIN_PREFIX (any name — extensionless
        # trampoline CLIs are in-class; the allowlist predicate filters below).
        # Review: code-reviewer Slice B — explicit prefix-strip avoids treating
        # glob metacharacters in BIN_PREFIX as wildcards (case-glob hazard).
        echo "$STAGED" | while IFS= read -r rel; do
            stripped="${rel#$BIN_PREFIX}"
            if [ "$stripped" != "$rel" ]; then
                base="$stripped"
                # Must be directly in bin/ (no sub-directory slash)
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
        # Full scan: ALL regular files directly in BIN_DIR (not just *.py — the
        # protected trampoline CLIs cross-repo-memo, coordinator-lesson-promote,
        # coordinator-queue-append, install-sentinel-write are EXTENSIONLESS; the
        # protected-class predicate below filters down to the real class).
        for f in "${BIN_DIR}"/*; do
            [ -f "$f" ] && echo "$f"
        done
    fi
}

# ---------------------------------------------------------------------------
# Detection helpers (DR-148 portable — no grep -P, no bash 4 features)
# ---------------------------------------------------------------------------

# _has_python3_shebang <file>
# Returns 0 if line 1 is exactly "#!/usr/bin/env python3", else 1.
_has_python3_shebang() {
    first_line="$(head -1 "$1" 2>/dev/null)" || return 1
    case "$first_line" in
        "#!/usr/bin/env python3")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# _is_allowlisted_python3 <file>
# Returns 0 if the file is one of the 4 legitimately-standalone python3 scripts
# that are explicitly carved out from the violation check (allowlist opt-out).
# Returns 1 for everything else — those files must NOT carry #!/usr/bin/env python3.
#
# To add a new legitimately-standalone python3 bin script: add its basename here
# before committing the file. The opt-out shape means any omission is caught.
# Review: code-reviewer Slice B — allowlist opt-out replaces positive predicate
# (trampoline-marker grep + .test.py test) which was narrower than spec invariant
# and would miss future bin/ files with python3 shebang lacking those markers.
_is_allowlisted_python3() {
    case "$(basename "$1")" in
        age-sweep-lessons.py|doctor-catalog-gen.py|doctor-probe-select.py|extract-lessons.py)
            return 0
            ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

OFFENDERS=""

# Heredoc (not pipe) so the loop body runs in the parent shell and $OFFENDERS
# survives the loop (bash 3.2 has no lastpipe).
while IFS= read -r filepath; do
    [ -f "$filepath" ] || continue
    if _has_python3_shebang "$filepath" && ! _is_allowlisted_python3 "$filepath"; then
        if [ -z "$OFFENDERS" ]; then
            OFFENDERS="$filepath"
        else
            OFFENDERS="${OFFENDERS}
${filepath}"
        fi
    fi
done <<EOF
$(_candidate_paths)
EOF

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

if [ -z "$OFFENDERS" ]; then
    echo "OK: no python3 shebang flip found in coordinator/bin/ protected class"
    exit 0
fi

echo "VIOLATION: WINDOWS-PYTHON-SHEBANG — the following coordinator/bin/ file(s)"
echo "  carry #!/usr/bin/env python3 and are not in the allowlist of legitimately-"
echo "  standalone python3 scripts. Correct shebang is #!/usr/bin/env python."
echo "  Portable fix: keep #!/usr/bin/env python and use the sh/python trampoline."
echo "  To add a new legitimately-standalone script: add to _is_allowlisted_python3()."
echo "  See: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline"
echo ""
echo "$OFFENDERS" | while IFS= read -r f; do
    echo "  $f"
done
exit 1
