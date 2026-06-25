#!/usr/bin/env bash
# test_setup_rag_decision.bats — plain-bash harness for lib/setup-rag-decision.sh
#
# Purpose: exercises all three decision branches (UE+daemon→offer, non-UE→tripwire,
# UE+no-daemon→tripwire) against a temp repo dir via injected daemon/UE state.
# Also verifies idempotency (tripwire block not duplicated on re-run).
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness mirroring bin/tests/check-machine-path-leak.bats. Named .bats so
# any acceptance-oracle grep resolves it correctly.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1c (AC3)
#
# Run: bash plugins/coordinator-claude/coordinator/tests/test_setup_rag_decision.bats
#      from the ~/.claude repo root.
#
# Injection contract (see lib/setup-rag-decision.sh for full doc):
#   SETUP_RAG_IS_UE_REPO   — "1" = UE repo, "0" = non-UE repo
#   SETUP_RAG_DAEMON_PROBE — shell command; exit 0 = daemon present, non-0 = absent
#   SETUP_RAG_TARGET_ROOT  — repo root to operate on (overrides --root and cwd)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../lib/setup-rag-decision.sh"

# ---------------------------------------------------------------------------
# Test framework (mirrors bin/tests/check-machine-path-leak.bats)
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
    echo "  FAIL: $1"
    FAIL_MSGS+=("$1")
    (( FAIL++ )) || true
}

run_test() {
    local name="$1"
    local fn="$2"
    echo "--- ${name}"
    if "${fn}"; then
        pass "${name}"
    else
        fail "${name}"
    fi
}

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_sentinel="coordinator-rag-tripwire: un-indexed"

_tripwire_present() {
    grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md"
}

_tripwire_count() {
    grep -cF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" || true
}

# ---------------------------------------------------------------------------
# Branch 1: UE repo + daemon present → offer to index (no tripwire written)
# ---------------------------------------------------------------------------

test_T1_ue_daemon_present_offer_no_tripwire() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=1 SETUP_RAG_DAEMON_PROBE="true" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    # Output must mention the offer.
    local offer_found=0
    case "$output" in
        *"branch 1"*|*"offer"*|*"Offer"*) offer_found=1 ;;
    esac
    if [ "$offer_found" -eq 0 ]; then
        printf '    FAIL: expected offer mention in output: %s\n' "$output" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    # Tripwire must NOT be written.
    if grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire must not be written on branch 1\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Branch 2: non-UE repo → tripwire (daemon state irrelevant)
# ---------------------------------------------------------------------------

test_T2_nonue_daemon_present_tripwire_written() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="true" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    if ! grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire not written for non-UE repo\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

test_T2b_nonue_daemon_absent_still_tripwire() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    if ! grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire not written for non-UE repo with absent daemon\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Branch 3: UE repo but no daemon → tripwire
# ---------------------------------------------------------------------------

test_T3_ue_no_daemon_tripwire_written() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=1 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    if ! grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire not written for UE repo with no daemon\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Idempotency: re-run does NOT duplicate the tripwire block
# ---------------------------------------------------------------------------

test_T4_rerun_branch2_no_duplicate() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status

    # First run.
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: first run exited %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi
    if ! grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire not written on first run\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    # Second run — must not duplicate.
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: second run exited %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    local count
    count="$(grep -cF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" || true)"
    if [ "$count" -ne 1 ]; then
        printf '    FAIL: expected 1 tripwire occurrence, got %s\n' "$count" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

test_T5_rerun_branch3_no_duplicate() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    SETUP_RAG_IS_UE_REPO=1 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" >/dev/null 2>&1
    SETUP_RAG_IS_UE_REPO=1 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" >/dev/null 2>&1

    local count
    count="$(grep -cF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" || true)"
    if [ "$count" -ne 1 ]; then
        printf '    FAIL: expected 1 tripwire occurrence after two runs, got %s\n' "$count" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Tripwire block content sanity
# ---------------------------------------------------------------------------

test_T6_tripwire_contains_tier3_guidance() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" >/dev/null 2>&1

    if ! grep -qF "Tier-3" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: "Tier-3" not found in tripwire block\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# --dry-run does not write the file
# ---------------------------------------------------------------------------

test_T7_dryrun_branch2_no_mutation() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local before
    before="$(cat "${TEST_ROOT}/CLAUDE.md")"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" --dry-run 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: --dry-run exited %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    local after
    after="$(cat "${TEST_ROOT}/CLAUDE.md")"

    if [ "$before" != "$after" ]; then
        printf '    FAIL: CLAUDE.md was mutated by --dry-run\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

test_T8_dryrun_branch3_no_mutation() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local before
    before="$(cat "${TEST_ROOT}/CLAUDE.md")"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO=1 SETUP_RAG_DAEMON_PROBE="false" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" --dry-run 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: --dry-run exited %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    local after
    after="$(cat "${TEST_ROOT}/CLAUDE.md")"

    if [ "$before" != "$after" ]; then
        printf '    FAIL: CLAUDE.md was mutated by --dry-run\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Fail-loud: ambiguous UE detection (SETUP_RAG_IS_UE_REPO not 0 or 1)
# ---------------------------------------------------------------------------

test_T9_ambiguous_ue_value_nonzero_exit() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    output="$(SETUP_RAG_IS_UE_REPO="maybe" SETUP_RAG_DAEMON_PROBE="true" SETUP_RAG_TARGET_ROOT="$TEST_ROOT" \
        bash "$SUBJECT" 2>&1)"
    status=$?

    rm -rf "$TEST_ROOT"

    if [ "$status" -eq 0 ]; then
        printf '    FAIL: expected non-zero exit for ambiguous SETUP_RAG_IS_UE_REPO, got 0\n' >&2
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# --root flag works (no SETUP_RAG_TARGET_ROOT override)
# ---------------------------------------------------------------------------

test_T10_root_flag_branch2_via_nonue() {
    local TEST_ROOT
    TEST_ROOT="$(mktemp -d)"
    printf '# Test CLAUDE.md\n' > "${TEST_ROOT}/CLAUDE.md"

    local output status
    # Explicitly unset the env override so --root is exercised.
    output="$(SETUP_RAG_IS_UE_REPO=0 SETUP_RAG_DAEMON_PROBE="false" \
        bash "$SUBJECT" --root "$TEST_ROOT" 2>&1)"
    status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    if ! grep -qF "${_sentinel}" "${TEST_ROOT}/CLAUDE.md" 2>/dev/null; then
        printf '    FAIL: tripwire not written when using --root flag\n' >&2
        rm -rf "$TEST_ROOT"
        return 1
    fi

    rm -rf "$TEST_ROOT"
    return 0
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if [[ ! -f "$SUBJECT" ]]; then
    echo "ERROR: subject not found at ${SUBJECT}" >&2
    exit 2
fi

run_test "T1: UE repo + daemon present → offer emitted, no tripwire written" \
    test_T1_ue_daemon_present_offer_no_tripwire

run_test "T2: non-UE repo → tripwire block written into CLAUDE.md" \
    test_T2_nonue_daemon_present_tripwire_written

run_test "T2b: non-UE repo with absent daemon → still tripwire (branch 2 wins)" \
    test_T2b_nonue_daemon_absent_still_tripwire

run_test "T3: UE repo + no daemon → tripwire block written into CLAUDE.md" \
    test_T3_ue_no_daemon_tripwire_written

run_test "T4: re-run on branch 2 does not duplicate the tripwire block" \
    test_T4_rerun_branch2_no_duplicate

run_test "T5: re-run on branch 3 does not duplicate the tripwire block" \
    test_T5_rerun_branch3_no_duplicate

run_test "T6: tripwire block contains 'Tier-3' guidance" \
    test_T6_tripwire_contains_tier3_guidance

run_test "T7: --dry-run on branch 2 does not mutate CLAUDE.md" \
    test_T7_dryrun_branch2_no_mutation

run_test "T8: --dry-run on branch 3 does not mutate CLAUDE.md" \
    test_T8_dryrun_branch3_no_mutation

run_test "T9: ambiguous SETUP_RAG_IS_UE_REPO value → non-zero exit" \
    test_T9_ambiguous_ue_value_nonzero_exit

run_test "T10: --root flag routes correctly (branch 2 via non-UE)" \
    test_T10_root_flag_branch2_via_nonue

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed."

if [[ ${FAIL} -gt 0 ]]; then
    echo ""
    echo "Failed tests:"
    for msg in "${FAIL_MSGS[@]}"; do
        echo "  - ${msg}"
    done
    exit 1
fi

exit 0
