#!/usr/bin/env bash
# test-migrate-completion-log-legacy.sh — Smoke tests for migrate-completion-log-legacy.sh
#
# Purpose: verifies the three key AC properties from the plan spec:
#   1. A repo with 3 monthly monoliths produces 3 git mv ops (files land in legacy/).
#   2. Running again on an already-migrated repo is a no-op (exit 0, 0 moves).
#   3. A repo with no archive/completed/ dir fails with exit 1 + remediation message.
#
# All tests use a tmpdir git repo fixture — no writes to the real repo.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 7
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-migrate-completion-log-legacy.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../migrate-completion-log-legacy.sh"

# ---------------------------------------------------------------------------
# Minimal test framework (same conventions as test-coordinator-write-review-trail.sh)
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

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    return 0
  else
    echo "    Expected: $(printf '%q' "$expected")" >&2
    echo "    Actual:   $(printf '%q' "$actual")" >&2
    return 1
  fi
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
# Fixture: minimal git repo with archive/completed/ and N monolith files
# ---------------------------------------------------------------------------

TMP_REPOS=()

make_fixture_repo() {
  local tmpdir
  tmpdir=$(mktemp -d)
  TMP_REPOS+=("$tmpdir")

  git -C "$tmpdir" init -q
  git -C "$tmpdir" config user.email "test@example.com"
  git -C "$tmpdir" config user.name "Test"

  mkdir -p "$tmpdir/archive/completed"

  # Seed with N monthly monolith files.
  local n="${1:-3}"
  local base_year=2026
  for (( i = 0; i < n; i++ )); do
    local month
    month=$(printf "%02d" $(( i + 1 )))
    local fname="${base_year}-${month}.md"
    echo "# Legacy monolith ${fname}" > "$tmpdir/archive/completed/${fname}"
    git -C "$tmpdir" add "archive/completed/${fname}"
  done

  # Initial commit so git mv has something to work with.
  git -C "$tmpdir" commit -q -m "fixture: initial monolith files"

  echo "$tmpdir"
}

cleanup() {
  for d in "${TMP_REPOS[@]}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Test 1: 3 monoliths → 3 moves; files appear under legacy/
# ---------------------------------------------------------------------------

echo "--- Test 1: 3 monoliths produce 3 git mv ops"
REPO1=$(make_fixture_repo 3)
OUTPUT1=$(bash "$SUBJECT" --root "$REPO1" 2>&1) || {
  fail "Test 1: script exited non-zero"
  echo "    Output: $OUTPUT1" >&2
}

# Check output summary line
if assert_contains "T1-summary-moved" "Moved:  3" "$OUTPUT1"; then
  pass "Test 1: summary reports Moved: 3"
else
  fail "Test 1: summary does not report Moved: 3 — output: $OUTPUT1"
fi

# Check files are staged under legacy/
MOVED_COUNT=$(git -C "$REPO1" diff --cached --name-only | grep -c "archive/completed/legacy/" || true)
if assert_eq "T1-staged-count" "3" "$MOVED_COUNT"; then
  pass "Test 1: 3 files staged under archive/completed/legacy/"
else
  fail "Test 1: expected 3 staged files under legacy/, got $MOVED_COUNT"
fi

# Verify original locations are gone
for m in 01 02 03; do
  if [[ ! -f "$REPO1/archive/completed/2026-${m}.md" ]]; then
    pass "Test 1: 2026-${m}.md no longer at root of completed/"
  else
    fail "Test 1: 2026-${m}.md still present at root of completed/ after migration"
  fi
done

# Verify files exist at new location
for m in 01 02 03; do
  if [[ -f "$REPO1/archive/completed/legacy/2026-${m}.md" ]]; then
    pass "Test 1: 2026-${m}.md present under legacy/"
  else
    fail "Test 1: 2026-${m}.md missing from legacy/ after migration"
  fi
done

# ---------------------------------------------------------------------------
# Test 2: running again on an already-migrated repo is a no-op
# ---------------------------------------------------------------------------

echo "--- Test 2: re-run is a no-op (idempotency)"

# Commit the migration from Test 1 so the repo is in the post-migration state.
git -C "$REPO1" commit -q -m "migrate: move monoliths to legacy/"

OUTPUT2=$(bash "$SUBJECT" --root "$REPO1" 2>&1)
EXIT2=$?

if assert_eq "T2-exit" "0" "$EXIT2"; then
  pass "Test 2: re-run exits 0"
else
  fail "Test 2: re-run exited $EXIT2 (expected 0)"
fi

if assert_contains "T2-noop-msg" "Nothing to migrate" "$OUTPUT2" || \
   assert_contains "T2-noop-alt" "no-op" "$OUTPUT2"; then
  pass "Test 2: re-run reports no-op"
else
  # Either message shape is acceptable — just check Moved:  0 isn't present
  if echo "$OUTPUT2" | grep -q "Moved:  0"; then
    pass "Test 2: re-run shows Moved: 0 (no files moved)"
  else
    fail "Test 2: re-run output unclear — got: $OUTPUT2"
  fi
fi

# No new staged changes.
STAGED2=$(git -C "$REPO1" diff --cached --name-only | wc -l | tr -d ' ')
if assert_eq "T2-no-staged" "0" "$STAGED2"; then
  pass "Test 2: no new staged files after re-run"
else
  fail "Test 2: unexpected staged files after re-run — count: $STAGED2"
fi

# ---------------------------------------------------------------------------
# Test 3: repo without archive/completed/ exits 1 with remediation message
# ---------------------------------------------------------------------------

echo "--- Test 3: missing archive/completed/ → exit 1 with remediation"
REPO3=$(mktemp -d)
TMP_REPOS+=("$REPO3")
git -C "$REPO3" init -q
git -C "$REPO3" config user.email "test@example.com"
git -C "$REPO3" config user.name "Test"

OUTPUT3=$(bash "$SUBJECT" --root "$REPO3" 2>&1) && EXIT3=0 || EXIT3=$?

if assert_eq "T3-exit" "1" "$EXIT3"; then
  pass "Test 3: exits 1 for missing archive/completed/"
else
  fail "Test 3: expected exit 1, got $EXIT3"
fi

if assert_contains "T3-remediation" "Remediation:" "$OUTPUT3"; then
  pass "Test 3: output includes remediation message"
else
  fail "Test 3: remediation message missing — output: $OUTPUT3"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=============================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "=============================="

if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failures:"
  for m in "${FAIL_MSGS[@]}"; do
    echo "  - $m"
  done
  exit 1
fi

exit 0
