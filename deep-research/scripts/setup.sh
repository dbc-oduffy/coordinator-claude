#!/usr/bin/env bash
# scripts/setup.sh — Standalone install-chain walker for deep-research-claude.
#
# Walks the install-chain DAG declared in docs/install/agent-install-manifest.json,
# checks the single soft dep (coordinator-claude), and reports status.
#
# deep-research is chain step 4 of 5 in the install DAG:
#   holodeck → project-rag-ue-addon → project-rag → deep-research → coordinator-claude (soft)
#
# Usage: bash scripts/setup.sh [OPTIONS]
#
# Options:
#   --help              Print this help and exit 0.
#   --version           Print script version and exit 0.
#   --phase-list        List install phases and exit 0.
#   --last-status       Print last install status JSON and exit 0.
#   --check             Read-only check: probe deps and report status. Does NOT
#                       write install-status, manifest, or any persistent state.
#                       DR-specific read-only extension (contract § Read-only flag carve-out).
#   --skip-dep-check    Skip dependency-chain consent gate (pair with below).
#   --accept-missing-deps-risk
#                       Accept the risk of proceeding with a soft dep absent.
#                       Both override flags required together; one alone exits 93.
#
# Exit codes:
#   0   success (all deps satisfied, or soft deps absent with override accepted)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#
# Layout-agnostic repo_root resolution:
#   Flat layout (publish-repo):    scripts/ lives directly under repo root;
#                                  heuristic: ../docs/install/AGENT.md exists.
#   Nested layout (working-repo):  scripts/ lives under plugins/deep-research/;
#                                  heuristic: ../../coordinator-claude/coordinator/CLAUDE.md exists.
#
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
#
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C2
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#                § Read-only flag carve-out, § Severity semantics

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (DR-148 — bash >= 4 required)
# Script syntax must parse on bash 3.2; features used require 4+.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required. Stock macOS /bin/bash is 3.2 (unsupported)." >&2
    echo "Remediation: brew install bash && ensure /usr/local/bin/bash appears first in PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Script metadata
# ---------------------------------------------------------------------------
_SCRIPT_VERSION="1.0.0"
_SCRIPT_NAME="deep-research-claude setup"
_CHAIN_STEP="chain step 4 of 5"
_CHAIN_BANNER="DR install-chain walker — ${_CHAIN_STEP}"

# ---------------------------------------------------------------------------
# Locate this script and resolve repo_root (layout-agnostic).
#
# Two supported layouts:
#   Flat (publish-repo):
#     <repo-root>/scripts/setup.sh
#     <repo-root>/docs/install/AGENT.md     ← heuristic marker
#   Nested (working-repo):
#     <wr-root>/plugins/deep-research/scripts/setup.sh
#     <wr-root>/plugins/coordinator/CLAUDE.md ← heuristic marker
#
# DO NOT hardcode plugins/deep-research/ — that path does
# not exist in the flat publish-repo layout.
#
# Cross-platform portability (cross-platform-shell-portability.md):
#   Use _portable_realpath to resolve absolute paths; never bare realpath/readlink -f.
# ---------------------------------------------------------------------------
_portable_realpath() {
    # Portable realpath — works on stock macOS (no realpath / no readlink -f) and Linux.
    # cross-platform-shell-portability.md § Construct → portable fix
    if command -v realpath >/dev/null 2>&1; then realpath "$1"; return; fi
    if readlink -f "$1" >/dev/null 2>&1; then readlink -f "$1"; return; fi
    if [ -d "$1" ]; then (cd "$1" 2>/dev/null && pwd)
    else (cd "$(dirname "$1")" 2>/dev/null && printf '%s/%s\n' "$(pwd)" "$(basename "$1")"); fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect layout by heuristic probes.
_flat_marker="${SCRIPT_DIR}/../docs/install/AGENT.md"
_nested_marker="${SCRIPT_DIR}/../../coordinator-claude/coordinator/CLAUDE.md"

if [[ -f "${_flat_marker}" ]]; then
    # Flat layout: repo root is parent of scripts/
    REPO_ROOT="$(_portable_realpath "${SCRIPT_DIR}/..")"
elif [[ -f "${_nested_marker}" ]]; then
    # Nested layout: repo root is the deep-research/ tree root
    # (three levels up from scripts/ takes us to plugins/coordinator-claude/;
    #  we want plugins/deep-research/, i.e. one up from scripts/).
    REPO_ROOT="$(_portable_realpath "${SCRIPT_DIR}/..")"
else
    # Neither marker found — fall back to scripts/../ and continue.
    # This is the case during flat-layout simulation before AGENT.md is copied.
    REPO_ROOT="$(_portable_realpath "${SCRIPT_DIR}/..")"
fi

export REPO_ROOT

# ---------------------------------------------------------------------------
# Source dep_check.sh and manifest_reader.sh from lib/.
# These helpers are provided by C3 (template-copied from project-rag-ue-addon).
# Function signatures pinned from project_rag_ue_addon_scripts/lib/ precedent.
# ---------------------------------------------------------------------------
_LIB_DIR="${SCRIPT_DIR}/lib"

# shellcheck source=scripts/lib/manifest_reader.sh
source "${_LIB_DIR}/manifest_reader.sh" 2>/dev/null || {
    echo "ERROR: Cannot source scripts/lib/manifest_reader.sh." >&2
    echo "  Run: git status to verify file presence." >&2
    exit 1
}

# shellcheck source=scripts/lib/dep_check.sh
source "${_LIB_DIR}/dep_check.sh" 2>/dev/null || {
    echo "ERROR: Cannot source scripts/lib/dep_check.sh." >&2
    echo "  Run: git status to verify file presence." >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
SKIP_DEP_CHECK=false
ACCEPT_MISSING_DEPS_RISK=false
CHECK_FLAG=false
HELP_FLAG=false
VERSION_FLAG=false
PHASE_LIST=false
LAST_STATUS=false
I_AM_AGENT=false

export SKIP_DEP_CHECK ACCEPT_MISSING_DEPS_RISK CHECK_FLAG HELP_FLAG VERSION_FLAG PHASE_LIST LAST_STATUS I_AM_AGENT

while [[ $# -gt 0 ]]; do
    arg="$1"
    case "${arg}" in
        -h|--help)
            HELP_FLAG=true
            echo "Usage: bash scripts/setup.sh [OPTIONS]"
            echo ""
            echo "  --help                     Print this help and exit."
            echo "  --version                  Print script version and exit."
            echo "  --phase-list               List install phases and exit."
            echo "  --last-status              Print last install status JSON and exit."
            echo "  --check                    Read-only dep probe + status report. No state written."
            echo "                             DR-specific read-only extension (chain step 4 of 5)."
            echo "  --skip-dep-check           Skip dep-chain consent gate (pair with below)."
            echo "  --accept-missing-deps-risk Accept risk of proceeding with soft dep absent."
            echo "                             Both flags required together; one alone exits 93."
            echo ""
            echo "Exit codes: 0=ok  90=non-TTY/missing-dep  91=user-declined"
            echo "            92=agent-direct  93=incomplete-override-pair"
            exit 0
            ;;
        --version)
            VERSION_FLAG=true
            echo "${_SCRIPT_NAME} version ${_SCRIPT_VERSION}"
            exit 0
            ;;
        --phase-list)
            PHASE_LIST=true
            echo "dep-check:  probe coordinator-claude soft dep and report status"
            exit 0
            ;;
        --last-status)
            LAST_STATUS=true
            echo '{"overall": "no-prior-install"}'
            exit 0
            ;;
        --check)
            # DR repo-specific read-only extension (contract § Read-only flag carve-out).
            # MUST NOT write to install-status, manifest, or any persistent state.
            # Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
            CHECK_FLAG=true
            ;;
        --skip-dep-check)
            SKIP_DEP_CHECK=true
            ;;
        --accept-missing-deps-risk)
            # AUTHORITATIVE: docs/install/agent-install-manifest.json :: override_flags
            # JSON key: accept_hallucination_risk  CLI flag: --accept-missing-deps-risk
            ACCEPT_MISSING_DEPS_RISK=true
            ;;
        --i-am-agent)
            I_AM_AGENT=true
            ;;
        *)
            echo "ERROR: Unknown argument: ${arg}" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
    esac
    shift
done

export SKIP_DEP_CHECK ACCEPT_MISSING_DEPS_RISK CHECK_FLAG HELP_FLAG VERSION_FLAG PHASE_LIST LAST_STATUS I_AM_AGENT

# ---------------------------------------------------------------------------
# Override-flag pair integrity check.
# One flag without the other → exit 93.
# (Applies to install runs only; --check is read-only and does not require the pair.)
# ---------------------------------------------------------------------------
if [[ "${CHECK_FLAG}" == false ]]; then
    if [[ "${SKIP_DEP_CHECK}" == true && "${ACCEPT_MISSING_DEPS_RISK}" == false ]]; then
        echo "ERROR: --skip-dep-check requires --accept-missing-deps-risk (both flags required together)." >&2
        exit 93
    fi
    if [[ "${ACCEPT_MISSING_DEPS_RISK}" == true && "${SKIP_DEP_CHECK}" == false ]]; then
        echo "ERROR: --accept-missing-deps-risk requires --skip-dep-check (both flags required together)." >&2
        exit 93
    fi
fi

# ---------------------------------------------------------------------------
# Agent-direct short-circuit.
# Fires before the dep-check gate. Exit 92 unless full override pair is present.
# ---------------------------------------------------------------------------
if [[ "${I_AM_AGENT:-false}" == true || "${ADDON_RUN_MODE:-}" == "agent" ]]; then
    if [[ "${SKIP_DEP_CHECK:-false}" == true && "${ACCEPT_MISSING_DEPS_RISK:-false}" == true ]]; then
        : # full override pair present — fall through
    else
        echo "AGENT_MANIFEST_PATH=docs/install/AGENT.md" >&2
        echo "[setup] Agent-direct invocation detected. Use /deep-research:setup instead." >&2
        echo "[setup] Agent install guide: docs/install/AGENT.md" >&2
        echo "[setup] To run non-interactively, supply both:" >&2
        echo "[setup]   --i-am-agent --skip-dep-check --accept-missing-deps-risk" >&2
        exit 92
    fi
fi

# ---------------------------------------------------------------------------
# --check mode: read-only dep probe.
#
# Probe each direct_dep in the manifest and report:
#   present    → acknowledge-and-continue
#   missing    → soft: warn-and-offer-override + continue
#
# MUST NOT write to install-status, manifest, or any persistent state.
# DR repo-specific read-only extension (contract § Read-only flag carve-out).
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
if [[ "${CHECK_FLAG}" == true ]]; then
    echo "=========================================================="
    echo "  ${_CHAIN_BANNER}"
    echo "=========================================================="
    echo "  repo:         deep-research-claude"
    echo "  repo_root:    ${REPO_ROOT}"
    echo "  mode:         --check (read-only, no state written)"
    echo ""

    # Probe all direct_deps via the manifest reader + dep_check helpers.
    _PYTHON=""
    if command -v python3 >/dev/null 2>&1; then _PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then _PYTHON="python"
    else
        echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
        echo "  Python 3.11+ is required to read the install manifest." >&2
        exit 1
    fi
    export PYTHON="${_PYTHON}"

    _MANIFEST_PATH="${REPO_ROOT}/docs/install/agent-install-manifest.json"
    if [[ ! -f "${_MANIFEST_PATH}" ]]; then
        echo "WARNING: install manifest not found at ${_MANIFEST_PATH}" >&2
        echo "  C1 (manifest + AGENT.md) must land before --check can probe deps." >&2
        echo ""
        echo "  ${_CHAIN_BANNER}: no manifest to probe — exiting 0 (check-only mode)."
        exit 0
    fi

    # Read deps via manifest reader (function from scripts/lib/manifest_reader.sh).
    _NDJSON="$(_dr_manifest_read_ndjson "${_MANIFEST_PATH}" 2>&1)" || {
        echo "ERROR: manifest unreadable or corrupt: ${_MANIFEST_PATH}" >&2
        exit 1
    }

    _ALL_SATISFIED=true

    while IFS= read -r _dep_line; do
        [[ -z "${_dep_line}" ]] && continue

        _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_dep_line}" 2>/dev/null)"
        _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_dep_line}" 2>/dev/null)"

        # Probe this dep (function from scripts/lib/dep_check.sh).
        _status="$(_dr_dep_probe "${_dep_id}")"

        case "${_status}" in
            present)
                echo "  [${_dep_id}] coordinator dep satisfied — present ✓"
                ;;
            present-but-broken)
                echo "  [${_dep_id}] coordinator dep found but functional probe failed" >&2
                if [[ "${_dep_severity}" == "soft" ]]; then
                    echo "  WARNING: soft dep ${_dep_id} present-but-broken — continuing (warn-and-continue)." >&2
                    echo "    Override: re-run with --skip-dep-check --accept-missing-deps-risk to suppress." >&2
                    _ALL_SATISFIED=false
                fi
                ;;
            missing)
                if [[ "${_dep_severity}" == "soft" ]]; then
                    # Soft dep absent: warn loudly + offer override + continue.
                    # AC8 assertion: stderr must contain a warning AND --accept-missing-deps-risk.
                    echo "" >&2
                    echo "  WARNING: soft dep [${_dep_id}] is absent (missing)." >&2
                    echo "  deep-research works without coordinator-claude installed, but chain-walk" >&2
                    echo "  functionality is reduced." >&2
                    echo "  To suppress this warning and accept the missing dep:" >&2
                    echo "    bash scripts/setup.sh --skip-dep-check --accept-missing-deps-risk" >&2
                    echo "" >&2
                    _ALL_SATISFIED=false
                else
                    # Hard dep missing: fail loud (not applicable for DR which has only soft).
                    echo "ERROR: hard dep [${_dep_id}] is missing." >&2
                    exit 90
                fi
                ;;
        esac
    done <<< "${_NDJSON}"

    echo ""
    if [[ "${_ALL_SATISFIED}" == true ]]; then
        echo "  ${_CHAIN_BANNER}: all deps satisfied."
    else
        echo "  ${_CHAIN_BANNER}: soft dep(s) absent — proceeding (soft dep warn-and-continue)."
    fi
    echo "=========================================================="
    exit 0
fi

# ---------------------------------------------------------------------------
# Full install body (non-check mode).
#
# DR is a pure-coordinator-plugin — no Python deps, no binary installs, no
# Playwright, no libclang. The only install step is the dep-chain walk.
# The setup.sh exists to conform to the chain-walker contract and to exercise
# the soft-dep path end-to-end. The real heavy install is /deep-research:setup
# (the skill) which dispatches the chain-walker subagent.
# ---------------------------------------------------------------------------
echo "=========================================================="
echo "  ${_CHAIN_BANNER}"
echo "=========================================================="
echo "  repo:      deep-research-claude"
echo "  repo_root: ${REPO_ROOT}"
echo ""

# Python pre-flight (required for manifest read).
if command -v python3 >/dev/null 2>&1; then _PYTHON="python3"
elif command -v python >/dev/null 2>&1; then _PYTHON="python"
else
    echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
    exit 1
fi
export PYTHON="${_PYTHON}"

# Phase 0: dependency-chain gate.
# Run agent-mode prompt (from dep_check.sh) then consent gate.
if declare -F _dr_run_mode_prompt >/dev/null 2>&1; then
    _dr_run_mode_prompt
fi

if declare -F _dr_phase_zero_should_run >/dev/null 2>&1; then
    if _dr_phase_zero_should_run 2>/dev/null; then
        if declare -F _dr_consent_gate >/dev/null 2>&1; then
            _dr_consent_gate
        fi
    fi
fi

# Probe all deps and report status.
echo "[setup] Probing direct deps..."
if declare -F _dr_dep_probe_all >/dev/null 2>&1; then
    while IFS= read -r _probe_line; do
        [[ -z "${_probe_line}" ]] && continue
        _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_probe_line}" 2>/dev/null)"
        _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_probe_line}" 2>/dev/null)"
        _dep_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_probe_line}" 2>/dev/null)"
        _dep_hint="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('hint',''))" "${_probe_line}" 2>/dev/null)"

        case "${_dep_status}" in
            present)
                echo "[setup] dep [${_dep_id}] (${_dep_severity}): coordinator dep satisfied — present ✓"
                ;;
            present-but-broken|missing)
                if [[ "${_dep_severity}" == "soft" ]]; then
                    echo "" >&2
                    echo "WARNING: soft dep [${_dep_id}] is ${_dep_status}." >&2
                    [[ -n "${_dep_hint}" ]] && echo "  Hint: ${_dep_hint}" >&2
                    echo "  Override: re-run with --skip-dep-check --accept-missing-deps-risk to suppress." >&2
                    echo "" >&2
                else
                    echo "ERROR: hard dep [${_dep_id}] is ${_dep_status}." >&2
                    exit 90
                fi
                ;;
        esac
    done < <(_dr_dep_probe_all 2>/dev/null)
fi

echo ""
echo "[setup] ${_CHAIN_BANNER}: complete."
echo "  deep-research-claude has no Python/binary install phases."
echo "  Use /deep-research:setup to run the full chain-walker via the skill."
echo "=========================================================="
exit 0
