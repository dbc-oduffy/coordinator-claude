#!/usr/bin/env bash
# strangler-facade.test.sh — DR-210/DR-215 facade routing shell test.
#
# Purpose: Verifies both routing branches of the strangler-facade.sh router
# for both body-swapped emitter scripts (emit-cockpit-snapshot.sh,
# append-goal-event.sh), plus the AC6 grep-gate asserting no machine-local
# get CLI call in fallback branches or strangler-facade.sh itself.
#
# Spec backlinks:
#   docs/plans/2026-07-04-strang-01-tc3-emission-port-facade-respin.md § C4c
#   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C1 (DR-215 repoint)
# Sibling test: coordinator/bin/append-goal-event.test.sh (harness conventions)
#
# DR-215 repoint: fake coordinator_core.invoke replaces fake coordinator_core.client.
# The fake invoke __main__.py emits a valid JSON-RPC envelope on success so cc_invoke
# can parse it.  State-3 now exits 2 (cc_invoke's fail-closed rc) not 3.
#
# AC coverage:
#   AC2 — emit-cockpit-snapshot.sh: absent-seam -> legacy path; present-seam -> native path.
#   AC3 — append-goal-event.sh: absent-seam -> legacy path; present-seam -> native path.
#   AC5 — State-3 (present + fake invoke exits 1) -> cc_invoke returns 2 -> hard-fail, NOT legacy.
#   AC6 — grep-gate: no machine-local get CLI call in strangler-facade.sh or
#          in the fallback function bodies of the two body-swapped scripts.
#
# No deferred assertions — all AC5 coverage is now exercised:
#   T6  covers State-3 for append-goal-event.sh (JSONL absent, exit 2).
#   T6b covers State-3 for emit-cockpit-snapshot.sh (exit 2, no cockpit-contract error).
#   Cockpit-contract dist/ is NOT needed for T6b: legacy_emit is never reached in
#   State-3 (strangle_route hard-fails before any fallback is invoked).
#   Review: code-reviewer F3 — prior deferred rationale was incorrect.
#
# CWD discipline:
#   All subprocess invocations run from TMP_BASE (not example-orchestration-hub-repo).
#   Python always includes '' (CWD) in sys.path; running from example-orchestration-hub-repo would
#   make coordinator_core.invoke importable regardless of EXAMPLE_ORCHESTRATION_HUB_ROOT, making the
#   absent-seam test vacuous.  A neutral CWD ensures EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability.
#
# bash -n validation (Review: code-reviewer F4):
#   All 4 touched .sh files pass bash -n with no errors.
#   Run: bash -n coordinator/lib/strangler-facade.sh \
#              coordinator/bin/emit-cockpit-snapshot.sh \
#              coordinator/bin/append-goal-event.sh \
#              coordinator/bin/strangler-facade.test.sh
#   Result: exit 0 (no syntax errors) — validated post-integration.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMIT_SCRIPT="${SCRIPT_DIR}/emit-cockpit-snapshot.sh"
APPEND_SCRIPT="${SCRIPT_DIR}/append-goal-event.sh"
FACADE_LIB="${SCRIPT_DIR}/../lib/strangler-facade.sh"

PASS=0
FAIL=0
SKIP=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }
skip() { echo "SKIP: $1"; SKIP=$(( SKIP + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base directory for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
# Init TMP_BASE as a git repo so `git rev-parse --show-toplevel` succeeds when
# strangle_route (States 2/3) calls cc_invoke, which resolves the repo root.
git init -q "$TMP_BASE" 2>/dev/null || true

# EXAMPLE_ORCHESTRATION_HUB_ABSENT: real but empty dir. EXAMPLE_ORCHESTRATION_HUB_ROOT resolves, but coordinator_core.invoke
# is not importable from it -> disk-presence gate returns 1 -> legacy path.
EXAMPLE_ORCHESTRATION_HUB_ABSENT="${TMP_BASE}/example-orchestration-hub-absent"
# EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK: has coordinator_core.invoke package, __main__.py exits 0.
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
# When validate_json=1 (3rd arg), the invoke stub also validates sys.argv[2] as
# well-formed JSON before exiting — this is the C4c payload-validity guard
# that ensures the params JSON string reaching invoke was not corrupted
# (e.g. by the ${1:-{}} brace-in-default mis-parse, which appended a
# spurious trailing }).
# When sentinel (4th arg) is non-empty, the invoke stub writes a sentinel file at
# that path on invocation — enables positive proof of native-path selection
# (see T5, F8).
#
# Review: code-reviewer — F9: replaced python3 -c "...${root}..." with
# printf-to-file to eliminate path-quote fragility in the -c shell string.
# popup-safe-env-suppressed: writes a pure sys.exit stub, no subprocess calls.
# ---------------------------------------------------------------------------
_build_fake_invoke() {
  local root="$1" exit_code="$2" validate_json="${3:-}" sentinel="${4:-}"
  mkdir -p "${root}/coordinator_core/invoke"
  touch "${root}/coordinator_core/__init__.py"
  touch "${root}/coordinator_core/invoke/__init__.py"
  if [[ -n "$validate_json" ]]; then
    {
      printf '%s\n' 'import sys, json'
      [[ -n "$sentinel" ]] && printf "import pathlib; pathlib.Path('%s').touch()\n" "$sentinel"
      printf '%s\n' \
        'try:' \
        '    json.loads(sys.argv[2])' \
        'except Exception as e:' \
        '    print("FATAL: invalid JSON param: " + str(e), file=sys.stderr)' \
        '    sys.exit(2)'
      # Emit a valid JSON-RPC envelope so cc_invoke can parse and return 0.
      printf '%s\n' 'sys.stdout.write("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"exit_code\":0}}\n")'
      printf 'sys.exit(%s)\n' "$exit_code"
    } > "${root}/coordinator_core/invoke/__main__.py"  # popup-safe-env-suppressed
  else
    {
      printf '%s\n' 'import sys'
      [[ -n "$sentinel" ]] && printf "import pathlib; pathlib.Path('%s').touch()\n" "$sentinel"
      if [[ "$exit_code" -eq 0 ]]; then
        # Emit valid JSON-RPC envelope for cc_invoke to parse on success path.
        printf '%s\n' 'sys.stdout.write("{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"exit_code\":0}}\n")'
      fi
      printf 'sys.exit(%s)\n' "$exit_code"
    } > "${root}/coordinator_core/invoke/__main__.py"  # popup-safe-env-suppressed
  fi
}

# Review: code-reviewer — F8: EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK invoke stub writes sentinel on invocation
# (positive proof of native-path selection, asserted in T5).
_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK" 0 "validate" "${TMP_BASE}/native-called"
# EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL: invoke exits 1; cc_invoke catches nonzero and returns 2.
_build_fake_invoke "$EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL" 1

# Per-machine slug (legacy_append writes to $EXAMPLE_ORCHESTRATION_HUB_ROOT/state/goals-log.<slug>.jsonl
# via coordinator_state_root --central which resolves to $EXAMPLE_ORCHESTRATION_HUB_ROOT/state when
# EXAMPLE_ORCHESTRATION_HUB_ROOT is set as an env var).
MACHINE_SLUG="$(printf '%s' "$(hostname)" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
APPEND_LOG_ABSENT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}/state/goals-log.${MACHINE_SLUG}.jsonl"
APPEND_LOG_PRESENT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}/state/goals-log.${MACHINE_SLUG}.jsonl"
APPEND_LOG_STATE3="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}/state/goals-log.${MACHINE_SLUG}.jsonl"

# ---------------------------------------------------------------------------
# Verify prerequisite files exist
# ---------------------------------------------------------------------------
for _f in "$EMIT_SCRIPT" "$APPEND_SCRIPT" "$FACADE_LIB"; do
  if [[ ! -f "$_f" ]]; then
    echo "FATAL: prerequisite file missing: $_f"
    exit 2
  fi
done

# ===========================================================================
# T1 -- append-goal-event.sh: absent-seam -> legacy path (JSONL created)
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty dir -> import coordinator_core.invoke fails
# -> disk-presence gate returns 1 -> legacy_append runs.
# Review: code-reviewer — F3 extension: same stale .client reference pattern as T2/T5.
# CWD = TMP_BASE (neutral; no coordinator_core there, so Python '' path is safe).
# Proof: JSONL file created at $EXAMPLE_ORCHESTRATION_HUB_ABSENT/state/, exit 0.
# ===========================================================================
rm -f "$APPEND_LOG_ABSENT"
_t1_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" bash "$APPEND_SCRIPT" \
  --period week \
  --period-value "2026-W27" \
  --text "facade absent-seam test" \
  --repo "test/repo" \
  --root "." 2>/dev/null) || _t1_rc=$?

if [[ "$_t1_rc" -eq 0 && -f "$APPEND_LOG_ABSENT" ]]; then
  pass "T1: append absent-seam: legacy path taken (JSONL created, exit 0)"
else
  fail "T1: append absent-seam: expected JSONL at '$APPEND_LOG_ABSENT', rc=$_t1_rc"
fi

# ===========================================================================
# T2 -- append-goal-event.sh: present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke that exits 0.
# Review: code-reviewer — F3: updated stale .client reference to .invoke.
# Proof: JSONL is NOT created at $EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK/state/ (legacy_append never
# runs), exit 0.
# ===========================================================================
rm -f "$APPEND_LOG_PRESENT"
_t2_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" bash "$APPEND_SCRIPT" \
  --period week \
  --period-value "2026-W27" \
  --text "facade present-seam test" \
  --repo "test/repo" \
  --root "." 2>/dev/null) || _t2_rc=$?

if [[ "$_t2_rc" -eq 0 && ! -f "$APPEND_LOG_PRESENT" ]]; then
  pass "T2: append present-seam: native path taken (JSONL absent, exit 0)"
elif [[ "$_t2_rc" -ne 0 ]]; then
  fail "T2: append present-seam: expected exit 0, got $_t2_rc"
else
  fail "T2: append present-seam: JSONL created -- legacy path was taken instead of native"
fi

# ===========================================================================
# T3 -- append-goal-event.sh: legacy output matches pre-facade contract
#
# Verifies legacy_append output is byte-identical to the pre-facade contract:
# valid JSON, all 9 required keys present, status="active".
# ===========================================================================
rm -f "$APPEND_LOG_ABSENT"
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" bash "$APPEND_SCRIPT" \
  --period day \
  --period-value "2026-07-05" \
  --text "legacy-contract-check" \
  --repo "test/repo" \
  --root "." 2>/dev/null)

if [[ -f "$APPEND_LOG_ABSENT" ]]; then
  _t3_line="$(head -n 1 "$APPEND_LOG_ABSENT")"
  if echo "$_t3_line" | jq -e . >/dev/null 2>&1; then
    pass "T3: legacy output is valid JSON"
  else
    fail "T3: legacy output is not valid JSON"
  fi
  _t3_status="$(echo "$_t3_line" | jq -r '.status' 2>/dev/null)"
  if [[ "$_t3_status" == "active" ]]; then
    pass "T3: legacy output has status=active"
  else
    fail "T3: legacy output has status='$_t3_status' (expected 'active')"
  fi
  _t3_keys_ok=1
  for _k in goal_id repo coordinator_root_path period period_value \
            declared_by_machine declared_at text status; do
    if ! echo "$_t3_line" | jq -e "has(\"$_k\")" >/dev/null 2>&1; then
      fail "T3: legacy output missing required key '$_k'"
      _t3_keys_ok=0
    fi
  done
  if [[ "$_t3_keys_ok" -eq 1 ]]; then
    pass "T3: legacy output has all 9 required keys"
  fi
else
  fail "T3: legacy path did not create JSONL log"
fi

# ===========================================================================
# T4 -- emit-cockpit-snapshot.sh: absent-seam -> State-1 fail-loud (C2)
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT absent -> seam absent -> legacy_emit called. legacy_emit no
# longer carries a bash emitter body (DR-208 ported the emitter to example-orchestration-hub's
# Python artifact.emit, C2 stripped the ~3000-line body to a fail-loud stub) --
# it now fails loud rather than writing a snapshot.
# Proof: exit 1, no cockpit-emission.json written, native sentinel absent.
#
# Spec backlink: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § C2/D1
# ===========================================================================
rm -f "${TMP_BASE}/native-called"
rm -f "${EXAMPLE_ORCHESTRATION_HUB_ABSENT}/state/cockpit-emission.json"
_t4_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ABSENT}" \
  bash "$EMIT_SCRIPT" 2>/dev/null 1>/dev/null) || _t4_rc=$?

if [[ "$_t4_rc" -eq 1 ]] \
    && ! [[ -f "${EXAMPLE_ORCHESTRATION_HUB_ABSENT}/state/cockpit-emission.json" ]] \
    && ! [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "T4: emit absent-seam: State-1 fail-loud (exit 1, no snapshot written, native sentinel absent)"
elif [[ -f "${TMP_BASE}/native-called" ]]; then
  fail "T4: emit absent-seam: native sentinel written -- native path was taken unexpectedly"
elif [[ -f "${EXAMPLE_ORCHESTRATION_HUB_ABSENT}/state/cockpit-emission.json" ]]; then
  fail "T4: emit absent-seam: cockpit-emission.json written -- legacy emitter body unexpectedly present"
else
  fail "T4: emit absent-seam: expected exit 1 (fail-loud), got $_t4_rc"
fi

# ===========================================================================
# T5 -- emit-cockpit-snapshot.sh: present-seam (exits 0) -> native path taken
#
# EXAMPLE_ORCHESTRATION_HUB_ROOT points to fake dir with coordinator_core.invoke that exits 0.
# Review: code-reviewer — F3: updated stale .client reference to .invoke.
# Proof: exit 0, no cockpit-contract error in stderr, AND native client wrote
# the sentinel file ${TMP_BASE}/native-called (positive proof of invocation —
# Review: code-reviewer F8; sentinel cleared before run to avoid false-pass from T2).
# ===========================================================================
rm -f "${TMP_BASE}/native-called"
_t5_rc=0
_t5_stderr="$(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" \
  bash "$EMIT_SCRIPT" 2>&1 1>/dev/null)" || _t5_rc=$?

if [[ "$_t5_rc" -eq 0 ]]; then
  pass "T5: emit present-seam: native path taken (exit 0)"
else
  fail "T5: emit present-seam: expected exit 0, got $_t5_rc; stderr: $(echo "$_t5_stderr" | head -3)"
fi

if echo "$_t5_stderr" | grep -q "cockpit-contract"; then
  fail "T5: emit present-seam: cockpit-contract error seen -- legacy path entered unexpectedly"
else
  pass "T5: emit present-seam: no cockpit-contract error (legacy path not entered)"
fi

if [[ -f "${TMP_BASE}/native-called" ]]; then
  pass "T5: emit present-seam: native client invoked (sentinel written)"
else
  fail "T5: emit present-seam: native client not invoked (sentinel absent)"
fi

# ===========================================================================
# T5b -- COORDINATOR_FORCE_LEGACY=1: append present-seam -> legacy path forced
#
# Force-legacy affordance (byte-parity harness lever): mirrors T2's present-seam
# setup exactly (same EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK fake invoke), but with
# COORDINATOR_FORCE_LEGACY=1 exported.  Expected: legacy_append runs (JSONL
# created) even though the seam IS importable -- the lever bypasses native
# when explicitly set, per the header/negative-spec addendum in
# strangler-facade.sh.  Proof: JSONL created at EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK/state/, exit 0.
# ===========================================================================
rm -f "$APPEND_LOG_PRESENT"
_t5b_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" COORDINATOR_FORCE_LEGACY=1 \
  bash "$APPEND_SCRIPT" \
  --period week \
  --period-value "2026-W27" \
  --text "force-legacy override test" \
  --repo "test/repo" \
  --root "." 2>/dev/null) || _t5b_rc=$?

if [[ "$_t5b_rc" -eq 0 && -f "$APPEND_LOG_PRESENT" ]]; then
  pass "T5b: append present-seam + COORDINATOR_FORCE_LEGACY=1: legacy path forced (JSONL created, exit 0)"
elif [[ "$_t5b_rc" -ne 0 ]]; then
  fail "T5b: append present-seam + COORDINATOR_FORCE_LEGACY=1: expected exit 0, got $_t5b_rc"
else
  fail "T5b: append present-seam + COORDINATOR_FORCE_LEGACY=1: JSONL absent -- native path taken instead of forced legacy"
fi
rm -f "$APPEND_LOG_PRESENT"

# ===========================================================================
# T6 -- State-3: append present-seam + fake invoke exits 1 -> cc_invoke returns 2 -> hard-fail
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke maps any nonzero invoke exit to rc=2; strangle_route propagates 2.
# strangle_route does NOT fall back to legacy.
# Proof: exit 2, JSONL absent.
# ===========================================================================
rm -f "$APPEND_LOG_STATE3"
_t6_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" bash "$APPEND_SCRIPT" \
  --period week \
  --period-value "2026-W27" \
  --text "state3-hard-fail-test" \
  --repo "test/repo" \
  --root "." 2>/dev/null) || _t6_rc=$?

if [[ "$_t6_rc" -eq 2 ]]; then
  pass "T6: append State-3: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "T6: append State-3: expected exit 2, got $_t6_rc"
fi

if [[ ! -f "$APPEND_LOG_STATE3" ]]; then
  pass "T6: append State-3: JSONL absent (legacy path NOT taken)"
else
  fail "T6: append State-3: JSONL created -- legacy fallback triggered incorrectly"
fi

# ===========================================================================
# T6b -- State-3: emit present-seam + fake invoke exits 1 -> cc_invoke returns 2 -> hard-fail
#
# Review: code-reviewer — F3: AC5 gap fixed.  State-3 for emit-cockpit-snapshot.sh
# does NOT require cockpit-contract dist/ or node; legacy_emit is never reached
# when the seam is present (strangle_route hard-fails before any fallback is invoked).
# The deferred rationale in the original header was incorrect.
#
# Seam present, fake invoke exits 1 (simulates post-spawn failure).
# cc_invoke returns 2; strangle_route propagates 2; does NOT fall back to legacy_emit.
# Proof: exit 2 propagated; no cockpit-contract error in stderr (legacy_emit NOT entered).
# CWD = TMP_BASE (neutral for Python import check; EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability).
# ===========================================================================
_t6b_rc=0
_t6b_stderr="$(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_FAIL}" \
  bash "$EMIT_SCRIPT" 2>&1 1>/dev/null)" || _t6b_rc=$?

if [[ "$_t6b_rc" -eq 2 ]]; then
  pass "T6b: emit State-3: exit code 2 from cc_invoke (nonzero invoke -> fail-closed)"
else
  fail "T6b: emit State-3: expected exit 2, got $_t6b_rc"
fi

if ! echo "$_t6b_stderr" | grep -q "cockpit-contract"; then
  pass "T6b: emit State-3: no cockpit-contract error (legacy_emit NOT entered)"
else
  fail "T6b: emit State-3: cockpit-contract error seen -- legacy_emit entered incorrectly"
fi

# ===========================================================================
# T7 -- GREP-GATE (AC6): strangler-facade.sh has no machine-local get CLI call
#
# Non-comment lines (lines whose first non-whitespace char is not #) are
# searched for "machine-local get" as an invocation.  Negative-spec comments
# referencing the pattern are excluded by the grep -v.
#
# Scope note (Review: code-reviewer F7): coordinator-example-orchestration-hub-root.sh is
# intentionally excluded from this grep-gate.  Its machine-local get call lives
# in the presence-check (_sf_seam_present) and native-dispatch paths only —
# never in a fallback branch — so the CD-3 invariant (no machine-local get in
# legacy bodies) is correctly upheld without gating the resolver lib itself.
# ===========================================================================
_t7_hits="$(grep -v '^\s*#' "$FACADE_LIB" | grep 'machine-local[[:space:]]\+get' || true)"
if [[ -z "$_t7_hits" ]]; then
  pass "T7: grep-gate strangler-facade.sh: no machine-local get CLI call"
else
  fail "T7: grep-gate strangler-facade.sh: found machine-local get CLI call:"
  echo "$_t7_hits" | sed 's/^/    /'
fi

# ===========================================================================
# T8 -- GREP-GATE (AC6): emit-cockpit-snapshot.sh has no machine-local get CLI call
#
# The legacy_emit function spans the vast majority of the file.  Greping the
# full file for non-comment invocations covers the fallback branch completely.
# ===========================================================================
_t8_hits="$(grep -v '^\s*#' "$EMIT_SCRIPT" | grep 'machine-local[[:space:]]\+get' || true)"
if [[ -z "$_t8_hits" ]]; then
  pass "T8: grep-gate emit-cockpit-snapshot.sh: no machine-local get CLI call"
else
  fail "T8: grep-gate emit-cockpit-snapshot.sh: found machine-local get CLI call:"
  echo "$_t8_hits" | sed 's/^/    /'
fi

# ===========================================================================
# T9 -- GREP-GATE (AC6): append-goal-event.sh has no machine-local get CLI call
# ===========================================================================
_t9_hits="$(grep -v '^\s*#' "$APPEND_SCRIPT" | grep 'machine-local[[:space:]]\+get' || true)"
if [[ -z "$_t9_hits" ]]; then
  pass "T9: grep-gate append-goal-event.sh: no machine-local get CLI call"
else
  fail "T9: grep-gate append-goal-event.sh: found machine-local get CLI call:"
  echo "$_t9_hits" | sed 's/^/    /'
fi

# ===========================================================================
# T10 -- Payload JSON validity: params_json arrives at invoke well-formed
#
# Regression guard for the ${1:-{}} brace-in-default mis-parse (DR-210 strang-01
# bug): when $1 is set to a non-empty JSON string the first } in ${1:-{}} closes
# the parameter expansion, appending a spurious trailing } to the value and
# producing malformed JSON (e.g. '{"out":"/tmp/x"}' -> '{"out":"/tmp/x"}}').
#
# This test calls strangle_route directly with a known params string so the
# regression fires at the facade level rather than only via the body-swapped
# scripts (T2/T5).  The validating PRESENT_OK invoke stub runs json.loads(sys.argv[2])
# and exits 2 on failure; old buggy code -> exit 2; fixed code -> exit 0.
#
# CWD = TMP_BASE (neutral Python path; EXAMPLE_ORCHESTRATION_HUB_ROOT governs importability).
# The test runs inside a git repo (TMP_BASE may lack .git); we set GIT_DIR to
# a dummy value and pass a repo-root override via the git fallback path.
# ===========================================================================
_t10_rc=0
(cd "$TMP_BASE" && EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_PRESENT_OK}" bash -c "
  source '${FACADE_LIB}'
  noop_legacy() { :; }
  strangle_route 'artifact.emit' 'noop_legacy' '{\"out\":\"/tmp/x\"}'
" 2>/dev/null) || _t10_rc=$?

if [[ "$_t10_rc" -eq 0 ]]; then
  pass "T10: payload JSON validity: '{\"out\":\"/tmp/x\"}' arrives well-formed at invoke (exit 0)"
else
  fail "T10: payload JSON validity: expected exit 0, got $_t10_rc -- params_json malformed (trailing-brace bug?)"
fi

# ===========================================================================
# T11 -- GREP-GATE (AC2): no residual coordinator_core.client in this slice's lib/JS files
#
# AC2 requires: "A grep-gate asserts no residual coordinator_core.client in any
# coordinator/ shell/lib/js file, excluding comment lines."
# Scope: the lib/JS files owned by this slice (strangler-facade.sh,
# memo-transition-facade.sh, coordinator-core-invoke.sh, normalize-handoff-frontmatter.js).
# The full coordinator/ scan cannot run until all peer DR-215 migration slices land;
# this slice-scoped gate provides coverage for the files touched here.
# Strips comment lines: shell (#), JS single-line (//), and JS block comment
# content (* lines) before testing.
# Prevents silent CI pass if .client is accidentally reintroduced into this slice's code.
#
# Review: code-reviewer — F1: AC2 grep-gate added; slice-scoped because the broader
# coordinator/ migration is in-flight across parallel slices (peer files still have
# .client in live code; a full coordinator/ scan would fail until all slices land).
# ===========================================================================
_t11_scope_files=(
  "${SCRIPT_DIR}/../lib/strangler-facade.sh"
  "${SCRIPT_DIR}/../lib/memo-transition-facade.sh"
  "${SCRIPT_DIR}/../lib/coordinator-core-invoke.sh"
  "${SCRIPT_DIR}/normalize-handoff-frontmatter.js"
)
_t11_hits=""
for _cfile in "${_t11_scope_files[@]}"; do
  if [[ -f "$_cfile" ]]; then
    if grep -v '^\s*#\|^\s*//\|^\s*\*' "$_cfile" 2>/dev/null \
        | grep -q 'coordinator_core\.client'; then
      _t11_hits="${_t11_hits}${_cfile}"$'\n'
    fi
  fi
done
if [[ -z "$_t11_hits" ]]; then
  pass "T11: grep-gate AC2: no live-code .client transport references in slice lib/JS files"
else
  fail "T11: grep-gate AC2: live-code .client transport reference found in files:"
  printf '%s' "$_t11_hits" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [[ "$SKIP" -gt 0 ]]; then
  echo "Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
else
  echo "Results: ${PASS} passed, ${FAIL} failed"
fi
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
