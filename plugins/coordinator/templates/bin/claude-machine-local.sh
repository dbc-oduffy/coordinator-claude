#!/usr/bin/env bash
# claude-machine-local.sh — sourced helper exporting $REPO_* for portable paths.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.2
# Purpose: make $REPO_PROJECT_RAG (and friends) cheaper to type than the
# hardcoded literal. Sourced once per shell session; idempotent.
#
# Usage:
#   source ~/.claude/bin/claude-machine-local.sh
#   echo "$REPO_PROJECT_RAG/subdir/file.py"

if [ -n "${CLAUDE_MACHINE_LOCAL_SOURCED:-}" ]; then
    return 0
fi

_ml_keys=$(~/.claude/bin/machine-local keys 2>/dev/null | grep -E '^repos\.')
for _ml_key in $_ml_keys; do
    # Normalize: repos.foo-bar → REPO_FOO_BAR. Strip the "repos." prefix first,
    # then uppercase the suffix and prepend REPO_. Handle both . and - as separators.
    _ml_suffix=$(echo "${_ml_key#repos.}" | tr 'a-z.-' 'A-Z__')
    _ml_var="REPO_${_ml_suffix}"
    # Validate POSIX shell identifier: ^[A-Z_][A-Z0-9_]*$
    if ! [[ "$_ml_var" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
        echo "claude-machine-local: warning: skipping key '$_ml_key' — produces non-conformant shell identifier '$_ml_var'" >&2
        continue
    fi
    _ml_value=$(~/.claude/bin/machine-local get "$_ml_key" --default "" 2>/dev/null)
    if [ -z "$_ml_value" ]; then
        echo "claude-machine-local: warning: $_ml_key is unset (\$$_ml_var='')" >&2
    fi
    export "$_ml_var=$_ml_value"
done
unset _ml_keys _ml_key _ml_suffix _ml_var _ml_value

export CLAUDE_MACHINE_LOCAL_SOURCED=1
