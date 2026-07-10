#!/usr/bin/env bash
# handoff-gate-aging.sh — mechanized 14d/7d gate-recheck aging check
#
# Mechanizes the aging-reconcile predicate that was pure EM-arithmetic prose
# (pickup/SKILL.md § Step 3.4d, docs/wiki/spinoff-handoffs.md § Awaiting_gate
# aging § Thresholds) into a single fail-loud tool call. A stale awaiting_gate
# handoff must not silently re-surface in the pickup/workday-start queues —
# this script is the detector; the caller drives the actual re-check via the
# existing `gate-recheck` verb on `handoff-transition.js` (C5b).
#
# Predicate — a handoff is STALE (force re-check) iff ALL THREE hold:
#   1. now - created: >= 14 days
#   2. deployment_state: awaiting_gate
#   3. last_gate_recheck: absent, OR last_gate_recheck: >= 7 days ago
#
# Usage:
#   handoff-gate-aging.sh <handoff-path>            # single-file check
#   handoff-gate-aging.sh <directory>                # scan *.md files (one level)
#
# Output: one line per stale handoff (path + reason), to stdout.
# Exit codes:
#   0 — no stale awaiting_gate handoffs found
#   1 — one or more stale awaiting_gate handoffs found (fail loud)
#   2 — internal error (missing path, bad frontmatter, unparseable date)
#
# Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5c
# Doctrine anchor: docs/wiki/spinoff-handoffs.md § Awaiting_gate aging
# Portability (DR-148): bash >= 4 + BSD coreutils; date -d/-j fallback chain, no GNU-only flags.

set -euo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "handoff-gate-aging.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2
fi

AGING_THRESHOLD_DAYS=14
RECHECK_COOLDOWN_DAYS=7

TARGET="${1-}"
if [[ -z "$TARGET" ]]; then
  echo "handoff-gate-aging.sh: missing argument: <handoff-path-or-directory>" >&2
  exit 2
fi
if [[ ! -e "$TARGET" ]]; then
  echo "handoff-gate-aging.sh: path not found: ${TARGET}" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Portable date-to-epoch (mirrors check-atlas-watch-drift.sh / aggregate-chain-loe.sh
# convention: GNU `date -d` tried first, BSD `date -j -f` fallback).
# ---------------------------------------------------------------------------
_date_to_epoch() {
  local d="$1" e=""
  if date --version >/dev/null 2>&1; then
    e=$(date -d "$d" +%s 2>/dev/null || echo "")
  else
    e=$(date -j -f "%Y-%m-%d" "$d" +%s 2>/dev/null || echo "")
  fi
  printf '%s' "$e"
}

TODAY_EPOCH=$(date +%s)

# ---------------------------------------------------------------------------
# Read a top-level frontmatter scalar field from a handoff file.
# Mirrors the awk `/^---$/{n++; next} n==1 && /^field:/` convention used
# throughout commands/workday-start.md and commands/workday-complete.md.
# Strips surrounding double-quotes (gate_dependency is often quoted).
# ---------------------------------------------------------------------------
_read_fm_field() {
  local file="$1" field="$2"
  awk -v f="^${field}:" '
    /^---$/ { n++; next }
    n==1 && $0 ~ f {
      sub(f "[[:space:]]*", "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$file" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Evaluate the 14d/7d aging predicate for one handoff file.
# Prints "STALE" + a reason to stdout when all three conditions hold;
# prints nothing when any condition fails. Returns 1 for internal parse
# errors ONLY (caller distinguishes via the printed marker, not rc).
# ---------------------------------------------------------------------------
_check_one() {
  local file="$1"
  local deployment_state created last_recheck

  deployment_state="$(_read_fm_field "$file" "deployment_state")"
  # Condition 2: deployment_state must be awaiting_gate — cheap short-circuit.
  [[ "$deployment_state" == "awaiting_gate" ]] || return 0

  created="$(_read_fm_field "$file" "created")"
  if [[ -z "$created" ]]; then
    echo "handoff-gate-aging.sh: ${file}: awaiting_gate handoff missing 'created:' field — cannot evaluate aging" >&2
    return 2
  fi

  local created_epoch
  created_epoch="$(_date_to_epoch "$created")"
  if [[ -z "$created_epoch" ]]; then
    echo "handoff-gate-aging.sh: ${file}: unparseable created date '${created}'" >&2
    return 2
  fi

  local age_days=$(( (TODAY_EPOCH - created_epoch) / 86400 ))
  # Condition 1: age >= 14 days.
  (( age_days >= AGING_THRESHOLD_DAYS )) || return 0

  last_recheck="$(_read_fm_field "$file" "last_gate_recheck")"
  if [[ -n "$last_recheck" ]]; then
    local recheck_epoch
    recheck_epoch="$(_date_to_epoch "$last_recheck")"
    if [[ -z "$recheck_epoch" ]]; then
      echo "handoff-gate-aging.sh: ${file}: unparseable last_gate_recheck date '${last_recheck}'" >&2
      return 2
    fi
    local recheck_age_days=$(( (TODAY_EPOCH - recheck_epoch) / 86400 ))
    # Condition 3: last_gate_recheck must be >= 7 days ago to re-fire.
    (( recheck_age_days >= RECHECK_COOLDOWN_DAYS )) || return 0
    echo "STALE: ${file} (created ${age_days}d ago, last_gate_recheck ${recheck_age_days}d ago)"
  else
    # Condition 3: absent last_gate_recheck counts as due.
    echo "STALE: ${file} (created ${age_days}d ago, last_gate_recheck absent)"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Collect target files: single file, or one-level *.md scan of a directory.
# ---------------------------------------------------------------------------
FILES=()
if [[ -d "$TARGET" ]]; then
  # Review: code-reviewer F5 — state/handoffs/ is flat by design; -maxdepth 1 assumes
  # no subdirectories. Update this scan if that layout assumption changes.
  while IFS= read -r -d '' f; do
    FILES+=("$f")
  done < <(find "$TARGET" -maxdepth 1 -name '*.md' -print0 2>/dev/null)
else
  FILES=("$TARGET")
fi

STALE_COUNT=0
PARSE_ERROR=0
for f in "${FILES[@]}"; do
  out="$(_check_one "$f")" || PARSE_ERROR=1
  if [[ -n "$out" ]]; then
    echo "$out"
    STALE_COUNT=$((STALE_COUNT + 1))
  fi
done

if [[ "$PARSE_ERROR" -eq 1 && "$STALE_COUNT" -eq 0 ]]; then
  exit 2
fi
if [[ "$STALE_COUNT" -gt 0 ]]; then
  exit 1
fi
exit 0
