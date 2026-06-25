#!/usr/bin/env bash
# review-coverage-core.sh — shared coverage-computation core for review-trail gates.
#
# Purpose: provides the reusable primitives consumed by BOTH the weekly scope gate
# (lib/workweek-trail-scope.sh) and the chain-end coverage gate
# (bin/review-coverage-gate.sh):
#   - SAFE_RANGE argument-injection validator
#   - JSON-OR-JSONL dual-shape trail-record parser
#   - per-record `git rev-list <sha_range>` union loop → reviewed_set
#   - verdict filter: exclude verdict=pending; include {ok, warn, blocked, waived}
#   - scope_kind filter: skip plan/integration records silently
#
# VERDICT FILTER LIVES HERE — both gates inherit it:
#   pending  → EXCLUDED (review not yet complete; counting pending as coverage
#              would allow the gate to pass on un-reviewed commits — the latent
#              gap closed by this shared extraction, per C2 of the plan).
#   waived   → INCLUDED (explicit PM waiver is a coverage decision).
#   ok / warn / blocked → INCLUDED.
#   absent   → INCLUDED (legacy records without verdict field still count).
#
# Interface (called as a subprocess, never sourced):
#
#   review-coverage-core.sh --reviewed-set <trail-path> [<trail-path>...]
#       Prints one reviewed SHA per line on stdout (union across all records).
#       Returns exit 0 on success, 1 on fatal error.
#
#   review-coverage-core.sh --segments-json <trail-path> [<trail-path>...]
#       Prints a JSON array of segment objects on stdout:
#         [{"sha_range":"...","shas":["..."],"files":["..."]}]
#       Each entry represents one valid diff trail record with its per-commit
#       coverage info. The weekly gate uses this for seam detection.
#       Returns exit 0 on success, 1 on fatal error.
#
# Environment:
#   TRAIL_FILES — newline-separated list of trail-file paths (alternative to
#                 passing paths as positional args; used by workweek-trail-scope.sh).
#   WEEK_START  — if set, only records whose filename date-prefix falls within
#                 [WEEK_START, TODAY] are processed (weekly-gate filtering).
#   TODAY       — if set, upper bound for date-prefix filtering (pairs with WEEK_START).
#
# Cross-platform: bash≥4 + BSD coreutils. No GNU-isms.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2

set -euo pipefail

# Bail early on bash < 4 — we use BASH_VERSINFO (available since bash 2, so the
# guard itself is safe on 3.2) but the consumer scripts require bash 4 features.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
_usage() {
  echo "Usage: $0 (--reviewed-set | --segments-json) [<trail-path>...]" >&2
  echo "  or set TRAIL_FILES env var and call with a mode flag only." >&2
  exit 1
}

if [[ $# -lt 1 ]]; then
  _usage
fi

MODE="$1"
shift

case "$MODE" in
  --reviewed-set|--segments-json) ;;
  *) _usage ;;
esac

# ---------------------------------------------------------------------------
# Collect trail-file paths (positional) + optional --on-record-error policy.
#
# --on-record-error fail (default): a record that parses as neither JSON nor
#   JSONL aborts the run (exit 1). This preserves the weekly-gate's documented
#   detect-then-fail-loud-on-segment-shape doctrine (workstream-complete-review.md
#   § detect-then-fail-loud; b3g-077) — the weekly gate scans the NARROW current-week
#   live dir, where a malformed record is a fresh defect the operator must fix.
# --on-record-error skip: warn-and-continue on an unprocessable record — one that
#   parses as neither JSON nor JSONL, OR whose sha_range references an unresolvable
#   git ref (a literal "WORKING" placeholder, a GC'd/rebased SHA, a foreign-repo SHA).
#   The chain-end
#   coverage gate scans the FULL archive (live + archive/**, hundreds of historical
#   records via list-review-trail-records.sh); a single ancient corrupt/non-record
#   file (e.g. a doc-link-checker sidecar sharing the dir) must not abort coverage of
#   TODAY's chain. Fail-safe: an unparseable record credits NO commits, so its
#   (unknowable) coverage is simply not counted → those commits surface as MORE
#   review, never less. The skip is announced per-file on stderr (not silent).
# ---------------------------------------------------------------------------
ON_RECORD_ERROR="fail"
declare -a TRAIL_PATH_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --on-record-error)
      ON_RECORD_ERROR="${2:-}"
      shift 2
      ;;
    *)
      TRAIL_PATH_ARGS+=("$1")
      shift
      ;;
  esac
done
case "$ON_RECORD_ERROR" in
  skip|fail) ;;
  *) echo "ERROR: --on-record-error must be 'skip' or 'fail', got: ${ON_RECORD_ERROR}" >&2; exit 1 ;;
esac
export ON_RECORD_ERROR

# ---------------------------------------------------------------------------
# Resolve Python interpreter — same portable pattern as workweek-trail-scope.sh
# ---------------------------------------------------------------------------
PYTHON_ARGS=()
_CORE_LIB="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
[[ ! -f "$_CORE_LIB" ]] && _CORE_LIB="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
if [[ -f "$_CORE_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_CORE_LIB"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "ERROR: no Python interpreter found — required for review-coverage-core" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Encode positional trail-file paths into an env var for the Python heredoc
# (avoids shell-escaping gymnastics when passing arbitrary paths via args)
# ---------------------------------------------------------------------------
# Join positional args with newlines; Python picks them up via TRAIL_PATH_ARGS env var.
export TRAIL_PATH_ARGS_ENV
TRAIL_PATH_ARGS_ENV="$(printf '%s\n' "${TRAIL_PATH_ARGS[@]}")"

export TRAIL_FILES="${TRAIL_FILES:-}"
export WEEK_START="${WEEK_START:-}"
export TODAY="${TODAY:-}"
export COVERAGE_MODE="$MODE"

"$PYTHON_BIN" "${PYTHON_ARGS[@]}" - <<'PYEOF'
import json, os, re, subprocess, sys

# ---------------------------------------------------------------------------
# SAFE_RANGE — argument-injection validator.
#
# A safe git rev-range from UNTRUSTED trail-JSON sha_range. Each side must
# START with an alphanumeric (blocks leading-dash argument injection — e.g.
# "--output=/x..y" reaching `git rev-list` as a flag) and contains no
# whitespace or shell metacharacters. Permits the legitimate shapes the trail
# emits: hex SHAs, HEAD, and ^/~N ancestry suffixes
# (e.g. "009505d6..HEAD", "b05a1dcf^..817dba14", "71e24142~1..fd413ff9").
#
# VERDICT FILTER is also centralised here — both gates inherit:
#   pending  → EXCLUDED (review not complete; must not count as coverage)
#   waived   → INCLUDED (explicit PM waiver = coverage decision)
#   ok / warn / blocked / absent → INCLUDED
# ---------------------------------------------------------------------------
# Review: code-reviewer — SAFE_RANGE is an argument-injection (no-leading-dash) guard,
# NOT a ref-validity filter; git resolves/rejects the ref itself. The class is intentionally
# permissive (allows leading / and .) to avoid rejecting legitimate ~N/^ ancestry refs.
SAFE_RANGE = re.compile(
    r"^[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*\.\.\.?[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*$"
)

EXCLUDED_VERDICTS = {"pending"}

def verdict_counts(rec):
    """Return True if this record's verdict allows it to count toward reviewed_set."""
    v = rec.get("verdict", None)
    if v is None:
        return True   # legacy record — no verdict field; include
    return v not in EXCLUDED_VERDICTS

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        print(f"ERROR: command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def run_ok(cmd):
    """Run cmd; return (returncode, stdout, stderr) WITHOUT exiting — lets the
    per-record loop honour the on_record_error policy on git-resolution failure
    (a record whose range names an unresolvable ref, e.g. a 'WORKING' placeholder
    or a GC'd/rebased/foreign SHA)."""
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    return result.returncode, result.stdout.strip(), result.stderr

# ---------------------------------------------------------------------------
# Collect trail file paths from env
# ---------------------------------------------------------------------------
trail_files_env  = os.environ.get("TRAIL_FILES", "")
trail_args_env   = os.environ.get("TRAIL_PATH_ARGS_ENV", "")
week_start       = os.environ.get("WEEK_START", "")
today            = os.environ.get("TODAY", "")
mode             = os.environ.get("COVERAGE_MODE", "--reviewed-set")
on_record_error   = os.environ.get("ON_RECORD_ERROR", "fail")

# Merge both sources; deduplicate while preserving order.
seen_paths = set()
trail_files = []
for line in (trail_files_env + "\n" + trail_args_env).split("\n"):
    p = line.strip()
    if p and p.endswith(".json") and p not in seen_paths:
        seen_paths.add(p)
        trail_files.append(p)

# ---------------------------------------------------------------------------
# Parse trail records — JSON-OR-JSONL dual-shape fallback.
#
# Writer-side doctrine: review-trail records are accepted in either shape:
#   (a) one JSON object per file (single-line OR pretty-printed)
#   (b) JSONL — one JSON object per line (integrator-envelope shape)
# Convergence lives in the parser (here), not in the writers.
# ---------------------------------------------------------------------------
class _TrailParseError(Exception):
    """Raised when a trail file parses as neither JSON nor JSONL."""

def parse_trail_file(f):
    """Return list of parsed record dicts from a trail file. Raises _TrailParseError on unrecoverable error."""
    try:
        with open(f) as fh:
            rec = json.load(fh)
        return [rec]
    except json.JSONDecodeError as json_err:
        # JSONL fallback — one object per line.
        try:
            records = []
            with open(f) as fh:
                for ln, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    records.append(json.loads(line))
            return records
        except Exception as e:
            raise _TrailParseError(
                f"could not parse trail record {f} — "
                f"failed as JSON ({json_err}) and JSONL ({e})"
            )
    except _TrailParseError:
        raise
    except Exception as e:
        raise _TrailParseError(f"could not parse trail record {f}: {e}")

# ---------------------------------------------------------------------------
# Load and filter records
# ---------------------------------------------------------------------------
all_records = []  # list of (source_path, rec_dict)
for f in trail_files:
    basename = os.path.basename(f)
    # Date-prefix filter: only when WEEK_START and TODAY are set (weekly-gate mode).
    if week_start and today:
        date_prefix = basename[:10]
        if not (week_start <= date_prefix <= today):
            continue
    try:
        recs = parse_trail_file(f)
    except _TrailParseError as e:
        if on_record_error == "skip":
            print(f"WARN: skipping unparseable trail record: {e}", file=sys.stderr)
            continue
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # I/O or unexpected error opening the file.
        if on_record_error == "skip":
            print(f"WARN: skipping unreadable trail record {f}: {e}", file=sys.stderr)
            continue
        print(f"ERROR: could not open trail record {f}: {e}", file=sys.stderr)
        sys.exit(1)
    for rec in recs:
        all_records.append((f, rec))

# ---------------------------------------------------------------------------
# Per-record classification and git rev-list union
# ---------------------------------------------------------------------------
# Each entry: {"sha_range": str, "shas": set, "files": set}
segments = []

for source_path, rec in all_records:
    sha_range = rec.get("sha_range", "")

    # --- Scope-kind classification (same logic as workweek-trail-scope.sh) ---
    scope_kind = rec.get("scope_kind")
    if scope_kind is not None:
        if scope_kind in ("plan", "integration"):
            continue  # legitimately non-diff; skip silently
        if not sha_range:
            artifact = rec.get("artifact", "<unknown>")
            print(
                f"WARN: diff-typed trail record has empty sha_range: {artifact}",
                file=sys.stderr,
            )
            continue
        # scope_kind == "diff" (or future value): fall through
    else:
        # Legacy record — no scope_kind. Use ".." inference.
        if not sha_range or ".." not in sha_range:
            artifact = rec.get("artifact", "<unknown>")
            print(
                f"WARN: skipping non-diff trail record (sha_range={sha_range!r}): {artifact}",
                file=sys.stderr,
            )
            continue

    # --- SAFE_RANGE validation (argument-injection defence) ---
    if not SAFE_RANGE.match(sha_range):
        artifact = rec.get("artifact", "<unknown>")
        print(
            f"WARN: skipping unsafe sha_range {sha_range!r} "
            f"(failed rev-range validation): {artifact}",
            file=sys.stderr,
        )
        continue

    # --- Verdict filter (THE canonical verdict filter for both gates) ---
    # pending → excluded; ok/warn/blocked/waived/absent → included.
    if not verdict_counts(rec):
        artifact = rec.get("artifact", "<unknown>")
        print(
            f"INFO: skipping verdict=pending trail record (not yet reviewed): {artifact}",
            file=sys.stderr,
        )
        continue

    # --- git rev-list: per-commit coverage ---
    # A record whose range references an unresolvable ref (literal placeholder
    # like "WORKING", a GC'd/rebased SHA, or a SHA from another repo) fails git
    # resolution. Under on_record_error=skip the record is skipped with a warning
    # (it credits no coverage — fail-safe: those commits surface as more review);
    # under fail the run aborts (weekly-gate detect-then-fail-loud doctrine).
    artifact = rec.get("artifact", "<unknown>")
    rc, shas_out, rev_err = run_ok(["git", "rev-list", sha_range])
    if rc != 0:
        last_err = rev_err.strip().splitlines()[-1] if rev_err.strip() else "git rev-list failed"
        if on_record_error == "skip":
            print(
                f"WARN: skipping trail record with unresolvable range {sha_range!r}: "
                f"{last_err} ({artifact})",
                file=sys.stderr,
            )
            continue
        print(f"ERROR: command failed: git rev-list {sha_range}\n{rev_err}", file=sys.stderr)
        sys.exit(1)
    shas = set(shas_out.splitlines()) if shas_out else set()

    # --- git log --name-only: files touched (for seam detection) ---
    rc2, log_out, log_err = run_ok(["git", "log", "--name-only", "--format=", sha_range])
    if rc2 != 0:
        if on_record_error == "skip":
            print(
                f"WARN: skipping trail record (git log failed) {sha_range!r} ({artifact})",
                file=sys.stderr,
            )
            continue
        print(f"ERROR: command failed: git log {sha_range}\n{log_err}", file=sys.stderr)
        sys.exit(1)
    files = set(l for l in log_out.splitlines() if l.strip()) if log_out else set()

    segments.append({
        "sha_range": sha_range,
        "shas": shas,
        "files": files,
    })

# ---------------------------------------------------------------------------
# Emit output in the requested mode
# ---------------------------------------------------------------------------
if mode == "--reviewed-set":
    # Union of all reviewed SHAs, one per line.
    reviewed = set()
    for seg in segments:
        reviewed |= seg["shas"]
    for sha in sorted(reviewed):
        print(sha)

elif mode == "--segments-json":
    # JSON array of per-segment records (shas and files as sorted lists for
    # deterministic output; sha_range as recorded).
    out = []
    for seg in segments:
        out.append({
            "sha_range": seg["sha_range"],
            "shas": sorted(seg["shas"]),
            "files": sorted(seg["files"]),
        })
    print(json.dumps(out, indent=2))

else:
    print(f"ERROR: unknown mode: {mode}", file=sys.stderr)
    sys.exit(1)
PYEOF
