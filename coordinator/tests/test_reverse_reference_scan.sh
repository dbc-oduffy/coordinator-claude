#!/usr/bin/env bash
# plugins/coordinator/tests/test_reverse_reference_scan.sh
#
# Verifies that no surviving in-tree references to the old holodeck-canonical
# contract-doc / schema paths exist as CANONICAL SOURCE assertions.
#
# As part of coord Phase B (G2b), the canonical home for:
#   - agent-install-contract.md was moved from holodeck to coord (2026-05-23)
#   - agent-install-manifest.schema.json is being established at coord (this plan)
#
# C6 performs the mechanical cleanup (holodeck-side trim, DR plan amendment,
# cross-repo memos to ue-addon + project-rag). This test verifies the in-scope
# deliverable: the four grep targets enumerated in plan §10 contain zero
# surviving canonical-source citations of the old holodeck-canonical paths.
#
# SCOPE PER PLAN §10 (AC10 binding):
#   Four sibling-repo trees scanned:
#     1. /x/claude-unreal-holodeck/   (full tree)
#     2. /x/project-rag-ue-addon/     (full tree)
#     3. /x/project-rag/              (full tree)
#     4. plugins/deep-research/  (in-tree DR plugin)
#
#   Exclusions (legitimate non-canonical mentions per plan §10):
#     - archive/ directories — historical record; not canonical-source assertions
#     - tasks/*/flight/ directories — per-chunk execution recorders; ephemeral
#     - DR Phase B plan body R2-fallback citation (legitimate at DR Phase B
#       authoring time; plan §8 amendment note documents the supersession)
#     - This plan's own body (describes old paths to explain what is being repointed)
#
# PATTERNS SEARCHED (canonical-source assertion indicators):
#   - claude-unreal-holodeck/docs/wiki/agent-install-contract.md
#   - claude-unreal-holodeck/docs/install/agent-install-manifest.schema.json
#
#   These are the specific path fragments that identify holodeck-canonical citations.
#   A mention in a "R2 fallback" or "this path is being superseded" context is
#   excluded via the targeted exclusion rules.
#
# Tests are intentionally RED until C6 lands the cleanup (holodeck trim + DR
# plan body amendment). That is the contract per plan §7 C5.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md
#                §6 AC10 + §10 (reverse-reference scan)
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#
# Cross-platform portability notes (DR-148, cross-platform-shell-portability.md):
#   - Requires bash >= 4; stock macOS /bin/bash is 3.2 (unsupported target).
#   - GNU-isms avoided: no grep -P.
#   - grep -r is BSD-portable (both macOS and Linux).
#   - Sibling-repo paths expected at /x/ prefix (Git-Bash Windows convention).
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

# The DR plugin lives in-tree relative to coordinator root:
# Review: code-reviewer F8 — DR scan is nested-layout-only (path surgery only works in the
# working-repo tree where plugins/coordinator-claude/{coordinator,deep-research} coexist).
# In the flat publish-repo layout, deep-research is absent; this scan is moot there —
# the test runs in-tree only and the DR scan silently skips if the directory doesn't exist.
DR_PLUGIN_ROOT="${COORDINATOR_ROOT%/coordinator}/deep-research"

# Sibling-repo trees (Windows Git-Bash /x/ mount convention)
HOLODECK_ROOT="/x/claude-unreal-holodeck"
UE_ADDON_ROOT="/x/project-rag-ue-addon"
PROJECT_RAG_ROOT="/x/project-rag"

# Patterns that identify holodeck-canonical-source citations (the old canonical paths)
PATTERN_CONTRACT_DOC="claude-unreal-holodeck/docs/wiki/agent-install-contract.md"
PATTERN_SCHEMA="claude-unreal-holodeck/docs/install/agent-install-manifest.schema.json"

PASS=0
FAIL=0
ERRORS=()
WARNINGS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    # Review: code-reviewer F3 — use printf so \n in msg renders as actual newline, not literal.
    printf 'FAIL: %s\n' "${msg}" >&2
}

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_warn() {
    local msg="$1"
    WARNINGS+=("WARN: ${msg}")
    echo "WARN: ${msg}"
}

# ---------------------------------------------------------------------------
# _scan_tree: grep a tree for canonical-source citations
#
# Args:
#   $1 — label for error messages
#   $2 — root path to scan
#   $3 — pattern to search
#   $4 — (optional) --exclude-dir values, space-separated
#
# Returns 0 (pass) if zero hits; sets _fail otherwise.
# Excludions:
#   - archive/ dirs (historical record)
#   - tasks/*/flight/ (ephemeral per-chunk sidecars)
#   - .git/ (not content)
#
# The R2-fallback exclusion for DR Phase B plan body is handled by excluding
# the specific plan file path containing the R2-fallback framing.
# ---------------------------------------------------------------------------
_scan_tree() {
    local label="$1"
    local root="$2"
    local pattern="$3"

    if [[ ! -d "${root}" ]]; then
        _warn "${label}: root directory not accessible at ${root}. Skipping (R4 — sibling-repo may not be present on this machine)."
        return 0
    fi

    local hits
    # Use grep -r with --include for text files; exclude archive/ and .git/ and tasks/
    # BSD grep (macOS) does not support --exclude-dir with wildcards as flexibly as GNU grep,
    # but --exclude-dir=<dir> with a literal name IS supported on both BSD and GNU.
    # We exclude: .git, archive, tasks
    # The DR Phase B plan body R2-fallback exclusion is handled by a secondary filter below.
    hits=$(
        grep -r --include="*.md" --include="*.json" --include="*.txt" --include="*.toml" \
             --include="*.sh" --include="*.ps1" --include="*.py" \
             --exclude-dir=".git" \
             --exclude-dir="archive" \
             --exclude-dir="tasks" \
             -l "${pattern}" "${root}" 2>/dev/null || true
    )

    if [[ -z "${hits}" ]]; then
        _pass "${label}: zero hits for '${pattern}' in ${root}"
        return 0
    fi

    # Secondary filter: exclude flight sidecar paths (tasks/*/flight/)
    # These were already excluded above via --exclude-dir=tasks, but handle
    # any that slip through alternate directory names.
    local filtered_hits=""
    while IFS= read -r hit_file; do
        # Skip DR Phase B plan body R2-fallback (legitimate non-canonical mention)
        # The R2-fallback appears in the plan body that explicitly says this is a
        # fallback path "pre-coord-Phase-B-ship" — excluded per plan §10.
        if echo "${hit_file}" | grep -qF "2026-06-15-deep-research-install-chain-application-phase-b.md"; then
            # Further check: only exclude if it actually contains R2-fallback framing
            # Review: code-reviewer F13 — drop bare "fallback" alternation; too broad (matches
            # any "fallback" anywhere). Tighten to named R2-fallback / holodeck-canonical forms only.
            if grep -q "R2.fallback\|holodeck-canonical fallback\|R2-fallback" "${hit_file}" 2>/dev/null; then
                _warn "${label}: DR Phase B plan body '${hit_file}' excluded (R2-fallback per plan §10). C6 should add amendment note."
                continue
            fi
        fi
        # Skip this plan's own body (describes old paths to explain repointing)
        if echo "${hit_file}" | grep -qF "2026-06-15-coordinator-install-chain-application-phase-b.md"; then
            continue
        fi
        # Skip cross-repo memos that ARE the repointing mechanism (the ASK body cites old paths
        # so the recipient knows what to repoint — that is the memo's purpose, not a canonical-source assertion)
        # Review: code-reviewer F7 — add leading / anchor to match path boundary precisely.
        if echo "${hit_file}" | grep -qE "/cross-repo/(inbox|outbox)/.*-contract-doc-canonical-repoint"; then
            continue
        fi
        # Skip DoE decision archive-class memos under cross-repo/ (historical paper trail,
        # not canonical-source assertions)
        if echo "${hit_file}" | grep -qE "cross-repo/.*-doe-decision-"; then
            continue
        fi
        filtered_hits="${filtered_hits}${hit_file}"$'\n'
    done <<< "${hits}"

    filtered_hits="${filtered_hits%$'\n'}"  # strip trailing newline

    if [[ -z "${filtered_hits}" ]]; then
        _pass "${label}: zero hits for '${pattern}' after exclusions in ${root}"
    else
        local hit_count
        hit_count=$(echo "${filtered_hits}" | wc -l | tr -d ' ')
        _fail "${label}: ${hit_count} file(s) still reference '${pattern}' as canonical source in ${root}. C6 must repoint these. Files:\n${filtered_hits}"
    fi
}

# ---------------------------------------------------------------------------
# Scan 1: Holodeck tree
#
# After C6 trims the holodeck-side residual to a pure forwarder, the holodeck
# tree should contain no canonical-source assertions of the old paths.
# The forwarder itself (docs/wiki/agent-install-contract.md) will still
# reference the old path in its "moved to" redirect — that is a FORWARDER,
# not a canonical-source assertion. We exclude it below.
# ---------------------------------------------------------------------------
echo "=== Scan 1: Holodeck tree (${HOLODECK_ROOT}) ==="

if [[ -d "${HOLODECK_ROOT}" ]]; then
    # Special handling for holodeck: the forwarder doc itself references the old path
    # in its redirect text ("this file moved from X to Y") — that is legitimate.
    # We scan the full tree but exclude the forwarder file itself.
    HOLODECK_FORWARDER="${HOLODECK_ROOT}/docs/wiki/agent-install-contract.md"

    for pattern in "${PATTERN_CONTRACT_DOC}" "${PATTERN_SCHEMA}"; do
        hits=$(
            grep -r --include="*.md" --include="*.json" --include="*.txt" --include="*.toml" \
                 --include="*.sh" --include="*.ps1" --include="*.py" \
                 --exclude-dir=".git" \
                 --exclude-dir="archive" \
                 --exclude-dir="tasks" \
                 -l "${pattern}" "${HOLODECK_ROOT}" 2>/dev/null || true
        )

        if [[ -z "${hits}" ]]; then
            _pass "holodeck/${pattern##*/}: zero hits for '${pattern}'"
            continue
        fi

        # Filter: exclude the forwarder doc itself (redirect text is legitimate)
        # and this plan's body
        filtered_hits=""
        while IFS= read -r hit_file; do
            if [[ "${hit_file}" == "${HOLODECK_FORWARDER}" ]]; then
                # It's the forwarder — check it is actually a forwarder (≤10 lines, per AC9)
                line_count=$(wc -l < "${hit_file}" 2>/dev/null || echo "999")
                if [[ "${line_count}" -le 10 ]]; then
                    _warn "holodeck forwarder ${hit_file} (${line_count} lines ≤10): treated as legitimate redirect, not canonical-source assertion."
                    continue
                else
                    _fail "holodeck forwarder ${hit_file} has ${line_count} lines (expected ≤10 per AC9). C6 must trim to pure forwarder."
                    continue
                fi
            fi
            if echo "${hit_file}" | grep -qF "2026-06-15-coordinator-install-chain-application-phase-b.md"; then
                continue  # This plan's own body
            fi
            # Skip DoE decision archive-class memos under cross-repo/ (historical paper trail,
            # not canonical-source assertions — 2026-05-23 migration-ownership decision)
            if echo "${hit_file}" | grep -qE "cross-repo/.*-doe-decision-"; then
                continue
            fi
            filtered_hits="${filtered_hits}${hit_file}"$'\n'
        done <<< "${hits}"

        filtered_hits="${filtered_hits%$'\n'}"

        if [[ -z "${filtered_hits}" ]]; then
            _pass "holodeck/${pattern##*/}: zero hits after forwarder exclusion for '${pattern}'"
        else
            hit_count=$(echo "${filtered_hits}" | wc -l | tr -d ' ')
            _fail "holodeck/${pattern##*/}: ${hit_count} file(s) still reference '${pattern}' as canonical source. C6 must repoint. Files: ${filtered_hits}"
        fi
    done
else
    _warn "Holodeck tree not accessible at ${HOLODECK_ROOT} — skipping (R4: sibling-repo may not be present on this machine)."
fi

# ---------------------------------------------------------------------------
# Scan 2: ue-addon tree
# ---------------------------------------------------------------------------
echo ""
echo "=== Scan 2: UE-addon tree (${UE_ADDON_ROOT}) ==="
_scan_tree "ue-addon/contract-doc" "${UE_ADDON_ROOT}" "${PATTERN_CONTRACT_DOC}"
_scan_tree "ue-addon/schema" "${UE_ADDON_ROOT}" "${PATTERN_SCHEMA}"

# ---------------------------------------------------------------------------
# Scan 3: project-rag tree
# ---------------------------------------------------------------------------
echo ""
echo "=== Scan 3: project-rag tree (${PROJECT_RAG_ROOT}) ==="
_scan_tree "project-rag/contract-doc" "${PROJECT_RAG_ROOT}" "${PATTERN_CONTRACT_DOC}"
_scan_tree "project-rag/schema" "${PROJECT_RAG_ROOT}" "${PATTERN_SCHEMA}"

# ---------------------------------------------------------------------------
# Scan 4: DR plugin (in-tree)
#
# The DR Phase B plan body contains an R2-fallback citation that was legitimate
# at authoring time (pre-coord-Phase-B-ship). C6 adds an amendment note to that
# plan body. The _scan_tree helper excludes the DR Phase B plan body when it
# contains R2-fallback framing.
# ---------------------------------------------------------------------------
echo ""
echo "=== Scan 4: DR plugin in-tree (${DR_PLUGIN_ROOT}) ==="
if [[ -d "${DR_PLUGIN_ROOT}" ]]; then
    _scan_tree "deep-research/contract-doc" "${DR_PLUGIN_ROOT}" "${PATTERN_CONTRACT_DOC}"
    _scan_tree "deep-research/schema" "${DR_PLUGIN_ROOT}" "${PATTERN_SCHEMA}"
else
    _warn "DR plugin root not accessible at ${DR_PLUGIN_ROOT} — skipping."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}  WARN: ${#WARNINGS[@]}"
if [[ "${#WARNINGS[@]}" -gt 0 ]]; then
    echo ""
    echo "Warnings (non-fatal):"
    for w in "${WARNINGS[@]}"; do
        echo "  ${w}"
    done
fi
if [[ "${FAIL}" -gt 0 ]]; then
    echo "" >&2
    echo "Failed assertions:" >&2
    for err in "${ERRORS[@]}"; do
        echo "  ${err}" >&2
    done
    exit 1
fi
exit 0
