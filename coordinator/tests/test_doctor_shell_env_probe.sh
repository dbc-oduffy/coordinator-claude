#!/usr/bin/env bash
# tests/test_doctor_shell_env_probe.sh — behavioral tests for the P-17 bash login-shell orphan probe.
#
# Purpose: verify that coordinator-doctor-sentinel.sh fires P-17 correctly:
#   - RED when _co_probe_shell_login_env returns "fail" (orphaned bash login shell).
#   - GREEN (not RED) when the probe returns "pass" (healthy login shell).
#   - Silent skip (not RED) when the probe returns "inconclusive".
#   - Manifest SSOT still green with the P-17 row (P-17 consistently registered).
#
# Spec backlink: docs/plans/2026-06-25-phase-zero-macos-bash-login-shell-provisioning.md § C7c
# Review: code-reviewer F9 — prior backlink was a fabricated non-existent path; corrected to the real plan.
# Sentinel SSOT: bin/coordinator-doctor-sentinel.sh § P-17
# Prereq SSOT:   scripts/lib/prereq_probe.sh (_co_probe_shell_login_env)
#
# Test strategy: inject a fake prereq_probe.sh via COORDINATOR_PREREQ_PROBE_LIB_DIR
# that provides a controlled _co_probe_shell_login_env returning "fail", "pass", or
# "inconclusive", then invoke bin/coordinator-doctor-sentinel.sh --probe P-17 and
# assert the verdict token in its stdout. This exercises the real P-17 sentinel block
# including the fail->note_red mapping and the inconclusive->silent-skip path.
#
# Run: bash tests/test_doctor_shell_env_probe.sh
# (from any directory — script resolves its own location)
#
# Exit codes:
#   0  All cases PASS
#   1  One or more cases FAIL
#
# BSD-portable: no grep -P, no sed -i, no date -d. Requires bash >= 4.
# Cross-platform portability (DR-148, cross-platform-shell-portability.md).

set -euo pipefail
# Review: code-reviewer F10 — added -e; missing -e meant intentional failures were not caught.

# ---------------------------------------------------------------------------
# Locate a real bash >= 4.  Self-re-exec under it if needed.
# (Stock macOS /bin/bash is 3.2 — would produce false failures or vacuous passes.)
# Review: code-reviewer F2 — added bash-4 detection + self-re-exec block to match siblings.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="${SCRIPT_DIR}/.."
SENTINEL="${COORDINATOR_ROOT}/bin/coordinator-doctor-sentinel.sh"
MANIFEST_SSOT_TEST="${COORDINATOR_ROOT}/bin/tests/test-doctor-manifest-ssot.sh"

# ---------------------------------------------------------------------------
# Guard: required files must exist
# ---------------------------------------------------------------------------

for _f in "$SENTINEL" "$MANIFEST_SSOT_TEST"; do
  if [[ ! -f "$_f" ]]; then
    echo "FATAL: required file not found: $_f" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# ---------------------------------------------------------------------------
# _build_fake_lib <dir> <probe-status>
#
# Writes a minimal prereq_probe.sh stub into <dir> that provides:
#   _co_probe_shell_login_env — returns controlled NDJSON with given status.
#   _co_pp_emit               — minimal NDJSON emitter (the real lib sources
#                               step_zero_emit.sh for this; the fake is standalone).
#
# probe-status values: fail | pass | inconclusive
# ---------------------------------------------------------------------------

_build_fake_lib() {
  local _dir="$1"
  local _probe_status="$2"
  mkdir -p "$_dir"

  # Resolve controlled detail strings. Keep them free of shell metacharacters
  # so they survive interpolation into the heredoc without quoting complexity.
  local _detail _remediation
  case "$_probe_status" in
    fail)
      _detail="bash login shell: local-bin absent from fresh login PATH"
      _remediation="run coordinator:install or normalize-env.sh to reconstruct bash profile"
      ;;
    pass)
      _detail="bash login shell: local-bin present in PATH and claude resolves"
      _remediation=""
      ;;
    inconclusive)
      _detail="could not probe login shell PATH - shell returned empty"
      _remediation=""
      ;;
    *)
      echo "FATAL: _build_fake_lib: unknown probe-status '${_probe_status}'" >&2
      return 1
      ;;
  esac

  # The heredoc is unquoted so outer-shell variables ($_probe_status, $_detail,
  # $_remediation) are expanded into the written file. Inner-shell references
  # in function bodies use \$ to become literal $ in the written file.
  cat > "$_dir/prereq_probe.sh" <<FAKE_PREREQ
#!/usr/bin/env bash
# Fake prereq_probe.sh for test_doctor_shell_env_probe.sh
# Status baked in at write time: ${_probe_status}

# Idempotency guard (matches real prereq_probe.sh contract).
_CO_PREREQ_PROBE_LOADED="\${_CO_PREREQ_PROBE_LOADED:-0}"
if [[ "\$_CO_PREREQ_PROBE_LOADED" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_CO_PREREQ_PROBE_LOADED=1

# Minimal NDJSON emitter — mirrors _co_pp_emit from scripts/lib/step_zero_emit.sh.
_co_pp_emit() {
  printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
    "\$1" "\$2" "\$3" "\$4" "\$5"
}

# Controlled probe: always returns the status baked in at write time.
_co_probe_shell_login_env() {
  _co_pp_emit "shell_login_env" "${_probe_status}" "advisory" \
    "${_detail}" "${_remediation}"
}

# Stub aggregator so P-15 (if ever co-selected) doesn't fail on missing symbols.
_co_prereq_probe_all() {
  _co_probe_shell_login_env
}
FAKE_PREREQ
}

# ---------------------------------------------------------------------------
# _run_p17_with_status <probe-status>
#
# Builds a fake prereq_probe.sh for the given status, runs the real sentinel
# with --probe P-17, and captures stdout+stderr into _probe_out.
# The sentinel's --probe mode always exits 0 (verdict is in stdout).
# ---------------------------------------------------------------------------

_run_p17_with_status() {
  local _st="$1"
  local _fake_lib_dir _tmpdir
  _fake_lib_dir="$(mktemp -d)"
  _tmpdir="$(mktemp -d)"
  mkdir -p "$_tmpdir/plugins/coordinator-claude/data"

  _build_fake_lib "$_fake_lib_dir" "$_st"

  _probe_out="$(
    CLAUDE_HOME="$_tmpdir" \
    COORDINATOR_PLUGINS_ROOT="$_tmpdir/plugins" \
    COORDINATOR_PREREQ_PROBE_LIB_DIR="$_fake_lib_dir" \
    "$_BASH4" "$SENTINEL" --probe P-17 2>&1
  )" || true
  # Review: code-reviewer F2 — replaced bare bash with $_BASH4 (stock macOS bash is 3.2)

  rm -rf "$_fake_lib_dir" "$_tmpdir"
}

# ---------------------------------------------------------------------------
# Section 1 — Syntax check
# ---------------------------------------------------------------------------

echo ""
echo "--- Section 1: bash -n syntax check on sentinel"

# Review: code-reviewer F2 — replaced bare bash with $_BASH4; also fixed set -e interaction:
# the original pattern captured $? AFTER assignment but with set -e the script would abort
# before reaching the check. Use || bash_n_rc=$? to capture exit code safely under set -e.
bash_n_rc=0
bash_n_out="$("$_BASH4" -n "$SENTINEL" 2>&1)" || bash_n_rc=$?
if [[ $bash_n_rc -eq 0 ]]; then
  pass "1a: bash -n passes on coordinator-doctor-sentinel.sh"
else
  fail "1a: bash -n failed on coordinator-doctor-sentinel.sh: $bash_n_out"
fi

# ---------------------------------------------------------------------------
# Section 2 — Orphaned bash login shell → P-17 RED
#
# When _co_probe_shell_login_env returns "fail", the P-17 block fires note_red,
# which causes the sentinel to emit verdict=RED (fail→note_red is the contract).
# ---------------------------------------------------------------------------

echo ""
echo "--- Section 2: orphaned bash login shell (probe=fail) → verdict=RED for P-17"

_run_p17_with_status "fail"

# The sentinel emits "All selected probes passed." only on GREEN — must NOT appear.
if echo "$_probe_out" | grep -q "All selected probes passed"; then
  fail "2a: P-17 reported 'All selected probes passed' despite probe returning fail (vacuous GREEN)"
else
  pass "2a: P-17 did not report vacuous GREEN on orphan-fail probe result"
fi

# The sentinel emits "[coordinator-doctor] MODE=probe verdict=RED" when note_red fired.
if echo "$_probe_out" | grep -q "verdict=RED"; then
  pass "2b: P-17 surfaces verdict=RED when bash login shell is orphaned (probe=fail -> note_red)"
else
  fail "2b: P-17 did not emit verdict=RED on orphaned bash login shell (output: '$_probe_out')"
fi

# ---------------------------------------------------------------------------
# Section 3 — Healthy login shell → P-17 GREEN (not RED)
#
# When _co_probe_shell_login_env returns "pass", the P-17 block takes the
# pass|* branch (no action) so no note_red fires and verdict=GREEN is emitted.
# ---------------------------------------------------------------------------

echo ""
echo "--- Section 3: healthy login shell (probe=pass) → verdict=GREEN for P-17"

_run_p17_with_status "pass"

if echo "$_probe_out" | grep -q "verdict=RED"; then
  fail "3a: P-17 emitted RED on a healthy (pass) login shell probe result"
else
  pass "3a: P-17 did not emit RED on healthy login shell"
fi

# Assert the positive GREEN token — absence of RED could mask a probe-not-ran failure.
if echo "$_probe_out" | grep -q "verdict=GREEN"; then
  pass "3b: P-17 reports verdict=GREEN when login shell is healthy"
else
  fail "3b: P-17 did not emit verdict=GREEN on healthy login shell (output: '$_probe_out')"
fi

# ---------------------------------------------------------------------------
# Section 4 — Inconclusive login shell probe → P-17 silent skip (not RED)
#
# When _co_probe_shell_login_env returns "inconclusive", the P-17 block
# falls into the inconclusive branch which is a silent skip (no note call).
# Neither RED nor AMBER is expected; the sentinel emits verdict=GREEN.
# ---------------------------------------------------------------------------

echo ""
echo "--- Section 4: inconclusive login shell probe → P-17 silent skip (not RED)"

_run_p17_with_status "inconclusive"

if echo "$_probe_out" | grep -q "verdict=RED"; then
  fail "4a: P-17 emitted RED on inconclusive probe result (must silently skip)"
else
  pass "4a: P-17 did not emit RED on inconclusive probe result (silent skip confirmed)"
fi

if echo "$_probe_out" | grep -q "verdict=AMBER"; then
  fail "4b: P-17 emitted AMBER on inconclusive probe result (sentinel spec says silent skip)"
else
  pass "4b: P-17 did not emit AMBER on inconclusive probe result"
fi

# ---------------------------------------------------------------------------
# Section 5 — Manifest SSOT: P-17 row consistent across manifest + wiki catalog
#
# Invokes test-doctor-manifest-ssot.sh (already tests bijection and severity
# agreement for all probes including P-17) and asserts it exits 0.
# ---------------------------------------------------------------------------

echo ""
echo "--- Section 5: manifest SSOT green with P-17 row"

_ssot_exit=0
"$_BASH4" "$MANIFEST_SSOT_TEST" >/dev/null 2>&1 || _ssot_exit=$?
# Review: code-reviewer F2 — replaced bare bash with $_BASH4

if [[ "$_ssot_exit" -eq 0 ]]; then
  pass "5a: test-doctor-manifest-ssot.sh exits 0 (P-17 consistently registered in manifest + wiki catalog)"
else
  fail "5a: test-doctor-manifest-ssot.sh exited ${_ssot_exit} — P-17 may be missing from wiki catalog or manifest (run it directly to diagnose)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================"
echo "  Results: $((PASS + FAIL)) total   $PASS passed, $FAIL failed"
echo "============================================"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
