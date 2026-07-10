#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Shared substrate: read the DoE repo root from the cold-readable pointer
# file (~/.claude/.doe-root). Neutral lib — NOT owned by resolve-coordinator-
# clone.sh; shared by any resolver rung that needs the pointer-file read.
#
# Reads ${CLAUDE_HOME:-$HOME}/.claude/.doe-root via cat — zero tool
# dependency, works cold (before any coordinator bins are on PATH, before
# machine-local is available). This is the cold-read primitive for the
# maximalist install shape.
#
# DR-148: no realpath, no GNU-isms. Bash 3.2 compatible. Idempotent to
# source (defines a single function, no top-level side effects).
#
# This lib is sourced, not executed — no 'set -e' (a sourced script's
# 'set -e' leaks into the caller's shell and changes its error-handling
# semantics). 'set -uo pipefail' is safe to source.
# ---------------------------------------------------------------------------
set -uo pipefail

# ---------------------------------------------------------------------------
# Helper: read the DoE repo root from the cold-readable pointer file.
#
# Returns the DoE repo root path (a single line) or empty if the pointer file
# is absent or unreadable. Does NOT validate whether the path exists on disk —
# callers apply the -d gate themselves (so the gate is explicit and greppable).
# ---------------------------------------------------------------------------
coordinator_read_doe_root_pointer() {
  local _home="${CLAUDE_HOME:-${HOME:-${USERPROFILE:-}}}"
  [[ -n "$_home" ]] || return 0
  local _root
  _root="$(cat "${_home}/.claude/.doe-root" 2>/dev/null || true)"
  printf '%s' "${_root}"
}
