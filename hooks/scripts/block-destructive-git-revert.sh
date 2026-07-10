#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks a whole-tree revert of UNCOMMITTED TRACKED
# work (`git checkout .` / `git restore .` / `git reset --hard`) and an
# unscoped stash-sweep of untracked work (`git stash -u` with no pathspec)
# when the discarded work is load-bearing or peer-claimed.
#
# Motivation: sibling to block-destructive-git-orphan.sh (committed-work loss
# class), block-destructive-rm.sh (uncommitted-rm loss class), and
# block-destructive-git-clean.sh (uncommitted-clean/untracked loss class).
# This hook closes the FOURTH leg — the "uncommitted-tracked-REVERT +
# untracked-sweep" loss class.
#
# 2026-07-10 project-rag incident (accepted cross-repo memo): on a shared
# work/* tree, a sibling session ran `git checkout .` which reverted
# tracked-but-uncommitted hunks in shared files (registry, pyproject, golden
# fixtures, wiki) — a live peer's reviewed-and-ready work. Unstaged edits to
# TRACKED files live in no git object (not a commit, not a stash, not the
# reflog), so this loss is git-unrecoverable. The orphan guard does NOT catch
# it: `git checkout .` / `git restore .` / `git reset --hard HEAD` all drop
# ZERO commits (the orphan guard only denies commit-DROPPING resets), so a
# same-branch whole-tree revert sails through that guard untouched.
#
# Sibling guards:
#   block-destructive-git-orphan.sh  — committed-work loss (reset --hard DROPS commits / force-push / branch -D)
#   block-destructive-rm.sh          — uncommitted-rm loss (rm -rf on dirty trees)
#   block-destructive-git-clean.sh   — uncommitted-clean loss (untracked sweep via git clean)
#   block-destructive-git-revert.sh  — uncommitted-tracked-REVERT + unscoped stash-sweep loss (this file)
#
# Trigger scope (deliberately narrow, to stay an offer not a nag):
#   1. `git checkout .` / `git checkout -- .` / `git checkout HEAD .` /
#      `git checkout HEAD -- .` / `git checkout <ref> -- .` — WHOLE-TREE
#      working-tree overwrite (pathspec is literally `.`). A branch switch
#      (`git checkout <branch>`) and a SCOPED checkout (`git checkout --
#      <specific-path>`) are NOT matched — those are different ops / the safe
#      alternative this hook steers toward.
#   2. `git restore .` / `git restore -- .` / `git restore --worktree .` /
#      `git restore -W .` / `git restore --staged --worktree .` — whole-tree,
#      ONLY when the working tree is the target (default, or `-W`/`--worktree`
#      present). `git restore --staged .` (staged-ONLY, no `-W`) does NOT
#      touch the working tree and is explicitly NOT matched (non-destructive).
#   3. `git reset --hard` with NO pathspec (git rejects `--hard` + a pathspec,
#      so only the no-pathspec form is reachable). Independent of the orphan
#      guard, which runs earlier in the dispatch chain and denies FIRST on any
#      commit-dropping reset (first-deny-wins) — this hook catches the
#      uncommitted-hunk loss on a same-branch `reset --hard` the orphan guard
#      lets through.
#   4. `git stash` / `git stash push` / `git stash save` WITH `-u` /
#      `--include-untracked` / `-a` / `--all` AND NO `-- <pathspec>` — an
#      UNSCOPED untracked-sweep. A SCOPED `git stash push -u -- <paths>` is
#      NOT matched (that is the safe form the rm/clean guards already
#      recommend).
#
# Precision gate (what keeps this an offer, not a nag): a naive "deny every
# `git checkout .` on a dirty tree" would fire on routine self-discard of own
# WIP. Instead, an ORACLE re-derives what the op would actually discard
# (`git status --porcelain` filtered to the affected paths for
# checkout/restore/reset-hard; the untracked `??` set for stash -u), and each
# affected path is classified as LOAD-BEARING (mirrors
# block-destructive-git-clean.sh's _gc_LOADBEARING_RE / _gc_LOADBEARING_PREFIXES
# two-direction ancestor check, copied here with _gr_ names so this hook is
# self-contained standalone) or PEER-CLAIMED (mirrors block-destructive-rm.sh's
# _rm_peer_claim_of, copied here as _gr_peer_claim_of for the same reason).
# DENY fires iff >=1 affected path is load-bearing OR peer-claimed; otherwise
# ALLOW (the operator's own disposable WIP is left alone).
#
# Fail-safe direction: not-a-repo / git-error oracle failures ALLOW silently
# (nothing to lose / can't scope). A `git status --porcelain` that DID report
# affected paths but cannot be classified due to missing tooling (no `_GR_PY`)
# fails SAFE toward DENY with the override offered — mirrors the clean guard's
# timeout-deny posture.
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
# Override: export COORDINATOR_OVERRIDE_GIT_REVERT=1 in the environment (NOT
# an inline prefix — that sets the var for the git child, not this hook
# process). Honored early, before the oracle runs — same pattern as the clean
# guard's COORDINATOR_OVERRIDE_GIT_CLEAN.
#
# Sourceable interface (check_destructive_git_revert):
#   source block-destructive-git-revert.sh
#   check_destructive_git_revert "$cmd" "$session_id"
# When sourced, only the function and file-scope helpers are defined; no stdin
# is read and no logic executes at source time. On DENY, the function prints
# the nested hookSpecificOutput JSON to stdout and returns. On allow, it
# prints nothing and returns 0.
#
# KNOWN v1 limitations (classify each as fail-open or fail-safe):
#   - Literal command-verb match only, at COMMAND POSITION — mirrors the
#     clean/rm guards' wrapped/grouped/quoted-verb coverage (leading-opener
#     peel, quote-stripped probe) and shell-invoker broad fallback
#     (`bash -c '...'`, `eval ...`), plus the execution-wrapper class
#     (sudo/env/time/exec/nice/nohup/ionice/timeout/stdbuf/which/type).
#     Aliased forms (`git co` mapped via `.gitconfig`) are NOT detected —
#     fail OPEN.
#   - `$(which git) checkout .` — the subshell resolves at runtime; the hook
#     sees an unresolved token and does NOT match — fail OPEN.
#   - `cd <dir> && git checkout .` — oracle is evaluated against the hook's
#     own cwd (parity with block-destructive-rm.sh / block-destructive-git-
#     clean.sh § cd limitation). The `cd` target is not followed — fail OPEN.
#   - `git -C <dir> checkout .` IS handled: the oracle mirrors `-C <dir>` so
#     the scope matches the real op — fail SAFE.
#   - `git -C "path with spaces" checkout .` — the -C path extractor uses
#     whitespace tokenization; quoted multi-token paths are not handled. The
#     oracle runs against the hook's cwd instead — fail OPEN for that segment.
#   - Multi-segment commands (`;`, `&&`, `||`, `|`, `&`) are handled via
#     segment split — each segment is evaluated independently — fail SAFE.
#   - `timeout` binary absent (macOS BSD without GNU coreutils): the oracle
#     runs without a time cap — fail OPEN for the *timeout* case only. The
#     load-bearing/peer-claim deny still functions — fail SAFE.
#   - PowerShell equivalents are not covered — fail OPEN (Bash hook only; the
#     dispatcher receives Bash tool calls).
#   - Ancestor-directory collapse IS handled (fail SAFE) via the same
#     two-direction classifier as the clean guard.
#   - `git stash` (no `-u`/`-a`) is NOT matched — plain stash of tracked
#     changes only is git-recoverable (stash pop) and out of scope; the
#     distinct hazard this hook guards is the UNTRACKED sweep.

set -uo pipefail

# Source the coordinator state-root seam for dynamic load-bearing path resolution.
# Guarded — no-op if the lib is absent (partial install, pre-C2 checkout).
# coordinator-state-root.sh is idempotent (safe to source multiple times).
_gr_CSR_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)/lib/coordinator-state-root.sh"
if [[ -f "$_gr_CSR_LIB" ]]; then
  # shellcheck source=../../lib/coordinator-state-root.sh
  source "$_gr_CSR_LIB" 2>/dev/null || true
fi
unset _gr_CSR_LIB

# ---------------------------------------------------------------------------
# File-scope constants and helpers — _gr_-prefixed to avoid name collisions
# when this file is sourced alongside sibling hooks:
#   block-destructive-rm.sh          uses _rm_-prefixed names
#   block-destructive-git-orphan.sh  uses _orphan_-prefixed names
#   block-destructive-git-clean.sh   uses _gc_-prefixed names
# ---------------------------------------------------------------------------

# Load-bearing path classifier — copied verbatim (with _gr_ names) from
# block-destructive-git-clean.sh so this hook is self-contained standalone.
# Cross-reference: the canonical load-bearing surface is defined in
# ~/.claude/CLAUDE.md § "state/ vs tasks/" and the coordinator CLAUDE.md §
# "state/ vs tasks/". This regex must stay in sync with that surface
# definition AND with _gc_LOADBEARING_RE in block-destructive-git-clean.sh.
_gr_LOADBEARING_RE='(^|/)state(/|$)|(^|/)docs/plans(/|$)|(^|/)docs/decisions(/|$)|(^|/)docs/wiki(/|$)|(^|/)docs/research(/|$)|(^|/)cross-repo/(inbox|archive|outbox)(/|$)|-handoff.*\.md$|(^|/)completion(/|$)|review-trail/.*\.json$'

# Explicit directory-form load-bearing prefixes — parallel to the directory
# alternatives in _gr_LOADBEARING_RE, used for the ANCESTOR-direction check: a
# path P is also load-bearing when P is an ANCESTOR of a load-bearing
# directory (e.g. "docs" is an ancestor of "docs/plans").
_gr_LOADBEARING_PREFIXES=(
  "state"
  "docs/plans"
  "docs/decisions"
  "docs/wiki"
  "docs/research"
  "cross-repo/inbox"
  "cross-repo/archive"
  "cross-repo/outbox"
)

# _gr_is_loadbearing <path>
#   Two-direction classifier — returns 0 (true) if <path> is load-bearing.
#   Direction 1: P is under (or equal to) a load-bearing dir (regex).
#   Direction 2: P is an ancestor of a load-bearing dir (prefix-list check).
#   Direction 3: seam-resolved state root (post-migration central state).
_gr_is_loadbearing() {
  local p="${1%/}" prefix
  [[ -z "$p" ]] && return 1
  if printf '%s' "$p" | grep -qE "$_gr_LOADBEARING_RE"; then
    return 0
  fi
  for prefix in ${_gr_LOADBEARING_PREFIXES[@]+"${_gr_LOADBEARING_PREFIXES[@]}"}; do
    if [[ "$prefix" == "$p" || "$prefix" == "$p"/* ]]; then
      return 0
    fi
  done
  if [[ -n "${_gr_seam_state_root:-}" ]]; then
    if [[ "$p" == "$_gr_seam_state_root" || "$p" == "$_gr_seam_state_root"/* ]]; then
      return 0
    elif [[ "$_gr_seam_state_root" == "$p"/* ]]; then
      return 0
    fi
  fi
  return 1
}

# Override hint text — references COORDINATOR_OVERRIDE_GIT_REVERT. Kept LAST
# in every deny message (design-as-offers — never lead with the override).
_GR_OVERRIDE_HINT="If this revert is genuinely intended, export COORDINATOR_OVERRIDE_GIT_REVERT=1 in your environment first (an inline prefix on the git command does NOT reach this hook)."

# Emit the deny JSON to stdout. Does NOT call exit — the caller must `return`
# immediately after this. Uses _GR_PY (set by check_destructive_git_revert at
# entry; stored without `local` so this file-scope function can read it).
_gr_deny() {
  local reason="$1"
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "${_GR_PY:-}" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "${_GR_PY}" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
}

# _gr_peer_claim_of <tgt_abs> <root>
#   Copied (with _gr_ names) from block-destructive-rm.sh's _rm_peer_claim_of
#   (2026-07-10 peer-contest hardening) so this hook is self-contained
#   standalone. Echoes the session id of a LIVE peer coordinator session (not
#   this process's own session) that has TOUCHED a path equal to, under, or
#   containing <tgt_abs>'s repo-relative path, per the shared-worktree
#   touched.txt ledger (lib/coordinator-session.sh). Prints nothing if no live
#   peer contests the target.
#
#   Liveness: prefers the canonical cs_live_session_ids (lib/coordinator-
#   session.sh) when resolvable. Degrades to a 30-minute touched.txt mtime
#   heuristic when the lib/function is unavailable. DR-148: no
#   `find -newermt` (GNU-only); mtime compared via _GR_PY epoch read.
#
#   Self-identity: cur_sid self-exclusion routes through cs_resolve_session_id
#   (NOT the raw .current-session-id sentinel) with a fail-safe don't-exclude
#   fallback when identity is unresolvable/ambiguous under concurrency.
_gr_peer_claim_of() {
  local tgt_rel_in="$1" root="$2"
  local sess_dir="${root}/.git/coordinator-sessions"
  [[ -d "$sess_dir" ]] || return 0

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

  local tgt_rel="$tgt_rel_in"
  [[ -z "$tgt_rel" ]] && return 0

  local sid line now_epoch mtime_epoch _canon_covers _l _l_matched
  for sid in "$sess_dir"/*/; do
    [[ -d "$sid" ]] || continue
    sid="${sid%/}"; sid="$(basename "$sid")"
    [[ -n "$cur_sid" && "$sid" == "$cur_sid" ]] && continue
    [[ "$sid" == ".archive" || "$sid" == ".agents" ]] && continue

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
      [[ -f "${sess_dir}/${sid}/touched.txt" ]] || continue
      if [[ -n "${_GR_PY:-}" ]]; then
        mtime_epoch=$("${_GR_PY}" -c 'import os,sys;print(int(os.path.getmtime(sys.argv[1])))' "${sess_dir}/${sid}/touched.txt" 2>/dev/null || true)
        now_epoch=$("${_GR_PY}" -c 'import time;print(int(time.time()))' 2>/dev/null || true)
        [[ -z "$mtime_epoch" || -z "$now_epoch" ]] && continue
        (( now_epoch - mtime_epoch > 1800 )) && continue
      else
        :   # no python -> fail-safe: treat as contested (cannot verify staleness)
      fi
    fi

    [[ -f "${sess_dir}/${sid}/touched.txt" ]] || continue
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      [[ "${line#"$tgt_rel"/}" != "$line" ]] && { echo "$sid"; return 0; }
      [[ "${tgt_rel#"$line"/}" != "$tgt_rel" ]] && { echo "$sid"; return 0; }
      [[ "$line" == "$tgt_rel" ]] && { echo "$sid"; return 0; }
    done < "${sess_dir}/${sid}/touched.txt"
  done

  return 0
}

# Detect whether a single command SEGMENT invokes `git checkout`/`git
# restore`/`git reset`/`git stash` as a command verb. Sets file-scope
# _GR_MATCHED_VERB to which one matched ("checkout"|"restore"|"reset"|"stash")
# for the caller to branch on. Mirrors _gc_is_clean_segment's leading-opener
# peel + shell-invoker fallback + execution-wrapper class + command-position
# regex structure exactly.
_gr_is_revert_segment() {
  local seg="$1" probe prev=""
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
  probe="${seg//\'/}"; probe="${probe//\"/}"

  _GR_MATCHED_VERB=""

  # Shell-invoker broad fallback: bash/sh/zsh/dash -c, or eval — the payload
  # EXECUTES, so a broad scan for `git ... <verb>` in the payload is correct.
  if printf '%s' "$probe" | grep -qE '^(bash|sh|zsh|dash)[[:space:]]+([^[:space:]]+[[:space:]]+)*-c([[:space:]]|$)|^eval([[:space:]]|$)'; then
    if printf '%s' "$probe" | grep -qE '\bgit\b.*\bcheckout\b'; then _GR_MATCHED_VERB="checkout"; return 0; fi
    if printf '%s' "$probe" | grep -qE '\bgit\b.*\brestore\b'; then _GR_MATCHED_VERB="restore"; return 0; fi
    if printf '%s' "$probe" | grep -qE '\bgit\b.*\breset\b'; then _GR_MATCHED_VERB="reset"; return 0; fi
    if printf '%s' "$probe" | grep -qE '\bgit\b.*\bstash\b'; then _GR_MATCHED_VERB="stash"; return 0; fi
    return 1
  fi

  # Execution-wrapper / verb-resolver class.
  local firstword="${seg%%[[:space:]]*}"
  case "$firstword" in
    sudo|command|time|exec|nice|nohup|env|ionice|timeout|stdbuf|which|type)
      if printf '%s' "$seg" | grep -qE '\bgit\b.*\bcheckout\b'; then _GR_MATCHED_VERB="checkout"; return 0; fi
      if printf '%s' "$seg" | grep -qE '\bgit\b.*\brestore\b'; then _GR_MATCHED_VERB="restore"; return 0; fi
      if printf '%s' "$seg" | grep -qE '\bgit\b.*\breset\b'; then _GR_MATCHED_VERB="reset"; return 0; fi
      if printf '%s' "$seg" | grep -qE '\bgit\b.*\bstash\b'; then _GR_MATCHED_VERB="stash"; return 0; fi
      return 1 ;;
  esac

  # Direct command position: `git [global-opts] <verb>` anchored to `^`.
  local base_re='^[[:space:]]*((sudo|command|time|exec|nice|nohup|ionice|timeout|stdbuf|which|type)[[:space:]]+|env[[:space:]]+([^[:space:]]+=[^[:space:]]*[[:space:]]+)*|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(/[^[:space:]]*/)?git([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|--(git-dir|work-tree|namespace)(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)|--exec-path(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)?|-p|--paginate|--no-pager|--bare|--no-replace-objects|--literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs|--no-optional-locks))*[[:space:]]+'

  if printf '%s' "$probe" | grep -qE "${base_re}checkout\b"; then _GR_MATCHED_VERB="checkout"; return 0; fi
  if printf '%s' "$probe" | grep -qE "${base_re}restore\b"; then _GR_MATCHED_VERB="restore"; return 0; fi
  if printf '%s' "$probe" | grep -qE "${base_re}reset\b"; then _GR_MATCHED_VERB="reset"; return 0; fi
  if printf '%s' "$probe" | grep -qE "${base_re}stash\b"; then _GR_MATCHED_VERB="stash"; return 0; fi
  return 1
}

# ---------------------------------------------------------------------------
# check_destructive_git_revert <command> <session_id>
#
# Contains ALL decision logic for the destructive-git-revert guard. Prints
# the nested hookSpecificOutput deny JSON to stdout when a covered
# destructive whole-tree revert / unscoped stash-sweep is detected; prints
# nothing and returns 0 on allow.
#
# $2 (session_id) accepted for dispatcher interface compat; not used —
# resolution is driven by oracle output + peer-claim probe, not identity.
# ---------------------------------------------------------------------------
check_destructive_git_revert() {
  # Resolve python interpreter; stored WITHOUT `local` so file-scope helpers
  # (_gr_deny, _gr_peer_claim_of) can read it. Idempotent on repeated calls.
  _GR_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  local CMD="$1"

  # Normalize CRLF -> LF (Windows/Git-Bash jq.exe text-mode CR injection).
  CMD="${CMD//$'\r'/}"

  # Join backslash-newline continuations so a split op is one segment.
  local NL=$'\n'
  CMD="${CMD//\\$NL/ }"

  # Strip heredoc bodies — verbatim awk strip from the sibling guards.
  local _BDGR_AWK _BDGR_STRIPPED _BDGR_RC
  _BDGR_AWK=$(mktemp 2>/dev/null || true)
  if [[ -n "$_BDGR_AWK" ]]; then
    cat > "$_BDGR_AWK" << 'BDGR_AWK_EOF'
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
BDGR_AWK_EOF
    _BDGR_STRIPPED=$(printf '%s' "$CMD" | awk -f "$_BDGR_AWK"); _BDGR_RC=$?
    rm -f "$_BDGR_AWK"
    [[ "$_BDGR_RC" -eq 0 ]] && CMD="$_BDGR_STRIPPED"
  fi

  # Fast bail: nothing to do unless `git` and at least one covered verb appear.
  printf '%s' "$CMD" | grep -qE '\bgit\b' || return 0
  printf '%s' "$CMD" | grep -qE '\bcheckout\b|\brestore\b|\breset\b|\bstash\b' || return 0

  # Escape hatch (honored early, before oracle runs).
  [[ "${COORDINATOR_OVERRIDE_GIT_REVERT:-0}" == "1" ]] && return 0

  # --- Seam-resolved state root (Direction 3), reused by _gr_is_loadbearing. ---
  # Deliberately assigned WITHOUT `local` — file-scope by design so
  # _gr_is_loadbearing (a separate function) can read it, mirroring the
  # _GR_PY/_RM_PY cross-function-read convention documented elsewhere in
  # this file.
  _gr_seam_state_root=""
  if command -v coordinator_state_root &>/dev/null; then
    _gr_seam_state_root=$(coordinator_state_root 2>/dev/null || true)
  fi

  local -a _gr_timeout_prefix=()
  command -v timeout &>/dev/null && _gr_timeout_prefix=("timeout" "2")

  # bash < 4.4 (stock macOS /bin/bash 3.2): "${arr[@]}" on an EMPTY array
  # under `set -u` is a fatal "unbound variable" that aborts the hook
  # mid-run — no deny JSON is emitted, so a destructive revert is SILENTLY
  # ALLOWED (fail-open). Both _gr_timeout_prefix (empty when `timeout` is
  # absent — stock macOS BSD userland) and GIT_C_ARGS (empty when the command
  # carries no `git -C <dir>`) are commonly empty here. Every expansion of
  # both below uses ${arr[@]+"${arr[@]}"} — the bash-3.2-safe idiom that
  # expands to nothing when the array is empty/unset, else the elements
  # verbatim — identical behavior to "${arr[@]}" on bash >=4.4, portable down
  # to 3.2.
  # --- Evaluate each command segment independently. ---
  local SEGMENTS
  SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

  local SEG
  while IFS= read -r SEG; do
    [[ -z "${SEG//[[:space:]]/}" ]] && continue

    _gr_is_revert_segment "$SEG" || continue
    local VERB="$_GR_MATCHED_VERB"

    # Extract git -C <dir> if present (oracle must run against the same dir).
    local GIT_C_DIR=""
    GIT_C_DIR=$(printf '%s' "$SEG" \
      | grep -oE '\bgit([[:space:]]+[^[:space:]]+)*[[:space:]]+-C[[:space:]]+[^[:space:]]+' \
      | grep -oE '[-]C[[:space:]]+[^[:space:]]+' \
      | sed 's/[-]C[[:space:]]*//' \
      | tail -n 1 2>/dev/null || true)

    local -a GIT_C_ARGS=()
    [[ -n "$GIT_C_DIR" ]] && GIT_C_ARGS=("-C" "$GIT_C_DIR")

    # Tokens after the verb (used to scan flags/pathspec).
    # BSD sed's ERE lacks \b (GNU-only extension); use the [[:space:]]-boundary
    # idiom so this strips the verb identically on BSD and GNU. `\bVERB\b` was a
    # silent NO-OP on BSD sed (DR-148 audit, 2026-07-10).
    local AFTER=""
    case "$VERB" in
      checkout) AFTER=$(printf '%s' "$SEG" | sed -E 's/.*(^|[[:space:]])checkout([[:space:]]|$)/ /') ;;
      restore)  AFTER=$(printf '%s' "$SEG" | sed -E 's/.*(^|[[:space:]])restore([[:space:]]|$)/ /') ;;
      reset)    AFTER=$(printf '%s' "$SEG" | sed -E 's/.*(^|[[:space:]])reset([[:space:]]|$)/ /') ;;
      stash)    AFTER=$(printf '%s' "$SEG" | sed -E 's/.*(^|[[:space:]])stash([[:space:]]|$)/ /') ;;
    esac

    local -a AFFECTED_PATHS=()
    local ORACLE_OUT="" ORACLE_RC=0

    if [[ "$VERB" == "checkout" || "$VERB" == "restore" ]]; then
      # --- Whole-tree pathspec-is-. detection. ---
      # Strip a trailing '.' token (possibly preceded by `--`) and confirm it
      # is the ONLY non-flag token, i.e. the effective pathspec is exactly `.`.
      local -a toks=()
      set -f
      for _t in $AFTER; do toks+=("$_t"); done
      set +f

      local dotspec=0 nonflag_count=0 seen_dashdash=0 tk
      for tk in ${toks[@]+"${toks[@]}"}; do
        case "$tk" in
          --) seen_dashdash=1; continue ;;
        esac
        if [[ "$seen_dashdash" -eq 1 ]]; then
          nonflag_count=$((nonflag_count + 1))
          # "./" is whole-tree-equivalent to "." in git — normalize a single
          # trailing slash before comparing (does not affect "./sub" or
          # "sub/." which retain non-"." content after stripping one slash).
          [[ "${tk%/}" == "." ]] && dotspec=1
        else
          case "$tk" in
            -*) : ;;   # flag — ignore (covers -W/-S/--worktree/--staged/HEAD-as-ref is not a flag though)
            *)
              # Non-flag token before `--`: could be a ref (checkout) or `.`
              # itself (restore/checkout without --).
              nonflag_count=$((nonflag_count + 1))
              [[ "${tk%/}" == "." ]] && dotspec=1
              ;;
          esac
        fi
      done

      # Only proceed when the pathspec is exactly `.` and nothing else
      # non-flag was supplied besides an optional leading ref (checkout
      # HEAD . / checkout <ref> -- .). A bare branch-switch (`git checkout
      # main`) has nonflag_count==1 and dotspec==0 -> skip (not matched).
      # A scoped checkout (`git checkout -- somefile`) has dotspec==0 -> skip.
      if [[ "$dotspec" -eq 1 ]]; then
        # Bundle-aware staged/worktree flag detection (Finding 4): also match
        # bundled short forms (-SW/-WS/etc, mirroring block-destructive-git-
        # clean.sh's bundled -x/-X/-n matching) in addition to the standalone
        # whitespace-bounded long/short forms. Restore defaults to worktree
        # when no flag narrows it, so "worktree targeted" is: -W/--worktree
        # present, OR no --staged at all (restore's default scope).
        local has_staged=0 has_worktree=0
        if printf '%s' "$AFTER" | grep -qE '(^|[[:space:]])(-[a-zA-Z]*S[a-zA-Z]*|--staged)([[:space:]]|$)'; then has_staged=1; fi
        if printf '%s' "$AFTER" | grep -qE '(^|[[:space:]])(-[a-zA-Z]*W[a-zA-Z]*|--worktree)([[:space:]]|$)'; then has_worktree=1; fi

        if [[ "$VERB" == "restore" ]]; then
          # git restore --staged . (no -W/--worktree) does NOT touch the
          # working tree -> explicitly ALLOW (non-destructive).
          if [[ "$has_staged" -eq 1 && "$has_worktree" -eq 0 ]]; then
            continue   # staged-only restore — non-destructive, next segment
          fi
        fi

        # Every form reaching this point is worktree-targeted: checkout is
        # always worktree-targeted (no --staged concept); restore is
        # worktree-targeted here because the staged-only skip above already
        # `continue`d the pure-staged case.

        # --- Oracle: git status --porcelain filtered to the paths the op
        # would actually discard. `checkout .` / `restore .` (worktree-
        # targeted, the only forms reaching this point — see Finding 1)
        # overwrite the WORKING TREE from the index; they do NOT touch the
        # index/staged content itself. So only rows with a non-blank
        # WORKTREE column (2nd status char) are affected — a pure-staged row
        # (index col non-blank, worktree col blank, e.g. "A "/"M ") is left
        # untouched by these ops and must be excluded, else the oracle
        # over-reports AFFECTED_PATHS and can falsely DENY a safe op (the
        # routine "stage one file, checkout . to discard an unrelated
        # unstaged edit elsewhere" case the precision gate exists to leave
        # alone). `reset --hard` (below) is a SEPARATE oracle block that
        # correctly includes both columns — that op genuinely discards both
        # staged and unstaged tracked state.
        ORACLE_OUT=$(LC_ALL=C ${_gr_timeout_prefix[@]+"${_gr_timeout_prefix[@]}"} git ${GIT_C_ARGS[@]+"${GIT_C_ARGS[@]}"} status --porcelain 2>/dev/null) || ORACLE_RC=$?
        if [[ "$ORACLE_RC" -eq 124 ]]; then
          _gr_deny "BLOCKED: 'git ${VERB} .' oracle (git status) timed out (2 s) — cannot verify the revert is safe.

Safe path first — verify what would be discarded, then preserve it:
  git status --porcelain
  git stash push -u -m \"before-revert\" -- <paths>   # make it recoverable

After preserving the files, re-run. Or:
${_GR_OVERRIDE_HINT}"
          return
        fi
        [[ "$ORACLE_RC" -ne 0 ]] && { ORACLE_RC=0; continue; }   # not a repo / error — nothing to lose

        local st_line st_cols st_path
        while IFS= read -r st_line; do
          [[ -z "$st_line" ]] && continue
          st_cols="${st_line:0:2}"
          st_path="${st_line:3}"
          # Strip rename arrow "old -> new" -> use new path.
          [[ "$st_path" == *" -> "* ]] && st_path="${st_path##* -> }"
          # Skip untracked (??) — checkout/restore/reset-hard do not remove
          # untracked files; that is git clean's / stash -u's domain.
          [[ "$st_cols" == "??" ]] && continue
          # checkout/restore (worktree-targeted) only discard WORKTREE
          # modifications — the 2nd status char (index char at position 1 is
          # NOT examined here; a pure-staged row like "A "/"M " must be
          # excluded, see Finding 1 above).
          if [[ "${st_cols:1:1}" != " " ]]; then
            AFFECTED_PATHS+=("$st_path")
          fi
        done <<< "$ORACLE_OUT"
      fi

    elif [[ "$VERB" == "reset" ]]; then
      # git reset --hard with NO pathspec. git rejects --hard + a pathspec,
      # so if --hard is present the whole tracked-worktree+index is in scope
      # regardless of what tokens follow (a ref like HEAD is not a pathspec).
      if printf '%s' "$AFTER" | grep -qE '(^|[[:space:]])--hard([[:space:]]|$)'; then
        ORACLE_OUT=$(LC_ALL=C ${_gr_timeout_prefix[@]+"${_gr_timeout_prefix[@]}"} git ${GIT_C_ARGS[@]+"${GIT_C_ARGS[@]}"} status --porcelain 2>/dev/null) || ORACLE_RC=$?
        if [[ "$ORACLE_RC" -eq 124 ]]; then
          _gr_deny "BLOCKED: 'git reset --hard' oracle (git status) timed out (2 s) — cannot verify the reset is safe.

Safe path first — verify what would be discarded, then preserve it:
  git status --porcelain
  git stash push -u -m \"before-reset\" -- <paths>   # make it recoverable

After preserving the files, re-run. Or:
${_GR_OVERRIDE_HINT}"
          return
        fi
        [[ "$ORACLE_RC" -ne 0 ]] && { ORACLE_RC=0; continue; }

        local rs_line rs_cols rs_path
        while IFS= read -r rs_line; do
          [[ -z "$rs_line" ]] && continue
          rs_cols="${rs_line:0:2}"
          rs_path="${rs_line:3}"
          [[ "$rs_path" == *" -> "* ]] && rs_path="${rs_path##* -> }"
          # reset --hard discards ALL tracked staged+unstaged changes — skip
          # only pure-untracked (??) rows.
          [[ "$rs_cols" == "??" ]] && continue
          if [[ "$rs_cols" != "  " ]]; then
            AFFECTED_PATHS+=("$rs_path")
          fi
        done <<< "$ORACLE_OUT"
      fi

    elif [[ "$VERB" == "stash" ]]; then
      # Unscoped -u/-a stash: match only push/save (bare `git stash` defaults
      # to push) WITH -u/--include-untracked/-a/--all AND NO `-- <pathspec>`.
      # Also match bundled short forms (-um/-au/etc, mirroring the has_staged/
      # has_worktree bundling above and block-destructive-git-clean.sh's
      # bundled -x/-X/-n matching) alongside the long-form alternatives.
      local has_u=0 has_dashdash=0
      if printf '%s' "$AFTER" | grep -qE '(^|[[:space:]])(-[a-zA-Z]*u[a-zA-Z]*|--include-untracked|-[a-zA-Z]*a[a-zA-Z]*|--all)([[:space:]]|$)'; then
        has_u=1
      fi
      if printf '%s' "$AFTER" | grep -qE '(^|[[:space:]])--([[:space:]]|$)'; then
        has_dashdash=1
      fi
      # Also require the subcommand (if any explicit word follows `stash`)
      # is push/save/not-a-recognized-subcommand-that-isn't-push (pop/apply/
      # drop/list/show/clear do not take -u in a destructive-sweep sense and
      # are excluded by requiring has_u to be meaningful only alongside
      # push/save or the bare default form).
      local first_after_tok=""
      for _t in $AFTER; do first_after_tok="$_t"; break; done
      case "$first_after_tok" in
        pop|apply|drop|list|show|clear|branch) has_u=0 ;;   # not a sweep form
      esac

      if [[ "$has_u" -eq 1 && "$has_dashdash" -eq 0 ]]; then
        # Oracle: untracked (??) files that would be swept, mirroring the
        # clean guard's untracked-set focus (the distinct hazard vs a scoped
        # stash is the UNTRACKED sweep).
        ORACLE_OUT=$(LC_ALL=C ${_gr_timeout_prefix[@]+"${_gr_timeout_prefix[@]}"} git ${GIT_C_ARGS[@]+"${GIT_C_ARGS[@]}"} status --porcelain 2>/dev/null) || ORACLE_RC=$?
        if [[ "$ORACLE_RC" -eq 124 ]]; then
          _gr_deny "BLOCKED: 'git stash -u' oracle (git status) timed out (2 s) — cannot verify the sweep is safe.

Safe path first — scope the stash to your own paths:
  git stash push -u -m \"before-stash\" -- <paths>

Or: ${_GR_OVERRIDE_HINT}"
          return
        fi
        [[ "$ORACLE_RC" -ne 0 ]] && { ORACLE_RC=0; continue; }

        local ss_line ss_cols ss_path
        while IFS= read -r ss_line; do
          [[ -z "$ss_line" ]] && continue
          ss_cols="${ss_line:0:2}"
          ss_path="${ss_line:3}"
          [[ "$ss_cols" == "??" ]] || continue
          AFFECTED_PATHS+=("$ss_path")
        done <<< "$ORACLE_OUT"
      fi
    fi

    [[ "${#AFFECTED_PATHS[@]}" -eq 0 ]] && continue

    # Resolve repo root for the peer-claim probe (per-segment, mirrors -C).
    local REPO_ROOT
    REPO_ROOT=$(git ${GIT_C_ARGS[@]+"${GIT_C_ARGS[@]}"} rev-parse --show-toplevel 2>/dev/null || true)

    # --- Classify each affected path: load-bearing OR peer-claimed. ---
    local -a DENY_PATHS=()
    local -a DENY_REASONS=()
    local ap lb_hit peer_sid
    for ap in ${AFFECTED_PATHS[@]+"${AFFECTED_PATHS[@]}"}; do
      lb_hit=0
      _gr_is_loadbearing "$ap" && lb_hit=1

      peer_sid=""
      if [[ -n "$REPO_ROOT" ]]; then
        peer_sid=$(_gr_peer_claim_of "$ap" "$REPO_ROOT")
      fi

      if [[ "$lb_hit" -eq 1 && -n "$peer_sid" ]]; then
        DENY_PATHS+=("$ap"); DENY_REASONS+=("load-bearing, peer-claimed by ${peer_sid}")
      elif [[ "$lb_hit" -eq 1 ]]; then
        DENY_PATHS+=("$ap"); DENY_REASONS+=("load-bearing")
      elif [[ -n "$peer_sid" ]]; then
        DENY_PATHS+=("$ap"); DENY_REASONS+=("peer-claimed by ${peer_sid}")
      fi
    done

    [[ "${#DENY_PATHS[@]}" -eq 0 ]] && continue

    # --- Build deny message. Cap shown paths at 8. ---
    local SHOWN_COUNT="${#DENY_PATHS[@]}"
    local SHOWN="" i
    for ((i = 0; i < SHOWN_COUNT && i < 8; i++)); do
      SHOWN="${SHOWN}  ${DENY_PATHS[$i]} (${DENY_REASONS[$i]})
"
    done
    local MORE_TEXT=""
    if [[ "$SHOWN_COUNT" -gt 8 ]]; then
      MORE_TEXT="
  ... and $((SHOWN_COUNT - 8)) more (first 8 shown)"
    fi

    local VERB_LABEL="git ${VERB}"
    [[ "$VERB" == "reset" ]] && VERB_LABEL="git reset --hard"
    [[ "$VERB" == "stash" ]] && VERB_LABEL="git stash -u/-a (unscoped)"

    local SAFE_PATH=""
    case "$VERB" in
      checkout|restore)
        SAFE_PATH="Did you mean to scope this to your own paths?
  git checkout -- <your-paths>
  git restore -- <your-paths>

Preserve first (recoverable stash of everything, including untracked):
  git stash push -u -m \"before-revert\" -- <paths>" ;;
      reset)
        SAFE_PATH="Preserve first (recoverable stash), then reset:
  git stash push -u -m \"before-reset\"
  git reset --hard" ;;
      stash)
        SAFE_PATH="Scope the stash to your own paths instead of sweeping everything untracked:
  git stash push -u -m \"before-stash\" -- <your-paths>" ;;
    esac

    _gr_deny "BLOCKED: '${VERB_LABEL}' would discard ${SHOWN_COUNT} uncommitted tracked/untracked file(s) that git CANNOT recover (unstaged edits to tracked files, and untracked files, live in no commit, no stash, no reflog — there is no recovery path once this completes):
${SHOWN}${MORE_TEXT}

${SAFE_PATH}

Or: ${_GR_OVERRIDE_HINT}"
    return

  done <<< "$SEGMENTS"

  # No covered destructive revert (or all segments evaluated as safe) -> allow.
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

  check_destructive_git_revert "$CMD" ""
  exit 0
fi
