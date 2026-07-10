#!/usr/bin/env bash
# mint-deliverable-id.test.sh — Self-contained tests for mint-deliverable-id.sh
#
# Purpose: Verifies the three minting paths (carry / mint-from-stub / mint-from-slug),
#          output format, stderr logging, idempotency, and error handling.
#
# Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1, C3a, AC1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/mint-deliverable-id.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Test 1: carry path — --deliverable-id echoes the id unchanged
# ---------------------------------------------------------------------------
EXISTING_ID="dlv-my-plan-abc123"
CARRY_OUT="$(bash "$HELPER" --deliverable-id "$EXISTING_ID" 2>/dev/null)"
if [[ "$CARRY_OUT" == "$EXISTING_ID" ]]; then
  pass "T1: carry path echoes id unchanged ('$CARRY_OUT')"
else
  fail "T1: carry path expected '$EXISTING_ID', got '$CARRY_OUT'"
fi

# ---------------------------------------------------------------------------
# Test 2: carry path — idempotent (calling twice with same id yields same output)
# ---------------------------------------------------------------------------
CARRY_OUT2="$(bash "$HELPER" --deliverable-id "$EXISTING_ID" 2>/dev/null)"
if [[ "$CARRY_OUT" == "$CARRY_OUT2" ]]; then
  pass "T2: carry path is idempotent (same input → same output)"
else
  fail "T2: carry path produced different output on second call: '$CARRY_OUT2'"
fi

# ---------------------------------------------------------------------------
# Test 3: carry path — logs "carry" to stderr
# ---------------------------------------------------------------------------
CARRY_STDERR="$(bash "$HELPER" --deliverable-id "$EXISTING_ID" 2>&1 >/dev/null)"
if echo "$CARRY_STDERR" | grep -q "carry"; then
  pass "T3: carry path logs 'carry' to stderr"
else
  fail "T3: carry path did not log 'carry' to stderr (got: '$CARRY_STDERR')"
fi

# ---------------------------------------------------------------------------
# Test 4: stub path — mints "dlv-<stub_id>"
# ---------------------------------------------------------------------------
STUB_ID="some-feature-3"
STUB_OUT="$(bash "$HELPER" --stub-id "$STUB_ID" 2>/dev/null)"
EXPECTED_STUB="dlv-${STUB_ID}"
if [[ "$STUB_OUT" == "$EXPECTED_STUB" ]]; then
  pass "T4: stub path mints 'dlv-<stub_id>' ('$STUB_OUT')"
else
  fail "T4: stub path expected '$EXPECTED_STUB', got '$STUB_OUT'"
fi

# ---------------------------------------------------------------------------
# Test 5: stub path — output starts with "dlv-" prefix
# ---------------------------------------------------------------------------
if [[ "$STUB_OUT" =~ ^dlv- ]]; then
  pass "T5: stub path output has 'dlv-' prefix"
else
  fail "T5: stub path output missing 'dlv-' prefix ('$STUB_OUT')"
fi

# ---------------------------------------------------------------------------
# Test 6: stub path — logs "mint-from-stub" to stderr
# ---------------------------------------------------------------------------
STUB_STDERR="$(bash "$HELPER" --stub-id "$STUB_ID" 2>&1 >/dev/null)"
if echo "$STUB_STDERR" | grep -q "mint-from-stub"; then
  pass "T6: stub path logs 'mint-from-stub' to stderr"
else
  fail "T6: stub path did not log 'mint-from-stub' to stderr (got: '$STUB_STDERR')"
fi

# ---------------------------------------------------------------------------
# Test 7: slug path — mints "dlv-<slug>-<6hex>"
# ---------------------------------------------------------------------------
SLUG="my-plan"
SLUG_OUT="$(bash "$HELPER" --slug "$SLUG" 2>/dev/null)"
if [[ "$SLUG_OUT" =~ ^dlv-my-plan-[0-9a-f]{6}$ ]]; then
  pass "T7: slug path mints 'dlv-<slug>-<6hex>' ('$SLUG_OUT')"
else
  fail "T7: slug path output '$SLUG_OUT' does not match 'dlv-my-plan-[0-9a-f]{6}'"
fi

# ---------------------------------------------------------------------------
# Test 8: slug path — output has exactly 6 hex chars suffix
# ---------------------------------------------------------------------------
HEX_PART="${SLUG_OUT##dlv-${SLUG}-}"
if [[ "$HEX_PART" =~ ^[0-9a-f]{6}$ ]]; then
  pass "T8: slug path 6hex suffix is valid lowercase hex ('$HEX_PART')"
else
  fail "T8: slug path suffix '$HEX_PART' is not exactly 6 lowercase hex chars"
fi

# ---------------------------------------------------------------------------
# Test 9: slug path — logs "mint-from-slug" to stderr
# ---------------------------------------------------------------------------
SLUG_STDERR="$(bash "$HELPER" --slug "$SLUG" 2>&1 >/dev/null)"
if echo "$SLUG_STDERR" | grep -q "mint-from-slug"; then
  pass "T9: slug path logs 'mint-from-slug' to stderr"
else
  fail "T9: slug path did not log 'mint-from-slug' to stderr (got: '$SLUG_STDERR')"
fi

# ---------------------------------------------------------------------------
# Test 10: slug path — two independent mints of the same slug yield "dlv-<slug>-*" format
#           (each is a new unique id; both must match the pattern)
# ---------------------------------------------------------------------------
SLUG_OUT_A="$(bash "$HELPER" --slug "alpha-plan" 2>/dev/null)"
sleep 1  # ensure different epoch-second for distinctness
SLUG_OUT_B="$(bash "$HELPER" --slug "alpha-plan" 2>/dev/null)"
if [[ "$SLUG_OUT_A" =~ ^dlv-alpha-plan-[0-9a-f]{6}$ ]] && \
   [[ "$SLUG_OUT_B" =~ ^dlv-alpha-plan-[0-9a-f]{6}$ ]]; then
  pass "T10: both independent slug mints match format (A='$SLUG_OUT_A', B='$SLUG_OUT_B')"
else
  fail "T10: one or both slug mints have wrong format (A='$SLUG_OUT_A', B='$SLUG_OUT_B')"
fi

# ---------------------------------------------------------------------------
# Test 11: stub path is deterministic — same stub_id always yields same id
# ---------------------------------------------------------------------------
STUB_OUT_A="$(bash "$HELPER" --stub-id "roadmap-stub-7" 2>/dev/null)"
STUB_OUT_B="$(bash "$HELPER" --stub-id "roadmap-stub-7" 2>/dev/null)"
if [[ "$STUB_OUT_A" == "$STUB_OUT_B" && "$STUB_OUT_A" == "dlv-roadmap-stub-7" ]]; then
  pass "T11: stub path is deterministic ('$STUB_OUT_A')"
else
  fail "T11: stub path not deterministic (A='$STUB_OUT_A', B='$STUB_OUT_B')"
fi

# ---------------------------------------------------------------------------
# Test 12: fail-loud — no arguments provided
# ---------------------------------------------------------------------------
if bash "$HELPER" 2>/dev/null; then
  fail "T12: should have exited non-zero when no arguments supplied"
else
  pass "T12: exits non-zero when no arguments supplied"
fi

# ---------------------------------------------------------------------------
# Test 13: fail-loud — mutually exclusive flags (--stub-id + --slug)
# ---------------------------------------------------------------------------
if bash "$HELPER" --stub-id "foo-1" --slug "bar" 2>/dev/null; then
  fail "T13: should have exited non-zero for mutually exclusive flags"
else
  pass "T13: exits non-zero for mutually exclusive --stub-id + --slug"
fi

# ---------------------------------------------------------------------------
# Test 14: fail-loud — mutually exclusive flags (--deliverable-id + --slug)
# ---------------------------------------------------------------------------
if bash "$HELPER" --deliverable-id "dlv-existing-abc" --slug "bar" 2>/dev/null; then
  fail "T14: should have exited non-zero for --deliverable-id + --slug"
else
  pass "T14: exits non-zero for mutually exclusive --deliverable-id + --slug"
fi

# ---------------------------------------------------------------------------
# Test 15: slug handles a realistic slug with hyphens and numbers
# ---------------------------------------------------------------------------
SLUG_COMPLEX="fleet-deliverable-spine-2026-07-03"
SLUG_COMPLEX_OUT="$(bash "$HELPER" --slug "$SLUG_COMPLEX" 2>/dev/null)"
if [[ "$SLUG_COMPLEX_OUT" =~ ^dlv-fleet-deliverable-spine-2026-07-03-[0-9a-f]{6}$ ]]; then
  pass "T15: slug path handles realistic slug with hyphens/numbers ('$SLUG_COMPLEX_OUT')"
else
  fail "T15: complex slug output '$SLUG_COMPLEX_OUT' did not match expected pattern"
fi

# ---------------------------------------------------------------------------
# Test 16: unknown argument exits non-zero
# ---------------------------------------------------------------------------
if bash "$HELPER" --unknown-flag 2>/dev/null; then
  fail "T16: should have exited non-zero for unknown argument"
else
  pass "T16: exits non-zero for unknown argument"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
