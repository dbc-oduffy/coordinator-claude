#!/usr/bin/env bash
# workday-complete-backfill-inject-anchor.sh — Phase A0 mechanical anchor injection.
#
# Injects covered_tip_sha/covered_machine anchors into a pre-existing daily summary that
# lacks them. Called before any Phase A analyst fan-out so format-migration gap rows are
# closed deterministically without dispatching agents.
#
# Usage: workday-complete-backfill-inject-anchor.sh <ROOT> <DATE> <DESCENDANT_TIP_SHA> [TODAY] [MACHINE]
#   ROOT               — repo root (path; must be a git worktree)
#   DATE               — date in YYYY-MM-DD format
#   DESCENDANT_TIP_SHA — the per-day descendant tip SHA (caller resolves from scan row;
#                        this script verifies it resolves via git rev-parse)
#   TODAY              — optional override for "today" (YYYY-MM-DD); defaults to date +%Y-%m-%d
#   MACHINE            — optional machine name (caller knows from scan row; skips branch-ref enumeration)
#
# Exit codes:
#   0  — anchor injected successfully (also covers a STALE anchor bumped to the
#         descendant tip — recorded covered_tip_sha was a strict ancestor of the
#         target, or unresolvable, so it was rewritten in place; no re-injection)
#   10 — already anchored (idempotent skip; no change made) — anchor is present AND
#         fresh: recorded covered_tip_sha == target, or recorded is a descendant of
#         / diverged from target (scan does not flag it as a gap)
#   20 — summary file absent (real content gap → caller routes to Phase A analyst)
#   30 — content-completeness or commit-density guard fired (summary looks incomplete for
#         the date range → caller routes to Phase A content-assembly analyst; no anchor injected)
#
# Anchor format injected (bare line-start — scan greps '^covered_tip_sha:'):
#   covered_tip_sha: <full-40-char-sha>
#   covered_machine: <machine>
#   > _Record anchor injected <TODAY> by /workday-complete backfill (mechanical) — summary content pre-existing._
#
# Spec backlink: docs/plans/2026-07-02-backfill-anchor-injection-contract.md § Deliverable A
# Negative-spec: anchors are bare line-start, NOT blockquoted ('> covered_tip_sha:') — the
#   backfill scan greps '^covered_tip_sha:'; a blockquote prefix silently breaks the match.

# bash >=4 guard — only arithmetic before this line so the guard is reachable on bash 3.2
# (bash-4-only syntax like declare -A or ${v^^} must not appear before this check).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (running ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -lt 3 ]]; then
  echo "Usage: $(basename "$0") <ROOT> <DATE> <DESCENDANT_TIP_SHA> [TODAY] [MACHINE]" >&2
  exit 1
fi

ROOT_RAW="$1"
DATE="$2"
DESCENDANT_TIP_SHA="$3"
TODAY="${4:-$(date +%Y-%m-%d)}"
_MACHINE_ARG="${5:-}"

# Resolve ROOT to an absolute path (fail loud if it doesn't exist)
ROOT="$(cd "$ROOT_RAW" 2>/dev/null && pwd)" || {
  echo "ERROR: ROOT does not exist or is not accessible: ${ROOT_RAW}" >&2
  exit 1
}

# Validate DATE format (YYYY-MM-DD)
if ! [[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: DATE must be YYYY-MM-DD (got '${DATE}')" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Verify the descendant tip SHA resolves in this repo (fail loud on bad SHA)
# ---------------------------------------------------------------------------
FULL_SHA=""
FULL_SHA="$(git -C "$ROOT" rev-parse --verify "${DESCENDANT_TIP_SHA}^{commit}" 2>/dev/null)" || true
if [[ -z "$FULL_SHA" ]]; then
  echo "ERROR: DESCENDANT_TIP_SHA '${DESCENDANT_TIP_SHA}' does not resolve to a commit in ${ROOT}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Derive the covered_machine value
# Resolution order:
#   1. CLI arg (caller knows machine from scan row — preferred, avoids stale branch-ref lookup)
#   2. git for-each-ref: find a work/<machine>/ branch containing the SHA
#   3. cs_compute_machine from coordinator-daily-branch lib (machine-local registry / hostname)
#   4. "unknown" fallback
# ---------------------------------------------------------------------------
_MACHINE=""
if [[ -n "$_MACHINE_ARG" ]]; then
  _MACHINE="$_MACHINE_ARG"
else
  while IFS= read -r _ref; do
    if [[ "$_ref" =~ ^refs/heads/work/([^/]+)/ ]]; then
      _MACHINE="${BASH_REMATCH[1]}"
      break
    elif [[ "$_ref" =~ ^refs/remotes/origin/work/([^/]+)/ ]]; then
      _MACHINE="${BASH_REMATCH[1]}"
      break
    fi
  done < <(git -C "$ROOT" for-each-ref --contains "$FULL_SHA" \
      --format='%(refname)' 'refs/heads/work/' 'refs/remotes/origin/work/' 2>/dev/null || true)

  if [[ -z "$_MACHINE" ]]; then
    _LIB_BRANCH="${PLUGIN_ROOT}/lib/coordinator-daily-branch.sh"
    if [[ -f "$_LIB_BRANCH" ]]; then
      # shellcheck source=/dev/null
      source "$_LIB_BRANCH"
      _MACHINE="$(cs_compute_machine 2>/dev/null || true)"
    fi
    _MACHINE="${_MACHINE:-unknown}"
  fi
fi

# ---------------------------------------------------------------------------
# Resolve target summary file
# Preference order:
#   1. archive/daily-summaries/<DATE>-<machine>.md  (per-machine, derived above)
#   2. archive/daily-summaries/<DATE>-*.md          (any per-machine file for this date)
#   3. archive/daily-summaries/<DATE>.md            (legacy flat file)
# ---------------------------------------------------------------------------
TARGET_FILE=""

# Candidate 1: per-machine file with derived machine name
_cand1="${ROOT}/archive/daily-summaries/${DATE}-${_MACHINE}.md"
if [[ -f "$_cand1" ]]; then
  TARGET_FILE="$_cand1"
fi

# Candidate 2: any per-machine file for this date (glob)
if [[ -z "$TARGET_FILE" ]]; then
  for _cand in "${ROOT}/archive/daily-summaries/${DATE}-"*.md; do
    if [[ -f "$_cand" ]]; then
      TARGET_FILE="$_cand"
      break
    fi
  done
fi

# Candidate 3: legacy flat file
if [[ -z "$TARGET_FILE" ]]; then
  _cand3="${ROOT}/archive/daily-summaries/${DATE}.md"
  if [[ -f "$_cand3" ]]; then
    TARGET_FILE="$_cand3"
  fi
fi

if [[ -z "$TARGET_FILE" ]]; then
  echo "summary-absent: no summary file found for ${DATE} in ${ROOT}/archive/daily-summaries/" >&2
  exit 20
fi

# ---------------------------------------------------------------------------
# Idempotency check — already anchored, and is it FRESH?
#
# A pure presence check treats a STALE anchor (recorded covered_tip_sha is a strict
# ancestor of the target descendant tip) as "already anchored", but the sibling scan
# (workday-complete-backfill-scan.sh) defines a gap as: recorded is a strict ancestor
# of the machine's actual window-tip, OR recorded is unresolvable. Mirror that exact
# predicate here so a stale anchor doesn't get reported "already-anchored" forever
# while scan re-flags it as a gap on every run.
# Spec backlink: docs/plans/2026-07-02-backfill-anchor-injection-contract.md § Deliverable A
# ---------------------------------------------------------------------------
_recorded="$(grep -m1 '^covered_tip_sha:' "$TARGET_FILE" 2>/dev/null | awk '{print $2}' || true)"
if [[ -n "$_recorded" ]]; then
  _rec_full="$(git -C "$ROOT" rev-parse --verify "${_recorded}^{commit}" 2>/dev/null || true)"
  if [[ -n "$_rec_full" && "$_rec_full" == "$FULL_SHA" ]]; then
    echo "already-anchored (fresh): ${TARGET_FILE}" >&2
    exit 10
  elif [[ -n "$_rec_full" ]] && git -C "$ROOT" merge-base --is-ancestor "$_rec_full" "$FULL_SHA" 2>/dev/null; then
    # Recorded is a strict ancestor of target (the equal case already returned above) → BUMP.
    _TMP="${TARGET_FILE}.tmp.$$"
    trap 'rm -f "$_TMP"' EXIT
    awk -v sha="$FULL_SHA" -v m="$_MACHINE" '
      !stip && /^covered_tip_sha:/ { print "covered_tip_sha: " sha; stip=1; next }
      !smach && /^covered_machine:/ { print "covered_machine: " m; smach=1; next }
      { print }
    ' "$TARGET_FILE" > "$_TMP"
    mv "$_TMP" "$TARGET_FILE"
    echo "bumped: ${TARGET_FILE}  covered_tip_sha ${_recorded} -> ${FULL_SHA}" >&2
    echo "TARGET=${TARGET_FILE}"
    exit 0
  elif [[ -z "$_rec_full" ]]; then
    # Recorded doesn't resolve (stale/rewritten history) — scan treats this as a
    # conservative gap; bump to a known-good SHA clears it.
    _TMP="${TARGET_FILE}.tmp.$$"
    trap 'rm -f "$_TMP"' EXIT
    awk -v sha="$FULL_SHA" -v m="$_MACHINE" '
      !stip && /^covered_tip_sha:/ { print "covered_tip_sha: " sha; stip=1; next }
      !smach && /^covered_machine:/ { print "covered_machine: " m; smach=1; next }
      { print }
    ' "$TARGET_FILE" > "$_TMP"
    mv "$_TMP" "$TARGET_FILE"
    echo "bumped: ${TARGET_FILE}  covered_tip_sha <unresolvable:${_recorded}> -> ${FULL_SHA}" >&2
    echo "TARGET=${TARGET_FILE}"
    exit 0
  else
    # Recorded resolves and is >= target (descendant) or diverged/unrelated —
    # scan does not flag this as a gap. Never regress a fresh/newer anchor.
    echo "already-anchored (>= target or divergent): ${TARGET_FILE}" >&2
    exit 10
  fi
fi

# ---------------------------------------------------------------------------
# Content-completeness guard (Phase A0 defense-in-depth)
#
# Heuristic: compare completion-log entry count for <DATE> against the count of
# ## Work Completed bullets in the summary. A large mismatch suggests the summary
# was authored mid-day and the afternoon work is absent from the prose.
#
# Fires when: completion_count >= 3  AND  completion_count >= 2 * bullet_count
# (i.e. at least 3 entries exist AND they outnumber bullets by 2x or more)
#
# On fire: exit 30 (CONTENT-GAP). No anchor injected — caller routes to Phase A
# content-assembly analyst to complete the prose first.
# ---------------------------------------------------------------------------
_COMPLETION_COUNT=0
_QUERY_BIN="${PLUGIN_ROOT}/bin/query-completions.sh"
if [[ -f "$_QUERY_BIN" ]] && command -v node &>/dev/null; then
  _completions_json="$(bash "$_QUERY_BIN" --root "$(coordinator_example_orchestration_hub_root)" --where "created=${DATE}" --format json 2>/dev/null || true)"
  if [[ -n "$_completions_json" ]] && [[ "$_completions_json" != "[]" ]]; then
    # try python3 JSON parse first (precise record count); fall back to grep heuristic
    _COMPLETION_COUNT="$(printf '%s' "$_completions_json" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || printf '%s' "$_completions_json" | grep -c '"path":' || echo 0)"  # popup-intentional-last-resort
    _COMPLETION_COUNT="${_COMPLETION_COUNT:-0}"
  fi
else
  # warn when guard is bypassed (detect-then-fail-loud)
  echo "WARN: content-completeness guard skipped (query-completions.sh or node unavailable); injecting without heuristic check" >&2
fi

# Count top-level bullet items and subsection headers under ## Work Completed.
# Counts lines matching '^[-*] ' or '^### ' within the Work Completed section
# (stops counting at the next '## ' sibling heading).
_BULLET_COUNT=0
_in_work_completed=0
while IFS= read -r _line; do
  if [[ "$_line" =~ ^##[[:space:]] ]]; then
    if [[ "$_line" =~ Work[[:space:]]Completed ]]; then
      _in_work_completed=1
    else
      _in_work_completed=0
    fi
    continue
  fi
  if [[ "$_in_work_completed" -eq 1 ]]; then
    if [[ "$_line" =~ ^[-*][[:space:]] ]] || [[ "$_line" =~ ^###[[:space:]] ]]; then
      _BULLET_COUNT=$(( _BULLET_COUNT + 1 ))
    fi
  fi
done < "$TARGET_FILE"

echo "INFO: date=${DATE} file=${TARGET_FILE} completions=${_COMPLETION_COUNT} bullets=${_BULLET_COUNT}" >&2
if [[ "$_COMPLETION_COUNT" -ge 3 ]] && [[ "$_COMPLETION_COUNT" -ge $(( _BULLET_COUNT * 2 )) ]]; then
  echo "CONTENT-GAP: ${TARGET_FILE} — ${_COMPLETION_COUNT} completion entries vs ${_BULLET_COUNT} Work Completed bullets; route to Phase A content-assembly analyst" >&2
  exit 30
fi

# ---------------------------------------------------------------------------
# Commit-density content-gap signal (defense-in-depth complement)
#
# Catches the false-negative where a morning-run summary that describes only
# a few early commits is anchored to a tip spanning the full day's commit range.
# Cited in-range SHA count < 50% of the day's range count (range >= 3) → CONTENT-GAP.
# A morning-run/tail-wrap note in the summary corroborates a large range (>= 10).
# ---------------------------------------------------------------------------
# enumerate the date's commit range (--no-merges: merge commits are excluded because
# summaries describe work, not plumbing merges; they would otherwise inflate the count)
_RANGE_SHAS="$(git -C "$ROOT" log "$FULL_SHA" --no-merges --since="${DATE} 00:00:00" --until="${DATE} 23:59:59" --format='%H' 2>/dev/null || true)"
_RANGE_COUNT=0
if [[ -n "$_RANGE_SHAS" ]]; then
  _RANGE_COUNT="$(printf '%s\n' "$_RANGE_SHAS" | wc -l | tr -d ' ')"
fi
_RANGE_COUNT="${_RANGE_COUNT:-0}"

_CITED_COUNT=0
_CITED_FULL_SHAS=""  # newline-separated full SHAs already counted (dedup on resolved SHA prevents double-count across short/long forms)
while IFS= read -r _tok; do
  [[ -z "$_tok" ]] && continue
  # resolve to full SHA; skip tokens that don't resolve to a commit
  _full=""
  _full="$(git -C "$ROOT" rev-parse --verify -q "${_tok}^{commit}" 2>/dev/null)" || continue
  # dedup: skip if this commit was already counted via a different abbreviated form
  if printf '%s\n' "$_CITED_FULL_SHAS" | grep -qxF "$_full" 2>/dev/null; then
    continue
  fi
  # only count SHAs that are in the date range (not cross-date ancestors)
  if printf '%s\n' "$_RANGE_SHAS" | grep -qxF "$_full" 2>/dev/null; then
    _CITED_FULL_SHAS="${_CITED_FULL_SHAS}${_full}"$'\n'
    _CITED_COUNT=$(( _CITED_COUNT + 1 ))
  fi
done < <(grep -oiE '\b[0-9a-f]{7,40}\b' "$TARGET_FILE" 2>/dev/null | tr 'A-F' 'a-f' | sort -u)

_MORNING_SIGNAL=0
if grep -qiE 'morning run|wraps the tail|spilled past midnight' "$TARGET_FILE" 2>/dev/null; then _MORNING_SIGNAL=1; fi

echo "INFO: content-density date=${DATE} range_commits=${_RANGE_COUNT} cited_shas=${_CITED_COUNT} morning_signal=${_MORNING_SIGNAL}" >&2
# Primary: cited SHAs cover < 50% of the day's commit range (and range is non-trivial).
# Guard abstains when _CITED_COUNT=0 (prose-only summary has no SHA citations — a legitimate
# complete artifact; the corroborator and completion-count guard remain independent backstops).
if [[ "$_RANGE_COUNT" -ge 3 ]] && [[ "$_CITED_COUNT" -ge 1 ]] && [[ $(( _CITED_COUNT * 2 )) -lt "$_RANGE_COUNT" ]]; then
  echo "CONTENT-GAP: ${TARGET_FILE} — summary cites ${_CITED_COUNT} in-range commit SHAs vs ${_RANGE_COUNT} commits in the ${DATE} range (<50%); route to Phase A content-assembly analyst" >&2
  exit 30
fi
# Corroborator: a morning-run/tail-wrap note anchored to a large range is a near-certain gap
if [[ "$_MORNING_SIGNAL" -eq 1 ]] && [[ "$_RANGE_COUNT" -ge 10 ]]; then
  echo "CONTENT-GAP: ${TARGET_FILE} — morning-run/tail-wrap note anchored to a ${_RANGE_COUNT}-commit range; route to Phase A content-assembly analyst" >&2
  exit 30
fi

# ---------------------------------------------------------------------------
# Inject anchors
# ---------------------------------------------------------------------------
_TMP="${TARGET_FILE}.tmp.$$"
trap 'rm -f "$_TMP"' EXIT

_FIRST_LINE="$(head -n 1 "$TARGET_FILE")"

if [[ "$_FIRST_LINE" == "---" ]]; then
  # File has YAML frontmatter: insert key-value fields inside the frontmatter block
  # (before the closing ---), then insert the prose note after the # Daily Summary H1.
  # The bare key-value lines inside frontmatter are still found by '^covered_tip_sha:' grep.
  # literal em-dash (octal \342\200\224 is gawk-only; fails on macOS one-true-awk)
  # END guard so unclosed frontmatter fails loud (exit 1) instead of silently injecting no anchor
  # Intentional: no blank line is added before the injected keys inside the YAML block; YAML does not require it.
  awk -v sha="$FULL_SHA" -v m="$_MACHINE" -v today="$TODAY" '
    BEGIN { fm_open=0; keys_done=0; note_done=0 }
    NR==1 { fm_open=1; print; next }
    fm_open && /^---$/ && !keys_done {
      print "covered_tip_sha: " sha
      print "covered_machine: " m
      keys_done=1; fm_open=0
      print; next
    }
    !note_done && tolower($0) ~ /^# daily summary/ {
      print
      print "> _Record anchor injected " today " by /workday-complete backfill (mechanical) — summary content pre-existing._"
      note_done=1; next
    }
    { print }
    END {
      if (!keys_done) {
        print "ERROR: frontmatter block not closed (no terminating ---); anchor not injected" > "/dev/stderr"
        exit 1
      }
    }
  ' "$TARGET_FILE" > "$_TMP"
else
  # No frontmatter: insert all three lines after the # Daily Summary H1.
  # The awk exits 1 in END if no H1 was found (unexpected file structure).
  awk -v sha="$FULL_SHA" -v m="$_MACHINE" -v today="$TODAY" '
    !done && tolower($0) ~ /^# daily summary/ {
      print
      print ""
      print "covered_tip_sha: " sha
      print "covered_machine: " m
      print "> _Record anchor injected " today " by /workday-complete backfill (mechanical) — summary content pre-existing._"
      done=1; next
    }
    { print }
    END {
      if (!done) {
        print "ERROR: no \"# Daily Summary\" H1 found in file; cannot inject anchor" > "/dev/stderr"
        exit 1
      }
    }
  ' "$TARGET_FILE" > "$_TMP"
fi

mv "$_TMP" "$TARGET_FILE"
echo "injected: ${TARGET_FILE}  covered_tip_sha=${FULL_SHA}  covered_machine=${_MACHINE}" >&2
# emit injected path on stdout so caller can stage only those files — not the whole directory
echo "TARGET=${TARGET_FILE}"
exit 0
