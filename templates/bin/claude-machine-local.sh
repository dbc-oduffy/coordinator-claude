#!/usr/bin/env bash

# Sourced helper exporting $REPO_* for portable, host-independent repo paths -- never a
# hardcoded literal. Sourced once per shell session; idempotent via the
# CLAUDE_MACHINE_LOCAL_SOURCED guard below. This file is installed standalone on a
# consumer machine, so it resolves the settings home by pure path arithmetic rather than
# sourcing coordinator/lib/settings-home.sh, which is not guaranteed present.
#
# A cleanly-absent key ($REPO_FOO unset) must not be exported as "" -- an empty export
# would silently corrupt "$REPO_FOO/subdir" path joins to "/subdir".
#
# Not `set -e`: this file is sourced, so `set -e` would propagate to the caller's shell
# and kill it on any error.

if [ -n "${CLAUDE_MACHINE_LOCAL_SOURCED:-}" ]; then
    return 0
fi

# Settings-home resolution ladder, most-specific first.
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
    # Nothing resolved AND the reader failed -- most often a settings-home whose
    # _machine_local.py predates `--format sh`. Every $REPO_* would silently be unset;
    # say so instead.
    echo "claude-machine-local: error: reader at $_ml_reader failed (rc=$_ml_rc) and exported nothing — no \$REPO_* is set. If it predates 'dump --format sh', re-run the coordinator install to refresh it." >&2
else
    eval "$_ml_exports"
fi
unset _ml_settings_home _ml_reader _ml_python _ml_exports _ml_rc

export CLAUDE_MACHINE_LOCAL_SOURCED=1
