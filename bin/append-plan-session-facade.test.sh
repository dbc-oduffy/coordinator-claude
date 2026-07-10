#!/usr/bin/env bash
# coordinator/bin/append-plan-session-facade.test.sh — DR-216 plan.append_session facade routing test.
#
# Purpose: Verifies all three routing branches of the append-plan-session.sh
# strangler facade — absent-seam (legacy), present-ok (native), and
# present-fail/State-3 (hard-fail, no legacy fallback).
#
# Spec backlinks:
#   DR-216 (docs/decisions/DR-216-changelog-completion-reviewtrail-write-carveout.md)
#   docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md
# Strang-10 chunk: append-plan-session
#
# Three-state contract:
#   TC-absent      — seam absent -> legacy path: legacy_append_plan_session writes
#                    a session entry into the plan file (sentinel = entry present).
#   TC-present-ok  — seam present (exit 0) -> native path: legacy NOT run, plan
#                    file unchanged, positive sentinel written by fake invoke stub.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 -> cc_invoke
#                    returns 2, legacy NOT taken (fail-loud, no silent legacy),
#                    plan file unchanged.
#
# Path-scope discipline:
#   Plan files live at ${TMP_BASE}/docs/plans/*.md so they pass the facade's
#   /docs/plans/ gate — that gate routes non-plans/ paths directly to legacy
#   (reflecting the native op's noun-confinement constraint DR-216 D2(iv)).
#   Using docs/plans/ paths ensures strangle_route is always called and all
#   three routing states are exercised.
#
# CWD discipline:
#   All subprocess invocations run from TMP_BASE (not the DoE repo directory).
#   Python always includes '' (CWD) in sys.path; running from the repo root would
#   make coordinator_core.invoke importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT, making the
#   absent-seam test vacuous. A neutral CWD + git init ensures EXAMPLE_ORCHESTRATION_HUB_ROOT governs
#   importability.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="${SCRIPT_DIR}/append-plan-session.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
# Init TMP_BASE as a git repo so:
#   (a) `git rev-parse --git-dir` succeeds inside the legacy function (lock acquire).
#   (b) strangle_route's native path can resolve the repo root via
#       `git -C "$PWD" rev-parse --show-toplevel` when State 2/3 is taken.
git init -q "$TMP_BASE" 2>/dev/null || true

# Plan files live under docs/plans/ so they pass the facade's path-scope gate.
# The gate routes non-plans/ paths to legacy directly; docs/plans/ paths reach
# strangle_route and exercise all three routing states.
PLANS_DIR="${TMP_BASE}/docs/plans"
mkdir -p "$PLANS_DIR"

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
# Helper: create a minimal plan file with valid YAML frontmatter.
# The legacy function validates --- fences and may append agent_sessions:.
# ---------------------------------------------------------------------------
_make_plan() {
  local path="$1"
  printf '%s\n' \
    '---' \
    'title: "facade routing test plan"' \
    'created: 2026-07-06' \
    '---' \
    '' \
    '# Body' \
    '' \
    'Test plan body for facade routing test.' > "$path"
}

# ---------------------------------------------------------------------------
# Verify prerequisite
# ---------------------------------------------------------------------------
if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
  echo "FATAL: prerequisite file missing: $SCRIPT_UNDER_TEST"
  exit 2
fi

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_append_plan_session runs and
# appends a session entry to the plan file.
#
# Plan file is in docs/plans/ to pass the facade's path-scope gate, ensuring
# strangle_route is called (not bypassed by the gate to legacy directly).
# CWD = TMP_BASE (neutral; no coordinator_core there, so Python '' path is safe).
# COORDINATOR_SESSION_ID is set so the legacy session-id resolution succeeds.
#
# Sentinel: plan file gains an agent_sessions entry for the test session id.
# Exit: 0 (legacy append succeeds).
# ===========================================================================
PLAN_ABSENT="${PLANS_DIR}/plan-absent.md"
_make_plan "$PLAN_ABSENT"

_tc_absent_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" \
  COORDINATOR_SESSION_ID="test-session-absent-$(date +%s)" \
  bash "${SCRIPT_UNDER_TEST}" "${PLAN_ABSENT}" 2>/dev/null) || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]] && grep -q 'agent_sessions:' "$PLAN_ABSENT"; then
  pass "TC-absent: legacy path taken (session entry appended to plan, exit 0)"
elif [[ "$_tc_absent_rc" -ne 0 ]]; then
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
else
  fail "TC-absent: plan has no agent_sessions entry (legacy_append_plan_session not reached)"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0
# and emits a JSON-RPC envelope (so cc_invoke returns 0 to strangle_route).
# Plan file is in docs/plans/ to pass the facade's path-scope gate.
#
# Proof (dual):
#   1. Plan file NOT modified — legacy_append_plan_session never ran.
#   2. Sentinel file ${TMP_BASE}/native-called written by the fake invoke stub
#      (positive proof that coordinator_core.invoke was reached via native path).
# Exit: 0 (cc_invoke returns 0 after parsing the valid envelope).
# ===========================================================================
PLAN_PRESENT="${PLANS_DIR}/plan-present.md"
_make_plan "$PLAN_PRESENT"
rm -f "${TMP_BASE}/native-called"

_tc_present_ok_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" \
  COORDINATOR_SESSION_ID="test-session-present-$(date +%s)" \
  bash "${SCRIPT_UNDER_TEST}" "${PLAN_PRESENT}" 2>/dev/null) || _tc_present_ok_rc=$?

if [[ "$_tc_present_ok_rc" -eq 0 ]]; then
  pass "TC-present-ok: native path exit 0"
else
  fail "TC-present-ok: expected exit 0, got $_tc_present_ok_rc"
fi

if ! grep -q 'agent_sessions:' "$PLAN_PRESENT"; then
  pass "TC-present-ok: plan unchanged (legacy NOT run)"
else
  fail "TC-present-ok: plan gained agent_sessions entry — legacy_append_plan_session entered unexpectedly"
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
# propagates 2 and returns immediately; legacy_append_plan_session is never reached.
# fail-loud (not silent legacy). Plan file is in docs/plans/ to pass the gate.
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. Plan file unchanged — legacy NOT taken.
# ===========================================================================
PLAN_FAIL="${PLANS_DIR}/plan-fail.md"
_make_plan "$PLAN_FAIL"

_tc_present_fail_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" \
  COORDINATOR_SESSION_ID="test-session-fail-$(date +%s)" \
  bash "${SCRIPT_UNDER_TEST}" "${PLAN_FAIL}" 2>/dev/null) || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

if ! grep -q 'agent_sessions:' "$PLAN_FAIL"; then
  pass "TC-present-fail: plan unchanged (legacy NOT taken)"
else
  fail "TC-present-fail: plan gained agent_sessions entry — legacy fallback triggered incorrectly"
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
