#!/usr/bin/env bash
# workday-start-step0.sh — deterministic Step 0 (Branch Setup) for /workday-start.
#
# Encapsulates the precedence switch documented in
# pipelines/workday-start-internals.md § Step 0. Exists because the procedure
# was empirically EM-skippable when expressed as inline bash in the skill body
# (2026-05-20: an EM ran the assertion in Step 0.45 but never executed Check 4,
# leaving the working tree on a stale-suffix branch). Concentrating the
# precedence logic in a single invokable script removes EM judgment from a
# mechanical procedure.
#
# Stdout: one-line status notice consumed by the briefing (RENAMED / IN-SPAN /
# FRESH-CUT / NAMED-WORKSTREAM / STALE-NEEDS-ABC / RECONCILE-CONFLICT).
# Stderr: human-readable detail.
# Exit codes:
#   0 — step 0 succeeded; proceed to step 1.
#   2 — stale-commit guard triggered; A/B/C Branch Reconciliation needed.
#   3 — reconcile with origin/main hit a conflict; PM resolves first.
#   1 — sync-main aborted or other unexpected error.

set -eu

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_PATH="${PLUGIN_ROOT}/lib/coordinator-daily-branch.sh"

if [[ ! -f "$LIB_PATH" ]]; then
  echo "ERROR: daily-branch lib not found at $LIB_PATH" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$LIB_PATH"

# Step 0.1 — Sync main
if ! bash "${PLUGIN_ROOT}/bin/sync-main.sh" >&2; then
  echo "SYNC-MAIN-ABORT"
  exit 1
fi

# Step 0.2 — Determine machine and today
MACHINE=$(cs_compute_machine)
TODAY=$(date -u +%Y-%m-%d)
CURRENT=$(git branch --show-current 2>/dev/null || echo "")

# Step 0.3 — Precedence switch

# Check 1 — Stale-commit guard
LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
NOW_EPOCH=$(date -u +%s)
AGE_DAYS=$(( (NOW_EPOCH - LAST_EPOCH) / 86400 ))
if [[ "$AGE_DAYS" -gt 2 ]] && [[ "$CURRENT" == work/* ]]; then
  echo "STALE-NEEDS-ABC branch=$CURRENT age_days=$AGE_DAYS"
  echo "Stale-commit guard: $CURRENT last commit $AGE_DAYS days ago. Surface A/B/C Branch Reconciliation Decision." >&2
  exit 2
fi

# Check 2 — Already in span
# cs_should_prompt_rename returns 0 = rename needed (active branch, not in span),
# 1 = no rename (already in span OR stale OR unparseable). Capture exit code
# unconditionally (|| true required because set -e otherwise aborts on the
# non-zero return).
RENAME_NEEDED=0
cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH" || RENAME_NEEDED=$?
# RENAME_NEEDED is 0 when rename is needed, non-zero otherwise. Combined with
# a successful cs_parse_branch_span, RENAME_NEEDED != 0 means "branch parses
# and already covers today" — the IN-SPAN case. (Unparseable branches get
# RENAME_NEEDED != 0 too, but cs_parse_branch_span fails for them, so they
# fall through to Check 3 / 3.5.)
if [[ "$RENAME_NEEDED" -ne 0 ]] && cs_parse_branch_span "$CURRENT" >/dev/null 2>&1; then
  echo "IN-SPAN branch=$CURRENT"
  exit 0
fi

# Check 3 — On main / detached / empty branch
HEAD_DETACHED=$(git symbolic-ref -q HEAD >/dev/null 2>&1 && echo "no" || echo "yes")
COMMITS_AHEAD=0
if [[ -n "$CURRENT" && "$CURRENT" != "main" ]]; then
  COMMITS_AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
fi
if [[ "$CURRENT" == "main" ]] || [[ "$HEAD_DETACHED" == "yes" ]] || \
   { [[ -n "$CURRENT" ]] && [[ "$CURRENT" != "main" ]] && [[ "$COMMITS_AHEAD" -eq 0 ]] && ! cs_parse_branch_span "$CURRENT" >/dev/null 2>&1; }; then
  NEW_BRANCH="work/${MACHINE}/${TODAY}"
  # Loop to find an unused suffix when -2 also exists (rare but possible if
  # yesterday's session plus a recovery cut both ran).
  if git show-ref --verify --quiet "refs/heads/${NEW_BRANCH}"; then
    n=2
    while git show-ref --verify --quiet "refs/heads/${NEW_BRANCH}-${n}"; do
      n=$(( n + 1 ))
      if [[ "$n" -gt 9 ]]; then
        echo "ERROR: cannot find unused workstream branch suffix (tried -2 through -9)" >&2
        exit 1
      fi
    done
    NEW_BRANCH="${NEW_BRANCH}-${n}"
  fi
  COORDINATOR_OVERRIDE_BRANCH=1 \
  COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 create workstream branch" \
  git checkout -b "$NEW_BRANCH" >&2
  COORDINATOR_OVERRIDE_BRANCH=1 \
  COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 push new workstream branch" \
  git push -u origin "$NEW_BRANCH" >&2 || echo "WARN: push of new branch failed — crash-insurance push not established" >&2
  echo "FRESH-CUT branch=$NEW_BRANCH"
  exec bash "${PLUGIN_ROOT}/bin/workday-start-step0-reconcile.sh"
fi

# Check 3.5 — Named long-lived workstream
if ! cs_parse_branch_span "$CURRENT" >/dev/null 2>&1 && [[ "$COMMITS_AHEAD" -gt 0 ]]; then
  echo "NAMED-WORKSTREAM branch=$CURRENT"
  exec bash "${PLUGIN_ROOT}/bin/workday-start-step0-reconcile.sh"
fi

# Check 4 — Midnight rename (RENAME_NEEDED=0 implies active work, not in span)
OLD="$CURRENT"
# Guard: Check 4 is only reachable when cs_parse_branch_span SHOULD succeed
# (Checks 2, 3, 3.5 catch unparseable forms). If it doesn't, abort loudly
# rather than constructing a malformed branch name like work/striker/to20.
if ! parsed_span=$(cs_parse_branch_span "$OLD" 2>/dev/null); then
  echo "ERROR: Check 4 reached with unparseable branch '$OLD' — precedence switch fell through unexpectedly" >&2
  exit 1
fi
START_DATE=$(echo "$parsed_span" | awk '{print $1}')
if [[ -z "$START_DATE" ]]; then
  echo "ERROR: cs_parse_branch_span returned empty start_date for branch '$OLD'" >&2
  exit 1
fi

# Choose the rename target. A "start-to-today" span (e.g. 2026-06-01to02) is
# only honest when this branch carries UNMERGED work across the day boundary;
# when COMMITS_AHEAD == 0 the history has all merged (or main moved ahead) and a
# span name would misleadingly advertise WIP that no longer exists — so the
# target collapses to today-only and the reconcile leg ff's us onto origin/main.
# Selection logic lives in cs_rename_target (unit-tested without a repo).
# Doctrine 2026-06-02: refines "reconcile not rotate". → daily-branch-discipline.md.
NEW=$(cs_rename_target "$MACHINE" "$START_DATE" "$TODAY" "$COMMITS_AHEAD")

# Concurrent-rename race guard: a sibling session on this shared-bus branch may
# have already rotated it to cover today during the Check 2→4 window. Match BOTH
# forms cs_rename_target can produce — the *toDD span AND the single-date today
# name (the 0-ahead form). TODAY_DD derives from the UTC $TODAY (line 41), NOT a
# fresh `date +%d` (which omits -u and diverges from $TODAY across the UTC
# midnight boundary when local time is behind UTC). [code-reviewer F1, F4]
CURRENT_RECHECK=$(git branch --show-current)
TODAY_DD="${TODAY##*-}"
if [[ "$CURRENT_RECHECK" == *"to${TODAY_DD}" ]] || [[ "$CURRENT_RECHECK" == *"/${TODAY}" ]]; then
  echo "IN-SPAN branch=$CURRENT_RECHECK note=concurrent-rename"
  exit 0
fi

# Collision guard: the target name may already exist (a recovery cut, or a
# concurrent session that already rotated to today). Never `git branch -m` onto
# an existing ref — append a numeric suffix, mirroring the Check 3 fresh-cut path.
if [[ "$NEW" != "$OLD" ]] && git show-ref --verify --quiet "refs/heads/${NEW}"; then
  n=2
  while git show-ref --verify --quiet "refs/heads/${NEW}-${n}"; do
    n=$(( n + 1 ))
    if [[ "$n" -gt 9 ]]; then
      echo "ERROR: cannot find unused rename target for '$NEW' (tried -2 through -9)" >&2
      exit 1
    fi
  done
  NEW="${NEW}-${n}"
fi

COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename across midnight" \
git branch -m "$OLD" "$NEW" >&2

if ! COORDINATOR_OVERRIDE_BRANCH=1 \
     COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 atomic rename push" \
     git push --atomic origin "${NEW}:${NEW}" ":${OLD}" >&2; then
  COORDINATOR_OVERRIDE_BRANCH=1 \
  COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename rollback" \
  git branch -m "$NEW" "$OLD" >&2
  echo "RENAME-PUSH-FAILED old=$OLD"
  echo "Remote rename rejected; local rolled back. Investigate remote ref-update hooks or permissions." >&2
  exit 1
fi

if ! git branch --set-upstream-to="origin/${NEW}" "$NEW" >/dev/null 2>&1; then
  echo "WARN: could not set upstream to origin/${NEW}; check remote tracking manually." >&2
fi

echo "RENAMED old=$OLD new=$NEW"
exec bash "${PLUGIN_ROOT}/bin/workday-start-step0-reconcile.sh"
