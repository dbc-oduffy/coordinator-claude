#!/usr/bin/env bats
# coordinator-root-warn-guard.bats - regression net for the COORDINATOR_ROOT mis-root guard.
#
# Purpose: COORDINATOR_ROOT is a TEST-ONLY repo-root override. On 2026-06-24 a holodeck-em
# cross-repo memo reported that the workday backfill ceremony hard-coded
# COORDINATOR_ROOT="$HOME/.claude" on its script invocations, mis-rooting the skipped-day scan
# and changelog/summary writes to the meta-repo on every non-meta project repo. The fix removed
# the hardcode and added a warn-guard: if COORDINATOR_ROOT is set to a path other than the cwd
# git toplevel, the script warns to stderr (canonicalized paths; COORDINATOR_ROOT_WARN_SUPPRESS=1
# silences). This test exercises that guard. The guard logic is mirrored verbatim in
# bin/workday-complete-step9-append-changelog.sh; backfill-scan is the clean self-contained vehicle.
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/coordinator-root-warn-guard.bats
#      from the ~/.claude repo root.

SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/workday-complete-backfill-scan.sh"

setup() {
  TMPDIR_TEST="$(mktemp -d)"
  git -C "$TMPDIR_TEST" init -q
  git -C "$TMPDIR_TEST" config user.email "test@example.com"
  git -C "$TMPDIR_TEST" config user.name "Test"
}

teardown() {
  [ -n "${TMPDIR_TEST:-}" ] && rm -rf "$TMPDIR_TEST"
}

@test "unset COORDINATOR_ROOT in a git repo: no warning, root defaults to cwd toplevel" {
  run env -u COORDINATOR_ROOT bash -c "cd '$TMPDIR_TEST' && bash '$SCRIPT' --lookback 1"
  [ "$status" -eq 0 ]
  [[ "$output" != *WARNING* ]]
}

@test "COORDINATOR_ROOT == cwd toplevel: no warning" {
  TOP="$(cd "$TMPDIR_TEST" && pwd -P)"
  run bash -c "cd '$TMPDIR_TEST' && COORDINATOR_ROOT='$TOP' bash '$SCRIPT' --lookback 1"
  [ "$status" -eq 0 ]
  [[ "$output" != *WARNING* ]]
}

@test "COORDINATOR_ROOT differs from cwd toplevel: warns" {
  OTHER="$(mktemp -d)"
  git -C "$OTHER" init -q
  run bash -c "cd '$TMPDIR_TEST' && COORDINATOR_ROOT='$OTHER' bash '$SCRIPT' --lookback 1"
  rm -rf "$OTHER"
  [[ "$output" == *WARNING* ]]
  [[ "$output" == *COORDINATOR_ROOT* ]]
}

@test "COORDINATOR_ROOT_WARN_SUPPRESS=1 silences the warning on a mismatch" {
  OTHER="$(mktemp -d)"
  git -C "$OTHER" init -q
  run bash -c "cd '$TMPDIR_TEST' && COORDINATOR_ROOT='$OTHER' COORDINATOR_ROOT_WARN_SUPPRESS=1 bash '$SCRIPT' --lookback 1"
  rm -rf "$OTHER"
  [[ "$output" != *WARNING* ]]
}

@test "symlinked-equivalent path (canonicalization) does not false-positive" {
  # A symlink whose target IS the cwd toplevel must not trip the guard.
  LINK="$(mktemp -d)/link-to-top"
  ln -s "$TMPDIR_TEST" "$LINK"
  run bash -c "cd '$TMPDIR_TEST' && COORDINATOR_ROOT='$LINK' bash '$SCRIPT' --lookback 1"
  rm -rf "$(dirname "$LINK")"
  [[ "$output" != *WARNING* ]]
}
