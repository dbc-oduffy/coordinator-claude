#!/bin/bash
# coordinator-write-review-trail.sh — Write a per-session review-trail record
#
# Purpose: records a code-review marker after /session-end or /handoff review
# completion, enabling /workday-complete Step 9 and /workweek-complete Step 7
# to shed redundant review load by reading what has already been reviewed.
#
# Spec backlink: docs/plans/2026-05-08-session-end-review-and-marker-trail.md § T2
#
# Usage:
#   coordinator-write-review-trail.sh \
#     --sha-range A..B \
#     --reviewer sonnet|patrik|sonnet+patrik|waived \
#     --scope chain|session \
#     --verdict ok|warn|blocked|waived \
#     --diff-loc <integer>
#
# Session-id resolution (strict precedence):
#   1. CLAUDE_SESSION_ID env var (if set and non-empty)
#   2. Sentinel file: $(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id
#   3. If neither resolves → exit 3 with a clear error naming both sources attempted.
#
# Idempotency contract:
#   - Target file absent            → write and exit 0
#   - Target file exists, byte-identical content → exit 0 (no-op)
#   - Target file exists, different content      → exit 2, error naming the path (never overwrite)
#
# Per docs/plans/2026-05-08-session-end-review-and-marker-trail.md § Considered Alternatives
# (Markdown over JSON for trail records — rejected). JSON chosen because:
# (a) /workweek-complete Step 7 prelude does set-subtraction over sha_range arrays — typed
#     structured format avoids parser fragility against bold-prefixed key:value markdown;
# (b) sole writer is this helper (no LLM authorship), so text-only-recovery and grep-tooling
#     concerns motivating markdown-canonical don't apply;
# (c) record shape is closed and small (6 fields) — markdown's flexibility provides no benefit.
# This deviation is intentional and greppable. Do not "fix" the format.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

SHA_RANGE=""
REVIEWER=""
SCOPE=""
VERDICT=""
DIFF_LOC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha-range)
      SHA_RANGE="${2:-}"
      shift 2
      ;;
    --reviewer)
      REVIEWER="${2:-}"
      shift 2
      ;;
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --verdict)
      VERDICT="${2:-}"
      shift 2
      ;;
    --diff-loc)
      DIFF_LOC="${2:-}"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      echo "Usage: coordinator-write-review-trail.sh --sha-range A..B --reviewer sonnet|patrik|sonnet+patrik|waived --scope chain|session --verdict ok|warn|blocked|waived --diff-loc <integer>" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Validation — required args
# ---------------------------------------------------------------------------

if [[ -z "$SHA_RANGE" ]]; then
  echo "ERROR: --sha-range is required (e.g. abc123..def456)" >&2
  exit 1
fi

if [[ -z "$REVIEWER" ]]; then
  echo "ERROR: --reviewer is required; allowed: sonnet | patrik | sonnet+patrik | waived" >&2
  exit 1
fi

if [[ -z "$SCOPE" ]]; then
  echo "ERROR: --scope is required; allowed: chain | session" >&2
  exit 1
fi

if [[ -z "$VERDICT" ]]; then
  echo "ERROR: --verdict is required; allowed: ok | warn | blocked | waived" >&2
  exit 1
fi

if [[ -z "$DIFF_LOC" ]]; then
  echo "ERROR: --diff-loc is required (integer LOC count)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Validation — enum values
# ---------------------------------------------------------------------------

case "$REVIEWER" in
  sonnet|patrik|sonnet+patrik|waived) ;;
  *)
    echo "ERROR: --reviewer value '${REVIEWER}' is invalid; allowed: sonnet | patrik | sonnet+patrik | waived" >&2
    exit 1
    ;;
esac

case "$SCOPE" in
  chain|session) ;;
  *)
    echo "ERROR: --scope value '${SCOPE}' is invalid; allowed: chain | session" >&2
    exit 1
    ;;
esac

case "$VERDICT" in
  ok|warn|blocked|waived) ;;
  *)
    echo "ERROR: --verdict value '${VERDICT}' is invalid; allowed: ok | warn | blocked | waived" >&2
    exit 1
    ;;
esac

if ! [[ "$DIFF_LOC" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --diff-loc value '${DIFF_LOC}' is not a non-negative integer" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Session-id resolution (strict precedence)
# ---------------------------------------------------------------------------

SESSION_ID=""

if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
  SESSION_ID="$CLAUDE_SESSION_ID"
else
  # Sentinel fallback
  REPO_ROOT=""
  if REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    SENTINEL="${REPO_ROOT}/.git/coordinator-sessions/.current-session-id"
    if [[ -f "$SENTINEL" ]]; then
      SESSION_ID=$(cat "$SENTINEL" | tr -d '[:space:]')
    fi
  fi
fi

if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: Could not resolve session-id. Attempted:" >&2
  echo "  1. CLAUDE_SESSION_ID env var — not set or empty" >&2
  SENTINEL_PATH="${REPO_ROOT:-<git-root-unavailable>}/.git/coordinator-sessions/.current-session-id"
  echo "  2. Sentinel file: ${SENTINEL_PATH} — not found or empty" >&2
  echo "Set CLAUDE_SESSION_ID or create the sentinel file before invoking this helper." >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Compute target path
# ---------------------------------------------------------------------------

# Resolve the repo root for writing into tasks/review-trail/
# Use the working directory from which we're invoked (git repo context)
REPO_ROOT_FOR_WRITE=""
if ! REPO_ROOT_FOR_WRITE=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "ERROR: Not inside a git repository; cannot resolve tasks/review-trail/ path" >&2
  exit 1
fi

# Review: the Staff Engineer — two reviews within the same second from the same session would
# collide and cause exit 2. Use nanosecond precision where the platform supports it
# (%N is a glibc/Linux extension; macOS date and Windows git-bash return literal %N).
# We probe for %N support and fall back to second-precision with a documented contract.
_TS_RAW=$(date -u +%Y-%m-%d-%H%M%S%N 2>/dev/null || true)
if [[ "$_TS_RAW" == *%N* ]] || [[ ${#_TS_RAW} -lt 20 ]]; then
  # %N not supported on this platform (returned literal or empty).
  # Second-precision contract: two invocations within one second from the same session
  # will exit 2 (collision). This is intentional fail-loud behaviour — callers must
  # not invoke this helper more than once per second per session.
  TIMESTAMP=$(date -u +%Y-%m-%d-%H%M%S)
else
  # Truncate to 22 chars: YYYY-MM-DD-HHMMSS + 6 nanosecond digits (stable length).
  TIMESTAMP="${_TS_RAW:0:22}"
fi
SESSION_ID_SHORT="${SESSION_ID:0:8}"
TRAIL_DIR="${REPO_ROOT_FOR_WRITE}/tasks/review-trail"
TARGET_FILE="${TRAIL_DIR}/${TIMESTAMP}-${SESSION_ID_SHORT}.json"

# Ensure the trail directory exists (created by .gitkeep but may not exist in fresh clones)
mkdir -p "$TRAIL_DIR"

# ---------------------------------------------------------------------------
# Compose JSON record
# ---------------------------------------------------------------------------

JSON_RECORD="{\"sha_range\":\"${SHA_RANGE}\",\"reviewer\":\"${REVIEWER}\",\"scope\":\"${SCOPE}\",\"verdict\":\"${VERDICT}\",\"diff_loc\":${DIFF_LOC},\"session_id\":\"${SESSION_ID}\"}"

# ---------------------------------------------------------------------------
# Idempotency check and write
# ---------------------------------------------------------------------------

if [[ -f "$TARGET_FILE" ]]; then
  EXISTING_CONTENT=$(cat "$TARGET_FILE")
  if [[ "$EXISTING_CONTENT" == "$JSON_RECORD" ]]; then
    # Byte-identical — no-op
    exit 0
  else
    echo "ERROR: Target file already exists with different content — refusing to overwrite." >&2
    echo "  Path: ${TARGET_FILE}" >&2
    echo "  Existing: ${EXISTING_CONTENT}" >&2
    echo "  Attempted: ${JSON_RECORD}" >&2
    exit 2
  fi
fi

# Write the record
printf '%s' "$JSON_RECORD" > "$TARGET_FILE"
echo "Review trail record written: ${TARGET_FILE}"
