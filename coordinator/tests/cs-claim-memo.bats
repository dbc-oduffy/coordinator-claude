#!/usr/bin/env bats
# cs-claim-memo.bats — regression net for the memo-pickup claim-lock parity (Gap #1) and
# the holder-identity-checked explicit release (Patrik #1).
#
# Purpose: cross-repo memo pickup now claims atomically at pickup-start via cs_claim_memo
# (a thin wrapper over the generalized cs_claim_artifact), restoring the same single-owner
# concurrent-pickup guard handoffs already have. Memos additionally support explicit release
# on non-terminal disposition (Decline / Surface-to-PM) via cs_release_artifact, which must
# be a NO-OP unless this session is the claim holder (else it would delete a live peer's
# claim — the TOCTOU class cs_reap_stale_claims guards against).
#
# Reproduces the 2026-06-20 whoami collision shape at the primitive level: two sessions,
# same memo, distinct sids → second fails loud.
#
# Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C1/C5
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/cs-claim-memo.bats
#      from the ~/.claude repo root.
#
# Note: bash keeps $$ stable across bats `run` subshells (only $BASHPID changes), so a claim
# written under one `run` is correctly recognised as held-by-$$ in a later `run` in the same test.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
LIB="${SCRIPT_DIR}/../lib/coordinator-session.sh"

_mkrepo() {
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init -q
  git -C "$d" config user.email "test@example.com"
  git -C "$d" config user.name "Test"
}

setup() {
  # Clear ALL sid slots (the bats runner inherits CLAUDE_CODE_SESSION_ID) so each test
  # controls sid explicitly. Same isolation discipline as cs-claim-handoff-foreign-cwd.bats.
  unset COORDINATOR_SESSION_ID CLAUDE_SESSION_ID CLAUDE_CODE_SESSION_ID

  TEST_ROOT="$(mktemp -d)"
  BATON_REPO="${TEST_ROOT}/baton"
  CWD_A="${TEST_ROOT}/cwd-a"
  CWD_B="${TEST_ROOT}/cwd-b"
  _mkrepo "$BATON_REPO"
  _mkrepo "$CWD_A"
  _mkrepo "$CWD_B"

  # shellcheck source=/dev/null
  source "$LIB"
}

teardown() {
  [[ -n "${TEST_ROOT:-}" && -d "$TEST_ROOT" ]] && rm -rf "$TEST_ROOT"
}

# M1 — cs_claim_memo lands under the memo-claims subdir (NOT handoff-claims), basename-only.
@test "M1: cs_claim_memo claim lands under memo-claims (basename-only) (AC1)" {
  export CLAUDE_CODE_SESSION_ID="sidM1"
  cd "$CWD_A"
  run cs_claim_memo "2026-06-21-topic.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  [ -d "${BATON_REPO}/.git/coordinator-sessions/memo-claims/2026-06-21-topic.md" ]
  # class isolation: nothing under handoff-claims
  [ ! -d "${BATON_REPO}/.git/coordinator-sessions/handoff-claims/2026-06-21-topic.md" ]
}

# M2 (AC2) — the whoami collision repro: two distinct sids, same memo, different cwds →
# first wins, second fails loud. This is the race the whole workstream closes.
@test "M2: distinct sids, same memo → second cs_claim_memo rejected (AC2 collision repro)" {
  cd "$CWD_A"
  CLAUDE_CODE_SESSION_ID="sidX" run cs_claim_memo "memo.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  [ "$(cat "${BATON_REPO}/.git/coordinator-sessions/memo-claims/memo.md/session_id")" = "sidX" ]
  cd "$CWD_B"
  CLAUDE_CODE_SESSION_ID="sidY" run cs_claim_memo "memo.md" "$BATON_REPO"
  [ "$status" -ne 0 ]
  [[ "$output" == *"concurrent /pickup detected"* ]] || { echo "expected 'concurrent /pickup detected' in: $output" >&2; return 1; }
}

# M3 (AC2) — stale dead-PID takeover for memo claims (parity with handoff T5).
@test "M3: stale-PID memo claim is taken over (AC2)" {
  export CLAUDE_CODE_SESSION_ID="sidM3"
  cd "$CWD_A"
  CLAIM="${BATON_REPO}/.git/coordinator-sessions/memo-claims/stale.md"
  mkdir -p "$CLAIM"
  ( exit 0 ) & DEAD=$!
  wait "$DEAD" 2>/dev/null || true
  echo "$DEAD"  > "${CLAIM}/pid"
  echo "oldsid" > "${CLAIM}/session_id"
  echo "stale"  > "${CLAIM}/claimed_at"

  run cs_claim_memo "stale.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  [ -d "$CLAIM" ]
  [ "$(cat "${CLAIM}/pid")" != "$DEAD" ]
}

# M4 (AC10) — cs_release_artifact by the HOLDER removes the claim.
@test "M4: cs_release_artifact by the holder releases the claim (AC10)" {
  export CLAUDE_CODE_SESSION_ID="sidM4"
  cd "$CWD_A"
  cs_claim_memo "rel.md" "$BATON_REPO"
  CLAIM="${BATON_REPO}/.git/coordinator-sessions/memo-claims/rel.md"
  [ -d "$CLAIM" ]
  # $$ is stable across run subshells, so the holder check (held_pid == $$) matches.
  run cs_release_artifact "memo" "rel.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  [ ! -d "$CLAIM" ]
}

# M5 (AC10) — cs_release_artifact by a NON-holder is a NO-OP: it must NOT delete a claim
# held by another session. This is the double-release / lost-claim hazard Patrik flagged.
@test "M5: cs_release_artifact by a non-holder is a no-op, claim survives (AC10)" {
  cd "$CWD_A"
  CLAIM="${BATON_REPO}/.git/coordinator-sessions/memo-claims/peer.md"
  mkdir -p "$CLAIM"
  # A different session's claim — pid deliberately != $$ so this exercises the
  # held_pid==$$ string-identity guard specifically (not a liveness check). Assert the
  # premise: the seeded pid must genuinely differ from this process, else the test would
  # pass for the wrong reason.
  [ "999999" != "$$" ]
  echo "999999"  > "${CLAIM}/pid"
  echo "peersid" > "${CLAIM}/session_id"
  echo "now"     > "${CLAIM}/claimed_at"

  run cs_release_artifact "memo" "peer.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  # the peer's claim must STILL exist — release by a non-holder did nothing
  [ -d "$CLAIM" ]
  [ "$(cat "${CLAIM}/pid")" = "999999" ]
}

# M6 (AC10) — cs_release_artifact on an absent claim is an idempotent no-op (return 0).
@test "M6: cs_release_artifact on an absent claim is a no-op (AC10)" {
  cd "$CWD_A"
  run cs_release_artifact "memo" "ghost.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
}

# M7 (AC3) — the no-arg reaper sweeps memo-claims too (not only handoff-claims).
@test "M7: no-arg cs_reap_stale_claims reaps a dead memo claim (AC3)" {
  cd "$CWD_A"
  CLAIM="${CWD_A}/.git/coordinator-sessions/memo-claims/dead.md"
  mkdir -p "$CLAIM"
  ( exit 0 ) & DEAD=$!
  wait "$DEAD" 2>/dev/null || true
  echo "$DEAD" > "${CLAIM}/pid"
  echo "sid"   > "${CLAIM}/session_id"
  echo "old"   > "${CLAIM}/claimed_at"

  # no-arg call (cwd repo) — must reach memo-claims, not just handoff-claims
  run cs_reap_stale_claims
  [ "$status" -eq 0 ]
  [ ! -d "$CLAIM" ]
}
