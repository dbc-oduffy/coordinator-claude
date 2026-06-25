#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# plugins/coordinator/tests/test_step_zero.sh
#
# Tests for the --preflight mode of scripts/setup.sh.
# --preflight is a superset of --check: probes manifest deps AND env-prereq
# probes (from scripts/lib/prereq_probe.sh) through one unified tabling +
# NDJSON emitter, with a severity-aware exit gate.
#
# Realizes plan ACs AC2, AC3, AC8 from:
# docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
#
# Test cases:
#   1. AC3 — NDJSON shape: --preflight emits >=6 NDJSON lines with correct keys
#            (id/status/severity/hint) from the unified _co_pf_emit_row emitter.
#   2. AC2 — exit-code gate (three sub-cases):
#      a. Green path: on macOS with a healthy python, --preflight exits 0.
#      b. Hard-FAIL path: python stub that exits 49 causes --preflight to exit non-zero.
#      c. Advisory-does-not-fail: advisory probe failure does NOT affect exit code.
#   3. AC8 — layout-aware: --preflight resolves in both nested and flat layouts.
#
# NDJSON emitter shape (from _co_pf_emit_row in setup.sh --preflight block):
#   {"id":"<name>","status":"<pass|fail|warn|inconclusive>","severity":"<hard|advisory>","hint":"<combined>"}
#   NOTE: these differ from prereq_probe.sh's native shape (name/detail/remediation)
#   because --preflight adapts through _co_pf_emit_row.
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md §AC2 §AC3 §AC8
#
# Cross-platform portability (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4.
#   - BSD-portable: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable.
#   - macOS-passing required; guards in place for macOS-only assertions.
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
# Locate the coordinator plugin root and setup.sh.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_SH="${COORDINATOR_ROOT}/scripts/setup.sh"

if [[ ! -f "$SETUP_SH" ]]; then
    echo "ERROR: setup.sh not found: $SETUP_SH" >&2
    exit 1
fi

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
# Scratch directory for fake stubs and flat-layout fixture.
# PATH is saved globally so per-test mutations can be restored.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
_ORIG_PATH="$PATH"

cleanup() {
    PATH="$_ORIG_PATH"
    rm -rf "$_SCRATCH_DIR"
}
trap cleanup EXIT

# Helper: create a minimal executable stub in a directory.
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

# Helper: resolve a Python binary to use for JSON field extraction.
# Captures the real python3/python BEFORE any PATH mutation.
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
# Helper: run setup.sh --preflight and extract only the NDJSON lines from
# combined stdout+stderr output.
# NDJSON lines are identified as lines starting with '{' (emitted to stdout by
# _co_pf_emit_row). Human-readable table rows and banners go to stdout too, but
# only NDJSON rows begin with '{'.
# ---------------------------------------------------------------------------
_extract_ndjson_lines() {
    local _output="$1"
    echo "$_output" | grep -E '^\{' || true
}

# ---------------------------------------------------------------------------
# Test 1: AC3 — NDJSON shape.
#
# Run `bash scripts/setup.sh --preflight`, extract NDJSON lines, assert:
#   - each line parses as JSON
#   - there are >= 6 lines (one per prereq probe; dep probes may add more but
#     coordinator is DAG root with no deps)
#   - required keys are present: id, status, severity, hint
#   - status in {pass, fail, warn, inconclusive}
#   - severity in {hard, advisory}
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: AC3 — --preflight NDJSON shape (keys: id/status/severity/hint) ==="

_t1_output=""
if _t1_output="$("$_BASH4" "$SETUP_SH" --preflight 2>&1)"; then
    : # exit 0 is fine
else
    _t1_exit=$?
    # Non-zero exit is only a concern if it's not due to a real hard-fail probe.
    # We still extract and validate the NDJSON regardless of exit code.
    echo "  NOTE: --preflight exited $_t1_exit (may be a hard-probe failure; still validating NDJSON)"
fi

_t1_ndjson="$(_extract_ndjson_lines "$_t1_output")"
_t1_line_count=0
# Review: code-reviewer F4 — guard grep -c . on possibly-empty input (exits 1 under set -euo pipefail)
if [[ -n "$_t1_ndjson" ]]; then
    _t1_line_count="$(printf '%s\n' "$_t1_ndjson" | grep -c . || echo 0)"
fi

if [[ "$_t1_line_count" -ge 6 ]]; then
    _pass "test 1a: --preflight emits >= 6 NDJSON lines (got $_t1_line_count)"
else
    _fail "test 1a: expected >= 6 NDJSON lines from --preflight, got $_t1_line_count"
fi

_t1_bad=0
_t1_line_num=0
while IFS= read -r _line; do
    [[ -z "$_line" ]] && continue
    _t1_line_num=$(( _t1_line_num + 1 ))

    # Validate parseable JSON.
    if ! _json_valid "$_line"; then
        _fail "test 1b: NDJSON line $_t1_line_num is not valid JSON: $_line"
        _t1_bad=$(( _t1_bad + 1 ))
        continue
    fi

    # Validate required keys are present and non-empty.
    # 'hint' may be empty string on a pass row — check key exists but allow empty.
    for _key in id status severity; do
        _val="$(_json_field "$_line" "$_key")"
        if [[ -z "$_val" ]]; then
            _fail "test 1b: NDJSON line $_t1_line_num missing required non-empty key '$_key': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
        fi
    done
    # 'hint' key must exist (may be empty string).
    # We check it exists by verifying _json_valid passes (the key is present even if empty).
    if ! "$_PY" -c "  # popup-safe-env-suppressed
import json, sys
try:
    d = json.loads(sys.argv[1])
    assert 'hint' in d
except Exception:
    raise SystemExit(1)
" "$_line" 2>/dev/null; then
        _fail "test 1b: NDJSON line $_t1_line_num missing 'hint' key: $_line"
        _t1_bad=$(( _t1_bad + 1 ))
    fi

    # Validate status enum.
    _t1_status="$(_json_field "$_line" "status")"
    case "$_t1_status" in
        pass|fail|warn|inconclusive) ;;
        *)
            _fail "test 1c: NDJSON line $_t1_line_num has invalid status '$_t1_status': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
            ;;
    esac

    # Validate severity enum.
    _t1_severity="$(_json_field "$_line" "severity")"
    case "$_t1_severity" in
        hard|advisory) ;;
        *)
            _fail "test 1c: NDJSON line $_t1_line_num has invalid severity '$_t1_severity': $_line"
            _t1_bad=$(( _t1_bad + 1 ))
            ;;
    esac
done <<< "$_t1_ndjson"

if [[ "$_t1_bad" -eq 0 && "$_t1_line_count" -ge 6 ]]; then
    _pass "test 1b/c: all $_t1_line_count NDJSON lines are valid JSON with correct keys and enum values"
fi

# ---------------------------------------------------------------------------
# Test 2: AC2 — exit-code gate (three sub-cases).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: AC2 — exit-code gate ==="

# ---------------------------------------------------------------------------
# Test 2a: Green path — on macOS, --preflight exits 0 (python is healthy).
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 2a: green path (python healthy -> exit 0) ---"

# Review: code-reviewer F3 — guard on host Python >= 3.11; a fresh box without
# Python 3.11+ would FAIL spuriously (target of this feature). Mirror the
# host-dependency guard in test 4 of test_prereq_probe.sh.
_t2a_os="$(uname -s 2>/dev/null)"
if [[ "$_t2a_os" == "Darwin" ]]; then
    # Check host Python version before asserting exit-0.
    _t2a_py_ok=0
    for _pcand in python3 python; do
        if command -v "$_pcand" >/dev/null 2>&1; then
            if "$_pcand" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)' 2>/dev/null; then
                _t2a_py_ok=1
                break
            fi
        fi
    done

    if [[ "$_t2a_py_ok" -eq 0 ]]; then
        echo "NOTE: test 2a skipped — host Python 3.11+ not found (this is the target audience; install Python 3.11+ to run this assertion)"
        _pass "test 2a: skipped (host python < 3.11 — expected on target machines)"
    else
        _t2a_exit=0
        "$_BASH4" "$SETUP_SH" --preflight >/dev/null 2>&1 || _t2a_exit=$?
        if [[ "$_t2a_exit" -eq 0 ]]; then
            _pass "test 2a: --preflight exits 0 on macOS with healthy python"
        else
            _fail "test 2a: --preflight exited $_t2a_exit on macOS — expected 0 (is python 3.11+ installed?)"
        fi
    fi
else
    echo "SKIP: test 2a (macOS-specific green-path assertion skipped on $_t2a_os)"
    _pass "test 2a: skipped on non-macOS platform"
fi

# ---------------------------------------------------------------------------
# Test 2b: Hard-FAIL path — python stub exits 49 (Store-stub mime).
#
# Prepend a temp dir with fake python3/python that exit 49 to PATH, run
# --preflight, assert exit is NON-ZERO (the hard-floor gate fires on python fail).
# PATH is restored via the trap EXIT (and explicitly after the call).
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 2b: hard-FAIL path (python stub exits 49 -> --preflight exits non-zero) ---"

_t2b_dir="$_SCRATCH_DIR/t2b_stub"
mkdir -p "$_t2b_dir"

# Stub mimics the Windows Store App Execution alias: prints the Store error, exits 49.
_make_stub "$_t2b_dir" "python3" "49" "Python was not found; run without arguments to install from the Microsoft Store"
_make_stub "$_t2b_dir" "python"  "49" "Python was not found; run without arguments to install from the Microsoft Store"
# Also stub 'py' (Windows py launcher) to ensure _co_find_python finds no usable interpreter.
_make_stub "$_t2b_dir" "py"      "49" "Python was not found; run without arguments to install from the Microsoft Store"

PATH="$_t2b_dir:$_ORIG_PATH"
_t2b_exit=0
"$_BASH4" "$SETUP_SH" --preflight >/dev/null 2>&1 || _t2b_exit=$?
PATH="$_ORIG_PATH"

if [[ "$_t2b_exit" -ne 0 ]]; then
    _pass "test 2b: --preflight exits non-zero ($_t2b_exit) when python is hard-fail (Store stub exits 49)"
else
    _fail "test 2b: --preflight exited 0 with broken python stub — hard exit gate did not fire"
fi

# ---------------------------------------------------------------------------
# Test 2c: Advisory-does-not-fail — an advisory-only failure does NOT affect
# exit code when python is healthy.
#
# Strategy: shadow 'uv' with a stub that exits 1 (broken uv install).
# The uv probe has severity=advisory, so --preflight should still exit 0
# even though uv fails.
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 2c: advisory failure does NOT fail exit code (uv stub broken, python healthy) ---"

_t2c_dir="$_SCRATCH_DIR/t2c_uv"
mkdir -p "$_t2c_dir"

# Broken uv stub exits 1 and emits nothing.
_make_stub "$_t2c_dir" "uv" "1"

PATH="$_t2c_dir:$_ORIG_PATH"
_t2c_exit=0
"$_BASH4" "$SETUP_SH" --preflight >/dev/null 2>&1 || _t2c_exit=$?
PATH="$_ORIG_PATH"

if [[ "$_t2c_exit" -eq 0 ]]; then
    _pass "test 2c: --preflight exits 0 even when uv advisory probe fails (advisory severity does not fail exit gate)"
else
    _fail "test 2c: --preflight exited $_t2c_exit with broken uv — advisory failure should NOT fail the exit gate"
fi

# ---------------------------------------------------------------------------
# Test 3: AC8 — layout-aware.
#
# Assert --preflight resolves and runs in BOTH layout variants.
#
# Layout 1 (nested working-tree): the current repo — run from coordinator root.
# Layout 2 (flat publish-repo):   construct a temp dir mirroring the flat shape
#   (setup.sh at <flat-root>/scripts/setup.sh; lib/ siblings; docs/ subtree)
#   and run --preflight from there.
#
# Mirrors the test_repo_root_resolution.sh pattern for layout coverage.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: AC8 — layout-aware (nested and flat layouts) ==="

# ---------------------------------------------------------------------------
# Test 3a: Nested working-tree layout (run --preflight from coordinator root).
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 3a: nested layout (run from coordinator root) ---"

_wd="$(pwd)"
cd "$COORDINATOR_ROOT"
_t3a_exit=0
"$_BASH4" "$SETUP_SH" --preflight >/dev/null 2>&1 || _t3a_exit=$?
cd "$_wd"

# Accept exit 0 (all probes pass) or exit 1 (hard fail — e.g. a probe that
# genuinely fails on this machine). What we DO NOT accept: exit 1 due to
# layout resolution failure (which would emit an error message, not NDJSON).
# We check that NDJSON lines were emitted (layout resolved) regardless of the
# exit code of the probes.
_t3a_output=""
cd "$COORDINATOR_ROOT"
_t3a_output="$("$_BASH4" "$SETUP_SH" --preflight 2>&1)" || true
cd "$_wd"

_t3a_ndjson="$(_extract_ndjson_lines "$_t3a_output")"
_t3a_line_count=0
# Review: code-reviewer F4 — guard grep -c . on possibly-empty input (exits 1 under set -euo pipefail)
if [[ -n "$_t3a_ndjson" ]]; then
    _t3a_line_count="$(printf '%s\n' "$_t3a_ndjson" | grep -c . || echo 0)"
fi

if [[ "$_t3a_line_count" -ge 6 ]]; then
    _pass "test 3a: nested layout — --preflight emits >= 6 NDJSON lines (layout resolved, got $_t3a_line_count)"
else
    _fail "test 3a: nested layout — --preflight emitted only $_t3a_line_count NDJSON lines; expected >= 6 (layout may have failed to resolve)"
fi

# ---------------------------------------------------------------------------
# Test 3b: Flat publish-repo layout simulation.
#
# Mirror test_repo_root_resolution.sh Test 2: copy docs/, scripts/, skills/
# subtrees into a temp dir at flat layout positions, then run --preflight
# from the flat root.
#
# The flat layout heuristic in setup.sh:
#   REPO_ROOT = parent of scripts/ directory
# So setup.sh at <flat-root>/scripts/setup.sh resolves REPO_ROOT = <flat-root>.
# The manifest path resolver (_co_resolve_manifest_path) checks:
#   <REPO_ROOT>/docs/install/AGENT.md (flat-layout marker)
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 3b: flat layout (temp-dir simulation) ---"

_t3b_root="$_SCRATCH_DIR/flat-layout"
mkdir -p "$_t3b_root"

_t3b_copy_failed=0
for subtree in docs scripts skills; do
    if [[ -d "${COORDINATOR_ROOT}/${subtree}" ]]; then
        cp -r "${COORDINATOR_ROOT}/${subtree}" "${_t3b_root}/${subtree}"
    else
        _fail "test 3b: flat layout setup — ${COORDINATOR_ROOT}/${subtree} does not exist (required for flat fixture)"
        _t3b_copy_failed=1
    fi
done

if [[ "${_t3b_copy_failed}" -eq 0 ]]; then
    _t3b_setup_sh="${_t3b_root}/scripts/setup.sh"
    if [[ ! -f "$_t3b_setup_sh" ]]; then
        _fail "test 3b: flat layout — scripts/setup.sh not found in flat fixture at $_t3b_setup_sh"
    else
        _wd="$(pwd)"
        cd "$_t3b_root"
        _t3b_stdout=""
        _t3b_stderr=""
        # Review: code-reviewer F6 — capture stdout and stderr separately so we
        # can assert stderr does NOT contain layout-resolution error markers,
        # distinguishing a clean run (zero NDJSON) from a source-failure.
        _t3b_stderr_file="$_SCRATCH_DIR/t3b_stderr.txt"
        _t3b_stdout="$("$_BASH4" scripts/setup.sh --preflight 2>"$_t3b_stderr_file")" || true
        _t3b_stderr="$(cat "$_t3b_stderr_file" 2>/dev/null || true)"
        _t3b_output="$_t3b_stdout"$'\n'"$_t3b_stderr"
        cd "$_wd"

        _t3b_ndjson="$(_extract_ndjson_lines "$_t3b_stdout")"
        _t3b_line_count=0
        # Review: code-reviewer F4 — guard grep -c . on possibly-empty input (exits 1 under set -euo pipefail)
        if [[ -n "$_t3b_ndjson" ]]; then
            _t3b_line_count="$(printf '%s\n' "$_t3b_ndjson" | grep -c . || echo 0)"
        fi

        if [[ "$_t3b_line_count" -ge 6 ]]; then
            _pass "test 3b: flat layout — --preflight emits >= 6 NDJSON lines (layout resolved, got $_t3b_line_count)"
        else
            _fail "test 3b: flat layout — --preflight emitted only $_t3b_line_count NDJSON lines; expected >= 6 (layout may have failed to resolve)"
        fi

        # Review: code-reviewer F6 — assert stderr does NOT contain layout-resolution error markers;
        # distinguishes a clean run from a fixture source-failure. We target shell-level
        # file-access errors (No such file or directory; cannot open; bash: path/to/file:)
        # rather than probe-output "not found" messages (which are legitimate advisory results).
        if echo "$_t3b_stderr" | grep -qiE 'No such file or directory|cannot open|bash: .*: No such file'; then
            _fail "test 3b-stderr: flat layout stderr contains shell file-access errors — layout resolution failure"
        else
            _pass "test 3b-stderr: flat layout stderr contains no shell file-access errors (clean resolution)"
        fi
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
