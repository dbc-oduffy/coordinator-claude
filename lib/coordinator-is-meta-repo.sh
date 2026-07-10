#!/usr/bin/env bash
# coordinator-is-meta-repo.sh — canonical boolean primitive: is cwd's git root the meta-repo?
#
# Purpose: single definition of "is the current (or given) git repository the
# coordinator meta-repo (~/.claude / CLAUDE_HOME)?"  Replaces three diverging
# hardcoded $HOME/.claude compares scattered across bin/lib scripts.
#
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C2 / AC2
#
# Design:
#   - CLAUDE_HOME-aware: resolves meta-repo root via the canonical claude-home dir
#     resolver (machine-local-registry.md §4a) — honours CLAUDE_HOME overrides for
#     test sandboxes and CI.
#   - Canonicalized: both sides go through `cd && pwd -P` (BSD-portable; no GNU
#     realpath) before `==` to survive symlinked paths and /c/ vs C:\ mismatches.
#   - Fail-loud: returns 2 + remediation message on stderr when git root is empty
#     or unresolvable (detect-then-fail-loud, not detect-then-silently-pick).
#
# Public API (source this file, then call):
#   coordinator_is_meta_repo [<git-root>]
#     Returns 0 (true)  — <git-root> (or cwd's git root when omitted) IS the meta-repo.
#     Returns 1 (false) — it is NOT the meta-repo.
#     Returns 2 (error) — git root unresolvable OR detection itself failed; see stderr.
#
# Negative-spec:
#   - Does NOT modify any global variables.
#   - Does NOT call coordinator_example_orchestration_hub_root — purely about meta-repo identity.
#   - Does NOT use GNU realpath — uses cd/pwd -P for BSD-portable canonicalization.
#   - Does NOT define any file-scope state (safe to source multiple times without side-effects).
#
# Cross-platform: bash ≥3.2+ compatible (no bash-4-only features used).
# Safe to source multiple times (all names are function-local; no readonly globals).

# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly instead. Mirrors coordinator-example-orchestration-hub-root.sh convention.
set -uo pipefail

# ---------------------------------------------------------------------------
# Public: coordinator_is_meta_repo [<git-root>]
# ---------------------------------------------------------------------------
coordinator_is_meta_repo() {
  local _cimr_git_root="${1:-}"

  # Resolve git root from cwd if not provided by caller.
  if [[ -z "$_cimr_git_root" ]]; then
    _cimr_git_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
      {
        echo "coordinator_is_meta_repo: git rev-parse --show-toplevel failed — not in a git repository?"
        echo "  Remediation: run from within a git repository, or pass the git root as the first argument."
      } >&2
      return 2
    }
    if [[ -z "$_cimr_git_root" ]]; then
      {
        echo "coordinator_is_meta_repo: git rev-parse --show-toplevel returned empty — not in a git repository?"
        echo "  Remediation: run from within a git repository, or pass the git root as the first argument."
      } >&2
      return 2
    fi
  fi

  # Resolve this lib's directory from BASH_SOURCE[0] — points to the defining file
  # even when the function is called from another script.  Stable across sourcing callers.
  local _cimr_lib_dir
  _cimr_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || {
    echo "coordinator_is_meta_repo: cannot resolve own lib dir via BASH_SOURCE" >&2
    return 2
  }

  # Resolve meta-repo root via the canonical claude-home dir resolver (§4a).
  # Honours CLAUDE_HOME overrides — test sandboxes set CLAUDE_HOME to a fake home.
  local _cimr_claude_home_bin="${_cimr_lib_dir}/claude-home/claude-home"
  local _cimr_meta_root
  _cimr_meta_root="$("${_cimr_claude_home_bin}" dir 2>/dev/null)" || {
    {
      echo "coordinator_is_meta_repo: claude-home dir failed to resolve meta-repo root."
      echo "  Remediation: ensure ${_cimr_lib_dir}/claude-home/claude-home is present"
      echo "  and python3 is available on PATH."
    } >&2
    return 2
  }
  if [[ -z "$_cimr_meta_root" ]]; then
    echo "coordinator_is_meta_repo: claude-home dir returned empty — check CLAUDE_HOME / HOME." >&2
    return 2
  fi

  # Canonicalize both sides (BSD-portable: cd + pwd -P resolves symlinks; no GNU realpath).
  # Fallback to literal path if the directory does not exist on disk.
  local _cimr_canon_git _cimr_canon_meta
  _cimr_canon_git="$(cd "$_cimr_git_root"  2>/dev/null && pwd -P || echo "$_cimr_git_root")"
  _cimr_canon_meta="$(cd "$_cimr_meta_root" 2>/dev/null && pwd -P || echo "$_cimr_meta_root")"

  [[ "$_cimr_canon_git" == "$_cimr_canon_meta" ]]
}
