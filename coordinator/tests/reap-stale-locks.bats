#!/usr/bin/env bats
# reap-stale-locks.bats — bats tests for bin/coordinator-reap-stale-locks
#
# Purpose: regression coverage for the orphaned-`.git/index.lock` reaper. Exercises
#   every reap/preserve branch DETERMINISTICALLY via the script's env test seams
#   (COORDINATOR_LOCK_REAP_AGE_SEC / _MAINT_AGE_SEC / _STABILITY_SEC /
#   _NO_SLEEP) — NO reliance on accidental concurrency timing. This closes the one
#   unmet acceptance criterion of the holodeck index-lock-leak investigation
#   ("a reliable reproducer that does NOT rely on accidental concurrency timing").
#
# Spec backlink: docs/wiki/concurrent-em-hazards.md § H21;
#   originating consult: cross-repo/inbox/2026-05-30-index-lock-leak-concurrent-em.md
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/reap-stale-locks.bats
#      from the ~/.claude repo root.
#      (Override the subject for out-of-tree verification: REAP_BIN=/abs/path npx bats <file>)
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
# Explicit override → default-relative (build-for-someone-else's-machine path order).
SUBJECT="${REAP_BIN:-${SCRIPT_DIR}/../bin/coordinator-reap-stale-locks}"

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

setup() {
  TMPDIR_TEST="$(mktemp -d)"
  REPO="${TMPDIR_TEST}/repo"
  mkdir -p "$REPO"
  git -C "$REPO" init -q
  # Reaper resolves dirs via `git rev-parse`; a bare `git init` worktree suffices.
  GITDIR="${REPO}/.git"
}

teardown() {
  # Kill any lingering background mutator from the mutating-lock test.
  [[ -n "${MUTATOR_PID:-}" ]] && kill "$MUTATOR_PID" 2>/dev/null
  rm -rf "$TMPDIR_TEST"
}

# ---------------------------------------------------------------------------
# Reap path — stale + stable locks are removed
# ---------------------------------------------------------------------------

@test "reaps a stale, stable index.lock and exits 0" {
  printf 'orphan-index-copy' > "${GITDIR}/index.lock"
  run env COORDINATOR_LOCK_REAP_AGE_SEC=0 COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  [ ! -e "${GITDIR}/index.lock" ]
}

@test "reaps a stale, stable next-index-*.lock" {
  printf 'orphan' > "${GITDIR}/next-index-12345.lock"
  run env COORDINATOR_LOCK_REAP_AGE_SEC=0 COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  [ ! -e "${GITDIR}/next-index-12345.lock" ]
}

@test "writes a reap-log entry when it reaps" {
  printf 'orphan' > "${GITDIR}/index.lock"
  run env COORDINATOR_LOCK_REAP_AGE_SEC=0 COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  [ -f "${GITDIR}/lock-reap.log" ]
  grep -q "reaped stale index.lock" "${GITDIR}/lock-reap.log"
}

# ---------------------------------------------------------------------------
# Preserve path — fresh / mutating locks are NEVER reaped
# ---------------------------------------------------------------------------

@test "preserves a fresh index.lock and signals exit 2 (live commit may hold it)" {
  printf 'live-commit-index' > "${GITDIR}/index.lock"
  # Default AGE floor (120s); a just-created lock is too fresh to reap.
  run env COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 2 ]
  [ -e "${GITDIR}/index.lock" ]
}

@test "preserves an actively-mutating index.lock (not stable) and exits 2" {
  printf 'start' > "${GITDIR}/index.lock"
  # Old enough to pass the AGE gate, but a writer mutates it across the
  # stability window so the (mtime,size) re-sample differs -> not reaped.
  ( for _ in $(seq 1 60); do printf 'x' >> "${GITDIR}/index.lock"; sleep 0.05; done ) &
  MUTATOR_PID=$!
  run env COORDINATOR_LOCK_REAP_AGE_SEC=0 COORDINATOR_LOCK_REAP_STABILITY_SEC=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  kill "$MUTATOR_PID" 2>/dev/null
  [ "$status" -eq 2 ]
  [ -e "${GITDIR}/index.lock" ]
}

# ---------------------------------------------------------------------------
# maintenance.lock — independent, larger age floor
# ---------------------------------------------------------------------------

@test "preserves a fresh maintenance.lock even when the index floor is 0" {
  mkdir -p "${GITDIR}/objects"
  printf 'gc' > "${GITDIR}/objects/maintenance.lock"
  # index floor 0 but maint floor default (600s); fresh maint lock survives.
  run env COORDINATOR_LOCK_REAP_AGE_SEC=0 COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  [ -e "${GITDIR}/objects/maintenance.lock" ]
}

@test "reaps a stale maintenance.lock once its own floor is crossed" {
  mkdir -p "${GITDIR}/objects"
  printf 'gc' > "${GITDIR}/objects/maintenance.lock"
  run env COORDINATOR_LOCK_REAP_MAINT_AGE_SEC=0 COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  [ ! -e "${GITDIR}/objects/maintenance.lock" ]
}

# ---------------------------------------------------------------------------
# Error / no-op contract
# ---------------------------------------------------------------------------

@test "exits 1 when not inside a git repository" {
  run env COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$TMPDIR_TEST' && '$SUBJECT'"
  [ "$status" -eq 1 ]
}

@test "is a clean no-op (exit 0) when no locks are present, and idempotent" {
  run env COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
  # second run is identical — idempotent on a clean tree
  run env COORDINATOR_LOCK_REAP_NO_SLEEP=1 \
      bash -c "cd '$REPO' && '$SUBJECT'"
  [ "$status" -eq 0 ]
}
