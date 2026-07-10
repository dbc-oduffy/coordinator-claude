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
# Review: code-reviewer F12 — add existence guard to match every other script in this diff
# (step3, step9, backfill-scan all guard before sourcing coordinator-daily-day.sh).
# Without this, a partial install produces an opaque "No such file or directory" bash error
# rather than a clear diagnostic, and silently blocks the workday-start ceremony.
if [[ ! -f "${PLUGIN_ROOT}/lib/coordinator-daily-day.sh" ]]; then
  echo "ERROR: coordinator-daily-day lib not found at ${PLUGIN_ROOT}/lib/coordinator-daily-day.sh" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${PLUGIN_ROOT}/lib/coordinator-daily-day.sh"

if [[ ! -f "${PLUGIN_ROOT}/lib/session-ensure-branch.sh" ]]; then
  echo "ERROR: session-ensure-branch lib not found at ${PLUGIN_ROOT}/lib/session-ensure-branch.sh" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${PLUGIN_ROOT}/lib/session-ensure-branch.sh"

# Step 0.1 — Sync main
if ! bash "${PLUGIN_ROOT}/bin/sync-main.sh" >&2; then
  echo "SYNC-MAIN-ABORT"
  exit 1
fi

# Step 0.2 — Determine machine and today
MACHINE=$(cs_compute_machine)
TODAY=$(coordinator_local_day)
CURRENT=$(git branch --show-current 2>/dev/null || echo "")

# Step 0.2a — Machine-slug registry self-heal and drift detection
# Spec backlink: docs/plans/2026-06-22-persist-machine-slug-registry.md § Seeding item 2 + § Drift detection
# Guard: CLI absent (exit 127) or key absent (exit 1) must never abort this script (set -eu active).
_ML_BIN="${MACHINE_LOCAL_BIN:-machine-local}"
if command -v "$_ML_BIN" &>/dev/null; then
  if ! "$_ML_BIN" has coordinator.machine_slug &>/dev/null; then
    # Key absent — seed from live hostname (not from COORDINATOR_MACHINE env override).
    # cs_compute_machine_live: env→COMPUTERNAME→hostname→HOSTNAME→"unknown" (no registry read).
    _LIVE_SLUG=$(cs_compute_machine_live)
    "$_ML_BIN" set coordinator.machine_slug "$_LIVE_SLUG" &>/dev/null || true
  else
    # Key present — compare persisted value against live hostname; surface drift, do not pick.
    _PERSISTED=$("$_ML_BIN" get --default "" coordinator.machine_slug 2>/dev/null || true)
    _LIVE_SLUG=$(cs_compute_machine_live)
    if [[ -n "$_PERSISTED" && "$_PERSISTED" != "$_LIVE_SLUG" ]]; then
      echo "Machine-slug drift: persisted='${_PERSISTED}', this session's hostname yields '${_LIVE_SLUG}'." >&2
      echo "  Option 1 — stale session: this process has a stale hostname. Keeping persisted value is correct; no action needed." >&2
      echo "  Option 2 — machine renamed: run 'machine-local set coordinator.machine_slug ${_LIVE_SLUG}' to update the registry." >&2
      # MACHINE retains the value from cs_compute_machine (persisted/env/hostname) — not overwritten here.
    fi
  fi
fi
unset _ML_BIN _LIVE_SLUG _PERSISTED

# Step 0.2b — Contributor-slug registry self-heal and drift detection
# Spec backlink: docs/plans/2026-07-08-mcollab-01-contributor-slug.md § "workday-start Step 0 self-heal + drift seam"
# Thinner mirror of Step 0.2a: a person's slug does not drift on machine-rename,
# so there is no "machine renamed" option here — the single surfaced case is
# "persisted slug differs from the git user.email-derived slug".
# Guard: CLI absent (exit 127) or key absent (exit 1) must never abort this script (set -eu active).
_ML_BIN="${MACHINE_LOCAL_BIN:-machine-local}"
if command -v "$_ML_BIN" &>/dev/null; then
  if ! "$_ML_BIN" has coordinator.contributor_slug &>/dev/null; then
    # Key absent — seed from live git user.email (not from COORDINATOR_CONTRIBUTOR env override).
    # cs_compute_contributor_live: env→sanitized user.email local-part→"unknown" (no registry read).
    _LIVE_SLUG=$(cs_compute_contributor_live)
    "$_ML_BIN" set coordinator.contributor_slug "$_LIVE_SLUG" &>/dev/null || true
  else
    # Key present — compare persisted value against live user.email-derived slug; surface drift, do not pick.
    _PERSISTED=$("$_ML_BIN" get --default "" coordinator.contributor_slug 2>/dev/null || true)
    _LIVE_SLUG=$(cs_compute_contributor_live)
    if [[ -n "$_PERSISTED" && "$_PERSISTED" != "$_LIVE_SLUG" ]]; then
      echo "Contributor-slug drift: persisted='${_PERSISTED}', git user.email yields '${_LIVE_SLUG}'." >&2
      echo "  Option 1 — keep persisted: this is the intentional slug; no action needed." >&2
      echo "  Option 2 — update: run 'machine-local set coordinator.contributor_slug ${_LIVE_SLUG}' to update the registry." >&2
      # No MACHINE-equivalent overwrite here — cs_compute_contributor (registry-preferring) still resolves the persisted value.
    fi
  fi
fi
unset _ML_BIN _LIVE_SLUG _PERSISTED

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
cs_session_ensure_branch "$MACHINE" "$TODAY" "$CURRENT" "$HEAD_DETACHED" "$COMMITS_AHEAD" || exit 1
if [[ "${_CS_ENSURE_RESULT:-}" == "FRESH-CUT" ]]; then
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
# rather than constructing a malformed branch name like work/machine-a/to20.
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
# name (the 0-ahead form). TODAY_DD derives from the LOCAL $TODAY (line 41, via
# coordinator_local_day), NOT a fresh `date +%d` (which may diverge from $TODAY
# if called at a different moment). [code-reviewer F1, F4]
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
