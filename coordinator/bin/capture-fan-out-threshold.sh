#!/usr/bin/env bash
# bin/capture-fan-out-threshold.sh — Idempotent capture of the cores-scaled fan-out
# large-wave reminder threshold into the machine-local registry.
#
# Purpose: single source of the setup-time threshold capture so the guard is
# behaviorally testable (not an untestable markdown snippet). Called by
# coordinator:install Step 8; the value is read back by bin/fan-out-dispatch.sh
# (env LARGE_WAVE_THRESHOLD → machine-local get fan_out.large_wave_threshold → 16).
#
# Value = 3 × logical CPU count (floored at 1) — a speed-taper advisory threshold, NOT a
# cap: a CPU time-slices far more than (cores) tasks, so this marks where parallel returns
# may start tapering, not a ceiling. The genuinely load-bearing resource is memory commit
# (RAM/VRAM); the core-count proxy this helper writes is complemented at dispatch time by
# bin/probe-memory-headroom.sh, which reads live RAM/VRAM headroom (fan-out-dispatch.sh
# fires a "headroom tight" NOTE on a loaded machine regardless of wave size). The
# idempotency guard uses
# `machine-local keys` (registry layers ONLY) — NOT `machine-local has`, which
# consults the env layer and would skip the persistent write if the operator
# already has MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD exported (the clean-install
# hole the Staff Engineer F1/F7 flagged). Never clobbers an operator's manual registry value.
#
# Spec backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §C6
#
# Usage:
#   capture-fan-out-threshold.sh              # idempotent write
#   capture-fan-out-threshold.sh --check-only # print would-write status, no mutation
set -euo pipefail

KEY="fan_out.large_wave_threshold"

# Resolve Python via the canonical portable resolver (handles python3/python/py on Windows).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/resolve-python.sh
source "${SCRIPT_DIR}/../lib/resolve-python.sh"
if [[ -z "$PYTHON_BIN" ]]; then
    echo "WARN: capture-fan-out-threshold.sh: no Python on PATH; skipping threshold capture" >&2
    exit 0
fi

_compute_value() {
    local cores
    cores="$("$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c 'import os; print(max(1, os.cpu_count() or 1))')"
    echo "$(( 3 * cores ))"
}

CHECK_ONLY=0
case "${1:-}" in
    --check-only) CHECK_ONLY=1 ;;
    "")           ;;
    *) echo "usage: capture-fan-out-threshold.sh [--check-only]" >&2; exit 2 ;;
esac

# Registry-only idempotency guard. `machine-local keys` lists registry layers with no
# env merge, so an exported MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD does NOT suppress
# the persistent write. Short-circuits before computing/writing when already present.
#
# Capture the key list in its own step (not a `machine-local keys | grep` pipeline in `if`
# position): the `2>/dev/null || true` makes a missing/erroring `machine-local` — an OSS
# user partway through setup, or a CI runner without it on PATH — degrade to "key absent →
# write", instead of letting a pipeline failure abort the script under `set -euo pipefail`.
existing_keys="$(machine-local keys 2>/dev/null || true)"
if printf '%s\n' "$existing_keys" | grep -qx "$KEY"; then
    echo "fan_out_threshold: pre-existing"
    exit 0
fi

VALUE="$(_compute_value)"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "fan_out_threshold: would write (${VALUE})"
    exit 0
fi

machine-local set "$KEY" "$VALUE" >/dev/null
echo "fan_out_threshold: written (${VALUE})"
