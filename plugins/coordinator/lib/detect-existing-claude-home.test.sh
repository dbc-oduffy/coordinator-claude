#!/usr/bin/env bash
# lib/detect-existing-claude-home.test.sh — unit tests for detect-existing-claude-home.sh
#
# Spec backlink: chunk C7 — Track A/B detection helper (P8)
#
# Tests:
#   T1  Vanilla fixture → Track A
#   T2  Plugin fixture (non-empty plugins/ subdir) → Track B
#   T3  Substantial CLAUDE.md fixture (>10 non-blank lines) → Track B
#   T4  Git-init'd fixture → Track B
#
# Self-contained: creates temp fixture dirs, runs the script against them,
# asserts stdout contains the expected track label, then cleans up.
# Exit code: 0 if all tests pass, 1 if any fail.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECTOR="$SCRIPT_DIR/detect-existing-claude-home.sh"

PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
_fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

echo "=== detect-existing-claude-home.test.sh ==="

# Guard: detector must exist and be readable.
if [[ ! -f "$DETECTOR" ]]; then
    echo "FATAL: detector not found at $DETECTOR" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Temp dir management
# ---------------------------------------------------------------------------
TMPROOT="$(mktemp -d)"
# Cleanup on exit (including error paths) — read-only guarantee: we only
# remove dirs we created under TMPROOT.
trap 'rm -rf "$TMPROOT"' EXIT

# ---------------------------------------------------------------------------
# T1: Vanilla fixture → Track A
# ---------------------------------------------------------------------------
echo "--- T1: vanilla fixture → Track A"
T1_DIR="$TMPROOT/vanilla"
mkdir -p "$T1_DIR"

T1_OUT="$(bash "$DETECTOR" "$T1_DIR")"
if [[ "$T1_OUT" == track=A* ]]; then
    _pass "T1 vanilla → Track A"
else
    _fail "T1 vanilla → Track A" "got: '$T1_OUT'"
fi

# ---------------------------------------------------------------------------
# T2: Plugin fixture → Track B (B2 trigger)
# ---------------------------------------------------------------------------
echo "--- T2: plugin fixture → Track B"
T2_DIR="$TMPROOT/with-plugin"
mkdir -p "$T2_DIR/plugins/my-plugin"
# Create at least one file inside the plugin dir to make it non-empty.
echo "plugin content" > "$T2_DIR/plugins/my-plugin/PLUGIN.md"

T2_OUT="$(bash "$DETECTOR" "$T2_DIR")"
if [[ "$T2_OUT" == track=B* ]]; then
    _pass "T2 plugin present → Track B"
else
    _fail "T2 plugin present → Track B" "got: '$T2_OUT'"
fi

# T2b: a file directly under plugins/ (not in a subdir) → Track B
echo "--- T2b: file directly under plugins/ → Track B"
T2B_DIR="$TMPROOT/with-plugin-file"
mkdir -p "$T2B_DIR/plugins"
echo "x" > "$T2B_DIR/plugins/some-plugin-file.md"
T2B_OUT="$(bash "$DETECTOR" "$T2B_DIR")"
if [[ "$T2B_OUT" == track=B* ]]; then
    _pass "T2b file under plugins/ → Track B"
else
    _fail "T2b file under plugins/ → Track B" "got: '$T2B_OUT'"
fi

# T2c: plugins/ exists but contains only an EMPTY subdir → Track A (fallthrough)
echo "--- T2c: empty plugins/ subdir → Track A"
T2C_DIR="$TMPROOT/with-empty-plugin-dir"
mkdir -p "$T2C_DIR/plugins/empty-plugin"
T2C_OUT="$(bash "$DETECTOR" "$T2C_DIR")"
if [[ "$T2C_OUT" == track=A* ]]; then
    _pass "T2c empty plugins/ subdir → Track A"
else
    _fail "T2c empty plugins/ subdir → Track A" "got: '$T2C_OUT'"
fi

# ---------------------------------------------------------------------------
# T3: Substantial CLAUDE.md fixture → Track B (B3 trigger)
# ---------------------------------------------------------------------------
echo "--- T3: substantial CLAUDE.md → Track B"
T3_DIR="$TMPROOT/with-claude-md"
mkdir -p "$T3_DIR"
# Write a CLAUDE.md with exactly 11 non-blank lines (crosses the >10 threshold).
{
    printf '# My Claude Config\n\n'
    for i in $(seq 1 11); do
        printf 'Non-blank line %d\n' "$i"
    done
} > "$T3_DIR/CLAUDE.md"

T3_OUT="$(bash "$DETECTOR" "$T3_DIR")"
if [[ "$T3_OUT" == track=B* ]]; then
    _pass "T3 substantial CLAUDE.md → Track B"
else
    _fail "T3 substantial CLAUDE.md → Track B" "got: '$T3_OUT'"
fi

# Sanity-check: a stub CLAUDE.md with ≤10 non-blank lines should NOT trigger B.
echo "--- T3b: stub CLAUDE.md (<=10 non-blank lines) → still Track A"
T3B_DIR="$TMPROOT/with-stub-claude-md"
mkdir -p "$T3B_DIR"
{
    printf '# Stub\n\n'
    for i in $(seq 1 5); do
        printf 'Line %d\n' "$i"
    done
} > "$T3B_DIR/CLAUDE.md"

T3B_OUT="$(bash "$DETECTOR" "$T3B_DIR")"
if [[ "$T3B_OUT" == track=A* ]]; then
    _pass "T3b stub CLAUDE.md → Track A (not triggered)"
else
    _fail "T3b stub CLAUDE.md → Track A" "got: '$T3B_OUT'"
fi

# ---------------------------------------------------------------------------
# T4: Git-init'd fixture → Track B (B1 trigger)
# ---------------------------------------------------------------------------
echo "--- T4: git-init'd fixture → Track B"
T4_DIR="$TMPROOT/git-tracked"
mkdir -p "$T4_DIR"
# Suppress git's hint about initial branch name.
git -C "$T4_DIR" init --quiet

T4_OUT="$(bash "$DETECTOR" "$T4_DIR")"
if [[ "$T4_OUT" == track=B* ]]; then
    _pass "T4 git-tracked → Track B"
else
    _fail "T4 git-tracked → Track B" "got: '$T4_OUT'"
fi

# T4b: TARGET is a plain subdir of an ANCESTOR git repo → Track A (regression
# guard for the B1 ancestor-false-positive fix — must check TARGET/.git, not
# `rev-parse --is-inside-work-tree`).
echo "--- T4b: subdir of an ancestor git repo → Track A"
T4B_PARENT="$TMPROOT/git-parent"
mkdir -p "$T4B_PARENT"
git -C "$T4B_PARENT" init --quiet
T4B_DIR="$T4B_PARENT/dot-claude"   # a subdir; has NO .git of its own
mkdir -p "$T4B_DIR"
T4B_OUT="$(bash "$DETECTOR" "$T4B_DIR")"
if [[ "$T4B_OUT" == track=A* ]]; then
    _pass "T4b subdir of ancestor repo → Track A (not git-tracked itself)"
else
    _fail "T4b subdir of ancestor repo → Track A" "got: '$T4B_OUT'"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
