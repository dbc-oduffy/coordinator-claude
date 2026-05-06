#!/bin/bash
# PreToolUse hook: Blocks branch creation/switch operations that would put the
# main checkout on anything other than today's daily branch or main.
# Also blocks git commit on off-daily branches (defence-in-depth; was Check 6
# in validate-commit.sh, consolidated here by Patrik F11 review).
#
# Doctrine: coordinator/CLAUDE.md § Concurrent-EM Git Operations —
# "Branch naming: work/{machine}/{YYYY-MM-DD}, always. One branch per machine
# per day per project. main is read-only (PR-only); no other branches in the
# main checkout."
#
# Postmortem source: 2026-05-05 X:/project-rag branch-sprawl & orphan-stashes
# (checkout -b feature/X + stash + checkout - produces empty branches and
# orphan stashes by construction). Real-time prevention; no /workday-complete
# cleanup.
#
# Escape hatch: COORDINATOR_OVERRIDE_BRANCH=1 (logged). Used by /workday-start,
# /merge-to-main, /consolidate-git, and any other skill that legitimately needs
# to operate off-daily.
#
# Shared lib: coordinator/lib/coordinator-daily-branch.sh
#   cs_compute_machine, cs_compute_today_daily_lc, cs_is_allowed_branch
#
# Input schema (PreToolUse for Bash):
#   { "tool_name": "Bash", "tool_input": { "command": "..." }, "session_id": "..." }
#
# Deny mechanism: JSON permissionDecision per pretooluse-deny-contract.md.

# Safe stdin read — timeout prevents hang on Windows/Git Bash.
# Must run BEFORE the override check so SESSION_ID + COMMAND are available for
# the audit log. (Review: patrik F12 — override log was anaemic without them.)
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Parse command and session_id — prefer jq, fall back to sed.
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Honor escape hatch before any work.
# Log override with full context so the audit log is useful.
# Review: patrik F12 — mirror deny log shape: session + command + reason.
if [[ "${COORDINATOR_OVERRIDE_BRANCH:-0}" == "1" ]]; then
  GIT_ROOT_FOR_LOG=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$GIT_ROOT_FOR_LOG" ]]; then
    LOG_DIR="$GIT_ROOT_FOR_LOG/.git/coordinator-sessions/_branch-overrides"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
    REASON="${COORDINATOR_OVERRIDE_BRANCH_REASON:-unspecified}"
    echo "${TS} | OVERRIDE | session=${SESSION_ID} | command=${COMMAND} | reason=${REASON}" \
      >> "$LOG_DIR/overrides.log" 2>/dev/null || true
  fi
  exit 0
fi

# Fast exit: no command to inspect.
[[ -z "$COMMAND" ]] && exit 0

# Cheap gate — only inspect if command contains a branch-mutating git form.
# Covers: checkout/switch (create & switch), branch -m/-M/--move/-c/-C/--copy
# (rename/copy), stash branch, worktree add, git commit (Check 6 — commit on
# off-daily branch), and git -C / --git-dir cross-repo forms.
# False positives cause extra parsing below; false negatives are policy gaps.
# Review: patrik F7/F8 — extended to include --move, --copy, -c, -C, -M; F11
# — added commit; F4/F5 — added git -C / --git-dir patterns.
if ! echo "$COMMAND" | grep -qE '(\bgit[[:space:]]+(checkout|switch|branch([[:space:]]+(-m|-M|-c|-C|--move|--copy|--force-create-branch))?|stash[[:space:]]+branch|worktree[[:space:]]+add|commit)\b|\bgit[[:space:]]+(-C[[:space:]]|--git-dir|--work-tree))'; then
  exit 0
fi

# Are we in a git repo?
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
[[ -z "$GIT_ROOT" ]] && exit 0

# Skip linked worktrees — doctrine bans them, but if one exists we don't
# break it. The wiki audit catches worktree existence separately.
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || true)
case "$GIT_DIR" in
  *worktrees/*) exit 0 ;;
esac

# --- Load shared lib for MACHINE/TODAY/is_allowed_branch ---
# Review: patrik F10 — extracted shared helpers to coordinator-daily-branch.sh
# to avoid duplication between this hook and validate-commit.sh.
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-daily-branch.sh"
if [[ ! -f "$LIB_PATH" ]]; then
  LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-daily-branch.sh"
fi
if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
else
  # Fallback: inline the helpers if lib is missing (should not happen in normal install).
  cs_compute_machine() {
    if [[ -n "${COORDINATOR_MACHINE:-}" ]]; then echo "$COORDINATOR_MACHINE"; return; fi
    if [[ -n "${COMPUTERNAME:-}" ]]; then echo "$COMPUTERNAME"; return; fi
    if command -v hostname &>/dev/null; then local h; h=$(hostname 2>/dev/null | sed 's/\..*//'
); [[ -n "$h" ]] && echo "$h" && return; fi
    echo "${HOSTNAME:-unknown}"
  }
  cs_compute_today_daily_lc() {
    local machine today
    machine=$(cs_compute_machine); today=$(date +%Y-%m-%d)
    echo "work/${machine}/${today}" | tr '[:upper:]' '[:lower:]'
  }
  cs_is_allowed_branch() {
    local lc daily_lc
    lc=$(echo "$1" | tr '[:upper:]' '[:lower:]')
    daily_lc=$(cs_compute_today_daily_lc)
    [[ "$lc" == "main" ]] && return 0; [[ "$lc" == "$daily_lc" ]] && return 0; return 1
  }
fi

# Local aliases for readability in this script.
MACHINE=$(cs_compute_machine)
TODAY=$(date +%Y-%m-%d)
DAILY_LC=$(cs_compute_today_daily_lc)

# --- Helpers ---

# is_allowed_branch <name> — delegates to shared lib cs_is_allowed_branch.
is_allowed_branch() {
  cs_is_allowed_branch "$1"
}

# is_local_branch <name> — true iff refs/heads/<name> exists.
is_local_branch() {
  git -C "$GIT_ROOT" show-ref --verify --quiet "refs/heads/$1" 2>/dev/null
}

# emit_deny <reason> — write JSON deny to stdout, log, exit 0 (so JSON is parsed).
emit_deny() {
  local reason="$1"
  local target="$2"

  # Per-session log (best-effort).
  if [[ -n "$SESSION_ID" ]]; then
    LOG_DIR="$GIT_ROOT/.git/coordinator-sessions/$SESSION_ID"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
    echo "${TS} | DENY | target=${target} | command=${COMMAND}" \
      >> "$LOG_DIR/branch-discipline.log" 2>/dev/null || true
  fi

  local full_reason
  full_reason="BLOCKED: off-daily branch operation."$'\n\n'
  full_reason+="  Command: ${COMMAND}"$'\n'
  full_reason+="  Target:  ${target}"$'\n'
  full_reason+="  Allowed: work/${MACHINE}/${TODAY} (today's daily) or main (read-only)"$'\n\n'
  full_reason+="${reason}"$'\n\n'
  full_reason+="To park WIP without a sibling branch:"$'\n'
  full_reason+="  • commit on the daily (intentionally messy commits are fine on work/*)"$'\n'
  full_reason+="  • git stash push -u -m \"<subject>\" (do NOT change branches first)"$'\n\n'
  full_reason+="Override: COORDINATOR_OVERRIDE_BRANCH=1 (logged). Use only inside skills"$'\n'
  full_reason+="that legitimately need off-daily ops (/workday-start, /merge-to-main, /consolidate-git)."

  if command -v jq &>/dev/null; then
    jq -nc --arg reason "$full_reason" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: $reason
      }
    }'
  else
    local esc="${full_reason//\\/\\\\}"
    esc="${esc//\"/\\\"}"
    esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

# --- F4/F5: Deny git -C / --git-dir / cd-then-git cross-repo forms ---
# Review: patrik F4/F5 — these forms evade the parser and allow off-daily
# branch ops in sibling repos. Minimum viable: deny outright when followed by
# a branch-mutating subcommand. Legitimate cross-repo work uses the override.

# Detect cd <path> && git <branch-op> chains.
if echo "$COMMAND" | grep -qE 'cd[[:space:]]+[^&;|]+(&&|;)[[:space:]]*git[[:space:]]+(checkout|switch|branch|stash[[:space:]]+branch|worktree)'; then
  emit_deny \
    "Cross-directory 'cd && git' branch op is not parsed; use COORDINATOR_OVERRIDE_BRANCH=1 if intentional." \
    "cd-then-git"
fi

# Detect git -C <path> / --git-dir / --work-tree global flags before subcommand.
# We check for these flags appearing in the raw command string alongside a branch-mutating subcommand.
if echo "$COMMAND" | grep -qE '\bgit[[:space:]]+(-C[[:space:]]|--git-dir[=[:space:]]|--work-tree[=[:space:]])'; then
  # Only deny if a branch-mutating subcommand follows anywhere in the command.
  if echo "$COMMAND" | grep -qE '(checkout|switch|branch|stash[[:space:]]+branch|worktree[[:space:]]+add)'; then
    emit_deny \
      "git -C / --git-dir cross-repo branch op is not parsed; use COORDINATOR_OVERRIDE_BRANCH=1 if intentional." \
      "git-C-or-git-dir"
  fi
fi

# --- Parse the command. Tokenise, then handle each shape. ---
# Strip leading/chained-prefix (handles "&& git checkout -b foo" etc.).
# We process the FIRST git-branch-op found; chained subsequent ops will be
# inspected on the next Bash hook invocation if they survive (but most chains
# fail-fast). Good enough for the documented anti-pattern.

# Use bash word splitting on the original command. Intentional: preserves shell
# semantics for our purposes. Quoted branch names with spaces are a non-concern
# (git refnames cannot contain spaces).
# shellcheck disable=SC2206
TOKENS=( $COMMAND )

# strip_quotes <token> — remove surrounding single or double quotes.
# Review: patrik F2 — TOKENS=( $COMMAND ) embeds surrounding quotes in each
# token; `git checkout -b "feature/foo"` tokenises as `"feature/foo"`, which
# fails the case-insensitive allow-list comparison.
strip_quotes() {
  local t="$1"
  # Strip surrounding double-quotes.
  t="${t%\"}"
  t="${t#\"}"
  # Strip surrounding single-quotes.
  t="${t%\'}"
  t="${t#\'}"
  echo "$t"
}

# Walk tokens, find the relevant git op.
i=0
n=${#TOKENS[@]}
while (( i < n )); do
  tok="${TOKENS[$i]}"
  case "$tok" in
    git)
      sub="${TOKENS[$((i+1))]:-}"
      # Review: patrik F4 — skip past git global flags (-C, --git-dir, etc.)
      # before reading the subcommand. These were already denied above, but the
      # parser guard here prevents false-allows if the deny somehow doesn't fire.
      while [[ "$sub" == -C || "$sub" == --git-dir* || "$sub" == --work-tree* ]]; do
        i=$((i+1))
        # If -C or --git-dir takes a separate value token, skip that too.
        case "$sub" in
          -C|--git-dir|--work-tree) i=$((i+1)) ;;
        esac
        sub="${TOKENS[$((i+1))]:-}"
      done

      case "$sub" in
        checkout|switch)
          # Find the operative argument.
          # Forms:
          #   git checkout -b <new> [<start>]
          #   git checkout -B <new> [<start>]
          #   git switch  -c <new> [<start>]
          #   git switch  -C <new> [<start>]
          #   git checkout --orphan <name>
          #   git checkout -
          #   git switch -
          #   git checkout <branch>
          #   git switch <branch>
          #   git checkout -- <path>      (allow — file restore)
          #   git checkout <ref> -- <path> (allow — file restore from ref)
          #   git checkout <sha|tag>      (allow — detached / non-branch)

          # File-restore form: contains a literal '--' token after checkout.
          for ((j=i+1; j<n; j++)); do
            [[ "${TOKENS[$j]}" == "--" ]] && exit 0
          done

          # Look for create flags, --detach, --orphan, and the '-' form.
          create_target=""
          switch_target=""
          for ((j=i+2; j<n; j++)); do
            t=$(strip_quotes "${TOKENS[$j]}")
            case "$t" in
              -b|-B|-c|-C)
                create_target=$(strip_quotes "${TOKENS[$((j+1))]:-}")
                break
                ;;
              --detach)
                # Detached HEAD — allow; commit-time check catches commits there.
                exit 0
                ;;
              --orphan)
                # Review: patrik F3 — --orphan <name> creates a real branch ref.
                # Check the name; allow only if it matches today's daily or main.
                orphan_name=$(strip_quotes "${TOKENS[$((j+1))]:-}")
                if [[ -z "$orphan_name" ]]; then
                  emit_deny "--orphan requires a branch name." "--orphan (no name)"
                fi
                if is_allowed_branch "$orphan_name"; then
                  exit 0
                fi
                emit_deny "--orphan '$orphan_name' creates an off-daily branch ref." "$orphan_name"
                ;;
              -)
                # Switch to previous branch — resolve and validate.
                prev=$(git -C "$GIT_ROOT" rev-parse --abbrev-ref '@{-1}' 2>/dev/null || true)
                if [[ -z "$prev" || "$prev" == "@{-1}" ]]; then
                  # No previous branch known; allow and let runtime fail.
                  exit 0
                fi
                # Review: patrik F6 — if abbrev-ref returned a raw SHA, the
                # previous HEAD was detached, not a branch. Emit a clear message.
                if echo "$prev" | grep -qE '^[0-9a-f]{7,40}$'; then
                  emit_deny \
                    "Previous HEAD was detached (not a branch); refusing to switch back into off-daily state." \
                    "$prev"
                fi
                if is_allowed_branch "$prev"; then
                  exit 0
                fi
                emit_deny "Previous branch '$prev' is not today's daily." "$prev"
                ;;
              -*)
                # Other flags (--quiet, --force, etc.) — keep scanning.
                continue
                ;;
              *)
                # First non-flag positional arg is the target.
                switch_target="$t"
                break
                ;;
            esac
          done

          if [[ -n "$create_target" ]]; then
            if is_allowed_branch "$create_target"; then
              exit 0
            fi
            emit_deny "Creating off-daily branch '$create_target' is forbidden." "$create_target"
          fi

          if [[ -n "$switch_target" ]]; then
            # Is it a local branch? If not, it's a sha/tag/remote-ref — allow.
            if ! is_local_branch "$switch_target"; then
              # Could be a remote-tracking spec like origin/foo — allow as
              # those produce detached HEAD. Commit-time check catches commits there.
              exit 0
            fi
            if is_allowed_branch "$switch_target"; then
              exit 0
            fi
            emit_deny "Switching to off-daily branch '$switch_target' is forbidden." "$switch_target"
          fi

          # No target found — allow (likely just `git checkout` with no args, harmless).
          exit 0
          ;;
        branch)
          # Review: patrik F7/F8 — extend to cover long-form rename/copy flags.
          # Forms: git branch -m/-M/--move/-c/-C/--copy [<old>] <new>
          # When any create/rename/copy flag is present, scan remaining positionals
          # and apply is_allowed_branch to the new name (last positional).
          has_create_flag=0
          new=""
          for ((j=i+2; j<n; j++)); do
            t=$(strip_quotes "${TOKENS[$j]}")
            case "$t" in
              -m|-M|--move)
                has_create_flag=1
                ;;
              -c|-C|--copy)
                has_create_flag=1
                ;;
              --force)
                # Combinator flag — keep scanning.
                ;;
              -*)
                # Other flags — keep scanning.
                ;;
              *)
                # Positional — accumulate; last one is the new name.
                new="$t"
                ;;
            esac
          done
          if [[ "$has_create_flag" == "1" && -n "$new" ]] && ! is_allowed_branch "$new"; then
            emit_deny "Renaming/copying branch to off-daily name '$new' is forbidden." "$new"
          fi
          exit 0
          ;;
        stash)
          # Form: git stash branch <name> [<stash>]
          if [[ "${TOKENS[$((i+2))]:-}" == "branch" ]]; then
            new=$(strip_quotes "${TOKENS[$((i+3))]:-}")
            if [[ -n "$new" ]] && ! is_allowed_branch "$new"; then
              emit_deny "Materialising stash onto off-daily branch '$new' is forbidden." "$new"
            fi
          fi
          exit 0
          ;;
        worktree)
          # Form: git worktree add <path> [<branch>] / -b <new>
          # Doctrine bans worktrees outright. Surface the ban.
          if [[ "${TOKENS[$((i+2))]:-}" == "add" ]]; then
            emit_deny "Worktrees are forbidden by doctrine (mise-en-place: \"No worktrees. Ever.\")." "worktree"
          fi
          exit 0
          ;;
        commit)
          # Review: patrik F11 — Check 6 (defence-in-depth at commit time) consolidated
          # here from validate-commit.sh. One hook for branch discipline (creation,
          # switch, commit); one hook for commit-content validation (validate-commit.sh
          # checks 1-5). Catches the "session inherited a stale-day branch" case.
          CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
          if [[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "HEAD" ]]; then
            CURRENT_LC=$(echo "$CURRENT_BRANCH" | tr '[:upper:]' '[:lower:]')
            if [[ "$CURRENT_LC" != "$DAILY_LC" ]]; then
              REASON_C6="BLOCKED: commit on off-daily branch."$'\n\n'
              REASON_C6+="  Current branch: ${CURRENT_BRANCH}"$'\n'
              REASON_C6+="  Today's daily:  work/${MACHINE}/${TODAY}"$'\n\n'
              REASON_C6+="The coordinator doctrine requires commits to land on today's daily branch."$'\n'
              if [[ "$CURRENT_LC" == "main" ]]; then
                REASON_C6+="main is PR-only; never commit directly."$'\n'
              elif echo "$CURRENT_BRANCH" | grep -qE '^work/[^/]+/[0-9]{4}-[0-9]{2}-[0-9]{2}'; then
                REASON_C6+="If this branch is yesterday's daily or older, run /workday-start to roll forward."$'\n'
                REASON_C6+="If you've crossed midnight in a long session, run /workday-start to roll the daily forward."$'\n'
              else
                REASON_C6+="If you've crossed midnight in a long session, run /workday-start to roll the daily forward."$'\n'
              fi
              REASON_C6+=$'\n'
              REASON_C6+="Override: COORDINATOR_OVERRIDE_BRANCH=1 (logged). Use only inside skills"$'\n'
              REASON_C6+="that legitimately commit off-daily (/workday-start, /merge-to-main, /consolidate-git)."

              if command -v jq &>/dev/null; then
                jq -nc --arg reason "$REASON_C6" '{
                  hookSpecificOutput: {
                    hookEventName: "PreToolUse",
                    permissionDecision: "deny",
                    permissionDecisionReason: $reason
                  }
                }'
              else
                ESC_C6=${REASON_C6//\\/\\\\}
                ESC_C6=${ESC_C6//\"/\\\"}
                ESC_C6=${ESC_C6//$'\n'/\\n}
                printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$ESC_C6"
              fi
              exit 0
            fi
          fi
          # On correct branch — allow.
          exit 0
          ;;
      esac
      ;;
  esac
  i=$((i+1))
done

exit 0
