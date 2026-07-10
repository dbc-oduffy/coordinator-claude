#!/usr/bin/env bash
# workday-start-cross-repo-memo-outbox-surface.sh — Surface stale outbox memo drafts.
#
# Purpose: Scan THIS repo's state/memo-outbox/ directory for draft memos whose mtime
# exceeds the stale threshold (default: 24h, configurable via COORDINATOR_OUTBOX_STALE_HOURS).
# Emits one nudge line per stale draft so the EM can act (send / compose / discard).
# Silent when outbox is absent, empty, or all drafts are under the threshold.
#
# Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md §C4
#
# Negative-spec: Surfacer is offer-shape ONLY — emits three action verbs as options,
# never auto-discards, never auto-sends. Lifecycle mutation lives solely in the CLI
# subcommands per the /workstream-start surfaces, /pickup acts boundary
# (cross-repo-communication.md:315).
#
# Output format (one line per stale draft):
#   Outbox draft <topic> staged <N>h ago → <to>  :: <title>
#     → send | compose | discard
#
# Usage:
#   bash workday-start-cross-repo-memo-outbox-surface.sh [REPO_ROOT]
#   COORDINATOR_OUTBOX_DIR=/some/tmpdir bash workday-start-cross-repo-memo-outbox-surface.sh
#
# Environment:
#   COORDINATOR_OUTBOX_STALE_HOURS  — stale threshold in hours (default: 24).
#   COORDINATOR_OUTBOX_DIR          — override outbox directory (for tests only).
#
# Exit: always 0. Emits nothing when no qualifying drafts exist (silent per spec).

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  echo "bash >= 4 required (got ${BASH_VERSION:-unknown}). Install via brew: brew install bash" >&2
  exit 1
fi

set -euo pipefail

# Source state-root seam — routes per-repo state/ refs through coordinator_state_root
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4 / AC4
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# Resolve the outbox directory.
# Priority: COORDINATOR_OUTBOX_DIR env override → git root → cwd.
# ---------------------------------------------------------------------------
if [[ -n "${COORDINATOR_OUTBOX_DIR:-}" ]]; then
  OUTBOX_DIR="$COORDINATOR_OUTBOX_DIR"
else
  # First arg (if provided) is REPO_ROOT override (used by test fixture)
  _repo_root_arg="${1:-}"
  if [[ -n "$_repo_root_arg" && -d "$_repo_root_arg" ]]; then
    OUTBOX_DIR="${_repo_root_arg}/state/memo-outbox"
  elif git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
    OUTBOX_DIR="$(coordinator_state_root)/memo-outbox"
  else
    # Not in a git repo — stay silent per spec.
    exit 0
  fi
fi

# Stale threshold in hours.
STALE_HOURS="${COORDINATOR_OUTBOX_STALE_HOURS:-24}"

# ---------------------------------------------------------------------------
# Guard: silent on absent or empty directory.
# ---------------------------------------------------------------------------
[[ -d "$OUTBOX_DIR" ]] || exit 0

# ---------------------------------------------------------------------------
# Detect stat flavour once: GNU stat (-c %Y) or BSD stat (-f %m).
# Both return epoch seconds. Falls back to Python if neither is available.
# ---------------------------------------------------------------------------
_STAT_CMD=""
if command -v stat >/dev/null 2>&1; then
  # Try GNU form
  if stat -c %Y "$OUTBOX_DIR" >/dev/null 2>&1; then
    _STAT_CMD="gnu"
  # Try BSD form
  elif stat -f %m "$OUTBOX_DIR" >/dev/null 2>&1; then
    _STAT_CMD="bsd"
  fi
fi

# Python fallback for mtime when stat is unavailable or non-standard.
_PYTHON_BIN=""
if [[ -z "$_STAT_CMD" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    _PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    _PYTHON_BIN=python
  else
    # No stat, no python — cannot determine mtime. Stay silent.
    exit 0
  fi
fi

# Helper: get mtime in epoch seconds for a file.
get_mtime() {
  local f="$1"
  if [[ "$_STAT_CMD" == "gnu" ]]; then
    stat -c %Y "$f" 2>/dev/null || echo 0
  elif [[ "$_STAT_CMD" == "bsd" ]]; then
    stat -f %m "$f" 2>/dev/null || echo 0
  elif [[ -n "$_PYTHON_BIN" ]]; then
    # Review: code-reviewer — pass $f via sys.argv to avoid shell-string injection
    # (a filename containing a single-quote could escape the Python string literal)
    "$_PYTHON_BIN" -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" -- "$f" 2>/dev/null || echo 0
  else
    echo 0
  fi
}

# Current epoch (POSIX date +%s is supported on GNU, BSD, and Git-for-Windows).
NOW_EPOCH=$(date +%s 2>/dev/null || echo 0)
STALE_THRESHOLD_SECONDS=$(( STALE_HOURS * 3600 ))

# ---------------------------------------------------------------------------
# Scan outbox directory.
# ---------------------------------------------------------------------------
for f in "${OUTBOX_DIR}"/*.md; do
  [[ -f "$f" ]] || continue

  mtime=$(get_mtime "$f")
  if [[ "$mtime" -eq 0 || "$NOW_EPOCH" -eq 0 ]]; then
    continue
  fi

  age_seconds=$(( NOW_EPOCH - mtime ))
  if [[ "$age_seconds" -lt "$STALE_THRESHOLD_SECONDS" ]]; then
    # Draft is fresh — skip silently.
    continue
  fi

  age_hours=$(( age_seconds / 3600 ))

  # Derive topic from filename (strip directory and .md extension).
  topic="${f##*/}"
  topic="${topic%.md}"

  # Parse to: and title: from frontmatter using grep.
  # Simple YAML quoted strings: grep -E '^to:|^title:' then strip key and quotes.
  # NO grep -P (not cross-platform).
  to_raw=$(grep -E '^to:' "$f" 2>/dev/null | head -1 | sed 's/^to:[[:space:]]*//' | tr -d '"'"'" | xargs || true)
  title_raw=$(grep -E '^title:' "$f" 2>/dev/null | head -1 | sed 's/^title:[[:space:]]*//' | tr -d '"'"'" | xargs || true)

  to_val="${to_raw:-unknown}"
  title_val="${title_raw:-untitled}"

  # Emit the nudge line (offer-shape only — no mutation).
  printf 'Outbox draft %s staged %sh ago → %s  :: %s\n' \
    "$topic" "$age_hours" "$to_val" "$title_val"
  printf '  → send | compose | discard\n'
done

exit 0
