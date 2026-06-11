#!/usr/bin/env bash
# Test suite for block-destructive-git-orphan.sh
#
# Builds a REAL throwaway git repo and drives the hook with crafted Bash-tool
# JSON payloads, asserting allow (exit 0, no deny JSON) vs deny (Form-A JSON with
# permissionDecision=deny on stdout). The repo is real because the hook's whole
# value is that it re-derives true git state — a mocked repo would test nothing.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-destructive-git-orphan.sh"
PASS=0
FAIL=0

emit() {
  # $1 = command string -> Bash-tool PreToolUse JSON
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
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 160)"
  fi
}

# ---------------------------------------------------------------------------
# Build a real temp repo:  main(3 commits) , feature-unique , feature-merged
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
git init -q -b main
git config user.email t@t.t
git config user.name t
git config commit.gpgsign false

commit() { git commit -q --allow-empty -m "$1"; }
commit "c1"; commit "c2"; commit "c3"          # main has 3 commits

# A fake "remote-behind" ref: 'origin-main' sitting at c1, two behind HEAD.
git branch behind-2 HEAD~2                       # points at c1

# feature-merged: branched, then its content is already on main (empty -> merged)
git branch feature-merged main                   # tip == main tip -> contained in main

# feature-unique: a branch with a commit on no other ref
git checkout -q -b feature-unique
commit "unique-work"
git checkout -q main

# ---------------------------------------------------------------------------
# CHECK 1 — reset --hard
# ---------------------------------------------------------------------------
run_case "reset --hard HEAD~2 drops 2 commits" deny "git reset --hard HEAD~2"
run_case "reset --hard to behind ref drops commits" deny "git reset --hard behind-2"
run_case "reset --hard HEAD drops nothing" allow "git reset --hard HEAD"
run_case "reset --hard (no target = HEAD) drops nothing" allow "git reset --hard"
run_case "reset --hard to current tip drops nothing" allow "git reset --hard main"
run_case "reset --hard with cd prefix still caught" deny "cd '$TMP' && git reset --hard HEAD~2"
run_case "reset --hard to bogus ref is not false-blocked" allow "git reset --hard nonexistent-ref-xyz"
run_case "soft reset is ignored" allow "git reset --soft HEAD~2"
run_case "plain reset (no --hard) is ignored" allow "git reset HEAD~2"
# P0-1: safe first op must NOT mask a destructive later op (chained segments)
run_case "chained: safe reset then destructive reset caught" deny "git reset --hard HEAD && git reset --hard HEAD~2"
run_case "chained: status then destructive reset caught" deny "git status && git reset --hard HEAD~2"
run_case "chained: destructive then safe (first segment caught)" deny "git reset --hard HEAD~2 ; git log"
# P0-2: per-segment git -C resolves the right repo on a chained op (quoted path)
run_case "chained git -C (quoted path) second-op evaluated in right repo" deny "git -C '$TMP' status && git -C '$TMP' reset --hard HEAD~2"
run_case "git -C unquoted path reset caught" deny "git -C $TMP reset --hard HEAD~2"
# Quoted refs must not evade extraction
run_case "reset --hard double-quoted ref caught" deny 'git reset --hard "HEAD~2"'
run_case "reset --hard single-quoted ref caught" deny "git reset --hard 'behind-2'"
# Unverifiable subshell target fails SAFE (deny)
run_case "reset --hard subshell target denied (unverifiable)" deny 'git reset --hard $(git rev-parse HEAD~2)'
# Pathspec / invalid-multi-token reset forms do NOT move HEAD -> allow
run_case "reset --hard <ref> -- <path> (no HEAD move) allowed" allow "git reset --hard HEAD~2 -- somefile.txt"
run_case "reset --hard <ref> <path> (invalid: --hard+paths) allowed" allow "git reset --hard HEAD~2 somefile.txt"
# Backslash-newline line continuation joined then caught
bslash_reset=$'git reset \\\n  --hard HEAD~2'
run_case "reset --hard across backslash-continuation caught" deny "$bslash_reset"

# ---------------------------------------------------------------------------
# CHECK 2 — force push
# ---------------------------------------------------------------------------
run_case "push --force denied" deny "git push origin main --force"
run_case "push -f denied" deny "git push -f origin main"
run_case "push bundled -uf denied" deny "git push -uf origin main"
run_case "push +refspec (force) denied" deny "git push origin +main"
run_case "push +refspec colon form denied" deny "git push origin +HEAD:main"
run_case "push --force-with-lease allowed" allow "git push origin main --force-with-lease"
run_case "push --follow-tags (has f, long flag) allowed" allow "git push --follow-tags origin main"
run_case "push -u (set upstream, no force) allowed" allow "git push -u origin main"
run_case "ordinary push allowed" allow "git push origin main"

# ---------------------------------------------------------------------------
# CHECK 3 — branch -D
# ---------------------------------------------------------------------------
run_case "branch -D unique-commit branch denied" deny "git branch -D feature-unique"
run_case "branch -D merged branch allowed" allow "git branch -D feature-merged"
run_case "branch -d (lowercase, no force) not evaluated" allow "git branch -d feature-unique"
run_case "branch -d --force unique branch denied" deny "git branch -d --force feature-unique"
run_case "branch -d -f unique branch denied" deny "git branch -d -f feature-unique"
run_case "branch -d --force merged branch allowed" allow "git branch -d --force feature-merged"
run_case "branch --delete --force unique branch denied" deny "git branch --delete --force feature-unique"
run_case "branch -D quoted name denied" deny "git branch -D 'feature-unique'"
run_case "branch -D nonexistent branch not blocked" allow "git branch -D no-such-branch"

# ---------------------------------------------------------------------------
# Override + non-git
# ---------------------------------------------------------------------------
run_case "override env bypasses reset block" allow "git reset --hard HEAD~2" "COORDINATOR_ALLOW_ORPHAN=1"
run_case "non-destructive git allowed" allow "git status"
run_case "git commit allowed" allow "git commit -m wip"
run_case "non-git command allowed" allow "rm -rf build/"

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-destructive-git-orphan: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
