#!/usr/bin/env bash
# bin/list-reverse-drift-cmds.sh — emit registered reverse-drift commands.
#
# Purpose: read plugin.mirrors from the machine-local registry and emit one
# line per copy_install plugin that has a non-empty reverse_drift_cmd:
#
#   <plugin_name>|<source_path>|<reverse_drift_cmd>
#
# Consumed by /workweek-complete Step 4g, which cd's to <source_path> and runs
# <reverse_drift_cmd> as a blocking merge gate.
#
# Exit codes encode the difference between "gate is genuinely N/A" and "gate is
# blind because of misconfiguration" — so Step 4g never silently passes when it
# should be running but cannot:
#   0  — emitted >=1 runnable row, OR no copy_install plugins exist at all (N/A).
#   3  — copy_install plugins ARE registered but NONE carry a reverse_drift_cmd.
#        The gate is structurally blind (the bug-equivalent state). Fail loud.
#   2  — invocation/parse error.
#
# Spec backlink: docs/plans/2026-05-28-reverse-drift-gate-meta-repo-coverage.md §Chunk 3

# set -e intentionally omitted (matches check-plugin-drift.sh): every error path below
# is handled explicitly with `|| exit` / `||` arms, and we want to emit the rc=3 misconfig
# signal rather than abort on a mid-script non-zero.
set -uo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: list-reverse-drift-cmds.sh
Emits "<plugin>|<source_path>|<reverse_drift_cmd>" per copy_install plugin with
a reverse_drift_cmd registered.
Exit: 0 = runnable rows emitted or no copy_install plugins (N/A);
      3 = copy_install plugins exist but none have reverse_drift_cmd (misconfig);
      2 = error.
Environment: MACHINE_LOCAL_REGISTRY_DIR, HOME
EOF
    exit 0
fi

if [[ -n "${MACHINE_LOCAL_REGISTRY_DIR:-}" ]]; then
    REGISTRY_DIR="$MACHINE_LOCAL_REGISTRY_DIR"
else
    REGISTRY_DIR="${HOME}/.claude/machine-local"
fi
REGISTRY_LOCAL="${REGISTRY_DIR}/registry.local.toml"
REGISTRY_TOML="${REGISTRY_DIR}/registry.toml"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "list-reverse-drift-cmds.sh: python3 not found" >&2
    exit 2
fi
export PYTHON

# shellcheck source=lib/read-mirrors.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/read-mirrors.sh"

REGISTRY_FILE=""
if [[ -f "$REGISTRY_LOCAL" ]]; then
    REGISTRY_FILE="$REGISTRY_LOCAL"
elif [[ -f "$REGISTRY_TOML" ]]; then
    REGISTRY_FILE="$REGISTRY_TOML"
fi

# No registry → nothing to emit (not an error; matches check-plugin-drift.sh).
[[ -z "$REGISTRY_FILE" ]] && exit 0

MIRRORS_OUTPUT="$(_read_all_mirrors "$REGISTRY_FILE")" || {
    echo "list-reverse-drift-cmds.sh: failed to read registry" >&2
    exit 2
}
[[ "$MIRRORS_OUTPUT" == "NO_MIRRORS" || -z "$MIRRORS_OUTPUT" ]] && exit 0

copy_install_seen=0
runnable_emitted=0
# Positional fields from the shared 7-field parser; this reader only consumes
# plugin_name, source_path, prop_mode, reverse_drift_cmd. The rest are read to
# land the columns correctly, not used here.
# shellcheck disable=SC2034
while IFS='|' read -r plugin_name source_path live_path track_ref dist_name prop_mode reverse_drift_cmd; do
    [[ -z "$plugin_name" ]] && continue
    [[ "$prop_mode" != "copy_install" ]] && continue
    copy_install_seen=1
    [[ -z "$reverse_drift_cmd" ]] && continue
    # Advisory: the value is shell-evaluated once by `bash -c` in Step 4g, and the
    # documented convention is to single-quote it in registry.local.toml. A literal
    # double-quote in the value almost always signals a misconfiguration (the operator
    # used "double quotes" in TOML). Warn but do not block — exotic single-quoted values
    # are legitimate. (We deliberately do NOT flag `$`, since `$(...)` is a valid idiom.)
    if [[ "$reverse_drift_cmd" == *'"'* ]]; then
        echo "list-reverse-drift-cmds.sh: WARNING: ${plugin_name}.reverse_drift_cmd contains a double-quote — single-quote the value in registry.local.toml (see docs/wiki/machine-local-registry.md § reverse_drift_cmd)." >&2
    fi
    printf '%s|%s|%s\n' "$plugin_name" "$source_path" "$reverse_drift_cmd"
    runnable_emitted=1
done <<< "$MIRRORS_OUTPUT"

# copy_install plugins exist but none carry a reverse_drift_cmd → gate is blind.
if [[ $copy_install_seen -eq 1 && $runnable_emitted -eq 0 ]]; then
    echo "list-reverse-drift-cmds.sh: copy_install plugins are registered but none have a reverse_drift_cmd — the reverse-drift gate cannot run. Register with: bin/machine-local set plugin.mirrors.<name>.reverse_drift_cmd '<invocation>'. See docs/wiki/machine-local-registry.md § reverse_drift_cmd." >&2
    exit 3
fi

# Either runnable rows were emitted, or there are no copy_install plugins (N/A).
exit 0
