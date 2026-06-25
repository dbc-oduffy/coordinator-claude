#!/usr/bin/env bash
# workday-complete-step9-append-changelog.sh — Step 9 of /workday-complete: append daily block
# to the week-changelog.
#
# Purpose: encapsulates the changelog-append logic that was empirically EM-skippable when
# expressed as inline bash in the skill body. Concentrating the logic here removes EM
# judgment from a mechanical procedure and makes the step idempotent and testable.
#
# Spec backlink: commands/workday-complete.md § Step 9: Append to Week-Changelog
#
# Usage:
#   workday-complete-step9-append-changelog.sh [OPTIONS] [SCOPE_SUMMARY]
#
# Positional:
#   SCOPE_SUMMARY   One-line day summary for the **Scope:** field. If omitted, derived from
#                   the most recent non-trivial commit subject (first 80 chars). Falls back
#                   to "no work today" when no non-trivial commits exist.
#
# Options:
#   --no-push   Skip the git push step.
#   --dry-run   Print block to stdout; no file write, no commit, no push. Implies --no-push.
#
# Environment (populated by Step 1 and Step 5 of /workday-complete):
#   RC_VALIDATE      Numeric exit code or "skipped"; populates Validation: validate=…
#   RC_PLUGIN_SUITE  Numeric exit code; populates plugin-suite=…   Default: "n/a" if unset.
#   COORDINATOR_ROOT TEST-ONLY override for the repo root (must not be set in a live
#                    ceremony; warns if set to a non-cwd-toplevel path). Default: git toplevel.
#   COORDINATOR_MACHINE Override machine name (used by tests).
#
# Stdout: structured one-line progress messages prefixed [step9].
# Stderr: human-readable detail.
#
# Exit codes:
#   0 — block appended and committed (or dry-run succeeded).
#   1 — write or commit error.
#   2 — push rejected.
#   3 — HEADER staleness skip (informational, not failure).

set -uo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (bash ≥ 4 required for this plugin)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash ≥ 4 required (running ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Plugin root and lib sourcing
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_PATH="${PLUGIN_ROOT}/lib/coordinator-daily-branch.sh"

if [[ ! -f "${LIB_PATH}" ]]; then
  echo "ERROR: daily-branch lib not found at ${LIB_PATH}" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${LIB_PATH}"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
NO_PUSH=false
DRY_RUN=false
SCOPE_ARG=""
FOR_DATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-push)
      NO_PUSH=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      NO_PUSH=true
      shift
      ;;
    --for-date)
      # Backfill a specific (past) day. Overrides TODAY so the whole block —
      # commit window, changelog filename, daily-summary path, header — keys to
      # that date. Window math is unchanged: YESTERDAY derives from TODAY, so the
      # existing (YESTERDAY 23:59:59Z, TODAY 23:59:59Z] window captures exactly
      # FOR_DATE's commits. Used by the skipped-day backfill pass.
      FOR_DATE="${2:-}"
      if [[ ! "${FOR_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        echo "ERROR: --for-date requires a YYYY-MM-DD argument (got '${FOR_DATE}')" >&2
        exit 1
      fi
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      SCOPE_ARG="$1"
      shift
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
# COORDINATOR_ROOT is a TEST-ONLY repo-root override; a live ceremony leaves it
# unset so it defaults to the cwd git toplevel. Warn loud if it is set to a path
# other than the cwd toplevel — catches copy-paste of the test-only override into a
# live ceremony (the 2026-06-24 mis-root bug). Paths are canonicalized (pwd -P) so a
# symlinked tmpdir is not a false positive; set COORDINATOR_ROOT_WARN_SUPPRESS=1 to
# silence (tests pointing at an in-tree fixture). Structure mirrors backfill-scan.sh.
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

COORDINATOR_ROOT="${COORDINATOR_ROOT:-${_cwd_top}}"
if [[ -z "${COORDINATOR_ROOT}" ]]; then
  echo "ERROR: cwd is not a git repo and COORDINATOR_ROOT is not set" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Machine and date
# ---------------------------------------------------------------------------
MACHINE="$(cs_compute_machine)"
TODAY="${FOR_DATE:-$(date -u +%Y-%m-%d)}"
CHANGELOG_FILE="${COORDINATOR_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"
HEADER_FILE="${COORDINATOR_ROOT}/state/week-changelog/HEADER.md"
DAILY_SUMMARY="${COORDINATOR_ROOT}/archive/daily-summaries/${TODAY}.md"

# ---------------------------------------------------------------------------
# Staleness guard: HEADER.md Week starting: must be ≤14 days ago
# Backfill (--for-date) bypasses the staleness guard: a historical block is keyed to a past
# day and must be written regardless of current HEADER freshness.
# ---------------------------------------------------------------------------
if [[ -z "${FOR_DATE}" ]] && [[ -f "${HEADER_FILE}" ]]; then
  WEEK_START=""
  while IFS= read -r line; do
    case "$line" in
      "Week starting:"*)
        WEEK_START="${line#Week starting:}"
        WEEK_START="${WEEK_START#"${WEEK_START%%[! ]*}"}"  # ltrim spaces
        break
        ;;
    esac
  done < "${HEADER_FILE}"

  if [[ -n "${WEEK_START}" ]]; then
    # Portable date-delta: prefer python3, fall back to epoch arithmetic with
    # date +%s (portable on macOS BSD date and GNU date).
    DAYS_AGO=""
    if command -v python3 >/dev/null 2>&1; then
      # Review: code-reviewer — gated on STEP9_DEBUG to avoid stderr noise on every run (F9)
      [[ "${STEP9_DEBUG:-}" == "1" ]] && echo "staleness check: using python3 for date arithmetic" >&2
      DAYS_AGO="$(python3 -c "
from datetime import date
today = date.fromisoformat('${TODAY}')
start = date.fromisoformat('${WEEK_START}')
print((today - start).days)
" 2>/dev/null || true)"
    fi
    if [[ -z "${DAYS_AGO}" ]]; then
      [[ "${STEP9_DEBUG:-}" == "1" ]] && echo "staleness check: using epoch arithmetic (date +%s)" >&2
      # date +%s is portable on macOS BSD and GNU date
      # Review: code-reviewer — renamed from TODAY_EPOCH; scoped to staleness check only (F14)
      STALE_CHECK_EPOCH="$(date -u +%s)"
      # Parse WEEK_START as YYYY-MM-DD
      WS_YEAR="${WEEK_START:0:4}"
      WS_MON="${WEEK_START:5:2}"
      WS_DAY="${WEEK_START:8:2}"
      # Portable: pass the canonical date string and let the OS parse it.
      # macOS BSD: date -j -f "%Y-%m-%d" "YYYY-MM-DD" +%s
      # GNU: date -u -d "YYYY-MM-DD" +%s
      WS_EPOCH=""
      if date -j -f "%Y-%m-%d" "${WEEK_START}" +%s >/dev/null 2>&1; then
        WS_EPOCH="$(date -j -f "%Y-%m-%d" "${WEEK_START}" +%s)"
      elif date -u -d "${WEEK_START}" +%s >/dev/null 2>&1; then
        WS_EPOCH="$(date -u -d "${WEEK_START}" +%s)"
      else
        # Last resort: compute from components using printf+mktime via awk
        WS_EPOCH="$(awk -v y="${WS_YEAR}" -v m="${WS_MON}" -v d="${WS_DAY}" \
          'BEGIN{print mktime(y " " m " " d " 00 00 00")}' 2>/dev/null || true)"
      fi
      if [[ -n "${WS_EPOCH}" && "${WS_EPOCH}" -gt 0 ]]; then
        DAYS_AGO=$(( (STALE_CHECK_EPOCH - WS_EPOCH) / 86400 ))
      fi
    fi

    if [[ -n "${DAYS_AGO}" && "${DAYS_AGO}" -gt 14 ]]; then
      echo "WARN: HEADER.md is stale (week started ${DAYS_AGO} days ago, >14). Was \`/workweek-complete\` skipped?" >&2
      echo "[step9] SKIPPED (HEADER stale)"
      exit 3
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Commit information for today
# ---------------------------------------------------------------------------
# All commits on current branch since origin/main divergence, authored today (UTC)
# git log --format="%H %s" --after / --before doesn't exist portably; use date filter.
# "Non-trivial" pattern: commit subject does NOT match ^(chore|docs?)([(:]|$) or
# ^workstream-complete quick-save
TRIVIAL_PATTERN='^(chore|docs?)([(:]|$)|^workstream-complete quick-save'

# Collect today's commits from HEAD relative to origin/main
# We use --after="yesterday midnight UTC" which doesn't work on BSD.
# Use a date string that all implementations accept: the ISO date of yesterday.
# Review: code-reviewer — awk leap-year comment added for readability (F15)
# The awk fallback only populates days_in_m[] inside the month-boundary branch (d<1),
# so the array only needs values when we've decremented past the 1st of the month.
# Leap-year: Feb gets 29 days when (y%4==0 && (y%100!=0 || y%400==0)).
YESTERDAY="$(python3 -c "from datetime import date, timedelta; print(date.fromisoformat('${TODAY}') - timedelta(days=1))" 2>/dev/null || \
  awk -v today="${TODAY}" 'BEGIN{
    y=substr(today,1,4)+0; m=substr(today,6,2)+0; d=substr(today,9,2)+0
    d--; if(d<1){m--; if(m<1){m=12;y--}
      # days_in_m only populated here (month-boundary branch); standard Gregorian calendar
      days_in_m[1]=31;days_in_m[2]=28;days_in_m[3]=31;days_in_m[4]=30;
      days_in_m[5]=31;days_in_m[6]=30;days_in_m[7]=31;days_in_m[8]=31;
      days_in_m[9]=30;days_in_m[10]=31;days_in_m[11]=30;days_in_m[12]=31;
      # Proleptic Gregorian leap-year rule
      if(y%4==0&&(y%100!=0||y%400==0))days_in_m[2]=29
      d=days_in_m[m]}
    printf "%04d-%02d-%02d\n",y,m,d
  }')"

# Get all commits since yesterday (inclusive of today, covers UTC day boundary)
# Format: HASH<TAB>SUBJECT
# Always scoped to COORDINATOR_ROOT via -C to avoid picking up the caller's cwd repo.
# Exclude the step9 self-generated commit (chore(week-changelog): daily block …) so
# that a second idempotency run sees the same commit list as the first run — otherwise
# run 1 creates the changelog commit which changes the Commits: count on run 2.
# Pattern: match lines where the subject field (after TAB) contains the changelog prefix.
# Use a tab-delimited field; grep -vE on the full line (regex, not fixed-string — see SELF_COMMIT_REGEX).
# Review: code-reviewer — broadened to match any date (not just TODAY) to survive midnight
# rollover where prior run's commit has yesterday's date in its subject.
# Pattern matches TAB + "chore(week-changelog): daily block YYYY-MM-DD" for any date.
SELF_COMMIT_REGEX="	chore\(week-changelog\): daily block [0-9]{4}-[0-9]{2}-[0-9]{2}"
ALL_COMMITS_RAW=""
# Review: code-reviewer — added --before to prevent future-dated / clock-skew commits leaking in (F2)
ALL_COMMITS_RAW="$(git -C "${COORDINATOR_ROOT}" log --format="%H%x09%s" --after="${YESTERDAY}T23:59:59Z" --before="${TODAY}T23:59:59Z" --no-merges 2>/dev/null \
  | grep -vE "${SELF_COMMIT_REGEX}" || true)"

# Filter non-trivial commit subjects
NON_TRIVIAL_SUBJECTS=()
NON_TRIVIAL_HASHES=()
ALL_HASHES=()
ALL_SUBJECTS=()

if [[ -n "${ALL_COMMITS_RAW}" ]]; then
  while IFS=$'\t' read -r chash csubj; do
    [[ -z "${chash}" ]] && continue
    ALL_HASHES+=("${chash}")
    ALL_SUBJECTS+=("${csubj}")
    if ! echo "${csubj}" | grep -qE "${TRIVIAL_PATTERN}"; then
      NON_TRIVIAL_SUBJECTS+=("${csubj}")
      NON_TRIVIAL_HASHES+=("${chash}")
    fi
  done <<< "${ALL_COMMITS_RAW}"
fi

COMMIT_COUNT="${#ALL_HASHES[@]}"
HAS_NON_TRIVIAL=false
[[ "${#NON_TRIVIAL_HASHES[@]}" -gt 0 ]] && HAS_NON_TRIVIAL=true

# Oldest and newest SHA (git log emits newest-first)
OLDEST_SHA="n/a"
NEWEST_SHA="n/a"
if [[ "${COMMIT_COUNT}" -gt 0 ]]; then
  NEWEST_SHA="${ALL_HASHES[0]}"
  OLDEST_SHA="${ALL_HASHES[${#ALL_HASHES[@]}-1]}"
  NEWEST_SHA="${NEWEST_SHA:0:8}"
  OLDEST_SHA="${OLDEST_SHA:0:8}"
fi

# Commit range string
if [[ "${COMMIT_COUNT}" -eq 0 ]]; then
  COMMIT_RANGE="n/a"
elif [[ "${COMMIT_COUNT}" -eq 1 ]]; then
  COMMIT_RANGE="${NEWEST_SHA}"
else
  COMMIT_RANGE="${OLDEST_SHA}..${NEWEST_SHA}"
fi

# ---------------------------------------------------------------------------
# Scope field
# ---------------------------------------------------------------------------
if [[ -n "${SCOPE_ARG}" ]]; then
  SCOPE="${SCOPE_ARG}"
elif "${HAS_NON_TRIVIAL}"; then
  # First 80 chars of most recent non-trivial commit subject
  SCOPE="${NON_TRIVIAL_SUBJECTS[0]:0:80}"
else
  SCOPE="no work today"
fi

# ---------------------------------------------------------------------------
# Branch info
# ---------------------------------------------------------------------------
# Review: code-reviewer — git branch --show-current fallback now uses -C COORDINATOR_ROOT
# to avoid reflecting a different repo when invoked from a different cwd (F8)
BRANCH="$("${SCRIPT_DIR}/coordinator-current-branch" 2>/dev/null || git -C "${COORDINATOR_ROOT}" branch --show-current 2>/dev/null || echo "unknown")"

# ---------------------------------------------------------------------------
# Plans touched today
# ---------------------------------------------------------------------------
# Look for docs/plans/ files modified in today's commits
PLANS_TOUCHED="none"
if [[ "${COMMIT_COUNT}" -gt 0 ]]; then
  PLANS_RAW=""
  # Review: code-reviewer — added --before to match commit list query upper bound (F2)
  # Note: unlike the commit list, no SELF_COMMIT_REGEX exclusion here — self-commit
  # doesn't touch docs/plans/; asymmetry is intentional (F5).
  PLANS_RAW="$(git -C "${COORDINATOR_ROOT}" log --format="" --name-only --after="${YESTERDAY}T23:59:59Z" --before="${TODAY}T23:59:59Z" --no-merges \
    -- "docs/plans/*.md" 2>/dev/null | sort -u || true)"
  if [[ -n "${PLANS_RAW}" ]]; then
    # Format as comma-separated list; status detection is out of scope (use "in-progress")
    PLANS_LIST=""
    while IFS= read -r pfile; do
      [[ -z "${pfile}" ]] && continue
      [[ -n "${PLANS_LIST}" ]] && PLANS_LIST="${PLANS_LIST}, "
      PLANS_LIST="${PLANS_LIST}${pfile} (status: in-progress)"
    done <<< "${PLANS_RAW}"
    PLANS_TOUCHED="${PLANS_LIST}"
  fi
fi

# ---------------------------------------------------------------------------
# Handoffs for today
# ---------------------------------------------------------------------------
HANDOFF_DIR="${COORDINATOR_ROOT}/state/handoffs"
HANDOFFS_LIST="none"
HANDOFFS_PATHS=()

if [[ -d "${HANDOFF_DIR}" ]]; then
  while IFS= read -r hf; do
    [[ -z "${hf}" ]] && continue
    # Store relative path from repo root
    HANDOFFS_PATHS+=("${hf}")
  done < <(find "${HANDOFF_DIR}" -maxdepth 1 -name "${TODAY}-*.md" 2>/dev/null | sort)
fi

if [[ "${#HANDOFFS_PATHS[@]}" -gt 0 ]]; then
  HANDOFFS_LIST=""
  for hpath in "${HANDOFFS_PATHS[@]}"; do
    rel="${hpath#"${COORDINATOR_ROOT}/"}"
    [[ -n "${HANDOFFS_LIST}" ]] && HANDOFFS_LIST="${HANDOFFS_LIST}, "
    HANDOFFS_LIST="${HANDOFFS_LIST}${rel}"
  done
fi

# ---------------------------------------------------------------------------
# Decisions and Blockers: extract from handoff bodies
# Extract lines following "Decisions:" / "Blockers:" headings or frontmatter keys.
# Prefer python3 for YAML-aware extraction; fall back to grep -E.
# ---------------------------------------------------------------------------
DECISIONS="none"
BLOCKERS="none"

extract_field_from_handoffs() {
  # $1 = field name ("Decisions" or "Blockers")
  local field="$1"
  local result=""

  if [[ "${#HANDOFFS_PATHS[@]}" -eq 0 ]]; then
    echo "none"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    # Review: code-reviewer — gated on STEP9_DEBUG to avoid 4 stderr lines per run (F10)
    [[ "${STEP9_DEBUG:-}" == "1" ]] && echo "extracting ${field} via python3 YAML-aware reader" >&2
    result="$(python3 - "${field}" "${HANDOFFS_PATHS[@]}" <<'PYEOF'
import sys, re

field = sys.argv[1]
files = sys.argv[2:]
collected = []

for fpath in files:
    try:
        with open(fpath, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        continue

    # Try YAML frontmatter first (between --- markers)
    fm_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        # Look for "field: value" in frontmatter
        for line in fm.splitlines():
            m = re.match(r'^' + re.escape(field) + r':\s*(.+)', line, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val and val not in ("none", "n/a", ""):
                    collected.append(val)

    # Also look for markdown heading ## Decisions / ## Blockers followed by content
    md_pat = re.compile(r'##\s+' + re.escape(field) + r'\s*\n((?:(?!##).)+)', re.IGNORECASE | re.DOTALL)
    for m in md_pat.finditer(content):
        val = m.group(1).strip()
        # Strip markdown bullets
        lines = [re.sub(r'^[-*]\s+', '', l).strip() for l in val.splitlines() if l.strip()]
        text = "; ".join(l for l in lines if l)
        if text:
            collected.append(text)

if collected:
    print("; ".join(collected))
else:
    print("none")
PYEOF
)" 2>/dev/null || true
  fi

  if [[ -z "${result}" ]]; then
    [[ "${STEP9_DEBUG:-}" == "1" ]] && echo "extracting ${field} via grep -E fallback" >&2
    # grep -E: look for "field: value" or "## Field\nvalue lines"
    local combined=""
    for hpath in "${HANDOFFS_PATHS[@]}"; do
      [[ -f "${hpath}" ]] || continue
      # frontmatter key: "Decisions: ..." (case-insensitive field match)
      local fm_val
      # Review: code-reviewer — generic strip (any "field: value" prefix) so future callers
      # passing other field names don't leave the prefix in output (F6)
      fm_val="$(grep -iE "^${field}:[[:space:]]*(.+)" "${hpath}" | head -1 | sed "s/^[^:]*:[[:space:]]*//" || true)"
      if [[ -n "${fm_val}" && "${fm_val}" != "none" && "${fm_val}" != "n/a" ]]; then
        [[ -n "${combined}" ]] && combined="${combined}; "
        combined="${combined}${fm_val}"
      fi
    done
    result="${combined:-none}"
  fi

  echo "${result:-none}"
}

DECISIONS="$(extract_field_from_handoffs "Decisions")"
BLOCKERS="$(extract_field_from_handoffs "Blockers")"

# ---------------------------------------------------------------------------
# Validation fields
# ---------------------------------------------------------------------------
VALIDATE_VAL="${RC_VALIDATE:-skipped}"
PLUGIN_SUITE_VAL="${RC_PLUGIN_SUITE:-n/a}"

# ---------------------------------------------------------------------------
# Reviewed: field
# Read records from list-review-trail-records.sh --date-prefix TODAY
# ---------------------------------------------------------------------------
REVIEW_TRAIL_SCRIPT="${SCRIPT_DIR}/list-review-trail-records.sh"
REVIEWED_LINES=()

if [[ -x "${REVIEW_TRAIL_SCRIPT}" ]]; then
  TRAIL_OUTPUT=""
  # COORDINATOR_ROOT controls the root that list-review-trail-records.sh uses
  TRAIL_OUTPUT="$(COORDINATOR_ROOT="${COORDINATOR_ROOT}" \
    "${BASH}" "${REVIEW_TRAIL_SCRIPT}" --date-prefix "${TODAY}" 2>/dev/null || true)"

  if [[ -n "${TRAIL_OUTPUT}" ]]; then
    while IFS= read -r record_path; do
      [[ -z "${record_path}" ]] && continue
      # Parse JSON record fields: sha_range, reviewer, verdict, diff_loc
      if command -v python3 >/dev/null 2>&1; then
        line="$(python3 -c "
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8', errors='replace') as f:
        d = json.load(f)
    sha = d.get('sha_range', d.get('commit_range', 'unknown'))
    rev = d.get('reviewer', 'unknown')
    ver = d.get('verdict', 'unknown')
    loc = d.get('diff_loc', d.get('diff_lines', 'unknown'))
    print(f'sha_range={sha} reviewer={rev} verdict={ver} diff_loc={loc}')
except Exception as e:
    print(f'parse-error={e}')
" "${record_path}" 2>/dev/null || echo "parse-error=python-failed")"
      else
        # grep -E fallback: extract individual JSON fields
        sha_val="$(grep -oE '"sha_range"[[:space:]]*:[[:space:]]*"[^"]*"' "${record_path}" | head -1 | sed 's/.*: *"\(.*\)"/\1/' || echo "unknown")"
        rev_val="$(grep -oE '"reviewer"[[:space:]]*:[[:space:]]*"[^"]*"' "${record_path}" | head -1 | sed 's/.*: *"\(.*\)"/\1/' || echo "unknown")"
        ver_val="$(grep -oE '"verdict"[[:space:]]*:[[:space:]]*"[^"]*"' "${record_path}" | head -1 | sed 's/.*: *"\(.*\)"/\1/' || echo "unknown")"
        loc_val="$(grep -oE '"diff_loc"[[:space:]]*:[[:space:]]*"[^"]*"' "${record_path}" | head -1 | sed 's/.*: *"\(.*\)"/\1/' || echo "unknown")"
        line="sha_range=${sha_val} reviewer=${rev_val} verdict=${ver_val} diff_loc=${loc_val}"
      fi
      REVIEWED_LINES+=("${line}")
    done <<< "${TRAIL_OUTPUT}"
  fi
fi

# ---------------------------------------------------------------------------
# Compose the block
# ---------------------------------------------------------------------------
compose_block() {
  local header="## ${TODAY} — ${MACHINE}"
  printf '%s\n\n' "${header}"
  printf '**Branch:** %s\n' "${BRANCH}"
  printf '**Commits:** %d (range: %s)\n' "${COMMIT_COUNT}" "${COMMIT_RANGE}"
  printf '**Scope:** %s\n' "${SCOPE}"
  printf '**Plans touched:** %s\n' "${PLANS_TOUCHED}"
  printf '**Handoffs:** %s\n' "${HANDOFFS_LIST}"
  printf '**Decisions:** %s\n' "${DECISIONS}"
  printf '**Blockers:** %s\n' "${BLOCKERS}"
  printf '**Validation:** validate=%s plugin-suite=%s\n' "${VALIDATE_VAL}" "${PLUGIN_SUITE_VAL}"

  # Reviewed field logic
  if [[ "${#REVIEWED_LINES[@]}" -gt 0 ]]; then
    for rline in "${REVIEWED_LINES[@]}"; do
      printf '**Reviewed:** %s\n' "${rline}"
    done
  elif "${HAS_NON_TRIVIAL}"; then
    printf '**Reviewed:** none — flag for /workweek-complete Step 7\n'
  fi
  # else: all-trivial + no records → omit **Reviewed:** entirely

  printf '**Links:** archive/daily-summaries/%s.md, archive/completed/%s/ (per-entry files; query via `bin/query-completions --where "created=%s"`)\n' \
    "${TODAY}" "${TODAY:0:7}" "${TODAY}"
}

NEW_BLOCK="$(compose_block)"

# Review: code-reviewer — write NEW_BLOCK to a temp file so the awk fallback can read
# it via getline rather than -v, avoiding macOS awk silent truncation on embedded newlines (F4).
NEW_BLOCK_TMP="$(mktemp)"
printf '%s\n' "${NEW_BLOCK}" > "${NEW_BLOCK_TMP}"
cleanup_step9() { rm -f "${NEW_BLOCK_TMP}"; }
trap cleanup_step9 EXIT

# ---------------------------------------------------------------------------
# Dry-run: print and exit
# ---------------------------------------------------------------------------
if "${DRY_RUN}"; then
  printf '%s\n' "${NEW_BLOCK}"
  echo "[step9] push: skipped (--dry-run)"
  echo "[step9] OK"
  exit 0
fi

# ---------------------------------------------------------------------------
# Idempotency: check existing file for today's section
# ---------------------------------------------------------------------------
SECTION_HEADER="## ${TODAY} — ${MACHINE}"

# Normalise trailing whitespace for comparison (strip trailing spaces per line,
# then strip trailing blank lines from the block). Uses temp-file pattern for
# portability (no sed -i).
normalise_block() {
  # Strip trailing spaces from each line, then strip trailing blank lines.
  # Review: code-reviewer — harmonised so python3 and awk extraction paths produce
  # byte-equivalent output; both now strip ALL trailing blank lines (F3).
  # The awk one-liner buffers blank lines and only flushes them when a non-blank
  # line follows — so trailing blanks are swallowed at EOF.
  local input="$1"
  printf '%s' "${input}" \
    | sed 's/[[:space:]]*$//' \
    | awk 'BEGIN{buf=""} /^$/{buf=buf"\n"; next} {printf "%s", buf; buf=""; print}'
}

NORM_NEW="$(normalise_block "${NEW_BLOCK}")"

write_needed=true

if [[ -f "${CHANGELOG_FILE}" ]]; then
  # Check if today's section already exists
  if grep -qF "${SECTION_HEADER}" "${CHANGELOG_FILE}" 2>/dev/null; then
    # Extract existing section: from the header line to the next ## header or EOF
    # Use python3 if available; otherwise awk
    EXISTING_SECTION=""
    if command -v python3 >/dev/null 2>&1; then
      EXISTING_SECTION="$(python3 - "${CHANGELOG_FILE}" "${SECTION_HEADER}" <<'PYEOF'
import sys, re

fpath = sys.argv[1]
target = sys.argv[2]

with open(fpath, encoding="utf-8", errors="replace") as f:
    content = f.read()

# Find the target section header
idx = content.find(target)
if idx == -1:
    print("")
    sys.exit(0)

# Find next ## at start of line after the target header
rest = content[idx:]
m = re.search(r'\n## ', rest[1:])
if m:
    section = rest[:m.start() + 1]
else:
    section = rest

# Strip trailing whitespace from each line, then trailing blank lines
lines = [l.rstrip() for l in section.splitlines()]
# Remove trailing empty lines
while lines and not lines[-1]:
    lines.pop()
print('\n'.join(lines))
PYEOF
)" 2>/dev/null || true
    else
      # awk fallback: extract section from header to next ## or EOF
      EXISTING_SECTION="$(awk -v hdr="${SECTION_HEADER}" '
        BEGIN{found=0}
        $0==hdr{found=1}
        found && NR>1 && /^## /{exit}
        found{print}
      ' "${CHANGELOG_FILE}" | sed 's/[[:space:]]*$//' | awk '
        BEGIN{buf=""; had_content=0}
        /^$/{buf=buf"\n"; next}
        {printf "%s", buf; buf=""; print; had_content=1}
      ')" 2>/dev/null || true
    fi

    NORM_EXISTING="$(normalise_block "${EXISTING_SECTION}")"

    if [[ "${NORM_NEW}" == "${NORM_EXISTING}" ]]; then
      echo "[step9] block unchanged (idempotent no-op)"
      exit 0
    fi

    # Replace existing section with new block
    echo "replacing existing section for ${TODAY}" >&2
    if command -v python3 >/dev/null 2>&1; then
      python3 - "${CHANGELOG_FILE}" "${SECTION_HEADER}" "${NEW_BLOCK}" <<'PYEOF' # verify-no-console-flash: allow — one-shot changelog text-replace; not on Windows hot-path
import sys, re

fpath = sys.argv[1]
target = sys.argv[2]
new_block = sys.argv[3]

with open(fpath, encoding="utf-8", errors="replace") as f:
    content = f.read()

idx = content.find(target)
if idx == -1:
    sys.exit(1)

rest = content[idx:]
m = re.search(r'\n## ', rest[1:])
if m:
    after = rest[m.start() + 1:]
    before = content[:idx]
else:
    after = ""
    before = content[:idx]

# Compose replacement: before + new_block + separator + rest (if any)
new_content = before + new_block.rstrip("\n") + "\n"
if after.strip():
    new_content += "\n" + after.lstrip("\n")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(new_content)
PYEOF
      if [[ $? -ne 0 ]]; then
        echo "ERROR: failed to replace existing section in ${CHANGELOG_FILE}" >&2
        exit 1
      fi
    else
      # awk fallback: rebuild file replacing the section.
      # Review: code-reviewer — read NEW_BLOCK from temp file via getline rather than
      # -v newblock; macOS awk (one-true-awk / nawk) truncates -v args at first newline (F4).
      TMP_FILE="${CHANGELOG_FILE}.step9.tmp"
      awk -v hdr="${SECTION_HEADER}" -v tmpfile="${NEW_BLOCK_TMP}" '
        BEGIN{
          in_section=0; printed_new=0
          # Slurp new block from temp file
          new_block=""
          while ((getline line < tmpfile) > 0) {
            new_block = (new_block == "") ? line : new_block "\n" line
          }
          close(tmpfile)
        }
        $0==hdr{
          if(!printed_new){printf "%s\n", new_block; printed_new=1}
          in_section=1; next
        }
        in_section && /^## /{in_section=0}
        !in_section{print}
      ' "${CHANGELOG_FILE}" > "${TMP_FILE}" && mv "${TMP_FILE}" "${CHANGELOG_FILE}"
    fi
    write_needed=false
  fi
fi

# If no existing section found, append
if "${write_needed}"; then
  # Ensure directory exists
  mkdir -p "$(dirname "${CHANGELOG_FILE}")"

  if [[ -f "${CHANGELOG_FILE}" ]]; then
    # Append with separator if file already has content
    {
      printf '\n'
      printf '%s\n' "${NEW_BLOCK}"
    } >> "${CHANGELOG_FILE}"
  else
    printf '%s\n' "${NEW_BLOCK}" > "${CHANGELOG_FILE}"
  fi
fi

# Review: code-reviewer — removed >&2 duplicate; stdout carries the signal (F16)
echo "[step9] block written: ${CHANGELOG_FILE}"

# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------
FILES_TO_COMMIT=("${CHANGELOG_FILE}")
if [[ -f "${DAILY_SUMMARY}" ]]; then
  FILES_TO_COMMIT+=("${DAILY_SUMMARY}")
fi

# Stage files explicitly (never git add -A)
for f in "${FILES_TO_COMMIT[@]}"; do
  git -C "${COORDINATOR_ROOT}" add -- "${f}" 2>/dev/null
done

# Check if there's anything staged to commit
STAGED="$(git -C "${COORDINATOR_ROOT}" diff --cached --name-only 2>/dev/null || true)"
if [[ -z "${STAGED}" ]]; then
  echo "[step9] block unchanged (idempotent no-op)"
  exit 0
fi

COMMIT_MSG="chore(week-changelog): daily block ${TODAY} ${MACHINE}"
# Review: code-reviewer — grep -q "" always matches; removed so pipefail propagates commit failure
if ! git -C "${COORDINATOR_ROOT}" commit -m "${COMMIT_MSG}" 2>&1 | tee /dev/stderr; then
  echo "ERROR: git commit failed" >&2
  exit 1
fi

COMMIT_SHA="$(git -C "${COORDINATOR_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
echo "[step9] commit: ${COMMIT_SHA}"

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------
if "${NO_PUSH}"; then
  echo "[step9] push: skipped (--no-push)"
  echo "[step9] OK"
  exit 0
fi

PUSH_BRANCH="$("${SCRIPT_DIR}/coordinator-current-branch" 2>/dev/null || \
  git -C "${COORDINATOR_ROOT}" branch --show-current 2>/dev/null || echo "")"

if [[ -z "${PUSH_BRANCH}" ]]; then
  echo "WARN: no current branch; skipping push" >&2
  echo "[step9] push: skipped (no branch)"
  echo "[step9] OK"
  exit 0
fi

if git -C "${COORDINATOR_ROOT}" push origin "${PUSH_BRANCH}" 2>&1; then
  echo "[step9] push: ok"
else
  PUSH_RC=$?
  echo "ERROR: push rejected (exit ${PUSH_RC})" >&2
  echo "[step9] push: rejected"
  exit 2
fi

echo "[step9] OK"
