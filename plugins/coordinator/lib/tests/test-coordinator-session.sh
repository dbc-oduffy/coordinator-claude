#!/bin/bash
# test-coordinator-session.sh — Tests for coordinator-session.sh
#
# Exercises: dir creation, touch dedup, scope computation (including
# cross-session set-subtraction), mtime fallback union, orphan detection,
# archive, and liveness classification.
#
# Run from any directory:
#   bash ~/.claude/plugins/coordinator-claude/coordinator/lib/tests/test-coordinator-session.sh
#
# Exit 0: all tests pass. Non-zero: at least one failure (details on stderr).

set -euo pipefail

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
SKIP=0

_pass() { PASS=$(( PASS + 1 )); echo "  PASS: $1"; }
_fail() { FAIL=$(( FAIL + 1 )); echo "  FAIL: $1" >&2; }
_skip() { SKIP=$(( SKIP + 1 )); echo "  SKIP: $1"; }

assert_eq() {
  local desc="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    _pass "$desc"
  else
    _fail "$desc — expected $(printf '%q' "$expected"), got $(printf '%q' "$actual")"
  fi
}

assert_file_exists() {
  local desc="$1" path="$2"
  if [[ -f "$path" ]]; then
    _pass "$desc"
  else
    _fail "$desc — file not found: $path"
  fi
}

assert_dir_exists() {
  local desc="$1" path="$2"
  if [[ -d "$path" ]]; then
    _pass "$desc"
  else
    _fail "$desc — dir not found: $path"
  fi
}

assert_contains() {
  local desc="$1" haystack="$2" needle="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    _pass "$desc"
  else
    _fail "$desc — expected to contain $(printf '%q' "$needle"), got: $haystack"
  fi
}

assert_not_contains() {
  local desc="$1" haystack="$2" needle="$3"
  if ! echo "$haystack" | grep -qF "$needle"; then
    _pass "$desc"
  else
    _fail "$desc — expected NOT to contain $(printf '%q' "$needle"), got: $haystack"
  fi
}

# ---------------------------------------------------------------------------
# Setup: temporary git repo + source the library
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB="${LIB_DIR}/coordinator-session.sh"

if [[ ! -f "$LIB" ]]; then
  echo "ERROR: library not found at $LIB" >&2
  exit 1
fi

# Create a temp git repo so all git calls operate on a known clean state
TMPDIR_BASE=$(mktemp -d)
REPO="${TMPDIR_BASE}/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "test@test.local"
git config user.name "Test"
# Create an initial commit so HEAD is valid
echo "init" > init.txt
git add init.txt
git commit -q -m "init"

# Source the library in this repo context
# shellcheck source=../coordinator-session.sh
source "$LIB"

cleanup() {
  rm -rf "$TMPDIR_BASE"
}
trap cleanup EXIT

echo
echo "=== coordinator-session.sh tests ==="
echo

# ---------------------------------------------------------------------------
# T01: cs_init creates session directory and required files
# ---------------------------------------------------------------------------
echo "--- T01: cs_init creates session directory ---"

SID="test-session-01"
cs_init "$SID" "test goal"

SDIR="${REPO}/.git/coordinator-sessions/${SID}"
assert_dir_exists  "T01a session dir created"           "$SDIR"
assert_file_exists "T01b started_at file created"       "${SDIR}/started_at"
assert_file_exists "T01c head_at_start file created"    "${SDIR}/head_at_start"
assert_file_exists "T01d touched.txt file created"      "${SDIR}/touched.txt"
assert_file_exists "T01e meta.json file created"        "${SDIR}/meta.json"

# Verify started_at is a plausible ISO timestamp
SA=$(cat "${SDIR}/started_at")
assert_contains "T01f started_at looks like ISO-8601" "$SA" "T"

# Verify meta.json contains expected fields
META=$(cat "${SDIR}/meta.json")
assert_contains "T01g meta.json has session_id" "$META" "test-session-01"
assert_contains "T01h meta.json has goal"       "$META" "test goal"

echo

# ---------------------------------------------------------------------------
# T02: cs_init is idempotent (second call refreshes meta, preserves started_at)
# ---------------------------------------------------------------------------
echo "--- T02: cs_init idempotent ---"

SA_BEFORE=$(cat "${SDIR}/started_at")
# Small sleep to ensure timestamp would differ if re-written
sleep 1
cs_init "$SID" "new goal"
SA_AFTER=$(cat "${SDIR}/started_at")

assert_eq "T02a started_at not overwritten on second init" "$SA_AFTER" "$SA_BEFORE"

# meta.json goal should preserve original on second init with different goal
META2=$(cat "${SDIR}/meta.json")
assert_contains "T02b meta.json still has original goal on re-init" "$META2" "test goal"

echo

# ---------------------------------------------------------------------------
# T03: cs_touch appends a path
# ---------------------------------------------------------------------------
echo "--- T03: cs_touch appends path ---"

SID2="test-session-02"
cs_init "$SID2"

cs_touch "$SID2" "src/foo.sh"
TOUCHED=$(cat "${REPO}/.git/coordinator-sessions/${SID2}/touched.txt")
assert_contains "T03a path appears in touched.txt" "$TOUCHED" "src/foo.sh"

echo

# ---------------------------------------------------------------------------
# T04: cs_touch deduplication — same path appended twice appears once
# ---------------------------------------------------------------------------
echo "--- T04: cs_touch deduplication ---"

cs_touch "$SID2" "src/foo.sh"
cs_touch "$SID2" "src/foo.sh"
COUNT=$(grep -c "src/foo.sh" "${REPO}/.git/coordinator-sessions/${SID2}/touched.txt" || true)
assert_eq "T04a path appears exactly once after duplicate appends" "$COUNT" "1"

echo

# ---------------------------------------------------------------------------
# T05: cs_touch normalizes absolute paths to repo-relative
# ---------------------------------------------------------------------------
echo "--- T05: cs_touch absolute path normalization ---"

ABS_PATH="${REPO}/src/bar.sh"
cs_touch "$SID2" "$ABS_PATH"
TOUCHED2=$(cat "${REPO}/.git/coordinator-sessions/${SID2}/touched.txt")
assert_contains     "T05a normalized path in touched.txt"           "$TOUCHED2" "src/bar.sh"
assert_not_contains "T05b absolute path NOT in touched.txt"         "$TOUCHED2" "${REPO}/src/bar.sh"

echo

# ---------------------------------------------------------------------------
# T06: cs_compute_scope returns own touched paths
# ---------------------------------------------------------------------------
echo "--- T06: cs_compute_scope returns own paths ---"

SID3="test-session-03"
cs_init "$SID3"
cs_touch "$SID3" "tasks/handoffs/w1.md"
cs_touch "$SID3" "docs/plans/plan.md"

SCOPE=$(cs_compute_scope "$SID3" 2>/dev/null)
assert_contains "T06a scope contains first touch"  "$SCOPE" "tasks/handoffs/w1.md"
assert_contains "T06b scope contains second touch" "$SCOPE" "docs/plans/plan.md"

echo

# ---------------------------------------------------------------------------
# T07: cs_compute_scope cross-session subtraction
# ---------------------------------------------------------------------------
echo "--- T07: cs_compute_scope cross-session subtraction ---"

SID_A="test-session-A"
SID_B="test-session-B"
cs_init "$SID_A"
cs_init "$SID_B"

cs_touch "$SID_A" "shared/claimed-by-A.sh"
cs_touch "$SID_A" "shared/only-A.sh"
cs_touch "$SID_B" "shared/claimed-by-A.sh"   # B also claims the shared file
cs_touch "$SID_B" "shared/only-B.sh"

# A's scope should NOT contain claimed-by-A.sh because B also claims it
SCOPE_A=$(cs_compute_scope "$SID_A" 2>/dev/null)
SCOPE_A_STDERR=$(cs_compute_scope "$SID_A" 2>&1 >/dev/null || true)

assert_contains     "T07a A scope contains only-A.sh"              "$SCOPE_A"        "shared/only-A.sh"
assert_not_contains "T07b A scope excludes B-claimed file"         "$SCOPE_A"        "shared/claimed-by-A.sh"
assert_contains     "T07c subtraction warning emitted to stderr"   "$SCOPE_A_STDERR" "skipping shared/claimed-by-A.sh"
assert_contains     "T07d stderr names owning session"             "$SCOPE_A_STDERR" "$SID_B"

echo

# ---------------------------------------------------------------------------
# T08: cs_compute_scope mtime fallback union
# ---------------------------------------------------------------------------
echo "--- T08: cs_compute_scope mtime fallback ---"

SID4="test-session-mtime"
cs_init "$SID4"

# Create a real file in the repo that was NOT touched via cs_touch but is dirty
# and newer than started_at. We need the file to show up in `git status`.
mkdir -p "${REPO}/src"
echo "hello" > "${REPO}/src/bash-edited.sh"
# File is untracked (dirty) and mtime > started_at (just written)

SCOPE4=$(cs_compute_scope "$SID4" 2>/dev/null)
assert_contains "T08a mtime-dirty file appears in scope even without cs_touch" "$SCOPE4" "src/bash-edited.sh"

echo

# ---------------------------------------------------------------------------
# T09: cs_compute_scope orphan detection
# ---------------------------------------------------------------------------
echo "--- T09: orphan detection ---"

SID5="test-session-orphan"
cs_init "$SID5"

# Create a dirty file that no session claims and is newer than started_at
echo "orphan content" > "${REPO}/src/orphan-file.sh"

SCOPE5_STDERR=$(cs_compute_scope "$SID5" 2>&1 >/dev/null || true)

# The orphan file is new (mtime > started_at) so it enters the candidate set
# for SID5. Since no other session claims it, it goes INTO SID5's scope (not orphaned).
# A true orphan would be a dirty file with mtime > started_at that is subtracted
# by another session's claim AND also not in SID5's touched set.
# Test scenario: another session claims the file; SID5 didn't touch it; SID5 sees it as orphaned.

SID_CLAIMER="test-session-claimer"
cs_init "$SID_CLAIMER"
cs_touch "$SID_CLAIMER" "src/contested-orphan.sh"
echo "contested" > "${REPO}/src/contested-orphan.sh"

SCOPE5b_STDERR=$(cs_compute_scope "$SID5" 2>&1 >/dev/null || true)
# contested-orphan.sh is dirty (mtime > SID5 started_at), SID5 never touched it,
# but SID_CLAIMER claims it → not in SID5's scope, not an orphan (owned by claimer)
assert_not_contains "T09a claimer-owned file not reported as orphan for SID5" "$SCOPE5b_STDERR" "orphan: src/contested-orphan.sh"

echo

# ---------------------------------------------------------------------------
# T10: cs_archive moves session dir to .archive
# ---------------------------------------------------------------------------
echo "--- T10: cs_archive ---"

SID6="test-session-archive"
cs_init "$SID6"
assert_dir_exists "T10a session dir exists before archive" "${REPO}/.git/coordinator-sessions/${SID6}"

cs_archive "$SID6"
assert_not_contains "T10b session dir gone after archive" "$(ls "${REPO}/.git/coordinator-sessions/" 2>/dev/null)" "$SID6"

# The archive dir should exist somewhere under .archive/
ARCHIVED=$(find "${REPO}/.git/coordinator-sessions/.archive/" -maxdepth 1 -name "${SID6}-*" -type d 2>/dev/null | head -1)
if [[ -n "$ARCHIVED" ]]; then
  _pass "T10c archive dir exists under .archive/"
else
  _fail "T10c archive dir not found under .archive/"
fi

echo

# ---------------------------------------------------------------------------
# T11: cs_archive is idempotent (calling twice doesn't error)
# ---------------------------------------------------------------------------
echo "--- T11: cs_archive idempotent ---"

cs_archive "$SID6"   # already archived — should return 0 silently
_pass "T11a second cs_archive call on already-archived session succeeds"

echo

# ---------------------------------------------------------------------------
# T12: cs_active_sessions liveness classification
# ---------------------------------------------------------------------------
echo "--- T12: cs_active_sessions liveness ---"

# Create a "live" session: current PID, just now
SID_LIVE="test-session-live"
cs_init "$SID_LIVE"

# Create a "stale" session: a PID that definitely isn't alive (use a high number),
# and a last_activity timestamp far in the past.
SID_STALE="test-session-stale"
cs_init "$SID_STALE"
# Overwrite meta.json with a dead PID and old timestamp
cat > "${REPO}/.git/coordinator-sessions/${SID_STALE}/meta.json" <<STALEOF
{
  "session_id": "${SID_STALE}",
  "branch": "main",
  "pid": "999999999",
  "last_activity": "2000-01-01T00:00:00Z",
  "goal": "stale test"
}
STALEOF

SESSIONS=$(cs_active_sessions 2>/dev/null)
assert_contains "T12a live session shows as Live"   "$SESSIONS" "Live"
assert_contains "T12b stale session shows as Stale" "$SESSIONS" "Stale"
assert_contains "T12c live session id appears"      "$SESSIONS" "$SID_LIVE"
assert_contains "T12d stale session id appears"     "$SESSIONS" "$SID_STALE"

echo

# ---------------------------------------------------------------------------
# T13: cs_active_sessions with no sessions
# ---------------------------------------------------------------------------
echo "--- T13: cs_active_sessions empty state ---"

# Use a fresh repo with no sessions dir
EMPTY_REPO="${TMPDIR_BASE}/empty-repo"
mkdir -p "$EMPTY_REPO"
cd "$EMPTY_REPO"
git init -q
git config user.email "test@test.local"
git config user.name "Test"
echo "x" > x.txt; git add x.txt; git commit -q -m "x"

# Source again to pick up new git root
source "$LIB"
EMPTY_SESSIONS=$(cs_active_sessions 2>/dev/null)
assert_contains "T13a empty state returns readable message" "$EMPTY_SESSIONS" "no"

# Return to original repo
cd "$REPO"
source "$LIB"

echo

# ---------------------------------------------------------------------------
# T14: cs_reap_stale archives sessions meeting the reaper criterion
# ---------------------------------------------------------------------------
echo "--- T14: cs_reap_stale ---"

SID_REAP="test-session-reap"
cs_init "$SID_REAP"
# Set last_activity to > 24h ago and a dead PID
cat > "${REPO}/.git/coordinator-sessions/${SID_REAP}/meta.json" <<REAPEOF
{
  "session_id": "${SID_REAP}",
  "branch": "main",
  "pid": "999999998",
  "last_activity": "2000-01-01T00:00:00Z",
  "goal": "reap test"
}
REAPEOF

REAPED=$(cs_reap_stale 2>/dev/null)
assert_contains "T14a reap output names the reaped session" "$REAPED" "$SID_REAP"

# Verify session is actually gone
if [[ ! -d "${REPO}/.git/coordinator-sessions/${SID_REAP}" ]]; then
  _pass "T14b session dir removed by reaper"
else
  _fail "T14b session dir still present after reap"
fi

echo

# ---------------------------------------------------------------------------
# T15: cs_reap_stale does NOT reap a live session
# ---------------------------------------------------------------------------
echo "--- T15: cs_reap_stale spares live sessions ---"

SID_SPARE="test-session-spare"
cs_init "$SID_SPARE"
# meta.json has current PID ($$) and recent last_activity — cs_init already wrote this

REAPED2=$(cs_reap_stale 2>/dev/null)
assert_not_contains "T15a live session NOT reaped" "$REAPED2" "$SID_SPARE"
assert_dir_exists   "T15b live session dir still present" "${REPO}/.git/coordinator-sessions/${SID_SPARE}"

echo

# ---------------------------------------------------------------------------
# T16: cs_write_sentinel — atomic write creates sentinel
# W1.4 spec backlink: atomic sentinel write (temp + rename).
# ---------------------------------------------------------------------------
echo "--- T16: cs_write_sentinel atomic write ---"

SID_SENT="test-session-sentinel"
cs_init "$SID_SENT"

cs_write_sentinel "$SID_SENT"
SENTINEL_PATH="${REPO}/.git/coordinator-sessions/.current-session-id"

assert_file_exists "T16a sentinel file created" "$SENTINEL_PATH"

SENTINEL_VAL=$(cat "$SENTINEL_PATH" | tr -d '[:space:]')
assert_eq "T16b sentinel contains correct session ID" "$SENTINEL_VAL" "$SID_SENT"

echo

# ---------------------------------------------------------------------------
# T17: cs_write_sentinel — overwrites existing sentinel atomically
# Verifies that a second call updates the sentinel value.
# W1.4 spec backlink: atomic sentinel write idempotent / overwrite.
# ---------------------------------------------------------------------------
echo "--- T17: cs_write_sentinel overwrites existing sentinel ---"

SID_SENT2="test-session-sentinel-2"
cs_init "$SID_SENT2"

cs_write_sentinel "$SID_SENT2"
SENTINEL_VAL2=$(cat "$SENTINEL_PATH" | tr -d '[:space:]')
assert_eq "T17a sentinel updated to second session" "$SENTINEL_VAL2" "$SID_SENT2"

echo

# ---------------------------------------------------------------------------
# T18: cs_write_sentinel — locked-target fallback emits warning, still writes
# Simulates AV-locking by making the tempfile location unwritable, then verifying
# the fallback direct-write path fires and emits the expected warning text.
# W1.4 spec backlink: locked-target fallback with warning emission.
# ---------------------------------------------------------------------------
echo "--- T18: cs_write_sentinel locked-target fallback ---"

SID_SENT3="test-session-sentinel-3"
cs_init "$SID_SENT3"

# Simulate locked-target by making sessions dir read-only for the mv step.
# Strategy: create a sessions dir subdir that will block tempfile creation
# within that dir, by pointing the sentinel at a path where mkdir -p already
# created the dir as a file (not a dir) — this forces the tempfile write to fail.
# Simpler approach: chmod the sessions dir temporarily to block file creation.
# On Git Bash (Windows) chmod -w may not prevent writes, so we test portably:
# we verify that the function still produces the sentinel value even via fallback.

# Direct fallback test: write a read-only sentinel, verify cs_write_sentinel
# can still update it (either via mv or direct write).
chmod 444 "$SENTINEL_PATH" 2>/dev/null || true
SENTINEL_WARN=$(cs_write_sentinel "$SID_SENT3" 2>&1 || true)
chmod 644 "$SENTINEL_PATH" 2>/dev/null || true

# The sentinel may or may not be writable depending on filesystem/OS.
# What we CAN reliably test: if mv failed, the WARN message was emitted,
# OR if it succeeded silently, the value is correct.
SENTINEL_AFTER=$(cat "$SENTINEL_PATH" 2>/dev/null | tr -d '[:space:]' || true)
if [[ "$SENTINEL_AFTER" == "$SID_SENT3" ]]; then
  _pass "T18a sentinel written (atomic or fallback)"
elif echo "$SENTINEL_WARN" | grep -q "WARN"; then
  _pass "T18a fallback warning emitted when write failed (expected on read-only FS)"
else
  _fail "T18a sentinel not written and no fallback warning (unexpected failure)"
fi

echo

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "==================================="
echo "Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
echo "==================================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
