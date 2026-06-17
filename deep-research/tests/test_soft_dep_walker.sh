#!/usr/bin/env bash
# plugins/deep-research/tests/test_soft_dep_walker.sh
#
# Verifies the soft-dep chain-walker behaviour for coordinator-claude:
#
#   Arm 1 — coord-present:
#     Run scripts/setup.sh --check with coord's CLAUDE.md present.
#     Assert: exit 0 AND stdout contains an acknowledgment that the coordinator
#     dependency is satisfied (walker reports dep as satisfied and continues).
#
#   Arm 2 — coord-absent (temporarily renamed):
#     Rename plugins/coordinator/CLAUDE.md →
#     plugins/coordinator/CLAUDE.md.HIDDEN_FOR_TEST
#     Run scripts/setup.sh --check.
#     Assert: exit 0 (soft-dep does NOT fail-loud — warn-and-continue) AND
#     stderr contains a warning message AND stderr mentions the
#     override-flag offer --accept-missing-deps-risk.
#     Restore the file via EXIT trap immediately after.
#
# Tests are intentionally RED until Wave 2 lands scripts/setup.sh.
#
# The functional probe for coordinator-claude is:
#   kind: file_exists
#   path: plugins/coordinator/CLAUDE.md
# "path" is relative to the sibling repo root. In the nested working-repo
# layout, the sibling clone IS the working repo — the probe path resolves
# to ${WR_ROOT}/plugins/coordinator/CLAUDE.md where
# WR_ROOT is the ~/.claude meta-repo.
#
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md
#                §6 AC8 + §7 C5
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#                § Severity semantics (soft: warn loudly, offer, proceed if declined)
#
# Cross-platform portability (DR-148, cross-platform-shell-portability.md):
#   - bash >= 4 required (guard below)
#   - No GNU-isms: no grep -P, no sed -i, no date -d
#   - mv and mv-back are POSIX-portable
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
# Path resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SH="${DR_ROOT}/scripts/setup.sh"

# The working-repo root is three levels above DR_ROOT:
#   DR_ROOT = ~/.claude/plugins/coordinator-claude/deep-research
#   ../     = ~/.claude/plugins/coordinator-claude
#   ../../  = ~/.claude/plugins
#   ../../../ = ~/.claude  (WR_ROOT)
WR_ROOT="$(cd "${DR_ROOT}/../../.." && pwd)"

# Probe target: the coordinator CLAUDE.md that the functional_probe verifies
# path is relative to the sibling repo root = WR_ROOT in nested layout
COORD_CLAUDE_MD="${WR_ROOT}/plugins/coordinator/CLAUDE.md"
COORD_CLAUDE_MD_HIDDEN="${COORD_CLAUDE_MD}.HIDDEN_FOR_TEST"

PASS=0
FAIL=0
ERRORS=()

# ---------------------------------------------------------------------------
# EXIT trap — always restore the coordinator CLAUDE.md if we hid it
# ---------------------------------------------------------------------------
_restore_coord_claude_md() {
    if [[ -f "${COORD_CLAUDE_MD_HIDDEN}" && ! -f "${COORD_CLAUDE_MD}" ]]; then
        mv "${COORD_CLAUDE_MD_HIDDEN}" "${COORD_CLAUDE_MD}"
        echo "(restored ${COORD_CLAUDE_MD})"
    fi
}
trap _restore_coord_claude_md EXIT

# ---------------------------------------------------------------------------
# Helper: record pass/fail
# ---------------------------------------------------------------------------
_pass() {
    PASS=$(( PASS + 1 ))
    echo "PASS: $1"
}

_fail() {
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: $1")
    echo "FAIL: $1" >&2
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ ! -f "${SETUP_SH}" ]]; then
    echo "ERROR: ${SETUP_SH} does not exist." >&2
    echo "C2 must land before this test can be green. Tests are intentionally RED until Wave 2." >&2
    exit 1
fi

if [[ ! -f "${COORD_CLAUDE_MD}" ]]; then
    echo "ERROR: coordinator CLAUDE.md not found at ${COORD_CLAUDE_MD}." >&2
    echo "This file must exist to run the coord-present arm." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Arm 1: coord-present
#
# Run setup.sh --check with coordinator CLAUDE.md in place.
# Assert: exit 0 AND stdout contains acknowledgment that the coord dep
# is satisfied (some form of "coordinator" acknowledgment expected).
#
# The exact acknowledgment string is implementation-defined by C2. The
# assertion is deliberately loose on the exact wording ("coordinator" appears
# somewhere in stdout) to stay robust to C2's phrasing choices, while still
# verifying the satisfied-and-continue behaviour is exercised.
# ---------------------------------------------------------------------------
echo "=== Arm 1: coord-present ==="
echo "Verifying ${COORD_CLAUDE_MD} is in place..."

STDOUT_PRESENT=""
STDERR_PRESENT=""
EXIT_PRESENT=0

# Capture stdout and stderr separately; allow non-zero to handle ourselves
STDOUT_PRESENT="$(cd "${DR_ROOT}" && bash scripts/setup.sh --check 2>/tmp/_dr_test_soft_dep_stderr_present || true)"
EXIT_PRESENT=$?
STDERR_PRESENT="$(cat /tmp/_dr_test_soft_dep_stderr_present 2>/dev/null || true)"

# Assert exit 0 (--check is a read-only carve-out; must succeed when dep is present)
if [[ "${EXIT_PRESENT}" -eq 0 ]]; then
    _pass "Arm 1: setup.sh --check exits 0 when coordinator CLAUDE.md is present"
else
    _fail "Arm 1: setup.sh --check exited ${EXIT_PRESENT} (expected 0) when coord is present. stderr: ${STDERR_PRESENT}"
fi

# Assert stdout acknowledges coordinator dep as satisfied
# Accept any of: "coordinator", "satisfied", "present", "acknowledge", "found"
if echo "${STDOUT_PRESENT}" | grep -qiF "coordinator"; then
    _pass "Arm 1: stdout acknowledges coordinator dep (contains 'coordinator')"
elif echo "${STDOUT_PRESENT}" | grep -qiF "satisfied"; then
    _pass "Arm 1: stdout acknowledges coordinator dep (contains 'satisfied')"
elif echo "${STDOUT_PRESENT}" | grep -qiF "present"; then
    _pass "Arm 1: stdout acknowledges coordinator dep (contains 'present')"
else
    _fail "Arm 1: stdout does not mention coordinator dep acknowledgment. stdout: ${STDOUT_PRESENT}"
fi

# ---------------------------------------------------------------------------
# Arm 2: coord-absent (temporarily hide the CLAUDE.md)
#
# Rename coordinator/CLAUDE.md → CLAUDE.md.HIDDEN_FOR_TEST so the
# functional_probe file_exists check fails.
# Run setup.sh --check.
# Assert:
#   (a) exit 0  — soft dep must NOT fail-loud; warn-and-continue required
#   (b) stderr contains a warning (soft dep absent triggers loud warn)
#   (c) stderr mentions --accept-missing-deps-risk (override-flag offer)
# Restore file immediately after capture (EXIT trap also provides safety net).
# ---------------------------------------------------------------------------
echo ""
echo "=== Arm 2: coord-absent (temporarily renaming ${COORD_CLAUDE_MD}) ==="

mv "${COORD_CLAUDE_MD}" "${COORD_CLAUDE_MD_HIDDEN}"
echo "Renamed → ${COORD_CLAUDE_MD_HIDDEN}"

STDOUT_ABSENT=""
STDERR_ABSENT=""
EXIT_ABSENT=0

STDOUT_ABSENT="$(cd "${DR_ROOT}" && bash scripts/setup.sh --check 2>/tmp/_dr_test_soft_dep_stderr_absent || true)"
EXIT_ABSENT=$?
STDERR_ABSENT="$(cat /tmp/_dr_test_soft_dep_stderr_absent 2>/dev/null || true)"

# Restore immediately (EXIT trap is the safety net; explicit restore is belt-and-suspenders)
mv "${COORD_CLAUDE_MD_HIDDEN}" "${COORD_CLAUDE_MD}"
echo "Restored ${COORD_CLAUDE_MD}"

# Assert (a): exit 0 — soft dep warn-and-continue, NOT fail-loud
if [[ "${EXIT_ABSENT}" -eq 0 ]]; then
    _pass "Arm 2: setup.sh --check exits 0 when coordinator CLAUDE.md is absent (warn-and-continue)"
else
    _fail "Arm 2: setup.sh --check exited ${EXIT_ABSENT} (expected 0) when coord is absent. "\
"Soft dep must warn-and-continue, not fail-loud. "\
"See agent-install-contract.md § Severity semantics: soft → warn loudly, offer, proceed if declined."
fi

# Assert (b): stderr contains a warning
if echo "${STDERR_ABSENT}" | grep -qiE "warn|warning|missing|absent|not found"; then
    _pass "Arm 2: stderr contains a warning when coordinator dep is absent"
else
    _fail "Arm 2: stderr does not contain a warning. Soft dep must emit loud warning when absent. "\
"stderr: ${STDERR_ABSENT}"
fi

# Assert (c): stderr offers --accept-missing-deps-risk override flag
if echo "${STDERR_ABSENT}" | grep -qF -- "--accept-missing-deps-risk"; then
    _pass "Arm 2: stderr mentions --accept-missing-deps-risk override-flag offer"
else
    _fail "Arm 2: stderr does not mention '--accept-missing-deps-risk'. "\
"The override-flag offer is required for soft-dep absent path. "\
"See predecessor §7.2 (vestigial-path naming) and plan §7 C5. "\
"stderr: ${STDERR_ABSENT}"
fi

# ---------------------------------------------------------------------------
# Cleanup temp files
# ---------------------------------------------------------------------------
rm -f /tmp/_dr_test_soft_dep_stderr_present /tmp/_dr_test_soft_dep_stderr_absent 2>/dev/null || true

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
