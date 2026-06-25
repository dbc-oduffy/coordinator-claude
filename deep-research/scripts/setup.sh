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
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check --preflight
#
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C2
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
#                § Read-only flag carve-out, § Severity semantics

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard (DR-148 — bash >= 4 required)
# Script syntax must parse on bash 3.2; features used require 4+.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
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

# shellcheck source=scripts/lib/coordinator_prereq/manifest_reader.sh
source "${_LIB_DIR}/coordinator_prereq/manifest_reader.sh" 2>/dev/null || {
    echo "ERROR: Cannot source scripts/lib/coordinator_prereq/manifest_reader.sh." >&2
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
PREFLIGHT_FLAG=false
HELP_FLAG=false
VERSION_FLAG=false
PHASE_LIST=false
LAST_STATUS=false
I_AM_AGENT=false
# chain-preinstall is stateful-by-contract (NOT in the read-only carve-out): the --phase
# case sets this marker instead of exiting inline, so the post-parse agent/token gate decides
# exit 92 vs no-op body. Mirrors coordinator setup.sh. agent-install-contract.md § chain-preinstall.
_RUN_CHAIN_PREINSTALL=false
# (Pre-loop export removed for parity with coordinator setup.sh F5 — code-reviewer slice-A F1.
#  The post-loop export at the canonical block below is authoritative; a pre-loop export would
#  ship the stale pre-parse `_RUN_CHAIN_PREINSTALL=false` to any subshell launched mid-parse.)

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
            echo "                             Stateful phases (gated): chain-preinstall — pre-restart"
            echo "                               full-install seam; requires \$COORDINATOR_CHAIN_PREINSTALL_CONSENT (or"
            echo "                               the override pair) in agent mode; no-op body (DR is pure-plugin)."
            echo "                             Unknown phase names exit non-zero (fail-loud)."
            echo "  --last-status              Print last install status JSON and exit."
            echo "  --check                    Read-only dep probe + status report. No state written."
            echo "                             DR-specific read-only extension (chain step 4 of 5)."
            echo "  --preflight                Superset of --check: dep probes + machine environment"
            echo "                             prerequisite probes (Python, gh, git, node, clone_auth, …)."
            echo "                             Read-only; no state written. Exit 1 on hard failure."
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
            echo "Available --phase <name> values:"
            echo "  chain-preinstall  Pre-restart full-install seam (stateful-by-contract; gated by \$COORDINATOR_CHAIN_PREINSTALL_CONSENT in agent mode; no-op body — DR is pure-plugin)"
            echo ""
            echo "Informational (NOT --phase <name> values):"
            echo "  dep-check:  probe coordinator-claude soft dep and report status"
            exit 0
            ;;
        --phase)
            # Value-taking dispatch flag (added for chain-preinstall — DR's first --phase).
            # Mirrors coordinator setup.sh: flag-shaped-value guard + unknown-phase fail-loud.
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --phase requires a phase name argument." >&2
                echo "Run with --phase-list to see available phases." >&2
                echo "Run with --help for full usage." >&2
                exit 1
            fi
            _PHASE_NAME="$2"
            shift  # consume the phase name token ($2); inner case branches exit or fall through
            if [[ "${_PHASE_NAME}" == --* ]]; then
                echo "ERROR: --phase requires a phase name, but got a flag ('${_PHASE_NAME}'). Did you forget the phase name?" >&2
                exit 1
            fi
            case "${_PHASE_NAME}" in
                chain-preinstall)
                    # Stateful-by-contract — NOT an inline read-only exit. Set the marker and
                    # DO NOT exit; the post-parse agent/token gate decides exit 92 vs no-op body.
                    # Phase-level gate, uniform across legs. agent-install-contract.md § chain-preinstall.
                    # (DR seeds no seed-install-spinoff: coordinator seeds DR's spinoff from a template.)
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
            # DR repo-specific read-only extension (contract § Read-only flag carve-out).
            # MUST NOT write to install-status, manifest, or any persistent state.
            # Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check --preflight
            CHECK_FLAG=true
            ;;
        --preflight)
            # Superset of --check: probes manifest deps AND machine environment prerequisites.
            # MUST NOT write to install-status, manifest, or any persistent state.
            # Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check --preflight
            PREFLIGHT_FLAG=true
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

export SKIP_DEP_CHECK ACCEPT_MISSING_DEPS_RISK CHECK_FLAG PREFLIGHT_FLAG HELP_FLAG VERSION_FLAG PHASE_LIST LAST_STATUS I_AM_AGENT _RUN_CHAIN_PREINSTALL

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
if [[ "${I_AM_AGENT:-false}" == true || "${ADDON_RUN_MODE:-}" == "agent" ]]; then
    if [[ "${SKIP_DEP_CHECK:-false}" == true && "${ACCEPT_MISSING_DEPS_RISK:-false}" == true ]]; then
        : # full override pair present — fall through
    elif [[ "${_RUN_CHAIN_PREINSTALL:-false}" == true && -n "${COORDINATOR_CHAIN_PREINSTALL_CONSENT:-}" ]]; then
        : # chain-preinstall phase inside a consented chain walk — fall through.
          # The consent token is the same trust altitude as the override pair (a deliberate
          # redirect-guard escape, not a capability token). agent-install-contract.md § chain-preinstall.
    else
        echo "AGENT_MANIFEST_PATH=docs/install/AGENT.md" >&2
        echo "[setup] Agent-direct invocation detected. Use /deep-research:setup instead." >&2
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
# gate above passed (or in non-agent mode). deep-research-claude is a pure
# coordinator-plugin with no script-install body, so chain-preinstall is a
# no-op here — it still routes THROUGH the gate above (phase-level gate,
# uniform across legs), then exits 0. NOT in the read-only carve-out.
# ---------------------------------------------------------------------------
if [[ "${_RUN_CHAIN_PREINSTALL:-false}" == true ]]; then
    echo "deep-research-claude: chain step 4 of 5 — nothing to preinstall (chain-preinstall no-op body; pure-plugin, no script-install). Capability install happens at downstream heavy-install legs."
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
# Mirrors coordinator/scripts/setup.sh _co_pf_emit_row — byte-identical logic;
# DR does not inherit coordinator's setup.sh functions at runtime, so this is
# a local copy scoped to the --preflight block.
#
# Requires: ${_PYTHON} set in caller scope (used for NDJSON re-emission).
# Spec backlink: docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md §C3
# ---------------------------------------------------------------------------
_co_pf_emit_row() {
    local _id="$1"
    local _status="$2"
    local _severity="$3"
    local _hint="$4"

    # Human-readable table row — ALL to stderr so stdout is pure NDJSON.
    case "${_status}" in
        pass|present)
            printf '  %-7s %-20s (%s)\n' "[PASS]" "${_id}" "${_severity}" >&2
            ;;
        warn|present-but-broken)
            if [[ "${_severity}" == "semi-hard" ]]; then
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
    # Normalise dep-probe statuses to the prereq_probe vocabulary:
    # present→pass, missing→fail, present-but-broken→warn.
    # Re-emit via Python for proper JSON escaping (handles backslash/quote in hints).
    local _ndjson_status="${_status}"
    case "${_status}" in
        present)            _ndjson_status="pass" ;;
        missing)            _ndjson_status="fail" ;;
        present-but-broken) _ndjson_status="warn" ;;
    esac
    "${_PYTHON}" -c "
import json, sys
row = {'id': sys.argv[1], 'status': sys.argv[2], 'severity': sys.argv[3], 'hint': sys.argv[4]}
print(json.dumps(row, ensure_ascii=False))
" "${_id}" "${_ndjson_status}" "${_severity}" "${_hint}"
}

# ---------------------------------------------------------------------------
# --preflight mode: unified dep + environment-prerequisite probe.
#
# SUPERSET of --check: runs the existing manifest-dep probes AND the machine-
# environment probes from the vendored prereq_probe.sh through ONE tabling +
# NDJSON code path. Does NOT write install-status or any persistent state.
#
# stdout contract:
#   --check    emits human-readable rows to stdout (readable without a parser).
#   --preflight emits pure NDJSON to stdout (one compact JSON object per row);
#               all human-readable output goes to stderr so stdout is machine-
#               parseable by the chain-walker and install-health scripts.
#
# Exit-code gate (severity-aware):
#   NON-ZERO only when status=fail AND severity=hard (exit 1).
#   status=warn/fail with severity=advisory: WARN row, exit 0.
#   status=warn/fail with severity=semi-hard and no --accept-no-git-auth: exit 94.
#   inconclusive: INCONCLUSIVE row, does not fail.
#
# Lib-dir override (CRITICAL — the Staff Engineer P0-2):
#   prereq_probe.sh self-sources its siblings (manifest_reader.sh,
#   step_zero_emit.sh) from its own dir by generic name. Under this nested
#   subdir layout the cwd-marker and git-toplevel fallbacks look for
#   scripts/lib/prereq_probe.sh — not lib/coordinator_prereq/ — and hard-exit.
#   Exporting COORDINATOR_PREREQ_PROBE_LIB_DIR before source overrides that
#   resolution so the probe finds its siblings at the correct isolated subdir.
#
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check --preflight
# Spec backlink: docs/plans/2026-06-23-deep-research-install-parity-with-coordinator.md §C3
# ---------------------------------------------------------------------------
if [[ "${PREFLIGHT_FLAG}" == true ]]; then
    # All human-readable output goes to stderr so stdout is pure NDJSON.
    echo "==========================================================" >&2
    echo "  ${_CHAIN_BANNER}" >&2
    echo "==========================================================" >&2
    echo "  repo:         deep-research-claude" >&2
    echo "  repo_root:    ${REPO_ROOT}" >&2
    echo "  mode:         --preflight (read-only; dep probes + env prereq probes)" >&2
    echo "" >&2

    # ---------------------------------------------------------------------------
    # Python discovery (required for manifest read and dep probes).
    # Run prereq probes first (no python needed for env probes) so the python
    # probe row appears in output even when Python is absent.
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
        if ! _MANIFEST_PATH="$(_co_resolve_manifest_path "${REPO_ROOT}" 2>/dev/null)"; then
            echo "" >&2
            echo "  ${_CHAIN_BANNER}: no manifest found — skipping dep probes." >&2
        fi
    fi

    # Unified table state.
    _PF_HARD_FAIL=false
    _PF_SEMIHARD_FAIL=false

    # ---------------------------------------------------------------------------
    # Part 0: harness capability probes (DR-authored dr_capability_probe.sh).
    # Runs FIRST — env-only ordering so agent_teams reports even without Python.
    # Sourcing is standalone: dr_capability_probe.sh self-sources step_zero_emit.sh.
    # ---------------------------------------------------------------------------
    echo "  --- harness capability probes ---" >&2
    # shellcheck source=scripts/lib/dr_capability_probe.sh
    source "${_LIB_DIR}/dr_capability_probe.sh"

    while IFS= read -r _cap_line; do
        [[ -z "${_cap_line}" ]] && continue

        if [[ "${_PYTHON_AVAILABLE}" == true ]]; then
            _cap_name="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('name',''))" "${_cap_line}" 2>/dev/null)"
            _cap_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_cap_line}" 2>/dev/null)"
            _cap_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_cap_line}" 2>/dev/null)"
            _cap_detail="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('detail',''))" "${_cap_line}" 2>/dev/null)"
            _cap_remediation="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('remediation',''))" "${_cap_line}" 2>/dev/null)"

            # Build hint: detail + remediation (both may be empty).
            _cap_hint="${_cap_detail}"
            if [[ -n "${_cap_remediation}" ]]; then
                if [[ -n "${_cap_hint}" ]]; then
                    _cap_hint="${_cap_hint} | Remediation: ${_cap_remediation}"
                else
                    _cap_hint="Remediation: ${_cap_remediation}"
                fi
            fi

            _co_pf_emit_row "${_cap_name}" "${_cap_status}" "${_cap_severity}" "${_cap_hint}"
        else
            # Python absent: pass raw NDJSON directly to stdout; print minimal
            # human-readable row to stderr using awk for field extraction.
            printf '%s\n' "${_cap_line}"
            _cap_name_raw="$(printf '%s' "${_cap_line}" | awk -F'"name":"' '{print $2}' | awk -F'"' '{print $1}')"
            _cap_status_raw="$(printf '%s' "${_cap_line}" | awk -F'"status":"' '{print $2}' | awk -F'"' '{print $1}')"
            _cap_severity_raw="$(printf '%s' "${_cap_line}" | awk -F'"severity":"' '{print $2}' | awk -F'"' '{print $1}')"
            _cap_status_upper="$(printf '%s' "${_cap_status_raw}" | tr '[:lower:]' '[:upper:]')"
            printf '  [%-4s] %-20s (%s)\n' "${_cap_status_upper}" "${_cap_name_raw}" "${_cap_severity_raw}" >&2
            if [[ "${_cap_status_raw}" == "fail" && "${_cap_severity_raw}" == "hard" ]]; then
                _PF_HARD_FAIL=true
            fi
            if [[ ( "${_cap_status_raw}" == "warn" || "${_cap_status_raw}" == "fail" ) && "${_cap_severity_raw}" == "semi-hard" ]]; then
                _PF_SEMIHARD_FAIL=true
            fi
        fi
    done < <(_dr_cap_probe_all)

    echo "" >&2

    # ---------------------------------------------------------------------------
    # Part 1: environment-prerequisite probes (vendored prereq_probe.sh).
    # The `ue` (UnrealEditor) row is filtered from display — irrelevant to a
    # research plugin. Filter at the DR tabler; vendored prereq_probe.sh is
    # not edited (byte-identity must hold).
    #
    # Export COORDINATOR_PREREQ_PROBE_LIB_DIR so prereq_probe.sh resolves its
    # siblings (manifest_reader.sh, step_zero_emit.sh) from the correct isolated
    # subdir rather than from the generic cwd-marker / git-toplevel fallbacks
    # that look for scripts/lib/prereq_probe.sh (wrong path in nested layout).
    # ---------------------------------------------------------------------------
    echo "  --- environment prerequisite probes ---" >&2
    export COORDINATOR_PREREQ_PROBE_LIB_DIR="${_LIB_DIR}/coordinator_prereq"
    # shellcheck source=scripts/lib/coordinator_prereq/prereq_probe.sh
    source "${_LIB_DIR}/coordinator_prereq/prereq_probe.sh"

    while IFS= read -r _prereq_line; do
        [[ -z "${_prereq_line}" ]] && continue

        if [[ "${_PYTHON_AVAILABLE}" == true ]]; then
            _pr_name="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('name',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_detail="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('detail',''))" "${_prereq_line}" 2>/dev/null)"
            _pr_remediation="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('remediation',''))" "${_prereq_line}" 2>/dev/null)"

            # Filter the advisory `ue` row — UnrealEditor is irrelevant to the
            # research plugin; skip display and NDJSON emission for this row.
            [[ "${_pr_name}" == "ue" ]] && continue

            # Build hint: detail + remediation (both may be empty).
            _pr_hint="${_pr_detail}"
            if [[ -n "${_pr_remediation}" ]]; then
                if [[ -n "${_pr_hint}" ]]; then
                    _pr_hint="${_pr_hint} | Remediation: ${_pr_remediation}"
                else
                    _pr_hint="Remediation: ${_pr_remediation}"
                fi
            fi

            _co_pf_emit_row "${_pr_name}" "${_pr_status}" "${_pr_severity}" "${_pr_hint}"
        else
            # Python absent: pass raw NDJSON from prereq_probe_all directly to stdout;
            # print minimal human-readable row to stderr using awk for field extraction.
            _pr_name_raw="$(printf '%s' "${_prereq_line}" | awk -F'"name":"' '{print $2}' | awk -F'"' '{print $1}')"
            # Filter the advisory `ue` row in no-python path as well.
            [[ "${_pr_name_raw}" == "ue" ]] && continue
            printf '%s\n' "${_prereq_line}"
            _pr_status_raw="$(printf '%s' "${_prereq_line}" | awk -F'"status":"' '{print $2}' | awk -F'"' '{print $1}')"
            _pr_severity_raw="$(printf '%s' "${_prereq_line}" | awk -F'"severity":"' '{print $2}' | awk -F'"' '{print $1}')"
            _pr_status_upper="$(printf '%s' "${_pr_status_raw}" | tr '[:lower:]' '[:upper:]')"
            printf '  [%-4s] %-20s (%s)\n' "${_pr_status_upper}" "${_pr_name_raw}" "${_pr_severity_raw}" >&2
            if [[ "${_pr_status_raw}" == "fail" && "${_pr_severity_raw}" == "hard" ]]; then
                _PF_HARD_FAIL=true
            fi
            if [[ ( "${_pr_status_raw}" == "warn" || "${_pr_status_raw}" == "fail" ) && "${_pr_severity_raw}" == "semi-hard" ]]; then
                _PF_SEMIHARD_FAIL=true
            fi
        fi
    done < <(_co_prereq_probe_all)

    echo "" >&2

    # ---------------------------------------------------------------------------
    # Part 2: manifest dep probes (same shape as --check, via _dr_dep_probe_all).
    # Skipped entirely when Python is absent.
    # ---------------------------------------------------------------------------
    echo "  --- manifest dep probes ---" >&2
    _DEP_COUNT=0
    if [[ "${_PYTHON_AVAILABLE}" == false ]]; then
        # Emit a skipped row directly as raw NDJSON (cannot use _co_pf_emit_row — it calls Python).
        printf '{"id":"manifest-deps","status":"inconclusive","severity":"advisory","hint":"skipped: no python interpreter available (required for manifest dep probes)"}\n' # verify-no-console-flash: allow — string literal in printf, not a spawn
        echo "  (manifest dep probes skipped — no python available)" >&2
    elif [[ -n "${_MANIFEST_PATH}" ]]; then
        while IFS= read -r _probe_line; do
            [[ -z "${_probe_line}" ]] && continue
            _DEP_COUNT=$(( _DEP_COUNT + 1 ))

            _dep_id="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "${_probe_line}" 2>/dev/null)"
            _dep_severity="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "${_probe_line}" 2>/dev/null)"
            _dep_status="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "${_probe_line}" 2>/dev/null)"
            _dep_hint="$("${_PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1]).get('hint',''))" "${_probe_line}" 2>/dev/null)"

            _co_pf_emit_row "${_dep_id}" "${_dep_status}" "${_dep_severity}" "${_dep_hint}"
        done < <(_dr_dep_probe_all 2>/dev/null)
    fi

    if [[ "${_DEP_COUNT}" -eq 0 && "${_PYTHON_AVAILABLE}" == true ]]; then
        echo "  (coordinator-claude soft dep — see rows above)" >&2
    fi
    echo "" >&2

    # ---------------------------------------------------------------------------
    # Exit gate (severity-aware).
    # _PF_HARD_FAIL     → exit 1 (hard probe failure)
    # _PF_SEMIHARD_FAIL → exit 94 unless --accept-no-git-auth (semi-hard unverified)
    # Otherwise         → exit 0
    # ---------------------------------------------------------------------------
    if [[ "${_PF_HARD_FAIL}" == true ]]; then
        echo "  ${_CHAIN_BANNER}: PREREQ GATE FAILED (hard probe failure — see [FAIL] rows above)." >&2
        exit 1
    elif [[ "${_PF_SEMIHARD_FAIL}" == true && "${ACCEPT_NO_GIT_AUTH:-false}" != true ]]; then
        echo "  ${_CHAIN_BANNER}: PREREQ GATE BLOCKED (semi-hard probe unverified — see [BLOCK] rows above)." >&2
        echo "  Suppress with: --accept-no-git-auth (operator override; audited to stderr)." >&2
        exit 94
    fi

    echo "  ${_CHAIN_BANNER}: preflight complete (no hard or unaccepted semi-hard failures)." >&2
    echo "==========================================================" >&2
    exit 0
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
# Read-only flags (no install-status write): --help --version --phase-list --last-status --i-am-agent --check --preflight
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
    _NDJSON="$(_co_manifest_read_ndjson "${_MANIFEST_PATH}" 2>&1)" || {
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
