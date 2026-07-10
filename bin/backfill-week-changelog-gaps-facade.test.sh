#!/usr/bin/env bash
# coordinator/bin/backfill-week-changelog-gaps-facade.test.sh — DR-216 changelog.backfill_gaps facade routing test.
#
# Purpose: Verifies all three routing branches of the backfill-week-changelog-gaps.sh
# facade (absent-seam/legacy, present-ok/native, present-fail/State-3 fail-closed).
#
# Spec backlink: cross-repo/inbox/2026-07-06-strang-10-facade-adoption.md
#
# DR-215 transport: fake coordinator_core.invoke replaces any retired UDS client stub.
# TC-present-fail exits 2 (cc_invoke fail-closed).
#
# AC coverage:
#   TC-absent   — seam absent -> legacy path: legacy_backfill_gaps runs and writes a
#                 synthesized backfill file under TMP_BASE/state/week-changelog/.
#                 Sentinel: the backfill file's existence proves legacy fired.
#   TC-present-ok — seam present (exit 0) -> native path: legacy NOT run, no backfill
#                 file written, positive sentinel file written by fake coordinator_core.invoke.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 -> cc_invoke returns 2,
#                 legacy NOT taken (fail-loud, no silent legacy fallback).
#
# CWD discipline:
#   All subprocess invocations run from TMP_BASE (not the DoE repo directory).
#   Python always includes '' (CWD) in sys.path; running from the repo root would make
#   coordinator_core.invoke importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT, making the absent-seam
#   test vacuous. A neutral CWD ensures EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability.
#
# TC-absent sentinel detail:
#   The legacy function uses coordinator_state_root (Rule 5: no --central) which, when
#   CWD is a non-meta git repo, returns ${GIT_ROOT}/state. TMP_BASE is a git-init'd
#   non-meta repo, so coordinator_state_root returns ${TMP_BASE}/state. A HEADER.md is
#   placed there and a test commit made; legacy finds the HEADER, runs git log, and
#   writes a backfill file — positive proof of the legacy path.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/backfill-week-changelog-gaps.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
# Init TMP_BASE as a git repo so:
#  (a) git rev-parse --show-toplevel succeeds when strangle_route (States 2/3)
#      calls cc_invoke, which resolves the repo root, AND
#  (b) coordinator_state_root (Rule 5) returns ${TMP_BASE}/state (not meta-repo)
#      so the legacy function writes backfill files there — isolated from real state.
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
# Build fake coordinator_core.invoke package (DR-215 replacement).
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
# Setup for TC-absent: HEADER.md + git commit so legacy actually backfills.
#
# coordinator_state_root (Rule 5, no --central) returns ${TMP_BASE}/state when
# CWD is TMP_BASE (a non-meta git repo). We place HEADER.md there and make a
# test commit in TMP_BASE so git log has output — causing legacy to write a
# backfill file (positive sentinel that the legacy path ran).
# ---------------------------------------------------------------------------
_PYTHON_BIN="$(command -v python3 || command -v python || true)"

_TC_ABSENT_WEEK_START=""
if [[ -n "$_PYTHON_BIN" ]]; then
  _TC_ABSENT_WEEK_START="$("$_PYTHON_BIN" -c \
    "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%d'))" \
    2>/dev/null || true)"
fi

mkdir -p "${TMP_BASE}/state/week-changelog"
if [[ -n "$_TC_ABSENT_WEEK_START" ]]; then
  printf '**Week starting:** %s\n\n## Week summary\n\n(synthesized by test)\n' \
    "$_TC_ABSENT_WEEK_START" > "${TMP_BASE}/state/week-changelog/HEADER.md"
fi

# Make a test commit in TMP_BASE so git log returns output for today's date range.
GIT_AUTHOR_NAME="test" GIT_AUTHOR_EMAIL="test@test.com" \
GIT_COMMITTER_NAME="test" GIT_COMMITTER_EMAIL="test@test.com" \
  git -C "$TMP_BASE" commit --allow-empty -q -m "test-backfill-sentinel" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Verify prerequisites
# ---------------------------------------------------------------------------
if [[ ! -f "$SCRIPT" ]]; then
  echo "FATAL: prerequisite script missing: $SCRIPT"
  exit 2
fi
if [[ -z "$_PYTHON_BIN" ]]; then
  echo "FATAL: python3 not found (required by legacy_backfill_gaps)"
  exit 2
fi
if [[ -z "$_TC_ABSENT_WEEK_START" ]]; then
  echo "FATAL: could not compute today's date via Python (needed for TC-absent HEADER.md)"
  exit 2
fi

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_backfill_gaps runs.
# CWD = TMP_BASE (neutral; git-init'd non-meta repo so coordinator_state_root
# Rule 5 returns ${TMP_BASE}/state, isolating writes from real state).
#
# Sentinel: a backfill file is written to ${TMP_BASE}/state/week-changelog/
# proving that legacy_backfill_gaps was invoked and executed successfully.
# Exit: 0 (legacy advisory trap; never aborts caller).
# ===========================================================================
rm -f "${TMP_BASE}/native-called"

_tc_absent_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" bash "$SCRIPT" 2>/dev/null) \
  || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]]; then
  pass "TC-absent: legacy path exited 0 (advisory contract)"
else
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
fi

# Positive sentinel: check for a backfill file written by legacy.
_absent_backfill_found=0
for _f in "${TMP_BASE}/state/week-changelog/"*"-backfill.md"; do
  [[ -f "$_f" ]] && _absent_backfill_found=1 && break
done

if [[ "$_absent_backfill_found" -eq 1 ]]; then
  pass "TC-absent: legacy path taken (backfill file written — positive sentinel)"
else
  fail "TC-absent: backfill file not written (legacy_backfill_gaps did not fire or found no commits)"
fi

if [[ ! -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-absent: native client NOT invoked (seam-absent confirmed)"
else
  fail "TC-absent: native-called sentinel unexpectedly present"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0
# and emits a JSON-RPC envelope (so cc_invoke returns 0 to strangle_route).
# Proof (dual):
#   1. Exit code 0 (cc_invoke returns 0 after parsing the valid envelope).
#   2. Sentinel file ${TMP_BASE}/native-called written by the fake invoke stub.
#   3. No backfill file written in the new-dir-only window — legacy NOT run.
# ===========================================================================

# Remove any backfill files from TC-absent before TC-present-ok.
rm -f "${TMP_BASE}/state/week-changelog/"*"-backfill.md"
rm -f "${TMP_BASE}/native-called"

_tc_present_ok_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" bash "$SCRIPT" 2>/dev/null) \
  || _tc_present_ok_rc=$?

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

# Verify legacy did NOT run: no backfill file should have been written.
_present_ok_backfill_found=0
for _f in "${TMP_BASE}/state/week-changelog/"*"-backfill.md"; do
  [[ -f "$_f" ]] && _present_ok_backfill_found=1 && break
done

if [[ "$_present_ok_backfill_found" -eq 0 ]]; then
  pass "TC-present-ok: no backfill file written (legacy NOT run)"
else
  fail "TC-present-ok: backfill file found — legacy_backfill_gaps entered unexpectedly"
fi

# ===========================================================================
# TC-present-fail -- State-3: present-seam + fake invoke exits 1 -> cc_invoke returns 2
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke catches the nonzero invoke exit and returns 2; strangle_route
# propagates 2 and returns immediately; legacy_backfill_gaps is never reached.
# fail-loud (not silent legacy).
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. No backfill file written — legacy NOT taken.
# ===========================================================================
rm -f "${TMP_BASE}/state/week-changelog/"*"-backfill.md"

_tc_present_fail_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" bash "$SCRIPT" 2>/dev/null) \
  || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

_fail_backfill_found=0
for _f in "${TMP_BASE}/state/week-changelog/"*"-backfill.md"; do
  [[ -f "$_f" ]] && _fail_backfill_found=1 && break
done

if [[ "$_fail_backfill_found" -eq 0 ]]; then
  pass "TC-present-fail: no backfill file written (legacy NOT taken)"
else
  fail "TC-present-fail: backfill file found — legacy fallback triggered incorrectly"
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
