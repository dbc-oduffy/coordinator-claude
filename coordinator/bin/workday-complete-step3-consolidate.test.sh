#!/usr/bin/env bash
# workday-complete-step3-consolidate.test.sh — smoke tests for Step 3 consolidation script.
#
# Purpose: validates the branch-consolidation logic in workday-complete-step3-consolidate.sh
# using isolated temp git repos with file-system remotes. Never touches the real
# ~/.claude repo or its origin.
#
# Spec backlink: commands/workday-complete.md lines 145-196
#
# Usage:
#   bash workday-complete-step3-consolidate.test.sh
#
# Exit: 0 all tests pass, 1 any test fails.

set -uo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash 4+ required. Run: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate the script under test
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEP3="${SCRIPT_DIR}/workday-complete-step3-consolidate.sh"

if [[ ! -f "$STEP3" ]]; then
  echo "ERROR: script under test not found: $STEP3" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
TMPDIR_ROOT=""

cleanup() {
  if [[ -n "$TMPDIR_ROOT" && -d "$TMPDIR_ROOT" ]]; then
    rm -rf "$TMPDIR_ROOT"
  fi
}
trap cleanup EXIT

_pass() {
  echo "PASS: $1"
  PASS=$(( PASS + 1 ))
}

_fail() {
  echo "FAIL: $1 — $2"
  FAIL=$(( FAIL + 1 ))
}

# ---------------------------------------------------------------------------
# Fixture builder
#
# _make_repo <dir>
#   Creates a bare "origin" remote + a working clone pre-configured with
#   user.name/user.email so commits work in sandboxed env.
#   Sets COORDINATOR_MACHINE to "striker" to ensure cs_compute_machine
#   produces a deterministic result regardless of the test machine's hostname.
#
# On entry sets:
#   ORIGIN_DIR  — bare repo (fake remote)
#   WORK_DIR    — working clone
#   TODAY       — current UTC date (YYYY-MM-DD)
#   MACHINE     — "striker" (fixed for tests)
# ---------------------------------------------------------------------------
_make_repo() {
  local base="$1"
  ORIGIN_DIR="${base}/origin.git"
  WORK_DIR="${base}/work"
  TODAY=$(date -u +%Y-%m-%d)
  MACHINE="striker"

  # Bare repo acts as the fake remote
  git init --bare "$ORIGIN_DIR" >/dev/null 2>&1

  # Clone into working dir
  git clone "$ORIGIN_DIR" "$WORK_DIR" >/dev/null 2>&1
  cd "$WORK_DIR"

  # Identity for commits
  git config user.email "test@test.local"
  git config user.name "Test"

  # Seed origin/main with an initial commit
  echo "seed" > seed.txt
  git add seed.txt
  git commit -m "initial" >/dev/null 2>&1
  git push -u origin main >/dev/null 2>&1
}

# _add_commit <message> [<file>]
#   Adds a commit on the current branch.
_add_commit() {
  local msg="$1"
  local file="${2:-commit-${msg// /-}.txt}"
  echo "$msg" > "$file"
  git add "$file"
  git commit -m "$msg" >/dev/null 2>&1
}

# _run_step3 [args...]
#   Invokes the script under test with COORDINATOR_MACHINE=striker and
#   the plugin root pointing at the real plugin (for lib sourcing) but
#   with a stub sync-main.sh that is a no-op (to avoid real network ops).
#
# Returns the exit code in STEP3_RC and combined stdout+stderr in STEP3_OUT.
_run_step3() {
  local plugin_root
  plugin_root="$(cd "${SCRIPT_DIR}/.." && pwd)"

  # Provide a stub sync-main.sh in a temp bin dir so the script doesn't
  # attempt network operations. We prepend that dir to PATH.
  local stub_bin
  stub_bin="$(mktemp -d)"
  cat > "${stub_bin}/sync-main.sh" <<'STUB'
#!/usr/bin/env bash
# stub: no-op sync-main for tests
exit 0
STUB
  chmod +x "${stub_bin}/sync-main.sh"

  # The script discovers its PLUGIN_ROOT from __BASH_SOURCE[0]__ so it will
  # find the real lib/coordinator-daily-branch.sh. We only need to override
  # the bin/sync-main.sh lookup. The script builds BIN_SYNC_MAIN as
  # "${PLUGIN_ROOT}/bin/sync-main.sh" — we cannot easily override it via
  # PATH because the script uses absolute path. Instead we temporarily
  # replace sync-main.sh with a symlink to our stub, then restore.
  local real_sync="${plugin_root}/bin/sync-main.sh"
  local backup_sync="${stub_bin}/sync-main.sh.bak"

  # Non-destructive: only shadow if the file exists
  # We write a wrapper that immediately calls exit 0
  local saved_content
  saved_content=$(cat "$real_sync")
  local stub_content
  stub_content=$'#!/usr/bin/env bash\n# test-stub: no-op sync-main\nexit 0'
  printf '%s\n' "$stub_content" > "$real_sync"

  STEP3_RC=0
  STEP3_OUT=$(COORDINATOR_MACHINE="striker" "$BASH" "$STEP3" "$@" 2>&1) || STEP3_RC=$?

  # Restore the real sync-main.sh
  printf '%s\n' "$saved_content" > "$real_sync"

  rm -rf "$stub_bin"
}

# ---------------------------------------------------------------------------
# Test 1: No siblings, branch ahead of origin/main → ahead-only reconcile, push, exit 0
# ---------------------------------------------------------------------------
test_1_no_siblings_ahead() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Cut workstream branch and add a commit (now ahead of origin/main)
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "ahead-commit"

  _run_step3
  cd "$WORK_DIR"  # restore cwd after _run_step3

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test1" "expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "reconcile: no-op (ahead-only)"; then
    _fail "test1" "expected ahead-only reconcile. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "push: ok"; then
    _fail "test1" "expected push ok. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test1 (no siblings, ahead of origin/main)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 2: No siblings, branch matches origin/main exactly → no-op reconcile, push, idempotency
# ---------------------------------------------------------------------------
test_2_no_siblings_current() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Workstream branch at same SHA as origin/main (zero ahead)
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  # No extra commits — HEAD is at same place as origin/main

  _run_step3
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test2" "first run: expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "\[step3\] OK"; then
    _fail "test2" "first run: expected OK. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi

  # Second run — idempotency check
  _run_step3
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test2" "second run (idempotency): expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "\[step3\] OK"; then
    _fail "test2" "second run (idempotency): expected OK. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test2 (no siblings, matches origin/main; idempotent)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 3: One sibling with non-conflicting commits → merged, pushed, sibling deleted, exit 0
# ---------------------------------------------------------------------------
test_3_sibling_non_conflicting() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Main workstream branch
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "main-branch-commit" "file-main.txt"

  # Sibling branch with non-conflicting commit (different file)
  git checkout -b "work/striker/${TODAY}-2" >/dev/null 2>&1
  _add_commit "sibling-commit" "file-sibling.txt"
  git push -u origin "work/striker/${TODAY}-2" >/dev/null 2>&1

  # Return to main workstream branch
  git checkout "work/striker/${TODAY}" >/dev/null 2>&1

  _run_step3
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test3" "expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "siblings merged: 1"; then
    _fail "test3" "expected siblings merged: 1. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "siblings deleted: 1"; then
    _fail "test3" "expected siblings deleted: 1. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "\[step3\] OK"; then
    _fail "test3" "expected OK. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  # Verify sibling is gone
  if git -C "$WORK_DIR" branch --list "work/striker/${TODAY}-2" | grep -q "work/striker/${TODAY}-2"; then
    _fail "test3" "sibling branch was not deleted"
    rm -rf "$base"; return
  fi
  _pass "test3 (sibling non-conflicting: merged, pushed, deleted)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 4: One sibling with conflicting commits → exit 2, current branch unchanged
# ---------------------------------------------------------------------------
test_4_sibling_conflict() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Main workstream branch with a commit on conflict.txt
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  echo "main version" > conflict.txt
  git add conflict.txt
  git commit -m "main: conflict.txt version A" >/dev/null 2>&1

  # Sibling: branch from the initial commit, write conflicting content
  git checkout main >/dev/null 2>&1
  git checkout -b "work/striker/${TODAY}-2" >/dev/null 2>&1
  echo "sibling version" > conflict.txt
  git add conflict.txt
  git commit -m "sibling: conflict.txt version B" >/dev/null 2>&1

  # Return to main workstream branch
  git checkout "work/striker/${TODAY}" >/dev/null 2>&1

  # Record HEAD before the merge attempt
  HEAD_BEFORE=$(git rev-parse HEAD)

  _run_step3
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 2 ]]; then
    _fail "test4" "expected exit 2 (merge conflict), got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  HEAD_AFTER=$(git rev-parse HEAD)
  if [[ "$HEAD_BEFORE" != "$HEAD_AFTER" ]]; then
    _fail "test4" "current branch HEAD changed despite conflict abort"
    rm -rf "$base"; return
  fi
  _pass "test4 (conflicting sibling: exit 2, branch unchanged)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 5: origin/main moved ahead (behind state) → rebase happens, exit 0
# ---------------------------------------------------------------------------
test_5_behind_origin_main() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Workstream branch cut at initial state
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "workstream-commit" "ws.txt"

  # Simulate origin/main moving ahead: push a new commit to origin/main
  # We do this by checking out main, adding a commit, pushing, then going back
  git checkout main >/dev/null 2>&1
  _add_commit "origin-main-advance" "origin-advance.txt"
  git push origin main >/dev/null 2>&1
  # Fetch to get the updated origin/main ref
  git fetch origin main >/dev/null 2>&1
  git checkout "work/striker/${TODAY}" >/dev/null 2>&1

  # Confirm we are behind
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
  if [[ "$BEHIND" -eq 0 ]]; then
    _fail "test5" "fixture setup error: expected to be behind origin/main"
    rm -rf "$base"; return
  fi

  _run_step3
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test5" "expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if echo "$STEP3_OUT" | grep -q "reconcile: no-op"; then
    _fail "test5" "expected a rebase/merge, but got no-op. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -qE "reconcile: rebased|reconcile: merged \(fallback\)"; then
    _fail "test5" "expected rebased or merged-fallback. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test5 (behind origin/main: rebased)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 6: --dry-run → no mutations, summary shows what would happen
# ---------------------------------------------------------------------------
test_6_dry_run() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  # Workstream branch with a sibling and an ahead commit
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "ahead-commit" "ahead.txt"

  git checkout -b "work/striker/${TODAY}-2" >/dev/null 2>&1
  _add_commit "sibling-dry" "sibling-dry.txt"
  git checkout "work/striker/${TODAY}" >/dev/null 2>&1

  # Count commits before dry-run
  COMMITS_BEFORE=$(git rev-list --count HEAD)
  BRANCHES_BEFORE=$(git branch --list | wc -l | tr -d ' ')

  _run_step3 --dry-run
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test6" "dry-run: expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi

  # No commits should have been added
  COMMITS_AFTER=$(git rev-list --count HEAD)
  if [[ "$COMMITS_BEFORE" -ne "$COMMITS_AFTER" ]]; then
    _fail "test6" "dry-run added commits: before=$COMMITS_BEFORE after=$COMMITS_AFTER"
    rm -rf "$base"; return
  fi

  # Sibling branch should still exist
  BRANCHES_AFTER=$(git branch --list | wc -l | tr -d ' ')
  if [[ "$BRANCHES_BEFORE" -ne "$BRANCHES_AFTER" ]]; then
    _fail "test6" "dry-run deleted branches: before=$BRANCHES_BEFORE after=$BRANCHES_AFTER"
    rm -rf "$base"; return
  fi

  # Should mention DRY-RUN in output
  if ! echo "$STEP3_OUT" | grep -qi "dry-run"; then
    _fail "test6" "dry-run output lacks DRY-RUN label. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test6 (--dry-run: no mutations, summary produced)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 7: --no-push → local consolidation; push explicitly skipped, exit 0
# ---------------------------------------------------------------------------
test_7_no_push() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "local-only-commit" "local.txt"

  _run_step3 --no-push
  cd "$WORK_DIR"

  if [[ "$STEP3_RC" -ne 0 ]]; then
    _fail "test7" "expected exit 0, got $STEP3_RC. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "push: skipped (--no-push)"; then
    _fail "test7" "expected 'push: skipped (--no-push)'. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  if ! echo "$STEP3_OUT" | grep -q "\[step3\] OK"; then
    _fail "test7" "expected OK. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test7 (--no-push: local consolidation, push skipped)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 8: cs_compute_machine returns expected lowercase form
# ---------------------------------------------------------------------------
test_8_machine_lowercase() {
  local base
  base=$(mktemp -d)
  _make_repo "$base"

  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1

  # Force the machine name to an uppercase variant to confirm lowercase output
  local rc8=0
  STEP3_OUT=$(COORDINATOR_MACHINE="STRIKER" "$BASH" "$STEP3" --no-push 2>&1) || rc8=$?
  cd "$WORK_DIR"

  if ! echo "$STEP3_OUT" | grep -q "machine: striker"; then
    _fail "test8" "expected lowercase 'machine: striker'. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test8 (cs_compute_machine: STRIKER → striker)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
# We need a single shared TMPDIR_ROOT for the cleanup trap
TMPDIR_ROOT=$(mktemp -d)

echo "Running workday-complete-step3-consolidate smoke tests..."
echo ""

test_1_no_siblings_ahead
test_2_no_siblings_current
test_3_sibling_non_conflicting
test_4_sibling_conflict
test_5_behind_origin_main
test_6_dry_run
test_7_no_push
test_8_machine_lowercase

echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
