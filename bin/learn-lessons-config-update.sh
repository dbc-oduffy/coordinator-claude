#!/usr/bin/env bash
# learn-lessons-config-update.sh — ensure the cwd repo is discoverable by learn-lessons.
#
# learn-lessons discovery roots are derived PER-MACHINE from the machine-local [repos] registry
# (see bin/learn-lessons-roots.sh: $CLAUDE_HOME + `machine-local get repos.*`, skip-absent, minus
# publish targets). This script NO LONGER appends absolute paths to the committed config file —
# that accretion baked one machine's paths into a git-tracked file and did not survive a machine
# change (retired 2026-06-19; the prior awk-marker append was also silently broken — its marker
# `learn-lessons-config-end` never matched the file's `END learn-lessons-roots` sentinel, so it
# printed "appended" while writing nothing).
#
# Behavior: if the cwd repo is already a learn-lessons root (the meta-repo $CLAUDE_HOME itself, or a
# registered [repos] entry), silent no-op. Otherwise print a one-line hint to register it via
# machine-local. NEVER mutates a tracked file. Always exits 0 (idempotent; safe as a Phase 0 call).
set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"

# Resolve the machine-local CLI: PATH first, then the in-plugin bin as fallback.
ML="$(command -v machine-local 2>/dev/null || true)"
[ -n "$ML" ] || ML="$CLAUDE_HOME/plugins/coordinator/bin/machine-local"

# Physical-path normalize for comparison (portable; no realpath/readlink -f dependency).
_norm() { ( cd "$1" 2>/dev/null && pwd -P ) || printf '%s' "$1"; }

cwd="$(_norm "$PWD")"
home_norm="$(_norm "$CLAUDE_HOME")"

# The meta-repo itself is always a learn-lessons root — nothing to advise.
[ "$cwd" = "$home_norm" ] && exit 0

# Already a registered [repos] entry? Then it is already discoverable — silent no-op.
if [ -x "$ML" ]; then
  while IFS= read -r key; do
    [ -z "$key" ] && continue
    p="$("$ML" get "$key" 2>/dev/null)" || continue
    [ -n "$p" ] || continue
    [ "$(_norm "$p")" = "$cwd" ] && exit 0
  done < <("$ML" keys 2>/dev/null | grep '^repos\.')
fi

# Not a known root — advise on stderr (do NOT mutate any tracked file).
slug="$(basename "$cwd" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/^_*//; s/_*$//')"
{
  echo "learn-lessons: '$cwd' is not a registered learn-lessons root."
  echo "  To include its lessons in central runs, register it once:"
  echo "    machine-local set repos.${slug} \"$cwd\""
} >&2
exit 0
