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
#
# The encoding is LOSSY: a literal hyphen inside a path segment and a structural
# separator both encode to `-`. A blanket `-`→separator reverse is therefore
# wrong for any path whose segments contain real hyphens — e.g. `X:\dev\fifa-stats`
# encodes to `X--dev-fifa-stats`, which the naive decode turns into
# `X:\dev\fifa\stats`; the `-d` test then fails and the repo is silently dropped.
# We keep the naive decode as a zero-cost fast path and fall back to a greedy
# filesystem-walk disambiguation only on miss.

# Convert a native Windows-form path ("X:\a\b") to its POSIX existence-test path
# (lowercased — GNU sed's \L extension is not on BSD/macOS, so use `tr`). With
# $2 (fs_root) set, the drive root is replaced by fs_root — a hermetic test
# seam; unset in production.
_tier_a_posix() {
    local win="$1" fs_root="$2"
    if [[ -n "$fs_root" ]]; then
        local tail; tail="$(echo "${win#*:\\}" | sed 's|\\|/|g' | tr '[:upper:]' '[:lower:]')"
        echo "$fs_root/$tail"
    else
        echo "$win" | sed -E 's|^([A-Za-z]):\\|/\1/|; s|\\|/|g' | tr '[:upper:]' '[:lower:]'
    fi
}

# Greedy filesystem-walk disambiguation of a lossy projects-dir remainder.
# Args: $1 = post-drive remainder (e.g. "dev-fifa-stats"), $2 = drive letter,
#       $3 = optional POSIX walk root (test seam; defaults to /<drive>).
# At each level, consume the LONGEST run of remaining `-`-tokens that names an
# existing directory; descend; repeat. This resolves hyphen-as-literal vs
# hyphen-as-separator by what actually exists on disk. Emits the reconstructed
# native Windows path on a full resolution, nothing otherwise (fail-safe — a
# miss never emits a wrong path). Bash-3.2-safe (arrays + `tr`, no `${,,}`).
_tier_a_greedy_decode() {
    local rest="$1" drive="$2" fs_root="$3"
    local root
    if [[ -n "$fs_root" ]]; then
        root="$fs_root"
    else
        root="/$(echo "$drive" | tr '[:upper:]' '[:lower:]')"
    fi
    local -a tokens=()
    IFS='-' read -r -a tokens <<< "$rest"
    local n=${#tokens[@]}
    # Bound the walk so a pathological all-hyphen name can't blow up the search.
    # `(( ))` is the &&-conditional here — its exit-1 on a false expression is
    # exempt from `set -e` (do not rewrite as a bare statement).
    (( n > 40 )) && return 0
    local cur="$root"
    local -a segs=()
    local i=0
    while (( i < n )); do
        local matched=0 j
        for (( j=n; j>i; j-- )); do
            # cand is rebuilt fresh each j-iteration (longest run first), not
            # accumulated across iterations.
            local cand="${tokens[i]}" k
            for (( k=i+1; k<j; k++ )); do cand="$cand-${tokens[k]}"; done
            # Empty token (leading `-` or a `--` from an encoded `.`/`..`) — skip.
            [[ -z "$cand" ]] && continue
            local cand_lc; cand_lc="$(echo "$cand" | tr '[:upper:]' '[:lower:]')"
            if [[ -d "$cur/$cand_lc" ]]; then
                segs+=( "$cand" )
                cur="$cur/$cand_lc"
                i=$j
                matched=1
                break
            fi
        done
        (( matched )) || return 0
    done
    (( ${#segs[@]} == 0 )) && return 0
    # Reconstruct the native Windows path (Tier A's output contract): drive +
    # backslash-joined segments, as cased in the encoded name (the encoding is
    # case-lossy, so this is whatever the projects-dir basename carried).
    local out="$drive:" seg
    for seg in "${segs[@]}"; do out="$out\\$seg"; done
    printf '%s\n' "$out"
}

_tier_a() {
    # Optional hermetic-test seam: POSIX filesystem root that decoded paths are
    # existence-tested against. Unset in production (real drive roots like /x).
    local fs_root="${COORDINATOR_TIER_A_FS_ROOT:-}"
    # Loop vars are scoped to the pipe subshell (the `ls | head | while` runs in
    # a child); `local` keeps them off the function scope for consistency.
    local base drive rest decoded posix
    ls -1dt ~/.claude/projects/*/ 2>/dev/null | head -50 | while read -r p; do
        base="$(basename "$p")"
        case "$base" in
            [A-Za-z]--*) drive="${base:0:1}"; rest="${base:3}"
                         decoded="${drive}:\\${rest//-/\\}";;
            # Non-drive-letter entries (POSIX-form, not produced by Claude Code on
            # Windows): naive decode only, no greedy fallback — out of scope.
            *) drive=""; rest="$base"; decoded="${base//-/\\}";;
        esac
        posix="$(_tier_a_posix "$decoded" "$fs_root")"
        if [[ -d "$posix" ]]; then
            # Fast path: naive decode resolved (no literal hyphens in segments).
            echo "$decoded"
        elif [[ -n "$drive" ]]; then
            # Naive decode missed — disambiguate the lossy encoding against disk.
            _tier_a_greedy_decode "$rest" "$drive" "$fs_root"
        fi
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
# Run the tier dispatch only when executed directly. When sourced (e.g. by the
# regression test exercising the decode functions in isolation), skip dispatch.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
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
fi
