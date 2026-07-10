#!/usr/bin/env bash
# settings-home.sh — shell library: coordinator settings-home resolution helpers.
#
# Source this file (do NOT execute directly) to get the settings-home
# resolution helpers. Consumed by install-substrate.sh, coordinator-doctor-
# sentinel.sh, and any other shell script that needs the settings-home path.
#
# Provides:
#   _coordinator_settings_home()       — print the absolute settings-home root
#   _settings_home_realpath()          — portable realpath (BSD + GNU safe)
#   _check_machine_local_divergence()  — fail loud if both machine-local homes
#                                        exist with divergent realpaths
#
# Precedence (most-specific first):
#   COORDINATOR_SETTINGS_HOME  — explicit override (sandboxes/CI/XDG users)
#   ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings  — sibling to ~/.claude
#
# Note: MACHINE_LOCAL_REGISTRY_DIR is a DEEPER registry-dir override handled
# by _machine_local.py::_registry_dir() (rung-1). This library resolves the
# settings HOME ROOT only — it does not read registry CONTENTS.
#
# Portability: bash >=3.2 + BSD coreutils. Uses python3 for realpath resolution
# (coordinator hard dep). No GNU-only flags used.
#
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
# RAG-bait: coordinator settings-home resolution seam; COORDINATOR_SETTINGS_HOME
#           env var; machine-local divergence fail-loud guard

_coordinator_settings_home() {
    # Print the absolute settings-home root path. No side effects.
    #
    # Precedence:
    #   COORDINATOR_SETTINGS_HOME (if non-empty) → use verbatim
    #   else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
    if [[ -n "${COORDINATOR_SETTINGS_HOME:-}" ]]; then
        printf '%s' "$COORDINATOR_SETTINGS_HOME"
        return 0
    fi
    printf '%s' "${CLAUDE_HOME:-${HOME}}/.coordinator-claude-settings"
}

_settings_home_realpath() {
    # Resolve a path to its canonical (fully symlink-resolved) form.
    #
    # BSD-portable: GNU realpath and readlink -f are unavailable on stock macOS.
    # Uses python3 (coordinator hard dep — always present on managed machines).
    # Falls back to returning the literal path unchanged when python3 is absent
    # (e.g. early bootstrap before python is installed) — callers that need a
    # real canonical path must ensure python3 is available.
    local _path="$1"
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$_path"  # popup-safe-env-suppressed
    else
        # No python3 — return literal path. The divergence check degrades to a
        # lexical comparison; a compat symlink may still prevent a false positive
        # if the symlink path == the new path lexically (unusual but possible).
        printf '%s\n' "$_path"
    fi
}

_check_machine_local_divergence() {
    # Fail loud if BOTH machine-local homes exist AND their realpaths differ.
    #
    # Returns 0 (OK) in all safe states:
    #   - Legacy ~/.claude/machine-local absent, OR
    #   - New <settings-home>/machine-local absent, OR
    #   - Both exist AND realpaths are equal (compat symlink — NOT a second home).
    #
    # Exits non-zero (fail-loud) when both exist AND realpaths diverge. Never
    # silently picks one; the operator must run the migration to resolve.
    #
    # CRITICAL: realpath comparison prevents a false positive on the compat layer
    # (C3): a symlink at ~/.claude/machine-local → <settings-home>/machine-local
    # resolves to the same realpath and MUST NOT trigger fail-loud.
    local _settings_home
    _settings_home="$(_coordinator_settings_home)"
    local _legacy="${CLAUDE_HOME:-${HOME}}/.claude/machine-local"
    local _new="${_settings_home}/machine-local"

    # Fast path: if either side is absent there is no divergence.
    [[ -e "$_legacy" ]] || return 0
    [[ -e "$_new"   ]] || return 0

    local _rp_legacy _rp_new
    _rp_legacy="$(_settings_home_realpath "$_legacy")"
    _rp_new="$(_settings_home_realpath "$_new")"

    if [[ "$_rp_legacy" != "$_rp_new" ]]; then
        cat >&2 <<'_DIVERGENCE_MSG'
coordinator-settings-home: DIVERGENT MACHINE-LOCAL HOMES — cannot safely resolve.

Both ~/.claude/machine-local and <settings-home>/machine-local exist and point
at different content homes. Reading from either risks using stale or incomplete
registry data.

Remediation — run the one-time migration to consolidate both homes:
    coordinator/lib/migrate-substrate-to-settings-home.sh

Or, if you know which home is authoritative, set COORDINATOR_SETTINGS_HOME to
point at the desired settings home and then remove or symlink the other:
    export COORDINATOR_SETTINGS_HOME=/path/to/settings-home
_DIVERGENCE_MSG
        printf '  Legacy realpath : %s\n' "$_rp_legacy" >&2
        printf '  New    realpath : %s\n' "$_rp_new" >&2
        return 1
    fi
    return 0
}
