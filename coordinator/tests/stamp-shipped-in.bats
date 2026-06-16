#!/usr/bin/env bats
# stamp-shipped-in.bats — bats tests for bin/stamp-shipped-in.js
#
# Purpose: verifies idempotency, `#`-in-SHA quoting defense, and error handling
# for the stamp-shipped-in CLI.
#
# Spec backlink: docs/plans/2026-06-15-shipped-in-archive-stamping.md § Chunk C1 (AC1)
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/stamp-shipped-in.bats
#      from the ~/.claude repo root.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="node ${SCRIPT_DIR}/../bin/stamp-shipped-in.js"

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

setup() {
  TMPDIR_TEST="$(mktemp -d)"
}

teardown() {
  rm -rf "$TMPDIR_TEST"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

write_handoff() {
  # write_handoff <path> [extra_fm_lines...]
  # Writes a minimal handoff file with YAML frontmatter.
  local path="$1"; shift
  {
    printf -- '---\n'
    printf 'status: consumed\n'
    printf 'consumed_at: 2026-06-14\n'
    for line in "$@"; do
      printf '%s\n' "$line"
    done
    printf -- '---\n'
    printf '\n# Body content\n'
  } > "$path"
}

write_handoff_no_frontmatter() {
  local path="$1"
  printf '# No frontmatter here\n\nJust body content.\n' > "$path"
}

# ---------------------------------------------------------------------------
# Test: happy path — stamp inserts shipped_in: field
# ---------------------------------------------------------------------------

@test "happy path: stamp inserts shipped_in into unstamped handoff" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  run $SUBJECT --handoff "$handoff" --sha "abc1234f"
  [ "$status" -eq 0 ]

  # shipped_in must be present in the file
  grep -q 'shipped_in: abc1234f' "$handoff"
}

@test "happy path: shipped_in is inserted after consumed_at" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "deadbeef"

  # consumed_at line must appear before shipped_in line
  local consumed_line shipped_line
  consumed_line="$(grep -n 'consumed_at:' "$handoff" | cut -d: -f1)"
  shipped_line="$(grep -n 'shipped_in:' "$handoff" | cut -d: -f1)"
  [ -n "$consumed_line" ]
  [ -n "$shipped_line" ]
  [ "$consumed_line" -lt "$shipped_line" ]
}

@test "happy path: no other frontmatter fields are mutated" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  # Capture content before stamp
  local before
  before="$(cat "$handoff")"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"

  # status and consumed_at must still be present and unchanged
  grep -q 'status: consumed' "$handoff"
  grep -q 'consumed_at: 2026-06-14' "$handoff"

  # Body content must be preserved
  grep -q '# Body content' "$handoff"

  # The shipped_in field must appear exactly once (field-presence count — robust to
  # diff heuristics that can produce >1 line for a single insertion)
  # Review: F12 — replaced fragile diff-count assertion with field-presence count
  [ "$(grep -c '^shipped_in:' "$handoff")" -eq 1 ]
}

# ---------------------------------------------------------------------------
# Test: idempotency — second invocation is a no-op
# ---------------------------------------------------------------------------

@test "idempotency: second invocation on already-stamped handoff exits 0" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"
  run $SUBJECT --handoff "$handoff" --sha "abc1234f"
  [ "$status" -eq 0 ]
}

@test "idempotency: second invocation produces no diff - file content unchanged" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"

  local after_first
  after_first="$(cat "$handoff")"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"

  local after_second
  after_second="$(cat "$handoff")"

  [ "$after_first" = "$after_second" ]
}

@test "idempotency: only one shipped_in line present after two invocations" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"
  $SUBJECT --handoff "$handoff" --sha "abc1234f"

  local count
  count="$(grep -c 'shipped_in:' "$handoff")"
  [ "$count" -eq 1 ]
}

# ---------------------------------------------------------------------------
# Test: `#`-in-SHA defense — SHA containing `#` must not be silently truncated
# ---------------------------------------------------------------------------

@test "hash-in-SHA defense: SHA with # is YAML-quoted in output" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "abc123 fixed in #42"

  # The value must be single-quoted in the file (the # must NOT truncate the value)
  grep -q "shipped_in: 'abc123 fixed in #42'" "$handoff"
}

@test "hash-in-SHA defense: round-trip value contains the full SHA including hash" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  local sha_with_hash="abc123 fixed in #42"
  $SUBJECT --handoff "$handoff" --sha "$sha_with_hash"

  # The raw file content must contain `#42` — not be truncated before it
  grep -q '#42' "$handoff"
}

@test "hash-in-SHA defense: plain SHA without # is NOT quoted" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  $SUBJECT --handoff "$handoff" --sha "abc1234f"

  # No single-quotes for a simple alphanumeric SHA
  grep -q "shipped_in: abc1234f" "$handoff"
  ! grep -q "shipped_in: '" "$handoff"
}

# ---------------------------------------------------------------------------
# Test: missing frontmatter — handoff with no frontmatter block returns non-zero
# ---------------------------------------------------------------------------

@test "missing frontmatter: exits non-zero when handoff has no frontmatter block" {
  local handoff="${TMPDIR_TEST}/no-fm.md"
  write_handoff_no_frontmatter "$handoff"

  run $SUBJECT --handoff "$handoff" --sha "abc1234f"
  [ "$status" -ne 0 ]
}

@test "missing frontmatter: error message references the file path" {
  local handoff="${TMPDIR_TEST}/no-fm.md"
  write_handoff_no_frontmatter "$handoff"

  run $SUBJECT --handoff "$handoff" --sha "abc1234f"
  # stderr output should mention the file (bats captures combined output in $output)
  [[ "$output" == *"no-fm.md"* ]]
}

# ---------------------------------------------------------------------------
# Test: missing arguments — CLI errors clearly
# ---------------------------------------------------------------------------

@test "missing args: exits non-zero when --sha is absent" {
  local handoff="${TMPDIR_TEST}/handoff.md"
  write_handoff "$handoff"

  run $SUBJECT --handoff "$handoff"
  [ "$status" -ne 0 ]
}

@test "missing args: exits non-zero when --handoff is absent" {
  run $SUBJECT --sha "abc1234f"
  [ "$status" -ne 0 ]
}

@test "missing args: exits non-zero when both args are absent" {
  run $SUBJECT
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# Test: non-existent handoff path returns non-zero
# ---------------------------------------------------------------------------

@test "bad path: exits non-zero for non-existent handoff file" {
  run $SUBJECT --handoff "/tmp/does-not-exist-stamp-test.md" --sha "abc1234f"
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# Test: handoff without consumed_at — shipped_in still inserted (end-of-fm fallback)
# ---------------------------------------------------------------------------

@test "no consumed_at: shipped_in still inserted when consumed_at is absent" {
  local handoff="${TMPDIR_TEST}/no-consumed.md"
  {
    printf -- '---\n'
    printf 'status: consumed\n'
    printf -- '---\n'
    printf '\n# Body\n'
  } > "$handoff"

  run $SUBJECT --handoff "$handoff" --sha "abc1234f"
  [ "$status" -eq 0 ]
  grep -q 'shipped_in: abc1234f' "$handoff"
}
