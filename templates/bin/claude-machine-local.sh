#!/usr/bin/env bash
# claude-machine-local.sh — sourced helper exporting $REPO_* for portable paths.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.2
# Purpose: make $REPO_PROJECT_RAG (and friends) cheaper to type than the
# hardcoded literal. Sourced once per shell session; idempotent.
#
# Settings-home contract (DR-072): the machine-local registry and its reader
# live under a settings home, not a fixed ~/.claude/bin path. Consumers MUST
# NOT invoke the bare-name `machine-local` wrapper to bootstrap — per
# docs/wiki/machine-local-registry.md:278, this script resolves the settings
# home by pure path arithmetic and invokes the reader impl directly:
#   <settings-home>/bin/_machine_local.py get|keys <key>
# Settings-home resolution ladder (most-specific first; mirrors, but does not
# source, coordinator/lib/settings-home.sh — this file is installed standalone
# on a consumer machine where that lib is not guaranteed present):
#   1. $COORDINATOR_SETTINGS_HOME (if non-empty) → use verbatim
#   2. else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
#
# Resolution: each $REPO_<SLUG> is resolved via the reader's `get repos.<slug>`
# which implements the full 4-rung ladder (explicit flag/env → OS-keyed
# search-roots + marker autodiscovery → exceptions table → registry.local.toml
# fallback). Raw registry reads are NOT used; autodiscovered repos resolve.
#
# §4b idempotency (machine-local-registry.md §4b): each export is gated on
# [[ -z "${VAR:-}" ]] — re-sourcing in a child process does NOT clobber a
# deliberately pre-set $REPO_* override. The whole-script early-exit guard
# (CLAUDE_MACHINE_LOCAL_SOURCED) is retained for the common case (no pre-sets).
#
# Negative-spec: empty-string exports are suppressed. rc=1 (clean absence from
# the ladder) skips the export rather than exporting "" — exporting "" would
# corrupt "$REPO_FOO/subdir" path joins to "/subdir".
#
# Strict mode: set -e is intentionally absent — this file is sourced, so
# set -e would propagate to the caller's shell and kill it on any error.
#
# Usage:
#   source <settings-home>/bin/claude-machine-local.sh
#   echo "$REPO_PROJECT_RAG/subdir/file.py"

if [ -n "${CLAUDE_MACHINE_LOCAL_SOURCED:-}" ]; then
    return 0
fi

# Settings-home resolution ladder (inline mirror of
# coordinator/lib/settings-home.sh::_coordinator_settings_home — not sourced,
# see file-top note). Scope matches that lib: MACHINE_LOCAL_REGISTRY_DIR is a
# deeper registry-dir override handled by _machine_local.py itself, not here.
if [ -n "${COORDINATOR_SETTINGS_HOME:-}" ]; then
    _ml_settings_home="$COORDINATOR_SETTINGS_HOME"
else
    _ml_settings_home="${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings"
fi
_ml_reader="$_ml_settings_home/bin/_machine_local.py"

# Interpreter probe: conservative, fail loud on absence rather than silently
# skipping the whole export ladder (silent-skip on a resolver is the named
# anti-pattern here — see coordinator/docs/wiki/machine-local-registry.md
# § 4 Resolution Order (formerly coordinator/CLAUDE.md § Build For Someone
# Else's Machine, retired 2026-07-27)).
if command -v python3 >/dev/null 2>&1; then
    _ml_python="python3"
elif command -v python >/dev/null 2>&1; then
    _ml_python="python"
else
    echo "claude-machine-local: error: no python3 or python interpreter found on PATH — cannot invoke $_ml_reader. Install Python 3 and re-source this file." >&2
    unset _ml_settings_home _ml_reader
    return 1
fi

while IFS= read -r _ml_key; do
    # Normalize: repos.foo-bar → REPO_FOO_BAR. Strip the "repos." prefix first,
    # then uppercase the suffix and prepend REPO_. Handle both . and - as separators.
    _ml_suffix=$(echo "${_ml_key#repos.}" | tr 'a-z.-' 'A-Z__')
    _ml_var="REPO_${_ml_suffix}"
    # Validate POSIX shell identifier: ^[A-Z_][A-Z0-9_]*$
    if ! [[ "$_ml_var" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
        echo "claude-machine-local: warning: skipping key '$_ml_key' — produces non-conformant shell identifier '$_ml_var'" >&2
        continue
    fi
    # §4b idempotency gate: if the variable is already non-empty, honour the
    # pre-set value (deliberate REPO_* override) and skip re-resolution.
    if [[ -n "${!_ml_var:-}" ]]; then
        continue
    fi
    # Resolve via the full 4-rung ladder (incl. autodiscovery). No --default ""
    # so rc=1 (clean absence) is distinguishable from rc=0 (found a path).
    # stderr from the CLI flows through so operational failures (rc≥2) surface
    # their own remediation messages to the caller.
    _ml_value=$("$_ml_python" "$_ml_reader" get "$_ml_key")
    _ml_rc=$?
    case $_ml_rc in
        0)
            # Ladder resolved rc=0, but the reader also round-trips an explicit
            # user-declared empty value with rc=0 (the AC14 "declared but
            # unconfigured" case — see _machine_local.py:796-810). Guard the
            # export on non-empty to avoid exporting a corrupting "" that would
            # collapse "$REPO_FOO/subdir" to "/subdir" (see negative-spec above).
            # Review: code-reviewer — F1, empty-value declared-but-unconfigured
            # case must not export "".
            if [ -z "$_ml_value" ]; then
                echo "claude-machine-local: warning: '$_ml_key' declared but has no value — \$$_ml_var not exported" >&2
            else
                export "$_ml_var=$_ml_value"
            fi
            ;;
        1)
            # Clean absence — ladder found no value for this key; skip export.
            # (Exporting "" would corrupt "$REPO_X/subdir" to "/subdir".)
            echo "claude-machine-local: warning: '$_ml_key' not resolved by ladder — \$$_ml_var not exported" >&2
            ;;
        *)
            # Operational failure (rc≥2): Python version guard, malformed TOML, etc.
            # The CLI already emitted remediation to stderr; add envelope context.
            echo "claude-machine-local: error: machine-local reader failed for '$_ml_key' (rc=$_ml_rc)" >&2
            ;;
    esac
done < <("$_ml_python" "$_ml_reader" keys 2>/dev/null | grep -E '^repos\.')
unset _ml_key _ml_suffix _ml_var _ml_value _ml_rc _ml_settings_home _ml_reader _ml_python

export CLAUDE_MACHINE_LOCAL_SOURCED=1
