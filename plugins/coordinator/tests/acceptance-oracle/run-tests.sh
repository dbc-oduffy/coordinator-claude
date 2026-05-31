#!/usr/bin/env bash
# Purpose: Exercise bin/check-acceptance-oracle.sh against the synthetic fixture and assert expected verdicts.
# Spec: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md § Task 2
#
# Run from the ~/.claude repo root:
#   bash plugins/coordinator/tests/acceptance-oracle/run-tests.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve paths relative to this script's location (portable across machines)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

GATE="$COORDINATOR_ROOT/bin/check-acceptance-oracle.sh"
FIXTURE="$SCRIPT_DIR/fixture-plan.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

pass() { echo "[PASS] $1"; (( PASS++ )) || true; }
fail() { echo "[FAIL] $1"; (( FAIL++ )) || true; }

assert_contains() {
    local label="$1" text="$2" pattern="$3"
    if echo "$text" | grep -q "$pattern"; then
        pass "$label — contains: $pattern"
    else
        fail "$label — expected to contain: $pattern"
        echo "       actual text: $text" >&2
    fi
}

assert_not_contains() {
    local label="$1" text="$2" pattern="$3"
    if ! echo "$text" | grep -q "$pattern"; then
        pass "$label — does not contain: $pattern"
    else
        fail "$label — expected NOT to contain: $pattern"
    fi
}

# ---------------------------------------------------------------------------
# Test 1: Main fixture run — rows 2, 4, 6 are red; exit code must be non-zero
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: fixture run (rows 2, 4, 6 red) ==="

# Run from REPO_ROOT so relative paths in fixture resolve correctly
stdout="$(cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" 2>/dev/null)" || true
stderr="$(cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" 2>&1 >/dev/null)" || true
exit_code=0
cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" >/dev/null 2>&1 || exit_code=$?

if [[ $exit_code -ne 0 ]]; then
    pass "Test 1a — exit code non-zero (got $exit_code)"
else
    fail "Test 1a — expected non-zero exit code, got 0"
fi

# Re-run capturing both streams cleanly
combined="$(cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" 2>&1)" || true
stdout_only="$(cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" 2>/dev/null)" || true
stderr_only="$(cd "$REPO_ROOT" && bash "$GATE" "$FIXTURE" 2>&1 >/dev/null)" || true

# Assert final summary line (rows 1+3 green, 2+4+6 red, 5 skipped → 2/5 green; 3 red; 1 skipped)
assert_contains "Test 1b — summary line" "$stdout_only" "2/5 gate-bound acceptance tests green; 3 red; 1 skipped (reviewer-judgment)"

# Assert cited-resolvable loud log on stderr for row 3
assert_contains "Test 1c — row 3 cited loud log on stderr" "$stderr_only" "AC-3 satisfied by citation"
assert_contains "Test 1c — row 3 cited log contains NOT re-run" "$stderr_only" "NOT re-run on this host"

# Assert per-row red explanations are present for rows 2, 4, 6
assert_contains "Test 1d — row 2 red (no match)" "$stdout_only" "AC-2"
assert_contains "Test 1d — row 2 red reason" "$stdout_only" "no match"

assert_contains "Test 1e — row 4 red (ref does not resolve)" "$stdout_only" "AC-4"
assert_contains "Test 1e — row 4 red reason" "$stdout_only" "does not resolve"

assert_contains "Test 1f — row 6 red (all-must-match)" "$stdout_only" "AC-6"
assert_contains "Test 1f — row 6 red reason" "$stdout_only" "all-must-match"

# Assert row 5 (reviewer-judgment) is NOT mentioned as red
assert_not_contains "Test 1g — row 5 not red" "$stdout_only" "AC-5.*red"

# ---------------------------------------------------------------------------
# Test 2: COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 — exit 0 + override message
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 ==="

override_out=""
override_exit=0
override_out="$(cd "$REPO_ROOT" && COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 bash "$GATE" "$FIXTURE" 2>&1)" || override_exit=$?

if [[ $override_exit -eq 0 ]]; then
    pass "Test 2a — exit 0 with override active"
else
    fail "Test 2a — expected exit 0 with override, got $override_exit"
fi

assert_contains "Test 2b — override message printed" "$override_out" "override active"
assert_contains "Test 2c — override message mentions env var" "$override_out" "COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1"
assert_contains "Test 2d — gate skipped message" "$override_out" "gate skipped"

# ---------------------------------------------------------------------------
# Test 3: Missing-table case — plan with no ## Acceptance Criteria heading
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: plan with no ## Acceptance Criteria heading ==="

TMPFILE="$(mktemp /tmp/check-oracle-test-XXXX.md)"
cat > "$TMPFILE" <<'NOAC'
---
status: draft
kind: plan
---

# A Plan With No Acceptance Criteria

This plan predates the acceptance oracle. It has no bindable table.

## Goals

- Do some stuff
NOAC

noac_out=""
noac_exit=0
noac_out="$(bash "$GATE" "$TMPFILE" 2>&1)" || noac_exit=$?
rm -f "$TMPFILE"

if [[ $noac_exit -eq 0 ]]; then
    pass "Test 3a — exit 0 for missing-table plan"
else
    fail "Test 3a — expected exit 0 for missing-table plan, got $noac_exit"
fi

assert_contains "Test 3b — skip-with-offer message" "$noac_out" "no acceptance oracle in"
assert_contains "Test 3b — skip message contains skipping gate" "$noac_out" "skipping gate"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "============================================="

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
