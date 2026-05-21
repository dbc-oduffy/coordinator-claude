#!/usr/bin/env bash
# test-sync-plugin-wiki-mirror-guard.sh — Verify sync-plugin-wiki.sh exit-5 guard.
#
# Spec backlink: docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md § Phase 4
#
# Validates:
#   1. Script exits 0 when no dev-side mirrors exist (clean state).
#   2. Script exits 5 when a dev-side mirror of a plugin-cited wiki exists.
#   3. Exit-5 message includes both paths, both mtimes, and the remediation line.
#   4. COORDINATOR_OVERRIDE_WIKI_MIRROR=1 suppresses exit-5 and exits 0 instead.
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-sync-plugin-wiki-mirror-guard.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="${SCRIPT_DIR}/../sync-plugin-wiki.sh"

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Setup: create isolated temp dirs that mimic the dev-wiki and bundled-wiki layout
# ---------------------------------------------------------------------------

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FAKE_HOME="${TMPDIR_ROOT}/home"
FAKE_DEV_WIKI="${FAKE_HOME}/.claude/docs/wiki"
FAKE_PLUGIN_ROOT="${FAKE_HOME}/.claude/plugins/coordinator-claude/coordinator"
FAKE_BUNDLED_WIKI="${FAKE_PLUGIN_ROOT}/docs/wiki"

mkdir -p "$FAKE_DEV_WIKI"
mkdir -p "$FAKE_BUNDLED_WIKI"
mkdir -p "${FAKE_PLUGIN_ROOT}/skills"
mkdir -p "${FAKE_PLUGIN_ROOT}/commands"

# Create a fake skill that cites test-wiki.md and another-wiki.md
cat > "${FAKE_PLUGIN_ROOT}/skills/fake-skill.md" <<'EOF'
# Fake Skill
See docs/wiki/test-wiki.md for details.
Also see docs/wiki/another-wiki.md for context.
EOF

# Create bundled copies (canonical single-tree)
echo "# Test Wiki" > "${FAKE_BUNDLED_WIKI}/test-wiki.md"
echo "# Another Wiki" > "${FAKE_BUNDLED_WIKI}/another-wiki.md"

# Patch the sync script to use the fake HOME paths (via env override)
# We do this by creating a wrapper that substitutes the HOME-relative paths.
# Approach: copy the script and replace the HOME-based path declarations.
PATCHED_SCRIPT="${TMPDIR_ROOT}/sync-plugin-wiki-patched.sh"
sed \
  -e "s|PLUGIN_ROOT=\"\${HOME}/.claude/plugins/coordinator-claude/coordinator\"|PLUGIN_ROOT=\"${FAKE_PLUGIN_ROOT}\"|" \
  -e "s|DEV_WIKI=\"\${HOME}/.claude/docs/wiki\"|DEV_WIKI=\"${FAKE_DEV_WIKI}\"|" \
  -e "s|BUNDLED_WIKI=\"\${PLUGIN_ROOT}/docs/wiki\"|BUNDLED_WIKI=\"${FAKE_BUNDLED_WIKI}\"|" \
  "$SYNC_SCRIPT" > "$PATCHED_SCRIPT"
chmod +x "$PATCHED_SCRIPT"

# Also need fake files for the grep targets (CLAUDE.md, README.md, etc.) so grep doesn't error
for stub in CLAUDE.md README.md em-operating-model.md capability-catalog.md; do
  touch "${FAKE_PLUGIN_ROOT}/${stub}"
done
for dir in agents commands skills snippets pipelines hooks; do
  mkdir -p "${FAKE_PLUGIN_ROOT}/${dir}"
done
# skills/fake-skill.md already created above

# ---------------------------------------------------------------------------
# Test 1: Clean state — no dev-side mirrors → exit 0
# ---------------------------------------------------------------------------
echo "--- Test 1: clean state (no mirrors) → exit 0"
output=$("$PATCHED_SCRIPT" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 on clean state"
else
  fail "expected exit 0, got $exit_code"
fi
if echo "$output" | grep -q "clean"; then
  pass "output contains 'clean'"
else
  fail "output does not contain 'clean': $output"
fi

# ---------------------------------------------------------------------------
# Test 2: Dev-side mirror exists → exit 5
# ---------------------------------------------------------------------------
echo "--- Test 2: dev-side mirror exists → exit 5"
echo "# Dev-side mirror (should not exist)" > "${FAKE_DEV_WIKI}/test-wiki.md"
touch -t 202605150800 "${FAKE_DEV_WIKI}/test-wiki.md"   # set mtime to 2026-05-15 08:00
touch -t 202605151200 "${FAKE_BUNDLED_WIKI}/test-wiki.md"  # bundled is newer

output=$("$PATCHED_SCRIPT" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 5 ]; then
  pass "exit 5 on dev-side mirror"
else
  fail "expected exit 5, got $exit_code"
fi

# Test 3: exit-5 message contains required elements
echo "--- Test 3: exit-5 message content check"
if echo "$output" | grep -q "${FAKE_DEV_WIKI}/test-wiki.md"; then
  pass "message contains dev-side path"
else
  fail "message missing dev-side path"
fi
if echo "$output" | grep -q "${FAKE_BUNDLED_WIKI}/test-wiki.md"; then
  pass "message contains bundled path"
else
  fail "message missing bundled path"
fi
if echo "$output" | grep -q "mtime"; then
  pass "message contains 'mtime'"
else
  fail "message missing 'mtime'"
fi
if echo "$output" | grep -q "bundled is canonical"; then
  pass "message contains remediation line"
else
  fail "message missing remediation line ('bundled is canonical')"
fi

# ---------------------------------------------------------------------------
# Test 4: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 suppresses exit-5 → exit 0
# ---------------------------------------------------------------------------
echo "--- Test 4: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 → exit 0 (mirror suppressed)"
# test-wiki.md dev-side mirror still exists from Test 2
output=$(COORDINATOR_OVERRIDE_WIKI_MIRROR=1 "$PATCHED_SCRIPT" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 with COORDINATOR_OVERRIDE_WIKI_MIRROR=1"
else
  fail "expected exit 0 with override, got $exit_code"
fi
if echo "$output" | grep -q "override"; then
  pass "output mentions override"
else
  fail "output does not mention override: $output"
fi

# ---------------------------------------------------------------------------
# Test 5: Transitive discovery — citation from bundled wiki body is detected
# ---------------------------------------------------------------------------
# This test verifies the extended discovery scope (BUNDLED_WIKI added to mapfile grep).
# A bundled wiki body cites docs/wiki/transitive-wiki.md; that name should appear
# in discovery even though no skill/command/snippet cites it directly.
# Since transitive-wiki.md has no bundled copy, the script will emit a WARN and
# continue (exit 0, missing_bundled=1). We assert the WARN line mentions the name.
echo "--- Test 5: transitive citation from bundled wiki body is discovered"

# Remove the dev-side mirror from Test 2 so we get a clean exit path
rm -f "${FAKE_DEV_WIKI}/test-wiki.md"

# Create a bundled wiki that cites a transitive name not cited by any skill/command
cat > "${FAKE_BUNDLED_WIKI}/citing-wiki.md" <<'EOF'
# Citing Wiki
See docs/wiki/transitive-wiki.md for more detail.
EOF
# No bundled copy of transitive-wiki.md exists — expect a WARN, not exit-5

output=$("$PATCHED_SCRIPT" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  pass "exit 0 (transitive citation causes WARN not exit-5)"
else
  fail "expected exit 0, got $exit_code; output: $output"
fi
if echo "$output" | grep -q "transitive-wiki"; then
  pass "discovery output mentions transitive-wiki (transitive citation found)"
else
  fail "transitive-wiki not found in discovery output — transitive discovery may be broken: $output"
fi

# ---------------------------------------------------------------------------
# Cleanup and summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
