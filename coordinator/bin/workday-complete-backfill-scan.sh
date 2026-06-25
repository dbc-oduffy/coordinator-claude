#!/usr/bin/env bash
# workday-complete-backfill-scan.sh — detect skipped workdays that need a daily-summary backfill.
#
# Emits TSV, one row per past day (within --lookback) that has >=1 non-merge commit but NO
# archive/daily-summaries/<date>.md on disk:
#
#     <YYYY-MM-DD>\t<commit_count>\t<baseline_sha>\t<tip_sha>
#
# baseline_sha is the parent of that day's OLDEST commit; tip_sha is that day's NEWEST commit.
# The backfill analyst diffs baseline_sha..tip_sha and queries completions --where created=<date>.
# Empty stdout = no missed days (the common, healthy case). Rows are emitted OLDEST-FIRST so the
# caller backfills chronologically.
#
# Bounded by --lookback (default 14 days) so a long-idle repo never triggers an unbounded
# historical backfill — older gaps are deliberately out of scope (surface to PM if needed).
#
# Why this exists: /workday-complete's daily window is a rolling ~24h (YESTERDAY 23:59Z..TODAY
# 23:59Z). A day with no ceremony falls permanently between windows. This scan + step9 --for-date
# closes that gap. Converged-on independently by project-opticon-em (cross-repo memo 2026-06-23).
#
# Portable: bash 3.2 + BSD/GNU coreutils. python3-first date math with an epoch fallback.

# Review: code-reviewer — bash >=4 required for BASH_VERSINFO; guard must be reachable on 3.2
# (only arithmetic and echo used here; no bash-4-only syntax before this guard).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (running ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

set -euo pipefail

LOOKBACK=14
TODAY_OVERRIDE=""   # TEST-ONLY — not used by the production callers

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lookback) LOOKBACK="${2:?--lookback needs a value}"; shift 2 ;;
    --today)    TODAY_OVERRIDE="${2:?--today needs a value}"; shift 2 ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *)  echo "Unexpected argument: $1" >&2; exit 1 ;;
  esac
done

if ! [[ "$LOOKBACK" =~ ^[0-9]+$ ]] || [[ "$LOOKBACK" -lt 1 ]]; then
  echo "ERROR: --lookback must be a positive integer (got '${LOOKBACK}')" >&2
  exit 1
fi

# COORDINATOR_ROOT is a TEST-ONLY repo-root override; a live ceremony leaves it
# unset so it defaults to the cwd git toplevel (the correct project repo). Warn
# loud if it is set to a path other than the cwd toplevel — catches copy-paste of
# the test-only override into a live ceremony (the 2026-06-24 mis-root bug). Paths
# are canonicalized (pwd -P) so a symlinked tmpdir is not a false positive; set
# COORDINATOR_ROOT_WARN_SUPPRESS=1 to silence (tests pointing at an in-tree fixture).
_top_raw="$(git rev-parse --show-toplevel 2>/dev/null || true)"
_cwd_top=""
if [[ -n "${_top_raw}" ]]; then
  _cwd_top="$(cd "${_top_raw}" 2>/dev/null && pwd -P || true)"
fi
if [[ -n "${COORDINATOR_ROOT:-}" && "${COORDINATOR_ROOT_WARN_SUPPRESS:-}" != "1" && -n "${_cwd_top}" ]]; then
  _cr_real="$(cd "${COORDINATOR_ROOT}" 2>/dev/null && pwd -P || echo "${COORDINATOR_ROOT}")"
  if [[ "${_cr_real}" != "${_cwd_top}" ]]; then
    echo "WARNING: COORDINATOR_ROOT='${COORDINATOR_ROOT}' differs from the cwd git toplevel '${_cwd_top}'. COORDINATOR_ROOT is a TEST-ONLY override; continuing with it as the repo root for this run. If this is a live ceremony on a consumer project, unset COORDINATOR_ROOT and re-run (COORDINATOR_ROOT_WARN_SUPPRESS=1 silences this in tests)." >&2
  fi
fi

ROOT="${COORDINATOR_ROOT:-${_cwd_top}}"
if [[ -z "${ROOT}" ]]; then
  echo "ERROR: cwd is not a git repo and COORDINATOR_ROOT is not set" >&2
  exit 1
fi

TODAY="${TODAY_OVERRIDE:-$(date -u +%Y-%m-%d)}"

# date_minus <YYYY-MM-DD> <days> -> prints the resulting date. python3-first, epoch fallback.
date_minus() {
  local d="$1" n="$2" out=""
  if command -v python3 >/dev/null 2>&1; then
    out="$(python3 -c "from datetime import date,timedelta;print(date.fromisoformat('${d}')-timedelta(days=${n}))" 2>/dev/null || true)"
  fi
  if [[ -z "${out}" ]]; then
    local e
    e="$(date -u -j -f %Y-%m-%d "${d}" +%s 2>/dev/null || date -u -d "${d}" +%s 2>/dev/null || true)"
    if [[ -n "${e}" ]]; then
      e=$(( e - n * 86400 ))
      out="$(date -u -j -f %s "${e}" +%Y-%m-%d 2>/dev/null || date -u -d "@${e}" +%Y-%m-%d 2>/dev/null || true)"
    fi
  fi
  printf '%s' "${out}"
}

# Walk candidate days oldest-first: today-LOOKBACK .. today-1.
i="${LOOKBACK}"
while [[ "${i}" -ge 1 ]]; do
  D="$(date_minus "${TODAY}" "${i}")"
  i=$(( i - 1 ))
  [[ -n "${D}" ]] || continue

  # Already covered? Skip.
  if [[ -f "${ROOT}/archive/daily-summaries/${D}.md" ]]; then
    continue
  fi

  PREV="$(date_minus "${D}" 1)"
  [[ -n "${PREV}" ]] || continue

  # Review: code-reviewer — single git log pass (F2+F3): newest-first list; derive CNT, TIP,
  # FIRST from it. || true prevents set -e kill on git failure (yields empty = skip day).
  # Day window: (PREV 23:59:59Z, D 23:59:59Z] == all of D's non-merge commits.
  _DAY_LOG="$(git -C "${ROOT}" log --no-merges --format=%H \
              --after="${PREV}T23:59:59Z" --before="${D}T23:59:59Z" 2>/dev/null || true)"
  CNT="$(printf '%s' "${_DAY_LOG}" | grep -c . || true)"
  # grep -c on empty string returns 0 (exit 1 on no match); normalise to numeric.
  [[ "${CNT}" -gt 0 ]] 2>/dev/null || continue

  TIP="$(printf '%s' "${_DAY_LOG}" | head -1)"    # newest commit (git log default order)
  FIRST="$(printf '%s' "${_DAY_LOG}" | tail -1)"   # oldest commit

  # ROOT-COMMIT FALLBACK: if the oldest commit has no parent, baseline=oldest → empty but valid range.
  BASE="$(git -C "${ROOT}" rev-parse "${FIRST}^" 2>/dev/null || printf '%s' "${FIRST}")"

  printf '%s\t%s\t%s\t%s\n' "${D}" "${CNT}" "${BASE}" "${TIP}"
done
