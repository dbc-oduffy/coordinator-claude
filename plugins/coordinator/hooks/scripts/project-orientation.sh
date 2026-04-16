#!/bin/bash
# SessionStart hook: inject project orientation documents into context
# Convention-based discovery — reads what exists, skips what doesn't.
# Subsumes the old repomap-sessionstart.sh (staleness check + content injection).
#
# Flags:
#   --lightweight   Skip heavy operations (scc, git log). Used on /clear where
#                   the project hasn't changed since 2 minutes ago.

LIGHTWEIGHT=false
for arg in "$@"; do
  case "$arg" in
    --lightweight) LIGHTWEIGHT=true ;;
  esac
done

# RAM cache check — prefer compact cache over raw docs
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
CACHE="${REPO_ROOT:-.}/tasks/orientation_cache.md"

if [ -f "$CACHE" ]; then
    # Extract git HEAD from YAML frontmatter (portable across GNU/BSD sed)
    CACHE_HEAD=$(grep '^git_head_at_generation:' "$CACHE" | head -1 | sed 's/.*: *//; s/["'"'"'[:space:]]//g')

    if [ -n "$CACHE_HEAD" ] && git cat-file -t "$CACHE_HEAD" &>/dev/null; then
        # Programmatic staleness: has anything the cache describes actually changed?
        # These are the paths whose state the orientation cache summarizes.
        CHANGED=$(git diff --name-only "${CACHE_HEAD}..HEAD" -- \
            plugins/ tasks/health-*.md tasks/architecture-atlas/ \
            .github/ CLAUDE.md DIRECTORY.md tasks/ \
            2>/dev/null | head -1)

        if [ -z "$CHANGED" ]; then
            # No cache-relevant changes since generation — cache is fresh
            echo ""
            echo "── Orientation (RAM cache, structurally current) ──"
            cat "$CACHE"
            echo ""
            echo "── Orientation: 1 document loaded (from cache) ──"
            exit 0
        fi
        # Cache-relevant files changed — emit stale cache with warning
        echo ""
        echo "── Orientation (RAM cache, stale — run /workday-start to refresh) ──"
        cat "$CACHE"
        echo ""
        echo "── Orientation: 1 document loaded (stale cache — $CHANGED and possibly others changed since generation) ──"
        exit 0
    fi
    # CACHE_HEAD missing or invalid — emit cache without staleness guarantee
    echo ""
    echo "── Orientation (RAM cache, HEAD unverifiable) ──"
    cat "$CACHE"
    echo ""
    echo "── Orientation: 1 document loaded (from cache, staleness unknown) ──"
    exit 0
fi

# Cache absent entirely — inject lightweight pointers, EM reads full files on demand.

# ── Lightweight mode (used on /clear) ────────────────────────────────────
# On clear the project hasn't changed — just re-emit branch + pointers.
if [ "$LIGHTWEIGHT" = true ]; then
    echo ""
    echo "── Orientation (lightweight — /clear) ──"
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    [ -n "$BRANCH" ] && echo "  Branch: $BRANCH"
    echo "  Full orientation available on next fresh session start."
    exit 0
fi

# ── Full mode (startup / compact) ────────────────────────────────────────

echo ""
echo "── Orientation (no fresh cache — pointers only) ──"

pointer_doc() {
    local label="$1"
    shift
    for path in "$@"; do
        if [ -f "$path" ]; then
            local lines
            lines=$(wc -l < "$path" | tr -d ' ')
            echo "  $label: $path (${lines} lines) — read when needed"
            return 0
        fi
    done
    echo "  $label: not found"
    return 1
}

found=0

# Repo map — pointer with staleness note
REPOMAP="tasks/repomap.md"
if [ -f "$REPOMAP" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        file_epoch=$(stat -f %m "$REPOMAP" 2>/dev/null)
    else
        file_epoch=$(stat -c %Y "$REPOMAP" 2>/dev/null)
    fi
    stale_note=""
    if [ -n "$file_epoch" ]; then
        now_epoch=$(date +%s)
        age_hours=$(( (now_epoch - file_epoch) / 3600 ))
        if [ "$age_hours" -ge 24 ]; then
            stale_note=" [STALE: ${age_hours}h old — run /generate-repomap]"
        fi
    fi
    lines=$(wc -l < "$REPOMAP" | tr -d ' ')
    echo "  Repo Map: $REPOMAP (${lines} lines)${stale_note} — read when needed"
    found=$((found + 1))
else
    echo "  Repo Map: not found — run /generate-repomap to create"
fi

# Directory
pointer_doc "Directory" "DIRECTORY.md" "docs/DIRECTORY.md" && found=$((found + 1))

# --- Project vitals (fallback path only) ---
echo ""
echo "── Project Vitals ──"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -n "$BRANCH" ]; then
    echo "  Branch: $BRANCH"
    echo "  Recent commits:"
    git log --oneline -5 2>/dev/null | while read -r line; do
        echo "    $line"
    done
fi

# Code statistics (scc) — cached by git HEAD to avoid rescanning on every session
SCC_CACHE="${REPO_ROOT:-.}/tasks/.scc-cache"
SCC_CACHE_HEAD=""
if [ -f "$SCC_CACHE" ]; then
    SCC_CACHE_HEAD=$(head -1 "$SCC_CACHE")
fi
CURRENT_HEAD=$(git rev-parse HEAD 2>/dev/null)

if [ -n "$SCC_CACHE_HEAD" ] && [ "$SCC_CACHE_HEAD" = "$CURRENT_HEAD" ]; then
    # Cache hit — emit stored output (skip first line which is the HEAD marker)
    SCC_OUT=$(tail -n +2 "$SCC_CACHE")
else
    # Cache miss — run scc and store
    SCC_CMD=""
    for cmd in scc "$HOME/bin/scc" "$HOME/bin/scc.exe"; do
      if command -v "$cmd" &>/dev/null || [ -x "$cmd" ]; then
        SCC_CMD="$cmd"
        break
      fi
    done
    if [ -n "$SCC_CMD" ]; then
      SCC_OUT=$("$SCC_CMD" --no-complexity --no-cocomo --no-duplicates --sort code 2>/dev/null | head -20)
      if [ -n "$SCC_OUT" ] && [ -n "$CURRENT_HEAD" ]; then
        SCC_TMP=$(mktemp "${SCC_CACHE}.XXXXXX" 2>/dev/null) && {
          { echo "$CURRENT_HEAD"; echo "$SCC_OUT"; } > "$SCC_TMP"
          mv -f "$SCC_TMP" "$SCC_CACHE" 2>/dev/null
        } || { echo "$CURRENT_HEAD"; echo "$SCC_OUT"; } > "$SCC_CACHE" 2>/dev/null
      fi
    fi
fi
if [ -n "$SCC_OUT" ]; then
    echo "  Code stats (scc):"
    echo "$SCC_OUT" | while read -r line; do echo "    $line"; done
fi

# Active plan files
PLANS=$(ls tasks/*/todo.md 2>/dev/null)
if [ -n "$PLANS" ]; then
    echo "  Active plans:"
    echo "$PLANS" | while read -r p; do echo "    $p"; done
fi

# Pending handoffs
HANDOFFS=$(ls tasks/handoffs/*.md 2>/dev/null)
if [ -n "$HANDOFFS" ]; then
    echo "  Pending handoffs:"
    echo "$HANDOFFS" | while read -r h; do echo "    $h"; done
fi

# Lessons file freshness
if [ -f "tasks/lessons.md" ]; then
    LESSON_LINES=$(wc -l < "tasks/lessons.md" | tr -d ' ')
    echo "  Lessons: tasks/lessons.md (${LESSON_LINES} lines)"
fi

echo ""
echo "No orientation cache. Run /update-docs or /workday-start to generate one."
echo "── Orientation: $found document(s) available (not loaded — read on demand) ──"
