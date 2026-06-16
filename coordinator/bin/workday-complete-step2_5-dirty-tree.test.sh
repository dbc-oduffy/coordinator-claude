#!/usr/bin/env bash
# workday-complete-step2_5-dirty-tree.test.sh — smoke tests for the step-2.5 script.
#
# Spec backlink: commands/workday-complete.md § Step 2.5
# PM ruling:     cross-repo/inbox/2026-06-16-workday-complete-dirty-tree-autonomy.md
#
# Usage: bash <this-file>
# Exit: 0 if all tests pass, non-zero on any failure.

set -eu

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash ≥ 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/workday-complete-step2_5-dirty-tree.sh"

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

# _make_repo DIR — init a bare git repo with an initial commit in DIR
_make_repo() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" config user.email "test@test.local"
  git -C "$dir" config user.name "Test"
  # Initial commit so HEAD exists
  touch "$dir/.gitkeep"
  git -C "$dir" add -- .gitkeep
  git -C "$dir" commit -q -m "init"
}

# _run_script REPO_DIR [args...] → stdout in STDOUT_OUT, exit code in RC
STDOUT_OUT=""
STDERR_OUT=""
RC=0
_run_script() {
  local repo="$1"; shift
  STDOUT_OUT=""
  STDERR_OUT=""
  RC=0
  # Run with cwd=repo so git rev-parse --show-toplevel works
  STDOUT_OUT=$(cd "$repo" && bash "$SUBJECT" "$@" 2>/tmp/step2_5_test_stderr) || RC=$?
  STDERR_OUT=$(cat /tmp/step2_5_test_stderr 2>/dev/null || true)
}

# ---------------------------------------------------------------------------
# Temp-dir management
# ---------------------------------------------------------------------------
TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

# ---------------------------------------------------------------------------
# Test 1: Empty repo, no dirty paths → all-zero summary, exit 0
# ---------------------------------------------------------------------------
T1="$TMPBASE/t1"
_make_repo "$T1"
_run_script "$T1"
if [[ "$RC" -eq 0 ]]; then
  # Stdout should just be the OK line (all counts zero → no group lines)
  if echo "$STDOUT_OUT" | grep -q "\[step2.5\] OK"; then
    _pass "T1: empty repo → exit 0 + OK"
  else
    _fail "T1: empty repo" "expected [step2.5] OK in stdout; got: $STDOUT_OUT"
  fi
else
  _fail "T1: empty repo" "expected exit 0, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# Test 2: EOL-phantom only → skipped, exit 0
# Create a tracked file, stage it, then modify it with only an EOL change
# so that git diff --quiet exits 0 (content-equal to index).
# We simulate this by staging the file and NOT modifying it afterwards
# (git porcelain will show it as modified if index differs from HEAD, but
# git diff --quiet compares worktree to index; if we stage and then the
# worktree matches the index, diff --quiet exits 0).
# ---------------------------------------------------------------------------
T2="$TMPBASE/t2"
_make_repo "$T2"
# Write a file with LF, add to index (stage)
printf 'hello\n' > "$T2/eol-test.txt"
git -C "$T2" add -- eol-test.txt
# Commit so HEAD has it
git -C "$T2" commit -q -m "add eol-test"
# Now make HEAD differ from index by amending the committed content but leave
# worktree matching index: we do this by: modify+stage → now index != HEAD,
# worktree == index → git diff --quiet (WT vs index) exits 0
printf 'hello world\n' > "$T2/eol-test.txt"
git -C "$T2" add -- eol-test.txt
# Now porcelain shows "M " (staged) — worktree == index → git diff --quiet exits 0
_run_script "$T2"
if [[ "$RC" -eq 0 ]]; then
  if echo "$STDOUT_OUT" | grep -q "EOL-phantom skipped: 1"; then
    _pass "T2: EOL-phantom skipped"
  else
    _fail "T2: EOL-phantom" "expected 'EOL-phantom skipped: 1'; got: $STDOUT_OUT"
  fi
else
  _fail "T2: EOL-phantom" "expected exit 0, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# Test 3: AUTO-COMMIT — file under state/review-trail/ gets committed
# ---------------------------------------------------------------------------
T3="$TMPBASE/t3"
_make_repo "$T3"
mkdir -p "$T3/state/review-trail"
printf '{"status":"done"}\n' > "$T3/state/review-trail/review-2026-06-16.json"
rev_before=$(git -C "$T3" rev-list --count HEAD)
_run_script "$T3"
if [[ "$RC" -eq 0 ]]; then
  rev_after=$(git -C "$T3" rev-list --count HEAD)
  if [[ "$rev_after" -gt "$rev_before" ]]; then
    # Verify the file is in the commit
    committed=$(git -C "$T3" show --stat HEAD | grep "review-2026-06-16.json" || true)
    if [[ -n "$committed" ]]; then
      _pass "T3: AUTO-COMMIT landed review-trail file"
    else
      _fail "T3: AUTO-COMMIT" "commit landed but file not in HEAD: $(git -C "$T3" show --stat HEAD)"
    fi
  else
    _fail "T3: AUTO-COMMIT" "expected new commit; rev_before=$rev_before rev_after=$rev_after. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
else
  _fail "T3: AUTO-COMMIT" "expected exit 0, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# Test 3b: second run no-ops
rev_before2=$(git -C "$T3" rev-list --count HEAD)
_run_script "$T3"
rev_after2=$(git -C "$T3" rev-list --count HEAD)
if [[ "$rev_after2" -eq "$rev_before2" ]]; then
  _pass "T3b: second run is a no-op"
else
  _fail "T3b: idempotency" "second run produced extra commit(s): rev_before=$rev_before2 rev_after=$rev_after2"
fi

# ---------------------------------------------------------------------------
# Test 4: AUTO-GITIGNORE — touch logs/foo.log; .gitignore gets entry; commit lands
# ---------------------------------------------------------------------------
T4="$TMPBASE/t4"
_make_repo "$T4"
mkdir -p "$T4/logs"
printf 'some log\n' > "$T4/logs/foo.log"
rev_before=$(git -C "$T4" rev-list --count HEAD)
_run_script "$T4"
if [[ "$RC" -eq 0 ]]; then
  # .gitignore should contain logs/ or *.log
  gi_content=$(cat "$T4/.gitignore" 2>/dev/null || true)
  if echo "$gi_content" | grep -qE "^(logs/|\*\.log)$"; then
    # A commit should have landed
    rev_after=$(git -C "$T4" rev-list --count HEAD)
    if [[ "$rev_after" -gt "$rev_before" ]]; then
      _pass "T4: AUTO-GITIGNORE added entry and committed"
    else
      _fail "T4: AUTO-GITIGNORE" "no commit landed; rev_before=$rev_before rev_after=$rev_after"
    fi
  else
    _fail "T4: AUTO-GITIGNORE" "expected logs/ or *.log in .gitignore; got: $gi_content"
  fi
else
  _fail "T4: AUTO-GITIGNORE" "expected exit 0, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# Test 4b: second run no-ops
rev_before2=$(git -C "$T4" rev-list --count HEAD)
_run_script "$T4"
rev_after2=$(git -C "$T4" rev-list --count HEAD)
if [[ "$rev_after2" -eq "$rev_before2" ]]; then
  _pass "T4b: gitignore second run is a no-op"
else
  _fail "T4b: gitignore idempotency" "second run produced extra commits: rev_before=$rev_before2 rev_after=$rev_after2"
fi

# ---------------------------------------------------------------------------
# Test 5: SOURCE-TREE — modify a bin/ file; exit 2; stderr lists the path
# ---------------------------------------------------------------------------
T5="$TMPBASE/t5"
_make_repo "$T5"
mkdir -p "$T5/bin"
printf '#!/usr/bin/env bash\necho hello\n' > "$T5/bin/foo.sh"
git -C "$T5" add -- bin/foo.sh
git -C "$T5" commit -q -m "add foo.sh"
# Now modify it (tracked file, worktree != index != HEAD)
printf '#!/usr/bin/env bash\necho goodbye\n' > "$T5/bin/foo.sh"
_run_script "$T5"
if [[ "$RC" -eq 2 ]]; then
  if echo "$STDERR_OUT" | grep -q "\[step2.5\] source-tree: bin/foo.sh"; then
    if echo "$STDOUT_OUT" | grep -q "\[step2.5\] NEEDS-PM"; then
      _pass "T5: SOURCE-TREE → exit 2 + NEEDS-PM + stderr listing"
    else
      _fail "T5: SOURCE-TREE" "expected NEEDS-PM in stdout; got: $STDOUT_OUT"
    fi
  else
    _fail "T5: SOURCE-TREE" "expected source-tree listing in stderr; got: $STDERR_OUT"
  fi
else
  _fail "T5: SOURCE-TREE" "expected exit 2, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# Test 6: Idempotency — AUTO-COMMIT scenario run twice; second run no new commit
# ---------------------------------------------------------------------------
T6="$TMPBASE/t6"
_make_repo "$T6"
mkdir -p "$T6/state/review-trail"
printf '{"x":1}\n' > "$T6/state/review-trail/r.json"
rev_before=$(git -C "$T6" rev-list --count HEAD)

_run_script "$T6"
rev_mid=$(git -C "$T6" rev-list --count HEAD)

_run_script "$T6"
rev_after=$(git -C "$T6" rev-list --count HEAD)

if [[ "$rev_mid" -gt "$rev_before" ]] && [[ "$rev_after" -eq "$rev_mid" ]]; then
  _pass "T6: idempotency — first run commits, second run no-ops"
else
  _fail "T6: idempotency" "rev_before=$rev_before rev_mid=$rev_mid rev_after=$rev_after"
fi

# ---------------------------------------------------------------------------
# Test 7: --dry-run under AUTO-COMMIT setup; no commit lands
# ---------------------------------------------------------------------------
T7="$TMPBASE/t7"
_make_repo "$T7"
mkdir -p "$T7/state/review-trail"
printf '{"x":1}\n' > "$T7/state/review-trail/dryrun.json"
rev_before=$(git -C "$T7" rev-list --count HEAD)

_run_script "$T7" --dry-run

rev_after=$(git -C "$T7" rev-list --count HEAD)
if [[ "$rev_after" -eq "$rev_before" ]]; then
  # Stdout should still show auto-commit summary
  if echo "$STDOUT_OUT" | grep -q "auto-commit"; then
    _pass "T7: --dry-run prints summary but no commit"
  else
    _fail "T7: --dry-run" "expected auto-commit summary in stdout; got: $STDOUT_OUT"
  fi
else
  _fail "T7: --dry-run" "commit landed despite --dry-run; rev_before=$rev_before rev_after=$rev_after"
fi

# ---------------------------------------------------------------------------
# Test 8: ORPHAN-TMP — basename matches *.tmp.DIGITS.DIGITS; listed on stderr; not deleted; exit 0
# ---------------------------------------------------------------------------
T8="$TMPBASE/t8"
_make_repo "$T8"
printf 'crash artifact\n' > "$T8/foo.tmp.12345.67890"
_run_script "$T8"
if [[ "$RC" -eq 0 ]]; then
  if echo "$STDERR_OUT" | grep -q "\[step2.5\] orphan-tmp: foo.tmp.12345.67890"; then
    if [[ -f "$T8/foo.tmp.12345.67890" ]]; then
      if echo "$STDOUT_OUT" | grep -q "orphan-tmp listed (no action): 1"; then
        _pass "T8: ORPHAN-TMP listed on stderr, not deleted, exit 0"
      else
        _fail "T8: ORPHAN-TMP" "expected summary line; stdout=$STDOUT_OUT"
      fi
    else
      _fail "T8: ORPHAN-TMP" "file was deleted (must not be auto-deleted)"
    fi
  else
    _fail "T8: ORPHAN-TMP" "expected orphan-tmp in stderr; got: $STDERR_OUT"
  fi
else
  _fail "T8: ORPHAN-TMP" "expected exit 0, got $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL (${TOTAL} total)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
