#!/usr/bin/env bash
# tests/preflight/semi-hard-gate.sh
#
# Purpose: realizes AC2 — semi-hard gate + --accept-no-git-auth.
#
# Tests the CONTRACT that a semi-hard severity clone_auth warn row drives exit 94
# from setup.sh --preflight, and that --accept-no-git-auth suppresses it.
# The probe itself (prereq_probe.sh § _co_probe_clone_auth) is edited by a
# concurrent C1 executor; this test stubs at the prereq_probe.sh level so it
# remains correct regardless of which clone_auth probe implementation is live,
# as long as the emit contract ({name,status,severity,...} NDJSON) holds.
#
# Test cases:
#   T1 — PATH-stubbed: no git-host auth available → exit 94 + [BLOCK] row present.
#   T2 — --accept-no-git-auth: same stub → exit 0 + override log line on stderr.
#   T3 — auth present (stub gh auth status exit 0) → exit 0 + no [BLOCK] row.
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md §7 C2
# Spec backlink: docs/wiki/agent-install-contract.md § Exit code table (code 94)
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
# _make_stub_with_stderr <dir> <name> <exit-code> <stderr-text>
# ---------------------------------------------------------------------------
_make_stub_with_stderr() {
    local _dir="$1" _name="$2" _exit_code="$3" _stderr="${4:-}"
    printf '#!/bin/sh\nprintf "%%s\\n" "%s" >&2\nexit %s\n' "${_stderr}" "${_exit_code}" > "${_dir}/${_name}"
    chmod +x "${_dir}/${_name}"
}

# ---------------------------------------------------------------------------
# Run setup.sh --preflight with a stubbed prereq_probe.sh injected via PATH.
#
# Strategy: prereq_probe.sh is SOURCED by setup.sh; we cannot override it via
# PATH. Instead we create a temporary replacement file that sources the real
# prereq_probe.sh but then overrides _co_probe_clone_auth with our stub body.
# setup.sh sources from _LIB_DIR (the scripts/lib/ path determined at startup),
# so we need to inject at the file level, not PATH.
#
# We use a tmpdir overlay: copy all lib files into a tmp lib dir, then replace
# prereq_probe.sh with our patched version. We then patch REPO_ROOT to point
# at a mirror that has scripts/lib → our tmp lib dir, by writing a minimal
# wrapper setup.sh in the scratch dir.
#
# Simpler approach: prereq_probe.sh sources step_zero_emit.sh and
# manifest_reader.sh by name from its own dir (SCRIPT_DIR). We create a
# parallel lib dir under scratch, symlink/copy everything, then replace
# prereq_probe.sh in that parallel lib. Then we source the modified file.
#
# Since setup.sh hard-computes _LIB_DIR = "${SCRIPT_DIR}/lib" from BASH_SOURCE,
# we cannot redirect it via env. The cleanest approach is to invoke a small
# wrapper script that sources the patched prereq_probe into the environment
# and then sets _co_prereq_probe_all to emit our controlled NDJSON.
#
# ACTUAL APPROACH: inject via a wrapper prereq_probe.sh in a parallel lib dir,
# then run setup.sh with a symlinked scripts/ tree where lib → our patched dir.
# This avoids any setup.sh edits and is purely additive.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Build the parallel lib dir with a patched prereq_probe.sh for a given
# clone_auth scenario. Returns the path to the parallel lib dir.
#
# _build_patched_lib <target_dir> <clone_auth_status> <clone_auth_severity>
#   clone_auth_status:   pass | warn | fail | inconclusive
#   clone_auth_severity: advisory | semi-hard
# ---------------------------------------------------------------------------
_build_patched_lib() {
    local _target="$1"
    local _ca_status="$2"
    local _ca_severity="$3"

    mkdir -p "${_target}"

    # Symlink all real lib files into the patched lib dir.
    for _f in "${LIB_DIR}"/*; do
        local _fname
        _fname="$(basename "${_f}")"
        if [[ "${_fname}" != "prereq_probe.sh" ]]; then
            ln -sf "${_f}" "${_target}/${_fname}"
        fi
    done

    # Write a patched prereq_probe.sh that sources the real one (for all other
    # probes) but overrides _co_probe_clone_auth and _co_prereq_probe_all so
    # only our controlled clone_auth NDJSON line is emitted. This isolates the
    # gate contract test from live machine state (gh auth, network, etc.).
    #
    # _co_prereq_probe_all override: emit ONE clone_auth NDJSON line only.
    # All other probes are suppressed so they do not drive _PF_HARD_FAIL
    # (e.g. python failing on a machine with no Python would mask our 94 test).
    # The real python probe carries severity=hard; we emit a synthetic pass row
    # so the hard-fail gate never fires and we can test 94 isolation cleanly.
    cat > "${_target}/prereq_probe.sh" <<STUB_EOF
#!/usr/bin/env bash
# Patched prereq_probe.sh — semi-hard-gate.sh test stub.
# Sources the real lib but overrides _co_prereq_probe_all to emit controlled NDJSON.

# Bash version guard (must parse on 3.2).
if [[ "\${BASH_VERSINFO[0]}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required." >&2; exit 1
fi

# Idempotency guard (matches the real prereq_probe.sh pattern).
if [[ "\${_CO_PREREQ_PROBE_LOADED:-}" == "1" ]]; then return 0 2>/dev/null || true; fi
_CO_PREREQ_PROBE_LOADED=1

# Source siblings from THIS file's dir (same as real prereq_probe.sh).
_PP_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
# step_zero_emit.sh and manifest_reader.sh may or may not exist; guard.
[[ -f "\${_PP_DIR}/step_zero_emit.sh" ]] && source "\${_PP_DIR}/step_zero_emit.sh" 2>/dev/null || true
[[ -f "\${_PP_DIR}/manifest_reader.sh" ]] && source "\${_PP_DIR}/manifest_reader.sh" 2>/dev/null || true

# _co_pp_emit: emit one NDJSON prereq probe line to stdout.
_co_pp_emit() {
    local _name="\$1" _status="\$2" _severity="\$3" _detail="\${4:-}" _remediation="\${5:-}"
    printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \\
        "\${_name}" "\${_status}" "\${_severity}" "\${_detail}" "\${_remediation}"
}

# Override aggregator: emit synthetic pass rows for all hard probes (so
# _PF_HARD_FAIL never fires), then the controlled clone_auth row.
_co_prereq_probe_all() {
    # Synthetic pass rows for hard probes (python, gh, node).
    _co_pp_emit "python"     "pass" "hard"      "stub-pass" ""
    _co_pp_emit "gh"         "pass" "hard"      "stub-pass" ""
    _co_pp_emit "node"       "pass" "hard"      "stub-pass" ""
    # Advisory pass rows (uv, pwsh, ue, longpaths).
    _co_pp_emit "uv"         "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "pwsh"       "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "ue"         "pass" "advisory"  "stub-pass" ""
    _co_pp_emit "longpaths"  "pass" "advisory"  "stub-pass" ""
    # Controlled clone_auth row — severity and status from test scenario.
    _co_pp_emit "clone_auth" "${_ca_status}" "${_ca_severity}" \\
        "git-host auth not verified (stub)" \\
        "gh auth login OR re-run with --accept-no-git-auth"
}

# Individual probe stubs (no-ops — only _co_prereq_probe_all is called by setup.sh).
_co_probe_python()     { _co_pp_emit "python"    "pass" "hard"     "stub" ""; }
_co_probe_uv()         { _co_pp_emit "uv"        "pass" "advisory" "stub" ""; }
_co_probe_gh()         { _co_pp_emit "gh"        "pass" "hard"     "stub" ""; }
_co_probe_node()       { _co_pp_emit "node"      "pass" "hard"     "stub" ""; }
_co_probe_pwsh()       { _co_pp_emit "pwsh"      "pass" "advisory" "stub" ""; }
_co_probe_ue()         { _co_pp_emit "ue"        "pass" "advisory" "stub" ""; }
_co_probe_clone_auth() { _co_pp_emit "clone_auth" "${_ca_status}" "${_ca_severity}" "stub" ""; }
_co_probe_longpaths()  { _co_pp_emit "longpaths" "pass" "advisory" "stub" ""; }
STUB_EOF
    # Review: review-integrator F7 — the heredoc above is unquoted (STUB_EOF, not 'STUB_EOF'),
    # so ${_ca_status} and ${_ca_severity} are already expanded at write-time by the shell.
    # The subsequent sed substitution is a no-op and is removed. chmod only.
    chmod +x "${_target}/prereq_probe.sh"
}

# ---------------------------------------------------------------------------
# Run setup.sh --preflight with a patched lib dir.
#
# We cannot redirect _LIB_DIR (computed at setup.sh startup from BASH_SOURCE).
# Workaround: create a minimal scripts/ shadow tree under scratch that has our
# patched lib/ dir, and invoke setup.sh from there by creating a thin wrapper
# that tweaks _LIB_DIR before sourcing the real setup.sh internals.
#
# Cleaner approach: since setup.sh uses _LIB_DIR="${SCRIPT_DIR}/lib" and
# SCRIPT_DIR is computed from BASH_SOURCE[0], we can make BASH_SOURCE[0]
# point at a copy of setup.sh in a shadow scripts/ that has our patched lib/.
#
# _run_preflight <patched_lib_dir> [extra_args...]
#   Runs setup.sh --preflight with the patched lib as scripts/lib.
#   Captures combined stdout+stderr. Returns exit code.
# ---------------------------------------------------------------------------
_RUN_PREFLIGHT_COUNT=0

_run_preflight() {
    local _patched_lib="$1"
    shift
    local _extra_args=("$@")

    # Build a shadow scripts/ dir: copy setup.sh there, symlink patched lib.
    # Use a unique dir per call (counter-based) — ln -sf on macOS does NOT
    # replace an existing directory symlink; a fresh dir avoids stale-symlink pollution.
    _RUN_PREFLIGHT_COUNT=$(( _RUN_PREFLIGHT_COUNT + 1 ))
    local _shadow_scripts="${_SCRATCH_DIR}/shadow_scripts_${_RUN_PREFLIGHT_COUNT}"
    mkdir -p "${_shadow_scripts}"
    cp "${SETUP_SH}" "${_shadow_scripts}/setup.sh"
    # Remove any pre-existing lib symlink before re-linking (BSD ln -sf does not
    # replace an existing symlink-to-directory; it would nest inside instead).
    rm -f "${_shadow_scripts}/lib"
    ln -sf "${_patched_lib}" "${_shadow_scripts}/lib"

    # Run the shadow setup.sh. It will compute _LIB_DIR = shadow_scripts/lib.
    # Capture stderr + stdout combined for assertion.
    # set -e is active in outer script; subshell failure is expected in some tests.
    local _rc=0
    local _out
    _out="$("${_BASH4}" "${_shadow_scripts}/setup.sh" --preflight "${_extra_args[@]}" 2>&1)" || _rc=$?

    # Return the output via a temp file (avoids subshell variable scope issues).
    printf '%s' "${_out}" > "${_SCRATCH_DIR}/last_output.txt"
    echo "${_rc}" > "${_SCRATCH_DIR}/last_rc.txt"
}

_last_output() { cat "${_SCRATCH_DIR}/last_output.txt" 2>/dev/null || true; }
_last_rc()     { cat "${_SCRATCH_DIR}/last_rc.txt"     2>/dev/null || echo "999"; }

# ---------------------------------------------------------------------------
# T1: no git-host auth (semi-hard warn) → exit 94 + [BLOCK] row present.
# ---------------------------------------------------------------------------
echo ""
echo "--- T1: semi-hard clone_auth warn → expect exit 94 + [BLOCK] row ---"

_t1_lib="${_SCRATCH_DIR}/t1_lib"
_build_patched_lib "${_t1_lib}" "warn" "semi-hard"
_run_preflight "${_t1_lib}"
_t1_rc="$(_last_rc)"
_t1_out="$(_last_output)"

if [[ "${_t1_rc}" -eq 94 ]]; then
    _pass "T1: exit code is 94 (semi-hard unverified)"
else
    _fail "T1: expected exit 94, got ${_t1_rc}"
fi

if printf '%s' "${_t1_out}" | grep -q '\[BLOCK\]'; then
    _pass "T1: [BLOCK] row present in output"
else
    _fail "T1: [BLOCK] row NOT found in output. Output was: $(printf '%s' "${_t1_out}" | head -30)"
fi

# [FAIL] should NOT appear (that would be a hard failure, not semi-hard).
if printf '%s' "${_t1_out}" | grep -q '\[FAIL\]'; then
    _fail "T1: unexpected [FAIL] row (should be [BLOCK] for semi-hard)"
else
    _pass "T1: no [FAIL] row (correct — semi-hard uses [BLOCK])"
fi

# ---------------------------------------------------------------------------
# T2: --accept-no-git-auth: same stub → exit 0 + override log line on stderr.
# ---------------------------------------------------------------------------
echo ""
echo "--- T2: --accept-no-git-auth with semi-hard clone_auth warn → expect exit 0 + override log ---"

_t2_lib="${_SCRATCH_DIR}/t2_lib"
_build_patched_lib "${_t2_lib}" "warn" "semi-hard"
_run_preflight "${_t2_lib}" "--accept-no-git-auth"
_t2_rc="$(_last_rc)"
_t2_out="$(_last_output)"

if [[ "${_t2_rc}" -eq 0 ]]; then
    _pass "T2: exit code is 0 (--accept-no-git-auth suppressed semi-hard)"
else
    _fail "T2: expected exit 0, got ${_t2_rc}. Output: $(printf '%s' "${_t2_out}" | head -30)"
fi

if printf '%s' "${_t2_out}" | grep -q "proceeding without verified git-host auth"; then
    # Review: review-integrator F9 — strengthen assertion to match the full phrase emitted by
    # setup.sh; 'accept-no-git-auth' is a substring of the flag itself, not the log message.
    _pass "T2: override log line present ('proceeding without verified git-host auth' found)"
else
    _fail "T2: override log line NOT found. Output: $(printf '%s' "${_t2_out}" | head -30)"
fi

# ---------------------------------------------------------------------------
# T3: auth present (advisory clone_auth pass) → exit 0 + no [BLOCK] row.
# ---------------------------------------------------------------------------
echo ""
echo "--- T3: advisory clone_auth pass (auth present) → expect exit 0 + no [BLOCK] row ---"

_t3_lib="${_SCRATCH_DIR}/t3_lib"
_build_patched_lib "${_t3_lib}" "pass" "advisory"
_run_preflight "${_t3_lib}"
_t3_rc="$(_last_rc)"
_t3_out="$(_last_output)"

if [[ "${_t3_rc}" -eq 0 ]]; then
    _pass "T3: exit code is 0 (no semi-hard failure)"
else
    _fail "T3: expected exit 0, got ${_t3_rc}. Output: $(printf '%s' "${_t3_out}" | head -30)"
fi

if printf '%s' "${_t3_out}" | grep -q '\[BLOCK\]'; then
    _fail "T3: unexpected [BLOCK] row in output (should not appear when auth passes)"
else
    _pass "T3: no [BLOCK] row (correct — advisory pass does not block)"
fi

# ---------------------------------------------------------------------------
# T4: semi-hard clone_auth fail (not just warn) → exit 94 + [BLOCK] row.
# ---------------------------------------------------------------------------
echo ""
echo "--- T4: semi-hard clone_auth FAIL → expect exit 94 + [BLOCK] row ---"

_t4_lib="${_SCRATCH_DIR}/t4_lib"
_build_patched_lib "${_t4_lib}" "fail" "semi-hard"
_run_preflight "${_t4_lib}"
_t4_rc="$(_last_rc)"
_t4_out="$(_last_output)"

if [[ "${_t4_rc}" -eq 94 ]]; then
    _pass "T4: exit code is 94 (semi-hard fail also drives exit 94)"
else
    _fail "T4: expected exit 94, got ${_t4_rc}"
fi

if printf '%s' "${_t4_out}" | grep -q '\[BLOCK\]'; then
    _pass "T4: [BLOCK] row present for semi-hard fail"
else
    _fail "T4: [BLOCK] row NOT found for semi-hard fail"
fi

# ---------------------------------------------------------------------------
# T5: --accept-no-git-auth with semi-hard fail → exit 0.
# ---------------------------------------------------------------------------
echo ""
echo "--- T5: --accept-no-git-auth with semi-hard clone_auth FAIL → expect exit 0 ---"

_t5_lib="${_SCRATCH_DIR}/t5_lib"
_build_patched_lib "${_t5_lib}" "fail" "semi-hard"
_run_preflight "${_t5_lib}" "--accept-no-git-auth"
_t5_rc="$(_last_rc)"
_t5_out="$(_last_output)"

if [[ "${_t5_rc}" -eq 0 ]]; then
    _pass "T5: exit code is 0 (--accept-no-git-auth suppresses semi-hard fail)"
else
    _fail "T5: expected exit 0, got ${_t5_rc}"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  semi-hard-gate.sh results"
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

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
