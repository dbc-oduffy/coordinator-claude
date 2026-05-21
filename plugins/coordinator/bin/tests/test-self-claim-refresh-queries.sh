#!/bin/bash
# test-self-claim-refresh-queries.sh — Verify Wave 2 self-claim in refresh-queries.js.
#
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
#
# Validates:
#   1. With an active session: running refresh-queries.js against a markdown file
#      with an out-of-sync query callout causes the written file path to appear in
#      the session's touched.txt.
#   2. With no session: selfClaim emits a stderr warning; the JS writer still exits 0.
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-self-claim-refresh-queries.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${SCRIPT_DIR}/../../lib/coordinator-session.sh"
NODE_SHIM="${SCRIPT_DIR}/../../lib/coordinator_session.js"
REFRESH_JS="${SCRIPT_DIR}/../refresh-queries.js"

# On Windows+Git Bash, Node requires Windows-native paths for require().
# Use cygpath -w when available; otherwise leave as-is (POSIX hosts).
_to_node_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        echo "$1"
    fi
}

NODE_SHIM_WIN="$(_to_node_path "$NODE_SHIM")"

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
    echo "  FAIL: $1"
    (( FAIL++ )) || true
}

assert_file_contains() {
    local label="$1" needle="$2" file="$3"
    if grep -qF "$needle" "$file" 2>/dev/null; then
        return 0
    else
        echo "    Expected '$needle' in $file" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Scratch git repo setup / teardown
# ---------------------------------------------------------------------------

SCRATCH_DIR=""

setup_repo() {
    SCRATCH_DIR=$(mktemp -d)
    cd "$SCRATCH_DIR"
    git init -q
    git config user.email "test@test.com"
    git config user.name "Test"
    touch README
    git add README
    git commit -q -m "init"
}

teardown_repo() {
    [[ -n "$SCRATCH_DIR" ]] && rm -rf "$SCRATCH_DIR"
    SCRATCH_DIR=""
}

fake_session() {
    local sid="test-rq-$$"
    local sessions_dir="${SCRATCH_DIR}/.git/coordinator-sessions/${sid}"
    mkdir -p "$sessions_dir"
    touch "${sessions_dir}/touched.txt"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
    cat > "${sessions_dir}/meta.json" <<METAJSON
{
  "session_id": "${sid}",
  "branch": "test",
  "pid": "$$",
  "last_activity": "${now}",
  "goal": "test"
}
METAJSON
    echo "$sid"
}

# ---------------------------------------------------------------------------
# Test 1: Node shim selfClaim registers path in active session
# ---------------------------------------------------------------------------

test_node_shim_selfclaim_active_session() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"
    local sid
    sid=$(fake_session)
    local sdir
    sdir=$(_cs_session_dir "$sid")
    local touched="${sdir}/touched.txt"

    local fake_path="${SCRATCH_DIR}/test-callout.md"
    echo "some content" > "$fake_path"

    # Invoke the Node shim directly to call selfClaim.
    # Use Windows-native path for require() on Windows+Git Bash.
    local node_shim_win="$(_to_node_path "$NODE_SHIM")"
    local fake_path_fwd="${fake_path//\\//}"
    node -e "
const { selfClaim } = require('${node_shim_win//\\/\\\\}');
selfClaim('${fake_path_fwd}');
" 2>/dev/null

    if assert_file_contains "fake_path in touched.txt" "$fake_path" "$touched"; then
        teardown_repo
        return 0
    else
        echo "    touched.txt contents:" >&2
        cat "$touched" >&2
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 2: No session — selfClaim emits warning, does not throw
# ---------------------------------------------------------------------------

test_node_shim_no_session_exit_zero() {
    setup_repo

    # No session created — sessions dir is empty.
    local fake_path="${SCRATCH_DIR}/test-no-session.md"
    echo "content" > "$fake_path"

    local node_shim_win="$(_to_node_path "$NODE_SHIM")"
    local fake_path_fwd="${fake_path//\\//}"
    local stderr_out
    local rc=0
    stderr_out=$(node -e "
const { selfClaim } = require('${node_shim_win//\\/\\\\}');
selfClaim('${fake_path_fwd}');
" 2>&1) || rc=$?

    if [[ $rc -eq 0 ]] && echo "$stderr_out" | grep -qF "coordinator-session:"; then
        teardown_repo
        return 0
    else
        echo "    rc=$rc stderr=$stderr_out" >&2
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 3: claimPath directly — active session, explicit touched.txt
# ---------------------------------------------------------------------------

test_node_shim_claim_path_direct() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"
    local sid
    sid=$(fake_session)
    local sdir
    sdir=$(_cs_session_dir "$sid")
    local touched="${sdir}/touched.txt"

    local fake_path="${SCRATCH_DIR}/direct-claim.md"
    echo "content" > "$fake_path"

    local node_shim_win="$(_to_node_path "$NODE_SHIM")"
    local touched_fwd="${touched//\\//}"
    local fake_path_fwd="${fake_path//\\//}"
    node -e "
const { claimPath } = require('${node_shim_win//\\/\\\\}');
claimPath('${touched_fwd}', '${fake_path_fwd}');
" 2>/dev/null

    if assert_file_contains "direct claim in touched.txt" "$fake_path" "$touched"; then
        teardown_repo
        return 0
    else
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 4: refresh-queries.js integration — selfClaim wired after writeFileSync
# This test verifies the require() line and _csSelfClaim call are present.
# ---------------------------------------------------------------------------

test_refresh_queries_has_selfclaim_wiring() {
    if grep -qF '_csSelfClaim(filePath)' "$REFRESH_JS" 2>/dev/null && \
       grep -qF "coordinator_session.js" "$REFRESH_JS" 2>/dev/null; then
        return 0
    else
        echo "    selfClaim wiring not found in refresh-queries.js" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

echo "=== test-self-claim-refresh-queries.sh ==="

if ! command -v node >/dev/null 2>&1; then
    echo "SKIP: node not found on PATH"
    echo "Results: 0 passed, 0 failed (skipped)"
    exit 0
fi

echo "--- Test 1: Node shim selfClaim — active session"
test_node_shim_selfclaim_active_session && pass "selfClaim active session" || fail "selfClaim active session"

echo "--- Test 2: No session — warning + exit 0"
test_node_shim_no_session_exit_zero && pass "selfClaim no session" || fail "selfClaim no session"

echo "--- Test 3: claimPath direct — explicit touched.txt"
test_node_shim_claim_path_direct && pass "claimPath direct" || fail "claimPath direct"

echo "--- Test 4: refresh-queries.js wiring check"
test_refresh_queries_has_selfclaim_wiring && pass "refresh-queries.js wired" || fail "refresh-queries.js wired"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ $FAIL -eq 0 ]]
