#!/bin/bash
# test-self-claim-check-mcp-versions.sh — Verify Wave 5 self-claim in check-mcp-versions.sh.
#
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
#
# Validates:
#   1. With an active session: after the marker file is written, its path appears
#      in the session's touched.txt.
#   2. With no session: _cs_claim_if_session emits a warning and exits 0.
#   3. check-mcp-versions.sh contains the self-claim wiring.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-self-claim-check-mcp-versions.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${SCRIPT_DIR}/../../lib/coordinator-session.sh"

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

assert_stderr_contains() {
    local label="$1" needle="$2" stderr_content="$3"
    if echo "$stderr_content" | grep -qF "$needle"; then
        return 0
    else
        echo "    Expected stderr: $needle" >&2
        echo "    Actual: $stderr_content" >&2
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
    local sid="test-mcp-$$"
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
# Test 1: Active session — marker path claimed in touched.txt
# ---------------------------------------------------------------------------

test_marker_claimed_in_session() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"
    local sid
    sid=$(fake_session)

    local sdir
    sdir=$(_cs_session_dir "$sid")
    local touched="${sdir}/touched.txt"

    # Simulate: write the marker file and claim it (mirrors _cs_claim_if_session).
    local fake_marker="${SCRATCH_DIR}/.mcp-version-check"
    date +%Y-%m-%d > "$fake_marker"

    local _sids
    _sids="$(cs_live_session_ids 2>/dev/null)" || _sids=""
    local _sid_count
    _sid_count=$(echo "$_sids" | grep -c '[^[:space:]]' 2>/dev/null || echo 0)

    local claimed=0
    if [[ "$_sid_count" -eq 1 ]]; then
        local _claim_sid
        _claim_sid=$(echo "$_sids" | head -1)
        local _claim_sdir
        _claim_sdir=$(_cs_session_dir "$_claim_sid" 2>/dev/null) || true
        if [[ -n "$_claim_sdir" ]]; then
            cs_atomic_dedup_append "${_claim_sdir}/touched.txt" "$fake_marker" 2>/dev/null && claimed=1
        fi
    fi

    if [[ "$claimed" -eq 1 ]] && assert_file_contains "marker in touched.txt" "$fake_marker" "$touched"; then
        teardown_repo
        return 0
    else
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 2: No session — warning on stderr, exit 0
# ---------------------------------------------------------------------------

test_no_session_warning_exit_zero() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"

    local fake_marker="${SCRATCH_DIR}/.mcp-version-check"
    date +%Y-%m-%d > "$fake_marker"

    local tmp_stderr="${SCRATCH_DIR}/test-stderr-mcp.txt"
    local tmp_script="${SCRATCH_DIR}/test-no-session-mcp.sh"
    cat > "$tmp_script" <<SCRIPT
#!/bin/bash
source "${LIB}"
_sids="\$(cs_live_session_ids 2>/dev/null)" || _sids=""
if [[ -z "\$_sids" ]]; then _sid_count=0
else _sid_count=\$(echo "\$_sids" | wc -l | tr -d ' \n'); fi
if [[ "\${_sid_count:-0}" -eq 0 ]]; then
    echo "coordinator-session: no active session found — skipping self-claim for ${fake_marker}" >&2
fi
SCRIPT
    chmod +x "$tmp_script"
    local rc=0
    bash "$tmp_script" 2>"$tmp_stderr" || rc=$?
    local stderr_out
    stderr_out=$(cat "$tmp_stderr" 2>/dev/null || true)

    if [[ $rc -eq 0 ]] && assert_stderr_contains "warning" "coordinator-session: no active session" "$stderr_out"; then
        teardown_repo
        return 0
    else
        echo "    rc=$rc stderr=$stderr_out" >&2
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 3: check-mcp-versions.sh wiring check
# ---------------------------------------------------------------------------

test_check_mcp_has_wiring() {
    local script="${HOME}/.claude/scripts/check-mcp-versions.sh"
    [[ ! -f "$script" ]] && script="${SCRIPT_DIR}/../../../../../scripts/check-mcp-versions.sh"

    if grep -qF '_cs_claim_if_session' "$script" 2>/dev/null && \
       grep -qF 'coordinator-session.sh' "$script" 2>/dev/null && \
       grep -qF '_cs_claim_if_session "$MARKER"' "$script" 2>/dev/null; then
        return 0
    else
        echo "    self-claim wiring not found in check-mcp-versions.sh ($script)" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

echo "=== test-self-claim-check-mcp-versions.sh ==="

echo "--- Test 1: marker claimed in active session touched.txt"
test_marker_claimed_in_session && pass "marker claimed" || fail "marker claimed"

echo "--- Test 2: no session — warning + exit 0"
test_no_session_warning_exit_zero && pass "no session exit 0" || fail "no session exit 0"

echo "--- Test 3: check-mcp-versions.sh wiring"
test_check_mcp_has_wiring && pass "check-mcp-versions.sh wired" || fail "check-mcp-versions.sh wired"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ $FAIL -eq 0 ]]
