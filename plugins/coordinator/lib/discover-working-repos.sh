#!/usr/bin/env bash
# discover-working-repos.sh — three-tier working-repo discovery for /setup Phase 2 Step 4.
#
# Prints discovered repo paths to stdout (one per line). Empty stdout means
# no repos discovered — caller (setup skill) falls through to Tier C
# (operator prompt) interactively.
#
# Tier A (preferred):  ~/.claude/projects/ activity record.
# Tier A.5 (registry): ~/.claude/machine-local/registry.local.toml::repos.*
# Tier B (fallback):   common dev-folder layouts.
# Tier C:              caller-handled interactive prompt (NOT in this script).
#
# Stops at first non-empty tier. Filters meta-repo, AppData/Local/Temp,
# bare drive roots.

set -euo pipefail

# Tier A — Claude Code's own activity record.
# Path encoding: `:` `\` `/` `.` → `-`. Drive root "X:\Foo" → "X--Foo".
_tier_a() {
    ls -1dt ~/.claude/projects/*/ 2>/dev/null | head -50 | while read -r p; do
        base="$(basename "$p")"
        case "$base" in
            [A-Za-z]--*) decoded="${base:0:1}:\\${base:3}"; decoded="${decoded//-/\\}";;
            *) decoded="${base//-/\\}";;
        esac
        # Convert Windows path to POSIX form for existence test.
        # Portable lowercase via `tr` (GNU sed's \L extension is not on BSD/macOS).
        posix="$(echo "$decoded" | sed -E 's|^([A-Za-z]):\\|/\1/|; s|\\|/|g' | tr '[:upper:]' '[:lower:]')"
        [[ -d "$posix" ]] && echo "$decoded"
    done | grep -vE '(AppData[\\/]Local[\\/]Temp|^[A-Za-z]:\\?$|/\.claude$)' | sort -u | head -20
}

# Tier A.5 — machine-local registry repos.* enumeration.
# Closes the gap where an operator has registered sibling repos in
# registry.local.toml but no activity record exists yet (Tier A miss) AND the
# path doesn't match the dev-folder probe layouts (Tier B miss). Defensive
# fallback: silently no-op if machine-local is unavailable.
_tier_a5() {
    local ml_bin=""
    if command -v machine-local >/dev/null 2>&1; then
        ml_bin="machine-local"
    elif [[ -x "$HOME/.claude/bin/machine-local" ]]; then
        ml_bin="$HOME/.claude/bin/machine-local"
    else
        return 0
    fi
    "$ml_bin" keys 2>/dev/null | grep '^repos\.' | while read -r key; do
        val="$("$ml_bin" get "$key" 2>/dev/null)" || continue
        [[ -z "$val" ]] && continue
        # Normalize to POSIX form for the existence test (registry values are
        # commonly stored as native paths like "X:/foo" or "X:\foo").
        posix="$(echo "$val" | sed -E 's|^([A-Za-z]):[\\/]|/\1/|; s|\\|/|g' | tr '[:upper:]' '[:lower:]')"
        if [[ -d "$posix" || -d "$val" ]]; then
            echo "$val"
        fi
    done | sort -u
}

# Tier B — common dev-folder layouts.
# Accept .git as directory OR file (worktrees use a `.git` file containing
# `gitdir: <path>` — `-type d` alone misses them).
_tier_b() {
    for cand in ~/dev ~/Dev ~/code ~/Code ~/src ~/Source ~/Projects ~/projects ~/workspace ~/repos ~/Documents/GitHub /c/dev /d/dev /e/dev /x; do
        [[ -d "$cand" ]] && find "$cand" -maxdepth 2 -name .git \( -type d -o -type f \) 2>/dev/null | sed 's|/\.git$||'
    done | sort -u | head -30
}

# `|| true` defends against pipefail SIGPIPE: head -N inside the tier functions
# cuts the pipe before upstream `read` exhausts; under `set -euo pipefail` that
# raises 141, killing the assignment. Tier helpers can legitimately produce
# zero output (no matches); we want exit 0 + empty stdout, not abort.
#
# Tier A.5 always runs ALONGSIDE the first non-empty tier (A or B). Its purpose
# is to close gaps in Tier A — an operator may have registered a sibling repo
# in registry.local.toml but lack an activity record for it, so a strict
# stop-at-first-non-empty A would mask the registered repo. Merge + dedup.
_a_out=$(_tier_a || true)
_a5_out=$(_tier_a5 || true)
if [[ -n "$_a_out" ]]; then
    { echo "$_a_out"; [[ -n "$_a5_out" ]] && echo "$_a5_out"; } | sort -u
    exit 0
fi

_b_out=$(_tier_b || true)
if [[ -n "$_b_out" || -n "$_a5_out" ]]; then
    { [[ -n "$_b_out" ]] && echo "$_b_out"; [[ -n "$_a5_out" ]] && echo "$_a5_out"; } | sort -u
    exit 0
fi

# All tiers empty — exit 0 with no stdout; caller handles Tier C interactively.
exit 0
