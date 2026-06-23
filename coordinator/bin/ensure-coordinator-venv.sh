#!/usr/bin/env bash
# ensure-coordinator-venv.sh — idempotently ensures a coordinator-owned Python venv
# exists with coordinator_whoami installed, and pins it via the machine-local registry.
#
# Purpose: durable fix for coordinator_whoami going unimportable after a system python
# bump. The venv is isolated from the system interpreter and survives python upgrades.
#
# Spec backlink: docs/plans/2026-06-20-whoami-durable-install-surface.md § C2 — ensure-coordinator-venv
#
# Usage:
#   ensure-coordinator-venv.sh          # create/validate venv, pin registry, print status
#   ensure-coordinator-venv.sh --check  # report-only; never mutate (for --check-only installers)
#
# Exit codes:
#   0 — healthy (ready / rebuilt) or --check mode (would-rebuild / would-write / ready)
#   1 — error (pip failure, missing base python, mutex contention)
#
# Outputs (stdout):
#   ready        — venv already healthy, no action taken (fast path)
#   rebuilt      — venv was (re)built this run, including fresh creation; pin set
#   would-rebuild  (--check only) — venv is absent or unhealthy; would rebuild
#   would-write    (--check only) — venv healthy but pin missing; would write pin
#
# Negative-spec: this script does NOT source lib/resolve-python.sh to avoid coupling
# to the peer chunk's in-flight pin-tier edit. Base python is resolved directly via
# `command -v python3 || command -v python`.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash ≥ 4 guard — must be reachable (and parseable) on bash 3.2.
# This block uses only 3.2-compatible syntax up to the version check.
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "[ensure-coordinator-venv] ERROR: bash ≥ 4 required (found bash ${BASH_VERSION})." >&2
  # Review: suppress brew remediation prose in non-interactive mode (Finding 3 — COORDINATOR_NON_INTERACTIVE)
  if [ "${COORDINATOR_NON_INTERACTIVE:-0}" != "1" ]; then
    echo "[ensure-coordinator-venv]   On macOS, install via Homebrew: brew install bash" >&2
    echo "[ensure-coordinator-venv]   Then ensure /usr/local/bin/bash (or /opt/homebrew/bin/bash) is" >&2
    echo "[ensure-coordinator-venv]   first in PATH, or invoke this script with that bash explicitly." >&2
  fi
  exit 1
fi

# ---------------------------------------------------------------------------
# Non-interactive mode flag (Finding 3 — spec deliverable)
# Suppresses interactive-only prose (brew remediation, advisory messages) when set.
# ---------------------------------------------------------------------------
# Review: COORDINATOR_NON_INTERACTIVE — suppresses interactive-only output (Finding 3)
COORDINATOR_NON_INTERACTIVE="${COORDINATOR_NON_INTERACTIVE:-0}"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
CHECK_MODE=0
for _arg in "$@"; do
  case "$_arg" in
    --check) CHECK_MODE=1 ;;
    *) echo "[ensure-coordinator-venv] unknown argument: $_arg" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# CLAUDE_HOME is a $HOME-substitute, NOT a .claude/ substitute (machine-local-registry.md §4a):
# CLAUDE_HOME=/x → the install lives at /x/.claude/. Resolve the .claude base the same way
# machine-local and claude-home do, so the venv lands alongside the rest of the install. Do NOT
# reassign CLAUDE_HOME itself (child processes apply their own §4a convention to it).
_claude_base="${CLAUDE_HOME:-$HOME}/.claude"
VENV="${_claude_base}/.coordinator-venv"
VENV_LOCK="${VENV}.lock"

# CLAUDE_PLUGIN_ROOT: prefer env var (set by skill/command invocations) over derivation
_plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WHOAMI_PKG="${_plugin_root}/whoami"

# Determine the venv python path — POSIX vs Windows.
# Branch on uname -s: MINGW/MSYS/CYGWIN → Windows-style Scripts/python.exe
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    VENV_PY="${VENV}/Scripts/python.exe"
    ;;
  *)
    VENV_PY="${VENV}/bin/python"
    ;;
esac

# ---------------------------------------------------------------------------
# Health check function
# Returns 0 if venv is healthy (executable + coordinator_whoami importable)
# ---------------------------------------------------------------------------
_venv_healthy() {
  [[ -x "${VENV_PY}" ]] && "${VENV_PY}" -c 'import coordinator_whoami' >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Pin helper — machine-local set coordinator.python <path>
# Idempotent: only writes if the current value differs.
# ---------------------------------------------------------------------------
_set_pin() {
  local venv_py="$1"
  # Locate machine-local CLI: prefer PATH, fall back to bin-relative
  local ml_cli
  if command -v machine-local >/dev/null 2>&1; then
    ml_cli="machine-local"
  elif [[ -x "$(dirname "${BASH_SOURCE[0]}")/machine-local" ]]; then
    ml_cli="$(dirname "${BASH_SOURCE[0]}")/machine-local"
  else
    echo "[ensure-coordinator-venv] WARNING: machine-local CLI not found; coordinator venv built but pin not persisted." >&2
    echo "[ensure-coordinator-venv]   Set COORDINATOR_PYTHON=${venv_py} or re-run after installing machine-local." >&2
    return 0  # graceful degradation — venv is usable via COORDINATOR_PYTHON env
  fi

  # Read current pin; skip write if already correct.
  local current
  current="$("${ml_cli}" get coordinator.python 2>/dev/null || true)"
  if [[ "${current}" == "${venv_py}" ]]; then
    return 0  # already pinned correctly, idempotent
  fi
  "${ml_cli}" set coordinator.python "${venv_py}"
}

# ---------------------------------------------------------------------------
# --check mode: report health without mutating
# ---------------------------------------------------------------------------
if [[ "${CHECK_MODE}" -eq 1 ]]; then
  if _venv_healthy; then
    # Check if pin is set correctly (non-mutating — only read)
    local_ml=""
    if command -v machine-local >/dev/null 2>&1; then
      local_ml="machine-local"
    elif [[ -x "$(dirname "${BASH_SOURCE[0]}")/machine-local" ]]; then
      local_ml="$(dirname "${BASH_SOURCE[0]}")/machine-local"
    fi
    if [[ -n "${local_ml}" ]]; then
      current_pin="$("${local_ml}" get coordinator.python 2>/dev/null || true)"
      if [[ "${current_pin}" != "${VENV_PY}" ]]; then
        echo "would-write"
        exit 0
      fi
    fi
    echo "ready"
  elif [[ -d "${VENV}" ]]; then
    echo "would-rebuild"
  else
    echo "would-rebuild"
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# Default (mutate) mode
# ---------------------------------------------------------------------------

# Fast path: already healthy — emit "ready" (no action taken)
if _venv_healthy; then
  _set_pin "${VENV_PY}"
  echo "ready"
  exit 0
fi

# Need to build or rebuild. Acquire build mutex first.
# mkdir is atomic on POSIX — succeeds only if dir does not exist.
# Review: TOCTOU fix — failed mkdir path NEVER proceeds lockless (Findings 1+12).
# If lock is stale (>300s), remove and retry once. Otherwise exit non-zero.
_LOCK_ACQUIRED=0

# Review: portable mtime using date -r (Finding 10 — stat -f %m is BSD-only;
# GNU stat -f returns filesystem type, not mtime).
_stat_mtime() {
  local path="$1"
  # date -r is portable: BSD date and GNU date both support -r <file> +%s.
  date -r "$path" +%s 2>/dev/null || echo 0
}

# Ensure the .claude base dir exists before the lock/venv land in it (it may not under a
# CLAUDE_HOME sandbox / fresh install). mkdir -p is idempotent and a no-op for the real ~/.claude.
mkdir -p "${_claude_base}"

if ! mkdir "${VENV_LOCK}" 2>/dev/null; then
  # Lock already held — check age
  if [[ -d "${VENV_LOCK}" ]]; then
    _lock_mtime="$(_stat_mtime "${VENV_LOCK}")"
    _now="$(date +%s)"
    _age=$(( _now - _lock_mtime ))
    if [[ "${_age}" -gt 300 ]]; then
      # Stale lock — remove and retry once
      rm -rf "${VENV_LOCK}"
      if ! mkdir "${VENV_LOCK}" 2>/dev/null; then
        # Another concurrent session grabbed the lock during our window
        echo "[ensure-coordinator-venv] another session is rebuilding the coordinator venv; retry in a moment" >&2
        exit 1
      fi
      _LOCK_ACQUIRED=1
    else
      # Lock is fresh — another session is actively building; back off
      echo "[ensure-coordinator-venv] another session is rebuilding the coordinator venv; retry in a moment" >&2
      exit 1
    fi
  else
    # Lock dir does not exist at all (race: mkdir failed but dir is gone).
    # This can only happen if another session acquired and released the lock
    # extremely rapidly — in which case the venv should now be healthy.
    # Do NOT proceed lockless. Re-check health and exit appropriately.
    if _venv_healthy; then
      _set_pin "${VENV_PY}"
      echo "ready"
      exit 0
    fi
    # Still not healthy and no lock to acquire; treat as contention.
    echo "[ensure-coordinator-venv] another session is rebuilding the coordinator venv; retry in a moment" >&2
    exit 1
  fi
else
  _LOCK_ACQUIRED=1
fi

# _LOCK_ACQUIRED is always 1 here — the only paths that reach this point have the lock.

# Register trap to release lock on any exit.
# Review: gate lock-removal on _LOCK_ACQUIRED (Finding 2 — prevents destroying
# a concurrent session's mutex when trap fires without lock ownership).
trap 'rm -f "${_pip_stderr_file:-}"; [[ "${_LOCK_ACQUIRED}" -eq 1 ]] && { rmdir "${VENV_LOCK}" 2>/dev/null || rm -rf "${VENV_LOCK}"; }' EXIT

# Re-check health after acquiring lock (another session may have built it while we waited)
if _venv_healthy; then
  _set_pin "${VENV_PY}"
  echo "ready"
  exit 0
fi

# Remove any partial/broken venv
if [[ -d "${VENV}" ]]; then
  rm -rf "${VENV}"
fi

# Resolve base python
BASE_PY=""
if command -v python3 >/dev/null 2>&1; then
  BASE_PY="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  BASE_PY="$(command -v python)"
else
  echo "[ensure-coordinator-venv] ERROR: no python3 or python found in PATH." >&2
  echo "[ensure-coordinator-venv]   Install Python 3.10+ and ensure it is on PATH." >&2
  exit 1
fi

# Create venv
"${BASE_PY}" -m venv "${VENV}"

# Install whoami package editable
_pip_stderr_file="$(mktemp -t coordinator-venv-pip-err.XXXXXX)"
# Note: the EXIT trap above now handles both _pip_stderr_file cleanup and lock release.

_pip_exit=0
"${VENV_PY}" -m pip install -e "${WHOAMI_PKG}/" 2>"${_pip_stderr_file}" || _pip_exit=$?

if [[ "${_pip_exit}" -ne 0 ]]; then
  _pip_stderr_content="$(cat "${_pip_stderr_file}" 2>/dev/null || true)"
  # Remove partial venv before exit
  rm -rf "${VENV}"
  # Classify failure: network vs generic
  # Review: use printf to avoid echo interpreting escape sequences (Finding 14)
  if printf '%s\n' "${_pip_stderr_content}" | grep -qiE \
      'Could not find a version|ConnectionError|TimeoutError|Temporary failure in name resolution|Network is unreachable|Failed to establish a new connection'; then
    echo "[ensure-coordinator-venv] coordinator venv rebuild failed — pip could not reach PyPI (check network/proxy)." >&2
    echo "[ensure-coordinator-venv]   The venv needs PyPI access for jsonschema." >&2
    echo "[ensure-coordinator-venv]   Re-run ensure-coordinator-venv.sh once online." >&2
  else
    echo "[ensure-coordinator-venv] ERROR: pip install failed (exit ${_pip_exit})." >&2
    # Print tail of stderr for diagnostics
    printf '%s\n' "${_pip_stderr_content}" | tail -20 >&2
  fi
  echo "failed (pip exit ${_pip_exit})" >&2
  exit 1
fi

# Pin the venv python in the machine-local registry
_set_pin "${VENV_PY}"

# Review: emit "rebuilt" for BOTH rebuild-from-broken AND fresh-create (Finding 5).
# "ready" is reserved for the fast-path healthy no-op above.
# Both paths reaching here represent work done this run.
echo "rebuilt"

exit 0
