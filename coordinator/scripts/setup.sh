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
#   --accept-no-git-auth
#                       Accept the risk of proceeding without verified git-host authentication.
#                       Suppresses the semi-hard exit (94) from a clone_auth semi-hard warn row.
#                       Standalone flag — does NOT require --skip-dep-check or --accept-missing-deps-risk.
#
# Exit codes:
#   0   success (DAG root — no deps to check; or all deps satisfied)
#   90  non-interactive/non-TTY dep missing, no override flag pair
#   91  user declined
#   92  agent-direct invocation without override flag pair
#   93  override flag pair incomplete (only one of two flags supplied)
#   94  semi-hard probe unverified (clone_auth unauthenticated; re-run with --accept-no-git-auth to suppress)
#
# Severity levels (--preflight exit-code gate):
#   hard       — exit non-zero unconditionally (currently: python, gh, node)
#   semi-hard  — exit 94 unless --accept-no-git-auth is supplied (currently: clone_auth)
#   advisory   — WARN row only; never fails exit code
#
# Layout-agnostic repo_root resolution:
#   Flat layout (publish-repo):    scripts/ lives directly under repo root;
#                                  heuristic: ../docs/install/AGENT.md exists.
#   Nested layout (working-repo):  scripts/ lives under plugins/coordinator/;
#                                  heuristic: ../coordinator/docs/install/AGENT.md exists.
#
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
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
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
# ---------------------------------------------------------------------------
SKIP_DEP_CHECK=false
ACCEPT_MISSING_DEPS_RISK=false
ACCEPT_NO_GIT_AUTH=false
CHECK_FLAG=false
PREFLIGHT_FLAG=false
HELP_FLAG=false
VERSION_FLAG=false
PHASE_LIST=false
LAST_STATUS=false
I_AM_AGENT=false
# chain-preinstall is stateful-by-contract (NOT in the read-only carve-out): set a
# deferred marker here, run the no-op body only AFTER the post-parse agent/token gate
# (so later-parsed override flags / the consent token are seen). See
# agent-install-contract.md § chain-preinstall phase.
_RUN_CHAIN_PREINSTALL=false
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
            echo "                             Stateful phases (gated; write install-status at heavy legs):"
            echo "                               chain-preinstall      pre-restart full-install seam;"
            echo "                                                      requires \$COORDINATOR_CHAIN_PREINSTALL_CONSENT (or the"
            echo "                                                      override pair) in agent mode; no-op body at root."
            echo "                             Unknown phase names exit non-zero with a remediation message."
            echo "  --last-status              Print last install status JSON and exit."
            echo "  --check                    Read-only dep probe + status report. No state written."
            echo "                             coord-specific read-only extension (chain step 5 of 5)."
            echo "  --preflight                Superset of --check: probes manifest deps AND machine"
            echo "                             environment prerequisites (python, uv, pwsh, ue,"
            echo "                             clone_auth, longpaths). Emits unified PASS/FAIL table"
            echo "                             + NDJSON. No state written. Exits non-zero when a"
            echo "                             hard probe fails, or when a semi-hard probe fails"
            echo "                             without --accept-no-git-auth."
            echo "  --skip-dep-check           Skip dep-chain consent gate (pair with below)."
            echo "  --accept-missing-deps-risk Accept risk of proceeding with dep absent."
            echo "                             Both flags required together; one alone exits 93."
            echo "  --accept-no-git-auth       Suppress semi-hard exit (94) from clone_auth probe."
            echo "                             Standalone flag — does not pair with dep-risk flags."
            echo ""
            echo "Exit codes: 0=ok  90=non-TTY/missing-dep  91=user-declined"
            echo "            92=agent-direct  93=incomplete-override-pair"
            echo "            94=semi-hard-git-auth-unverified (suppress with --accept-no-git-auth)"
            echo ""
            echo "Severity levels (--preflight):"
            echo "  hard      — exits non-zero unconditionally"
            echo "  semi-hard — exits 94 unless --accept-no-git-auth supplied"
            echo "  advisory  — WARN row; never fails exit code"
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
            echo "  chain-preinstall      Pre-restart full-install seam (stateful-by-contract; gated by \$COORDINATOR_CHAIN_PREINSTALL_CONSENT in agent mode; no-op body at the DAG root)"
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
                    # Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
                    # coordinator-claude is the install-chain DAG-root spine: it STITCHES+DRIVES
                    # the install chain but seeds no leg baton for itself. The leaf bootstrap
                    # discovers coordinator via the manifest and invokes this phase; the correct
                    # outcome is exit 0 with an explanatory message — not SEED STEP ABSENT.
                    # Decision-0: no state written; deep-research baton is seeded by coordinator's
                    # own onboarding flow pre-reboot, not by this phase invocation.
                    echo "coordinator-claude: DAG-root spine — STITCHES+DRIVES the install chain; seeds no leg baton for itself (seed-install-spinoff is a no-op by design)."
                    exit 0
                    ;;
                chain-preinstall)
                    # Stateful-by-contract phase — NOT an inline read-only exit like seed-install-spinoff.
                    # Set a deferred marker and DO NOT exit: let the rest of the arg loop parse
                    # (so a later --skip-dep-check / --accept-missing-deps-risk is seen), then the
                    # post-parse agent/token gate decides exit 92 vs no-op body. Phase-level gate,
                    # uniform across no-op and heavy legs. agent-install-contract.md § chain-preinstall.
                    _RUN_CHAIN_PREINSTALL=true
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
            # Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
            CHECK_FLAG=true
            ;;
        --preflight)
            # Superset of --check: probes manifest deps AND machine environment prerequisites.
            # MUST NOT write to install-status, manifest, or any persistent state.
            # Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
            PREFLIGHT_FLAG=true
            ;;
        --skip-dep-check)
            SKIP_DEP_CHECK=true
            ;;
        --accept-missing-deps-risk)
            # AUTHORITATIVE: docs/install/agent-install-manifest.json :: override_flags
            # JSON key: accept_missing_deps_risk  CLI flag: --accept-missing-deps-risk
            ACCEPT_MISSING_DEPS_RISK=true
            ;;
        --accept-no-git-auth)
            # Standalone override: suppresses the semi-hard exit (94) from a clone_auth semi-hard
            # warn row. Does NOT require --skip-dep-check or --accept-missing-deps-risk.
            # Logs to stderr at preflight time so the suppression is auditable.
            ACCEPT_NO_GIT_AUTH=true
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

export SKIP_DEP_CHECK ACCEPT_MISSING_DEPS_RISK ACCEPT_NO_GIT_AUTH CHECK_FLAG PREFLIGHT_FLAG HELP_FLAG VERSION_FLAG PHASE_LIST LAST_STATUS I_AM_AGENT _RUN_CHAIN_PREINSTALL

# ---------------------------------------------------------------------------
# Override-flag pair integrity check.
# One flag without the other → exit 93.
# (Applies to install runs only; --check is read-only and does not require the pair.)
# ---------------------------------------------------------------------------
if [[ "${CHECK_FLAG}" == false && "${PREFLIGHT_FLAG}" == false ]]; then
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
    elif [[ "${_RUN_CHAIN_PREINSTALL:-false}" == true && -n "${COORDINATOR_CHAIN_PREINSTALL_CONSENT:-}" ]]; then
        : # chain-preinstall phase inside a consented chain walk — fall through.
          # The consent token is the same trust altitude as the override pair (a deliberate
          # redirect-guard escape, not a capability token); it gates this phase WITHOUT
          # being a blanket agent bypass. agent-install-contract.md § chain-preinstall.
    else
        echo "AGENT_MANIFEST_PATH=docs/install/AGENT.md" >&2
        echo "[setup] Agent-direct invocation detected." >&2
        echo "[setup]   To BOOTSTRAP A MACHINE (machine-local registry, venv, substrate): run /coordinator:install (Phase 3)." >&2
        echo "[setup]   To WALK THE INSTALL CHAIN only (DAG walk, bootstraps nothing): run /coordinator:setup." >&2
        echo "[setup] This script (setup.sh) is the chain-walker and installs no machine substrate itself." >&2
        echo "[setup] Agent install guide: docs/install/AGENT.md" >&2
        if [[ "${_RUN_CHAIN_PREINSTALL:-false}" == true ]]; then
            echo "[setup] --phase chain-preinstall requires a consented chain walk:" >&2
            echo "[setup]   set \$COORDINATOR_CHAIN_PREINSTALL_CONSENT (the chain-walk token) — or supply the override pair" >&2
            echo "[setup]   --i-am-agent --skip-dep-check --accept-missing-deps-risk" >&2
        else
            echo "[setup] To run non-interactively, supply both:" >&2
            echo "[setup]   --i-am-agent --skip-dep-check --accept-missing-deps-risk" >&2
        fi
        exit 92
    fi
fi

# ---------------------------------------------------------------------------
# chain-preinstall phase body (post-gate). Reached only when the agent/token
# gate above passed (or in non-agent mode). coordinator-claude is the DAG root
# with no script-install body, so chain-preinstall is a no-op here — it still
# routes THROUGH the gate above (phase-level gate, uniform across legs), then
# exits 0. NOT in the read-only carve-out: stateful-by-contract.
# ---------------------------------------------------------------------------
if [[ "${_RUN_CHAIN_PREINSTALL:-false}" == true ]]; then
    echo "coordinator-claude: DAG-root spine — nothing to preinstall (chain-preinstall no-op body at the root; capability install happens at downstream heavy-install legs)."
    exit 0
fi

# ---------------------------------------------------------------------------
# --check mode: read-only dep probe.
#
# coordinator-claude is DAG root (direct_deps: []). The manifest probe loop
# will emit zero lines; the walker terminates with the DAG-root message.
#
# MUST NOT write to install-status, manifest, or any persistent state.
# coord repo-specific read-only extension (contract § Read-only flag carve-out).
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
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
# _co_pf_emit_row <id> <status> <severity> <hint>
#
# Purpose: print one unified table row (human-readable to stderr) and one
# NDJSON line (to stdout). Updates _PF_HARD_FAIL / _PF_SEMIHARD_FAIL when
# the severity tier warrants it. Severity-aware: advisory warn/fail never
# fails the exit code.
#
# Called by _co_run_prereq_gate in BOTH strict and post-consumer modes with
# the severity already demoted (post-consumer) or un-demoted (strict).
# This function is BYTE-IDENTICAL across both modes — do NOT add mode logic here.
#
# Requires: ${_PYTHON} set in caller scope (used for NDJSON re-emission).
# Spec backlink: docs/plans/2026-06-23-clone-auth-semi-hard-step-zero.md §C3
# ---------------------------------------------------------------------------
_co_pf_emit_row() {
    local _id="$1"
    local _status="$2"
    local _severity="$3"
    local _hint="$4"

    # Human-readable table row — ALL to stderr so stdout is pure NDJSON.
    # Review: code-reviewer — send all human-readable table rows to stderr; NDJSON to stdout only,
    #   so --preflight 2>/dev/null yields clean machine-parseable NDJSON on stdout.
    # Review: code-reviewer — nit: fix [???? ] (7 chars) to [????] for consistent 6-char width
    # Review: code-reviewer — F1: all status labels rendered at fixed %-7s width so
    #   probe-name column aligns; [PASS]/[WARN]/[FAIL]/[????] padded to match [BLOCK].
    case "${_status}" in
        pass|present)
            printf '  %-7s %-20s (%s)\n' "[PASS]" "${_id}" "${_severity}" >&2
            ;;
        warn|present-but-broken)
            if [[ "${_severity}" == "semi-hard" ]]; then
                # Semi-hard warn: print [BLOCK] row and set _PF_SEMIHARD_FAIL.
                printf '  %-7s %-20s (%s)' "[BLOCK]" "${_id}" "${_severity}" >&2
                if [[ -n "${_hint}" ]]; then
                    printf ' — %s' "${_hint}" >&2
                fi
                printf '\n' >&2
                _PF_SEMIHARD_FAIL=true
            else
                printf '  %-7s %-20s (%s)' "[WARN]" "${_id}" "${_severity}" >&2
                if [[ -n "${_hint}" ]]; then
                    printf ' — %s' "${_hint}" >&2
                fi
                printf '\n' >&2
            fi
            ;;
        fail|missing)
            if [[ "${_severity}" == "hard" ]]; then
                printf '  %-7s %-20s (%s)' "[FAIL]" "${_id}" "${_severity}" >&2
                if [[ -n "${_hint}" ]]; then
                    printf ' — %s' "${_hint}" >&2
                fi
                printf '\n' >&2
                _PF_HARD_FAIL=true
            elif [[ "${_severity}" == "semi-hard" ]]; then
                # Semi-hard fail: print [BLOCK] row and set _PF_SEMIHARD_FAIL.
                printf '  %-7s %-20s (%s)' "[BLOCK]" "${_id}" "${_severity}" >&2
                if [[ -n "${_hint}" ]]; then
                    printf ' — %s' "${_hint}" >&2
                fi
                printf '\n' >&2
                _PF_SEMIHARD_FAIL=true
            else
                # Advisory fail — print as WARN, do not set _PF_HARD_FAIL.
                printf '  %-7s %-20s (%s)' "[WARN]" "${_id}" "${_severity}" >&2
                if [[ -n "${_hint}" ]]; then
                    printf ' — %s' "${_hint}" >&2
                fi
                printf '\n' >&2
            fi
            ;;
        inconclusive)
            printf '  %-7s %-20s (%s)' "[????]" "${_id}" "${_severity}" >&2
            if [[ -n "${_hint}" ]]; then
                printf ' — %s' "${_hint}" >&2
            fi
            printf '\n' >&2
            ;;
        *)
            printf '  [%-6s] %-20s (%s)\n' "${_status}" "${_id}" "${_severity}" >&2
            ;;
    esac

    # NDJSON line — one per probe row, to stdout (pure machine-parseable stream).
    # Normalise dep-probe statuses to the prereq_probe vocabulary for a
    # consistent NDJSON stream: present→pass, missing→fail,
    # present-but-broken→warn (advisory shape; dep rows have no hard fail here).
    # Review: code-reviewer — re-emit NDJSON via Python to ensure proper JSON escaping of all
    #   fields; a remediation string with backslash/quote/backtick (Windows path, git config
    #   command) would otherwise produce invalid JSON from a bare printf.
    local _ndjson_status="${_status}"
    case "${_status}" in
        present)           _ndjson_status="pass" ;;
        missing)           _ndjson_status="fail" ;;
        present-but-broken) _ndjson_status="warn" ;;
    esac
    "${_PYTHON}" -c "
import json, sys
row = {'id': sys.argv[1], 'status': sys.argv[2], 'severity': sys.argv[3], 'hint': sys.argv[4]}
print(json.dumps(row, ensure_ascii=False))
" "${_id}" "${_ndjson_status}" "${_severity}" "${_hint}"
}

# ---------------------------------------------------------------------------
# _co_run_prereq_gate <mode>
#
# Purpose: unified prereq-probe consumption + manifest-dep probe + exit-gate.
# DRY — called by both --preflight (strict) and the default chain-walk body
# (post-consumer). The ONLY per-mode difference is a severity-demotion pre-pass:
#
#   strict:        no demotion — probes emit at their declared severity.
#                  python=hard  gh=hard  node=hard  git=hard  clone_auth=semi-hard
#
#   post-consumer: demote gh, node, git, AND clone_auth → advisory.
#                  python STAYS hard (existing hard gate; no regression).
#                  Rationale: chain-walk default body currently exits 0; any new
#                  non-zero exit is a retroactive regression. Advisory WARN for
#                  gh/node/git/clone_auth keeps the chain-walk's only hard gate
#                  = python (unchanged).
#                  (Decision-3 refinement: clone_auth also demotes to advisory on
#                  the chain-walk, not semi-hard. --preflight keeps semi-hard.)
#
# Exit-gate (BYTE-IDENTICAL logic in both modes — demotion happens before):
#   _PF_HARD_FAIL=true     → exit 1  (hard probe failure)
#   _PF_SEMIHARD_FAIL=true
#   && ACCEPT_NO_GIT_AUTH!=true → exit 94 (semi-hard unverified)
#   Otherwise              → return 0 (caller continues or exits 0)
#
# Requires globals set by caller BEFORE calling this function:
#   ${_PYTHON}           — python binary path (used by _co_pf_emit_row NDJSON)
#   ${_PYTHON_AVAILABLE} — "true" | "false"
#   ${_MANIFEST_PATH}    — resolved manifest path (may be empty = skip dep probes)
#   ${ACCEPT_NO_GIT_AUTH} — "true" | "false"
#   ${_LIB_DIR}          — scripts/lib/ directory (to source prereq_probe.sh)
#   ${_CHAIN_BANNER}     — banner string for exit messages
#
# Spec backlink: docs/plans/2026-06-23-clone-auth-semi-hard-step-zero.md §C3
# Negative-spec: do NOT add mode-specific logic inside _co_pf_emit_row.
#   The demotion pre-pass happens here, before _co_pf_emit_row is called.
# ---------------------------------------------------------------------------
_co_run_prereq_gate() {
    local _gate_mode="$1"

    # ---------------------------------------------------------------------------
    # Unified table state.
    # _PF_HARD_FAIL:     set when any severity=hard probe emits status=fail/missing.
    # _PF_SEMIHARD_FAIL: set when any severity=semi-hard probe emits status=fail/warn.
    #   Semi-hard exits 94 unless --accept-no-git-auth is supplied.
    # ---------------------------------------------------------------------------
    _PF_HARD_FAIL=false
    _PF_SEMIHARD_FAIL=false

    # Log --accept-no-git-auth suppression intent early so it appears in stderr before table rows.
    if [[ "${ACCEPT_NO_GIT_AUTH}" == true ]]; then
        echo "[prereq-gate] --accept-no-git-auth: proceeding without verified git-host auth (operator override)" >&2
    fi

    # ---------------------------------------------------------------------------
    # Part 1: environment-prerequisite probes (prereq_probe.sh).
    # These do NOT require Python — run them first so the python probe row and its
    # remediation appear in output even when Python is absent. The python probe has
    # severity=hard, so _PF_HARD_FAIL will be set by _co_pf_emit_row if it fails;
    # the exit gate below then drives the non-zero exit without an early exit 1.
    #
    # Source prereq_probe.sh. The lib has its own bash-version guard (>=4) and
    # idempotency guard; set -e is active so source failure exits immediately.
    # Errors are surfaced (FB-4 — no 2>/dev/null masking of real errors).
    # ---------------------------------------------------------------------------
    echo "  --- environment prerequisite probes ---" >&2
    _PREREQ_LIB="${_LIB_DIR}/prereq_probe.sh"
    if [[ ! -f "${_PREREQ_LIB}" ]]; then
        echo "ERROR: prereq_probe.sh not found at ${_PREREQ_LIB}" >&2
        echo "  Ensure scripts/lib/prereq_probe.sh is present (committed 2026-06-22)." >&2
        exit 1
    fi
    # shellcheck source=scripts/lib/prereq_probe.sh
    source "${_PREREQ_LIB}"

    # Consume _co_prereq_probe_all NDJSON; apply severity-demotion pre-pass for
    # post-consumer mode, then route each row through _co_pf_emit_row.
    #
    # Adapter: {name,status,severity,detail,remediation} → (id, status, severity, hint)
    #   hint = detail (if non-empty) + " | Remediation: " + remediation (if non-empty)
    #
    # Demotion table (post-consumer mode only):
    #   gh, node, git, clone_auth → advisory  (keeps exit-code regression-free)
    #   python                    → UNCHANGED (stays hard; existing hard gate)
    #   all others                → UNCHANGED (already advisory)
    #
    # When Python is available, parse fields with Python (exact, handles escaping).
    # When Python is absent, _co_pf_emit_row's NDJSON emission will fail, but the
    # prereq_probe_all raw JSON lines are already valid NDJSON — pass them through
    # directly to stdout and emit human-readable rows with awk as a fallback.
    while IFS= read -r _prereq_line; do
        [[ -z "${_prereq_line}" ]] && continue

        if [[ "${_PYTHON_AVAILABLE}" == true ]]; then
            _pr_name="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('name',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_detail="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('detail',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_remediation="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('remediation',''))" "${_prereq_line}" 2>/dev/null)"

            # Build hint: detail + remediation (both may be empty).
            _pr_hint="${_pr_detail}"
            if [[ -n "${_pr_remediation}" ]]; then
                if [[ -n "${_pr_hint}" ]]; then
                    _pr_hint="${_pr_hint} | Remediation: ${_pr_remediation}"
                else
                    _pr_hint="Remediation: ${_pr_remediation}"
                fi
            fi

            # Severity-demotion pre-pass (post-consumer mode only).
            # Applied BEFORE _co_pf_emit_row so the emit function stays mode-agnostic.
            local _pr_severity_eff="${_pr_severity}"
            if [[ "${_gate_mode}" == "post-consumer" ]]; then
                case "${_pr_name}" in
                    gh|node|git|clone_auth)
                        _pr_severity_eff="advisory"
                        ;;
                esac
            fi

            _co_pf_emit_row "${_pr_name}" "${_pr_status}" "${_pr_severity_eff}" "${_pr_hint}"
        else
            # Python absent: pass raw NDJSON from prereq_probe_all directly to stdout;
            # print minimal human-readable row to stderr using awk for field extraction.
            # The human-readable row is best-effort; NDJSON stdout is exact.
            # In post-consumer mode, demotion applies in the gate logic below too.
            printf '%s\n' "${_prereq_line}"
            _pr_name_raw="$(printf '%s' "${_prereq_line}" | awk -F'"name":"' '{print $2}' | awk -F'"' '{print $1}')"
            _pr_status_raw="$(printf '%s' "${_prereq_line}" | awk -F'"status":"' '{print $2}' | awk -F'"' '{print $1}')"
            _pr_severity_raw="$(printf '%s' "${_prereq_line}" | awk -F'"severity":"' '{print $2}' | awk -F'"' '{print $1}')"
            # Review: review-integrator F3 — replace bash-4 ${_pr_status_raw^^} with portable
            # tr uppercase — the python-absent path is exactly where bash-4 features are riskiest.
            _pr_status_upper="$(printf '%s' "${_pr_status_raw}" | tr '[:lower:]' '[:upper:]')"

            # Apply demotion for post-consumer mode in the awk fallback path too.
            local _pr_severity_eff_raw="${_pr_severity_raw}"
            if [[ "${_gate_mode}" == "post-consumer" ]]; then
                case "${_pr_name_raw}" in
                    gh|node|git|clone_auth)
                        _pr_severity_eff_raw="advisory"
                        ;;
                esac
            fi

            printf '  [%-4s] %-20s (%s)\n' "${_pr_status_upper}" "${_pr_name_raw}" "${_pr_severity_eff_raw}" >&2
            # Gate _PF_HARD_FAIL for severity=hard + status=fail (python probe row).
            if [[ "${_pr_status_raw}" == "fail" && "${_pr_severity_eff_raw}" == "hard" ]]; then
                _PF_HARD_FAIL=true
            fi
            # Review: review-integrator F4 — Python-absent fallback was missing _PF_SEMIHARD_FAIL gate.
            # A machine with no Python + no git auth would exit 0 instead of 94. Add parallel gate.
            if [[ ( "${_pr_status_raw}" == "warn" || "${_pr_status_raw}" == "fail" ) && "${_pr_severity_eff_raw}" == "semi-hard" ]]; then
                _PF_SEMIHARD_FAIL=true
            fi
        fi
    done < <(_co_prereq_probe_all)

    echo "" >&2

    # ---------------------------------------------------------------------------
    # Part 2: manifest dep probes (same as --check).
    # coordinator-claude is DAG root; direct_deps is []. Loop emits zero rows.
    # Skipped entirely when Python is absent — emit a single "skipped: no python" row.
    # ---------------------------------------------------------------------------
    echo "  --- manifest dep probes ---" >&2
    _DEP_COUNT=0
    if [[ "${_PYTHON_AVAILABLE}" == false ]]; then
        # Emit a skipped row directly as raw NDJSON (cannot use _co_pf_emit_row — it calls Python).
        # The python hard-fail row above already drives _PF_HARD_FAIL; this row is informational.
        printf '{"id":"manifest-deps","status":"inconclusive","severity":"advisory","hint":"skipped: no python interpreter available (required for manifest dep probes)"}\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
        echo "  (manifest dep probes skipped — no python available)" >&2
    elif [[ -n "${_MANIFEST_PATH}" ]]; then
        # _co_dep_probe_all is guaranteed present — dep_check.sh was sourced unconditionally
        # above under set -e, so if we reached here the function exists.
        # Review: code-reviewer — F9: declare -F guard is dead; function guaranteed present after source
        while IFS= read -r _probe_line; do
            [[ -z "${_probe_line}" ]] && continue
            _DEP_COUNT=$(( _DEP_COUNT + 1 ))

            _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_probe_line}" 2>/dev/null)"
            _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_probe_line}" 2>/dev/null)"
            _dep_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_probe_line}" 2>/dev/null)"
            _dep_hint="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('hint',''))" "${_probe_line}" 2>/dev/null)"

            _co_pf_emit_row "${_dep_id}" "${_dep_status}" "${_dep_severity}" "${_dep_hint}"
        done < <(_co_dep_probe_all "${_MANIFEST_PATH}")
    fi

    if [[ "${_DEP_COUNT}" -eq 0 && "${_PYTHON_AVAILABLE}" == true ]]; then
        echo "  (no manifest deps — coordinator-claude is DAG root)" >&2
    fi
    echo "" >&2

    # ---------------------------------------------------------------------------
    # Exit gate (BYTE-IDENTICAL logic across strict and post-consumer modes).
    # Demotion was applied above before _co_pf_emit_row, so _PF_HARD_FAIL and
    # _PF_SEMIHARD_FAIL already reflect the effective (possibly demoted) severity.
    # Returns 0 on success so the caller can continue (print banner, exit 0, etc.).
    # ---------------------------------------------------------------------------
    if [[ "${_PF_HARD_FAIL}" == true ]]; then
        echo "  ${_CHAIN_BANNER}: PREREQ GATE FAILED (hard probe failure — see [FAIL] rows above)." >&2
        exit 1
    elif [[ "${_PF_SEMIHARD_FAIL}" == true && "${ACCEPT_NO_GIT_AUTH}" != true ]]; then
        echo "  ${_CHAIN_BANNER}: PREREQ GATE BLOCKED (semi-hard probe unverified — see [BLOCK] rows above)." >&2
        echo "  Suppress with: --accept-no-git-auth (operator override; audited to stderr)." >&2
        exit 94
    fi
    # Success — return 0; caller prints summary and exits.
    return 0
}

# ---------------------------------------------------------------------------
# --preflight mode: unified dep + environment-prerequisite probe.
#
# SUPERSET of --check: runs the existing manifest-dep probes AND the six
# machine-environment probes from prereq_probe.sh through ONE tabling +
# NDJSON code path. Does NOT write install-status or any persistent state.
#
# Exit-code gate (severity-aware, post-consumer-gate doctrine):
#   NON-ZERO only when status=fail AND severity=hard.
#   status=warn/fail with severity=advisory: prints WARN line + remediation,
#   does NOT fail exit code. inconclusive: prints INCONCLUSIVE, does not fail.
#
# Adapter: prereq_probe.sh emits {name,status,severity,detail,remediation}.
#   We map: name→id, detail+remediation→hint (combined). The dep-probe rows
#   already carry {id,severity,status,hint} from _co_dep_probe_all.
#   Both shapes flow through ONE unified tabling function (_co_pf_emit_row).
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md §C1
# Read-only flags (no install-status write): --help --version --phase-list --phase seed-install-spinoff --last-status --i-am-agent --check --preflight
# ---------------------------------------------------------------------------
if [[ "${PREFLIGHT_FLAG}" == true ]]; then
    # All human-readable output goes to stderr so stdout is pure NDJSON.
    # Review: code-reviewer — F5: banner/header/summary lines also go to stderr for clean NDJSON stdout
    echo "==========================================================" >&2
    echo "  ${_CHAIN_BANNER}" >&2
    echo "==========================================================" >&2
    echo "  repo:         coordinator-claude" >&2
    echo "  repo_root:    ${REPO_ROOT}" >&2
    echo "  mode:         --preflight (read-only; dep probes + env prereq probes)" >&2
    echo "" >&2

    # ---------------------------------------------------------------------------
    # Python discovery (required for manifest read and dep probes).
    # Review: code-reviewer — reorder: run prereq probes (no python needed) FIRST;
    #   only skip manifest-dep probes if python absent; let _PF_HARD_FAIL gate the exit.
    #   This ensures the python probe itself (with its remediation) appears in the output
    #   even when python is absent, rather than exiting early before any rows emit.
    # ---------------------------------------------------------------------------
    _PYTHON=""
    _PYTHON_AVAILABLE=true
    if ! _PYTHON="$(_co_find_python 2>/dev/null)"; then
        _PYTHON_AVAILABLE=false
    fi
    export PYTHON="${_PYTHON:-}"

    # Layout-aware manifest resolution (only attempted if python is available).
    _MANIFEST_PATH=""
    if [[ "${_PYTHON_AVAILABLE}" == true ]]; then
        if ! _MANIFEST_PATH="$(_co_resolve_manifest_path "${REPO_ROOT}")"; then
            echo "" >&2
            echo "  ${_CHAIN_BANNER}: no manifest found — skipping dep probes." >&2
        fi
    fi

    # Run the shared prereq gate (strict mode: no severity demotion).
    # On hard/semi-hard failure, _co_run_prereq_gate exits non-zero.
    # On success, returns 0 and we emit the success banner below.
    _co_run_prereq_gate strict

    echo "  ${_CHAIN_BANNER}: preflight complete (no hard or unaccepted semi-hard failures)." >&2
    echo "==========================================================" >&2
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

# Python pre-flight (required for manifest read and prereq gate).
_PYTHON=""
if ! _PYTHON="$(_co_find_python 2>/dev/null)"; then
    echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
    exit 1
fi
export PYTHON="${_PYTHON}"
_PYTHON_AVAILABLE=true

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

# ---------------------------------------------------------------------------
# Prereq gate (post-consumer mode): run system-level prerequisite probes as
# part of the chain-walk. Python's hard gate was already enforced by the EARLY
# python-discovery exit above (_co_find_python, ~line 868-871) — if we reach
# here, _PYTHON_AVAILABLE=true. _co_run_prereq_gate post-consumer therefore
# runs with python confirmed; gh/node/git/clone_auth are demoted to advisory
# in this mode and emit WARN rows but do not block exit 0.
# Review: code-reviewer — F2: corrected comment to accurately describe the
#   python hard gate as enforced by the early _co_find_python exit above,
#   not by the prereq gate itself.
# ---------------------------------------------------------------------------
# Resolve the manifest layout-aware (nested working-tree vs flat publish root).
_MANIFEST_PATH=""
if ! _MANIFEST_PATH="$(_co_resolve_manifest_path "${REPO_ROOT}")"; then
    echo "[setup] WARNING: proceeding without dep probe — coordinator-claude is the DAG root (no direct_deps)." >&2
fi

echo "[setup] Running prereq gate (post-consumer mode)..."
_co_run_prereq_gate post-consumer

# DAG-root termination: coordinator-claude has no direct_deps.
# _DEP_COUNT is set by _co_run_prereq_gate (Part 2 manifest dep probes).
echo ""
if [[ "${_DEP_COUNT:-0}" -eq 0 ]]; then
    echo "chain walk complete — coordinator-claude is DAG root"
else
    echo "[setup] ${_CHAIN_BANNER}: complete."
fi
echo "  coordinator-claude has no Python/binary install phases."
echo "  Use /coordinator:setup to run the full chain-walker via the skill."
echo "=========================================================="
exit 0
