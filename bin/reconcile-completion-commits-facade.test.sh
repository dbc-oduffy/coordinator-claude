#!/usr/bin/env bash
# coordinator/bin/reconcile-completion-commits-facade.test.sh — DR-210/DR-215
# completion.reconcile_commits facade routing test.
#
# Purpose: Verifies all three routing branches of reconcile-completion-commits.sh
# when invoked in --append mode (the zone-B write dispatch zone):
#   TC-absent      — seam absent -> legacy path: entry SHA appended (sentinel).
#   TC-present-ok  — seam present (exit 0) -> native path: entry NOT updated,
#                    sentinel file written by fake coordinator_core.invoke.
#   TC-present-fail — State-3: seam present + fake invoke exits 1 -> cc_invoke
#                    returns 2, legacy NOT taken (fail-loud, no silent legacy).
#
# Note on detect-only mode: the detect-only branch (no --append) stays entirely
# facade-side (MODE GATE — no write op dispatched). It is tested by the existing
# coordinator/bin/tests/test-reconcile-completion-commits.bats, not here.
#
# Spec backlinks:
#   DR-210 (docs/decisions/DR-210-cross-repo-memo-strangle.md)
#   DR-216 (docs/decisions/DR-216-changelog-completion-reviewtrail-write-carveout.md § D2)
#   docs/plans/2026-07-06-strang-10-facade-adoption.md (this chunk)
# Strang-10 chunk: completion.reconcile_commits
#
# DR-215 transport: fake coordinator_core.invoke replaces retired coordinator_core.client.
# TC-present-fail now exits 2 (cc_invoke fail-closed), not 3.
#
# CWD discipline (load-bearing):
#   All subprocess invocations run from TMP_BASE (a neutral temp dir, NOT the DoE
#   repo root), which is also git-initialised with an origin/main. Running from the
#   DoE repo root would put '' on Python's sys.path, making coordinator_core.invoke
#   importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT and rendering TC-absent vacuous.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/reconcile-completion-commits.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"

# Initialise TMP_BASE as a git repo with origin/main so that:
#   (a) git merge-base origin/main HEAD succeeds for the legacy --append path.
#   (b) strangle_route's `git -C "$PWD" rev-parse --show-toplevel` resolves when
#       states 2/3 invoke cc_invoke from this CWD.
git init -q "$TMP_BASE" 2>/dev/null || true

REMOTE_DIR="${TMP_BASE}/.remote-bare"
git init --bare -q "$REMOTE_DIR" 2>/dev/null || true

(
  cd "$TMP_BASE"
  git config user.email "test@example.com"
  git config user.name "Test Author"
  # Initial commit — becomes origin/main base (merge-base target)
  printf '# facade test repo\n' > README.md
  GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00" \
  GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00" \
  GIT_AUTHOR_NAME="Test Author" GIT_AUTHOR_EMAIL="test@example.com" \
  GIT_COMMITTER_NAME="Test Author" GIT_COMMITTER_EMAIL="test@example.com" \
    git add README.md && git commit -q -m "initial commit"
  git remote add origin "$REMOTE_DIR"
  git push -q origin HEAD:main 2>/dev/null
  git fetch -q origin 2>/dev/null
  git branch -q --set-upstream-to=origin/main 2>/dev/null || true
) 2>/dev/null

# Session commit in TMP_BASE carrying the test session-id trailer
SESSION_SID="facade-rcc-test-sid"
SESSION_SHA=""
(
  cd "$TMP_BASE"
  printf 'echo facade-rcc-work\n' > work-facade.sh
  GIT_AUTHOR_DATE="2026-06-27T00:00:00+00:00" \
  GIT_COMMITTER_DATE="2026-06-27T00:00:00+00:00" \
  GIT_AUTHOR_NAME="Test Author" GIT_AUTHOR_EMAIL="test@example.com" \
  GIT_COMMITTER_NAME="Test Author" GIT_COMMITTER_EMAIL="test@example.com" \
    git add work-facade.sh && \
    git commit -q -m "$(printf 'facade rcc work\n\nSession-Id: %s' "$SESSION_SID")"
) 2>/dev/null
SESSION_SHA="$(cd "$TMP_BASE" && git rev-parse --short HEAD 2>/dev/null)"

# EXAMPLE_ORCHESTRATION_HUB_ABSENT: real but empty dir → seam absent (coordinator_core.invoke not importable)
EXAMPLE_ORCHESTRATION_HUB_ABSENT="${TMP_BASE}/example-orchestration-hub-absent"

# EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK: has coordinator_core.invoke stub that exits 0 + writes sentinel.
EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK="${TMP_BASE}/example-orchestration-hub-present-ok"

# EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL: has coordinator_core.invoke stub that exits 1.
EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL="${TMP_BASE}/example-orchestration-hub-present-fail"

mkdir -p "$EXAMPLE_ORCHESTRATION_HUB_ABSENT"

cleanup() { rm -rf "$TMP_BASE"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Build fake coordinator_core.invoke package (DR-215 spawn-per-call transport).
#
# __main__.py is invoked as `python3 -m coordinator_core.invoke <op> <params> --repo <root>`.
# On success (exit_code=0): emits a valid JSON-RPC envelope to stdout and exits 0
# so cc_invoke can parse the result object and return 0 to strangle_route.
# On failure (exit_code!=0): exits non-zero; cc_invoke catches this and returns 2.
#
# When sentinel is non-empty, the stub writes a sentinel file at that path on
# invocation — positive proof of native-path selection (TC-present-ok).
#
# popup-safe-env-suppressed: writes a pure sys.exit stub, no subprocess calls.
# ---------------------------------------------------------------------------
_build_fake_invoke() {
  local root="$1" exit_code="$2" sentinel="${3:-}" result_inner="${4:-}"
  mkdir -p "${root}/coordinator_core/invoke"
  touch "${root}/coordinator_core/__init__.py"
  touch "${root}/coordinator_core/invoke/__init__.py"
  {
    printf '%s\n' 'import sys'
    [[ -n "$sentinel" ]] && printf "import pathlib; pathlib.Path('%s').touch()\n" "$sentinel"
    if [[ "$exit_code" -eq 0 ]]; then
      if [[ -n "$result_inner" ]]; then
        # Emit real op-shape result using json.loads to avoid string-escaping complexity.
        # result_inner is valid JSON with no single-quotes, so embedding in a Python
        # single-quoted string literal is safe.
        # Review: code-reviewer — F2: real op shape enables normalization-branch coverage.
        printf '%s\n' 'import json'
        printf "result_inner = '%s'\n" "$result_inner"
        printf '%s\n' 'envelope = {"jsonrpc": "2.0", "id": 1, "result": json.loads(result_inner)}'
        printf '%s\n' 'sys.stdout.write(json.dumps(envelope) + "\n")'
      else
        # Default envelope for simple routing proofs (no normalization assertion needed).
        printf '%s\n' 'sys.stdout.write("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"exit_code\":0}}\n")'
      fi
    fi
    printf 'sys.exit(%s)\n' "$exit_code"
  } > "${root}/coordinator_core/invoke/__main__.py"  # popup-safe-env-suppressed
}

# EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK uses real op shape to exercise the appended=N normalization branch.
# Review: code-reviewer — F2: completion.reconcile_commits returns {"appended":N,...}.
_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK"   0 "${TMP_BASE}/native-called" \
  '{"appended":1,"skipped":0,"no_op":false}'
_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL" 1

# ---------------------------------------------------------------------------
# Helper: create a minimal pending-release entry at ENTRY_PATH with empty
# commits: list. Called before each test case to ensure a pristine entry.
# ---------------------------------------------------------------------------
ENTRY_PATH="${TMP_BASE}/test-rcc-entry.md"

_make_fresh_entry() {
  cat > "$ENTRY_PATH" <<EOF
---
title: "Facade routing test entry"
created: 2026-06-27
nature: adhoc
commits:
status: pending-release
authored_by: ${SESSION_SID}
---
Facade routing test body.
EOF
}

# ---------------------------------------------------------------------------
# Verify prerequisites
# ---------------------------------------------------------------------------
if [[ ! -f "$SCRIPT" ]]; then
  echo "FATAL: script not found: $SCRIPT"
  exit 2
fi

if [[ -z "$SESSION_SHA" ]]; then
  echo "FATAL: SESSION_SHA not resolved — git repo setup failed"
  exit 2
fi

# ===========================================================================
# TC-absent -- absent-seam -> legacy path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_reconcile_commits executes the
# awk/mv write body.
#
# Sentinel: ENTRY_PATH is updated with the session SHA (awk/mv fold ran).
# This is the proof that legacy_reconcile_commits was invoked.
# Exit: 0 (append succeeded; appended=1 on stdout).
#
# CWD = TMP_BASE (neutral git repo; no coordinator_core there).
# ===========================================================================
_make_fresh_entry

_tc_absent_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" bash "${SCRIPT}" \
  --append --session-id "${SESSION_SID}" "${ENTRY_PATH}" 2>/dev/null) || _tc_absent_rc=$?

if [[ "$_tc_absent_rc" -eq 0 ]] && grep -qF "\"${SESSION_SHA}\"" "$ENTRY_PATH"; then
  pass "TC-absent: legacy path taken (SHA appended to entry, exit 0)"
elif [[ "$_tc_absent_rc" -ne 0 ]]; then
  fail "TC-absent: expected exit 0, got $_tc_absent_rc"
else
  fail "TC-absent: SHA ${SESSION_SHA} not in entry — legacy_reconcile_commits did not run"
fi

# ===========================================================================
# TC-present-ok -- present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke stub that exits 0
# and emits a valid JSON-RPC envelope (so cc_invoke returns 0 to strangle_route).
# Proof (dual):
#   1. ENTRY_PATH NOT updated — legacy_reconcile_commits never ran.
#   2. Sentinel file ${TMP_BASE}/native-called written by the fake invoke stub
#      on invocation (positive proof that coordinator_core.invoke was reached).
# Exit: 0 (cc_invoke returns 0 after parsing the valid envelope).
# ===========================================================================
_make_fresh_entry
rm -f "${TMP_BASE}/native-called"

_tc_present_ok_rc=0
_tc_present_ok_out=""
_tc_present_ok_out="$(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" bash "${SCRIPT}" \
  --append --session-id "${SESSION_SID}" "${ENTRY_PATH}" 2>/dev/null)" || _tc_present_ok_rc=$?

if [[ "$_tc_present_ok_rc" -eq 0 ]]; then
  pass "TC-present-ok: native path exit 0"
else
  fail "TC-present-ok: expected exit 0, got $_tc_present_ok_rc"
fi

if ! grep -qF "\"${SESSION_SHA}\"" "$ENTRY_PATH"; then
  pass "TC-present-ok: entry unchanged (legacy NOT run)"
else
  fail "TC-present-ok: entry updated — legacy_reconcile_commits entered unexpectedly"
fi

if [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "TC-present-ok: native client invoked (sentinel written)"
else
  fail "TC-present-ok: native client not invoked (sentinel absent)"
fi

# Normalization branch: real op shape {"appended":1,...} -> translated to appended=1.
# Review: code-reviewer — F2: proves the JSON->bash output normalization branch is reachable.
if [[ "${_tc_present_ok_out}" == *"appended=1"* ]]; then
  pass "TC-present-ok: output normalized to appended=1 (JSON translation branch proven)"
else
  fail "TC-present-ok: stdout missing 'appended=1' — normalization branch not entered (got: '${_tc_present_ok_out}')"
fi

# ===========================================================================
# TC-present-fail -- State-3: present-seam + fake invoke exits 1 -> cc_invoke returns 2
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke catches the nonzero invoke exit and returns 2; strangle_route
# propagates 2 and returns immediately; legacy_reconcile_commits is never reached.
# fail-loud (not silent legacy).
#
# Proof:
#   1. Exit code 2 propagated (cc_invoke fail-closed rc).
#   2. ENTRY_PATH NOT updated — legacy NOT taken.
# ===========================================================================
_make_fresh_entry

_tc_present_fail_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" bash "${SCRIPT}" \
  --append --session-id "${SESSION_SID}" "${ENTRY_PATH}" 2>/dev/null) || _tc_present_fail_rc=$?

if [[ "$_tc_present_fail_rc" -eq 2 ]]; then
  pass "TC-present-fail: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "TC-present-fail: expected exit 2, got $_tc_present_fail_rc"
fi

if ! grep -qF "\"${SESSION_SHA}\"" "$ENTRY_PATH"; then
  pass "TC-present-fail: entry unchanged (legacy NOT taken)"
else
  fail "TC-present-fail: entry updated — legacy fallback triggered incorrectly"
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
