#!/usr/bin/env bash
# verify-prereq-probe-sync.sh — Byte-identity check/fix for the vendored coordinator prereq unit.
#
# The deep-research installer vendors three files from the coordinator SSOT source tree so
# deep-research's install path has no runtime dependency on coordinator being present on disk.
# This script enforces the FAITHFULNESS leg of that contract: every vendored file must be a
# byte-for-byte copy of its SSOT source.
#
# FRESHNESS leg is deliberately advisory (not a hard gate) because coordinator is
# source_is_live — its files update in place under ~/.claude without a publish step, so a
# "stale" vendor copy is normal during active coordinator development. Run this verifier after
# deliberate vendor refreshes, not as a CI gate. See plan C5 / prior-art CR-1 for rationale.
#
# Usage:
#   verify-prereq-probe-sync.sh          Diff each vendored file against its SSOT source;
#                                         exit 0 if all three byte-identical; exit non-zero
#                                         (printing which file drifted) on any mismatch.
#   verify-prereq-probe-sync.sh --fix    Re-copy SSOT → vendor for any drifted file
#                                         (one-way, outward from SSOT only; vendor→SSOT is
#                                         never correct). Then re-verifies.
#
# The three-file vendored unit:
#   prereq_probe.sh      ↔  coordinator/scripts/lib/prereq_probe.sh
#   step_zero_emit.sh    ↔  coordinator/scripts/lib/step_zero_emit.sh
#   manifest_reader.sh   ↔  coordinator/scripts/lib/manifest_reader.sh
#
# Spec backlink: docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md § C5

set -euo pipefail

# Bash ≥ 4 is required (coordinator:install ensures brew bash is in PATH on macOS).
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
    echo "ERROR: bash ≥ 4 required (found ${BASH_VERSION}). Install via: brew install bash" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Resolve repo root: git-toplevel walk, with a fallback to marker discovery.
# This script lives at plugins/deep-research/bin/ inside the
# meta-repo, so SCRIPT_DIR/../../../.. lands at the repo root when invoked from
# any cwd — but git rev-parse is the robust approach.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "$0")"

if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
else
    # Fallback: walk up from script dir looking for the .claude marker file.
    _dir="$SCRIPT_DIR"
    REPO_ROOT=""
    while [ "$_dir" != "/" ]; do
        if [ -f "$_dir/CLAUDE.md" ] || [ -f "$_dir/.git/config" ]; then
            REPO_ROOT="$_dir"
            break
        fi
        _dir="$(dirname "$_dir")"
    done
    if [ -z "$REPO_ROOT" ]; then
        echo "ERROR: could not resolve repo root from $SCRIPT_DIR" >&2
        exit 1
    fi
fi

SSOT_DIR="$REPO_ROOT/plugins/coordinator/scripts/lib"
VENDOR_DIR="$REPO_ROOT/plugins/deep-research/scripts/lib/coordinator_prereq"

MODE="${1:-verify}"

FILES=(
    "prereq_probe.sh"
    "step_zero_emit.sh"
    "manifest_reader.sh"
)

EXIT_CODE=0
ANY_CHECKED=0

for fname in "${FILES[@]}"; do
    ssot_path="$SSOT_DIR/$fname"
    vendor_path="$VENDOR_DIR/$fname"

    ssot_exists=0
    vendor_exists=0
    [ -f "$ssot_path" ]   && ssot_exists=1
    [ -f "$vendor_path" ] && vendor_exists=1

    if [ "$ssot_exists" -eq 0 ] && [ "$vendor_exists" -eq 0 ]; then
        echo "NOT_PRESENT  $fname (neither SSOT source nor vendor copy exists yet)"
        continue
    fi

    if [ "$ssot_exists" -eq 0 ]; then
        echo "SSOT_MISSING $fname (vendor copy present but SSOT source absent at $ssot_path)"
        EXIT_CODE=1
        continue
    fi

    if [ "$vendor_exists" -eq 0 ]; then
        if [ "$MODE" = "--fix" ]; then
            mkdir -p "$VENDOR_DIR"
            cp "$ssot_path" "$vendor_path"
            echo "COPIED       $fname → coordinator_prereq/$fname"
            ANY_CHECKED=1
        else
            echo "VENDOR_MISSING $fname (SSOT exists but vendor copy absent at $vendor_path)"
            EXIT_CODE=1
        fi
        continue
    fi

    ANY_CHECKED=1

    if diff -q "$ssot_path" "$vendor_path" >/dev/null 2>&1; then
        echo "OK           $fname"
    else
        if [ "$MODE" = "--fix" ]; then
            cp "$ssot_path" "$vendor_path"
            echo "FIXED        $fname → coordinator_prereq/$fname"
        else
            echo "MISMATCH     $fname"
            EXIT_CODE=1
        fi
    fi
done

if [ "$ANY_CHECKED" -eq 0 ] && [ "$EXIT_CODE" -eq 0 ]; then
    echo "no files present on either side — nothing to verify"
fi

if [ "$MODE" = "--fix" ] && [ "$EXIT_CODE" -eq 0 ]; then
    # Re-verify after fix to confirm byte-identity.
    echo "--- re-verifying after fix ---"
    exec "$SCRIPT_PATH"
fi

exit $EXIT_CODE
