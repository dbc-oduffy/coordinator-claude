#!/usr/bin/env bats
# cs-claim-handoff-foreign-cwd.bats — regression net for cs_claim_handoff's optional
# baton-repo-root arg (foreign-cwd /pickup hardening).
#
# Purpose: cs_claim_handoff gained an optional 2nd positional arg = the baton's repo
# root. When supplied, the atomic claim dir lives under the BATON repo's .git, so two
# pickups of the same baton from different cwds contest the same mkdir. When absent,
# behavior is byte-for-byte the legacy cwd path. A supplied-but-non-git root fails loud.
#
# Spec backlink: docs/plans/2026-06-17-foreign-cwd-pickup-hardening.md § C3 (AC1-AC3, AC8, AC9)
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/cs-claim-handoff-foreign-cwd.bats
#      from the ~/.claude repo root.
#
# Note on the collision test (T3): the claim dir is sid-namespaced
# (<base>/<sid>/handoff-claims/<basename>), so two claims collide only when they share a
# sid. That is the property baton-rooting fixes — a shared-sid sibling resolves the SAME
# lock location regardless of cwd. The cross-session/cross-machine authority is a separate
# layer (SKILL.md Gate 2: the consumed_by frontmatter check after git fetch); this primitive
# is the same-machine/shared-sid belt-and-suspenders. T3 therefore pins a shared sid on purpose.
#
# MSYS note (bash-on-windows-gotchas.md §10): temp paths come from mktemp -d (no leading-slash
# literals that MSYS would rewrite), so the path-translation trap does not apply here.

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
  # The primitive resolves sid from COORDINATOR_SESSION_ID → CLAUDE_SESSION_ID →
  # CLAUDE_CODE_SESSION_ID → sentinel. Clear the higher-priority slots so the test
  # controls sid via CLAUDE_CODE_SESSION_ID (the documented test-override slot).
  unset COORDINATOR_SESSION_ID CLAUDE_SESSION_ID

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

# AC1 (T1) — foreign-cwd happy path: claim lands under the BATON repo, never under cwd.
@test "T1: baton-root claim lands under baton repo, ABSENT under cwd (AC1)" {
  export CLAUDE_CODE_SESSION_ID="sidT1"
  cd "$CWD_A"
  run cs_claim_handoff "foo.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  # positive: claim exists under the baton repo
  [ -d "${BATON_REPO}/.git/coordinator-sessions/sidT1/handoff-claims/foo.md" ]
  # hard negative: nothing written under the cwd repo
  [ ! -d "${CWD_A}/.git/coordinator-sessions/sidT1/handoff-claims/foo.md" ]
}

# AC2 (T2) — legacy one-arg call is unchanged: claim under the cwd repo.
@test "T2: legacy one-arg claim lands under cwd repo (AC2)" {
  export CLAUDE_CODE_SESSION_ID="sidT2"
  cd "$CWD_A"
  run cs_claim_handoff "bar.md"
  [ "$status" -eq 0 ]
  [ -d "${CWD_A}/.git/coordinator-sessions/sidT2/handoff-claims/bar.md" ]
}

# AC3 (T3) — shared-sid collision: the second claim of the same baton from a DIFFERENT cwd
# resolves the same baton-rooted path and is rejected (live holder PID). Proves the lock
# location is cwd-independent. (Shared sid is the precondition — see header note.)
@test "T3: same sid + same baton, different cwds → second claim rejected (AC3)" {
  export CLAUDE_CODE_SESSION_ID="sidT3"
  cd "$CWD_A"
  run cs_claim_handoff "baz.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  cd "$CWD_B"
  run cs_claim_handoff "baz.md" "$BATON_REPO"
  [ "$status" -ne 0 ]
  [[ "$output" == *"concurrent /pickup detected"* ]]
}

# AC8 (T4) — fail-loud on a supplied-but-non-git baton root; never a silent cwd fallback.
@test "T4: supplied non-git baton root fails loud, no cwd fallback (AC8)" {
  export CLAUDE_CODE_SESSION_ID="sidT4"
  cd "$CWD_A"
  NONGIT="$(mktemp -d)"
  run cs_claim_handoff "qux.md" "$NONGIT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"is not a git repo"* ]]
  # must NOT have silently written the claim under the cwd repo
  [ ! -d "${CWD_A}/.git/coordinator-sessions/sidT4/handoff-claims/qux.md" ]
  rmdir "$NONGIT"
}

# AC9 (T5) — stale-PID takeover walks the BATON root (not cwd): a baton-rooted claim held
# by a dead PID is reclaimed by a same-sid pickup. Exercises the exact self-heal path the
# release-asymmetry wart relies on.
@test "T5: stale-PID takeover reclaims baton-rooted claim dir, not cwd (AC9)" {
  export CLAUDE_CODE_SESSION_ID="sidT5"
  cd "$CWD_A"
  CLAIM="${BATON_REPO}/.git/coordinator-sessions/sidT5/handoff-claims/stale.md"
  mkdir -p "$CLAIM"
  # Guaranteed-dead PID: spawn a child, reap it, then reuse its (now-dead) PID.
  ( exit 0 ) & DEAD=$!
  wait "$DEAD" 2>/dev/null || true
  echo "$DEAD"   > "${CLAIM}/pid"
  echo "oldsid"  > "${CLAIM}/session_id"
  echo "stale"   > "${CLAIM}/claimed_at"

  run cs_claim_handoff "stale.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  # reclaimed in place, under the baton root
  [ -d "$CLAIM" ]
  # pid file now holds the live (reclaiming) process, not the dead seed PID
  [ "$(cat "${CLAIM}/pid")" != "$DEAD" ]
  # and nothing leaked under the cwd repo
  [ ! -d "${CWD_A}/.git/coordinator-sessions/sidT5/handoff-claims/stale.md" ]
}
