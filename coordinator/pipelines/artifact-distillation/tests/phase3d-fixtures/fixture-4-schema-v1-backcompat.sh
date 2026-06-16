#!/usr/bin/env bash
# fixture-4-schema-v1-backcompat.sh — AC15 backward-compatibility test.
#
# spec-backlink: docs/plans/2026-06-14-distill-phase3d-output-budget.md § C4, AC15
# contract-source: PIPELINE.md § Phase 5 step 5
#
# PURPOSE: Asserts that the Phase 5 expansion consumer (simulated by
# lib/expand-phase3d-manifest.sh) successfully parses a schema_version: 1 Phase 3d
# manifest (flat deletions: only, no deletion_groups: key) without error.
#
# AC15 requirement:
#   "Schema_version: 1 manifests (no deletion_groups: key) are consumed as flat
#    deletions:-only without error — backward-compat invariant."
#   — PIPELINE.md § Phase 5 step 5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FIXTURE_DIR="$SCRIPT_DIR/fixture-4"
MANIFEST="$FIXTURE_DIR/input/phase3d-deletion-manifest.md"
GOLDEN="$FIXTURE_DIR/golden/expected-delete-set.txt"
EXPAND="$SCRIPT_DIR/lib/expand-phase3d-manifest.sh"

fail=0

echo "=== fixture-4: schema_version: 1 backward-compat ==="

# Prerequisite: required files exist
for f in "$MANIFEST" "$GOLDEN" "$EXPAND"; do
    if [ -f "$f" ]; then
        echo "OK     found: $(basename "$f")"
    else
        echo "FAIL   missing: $f"
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    echo "FAIL — missing prerequisite files"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    # Review: code-reviewer F11 — exit 2 signals SKIP to the parent runner (exit 0
    # was previously counted as PASS, masking the missing python3 prerequisite).
    echo "SKIP: python3 not available; cannot exercise expansion"
    exit 2
fi

# Run expand — must succeed (exit 0) for schema_version: 1
TMP_OUT="$(mktemp -t fixture4-expand-XXXXXX.txt)"
TMP_ERR="$(mktemp -t fixture4-err-XXXXXX.txt)"
trap 'rm -f "$TMP_OUT" "$TMP_ERR"' EXIT

if bash "$EXPAND" "$MANIFEST" "$FIXTURE_DIR/input" > "$TMP_OUT" 2> "$TMP_ERR"; then
    echo "OK     expand-phase3d-manifest.sh exited 0 (no error on schema_version: 1)"
else
    echo "FAIL   expand-phase3d-manifest.sh exited non-zero for schema_version: 1 manifest"
    echo "       stderr: $(cat "$TMP_ERR")"
    exit 1
fi

# Verify stderr is empty (no warnings about unsupported schema)
if [ -s "$TMP_ERR" ]; then
    stderr_content="$(cat "$TMP_ERR")"
    # Warn-level non-.md exclusions are acceptable; ERROR is not
    if echo "$stderr_content" | grep -q "^ERROR:"; then
        echo "FAIL   unexpected ERROR in stderr: $stderr_content"
        fail=1
    else
        echo "OK     stderr contains only WARN lines (non-.md exclusions) — acceptable"
    fi
else
    echo "OK     stderr empty"
fi

# Compare expanded output against golden
if diff -u "$GOLDEN" "$TMP_OUT" > /dev/null 2>&1; then
    echo "OK     expanded delete set matches golden ($(wc -l < "$GOLDEN" | awk '{print $1}') lines)"
else
    echo "FAIL   expanded delete set differs from golden"
    echo "       --- golden"
    echo "       +++ actual"
    diff -u "$GOLDEN" "$TMP_OUT" || true
    fail=1
fi

echo ""
if [ "$fail" -eq 0 ]; then
    echo "PASS — AC15: schema_version: 1 backward-compat invariant holds"
    exit 0
else
    echo "FAIL — AC15: schema_version: 1 backward-compat broken — see errors above"
    exit 1
fi
