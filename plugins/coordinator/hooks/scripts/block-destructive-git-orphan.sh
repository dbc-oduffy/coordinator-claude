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
# same class as block-off-daily-branch.sh): `cd <dir> && git …` and the env-prefix
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

set -uo pipefail

# Resolve a python interpreter once (python3 preferred); empty if neither exists.
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

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

# Join backslash-newline line continuations so a single op split across lines is
# evaluated as one segment (`git reset \<newline>  --hard HEAD~5`).
# NOTE: a newline var is required — `$'\n'` does NOT expand inside the
# double-quoted ${//} replacement, so an inline `${CMD//\\$'\n'/ }` is a silent no-op.
NL=$'\n'
CMD="${CMD//\\$NL/ }"

# Fast bail: nothing to do unless this is a git command.
echo "$CMD" | grep -qE '\bgit\b' || exit 0

# Escape hatch (honored early, before any git work).
[[ "${COORDINATOR_ALLOW_ORPHAN:-0}" == "1" ]] && exit 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Strip a single layer of surrounding single/double quotes from a token.
strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

# Form-A deny emitter.
deny() {
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

OVERRIDE_HINT="If this is genuinely intended, export COORDINATOR_ALLOW_ORPHAN=1 in your environment first (an inline prefix on the git command does NOT reach this hook)."

# ---------------------------------------------------------------------------
# Evaluate each command segment independently. Separators ; && || | & all
# collapse to newlines (we only need to ISOLATE commands, not preserve operator
# semantics). Erring toward MORE segments = more checks, never fewer.
# ---------------------------------------------------------------------------
SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

while IFS= read -r SEG; do
  [[ -z "${SEG//[[:space:]]/}" ]] && continue
  echo "$SEG" | grep -qE '\bgit\b' || continue

  # Per-segment repo resolution: honor `git -C <dir>` (quote-stripped), else cwd.
  GOPT=()
  SEGDIR=$(echo "$SEG" | grep -oE 'git[[:space:]]+-C[[:space:]]+[^[:space:]]+' | head -1 | awk '{print $3}')
  SEGDIR=$(strip_q "$SEGDIR")
  [[ -n "$SEGDIR" ]] && GOPT=(-C "$SEGDIR")

  # -------------------------------------------------------------------------
  # CHECK 1 — git reset --hard <target>  (the 2026-05-28 near-miss shape)
  # -------------------------------------------------------------------------
  if echo "$SEG" | grep -qE '\breset\b' && echo "$SEG" | grep -qE -- '--hard'; then
    AFTER=$(echo "$SEG" | sed -E 's/.*\breset\b//')

    # Unverifiable target (subshell): cannot resolve without running it -> deny safe.
    if echo "$AFTER" | grep -qE '\$\(|`'; then
      deny "BLOCKED: 'git reset --hard' with a subshell-resolved target ($(...) or backticks) cannot be verified safe — the hook will not execute the subshell to learn what it points at.

Resolve the ref to a literal first and re-check what it would drop:
  git rev-list --count <resolved-ref>..HEAD

${OVERRIDE_HINT}"
    fi

    # Pathspec form (reset --hard <ref> -- <path>) does NOT move HEAD; git in fact
    # rejects --hard with paths. Either way it cannot orphan commits -> allow.
    if echo "$AFTER" | grep -qE '(^|[[:space:]])--([[:space:]]|$)'; then
      :
    else
      # Collect bare (non-flag) tokens, quote-stripped. reset --hard takes at most
      # ONE commit; a 2nd bare token makes the command invalid (--hard + paths) so
      # it cannot orphan anything -> allow.
      bare=()
      for tok in $AFTER; do
        case "$tok" in
          -*) continue ;;
          *)  bare+=("$(strip_q "$tok")") ;;
        esac
      done
      if [[ "${#bare[@]}" -le 1 ]]; then
        TARGET="${bare[0]:-HEAD}"
        if git "${GOPT[@]}" rev-parse --verify "${TARGET}^{commit}" &>/dev/null; then
          N=$(git "${GOPT[@]}" rev-list --count "${TARGET}..HEAD" 2>/dev/null || echo 0)
          if [[ "${N:-0}" =~ ^[0-9]+$ && "${N:-0}" -gt 0 ]]; then
            CUR_BRANCH=$(git "${GOPT[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
            SUBJECTS=$(git "${GOPT[@]}" log --format='  - %h %s' "${TARGET}..HEAD" 2>/dev/null | head -5)
            MORE=""
            [[ "$N" -gt 5 ]] && MORE="
  ... and $((N - 5)) more"
            deny "BLOCKED: 'git reset --hard ${TARGET}' would drop ${N} commit(s) from branch '${CUR_BRANCH}'.

These commits are reachable from HEAD but NOT from ${TARGET}, so the reset orphans them:
${SUBJECTS}${MORE}

This is the 2026-05-28 near-miss shape: a hard reset to a ref that is BEHIND your current work. Before overriding, re-derive the TRUE state yourself (do not trust a remembered count):
  git rev-list --count ${TARGET}..HEAD   # commits you would lose; must be 0 to be safe
  git branch -a --contains HEAD          # other refs that already hold this work

If those ${N} commits are genuinely disposable (or provably safe on another ref), ${OVERRIDE_HINT}"
          fi
        fi
      fi
    fi
  fi

  # -------------------------------------------------------------------------
  # CHECK 2 — force push: plain --force, bundled short -f (e.g. -uf), or a
  # leading-'+' refspec (git push origin +main). --force-with-lease is allowed.
  # -------------------------------------------------------------------------
  if echo "$SEG" | grep -qE '\bpush\b'; then
    if echo "$SEG" | grep -qE '(--force([^-=]|$)|(^|[[:space:]])-[a-zA-Z]*f[a-zA-Z]*([[:space:]]|$)|(^|[[:space:]"'\''])\+[^[:space:]]+)'; then
      deny "BLOCKED: this 'git push' uses a forcing form (--force / -f / +refspec) that rewrites remote history and can drop commits existing only on the remote (a concurrent push you have not fetched).

Use --force-with-lease instead. It refuses the push if the remote moved since your last fetch — exactly the protection plain --force discards:
  git push <remote> <branch> --force-with-lease

${OVERRIDE_HINT}"
    fi
  fi

  # -------------------------------------------------------------------------
  # CHECK 3 — force-delete a branch: -D, bundled -rD, --delete+--force in any
  # order, OR lowercase -d/--delete combined with -f/--force.
  # -------------------------------------------------------------------------
  if echo "$SEG" | grep -qE '\bbranch\b'; then
    FORCE_DELETE=0
    # Uppercase -D bundle (e.g. -D, -rD) => force-delete by itself.
    if echo "$SEG" | grep -qE '(^|[[:space:]])-[a-zA-Z]*D[a-zA-Z]*([[:space:]]|$)'; then
      FORCE_DELETE=1
    fi
    # Lowercase delete flag AND a force flag (any order, separate or combined).
    if echo "$SEG" | grep -qE '((^|[[:space:]])-[a-zA-Z]*d[a-zA-Z]*([[:space:]]|$)|--delete)' \
       && echo "$SEG" | grep -qE '((^|[[:space:]])-[a-zA-Z]*f[a-zA-Z]*([[:space:]]|$)|--force)'; then
      FORCE_DELETE=1
    fi
    if [[ "$FORCE_DELETE" == "1" ]] && git "${GOPT[@]}" rev-parse --git-dir &>/dev/null; then
      AFTER=$(echo "$SEG" | sed -E 's/.*\bbranch\b//')
      for tok in $AFTER; do
        case "$tok" in
          -*) continue ;;
          *)
            BR=$(strip_q "$tok")
            git "${GOPT[@]}" rev-parse --verify "refs/heads/${BR}" &>/dev/null || continue
            OTHERS=$(git "${GOPT[@]}" branch -a --contains "refs/heads/${BR}" --format='%(refname)' 2>/dev/null \
                      | grep -vxF "refs/heads/${BR}" \
                      | grep -v 'refs/remotes/[^/]*/HEAD' \
                      | head -1)
            if [[ -z "$OTHERS" ]]; then
              deny "BLOCKED: force-deleting branch '${BR}' would orphan its commits — they live on NO other ref (no local branch, no remote).

'${BR}' is not contained in any other branch or remote. The lowercase, non-forced 'git branch -d' refuses exactly this case; the force form ('-D', or '-d --force') overrides that safety.

To preserve the work first:
  git checkout <target> && git merge ${BR}

If '${BR}' is truly disposable, ${OVERRIDE_HINT}"
            fi
            ;;
        esac
      done
    fi
  fi

done <<< "$SEGMENTS"

# No covered destructive op (or all evaluated as safe) -> allow.
exit 0
