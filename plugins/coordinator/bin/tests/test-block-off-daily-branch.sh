#!/bin/bash
# test-block-off-daily-branch.sh — Regression tests for block-off-daily-branch.sh
#
# Spec backlink: docs/plans/2026-05-07-daily-branch-doctrine-rethink.md Phase 2
# Covers: AC-2 (commit-block removed), AC-3 (orphan-branch prevention preserved),
#         AC-4 (span branches accepted), AC-10 (case-insensitive legacy tolerance)
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-block-off-daily-branch.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${SCRIPT_DIR}/../../hooks/scripts/block-off-daily-branch.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FATAL: hook not found at $HOOK" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

run_test() {
  local name="$1"
  local fn="$2"
  echo "--- $name"
  if "$fn"; then
    pass "$name"
  else
    fail "$name"
  fi
}

# pipe_hook <json> — pipe JSON input to the hook and capture stdout
pipe_hook() {
  local json="$1"
  echo "$json" | bash "$HOOK" 2>/dev/null || true
}

# assert_no_deny <label> <output> — asserts output does NOT contain deny JSON
assert_no_deny() {
  local label="$1" output="$2"
  if echo "$output" | grep -q '"permissionDecision":"deny"'; then
    echo "    Expected: no deny JSON" >&2
    echo "    Got: $output" >&2
    return 1
  fi
  return 0
}

# assert_deny <label> <output> — asserts output DOES contain deny JSON
assert_deny() {
  local label="$1" output="$2"
  if ! echo "$output" | grep -q '"permissionDecision":"deny"'; then
    echo "    Expected: deny JSON" >&2
    echo "    Got: $(printf '%q' "$output")" >&2
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# AC-2: git commit no longer denied (commit-block removed)
# ---------------------------------------------------------------------------

test_commit_on_old_daily_not_denied() {
  # Regression: this was the exact block we hit — committing on work/striker/2026-05-06
  # when today is 2026-05-07 used to deny; now it must pass through.
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"},"session_id":"smoke"}')
  assert_no_deny "commit on old daily" "$output"
}

test_commit_with_message_not_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"wip: crossing midnight\""},"session_id":"smoke"}')
  assert_no_deny "commit with message" "$output"
}

test_commit_amend_not_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git commit --amend --no-edit"},"session_id":"smoke"}')
  assert_no_deny "git commit --amend" "$output"
}

# ---------------------------------------------------------------------------
# AC-3: orphan-branch creation still denied
# ---------------------------------------------------------------------------

test_checkout_b_feature_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout -b feature/X"},"session_id":"smoke"}')
  assert_deny "git checkout -b feature/X denied" "$output"
}

test_switch_c_feature_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git switch -c feature/new-thing"},"session_id":"smoke"}')
  assert_deny "git switch -c feature/new-thing denied" "$output"
}

test_branch_m_feature_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git branch -m feature/renamed"},"session_id":"smoke"}')
  assert_deny "git branch -m feature/renamed denied" "$output"
}

# ---------------------------------------------------------------------------
# AC-4: span-form branch names accepted
# ---------------------------------------------------------------------------

test_checkout_b_span_branch_allowed() {
  # Creating a span branch should be allowed (shape is valid)
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout -b work/striker/2026-05-07to08"},"session_id":"smoke"}')
  assert_no_deny "git checkout -b work/striker/2026-05-07to08" "$output"
}

test_switch_c_span_branch_allowed() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git switch -c work/striker/2026-05-06to09"},"session_id":"smoke"}')
  assert_no_deny "git switch -c work/striker/2026-05-06to09" "$output"
}

# ---------------------------------------------------------------------------
# Canonical-case creation enforcement (HEAD vs on-disk case-mismatch prevention,
# 2026-05-07 spinoff). Branch CREATION arms must reject mixed-case work/* names
# even though they parse as allowed shape; SWITCH-TO-EXISTING arms keep
# accepting them so the migration script can rename them.
# ---------------------------------------------------------------------------

test_checkout_b_mixed_case_machine_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout -b work/STRIKER/2026-05-07"},"session_id":"smoke"}')
  assert_deny "git checkout -b work/STRIKER/2026-05-07 denied (non-canonical case)" "$output" || return 1
  # Hint check: deny message should propose the canonical form.
  if ! echo "$output" | grep -q 'Canonical form'; then
    echo "    Expected: deny output to include 'Canonical form' hint" >&2
    echo "    Got: $output" >&2
    return 1
  fi
}

test_checkout_b_canonical_lowercase_allowed() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout -b work/striker/2026-05-07"},"session_id":"smoke"}')
  assert_no_deny "git checkout -b work/striker/2026-05-07 allowed" "$output"
}

test_checkout_b_mixed_case_span_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout -b work/STRIKER/2026-05-07to08"},"session_id":"smoke"}')
  assert_deny "git checkout -b work/STRIKER/2026-05-07to08 denied" "$output"
}

test_branch_m_to_mixed_case_denied() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git branch -m work/striker/2026-05-07 work/STRIKER/2026-05-07"},"session_id":"smoke"}')
  assert_deny "git branch -m to mixed-case denied" "$output"
}

# ---------------------------------------------------------------------------
# AC-10: case-insensitive legacy tolerance
# ---------------------------------------------------------------------------

test_checkout_legacy_uppercase_branch_allowed() {
  # work/STRIKER/2026-05-07 is a legacy uppercase branch; hook must accept it
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git checkout work/STRIKER/2026-05-07"},"session_id":"smoke"}')
  # Note: git checkout (switch-to) of a local branch: would only deny if is_local_branch returns true
  # and cs_is_allowed_branch fails. Since cs_is_allowed_branch is case-insensitive, this should pass.
  assert_no_deny "git checkout work/STRIKER/2026-05-07 (legacy uppercase)" "$output"
}

# ---------------------------------------------------------------------------
# Sanity: non-git commands pass through
# ---------------------------------------------------------------------------

test_non_git_command_passes() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"echo hello world"},"session_id":"smoke"}')
  assert_no_deny "non-git command passes" "$output"
}

test_git_log_passes() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git log --oneline -5"},"session_id":"smoke"}')
  assert_no_deny "git log passes" "$output"
}

test_git_status_passes() {
  local output
  output=$(pipe_hook '{"tool_name":"Bash","tool_input":{"command":"git status"},"session_id":"smoke"}')
  assert_no_deny "git status passes" "$output"
}

# ---------------------------------------------------------------------------
# Override escape hatch: COORDINATOR_OVERRIDE_BRANCH=1 bypasses everything
# ---------------------------------------------------------------------------

test_override_bypasses_feature_branch() {
  local output
  output=$(echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b feature/override-test"},"session_id":"smoke"}' \
    | COORDINATOR_OVERRIDE_BRANCH=1 bash "$HOOK" 2>/dev/null || true)
  assert_no_deny "override bypasses feature/X deny" "$output"
}

# Inline-prefix override — required because env-var prefixes don't propagate
# from the user's bash command into the hook's env (the hook is a child of
# Claude Code, not of the user's shell). The hook parses $COMMAND for the
# literal prefix and treats it equivalently to the env-var override.
test_inline_override_bypasses_feature_branch() {
  local output
  output=$(echo '{"tool_name":"Bash","tool_input":{"command":"COORDINATOR_OVERRIDE_BRANCH=1 git checkout -b feature/inline-override-test"},"session_id":"smoke"}' \
    | bash "$HOOK" 2>/dev/null || true)
  assert_no_deny "inline override bypasses feature/X deny" "$output"
}

# Inline override with a paired REASON env var — common real-world shape.
test_inline_override_with_reason_bypasses() {
  local output
  output=$(echo '{"tool_name":"Bash","tool_input":{"command":"COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON=spec-test git stash branch foo"},"session_id":"smoke"}' \
    | bash "$HOOK" 2>/dev/null || true)
  assert_no_deny "inline override with reason bypasses deny" "$output"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

echo "=== block-off-daily-branch.sh regression tests ==="
echo ""

run_test "AC-2: git commit not denied (old daily)" test_commit_on_old_daily_not_denied
run_test "AC-2: git commit with message not denied" test_commit_with_message_not_denied
run_test "AC-2: git commit --amend not denied" test_commit_amend_not_denied

run_test "AC-3: git checkout -b feature/X denied" test_checkout_b_feature_denied
run_test "AC-3: git switch -c feature/new denied" test_switch_c_feature_denied
run_test "AC-3: git branch -m feature/renamed denied" test_branch_m_feature_denied

run_test "AC-4: git checkout -b span branch allowed" test_checkout_b_span_branch_allowed
run_test "AC-4: git switch -c span branch allowed" test_switch_c_span_branch_allowed

run_test "canonical-case: git checkout -b mixed-case machine denied" test_checkout_b_mixed_case_machine_denied
run_test "canonical-case: git checkout -b lowercase canonical allowed" test_checkout_b_canonical_lowercase_allowed
run_test "canonical-case: git checkout -b mixed-case span denied" test_checkout_b_mixed_case_span_denied
run_test "canonical-case: git branch -m to mixed-case denied" test_branch_m_to_mixed_case_denied

run_test "AC-10: git checkout legacy uppercase branch allowed" test_checkout_legacy_uppercase_branch_allowed

run_test "sanity: non-git command passes" test_non_git_command_passes
run_test "sanity: git log passes" test_git_log_passes
run_test "sanity: git status passes" test_git_status_passes

run_test "override: COORDINATOR_OVERRIDE_BRANCH=1 bypasses deny" test_override_bypasses_feature_branch
run_test "override: inline COORDINATOR_OVERRIDE_BRANCH=1 prefix bypasses deny" test_inline_override_bypasses_feature_branch
run_test "override: inline override with REASON bypasses deny" test_inline_override_with_reason_bypasses

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
if (( FAIL > 0 )); then
  echo ""
  echo "Failed tests:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
  exit 1
fi
exit 0
