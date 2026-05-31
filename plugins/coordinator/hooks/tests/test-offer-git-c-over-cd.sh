#!/usr/bin/env bash
# Test suite for offer-git-c-over-cd.sh
#
# Drives the hook with crafted Bash-tool JSON payloads and asserts allow vs deny
# (the "deny" here is the offer/redirect mechanism, not a destructive block).
# Also asserts the redirect message reconstructs a correct `git -C` suggestion.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/offer-git-c-over-cd.sh"
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

assert_suggestion() {
  # $1 = description, $2 = command, $3 = substring expected in the DECODED reason
  # Decode the JSON reason first: in the raw envelope, suggestion quotes are
  # backslash-escaped (\"), so a literal grep of the raw JSON would miss a quoted
  # path. Match against the decoded reason text the model actually sees.
  local desc="$1" cmd="$2" want="$3" out reason
  out=$(emit "$cmd" | bash "$HOOK" 2>/dev/null || true)
  if command -v jq &>/dev/null; then
    reason=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null || true)
  else
    local _py; _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    reason=$(printf '%s' "$out" | "$_py" -c 'import json,sys
try: print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecisionReason"])
except Exception: pass' 2>/dev/null || true)
  fi
  if printf '%s' "$reason" | grep -qF "$want"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (suggestion did not contain: $want)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
  fi
}

# ---------------------------------------------------------------------------
# DENY / REDIRECT — the cd-prefix-then-git stall shape.
# ---------------------------------------------------------------------------
run_case "cd then git (&&) redirected" deny "cd /c/Users/oduffy/.claude && git log --oneline -1"
run_case "cd then git (;) redirected" deny "cd /repo; git status --porcelain"
run_case "cd then git (newline) redirected" deny "cd /repo
git add -- file.txt"
run_case "cd then git with backslash-newline continuation redirected" deny "cd /repo \\
git commit -m x"
run_case "cd then git add then commit (3 segments, seg2 is git) redirected" deny "cd /repo && git add -- a && git commit -m b"

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
# Suggestion reconstruction.
# ---------------------------------------------------------------------------
assert_suggestion "suggestion rewrites to git -C <path>" \
  "cd /c/Users/oduffy/.claude && git log --oneline -1" \
  "git -C /c/Users/oduffy/.claude log --oneline -1"
assert_suggestion "suggestion quotes a spaced path" \
  "cd '/c/Program Files/repo' && git status" \
  'git -C "/c/Program Files/repo" status'
assert_suggestion "redirect names the override env var" \
  "cd /repo && git status" \
  "COORDINATOR_ALLOW_CD_PREFIX=1"
# A variable cd target is rewritten verbatim (git -C accepts the same token).
assert_suggestion "variable target rewritten verbatim" \
  "cd \$HOME && git status" \
  "git -C \$HOME status"
# Multi-git chain: only the first git command is rewritten (leading-cd-only design).
assert_suggestion "multi-git chain suggests only the first git" \
  "cd /repo && git add -- a && git commit -m b" \
  "git -C /repo add -- a"

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
echo "----------------------------------------"
echo "offer-git-c-over-cd: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
