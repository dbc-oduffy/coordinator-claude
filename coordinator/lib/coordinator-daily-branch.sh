#!/bin/bash
# coordinator-daily-branch.sh — Shared helpers for daily-branch discipline enforcement
#
# NOTE on examples: tests under bin/tests/ use `striker` / `STRIKER` as
# literal fixture values (test cases assert canonical-case behavior on a
# concrete machine name; placeholders won't substitute mechanically). Doctrine
# prose elsewhere in the plugin uses `<machine>` / `<MACHINE>` placeholders.
# A consumer reading either form should mentally substitute their own machine
# name — both shapes convey "lowercase ASCII identifier, no slashes."
#
# Spec backlink: docs/plans/2026-05-07-daily-branch-doctrine-rethink.md (Phase 1)
#
# The hook polices branch *shape*, not branch *date*. There is no notion of
# "today's daily" in this library — only "is this branch an allowed workstream
# branch?" The policy oracle is cs_is_allowed_branch.
#
# Consumers:
#   - hooks/scripts/block-off-daily-branch.sh (PreToolUse hook)
#
# Check 6 history: commit-time date-enforcement (Check 6) was in validate-commit.sh,
# then consolidated into block-off-daily-branch.sh (commit arm) per the Staff Engineer F11.
# Check 6 fully decommissioned 2026-05-07 per PM call — not in either file.
# Rationale: "if the branch isn't totally out of date then what harm? I think a hook
# to reject commits is too harsh." (PM verbatim). Stale-day branches are now handled
# by the /workday-start rename prompt, not a commit block.
#
# Source this file; do NOT execute it directly. Functions are prefixed cs_ to
# match coordinator-session.sh convention.
#
# Source pattern (same as coordinator-session.sh):
#   LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-daily-branch.sh"
#   if [[ ! -f "$LIB_PATH" ]]; then
#     LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh"
#   fi
#   [[ -f "$LIB_PATH" ]] && source "$LIB_PATH"

# cs_compute_machine — echo the coordinator machine name, always lowercase.
# Resolution order: $COORDINATOR_MACHINE → $COMPUTERNAME → hostname → $HOSTNAME → "unknown"
# Single-tail-emit pattern: all paths converge to one echo+tr at the end (the Staff Engineer F11).
cs_compute_machine() {
  local m
  if [[ -n "${COORDINATOR_MACHINE:-}" ]]; then m="$COORDINATOR_MACHINE"
  elif [[ -n "${COMPUTERNAME:-}" ]]; then m="$COMPUTERNAME"
  elif command -v hostname &>/dev/null; then m=$(hostname 2>/dev/null | sed 's/\..*//')
  else m="${HOSTNAME:-unknown}"
  fi
  echo "${m:-unknown}" | tr '[:upper:]' '[:lower:]'
}

# cs_parse_branch_span <name>
# Given work/{machine}/{date-or-span}, echo "start_date end_date" (space-separated).
# end_date equals start_date for single-day branches.
# Returns 1 if not parseable as a daily/span branch.
#
# Accepted formats:
#   work/<machine>/YYYY-MM-DD           → start=YYYY-MM-DD, end=YYYY-MM-DD
#   work/<machine>/YYYY-MM-DDtoDD       → start=YYYY-MM-DD, end computed (month/year roll if end-DD < start-DD)
#
# Month/year boundary rule (the Staff Engineer F4, option b):
#   If end-DD < start-DD → advance month by 1 (advance year by 1 on Dec→Jan).
#   Parser advances at most one month — spans >~28 days are anti-patterns routed
#   through the A/B/C reconciliation flow, not through this parser.
#
# Negative spec: does NOT accept feature/foo, work/striker/feature-X, or branches
# with invalid date components (month > 12, day > 31).
cs_parse_branch_span() {
  local name="$1"
  local lc
  lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')

  # Must start with work/<something>/<date-or-span>
  # Regex: work / <machine-segment> / <YYYY-MM-DD>[to<DD>]
  if ! echo "$lc" | grep -qE '^work/[^/]+/[0-9]{4}-[0-9]{2}-[0-9]{2}(to[0-9]{2})?$'; then
    return 1
  fi

  # Extract the date portion (everything after the second /)
  local date_part
  date_part=$(echo "$lc" | sed 's|^work/[^/]*/||')

  # Parse start date
  local start_year start_month start_day
  start_year="${date_part:0:4}"
  start_month="${date_part:5:2}"
  start_day="${date_part:8:2}"

  # Validate start date components
  if (( 10#$start_month < 1 || 10#$start_month > 12 )); then return 1; fi
  if (( 10#$start_day < 1 || 10#$start_day > 31 )); then return 1; fi

  local start_date="${start_year}-${start_month}-${start_day}"

  # Check for span suffix (toDD)
  if echo "$date_part" | grep -qE 'to[0-9]{2}$'; then
    local end_dd
    end_dd=$(echo "$date_part" | sed 's/.*to//')

    local end_year end_month end_day
    end_day="$end_dd"

    # Month/year boundary: if end-DD < start-DD, advance month by 1
    if (( 10#$end_day < 10#$start_day )); then
      # Roll month forward
      if (( 10#$start_month == 12 )); then
        # December → January (year roll)
        end_year=$(( 10#$start_year + 1 ))
        end_month="01"
      else
        end_year="$start_year"
        end_month=$(printf '%02d' $(( 10#$start_month + 1 )))
      fi
    else
      # Same month, end_DD >= start_DD (or same day — single-char to suffix is unusual but valid)
      end_year="$start_year"
      end_month="$start_month"
    fi

    local end_date="${end_year}-${end_month}-${end_day}"
    echo "${start_date} ${end_date}"
  else
    # Single-day branch
    echo "${start_date} ${start_date}"
  fi
  return 0
}

# cs_is_allowed_branch <name>
# Returns 0 if <name> is an allowed workstream branch: main, or any
# work/{machine}/{date-or-span} that parses via cs_parse_branch_span (case-insensitive).
# There is no "today's daily" check — the hook polices branch shape, not date.
#
# This is the SHAPE oracle — case-insensitive by design so remediation paths
# (rename prompts, migration scripts) can recognise mixed-case input as
# "valid shape, wrong case" and fix it. For creation-time canonical-case
# enforcement use cs_is_canonical_branch instead.
#
# Negative spec: rejects feature/foo, work/striker/feature-X, hotfix/*, etc.
cs_is_allowed_branch() {
  local name="$1"
  local lc
  lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')
  [[ "$lc" == "main" ]] && return 0
  cs_parse_branch_span "$lc" > /dev/null 2>&1 && return 0
  return 1
}

# cs_is_canonical_branch <name>
# Returns 0 iff <name> is allowed AND already in canonical (lowercase) form.
# This is the CREATION oracle — used by the hook to fail closed when a new
# work/* ref would land on disk in non-canonical case. Distinct from
# cs_is_allowed_branch because remediation paths need to recognise mixed-case
# input in order to fix it; this oracle rejects mixed-case so the hook can
# block its creation in the first place.
#
# Why creation-time: on Windows's case-insensitive FS, a mixed-case ref
# created via `git checkout -b work/STRIKER/...` lands on disk as
# `refs/heads/work/striker/...` (lowercase) but `.git/HEAD` stores the
# literal mixed-case text. `git branch --show-current` returns the stored
# case, and `git push origin <that>` fails ref lookup case-sensitively
# against the canonical form. The runtime canonicalization in
# coordinator-auto-push (commit 6fa4d58) and the doctrine snippet sweep
# (commit 40a2736) work around the symptom; this oracle prevents the cause.
cs_is_canonical_branch() {
  local name="$1"
  cs_is_allowed_branch "$name" || return 1
  local lc
  lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')
  [[ "$name" == "$lc" ]]
}

# cs_format_span_suffix <start-date> <today>
# Emits the full branch date portion: just <start-date> when start == today,
# or <start-date>to<end-DD> when start != today.
# Both arguments must be YYYY-MM-DD.
cs_format_span_suffix() {
  local start_date="$1"
  local today="$2"
  if [[ "$start_date" == "$today" ]]; then
    echo "$start_date"
  else
    local end_dd
    end_dd="${today##*-}"
    echo "${start_date}to${end_dd}"
  fi
}

# cs_rename_target <machine> <start-date> <today> <commits-ahead>
# Chooses the midnight-rename target branch name (Check 4 of workday-start
# Step 0). When <commits-ahead> == 0 the branch's history has all merged to
# origin/main (or main moved ahead and we are strictly behind) — a
# {start}to{today} span name would misleadingly advertise multi-day WIP that no
# longer exists, so the target is today-only `work/{machine}/{today}`. When
# <commits-ahead> > 0 the span is honest and carries the genuine WIP forward.
# Doctrine 2026-06-02 (→ daily-branch-discipline.md): refines "reconcile not
# rotate" — 0-ahead means no ongoing work to abandon, so renaming to an honest
# today-only name + ff-to-main is reconciliation, not rotation.
#
# When <commits-ahead> > 0 but <start-date> == <today>, cs_format_span_suffix
# collapses to <today> — same result as the 0-ahead path (no spurious span).
#
# Negative spec: does NOT touch git — the caller supplies <commits-ahead> so
# this is unit-testable without a repo (mirrors cs_should_prompt_rename).
cs_rename_target() {
  local machine="$1"
  local start_date="$2"
  local today="$3"
  local commits_ahead="$4"
  # Detect-then-fail-loud on non-integer input: [[ "" -eq 0 ]] is true in bash,
  # so a missing/garbage arg would otherwise silently select the 0-ahead path.
  if ! [[ "$commits_ahead" =~ ^[0-9]+$ ]]; then
    echo "cs_rename_target: commits_ahead must be a non-negative integer, got '$commits_ahead'" >&2
    return 1
  fi
  if [[ "$commits_ahead" -eq 0 ]]; then
    echo "work/${machine}/${today}"
  else
    echo "work/${machine}/$(cs_format_span_suffix "$start_date" "$today")"
  fi
}

# cs_should_prompt_rename <branch> <today> <last-commit-epoch>
# Returns 0 (should prompt for rename) when:
#   - last commit was within 48h (active work — matches stale-commit cutoff in /workday-start Step 0 Check 1), AND
#   - the branch end-suffix does NOT already equal today (not already in span)
#
# Returns 1 (no-op) when:
#   - branch already covers today (end-suffix == today's DD within today's month/year), OR
#   - last commit is older than 48h (stale — routes to A/B/C triage, not rename prompt)
#
# Arguments:
#   <branch>            — branch name (e.g. work/striker/2026-05-06)
#   <today>             — today's date as YYYY-MM-DD
#   <last-commit-epoch> — unix epoch of most recent commit on the branch
#
# Negative spec: does NOT compute git state — callers pass the epoch so this
# function is unit-testable without a git repo.
cs_should_prompt_rename() {
  local branch="$1"
  local today="$2"
  local last_commit_epoch="$3"

  # Must be a parseable daily/span branch
  local span
  span=$(cs_parse_branch_span "$branch") || return 1

  local _start end_date
  _start="${span%% *}"
  end_date="${span##* }"

  # Check if already in span: end_date == today
  if [[ "$end_date" == "$today" ]]; then
    return 1  # Already covers today — no prompt needed
  fi

  # Check staleness: last commit >48h ago → route to A/B/C, not rename prompt
  local now_epoch
  now_epoch=$(date +%s 2>/dev/null || echo 0)
  local age_seconds=$(( now_epoch - last_commit_epoch ))
  local hours_48=$(( 48 * 3600 ))
  if (( age_seconds > hours_48 )); then
    return 1  # Stale — no prompt; A/B/C flow handles it
  fi

  # Active work, not yet in span — prompt for rename
  return 0
}

# --- REMOVED (do not re-add) ---
# cs_compute_active_daily_lc — INTENTIONALLY ABSENT.
#   This helper was in an earlier draft but is redundant and concurrency-hostile:
#   it couples branch-policy resolution to working-tree HEAD, which (a) reads the
#   source branch, not the target, during branch-mutating ops, and (b) breaks under
#   concurrent EM sessions where each session is on a different but valid span branch.
#   Policy oracle is cs_is_allowed_branch. (the Staff Engineer R1 F1; 2026-05-07)
#
# cs_compute_today_daily_lc — INTENTIONALLY ABSENT.
#   Replaced by cs_is_allowed_branch which parses span form without a "today" oracle.
#   Retained only in the hook fallback inline (which will be updated in Phase 2).
