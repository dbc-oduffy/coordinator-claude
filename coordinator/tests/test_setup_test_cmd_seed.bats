#!/usr/bin/env bash
# test_setup_test_cmd_seed.bats — plain-bash harness for lib/setup-detect-test-cmd.sh
#
# Purpose: verify that setup-detect-test-cmd.sh correctly detects stack markers
# and seeds fast_test_cmd / full_test_cmd into coordinator.local.md frontmatter.
# All tests operate on a TEMP repo dir — the live repo is never touched.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1 (AC1)
#
# Covers:
#   T1  — Node.js stack (test + test:unit + pnpm) → fast=pnpm run test:unit, full=pnpm run test
#   T2  — Python stack (pyproject.toml with [tool.pytest]) → fast=pytest
#   T2b — Python stack keys land in frontmatter (resolver awk parser shape)
#   T3  — Ambiguous (two stacks, two fast candidates) → exit 1 fail-loud, no write
#   T3b — Ambiguous path — output names at least one candidate command
#   T4a — Already-configured repo → exit 2 no-op, keys unchanged
#   T4b — --force overwrites stale keys, exactly one of each after upsert
#   T5  — No stack markers → exit 2 with diagnostic
#   T6  — Rust stack (Cargo.toml) → fast=cargo test --lib, full=cargo test
#   T7  — Missing coordinator.local.md → exit 3 with remediation
#   T8  — coordinator.local.md without frontmatter → exit 3 with remediation
#   T9  — Keys land in frontmatter between the two --- delimiters
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness mirroring bin/tests/check-machine-path-leak.bats.
# The file is named .bats so any acceptance-oracle grep resolves it correctly.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/tests/test_setup_test_cmd_seed.bats
#      from the ~/.claude repo root.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../lib/setup-detect-test-cmd.sh"

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
# Shared helpers
# ---------------------------------------------------------------------------

# _make_local_md <root> — create a minimal coordinator.local.md with frontmatter
_make_local_md() {
    local root="$1"
    {
        printf -- '---\n'
        printf 'project_type: test\n'
        printf -- '---\n'
        printf '\n# Test project\n'
    } > "$root/coordinator.local.md"
}

# _make_local_md_with_keys <root> <fast> <full>
# Create coordinator.local.md with preset key values (for upsert / idempotency tests).
_make_local_md_with_keys() {
    local root="$1" fast="$2" full="$3"
    {
        printf -- '---\n'
        printf 'project_type: test\n'
        printf 'fast_test_cmd: %s\n' "$fast"
        printf 'full_test_cmd: %s\n' "$full"
        printf -- '---\n'
        printf '\n# Test project\n'
    } > "$root/coordinator.local.md"
}

# _read_fm_key <file> <key>
# Extract a flat top-level frontmatter key value from coordinator.local.md
# using the same awk parser shape as coordinator-resolve-validation-cmd.sh.
_read_fm_key() {
    local file="$1" key="$2"
    local fm val
    fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$file" 2>/dev/null)
    val=$(printf '%s\n' "$fm" \
        | grep -m1 "^${key}:" \
        | sed -E "s/^${key}:[[:space:]]*//" \
        | tr -d '"' \
        | sed -E "s/^[[:space:]]+//; s/[[:space:]]+$//")
    printf '%s' "$val"
}

# ---------------------------------------------------------------------------
# T1 — Node.js stack: test + test:unit + pnpm
#      Expect: fast=pnpm run test:unit, full=pnpm run test
# ---------------------------------------------------------------------------

test_T1_node_stack_pnpm() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "test-project",
  "scripts": {
    "test:unit": "jest --testPathPattern=unit",
    "test": "jest",
    "lint": "eslint ."
  }
}
EOF
    touch "$tmpdir/pnpm-lock.yaml"
    _make_local_md "$tmpdir"

    local status=0
    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: subject exited %d (expected 0)\n' "$status" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local fast full
    fast=$(_read_fm_key "$tmpdir/coordinator.local.md" "fast_test_cmd")
    full=$(_read_fm_key "$tmpdir/coordinator.local.md" "full_test_cmd")

    rm -rf "$tmpdir"

    if [ "$fast" != "pnpm run test:unit" ]; then
        printf '    FAIL: fast_test_cmd=%s (expected "pnpm run test:unit")\n' "$fast" >&2
        return 1
    fi
    if [ "$full" != "pnpm run test" ]; then
        printf '    FAIL: full_test_cmd=%s (expected "pnpm run test")\n' "$full" >&2
        return 1
    fi
    printf '    fast=%s, full=%s — correct\n' "$fast" "$full"
    return 0
}

# ---------------------------------------------------------------------------
# T2 — Python stack: pyproject.toml with [tool.pytest.ini_options]
#      Expect: fast=pytest written
# ---------------------------------------------------------------------------

test_T2_python_stack_pytest() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
    _make_local_md "$tmpdir"

    local status=0
    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: subject exited %d (expected 0)\n' "$status" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local fast
    fast=$(_read_fm_key "$tmpdir/coordinator.local.md" "fast_test_cmd")

    rm -rf "$tmpdir"

    if [ "$fast" != "pytest" ]; then
        printf '    FAIL: fast_test_cmd=%s (expected "pytest")\n' "$fast" >&2
        return 1
    fi
    printf '    fast_test_cmd=%s — correct\n' "$fast"
    return 0
}

# ---------------------------------------------------------------------------
# T2b — Python stack: keys land in frontmatter (resolver awk parser shape)
# ---------------------------------------------------------------------------

test_T2b_python_keys_in_frontmatter() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
    _make_local_md "$tmpdir"

    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1

    # Extract frontmatter using the same awk parser shape as the resolver
    local fm resolved
    fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' \
        "$tmpdir/coordinator.local.md")
    resolved=$(printf '%s\n' "$fm" \
        | grep -m1 '^fast_test_cmd:' \
        | sed -E 's/^fast_test_cmd:[[:space:]]*//' \
        | tr -d '"' \
        | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')

    rm -rf "$tmpdir"

    if [ -z "$resolved" ]; then
        printf '    FAIL: fast_test_cmd not found in frontmatter\n' >&2
        return 1
    fi
    if [ "$resolved" != "pytest" ]; then
        printf '    FAIL: resolved=%s (expected "pytest")\n' "$resolved" >&2
        return 1
    fi
    printf '    awk-resolved fast_test_cmd=%s in frontmatter — correct\n' "$resolved"
    return 0
}

# ---------------------------------------------------------------------------
# T3 — Ambiguous: both Node and Python → fail-loud, exit 1, file unchanged
# ---------------------------------------------------------------------------

test_T3_ambiguous_multi_stack_exit1() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "poly-project",
  "scripts": {
    "test": "jest"
  }
}
EOF
    cat > "$tmpdir/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
    _make_local_md "$tmpdir"
    local before
    before="$(cat "$tmpdir/coordinator.local.md")"

    local status=0
    local output
    output="$(bash "$SUBJECT" --root "$tmpdir" --non-interactive 2>&1)" || status=$?

    local after
    after="$(cat "$tmpdir/coordinator.local.md")"

    rm -rf "$tmpdir"

    if [ "$status" -ne 1 ]; then
        printf '    FAIL: subject exited %d (expected 1 for ambiguous)\n' "$status" >&2
        return 1
    fi

    if [ "$before" != "$after" ]; then
        printf '    FAIL: coordinator.local.md was modified (should be unchanged on ambiguity)\n' >&2
        return 1
    fi

    case "$output" in
        *AMBIGUOUS*|*ambiguous*)
            printf '    exit 1, file unchanged, output mentions AMBIGUOUS — correct\n'
            return 0
            ;;
        *)
            printf '    FAIL: output does not mention AMBIGUOUS/ambiguous\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# T3b — Ambiguous path: output names at least one candidate command
# ---------------------------------------------------------------------------

test_T3b_ambiguous_names_candidate() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "poly-project",
  "scripts": {
    "test": "jest"
  }
}
EOF
    cat > "$tmpdir/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
    _make_local_md "$tmpdir"

    local status=0
    local output
    output="$(bash "$SUBJECT" --root "$tmpdir" --non-interactive 2>&1)" || status=$?

    rm -rf "$tmpdir"

    if [ "$status" -ne 1 ]; then
        printf '    FAIL: subject exited %d (expected 1 for ambiguous)\n' "$status" >&2
        return 1
    fi

    case "$output" in
        *npm*|*pnpm*|*pytest*)
            printf '    output names at least one candidate — correct\n'
            return 0
            ;;
        *)
            printf '    FAIL: output names no candidate command (npm/pnpm/pytest)\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# T4a — Already-configured repo → exit 2 no-op, keys unchanged
# ---------------------------------------------------------------------------

test_T4a_already_configured_noop() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "test-project",
  "scripts": {
    "test:unit": "jest --unit",
    "test": "jest"
  }
}
EOF
    touch "$tmpdir/pnpm-lock.yaml"
    _make_local_md_with_keys "$tmpdir" "npm run old-test" "npm run old-full"

    local status=0
    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1 || status=$?

    local fast full
    fast=$(_read_fm_key "$tmpdir/coordinator.local.md" "fast_test_cmd")
    full=$(_read_fm_key "$tmpdir/coordinator.local.md" "full_test_cmd")

    rm -rf "$tmpdir"

    if [ "$status" -ne 2 ]; then
        printf '    FAIL: subject exited %d (expected 2 for no-op)\n' "$status" >&2
        return 1
    fi
    if [ "$fast" != "npm run old-test" ]; then
        printf '    FAIL: fast_test_cmd changed to %s (should be unchanged)\n' "$fast" >&2
        return 1
    fi
    if [ "$full" != "npm run old-full" ]; then
        printf '    FAIL: full_test_cmd changed to %s (should be unchanged)\n' "$full" >&2
        return 1
    fi
    printf '    exit 2, keys unchanged — correct no-op behavior\n'
    return 0
}

# ---------------------------------------------------------------------------
# T4b — --force overwrites stale keys, exactly one of each after upsert
# ---------------------------------------------------------------------------

test_T4b_force_overwrites_stale_keys() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/package.json" <<'EOF'
{
  "name": "test-project",
  "scripts": {
    "test:unit": "jest --unit",
    "test": "jest"
  }
}
EOF
    touch "$tmpdir/pnpm-lock.yaml"
    _make_local_md_with_keys "$tmpdir" "npm run old-test" "npm run old-full"

    local status=0
    bash "$SUBJECT" --root "$tmpdir" --non-interactive --force >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: subject exited %d (expected 0 with --force)\n' "$status" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local fast_count full_count
    fast_count=$(grep -c '^fast_test_cmd:' "$tmpdir/coordinator.local.md")
    full_count=$(grep -c '^full_test_cmd:' "$tmpdir/coordinator.local.md")

    local fast full
    fast=$(_read_fm_key "$tmpdir/coordinator.local.md" "fast_test_cmd")
    full=$(_read_fm_key "$tmpdir/coordinator.local.md" "full_test_cmd")

    rm -rf "$tmpdir"

    if [ "$fast_count" -ne 1 ]; then
        printf '    FAIL: fast_test_cmd appears %d times (expected exactly 1)\n' "$fast_count" >&2
        return 1
    fi
    if [ "$full_count" -ne 1 ]; then
        printf '    FAIL: full_test_cmd appears %d times (expected exactly 1)\n' "$full_count" >&2
        return 1
    fi
    if [ "$fast" != "pnpm run test:unit" ]; then
        printf '    FAIL: fast_test_cmd=%s (expected "pnpm run test:unit")\n' "$fast" >&2
        return 1
    fi
    if [ "$full" != "pnpm run test" ]; then
        printf '    FAIL: full_test_cmd=%s (expected "pnpm run test")\n' "$full" >&2
        return 1
    fi
    printf '    --force: keys overwritten, each appears exactly once — correct\n'
    return 0
}

# ---------------------------------------------------------------------------
# T5 — No stack markers → exit 2 with diagnostic
# ---------------------------------------------------------------------------

test_T5_no_stack_markers_exit2() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    _make_local_md "$tmpdir"
    local before
    before="$(cat "$tmpdir/coordinator.local.md")"

    local status=0
    local output
    output="$(bash "$SUBJECT" --root "$tmpdir" --non-interactive 2>&1)" || status=$?

    local after
    after="$(cat "$tmpdir/coordinator.local.md")"

    rm -rf "$tmpdir"

    if [ "$status" -ne 2 ]; then
        printf '    FAIL: subject exited %d (expected 2 for no stack markers)\n' "$status" >&2
        return 1
    fi

    if [ "$before" != "$after" ]; then
        printf '    FAIL: coordinator.local.md was modified (should be unchanged)\n' >&2
        return 1
    fi

    case "$output" in
        *package.json*|*pytest*|*Cargo*)
            printf '    exit 2, file unchanged, diagnostic names at least one checked stack — correct\n'
            return 0
            ;;
        *)
            printf '    FAIL: diagnostic does not name any stack checked (package.json/pytest/Cargo)\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# T6 — Rust stack (Cargo.toml)
#      Expect: fast=cargo test --lib, full=cargo test
# ---------------------------------------------------------------------------

test_T6_rust_stack_cargo() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/Cargo.toml" <<'EOF'
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"

[dependencies]
EOF
    _make_local_md "$tmpdir"

    local status=0
    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1 || status=$?

    if [ "$status" -ne 0 ]; then
        printf '    FAIL: subject exited %d (expected 0)\n' "$status" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local fast full
    fast=$(_read_fm_key "$tmpdir/coordinator.local.md" "fast_test_cmd")
    full=$(_read_fm_key "$tmpdir/coordinator.local.md" "full_test_cmd")

    rm -rf "$tmpdir"

    if [ "$fast" != "cargo test --lib" ]; then
        printf '    FAIL: fast_test_cmd=%s (expected "cargo test --lib")\n' "$fast" >&2
        return 1
    fi
    if [ "$full" != "cargo test" ]; then
        printf '    FAIL: full_test_cmd=%s (expected "cargo test")\n' "$full" >&2
        return 1
    fi
    printf '    fast=%s, full=%s — correct\n' "$fast" "$full"
    return 0
}

# ---------------------------------------------------------------------------
# T7 — Missing coordinator.local.md → exit 3 with remediation message
# ---------------------------------------------------------------------------

test_T7_missing_local_md_exit3() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/Cargo.toml" <<'EOF'
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"
EOF
    # Intentionally do NOT create coordinator.local.md

    local status=0
    local output
    output="$(bash "$SUBJECT" --root "$tmpdir" --non-interactive 2>&1)" || status=$?

    rm -rf "$tmpdir"

    if [ "$status" -ne 3 ]; then
        printf '    FAIL: subject exited %d (expected 3 for missing coordinator.local.md)\n' "$status" >&2
        return 1
    fi

    case "$output" in
        *coordinator.local.md*)
            ;;
        *)
            printf '    FAIL: output does not mention coordinator.local.md\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac

    case "$output" in
        *repo-setup*|*Remediation*|*create*)
            printf '    exit 3, output names coordinator.local.md and remediation — correct\n'
            return 0
            ;;
        *)
            printf '    FAIL: output lacks remediation hint (repo-setup/Remediation/create)\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# T8 — coordinator.local.md with no frontmatter (no --- markers) → exit 3
# ---------------------------------------------------------------------------

test_T8_no_frontmatter_exit3() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/Cargo.toml" <<'EOF'
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"
EOF
    {
        printf '# No frontmatter here\n\n'
        printf 'Just a plain markdown file with no YAML block.\n'
    } > "$tmpdir/coordinator.local.md"

    local status=0
    local output
    output="$(bash "$SUBJECT" --root "$tmpdir" --non-interactive 2>&1)" || status=$?

    rm -rf "$tmpdir"

    if [ "$status" -ne 3 ]; then
        printf '    FAIL: subject exited %d (expected 3 for missing frontmatter)\n' "$status" >&2
        return 1
    fi

    case "$output" in
        *frontmatter*|*---*)
            printf '    exit 3, diagnostic mentions frontmatter/--- — correct\n'
            return 0
            ;;
        *)
            printf '    FAIL: output does not mention frontmatter or --- delimiter\n' >&2
            printf '    output was: %s\n' "$output" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# T9 — Keys land in frontmatter between the two --- delimiters
# ---------------------------------------------------------------------------

test_T9_keys_in_frontmatter_block() {
    local tmpdir
    tmpdir="$(mktemp -d)"

    cat > "$tmpdir/Cargo.toml" <<'EOF'
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"
EOF
    _make_local_md "$tmpdir"

    bash "$SUBJECT" --root "$tmpdir" --non-interactive >/dev/null 2>&1

    # Extract the frontmatter block (between first and second --- delimiters)
    local fm
    fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$tmpdir/coordinator.local.md")

    local has_fast has_full
    has_fast=0
    has_full=0
    printf '%s\n' "$fm" | grep -q '^fast_test_cmd:' && has_fast=1 || true
    printf '%s\n' "$fm" | grep -q '^full_test_cmd:' && has_full=1 || true

    rm -rf "$tmpdir"

    if [ "$has_fast" -ne 1 ]; then
        printf '    FAIL: fast_test_cmd not found in frontmatter block\n' >&2
        return 1
    fi
    if [ "$has_full" -ne 1 ]; then
        printf '    FAIL: full_test_cmd not found in frontmatter block\n' >&2
        return 1
    fi
    printf '    both keys present in frontmatter block — correct\n'
    return 0
}

# ---------------------------------------------------------------------------
# Preflight: subject must exist
# ---------------------------------------------------------------------------

if [[ ! -f "$SUBJECT" ]]; then
    echo "ERROR: subject not found at ${SUBJECT}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

run_test "T1: node stack with pnpm + test:unit + test → fast=pnpm run test:unit, full=pnpm run test" \
    test_T1_node_stack_pnpm

run_test "T2: python stack (pyproject.toml + [tool.pytest]) → fast_test_cmd=pytest written" \
    test_T2_python_stack_pytest

run_test "T2b: python stack keys land in coordinator.local.md frontmatter (resolver awk shape)" \
    test_T2b_python_keys_in_frontmatter

run_test "T3: ambiguous multi-stack (node + python) → exit 1 fail-loud, file unchanged" \
    test_T3_ambiguous_multi_stack_exit1

run_test "T3b: ambiguous path — output names at least one candidate command" \
    test_T3b_ambiguous_names_candidate

run_test "T4a: already-configured repo → exit 2 no-op, keys unchanged" \
    test_T4a_already_configured_noop

run_test "T4b: --force overwrites stale keys, exactly one of each after upsert" \
    test_T4b_force_overwrites_stale_keys

run_test "T5: no stack markers → exit 2, coordinator.local.md unchanged" \
    test_T5_no_stack_markers_exit2

run_test "T6: rust stack (Cargo.toml) → fast=cargo test --lib, full=cargo test" \
    test_T6_rust_stack_cargo

run_test "T7: missing coordinator.local.md → exit 3 with remediation message" \
    test_T7_missing_local_md_exit3

run_test "T8: coordinator.local.md with no frontmatter (no --- markers) → exit 3" \
    test_T8_no_frontmatter_exit3

run_test "T9: written keys are in the frontmatter block (between --- delimiters)" \
    test_T9_keys_in_frontmatter_block

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
