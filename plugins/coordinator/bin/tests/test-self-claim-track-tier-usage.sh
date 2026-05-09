#!/bin/bash
# test-self-claim-track-tier-usage.sh — Verify Wave 3 self-claim in track-tier-usage.sh.
#
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
#
# Validates:
#   1. With an active session: the self-claim block appends the tier-usage JSON path
#      to the session's touched.txt after the Python write.
#   2. The hook still exits 0 on no-session (best-effort contract).
#
# Note: The hook itself requires a PostToolUse JSON payload. We test the self-claim
# block's plumbing directly rather than exercising the full hook, since the hook's
# Python block exercises Python and JSON — orthogonal to self-claim correctness.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-self-claim-track-tier-usage.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${SCRIPT_DIR}/../../lib/coordinator-session.sh"
HOOK_SCRIPT="${SCRIPT_DIR}/../../hooks/scripts/track-tier-usage.sh"

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
    echo "  FAIL: $1"
    (( FAIL++ )) || true
}

assert_file_contains() {
    local label="$1" needle="$2" file="$3"
    if grep -qF "$needle" "$file" 2>/dev/null; then
        return 0
    else
        echo "    Expected '$needle' in $file" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Scratch git repo setup / teardown
# ---------------------------------------------------------------------------

SCRATCH_DIR=""

setup_repo() {
    SCRATCH_DIR=$(mktemp -d)
    cd "$SCRATCH_DIR"
    git init -q
    git config user.email "test@test.com"
    git config user.name "Test"
    touch README
    git add README
    git commit -q -m "init"
}

teardown_repo() {
    [[ -n "$SCRATCH_DIR" ]] && rm -rf "$SCRATCH_DIR"
    SCRATCH_DIR=""
}

fake_session() {
    local sid="$1"
    local sessions_dir="${SCRATCH_DIR}/.git/coordinator-sessions/${sid}"
    mkdir -p "$sessions_dir"
    touch "${sessions_dir}/touched.txt"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
    cat > "${sessions_dir}/meta.json" <<METAJSON
{
  "session_id": "${sid}",
  "branch": "test",
  "pid": "$$",
  "last_activity": "${now}",
  "goal": "test"
}
METAJSON
}

# ---------------------------------------------------------------------------
# Test 1: self-claim block appends tier-usage JSON path to session touched.txt
# ---------------------------------------------------------------------------

test_tier_usage_claim_path() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"
    local sid="test-tier-$$"
    fake_session "$sid"

    local sdir
    sdir=$(_cs_session_dir "$sid")
    local touched="${sdir}/touched.txt"

    # Simulate what the self-claim block in track-tier-usage.sh does:
    # It uses SESSION_ID and PROJECT_SLUG (extracted from hook payload earlier in the hook).
    local project_slug="test-project"
    local tier_written="${HOME}/.claude/projects/${project_slug}/tier-usage/${sid}.json"

    # The self-claim block resolves the session dir from SESSION_ID and calls cs_atomic_dedup_append.
    local tier_sdir
    tier_sdir=$(_cs_session_dir "$sid" 2>/dev/null) || true
    if [[ -n "$tier_sdir" && -f "${tier_sdir}/touched.txt" ]]; then
        cs_atomic_dedup_append "${tier_sdir}/touched.txt" "$tier_written" 2>/dev/null || true
    fi

    if assert_file_contains "tier-usage path in touched.txt" "$tier_written" "$touched"; then
        teardown_repo
        return 0
    else
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 2: Self-claim block in hook exits 0 when no session exists
# ---------------------------------------------------------------------------

test_tier_usage_no_session_exit_zero() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"

    # Replicate the self-claim block logic with no active session.
    local stderr_out
    local rc=0
    stderr_out=$(
        set +e
        _CS_TIER_LIB="$LIB"
        local project_slug="test"
        local SESSION_ID="fake-sid-$$"
        local PROJECT_SLUG="$project_slug"
        if [[ -f "$_CS_TIER_LIB" && -n "${SESSION_ID:-}" && -n "${PROJECT_SLUG:-}" ]]; then
            source "$_CS_TIER_LIB" 2>/dev/null || true
            _TIER_WRITTEN="${HOME}/.claude/projects/${PROJECT_SLUG}/tier-usage/${SESSION_ID}.json"
            _TIER_SDIR=$(_cs_session_dir "$SESSION_ID" 2>/dev/null) || true
            if [[ -n "$_TIER_SDIR" && -f "${_TIER_SDIR}/touched.txt" ]]; then
                cs_atomic_dedup_append "${_TIER_SDIR}/touched.txt" "$_TIER_WRITTEN" 2>/dev/null || true
            fi
        fi
    ) 2>&1
    rc=$?

    # The session dir for the fake sid doesn't exist, so nothing is appended — but exit is 0.
    if [[ $rc -eq 0 ]]; then
        teardown_repo
        return 0
    else
        echo "    rc=$rc stderr=$stderr_out" >&2
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 3: Self-claim wiring present in hook script
# ---------------------------------------------------------------------------

test_hook_has_selfclaim_wiring() {
    if grep -qF 'cs_atomic_dedup_append' "$HOOK_SCRIPT" 2>/dev/null && \
       grep -qF 'coordinator-session.sh' "$HOOK_SCRIPT" 2>/dev/null && \
       grep -qF '_TIER_WRITTEN' "$HOOK_SCRIPT" 2>/dev/null; then
        return 0
    else
        echo "    self-claim wiring not found in track-tier-usage.sh" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

echo "=== test-self-claim-track-tier-usage.sh ==="

echo "--- Test 1: tier-usage JSON path claimed in session touched.txt"
test_tier_usage_claim_path && pass "tier-usage claim" || fail "tier-usage claim"

echo "--- Test 2: no session — exit 0 (best-effort)"
test_tier_usage_no_session_exit_zero && pass "no session exit 0" || fail "no session exit 0"

echo "--- Test 3: hook wiring check"
test_hook_has_selfclaim_wiring && pass "hook wiring present" || fail "hook wiring present"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ $FAIL -eq 0 ]]
