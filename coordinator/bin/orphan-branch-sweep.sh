#!/usr/bin/env bash
# orphan-branch-sweep.sh — enumerate suspect work/feature branches across the current repo
#
# Spec backlink: archive/specs/2026-05-01-orphan-branch-prevention.md § 1.1
#
# Purpose: read-only scan of user-owned work/* and feature/* branches. For each
# qualifying branch, determines whether it has commits that post-date a merged PR
# (CRITICAL), is an open branch with no PR and a branch-name date ≥2 days old or
# age_h>36 (WARNING), or is clean (OK). Emits JSON lines to stdout.
#
# Negative-spec: this script never mutates branches, refs, or PRs. It is purely
# diagnostic. It does NOT archive, delete, or rename any branch.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
    echo "WARN: orphan-branch-sweep.sh: bash 4+ required; skipping" >&2
    exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"

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
# Guard: jq is required for --format json. Auto-fall-back to text and warn
# rather than dying under `set -e`, so /workday-start (which calls this in
# JSON mode) still surfaces severities on machines missing jq. Install hint
# is the actionable remediation; the fallback is the safety net.
#
# NOTE for downstream callers: when this fallback fires, stdout is text not
# JSON. Callers that pipe into a JSON parser must either check stderr for the
# "falling back to --format text" signal, or accept that JSON-parse errors in
# this path are jq-missing symptoms (not malformed data).
# ---------------------------------------------------------------------------
if [[ "$FORMAT" == "json" ]] && ! command -v jq &>/dev/null; then
  echo "orphan-branch-sweep.sh: jq not found on PATH — falling back to --format text." >&2
  echo "  Install jq for JSON output: https://jqlang.org/download/" >&2
  FORMAT="text"
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
    # only work/* and feature/* branches (case-insensitive — legacy work/MACHINE-A/... must match)
    shopt -s nocasematch
    if [[ "$branch" =~ ^(work|feature)/ ]]; then
      seen_branches["$branch"]=1
    fi
    shopt -u nocasematch
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
    jq -cn \
      --arg branch "$branch" \
      --argjson ahead "$ahead" \
      --argjson age_h "$age_h" \
      --argjson pr "$pr_json" \
      --argjson orphan_after_merge "$orphan_after_merge" \
      --arg severity "$severity" \
      '{branch: $branch, ahead: $ahead, age_h: $age_h, pr: $pr, orphan_after_merge: $orphan_after_merge, severity: $severity}'
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
      pr_number=$(echo "$pr_raw" | "${PYTHON_BIN:-python3}" -c " # verify-no-console-flash: allow — on-demand orphan branch sweep, not session-hot-path
import json,sys
prs=json.load(sys.stdin)
if prs:
    p=prs[-1]
    print(p.get('number',''))
" 2>/dev/null || true)
      pr_state=$(echo "$pr_raw" | "${PYTHON_BIN:-python3}" -c " # verify-no-console-flash: allow — on-demand orphan branch sweep, not session-hot-path
import json,sys
prs=json.load(sys.stdin)
if prs:
    p=prs[-1]
    print(p.get('state',''))
" 2>/dev/null || true)
      pr_merged_at=$(echo "$pr_raw" | "${PYTHON_BIN:-python3}" -c " # verify-no-console-flash: allow — on-demand orphan branch sweep, not session-hot-path
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
    # Re-verify against the live ref-graph before raising CRITICAL.
    # The orphan_after_merge count is timestamp-derived (git log --after) and
    # lags the live graph: after a fast-forward merge or a delete-only
    # operation, the cache/timestamp pass still sees commits that the
    # ref-graph reports as fully merged. Cross-check with rev-list against
    # main — if no commits remain unmerged, the branch is not orphaned.
    unmerged=0
    if git rev-parse origin/main &>/dev/null 2>&1; then
      unmerged=$(git rev-list --count "${tip_sha}" ^origin/main 2>/dev/null || echo 0)
    elif git rev-parse main &>/dev/null 2>&1; then
      unmerged=$(git rev-list --count "${tip_sha}" ^main 2>/dev/null || echo 0)
    fi
    if [[ "${unmerged}" -gt 0 ]]; then
      # Daily-branch carry-forward check: under the work/{machine}/{date}
      # discipline, a merged PR closes the day, but the branch often keeps
      # accruing commits that get carried forward through subsequent daily
      # branches (work/.../2026-05-04 → 2026-05-05 → 2026-05-06 → ...). If
      # the tip is an ancestor of any other live work/* or feature/* branch
      # (or HEAD), the work is not orphaned — it'll reach main on the next
      # merge of the descendant branch.
      carried_forward=0
      head_sha=$(git rev-parse HEAD 2>/dev/null || true)
      if [[ -n "$head_sha" && "$head_sha" != "$tip_sha" ]]; then
        if git merge-base --is-ancestor "$tip_sha" "$head_sha" 2>/dev/null; then
          carried_forward=1
        fi
      fi
      if [[ $carried_forward -eq 0 ]]; then
        for other in "${!seen_branches[@]}"; do
          [[ "$other" == "$branch" ]] && continue
          other_tip=""
          if git rev-parse "refs/heads/${other}" &>/dev/null; then
            other_tip=$(git rev-parse "refs/heads/${other}")
          elif git rev-parse "refs/remotes/origin/${other}" &>/dev/null; then
            other_tip=$(git rev-parse "refs/remotes/origin/${other}")
          fi
          [[ -z "$other_tip" || "$other_tip" == "$tip_sha" ]] && continue
          if git merge-base --is-ancestor "$tip_sha" "$other_tip" 2>/dev/null; then
            carried_forward=1
            break
          fi
        done
      fi
      if [[ $carried_forward -eq 1 ]]; then
        # Carried forward into a descendant branch — not orphaned.
        # orphan_after_merge stays in JSON for forensics.
        severity="OK"
      else
        severity="CRITICAL"
      fi
    else
      # Stale-cache false positive — branch is fully merged into main.
      # Downgrade to OK; orphan_after_merge stays in the JSON for forensics.
      severity="OK"
    fi
  elif [[ "$pr_state" != "MERGED" && $ahead -gt 0 ]]; then
    # Use last-commit time (tip_ct, already computed above) for age rather than
    # parsing the branch-name start-date. This prevents false-positive WARNING
    # noise on legitimate active span branches like work/machine-a/2026-05-01to07
    # where the start-date is days old but the branch is still actively committed.
    # (the Staff Engineer R1 F6 — promoted from anti-scope "verify only" to explicit fix.)
    branch_age_days=$(( age_secs / 86400 ))

    if [[ $branch_age_days -ge 2 || $age_h -gt 36 ]]; then
      severity="WARNING"
    fi
  fi

  emit_result "$branch" "$severity" "$ahead" "$age_h" "${pr_json:-null}" "$orphan_after_merge"

done
