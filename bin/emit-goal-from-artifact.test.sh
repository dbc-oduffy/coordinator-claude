#!/usr/bin/env bash
# emit-goal-from-artifact.test.sh — Tests for emit-goal-from-artifact.sh
#
# Purpose: Verifies that emit-goal-from-artifact.sh reads per-repo
# state/goals/*.md frontmatter and invokes append-goal-event.sh once per
# goal with correct params (period, period_value, text, repo, root);
# verifies the invocation count and wire-conformant arg pass-through.
#
# Test isolation: uses a PATH-shim for append-goal-event.sh so tests run
# without requiring EXAMPLE_ORCHESTRATION_HUB_ROOT to be configured on the machine.  The shim
# records each invocation's args to a log file and exits 0, allowing
# emit-goal-from-artifact.sh to be exercised in isolation.
#
# Spec backlink: docs/plans/2026-07-06-goal-setting-okr-legibility-system.md § C7

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMITTER="${SCRIPT_DIR}/emit-goal-from-artifact.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp base for all test state
# ---------------------------------------------------------------------------
TMP_BASE="$(mktemp -d)"
cleanup() { rm -rf "$TMP_BASE"; }
trap cleanup EXIT

# Create a fake git repo root (git init creates a real repo so rev-parse works)
TMP_REPO="${TMP_BASE}/repo"
mkdir -p "$TMP_REPO"
git init -q "$TMP_REPO" 2>/dev/null || true

# state/goals directory
mkdir -p "${TMP_REPO}/state/goals"

# ---------------------------------------------------------------------------
# Build a PATH shim for append-goal-event.sh.
# The shim records each invocation's args to SHIM_LOG (one line per call,
# args space-joined), exits 0.  This lets us assert:
#   - how many times it was called (invocation count)
#   - which args were passed (period, period_value, text, repo, root)
# ---------------------------------------------------------------------------
SHIM_DIR="${TMP_BASE}/shim-bin"
SHIM_LOG="${TMP_BASE}/shim-invocations.log"
mkdir -p "$SHIM_DIR"

# The shim must be named append-goal-event.sh so PATH resolution finds it.
cat > "${SHIM_DIR}/append-goal-event.sh" <<'SHIM'
#!/usr/bin/env bash
# Shim: records args to $SHIM_LOG, exits 0.
printf '%s\n' "$*" >> "$SHIM_LOG"
exit 0
SHIM
chmod +x "${SHIM_DIR}/append-goal-event.sh"

# Export SHIM_LOG so the shim can write to it
export SHIM_LOG

# Prepend shim dir to PATH so emit-goal-from-artifact.sh finds the shim.
# Note: emit-goal-from-artifact.sh uses $_SCRIPT_DIR/../bin/append-goal-event.sh
# via absolute path (_APPEND_HELPER), so PATH alone is not enough.
# We use EMIT_GOAL_APPEND_HELPER env var to override the helper path.
# The emitter reads this env var if set (see implementation).
#
# Alternative: pass --append-helper flag. But the emitter doesn't expose that.
# We need to patch the helper path at runtime.
#
# Solution: pass the shim via COORDINATOR_APPEND_GOAL_HELPER env var which the
# emitter checks.  If that var is unset, it falls back to the SCRIPT_DIR sibling.
# This is the test-isolation seam.
export COORDINATOR_APPEND_GOAL_HELPER="${SHIM_DIR}/append-goal-event.sh"

# ---------------------------------------------------------------------------
# Fixture A: one valid goal artifact
# ---------------------------------------------------------------------------
cat > "${TMP_REPO}/state/goals/goal-legibility.md" <<'FIXTURE'
---
id: goal-legibility
title: "Test Goal: Legibility"
schema: goal
status: active
period: repo
period_value: "DoE-2026"
objective: "Make the system fully legible to new engineers"
owner: doe-em
created: "2026-07-07"
---

## Objective

Make the system fully legible to new engineers so onboarding is fast.
FIXTURE

# ---------------------------------------------------------------------------
# Test 1: emitter exits 0 over a single valid fixture goal
# ---------------------------------------------------------------------------
rm -f "$SHIM_LOG"
EMIT_EXIT=0
bash "$EMITTER" --root "${TMP_REPO}" --repo "dbc-oduffy/doe-test" 2>/dev/null \
  || EMIT_EXIT=$?

if [[ "$EMIT_EXIT" -eq 0 ]]; then
  pass "T1: emitter exits 0 for a valid goal artifact"
else
  fail "T1: emitter exited ${EMIT_EXIT}, expected 0"
fi

# ---------------------------------------------------------------------------
# Test 2: append-goal-event.sh invoked exactly once (one goal → one call)
# ---------------------------------------------------------------------------
if [[ -f "$SHIM_LOG" ]]; then
  INV_COUNT=$(wc -l < "$SHIM_LOG" | tr -d ' ')
  if [[ "$INV_COUNT" -eq 1 ]]; then
    pass "T2: append-goal-event.sh invoked exactly once"
  else
    fail "T2: expected 1 invocation, got ${INV_COUNT}"
  fi
else
  fail "T2: shim log not created — append-goal-event.sh was not invoked"
fi

# ---------------------------------------------------------------------------
# Test 3: invocation carries --period from frontmatter
# ---------------------------------------------------------------------------
if [[ -f "$SHIM_LOG" ]]; then
  INV_LINE="$(head -n 1 "$SHIM_LOG")"
  if echo "$INV_LINE" | grep -qF -- "--period repo"; then
    pass "T3: invocation carries --period repo"
  else
    fail "T3: invocation line missing '--period repo': ${INV_LINE}"
  fi
fi

# ---------------------------------------------------------------------------
# Test 4: invocation carries --period-value from frontmatter
# ---------------------------------------------------------------------------
if [[ -f "$SHIM_LOG" ]]; then
  INV_LINE="$(head -n 1 "$SHIM_LOG")"
  if echo "$INV_LINE" | grep -qF -- "DoE-2026"; then
    pass "T4: invocation carries period_value=DoE-2026"
  else
    fail "T4: invocation line missing 'DoE-2026': ${INV_LINE}"
  fi
fi

# ---------------------------------------------------------------------------
# Test 5: invocation --text contains artifact id (identity chain anchor)
# ---------------------------------------------------------------------------
if [[ -f "$SHIM_LOG" ]]; then
  INV_LINE="$(head -n 1 "$SHIM_LOG")"
  if echo "$INV_LINE" | grep -qF "goal-legibility"; then
    pass "T5: wire text contains artifact id (identity chain: artifact-id -> wire goal_id)"
  else
    fail "T5: invocation text missing artifact id 'goal-legibility': ${INV_LINE}"
  fi
fi

# ---------------------------------------------------------------------------
# Test 6: two goal artifacts → two invocations
# ---------------------------------------------------------------------------
cat > "${TMP_REPO}/state/goals/goal-tooling.md" <<'FIXTURE2'
---
id: goal-tooling
title: "Test Goal: Tooling"
schema: goal
status: active
period: week
period_value: "2026-W28"
objective: "All EM actions are one CLI invocation"
owner: doe-em
created: "2026-07-07"
---
FIXTURE2

rm -f "$SHIM_LOG"
EMIT_EXIT2=0
bash "$EMITTER" --root "${TMP_REPO}" --repo "dbc-oduffy/doe-test" 2>/dev/null \
  || EMIT_EXIT2=$?

if [[ "$EMIT_EXIT2" -eq 0 ]]; then
  pass "T6a: emitter exits 0 for two goal artifacts"
else
  fail "T6a: emitter exited ${EMIT_EXIT2} for two goals"
fi

if [[ -f "$SHIM_LOG" ]]; then
  INV_COUNT2=$(wc -l < "$SHIM_LOG" | tr -d ' ')
  if [[ "$INV_COUNT2" -eq 2 ]]; then
    pass "T6b: two goal artifacts → two append-goal-event.sh invocations"
  else
    fail "T6b: expected 2 invocations for 2 goals, got ${INV_COUNT2}"
  fi
else
  fail "T6b: shim log not created for two-goal run"
fi

# ---------------------------------------------------------------------------
# Test 7: identity chain stability — two runs produce same invocation args
# (verifies text includes id so hash is deterministic across re-runs)
# Review: code-reviewer — T7 was using T6's shim log as "run 1", making it
# implicitly dependent on T6 succeeding with the right shape (F11). Fixed to
# do its own two independent runs into separate named logs so T7 is self-contained.
# ---------------------------------------------------------------------------
T7_LOG1="${TMP_BASE}/shim-t7-run1.log"
T7_LOG2="${TMP_BASE}/shim-t7-run2.log"
rm -f "$T7_LOG1" "$T7_LOG2"

export SHIM_LOG="$T7_LOG1"
bash "$EMITTER" --root "${TMP_REPO}" --repo "dbc-oduffy/doe-test" 2>/dev/null || true

export SHIM_LOG="$T7_LOG2"
bash "$EMITTER" --root "${TMP_REPO}" --repo "dbc-oduffy/doe-test" 2>/dev/null || true

if [[ -f "$T7_LOG1" ]] && [[ -f "$T7_LOG2" ]]; then
  # Compare sorted args from both runs (goals are sorted by filename)
  ARGS_RUN1="$(sort "$T7_LOG1")"
  ARGS_RUN2="$(sort "$T7_LOG2")"
  if [[ "$ARGS_RUN1" == "$ARGS_RUN2" ]]; then
    pass "T7: identity chain stable — same args across two runs"
  else
    fail "T7: args differ across runs (not idempotent)"
  fi
else
  fail "T7: one or both shim logs missing for stability check"
fi

# Restore for remaining tests
export SHIM_LOG="${TMP_BASE}/shim-invocations.log"

# ---------------------------------------------------------------------------
# Test 8: goal with missing 'period' field → exit 2 (partial failure)
# ---------------------------------------------------------------------------
TMP_REPO2="${TMP_BASE}/repo-bad"
mkdir -p "$TMP_REPO2"
git init -q "$TMP_REPO2" 2>/dev/null || true
mkdir -p "${TMP_REPO2}/state/goals"

cat > "${TMP_REPO2}/state/goals/bad-goal.md" <<'BADFIXTURE'
---
id: goal-bad
title: "Bad Goal"
schema: goal
status: active
objective: "Missing period fields"
---
BADFIXTURE

rm -f "$SHIM_LOG"
EXIT_BAD=0
bash "$EMITTER" --root "${TMP_REPO2}" --repo "dbc-oduffy/doe-test" 2>/dev/null \
  || EXIT_BAD=$?

if [[ "$EXIT_BAD" -eq 2 ]]; then
  pass "T8: missing period field → exit 2 (partial failure signaled correctly)"
else
  fail "T8: expected exit 2 for missing period, got ${EXIT_BAD}"
fi

# Verify no invocation happened (bad goal was skipped, not forwarded)
if [[ ! -f "$SHIM_LOG" ]] || [[ "$(wc -l < "$SHIM_LOG" | tr -d ' ')" -eq 0 ]]; then
  pass "T8b: bad goal not forwarded to append-goal-event.sh"
else
  fail "T8b: bad goal was incorrectly forwarded to append-goal-event.sh"
fi

# ---------------------------------------------------------------------------
# Test 9: no state/goals directory → exit 0 (nothing to emit)
# ---------------------------------------------------------------------------
TMP_REPO3="${TMP_BASE}/repo-nogoals"
mkdir -p "$TMP_REPO3"
git init -q "$TMP_REPO3" 2>/dev/null || true
# No state/goals dir created

EXIT_NODIR=0
bash "$EMITTER" --root "${TMP_REPO3}" --repo "dbc-oduffy/doe-test" 2>/dev/null \
  || EXIT_NODIR=$?

if [[ "$EXIT_NODIR" -eq 0 ]]; then
  pass "T9: absent state/goals dir → exit 0"
else
  fail "T9: expected exit 0 for absent goals dir, got ${EXIT_NODIR}"
fi

# ---------------------------------------------------------------------------
# Test 10: empty state/goals directory → exit 0
# ---------------------------------------------------------------------------
TMP_REPO4="${TMP_BASE}/repo-emptygoals"
mkdir -p "${TMP_REPO4}/state/goals"
git init -q "$TMP_REPO4" 2>/dev/null || true

EXIT_EMPTY=0
bash "$EMITTER" --root "${TMP_REPO4}" --repo "dbc-oduffy/doe-test" 2>/dev/null \
  || EXIT_EMPTY=$?

if [[ "$EXIT_EMPTY" -eq 0 ]]; then
  pass "T10: empty state/goals dir → exit 0"
else
  fail "T10: expected exit 0 for empty goals dir, got ${EXIT_EMPTY}"
fi

# ---------------------------------------------------------------------------
# Test 11: --dry-run flag — shim NOT invoked (no goals-log written)
# ---------------------------------------------------------------------------
rm -f "$SHIM_LOG"
bash "$EMITTER" --root "${TMP_REPO}" --repo "dbc-oduffy/doe-test" --dry-run 2>/dev/null || true

if [[ ! -f "$SHIM_LOG" ]] || [[ "$(wc -l < "$SHIM_LOG" | tr -d ' ')" -eq 0 ]]; then
  pass "T11: --dry-run does not invoke append-goal-event.sh"
else
  fail "T11: --dry-run should not invoke append-goal-event.sh"
fi

# ---------------------------------------------------------------------------
# Test 12: invocation carries --repo and --root
# ---------------------------------------------------------------------------
rm -f "$SHIM_LOG"
bash "$EMITTER" --root "${TMP_REPO}" --repo "myorg/myrepo" 2>/dev/null || true

if [[ -f "$SHIM_LOG" ]]; then
  INV_REPO="$(head -n 1 "$SHIM_LOG")"
  if echo "$INV_REPO" | grep -qF -- "--repo"; then
    pass "T12a: invocation carries --repo flag"
  else
    fail "T12a: invocation missing --repo flag: ${INV_REPO}"
  fi
  if echo "$INV_REPO" | grep -qF "myorg/myrepo"; then
    pass "T12b: --repo value passed through correctly"
  else
    fail "T12b: expected 'myorg/myrepo' in invocation: ${INV_REPO}"
  fi
  if echo "$INV_REPO" | grep -qF -- "--root"; then
    pass "T12c: invocation carries --root flag"
  else
    fail "T12c: invocation missing --root flag: ${INV_REPO}"
  fi
else
  fail "T12: shim log not created"
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
