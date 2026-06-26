#!/usr/bin/env bash
# PreToolUse(Bash) hook: redirects a `cd <path> && git ...` prefix to the
# prompt-free `git -C <path> ...` equivalent — an OFFER, not a guard.
#
# Motivation: the tool-output-flakiness protocol distinguishes three shapes of
# output-that-came-back-wrong (empty / scrambled / fabricated) from a FOURTH,
# different failure: a command that never returns — stuck at `Waiting...`. A
# leading `cd` turns a Bash call into a compound command, which trips a
# permission prompt that renders as a non-returning `Waiting...`. Misreading that
# stall as a flaky channel drove a recurring probe-spray loop on 2026-05-30
# (echo ALIVE / printf CHAN_OK / variant git log), broken only by PM interrupt.
# Full mechanism + the "blocked != flaky" discrimination:
#   docs/wiki/tool-output-flakiness-protocol.md
#     § Not this protocol — blocked / no-return (`Waiting...`) is a different failure
#
# This hook closes the trigger at the boundary, where the diagnosis record says
# the fix must live: doctrine alone cannot bind the model mid-spray, but a
# boundary redirect holds regardless of what the model remembers. Unlike the
# block-destructive-* guards (which DENY irreversible loss), this is a low-stakes
# REDIRECT — `git -C <path>` is an exact, prompt-free equivalent of
# `cd <path> && git ...`, so the redirect is always actionable and the
# false-positive cost is ~zero. It LEADS WITH the better command (design-as-offers:
# block WITH an alternative is a redirect, not a nag).
#
# Trigger scope (deliberately narrow, to stay an offer not a nag):
#   - FIRST command segment is `cd <path>` AND the SECOND segment is a `git`
#     invocation. This is the exact stall shape and the one case where the
#     `git -C` rewrite is trivially clean. `cd X && npm i && git status` (second
#     segment is not git) is left alone — its redirect is not clean.
#   - PowerShell is a separate tool with no matcher here (it already uses
#     `git -C` by idiom in the transcript that motivated this).
#
# v2 (2026-06-11): preserves the FULL chain in the suggestion when the user typed
# more than two segments (`cd X && git Y ; head Z`), and adds a one-line cwd-binding
# note flagging that followers no longer share the cd target's working directory.
# v1 silently truncated the suggestion at the end of the git segment, which left the
# agent reconstructing the rest by hand and disguised what the redirect actually was
# doing. The full-chain rewrite uses a quote-aware awk scan to locate the first
# unquoted operator after the git invocation — a `;` inside a git argument
# (`git log --format='%h;%s'`) is not mis-identified as the body/tail split point.
# Once the split point is fixed, followers are captured verbatim from that point
# onward (no re-parsing). The 2-segment case is unchanged from v1.
#
# KNOWN limitations:
#   - Only a LEADING cd is matched. `ls && cd X && git ...` (cd not first) is
#     allowed — the leading-cd form is the documented stall trigger.
#   - Does NOT detect the OTHER trigger named in the wiki — batched redundant
#     variant-probes across multiple tool calls in one message — because a
#     per-call PreToolUse hook cannot see sibling calls in the batch. That trigger
#     stays doctrine-only (wiki § Not this protocol, trigger 2).
#   - Subshell/variable cd targets ($(...) / $VAR) are rewritten verbatim into the
#     suggestion; the redirect still holds (git -C accepts the same token).
#   - A `&&`/`;` inside a quoted argument in seg0/seg1 (`git commit -m "a && b"`)
#     would mis-split; the unbalanced-quote guard below detects this and bails
#     (allow) rather than emit a truncated suggestion. The awk quote-awareness in
#     loop 2 is defense-in-depth — the bash guard catches these inputs first in
#     practice, but awk would still locate the correct body/tail split if the
#     upstream guard were ever weakened.
#   - A cd target that starts with `-` (real dir named `-foo`, or a flag) is left
#     alone — `git -C -foo` is ambiguous; use `git -C ./-foo` manually.
#   - The cwd-binding note is generic: it names the cd target and tells the agent
#     to prefix relative paths with it, but does NOT auto-rewrite the followers
#     (semantic per-follower path-detection has too many false positives — flagging
#     is honest, silent mangling is not).
#
# Decision mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
# Override: export COORDINATOR_ALLOW_CD_PREFIX=1 in the environment (NOT an inline
# prefix — that sets the var for the cd child, not this hook process).

set -uo pipefail

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Parse tool_name + command (jq -> python -> sed/grep fallback) ---
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
  CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  CMD=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
fi

[[ "$TOOL_NAME" != "Bash" ]] && exit 0
[[ -z "$CMD" ]] && exit 0

# Join backslash-newline continuations as a ';' separator — an agent that emits
# multi-line 'cd X \<NL>git Y' clearly intended sequencing, even though strict shell
# would treat \<NL> as a no-separator line-join. Treating it as ';' lets the
# downstream split recognize the chain.
NL=$'\n'
CMD="${CMD//\\$NL/;}"

# Fast bail: nothing to do unless BOTH a `cd` and a `git` appear.
echo "$CMD" | grep -qE '\bcd\b' || exit 0
echo "$CMD" | grep -qE '\bgit\b' || exit 0

# Escape hatch (honored early).
[[ "${COORDINATOR_ALLOW_CD_PREFIX:-0}" == "1" ]] && exit 0

# --- Helpers ---
strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

trim() {
  local t="$1"
  t="${t#"${t%%[![:space:]]*}"}"   # ltrim
  t="${t%"${t##*[![:space:]]}"}"   # rtrim
  printf '%s' "$t"
}

offer() {
  local reason="$1"
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "$PY" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "$PY" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

# --- Read the first two non-empty command segments. Split ONLY on the sequencing
# operators that create the compound-command stall: `&&` and `;` (plus literal
# newlines already present). NOT `|`, `||`, or a single `&` — a pipe / alternation /
# background from `cd` is not the stall shape, and redirecting `cd /x || git status`
# to `git -C /x status` would silently change conditional execution to unconditional
# (review finding F2). ---
SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/&&/\n/g; s/;/\n/g')

SEG0=""; SEG1=""; n=0
while IFS= read -r line; do
  t=$(trim "$line")
  [[ -z "$t" ]] && continue
  n=$((n + 1))
  if [[ $n -eq 1 ]]; then SEG0="$t"; fi
  if [[ $n -eq 2 ]]; then SEG1="$t"; break; fi
done <<< "$SEGMENTS"

# Trigger: first segment's leading token is EXACTLY `cd` with a path arg, and the
# second segment is a `git` invocation. The exact-token check rules out any
# `cd`-prefixed alias/function (`cdup …`); the space-then-nonspace check requires a
# real argument.
[[ "${SEG0%%[[:space:]]*}" == "cd" ]] || exit 0
[[ "$SEG0" =~ ^cd[[:space:]]+[^[:space:]] ]] || exit 0
[[ "$SEG1" =~ ^git[[:space:]] ]] || exit 0

# A `&&`/`;` inside a quoted argument (e.g. `git commit -m "fix: a && b"`) is
# mis-split by the sed pass, truncating a segment. If either segment carries an
# unbalanced quote, the split broke a quoted string — bail rather than emit a
# malformed `git -C` suggestion (review finding, round 2).
for _seg in "$SEG0" "$SEG1"; do
  _dq="${_seg//[^\"]/}"; _sq="${_seg//[^\']/}"
  (( ${#_dq} % 2 == 1 )) && exit 0
  (( ${#_sq} % 2 == 1 )) && exit 0
done

# Extract the cd target (token after `cd`, quote-stripped) and the git remainder.
TARGET=$(trim "${SEG0#cd}")
TARGET=$(strip_q "$TARGET")

# cd flags / special forms (`-`, `-L`, `-P`, `--`) have no clean `git -C` rewrite —
# the suggestion `git -C - …` / `git -C -L …` would be malformed. Leave them alone
# (review findings F6/F12/F15).
[[ "$TARGET" == -* ]] && exit 0

# Quote the target in the suggestion if it contains whitespace.
case "$TARGET" in
  *[[:space:]]*) QT="\"$TARGET\"" ;;
  *) QT="$TARGET" ;;
esac

# Extract the original-spacing git body and the verbatim tail of CMD starting at the
# first unquoted `&&` / `;` / newline AFTER the leading `cd <path> <op> git <args>`.
# Both come from the original CMD (not from trimmed SEG1), so the suggestion
# preserves the agent's whitespace exactly — `cd X && git add -- a && git commit -m b`
# rewrites to `git -C X add -- a && git commit -m b` (space before the second `&&`)
# rather than the wart `git -C X add -- a&& git commit -m b` you get if you
# concatenate trim(SEG1) with the tail. Quote-aware so a `;` inside a follower's
# quoted argument (`echo 'a;b'`) isn't false-split. awk is BSD-portable; a failure
# here is caught downstream and we fall back to the v1 trim-based rewrite.
PARSED=$(printf '%s' "$CMD" | awk '
{ if (NR > 1) buf = buf "\n" $0; else buf = $0; }
END {
  n = length(buf); i = 1; in_sq = 0; in_dq = 0;
  while (i <= n && substr(buf, i, 1) ~ /[ \t]/) i++;
  i += 2;  # past leading "cd"
  found = 0;
  while (i <= n) {
    c = substr(buf, i, 1);
    if (in_sq) { if (c == "\047") in_sq = 0; i++; continue; }
    if (in_dq) {
      if (c == "\\" && i < n) { i += 2; continue; }
      if (c == "\"") in_dq = 0;
      i++; continue;
    }
    if (c == "\047") { in_sq = 1; i++; continue; }
    if (c == "\"") { in_dq = 1; i++; continue; }
    if (c == "&" && substr(buf, i+1, 1) == "&") { i += 2; found = 1; break; }
    if (c == ";" || c == "\n") { i++; found = 1; break; }
    i++;
  }
  if (!found) exit 0;
  while (i <= n && substr(buf, i, 1) ~ /[ \t]/) i++;
  if (substr(buf, i, 3) != "git") exit 0;
  seg1_start = i;
  i += 3;
  # Reset quote state between loops. In practice the bash unbalanced-quote guard
  # upstream ensures we reach awk only with balanced quotes in SEG0/SEG1, so loop 1
  # always exits with in_sq=in_dq=0. The reset is belt-and-braces against a future
  # weakening of that guard — without it, an unbalanced-quote loop-1 exit would
  # corrupt the loop-2 tail detection silently.
  in_sq = 0; in_dq = 0;
  tail_start = 0;
  while (i <= n) {
    c = substr(buf, i, 1);
    if (in_sq) { if (c == "\047") in_sq = 0; i++; continue; }
    if (in_dq) {
      if (c == "\\" && i < n) { i += 2; continue; }
      if (c == "\"") in_dq = 0;
      i++; continue;
    }
    if (c == "\047") { in_sq = 1; i++; continue; }
    if (c == "\"") { in_dq = 1; i++; continue; }
    if (c == "&" && substr(buf, i+1, 1) == "&") { tail_start = i; break; }
    if (c == ";" || c == "\n") { tail_start = i; break; }
    i++;
  }
  if (tail_start > 0) {
    body = substr(buf, seg1_start, tail_start - seg1_start);
    tail = substr(buf, tail_start);
  } else {
    body = substr(buf, seg1_start);
    tail = "";
  }
  # Tab-delimited. The bash reader uses `IFS=$'\t' read -r _key _val` which splits
  # on the FIRST tab only; embedded tabs in body or tail land in _val intact, so
  # the suggestion is correct regardless. Embedded tabs in shell commands are rare
  # in practice (paths, commit messages with literal tabs).
  print "BODY\t" body;
  print "TAIL\t" tail;
}' 2>/dev/null || true)

GIT_BODY=""
FOLLOWERS=""
while IFS=$'\t' read -r _key _val; do
  case "$_key" in
    BODY) GIT_BODY="$_val" ;;
    TAIL) FOLLOWERS="$_val" ;;
  esac
done <<< "$PARSED"

if [[ -n "$GIT_BODY" ]]; then
  # GIT_BODY starts with literal "git"; strip just those three chars, keep the
  # original leading whitespace of the args so concatenation reads correctly.
  GIT_ARGS="${GIT_BODY#git}"
  SUGGESTION="git -C ${QT}${GIT_ARGS}${FOLLOWERS}"
else
  # awk produced nothing (awk unavailable, parser hiccup, unexpected input shape) —
  # fall back to the v1 trim-based rewrite. Loses some whitespace fidelity and the
  # tail of any 3+ segment chain, but the redirect is still correct for the
  # 2-segment case and the agent gets a working suggestion. Not exercised by a
  # dedicated test: this is the literal v1 code path, every passing 2-segment
  # assertion in the test suite asserts the SAME logic from the awk-success branch,
  # so any regression here surfaces as a broad green-to-red sweep. The only
  # untested dimension is "does the trigger condition fire when awk is missing,"
  # which is platform-installer concern, not a hook-logic concern.
  GITREST=$(trim "${SEG1#git}")
  SUGGESTION="git -C $QT $GITREST"
fi

if [[ -n "$FOLLOWERS" ]]; then
  offer "Use 'git -C <path>' instead of a 'cd <path> && git ...' prefix.

A leading 'cd' makes this a compound command, which trips a permission prompt that renders as a non-returning 'Waiting...' — the stall that gets misread as a flaky channel and drives the probe-spray loop (docs/wiki/tool-output-flakiness-protocol.md § Not this protocol — blocked / no-return). 'git -C' is the exact, prompt-free equivalent. (This fires on the 'cd … && git' SHAPE — it does not check whether the cd is redundant, so you may see it even when your cwd is already the target dir; 'git -C' is still the equivalent there.)

Did you mean:
  ${SUGGESTION}

Note: the follower commands after the first ';' / '&&' / newline no longer run with '$TARGET' as cwd. If a follower references a relative path that was anchored at the cd target, prefix the path with '$TARGET/'. Or, if the original cwd-binding form is genuinely needed across the whole chain, export COORDINATOR_ALLOW_CD_PREFIX=1 (an inline prefix does NOT reach this hook)."
else
  offer "Use 'git -C <path>' instead of a 'cd <path> && git ...' prefix.

A leading 'cd' makes this a compound command, which trips a permission prompt that renders as a non-returning 'Waiting...' — the stall that gets misread as a flaky channel and drives the probe-spray loop (docs/wiki/tool-output-flakiness-protocol.md § Not this protocol — blocked / no-return). 'git -C' is the exact, prompt-free equivalent. (This fires on the 'cd … && git' SHAPE — it does not check whether the cd is redundant, so you may see it even when your cwd is already the target dir; 'git -C' is still the equivalent there.)

Did you mean:
  ${SUGGESTION}

If the cd-prefix is genuinely needed (a non-git command later in the chain depends on that working directory), export COORDINATOR_ALLOW_CD_PREFIX=1 in your environment first (an inline prefix does NOT reach this hook)."
fi
