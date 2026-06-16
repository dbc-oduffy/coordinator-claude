#!/usr/bin/env bash
# plugins/coordinator/tests/test_dag_root_walker.sh
#
# Verifies the DAG-root chain-walker termination behaviour of scripts/setup.sh.
#
# Coordinator-claude is the DAG root (chain step 5 of 5, direct_deps: []).
# When the chain-walker reaches coord, it must:
#   - Read the manifest and observe empty direct_deps
#   - Emit "chain walk complete — coordinator-claude is DAG root" to stdout
#   - Exit 0
#
# This test is NEW (no DR Phase B analogue — DR has deps and does not terminate
# at DAG root; coord IS the DAG root, so the walker terminates here by design).
#
# Tests are intentionally RED until Wave 2 lands scripts/setup.sh.
# That is the contract — see plan §7 C5: 'Tests will be RED on dispatch return.'
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md
#                §6 AC8 + §7 C5
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#                § Chain-walker visited-set protocol
#
# Cross-platform portability notes (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4; stock macOS /bin/bash is 3.2 (unsupported target).
#   - GNU-isms avoided: no grep -P, no date -d, no sed -i.
#   - Runs on Git-Bash (Windows) as well as POSIX per AC8 requirement.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (DR-148)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required. Stock macOS /bin/bash is 3.2 (unsupported)." >&2
    echo "Remediation: brew install bash && ensure /usr/local/bin/bash appears first in PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SETUP_SH="${COORDINATOR_ROOT}/scripts/setup.sh"

# The exact terminal banner string the chain-walker must emit when it reaches
# a DAG root (empty direct_deps). C2 must produce this exact string in stdout.
DAG_ROOT_NEEDLE="chain walk complete — coordinator-claude is DAG root"

PASS=0
FAIL=0
ERRORS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

# ---------------------------------------------------------------------------
# Pre-flight: scripts/setup.sh must exist
# ---------------------------------------------------------------------------
echo "=== Pre-flight: setup.sh existence ==="
if [[ ! -f "${SETUP_SH}" ]]; then
    _fail "setup.sh does not exist at ${SETUP_SH}. C2 must land before this test can be green. Tests are intentionally RED until Wave 2."
    echo ""
    echo "=== Summary ==="
    echo "PASS: ${PASS}  FAIL: ${FAIL}"
    exit 1
fi
_pass "setup.sh exists at ${SETUP_SH}"

# ---------------------------------------------------------------------------
# Test 1: --check flag exits 0
#
# The --check flag is the read-only extension (contract § Read-only flag carve-out).
# Under --check, setup.sh must exit 0 (no writes to install-status, manifest, or
# any persistent state). This is a precondition for the DAG-root banner test.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: --check flag exits 0 ==="

# Review: code-reviewer F1+F14 — pull cd OUT of subshell so PASS/FAIL counter
# mutations in _pass/_fail are visible to the parent shell.
# Review: code-reviewer F4 — single capture reused across Tests 1/2/3.
_wd=$(pwd)
cd "${COORDINATOR_ROOT}"
output=$(bash scripts/setup.sh --check 2>/dev/null) && exit_code=0 || exit_code=$?
cd "${_wd}"

if [[ "${exit_code}" -eq 0 ]]; then
    _pass "--check flag: setup.sh --check exited 0"
else
    _fail "--check flag: setup.sh --check exited ${exit_code} (expected 0). Under --check, no install-status writes should block exit."
fi

# ---------------------------------------------------------------------------
# Test 2: stdout contains the DAG-root terminal banner
#
# When coord's setup.sh reads the manifest and observes empty direct_deps,
# it must emit the DAG-root terminal banner to stdout. This is the functional
# proof that the chain-walker terminates correctly at the DAG root.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: stdout contains DAG-root terminal banner ==="

# Review: code-reviewer F1+F14 — no subshell; reuses $output/$exit_code from Test 1 single capture (F4).
if echo "${output}" | grep -qF "${DAG_ROOT_NEEDLE}"; then
    _pass "DAG-root banner: stdout contains '${DAG_ROOT_NEEDLE}'"
else
    _fail "DAG-root banner: stdout did not contain '${DAG_ROOT_NEEDLE}'. Actual stdout: ${output}"
fi

# ---------------------------------------------------------------------------
# Test 3: stdout contains the "chain step 5 of 5" setup banner
#
# The setup script should emit its identity banner before the DAG-root
# terminal. Both must be present. This cross-checks with AC3 / test_repo_root_resolution.sh.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: stdout contains chain step banner ==="

CHAIN_STEP_NEEDLE="chain step 5 of 5"

# Review: code-reviewer F1+F14 — no subshell; reuses $output/$exit_code from Test 1 single capture (F4).
if echo "${output}" | grep -qF "${CHAIN_STEP_NEEDLE}"; then
    _pass "Chain step banner: stdout contains '${CHAIN_STEP_NEEDLE}'"
else
    _fail "Chain step banner: stdout did not contain '${CHAIN_STEP_NEEDLE}'. Actual stdout: ${output}"
fi

# ---------------------------------------------------------------------------
# Test 4: --check produces no side effects (no state writes)
#
# The --check flag is contract-required read-only. Verify that invoking
# setup.sh --check does NOT create any state files under ~/.claude/coordinator-claude/.
# The visited-set file at ~/.claude/coordinator-claude/chain-walk-<session-id>.json
# is session-scoped scratch — it must NOT persist after --check.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 4: --check produces no state files ==="

STATE_DIR="${HOME}/.claude/coordinator-claude"
# Capture any pre-existing chain-walk files before running --check
pre_files=()
if [[ -d "${STATE_DIR}" ]]; then
    while IFS= read -r -d '' f; do
        pre_files+=("$f")
    done < <(find "${STATE_DIR}" -name "chain-walk-*.json" -print0 2>/dev/null || true)
fi

(
    cd "${COORDINATOR_ROOT}"
    bash scripts/setup.sh --check >/dev/null 2>/dev/null || true
)

# Check for new chain-walk files
post_files=()
if [[ -d "${STATE_DIR}" ]]; then
    while IFS= read -r -d '' f; do
        post_files+=("$f")
    done < <(find "${STATE_DIR}" -name "chain-walk-*.json" -print0 2>/dev/null || true)
fi

new_files=()
for f in "${post_files[@]+"${post_files[@]}"}"; do
    found=0
    for pre in "${pre_files[@]+"${pre_files[@]}"}"; do
        if [[ "$f" == "$pre" ]]; then
            found=1
            break
        fi
    done
    if [[ "$found" -eq 0 ]]; then
        new_files+=("$f")
    fi
done

if [[ "${#new_files[@]}" -eq 0 ]]; then
    _pass "No-side-effects: --check produced no new chain-walk state files"
else
    # Review: code-reviewer F2 — concatenate into single $1; _fail only reads $1.
    _fail "No-side-effects: --check created unexpected state files: ${new_files[*]}. The --check flag must be read-only (contract § Read-only flag carve-out)."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
    echo "" >&2
    echo "Failed assertions:" >&2
    for err in "${ERRORS[@]}"; do
        echo "  ${err}" >&2
    done
    exit 1
fi
exit 0
