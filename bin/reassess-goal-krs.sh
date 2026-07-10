#!/usr/bin/env bash
# reassess-goal-krs.sh — Weekly KR re-assessment for per-repo goal artifacts.
#
# Purpose: For each state/goals/*.md artifact, parse YAML frontmatter key_results[]
# and correlate against existing weekly signal (completions, handoffs, week-changelog
# HEADER.md). Proposes a per-KR status and a perceptible_movement flag. KRs that
# show no movement AND have weekly_perceptible:true are flagged as
# "maybe-not-a-goal — no perceptible movement this week".
#
# READS existing signal only — does NOT build new instrumentation (OOS #1):
#   - coordinator/bin/query-completions.sh --since <week-start>
#   - coordinator/bin/query-records.js --type handoff
#   - state/week-changelog/HEADER.md (if present)
#
# OUTPUT: per-goal proposed-status report to stdout + writes a
# proposed_status comment block into each goal artifact's frontmatter for
# EM/PM confirmation. Does NOT overwrite the live status field.
#
# Spec backlink: docs/plans/2026-07-06-goal-setting-okr-legibility-system.md § C6
#
# Usage:
#   reassess-goal-krs.sh [--goals-dir <path>] [--since <date>] [--dry-run]
#
# Options:
#   --goals-dir <path>  Directory containing goal *.md files
#                       (default: state/goals relative to repo root)
#   --since <date>      Week-start date for signal queries (default: 7d ago)
#   --dry-run           Print proposed changes without writing to artifacts
#
# Exit codes:
#   0 — assessment complete (even if some goals have no movement)
#   1 — fatal error (missing repo root, node unavailable)

set -euo pipefail

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Self-location — derive repo root and bin dir from BASH_SOURCE[0].
# Never rely on cwd.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PLUGIN_ROOT}/.." && pwd)"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
GOALS_DIR=""
SINCE="7d"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --goals-dir)
      GOALS_DIR="$2"; shift 2 ;;
    --since)
      SINCE="$2"; shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    --help|-h)
      cat <<'EOF'
reassess-goal-krs.sh — Weekly KR re-assessment for goal artifacts.

Usage:
  reassess-goal-krs.sh [--goals-dir <path>] [--since <date>] [--dry-run]

Options:
  --goals-dir <path>  Directory containing goal *.md files
                      (default: <repo-root>/state/goals)
  --since <date>      Week-start date for signal queries (default: 7d)
  --dry-run           Print proposed changes without writing to artifacts
EOF
      exit 0 ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# Default goals dir
if [[ -z "$GOALS_DIR" ]]; then
  GOALS_DIR="${REPO_ROOT}/state/goals"
fi

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is required for query-records.js" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Gather existing weekly signal via existing tools.
# Signal is read-only; no new instrumentation.
# ---------------------------------------------------------------------------

# Completion titles from this week
COMPLETION_SIGNAL=""
if [[ -x "${SCRIPT_DIR}/query-completions.sh" ]]; then
  COMPLETION_SIGNAL="$("${SCRIPT_DIR}/query-completions.sh" --since "${SINCE}" --format json 2>/dev/null || true)"
else
  # Review: code-reviewer — warn when signal script absent so operator knows assessment is partial (F16)
  echo "WARNING: signal incomplete — query-completions.sh not found at ${SCRIPT_DIR}; movement detection may produce false negatives" >&2
fi

# Handoff titles from this week
HANDOFF_SIGNAL=""
if [[ -x "${SCRIPT_DIR}/query-records.sh" ]]; then
  HANDOFF_SIGNAL="$("${SCRIPT_DIR}/query-records.sh" --type handoff --since "${SINCE}" --format json 2>/dev/null || true)"
else
  # Review: code-reviewer — warn when signal script absent so operator knows assessment is partial (F16)
  echo "WARNING: signal incomplete — query-records.sh not found at ${SCRIPT_DIR}; movement detection may produce false negatives" >&2
fi

# Week-changelog HEADER summary text (best-effort)
CHANGELOG_TEXT=""
CHANGELOG_HEADER="${REPO_ROOT}/state/week-changelog/HEADER.md"
if [[ -f "${CHANGELOG_HEADER}" ]]; then
  CHANGELOG_TEXT="$(cat "${CHANGELOG_HEADER}")"
fi

# Combine all signal text for keyword matching
ALL_SIGNAL_TEXT="${COMPLETION_SIGNAL}
${HANDOFF_SIGNAL}
${CHANGELOG_TEXT}"

# ---------------------------------------------------------------------------
# Parse YAML frontmatter helper (pure bash, BSD-portable).
# Extracts the key_results[] block from a goal .md file.
# ---------------------------------------------------------------------------

# parse_frontmatter_field <file> <field>
# Prints the raw value of a scalar frontmatter field.
parse_frontmatter_field() {
  local file="$1" field="$2"
  # Review: code-reviewer — escape awk regex metacharacters in $field before interpolation
  # so fields with dots, brackets, etc. don't produce unintended pattern matches (F4).
  local field_esc
  field_esc="$(printf '%s' "$field" | sed 's/[.^$*[\\]/\\&/g')"
  # Extract between the two --- delimiters; find the first matching key
  awk '
    BEGIN { in_fm=0; found=0 }
    /^---/ { if (in_fm == 0) { in_fm=1; next } else { exit } }
    in_fm && /^'"${field_esc}"':/ {
      sub(/^'"${field_esc}"':[[:space:]]*/, "")
      print
      found=1
      next
    }
  ' "${file}"
}

# extract_key_results <file>
# Prints lines inside the key_results[] YAML block.
# Each entry is printed with its fields on separate lines.
extract_key_results() {
  local file="$1"
  awk '
    BEGIN { in_fm=0; in_kr=0; depth=0 }
    /^---/ {
      if (in_fm == 0) { in_fm=1; next }
      else { exit }
    }
    in_fm && /^key_results:/ { in_kr=1; next }
    in_kr && /^[a-zA-Z_]/ && !/^  / { exit }
    in_kr { print }
  ' "${file}"
}

# match_signal <keyword>
# Returns 0 if the keyword appears in the combined weekly signal, 1 otherwise.
match_signal() {
  local keyword="$1"
  # Case-insensitive substring search
  local lower_kw lower_sig
  # Use tr for BSD portability (no ${var,,} in bash 3 — but we require bash 4,
  # so ${var,,} is safe; still using grep -i for clarity)
  echo "${ALL_SIGNAL_TEXT}" | grep -qi "${keyword}" 2>/dev/null
}

# ---------------------------------------------------------------------------
# process_kr_entry — assess a single parsed KR entry against weekly signal.
# Defined at top-level (not inside the for-loop) for clarity; bash redefines
# on each call-of-the-enclosing-scope otherwise, which is harmless but
# confusing (Review: code-reviewer F14).
# ---------------------------------------------------------------------------
process_kr_entry() {
  local id="$1" text="$2" current_status="$3" weekly_perceptible="$4"
  [[ -z "$id" && -z "$text" ]] && return

  # Determine perceptible movement: keyword match on KR text tokens
  local movement="no"
  if [[ -n "$text" ]]; then
    # Extract meaningful keywords: drop common stopwords, use first few words
    local keywords
    keywords="$(echo "${text}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' ' ' | tr ' ' '\n' | grep -v -E '^(a|an|the|and|or|of|to|in|for|is|are|be|by|with|on|at|from|as|it|its|this|that|we|our|per|week|monthly|daily|each|every|by|via|into|has|have|had|can|will|should|must|not|no|if|when|then|do|does|did|was|were|been)$' | head -5 | tr '\n' ' ')"
    for kw in ${keywords}; do
      [[ ${#kw} -lt 3 ]] && continue
      if match_signal "${kw}"; then
        movement="yes"
        break
      fi
    done
  fi

  # Determine proposed status
  local proposed_status="${current_status}"
  if [[ "${current_status}" == "not-started" && "${movement}" == "yes" ]]; then
    proposed_status="in-progress"
  elif [[ "${current_status}" == "in-progress" && "${movement}" == "yes" ]]; then
    proposed_status="in-progress"  # stays in-progress; no sufficient signal to advance
  fi

  # Flag: no movement AND weekly_perceptible=true
  local flag=""
  if [[ "${movement}" == "no" && "${weekly_perceptible,,}" == "true" ]]; then
    flag=" *** maybe-not-a-goal — no perceptible movement this week"
    FLAGS_FOUND=1
  fi

  local kr_label="${id:-${text:0:40}}"
  echo "  KR [${kr_label}]: current=${current_status} | movement=${movement} | proposed=${proposed_status}${flag}"
  proposed_lines+=("    # KR ${kr_label}: proposed_status: ${proposed_status} | perceptible_movement: ${movement}${flag}")
}

# ---------------------------------------------------------------------------
# Main loop: iterate over state/goals/*.md
# ---------------------------------------------------------------------------

if [[ ! -d "${GOALS_DIR}" ]]; then
  echo "INFO: No goals directory found at ${GOALS_DIR} — skipping KR re-assessment."
  exit 0
fi

# Collect goal files
goal_files=()
while IFS= read -r -d '' f; do
  goal_files+=("$f")
done < <(find "${GOALS_DIR}" -maxdepth 1 -name "*.md" -type f -print0 2>/dev/null | sort -z)

if [[ ${#goal_files[@]} -eq 0 ]]; then
  echo "INFO: No goal files found in ${GOALS_DIR} — skipping KR re-assessment."
  exit 0
fi

echo "=== Weekly KR Re-assessment ==="
echo "Signal window: --since ${SINCE}"
echo "Goals dir:     ${GOALS_DIR}"
echo ""

FLAGS_FOUND=0

for goal_file in "${goal_files[@]}"; do
  goal_name="$(basename "${goal_file}")"
  goal_title="$(parse_frontmatter_field "${goal_file}" "title" | tr -d '"')"
  goal_status="$(parse_frontmatter_field "${goal_file}" "status" | tr -d '"')"

  # Skip non-active goals
  if [[ "${goal_status}" != "active" && "${goal_status}" != "" ]]; then
    echo "-- ${goal_name}: status=${goal_status} — skipping (non-active)"
    continue
  fi

  echo "Goal: ${goal_title:-${goal_name}}"
  echo "  File: ${goal_file}"

  # Extract KR block
  kr_block="$(extract_key_results "${goal_file}")"

  if [[ -z "${kr_block}" ]]; then
    echo "  (no key_results[] found)"
    echo ""
    continue
  fi

  # Parse each KR entry: look for id, text, status, weekly_perceptible fields
  # Each KR starts with a "  - " line (YAML list item).
  # We accumulate fields within each KR entry.
  proposed_lines=()  # Review: code-reviewer — plain assignment clearer than declare -a inside loop (F10)

  kr_id=""
  kr_text=""
  kr_status=""
  kr_weekly_perceptible=""
  in_kr_entry=0

  while IFS= read -r line; do
    # New KR item starts with "  - " in the YAML list
    if [[ "${line}" =~ ^[[:space:]]*-[[:space:]]+ ]]; then
      # Flush previous entry
      if [[ "${in_kr_entry}" -eq 1 ]]; then
        process_kr_entry "${kr_id}" "${kr_text}" "${kr_status}" "${kr_weekly_perceptible}"
      fi
      in_kr_entry=1
      kr_id=""
      kr_text=""
      kr_status="not-started"
      kr_weekly_perceptible="false"
      # Parse inline field on the "-" line (e.g. "  - id: foo" or "  - text: foo")
      local_rest="${line#*- }"
      if [[ "${local_rest}" =~ ^id:[[:space:]]*(.*) ]]; then
        kr_id="${BASH_REMATCH[1]}"
      elif [[ "${local_rest}" =~ ^text:[[:space:]]*(.*) ]]; then
        kr_text="${BASH_REMATCH[1]}"
      fi
    elif [[ "${in_kr_entry}" -eq 1 && "${line}" =~ ^[[:space:]]+([a-z_]+):[[:space:]]*(.*) ]]; then
      field_name="${BASH_REMATCH[1]}"
      field_val="${BASH_REMATCH[2]}"
      case "${field_name}" in
        id)                 kr_id="${field_val}" ;;
        text)               kr_text="${field_val}" ;;
        status)             kr_status="${field_val}" ;;
        weekly_perceptible) kr_weekly_perceptible="${field_val}" ;;
      esac
    fi
  done <<< "${kr_block}"

  # Flush last entry
  if [[ "${in_kr_entry}" -eq 1 ]]; then
    process_kr_entry "${kr_id}" "${kr_text}" "${kr_status}" "${kr_weekly_perceptible}"
  fi

  # Write proposed status back to artifact (NOT overwriting live status field).
  # Appends a "## KR Re-assessment (proposed)" section at end of frontmatter comment
  # or replaces an existing one.
  if [[ "${DRY_RUN}" -eq 0 && "${#proposed_lines[@]}" -gt 0 ]]; then
    # Build the proposed block — use SINCE as the temporal anchor, not today's date,
    # to avoid git diff churn on re-runs with identical status proposals (F5).
    proposed_block="# --- KR Re-assessment (proposed since=${SINCE}) ---"
    for pl in "${proposed_lines[@]}"; do
      proposed_block="${proposed_block}
${pl}"
    done
    proposed_block="${proposed_block}
# --- end proposed re-assessment ---"

    # Remove any prior proposed re-assessment block, then append
    # Use temp files for in-place edit (BSD-portable; no sed -i .bak portability issues).
    # Avoid passing multi-line strings as awk -v variables (awk newline-in-literal error
    # on BSD/POSIX awk); write the proposed block to its own temp file instead.
    tmp_stripped="$(mktemp)"
    tmp_block="$(mktemp)"

    # Write the proposed block to its own file so awk can read it via getline
    printf '%s\n' "${proposed_block}" > "${tmp_block}"

    # Strip existing proposed-assessment block from the source artifact
    awk '
      /^# --- KR Re-assessment \(proposed/ { skip=1 }
      skip && /^# --- end proposed re-assessment ---/ { skip=0; next }
      !skip { print }
    ' "${goal_file}" > "${tmp_stripped}"

    # Insert the block file just before the closing --- of frontmatter (second ---)
    awk -v blockfile="${tmp_block}" '
      BEGIN { fm_count=0; inserted=0 }
      /^---/ {
        fm_count++
        if (fm_count == 2 && !inserted) {
          while ((getline line < blockfile) > 0) { print line }
          close(blockfile)
          inserted=1
        }
      }
      { print }
    ' "${tmp_stripped}" > "${goal_file}"
    rm -f "${tmp_stripped}" "${tmp_block}"
  fi

  echo ""
done

echo "=== Re-assessment summary ==="
if [[ "${FLAGS_FOUND}" -eq 1 ]]; then
  echo "ACTION NEEDED: One or more KRs had no perceptible movement despite weekly_perceptible:true."
  echo "Review flagged KRs (marked '*** maybe-not-a-goal') and confirm or reclassify."
else
  echo "All active KRs with weekly_perceptible:true show movement (or none required assessment)."
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo ""
  echo "(dry-run mode — no files were modified)"
fi

echo ""
echo "Proposed statuses written to goal artifacts for EM/PM confirmation."
echo "These are PROPOSALS only — the live 'status' field is unchanged."
