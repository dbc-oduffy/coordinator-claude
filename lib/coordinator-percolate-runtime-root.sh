#!/usr/bin/env bash
# coordinator-percolate-runtime-root.sh — PERCOLATE_ROOT resolver primitive.
#
# Purpose: resolves the percolate runtime root — the directory that CONTAINS
# setup/publish.sh — analogous to how coordinator-doe-root.sh resolves
# REPO_DOE_CLAUDE. Exposes a single public function: coordinator_percolate_runtime_root.
#
# Resolution chain, in order (first match wins):
#   1. $COORDINATOR_PERCOLATE_ROOT — explicit override, if it points at a
#      directory containing setup/publish.sh.
#   2. mode 2 (repo-local): the cwd's git root, if it contains setup/publish.sh.
#      Git root via: git rev-parse --show-toplevel 2>/dev/null
#   3. mode 3 (shared install): "${CLAUDE_HOME:-$HOME}/.claude", if it
#      contains setup/publish.sh.
#   4. Hard error + actionable remediation message on stderr.
#
# PERCOLATE_ROOT is the directory that CONTAINS setup/publish.sh (not the
# setup/ directory itself).
#
# Cross-platform: bash ≥3.2 compatible, no bash-4-only features used;
# no GNU-isms (sed -i, grep -P, date -d, realpath). Safe to source multiple times.
#
# Public API:
#   coordinator_percolate_runtime_root — prints resolved path to stdout; returns 0
#                                        on success, 1 on failure (stderr carries
#                                        remediation). Exports PERCOLATE_ROOT on
#                                        success.
#
# Usage (source mode):
#   source "$PLUGIN_ROOT/lib/coordinator-percolate-runtime-root.sh"
#   percolate_root=$(coordinator_percolate_runtime_root) || exit 1
#
# Idempotency: sourcing this file multiple times is a no-op. All names are
# prefixed with coordinator_percolate_ to avoid collision with caller state.

# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly instead. Mirrors coordinator-doe-root.sh convention.
# NOTE: set -u and set -o pipefail (below) also propagate to any script that
# sources this lib — callers must be nounset-clean and handle pipeline exits.
set -uo pipefail

# ---------------------------------------------------------------------------
# Public: coordinator_percolate_runtime_root
# ---------------------------------------------------------------------------
# Resolves PERCOLATE_ROOT via the documented four-rung chain.
# Prints the resolved absolute path to stdout.
# Returns 0 on success, 1 on failure (remediation message written to stderr).
#
# Side-effect on success: exports PERCOLATE_ROOT so subsequent calls within
# the same process short-circuit via a direct check, avoiding re-resolution.
coordinator_percolate_runtime_root() {
  # Rung 1: $COORDINATOR_PERCOLATE_ROOT explicit override.
  # Use "${COORDINATOR_PERCOLATE_ROOT:-}" so an unset variable is treated as
  # empty without triggering nounset (-u) errors.
  if [[ -n "${COORDINATOR_PERCOLATE_ROOT:-}" && -f "${COORDINATOR_PERCOLATE_ROOT}/setup/publish.sh" ]]; then
    PERCOLATE_ROOT="$COORDINATOR_PERCOLATE_ROOT"
    export PERCOLATE_ROOT
    printf '%s' "$PERCOLATE_ROOT"
    return 0
  fi

  # Rung 2: repo-local mode — the cwd's git root, if it carries setup/publish.sh.
  local _git_root
  _git_root=$(git rev-parse --show-toplevel 2>/dev/null)
  if [[ -n "$_git_root" && -f "${_git_root}/setup/publish.sh" ]]; then
    PERCOLATE_ROOT="$_git_root"
    export PERCOLATE_ROOT
    printf '%s' "$PERCOLATE_ROOT"
    return 0
  fi

  # Rung 3: shared-install mode — "${CLAUDE_HOME:-$HOME}/.claude".
  local _claude_home
  _claude_home="${CLAUDE_HOME:-$HOME}/.claude"
  if [[ -f "${_claude_home}/setup/publish.sh" ]]; then
    PERCOLATE_ROOT="$_claude_home"
    export PERCOLATE_ROOT
    printf '%s' "$PERCOLATE_ROOT"
    return 0
  fi

  # Rung 4: hard error with actionable remediation.
  {
    echo "coordinator_percolate_runtime_root: cannot resolve PERCOLATE_ROOT."
    echo "  None of the following resolved to a directory containing setup/publish.sh:"
    echo "    1. \$COORDINATOR_PERCOLATE_ROOT (${COORDINATOR_PERCOLATE_ROOT:-<unset>})"
    echo "    2. cwd git root (${_git_root:-<not a git repo>})"
    echo "    3. shared install (${_claude_home})"
    echo "  Remediate (choose one):"
    echo "    export COORDINATOR_PERCOLATE_ROOT=/path/to/percolate-root"
    echo "    Run from within a repo-local clone that has setup/publish.sh at its root."
    echo "    Install setup/publish.sh under \${CLAUDE_HOME:-\$HOME}/.claude."
  } >&2
  return 1
}
