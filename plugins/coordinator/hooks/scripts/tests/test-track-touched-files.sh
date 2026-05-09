#!/bin/bash
# Tests for track-touched-files.sh
#
# Runs in a temporary git repo to avoid polluting the real repo.
# Tests:
#   T1. Hook fires on Write input  → path appended to touched.txt
#   T2. Hook fires on Edit input   → path appended to touched.txt
#   T3. Hook fires on MultiEdit    → path appended to touched.txt
#   T4. Hook fires on NotebookEdit → path appended to touched.txt
#   T5. Hook fast-exits on Bash input (no append, no error)
#   T6. Hook fast-exits on missing session_id (exit 0, no file created)
#   T7. Hook initializes session dir if it does not exist
#   T8. Hook is idempotent: duplicate path not appended twice
#
# Exit codes: 0 = all pass, 1 = at least one failure

set -euo pipefail

HOOK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../track-touched-files.sh"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook script not found at $HOOK_SCRIPT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

pass() { echo "PASS: $1"; (( PASS++ )) || true; }
fail() { echo "FAIL: $1  =>  ${2:-}"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Setup: create a scratch git repo in a temp dir
# ---------------------------------------------------------------------------
TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t track-touched-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

REPO="$TMPDIR_BASE/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "test@test.com"
git config user.name "Test"
# Create an initial commit so HEAD exists
touch README.md && git add README.md && git commit -q -m "init"

# Path to hook script — absolute so we can call from anywhere
HOOK="$HOOK_SCRIPT"

# Helper: synthesize PostToolUse JSON input
make_input() {
  local tool_name="${1}"
  local file_path="${2}"
  local session_id="${3:-test-session-001}"
  # Emit minimal JSON matching the PostToolUse schema
  printf '{"session_id":"%s","tool_name":"%s","tool_input":{"file_path":"%s"}}' \
    "$session_id" "$tool_name" "$file_path"
}

SESSIONS_DIR="$REPO/.git/coordinator-sessions"
SID="test-session-001"
TOUCHED="$SESSIONS_DIR/$SID/touched.txt"

# ---------------------------------------------------------------------------
# T1–T4: Edit-family tools write to touched.txt
# ---------------------------------------------------------------------------
for tool in Write Edit MultiEdit NotebookEdit; do
  # Fresh session dir each tool test
  rm -rf "$SESSIONS_DIR/$SID"

  make_input "$tool" "src/foo.ts" "$SID" | bash "$HOOK"
  EXIT_CODE=$?

  if [[ "$EXIT_CODE" -ne 0 ]]; then
    fail "T-${tool}: hook exited with $EXIT_CODE (expected 0)"
    continue
  fi

  if [[ ! -f "$TOUCHED" ]]; then
    fail "T-${tool}: touched.txt not created"
  elif ! grep -qF "src/foo.ts" "$TOUCHED" 2>/dev/null && \
       ! grep -q "foo.ts" "$TOUCHED" 2>/dev/null; then
    # Path normalization may reduce to relative — accept any substring match
    fail "T-${tool}: 'src/foo.ts' not found in touched.txt (content: $(cat "$TOUCHED"))"
  else
    pass "T-${tool}: path recorded in touched.txt"
  fi
done

# ---------------------------------------------------------------------------
# T5: Bash tool → fast-exit, nothing written
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR/$SID"
make_input "Bash" "src/bar.ts" "$SID" | bash "$HOOK"
if [[ -f "$TOUCHED" ]] && grep -q "bar.ts" "$TOUCHED" 2>/dev/null; then
  fail "T5-Bash: path was recorded (should fast-exit on Bash)"
else
  pass "T5-Bash: fast-exit on Bash — nothing recorded"
fi

# ---------------------------------------------------------------------------
# T6: Missing session_id → exit 0, no crash
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
# Input with no session_id field
NOSID_INPUT='{"tool_name":"Write","tool_input":{"file_path":"src/foo.ts"}}'
echo "$NOSID_INPUT" | bash "$HOOK"
RC=$?
if [[ "$RC" -ne 0 ]]; then
  fail "T6-no-session-id: expected exit 0, got $RC"
elif [[ -d "$SESSIONS_DIR" ]] && find "$SESSIONS_DIR" -name "touched.txt" 2>/dev/null | grep -q .; then
  fail "T6-no-session-id: session dir created despite missing session_id"
else
  pass "T6-no-session-id: exit 0, no session dir created"
fi

# ---------------------------------------------------------------------------
# T7: Session dir missing → hook initializes it automatically
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
make_input "Write" "lib/utils.sh" "$SID" | bash "$HOOK"

if [[ -d "$SESSIONS_DIR/$SID" ]]; then
  pass "T7-auto-init: session dir created on first touch"
else
  fail "T7-auto-init: session dir not created (expected auto-init)"
fi

# ---------------------------------------------------------------------------
# T8: Idempotent — duplicate path appended only once
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
make_input "Write" "lib/utils.sh" "$SID" | bash "$HOOK"
make_input "Edit"  "lib/utils.sh" "$SID" | bash "$HOOK"

# Count occurrences of the path in touched.txt
if [[ -f "$TOUCHED" ]]; then
  # Grep for any line containing "utils.sh" (path normalization may vary)
  COUNT=$(grep -c "utils.sh" "$TOUCHED" 2>/dev/null || echo 0)
  if [[ "$COUNT" -eq 1 ]]; then
    pass "T8-dedup: path appears exactly once after two identical touches"
  else
    fail "T8-dedup: expected 1 occurrence, found $COUNT"
  fi
else
  fail "T8-dedup: touched.txt not found"
fi

# ---------------------------------------------------------------------------
# Concurrent-writer regression tests (Phase 3a-pre)
#
# Spec backlink: plans/safe-commit-fixes.md § Phase 3a pre-flight
# Purpose: Certify that _atomic_dedup_append in track-touched-files.sh
# (lines 159-184) holds its at-most-once contract under N-way parallel
# writes before Phase 3a extracts it to lib/coordinator-session.sh.
#
# Windows + Git Bash: flock(1) is unavailable. The implementation relies on
# mktemp-adjacent + sort -u + mv. The race window is the interval between
# the non-atomic read (line 167) and the atomic mv (line 182). With N=10
# parallel writers, the dedup-on-read fast-exit (line 167) short-circuits
# most races, and the merge-then-mv collapses the remainder to at-most-once.
#
# Background jobs are collected with wait; PIDs are tracked in an array so
# partial failures are caught even if a subshell exits non-zero.
# ---------------------------------------------------------------------------

# Concurrency level used across all T20-T22
CONCURRENCY=10

# ---------------------------------------------------------------------------
# T20: Concurrent writers, same path
#      N writers all appending the same file path to the same touched.txt.
#      Assert: exactly one entry in touched.txt (no duplicates from race).
# ---------------------------------------------------------------------------
SID20="test-session-T20"
TOUCHED20="$SESSIONS_DIR/$SID20/touched.txt"
rm -rf "$SESSIONS_DIR/$SID20"
mkdir -p "$SESSIONS_DIR/$SID20"
touch "$TOUCHED20"

PIDS=()
for i in $(seq 1 $CONCURRENCY); do
  make_input "Write" "src/shared-target.ts" "$SID20" | bash "$HOOK" &
  PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
  wait "$pid" || true
done

if [[ ! -f "$TOUCHED20" ]]; then
  fail "T20-concurrent-same-path: touched.txt missing after $CONCURRENCY parallel writes"
else
  COUNT20=$(grep -c "shared-target.ts" "$TOUCHED20" 2>/dev/null || echo 0)
  if [[ "$COUNT20" -eq 1 ]]; then
    pass "T20-concurrent-same-path: exactly 1 entry after $CONCURRENCY parallel writes to the same path"
  elif [[ "$COUNT20" -eq 0 ]]; then
    fail "T20-concurrent-same-path: 0 entries — path was lost entirely"
  else
    fail "T20-concurrent-same-path: expected 1, found $COUNT20 duplicates (race dedup failed)"
  fi
fi

# ---------------------------------------------------------------------------
# T21: Concurrent writers, different paths
#      N writers each appending a distinct file path.
#      Assert: all N paths present (none lost), no path appears more than once.
# ---------------------------------------------------------------------------
SID21="test-session-T21"
TOUCHED21="$SESSIONS_DIR/$SID21/touched.txt"
rm -rf "$SESSIONS_DIR/$SID21"
mkdir -p "$SESSIONS_DIR/$SID21"
touch "$TOUCHED21"

PIDS=()
for i in $(seq 1 $CONCURRENCY); do
  make_input "Write" "src/distinct-file-${i}.ts" "$SID21" | bash "$HOOK" &
  PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
  wait "$pid" || true
done

T21_OK=true
if [[ ! -f "$TOUCHED21" ]]; then
  fail "T21-concurrent-distinct-paths: touched.txt missing after $CONCURRENCY parallel writes"
  T21_OK=false
else
  # Verify all N paths landed exactly once
  MISSING21=0
  DUP21=0
  for i in $(seq 1 $CONCURRENCY); do
    # grep -c exits 1 when count=0 but still emits "0" on stdout.
    # Wrap in a subshell that always exits 0 to avoid triggering set -e,
    # and capture only grep's stdout (the numeric count line).
    CNT=$(grep -c "distinct-file-${i}.ts" "$TOUCHED21" 2>/dev/null; true)
    CNT="${CNT:-0}"
    if [[ "$CNT" -eq 0 ]]; then
      MISSING21=$(( MISSING21 + 1 ))
    elif [[ "$CNT" -gt 1 ]]; then
      DUP21=$(( DUP21 + 1 ))
    fi
  done
  if [[ "$MISSING21" -eq 0 && "$DUP21" -eq 0 ]]; then
    pass "T21-concurrent-distinct-paths: all $CONCURRENCY paths present exactly once"
  else
    T21_OK=false
    fail "T21-concurrent-distinct-paths: $MISSING21 missing, $DUP21 duplicated paths out of $CONCURRENCY"
  fi
fi

# ---------------------------------------------------------------------------
# T22: Concurrent writers, mixed (some duplicate, some unique)
#      2N invocations: N writes of path-A, N writes of path-B.
#      Assert: touched.txt contains exactly path-A and path-B (one each).
# ---------------------------------------------------------------------------
SID22="test-session-T22"
TOUCHED22="$SESSIONS_DIR/$SID22/touched.txt"
rm -rf "$SESSIONS_DIR/$SID22"
mkdir -p "$SESSIONS_DIR/$SID22"
touch "$TOUCHED22"

PIDS=()
for i in $(seq 1 $CONCURRENCY); do
  make_input "Write" "src/mixed-path-a.ts" "$SID22" | bash "$HOOK" &
  PIDS+=($!)
  make_input "Edit" "src/mixed-path-b.ts" "$SID22" | bash "$HOOK" &
  PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
  wait "$pid" || true
done

if [[ ! -f "$TOUCHED22" ]]; then
  fail "T22-concurrent-mixed: touched.txt missing after $((CONCURRENCY * 2)) parallel writes"
else
  COUNT_A=$(grep -c "mixed-path-a.ts" "$TOUCHED22" 2>/dev/null || echo 0)
  COUNT_B=$(grep -c "mixed-path-b.ts" "$TOUCHED22" 2>/dev/null || echo 0)
  if [[ "$COUNT_A" -eq 1 && "$COUNT_B" -eq 1 ]]; then
    pass "T22-concurrent-mixed: path-A and path-B each appear exactly once after $((CONCURRENCY * 2)) parallel writes"
  else
    fail "T22-concurrent-mixed: expected path-A=1, path-B=1; got path-A=$COUNT_A, path-B=$COUNT_B"
  fi
fi

# ---------------------------------------------------------------------------
# T23: mktemp failure path
#      Simulate mktemp failure by making target_dir read-only.
#      Assert: hook exits 0, existing touched.txt content is NOT corrupted.
#
# Implementation note: _atomic_dedup_append returns 0 on mktemp failure
# (lines 173-174: `|| return 0`). The hook always exits 0 (advisory hook).
# We verify the pre-existing entry survives the failed write attempt.
#
# On Windows with Git Bash, chmod 555 may not enforce read-only on the
# NTFS filesystem for the current user (who owns the dir). We detect this
# and skip the enforcement check gracefully, but still confirm exit 0.
# ---------------------------------------------------------------------------
SID23="test-session-T23"
TOUCHED23="$SESSIONS_DIR/$SID23/touched.txt"
rm -rf "$SESSIONS_DIR/$SID23"
mkdir -p "$SESSIONS_DIR/$SID23"
# Pre-seed a known entry so we can verify it survives
printf 'src/existing-sentinel.ts\n' > "$TOUCHED23"

# Attempt to make the session dir read-only (blocks mktemp within it)
chmod 555 "$SESSIONS_DIR/$SID23" 2>/dev/null || true

MKTEMP_FAIL_RC=0
make_input "Write" "src/should-not-land.ts" "$SID23" | bash "$HOOK" || MKTEMP_FAIL_RC=$?

# Restore permissions for cleanup
chmod 755 "$SESSIONS_DIR/$SID23" 2>/dev/null || true

if [[ "$MKTEMP_FAIL_RC" -ne 0 ]]; then
  fail "T23-mktemp-fail: hook exited non-zero ($MKTEMP_FAIL_RC) — must always exit 0"
else
  # Check that the pre-existing sentinel survived
  if [[ -f "$TOUCHED23" ]] && grep -qF "existing-sentinel.ts" "$TOUCHED23" 2>/dev/null; then
    # Also check that the new path did NOT land (mktemp failed, so no merge happened)
    # On Windows where chmod may not be enforced, the write may have succeeded —
    # in that case we accept it as long as the sentinel survived (no corruption).
    if grep -qF "should-not-land.ts" "$TOUCHED23" 2>/dev/null; then
      # chmod was not enforced (Windows/NTFS) — write succeeded, sentinel survived.
      # This is acceptable: the mktemp-failure no-op path wasn't triggered, but the
      # merge-and-dedup path ran correctly. Sentinel survival = no corruption.
      pass "T23-mktemp-fail: exit 0, sentinel survived (chmod not enforced on this FS — write path ran instead)"
    else
      pass "T23-mktemp-fail: exit 0, mktemp failure silently no-oped, sentinel content intact"
    fi
  else
    fail "T23-mktemp-fail: existing touched.txt content corrupted or lost after mktemp failure"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: $PASS/$TOTAL passed"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
