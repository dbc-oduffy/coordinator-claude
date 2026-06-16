#!/usr/bin/env bats
# normalize-consumed-frontmatter.bats — bats tests for bin/normalize-consumed-frontmatter.js
#
# Purpose: verifies widened archive/handoffs/ scan target and holodeck grandfathered-path
# exclusion for the normalize-consumed-frontmatter helper.
#
# Spec backlink: docs/plans/2026-06-15-shipped-in-archive-stamping.md § Chunk C3 (AC4, AC5)
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/normalize-consumed-frontmatter.bats
#      from the ~/.claude repo root.
#
# Negative-spec: tasks/handoffs/archive/ is a grandfathered holodeck-specific path
# (read-only per spinoff-handoffs.md:341-342). The helper MUST NOT be widened to scan
# that path — it is not in TYPE_TO_GLOB and this test suite enforces that contract.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="node ${SCRIPT_DIR}/../bin/normalize-consumed-frontmatter.js"

# ---------------------------------------------------------------------------
# Setup / teardown — synthetic git repo so git ls-files works correctly
# ---------------------------------------------------------------------------

setup() {
  TMPDIR_TEST="$(mktemp -d)"

  # Initialise a git repo in the scratch dir so git ls-files resolves correctly
  # and the helper's tracked-file gate operates (not just the no-git fallback).
  git -C "$TMPDIR_TEST" init -q
  git -C "$TMPDIR_TEST" config user.email "test@example.com"
  git -C "$TMPDIR_TEST" config user.name "Test"
}

teardown() {
  rm -rf "$TMPDIR_TEST"
}

# ---------------------------------------------------------------------------
# Helper: write a handoff file with consumed marker but no shipped_in:
# ---------------------------------------------------------------------------

write_consumed_handoff() {
  # write_consumed_handoff <path>
  # Creates a handoff with a consumed body marker and no shipped_in: field.
  local path="$1"
  mkdir -p "$(dirname "$path")"
  {
    printf -- '---\n'
    printf 'status: active\n'
    printf 'deployment_state: in_flight\n'
    printf 'consumed_at: 2026-06-14\n'
    printf -- '---\n'
    printf '\n# Body content\n'
    printf '\n<!-- consumed: 2026-06-14 c3-test-commit -->\n'
  } > "$path"
}

write_consumed_handoff_with_shipped_in() {
  # write_consumed_handoff_with_shipped_in <path>
  # Creates a handoff already carrying shipped_in: (used to verify no-op).
  local path="$1"
  mkdir -p "$(dirname "$path")"
  {
    printf -- '---\n'
    printf 'status: consumed\n'
    printf 'deployment_state: shipped\n'
    printf 'consumed_at: 2026-06-14\n'
    printf 'shipped_in: abc1234f\n'
    printf -- '---\n'
    printf '\n# Body content\n'
    printf '\n<!-- consumed: 2026-06-14 abc1234f -->\n'
  } > "$path"
}

# ---------------------------------------------------------------------------
# Test: state/handoffs/ scan — baseline unbroken by the widening
# ---------------------------------------------------------------------------

@test "state/handoffs scan: consumed handoff gets shipped_in set" {
  local handoff="${TMPDIR_TEST}/state/handoffs/test-c3-state.md"
  write_consumed_handoff "$handoff"

  # Track the file so git ls-files returns it
  git -C "$TMPDIR_TEST" add "$handoff"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff
  [ "$status" -eq 0 ]

  # shipped_in must be present in the file after the run
  grep -q 'shipped_in: c3-test-commit' "$handoff"
}

@test "state/handoffs scan: status flipped to consumed" {
  local handoff="${TMPDIR_TEST}/state/handoffs/test-c3-status.md"
  write_consumed_handoff "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  $SUBJECT --root "$TMPDIR_TEST" --type handoff

  grep -q 'status: consumed' "$handoff"
}

# ---------------------------------------------------------------------------
# Test: archive/handoffs/ scan — the widened target
# ---------------------------------------------------------------------------

@test "archive/handoffs scan: consumed archived handoff missing shipped_in gets it set" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-archive.md"
  write_consumed_handoff "$handoff"

  # Track the file so git ls-files returns it
  git -C "$TMPDIR_TEST" add "$handoff"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff
  [ "$status" -eq 0 ]

  # shipped_in must be present in the archived handoff
  grep -q 'shipped_in: c3-test-commit' "$handoff"
}

@test "archive/handoffs scan: status flipped to consumed on archived handoff" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-archive-status.md"
  write_consumed_handoff "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  $SUBJECT --root "$TMPDIR_TEST" --type handoff

  grep -q 'status: consumed' "$handoff"
}

@test "archive/handoffs scan: idempotent - already-stamped archive handoff is unchanged" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-already-stamped.md"
  write_consumed_handoff_with_shipped_in "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  local before
  before="$(cat "$handoff")"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff
  [ "$status" -eq 0 ]

  local after
  after="$(cat "$handoff")"

  # File content must be unchanged — shipped_in already present, no re-write
  [ "$before" = "$after" ]
}

@test "archive/handoffs scan: only one shipped_in line after repeated runs" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-idempotent.md"
  write_consumed_handoff "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  $SUBJECT --root "$TMPDIR_TEST" --type handoff
  $SUBJECT --root "$TMPDIR_TEST" --type handoff

  local count
  count="$(grep -c 'shipped_in:' "$handoff")"
  [ "$count" -eq 1 ]
}

# ---------------------------------------------------------------------------
# Test: holodeck exclusion — tasks/handoffs/archive/ MUST NOT be touched
#
# Negative-spec: tasks/handoffs/archive/ is the grandfathered holodeck path
# (spinoff-handoffs.md:341-342). It is NOT in TYPE_TO_GLOB['handoff'] and
# must never be scanned, even if a shipped_in:-less handoff exists there.
# ---------------------------------------------------------------------------

@test "holodeck exclusion: tasks/handoffs/archive/ file is NOT modified even if shipped_in: absent" {
  # Place a consumed handoff in the grandfathered holodeck path
  local holodeck_handoff="${TMPDIR_TEST}/tasks/handoffs/archive/test-c3-holodeck.md"
  write_consumed_handoff "$holodeck_handoff"
  git -C "$TMPDIR_TEST" add "$holodeck_handoff"

  local before
  before="$(cat "$holodeck_handoff")"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff
  # Helper exits 0 regardless (no drift if only unscanned paths have drift)
  [ "$status" -eq 0 ]

  local after
  after="$(cat "$holodeck_handoff")"

  # The holodeck grandfathered file must be byte-identical — helper must not touch it
  [ "$before" = "$after" ]
}

@test "holodeck exclusion: shipped_in: absent in tasks/handoffs/archive/ file after run" {
  local holodeck_handoff="${TMPDIR_TEST}/tasks/handoffs/archive/test-c3-holodeck-no-stamp.md"
  write_consumed_handoff "$holodeck_handoff"
  git -C "$TMPDIR_TEST" add "$holodeck_handoff"

  $SUBJECT --root "$TMPDIR_TEST" --type handoff

  # shipped_in: must NOT have been inserted — the helper must not have touched this file
  ! grep -q 'shipped_in:' "$holodeck_handoff"
}

@test "holodeck exclusion: both archive/handoffs/ and tasks/handoffs/archive/ present - only archive/handoffs/ gets stamped" {
  local archive_handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-should-stamp.md"
  local holodeck_handoff="${TMPDIR_TEST}/tasks/handoffs/archive/test-c3-should-not-stamp.md"

  write_consumed_handoff "$archive_handoff"
  write_consumed_handoff "$holodeck_handoff"

  git -C "$TMPDIR_TEST" add "$archive_handoff"
  git -C "$TMPDIR_TEST" add "$holodeck_handoff"

  $SUBJECT --root "$TMPDIR_TEST" --type handoff

  # archive/handoffs/ file must have shipped_in set
  grep -q 'shipped_in: c3-test-commit' "$archive_handoff"

  # tasks/handoffs/archive/ file must NOT have shipped_in set
  ! grep -q 'shipped_in:' "$holodeck_handoff"
}

# ---------------------------------------------------------------------------
# Test: --dry-run does not mutate archive/handoffs/ files
# ---------------------------------------------------------------------------

@test "dry-run: archive/handoffs/ file is not mutated in dry-run mode" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-dryrun.md"
  write_consumed_handoff "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  local before
  before="$(cat "$handoff")"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff --dry-run
  [ "$status" -eq 0 ]

  local after
  after="$(cat "$handoff")"

  # Dry-run must not mutate the file
  [ "$before" = "$after" ]
}

@test "dry-run: stdout mentions the archive/handoffs/ file as would-be-updated" {
  local handoff="${TMPDIR_TEST}/archive/handoffs/test-c3-dryrun-stdout.md"
  write_consumed_handoff "$handoff"
  git -C "$TMPDIR_TEST" add "$handoff"

  run $SUBJECT --root "$TMPDIR_TEST" --type handoff --dry-run
  [ "$status" -eq 0 ]

  # Output must mention the archive path
  [[ "$output" == *"archive/handoffs"* ]]
}
