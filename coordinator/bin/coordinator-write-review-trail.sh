#!/usr/bin/env bash
# coordinator-write-review-trail.sh — Write a per-session review-trail record
#
# Purpose: records a code-review marker after /workstream-complete or /handoff review
# completion, enabling /workday-complete Step 9 and /workweek-complete Step 7
# to shed redundant review load by reading what has already been reviewed.
#
# Spec backlink: docs/plans/2026-05-08-session-end-review-and-marker-trail.md § T2
#
# Usage:
#   coordinator-write-review-trail.sh \
#     --sha-range A..B \
#     --reviewer code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile \
#     --scope chain|session \
#     --verdict ok|warn|blocked|waived|pending \
#     --diff-loc <integer> \
#     [--scope-kind diff|plan|integration]
#
# --scope-kind (optional, default: diff):
#   diff        — this record covers a real code diff; included in weekly diff-scope accounting.
#   plan        — plan-review or integration pass with no code sha_range; skipped silently by
#                 workweek-trail-scope.sh without a WARN (legitimately non-diff record).
#   integration — same as plan; use when the reviewer pass was a review-integrator run.
#
# Negative-spec: do NOT repurpose or remove the existing --scope field (chain|session);
# --scope-kind is orthogonal and carries a different classification dimension.
#
# Automated-check reviewer names are mechanism-named (e.g. ubt-compile, not automated-check)
# so future automated verdicts (clippy, eslint, pytest-coverage) each add one unambiguous entry.
# ubt-compile: automated build verdict produced by bin/check-ubt-build-fresh.sh
#
# Session-id resolution (strict precedence):
#   1. CLAUDE_SESSION_ID env var (explicit override; if set and non-empty)
#   2. CLAUDE_CODE_SESSION_ID env var (platform-injected, Claude Code ≥ ~2.1.150)
#   3. Sentinel file: $(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id
#   4. If neither resolves → exit 3 with a clear error naming both sources attempted.
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
# (c) record shape is closed and small (7 fields) — markdown's flexibility provides no benefit.
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
SCOPE_KIND="diff"  # optional; default: diff

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
    --scope-kind)
      SCOPE_KIND="${2:-}"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      echo "Usage: coordinator-write-review-trail.sh --sha-range A..B --reviewer code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile --scope chain|session --verdict ok|warn|blocked|waived|pending --diff-loc <integer> [--scope-kind diff|plan|integration]" >&2
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
  echo "ERROR: --reviewer is required; allowed: code-reviewer | patrik | code-reviewer+patrik | waived | ubt-compile" >&2
  exit 1
fi

if [[ -z "$SCOPE" ]]; then
  echo "ERROR: --scope is required; allowed: chain | session" >&2
  exit 1
fi

if [[ -z "$VERDICT" ]]; then
  echo "ERROR: --verdict is required; allowed: ok | warn | blocked | waived | pending" >&2
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
  code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile) ;;
  *)
    echo "ERROR: --reviewer value '${REVIEWER}' is invalid; allowed: code-reviewer | patrik | code-reviewer+patrik | waived | ubt-compile" >&2
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
  ok|warn|blocked|waived|pending) ;;
  *)
    echo "ERROR: --verdict value '${VERDICT}' is invalid; allowed: ok | warn | blocked | waived | pending" >&2
    exit 1
    ;;
esac

if ! [[ "$DIFF_LOC" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --diff-loc value '${DIFF_LOC}' is not a non-negative integer" >&2
  exit 1
fi

case "$SCOPE_KIND" in
  diff|plan|integration) ;;
  *)
    echo "ERROR: --scope-kind value '${SCOPE_KIND}' is invalid; allowed: diff | plan | integration" >&2
    exit 1
    ;;
esac

# Review: focused-review — close writer/consumer validation asymmetry: the consumer
# (workweek-trail-scope.sh) always drops diff records without a ".." range; the writer
# must reject them at write-time rather than silently accepting invalid records.
# plan/integration scope_kind records do not consume sha_range, so no constraint there.
if [[ "$SCOPE_KIND" == "diff" ]] && [[ "$SHA_RANGE" != *..* ]]; then
  echo "ERROR: --scope-kind diff requires --sha-range to contain '..', got: '${SHA_RANGE}'" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Session-id resolution (strict precedence)
# ---------------------------------------------------------------------------

SESSION_ID=""

if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
  SESSION_ID="$CLAUDE_SESSION_ID"
elif [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
  # Platform-injected session id (Claude Code ≥ ~2.1.150). Per-session and
  # unclobberable by sibling sessions — beats the last-writer-wins sentinel.
  SESSION_ID="$CLAUDE_CODE_SESSION_ID"
else
  # Sentinel fallback (last-writer-wins; only reached on old Claude Code)
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
  echo "  2. CLAUDE_CODE_SESSION_ID env var — not set or empty" >&2
  SENTINEL_PATH="${REPO_ROOT:-<git-root-unavailable>}/.git/coordinator-sessions/.current-session-id"
  echo "  3. Sentinel file: ${SENTINEL_PATH} — not found or empty" >&2
  echo "Set CLAUDE_SESSION_ID or create the sentinel file before invoking this helper." >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Compute target path
# ---------------------------------------------------------------------------

# Resolve the repo root for writing into state/review-trail/
# Use the working directory from which we're invoked (git repo context)
REPO_ROOT_FOR_WRITE=""
if ! REPO_ROOT_FOR_WRITE=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "ERROR: Not inside a git repository; cannot resolve state/review-trail/ path" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Workstream resolution (tolerant/nullable — D9: present-as-null discipline)
#
# Resolution order:
#   1. COORDINATOR_REVIEW_WORKSTREAM env var (explicit caller override)
#   2. Scan state/handoffs/*.md for the first active handoff's `workstream:` field
#      (active = status not consumed or superseded)
#   3. Null — no active workstream resolvable
#
# Negative-spec: do NOT invent a new resolution mechanism. Do NOT emit an empty
# string — JSON null is the D9-compliant form for "not resolvable".
# ---------------------------------------------------------------------------

WORKSTREAM_SLUG=""
WORKSTREAM_JSON="null"

if [[ -n "${COORDINATOR_REVIEW_WORKSTREAM:-}" ]]; then
  WORKSTREAM_SLUG="$COORDINATOR_REVIEW_WORKSTREAM"
else
  # Scan state/handoffs/ in the repo for the first active handoff's workstream field.
  # "Active" means status is not consumed or superseded (matches the pattern used
  # in assert-no-terminal-plans-in-live.sh and whats-next.sh).
  _HANDOFFS_DIR="${REPO_ROOT_FOR_WRITE}/state/handoffs"
  if [[ -d "$_HANDOFFS_DIR" ]]; then
    while IFS= read -r _hfile; do
      [[ -f "$_hfile" ]] || continue
      _hstatus=$(awk '/^---/{f++} f==1 && /^status:/{print $2; exit}' "$_hfile" 2>/dev/null || true)
      [[ "$_hstatus" == "consumed" || "$_hstatus" == "superseded" ]] && continue
      # Extract workstream: field from the frontmatter block
      _ws=$(awk '/^---/{f++} f==1 && /^workstream:/{print $2; exit}' "$_hfile" 2>/dev/null || true)
      if [[ -n "$_ws" ]]; then
        WORKSTREAM_SLUG="$_ws"
        break
      fi
    done < <(find "$_HANDOFFS_DIR" -maxdepth 1 -name '*.md' -print 2>/dev/null | sort || true)
  fi
fi

# Validate WORKSTREAM_SLUG: only [A-Za-z0-9_-] permitted.
# Slugs are kebab-case by construction; any other character indicates an injection
# risk or malformed source (e.g. a slug with '"' or '\' would corrupt the JSON record).
# Reject-to-null is the D9 tolerant-null path — cleaner than escaping, consistent
# with the null-fallback discipline used throughout this helper.
if [[ -n "$WORKSTREAM_SLUG" ]] && [[ "$WORKSTREAM_SLUG" =~ [^A-Za-z0-9_-] ]]; then
  echo "WARN: workstream slug contains invalid characters (only [A-Za-z0-9_-] permitted); emitting null" >&2
  WORKSTREAM_SLUG=""
fi

if [[ -n "$WORKSTREAM_SLUG" ]]; then
  WORKSTREAM_JSON="\"${WORKSTREAM_SLUG}\""
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
  # Truncate to 23 chars: YYYY-MM-DD-HHMMSS + 6 nanosecond digits (stable length).
  TIMESTAMP="${_TS_RAW:0:23}"
fi
SESSION_ID_SHORT="${SESSION_ID:0:8}"
TRAIL_DIR="${REPO_ROOT_FOR_WRITE}/state/review-trail"
TARGET_FILE="${TRAIL_DIR}/${TIMESTAMP}-${SESSION_ID_SHORT}.json"

# Ensure the trail directory exists (created by .gitkeep but may not exist in fresh clones)
mkdir -p "$TRAIL_DIR"

# ---------------------------------------------------------------------------
# Compose JSON record
# ---------------------------------------------------------------------------

# NOTE: sha_range is consumed PER-COMMIT by lib/review-coverage-core.sh (via `git rev-list`);
# do NOT "fix" the recorded format to be endpoint-inclusive — per-commit consumption handles
# the A..B boundary correctly, and changing the format breaks workweek-trail-scope.sh +
# cockpit-tc-3 ReviewTrail reader. See docs/wiki/workstream-complete-review.md § A..B footgun.
JSON_RECORD="{\"sha_range\":\"${SHA_RANGE}\",\"reviewer\":\"${REVIEWER}\",\"scope\":\"${SCOPE}\",\"scope_kind\":\"${SCOPE_KIND}\",\"verdict\":\"${VERDICT}\",\"diff_loc\":${DIFF_LOC},\"session_id\":\"${SESSION_ID}\",\"workstream\":${WORKSTREAM_JSON}}"

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
