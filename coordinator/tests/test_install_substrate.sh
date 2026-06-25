#!/usr/bin/env bash
# plugins/coordinator/tests/test_install_substrate.sh
#
# Tests for lib/install-substrate.sh — Phase 3 mechanical substrate installer.
#
# Covers:
#   D2-16: running install-substrate.sh against a temp CLAUDE_HOME seeds a live
#          registry.toml; a second run does NOT overwrite an operator-modified one.
#   D2-15: invoking the script with CLAUDE_PLUGIN_ROOT unset still resolves via
#          the BASH_SOURCE fallback (does not exit 1).
#
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md
#
# Cross-platform portability (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4 (harness locate + re-exec pattern).
#   - BSD-portable: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable.
#
# Uses COORDINATOR_NON_INTERACTIVE=1 to suppress interactive prompts.
# Uses CLAUDE_HOME=<tmpdir> to sandbox the install destination so the test
# never writes to the real ~/.claude.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate a real bash >= 4 (needed for subshell invocations and self-re-exec).
# ---------------------------------------------------------------------------
_BASH4=""
for _b in "$BASH" /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash bash; do
    [[ -z "${_b:-}" ]] && continue
    if "$_b" -c '[[ "${BASH_VERSINFO[0]}" -ge 4 ]]' 2>/dev/null; then
        _BASH4="$_b"
        break
    fi
done

if [[ -z "$_BASH4" ]]; then
    echo "ERROR: bash >= 4 required but not found." >&2
    echo "Remediation: brew install bash" >&2
    exit 1
fi

# Self-re-exec under bash >= 4 if needed.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and the script under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_UNDER_TEST="${COORDINATOR_ROOT}/lib/install-substrate.sh"

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
    echo "ERROR: script not found: $SCRIPT_UNDER_TEST" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Test counters and helpers.
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
ERRORS=()

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

# ---------------------------------------------------------------------------
# Scratch directory — cleaned up on exit. Isolated from real ~/.claude.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
trap 'rm -rf "$_SCRATCH_DIR"' EXIT

# ---------------------------------------------------------------------------
# Helper: run install-substrate.sh against a sandboxed CLAUDE_HOME.
# Usage: _run_install <fake_home> [extra env assignments...]
# Returns exit code of the script.
# ---------------------------------------------------------------------------
_run_install() {
    local _fake_home="$1"
    # Review: code-reviewer F8 — removed vestigial shift/"$@"; install-substrate.sh takes no positional args.
    # Run in a subshell so env mutations don't leak.
    (
        export CLAUDE_HOME="$_fake_home"
        export CLAUDE_PLUGIN_ROOT="$COORDINATOR_ROOT"
        export COORDINATOR_NON_INTERACTIVE=1
        # Review: code-reviewer F4 — the helper itself does no output suppression; callers
        # redirect stdout/stderr at their call sites (>/dev/null 2>&1 or to a temp file).
        "$_BASH4" "$SCRIPT_UNDER_TEST"
    )
}

# ---------------------------------------------------------------------------
# Test 1 (D2-16): fresh install seeds a live registry.toml.
#
# Assert:
#   - After running install-substrate.sh with CLAUDE_HOME pointing at a
#     temp dir, ${fake_home}/.claude/machine-local/registry.toml exists.
#   - The seeded file is non-empty (the .example has real content).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1 (D2-16): fresh install seeds live registry.toml ==="

_t1_home="${_SCRATCH_DIR}/t1_home"
mkdir -p "$_t1_home"

_t1_dst="${_t1_home}/.claude/machine-local/registry.toml"

# Review: code-reviewer F5 — capture stderr to temp file so failure diagnostics are visible in _fail.
_t1_stderr_file="$(mktemp)"
if _run_install "$_t1_home" >/dev/null 2>"$_t1_stderr_file"; then
    _t1_exit=0
else
    _t1_exit=$?
fi

if [[ -f "$_t1_dst" ]]; then
    _pass "test 1a: registry.toml seeded at ${_t1_dst}"
else
    _t1_stderr="$(cat "$_t1_stderr_file" 2>/dev/null || true)"
    _fail "test 1a: registry.toml NOT found at ${_t1_dst} after fresh install (exit: ${_t1_exit}; stderr: ${_t1_stderr})"
fi
rm -f "$_t1_stderr_file"

if [[ -s "$_t1_dst" ]]; then
    _pass "test 1b: seeded registry.toml is non-empty"
else
    _fail "test 1b: seeded registry.toml exists but is empty"
fi

# ---------------------------------------------------------------------------
# Test 2 (D2-16): second run does NOT overwrite operator-modified registry.toml.
#
# Procedure:
#   1. Reuse the home from test 1 (registry.toml already exists).
#   2. Write a sentinel value into registry.toml that the template doesn't have.
#   3. Run install-substrate.sh again.
#   4. Assert the sentinel is still present (file was not overwritten).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2 (D2-16): second run preserves operator-modified registry.toml ==="

_t2_sentinel="# OPERATOR-SENTINEL-DO-NOT-OVERWRITE"

if [[ -f "$_t1_dst" ]]; then
    printf '\n%s\n' "$_t2_sentinel" >> "$_t1_dst"
    # Review: code-reviewer F5 — capture stderr so failure diagnostics are visible.
    _t2_stderr_file="$(mktemp)"
    _run_install "$_t1_home" >/dev/null 2>"$_t2_stderr_file" || true
    _t2_stderr="$(cat "$_t2_stderr_file" 2>/dev/null || true)"
    rm -f "$_t2_stderr_file"

    if grep -qF "$_t2_sentinel" "$_t1_dst"; then
        _pass "test 2: operator-modified registry.toml preserved on re-run (sentinel intact)"
    else
        _fail "test 2: registry.toml was overwritten — sentinel missing after second install run"
    fi
else
    # Test 1 already failed; report a dependency note rather than a misleading failure.
    _fail "test 2: skipped — registry.toml not found (test 1 prerequisite failed)"
fi

# ---------------------------------------------------------------------------
# Test 3 (D2-15): BASH_SOURCE fallback — running without CLAUDE_PLUGIN_ROOT set
# resolves the root from BASH_SOURCE and does not exit 1.
#
# Procedure:
#   - Run install-substrate.sh in a subshell with CLAUDE_PLUGIN_ROOT explicitly
#     unset. The script must still complete (exit 0).
# Note: we must still set CLAUDE_HOME to the sandbox so the script doesn't
# write to the real ~/.claude. COORDINATOR_NON_INTERACTIVE=1 suppresses prompts.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3 (D2-15): BASH_SOURCE fallback — unset CLAUDE_PLUGIN_ROOT resolves correctly ==="

_t3_home="${_SCRATCH_DIR}/t3_home"
mkdir -p "$_t3_home"

_t3_exit=0
# Review: code-reviewer F5 — capture stderr to temp file so failure diagnostics are visible.
_t3_stderr_file="$(mktemp)"
(
    unset CLAUDE_PLUGIN_ROOT
    export CLAUDE_HOME="$_t3_home"
    export COORDINATOR_NON_INTERACTIVE=1
    "$_BASH4" "$SCRIPT_UNDER_TEST" >/dev/null 2>"$_t3_stderr_file"
) || _t3_exit=$?

if [[ "$_t3_exit" -eq 0 ]]; then
    _pass "test 3a: script exited 0 with CLAUDE_PLUGIN_ROOT unset (BASH_SOURCE fallback worked)"
else
    _t3_stderr="$(cat "$_t3_stderr_file" 2>/dev/null || true)"
    _fail "test 3a: script exited ${_t3_exit} with CLAUDE_PLUGIN_ROOT unset — fallback failed (stderr: ${_t3_stderr})"
fi
rm -f "$_t3_stderr_file"

# Also confirm that registry.toml was seeded in the fallback run (end-to-end).
_t3_dst="${_t3_home}/.claude/machine-local/registry.toml"
if [[ -f "$_t3_dst" ]]; then
    _pass "test 3b: registry.toml seeded in BASH_SOURCE fallback run"
else
    _fail "test 3b: registry.toml NOT seeded in BASH_SOURCE fallback run"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _err in "${ERRORS[@]}"; do
        echo "  ${_err}"
    done
fi

if [[ ${FAIL} -gt 0 ]]; then
    exit 1
fi
exit 0
