#!/usr/bin/env bash
# bin/classify-dispatch-shape.test.sh — Self-contained test suite for classify-dispatch-shape.sh
#
# Purpose: Validate the dispatch-shape classifier's count-based signal across
# the key cases: parallel wave correctly recognized, serial-grind detected,
# false-positive guard (serial gate-kind), F1 inline-EM exclusion, and F3
# reviewer-exclusion from executor count.
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C3
#
# Usage: bash bin/classify-dispatch-shape.test.sh
# Exit 0 = all tests pass; non-zero = at least one failure.
#
# Fixture conventions:
#   dispatched-agents.txt: 4-col TSV  agentId<TAB>model<TAB>subagent_type<TAB>dispatched-at
#   dispatched-at: Unix epoch (return-time; NO fabricated overlapping timestamps)
#   ## Dispatch Ledger: real table shape as per execute-plan SKILL.md Phase 1.6

# --- bash >= 4 guard (must be reachable on 3.2 — no bash-4 syntax before this) ---
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "classify-dispatch-shape.test.sh: requires bash >= 4 (found ${BASH_VERSION})." >&2
  echo "  brew install bash  # macOS" >&2
  exit 1
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/classify-dispatch-shape.sh"

PASS=0
FAIL=0
TMPDIR_ROOT=""

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
_setup() {
  TMPDIR_ROOT="$(mktemp -d)"
}

_teardown() {
  if [[ -n "$TMPDIR_ROOT" ]] && [[ -d "$TMPDIR_ROOT" ]]; then
    rm -rf "$TMPDIR_ROOT"
  fi
}

trap _teardown EXIT

_setup

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

_assert_exit_zero() {
  local label="$1" exit_code="$2"
  if [[ "$exit_code" -eq 0 ]]; then
    _pass "$label — exited zero"
  else
    _fail "$label — expected zero exit, got ${exit_code}"
  fi
}

_assert_stderr_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF -- "$needle"; then
    _pass "$label — stderr contains: ${needle}"
  else
    _fail "$label — stderr missing: ${needle}"
    echo "    (actual stderr first 500 chars: ${haystack:0:500})"
  fi
}

_assert_stderr_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF -- "$needle"; then
    _fail "$label — stderr unexpectedly contains: ${needle}"
    echo "    (actual stderr first 500 chars: ${haystack:0:500})"
  else
    _pass "$label — stderr does not contain: ${needle}"
  fi
}

# ---------------------------------------------------------------------------
# Fixture builder helpers
# ---------------------------------------------------------------------------

# Build a minimal git repo structure with coordinator-sessions/<sid>/dispatched-agents.txt
# Returns the path to the temp repo and sets FIXTURE_SID, FIXTURE_GIT_DIR
FIXTURE_SID=""
FIXTURE_GIT_DIR=""

_make_repo() {
  local dir="$1"
  mkdir -p "${dir}"
  git -C "$dir" init -q
  FIXTURE_GIT_DIR="${dir}/.git"
  FIXTURE_SID="test-session-sid-001"
  mkdir -p "${FIXTURE_GIT_DIR}/coordinator-sessions/${FIXTURE_SID}"
}

_write_agents_file() {
  local repo_dir="$1"
  shift
  # Each remaining argument is a TSV row: agentId<TAB>model<TAB>subagent_type<TAB>epoch
  local out="${FIXTURE_GIT_DIR}/coordinator-sessions/${FIXTURE_SID}/dispatched-agents.txt"
  : > "$out"
  for row in "$@"; do
    printf '%s\n' "$row" >> "$out"
  done
}

_write_plan() {
  local plan_file="$1"
  local ledger_body="$2"
  mkdir -p "$(dirname "$plan_file")"
  cat > "$plan_file" <<PLANEOF
# Test Plan

Some plan body text.

## Dispatch Ledger

| dispatch # | chunk-id | one-line brief | write-files | AC-paths | gate-kind | runs | est-min | status |
|---|---|---|---|---|---|---|---|---|
${ledger_body}

## Another Section

Nothing here.
PLANEOF
}

# ---------------------------------------------------------------------------
# Test (a): 3 parallel-permitted chunks + 3 distinct executor agentIds → silent
# ---------------------------------------------------------------------------
echo ""
echo "Test (a): 3 parallel chunks + 3 distinct executor agents → silent (no offer)"

dir_a="${TMPDIR_ROOT}/test_a"
_make_repo "$dir_a"

# 3 distinct executor agents (general-purpose subagent_type)
_write_agents_file "$dir_a" \
  "$(printf 'agent-aaa111\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-bbb222\tsonnet\tgeneral-purpose\t1782100100')" \
  "$(printf 'agent-ccc333\tsonnet\tgeneral-purpose\t1782100200')"

plan_a="${dir_a}/docs/plans/test-plan.md"
_write_plan "$plan_a" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |'

stderr_a="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_a" 2>&1)"
exit_a=$?

_assert_exit_zero "test-a: exit 0" "$exit_a"
_assert_stderr_not_contains "test-a: no offer emitted" "DISPATCH SHAPE QUESTION" "$stderr_a"

# ---------------------------------------------------------------------------
# Test (b): 3 parallel-permitted chunks + 1 distinct executor agentId → offer
# ---------------------------------------------------------------------------
echo ""
echo "Test (b): 3 parallel chunks + 1 distinct executor agent → offer (question-framed)"

dir_b="${TMPDIR_ROOT}/test_b"
_make_repo "$dir_b"

# Only 1 distinct executor agent handled all 3 chunks
_write_agents_file "$dir_b" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100100')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100200')"

plan_b="${dir_b}/docs/plans/test-plan.md"
_write_plan "$plan_b" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |'

stderr_b="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_b" 2>&1)"
exit_b=$?

_assert_exit_zero "test-b: exit 0 (always)" "$exit_b"
_assert_stderr_contains "test-b: offer emitted" "DISPATCH SHAPE QUESTION" "$stderr_b"
_assert_stderr_contains "test-b: offer is question-framed" "Was this a serial grind" "$stderr_b"
_assert_stderr_contains "test-b: offer acknowledges pilot-then-expand" "pilot-then-expand" "$stderr_b"
_assert_stderr_contains "test-b: offer names chunk count" "3 parallel-permitted chunks" "$stderr_b"
_assert_stderr_contains "test-b: offer acknowledges multi-plan mixing" "Multi-plan sessions may include" "$stderr_b"

# ---------------------------------------------------------------------------
# Test (c): gate-kind file-write-overlap forbids parallelism → silent (false-positive guard)
# EXACT-STRING NIT: canonical enum is `file-write-overlap` NOT `file-overlap`
# ---------------------------------------------------------------------------
echo ""
echo "Test (c): gate-kind file-write-overlap (serial gate) → silent, no offer"

dir_c="${TMPDIR_ROOT}/test_c"
_make_repo "$dir_c"

# Only 1 executor agent (would trigger if gate were parallel-permitted — it must NOT)
_write_agents_file "$dir_c" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100100')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100200')"

plan_c="${dir_c}/docs/plans/test-plan.md"
# All 3 chunks have runs:parallel but gate-kind:file-write-overlap (serial gate)
# These chunks are NOT parallel-permitted → denominator = 0 → no signal
_write_plan "$plan_c" \
'| 1 | C1 | chunk one | file1.sh | AC1 | file-write-overlap | parallel | 10 | pending |
| 2 | C2 | chunk two | file1.sh | AC2 | file-write-overlap | parallel | 10 | pending |
| 3 | C3 | chunk three | file1.sh | AC3 | file-write-overlap | parallel | 10 | pending |'

stderr_c="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_c" 2>&1)"
exit_c=$?

_assert_exit_zero "test-c: exit 0" "$exit_c"
_assert_stderr_not_contains "test-c: no offer on file-write-overlap (false-positive guard)" "DISPATCH SHAPE QUESTION" "$stderr_c"

# ---------------------------------------------------------------------------
# Test (d): [F1] mixed runs:parallel and inline (EM) rows → denominator counts only parallel
# Setup: 1 parallel chunk + 2 inline-EM chunks; 1 executor agent; should be SILENT
# (parallel_chunk_count = 1, threshold not reached)
# ---------------------------------------------------------------------------
echo ""
echo "Test (d): [F1] mixed parallel + inline (EM) rows → denominator counts only parallel rows"

dir_d="${TMPDIR_ROOT}/test_d"
_make_repo "$dir_d"

# 1 executor agent
_write_agents_file "$dir_d" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100000')"

plan_d="${dir_d}/docs/plans/test-plan.md"
# 1 parallel-permitted row + 2 inline (EM) rows
# F1: inline (EM) rows excluded from denominator; only 1 parallel row → count=1 → no signal
_write_plan "$plan_d" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | none | inline (EM) | 5 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | inline (EM) | 5 | pending |'

stderr_d="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_d" 2>&1)"
exit_d=$?

_assert_exit_zero "test-d: exit 0" "$exit_d"
_assert_stderr_not_contains "test-d: [F1] no false offer when only 1 parallel row" "DISPATCH SHAPE QUESTION" "$stderr_d"

# Secondary: 3 parallel rows + 2 inline-EM rows + 1 executor → OFFER (denominator=3)
dir_d2="${TMPDIR_ROOT}/test_d2"
_make_repo "$dir_d2"

_write_agents_file "$dir_d2" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100100')" \
  "$(printf 'agent-solo-001\tsonnet\tgeneral-purpose\t1782100200')"

plan_d2="${dir_d2}/docs/plans/test-plan.md"
_write_plan "$plan_d2" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |
| 4 | C4 | inline one | file4.sh | AC4 | none | inline (EM) | 5 | pending |
| 5 | C5 | inline two | file5.sh | AC5 | contract-change | inline (EM) | 5 | pending |'

stderr_d2="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_d2" 2>&1)"
exit_d2=$?

_assert_exit_zero "test-d2: exit 0 (always)" "$exit_d2"
_assert_stderr_contains "test-d2: [F1] offer when 3 parallel rows even with 2 inline-EM rows present" "DISPATCH SHAPE QUESTION" "$stderr_d2"

# ---------------------------------------------------------------------------
# [F3] Reviewer/scout agentId included in session window — confirm excluded from executor count
# Test: 3 parallel chunks + 1 executor agent + 2 reviewer agents → offer (1 executor, not 3)
# ---------------------------------------------------------------------------
echo ""
echo "Test [F3]: reviewer agents excluded from executor count"

dir_f3="${TMPDIR_ROOT}/test_f3"
_make_repo "$dir_f3"

# 1 executor (general-purpose) + 2 non-executor (reviewer, scout)
_write_agents_file "$dir_f3" \
  "$(printf 'agent-exec-001\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-rev-001\tunknown\tcoordinator:review-integrator\t1782100100')" \
  "$(printf 'agent-scout-001\tunknown\tcoordinator:staff-eng\t1782100200')"

plan_f3="${dir_f3}/docs/plans/test-plan.md"
_write_plan "$plan_f3" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |'

stderr_f3="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_f3" 2>&1)"
exit_f3=$?

_assert_exit_zero "test-f3: exit 0 (always)" "$exit_f3"
# With only 1 executor (reviewers excluded), offer should fire
_assert_stderr_contains "test-f3: [F3] offer fires (reviewer+scout excluded, only 1 executor)" "DISPATCH SHAPE QUESTION" "$stderr_f3"

# Contrast: 3 parallel chunks + 3 executor agents + reviewers → NO offer
dir_f3b="${TMPDIR_ROOT}/test_f3b"
_make_repo "$dir_f3b"

_write_agents_file "$dir_f3b" \
  "$(printf 'agent-exec-001\tsonnet\tgeneral-purpose\t1782100000')" \
  "$(printf 'agent-exec-002\tsonnet\tgeneral-purpose\t1782100050')" \
  "$(printf 'agent-exec-003\tsonnet\tgeneral-purpose\t1782100090')" \
  "$(printf 'agent-rev-001\tunknown\tcoordinator:review-integrator\t1782100100')" \
  "$(printf 'agent-scout-001\tunknown\tcoordinator:staff-eng\t1782100200')"

plan_f3b="${dir_f3b}/docs/plans/test-plan.md"
_write_plan "$plan_f3b" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |'

stderr_f3b="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_f3b" 2>&1)"
exit_f3b=$?

_assert_exit_zero "test-f3b: exit 0" "$exit_f3b"
_assert_stderr_not_contains "test-f3b: [F3] no offer when 3 distinct executors (reviewers excluded correctly)" "DISPATCH SHAPE QUESTION" "$stderr_f3b"

# ---------------------------------------------------------------------------
# Test [F7]: 3 parallel-permitted chunks + 0 executor-class agents (only reviewer/scout) → silent
# Zero executor count means no signal (denominator not ≤ 1 in the way that fires;
# distinct_executor_count == 0, which is not == 1, so no offer should be emitted).
# ---------------------------------------------------------------------------
echo ""
echo "Test [F7]: 3 parallel chunks + 0 executor agents (only reviewer/scout rows) → no offer"

dir_f7="${TMPDIR_ROOT}/test_f7"
_make_repo "$dir_f7"

# Review: code-reviewer — tests that zero executor-class agents (F3 filter removes all) → exit 0, no offer.
# Only reviewer and scout subagent_types — none qualify as executor-class.
_write_agents_file "$dir_f7" \
  "$(printf 'agent-rev-001\tunknown\tcoordinator:review-integrator\t1782100000')" \
  "$(printf 'agent-rev-002\tunknown\tcoordinator:review-integrator\t1782100100')" \
  "$(printf 'agent-scout-001\tunknown\tcoordinator:staff-eng\t1782100200')"

plan_f7="${dir_f7}/docs/plans/test-plan.md"
_write_plan "$plan_f7" \
'| 1 | C1 | chunk one | file1.sh | AC1 | none | parallel | 10 | pending |
| 2 | C2 | chunk two | file2.sh | AC2 | output-consumption-content | parallel | 10 | pending |
| 3 | C3 | chunk three | file3.sh | AC3 | contract-change | parallel | 10 | pending |'

stderr_f7="$(CLAUDE_CODE_SESSION_ID="$FIXTURE_SID" bash "$SUBJECT" --plan-file "$plan_f7" 2>&1)"
exit_f7=$?

_assert_exit_zero "test-f7: exit 0 (always)" "$exit_f7"
_assert_stderr_not_contains "test-f7: [F7] no offer when 0 executor agents (only reviewer/scout)" "DISPATCH SHAPE QUESTION" "$stderr_f7"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
echo ""

if [[ $FAIL -gt 0 ]]; then
  exit 1
else
  exit 0
fi
