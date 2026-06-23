#!/usr/bin/env bash
# count-distill-backlog.sh — heuristic count of completion-log entries pending wiki distillation.
#
# Purpose: scan archive/completed entries older than threshold_days and report how many
# have not yet been absorbed into the wiki. The count is approximate — chain:null entries
# cannot be matched by chain slug and will always count as pending.
#
# Usage:
#   count-distill-backlog.sh              # prints pending_count integer
#   count-distill-backlog.sh --format json  # prints single-line JSON object
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C1
# Review: A-F15 — fabricated plan path repointed to real plan
set -euo pipefail

# ---------------------------------------------------------------------------
# Repo root resolution — cwd-scope-guard form (mandatory verbatim per spec)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer resolving from script location (bin/ -> coordinator/ -> plugins/ -> .claude/)
_SCRIPT_INFERRED_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
if [[ -d "$_SCRIPT_INFERRED_ROOT/archive/completed" ]]; then
  ROOT="$_SCRIPT_INFERRED_ROOT"
else
  # Mandatory env-fallback form (verbatim per spec — do NOT use ${CLAUDE_HOME:-$HOME/.claude})
  ROOT="${CLAUDE_HOME:-$HOME}/.claude"
fi

ARCHIVE_ROOT="$ROOT/archive/completed"
WIKI_LOCAL="$ROOT/docs/wiki"
WIKI_COORD="$ROOT/plugins/coordinator/docs/wiki"

THRESHOLD_DAYS=30
FORMAT="${1:-}"

# ---------------------------------------------------------------------------
# Fail loud if archive root is missing
# ---------------------------------------------------------------------------
if [[ ! -d "$ARCHIVE_ROOT" ]]; then
  echo "ERROR: archive root not found: $ARCHIVE_ROOT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Compute cutoff date (BSD-portable: date -v-Nd; GNU fallback)
# ---------------------------------------------------------------------------
if date -v 1d +%F &>/dev/null; then
  # BSD date (macOS) — Review: A-F6 drop redundant 2>&1 after &>/dev/null
  CUTOFF="$(date -v-${THRESHOLD_DAYS}d +%F)"
else
  # GNU date (Linux)
  CUTOFF="$(date -d "${THRESHOLD_DAYS} days ago" +%F)"
fi
# Review: A-F2 — fail loud when neither BSD nor GNU date works (prevents silent pending=0)
[[ -n "${CUTOFF:-}" ]] || { echo "ERROR: cannot compute cutoff date (neither BSD date -v nor GNU date -d works)" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Scan entries
# ---------------------------------------------------------------------------
total_entries=0
pending_count=0
# Review: A-F7 — track whether the archive glob matched any files at all;
# if it matches zero files (not just zero OLDER entries), the state is truly
# unknown. zero matches here with non-empty archive → unknown; zero old entries
# in a populated archive → fresh (genuinely clean state, not can't-compute).
archive_files_found=0

for entry in "$ARCHIVE_ROOT"/*/*.md; do
  # Skip if glob matched nothing
  [[ -e "$entry" ]] || continue
  archive_files_found=$((archive_files_found + 1))

  # Extract created date from YAML frontmatter (grep may return 1 — tolerate)
  created="$(grep -m1 '^created:' "$entry" 2>/dev/null || true)"
  created="$(echo "$created" | awk '{print $2}')"
  [[ -z "$created" ]] && continue  # no frontmatter — skip (legacy rollup files)

  # Only process entries strictly older than the cutoff
  [[ "$created" < "$CUTOFF" ]] || continue

  total_entries=$((total_entries + 1))

  # Derive slug: use chain: if non-null, else strip date+hash from filename
  chain="$(grep -m1 '^chain:' "$entry" 2>/dev/null || true)"
  chain="$(echo "$chain" | awk '{print $2}')"
  if [[ "$chain" != "null" && -n "$chain" ]]; then
    slug="$chain"
  else
    base="$(basename "$entry" .md)"
    # strip trailing 6-char hex suffix (e.g. -a62b94)
    no_hash="${base%-??????}"
    # strip leading YYYY-MM-DD- date prefix
    slug="${no_hash#????-??-??-}"
  fi

  # Check if slug appears in either wiki location
  found=0

  if ls "$WIKI_LOCAL"/*.md &>/dev/null 2>&1; then
    if grep -ql "$slug" "$WIKI_LOCAL"/*.md 2>/dev/null || false; then
      found=1
    fi
  fi

  if [[ "$found" -eq 0 ]] && ls "$WIKI_COORD"/*.md &>/dev/null 2>&1; then
    if grep -ql "$slug" "$WIKI_COORD"/*.md 2>/dev/null || false; then
      found=1
    fi
  fi

  if [[ "$found" -eq 0 ]]; then
    pending_count=$((pending_count + 1))
  fi
done

# ---------------------------------------------------------------------------
# Compute band
# ---------------------------------------------------------------------------
# Review: A-F7 — `unknown` = couldn't compute (archive glob matched zero files).
# `fresh` = archive scanned, no entries older than cutoff (genuinely clean).
# `mild`/`stale` = computable pending count 1-5 / >=6.
if [[ "$archive_files_found" -eq 0 ]]; then
  # No files in archive at all — truly can't say (empty or mis-configured)
  computed_state="unknown"
elif [[ "$pending_count" -eq 0 ]]; then
  # Archive scanned, nothing older than threshold pending → clean
  computed_state="fresh"
elif [[ "$pending_count" -le 5 ]]; then
  computed_state="mild"
else
  computed_state="stale"
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
if [[ "$FORMAT" == "--format" && "${2:-}" == "json" ]] || [[ "$FORMAT" == "--format=json" ]]; then
  jq -cn \
    --argjson pending_count "$pending_count" \
    --argjson threshold_days "$THRESHOLD_DAYS" \
    --arg computed_state "$computed_state" \
    '{"pending_count": $pending_count, "threshold_days": $threshold_days, "computed_state": $computed_state}'
else
  echo "$pending_count"
fi
