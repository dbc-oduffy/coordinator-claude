#!/usr/bin/env bash
# scripts/setup.sh — Standalone install-chain walker for coordinator-claude.
#
# Walks the install-chain DAG declared in docs/install/agent-install-manifest.json.
# coordinator-claude is DAG root (direct_deps: []); the walker terminates
# immediately after confirming the empty dep list with:
#   chain walk complete — coordinator-claude is DAG root
# and exits 0.
#
# coordinator-claude is chain step 5 of 5 in the install DAG:
#   holodeck → project-rag-ue-addon → project-rag → deep-research → coordinator-claude (DAG root)
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
#                       coord-specific read-only extension (contract § Read-only flag carve-out).
#   --skip-dep-check    Skip dependency-chain consent gate (pair with below).
#   --accept-missing-deps-risk
#                       Accept the risk of proceeding with a soft dep absent.
#                       Both override flags required together; one alone exits 93.
#
# Exit codes:
#   0   success (DAG root — no deps to check; or all deps satisfied)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#
# Layout-agnostic repo_root resolution:
#   Flat layout (publish-repo):    scripts/ lives directly under repo root;
#                                  heuristic: ../docs/install/AGENT.md exists.
#   Nested layout (working-repo):  scripts/ lives under plugins/coordinator/;
#                                  heuristic: ../coordinator/docs/install/AGENT.md exists.
#
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C2
# Spec backlink: docs/plans/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md §C2
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
_SCRIPT_NAME="coordinator-claude setup"
_CHAIN_STEP="chain step 5 of 5"
_CHAIN_BANNER="coordinator install-chain walker — ${_CHAIN_STEP}"

# ---------------------------------------------------------------------------
# Locate this script and resolve repo_root (layout-agnostic).
#
# Two supported layouts:
#   Flat (publish-repo):
#     <repo-root>/scripts/setup.sh
#     <repo-root>/docs/install/AGENT.md     ← heuristic marker
#   Nested (working-repo):
#     <wr-root>/plugins/coordinator/scripts/setup.sh
#     <wr-root>/plugins/coordinator/docs/install/AGENT.md ← heuristic marker
#
# DO NOT hardcode plugins/coordinator/ — that path does
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
_nested_marker="${SCRIPT_DIR}/../coordinator/docs/install/AGENT.md"

# F13: collapsed the flat/nested/fallback if/elif/else — all three branches resolved to
# the same _portable_realpath "${SCRIPT_DIR}/.." because scripts/ is always exactly one
# level below the coordinator/ tree root in both layouts. The probes only differentiate
# WHICH layout-marker exists, not the resulting path. A single assignment with an
# explanatory comment is equivalent and less confusing.
# Flat layout:   scripts/ is at <repo-root>/scripts/     → parent of scripts/ = <repo-root>
# Nested layout: scripts/ is at coordinator/scripts/     → parent of scripts/ = coordinator/
# Both cases:    parent of scripts/ is the correct repo root.
REPO_ROOT="$(_portable_realpath "${SCRIPT_DIR}/..")"

export REPO_ROOT

# ---------------------------------------------------------------------------
# Source dep_check.sh and manifest_reader.sh from lib/.
# Function names are _co_* (coordinator prefix — pinned from C3 lib exports).
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
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
SKIP_DEP_CHECK=false
ACCEPT_MISSING_DEPS_RISK=false
CHECK_FLAG=false
HELP_FLAG=false
VERSION_FLAG=false
PHASE_LIST=false
LAST_STATUS=false
I_AM_AGENT=false
# F5: removed pre-loop export here; variables are exported once after the while loop
# at the canonical post-parse export block (line ~210). The pre-loop export was redundant
# and could export stale values if the parser modified any variable after this point.

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
            echo "  --phase <name>             Run a named install phase and exit."
            echo "                             Read-only phases (no state written):"
            echo "                               seed-install-spinoff  DAG-root no-op; prints that"
            echo "                                                      coordinator STITCHES+DRIVES"
            echo "                                                      and seeds no leg baton for itself."
            echo "                             Unknown phase names exit non-zero with a remediation message."
            echo "  --last-status              Print last install status JSON and exit."
            echo "  --check                    Read-only dep probe + status report. No state written."
            echo "                             coord-specific read-only extension (chain step 5 of 5)."
            echo "  --skip-dep-check           Skip dep-chain consent gate (pair with below)."
            echo "  --accept-missing-deps-risk Accept risk of proceeding with dep absent."
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
            echo "Available --phase <name> values:"
            echo "  seed-install-spinoff  DAG-root no-op (read-only, no state written)"
            echo ""
            echo "Informational (NOT --phase <name> values):"
            echo "  dep-check:  coordinator-claude is DAG root — no upstream deps; chain-walk terminates here"
            exit 0
            ;;
        --phase)
            # Value-taking dispatch flag. Consumes the next argument as the phase name.
            # Read-only phases (no install-status write): seed-install-spinoff
            # Spec backlink: docs/plans/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md §C2 §Decision-0
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --phase requires a phase name argument." >&2
                echo "Run with --phase-list to see available phases." >&2
                echo "Run with --help for full usage." >&2
                exit 1
            fi
            _PHASE_NAME="$2"
            shift  # consume the phase name token ($2); inner case branches all exit, so the outer-loop shift is unreachable on the phase-dispatch path
            # Review: code-reviewer — guard against a forgotten phase name producing a confusing "Unknown --phase value: '--nextflag'" error
            if [[ "${_PHASE_NAME}" == --* ]]; then
                echo "ERROR: --phase requires a phase name, but got a flag ('${_PHASE_NAME}'). Did you forget the phase name?" >&2
                exit 1
            fi
            case "${_PHASE_NAME}" in
                seed-install-spinoff)
                    # Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
                    # coordinator-claude is the install-chain DAG-root spine: it STITCHES+DRIVES
                    # the install chain but seeds no leg baton for itself. The leaf bootstrap
                    # discovers coordinator via the manifest and invokes this phase; the correct
                    # outcome is exit 0 with an explanatory message — not SEED STEP ABSENT.
                    # Decision-0: no state written; deep-research baton is seeded by coordinator's
                    # own onboarding flow pre-reboot, not by this phase invocation.
                    echo "coordinator-claude: DAG-root spine — STITCHES+DRIVES the install chain; seeds no leg baton for itself (seed-install-spinoff is a no-op by design)."
                    exit 0
                    ;;
                *)
                    echo "ERROR: Unknown --phase value: '${_PHASE_NAME}'" >&2
                    echo "Run with --phase-list to see available phase names." >&2
                    echo "Run with --help for full usage." >&2
                    exit 1
                    ;;
            esac
            ;;
        --last-status)
            LAST_STATUS=true
            echo '{"overall": "no-prior-install"}'
            exit 0
            ;;
        --check)
            # coord repo-specific read-only extension (contract § Read-only flag carve-out).
            # MUST NOT write to install-status, manifest, or any persistent state.
            # Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
            CHECK_FLAG=true
            ;;
        --skip-dep-check)
            SKIP_DEP_CHECK=true
            ;;
        --accept-missing-deps-risk)
            # AUTHORITATIVE: docs/install/agent-install-manifest.json :: override_flags
            # JSON key: accept_missing_deps_risk  CLI flag: --accept-missing-deps-risk
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
if [[ "${I_AM_AGENT:-false}" == true || "${COORDINATOR_RUN_MODE:-}" == "agent" ]]; then
    if [[ "${SKIP_DEP_CHECK:-false}" == true && "${ACCEPT_MISSING_DEPS_RISK:-false}" == true ]]; then
        : # full override pair present — fall through
    else
        echo "AGENT_MANIFEST_PATH=docs/install/AGENT.md" >&2
        echo "[setup] Agent-direct invocation detected. Use /coordinator:setup instead." >&2
        echo "[setup] Agent install guide: docs/install/AGENT.md" >&2
        echo "[setup] To run non-interactively, supply both:" >&2
        echo "[setup]   --i-am-agent --skip-dep-check --accept-missing-deps-risk" >&2
        exit 92
    fi
fi

# ---------------------------------------------------------------------------
# --check mode: read-only dep probe.
#
# coordinator-claude is DAG root (direct_deps: []). The manifest probe loop
# will emit zero lines; the walker terminates with the DAG-root message.
#
# MUST NOT write to install-status, manifest, or any persistent state.
# coord repo-specific read-only extension (contract § Read-only flag carve-out).
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check
# ---------------------------------------------------------------------------
if [[ "${CHECK_FLAG}" == true ]]; then
    echo "=========================================================="
    echo "  ${_CHAIN_BANNER}"
    echo "=========================================================="
    echo "  repo:         coordinator-claude"
    echo "  repo_root:    ${REPO_ROOT}"
    echo "  mode:         --check (read-only, no state written)"
    echo ""

    # Probe all direct_deps via the manifest reader + dep_check helpers.
    _PYTHON=""
    if ! _PYTHON="$(_co_find_python 2>/dev/null)"; then
        echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
        echo "  Python 3.11+ is required to read the install manifest." >&2
        exit 1
    fi
    export PYTHON="${_PYTHON}"

    # Layout-aware resolution (nested working-tree vs flat publish-repo-root).
    # The resolver prints not-found remediation to stderr on failure.
    _MANIFEST_PATH=""
    if ! _MANIFEST_PATH="$(_co_resolve_manifest_path "${REPO_ROOT}")"; then
        echo "" >&2
        echo "  ${_CHAIN_BANNER}: no manifest to probe — exiting 0 (check-only mode)."
        exit 0
    fi

    # Read deps via manifest reader (function from scripts/lib/manifest_reader.sh).
    _NDJSON="$(_co_manifest_read_ndjson "${_MANIFEST_PATH}" 2>&1)" || {
        echo "ERROR: manifest unreadable or corrupt: ${_MANIFEST_PATH}" >&2
        exit 1
    }

    _DEP_COUNT=0
    _ALL_SATISFIED=true

    while IFS= read -r _dep_line; do
        [[ -z "${_dep_line}" ]] && continue
        _DEP_COUNT=$(( _DEP_COUNT + 1 ))

        _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_dep_line}" 2>/dev/null)"
        _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_dep_line}" 2>/dev/null)"

        # Probe this dep (function from scripts/lib/dep_check.sh).
        # F1: pass _MANIFEST_PATH to avoid double-resolve divergence.
        _status="$(_co_dep_probe "${_dep_id}" "${_MANIFEST_PATH}")"

        case "${_status}" in
            present)
                echo "  [${_dep_id}] dep satisfied — present ✓"
                ;;
            present-but-broken)
                echo "  [${_dep_id}] dep found but functional probe failed" >&2
                if [[ "${_dep_severity}" == "soft" ]]; then
                    echo "  WARNING: soft dep ${_dep_id} present-but-broken — continuing (warn-and-continue)." >&2
                    echo "    Override: re-run with --skip-dep-check --accept-missing-deps-risk to suppress." >&2
                    _ALL_SATISFIED=false
                fi
                ;;
            missing)
                if [[ "${_dep_severity}" == "soft" ]]; then
                    echo "" >&2
                    echo "  WARNING: soft dep [${_dep_id}] is absent (missing)." >&2
                    echo "  To suppress this warning and accept the missing dep:" >&2
                    echo "    bash scripts/setup.sh --skip-dep-check --accept-missing-deps-risk" >&2
                    echo "" >&2
                    _ALL_SATISFIED=false
                else
                    echo "ERROR: hard dep [${_dep_id}] is missing." >&2
                    exit 90
                fi
                ;;
        esac
    done <<< "${_NDJSON}"

    echo ""
    # DAG-root walker: coordinator-claude has no direct_deps.
    if [[ "${_DEP_COUNT}" -eq 0 ]]; then
        echo "chain walk complete — coordinator-claude is DAG root"
    elif [[ "${_ALL_SATISFIED}" == true ]]; then
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
# coordinator-claude is DAG root (direct_deps: []).
# The only install step is confirming the empty dep list and emitting the
# DAG-root termination message. The real heavy install is /coordinator:setup
# (the skill) which dispatches the chain-walker subagent.
# ---------------------------------------------------------------------------
echo "=========================================================="
echo "  ${_CHAIN_BANNER}"
echo "=========================================================="
echo "  repo:      coordinator-claude"
echo "  repo_root: ${REPO_ROOT}"
echo ""

# Python pre-flight (required for manifest read).
_PYTHON=""
if ! _PYTHON="$(_co_find_python 2>/dev/null)"; then
    echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
    exit 1
fi
export PYTHON="${_PYTHON}"

# Phase 0: dependency-chain gate.
# Run agent-mode prompt (from dep_check.sh) then consent gate.
if declare -F _co_run_mode_prompt >/dev/null 2>&1; then
    _co_run_mode_prompt
fi

if declare -F _co_phase_zero_should_run >/dev/null 2>&1; then
    if _co_phase_zero_should_run 2>/dev/null; then
        if declare -F _co_consent_gate >/dev/null 2>&1; then
            _co_consent_gate
        fi
    fi
fi

# Probe all deps and report status (coordinator-claude is DAG root; direct_deps is []).
echo "[setup] Probing direct deps..."
_DEP_COUNT=0

# Resolve the manifest layout-aware (nested working-tree vs flat publish root).
# Previously _MANIFEST_PATH was assigned ONLY in the --check block, so the
# full-install body dereferenced it unbound at the _co_dep_probe_all call
# below — `set -u` then hard-crashed with "_MANIFEST_PATH: unbound variable"
# (2026-06-17 holodeck-em report). A missing manifest is non-fatal here (the
# DAG-root walker has no direct_deps to probe), but it MUST fail loud with
# remediation instead of crashing. Guard the probe call on a non-empty path.
_MANIFEST_PATH=""
if ! _MANIFEST_PATH="$(_co_resolve_manifest_path "${REPO_ROOT}")"; then
    # Resolver emits only to stderr on failure, so the pre-init "" above already
    # holds — no inline reset needed; the probe loop below is guarded on non-empty.
    echo "[setup] WARNING: proceeding without dep probe — coordinator-claude is the DAG root (no direct_deps)." >&2
fi

if [[ -n "${_MANIFEST_PATH}" ]] && declare -F _co_dep_probe_all >/dev/null 2>&1; then
    while IFS= read -r _probe_line; do
        [[ -z "${_probe_line}" ]] && continue
        _DEP_COUNT=$(( _DEP_COUNT + 1 ))

        _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_probe_line}" 2>/dev/null)"
        _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_probe_line}" 2>/dev/null)"
        _dep_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_probe_line}" 2>/dev/null)"
        _dep_hint="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('hint',''))" "${_probe_line}" 2>/dev/null)"

        case "${_dep_status}" in
            present)
                echo "[setup] dep [${_dep_id}] (${_dep_severity}): dep satisfied — present ✓"
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
    # F1: pass _MANIFEST_PATH to _co_dep_probe_all to avoid a second divergent resolution.
    done < <(_co_dep_probe_all "${_MANIFEST_PATH}")
fi

echo ""
# DAG-root termination: coordinator-claude has no direct_deps.
if [[ "${_DEP_COUNT}" -eq 0 ]]; then
    echo "chain walk complete — coordinator-claude is DAG root"
else
    echo "[setup] ${_CHAIN_BANNER}: complete."
fi
echo "  coordinator-claude has no Python/binary install phases."
echo "  Use /coordinator:setup to run the full chain-walker via the skill."
echo "=========================================================="
exit 0
