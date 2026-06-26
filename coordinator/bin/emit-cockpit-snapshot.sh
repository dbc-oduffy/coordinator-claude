#!/usr/bin/env bash
# emit-cockpit-snapshot.sh — compose a C2-contract-conformant snapshot from
# coordinator surfaces and write state/cockpit-emission.json.
#
# Purpose: single-artifact emission that maps each coordinator surface to its
# corresponding contract entity, normalises legacy-data gaps, quarantines
# records with absent required-non-nullable keys, and validates every main-array
# record via validate-cockpit-record.mjs before writing.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C5
# Contract version: sourced at runtime from cockpit-contract/schema/cockpit-contract.schema.json
#
# Usage:
#   emit-cockpit-snapshot.sh
#   emit-cockpit-snapshot.sh --out /path/to/output.json
#
# Exit codes:
#   0 — success, state/cockpit-emission.json written
#   1 — hard precondition failed or main-array record validation failed (code bug)
set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (bash >=4 required for associative arrays)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "ERROR: bash >= 4 required (this is bash ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Repo root resolution — cwd-scope guard (mandatory verbatim per spec)
# Do NOT regroup as ${CLAUDE_HOME:-$HOME/.claude} — wrong grouping.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer script-location resolution: bin/ -> coordinator/ -> plugins/ -> .claude/
_INFERRED_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
if [[ -d "$_INFERRED_ROOT/state" && -d "$_INFERRED_ROOT/plugins" ]]; then
  ROOT="$_INFERRED_ROOT"
else
  # Mandatory env-fallback form (verbatim — NOT ${CLAUDE_HOME:-$HOME/.claude})
  ROOT="${CLAUDE_HOME:-$HOME}/.claude"
fi

COORDINATOR_ROOT="$ROOT/plugins/coordinator-claude/coordinator"

# ---------------------------------------------------------------------------
# HARD PRECONDITION: cockpit-contract/dist/index.js must exist
# ---------------------------------------------------------------------------
DIST_ENTRY="$COORDINATOR_ROOT/cockpit-contract/dist/index.js"
if [[ ! -f "$DIST_ENTRY" ]]; then
  echo "ERROR: cockpit-contract/dist/ not found." >&2
  echo "Run: cd $COORDINATOR_ROOT/cockpit-contract && pnpm install" >&2
  echo "(pnpm install rebuilds dist/ via the package's prepare script)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
OUT_FILE="$ROOT/state/cockpit-emission.json"
if [[ "${1:-}" == "--out" && -n "${2:-}" ]]; then
  OUT_FILE="$2"
fi

VALIDATE_MJS="$COORDINATOR_ROOT/bin/lib/validate-cockpit-record.mjs"

# ---------------------------------------------------------------------------
# Collect git state once (used for provenance on all records)
# ---------------------------------------------------------------------------
GIT_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
GIT_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")"
GIT_SHA_SHORT="${GIT_SHA:0:8}"
OBSERVED_AT="$(date -u +%FT%TZ)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo "unknown")"
REPO_NAME="dbc-oduffy/.claude-prime"

# ---------------------------------------------------------------------------
# Helper: build provenance envelope JSON fragment
# Args: source_kind path derivation
# ---------------------------------------------------------------------------
provenance_json() {
  local source_kind="$1"
  local prov_path="$2"
  local derivation="$3"
  jq -cn \
    --arg source_kind "$source_kind" \
    --arg repo "$REPO_NAME" \
    --arg branch "$GIT_BRANCH" \
    --arg sha "$GIT_SHA" \
    --arg path "$prov_path" \
    --arg observed_at "$OBSERVED_AT" \
    --arg derivation "$derivation" \
    '{
      source_kind: $source_kind,
      repo: $repo,
      ref: { branch: $branch, sha: $sha },
      path: $path,
      observed_at: $observed_at,
      derivation: $derivation
    }'
}

# ---------------------------------------------------------------------------
# Helper: validate a record JSON string against entity name; fail loud on failure
# Args: entity_name record_json description
# ---------------------------------------------------------------------------
validate_main_record() {
  local entity="$1"
  local record_json="$2"
  local description="${3:-}"
  local tmpf _val_output _val_rc
  tmpf="$(mktemp "${TMPDIR:-/tmp}/cockpit-validate.XXXXXX")"
  printf '%s' "$record_json" > "$tmpf"
  # Review: B-F8 — capture output once; re-running node on failure doubles startup cost
  # and risks divergent output if the record changes between calls (it can't here, but
  # the pattern is still wrong). One capture, one conditional print.
  # NOTE: the `if` wrapper is load-bearing under `set -e` — a bare `_val_output="$(node …)"`
  # assignment aborts the whole script the instant node exits non-zero, BEFORE the rc-check
  # below can print which record failed (the error path is then unreachable; failures look
  # like a silent exit 1). The `if` disables set -e for this one command so the diagnostic runs.
  if _val_output="$(node "$VALIDATE_MJS" "$entity" "$tmpf" 2>&1)"; then
    _val_rc=0
  else
    _val_rc=$?
  fi
  if [[ "$_val_rc" -ne 0 ]]; then
    echo "ERROR: main-array $entity record failed validation (code bug, not data gap)${description:+ — $description}" >&2
    echo "Record JSON:" >&2
    jq . "$tmpf" >&2 || cat "$tmpf" >&2
    echo "Validation errors:" >&2
    printf '%s\n' "$_val_output" >&2
    rm -f "$tmpf"
    exit 1
  fi
  rm -f "$tmpf"
}

# ===========================================================================
# SECTION 1 — HandoffSummary records
# Sources: query-records.js --type handoff + handoff-archived
# Normalization:
#   - kind absent → inject "session-handoff" (per Zod docstring)
#   - workstream absent → inject "" (empty string, valid z.string())
#   - predecessor absent → inject "none"
#   - scope absent → inject []
#   - Records missing title/created/status/deployment_state → quarantine
# ===========================================================================
echo "[emit] collecting handoffs..." >&2

HANDOFFS_LIVE_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type handoff --limit 0 --format json 2>/dev/null || echo "[]")"
HANDOFFS_ARCH_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type handoff-archived --limit 0 --format json 2>/dev/null || echo "[]")"

# Merge live + archived into one array
ALL_HANDOFFS_JSON="$(jq -s '.[0] + .[1]' <(echo "$HANDOFFS_LIVE_JSON") <(echo "$HANDOFFS_ARCH_JSON"))"

HANDOFFS_ARRAY="$(echo "$ALL_HANDOFFS_JSON" | jq -c --arg repo "$REPO_NAME" --arg observed_at "$OBSERVED_AT" --arg branch "$GIT_BRANCH" --arg sha "$GIT_SHA" '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    ($rec.path) as $p |
    # Normalization: inject kind if absent
    ($fm.kind // "session-handoff") as $kind |
    # Normalization: inject workstream if absent
    ($fm.workstream // "") as $workstream |
    # Normalization: inject predecessor if absent
    ($fm.predecessor // "none") as $predecessor |
    # Normalization: inject scope if absent
    ($fm.scope // []) as $scope |
    # Required fields check — quarantine logic handled in jq by emitting error markers
    # We need: title, created, status, deployment_state
    select(
      ($fm.title | type) == "string" and
      ($fm.created | type) == "string" and
      ($fm.status | type) == "string" and
      ($fm.deployment_state | type) == "string"
    ) |
    {
      repo: $repo,
      coordinator_root_path: ".",
      title: $fm.title,
      created: $fm.created,
      # superseded: retired handoff status — coerced to consumed at ingest so the strict 2.0 schema never sees it (handoff-archived.yaml stays tolerant upstream; see plan Key design decision)
      status: (if $fm.status == "superseded" then "consumed" else $fm.status end),
      kind: $kind,
      deployment_state: $fm.deployment_state,
      workstream: $workstream,
      predecessor: $predecessor,
      scope: $scope,
      consumed_by: ($fm.consumed_by // null),
      # consumed_at: tolerant datetime guard — bare ISO dates (no T) become null;
      # some legacy handoffs stored only a date here (pre-datetime convention).
      consumed_at: (if (($fm.consumed_at | type) == "string") and ($fm.consumed_at | contains("T")) then $fm.consumed_at else null end),
      picked_up_by: ($fm.picked_up_by // null),
      # shipped_in and acceptance_criteria are null here; enriched per-record below.
      shipped_in: null,
      acceptance_criteria: null,
      # _shipped_in_sha is a temp field (removed before validation); carries the raw
      # frontmatter SHA string for git-resolution in the enrichment loop below.
      _shipped_in_sha: ($fm.shipped_in // null),
      provenance: {
        source_kind: "local_fs",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: $p,
        observed_at: $observed_at,
        derivation: "parsed"
      }
    }
  ]
')"

# Collect malformed handoffs (those that failed select)
MALFORMED_HANDOFFS="$(echo "$ALL_HANDOFFS_JSON" | jq -c --arg repo "$REPO_NAME" '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    select(
      (($fm.title | type) != "string") or
      (($fm.created | type) != "string") or
      (($fm.status | type) != "string") or
      (($fm.deployment_state | type) != "string")
    ) |
    {
      path: $rec.path,
      reason: "missing required non-nullable field (title/created/status/deployment_state)",
      frontmatter_keys: ($fm | keys)
    }
  ]
')"

# Enrich (shipped_in + acceptance_criteria) and validate all handoff records.
# shipped_in: resolve _shipped_in_sha (temp field) → {sha, date} via git log.
# acceptance_criteria: parse body checklist from file; emit ratio {done, total} or null.
# D9 nullability: all five new keys must always be present (null when uncomputed).
echo "[emit] enriching and validating handoffs..." >&2
HANDOFF_COUNT="$(echo "$HANDOFFS_ARRAY" | jq 'length')"
ENRICHED_HANDOFFS="[]"
if [[ "$HANDOFF_COUNT" -gt 0 ]]; then
  # Review: F5 — accumulate into a temp file and assemble once after the loop to avoid
  # O(n²) jq re-parse of the growing ENRICHED_HANDOFFS array on each iteration.
  ENRICHED_TMP="$(mktemp "${TMPDIR:-/tmp}/cockpit-handoffs-enriched.XXXXXX")"
  for i in $(seq 0 $((HANDOFF_COUNT - 1))); do
    rec="$(echo "$HANDOFFS_ARRAY" | jq -c ".[$i]")"

    # Resolve shipped_in: git log lookup for {sha, date}; null if SHA absent or unresolvable
    _si_sha="$(echo "$rec" | jq -r '._shipped_in_sha // empty')"
    _shipped_in_json="null"
    if [[ -n "$_si_sha" ]]; then
      _si_date="$(git -C "$ROOT" log -1 --format="%ad" --date=format:%Y-%m-%d "$_si_sha" 2>/dev/null || echo "")"
      if [[ -n "$_si_date" ]]; then
        _shipped_in_json="$(jq -cn --arg sha "$_si_sha" --arg date "$_si_date" '{sha: $sha, date: $date}')"
      fi
    fi

    # Parse acceptance_criteria from handoff body — ratio only, no prose (privacy constraint)
    # Count: done = "- [x]" / "- [X]" lines; not_done = "- [ ]" lines
    _rec_path="$(echo "$rec" | jq -r '.provenance.path')"
    _ac_json="null"
    if [[ -n "$_rec_path" && -f "$ROOT/$_rec_path" ]]; then
      _ac_body="$(cat "$ROOT/$_rec_path")"
      _ac_done="$(printf '%s' "$_ac_body" | awk '/^[[:space:]]*- \[[xX]\]/{n++} END{print n+0}')"
      _ac_not_done="$(printf '%s' "$_ac_body" | awk '/^[[:space:]]*- \[ \]/{n++} END{print n+0}')"
      _ac_total=$(( _ac_done + _ac_not_done ))
      if [[ "$_ac_total" -gt 0 ]]; then
        _ac_json="$(jq -cn --argjson done "$_ac_done" --argjson total "$_ac_total" '{done: $done, total: $total}')"
      fi
    fi

    # Remove temp field; inject resolved lifecycle fields
    rec="$(echo "$rec" | jq -c \
      --argjson shipped_in "$_shipped_in_json" \
      --argjson acceptance_criteria "$_ac_json" \
      'del(._shipped_in_sha) | .shipped_in = $shipped_in | .acceptance_criteria = $acceptance_criteria')"

    validate_main_record "handoff-summary" "$rec" "index $i"
    printf '%s\n' "$rec" >> "$ENRICHED_TMP"
  done
  ENRICHED_HANDOFFS="$(jq -s '.' "$ENRICHED_TMP")"
  rm -f "$ENRICHED_TMP"
fi
HANDOFFS_ARRAY="$ENRICHED_HANDOFFS"

# ===========================================================================
# SECTION 2 — BacklogItemSummary records
# Sources: query-records.js --type bug|debt|improvement
# ===========================================================================
echo "[emit] collecting backlogs..." >&2

BUG_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type bug --limit 0 --format json 2>/dev/null || echo "[]")"
DEBT_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type debt --limit 0 --format json 2>/dev/null || echo "[]")"
IMPROV_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type improvement --limit 0 --format json 2>/dev/null || echo "[]")"

# Build BacklogItemSummary records — bug type
# Review: B-F1 — enum-invalid severity (e.g. "p1" lowercase, unknown value) quarantines
# non-fatally rather than aborting the emitter; applies same principle as missing-key.
build_backlog_records() {
  local type_tag="$1"
  local raw_json="$2"
  echo "$raw_json" | jq -c --arg type "$type_tag" --arg repo "$REPO_NAME" --arg observed_at "$OBSERVED_AT" --arg branch "$GIT_BRANCH" --arg sha "$GIT_SHA" '
    [
      .[] | . as $rec |
      ($rec.frontmatter) as $fm |
      ($rec.path) as $p |
      select(
        ($fm.id | type) == "string" and
        ($fm.created | type) == "string" and
        ($fm.status | type) == "string" and
        ($fm.title | type) == "string"
      ) |
      # Also exclude bug records whose severity is present but not a valid P0..P3 enum value
      select(
        $type != "bug" or
        ($fm.severity == null) or
        ($fm.severity | . == "P0" or . == "P1" or . == "P2" or . == "P3")
      ) |
      {
        type: $type,
        id: $fm.id,
        created: $fm.created,
        status: $fm.status,
        title: $fm.title,
        repo: $repo,
        from_repo: ($fm.from_repo // "claude-central-em"),
        coordinator_root_path: ".",
        queue_scope: ($fm.queue_scope // "project"),
        severity: (if $type == "bug" then ($fm.severity // null) else null end),
        risk: (if $type == "debt" then ($fm.risk // null) else null end),
        provenance: {
          source_kind: "local_fs",
          repo: $repo,
          ref: { branch: $branch, sha: $sha },
          path: $p,
          observed_at: $observed_at,
          derivation: "parsed"
        }
      }
    ]
  '
}

BUG_RECORDS="$(build_backlog_records "bug" "$BUG_JSON")"
DEBT_RECORDS="$(build_backlog_records "debt" "$DEBT_JSON")"
IMPROV_RECORDS="$(build_backlog_records "improvement" "$IMPROV_JSON")"

ALL_BACKLOGS="$(jq -s '.[0] + .[1] + .[2]' <(echo "$BUG_RECORDS") <(echo "$DEBT_RECORDS") <(echo "$IMPROV_RECORDS"))"

# Malformed backlogs
# Review: B-F1 — also quarantine bug records with severity present but outside P0..P3 enum.
build_malformed_backlogs() {
  local type_tag="$1"
  local raw_json="$2"
  echo "$raw_json" | jq -c --arg type "$type_tag" '
    [
      .[] | . as $rec |
      ($rec.frontmatter) as $fm |
      (
        # Missing required fields
        if (
          (($fm.id | type) != "string") or
          (($fm.created | type) != "string") or
          (($fm.status | type) != "string") or
          (($fm.title | type) != "string")
        ) then
          { path: $rec.path, type: $type, reason: "missing required field (id/created/status/title)" }
        # Bug with invalid severity enum (present and non-null but not P0..P3)
        elif (
          $type == "bug" and
          ($fm.severity != null) and
          ($fm.severity | . != "P0" and . != "P1" and . != "P2" and . != "P3")
        ) then
          { path: $rec.path, type: $type, reason: ("invalid severity enum value (got \($fm.severity); expected P0|P1|P2|P3)") }
        else
          empty
        end
      )
    ]
  '
}

MALFORMED_BUG="$(build_malformed_backlogs "bug" "$BUG_JSON")"
MALFORMED_DEBT="$(build_malformed_backlogs "debt" "$DEBT_JSON")"
MALFORMED_IMPROV="$(build_malformed_backlogs "improvement" "$IMPROV_JSON")"
MALFORMED_BACKLOGS="$(jq -s '.[0] + .[1] + .[2]' <(echo "$MALFORMED_BUG") <(echo "$MALFORMED_DEBT") <(echo "$MALFORMED_IMPROV"))"

# Validate backlog records
echo "[emit] validating backlogs..." >&2
BACKLOG_COUNT="$(echo "$ALL_BACKLOGS" | jq 'length')"
if [[ "$BACKLOG_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((BACKLOG_COUNT - 1))); do
  rec="$(echo "$ALL_BACKLOGS" | jq -c ".[$i]")"
  validate_main_record "backlog-item-summary" "$rec" "index $i"
done
fi

# ===========================================================================
# SECTION 3 — ReviewTrail records
# Source: list-review-trail-records.sh (union of live + archived)
# derive reviewed_at from filename: YYYY-MM-DD-HHMMSS[ns]-<session>.json
# Normalise verdict case; quarantine invalid verdict / parse errors
# ===========================================================================
echo "[emit] collecting review trail..." >&2

# Use Python for the full review trail processing — handles large ints, parse errors,
# verdict normalization, and non-standard filenames robustly.
# Write the file list to a temp file first to avoid SIGPIPE in the pipe-to-heredoc pattern.
_RT_PATHS_TMP="$(mktemp "${TMPDIR:-/tmp}/cockpit-rt-paths.XXXXXX")"
bash "$COORDINATOR_ROOT/bin/list-review-trail-records.sh" 2>/dev/null > "$_RT_PATHS_TMP" || true

_RT_RESULT="$(
  python3 - "$REPO_NAME" "$OBSERVED_AT" "$GIT_BRANCH" "$GIT_SHA" "$_RT_PATHS_TMP" <<'PYEOF' # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
import json, sys, os, re

repo = sys.argv[1]
observed_at = sys.argv[2]
git_branch = sys.argv[3]
git_sha = sys.argv[4]
paths_file = sys.argv[5]

VALID_VERDICTS = {"ok", "warn", "blocked", "waived"}
# Normalise known non-standard verdict strings to schema-valid ones
VERDICT_MAP = {
    "ok": "ok",
    "OK": "ok",
    "warn": "warn",
    "WARN": "warn",
    "blocked": "blocked",
    "BLOCKED": "blocked",
    "waived": "waived",
    "WAIVED": "waived",
    # Non-standard verdicts that appear in older records → quarantine (no mapping)
}

valid_records = []
malformed = []

with open(paths_file) as f:
    paths = [line.strip() for line in f if line.strip()]

for filepath in paths:
    if not filepath or not os.path.isfile(filepath):
        continue

    # Parse reviewed_at from filename
    bn = os.path.basename(filepath)
    if bn.endswith(".json"):
        bn_stem = bn[:-5]
    else:
        bn_stem = bn

    # Extract date: first 10 chars YYYY-MM-DD
    rt_date = bn_stem[:10] if len(bn_stem) >= 10 else "1970-01-01"
    rest = bn_stem[11:] if len(bn_stem) > 11 else ""

    # Check if the next segment is all-numeric (HHMMSS+nanoseconds)
    # Filename: YYYY-MM-DD-HHMMSS[nanoseconds]-<session>
    # or: YYYY-MM-DD-<description>
    m = re.match(r'^(\d{6,})(?:-(.+))?$', rest)
    if m:
        time_digits = m.group(1)
        # First 6 digits = HHMMSS
        hh = time_digits[0:2] if len(time_digits) >= 2 else "00"
        mm = time_digits[2:4] if len(time_digits) >= 4 else "00"
        ss = time_digits[4:6] if len(time_digits) >= 6 else "00"
        reviewed_at = f"{rt_date}T{hh}:{mm}:{ss}Z"
    else:
        # Non-numeric segment: YYYY-MM-DD-<description>.json → midnight
        reviewed_at = f"{rt_date}T00:00:00Z"

    # Read and parse the JSON body
    try:
        raw = open(filepath).read()
        body = json.loads(raw)
    except Exception as e:
        malformed.append({
            "path": filepath,
            "reason": f"JSON parse error: {e}"
        })
        continue

    if not isinstance(body, dict):
        malformed.append({"path": filepath, "reason": "body is not a JSON object"})
        continue

    sha_range = body.get("sha_range")
    reviewer = body.get("reviewer")
    raw_verdict = body.get("verdict")
    diff_loc = body.get("diff_loc", 0)

    # Missing required fields → quarantine
    if not isinstance(sha_range, str) or not sha_range:
        malformed.append({"path": filepath, "reason": "missing sha_range"})
        continue
    if not isinstance(reviewer, str) or not reviewer:
        malformed.append({"path": filepath, "reason": "missing reviewer"})
        continue

    # Normalise verdict
    if raw_verdict is None:
        malformed.append({"path": filepath, "reason": "missing verdict"})
        continue
    verdict = VERDICT_MAP.get(str(raw_verdict))
    if verdict is None:
        malformed.append({
            "path": filepath,
            "reason": f"invalid verdict '{raw_verdict}' (not in ok|warn|blocked|waived)"
        })
        continue

    # Ensure diff_loc is an integer
    try:
        diff_loc_int = int(diff_loc) if diff_loc is not None else 0
    except (TypeError, ValueError):
        diff_loc_int = 0

    record = {
        "repo": repo,
        "coordinator_root_path": ".",
        "sha_range": sha_range,
        "reviewer": reviewer,
        "verdict": verdict,
        "diff_loc": diff_loc_int,
        "reviewed_at": reviewed_at,
        "workstream": body.get("workstream", None),
        "provenance": {
            "source_kind": "local_fs",
            "repo": repo,
            "ref": {"branch": git_branch, "sha": git_sha},
            "path": filepath,
            "observed_at": observed_at,
            "derivation": "parsed"
        }
    }
    valid_records.append(record)

result = {"valid": valid_records, "malformed": malformed}
print(json.dumps(result))
PYEOF
)"

rm -f "$_RT_PATHS_TMP"
REVIEW_TRAIL_ARRAY="$(echo "$_RT_RESULT" | jq '.valid')"
MALFORMED_REVIEW_TRAIL="$(echo "$_RT_RESULT" | jq '.malformed')"

# Validate review trail records
echo "[emit] validating review trail..." >&2
RT_COUNT="$(echo "$REVIEW_TRAIL_ARRAY" | jq 'length')"
if [[ "$RT_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((RT_COUNT - 1))); do
  rec="$(echo "$REVIEW_TRAIL_ARRAY" | jq -c ".[$i]")"
  validate_main_record "review-trail" "$rec" "index $i"
done
fi

# ===========================================================================
# SECTION 4 — RoutineSignals (all 6 kinds)
# Sources: check-weekly-staleness.sh, check-arch-audit-staleness.sh,
#   docs (git log), bug-sweep header, dormant-repo (static), count-distill-backlog.sh
# All use derivation: "rolled_up"
# ===========================================================================
echo "[emit] collecting routine signals..." >&2

# Helper: run staleness script and lowercase the result
run_staleness() {
  local script="$1"
  local result
  result="$(bash "$script" 2>/dev/null || echo "UNKNOWN")"
  echo "$result" | tr '[:upper:]' '[:lower:]'
}

WEEKLY_STATE="$(run_staleness "$COORDINATOR_ROOT/bin/check-weekly-staleness.sh")"
ARCH_AUDIT_STATE="$(run_staleness "$COORDINATOR_ROOT/bin/check-arch-audit-staleness.sh")"

# Distill backlog signal
DISTILL_JSON="$(bash "$COORDINATOR_ROOT/bin/count-distill-backlog.sh" --format json 2>/dev/null || echo '{"pending_count":0,"threshold_days":30,"computed_state":"unknown"}')"
DISTILL_PENDING="$(echo "$DISTILL_JSON" | jq '.pending_count')"
DISTILL_STATE="$(echo "$DISTILL_JSON" | jq -r '.computed_state')"
DISTILL_OVERDUE="$(echo "$DISTILL_PENDING" | jq '. >= 6')"

# Docs staleness — count commits since last update-docs run
# Heuristic: check git log for update-docs commits
DOCS_COMMITS_SINCE=0
if command -v git &>/dev/null; then
  # Find last update-docs commit
  LAST_DOCS_SHA="$(git -C "$ROOT" log --oneline --all --grep="update-docs" --format="%H" 2>/dev/null | head -1 || echo "")"
  if [[ -n "$LAST_DOCS_SHA" ]]; then
    DOCS_COMMITS_SINCE="$(git -C "$ROOT" log --oneline "${LAST_DOCS_SHA}..HEAD" 2>/dev/null | wc -l | tr -d ' ')"
  else
    DOCS_COMMITS_SINCE=99
  fi
fi
if [[ "$DOCS_COMMITS_SINCE" -eq 0 ]]; then
  DOCS_STATE="fresh"
  DOCS_OVERDUE=false
elif [[ "$DOCS_COMMITS_SINCE" -le 10 ]]; then
  DOCS_STATE="mild"
  DOCS_OVERDUE=false
else
  DOCS_STATE="stale"
  DOCS_OVERDUE=true
fi

# Bug-sweep staleness — check for recent bug-sweep runs in git log
BUG_SWEEP_COMMITS=0
if command -v git &>/dev/null; then
  LAST_BUG_SHA="$(git -C "$ROOT" log --oneline --all --grep="bug-sweep\|bug_sweep" --format="%H" 2>/dev/null | head -1 || echo "")"
  if [[ -n "$LAST_BUG_SHA" ]]; then
    BUG_SWEEP_COMMITS="$(git -C "$ROOT" log --oneline "${LAST_BUG_SHA}..HEAD" 2>/dev/null | wc -l | tr -d ' ')"
  else
    BUG_SWEEP_COMMITS=99
  fi
fi
if [[ "$BUG_SWEEP_COMMITS" -eq 0 ]]; then
  BUG_SWEEP_STATE="fresh"
  BUG_SWEEP_OVERDUE=false
elif [[ "$BUG_SWEEP_COMMITS" -le 15 ]]; then
  BUG_SWEEP_STATE="mild"
  BUG_SWEEP_OVERDUE=false
else
  BUG_SWEEP_STATE="stale"
  BUG_SWEEP_OVERDUE=true
fi

# Dormant-repo: check if any sibling repo has had no commits in >30d
# Heuristic: always "unknown" since we don't have cross-repo git access here
DORMANT_STATE="unknown"
DORMANT_OVERDUE=false

# Build RoutineSignal array
build_routine_signal() {
  local kind="$1"
  local state="$2"
  local overdue="$3"
  local inputs_json="$4"
  local threshold="$5"
  jq -cn \
    --arg kind "$kind" \
    --arg repo "$REPO_NAME" \
    --arg computed_state "$state" \
    --arg overdue "$overdue" \
    --arg observed_at "$OBSERVED_AT" \
    --arg threshold "$threshold" \
    --argjson inputs "$inputs_json" \
    --arg branch "$GIT_BRANCH" \
    --arg sha "$GIT_SHA" \
    '{
      kind: $kind,
      repo: $repo,
      coordinator_root_path: ".",
      inputs: $inputs,
      threshold: $threshold,
      computed_state: $computed_state,
      overdue: ($overdue == "true"),
      observed_at: $observed_at,
      computed_as_of: $observed_at,
      provenance: {
        source_kind: "coordinator_artifact",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: "",
        observed_at: $observed_at,
        derivation: "rolled_up"
      }
    }'
}

WEEKLY_SIGNAL="$(build_routine_signal "weekly" "$WEEKLY_STATE" "$([ "$WEEKLY_STATE" = "stale" ] && echo true || echo false)" \
  '{"check": "check-weekly-staleness.sh"}' \
  "STALE: >= 5 days AND >= 15 commits since last weekly-reset; MILD: one condition; FRESH: neither")"

DOCS_SIGNAL="$(build_routine_signal "docs" "$DOCS_STATE" "$DOCS_OVERDUE" \
  "$(jq -cn --argjson c "$DOCS_COMMITS_SINCE" '{commits_since_update_docs: $c}')" \
  "STALE: >10 commits since last update-docs run; MILD: 1-10 commits; FRESH: 0 commits")"

ARCH_SIGNAL="$(build_routine_signal "arch-audit" "$ARCH_AUDIT_STATE" "$([ "$ARCH_AUDIT_STATE" = "stale" ] && echo true || echo false)" \
  '{"check": "check-arch-audit-staleness.sh"}' \
  "STALE: arch audit not run in >=30 days; MILD: 15-29 days; FRESH: <15 days")"

BUG_SWEEP_SIGNAL="$(build_routine_signal "bug-sweep" "$BUG_SWEEP_STATE" "$BUG_SWEEP_OVERDUE" \
  "$(jq -cn --argjson c "$BUG_SWEEP_COMMITS" '{commits_since_bug_sweep: $c}')" \
  "STALE: >15 commits since last bug-sweep; MILD: 1-15 commits; FRESH: 0 commits")"

DORMANT_SIGNAL="$(build_routine_signal "dormant-repo" "$DORMANT_STATE" "false" \
  '{"note": "cross-repo commit scan requires tc-4 connector; emitting unknown from tc-3"}' \
  "STALE: sibling repo with no commits in >=30 days; tc-3 emits unknown without REST access")"

DISTILL_SIGNAL="$(build_routine_signal "distill-backlog" "$DISTILL_STATE" "$DISTILL_OVERDUE" \
  "$(jq -cn --argjson pc "$DISTILL_PENDING" '{pending_count: $pc}' )" \
  "fresh (pending=0), mild (pending 1-5), stale (pending >= 6), unknown (archive empty or unreadable)")"

ROUTINE_SIGNALS_ARRAY="$(jq -s '.' \
  <(echo "$WEEKLY_SIGNAL") \
  <(echo "$DOCS_SIGNAL") \
  <(echo "$ARCH_SIGNAL") \
  <(echo "$BUG_SWEEP_SIGNAL") \
  <(echo "$DORMANT_SIGNAL") \
  <(echo "$DISTILL_SIGNAL"))"

# Validate routine signals
echo "[emit] validating routine signals..." >&2
RS_COUNT="$(echo "$ROUTINE_SIGNALS_ARRAY" | jq 'length')"
if [[ "$RS_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((RS_COUNT - 1))); do
  rec="$(echo "$ROUTINE_SIGNALS_ARRAY" | jq -c ".[$i]")"
  validate_main_record "routine-signal" "$rec" "index $i"
done
fi

# ===========================================================================
# SECTION 5 — Completion Rollup (WeekRollup + DayRollup)
# Source: query-completions.sh --since 30d --format json
# Dedup on chain grain; null chains are distinct atoms
# loe.* nesting for opus_dispatches/tshirt
# commit filter: /^[0-9a-f]{7,40}$/
# ===========================================================================
echo "[emit] building completion rollup..." >&2

COMPLETIONS_JSON="$(bash "$COORDINATOR_ROOT/bin/query-completions.sh" --since 30d --format json 2>/dev/null || echo "[]")"
COMPLETIONS_COUNT="$(echo "$COMPLETIONS_JSON" | jq 'length')"

# Compute rollup facts using jq
# We need to dedup on chain (null chains are distinct atoms — each is its own chain)
# Use a running ID for null chains to keep them distinct
ROLLUP_FACTS="$(echo "$COMPLETIONS_JSON" | jq '
  # Assign each entry a dedup key: chain slug if non-null, else __null_<index>
  to_entries |
  map(
    .value as $v |
    .key as $idx |
    ($v.frontmatter.chain) as $chain |
    {
      chain_key: (if $chain == null then ("__null_\($idx)") else $chain end),
      fm: $v.frontmatter,
      path: $v.path
    }
  ) |
  # Dedup: keep only the first occurrence of each chain_key
  group_by(.chain_key) |
  map(.[0]) |
  # Aggregate
  {
    chains_completed: (map(select(.chain_key | startswith("__null_") | not)) | map(.chain_key) | unique | length),
    null_chains: (map(select(.chain_key | startswith("__null_"))) | length),
    tshirt_counts: (
      map(select(.fm.loe.tshirt != null) | .fm.loe.tshirt) |
      group_by(.) |
      map({key: .[0], value: (. | length)}) |
      from_entries
    ),
    opus_dispatches: (map((.fm.loe.opus_dispatches // 0) | numbers) | add // 0),
    commits: (
      map(.fm.commits // [] | map(tostring | select(test("^[0-9a-f]{7,40}$")))) |
      flatten |
      length
    ),
    source_count: length,
    max_chain_date: (map(.fm.created) | sort | last // "2026-01-01")
  }
')"

# Compute max_commit_sha (latest valid commit across all entries)
MAX_COMMIT_SHA="$(echo "$COMPLETIONS_JSON" | jq -r '
  [.[].frontmatter.commits // [] | .[] | tostring | select(test("^[0-9a-f]{7,40}$"))] |
  sort | last // "0000000"
')"

CHAINS_COMPLETED="$(echo "$ROLLUP_FACTS" | jq '.chains_completed')"
NULL_CHAINS="$(echo "$ROLLUP_FACTS" | jq '.null_chains')"
# Total unique chains_completed = named chains + null chains (each null is distinct)
TOTAL_CHAINS="$(echo "$ROLLUP_FACTS" | jq '.chains_completed + .null_chains')"
TSHIRT_COUNTS="$(echo "$ROLLUP_FACTS" | jq '.tshirt_counts')"
OPUS_DISPATCHES="$(echo "$ROLLUP_FACTS" | jq '.opus_dispatches')"
COMMITS_COUNT="$(echo "$ROLLUP_FACTS" | jq '.commits')"
SOURCE_COUNT="$(echo "$ROLLUP_FACTS" | jq '.source_count')"

# Determine freshness: current if source entries from today; stale otherwise
TODAY="$(date -u +%F)"
HAS_TODAY="$(echo "$COMPLETIONS_JSON" | jq --arg today "$TODAY" '[.[].frontmatter.created == $today] | any')"
ROLLUP_FRESHNESS="$([ "$HAS_TODAY" = "true" ] && echo "current" || echo "stale")"

# Current ISO week (YYYY-Www)
ISO_WEEK="$(date -u +%Y-W%V)"

# Build week review facts from review trail
WEEK_REVIEWS="$(echo "$REVIEW_TRAIL_ARRAY" | jq 'length')"
WEEK_VERDICTS="$(echo "$REVIEW_TRAIL_ARRAY" | jq '
  group_by(.verdict) |
  map({key: .[0].verdict, value: (. | length)}) |
  from_entries
')"

# Build WeekRollup record
WEEK_ROLLUP="$(jq -cn \
  --arg period "$ISO_WEEK" \
  --arg repo "$REPO_NAME" \
  --argjson chains "$TOTAL_CHAINS" \
  --argjson tshirt "$TSHIRT_COUNTS" \
  --argjson opus "$OPUS_DISPATCHES" \
  --argjson commits "$COMMITS_COUNT" \
  --argjson reviews "$WEEK_REVIEWS" \
  --argjson verdicts "$WEEK_VERDICTS" \
  --arg max_observed_at "$OBSERVED_AT" \
  --arg max_commit_sha "$MAX_COMMIT_SHA" \
  --argjson source_count "$SOURCE_COUNT" \
  --arg freshness "$ROLLUP_FRESHNESS" \
  --arg branch "$GIT_BRANCH" \
  --arg sha "$GIT_SHA" \
  --arg observed_at "$OBSERVED_AT" \
  '{
    grain: "week",
    period: $period,
    repo: $repo,
    coordinator_root_path: ".",
    deterministic_facts: {
      chains_completed: $chains,
      tshirt_counts: $tshirt,
      opus_dispatches: $opus,
      commits: $commits,
      reviews_conducted: $reviews,
      verdicts: $verdicts
    },
    narrative: null,
    input_watermark: {
      max_observed_at: $max_observed_at,
      max_commit_sha: $max_commit_sha,
      source_count: $source_count
    },
    freshness: $freshness,
    provenance: {
      source_kind: "coordinator_artifact",
      repo: $repo,
      ref: { branch: $branch, sha: $sha },
      path: "archive/completed",
      observed_at: $observed_at,
      derivation: "rolled_up"
    }
  }')"

# Build DayRollup record
TODAY_COMPLETIONS="$(echo "$COMPLETIONS_JSON" | jq --arg today "$TODAY" '
  [.[] | select(.frontmatter.created == $today)]
')"
TODAY_SOURCE_COUNT="$(echo "$TODAY_COMPLETIONS" | jq 'length')"
TODAY_CHAINS="$(echo "$TODAY_COMPLETIONS" | jq '
  [.[].frontmatter.chain // null] |
  to_entries |
  map(
    .key as $idx |
    .value as $chain |
    if $chain == null then ("__null_\($idx)") else $chain end
  ) |
  unique | length
')"
TODAY_TSHIRT="$(echo "$TODAY_COMPLETIONS" | jq '
  [.[].frontmatter.loe.tshirt // null | select(. != null)] |
  group_by(.) |
  map({key: .[0], value: (. | length)}) |
  from_entries
')"
TODAY_OPUS="$(echo "$TODAY_COMPLETIONS" | jq '[.[].frontmatter.loe.opus_dispatches // 0 | numbers] | add // 0')"
TODAY_COMMITS="$(echo "$TODAY_COMPLETIONS" | jq '
  [.[].frontmatter.commits // [] | .[] | tostring | select(test("^[0-9a-f]{7,40}$"))] | length
')"
TODAY_FRESHNESS="$([ "$TODAY_SOURCE_COUNT" -gt 0 ] && echo "current" || echo "stale")"

DAY_ROLLUP="$(jq -cn \
  --arg period "$TODAY" \
  --arg repo "$REPO_NAME" \
  --argjson chains "$TODAY_CHAINS" \
  --argjson tshirt "$TODAY_TSHIRT" \
  --argjson opus "$TODAY_OPUS" \
  --argjson commits "$TODAY_COMMITS" \
  --arg max_observed_at "$OBSERVED_AT" \
  --arg max_commit_sha "$MAX_COMMIT_SHA" \
  --argjson source_count "$TODAY_SOURCE_COUNT" \
  --arg freshness "$TODAY_FRESHNESS" \
  --arg branch "$GIT_BRANCH" \
  --arg sha "$GIT_SHA" \
  --arg observed_at "$OBSERVED_AT" \
  '{
    grain: "day",
    period: $period,
    repo: $repo,
    coordinator_root_path: ".",
    deterministic_facts: {
      chains_completed: $chains,
      tshirt_counts: $tshirt,
      opus_dispatches: $opus,
      commits: $commits
    },
    narrative: null,
    input_watermark: {
      max_observed_at: $max_observed_at,
      max_commit_sha: $max_commit_sha,
      source_count: $source_count
    },
    freshness: $freshness,
    provenance: {
      source_kind: "coordinator_artifact",
      repo: $repo,
      ref: { branch: $branch, sha: $sha },
      path: "archive/completed",
      observed_at: $observed_at,
      derivation: "rolled_up"
    }
  }')"

# Validate rollups
echo "[emit] validating rollups..." >&2
validate_main_record "week-rollup" "$WEEK_ROLLUP" "week rollup"
validate_main_record "day-rollup" "$DAY_ROLLUP" "day rollup"

# ===========================================================================
# SECTION 6 — Goals (from state/goals-log.jsonl)
# Derive current = latest per (repo, root, period, period_value)
# Inject provenance at emit time
# ===========================================================================
echo "[emit] collecting goals..." >&2

# Per-machine append-only logs (goals-log.<machine>.jsonl); concat all, latest-wins across machines (P1-D6).
GOALS_ARRAY="[]"
# Review: B-F2 — use explicit template (consistent with other mktemp calls; aids /tmp identification)
GOALS_TMP="$(mktemp "${TMPDIR:-/tmp}/cockpit-goals.XXXXXX")"
for _gl in "$ROOT"/state/goals-log.*.jsonl; do
  [[ -e "$_gl" ]] || continue
  cat "$_gl" >> "$GOALS_TMP"
done

if [[ -s "$GOALS_TMP" ]]; then
  # Read JSONL, group by (repo, coordinator_root_path, period, period_value), keep latest
  GOALS_ARRAY="$(
    # Parse all lines, group and deduplicate
    python3 - "$GOALS_TMP" "$OBSERVED_AT" "$GIT_BRANCH" "$GIT_SHA" "$REPO_NAME" <<'PYEOF' # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
import json
import sys

goals_log = sys.argv[1]
observed_at = sys.argv[2]
git_branch = sys.argv[3]
git_sha = sys.argv[4]
repo_name = sys.argv[5]

latest = {}
with open(goals_log) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (
            record.get("repo", repo_name),
            record.get("coordinator_root_path", "."),
            record.get("period", ""),
            record.get("period_value", "")
        )
        # Keep latest by declared_at
        if key not in latest or record.get("declared_at", "") > latest[key].get("declared_at", ""):
            latest[key] = record

results = []
for record in latest.values():
    # Determine derivation from period type.
    # Review: B-F5 — weekly goals are PM-declared (parsed from HEADER); daily/other goals are
    # synthesized from activity (rolled_up). Per plan Decision 4/F10.
    period = record.get("period", "")
    if period == "week":
        derivation = "parsed"
    else:
        derivation = "rolled_up"

    goal_record = {
        "goal_id": record.get("goal_id", ""),
        "repo": record.get("repo", repo_name),
        "coordinator_root_path": record.get("coordinator_root_path", "."),
        "period": period,
        "period_value": record.get("period_value", ""),
        "declared_by_machine": record.get("declared_by_machine", "unknown"),
        "declared_at": record.get("declared_at", observed_at),
        "text": record.get("text", ""),
        "status": record.get("status", "active"),
        "provenance": {
            "source_kind": "coordinator_artifact",
            "repo": repo_name,
            "ref": {"branch": git_branch, "sha": git_sha},
            "path": "state/goals-log.*.jsonl",
            "observed_at": observed_at,
            "derivation": derivation
        }
    }
    results.append(goal_record)

print(json.dumps(results))
PYEOF
  )"
fi
rm -f "$GOALS_TMP"

# Validate goal records
echo "[emit] validating goals..." >&2
GOALS_COUNT="$(echo "$GOALS_ARRAY" | jq 'length')"
if [[ "$GOALS_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((GOALS_COUNT - 1))); do
  rec="$(echo "$GOALS_ARRAY" | jq -c ".[$i]")"
  validate_main_record "goal" "$rec" "index $i"
done
fi

# ===========================================================================
# SECTION 7 — CoordinatorRoots (fleet array, element [0] = local meta-repo)
# Source: gh repo view for metadata; git log for last_activity_at
# Review: B-F7 — derivation: "parsed" (not "raw"): gh repo view --json returns processed
# CLI JSON, not raw GraphQL wire; source_kind "github_graphql" remains accurate.
# ===========================================================================
echo "[emit] collecting coordinator roots..." >&2

# Accumulated malformed items (JSON array) — grows if gh fails per-repo
CR_MALFORMED_ITEMS="[]"

# ---------------------------------------------------------------------------
# Element [0]: local meta-repo (dbc-oduffy/.claude-prime) — MANDATORY
# Always present even if gh is unavailable; machine field required by schema.
# ---------------------------------------------------------------------------
GH_REPO_JSON="$(gh repo view "dbc-oduffy/.claude-prime" --json "visibility,isArchived,isFork,defaultBranchRef,pushedAt" 2>/dev/null || echo "")"
CR_LAST_ACTIVITY="$(git -C "$ROOT" log -1 --format="%cI" HEAD 2>/dev/null || echo "$OBSERVED_AT")"

if [[ -n "$GH_REPO_JSON" ]]; then
  CR_VISIBILITY="$(echo "$GH_REPO_JSON" | jq -r '.visibility')"
  CR_ARCHIVED="$(echo "$GH_REPO_JSON" | jq '.isArchived')"
  CR_IS_FORK="$(echo "$GH_REPO_JSON" | jq '.isFork')"
  CR_DEFAULT_BRANCH="$(echo "$GH_REPO_JSON" | jq -r '.defaultBranchRef.name')"

  LOCAL_ROOT_RECORD="$(jq -cn \
    --arg repo "$REPO_NAME" \
    --arg machine "$HOSTNAME_VAL" \
    --arg visibility "$CR_VISIBILITY" \
    --argjson archived "$CR_ARCHIVED" \
    --argjson is_fork "$CR_IS_FORK" \
    --arg default_branch "$CR_DEFAULT_BRANCH" \
    --arg last_activity_at "$CR_LAST_ACTIVITY" \
    --arg branch "$GIT_BRANCH" \
    --arg sha "$GIT_SHA" \
    --arg observed_at "$OBSERVED_AT" \
    '{
      repo: $repo,
      # Review: F6 — derive owner from slug split rather than hardcoding "dbc-oduffy".
      owner: ($repo | split("/")[0]),
      coordinator_root_path: ".",
      machine: $machine,
      visibility: $visibility,
      archived: $archived,
      is_fork: $is_fork,
      default_branch: $default_branch,
      last_activity_at: $last_activity_at,
      open_pr_count: null,
      provenance: {
        source_kind: "github_graphql",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: "",
        observed_at: $observed_at,
        derivation: "parsed"
      }
    }')"
else
  echo "[emit] gh unavailable for .claude-prime — building fallback local root (git-only)" >&2
  CR_MALFORMED_ITEMS="$(echo "$CR_MALFORMED_ITEMS" | jq -c '. + [{"reason":"gh repo view failed or gh unavailable","path":"dbc-oduffy/.claude-prime"}]')"
  LOCAL_ROOT_RECORD="$(jq -cn \
    --arg repo "$REPO_NAME" \
    --arg machine "$HOSTNAME_VAL" \
    --arg last_activity_at "$CR_LAST_ACTIVITY" \
    --arg branch "$GIT_BRANCH" \
    --arg sha "$GIT_SHA" \
    --arg observed_at "$OBSERVED_AT" \
    '{
      repo: $repo,
      # Review: F6 — derive owner from slug split rather than hardcoding "dbc-oduffy".
      owner: ($repo | split("/")[0]),
      coordinator_root_path: ".",
      machine: $machine,
      visibility: "PRIVATE",
      archived: false,
      is_fork: false,
      default_branch: "main",
      last_activity_at: $last_activity_at,
      open_pr_count: null,
      provenance: {
        source_kind: "local_fs",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: "",
        observed_at: $observed_at,
        derivation: "parsed"
      }
    }')"
fi
validate_main_record "coordinator-root" "$LOCAL_ROOT_RECORD" "index 0 (local meta-repo)"
COORDINATOR_ROOTS_ARRAY="$(jq -cn --argjson local_root "$LOCAL_ROOT_RECORD" '[$local_root]')"

# ---------------------------------------------------------------------------
# Fleet iteration: working-repos.yaml (render ALL — no visibility filter)
# PM decision 2026-06-26: visibility is a DISPLAY field, not a filter.
# gh repo view works for repos not on disk — queries GitHub directly.
# ---------------------------------------------------------------------------
WORKING_REPOS_YAML="$ROOT/working-repos.yaml"
if [[ -f "$WORKING_REPOS_YAML" ]]; then
  echo "[emit] iterating fleet repos from working-repos.yaml..." >&2
  FLEET_IDX=1
  while IFS= read -r FLEET_SLUG; do
    [[ -z "$FLEET_SLUG" ]] && continue
    echo "[emit]   fleet repo[$FLEET_IDX]: $FLEET_SLUG" >&2
    FLEET_GH_JSON="$(gh repo view "$FLEET_SLUG" --json "visibility,isArchived,isFork,defaultBranchRef,pushedAt" 2>/dev/null || echo "")"
    if [[ -n "$FLEET_GH_JSON" ]]; then
      F_VISIBILITY="$(echo "$FLEET_GH_JSON" | jq -r '.visibility')"
      F_ARCHIVED="$(echo "$FLEET_GH_JSON" | jq '.isArchived')"
      F_IS_FORK="$(echo "$FLEET_GH_JSON" | jq '.isFork')"
      F_DEFAULT_BRANCH="$(echo "$FLEET_GH_JSON" | jq -r '.defaultBranchRef.name // "main"')"
      # last_activity_at: pushedAt → OBSERVED_AT
      # Review: F1 — defaultBranchRef.target (committedDate) is not a subobject returned by
      # the gh json fields requested above; F_COMMITTED_DATE was always empty. Use pushedAt directly.
      F_PUSHED_AT="$(echo "$FLEET_GH_JSON" | jq -r '(.pushedAt // "") | select(. != "")' 2>/dev/null || echo "")"
      if [[ -n "$F_PUSHED_AT" ]]; then
        F_LAST_ACTIVITY="$F_PUSHED_AT"
      else
        F_LAST_ACTIVITY="$OBSERVED_AT"
      fi
      FLEET_RECORD="$(jq -cn \
        --arg repo "$FLEET_SLUG" \
        --arg machine "$HOSTNAME_VAL" \
        --arg visibility "$F_VISIBILITY" \
        --argjson archived "$F_ARCHIVED" \
        --argjson is_fork "$F_IS_FORK" \
        --arg default_branch "$F_DEFAULT_BRANCH" \
        --arg last_activity_at "$F_LAST_ACTIVITY" \
        --arg branch "$GIT_BRANCH" \
        --arg sha "$GIT_SHA" \
        --arg observed_at "$OBSERVED_AT" \
        '{
          repo: $repo,
          # Review: F6 — derive owner from slug split rather than hardcoding "dbc-oduffy".
          owner: ($repo | split("/")[0]),
          coordinator_root_path: ".",
          machine: $machine,
          visibility: $visibility,
          archived: $archived,
          is_fork: $is_fork,
          default_branch: $default_branch,
          last_activity_at: $last_activity_at,
          open_pr_count: null,
          provenance: {
            source_kind: "github_graphql",
            repo: $repo,
            ref: { branch: $branch, sha: $sha },
            path: "",
            observed_at: $observed_at,
            derivation: "parsed"
          }
        }')"
      validate_main_record "coordinator-root" "$FLEET_RECORD" "index $FLEET_IDX ($FLEET_SLUG)"
      COORDINATOR_ROOTS_ARRAY="$(echo "$COORDINATOR_ROOTS_ARRAY" | jq -c --argjson rec "$FLEET_RECORD" '. + [$rec]')"
      FLEET_IDX=$((FLEET_IDX + 1))
    else
      echo "[emit]   gh unavailable for $FLEET_SLUG — skipping to malformed" >&2
      CR_MALFORMED_ITEMS="$(echo "$CR_MALFORMED_ITEMS" | jq -c --arg slug "$FLEET_SLUG" '. + [{"reason":"gh repo view failed or gh unavailable","path":$slug}]')"
    fi
  done < <(awk '/^repos:/{found=1; next} /^out_of_tree:/{found=0} found && /github:/{gsub(/^[[:space:]]*github:[[:space:]]*/, ""); gsub(/#.*$/, ""); gsub(/[[:space:]]*$/, ""); print}' "$WORKING_REPOS_YAML")
else
  echo "[emit] working-repos.yaml not found at $WORKING_REPOS_YAML — fleet iteration skipped" >&2
fi

# ===========================================================================
# SECTION 8 — Branch
# Source: git for branch metadata; compare-derived fields → null (D9)
# ===========================================================================
echo "[emit] collecting branch..." >&2

GIT_LAST_COMMIT_AT="$(git -C "$ROOT" log -1 --format="%cI" HEAD 2>/dev/null || echo "$OBSERVED_AT")"
GIT_LAST_COMMIT_MSG="$(git -C "$ROOT" log -1 --format="%s" HEAD 2>/dev/null || echo "")"

# Parse machine_hint and date_hint from branch name work/<machine>/<date>
# Review: F3 — store raw captures and pass via --arg; use null-conditional in jq to preserve
# null-emission semantics on no-match. Manual quote-wrapping ("\"...\"" + --argjson) breaks
# if the branch name contains " or \ (malformed JSON aborts under set -euo pipefail).
BRANCH_MACHINE_HINT=""
BRANCH_DATE_HINT=""
if [[ "$GIT_BRANCH" =~ ^work/([^/]+)/(.+)$ ]]; then
  BRANCH_MACHINE_HINT="${BASH_REMATCH[1]}"
  BRANCH_DATE_HINT="${BASH_REMATCH[2]}"
fi

BRANCH_RECORD="$(jq -cn \
  --arg repo "$REPO_NAME" \
  --arg name "$GIT_BRANCH" \
  --arg tip_sha "$GIT_SHA" \
  --arg last_commit_at "$GIT_LAST_COMMIT_AT" \
  --arg last_commit_message "$GIT_LAST_COMMIT_MSG" \
  --arg machine_hint "$BRANCH_MACHINE_HINT" \
  --arg date_hint "$BRANCH_DATE_HINT" \
  --arg branch "$GIT_BRANCH" \
  --arg sha "$GIT_SHA" \
  --arg observed_at "$OBSERVED_AT" \
  '{
    repo: $repo,
    owner: "dbc-oduffy",
    coordinator_root_path: ".",
    name: $name,
    tip_sha: $tip_sha,
    merge_base_sha: null,
    ahead_by: null,
    behind_by: null,
    last_commit_at: $last_commit_at,
    last_commit_message: $last_commit_message,
    machine_hint: (if $machine_hint == "" then null else $machine_hint end),
    date_hint: (if $date_hint == "" then null else $date_hint end),
    provenance: {
      source_kind: "local_fs",
      repo: $repo,
      ref: { branch: $branch, sha: $sha },
      path: "",
      observed_at: $observed_at,
      derivation: "parsed"
    }
  }')"

validate_main_record "branch" "$BRANCH_RECORD" "branch"

# ===========================================================================
# SECTION 8.5 — LessonSummary records
# Sources: {state/lessons.md} ∪ {state/lessons-outbox/*.yaml} ∪ {state/lessons-outbox/drained/*.yaml}
# Union-dedup on lesson_key (first 16 hex chars of sha256(normalize(title))).
# promotion_state precedence (C-F3): drained > pending > captured.
# A lesson present ONLY in drained/ is still emitted — full outer join, not left-join.
# parse_status="partial" entries are emitted (degraded-but-counted), not quarantined.
# Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C3
# ===========================================================================
echo "[emit] collecting lessons..." >&2

LESSONS_ARRAY="$(python3 "$COORDINATOR_ROOT/bin/lib/emit-lesson-summaries.py" \
  "$ROOT" "$REPO_NAME" "$GIT_BRANCH" "$GIT_SHA" "$OBSERVED_AT" \
  2>/dev/null || echo "[]")"

# Validate each lesson record (lesson-summary entity)
LESSON_COUNT="$(echo "$LESSONS_ARRAY" | jq 'length')"
if [[ "$LESSON_COUNT" -gt 0 ]]; then
  for i in $(seq 0 $((LESSON_COUNT - 1))); do
    rec="$(echo "$LESSONS_ARRAY" | jq -c ".[$i]")"
    validate_main_record "lesson-summary" "$rec" "index $i"
  done
fi

# ===========================================================================
# SECTION 8.6 — PlanSummary records
# Sources: query-records.js --type plan (sidecar-free via the C4a producer-side
# denylist — review sidecars never reach this consumer).
# Composite natural key: (repo, coordinator_root_path, path).
# created truncated to date-only (schema IsoDate rejects a full datetime).
# author emitted verbatim from frontmatter (no git-blame inference — C-F6).
# status validated against the 8-value PlanStatus enum; non-conforming or
# missing-required-field rows quarantine to malformed_records.plans (handoffs
# section is the template — quarantine, do not silent-drop).
# Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C4b
# ===========================================================================
echo "[emit] collecting plans..." >&2

PLANS_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type plan --limit 0 --format json 2>/dev/null || echo "[]")"

PLANS_ARRAY="$(echo "$PLANS_JSON" | jq -c --arg repo "$REPO_NAME" --arg observed_at "$OBSERVED_AT" --arg branch "$GIT_BRANCH" --arg sha "$GIT_SHA" '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    ($rec.path) as $p |
    # Required fields present + status within the frozen 8-value PlanStatus enum
    select(
      ($fm.title | type) == "string" and
      ($fm.created | type) == "string" and
      ($fm.author | type) == "string" and
      ($fm.status | type) == "string" and
      ($fm.status | . == "draft" or . == "reviewed" or . == "approved" or . == "executing" or . == "implemented" or . == "deferred" or . == "abandoned" or . == "superseded")
    ) |
    {
      repo: $repo,
      coordinator_root_path: ".",
      path: $p,
      title: $fm.title,
      # IsoDate (YYYY-MM-DD): truncate any IsoDateTime to date-only before emit.
      created: ($fm.created | .[0:10]),
      author: $fm.author,
      status: $fm.status,
      scope_mode: ($fm.scope_mode // null),
      reviewer: ($fm.reviewer // null),
      branch: ($fm.branch // null),
      superseded_by: ($fm.superseded_by // null),
      # Review: code-reviewer — source maps roadmap_id for roadmap-sourced plans (schema source field is free-text)
      source: ($fm.source // $fm.roadmap_id // null),
      provenance: {
        source_kind: "local_fs",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: $p,
        observed_at: $observed_at,
        derivation: "parsed"
      }
    }
  ]
' || echo "[]")"

# Quarantine: missing required field OR status outside the PlanStatus enum.
# Review: code-reviewer — guarded with || echo "[]" to match PLANS_JSON/BUG_RECORDS/DEBT_RECORDS pattern (F2)
MALFORMED_PLANS="$(echo "$PLANS_JSON" | jq -c '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    select(
      (($fm.title | type) != "string") or
      (($fm.created | type) != "string") or
      (($fm.author | type) != "string") or
      (($fm.status | type) != "string") or
      (($fm.status | . != "draft" and . != "reviewed" and . != "approved" and . != "executing" and . != "implemented" and . != "deferred" and . != "abandoned" and . != "superseded"))
    ) |
    {
      path: $rec.path,
      reason: "missing required field (title/created/author/status) or status outside PlanStatus enum",
      frontmatter_keys: ($fm | keys)
    }
  ]
' || echo "[]")"

# Validate all plan records
echo "[emit] validating plans..." >&2
PLAN_COUNT="$(echo "$PLANS_ARRAY" | jq 'length')"
if [[ "$PLAN_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((PLAN_COUNT - 1))); do
  rec="$(echo "$PLANS_ARRAY" | jq -c ".[$i]")"
  validate_main_record "plan-summary" "$rec" "index $i"
done
fi

# ===========================================================================
# SECTION 8.7 — CrossRepoMemoSummary records
# Sources: query-records.js --type cross-repo-memo (reads cross-repo/inbox/*.md).
# Actionable inbox set only — archived memos are not emitted.
# Required fields (all 10): repo, coordinator_root_path, title, from, to,
#   status, created, kind, related, provenance.
# status enum: open | in_progress | actioned (cross-repo-memo-summary.schema.json).
# kind enum:   ask | consult | fyi  (default: "ask" per memo doctrine).
# related:     empty array when frontmatter key is absent (schema requires array).
# HARD CONSTRAINT: metadata only — NO body text, no summary/decision_note fields.
# Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C9b
# ===========================================================================
echo "[emit] collecting cross-repo memos..." >&2

CROSS_REPO_MEMOS_JSON="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type cross-repo-memo --limit 0 --format json 2>/dev/null || echo "[]")"

CROSS_REPO_MEMOS_ARRAY="$(echo "$CROSS_REPO_MEMOS_JSON" | jq -c \
  --arg repo "$REPO_NAME" \
  --arg observed_at "$OBSERVED_AT" \
  --arg branch "$GIT_BRANCH" \
  --arg sha "$GIT_SHA" '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    ($rec.path) as $p |
    # Require all 10 fields the schema marks required; status and kind must be within enum
    select(
      ($fm.title | type) == "string" and
      ($fm.from  | type) == "string" and
      ($fm.to    | type) == "string" and
      ($fm.status | type) == "string" and
      ($fm.status | . == "open" or . == "in_progress" or . == "actioned") and
      ($fm.created | type) == "string" and
      (($fm.kind // "ask") | . == "ask" or . == "consult" or . == "fyi")
    ) |
    {
      repo: $repo,
      coordinator_root_path: ".",
      title: $fm.title,
      from: $fm.from,
      to: $fm.to,
      status: $fm.status,
      created: ($fm.created | .[0:10]),
      kind: ($fm.kind // "ask"),
      related: ($fm.related // []),
      provenance: {
        source_kind: "local_fs",
        repo: $repo,
        ref: { branch: $branch, sha: $sha },
        path: $p,
        observed_at: $observed_at,
        derivation: "parsed"
      }
    }
  ]
' || echo "[]")"

# Review: F2 — build malformed quarantine for memos mirroring the MALFORMED_HANDOFFS pattern.
# Records that fail the validity select() above are captured here with a {path, reason} shape.
MALFORMED_CROSS_REPO_MEMOS="$(echo "$CROSS_REPO_MEMOS_JSON" | jq -c \
  --arg repo "$REPO_NAME" '
  [
    .[] | . as $rec |
    ($rec.frontmatter) as $fm |
    select(
      (($fm.title | type) != "string") or
      (($fm.from  | type) != "string") or
      (($fm.to    | type) != "string") or
      (($fm.status | type) != "string") or
      (($fm.status | . != "open" and . != "in_progress" and . != "actioned")) or
      (($fm.created | type) != "string") or
      ((($fm.kind // "ask") | . != "ask" and . != "consult" and . != "fyi"))
    ) |
    {
      path: $rec.path,
      reason: "missing required field or invalid status/kind enum"
    }
  ]
' || echo "[]")"

# Validate each memo record against cross-repo-memo-summary schema
echo "[emit] validating cross-repo memos..." >&2
MEMO_COUNT="$(echo "$CROSS_REPO_MEMOS_ARRAY" | jq 'length')"
if [[ "$MEMO_COUNT" -gt 0 ]]; then
  for i in $(seq 0 $((MEMO_COUNT - 1))); do
    rec="$(echo "$CROSS_REPO_MEMOS_ARRAY" | jq -c ".[$i]")"
    validate_main_record "cross-repo-memo-summary" "$rec" "index $i"
  done
fi

# ===========================================================================
# SECTION 9 — Compose final envelope
# ===========================================================================
echo "[emit] composing envelope..." >&2

EMITTED_AT="$(date -u +%FT%TZ)"

# ---------------------------------------------------------------------------
# Source schema_version from the canonical contract bundle (the Staff Engineer F1).
# Reads the top-level .version field from the emitted JSON Schema bundle so
# schema_version in the output can never desync from CONTRACT_VERSION.
# Spec backlink: state/handoffs/2026-06-22_230001_roadmap-cockpit-contract-ext-2026-06-22-tc-1.md
# Negative-spec: do NOT hardcode the version string here — that is what this
# block replaces.
# ---------------------------------------------------------------------------
CONTRACT_SCHEMA_BUNDLE="$COORDINATOR_ROOT/cockpit-contract/schema/cockpit-contract.schema.json"
if [[ ! -f "$CONTRACT_SCHEMA_BUNDLE" ]]; then
  echo "ERROR: contract schema bundle not found: $CONTRACT_SCHEMA_BUNDLE" >&2
  echo "Run: cd $COORDINATOR_ROOT/cockpit-contract && pnpm run emit-schema" >&2
  exit 1
fi
SCHEMA_VERSION="$(jq -r '.version // empty' "$CONTRACT_SCHEMA_BUNDLE")"
if [[ -z "$SCHEMA_VERSION" ]]; then
  echo "ERROR: .version field missing or empty in $CONTRACT_SCHEMA_BUNDLE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# C11(a) producer-half migration gate — fail loud on contract-bundle desync.
# Source of truth for the version is CONTRACT_VERSION in src/index.ts; the
# emitted schema bundle is generated FROM it via `pnpm run emit`. If the two
# disagree, the bundle is stale (someone bumped CONTRACT_VERSION but did not
# re-emit) and we would publish a schema_version that does not match the
# entity shapes — the exact silent-break DSR-2026-06-23-4 names. Abort rather
# than emit a mismatched snapshot. Spec: docs/plans/2026-06-24-opticon-cockpit-contract-reshape.md § C11(a).
# ---------------------------------------------------------------------------
CONTRACT_SRC_INDEX="$COORDINATOR_ROOT/cockpit-contract/src/index.ts"
if [[ -f "$CONTRACT_SRC_INDEX" ]]; then
  # Review: F4 — widen grep to tolerate type annotations (e.g. `CONTRACT_VERSION: string = "2.0"`);
  # split condition so an empty extraction emits a non-fatal WARN rather than silently skipping
  # the DSR-2026-06-23-4 desync guard entirely.
  SRC_CONTRACT_VERSION="$(grep -oE 'CONTRACT_VERSION[^=]*= "[^"]+"' "$CONTRACT_SRC_INDEX" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
  if [[ -z "$SRC_CONTRACT_VERSION" ]]; then
    echo "WARN: could not extract CONTRACT_VERSION from $CONTRACT_SRC_INDEX — desync guard skipped" >&2
  elif [[ "$SRC_CONTRACT_VERSION" != "$SCHEMA_VERSION" ]]; then
    echo "ERROR: cockpit-contract version desync — src/index.ts CONTRACT_VERSION=$SRC_CONTRACT_VERSION but emitted schema bundle .version=$SCHEMA_VERSION." >&2
    echo "The schema bundle is stale. Run: cd $COORDINATOR_ROOT/cockpit-contract && pnpm run emit" >&2
    echo "Refusing to emit a snapshot whose schema_version does not match the contract source (DSR-2026-06-23-4 silent-break guard)." >&2
    exit 1
  fi
fi

# Build malformed_records
MALFORMED_CR_ARRAY="$CR_MALFORMED_ITEMS"

FINAL_JSON="$(jq -cn \
  --arg schema_version "$SCHEMA_VERSION" \
  --arg emitted_at "$EMITTED_AT" \
  --arg emitted_by_machine "$HOSTNAME_VAL" \
  --argjson coordinator_roots "$COORDINATOR_ROOTS_ARRAY" \
  --argjson handoffs "$HANDOFFS_ARRAY" \
  --argjson week_rollup "$WEEK_ROLLUP" \
  --argjson day_rollup "$DAY_ROLLUP" \
  --argjson backlogs_bug "$(echo "$ALL_BACKLOGS" | jq '[.[] | select(.type == "bug")]')" \
  --argjson backlogs_debt "$(echo "$ALL_BACKLOGS" | jq '[.[] | select(.type == "debt")]')" \
  --argjson backlogs_improvement "$(echo "$ALL_BACKLOGS" | jq '[.[] | select(.type == "improvement")]')" \
  --argjson review_trail "$REVIEW_TRAIL_ARRAY" \
  --argjson routine_signals "$ROUTINE_SIGNALS_ARRAY" \
  --argjson goals_current "$GOALS_ARRAY" \
  --argjson malformed_handoffs "$MALFORMED_HANDOFFS" \
  --argjson malformed_backlogs "$MALFORMED_BACKLOGS" \
  --argjson malformed_review_trail "$MALFORMED_REVIEW_TRAIL" \
  --argjson malformed_coordinator_root "$MALFORMED_CR_ARRAY" \
  --argjson branch "$BRANCH_RECORD" \
  --argjson lessons "$LESSONS_ARRAY" \
  --argjson plans "$PLANS_ARRAY" \
  --argjson malformed_plans "$MALFORMED_PLANS" \
  --argjson malformed_lessons "[]" \
  --argjson malformed_cross_repo_memos "$MALFORMED_CROSS_REPO_MEMOS" \
  --argjson cross_repo_memos "$CROSS_REPO_MEMOS_ARRAY" \
  '{
    schema_version: $schema_version,
    emitted_at: $emitted_at,
    emitted_by_machine: $emitted_by_machine,
    coordinator_roots: $coordinator_roots,
    branches: (if $branch == null then [] else [$branch] end),
    handoffs: $handoffs,
    completion_rollups: {
      day: (if $day_rollup == null then [] else [$day_rollup] end),
      week: (if $week_rollup == null then [] else [$week_rollup] end)
    },
    backlogs: {
      bug: $backlogs_bug,
      debt: $backlogs_debt,
      improvement: $backlogs_improvement
    },
    review_trail: $review_trail,
    routine_signals: $routine_signals,
    goals_current: $goals_current,
    lessons: $lessons,
    plans: $plans,
    cross_repo_memos: $cross_repo_memos,
    narrative_views: null,
    malformed_records: {
      handoffs: $malformed_handoffs,
      backlogs: $malformed_backlogs,
      review_trail: $malformed_review_trail,
      coordinator_roots: $malformed_coordinator_root,
      plans: $malformed_plans,
      lessons: $malformed_lessons,
      cross_repo_memos: $malformed_cross_repo_memos
    }
  }')"

# Write output
printf '%s\n' "$FINAL_JSON" | jq . > "$OUT_FILE"
echo "[emit] wrote $OUT_FILE" >&2

# Print summary
# Review: code-reviewer — include .malformed_records.plans so quarantined plans are counted in the total (F11)
MALFORMED_TOTAL="$(echo "$FINAL_JSON" | jq '
  .malformed_records.handoffs + .malformed_records.backlogs +
  .malformed_records.review_trail + .malformed_records.coordinator_roots +
  .malformed_records.plans + .malformed_records.lessons +
  .malformed_records.cross_repo_memos |
  length
')"

echo "=== Emission summary ===" >&2
echo "handoffs:        $(echo "$FINAL_JSON" | jq '.handoffs | length')" >&2
echo "backlogs_bug:    $(echo "$FINAL_JSON" | jq '.backlogs.bug | length')" >&2
echo "backlogs_debt:   $(echo "$FINAL_JSON" | jq '.backlogs.debt | length')" >&2
echo "backlogs_improv: $(echo "$FINAL_JSON" | jq '.backlogs.improvement | length')" >&2
echo "review_trail:    $(echo "$FINAL_JSON" | jq '.review_trail | length')" >&2
echo "routine_signals: $(echo "$FINAL_JSON" | jq '.routine_signals | length')" >&2
echo "goals_current:   $(echo "$FINAL_JSON" | jq '.goals_current | length')" >&2
echo "lessons:         $(echo "$FINAL_JSON" | jq '.lessons | length')" >&2
echo "plans:           $(echo "$FINAL_JSON" | jq '.plans | length')" >&2
# Review: F7 — add coordinator_roots, cross_repo_memos, branches to emission summary.
echo "coord_roots:     $(echo "$FINAL_JSON" | jq '.coordinator_roots | length')" >&2
echo "cross_repo_memos: $(echo "$FINAL_JSON" | jq '.cross_repo_memos | length')" >&2
echo "branches:        $(echo "$FINAL_JSON" | jq '.branches | length')" >&2
echo "malformed_total: $MALFORMED_TOTAL" >&2
echo "schema_version:  $(echo "$FINAL_JSON" | jq -r '.schema_version')" >&2
echo "========================" >&2
