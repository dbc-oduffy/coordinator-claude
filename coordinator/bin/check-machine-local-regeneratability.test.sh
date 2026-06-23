#!/usr/bin/env bash
# bin/check-machine-local-regeneratability.test.sh — Tests for check-machine-local-regeneratability.sh
#
# Purpose: Self-contained test suite (temp dirs, assert exit code + stderr content).
# Models structure after bin/fan-out-dispatch.test.sh.
#
# Tests:
#   (a) clean state — all session-accumulated entries have tracked baseline → silent, exit 0
#   (b) gitignored session-accumulated entry with no tracked baseline → finding on stderr, exit 0
#   (c) [regeneratability] table covers all 8 coordinator-owned keys → no unclassified warning
#   (d) a coordinator-owned key absent from the table → unclassified-key warning, exit 0
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C1
#
# Usage: bash bin/check-machine-local-regeneratability.test.sh
# Exit 0 = all tests pass; non-zero = at least one failure.

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required (found ${BASH_VERSION:-unknown}). Install via homebrew: brew install bash" >&2
    exit 1
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="${SCRIPT_DIR}/check-machine-local-regeneratability.sh"

PASS=0
FAIL=0
TMPDIR_ROOT=""

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
_setup() {
    TMPDIR_ROOT="$(mktemp -d)"
}

_teardown() {
    if [[ -n "${TMPDIR_ROOT:-}" ]] && [[ -d "${TMPDIR_ROOT:-}" ]]; then
        rm -rf "$TMPDIR_ROOT"
    fi
}

trap _teardown EXIT
_setup

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

_assert_exit_zero() {
    local label="$1" exit_code="$2"
    if [[ "$exit_code" -eq 0 ]]; then
        _pass "$label — exited zero"
    else
        _fail "$label — expected zero exit, got ${exit_code}"
    fi
}

_assert_stderr_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _pass "$label — stderr contains: ${needle}"
    else
        _fail "$label — stderr missing: ${needle}"
        echo "    (actual stderr first 600 chars: ${haystack:0:600})"
    fi
}

_assert_stderr_not_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _fail "$label — stderr unexpectedly contains: ${needle}"
        echo "    (actual stderr first 600 chars: ${haystack:0:600})"
    else
        _pass "$label — stderr does not contain: ${needle}"
    fi
}

# ---------------------------------------------------------------------------
# Fixture builder: create a fake ~/.claude directory with machine-local/ populated
# ---------------------------------------------------------------------------
_make_claude_dir() {
    local base="$1"
    local ml_dir="${base}/.claude/machine-local"
    mkdir -p "$ml_dir"
    echo "$ml_dir"
}

_run_check() {
    local fake_home="$1"
    local stderr_out
    local exit_code
    stderr_out="$(CLAUDE_HOME="$fake_home" bash "$CHECK_SCRIPT" 2>&1 >/dev/null)"
    exit_code="$?"
    echo "$stderr_out"
    return "$exit_code"
}

_run_check_capture() {
    # Capture stderr separately; return exit code via global
    local fake_home="$1"
    TEST_STDERR=""
    TEST_EXIT=0
    TEST_STDERR="$(CLAUDE_HOME="$fake_home" bash "$CHECK_SCRIPT" 2>&1 >/dev/null)" || TEST_EXIT="$?"
}

# ---------------------------------------------------------------------------
# Test (a): Clean state — all session-accumulated entries have tracked baseline
# Registry has coordinator.python in [regeneratability] as idempotent-regeneratable
# and repos.* as session-accumulated-must-survive-crash WITH tracked declarations.
# Expected: silent (no stderr), exit 0.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test (a): Clean state — all session-accumulated entries have tracked baseline ==="

FAKE_HOME_A="${TMPDIR_ROOT}/home_a"
ML_DIR_A="$(_make_claude_dir "$FAKE_HOME_A")"

# Write tracked registry.toml with both [regeneratability] table AND baseline declarations
cat > "${ML_DIR_A}/registry.toml" <<'TOML'
schema = 1

# Tracked baseline declarations (empty = declared but per-machine value goes in .local.toml)
"coordinator.python"       = ""
"plugin.mirrors"           = ""
"publish.targets"          = []
"repos.coordinator_claude" = ""
"repos.dronesim"           = ""
"repos.project_rag"        = ""
"repos.project_rag_ue_addon" = ""
"repos.claude_unreal_holodeck" = ""
"repos.geneva_mvp"         = ""
"repos.fifa_stats"         = ""
"repos.experiments"        = ""

[regeneratability]
"coordinator.python"           = "idempotent-regeneratable"
"plugin.mirrors"               = "idempotent-regeneratable"
"publish.targets"              = "idempotent-regeneratable"
"repos.coordinator_claude"     = "session-accumulated-must-survive-crash"
"repos.dronesim"               = "session-accumulated-must-survive-crash"
"repos.project_rag"            = "session-accumulated-must-survive-crash"
"repos.project_rag_ue_addon"   = "session-accumulated-must-survive-crash"
"repos.claude_unreal_holodeck" = "session-accumulated-must-survive-crash"
"repos.geneva_mvp"             = "session-accumulated-must-survive-crash"
"repos.fifa_stats"             = "session-accumulated-must-survive-crash"
"repos.experiments"            = "session-accumulated-must-survive-crash"
TOML

# Write .local.toml with per-machine values — but the keys ARE declared in tracked file
cat > "${ML_DIR_A}/registry.local.toml" <<'TOML'
schema = 1
"repos.project_rag" = "/home/user/project-rag"
"repos.dronesim"    = "/home/user/dronesim"
TOML

_run_check_capture "$FAKE_HOME_A"
_assert_exit_zero "(a) clean state" "$TEST_EXIT"
_assert_stderr_not_contains "(a) clean state - no unclassified warning" "unclassified" "$TEST_STDERR"
_assert_stderr_not_contains "(a) clean state - no install-surface warning" "install-surface-completeness defect" "$TEST_STDERR"

# ---------------------------------------------------------------------------
# Test (b): Gitignored session-accumulated entry with no tracked baseline
# A repos.* key appears ONLY in registry.local.toml (gitignored) and is classified
# as session-accumulated-must-survive-crash — but has no entry in registry.toml.
# Expected: finding on stderr, still exit 0.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test (b): Gitignored session-accumulated entry with no tracked baseline ==="

FAKE_HOME_B="${TMPDIR_ROOT}/home_b"
ML_DIR_B="$(_make_claude_dir "$FAKE_HOME_B")"

# Tracked registry: has [regeneratability] table with repos.project_rag classified,
# but does NOT have a baseline declaration for repos.project_rag itself.
cat > "${ML_DIR_B}/registry.toml" <<'TOML'
schema = 1

# Note: repos.project_rag is intentionally NOT declared here (simulating the defect)
"coordinator.python"       = ""
"plugin.mirrors"           = ""
"publish.targets"          = []
"repos.coordinator_claude" = ""
"repos.dronesim"           = ""
"repos.project_rag_ue_addon" = ""
"repos.claude_unreal_holodeck" = ""
"repos.geneva_mvp"         = ""
"repos.fifa_stats"         = ""
"repos.experiments"        = ""

[regeneratability]
"coordinator.python"           = "idempotent-regeneratable"
"plugin.mirrors"               = "idempotent-regeneratable"
"publish.targets"              = "idempotent-regeneratable"
"repos.coordinator_claude"     = "session-accumulated-must-survive-crash"
"repos.dronesim"               = "session-accumulated-must-survive-crash"
"repos.project_rag"            = "session-accumulated-must-survive-crash"
"repos.project_rag_ue_addon"   = "session-accumulated-must-survive-crash"
"repos.claude_unreal_holodeck" = "session-accumulated-must-survive-crash"
"repos.geneva_mvp"             = "session-accumulated-must-survive-crash"
"repos.fifa_stats"             = "session-accumulated-must-survive-crash"
"repos.experiments"            = "session-accumulated-must-survive-crash"
TOML

# .local.toml has repos.project_rag but no tracked baseline declaration for it
cat > "${ML_DIR_B}/registry.local.toml" <<'TOML'
schema = 1
"repos.project_rag" = "/home/user/project-rag"
TOML

_run_check_capture "$FAKE_HOME_B"
_assert_exit_zero "(b) gitignored session-accumulated - still exit 0" "$TEST_EXIT"
_assert_stderr_contains "(b) gitignored session-accumulated - finding emitted" "install-surface-completeness defect" "$TEST_STDERR"
_assert_stderr_contains "(b) gitignored session-accumulated - names the key" "repos.project_rag" "$TEST_STDERR"
_assert_stderr_contains "(b) gitignored session-accumulated - leads with offer" "Offer:" "$TEST_STDERR"
# Review: code-reviewer — confirm the finding scopes to exactly repos.project_rag (not repos.dronesim,
# which IS declared in the tracked registry.toml; the finding must not fire for it).
_assert_stderr_not_contains "(b) gitignored session-accumulated - repos.dronesim NOT flagged (has tracked baseline)" "repos.dronesim" "$TEST_STDERR"

# ---------------------------------------------------------------------------
# Test (c): [regeneratability] table covers all coordinator-owned keys → no unclassified warning
# ---------------------------------------------------------------------------
echo ""
echo "=== Test (c): [regeneratability] table covers all coordinator-owned keys ==="

FAKE_HOME_C="${TMPDIR_ROOT}/home_c"
ML_DIR_C="$(_make_claude_dir "$FAKE_HOME_C")"

# Complete coverage of all coordinator-owned keys
cat > "${ML_DIR_C}/registry.toml" <<'TOML'
schema = 1

"coordinator.python"           = ""
"plugin.mirrors"               = ""
"publish.targets"              = []
"repos.coordinator_claude"     = ""
"repos.dronesim"               = ""
"repos.project_rag"            = ""
"repos.project_rag_ue_addon"   = ""
"repos.claude_unreal_holodeck" = ""
"repos.geneva_mvp"             = ""
"repos.fifa_stats"             = ""
"repos.experiments"            = ""

[regeneratability]
"coordinator.python"           = "idempotent-regeneratable"
"plugin.mirrors"               = "idempotent-regeneratable"
"publish.targets"              = "idempotent-regeneratable"
"repos.coordinator_claude"     = "session-accumulated-must-survive-crash"
"repos.dronesim"               = "session-accumulated-must-survive-crash"
"repos.project_rag"            = "session-accumulated-must-survive-crash"
"repos.project_rag_ue_addon"   = "session-accumulated-must-survive-crash"
"repos.claude_unreal_holodeck" = "session-accumulated-must-survive-crash"
"repos.geneva_mvp"             = "session-accumulated-must-survive-crash"
"repos.fifa_stats"             = "session-accumulated-must-survive-crash"
"repos.experiments"            = "session-accumulated-must-survive-crash"
TOML

_run_check_capture "$FAKE_HOME_C"
_assert_exit_zero "(c) full coverage - exit 0" "$TEST_EXIT"
_assert_stderr_not_contains "(c) full coverage - no unclassified warning" "absent from [regeneratability]" "$TEST_STDERR"

# ---------------------------------------------------------------------------
# Test (d): A coordinator-owned key absent from [regeneratability] table → unclassified-key warning
# coords.python is in the coordinator-owned list but missing from [regeneratability]
# Expected: unclassified-key warning, still exit 0.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test (d): coordinator-owned key absent from [regeneratability] table ==="

FAKE_HOME_D="${TMPDIR_ROOT}/home_d"
ML_DIR_D="$(_make_claude_dir "$FAKE_HOME_D")"

# [regeneratability] table is missing coordinator.python
cat > "${ML_DIR_D}/registry.toml" <<'TOML'
schema = 1

"coordinator.python"           = ""
"publish.targets"              = []
"repos.coordinator_claude"     = ""
"repos.dronesim"               = ""
"repos.project_rag"            = ""
"repos.project_rag_ue_addon"   = ""
"repos.claude_unreal_holodeck" = ""
"repos.geneva_mvp"             = ""
"repos.fifa_stats"             = ""
"repos.experiments"            = ""

[regeneratability]
# coordinator.python is intentionally omitted
"publish.targets"              = "idempotent-regeneratable"
"repos.coordinator_claude"     = "session-accumulated-must-survive-crash"
"repos.dronesim"               = "session-accumulated-must-survive-crash"
"repos.project_rag"            = "session-accumulated-must-survive-crash"
"repos.project_rag_ue_addon"   = "session-accumulated-must-survive-crash"
"repos.claude_unreal_holodeck" = "session-accumulated-must-survive-crash"
"repos.geneva_mvp"             = "session-accumulated-must-survive-crash"
"repos.fifa_stats"             = "session-accumulated-must-survive-crash"
"repos.experiments"            = "session-accumulated-must-survive-crash"
TOML

_run_check_capture "$FAKE_HOME_D"
_assert_exit_zero "(d) missing key - still exit 0" "$TEST_EXIT"
_assert_stderr_contains "(d) missing key - unclassified warning emitted" "absent from [regeneratability]" "$TEST_STDERR"
_assert_stderr_contains "(d) missing key - names the specific key" "coordinator.python" "$TEST_STDERR"

# Also check plugin.mirrors is flagged (another missing key)
_assert_stderr_contains "(d) missing key - plugin.mirrors also flagged" "plugin.mirrors" "$TEST_STDERR"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "--- Results ---"
echo "PASS: ${PASS}"
echo "FAIL: ${FAIL}"
echo ""

if [[ "$FAIL" -eq 0 ]]; then
    echo "All tests passed."
    exit 0
else
    echo "Some tests FAILED."
    exit 1
fi
