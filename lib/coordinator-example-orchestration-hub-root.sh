#!/usr/bin/env bash
# coordinator-example-orchestration-hub-root.sh — EXAMPLE_ORCHESTRATION_HUB_ROOT resolver primitive.
#
# Purpose: resolves the example-orchestration-hub sibling-repo root, analogous to how
# CLAUDE_HOME→~/.claude works for the coordinator meta-repo. Exposes a
# single public function: coordinator_example_orchestration_hub_root.
#
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C1 / AC1
#
# Resolution chain (outer), in order:
#   1. EXAMPLE_ORCHESTRATION_HUB_ROOT env var — if already set, return it unchanged.
#      The guard is [[ -n "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" ]] per machine-local-registry.md §4b
#      so a script that derives+exports EXAMPLE_ORCHESTRATION_HUB_ROOT does not re-resolve.
#   2. machine-local get repos.example_orchestration_hub_repo — delegates to the §4c four-rung
#      discovery ladder (explicit env override → OS-keyed search-root marker
#      autodiscovery → path-exceptions → registry.local.toml fallback).
#      Do NOT re-implement those rungs here; machine-local is the SSOT.
#   3. Hard error + actionable remediation message on stderr. Callers in the
#      central write loop (coordinator-lesson-promote, coordinator-queue-append)
#      wrap this function and degrade to warn+skip; the primitive itself fails loud.
#
# Cross-platform: bash ≥4 + BSD coreutils. No bash-4-specific features used;
# no GNU-isms (sed -i, grep -P, date -d, realpath). Safe to source multiple times.
#
# Public API:
#   coordinator_example_orchestration_hub_root          — prints resolved path to stdout; returns 0 on
#                                      success, 1 on failure (stderr carries remediation).
#
# Usage (source mode):
#   source "$PLUGIN_ROOT/lib/coordinator-example-orchestration-hub-root.sh"
#   example_orchestration_hub_root=$(coordinator_example_orchestration_hub_root) || exit 1
#
# Idempotency: sourcing this file multiple times is a no-op. All names are
# prefixed with coordinator_example_orchestration_hub_ to avoid collision with caller state.

# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly instead. Mirrors coordinator-currency.sh convention.
set -uo pipefail

# ---------------------------------------------------------------------------
# Public: coordinator_example_orchestration_hub_root
# ---------------------------------------------------------------------------
# Resolves the example-orchestration-hub sibling-repo root via the documented chain.
# Prints the resolved absolute path to stdout.
# Returns 0 on success, 1 on failure (remediation message written to stderr).
#
# Side-effect on success: exports EXAMPLE_ORCHESTRATION_HUB_ROOT so subsequent calls within the
# same process hit the §4b guard and skip re-resolution, avoiding inadvertent
# clobber of a MACHINE_LOCAL_REPOS_EXAMPLE_ORCHESTRATION_HUB_REPO env override a parent set.
coordinator_example_orchestration_hub_root() {
  # Rung 1: EXAMPLE_ORCHESTRATION_HUB_ROOT already set in environment (§4b idempotency gate).
  # Use "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" so an unset variable is treated as empty without
  # triggering nounset (-u) errors.
  if [[ -n "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" ]]; then
    printf '%s' "$EXAMPLE_ORCHESTRATION_HUB_ROOT"
    return 0
  fi

  # Rung 2: machine-local registry (§4c four-rung discovery ladder runs inside).
  # Capture output + exit code separately so a missing key (rc=1) vs an
  # operational reader failure (rc=2) can both be caught and fail loud.
  local _resolved _ml_rc
  _resolved=$(machine-local get repos.example_orchestration_hub_repo 2>/dev/null) || _ml_rc=$?
  _ml_rc=${_ml_rc:-$?}   # set from subshell exit if not already set by ||

  if [[ "${_ml_rc:-0}" -eq 0 && -n "${_resolved:-}" ]]; then
    # Export so child processes and re-sourcing this lib benefit from the §4b guard.
    EXAMPLE_ORCHESTRATION_HUB_ROOT="$_resolved"
    export EXAMPLE_ORCHESTRATION_HUB_ROOT
    printf '%s' "$EXAMPLE_ORCHESTRATION_HUB_ROOT"
    return 0
  fi

  # Rung 3: hard error with actionable remediation.
  {
    echo "coordinator_example_orchestration_hub_root: cannot resolve EXAMPLE_ORCHESTRATION_HUB_ROOT — repos.example_orchestration_hub_repo is not set."
    echo "  The machine-local registry has no 'repos.example_orchestration_hub_repo' entry on this machine."
    echo "  Remediate (choose one):"
    echo "    machine-local set repos.example_orchestration_hub_repo /path/to/example-orchestration-hub-repo"
    echo "    Re-run /coordinator:install to populate the repos.* registry entries."
    echo "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
  } >&2
  return 1
}
