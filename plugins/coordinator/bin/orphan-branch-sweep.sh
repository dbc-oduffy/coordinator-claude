#!/usr/bin/env bash
# orphan-branch-sweep.sh — enumerate suspect work/feature branches across the current repo
#
# Spec backlink: docs/plans/2026-05-01-orphan-branch-prevention.md § 1.1
#
# Purpose: read-only scan of user-owned work/* and feature/* branches. For each
# qualifying branch, determines whether it has commits that post-date a merged PR
# (CRITICAL), is an open branch with no PR and a branch-name date ≥2 days old or
# age_h>36 (WARNING), or is clean (OK). Emits JSON lines to stdout.
#
# Negative-spec: this script never mutates branches, refs, or PRs. It is purely
# diagnostic. It does NOT archive, delete, or rename any branch.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
FORMAT="json"
SEVERITY_MIN="ok"
INCLUDE_REMOTE=1
MAX_AGE_DAYS=30

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --format)       FORMAT="$2";          shift 2 ;;
    --severity-min) SEVERITY_MIN="$2";    shift 2 ;;
    --include-remote)  INCLUDE_REMOTE=1;  shift ;;
    --no-include-remote) INCLUDE_REMOTE=0; shift ;;
    --max-age-days) MAX_AGE_DAYS="$2";    shift 2 ;;
    --help|-h)
      cat <<'EOF'
Usage: orphan-branch-sweep.sh [OPTIONS]

Options:
  --format json|text          Output format (default: json)
  --severity-min ok|warning|critical  Minimum severity to emit (default: ok)
  --include-remote / --no-include-remote  Include origin/* branches (default: on)
  --max-age-days N            Ignore branches older than N days (default: 30)
  --help                      Show this help

Outputs one line per qualifying branch. Exits 0 always (even when gh unavailable).
EOF
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Guard: must be inside a git repo
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Guard: gh must be available for PR state checks
# ---------------------------------------------------------------------------
GH_AVAILABLE=0
if command -v gh &>/dev/null; then
  GH_AVAILABLE=1
fi

# ---------------------------------------------------------------------------
# Severity ordering helper
# ---------------------------------------------------------------------------
severity_rank() {
  case "$1" in
    OK)       echo 0 ;;
    WARNING)  echo 1 ;;
    CRITICAL) echo 2 ;;
    *)        echo 0 ;;
  esac
}

min_rank=$(severity_rank "$(echo "$SEVERITY_MIN" | tr '[:lower:]' '[:upper:]')")

# ---------------------------------------------------------------------------
# Collect user email for ownership filter
# ---------------------------------------------------------------------------
USER_EMAIL=$(git config user.email 2>/dev/null || true)

# ---------------------------------------------------------------------------
# Collect qualifying branches (local + remote if requested)
# ---------------------------------------------------------------------------
declare -A seen_branches

collect_branches() {
  local raw_list="$1"
  while IFS= read -r line; do
    # strip leading whitespace and remote prefix
    branch=$(echo "$line" | sed 's|^[[:space:]]*||; s|^origin/||; s|^remotes/origin/||')
    [[ -z "$branch" ]] && continue
    [[ "$branch" == "HEAD" ]] && continue
    # only work/* and feature/* branches
    if [[ "$branch" =~ ^(work|feature)/ ]]; then
      seen_branches["$branch"]=1
    fi
  done <<< "$raw_list"
}

collect_branches "$(git branch --list 'work/*' 'feature/*' 2>/dev/null)"
collect_branches "$(git branch --list -r 'origin/work/*' 'origin/feature/*' 2>/dev/null)"

# ---------------------------------------------------------------------------
# For each qualifying branch, compute attributes and classify
# ---------------------------------------------------------------------------
NOW=$(date +%s)
MAX_AGE_SECS=$((MAX_AGE_DAYS * 86400))

emit_result() {
  local branch="$1"
  local severity="$2"
  local ahead="$3"
  local age_h="$4"
  local pr_json="$5"
  local orphan_after_merge="$6"

  local rank
  rank=$(severity_rank "$severity")
  if [[ $rank -lt $min_rank ]]; then
    return
  fi

  if [[ "$FORMAT" == "text" ]]; then
    if [[ "$severity" == "CRITICAL" ]]; then
      echo "${severity} ${branch} | ahead=${ahead} age_h=${age_h}h | pr=${pr_json} | orphan_commits=${orphan_after_merge}"
    elif [[ "$severity" == "WARNING" ]]; then
      echo "${severity} ${branch} | ahead=${ahead} age_h=${age_h}h | no_pr"
    else
      echo "OK ${branch} | ahead=${ahead} age_h=${age_h}h"
    fi
  else
    # JSON line
    echo "{\"branch\":\"${branch}\",\"ahead\":${ahead},\"age_h\":${age_h},\"pr\":${pr_json},\"orphan_after_merge\":${orphan_after_merge},\"severity\":\"${severity}\"}"
  fi
}

for branch in "${!seen_branches[@]}"; do
  # Skip if tip doesn't exist (stale remote ref that has been deleted locally)
  if ! git rev-parse "refs/heads/${branch}" &>/dev/null && \
     ! git rev-parse "refs/remotes/origin/${branch}" &>/dev/null; then
    continue
  fi

  # Resolve tip SHA (prefer local, fall back to remote)
  tip_sha=""
  if git rev-parse "refs/heads/${branch}" &>/dev/null; then
    tip_sha=$(git rev-parse "refs/heads/${branch}")
  else
    tip_sha=$(git rev-parse "refs/remotes/origin/${branch}")
  fi

  # Ownership filter: tip author email must match git config user.email
  if [[ -n "$USER_EMAIL" ]]; then
    tip_author=$(git log -1 --format="%ae" "$tip_sha" 2>/dev/null || true)
    if [[ "$tip_author" != "$USER_EMAIL" ]]; then
      continue
    fi
  fi

  # Last-commit age
  tip_ct=$(git log -1 --format="%ct" "$tip_sha" 2>/dev/null || echo "$NOW")
  age_secs=$(( NOW - tip_ct ))

  # Skip branches older than max-age-days
  if [[ $age_secs -gt $MAX_AGE_SECS ]]; then
    continue
  fi

  age_h=$(( age_secs / 3600 ))

  # Ahead count against main
  ahead=0
  if git rev-parse origin/main &>/dev/null 2>&1; then
    ahead=$(git rev-list --count "origin/main..${tip_sha}" 2>/dev/null || echo 0)
  elif git rev-parse main &>/dev/null 2>&1; then
    ahead=$(git rev-list --count "main..${tip_sha}" 2>/dev/null || echo 0)
  fi

  # PR state via gh
  pr_json="null"
  pr_state=""
  pr_merged_at=""
  pr_number=""
  orphan_after_merge=0

  if [[ $GH_AVAILABLE -eq 1 ]]; then
    pr_raw=$(gh pr list --head "$branch" --state all --limit 5 \
      --json number,state,mergedAt,mergeCommit 2>/dev/null || true)
    if [[ -n "$pr_raw" && "$pr_raw" != "[]" ]]; then
      # Pick the most recent (last item in array is typically newest)
      pr_number=$(echo "$pr_raw" | python3 -c "
import json,sys
prs=json.load(sys.stdin)
if prs:
    p=prs[-1]
    print(p.get('number',''))
" 2>/dev/null || true)
      pr_state=$(echo "$pr_raw" | python3 -c "
import json,sys
prs=json.load(sys.stdin)
if prs:
    p=prs[-1]
    print(p.get('state',''))
" 2>/dev/null || true)
      pr_merged_at=$(echo "$pr_raw" | python3 -c "
import json,sys
prs=json.load(sys.stdin)
if prs:
    p=prs[-1]
    print(p.get('mergedAt') or '')
" 2>/dev/null || true)

      # Build pr_json fragment
      pr_json="{\"number\":${pr_number:-0},\"state\":\"${pr_state}\",\"merged_at\":\"${pr_merged_at}\"}"

      # Count commits after merge
      if [[ "$pr_state" == "MERGED" && -n "$pr_merged_at" ]]; then
        orphan_after_merge=$(git log "${tip_sha}" \
          --after="$pr_merged_at" \
          --format="%H" 2>/dev/null | wc -l | tr -d ' ' || echo 0)
      fi
    fi
  fi

  # ---------------------------------------------------------------------------
  # Classify severity
  # ---------------------------------------------------------------------------
  severity="OK"

  if [[ "$pr_state" == "MERGED" && $orphan_after_merge -gt 0 ]]; then
    severity="CRITICAL"
  elif [[ "$pr_state" != "MERGED" && $ahead -gt 0 ]]; then
    # Extract date from branch name if present (work/machine/YYYY-MM-DD pattern)
    branch_date=""
    if [[ "$branch" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
      branch_date="${BASH_REMATCH[1]}"
    fi

    branch_age_days=0
    if [[ -n "$branch_date" ]]; then
      branch_ts=$(date -d "$branch_date" +%s 2>/dev/null || \
                  python3 -c "import datetime; print(int(datetime.datetime.strptime('$branch_date','%Y-%m-%d').timestamp()))" 2>/dev/null || \
                  echo "0")
      if [[ $branch_ts -gt 0 ]]; then
        branch_age_days=$(( (NOW - branch_ts) / 86400 ))
      fi
    fi

    if [[ $branch_age_days -ge 2 || $age_h -gt 36 ]]; then
      severity="WARNING"
    fi
  fi

  emit_result "$branch" "$severity" "$ahead" "$age_h" "${pr_json:-null}" "$orphan_after_merge"

done
