#!/usr/bin/env bash
# bin/tests/test-scaffold-canonical-structure.sh — Test harness for scaffold-canonical-structure.sh
#
# Purpose: verify idempotency, README creation, no .gitkeep, and no-clobber behaviour
# of scaffold-canonical-structure.sh.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 2
#
# Run: bash plugins/coordinator/bin/tests/test-scaffold-canonical-structure.sh
# (from any directory — script resolves its own location)
#
# Exit codes:
#   0  All cases PASS
#   1  One or more cases FAIL

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAFFOLD="${SCRIPT_DIR}/../scaffold-canonical-structure.sh"

if [[ ! -f "$SCAFFOLD" ]]; then
    echo "FATAL: scaffold-canonical-structure.sh not found at: $SCAFFOLD" >&2
    exit 1
fi

# Make executable if it isn't already (tolerated — Write tool doesn't set +x)
chmod +x "$SCAFFOLD" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TMPDIR_HARNESS="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_HARNESS"' EXIT

PASS=0
FAIL=0

pass() {
    echo "  PASS: $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "  FAIL: $1"
    FAIL=$((FAIL + 1))
}

# ---------------------------------------------------------------------------
# Setup: create a minimal tmp repo root for scaffolding into.
# We don't need a real git repo — we'll pass --root explicitly.
# ---------------------------------------------------------------------------

TMP_REPO="${TMPDIR_HARNESS}/test-repo"
mkdir -p "$TMP_REPO"

# ---------------------------------------------------------------------------
# Case 1 — First run: eager dirs + READMEs are created
# ---------------------------------------------------------------------------

echo "--- Case 1: first run creates eager dirs and READMEs"

run1_output="$("$SCAFFOLD" --root "$TMP_REPO" 2>&1)" || {
    fail "Case 1: scaffold exited non-zero; output: $run1_output"
}

# Verify cross-repo/inbox/ dir exists (eager directory entry in the current manifest)
if [[ -d "$TMP_REPO/cross-repo/inbox" ]]; then
    pass "Case 1a: cross-repo/inbox/ directory created"
else
    fail "Case 1a: cross-repo/inbox/ directory NOT created"
fi

# Verify cross-repo/inbox/README.md exists
if [[ -f "$TMP_REPO/cross-repo/inbox/README.md" ]]; then
    pass "Case 1b: cross-repo/inbox/README.md created"
else
    fail "Case 1b: cross-repo/inbox/README.md NOT created"
fi

# Verify README has non-empty content (not a blank stub)
readme_content="$(cat "$TMP_REPO/cross-repo/inbox/README.md" 2>/dev/null || echo '')"
if [[ -n "$readme_content" ]]; then
    pass "Case 1c: cross-repo/inbox/README.md has non-empty content"
else
    fail "Case 1c: cross-repo/inbox/README.md is empty"
fi

# Verify README contains expected purpose text
if echo "$readme_content" | grep -qi "cross-repo"; then
    pass "Case 1d: README mentions 'cross-repo' (purpose content present)"
else
    fail "Case 1d: README does not mention 'cross-repo' — purpose text missing"
fi

# Verify README contains the sending-directionality line (bleed + content regression guard)
if echo "$readme_content" | grep -q "deliver to the RECIPIENT"; then
    pass "Case 1e: README contains sending-directionality 'deliver to the RECIPIENT' line"
else
    fail "Case 1e: README missing 'deliver to the RECIPIENT' directionality line — content or bleed problem"
fi

# Verify README does NOT contain comment bleed from the next YAML entry
if echo "$readme_content" | grep -q "# CLAUDE.md"; then
    fail "Case 1f: README contains stray '# CLAUDE.md' comment — comment-bleed regression"
else
    pass "Case 1f: README does not contain '# CLAUDE.md' bleed (comment-bleed guard OK)"
fi

# Verify README is multi-line (line structure preserved, not flattened)
readme_line_count="$(echo "$readme_content" | wc -l | tr -d ' ')"
if [[ "$readme_line_count" -gt 5 ]]; then
    pass "Case 1g: README is multi-line ($readme_line_count lines) — structure preserved, not flattened"
else
    fail "Case 1g: README has only $readme_line_count line(s) — should be multi-line (flatten regression)"
fi

# ---------------------------------------------------------------------------
# Case 2 — No .gitkeep files produced
# ---------------------------------------------------------------------------

echo "--- Case 2: no .gitkeep files"

gitkeep_count="$(find "$TMP_REPO" -name ".gitkeep" 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$gitkeep_count" -eq 0 ]]; then
    pass "Case 2: no .gitkeep files found under repo root"
else
    fail "Case 2: found $gitkeep_count .gitkeep file(s) — scaffold must use READMEs, not .gitkeep"
fi

# ---------------------------------------------------------------------------
# Case 3 — Second run is a no-op (idempotency)
# ---------------------------------------------------------------------------

echo "--- Case 3: second run is idempotent"

# Capture the state of cross-repo/inbox/README.md before second run
readme_before="$(cat "$TMP_REPO/cross-repo/inbox/README.md")"

run2_output="$("$SCAFFOLD" --root "$TMP_REPO" 2>&1)" || {
    fail "Case 3: second scaffold run exited non-zero; output: $run2_output"
}

# README must not be modified
readme_after="$(cat "$TMP_REPO/cross-repo/inbox/README.md")"
if [[ "$readme_before" == "$readme_after" ]]; then
    pass "Case 3a: README.md unchanged after second run"
else
    fail "Case 3a: README.md was modified by second run (idempotency broken)"
fi

# code-review F14: Case 3a (README unchanged) is the load-bearing idempotency assertion.
# Case 3b is a secondary signal check — it passes even on empty output (silent is acceptable).
# Simplified comment to reflect that empty second-run output is also fine.
if echo "$run2_output" | grep -qi "skipped\|already-present\|skip"; then
    pass "Case 3b: second run reports skipped items"
else
    # Silent second run is acceptable (the idempotency guarantee is proven by Case 3a).
    # Only fail if the second run explicitly claims to have created already-present items.
    if echo "$run2_output" | grep -qi "created dir.*cross-repo/inbox\|created README.*cross-repo/inbox"; then
        fail "Case 3b: second run claimed to create already-present items"
    else
        pass "Case 3b: second run silent or non-claiming (Case 3a is the load-bearing idempotency check)"
    fi
fi

# ---------------------------------------------------------------------------
# Case 4 — Existing README is NOT overwritten (no-clobber)
# ---------------------------------------------------------------------------

echo "--- Case 4: existing README is not clobbered"

# Write a sentinel value into the README
SENTINEL="SENTINEL-DO-NOT-CLOBBER-$(date +%s)"
echo "$SENTINEL" > "$TMP_REPO/cross-repo/inbox/README.md"

"$SCAFFOLD" --root "$TMP_REPO" >/dev/null 2>&1 || {
    fail "Case 4: scaffold exited non-zero during no-clobber test"
}

readme_after_clobber="$(cat "$TMP_REPO/cross-repo/inbox/README.md")"
if echo "$readme_after_clobber" | grep -q "$SENTINEL"; then
    pass "Case 4: existing README preserved (not clobbered)"
else
    fail "Case 4: README was OVERWRITTEN — sentinel value missing"
fi

# ---------------------------------------------------------------------------
# Case 5 — --dry-run prints what would be created but creates nothing
# ---------------------------------------------------------------------------

echo "--- Case 5: --dry-run creates nothing"

TMP_DRYRUN="${TMPDIR_HARNESS}/dryrun-repo"
mkdir -p "$TMP_DRYRUN"

dryrun_output="$("$SCAFFOLD" --dry-run --root "$TMP_DRYRUN" 2>&1)" || {
    fail "Case 5: --dry-run exited non-zero; output: $dryrun_output"
}

# No dirs should have been created
dryrun_items="$(find "$TMP_DRYRUN" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$dryrun_items" -eq 0 ]]; then
    pass "Case 5a: --dry-run created no files or dirs"
else
    fail "Case 5a: --dry-run created $dryrun_items item(s) in repo (should create nothing)"
fi

# Dry-run output should mention "dry-run" and "would create"
if echo "$dryrun_output" | grep -qi "dry-run\|would create"; then
    pass "Case 5b: --dry-run output describes what would be created"
else
    fail "Case 5b: --dry-run output missing 'dry-run'/'would create' text; got: $dryrun_output"
fi

# ---------------------------------------------------------------------------
# Case 6 — Script uses its own manifest location, not the --root
# ---------------------------------------------------------------------------

echo "--- Case 6: manifest resolved relative to script location (not --root)"

# Create a fresh repo in a path that has no canonical-structure.yaml
TMP_ISOLATED="${TMPDIR_HARNESS}/isolated-repo"
mkdir -p "$TMP_ISOLATED"

"$SCAFFOLD" --root "$TMP_ISOLATED" >/dev/null 2>&1 || {
    fail "Case 6: scaffold failed when run with isolated --root"
}

# The manifest is in the coordinator's dir (SCRIPT_DIR/../canonical-structure.yaml).
# As long as it found eager entries and created cross-repo/inbox/ in the isolated root, we're good.
if [[ -d "$TMP_ISOLATED/cross-repo/inbox" ]]; then
    pass "Case 6: scaffold found manifest from its own location and created cross-repo/inbox/ in --root"
else
    fail "Case 6: cross-repo/inbox/ not created in isolated --root — manifest may not have been found"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================"
echo "  Total: $((PASS + FAIL))   Passed: $PASS   Failed: $FAIL"
echo "============================================"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
