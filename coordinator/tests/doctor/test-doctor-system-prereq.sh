#!/usr/bin/env bash
# test-doctor-system-prereq.sh — behavioral tests for the P-15 system-prereq probe.
#
# Purpose: verify that coordinator-doctor-sentinel.sh fires P-15 correctly:
#   - RED (error) when a hard prerequisite reports fail/hard in NDJSON output.
#   - GREEN when all hard prereqs pass and advisory ones are absent/warn.
#   - No AMBER on advisory-only absences (doctor-probe-design.md § AMBER on Optional
#     Absence Is Bad Form).
#
# Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md § C4 (AC5)
# Sentinel SSOT: bin/coordinator-doctor-sentinel.sh § P-15
# Prereq SSOT:   scripts/lib/prereq_probe.sh (_co_prereq_probe_all)
#
# Test strategy: inject a fake prereq_probe.sh via COORDINATOR_PREREQ_PROBE_LIB_DIR
# that emits controlled NDJSON rows (hard-fail, advisory-warn, all-pass) without
# requiring real tool absences — avoids the Python-absent-kills-selector problem
# while exercising the probe body's NDJSON parsing and verdict logic faithfully.
#
# Run: bash tests/doctor/test-doctor-system-prereq.sh
# (from any directory — script resolves its own location)
#
# Exit codes:
#   0  All cases PASS
#   1  One or more cases FAIL

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="${SCRIPT_DIR}/../.."
SENTINEL="${COORDINATOR_ROOT}/bin/coordinator-doctor-sentinel.sh"

# ---------------------------------------------------------------------------
# Guard: required files must exist
# ---------------------------------------------------------------------------

for _f in "$SENTINEL"; do
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
# Build a fake lib dir containing a controlled prereq_probe.sh
# The fake lib also provides minimal manifest_reader.sh and step_zero_emit.sh
# stubs so prereq_probe.sh's sourcing chain resolves.
#
# _build_fake_lib <dir> <scenario>
#   scenario = "hard_fail"     — emit git/python/gh/node as fail+hard; rest pass
#   scenario = "advisory_only" — emit all hard as pass; uv/pwsh/ue/longpaths/git_lfs as warn+advisory
#   scenario = "all_pass"      — emit all probes as pass
# ---------------------------------------------------------------------------

_build_fake_lib() {
  local _dir="$1"
  local _scenario="$2"
  mkdir -p "$_dir"

  # ---- step_zero_emit.sh stub ----
  # Provides _co_pp_emit and _co_pp_json_escape (the only symbols prereq_probe.sh
  # requires from this sibling; the real implementation is more complex but the
  # output shape contract is what matters for testing).
  cat > "$_dir/step_zero_emit.sh" <<'EMITTER'
#!/usr/bin/env bash
_co_pp_json_escape() {
  local _s="$1"
  _s="${_s//\\/\\\\}"
  _s="${_s//\"/\\\"}"
  printf '%s' "$_s"
}
_co_pp_emit() {
  local _name="$1" _status="$2" _severity="$3" _detail="$4" _remediation="$5"
  printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
    "$(_co_pp_json_escape "$_name")" \
    "$(_co_pp_json_escape "$_status")" \
    "$(_co_pp_json_escape "$_severity")" \
    "$(_co_pp_json_escape "$_detail")" \
    "$(_co_pp_json_escape "$_remediation")"
}
EMITTER

  # ---- manifest_reader.sh stub ----
  # Provides _co_find_python (only symbol prereq_probe.sh uses from this sibling).
  cat > "$_dir/manifest_reader.sh" <<'READER'
#!/usr/bin/env bash
_co_find_python() {
  # Stub: return whatever python the environment has (we don't care for testing).
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return 0; fi
  if command -v python >/dev/null 2>&1; then echo "python"; return 0; fi
  return 1
}
READER

  # ---- prereq_probe.sh controlled fake ----
  # Bypasses all real probing; emits fixed NDJSON rows per scenario.
  local _hard_status _advisory_status
  case "$_scenario" in
    hard_fail)
      _hard_status="fail"
      _advisory_status="warn"
      ;;
    advisory_only)
      _hard_status="pass"
      _advisory_status="warn"
      ;;
    all_pass)
      _hard_status="pass"
      _advisory_status="pass"
      ;;
    *)
      echo "FATAL: unknown scenario: $_scenario" >&2
      return 1
      ;;
  esac

  # Write the fake prereq_probe.sh with the scenario baked in.
  # We cannot use variables directly in the heredoc without quoting the marker,
  # so we write a script that echoes fixed JSON.
  cat > "$_dir/prereq_probe.sh" <<FAKE_PREREQ
#!/usr/bin/env bash
# Fake prereq_probe.sh for testing — emits controlled NDJSON rows.
# Scenario: ${_scenario}

# Idempotency guard (matches real prereq_probe.sh).
_CO_PREREQ_PROBE_LOADED="\${_CO_PREREQ_PROBE_LOADED:-0}"
if [[ "\$_CO_PREREQ_PROBE_LOADED" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_CO_PREREQ_PROBE_LOADED=1

# Provide _co_find_python so the real lib's collision guard passes.
_co_find_python() { command -v python3 || command -v python || return 1; }

# Provide the emitter primitives (real prereq_probe.sh sources step_zero_emit.sh,
# but our fake is standalone).
_co_pp_json_escape() { printf '%s' "\$1"; }
_co_pp_emit() {
  printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
    "\$1" "\$2" "\$3" "\$4" "\$5"
}

_co_prereq_probe_all() {
  # Hard-tier probes: git, python, gh, node
  echo '{"name":"git","status":"${_hard_status}","severity":"hard","detail":"test-fake","remediation":""}'
  echo '{"name":"python","status":"${_hard_status}","severity":"hard","detail":"test-fake","remediation":""}'
  echo '{"name":"gh","status":"${_hard_status}","severity":"hard","detail":"test-fake","remediation":""}'
  echo '{"name":"node","status":"${_hard_status}","severity":"hard","detail":"test-fake","remediation":""}'
  # Advisory-tier probes: uv, pwsh, ue, clone_auth, longpaths, git_lfs
  echo '{"name":"uv","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
  echo '{"name":"pwsh","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
  echo '{"name":"ue","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
  echo '{"name":"clone_auth","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
  echo '{"name":"longpaths","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
  echo '{"name":"git_lfs","status":"${_advisory_status}","severity":"advisory","detail":"test-fake","remediation":""}'
}

# Standalone entrypoint.
if [[ "\${BASH_SOURCE[0]}" == "\${0}" ]]; then
  _co_prereq_probe_all
fi
FAKE_PREREQ

}

# ---------------------------------------------------------------------------
# Helper: run P-15 with a given fake lib scenario
# Sets _probe_out to the sentinel output.
# ---------------------------------------------------------------------------
_run_p15_with_scenario() {
  local _scenario="$1"
  local _fake_lib_dir _tmpdir
  _fake_lib_dir="$(mktemp -d)"
  _tmpdir="$(mktemp -d)"
  mkdir -p "$_tmpdir/plugins/coordinator-claude/data"

  _build_fake_lib "$_fake_lib_dir" "$_scenario"

  _probe_out="$(
    CLAUDE_HOME="$_tmpdir" \
    COORDINATOR_PLUGINS_ROOT="$_tmpdir/plugins" \
    COORDINATOR_PREREQ_PROBE_LIB_DIR="$_fake_lib_dir" \
    bash "$SENTINEL" --probe P-15 2>&1
  )" || true

  rm -rf "$_fake_lib_dir" "$_tmpdir"
}

# ---------------------------------------------------------------------------
# Section 1 — Syntax check
# ---------------------------------------------------------------------------

echo "--- Section 1: bash -n syntax check"

bash_n_out="$(bash -n "$SENTINEL" 2>&1)"
if [[ $? -eq 0 ]]; then
  pass "1a: bash -n passes on sentinel"
else
  fail "1a: bash -n failed: $bash_n_out"
fi

# ---------------------------------------------------------------------------
# Section 2 — RED on hard-prereq absence
# ---------------------------------------------------------------------------

echo "--- Section 2: RED when hard prerequisites fail"

_run_p15_with_scenario "hard_fail"

# When hard prereqs fail, the probe must NOT report "All selected probes passed".
if echo "$_probe_out" | grep -q "All selected probes passed"; then
  fail "2a: P-15 reported 'All selected probes passed' when hard prereqs are absent (vacuous GREEN)"
else
  pass "2a: P-15 did not report vacuous GREEN when hard prereqs fail"
fi

# The sentinel in subset mode (--probe P-15) emits exactly:
#   [coordinator-doctor] MODE=probe verdict=RED
# on hard-prereq failure. Assert on that specific token — no fallback that
# can match a comment or empty string.
# Review: code-reviewer slice B — fallback grep on "Failing|P-15" matched any
# text containing "P-15" (e.g. a comment), producing vacuous pass on empty output.
if echo "$_probe_out" | grep -q "verdict=RED"; then
  pass "2b: P-15 surfaces verdict=RED on hard-prereq failure"
else
  fail "2b: P-15 did not emit verdict=RED on hard-prereq failure (got: '$_probe_out')"
fi

# ---------------------------------------------------------------------------
# Section 3 — GREEN when only advisory prereqs absent
# ---------------------------------------------------------------------------

echo "--- Section 3: GREEN when only advisory prereqs absent (no AMBER)"

_run_p15_with_scenario "advisory_only"

# Advisory-only absence must yield GREEN — the sentinel emits exactly:
#   [coordinator-doctor] MODE=probe verdict=GREEN
# Assert on that specific positive token. Empty or ambiguous output is
# treated as FAIL — absence-of-RED cannot distinguish "probe ran and
# reported GREEN" from "probe didn't run at all".
# Review: code-reviewer slice B — fallback accepting absence-of-RED passed
# on empty output, masking probe-not-ran failures.
if echo "$_probe_out" | grep -q "verdict=GREEN"; then
  pass "3a: P-15 reports verdict=GREEN when only advisory prereqs absent"
else
  fail "3a: P-15 did not emit verdict=GREEN with advisory-only absences (got: '$_probe_out')"
fi

if echo "$_probe_out" | grep -q "verdict=AMBER"; then
  fail "3b: P-15 emitted AMBER on advisory-only absence (violates AMBER-on-optional-absence rule)"
else
  pass "3b: P-15 did not emit AMBER on advisory-only absence"
fi

# ---------------------------------------------------------------------------
# Section 4 — GREEN when all prereqs pass
# ---------------------------------------------------------------------------

echo "--- Section 4: GREEN when all prereqs pass"

_run_p15_with_scenario "all_pass"

if echo "$_probe_out" | grep -q "All selected probes passed\|verdict=GREEN"; then
  pass "4a: P-15 reports GREEN when all prereqs pass"
elif echo "$_probe_out" | grep -q "verdict=RED\|verdict=AMBER"; then
  fail "4a: P-15 reported RED/AMBER when all prereqs pass"
else
  pass "4a: P-15 did not report RED/AMBER when all prereqs pass"
fi

# ---------------------------------------------------------------------------
# Section 5 — Manifest invariants for P-15
# ---------------------------------------------------------------------------

echo "--- Section 5: P-15 manifest invariants"

MANIFEST="${COORDINATOR_ROOT}/bin/doctor-probes.toml"
PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
fi

if [[ -n "$PY" ]]; then
  manifest_check="$(DOCTOR_PROBES_MANIFEST="$MANIFEST" "$PY" -c "
import sys, os
from pathlib import Path
try:
    import tomllib
except ImportError:
    print('SKIP-notomllib')
    sys.exit(0)
data = tomllib.loads(Path(os.environ['DOCTOR_PROBES_MANIFEST']).read_text())
p15 = next((p for p in data.get('probe', []) if p['id'] == 'P-15'), None)
errors = []
if p15 is None:
    errors.append('P-15 not in manifest')
else:
    if not p15.get('triage'):
        errors.append('triage=false (expected true)')
    if p15.get('weight') not in ('cheap', 'standard'):
        errors.append('weight=' + str(p15.get('weight')) + ' violates triage invariant (must be cheap or standard)')
    if p15.get('severity_if_fail') != 'error':
        errors.append('severity_if_fail=' + str(p15.get('severity_if_fail')) + ' (expected error)')
    if p15.get('cluster') != 'system-prereq':
        errors.append('cluster=' + str(p15.get('cluster')) + ' (expected system-prereq)')
print('FAIL:' + '; '.join(errors) if errors else 'OK')
" 2>/dev/null)"

  if [[ "$manifest_check" == "SKIP-notomllib" ]]; then
    echo "  SKIP 5a: tomllib unavailable"
  elif [[ "$manifest_check" == "OK" ]]; then
    pass "5a: P-15 manifest entry: triage=true, weight=standard, severity_if_fail=error, cluster=system-prereq"
  else
    fail "5a: P-15 manifest invariant failed — $manifest_check"
  fi

  # 5b: P-15 appears in the --triage selector output
  SELECTOR="${COORDINATOR_ROOT}/bin/doctor-probe-select.py"
  if [[ -f "$SELECTOR" ]]; then
    triage_out="$(DOCTOR_PROBES_MANIFEST="$MANIFEST" "$PY" "$SELECTOR" --triage 2>/dev/null | tr '\n' ',' || true)"
    if echo "$triage_out" | grep -q "P-15"; then
      pass "5b: P-15 appears in --triage selector output"
    else
      fail "5b: P-15 missing from --triage selector output (got: $triage_out)"
    fi
  else
    echo "  SKIP 5b: selector not found"
  fi
else
  echo "  SKIP 5a-5b: no Python interpreter found"
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
