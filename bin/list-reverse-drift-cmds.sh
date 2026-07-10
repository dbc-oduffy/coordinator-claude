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
# Per-repo scoping (--scope-repo <repo-root>):
#   Without --scope-repo, EVERY copy_install row is emitted (legacy behavior;
#   preserved for direct callers and tests). Step 4g always passes its repo root
#   so a CONSUMER repo's release never gates on a SIBLING plugin's live-install
#   drift. The meta-repo (${HOME}/.claude, the coordinator home) is the explicit
#   check-all case — releasing it covers every copy_install plugin on the machine
#   (the 2026-05-28 §Chunk 3 meta-repo coverage intent). Any other repo emits only
#   rows whose source_path IS that repo (usually none → clean no-op).
#   Paths are normalized before comparison (Windows X:/ vs MSYS /x/ vs $HOME /c/)
#   so the meta-repo and source_path matches survive cross-platform path forms.
#   Spec backlink: cross-repo/inbox/2026-06-01-reverse-drift-gate-per-repo-scoping.md
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

SCOPE_REPO=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            cat <<'EOF'
Usage: list-reverse-drift-cmds.sh [--scope-repo <repo-root>]
Emits "<plugin>|<source_path>|<reverse_drift_cmd>" per copy_install plugin with
a reverse_drift_cmd registered.
  --scope-repo <repo-root>  Restrict emission to the releasing repo. The meta-repo
                            (${HOME}/.claude) emits ALL rows (check-all); any other
                            repo emits only rows whose source_path is that repo.
                            Omitted → all rows (legacy / direct-caller behavior).
Exit: 0 = runnable rows emitted, scoped to none, or no copy_install plugins (N/A);
      3 = copy_install plugins exist but none have reverse_drift_cmd (misconfig);
      2 = error.
Environment: MACHINE_LOCAL_REGISTRY_DIR, HOME
EOF
            exit 0
            ;;
        --scope-repo)
            SCOPE_REPO="${2:-}"
            if [[ -z "$SCOPE_REPO" ]]; then
                echo "list-reverse-drift-cmds.sh: --scope-repo requires a path argument" >&2
                exit 2
            fi
            shift 2
            ;;
        *)
            echo "list-reverse-drift-cmds.sh: unknown argument '$1'" >&2
            exit 2
            ;;
    esac
done

# Normalize a path for cross-platform comparison so that the registry's Windows
# `X:/` form, `git rev-parse --show-toplevel`'s `C:/` form, and `$HOME`-derived
# `/c/` form all converge. Windows drive paths fold to MSYS lowercase form
# (X:/Foo, X:\Foo, drive-relative X:Foo → /x/foo); the MSYS drive-mount form
# (/x/Foo) folds only under a Windows shell. A genuine POSIX path (/Users/...,
# /home/..., or a single-letter top-level dir /a/... on Linux) is returned
# case-preserved.
_norm_path() {
    local p="$1"
    if [[ "$p" =~ ^[A-Za-z]: ]]; then
        # Windows drive form. Separator is normalized AFTER stripping the `X:`
        # prefix — never put a backslash inside a regex bracket expression, whose
        # meaning is undefined under bash 3.2 POSIX ERE (code-reviewer F1).
        local drive rest
        drive="$(printf '%s' "${p:0:1}" | tr 'A-Z' 'a-z')"
        rest="${p:2}"
        rest="${rest//\\//}"                    # backslashes → forward
        [[ "$rest" != /* ]] && rest="/$rest"    # drive-relative X:foo → /x/foo (code-reviewer F2)
        # Windows filesystems are case-insensitive — fold the whole path.
        p="$(printf '/%s%s' "$drive" "$rest" | tr 'A-Z' 'a-z')"
    elif [[ "$p" =~ ^/[A-Za-z]/ ]] \
        && { [[ "${OSTYPE:-}" == msys* ]] || [[ "${OSTYPE:-}" == cygwin* ]] || [[ "${OSTYPE:-}" == win* ]]; }; then
        # MSYS drive-mount form (/x/Foo) under a Windows shell only — fold to match
        # the X:/ branch. NOT folded on macOS/Linux, where /a/foo is case-sensitive
        # and must not collide with a different-cased path (code-reviewer F3).
        p="$(printf '%s' "$p" | tr 'A-Z' 'a-z')"
    fi
    # Strip trailing separators LAST: a trailing backslash (X:\foo\) becomes a
    # trailing slash after normalization and must not defeat the == compare
    # (code-reviewer F4).
    while [[ "$p" == */ && "$p" != "/" ]]; do p="${p%/}"; done
    printf '%s' "$p"
}

# Resolve machine-local dir through the settings-home seam (C1).
# MACHINE_LOCAL_REGISTRY_DIR is rung-1 (direct override, bypasses home resolution);
# otherwise resolve via _coordinator_settings_home() from settings-home.sh.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2b
# shellcheck source=../lib/settings-home.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/settings-home.sh"

if [[ -n "${MACHINE_LOCAL_REGISTRY_DIR:-}" ]]; then
    REGISTRY_DIR="$MACHINE_LOCAL_REGISTRY_DIR"
else
    REGISTRY_DIR="$(_coordinator_settings_home)/machine-local"
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

# Resolve scoping decision once. SCOPE_MODE:
#   all  — emit every copy_install row (no --scope-repo, or scope == meta-repo).
#   own  — emit only rows whose source_path == SCOPE_NORM.
SCOPE_MODE="all"
if [[ -n "$SCOPE_REPO" ]]; then
    SCOPE_NORM="$(_norm_path "$SCOPE_REPO")"
    META_NORM="$(_norm_path "${HOME}/.claude")"
    if [[ "$SCOPE_NORM" != "$META_NORM" ]]; then
        SCOPE_MODE="own"
    fi
fi

copy_install_seen=0
runnable_emitted=0
# Positional fields from the shared 7-field parser; this reader only consumes
# plugin_name, source_path, prop_mode, reverse_drift_cmd. The rest are read to
# land the columns correctly, not used here.
# shellcheck disable=SC2034
while IFS='|' read -r plugin_name source_path live_path track_ref dist_name prop_mode reverse_drift_cmd; do
    [[ -z "$plugin_name" ]] && continue
    [[ "$prop_mode" != "copy_install" ]] && continue
    # Per-repo scoping BEFORE the misconfig counter: a plugin a consumer repo does
    # not source is not "this repo's gate" — it must not count toward copy_install_seen,
    # else a clean consumer no-op would falsely trip the rc=3 "gate is blind" signal.
    # The meta-repo (SCOPE_MODE=all) checks every copy_install plugin.
    if [[ "$SCOPE_MODE" == "own" && "$(_norm_path "$source_path")" != "$SCOPE_NORM" ]]; then
        continue
    fi
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
