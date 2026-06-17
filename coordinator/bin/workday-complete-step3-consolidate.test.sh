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
  # Review: code-reviewer (F4) — set -e inside _make_repo so git failures produce
  # a clear FATAL diagnostic rather than misleading downstream test output.
  local base="$1"
  ORIGIN_DIR="${base}/origin.git"
  WORK_DIR="${base}/work"
  TODAY=$(date -u +%Y-%m-%d)
  MACHINE="striker"
  # SIBLING_BRANCH — a valid span-form sibling that covers today.
  # Computed as work/striker/<YYYY-MM-(DD-1)>to<DD> (starts yesterday, ends today).
  # cs_parse_branch_span validates this as a span branch covering TODAY.
  local today_dd today_yy today_mm yesterday_dd yesterday_yy yesterday_mm sibling_start
  today_dd="${TODAY##*-}"
  today_yy="${TODAY%%-*}"
  today_mm="${TODAY#*-}"; today_mm="${today_mm%%-*}"
  if (( 10#$today_dd > 1 )); then
    yesterday_dd=$(printf '%02d' $(( 10#$today_dd - 1 )))
    yesterday_mm="$today_mm"
    yesterday_yy="$today_yy"
  else
    # First of the month — use last day of prior month (simplified: use 28 as safe value)
    yesterday_dd="28"
    if (( 10#$today_mm > 1 )); then
      yesterday_mm=$(printf '%02d' $(( 10#$today_mm - 1 )))
      yesterday_yy="$today_yy"
    else
      yesterday_mm="12"
      yesterday_yy=$(( 10#$today_yy - 1 ))
    fi
  fi
  sibling_start="${yesterday_yy}-${yesterday_mm}-${yesterday_dd}"
  SIBLING_BRANCH="work/striker/${sibling_start}to${today_dd}"

  (
    set -e
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
  ) || { echo "FATAL: _make_repo failed at $base" >&2; exit 1; }

  # cd into WORK_DIR so callers start in the right place
  cd "$WORK_DIR"
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
# Review: code-reviewer (F3) — uses STEP3_SYNC_MAIN env-var override instead of
# mutating the live sync-main.sh on disk (which would corrupt it on runner kill).
#
# Returns the exit code in STEP3_RC and combined stdout+stderr in STEP3_OUT.
_run_step3() {
  # Create a per-call stub sync-main.sh in a temp dir; pass via STEP3_SYNC_MAIN
  local stub_bin
  stub_bin="$(mktemp -d)"
  local stub_path="${stub_bin}/sync-main.sh"
  cat > "$stub_path" <<'STUB'
#!/usr/bin/env bash
# stub: no-op sync-main for tests
exit 0
STUB
  chmod +x "$stub_path"

  STEP3_RC=0
  # Review: code-reviewer (F8) — || STEP3_RC=$? pattern preserves the real exit code;
  # || true here would absorb failure RC — regression for the || true bug
  # TEST_COORDINATOR_MACHINE allows callers to override the machine name (e.g. test 8).
  STEP3_OUT=$(COORDINATOR_MACHINE="${TEST_COORDINATOR_MACHINE:-striker}" STEP3_SYNC_MAIN="$stub_path" "$BASH" "$STEP3" "$@" 2>&1) || STEP3_RC=$?

  rm -rf "$stub_bin"
}

# ---------------------------------------------------------------------------
# Test 1: No siblings, branch ahead of origin/main → ahead-only reconcile, push, exit 0
# ---------------------------------------------------------------------------
test_1_no_siblings_ahead() {
  local base
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
  _make_repo "$base"

  # Main workstream branch
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "main-branch-commit" "file-main.txt"

  # Sibling branch with non-conflicting commit (different file).
  # Use SIBLING_BRANCH (span-form, covers today) — valid cs_parse_branch_span input.
  git checkout -b "$SIBLING_BRANCH" >/dev/null 2>&1
  _add_commit "sibling-commit" "file-sibling.txt"
  git push -u origin "$SIBLING_BRANCH" >/dev/null 2>&1

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
  if git -C "$WORK_DIR" branch --list "$SIBLING_BRANCH" | grep -q "$SIBLING_BRANCH"; then
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
  _make_repo "$base"

  # Main workstream branch with a commit on conflict.txt
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  echo "main version" > conflict.txt
  git add conflict.txt
  git commit -m "main: conflict.txt version A" >/dev/null 2>&1

  # Sibling: branch from the initial commit, write conflicting content.
  # Use SIBLING_BRANCH (span-form, covers today) — valid cs_parse_branch_span input.
  git checkout main >/dev/null 2>&1
  git checkout -b "$SIBLING_BRANCH" >/dev/null 2>&1
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
  _make_repo "$base"

  # Workstream branch with a sibling and an ahead commit
  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1
  _add_commit "ahead-commit" "ahead.txt"

  # Use SIBLING_BRANCH (span-form, covers today) — valid cs_parse_branch_span input.
  git checkout -b "$SIBLING_BRANCH" >/dev/null 2>&1
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
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
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  base=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
  _make_repo "$base"

  git checkout -b "work/striker/${TODAY}" >/dev/null 2>&1
  git push -u origin "work/striker/${TODAY}" >/dev/null 2>&1

  # Force the machine name to an uppercase variant to confirm lowercase output
  # Review: code-reviewer (F5) — use _run_step3 wrapper so STEP3_SYNC_MAIN stub applies;
  # direct invocation bypasses the wrapper and may hit real sync-main.sh.
  TEST_COORDINATOR_MACHINE="STRIKER" _run_step3 --no-push
  cd "$WORK_DIR"

  if ! echo "$STEP3_OUT" | grep -q "machine: striker"; then
    _fail "test8" "expected lowercase 'machine: striker'. Output: $STEP3_OUT"
    rm -rf "$base"; return
  fi
  _pass "test8 (cs_compute_machine: STRIKER → striker)"
  rm -rf "$base"
}

# ---------------------------------------------------------------------------
# Test 9: PLUGIN_ROOT without lib → exit 5
# ---------------------------------------------------------------------------
# Review: code-reviewer (F12) — no test previously covered exit code 5 (lib missing).
test_9_lib_missing() {
  local fake_root
  # Review: code-reviewer (F6) — route under TMPDIR_ROOT so cleanup trap handles on early failure.
  # Use template form (portable BSD+GNU; -p flag is GNU-only).
  fake_root=$(mktemp -d "${TMPDIR_ROOT}/test.XXXXXX")
  # Create a minimal bin dir so --help path discovery works, but no lib/
  mkdir -p "${fake_root}/bin"

  # Override PLUGIN_ROOT by invoking via a symlink in fake_root/bin so the script's
  # own PLUGIN_ROOT resolution (dirname BASH_SOURCE[0]/..) lands on fake_root.
  # Simpler: pass PLUGIN_ROOT via the script's own discovery — it uses dirname of its own path.
  # We create a stub script that sources the real step3 with PLUGIN_ROOT overridden via env.
  # Actually the script resolves PLUGIN_ROOT from BASH_SOURCE[0] — we can't override it via env.
  # Easiest: symlink the script into fake_root/bin/ so PLUGIN_ROOT resolves to fake_root.
  ln -s "$STEP3" "${fake_root}/bin/workday-complete-step3-consolidate.sh"

  local rc9=0
  local out9
  out9=$("$BASH" "${fake_root}/bin/workday-complete-step3-consolidate.sh" --no-push 2>&1) || rc9=$?

  rm -rf "$fake_root"

  if [[ "$rc9" -ne 5 ]]; then
    _fail "test9" "expected exit 5 (lib missing), got $rc9. Output: $out9"
    return
  fi
  if ! echo "$out9" | grep -q "lib not found"; then
    _fail "test9" "expected 'lib not found' diagnostic. Output: $out9"
    return
  fi
  _pass "test9 (PLUGIN_ROOT without lib: exit 5)"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
# Review: code-reviewer (F6) — TMPDIR_ROOT is the single root for all per-test dirs;
# cleanup trap at top of file handles it on exit (including early failure).
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
test_9_lib_missing

echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
