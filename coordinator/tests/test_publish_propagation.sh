#!/usr/bin/env bash
# plugins/coordinator/tests/test_publish_propagation.sh
#
# Verifies that publish.sh coordinator-claude propagates the schema mirror
# (docs/install/agent-install-manifest.schema.json) to the publish-repo
# at a byte-identical path.
#
# AC13 binding: "Dry-run publish.sh coordinator-claude propagates the schema
# mirror to <publish-repo>/docs/install/agent-install-manifest.schema.json
# byte-identically."
#
# SUBSTRATE-DRIFT REPORT (per plan §7 C5 guidance):
# ----------------------------------------------------------------------
# This test was authored per plan §7 C5: "If publish.sh does NOT natively
# propagate docs/install/, write the test to BLOCK with substrate-drift
# report rather than silently shimming — do NOT add propagation rules."
#
# ANALYSIS (2026-06-15, C5 executor):
# The 'coordinator-claude' target in publish-targets.sh is:
#   "coordinator-claude|mirror|$HOME/.claude/plugins/coordinator-claude|/x/coordinator-claude/plugins"
#
# Mode: mirror
# Source: $HOME/.claude/plugins/coordinator-claude
# Target: /x/coordinator-claude/plugins
#
# publish_sync.py mirror mode copies plugin subdirectories from source to target.
# The coordinator plugin subdir is 'coordinator', so:
#   Source: ~/.claude/plugins/coordinator/docs/install/
#   Target: /x/coordinator-claude/plugins/coordinator/docs/install/
#
# This produces a NESTED path under /x/coordinator-claude/plugins/coordinator/,
# NOT the flat canonical publish-repo path /x/coordinator-claude/docs/install/.
#
# AC13 calls for <publish-repo>/docs/install/agent-install-manifest.schema.json
# which is /x/coordinator-claude/docs/install/agent-install-manifest.schema.json.
#
# The existing 'coordinator-claude-publish-repo-docs' target covers flat-mirror
# of coordinator/dist/publish-repo-docs → /x/coordinator-claude/docs, but:
#   1. That target covers dist/publish-repo-docs/, not coordinator/docs/install/
#   2. No target explicitly propagates coordinator/docs/install/ to /x/coordinator-claude/docs/install/
#
# CONCLUSION: publish.sh coordinator-claude does NOT natively propagate
# docs/install/ to the flat <publish-repo>/docs/install/ path.
#
# Per plan §7 C5 guidance: this test BLOCKS with a substrate-drift report
# rather than silently shimming. A separate plan is required to add proper
# propagation rules to publish.sh or to the coordinator-claude-publish-repo-docs
# target configuration.
#
# To resolve: author a plan that:
#   1. Adds a coordinator-claude-install-surface target to publish-targets.sh
#      covering coordinator/docs/install/ → /x/coordinator-claude/docs/install/
#   OR
#   2. Extends the coordinator-claude-publish-repo-docs target to include the
#      install surface files from coordinator/docs/install/
#   THEN re-run this test to verify byte-identical propagation.
# ----------------------------------------------------------------------
#
# WHAT THIS TEST DOES (under BLOCK conditions):
#   1. Detects whether the publish-repo target path (/x/coordinator-claude/docs/install/)
#      exists and contains the schema mirror.
#   2. If the flat target path does NOT exist: reports SUBSTRATE-DRIFT and exits 1.
#   3. If the flat target path DOES exist (i.e., the drift was resolved by a separate
#      plan): verifies byte-identical content vs. the source schema mirror and
#      reports PASS or FAIL accordingly.
#
# This design means the test can serve as the green-gate verification once the
# publish.sh propagation substrate drift is resolved — it doesn't need to be
# rewritten, only re-run.
#
# Tests are intentionally RED (BLOCK-mode) until the publish.sh propagation
# substrate is fixed by a separate plan. That is the contract per plan §7 C5.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md
#                §6 AC13 + §7 C5 (publish substrate verification guidance)
# Spec backlink: setup/publish.sh (coordinator-claude mirror target)
# Spec backlink: setup/publish-targets.sh (target registry)
#
# Cross-platform portability notes (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4.
#   - GNU-isms avoided: no grep -P, no diff --color.
#   - cmp is BSD-portable for byte-by-byte file comparison.
#   - Runs on Git-Bash (Windows) as well as POSIX.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (DR-148)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required. Stock macOS /bin/bash is 3.2 (unsupported)." >&2
    echo "Remediation: brew install bash && ensure /usr/local/bin/bash appears first in PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and working-repo root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source schema mirror (the coord-canonical path, authored by C1)
SOURCE_SCHEMA="${COORDINATOR_ROOT}/docs/install/agent-install-manifest.schema.json"

# Publish-repo target path (AC13: <publish-repo>/docs/install/)
# The publish-repo for coordinator-claude is /x/coordinator-claude
PUBLISH_REPO="/x/coordinator-claude"
TARGET_SCHEMA="${PUBLISH_REPO}/docs/install/agent-install-manifest.schema.json"

# Mirror target path (what publish.sh coordinator-claude ACTUALLY produces)
# This is the nested path under /x/coordinator-claude/plugins/coordinator/
MIRROR_TARGET_SCHEMA="${PUBLISH_REPO}/plugins/coordinator/docs/install/agent-install-manifest.schema.json"

PASS=0
FAIL=0
WARN=0
ERRORS=()
WARNINGS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_warn() {
    local msg="$1"
    WARN=$(( WARN + 1 ))
    WARNINGS+=("WARN: ${msg}")
    echo "WARN: ${msg}" >&2
}

# ---------------------------------------------------------------------------
# Step 1: Verify source schema mirror exists (C1 must have landed)
# ---------------------------------------------------------------------------
echo "=== Step 1: Source schema mirror exists ==="

if [[ ! -f "${SOURCE_SCHEMA}" ]]; then
    _fail "Source schema mirror not found at ${SOURCE_SCHEMA}. C1 must land before this test can run."
    echo ""
    echo "=== Summary ==="
    echo "PASS: ${PASS}  FAIL: ${FAIL}"
    exit 1
fi
_pass "Source schema mirror exists at ${SOURCE_SCHEMA}"

# ---------------------------------------------------------------------------
# Step 2: Verify publish-repo flat target path (AC13 canonical path)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Publish-repo flat target path (AC13 canonical) ==="
echo "  AC13 target:  ${TARGET_SCHEMA}"
echo "  Mirror target: ${MIRROR_TARGET_SCHEMA}"
echo ""

if [[ ! -d "${PUBLISH_REPO}" ]]; then
    echo "SUBSTRATE-DRIFT: publish-repo not accessible at ${PUBLISH_REPO}." >&2
    echo "" >&2
    echo "  This machine may not have the coordinator-claude publish-repo cloned." >&2
    echo "  Skipping byte-identity check (cannot verify AC13 without the publish-repo)." >&2
    echo "" >&2
    echo "BLOCK: AC13 cannot be verified — publish-repo not present at ${PUBLISH_REPO}." >&2
    echo "  To resolve: clone the coordinator-claude publish-repo to /x/coordinator-claude" >&2
    echo "  and re-run this test." >&2
    exit 1
fi

if [[ ! -f "${TARGET_SCHEMA}" ]]; then
    echo "SUBSTRATE-DRIFT REPORT:" >&2
    echo "" >&2
    echo "  publish.sh coordinator-claude does NOT natively propagate docs/install/" >&2
    echo "  to the flat canonical publish-repo path." >&2
    echo "" >&2
    echo "  AC13 expected: ${TARGET_SCHEMA}" >&2
    echo "  NOT FOUND. This path does not exist in the publish-repo." >&2
    echo "" >&2
    echo "  Mirror target (what publish.sh actually produces):" >&2
    echo "    ${MIRROR_TARGET_SCHEMA}" >&2
    if [[ -f "${MIRROR_TARGET_SCHEMA}" ]]; then
        echo "    EXISTS (nested layout — not the AC13 flat target)." >&2
    else
        echo "    NOT FOUND (publish.sh may not have been run, or coordinator target is misconfigured)." >&2
    fi
    echo "" >&2
    echo "  Root cause (publish-targets.sh coordinator-claude entry):" >&2
    echo "    'coordinator-claude|mirror|\$HOME/.claude/plugins/coordinator-claude|/x/coordinator-claude/plugins'" >&2
    echo "    Mode 'mirror' copies ~/.claude/plugins/coordinator-claude/ → /x/coordinator-claude/plugins/" >&2
    echo "    coordinator plugin subdir lands at /x/coordinator-claude/plugins/coordinator/ (nested)." >&2
    echo "    No target maps coordinator/docs/install/ to /x/coordinator-claude/docs/install/ (flat)." >&2
    echo "" >&2
    echo "  Required fix (out-of-scope for this plan — separate plan required per plan §7 C5):" >&2
    echo "    Option A: Add a 'coordinator-claude-install-surface' target to publish-targets.sh" >&2
    echo "              (flat-mirror coordinator/docs/install/ → /x/coordinator-claude/docs/install/)." >&2
    echo "    Option B: Extend 'coordinator-claude-publish-repo-docs' target to include" >&2
    echo "              coordinator/docs/install/ files." >&2
    echo "    Then re-run this test to verify byte-identical propagation." >&2
    echo "" >&2
    _fail "AC13: publish.sh coordinator-claude does not propagate schema to flat publish-repo path. SUBSTRATE-DRIFT — separate plan required."
    echo ""
    echo "=== Summary ==="
    echo "PASS: ${PASS}  FAIL: ${FAIL}"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Byte-identical comparison (only reached if flat target exists)
#
# This step runs when the publish.sh substrate drift has been resolved by
# a separate plan. Verifies byte-for-byte identity between source and target.
# ---------------------------------------------------------------------------
echo "=== Step 3: Byte-identical comparison ==="
echo "  Source: ${SOURCE_SCHEMA}"
echo "  Target: ${TARGET_SCHEMA}"

if cmp -s "${SOURCE_SCHEMA}" "${TARGET_SCHEMA}"; then
    _pass "Byte-identical: schema mirror matches publish-repo target byte-for-byte"
else
    # Review: code-reviewer F2 — concatenate into single $1; _fail only reads $1.
    _fail "Byte-mismatch: schema mirror content differs between source and publish-repo target. Run 'publish.sh coordinator-claude' (or equivalent) to sync."
fi

# ---------------------------------------------------------------------------
# Step 4: Verify mirror-target path also byte-matches (nested layout check)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: Mirror-target path check (nested layout) ==="

if [[ -f "${MIRROR_TARGET_SCHEMA}" ]]; then
    if cmp -s "${SOURCE_SCHEMA}" "${MIRROR_TARGET_SCHEMA}"; then
        _pass "Mirror-target byte-identical: nested-layout schema matches source"
    else
        # Review: code-reviewer F2 — concatenate into single $1; _fail only reads $1.
        _fail "Mirror-target byte-mismatch: nested-layout schema differs from source. Run 'publish.sh coordinator-claude' to resync."
    fi
else
    # AC13 binds flat-target byte-identity (Steps 1-3); nested mirror is a defensive
    # secondary check that fires only when the `coordinator-claude` mirror target has
    # also been run since the install surface edit. Concurrent-EM dirty trees commonly
    # block the mirror target's publish (refuses on uncommitted siblings), so a nested-
    # absent state is expected operationally. Demoted to WARN 2026-06-15 (coord Phase B
    # follow-on closing — AC13 GREEN on Steps 1-3).
    _warn "Flat target passed Step 3; nested-layout mirror not found at ${MIRROR_TARGET_SCHEMA}. Run 'bash setup/publish.sh coordinator-claude' (may require COORDINATOR_OVERRIDE_DIRTY_TREE=1 on a shared branch) to also sync the nested mirror. Not an AC13 binding failure."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
    echo "" >&2
    echo "Failed assertions:" >&2
    for err in "${ERRORS[@]}"; do
        echo "  ${err}" >&2
    done
    exit 1
fi
exit 0
