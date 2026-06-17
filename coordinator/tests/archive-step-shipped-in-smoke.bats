#!/usr/bin/env bats
# archive-step-shipped-in-smoke.bats - integration smoke test for the stamp_shipped_in lib function.
#
# Purpose: drives a synthetic handoff through the stamp -> archive flow end-to-end, covering
# the ceremony path (--allow-branch-tip-fallback ON), scope-empty fallback, the orphan-sweep
# no-stamp correctness contract (Patrik F1), scope-path commit resolution without the flag,
# and idempotency.
#
# Spec backlink: docs/plans/2026-06-15-shipped-in-archive-stamping.md § C4
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/archive-step-shipped-in-smoke.bats
#      from the ~/.claude repo root.
#
# Negative-spec: stamp_shipped_in WITHOUT --allow-branch-tip-fallback must NOT stamp when
# scope yields no SHA (Patrik F1 orphan-sweep correctness contract).

LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../lib" && pwd)"
LIB="$LIB_DIR/coordinator-archive-stamp.sh"

# ---------------------------------------------------------------------------
# Setup / teardown - synthetic git repo so git log resolves correctly
# ---------------------------------------------------------------------------

setup() {
  TMPDIR_TEST="$(mktemp -d)"

  # Initialise a git repo in the scratch dir.
  git -C "$TMPDIR_TEST" init -q
  git -C "$TMPDIR_TEST" config user.email "test@example.com"
  git -C "$TMPDIR_TEST" config user.name "Test"

  # Create a scope target file and commit it so git log returns a real SHA.
  mkdir -p "$TMPDIR_TEST/state/handoffs"
  echo "scope target content" > "$TMPDIR_TEST/state/scope-target.txt"
  git -C "$TMPDIR_TEST" add "$TMPDIR_TEST/state/scope-target.txt"
  git -C "$TMPDIR_TEST" commit -q -m "add scope target"

  # Record the SHA of that commit for assertions.
  SCOPE_COMMIT_SHA="$(git -C "$TMPDIR_TEST" log --format=%H -n1)"
}

teardown() {
  rm -rf "$TMPDIR_TEST"
}

# ---------------------------------------------------------------------------
# Helper: write a handoff with frontmatter and optional scope: block
# ---------------------------------------------------------------------------

write_handoff() {
  # write_handoff <path> [with_scope|no_scope|empty_scope]
  # with_scope   - scope: block pointing at state/scope-target.txt
  # no_scope     - no scope: key at all
  # empty_scope  - scope: key with empty list (default)
  local path="$1"
  local scope_style="${2:-empty_scope}"
  mkdir -p "$(dirname "$path")"
  {
    printf -- '---\n'
    printf 'status: consumed\n'
    printf 'consumed_at: 2026-06-14\n'
    if [ "$scope_style" = "with_scope" ]; then
      printf 'scope:\n'
      printf '  - state/scope-target.txt\n'
    elif [ "$scope_style" = "empty_scope" ]; then
      printf 'scope: []\n'
    fi
    # no_scope: omit the key entirely
    printf -- '---\n'
    printf '\n# Body content\n'
  } > "$path"
}

# ---------------------------------------------------------------------------
# Test 1: ceremony path - stamp resolves SHA from scope: paths
# --allow-branch-tip-fallback ON, scope: has a matching file commit
# ---------------------------------------------------------------------------

@test "ceremony-path: stamp inserts shipped_in SHA resolved from scope paths" {
  local handoff="$TMPDIR_TEST/state/handoffs/ceremony-scope.md"
  write_handoff "$handoff" "with_scope"

  # Source the lib and call the function from inside the tmp repo so
  # git rev-parse --show-toplevel resolves to TMPDIR_TEST.
  (
    cd "$TMPDIR_TEST"
    # shellcheck source=/dev/null
    source "$LIB"
    stamp_shipped_in "$handoff" --allow-branch-tip-fallback
  )

  # shipped_in must be present
  grep -q 'shipped_in:' "$handoff"

  # The value must be the 8-char prefix of the scope-path commit
  local expected_prefix="${SCOPE_COMMIT_SHA:0:8}"
  grep -q "shipped_in: $expected_prefix" "$handoff"
}

# ---------------------------------------------------------------------------
# Test 2: ceremony path - scope-empty fallback to branch tip
# scope: is empty, --allow-branch-tip-fallback ON -> falls back to branch tip
# ---------------------------------------------------------------------------

@test "ceremony-path scope-empty: shipped_in falls back to branch tip SHA when scope yields no commit" {
  local handoff="$TMPDIR_TEST/state/handoffs/ceremony-empty-scope.md"
  write_handoff "$handoff" "empty_scope"

  # Add a new commit after setup so branch tip differs from SCOPE_COMMIT_SHA.
  echo "second commit marker" > "$TMPDIR_TEST/extra.txt"
  git -C "$TMPDIR_TEST" add "$TMPDIR_TEST/extra.txt"
  git -C "$TMPDIR_TEST" commit -q -m "second commit"
  local branch_tip
  branch_tip="$(git -C "$TMPDIR_TEST" log --format=%H -n1)"

  (
    cd "$TMPDIR_TEST"
    # shellcheck source=/dev/null
    source "$LIB"
    stamp_shipped_in "$handoff" --allow-branch-tip-fallback
  )

  # shipped_in must be present
  grep -q 'shipped_in:' "$handoff"

  # Value must be the branch tip (not the scope-path commit, since scope was empty)
  local expected_prefix="${branch_tip:0:8}"
  grep -q "shipped_in: $expected_prefix" "$handoff"
}

# ---------------------------------------------------------------------------
# Test 3: orphan-sweep path - no stamp when scope is empty and flag is absent
# Patrik F1 correctness contract: fallback flag off, no scope commit => no stamp
# ---------------------------------------------------------------------------

@test "orphan-sweep no-stamp: shipped_in is NOT written when scope empty and flag absent" {
  local handoff="$TMPDIR_TEST/state/handoffs/orphan-no-stamp.md"
  write_handoff "$handoff" "empty_scope"

  (
    cd "$TMPDIR_TEST"
    # shellcheck source=/dev/null
    source "$LIB"
    stamp_shipped_in "$handoff"
    # No --allow-branch-tip-fallback flag
  )

  # shipped_in must NOT appear in the file
  ! grep -q 'shipped_in:' "$handoff"
}

# ---------------------------------------------------------------------------
# Test 4: orphan-sweep path with scope that yields a commit
# No fallback flag, but scope: has a real commit => stamp IS written
# ---------------------------------------------------------------------------

@test "orphan-sweep with-scope: shipped_in IS written when scope paths have commits even without fallback flag" {
  local handoff="$TMPDIR_TEST/state/handoffs/orphan-with-scope.md"
  write_handoff "$handoff" "with_scope"

  (
    cd "$TMPDIR_TEST"
    # shellcheck source=/dev/null
    source "$LIB"
    stamp_shipped_in "$handoff"
    # No --allow-branch-tip-fallback flag - but scope resolves to a real commit
  )

  # shipped_in must be present
  grep -q 'shipped_in:' "$handoff"

  # Value must be the 8-char prefix of the scope-path commit
  local expected_prefix="${SCOPE_COMMIT_SHA:0:8}"
  grep -q "shipped_in: $expected_prefix" "$handoff"
}

# ---------------------------------------------------------------------------
# Test 5: idempotency - re-running stamp produces no second shipped_in: line
# ---------------------------------------------------------------------------

@test "idempotency: second invocation does not add a second shipped_in line" {
  local handoff="$TMPDIR_TEST/state/handoffs/idempotent.md"
  write_handoff "$handoff" "with_scope"

  (
    cd "$TMPDIR_TEST"
    # shellcheck source=/dev/null
    source "$LIB"
    stamp_shipped_in "$handoff" --allow-branch-tip-fallback
    # Second invocation
    stamp_shipped_in "$handoff" --allow-branch-tip-fallback
  )

  # Exactly one shipped_in: line must be present
  local count
  count="$(grep -c 'shipped_in:' "$handoff")"
  [ "$count" -eq 1 ]

  # File content after second run must equal content after first run
  # (verify by checking exactly one stamp line and no duplication in frontmatter)
  local fm_count
  fm_count="$(grep -c '^---$' "$handoff")"
  # Standard frontmatter has exactly two --- delimiters
  [ "$fm_count" -eq 2 ]
}
