#!/usr/bin/env bash
# workday-complete-step9-append-changelog-facade.test.sh — DR-216 strang-10 facade routing test.
#
# Purpose: Verifies all three routing branches of the changelog.append_day facade in
# workday-complete-step9-append-changelog.sh — absent-seam (legacy), present-ok (native),
# and present-fail/State-3 (hard-fail, no legacy fallback).
#
# Spec backlinks:
#   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § strang-10
#   DR-216 (coordinator/docs/decisions/DR-216-*.md)
#
# AC coverage:
#   TC-absent  — seam absent → legacy path: legacy_append_day runs; changelog file written.
#                Sentinel: CHANGELOG_PATH exists with today's section header.
#   TC-present-ok — seam present (exit 0) → native path: legacy NOT run; changelog NOT written
#                   by legacy; positive sentinel written by fake coordinator_core.invoke.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 → cc_invoke returns 2;
#                     legacy NOT taken; script exits 2 (fail-loud).
#
# CWD and state-root discipline (load-bearing):
#   All subprocess invocations run from TMP_BASE, which serves as the neutral git CWD.
#   Because coordinator_state_root (Rule 5) resolves from the current working directory's
#   git root (not COORDINATOR_ROOT env var), the script writes changelog files to
#   TMP_BASE/state/week-changelog/. Tests check TMP_BASE-based paths, not COORDINATOR_ROOT.
#   TMP_BASE is git-init'd for two reasons:
#     1. strangle_route (States 2/3) resolves repo root via `git -C "$PWD" rev-parse`.
#     2. coordinator_state_root uses `git rev-parse --show-toplevel` from CWD.
#   Python sys.path[0] = TMP_BASE; no coordinator_core there so absent-seam test is sound.
#
# COORDINATOR_ROOT is set to a per-test fixture repo for the git-log/plans/handoffs
# compute operations; it does NOT affect coordinator_state_root resolution (CWD governs).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEP9="${SCRIPT_DIR}/workday-complete-step9-append-changelog.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state.
# TMP_BASE serves as neutral CWD and state-root parent.
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
# Init TMP_BASE as a git repo:
#   - coordinator_state_root resolves TMP_BASE/state (sibling-repo rule from CWD)
#   - strangle_route can resolve repo root for native dispatch
git init -q "$TMP_BASE" 2>/dev/null || true
git -C "$TMP_BASE" config user.email "test@test.com"
git -C "$TMP_BASE" config user.name "Test"
git -C "$TMP_BASE" config commit.gpgsign false

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
# Build fake coordinator_core.invoke package (DR-215 spawn-per-call transport).
#
# __main__.py is invoked as `python3 -m coordinator_core.invoke <op> <params> <repo_root>`.
# On success (exit_code=0): emits a valid JSON-RPC envelope to stdout and exits 0 so
# cc_invoke can parse the result and return 0 to strangle_route.
# On failure (exit_code!=0): exits non-zero; cc_invoke catches this and returns 2.
#
# When sentinel path is non-empty, the invoke stub writes a sentinel file at that path
# on invocation — positive proof of native-path selection (TC-present-ok).
#
# popup-safe-env-suppressed: writes a pure sys.exit stub; no Windows console subprocess.
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
# make_fixture_repo: create a minimal git repo with required directory structure.
# Used for COORDINATOR_ROOT (git-log/compute operations in Zone A).
# coordinator_state_root still resolves via CWD (TMP_BASE), not FIXTURE_ROOT.
# Sets FIXTURE_ROOT to the created path.
# ---------------------------------------------------------------------------
TODAY_DATE="$(date -u +%Y-%m-%d)"
FIXTURE_MACHINE="facade-test-machine"
FIXTURE_ROOT=""

make_fixture_repo() {
  local dir
  dir="$(mktemp -d)"
  FIXTURE_ROOT="${dir}"

  git -C "${dir}" init -q
  git -C "${dir}" config user.email "test@test.com"
  git -C "${dir}" config user.name "Test"
  git -C "${dir}" config commit.gpgsign false

  mkdir -p "${dir}/state/week-changelog"
  mkdir -p "${dir}/state/handoffs"
  mkdir -p "${dir}/state/review-trail"
  mkdir -p "${dir}/archive/daily-summaries"
  mkdir -p "${dir}/archive/review-trail"

  # Initial commit so git log works
  touch "${dir}/state/week-changelog/.keep"
  git -C "${dir}" add -- "${dir}/state/week-changelog/.keep"
  git -C "${dir}" commit -q -m "chore: init"

  # HEADER.md in the fixture dir (used if coordinator_state_root returns fixture root).
  # When running from TMP_BASE, coordinator_state_root resolves to TMP_BASE/state instead,
  # so the HEADER here is not read. We still write it for completeness / fallback safety.
  printf 'Week starting: %s\n' "${TODAY_DATE}" > "${dir}/state/week-changelog/HEADER.md"
}

# CHANGELOG_PATH: where the script writes the changelog.
# coordinator_state_root with CWD=TMP_BASE resolves to TMP_BASE/state (sibling-repo rule).
# Tests check this path, not the FIXTURE_ROOT-based path.
CHANGELOG_PATH="${TMP_BASE}/state/week-changelog/${TODAY_DATE}-${FIXTURE_MACHINE}.md"

# ---------------------------------------------------------------------------
# Verify prerequisite
# ---------------------------------------------------------------------------
if [[ ! -f "$STEP9" ]]; then
  echo "FATAL: step9 script not found at $STEP9"
  exit 2
fi

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_append_day runs and writes the changelog.
#
# The script runs with:
#   CWD          = TMP_BASE (git-init'd; Python '' path has no coordinator_core)
#   COORDINATOR_ROOT = FIXTURE_ROOT (git repo for Zone-A git-log operations)
#   coordinator_state_root -> TMP_BASE/state (CWD-based resolution, not COORDINATOR_ROOT)
#
# Zone C tries to git-add CHANGELOG_FILE into FIXTURE_ROOT, which fails silently
# (file is in TMP_BASE, not FIXTURE_ROOT), so nothing is staged and Zone C exits 0
# via the idempotent-no-op path. Legacy write to TMP_BASE/state still happened.
#
# Sentinel: CHANGELOG_PATH (TMP_BASE-based) exists.
# Exit: 0.
# ===========================================================================
echo ""
echo "=== TC-absent: absent-seam -> legacy path ==="
make_fixture_repo
rm -f "${CHANGELOG_PATH}"
rm -f "${TMP_BASE}/native-called"

_tc_absent_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" \
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${FIXTURE_MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
  bash "${STEP9}" --no-push 2>/dev/null) || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]]; then
  pass "TC-absent: exit 0"
else
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
fi

if [[ -f "$CHANGELOG_PATH" ]]; then
  pass "TC-absent: changelog file written (legacy_append_day ran)"
else
  fail "TC-absent: changelog file not written -- legacy_append_day did not run (checked: $CHANGELOG_PATH)"
fi

if grep -q "## ${TODAY_DATE}" "$CHANGELOG_PATH" 2>/dev/null; then
  pass "TC-absent: section header present in changelog"
else
  fail "TC-absent: section header '## ${TODAY_DATE}' not found in changelog"
fi

if [[ ! -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-absent: native invoke NOT called (sentinel absent, as expected)"
else
  fail "TC-absent: native invoke was unexpectedly called (sentinel present)"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0 and
# emits a valid JSON-RPC envelope. Native path runs; legacy_append_day NOT called.
# Zone C runs after strangle_route returns 0; fake invoke does not write the changelog
# file, git-add stages nothing -> "[step9] block unchanged (idempotent no-op)" -> exit 0.
#
# Proof (dual):
#   1. Changelog file NOT written -- legacy_append_day never ran.
#   2. Sentinel file ${TMP_BASE}/native-called written by fake invoke stub (positive proof
#      that coordinator_core.invoke was reached via native path).
# Exit: 0.
# ===========================================================================
echo ""
echo "=== TC-present-ok: present-seam exit 0 -> native path ==="
make_fixture_repo
rm -f "${CHANGELOG_PATH}"
rm -f "${TMP_BASE}/native-called"

_tc_present_ok_rc=0
_tc_present_ok_out=""
_tc_present_ok_out="$(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" \
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${FIXTURE_MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
  bash "${STEP9}" --no-push 2>/dev/null)" || _tc_present_ok_rc=$?

if [[ "$_tc_present_ok_rc" -eq 0 ]]; then
  pass "TC-present-ok: exit 0"
else
  fail "TC-present-ok: expected exit 0, got $_tc_present_ok_rc"
fi

if [[ ! -f "$CHANGELOG_PATH" ]]; then
  pass "TC-present-ok: changelog NOT written by legacy (legacy_append_day not called)"
else
  fail "TC-present-ok: changelog was written -- legacy_append_day entered unexpectedly"
fi

if [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-present-ok: native invoke called (sentinel present)"
else
  fail "TC-present-ok: native invoke not called (sentinel absent)"
fi

# Zone-C proof: Zone-C emits "[step9] block unchanged (idempotent no-op)" when nothing
# is staged in COORDINATOR_ROOT. On the native path, fake invoke does not write CHANGELOG_FILE
# into COORDINATOR_ROOT (FIXTURE_ROOT); git-add fails silently; nothing staged → idempotent-no-op.
# Note: "[step9] block written" (line 826 of step9 script) is the shared post-strangle_route
# signal on BOTH State-1 and State-2 paths — it is NOT a legacy-only signal, so the reviewer's
# first suggested assertion was incorrect; the reviewer's alternative (idempotent-no-op) is used.
# Review: code-reviewer — F3: stdout capture + idempotent-no-op assertion (reviewer alternative).
if [[ "${_tc_present_ok_out}" == *"[step9] block unchanged (idempotent no-op)"* ]]; then
  pass "TC-present-ok: Zone-C idempotent-no-op confirmed (nothing staged — CHANGELOG_FILE outside COORDINATOR_ROOT)"
else
  fail "TC-present-ok: expected '[step9] block unchanged (idempotent no-op)' in stdout (got: '${_tc_present_ok_out}')"
fi

# ===========================================================================
# TC-present-fail -- State-3: present-seam + fake invoke exits 1 -> cc_invoke returns 2
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure / import error).
# cc_invoke catches the nonzero invoke exit and returns 2; strangle_route propagates 2;
# the script hits `exit ${_STRANGLE_RC}` -> exits 2. legacy_append_day never reached.
# Fail-loud, no silent legacy fallback.
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. Changelog file NOT written -- legacy NOT taken.
# ===========================================================================
echo ""
echo "=== TC-present-fail: State-3 -> fail-closed exit 2 ==="
make_fixture_repo
rm -f "${CHANGELOG_PATH}"

_tc_present_fail_rc=0
(cd "$TMP_BASE" && \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" \
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${FIXTURE_MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
  bash "${STEP9}" --no-push 2>/dev/null) || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 (cc_invoke fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

if [[ ! -f "$CHANGELOG_PATH" ]]; then
  pass "TC-present-fail: changelog NOT written (legacy NOT taken)"
else
  fail "TC-present-fail: changelog was written -- legacy fallback triggered incorrectly"
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
