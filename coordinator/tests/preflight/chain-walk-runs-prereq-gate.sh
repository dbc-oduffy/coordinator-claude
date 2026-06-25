#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# tests/preflight/chain-walk-runs-prereq-gate.sh
#
# Purpose: realizes C3 — chain-walk default body runs the prereq gate.
#
# Tests the CONTRACT that the default setup.sh invocation (no --preflight/--check)
# now runs the prereq gate via _co_run_prereq_gate post-consumer, AND that the
# post-consumer severity-demotion table is applied correctly (gh/node/git/clone_auth
# demoted to advisory; python stays hard).
#
# Test cases:
#   Ta — Default body output includes prereq probe rows (e.g. a git row).
#   Tb — Python is the sole hard gate: post-consumer demotion does NOT demote python.
#        Verified via a focused unit check on the demotion logic in the default body
#        output (python shows as (hard), others show as (advisory)).
#   Tc — gh/node/git/clone_auth absence → advisory-WARN, exit 0 on default body.
#        Simulated by PATH-shadowing gh to a failing stub; default body exits 0
#        with a WARN row, not a [FAIL] row.
#   Td — Identical-exit-code proof: on all-present machine, setup.sh --preflight
#        and default setup.sh both exit 0.
#
# Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md § C3 (AC4)
#
# Cross-platform portability (DR-148):
#   Requires bash >= 4.
#   BSD-portable: no grep -P, no date -d, no sed -i.
#   mktemp -d is BSD-portable.
#
# popup-safe-env-suppressed — python3 calls here are JSON-parsing helpers;
# this test runs on macOS/Linux only (not shipped as a Windows batch script).

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate bash >= 4 and self-re-exec if needed.
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

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Resolve paths.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SETUP_SH="${COORDINATOR_ROOT}/scripts/setup.sh"
LIB_DIR="${COORDINATOR_ROOT}/scripts/lib"
PREREQ_PROBE_SH="${LIB_DIR}/prereq_probe.sh"

if [[ ! -f "${SETUP_SH}" ]]; then
    echo "ERROR: setup.sh not found at ${SETUP_SH}" >&2
    exit 1
fi

if [[ ! -f "${PREREQ_PROBE_SH}" ]]; then
    echo "ERROR: prereq_probe.sh not found at ${PREREQ_PROBE_SH}" >&2
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
# Scratch directory. Cleaned up on exit.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
_ORIG_PATH="$PATH"
trap 'rm -rf "${_SCRATCH_DIR}"; PATH="${_ORIG_PATH}"' EXIT

# ---------------------------------------------------------------------------
# Stub-creation helpers.
# _make_stub <dir> <name> <exit-code> [<stdout>]
# ---------------------------------------------------------------------------
_make_stub() {
    local _dir="$1" _name="$2" _exit_code="$3" _stdout="${4:-}"
    if [[ -n "${_stdout}" ]]; then
        printf '#!/bin/sh\nprintf "%%s\\n" "%s"\nexit %s\n' "${_stdout}" "${_exit_code}" > "${_dir}/${_name}"
    else
        printf '#!/bin/sh\nexit %s\n' "${_exit_code}" > "${_dir}/${_name}"
    fi
    chmod +x "${_dir}/${_name}"
}

# ---------------------------------------------------------------------------
# Build a shadow scripts/ tree with a patched lib dir, mirroring the approach
# in semi-hard-gate.sh. This lets us redirect _LIB_DIR inside setup.sh to our
# patched lib without modifying setup.sh itself.
#
# _build_shadow <target_scripts_dir> <patched_lib_dir>
#   Creates <target_scripts_dir>/setup.sh (copy) + lib → <patched_lib_dir>.
# ---------------------------------------------------------------------------
_RUN_SETUP_COUNT=0

_build_shadow() {
    local _shadow_scripts="$1" _patched_lib="$2"
    mkdir -p "${_shadow_scripts}"
    cp "${SETUP_SH}" "${_shadow_scripts}/setup.sh"
    rm -f "${_shadow_scripts}/lib"
    ln -sf "${_patched_lib}" "${_shadow_scripts}/lib"
}

# ---------------------------------------------------------------------------
# Run default setup.sh (no flags) from a shadow scripts tree.
# Output captured to ${_SCRATCH_DIR}/last_output.txt, rc to last_rc.txt.
# ---------------------------------------------------------------------------
_run_default() {
    local _patched_lib="$1"
    shift
    local _extra_args=("$@")

    _RUN_SETUP_COUNT=$(( _RUN_SETUP_COUNT + 1 ))
    local _shadow_scripts="${_SCRATCH_DIR}/shadow_default_${_RUN_SETUP_COUNT}"
    _build_shadow "${_shadow_scripts}" "${_patched_lib}"

    local _rc=0
    local _out
    _out="$("${_BASH4}" "${_shadow_scripts}/setup.sh" "${_extra_args[@]}" 2>&1)" || _rc=$?

    printf '%s' "${_out}" > "${_SCRATCH_DIR}/last_output.txt"
    echo "${_rc}" > "${_SCRATCH_DIR}/last_rc.txt"
}

# ---------------------------------------------------------------------------
# Run setup.sh --preflight from a shadow scripts tree.
# ---------------------------------------------------------------------------
_run_preflight() {
    local _patched_lib="$1"
    shift
    local _extra_args=("$@")

    _RUN_SETUP_COUNT=$(( _RUN_SETUP_COUNT + 1 ))
    local _shadow_scripts="${_SCRATCH_DIR}/shadow_preflight_${_RUN_SETUP_COUNT}"
    _build_shadow "${_shadow_scripts}" "${_patched_lib}"

    local _rc=0
    local _out
    _out="$("${_BASH4}" "${_shadow_scripts}/setup.sh" --preflight "${_extra_args[@]}" 2>&1)" || _rc=$?

    printf '%s' "${_out}" > "${_SCRATCH_DIR}/last_output.txt"
    echo "${_rc}" > "${_SCRATCH_DIR}/last_rc.txt"
}

_last_output() { cat "${_SCRATCH_DIR}/last_output.txt" 2>/dev/null || true; }
_last_rc()     { cat "${_SCRATCH_DIR}/last_rc.txt"     2>/dev/null || echo "999"; }

# ---------------------------------------------------------------------------
# Build a pass-all patched lib dir (all probes emit pass) with a controlled
# clone_auth row. Used to isolate gate behaviour from live machine state.
#
# _build_pass_all_lib <target_dir>
# ---------------------------------------------------------------------------
_build_pass_all_lib() {
    local _target="$1"
    mkdir -p "${_target}"

    # Symlink all real lib files except prereq_probe.sh.
    for _f in "${LIB_DIR}"/*; do
        local _fname
        _fname="$(basename "${_f}")"
        if [[ "${_fname}" != "prereq_probe.sh" ]]; then
            ln -sf "${_f}" "${_target}/${_fname}"
        fi
    done

    # Write a patched prereq_probe.sh that emits pass for all probes.
    cat > "${_target}/prereq_probe.sh" <<'STUB_EOF'
#!/usr/bin/env bash
# Patched prereq_probe.sh — chain-walk-runs-prereq-gate.sh test stub.
# All probes emit pass with their real (undmoted) severities so we can
# verify demotion by observing the (advisory) label in post-consumer output.

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required." >&2; exit 1
fi

if [[ "${_CO_PREREQ_PROBE_LOADED:-}" == "1" ]]; then return 0 2>/dev/null || true; fi
_CO_PREREQ_PROBE_LOADED=1

_PP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "${_PP_DIR}/step_zero_emit.sh" ]] && source "${_PP_DIR}/step_zero_emit.sh" 2>/dev/null || true
[[ -f "${_PP_DIR}/manifest_reader.sh" ]] && source "${_PP_DIR}/manifest_reader.sh" 2>/dev/null || true

_co_pp_emit() {
    local _name="$1" _status="$2" _severity="$3" _detail="${4:-}" _remediation="${5:-}"
    printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
        "${_name}" "${_status}" "${_severity}" "${_detail}" "${_remediation}"
}

_co_prereq_probe_all() {
    # Emit probes with their REAL (not yet demoted) severities.
    # setup.sh's post-consumer demotion pre-pass will demote gh/node/git/clone_auth.
    _co_pp_emit "git"        "pass" "hard"      "git version 2.x (stub-pass)" ""
    _co_pp_emit "python"     "pass" "hard"      "Python 3.x (stub-pass)" ""
    _co_pp_emit "uv"         "pass" "advisory"  "uv x.y (stub-pass)" ""
    _co_pp_emit "gh"         "pass" "hard"      "gh x.y (stub-pass)" ""
    _co_pp_emit "node"       "pass" "hard"      "node vX (stub-pass)" ""
    _co_pp_emit "pwsh"       "pass" "advisory"  "pwsh x.y (stub-pass)" ""
    _co_pp_emit "ue"         "pass" "advisory"  "UnrealEditor (stub-pass)" ""
    _co_pp_emit "clone_auth" "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "longpaths"  "pass" "advisory"  "n/a (stub-pass)" ""
    _co_pp_emit "git_lfs"    "pass" "advisory"  "git-lfs x.y (stub-pass)" ""
}
STUB_EOF
    chmod +x "${_target}/prereq_probe.sh"
}

# ---------------------------------------------------------------------------
# Build a patched lib where gh emits fail/hard (simulating gh absent in strict
# mode) so we can verify that post-consumer mode demotes it to advisory-WARN.
#
# _build_gh_fail_lib <target_dir>
# ---------------------------------------------------------------------------
_build_gh_fail_lib() {
    local _target="$1"
    mkdir -p "${_target}"

    for _f in "${LIB_DIR}"/*; do
        local _fname
        _fname="$(basename "${_f}")"
        if [[ "${_fname}" != "prereq_probe.sh" ]]; then
            ln -sf "${_f}" "${_target}/${_fname}"
        fi
    done

    cat > "${_target}/prereq_probe.sh" <<'STUB_EOF'
#!/usr/bin/env bash
# Patched prereq_probe.sh — gh absent (fail/hard), all others pass.

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required." >&2; exit 1
fi

if [[ "${_CO_PREREQ_PROBE_LOADED:-}" == "1" ]]; then return 0 2>/dev/null || true; fi
_CO_PREREQ_PROBE_LOADED=1

_PP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "${_PP_DIR}/step_zero_emit.sh" ]] && source "${_PP_DIR}/step_zero_emit.sh" 2>/dev/null || true
[[ -f "${_PP_DIR}/manifest_reader.sh" ]] && source "${_PP_DIR}/manifest_reader.sh" 2>/dev/null || true

_co_pp_emit() {
    local _name="$1" _status="$2" _severity="$3" _detail="${4:-}" _remediation="${5:-}"
    printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
        "${_name}" "${_status}" "${_severity}" "${_detail}" "${_remediation}"
}

_co_prereq_probe_all() {
    _co_pp_emit "git"        "pass" "hard"      "stub-pass" ""
    _co_pp_emit "python"     "pass" "hard"      "stub-pass" ""
    _co_pp_emit "uv"         "pass" "advisory"  "stub-pass" ""
    # gh emits fail/hard — post-consumer demotes to advisory, so it should WARN not FAIL
    _co_pp_emit "gh"         "fail" "hard"      "gh not found (stub)" "install GitHub CLI"
    _co_pp_emit "node"       "pass" "hard"      "stub-pass" ""
    _co_pp_emit "pwsh"       "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "ue"         "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "clone_auth" "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "longpaths"  "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "git_lfs"    "pass" "advisory"  "stub-pass" ""
}
STUB_EOF
    chmod +x "${_target}/prereq_probe.sh"
}

# ===========================================================================
# Ta: Default body output includes prereq probe rows (e.g. a git row).
# ===========================================================================
echo ""
echo "--- Ta: default body output includes prereq probe rows ---"

_ta_lib="${_SCRATCH_DIR}/ta_lib"
_build_pass_all_lib "${_ta_lib}"
_run_default "${_ta_lib}"
_ta_rc="$(_last_rc)"
_ta_out="$(_last_output)"

if [[ "${_ta_rc}" -eq 0 ]]; then
    _pass "Ta: default body exits 0"
else
    _fail "Ta: expected exit 0, got ${_ta_rc}"
fi

# Check for git probe row in output (human-readable stderr merged with stdout).
if printf '%s' "${_ta_out}" | grep -q '"name":"git"\|"id":"git"\|(git)\|git.*hard\|git.*advisory'; then
    _pass "Ta: prereq probe rows present in default body output (git row found)"
else
    _fail "Ta: prereq probe rows NOT found in default body output. Output:\n$(printf '%s' "${_ta_out}" | head -40)"
fi

# Check that the chain-walk banner is still present.
if printf '%s' "${_ta_out}" | grep -q "chain walk complete.*DAG root"; then
    _pass "Ta: chain-walk banner still present"
else
    _fail "Ta: chain-walk banner not found. Output:\n$(printf '%s' "${_ta_out}" | head -40)"
fi

# ===========================================================================
# Tb: Python stays hard in post-consumer mode (demotion does NOT touch python).
#     gh/node/git show as (advisory) in post-consumer output.
# ===========================================================================
echo ""
echo "--- Tb: python stays hard; gh/node/git demoted to advisory in post-consumer ---"

# Reuse Ta's output (pass-all lib, all probes present with real severities from stub).
_tb_out="${_ta_out}"

# python should show as (hard) in the default body output.
# Assert on the precise NDJSON row format setup.sh emits: {"id": "python", ..., "severity": "hard", ...}
# OR the human-readable table format: [PASS]  python  (hard).
# No multi-level fallback — a comment containing "python" and "hard" would satisfy a
# loose grep. We require the line to be either the NDJSON row or the table row.
# Review: code-reviewer slice B — innermost fallback `grep python | grep hard` could
# match a comment or banner line, producing vacuous pass on wrong/missing output.
if printf '%s' "${_tb_out}" | grep -E '"id": "python"' | grep -q '"severity": "hard"'; then
    _pass "Tb: python NDJSON row has severity=hard (post-consumer preserved)"
elif printf '%s' "${_tb_out}" | grep -E '^\s+\[PASS\]\s+python' | grep -q '(hard)'; then
    _pass "Tb: python table row shows (hard) in post-consumer output"
else
    _fail "Tb: python severity=hard NOT found in output. Output:\n$(printf '%s' "${_tb_out}" | head -40)"
fi

# git should show as (advisory) in the default body output (demoted from hard).
# Assert on the NDJSON row {"id": "git", ..., "severity": "advisory"} or table row.
if printf '%s' "${_tb_out}" | grep -E '"id": "git"' | grep -q '"severity": "advisory"'; then
    _pass "Tb: git NDJSON row has severity=advisory (correctly demoted)"
elif printf '%s' "${_tb_out}" | grep -E '^\s+\[PASS\]\s+git\b' | grep -q '(advisory)'; then
    _pass "Tb: git table row shows (advisory) in post-consumer output (correctly demoted)"
else
    _fail "Tb: git NOT shown as advisory in post-consumer. Output:\n$(printf '%s' "${_tb_out}" | grep -E '"id": "git"|\[PASS\].*git' | head -10)"
fi

# gh should show as (advisory) in the default body output (demoted from hard).
# Assert on the NDJSON row {"id": "gh", ..., "severity": "advisory"} or table row.
if printf '%s' "${_tb_out}" | grep -E '"id": "gh"' | grep -q '"severity": "advisory"'; then
    _pass "Tb: gh NDJSON row has severity=advisory (correctly demoted)"
elif printf '%s' "${_tb_out}" | grep -E '^\s+\[PASS\]\s+gh\b' | grep -q '(advisory)'; then
    _pass "Tb: gh table row shows (advisory) in post-consumer output (correctly demoted)"
else
    _fail "Tb: gh NOT shown as advisory in post-consumer. Output:\n$(printf '%s' "${_tb_out}" | grep -E '"id": "gh"|\[PASS\].*gh' | head -10)"
fi

# ===========================================================================
# Tc: gh fail/hard → advisory-WARN in post-consumer, exit 0 (NOT blocked).
# ===========================================================================
echo ""
echo "--- Tc: gh fail/hard emitted → post-consumer demotes to advisory-WARN, exit 0 ---"

_tc_lib="${_SCRATCH_DIR}/tc_lib"
_build_gh_fail_lib "${_tc_lib}"
_run_default "${_tc_lib}"
_tc_rc="$(_last_rc)"
_tc_out="$(_last_output)"

if [[ "${_tc_rc}" -eq 0 ]]; then
    _pass "Tc: exit code is 0 (gh fail/hard demoted to advisory in post-consumer mode)"
else
    _fail "Tc: expected exit 0, got ${_tc_rc}. Output:\n$(printf '%s' "${_tc_out}" | head -30)"
fi

# Should have a [WARN] row for gh (advisory fail renders as WARN), NOT a [FAIL] row.
if printf '%s' "${_tc_out}" | grep -E '\[WARN\].*gh |\[WARN\] gh' > /dev/null 2>&1; then
    _pass "Tc: [WARN] row present for gh (advisory demotion rendered as WARN)"
else
    # NDJSON row check: gh with status=fail but severity=advisory.
    if printf '%s' "${_tc_out}" | grep '"id":"gh"' | grep -q '"status":"fail".*"severity":"advisory"\|"severity":"advisory".*"status":"fail"'; then
        _pass "Tc: gh NDJSON row is fail/advisory (demoted from hard — correct)"
    else
        _fail "Tc: [WARN] row NOT found for gh. Output:\n$(printf '%s' "${_tc_out}" | head -40)"
    fi
fi

# [FAIL] should NOT appear (that would be a hard failure, not advisory).
if printf '%s' "${_tc_out}" | grep -q '\[FAIL\]'; then
    _fail "Tc: unexpected [FAIL] row in post-consumer output (gh should be advisory)"
else
    _pass "Tc: no [FAIL] row (correct — gh demoted to advisory in post-consumer)"
fi

# ===========================================================================
# Td: Identical-exit-code proof — both --preflight and default exit 0 on all-present.
# ===========================================================================
echo ""
echo "--- Td: identical exit code on all-present machine (both should be 0) ---"

_td_lib="${_SCRATCH_DIR}/td_lib"
_build_pass_all_lib "${_td_lib}"

_run_preflight "${_td_lib}"
_td_pf_rc="$(_last_rc)"

_run_default "${_td_lib}"
_td_def_rc="$(_last_rc)"

if [[ "${_td_pf_rc}" -eq 0 ]]; then
    _pass "Td: setup.sh --preflight exits 0 on all-present machine"
else
    _fail "Td: setup.sh --preflight exited ${_td_pf_rc} (expected 0)"
fi

if [[ "${_td_def_rc}" -eq 0 ]]; then
    _pass "Td: setup.sh (default) exits 0 on all-present machine"
else
    _fail "Td: setup.sh (default) exited ${_td_def_rc} (expected 0)"
fi

if [[ "${_td_pf_rc}" -eq "${_td_def_rc}" ]]; then
    _pass "Td: both exit codes match (${_td_pf_rc} == ${_td_def_rc}) — gate mechanism is shared"
else
    _fail "Td: exit codes differ (--preflight=${_td_pf_rc}, default=${_td_def_rc}) — gate may be forked"
fi

# ===========================================================================
# Summary.
# ===========================================================================
echo ""
echo "========================================"
echo "  chain-walk-runs-prereq-gate.sh results"
echo "========================================"
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
if [[ "${#ERRORS[@]}" -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _e in "${ERRORS[@]}"; do
        echo "  ${_e}"
    done
fi
echo "========================================"
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
