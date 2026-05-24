#!/usr/bin/env bash
# test-migrate-cross-repo-layout.sh — Fixture-based tests for migrate-cross-repo-layout.sh
#
# Purpose: Verifies the AC-8 properties from the plan spec:
#   1. Fixture with flat cross-repo/*.md + archive/cross-repo/* → files land in correct
#      destinations; top-level archive/cross-repo/ is removed; README.md stays put.
#   2. Second run (re-run on migrated repo) is a no-op (exit 0, 0 moves).
#   3. Pre-existing target-collision → exit non-zero, filename in stderr.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk F
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-migrate-cross-repo-layout.sh
# (from any directory — script resolves its own location)
#
# Exit codes:
#   0  All cases PASS
#   1  One or more cases FAIL

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../migrate-cross-repo-layout.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "FATAL: migrate-cross-repo-layout.sh not found at: $SUBJECT" >&2
  exit 1
fi

chmod +x "$SUBJECT" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Minimal test framework
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
# Fixture factory
# ---------------------------------------------------------------------------

TMP_REPOS=()

cleanup() {
  for d in "${TMP_REPOS[@]}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

make_fixture_repo() {
  # Creates a minimal git repo in a tmpdir with:
  #   cross-repo/README.md
  #   cross-repo/<n-flat>.md (flat active memo files, default 1)
  #   cross-repo/<n-dotfiles> optional dotfile in archive
  #   archive/cross-repo/<m-archive>.md (flat archive files, default 2)
  #   archive/cross-repo/.dogfood-postscript.md (dotfile, default included)
  #
  # Returns the path to the tmpdir.

  local n_flat="${1:-1}"
  local m_archive="${2:-2}"

  local tmpdir
  tmpdir=$(mktemp -d)
  TMP_REPOS+=("$tmpdir")

  git -C "$tmpdir" init -q
  git -C "$tmpdir" config user.email "test@example.com"
  git -C "$tmpdir" config user.name "Test"

  # cross-repo/ flat layout
  mkdir -p "$tmpdir/cross-repo"
  echo "# README" > "$tmpdir/cross-repo/README.md"
  for (( i = 1; i <= n_flat; i++ )); do
    local fname="2026-05-2${i}-test-memo-${i}.md"
    printf -- "---\nfrom: other-em\nto: this-em\ntitle: Test memo %d\nstatus: open\n---\nBody.\n" "$i" > "$tmpdir/cross-repo/${fname}"
  done

  # archive/cross-repo/ flat layout (includes a dotfile)
  mkdir -p "$tmpdir/archive/cross-repo"
  for (( i = 1; i <= m_archive; i++ )); do
    local fname="2026-05-1${i}-archived-memo-${i}.md"
    printf -- "---\nfrom: other-em\nto: this-em\ntitle: Archived memo %d\nstatus: actioned\n---\nBody.\n" "$i" > "$tmpdir/archive/cross-repo/${fname}"
  done
  # Include a dotfile (mirrors real central state)
  echo "# dogfood postscript" > "$tmpdir/archive/cross-repo/.dogfood-postscript.md"

  # Commit all so git mv has a tree to work against
  git -C "$tmpdir" add -A
  git -C "$tmpdir" commit -q -m "fixture: initial flat cross-repo layout"

  echo "$tmpdir"
}

# ---------------------------------------------------------------------------
# Test 1: standard migration
# ---------------------------------------------------------------------------

echo "--- Test 1: standard migration (1 flat memo, 2 archive + 1 dotfile)"
REPO1=$(make_fixture_repo 1 2)
OUTPUT1=$(bash "$SUBJECT" --root "$REPO1" 2>&1)
EXIT1=$?

if assert_eq "T1-exit" "0" "$EXIT1"; then
  pass "Test 1: exits 0"
else
  fail "Test 1: expected exit 0, got $EXIT1 — output: $OUTPUT1"
fi

# Active memo moved to inbox/
FLAT_MEMO="2026-05-21-test-memo-1.md"
if [[ -f "$REPO1/cross-repo/inbox/$FLAT_MEMO" ]]; then
  pass "Test 1: flat memo landed in cross-repo/inbox/"
else
  fail "Test 1: flat memo not found in cross-repo/inbox/ — contents: $(ls "$REPO1/cross-repo/inbox/" 2>&1)"
fi

# Flat memo no longer at root of cross-repo/
if [[ ! -f "$REPO1/cross-repo/$FLAT_MEMO" ]]; then
  pass "Test 1: flat memo no longer at cross-repo/ root"
else
  fail "Test 1: flat memo still present at cross-repo/ root after migration"
fi

# README.md preserved at cross-repo/
if [[ -f "$REPO1/cross-repo/README.md" ]]; then
  pass "Test 1: README.md preserved at cross-repo/ root"
else
  fail "Test 1: README.md missing from cross-repo/ root after migration"
fi

# Archive files moved to cross-repo/archive/
for i in 1 2; do
  ARCH_MEMO="2026-05-1${i}-archived-memo-${i}.md"
  if [[ -f "$REPO1/cross-repo/archive/$ARCH_MEMO" ]]; then
    pass "Test 1: $ARCH_MEMO landed in cross-repo/archive/"
  else
    fail "Test 1: $ARCH_MEMO not found in cross-repo/archive/ — contents: $(ls "$REPO1/cross-repo/archive/" 2>&1)"
  fi
done

# Dotfile moved too
if [[ -f "$REPO1/cross-repo/archive/.dogfood-postscript.md" ]]; then
  pass "Test 1: .dogfood-postscript.md dotfile moved to cross-repo/archive/"
else
  fail "Test 1: .dogfood-postscript.md not found in cross-repo/archive/"
fi

# archive/cross-repo/ top-level removed
if [[ ! -d "$REPO1/archive/cross-repo" ]]; then
  pass "Test 1: top-level archive/cross-repo/ removed"
else
  fail "Test 1: top-level archive/cross-repo/ still exists"
fi

# Summary output sanity
if assert_contains "T1-inbox-count" "inbox moves:   1" "$OUTPUT1"; then
  pass "Test 1: summary reports inbox moves: 1"
else
  fail "Test 1: summary inbox count wrong — output: $OUTPUT1"
fi
if assert_contains "T1-archive-count" "archive moves: 3" "$OUTPUT1"; then
  pass "Test 1: summary reports archive moves: 3 (2 named + 1 dotfile)"
else
  fail "Test 1: summary archive count wrong — output: $OUTPUT1"
fi

# Files are staged (git mv stages the move)
STAGED1=$(git -C "$REPO1" diff --cached --name-only | wc -l | tr -d ' ')
if [[ "$STAGED1" -gt 0 ]]; then
  pass "Test 1: moves are staged (git mv staged changes present)"
else
  fail "Test 1: no staged changes after migration — git diff --cached was empty"
fi

# ---------------------------------------------------------------------------
# Test 2: idempotency — second run after commit is a no-op
# ---------------------------------------------------------------------------

echo "--- Test 2: idempotent re-run (second run = no-op)"

# Commit the migration from Test 1 so repo is in post-migration state.
git -C "$REPO1" commit -q -m "migrate: cross-repo layout"

OUTPUT2=$(bash "$SUBJECT" --root "$REPO1" 2>&1)
EXIT2=$?

if assert_eq "T2-exit" "0" "$EXIT2"; then
  pass "Test 2: re-run exits 0"
else
  fail "Test 2: expected exit 0, got $EXIT2 — output: $OUTPUT2"
fi

if assert_contains "T2-noop" "no-op" "$OUTPUT2"; then
  pass "Test 2: re-run reports no-op"
else
  fail "Test 2: re-run did not report no-op — output: $OUTPUT2"
fi

# No new staged changes after re-run.
STAGED2=$(git -C "$REPO1" diff --cached --name-only | wc -l | tr -d ' ')
if assert_eq "T2-no-staged" "0" "$STAGED2"; then
  pass "Test 2: no staged changes after re-run"
else
  fail "Test 2: unexpected staged changes after re-run — count: $STAGED2"
fi

# inbox-count in summary should be 0
if assert_contains "T2-inbox-zero" "inbox moves:   0" "$OUTPUT2"; then
  pass "Test 2: summary reports inbox moves: 0"
else
  fail "Test 2: summary inbox count not 0 — output: $OUTPUT2"
fi

# ---------------------------------------------------------------------------
# Test 3a: mixed tracked + untracked files in archive/cross-repo/
# (regression for the live central scenario where some files were untracked)
# ---------------------------------------------------------------------------

echo "--- Test 3a: mixed tracked + untracked archive files"
REPO3A=$(make_fixture_repo 0 1)  # 0 flat memos, 1 tracked archive file
# Add an untracked file to archive/cross-repo/ (not committed)
printf -- "---\nfrom: other-em\nto: this-em\ntitle: Untracked memo\nstatus: actioned\n---\nBody.\n" > "$REPO3A/archive/cross-repo/2026-05-23-untracked-memo.md"
# NOTE: deliberately NOT staged/committed — simulates live central scenario

OUTPUT3A=$(bash "$SUBJECT" --root "$REPO3A" 2>&1)
EXIT3A=$?

if assert_eq "T3a-exit" "0" "$EXIT3A"; then
  pass "Test 3a: exits 0 with mixed tracked/untracked files"
else
  fail "Test 3a: expected exit 0, got $EXIT3A — output: $OUTPUT3A"
fi

# Both tracked and untracked files land in cross-repo/archive/
if [[ -f "$REPO3A/cross-repo/archive/2026-05-11-archived-memo-1.md" ]]; then
  pass "Test 3a: tracked archive file moved to cross-repo/archive/"
else
  fail "Test 3a: tracked archive file not in cross-repo/archive/"
fi

if [[ -f "$REPO3A/cross-repo/archive/2026-05-23-untracked-memo.md" ]]; then
  pass "Test 3a: untracked archive file moved to cross-repo/archive/"
else
  fail "Test 3a: untracked archive file not in cross-repo/archive/"
fi

# archive/cross-repo/ is gone
if [[ ! -d "$REPO3A/archive/cross-repo" ]]; then
  pass "Test 3a: archive/cross-repo/ removed after mixed migration"
else
  fail "Test 3a: archive/cross-repo/ still present after mixed migration"
fi

# Moves are staged
STAGED3A=$(git -C "$REPO3A" diff --cached --name-only | wc -l | tr -d ' ')
if [[ "$STAGED3A" -gt 0 ]]; then
  pass "Test 3a: staged changes present after mixed migration"
else
  fail "Test 3a: no staged changes after mixed migration"
fi

# ---------------------------------------------------------------------------
# Test 3: target-collision → fail loud, non-zero exit, filename in stderr
# ---------------------------------------------------------------------------

echo "--- Test 3: target-collision → fail loud"

REPO3=$(make_fixture_repo 1 0)  # 1 flat memo, 0 archive files

# Manually pre-create the collision target in inbox/ (before committing)
mkdir -p "$REPO3/cross-repo/inbox"
echo "pre-existing" > "$REPO3/cross-repo/inbox/2026-05-21-test-memo-1.md"
git -C "$REPO3" add "cross-repo/inbox/2026-05-21-test-memo-1.md"
git -C "$REPO3" commit -q -m "fixture: pre-existing collision target"

# Now run the migration — it should fail loud
OUTPUT3=$(bash "$SUBJECT" --root "$REPO3" 2>&1) && EXIT3=0 || EXIT3=$?

if [[ "$EXIT3" -ne 0 ]]; then
  pass "Test 3: exits non-zero on collision"
else
  fail "Test 3: expected non-zero exit on collision, got 0"
fi

if assert_contains "T3-collision-msg" "collision" "$OUTPUT3" || \
   assert_contains "T3-already-exists" "already exists" "$OUTPUT3"; then
  pass "Test 3: error message mentions collision/already exists"
else
  fail "Test 3: error message missing — output: $OUTPUT3"
fi

if assert_contains "T3-filename" "2026-05-21-test-memo-1.md" "$OUTPUT3"; then
  pass "Test 3: conflicting filename named in error output"
else
  fail "Test 3: conflicting filename not in error output — output: $OUTPUT3"
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
