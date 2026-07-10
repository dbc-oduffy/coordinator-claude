#!/usr/bin/env bash
# coordinator/bin/coordinator-write-review-trail-facade.test.sh — DR-216 review_trail.write facade routing test.
#
# Purpose: Verifies all three routing branches of coordinator-write-review-trail.sh
# (absent-seam / legacy, present-ok / native, present-fail / State-3 hard-fail).
#
# Spec backlinks:
#   DR-216 (docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md)
#   docs/plans/2026-07-06-dr215-veneer-uds-to-invoke-migration.md (strang-10 C5)
#
# DR-215 transport: fake coordinator_core.invoke (spawn-per-call).
# TC-present-fail exits 2 (cc_invoke fail-closed).
#
# AC coverage:
#   TC-absent — seam absent -> legacy path: legacy_review_trail_write runs and writes
#               a JSON file to state/review-trail/ (sentinel: file present).
#   TC-present-ok — seam present (exit 0) -> native path: legacy NOT run (no trail file
#                   from bash legacy), positive sentinel written by fake coordinator_core.invoke.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 -> cc_invoke returns 2,
#                     legacy NOT taken (fail-loud, no silent legacy), no trail file written.
#
# CWD discipline:
#   All subprocess invocations run from TMP_BASE (not the DoE repo directory).
#   Python always includes '' (CWD) in sys.path; running from the repo root would make
#   coordinator_core.invoke importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT, making the absent-seam
#   test vacuous. A neutral CWD ensures EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FACADE_SCRIPT="${SCRIPT_DIR}/coordinator-write-review-trail.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
# Init TMP_BASE as a git repo so `git rev-parse --show-toplevel` succeeds when
# strangle_route (States 2/3) calls cc_invoke, which resolves the repo root.
git init -q "$TMP_BASE" 2>/dev/null || true
git -C "$TMP_BASE" config user.email "test@test.com" 2>/dev/null || true
git -C "$TMP_BASE" config user.name "Test" 2>/dev/null || true

# EXAMPLE_ORCHESTRATION_HUB_ABSENT: real but empty dir. EXAMPLE_ORCHESTRATION_HUB_ROOT resolves but coordinator_core.invoke
# is not importable -> disk-presence gate returns 1 -> legacy path (State 1).
EXAMPLE_ORCHESTRATION_HUB_ABSENT="${TMP_BASE}/example-orchestration-hub-absent"

# EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK: has coordinator_core.invoke package, __main__.py exits 0.
# Simulates seam present + invoke succeeds (State 2 steady-state stub).
EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK="${TMP_BASE}/example-orchestration-hub-present-ok"

# EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL: has coordinator_core.invoke package, __main__.py exits 1.
# Simulates State-3: seam present, invoke exits non-zero -> cc_invoke returns 2.
EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL="${TMP_BASE}/example-orchestration-hub-present-fail"

mkdir -p "$EXAMPLE_ORCHESTRATION_HUB_ABSENT"

cleanup() { rm -rf "$TMP_BASE"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Build fake coordinator_core.invoke package (DR-215 replacement for the
# retired coordinator_core.client).
#
# __main__.py is invoked as `python3 -m coordinator_core.invoke <op> <params> --repo <root>`.
# On success (exit_code=0): emits a valid JSON-RPC envelope to stdout and exits 0
# so cc_invoke can parse the result object and return 0 to strangle_route.
# On failure (exit_code!=0): exits non-zero; cc_invoke catches this and returns 2.
#
# When sentinel (3rd arg) is non-empty, the invoke stub writes a sentinel file at
# that path on invocation — positive proof of native-path selection (TC-present-ok).
#
# popup-safe-env-suppressed: writes a pure sys.exit stub, no subprocess calls.
# ---------------------------------------------------------------------------
_build_fake_invoke() {
  local root="$1" exit_code="$2" sentinel="${3:-}"
  mkdir -p "${root}/coordinator_core/invoke"
  touch "${root}/coordinator_core/__init__.py"
  touch "${root}/coordinator_core/invoke/__init__.py"
  {
    printf '%s\n' 'import sys'
    [[ -n "$sentinel" ]] && printf "import pathlib; pathlib.Path('%s').touch()\n" "$sentinel"
    if [[ "$exit_code" -eq 0 ]]; then
      # Emit valid JSON-RPC envelope for cc_invoke to parse on success path.
      printf '%s\n' 'sys.stdout.write("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"exit_code\":0}}\n")'
    fi
    printf 'sys.exit(%s)\n' "$exit_code"
  } > "${root}/coordinator_core/invoke/__main__.py"  # popup-safe-env-suppressed
}

_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK"   0 "${TMP_BASE}/native-called"
_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL" 1

# ---------------------------------------------------------------------------
# Verify prerequisite
# ---------------------------------------------------------------------------
if [[ ! -f "$FACADE_SCRIPT" ]]; then
  echo "FATAL: prerequisite file missing: $FACADE_SCRIPT"
  exit 2
fi

# Standard args shared across test cases (valid inputs).
_STANDARD_ARGS=(
  --sha-range "abc123..def456"
  --reviewer code-reviewer
  --scope session
  --verdict ok
  --diff-loc 42
)

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_review_trail_write runs.
# CWD = TMP_BASE (neutral; no coordinator_core there, so Python '' path is safe).
#
# Sentinel: a JSON file is written to state/review-trail/ by the legacy bash body.
# This is proof that legacy_review_trail_write was invoked and completed.
# Exit: 0 (legacy path succeeds when required args + session-id are present).
# ===========================================================================
_tc_absent_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" \
  CLAUDE_SESSION_ID="test-session-absent" \
  bash "$FACADE_SCRIPT" "${_STANDARD_ARGS[@]}" 2>/dev/null) || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]]; then
  pass "TC-absent: exit 0 (legacy path ran)"
else
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
fi

_absent_file_count=$(find "${TMP_BASE}/state/review-trail" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$_absent_file_count" -gt 0 ]]; then
  pass "TC-absent: trail file written by legacy (sentinel confirms legacy path taken)"
else
  fail "TC-absent: no trail file in state/review-trail/ — legacy path not taken"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0
# and emits a JSON-RPC envelope (so cc_invoke returns 0 to strangle_route).
# Proof (dual):
#   1. Sentinel file ${TMP_BASE}/native-called written by the fake invoke stub on
#      invocation (positive proof that coordinator_core.invoke was reached).
#   2. No trail file added beyond those from TC-absent — legacy NOT run.
# Exit: 0 (cc_invoke returns 0 after parsing the valid envelope).
# ===========================================================================
rm -f "${TMP_BASE}/native-called"
_trail_count_before=$(find "${TMP_BASE}/state/review-trail" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')

_tc_present_ok_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" \
  CLAUDE_SESSION_ID="test-session-present" \
  bash "$FACADE_SCRIPT" "${_STANDARD_ARGS[@]}" 2>/dev/null) || _tc_present_ok_rc=$?

if [[ "$_tc_present_ok_rc" -eq 0 ]]; then
  pass "TC-present-ok: native path exit 0"
else
  fail "TC-present-ok: expected exit 0, got $_tc_present_ok_rc"
fi

if [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-present-ok: native client invoked (sentinel written)"
else
  fail "TC-present-ok: native client not invoked (sentinel absent)"
fi

_trail_count_after=$(find "${TMP_BASE}/state/review-trail" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$_trail_count_after" -eq "$_trail_count_before" ]]; then
  pass "TC-present-ok: no new trail file (legacy NOT run)"
else
  fail "TC-present-ok: trail file count changed ($trail_count_before -> $_trail_count_after) — legacy ran unexpectedly"
fi

# ===========================================================================
# TC-present-ok-missing-arg -- facade-side required-arg gate exits 1 (not 2)
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT = EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK (State 2 would otherwise run).
# --sha-range is omitted; the facade gate catches it before _RT_PARAMS is built
# -> exit 1 (matching legacy exit-1 contract).
# Proves: native-path validation failures for missing required args exit 1, not 2.
# Review: code-reviewer — F1: test case added per finding.
# ===========================================================================
_tc_present_ok_missing_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" \
  CLAUDE_SESSION_ID="test-session-missing" \
  bash "$FACADE_SCRIPT" \
    --reviewer code-reviewer \
    --scope session \
    --verdict ok \
  2>/dev/null) || _tc_present_ok_missing_rc=$?

if [[ "$_tc_present_ok_missing_rc" -ne 0 ]]; then
  pass "TC-present-ok-missing-arg: exit nonzero on missing --sha-range"
else
  fail "TC-present-ok-missing-arg: expected nonzero exit, got 0"
fi

if [[ "$_tc_present_ok_missing_rc" -eq 1 ]]; then
  pass "TC-present-ok-missing-arg: exit 1 (legacy contract preserved, not exit 2)"
else
  fail "TC-present-ok-missing-arg: expected exit 1, got $_tc_present_ok_missing_rc"
fi

# ===========================================================================
# TC-present-fail -- State-3: present-seam + fake invoke exits 1 -> cc_invoke returns 2
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke catches the nonzero invoke exit and returns 2; strangle_route
# propagates 2 and returns immediately; legacy_review_trail_write is never reached.
# fail-loud (not silent legacy).
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. Trail file count unchanged — legacy NOT taken.
# ===========================================================================
_trail_count_before_fail=$(find "${TMP_BASE}/state/review-trail" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')

_tc_present_fail_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" \
  CLAUDE_SESSION_ID="test-session-fail" \
  bash "$FACADE_SCRIPT" "${_STANDARD_ARGS[@]}" 2>/dev/null) || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

_trail_count_after_fail=$(find "${TMP_BASE}/state/review-trail" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$_trail_count_after_fail" -eq "$_trail_count_before_fail" ]]; then
  pass "TC-present-fail: trail file count unchanged (legacy NOT taken)"
else
  fail "TC-present-fail: trail file written — legacy fallback triggered incorrectly"
fi

# ===========================================================================
# TC-wsc-auto-sentinels -- machine-provenance sentinels accepted through the
# legacy (State-1, absent-seam) enum gate.
#
# wsc-auto-adjudication (--reviewer) / workstream-close-auto (--scope) are the
# example-orchestration-hub wsc_commit._build_effective_review_trail auto-source sentinel values
# (example-orchestration-hub commit 5854d06). Proves the DoE bash cold-fallback enum gate accepts
# both values end-to-end (exit 0 + record written), matching TC-absent's shape.
# ===========================================================================
_tc_wsc_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" \
  CLAUDE_SESSION_ID="wscauto1-session" \
  bash "$FACADE_SCRIPT" \
    --sha-range "abc123..def456" \
    --reviewer wsc-auto-adjudication \
    --scope workstream-close-auto \
    --verdict ok \
    --diff-loc 42 \
  2>/dev/null) || _tc_wsc_rc=$?

if [[ "$_tc_wsc_rc" -eq 0 ]]; then
  pass "TC-wsc-auto-sentinels: exit 0 (enum gate accepts wsc-auto-adjudication / workstream-close-auto)"
else
  fail "TC-wsc-auto-sentinels: expected exit 0, got $_tc_wsc_rc"
fi

# SESSION_ID_SHORT truncates CLAUDE_SESSION_ID to its first 8 chars in the
# target filename (coordinator-write-review-trail.sh line ~346) — match on
# that 8-char prefix, not the full session-id string.
_wsc_trail_file=$(find "${TMP_BASE}/state/review-trail" -name "*wscauto1*.json" 2>/dev/null | head -n 1)
if [[ -n "$_wsc_trail_file" ]] && grep -q '"reviewer":"wsc-auto-adjudication"' "$_wsc_trail_file" 2>/dev/null \
  && grep -q '"scope":"workstream-close-auto"' "$_wsc_trail_file" 2>/dev/null; then
  pass "TC-wsc-auto-sentinels: record written with both sentinel values"
else
  fail "TC-wsc-auto-sentinels: expected record with reviewer=wsc-auto-adjudication scope=workstream-close-auto — file: ${_wsc_trail_file:-<none>}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
