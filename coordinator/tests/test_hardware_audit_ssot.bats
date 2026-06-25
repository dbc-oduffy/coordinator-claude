#!/usr/bin/env bash
# test_hardware_audit_ssot.bats — regression net for the hardware audit SSOT.
#
# Purpose: verify that detect-hardware.sh writes hardware.cores/hardware.ram_gb
# to hardware.local.toml (AC4), that an existing-install registry.toml without
# `hardware` in concerns gets it added (AC10), and that hardware.local.toml IS
# written when running against a non-Windows temp-HOME — proving the audit runs
# BEFORE the non-Windows exit 0 guard in install-substrate.sh (AC11).
#
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4
#
# NOTE: bats is not installed in this environment. This file uses a plain-bash
# test harness mirroring bin/tests/check-machine-path-leak.bats.
# The file is named .bats so any acceptance-oracle grep resolves it correctly.
#
# Run: cd ~/.claude && bash plugins/coordinator-claude/coordinator/tests/test_hardware_audit_ssot.bats
#
# Negative-spec: tests do NOT exercise the Windows PowerShell path — that branch
# requires powershell.exe; these tests exercise the macOS/Linux detection path.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DETECT_HW="${PLUGIN_ROOT}/lib/detect-hardware.sh"
ML_IMPL="${PLUGIN_ROOT}/templates/bin/_machine_local.py"
ML_WRAPPER="${PLUGIN_ROOT}/templates/bin/machine-local"

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
# Per-test setup/teardown helpers
# ---------------------------------------------------------------------------

# _setup_test_home creates a temp HOME with the machine-local structure and
# exports the env vars needed by detect-hardware.sh and machine-local.
# Sets TEST_HOME, ML_DIR, BIN_DIR in the caller's scope.
_setup_test_home() {
    TEST_HOME="$(mktemp -d)"
    ML_DIR="${TEST_HOME}/.claude/machine-local"
    BIN_DIR="${TEST_HOME}/.claude/bin"
    mkdir -p "$ML_DIR" "$BIN_DIR"

    # Install the machine-local wrapper and implementation into the temp bin dir.
    cp "$ML_WRAPPER" "${BIN_DIR}/machine-local"
    cp "$ML_IMPL"    "${BIN_DIR}/_machine_local.py"
    chmod +x "${BIN_DIR}/machine-local"

    # Point the reader/writer at our temp registry dir.
    export MACHINE_LOCAL_REGISTRY_DIR="$ML_DIR"

    # Ensure the bin dir is on PATH so detect-hardware.sh finds `machine-local`.
    export PATH="${BIN_DIR}:${PATH}"

    # Seed a registry.toml with hardware in concerns so machine-local get resolves.
    # AC4/AC11 tests rely on this baseline; AC10 overwrites it with the no-hardware form.
    cat > "${ML_DIR}/registry.toml" <<'EOF'
schema = 1
concerns = ["hardware"]
EOF
}

# _teardown_test_home removes the temp HOME and unsets env vars.
_teardown_test_home() {
    [[ -n "${TEST_HOME:-}" && -d "${TEST_HOME}" ]] && rm -rf "${TEST_HOME}"
    unset MACHINE_LOCAL_REGISTRY_DIR
    TEST_HOME=""
    ML_DIR=""
    BIN_DIR=""
}

# ---------------------------------------------------------------------------
# Helper: seed a registry.toml without `hardware` in concerns
# ---------------------------------------------------------------------------

_seed_registry_no_hardware() {
    cat > "${ML_DIR}/registry.toml" <<'EOF'
schema = 1
concerns = ["project_rag", "unreal"]
EOF
}

# ---------------------------------------------------------------------------
# Helper: run the same Python inline migration that install-substrate.sh §3g
# uses to register 'hardware' in concerns.
# ---------------------------------------------------------------------------

_run_concerns_migration() {
    local reg="$1"
    # Review: reviewer — mirror the fixed Python from install-substrate.sh §3g
    # (Finding 1: re.DOTALL for multiline arrays; Finding 2: portable tomllib import).
    python3 - "$reg" <<'PYEOF'
import sys, re, os

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

if tomllib is not None:
    try:
        data = tomllib.loads(content)
    except Exception:
        sys.exit(0)
    concerns = data.get('concerns')
    if not isinstance(concerns, list):
        sys.exit(0)
    if 'hardware' in concerns:
        sys.exit(0)
else:
    if re.search(r'["\']hardware["\']', content):
        sys.exit(0)

# Finding 1 fix: re.DOTALL + multiline-aware insert (avoids double-comma).
inline_pat = re.compile(r'^(concerns\s*=\s*\[)([^\]]*?)(\])', re.MULTILINE | re.DOTALL)
m = inline_pat.search(content)
if m:
    inner = m.group(2)
    if '\n' in inner:
        lines = inner.rstrip().split('\n')
        last_line = lines[-1] if lines else ''
        indent_count = len(last_line) - len(last_line.lstrip())
        indent_str = ' ' * indent_count if indent_count else '  '
        insert = indent_str + '"hardware",\n'
        new_content = content[:m.end(2)] + insert + content[m.end(2):]
    else:
        inner_stripped = inner.strip()
        new_inner = (inner_stripped + ', "hardware"') if inner_stripped else '"hardware"'
        new_content = content[:m.start(2)] + new_inner + content[m.end(2):]
else:
    section_pat = re.compile(r'^\[', re.MULTILINE)
    sm = section_pat.search(content)
    insert_line = 'concerns = ["hardware"]\n'
    if sm:
        new_content = content[:sm.start()] + insert_line + '\n' + content[sm.start():]
    else:
        new_content = content.rstrip('\n') + '\n' + insert_line

if tomllib is not None:
    try:
        parsed = tomllib.loads(new_content)
        new_concerns = parsed.get('concerns', [])
        if 'hardware' not in new_concerns:
            sys.exit(1)
        orig_concerns = tomllib.loads(content).get('concerns', [])
        for c in orig_concerns:
            if c not in new_concerns:
                print(f'[setup] ERROR: concern "{c}" was lost — aborting', file=sys.stderr)
                sys.exit(1)
    except Exception:
        sys.exit(1)

tmp = path + '.tmp.' + str(os.getpid())
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(new_content)
os.replace(tmp, path)
print('[machine-local] registered hardware concern in registry.toml')
PYEOF
}

# ---------------------------------------------------------------------------
# AC4: detector writes hardware.cores/hardware.ram_gb via --concern writer
# ---------------------------------------------------------------------------

test_ac4_writes_cores() {
    _setup_test_home
    local ok=0

    local output status
    output="$(bash "$DETECT_HW" 2>&1)"; status=$?

    if [ "$status" -ne 0 ]; then
        printf '    detect-hardware output: %s\n' "$output" >&2
        ok=1
    fi

    if [ $ok -eq 0 ] && [ ! -f "${ML_DIR}/hardware.local.toml" ]; then
        printf '    FAIL: hardware.local.toml not created\n' >&2
        ok=1
    fi

    local cores_val cores_status
    if [ $ok -eq 0 ]; then
        cores_val="$(machine-local get hardware.cores 2>&1)"; cores_status=$?
        if [ "$cores_status" -ne 0 ]; then
            printf '    FAIL: machine-local get hardware.cores failed (exit %d)\n' "$cores_status" >&2
            ok=1
        fi
    fi

    if [ $ok -eq 0 ]; then
        if ! [[ "$cores_val" =~ ^[1-9][0-9]*$ ]]; then
            printf '    FAIL: hardware.cores not a positive integer: "%s"\n' "$cores_val" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

test_ac4_writes_ram_gb() {
    _setup_test_home
    local ok=0

    local output status
    output="$(bash "$DETECT_HW" 2>&1)"; status=$?

    if [ "$status" -ne 0 ]; then
        printf '    detect-hardware output: %s\n' "$output" >&2
        ok=1
    fi

    local ram_val ram_status
    if [ $ok -eq 0 ]; then
        ram_val="$(machine-local get hardware.ram_gb 2>&1)"; ram_status=$?
        if [ "$ram_status" -ne 0 ]; then
            printf '    FAIL: machine-local get hardware.ram_gb failed (exit %d)\n' "$ram_status" >&2
            ok=1
        fi
    fi

    if [ $ok -eq 0 ]; then
        if ! [[ "$ram_val" =~ ^[1-9][0-9]*$ ]]; then
            printf '    FAIL: hardware.ram_gb not a positive integer: "%s"\n' "$ram_val" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

test_ac4_idempotent() {
    _setup_test_home
    local ok=0

    # First run
    local output status
    output="$(bash "$DETECT_HW" 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: first detect-hardware run failed: %s\n' "$output" >&2
        ok=1
    fi

    local cores_first ram_first
    if [ $ok -eq 0 ]; then
        cores_first="$(machine-local get hardware.cores 2>&1)"
        ram_first="$(machine-local get hardware.ram_gb 2>&1)"

        # Second run
        output="$(bash "$DETECT_HW" 2>&1)"; status=$?
        if [ "$status" -ne 0 ]; then
            printf '    FAIL: second detect-hardware run failed: %s\n' "$output" >&2
            ok=1
        fi
    fi

    if [ $ok -eq 0 ]; then
        local cores_second ram_second
        cores_second="$(machine-local get hardware.cores 2>&1)"
        ram_second="$(machine-local get hardware.ram_gb 2>&1)"

        if [ "$cores_first" != "$cores_second" ]; then
            printf '    FAIL: hardware.cores not stable across runs ("%s" vs "%s")\n' \
                "$cores_first" "$cores_second" >&2
            ok=1
        fi

        if [ "$ram_first" != "$ram_second" ]; then
            printf '    FAIL: hardware.ram_gb not stable across runs ("%s" vs "%s")\n' \
                "$ram_first" "$ram_second" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

# ---------------------------------------------------------------------------
# AC10: existing-install scenario — registry.toml without `hardware` in
#        concerns gets `hardware` appended via migration, and hardware.cores
#        resolves afterwards.
# ---------------------------------------------------------------------------

test_ac10_migration_appends_hardware_concern() {
    _setup_test_home
    local ok=0

    _seed_registry_no_hardware

    local mig_out mig_status
    mig_out="$(_run_concerns_migration "${ML_DIR}/registry.toml" 2>&1)"; mig_status=$?
    if [ "$mig_status" -ne 0 ]; then
        printf '    FAIL: migration failed (exit %d): %s\n' "$mig_status" "$mig_out" >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        local py_out py_status
        py_out="$(python3 -c "
import tomllib, sys
with open('${ML_DIR}/registry.toml', 'rb') as f:
    data = tomllib.load(f)
concerns = data.get('concerns', [])
if 'hardware' in concerns:
    print('found')
else:
    print('missing')
    sys.exit(1)
" 2>&1)"; py_status=$?
        if [ "$py_status" -ne 0 ]; then
            printf '    FAIL: hardware not found in concerns after migration\n' >&2
            ok=1
        fi
        if [ $ok -eq 0 ] && [ "$py_out" != "found" ]; then
            printf '    FAIL: expected "found", got "%s"\n' "$py_out" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

test_ac10_hardware_cores_resolves_after_migration() {
    _setup_test_home
    local ok=0

    _seed_registry_no_hardware
    _run_concerns_migration "${ML_DIR}/registry.toml"

    local output status
    output="$(bash "$DETECT_HW" 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: detect-hardware failed after migration: %s\n' "$output" >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        local cores_val cores_status
        cores_val="$(machine-local get hardware.cores 2>&1)"; cores_status=$?
        if [ "$cores_status" -ne 0 ]; then
            printf '    FAIL: machine-local get hardware.cores failed (exit %d)\n' "$cores_status" >&2
            ok=1
        fi

        if [ $ok -eq 0 ]; then
            if ! [[ "$cores_val" =~ ^[1-9][0-9]*$ ]]; then
                printf '    FAIL: hardware.cores not a positive integer: "%s"\n' "$cores_val" >&2
                ok=1
            fi
        fi
    fi

    _teardown_test_home
    return $ok
}

# AC10 (multiline): migration preserves existing entries in a multiline concerns array.
# Regression guard for Finding 1 — the original regex lacked re.DOTALL and silently
# dropped pre-existing entries (project_rag, unreal) by inserting a duplicate key.
test_ac10_migration_multiline_preserves_existing() {
    _setup_test_home
    local ok=0

    # Seed registry.toml with a multiline concerns array (machine-local native format).
    cat > "${ML_DIR}/registry.toml" <<'EOF'
schema = 1
concerns = [
  "project_rag",
  "unreal",
]
EOF

    local mig_out mig_status
    mig_out="$(_run_concerns_migration "${ML_DIR}/registry.toml" 2>&1)"; mig_status=$?
    if [ "$mig_status" -ne 0 ]; then
        printf '    FAIL: migration failed on multiline array (exit %d): %s\n' "$mig_status" "$mig_out" >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        local py_out py_status
        py_out="$(python3 -c "
import tomllib, sys
with open('${ML_DIR}/registry.toml', 'rb') as f:
    data = tomllib.load(f)
concerns = data.get('concerns', [])
missing = [c for c in ['project_rag', 'unreal', 'hardware'] if c not in concerns]
if missing:
    print('MISSING: ' + ', '.join(missing))
    sys.exit(1)
print('ok: ' + str(concerns))
" 2>&1)"; py_status=$?
        if [ "$py_status" -ne 0 ]; then
            printf '    FAIL: post-migration parse: %s\n' "$py_out" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

test_ac10_migration_idempotent_no_duplicate() {
    _setup_test_home
    local ok=0

    _seed_registry_no_hardware
    _run_concerns_migration "${ML_DIR}/registry.toml"
    _run_concerns_migration "${ML_DIR}/registry.toml"

    local py_out py_status
    py_out="$(python3 -c "
import tomllib
with open('${ML_DIR}/registry.toml', 'rb') as f:
    data = tomllib.load(f)
concerns = data.get('concerns', [])
count = concerns.count('hardware')
print(count)
" 2>&1)"; py_status=$?

    if [ "$py_status" -ne 0 ]; then
        printf '    FAIL: python3 parse of registry.toml failed\n' >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        if ! [[ "$py_out" =~ ^[0-9]+$ ]]; then
            printf '    FAIL: count output not numeric: "%s"\n' "$py_out" >&2
            ok=1
        elif [ "$py_out" != "1" ]; then
            printf '    FAIL: hardware appears %s times in concerns (expected 1)\n' "$py_out" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

# ---------------------------------------------------------------------------
# AC11: non-Windows leg — hardware.local.toml IS written, proving the audit
#       runs BEFORE the non-Windows exit 0 guard in install-substrate.sh.
# ---------------------------------------------------------------------------

test_ac11_hardware_local_toml_written_nonwindows() {
    # Skip on Windows.
    if [[ "${OSTYPE:-}" == "msys" || "${OSTYPE:-}" == "cygwin" || "${OS:-}" == "Windows_NT" ]]; then
        echo "  SKIP: AC11 is for non-Windows only"
        return 0
    fi

    _setup_test_home
    local ok=0

    local output status
    output="$(bash "$DETECT_HW" 2>&1)"; status=$?
    if [ "$status" -ne 0 ]; then
        printf '    FAIL: detect-hardware failed: %s\n' "$output" >&2
        ok=1
    fi

    if [ $ok -eq 0 ] && [ ! -f "${ML_DIR}/hardware.local.toml" ]; then
        printf '    FAIL: hardware.local.toml not created\n' >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        if ! grep -q '\[hardware\]' "${ML_DIR}/hardware.local.toml"; then
            printf '    FAIL: hardware.local.toml does not contain [hardware] table\n' >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

test_ac11_cores_numeric_nonwindows() {
    # Skip on Windows.
    if [[ "${OSTYPE:-}" == "msys" || "${OSTYPE:-}" == "cygwin" || "${OS:-}" == "Windows_NT" ]]; then
        echo "  SKIP: AC11 is for non-Windows only"
        return 0
    fi

    _setup_test_home
    local ok=0

    bash "$DETECT_HW" >/dev/null 2>&1 || true

    local cores_val cores_status
    cores_val="$(machine-local get hardware.cores 2>&1)"; cores_status=$?
    if [ "$cores_status" -ne 0 ]; then
        printf '    FAIL: machine-local get hardware.cores failed (exit %d)\n' "$cores_status" >&2
        ok=1
    fi

    if [ $ok -eq 0 ]; then
        if ! [[ "$cores_val" =~ ^[1-9][0-9]*$ ]]; then
            printf '    FAIL: hardware.cores not a positive integer: "%s"\n' "$cores_val" >&2
            ok=1
        fi
    fi

    _teardown_test_home
    return $ok
}

# ---------------------------------------------------------------------------
# Verify required scripts exist before running tests
# ---------------------------------------------------------------------------

if [[ ! -f "$DETECT_HW" ]]; then
    echo "ERROR: detect-hardware.sh not found at ${DETECT_HW}" >&2
    exit 2
fi
if [[ ! -f "$ML_WRAPPER" ]]; then
    echo "ERROR: machine-local wrapper not found at ${ML_WRAPPER}" >&2
    exit 2
fi
if [[ ! -f "$ML_IMPL" ]]; then
    echo "ERROR: _machine_local.py not found at ${ML_IMPL}" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Run all 9 tests
# ---------------------------------------------------------------------------

run_test "AC4: detect-hardware.sh writes hardware.cores to hardware.local.toml" \
    test_ac4_writes_cores

run_test "AC4: detect-hardware.sh writes hardware.ram_gb to hardware.local.toml" \
    test_ac4_writes_ram_gb

run_test "AC4: detect-hardware.sh is idempotent — second run upserts without error" \
    test_ac4_idempotent

run_test "AC10: registry.toml without hardware concern gets hardware appended by migration step" \
    test_ac10_migration_appends_hardware_concern

run_test "AC10: after migration, hardware.cores resolves via machine-local get" \
    test_ac10_hardware_cores_resolves_after_migration

run_test "AC10: migration preserves existing entries in multiline concerns array (Finding 1 regression)" \
    test_ac10_migration_multiline_preserves_existing

run_test "AC10: migration is idempotent — running twice does not duplicate hardware in concerns" \
    test_ac10_migration_idempotent_no_duplicate

run_test "AC11: hardware.local.toml written on non-Windows (macOS/Linux) system" \
    test_ac11_hardware_local_toml_written_nonwindows

run_test "AC11: hardware.cores value is numeric (not empty) on non-Windows" \
    test_ac11_cores_numeric_nonwindows

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
