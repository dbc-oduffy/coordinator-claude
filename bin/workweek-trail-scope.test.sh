#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# workweek-trail-scope.test.sh — regression net for lib/workweek-trail-scope.sh.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C1
#
# Pins the CURRENT behaviour (pre-extraction) so the C2 extraction refactor can
# be verified behaviour-preserving. Run against the unmodified script and expect
# all tests to be GREEN.
#
# Coverage:
#   T1  SAFE_RANGE validation — malformed sha_range is skipped with WARN
#   T2  JSON single-object record — sha_range commits land in reviewed_set (verified
#       by checking unreviewed_set excludes them)
#   T3  JSONL dual-shape record — parsed without error; its commits count as reviewed
#   T4  scope_kind=plan record — skipped silently (no WARN, no error)
#   T5  Cross-segment seam detection — two records touching a common file surface
#       that file in patrik_seam_files
#   T6  No-verdict-filter baseline — all diff records count regardless of verdict
#       field value (current behaviour pre-C2; the verdict filter is NOT applied yet)
#
# Usage: bash <this-file>
# Exit:  0 if all tests pass, non-zero on any failure.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../lib/workweek-trail-scope.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "ERROR: subject not found: $SUBJECT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pass/fail tally
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Temp-dir + cleanup
# ---------------------------------------------------------------------------
TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

STDERR_TMP="$TMPBASE/stderr"

# ---------------------------------------------------------------------------
# _make_fixture DIR  — build a git repo with a local-bare origin remote.
#
# Structure:
#   $DIR/origin.git  — bare repo acting as the "remote"
#   $DIR/repo        — working clone of origin
#
# After _make_fixture the caller can:
#   - add commits to $DIR/repo (they appear in origin/main..HEAD)
#   - write state/review-trail/*.json files under $DIR/repo
#   - write a HEADER.md under $DIR/repo
#   - run the subject with cwd=$DIR/repo
#
# NOTE: the bare repo starts with a root commit on "main" so that
# "origin/main" is a valid ref in the working tree at clone time.
# ---------------------------------------------------------------------------
_make_fixture() {
  local base="$1"

  # --- bare "origin" ---
  local origin_dir="$base/origin.git"
  mkdir -p "$origin_dir"
  git -C "$origin_dir" init -q --bare

  # Seed the bare repo with a root commit so origin/main exists.
  # We do this via a temp clone, commit, push, then discard the temp clone.
  local seed_dir="$base/seed"
  git clone -q "$origin_dir" "$seed_dir" 2>/dev/null
  git -C "$seed_dir" config user.email "test@test.local"
  git -C "$seed_dir" config user.name  "Test"
  # Ensure the branch is named "main" (git default changed across versions).
  git -C "$seed_dir" checkout -q -b main 2>/dev/null || git -C "$seed_dir" checkout -q main 2>/dev/null || true
  touch "$seed_dir/.gitkeep"
  git -C "$seed_dir" add -- .gitkeep
  git -C "$seed_dir" commit -q -m "root"
  git -C "$seed_dir" push -q origin main
  rm -rf "$seed_dir"

  # --- working clone ---
  local repo_dir="$base/repo"
  git clone -q "$origin_dir" "$repo_dir" 2>/dev/null
  git -C "$repo_dir" config user.email "test@test.local"
  git -C "$repo_dir" config user.name  "Test"
  # Ensure we are on "main" in the working clone.
  git -C "$repo_dir" checkout -q main 2>/dev/null || true

  # Create required directory layout under the repo.
  mkdir -p "$repo_dir/state/review-trail"
}

# Helper: add a commit to the fixture repo touching one or more files.
# Usage: _add_commit REPO_DIR FILE_PATH [FILE_PATH ...]
# Returns: the SHA of the new commit via stdout.
_add_commit() {
  local repo="$1"; shift
  local sha
  for f in "$@"; do
    local dir
    dir="$(dirname "$repo/$f")"
    mkdir -p "$dir"
    printf 'content of %s\n' "$f" >> "$repo/$f"
    git -C "$repo" add -- "$f"
  done
  git -C "$repo" commit -q -m "touch $*"
  sha=$(git -C "$repo" rev-parse HEAD)
  printf '%s' "$sha"
}

# Helper: run the subject script in a given repo directory.
# Sets RC, STDOUT_OUT, STDERR_OUT.
RC=0
STDOUT_OUT=""
STDERR_OUT=""

_run_subject() {
  local repo="$1"
  local header_file="$2"
  RC=0
  STDOUT_OUT=""
  STDERR_OUT=""
  STDOUT_OUT=$(cd "$repo" && HEADER_FILE="$header_file" CLAUDE_CODE_SESSION_ID="test-session-abcd1234" bash "$SUBJECT" 2>"$STDERR_TMP") || RC=$?
  STDERR_OUT=$(cat "$STDERR_TMP" 2>/dev/null || true)
}

# Variant of _run_subject that accepts an explicit session id (for
# concurrency tests that need to run the subject twice with distinct
# session ids against the same fixture) and optionally prepends a
# PATH override (used to force the %N-fallback branch via a stub `date`).
# Review: code-reviewer — F5: T8/T9 prove the concurrency-safety property
# (distinct shard files), not just the shard-naming format T1-T7 cover.
_run_subject_as() {
  local repo="$1"
  local header_file="$2"
  local session_id="$3"
  local path_prefix="${4:-}"
  RC=0
  STDOUT_OUT=""
  STDERR_OUT=""
  if [[ -n "$path_prefix" ]]; then
    STDOUT_OUT=$(cd "$repo" && HEADER_FILE="$header_file" CLAUDE_CODE_SESSION_ID="$session_id" PATH="$path_prefix:$PATH" bash "$SUBJECT" 2>"$STDERR_TMP") || RC=$?
  else
    STDOUT_OUT=$(cd "$repo" && HEADER_FILE="$header_file" CLAUDE_CODE_SESSION_ID="$session_id" bash "$SUBJECT" 2>"$STDERR_TMP") || RC=$?
  fi
  STDERR_OUT=$(cat "$STDERR_TMP" 2>/dev/null || true)
}

# Helper: count how many session-keyed scope shard files exist in a repo.
_count_scope_shards() {
  local repo="$1"
  local count=0
  local f
  for f in "$repo"/state/review-trail/.weekly-reviewer-scopes-*.json; do
    [[ -f "$f" ]] || continue
    count=$(( count + 1 ))
  done
  printf '%s' "$count"
}

# Helper: write a HEADER.md for the given week-start date.
_write_header() {
  local path="$1" week_start="$2"
  mkdir -p "$(dirname "$path")"
  printf '**Week starting:** %s\n' "$week_start" > "$path"
}

# Helper: return today's date in YYYY-MM-DD (BSD-portable, no date -d).
_today() {
  date -u +%Y-%m-%d
}

# Helper: locate the newest session-keyed scope shard written by the subject.
# Shard naming: state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
# (replaces the old singleton .weekly-reviewer-scopes.json — see
# coordinator/lib/workweek-trail-scope.sh header comment).
_latest_scope_shard() {
  local repo="$1"
  local newest=""
  local f
  for f in "$repo"/state/review-trail/.weekly-reviewer-scopes-*.json; do
    [[ -f "$f" ]] || continue
    if [[ -z "$newest" || "$f" -nt "$newest" ]]; then
      newest="$f"
    fi
  done
  printf '%s' "$newest"
}

# Helper: read the Staff Engineer array from the newest session-keyed scope shard.
# Usage: _read_patrik_shas REPO_DIR  → newline-separated SHAs on stdout
_read_patrik_shas() {
  local repo="$1"
  local scope_file
  scope_file=$(_latest_scope_shard "$repo")
  if [[ -z "$scope_file" || ! -f "$scope_file" ]]; then
    return 0
  fi
  # Use python3 (always available per test preamble) to extract the array.
  python3 - "$scope_file" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    obj = json.load(f)
for sha in obj.get("the Staff Engineer", []):
    print(sha)
PYEOF
}

# Helper: read patrik_seam_files from the newest session-keyed scope shard.
_read_seam_files() {
  local repo="$1"
  local scope_file
  scope_file=$(_latest_scope_shard "$repo")
  if [[ -z "$scope_file" || ! -f "$scope_file" ]]; then
    return 0
  fi
  python3 - "$scope_file" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    obj = json.load(f)
for p in obj.get("patrik_seam_files", []):
    print(p)
PYEOF
}

# ---------------------------------------------------------------------------
# T1 — SAFE_RANGE validation: malformed sha_range is skipped with a WARN.
# ---------------------------------------------------------------------------
T1="$TMPBASE/t1"
_make_fixture "$T1"

# Add a commit so origin/main..HEAD is non-empty.
sha_t1=$(_add_commit "$T1/repo" "src/thing.py")

# Write a trail record with an unsafe sha_range (leading dash = injection attempt).
cat > "$T1/repo/state/review-trail/$(printf '%s' "$(_today)")-unsafe.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "--output=/tmp/evil..HEAD",
  "artifact": "evil-record"
}
JSON

_write_header "$T1/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T1/repo" "$T1/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -eq 0 ]]; then
  if echo "$STDERR_OUT" | grep -qi "unsafe sha_range\|failed rev-range validation"; then
    _pass "T1: unsafe sha_range emits WARN and script exits 0"
  else
    _fail "T1: SAFE_RANGE" "expected 'unsafe sha_range' WARN in stderr; got: $STDERR_OUT"
  fi
else
  _fail "T1: SAFE_RANGE" "expected exit 0, got $RC. stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# T2 — JSON single-object record: reviewed commits are subtracted from
#      unreviewed_set (they do NOT appear in the Staff Engineer shas).
# ---------------------------------------------------------------------------
T2="$TMPBASE/t2"
_make_fixture "$T2"

sha_c1=$(_add_commit "$T2/repo" "src/alpha.py")
sha_c2=$(_add_commit "$T2/repo" "src/beta.py")
# sha_c1 is the first commit after origin/main; sha_c2 is the tip.
# Build a sha_range that covers both commits: sha_c1^..sha_c2 (git rev-list excludes left side).
# Because sha_c1 is the first commit, sha_c1^ is origin/main's tip.
origin_sha=$(git -C "$T2/repo" rev-parse origin/main)
sha_range="${origin_sha}..${sha_c2}"

cat > "$T2/repo/state/review-trail/$(printf '%s' "$(_today)")-single-obj.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${sha_range}",
  "verdict": "ok",
  "artifact": "some-workstream"
}
JSON

_write_header "$T2/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T2/repo" "$T2/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -ne 0 ]]; then
  _fail "T2: single-obj" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  patrik_shas=$(_read_patrik_shas "$T2/repo")
  # Both commits should be reviewed; neither should appear in the Staff Engineer set.
  if echo "$patrik_shas" | grep -qF "$sha_c1" || echo "$patrik_shas" | grep -qF "$sha_c2"; then
    _fail "T2: single-obj" "reviewed commits ($sha_c1, $sha_c2) appeared in the Staff Engineer shas (should be subtracted): $patrik_shas"
  else
    _pass "T2: single-obj JSON record — reviewed commits subtracted from the Staff Engineer set"
  fi
fi

# ---------------------------------------------------------------------------
# T3 — JSONL dual-shape record: parsed without error; commits count as reviewed.
# ---------------------------------------------------------------------------
T3="$TMPBASE/t3"
_make_fixture "$T3"

sha_j1=$(_add_commit "$T3/repo" "src/jsonl-thing.py")
sha_j2=$(_add_commit "$T3/repo" "src/jsonl-other.py")
origin_sha_t3=$(git -C "$T3/repo" rev-parse origin/main)
sha_range_t3="${origin_sha_t3}..${sha_j2}"

# Write a JSONL file (two JSON objects on separate lines, one after another).
# The first line is the original reviewer record, the second is an integrator envelope.
# Both are valid JSON objects; the file is NOT parseable as a single JSON object.
trail_file_t3="$T3/repo/state/review-trail/$(printf '%s' "$(_today)")-jsonl-record.json"
printf '{"scope_kind":"diff","sha_range":"%s","verdict":"warn","artifact":"jsonl-ws"}\n' "$sha_range_t3" > "$trail_file_t3"
printf '{"scope_kind":"integration","artifact":"jsonl-ws-integrator","note":"integrator envelope"}\n' >> "$trail_file_t3"

_write_header "$T3/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T3/repo" "$T3/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -ne 0 ]]; then
  _fail "T3: JSONL" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  patrik_shas_t3=$(_read_patrik_shas "$T3/repo")
  # The diff record's commits should be reviewed → not in the Staff Engineer set.
  if echo "$patrik_shas_t3" | grep -qF "$sha_j1" || echo "$patrik_shas_t3" | grep -qF "$sha_j2"; then
    _fail "T3: JSONL" "JSONL-record commits appeared in the Staff Engineer set (should be reviewed): $patrik_shas_t3"
  else
    _pass "T3: JSONL dual-shape record — parsed, commits counted as reviewed"
  fi
fi

# ---------------------------------------------------------------------------
# T4 — scope_kind=plan record is skipped silently (no WARN, no error).
# ---------------------------------------------------------------------------
T4="$TMPBASE/t4"
_make_fixture "$T4"

_add_commit "$T4/repo" "docs/plan.md" >/dev/null

cat > "$T4/repo/state/review-trail/$(printf '%s' "$(_today)")-plan-record.json" <<JSON
{
  "scope_kind": "plan",
  "artifact": "some-plan-review",
  "verdict": "ok"
}
JSON

_write_header "$T4/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T4/repo" "$T4/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -ne 0 ]]; then
  _fail "T4: plan record" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  # Should produce NO WARN for the plan record (typed scope_kind suppresses WARN).
  if echo "$STDERR_OUT" | grep -qi "skipping non-diff\|WARN.*plan-record"; then
    _fail "T4: plan record" "unexpected WARN emitted for plan record; stderr: $STDERR_OUT"
  else
    _pass "T4: scope_kind=plan record skipped silently, no WARN"
  fi
fi

# ---------------------------------------------------------------------------
# T5 — Cross-segment seam detection: two records touching a common file
#      surface that file in patrik_seam_files.
# ---------------------------------------------------------------------------
T5="$TMPBASE/t5"
_make_fixture "$T5"

# Segment A: touches common.py + afile.py
sha_a1=$(_add_commit "$T5/repo" "src/common.py" "src/afile.py")
sha_a2=$(_add_commit "$T5/repo" "src/afile.py")
origin_sha_t5=$(git -C "$T5/repo" rev-parse origin/main)
range_a="${origin_sha_t5}..${sha_a2}"

# Segment B: touches common.py + bfile.py (separate "review session")
sha_b1=$(_add_commit "$T5/repo" "src/common.py" "src/bfile.py")
sha_b2=$(_add_commit "$T5/repo" "src/bfile.py")
range_b="${sha_a2}..${sha_b2}"

cat > "$T5/repo/state/review-trail/$(printf '%s' "$(_today)")-seg-a.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${range_a}",
  "verdict": "ok",
  "artifact": "segment-a"
}
JSON

cat > "$T5/repo/state/review-trail/$(printf '%s' "$(_today)")-seg-b.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${range_b}",
  "verdict": "ok",
  "artifact": "segment-b"
}
JSON

_write_header "$T5/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T5/repo" "$T5/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -ne 0 ]]; then
  _fail "T5: seam detection" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  seam_files=$(_read_seam_files "$T5/repo")
  if echo "$seam_files" | grep -qF "src/common.py"; then
    _pass "T5: cross-segment seam detection — common file in patrik_seam_files"
  else
    _fail "T5: seam detection" "expected src/common.py in patrik_seam_files; got: $seam_files"
  fi
fi

# ---------------------------------------------------------------------------
# T6 — Verdict=pending is EXCLUDED from reviewed_set (C2 behaviour).
#
# DELIBERATE C2 BEHAVIOR CHANGE: the shared core (lib/review-coverage-core.sh)
# now applies a verdict filter — verdict=pending records are excluded from
# reviewed_set, so their commits move into the unreviewed set and appear in
# patrik_shas. This closes the latent weekly-gate gap where a pending record
# (an incomplete review) previously counted as coverage.
#
# Prior T6 asserted the pre-C2 shape: "pending counts as reviewed".
# This updated T6 asserts the NEW shape: "pending commits land in the Staff Engineer set".
#
# T1-T5 are unchanged and green — they are the behavior-preserving proof
# that extraction did not alter any other behavior.
# ---------------------------------------------------------------------------
T6="$TMPBASE/t6"
_make_fixture "$T6"

sha_p1=$(_add_commit "$T6/repo" "src/pending-thing.py")
sha_p2=$(_add_commit "$T6/repo" "src/another-thing.py")
origin_sha_t6=$(git -C "$T6/repo" rev-parse origin/main)
range_p="${origin_sha_t6}..${sha_p2}"

cat > "$T6/repo/state/review-trail/$(printf '%s' "$(_today)")-pending.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${range_p}",
  "verdict": "pending",
  "artifact": "pending-ws"
}
JSON

_write_header "$T6/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T6/repo" "$T6/repo/state/week-changelog/HEADER.md"

if [[ "$RC" -ne 0 ]]; then
  _fail "T6: pending-excluded (C2 behaviour)" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  patrik_shas_t6=$(_read_patrik_shas "$T6/repo")
  # C2 behaviour: pending verdict IS filtered out; commits are NOT credited as
  # reviewed and therefore DO appear in the Staff Engineer set (more review, never less).
  if echo "$patrik_shas_t6" | grep -qF "$sha_p1" && echo "$patrik_shas_t6" | grep -qF "$sha_p2"; then
    _pass "T6: pending-excluded (C2 behaviour) — pending record's commits appear in the Staff Engineer set (unreviewed)"
  else
    _fail "T6: pending-excluded (C2 behaviour)" "expected sha_p1 ($sha_p1) and sha_p2 ($sha_p2) in the Staff Engineer set (pending excluded); got: $patrik_shas_t6"
  fi
fi

# ---------------------------------------------------------------------------
# T7 — A malformed live-dir trail record makes the weekly gate FAIL LOUD.
# The weekly gate consumes the shared core WITHOUT --on-record-error, inheriting
# its default `fail` — so a record that parses as neither JSON nor JSONL aborts
# the run (the detect-then-fail-loud-on-segment-shape doctrine, b3g-077, exercised
# end-to-end through workweek-trail-scope.sh, not just at the core in isolation).
# This is the deliberate OPPOSITE of the chain-end coverage gate's `skip` policy.
# ---------------------------------------------------------------------------
T7="$TMPBASE/t7"
_make_fixture "$T7"
_add_commit "$T7/repo" "src/t7-thing.py" >/dev/null
# Garbage that parses as neither a single JSON object nor JSONL.
printf '%s\n' '{"scope_kind":"diff"} GARBAGE not json {' \
  > "$T7/repo/state/review-trail/$(_today)-malformed.json"
_write_header "$T7/repo/state/week-changelog/HEADER.md" "2000-01-01"
_run_subject "$T7/repo" "$T7/repo/state/week-changelog/HEADER.md"
if [[ "$RC" -ne 0 ]]; then
  _pass "T7: malformed live-dir record → weekly gate fails loud (inherits core default --on-record-error fail)"
else
  _fail "T7: weekly fail-loud" "expected non-zero exit on a malformed record; got RC=$RC stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# T8 — Concurrent-session non-collision: two invocations against the same
# fixture with two DISTINCT CLAUDE_CODE_SESSION_ID values must produce two
# distinct shard files (the core claim of the session-keyed shard rework).
# Review: code-reviewer — F5.
# ---------------------------------------------------------------------------
T8="$TMPBASE/t8"
_make_fixture "$T8"
_add_commit "$T8/repo" "src/t8-thing.py" >/dev/null
_write_header "$T8/repo/state/week-changelog/HEADER.md" "2000-01-01"

_run_subject_as "$T8/repo" "$T8/repo/state/week-changelog/HEADER.md" "test-session-aaaaaaaa"
rc8a="$RC"
_run_subject_as "$T8/repo" "$T8/repo/state/week-changelog/HEADER.md" "test-session-bbbbbbbb"
rc8b="$RC"

if [[ "$rc8a" -ne 0 || "$rc8b" -ne 0 ]]; then
  _fail "T8: concurrent-session non-collision" "expected both invocations to exit 0; got rc8a=$rc8a rc8b=$rc8b"
else
  shard_count_t8=$(_count_scope_shards "$T8/repo")
  if [[ "$shard_count_t8" -eq 2 ]]; then
    _pass "T8: two distinct CLAUDE_CODE_SESSION_ID invocations produce two distinct shard files"
  else
    _fail "T8: concurrent-session non-collision" "expected 2 distinct shard files, found $shard_count_t8"
  fi
fi

# ---------------------------------------------------------------------------
# T9 — %N-fallback branch: force the fallback via a stub `date` on PATH that
# never emits %N, then run the subject TWICE with the SAME session id. Before
# the F2 fix this silently clobbered (one shard file survives); after the fix
# the per-process PID disambiguator produces two distinct files.
# Review: code-reviewer — F5/F2 regression net for the fallback branch.
# ---------------------------------------------------------------------------
T9="$TMPBASE/t9"
_make_fixture "$T9"
_add_commit "$T9/repo" "src/t9-thing.py" >/dev/null
_write_header "$T9/repo/state/week-changelog/HEADER.md" "2000-01-01"

STUBDIR="$TMPBASE/t9-stub-bin"
mkdir -p "$STUBDIR"
cat > "$STUBDIR/date" <<'STUBEOF'
#!/usr/bin/env bash
# Stub `date`: strips any %N from the format string before delegating to the
# real `date`, so the %N-probe in workweek-trail-scope.sh always falls back
# to second-precision (simulates BSD/macOS `date` on a platform where %N is
# a literal passthrough rather than nanoseconds).
if [[ -x /bin/date ]]; then
  real_date=/bin/date
elif [[ -x /usr/bin/date ]]; then
  real_date=/usr/bin/date
else
  real_date=$(type -ap date | grep -v "^$0\$" | head -n1)
fi
args=()
for a in "$@"; do
  args+=("${a//%N/}")
done
exec "$real_date" "${args[@]}"
STUBEOF
chmod +x "$STUBDIR/date"

_run_subject_as "$T9/repo" "$T9/repo/state/week-changelog/HEADER.md" "test-session-cccccccc" "$STUBDIR"
rc9a="$RC"
_run_subject_as "$T9/repo" "$T9/repo/state/week-changelog/HEADER.md" "test-session-cccccccc" "$STUBDIR"
rc9b="$RC"

if [[ "$rc9a" -ne 0 || "$rc9b" -ne 0 ]]; then
  _fail "T9: %N-fallback disambiguator" "expected both invocations to exit 0; got rc9a=$rc9a rc9b=$rc9b"
else
  shard_count_t9=$(_count_scope_shards "$T9/repo")
  if [[ "$shard_count_t9" -eq 2 ]]; then
    _pass "T9: %N-fallback branch — same-session same-second invocations produce distinct shard files (F2 disambiguator)"
  else
    _fail "T9: %N-fallback disambiguator" "expected 2 distinct shard files under forced %N-fallback, found $shard_count_t9"
  fi
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL (${TOTAL} total)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
