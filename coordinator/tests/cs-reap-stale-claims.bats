#!/usr/bin/env bats
# cs-reap-stale-claims.bats — regression net for cs_reap_stale_claims (basename-only claim reaper).
#
# Purpose: cs_reap_stale_claims reaps orphaned handoff claims left by cs_claim_handoff. The
# liveness rule is DEAD-PID-ONLY — a live holder is NEVER reaped regardless of claim age (a
# /pickup may legitimately hold a workstream open for hours/days). The "live holder, old claim
# → PRESERVED" case is the load-bearing regression-net: it fails if anyone reintroduces an
# age-based ("OR >24h") reap predicate, which would delete a live holder's claim and re-open
# the same-machine split-brain the basename-only lock exists to prevent.
#
# Spec backlink: docs/plans/2026-06-17-concurrent-pickup-guard-sid-regression.md § C3 (AC5)
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/cs-reap-stale-claims.bats

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
LIB="${SCRIPT_DIR}/../lib/coordinator-session.sh"

setup() {
  unset COORDINATOR_SESSION_ID CLAUDE_SESSION_ID CLAUDE_CODE_SESSION_ID
  TEST_ROOT="$(mktemp -d)"
  REPO="${TEST_ROOT}/repo"
  mkdir -p "$REPO"
  git -C "$REPO" init -q
  git -C "$REPO" config user.email "test@example.com"
  git -C "$REPO" config user.name "Test"
  CLAIMS="${REPO}/.git/coordinator-sessions/handoff-claims"
  mkdir -p "$CLAIMS"
  # shellcheck source=/dev/null
  source "$LIB"
}

teardown() {
  [[ -n "${TEST_ROOT:-}" && -d "$TEST_ROOT" ]] && rm -rf "$TEST_ROOT"
}

# seed a claim dir with a given pid + claimed_at
_seed_claim() {
  local name="$1" pid="$2" claimed_at="$3"
  local d="${CLAIMS}/${name}"
  mkdir -p "$d"
  echo "$pid"        > "${d}/pid"
  echo "sid-seed"    > "${d}/session_id"
  echo "$claimed_at" > "${d}/claimed_at"
}

# AC5 case 1 — dead-PID claim → reaped.
@test "dead-PID claim is reaped" {
  ( exit 0 ) & DEAD=$!
  wait "$DEAD" 2>/dev/null || true
  _seed_claim "dead.md" "$DEAD" "2026-06-17T00:00:00Z"
  run cs_reap_stale_claims "$REPO"
  [ "$status" -eq 0 ]
  [ ! -d "${CLAIMS}/dead.md" ]
}

# AC5 case 2 (LOAD-BEARING regression net for Finding #0) — live PID, claim backdated >25h → PRESERVED.
# A dead-PID-only reaper preserves this; an "OR >24h" predicate would wrongly reap it.
@test "live-PID claim backdated >25h is PRESERVED (no age-based reap)" {
  # $$ is the live bats process — guaranteed alive for the duration of the test.
  _seed_claim "longheld.md" "$$" "1970-01-02T00:00:00Z"   # ~56 years old; far beyond any threshold
  run cs_reap_stale_claims "$REPO"
  [ "$status" -eq 0 ]
  [ -d "${CLAIMS}/longheld.md" ]
}

# AC5 case 3 — live PID, recent claim → preserved.
@test "live-PID recent claim is preserved" {
  _seed_claim "fresh.md" "$$" "2026-06-17T12:00:00Z"
  run cs_reap_stale_claims "$REPO"
  [ "$status" -eq 0 ]
  [ -d "${CLAIMS}/fresh.md" ]
}

# Absent claims dir → no-op, exit 0.
@test "absent claims dir is a no-op" {
  rm -rf "$CLAIMS"
  run cs_reap_stale_claims "$REPO"
  [ "$status" -eq 0 ]
}
