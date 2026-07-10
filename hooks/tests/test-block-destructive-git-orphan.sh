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
# Review: code-reviewer — Finding 1 (bsd-sed-portability-sweep, 2026-07-10): the
# verb-strip's boundary-inclusive match consumes one space, same as a single-space
# case, so multi-space verb boundaries were traced as equivalent but not covered
# by a live test. Land as durable regression coverage on BSD sed.
run_case "reset --hard double-spaced verb boundaries drops 2 commits" deny "git   reset   --hard   HEAD~2"
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
# 2026-07-10 regression: the quote-strip step must not merge two ADJACENT
# whitespace-containing quoted spans into one garbage token (confirmed bug —
# a single-pass sed ERE treats one span's closing quote as the next span's
# opening quote on 'A' x 'B' -> 'AB'). This case has two independent
# multi-word quoted args in one segment; if they merge, the -C dir extraction
# below would corrupt to a bogus path (same failure mode as P0-2 above, but
# isolating the merge itself rather than the -C resolution consequence).
run_case "two adjacent multi-word quoted spans do not merge (-C resolves correctly)" deny \
  "git -C '$TMP' commit -m 'first message here' && git -C '$TMP' reset --hard HEAD~2"
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
# CRLF/LF robustness (2026-06-30): on Windows the native jq.exe emits decode
# output in text mode, injecting a CR before every LF, so a continuation reaches
# the hook as `\<CR><LF>`. The check-level CR-strip normalizes this so the
# backslash-continuation still joins and the reset is SEEN. Both the `\`+LF and
# explicit `\`+CRLF forms of a HEAD-dropping reset MUST DENY — only the multi-line
# FORM changes. Built from explicit backslash / LF / CR vars (unambiguous bytes).
ORPHAN_BS='\'; ORPHAN_NL=$'\n'; ORPHAN_CR=$'\r'
run_case "reset --hard backslash+LF continuation (explicit bytes) caught" \
  deny "git reset --hard ${ORPHAN_BS}${ORPHAN_NL} HEAD~2"
run_case "reset --hard backslash+CRLF continuation caught" \
  deny "git reset --hard ${ORPHAN_BS}${ORPHAN_CR}${ORPHAN_NL} HEAD~2"

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
# Quoted-argument-content false-positives (2026-07-08 regression):
# a trigger phrase inside a multi-word quoted ARGUMENT must NOT be treated as a
# destructive command. Real destructive ops (unquoted flags/refs) still block.
# ---------------------------------------------------------------------------
run_case "trigger phrase inside a quoted --body arg is not blocked" allow \
  "coordinator-lesson-add --title x --body \"the hook denies git push --force in one call\""
run_case "quoted commit message narrating force-delete not blocked" allow \
  "git commit -m \"explain why git branch -D drops commits\""
run_case "quoted reset --hard narrated in a message not blocked" allow \
  "git commit -m \"note: git reset --hard HEAD~2 would orphan work\""
run_case "quoted-message punctuation does not spawn a bogus destructive segment" allow \
  "git commit -m \"wip; git push --force later maybe\""
# Real ops still caught after the strip (unquoted flags survive):
run_case "real force push still denied post-strip" deny "git push origin main --force"
run_case "real force push alongside a quoted message still denied" deny \
  "git commit -m \"a message with git reset words\" && git push origin main --force"
run_case "short quoted refspec +main (no whitespace) still denied" deny "git push origin '+main'"
# NOTE: a reset-based short-quoted-token assertion belongs here too, but the
# reset/branch CHECK-1/CHECK-3 cases depend on `grep <<< …` word-boundary semantics
# that DIVERGE when this suite is run through the Claude Code Bash tool (its `grep`
# resolves to a bundled ugrep shim). CHECK-2 (push) is pure pattern-match and is the
# reliable regression surface for this quote-strip fix; the reset-side preservation is
# covered by the pre-existing `reset --hard "HEAD~2"` case under real grep.

# ---------------------------------------------------------------------------
# Review: code-reviewer — Finding 2 (2026-07-10): the _orphan_strip_ws_quoted_spans
# awk state machine is verified correct by hand-tracing, but only the cross-span-merge
# shape had a dedicated regression test (and only indirectly, via -C resolution). These
# cases lock in the other hazard shapes the fix's own docstring reasons through, routed
# through CHECK-2 (push) per the reliability note above.
# ---------------------------------------------------------------------------
# Zero-separator adjacent quoted spans (no characters at all between the closing
# quote of span 1 and the opening quote of span 2) — the shape most likely to trip
# a subtle off-by-one in the pairing loop; structurally distinct from the ` && `-
# separated case above.
run_case "zero-separator adjacent quoted spans do not merge" deny \
  "git commit -m \"a b\"\"c d\" && git push origin main --force"
# Embedded opposite-quote-type: a single-quote literal inside a double-quoted span
# must NOT be mistaken for a delimiter (validates cj == q is SAME-literal-only, not
# any-quote-char).
run_case "single-quote literal embedded in double-quoted span preserved" deny \
  "git commit -m \"it's here\" && git push origin main --force"
# Mixed quote types on one line.
run_case "mixed double- and single-quoted spans on one line" deny \
  "git commit -m \"double q\" -m 'single q' && git push origin main --force"
# Unterminated / odd-count quote: locks in "preserved as literal, remainder scanned
# normally" as a permanent contract — a destructive op after an unbalanced quote
# must still be caught.
run_case "unterminated quote preserved as literal, destructive op after it still caught" deny \
  "git commit -m \"unterminated && git push origin main --force"
# Empty quoted span.
run_case "empty quoted span does not disrupt scanning" deny \
  "git commit -m \"\" && git push origin main --force"

# ---------------------------------------------------------------------------
# Override + non-git
# ---------------------------------------------------------------------------
run_case "override env bypasses reset block" allow "git reset --hard HEAD~2" "COORDINATOR_ALLOW_ORPHAN=1"
run_case "non-destructive git allowed" allow "git status"
run_case "git commit allowed" allow "git commit -m wip"
run_case "non-git command allowed" allow "rm -rf build/"

# ---------------------------------------------------------------------------
# bash 3.2 fail-open regression (2026-07-10): "${GOPT[@]}" on an EMPTY array
# under `set -u` is a fatal "unbound variable" on bash < 4.4 (stock macOS
# /bin/bash 3.2), which aborts the hook mid-run with no deny JSON emitted —
# silently ALLOWING a destructive reset. Runs the hook under /bin/bash
# directly (not the test-suite's own $BASH) to reproduce the exact 3.2
# execution path. Skips cleanly when /bin/bash is absent or is itself >=4
# (a supported-bash-only machine has no 3.2 execution path to regress).
# ---------------------------------------------------------------------------
if [[ -x /bin/bash ]]; then
  BASH32_MAJOR=$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 99)
  if [[ "$BASH32_MAJOR" -lt 4 ]]; then
    OUT32=$(emit "git reset --hard HEAD~2" | /bin/bash "$HOOK" 2>/dev/null || true)
    GOT32="allow"
    echo "$OUT32" | grep -q '"permissionDecision":"deny"' && GOT32="deny"
    if [[ "$GOT32" == "deny" ]]; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      echo "FAIL: bash 3.2 (/bin/bash) reset --hard HEAD~2 must DENY, not fail-open (got $GOT32)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-destructive-git-orphan: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
