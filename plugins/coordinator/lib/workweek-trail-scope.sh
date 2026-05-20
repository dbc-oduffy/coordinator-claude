#!/usr/bin/env bash
# workweek-trail-scope.sh — Step 7 prelude for /workweek-complete.
#
# Reads the session-end review trail records for the current week and
# computes the narrowed scope for the Staff Engineer reviewer:
#
#   patrik_scope = unreviewed_week_SHAs ∪ cross-segment-seam SHAs
#
# A "segment" is the sha_range of one trail record (one session-end review).
# Cross-segment seams are file paths touched by ≥2 distinct segments —
# computed by intersecting the files-touched sets pairwise.
#
# Output: writes tasks/review-trail/.weekly-reviewer-scopes.json with shape:
#   { "patrik": [sha...], "patrik_seam_files": [path...], "mechanical_workers": "full" }
#
# MUST be executed as a subprocess, never sourced. Fail-loud on any error.
#
# Env:
#   HEADER_FILE — path to tasks/week-changelog/HEADER.md (required)
#
# Spec backlink: coordinator/commands/workweek-complete.md § Step 7 prelude

set -euo pipefail

HEADER_FILE="${HEADER_FILE:-tasks/week-changelog/HEADER.md}"

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

TRAIL_FILES=$(find tasks/review-trail -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)
export TRAIL_FILES

python3 - <<'PYEOF'
import json, os, subprocess, sys

week_start = os.environ.get("WEEK_START", "")
today      = os.environ.get("TODAY", "")
trail_env  = os.environ.get("TRAIL_FILES", "")

if not week_start or not today:
    print("ERROR: WEEK_START and TODAY must be set before invoking this block", file=sys.stderr)
    sys.exit(1)

trail_files = [f.strip() for f in trail_env.split("\n") if f.strip() and f.strip().endswith(".json")]
week_records = []
for f in trail_files:
    basename = os.path.basename(f)
    date_prefix = basename[:10]
    if week_start <= date_prefix <= today:
        try:
            with open(f) as fh:
                rec = json.load(fh)
            week_records.append(rec)
        except Exception as e:
            print(f"ERROR: could not parse trail record {f}: {e}", file=sys.stderr)
            sys.exit(1)

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        print(f"ERROR: command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

segment_shas  = []
segment_files = []

for rec in week_records:
    sha_range = rec.get("sha_range", "")
    if not sha_range or ".." not in sha_range:
        print(f"ERROR: trail record has invalid sha_range: {sha_range!r}", file=sys.stderr)
        sys.exit(1)
    shas_out  = run(["git", "rev-list", sha_range])
    files_out = run(["git", "diff", "--name-only", sha_range])
    segment_shas.append(set(shas_out.splitlines()) if shas_out else set())
    segment_files.append(set(files_out.splitlines()) if files_out else set())

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

scope_path = "tasks/review-trail/.weekly-reviewer-scopes.json"
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
