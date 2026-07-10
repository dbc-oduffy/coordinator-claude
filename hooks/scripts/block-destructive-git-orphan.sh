#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks git operations that would ORPHAN committed work
# (silently drop commits) unless the loss is proven safe or explicitly overridden.
#
# Motivation: 2026-05-28 near-miss. An EM, acting on corrupted/flaky tool output
# (a phantom "already merged via PR#47" premise built on SHAs that never existed),
# proposed `git reset --hard origin/main` on a branch 257 commits AHEAD of main.
# That would have orphaned a full day-plus of work. The premise was false; the
# only backstops were the PM's caution and a late manual re-check — neither of
# which the system should depend on.
#
# This hook externalizes the check. It re-derives the TRUE git state with fresh
# git commands at the tool boundary, independent of anything the model believes.
# It is the "verify the premise before the irreversible action" rule made
# load-bearing instead of advisory.
#
# Covered destructive ops (each evaluated against fresh git state in the repo):
#   1. git reset --hard <target>  -> deny if <target>..HEAD would drop >=1 commit
#   2. git push --force / -f / +refspec -> deny (steer to --force-with-lease)
#   3. git branch -D / -d --force <name> -> deny if commits live on no other ref
#
# The command is split into segments on ; && || | & (and backslash-newline line
# continuations are joined first), and EACH segment is evaluated independently —
# a safe first op never masks a destructive later op, and per-segment `git -C` is
# honored so chained cross-repo ops resolve to the right repo. Extracted tokens
# (target ref, -C dir, branch name) are quote-stripped so shell-quoted forms
# (`git reset --hard "HEAD~2"`) do not evade the check.
#
# Unverifiable targets fail SAFE (deny): a `reset --hard $(...)` / backtick target
# cannot be resolved without running the subshell, so it is denied by default.
# A pathspec reset (`reset --hard <ref> -- <path>`, or any 2nd bare token) does
# NOT move HEAD (git rejects `--hard` with paths) and is allowed.
#
# Deliberately NOT covered (v1): rebase (routine; reflog-recoverable), clean -fdx.
# KNOWN v1 limitations (evaluate against hook cwd, not the real target repo —
# same class as block-destructive-rm.sh v1 limitation): `cd <dir> && git …` and the env-prefix
# forms `GIT_DIR=<path> git …` / `GIT_WORK_TREE=<path> git …`. Explicit
# `git -C <dir>` IS resolved. TOCTOU: a concurrent session committing between this
# check and the command's execution is a millisecond window the hook cannot close.
#
# Input schema (PreToolUse for Bash):
#   { "tool_name":"Bash", "tool_input":{"command":"..."}, ... }
#
# Deny mechanism (Form A): emit {"hookSpecificOutput":{...,"permissionDecision":
# "deny",...}} to STDOUT and exit 0. Form B (stderr + exit 2) is silently
# swallowed by the runtime — see docs/wiki/hook-best-practices.md.
# Allow: exit 0 with no stdout.
#
# Override: export COORDINATOR_ALLOW_ORPHAN=1 in the environment (NOT an inline
# `COORDINATOR_ALLOW_ORPHAN=1 git …` prefix — that sets the var for the git child,
# not for this hook process, so it will NOT bypass the gate). Use it ONLY after
# you have independently confirmed the commits are safe — that confirmation is the
# entire point of this hook.
#
# Sourceable: when sourced, ONLY defines check_destructive_git_orphan() and its
# helpers; no code runs at source time. The main guard at the bottom drives the
# standalone (direct-invocation) path.

set -uo pipefail

# Resolve a python interpreter once at file scope (shared by _orphan_deny helper).
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# ---------------------------------------------------------------------------
# _orphan_strip_q — strip a single layer of surrounding single/double quotes.
# Prefixed to avoid collision when sourced alongside block-destructive-rm.sh.
# ---------------------------------------------------------------------------
_orphan_strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

# ---------------------------------------------------------------------------
# _orphan_strip_ws_quoted_spans — delete quoted spans that contain whitespace,
# leaving whitespace-free quoted tokens (`"HEAD~2"`, `'behind-2'`) untouched.
#
# WHY awk, not sed: a single-pass ERE `"[^"]*[[:space:]][^"]*"` (the prior
# implementation) is unsafe because `"` is the SAME character for open and
# close — the engine can treat one span's CLOSING quote as the next span's
# OPENING quote and vice versa, so on `"A" x "B"` it matches from A's closing
# quote through B's opening quote (` x `) and merges the two spans into
# `"AB"`. This is standard ERE backtracking, not a BSD/GNU dialect gap — it
# reproduces identically on both. The same ambiguity applies to `'...'`.
# Deleting the whole span unconditionally (`"[^"]*"`, no whitespace test)
# WOULD be span-safe (`[^"]` cannot itself contain a quote, so the match is
# always exactly one balanced pair) — but that is too aggressive: it would
# also delete whitespace-free quoted refs like `"HEAD~2"`, which the caller
# needs to survive this step and be recovered by _orphan_strip_q downstream
# (see the "reset --hard double/single-quoted ref caught" tests). The
# whitespace TEST and the SPAN-BOUNDARY test cannot both be expressed inside
# one sed match without introducing the open/close ambiguity above, so this
# helper walks the string once, char by char, pairing each quote with its
# own literal closing quote (never re-using a quote as both close-of-A and
# open-of-B), and only omits a span from the output when ITS OWN content
# contains whitespace. O(n) single pass, no backtracking, no cross-span
# merges possible by construction.
#
# An unmatched trailing quote (odd count) is left as a literal character —
# same permissive behavior as leaving malformed input alone elsewhere in
# this hook; it does not hang or error.
#
# Input is piped on STDIN (not passed via `-v`) and reassembled line-by-line
# in the awk program itself: awk's `-v var=value` assignment hard-errors
# ("newline in string") if `value` contains a literal embedded newline, which
# a multi-line quoted commit body legitimately can. Reading via the
# NR/END-accumulator pattern below handles embedded newlines natively (each
# input record becomes one line of `s`, rejoined with `\n`), which is also a
# strict improvement over the old sed call's KNOWN LIMIT (line-by-line-only
# stripping) — a multi-line quoted span is now stripped as a single unit.
# ---------------------------------------------------------------------------
_orphan_strip_ws_quoted_spans() {
  # SQ passed as its own -v (not a literal '\'' in the awk source) to avoid
  # \x27-style hex escapes, which are a GNU-awk extension and NOT POSIX/BSD
  # awk portable — DR-148 forbids relying on non-portable escape dialects.
  # The `\t`/`\n` escapes used in the bracket expression below (whitespace
  # test) were also considered for portability: escape interpretation inside
  # a bracket expression is universally supported in practice (onetrueawk,
  # gawk, mawk, busybox awk) — a different, safer guarantee than the \x27
  # hex-escape trap above, not a dialect gap.
  printf '%s' "$1" | awk -v SQ="'" '
  {
    if (NR > 1) s = s "\n" $0; else s = $0
  }
  END {
    out = ""
    n = length(s)
    i = 1
    while (i <= n) {
      c = substr(s, i, 1)
      if (c == "\"" || c == SQ) {
        q = c
        j = i + 1
        span = ""
        found = 0
        while (j <= n) {
          cj = substr(s, j, 1)
          if (cj == q) { found = 1; break }
          span = span cj
          j++
        }
        if (found) {
          if (span !~ /[ \t\n]/) {
            out = out q span q
          }
          i = j + 1
        } else {
          out = out c
          i++
        }
      } else {
        out = out c
        i++
      }
    }
    printf "%s", out
  }'
}

# ---------------------------------------------------------------------------
# _orphan_deny — Form-A deny emitter.
# Prefixed to avoid collision when sourced alongside block-destructive-rm.sh
# (which defines its own deny() helper with DIFFERENT text referencing
# COORDINATOR_ALLOW_RM). Prints the nested hookSpecificOutput JSON to stdout
# and returns; the caller is responsible for returning from the outer function.
# ---------------------------------------------------------------------------
_orphan_deny() {
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
}

# ---------------------------------------------------------------------------
# check_destructive_git_orphan <command> <session_id>
#
# Evaluates <command> (a Bash-tool command string) for destructive git
# operations that would orphan committed work. Prints Form-A deny JSON to
# stdout if denied; prints nothing and returns 0 if allowed.
#
# Per-target repo resolution is load-bearing: each command segment is
# evaluated in the repo implied by its `git -C <dir>` flag (if present),
# NOT necessarily cwd. A reset/force-push target can live in a different
# repo than cwd; this function resolves per segment exactly as the original
# standalone script did.
#
# OVERRIDE_HINT is local to this function to prevent clobbering the sibling
# hook block-destructive-rm.sh's OVERRIDE_HINT (which references
# COORDINATOR_ALLOW_RM instead of COORDINATOR_ALLOW_ORPHAN).
#
# $1 — command string (Bash tool_input.command)
# $2 — session_id (reserved for dispatcher interface; not used in logic)
# ---------------------------------------------------------------------------
check_destructive_git_orphan() {
  local CMD="$1"
  # $2 = session_id: reserved for the dispatcher interface, unused here.

  local NL SEGMENTS SEG SEGDIR AFTER TARGET N CUR_BRANCH SUBJECTS MORE FORCE_DELETE tok BR OTHERS STRIPPED
  local -a GOPT bare

  # OVERRIDE_HINT is local: block-destructive-rm.sh defines its own OVERRIDE_HINT
  # with different text (COORDINATOR_ALLOW_RM). Keeping both local prevents one
  # clobbering the other when sourced together, so the deny message always names
  # the correct env var for this hook.
  local OVERRIDE_HINT="If this is genuinely intended, export COORDINATOR_ALLOW_ORPHAN=1 in your environment first (an inline prefix on the git command does NOT reach this hook)."

  [[ -z "$CMD" ]] && return 0

  # Normalize CRLF -> LF first. On Windows/Git-Bash the native jq.exe emits its
  # output in text mode, injecting a CR before every LF, so a command carrying a
  # real newline reaches this function as `\<CR><LF>` (backslash CR LF), not
  # `\<LF>`. A bare CR is never a meaningful shell token, so stripping every CR is
  # safe and makes the whole function CRLF-robust — without it the join below (and
  # the sed/grep segmentation) silently miss any continuation on Windows, which
  # would DISABLE this guard for multi-line destructive commands on that platform.
  CMD="${CMD//$'\r'/}"

  # Join backslash-newline line continuations so a single op split across lines is
  # evaluated as one segment (`git reset \<newline>  --hard HEAD~5`).
  # NOTE: a newline var is required — `$'\n'` does NOT expand inside the
  # double-quoted ${//} replacement, so an inline `${CMD//\\$'\n'/ }` is a silent no-op.
  NL=$'\n'
  CMD="${CMD//\\$NL/ }"

  # Strip whitespace-containing quoted spans (prose / multi-word ARGUMENTS: a commit
  # message `-m "wip drop it"`, a `--body "…"` payload, etc.) BEFORE segmentation and
  # detection. A destructive git TOKEN — a ref, a branch name, `--force`/`-f`, or a
  # `+refspec` — never contains internal whitespace (git forbids whitespace in ref and
  # branch names, and flags have none), so deleting multi-word quoted spans can NEVER
  # hide a real destructive op. It only prevents the trigger patterns from matching
  # inside quoted argument text — the "guards match conditions, not containers" rule
  # (a lesson body that merely NARRATES `git push --force` must not be blocked). Short
  # quoted tokens with no internal whitespace (`"HEAD~2"`, `'+main'`) are preserved and
  # still checked. This also prevents a `;`/`&`/`|` inside a quoted message from
  # producing a bogus extra segment below.
  # Delegated to _orphan_strip_ws_quoted_spans (see its docstring above) rather
  # than an inline sed pattern: a single-pass ERE `"[^"]*[[:space:]][^"]*"`
  # merges across adjacent quoted spans (`"A" x "B"` -> `"AB"`) because `"` is
  # the SAME character for open and close, so the match can start at one
  # span's CLOSING quote and end at the next span's OPENING quote — confirmed
  # bug, 2026-07-10, root-caused against the chained `git -C '<dir>' status &&
  # git -C '<dir>' reset --hard HEAD~2` case, which corrupted BOTH `-C` args
  # into one garbage token and let the destructive reset through UNCHECKED
  # (fail-open). Reproduces identically on BSD and GNU sed — not a dialect
  # gap. The awk helper handles multi-line quoted spans as a bonus (see its
  # docstring); the old line-by-line KNOWN LIMIT no longer applies.
  #
  # Fail-toward-deny, not fail-open, if the strip can't run: `awk` was already
  # a SOFT dependency in this file (below, `-C` dir extraction — a missing awk
  # there only degrades to cwd, non-fatal). Making it a HARD dependency here
  # would be catastrophic — if `awk` is absent or errors, the strip would
  # produce empty stdout, `CMD` would be unconditionally blanked, and the
  # `grep -qE '\bgit\b'` fast-bail below would then ALLOW every command,
  # including an entirely-unquoted `git reset --hard HEAD~2` that never
  # needed quote-stripping. Skip the strip entirely when `awk` is unavailable
  # (leave CMD unstripped — quoted prose may over-trigger a later check, the
  # safe failure mode) and never accept an empty-strip result over a
  # non-empty input (same reasoning, for a runtime awk fault).
  if command -v awk &>/dev/null; then
    STRIPPED=$(_orphan_strip_ws_quoted_spans "$CMD")
    [[ -n "$STRIPPED" || -z "$CMD" ]] && CMD="$STRIPPED"
  fi

  # Fast bail: nothing to do unless this is a git command.
  grep -qE '\bgit\b' <<< "$CMD" || return 0

  # Escape hatch (honored early, before any git work).
  [[ "${COORDINATOR_ALLOW_ORPHAN:-0}" == "1" ]] && return 0

  # ---------------------------------------------------------------------------
  # Evaluate each command segment independently. Separators ; && || | & all
  # collapse to newlines (we only need to ISOLATE commands, not preserve operator
  # semantics). Erring toward MORE segments = more checks, never fewer.
  # ---------------------------------------------------------------------------
  SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

  while IFS= read -r SEG; do
    [[ -z "${SEG//[[:space:]]/}" ]] && continue
    grep -qE '\bgit\b' <<< "$SEG" || continue

    # Per-segment repo resolution: honor `git -C <dir>` (quote-stripped), else cwd.
    GOPT=()
    SEGDIR=$(echo "$SEG" | grep -oE 'git[[:space:]]+-C[[:space:]]+[^[:space:]]+' | head -1 | awk '{print $3}')
    SEGDIR=$(_orphan_strip_q "$SEGDIR")
    [[ -n "$SEGDIR" ]] && GOPT=(-C "$SEGDIR")

    # -------------------------------------------------------------------------
    # CHECK 1 — git reset --hard <target>  (the 2026-05-28 near-miss shape)
    # -------------------------------------------------------------------------
    if grep -qE '\breset\b' <<< "$SEG" && grep -qE -- '--hard' <<< "$SEG"; then
      # BSD sed's ERE lacks \b (GNU-only extension); use the [[:space:]]-boundary
      # idiom (matches the -[a-zA-Z]*D[a-zA-Z]*([[:space:]]|$) pattern above) so
      # this strips the verb identically on BSD and GNU. `\breset\b` was a silent
      # NO-OP on BSD sed, leaving "reset" in $AFTER and over-counting bare tokens
      # below, which caused CHECK 1 to skip the deny entirely on macOS.
      AFTER=$(echo "$SEG" | sed -E 's/.*(^|[[:space:]])reset([[:space:]]|$)/ /')

      # Unverifiable target (subshell): cannot resolve without running it -> deny safe.
      if grep -qE '\$\(|`' <<< "$AFTER"; then
        _orphan_deny "BLOCKED: 'git reset --hard' with a subshell-resolved target ($(...) or backticks) cannot be verified safe — the hook will not execute the subshell to learn what it points at.

Resolve the ref to a literal first and re-check what it would drop:
  git rev-list --count <resolved-ref>..HEAD

${OVERRIDE_HINT}"
        return 0
      fi

      # Pathspec form (reset --hard <ref> -- <path>) does NOT move HEAD; git in fact
      # rejects --hard with paths. Either way it cannot orphan commits -> allow.
      if grep -qE '(^|[[:space:]])--([[:space:]]|$)' <<< "$AFTER"; then
        :
      else
        # Collect bare (non-flag) tokens, quote-stripped. reset --hard takes at most
        # ONE commit; a 2nd bare token makes the command invalid (--hard + paths) so
        # it cannot orphan anything -> allow.
        bare=()
        for tok in $AFTER; do
          case "$tok" in
            -*) continue ;;
            *)  bare+=("$(_orphan_strip_q "$tok")") ;;
          esac
        done
        if [[ "${#bare[@]}" -le 1 ]]; then
          TARGET="${bare[0]:-HEAD}"
          # bash < 4.4 (stock macOS /bin/bash 3.2): "${arr[@]}" on an EMPTY array
          # under `set -u` is a fatal "unbound variable" that aborts the hook
          # mid-run — no deny JSON is emitted, so the destructive command is
          # SILENTLY ALLOWED (fail-open). GOPT is `()` whenever the command has
          # no `git -C <dir>`. ${GOPT[@]+"${GOPT[@]}"} is the bash-3.2-safe idiom:
          # it expands to nothing when GOPT is empty/unset, else the elements
          # verbatim — identical behavior to "${GOPT[@]}" on bash >=4.4, portable
          # down to 3.2. Applied at every GOPT expansion in this function.
          if git ${GOPT[@]+"${GOPT[@]}"} rev-parse --verify "${TARGET}^{commit}" &>/dev/null; then
            N=$(git ${GOPT[@]+"${GOPT[@]}"} rev-list --count "${TARGET}..HEAD" 2>/dev/null || echo 0)
            if [[ "${N:-0}" =~ ^[0-9]+$ && "${N:-0}" -gt 0 ]]; then
              CUR_BRANCH=$(git ${GOPT[@]+"${GOPT[@]}"} rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
              SUBJECTS=$(git ${GOPT[@]+"${GOPT[@]}"} log --format='  - %h %s' "${TARGET}..HEAD" 2>/dev/null | head -5)
              MORE=""
              [[ "$N" -gt 5 ]] && MORE="
  ... and $((N - 5)) more"
              _orphan_deny "BLOCKED: 'git reset --hard ${TARGET}' would drop ${N} commit(s) from branch '${CUR_BRANCH}'.

These commits are reachable from HEAD but NOT from ${TARGET}, so the reset orphans them:
${SUBJECTS}${MORE}

This is the 2026-05-28 near-miss shape: a hard reset to a ref that is BEHIND your current work. Before overriding, re-derive the TRUE state yourself (do not trust a remembered count):
  git rev-list --count ${TARGET}..HEAD   # commits you would lose; must be 0 to be safe
  git branch -a --contains HEAD          # other refs that already hold this work

If those ${N} commits are genuinely disposable (or provably safe on another ref), ${OVERRIDE_HINT}"
              return 0
            fi
          fi
        fi
      fi
    fi

    # -------------------------------------------------------------------------
    # CHECK 2 — force push: plain --force, bundled short -f (e.g. -uf), or a
    # leading-'+' refspec (git push origin +main). --force-with-lease is allowed.
    # -------------------------------------------------------------------------
    if grep -qE '\bpush\b' <<< "$SEG"; then
      if grep -qE '(--force([^-=]|$)|(^|[[:space:]])-[a-zA-Z]*f[a-zA-Z]*([[:space:]]|$)|(^|[[:space:]"'\''])\+[^[:space:]]+)' <<< "$SEG"; then
        _orphan_deny "BLOCKED: this 'git push' uses a forcing form (--force / -f / +refspec) that rewrites remote history and can drop commits existing only on the remote (a concurrent push you have not fetched).

Use --force-with-lease instead. It refuses the push if the remote moved since your last fetch — exactly the protection plain --force discards:
  git push <remote> <branch> --force-with-lease

${OVERRIDE_HINT}"
        return 0
      fi
    fi

    # -------------------------------------------------------------------------
    # CHECK 3 — force-delete a branch: -D, bundled -rD, --delete+--force in any
    # order, OR lowercase -d/--delete combined with -f/--force.
    # -------------------------------------------------------------------------
    if grep -qE '\bbranch\b' <<< "$SEG"; then
      FORCE_DELETE=0
      # Uppercase -D bundle (e.g. -D, -rD) => force-delete by itself.
      if grep -qE '(^|[[:space:]])-[a-zA-Z]*D[a-zA-Z]*([[:space:]]|$)' <<< "$SEG"; then
        FORCE_DELETE=1
      fi
      # Lowercase delete flag AND a force flag (any order, separate or combined).
      if grep -qE '((^|[[:space:]])-[a-zA-Z]*d[a-zA-Z]*([[:space:]]|$)|--delete)' <<< "$SEG" \
         && grep -qE '((^|[[:space:]])-[a-zA-Z]*f[a-zA-Z]*([[:space:]]|$)|--force)' <<< "$SEG"; then
        FORCE_DELETE=1
      fi
      if [[ "$FORCE_DELETE" == "1" ]] && git ${GOPT[@]+"${GOPT[@]}"} rev-parse --git-dir &>/dev/null; then
        # BSD-portable whole-word strip; see CHECK 1 comment above for rationale
        # (same \b-in-sed NO-OP-on-BSD defect, same fix shape).
        AFTER=$(echo "$SEG" | sed -E 's/.*(^|[[:space:]])branch([[:space:]]|$)/ /')
        for tok in $AFTER; do
          case "$tok" in
            -*) continue ;;
            *)
              BR=$(_orphan_strip_q "$tok")
              git ${GOPT[@]+"${GOPT[@]}"} rev-parse --verify "refs/heads/${BR}" &>/dev/null || continue
              OTHERS=$(git ${GOPT[@]+"${GOPT[@]}"} branch -a --contains "refs/heads/${BR}" --format='%(refname)' 2>/dev/null \
                        | grep -vxF "refs/heads/${BR}" \
                        | grep -v 'refs/remotes/[^/]*/HEAD' \
                        | head -1)
              if [[ -z "$OTHERS" ]]; then
                _orphan_deny "BLOCKED: force-deleting branch '${BR}' would orphan its commits — they live on NO other ref (no local branch, no remote).

'${BR}' is not contained in any other branch or remote. The lowercase, non-forced 'git branch -d' refuses exactly this case; the force form ('-D', or '-d --force') overrides that safety.

To preserve the work first:
  git checkout <target> && git merge ${BR}

If '${BR}' is truly disposable, ${OVERRIDE_HINT}"
                return 0
              fi
              ;;
          esac
        done
      fi
    fi

  done <<< "$SEGMENTS"

  # No covered destructive op (or all evaluated as safe) -> allow.
  return 0
}

# ---------------------------------------------------------------------------
# Main guard: when invoked directly, read stdin once and drive the function.
# When sourced, only the function definitions above execute — no I/O, no side
# effects at source time.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # ---------------------------------------------------------------------------
  # Safe stdin read (timeout guard prevents hang on Windows/Git Bash)
  # ---------------------------------------------------------------------------
  if command -v timeout &>/dev/null; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
  fi

  # ---------------------------------------------------------------------------
  # Parse tool_name + command. Prefer jq; fall back to python (robust JSON);
  # sed/grep is the last resort (truncates on embedded quotes — only bites if
  # NEITHER jq nor python exists).
  # ---------------------------------------------------------------------------
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

  check_destructive_git_orphan "$CMD" ""
  exit 0
fi
