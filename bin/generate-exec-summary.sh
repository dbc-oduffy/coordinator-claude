#!/usr/bin/env bash
# generate-exec-summary.sh — Generate or refresh docs/exec-summary.md for any coordinator repo.
#
# Purpose: populate the two MANAGED sections (identity, progress) from disk artifacts
# and preserve the two HAND sections (special, goals) verbatim across regenerations.
# Shaped after regenerate-orientation-cache.sh: git-root resolve, disk derivation,
# --check flag, no-clobber create.
#
# Spec backlink: docs/plans/2026-07-03-exec-summary-per-repo-brief.md § C2
# Spec backlink: docs/wiki/exec-summary-artifact.md § Generator contract
#
# Usage:
#   generate-exec-summary.sh [--check]
#
# Options:
#   --check   Print generated content to stdout without writing to disk.
#
# Behavior:
#   New file (docs/exec-summary.md absent) — creates with MANAGED sections filled
#     from disk and HAND sections seeded with placeholder text.
#   Existing file — re-derives MANAGED sections from disk; preserves HAND sections
#     verbatim.  Exits non-zero (fail-loud) if any HAND fence is absent or malformed.
#
# Portability: bash 3.2+ / BSD coreutils (DR-148). No GNU-isms.
#
# Negative-spec:
#   - Does NOT overwrite HAND sections on existing files.
#   - Does NOT continue silently if HAND fences are malformed on an existing file.
#   - Does NOT add a cockpit-contract entity or bump CONTRACT_VERSION (anti-scope).
#   - Does NOT write to disk when --check is passed.
#   - MANAGED-section markdown links with bare repo-root-relative targets (e.g.
#     `](archive/foo.md)`) are rewritten to `](../archive/foo.md)` since the output
#     file lives one directory below repo root at docs/exec-summary.md; HAND
#     sections are left untouched (author-owned, not rewritten).

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
# shellcheck source=../lib/coordinator-state-root.sh
source "${_SCRIPT_DIR}/../lib/coordinator-state-root.sh"

CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK_ONLY=1; shift ;;
        *)       printf 'ERROR: unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || { printf 'ERROR: not inside a git repository\n' >&2; exit 1; })"
TARGET="$REPO_ROOT/docs/exec-summary.md"
STATE_ROOT="$(coordinator_state_root)"
ISO_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# HAND block validation and extraction
# (only called on existing files; new files receive placeholder text)
# ---------------------------------------------------------------------------

# Validate that both HAND fence pairs (special, goals) are present and paired.
# Prints error to stderr and returns 1 if any fence is absent or malformed.
# Negative-spec: does NOT write any output or modify any file.
_validate_hand_fences() {
    local file="$1" ok=1 name found_begin found_end
    for name in special goals; do
        found_begin="$(awk -v n="$name" '$0 == "<!-- BEGIN HAND: " n " -->" { print 1; exit }' "$file")"
        found_end="$(awk -v n="$name" '$0 == "<!-- END HAND: " n " -->" { print 1; exit }' "$file")"
        if [[ "${found_begin:-0}" != "1" || "${found_end:-0}" != "1" ]]; then
            printf 'ERROR: %s: HAND fence pair "%s" is absent or malformed — aborting; generator will not overwrite unparseable HAND region\n' \
                "$file" "$name" >&2
            ok=0
        fi
    done
    [[ "$ok" == 1 ]]
}

# Extract content between a named HAND fence pair, verbatim (excluding fence lines).
# Prints the content to stdout; empty if the block is empty.
_extract_hand() {
    local file="$1" name="$2"
    awk -v n="$name" '
        $0 == "<!-- BEGIN HAND: " n " -->" { in_b=1; next }
        $0 == "<!-- END HAND: " n " -->" { in_b=0; next }
        in_b { print }
    ' "$file"
}

# ---------------------------------------------------------------------------
# Identity derivation (MANAGED: identity)
# Precedence: README H1 + lead paragraph → CLAUDE.md first line after H1 → basename
# ---------------------------------------------------------------------------

# Returns the short project title (first line of identity, cap 200 chars).
_derive_project_title() {
    local readme="$REPO_ROOT/README.md" result=""
    if [[ -f "$readme" ]]; then
        result="$(awk '/^# / { sub(/^# /, ""); print; exit }' "$readme" 2>/dev/null)"
    fi
    if [[ -z "$result" && -f "$REPO_ROOT/CLAUDE.md" ]]; then
        # Mirror regenerate-orientation-cache.sh: first non-blank line after H1.
        # Review: code-reviewer — use getline-into-variable form to avoid infinite
        # loop when H1 is the last line (getline returns 0 at EOF).
        result="$(awk '/^# / { while ((getline line) > 0) { if (line !~ /^[[:space:]]*$/) { print line; exit } } exit }' \
            "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -1)"
    fi
    [[ -z "$result" ]] && result="$(basename "$REPO_ROOT")"
    printf '%s' "$result" | tr -d '\n' | cut -c1-200
}

# Returns the full identity block: H1 title + lead paragraph (separated by blank line).
_derive_identity() {
    local readme="$REPO_ROOT/README.md" result="" title="" lead=""
    if [[ -f "$readme" ]]; then
        title="$(awk '/^# / { sub(/^# /, ""); print; exit }' "$readme" 2>/dev/null)"
        if [[ -n "$title" ]]; then
            # Extract first non-blank paragraph after the H1 (up to the next blank line).
            lead="$(awk '
                /^# / { found_h1=1; next }
                found_h1 && !in_para && /^[[:space:]]*$/ { next }
                found_h1 && !in_para && !/^[[:space:]]*$/ { in_para=1 }
                in_para && /^[[:space:]]*$/ { exit }
                in_para { print }
            ' "$readme" 2>/dev/null)"
            result="$title"
            [[ -n "$lead" ]] && result="${result}

${lead}"
        fi
    fi
    if [[ -z "$result" && -f "$REPO_ROOT/CLAUDE.md" ]]; then
        result="$(awk '/^# / { while ((getline line) > 0) { if (line !~ /^[[:space:]]*$/) { print line; exit } } exit }' \
            "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -1)"
    fi
    [[ -z "$result" ]] && result="Project at $(basename "$REPO_ROOT")"
    printf '%s' "$result"
}

# ---------------------------------------------------------------------------
# Progress derivation (MANAGED: progress)
# Sources: orientation_cache Counters + week-changelog Highlights + git-log fallback
# ---------------------------------------------------------------------------

_derive_progress() {
    local wc_dir="$STATE_ROOT/week-changelog"
    local cache_file="$STATE_ROOT/orientation_cache.md"
    local output="" counters="" highlights=""

    # --- Counters from orientation_cache (coordinator-regen format; skip if section absent) ---
    if [[ -f "$cache_file" ]]; then
        counters="$(awk '
            /^## Counters$/ { in_s=1; next }
            in_s && /^## / { exit }
            in_s && !/^[[:space:]]*$/ { print }
        ' "$cache_file" 2>/dev/null)"
    fi

    # --- Highlights from week-changelog (if directory present) ---
    if [[ -d "$wc_dir" ]]; then
        # Scan current-week files for a Highlights section.
        local wc_file h
        for wc_file in "$wc_dir"/*.md; do
            [[ -f "$wc_file" ]] || continue
            h="$(awk '
                /^## Highlights$/ { in_s=1; next }
                in_s && /^## / { exit }
                in_s && !/^[[:space:]]*$/ { print }
            ' "$wc_file" 2>/dev/null)"
            if [[ -n "$h" ]]; then
                highlights="$h"
                break
            fi
        done

        # Fallback: most recent archived pending-release.md.
        if [[ -z "$highlights" ]]; then
            local repo_dir
            repo_dir="$(dirname "$STATE_ROOT")"
            local latest_pr
            latest_pr="$(find "${repo_dir}/archive/week-changelogs" -name "*pending-release*.md" \
                2>/dev/null | sort | tail -1)"
            if [[ -f "$latest_pr" ]]; then
                highlights="$(awk '
                    /^## Highlights$/ { in_s=1; next }
                    in_s && /^## / { exit }
                    in_s && !/^[[:space:]]*$/ { print }
                ' "$latest_pr" 2>/dev/null)"
            fi
        fi
    fi

    # --- Assemble output ---
    if [[ -n "$counters" ]]; then
        output="${output}**Activity counters:**

${counters}

"
    fi

    if [[ -n "$highlights" ]]; then
        output="${output}**Recent highlights:**

${highlights}

"
    fi

    # git-log fallback: use when week-changelog absent OR when both counters and highlights are empty.
    if [[ ! -d "$wc_dir" || ( -z "$highlights" && -z "$counters" ) ]]; then
        local log_out
        log_out="$(git -C "$REPO_ROOT" log --oneline -8 2>/dev/null || true)"
        if [[ -n "$log_out" ]]; then
            output="${output}**Recent commits:**

\`\`\`
${log_out}
\`\`\`

"
        fi
    fi

    if [[ -z "$output" ]]; then
        output="_No progress data available. Run \`regenerate-orientation-cache.sh\` and \`/workday-complete\` to populate._"
    fi

    # Trim trailing newlines so the fence closes cleanly.
    printf '%s' "$output" | awk '
        { lines[NR]=$0 }
        END {
            last=NR
            while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--
            for (i=1; i<=last; i++) print lines[i]
        }
    '
}

# ---------------------------------------------------------------------------
# Link rewriting for MANAGED sections
# The output file lives at docs/exec-summary.md — one directory below repo
# root — so any bare repo-root-relative markdown link target needs a `../`
# prefix to resolve correctly from that location.
# ---------------------------------------------------------------------------

# Reads MANAGED-section content on stdin, rewrites inline markdown link targets
# `](TARGET)` by prefixing `../` when TARGET is a bare repo-root-relative path.
# Leaves external URLs, mailto:, anchors, absolute paths, and already-relative
# targets (./ or ../) untouched. Reference-style links and autolinks are out
# of scope (inline `](...)` targets only).
# Negative-spec: does NOT touch HAND-section content (never called on it).
_rewrite_managed_links() {
    awk '
        {
            line = $0
            out = ""
            rest = line
            while ((idx = index(rest, "](")) > 0) {
                out = out substr(rest, 1, idx + 1)
                rest = substr(rest, idx + 2)
                close_idx = index(rest, ")")
                if (close_idx == 0) {
                    out = out rest
                    rest = ""
                    break
                }
                target = substr(rest, 1, close_idx - 1)
                skip = 0
                if (target ~ /^https?:\/\//) skip = 1
                else if (target ~ /^mailto:/) skip = 1
                else if (target ~ /^#/) skip = 1
                else if (target ~ /^\//) skip = 1
                else if (target ~ /^\.\.\//) skip = 1
                else if (target ~ /^\.\//) skip = 1
                if (!skip && target != "") {
                    target = "../" target
                }
                out = out target ")"
                rest = substr(rest, close_idx + 1)
            }
            out = out rest
            print out
        }
    '
}

# ---------------------------------------------------------------------------
# Placeholder text for HAND sections in new files (matches template text)
# ---------------------------------------------------------------------------

_HAND_SPECIAL_PLACEHOLDER='_What sets this project apart from similar efforts. What problems does it solve that nothing else
does? Distil the differentiator into 2–4 sentences. The generator preserves this verbatim on
every refresh — edit once, it survives regen._'

_HAND_GOALS_PLACEHOLDER='_The 2–4 most important near-term objectives. What does success look like in the next 4–8 weeks?
Reference concrete milestones or workstreams where useful. The generator preserves this verbatim
on every refresh — edit once, it survives regen._'

# ---------------------------------------------------------------------------
# File emission
# ---------------------------------------------------------------------------

_emit_file() {
    local project_title="$1" repo_name="$2" identity="$3"
    local hand_special="$4" hand_goals="$5" progress="$6"

    printf '%s\n' '---'
    printf 'kind: exec-summary\n'
    printf 'repo: %s\n' "$repo_name"
    printf 'project: %s\n' "$project_title"
    printf 'generated: %s\n' "$ISO_NOW"
    printf 'generator: bin/generate-exec-summary.sh\n'
    printf '%s\n' '---'
    printf '\n'
    printf '# %s — Executive Summary\n' "$project_title"
    printf '\n'
    printf '> One-screen "why this project matters" brief. The two MANAGED sections are refreshed by\n'
    printf '> `bin/generate-exec-summary.sh` from disk artifacts; the two HAND sections are yours to\n'
    printf '> author once and are preserved verbatim on every regeneration.\n'
    printf '>\n'
    printf '> Spec backlink: docs/wiki/exec-summary-artifact.md\n'
    printf '\n'
    printf '## What this project is\n'
    printf '\n'
    printf '<!-- BEGIN MANAGED: identity -->\n'
    printf '%s\n' "$identity"
    printf '<!-- END MANAGED: identity -->\n'
    printf '\n'
    printf '## What makes it special\n'
    printf '\n'
    printf '<!-- BEGIN HAND: special -->\n'
    printf '%s\n' "$hand_special"
    printf '<!-- END HAND: special -->\n'
    printf '\n'
    printf '## Near-term goals\n'
    printf '\n'
    printf '<!-- BEGIN HAND: goals -->\n'
    printf '%s\n' "$hand_goals"
    printf '<!-- END HAND: goals -->\n'
    printf '\n'
    printf '## Progress\n'
    printf '\n'
    printf '<!-- BEGIN MANAGED: progress -->\n'
    printf '%s\n' "$progress"
    printf '<!-- END MANAGED: progress -->\n'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

REPO_NAME="$(basename "$REPO_ROOT")"
PROJECT_TITLE="$(_derive_project_title)"
IDENTITY="$(_derive_identity)"
PROGRESS="$(_derive_progress)"
IDENTITY="$(printf '%s' "$IDENTITY" | _rewrite_managed_links)"
PROGRESS="$(printf '%s' "$PROGRESS" | _rewrite_managed_links)"

if [[ -f "$TARGET" ]]; then
    # Existing file: validate HAND fences before doing anything else.
    # Fail-loud (exit 1) and write nothing if validation fails.
    if ! _validate_hand_fences "$TARGET"; then
        exit 1
    fi
    HAND_SPECIAL="$(_extract_hand "$TARGET" "special")"
    HAND_GOALS="$(_extract_hand "$TARGET" "goals")"
else
    # New file: seed HAND sections with placeholder text.
    HAND_SPECIAL="$_HAND_SPECIAL_PLACEHOLDER"
    HAND_GOALS="$_HAND_GOALS_PLACEHOLDER"
fi

OUTPUT="$(_emit_file "$PROJECT_TITLE" "$REPO_NAME" "$IDENTITY" "$HAND_SPECIAL" "$HAND_GOALS" "$PROGRESS")"

if [[ "$CHECK_ONLY" == 1 ]]; then
    printf '%s\n' "$OUTPUT"
else
    if [[ ! -f "$TARGET" ]]; then
        # No-clobber: create parent directory if needed.
        mkdir -p "$(dirname "$TARGET")"
        printf '%s\n' "$OUTPUT" > "$TARGET"
        printf 'generate-exec-summary: created %s\n' "$TARGET" >&2
    else
        printf '%s\n' "$OUTPUT" > "$TARGET"
        printf 'generate-exec-summary: updated %s\n' "$TARGET" >&2
    fi
fi
