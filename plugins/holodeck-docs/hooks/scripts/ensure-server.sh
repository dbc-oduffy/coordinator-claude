#!/usr/bin/env bash
# SessionStart hook — ensures the holodeck-docs HTTP server is running.
# Delegates to the repo's ensure script which handles health checks,
# lock-based deduplication, and polling.

REPO_ROOT="X:/claude-unreal-holodeck"
ENSURE_SCRIPT="$REPO_ROOT/scripts/ensure-holodeck-docs-server.sh"

if [ -f "$ENSURE_SCRIPT" ]; then
    exec bash "$ENSURE_SCRIPT"
else
    echo "holodeck-docs: ensure script not found at $ENSURE_SCRIPT" >&2
    exit 1
fi
