#!/usr/bin/env bash
# setup-fnm-pin.sh — repo-setup-time fnm pin resolution for coordinator repo-setup.
#
# Purpose: if the target repo has a .node-version or .nvmrc pin file, install the
# pinned Node version via fnm and emit activation guidance for bare shells.
# This is PIN RESOLUTION ONLY — it does not install the fnm binary; that is owned
# by coordinator:install (a separate chunk). If fnm is absent, fails loud with
# actionable remediation.
#
# Usage:
#   bash setup-fnm-pin.sh [<repo-root>]
#
#   <repo-root>  — optional; directory containing the repo (default: cwd).
#
# Env seams (injectable for tests — set these to mock fnm presence/absence):
#   COORDINATOR_FNM_CMD      — override the fnm command (default: fnm).
#                              Set to a mock script path in tests to intercept calls.
#   COORDINATOR_FNM_ABSENT   — set to "1" to simulate fnm not found (for tests).
#
# Exit codes:
#   0 — success (pin resolved, or no pin file found — both are clean exits)
#   1 — fnm absent when a pin file is present (fail loud with remediation)
#
# Contract:
#   - No pin file  → pure no-op, exits 0, zero output.
#   - Pin file + fnm present  → runs `fnm install <version>`, emits env guidance.
#   - Pin file + fnm absent   → exits 1 with remediation message on stderr.
#   - Idempotent: `fnm install` itself is idempotent; safe to call multiple times.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1d (AC6)
# Review: code-reviewer — corrected from non-existent opticon-node24-fnm-pin.md
# NOT a capability probe — does not re-implement _co_probe_node from
#   scripts/lib/prereq_probe.sh. Just `command -v fnm` for binary presence.

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash version guard — must be syntactically parseable on bash 3.2.
# This file uses no bash-4-only features, but guard is required by house style
# whenever the script may be sourced or invoked on stock macOS bash.
# Remediation: brew install bash
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'ERROR: setup-fnm-pin.sh requires bash >= 4 (found: %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS ships bash 3.2 — install a modern bash via Homebrew:\n' >&2
  printf '    brew install bash\n' >&2
  exit 78  # EX_CONFIG
fi

# ---------------------------------------------------------------------------
# Argument resolution
# ---------------------------------------------------------------------------
_REPO_ROOT="${1:-${PWD}}"

if [[ ! -d "$_REPO_ROOT" ]]; then
  printf 'setup-fnm-pin: repo root does not exist: %s\n' "$_REPO_ROOT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pin file detection — check .node-version first, then .nvmrc
# ---------------------------------------------------------------------------
_PIN_FILE=""
_PIN_VERSION=""

if [[ -f "${_REPO_ROOT}/.node-version" ]]; then
  _PIN_FILE="${_REPO_ROOT}/.node-version"
elif [[ -f "${_REPO_ROOT}/.nvmrc" ]]; then
  _PIN_FILE="${_REPO_ROOT}/.nvmrc"
fi

# No pin file — pure no-op.
if [[ -z "$_PIN_FILE" ]]; then
  exit 0
fi

# Read the pinned version (trim whitespace; BSD-portable tr + read pattern).
_PIN_VERSION="$(tr -d '[:space:]' < "$_PIN_FILE")"

if [[ -z "$_PIN_VERSION" ]]; then
  printf 'setup-fnm-pin: pin file is empty: %s\n' "$_PIN_FILE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# fnm presence check — injectable via env for tests
# ---------------------------------------------------------------------------
_FNM_CMD="${COORDINATOR_FNM_CMD:-fnm}"

_fnm_is_present() {
  # Allow test injection of absence sentinel.
  if [[ "${COORDINATOR_FNM_ABSENT:-}" == "1" ]]; then
    return 1
  fi
  # Accept either a PATH-resolvable name or an explicit path (for mocks).
  if [[ "$_FNM_CMD" == /* ]] || [[ "$_FNM_CMD" == ./* ]]; then
    [[ -x "$_FNM_CMD" ]]
  else
    command -v "$_FNM_CMD" >/dev/null 2>&1  # Review: code-reviewer — &> is non-POSIX; use portable redirect form
  fi
}

if ! _fnm_is_present; then
  printf 'setup-fnm-pin: fnm not installed — run coordinator:install to install the Node toolchain manager, then re-run repo-setup\n' >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# fnm install — idempotent; fnm install is safe to run repeatedly
# ---------------------------------------------------------------------------
printf 'setup-fnm-pin: installing Node %s via fnm (pin: %s)\n' "$_PIN_VERSION" "$_PIN_FILE"

"$_FNM_CMD" install "$_PIN_VERSION"

# ---------------------------------------------------------------------------
# Activation guidance for bare shells that do not source fnm env
# ---------------------------------------------------------------------------
printf '\n'
printf 'Node %s installed. To activate in your current shell:\n' "$_PIN_VERSION"
printf '  eval "$(fnm env)"\n'
printf '\n'
printf 'Or prepend the fnm-managed Node to PATH directly (add to your shell profile):\n'
printf '  export PATH="$HOME/.local/share/fnm/node-versions/%s/installation/bin:$PATH"\n' "$_PIN_VERSION"
printf '\n'
printf 'For bash/zsh login shells, add to ~/.bashrc or ~/.zshrc:\n'
printf '  eval "$(fnm env --use-on-cd)"\n'
