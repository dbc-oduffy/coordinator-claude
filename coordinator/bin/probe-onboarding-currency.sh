#!/usr/bin/env bash
# probe-onboarding-currency.sh — P-13 drift probe: onboarding currency check.
#
# Purpose: compare a repo's onboarded COORDINATOR_SCHEMA_VERSION stamp against
# the coordinator source's current schema version. Returns one of four statuses:
#
#   current              — stamp present, matches current schema version
#   drift(N->M)          — stamp present, older than current version
#   unstamped(legacy)    — probe ran OK, no stamp found; repo predates currency feature
#   inconclusive(...)    — probe could not run (schema constant unreadable, etc.)
#
# source_is_live handling: on a machine where the live install IS the source
# (COORDINATOR_CURRENCY_SOURCE_IS_LIVE=1, or auto-detected), a missing stamp is
# expected — not a warning. The probe exits 0 with status "source_is_live" (skipped).
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1.
# Doctrine: docs/wiki/doctor-probe-design.md § inconclusive Is a First-Class Probe Status.
#
# Implementation note: classification is fully delegated to
# lib/coordinator-currency.sh::coordinator_currency_probe — no local parse/classify
# logic. Seam fixed 2026-05-29 (W1-B seam reconciliation): prior version read the
# wrong stamp path (${CLAUDE_HOME}/coordinator-currency.yaml, missing docs/ subdir)
# and reimplemented classification independently, diverging from the W1-A contract.
#
# Environment:
#   CLAUDE_HOME                          — repo root to check (default: ~/.claude)
#   COORDINATOR_CURRENCY_SOURCE_IS_LIVE  — set to 1 to treat missing stamp as expected
#   COORDINATOR_CURRENCY_PLUGIN_ROOT     — override coordinator plugin root
#                                          (default: auto-resolved as parent of bin/)
#
# Outputs (stdout):
#   One of: current | drift(N->M) | unstamped(legacy) | inconclusive(<reason>)
#           source_is_live (expected-unstamped skip)
#
# Exit codes:
#   0 — probe ran and produced a classification (always, per coordinator_currency_probe contract)

set -uo pipefail

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# plugin_root: the coordinator plugin dir containing coordinator-schema-version.
# Defaults to the parent of bin/ (i.e., .../coordinator/).
# Tests override via COORDINATOR_CURRENCY_PLUGIN_ROOT to point at a sandbox
# plugin structure without affecting any other env surface.
_plugin_root="${COORDINATOR_CURRENCY_PLUGIN_ROOT:-$(dirname "$_SCRIPT_DIR")}"

# repo_root: the project repo whose onboarding stamp we are checking.
# Defaults to CLAUDE_HOME (same as the sentinel passes).
_repo_root="${CLAUDE_HOME:-$HOME}/.claude"

# ---------------------------------------------------------------------------
# Source the authoritative currency library (W1-A)
# ---------------------------------------------------------------------------

_LIB="${_SCRIPT_DIR}/../lib/coordinator-currency.sh"
if [[ ! -f "$_LIB" ]]; then
  echo "inconclusive(probe-infra: lib/coordinator-currency.sh not found at $_LIB)" >&2
  echo "inconclusive(probe-infra: lib/coordinator-currency.sh missing)"
  exit 0
fi
# shellcheck source=../lib/coordinator-currency.sh
source "$_LIB"

# ---------------------------------------------------------------------------
# source_is_live detection
# ---------------------------------------------------------------------------
# Auto-detect: if CLAUDE_HOME contains the coordinator plugin source tree
# (this script's own directory is inside CLAUDE_HOME/plugins/), the repo
# being checked IS the coordinator source. No stamp is expected.
_source_is_live=0
if [[ "${COORDINATOR_CURRENCY_SOURCE_IS_LIVE:-0}" == "1" ]]; then
  _source_is_live=1
else
  _chome_norm="${_repo_root%/}"
  _script_norm="${_SCRIPT_DIR%/}"
  if [[ "$_script_norm" == "${_chome_norm}/plugins"* ]]; then
    _source_is_live=1
  fi
fi

if [[ "$_source_is_live" -eq 1 ]]; then
  echo "source_is_live"
  exit 0
fi

# ---------------------------------------------------------------------------
# Delegate classification to the authoritative library function
# ---------------------------------------------------------------------------

coordinator_currency_probe "$_repo_root" "$_plugin_root"
exit 0
