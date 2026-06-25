#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# plugins/coordinator/tests/test_repo_root_resolution.sh
#
# Verifies that scripts/setup.sh (and scripts/setup.ps1 when pwsh is available)
# resolve repo_root correctly in BOTH layouts:
#   1. Nested working-repo layout (scripts live under plugins/coordinator/)
#   2. Flat publish-repo layout (scripts live at repo root after publish.sh percolates)
#
# The test invokes setup.sh --check in each layout and asserts the expected
# "chain step 5 of 5" banner appears in stdout.
#
# Tests are intentionally RED until Wave 2 lands scripts/setup.{sh,ps1}.
# "chain step 5 of 5" is the exact banner string asserted; C2 must produce that output.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md
#                §6 AC7 + §7 C5 (pseudocode)
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#                § Read-only flag carve-out
#
# Adapted from plugins/deep-research/tests/test_repo_root_resolution.sh
# (DR Phase B C5 shape) with these coordinator-claude-specific adaptations:
#   - COORDINATOR_ROOT resolves from tests/<file> two levels up (not DR_ROOT)
#   - Banner string: "chain step 5 of 5" (coord is chain step 5 of 5, DAG root)
#   - Source plugin subtree: docs, scripts, skills (same as DR)
#
# Cross-platform portability notes (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4; stock macOS /bin/bash is 3.2 (unsupported target).
#   - GNU-isms avoided: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable (both macOS and Linux).
#   - cp -r is BSD-portable for recursive directory copy.
#   - Runs on Git-Bash (Windows) as well as POSIX per AC7 requirement.
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
# Locate this file and the coordinator plugin root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Nested-layout script path
WR_SETUP_SH="${COORDINATOR_ROOT}/scripts/setup.sh"

BANNER_NEEDLE="chain step 5 of 5"
PASS=0
FAIL=0
ERRORS=()

# ---------------------------------------------------------------------------
# Helper: fail with a message
# ---------------------------------------------------------------------------
_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

# ---------------------------------------------------------------------------
# Helper: assert a command's stdout contains the banner needle
# ---------------------------------------------------------------------------
_assert_banner() {
    local label="$1"
    shift
    local output err_output
    local _tmp_stderr
    _tmp_stderr="$(mktemp)"
    # Review: code-reviewer F5 — capture stderr to temp file; include on failure for diagnosis.
    # Run the command; capture stdout; allow non-zero exit so we can report it cleanly
    if output=$("$@" 2>"${_tmp_stderr}"); then
        if echo "${output}" | grep -qF "${BANNER_NEEDLE}"; then
            PASS=$(( PASS + 1 ))
            echo "PASS: ${label}"
        else
            err_output="$(cat "${_tmp_stderr}" 2>/dev/null || true)"
            _fail "${label}: stdout did not contain '${BANNER_NEEDLE}'. Output: ${output}${err_output:+ | stderr: ${err_output}}"
        fi
    else
        local exit_code=$?
        err_output="$(cat "${_tmp_stderr}" 2>/dev/null || true)"
        _fail "${label}: command exited ${exit_code}. (setup.sh may not exist yet — tests are RED until Wave 2)${err_output:+ | stderr: ${err_output}}"
    fi
    rm -f "${_tmp_stderr}"
}

# ---------------------------------------------------------------------------
# Test 1: Nested working-repo layout
#
# Invoke scripts/setup.sh --check from the coordinator plugin root.
# The --check flag is the read-only extension declared in C2; it must:
#   - exit 0
#   - emit the "chain step 5 of 5" banner to stdout
# ---------------------------------------------------------------------------
echo "=== Test 1: Nested working-repo layout ==="
if [[ ! -f "${WR_SETUP_SH}" ]]; then
    _fail "Nested layout: ${WR_SETUP_SH} does not exist. C2 must land first."
else
    # Review: code-reviewer F1+F14 — pull cd OUT of subshell so PASS/FAIL counter
    # mutations in _assert_banner are visible to the parent shell.
    _wd=$(pwd)
    cd "${COORDINATOR_ROOT}"
    _assert_banner "nested-layout bash scripts/setup.sh --check" \
        "${BASH}" scripts/setup.sh --check
    cd "${_wd}"
fi

# ---------------------------------------------------------------------------
# Test 2: Flat publish-repo layout simulation
#
# Create a temp directory and copy the docs/, scripts/, and skills/ subtrees
# into it, simulating the flat layout that publish.sh produces in the
# publish repo (X:\coordinator-claude\).
#
# In the flat layout, setup.sh sits at <flat-root>/scripts/setup.sh and
# the docs/install/AGENT.md lives at <flat-root>/docs/install/AGENT.md —
# no plugins/coordinator/ prefix.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: Flat publish-repo layout simulation ==="

TMP_ROOT=""
cleanup() {
    if [[ -n "${TMP_ROOT}" && -d "${TMP_ROOT}" ]]; then
        rm -rf "${TMP_ROOT}"
    fi
}
trap cleanup EXIT

TMP_ROOT="$(mktemp -d)"
FLAT_LAYOUT="${TMP_ROOT}/flat-layout"
mkdir -p "${FLAT_LAYOUT}"

# Copy the three subtrees that publish.sh percolates — docs, scripts, skills
# Only copy if they exist (they won't until C1–C4 land; we detect and fail gracefully)
COPY_FAILED=0
for subtree in docs scripts skills; do
    if [[ -d "${COORDINATOR_ROOT}/${subtree}" ]]; then
        cp -r "${COORDINATOR_ROOT}/${subtree}" "${FLAT_LAYOUT}/${subtree}"
    else
        _fail "Flat layout setup: ${COORDINATOR_ROOT}/${subtree} does not exist. C1-C4 must land first."
        COPY_FAILED=1
    fi
done

if [[ "${COPY_FAILED}" -eq 0 ]]; then
    # Review: code-reviewer F1+F14 — pull cd OUT of subshell so PASS/FAIL counter
    # mutations in _assert_banner are visible to the parent shell.
    _wd=$(pwd)
    cd "${FLAT_LAYOUT}"
    _assert_banner "flat-layout bash scripts/setup.sh --check" \
        "${BASH}" scripts/setup.sh --check
    cd "${_wd}"
fi

# ---------------------------------------------------------------------------
# Test 3: PowerShell mirror (pwsh conditional — AC7 requirement)
#
# If pwsh is available on the test host, mirror the two layout tests for
# setup.ps1 with the -Check flag. This satisfies the sh+ps1 mirror pair
# constraint from plan §7 C2.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: PowerShell mirror (conditional on pwsh availability) ==="

WR_SETUP_PS1="${COORDINATOR_ROOT}/scripts/setup.ps1"

if command -v pwsh >/dev/null 2>&1; then
    echo "pwsh found — running ps1 mirror tests."

    # Nested layout
    if [[ ! -f "${WR_SETUP_PS1}" ]]; then
        _fail "Nested layout ps1: ${WR_SETUP_PS1} does not exist. C2 must land first."
    else
        # Review: code-reviewer F1+F14 — pull cd OUT of subshell so PASS/FAIL counter
        # mutations in _assert_banner are visible to the parent shell.
        _wd=$(pwd)
        cd "${COORDINATOR_ROOT}"
        _assert_banner "nested-layout pwsh scripts/setup.ps1 -Check" \
            pwsh -NonInteractive -File scripts/setup.ps1 -Check
        cd "${_wd}"
    fi

    # Flat layout (only if copy succeeded and ps1 was copied)
    if [[ "${COPY_FAILED}" -eq 0 && -f "${FLAT_LAYOUT}/scripts/setup.ps1" ]]; then
        # Review: code-reviewer F1+F14 — pull cd OUT of subshell so PASS/FAIL counter
        # mutations in _assert_banner are visible to the parent shell.
        _wd=$(pwd)
        cd "${FLAT_LAYOUT}"
        _assert_banner "flat-layout pwsh scripts/setup.ps1 -Check" \
            pwsh -NonInteractive -File scripts/setup.ps1 -Check
        cd "${_wd}"
    elif [[ "${COPY_FAILED}" -eq 0 ]]; then
        _fail "Flat layout ps1: scripts/setup.ps1 not found in flat copy. C2 must produce the ps1."
    fi
else
    echo "pwsh not found — skipping PowerShell mirror tests (AC7 note: run on Windows to cover ps1 leg)."
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
