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
# Output: writes state/review-trail/.weekly-reviewer-scopes.json with shape:
#   { "patrik": [sha...], "patrik_seam_files": [path...], "mechanical_workers": "full" }
#
# MUST be executed as a subprocess, never sourced. Fail-loud on any error.
#
# Env:
#   HEADER_FILE — path to state/week-changelog/HEADER.md (required)
#
# Spec backlink: coordinator/commands/workweek-complete.md § Step 7 prelude
# C2 extraction backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2

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

TODAY=$(date -u +%Y-%m-%d)
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
[[ ! -f "$_WWTS_LIB" ]] && _WWTS_LIB="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
if [[ -f "$_WWTS_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_WWTS_LIB"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "ERROR: no Python interpreter found (python3/python/py) — required for workweek scope computation" >&2
  exit 1
fi

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
bash "$COVERAGE_CORE" --segments-json > "$SEGMENTS_JSON_FILE"

# ---------------------------------------------------------------------------
# Step 2: seam detection (stays LOCAL — it is weekly-gate specific).
#
# Cross-segment seams are file paths touched by ≥2 distinct segments.
# A segment whose file-set intersects with the seam set contributes its
# reviewed commits to patrik_shas (they need another look in the context of
# the adjacent segment that touched the same file).
# ---------------------------------------------------------------------------
"$PYTHON_BIN" "${PYTHON_ARGS[@]}" - "$SEGMENTS_JSON_FILE" <<'PYEOF'  # verify-no-console-flash: allow (weekly-gate only; not session hot-path)
import json, subprocess, sys

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

scope_path = "state/review-trail/.weekly-reviewer-scopes.json"
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

print(f"Scope written: {len(patrik_shas)} patrik SHA(s), {len(seam_files)} seam file(s) → {scope_path}")
PYEOF
