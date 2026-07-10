#!/usr/bin/env bash
# register-discovered-repos.sh — F16 fix: bridges discover-working-repos.sh's
# tier-gated discovery output into the machine-local `repos.*` registry that
# cross-repo addressing (cross-repo-memo --list-receivers, sibling-path
# resolution) depends on.
#
# Problem this closes: coordinator:install Step 4 (Discover working repos)
# ran three-tier discovery and persisted a batch-onboarding manifest at
# ~/.claude/working-repos.yaml, but never registered any discovered repo into
# repos.* — so a fresh-machine operator could not address any fleet sibling
# by name until manually running `machine-local set repos.<name> <path>`.
#
# Design:
#   - Tier-gated: repos come ONLY from discover-working-repos.sh's own three-
#     tier qualification (activity record / registry / dev-folder probe).
#     This script does NOT walk the filesystem itself — a stray git clone
#     that discover-working-repos.sh doesn't already surface is never
#     registered. Over-registration is bounded by that upstream script.
#   - Only-if-absent: never clobbers an existing repos.<key> value. A prior
#     manual registration (possibly pointing elsewhere on purpose) always
#     wins. Re-runs are no-ops for anything already registered.
#   - Key derivation matches cross-repo-memo's `_receiver_repo_key` resolver
#     (dashes-to-underscores on `--to <name>-em` lookups) — that resolver is
#     the authority a hyphenated repo basename must land under: lowercase
#     basename, non-alnum runs collapsed to a single `_`, leading/trailing
#     `_` stripped. (Mirrors first-run.sh's `_repo_key` derivation — kept in
#     sync intentionally.)
#
# Modes:
#   (default)          interactive when stdin is a tty: prints the list of
#                       not-yet-registered repos, asks Y/n, registers on
#                       accept (or on any non-interactive/non-tty context).
#   --non-interactive   silent absent-only seed, no prompt.
#   --check-only        report what WOULD register; writes nothing.
#
# Negative-spec: this script does not read or write ~/.claude/working-repos.yaml
# (that manifest is a separate concern — see install.md Step 4). It only reads
# discover-working-repos.sh's stdout and machine-local's registry.
#
# Spec backlink: F16 (install discovers working repos but never registers
# them into the machine-local repos.* registry).

set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

_RD_NON_INTERACTIVE=0
_RD_CHECK_ONLY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --non-interactive) _RD_NON_INTERACTIVE=1 ;;
        --check-only) _RD_CHECK_ONLY=1 ;;
        *)
            echo "register-discovered-repos.sh: unknown argument: $1" >&2
            echo "Usage: $0 [--non-interactive] [--check-only]" >&2
            exit 1
            ;;
    esac
    shift
done

_discover_sh="$SELF_DIR/discover-working-repos.sh"

if [ ! -x "$_discover_sh" ]; then
    echo "register-discovered-repos.sh: discover-working-repos.sh not found/executable at $_discover_sh — skipping registration." >&2
    exit 0
fi

_ml_bin=""
if command -v machine-local >/dev/null 2>&1; then
    _ml_bin="machine-local"
elif [ -x "${CLAUDE_HOME:-$HOME}/.claude/bin/machine-local" ]; then
    _ml_bin="${CLAUDE_HOME:-$HOME}/.claude/bin/machine-local"
else
    echo "register-discovered-repos.sh: machine-local CLI not found — skipping registration. Register later: machine-local set repos.<name> <path>" >&2
    exit 0
fi

# Derive a sane lowercase registry key from a repo basename. Bash-3.2-safe
# (tr only, no ${var,,}). Matches first-run.sh's existing `_repo_key` derivation.
_derive_key() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_' | sed 's/^_//;s/_$//'
}

# Collect discovery candidates (already tier-gated/deduped by discover-working-repos.sh).
_candidates=()
while IFS= read -r _repo_path; do
    [ -z "$_repo_path" ] && continue
    _candidates+=("$_repo_path")
done < <("$_discover_sh")

if [ "${#_candidates[@]}" -eq 0 ]; then
    exit 0
fi

# Filter to only-if-absent: skip any repo whose key is already registered.
_to_register=()
for _repo_path in "${_candidates[@]}"; do
    _key="$(_derive_key "$(basename "$_repo_path")")"
    [ -z "$_key" ] && continue
    if "$_ml_bin" has "repos.$_key" >/dev/null 2>&1; then
        continue
    fi
    _to_register+=("${_key}=${_repo_path}")
done

if [ "${#_to_register[@]}" -eq 0 ]; then
    exit 0
fi

if [ "$_RD_CHECK_ONLY" = 1 ]; then
    printf 'register-discovered-repos.sh: would register %d repo(s):\n' "${#_to_register[@]}"
    for _pair in "${_to_register[@]}"; do
        printf '  repos.%s = %s\n' "${_pair%%=*}" "${_pair#*=}"
    done
    exit 0
fi

if [ "$_RD_NON_INTERACTIVE" = 0 ] && [ -t 0 ]; then
    printf 'register-discovered-repos.sh: %d discovered repo(s) not yet in the machine-local registry:\n' "${#_to_register[@]}"
    for _pair in "${_to_register[@]}"; do
        printf '  repos.%s = %s\n' "${_pair%%=*}" "${_pair#*=}"
    done
    printf 'Register them now? [Y/n] '
    _reply=""
    read -r _reply
    case "$_reply" in
        ''|[Yy]|[Yy][Ee][Ss]) : ;;
        *)
            echo "register-discovered-repos.sh: registration skipped by operator. Register later: machine-local set repos.<name> <path>"
            exit 0
            ;;
    esac
fi

for _pair in "${_to_register[@]}"; do
    _key="${_pair%%=*}"
    _path="${_pair#*=}"
    printf 'register-discovered-repos.sh: registering repos.%s = %s\n' "$_key" "$_path"
    "$_ml_bin" set "repos.$_key" "$_path" || {
        echo "register-discovered-repos.sh: WARNING: failed to register repos.$_key — skipping." >&2
    }
done
