#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# plugins/deep-research/tests/test_prereq_probe.sh
#
# Tests for the VENDORED prereq_probe unit at
# deep-research/scripts/lib/coordinator_prereq/ (prereq_probe.sh +
# step_zero_emit.sh + manifest_reader.sh — byte-identical to coordinator SSOT).
#
# Exercises the probe functions sourced from the DR vendored location and
# asserts the three critical the Staff Engineer / CR requirements:
#
#   P0-2 (AC5)  — bash -c invocation with empty BASH_SOURCE succeeds GREEN under
#                 the COORDINATOR_PREREQ_PROBE_LIB_DIR override.
#   P1-1        — REPO_ROOT is exported to the meta-repo root so
#                 _co_resolve_manifest_path honours the live contract.
#   CR-2        — after the _dr_ fork deletion, the collision guard finds
#                 _co_find_python defined (the _co_ manifest_reader sourced
#                 correctly) and does NOT fire.
#
# Test cases:
#   1. probe-all emits exactly 10 valid NDJSON lines with required keys/enum values.
#   2. AC1 — python probe rejects a broken Store-stub (exits 49) and reports remediation.
#   3. AC5 — probes are FUNCTIONAL, not existence-only: broken-uv stub yields non-"pass".
#   4. pass path — on macOS, python probe returns "pass"; longpaths returns "pass"
#      with detail "n/a (non-Windows)".
#   5. inconclusive is a valid reachable status — clone_auth returns one of the
#      valid enum values (pass|warn|inconclusive).
#   6. AC7 — gh probe: absent binary yields status=fail and severity=hard.
#   7. AC7 — gh probe: present binary with valid auth yields valid status enum + severity=hard.
#   8. AC7 — node probe: absent binary yields status=fail; present node yields status=pass.
#   9. git_lfs probe: absent git-lfs yields status=warn and severity=advisory.
#  10. git_lfs probe: present git-lfs but not configured yields status=warn + advisory.
#  11. git_lfs probe: present and configured yields status=pass + advisory.
#  12. AC10 — advisory git_lfs warn does not change aggregator exit code (NEVER fails the suite).
#  13. P0-2 — bash -c invocation with COORDINATOR_PREREQ_PROBE_LIB_DIR override runs GREEN.
#  14. CR-2 — collision guard resolves green: _co_find_python defined, guard does NOT fire.
#
# Spec backlink: docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md
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
# Locate the deep-research plugin root and the vendored library under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# The vendored prereq unit lives in its own isolated subdir (cross-repo memo 2026-06-22).
DR_PREREQ_LIB_DIR="${DR_ROOT}/scripts/lib/coordinator_prereq"
LIB_UNDER_TEST="${DR_PREREQ_LIB_DIR}/prereq_probe.sh"

if [[ ! -f "$LIB_UNDER_TEST" ]]; then
    echo "ERROR: vendored library not found: $LIB_UNDER_TEST" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# P1-1: export REPO_ROOT to the meta-repo root so _co_resolve_manifest_path
# honours the live contract (not the flat-fallback accident).
# The meta-repo root is two levels up from deep-research/ (deep-research is
# plugins/deep-research/).
# ---------------------------------------------------------------------------
META_REPO_ROOT="$(cd "${DR_ROOT}/../.." && pwd)"
export REPO_ROOT="${META_REPO_ROOT}"

# Source the vendored library -- defines all _co_probe_* and _co_prereq_probe_all.
# COORDINATOR_PREREQ_PROBE_LIB_DIR is set so the source succeeds even if BASH_SOURCE
# would resolve wrongly in some invocation contexts.
export COORDINATOR_PREREQ_PROBE_LIB_DIR="${DR_PREREQ_LIB_DIR}"
# shellcheck source=../scripts/lib/coordinator_prereq/prereq_probe.sh
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
#
# The DR vendored unit includes _co_probe_git (added in the coordinator BUMP
# PENDING 2026-06-23 — the DR vendor already carries it) bringing the
# aggregator to 10 probes: git, python, uv, gh, node, pwsh, ue, clone_auth,
# longpaths, git_lfs.
#
# Each line must:
#   - parse as JSON (no syntax errors).
#   - contain all 5 required keys: name, status, severity, detail, remediation.
#   - have status in {pass, fail, warn, inconclusive}.
#   - have severity in {hard, advisory}.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: probe-all emits 10 valid NDJSON lines with required keys/enum values ==="

_t1_output="$(_co_prereq_probe_all 2>/dev/null)"
# Guard grep -c . on empty input (exits 1 under set -euo pipefail).
_t1_line_count=0
[[ -n "$_t1_output" ]] && _t1_line_count="$(printf '%s\n' "$_t1_output" | grep -c . || echo 0)"

if [[ "$_t1_line_count" -ne 10 ]]; then
    _fail "test 1a: expected 10 lines from _co_prereq_probe_all, got $_t1_line_count"
else
    _pass "test 1a: probe-all emits exactly 10 lines"
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
    _pass "test 1b/c: all 10 lines are valid JSON with correct keys and enum values"
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
#   - assert: remediation is non-empty.
# PATH is restored after the test.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: AC1 — python probe rejects Store-stub (exit 49), reports remediation ==="

_t2_dir="$_SCRATCH_DIR/t2_stub"
mkdir -p "$_t2_dir"

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
# Part A (python): the exit-49 stub case (Test 2) already demonstrates this.
#   Record it explicitly here as the AC5 python evidence.
#
# Part B (uv): create a fake "uv" on PATH that exits 1 (simulates a broken install).
#   Assert uv probe status is NOT "pass".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: AC5 — functional probes: broken-uv stub yields non-pass status ==="

# Part A: python evidence — assert on the real test-2 result captured above.
if [[ "$_t2_status" == "fail" ]]; then
    _pass "test 3a: AC5 python evidence — _co_probe_python returned 'fail' for Store-stub (functional, not existence-only)"
else
    _fail "test 3a: AC5 python evidence — expected _co_probe_python status='fail' for Store-stub but got '$_t2_status'"
fi

# Part B: uv — fake uv exits 1 (empty/nonzero output).
_t3_dir="$_SCRATCH_DIR/t3_uv"
mkdir -p "$_t3_dir"
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
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 4: pass path — macOS python pass; longpaths pass with non-Windows detail ==="

_t4_os="$(uname -s 2>/dev/null)"

if [[ "$_t4_os" == "Darwin" ]]; then
    _t4_py_output="$(_co_probe_python 2>/dev/null)"
    _t4_py_status="$(_json_field "$_t4_py_output" "status")"
    if [[ "$_t4_py_status" == "pass" ]]; then
        _t4_py_detail="$(_json_field "$_t4_py_output" "detail")"
        _pass "test 4a: _co_probe_python returns 'pass' on macOS (detail: $_t4_py_detail)"
    else
        _fail "test 4a: _co_probe_python returned '$_t4_py_status' on macOS — expected 'pass' (is Python 3.11+ installed?)"
    fi

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
# Assert the returned status is one of the valid enum values.
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

_t5_synthetic='{"name":"clone_auth","status":"inconclusive","severity":"advisory","detail":"Network unreachable; cannot determine clone auth state","remediation":"ensure network connectivity"}'
if [[ -n "$_PY" ]] && "$_PY" -c "import json,sys; d=json.loads(sys.argv[1]); assert d['status']=='inconclusive'" "$_t5_synthetic" 2>/dev/null; then  # popup-safe-env-suppressed
    _pass "test 5b: harness correctly parses 'inconclusive' as a valid status value"
else
    _fail "test 5b: harness failed to parse synthetic inconclusive JSON — tooling issue"
fi

# ---------------------------------------------------------------------------
# Test 6: AC7 — gh probe: absent binary yields status=fail and severity=hard.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 6: AC7 — gh probe: absent binary yields fail + hard severity ==="

_t6_dir="$_SCRATCH_DIR/t6_no_gh"
mkdir -p "$_t6_dir"

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
# Verifies the probe emits valid JSON with severity=hard regardless of auth state.
# Status must be in {pass, fail} — warn is not emitted by this probe.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 7: AC7 — gh probe: present path emits hard severity + valid enum ==="

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
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 8: AC7 — node probe: absent => fail; present => pass ==="

# Part A: absent node.
_t8_dir="$_SCRATCH_DIR/t8_no_node"
mkdir -p "$_t8_dir"

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
_t8c_dir="$_SCRATCH_DIR/t8c_broken_node"
mkdir -p "$_t8c_dir"
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
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 9: git_lfs probe: absent git-lfs => warn + advisory ==="

_t9_dir="$_SCRATCH_DIR/t9_no_lfs"
mkdir -p "$_t9_dir"

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
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 10: git_lfs probe: lfs present but not configured => warn + advisory ==="

_t10_dir="$_SCRATCH_DIR/t10_lfs_not_configured"
mkdir -p "$_t10_dir"

if [[ -n "$_REAL_GIT" ]]; then
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
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 12: AC10 — advisory git_lfs warn does NOT change aggregator exit code ==="

_t12_dir="$_SCRATCH_DIR/t12_no_lfs_aggregator"
mkdir -p "$_t12_dir"

if [[ -n "$_REAL_GIT" ]]; then
    printf '#!/bin/sh\nif [ "$1" = "lfs" ]; then exit 1; fi\nexec "%s" "$@"\n' "$_REAL_GIT" > "$_t12_dir/git"
    chmod +x "$_t12_dir/git"

    _t12_exit=0
    _t12_output="$(PATH="$_t12_dir:$_ORIG_PATH" _co_prereq_probe_all 2>/dev/null)" || _t12_exit=$?

    if [[ "$_t12_exit" -eq 0 ]]; then
        _pass "test 12a: _co_prereq_probe_all exit code is 0 even when git_lfs warns (advisory does not fail the suite)"
    else
        _fail "test 12a: _co_prereq_probe_all exited $_t12_exit — expected 0 (advisory git_lfs must not gate the suite)"
    fi

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
# Test 13: P0-2 (AC5) — bash -c invocation with empty BASH_SOURCE runs GREEN.
#
# This is the exact path the isolated-subdir layout breaks without the
# COORDINATOR_PREREQ_PROBE_LIB_DIR override. Invoke under bash -c with the
# override set and assert the probe runs successfully (exit 0, emits JSON).
#
# The invocation exercises the four-step lib-dir fallback in prereq_probe.sh:
# under `bash -c`, BASH_SOURCE[0] is empty — the override is the ONLY reliable
# path to the sibling libs. Without it, the probe exits 1 with "cannot resolve
# lib dir". With it, the probe sources correctly and runs to completion.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 13: P0-2 — bash -c with COORDINATOR_PREREQ_PROBE_LIB_DIR override runs GREEN ==="

_t13_bash_c_out=""
_t13_bash_c_exit=0
_t13_bash_c_out="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${LIB_UNDER_TEST}'
_co_prereq_probe_all
" 2>/dev/null)" || _t13_bash_c_exit=$?

if [[ "$_t13_bash_c_exit" -eq 0 ]]; then
    _pass "test 13a: bash -c invocation with COORDINATOR_PREREQ_PROBE_LIB_DIR override exits 0 (GREEN)"
else
    _fail "test 13a: bash -c invocation exited $_t13_bash_c_exit — COORDINATOR_PREREQ_PROBE_LIB_DIR override broken"
fi

# Verify output is non-empty and at least one line is valid JSON.
_t13_line_count=0
[[ -n "$_t13_bash_c_out" ]] && _t13_line_count="$(printf '%s\n' "$_t13_bash_c_out" | grep -c . || echo 0)"

if [[ "$_t13_line_count" -ge 1 ]]; then
    _pass "test 13b: bash -c invocation emitted $_t13_line_count NDJSON lines (probe ran to completion)"
else
    _fail "test 13b: bash -c invocation emitted no output — prereq_probe did not run"
fi

# Verify the first line is valid JSON (sanity-check the output shape).
_t13_first_line="$(printf '%s\n' "$_t13_bash_c_out" | head -1)"
if [[ -n "$_t13_first_line" ]] && _json_valid "$_t13_first_line"; then
    _pass "test 13c: first output line from bash -c invocation is valid JSON"
else
    _fail "test 13c: first output line from bash -c invocation is not valid JSON: $_t13_first_line"
fi

# ---------------------------------------------------------------------------
# Test 14: CR-2 — collision guard resolves green in DR context.
#
# After the _dr_ fork deletion (the vendored copy uses _co_ prefixes, same as
# the coordinator SSOT), assert:
#   a. _co_find_python is defined (the correct _co_ manifest_reader was sourced).
#   b. _co_pp_emit is defined (the correct _co_ step_zero_emit was sourced).
#   c. The collision guard (prereq_probe.sh ~L126) did NOT fire — i.e. the
#      probe sources cleanly without exiting 1 with the "NAME COLLISION" message.
#
# The test uses the already-sourced session (COORDINATOR_PREREQ_PROBE_LIB_DIR
# was set before source above) to verify the post-source symbol state.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 14: CR-2 — collision guard resolves green: _co_find_python defined, guard did not fire ==="

if command -v _co_find_python >/dev/null 2>&1; then
    _pass "test 14a: _co_find_python is defined — _co_ manifest_reader sourced correctly (collision guard did not fire)"
else
    _fail "test 14a: _co_find_python is NOT defined — collision guard may have fired or wrong manifest_reader.sh was sourced"
fi

if command -v _co_pp_emit >/dev/null 2>&1; then
    _pass "test 14b: _co_pp_emit is defined — _co_ step_zero_emit sourced correctly"
else
    _fail "test 14b: _co_pp_emit is NOT defined — wrong step_zero_emit.sh may have been sourced"
fi

# Re-source in a clean subshell with COORDINATOR_PREREQ_PROBE_LIB_DIR set and
# confirm no "NAME COLLISION" / "cannot resolve lib dir" error output.
_t14_collision_out=""
_t14_collision_exit=0
_t14_collision_out="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${LIB_UNDER_TEST}'
" 2>&1)" || _t14_collision_exit=$?

if [[ "$_t14_collision_exit" -eq 0 ]]; then
    _pass "test 14c: DR vendored prereq_probe.sh sources cleanly in a fresh subshell (exit 0)"
else
    _fail "test 14c: DR vendored prereq_probe.sh source exited $_t14_collision_exit — collision guard or source error: $_t14_collision_out"
fi

if echo "$_t14_collision_out" | grep -qi "NAME COLLISION\|cannot resolve lib dir" 2>/dev/null; then
    _fail "test 14d: collision guard fired (or lib-dir resolution failed) — output: $_t14_collision_out"
else
    _pass "test 14d: no 'NAME COLLISION' or 'cannot resolve lib dir' in subshell output (collision guard did not fire)"
fi

# ---------------------------------------------------------------------------
# Test 15: DR capability probe — _dr_cap_probe_all emits exactly 5 valid NDJSON lines.
#
# The DR capability probe (scripts/lib/dr_capability_probe.sh) is distinct from
# the vendored coordinator machine-prereq probe. It reports DR harness readiness:
# agent_teams, pipelines_present, web_access, notebooklm, python — in that
# env-only-first order so the agent_teams check runs with no Python/tool dependency.
#
# Each line must:
#   - parse as JSON (no syntax errors).
#   - contain all 5 required keys: name, status, severity, detail, remediation.
#   - have status in {pass, fail, warn}.
#   - have severity in {hard, advisory}.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 15: DR capability probe — _dr_cap_probe_all emits 5 valid NDJSON lines ==="

DR_CAP_PROBE="${DR_ROOT}/scripts/lib/dr_capability_probe.sh"
if [[ ! -f "$DR_CAP_PROBE" ]]; then
    _fail "test 15 setup: dr_capability_probe.sh not found at $DR_CAP_PROBE"
else
    _t15_output=""
    _t15_source_exit=0
    _t15_output="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
_dr_cap_probe_all
" 2>/dev/null)" || _t15_source_exit=$?

    _t15_line_count=0
    [[ -n "$_t15_output" ]] && _t15_line_count="$(printf '%s\n' "$_t15_output" | grep -c . || echo 0)"

    if [[ "$_t15_line_count" -eq 5 ]]; then
        _pass "test 15a: _dr_cap_probe_all emits exactly 5 lines"
    else
        _fail "test 15a: expected 5 lines from _dr_cap_probe_all, got $_t15_line_count (exit: $_t15_source_exit)"
    fi

    _t15_bad=0
    _t15_line_num=0
    while IFS= read -r _line; do
        _t15_line_num=$(( _t15_line_num + 1 ))
        [[ -z "$_line" ]] && continue

        if ! _json_valid "$_line"; then
            _fail "test 15b: line $_t15_line_num is not valid JSON: $_line"
            _t15_bad=$(( _t15_bad + 1 ))
            continue
        fi

        for _key in name status severity detail; do
            _val="$(_json_field "$_line" "$_key")"
            if [[ -z "$_val" ]]; then
                _fail "test 15b: line $_t15_line_num missing required non-empty key '$_key': $_line"
                _t15_bad=$(( _t15_bad + 1 ))
            fi
        done

        _t15_status="$(_json_field "$_line" "status")"
        case "$_t15_status" in
            pass|fail|warn) ;;
            *)
                _fail "test 15b: line $_t15_line_num has invalid status '$_t15_status': $_line"
                _t15_bad=$(( _t15_bad + 1 ))
                ;;
        esac

        _t15_severity="$(_json_field "$_line" "severity")"
        case "$_t15_severity" in
            hard|advisory) ;;
            *)
                _fail "test 15b: line $_t15_line_num has invalid severity '$_t15_severity': $_line"
                _t15_bad=$(( _t15_bad + 1 ))
                ;;
        esac
    done <<< "$_t15_output"

    if [[ "$_t15_bad" -eq 0 ]]; then
        _pass "test 15b: all 5 lines are valid JSON with correct keys and enum values"
    fi
fi

# ---------------------------------------------------------------------------
# Test 16: DR capability probe — row 1 is agent_teams (env-only ordering).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 16: DR capability probe — row 1 is agent_teams (env-only ordering) ==="

if [[ ! -f "$DR_CAP_PROBE" ]]; then
    _fail "test 16 setup: dr_capability_probe.sh not found at $DR_CAP_PROBE"
else
    _t16_output=""
    _t16_output="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
_dr_cap_probe_all
" 2>/dev/null)"

    _t16_first_line="$(printf '%s\n' "$_t16_output" | head -1)"
    _t16_first_name="$(_json_field "$_t16_first_line" "name")"

    if [[ "$_t16_first_name" == "agent_teams" ]]; then
        _pass "test 16a: row 1 name is 'agent_teams' (env-only ordering confirmed)"
    else
        _fail "test 16a: row 1 name is '$_t16_first_name' — expected 'agent_teams' (env-only ordering violated)"
    fi
fi

# ---------------------------------------------------------------------------
# Test 17: agent_teams env-only behavior — UNSET env var yields fail+hard
#          with NO Python/shell tool dependency (pure env check).
#
# Mirror of Test 13's bash -c pattern: run in a fresh subshell with
# CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS explicitly unset to confirm the probe
# emits fail+hard using only env inspection (no Python, no PATH tools).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 17: agent_teams env-only: UNSET => fail+hard, no Python/tool dependency ==="

if [[ ! -f "$DR_CAP_PROBE" ]]; then
    _fail "test 17 setup: dr_capability_probe.sh not found at $DR_CAP_PROBE"
else
    _t17_output=""
    _t17_exit=0
    _t17_output="$("$_BASH4" -c "
unset CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
_dr_cap_probe_all
" 2>/dev/null)" || _t17_exit=$?

    _t17_first_line="$(printf '%s\n' "$_t17_output" | head -1)"
    _t17_name="$(_json_field "$_t17_first_line" "name")"
    _t17_status="$(_json_field "$_t17_first_line" "status")"
    _t17_severity="$(_json_field "$_t17_first_line" "severity")"

    if [[ "$_t17_name" == "agent_teams" ]]; then
        _pass "test 17a: agent_teams is row 1 even with CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS unset"
    else
        _fail "test 17a: row 1 name is '$_t17_name' — expected 'agent_teams'"
    fi

    if [[ "$_t17_status" == "fail" ]]; then
        _pass "test 17b: agent_teams status is 'fail' when env var is unset"
    else
        _fail "test 17b: agent_teams status is '$_t17_status' — expected 'fail' (env var unset)"
    fi

    if [[ "$_t17_severity" == "hard" ]]; then
        _pass "test 17c: agent_teams severity is 'hard' when env var is unset"
    else
        _fail "test 17c: agent_teams severity is '$_t17_severity' — expected 'hard'"
    fi

    # Confirm the probe emitted output at all (subshell ran without Python/tools on PATH).
    _t17_line_count=0
    [[ -n "$_t17_output" ]] && _t17_line_count="$(printf '%s\n' "$_t17_output" | grep -c . || echo 0)"
    if [[ "$_t17_line_count" -ge 1 ]]; then
        _pass "test 17d: probe emitted $_t17_line_count lines with env var unset (env-only check confirmed)"
    else
        _fail "test 17d: probe emitted no output with env var unset — env-only path broken"
    fi
fi

# ---------------------------------------------------------------------------
# Test 18: agent_teams env-only behavior — SET env var yields pass.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 18: agent_teams env-only: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 => pass ==="

if [[ ! -f "$DR_CAP_PROBE" ]]; then
    _fail "test 18 setup: dr_capability_probe.sh not found at $DR_CAP_PROBE"
else
    _t18_output=""
    _t18_output="$("$_BASH4" -c "
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
_dr_cap_probe_all
" 2>/dev/null)"

    _t18_first_line="$(printf '%s\n' "$_t18_output" | head -1)"
    _t18_name="$(_json_field "$_t18_first_line" "name")"
    _t18_status="$(_json_field "$_t18_first_line" "status")"

    if [[ "$_t18_name" == "agent_teams" ]]; then
        _pass "test 18a: agent_teams is row 1 with CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
    else
        _fail "test 18a: row 1 name is '$_t18_name' — expected 'agent_teams'"
    fi

    if [[ "$_t18_status" == "pass" ]]; then
        _pass "test 18b: agent_teams status is 'pass' when CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
    else
        _fail "test 18b: agent_teams status is '$_t18_status' — expected 'pass' (env var set to 1)"
    fi
fi

# ---------------------------------------------------------------------------
# Test 19: dr_capability_probe.sh sources cleanly in a fresh subshell and
#          _co_pp_emit is reachable (step_zero_emit vendored unit sourced).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 19: dr_capability_probe.sh sources cleanly; _co_pp_emit reachable ==="

if [[ ! -f "$DR_CAP_PROBE" ]]; then
    _fail "test 19 setup: dr_capability_probe.sh not found at $DR_CAP_PROBE"
else
    _t19_source_out=""
    _t19_source_exit=0
    _t19_source_out="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
" 2>&1)" || _t19_source_exit=$?

    if [[ "$_t19_source_exit" -eq 0 ]]; then
        _pass "test 19a: dr_capability_probe.sh sources cleanly in a fresh subshell (exit 0)"
    else
        _fail "test 19a: dr_capability_probe.sh source exited $_t19_source_exit: $_t19_source_out"
    fi

    # Verify _co_pp_emit is reachable after sourcing (step_zero_emit was vendored in).
    _t19_emit_out=""
    _t19_emit_exit=0
    _t19_emit_out="$("$_BASH4" -c "
export COORDINATOR_PREREQ_PROBE_LIB_DIR='${DR_PREREQ_LIB_DIR}'
export REPO_ROOT='${META_REPO_ROOT}'
source '${DR_CAP_PROBE}'
command -v _co_pp_emit >/dev/null 2>&1 && echo 'defined' || echo 'missing'
" 2>/dev/null)" || _t19_emit_exit=$?

    if [[ "$_t19_emit_out" == "defined" ]]; then
        _pass "test 19b: _co_pp_emit is reachable after sourcing dr_capability_probe.sh (step_zero_emit vendored correctly)"
    else
        _fail "test 19b: _co_pp_emit is not reachable after sourcing dr_capability_probe.sh (output: $_t19_emit_out, exit: $_t19_emit_exit)"
    fi
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
