#!/usr/bin/env bash
# workday-complete-step3-consolidate.sh — Step 3 Branch Consolidation for /workday-complete.
#
# Purpose: encapsulates the deterministic branch-consolidation procedure from
# commands/workday-complete.md § Step 3 so it is independently invokable,
# testable, and not skippable by EM discretion.
#
# Spec backlink: commands/workday-complete.md lines 145-196
#
# Stdout: one-line-per-action summary (machine-readable prefix [step3])
# Stderr: detailed git command output and warnings
#
# Exit codes:
#   0 — full success
#   1 — sync-main aborted; OR detached HEAD / running on main/master branch (guard, F11)
#   2 — merge conflict during sibling merge (halt; PM resolves)
#   3 — reconcile with origin/main hit a conflict
#   4 — push rejected twice (PM surface)
#   5 — cs_compute_machine unavailable (lib missing)
#
# Negative-spec: does NOT touch feature/* branches (intentionally long-lived).
# Does NOT modify sync-main.sh or coordinator-current-branch.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash version guard (bash 4+ required per DR-148)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "[step3] ERROR: bash 4+ required. Run: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# PLUGIN_ROOT discovery — resolve relative to this script's location
# (portable: no realpath / readlink -f dependency)
# ---------------------------------------------------------------------------
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_PATH="${PLUGIN_ROOT}/lib/coordinator-daily-branch.sh"
BIN_SYNC_MAIN="${STEP3_SYNC_MAIN:-${PLUGIN_ROOT}/bin/sync-main.sh}"
BIN_CURRENT_BRANCH="${PLUGIN_ROOT}/bin/coordinator-current-branch"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
NO_PUSH=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push)  NO_PUSH=1;  shift ;;
    --dry-run)  DRY_RUN=1;  shift ;;
    --help|-h)
      cat <<'EOF'
Usage: workday-complete-step3-consolidate.sh [--no-push] [--dry-run]

  --no-push   Perform local consolidation; skip push step.
  --dry-run   Print what would happen; perform no git mutations.

Exit codes: 0=ok 1=sync-main-abort 2=merge-conflict 3=reconcile-conflict
            4=push-rejected-twice 5=lib-missing
EOF
      exit 0
      ;;
    *) echo "[step3] ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Lib availability check
# ---------------------------------------------------------------------------
if [[ ! -f "$LIB_PATH" ]]; then
  echo "[step3] ERROR: coordinator-daily-branch lib not found at $LIB_PATH" >&2
  exit 5
fi
# shellcheck source=/dev/null
source "$LIB_PATH"

# ---------------------------------------------------------------------------
# Dry-run gate helper — wraps git mutations
# ---------------------------------------------------------------------------
_git_mutate() {
  # Usage: _git_mutate <description> <git args...>
  local desc="$1"; shift
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[step3] DRY-RUN: would run: git $*" >&2
    return 0
  fi
  git "$@"
}

# ---------------------------------------------------------------------------
# Step 3.0 — sync-main
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[step3] DRY-RUN: would run sync-main.sh" >&2
  echo "[step3] sync-main: ok"
else
  if ! "$BASH" "$BIN_SYNC_MAIN" >&2; then
    echo "[step3] sync-main: FAILED" >&2
    exit 1
  fi
  echo "[step3] sync-main: ok"
fi

# ---------------------------------------------------------------------------
# Step 3.1 — Determine machine and today
# ---------------------------------------------------------------------------
MACHINE=$(cs_compute_machine)
TODAY=$(date -u +%Y-%m-%d)
echo "[step3] machine: ${MACHINE}"
echo "[step3] today: ${TODAY}"

# ---------------------------------------------------------------------------
# Step 3.2 — Determine current branch
# ---------------------------------------------------------------------------
CURRENT_BRANCH=""
if [[ -x "$BIN_CURRENT_BRANCH" ]]; then
  # Review: code-reviewer (F14) — invoke directly; "$BASH" wrapper fails if shebang is not bash
  CURRENT_BRANCH=$("$BIN_CURRENT_BRANCH" 2>/dev/null || true)
fi
if [[ -z "$CURRENT_BRANCH" ]]; then
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || true)
fi

# Review: code-reviewer (F11) — catastrophic guard: detached HEAD produces empty string → excludes nothing;
# on-main guard prevents git push --force-with-lease origin main which is destructive.
if [[ -z "$CURRENT_BRANCH" ]]; then
  echo "[step3] ERROR: cannot determine current branch (detached HEAD?)" >&2; exit 1
fi
if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" ]]; then
  echo "[step3] ERROR: current branch is '$CURRENT_BRANCH' — Step 3 must run on a workstream branch" >&2; exit 1
fi

# ---------------------------------------------------------------------------
# Step 3.3 — Discover sibling workstream branches
# (case-insensitive; excludes current branch; matches date and span forms)
# Pattern: work/<machine>/<date-or-span> where the span contains TODAY.
# Two-pass filter: (1) grep for work/$MACHINE/ prefix, (2) cs_parse_branch_span
# checks that TODAY falls within [start_date, end_date].
# Review: code-reviewer (F1) — previous grep anchored on TODAY's literal date,
# breaking span-form branches like work/striker/2026-05-06to07 whose date
# component is the start date, not today. Also F15: comment updated to match.
# ---------------------------------------------------------------------------
# Helper: returns 0 if TODAY falls within the span of the given branch name
_branch_covers_today() {
  local b="$1"
  local span
  span=$(cs_parse_branch_span "$b") || return 1
  local start_date end_date
  start_date="${span%% *}"
  end_date="${span##* }"
  # Lexicographic comparison works correctly for YYYY-MM-DD.
  # bash [[ ]] has no <= operator; use NOT-less-than as the equivalent of >=.
  [[ ! "$TODAY" < "$start_date" && ! "$end_date" < "$TODAY" ]]
}

SIBLING_BRANCHES=()
while IFS= read -r branch; do
  [[ -z "$branch" ]] && continue
  # Review: code-reviewer (F7) — use [[:space:]]* (zero-or-more) not + so a branch
  # with no leading whitespace is not stripped to empty by the quantifier.
  branch=$(echo "$branch" | awk '{gsub(/^\*?[[:space:]]*/,""); print}')
  [[ -z "$branch" ]] && continue
  # Exclude current branch — we merge siblings INTO it, not itself
  [[ "$branch" == "$CURRENT_BRANCH" ]] && continue
  # Two-pass: prefix match then span-date check
  _branch_covers_today "$branch" || continue
  SIBLING_BRANCHES+=("$branch")
done < <(git branch --list 2>/dev/null \
  | grep -iE "^\*? *work/${MACHINE}/" \
  || true)

# Build comma-separated list for summary output
if [[ "${#SIBLING_BRANCHES[@]}" -eq 0 ]]; then
  SIBLINGS_DISPLAY="none"
else
  SIBLINGS_DISPLAY=""
  for b in "${SIBLING_BRANCHES[@]}"; do
    [[ -n "$SIBLINGS_DISPLAY" ]] && SIBLINGS_DISPLAY+=","
    SIBLINGS_DISPLAY+="$b"
  done
fi
echo "[step3] siblings discovered: ${SIBLINGS_DISPLAY}"

# ---------------------------------------------------------------------------
# Step 3.4 — Merge siblings into current branch
# ---------------------------------------------------------------------------
MERGED_COUNT=0
for sibling in "${SIBLING_BRANCHES[@]}"; do
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[step3] DRY-RUN: would merge ${sibling}" >&2
    MERGED_COUNT=$(( MERGED_COUNT + 1 ))
    continue
  fi

  echo "[step3] merging sibling: ${sibling}" >&2
  # Attempt the merge; on conflict abort and surface to PM
  if ! git merge --no-edit "$sibling" >&2; then
    echo "[step3] CONFLICT merging sibling branch: ${sibling}" >&2
    echo "[step3] Aborting merge. Resolve conflicts, then re-run." >&2
    # Review: code-reviewer (F9) — drop 2>/dev/null; abort diagnostics go to stderr
    git merge --abort >&2 || true
    exit 2
  fi
  MERGED_COUNT=$(( MERGED_COUNT + 1 ))
done
echo "[step3] siblings merged: ${MERGED_COUNT}"

# ---------------------------------------------------------------------------
# Step 3.5 — Reconcile with origin/main
# Precondition: sync-main.sh already ran (fetched origin/main).
# ---------------------------------------------------------------------------
RECONCILE_STATUS="no-op (origin/main missing)"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[step3] DRY-RUN: would reconcile with origin/main" >&2
  RECONCILE_STATUS="no-op (dry-run)"
elif ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  # origin/main not present locally — skip reconcile
  echo "[step3] origin/main not present locally — skipping reconcile" >&2
  RECONCILE_STATUS="no-op (origin/main missing)"
else
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "0")
  if [[ "$BEHIND" == "0" ]]; then
    # HEAD already contains origin/main — no rebase needed.
    # Distinguish at-parity (zero ahead too) from genuinely-ahead-only.
    # Review: code-reviewer (F2) — BEHIND==0 is true for both ahead-only AND at-parity;
    # mislabelling at-parity as "ahead-only" is confusing in machine-readable output.
    AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")
    if [[ "$AHEAD" == "0" ]]; then
      echo "[step3] branch is at origin/main — no rebase needed" >&2
      RECONCILE_STATUS="no-op (at origin/main)"
    else
      echo "[step3] branch already contains origin/main — no rebase needed" >&2
      RECONCILE_STATUS="no-op (ahead-only)"
    fi
  else
    echo "[step3] ${BEHIND} commit(s) behind origin/main — rebasing..." >&2
    if git rebase origin/main >&2; then
      RECONCILE_STATUS="rebased"
    else
      echo "[step3] rebase had conflicts; falling back to merge..." >&2
      # Review: code-reviewer (F9) — drop 2>/dev/null; abort diagnostics go to stderr
      git rebase --abort >&2 || true
      if git merge origin/main >&2; then
        RECONCILE_STATUS="merged (fallback)"
      else
        echo "[step3] CONFLICT reconciling with origin/main" >&2
        # Review: code-reviewer (F9) — drop 2>/dev/null; abort diagnostics go to stderr
        git merge --abort >&2 || true
        exit 3
      fi
    fi
  fi
fi
echo "[step3] reconcile: ${RECONCILE_STATUS}"

# ---------------------------------------------------------------------------
# Step 3.6 — Push current branch
# ---------------------------------------------------------------------------
PUSH_STATUS=""
if [[ "$NO_PUSH" -eq 1 ]]; then
  PUSH_STATUS="skipped (--no-push)"
elif [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[step3] DRY-RUN: would push origin/${CURRENT_BRANCH} --force-with-lease" >&2
  PUSH_STATUS="skipped (--dry-run)"
else
  echo "[step3] pushing to origin/${CURRENT_BRANCH}..." >&2
  if git push --force-with-lease origin "$CURRENT_BRANCH" >&2; then
    PUSH_STATUS="ok"
  else
    # First push failed — fetch then rebase, retry once
    # Review: code-reviewer (F10) — verify remote branch exists before rebasing;
    # if absent (first push attempt), rebase errors with fatal "not a git repository".
    echo "[step3] push rejected; fetching and rebasing, then retrying..." >&2
    git fetch origin >&2 || true
    if ! git rev-parse --verify "origin/${CURRENT_BRANCH}" >/dev/null 2>&1; then
      # Remote branch absent — attempt plain push directly (first-time push)
      echo "[step3] remote branch absent — attempting plain push..." >&2
      if git push --force-with-lease origin "$CURRENT_BRANCH" >&2; then
        PUSH_STATUS="retried-ok"
      else
        echo "[step3] push rejected twice. PM must resolve before continuing." >&2
        exit 4
      fi
    elif git rebase "origin/${CURRENT_BRANCH}" >&2; then
      if git push --force-with-lease origin "$CURRENT_BRANCH" >&2; then
        PUSH_STATUS="retried-ok"
      else
        echo "[step3] push rejected twice. PM must resolve before continuing." >&2
        exit 4
      fi
    else
      # Review: code-reviewer (F9) — drop 2>/dev/null; abort diagnostics go to stderr
      git rebase --abort >&2 || true
      echo "[step3] push-retry rebase failed. PM must resolve before continuing." >&2
      exit 4
    fi
  fi
fi
echo "[step3] push: ${PUSH_STATUS}"

# ---------------------------------------------------------------------------
# Step 3.7 — Delete merged sibling branches
# Only delete branches that are now fully merged into HEAD.
# Excludes the current branch and feature/* branches (long-lived by design).
# ---------------------------------------------------------------------------
DELETED_COUNT=0
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[step3] DRY-RUN: would delete merged sibling branches" >&2
else
  # Review: code-reviewer (F1) — two-pass filter matches span-form branches too;
  # (F7) use [[:space:]]* (zero-or-more) in awk so no-leading-whitespace branch not stripped empty.
  while IFS= read -r branch; do
    [[ -z "$branch" ]] && continue
    branch=$(echo "$branch" | awk '{gsub(/^\*?[[:space:]]*/,""); print}')
    [[ -z "$branch" ]] && continue
    [[ "$branch" == "$CURRENT_BRANCH" ]] && continue
    _branch_covers_today "$branch" || continue
    echo "[step3] deleting merged sibling: ${branch}" >&2
    if git branch -d "$branch" >&2; then
      DELETED_COUNT=$(( DELETED_COUNT + 1 ))
    else
      echo "[step3] WARN: could not delete ${branch} — may not be fully merged" >&2
    fi
  done < <(git branch --merged 2>/dev/null \
    | grep -iE "^\*? *work/${MACHINE}/" \
    || true)
fi
echo "[step3] siblings deleted: ${DELETED_COUNT}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo "[step3] OK"
exit 0
