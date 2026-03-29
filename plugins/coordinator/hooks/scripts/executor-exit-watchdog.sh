#!/bin/bash
# Executor Exit Watchdog — SubagentStop hook
# Detects thrashing executors at exit boundary and forces structured post-mortem.
#
# Three-tier detection:
#   Tier 1 (tag-based): Checks for <exit-status> tag in last assistant output
#   Tier 1.5 (AC-N check): On DONE, verifies AC-N acceptance criteria lines exist (soft warning if missing)
#   Tier 2 (heuristic): Counts Edit/Write calls per file — flags 12+ edits to same file
#                        SKIPPED for protocol-aware agents (any exit-status tag in transcript)
#
# Re-entry guard: Blocks once per transcript, then always approves (bark once, let go)

set -euo pipefail

# jq is required for transcript parsing and structured JSON output.
# Fail-open if unavailable (grep fallback not viable — downstream parsing requires jq).
if ! command -v jq &>/dev/null; then
  cat > /dev/null  # drain stdin to prevent SIGPIPE in caller
  exit 0
fi

# Read hook input from stdin (JSON with transcript_path, session_id)
# Safe stdin read — timeout prevents hang on Windows/Git Bash (see memory:
# feedback_no_userpromptsubmit_hooks.md for the full incident).
if command -v timeout &>/dev/null; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# --- Agent type gate ---
# This watchdog is ONLY for executor agents. Reviewers (Patrik, Sid, etc.), enrichers,
# and other subagent types should never be subjected to thrashing heuristics — their
# high-volume Read patterns are normal and the hook's output can replace the agent's
# actual findings in the return channel.
AGENT_TYPE=$(echo "$HOOK_INPUT" | jq -r '.agent_type // empty' 2>/dev/null || true)

if [[ "$AGENT_TYPE" != "coordinator:executor" ]]; then
  exit 0
fi

# --- Defensive input validation ---
# SubagentStop provides agent_transcript_path (the subagent's own transcript)
# and last_assistant_message (the final text block, no parsing needed for Tier 1).
# transcript_path is the PARENT's transcript — not what we want.
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.agent_transcript_path // .transcript_path // empty' 2>/dev/null || true)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
LAST_ASSISTANT_MSG=$(echo "$HOOK_INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null || true)

if [[ -z "$TRANSCRIPT_PATH" ]]; then
  echo "⚠️  Watchdog: transcript_path missing from hook input — approving (fail-open)" >&2
  exit 0
fi

if [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  echo "⚠️  Watchdog: transcript file not found: $TRANSCRIPT_PATH — approving (fail-open)" >&2
  exit 0
fi

# --- Re-entry guard ---
# Use md5sum/md5 of transcript path as sentinel key (not session_id — that's the parent)
if command -v md5sum &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5sum | cut -d' ' -f1)
elif command -v md5 &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5 -q)
else
  # Fallback: use a sanitized path as key
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | tr '/:. ' '____')
fi

SENTINEL_FILE="/tmp/watchdog-blocked-${TRANSCRIPT_HASH}"

if [[ -f "$SENTINEL_FILE" ]]; then
  # Already blocked this transcript once — approve and clean up
  rm -f "$SENTINEL_FILE"
  exit 0
fi

# --- Get last assistant output ---
# Prefer last_assistant_message from hook input (direct, no parsing needed).
# Fall back to transcript parsing if the field is empty.
if [[ -n "$LAST_ASSISTANT_MSG" ]]; then
  LAST_OUTPUT="$LAST_ASSISTANT_MSG"
else
  # Fallback: parse transcript for last assistant text block
  if ! grep -q '"role":"assistant"' "$TRANSCRIPT_PATH" 2>/dev/null; then
    exit 0
  fi
  LAST_LINES=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" | tail -n 100)
  if [[ -z "$LAST_LINES" ]]; then
    exit 0
  fi
  set +e
  LAST_OUTPUT=$(echo "$LAST_LINES" | jq -rs '
    map(.message.content[]? | select(.type == "text") | .text) | last // ""
  ' 2>&1)
  JQ_EXIT=$?
  set -e
  if [[ $JQ_EXIT -ne 0 ]] || [[ -z "$LAST_OUTPUT" ]]; then
    echo "⚠️  Watchdog: failed to parse transcript — approving (fail-open)" >&2
    exit 0
  fi
fi

# --- Tier 1: Tag-based detection ---
EXIT_TAG=$(echo "$LAST_OUTPUT" | sed -n 's/.*<exit-status>\([^<]*\)<.*/\1/p' | tail -1)

if [[ -n "$EXIT_TAG" ]]; then
  # Tag found — Tier 1 handles it, skip Tier 2 entirely
  case "$EXIT_TAG" in
    DONE)
      # Tier 1.5: Check for AC-N structured criteria in DONE reports
      if ! echo "$LAST_OUTPUT" | grep -qE '^AC-[0-9]+: (PASS|FAIL)'; then
        # No AC-N lines found — soft warning (approve with system message)
        jq -n '{
          "decision": "approve",
          "systemMessage": "⚠️ Watchdog Tier 1.5: Executor DONE report has no AC-N acceptance criteria lines. The stub may lack an Acceptance Criteria section, or the executor omitted the structured checklist. Coordinator should verify spec compliance."
        }'
        exit 0
      fi
      # AC-N lines present — clean approve
      exit 0
      ;;
    BLOCKED|ABORTED)
      # Clean exit — approve
      exit 0
      ;;
    THRASHING)
      # Self-detected thrashing — force post-mortem
      touch "$SENTINEL_FILE"
      jq -n '{
        "decision": "block",
        "reason": "The executor watchdog has detected your THRASHING exit status. Before you can exit, you MUST complete a post-mortem:\n\n1. Write an \"## Execution Post-Mortem\" section in the stub document with:\n   - Detection: self\n   - Stuck pattern: <repetition | oscillation | analysis-paralysis>\n   - Approaches tried: <numbered list>\n   - Last error/state: <specific failure>\n   - Stub diagnosis: <spec problem | environment problem | architectural gap>\n   - Files touched so far: <list with status>\n\n2. Update the stub status line to: **Status:** Execution aborted (YYYY-MM-DD HH:MM)\n\n3. If a tracker path was provided, update your entry to: \"Aborted — see stub post-mortem\"\n\n4. Exit with your report ending in: <exit-status>ABORTED</exit-status>",
        "systemMessage": "🚨 Watchdog: THRASHING detected — post-mortem required before exit"
      }'
      exit 0
      ;;
    *)
      # Unknown tag value — agent is protocol-aware but sent unexpected value. Approve.
      echo "⚠️  Watchdog: unknown exit-status tag '$EXIT_TAG' — approving" >&2
      exit 0
      ;;
  esac
fi

# --- Tier 2: Heuristic detection (no tag found in last text block) ---
# Before counting edits, check if any exit-status tag exists ANYWHERE in the transcript.
# Protocol-aware agents (executors) always emit a tag. If we find one anywhere, the agent
# is protocol-aware and Tier 1 should have handled it — skip the heuristic entirely.
# This prevents false positives when the tag isn't in the very last text block.

set +e
ANY_TAG=$(grep -o '<exit-status>[^<]*</exit-status>' "$TRANSCRIPT_PATH" 2>/dev/null | tail -1)
set -e

if [[ -n "$ANY_TAG" ]]; then
  # Protocol-aware agent — Tier 1 already handled or should have. Skip heuristic.
  exit 0
fi

# Count Edit/Write tool calls per file path in the subagent's transcript
# Only fires for non-protocol-aware agents (no exit-status tag anywhere in transcript)

set +e
# Parse assistant lines from transcript (needed for edit counting even if Tier 1 used last_assistant_message)
AGENT_LINES=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" 2>/dev/null | tail -n 100)
MAX_EDITS=$(echo "$AGENT_LINES" | jq -rs '
  [.[] | .message.content[]? | select(.type == "tool_use") |
   select(.name == "Edit" or .name == "Write") |
   .input.file_path // empty] |
  group_by(.) | map(length) | max // 0
' 2>/dev/null)
T2_EXIT=$?
set -e

if [[ $T2_EXIT -ne 0 ]] || [[ -z "$MAX_EDITS" ]]; then
  MAX_EDITS=0
fi

THRESHOLD=12

if [[ "$MAX_EDITS" -ge "$THRESHOLD" ]]; then
  # Likely thrashing — block with post-mortem prompt
  touch "$SENTINEL_FILE"
  jq -n \
    --arg edits "$MAX_EDITS" \
    --arg thresh "$THRESHOLD" '{
      "decision": "block",
      "reason": ("The executor watchdog has detected potential thrashing: a single file was edited " + $edits + " times (threshold: " + $thresh + "). Before you can exit, you MUST complete a post-mortem:\n\n1. Write an \"## Execution Post-Mortem\" section in the stub document with:\n   - Detection: watchdog\n   - Stuck pattern: <repetition | oscillation | analysis-paralysis>\n   - Approaches tried: <numbered list of distinct approaches>\n   - Last error/state: <specific failure that repeated>\n   - Stub diagnosis: <spec problem | environment problem | architectural gap>\n   - Files touched so far: <list with status>\n\n2. Update the stub status line to: **Status:** Execution aborted (YYYY-MM-DD HH:MM)\n\n3. If a tracker path was provided, update your entry to: \"Aborted — see stub post-mortem\"\n\n4. Exit with your report ending in: <exit-status>ABORTED</exit-status>"),
      "systemMessage": ("🚨 Watchdog: " + $edits + " edits to same file detected — post-mortem required before exit")
    }'
  exit 0
fi

# Below threshold or no Edit/Write calls — approve (could be reviewer, enricher, etc.)
exit 0
