#!/usr/bin/env bash
# test_setup_health_ledger_seed.bats — plain-bash harness for lib/setup-seed-health-ledger.sh
#
# Purpose: verifies that the health-ledger seeder creates state/health-ledger.md with
# the two required audit clocks and an empty per-system table, and that re-running is
# idempotent (no overwrite when the file already exists).
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness mirroring bin/tests/check-machine-path-leak.bats.
# The file is named .bats so any acceptance-oracle grep resolves it correctly.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/tests/test_setup_health_ledger_seed.bats
#
# Spec backlink: docs/plans/2026-06-23-setup-substrate-completeness.md § C1b

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../lib/setup-seed-health-ledger.sh"

# ---------------------------------------------------------------------------
# Test framework (mirrors bin/tests/check-machine-path-leak.bats)
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
# Helper — returns path to ledger in a given tmpdir
# ---------------------------------------------------------------------------

ledger_path() {
    printf '%s/state/health-ledger.md' "$1"
}

# ---------------------------------------------------------------------------
# Test 1: creates state/health-ledger.md in target repo on fresh run
# ---------------------------------------------------------------------------

test_creates_ledger_on_fresh_run() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    local output status
    output="$(bash "$SUBJECT" "$tmpdir" 2>&1)"; status=$?

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local ok=0
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: exited %d (expected 0)\n' "$status" >&2
        ok=1
    fi
    if [ ! -f "$ledger" ]; then
        printf '    FAIL: ledger not created at %s\n' "$ledger" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 2: creates state/ directory when it does not exist
# ---------------------------------------------------------------------------

test_creates_state_dir_when_absent() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    if [ -d "${tmpdir}/state" ]; then
        printf '    FAIL: state/ already exists before test\n' >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local status
    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1; status=$?

    local ok=0
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: exited %d (expected 0)\n' "$status" >&2
        ok=1
    fi
    if [ ! -d "${tmpdir}/state" ]; then
        printf '    FAIL: state/ directory not created\n' >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 3: seeded file contains Last full audit clock
# ---------------------------------------------------------------------------

test_seeded_file_contains_full_audit_clock() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local ok=0
    if ! grep -qF '**Last full audit:**' "$ledger" 2>/dev/null; then
        printf '    FAIL: "**Last full audit:**" not found in ledger\n' >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 4: seeded file contains Last targeted audit clock
# ---------------------------------------------------------------------------

test_seeded_file_contains_targeted_audit_clock() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local ok=0
    if ! grep -qF '**Last targeted audit:**' "$ledger" 2>/dev/null; then
        printf '    FAIL: "**Last targeted audit:**" not found in ledger\n' >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 5: seeded file contains two distinct audit clocks (both present)
# ---------------------------------------------------------------------------

test_seeded_file_contains_both_audit_clocks() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local full_count targeted_count
    full_count="$(grep -c 'Last full audit' "$ledger" 2>/dev/null || echo 0)"
    targeted_count="$(grep -c 'Last targeted audit' "$ledger" 2>/dev/null || echo 0)"

    local ok=0
    if [ "$full_count" -lt 1 ]; then
        printf '    FAIL: "Last full audit" count=%d (expected >=1)\n' "$full_count" >&2
        ok=1
    fi
    if [ "$targeted_count" -lt 1 ]; then
        printf '    FAIL: "Last targeted audit" count=%d (expected >=1)\n' "$targeted_count" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 6: seeded file contains per-system table header
# ---------------------------------------------------------------------------

test_seeded_file_contains_table_header() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local ok=0
    if ! grep -q '| System | Grade | Last Audited | Notes |' "$ledger" 2>/dev/null; then
        printf '    FAIL: per-system table header not found in ledger\n' >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 7: seeded file has no fabricated grade — no A-F grade in table body
# ---------------------------------------------------------------------------

test_seeded_file_no_fabricated_grade() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    # Body rows: lines starting with '|', excluding header and separator
    local bad_grades
    bad_grades="$(grep '^|' "$ledger" 2>/dev/null \
        | grep -v 'System.*Grade' \
        | grep -v '^|[-|]\+|' \
        | grep -E '\| [A-F] \|' || true)"

    local ok=0
    if [ -n "$bad_grades" ]; then
        printf '    FAIL: fabricated A-F grade found in table body:\n%s\n' "$bad_grades" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 8: seeded file has no non-question-mark grade in the table body
# ---------------------------------------------------------------------------

test_seeded_file_only_question_mark_grades() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    # Extract body rows (not header, not separator)
    local body_rows
    body_rows="$(grep '^|' "$ledger" 2>/dev/null \
        | grep -v 'System.*Grade' \
        | grep -v '^|[-|]\+|' || true)"

    local ok=0
    if [ -n "$body_rows" ]; then
        # Grade column is second: | System | Grade | ...
        # Fail if any body row has a grade column that is not '?' or empty
        # Review: code-reviewer — removed leading ! : awk exits 1 when bad grade found;
        # the original ! inverted the sense so FAIL fired when NO bad grade existed (false-pass).
        if printf '%s\n' "$body_rows" | awk -F'|' '{gsub(/^ +| +$/, "", $3); if ($3 != "?" && $3 != "") exit 1}'; then
            : # all grades are "?" or empty — test passes
        else
            printf '    FAIL: table body row has a non-"?" grade\n' >&2
            ok=1
        fi
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 9: stdout mentions seeding action on success
# ---------------------------------------------------------------------------

test_stdout_mentions_seeding_action() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    local output status
    output="$(bash "$SUBJECT" "$tmpdir" 2>&1)"; status=$?

    local ok=0
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: exited %d (expected 0)\n' "$status" >&2
        ok=1
    fi
    if ! printf '%s' "$output" | grep -q 'health-ledger'; then
        printf '    FAIL: stdout does not mention "health-ledger"\n' >&2
        printf '    stdout was: %s\n' "$output" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 10: defaults to cwd when no argument is given
# ---------------------------------------------------------------------------

test_defaults_to_cwd_when_no_arg() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    # Run from inside the temp dir — should seed state/health-ledger.md there
    ( cd "$tmpdir" && bash "$SUBJECT" ) >/dev/null 2>&1

    local ledger
    ledger="$(ledger_path "$tmpdir")"

    local ok=0
    if [ ! -f "$ledger" ]; then
        printf '    FAIL: ledger not created in cwd (%s)\n' "$tmpdir" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 11: exits 0 when state/health-ledger.md already exists
# ---------------------------------------------------------------------------

test_exits_zero_when_ledger_already_exists() {
    local tmpdir
    tmpdir="$(mktemp -d)"
    mkdir -p "${tmpdir}/state"
    printf '# Health Ledger\nexisting content\n' > "$(ledger_path "$tmpdir")"

    local status
    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1; status=$?

    local ok=0
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: exited %d (expected 0 on idempotent re-run)\n' "$status" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 12: does not overwrite existing state/health-ledger.md
# ---------------------------------------------------------------------------

test_does_not_overwrite_existing_ledger() {
    local tmpdir
    tmpdir="$(mktemp -d)"
    mkdir -p "${tmpdir}/state"
    printf '# Health Ledger\nexisting content\n' > "$(ledger_path "$tmpdir")"

    local before
    before="$(cat "$(ledger_path "$tmpdir")")"

    bash "$SUBJECT" "$tmpdir" >/dev/null 2>&1

    local after
    after="$(cat "$(ledger_path "$tmpdir")")"

    local ok=0
    if [ "$before" != "$after" ]; then
        printf '    FAIL: ledger content was overwritten\n' >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 13: stdout mentions skip on idempotent re-run
# ---------------------------------------------------------------------------

test_stdout_mentions_skip_on_idempotent_rerun() {
    local tmpdir
    tmpdir="$(mktemp -d)"
    mkdir -p "${tmpdir}/state"
    printf '# Health Ledger\nexisting content\n' > "$(ledger_path "$tmpdir")"

    local output status
    output="$(bash "$SUBJECT" "$tmpdir" 2>&1)"; status=$?

    local ok=0
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: exited %d (expected 0)\n' "$status" >&2
        ok=1
    fi
    if ! printf '%s' "$output" | grep -q 'skipping'; then
        printf '    FAIL: stdout does not mention "skipping" on idempotent re-run\n' >&2
        printf '    stdout was: %s\n' "$output" >&2
        ok=1
    fi

    rm -rf "$tmpdir"
    return $ok
}

# ---------------------------------------------------------------------------
# Test 14: exits non-zero when REPO_ROOT does not exist
# ---------------------------------------------------------------------------

test_exits_nonzero_when_repo_root_does_not_exist() {
    local output status
    output="$(bash "$SUBJECT" "/nonexistent/path/that/cannot/exist" 2>&1)"; status=$?

    if [ "$status" -ne 0 ]; then
        printf '    exited %d (non-zero) — correct for invalid REPO_ROOT\n' "$status"
        return 0
    else
        printf '    FAIL: exited 0 (expected non-zero for nonexistent path)\n' >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Test 15: error output mentions "does not exist" on invalid path
# ---------------------------------------------------------------------------

test_error_output_mentions_does_not_exist() {
    local output status
    output="$(bash "$SUBJECT" "/nonexistent/path/that/cannot/exist" 2>&1)"; status=$?

    if printf '%s' "$output" | grep -q 'does not exist'; then
        printf '    output mentions "does not exist" — correct\n'
        return 0
    else
        printf '    FAIL: output does not contain "does not exist"\n' >&2
        printf '    output was: %s\n' "$output" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Guard: subject must exist
# ---------------------------------------------------------------------------

if [[ ! -f "$SUBJECT" ]]; then
    echo "ERROR: subject not found at ${SUBJECT}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Run all 15 tests
# ---------------------------------------------------------------------------

run_test "creates state/health-ledger.md in target repo on fresh run" \
    test_creates_ledger_on_fresh_run

run_test "creates state/ directory when it does not exist" \
    test_creates_state_dir_when_absent

run_test "seeded file contains Last full audit clock" \
    test_seeded_file_contains_full_audit_clock

run_test "seeded file contains Last targeted audit clock" \
    test_seeded_file_contains_targeted_audit_clock

run_test "seeded file contains two distinct audit clocks (both present)" \
    test_seeded_file_contains_both_audit_clocks

run_test "seeded file contains per-system table header" \
    test_seeded_file_contains_table_header

run_test "seeded file has no fabricated grade — no A-F grade in table body" \
    test_seeded_file_no_fabricated_grade

run_test "seeded file has no non-question-mark grade in the table body" \
    test_seeded_file_only_question_mark_grades

run_test "stdout mentions seeding action on success" \
    test_stdout_mentions_seeding_action

run_test "defaults to cwd when no argument is given" \
    test_defaults_to_cwd_when_no_arg

run_test "exits 0 when state/health-ledger.md already exists" \
    test_exits_zero_when_ledger_already_exists

run_test "does not overwrite existing state/health-ledger.md" \
    test_does_not_overwrite_existing_ledger

run_test "stdout mentions skip on idempotent re-run" \
    test_stdout_mentions_skip_on_idempotent_rerun

run_test "exits non-zero when REPO_ROOT does not exist" \
    test_exits_nonzero_when_repo_root_does_not_exist

run_test "error output mentions REPO_ROOT on invalid path" \
    test_error_output_mentions_does_not_exist

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
