#!/usr/bin/env bash
# coordinator-doe-root.sh — REPO_DOE_CLAUDE resolver primitive.
#
# Purpose: resolves the DoE-claude sibling-repo root, analogous to how
# EXAMPLE_ORCHESTRATION_HUB_ROOT works for the example-orchestration-hub plane. Exposes a single public function:
# coordinator_doe_root.
#
# Spec backlink: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.1
# Recast (thin caller): docs/plans/2026-07-09-resolver-unification-v3split-01.md § C3 —
# rungs 1-2 (env, repos.doe_claude registry key) are UNCHANGED; the
# former rung-2.5 pointer-file duplication is replaced by a fallback call into
# resolve-coordinator-clone.sh's shared --clone-root verb (AC8), which now
# owns the .doe-root pointer rung + the flat-layout OSS-fallback rung.
#
# Registry-namespace collision resolution (plan C6/AC9, § C6): repos.doe_claude
# and plugin.mirrors.coordinator-claude.live_path describe the SAME fact (the
# DoE-claude clone path). This is a non-destructive READ-ORDER fix, not a
# schema restructure — repos.doe_claude remains CANONICAL (rung 2, unchanged),
# and rung 2.5 below reads plugin.mirrors.coordinator-claude.live_path as a
# FALLBACK when repos.doe_claude is unset, so a machine that only set live_path
# still resolves without touching the registry schema.
#
# Resolution chain (outer), in order:
#   1. REPO_DOE_CLAUDE env var — if already set, return it unchanged.
#      The guard is [[ -n "${REPO_DOE_CLAUDE:-}" ]] per machine-local-registry.md §4b
#      so a script that derives+exports REPO_DOE_CLAUDE does not re-resolve.
#   2. machine-local get repos.doe_claude (CANONICAL) — delegates to the §4c
#      four-rung discovery ladder (explicit env override → OS-keyed search-root
#      marker autodiscovery → path-exceptions → registry.local.toml fallback).
#      Do NOT re-implement those rungs here; machine-local is the SSOT.
#   2.5. Fallback (plan C6/AC9): machine-local get plugin.mirrors.coordinator-claude.live_path
#      — only fires when rung 2 (repos.doe_claude) returned nothing. Covers a
#      machine that registered the coordinator-specific mirror key but never
#      set the general repos.doe_claude key.
#   3. Fallback: resolve-coordinator-clone.sh --clone-root (shared unified lib
#      verb — AC8). Covers the .doe-root pointer rung (`.git`-gated) and the
#      flat-layout rung. Only fires when rungs 2 and 2.5 returned nothing —
#      registry still wins when set. No independent rung reimplementation
#      remains here.
#   4. Hard error + actionable remediation message on stderr. Callers in the
#      central write loop wrap this function and degrade to warn+skip; the
#      primitive itself fails loud.
#
# Cross-platform: bash ≥3.2 compatible, no bash-4-only features used;
# no GNU-isms (sed -i, grep -P, date -d, realpath). Safe to source multiple times.
#
# Public API:
#   coordinator_doe_root             — prints resolved path to stdout; returns 0 on
#                                      success, 1 on failure (stderr carries remediation).
#
# Usage (source mode):
#   source "$PLUGIN_ROOT/lib/coordinator-doe-root.sh"
#   doe_root=$(coordinator_doe_root) || exit 1
#
# Idempotency: sourcing this file multiple times is a no-op. All names are
# prefixed with coordinator_doe_ to avoid collision with caller state.

# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly instead. Mirrors coordinator-currency.sh convention.
# NOTE: set -u and set -o pipefail (below) also propagate to any script that
# sources this lib — callers must be nounset-clean and handle pipeline exits.
set -uo pipefail

# ---------------------------------------------------------------------------
# Public: coordinator_doe_root
# ---------------------------------------------------------------------------
# Resolves the DoE-claude sibling-repo root via the documented chain.
# Prints the resolved absolute path to stdout.
# Returns 0 on success, 1 on failure (remediation message written to stderr).
#
# Side-effect on success: exports REPO_DOE_CLAUDE so subsequent calls within
# the same process hit the §4b guard and skip re-resolution, avoiding
# inadvertent clobber of a MACHINE_LOCAL_REPOS_DOE_CLAUDE env override a
# parent set.
coordinator_doe_root() {
  # Rung 1: REPO_DOE_CLAUDE already set in environment (§4b idempotency gate).
  # Use "${REPO_DOE_CLAUDE:-}" so an unset variable is treated as empty without
  # triggering nounset (-u) errors.
  if [[ -n "${REPO_DOE_CLAUDE:-}" ]]; then
    printf '%s' "$REPO_DOE_CLAUDE"
    return 0
  fi

  # Rung 2: machine-local registry (§4c four-rung discovery ladder runs inside).
  # Capture output + exit code separately so a missing key (rc=1) vs an
  # operational reader failure (rc=2) can both be caught and fail loud.
  local _resolved _ml_rc
  _resolved=$(machine-local get repos.doe_claude 2>/dev/null) || _ml_rc=$?
  _ml_rc=${_ml_rc:-$?}   # set from subshell exit if not already set by ||

  if [[ "${_ml_rc:-0}" -eq 0 && -n "${_resolved:-}" ]]; then
    # Export so child processes and re-sourcing this lib benefit from the §4b guard.
    REPO_DOE_CLAUDE="$_resolved"
    export REPO_DOE_CLAUDE
    printf '%s' "$REPO_DOE_CLAUDE"
    return 0
  fi

  # Rung 2.5: fallback to plugin.mirrors.coordinator-claude.live_path (plan
  # C6/AC9 registry-namespace collision resolution — see header comment).
  # Only fires when rung 2 (repos.doe_claude, canonical) returned nothing.
  local _resolved_fallback
  _resolved_fallback=$(machine-local get plugin.mirrors.coordinator-claude.live_path 2>/dev/null) || _resolved_fallback=""
  if [[ -n "${_resolved_fallback:-}" ]]; then
    REPO_DOE_CLAUDE="$_resolved_fallback"
    export REPO_DOE_CLAUDE
    printf '%s' "$REPO_DOE_CLAUDE"
    return 0
  fi

  # Rung 3: fallback to the unified resolver lib's --clone-root verb (AC8).
  # Only fires when rungs 2 and 2.5 above returned nothing — registry
  # still wins when set. Delegates the .doe-root pointer rung and the
  # flat-layout rung to the single shared implementation in
  # resolve-coordinator-clone.sh rather than duplicating rung logic here.
  local _fallback
  _fallback="$(bash "${BASH_SOURCE[0]%/*}/resolve-coordinator-clone.sh" --clone-root 2>/dev/null || true)"
  if [[ -n "${_fallback:-}" ]]; then
    REPO_DOE_CLAUDE="$_fallback"
    export REPO_DOE_CLAUDE
    printf '%s' "$REPO_DOE_CLAUDE"
    return 0
  fi

  # Rung 4: hard error with actionable remediation.
  {
    echo "coordinator_doe_root: cannot resolve REPO_DOE_CLAUDE — repos.doe_claude is not set."
    echo "  The machine-local registry has no 'repos.doe_claude' entry (canonical) or"
    echo "  'plugin.mirrors.coordinator-claude.live_path' entry (fallback) on this machine."
    echo "  Remediate (choose one):"
    echo "    machine-local set repos.doe_claude /path/to/DoE-claude"
    echo "    Re-run /coordinator:install to populate the repos.* registry entries."
    echo "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
  } >&2
  return 1
}
