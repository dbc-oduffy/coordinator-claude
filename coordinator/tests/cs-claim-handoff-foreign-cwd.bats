#!/usr/bin/env bats
# cs-claim-handoff-foreign-cwd.bats — regression net for cs_claim_handoff's optional
# baton-repo-root arg AND its basename-only shared claim path.
#
# Purpose: cs_claim_handoff's claim dir is BASENAME-ONLY (`<base>/handoff-claims/<basename>/`,
# NOT sid-namespaced), so two same-machine sessions with DISTINCT session-ids contend for the
# SAME lock per handoff — restoring DR-110's same-machine concurrent-pickup guard, which the
# per-session-sid switch (spike 031909d8) had silently defeated. The optional 2nd positional arg
# (baton repo root) places that lock under the BATON repo so foreign-cwd pickups contend too.
#
# Spec backlinks: docs/plans/2026-06-17-foreign-cwd-pickup-hardening.md § C3;
#                 docs/plans/2026-06-17-concurrent-pickup-guard-sid-regression.md § C3
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/cs-claim-handoff-foreign-cwd.bats
#      from the ~/.claude repo root.
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
  # CLAUDE_CODE_SESSION_ID → sentinel. Clear ALL inherited slots (the bats runner itself
  # runs inside a Claude Code session and inherits CLAUDE_CODE_SESSION_ID) so each test
  # controls sid explicitly and no call falls through to a runner value.
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

# AC2/AC3 (T1) — foreign-cwd happy path: claim lands under the BATON repo at the BASENAME-ONLY
# path (no <sid> segment), never under cwd.
@test "T1: baton-root claim lands under baton repo (basename-only), ABSENT under cwd (AC2/AC3)" {
  export CLAUDE_CODE_SESSION_ID="sidT1"
  cd "$CWD_A"
  run cs_claim_handoff "foo.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  # positive: claim exists under the baton repo, basename-only (no sid segment)
  [ -d "${BATON_REPO}/.git/coordinator-sessions/handoff-claims/foo.md" ]
  # hard negative: nothing written under the cwd repo
  [ ! -d "${CWD_A}/.git/coordinator-sessions/handoff-claims/foo.md" ]
}

# AC4 (T2) — legacy one-arg call: claim under the cwd repo, basename-only.
@test "T2: legacy one-arg claim lands under cwd repo (basename-only) (AC4)" {
  export CLAUDE_CODE_SESSION_ID="sidT2"
  cd "$CWD_A"
  run cs_claim_handoff "bar.md"
  [ "$status" -eq 0 ]
  [ -d "${CWD_A}/.git/coordinator-sessions/handoff-claims/bar.md" ]
}

# AC1 (T3) — cross-sid collision REGRESSION NET: two DISTINCT session-ids, same baton, different
# cwds → first wins, second is rejected. This is the case that fails on HEAD (sid-namespaced paths
# never collide across distinct sids) and must pass after the basename-only fix.
@test "T3: distinct sids, same baton, different cwds → second claim rejected (AC1 regression)" {
  # Review: code-reviewer — sidX/sidY are literal + distinct; setup() unset the runner's inherited
  # CLAUDE_CODE_SESSION_ID so neither call falls through to it (isolation guaranteed by unset, not env -u).
  cd "$CWD_A"
  CLAUDE_CODE_SESSION_ID="sidX" run cs_claim_handoff "baz.md" "$BATON_REPO"
  [ "$status" -eq 0 ]
  # first session won and recorded its own identity
  [ "$(cat "${BATON_REPO}/.git/coordinator-sessions/handoff-claims/baz.md/session_id")" = "sidX" ]
  # a DIFFERENT session, from a DIFFERENT cwd, must lose — proves real cross-sid contention
  cd "$CWD_B"
  CLAUDE_CODE_SESSION_ID="sidY" run cs_claim_handoff "baz.md" "$BATON_REPO"
  [ "$status" -ne 0 ]
  # Review: code-reviewer — self-describing diagnostic on assertion failure
  [[ "$output" == *"concurrent /pickup detected"* ]] || { echo "expected 'concurrent /pickup detected' in: $output" >&2; return 1; }
}

# AC4 (T4) — fail-loud on a supplied-but-non-git baton root; never a silent cwd fallback.
@test "T4: supplied non-git baton root fails loud, no cwd fallback (AC4)" {
  export CLAUDE_CODE_SESSION_ID="sidT4"
  cd "$CWD_A"
  NONGIT="$(mktemp -d)"
  run cs_claim_handoff "qux.md" "$NONGIT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"is not a git repo"* ]]
  # must NOT have silently written the claim under the cwd repo
  [ ! -d "${CWD_A}/.git/coordinator-sessions/handoff-claims/qux.md" ]
  rmdir "$NONGIT"
}

# AC4 (T5) — stale-PID takeover walks the BATON root (not cwd): a baton-rooted claim held by a
# dead PID is reclaimed by a later pickup. Basename-only path.
@test "T5: stale-PID takeover reclaims baton-rooted claim dir (basename-only), not cwd (AC4)" {
  export CLAUDE_CODE_SESSION_ID="sidT5"
  cd "$CWD_A"
  CLAIM="${BATON_REPO}/.git/coordinator-sessions/handoff-claims/stale.md"
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
  [ ! -d "${CWD_A}/.git/coordinator-sessions/handoff-claims/stale.md" ]
}
