#!/bin/bash
# Tests for session-init.sh
#
# Tests:
#   T1. Hook creates session dir on first invocation
#   T2. Hook writes .current-session-id sentinel matching session_id from input
#   T3. Hook is idempotent — re-running with same session_id refreshes meta only
#   T4. Hook fast-exits with empty input
#   T5. Hook fast-exits with missing session_id
#   T6. Hook fast-exits when not in a git repo
#   T7. Sentinel reflects last-writer-wins on session_id collision

set -euo pipefail

HOOK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../session-init.sh"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook script not found at $HOOK_SCRIPT" >&2
  exit 1
fi

PASS=0
FAIL=0
pass() { echo "PASS: $1"; (( PASS++ )) || true; }
fail() { echo "FAIL: $1  =>  ${2:-}"; (( FAIL++ )) || true; }

TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t session-init-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

REPO="$TMPDIR_BASE/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "test@test.com"
git config user.name "Test"
touch README.md && git add README.md && git commit -q -m "init"

SESSIONS_DIR="$REPO/.git/coordinator-sessions"
SENTINEL="$SESSIONS_DIR/.current-session-id"

make_input() {
  local sid="$1"
  printf '{"session_id":"%s","source":"startup"}' "$sid"
}

# ---------------------------------------------------------------------------
# T1: Session dir creation
# ---------------------------------------------------------------------------
SID="sid-T1-abc123"
make_input "$SID" | bash "$HOOK_SCRIPT"
EXIT=$?
if [[ "$EXIT" -ne 0 ]]; then
  fail "T1" "hook exited with $EXIT"
elif [[ ! -d "$SESSIONS_DIR/$SID" ]]; then
  fail "T1" "session dir not created at $SESSIONS_DIR/$SID"
elif [[ ! -f "$SESSIONS_DIR/$SID/meta.json" ]]; then
  fail "T1" "meta.json not created"
elif [[ ! -f "$SESSIONS_DIR/$SID/touched.txt" ]]; then
  fail "T1" "touched.txt not created"
else
  pass "T1: session dir created with meta.json + touched.txt"
fi

# ---------------------------------------------------------------------------
# T2: Sentinel write
# ---------------------------------------------------------------------------
if [[ ! -f "$SENTINEL" ]]; then
  fail "T2" "sentinel file not created"
elif [[ "$(cat "$SENTINEL")" != "$SID" ]]; then
  fail "T2" "sentinel content '$(cat "$SENTINEL")' != expected '$SID'"
else
  pass "T2: sentinel written with correct session_id"
fi

# ---------------------------------------------------------------------------
# T3: Idempotency — re-run with same SID
# ---------------------------------------------------------------------------
ORIG_STARTED_AT=$(cat "$SESSIONS_DIR/$SID/started_at")
sleep 1
make_input "$SID" | bash "$HOOK_SCRIPT"
EXIT=$?
NEW_STARTED_AT=$(cat "$SESSIONS_DIR/$SID/started_at")
if [[ "$EXIT" -ne 0 ]]; then
  fail "T3" "second invocation exited with $EXIT"
elif [[ "$ORIG_STARTED_AT" != "$NEW_STARTED_AT" ]]; then
  fail "T3" "started_at changed on re-run (was '$ORIG_STARTED_AT', now '$NEW_STARTED_AT')"
else
  pass "T3: idempotent — started_at preserved on re-run"
fi

# ---------------------------------------------------------------------------
# T4: Empty input fast-exits
# ---------------------------------------------------------------------------
echo "" | bash "$HOOK_SCRIPT"
EXIT=$?
if [[ "$EXIT" -ne 0 ]]; then
  fail "T4" "empty input should exit 0, got $EXIT"
else
  pass "T4: empty input exits 0"
fi

# ---------------------------------------------------------------------------
# T5: Missing session_id fast-exits
# ---------------------------------------------------------------------------
echo '{"source":"startup"}' | bash "$HOOK_SCRIPT"
EXIT=$?
if [[ "$EXIT" -ne 0 ]]; then
  fail "T5" "missing session_id should exit 0, got $EXIT"
else
  pass "T5: missing session_id exits 0"
fi

# ---------------------------------------------------------------------------
# T6: Not-in-git-repo fast-exits
# ---------------------------------------------------------------------------
NON_REPO_DIR="$TMPDIR_BASE/not-a-repo"
mkdir -p "$NON_REPO_DIR"
(cd "$NON_REPO_DIR" && make_input "sid-T6" | bash "$HOOK_SCRIPT")
EXIT=$?
if [[ "$EXIT" -ne 0 ]]; then
  fail "T6" "non-repo invocation should exit 0, got $EXIT"
else
  pass "T6: non-repo invocation exits 0"
fi

# ---------------------------------------------------------------------------
# T7: Sentinel last-writer-wins on collision
# ---------------------------------------------------------------------------
SID_A="sid-T7-A"
SID_B="sid-T7-B"
make_input "$SID_A" | bash "$HOOK_SCRIPT"
make_input "$SID_B" | bash "$HOOK_SCRIPT"
ACTUAL=$(cat "$SENTINEL")
if [[ "$ACTUAL" != "$SID_B" ]]; then
  fail "T7" "expected sentinel='$SID_B' (last writer), got '$ACTUAL'"
elif [[ ! -d "$SESSIONS_DIR/$SID_A" ]]; then
  fail "T7" "session A dir was lost (should persist independent of sentinel)"
elif [[ ! -d "$SESSIONS_DIR/$SID_B" ]]; then
  fail "T7" "session B dir was lost"
else
  pass "T7: sentinel last-writer-wins; both session dirs persist"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "===================="
echo "PASS: $PASS  FAIL: $FAIL"
echo "===================="

[[ "$FAIL" -eq 0 ]]
