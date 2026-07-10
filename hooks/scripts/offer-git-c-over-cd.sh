#!/usr/bin/env bash
# PreToolUse(Bash) hook: transparently auto-rewrites or offers the prompt-free
# `git -C <path> ...` equivalent for commands that lead with `cd <path> && git ...`.
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
# rewrite transparently when safe, offer with explanation when not).
#
# Trigger scope (deliberately narrow, to stay an offer not a nag):
#   - FIRST command segment is `cd <path>` AND the SECOND segment is a `git`
#     invocation. This is the exact stall shape and the one case where the
#     `git -C` rewrite is trivially clean. `cd X && npm i && git status` (second
#     segment is not git) is left alone — its redirect is not clean.
#   - PowerShell is a separate tool with no matcher here (it already uses
#     `git -C` by idiom in the transcript that motivated this).
#
# v5 (2026-07-02): multi-line bail guard. Before any T1 or T2 auto-rewrite, detect
#   whether the ORIGINAL command (post-CRLF-strip, pre-\<NL>→; normalization) contains
#   a literal newline (which subsumes backslash-newline continuations since those
#   contain a newline char). If yes: T1 falls through to deny+offer (correct suggestion,
#   no stall); T2 allows unchanged (cd X is a no-op since X==cwd; no corruption risk).
#   Prevents corrupted rewrites where arg-level \<NL> continuations (e.g. `git add --
#   \<NL> path1`) are mis-parsed as segment separators after normalization, causing the
#   paths to run as shell commands instead of git arguments.
#   Single-line commands (no literal newlines in ORIGINAL_CMD) are unaffected.
# v4 (2026-07-02): tail-truncation safety guard. A 3+ segment command where the awk
#   tail parser yields an empty FOLLOWERS (e.g. newline-as-separator causes the TAIL
#   awk output to start with a bare newline that `read` consumes as an empty line, losing
#   the actual followers) now returns allow-unchanged instead of rewriting and silently
#   dropping the tail. True 2-segment commands (SEG_COUNT == 2) are unaffected.
# v3 (2026-07-02): three-tier auto-rewrite that eliminates friction for the safe cases.
#   Tier 1 — clean 2-segment `cd X && git Y` (no followers): TRANSPARENT AUTO-REWRITE
#     to `git -C X Y` via updatedInput. Safe regardless of cwd — git -C is an exact
#     equivalent; the model never sees a deny.
#   Tier 2 — redundant cd with followers (X resolves to same realpath as cwd, 3+ segs):
#     TRANSPARENT AUTO-REWRITE by stripping the leading `cd X &&/;` — followers still
#     run in cwd (== X), so semantics are preserved. Fail-open: if cwd is absent or
#     the path comparison fails, falls through to tier 3.
#   Tier 3 — non-redundant cd WITH cwd-dependent followers (X != cwd, 3+ segs):
#     KEEP the existing deny+offer unchanged — the cwd-binding note is load-bearing;
#     a transparent rewrite could break a follower that depends on being in X.
#   Bail-outs (unbalanced quotes, cd flags, non-git second segment, ||/|/&) are
#     unchanged from v2 — they allow without rewrite or offer.
#
# v2 (2026-06-11): preserves the FULL chain in the suggestion when the user typed
# more than two segments (`cd X && git Y ; head Z`), and adds a one-line cwd-binding
# note flagging that followers no longer share the cd target's working directory.
# v1 silently truncated the suggestion at the end of the git segment.
#
# KNOWN limitations:
#   - Only a LEADING cd is matched. `ls && cd X && git ...` (cd not first) is
#     allowed — the leading-cd form is the documented stall trigger.
#   - Does NOT detect the OTHER trigger named in the wiki — batched redundant
#     variant-probes across multiple tool calls in one message — because a
#     per-call PreToolUse hook cannot see sibling calls in the batch. That trigger
#     stays doctrine-only (wiki § Not this protocol, trigger 2).
#   - Subshell/variable cd targets ($(...) / $VAR) are rewritten verbatim into the
#     tier-1 rewrite; the redirect still holds (git -C accepts the same token).
#     Tier-2 (redundant-cd) path comparison is skipped for $VAR/$(...) targets
#     because realpath cannot resolve them — falls to tier 3 (deny+offer), which
#     is safe (fail-open).
#   - A `&&`/`;` inside a quoted argument in seg0/seg1 (`git commit -m "a && b"`)
#     would mis-split; the unbalanced-quote guard below detects this and bails
#     (allow) rather than emit a truncated rewrite. The awk quote-awareness in
#     loop 2 is defense-in-depth — the bash guard catches these inputs first in
#     practice, but awk would still locate the correct body/tail split if the
#     upstream guard were ever weakened.
#   - A cd target that starts with `-` (real dir named `-foo`, or a flag) is left
#     alone — `git -C -foo` is ambiguous; use `git -C ./-foo` manually.
#   - The tier-3 cwd-binding note is generic: it names the cd target and tells the
#     agent to prefix relative paths with it, but does NOT auto-rewrite the followers
#     (semantic per-follower path-detection has too many false positives — flagging
#     is honest, silent mangling is not).
#   - Tier-2 path comparison uses realpath when available. When realpath is absent,
#     falls back to a trailing-slash strip; this may miss symlink indirection, but
#     the worst case is a false-negative (falls to tier 3, deny+offer) — not a
#     false-positive (incorrect silent rewrite). Fail-open is the invariant.
#   - A 3+ segment command where the awk tail parser yields an empty FOLLOWERS (the
#     newline-as-separator shape causes the TAIL value to start with a bare newline
#     that `read` consumes as an empty line, losing the actual follower content) is
#     returned allow-unchanged by a safety guard (SEG_COUNT >= 3 + FOLLOWERS empty).
#     Pre-fix (2026-07-02), this hit Tier 1 and silently dropped every segment after
#     the git body — a staged-but-never-committed live failure. True 2-segment commands
#     (SEG_COUNT == 2, FOLLOWERS empty) are unaffected; Tier-1 still fires for them.
#
# Decision mechanism:
#   Tier 1/2 (auto-rewrite): emit allow + updatedInput.command to STDOUT, exit 0.
#     Optional additionalContext carries a light one-line note (not a nag).
#   Tier 3 (deny+offer, Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
#   Allow (no trigger): exit 0, no stdout.
# Override: export COORDINATOR_ALLOW_CD_PREFIX=1 in the environment (NOT an inline
# prefix — that sets the var for the cd child, not this hook process).
#
# Sourceable — defines check_offer_git_c() for use by dispatcher scripts.
# Spec: hooks/scripts/offer-git-c-over-cd.sh (sourceable refactor, 2026-06-30)

set -uo pipefail

# ---------------------------------------------------------------------------
# Helper functions — _offer_-prefixed to avoid file-scope name collisions
# when this script is sourced by a dispatcher.
# ---------------------------------------------------------------------------

_offer_strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

_offer_trim() {
  local t="$1"
  t="${t#"${t%%[![:space:]]*}"}"   # ltrim
  t="${t%"${t##*[![:space:]]}"}"   # rtrim
  printf '%s' "$t"
}

# _offer_offer: print the deny envelope to STDOUT, then return.
# On a trigger the caller is responsible for returning/exiting afterward.
# Never calls exit — safe to use when sourced.
_offer_offer() {
  local reason="$1"
  local _py
  _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "$_py" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "$_py" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  return 0
}

# _offer_allow_rewrite: emit the allow+updatedInput envelope to STDOUT.
# $1 = new command string; $2 = optional additionalContext (one-line note; omit to skip).
# Same jq→python→bash-fallback pattern as _offer_offer. Never calls exit.
_offer_allow_rewrite() {
  local new_cmd="$1" ctx="${2:-}"
  local _py
  _py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if command -v jq >/dev/null 2>&1; then
    if [[ -n "$ctx" ]]; then
      jq -nc --arg cmd "$new_cmd" --arg ctx "$ctx" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$cmd},additionalContext:$ctx}}'
    else
      jq -nc --arg cmd "$new_cmd" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$cmd}}}'
    fi
  elif [[ -n "$_py" ]]; then
    local cmd_j ctx_j
    cmd_j=$(printf '%s' "$new_cmd" | "$_py" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || cmd_j="\"$(printf '%s' "$new_cmd" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    if [[ -n "$ctx" ]]; then
      ctx_j=$(printf '%s' "$ctx" | "$_py" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
        || ctx_j="\"$(printf '%s' "$ctx" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":%s},"additionalContext":%s}}\n' "$cmd_j" "$ctx_j"
    else
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":%s}}}\n' "$cmd_j"
    fi
  else
    local esc_cmd="${new_cmd//\\/\\\\}"; esc_cmd="${esc_cmd//\"/\\\"}"; esc_cmd="${esc_cmd//$'\n'/\\n}"
    if [[ -n "$ctx" ]]; then
      local esc_ctx="${ctx//\\/\\\\}"; esc_ctx="${esc_ctx//\"/\\\"}"; esc_ctx="${esc_ctx//$'\n'/\\n}"
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"%s"},"additionalContext":"%s"}}\n' "$esc_cmd" "$esc_ctx"
    else
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"%s"}}}\n' "$esc_cmd"
    fi
  fi
  return 0
}

# _offer_normalize_path: return a canonical path for comparison.
# Expands leading ~, normalises Windows drive-letter form (C:/foo → /c/foo so the
# harness-injected .cwd and the shell's pwd agree), resolves via realpath when
# available, strips trailing slash as a fallback. Fails-open: an unresolvable path
# returns the input with trailing slash stripped — callers treat an empty result as
# "unable to compare".
_offer_normalize_path() {
  local p="$1"
  [[ -z "$p" ]] && return 0
  # Expand leading ~ (bash parameter expansion; safe, no eval).
  p="${p/#\~/$HOME}"
  # Normalise Windows drive-letter paths: C:/foo or C:\foo → /c/foo.
  # The harness-injected .cwd arrives as C:/... while bash pwd gives /c/...;
  # converting both to the lowercase-drive POSIX form makes the comparison stable
  # on Git-Bash/Windows. ${v,} lowercases one char (bash 4+). Non-Windows paths
  # are unchanged (the regex simply won't match).
  if [[ "$p" =~ ^([A-Za-z]):[/\\](.*) ]]; then
    # Review: code-reviewer — F2: ${BASH_REMATCH[1],} (lowercase first char) is bash-4-only
    # and unguarded in this standalone script. Replace with portable tr invocation.
    local _drive
    _drive=$(printf '%s' "${BASH_REMATCH[1]}" | tr 'A-Z' 'a-z')
    local _rest="${BASH_REMATCH[2]//\\//}"   # backslash → forward slash
    p="/${_drive}/${_rest}"
  fi
  if command -v realpath >/dev/null 2>&1; then
    realpath "$p" 2>/dev/null || printf '%s' "${p%/}"
  else
    # Best-effort without realpath: strip trailing slash so /repo/ == /repo.
    p="${p%/}"
    [[ -z "$p" ]] && p="/"
    printf '%s' "$p"
  fi
}

# ---------------------------------------------------------------------------
# check_offer_git_c <command> <session_id> [cwd]
#
# All decision logic for the cd-prefix offer/rewrite. Emits the allow+rewrite
# envelope (tiers 1-2) or the deny envelope (tier 3) to STDOUT when the
# trigger fires; prints nothing and returns 0 otherwise.
# Does NOT read stdin — the caller supplies parsed values as positional args.
# Safe to source: no top-level execution, no exit calls.
# ---------------------------------------------------------------------------
check_offer_git_c() {
  local CMD="$1"
  # $2 = session_id — reserved for dispatcher contract; not used by current logic.
  local CWD="${3:-}"   # optional; absent → fail-open on tier-2 redundant-cd check

  [[ -z "$CMD" ]] && return 0

  # Normalize CRLF -> LF first. On Windows/Git-Bash the native jq.exe emits its
  # output in text mode, injecting a CR before every LF, so a multi-line
  # `cd X \<CR><LF> git ...` reaches this function with a CR the join below would
  # otherwise miss. A bare CR is never a meaningful shell token, so stripping
  # every CR is safe. (Matches the CR-strip in block-destructive-git-orphan.sh.)
  CMD="${CMD//$'\r'/}"

  # v5: capture original command BEFORE continuation-normalize so the multi-line bail
  # can test the TRUE input, not the normalized form. Post-CRLF-strip is correct:
  # CRs are display artefacts; newlines and backslash-newlines are semantic.
  local ORIGINAL_CMD="$CMD"

  # Join backslash-newline continuations as a ';' separator — an agent that emits
  # multi-line 'cd X \<NL>git Y' clearly intended sequencing, even though strict shell
  # would treat \<NL> as a no-separator line-join. Treating it as ';' lets the
  # downstream split recognize the chain.
  local NL=$'\n'
  CMD="${CMD//\\$NL/;}"  # ';' not space: downstream sed splits on ';' so a cd…;git… chain forms two addressable segments

  # Fast bail: nothing to do unless BOTH a `cd` and a `git` appear.
  echo "$CMD" | grep -qE '\bcd\b' || return 0
  echo "$CMD" | grep -qE '\bgit\b' || return 0

  # Escape hatch (honored early).
  [[ "${COORDINATOR_ALLOW_CD_PREFIX:-0}" == "1" ]] && return 0

  # --- Read the first two non-empty command segments. Split ONLY on the sequencing
  # operators that create the compound-command stall: `&&` and `;` (plus literal
  # newlines already present). NOT `|`, `||`, or a single `&` — a pipe / alternation /
  # background from `cd` is not the stall shape, and redirecting `cd /x || git status`
  # to `git -C /x status` would silently change conditional execution to unconditional
  # (review finding F2). ---
  local SEGMENTS
  SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/&&/\n/g; s/;/\n/g')

  # Count non-empty segments for the tail-truncation safety guard (v4).
  # A segment is non-empty if it contains at least one non-space character.
  # Computed before reading SEG0/SEG1 so it covers the full split without
  # needing to change the existing read loop or its early `break`.
  local SEG_COUNT
  SEG_COUNT=$(printf '%s\n' "$SEGMENTS" | grep -c '[^[:space:]]' || true)

  local SEG0="" SEG1="" n=0 t
  while IFS= read -r line; do
    t=$(_offer_trim "$line")
    [[ -z "$t" ]] && continue
    n=$((n + 1))
    if [[ $n -eq 1 ]]; then SEG0="$t"; fi
    if [[ $n -eq 2 ]]; then SEG1="$t"; break; fi
  done <<< "$SEGMENTS"

  # Trigger: first segment's leading token is EXACTLY `cd` with a path arg, and the
  # second segment is a `git` invocation. The exact-token check rules out any
  # `cd`-prefixed alias/function (`cdup …`); the space-then-nonspace check requires a
  # real argument.
  [[ "${SEG0%%[[:space:]]*}" == "cd" ]] || return 0
  [[ "$SEG0" =~ ^cd[[:space:]]+[^[:space:]] ]] || return 0
  [[ "$SEG1" =~ ^git[[:space:]] ]] || return 0

  # A `&&`/`;` inside a quoted argument (e.g. `git commit -m "fix: a && b"`) is
  # mis-split by the sed pass, truncating a segment. If either segment carries an
  # unbalanced quote, the split broke a quoted string — bail rather than emit a
  # malformed `git -C` suggestion (review finding, round 2).
  local _seg _dq _sq
  for _seg in "$SEG0" "$SEG1"; do
    _dq="${_seg//[^\"]/}"; _sq="${_seg//[^\']/}"
    (( ${#_dq} % 2 == 1 )) && return 0
    (( ${#_sq} % 2 == 1 )) && return 0
  done

  # Extract the cd target (token after `cd`, quote-stripped) and the git remainder.
  local TARGET
  TARGET=$(_offer_trim "${SEG0#cd}")
  TARGET=$(_offer_strip_q "$TARGET")

  # cd flags / special forms (`-`, `-L`, `-P`, `--`) have no clean `git -C` rewrite —
  # the suggestion `git -C - …` / `git -C -L …` would be malformed. Leave them alone
  # (review findings F6/F12/F15).
  [[ "$TARGET" == -* ]] && return 0

  # Quote the target in the suggestion if it contains whitespace.
  local QT
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
  local PARSED
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

  local GIT_BODY="" FOLLOWERS="" _key _val
  while IFS=$'\t' read -r _key _val; do
    case "$_key" in
      BODY) GIT_BODY="$_val" ;;
      TAIL) FOLLOWERS="$_val" ;;
    esac
  done <<< "$PARSED"

  local SUGGESTION GIT_ARGS GITREST
  if [[ -n "$GIT_BODY" ]]; then
    # GIT_BODY starts with literal "git"; strip just those three chars, keep the
    # original leading whitespace of the args so concatenation reads correctly.
    GIT_ARGS="${GIT_BODY#git}"
    SUGGESTION="git -C ${QT}${GIT_ARGS}${FOLLOWERS}"
  else
    # awk produced nothing (awk unavailable, parser hiccup, unexpected input shape) —
    # fall back to the v1 trim-based rewrite. Loses some whitespace fidelity and the
    # tail of any 3+ segment chain, but the redirect is still correct for the
    # 2-segment case and the agent gets a working suggestion. For 3+ segment commands
    # where the tail is unrecoverable (FOLLOWERS empty, SEG_COUNT >= 3), the safety
    # guard below intercepts before Tier 1 and returns allow-unchanged — no rewrite,
    # no truncation. Not exercised by a dedicated test: this is the literal v1 code
    # path, every passing 2-segment assertion in the test suite asserts the SAME logic
    # from the awk-success branch, so any regression here surfaces as a broad
    # green-to-red sweep. The only untested dimension is "does the trigger condition
    # fire when awk is missing," which is a platform-installer concern, not a
    # hook-logic concern.
    GITREST=$(_offer_trim "${SEG1#git}")
    SUGGESTION="git -C $QT $GITREST"
  fi

  # Safety: 3+ segments but the parser extracted no followers → the tail is
  # unaccounted for. Auto-rewriting here would silently drop it (the 2026-07-02
  # tail-truncation bug: a `cd X && git add … && git commit …` chain ran only the
  # git-add). Run the original command unchanged rather than rewrite-and-truncate.
  # A true 2-segment command (SEG_COUNT == 2, FOLLOWERS empty) is unaffected —
  # Tier-1 still fires and still rewrites it cleanly.
  if [[ "$SEG_COUNT" -ge 3 && -z "$FOLLOWERS" ]]; then
    return 0
  fi

  # v5: multi-line bail. If the ORIGINAL command (pre-normalization) contains a
  # literal newline — which subsumes backslash-newline continuations since those
  # characters always contain \n — the \<NL>→; normalization may have mis-parsed
  # arg-level continuations (e.g. `git add -- \<NL> p1`) as segment separators,
  # producing a corrupted SUGGESTION or STRIPPED_CMD.
  # T1 bail: fall through to deny+offer below (correct suggestion text, avoids stall).
  # T2 bail: allow-unchanged (cd X is a no-op since X==cwd; no corruption risk).
  # Single-line commands (_ML_BAIL==0) are unaffected — T1/T2 still auto-rewrite.
  local _ML_BAIL=0
  [[ "$ORIGINAL_CMD" == *$'\n'* ]] && _ML_BAIL=1

  if [[ -z "$FOLLOWERS" ]]; then
    if [[ "$_ML_BAIL" -eq 0 ]]; then
      # Tier 1: clean 2-segment `cd X && git Y` — TRANSPARENT AUTO-REWRITE.
      # git -C X Y is an exact, prompt-free equivalent regardless of cwd; no
      # directory comparison needed. The stall never happens; the model never
      # sees friction. A light additionalContext notes the rewrite.
      _offer_allow_rewrite "$SUGGESTION" \
        "Auto-rewritten: 'cd ${TARGET} && git' → 'git -C ${TARGET}' (prompt-free). To bypass: export COORDINATOR_ALLOW_CD_PREFIX=1."
      return 0
    fi
    # Multi-line T1: fall through to deny+offer below (correct suggestion, avoids stall).
  fi

  # 3+ segments: cd is followed by more commands after the git invocation.
  # Check whether the cd is redundant (target == cwd → tier 2) or
  # load-bearing for the followers (target != cwd → tier 3).
  #
  # Tier 2 requires: (a) CWD is known, (b) awk produced GIT_BODY (so we can
  # build a clean stripped command), (c) NORM_TARGET and NORM_CWD are both
  # non-empty and equal. Any failure in (a)-(c) falls through to tier 3 —
  # the invariant is fail-OPEN, never a silent wrong rewrite.
  if [[ -n "$CWD" && -n "$GIT_BODY" ]]; then
    local NORM_TARGET NORM_CWD
    NORM_TARGET=$(_offer_normalize_path "$TARGET")
    NORM_CWD=$(_offer_normalize_path "$CWD")
    if [[ -n "$NORM_TARGET" && -n "$NORM_CWD" && "$NORM_TARGET" == "$NORM_CWD" ]]; then
      if [[ "$_ML_BAIL" -eq 1 ]]; then
        # Tier 2 multi-line bail: allow unchanged. cd X is a no-op (X==cwd) so the
        # original command runs correctly as-is; emitting a rewrite from the normalized
        # form would corrupt arg-level \<NL> continuations into spurious shell commands.
        return 0
      fi
      # Tier 2: cd is redundant — strip it. The git body + followers run in
      # cwd (== TARGET), so follower relative paths are unchanged.
      local STRIPPED_CMD="${GIT_BODY}${FOLLOWERS}"
      _offer_allow_rewrite "$STRIPPED_CMD" \
        "Auto-rewritten: leading 'cd ${TARGET}' stripped (cwd already matches target; followers unchanged). To bypass: export COORDINATOR_ALLOW_CD_PREFIX=1."
      return 0
    fi
  fi

  # Tier 3: non-redundant cd WITH cwd-dependent followers (or cwd unavailable).
  # The cwd-binding note is load-bearing — a transparent rewrite here could
  # silently break a follower that depends on being in TARGET. Keep deny+offer.
  _offer_offer "Use 'git -C <path>' instead of a 'cd <path> && git ...' prefix.

A leading 'cd' makes this a compound command, which trips a permission prompt that renders as a non-returning 'Waiting...' — the stall that gets misread as a flaky channel and drives the probe-spray loop (docs/wiki/tool-output-flakiness-protocol.md § Not this protocol — blocked / no-return). 'git -C' is the exact, prompt-free equivalent.

Did you mean:
  ${SUGGESTION}

Note: the follower commands after the first ';' / '&&' / newline no longer run with '$TARGET' as cwd. If a follower references a relative path that was anchored at the cd target, prefix the path with '$TARGET/'. Or, if the original cwd-binding form is genuinely needed across the whole chain, export COORDINATOR_ALLOW_CD_PREFIX=1 (an inline prefix does NOT reach this hook)."
  return 0
}

# ---------------------------------------------------------------------------
# Standalone entry point — reads stdin, parses hook JSON, dispatches.
# When sourced by a dispatcher: only the function definitions above load;
# no stdin is consumed and no code executes at source time.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  # --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
  if command -v timeout >/dev/null 2>&1; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
  fi

  # --- Parse tool_name + command (jq -> python -> sed/grep fallback) ---
  if command -v jq >/dev/null 2>&1; then
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

  # Parse session_id (passed as $2 per dispatcher contract; not used by current logic).
  if command -v jq >/dev/null 2>&1; then
    SID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  elif [[ -n "$PY" ]]; then
    SID=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("session_id","")))' 2>/dev/null || true)
  else
    SID=""
  fi

  # Parse cwd (top-level .cwd in the hook JSON — harness contract confirmed in
  # state/scratch/cd-guard-capability-findings.md § Q1; same pattern as
  # plan-persistence-check.sh lines 43+62-66). Used by check_offer_git_c() for
  # the tier-2 redundant-cd comparison. Absent or unresolvable → empty string →
  # check_offer_git_c() fails open to tier 3 (deny+offer).
  if command -v jq >/dev/null 2>&1; then
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
  elif [[ -n "$PY" ]]; then
    CWD=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("cwd","")))' 2>/dev/null || true)
  else
    CWD=""
  fi

  check_offer_git_c "$CMD" "$SID" "$CWD"
  exit 0
fi
