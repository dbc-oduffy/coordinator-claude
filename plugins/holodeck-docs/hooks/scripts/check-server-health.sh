#!/usr/bin/env bash
# PreToolUse health gate for holodeck-docs tools.
# Fast path: server healthy -> exit silently (no output, no delay).
# Recovery path: server down -> start it, wait for ready, then proceed.
# If recovery fails within 90s, deny the tool call with a clear error.

PORT="${MCP_PORT:-8765}"
HOST="${MCP_HOST:-127.0.0.1}"

# Fast health check (1s timeout) — this is the hot path.
# When the server is healthy, this adds ~10ms of overhead.
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 \
  "http://$HOST:$PORT/health" 2>/dev/null)

if [ "$HTTP_STATUS" = "200" ]; then
    exit 0  # Healthy — proceed with tool call, no output
fi

# --- Recovery path: server is down ---
echo "holodeck-docs: server not responding (HTTP $HTTP_STATUS), attempting recovery..." >&2

REPO_ROOT="X:/claude-unreal-holodeck"
ENSURE_SCRIPT="$REPO_ROOT/scripts/ensure-holodeck-docs-server.sh"

if [ ! -f "$ENSURE_SCRIPT" ]; then
    cat <<'HOOKJSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"holodeck-docs server is not running and ensure script not found. Run: bash X:/claude-unreal-holodeck/scripts/ensure-holodeck-docs-server.sh"}}
HOOKJSON
    exit 0
fi

# Start the ensure script in the background (it handles locking and dedup)
bash "$ENSURE_SCRIPT" &
ENSURE_PID=$!

# Wait up to 90s for the server to come up
elapsed=0
while [ "$elapsed" -lt 90 ]; do
    sleep 3
    elapsed=$((elapsed + 3))
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 \
      "http://$HOST:$PORT/health" 2>/dev/null)
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "holodeck-docs: server recovered after ${elapsed}s" >&2
        exit 0  # Server is back — let the tool call proceed
    fi
done

# Recovery failed — deny the tool call
cat <<'HOOKJSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"holodeck-docs server is not running and failed to start within 90s. Check logs/holodeck-docs-server.err for errors."}}
HOOKJSON
exit 0
