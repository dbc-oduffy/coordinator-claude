#!/usr/bin/env bash
# bin/capture-fan-out-threshold.test.sh — AC7 coverage for capture-fan-out-threshold.sh.
#
# Proves the setup-time threshold capture is idempotent AND that the registry-only guard
# writes even when an ambient MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD env var is exported
# (the Staff Engineer F1/F7: `machine-local has` would have skipped the persistent write — the clean-install
# hole). Hermetic via MACHINE_LOCAL_REGISTRY_DIR — never touches the real registry.
#
# Spec backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §C6, ACs 7/8.
# Intentionally `set -uo pipefail` WITHOUT `-e`: each case captures `$?` manually and the
# harness must continue-on-failure to run all assertions. (The production script under test
# uses the full `set -euo pipefail`.)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURE="${SCRIPT_DIR}/capture-fan-out-threshold.sh"
KEY="fan_out.large_wave_threshold"

PASS=0
FAIL=0
TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Expected value the script computes: 3 × max(1, cpu_count).
EXPECTED_VALUE="$(( 3 * $(python3 -c 'import os; print(max(1, os.cpu_count() or 1))') ))"

_ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_bad() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL + 1)); }

# Each case runs in a fresh temp registry dir so they cannot bleed into each other.
_fresh_reg() { local d; d="$(mktemp -d "${TMPROOT}/reg.XXXXXX")"; echo "$d"; }

echo "=== Test A: key absent → script writes 3×cores ==="
REG="$(_fresh_reg)"
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" bash "$CAPTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "A0: exit zero" || _bad "A0: exit zero" "rc=$RC"
[[ "$OUT" == *"written (${EXPECTED_VALUE})"* ]] && _ok "A1: reports written(${EXPECTED_VALUE})" || _bad "A1: written" "out=$OUT"
GOT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local get "$KEY" 2>/dev/null)"
[[ "$GOT" == "$EXPECTED_VALUE" ]] && _ok "A2: registry value == 3×cores" || _bad "A2: registry value" "got=$GOT want=$EXPECTED_VALUE"

echo "=== Test B: key present → no clobber (idempotent re-run) ==="
REG="$(_fresh_reg)"
MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local set "$KEY" 99 >/dev/null
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" bash "$CAPTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "B0: exit zero" || _bad "B0: exit zero" "rc=$RC"
[[ "$OUT" == *"pre-existing"* ]] && _ok "B1: reports pre-existing" || _bad "B1: pre-existing" "out=$OUT"
GOT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local get "$KEY" 2>/dev/null)"
[[ "$GOT" == "99" ]] && _ok "B2: operator value 99 NOT clobbered" || _bad "B2: no clobber" "got=$GOT want=99"

echo "=== Test C (F7): ambient env var exported, key absent → STILL writes registry ==="
REG="$(_fresh_reg)"
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD=777 bash "$CAPTURE" 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "C0: exit zero" || _bad "C0: exit zero" "rc=$RC"
[[ "$OUT" == *"written (${EXPECTED_VALUE})"* ]] && _ok "C1: env export did NOT suppress the write" || _bad "C1: write despite env" "out=$OUT"
# Read back WITHOUT the env var so we see the persisted registry layer, not the env escape hatch.
GOT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local keys | grep -cx "$KEY")"
[[ "$GOT" == "1" ]] && _ok "C2: registry layer now carries the key (not just env)" || _bad "C2: registry persisted" "keys-count=$GOT"

echo "=== Test D: --check-only on absent key → would write, NO mutation ==="
REG="$(_fresh_reg)"
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" bash "$CAPTURE" --check-only 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "D0: exit zero" || _bad "D0: exit zero" "rc=$RC"
[[ "$OUT" == *"would write (${EXPECTED_VALUE})"* ]] && _ok "D1: reports would write(${EXPECTED_VALUE})" || _bad "D1: would write" "out=$OUT"
GOT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local keys | grep -cx "$KEY")"
[[ "$GOT" == "0" ]] && _ok "D2: --check-only did NOT mutate the registry" || _bad "D2: no mutation" "keys-count=$GOT"

echo "=== Test E: --check-only on present key → pre-existing ==="
REG="$(_fresh_reg)"
MACHINE_LOCAL_REGISTRY_DIR="$REG" machine-local set "$KEY" 42 >/dev/null
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" bash "$CAPTURE" --check-only 2>&1)"; RC=$?
[[ "$RC" -eq 0 ]] && _ok "E0: exit zero" || _bad "E0: exit zero" "rc=$RC"
[[ "$OUT" == *"pre-existing"* ]] && _ok "E1: reports pre-existing" || _bad "E1: pre-existing" "out=$OUT"

echo "=== Test F: bad flag → usage error, exit 2 ==="
REG="$(_fresh_reg)"
OUT="$(MACHINE_LOCAL_REGISTRY_DIR="$REG" bash "$CAPTURE" --bogus 2>&1)"; RC=$?
[[ "$RC" -eq 2 ]] && _ok "F1: bad flag → exit 2" || _bad "F1: bad flag exit" "rc=$RC"

echo ""
echo "========================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "========================================"
[[ "$FAIL" -eq 0 ]]
