#!/bin/bash
# test-self-claim-setup-unix.sh — Verify Wave 4 self-claim in scripts/setup-unix.sh.
#
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
#
# Validates:
#   1. With an active session: setup-unix.sh claims each modified JSON path in
#      the session's touched.txt.
#   2. With no session: script emits coordinator-session warnings on stderr and
#      exits 0 (best-effort contract, no failure).
#
# Note: setup-unix.sh requires an oduffy-custom plugin dir and modifies specific
# JSON files. We test the self-claim plumbing with the lib directly rather than
# running the full script against live files, to avoid side-effects.
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-self-claim-setup-unix.sh

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
        echo "    Expected stderr to contain: $needle" >&2
        echo "    Actual stderr: $stderr_content" >&2
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
    local sid="test-setup-$$"
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
# Test 1: _cs_claim_if_session claims each JSON path in active session
# ---------------------------------------------------------------------------

test_setup_claims_json_paths() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"
    local sid
    sid=$(fake_session)

    local sdir
    sdir=$(_cs_session_dir "$sid")
    local touched="${sdir}/touched.txt"

    # Simulate the three paths that setup-unix.sh claims.
    local fake_claude_dir="${SCRATCH_DIR}/fake-claude"
    mkdir -p "${fake_claude_dir}/plugins"
    echo '{}' > "${fake_claude_dir}/plugins/installed_plugins.json"
    echo '{}' > "${fake_claude_dir}/plugins/known_marketplaces.json"
    echo '{}' > "${fake_claude_dir}/settings.json"

    local installed="${fake_claude_dir}/plugins/installed_plugins.json"
    local known="${fake_claude_dir}/plugins/known_marketplaces.json"
    local settings="${fake_claude_dir}/settings.json"

    # Exercise _cs_claim_if_session logic (mirrors setup-unix.sh's embedded helper).
    _CS_LIB_LOADED=1
    source "$LIB" 2>/dev/null

    for path_to_claim in "$installed" "$known" "$settings"; do
        local _sids
        _sids="$(cs_live_session_ids 2>/dev/null)" || _sids=""
        local _sid_count
        _sid_count=$(echo "$_sids" | grep -c '[^[:space:]]' 2>/dev/null || echo 0)
        if [[ "$_sid_count" -eq 1 ]]; then
            local _claim_sid
            _claim_sid=$(echo "$_sids" | head -1)
            local _claim_sdir
            _claim_sdir=$(_cs_session_dir "$_claim_sid" 2>/dev/null) || continue
            cs_atomic_dedup_append "${_claim_sdir}/touched.txt" "$path_to_claim" 2>/dev/null || true
        fi
    done

    local pass=1
    for expected in "$installed" "$known" "$settings"; do
        if ! assert_file_contains "path in touched.txt" "$expected" "$touched"; then
            pass=0
        fi
    done

    teardown_repo
    [[ $pass -eq 1 ]]
}

# ---------------------------------------------------------------------------
# Test 2: No session — warnings emitted, exit 0
# ---------------------------------------------------------------------------

test_setup_no_session_exit_zero() {
    setup_repo

    # shellcheck source=/dev/null
    source "$LIB"

    local fake_path="${SCRATCH_DIR}/test.json"
    echo '{}' > "$fake_path"

    # Write a test script to capture stderr properly (subshell 2>&1 is unreliable
    # when set -euo pipefail is active and grep -c returns 1 on 0-match).
    local tmp_stderr="${SCRATCH_DIR}/test-stderr-setup.txt"
    local tmp_script="${SCRATCH_DIR}/test-no-session-setup.sh"
    cat > "$tmp_script" <<SCRIPT
#!/bin/bash
source "${LIB}"
_sids="\$(cs_live_session_ids 2>/dev/null)" || _sids=""
if [[ -z "\$_sids" ]]; then _sid_count=0
else _sid_count=\$(echo "\$_sids" | wc -l | tr -d ' \n'); fi
if [[ "\${_sid_count:-0}" -eq 0 ]]; then
    echo "coordinator-session: no active session found — skipping self-claim for ${fake_path}" >&2
fi
SCRIPT
    chmod +x "$tmp_script"
    local rc=0
    bash "$tmp_script" 2>"$tmp_stderr" || rc=$?
    local stderr_out
    stderr_out=$(cat "$tmp_stderr" 2>/dev/null || true)

    if [[ $rc -eq 0 ]] && assert_stderr_contains "warning emitted" "coordinator-session: no active session" "$stderr_out"; then
        teardown_repo
        return 0
    else
        echo "    rc=$rc stderr=$stderr_out" >&2
        teardown_repo
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 3: setup-unix.sh has self-claim wiring in script
# ---------------------------------------------------------------------------

test_setup_unix_has_wiring() {
    local setup_script="${SCRIPT_DIR}/../../../../../scripts/setup-unix.sh"
    [[ ! -f "$setup_script" ]] && setup_script="${HOME}/.claude/scripts/setup-unix.sh"

    if grep -qF '_cs_claim_if_session' "$setup_script" 2>/dev/null && \
       grep -qF 'coordinator-session.sh' "$setup_script" 2>/dev/null; then
        return 0
    else
        echo "    self-claim wiring not found in setup-unix.sh ($setup_script)" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

echo "=== test-self-claim-setup-unix.sh ==="

echo "--- Test 1: claims all three JSON paths in active session"
test_setup_claims_json_paths && pass "setup claims json paths" || fail "setup claims json paths"

echo "--- Test 2: no session — stderr warning + exit 0"
test_setup_no_session_exit_zero && pass "no session exit 0" || fail "no session exit 0"

echo "--- Test 3: setup-unix.sh wiring check"
test_setup_unix_has_wiring && pass "setup-unix.sh wired" || fail "setup-unix.sh wired"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
[[ $FAIL -eq 0 ]]
