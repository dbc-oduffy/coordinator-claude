#!/usr/bin/env bash
# workweek-trail-scope.sh — Step 7 prelude for /workweek-complete.
#
# Reads the workstream-complete review trail records for the current week and
# computes the narrowed scope for the Staff Engineer reviewer:
#
#   patrik_scope = unreviewed_week_SHAs ∪ cross-segment-seam SHAs
#
# A "segment" is the sha_range of one trail record (one workstream-complete review).
# Cross-segment seams are file paths touched by ≥2 distinct segments —
# computed by intersecting the files-touched sets pairwise.
#
# Output: writes a session-keyed shard
#   state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
# with shape:
#   { "patrik": [sha...], "patrik_seam_files": [path...], "mechanical_workers": "full" }
#
# Session-keyed append-only (not a singleton overwrite): two concurrent
# /workweek-complete weekly gates each write their own shard rather than
# clobbering a shared filename. Consumers select the most-recent shard for
# their own session (falling back to the newest shard overall) — see
# coordinator/commands/workweek-complete.md § Step 7 read logic.
#
# MUST be executed as a subprocess, never sourced. Fail-loud on any error.
#
# Env:
#   HEADER_FILE — path to state/week-changelog/HEADER.md (required)
#
# Spec backlink: coordinator/commands/workweek-complete.md § Step 7 prelude
# C2 extraction backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2
# Singleton→session-keyed-shard backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2 (concurrency fix)

set -euo pipefail

HEADER_FILE="${HEADER_FILE:-state/week-changelog/HEADER.md}"

if [[ ! -f "$HEADER_FILE" ]]; then
  echo "ERROR: $HEADER_FILE not found — run /workweek-start to initialise." >&2
  exit 1
fi

WEEK_START=$(grep -E '^\*\*Week starting:\*\*' "$HEADER_FILE" | \
  sed -E 's/^\*\*Week starting:\*\* +([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/' | head -1)

if [[ -z "$WEEK_START" || ! "$WEEK_START" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: cannot parse 'Week starting:' YYYY-MM-DD from $HEADER_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/coordinator-daily-day.sh"
TODAY=$(coordinator_local_day)
export WEEK_START TODAY

TRAIL_FILES=$(find state/review-trail -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)
export TRAIL_FILES

# ---------------------------------------------------------------------------
# Temp dir for inter-step communication; cleaned up on exit.
# ---------------------------------------------------------------------------
_WWTS_TMPDIR=$(mktemp -d)
trap 'rm -rf "$_WWTS_TMPDIR"' EXIT

# ---------------------------------------------------------------------------
# Resolve the shared coverage core path (co-located in the same lib/ dir).
# ---------------------------------------------------------------------------
_WWTS_SELFDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COVERAGE_CORE="${_WWTS_SELFDIR}/review-coverage-core.sh"
if [[ ! -x "$COVERAGE_CORE" ]]; then
  echo "ERROR: shared coverage core not found or not executable: $COVERAGE_CORE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve Python interpreter — still needed for the seam-detection block,
# which remains local to this script.
# ---------------------------------------------------------------------------
PYTHON_ARGS=()
_WWTS_LIB="${_WWTS_SELFDIR}/resolve-python.sh"
if [[ ! -f "$_WWTS_LIB" ]]; then
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
  _WWTS_LIB="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
  coordinator_trusted_root_guard --mode=fail-loud --root="$_WWTS_LIB" --site="$0"
fi
if [[ -f "$_WWTS_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_WWTS_LIB"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "ERROR: no Python interpreter found (python3/python/py) — required for workweek scope computation" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Session-id + nanosecond-stamp resolution for the session-keyed shard write.
#
# Two concurrent /workweek-complete weekly gates previously clobbered each
# other's computed reviewer scopes via a singleton overwrite of
# .weekly-reviewer-scopes.json. Mirrors the exact scheme at
# coordinator-write-review-trail.sh:335-348 (nanosecond stamp with %N-probe
# fallback + 8-char session-id shard suffix) so both writers share one
# collision-avoidance contract.
#
# C2 backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2
# ---------------------------------------------------------------------------
_WWTS_SESSION_LIB="${_WWTS_SELFDIR}/coordinator-session.sh"
if [[ -f "$_WWTS_SESSION_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_WWTS_SESSION_LIB"
fi

WWTS_SESSION_ID=""
if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
  WWTS_SESSION_ID="$CLAUDE_SESSION_ID"
elif [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
  WWTS_SESSION_ID="$CLAUDE_CODE_SESSION_ID"
elif declare -F cs_resolve_session_id >/dev/null 2>&1; then
  WWTS_SESSION_ID=$(cs_resolve_session_id)
fi

if [[ -z "$WWTS_SESSION_ID" ]]; then
  echo "ERROR: Could not resolve session-id for scope shard write. Attempted:" >&2
  echo "  1. CLAUDE_SESSION_ID env var — not set or empty" >&2
  echo "  2. CLAUDE_CODE_SESSION_ID env var — not set or empty" >&2
  echo "  3. cs_resolve_session_id sentinel fallback — not found, empty, or ambiguous under concurrency" >&2
  echo "  Fix: export CLAUDE_SESSION_ID=<harness-id>   (run from inside the Claude Code session)" >&2
  exit 1
fi
WWTS_SESSION_ID_SHORT="${WWTS_SESSION_ID:0:8}"

# Nanosecond-precision stamp with %N-not-supported platform fallback —
# identical probe to coordinator-write-review-trail.sh:335-345.
_WWTS_TS_RAW=$(date -u +%Y-%m-%d-%H%M%S%N 2>/dev/null || true)
if [[ "$_WWTS_TS_RAW" == *%N* ]] || [[ ${#_WWTS_TS_RAW} -lt 20 ]]; then
  # %N not supported on this platform (returned literal or empty).
  # Second-precision fallback: two invocations within one second (same
  # session or, at birthday-paradox scale, same SID_SHORT truncation)
  # would otherwise collide on the shard filename. Append a per-process
  # PID disambiguator so same-second writes land in DISTINCT files —
  # consistent with the reader's most-recent-for-session semantics and
  # this workstream's "both survive" philosophy, and symmetric with the
  # O_CREAT|O_EXCL retry-with-suffix guards on the two Python CLIs this
  # shard scheme sits beside.
  # Review: code-reviewer — F2: plain open(scope_path, "w") on this
  # fallback branch had no collision guard, unlike the two CLIs; a
  # same-second same-SID_SHORT race silently clobbered one write.
  WWTS_TIMESTAMP="$(date -u +%Y-%m-%d-%H%M%S)-pid$$"
else
  WWTS_TIMESTAMP="${_WWTS_TS_RAW:0:23}"
fi
export WWTS_SESSION_ID_SHORT WWTS_TIMESTAMP

# ---------------------------------------------------------------------------
# Step 1: get per-segment data (sha_range + shas + files) via the shared core.
#
# The shared core applies:
#   - verdict filter: pending → excluded (fixes the latent weekly-gate gap
#     where pending records previously counted as reviewed; now BOTH this gate
#     and the chain-end gate inherit the same semantics from one place)
#   - SAFE_RANGE validator: argument-injection defence
#   - JSON-OR-JSONL dual-shape parse
#
# --segments-json mode emits per-segment {sha_range, shas, files} records so
# the local seam-detection block can do pairwise file-set intersection.
# ---------------------------------------------------------------------------
SEGMENTS_JSON_FILE="${_WWTS_TMPDIR}/segments.json"
# Cross-machine SHAs in trail records are unreachable locally on multi-machine weeks;
# --on-unresolvable-ref skip drops them from the segment set with a warning (fail-safe:
# they appear as unreviewed → more review, never less). Parse failures remain fail-loud
# (default --on-record-error fail) per b3g-077 detect-then-fail-loud doctrine.
bash "$COVERAGE_CORE" --segments-json --on-unresolvable-ref skip > "$SEGMENTS_JSON_FILE"

# ---------------------------------------------------------------------------
# Step 2: seam detection (stays LOCAL — it is weekly-gate specific).
#
# Cross-segment seams are file paths touched by ≥2 distinct segments.
# A segment whose file-set intersects with the seam set contributes its
# reviewed commits to patrik_shas (they need another look in the context of
# the adjacent segment that touched the same file).
# ---------------------------------------------------------------------------
"$PYTHON_BIN" "${PYTHON_ARGS[@]}" - "$SEGMENTS_JSON_FILE" <<'PYEOF'  # verify-no-console-flash: allow (weekly-gate only; not session hot-path)
import json, os, subprocess, sys

segments_json_file = sys.argv[1]

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        print(f"ERROR: command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

with open(segments_json_file) as fh:
    segments = json.load(fh)

segment_shas  = [set(seg["shas"])  for seg in segments]
segment_files = [set(seg["files"]) for seg in segments]

reviewed_set = set().union(*segment_shas) if segment_shas else set()

weekly_raw       = run(["git", "log", "origin/main..HEAD", "--format=%H"])
weekly_diff_shas = set(weekly_raw.splitlines()) if weekly_raw else set()
unreviewed_set   = weekly_diff_shas - reviewed_set

cross_segment_seams = set()
for i in range(len(segment_files)):
    for j in range(i + 1, len(segment_files)):
        cross_segment_seams |= segment_files[i] & segment_files[j]

seam_shas = set()
for k, fset in enumerate(segment_files):
    if fset & cross_segment_seams:
        seam_shas |= segment_shas[k]

patrik_shas = sorted(unreviewed_set | seam_shas)
seam_files  = sorted(cross_segment_seams)

timestamp    = os.environ["WWTS_TIMESTAMP"]
session_short = os.environ["WWTS_SESSION_ID_SHORT"]
scope_path = f"state/review-trail/.weekly-reviewer-scopes-{timestamp}-{session_short}.json"
scope_obj  = {
    "patrik":            patrik_shas,
    "patrik_seam_files": seam_files,
    "mechanical_workers": "full"
}
try:
    with open(scope_path, "w") as fh:
        json.dump(scope_obj, fh, indent=2)
except Exception as e:
    print(f"ERROR: could not write {scope_path}: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Scope written: {len(patrik_shas)} the Staff Engineer SHA(s), {len(seam_files)} seam file(s) → {scope_path}")
PYEOF
