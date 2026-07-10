#!/usr/bin/env bash
# coordinator-write-review-trail.sh — DR-216 facade router: review_trail.write (strang-10).
#
# Purpose: routes review_trail.write through the example-orchestration-hub native op (native-primary)
# with the original script body preserved as legacy_review_trail_write()
# (disk-absence fallback). Three-state routing model (Design pin 3):
#   State 1 (seam absent on disk) -> legacy_review_trail_write (current bash body, byte-identical).
#   State 2 (seam present + cc_invoke exits 0) -> native op ran; legacy NOT run.
#   State 3 (seam present + cc_invoke fails) -> propagate exit 2 (fail-closed); legacy NOT run.
#
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md (strang-10 C5)
#
# Usage (unchanged from pre-facade — zero caller repoints, DR-210):
#   coordinator-write-review-trail.sh \
#     --sha-range A..B \
#     --reviewer code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile|wsc-auto-adjudication \
#     --scope chain|session|workstream-close-auto \
#     --verdict ok|warn|blocked|waived|pending \
#     --diff-loc <integer> \
#     [--scope-kind diff|plan|integration]
#
# Exit codes (unchanged):
#   0 — success (review trail record written, or native op succeeded)
#   1 — hard precondition failed or validation failed (legacy path)
#   2 — native op: post-spawn transport failure (State 3, native path only)
#   3 — unresolvable session-id (legacy path)
set -euo pipefail

# ---------------------------------------------------------------------------
# DR-216 facade router -- source shared helper (must precede legacy_review_trail_write).
# Cold-fallback self-location note: legacy_review_trail_write resolves its DoE
# root via BASH_SOURCE[0]-relative paths (see _CSR_LIB_DIR inside the function),
# NEVER via `machine-local get` as a CLI.
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# legacy_review_trail_write -- the pre-facade script body, preserved verbatim.
# Called ONLY on State 1 (coordinator_core.invoke absent on disk).
# BASH_SOURCE[0]-relative self-location inside the function is unchanged and
# safe (resolves to this script path, same as before the body-swap).
# ---------------------------------------------------------------------------
legacy_review_trail_write() {
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
#     --reviewer code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile|wsc-auto-adjudication \
#     --scope chain|session|workstream-close-auto \
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
# wsc-auto-adjudication (reviewer) / workstream-close-auto (scope): machine-provenance
# sentinels for the /workstream-complete default auto-source path — see example-orchestration-hub
# coordinator_core/ops/review_trail_write.py _build_effective_review_trail (DR-216 parity).
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

# Source the state-root seam — must precede coordinator_state_root calls (C4 per-repo repoint)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"
# shellcheck source=lib/coordinator-session.sh
source "${_CSR_LIB_DIR}/coordinator-session.sh"

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
      echo "Usage: coordinator-write-review-trail.sh --sha-range A..B --reviewer code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile|wsc-auto-adjudication --scope chain|session|workstream-close-auto --verdict ok|warn|blocked|waived|pending --diff-loc <integer> [--scope-kind diff|plan|integration]" >&2
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
  echo "ERROR: --reviewer is required; allowed: code-reviewer | the Staff Engineer | code-reviewer+the Staff Engineer | waived | ubt-compile | wsc-auto-adjudication" >&2
  exit 1
fi

if [[ -z "$SCOPE" ]]; then
  echo "ERROR: --scope is required; allowed: chain | session | workstream-close-auto" >&2
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
  code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile|wsc-auto-adjudication) ;;
  *)
    echo "ERROR: --reviewer value '${REVIEWER}' is invalid; allowed: code-reviewer | the Staff Engineer | code-reviewer+the Staff Engineer | waived | ubt-compile | wsc-auto-adjudication" >&2
    exit 1
    ;;
esac

case "$SCOPE" in
  chain|session|workstream-close-auto) ;;
  *)
    echo "ERROR: --scope value '${SCOPE}' is invalid; allowed: chain | session | workstream-close-auto" >&2
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
  # Sentinel fallback — routed through cs_resolve_session_id for ambiguity-aware
  # fail-empty under concurrency (tier-4 guard; C3b per
  # docs/plans/2026-07-06-racy-sentinel-tier4-fail-empty.md).
  # Returns empty when ≥2 sessions are live (wrong-attribution prevented); the
  # existing exit-3 guard below then fires as the fail-loud path.
  SESSION_ID=$(cs_resolve_session_id)
fi

if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: Could not resolve session-id. Attempted:" >&2
  echo "  1. CLAUDE_SESSION_ID env var — not set or empty" >&2
  echo "  2. CLAUDE_CODE_SESSION_ID env var — not set or empty" >&2
  # Review: code-reviewer — B-F4: REPO_ROOT never set in this script (real var is
  # REPO_ROOT_FOR_WRITE, assigned later at line ~225); ${REPO_ROOT:-...} silently
  # degraded to "<git-root-unavailable>". Fixed by deriving root via git at the error site.
  SENTINEL_PATH="$(git rev-parse --show-toplevel 2>/dev/null || echo "<git-root-unavailable>")/.git/coordinator-sessions/.current-session-id"
  # Review: code-reviewer — B-F3: "not found or empty" implies file-absence; the most
  # common post-C3b cause is sentinel found-but-ambiguous under concurrency. Folded the
  # concurrency explanation into the step-3 line rather than a separated trailing line.
  echo "  3. Sentinel file: ${SENTINEL_PATH} — not found, empty, or ambiguous (returned empty under ≥2 live sessions — see cs_resolve_session_id)" >&2
  echo "  Fix: export CLAUDE_SESSION_ID=<harness-id>   (run from inside the Claude Code session)" >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Compute target path
# ---------------------------------------------------------------------------

# Resolve the state root for writing into state/review-trail/ via the per-repo seam (C4).
# coordinator_state_root (no flag) returns $EXAMPLE_ORCHESTRATION_HUB_ROOT/state for the meta-repo,
# or $GIT_ROOT/state for sibling repos.
REPO_ROOT_FOR_WRITE=""
if ! REPO_ROOT_FOR_WRITE=$(coordinator_state_root 2>/dev/null); then
  echo "ERROR: Cannot resolve per-repo state root via coordinator_state_root; cannot write state/review-trail/" >&2
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
  _HANDOFFS_DIR="${REPO_ROOT_FOR_WRITE}/handoffs"
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
TRAIL_DIR="${REPO_ROOT_FOR_WRITE}/review-trail"
TARGET_FILE="${TRAIL_DIR}/${TIMESTAMP}-${SESSION_ID_SHORT}.json"

# Ensure the trail directory exists (created by .gitkeep but may not exist in fresh clones)
mkdir -p "$TRAIL_DIR"

# ---------------------------------------------------------------------------
# Normalize symbolic-ref endpoints in '..' ranges to concrete shas.
#
# A caller passing X..HEAD persists the literal "HEAD" token; a backfilled or
# late-read record then appears to span into a later day (example-orchestration-hub Finding 5).
# Fix at this single writer chokepoint — every caller benefits without touching
# each call site.
#
# CONSTRAINT: bare sha_range values without '..' (e.g. "HEAD" stored by
# plan/integration scope_kind records) are CONVENTIONAL PLACEHOLDERS and MUST
# be left untouched.  Only '..' form is normalized.
# See docs/wiki/workstream-complete-review.md § A..B footgun — this changes
# endpoint VALUES, NOT the A..B FORMAT; the format must not change.
#
# Resolution uses git -C "${REPO_ROOT_FOR_WRITE}" (writer's established repo
# context), never a bare git rev-parse, because the writer runs from an
# arbitrary cwd.
# ---------------------------------------------------------------------------
if [[ "$SHA_RANGE" == *..* ]]; then
  _SR_LEFT="${SHA_RANGE%%..*}"     # everything left of the first .. (pattern: two literal dots + any)
  _SR_RIGHT="${SHA_RANGE#*..}"     # everything right of the first .. (pattern: any + two literal dots)
  # Resolve endpoint only when it is NOT already a concrete sha.
  # Concrete shas consist solely of hex characters [0-9a-fA-F].
  # Symbolic refs (HEAD, branch names, etc.) always contain at least one
  # non-hex character, so the pattern correctly distinguishes the two cases.
  local _resolved
  if ! [[ "$_SR_LEFT" =~ ^[0-9a-fA-F]+$ ]]; then
    if _resolved=$(git -C "${REPO_ROOT_FOR_WRITE}" rev-parse "$_SR_LEFT" 2>/dev/null); then
      _SR_LEFT="$_resolved"
    else
      echo "WARN: sha_range left endpoint '${_SR_LEFT}' could not be resolved via git rev-parse; persisting symbolic ref unchanged" >&2
    fi
  fi
  if ! [[ "$_SR_RIGHT" =~ ^[0-9a-fA-F]+$ ]]; then
    if _resolved=$(git -C "${REPO_ROOT_FOR_WRITE}" rev-parse "$_SR_RIGHT" 2>/dev/null); then
      _SR_RIGHT="$_resolved"
    else
      echo "WARN: sha_range right endpoint '${_SR_RIGHT}' could not be resolved via git rev-parse; persisting symbolic ref unchanged" >&2
    fi
  fi
  SHA_RANGE="${_SR_LEFT}..${_SR_RIGHT}"
fi

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
}

# ---------------------------------------------------------------------------
# Build review_trail.write params JSON from CLI args.
# Maps --sha-range, --reviewer, --scope, --verdict, --diff-loc, --scope-kind
# and COORDINATOR_REVIEW_WORKSTREAM env to the review_trail.write op params
# (coordinator_core/ops/review_trail_write.py: sha_range, reviewer, scope,
# verdict, diff_loc, scope_kind, workstream).
# diff_loc passed as string; the op accepts str and casts to int (DR-216 D3).
# session_id resolved by the native daemon from env — not a param.
# workstream: COORDINATOR_REVIEW_WORKSTREAM env var if set, else null (let op resolve).
# native path only — on State-1 (legacy), strangle_route forwards "$@" to
# legacy_review_trail_write, which re-parses "$@" with its own identical loop.
# ---------------------------------------------------------------------------
_RT_SHA_RANGE=""
_RT_REVIEWER=""
_RT_SCOPE=""
_RT_VERDICT=""
_RT_DIFF_LOC=""
_RT_SCOPE_KIND="diff"
_rt_args=("$@")
for (( _rti=0; _rti<${#_rt_args[@]}; _rti++ )); do
  case "${_rt_args[_rti]}" in
    --sha-range)   _RT_SHA_RANGE="${_rt_args[$((_rti+1))]:-}";  _rti=$((_rti+1)) ;;
    --reviewer)    _RT_REVIEWER="${_rt_args[$((_rti+1))]:-}";   _rti=$((_rti+1)) ;;
    --scope)       _RT_SCOPE="${_rt_args[$((_rti+1))]:-}";      _rti=$((_rti+1)) ;;
    --verdict)     _RT_VERDICT="${_rt_args[$((_rti+1))]:-}";    _rti=$((_rti+1)) ;;
    --diff-loc)    _RT_DIFF_LOC="${_rt_args[$((_rti+1))]:-}";   _rti=$((_rti+1)) ;;
    --scope-kind)  _RT_SCOPE_KIND="${_rt_args[$((_rti+1))]:-}"; _rti=$((_rti+1)) ;;
  esac
done

# Required-arg presence gate: exit 1 on any missing required arg, matching the
# legacy exit-1 contract. Enum validation is delegated to the op (native path)
# or to legacy_review_trail_write (State-1); this gate only catches absent args.
# Review: code-reviewer — F1: facade gate ensures exit 1 (not 2) for missing required args.
_rt_missing=()
[[ -z "$_RT_SHA_RANGE" ]] && _rt_missing+=("--sha-range")
[[ -z "$_RT_REVIEWER"  ]] && _rt_missing+=("--reviewer")
[[ -z "$_RT_SCOPE"     ]] && _rt_missing+=("--scope")
[[ -z "$_RT_VERDICT"   ]] && _rt_missing+=("--verdict")
if [[ ${#_rt_missing[@]} -gt 0 ]]; then
  printf 'coordinator-write-review-trail: missing required args: %s\n' \
    "${_rt_missing[*]}" >&2
  exit 1
fi

_RT_WORKSTREAM="${COORDINATOR_REVIEW_WORKSTREAM:-}"

_RT_PARAMS="$(jq -cn \
  --arg sha_range  "$_RT_SHA_RANGE" \
  --arg reviewer   "$_RT_REVIEWER" \
  --arg scope      "$_RT_SCOPE" \
  --arg verdict    "$_RT_VERDICT" \
  --arg diff_loc   "$_RT_DIFF_LOC" \
  --arg scope_kind "$_RT_SCOPE_KIND" \
  --arg workstream "$_RT_WORKSTREAM" \
  '{
    sha_range:  $sha_range,
    reviewer:   $reviewer,
    scope:      $scope,
    verdict:    $verdict,
    diff_loc:   $diff_loc,
    scope_kind: $scope_kind,
    workstream: (if $workstream == "" then null else $workstream end)
  }')"

# ---------------------------------------------------------------------------
# Three-state facade dispatch.
# strangle_route decides: seam-absent -> legacy_review_trail_write "$@";
#                         seam-present -> python3 -m coordinator_core.invoke review_trail.write.  # popup-safe-env-suppressed
# "$@" forwarded verbatim so legacy_review_trail_write receives original CLI args unchanged.
# ---------------------------------------------------------------------------
strangle_route "review_trail.write" "legacy_review_trail_write" "$_RT_PARAMS" "$@"
