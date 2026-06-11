#!/bin/bash
# Runtime Tripwire — Agent-Side Advisory (PostToolUse hook)
#
# Purpose: Fires inside a SUBAGENT session. Emits an additionalContext nudge
#          when the subagent has been running past its model-specific runtime
#          threshold, instructing it to wrap cleanly.
#
# Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C2
# Wiki: docs/wiki/runtime-tripwire.md (authoritative; written in C5)
#
# WRAP-SHAPE DOCTRINE — AUTHORITATIVE COPY
# =========================================
# This script is the authoritative copy of the wrap-shape prescription per
# docs/wiki/runtime-tripwire.md §3. The wiki quotes this text for human readers.
# DO NOT REWORD the canonical strings without also updating the wiki.
# AC5 grep targets: "stop starting new work", "persist any partial state to disk",
# "write a successor-handoff stub", "return"
#
# DISCRIMINATOR NOTE (C0 confirmed)
# ==================================
# Discriminator: HOOK_INPUT.session_id from stdin. The firing session_id is
# DISTINCT in a subagent vs the EM (per claude-code-platform-gotchas.md:154).
# CLAUDE_CODE_SESSION_ID env var inherits the EM's id inside subagents
# (gotchas:33-50) — do NOT use it as the discriminator here.
# Subagent check: does SESSION_ID appear as a dirname under .agents/?
# Subagents' session_ids are recorded as dirs under .agents/; EM's is not.

# NOTE: -e deliberately omitted. This is an advisory hook and must fail-open;
# critical sections use explicit || true guards. A blanket -e would abort on
# any subcommand non-zero (stat/jq/find), defeating the fail-open contract.
set -uo pipefail

# --- Safe stdin read (timeout-guarded; matches context-pressure-advisory.sh:25-29) ---
if command -v timeout >/dev/null 2>&1; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# --- Extract session_id (jq preferred, sed fallback per :32-38) ---
# transcript_path not needed here — timing uses dispatched-agents.txt, not transcript mtime
if command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fail-open: can't discriminate without a session_id
[[ -z "$SESSION_ID" ]] && exit 0

# --- Subagent-detect: is THIS firing session_id a subagent's? ---
# Each subagent session_id is recorded as a subdirectory under .agents/.
# If SESSION_ID exists there, we're inside a subagent — proceed.
# If not found, this is the EM session — exit 0 (EM-side hook handles that half).
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
[[ -z "$GIT_ROOT" ]] && exit 0

AGENTS_DIR="$GIT_ROOT/.git/coordinator-sessions/.agents"
[[ ! -d "$AGENTS_DIR" ]] && exit 0

OWN_AGENT_ID=""
if [[ -d "$AGENTS_DIR/$SESSION_ID" ]]; then
  OWN_AGENT_ID="$SESSION_ID"
fi

# Not a subagent — let the EM-side hook handle it.
# Review: code-reviewer — stale-dir degrade note: stale .agents/<id>/ dirs from
# crashed prior sessions that reused a session_id would match the directory
# check above and reach the EM_SID_FILE check. If the back-pointer file is
# absent (no em-session-id.txt), the hook exits 0 at line ~76 below — this is
# fail-open (silent), not a false alarm. Real subagents always have the
# back-pointer written; the absence is the degrade signal.
[[ -z "$OWN_AGENT_ID" ]] && exit 0

# --- Source the shared thresholds lib ---
LIB_DIR="$(dirname "${BASH_SOURCE[0]}")/lib"
# shellcheck source=lib/runtime-thresholds.sh
source "$LIB_DIR/runtime-thresholds.sh" 2>/dev/null || exit 0

# --- Find EM session id from back-pointer ---
EM_SID_FILE="$AGENTS_DIR/$OWN_AGENT_ID/em-session-id.txt"
[[ ! -f "$EM_SID_FILE" ]] && exit 0
EM_SID=$(head -1 "$EM_SID_FILE" 2>/dev/null | tr -d '[:space:]' || true)
[[ -z "$EM_SID" ]] && exit 0

# --- Read own dispatched-at + model from EM's dispatched-agents.txt ---
# Record shape (as of 2026-06-08): agentId\tmodel\tsubagent_type\tdispatched-at
DISPATCH_FILE="$GIT_ROOT/.git/coordinator-sessions/$EM_SID/dispatched-agents.txt"
[[ ! -f "$DISPATCH_FILE" ]] && exit 0

# Match on field 1 exactly via awk — guards against a longer agentId that has
# OWN_AGENT_ID as a substring. Random hex makes collisions astronomically
# unlikely but `awk $1 == id` makes the invariant explicit and survives any
# future ID-format change.
OWN_ROW=$(awk -F'\t' -v id="$OWN_AGENT_ID" '$1 == id { print; exit }' "$DISPATCH_FILE" 2>/dev/null || true)
[[ -z "$OWN_ROW" ]] && exit 0

MODEL=$(echo "$OWN_ROW" | cut -f2)
DISPATCHED_AT=$(echo "$OWN_ROW" | cut -f4)

# Backward-compat: legacy 3-col records have no col 4 — skip timing check
[[ ! "$DISPATCHED_AT" =~ ^[0-9]+$ ]] && exit 0
[[ "$DISPATCHED_AT" -eq 0 ]] && exit 0

# --- Compute elapsed minutes ---
NOW=$(date +%s)
ELAPSED_SEC=$(( NOW - DISPATCHED_AT ))
ELAPSED_MIN=$(( ELAPSED_SEC / 60 ))

# --- Threshold check ---
THRESHOLD_MIN=$(runtime_threshold_minutes "$MODEL")
[[ "$ELAPSED_MIN" -lt "$THRESHOLD_MIN" ]] && exit 0

# --- Bark-once sentinel (keyed on firing session_id, matching context-pressure pattern) ---
# One nudge per dispatch — do not re-fire on every tool call after threshold
SENTINEL="/tmp/runtime-tripwire-agent-${SESSION_ID}"
[[ -f "$SENTINEL" ]] && exit 0
touch "$SENTINEL"

# --- Autonomous-run detection (soften language slightly per compaction-advisory pattern) ---
AUTONOMOUS=false
if [[ -f "/tmp/autonomous-run-${EM_SID}" ]]; then
  AUTONOMOUS=true
fi

# --- Append to fire-log (R3 calibration evidence surface per the Staff Engineer F10) ---
# Format: timestamp\tagentId\tmodel\telapsed_min\tfire_type
# Surveyed at /workweek-complete Step 4 queue triage for calibration.
# Review: code-reviewer — O_APPEND on single-row payloads <PIPE_BUF (4KB) is
# atomic on POSIX: concurrent EM-session appends interleave at row boundaries
# only (each printf row is well under PIPE_BUF). Interleaved rows are acceptable
# for calibration accuracy — no locking needed.
FIRE_LOG="$GIT_ROOT/state/runtime-tripwire-fire-log.tsv"
mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
printf '%s\t%s\t%s\t%s\t%s\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  "$OWN_AGENT_ID" \
  "$MODEL" \
  "$ELAPSED_MIN" \
  "agent-side" >> "$FIRE_LOG" 2>/dev/null || true

# --- Emit additionalContext with WRAP-SHAPE prescription ---
# CANONICAL TEXT — DO NOT REWORD without updating docs/wiki/runtime-tripwire.md §3
# AC5 grep targets are embedded verbatim in the WRAP_TEXT strings below.
if [[ "$AUTONOMOUS" == true ]]; then
  WRAP_TEXT="RUNTIME TRIPWIRE — you've been running ~${ELAPSED_MIN} minutes (past the ~${THRESHOLD_MIN} min runtime tripwire for ${MODEL}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. Autonomous run active. Trust-but-verify with the EM as authority: form your own judgment, but assume the EM will evaluate it. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
else
  WRAP_TEXT="RUNTIME TRIPWIRE — you've been running ~${ELAPSED_MIN} minutes (past the ~${THRESHOLD_MIN} min runtime tripwire for ${MODEL}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. Trust-but-verify with the EM as authority: form your own judgment, but assume the EM will evaluate it. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
fi

jq -n --arg ctx "$WRAP_TEXT" \
  '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
exit 0
