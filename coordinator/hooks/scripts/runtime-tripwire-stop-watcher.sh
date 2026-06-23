#!/usr/bin/env bash
# Runtime Tripwire — asyncRewake Stop Watcher (L2 backstop)
#
# Purpose: Registered on the Stop hook event with asyncRewake: true.
#          Fires at end-of-turn, forks a background subprocess that sleeps
#          until the earliest tracked agent's model-specific threshold, then
#          re-checks whether the agent cleared. If not, exits 2 (asyncRewake
#          signal) to wake Claude with a stderr nudge naming the overrunning
#          dispatch. Closes the idle-EM blindspot that L1 (activity wiring)
#          cannot close: EM could go idle between PM messages for longer than
#          any threshold.
#
# Spec backlink: docs/plans/2026-06-15-runtime-tripwire-idle-em-layered-fix.md § C2a
# Wiki: docs/wiki/runtime-tripwire.md § L2
#
# Loop-guard invariant: if HOOK_INPUT.stop_hook_active == true, this Stop was
# triggered by the asyncRewake wakeup itself — do NOT re-arm a new watcher
# (infinite re-arming loop prevention per the Staff Engineer #6 / AC16).
#
# Lock invariant: PID lock at
#   $GIT_ROOT/.git/coordinator-sessions/$SESSION_ID/stop-watcher.pid
# Parent does NOT trap EXIT — lock must outlive the parent while the bg
# subprocess sleeps. Bg subprocess removes the lock in all its exit paths
# (both the cleared and the wake-fire paths). Stale locks swept by
# session-init.sh at session start (C2d). Trap discipline per the Staff Engineer #9.
#
# Portability: bash 3.2 / BSD coreutils (no declare -A, no mapfile,
#   no ${v^^}, no local -n, no sed -i, no date -d/%N, no grep -P).

set -uo pipefail
# NOTE: -e deliberately omitted. Advisory hook; must fail-open. Critical
# sections use explicit || true guards. A blanket -e aborts on stat/jq/find
# non-zero, defeating fail-open discipline.

# --- Safe stdin read (Windows Git-Bash hang guard) ---
if command -v timeout >/dev/null 2>&1; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat 2>/dev/null || true)
fi

# --- Step 1: stop_hook_active loop-guard (MUST be first check) ---
# If this Stop was triggered by an asyncRewake wakeup, exit 0 immediately.
# Do not re-arm — prevents infinite re-arming loop.
if command -v jq >/dev/null 2>&1; then
  STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)
else
  STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | sed -n 's/.*"stop_hook_active"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p' | head -1 || echo false)
fi
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
  exit 0
fi

# --- Step 2: GIT_ROOT discovery ---
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$GIT_ROOT" ]] && exit 0

# --- Step 3: SESSION_ID extraction ---
# Prefer HOOK_INPUT.session_id (distinct per firing session, unlike
# $CLAUDE_CODE_SESSION_ID which inherits EM id in subagents — see em-check.sh:22-26).
if command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)
fi
# Fall back to env var if HOOK_INPUT.session_id absent (matches em-check.sh fallback pattern).
if [[ -z "$SESSION_ID" ]]; then
  SESSION_ID="${CLAUDE_CODE_SESSION_ID:-}"
fi
[[ -z "$SESSION_ID" ]] && exit 0

# --- Step 4: Per-session PID lock ---
SESSIONS_DIR="$GIT_ROOT/.git/coordinator-sessions"
LOCK_DIR="$SESSIONS_DIR/$SESSION_ID"
LOCK="$LOCK_DIR/stop-watcher.pid"

mkdir -p "$LOCK_DIR" 2>/dev/null || true

if [[ -f "$LOCK" ]]; then
  EXISTING_PID=$(cat "$LOCK" 2>/dev/null || echo 0)
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    exit 0  # live watcher already running; do not stack
  fi
  # stale lock — overwrite below
fi
# Lock PID is written AFTER the bg subprocess forks, with $! (bg child PID), not
# $$ (parent — which exits 0 immediately and goes dead, defeating the kill -0
# dedup gate above). Slice 2 F4 fix.

# --- Step 5: Source shared thresholds lib ---
LIB_DIR="$(dirname "${BASH_SOURCE[0]}")/lib"
# shellcheck source=lib/runtime-thresholds.sh
source "$LIB_DIR/runtime-thresholds.sh" 2>/dev/null || { rm -f "$LOCK"; exit 0; }

# --- Step 6: Read earliest still-tracked agent from dispatched-agents.txt ---
# Same path em-check.sh reads (line 113).
DISPATCH_FILE="$SESSIONS_DIR/$SESSION_ID/dispatched-agents.txt"
COMPLETION_LOG="$SESSIONS_DIR/logs/agent-audit.jsonl"

if [[ ! -f "$DISPATCH_FILE" ]]; then
  rm -f "$LOCK"
  exit 0
fi

# Find earliest-dispatched still-tracked agent (lowest dispatched_at epoch among
# agents not yet in the completion log). Completion check mirrors em-check.sh:168.
EARLIEST_AGENT_ID=""
EARLIEST_MODEL=""
EARLIEST_DISPATCHED_AT=0

while IFS=$'\t' read -r agentId model _subagent_type dispatched_at; do
  [[ -z "$agentId" ]] && continue
  # Backward-compat: skip legacy records with no epoch timestamp.
  [[ ! "$dispatched_at" =~ ^[0-9]+$ ]] && continue
  [[ "$dispatched_at" -eq 0 ]] && continue
  # Skip completed agents.
  if [[ -f "$COMPLETION_LOG" ]] && grep -q "\"agentId\":[[:space:]]*\"${agentId}\"" "$COMPLETION_LOG" 2>/dev/null; then
    continue
  fi
  # Track earliest (smallest dispatched_at).
  if [[ "$EARLIEST_DISPATCHED_AT" -eq 0 || "$dispatched_at" -lt "$EARLIEST_DISPATCHED_AT" ]]; then
    EARLIEST_AGENT_ID="$agentId"
    EARLIEST_MODEL="$model"
    EARLIEST_DISPATCHED_AT="$dispatched_at"
  fi
done < "$DISPATCH_FILE"

if [[ -z "$EARLIEST_AGENT_ID" ]]; then
  # No tracked agents — no watcher needed.
  rm -f "$LOCK"
  exit 0
fi

# --- Step 7: Compute SLEEP_SEC ---
THRESHOLD_MIN=$(runtime_threshold_minutes "$EARLIEST_MODEL")
THRESHOLD_SEC=$(( THRESHOLD_MIN * 60 ))
NOW=$(date +%s)
TARGET_EPOCH=$(( EARLIEST_DISPATCHED_AT + THRESHOLD_SEC ))
SLEEP_SEC=$(( TARGET_EPOCH - NOW ))
if [[ "$SLEEP_SEC" -lt 0 ]]; then
  SLEEP_SEC=0
fi

# --- Step 8: Background subprocess — wait, recheck, nudge or clear ---
# Lock cleanup is the bg subprocess's sole responsibility in ALL exit paths.
(
  if [[ "$SLEEP_SEC" -gt 0 ]]; then
    sleep "$SLEEP_SEC"
  fi

  # Re-read state: is the agent still tracked and still not in the completion log?
  STILL_TRACKED=false
  if [[ -f "$DISPATCH_FILE" ]]; then
    while IFS=$'\t' read -r agentId model _subagent_type dispatched_at; do
      [[ "$agentId" == "$EARLIEST_AGENT_ID" ]] || continue
      # Found the record — check completion log.
      if [[ -f "$COMPLETION_LOG" ]] && grep -q "\"agentId\":[[:space:]]*\"${EARLIEST_AGENT_ID}\"" "$COMPLETION_LOG" 2>/dev/null; then
        break  # completed — STILL_TRACKED stays false
      fi
      STILL_TRACKED=true
      break
    done < "$DISPATCH_FILE"
  fi

  if [[ "$STILL_TRACKED" == "false" ]]; then
    # Agent cleared mid-sleep — exit silently.
    rm -f "$LOCK"
    exit 0
  fi

  # Agent still running past threshold — emit stderr nudge and wake EM.
  WAKE_NOW=$(date +%s)
  ELAPSED_MIN=$(( (WAKE_NOW - EARLIEST_DISPATCHED_AT) / 60 ))
  printf 'RUNTIME TRIPWIRE (L2 asyncRewake watcher) — agent past threshold:\n' >&2
  printf '  %s | %s | %d min elapsed\n' "$EARLIEST_AGENT_ID" "$EARLIEST_MODEL" "$ELAPSED_MIN" >&2
  printf 'Agent owns the wrap judgment; you (EM) hold authority. Assess: let it finish, TaskStop, or plan a successor.\n' >&2
  printf 'Reference: docs/wiki/runtime-tripwire.md\n' >&2

  rm -f "$LOCK"
  exit 2  # asyncRewake signal — wakes Claude with the stderr content above
) &
WATCHER_PID=$!
# Write CHILD PID (Slice 2 F4 fix) — parent dies on `exit 0` below; kill -0 dedup
# requires a live PID to gate correctly. $! is the live bg subprocess.
echo "$WATCHER_PID" > "$LOCK" 2>/dev/null || true

# --- Parent exits 0 immediately ---
# asyncRewake infrastructure monitors the background subprocess; fires Claude
# system reminder if/when the subprocess exits 2.
exit 0
