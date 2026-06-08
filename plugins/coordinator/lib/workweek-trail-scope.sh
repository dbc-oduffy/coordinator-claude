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

# Resolve Python interpreter — same portable pattern as coordinator-session.sh.
_WWTS_LIB="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
[[ ! -f "$_WWTS_LIB" ]] && _WWTS_LIB="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
if [[ -f "$_WWTS_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_WWTS_LIB"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "ERROR: no Python interpreter found (python3/python/py) — required for workweek scope computation" >&2
  exit 1
fi

"$PYTHON_BIN" "${PYTHON_ARGS[@]}" - <<'PYEOF'
import json, os, re, subprocess, sys

# A safe git rev-range from an UNTRUSTED trail-JSON sha_range. Each side must
# START with an alphanumeric (blocks leading-dash argument injection — e.g.
# "--output=/x..y" reaching `git rev-list` as a flag) and contains no whitespace
# or shell metacharacters. Permits the legitimate shapes the trail emits:
# hex SHAs, the literal HEAD, and ^ / ~N ancestry suffixes
# (e.g. "009505d6..HEAD", "b05a1dcf^..817dba14", "71e24142~1..fd413ff9").
SAFE_RANGE = re.compile(r"^[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*\.\.\.?[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*$")

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

    # --- Classification: typed field (scope_kind) takes precedence over inference ---
    # When scope_kind is present (records written by coordinator-write-review-trail.sh
    # after the typed-field addition), use it directly:
    #   diff        → code-diff record; include in scope accounting.
    #   plan        → plan/doc/integration review; legitimately non-diff; skip silently.
    #   integration → same as plan.
    # When scope_kind is absent (legacy records written before the field was added),
    # fall back to the original ".." presence inference for backward compatibility.
    # Negative-spec: do NOT emit a WARN for records that are typed as plan/integration —
    # the typed field makes the intent explicit; a WARN would be noise, not signal.
    scope_kind = rec.get("scope_kind")
    if scope_kind is not None:
        if scope_kind in ("plan", "integration"):
            # Legitimately non-diff; skip silently.
            continue
        # Review: focused-review — typed-diff path must be at least as informative as the
        # legacy path it supersedes. Guard empty sha_range explicitly before SAFE_RANGE check.
        if not sha_range:
            artifact = rec.get("artifact", "<unknown>")
            print(f"WARN: diff-typed trail record has empty sha_range: {artifact}", file=sys.stderr)
            continue
        # scope_kind == "diff" (or any future value): fall through to sha_range processing.
    else:
        # Legacy record — no scope_kind field. Fall back to ".." inference.
        if not sha_range or ".." not in sha_range:
            # Plan/doc reviews (and any non-diff-scoped record) legitimately carry no
            # SHA range. Emit a WARN only on this legacy path — typed records suppress it.
            artifact = rec.get("artifact", "<unknown>")
            print(f"WARN: skipping non-diff trail record (sha_range={sha_range!r}): {artifact}", file=sys.stderr)
            continue

    if not SAFE_RANGE.match(sha_range):
        # Has ".." but is not a safe rev-range — refuse to hand it to git.
        # Defends against argument injection via an untrusted trail-JSON record.
        artifact = rec.get("artifact", "<unknown>")
        print(f"WARN: skipping unsafe sha_range {sha_range!r} (failed rev-range validation): {artifact}", file=sys.stderr)
        continue
    shas_out  = run(["git", "rev-list", sha_range])
    # Use git-log --name-only (union of all touched files across the range)
    # rather than git-diff --name-only (net diff, which undercounts when a file
    # is modified then reverted within the range — those vanish from the net diff
    # but should still be considered "touched" for seam detection).
    log_out   = run(["git", "log", "--name-only", "--format=", sha_range])
    files_out_lines = [l for l in log_out.splitlines() if l.strip()]
    # Dedupe across commits in the range (log emits one path per commit-that-touched-it).
    segment_shas.append(set(shas_out.splitlines()) if shas_out else set())
    segment_files.append(set(files_out_lines) if files_out_lines else set())

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
