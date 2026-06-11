#!/usr/bin/env bash
# bin/check-schema-version-bump.sh — Tripwire: canonical-structure.yaml must not change
# without a corresponding bump to coordinator-schema-version.
#
# Purpose: Enforces the invariant that any structural schema change is accompanied by a
# version increment, so that consumer repos' currency stamps correctly drift-detect after
# a plugin upgrade.
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1
#
# Usage:
#   check-schema-version-bump.sh [--staged | --commit=<ref>]
#
#   --staged           (default) Inspects the current git index (staged diff vs HEAD).
#                      Suitable for use in a PreToolUse commit hook.
#   --commit=<ref>     Inspects the diff introduced by <ref> vs its parent (<ref>~1).
#                      Suitable for use in CI or post-commit checks.
#
# Exit codes:
#   0 — OK (canonical-structure.yaml not changed, or changed with version bump)
#   1 — VIOLATION: canonical-structure.yaml changed without coordinator-schema-version bump
#   2 — ERROR: could not determine diff (not a git repo, ref not found, etc.)
#
# Output:
#   stdout — human-readable status line
#   stderr — error details only
#
# Environment:
#   COORDINATOR_PLUGIN_ROOT  Optional. Path to the plugin root containing
#                            canonical-structure.yaml and coordinator-schema-version.
#                            Defaults to the directory two levels above this script
#                            (i.e., <plugin-root>/bin/../.. when invoked as bin/check-schema-version-bump.sh).
#
# Negative-spec (hard-won):
#   - This script does NOT check consumer repos — only the plugin root.
#   - This script does NOT block on other file changes — only canonical-structure.yaml.
#   - Renaming canonical-structure.yaml is out of scope; update the CANONICAL_FILE variable.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve plugin root and canonical paths
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${COORDINATOR_PLUGIN_ROOT:-${SCRIPT_DIR}/..}"

CANONICAL_FILE="canonical-structure.yaml"
VERSION_FILE="coordinator-schema-version"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

MODE="staged"
COMMIT_REF=""

for arg in "$@"; do
    case "$arg" in
        --staged)
            MODE="staged"
            ;;
        --commit=*)
            MODE="commit"
            COMMIT_REF="${arg#--commit=}"
            ;;
        -h|--help)
            sed -n '2,/^# Negative-spec/p' "$0" | grep '^#' | sed 's/^# \?//' || true
            exit 0
            ;;
        *)
            echo "check-schema-version-bump.sh: unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Verify we are inside a git repo
# ---------------------------------------------------------------------------

GIT_ROOT="$(git -C "$PLUGIN_ROOT" rev-parse --show-toplevel 2>/dev/null)" || {
    echo "check-schema-version-bump.sh: ERROR — not a git repo at '${PLUGIN_ROOT}'" >&2
    exit 2
}

# ---------------------------------------------------------------------------
# Compute relative paths from git root to the two files
# ---------------------------------------------------------------------------

# Normalise PLUGIN_ROOT to an absolute path.
ABS_PLUGIN_ROOT="$(cd "$PLUGIN_ROOT" && pwd)"

# Relative path from git root to plugin root, for git-diff path filtering.
# Use `git rev-parse --show-prefix` rather than a manual string-strip: git computes
# the git-root-relative path correctly regardless of path-format mismatches
# (Windows `C:/…` --show-toplevel vs MSYS `/c/…` pwd). --show-prefix returns the
# path WITH a trailing slash (e.g. "plugins/coordinator/"), or
# "" when the plugin root IS the git root — both handled below without ambiguity.
REL_PLUGIN_ROOT="$(git -C "$ABS_PLUGIN_ROOT" rev-parse --show-prefix 2>/dev/null)" || {
    echo "check-schema-version-bump.sh: ERROR — could not resolve plugin root relative to git root" >&2
    exit 2
}

# --show-prefix already carries the trailing slash, so concatenate directly.
REL_CANONICAL="${REL_PLUGIN_ROOT}${CANONICAL_FILE}"
REL_VERSION="${REL_PLUGIN_ROOT}${VERSION_FILE}"

# ---------------------------------------------------------------------------
# Build diff name-only output depending on mode
# ---------------------------------------------------------------------------

_get_changed_names() {
    if [[ "$MODE" == "staged" ]]; then
        git -C "$GIT_ROOT" diff --cached --name-only 2>/dev/null
    else
        # Verify the ref exists
        if ! git -C "$GIT_ROOT" rev-parse --verify "${COMMIT_REF}" > /dev/null 2>&1; then
            echo "check-schema-version-bump.sh: ERROR — ref not found: ${COMMIT_REF}" >&2
            exit 2
        fi
        git -C "$GIT_ROOT" diff "${COMMIT_REF}~1" "${COMMIT_REF}" --name-only 2>/dev/null
    fi
}

# Propagate the subshell's exit code: `_get_changed_names` may `exit 2` (bad ref).
# Under `set -uo pipefail` (no -e) a bare `VAR="$(...)"` would silently absorb that
# non-zero exit and proceed with an empty CHANGED_NAMES → a false "OK". The `|| exit $?`
# honours the documented exit-2 ERROR contract.
CHANGED_NAMES="$(_get_changed_names)" || exit $?

# ---------------------------------------------------------------------------
# Tripwire logic
# ---------------------------------------------------------------------------

CANONICAL_CHANGED=0
VERSION_CHANGED=0

# grep -qxF exits 1 on no match; the `if` construct absorbs that exit code, so no
# `|| true` is needed here (the script runs `set -uo pipefail`, not `set -e`).
if echo "$CHANGED_NAMES" | grep -qxF "$REL_CANONICAL" 2>/dev/null; then
    CANONICAL_CHANGED=1
fi

if echo "$CHANGED_NAMES" | grep -qxF "$REL_VERSION" 2>/dev/null; then
    VERSION_CHANGED=1
fi

# Decision matrix:
#   canonical NOT changed → OK regardless of version
#   canonical changed AND version changed → OK (proper bump)
#   canonical changed AND version NOT changed → VIOLATION

if [[ "$CANONICAL_CHANGED" -eq 0 ]]; then
    echo "OK: ${CANONICAL_FILE} not modified — no version bump required"
    exit 0
fi

if [[ "$VERSION_CHANGED" -eq 1 ]]; then
    echo "OK: ${CANONICAL_FILE} modified and ${VERSION_FILE} bumped"
    exit 0
fi

# Violation
echo "VIOLATION: ${CANONICAL_FILE} was modified but ${VERSION_FILE} was not bumped."
echo "  Consumers rely on the version integer to detect schema drift. Every structural"
echo "  change to canonical-structure.yaml must be accompanied by a version increment."
echo "  Fix: increment the integer in ${REL_VERSION} (currently: $(cat "${ABS_PLUGIN_ROOT}/${VERSION_FILE}" 2>/dev/null || echo '?')) and re-stage."
exit 1
