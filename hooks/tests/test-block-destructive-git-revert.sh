#!/usr/bin/env bash
# Test suite for block-destructive-git-revert.sh
#
# Builds a REAL throwaway git repo with a tracked load-bearing file
# (state/handoffs/...) modified-unstaged, plus non-load-bearing and
# peer-claimed fixtures, then drives the hook with crafted Bash-tool JSON
# payloads, asserting allow vs deny. Real repo because the hook's whole value
# is re-deriving true `git status --porcelain` oracle output — a mock would
# test nothing.
#
# Spec backlink: coordinator/hooks/scripts/block-destructive-git-revert.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-destructive-git-revert.sh"
PASS=0
FAIL=0

emit() {
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}'
  else
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "${1//\"/\\\"}"
  fi
}

run_case() {
  # $1 = description, $2 = expected (allow|deny), $3 = command, $4 = env-prefix (optional)
  local desc="$1" expected="$2" cmd="$3" envp="${4:-}"
  local out got
  out=$(emit "$cmd" | env $envp bash "$HOOK" 2>/dev/null || true)
  got="allow"
  echo "$out" | grep -q '"permissionDecision":"deny"' && got="deny"
  if [[ "$got" == "$expected" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (expected $expected, got $got)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
  fi
}

# ---------------------------------------------------------------------------
# Build a real temp repo.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
git init -q -b main
git config user.email t@t.t
git config user.name t
git config commit.gpgsign false

# Tracked, committed load-bearing file — will be modified-unstaged per case.
mkdir -p state/handoffs
echo "handoff content" > state/handoffs/session-handoff.md

# Tracked, committed NON-load-bearing scratch file.
echo "scratch content" > README-scratch.txt

# Tracked baseline file so the repo is non-empty regardless.
echo "tracked" > tracked.txt

git add state/handoffs/session-handoff.md README-scratch.txt tracked.txt
git commit -q -m "c1"

# ---------------------------------------------------------------------------
# DENY — git checkout . whole-tree, load-bearing tracked file modified-unstaged.
# ---------------------------------------------------------------------------
setup_lb_dirty() {
  echo "modified $RANDOM" >> state/handoffs/session-handoff.md
}
reset_clean() {
  git reset -q HEAD -- state/handoffs/session-handoff.md README-scratch.txt 2>/dev/null || true
  git checkout -q -- state/handoffs/session-handoff.md 2>/dev/null || true
  git checkout -q -- README-scratch.txt 2>/dev/null || true
  rm -f state/handoffs/bar-handoff.md
  # Note: rm -f on individual files inside .git/coordinator-sessions/ (not the
  # dir itself) avoids tripping the sibling block-destructive-rm.sh guard,
  # which denies any `rm -rf` targeting a .git store path. find -delete on
  # file entries only (not the dir itself) is not classified as a git-store
  # deletion by that guard's basename/`*/.git/*` match.
  if [[ -d .git/coordinator-sessions ]]; then
    find .git/coordinator-sessions -mindepth 1 -delete 2>/dev/null || true
  fi
}

setup_lb_dirty
run_case "git checkout . (load-bearing modified-unstaged) denied" deny "git checkout ."
reset_clean

setup_lb_dirty
run_case "git checkout -- . (load-bearing) denied" deny "git checkout -- ."
reset_clean

setup_lb_dirty
run_case "git checkout HEAD . (load-bearing) denied" deny "git checkout HEAD ."
reset_clean

setup_lb_dirty
run_case "git checkout HEAD -- . (load-bearing) denied" deny "git checkout HEAD -- ."
reset_clean

# ---------------------------------------------------------------------------
# DENY — git restore . / git restore --worktree . (load-bearing).
# ---------------------------------------------------------------------------
setup_lb_dirty
run_case "git restore . (load-bearing) denied" deny "git restore ."
reset_clean

setup_lb_dirty
run_case "git restore -- . (load-bearing) denied" deny "git restore -- ."
reset_clean

setup_lb_dirty
run_case "git restore --worktree . (load-bearing) denied" deny "git restore --worktree ."
reset_clean

setup_lb_dirty
run_case "git restore -W . (load-bearing) denied" deny "git restore -W ."
reset_clean

# ---------------------------------------------------------------------------
# DENY — git reset --hard / git reset --hard HEAD (load-bearing).
# ---------------------------------------------------------------------------
setup_lb_dirty
run_case "git reset --hard (load-bearing) denied" deny "git reset --hard"
reset_clean

setup_lb_dirty
run_case "git reset --hard HEAD (load-bearing) denied" deny "git reset --hard HEAD"
reset_clean

# ---------------------------------------------------------------------------
# DENY — git stash -u when an untracked load-bearing file exists.
# ---------------------------------------------------------------------------
echo "untracked handoff" > state/handoffs/bar-handoff.md
run_case "git stash -u (untracked load-bearing) denied" deny "git stash -u"
reset_clean

echo "untracked handoff" > state/handoffs/bar-handoff.md
run_case "git stash --include-untracked (untracked load-bearing) denied" deny "git stash --include-untracked"
reset_clean

echo "untracked handoff" > state/handoffs/bar-handoff.md
run_case "git stash push -u (untracked load-bearing) denied" deny "git stash push -u"
reset_clean

echo "untracked handoff" > state/handoffs/bar-handoff.md
run_case "git stash -a (untracked load-bearing, --all) denied" deny "git stash -a"
reset_clean

# ---------------------------------------------------------------------------
# DENY — peer-claimed path. Set up .git/coordinator-sessions/ with a peer
# touched.txt claiming a modified tracked file. Names the peer session.
# ---------------------------------------------------------------------------
PEER_SID="peer-$(date +%s)-cccc"
echo "modified $RANDOM" >> README-scratch.txt   # non-load-bearing, but peer-claimed
mkdir -p .git/coordinator-sessions
mkdir -p ".git/coordinator-sessions/${PEER_SID}"
echo "README-scratch.txt" > ".git/coordinator-sessions/${PEER_SID}/touched.txt"

peer_out=$(emit "git checkout ." | bash "$HOOK" 2>/dev/null || true)
if echo "$peer_out" | grep -q '"permissionDecision":"deny"' && echo "$peer_out" | grep -q "peer-claimed by ${PEER_SID}"; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: peer-claimed path denies and names peer session"
  [[ -n "$peer_out" ]] && echo "      out: $(echo "$peer_out" | head -c 300)"
fi
reset_clean

# ---------------------------------------------------------------------------
# ALLOW — scoped checkout, branch ops, staged-only restore, non-load-bearing,
# scoped stash, override, dry adversarial data-occurrence probes.
# ---------------------------------------------------------------------------

# Scoped checkout of a specific path — never matched (not whole-tree).
setup_lb_dirty
run_case "git checkout -- state/handoffs/session-handoff.md (scoped) allowed" allow \
  "git checkout -- state/handoffs/session-handoff.md"
reset_clean

# Branch switch — not matched (different op; no pathspec `.`).
run_case "git checkout main (branch op) allowed" allow "git checkout main"
run_case "git checkout -b feat (branch op) allowed" allow "git checkout -b feat-test-branch"

# git restore --staged . (staged-only, no -W) — non-destructive, explicitly allowed.
setup_lb_dirty
git add state/handoffs/session-handoff.md
run_case "git restore --staged . (staged-only) allowed" allow "git restore --staged ."
reset_clean

# git checkout . when only non-load-bearing, non-peer-claimed files are dirty.
echo "modified $RANDOM" >> README-scratch.txt
run_case "git checkout . (only non-load-bearing dirty) allowed" allow "git checkout ."
reset_clean

# Pure-staged load-bearing file, no additional unstaged edit — checkout . /
# restore . (worktree-targeted, default scope) do NOT touch staged/index
# content, so this must ALLOW (Finding 1 regression net: pre-fix, the oracle
# over-included the index column and wrongly DENIED this routine WIP shape).
git add state/handoffs/session-handoff.md
run_case "git checkout . (pure-staged, no unstaged edit) allowed" allow "git checkout ."
reset_clean

git add state/handoffs/session-handoff.md
run_case "git restore . (pure-staged, no unstaged edit) allowed" allow "git restore ."
reset_clean

# Scoped stash — not matched (has -- pathspec).
echo "untracked handoff" > state/handoffs/bar-handoff.md
run_case "git stash push -u -- somepath (scoped) allowed" allow "git stash push -u -- somepath"
reset_clean

# Plain git stash (no -u/-a) — out of scope, tracked-only stash is recoverable.
setup_lb_dirty
run_case "git stash (no -u, tracked only) allowed" allow "git stash"
git stash pop -q 2>/dev/null || true
reset_clean

# Override bypasses a would-deny.
setup_lb_dirty
run_case "git checkout . with COORDINATOR_OVERRIDE_GIT_REVERT=1 allowed" allow \
  "git checkout ." "COORDINATOR_OVERRIDE_GIT_REVERT=1"
reset_clean

# Dry / data-occurrence adversarial probes — command-position anchor.
run_case "echo 'git checkout .' (data occurrence) allowed" allow "echo 'git checkout .'"
run_case "grep 'git reset --hard' f (data occurrence) allowed" allow "grep 'git reset --hard' f"

# Non-covered commands — fast bail.
run_case "git status (non-covered verb) allowed" allow "git status"
run_case "ls (non-git command) allowed" allow "ls"

# Reset without --hard — not matched.
run_case "git reset (soft, no --hard) allowed" allow "git reset"
run_case "git reset --soft HEAD~1 allowed" allow "git reset --soft HEAD~1"

# stash subcommands that are not a sweep form (pop/apply/drop/list) — not matched.
run_case "git stash pop allowed" allow "git stash pop"
run_case "git stash list allowed" allow "git stash list"

# ---------------------------------------------------------------------------
# bash 3.2 fail-open regression (2026-07-10): "${_gr_timeout_prefix[@]}" and
# "${GIT_C_ARGS[@]}" on an EMPTY array under `set -u` are fatal "unbound
# variable" on bash < 4.4 (stock macOS /bin/bash 3.2) — both are commonly
# empty (_gr_timeout_prefix when `timeout` is absent; GIT_C_ARGS when the
# command carries no `git -C <dir>`). This aborts the hook mid-run with no
# deny JSON emitted — silently ALLOWING a destructive whole-tree revert. Runs
# the hook under /bin/bash directly (not the test suite's own $BASH) against
# the load-bearing-dirty fixture to reproduce the exact 3.2 execution path.
# Skips cleanly when /bin/bash is absent or is itself >=4.
# ---------------------------------------------------------------------------
if [[ -x /bin/bash ]]; then
  BASH32_MAJOR=$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 99)
  if [[ "$BASH32_MAJOR" -lt 4 ]]; then
    setup_lb_dirty
    OUT32=$(emit "git checkout ." | /bin/bash "$HOOK" 2>/dev/null || true)
    GOT32="allow"
    echo "$OUT32" | grep -q '"permissionDecision":"deny"' && GOT32="deny"
    if [[ "$GOT32" == "deny" ]]; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      echo "FAIL: bash 3.2 (/bin/bash) git checkout . must DENY, not fail-open (got $GOT32)"
    fi
    reset_clean
  fi
fi

# ---------------------------------------------------------------------------
# bash 3.2 fail-open regression, empty-_live_sids path (2026-07-10):
# "${_live_sids[@]}" on an EMPTY array under `set -u` is a fatal "unbound
# variable" on bash < 4.4 (stock macOS /bin/bash 3.2) — including a
# DECLARED-empty array, not just unset. _live_sids is empty whenever
# cs_live_session_ids resolves zero live sessions, which is the case here: a
# dead-session dir with a meta.json is present (sess_dir glob non-empty, so
# the peer-claim probe's canonical-liveness branch runs) but has no valid
# heartbeat, so cs_live_session_ids returns nothing. This is a DIFFERENT
# crash site than the _gr_timeout_prefix/GIT_C_ARGS regression above (that
# one fires earlier, in the oracle call; this one fires inside
# _gr_peer_claim_of, reached only once the oracle has already produced
# AFFECTED_PATHS). Runs the hook under /bin/bash directly on the
# load-bearing-dirty fixture plus a dead-session dir, confirming both (a)
# DENY fires and (b) no "unbound variable" is emitted to stderr. Skips
# cleanly when /bin/bash is absent or is itself >=4.
# ---------------------------------------------------------------------------
if [[ -x /bin/bash ]]; then
  BASH32_MAJOR=$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 99)
  if [[ "$BASH32_MAJOR" -lt 4 ]]; then
    setup_lb_dirty
    mkdir -p .git/coordinator-sessions/deadsession
    echo '{}' > .git/coordinator-sessions/deadsession/meta.json
    OUT32B=$(emit "git checkout ." | /bin/bash "$HOOK" 2>/tmp/revert32-stderr.$$ || true)
    ERR32B=$(cat /tmp/revert32-stderr.$$ 2>/dev/null || true)
    rm -f /tmp/revert32-stderr.$$
    GOT32B="allow"
    echo "$OUT32B" | grep -q '"permissionDecision":"deny"' && GOT32B="deny"
    if [[ "$GOT32B" == "deny" ]] && ! echo "$ERR32B" | grep -q 'unbound variable'; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      echo "FAIL: bash 3.2 (/bin/bash) git checkout . with dead-session/no-live-peer must DENY with no unbound-variable crash (got $GOT32B; stderr: $(printf '%s' "$ERR32B" | head -c 120))"
    fi
    reset_clean
    rm -rf .git/coordinator-sessions
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-destructive-git-revert: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
