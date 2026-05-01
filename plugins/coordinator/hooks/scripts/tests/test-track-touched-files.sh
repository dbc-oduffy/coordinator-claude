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
# T9: W1.0b — meta.json.pid updated to $PPID (a live ancestor PID) on each fire
#
# The hook's $PPID is the calling bash process — which IS alive for the
# duration of this test. We record the current test-process PID before calling
# the hook; meta.json.pid must equal that value, and kill -0 must succeed.
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR/$SID"

EXPECTED_PARENT_PID=$$
make_input "Write" "src/alpha.ts" "$SID" | bash "$HOOK"

if [[ ! -f "$SESSIONS_DIR/$SID/meta.json" ]]; then
  fail "T9-ppid: meta.json not created"
else
  # Extract pid field — use jq if available, else grep+sed
  if command -v jq &>/dev/null; then
    RECORDED_PID=$(jq -r '.pid // empty' "$SESSIONS_DIR/$SID/meta.json" 2>/dev/null || true)
  else
    RECORDED_PID=$(grep -o '"pid"[[:space:]]*:[[:space:]]*"[^"]*"' "$SESSIONS_DIR/$SID/meta.json" \
      | sed 's/.*"pid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | head -1)
  fi

  if [[ "$RECORDED_PID" == "$EXPECTED_PARENT_PID" ]]; then
    # Verify the recorded PID is actually alive
    if kill -0 "$RECORDED_PID" 2>/dev/null; then
      pass "T9-ppid: meta.json.pid=$RECORDED_PID is live ancestor (kill -0 succeeds)"
    else
      fail "T9-ppid: meta.json.pid=$RECORDED_PID is set correctly but kill -0 failed (expected live)"
    fi
  else
    fail "T9-ppid: meta.json.pid=$RECORDED_PID, expected $EXPECTED_PARENT_PID (the test process PID)"
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
