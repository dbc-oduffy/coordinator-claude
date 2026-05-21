#!/usr/bin/env bash
# block-dev-side-mirror-wiki.test.sh — Fixture for block-dev-side-mirror-wiki.sh hook.
#
# Spec backlink: docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md § Phase 5
#
# Verifies:
#   1. POSITIVE: Write to ~/.claude/docs/wiki/<name>.md is BLOCKED when a
#      bundled copy exists at <plugin>/docs/wiki/<name>.md.
#   2. NEGATIVE: Write to <project>/docs/wiki/<name>.md (not dev-wiki prefix)
#      is NOT blocked even when a bundled copy exists.
#   3. OVERRIDE: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 suppresses the block.
#
# Note: This file establishes the hook-test fixture convention for
# block-*-wiki.sh hooks. No prior hook test fixtures existed in this directory
# before 2026-05-15. Future hook test fixtures should follow this shape.
#
# Run: bash ~/.claude/plugins/coordinator/hooks/scripts/tests/block-dev-side-mirror-wiki.test.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${SCRIPT_DIR}/../block-dev-side-mirror-wiki.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Setup: isolated temp dirs
# ---------------------------------------------------------------------------

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FAKE_HOME="${TMPDIR_ROOT}/home"
FAKE_PLUGIN_ROOT="${FAKE_HOME}/.claude/plugins/coordinator-claude/coordinator"
FAKE_DEV_WIKI="${FAKE_HOME}/.claude/docs/wiki"
FAKE_BUNDLED_WIKI="${FAKE_PLUGIN_ROOT}/docs/wiki"
FAKE_PROJECT_WIKI="${TMPDIR_ROOT}/project/docs/wiki"

mkdir -p "$FAKE_DEV_WIKI"
mkdir -p "$FAKE_BUNDLED_WIKI"
mkdir -p "$FAKE_PROJECT_WIKI"

# Create a bundled wiki (the plugin-doctrine canonical copy)
echo "# Plugin-doctrine wiki" > "${FAKE_BUNDLED_WIKI}/writing-plans.md"

# Create a wrapper that substitutes HOME and CLAUDE_PLUGIN_ROOT
PATCHED_HOOK="${TMPDIR_ROOT}/patched-hook.sh"
sed \
  -e "s|PLUGIN_ROOT=\"\${CLAUDE_PLUGIN_ROOT:-\${HOME}/.claude/plugins/coordinator-claude/coordinator}\"|PLUGIN_ROOT=\"${FAKE_PLUGIN_ROOT}\"|" \
  -e "s|DEV_WIKI_ABS=\"\${HOME}/.claude/docs/wiki\"|DEV_WIKI_ABS=\"${FAKE_DEV_WIKI}\"|" \
  "$HOOK" > "$PATCHED_HOOK"
chmod +x "$PATCHED_HOOK"

# ---------------------------------------------------------------------------
# Test 1 POSITIVE: Write to dev-side path where bundled exists → blocked (exit 1)
# ---------------------------------------------------------------------------
echo "--- Test 1 (positive): write to dev-side path with bundled copy → BLOCK"
INPUT=$(cat <<EOF
{"tool_name":"Write","tool_input":{"file_path":"${FAKE_DEV_WIKI}/writing-plans.md","content":"# Mirror attempt"}}
EOF
)
stderr_output=$(echo "$INPUT" | "$PATCHED_HOOK" 2>&1 >/dev/null)
exit_code=$?
if [ "$exit_code" -eq 1 ]; then
  pass "exit 1 (blocked) on dev-side write with bundled copy"
else
  fail "expected exit 1, got $exit_code"
fi
if echo "$stderr_output" | grep -q "block"; then
  pass "stderr contains 'block' decision"
else
  fail "stderr missing block decision: $stderr_output"
fi
if echo "$stderr_output" | grep -q "writing-plans.md"; then
  pass "stderr names the wiki file"
else
  fail "stderr missing wiki filename: $stderr_output"
fi

# ---------------------------------------------------------------------------
# Test 2 NEGATIVE: Write to project wiki path (not dev-wiki prefix) → allowed
# ---------------------------------------------------------------------------
echo "--- Test 2 (negative): write to project wiki path → NOT blocked"
INPUT=$(cat <<EOF
{"tool_name":"Write","tool_input":{"file_path":"${FAKE_PROJECT_WIKI}/writing-plans.md","content":"# Project wiki"}}
EOF
)
exit_code=0
echo "$INPUT" | "$PATCHED_HOOK" 2>/dev/null || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 (allowed) for project wiki path"
else
  fail "expected exit 0 for non-dev-wiki path, got $exit_code"
fi

# ---------------------------------------------------------------------------
# Test 3 NEGATIVE: Write to dev-side path where NO bundled copy exists → allowed
# ---------------------------------------------------------------------------
echo "--- Test 3 (negative): write to dev-side path with no bundled copy → NOT blocked"
INPUT=$(cat <<EOF
{"tool_name":"Write","tool_input":{"file_path":"${FAKE_DEV_WIKI}/new-project-only-wiki.md","content":"# New project wiki"}}
EOF
)
exit_code=0
echo "$INPUT" | "$PATCHED_HOOK" 2>/dev/null || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 (allowed) for dev-side path with no bundled copy"
else
  fail "expected exit 0 for no-bundled-copy case, got $exit_code"
fi

# ---------------------------------------------------------------------------
# Test 4 OVERRIDE: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 suppresses block
# ---------------------------------------------------------------------------
echo "--- Test 4 (override): COORDINATOR_OVERRIDE_WIKI_MIRROR=1 → NOT blocked"
INPUT=$(cat <<EOF
{"tool_name":"Write","tool_input":{"file_path":"${FAKE_DEV_WIKI}/writing-plans.md","content":"# Override write"}}
EOF
)
exit_code=0
echo "$INPUT" | COORDINATOR_OVERRIDE_WIKI_MIRROR=1 "$PATCHED_HOOK" 2>/dev/null || exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 with COORDINATOR_OVERRIDE_WIKI_MIRROR=1"
else
  fail "expected exit 0 with override, got $exit_code"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
