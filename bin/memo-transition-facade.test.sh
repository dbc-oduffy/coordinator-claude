#!/usr/bin/env bash
# coordinator/bin/memo-transition-facade.test.sh — DR-210/DR-215 memo.transition facade routing test.
#
# Purpose: Verifies all three routing branches of _cs_memo_transition_route
# (memo-transition-facade.sh) — absent-seam (legacy), present-ok (native),
# and present-fail/State-3 (hard-fail, no legacy fallback).
#
# Spec backlinks:
#   DR-210 (docs/decisions/DR-210-cross-repo-memo-strangle.md)
#   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C1 (DR-215 repoint)
# Strang-09 chunk: C4
# Sibling: coordinator/bin/strangler-facade.test.sh (AC pattern mirrored here)
#
# DR-215 repoint: fake coordinator_core.invoke replaces fake coordinator_core.client.
# TC-present-fail now exits 2 (cc_invoke fail-closed) not 3.
#
# AC coverage:
#   TC-absent — seam absent -> legacy path: legacy_memo_transition runs node memo-transition.js;
#               sentinel is memo file transitioning from open -> in_progress.
#   TC-present-ok — seam present (exit 0) -> native path: legacy NOT run, memo unchanged,
#                   positive sentinel file written by fake coordinator_core.invoke.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 -> cc_invoke returns 2,
#                     legacy NOT taken (fail-loud, no silent legacy), memo unchanged.
#
# CWD discipline:
#   All subprocess invocations run from TMP_BASE (not the DoE repo directory).
#   Python always includes '' (CWD) in sys.path; running from the repo root would make
#   coordinator_core.invoke importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT, making the absent-seam
#   test vacuous. A neutral CWD ensures EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FACADE_LIB="${SCRIPT_DIR}/../lib/memo-transition-facade.sh"

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
# Helper: create a minimal open memo file with parseable YAML frontmatter.
# memo-transition.js claim verb: requires status: open and YAML delimiters.
# validateMemoFrontmatter checks cross-field rules only (no base-field requirement).
# ---------------------------------------------------------------------------
_make_open_memo() {
  local path="$1"
  printf '%s\n' '---' 'status: open' '---' 'Test memo body for facade routing test.' > "$path"
}

# ---------------------------------------------------------------------------
# Verify prerequisite
# ---------------------------------------------------------------------------
if [[ ! -f "$FACADE_LIB" ]]; then
  echo "FATAL: prerequisite file missing: $FACADE_LIB"
  exit 2
fi

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_memo_transition runs node memo-transition.js.
# Review: code-reviewer — F3: updated stale .client reference to .invoke.
# CWD = TMP_BASE (neutral; no coordinator_core there, so Python '' path is safe).
#
# Sentinel: the memo file transitions from open -> in_progress (node CLI ran and
# mutated the file). This is the proof that legacy_memo_transition was invoked.
# Exit: 0 (node memo-transition.js claim exits 0 on success).
# ===========================================================================
MEMO_ABSENT="${TMP_BASE}/memo-absent.md"
_make_open_memo "$MEMO_ABSENT"

_tc_absent_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" bash -c "
  source '${FACADE_LIB}'
  _cs_memo_transition_route claim '${MEMO_ABSENT}' \
    --session-id 'test-session-absent' \
    --at '2026-07-05T12:00:00Z'
" 2>/dev/null) || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]] && grep -q 'status: in_progress' "$MEMO_ABSENT"; then
  pass "TC-absent: legacy path taken (memo transitioned open->in_progress, exit 0)"
elif [[ "$_tc_absent_rc" -ne 0 ]]; then
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
else
  fail "TC-absent: memo not transitioned (expected status: in_progress); legacy path not taken"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0
# and emits a JSON-RPC envelope (so cc_invoke returns 0 to strangle_route).
# Proof (dual):
#   1. Memo file NOT transitioned — legacy_memo_transition never ran.
#   2. Sentinel file ${TMP_BASE}/native-called written by the fake invoke stub on invocation
#      (positive proof that coordinator_core.invoke was reached via native path).
# Exit: 0 (cc_invoke returns 0 after parsing the valid envelope).
# ===========================================================================
MEMO_PRESENT="${TMP_BASE}/memo-present.md"
_make_open_memo "$MEMO_PRESENT"
rm -f "${TMP_BASE}/native-called"

_tc_present_ok_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" bash -c "
  source '${FACADE_LIB}'
  _cs_memo_transition_route claim '${MEMO_PRESENT}' \
    --session-id 'test-session-present' \
    --at '2026-07-05T12:00:00Z'
" 2>/dev/null) || _tc_present_ok_rc=$?

if [[ "$_tc_present_ok_rc" -eq 0 ]]; then
  pass "TC-present-ok: native path exit 0"
else
  fail "TC-present-ok: expected exit 0, got $_tc_present_ok_rc"
fi

if ! grep -q 'status: in_progress' "$MEMO_PRESENT"; then
  pass "TC-present-ok: memo unchanged (legacy NOT run)"
else
  fail "TC-present-ok: memo transitioned — legacy_memo_transition entered unexpectedly"
fi

if [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-present-ok: native client invoked (sentinel written)"
else
  fail "TC-present-ok: native client not invoked (sentinel absent)"
fi

# ===========================================================================
# TC-present-fail -- State-3: present-seam + fake invoke exits 1 -> cc_invoke returns 2
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke catches the nonzero invoke exit and returns 2; strangle_route
# propagates 2 and returns immediately; legacy_memo_transition is never reached.
# fail-loud (not silent legacy).
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. Memo file unchanged — legacy NOT taken.
# ===========================================================================
MEMO_FAIL="${TMP_BASE}/memo-fail.md"
_make_open_memo "$MEMO_FAIL"

_tc_present_fail_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" bash -c "
  source '${FACADE_LIB}'
  _cs_memo_transition_route claim '${MEMO_FAIL}' \
    --session-id 'test-session-fail' \
    --at '2026-07-05T12:00:00Z'
" 2>/dev/null) || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

if ! grep -q 'status: in_progress' "$MEMO_FAIL"; then
  pass "TC-present-fail: memo unchanged (legacy NOT taken)"
else
  fail "TC-present-fail: memo transitioned — legacy fallback triggered incorrectly"
fi

# ===========================================================================
# TC-action -- action verb: --decision, --decision-note, --realized-by flag-parsing
#
# Verifies that the flag-parsing loop in _cs_memo_transition_route correctly
# populates decision, decision_note, and realized_by for the action verb.
# Only claim + --session-id/--at were previously exercised; --decision and
# --realized-by were untested.
#
# Setup: seam-present with a custom fake invoke stub that writes its params JSON
# argument (sys.argv[2]) to a temp file so the test can validate field values.
# Exit: 0 (invoke exits 0 on success path).
#
# Review: code-reviewer — F8: added TC-action to cover action-verb flag-parsing.
# ===========================================================================
EXAMPLE_ORCHESTRATION_HUB_ACTION="${TMP_BASE}/example-orchestration-hub-action"
ACTION_PARAMS_FILE="${TMP_BASE}/action-params.json"
mkdir -p "${EXAMPLE_ORCHESTRATION_HUB_ACTION}/coordinator_core/invoke"
touch "${EXAMPLE_ORCHESTRATION_HUB_ACTION}/coordinator_core/__init__.py"
touch "${EXAMPLE_ORCHESTRATION_HUB_ACTION}/coordinator_core/invoke/__init__.py"
{
  printf '%s\n' 'import sys, pathlib'
  printf "pathlib.Path('%s').write_text(sys.argv[2])\n" "$ACTION_PARAMS_FILE"
  printf '%s\n' 'sys.stdout.write("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"exit_code\":0}}\n")'
  printf '%s\n' 'sys.exit(0)'
} > "${EXAMPLE_ORCHESTRATION_HUB_ACTION}/coordinator_core/invoke/__main__.py"  # popup-safe-env-suppressed

rm -f "$ACTION_PARAMS_FILE"
_tc_action_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ACTION}" bash -c "
  source '${FACADE_LIB}'
  _cs_memo_transition_route action '/fake/memo.md' \
    --decision 'accepted' \
    --decision-note 'test decision note' \
    --realized-by 'DR-999'
" 2>/dev/null) || _tc_action_rc=$?

if [[ "$_tc_action_rc" -eq 0 ]]; then
  pass "TC-action: action verb exits 0"
else
  fail "TC-action: expected exit 0, got $_tc_action_rc"
fi

if [[ -f "$ACTION_PARAMS_FILE" ]]; then
  _ta_decision="$(jq -r '.decision' "$ACTION_PARAMS_FILE" 2>/dev/null)"
  _ta_decision_note="$(jq -r '.decision_note' "$ACTION_PARAMS_FILE" 2>/dev/null)"
  _ta_realized_by="$(jq -r '.realized_by' "$ACTION_PARAMS_FILE" 2>/dev/null)"

  if [[ "$_ta_decision" == "accepted" ]]; then
    pass "TC-action: params JSON contains decision='accepted'"
  else
    fail "TC-action: expected decision='accepted', got '$_ta_decision'"
  fi
  if [[ "$_ta_decision_note" == "test decision note" ]]; then
    pass "TC-action: params JSON contains correct decision_note"
  else
    fail "TC-action: expected decision_note='test decision note', got '$_ta_decision_note'"
  fi
  if [[ "$_ta_realized_by" == "DR-999" ]]; then
    pass "TC-action: params JSON contains realized_by='DR-999'"
  else
    fail "TC-action: expected realized_by='DR-999', got '$_ta_realized_by'"
  fi
else
  fail "TC-action: params file not written — native path not reached or params arg missing"
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
