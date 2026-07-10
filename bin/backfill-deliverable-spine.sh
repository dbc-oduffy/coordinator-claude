#!/usr/bin/env bash
# backfill-deliverable-spine.sh — Backfill deliverable_id onto fleet artifact corpus.
#
# Purpose: Group the board-relevant artifact corpus by workstream, emit a human-
#          reviewable GROUPING REPORT, then (with --write) stamp deliverable_id
#          onto mutable artifacts. Archived/immutable files are reported (derive-at-
#          emit) but NEVER written. Already-threaded artifacts (carrying deliverable_id)
#          are never re-minted.
#
# Corpus: handoff / plan / spinoff / roadmap / completion entities ONLY.
#   In scope:  state/handoffs/*.md   (active + spinoffs)
#              archive/handoffs/**   (archived handoffs — immutable)
#              docs/plans/*.md       (non-sidecar plans)
#              archive/completed/**  (completion entries — immutable)
#              state/roadmap/**/OVERVIEW.md  (roadmaps)
#              docs/ROADMAP.md
#   Out of scope: lessons, backlogs, memos, decisions, wiki, tasks/, templates/
#
# Grouping key:
#   Plans / handoffs / spinoffs: `workstream:` frontmatter field.
#   Completions: `chain:` field (semantic equivalent in that artifact type).
#   Roadmaps: `workstream:` field (if present).
#   Null / absent key → artifact placed in UNKNOWN group.
#
# Ambiguity (fail-loud, exit 2 in --dry-run; blocked in --write):
#   A group is ambiguous when it contains 2+ distinct plan slugs with NO
#   shared predecessor link — indicating two unrelated deliverables collided
#   on the same workstream string, or that a workstream string drifted.
#
# Idempotency:
#   Artifacts already carrying `deliverable_id:` are reported as "already-
#   threaded" and skipped (carry rule D1 — never re-mint).
#
# Usage:
#   backfill-deliverable-spine.sh [--dry-run] [--root <coordinator-root>]
#   backfill-deliverable-spine.sh --write [--root <coordinator-root>]
#
# Exit codes:
#   0 — clean (no ambiguities; write applied or dry-run report emitted)
#   1 — fatal error (missing dependency, bad arguments, corpus unreadable)
#   2 — ambiguous groups detected (human review required before --write)
#
# Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § C5, AC7

# ---------------------------------------------------------------------------
# Bash >=4 guard (BSD macOS ships 3.2; brew bash required)
# Must be reachable on 3.2 — only arithmetic and echo before this guard.
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MODE="dry-run"   # dry-run | write
COORDINATOR_ROOT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --write)
      MODE="write"
      shift
      ;;
    --root)
      COORDINATOR_ROOT_OVERRIDE="${2:-}"
      shift 2
      ;;
    -h|--help)
      grep '^#' "$0" | grep -v '^#!/' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      echo "Usage: backfill-deliverable-spine.sh [--dry-run|--write] [--root <path>]" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# COORDINATOR_ROOT discovery
# ---------------------------------------------------------------------------
if [[ -n "$COORDINATOR_ROOT_OVERRIDE" ]]; then
  COORDINATOR_ROOT="$COORDINATOR_ROOT_OVERRIDE"
else
  COORDINATOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

if [[ ! -d "$COORDINATOR_ROOT" ]]; then
  echo "ERROR: COORDINATOR_ROOT not found: $COORDINATOR_ROOT" >&2
  exit 1
fi

MINT_HELPER="${COORDINATOR_ROOT}/bin/mint-deliverable-id.sh"
if [[ ! -x "$MINT_HELPER" ]]; then
  echo "ERROR: mint-deliverable-id.sh not found or not executable: ${MINT_HELPER}" >&2
  echo "       (C3a must land before C5; run chunk C3a first)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Frontmatter field extraction helpers
# ---------------------------------------------------------------------------

# extract_fm_field <file> <field_name>
# Prints the scalar value for <field_name> from the YAML frontmatter block.
# Returns empty string when field is absent or null.
# Only reads the first frontmatter block (between first pair of --- delimiters).
extract_fm_field() {
  local file="$1" field="$2"
  awk -v field="$field" '
    BEGIN { fm=0; found=0 }
    /^---[[:space:]]*$/ {
      fm++
      if (fm == 2) exit
      next
    }
    fm == 1 {
      if ($0 ~ "^" field ":") {
        val = $0
        sub("^" field ":[[:space:]]*", "", val)
        # Strip surrounding quotes (single or double)
        if (val ~ /^".*"$/) { sub(/^"/, "", val); sub(/"$/, "", val) }
        if (val ~ /^'"'"'.*'"'"'$/) { sub(/^'"'"'/, "", val); sub(/'"'"'$/, "", val) }
        # Treat YAML null as empty
        if (val == "null" || val == "~") val = ""
        found = 1
        print val
        exit
      }
    }
  ' "$file"
}

# is_immutable_path <file>
# Returns 0 (true) when the file lives in an immutable archive path.
is_immutable_path() {
  local file="$1"
  case "$file" in
    */archive/handoffs/*|*/archive/completed/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# is_sidecar_plan <file>
# Returns 0 (true) when the plan file is a sidecar (not a primary plan artifact).
# Two sidecar conventions exist in the corpus:
#   Old: foo.md.sidecar-type.md   (double-md; caught by *.md.*.md)
#   New: foo.sidecar-type.md      (single-md suffix; caught by explicit type list)
# Exhaustive list derived from ls docs/plans/:
#   prior-art-check, coverage-check, plan-coverage-check, code-review,
#   code-review-slice-*, codereview-item*, the Staff Engineer-review, the Director of Engineering-review,
#   docs-check, doc-link-check, review (bare)
is_sidecar_plan() {
  local file="$1"
  local base
  base="$(basename "$file")"
  case "$base" in
    # Old double-md convention (foo.md.anything.md)
    *.md.*.md)
      return 0
      ;;
    # New single-md convention — enumerate known sidecar type suffixes
    *.prior-art-check.md|\
    *.coverage-check.md|\
    *.plan-coverage-check.md|\
    *.plan-coverage-check.*.md|\
    *.code-review.md|\
    *.code-review-slice-*.md|\
    *.codereview-item*.md|\
    *.the Staff Engineer-review.md|\
    *.the Director of Engineering-review.md|\
    *.docs-check.md|\
    *.doc-link-check.md|\
    *.review.md)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# classify_artifact <file>
# Prints the artifact class: plan | handoff | handoff-archived | completion | roadmap | unknown
classify_artifact() {
  local file="$1"
  case "$file" in
    */docs/plans/*.md)
      echo "plan"
      ;;
    */state/handoffs/*.md)
      echo "handoff"
      ;;
    */archive/handoffs/*)
      echo "handoff-archived"
      ;;
    */archive/completed/*)
      echo "completion"
      ;;
    */state/roadmap/*/OVERVIEW.md|*/docs/ROADMAP.md)
      echo "roadmap"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

# get_workstream_key <file> <artifact_class>
# Extracts the group key for the artifact.
# Plans / handoffs / spinoffs / roadmaps: `workstream:` field.
# Completions: `chain:` field.
get_workstream_key() {
  local file="$1" class="$2"
  local key=""
  if [[ "$class" == "completion" ]]; then
    key="$(extract_fm_field "$file" "chain")"
  else
    key="$(extract_fm_field "$file" "workstream")"
  fi
  printf '%s' "$key"
}

# ---------------------------------------------------------------------------
# Corpus enumeration
# ---------------------------------------------------------------------------
declare -a CORPUS_FILES=()

# 1. Active handoffs (includes spinoffs with kind: spinoff / kind: spinoff-roadmap)
HANDOFFS_DIR="${COORDINATOR_ROOT}/state/handoffs"
if [[ -d "$HANDOFFS_DIR" ]]; then
  while IFS= read -r -d '' f; do
    CORPUS_FILES+=("$f")
  done < <(find "$HANDOFFS_DIR" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
fi

# 2. Archived handoffs (immutable — derive-at-emit)
HANDOFFS_ARCH_DIR="${COORDINATOR_ROOT}/archive/handoffs"
if [[ -d "$HANDOFFS_ARCH_DIR" ]]; then
  while IFS= read -r -d '' f; do
    CORPUS_FILES+=("$f")
  done < <(find "$HANDOFFS_ARCH_DIR" -name "*.md" -print0 2>/dev/null)
fi

# 3. Non-sidecar plan files
PLANS_DIR="${COORDINATOR_ROOT}/docs/plans"
if [[ -d "$PLANS_DIR" ]]; then
  while IFS= read -r -d '' f; do
    if ! is_sidecar_plan "$f"; then
      CORPUS_FILES+=("$f")
    fi
  done < <(find "$PLANS_DIR" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
fi

# 4. Completion entries (immutable — derive-at-emit)
COMPLETED_DIR="${COORDINATOR_ROOT}/archive/completed"
if [[ -d "$COMPLETED_DIR" ]]; then
  while IFS= read -r -d '' f; do
    CORPUS_FILES+=("$f")
  done < <(find "$COMPLETED_DIR" -name "*.md" -print0 2>/dev/null)
fi

# 5. Roadmaps (state/roadmap/*/OVERVIEW.md + docs/ROADMAP.md)
ROADMAP_STATE_DIR="${COORDINATOR_ROOT}/state/roadmap"
if [[ -d "$ROADMAP_STATE_DIR" ]]; then
  while IFS= read -r -d '' f; do
    CORPUS_FILES+=("$f")
  done < <(find "$ROADMAP_STATE_DIR" -name "OVERVIEW.md" -print0 2>/dev/null)
fi
ROADMAP_DOC="${COORDINATOR_ROOT}/docs/ROADMAP.md"
if [[ -f "$ROADMAP_DOC" ]]; then
  CORPUS_FILES+=("$ROADMAP_DOC")
fi

TOTAL_SCANNED="${#CORPUS_FILES[@]}"

# ---------------------------------------------------------------------------
# Grouping pass
# ---------------------------------------------------------------------------
# Group key → list of file paths (newline-separated in value)
declare -A GROUP_FILES         # group_key → newline-delimited file paths
declare -A GROUP_CLASSES       # group_key → artifact classes seen (space-sep)
declare -A GROUP_PLAN_SLUGS    # group_key → distinct plan slugs seen (space-sep)

UNKNOWN_GROUP_KEY="__UNKNOWN__"
ALREADY_THREADED_COUNT=0
declare -a ALREADY_THREADED_FILES=()

for f in "${CORPUS_FILES[@]}"; do
  class="$(classify_artifact "$f")"

  # Check if already carrying deliverable_id
  existing_id="$(extract_fm_field "$f" "deliverable_id")"
  if [[ -n "$existing_id" ]]; then
    ALREADY_THREADED_COUNT=$(( ALREADY_THREADED_COUNT + 1 ))
    ALREADY_THREADED_FILES+=("$f|$existing_id")
    continue
  fi

  # Get workstream group key
  ws_key="$(get_workstream_key "$f" "$class")"
  if [[ -z "$ws_key" ]]; then
    ws_key="$UNKNOWN_GROUP_KEY"
  fi

  # Append file to its group
  if [[ -v "GROUP_FILES[$ws_key]" ]]; then
    GROUP_FILES["$ws_key"]+=$'\n'"$f"
  else
    GROUP_FILES["$ws_key"]="$f"
  fi

  # Track classes seen in this group
  if [[ -v "GROUP_CLASSES[$ws_key]" ]]; then
    GROUP_CLASSES["$ws_key"]+=" $class"
  else
    GROUP_CLASSES["$ws_key"]="$class"
  fi

  # Track distinct plan slugs for ambiguity detection
  if [[ "$class" == "plan" ]]; then
    plan_slug="$(extract_fm_field "$f" "slug")"
    if [[ -z "$plan_slug" ]]; then
      # Derive slug from filename
      plan_slug="$(basename "$f" .md | sed 's/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-//')"
    fi
    if [[ -v "GROUP_PLAN_SLUGS[$ws_key]" ]]; then
      # Only add if not already present
      if [[ "${GROUP_PLAN_SLUGS[$ws_key]}" != *"$plan_slug"* ]]; then
        GROUP_PLAN_SLUGS["$ws_key"]+=" $plan_slug"
      fi
    else
      GROUP_PLAN_SLUGS["$ws_key"]="$plan_slug"
    fi
  fi
done

# ---------------------------------------------------------------------------
# Ambiguity detection
# ---------------------------------------------------------------------------
declare -a AMBIGUOUS_KEYS=()

for ws_key in "${!GROUP_PLAN_SLUGS[@]}"; do
  [[ "$ws_key" == "$UNKNOWN_GROUP_KEY" ]] && continue
  slugs="${GROUP_PLAN_SLUGS[$ws_key]}"
  # Count words (distinct plan slugs)
  slug_count=$(echo "$slugs" | wc -w | tr -d ' ')
  if (( slug_count > 1 )); then
    AMBIGUOUS_KEYS+=("$ws_key")
  fi
done

AMBIGUOUS_COUNT="${#AMBIGUOUS_KEYS[@]}"

# ---------------------------------------------------------------------------
# Compute group metrics
# ---------------------------------------------------------------------------
KNOWN_GROUP_COUNT=0
UNKNOWN_COUNT=0
MUTABLE_TO_THREAD=0    # mutable artifacts in NAMED groups — will receive deliverable_id
MUTABLE_UNKNOWN=0      # mutable artifacts in UNKNOWN group — will skip (no group key)
IMMUTABLE_DERIVE=0     # archived/immutable — derive-at-emit, no write

for ws_key in "${!GROUP_FILES[@]}"; do
  mapfile -t gfiles <<< "${GROUP_FILES[$ws_key]}"
  if [[ "$ws_key" == "$UNKNOWN_GROUP_KEY" ]]; then
    UNKNOWN_COUNT="${#gfiles[@]}"
    for gf in "${gfiles[@]}"; do
      if is_immutable_path "$gf"; then
        IMMUTABLE_DERIVE=$(( IMMUTABLE_DERIVE + 1 ))
      else
        MUTABLE_UNKNOWN=$(( MUTABLE_UNKNOWN + 1 ))
      fi
    done
  else
    KNOWN_GROUP_COUNT=$(( KNOWN_GROUP_COUNT + 1 ))
    for gf in "${gfiles[@]}"; do
      if is_immutable_path "$gf"; then
        IMMUTABLE_DERIVE=$(( IMMUTABLE_DERIVE + 1 ))
      else
        MUTABLE_TO_THREAD=$(( MUTABLE_TO_THREAD + 1 ))
      fi
    done
  fi
done

# ---------------------------------------------------------------------------
# Emit GROUPING REPORT (always to stdout)
# ---------------------------------------------------------------------------
echo "============================================================"
echo "GROUPING REPORT — backfill-deliverable-spine"
echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Root: ${COORDINATOR_ROOT}"
echo "Mode: ${MODE}"
echo "============================================================"
echo ""
echo "SUMMARY"
echo "-------"
echo "  Total artifacts scanned:      ${TOTAL_SCANNED}"
echo "  Already-threaded (skip):      ${ALREADY_THREADED_COUNT}"
echo "  Known workstream groups:      ${KNOWN_GROUP_COUNT}"
echo "  Unknown (no workstream):      ${UNKNOWN_COUNT}"
echo "  Ambiguous groups:             ${AMBIGUOUS_COUNT}"
echo "  Mutable to stamp (named):     ${MUTABLE_TO_THREAD}"
echo "  Mutable (unknown, skip):      ${MUTABLE_UNKNOWN}"
echo "  Immutable (derive-at-emit):   ${IMMUTABLE_DERIVE}"
echo ""

# Already-threaded artifacts
if (( ALREADY_THREADED_COUNT > 0 )); then
  echo "ALREADY-THREADED (carry — no action):"
  for entry in "${ALREADY_THREADED_FILES[@]}"; do
    epath="${entry%%|*}"
    eid="${entry##*|}"
    rel="${epath#${COORDINATOR_ROOT}/}"
    echo "  [${eid}]  ${rel}"
  done
  echo ""
fi

# Named groups
if (( KNOWN_GROUP_COUNT > 0 )); then
  echo "------------------------------------------------------------"
  echo "NAMED GROUPS"
  echo "------------------------------------------------------------"

  for ws_key in $(printf '%s\n' "${!GROUP_FILES[@]}" | sort); do
    [[ "$ws_key" == "$UNKNOWN_GROUP_KEY" ]] && continue

    mapfile -t gfiles <<< "${GROUP_FILES[$ws_key]}"

    # Determine ambiguity
    is_ambig=false
    for ak in "${AMBIGUOUS_KEYS[@]}"; do
      [[ "$ak" == "$ws_key" ]] && is_ambig=true && break
    done

    # Propose a deliverable_id for this group (deterministic from workstream key)
    # Use the workstream key as slug for the proposal; actual mint happens in --write
    proposed_id=""
    # Find the earliest artifact's stub_id (for spinoff-roadmap) or use ws_key as slug
    earliest_stub=""
    for gf in "${gfiles[@]}"; do
      gf_class="$(classify_artifact "$gf")"
      if [[ "$gf_class" == "handoff" || "$gf_class" == "handoff-archived" ]]; then
        gf_kind="$(extract_fm_field "$gf" "kind")"
        if [[ "$gf_kind" == "spinoff-roadmap" ]]; then
          candidate_stub="$(extract_fm_field "$gf" "stub_id")"
          if [[ -n "$candidate_stub" ]]; then
            earliest_stub="$candidate_stub"
            break
          fi
        fi
      fi
    done

    if [[ -n "$earliest_stub" ]]; then
      proposed_id="dlv-${earliest_stub}  [from stub_id]"
    else
      # Use a deterministic preview — actual hex minted at --write time
      ws_slug="${ws_key//[^a-zA-Z0-9_-]/-}"
      # Truncate to keep id readable
      ws_slug="${ws_slug:0:40}"
      proposed_id="dlv-${ws_slug}-??????  [hex minted at --write time]"
    fi

    if [[ "$is_ambig" == "true" ]]; then
      echo ""
      echo "GROUP [AMBIGUOUS]: ${ws_key}"
      echo "  Proposed id: ${proposed_id}"
      echo "  AMBIGUITY: 2+ distinct plan slugs in this workstream group."
      echo "             Two unrelated deliverables may share this workstream string."
      echo "             Plan slugs: ${GROUP_PLAN_SLUGS[$ws_key]:-<none>}"
      echo "  Artifacts:"
    else
      echo ""
      echo "GROUP [OK]: ${ws_key}"
      echo "  Proposed id: ${proposed_id}"
      echo "  Artifacts:"
    fi

    for gf in "${gfiles[@]}"; do
      gf_class="$(classify_artifact "$gf")"
      gf_rel="${gf#${COORDINATOR_ROOT}/}"
      if is_immutable_path "$gf"; then
        echo "    [${gf_class}] ${gf_rel}  (immutable — derive-at-emit, no write)"
      else
        echo "    [${gf_class}] ${gf_rel}  (mutable — will stamp deliverable_id)"
      fi
    done
  done
  echo ""
fi

# Unknown group
if [[ -v "GROUP_FILES[$UNKNOWN_GROUP_KEY]" ]]; then
  echo "------------------------------------------------------------"
  echo "UNKNOWN GROUP (no workstream / chain field)"
  echo "  These artifacts have no deterministic group key."
  echo "  They will carry null deliverable_id until the field is added."
  echo "  Artifacts:"
  mapfile -t unknown_files <<< "${GROUP_FILES[$UNKNOWN_GROUP_KEY]}"
  for uf in "${unknown_files[@]}"; do
    uf_class="$(classify_artifact "$uf")"
    uf_rel="${uf#${COORDINATOR_ROOT}/}"
    if is_immutable_path "$uf"; then
      echo "    [${uf_class}] ${uf_rel}  (immutable — derive-at-emit)"
    else
      echo "    [${uf_class}] ${uf_rel}  (mutable — no workstream, skip)"
    fi
  done
  echo ""
fi

# Ambiguity summary
if (( AMBIGUOUS_COUNT > 0 )); then
  echo "============================================================"
  echo "AMBIGUOUS GROUPS — HUMAN REVIEW REQUIRED"
  echo "============================================================"
  echo "  The following workstream keys are ambiguous and cannot be"
  echo "  assigned a deliverable_id without human disambiguation."
  echo "  Resolve before running --write:"
  echo ""
  for ak in "${AMBIGUOUS_KEYS[@]}"; do
    echo "  - '${ak}' (plan slugs: ${GROUP_PLAN_SLUGS[$ak]:-<none>})"
  done
  echo ""
fi

echo "============================================================"
if (( AMBIGUOUS_COUNT > 0 )); then
  echo "STATUS: REVIEW REQUIRED (${AMBIGUOUS_COUNT} ambiguous group(s))"
  echo "  Fix ambiguities before running --write."
else
  echo "STATUS: CLEAN — no ambiguities detected"
  if [[ "$MODE" == "dry-run" ]]; then
    echo "  Run with --write to stamp deliverable_ids onto mutable artifacts."
  fi
fi
echo "============================================================"

# ---------------------------------------------------------------------------
# Write mode — stamp deliverable_id onto mutable artifacts
# ---------------------------------------------------------------------------
if [[ "$MODE" == "write" ]]; then
  if (( AMBIGUOUS_COUNT > 0 )); then
    echo "" >&2
    echo "ERROR: Cannot --write while ambiguous groups exist." >&2
    echo "       Resolve the ${AMBIGUOUS_COUNT} ambiguous group(s) above first." >&2
    exit 2
  fi

  echo ""
  echo "------------------------------------------------------------"
  echo "WRITE PASS — stamping deliverable_ids"
  echo "------------------------------------------------------------"

  STAMPED=0
  SKIPPED_IMMUTABLE=0
  SKIPPED_UNKNOWN=0

  for ws_key in "${!GROUP_FILES[@]}"; do
    [[ "$ws_key" == "$UNKNOWN_GROUP_KEY" ]] && continue

    mapfile -t gfiles <<< "${GROUP_FILES[$ws_key]}"

    # Mint ONE id for the group (idempotent: if any artifact already has id, carry it)
    group_id=""
    # First check if any mutable artifact in this group already has an id (from a prior partial write)
    for gf in "${gfiles[@]}"; do
      existing_id="$(extract_fm_field "$gf" "deliverable_id")"
      if [[ -n "$existing_id" ]]; then
        group_id="$existing_id"
        echo "  [carry] Using existing id from corpus: ${group_id}" >&2
        break
      fi
    done

    # If no existing id, mint one
    if [[ -z "$group_id" ]]; then
      # Check for spinoff-roadmap stub_id
      stub_id_found=""
      for gf in "${gfiles[@]}"; do
        gf_kind="$(extract_fm_field "$gf" "kind")"
        if [[ "$gf_kind" == "spinoff-roadmap" ]]; then
          candidate_stub="$(extract_fm_field "$gf" "stub_id")"
          if [[ -n "$candidate_stub" ]]; then
            stub_id_found="$candidate_stub"
            break
          fi
        fi
      done

      if [[ -n "$stub_id_found" ]]; then
        group_id="$(bash "$MINT_HELPER" --stub-id "$stub_id_found" 2>/dev/null)"
      else
        # Use workstream key as slug (sanitize to valid slug chars)
        ws_slug="${ws_key//[^a-zA-Z0-9_-]/-}"
        ws_slug="${ws_slug:0:40}"
        group_id="$(bash "$MINT_HELPER" --slug "$ws_slug" 2>/dev/null)"
      fi
      echo "  [mint] ${ws_key} → ${group_id}" >&2
    fi

    # Stamp each mutable artifact in the group
    for gf in "${gfiles[@]}"; do
      if is_immutable_path "$gf"; then
        gf_rel="${gf#${COORDINATOR_ROOT}/}"
        echo "  [skip-immutable] ${gf_rel}  (derive-at-emit)"
        SKIPPED_IMMUTABLE=$(( SKIPPED_IMMUTABLE + 1 ))
        continue
      fi

      # Check if already threaded (should have been caught earlier, but guard idempotency)
      existing_id="$(extract_fm_field "$gf" "deliverable_id")"
      if [[ -n "$existing_id" ]]; then
        gf_rel="${gf#${COORDINATOR_ROOT}/}"
        echo "  [skip-threaded] ${gf_rel}  (already has id: ${existing_id})"
        continue
      fi

      gf_rel="${gf#${COORDINATOR_ROOT}/}"
      gf_class="$(classify_artifact "$gf")"

      # Inject deliverable_id into frontmatter after the opening ---
      # Strategy: insert the field after the first --- line
      # Use a temp file for atomic write
      TMPFILE="${gf}.backfill.tmp.$$"
      awk -v new_id="$group_id" '
        BEGIN { injected=0; fm=0 }
        /^---[[:space:]]*$/ {
          fm++
          print
          # After opening ---, inject our field (once only)
          if (fm == 1 && !injected) {
            print "deliverable_id: " new_id
            injected=1
          }
          next
        }
        # Skip any existing deliverable_id line (should not exist, but guard idempotency)
        fm == 1 && /^deliverable_id:/ { next }
        { print }
      ' "$gf" > "$TMPFILE"
      mv "$TMPFILE" "$gf"

      echo "  [stamp] ${gf_rel}  → ${group_id}"
      STAMPED=$(( STAMPED + 1 ))
    done
  done

  # Unknown group: skip with note
  if [[ -v "GROUP_FILES[$UNKNOWN_GROUP_KEY]" ]]; then
    mapfile -t unknown_files <<< "${GROUP_FILES[$UNKNOWN_GROUP_KEY]}"
    for uf in "${unknown_files[@]}"; do
      uf_rel="${uf#${COORDINATOR_ROOT}/}"
      if ! is_immutable_path "$uf"; then
        echo "  [skip-unknown] ${uf_rel}  (no workstream field — cannot assign id)"
        SKIPPED_UNKNOWN=$(( SKIPPED_UNKNOWN + 1 ))
      fi
    done
  fi

  echo ""
  echo "WRITE COMPLETE:"
  echo "  Stamped:            ${STAMPED}"
  echo "  Skipped (immutable): ${SKIPPED_IMMUTABLE}"
  echo "  Skipped (unknown):   ${SKIPPED_UNKNOWN}"
fi

# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------
if (( AMBIGUOUS_COUNT > 0 )); then
  exit 2
fi
exit 0
