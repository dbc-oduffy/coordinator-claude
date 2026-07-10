#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks `git clean` that would destroy untracked
# load-bearing deliverables on a shared work/* branch — files that live in no
# commit, no stash, and no reflog, making destruction irrecoverable.
#
# Motivation: sibling to block-destructive-git-orphan.sh (committed-work loss
# class) and block-destructive-rm.sh (uncommitted-rm loss class). This hook
# closes the UNCOMMITTED-clean loss class — the third leg of the safety floor.
#
# 2026-06-30 project-rag incident: a sibling session running a workstream-
# complete ceremony issued `git clean -fd` on the shared work/* branch. Eight
# untracked spinoff handoff files (state/handoffs/*-handoff-*.md) that a
# concurrent session had just written but not yet committed were destroyed.
# Because they were untracked, git reflog, git stash, and git checkout are all
# silent — there is no recovery path once git clean completes. This hook
# closes that surface at the tool boundary, independent of anything the model
# believes about the working tree state.
#
# Sibling guards:
#   block-destructive-git-orphan.sh — committed-work loss (reset --hard / force-push / branch -D)
#   block-destructive-rm.sh         — uncommitted-rm loss (rm -rf on dirty trees)
#   block-destructive-git-clean.sh  — uncommitted-clean loss (this file)
#
# Trigger scope (deliberately narrow):
#   - Only `git clean` (as a command verb, tolerating git global options
#     between `git` and `clean`). Dry-run invocations (`-n`/`--dry-run`) are
#     ALLOWED — they delete nothing.
#   - `clean.requireForce=false` repos are covered — the hook does NOT require
#     `-f` to be present before running the oracle. The oracle classifies what
#     would be removed regardless of whether force is needed in that repo.
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
# Override: export COORDINATOR_OVERRIDE_GIT_CLEAN=1 in the environment (NOT
# an inline prefix — that sets the var for the git child, not this hook
# process).
#
# Sourceable interface (check_destructive_git_clean):
#   source block-destructive-git-clean.sh
#   check_destructive_git_clean "$cmd" "$session_id"
# When sourced, only the function and file-scope helpers are defined; no stdin
# is read and no logic executes at source time. On DENY, the function prints
# the nested hookSpecificOutput JSON to stdout and returns. On allow, it
# prints nothing and returns 0.
#
# KNOWN v1 limitations (classify each as fail-open or fail-safe):
#   - Literal `git clean` at command position only — fail OPEN. Aliased forms
#     (`git cls` if `cls` maps to clean in .gitconfig), shell functions that
#     call git clean internally, and git aliases defined with `git config
#     alias.*` are NOT detected.
#   - Wrapped/grouped/quoted-verb forms: `(git clean …)`, `{ git clean …; }`,
#     `\git clean`, `'git' clean`, `! git clean` ARE covered via the leading-
#     opener peeler in _gc_is_clean_segment. `bash -c 'git clean …'` / `eval`
#     ARE covered via the shell-invoker broad fallback. Execution-wrapper class
#     (sudo git clean, command git clean, env git clean, time git clean, etc.)
#     ARE covered. RESIDUAL not covered: `$(which git) clean` — the subshell
#     resolves `which git` at runtime; the hook sees an unresolved token and
#     does NOT match — fail OPEN.
#   - `cd <dir> && git clean` — oracle is evaluated against the hook's own cwd
#     (parity with block-destructive-rm.sh § cd limitation). The `cd` target
#     is not followed — fail OPEN.
#   - `git -C <dir> clean` IS handled: the oracle mirrors `-C <dir>` so the
#     scope matches the real clean — fail SAFE.
#   - `git -C "path with spaces" clean` — the -C path extractor uses whitespace
#     tokenization; quoted multi-token paths are not handled. The oracle runs
#     against the hook's cwd instead — fail OPEN for that segment.
#   - `timeout` binary absent (macOS BSD without GNU coreutils): the oracle
#     runs without a time cap — fail OPEN for the *timeout* case only (large
#     -x trees may stall). The load-bearing deny still functions — fail SAFE.
#   - `$VAR`/glob pathspec targets (e.g. `git clean -fd -- $SOMEPATH`) are
#     passed literally to the oracle. git sees the unexpanded token, fails or
#     matches nothing, and the hook allows — fail OPEN for these targets.
#   - Multi-segment commands (`;`, `&&`, `||`, `|`, `&`) are handled via
#     segment split — each segment is evaluated independently — fail SAFE.
#   - `clean.requireForce=false` not separately detected; the always-run-oracle
#     design covers the destructive outcome regardless of whether `-f` is
#     present — fail SAFE.
#   - Oracle timeout (2 s): large `-x` trees scanning all untracked+ignored
#     files may stall. On timeout the hook DENIES — fail SAFE. Use
#     COORDINATOR_OVERRIDE_GIT_CLEAN=1 after manual verification in that case.
#   - PowerShell `git clean` invocations are not covered — fail OPEN (Bash
#     hook only; the dispatcher receives Bash tool calls).
#   - Ancestor-directory collapse IS handled (fail SAFE): when `git clean -nd`
#     reports a shallow directory (e.g. `docs/`) that is an ancestor of a
#     load-bearing prefix (e.g. `docs/plans`), the two-direction classifier
#     catches it — both "P under LB" (regex) and "LB under P" (prefix-list
#     bash string check) directions are covered.

set -uo pipefail

# Source the coordinator state-root seam for dynamic load-bearing path resolution (L2 fix).
# Guarded — no-op if the lib is absent (partial install, pre-C2 checkout).
# coordinator-state-root.sh is idempotent (safe to source multiple times).
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § L2/C4
_gc_CSR_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)/lib/coordinator-state-root.sh"
if [[ -f "$_gc_CSR_LIB" ]]; then
  # shellcheck source=../../lib/coordinator-state-root.sh
  source "$_gc_CSR_LIB" 2>/dev/null || true
fi
unset _gc_CSR_LIB

# ---------------------------------------------------------------------------
# File-scope constants and helpers — _gc_-prefixed to avoid name collisions
# when this file is sourced alongside sibling hooks:
#   block-destructive-rm.sh         uses _rm_-prefixed names
#   block-destructive-git-orphan.sh uses _orphan_-prefixed names
# ---------------------------------------------------------------------------

# Load-bearing path classifier: a would-remove path from `git clean -nd` is
# load-bearing if it matches any of these patterns.
#
# Cross-reference: the canonical load-bearing surface is defined in
# ~/.claude/CLAUDE.md § "state/ vs tasks/" and the coordinator CLAUDE.md §
# "state/ vs tasks/". This regex must stay in sync with that surface definition.
#
# Deliberately EXCLUDED: tasks/<feature>/todo.md — these are load-bearing-by-
# convention but classified as ephemera (aggressive-sweep zone) per the
# coordinator doctrine § state/ vs tasks/. The exclusion is structural, not an
# oversight. A tasks/<feature>/flight/<chunk>.md sidecar is also ephemera-classed.
_gc_LOADBEARING_RE='(^|/)state(/|$)|(^|/)docs/plans(/|$)|(^|/)docs/decisions(/|$)|(^|/)docs/wiki(/|$)|(^|/)docs/research(/|$)|(^|/)cross-repo/(inbox|archive|outbox)(/|$)|-handoff.*\.md$|(^|/)completion(/|$)|review-trail/.*\.json$'
# Review: code-reviewer — F3: anchored `completion` to (^|/)completion(/|$) so bare
# substrings like scripts/tab-completion.sh no longer trigger a false deny.

# Explicit directory-form load-bearing prefixes — parallel to the directory
# alternatives in _gc_LOADBEARING_RE, but used for the ANCESTOR-direction
# check (BUG 3): a would-remove path P is also load-bearing when P is an
# ANCESTOR of a load-bearing directory (e.g. "docs" is an ancestor of
# "docs/plans"). Pure bash `==` / glob checks cover this without grep.
# Filename-glob alternatives (-handoff*.md, completion, review-trail) are
# file-only paths and cannot be ancestors of load-bearing dirs — excluded.
# Cross-reference: must mirror the dir-form entries in _gc_LOADBEARING_RE.
_gc_LOADBEARING_PREFIXES=(
  "state"
  "docs/plans"
  "docs/decisions"
  "docs/wiki"
  "docs/research"
  "cross-repo/inbox"
  "cross-repo/archive"
  "cross-repo/outbox"
)

# Anchored command-position regex for `git clean` — mirrors _RM_CMD_RE from
# block-destructive-rm.sh. The leading `^` ensures `git` is at COMMAND POSITION
# (not a data occurrence inside `echo "git clean"`, `grep "git clean" f`, etc.).
# Allows optional execution-wrapper prefixes (sudo/env/...) and optional bare
# VAR=val env-assignment prefixes before `git`, plus an optional full path prefix
# (/usr/bin/) on the `git` binary. Git global options between `git` and `clean`
# are explicitly enumerated so a stray `git ... clean` in arg-position (e.g. an
# arg to grep that happens to contain "git" and "clean") does NOT match here —
# the global-opts list is closed, so an intervening non-option word breaks it.
# Wrapper class (sudo/env/...) and shell-invoker (bash -c/eval) also appear in
# the earlier dedicated branches in _gc_is_clean_segment; their presence in this
# regex is defense-in-depth (mirrors _RM_CMD_RE structure exactly).
_gc_CLEAN_CMD_RE='^[[:space:]]*((sudo|command|time|exec|nice|nohup|ionice|timeout|stdbuf|which|type)[[:space:]]+|env[[:space:]]+([^[:space:]]+=[^[:space:]]*[[:space:]]+)*|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(/[^[:space:]]*/)?git([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|--(git-dir|work-tree|namespace)(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)|--exec-path(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)?|-p|--paginate|--no-pager|--bare|--no-replace-objects|--literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs|--no-optional-locks))*[[:space:]]+clean\b'

# Override hint text — references COORDINATOR_OVERRIDE_GIT_CLEAN.
_GC_OVERRIDE_HINT="If this git clean is genuinely intended, export COORDINATOR_OVERRIDE_GIT_CLEAN=1 in your environment first (an inline prefix on the git command does NOT reach this hook). Verify what would be lost first: git clean -nd [your flags]"

# Emit the deny JSON to stdout. Does NOT call exit — the caller must `return`
# immediately after this so check_destructive_git_clean returns to its caller.
# Uses _GC_PY (set by check_destructive_git_clean at entry; stored without
# `local` so this file-scope function can read it).
_gc_deny() {
  local reason="$1"
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "${_GC_PY:-}" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "${_GC_PY}" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
}

# Detect whether a single command SEGMENT invokes `git clean` as a command
# verb. Returns 0 if so. Mirrors _rm_is_rm_segment from block-destructive-rm.sh,
# adapted for the `git [global-opts] clean` verb form.
_gc_is_clean_segment() {
  local seg="$1" probe prev=""
  # Peel LEADING group/subshell/negation/backslash openers + whitespace, so a
  # verb wrapped as `(git clean …)`, `{ git clean …`, `! git clean`, or
  # `\git clean` is detected. Only the LEADING opener is peeled — a `$(...)`
  # appearing later (e.g. a pathspec subshell) is left intact. Iterate; openers
  # can nest (`( { git clean …`).
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
  # Strip quote chars for command-word detection so a quoted verb ('git'/"git")
  # and a shell-invoker payload (bash -c 'git clean …') read as commands.
  # Target extraction below still uses the original $SEG, so quoted targets are
  # unaffected.
  probe="${seg//\'/}"; probe="${probe//\"/}"
  # Shell-invoker broad fallback: bash/sh/zsh/dash -c, or eval — the payload
  # EXECUTES, so a broad scan for `git … clean` in the payload is correct and
  # only fires for these invokers, never for grep/ls/echo (preserving the
  # quoted-arg false-positive fix from the rm sibling).
  if printf '%s' "$probe" | grep -qE '^(bash|sh|zsh|dash)[[:space:]]+([^[:space:]]+[[:space:]]+)*-c([[:space:]]|$)|^eval([[:space:]]|$)'; then
    printf '%s' "$probe" | grep -qE '\bgit\b.*\bclean\b' && return 0
    return 1
  fi
  # Execution-wrapper / verb-resolver class: sudo, command, time, exec, nice,
  # nohup, env, ionice, timeout, stdbuf, which, type. A `git` token after any
  # of these, followed eventually by `clean`, is a real git clean — even behind
  # wrapper flags a position-anchored regex cannot track (`sudo -u root git clean`,
  # `env -i git clean`, `nice -n 10 git clean`).
  local firstword="${seg%%[[:space:]]*}"
  case "$firstword" in
    sudo|command|time|exec|nice|nohup|env|ionice|timeout|stdbuf|which|type)
      printf '%s' "$seg" | grep -qE '\bgit\b.*\bclean\b' && return 0
      return 1 ;;
  esac
  # Direct command position: `git [global-opts] clean` anchored to `^`.
  # Uses $_gc_CLEAN_CMD_RE (file-scope constant, defined above) which mirrors
  # _RM_CMD_RE from block-destructive-rm.sh. The `^` anchor is the fix for
  # the false-positive: `echo "git clean -fd"` reaches this branch with probe
  # = "echo git clean -fd"; without `^` the \bgit match fires mid-string and
  # produces an erroneous DENY; with `^` the regex requires git (or a VAR=val/
  # wrapper prefix) at the START, so "echo ..." does not match → ALLOW (correct).
  printf '%s' "$probe" | grep -qE "$_gc_CLEAN_CMD_RE"
}

# ---------------------------------------------------------------------------
# check_destructive_git_clean <command> <session_id>
#
# Contains ALL decision logic for the destructive-git-clean guard. Prints the
# nested hookSpecificOutput deny JSON to stdout when a covered destructive
# git clean is detected; prints nothing and returns 0 on allow.
#
# $2 (session_id) is accepted for dispatcher interface compatibility but is
# not used by the current implementation — resolution is driven by oracle
# output, not session identity.
# ---------------------------------------------------------------------------
check_destructive_git_clean() {
  # $2 (session_id) accepted for interface compat; not used.

  # Resolve python interpreter; stored WITHOUT `local` so the file-scope
  # _gc_deny can read it. Idempotent on repeated calls.
  _GC_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  local CMD="$1"

  # Normalize CRLF -> LF. On Windows/Git-Bash the native jq.exe emits its
  # output in text mode, injecting a CR before every LF, so a command carrying
  # a real newline reaches this function as `\<CR><LF>` (backslash CR LF), not
  # `\<LF>`. A bare CR is never a meaningful shell token, so stripping every CR
  # is safe and makes the whole function CRLF-robust — without it the segment
  # split below silently misses any continuation on Windows, disabling this
  # guard for a multi-line `git clean -fd <tree>` on that platform.
  # (Matches the CR-strip in block-destructive-rm.sh — kept consistent.)
  CMD="${CMD//$'\r'/}"

  # Join backslash-newline continuations so a split op is one segment.
  local NL=$'\n'
  CMD="${CMD//\\$NL/ }"

  # Part A: Strip heredoc bodies — git clean inside a heredoc literal is not
  # executed and must not be scanned. Handles <<WORD, <<'WORD', <<"WORD",
  # <<-WORD. The awk block is verbatim from block-destructive-rm.sh
  # (hook-agnostic). Fail-safe: if mktemp or awk is unavailable CMD is
  # unchanged — may produce a recoverable false-deny.
  local _BDGC_AWK _BDGC_STRIPPED _BDGC_RC
  _BDGC_AWK=$(mktemp 2>/dev/null || true)
  if [[ -n "$_BDGC_AWK" ]]; then
    cat > "$_BDGC_AWK" << 'BDGC_AWK_EOF'
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
BDGC_AWK_EOF
    _BDGC_STRIPPED=$(printf '%s' "$CMD" | awk -f "$_BDGC_AWK"); _BDGC_RC=$?
    rm -f "$_BDGC_AWK"
    # Fail-safe: awk exits 2 if it ended inside an unterminated heredoc.
    # Discard the strip and keep the original CMD — a stuck stripper must
    # never silently swallow a real trailing git clean.
    [[ "$_BDGC_RC" -eq 0 ]] && CMD="$_BDGC_STRIPPED"
  fi

  # Part B fast bail: nothing to do unless both `git` and `clean` appear.
  # Precise command-verb discrimination (quoted-arg vs verb, wrappers) happens
  # per-segment in the main loop via _gc_is_clean_segment — these two broad
  # checks are a cheap pre-filter.
  printf '%s' "$CMD" | grep -qE '\bgit\b' || return 0
  printf '%s' "$CMD" | grep -qE '\bclean\b' || return 0

  # Escape hatch (honored early, before segment loop).
  [[ "${COORDINATOR_OVERRIDE_GIT_CLEAN:-0}" == "1" ]] && return 0

  # --- Seam-resolved state root for Direction 3 load-bearing check (L2 fix). ---
  # Computed once per function call and reused across lb_path iterations.
  # coordinator_state_root is available when coordinator-state-root.sh was sourced at
  # file scope (above); absent on partial installs → Directions 1+2 still cover the
  # literal relative state/ path. After migration the seam resolves to an absolute
  # example-orchestration-hub path that Direction 2's pure-string ancestor checks cannot match.
  local _gc_seam_state_root=""
  if command -v coordinator_state_root &>/dev/null; then
    _gc_seam_state_root=$(coordinator_state_root 2>/dev/null || true)
  fi

  # --- Evaluate each command segment independently. Separators ; && || | &
  # collapse to newlines; erring toward MORE segments = more checks, never
  # fewer. ---
  local SEGMENTS
  SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

  local SEG
  while IFS= read -r SEG; do
    [[ -z "${SEG//[[:space:]]/}" ]] && continue

    # Must invoke git clean as a command verb (wrapped/grouped/quoted-verb
    # forms and shell-invoker payloads all handled by _gc_is_clean_segment).
    _gc_is_clean_segment "$SEG" || continue

    # --- Parse flags from this segment for oracle mirroring. ---

    # Extract git -C <dir> if present (oracle must run against the same dir).
    # Only the LAST -C dir is extracted (mirrors how git resolves multiple -C).
    local GIT_C_DIR=""
    GIT_C_DIR=$(printf '%s' "$SEG" \
      | grep -oE '\bgit([[:space:]]+[^[:space:]]+)*[[:space:]]+-C[[:space:]]+[^[:space:]]+' \
      | grep -oE '[-]C[[:space:]]+[^[:space:]]+' \
      | sed 's/[-]C[[:space:]]*//' \
      | tail -n 1 2>/dev/null || true)

    # Extract tokens AFTER the `clean` subcommand word.
    # BSD sed's ERE lacks \b (GNU-only extension); use the [[:space:]]-boundary
    # idiom so this strips the verb identically on BSD and GNU. `\bclean\b` was a
    # silent NO-OP on BSD sed (DR-148 audit, 2026-07-10).
    local AFTER_CLEAN=""
    AFTER_CLEAN=$(printf '%s' "$SEG" | sed -E 's/.*(^|[[:space:]])clean([[:space:]]|$)/ /')

    # Dry-run passthrough: -n (bundled like -nd/-nfd) or --dry-run deletes
    # nothing — allow this segment.
    if printf '%s' "$AFTER_CLEAN" | grep -qE '(^|[[:space:]])-[a-zA-Z]*n[a-zA-Z]*([[:space:]]|$)|(^|[[:space:]])--dry-run([[:space:]]|$)'; then
      continue
    fi

    # --- Build oracle argument list to mirror this segment's flags. ---
    # Oracle runs the same clean in dry-run mode so the scope matches exactly.
    # Review: code-reviewer — F2: -c color.ui=never suppresses ANSI color escape
    # codes regardless of the user's color.ui=always setting. LC_ALL=C alone does
    # not suppress color; without this guard a colored "Would remove " line never
    # matches the prefix check, causing silent fail-OPEN.
    local -a ORACLE_ARGS=("-c" "color.ui=never")

    # Mirror -C <dir>: oracle must scope to the same directory as the real clean.
    if [[ -n "$GIT_C_DIR" ]]; then
      ORACLE_ARGS+=("-C" "$GIT_C_DIR")
    fi

    ORACLE_ARGS+=("clean" "-nd")

    # Mirror -x (remove gitignored too) or -X (only gitignored), mutually
    # exclusive — -X takes priority if both appear (git's own behavior).
    if printf '%s' "$AFTER_CLEAN" | grep -qE '(^|[[:space:]])-[a-zA-Z]*X[a-zA-Z]*([[:space:]]|$)'; then
      ORACLE_ARGS+=("-X")
    elif printf '%s' "$AFTER_CLEAN" | grep -qE '(^|[[:space:]])-[a-zA-Z]*x[a-zA-Z]*([[:space:]]|$)'; then
      ORACLE_ARGS+=("-x")
    fi

    # Mirror every -e <pattern> exclude so the oracle scope matches exactly.
    local e_pat=""
    while IFS= read -r e_pat; do
      [[ -n "$e_pat" ]] && ORACLE_ARGS+=("-e" "$e_pat")
    done < <(printf '%s' "$AFTER_CLEAN" \
      | grep -oE '([-]e[[:space:]]+[^[:space:]]+|--exclude=[^[:space:]]+)' \
      | sed -E 's/^[-]e[[:space:]]*//; s/^--exclude=//' || true)
    # Review: code-reviewer — F4: extended extractor to match --exclude=PATTERN
    # (long form) in addition to -e PATTERN (short form), so the oracle mirrors
    # both forms and does not false-deny a clean that --exclude would make safe.
    # F7: removed unnecessary 2>/dev/null from sed (sed substitution never emits
    # stderr; suppression masked genuine future failures).

    # Mirror pathspecs after `--` if present (v1: literal tokens only;
    # $VAR/glob pathspec targets are passed unexpanded — see KNOWN-LIMITATIONS).
    local PATHSPECS=""
    if printf '%s' "$AFTER_CLEAN" | grep -qE '(^|[[:space:]])--([[:space:]]|$)'; then
      PATHSPECS=$(printf '%s' "$AFTER_CLEAN" | sed -E 's/.*[[:space:]]--[[:space:]]*//')
    fi

    # --- Run the oracle (dry-run of the same clean). ---
    #
    # LC_ALL=C is MANDATORY: git clean -n output is gettext-localized; without
    # pinning the locale, a non-English locale produces "Would remove" in another
    # language and the "Would remove " parse below returns empty -> fail-OPEN.
    # LC_ALL=C pins the C locale regardless of the user's LANG/LC_ALL settings.
    #
    # timeout 2: matches the dispatcher's `timeout 2 cat` precedent. Large `-x`
    # trees scanning all untracked+ignored files can stall; 2 s is enough for a
    # normal working tree and bounds the hook's latency contribution.
    #
    # Run from the HOOK'S OWN cwd (no injected -C) UNLESS the command carries
    # -C <dir> (already in ORACLE_ARGS). Injecting -C <root> would widen scope
    # and cause false-positives for commands scoped to a subdirectory.
    # Review: code-reviewer — F1: guard timeout binary availability. macOS BSD
    # ships without GNU coreutils; bare `timeout 2 git` exits rc=127 there,
    # which the non-124 allow path (line ~397) silently allows — hook becomes a
    # no-op on that platform. An array prefix avoids quoting hazards and
    # degrades gracefully to an unbounded oracle when timeout is absent (see
    # KNOWN-LIMITATIONS — the deny logic still functions; only the time cap is
    # lost). Mirrors the `command -v timeout` guard in the stdin-read block.
    local -a _gc_timeout_prefix=()
    command -v timeout &>/dev/null && _gc_timeout_prefix=("timeout" "2")
    local ORACLE_OUT="" ORACLE_RC=0
    # noglob: unquoted $PATHSPECS undergoes pathname expansion in the hook's cwd
    # before git sees it; set -f disables that expansion so literal tokens reach
    # git unchanged.
    set -f
    # bash < 4.4 (stock macOS /bin/bash 3.2): "${arr[@]}" on an EMPTY array
    # under `set -u` is a fatal "unbound variable" that aborts the hook
    # mid-run — no deny JSON is emitted, so a destructive `git clean` is
    # SILENTLY ALLOWED (fail-open). _gc_timeout_prefix is `()` whenever the
    # `timeout` binary is absent (stock macOS BSD userland has no GNU
    # coreutils `timeout`). ${arr[@]+"${arr[@]}"} is the bash-3.2-safe idiom:
    # expands to nothing when the array is empty/unset, else the elements
    # verbatim — identical behavior to "${arr[@]}" on bash >=4.4, portable
    # down to 3.2.
    if [[ -n "$PATHSPECS" ]]; then
      ORACLE_OUT=$(LC_ALL=C ${_gc_timeout_prefix[@]+"${_gc_timeout_prefix[@]}"} git ${ORACLE_ARGS[@]+"${ORACLE_ARGS[@]}"} -- $PATHSPECS 2>/dev/null) || ORACLE_RC=$?
    else
      ORACLE_OUT=$(LC_ALL=C ${_gc_timeout_prefix[@]+"${_gc_timeout_prefix[@]}"} git ${ORACLE_ARGS[@]+"${ORACLE_ARGS[@]}"} 2>/dev/null) || ORACLE_RC=$?
    fi
    set +f

    # Timeout (rc=124): oracle could not complete — fail CLOSED. We cannot prove
    # the clean is safe; the override is available after manual verification.
    if [[ "$ORACLE_RC" -eq 124 ]]; then
      _gc_deny "BLOCKED: 'git clean' oracle timed out (2 s) — cannot verify the clean is safe. The tree may be large (try without -x first) or the repository is under load.

Safe path first — verify what would be removed, then preserve it:
  git clean -nd [your flags]             # see the would-remove list
  git stash push -u -m \"before-clean\" -- <paths>   # make it recoverable

After preserving the files, re-run the clean. Or:
${_GC_OVERRIDE_HINT}"
      return
    fi

    # Non-zero rc other than 124: not a git repo, bad -C path, git invocation
    # error, or similar. There is nothing to lose — allow silently. Do NOT
    # emit a deny; returning 0 with no output is the correct allow signal.
    [[ "$ORACLE_RC" -ne 0 ]] && continue

    # Empty oracle output: nothing would be removed — allow.
    [[ -z "$ORACLE_OUT" ]] && continue

    # --- Classify each "Would remove " line. ---
    # Parse ONLY lines beginning with the C-locale prefix "Would remove "
    # (exclude "Would skip" / "Would not remove" — these are directory-
    # traversal notices, not removal candidates).
    #
    # Two-direction symmetric safety check:
    #   Direction 1 — P is UNDER a load-bearing dir (or equals one):
    #     caught by _gc_LOADBEARING_RE (e.g. "state/handoffs/foo.md" or bare "state")
    #   Direction 2 — P is an ANCESTOR of a load-bearing dir:
    #     caught by _gc_LOADBEARING_PREFIXES bash string check (e.g. "docs" is
    #     ancestor of "docs/plans" → removing "docs/" destroys "docs/plans/")
    # Both directions must deny; omitting Direction 2 is the BUG 3 fail-OPEN.
    local -a LOADBEARING_PATHS=()
    local lb_line="" lb_path="" lb_prefix="" lb_is_bearing=0
    while IFS= read -r lb_line; do
      # Exact C-locale prefix match; "Would skip" must not match here.
      [[ "$lb_line" == "Would remove "* ]] || continue
      lb_path="${lb_line#Would remove }"
      # Strip trailing slash — git clean -nd shows directories as "Would remove dir/".
      lb_path="${lb_path%/}"
      lb_is_bearing=0
      # Direction 1: P is under (or equal to) a load-bearing dir.
      if printf '%s' "$lb_path" | grep -qE "$_gc_LOADBEARING_RE"; then
        lb_is_bearing=1
      fi
      # Direction 2: P is an ancestor of a load-bearing dir. Pure bash string
      # ops (no grep) — cross-platform and avoids any grep flag edge-cases.
      # "$lb_prefix == $lb_path" catches exact match (redundant with D1 but
      # harmless); "$lb_prefix == $lb_path/*" catches LB starting with P+"/".
      if [[ "$lb_is_bearing" -eq 0 ]]; then
        for lb_prefix in ${_gc_LOADBEARING_PREFIXES[@]+"${_gc_LOADBEARING_PREFIXES[@]}"}; do
          if [[ "$lb_prefix" == "$lb_path" || "$lb_prefix" == "$lb_path"/* ]]; then
            lb_is_bearing=1
            break
          fi
        done
      fi
      # Direction 3: seam-resolved state root (L2 fix). Fires after migration when
      # state lives in example-orchestration-hub — an absolute path outside the local repo that
      # Directions 1+2 cannot cover (D1 regex catches /state/ fragments but not an
      # ancestor path like /path/to/example-orchestration-hub; D2 prefix list uses relative "state"
      # which never matches an absolute example-orchestration-hub path). Catches both:
      #   • lb_path IS or IS UNDER the seam state root  (P ∈ state tree)
      #   • lb_path IS AN ANCESTOR of the seam state root  (P ⊃ state root →
      #     cleaning P destroys the entire example-orchestration-hub/state subtree)
      # Active only when _gc_seam_state_root is non-empty (seam lib available).
      if [[ "$lb_is_bearing" -eq 0 && -n "$_gc_seam_state_root" ]]; then
        if [[ "$lb_path" == "$_gc_seam_state_root" || "$lb_path" == "$_gc_seam_state_root"/* ]]; then
          lb_is_bearing=1
        elif [[ "$_gc_seam_state_root" == "$lb_path"/* ]]; then
          lb_is_bearing=1
        fi
      fi
      [[ "$lb_is_bearing" -eq 1 ]] && LOADBEARING_PATHS+=("$lb_path")
    done <<< "$ORACLE_OUT"

    # Nothing load-bearing would be removed — allow this segment.
    [[ "${#LOADBEARING_PATHS[@]}" -eq 0 ]] && continue

    # --- Build deny message. Cap shown paths at 8. ---
    local SHOWN_COUNT="${#LOADBEARING_PATHS[@]}"
    local SHOWN
    # Note: "${arr[@]:0:N}" (slice form) does NOT crash on an empty array
    # under bash 3.2 set -u (confirmed empirically) — only the bare
    # "${arr[@]}" form does. Left as-is; also provably non-empty here (the
    # ${#LOADBEARING_PATHS[@]} -eq 0 guard above already `continue`d).
    SHOWN=$(printf '  %s\n' "${LOADBEARING_PATHS[@]:0:8}")
    local MORE_TEXT=""
    if [[ "$SHOWN_COUNT" -gt 8 ]]; then
      MORE_TEXT="
  ... and $((SHOWN_COUNT - 8)) more (first 8 shown)"
    fi

    # Steer to the safe path FIRST; override LAST.
    _gc_deny "BLOCKED: 'git clean' would destroy ${SHOWN_COUNT} untracked load-bearing file(s) that git CANNOT recover (untracked files live in no commit, no stash, no reflog — there is no recovery path once git clean completes):
${SHOWN}${MORE_TEXT}

Safe path first — commit the work, or stash it to make it recoverable:
  git stash push -u -m \"before-clean\" -- <paths>   # recoverable stash (git stash pop restores)
  git add -- <paths> && git commit -m \"wip: save before clean\"   # commit path

After preserving the files, re-run the git clean. Or:
${_GC_OVERRIDE_HINT}"
    return

  done <<< "$SEGMENTS"

  # No covered destructive git clean (or all segments evaluated as safe) -> allow.
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

  check_destructive_git_clean "$CMD" ""
  exit 0
fi
