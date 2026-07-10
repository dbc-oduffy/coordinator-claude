#!/usr/bin/env bash
# workday-complete-backfill-scan.sh — detect skipped workdays that need a daily-summary backfill.
#
# Emits TSV rows per past day (within --lookback) that need backfill attention. Three row shapes
# may appear in one run (lookback may span days with and without work/{machine}/* refs):
#
# (1) Global-fallback — no work/{machine}/* refs present for that day:
#       <YYYY-MM-DD>\t<commit_count>\t<baseline_sha>\t<tip_sha>
#     baseline_sha is the parent of that day's OLDEST commit; tip_sha is NEWEST. Analyst diffs
#     baseline_sha..tip_sha and queries completions --where created=<date>.
#
# (2) Per-machine gap — work/{machine}/* refs present, machine has unrecorded/stale tip:
#       <YYYY-MM-DD>\t<machine>\t<BASE>\t<TIP>
#     BASE is the parent of the oldest machine commit in the day window — always a real sha
#     derived from the git log independently of any covered_tip_sha anchor, so the
#     never-wrapped (missing-anchor) case and the stale-anchor case are both covered.
#     TIP is the newest machine commit in the window.
# Spec backlink: docs/plans/2026-07-07-workday-complete-local-day-and-targeted-wrap.md § C3
#
# (3) Dangling-defer — summary declares defers_to: <target> but target changelog absent (also on
#     stderr as DANGLING-DEFER: ...):
#       DANGLING-DEFER\t<date>\t<machine>\t<defer_target>
#
# Row discriminator: col-1 == "DANGLING-DEFER" → shape (3); col-2 matches ^[0-9]+$ → shape (1);
# else → shape (2). Machine names must not be purely numeric — the branch naming convention
# work/{hostname}/... already ensures this in practice (hostnames are not all-digit). A single
# run may interleave all three shapes when the lookback window spans branch-ref and
# branch-ref-absent days.
#
# Empty stdout = no missed days (the common, healthy case). Rows are emitted OLDEST-FIRST so the
# caller backfills chronologically.
#
# Bounded by --lookback (default 14 days) so a long-idle repo never triggers an unbounded
# historical backfill — older gaps are deliberately out of scope (surface to PM if needed).
#
# Why this exists: /workday-complete's daily window is a rolling ~24h (YESTERDAY 23:59..TODAY
# 23:59 local TZ — no Z suffix, so git interprets in the committer's local timezone).
# A day with no ceremony falls permanently between windows. This scan + step9 --for-date
# closes that gap. Converged-on independently by example-cockpit-repo-em (cross-repo memo 2026-06-23).
#
# Portable: bash 3.2 + BSD/GNU coreutils. python3-first date math with an epoch fallback.

# Review: code-reviewer — bash >=4 required for BASH_VERSINFO; guard must be reachable on 3.2
# (only arithmetic and echo used here; no bash-4-only syntax before this guard).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (running ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# PLUGIN_ROOT and lib sourcing
# ---------------------------------------------------------------------------
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_DAILY_DAY="${PLUGIN_ROOT}/lib/coordinator-daily-day.sh"

if [[ ! -f "${LIB_DAILY_DAY}" ]]; then
  echo "ERROR: coordinator-daily-day lib not found at ${LIB_DAILY_DAY}" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${LIB_DAILY_DAY}"

# Source state-root seam — routes per-repo state/ refs through coordinator_state_root
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4 / AC4
# shellcheck source=lib/coordinator-state-root.sh
source "${PLUGIN_ROOT}/lib/coordinator-state-root.sh"

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

# Resolve per-repo state root through the seam (AC4 — coordinator_state_root adoption).
# coordinator_state_root returns $EXAMPLE_ORCHESTRATION_HUB_ROOT/state when cwd git root is the meta-repo;
# otherwise returns $GIT_ROOT/state (sibling repo case). Called once and cached to avoid
# repeated git rev-parse in the lookback loop.
#
# COORDINATOR_ROOT is the TEST-ONLY repo-root override resolved into ROOT above. When it
# is set, the state root MUST be derived from that SAME override so the scan has one
# consistent notion of "this repo" — otherwise coordinator_state_root re-resolves the cwd
# git toplevel (ignoring the override) and the dangling-defer changelog lookup below points
# at the real repo, not the fixture. Production leaves COORDINATOR_ROOT unset, so the seam
# is used unchanged (correctly routing the meta-repo to example-orchestration-hub-central state).
if [[ -n "${COORDINATOR_ROOT:-}" ]]; then
  _REPO_STATE_ROOT="${ROOT}/state"
else
  _REPO_STATE_ROOT="$(coordinator_state_root)"
fi

TODAY="${TODAY_OVERRIDE:-$(coordinator_local_day)}"

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

  PREV="$(date_minus "${D}" 1)"
  [[ -n "${PREV}" ]] || continue

  # Collect machines with work/{machine}/* branches (local refs and origin/ remotes).
  # '*' in for-each-ref fnmatch does not match '/', so 'work/*/*' matches exactly
  # refs/heads/work/<machine>/<rest> — machine is the first path component after 'work/'.
  # Spec backlink: docs/plans/2026-07-01-workday-complete-multi-machine-coverage.md § C2
  declare -A _MACHINE_SET=()
  while IFS= read -r _ref; do
    [[ -z "${_ref}" ]] && continue
    _rest=""
    if [[ "${_ref}" == refs/heads/work/* ]]; then
      _rest="${_ref#refs/heads/work/}"
    elif [[ "${_ref}" == refs/remotes/origin/work/* ]]; then
      _rest="${_ref#refs/remotes/origin/work/}"
    fi
    _mach="${_rest%%/*}"
    [[ -n "${_mach}" ]] && _MACHINE_SET["${_mach}"]=1
  done < <(git -C "${ROOT}" for-each-ref --format='%(refname)' \
    'refs/heads/work/*/*' 'refs/remotes/origin/work/*/*' 2>/dev/null || true)

  if [[ "${#_MACHINE_SET[@]}" -eq 0 ]]; then
    # FALLBACK: no work/{machine}/* refs present (fully-merged history or non-work-branch repo).
    # Degrade to the original single-file existence check + global-tip scan.
    # Documented residual: cannot distinguish per-machine coverage in this case.
    if [[ -f "${ROOT}/archive/daily-summaries/${D}.md" ]]; then
      continue
    fi
    # Review: code-reviewer — single git log pass (F2+F3): newest-first list; derive CNT, TIP,
    # FIRST from it. || true prevents set -e kill on git failure (yields empty = skip day).
    # Day window: (PREV 23:59:59, D 23:59:59] local TZ == all of D's non-merge commits.
    _DAY_LOG="$(git -C "${ROOT}" log --no-merges --format=%H \
                --after="${PREV}T23:59:59" --before="${D}T23:59:59" 2>/dev/null || true)"
    CNT="$(printf '%s' "${_DAY_LOG}" | grep -c . || true)"
    # grep -c on empty string returns 0 (exit 1 on no match); normalise to numeric.
    [[ "${CNT}" -gt 0 ]] 2>/dev/null || continue
    TIP="$(printf '%s' "${_DAY_LOG}" | head -1)"    # newest commit (git log default order)
    FIRST="$(printf '%s' "${_DAY_LOG}" | tail -1)"   # oldest commit
    # ROOT-COMMIT FALLBACK: if the oldest commit has no parent, baseline=oldest → empty but valid range.
    BASE="$(git -C "${ROOT}" rev-parse "${FIRST}^" 2>/dev/null || printf '%s' "${FIRST}")"
    printf '%s\t%s\t%s\t%s\n' "${D}" "${CNT}" "${BASE}" "${TIP}"
    continue
  fi

  # Per-machine predicate: for each machine with work/* branches, check coverage for day D.
  # Output format: <date>\t<machine>\t<recorded_tip>\t<actual_tip>
  for _mach in "${!_MACHINE_SET[@]}"; do
    # Collect commits from ALL of this machine's branches within day D's window.
    # Format per line: "<committer_unix_ts> <sha>" — allows picking newest by numeric sort.
    _mach_log=""
    while IFS= read -r _mref; do
      [[ -z "${_mref}" ]] && continue
      _branch_log="$(git -C "${ROOT}" log --no-merges --format='%ct %H' \
        --after="${PREV}T23:59:59" --before="${D}T23:59:59" \
        "${_mref}" 2>/dev/null || true)"
      [[ -n "${_branch_log}" ]] && _mach_log="${_mach_log}${_branch_log}"$'\n'
    done < <(git -C "${ROOT}" for-each-ref --format='%(refname)' \
      "refs/heads/work/${_mach}/" "refs/remotes/origin/work/${_mach}/" 2>/dev/null || true)

    # Newest commit across all machine branches in window (highest committer timestamp).
    _mach_tip="$(printf '%s' "${_mach_log}" | sort -rn 2>/dev/null | \
      awk '!seen[$2]++ && NF>=2{print $2; exit}' || true)"
    [[ -n "${_mach_tip}" ]] || continue  # No commits for this machine on day D.

    # Oldest commit across all machine branches in window (lowest committer timestamp).
    # Used to derive the machine-scoped day-window BASE for the C3 commit-span output.
    # (sort -n ascending = oldest-first; take the first deduped sha)
    _mach_oldest="$(printf '%s' "${_mach_log}" | sort -n 2>/dev/null | \
      awk '!seen[$2]++ && NF>=2{print $2; exit}' || true)"
    # BASE = parent of the oldest machine commit; fall back to oldest itself for root commits.
    # This is always a real sha — independent of any covered_tip_sha anchor.
    _mach_base=""
    if [[ -n "${_mach_oldest}" ]]; then
      _mach_base="$(git -C "${ROOT}" rev-parse "${_mach_oldest}^" 2>/dev/null || \
        printf '%s' "${_mach_oldest}")"
    fi

    # Read covered_tip_sha and optional defers_to field from summary.
    # Check per-machine summary first, then legacy date-only file.
    _recorded=""
    _defer_target=""
    for _spath in \
      "${ROOT}/archive/daily-summaries/${D}-${_mach}.md" \
      "${ROOT}/archive/daily-summaries/${D}.md"; do
      if [[ -f "${_spath}" ]]; then
        _recorded="$(grep -m1 '^covered_tip_sha:' "${_spath}" 2>/dev/null | \
          awk '{print $2}' || true)"
        _defer_target="$(grep -m1 '^defers_to:' "${_spath}" 2>/dev/null | \
          awk '{print $2}' || true)"
        break
      fi
    done

    # Dangling-defer guard: if summary declares defers_to: <target>, the target's
    # per-machine week-changelog must exist for the defer to be valid. Without it,
    # the defer is a dangling pointer — the claimed coverage does not exist on disk.
    # Spec backlink: docs/wiki/daily-summary-procedure.md § Machine-Defer Convention
    if [[ -n "${_defer_target}" ]]; then
      _changelog="${_REPO_STATE_ROOT}/week-changelog/${D}-${_defer_target}.md"
      if [[ ! -f "${_changelog}" ]]; then
        echo "DANGLING-DEFER: ${D} ${_mach} -> ${_defer_target} (${_changelog} not found)" >&2
        printf 'DANGLING-DEFER\t%s\t%s\t%s\n' "${D}" "${_mach}" "${_defer_target}"
      fi
    fi

    # Determine gap: missing or stale covered_tip_sha vs. machine's actual window-tip.
    _is_gap=0
    if [[ -z "${_recorded}" ]]; then
      # Missing covered_tip_sha on a committed-work day is always a GAP (fail-loud).
      _is_gap=1
    else
      # Canonicalize both SHAs before comparison (recorded may be abbreviated).
      _rec_full="$(git -C "${ROOT}" rev-parse --verify "${_recorded}^{commit}" 2>/dev/null || true)"
      _act_full="$(git -C "${ROOT}" rev-parse --verify "${_mach_tip}^{commit}" 2>/dev/null || true)"
      if [[ -z "${_rec_full}" || -z "${_act_full}" ]]; then
        _is_gap=1  # Unresolvable SHA → conservative gap
      elif [[ "${_rec_full}" == "${_act_full}" ]]; then
        _is_gap=0  # Recorded tip == actual tip → fully covered
      elif git -C "${ROOT}" merge-base --is-ancestor "${_rec_full}" "${_act_full}" 2>/dev/null; then
        # Recorded is a strict ancestor of actual → newer unrecorded work exists → GAP.
        _is_gap=1
      fi
      # merge-base exits non-zero (diverged/unrelated) → not a gap on this axis.
    fi

    if [[ "${_is_gap}" -eq 1 ]]; then
      # Exclusive-commit gate: a real gap requires ≥1 commit reachable from THIS machine's
      # branch that is NOT reachable from any OTHER machine's branch, within day D's window.
      # Post-reconcile-merge, foreign commits become reachable here; --no-merges drops merge
      # commits but not the foreign non-merge commits they pull in. rev-list <tip> ^<others>
      # subtracts the union of other machines' reachable sets → leaves only this machine's own.
      # Also subtracts main/origin/main: once a wrapping machine's work/* branch is merged to
      # main and pruned, that work stays reachable from main but from no work/* ref, so without
      # this it would count as permanently "exclusive" here → an uncloseable false gap on every
      # run. main-integrated commits are shared history, not this machine's undocumented work.
      # Residual accepted tradeoff (narrower than before): a machine that authors genuine work
      # AND merges it to main in the same window-day WITHOUT writing a daily summary will not be
      # flagged — a compensating merge-to-main summary-coverage assertion is filed separately to
      # the improvement queue.
      # Spec backlink: cross-repo/archive/2026-07-06-backfill-scan-multimachine-false-positive.md
      # Spec backlink: state/handoffs/2026-07-10_002326_backfill-scan-cross-machine-main-exclusion.md
      _excl=()
      for _other in "${!_MACHINE_SET[@]}"; do
        [[ "${_other}" == "${_mach}" ]] && continue
        while IFS= read -r _oref; do
          [[ -n "${_oref}" ]] && _excl+=( "^${_oref}" )
        done < <(git -C "${ROOT}" for-each-ref --format='%(refname)' \
          "refs/heads/work/${_other}/" "refs/remotes/origin/work/${_other}/" 2>/dev/null || true)
      done
      # main/origin/main resolved via for-each-ref (not a hard ^ref add) so an absent/renamed
      # main branch silently contributes nothing rather than erroring the rev-list (which, piped
      # through 2>/dev/null | grep -c ., would yield 0 → total over-suppression of every machine).
      while IFS= read -r _mref; do
        [[ -n "${_mref}" ]] && _excl+=( "^${_mref}" )
      done < <(git -C "${ROOT}" for-each-ref --format='%(refname)' \
        refs/heads/main refs/remotes/origin/main 2>/dev/null || true)
      _exclusive="$(git -C "${ROOT}" rev-list --no-merges \
        --after="${PREV}T23:59:59" --before="${D}T23:59:59" \
        "${_mach_tip}" "${_excl[@]}" 2>/dev/null | grep -c . || true)"
      if [[ "${_exclusive:-0}" -eq 0 ]]; then
        # No commit exclusive to this machine on day D → reconcile-only. Not a gap.
        echo "NO-EXCLUSIVE-WORK: ${D} ${_mach} (reconcile-only; tip ${_mach_tip} inherited)" >&2
      else
        # C3: emit BASE..TIP where BASE is the parent of the oldest machine commit —
        # always a real sha regardless of whether a covered_tip_sha anchor exists.
        printf '%s\t%s\t%s\t%s\n' "${D}" "${_mach}" "${_mach_base:-${_mach_tip}}" "${_mach_tip}"
      fi
    fi
  done
done
