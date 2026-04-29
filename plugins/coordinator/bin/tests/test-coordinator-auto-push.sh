#!/bin/bash
# test-coordinator-auto-push.sh — Test suite for coordinator-auto-push post-commit hook.
#
# Uses a PATH-shim containing a fake `git` script to intercept push calls
# without touching any real remote. The fake git records argv to a file
# and exits with FAKE_GIT_EXIT_CODE (default 0). Non-push git calls are
# forwarded to the real git binary (resolved BEFORE the shim goes into PATH).
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-coordinator-auto-push.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/../coordinator-auto-push"

# Resolve real git BEFORE any PATH manipulation (avoids shim self-recursion)
REAL_GIT="$(command -v git)"

# ---------------------------------------------------------------------------
# Test framework (mirrors test-coordinator-safe-commit.sh style)
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
  "$fn" && pass "$name" || fail "$name"
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    return 0
  else
    echo "    Expected to contain: ${needle}" >&2
    echo "    In: ${haystack}" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Scratch repo + PATH shim setup / teardown
# ---------------------------------------------------------------------------

SCRATCH_DIR=""
SHIM_DIR=""
ORIG_DIR="$(pwd)"
ORIG_PATH="$PATH"

setup_repo() {
  local branch="${1:-work/test-fixture}"
  SCRATCH_DIR=$(mktemp -d)
  cd "$SCRATCH_DIR"
  "$REAL_GIT" init -q
  "$REAL_GIT" config user.email "test@test.example"
  "$REAL_GIT" config user.name "Test"
  echo "root" > root.txt
  "$REAL_GIT" add root.txt
  "$REAL_GIT" commit -q -m "init"
  # Create requested branch (default repo starts on 'main' or 'master')
  local current_branch
  current_branch=$("$REAL_GIT" branch --show-current)
  if [[ "$branch" == "main" || "$branch" == "$current_branch" ]]; then
    # Already on the right branch (or close enough — rename if needed)
    if [[ "$current_branch" != "$branch" ]]; then
      "$REAL_GIT" checkout -q -b "$branch"
    fi
  else
    "$REAL_GIT" checkout -q -b "$branch"
  fi
  # Configure a fake remote URL (HTTPS — avoids SSH-routing detection)
  "$REAL_GIT" remote add origin "https://github.com/fake-org/fake-repo.git"
}

setup_fake_git_shim() {
  local exit_code="${1:-0}"
  ARGV_LOG="${SCRATCH_DIR}/.git/fake-git-argv.log"
  SHIM_DIR=$(mktemp -d)
  # Write the shim with REAL_GIT hardcoded so it doesn't recurse via PATH lookup
  cat > "${SHIM_DIR}/git" <<SHIMEOF
#!/bin/bash
# Fake git shim — intercepts push calls, forwards everything else to real git.
# REAL_GIT is hardcoded at shim-creation time to avoid self-recursion via PATH.
for arg in "\$@"; do
  if [[ "\$arg" == "push" ]]; then
    echo "\$*" >> "${ARGV_LOG}"
    exit ${exit_code}
  fi
done
exec "${REAL_GIT}" "\$@"
SHIMEOF
  chmod +x "${SHIM_DIR}/git"
  export PATH="${SHIM_DIR}:${ORIG_PATH}"
}

teardown_all() {
  cd "$ORIG_DIR"
  export PATH="$ORIG_PATH"
  if [[ -n "$SCRATCH_DIR" && -d "$SCRATCH_DIR" ]]; then
    rm -rf "$SCRATCH_DIR"
  fi
  if [[ -n "$SHIM_DIR" && -d "$SHIM_DIR" ]]; then
    rm -rf "$SHIM_DIR"
  fi
  SCRATCH_DIR=""
  SHIM_DIR=""
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# T1: work/* branch — push is invoked with correct argv
test_work_branch_push_invoked() {
  setup_repo "work/test-fixture"
  setup_fake_git_shim 0

  bash "$HELPER"
  local rc=$?

  local argv_log="${SCRATCH_DIR}/.git/fake-git-argv.log"
  local recorded_argv=""
  [[ -f "$argv_log" ]] && recorded_argv=$(cat "$argv_log")

  teardown_all

  [[ $rc -eq 0 ]] \
    && assert_contains "T1" "push origin work/test-fixture" "$recorded_argv"
}

# T2: main branch — push is skipped (no argv recorded)
test_main_branch_push_skipped() {
  setup_repo "main"
  setup_fake_git_shim 0

  bash "$HELPER"
  local rc=$?

  local argv_log="${SCRATCH_DIR}/.git/fake-git-argv.log"
  local has_log=false
  [[ -f "$argv_log" ]] && has_log=true

  teardown_all

  # Must exit 0 AND not record any push call
  [[ $rc -eq 0 ]] && [[ "$has_log" == false ]]
}

# T3: feature/* branch — push is invoked
test_feature_branch_push_invoked() {
  setup_repo "feature/my-feature"
  setup_fake_git_shim 0

  bash "$HELPER"
  local rc=$?

  local argv_log="${SCRATCH_DIR}/.git/fake-git-argv.log"
  local recorded_argv=""
  [[ -f "$argv_log" ]] && recorded_argv=$(cat "$argv_log")

  teardown_all

  [[ $rc -eq 0 ]] \
    && assert_contains "T3" "push origin feature/my-feature" "$recorded_argv"
}

# T4: Push failure (fake git exits non-zero) — push-failures.log is written,
#     coordinator-auto-push itself exits 0 (must never block a commit)
test_push_failure_logged_exit_zero() {
  setup_repo "work/test-fixture"
  setup_fake_git_shim 1   # fake git exits non-zero on push

  bash "$HELPER"
  local rc=$?

  local failure_log="${SCRATCH_DIR}/.git/push-failures.log"
  local log_has_content=false
  if [[ -f "$failure_log" ]] && [[ -s "$failure_log" ]]; then
    log_has_content=true
  fi

  teardown_all

  # Hook must exit 0 even on push failure
  [[ $rc -eq 0 ]] && [[ "$log_has_content" == true ]]
}

# T5: SSH remote on non-Windows — goes through direct git push (not powershell)
#     We verify the push call makes it to the fake git (recorded in argv log).
test_ssh_remote_non_windows_direct_push() {
  setup_repo "work/test-fixture"
  # Override remote to SSH URL
  "$REAL_GIT" remote set-url origin "git@github.com:fake-org/fake-repo.git"
  setup_fake_git_shim 0

  # Run without MSYSTEM to simulate non-Windows
  MSYSTEM="" OS="" bash "$HELPER"
  local rc=$?

  local argv_log="${SCRATCH_DIR}/.git/fake-git-argv.log"
  local recorded_argv=""
  [[ -f "$argv_log" ]] && recorded_argv=$(cat "$argv_log")

  teardown_all

  # On non-Windows the direct-git path runs (not powershell), so push is recorded
  [[ $rc -eq 0 ]] \
    && assert_contains "T5" "push origin work/test-fixture" "$recorded_argv"
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

echo "============================================"
echo " coordinator-auto-push test suite"
echo "============================================"
echo ""

run_test "T1: work/* branch — push argv recorded correctly"    test_work_branch_push_invoked
run_test "T2: main branch — push skipped"                      test_main_branch_push_skipped
run_test "T3: feature/* branch — push argv recorded correctly" test_feature_branch_push_invoked
run_test "T4: push failure — log written, hook exits 0"        test_push_failure_logged_exit_zero
run_test "T5: SSH remote (non-Windows) — direct push path"     test_ssh_remote_non_windows_direct_push

echo ""
echo "============================================"
echo " Results: ${PASS} passed, ${FAIL} failed"
echo "============================================"

if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
fi

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
