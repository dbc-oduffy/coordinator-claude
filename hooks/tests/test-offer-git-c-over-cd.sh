#!/usr/bin/env bash
# Test suite for offer-git-c-over-cd.sh
#
# Drives the hook with crafted Bash-tool JSON payloads and asserts allow vs deny
# (the "deny" here is the offer/redirect mechanism, not a destructive block).
# Also asserts the redirect message reconstructs a correct `git -C` suggestion.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/offer-git-c-over-cd.sh"
DISPATCHER="$SCRIPT_DIR/../scripts/preuse-bash-dispatch.sh"
PASS=0
FAIL=0

emit() {
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}'
  else
    local c="${1//\\/\\\\}"; c="${c//\"/\\\"}"; c="${c//$'\n'/\\n}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$c"
  fi
}

emit_with_cwd() {
  # $1 = command, $2 = cwd (top-level field, as the harness injects it)
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$1" --arg w "$2" '{tool_name:"Bash",tool_input:{command:$c},cwd:$w}'
  else
    local c="${1//\\/\\\\}"; c="${c//\"/\\\"}"; c="${c//$'\n'/\\n}"
    local w="${2//\\/\\\\}"; w="${w//\"/\\\"}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$c" "$w"
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
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 200)"
  fi
}

run_case_cwd() {
  # $1 = description, $2 = expected (allow|deny), $3 = command, $4 = cwd, $5 = env-prefix (optional)
  # Review: code-reviewer — F6: add optional env-prefix $5 matching run_case's $4 so T2 cases
  # can test with COORDINATOR_ALLOW_CD_PREFIX=1 without a separate reimplementation.
  local desc="$1" expected="$2" cmd="$3" cwd="$4" envp="${5:-}"
  local out got
  out=$(emit_with_cwd "$cmd" "$cwd" | env $envp bash "$HOOK" 2>/dev/null || true)
  got="allow"
  echo "$out" | grep -q '"permissionDecision":"deny"' && got="deny"
  if [[ "$got" == "$expected" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (expected $expected, got $got)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 200)"
  fi
}

assert_deny_reason() {
  # $1 = description, $2 = command, $3 = substring expected in the DECODED deny reason
  # Review: code-reviewer — F7: renamed from assert_suggestion; added deny-path guard.
  # The old name implied it worked for any case; calling it on a T1/T2 allow+rewrite
  # case now produces a clear FAIL instead of silently passing.
  # Decode the JSON reason first: in the raw envelope, suggestion quotes are
  # backslash-escaped (\"), so a literal grep of the raw JSON would miss a quoted
  # path. Match against the decoded reason text the model actually sees.
  local desc="$1" cmd="$2" want="$3" out reason decision
  out=$(emit "$cmd" | bash "$HOOK" 2>/dev/null || true)
  # Guard: this helper is only correct for deny-path cases.
  if command -v jq &>/dev/null; then
    decision=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // ""' 2>/dev/null || true)
    reason=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null || true)
  else
    local _py; _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    decision=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecision"])
except Exception: pass' 2>/dev/null || true)
    reason=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecisionReason"])
except Exception: pass' 2>/dev/null || true)
  fi
  if [[ "$decision" != "deny" ]]; then
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (assert_deny_reason called on non-deny output; decision=${decision:-<empty>})"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
    return
  fi
  if printf '%s' "$reason" | grep -qF "$want"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (deny reason did not contain: $want)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
  fi
}

assert_rewrite() {
  # $1 = description, $2 = command, $3 = exact expected updatedInput.command, $4 = cwd (optional)
  # Asserts that the hook emits an allow+updatedInput envelope and that
  # updatedInput.command matches $3 exactly.
  local desc="$1" cmd="$2" want="$3" cwd="${4:-}" out got_cmd
  if [[ -n "$cwd" ]]; then
    out=$(emit_with_cwd "$cmd" "$cwd" | bash "$HOOK" 2>/dev/null || true)
  else
    out=$(emit "$cmd" | bash "$HOOK" 2>/dev/null || true)
  fi
  if command -v jq &>/dev/null; then
    got_cmd=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
  else
    local _py; _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    got_cmd=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print(d["hookSpecificOutput"]["updatedInput"]["command"])
except Exception: pass' 2>/dev/null || true)
  fi
  if [[ "$got_cmd" == "$want" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc"
    echo "      want: $want"
    echo "      got:  $got_cmd"
    [[ -n "$out" ]] && echo "      raw: $(echo "$out" | head -c 300)"
  fi
}

assert_context() {
  # $1 = description, $2 = command, $3 = substring expected in additionalContext, $4 = cwd (optional)
  # Review: code-reviewer — F4: assert additionalContext contains the expected phrase for T1/T2
  # allow+rewrite cases. Complements assert_rewrite (which checks updatedInput.command only).
  local desc="$1" cmd="$2" want="$3" cwd="${4:-}" out ctx
  if [[ -n "$cwd" ]]; then
    out=$(emit_with_cwd "$cmd" "$cwd" | bash "$HOOK" 2>/dev/null || true)
  else
    out=$(emit "$cmd" | bash "$HOOK" 2>/dev/null || true)
  fi
  if command -v jq &>/dev/null; then
    ctx=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // ""' 2>/dev/null || true)
  else
    local _py; _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    ctx=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])
except Exception: pass' 2>/dev/null || true)
  fi
  if printf '%s' "$ctx" | grep -qF "$want"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (additionalContext did not contain: $want)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
  fi
}

assert_rewrite_dispatcher() {
  # Like assert_rewrite but pipes through the full DISPATCHER (not the standalone hook).
  # Review: code-reviewer — F3: integration test that proves the dispatcher correctly
  # forwards .cwd to check_offer_git_c so T2 fires end-to-end in production.
  local desc="$1" cmd="$2" want="$3" cwd="${4:-}" out got_cmd
  if [[ -n "$cwd" ]]; then
    out=$(emit_with_cwd "$cmd" "$cwd" | bash "$DISPATCHER" 2>/dev/null || true)
  else
    out=$(emit "$cmd" | bash "$DISPATCHER" 2>/dev/null || true)
  fi
  if command -v jq &>/dev/null; then
    got_cmd=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
  else
    local _py; _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    got_cmd=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print(d["hookSpecificOutput"]["updatedInput"]["command"])
except Exception: pass' 2>/dev/null || true)
  fi
  if [[ "$got_cmd" == "$want" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc"
    echo "      want: $want"
    echo "      got:  $got_cmd"
    [[ -n "$out" ]] && echo "      raw: $(echo "$out" | head -c 300)"
  fi
}

# ---------------------------------------------------------------------------
# TIER 1 AUTO-REWRITE — 2-segment `cd X && git Y`: always allow + updatedInput.
# ---------------------------------------------------------------------------
run_case "cd then git (&&) auto-rewritten (tier 1)" allow "cd /c/Users/operator/.claude && git log --oneline -1"
run_case "cd then git (;) auto-rewritten (tier 1)" allow "cd /repo; git status --porcelain"
run_case "cd then git (newline) now denies (v5 multi-line bail, T1 falls to deny+offer)" deny "cd /repo
git add -- file.txt"
run_case "cd then git with backslash-newline continuation now denies (v5 multi-line bail, T1 falls to deny+offer)" deny "cd /repo \\
git commit -m x"
# 3-segment case (followers present, non-redundant cd, no cwd in payload) → tier 3 deny.
run_case "cd then git add then commit (3 segments) still denies (tier 3)" deny "cd /repo && git add -- a && git commit -m b"

# ---------------------------------------------------------------------------
# ALLOW — out of scope or already correct.
# ---------------------------------------------------------------------------
run_case "already git -C (good form) allowed" allow "git -C /repo log --oneline -1"
run_case "plain git, no cd, allowed" allow "git status"
run_case "cd then non-git (npm) allowed" allow "cd /repo && npm install"
run_case "cd then npm then git (seg2 not git) allowed" allow "cd /repo && npm i && git status"
run_case "non-cd leading, cd mid-chain (v1 limitation) allowed" allow "ls && cd /repo && git status"
run_case "no cd at all allowed" allow "echo hello && git log"
run_case "cd alone (no git) allowed" allow "cd /repo && ls -la"
run_case "override env bypasses redirect" allow "cd /repo && git status" "COORDINATOR_ALLOW_CD_PREFIX=1"
run_case "echo mentioning cd and git allowed" allow "echo 'use cd then git'"
# Sequencing-operator discrimination (review finding F2): only && ; newline stall.
run_case "cd || git (alternation, not a stall) allowed" allow "cd /x || git status"
run_case "cd | git (pipe, not a stall) allowed" allow "cd /x | git log"
# cd flags / special forms have no clean git -C rewrite (F6/F12/F15) — leave alone.
run_case "cd - (previous dir) allowed" allow "cd - && git status"
run_case "cd -L flag allowed" allow "cd -L /repo && git status"
run_case "cd -P flag allowed" allow "cd -P /repo && git status"
run_case "cd -- end-of-options allowed" allow "cd -- /repo && git status"
# Quoted && / ; inside a git argument must not mis-redirect (unbalanced-quote guard).
run_case "quoted && in commit msg not redirected" allow "cd /repo && git commit -m \"fix: a && b\""
run_case "quoted ; in commit msg not redirected"  allow "cd /repo && git commit -m \"step 1; step 2\""

# ---------------------------------------------------------------------------
# Tier-1 auto-rewrite: updatedInput.command contains the git -C form.
# (2-segment cases — no deny reason, use assert_rewrite not assert_suggestion)
# ---------------------------------------------------------------------------
assert_rewrite "tier-1: updatedInput rewrites to git -C <path>" \
  "cd /c/Users/operator/.claude && git log --oneline -1" \
  "git -C /c/Users/operator/.claude log --oneline -1"
assert_rewrite "tier-1: updatedInput quotes a spaced path" \
  "cd '/c/Program Files/repo' && git status" \
  'git -C "/c/Program Files/repo" status'
# A variable cd target is rewritten verbatim (git -C accepts the same token).
assert_rewrite "tier-1: variable target rewritten verbatim" \
  "cd \$HOME && git status" \
  "git -C \$HOME status"

# T1 additionalContext: must mention the rewrite, the git -C form, and the override var.
# Review: code-reviewer — F4: assert additionalContext content for T1 rewrites.
assert_context "tier-1: additionalContext mentions Auto-rewritten" \
  "cd /c/Users/operator/.claude && git log --oneline -1" \
  "Auto-rewritten"
assert_context "tier-1: additionalContext mentions git -C" \
  "cd /c/Users/operator/.claude && git log --oneline -1" \
  "git -C"
assert_context "tier-1: additionalContext mentions override var" \
  "cd /c/Users/operator/.claude && git log --oneline -1" \
  "COORDINATOR_ALLOW_CD_PREFIX=1"

# The override env var mention lives in the TIER-3 deny reason (3-segment, no cwd).
assert_deny_reason "tier-3 deny reason names the override env var" \
  "cd /repo && git status; echo done" \
  "COORDINATOR_ALLOW_CD_PREFIX=1"

# Multi-git chain: tier 3 (has followers, non-redundant cd, no cwd) — deny reason
# still carries the full-chain suggestion (first git gets -C, rest appended verbatim).
assert_deny_reason "multi-git chain rewrites first git in place, preserves rest (tier-3 reason)" \
  "cd /repo && git add -- a && git commit -m b" \
  "git -C /repo add -- a && git commit -m b"

# ---------------------------------------------------------------------------
# v2: chain preservation + cwd-binding note.
# ---------------------------------------------------------------------------
# Followers (non-git) are preserved verbatim in the suggestion.
assert_deny_reason "chain with non-git follower preserved in suggestion" \
  "cd /repo && git log --oneline -1; head -3 README.md" \
  "git -C /repo log --oneline -1; head -3 README.md"

# Suggestion carries a cwd-binding note that names the cd target.
assert_deny_reason "cwd-binding note names the cd target" \
  "cd /repo && git log -1; head -3 README.md" \
  "no longer run with '/repo' as cwd"

# Multiple followers are all preserved.
assert_deny_reason "multiple followers all preserved" \
  "cd /repo && git status; echo done; ls -la" \
  "git -C /repo status; echo done; ls -la"

# Follower content captured verbatim from the body/tail split point onward —
# anything inside the follower (including a ';' inside a quoted string) is part of
# the verbatim tail and is never re-scanned. Quote-awareness in the awk loop 2
# applies to LOCATING the split, not to parsing the follower; the in-practice
# load-bearing protection for `;` inside SEG1's own quoted argument is the bash
# unbalanced-quote guard upstream, not this assertion.
assert_deny_reason "follower captured verbatim from split point" \
  "cd /repo && git status; echo 'a;b'" \
  "echo 'a;b'"

# ---------------------------------------------------------------------------
# v3: tier-2 auto-rewrite (redundant cd — target == cwd) and tier-3 regression.
# ---------------------------------------------------------------------------
# Determine a canonical directory to use as the fake cwd for tier-2 tests.
# Must resolve the same way the hook's _offer_normalize_path does (realpath when
# available, trailing-slash strip otherwise). SCRIPT_DIR is always an absolute
# path (no trailing slash from `pwd`), so it round-trips cleanly.
if command -v realpath >/dev/null 2>&1; then
  TIER2_DIR=$(realpath "$SCRIPT_DIR")
else
  TIER2_DIR="$SCRIPT_DIR"
fi

# Tier 2: redundant cd (target == cwd) with followers → allow + stripped command.
run_case_cwd "tier-2: redundant cd with followers auto-stripped" allow \
  "cd ${TIER2_DIR} && git status; echo done" "$TIER2_DIR"
assert_rewrite "tier-2: stripped cmd is git body + followers" \
  "cd ${TIER2_DIR} && git status; echo done" \
  "git status; echo done" \
  "$TIER2_DIR"

# Review: code-reviewer — F5: T2 with && follower (was only `;` covered before).
assert_rewrite "tier-2: stripped cmd with && follower" \
  "cd ${TIER2_DIR} && git status && echo done" \
  "git status && echo done" \
  "$TIER2_DIR"

# Review: code-reviewer — F4: T2 additionalContext assertions.
assert_context "tier-2: additionalContext mentions stripped" \
  "cd ${TIER2_DIR} && git status; echo done" \
  "stripped" \
  "$TIER2_DIR"
assert_context "tier-2: additionalContext mentions cwd already matches" \
  "cd ${TIER2_DIR} && git status; echo done" \
  "cwd already matches" \
  "$TIER2_DIR"
assert_context "tier-2: additionalContext mentions override var" \
  "cd ${TIER2_DIR} && git status; echo done" \
  "COORDINATOR_ALLOW_CD_PREFIX=1" \
  "$TIER2_DIR"

# Review: code-reviewer — F8: T2 with Windows-style paths. The C:/... → /c/... normalization
# is pure string manipulation and verifiable on POSIX even when /c/... doesn't exist on disk
# (realpath falls back to stripped-slash form for both target and cwd → equal → T2 fires).
run_case_cwd "tier-2: Windows-style path C:/... triggers T2 (normalized equal)" allow \
  "cd C:/Users/operator/repo && git status; echo done" "C:/Users/operator/repo"
assert_rewrite "tier-2: Windows-style path stripped command correct" \
  "cd C:/Users/operator/repo && git status; echo done" \
  "git status; echo done" \
  "C:/Users/operator/repo"

# Review: code-reviewer — F3: DISPATCHER-PATH integration test. Proves Finding-1 fix:
# the dispatcher now parses .cwd from the JSON payload and forwards it as $3 to
# check_offer_git_c, so T2 fires end-to-end in production (not just via standalone hook).
# NOTE: The existing T2 tests above exercise check_offer_git_c directly (cwd as arg);
# this test exercises the full dispatcher→hook path with .cwd in the JSON envelope.
assert_rewrite_dispatcher "dispatcher-path T2: redundant cd stripped end-to-end via dispatcher" \
  "cd ${TIER2_DIR} && git status; echo done" \
  "git status; echo done" \
  "$TIER2_DIR"

# Tier 3 regression: non-redundant cd with followers (X != cwd) → still denies.
run_case_cwd "tier-3: non-redundant cd with followers still denies" deny \
  "cd /repo && git log -1; echo done" "/other/dir"

# Tier 3 regression: non-redundant cd with followers still carries the cwd-binding note.
assert_deny_reason "tier-3: cwd-binding note still present for non-redundant cd + follower" \
  "cd /repo && git log -1; head -3 README.md" \
  "no longer run with '/repo' as cwd"

# 2-segment commands (tier 1) emit allow+updatedInput — no permissionDecisionReason,
# so the deny-path cwd-binding note is never present (correct by construction).
two_seg_out=$(emit "cd /repo && git status" | bash "$HOOK" 2>/dev/null || true)
if command -v jq &>/dev/null; then
  two_seg_reason=$(printf '%s' "$two_seg_out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null || true)
else
  _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  two_seg_reason=$(printf '%s' "$two_seg_out" | "$_py" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecisionReason"])
except Exception: pass' 2>/dev/null || true)
fi
if printf '%s' "$two_seg_reason" | grep -qF "no longer run with"; then
  FAIL=$((FAIL + 1)); echo "FAIL: 2-segment command (tier 1) should NOT carry cwd-binding note in deny reason"
else
  PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# Non-Bash tool is ignored.
# ---------------------------------------------------------------------------
non_bash=$(printf '{"tool_name":"Write","tool_input":{"command":"cd /repo && git status"}}' | bash "$HOOK" 2>/dev/null || true)
if [[ -z "$non_bash" ]]; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1)); echo "FAIL: non-Bash tool should be ignored (got output)"
fi

# ---------------------------------------------------------------------------
# v4 (2026-07-02): tail-truncation safety guard.
# A 3+ segment newline-separated command with a multi-line commit message causes
# the awk tail parser to yield an empty FOLLOWERS: the TAIL from awk starts with a
# bare newline (the newline that separated `git add -- a` from `git commit ...`),
# and `read` consumes that newline as the end-of-line, leaving _val="" for TAIL.
# The actual follower content (git commit, git rev-parse) never lands in FOLLOWERS.
# Pre-fix (v3 and earlier), SEG_COUNT was not tracked so this hit Tier 1 and
# auto-rewrote to just `git -C <target> add -- a`, silently dropping the commit
# and rev-parse. Post-fix the safety guard (SEG_COUNT >= 3 + FOLLOWERS empty)
# returns allow-unchanged (empty output, no updatedInput).
# ---------------------------------------------------------------------------
TAIL_TRUNC_TARGET="$TIER2_DIR"
# Note: the multi-line commit message is the variable that triggers the bug.
# The newline after `git add -- a` means awk's TAIL starts with \n, which `read`
# consumes as an empty line, losing the git commit and git rev-parse followers.
TAIL_TRUNC_CMD="cd ${TAIL_TRUNC_TARGET}
git add -- a
git commit -m \"line1
line2
line3\"
git rev-parse HEAD"
# The pre-fix bad rewrite: only the git-add, tail silently dropped.
TAIL_TRUNC_BAD_CMD="git -C ${TAIL_TRUNC_TARGET} add -- a"
tail_trunc_out=$(emit_with_cwd "$TAIL_TRUNC_CMD" "$TAIL_TRUNC_TARGET" | bash "$HOOK" 2>/dev/null || true)
if command -v jq >/dev/null 2>&1; then
  tail_trunc_got=$(printf '%s' "$tail_trunc_out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
else
  _py_tt=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  tail_trunc_got=$(printf '%s' "$tail_trunc_out" | "$_py_tt" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["updatedInput"]["command"])
except Exception: pass' 2>/dev/null || true)
fi
if [[ "$tail_trunc_got" == "$TAIL_TRUNC_BAD_CMD" ]]; then
  FAIL=$((FAIL + 1))
  echo "FAIL: 3+ segment newline-separated command with multi-line commit msg must NOT truncate to git-add-only (tail-truncation bug fixed in v4)"
  echo "      got updatedInput.command: $tail_trunc_got"
else
  PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# v5 (2026-07-02): multi-line bail guard.
# T1 and T2 auto-rewrites must never emit a corrupted updatedInput.command when
# the original command contains literal newlines or backslash-newline continuations.
# T1 multi-line: falls through to deny+offer (correct suggestion, avoids stall).
# T2 multi-line: allow-unchanged (cd X is a no-op; no corrupted rewrite emitted).
# Single-line commands are unaffected.
# ---------------------------------------------------------------------------

# Test 1: literal newline inside a quoted commit message.
# The unbalanced-quote guard (SEG1 mis-split at the bare newline) fires first;
# the v5 multi-line bail is belt-and-braces. Either way: no updatedInput.command.
MULTILINE_MSG_CMD="cd /x && git commit -m \"first
second\""
multiline_msg_out=$(emit "$MULTILINE_MSG_CMD" | bash "$HOOK" 2>/dev/null || true)
if command -v jq >/dev/null 2>&1; then
  multiline_msg_cmd_got=$(printf '%s' "$multiline_msg_out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
else
  _py_mm=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  multiline_msg_cmd_got=$(printf '%s' "$multiline_msg_out" | "$_py_mm" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["updatedInput"]["command"])
except Exception: pass' 2>/dev/null || true)
fi
if [[ -z "$multiline_msg_cmd_got" ]]; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: v5 test 1 — multi-line commit msg must NOT emit an updatedInput.command (got: $multiline_msg_cmd_got)"
fi

# Test 2: backslash-newline continuation in git args, T2 path (cwd==/x, redundant cd).
# Without the fix: T2 fires and emits a corrupted `git add -- ; path1 ; path2` (the
# \<NL>→; normalization turned arg-level continuations into spurious segment separators).
# With the fix:   T2 multi-line bail → allow-unchanged → no updatedInput.command.
BACKSLASH_NL_CMD="$(printf 'cd /x && git add -- \\\n  path1 \\\n  path2')"
backslash_nl_out=$(emit_with_cwd "$BACKSLASH_NL_CMD" "/x" | bash "$HOOK" 2>/dev/null || true)
if command -v jq >/dev/null 2>&1; then
  backslash_nl_cmd_got=$(printf '%s' "$backslash_nl_out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
else
  _py_bn=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  backslash_nl_cmd_got=$(printf '%s' "$backslash_nl_out" | "$_py_bn" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["updatedInput"]["command"])
except Exception: pass' 2>/dev/null || true)
fi
if [[ -z "$backslash_nl_cmd_got" ]]; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: v5 test 2 — backslash-newline in git args (T2 path) must NOT emit a corrupted updatedInput.command (got: $backslash_nl_cmd_got)"
fi

# Test 3: regression guard — single-line `cd X && git status` STILL auto-rewrites (T1).
# The v5 bail fires only on commands that contain a literal newline; a pure-single-line
# command must not be affected.
assert_rewrite "v5 test 3 (regression): single-line T1 still auto-rewrites (multi-line bail must not fire)" \
  "cd /x && git status" \
  "git -C /x status"

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "offer-git-c-over-cd: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
