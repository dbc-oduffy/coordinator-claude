#!/usr/bin/env bash
# plugins/coordinator/tests/test_co_find_python.sh
#
# Focused tests for _co_find_python() in scripts/lib/manifest_reader.sh.
#
# Verifies the functional-probe behaviour introduced to catch the Windows 11
# WindowsApps Store stub (python3.exe App Execution alias) which passes
# "command -v python3" but exits 49 when executed -- an existence-only probe
# would return a broken name, failing every subsequent "$PYTHON -c" call.
#
# Test cases:
#   1. Working interpreter is selected and function returns exit 0.
#   2. Broken stub (exits 49, simulates WindowsApps Store alias) is rejected
#      in favour of a working interpreter later in the candidate list.
#   3. When no functional interpreter exists, function returns non-zero and
#      emits the WindowsApps remediation message to stderr.
#
# Spec backlink: docs/plans/2026-06-22-persist-machine-slug-registry.md (bug fix)
# Bug: Windows 11 WindowsApps python3.exe stub -- command -v passes, exec exits 49.
#
# Cross-platform portability notes (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4 (test runner); scripts under test also work on bash 3.2.
#   - GNU-isms avoided: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate a real bash >= 4 to use for subshells.  Needed because this test
# may be run via "bash <path>" from a shell (zsh, sh) that restricts PATH.
# Probe known install locations before falling back to PATH lookup.
# ---------------------------------------------------------------------------
_BASH4=""
for _b in "$BASH" /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash bash; do
    [[ -z "$_b" ]] && continue
    if "$_b" -c '[[ "${BASH_VERSINFO[0]}" -ge 4 ]]' 2>/dev/null; then
        _BASH4="$_b"
        break
    fi
done

if [[ -z "$_BASH4" ]]; then
    echo "ERROR: bash >= 4 required but not found." >&2
    echo "Remediation: brew install bash" >&2
    exit 1
fi

# Self-check: if WE are older than 4, re-exec under _BASH4.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and source the library under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_UNDER_TEST="${COORDINATOR_ROOT}/scripts/lib/manifest_reader.sh"

if [[ ! -f "$LIB_UNDER_TEST" ]]; then
    echo "ERROR: library not found: $LIB_UNDER_TEST" >&2
    exit 1
fi

# Source the library -- this defines _co_find_python and helpers.
# shellcheck source=../scripts/lib/manifest_reader.sh
source "$LIB_UNDER_TEST"

# ---------------------------------------------------------------------------
# Test counters and helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
ERRORS=()

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

# ---------------------------------------------------------------------------
# Scratch directory for fake interpreter stubs.  Cleaned up on exit.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
trap 'rm -rf "$_SCRATCH_DIR"' EXIT

# Helper: create a fake interpreter script in a dir that exits with a given code.
# Usage: _make_stub <dir> <name> <exit-code>
_make_stub() {
    local _dir="$1"
    local _name="$2"
    local _exit_code="$3"
    printf '#!/bin/sh\nexit %s\n' "$_exit_code" > "$_dir/$_name"
    chmod +x "$_dir/$_name"
}

# Helper: find a real Python >= 3.11 on the host.
# Echoes the path; returns 1 if none found.
_find_real_python() {
    local _cand _real
    for _cand in python3 python; do
        if command -v "$_cand" >/dev/null 2>&1; then
            _real="$(command -v "$_cand")"
            if "$_real" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)' >/dev/null 2>&1; then
                echo "$_real"
                return 0
            fi
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Test 1: A working interpreter is selected; function returns exit 0.
#
# Strategy: create scratch with a real-Python wrapper named python3.
# _co_find_python should select it, echo "python3", and return 0.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: working interpreter is selected ==="

_t1_real="$(_find_real_python 2>/dev/null)" || _t1_real=""

if [[ -z "$_t1_real" ]]; then
    echo "SKIP: no real Python >= 3.11 found on host -- cannot run test 1" >&2
    _pass "test 1 skipped (no host Python >= 3.11)"
else
    _t1_dir="$_SCRATCH_DIR/t1"
    mkdir -p "$_t1_dir"
    # Create a wrapper that delegates to the real host Python.
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$_t1_real" > "$_t1_dir/python3"
    chmod +x "$_t1_dir/python3"

    _t1_stderr="$_SCRATCH_DIR/t1.stderr"
    _t1_result=""
    _t1_exit=0

    _t1_result="$(PATH="$_t1_dir" "$_BASH4" -c '
        source "$1"
        _co_find_python
    ' _ "$LIB_UNDER_TEST" 2>"$_t1_stderr")" || _t1_exit=$?

    if [[ $_t1_exit -ne 0 ]]; then
        _fail "test 1: _co_find_python returned non-zero (exit $_t1_exit); stderr: $(cat "$_t1_stderr")"
    elif [[ -z "$_t1_result" ]]; then
        _fail "test 1: _co_find_python echoed empty string"
    else
        _pass "working interpreter '$_t1_result' selected and returned exit 0"
    fi
fi

# ---------------------------------------------------------------------------
# Test 2: Broken stub (exit 49) rejected; real interpreter selected instead.
#
# Strategy:
#   - python3 stub in a first-priority dir (exits 49).
#   - Real python wrapper named "python" in a second-priority dir.
#   - _co_find_python must skip python3 and select python.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: broken stub (exit 49) is rejected; real interpreter selected ==="

_t2_real="$(_find_real_python 2>/dev/null)" || _t2_real=""

if [[ -z "$_t2_real" ]]; then
    echo "SKIP: no real Python >= 3.11 found on host -- cannot run test 2" >&2
    _pass "test 2 skipped (no host Python >= 3.11)"
else
    _t2_stub_dir="$_SCRATCH_DIR/t2_stub"
    _t2_real_dir="$_SCRATCH_DIR/t2_real"
    mkdir -p "$_t2_stub_dir" "$_t2_real_dir"

    # Broken stub for python3 (mimics Windows Store alias exiting 49).
    _make_stub "$_t2_stub_dir" "python3" "49"

    # Real working interpreter as python.
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$_t2_real" > "$_t2_real_dir/python"
    chmod +x "$_t2_real_dir/python"

    _t2_stderr="$_SCRATCH_DIR/t2.stderr"
    _t2_result=""
    _t2_exit=0

    _t2_result="$(PATH="$_t2_stub_dir:$_t2_real_dir" "$_BASH4" -c '
        source "$1"
        _co_find_python
    ' _ "$LIB_UNDER_TEST" 2>"$_t2_stderr")" || _t2_exit=$?

    if [[ $_t2_exit -ne 0 ]]; then
        _fail "test 2: _co_find_python returned non-zero (exit $_t2_exit); stderr: $(cat "$_t2_stderr")"
    elif [[ "$_t2_result" != "python" ]]; then
        _fail "test 2: expected 'python' but got '$_t2_result'"
    else
        _pass "broken stub (exit 49) rejected; real interpreter 'python' selected"
    fi
fi

# ---------------------------------------------------------------------------
# Test 3: No functional interpreter exists; non-zero exit with remediation.
#
# Strategy:
#   - Populate PATH with only broken stubs (both exit 49).
#   - _co_find_python must return non-zero.
#   - stderr must contain the WindowsApps remediation mention.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: no functional interpreter -> non-zero exit with remediation ==="

_t3_dir="$_SCRATCH_DIR/t3_bad"
mkdir -p "$_t3_dir"
_make_stub "$_t3_dir" "python3" "49"
_make_stub "$_t3_dir" "python" "49"

_t3_stderr="$_SCRATCH_DIR/t3.stderr"
_t3_result=""
_t3_exit=0

_t3_result="$(PATH="$_t3_dir" "$_BASH4" -c '
    source "$1"
    _co_find_python
' _ "$LIB_UNDER_TEST" 2>"$_t3_stderr")" || _t3_exit=$?

if [[ $_t3_exit -eq 0 ]]; then
    _fail "test 3: _co_find_python returned 0 (expected non-zero)"
elif ! grep -q "WindowsApps" "$_t3_stderr"; then
    _fail "test 3: stderr does not mention 'WindowsApps' remediation. stderr: $(cat "$_t3_stderr")"
else
    _pass "no functional interpreter: non-zero exit and WindowsApps remediation in stderr"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _err in "${ERRORS[@]}"; do
        echo "  ${_err}"
    done
fi

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
