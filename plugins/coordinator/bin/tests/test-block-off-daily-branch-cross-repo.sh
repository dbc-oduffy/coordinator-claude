#!/bin/bash
# test-block-off-daily-branch-cross-repo.sh — Cross-repo regression matrix
#
# Spec backlink: ~/.claude/plans/2026-05-08-daily-branch-discipline-cross-repo.md
# Covers: 14-case matrix (was 12 + 3 new pathspec regression cases):
#   3 cross-repo forms × 4 parser arms + 3 cheap-gate pathspec regression cases
#   Forms: git -C <path> (relaxed), git --git-dir=<path>/.git (relaxed),
#          cd <path> && git (kept deny)
#   Arms:  create (-b), switch-existing (positional), switch-@{-1} (-),
#          worktree-add
#   Pathspec regressions: read-only git ops with "branch" in the pathspec must
#   not trigger the cheap gate (BS-2026-05-08-001 — over-match on bare branch keyword).
#   Spec backlink: archive/handoffs/2026-05-08_143000_post-split-cleanup-followups-2.md
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-block-off-daily-branch-cross-repo.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${SCRIPT_DIR}/../../hooks/scripts/block-off-daily-branch.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FATAL: hook not found at $HOOK" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test framework (mirrors test-block-off-daily-branch.sh convention)
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
# Sibling repo fixture setup
# ---------------------------------------------------------------------------
# We need a real temp git repo so is_local_branch can resolve refs/heads/*.
# The sibling repo has:
#   main                          (shape-canonical, allowed)
#   work/striker/2026-05-08       (shape-canonical, allowed)
#   feature/not-allowed           (off-shape, should be denied)
# The @{-1} previous-branch arm is tested via the hook's git rev-parse call,
# which queries the sibling repo's reflog. We set up a two-commit history so
# @{-1} resolves to an allowed branch.

SIBLING_REPO=""
cleanup_sibling() {
  if [[ -n "$SIBLING_REPO" && -d "$SIBLING_REPO" ]]; then
    rm -rf "$SIBLING_REPO" 2>/dev/null || true
  fi
}
trap cleanup_sibling EXIT

setup_sibling_repo() {
  SIBLING_REPO="$(mktemp -d)"
  (
    cd "$SIBLING_REPO"
    git init -q
    git config user.email "test@test.com"
    git config user.name "Test"
    # Initial commit on main
    git checkout -q -b main 2>/dev/null || git checkout -q -b main
    echo "init" > README.md
    git add README.md
    git commit -q -m "init"
    # Create canonical workstream branch (switch so @{-1} = main after switch back)
    git checkout -q -b work/striker/2026-05-08
    echo "work" >> README.md
    git add README.md
    git commit -q -m "work commit"
    # Switch back to main so @{-1} = work/striker/2026-05-08
    git checkout -q main
    # @{-1} is now work/striker/2026-05-08 (an allowed branch)
  ) 2>/dev/null
}

echo "=== Setting up sibling repo fixture..."
setup_sibling_repo
if [[ -z "$SIBLING_REPO" || ! -d "$SIBLING_REPO/.git" ]]; then
  echo "FATAL: sibling repo setup failed" >&2
  exit 1
fi
echo "    Sibling repo: $SIBLING_REPO"
echo ""

# ---------------------------------------------------------------------------
# Form 1: git -C <path> (RELAXED — parser applies shape policy)
# ---------------------------------------------------------------------------

# ARM 1: Create (-b) — shape-canonical → ALLOW
test_git_c_create_canonical_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} checkout -b work/striker/2026-05-09\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C create shape-canonical" "$output"
}

# ARM 1: Create (-b) — off-shape → DENY
test_git_c_create_offshape_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} checkout -b feature/foo\"},\"session_id\":\"test\"}")
  assert_deny "git -C create off-shape denied" "$output"
}

# ARM 2: Switch-existing — allowed branch in sibling → ALLOW
test_git_c_switch_existing_allowed() {
  local output
  # work/striker/2026-05-08 exists in sibling repo; is_allowed_branch → true
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} checkout work/striker/2026-05-08\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C switch-existing canonical branch allowed" "$output"
}

# ARM 3: Switch @{-1} (-) — previous branch was allowed → ALLOW
test_git_c_switch_prev_allowed() {
  local output
  # In the sibling repo, @{-1} is work/striker/2026-05-08 (allowed)
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} checkout -\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C switch-@{-1} previous=allowed" "$output"
}

# ARM 4: Worktree-add — DENY (doctrine ban, repo-agnostic)
test_git_c_worktree_add_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} worktree add /tmp/wt\"},\"session_id\":\"test\"}")
  assert_deny "git -C worktree add denied (doctrine)" "$output"
}

# ---------------------------------------------------------------------------
# Form 2: git --git-dir=<path>/.git (RELAXED — parser applies shape policy)
# ---------------------------------------------------------------------------

# ARM 1: Create (-b) — shape-canonical → ALLOW
test_git_gitdir_create_canonical_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git --git-dir=${SIBLING_REPO}/.git checkout -b work/striker/2026-05-09\"},\"session_id\":\"test\"}")
  assert_no_deny "git --git-dir create shape-canonical allowed" "$output"
}

# ARM 1: Create (-b) — off-shape → DENY
test_git_gitdir_create_offshape_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git --git-dir=${SIBLING_REPO}/.git checkout -b feature/bar\"},\"session_id\":\"test\"}")
  assert_deny "git --git-dir create off-shape denied" "$output"
}

# ARM 2: Switch-existing — positional branch arg → ALLOW
# For --git-dir, op_repo_root stays as $GIT_ROOT (we don't extract the work-tree
# root from a .git path — a documented scope note in the hook). The switch-existing
# arm will call is_local_branch against $GIT_ROOT. If the branch doesn't exist
# there, is_local_branch returns false → the hook exits 0 (treats as sha/tag/detached).
# This is the correct safe-direction: no deny.
test_git_gitdir_switch_existing_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git --git-dir=${SIBLING_REPO}/.git checkout main\"},\"session_id\":\"test\"}")
  assert_no_deny "git --git-dir switch-existing allowed (falls through as non-local-branch)" "$output"
}

# ARM 3: Switch @{-1} (-) — ALLOW (falls through; @{-1} query runs against GIT_ROOT
# which may not have a previous branch in test context; if unresolvable → allow)
test_git_gitdir_switch_prev_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git --git-dir=${SIBLING_REPO}/.git checkout -\"},\"session_id\":\"test\"}")
  # If @{-1} unresolvable, hook exits 0 (allow). Either way, not a deny.
  assert_no_deny "git --git-dir switch-@{-1} not denied" "$output"
}

# ARM 4: Worktree-add — DENY (doctrine ban, repo-agnostic)
test_git_gitdir_worktree_add_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git --git-dir=${SIBLING_REPO}/.git worktree add /tmp/wt2\"},\"session_id\":\"test\"}")
  assert_deny "git --git-dir worktree add denied (doctrine)" "$output"
}

# ---------------------------------------------------------------------------
# Form 3: cd <path> && git (KEPT DENY — cwd-tracking out of scope)
# ---------------------------------------------------------------------------

# ARM 1: Create (-b) — DENY regardless of shape
test_cd_git_create_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd ${SIBLING_REPO} && git checkout -b work/striker/2026-05-09\"},\"session_id\":\"test\"}")
  assert_deny "cd && git create denied (kept deny)" "$output"
}

# ARM 2: Switch-existing — DENY regardless of branch name
test_cd_git_switch_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd ${SIBLING_REPO} && git checkout main\"},\"session_id\":\"test\"}")
  assert_deny "cd && git switch-existing denied (kept deny)" "$output"
}

# ARM 3: Switch @{-1} (-) — DENY
test_cd_git_switch_prev_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd ${SIBLING_REPO} && git checkout -\"},\"session_id\":\"test\"}")
  assert_deny "cd && git switch-@{-1} denied (kept deny)" "$output"
}

# ARM 4: Worktree-add — DENY
test_cd_git_worktree_add_denied() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd ${SIBLING_REPO} && git worktree add /tmp/wt3\"},\"session_id\":\"test\"}")
  assert_deny "cd && git worktree add denied (kept deny)" "$output"
}

# ---------------------------------------------------------------------------
# Cheap-gate pathspec regression (BS-2026-05-08-001)
# Spec: archive/handoffs/2026-05-08_143000_post-split-cleanup-followups-2.md
#
# Read-only git subcommands (status, log, diff) with "branch" appearing in a
# pathspec after the "--" separator must NOT trigger the cheap gate or be denied.
# The old [^|;&]* in the second arm would cross the "--" boundary and match
# "branch" inside the pathspec. The tightened ([^|;&-]|-[^-]|--[^[:space:]])*
# pattern stops at the bare " -- " separator.
# ---------------------------------------------------------------------------

# ALLOW: git -C <path> status with branch in pathspec
test_git_c_status_branch_in_pathspec_allowed() {
  local output
  # status is read-only; "branch" appears only in the pathspec after "--"
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} status --short -- plans/2026-05-08-daily-branch-discipline-cross-repo.md\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C status -- pathspec with branch in name: not denied" "$output"
}

# ALLOW: git -C <path> log with branch in pathspec
test_git_c_log_branch_in_pathspec_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} log --oneline -- plans/branch-thing.md\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C log -- pathspec with branch in name: not denied" "$output"
}

# ALLOW: git -C <path> diff with branch in pathspec directory
test_git_c_diff_branch_in_pathspec_allowed() {
  local output
  output=$(pipe_hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git -C ${SIBLING_REPO} diff -- some/branch/path.md\"},\"session_id\":\"test\"}")
  assert_no_deny "git -C diff -- pathspec with branch directory component: not denied" "$output"
}

# ---------------------------------------------------------------------------
# Run all 17 matrix cases (14 original + 3 pathspec regression)
# ---------------------------------------------------------------------------

echo "=== block-off-daily-branch.sh cross-repo regression matrix ==="
echo ""
echo "--- Form 1: git -C <path> (relaxed)"

run_test "git -C: create arm — shape-canonical ALLOW" test_git_c_create_canonical_allowed
run_test "git -C: create arm — off-shape DENY" test_git_c_create_offshape_denied
run_test "git -C: switch-existing arm — canonical branch ALLOW" test_git_c_switch_existing_allowed
run_test "git -C: switch-@{-1} arm — previous=allowed ALLOW" test_git_c_switch_prev_allowed
run_test "git -C: worktree-add arm — doctrine DENY" test_git_c_worktree_add_denied

echo ""
echo "--- Form 2: git --git-dir=<path>/.git (relaxed)"

run_test "git --git-dir: create arm — shape-canonical ALLOW" test_git_gitdir_create_canonical_allowed
run_test "git --git-dir: create arm — off-shape DENY" test_git_gitdir_create_offshape_denied
run_test "git --git-dir: switch-existing arm — not denied" test_git_gitdir_switch_existing_allowed
run_test "git --git-dir: switch-@{-1} arm — not denied" test_git_gitdir_switch_prev_allowed
run_test "git --git-dir: worktree-add arm — doctrine DENY" test_git_gitdir_worktree_add_denied

echo ""
echo "--- Form 3: cd <path> && git (kept deny)"

run_test "cd && git: create arm — DENY" test_cd_git_create_denied
run_test "cd && git: switch-existing arm — DENY" test_cd_git_switch_denied
run_test "cd && git: switch-@{-1} arm — DENY" test_cd_git_switch_prev_denied
run_test "cd && git: worktree-add arm — DENY" test_cd_git_worktree_add_denied

echo ""
echo "--- Pathspec regression (BS-2026-05-08-001): read-only ops with branch in pathspec"

run_test "pathspec: git -C status -- branch-named file ALLOW" test_git_c_status_branch_in_pathspec_allowed
run_test "pathspec: git -C log -- branch-named file ALLOW" test_git_c_log_branch_in_pathspec_allowed
run_test "pathspec: git -C diff -- branch-dir/path ALLOW" test_git_c_diff_branch_in_pathspec_allowed

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
if (( FAIL > 0 )); then
  echo ""
  echo "Failed tests:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
  exit 1
fi
exit 0
