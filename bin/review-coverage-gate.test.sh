#!/usr/bin/env bash
# review-coverage-gate.test.sh — TF1-TF12 for bin/review-coverage-gate.sh.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C3
#
# Dogfoods a SYNTHETIC reproduction of the exact incident shape:
#   a chain where a trail record A..B has A = a chunk tip with no prior record
#   covering it → the gate correctly flags A as UNCOVERED (TF1).
#
# Harness matches the style of bin/workweek-trail-scope.test.sh:
#   each test builds a bare origin + working clone, seeds commits, writes trail
#   records into state/review-trail/, and runs the gate with cwd=fixture/repo.
#
# Test coverage:
#   TF1   Incident reproduction: record A..B where A is in chain, not covered → UNCOVERED
#   TF2   A covered by prior record X..A (A as right endpoint) → union covers A, COVERED
#   TF3   Chain fully covered by union of records → COVERED
#   TF4   Archive-resident record (archive/review-trail/**) counts toward coverage
#   TF5   scope_kind=plan/integration skipped; SAFE_RANGE-invalid sha_range skipped; no crash
#   TF6   --scope-paths narrows chain_set to commits touching those paths
#   TF7   verdict=pending NOT counted (UNCOVERED); verdict=waived IS counted (COVERED)
#   TF8   Empty trail dir → all chain commits UNCOVERED, no crash
#   TF9   Zero-commit chain (merge-base==HEAD) → COVERED, no crash
#   TF10  --scope-paths + merge commit → merge commit excluded from chain_set (--no-merges)
#   TF11  JSONL integrator-envelope trail record parsed; its diff record counts toward coverage
#   TF12  Missing --scope-paths falls back to unscoped whole-chain (no crash)
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
SUBJECT="${SCRIPT_DIR}/review-coverage-gate.sh"

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

STDERR_TMP="$TMPBASE/gate-stderr"
STDOUT_TMP="$TMPBASE/gate-stdout"

# ---------------------------------------------------------------------------
# _make_fixture DIR — build a git repo with a local-bare origin remote.
#
# Structure:
#   $DIR/origin.git  — bare repo (the "remote")
#   $DIR/repo        — working clone of origin
#
# After _make_fixture:
#   - origin/main is a valid ref in the working clone
#   - git merge-base origin/main HEAD resolves (shared root commit)
#   - state/review-trail/ exists under $DIR/repo
# ---------------------------------------------------------------------------
_make_fixture() {
  local base="$1"

  # --- bare "origin" ---
  local origin_dir="$base/origin.git"
  mkdir -p "$origin_dir"
  git -C "$origin_dir" init -q --bare

  # Seed with a root commit via a temp clone.
  local seed_dir="$base/seed"
  git clone -q "$origin_dir" "$seed_dir" 2>/dev/null
  git -C "$seed_dir" config user.email "test@test.local"
  git -C "$seed_dir" config user.name  "Test"
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
  git -C "$repo_dir" checkout -q main 2>/dev/null || true

  # Required directory layout.
  mkdir -p "$repo_dir/state/review-trail"
}

# Helper: add a commit to the fixture repo touching one or more files.
# Returns the SHA of the new commit via stdout.
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

# Helper: run the gate in a given repo directory.
# Optional extra args after REPO_DIR are passed to the gate.
# Sets RC, STDOUT_OUT, STDERR_OUT.
RC=0
STDOUT_OUT=""
STDERR_OUT=""

_run_gate() {
  local repo="$1"; shift
  RC=0
  STDOUT_OUT=""
  STDERR_OUT=""
  STDOUT_OUT=$(cd "$repo" && bash "$SUBJECT" "$@" 2>"$STDERR_TMP") || RC=$?
  STDERR_OUT=$(cat "$STDERR_TMP" 2>/dev/null || true)
}

# Helper: extract the VERDICT value from gate stdout.
_verdict() {
  printf '%s' "$STDOUT_OUT" | grep -oE 'VERDICT=[A-Z_]+' | cut -d= -f2
}

# ---------------------------------------------------------------------------
# TF1 — Incident reproduction: record A..B where A is a chain commit covered
# by NO other record → A flagged UNCOVERED.
#
# Shape: origin/main → C1(A) → C2(B)
# Trail record covers A..B (excludes A by git rev-list semantics).
# Expected: A is uncovered → VERDICT=UNCOVERED.
# ---------------------------------------------------------------------------
TF1="$TMPBASE/tf1"
_make_fixture "$TF1"

sha_a=$(_add_commit "$TF1/repo" "src/core.py")   # C1 — the chunk tip, A
sha_b=$(_add_commit "$TF1/repo" "src/extra.py")  # C2 — B

# Trail covers A..B: by rev-list semantics, A is excluded from this record's coverage.
# No other record covers A → A is UNCOVERED (the incident shape).
cat > "$TF1/repo/state/review-trail/2026-06-22-001-incident.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${sha_a}..${sha_b}",
  "verdict": "ok",
  "artifact": "workstream-c2-onwards"
}
JSON

_run_gate "$TF1/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF1: incident" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "UNCOVERED" ]] && printf '%s' "$STDERR_OUT" | grep -qF "$sha_a"; then
    _pass "TF1: incident shape — A flagged UNCOVERED, A appears in stderr"
  else
    _fail "TF1: incident" "expected VERDICT=UNCOVERED and $sha_a in stderr; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF2 — A covered by prior record X..A (A as right endpoint).
# Per-commit semantics: git rev-list X..A INCLUDES A.
# Expected: A is covered → VERDICT=COVERED.
# ---------------------------------------------------------------------------
TF2="$TMPBASE/tf2"
_make_fixture "$TF2"

origin_tf2=$(git -C "$TF2/repo" rev-parse origin/main)
sha_a2=$(_add_commit "$TF2/repo" "src/core.py")   # A — tip of first chunk
sha_b2=$(_add_commit "$TF2/repo" "src/extra.py")  # B

# Prior record covers X..A (includes A as right endpoint).
# origin/main..A = covers A and everything between origin and A.
cat > "$TF2/repo/state/review-trail/2026-06-22-001-prior.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf2}..${sha_a2}",
  "verdict": "ok",
  "artifact": "workstream-c1"
}
JSON

# Later record covers A..B.
cat > "$TF2/repo/state/review-trail/2026-06-22-002-later.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${sha_a2}..${sha_b2}",
  "verdict": "ok",
  "artifact": "workstream-c2"
}
JSON

_run_gate "$TF2/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF2: prior record covers A" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF2: A covered by prior record X..A → union covers A, VERDICT=COVERED"
  else
    _fail "TF2: prior record covers A" "expected COVERED; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF3 — Chain fully covered by union of records → COVERED.
# ---------------------------------------------------------------------------
TF3="$TMPBASE/tf3"
_make_fixture "$TF3"

origin_tf3=$(git -C "$TF3/repo" rev-parse origin/main)
sha_c3a=$(_add_commit "$TF3/repo" "src/a.py")
sha_c3b=$(_add_commit "$TF3/repo" "src/b.py")
sha_c3c=$(_add_commit "$TF3/repo" "src/c.py")

# Three records that together cover origin..C (all three commits).
cat > "$TF3/repo/state/review-trail/2026-06-22-001.json" <<JSON
{"scope_kind":"diff","sha_range":"${origin_tf3}..${sha_c3a}","verdict":"ok","artifact":"ws-a"}
JSON
cat > "$TF3/repo/state/review-trail/2026-06-22-002.json" <<JSON
{"scope_kind":"diff","sha_range":"${sha_c3a}..${sha_c3b}","verdict":"warn","artifact":"ws-b"}
JSON
cat > "$TF3/repo/state/review-trail/2026-06-22-003.json" <<JSON
{"scope_kind":"diff","sha_range":"${sha_c3b}..${sha_c3c}","verdict":"ok","artifact":"ws-c"}
JSON

_run_gate "$TF3/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF3: fully covered" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF3: chain fully covered by union → VERDICT=COVERED"
  else
    _fail "TF3: fully covered" "expected COVERED; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF4 — Archive-resident record (archive/review-trail/**) counts toward coverage.
# ---------------------------------------------------------------------------
TF4="$TMPBASE/tf4"
_make_fixture "$TF4"

origin_tf4=$(git -C "$TF4/repo" rev-parse origin/main)
sha_c4=$(_add_commit "$TF4/repo" "src/archived-feature.py")

# Record lives in ARCHIVE, not live trail.
mkdir -p "$TF4/repo/archive/review-trail/week-2026-06-15"
cat > "$TF4/repo/archive/review-trail/week-2026-06-15/2026-06-15-001-archived.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf4}..${sha_c4}",
  "verdict": "ok",
  "artifact": "archived-workstream"
}
JSON

# Live trail is empty.

_run_gate "$TF4/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF4: archive-resident record" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF4: archived trail record counts toward coverage → COVERED"
  else
    _fail "TF4: archive-resident record" "expected COVERED (archive record should count); got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF5 — scope_kind=plan/integration records ignored; SAFE_RANGE-invalid sha_range
# skipped; no crash, gate continues without those records.
# ---------------------------------------------------------------------------
TF5="$TMPBASE/tf5"
_make_fixture "$TF5"

origin_tf5=$(git -C "$TF5/repo" rev-parse origin/main)
sha_c5=$(_add_commit "$TF5/repo" "src/thing.py")

# Plan record — must be ignored.
cat > "$TF5/repo/state/review-trail/2026-06-22-001-plan.json" <<JSON
{
  "scope_kind": "plan",
  "verdict": "ok",
  "artifact": "some-plan-review"
}
JSON

# Integration record — must be ignored.
cat > "$TF5/repo/state/review-trail/2026-06-22-002-integration.json" <<JSON
{
  "scope_kind": "integration",
  "verdict": "ok",
  "artifact": "some-integration-review"
}
JSON

# SAFE_RANGE-invalid sha_range (leading dash = argument injection attempt).
cat > "$TF5/repo/state/review-trail/2026-06-22-003-unsafe.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "--output=/tmp/evil..HEAD",
  "verdict": "ok",
  "artifact": "unsafe-record"
}
JSON

# A real diff record that DOES cover the chain commit.
cat > "$TF5/repo/state/review-trail/2026-06-22-004-real.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf5}..${sha_c5}",
  "verdict": "ok",
  "artifact": "real-record"
}
JSON

_run_gate "$TF5/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF5: bad records skipped" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  # The chain commit is covered by the real record; bad records cause no crash.
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF5: plan/integration/SAFE_RANGE-invalid records skipped; real record counts → COVERED"
  else
    _fail "TF5: bad records skipped" "expected COVERED (bad records ignored, real record covers commit); got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF6 — --scope-paths narrows chain_set to commits touching those paths.
# Commit touching src/api.py is in scope; commit touching src/unrelated.py is not.
# Only the in-scope commit needs to be covered.
# ---------------------------------------------------------------------------
TF6="$TMPBASE/tf6"
_make_fixture "$TF6"

origin_tf6=$(git -C "$TF6/repo" rev-parse origin/main)
sha_api=$(_add_commit "$TF6/repo" "src/api.py")          # IN scope
sha_unrelated=$(_add_commit "$TF6/repo" "src/other.py")  # NOT in scope

# Only the api commit is covered by a trail record.
cat > "$TF6/repo/state/review-trail/2026-06-22-001.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf6}..${sha_api}",
  "verdict": "ok",
  "artifact": "api-review"
}
JSON
# src/other.py commit is NOT covered — but it's out of scope, so gate should pass.

_run_gate "$TF6/repo" --scope-paths "src/api.py"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF6: --scope-paths" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF6: --scope-paths narrows chain_set; only in-scope commit checked → COVERED"
  else
    _fail "TF6: --scope-paths" "expected COVERED (out-of-scope commit excluded); got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF7a — verdict=pending does NOT count as covered → commit is UNCOVERED.
# TF7b — verdict=waived DOES count as covered → commit is COVERED.
# Two sub-cases for TF7.
# ---------------------------------------------------------------------------

# TF7a: pending
TF7a="$TMPBASE/tf7a"
_make_fixture "$TF7a"

origin_tf7a=$(git -C "$TF7a/repo" rev-parse origin/main)
sha_p=$(_add_commit "$TF7a/repo" "src/feature.py")

cat > "$TF7a/repo/state/review-trail/2026-06-22-001-pending.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf7a}..${sha_p}",
  "verdict": "pending",
  "artifact": "in-progress-review"
}
JSON

_run_gate "$TF7a/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF7a: pending not counted" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "UNCOVERED" ]]; then
    _pass "TF7a: verdict=pending record does not count as covered → UNCOVERED"
  else
    _fail "TF7a: pending not counted" "expected UNCOVERED; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# TF7b: waived
TF7b="$TMPBASE/tf7b"
_make_fixture "$TF7b"

origin_tf7b=$(git -C "$TF7b/repo" rev-parse origin/main)
sha_w=$(_add_commit "$TF7b/repo" "src/feature.py")

cat > "$TF7b/repo/state/review-trail/2026-06-22-001-waived.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf7b}..${sha_w}",
  "verdict": "waived",
  "artifact": "pm-waived-review"
}
JSON

_run_gate "$TF7b/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF7b: waived counts" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF7b: verdict=waived counts as covered → COVERED"
  else
    _fail "TF7b: waived counts" "expected COVERED; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF8 — Empty trail dir → all chain commits UNCOVERED, no crash.
# ---------------------------------------------------------------------------
TF8="$TMPBASE/tf8"
_make_fixture "$TF8"

_add_commit "$TF8/repo" "src/thing.py" >/dev/null

# Leave state/review-trail/ empty.

_run_gate "$TF8/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF8: empty trail" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "UNCOVERED" ]]; then
    _pass "TF8: empty trail dir → all chain commits UNCOVERED, no crash"
  else
    _fail "TF8: empty trail" "expected UNCOVERED (no records); got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF9 — Zero-commit chain (merge-base == HEAD) → COVERED, no crash.
# HEAD is already at origin/main (nothing pushed after clone).
# ---------------------------------------------------------------------------
TF9="$TMPBASE/tf9"
_make_fixture "$TF9"

# No commits added — origin/main == HEAD → zero-commit chain.

_run_gate "$TF9/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF9: zero-commit chain" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  # chain_commits=0 → nothing to cover → COVERED
  chain_commits=$(printf '%s' "$STDOUT_OUT" | grep -oE 'chain_commits=[0-9]+' | cut -d= -f2 || true)
  if [[ "$verdict" == "COVERED" && "${chain_commits:-0}" -eq 0 ]]; then
    _pass "TF9: zero-commit chain (merge-base==HEAD) → COVERED, no crash"
  else
    _fail "TF9: zero-commit chain" "expected chain_commits=0 COVERED; got: verdict=$verdict chain_commits=${chain_commits:-?} stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF10 — Merge commit with --scope-paths → merge commit excluded from chain_set.
#
# Setup: origin → C1 (feature branch tip) → merge commit → C3 (more work)
# The merge commit touches src/feature.py (via merge resolution).
# With --scope-paths src/feature.py, only non-merge commits touching that file
# appear in chain_set (merge commit excluded by --no-merges).
# ---------------------------------------------------------------------------
TF10="$TMPBASE/tf10"
_make_fixture "$TF10"

origin_tf10=$(git -C "$TF10/repo" rev-parse origin/main)

# Create a feature branch with one commit.
git -C "$TF10/repo" checkout -q -b feature/tf10 2>/dev/null
sha_feat=$(_add_commit "$TF10/repo" "src/feature.py")  # feature commit

# Back to main, add a commit there too.
git -C "$TF10/repo" checkout -q main 2>/dev/null
sha_main=$(_add_commit "$TF10/repo" "src/main-thing.py")

# Merge the feature branch → creates a merge commit.
git -C "$TF10/repo" merge --no-ff -q -m "Merge feature/tf10" feature/tf10 2>/dev/null || true
sha_merge=$(git -C "$TF10/repo" rev-parse HEAD)

# Add one more commit after the merge.
sha_after=$(_add_commit "$TF10/repo" "src/feature.py")

# Review records covering the non-merge commits that touch src/feature.py.
cat > "$TF10/repo/state/review-trail/2026-06-22-001-feat.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf10}..${sha_feat}",
  "verdict": "ok",
  "artifact": "feature-review"
}
JSON

# The merge commit sha is known; we do NOT cover it (but --no-merges excludes it anyway).
# Cover sha_main's range too (so it doesn't flag, even though not in --scope-paths).
# Cover sha_after as well.
cat > "$TF10/repo/state/review-trail/2026-06-22-002-after.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${sha_merge}..${sha_after}",
  "verdict": "ok",
  "artifact": "after-merge-review"
}
JSON

# Run with --scope-paths src/feature.py — should only include sha_feat and sha_after.
# sha_merge is excluded by --no-merges. sha_main doesn't touch src/feature.py.
_run_gate "$TF10/repo" --scope-paths "src/feature.py"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF10: --no-merges with merge commit" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  # Merge commit must not appear in uncovered list.
  if printf '%s' "$STDERR_OUT" | grep -qF "$sha_merge"; then
    _fail "TF10: --no-merges" "merge commit $sha_merge appeared in stderr (should be excluded by --no-merges); stderr=$STDERR_OUT"
  elif [[ "$verdict" == "COVERED" ]]; then
    _pass "TF10: merge commit excluded from chain_set by --no-merges; scoped commits covered → COVERED"
  else
    _fail "TF10: --no-merges with merge commit" "expected COVERED; got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF11 — JSONL integrator-envelope trail record is parsed; its diff record
# counts toward coverage (exercises the core's JSONL parse path end-to-end).
#
# Shape: JSONL file with two lines — the first is the diff record (scope_kind=diff),
# the second is an integrator envelope (scope_kind=integration). The file as a
# whole is NOT parseable as a single JSON object (JSONL fallback fires).
# ---------------------------------------------------------------------------
TF11="$TMPBASE/tf11"
_make_fixture "$TF11"

origin_tf11=$(git -C "$TF11/repo" rev-parse origin/main)
sha_tf11=$(_add_commit "$TF11/repo" "src/jsonl-feature.py")

# JSONL file: two JSON lines; not parseable as single JSON object.
cat > "$TF11/repo/state/review-trail/2026-06-22-001-jsonl.json" <<JSON
{"scope_kind":"diff","sha_range":"${origin_tf11}..${sha_tf11}","verdict":"ok","artifact":"jsonl-ws"}
{"scope_kind":"integration","artifact":"jsonl-integrator","note":"envelope record"}
JSON

_run_gate "$TF11/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF11: JSONL parse" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  if [[ "$verdict" == "COVERED" ]]; then
    _pass "TF11: JSONL integrator-envelope record parsed; diff record counts toward coverage → COVERED"
  else
    _fail "TF11: JSONL parse" "expected COVERED (JSONL diff record should count); got: verdict=$verdict stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF12 — Missing --scope-paths falls back to unscoped whole-chain (no crash).
# All commits in the range are included in chain_set (no path filter applied).
# ---------------------------------------------------------------------------
TF12="$TMPBASE/tf12"
_make_fixture "$TF12"

origin_tf12=$(git -C "$TF12/repo" rev-parse origin/main)
sha_tf12a=$(_add_commit "$TF12/repo" "src/alpha.py")
sha_tf12b=$(_add_commit "$TF12/repo" "src/beta.py")

# Both commits covered.
cat > "$TF12/repo/state/review-trail/2026-06-22-001.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf12}..${sha_tf12b}",
  "verdict": "ok",
  "artifact": "full-ws-review"
}
JSON

# No --scope-paths passed — gate must apply whole-chain check (both commits).
_run_gate "$TF12/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF12: unscoped fallback" "gate exited $RC. stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  chain_commits=$(printf '%s' "$STDOUT_OUT" | grep -oE 'chain_commits=[0-9]+' | cut -d= -f2 || true)
  # chain_commits should be 2 (both commits included in unscoped whole-chain).
  if [[ "$verdict" == "COVERED" && "${chain_commits:-0}" -eq 2 ]]; then
    _pass "TF12: missing --scope-paths → unscoped whole-chain (both commits); no crash → COVERED"
  else
    _fail "TF12: unscoped fallback" "expected chain_commits=2 COVERED; got: verdict=$verdict chain_commits=${chain_commits:-?} stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF13 — Malformed (unparseable) trail file in state/review-trail/ alongside
#         valid records → gate does NOT crash, emits a VERDICT= line, and valid
#         records' coverage is still computed (gate uses --on-record-error skip).
# ---------------------------------------------------------------------------
TF13="$TMPBASE/tf13"
_make_fixture "$TF13"

origin_tf13=$(git -C "$TF13/repo" rev-parse origin/main)
sha_tf13=$(_add_commit "$TF13/repo" "src/tf13-feature.py")

# Malformed: concatenated JSON objects — neither JSON nor JSONL.
cat > "$TF13/repo/state/review-trail/2026-06-22-001-malformed.json" <<'BADEOF'
{"a":1}{"b":2}
BADEOF

# Valid sibling covering the chain commit.
cat > "$TF13/repo/state/review-trail/2026-06-22-002-valid.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf13}..${sha_tf13}",
  "verdict": "ok",
  "artifact": "tf13-real-record"
}
JSON

_run_gate "$TF13/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF13: malformed trail alongside valid" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  has_verdict=$(printf '%s' "$STDOUT_OUT" | grep -c 'VERDICT=' || true)
  if [[ "$has_verdict" -ge 1 && "$verdict" == "COVERED" ]]; then
    _pass "TF13: malformed trail file alongside valid record → gate does not crash, emits VERDICT=COVERED"
  elif [[ "$has_verdict" -ge 1 ]]; then
    _fail "TF13: malformed trail alongside valid" "gate ran but got unexpected verdict=$verdict (expected COVERED); stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  else
    _fail "TF13: malformed trail alongside valid" "expected VERDICT= line in stdout; got: stdout=$STDOUT_OUT stderr=$STDERR_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF14 — Record with unresolvable sha_range (real-sha..WORKING — passes
#         SAFE_RANGE but WORKING is not a ref) alongside a valid covering record
#         → gate does NOT crash, emits VERDICT= line, skips the bad record.
# ---------------------------------------------------------------------------
TF14="$TMPBASE/tf14"
_make_fixture "$TF14"

origin_tf14=$(git -C "$TF14/repo" rev-parse origin/main)
sha_tf14=$(_add_commit "$TF14/repo" "src/tf14-feature.py")

# sha_tf14..WORKING passes SAFE_RANGE (starts with hex char, contains "..")
# but WORKING is not a git ref in this synthetic repo → rev-list fails.
cat > "$TF14/repo/state/review-trail/2026-06-22-001-bad-range.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${sha_tf14}..WORKING",
  "verdict": "ok",
  "artifact": "tf14-unresolvable"
}
JSON

# Valid record covering the chain commit (origin..sha_tf14).
cat > "$TF14/repo/state/review-trail/2026-06-22-002-valid.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf14}..${sha_tf14}",
  "verdict": "ok",
  "artifact": "tf14-real-record"
}
JSON

_run_gate "$TF14/repo"

if [[ "$RC" -ne 0 ]]; then
  _fail "TF14: unresolvable sha_range in corpus" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
else
  verdict=$(_verdict)
  has_verdict=$(printf '%s' "$STDOUT_OUT" | grep -c 'VERDICT=' || true)
  has_warn=$(printf '%s' "$STDERR_OUT" | grep -ci 'WARN' || true)
  if [[ "$has_verdict" -ge 1 && "$verdict" == "COVERED" && "$has_warn" -ge 1 ]]; then
    _pass "TF14: unresolvable sha_range → gate does not crash, WARN on stderr, valid record still counts, VERDICT=COVERED"
  elif [[ "$has_verdict" -ge 1 && "$verdict" == "COVERED" ]]; then
    _fail "TF14: unresolvable sha_range" "COVERED but no WARN emitted on stderr (expected skip warning); stderr=$STDERR_OUT"
  else
    _fail "TF14: unresolvable sha_range" "expected VERDICT=COVERED with WARN; got: verdict=$verdict has_verdict=$has_verdict stderr=$STDERR_OUT stdout=$STDOUT_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TF15 — caller-supplied range with a leading dash (smuggled past the `-*` arm
# via the `--` separator) is rejected by SAFE_RANGE validation BEFORE reaching
# `git rev-list` (F4 hardening: the core's SAFE_RANGE protects trail-JSON, not
# the gate's own positional range arg).
# ---------------------------------------------------------------------------
TF15="$TMPBASE/tf15"
_make_fixture "$TF15"
_run_gate "$TF15/repo" -- "--output=/tmp/evil..HEAD"
if [[ "$RC" -ne 0 ]] && echo "$STDERR_OUT" | grep -q "unsafe range argument"; then
  _pass "TF15: leading-dash range arg rejected before git (F4 injection guard)"
else
  _fail "TF15: range injection guard" "expected non-zero exit + 'unsafe range argument'; got RC=$RC stderr=$STDERR_OUT stdout=$STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TF16 — CRLF regression: Python on Windows emits \r\n to stdout; bash $()
# captures preserve \r; REVIEWED_LOOKUP keys become "sha\r" while chain SHAs
# are clean → every membership test misses → covered=0 VERDICT=UNCOVERED for
# legitimately-reviewed commits (the exact incident reported 2026-06-29).
#
# Fix: strip \r from REVIEWED_OUTPUT before mapfile at the capture boundary.
#
# Pre-fix behaviour: gate reports VERDICT=UNCOVERED (covered=0) for this fixture.
# Post-fix behaviour: gate reports VERDICT=COVERED (covered=1).
# ---------------------------------------------------------------------------
TF16="$TMPBASE/tf16"
_make_fixture "$TF16"

origin_tf16=$(git -C "$TF16/repo" rev-parse origin/main)
sha_tf16=$(_add_commit "$TF16/repo" "src/crlf-regression.py")

# Trail record covering the one chain commit.
cat > "$TF16/repo/state/review-trail/2026-06-29-143522245846-0aad886c.json" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${origin_tf16}..${sha_tf16}",
  "verdict": "ok",
  "artifact": "crlf-regression-workstream"
}
JSON

_run_gate "$TF16/repo" --scope-paths src/crlf-regression.py

if [[ "$RC" -ne 0 ]]; then
  _fail "TF16: CRLF regression" "gate exited $RC (expected 0). stdout=$STDOUT_OUT stderr=$STDERR_OUT"
elif printf '%s' "$STDOUT_OUT" | grep -qF 'VERDICT=COVERED'; then
  _pass "TF16: CRLF regression — chain commit with trail record → VERDICT=COVERED (\\r stripped from REVIEWED_OUTPUT)"
else
  _fail "TF16: CRLF regression" "expected VERDICT=COVERED (chain commit IS covered by trail record); got: $STDOUT_OUT — pre-fix gate produces UNCOVERED because Python \\r\\n makes REVIEWED_LOOKUP[sha\\r]=1 while chain SHA is clean"
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
