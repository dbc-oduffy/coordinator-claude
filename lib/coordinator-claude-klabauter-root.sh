#!/usr/bin/env bash
# coordinator-claude-klabauter-root.sh — CLAUDE_KLABAUTER_ROOT resolver primitive.
#
# Purpose: resolves the claude-klabauter sibling-repo root, analogous to how
# CLAUDE_HOME→~/.claude works for the coordinator meta-repo. Exposes a
# single public function: coordinator_claude_klabauter_root.
#
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § C1 / AC1
#
# Resolution chain (outer), in order:
#   1. CLAUDE_KLABAUTER_ROOT env var — if already set, return it unchanged.
#      The guard is [[ -n "${CLAUDE_KLABAUTER_ROOT:-}" ]] per machine-local-registry.md §4b
#      so a script that derives+exports CLAUDE_KLABAUTER_ROOT does not re-resolve.
#   1.5. <settings-home>/machine-local/.claude-klabauter-root pointer file — a cheap
#      direct-file-read, checked ahead of the expensive machine-local
#      subprocess ladder so per-invoke resolution spawns zero bash subprocesses
#      on Windows. No subprocess spawn (bash builtin `$(<file)` read only).
#      Falls through to rung 2 if absent/empty.
#      Spec backlink: docs/plans/2026-07-14-claude-klabauter-windows-portability.md § C1
#   2. machine-local get repos.claude_klabauter — delegates to the §4c four-rung
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
#   coordinator_claude_klabauter_root          — prints resolved path to stdout; returns 0 on
#                                      success, 1 on failure (stderr carries remediation).
#
# Usage (source mode):
#   source "$PLUGIN_ROOT/lib/coordinator-claude-klabauter-root.sh"
#   claude_klabauter_root=$(coordinator_claude_klabauter_root) || exit 1
#
# Idempotency: sourcing this file multiple times is a no-op. All names are
# prefixed with coordinator_claude_klabauter_ to avoid collision with caller state.

# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly instead.
set -uo pipefail

# ---------------------------------------------------------------------------
# Public: coordinator_claude_klabauter_root
# ---------------------------------------------------------------------------
# Resolves the claude-klabauter sibling-repo root via the documented chain.
# Prints the resolved absolute path to stdout.
# Returns 0 on success, 1 on failure (remediation message written to stderr).
#
# Side-effect on success: exports CLAUDE_KLABAUTER_ROOT so subsequent calls within the
# same process hit the §4b guard and skip re-resolution, avoiding inadvertent
# clobber of a MACHINE_LOCAL_REPOS_CLAUDE_KLABAUTER_REPO env override a parent set.
Coordinator_claude_klabauter_root() {
  # Rung 1: CLAUDE_KLABAUTER_ROOT already set in environment (§4b idempotency gate).
  # Use "${CLAUDE_KLABAUTER_ROOT:-}" so an unset variable is treated as empty without
  # triggering nounset (-u) errors.
  if [[ -n "${CLAUDE_KLABAUTER_ROOT:-}" ]]; then
    printf '%s' "$CLAUDE_KLABAUTER_ROOT"
    return 0
  fi

  # Rung 1.5 (NEW): cheap direct-file-read pointer, checked ahead of the
  # expensive machine-local subprocess ladder below. On Windows this avoids
  # spawning bash for the per-invoke resolution hot path (fleet-wide
  # hook-latency fix). Writer follows reader: the install surface is expected
  # to write <settings-home>/machine-local/.claude-klabauter-root; absence here is a
  # normal fallback state, not an error.
  #
  # Spec backlink: docs/plans/2026-07-14-claude-klabauter-windows-portability.md § C1
  #
  # Negative-spec: does NOT spawn a subprocess (no `cat`, no external command) —
  # uses the bash builtin `$(<file)` construct so this rung is a plain read.
  # Settings-home resolution inlined directly (matches lib/settings_home.py's
  # settings_home() — 2026-07-19 debash campaign chunk E3-e retired the
  # sourced-lib shape this rung used to source, and the inline form keeps
  # this rung's "no subprocess spawn" negative-spec intact: COORDINATOR_SETTINGS_HOME
  # override, else <home>/.coordinator-claude-settings).
  #
  # The home fall-back carries a USERPROFILE rung because HOME is a POSIX
  # convention native Windows shells do not set; without it this rung built
  # "/.coordinator-claude-settings" and probed a DRIVE-ROOT path. That was inert
  # only by luck — anything landing a machine-local/.claude-klabauter-root there would have
  # been returned as CLAUDE_KLABAUTER_ROOT with no diagnostic. When no home resolves at all
  # the rung is skipped outright rather than probed at the drive root.
  local _cmr_settings_home _cmr_ptr _cmr_home
  if [[ -n "${COORDINATOR_SETTINGS_HOME:-}" ]]; then
    _cmr_settings_home="$COORDINATOR_SETTINGS_HOME"
  else
    _cmr_home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
    _cmr_settings_home="${_cmr_home:+${_cmr_home}/.coordinator-claude-settings}"
  fi
  _cmr_ptr="${_cmr_settings_home:+${_cmr_settings_home}/machine-local/.claude-klabauter-root}"
  if [[ -n "$_cmr_ptr" && -f "$_cmr_ptr" ]]; then
    local _cmr_val
    _cmr_val="$(<"$_cmr_ptr")"
    # Strip surrounding whitespace (readers strip per the pointer-file contract).
    _cmr_val="${_cmr_val#"${_cmr_val%%[![:space:]]*}"}"
    _cmr_val="${_cmr_val%"${_cmr_val##*[![:space:]]}"}"
    if [[ -n "$_cmr_val" ]]; then
      printf '%s' "$_cmr_val"
      return 0
    fi
  fi

  # Rung 2: machine-local registry (§4c four-rung discovery ladder runs inside).
  # Capture output + exit code separately so a missing key (rc=1) vs an
  # operational reader failure (rc=2) can both be caught and fail loud.
  local _resolved _ml_rc
  _resolved=$(machine-local get repos.claude_klabauter 2>/dev/null) || _ml_rc=$?
  _ml_rc=${_ml_rc:-$?}   # set from subshell exit if not already set by ||

  if [[ "${_ml_rc:-0}" -eq 0 && -n "${_resolved:-}" ]]; then
    # Export so child processes and re-sourcing this lib benefit from the §4b guard.
    CLAUDE_KLABAUTER_ROOT="$_resolved"
    export CLAUDE_KLABAUTER_ROOT
    printf '%s' "$CLAUDE_KLABAUTER_ROOT"
    return 0
  fi

  # Rung 3: hard error with actionable remediation.
  {
    echo "coordinator_claude_klabauter_root: cannot resolve CLAUDE_KLABAUTER_ROOT — repos.claude_klabauter is not set."
    echo "  The machine-local registry has no 'repos.claude_klabauter' entry on this machine."
    echo "  Remediate (choose one):"
    echo "    machine-local set repos.claude_klabauter /path/to/claude-klabauter"
    echo "    Re-run /coordinator:install to populate the repos.* registry entries."
    echo "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
  } >&2
  return 1
}
