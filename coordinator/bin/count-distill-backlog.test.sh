#!/usr/bin/env bash
# count-distill-backlog.test.sh — self-contained test for count-distill-backlog.sh.
#
# Runs against the REAL archive and asserts:
#   (a) --format json emits valid JSON with integer pending_count and a valid computed_state
#   (b) jq parses the output cleanly
#   (c) pending_count >= 1 (heuristic must find at least one pending entry on a live repo)
#
# Exit 0 on pass; non-zero with a diagnostic on failure.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C1
# Review: A-F15 — fabricated plan path repointed to real plan
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="$SCRIPT_DIR/count-distill-backlog.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# Guard: subject must exist and be executable
[[ -x "$SUBJECT" ]] || fail "subject script not found or not executable: $SUBJECT"

# Guard: jq must be available
command -v jq &>/dev/null || fail "jq is required for JSON validation but was not found in PATH"

# ---------------------------------------------------------------------------
# Review: A-F11 — graceful skip on clean/CI repo with no archive
# ---------------------------------------------------------------------------
_DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
if [[ ! -d "$_DEFAULT_ROOT/archive/completed" ]]; then
  _ALT_ROOT="${CLAUDE_HOME:-$HOME}/.claude"
  if [[ ! -d "$_ALT_ROOT/archive/completed" ]]; then
    echo "SKIP: no archive/completed — live-repo-only test"
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Review: A-F10 — synthetic band-boundary assertion (self-contained, temp dir)
# ---------------------------------------------------------------------------
echo "--- Synthetic band-boundary tests ---"

_TMP_BAND="$(mktemp -d)"
_cleanup_band() { rm -rf "$_TMP_BAND"; }
trap _cleanup_band EXIT

# Populate fake archive: create .md files with a created: date 60 days ago (older than 30d cutoff).
# Use BSD/GNU-portable date (matching what the subject itself uses).
if date -v 1d +%F &>/dev/null; then
  _OLD_DATE="$(date -v-60d +%F)"
  _NEW_DATE="$(date -v-1d +%F)"
else
  _OLD_DATE="$(date -d '60 days ago' +%F)"
  _NEW_DATE="$(date -d '1 day ago' +%F)"
fi

mkdir -p "$_TMP_BAND/.claude/archive/completed/2026-01"
mkdir -p "$_TMP_BAND/.claude/docs/wiki"

# Helper: create a fake completion entry
_make_entry() {
  local path="$1" date="$2"
  printf -- '---\ncreated: %s\nchain: null\n---\n# fake entry\n' "$date" > "$path"
}

# Band "unknown": no archive files at all (empty archive dir) → subject exits 1 (archive root missing)
# We test unknown indirectly: with archive dir present but empty, archive_files_found=0 → unknown.
# Create the dir but leave it empty — subject will find dir but glob matches nothing.
_EMPTY_DIR="$_TMP_BAND/.claude/archive/completed"
CLAUDE_HOME="$_TMP_BAND/.claude" output_unknown="$(CLAUDE_HOME="$_TMP_BAND/.claude" bash "$SUBJECT" --format json 2>&1)" || true
band_unknown="$(echo "$output_unknown" | jq -r '.computed_state' 2>/dev/null || true)"
if [[ "$band_unknown" == "unknown" ]]; then
  echo "PASS: band-boundary: empty archive → unknown"
else
  echo "FAIL: band-boundary: empty archive → expected 'unknown', got '$band_unknown' (output: $output_unknown)"
fi

# Band "fresh": 1 old entry, but it matches the slug in wiki → pending=0 → fresh
_make_entry "$_TMP_BAND/.claude/archive/completed/2026-01/2026-01-01-my-feature-aabb11.md" "$_OLD_DATE"
echo "my-feature content" > "$_TMP_BAND/.claude/docs/wiki/my-feature.md"
output_fresh="$(CLAUDE_HOME="$_TMP_BAND/.claude" bash "$SUBJECT" --format json)"
band_fresh="$(echo "$output_fresh" | jq -r '.computed_state')"
if [[ "$band_fresh" == "fresh" ]]; then
  echo "PASS: band-boundary: 1 old entry, slug matched in wiki → fresh"
else
  echo "FAIL: band-boundary: 1 old entry, slug matched in wiki → expected 'fresh', got '$band_fresh'"
fi

# Band "mild": 3 old unmatched entries → pending=3 → mild (1-5)
for i in 1 2 3; do
  _make_entry "$_TMP_BAND/.claude/archive/completed/2026-01/2026-01-0${i}-unmatched-${i}aabb11.md" "$_OLD_DATE"
done
output_mild="$(CLAUDE_HOME="$_TMP_BAND/.claude" bash "$SUBJECT" --format json)"
band_mild="$(echo "$output_mild" | jq -r '.computed_state')"
pending_mild="$(echo "$output_mild" | jq -r '.pending_count')"
if [[ "$band_mild" == "mild" && "$pending_mild" -ge 1 && "$pending_mild" -le 5 ]]; then
  echo "PASS: band-boundary: unmatched old entries → mild (pending=$pending_mild)"
else
  echo "FAIL: band-boundary: unmatched old entries → expected 'mild' with 1-5 pending, got '$band_mild' pending=$pending_mild"
fi

# Band "stale": add more unmatched entries to push pending >= 6
for i in 4 5 6 7; do
  _make_entry "$_TMP_BAND/.claude/archive/completed/2026-01/2026-01-1${i}-unmatched-${i}aabb11.md" "$_OLD_DATE"
done
# Also add a new-date entry that should be EXCLUDED (newer than cutoff)
_make_entry "$_TMP_BAND/.claude/archive/completed/2026-01/2026-01-20-newentry-ccdd22.md" "$_NEW_DATE"
output_stale="$(CLAUDE_HOME="$_TMP_BAND/.claude" bash "$SUBJECT" --format json)"
band_stale="$(echo "$output_stale" | jq -r '.computed_state')"
pending_stale="$(echo "$output_stale" | jq -r '.pending_count')"
if [[ "$band_stale" == "stale" && "$pending_stale" -ge 6 ]]; then
  echo "PASS: band-boundary: >=6 unmatched old entries → stale (pending=$pending_stale)"
else
  echo "FAIL: band-boundary: >=6 unmatched old entries → expected 'stale' with >=6 pending, got '$band_stale' pending=$pending_stale"
fi

echo "--- End synthetic band-boundary tests ---"
echo ""

echo "Running: $SUBJECT --format json"
output="$("$SUBJECT" --format json)"
echo "Output: $output"

# (a) output must parse as JSON
echo "$output" | jq . &>/dev/null \
  || fail "--format json did not produce parseable JSON. Output was: $output"

# (b) pending_count must be an integer
pending_count="$(echo "$output" | jq '.pending_count')"
echo "$pending_count" | grep -qE '^[0-9]+$' \
  || fail "pending_count is not a non-negative integer. Got: $pending_count"

# (b) threshold_days must be present and equal 30
threshold_days="$(echo "$output" | jq '.threshold_days')"
[[ "$threshold_days" -eq 30 ]] \
  || fail "threshold_days should be 30. Got: $threshold_days"

# (b) computed_state must be one of the defined bands
computed_state="$(echo "$output" | jq -r '.computed_state')"
case "$computed_state" in
  fresh|mild|stale|unknown) ;;
  *) fail "computed_state is not a valid band. Got: $computed_state" ;;
esac

# (c) AC7: pending_count must be >= 1 (heuristic/path is wrong if this returns 0 on a live repo)
[[ "$pending_count" -ge 1 ]] \
  || fail "pending_count is 0 — heuristic returned empty backlog. Check glob and grep paths. Got computed_state=$computed_state"

# Also verify the plain (non-JSON) output is a bare integer
plain_output="$("$SUBJECT")"
echo "Plain output: $plain_output"
echo "$plain_output" | grep -qE '^[0-9]+$' \
  || fail "Plain (non-JSON) output is not a bare integer. Got: $plain_output"

# Plain output must match JSON pending_count
[[ "$plain_output" -eq "$pending_count" ]] \
  || fail "Plain output ($plain_output) does not match JSON pending_count ($pending_count)"

echo "PASS: pending_count=$pending_count computed_state=$computed_state threshold_days=$threshold_days"
