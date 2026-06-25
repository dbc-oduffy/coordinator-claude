#!/usr/bin/env bash
# test_repo_setup_phase3j_integration.bats — integration smoke for repo-setup Phase 3j.
#
# Purpose: exercise the four extended-substrate seed helpers EXACTLY as
# skills/repo-setup/SKILL.md § "Phase 3j" invokes them — as `bash <path> <repo-root>`
# SUBPROCESSES, in sequence, against one temp repo. This is the regression net for the
# source-vs-subprocess contract: the helpers are fail-loud (they `exit` non-zero on
# ambiguity / missing prereqs), so SKILL.md MUST invoke them as subprocesses, never via
# `source` (a sourced `exit` terminates the repo-setup shell). The decisive assertion is
# that a fail-loud exit in one helper (fnm-pin with fnm absent) is ISOLATED and does not
# abort the sequence — the seeds written by the earlier helpers survive and the harness
# reaches the post-fail assertions.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1 (C1e seam)
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness. The file is named .bats so acceptance-oracle greps resolve it correctly.
#
# Run: bash plugins/coordinator-claude/coordinator/tests/test_repo_setup_phase3j_integration.bats

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${SCRIPT_DIR}/../lib"
DETECT="${LIB}/setup-detect-test-cmd.sh"
HEALTH="${LIB}/setup-seed-health-ledger.sh"
RAG="${LIB}/setup-rag-decision.sh"
FNM="${LIB}/setup-fnm-pin.sh"

# ---------------------------------------------------------------------------
# Test framework (mirrors check-machine-path-leak.bats)
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
# Test 1: Phase 3j: four helpers run as subprocesses; fail-loud in one is
#         isolated; seeds survive
# ---------------------------------------------------------------------------

test_phase3j_subprocess_isolation() {
    local REPO
    REPO="$(mktemp -d)"

    # coordinator.local.md with a frontmatter block (test-cmd detector upserts into it)
    printf -- '---\nproject_type: web\n---\n' > "${REPO}/coordinator.local.md"
    # a Node stack marker so the detector has something to detect
    printf '{\n  "scripts": { "test": "vitest run", "test:unit": "vitest run unit" }\n}\n' > "${REPO}/package.json"
    # a Node pin file so fnm-pin acts (and then fails loud on absent fnm)
    printf '24\n' > "${REPO}/.node-version"

    local output status

    # 1. test-command detection (repo root via --root flag + --non-interactive)
    output="$(bash "$DETECT" --root "$REPO" --non-interactive 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: DETECT exited %d (expected 0)\n    output: %s\n' "$status" "$output" >&2
        rm -rf "$REPO"
        return 1
    fi
    if ! grep -qE '^fast_test_cmd:' "${REPO}/coordinator.local.md"; then
        printf '    FAIL: fast_test_cmd not written to coordinator.local.md after DETECT\n' >&2
        rm -rf "$REPO"
        return 1
    fi
    # Review: code-reviewer — detector writes BOTH keys; assert full_test_cmd too (coverage gap)
    if ! grep -qE '^full_test_cmd:' "${REPO}/coordinator.local.md"; then
        printf '    FAIL: full_test_cmd not written to coordinator.local.md after DETECT\n' >&2
        rm -rf "$REPO"
        return 1
    fi

    # 2. health-ledger seed
    output="$(bash "$HEALTH" "$REPO" 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: HEALTH exited %d (expected 0)\n    output: %s\n' "$status" "$output" >&2
        rm -rf "$REPO"
        return 1
    fi
    if [ ! -f "${REPO}/state/health-ledger.md" ]; then
        printf '    FAIL: health-ledger.md not created after HEALTH\n' >&2
        rm -rf "$REPO"
        return 1
    fi

    # 3. RAG decision — non-UE injected → tripwire into CLAUDE.md
    output="$(env SETUP_RAG_IS_UE_REPO="0" bash "$RAG" --root "$REPO" 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: RAG exited %d (expected 0)\n    output: %s\n' "$status" "$output" >&2
        rm -rf "$REPO"
        return 1
    fi
    if ! grep -qF 'un-indexed' "${REPO}/CLAUDE.md"; then
        printf '    FAIL: "un-indexed" not found in CLAUDE.md after RAG\n' >&2
        rm -rf "$REPO"
        return 1
    fi

    # 4. fnm pin-resolution with fnm ABSENT → fail-loud exit 1.
    #    The whole point: this exit is ISOLATED (subprocess), not fatal to the sequence.
    output="$(env COORDINATOR_FNM_ABSENT="1" bash "$FNM" "$REPO" 2>&1)"; status=$?
    if [ "$status" -ne 1 ]; then
        printf '    FAIL: FNM exited %d (expected 1 for absent fnm)\n    output: %s\n' "$status" "$output" >&2
        rm -rf "$REPO"
        return 1
    fi
    if [[ "$output" != *"fnm not installed"* ]]; then
        printf '    FAIL: FNM output does not contain "fnm not installed"\n    output: %s\n' "$output" >&2
        rm -rf "$REPO"
        return 1
    fi

    # Regression assertion: we REACHED here past the fail-loud exit, and every seed
    # the earlier helpers wrote is intact — proving subprocess isolation. A `source`-based
    # Phase 3j would have killed the shell at step 4 (or earlier on any fail-loud branch).
    if ! grep -qE '^fast_test_cmd:' "${REPO}/coordinator.local.md"; then
        printf '    FAIL: fast_test_cmd seed not intact after FNM fail-loud (isolation broken)\n' >&2
        rm -rf "$REPO"
        return 1
    fi
    # Review: code-reviewer — detector writes BOTH keys; assert full_test_cmd survives isolation too
    if ! grep -qE '^full_test_cmd:' "${REPO}/coordinator.local.md"; then
        printf '    FAIL: full_test_cmd seed not intact after FNM fail-loud (isolation broken)\n' >&2
        rm -rf "$REPO"
        return 1
    fi
    if [ ! -f "${REPO}/state/health-ledger.md" ]; then
        printf '    FAIL: health-ledger.md seed not intact after FNM fail-loud (isolation broken)\n' >&2
        rm -rf "$REPO"
        return 1
    fi
    if ! grep -qF 'un-indexed' "${REPO}/CLAUDE.md"; then
        printf '    FAIL: CLAUDE.md un-indexed seed not intact after FNM fail-loud (isolation broken)\n' >&2
        rm -rf "$REPO"
        return 1
    fi

    rm -rf "$REPO"
    return 0
}

# ---------------------------------------------------------------------------
# Test 2: SKILL.md Phase 3j invokes the helpers via 'bash', never 'source'
# ---------------------------------------------------------------------------

test_skill_md_no_source_contract() {
    local skill="${SCRIPT_DIR}/../skills/repo-setup/SKILL.md"

    # No `source ...setup-*.sh` in the Phase 3j seed block — sourcing a fail-loud helper
    # terminates the repo-setup shell. This guards the contract at the SKILL surface.
    # Review: code-reviewer — broadened to catch unquoted/single-quoted source AND the `.`
    # builtin alias; original double-quote-only regex silently misses both forms.
    # Test passes when grep finds NO matches (exit non-zero from grep = no source lines found).
    if grep -nE '(^|[[:space:];&|])(source|\.)[[:space:]]+[^#]*setup-(detect-test-cmd|seed-health-ledger|rag-decision|fnm-pin)\.sh' "$skill" >/dev/null 2>&1; then
        printf '    FAIL: SKILL.md contains source invocation of a Phase 3j helper (subprocess contract violated)\n' >&2
        return 1
    fi

    printf '    No source invocations of Phase 3j helpers found in SKILL.md — contract intact\n'
    return 0
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

run_test "Phase 3j: four helpers run as subprocesses; fail-loud in one is isolated; seeds survive" \
    test_phase3j_subprocess_isolation

run_test "SKILL.md Phase 3j invokes the helpers via 'bash', never 'source'" \
    test_skill_md_no_source_contract

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
