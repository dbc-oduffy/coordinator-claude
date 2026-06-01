#!/bin/bash
# PreToolUse hook: Blocks branch creation/switch operations that would put the
# main checkout on anything other than an allowed workstream branch or main.
#
# Spec backlink: docs/plans/2026-05-07-daily-branch-doctrine-rethink.md (Phase 2)
#
# The hook polices branch *shape*, not branch *date*. Allowed workstream branches:
#   work/{machine}/{date-or-span}   (e.g. work/striker/2026-05-07 or work/striker/2026-05-06to07)
#   main                            (read-only, PR-only)
# Policy oracle is cs_is_allowed_branch in coordinator-daily-branch.sh.
#
# Commit-time branch enforcement (formerly Check 6, consolidated here by the Staff Engineer F11)
# was REMOVED 2026-05-07 per PM call. See docs/wiki/daily-branch-discipline.md.
# The orphan-branch-creation prevention (checkout -b, branch -m, stash branch,
# worktree add, --orphan) remains unchanged.
#
# Postmortem source: 2026-05-05 X:/project-rag branch-sprawl & orphan-stashes
# (checkout -b feature/X + stash + checkout - produces empty branches and
# orphan stashes by construction). Real-time prevention; no /workday-complete
# cleanup.
#
# Escape hatch: COORDINATOR_OVERRIDE_BRANCH=1 (logged). Used by /workday-start,
# /merge-to-main, /consolidate-git, and any other skill that legitimately needs
# to operate off-branch.
#
# Shared lib: coordinator/lib/coordinator-daily-branch.sh
#   cs_compute_machine, cs_is_allowed_branch
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
# Two override surfaces (logged identically):
#   (a) shell-env: COORDINATOR_OVERRIDE_BRANCH=1 exported into the hook's env
#       (Claude Code propagates exported env vars; rare in EM workflows)
#   (b) inline: `COORDINATOR_OVERRIDE_BRANCH=1 <command>` prefix on the user's
#       command — captured in $COMMAND because PreToolUse hooks see the literal
#       string before bash evaluates it. Required because inline env-var
#       prefixes do NOT propagate into the hook subprocess (the hook is a
#       child of Claude Code, not of the user's bash command).
# Review: patrik F12 — mirror deny log shape: session + command + reason.
INLINE_OVERRIDE=0
if [[ "$COMMAND" =~ (^|[[:space:]\;\&])COORDINATOR_OVERRIDE_BRANCH=1([[:space:]]|$) ]]; then
  INLINE_OVERRIDE=1
fi
if [[ "${COORDINATOR_OVERRIDE_BRANCH:-0}" == "1" ]] || [[ "$INLINE_OVERRIDE" == "1" ]]; then
  GIT_ROOT_FOR_LOG=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$GIT_ROOT_FOR_LOG" ]]; then
    LOG_DIR="$GIT_ROOT_FOR_LOG/.git/coordinator-sessions/_branch-overrides"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
    REASON="${COORDINATOR_OVERRIDE_BRANCH_REASON:-unspecified}"
    SOURCE=$([[ "$INLINE_OVERRIDE" == "1" ]] && echo "inline" || echo "env")
    echo "${TS} | OVERRIDE(${SOURCE}) | session=${SESSION_ID} | command=${COMMAND} | reason=${REASON}" \
      >> "$LOG_DIR/overrides.log" 2>/dev/null || true
  fi
  exit 0
fi

# Fast exit: no command to inspect.
[[ -z "$COMMAND" ]] && exit 0

# Cheap gate — only inspect if command contains a branch-mutating git form.
# Covers: checkout/switch (create & switch), branch -m/-M/--move/-c/-C/--copy
# (rename/copy), stash branch, worktree add, and git -C / --git-dir cross-repo
# forms ONLY when followed by a mutating subcommand.
# Note: 'commit' is intentionally absent — commit-time branch enforcement was
# decommissioned 2026-05-07 per PM call (plan Phase 2).
# False positives cause extra parsing below; false negatives are policy gaps.
# Review: patrik F7/F8 — extended to include --move, --copy, -c, -C, -M;
# F4/F5 — added git -C / --git-dir patterns; BS-2026-05-06-002 — tightened
# git -C / --git-dir gate to mutating subcommands only.
#
# Spec backlink: archive/handoffs/2026-05-08_143000_post-split-cleanup-followups-2.md
# § "New Followups Surfaced This Session — Cheap-gate over-match on bare branch keyword"
#
# The second arm uses ([^|;&-]|-[^-]|--[^[:space:]])* instead of [^|;&]* to prevent
# crossing a `--` pathspec separator. The old [^|;&]* would match tokens like
# "status -- plans/branch-thing.md" and trigger on "branch" inside the pathspec.
# The new character class allows: non-separator/non-dash chars, single-dash flags
# (-C, -q, etc.), and long flags (--git-dir=..., --work-tree=...) but STOPS at
# a bare " -- " separator (space + double-dash + space), which is the POSIX pathspec
# boundary. This preserves all true-positive mutating subcommand detection while
# eliminating false positives from read-only git ops with branch-named pathspecs.
if ! echo "$COMMAND" | grep -qE '(\bgit[[:space:]]+(checkout|switch|branch([[:space:]]+(-m|-M|-c|-C|--move|--copy|--force-create-branch))?|stash[[:space:]]+branch|worktree[[:space:]]+add)\b|\bgit[[:space:]]+(-C[[:space:]]|--git-dir[=[:space:]]|--work-tree[=[:space:]])([^|;&-]|-[^-]|--[^[:space:]])*\b(checkout|switch|branch|stash[[:space:]]+branch|worktree[[:space:]]+add)\b)'; then
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

# --- Load shared lib for MACHINE/is_allowed_branch ---
# Review: patrik F10 — extracted shared helpers to coordinator-daily-branch.sh
# to avoid duplication between this hook and validate-commit.sh.
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-daily-branch.sh"
if [[ ! -f "$LIB_PATH" ]]; then
  LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh"
fi
if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
else
  # Fallback: inline the helpers if lib is missing (should not happen in normal install).
  # Mirrors coordinator-daily-branch.sh — keep in sync if lib changes.
  # Drift-check (the Staff Engineer R-code follow-up): the inline copy below is a manual
  # mirror. Whenever cs_compute_machine / cs_parse_branch_span / cs_is_allowed_branch /
  # cs_is_canonical_branch change in the lib, update the fallback below in the
  # same commit. Verification: diff the lib body against the function bodies
  # below; they should be byte-equal (sans the 'cs_' prefix unification).
  cs_compute_machine() {
    local m
    if [[ -n "${COORDINATOR_MACHINE:-}" ]]; then m="$COORDINATOR_MACHINE"
    elif [[ -n "${COMPUTERNAME:-}" ]]; then m="$COMPUTERNAME"
    elif command -v hostname &>/dev/null; then m=$(hostname 2>/dev/null | sed 's/\..*//')
    else m="${HOSTNAME:-unknown}"
    fi
    echo "${m:-unknown}" | tr '[:upper:]' '[:lower:]'
  }
  cs_parse_branch_span() {
    local name="$1"
    local lc
    lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')
    if ! echo "$lc" | grep -qE '^work/[^/]+/[0-9]{4}-[0-9]{2}-[0-9]{2}(to[0-9]{2})?$'; then return 1; fi
    local date_part
    date_part=$(echo "$lc" | sed 's|^work/[^/]*/||')
    local sy sm sd
    sy="${date_part:0:4}"; sm="${date_part:5:2}"; sd="${date_part:8:2}"
    if (( 10#$sm < 1 || 10#$sm > 12 )); then return 1; fi
    if (( 10#$sd < 1 || 10#$sd > 31 )); then return 1; fi
    if echo "$date_part" | grep -qE 'to[0-9]{2}$'; then
      local ed
      ed=$(echo "$date_part" | sed 's/.*to//')
      local ey em
      if (( 10#$ed < 10#$sd )); then
        if (( 10#$sm == 12 )); then ey=$(( 10#$sy + 1 )); em="01"
        else ey="$sy"; em=$(printf '%02d' $(( 10#$sm + 1 ))); fi
      else ey="$sy"; em="$sm"; fi
      echo "${sy}-${sm}-${sd} ${ey}-${em}-${ed}"
    else
      echo "${sy}-${sm}-${sd} ${sy}-${sm}-${sd}"
    fi
    return 0
  }
  cs_is_allowed_branch() {
    local lc
    lc=$(echo "$1" | tr '[:upper:]' '[:lower:]')
    [[ "$lc" == "main" ]] && return 0
    cs_parse_branch_span "$lc" > /dev/null 2>&1 && return 0
    return 1
  }
  cs_is_canonical_branch() {
    local name="$1"
    cs_is_allowed_branch "$name" || return 1
    local lc
    lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')
    [[ "$name" == "$lc" ]]
  }
fi

# Local aliases for readability in this script.
MACHINE=$(cs_compute_machine)

# --- Helpers ---

# is_allowed_branch <name> — delegates to shared lib cs_is_allowed_branch.
# Used by switch-to-existing arms (allows mixed-case so the migration script can
# switch into a non-canonical branch and rename it).
is_allowed_branch() {
  cs_is_allowed_branch "$1"
}

# is_canonical_branch <name> — delegates to shared lib cs_is_canonical_branch.
# Used by branch-CREATION arms (checkout -b/-B, switch -c/-C, branch -m/-c,
# stash branch, --orphan). Fail-closed on mixed-case to prevent the HEAD
# vs on-disk canonical-case mismatch class on Windows.
is_canonical_branch() {
  cs_is_canonical_branch "$1"
}

# emit_canonical_hint <name> — if name is allowed-shape but non-canonical,
# echo the canonical form for inclusion in a deny-message. Empty string otherwise.
emit_canonical_hint() {
  local name="$1"
  cs_is_allowed_branch "$name" || { echo ""; return; }
  cs_is_canonical_branch "$name" && { echo ""; return; }
  echo "$name" | tr '[:upper:]' '[:lower:]'
}

# is_local_branch <name> [<root>] — true iff refs/heads/<name> exists in <root>.
# When <root> is omitted, defaults to $GIT_ROOT (same-repo behaviour).
# The optional root argument supports cross-repo forms (git -C <path>) where
# op_repo_root is captured from the -C flag during the global-flag skip loop.
is_local_branch() {
  local name="$1"
  local root="${2:-$GIT_ROOT}"
  git -C "$root" show-ref --verify --quiet "refs/heads/$name" 2>/dev/null
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
  full_reason="BLOCKED: off-workstream branch operation."$'\n\n'
  full_reason+="  Command: ${COMMAND}"$'\n'
  full_reason+="  Target:  ${target}"$'\n'
  full_reason+="  Allowed: work/${MACHINE}/{date-or-span} or main (read-only)"$'\n\n'
  full_reason+="${reason}"$'\n\n'
  # Case-canonical hint: if target is shape-valid but non-canonical, suggest the
  # lowercase form. Prevents the HEAD vs on-disk case-mismatch class on Windows
  # (autopush silent-failure root cause, 2026-05-07).
  local canonical_hint
  canonical_hint=$(emit_canonical_hint "$target")
  if [[ -n "$canonical_hint" ]]; then
    full_reason+="Canonical form: ${canonical_hint}"$'\n'
    full_reason+="  Try: git checkout -b ${canonical_hint}"$'\n\n'
  fi
  full_reason+="To park WIP without a sibling branch:"$'\n'
  full_reason+="  • commit on the active workstream branch (intentionally messy commits are fine on work/*)"$'\n'
  full_reason+="  • git stash push -u -m \"<subject>\" (do NOT change branches first)"$'\n\n'
  full_reason+="Override: COORDINATOR_OVERRIDE_BRANCH=1 (logged). Use only inside skills"$'\n'
  full_reason+="that legitimately need off-branch ops (/workday-start, /merge-to-main, /consolidate-git)."

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

# --- F4/F5 (form-split relaxation, 2026-05-08): Cross-repo branch-op policy ---
# Spec backlink: ~/.claude/plans/2026-05-08-daily-branch-discipline-cross-repo.md
#
# KEPT (cd && git): The hook subprocess captures $GIT_ROOT once from the
# *original* cwd. A `cd` before the git invocation changes directory in the
# user's shell but not here — policy checks would run against the wrong repo's
# refs/heads. This form continues to require COORDINATOR_OVERRIDE_BRANCH=1.
#
# RELAXED (git -C / --git-dir): The global-flag skip at the parser loop
# (below) already strips -C / --git-dir flags before tokenising the subcommand.
# The threat model is *shape*, not *location* — the parser's is_canonical_branch
# / is_allowed_branch oracles apply identically regardless of which repo is
# targeted. The F4/F5 outright deny was belt-on-working-suspenders; removing it
# lets the parser's shape policy apply cross-repo.

# Detect cd <path> && git <branch-op> chains — KEEP deny, parser cannot track
# post-cd cwd. Use COORDINATOR_OVERRIDE_BRANCH=1 for legitimate cd-then-git ops.
if echo "$COMMAND" | grep -qE 'cd[[:space:]]+[^&;|]+(&&|;)[[:space:]]*git[[:space:]]+(checkout|switch|branch|stash[[:space:]]+branch|worktree)'; then
  emit_deny \
    "Cross-directory 'cd && git' branch op is not parsed; the hook captures GIT_ROOT at entry and cannot follow the cd. Use COORDINATOR_OVERRIDE_BRANCH=1 if intentional." \
    "cd-then-git"
fi

# git -C / --git-dir forms: fall through to the parser below. The global-flag
# skip loop captures any -C <path> value into op_repo_root for use in
# is_local_branch and @{-1} resolution.

# --- Parse the command. Tokenise, then handle each shape. ---
# Strip leading/chained-prefix (handles "&& git checkout -b foo" etc.).
# We process the FIRST git-branch-op found; chained subsequent ops will be
# inspected on the next Bash hook invocation if they survive (but most chains
# fail-fast). Good enough for the documented anti-pattern.

# Use bash word splitting on the original command. Intentional: preserves shell
# semantics for our purposes. Quoted branch names with spaces are a non-concern
# (git refnames cannot contain spaces).
# set -f disables glob expansion so metacharacters in COMMAND (*/?/[...]) are
# not expanded during tokenisation — without it, a branch name like "fix/*"
# would be subject to pathname expansion before the array is built.
# shellcheck disable=SC2206
set -f
TOKENS=( $COMMAND )
set +f

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

# is_separator <token> — true if the token is a shell command/pipeline
# separator. The per-arm positional scans below MUST stop at the first
# separator: tokens after it belong to a DIFFERENT command in a compound, and
# attributing their flags/positionals to the git op produces false positives.
#
# Postmortem (2026-05-31): `git branch --contains <sha> | grep -C 0 foo && echo
# "NO-not-yet-in-HEAD"` was blocked because the unbounded branch-arm scan read
# grep's `-C` (context-lines) as `git branch -C` (copy) and the echoed string
# as the rename target. A read-only ancestry check got a false rename deny.
# Bounding each scan to the git op's own segment closes that class.
#
# Covers, as standalone word-split tokens: && || ; | (list/pipe operators),
# |& (pipe-with-stderr), & (background), and ;; (case-arm terminator — guards a
# git op embedded in a `case` body from scanning into the next arm). None of
# these can appear mid-argument, so none can prematurely truncate a legitimate
# single git command's args.
is_separator() {
  case "$1" in
    '&&'|'||'|';'|';;'|'|'|'|&'|'&') return 0 ;;
    *) return 1 ;;
  esac
}

# Walk tokens, find the relevant git op.
i=0
n=${#TOKENS[@]}
# op_repo_root: the repo root the current git invocation targets.
# Default is $GIT_ROOT (same-repo). Overridden to the -C <path> value when the
# global-flag skip loop sees a -C flag. Used in is_local_branch and @{-1}
# resolution so cross-repo forms validate against the correct repo's refs/heads.
op_repo_root="$GIT_ROOT"
while (( i < n )); do
  tok="${TOKENS[$i]}"
  # Reset op_repo_root for each new git token encountered.
  op_repo_root="$GIT_ROOT"
  case "$tok" in
    git)
      sub="${TOKENS[$((i+1))]:-}"
      # Review: patrik F4 — skip past git global flags (-C, --git-dir, etc.)
      # before reading the subcommand.
      # Spec (2026-05-08 form-split relaxation): capture -C <path> into
      # op_repo_root so downstream arms (switch-target is_local_branch,
      # @{-1} resolution) query the correct sibling repo's refs/heads.
      while [[ "$sub" == -C || "$sub" == --git-dir* || "$sub" == --work-tree* ]]; do
        i=$((i+1))
        # If -C or --git-dir takes a separate value token, skip that too.
        # Capture the value for op_repo_root resolution.
        case "$sub" in
          -C)
            # -C <path>: the value is the next token.
            op_repo_root="${TOKENS[$((i+1))]:-$GIT_ROOT}"
            i=$((i+1))
            ;;
          --git-dir|--work-tree)
            # --git-dir <path> or --work-tree <path>: skip the value token.
            # op_repo_root stays as $GIT_ROOT for --git-dir (we'd need dirname
            # on the .git path to resolve the work-tree root; not worth the
            # complexity — cross-repo shape check still applies on the branch name).
            i=$((i+1))
            ;;
          --git-dir=*|--work-tree=*)
            # --git-dir=<path>: value is embedded; no extra skip needed.
            ;;
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
          # Stop at a separator — a '--' in a later command is not ours.
          # Start at i+2 to skip the already-known subcommand token.
          for ((j=i+2; j<n; j++)); do
            is_separator "${TOKENS[$j]}" && break
            [[ "${TOKENS[$j]}" == "--" ]] && exit 0
          done

          # Look for create flags, --detach, --orphan, and the '-' form.
          create_target=""
          switch_target=""
          for ((j=i+2; j<n; j++)); do
            # Stop at a separator — the rest of the compound is a different op.
            is_separator "${TOKENS[$j]}" && break
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
                # Check the name; allow only if it's a canonical workstream branch.
                # Creation arm: canonical-case oracle (case-fragile push prevention).
                orphan_name=$(strip_quotes "${TOKENS[$((j+1))]:-}")
                if [[ -z "$orphan_name" ]]; then
                  emit_deny "--orphan requires a branch name." "--orphan (no name)"
                fi
                if is_canonical_branch "$orphan_name"; then
                  exit 0
                fi
                emit_deny "--orphan '$orphan_name' creates an off-daily or non-canonical-case branch ref." "$orphan_name"
                ;;
              -)
                # Switch to previous branch — resolve and validate.
                # Use op_repo_root so cross-repo `git -C <path> switch -`
                # queries the sibling repo's reflog, not $GIT_ROOT.
                prev=$(git -C "$op_repo_root" rev-parse --abbrev-ref '@{-1}' 2>/dev/null || true)
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
            # Creation arm: canonical-case oracle (case-fragile push prevention).
            if is_canonical_branch "$create_target"; then
              exit 0
            fi
            emit_deny "Creating off-daily or non-canonical-case branch '$create_target' is forbidden." "$create_target"
          fi

          if [[ -n "$switch_target" ]]; then
            # Is it a local branch? If not, it's a sha/tag/remote-ref — allow.
            # Pass op_repo_root so cross-repo forms (git -C <path> checkout main)
            # look up the branch ref in the sibling repo, not $GIT_ROOT.
            if ! is_local_branch "$switch_target" "$op_repo_root"; then
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
            # Stop at a separator — flags/positionals past it belong to a
            # different command (e.g. a piped `grep -C` is not `git branch -C`).
            is_separator "${TOKENS[$j]}" && break
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
          # Creation arm (rename/copy materialises a new ref): canonical-case oracle.
          if [[ "$has_create_flag" == "1" && -n "$new" ]] && ! is_canonical_branch "$new"; then
            emit_deny "Renaming/copying branch to off-daily or non-canonical-case name '$new' is forbidden." "$new"
          fi
          exit 0
          ;;
        stash)
          # Form: git stash branch <name> [<stash>]
          if [[ "${TOKENS[$((i+2))]:-}" == "branch" ]]; then
            new=$(strip_quotes "${TOKENS[$((i+3))]:-}")
            # If the name slot holds a separator (e.g. `git stash branch && ...`),
            # there is no branch name — the command is malformed-but-harmless, not
            # a creation. Exit rather than denying on the separator token.
            is_separator "$new" && exit 0
            # Creation arm: canonical-case oracle.
            if [[ -n "$new" ]] && ! is_canonical_branch "$new"; then
              emit_deny "Materialising stash onto off-daily or non-canonical-case branch '$new' is forbidden." "$new"
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
        # commit) arm intentionally absent — commit-time branch enforcement
        # decommissioned 2026-05-07 per PM call. See plan Phase 2 and
        # docs/wiki/daily-branch-discipline.md.
      esac
      ;;
  esac
  i=$((i+1))
done

exit 0
