#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks `rm` of a directory/tree that holds work git
# CANNOT recover — uncommitted modifications, untracked files, or the .git store
# itself — unless the loss is proven safe or explicitly overridden.
#
# Motivation: sibling to block-destructive-git-orphan.sh. That hook closes the
# COMMITTED-work loss class (reset --hard / force-push / branch -D). This hook
# closes the UNCOMMITTED-work loss class — the other half of the 2026-05-28
# flakiness near-miss surface. When the tool-output channel hands the model an
# empty/garbled result, the model can confabulate a plausible-but-false premise
# ("this directory is a stale duplicate, safe to delete") and drive an
# `rm -rf <path>` against real in-progress work. `git checkout` / reflog recover
# committed and staged content; they CANNOT recover untracked files or
# unstaged modifications, and nothing recovers a deleted .git store. That is the
# only file loss git cannot undo, so it is exactly what this hook guards.
#
# Like the orphan guard, the enforcement is at the tool boundary: the decision is
# re-derived from FRESH `git status` against the real target, independent of
# anything the model believes, and applied BEFORE the model narrates the result —
# so it holds even when the return channel that triggered the confabulation is
# itself flaky. Diagnosis: docs/architecture/audit-records/2026-05-29-tool-output-flakiness-diagnosis.md
#
# Trigger scope (deliberately narrow, to stay an offer not a nag):
#   - Only `rm` with recursive intent (-r/-R/--recursive) OR a target that is an
#     existing directory. A single-file `rm scratch.txt` is low-blast-radius and
#     left alone — guarding it would make the hook noisy and invite stripping.
#   - `git rm` is SKIPPED — it stages a tracked-file removal that git recovers.
#     The skip tolerates git's global options between `git` and the `rm`
#     subcommand (`git -C <path> rm`, `git -c k=v rm`, `git --no-pager rm`, …) —
#     a bare `\bgit[[:space:]]+rm\b` would miss `git -C <path> rm` and then
#     mis-evaluate the `-C` path as a raw-rm target against the wrong repo.
#
# Disposability is defined by GIT, not a hand-maintained allowlist: targets whose
# content is fully committed (clean) pass; gitignored trees (node_modules, build,
# .venv, __pycache__, dist) never appear in `git status --porcelain` so they pass
# automatically; targets OUTSIDE any git repo pass (scratch lives there, and the
# work this setup cares about lives in repos). DENY fires only when real,
# unrecoverable, in-repo work would be lost.
#
# KNOWN v1 limitations:
#   - Literal path targets only. `rm -rf $VAR` / glob `rm -rf *` are not resolved
#     (allowed); `rm -rf $(...)`/backtick targets under a recursive flag fail SAFE
#     (deny) — same unverifiable-target stance as the orphan guard.
#   - Bash only. PowerShell `Remove-Item` is a separate tool with no matcher here
#     (flagged residual — see the diagnosis doc).
#   - Evaluates against the literal target path; a `cd <dir> && rm -rf sub` is
#     resolved relative to the hook cwd, not the cd target (same class as
#     block-destructive-git-orphan.sh v1). Relative targets ARE resolved to absolute for
#     the git-status check, so a cwd-is-subdirectory `rm -rf sub` is handled.
#   - Heredoc bodies are stripped before scanning so rm inside a literal heredoc
#     is not treated as a command verb (Part A). Multi-heredoc-on-one-line is a
#     v1 limitation; it fails safe (recoverable deny via COORDINATOR_ALLOW_RM).
#   - rm is matched only at COMMAND POSITION (Part B): quoted grep patterns,
#     glob tokens like *rm*, and other non-verb occurrences are not flagged.
#     Wrapped/grouped/quoted-verb forms ARE flagged: `(rm …)`, `{ rm …; }`,
#     `\rm`, `'rm'`, `! rm`, shell-invokers `bash -c 'rm …'` / `eval`, and the
#     execution-wrapper class `sudo`/`command`/`time`/`exec`/`nice`/`nohup`/`env`/
#     `ionice`/`timeout`/`stdbuf` plus verb-resolvers `which`/`type` — for these a
#     bare rm TOKEN after any flags denies (flag-agnostic). REMAINING residuals
#     (deliberately out of scope — adversarial, not confabulation-shaped): a
#     destructive rm with NO literal target (`xargs rm` / `find … -exec rm {} +`,
#     bounded by the no-target rule), an rm hidden behind a shell FUNCTION/alias
#     defined earlier in the same command, an execution wrapper NOT in the set
#     above, and a wrapper IN the set whose SECONDARY verb is a shell-invoker whose
#     quoted payload holds the rm (`env sh -c 'rm -rf x'` — the wrapper-token check
#     fires first and returns before the invoker broad-scan runs). These fail OPEN;
#     the hook guards the flakiness-confabulation case (model believes a dir is
#     stale → `rm -rf <dir>`), not a determined evader.
#   - Token extraction takes the text after the LAST rm verb match in a segment;
#     separator-splitting means this only bites a segment with two bare rm verbs
#     (rare; `git rm` is already handled by the git-rm skip).
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
# Override: export COORDINATOR_ALLOW_RM=1 in the environment (NOT an inline
# prefix — that sets the var for the rm child, not this hook process). Deny
# messages never print this incantation (design-as-offers, 2026-07-10 — see
# _rm_peer_claim_of below). For a target `git status --porcelain` reports as
# dirty (untracked files OR unstaged-modified tracked files) the override is
# concurrent-session-aware: it is REFUSED (un-overridable) when a LIVE peer
# coordinator session in this shared worktree has touched a path under or
# containing the target (see _rm_peer_claim_of). At the claim-dir/.git-store/
# subshell-unverifiable sites the override still bypasses as before — out of
# scope for the 2026-07-10 hardening.
#
# Sourceable interface (check_destructive_rm):
#   source block-destructive-rm.sh
#   check_destructive_rm "$cmd" "$session_id"
# When sourced, only the function and file-scope helpers are defined; no stdin
# is read and no logic executes. On DENY, the function prints the nested
# hookSpecificOutput JSON to stdout and returns. On allow, it prints nothing
# and returns 0.

set -uo pipefail

# ---------------------------------------------------------------------------
# File-scope constants and helpers — _rm_-prefixed to avoid name collisions
# when this file is sourced alongside sibling hooks (e.g.,
# block-destructive-git-orphan.sh defines its own OVERRIDE_HINT for
# COORDINATOR_ALLOW_ORPHAN; a bare OVERRIDE_HINT at file scope would collide
# and corrupt the deny message in whichever hook was sourced second).
# ---------------------------------------------------------------------------

_RM_CMD_RE='^[[:space:]]*((sudo|command|time|exec|nice|nohup)[[:space:]]+|env[[:space:]]+([^[:space:]]+=[^[:space:]]*[[:space:]]+)*|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(/[^[:space:]]*/)?rm([[:space:]]|$)'

_rm_strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

# Emit the deny JSON to stdout. Does NOT call exit — the caller must `return`
# immediately after this so check_destructive_rm returns to its caller.
# Uses _RM_PY (set by check_destructive_rm at entry; stored without `local` so
# this file-scope function can read it).
_rm_deny() {
  local reason="$1"
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "${_RM_PY:-}" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "${_RM_PY}" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
}

# Detect whether a single command SEGMENT invokes rm destructively. Returns 0 if so.
# Discriminates a real rm VERB (incl. wrapped/grouped/quoted-verb forms) from rm
# appearing as DATA (a quoted arg to a non-shell command, or a glob substring).
_rm_is_rm_segment() {
  local seg="$1" probe prev=""
  # Peel LEADING group/subshell/negation/backslash openers + whitespace, so a verb
  # wrapped as `(rm …)`, `{ rm …`, `$(rm …)`, `! rm`, or `\rm` is detected. Only the
  # LEADING `$(`/`(` is peeled — a `$(...)` appearing later (an rm TARGET, e.g.
  # `rm -rf $(echo x)`) is left intact for the unverifiable-subshell deny. Iterate;
  # openers nest (`( { rm …`).
  while [[ "$seg" != "$prev" ]]; do
    prev="$seg"
    seg="${seg#"${seg%%[![:space:]]*}"}"   # ltrim whitespace
    case "$seg" in
      '$('*) seg="${seg#'$('}" ;;
      '('*)  seg="${seg#'('}" ;;
      '{'*)  seg="${seg#'{'}" ;;
      '!'*)  seg="${seg#'!'}" ;;
      '`'*)  seg="${seg#'`'}" ;;
      \\*)   seg="${seg#\\}" ;;
    esac
  done
  # For command-WORD detection, strip quote chars so a quoted verb ('rm'/"rm") and a
  # shell-invoker payload (bash -c 'rm …') read as commands. Target extraction below
  # still uses the ORIGINAL $SEG, so quoted targets are unaffected.
  probe="${seg//\'/}"; probe="${probe//\"/}"
  # Shell-invoker broad fallback: bash/sh/zsh/dash -c, or eval — the payload EXECUTES,
  # so a broad rm scan of the payload is correct (and only fires for these invokers,
  # never for grep/ls/echo, preserving the quoted-arg false-positive fix).
  if printf '%s' "$probe" | grep -qE '^(bash|sh|zsh|dash)[[:space:]]+([^[:space:]]+[[:space:]]+)*-c([[:space:]]|$)|^eval([[:space:]]|$)'; then
    printf '%s' "$probe" | grep -qE '\brm\b' && return 0
  fi
  # Execution-wrapper / verb-resolver class: a wrapper RUNS another command, so an
  # unquoted `rm` (or `/path/rm`) TOKEN anywhere after the wrapper is a real rm —
  # even behind wrapper flags a position-anchored regex cannot track (`sudo -u root rm`,
  # `env -i rm`, `nice -n 10 rm`) or behind a verb-resolving subshell (`$(which rm) …`).
  # Whole-TOKEN match (boundaries: whitespace and ( ) { }) so a quoted `grep "rm"` arg
  # is NOT matched — the false-positive fix is preserved. Firstword read on the
  # quote-PRESERVED, opener-peeled seg. A bare `which rm`/`command -v rm` carries no
  # target downstream, so it still ALLOWs (non-destructive).
  local firstword="${seg%%[[:space:]]*}"
  case "$firstword" in
    sudo|command|time|exec|nice|nohup|env|ionice|timeout|stdbuf|which|type)
      printf '%s' "$seg" | grep -qE '(^|[[:space:]({`])(/[^[:space:]]*/)?rm([[:space:])}`]|$)' && return 0
      return 1 ;;
  esac
  printf '%s\n' "$probe" | grep -qE "$_RM_CMD_RE" && return 0
  return 1
}

# _rm_peer_claim_of <tgt_abs> <root>
#   2026-07-10 peer-contest hardening. Echoes the session id of a LIVE peer
#   coordinator session (not this process's own session) that has TOUCHED a
#   path equal to, under, or containing the target's repo-relative path, per
#   the shared-worktree touched.txt ledger (lib/coordinator-session.sh). Prints
#   nothing if no live peer contests the target — this is the CALLER's signal
#   that COORDINATOR_ALLOW_RM=1 may be honored for an untracked target.
#
#   Motivation: an rm of untracked/uncommitted work is git-unrecoverable, and
#   untracked files are byte-indistinguishable between the caller's own
#   in-progress scratch and a PEER session's in-progress, already-reviewed work
#   in the same shared worktree (2026-07-10 incident: an EM's blanket
#   COORDINATOR_ALLOW_RM=1 deleted a live peer's uncommitted work with no git
#   recovery path). This helper makes the override peer-aware for that one
#   branch; it does not change behavior at the claim-dir/.git-store/subshell
#   sites (those remain plain override-bypass, out of scope here).
#
#   Liveness: prefers the canonical cs_live_session_ids (lib/coordinator-
#   session.sh) when resolvable. Degrades to a 30-minute touched.txt mtime
#   heuristic when the lib/function is unavailable — a backstop, not the
#   source of truth. DR-148: no `find -newermt` (GNU-only); mtime compared via
#   _RM_PY epoch read, matching the rest of this file's portability posture.
#
#   Self-identity: cur_sid self-exclusion routes through cs_resolve_session_id
#   (NOT the raw .current-session-id sentinel) with a fail-safe don't-exclude
#   fallback when identity is unresolvable/ambiguous under concurrency
#   (Finding 2, 2026-07-10 review).
_rm_peer_claim_of() {
  local tgt_abs="$1" root="$2"
  local sess_dir="${root}/.git/coordinator-sessions"
  [[ -d "$sess_dir" ]] || return 0

  # Resolve self-identity via the canonical resolver, NOT the raw sentinel file
  # (Review: code-reviewer F2, 2026-07-10 — see header comment above this
  # function). The sentinel is last-writer-wins and under >=2 live sessions may
  # name a LIVE PEER, not the caller; cs_resolve_session_id's Tier-4 ambiguity
  # guard fails EMPTY in that case rather than trusting it. Sourcing the lib and
  # calling cs_live_session_ids/cs_resolve_session_id both run inside ONE
  # command-substitution subshell (Review: code-reviewer F3) so an inherited
  # hard `exit` from coordinator_trusted_root_guard --mode=fail-loud is
  # contained to the subshell — the caller (this PreToolUse hook) must never be
  # terminated mid-evaluation by a sourced dependency's failure path. On any
  # failure this degrades to empty cur_sid / empty live-set, which is the
  # intended fail-safe: an empty cur_sid means NO session dir is excluded as
  # "self" below (never silently skip a live peer's dir on unverified
  # identity), and an empty live-set degrades every sid to the mtime backstop.
  local cur_sid
  local -a _live_sids=()
  local _have_live=0
  local _resolve_out
  _resolve_out=$(
    if ! command -v cs_live_session_ids &>/dev/null || ! command -v cs_resolve_session_id &>/dev/null; then
      _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
      if [[ -n "$_cc_root" && -f "${_cc_root}/lib/coordinator-session.sh" ]]; then
        # shellcheck source=/dev/null
        source "${_cc_root}/lib/coordinator-session.sh" 2>/dev/null || true
      fi
    fi
    if command -v cs_resolve_session_id &>/dev/null; then
      printf 'CUR_SID:%s\n' "$(cs_resolve_session_id 2>/dev/null || true)"
    else
      printf 'CUR_SID:\n'
    fi
    if command -v cs_live_session_ids &>/dev/null; then
      printf 'HAVE_LIVE:1\n'
      cs_live_session_ids 2>/dev/null | sed 's/^/LIVE:/' || true
    else
      printf 'HAVE_LIVE:0\n'
    fi
  )
  while IFS= read -r _rline; do
    case "$_rline" in
      CUR_SID:*) cur_sid="${_rline#CUR_SID:}" ;;
      HAVE_LIVE:1) _have_live=1 ;;
      HAVE_LIVE:0) _have_live=0 ;;
      LIVE:*) [[ -n "${_rline#LIVE:}" ]] && _live_sids+=("${_rline#LIVE:}") ;;
    esac
  done <<< "$_resolve_out"

  local tgt_rel
  if [[ -n "${_RM_PY:-}" ]]; then
    tgt_rel=$("${_RM_PY}" -c 'import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]).replace(os.sep,"/"))' "$tgt_abs" "$root" 2>/dev/null || true)
  fi
  [[ -z "$tgt_rel" ]] && return 0

  local sid line now_epoch mtime_epoch _canon_covers _l _l_matched
  for sid in "$sess_dir"/*/; do
    [[ -d "$sid" ]] || continue
    sid="${sid%/}"; sid="$(basename "$sid")"
    # Fail-safe: only exclude a dir as "self" when cur_sid resolved to a
    # non-empty, verified value. An empty cur_sid (unresolvable/ambiguous
    # identity) must NEVER cause a dir to be skipped as self — a false
    # self-exclusion of a live peer is the exact catastrophic failure this
    # hardening exists to close; a false self-block (scanning our own dir
    # too) merely denies our own recoverable untracked work.
    [[ -n "$cur_sid" && "$sid" == "$cur_sid" ]] && continue
    [[ "$sid" == ".archive" || "$sid" == ".agents" ]] && continue

    # Canonical liveness covers this sid only if it has a meta.json (the
    # source cs_live_session_ids scans) — a sid with no meta.json is simply
    # OUTSIDE canonical's scan set, not "known dead", so treat it as
    # UNCOVERED and fall through to the mtime backstop rather than silently
    # skipping it (fail-safe: "not in the live list" and "not known to the
    # liveness scan at all" are different facts).
    # bash < 4.4 (stock macOS /bin/bash 3.2): "${arr[@]}" on an EMPTY array
    # under `set -u` is a fatal "unbound variable" — including a DECLARED-
    # empty array (`arr=()`, not just unset). This fires whenever
    # _live_sids is empty, e.g. zero live peer sessions, aborting the hook
    # mid-run with no deny JSON emitted -> a destructive rm on a peer-claimed
    # target is SILENTLY ALLOWED. ${arr[@]+"${arr[@]}"} is the bash-3.2-safe
    # idiom: expands to nothing when the array is empty/unset, else the
    # elements verbatim — identical behavior to "${arr[@]}" on bash >=4.4,
    # portable down to 3.2. Applied at every non-count array expansion in
    # this file.
    _canon_covers=0
    if [[ "$_have_live" -eq 1 && -f "${sess_dir}/${sid}/meta.json" ]]; then
      _canon_covers=1
      _l_matched=0
      for _l in ${_live_sids[@]+"${_live_sids[@]}"}; do
        [[ "$_l" == "$sid" ]] && _l_matched=1 && break
      done
      [[ "$_l_matched" -eq 1 ]] || continue   # canonical says dead -> not contested
    fi

    if [[ "$_canon_covers" -eq 0 ]]; then
      # Degradation backstop: treat live-enough-to-protect as touched.txt mtime
      # within the last 30 minutes.
      [[ -f "${sess_dir}/${sid}/touched.txt" ]] || continue
      if [[ -n "${_RM_PY:-}" ]]; then
        mtime_epoch=$("${_RM_PY}" -c 'import os,sys;print(int(os.path.getmtime(sys.argv[1])))' "${sess_dir}/${sid}/touched.txt" 2>/dev/null || true)
        now_epoch=$("${_RM_PY}" -c 'import time;print(int(time.time()))' 2>/dev/null || true)
        [[ -z "$mtime_epoch" || -z "$now_epoch" ]] && continue
        (( now_epoch - mtime_epoch > 1800 )) && continue
      else
        # No python available to compute mtime — fail SAFE: treat as contested
        # if this peer has ANY touched.txt entry covering the target, since we
        # cannot verify staleness. (Same fail-safe stance as the rest of the file.)
        :
      fi
    fi

    [[ -f "${sess_dir}/${sid}/touched.txt" ]] || continue
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Glob-safe literal prefix tests (Review: code-reviewer F1, 2026-07-10) —
      # a real case-statement `case "$x/" in "$y"/*)` interpolates $y into GLOB
      # PATTERN position, mis-matching paths containing */?/[]. Parameter-
      # expansion prefix-strip with a DOUBLE-QUOTED pattern operand ("$y"/) is
      # literal, not glob-interpreted, so this is safe for any repo-relative path.
      [[ "${line#"$tgt_rel"/}" != "$line" ]] && { echo "$sid"; return 0; }
      [[ "${tgt_rel#"$line"/}" != "$tgt_rel" ]] && { echo "$sid"; return 0; }
      [[ "$line" == "$tgt_rel" ]] && { echo "$sid"; return 0; }
    done < "${sess_dir}/${sid}/touched.txt"
  done

  return 0
}

# ---------------------------------------------------------------------------
# check_destructive_rm <command> <session_id>
#
# Contains ALL decision logic for the destructive-rm guard. Prints the nested
# hookSpecificOutput deny JSON to stdout when a covered destructive rm is
# detected; prints nothing and returns 0 on allow.
#
# $2 (session_id) is accepted for dispatcher interface compatibility but is
# not used by the current implementation — resolution is driven by target path
# and git status, not by session identity.
#
# Per-target repo resolution: computed PER TARGET via
#   git -C "$(dirname "$TGT_ABS")" rev-parse --show-toplevel  (~line 314 below)
# NOT from cwd. An `rm -rf <path>` target can live in a DIFFERENT repo than cwd;
# a single cwd-derived root would silently miss loss in a sibling repo. The
# scratch-scope check (~line 334 below) also uses this per-target resolution.
# The function is FULLY SELF-CONTAINED and performs these lookups internally
# exactly as the original standalone script did.
# ---------------------------------------------------------------------------
check_destructive_rm() {
  # $2 (session_id) accepted for interface compat; not used.

  # Resolve python interpreter; stored WITHOUT `local` so the file-scope
  # _rm_deny can read it. Idempotent on repeated calls.
  _RM_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  local CMD="$1"

  # Normalize CRLF -> LF first. On Windows/Git-Bash the native jq.exe emits its
  # output in text mode, injecting a CR before every LF, so a command carrying a
  # real newline reaches this function as `\<CR><LF>` (backslash CR LF), not
  # `\<LF>`. A bare CR is never a meaningful shell token, so stripping every CR is
  # safe and makes the whole function CRLF-robust — without it the join below (and
  # the sed/grep segmentation) silently miss any continuation on Windows, which
  # would DISABLE this guard for a multi-line `rm -rf <tree>` on that platform.
  # (Matches the CR-strip in block-destructive-git-orphan.sh — kept consistent.)
  CMD="${CMD//$'\r'/}"

  # Join backslash-newline continuations so a split op is one segment.
  local NL=$'\n'
  CMD="${CMD//\\$NL/ }"

  # Part A: Strip heredoc bodies — rm inside a heredoc literal is not executed
  # and must not be scanned. Handles <<WORD, <<'WORD', <<"WORD", <<-WORD (the
  # - form allows a tab-indented terminator). The awk script reads CMD line by
  # line: on a line containing a <<WORD introducer it switches to heredoc-body
  # mode and suppresses lines (including the closing terminator) until the word
  # is seen alone on a line (tabs stripped for <<-). Fail-safe: if mktemp or
  # awk is unavailable CMD is unchanged — may produce a recoverable false-deny.
  local _BDRM_AWK _BDRM_STRIPPED _BDRM_RC
  _BDRM_AWK=$(mktemp 2>/dev/null || true)
  if [[ -n "$_BDRM_AWK" ]]; then
    cat > "$_BDRM_AWK" << 'BDRM_AWK_EOF'
BEGIN { in_hd = 0; hd_word = ""; hd_strip = 0 }
!in_hd {
  line = $0
  if (match(line, /<<-?('[^']*'|"[^"]*"|[A-Za-z0-9_.+-]+)/)) {
    seg      = substr(line, RSTART, RLENGTH)
    hd_strip = (substr(seg, 3, 1) == "-") ? 1 : 0
    w        = substr(seg, hd_strip ? 4 : 3)
    c1       = substr(w, 1, 1)
    if (c1 == "'" || c1 == "\"") w = substr(w, 2, length(w) - 2)
    hd_word = w
    in_hd   = 1
  }
  print
  next
}
in_hd {
  check = $0
  if (hd_strip) { sub(/^\t+/, "", check) }
  if (check == hd_word) { in_hd = 0 }
  next
}
END { if (in_hd) exit 2 }
BDRM_AWK_EOF
    _BDRM_STRIPPED=$(printf '%s' "$CMD" | awk -f "$_BDRM_AWK"); _BDRM_RC=$?
    rm -f "$_BDRM_AWK"
    # Fail-safe: awk exits 2 if it ended INSIDE an unterminated heredoc (a mismatched
    # terminator word). DISCARD the strip and keep the original CMD — a stuck stripper
    # must never silently swallow a real trailing rm. Any non-zero awk exit fails safe.
    [[ "$_BDRM_RC" -eq 0 ]] && CMD="$_BDRM_STRIPPED"
  fi

  # Part B fast bail: nothing to do unless rm appears as a COMMAND VERB in some
  # segment. Checks rm at start of segment (post-separator-split), allowing
  # optional sudo/command/time prefixes, VAR=val assignment prefixes, and an
  # optional /path/to/ prefix. This prevents quoted grep patterns, glob tokens
  # like *rm*, and other non-verb rm occurrences from triggering processing.
  # Fast bail: post-heredoc-strip, bail unless `rm` appears at all (broad). Precise
  # command-verb discrimination (quoted-arg vs verb, glob substring, wrappers) happens
  # per-segment in the main loop via _rm_is_rm_segment — broad here is a cheap pre-filter.
  printf '%s' "$CMD" | grep -qE '\brm\b' || return 0

  # Escape hatch — captured, NOT honored early. 2026-07-10 hardening: a blanket
  # early-return here let the override bypass a LIVE peer's untracked/uncommitted
  # work in a shared worktree (byte-indistinguishable from the caller's own files,
  # git-unrecoverable if deleted). The flag is now threaded through per-site so the
  # untracked-work branch can consult _rm_peer_claim_of before honoring it, while
  # the three out-of-scope sites (subshell-unverifiable, claim-dir, .git-store)
  # keep their PRE-2026-07-10 override-bypass behavior via an explicit check at
  # each site.
  local _RM_OVERRIDE="${COORDINATOR_ALLOW_RM:-0}"

  # Resolve the current git repo root once. Used by the scratch allowlist to scope
  # the exemption to THIS repo only — so tasks/*-scratch in a sibling repo does
  # not accidentally inherit the exemption when referenced by absolute path.
  local CUR_REPO
  CUR_REPO=$(git rev-parse --show-toplevel 2>/dev/null || true)

  # --- Evaluate each command segment independently. Separators ; && || | & collapse
  # to newlines; erring toward MORE segments = more checks, never fewer. Group/subshell
  # wrappers ( ) { } $( are NOT split here (that would fragment a `$(...)` rm target) —
  # _rm_is_rm_segment peels a LEADING wrapper, and trailing ) } are stripped from targets. ---
  local SEGMENTS
  SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

  local SEG AFTER RECURSIVE TGT TGT_ABS STATUS DISP MORE
  local SCRATCH_BN SCRATCH_PAR_ABS SCRATCH_REPO ROOT _t tok
  local -a TARGETS

  while IFS= read -r SEG; do
    [[ -z "${SEG//[[:space:]]/}" ]] && continue
    # Must invoke rm as a command verb (Part B — wrapped/grouped/quoted-verb forms
    # and shell-invoker payloads all handled by _rm_is_rm_segment; rm-as-data is not).
    # Skip `git rm` (staged removal, git-recoverable), tolerating git global options
    # (-C <path>, -c <kv>, --git-dir, --work-tree, --no-pager, …) between `git` and
    # the rm subcommand. Defense-in-depth: the separator split above is the PRIMARY
    # isolation — `git log && rm -rf x` is already two segments. The git…rm skip is
    # the SECONDARY check within a single separator-free segment.
    _rm_is_rm_segment "$SEG" || continue
    echo "$SEG" | grep -qE '\bgit([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|--(git-dir|work-tree|namespace)(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)|--exec-path(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)?|-p|--paginate|--no-pager|--bare|--no-replace-objects|--literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs|--no-optional-locks))*[[:space:]]+rm\b' && continue

    # Tokens after the `rm` verb.
    # BSD sed's ERE lacks \b (GNU-only extension); use the [[:space:]]-boundary
    # idiom so this strips the verb identically on BSD and GNU. `\brm\b` was a
    # silent NO-OP on BSD sed (DR-148 audit, 2026-07-10).
    AFTER=$(echo "$SEG" | sed -E 's/.*(^|[[:space:]])rm([[:space:]]|$)/ /')

    # Recursive intent? (-r / -R / --recursive, bundled like -rf / -fr)
    RECURSIVE=0
    if echo "$AFTER" | grep -qE '(^|[[:space:]])-[a-zA-Z]*[rR][a-zA-Z]*([[:space:]]|$)|--recursive'; then
      RECURSIVE=1
    fi

    # Unverifiable target under recursive intent -> fail safe (deny), UNLESS
    # overridden — the override still bypasses this site (out of scope for the
    # 2026-07-10 peer-contest hardening; see check_destructive_rm header note
    # on _RM_OVERRIDE). When overridden, fall through: a subshell target is
    # never added to TARGETS below (documented v1 limitation), so nothing
    # downstream evaluates it — same net effect as the old blanket early-return.
    if [[ "$RECURSIVE" == "1" ]] && echo "$AFTER" | grep -qE '\$\(|`' && [[ "$_RM_OVERRIDE" != "1" ]]; then
      _rm_deny "BLOCKED: 'rm' with a recursive flag and a subshell-resolved target (\$(...) or backticks) cannot be verified safe — the hook will not run the subshell to learn what it would delete.

Resolve the target to a literal path first and re-check what lives there:
  git status --porcelain -- <resolved-path>   # uncommitted/untracked work that rm would destroy"
      return
    fi

    # Collect literal (non-flag) path tokens, quote-stripped. Tokens carrying an
    # unresolved var ($VAR), glob (*?[), or NON-recursive subshell are skipped as a
    # documented v1 limitation (the recursive-subshell case already failed safe
    # above; a non-recursive `rm $(...)` can only delete files, since `rm` refuses
    # a directory without -r, so its blast radius is bounded to single files).
    TARGETS=()
    # noglob: unquoted $AFTER undergoes word-splitting AND pathname expansion; without
    # `set -f` a glob token (e.g. *.log) would expand against the HOOK's cwd before the
    # *\** skip-case sees it, turning a glob into literal hook-cwd filenames (F12).
    set -f
    for tok in $AFTER; do
      case "$tok" in
        --) continue ;;
        -*) continue ;;
        *\$*|*\**|*\?*|*\[*) continue ;;
        *)
          # Strip quotes, then trailing group-closers ) } left by a wrapped verb such
          # as `(rm -rf dir)` — without this the target reads as `dir)` and never matches.
          _t="$(_rm_strip_q "$tok")"; _t="${_t%)}"; _t="${_t%\}}"
          TARGETS+=("$_t") ;;
      esac
    done
    set +f

    [[ "${#TARGETS[@]}" -eq 0 ]] && continue
    for TGT in ${TARGETS[@]+"${TARGETS[@]}"}; do
      [[ -z "$TGT" ]] && continue
      # Nothing to lose if it does not exist.
      [[ -e "$TGT" ]] || continue

      # Resolve to an absolute path (relative tokens resolve against the hook cwd,
      # which is where the real `rm` would run). Required so the git-status pathspec
      # below is interpreted against the right location even when cwd is a repo
      # SUBDIRECTORY — a relative pathspec under `git -C <root>` would otherwise
      # resolve against the root and silently miss the work.
      # realpath/`readlink -f` are GNU; stock macOS (BSD) lacks `readlink -f` and older
      # macOS lacks `realpath` — fall back to python3 (already resolved into $_RM_PY) before the
      # bare-echo degradation, so a relative target still resolves to absolute on BSD hosts.
      TGT_ABS=$(realpath "$TGT" 2>/dev/null \
        || readlink -f "$TGT" 2>/dev/null \
        || { [[ -n "${_RM_PY:-}" ]] && "${_RM_PY}" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TGT" 2>/dev/null; } \
        || echo "$TGT")

      # Claim-dir guard (CLAIM-CLEAR-LIVENESS) — evaluated BEFORE the generic .git
      # guard because claim dirs live INSIDE .git/coordinator-sessions/*-claims/ and
      # are regenerable session scratch, NOT git history. The generic .git deny text
      # ("no checkout, reflog, or stash recovers it") is factually false for a claim
      # dir (it is recreated on next claim) and steers the EM toward the
      # COORDINATOR_ALLOW_RM=1 override — a design-as-offers violation.
      # Short-circuits: on match, deny fires and does NOT fall through to .git guard.
      #
      # Known v1 bypass routes this guard does NOT catch (same class as the hook-
      # level v1 limitations documented at the top of this file):
      #   (a) cd into the claims dir then a relative `rm <basename>` — hook cwd is
      #       the hook's own working dir, not the cd target, so TGT_ABS resolves
      #       against the wrong location and the pattern does not match;
      #   (b) $VAR/glob targets (e.g. rm -rf $CLAIM_DIR, rm -rf *-claims/*) — not
      #       resolved per the hook's documented v1 limitation; they pass unchecked.
      # This hook is a backstop, not a complete seal. The doctrine (CLAIM-CLEAR-
      # LIVENESS in coordinator-tripwires.md) and cs_clear_claim_if_dead (lib/coordinator-session.sh)
      # cover the paths the hook cannot intercept.
      # Review: code-reviewer R2 — F5 cs_clear_claim_if_dead is now shipped; drop "forthcoming"
      if [[ "$TGT_ABS" == */coordinator-sessions/*-claims/* \
         || "$TGT_ABS" == */coordinator-sessions/*-claims ]]; then
        # Override still bypasses this site — out of scope for the 2026-07-10
        # peer-contest hardening (untracked-work branch only; see the
        # _RM_OVERRIDE capture note above check_destructive_rm's escape hatch).
        if [[ "$_RM_OVERRIDE" == "1" ]]; then
          continue
        fi
        _rm_deny "BLOCKED: '${TGT}' is a coordinator claim lock dir — regenerable session scratch, NOT git history. Do not rm it by hand.

Did you mean: cs_clear_claim_if_dead <class> <basename>

  cs_clear_claim_if_dead calls cs_claim_holder_live first and refuses to clear
  a LIVE peer's claim. The manual-rm path is exactly how a live peer gets stomped
  (see CLAIM-CLEAR-LIVENESS in coordinator-tripwires.md).

  cs_clear_claim_if_dead is the canonical safe path for clearing a stale claim.
  (Available in lib/coordinator-session.sh — source it first if not already loaded.)"
  # Review: code-reviewer R2 — F1 cs_clear_claim_if_dead shipped; "forthcoming" stale, steered agents wrong
        return
      fi

      # Any part of a .git store is irreversible repo corruption — deny regardless
      # of which repo it belongs to and without needing to resolve a worktree root
      # (which `git rev-parse` cannot do from INSIDE .git). The `*/.git` glob matches
      # `.git` and `.git/objects` etc. but NOT bare-repo names like `foo.git`.
      if [[ "$TGT_ABS" == *"/.git" || "$TGT_ABS" == *"/.git/"* || "$(basename "$TGT_ABS")" == ".git" ]]; then
        # Override still bypasses this site — out of scope for the 2026-07-10
        # peer-contest hardening (untracked-work branch only).
        if [[ "$_RM_OVERRIDE" == "1" ]]; then
          continue
        fi
        _rm_deny "BLOCKED: 'rm' would delete part of the git store at '${TGT}'. This corrupts/destroys repository history irreversibly — no checkout, reflog, or stash recovers it."
        return
      fi

      # Allowlist: regenerable coordinator scratch directories.
      # These are created fresh each run by coordinator skills (e.g. /workday-complete
      # Step 4f creates tasks/daily-review-scratch). They may contain untracked files
      # by design — that is what makes them look dirty to git — but they hold no
      # irrecoverable work.
      #
      # Hardened allowlist — all conditions must hold:
      #   (a) Not a symlink — realpath-following a symlink could match against an
      #       unintended target; fall through to normal deny evaluation. The trailing
      #       slash is stripped before the `-L` test (`-L dir/` dereferences the link and
      #       mis-reports a symlink as a non-link, which would re-open the allowlist fast
      #       path for `rm -rf tasks/<sym>-scratch/` — F9).
      #   (b) Scoped to THIS repo — only allow when $TGT_ABS is exactly
      #       <repo-root>/tasks/<name>-scratch. "Any tasks/*-scratch anywhere on
      #       disk" is too broad; only THIS repo's regenerable scratch is exempt.
      #   (c) Basename matches ^[a-zA-Z0-9_-]+-scratch$ — rejects dotfile-ish
      #       names like .git-scratch that could sneak through.
      #
      #   Preferred v2: let coordinator skills write to a gitignored location
      #   (e.g. tasks/.scratch/) so git treats them as disposable automatically
      #   and no allowlist is needed.
      SCRATCH_BN=$(basename "$TGT_ABS")
      SCRATCH_PAR_ABS=$(dirname "$TGT_ABS")
      SCRATCH_REPO=$(git -C "$SCRATCH_PAR_ABS" rev-parse --show-toplevel 2>/dev/null || true)
      # Use -ef (inode/device equality) to compare paths — avoids Windows Git Bash
      # path-style mismatches between realpath (/c/Users/...) and git rev-parse
      # (C:/Users/...) representations of the same directory.
      # CUR_REPO -ef SCRATCH_REPO ensures the scratch dir belongs to THIS repo,
      # not a sibling repo that happens to have a tasks/*-scratch by the same name.
      if [[ -n "$SCRATCH_REPO" \
            && -n "$CUR_REPO" \
            && "$CUR_REPO" -ef "$SCRATCH_REPO" \
            && ! -L "${TGT%/}" \
            && -d "${SCRATCH_REPO}/tasks" \
            && "$SCRATCH_PAR_ABS" -ef "${SCRATCH_REPO}/tasks" \
            && "$SCRATCH_BN" =~ ^[a-zA-Z0-9_-]+-scratch$ ]]; then
        continue  # regenerable coordinator scratch in THIS repo — allow without git-status check
      fi

      # Only evaluate trees: a directory target, or a file under recursive intent.
      if [[ -d "$TGT" || "$RECURSIVE" == "1" ]]; then
        # Resolve the enclosing repo from the target's parent. Outside any git
        # repo -> allow (scratch lives there).
        ROOT=$(git -C "$(dirname "$TGT_ABS")" rev-parse --show-toplevel 2>/dev/null || true)
        [[ -z "$ROOT" ]] && continue

        # Uncommitted/untracked work under the target (gitignored paths excluded by
        # git, so node_modules/build/.venv pass automatically). Non-empty -> loss.
        # Single status call (bound traversal with head); the count is derived from
        # the same capture to avoid a second invocation and a TOCTOU display race.
        STATUS=$(git -C "$ROOT" status --porcelain -- "$TGT_ABS" 2>/dev/null | head -9)
        if [[ -n "$STATUS" ]]; then
          # Peer-contest check (2026-07-10 hardening) — un-overridable when a LIVE
          # peer session in this shared worktree has touched a path under (or
          # containing) the target. Covers anything `git status --porcelain`
          # reports as dirty under the target — untracked files AND unstaged
          # edits to tracked files — both byte-indistinguishable from the
          # caller's own scratch, and git CANNOT recover either if deleted; a
          # blanket COORDINATOR_ALLOW_RM=1 must never be able to stomp a live
          # peer's in-progress work of either kind. Fires REGARDLESS of _RM_OVERRIDE.
          local _PEER_SID
          _PEER_SID=$(_rm_peer_claim_of "$TGT_ABS" "$ROOT")
          if [[ -n "$_PEER_SID" ]]; then
            _rm_deny "BLOCKED (not overridable): '${TGT}' holds untracked/uncommitted work claimed by LIVE peer session ${_PEER_SID} in this shared worktree. Untracked files are byte-indistinguishable from your own and git CANNOT recover them. If you believe it is stale, confirm with the peer or wait for their handoff — do not delete a live peer's uncommitted work."
            return
          fi

          if [[ "$_RM_OVERRIDE" == "1" ]]; then
            continue  # no live peer claims this untracked target — override honored
          fi

          DISP=$(printf '%s\n' "$STATUS" | head -8)
          MORE=""
          [[ "$(printf '%s\n' "$STATUS" | grep -c .)" -gt 8 ]] && MORE="
  ... and more (first 8 shown)"
          _rm_deny "BLOCKED: 'rm' on '${TGT}' would destroy uncommitted/untracked work that git CANNOT recover (untracked files and unstaged edits live in no commit, no stash, no reflog):
${DISP}${MORE}

Before overriding, re-derive what would actually be lost (do not trust a remembered or narrated state):
  git -C \"${ROOT}\" status --porcelain -- \"${TGT_ABS}\"

To preserve the work first, stash it (includes untracked; restore later with stash pop):
  git -C \"${ROOT}\" stash push -u -- \"${TGT_ABS}\"   # -u includes untracked; restore later: git -C \"${ROOT}\" stash pop

Reserve irreversible deletion for genuinely disposable, self-authored, uncontested paths."
          return
        fi
      fi
    done

  done <<< "$SEGMENTS"

  # No covered destructive rm (or all evaluated as safe) -> allow.
  return 0
}

# ---------------------------------------------------------------------------
# Main guard — runs ONLY when this script is executed directly (not sourced).
# When sourced (e.g. by a dispatcher), only the function definitions above are
# evaluated; no stdin is read and no logic executes at source time.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
  if command -v timeout &>/dev/null; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
  fi

  # --- Parse tool_name + command (jq -> python -> sed/grep fallback) ---
  PARSE_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if command -v jq &>/dev/null; then
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  elif [[ -n "$PARSE_PY" ]]; then
    TOOL_NAME=$(printf '%s' "$INPUT" | "$PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
    CMD=$(printf '%s' "$INPUT" | "$PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
  else
    TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    CMD=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
  fi

  [[ "$TOOL_NAME" != "Bash" ]] && exit 0
  [[ -z "$CMD" ]] && exit 0

  check_destructive_rm "$CMD" ""
  exit 0
fi
