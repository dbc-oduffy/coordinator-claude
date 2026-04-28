#!/bin/bash
# Tests for validate-commit.sh — scope guard (Check 5) and regression tests.
#
# Tests:
#   S1. Staged file in MY_SCOPE (own touched.txt) → no warning emitted
#   S2. Staged file outside MY_SCOPE, in another session's touch list → warning emitted, scope-warnings.log written, exit 0
#   S3. Staged file outside MY_SCOPE, no claimant → orphan warning, log entry, exit 0
#   S4. COORDINATOR_SCOPE_STRICT=1 with foreign files → exit 0 + JSON deny on stdout
#   S5. COORDINATOR_SCOPE_STRICT=1 with COORDINATOR_OVERRIDE_SCOPE=1 → exit 0, override logged
#   S6. Regression: gitignore check (Check 1) still fires correctly
#   S7. Regression: JSON validity check (Check 2) still fires correctly
#   S8. Regression: empty JSONL check (Check 4) still fires correctly
#   S9. No staged files → clean exit 0
#
# NOTE: We test the scope guard by injecting a session_id into the JSON input.
# The hook reads session_id from the same INPUT blob that carries the git command.
# For scope tests we need a real .git dir, staged files, and coordinator-sessions dirs.

set -euo pipefail

HOOK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../validate-commit.sh"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: validate-commit.sh not found at $HOOK_SCRIPT" >&2
  exit 1
fi

PASS=0
FAIL=0

pass() { echo "PASS: $1"; (( PASS++ )) || true; }
fail() { echo "FAIL: $1  =>  ${2:-}"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Setup: scratch git repo
# ---------------------------------------------------------------------------
TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t validate-scope-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

REPO="$TMPDIR_BASE/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "test@test.com"
git config user.name "Test"
touch README.md && git add README.md && git commit -q -m "init"

SESSIONS_DIR="$REPO/.git/coordinator-sessions"
MY_SID="my-session-aaa"
OTHER_SID="other-session-bbb"

# Helper: build hook input JSON (PreToolUse for Bash with git commit)
make_commit_input() {
  local session_id="${1:-}"
  local command="${2:-git commit -m 'test'}"
  if [[ -n "$session_id" ]]; then
    printf '{"session_id":"%s","tool_name":"Bash","tool_input":{"command":"%s"}}' \
      "$session_id" "$command"
  else
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$command"
  fi
}

# Helper: initialize a session's touched.txt
init_session_touch() {
  local sid="$1"
  shift
  mkdir -p "$SESSIONS_DIR/$sid"
  printf '%s\n' "$@" > "$SESSIONS_DIR/$sid/touched.txt"
  echo "2026-04-27T00:00:00Z" > "$SESSIONS_DIR/$sid/started_at"
  cat > "$SESSIONS_DIR/$sid/meta.json" <<EOF
{"session_id":"${sid}","branch":"main","pid":"99999","last_activity":"2026-04-27T00:00:00Z","goal":"test"}
EOF
}

# ---------------------------------------------------------------------------
# S1: Staged file in MY_SCOPE → no scope warning
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
echo "owned-file content" > "owned-file.txt"
git add "owned-file.txt"
init_session_touch "$MY_SID" "owned-file.txt"

OUTPUT=$(make_commit_input "$MY_SID" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S1-in-scope: expected exit 0, got $RC"
elif echo "$OUTPUT" | grep -q "SCOPE:"; then
  fail "S1-in-scope: unexpected SCOPE warning: $OUTPUT"
else
  pass "S1-in-scope: no scope warning for own file"
fi

# Clean staged file
git restore --staged "owned-file.txt" 2>/dev/null || git rm --cached "owned-file.txt" 2>/dev/null || true
rm -f "owned-file.txt"

# ---------------------------------------------------------------------------
# S2: Staged file outside MY_SCOPE, in another session's touch list → warning, log, exit 0
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
echo "other content" > "other-file.txt"
git add "other-file.txt"

# My session knows nothing about other-file.txt
init_session_touch "$MY_SID" "owned-file.txt"
# Other session claims other-file.txt
init_session_touch "$OTHER_SID" "other-file.txt"

OUTPUT=$(make_commit_input "$MY_SID" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S2-foreign-owned: expected exit 0, got $RC"
elif ! echo "$OUTPUT" | grep -q "SCOPE:"; then
  fail "S2-foreign-owned: expected SCOPE warning, got: $OUTPUT"
elif ! echo "$OUTPUT" | grep -q "$OTHER_SID"; then
  fail "S2-foreign-owned: warning should mention owner session $OTHER_SID; got: $OUTPUT"
elif [[ ! -f "$SESSIONS_DIR/$MY_SID/scope-warnings.log" ]]; then
  fail "S2-foreign-owned: scope-warnings.log not created"
elif ! grep -q "other-file.txt" "$SESSIONS_DIR/$MY_SID/scope-warnings.log" 2>/dev/null; then
  fail "S2-foreign-owned: other-file.txt not logged in scope-warnings.log"
else
  pass "S2-foreign-owned: warning emitted, log written, exit 0"
fi

git restore --staged "other-file.txt" 2>/dev/null || git rm --cached "other-file.txt" 2>/dev/null || true
rm -f "other-file.txt"

# ---------------------------------------------------------------------------
# S3: Staged file outside MY_SCOPE, no claimant → orphan warning, log, exit 0
#
# "Orphan" here means: staged, NOT in any session's touched.txt, and NOT
# picked up by the mtime fallback (because mtime predates this session's
# started_at). We simulate this by setting started_at to a future timestamp
# so the mtime fallback adds nothing, and the file isn't in any touched.txt.
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
echo "orphan content" > "orphan-file.txt"
git add "orphan-file.txt"

# My session started_at is set to a far-future time so no dirty file's mtime
# qualifies for the mtime fallback. The orphan-file.txt therefore lands
# outside MY_SCOPE entirely.
mkdir -p "$SESSIONS_DIR/$MY_SID"
echo "2099-01-01T00:00:00Z" > "$SESSIONS_DIR/$MY_SID/started_at"
echo "owned-file.txt" > "$SESSIONS_DIR/$MY_SID/touched.txt"
cat > "$SESSIONS_DIR/$MY_SID/meta.json" <<EOF
{"session_id":"${MY_SID}","branch":"main","pid":"99999","last_activity":"2026-04-27T00:00:00Z","goal":"test"}
EOF

OUTPUT=$(make_commit_input "$MY_SID" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S3-orphan: expected exit 0, got $RC"
elif ! echo "$OUTPUT" | grep -q "SCOPE:"; then
  fail "S3-orphan: expected SCOPE warning for orphan, got: $OUTPUT"
elif ! echo "$OUTPUT" | grep -q "orphan"; then
  fail "S3-orphan: expected 'orphan' in warning, got: $OUTPUT"
elif [[ ! -f "$SESSIONS_DIR/$MY_SID/scope-warnings.log" ]]; then
  fail "S3-orphan: scope-warnings.log not created"
else
  pass "S3-orphan: orphan warning emitted, log written, exit 0"
fi

git restore --staged "orphan-file.txt" 2>/dev/null || git rm --cached "orphan-file.txt" 2>/dev/null || true
rm -f "orphan-file.txt"

# ---------------------------------------------------------------------------
# S4: COORDINATOR_SCOPE_STRICT=1 with foreign files → exit 0 + JSON deny on stdout
#
# The hook uses the modern PreToolUse JSON output form
# (hookSpecificOutput.permissionDecision = "deny"), which requires exit 0
# so the JSON gets parsed by Claude Code. See coordinator/docs/preooluse-deny-contract.md.
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
echo "strict-test content" > "foreign-strict.txt"
git add "foreign-strict.txt"

# My session doesn't own foreign-strict.txt; OTHER session claims it.
init_session_touch "$MY_SID" "owned-file.txt"
init_session_touch "$OTHER_SID" "foreign-strict.txt"

# Capture stdout and stderr separately so we can verify the JSON went to stdout.
set +e
STDOUT=$(make_commit_input "$MY_SID" "git commit -m 'test'" | COORDINATOR_SCOPE_STRICT=1 bash "$HOOK_SCRIPT" 2>/dev/null)
RC=$?
set -e

if [[ "$RC" -ne 0 ]]; then
  fail "S4-strict-block: expected exit 0 (JSON form), got $RC"
elif ! echo "$STDOUT" | grep -q '"permissionDecision":"deny"'; then
  fail "S4-strict-block: expected permissionDecision=deny in stdout JSON, got: $STDOUT"
elif ! echo "$STDOUT" | grep -q '"hookEventName":"PreToolUse"'; then
  fail "S4-strict-block: expected hookEventName=PreToolUse in stdout JSON, got: $STDOUT"
elif ! echo "$STDOUT" | grep -q "foreign-strict.txt"; then
  fail "S4-strict-block: expected reason to mention foreign-strict.txt, got: $STDOUT"
else
  pass "S4-strict-block: COORDINATOR_SCOPE_STRICT=1 → exit 0 + JSON deny with file in reason"
fi

git restore --staged "foreign-strict.txt" 2>/dev/null || git rm --cached "foreign-strict.txt" 2>/dev/null || true
rm -f "foreign-strict.txt"

# ---------------------------------------------------------------------------
# S5: COORDINATOR_SCOPE_STRICT=1 + COORDINATOR_OVERRIDE_SCOPE=1 → exit 0, override logged
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
echo "override content" > "foreign-override.txt"
git add "foreign-override.txt"

init_session_touch "$MY_SID" "owned-file.txt"
init_session_touch "$OTHER_SID" "foreign-override.txt"

OUTPUT=$(make_commit_input "$MY_SID" "git commit -m 'test'" | COORDINATOR_SCOPE_STRICT=1 COORDINATOR_OVERRIDE_SCOPE=1 bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S5-override: expected exit 0, got $RC"
elif [[ ! -f "$SESSIONS_DIR/$MY_SID/overrides.log" ]]; then
  fail "S5-override: overrides.log not created"
elif ! grep -q "OVERRIDE" "$SESSIONS_DIR/$MY_SID/overrides.log" 2>/dev/null; then
  fail "S5-override: 'OVERRIDE' not found in overrides.log"
else
  pass "S5-override: COORDINATOR_OVERRIDE_SCOPE=1 → exit 0, override logged"
fi

git restore --staged "foreign-override.txt" 2>/dev/null || git rm --cached "foreign-override.txt" 2>/dev/null || true
rm -f "foreign-override.txt"

# ---------------------------------------------------------------------------
# S6: Regression — gitignore check (Check 1) still fires
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
# Create a .gitignore that adds a pattern matching a curated dir
echo "data/" >> .gitignore
git add .gitignore

OUTPUT=$(make_commit_input "" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S6-gitignore-regression: expected exit 0, got $RC"
elif ! echo "$OUTPUT" | grep -qi "GITIGNORE"; then
  fail "S6-gitignore-regression: expected GITIGNORE warning, got: $OUTPUT"
else
  pass "S6-gitignore-regression: gitignore check still fires"
fi

git restore --staged .gitignore 2>/dev/null || git rm --cached .gitignore 2>/dev/null || true
# Restore clean .gitignore
git checkout -- .gitignore 2>/dev/null || rm -f .gitignore

# ---------------------------------------------------------------------------
# S7: Regression — JSON validity check (Check 2) still fires
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
mkdir -p data/
echo '{invalid json}' > data/bad.json
git add data/bad.json

OUTPUT=$(make_commit_input "" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S7-json-regression: expected exit 0, got $RC"
elif ! echo "$OUTPUT" | grep -qi "JSON"; then
  fail "S7-json-regression: expected JSON warning, got: $OUTPUT"
else
  pass "S7-json-regression: JSON validity check still fires"
fi

git restore --staged data/bad.json 2>/dev/null || git rm --cached data/bad.json 2>/dev/null || true
rm -rf data/

# ---------------------------------------------------------------------------
# S8: Regression — empty JSONL check (Check 4) still fires
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
mkdir -p chunks/
touch chunks/empty.jsonl
git add chunks/empty.jsonl

OUTPUT=$(make_commit_input "" "git commit -m 'test'" | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?

if [[ "$RC" -ne 0 ]]; then
  fail "S8-jsonl-regression: expected exit 0, got $RC"
elif ! echo "$OUTPUT" | grep -qi "CHUNKS"; then
  fail "S8-jsonl-regression: expected CHUNKS warning, got: $OUTPUT"
else
  pass "S8-jsonl-regression: empty JSONL check still fires"
fi

git restore --staged chunks/empty.jsonl 2>/dev/null || git rm --cached chunks/empty.jsonl 2>/dev/null || true
rm -rf chunks/

# ---------------------------------------------------------------------------
# S9: Non-commit Bash command → clean fast-exit (no staged files doesn't matter)
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
OUTPUT=$(printf '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | bash "$HOOK_SCRIPT" 2>&1 || true)
RC=$?
if [[ "$RC" -ne 0 ]]; then
  fail "S9-non-commit-fast-exit: expected exit 0, got $RC"
elif [[ -n "$OUTPUT" ]]; then
  fail "S9-non-commit-fast-exit: expected no output, got: $OUTPUT"
else
  pass "S9-non-commit-fast-exit: non-commit Bash exits silently"
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
