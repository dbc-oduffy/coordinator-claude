#!/usr/bin/env bash
# scripts/tests/first-run-regeneration.bats — AC3 (idempotency) + AC5 (regeneration)
# for scripts/first-run.sh --post-toolchain path.
#
# Purpose: verify that first-run.sh --post-toolchain orchestrates the three
# regenerators (install-substrate, ensure-coordinator-venv, platform-localize) in
# the correct order, produces the expected output markers (settings.local.json,
# venv-pin), and is idempotent on a second run.
#
# SAFETY: test runs entirely in a mktemp -d sandbox. STUB regenerators are used —
# no real install-substrate / ensure-coordinator-venv / platform-localize executes,
# no venv is built, no real ~/.claude state is mutated.
#
# NOTE: bats is NOT installed on this machine; this file uses the same plain-bash
# harness convention as check-machine-local-regeneratability.test.sh.
#
# Usage: bash scripts/tests/first-run-regeneration.bats
# Exit 0 = all tests pass; non-zero = at least one failure.
#
# Spec backlink: docs/plans/2026-06-23-new-machine-clone-lands-correctly.md § AC3/AC5
# Review: F12 — corrected spec-backlink to the canonical plan (not the -dogfood variant)
#   and pinned to the AC3/AC5 sections this test covers.

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required (found ${BASH_VERSION:-unknown}). Install via homebrew: brew install bash" >&2
    exit 1
fi

# Review: F13 — keep set -u but ensure summary always prints via trap on EXIT.
# All unset-var sites in helpers use ${VAR:-} guards (SANDBOX in _teardown already does).
set -uo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
SANDBOX=""

_setup() {
    SANDBOX="$(mktemp -d)"
}

_teardown() {
    if [[ -n "${SANDBOX:-}" && -d "${SANDBOX:-}" ]]; then
        rm -rf "$SANDBOX"
    fi
}

_print_summary_and_teardown() {
    # Review: F13 — always print summary, even if set -u fires mid-suite.
    local _pass_count="${PASS:-0}"
    local _fail_count="${FAIL:-0}"
    printf '\n--- Results ---\n'
    printf 'PASS: %d\n' "$_pass_count"
    printf 'FAIL: %d\n' "$_fail_count"
    printf '\n'
    if [[ "${_fail_count}" -eq 0 ]]; then
        printf 'All tests passed.\n'
    else
        printf 'Some tests FAILED.\n'
    fi
    _teardown
}
trap _print_summary_and_teardown EXIT
_setup

_pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
_fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

_assert_exit_zero() {
    local label="$1" exit_code="$2"
    if [[ "$exit_code" -eq 0 ]]; then
        _pass "$label — exited zero"
    else
        _fail "$label — expected exit 0, got ${exit_code}"
    fi
}

_assert_file_exists() {
    local label="$1" path="$2"
    if [[ -f "$path" ]]; then
        _pass "$label — file exists: $(basename "$path")"
    else
        _fail "$label — file missing: $path"
    fi
}

_assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if printf '%s' "$haystack" | grep -qF -- "$needle"; then
        _pass "$label — output contains: ${needle}"
    else
        _fail "$label — output missing: ${needle}"
        printf '    (actual output first 800 chars: %s)\n' "${haystack:0:800}"
    fi
}

_assert_order() {
    # Assert that $first appears before $second in call-order.log
    local label="$1" first="$2" second="$3" logfile="$4"
    local line_first line_second
    line_first=$(grep -n "$first" "$logfile" 2>/dev/null | head -1 | cut -d: -f1)
    line_second=$(grep -n "$second" "$logfile" 2>/dev/null | head -1 | cut -d: -f1)
    if [[ -z "$line_first" ]]; then
        _fail "$label — '$first' not found in call-order.log"
        return
    fi
    if [[ -z "$line_second" ]]; then
        _fail "$label — '$second' not found in call-order.log"
        return
    fi
    if [[ "$line_first" -lt "$line_second" ]]; then
        _pass "$label — $first (line $line_first) before $second (line $line_second)"
    else
        _fail "$label — $first (line $line_first) NOT before $second (line $line_second)"
    fi
}

# ---------------------------------------------------------------------------
# Sandbox fixture builder
#
# Layout mirrors the real plugin root as resolved by first-run.sh:
#   first-run.sh lives at  <sandbox>/coordinator/scripts/first-run.sh
#   PLUGIN_ROOT resolves to <sandbox>/coordinator  (SELF_DIR/..)
#
# Stub regenerators placed at:
#   <sandbox>/coordinator/lib/install-substrate.sh
#   <sandbox>/coordinator/lib/discover-working-repos.sh
#   <sandbox>/coordinator/bin/ensure-coordinator-venv.sh
#   <sandbox>/coordinator/bin/platform-localize.sh
#   <sandbox>/coordinator/bin/machine-local
#
# Each stub appends its short name to $SANDBOX/call-order.log.
# platform-localize also touches $SANDBOX/settings.local.json.
# ensure-coordinator-venv also writes $SANDBOX/venv-pin.
# setup.sh stub exits 0 silently (optional preflight, non-fatal).
# git stub (on PATH) makes `git lfs install` a no-op.
# ---------------------------------------------------------------------------

_build_sandbox_layout() {
    local root="$SANDBOX"

    # directory tree
    mkdir -p "$root/coordinator/scripts" \
             "$root/coordinator/lib" \
             "$root/coordinator/bin"

    # ---- copy real first-run.sh into sandbox scripts/ ----
    local SCRIPT_DIR
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp "$SCRIPT_DIR/../first-run.sh" "$root/coordinator/scripts/first-run.sh"
    chmod +x "$root/coordinator/scripts/first-run.sh"

    # ---- stub: install-substrate.sh ----
    cat > "$root/coordinator/lib/install-substrate.sh" <<STUB
#!/usr/bin/env bash
printf 'install-substrate\n' >> "\${SANDBOX_CALL_LOG}"
exit 0
STUB
    chmod +x "$root/coordinator/lib/install-substrate.sh"

    # ---- stub: discover-working-repos.sh (outputs nothing — no repos discovered) ----
    cat > "$root/coordinator/lib/discover-working-repos.sh" <<STUB
#!/usr/bin/env bash
# Stub: emit no repo paths (simulates no sibling repos on disk).
exit 0
STUB
    chmod +x "$root/coordinator/lib/discover-working-repos.sh"

    # ---- stub: ensure-coordinator-venv.sh ----
    cat > "$root/coordinator/bin/ensure-coordinator-venv.sh" <<STUB
#!/usr/bin/env bash
printf 'ensure-coordinator-venv\n' >> "\${SANDBOX_CALL_LOG}"
touch "\${SANDBOX_VENV_PIN}"
exit 0
STUB
    chmod +x "$root/coordinator/bin/ensure-coordinator-venv.sh"

    # ---- stub: platform-localize.sh ----
    cat > "$root/coordinator/bin/platform-localize.sh" <<STUB
#!/usr/bin/env bash
printf 'platform-localize\n' >> "\${SANDBOX_CALL_LOG}"
touch "\${SANDBOX_SETTINGS_JSON}"
exit 0
STUB
    chmod +x "$root/coordinator/bin/platform-localize.sh"

    # ---- stub: machine-local CLI ----
    cat > "$root/coordinator/bin/machine-local" <<STUB
#!/usr/bin/env bash
# Stub: swallow all machine-local set calls silently.
exit 0
STUB
    chmod +x "$root/coordinator/bin/machine-local"

    # ---- stub: setup.sh (optional preflight, non-fatal) ----
    cat > "$root/coordinator/scripts/setup.sh" <<STUB
#!/usr/bin/env bash
# Stub: preflight is a no-op in the test harness.
exit 0
STUB
    chmod +x "$root/coordinator/scripts/setup.sh"

    # ---- stub git binary that makes `git lfs install` a no-op ----
    mkdir -p "$root/bin-stubs"
    cat > "$root/bin-stubs/git" <<STUB
#!/usr/bin/env bash
# Stub git: make 'git lfs install' a silent no-op; pass other calls through.
if [[ "\${1:-}" == "lfs" && "\${2:-}" == "install" ]]; then
    exit 0
fi
# Fallback: exec real git if present (for any other git calls first-run might need).
real_git="\$(command -v git 2>/dev/null || true)"
if [[ -n "\$real_git" && "\$real_git" != "\$0" ]]; then
    exec "\$real_git" "\$@"
fi
exit 0
STUB
    chmod +x "$root/bin-stubs/git"
}

# ---------------------------------------------------------------------------
# Helper: run first-run.sh --post-toolchain inside the sandbox
# Exports SANDBOX_CALL_LOG, SANDBOX_VENV_PIN, SANDBOX_SETTINGS_JSON
# so stubs know where to write.
# ---------------------------------------------------------------------------
_run_first_run() {
    local root="$SANDBOX"
    export SANDBOX_CALL_LOG="$root/call-order.log"
    export SANDBOX_VENV_PIN="$root/venv-pin"
    export SANDBOX_SETTINGS_JSON="$root/settings.local.json"

    # Prepend our stub git dir and the coordinator bin/ stubs to PATH
    local saved_path="$PATH"
    export PATH="$root/bin-stubs:$root/coordinator/bin:$PATH"

    local output exit_code=0
    output="$(
        COORDINATOR_NON_INTERACTIVE=1 \
        bash "$root/coordinator/scripts/first-run.sh" \
             --post-toolchain --confirm \
             --no-git-lfs \
             2>&1
    )" || exit_code="$?"

    # Restore PATH
    export PATH="$saved_path"

    # Print captured output for diagnostic visibility
    printf '%s\n' "$output"
    return "$exit_code"
}

# ---------------------------------------------------------------------------
# Test suite setup: build the sandbox once, share across tests.
# ---------------------------------------------------------------------------
_build_sandbox_layout

# ---------------------------------------------------------------------------
# TEST 1 — AC5: First clean run produces expected outputs and call order
# ---------------------------------------------------------------------------
printf '\n=== Test 1 (AC5): clean run — regeneration outputs + call order ===\n'

# Precondition: no settings.local.json or venv-pin yet
[[ ! -f "$SANDBOX/settings.local.json" ]] || rm -f "$SANDBOX/settings.local.json"
[[ ! -f "$SANDBOX/venv-pin" ]]            || rm -f "$SANDBOX/venv-pin"
[[ ! -f "$SANDBOX/call-order.log" ]]      || rm -f "$SANDBOX/call-order.log"

T1_EXIT=0
T1_OUTPUT="$(_run_first_run 2>&1)" || T1_EXIT="$?"

_assert_exit_zero "AC5 clean run" "$T1_EXIT"
_assert_file_exists "AC5 settings.local.json produced" "$SANDBOX/settings.local.json"
_assert_file_exists "AC5 venv-pin produced" "$SANDBOX/venv-pin"
_assert_file_exists "AC5 call-order.log written" "$SANDBOX/call-order.log"

# Verify call order: install-substrate → ensure-coordinator-venv → platform-localize
_assert_order "AC5 install-substrate before ensure-venv" \
    "install-substrate" "ensure-coordinator-venv" "$SANDBOX/call-order.log"
_assert_order "AC5 ensure-venv before platform-localize" \
    "ensure-coordinator-venv" "platform-localize" "$SANDBOX/call-order.log"

_assert_contains "AC5 output mentions post-toolchain" "[post-toolchain]" "$T1_OUTPUT"
_assert_contains "AC5 output mentions install-substrate" "install-substrate" "$T1_OUTPUT"
_assert_contains "AC5 output mentions ensure-coordinator-venv" "ensure-coordinator-venv" "$T1_OUTPUT"
_assert_contains "AC5 output mentions platform-localize" "platform-localize" "$T1_OUTPUT"
_assert_contains "AC5 closing instruction present" "/reload-plugins" "$T1_OUTPUT"

# ---------------------------------------------------------------------------
# TEST 2 — AC3: Second run (idempotency) — exits 0, does not error
# ---------------------------------------------------------------------------
printf '\n=== Test 2 (AC3): idempotent second run — exits 0, no error ===\n'

# Reset call-order.log so we can verify second-run order independently
rm -f "$SANDBOX/call-order.log"

T2_EXIT=0
T2_OUTPUT="$(_run_first_run 2>&1)" || T2_EXIT="$?"

_assert_exit_zero "AC3 second run exits zero" "$T2_EXIT"
# Outputs should still be present (stubs are idempotent via touch/append)
_assert_file_exists "AC3 settings.local.json still present after second run" "$SANDBOX/settings.local.json"
_assert_file_exists "AC3 venv-pin still present after second run" "$SANDBOX/venv-pin"
# Order should be maintained on second run too
_assert_order "AC3 install-substrate still before ensure-venv on second run" \
    "install-substrate" "ensure-coordinator-venv" "$SANDBOX/call-order.log"
_assert_order "AC3 ensure-venv still before platform-localize on second run" \
    "ensure-coordinator-venv" "platform-localize" "$SANDBOX/call-order.log"

# ---------------------------------------------------------------------------
# TEST 3 — AC5 git-lfs path: run WITHOUT --no-git-lfs, assert closing instruction
# and exit 0. Stub git already no-ops `git lfs install`.
# Review: F6 — added to exercise the Step 5 git-lfs branch (previously untested).
# ---------------------------------------------------------------------------
printf '\n=== Test 3 (AC5): git-lfs path — without --no-git-lfs, exit 0, /reload-plugins ===\n'

_run_first_run_with_lfs() {
    local root="$SANDBOX"
    export SANDBOX_CALL_LOG="$root/call-order-lfs.log"
    export SANDBOX_VENV_PIN="$root/venv-pin-lfs"
    export SANDBOX_SETTINGS_JSON="$root/settings-lfs.local.json"

    local saved_path="$PATH"
    export PATH="$root/bin-stubs:$root/coordinator/bin:$PATH"

    local output exit_code=0
    output="$(
        COORDINATOR_NON_INTERACTIVE=1 \
        bash "$root/coordinator/scripts/first-run.sh" \
             --post-toolchain --confirm \
             2>&1
    )" || exit_code="$?"

    export PATH="$saved_path"
    printf '%s\n' "$output"
    return "$exit_code"
}

# Fresh log for Test 3
rm -f "$SANDBOX/call-order-lfs.log" "$SANDBOX/venv-pin-lfs" "$SANDBOX/settings-lfs.local.json"

T3_EXIT=0
T3_OUTPUT="$(_run_first_run_with_lfs 2>&1)" || T3_EXIT="$?"

_assert_exit_zero "AC5 lfs-path run" "$T3_EXIT"
_assert_contains "AC5 lfs-path closing instruction present" "/reload-plugins" "$T3_OUTPUT"
_assert_contains "AC5 lfs-path git lfs install ran (Step 5)" "git lfs install" "$T3_OUTPUT"

# ---------------------------------------------------------------------------
# Summary — printed by _print_summary_and_teardown via EXIT trap.
# Exit code reflects test outcome; trap fires after exit(), printing summary.
# ---------------------------------------------------------------------------
if [[ "$FAIL" -eq 0 ]]; then
    exit 0
else
    exit 1
fi
