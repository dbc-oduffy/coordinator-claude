#!/usr/bin/env bash
# verify-orientation-cache-sync.sh — Schema verifier for state/orientation_cache.md.
#
# Spec backlink: docs/plans/2026-05-18-orientation-cache-authoring-discipline.md
# Schema:       plugins/coordinator/pipelines/workday-start-internals.md § 5.5
# Producer:     plugins/coordinator/bin/regenerate-orientation-cache.sh
#
# Filename ends in -sync.sh to participate in /update-docs Phase 11b's verifier glob.
# Despite the suffix this is a schema verifier, not a snippet-sync check.
#
# Usage:
#   verify-orientation-cache-sync.sh           Verify the cache. Exit non-zero on violation.
#   verify-orientation-cache-sync.sh --list    Print the cache path that would be checked.
#
# Hard invariants enforced:
#   - File length ≤35 lines.
#   - Frontmatter has generated_by (slug, no parens), generated_at, git_head_at_generation.
#   - Every `## <Section>` heading is in the canonical schema set.
#   - Counter lines match the integer-terminated regex.
#   - Workstream lines match the name-only regex.
#   - Pinboard ≤1 line, ISO-date + writer-slug shape.
#   - Trust caveats ≤5 lines.
#   - If *.uproject present in repo, Trust caveats section MUST be present and first line
#     MUST contain "Unreal Engine project detected" (detector-regression guard).
#
# No --fix mode by design. Violations are structural — fix by regenerating via
# bin/regenerate-orientation-cache.sh, not by patching the file in place.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CACHE_FILE="$REPO_ROOT/state/orientation_cache.md"

if [[ "${1:-}" == "--list" ]]; then
    echo "$CACHE_FILE"
    exit 0
fi

if [[ ! -f "$CACHE_FILE" ]]; then
    echo "verify-orientation-cache-sync: no cache file at $CACHE_FILE — nothing to verify"
    exit 0
fi

VIOLATIONS=()

# Canonical schema headings (no leading `## `).
ALLOWED_HEADINGS=(
    "Project"
    "Trust caveats"
    "Counters"
    "Active workstreams"
    "Rechecks due ≤7 days"
    "Branch"
    "Auto-push health"
    "Pinboard"
)

is_allowed_heading() {
    local h="$1"
    for ok in "${ALLOWED_HEADINGS[@]}"; do
        [[ "$h" == "$ok" ]] && return 0
    done
    return 1
}

# --- File length ---
LINE_COUNT=$(wc -l < "$CACHE_FILE" | tr -d ' ')
if [[ "$LINE_COUNT" -gt 35 ]]; then
    VIOLATIONS+=("file length $LINE_COUNT exceeds 35-line ceiling")
fi

# --- Frontmatter ---
FM_END=$(awk '/^---$/{n++; if (n==2) {print NR; exit}}' "$CACHE_FILE")
if [[ -z "$FM_END" || "$FM_END" -le 1 ]]; then
    VIOLATIONS+=("frontmatter not found (expected --- delimited block at top of file)")
else
    FM_BODY=$(sed -n "2,$((FM_END-1))p" "$CACHE_FILE")
    GENERATED_BY=$(printf '%s\n' "$FM_BODY" | awk -F': *' '/^generated_by:/{print $2; exit}')
    GENERATED_AT=$(printf '%s\n' "$FM_BODY" | awk -F': *' '/^generated_at:/{print $2; exit}')
    GIT_HEAD_AT=$(printf '%s\n' "$FM_BODY" | awk -F': *' '/^git_head_at_generation:/{print $2; exit}')

    if [[ -z "$GENERATED_BY" ]]; then
        VIOLATIONS+=("frontmatter missing generated_by")
    elif ! [[ "$GENERATED_BY" =~ ^[a-z0-9-]+$ ]]; then
        VIOLATIONS+=("frontmatter generated_by='$GENERATED_BY' is not a single lowercase slug (no parentheticals, no 'patched by' prose allowed)")
    fi
    [[ -z "$GENERATED_AT" ]] && VIOLATIONS+=("frontmatter missing generated_at")
    [[ -z "$GIT_HEAD_AT" ]] && VIOLATIONS+=("frontmatter missing git_head_at_generation")
fi

# --- Top-level headings ---
while IFS= read -r line; do
    heading="${line#\#\# }"
    if ! is_allowed_heading "$heading"; then
        VIOLATIONS+=("out-of-schema heading: '## $heading'")
    fi
done < <(grep -E '^## ' "$CACHE_FILE" || true)

# --- Counter lines ---
COUNTER_LINES=$(awk '/^## Counters$/{in_s=1; next} /^## /{in_s=0} in_s && /^- /{print}' "$CACHE_FILE")
if [[ -n "$COUNTER_LINES" ]]; then
    while IFS= read -r line; do
        # Review: code-reviewer — counter labels are restricted to [A-Za-z0-9 /-] by verifier
        # convention. Any label using characters outside this set is a deliberate schema extension
        # that requires updating this verifier, the routine, AND the schema table together.
        if ! [[ "$line" =~ ^-\ \*\*[A-Za-z][A-Za-z0-9\ /\-]*:\*\*\ [0-9]+(\.|$) ]]; then
            VIOLATIONS+=("counter line fails integer-terminated regex: '$line'")
        fi
    done <<< "$COUNTER_LINES"
fi

# --- Workstream lines ---
WORKSTREAM_LINES=$(awk '/^## Active workstreams$/{in_s=1; next} /^## /{in_s=0} in_s && NF>0{print}' "$CACHE_FILE")
WS_COUNT=0
if [[ -n "$WORKSTREAM_LINES" ]]; then
    while IFS= read -r line; do
        WS_COUNT=$((WS_COUNT+1))
        if ! [[ "$line" =~ ^[0-9]+\.\ [A-Za-z] ]]; then
            VIOLATIONS+=("workstream line fails name-only regex: '$line'")
        fi
        if [[ ${#line} -gt 84 ]]; then
            VIOLATIONS+=("workstream line exceeds 80-char body cap: '$line'")
        fi
    done <<< "$WORKSTREAM_LINES"
    [[ "$WS_COUNT" -gt 10 ]] && VIOLATIONS+=("Active workstreams section has $WS_COUNT entries (max 10)")
fi

# --- Pinboard lines ---
PINBOARD_LINES=$(awk '/^## Pinboard$/{in_s=1; next} /^## /{in_s=0} in_s && /^- /{print}' "$CACHE_FILE")
PB_COUNT=0
if [[ -n "$PINBOARD_LINES" ]]; then
    while IFS= read -r line; do
        PB_COUNT=$((PB_COUNT+1))
        if ! [[ "$line" =~ ^-\ [0-9]{4}-[0-9]{2}-[0-9]{2}\ [a-z0-9-]+:\ .{1,120}$ ]]; then
            VIOLATIONS+=("pinboard line fails shape '- YYYY-MM-DD writer-slug: <note>': '$line'")
        fi
    done <<< "$PINBOARD_LINES"
    [[ "$PB_COUNT" -gt 1 ]] && VIOLATIONS+=("Pinboard section has $PB_COUNT lines (max 1 — one-slot only)")
fi

# --- Auto-push health lines ---
# Catches runaway multi-line output or gross format corruption; mirrors the
# per-section shape checks above. Loose by design (not a linter): ≤1 line, and if
# present it must be the `- ⚠ <N> unpushed commit(s) ...` bullet the routine emits.
APH_LINES=$(awk '/^## Auto-push health$/{in_s=1; next} /^## /{in_s=0} in_s && /^- /{print}' "$CACHE_FILE")
APH_COUNT=0
if [[ -n "$APH_LINES" ]]; then
    while IFS= read -r line; do
        APH_COUNT=$((APH_COUNT+1))
        if ! [[ "$line" =~ ^-\ ⚠\ [0-9]+\ unpushed\ commit ]]; then
            VIOLATIONS+=("Auto-push health line fails shape '- ⚠ <N> unpushed commit(s) ...': '$line'")
        fi
    done <<< "$APH_LINES"
    [[ "$APH_COUNT" -gt 1 ]] && VIOLATIONS+=("Auto-push health section has $APH_COUNT lines (max 1)")
fi

# --- Trust caveats lines ---
TC_LINES=$(awk '/^## Trust caveats$/{in_s=1; next} /^## /{in_s=0} in_s && /^- /{print}' "$CACHE_FILE")
TC_COUNT=0
TC_FIRST=""
if [[ -n "$TC_LINES" ]]; then
    while IFS= read -r line; do
        TC_COUNT=$((TC_COUNT+1))
        [[ "$TC_COUNT" == 1 ]] && TC_FIRST="$line"
    done <<< "$TC_LINES"
    [[ "$TC_COUNT" -gt 5 ]] && VIOLATIONS+=("Trust caveats section has $TC_COUNT lines (max 5)")
fi

# --- UE detector-regression guard ---
UPROJECT_PATH=""
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    UPROJECT_PATH="$(git -C "$REPO_ROOT" ls-files '*.uproject' 2>/dev/null | head -1)"
    # Review: code-reviewer — exclusions must match the producer's find exactly to avoid false
    # verifier failures when a *.uproject sits inside node_modules/ or .git/.
    [[ -z "$UPROJECT_PATH" ]] && UPROJECT_PATH="$(find "$REPO_ROOT" -maxdepth 6 -name '*.uproject' -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | head -1)"
else
    UPROJECT_PATH="$(find "$REPO_ROOT" -maxdepth 6 -name '*.uproject' 2>/dev/null | head -1)"
fi

if [[ -n "$UPROJECT_PATH" ]]; then
    if [[ -z "$TC_LINES" ]]; then
        VIOLATIONS+=("detector-output missing: *.uproject present in repo ($UPROJECT_PATH) but ## Trust caveats section absent — regenerate via bin/regenerate-orientation-cache.sh")
    elif ! [[ "$TC_FIRST" == *"Unreal Engine project detected"* ]]; then
        VIOLATIONS+=("detector-output corrupted: *.uproject present but first Trust caveats line does not contain 'Unreal Engine project detected': '$TC_FIRST'")
    fi
fi

# --- Report ---
if [[ ${#VIOLATIONS[@]} -gt 0 ]]; then
    echo "verify-orientation-cache-sync: FAIL ($CACHE_FILE)" >&2
    for v in "${VIOLATIONS[@]}"; do
        echo "  - $v" >&2
    done
    echo "" >&2
    echo "Fix: regenerate the cache via bin/regenerate-orientation-cache.sh (do NOT patch in place)." >&2
    exit 1
fi

echo "verify-orientation-cache-sync: OK ($CACHE_FILE, $LINE_COUNT lines)"
