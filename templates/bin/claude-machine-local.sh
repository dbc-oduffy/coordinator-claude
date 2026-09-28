#!/usr/bin/env bash


# Purpose: make $REPO_PROJECT_RAG (and friends) cheaper to type than the


#   1. $COORDINATOR_SETTINGS_HOME (if non-empty) → use verbatim
#   2. else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings


# The whole-script early-exit guard (CLAUDE_MACHINE_LOCAL_SOURCED) is retained


# corrupt "$REPO_FOO/subdir" path joins to "/subdir".


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


if command -v python3 >/dev/null 2>&1; then
    _ml_python="python3"
elif command -v python >/dev/null 2>&1; then
    _ml_python="python"
else
    echo "claude-machine-local: error: no python3 or python interpreter found on PATH — cannot invoke $_ml_reader. Install Python 3 and re-source this file." >&2
    unset _ml_settings_home _ml_reader
    return 1
fi


_ml_exports=$("$_ml_python" "$_ml_reader" dump --prefix repos --format sh)
_ml_rc=$?
if [ $_ml_rc -ne 0 ] && [ -z "$_ml_exports" ]; then
    
    
    echo "claude-machine-local: error: reader at $_ml_reader failed (rc=$_ml_rc) and exported nothing — no \$REPO_* is set. If it predates 'dump --format sh', re-run the coordinator install to refresh it." >&2
else
    eval "$_ml_exports"
fi
unset _ml_settings_home _ml_reader _ml_python _ml_exports _ml_rc

export CLAUDE_MACHINE_LOCAL_SOURCED=1
