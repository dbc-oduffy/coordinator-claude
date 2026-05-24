#!/usr/bin/env bash
# bin/tests/test-check-plugin-drift-copy-install.sh
#
# Purpose: Unit tests for the copy_install detection branch in check-plugin-drift.sh.
#
# Spec backlink: docs/plans/2026-05-23-copy-install-drift-coverage.md § Chunk 3 (AC-6)
#
# All git/dir construction is done in tmp — never touches the real ~/.claude/plugins.
# The test builds synthetic source git repos and synthetic live dirs to cover the
# full AC-2 / AC-3 matrix without network or live-install side effects.
#
# Run: bash plugins/coordinator/bin/tests/test-check-plugin-drift-copy-install.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="${SCRIPT_DIR}/../check-plugin-drift.sh"
REFRESH="${SCRIPT_DIR}/../refresh-plugin-live-install.sh"

# ---------------------------------------------------------------------------
# Test framework (mirrors convention from test-coordinator-safe-commit.sh)
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
    echo "--- $name"
    if "$fn"; then
        pass "$name"
    else
        fail "$name"
    fi
}

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        return 0
    else
        echo "    Expected: $(printf '%q' "$expected")" >&2
        echo "    Actual:   $(printf '%q' "$actual")" >&2
        return 1
    fi
}

assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if printf '%s\n' "$haystack" | grep -qF "$needle"; then
        return 0
    else
        echo "    Expected to contain: ${needle}" >&2
        echo "    In: ${haystack}" >&2
        return 1
    fi
}

assert_exit() {
    local label="$1" expected_exit="$2" actual_exit="$3"
    if [[ "$expected_exit" == "$actual_exit" ]]; then
        return 0
    else
        echo "    Expected exit: $expected_exit" >&2
        echo "    Actual exit:   $actual_exit" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Scratch infrastructure
# ---------------------------------------------------------------------------

TMP_ROOT=""

setup_tmp() {
    TMP_ROOT="$(mktemp -d)"
}

teardown_tmp() {
    if [[ -n "$TMP_ROOT" ]] && [[ -d "$TMP_ROOT" ]]; then
        rm -rf "$TMP_ROOT"
    fi
}

# Create a synthetic source git repo and return its path via the first arg (nameref).
# Optionally accepts a commit message for the initial commit.
make_source_repo() {
    local out_var="$1"
    local repo_dir="${TMP_ROOT}/source-${RANDOM}"
    mkdir -p "$repo_dir"
    git -C "$repo_dir" init -q
    git -C "$repo_dir" config user.email "test@test.invalid"
    git -C "$repo_dir" config user.name "Test"
    echo "source content" > "$repo_dir/README.md"
    git -C "$repo_dir" add README.md
    git -C "$repo_dir" commit -q -m "initial"
    # Use nameref-style output (print and capture at call site)
    echo "$repo_dir"
}

# Return the HEAD SHA of a repo.
head_sha() {
    git -C "$1" rev-parse HEAD 2>/dev/null | tr -d '\r'
}

# Create a synthetic live dir with an optional version.txt content.
make_live_dir() {
    local sentinel_content="${1:-}"   # empty = no version.txt
    local live_dir="${TMP_ROOT}/live-${RANDOM}"
    mkdir -p "$live_dir"
    if [[ -n "$sentinel_content" ]]; then
        printf '%s' "$sentinel_content" > "$live_dir/version.txt"
    fi
    echo "$live_dir"
}

# Write a minimal TOML registry with a single copy_install entry and return the path.
make_registry() {
    local source_path="$1"
    local live_path="$2"
    local registry="${TMP_ROOT}/registry-${RANDOM}.toml"
    cat > "$registry" <<TOML
[plugin.mirrors.test-plugin]
propagation_mode = "copy_install"
source_path = "${source_path}"
live_path   = "${live_path}"
TOML
    echo "$registry"
}

# ---------------------------------------------------------------------------
# Rename the registry to what the probe expects (registry.local.toml in REGISTRY_DIR).
# ---------------------------------------------------------------------------

install_registry() {
    local src_registry="$1"
    local reg_dir="${TMP_ROOT}/regdir-${RANDOM}"
    mkdir -p "$reg_dir"
    cp "$src_registry" "$reg_dir/registry.local.toml"
    echo "$reg_dir"
}

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# AC-2(d): sentinel present, matches source HEAD → [ok], exit 0
test_clean_equal_sha() {
    setup_tmp
    local source_dir live_dir reg_dir
    source_dir="$(make_source_repo _)"
    local sha; sha="$(head_sha "$source_dir")"
    live_dir="$(make_live_dir "$sha")"
    local registry; registry="$(make_registry "$source_dir" "$live_dir")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" 2>&1)"
    exit_code=$?

    assert_contains "clean: [ok] in output" "[ok]" "$output" || { teardown_tmp; return 1; }
    assert_exit "clean: exit 0" 0 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-2(e): sentinel present, well-formed, but != source HEAD → [drift], exit 1
test_drifted_unequal_sha() {
    setup_tmp
    local source_dir live_dir reg_dir
    source_dir="$(make_source_repo _)"
    # Add another commit so source HEAD != the sentinel we will write.
    local old_sha; old_sha="$(head_sha "$source_dir")"
    echo "second" > "$source_dir/second.md"
    git -C "$source_dir" add second.md
    git -C "$source_dir" commit -q -m "second"
    # Sentinel records old SHA (stale).
    live_dir="$(make_live_dir "$old_sha")"
    local registry; registry="$(make_registry "$source_dir" "$live_dir")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" 2>&1)"
    exit_code=$?

    assert_contains "drifted: [drift] in output" "[drift]" "$output" || { teardown_tmp; return 1; }
    assert_contains "drifted: copy_install in output" "copy_install" "$output" || { teardown_tmp; return 1; }
    assert_exit "drifted: exit 1" 1 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-2(b): no version.txt → [info], exit 0 (not drift)
test_no_sentinel_info_exit0() {
    setup_tmp
    local source_dir live_dir reg_dir
    source_dir="$(make_source_repo _)"
    live_dir="$(make_live_dir "")"   # no sentinel
    local registry; registry="$(make_registry "$source_dir" "$live_dir")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" 2>&1)"
    exit_code=$?

    assert_contains "no-sentinel: [info] in output" "[info]" "$output" || { teardown_tmp; return 1; }
    assert_exit "no-sentinel: exit 0" 0 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-2(a): live_path missing → [drift], exit 1
test_missing_live_path() {
    setup_tmp
    local source_dir reg_dir
    source_dir="$(make_source_repo _)"
    local nonexistent_live="${TMP_ROOT}/does-not-exist"
    local registry; registry="$(make_registry "$source_dir" "$nonexistent_live")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" 2>&1)"
    exit_code=$?

    assert_contains "missing-live: [drift] in output" "[drift]" "$output" || { teardown_tmp; return 1; }
    assert_exit "missing-live: exit 1" 1 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-3: --check-clean-only on copy_install → exit 0 (no live git working tree)
test_check_clean_only_exit0() {
    setup_tmp
    local source_dir live_dir reg_dir
    source_dir="$(make_source_repo _)"
    local sha; sha="$(head_sha "$source_dir")"
    live_dir="$(make_live_dir "$sha")"
    local registry; registry="$(make_registry "$source_dir" "$live_dir")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" --check-clean-only 2>&1)"
    exit_code=$?

    assert_exit "--check-clean-only: exit 0" 0 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-2(c) / AC-6 malformed sentinel: non-40-hex-char string → [warn], exit 0 (not drift)
test_malformed_sentinel_warn_not_drift() {
    setup_tmp
    local source_dir live_dir reg_dir
    source_dir="$(make_source_repo _)"
    # Write a sentinel that is clearly malformed (wrong length, non-hex chars).
    live_dir="$(make_live_dir "not-a-sha")"
    local registry; registry="$(make_registry "$source_dir" "$live_dir")"
    reg_dir="$(install_registry "$registry")"

    local output exit_code
    output="$(MACHINE_LOCAL_REGISTRY_DIR="$reg_dir" HOME="$TMP_ROOT" bash "$PROBE" 2>&1)"
    exit_code=$?

    assert_contains "malformed: [warn] in output" "[warn]" "$output" || { teardown_tmp; return 1; }
    assert_contains "malformed: 'malformed' in output" "malformed" "$output" || { teardown_tmp; return 1; }
    assert_exit "malformed: exit 0 (not drift)" 0 "$exit_code" || { teardown_tmp; return 1; }
    teardown_tmp
}

# AC-6 restore-orphan: REPLACE-vs-overlay restore semantics in the copy_install
# restore path of refresh-plugin-live-install.sh.
#
# Two-part guard (code-reviewer F5: a POSIX `rm-rf + cp-r` demo alone tests its own
# implementation, not the script). Part A is the behavioral demonstration; Part B is
# the actual regression guard — a structural assertion that the SCRIPT uses REPLACE
# semantics (`rm -rf "$LIVE_PATH"` then `cp -r "$SNAPSHOT_PATH"`) and NOT the overlay
# form (`cp -r "$SNAPSHOT_PATH/." "$LIVE_PATH/"`) at its copy_install restore sites.
# The live end-to-end restore path is additionally proven by the AC-9 dogfood
# (refresh-plugin-live-install.sh holodeck-control) recorded in the plan; a full
# refresh-script integration harness is tracked in the improvement queue.
test_restore_orphan_gone() {
    setup_tmp

    # Part A — behavioral demonstration of REPLACE semantics.
    local snapshot_dir="${TMP_ROOT}/snapshot"
    mkdir -p "$snapshot_dir"
    echo "original_file" > "$snapshot_dir/original.txt"
    local live_dir="${TMP_ROOT}/live"
    cp -r "$snapshot_dir" "$live_dir"
    echo "orphan" > "$live_dir/orphan_from_failed_install.txt"
    rm -rf "$live_dir"
    cp -r "$snapshot_dir" "$live_dir"
    if [[ -f "$live_dir/orphan_from_failed_install.txt" ]]; then
        echo "    FAIL: orphan survived REPLACE restore (Part A)" >&2
        teardown_tmp; return 1
    fi
    if [[ ! -f "$live_dir/original.txt" ]]; then
        echo "    FAIL: original missing after restore (Part A)" >&2
        teardown_tmp; return 1
    fi

    # Part B — structural regression guard against the COPY_INSTALL branch reverting
    # to overlay. Scoped to the copy_install branch only (the pre-existing git-managed
    # restore legitimately uses overlay `cp -r SNAPSHOT/. LIVE/` because its live IS a
    # git checkout — a global grep would false-positive on it). The copy_install restore
    # must clear LIVE_PATH (rm -rf) then `cp -r "$SNAPSHOT_PATH" "$LIVE_PATH"` (no `/.`).
    local ci_region
    ci_region="$(awk '/PROPAGATION_MODE" == "copy_install"/,/^fi$/' "$REFRESH")"
    if ! printf '%s\n' "$ci_region" | grep -qF 'rm -rf "$LIVE_PATH"'; then
        echo "    FAIL: copy_install branch no longer rm-rf's LIVE_PATH before restore (REPLACE semantics lost)" >&2
        teardown_tmp; return 1
    fi
    if printf '%s\n' "$ci_region" | grep -qF 'cp -r "$SNAPSHOT_PATH/." "$LIVE_PATH/"'; then
        echo "    FAIL: copy_install branch uses overlay restore (cp -r SNAPSHOT/. LIVE/) — orphans would survive" >&2
        teardown_tmp; return 1
    fi

    teardown_tmp
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

echo "=== test-check-plugin-drift-copy-install.sh ==="
echo ""

run_test "AC-2(d): clean equal SHA → [ok] exit 0"          test_clean_equal_sha
run_test "AC-2(e): drifted unequal SHA → [drift] exit 1"   test_drifted_unequal_sha
run_test "AC-2(b): no sentinel → [info] exit 0"             test_no_sentinel_info_exit0
run_test "AC-2(a): missing live path → [drift] exit 1"      test_missing_live_path
run_test "AC-3: --check-clean-only → exit 0"                test_check_clean_only_exit0
run_test "AC-2(c)/AC-6: malformed sentinel → [warn] exit 0" test_malformed_sentinel_warn_not_drift
run_test "AC-6: restore-orphan REPLACE semantics"           test_restore_orphan_gone

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ ${FAIL} -gt 0 ]]; then
    echo ""
    echo "Failed tests:"
    for msg in "${FAIL_MSGS[@]}"; do
        echo "  - $msg"
    done
    exit 1
fi

exit 0
