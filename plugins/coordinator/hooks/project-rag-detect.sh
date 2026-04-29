#!/usr/bin/env bash
# project-rag-detect.sh — SessionStart banner: generic project-RAG freshness
#
# Emits one of three banners to stdout (injected into Claude Code context):
#   fresh        — graph.db mtime >= HEAD commit time
#   stale (N)    — N commits behind HEAD
#   uninitialized — marker present but no graph.db found
#   (silent)     — no marker found, or holodeck context detected (let holodeck hook handle it)
#
# Kill-switch: set COORDINATOR_HOOK_PROJECT_RAG_DETECT_DISABLED=1 to disable
#
# Holodeck dedupe: if .holodeck/ directory or Saved/HolodeckProjectRag/ path is found
# walking up from cwd, this script exits silently — the holodeck-specific hook handles it.
#
# Generic project-RAG detection: looks for .project-rag/manifest.json walking up from cwd.

set -euo pipefail

# --- Kill-switch ---
if [ "${COORDINATOR_HOOK_PROJECT_RAG_DETECT_DISABLED:-}" = "1" ]; then
    exit 0
fi

# --- Helper: walk up from a directory looking for a marker ---
# Usage: find_marker_upward <start_dir> <relative_marker> [max_levels]
find_marker_upward() {
    local dir="$1"
    local marker="$2"
    local max_levels="${3:-6}"
    local i=0
    while [ $i -lt "$max_levels" ]; do
        local candidate="$dir/$marker"
        if [ -e "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
        local parent
        parent="$(dirname "$dir")"
        if [ "$parent" = "$dir" ]; then
            break
        fi
        dir="$parent"
        i=$((i + 1))
    done
    return 1
}

CWD="$(pwd)"

# --- Holodeck dedupe: positive context detection ---
# If we're in a holodeck UE project, let the holodeck-specific hook handle the banner.
if find_marker_upward "$CWD" ".holodeck" > /dev/null 2>&1; then
    exit 0
fi
if find_marker_upward "$CWD" "Saved/HolodeckProjectRag" > /dev/null 2>&1; then
    exit 0
fi

# --- Generic project-RAG detection via marker file ---
MANIFEST_PATH=""
if MANIFEST_PATH="$(find_marker_upward "$CWD" ".project-rag/manifest.json" 2>/dev/null)"; then
    :
else
    # No project-RAG in this repo — silent exit (no banner pollution)
    exit 0
fi

# Derive repo root from manifest path (.project-rag/ is at repo root)
PROJECT_RAG_DIR="$(dirname "$MANIFEST_PATH")"
REPO_ROOT="$(dirname "$PROJECT_RAG_DIR")"

# --- Locate graph.db ---
# Convention: .project-rag/graph.db alongside the manifest
DB_PATH="$PROJECT_RAG_DIR/graph.db"

# --- Uninitialized branch ---
if [ ! -f "$DB_PATH" ]; then
    echo "project-rag: UNINITIALIZED — marker found at $MANIFEST_PATH but no graph.db; run the project-RAG indexer before querying"
    exit 0
fi

# --- Stat mtime ---
# Cross-platform: try GNU stat, then macOS/BSD stat
if ! DB_MTIME_EPOCH="$(stat -c '%Y' "$DB_PATH" 2>/dev/null)"; then
    if ! DB_MTIME_EPOCH="$(stat -f '%m' "$DB_PATH" 2>/dev/null)"; then
        echo "project-rag: SKIP — could not stat graph.db (fail open)"
        exit 0
    fi
fi

NOW_EPOCH="$(date +%s)"
AGE_DAYS=$(( (NOW_EPOCH - DB_MTIME_EPOCH) / 86400 ))

# --- Verify git is available ---
if ! command -v git > /dev/null 2>&1; then
    echo "project-rag: SKIP — git not found (fail open)"
    exit 0
fi

# --- Find commit built against ---
# Convert mtime to ISO 8601 for git --before
if command -v date > /dev/null 2>&1; then
    # Try GNU date first, then BSD date
    MTIME_STR="$(date -u -d "@$DB_MTIME_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
        || date -u -r "$DB_MTIME_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
        || echo "")"
else
    MTIME_STR=""
fi

BUILT_COMMIT=""
if [ -n "$MTIME_STR" ]; then
    BUILT_COMMIT="$(git -C "$REPO_ROOT" log -1 "--before=$MTIME_STR" --format="%H" 2>/dev/null || true)"
    BUILT_COMMIT="${BUILT_COMMIT%%[[:space:]]*}"  # trim whitespace
fi

if [ -z "$BUILT_COMMIT" ]; then
    echo "project-rag: UNINITIALIZED — graph.db predates git history; run the project-RAG indexer"
    exit 0
fi

# --- Compute commit delta ---
DELTA=""
DELTA="$(git -C "$REPO_ROOT" rev-list "${BUILT_COMMIT}..HEAD" --count 2>/dev/null || true)"
DELTA="${DELTA%%[[:space:]]*}"

if [ -z "$DELTA" ]; then
    echo "project-rag: SKIP — git rev-list failed (fail open)"
    exit 0
fi

# --- Emit banner ---
if [ "$DELTA" -eq 0 ]; then
    echo "project-rag: fresh (HEAD aligned)"
else
    BASE_MSG="project-rag: STALE — $DELTA commits behind HEAD; project-RAG queries may miss recent changes"

    # Escalate to system-reminder block if N > 50 or age > 7 days
    if [ "$DELTA" -gt 50 ] || [ "$AGE_DAYS" -gt 7 ]; then
        echo "<system-reminder>"
        echo "$BASE_MSG"
        if [ "$DELTA" -gt 50 ]; then
            echo "  WARNING: $DELTA commits — index is significantly out of date. Run the project-RAG indexer to rebuild."
        fi
        if [ "$AGE_DAYS" -gt 7 ]; then
            echo "  WARNING: index is $AGE_DAYS days old. Run the project-RAG indexer to rebuild."
        fi
        echo "</system-reminder>"
    else
        echo "$BASE_MSG"
    fi
fi

exit 0
