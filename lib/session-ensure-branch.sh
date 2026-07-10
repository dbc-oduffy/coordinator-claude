#!/usr/bin/env bash
# session-ensure-branch.sh — Shared gate: cut work/{machine}/{today} when the session opens
#                             on main, detached HEAD, or a zero-ahead non-span branch.
#
# This lib is the extracted form of workday-start-step0.sh Check 3 — promoted to a shared
# helper so the same gate condition and branch-cut mechanics can be reused by:
#   - bin/workday-start-step0.sh  (Check 3 refactored to call through here)
#   - hooks/scripts/session-ensure-branch.sh  (SessionStart hook — fires at session open)
#
# nag→action pattern: this is the REFERENCE EXEMPLAR for the nag→action conversion
# pattern (strang-04). The SessionStart hook built on this lib is the "A" in
# "A built as template for B" — a concrete DoE-claude surface that does the active
# behavior now, shaped so it becomes the template every later nag→action conversion
# copies. See docs/wiki/hook-best-practices.md § nag→action for the pattern this
# establishes, and strang-06 for the next conversion that copies it.
#
# Soft seam — example-orchestration-hub action layer:
# The B-half (example-orchestration-hub-native session.ensure_branch op) is a future migration gated on the
# example-orchestration-hub action layer (pcore-06/10). When that lands, this lib becomes the legacy fallback
# wrapped by the DR-210 strangler facade. Keep internal logic clean enough to wrap.
#
# Source this file; do NOT execute it directly.
# Requires: lib/coordinator-daily-branch.sh reachable at the same lib dir (sourced here).
#
# Spec backlink: state/handoffs/2026-07-04_220004_roadmap-strang-04.md § Phase 1

# Guard against double-source
[[ -n "${_CS_SESSION_ENSURE_BRANCH_LOADED:-}" ]] && return 0
_CS_SESSION_ENSURE_BRANCH_LOADED=1

_SESSION_ENSURE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_SESSION_ENSURE_DAILY_BRANCH="${_SESSION_ENSURE_LIB_DIR}/coordinator-daily-branch.sh"
if [[ ! -f "$_SESSION_ENSURE_DAILY_BRANCH" ]]; then
  echo "ERROR: session-ensure-branch.sh requires coordinator-daily-branch.sh at ${_SESSION_ENSURE_DAILY_BRANCH}" >&2
  return 1
fi
# shellcheck source=/dev/null
source "$_SESSION_ENSURE_DAILY_BRANCH"
unset _SESSION_ENSURE_DAILY_BRANCH _SESSION_ENSURE_LIB_DIR

# cs_session_ensure_branch <machine> <today> <current> <head_detached> <commits_ahead>
#
# Gate condition: on main / detached HEAD / zero-ahead non-span branch →
#   cut work/{machine}/{today} (collision-safe suffix loop), push it, emit FRESH-CUT to stdout.
#   Silent no-op when the gate condition is not met.
#
# Parameters:
#   machine       — coordinator machine slug (from cs_compute_machine)
#   today         — today's date YYYY-MM-DD (from coordinator_local_day)
#   current       — current branch name (from git branch --show-current)
#   head_detached — "yes" if HEAD is detached, "no" otherwise
#   commits_ahead — commits ahead of origin/main (0 when on main or detached)
#
# Side effects (shell variables set on return):
#   _CS_ENSURE_RESULT     — "FRESH-CUT" when a new branch was cut; "" otherwise
#   _CS_ENSURE_NEW_BRANCH — new branch name when FRESH-CUT; "" otherwise
#
# Stdout: "FRESH-CUT branch=<name>" when a branch is cut; silent otherwise.
#
# Exit codes:
#   0 — no error; gate not triggered (no-op) or branch cut and pushed successfully
#   1 — suffix collision: could not find unused work/{machine}/{today} variant after -9
#
# COORDINATOR_OVERRIDE_BRANCH pattern: all git commands carry COORDINATOR_OVERRIDE_BRANCH=1
# so the off-daily-branch PreToolUse guard does not deny them. Do NOT remove this — the
# guard denies git checkout/push on non-daily branches without it.
#
# Callers are responsible for post-cut behavior:
#   - workday-start-step0.sh: exec workday-start-step0-reconcile.sh when FRESH-CUT
#   - session-ensure-branch hook: emit additionalContext heads-up and exit 0
cs_session_ensure_branch() {
  local machine="$1"
  local today="$2"
  local current="$3"
  local head_detached="$4"
  local commits_ahead="$5"

  _CS_ENSURE_RESULT=""
  _CS_ENSURE_NEW_BRANCH=""

  # Gate: on main, detached HEAD, or zero-ahead non-span branch (not a valid workstream)
  if [[ "$current" == "main" ]] || [[ "$head_detached" == "yes" ]] || \
     { [[ -n "$current" ]] && [[ "$current" != "main" ]] && [[ "$commits_ahead" -eq 0 ]] && \
       ! cs_parse_branch_span "$current" >/dev/null 2>&1; }; then

    local new_branch="work/${machine}/${today}"

    # Collision-safe suffix loop: rare but possible when yesterday's session plus a
    # recovery cut both ran. Mirrors workday-start-step0.sh Check 3 exactly.
    if git show-ref --verify --quiet "refs/heads/${new_branch}"; then
      local n=2
      while git show-ref --verify --quiet "refs/heads/${new_branch}-${n}"; do
        n=$(( n + 1 ))
        if [[ "$n" -gt 9 ]]; then
          echo "ERROR: cannot find unused workstream branch suffix (tried -2 through -9)" >&2
          return 1
        fi
      done
      new_branch="${new_branch}-${n}"
    fi

    COORDINATOR_OVERRIDE_BRANCH=1 \
    COORDINATOR_OVERRIDE_BRANCH_REASON="session-ensure-branch: create/push workstream branch" \
    git checkout -b "$new_branch" >&2

    COORDINATOR_OVERRIDE_BRANCH=1 \
    COORDINATOR_OVERRIDE_BRANCH_REASON="session-ensure-branch: create/push workstream branch" \
    git push -u origin "$new_branch" >&2 \
      || echo "WARN: push of new branch failed — crash-insurance push not established" >&2

    echo "FRESH-CUT branch=$new_branch"
    _CS_ENSURE_RESULT="FRESH-CUT"
    _CS_ENSURE_NEW_BRANCH="$new_branch"
  fi
}
