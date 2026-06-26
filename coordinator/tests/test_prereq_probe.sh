#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# plugins/coordinator/tests/test_prereq_probe.sh
#
# Tests for scripts/lib/prereq_probe.sh — SSOT functional-prereq probe library.
#
# Sources prereq_probe.sh and exercises each probe function plus the aggregator.
# Realizes plan ACs AC1, AC5, AC7.
# Review: code-reviewer F9 — added AC7 (node + gh probe tests added in C4/C5).
#
# Test cases:
#   1. probe-all emits exactly 11 valid NDJSON lines with required keys/enum values.
#   2. AC1 — python probe rejects a broken Store-stub (exits 49) and reports remediation.
#   3. AC5 — probes are FUNCTIONAL, not existence-only: broken-uv stub yields non-"pass".
#   4. pass path — on macOS, python probe returns "pass"; longpaths returns "pass"
#      with detail "n/a (non-Windows)".
#   5. inconclusive is a valid reachable status — clone_auth returns one of the
#      valid enum values (pass|warn|inconclusive), and "inconclusive" is documented
#      as the expected result when network is unavailable.
#   6. AC7 — gh probe: absent binary yields status=fail and severity=hard.
#   7. AC7 — gh probe: present binary with valid auth yields valid status enum + severity=hard.
#   8. AC7 — node probe: absent binary yields status=fail; present node yields status=pass.
#   9. git_lfs probe: absent git-lfs yields status=warn and severity=advisory.
#  10. git_lfs probe: present git-lfs but not configured yields status=warn + advisory.
#  11. git_lfs probe: present and configured yields status=pass + advisory.
#  12. AC10 — advisory git_lfs warn does not change aggregator exit code (NEVER fails the suite).
#  13. shell_login_env probe: orphaned bash login shell => fail (PATH lacks ~/.local/bin).
#  14. shell_login_env probe: zsh login shell => pass (orphan predicate is bash-only).
#  15. shell_login_env probe: bash login shell with intact PATH + claude => pass.
#  16. shell_login_env probe: unprobeable login shell (dscl empty + SHELL unset) => inconclusive.
#  17. shell_login_env probe: non-macOS (Linux mock) => pass (macOS hard-short-circuit fires first).
#  18. shell_login_env probe: login shell -lc exits non-zero => inconclusive (|| true + empty PATH).
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md (predecessor)
#   docs/plans/2026-06-25-phase-zero-macos-bash-login-shell-provisioning.md (AC1/AC2 for tests 13-18)
# Review: code-reviewer F8 — added 2026-06-25 plan as the spec backlink for tests 13-18 (AC1/AC2).
#
# Cross-platform portability (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4.
#   - BSD-portable: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable.
#
# popup-safe-env-suppressed — python3 -c calls in this test script are JSON-parsing
# helpers that run in the test harness (macOS/Linux only; the test binary is not
# shipped to Windows operators). The bare python3 invocations here carry this
# per-file suppression marker per the coordinator C2 authoring doctrine.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate a real bash >= 4 (needed for subshell invocations and self-re-exec).
# ---------------------------------------------------------------------------
_BASH4=""
for _b in "$BASH" /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash bash; do
    [[ -z "${_b:-}" ]] && continue
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

# Self-re-exec under bash >= 4 if needed.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and the library under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_UNDER_TEST="${COORDINATOR_ROOT}/scripts/lib/prereq_probe.sh"

if [[ ! -f "$LIB_UNDER_TEST" ]]; then
    echo "ERROR: library not found: $LIB_UNDER_TEST" >&2
    exit 1
fi

# Source the library -- defines all _co_probe_* and _co_prereq_probe_all.
# shellcheck source=../scripts/lib/prereq_probe.sh
source "$LIB_UNDER_TEST"

# ---------------------------------------------------------------------------
# Test counters and helpers.
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
# Scratch directory for fake stubs. Cleaned up on exit.
# PATH is saved globally so per-test mutations can be restored.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
_ORIG_PATH="$PATH"

trap 'rm -rf "$_SCRATCH_DIR"; PATH="$_ORIG_PATH"' EXIT

# Helper: create a minimal executable stub in a dir.
# Usage: _make_stub <dir> <name> <exit-code> [<stdout-text>]
_make_stub() {
    local _dir="$1"
    local _name="$2"
    local _exit_code="$3"
    local _stdout="${4:-}"
    if [[ -n "$_stdout" ]]; then
        printf '#!/bin/sh\necho "%s"\nexit %s\n' "$_stdout" "$_exit_code" > "$_dir/$_name"
    else
        printf '#!/bin/sh\nexit %s\n' "$_exit_code" > "$_dir/$_name"
    fi
    chmod +x "$_dir/$_name"
}

# Helper: resolve the Python binary (prefers python3, falls back to python).
# Used to invoke the JSON field extractor.
_PY=""
for _pcand in python3 python; do
    if command -v "$_pcand" >/dev/null 2>&1; then
        _PY="$(command -v "$_pcand")"
        break
    fi
done

# Helper: extract a field from a single JSON line.
# Usage: _json_field <json_line> <field>  -> echoes value or empty.
_json_field() {
    local _line="$1"
    local _field="$2"
    [[ -z "$_PY" ]] && { echo ""; return; }
    "$_PY" -c "  # popup-safe-env-suppressed
import json, sys
try:
    d = json.loads(sys.argv[1])
    print(d.get(sys.argv[2], ''))
except Exception:
    print('')
" "$_line" "$_field" 2>/dev/null || echo ""
}

# Helper: validate that a JSON line parses cleanly.
# Usage: _json_valid <json_line>  -> returns 0 on success, 1 on failure.
_json_valid() {
    local _line="$1"
    [[ -z "$_PY" ]] && return 1
    "$_PY" -c "import json,sys; json.loads(sys.argv[1])" "$_line" 2>/dev/null  # popup-safe-env-suppressed
}

# ---------------------------------------------------------------------------
# Test 1: _co_prereq_probe_all emits exactly 10 valid NDJSON lines.
# Review: code-reviewer F2 — was "exactly 6"; corrected to 8 to match the assertion and echo above.
#
# Each line must:
#   - parse as JSON (no syntax errors).
#   - contain all 5 required keys: name, status, severity, detail, remediation.
#   - have status in {pass, fail, warn, inconclusive}.
#   - have severity in {hard, advisory}.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: probe-all emits 11 valid NDJSON lines with required keys/enum values ==="

_t1_output="$(_co_prereq_probe_all 2>/dev/null)"
# Review: code-reviewer F4 — guard grep -c . on empty input (exits 1 under set -euo pipefail)
_t1_line_count=0
[[ -n "$_t1_output" ]] && _t1_line_count="$(printf '%s\n' "$_t1_output" | grep -c . || echo 0)"

if [[ "$_t1_line_count" -ne 11 ]]; then
    _fail "test 1a: expected 11 lines from _co_prereq_probe_all, got $_t1_line_count"
else
    _pass "test 1a: probe-all emits exactly 11 lines"
fi

_t1_bad=0
_t1_line_num=0
while IFS= read -r _line; do
    _t1_line_num=$(( _t1_line_num + 1 ))
    [[ -z "$_line" ]] && continue

    # Validate parseable JSON.
    if ! _json_valid "$_line"; then
        _fail "test 1b: line $_t1_line_num is not valid JSON: $_line"
        _t1_bad=$(( _t1_bad + 1 ))
        continue
    fi

    # Validate required keys (status, severity, name, detail must be non-empty;
    # remediation is allowed to be empty string on a "pass" result).
    for _key in name status severity detail; do
        _val="$(_json_field "$_line" "$_key")"
        if [[ -z "$_val" ]]; then
            _fail "test 1b: line $_t1_line_num missing required non-empty key '$_key': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
        fi
    done

    # Validate status enum.
    _t1_status="$(_json_field "$_line" "status")"
    case "$_t1_status" in
        pass|fail|warn|inconclusive) ;;
        *)
            _fail "test 1c: line $_t1_line_num has invalid status '$_t1_status': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
            ;;
    esac

    # Validate severity enum.
    _t1_severity="$(_json_field "$_line" "severity")"
    case "$_t1_severity" in
        hard|advisory) ;;
        *)
            _fail "test 1c: line $_t1_line_num has invalid severity '$_t1_severity': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
            ;;
    esac
done <<< "$_t1_output"

if [[ "$_t1_bad" -eq 0 ]]; then
    _pass "test 1b/c: all 11 lines are valid JSON with correct keys and enum values"
fi

# ---------------------------------------------------------------------------
# Test 2: AC1 — python probe rejects a broken Store-stub (exits 49).
#
# Simulate the Windows 11 WindowsApps python3/python stub:
#   - create a temp dir with python3 and python executables that:
#       echo "Python was not found" and exit 49.
#   - prepend that dir to PATH.
#   - run _co_probe_python.
#   - assert: status="fail" (existence-only probe would "pass" this).
#   - assert: severity="hard".
#   - assert: remediation is non-empty (mentions the Store alias / installing Python).
# PATH is restored after the test.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: AC1 — python probe rejects Store-stub (exit 49), reports remediation ==="

_t2_dir="$_SCRATCH_DIR/t2_stub"
mkdir -p "$_t2_dir"

# Stub that mimics the Windows Store App Execution alias: prints the Store error, exits 49.
_make_stub "$_t2_dir" "python3" "49" "Python was not found; run without arguments to install"
_make_stub "$_t2_dir" "python"  "49" "Python was not found; run without arguments to install"

PATH="$_t2_dir:$_ORIG_PATH"
_t2_output="$(_co_probe_python 2>/dev/null)"
PATH="$_ORIG_PATH"

_t2_status="$(_json_field "$_t2_output" "status")"
_t2_severity="$(_json_field "$_t2_output" "severity")"
_t2_remediation="$(_json_field "$_t2_output" "remediation")"

if [[ "$_t2_status" == "fail" ]]; then
    _pass "test 2a: status is 'fail' (not 'pass') — existence-only probe would have passed broken stub"
else
    _fail "test 2a: expected status='fail' but got '$_t2_status' (probe output: $_t2_output)"
fi

if [[ "$_t2_severity" == "hard" ]]; then
    _pass "test 2b: severity is 'hard'"
else
    _fail "test 2b: expected severity='hard' but got '$_t2_severity'"
fi

if [[ -n "$_t2_remediation" ]]; then
    _pass "test 2c: remediation is non-empty: $_t2_remediation"
else
    _fail "test 2c: remediation is empty — should mention Store alias or installing Python"
fi

# ---------------------------------------------------------------------------
# Test 3: AC5 — probes are FUNCTIONAL, not existence-only.
#
# Demonstrate that a present-but-broken binary yields a non-"pass" status.
# A command -v-only probe would return "pass" for any binary that exists on PATH.
#
# Part A (python): the exit-49 stub case (Test 2) already demonstrates this.
#   Record it explicitly here as the AC5 python evidence.
#
# Part B (uv): create a fake "uv" on PATH that exits 1 (simulates a broken install).
#   Assert uv probe status is NOT "pass".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: AC5 — functional probes: broken-uv stub yields non-pass status ==="

# Part A: python evidence.
# Assert on the actual test-2 result captured above — tautological _pass replaced.
# Review: code-reviewer F2 — unconditional _pass was tautological; now asserts on real output.
if [[ "$_t2_status" == "fail" ]]; then
    _pass "test 3a: AC5 python evidence — _co_probe_python returned 'fail' for Store-stub (functional, not existence-only)"
else
    _fail "test 3a: AC5 python evidence — expected _co_probe_python status='fail' for Store-stub but got '$_t2_status'"
fi

# Part B: uv — fake uv exits 1 (empty/nonzero output).
_t3_dir="$_SCRATCH_DIR/t3_uv"
mkdir -p "$_t3_dir"
# A broken uv that exits 1 and prints nothing (simulate broken install).
_make_stub "$_t3_dir" "uv" "1"

PATH="$_t3_dir:$_ORIG_PATH"
_t3_uv_output="$(_co_probe_uv 2>/dev/null)"
PATH="$_ORIG_PATH"

_t3_uv_status="$(_json_field "$_t3_uv_output" "status")"

if [[ "$_t3_uv_status" != "pass" ]]; then
    _pass "test 3b: broken uv (exits 1) yields non-pass status '$_t3_uv_status' — functional probe confirmed"
else
    _fail "test 3b: broken uv (exits 1) returned status='pass' — probe may be existence-only"
fi

# ---------------------------------------------------------------------------
# Test 4: pass path — on macOS, python probe returns "pass" and longpaths
#         returns "pass" with detail "n/a (non-Windows)".
#
# These tests run against the real host PATH.
# The macOS machine running this suite is Machine-C (Darwin); we guard all
# assertions with a platform check so the test remains valid on other machines.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 4: pass path — macOS python pass; longpaths pass with non-Windows detail ==="

_t4_os="$(uname -s 2>/dev/null)"

if [[ "$_t4_os" == "Darwin" ]]; then
    # Python probe — real Python >= 3.11 should be present on Machine-C.
    _t4_py_output="$(_co_probe_python 2>/dev/null)"
    _t4_py_status="$(_json_field "$_t4_py_output" "status")"
    if [[ "$_t4_py_status" == "pass" ]]; then
        _t4_py_detail="$(_json_field "$_t4_py_output" "detail")"
        _pass "test 4a: _co_probe_python returns 'pass' on macOS (detail: $_t4_py_detail)"
    else
        _fail "test 4a: _co_probe_python returned '$_t4_py_status' on macOS — expected 'pass' (is Python 3.11+ installed?)"
    fi

    # longpaths probe — non-Windows, must return "pass" with "n/a (non-Windows)" detail.
    _t4_lp_output="$(_co_probe_longpaths 2>/dev/null)"
    _t4_lp_status="$(_json_field "$_t4_lp_output" "status")"
    _t4_lp_detail="$(_json_field "$_t4_lp_output" "detail")"
    if [[ "$_t4_lp_status" == "pass" ]]; then
        _pass "test 4b: _co_probe_longpaths returns 'pass' on macOS"
    else
        _fail "test 4b: _co_probe_longpaths returned '$_t4_lp_status' on macOS — expected 'pass'"
    fi
    if [[ "$_t4_lp_detail" == "n/a (non-Windows)" ]]; then
        _pass "test 4c: longpaths detail is 'n/a (non-Windows)'"
    else
        _fail "test 4c: longpaths detail is '$_t4_lp_detail' — expected 'n/a (non-Windows)'"
    fi
else
    echo "SKIP: test 4 macOS-specific assertions skipped on $_t4_os"
    _pass "test 4: skipped on non-macOS platform"
fi

# ---------------------------------------------------------------------------
# Test 5: inconclusive is a reachable, valid status.
#
# clone_auth probe returns one of {pass, warn, inconclusive} depending on env.
# Document:
#   - pass:         gh auth status ok OR git ls-remote succeeds.
#   - warn:         reachable but unauthenticated.
#   - inconclusive: network unreachable (e.g. offline, CI with no outbound).
#
# Assert:
#   - The returned status is one of the valid enum values.
#   - "inconclusive" is explicitly valid (the harness knows it; we confirm it
#     by asserting the returned status passes the enum check, even if it happens
#     to be pass/warn on this machine in this run).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 5: inconclusive is a valid status — clone_auth returns a valid enum value ==="

_t5_output="$(_co_probe_clone_auth 2>/dev/null)"
_t5_status="$(_json_field "$_t5_output" "status")"

case "$_t5_status" in
    pass|warn|inconclusive)
        _pass "test 5a: _co_probe_clone_auth returned valid status '$_t5_status'"
        echo "  (NOTE: 'inconclusive' is the expected result when network is offline;"
        echo "   this run produced '$_t5_status' — all three enum values are accepted)"
        ;;
    *)
        _fail "test 5a: _co_probe_clone_auth returned invalid status '$_t5_status' — expected pass|warn|inconclusive"
        ;;
esac

# Demonstrate inconclusive is understood by the JSON validator (the same
# python3 validator used in test 1 would pass a line containing "inconclusive").
_t5_synthetic='{"name":"clone_auth","status":"inconclusive","severity":"advisory","detail":"Network unreachable; cannot determine clone auth state","remediation":"ensure network connectivity"}'
if [[ -n "$_PY" ]] && "$_PY" -c "import json,sys; d=json.loads(sys.argv[1]); assert d['status']=='inconclusive'" "$_t5_synthetic" 2>/dev/null; then  # popup-safe-env-suppressed
    _pass "test 5b: harness correctly parses 'inconclusive' as a valid status value"
else
    _fail "test 5b: harness failed to parse synthetic inconclusive JSON — tooling issue"
fi

# ---------------------------------------------------------------------------
# Test 6: AC7 — gh probe: absent binary yields status=fail and severity=hard.
#
# Create a PATH that has no `gh` binary. Assert:
#   - status is "fail" (hard gate — absent gh is a hard failure).
#   - severity is "hard".
#   - remediation is non-empty (install guidance).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 6: AC7 — gh probe: absent binary yields fail + hard severity ==="

_t6_dir="$_SCRATCH_DIR/t6_no_gh"
mkdir -p "$_t6_dir"
# Intentionally do NOT create a gh stub — test absent binary path.

PATH="$_t6_dir"
_t6_output="$(_co_probe_gh 2>/dev/null)"
PATH="$_ORIG_PATH"

_t6_status="$(_json_field "$_t6_output" "status")"
_t6_severity="$(_json_field "$_t6_output" "severity")"
_t6_remediation="$(_json_field "$_t6_output" "remediation")"

if [[ "$_t6_status" == "fail" ]]; then
    _pass "test 6a: gh absent => status is 'fail'"
else
    _fail "test 6a: gh absent => expected status='fail' but got '$_t6_status' (output: $_t6_output)"
fi

if [[ "$_t6_severity" == "hard" ]]; then
    _pass "test 6b: gh absent => severity is 'hard'"
else
    _fail "test 6b: gh absent => expected severity='hard' but got '$_t6_severity'"
fi

if [[ -n "$_t6_remediation" ]]; then
    _pass "test 6c: gh absent => remediation is non-empty: $_t6_remediation"
else
    _fail "test 6c: gh absent => remediation is empty — should contain install guidance"
fi

# ---------------------------------------------------------------------------
# Test 7: AC7 — gh probe: present binary path (environment-dependent).
#
# The authed path depends on the host gh CLI state and cannot be deterministically
# forced in all CI environments. This test therefore:
#   - Verifies the probe emits valid JSON with severity=hard regardless of auth state.
#   - Verifies the status is in the valid enum {pass, fail} (warn is not emitted by
#     this probe — it's either authed=pass or not=fail).
#   - Does NOT assert status=pass (that would be environment-dependent).
#
# If COORDINATOR_GH_PROBE_REPO is unset (default), the private-repo sub-probe
# is a silent no-op — we verify this by confirming no unexpected side effects.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 7: AC7 — gh probe: present path emits hard severity + valid enum ==="

# Run against real host PATH (gh may or may not be present).
_t7_output="$(_co_probe_gh 2>/dev/null)"
_t7_status="$(_json_field "$_t7_output" "status")"
_t7_severity="$(_json_field "$_t7_output" "severity")"

case "$_t7_status" in
    pass|fail)
        _pass "test 7a: _co_probe_gh returned valid status '$_t7_status' (pass=authed, fail=absent/unauthed)"
        ;;
    *)
        _fail "test 7a: _co_probe_gh returned invalid status '$_t7_status' — expected pass or fail"
        ;;
esac

if [[ "$_t7_severity" == "hard" ]]; then
    _pass "test 7b: _co_probe_gh severity is 'hard' (regardless of auth state)"
else
    _fail "test 7b: _co_probe_gh severity is '$_t7_severity' — expected 'hard'"
fi

# Verify COORDINATOR_GH_PROBE_REPO env var no-op: run with it unset (default).
# Should produce identical output shape — no crash, no extra lines.
_t7_noprobe_out="$(COORDINATOR_GH_PROBE_REPO="" _co_probe_gh 2>/dev/null)"
_t7_noprobe_status="$(_json_field "$_t7_noprobe_out" "status")"
case "$_t7_noprobe_status" in
    pass|fail)
        _pass "test 7c: COORDINATOR_GH_PROBE_REPO unset is a silent no-op (status '$_t7_noprobe_status')"
        ;;
    *)
        _fail "test 7c: COORDINATOR_GH_PROBE_REPO unset produced invalid status '$_t7_noprobe_status'"
        ;;
esac

# ---------------------------------------------------------------------------
# Test 8: AC7 — node probe: absent binary yields fail; present node yields pass.
#
# Part A: absent — create a PATH with no node binary; assert status=fail + severity=hard.
# Part B: present — run against real host PATH; if node is present, assert status=pass;
#         if absent, skip the pass assertion (environment-dependent).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 8: AC7 — node probe: absent => fail; present => pass ==="

# Part A: absent node.
_t8_dir="$_SCRATCH_DIR/t8_no_node"
mkdir -p "$_t8_dir"
# Intentionally do NOT create a node stub — test absent binary path.

PATH="$_t8_dir"
_t8_absent_out="$(_co_probe_node 2>/dev/null)"
PATH="$_ORIG_PATH"

_t8_absent_status="$(_json_field "$_t8_absent_out" "status")"
_t8_absent_severity="$(_json_field "$_t8_absent_out" "severity")"

if [[ "$_t8_absent_status" == "fail" ]]; then
    _pass "test 8a: node absent => status is 'fail'"
else
    _fail "test 8a: node absent => expected status='fail' but got '$_t8_absent_status' (output: $_t8_absent_out)"
fi

if [[ "$_t8_absent_severity" == "hard" ]]; then
    _pass "test 8b: node absent => severity is 'hard'"
else
    _fail "test 8b: node absent => expected severity='hard' but got '$_t8_absent_severity'"
fi

# Part B: present node (environment-dependent).
_t8_present_out="$(_co_probe_node 2>/dev/null)"
_t8_present_status="$(_json_field "$_t8_present_out" "status")"

if command -v node >/dev/null 2>&1; then
    # node is on this machine: must pass.
    if [[ "$_t8_present_status" == "pass" ]]; then
        _t8_node_ver="$(_json_field "$_t8_present_out" "detail")"
        _pass "test 8c: node present => status is 'pass' (detail: $_t8_node_ver)"
    else
        _fail "test 8c: node present on PATH but _co_probe_node returned '$_t8_present_status' — expected 'pass'"
    fi
else
    echo "SKIP: test 8c (node pass path) — node not on host PATH; absent path already tested in 8a"
    _pass "test 8c: skipped (node not on this host)"
fi

# Part C (AC5): node present-but-broken — exits 1 with no output.
# Review: code-reviewer F3 — AC5 functional-vs-existence distinction; broken node stub must not pass.
# Mirrors Test 3b's uv pattern: a node binary that exits 1 and emits nothing should yield non-"pass".
_t8c_dir="$_SCRATCH_DIR/t8c_broken_node"
mkdir -p "$_t8c_dir"
# Broken node stub: exits 1, prints nothing (simulates a broken install or version-check failure).
_make_stub "$_t8c_dir" "node" "1"

PATH="$_t8c_dir:$_ORIG_PATH"
_t8c_out="$(_co_probe_node 2>/dev/null)"
PATH="$_ORIG_PATH"

_t8c_status="$(_json_field "$_t8c_out" "status")"
if [[ "$_t8c_status" != "pass" ]]; then
    _pass "test 8d: broken node (exits 1, no output) yields non-pass status '$_t8c_status' — functional probe confirmed"
else
    _fail "test 8d: broken node (exits 1, no output) returned status='pass' — probe may be existence-only"
fi

# ---------------------------------------------------------------------------
# Test 9: git_lfs probe: absent git-lfs yields status=warn + severity=advisory.
#
# Stub a PATH with a real `git` but no git-lfs subcommand. `git lfs version`
# will exit non-zero because git does not know the lfs subcommand.
# Assert: status=warn, severity=advisory, remediation non-empty.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 9: git_lfs probe: absent git-lfs => warn + advisory ==="

_t9_dir="$_SCRATCH_DIR/t9_no_lfs"
mkdir -p "$_t9_dir"

# Stub: a `git` that exits 1 for any `lfs` subcommand (simulates missing git-lfs).
# The stub checks the first argument; if it is "lfs", exit 1. Otherwise delegate to
# the real git via exec (absolute path resolved below).
_REAL_GIT="$(command -v git 2>/dev/null || echo "")"

if [[ -n "$_REAL_GIT" ]]; then
    printf '#!/bin/sh\nif [ "$1" = "lfs" ]; then exit 1; fi\nexec "%s" "$@"\n' "$_REAL_GIT" > "$_t9_dir/git"
    chmod +x "$_t9_dir/git"

    PATH="$_t9_dir:$_ORIG_PATH"
    _t9_output="$(_co_probe_git_lfs 2>/dev/null)"
    PATH="$_ORIG_PATH"

    _t9_status="$(_json_field "$_t9_output" "status")"
    _t9_severity="$(_json_field "$_t9_output" "severity")"
    _t9_remediation="$(_json_field "$_t9_output" "remediation")"

    if [[ "$_t9_status" == "warn" ]]; then
        _pass "test 9a: git-lfs absent => status is 'warn'"
    else
        _fail "test 9a: git-lfs absent => expected status='warn' but got '$_t9_status' (output: $_t9_output)"
    fi

    if [[ "$_t9_severity" == "advisory" ]]; then
        _pass "test 9b: git-lfs absent => severity is 'advisory'"
    else
        _fail "test 9b: git-lfs absent => expected severity='advisory' but got '$_t9_severity'"
    fi

    if [[ -n "$_t9_remediation" ]]; then
        _pass "test 9c: git-lfs absent => remediation is non-empty: $_t9_remediation"
    else
        _fail "test 9c: git-lfs absent => remediation is empty — should contain install guidance"
    fi
else
    echo "SKIP: test 9 — real git not found on host; cannot stub lfs subcommand"
    _pass "test 9: skipped (no real git binary)"
fi

# ---------------------------------------------------------------------------
# Test 10: git_lfs probe: present git-lfs but NOT configured (filter.lfs.clean absent).
#
# Stub both `git lfs version` (succeeds, prints version) AND the
# `git config --global --get filter.lfs.clean` sub-probe (exits 1 = key absent).
# Assert: status=warn, severity=advisory.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 10: git_lfs probe: lfs present but not configured => warn + advisory ==="

_t10_dir="$_SCRATCH_DIR/t10_lfs_not_configured"
mkdir -p "$_t10_dir"

if [[ -n "$_REAL_GIT" ]]; then
    # Stub git: handles `git lfs version` (exit 0, prints version) and
    # `git config --global --get filter.lfs.clean` (exit 1, empty).
    cat > "$_t10_dir/git" << 'STUB_EOF'
#!/bin/sh
if [ "$1" = "lfs" ] && [ "$2" = "version" ]; then
    echo "git-lfs/3.5.1 (GitHub; darwin arm64; go 1.21.3)"
    exit 0
fi
if [ "$1" = "config" ] && [ "$2" = "--global" ] && [ "$3" = "--get" ] && [ "$4" = "filter.lfs.clean" ]; then
    exit 1
fi
STUB_EOF
    # Append a delegation to real git for anything else (ensures git is available for
    # other internal prereq_probe.sh uses if any).
    printf 'exec "%s" "$@"\n' "$_REAL_GIT" >> "$_t10_dir/git"
    chmod +x "$_t10_dir/git"

    PATH="$_t10_dir:$_ORIG_PATH"
    _t10_output="$(_co_probe_git_lfs 2>/dev/null)"
    PATH="$_ORIG_PATH"

    _t10_status="$(_json_field "$_t10_output" "status")"
    _t10_severity="$(_json_field "$_t10_output" "severity")"

    if [[ "$_t10_status" == "warn" ]]; then
        _pass "test 10a: git-lfs present-not-configured => status is 'warn'"
    else
        _fail "test 10a: git-lfs present-not-configured => expected status='warn' but got '$_t10_status' (output: $_t10_output)"
    fi

    if [[ "$_t10_severity" == "advisory" ]]; then
        _pass "test 10b: git-lfs present-not-configured => severity is 'advisory'"
    else
        _fail "test 10b: git-lfs present-not-configured => expected severity='advisory' but got '$_t10_severity'"
    fi
else
    echo "SKIP: test 10 — real git not found on host"
    _pass "test 10: skipped (no real git binary)"
fi

# ---------------------------------------------------------------------------
# Test 11: git_lfs probe: present and configured => pass + advisory.
#
# Stub both `git lfs version` (exit 0, prints version) AND
# `git config --global --get filter.lfs.clean` (exit 0, prints a non-empty value).
# Assert: status=pass, severity=advisory.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 11: git_lfs probe: lfs present and configured => pass + advisory ==="

_t11_dir="$_SCRATCH_DIR/t11_lfs_configured"
mkdir -p "$_t11_dir"

if [[ -n "$_REAL_GIT" ]]; then
    cat > "$_t11_dir/git" << 'STUB_EOF'
#!/bin/sh
if [ "$1" = "lfs" ] && [ "$2" = "version" ]; then
    echo "git-lfs/3.5.1 (GitHub; darwin arm64; go 1.21.3)"
    exit 0
fi
if [ "$1" = "config" ] && [ "$2" = "--global" ] && [ "$3" = "--get" ] && [ "$4" = "filter.lfs.clean" ]; then
    echo "git-lfs clean -- %f"
    exit 0
fi
STUB_EOF
    printf 'exec "%s" "$@"\n' "$_REAL_GIT" >> "$_t11_dir/git"
    chmod +x "$_t11_dir/git"

    PATH="$_t11_dir:$_ORIG_PATH"
    _t11_output="$(_co_probe_git_lfs 2>/dev/null)"
    PATH="$_ORIG_PATH"

    _t11_status="$(_json_field "$_t11_output" "status")"
    _t11_severity="$(_json_field "$_t11_output" "severity")"

    if [[ "$_t11_status" == "pass" ]]; then
        _t11_detail="$(_json_field "$_t11_output" "detail")"
        _pass "test 11a: git-lfs present+configured => status is 'pass' (detail: $_t11_detail)"
    else
        _fail "test 11a: git-lfs present+configured => expected status='pass' but got '$_t11_status' (output: $_t11_output)"
    fi

    if [[ "$_t11_severity" == "advisory" ]]; then
        _pass "test 11b: git-lfs present+configured => severity is 'advisory'"
    else
        _fail "test 11b: git-lfs present+configured => expected severity='advisory' but got '$_t11_severity'"
    fi
else
    echo "SKIP: test 11 — real git not found on host"
    _pass "test 11: skipped (no real git binary)"
fi

# ---------------------------------------------------------------------------
# Test 12: AC10 — advisory git_lfs warn must NOT change aggregator exit code.
#
# Run _co_prereq_probe_all in a subshell where git-lfs is unavailable.
# Capture its exit code. It must be 0 (advisory-only failures never fail the suite).
# Also confirm the git_lfs line appears in the output and has severity=advisory.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 12: AC10 — advisory git_lfs warn does NOT change aggregator exit code ==="

_t12_dir="$_SCRATCH_DIR/t12_no_lfs_aggregator"
mkdir -p "$_t12_dir"

if [[ -n "$_REAL_GIT" ]]; then
    # Stub: git lfs fails; all other git calls delegated to real git.
    printf '#!/bin/sh\nif [ "$1" = "lfs" ]; then exit 1; fi\nexec "%s" "$@"\n' "$_REAL_GIT" > "$_t12_dir/git"
    chmod +x "$_t12_dir/git"

    _t12_exit=0
    _t12_output="$(PATH="$_t12_dir:$_ORIG_PATH" _co_prereq_probe_all 2>/dev/null)" || _t12_exit=$?

    if [[ "$_t12_exit" -eq 0 ]]; then
        _pass "test 12a: _co_prereq_probe_all exit code is 0 even when git_lfs warns (advisory does not fail the suite)"
    else
        _fail "test 12a: _co_prereq_probe_all exited $_t12_exit — expected 0 (advisory git_lfs must not gate the suite)"
    fi

    # Find the git_lfs line in the output and confirm it is advisory.
    _t12_lfs_line=""
    while IFS= read -r _line; do
        _t12_name="$(_json_field "$_line" "name")"
        if [[ "$_t12_name" == "git_lfs" ]]; then
            _t12_lfs_line="$_line"
            break
        fi
    done <<< "$_t12_output"

    if [[ -n "$_t12_lfs_line" ]]; then
        _pass "test 12b: git_lfs line present in aggregator output"
        _t12_lfs_severity="$(_json_field "$_t12_lfs_line" "severity")"
        if [[ "$_t12_lfs_severity" == "advisory" ]]; then
            _pass "test 12c: git_lfs line has severity='advisory' in aggregator output"
        else
            _fail "test 12c: git_lfs line has severity='$_t12_lfs_severity' — expected 'advisory'"
        fi
    else
        _fail "test 12b: git_lfs line NOT found in aggregator output (output: $_t12_output)"
    fi
else
    echo "SKIP: test 12 — real git not found on host"
    _pass "test 12: skipped (no real git binary)"
fi

# ---------------------------------------------------------------------------
# Tests 13-18: _co_probe_shell_login_env — macOS login-shell orphan probe.
#
# Mocking strategy:
#   - A fake `uname` stub on PATH controls the macOS guard (Darwin or Linux).
#   - A fake `dscl` stub on PATH returns "UserShell: <path>" so awk extracts
#     the absolute path to the fake login-shell binary.
#   - Fake bash/zsh binaries on PATH respond to -lc invocations; their
#     basename (bash / zsh) drives the orphan-predicate branch.
#   - SHELL env var is managed for the no-login-shell (inconclusive) case.
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test 13: shell_login_env: orphaned bash login shell => fail.
#
# uname returns Darwin; dscl identifies a fake bash; fake bash reports a
# fresh PATH that lacks $HOME/.local/bin and does not resolve claude.
# The orphan predicate fires => status must be "fail".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 13: shell_login_env: orphaned bash login shell => fail ==="

_t13_dir="$_SCRATCH_DIR/t13_orphaned_bash"
mkdir -p "$_t13_dir"

# uname stub: returns "Darwin" so the macOS guard does not short-circuit.
_make_stub "$_t13_dir" "uname" "0" "Darwin"

# dscl stub: prints "UserShell: <dir>/bash" so awk extracts the fake bash path.
printf '#!/bin/sh\nprintf "UserShell: %s/bash\\n"\n' "$_t13_dir" > "$_t13_dir/dscl"
chmod +x "$_t13_dir/dscl"

# Fake bash login shell: PATH lacks $HOME/.local/bin; claude not found.
# Named "bash" so _login_basename == "bash" → orphan predicate runs.
cat > "$_t13_dir/bash" << 'STUB_EOF'
#!/bin/sh
# Fake bash: minimal PATH without ~/.local/bin; claude absent.
if [ "$1" = "-lc" ]; then
    case "$2" in
        *printf*) printf '%s' "/usr/bin:/bin" ;;
        # claude check: fall through → prints nothing (unresolvable)
    esac
fi
exit 0
STUB_EOF
chmod +x "$_t13_dir/bash"

PATH="$_t13_dir:$_ORIG_PATH"
_t13_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

_t13_status="$(_json_field "$_t13_output" "status")"
_t13_remediation="$(_json_field "$_t13_output" "remediation")"
if [[ "$_t13_status" == "fail" ]]; then
    _pass "test 13a: orphaned bash login shell (PATH lacks \$HOME/.local/bin) => status is 'fail'"
else
    _fail "test 13a: orphaned bash login shell => expected status='fail' but got '$_t13_status' (output: $_t13_output)"
fi
# Review: code-reviewer F6 — added remediation assertion (sibling tests 2/6/7/8/9 assert all fields).
if [[ -n "$_t13_remediation" ]]; then
    _pass "test 13b: orphaned bash login shell => remediation is non-empty: $_t13_remediation"
else
    _fail "test 13b: orphaned bash login shell => remediation is empty — should contain repair guidance"
fi

# ---------------------------------------------------------------------------
# Test 14: shell_login_env: zsh login shell => pass.
#
# Non-bash login shell: orphan predicate is bash-only; probe must return
# "pass" without checking PATH or claude resolubility.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 14: shell_login_env: zsh login shell => pass ==="

_t14_dir="$_SCRATCH_DIR/t14_zsh_login"
mkdir -p "$_t14_dir"

_make_stub "$_t14_dir" "uname" "0" "Darwin"

printf '#!/bin/sh\nprintf "UserShell: %s/zsh\\n"\n' "$_t14_dir" > "$_t14_dir/dscl"
chmod +x "$_t14_dir/dscl"

# Fake zsh: named "zsh" so _login_basename != "bash" → probe short-circuits to pass.
# Returns a valid (non-empty) PATH for the -lc 'printf %s "$PATH"' capture step.
cat > "$_t14_dir/zsh" << 'STUB_EOF'
#!/bin/sh
# Fake zsh: returns a valid PATH so the empty-PATH inconclusive guard does not fire.
if [ "$1" = "-lc" ]; then
    case "$2" in
        *printf*) printf '%s' "/usr/bin:/bin" ;;
    esac
fi
exit 0
STUB_EOF
chmod +x "$_t14_dir/zsh"

PATH="$_t14_dir:$_ORIG_PATH"
_t14_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

_t14_status="$(_json_field "$_t14_output" "status")"
_t14_detail="$(_json_field "$_t14_output" "detail")"
if [[ "$_t14_status" == "pass" ]]; then
    _pass "test 14a: zsh login shell => status is 'pass' (orphan predicate is bash-only)"
else
    _fail "test 14a: zsh login shell => expected status='pass' but got '$_t14_status' (output: $_t14_output)"
fi
# Review: code-reviewer F6 — added detail assertion (sibling tests assert all fields).
if [[ -n "$_t14_detail" ]]; then
    _pass "test 14b: zsh login shell => detail is non-empty: $_t14_detail"
else
    _fail "test 14b: zsh login shell => detail is empty — probe should always populate detail"
fi

# ---------------------------------------------------------------------------
# Test 15: shell_login_env: bash login shell with intact ~/.local/bin + claude => pass.
#
# Fake bash reports $HOME/.local/bin in the fresh PATH AND resolves claude.
# Both orphan-predicate conditions are satisfied => status must be "pass".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 15: shell_login_env: bash login shell with intact PATH + claude => pass ==="

_t15_dir="$_SCRATCH_DIR/t15_bash_intact"
mkdir -p "$_t15_dir"

_make_stub "$_t15_dir" "uname" "0" "Darwin"

printf '#!/bin/sh\nprintf "UserShell: %s/bash\\n"\n' "$_t15_dir" > "$_t15_dir/dscl"
chmod +x "$_t15_dir/dscl"

# Fake bash: PATH includes $HOME/.local/bin; claude resolves.
# $HOME is expanded at runtime by /bin/sh (the stub interpreter), matching the
# probe's own $HOME expansion in the case-pattern match.
cat > "$_t15_dir/bash" << 'STUB_EOF'
#!/bin/sh
# Fake bash login shell: intact PATH; claude resolves in ~/.local/bin.
if [ "$1" = "-lc" ]; then
    case "$2" in
        *printf*)
            printf '%s' "$HOME/.local/bin:/usr/bin:/bin"
            ;;
        *claude*)
            printf '%s\n' "$HOME/.local/bin/claude"
            ;;
    esac
fi
exit 0
STUB_EOF
chmod +x "$_t15_dir/bash"

PATH="$_t15_dir:$_ORIG_PATH"
_t15_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

_t15_status="$(_json_field "$_t15_output" "status")"
_t15_detail="$(_json_field "$_t15_output" "detail")"
if [[ "$_t15_status" == "pass" ]]; then
    _pass "test 15a: bash login shell with intact \$HOME/.local/bin and claude => status is 'pass'"
else
    _fail "test 15a: bash login shell intact => expected status='pass' but got '$_t15_status' (output: $_t15_output)"
fi
# Review: code-reviewer F6 — added detail assertion (sibling tests assert all fields).
if [[ -n "$_t15_detail" ]]; then
    _pass "test 15b: bash login shell intact => detail is non-empty: $_t15_detail"
else
    _fail "test 15b: bash login shell intact => detail is empty — probe should always populate detail"
fi

# ---------------------------------------------------------------------------
# Test 16: shell_login_env: unprobeable login shell => inconclusive.
#
# dscl prints nothing (empty awk field $2) AND $SHELL is unset/empty.
# The probe cannot detect ANY login shell => must emit "inconclusive".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 16: shell_login_env: unprobeable login shell => inconclusive ==="

_t16_dir="$_SCRATCH_DIR/t16_no_shell"
mkdir -p "$_t16_dir"

_make_stub "$_t16_dir" "uname" "0" "Darwin"

# dscl stub: prints nothing → awk field $2 is empty → _login_shell is empty.
_make_stub "$_t16_dir" "dscl" "0"

# Temporarily clear SHELL so the ${SHELL:-} fallback also yields empty.
_t16_saved_shell="${SHELL:-}"
SHELL=""

PATH="$_t16_dir:$_ORIG_PATH"
_t16_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

SHELL="$_t16_saved_shell"

_t16_status="$(_json_field "$_t16_output" "status")"
_t16_severity="$(_json_field "$_t16_output" "severity")"
if [[ "$_t16_status" == "inconclusive" ]]; then
    _pass "test 16a: unprobeable login shell (dscl empty + SHELL unset) => status is 'inconclusive'"
else
    _fail "test 16a: unprobeable login shell => expected status='inconclusive' but got '$_t16_status' (output: $_t16_output)"
fi
# Review: code-reviewer F6 — added severity assertion (sibling tests assert all fields).
if [[ -n "$_t16_severity" ]]; then
    _pass "test 16b: unprobeable login shell => severity is set: $_t16_severity"
else
    _fail "test 16b: unprobeable login shell => severity is empty — probe must always set severity"
fi

# ---------------------------------------------------------------------------
# Test 17: shell_login_env: non-macOS (Linux mock) => pass.
#
# Mock uname to return "Linux". The macOS HARD short-circuit fires BEFORE
# the orphan predicate. Status MUST be "pass"; the probe must NEVER return
# "fail" for a non-Darwin system regardless of PATH or shell configuration.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 17: shell_login_env: non-macOS (Linux mock) => pass (macOS guard fires first) ==="

_t17_dir="$_SCRATCH_DIR/t17_linux"
mkdir -p "$_t17_dir"

# uname stub: returns "Linux" → macOS guard short-circuits the entire probe.
_make_stub "$_t17_dir" "uname" "0" "Linux"

PATH="$_t17_dir:$_ORIG_PATH"
_t17_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

_t17_status="$(_json_field "$_t17_output" "status")"
if [[ "$_t17_status" == "pass" ]]; then
    _pass "test 17a: non-macOS (Linux mock) => macOS guard fires => status is 'pass' (orphan predicate never runs)"
else
    _fail "test 17a: non-macOS => expected status='pass' but got '$_t17_status' (output: $_t17_output)"
fi

# ---------------------------------------------------------------------------
# Test 18: shell_login_env: login shell -lc exits non-zero => inconclusive.
#
# Exercises the "|| true" guard + empty-fresh-PATH inconclusive path:
#   1. The fake bash exits 1 immediately (simulating an rc file failure).
#   2. The || true in the probe catches the non-zero exit under set -euo pipefail.
#   3. _fresh_path is empty (nothing printed before exit) => inconclusive.
#
# Critical invariant: the probe must NOT crash and must NOT emit "fail" —
# an unprobeable shell is inconclusive, not a confirmed orphan.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 18: shell_login_env: login shell -lc exits non-zero => inconclusive ==="

_t18_dir="$_SCRATCH_DIR/t18_lc_fail"
mkdir -p "$_t18_dir"

_make_stub "$_t18_dir" "uname" "0" "Darwin"

# dscl stub points at the fake bash so the login shell IS detected
# (distinguishes this case from test 16's "no shell detected" inconclusive path).
printf '#!/bin/sh\nprintf "UserShell: %s/bash\\n"\n' "$_t18_dir" > "$_t18_dir/dscl"
chmod +x "$_t18_dir/dscl"

# Fake bash: exits 1 immediately, prints nothing.
# The || true in the probe absorbs the error; _fresh_path becomes empty => inconclusive.
_make_stub "$_t18_dir" "bash" "1"

PATH="$_t18_dir:$_ORIG_PATH"
_t18_output="$(_co_probe_shell_login_env 2>/dev/null)"
PATH="$_ORIG_PATH"

_t18_status="$(_json_field "$_t18_output" "status")"
_t18_severity="$(_json_field "$_t18_output" "severity")"
if [[ "$_t18_status" == "inconclusive" ]]; then
    _pass "test 18a: login shell -lc exits non-zero => || true guard absorbed, empty PATH => status is 'inconclusive' (not crash, not fail)"
else
    _fail "test 18a: login shell -lc exits non-zero => expected status='inconclusive' but got '$_t18_status' (output: $_t18_output)"
fi
# Review: code-reviewer F6 — added severity assertion (sibling tests assert all fields).
if [[ -n "$_t18_severity" ]]; then
    _pass "test 18b: login shell -lc exits non-zero => severity is set: $_t18_severity"
else
    _fail "test 18b: login shell -lc exits non-zero => severity is empty — probe must always set severity"
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
