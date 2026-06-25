#!/usr/bin/env bash
# test_fnm_pin.bats — plain-bash harness for lib/setup-fnm-pin.sh
#
# Purpose: regression coverage for fnm pin resolution at repo-setup time.
#   (a) .node-version present + fnm present (mock) → calls fnm install <version> + emits env guidance
#   (b) .nvmrc present + fnm absent → fails loud with exact remediation string
#   (c) no pin file → clean no-op exit 0
#   (d) idempotent re-run → calling twice produces identical outcome, both exit 0
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness following the conventions in check-machine-path-leak.bats.
# The file is named .bats so any acceptance-oracle grep resolves it correctly.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/tests/test_fnm_pin.bats
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1d (AC6)
# Review: code-reviewer — corrected from non-existent opticon-node24-fnm-pin.md
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../lib/setup-fnm-pin.sh"

# ---------------------------------------------------------------------------
# Test framework (mirrors check-machine-path-leak.bats)
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
    echo "  FAIL: $1"
    FAIL_MSGS+=("$1")
    (( FAIL++ )) || true
}

run_test() {
    local name="$1"
    local fn="$2"
    echo "--- ${name}"
    if "${fn}"; then
        pass "${name}"
    else
        fail "${name}"
    fi
}

# ---------------------------------------------------------------------------
# Helper: create a per-test temp dir with a mock fnm script.
# Returns: sets TMPDIR_TEST, REPO, MOCK_FNM, MOCK_FNM_CALLS in caller scope.
# ---------------------------------------------------------------------------
_setup_test_dir() {
    TMPDIR_TEST="$(mktemp -d)"
    REPO="${TMPDIR_TEST}/repo"
    mkdir -p "$REPO"

    MOCK_FNM="${TMPDIR_TEST}/mock-fnm"
    MOCK_FNM_CALLS="${TMPDIR_TEST}/fnm-calls.log"
    cat > "$MOCK_FNM" <<'MOCK_EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${MOCK_FNM_CALLS}"
exit 0
MOCK_EOF
    chmod +x "$MOCK_FNM"
}

# ---------------------------------------------------------------------------
# (a) .node-version present + fnm present (mock) → installs + emits guidance
# ---------------------------------------------------------------------------

test_node_version_present_fnm_present_installs_and_emits_guidance() {
    _setup_test_dir
    printf 'v24.2.0\n' > "${REPO}/.node-version"

    local output status=0
    output="$(COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" 2>&1)" || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # fnm install must have been called with the pinned version.
    if ! grep -qF "install v24.2.0" "${MOCK_FNM_CALLS}" 2>/dev/null; then
        printf '    FAIL: fnm install v24.2.0 not found in call log\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Guidance for eval "$(fnm env)" must appear in output.
    if ! printf '%s\n' "$output" | grep -qF 'eval "$(fnm env)"'; then
        printf '    FAIL: eval "$(fnm env)" not found in output\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # PATH-prefix hint must also appear.
    if ! printf '%s\n' "$output" | grep -qF 'PATH='; then
        printf '    FAIL: PATH= hint not found in output\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (a-nvmrc) .nvmrc present + fnm present → reads version from .nvmrc
# ---------------------------------------------------------------------------

test_nvmrc_present_fnm_present_reads_nvmrc() {
    _setup_test_dir
    printf '24.2.0\n' > "${REPO}/.nvmrc"

    local status=0
    COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    if ! grep -qF "install 24.2.0" "${MOCK_FNM_CALLS}" 2>/dev/null; then
        printf '    FAIL: fnm install 24.2.0 not found in call log\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (a-prefer) .node-version takes precedence over .nvmrc when both present
# ---------------------------------------------------------------------------

test_node_version_takes_precedence_over_nvmrc() {
    _setup_test_dir
    printf 'v24.2.0\n' > "${REPO}/.node-version"
    printf '22.0.0\n'  > "${REPO}/.nvmrc"

    local status=0
    COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Must use .node-version's value.
    if ! grep -qF "install v24.2.0" "${MOCK_FNM_CALLS}" 2>/dev/null; then
        printf '    FAIL: fnm install v24.2.0 not found (should use .node-version)\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Must NOT use .nvmrc's value.
    if grep -qF "install 22.0.0" "${MOCK_FNM_CALLS}" 2>/dev/null; then
        printf '    FAIL: fnm install 22.0.0 found (should NOT use .nvmrc when .node-version present)\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (b) .nvmrc present + fnm absent → exits 1 with exact remediation message
# ---------------------------------------------------------------------------

test_nvmrc_present_fnm_absent_exits_1_with_remediation() {
    _setup_test_dir
    printf '24.2.0\n' > "${REPO}/.nvmrc"

    local output status=0
    output="$(COORDINATOR_FNM_ABSENT="1" bash "$SUBJECT" "$REPO" 2>&1)" || status=$?

    if [ "$status" -ne 1 ]; then
        printf '    FAIL: expected exit 1, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # The exact remediation string the spec requires verbatim.
    if ! printf '%s\n' "$output" | grep -qF \
        'fnm not installed — run coordinator:install to install the Node toolchain manager, then re-run repo-setup'; then
        printf '    FAIL: exact remediation string not found in output\n' >&2
        printf '    output was: %s\n' "$output" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (b-nodeversion) .node-version present + fnm absent → exits 1 with remediation
# ---------------------------------------------------------------------------

test_node_version_present_fnm_absent_exits_1_with_remediation() {
    _setup_test_dir
    printf 'v24.2.0\n' > "${REPO}/.node-version"

    local output status=0
    output="$(COORDINATOR_FNM_ABSENT="1" bash "$SUBJECT" "$REPO" 2>&1)" || status=$?

    if [ "$status" -ne 1 ]; then
        printf '    FAIL: expected exit 1, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    if ! printf '%s\n' "$output" | grep -qF 'fnm not installed'; then
        printf '    FAIL: "fnm not installed" not found in output\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (c) no pin file → clean no-op exit 0, zero output
# ---------------------------------------------------------------------------

test_no_pin_file_exits_0_no_output() {
    _setup_test_dir
    # REPO has no .node-version or .nvmrc.

    local output status=0
    output="$(bash "$SUBJECT" "$REPO" 2>&1)" || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    if [ -n "$output" ]; then
        printf '    FAIL: expected no output, got: %s\n' "$output" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (c) no pin file → does not invoke fnm even if present
# ---------------------------------------------------------------------------

test_no_pin_file_does_not_invoke_fnm() {
    _setup_test_dir
    # REPO has no .node-version or .nvmrc.

    local status=0
    COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Mock call log should not exist or be empty.
    if [ -f "${MOCK_FNM_CALLS}" ] && [ -s "${MOCK_FNM_CALLS}" ]; then
        printf '    FAIL: fnm was invoked but should not have been (no pin file)\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (d) idempotent: running twice with pin file + fnm present both exit 0
# ---------------------------------------------------------------------------

test_idempotent_pin_file_fnm_present_both_exit_0() {
    _setup_test_dir
    printf 'v24.2.0\n' > "${REPO}/.node-version"

    local first_status=0
    COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || first_status=$?

    if [ "$first_status" -ne 0 ]; then
        printf '    FAIL: first run expected exit 0, got %d\n' "$first_status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Rotate call log so second run is isolated.
    rm -f "${MOCK_FNM_CALLS}"

    local second_status=0
    COORDINATOR_FNM_CMD="${MOCK_FNM}" MOCK_FNM_CALLS="${MOCK_FNM_CALLS}" \
        bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || second_status=$?

    if [ "$second_status" -ne 0 ]; then
        printf '    FAIL: second run expected exit 0, got %d\n' "$second_status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    # Both runs must have called fnm install with the same version.
    if ! grep -qF "install v24.2.0" "${MOCK_FNM_CALLS}" 2>/dev/null; then
        printf '    FAIL: second run did not call fnm install v24.2.0\n' >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# (d) idempotent: running twice with no pin file both exit 0 cleanly
# ---------------------------------------------------------------------------

test_idempotent_no_pin_file_both_exit_0() {
    _setup_test_dir

    local status=0
    bash "$SUBJECT" "$REPO" >/dev/null 2>&1 || status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: first run expected exit 0, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    local output second_status=0
    output="$(bash "$SUBJECT" "$REPO" 2>&1)" || second_status=$?
    if [ "$second_status" -ne 0 ]; then
        printf '    FAIL: second run expected exit 0, got %d\n' "$second_status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    if [ -n "$output" ]; then
        printf '    FAIL: second run expected no output, got: %s\n' "$output" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# Edge: missing repo-root argument defaults to cwd cleanly (no pin file)
# ---------------------------------------------------------------------------

test_missing_repo_root_defaults_to_cwd_no_pin_file() {
    _setup_test_dir
    # Run from REPO with no pin files — no argument passed.

    local status=0
    ( cd "$REPO" && bash "$SUBJECT" ) >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: expected exit 0 (cwd default, no pin file), got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# Edge: non-existent repo-root exits 1
# ---------------------------------------------------------------------------

test_nonexistent_repo_root_exits_1() {
    _setup_test_dir
    local nonexistent="${TMPDIR_TEST}/does-not-exist"

    local status=0
    bash "$SUBJECT" "$nonexistent" >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 1 ]; then
        printf '    FAIL: expected exit 1 for non-existent repo root, got %d\n' "$status" >&2
        rm -rf "$TMPDIR_TEST"
        return 1
    fi

    rm -rf "$TMPDIR_TEST"
    return 0
}

# ---------------------------------------------------------------------------
# Guard: subject must exist
# ---------------------------------------------------------------------------

if [[ ! -f "$SUBJECT" ]]; then
    echo "ERROR: subject not found at ${SUBJECT}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Run all 11 tests
# ---------------------------------------------------------------------------

run_test "(a) .node-version present, fnm present: calls fnm install and emits env guidance" \
    test_node_version_present_fnm_present_installs_and_emits_guidance

run_test "(a-nvmrc) .nvmrc present, fnm present: reads version from .nvmrc" \
    test_nvmrc_present_fnm_present_reads_nvmrc

run_test "(a-prefer) .node-version takes precedence over .nvmrc when both present" \
    test_node_version_takes_precedence_over_nvmrc

run_test "(b) .nvmrc present, fnm absent: exits 1 with exact remediation message" \
    test_nvmrc_present_fnm_absent_exits_1_with_remediation

run_test "(b-nodeversion) .node-version present, fnm absent: exits 1 with remediation" \
    test_node_version_present_fnm_absent_exits_1_with_remediation

run_test "(c) no pin file: exits 0 with no output" \
    test_no_pin_file_exits_0_no_output

run_test "(c) no pin file: does not invoke fnm even if present" \
    test_no_pin_file_does_not_invoke_fnm

run_test "(d) idempotent: running twice with pin file + fnm present both exit 0" \
    test_idempotent_pin_file_fnm_present_both_exit_0

run_test "(d) idempotent: running twice with no pin file both exit 0 cleanly" \
    test_idempotent_no_pin_file_both_exit_0

run_test "missing repo-root argument defaults to cwd cleanly (no pin file)" \
    test_missing_repo_root_defaults_to_cwd_no_pin_file

run_test "non-existent repo-root exits 1" \
    test_nonexistent_repo_root_exits_1

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed."

if [[ ${FAIL} -gt 0 ]]; then
    echo ""
    echo "Failed tests:"
    for msg in "${FAIL_MSGS[@]}"; do
        echo "  - ${msg}"
    done
    exit 1
fi

exit 0
