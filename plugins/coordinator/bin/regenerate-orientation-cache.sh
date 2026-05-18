#!/usr/bin/env bash
# regenerate-orientation-cache.sh — Single source-of-truth derivation for tasks/orientation_cache.md.
#
# Spec backlink: docs/plans/2026-05-18-orientation-cache-authoring-discipline.md
# Schema: plugins/coordinator/pipelines/workday-start-internals.md § 5.5
# Verifier: plugins/coordinator/bin/verify-orientation-cache-sync.sh
#
# Usage:
#   regenerate-orientation-cache.sh --invoker <workday-start|update-docs|session-end|handoff>
#   regenerate-orientation-cache.sh --invoker <slug> --check       Print to stdout, don't write
#
# Writer tiers:
#   ceremony    (workday-start, update-docs)  — full regen, clears pinboard
#   mid-session (session-end, handoff)         — preserves all non-pinboard sections from existing
#                                                 file; pinboard handled via --pinboard if supplied
#
# Mid-session pinboard writes:
#   regenerate-orientation-cache.sh --invoker session-end --pinboard "<one-line note>"
#   (overwrites the single pinboard slot; pass --pinboard "" to clear)

set -euo pipefail

INVOKER=""
CHECK_ONLY=0
PINBOARD_NEW=""
PINBOARD_SET=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --invoker) INVOKER="$2"; shift 2 ;;
        --check)   CHECK_ONLY=1; shift ;;
        --pinboard) PINBOARD_NEW="$2"; PINBOARD_SET=1; shift 2 ;;
        *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$INVOKER" ]]; then
    echo "ERROR: --invoker <slug> required (workday-start|update-docs|session-end|handoff)" >&2
    exit 2
fi

case "$INVOKER" in
    workday-start|update-docs)            TIER=ceremony ;;
    session-end|handoff)                  TIER=mid-session ;;
    *) echo "ERROR: unknown invoker: $INVOKER (expected workday-start|update-docs|session-end|handoff)" >&2; exit 2 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CACHE_FILE="$REPO_ROOT/tasks/orientation_cache.md"

if [[ ! -d "$REPO_ROOT/tasks" ]]; then
    echo "regenerate-orientation-cache: no tasks/ directory at $REPO_ROOT — skipping (per schema spec)" >&2
    exit 0
fi

ISO_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_HEAD="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"

# -------- Detect *.uproject anywhere in repo (UE trust-caveat trigger) --------
UPROJECT_PATH=""
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Prefer tracked files first; fall back to untracked scan.
    UPROJECT_PATH="$(git -C "$REPO_ROOT" ls-files '*.uproject' 2>/dev/null | head -1)"
    if [[ -z "$UPROJECT_PATH" ]]; then
        UPROJECT_PATH="$(find "$REPO_ROOT" -maxdepth 6 -name '*.uproject' -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | head -1)"
        # Strip repo-root prefix for tidy citation.
        [[ -n "$UPROJECT_PATH" ]] && UPROJECT_PATH="${UPROJECT_PATH#"$REPO_ROOT/"}"
    fi
else
    UPROJECT_PATH="$(find "$REPO_ROOT" -maxdepth 6 -name '*.uproject' 2>/dev/null | head -1)"
    [[ -n "$UPROJECT_PATH" ]] && UPROJECT_PATH="${UPROJECT_PATH#"$REPO_ROOT/"}"
fi

# -------- Derive the Project line --------
# Precedence (first non-empty wins):
#   1. .claude/project-identity.txt  — explicit override (first non-blank, non-comment line)
#   2. CLAUDE.md first non-blank line after the first H1 (fallback for repos that haven't
#      authored an explicit identity)
#   3. "Project at <basename>" (final fallback so the section is never absent)
PROJECT_LINE=""
IDENTITY_FILE="$REPO_ROOT/.claude/project-identity.txt"
if [[ -f "$IDENTITY_FILE" ]]; then
    PROJECT_LINE="$(awk '/^[[:space:]]*#/ {next} /^[[:space:]]*$/ {next} {print; exit}' "$IDENTITY_FILE" 2>/dev/null)"
fi
if [[ -z "$PROJECT_LINE" && -f "$REPO_ROOT/CLAUDE.md" ]]; then
    PROJECT_LINE="$(awk '/^# / { getline; while (/^$/) getline; print; exit }' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -1)"
fi
if [[ -z "$PROJECT_LINE" ]]; then
    PROJECT_LINE="Project at $(basename "$REPO_ROOT")"
fi
# Enforce 1-line discipline (strip newlines). Sanity cap at 400 chars — long
# enough for a substantive identity sentence, short enough to stay on one line
# in any reasonable terminal. The 35-line file ceiling is the structural cap.
PROJECT_LINE="$(printf '%s' "$PROJECT_LINE" | tr -d '\n' | cut -c1-400)"

# -------- Counters (from disk) --------
# Counter helpers: always emit exactly one integer to stdout, never fail.
_clean_int() { tr -d ' \n\r\t' < <(printf '%s' "${1:-0}"); }

count_handoffs_ready() {
    local d="$REPO_ROOT/tasks/handoffs" n=0 f
    [[ ! -d "$d" ]] && { echo 0; return; }
    for f in "$d"/*.md; do
        [[ -f "$f" ]] || continue
        if grep -q 'deployment_state: ready_to_fire' "$f" 2>/dev/null && \
           ! grep -q 'kind: spinoff' "$f" 2>/dev/null; then
            n=$((n+1))
        fi
    done
    echo "$n"
}
count_spinoffs_ready() {
    local d="$REPO_ROOT/tasks/handoffs" n=0 f
    [[ ! -d "$d" ]] && { echo 0; return; }
    for f in "$d"/*.md; do
        [[ -f "$f" ]] || continue
        if grep -q 'deployment_state: ready_to_fire' "$f" 2>/dev/null && \
           grep -q 'kind: spinoff' "$f" 2>/dev/null; then
            n=$((n+1))
        fi
    done
    echo "$n"
}
count_handoffs_gated() {
    local d="$REPO_ROOT/tasks/handoffs" n=0 f
    [[ ! -d "$d" ]] && { echo 0; return; }
    for f in "$d"/*.md; do
        [[ -f "$f" ]] || continue
        grep -q 'deployment_state: awaiting_gate' "$f" 2>/dev/null && n=$((n+1))
    done
    echo "$n"
}
count_bug_backlog() {
    local f="$REPO_ROOT/tasks/bug-backlog.md" n=0
    [[ ! -f "$f" ]] && { echo 0; return; }
    n=$(grep -cE '^- (BS-|\*\*BS-)' "$f" 2>/dev/null || echo 0)
    _clean_int "$n"
}
count_local_queue() {
    local f="$REPO_ROOT/tasks/improvement-queue.md" n=0
    [[ ! -f "$f" ]] && { echo 0; return; }
    n=$(grep -cE '^- [0-9]{4}-[0-9]{2}-[0-9]{2}' "$f" 2>/dev/null || echo 0)
    _clean_int "$n"
}

HANDOFFS_READY=$(count_handoffs_ready)
SPINOFFS_READY=$(count_spinoffs_ready)
HANDOFFS_GATED=$(count_handoffs_gated)
BUG_BACKLOG=$(count_bug_backlog)
LOCAL_QUEUE=$(count_local_queue)

# -------- Active workstreams (≤10 from tracker) --------
emit_workstreams() {
    local tracker=""
    for cand in "$REPO_ROOT/tasks/project-tracker.md" "$REPO_ROOT/docs/project-tracker.md" "$REPO_ROOT/tasks/tracker.md"; do
        [[ -f "$cand" ]] && { tracker="$cand"; break; }
    done
    [[ -z "$tracker" ]] && return
    # Extract `### N. Name` entries under `## Active Workstreams` (the canonical shape in
    # docs/project-tracker.md). Fall back to `^N. Name` if H3 form not present.
    awk '
        BEGIN { in_section=0; count=0; saw_h3=0 }
        /^## / {
            if (tolower($0) ~ /^## active +workstreams/) { in_section=1; next }
            else if (in_section) { exit }
        }
        in_section && /^### [0-9]+\. / && count < 10 {
            sub(/^### /, "")
            sub(/ *\([^)]*\) *$/, "")
            print
            count++
            saw_h3=1
        }
        in_section && !saw_h3 && /^[0-9]+\. / && count < 10 {
            sub(/ *\([^)]*\) *$/, "")
            print
            count++
        }
    ' "$tracker" 2>/dev/null
}

# -------- Rechecks due ≤7 days --------
emit_rechecks() {
    local today_epoch threshold_epoch f date_str date_epoch base
    today_epoch=$(date -u +%s)
    threshold_epoch=$((today_epoch + 7*86400))
    for f in "$REPO_ROOT"/tasks/*-recheck-due-*.md; do
        [[ -f "$f" ]] || continue
        base="$(basename "$f")"
        # Extract YYYY-MM-DD from filename.
        date_str="$(echo "$base" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)"
        [[ -z "$date_str" ]] && continue
        date_epoch=$(date -u -d "$date_str" +%s 2>/dev/null || echo 0)
        [[ "$date_epoch" == 0 ]] && continue
        if [[ "$date_epoch" -le "$threshold_epoch" ]]; then
            echo "- \`tasks/$base\` (due $date_str)"
        fi
    done
}

# -------- Branch line --------
emit_branch_line() {
    local branch ahead behind
    branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    if git -C "$REPO_ROOT" rev-parse --verify origin/main >/dev/null 2>&1; then
        ahead=$(git -C "$REPO_ROOT" rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
        behind=$(git -C "$REPO_ROOT" rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
        echo "\`$branch\` — $ahead/$behind vs origin/main"
    else
        echo "\`$branch\` (no origin/main reference)"
    fi
}

# -------- Pinboard preservation (mid-session only) --------
# Ceremony writers clear pinboard. Mid-session writers preserve existing unless --pinboard given.
PINBOARD_FINAL=""
if [[ "$TIER" == "mid-session" ]]; then
    if [[ "$PINBOARD_SET" == 1 ]]; then
        PINBOARD_FINAL="$PINBOARD_NEW"
    elif [[ -f "$CACHE_FILE" ]]; then
        # Preserve existing pinboard line if present.
        PINBOARD_FINAL="$(awk '
            /^## Pinboard$/ { in_p=1; next }
            in_p && /^## / { exit }
            in_p && /^- / { sub(/^- /, ""); print; exit }
        ' "$CACHE_FILE" 2>/dev/null)"
    fi
fi

# Enforce one-slot only: if PINBOARD_FINAL contains a newline, take first line only.
PINBOARD_FINAL="$(printf '%s' "$PINBOARD_FINAL" | head -1)"

# -------- Emit cache --------
emit_cache() {
    cat <<EOF
---
generated_by: $INVOKER
generated_at: $ISO_NOW
git_head_at_generation: $GIT_HEAD
---

# Orientation Cache

## Project
$PROJECT_LINE
EOF

    if [[ -n "$UPROJECT_PATH" ]]; then
        cat <<EOF

## Trust caveats
- Unreal Engine project detected (\`$UPROJECT_PATH\`) — do NOT trust your training data on UE5 APIs, classes, or Blueprint semantics. Verify every claim via \`mcp__project-rag__*\` tools or dispatch \`game-dev:staff-game-dev\` (the Game Dev Reviewer). This applies to your delegates — restate it in every UE dispatch brief.
EOF
    fi

    # Counters — only emit non-zero lines, omit section if all zero.
    local counter_buf=""
    [[ "$HANDOFFS_READY" -gt 0 ]] && counter_buf+="- **Handoffs ready:** ${HANDOFFS_READY}."$'\n'
    [[ "$SPINOFFS_READY" -gt 0 ]] && counter_buf+="- **Spinoffs ready:** ${SPINOFFS_READY}."$'\n'
    [[ "$HANDOFFS_GATED" -gt 0 ]] && counter_buf+="- **Gated handoffs:** ${HANDOFFS_GATED}."$'\n'
    [[ "$BUG_BACKLOG" -gt 0 ]]    && counter_buf+="- **Bug backlog:** ${BUG_BACKLOG}."$'\n'
    [[ "$LOCAL_QUEUE" -gt 0 ]]    && counter_buf+="- **Improvement queue:** ${LOCAL_QUEUE}."$'\n'
    if [[ -n "$counter_buf" ]]; then
        printf '\n## Counters\n%s' "$counter_buf"
    fi

    local workstreams
    workstreams="$(emit_workstreams)"
    if [[ -n "$workstreams" ]]; then
        printf '\n## Active workstreams\n%s\n' "$workstreams"
    fi

    local rechecks
    rechecks="$(emit_rechecks)"
    if [[ -n "$rechecks" ]]; then
        printf '\n## Rechecks due ≤7 days\n%s\n' "$rechecks"
    fi

    printf '\n## Branch\n%s\n' "$(emit_branch_line)"

    if [[ -n "$PINBOARD_FINAL" ]]; then
        printf '\n## Pinboard\n- %s\n' "$PINBOARD_FINAL"
    fi
}

OUTPUT="$(emit_cache)"

if [[ "$CHECK_ONLY" == 1 ]]; then
    printf '%s\n' "$OUTPUT"
else
    printf '%s\n' "$OUTPUT" > "$CACHE_FILE"
    echo "regenerate-orientation-cache: wrote $CACHE_FILE (invoker=$INVOKER, tier=$TIER)" >&2
fi
