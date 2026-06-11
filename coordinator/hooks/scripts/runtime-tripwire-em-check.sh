#!/bin/bash
# Runtime Tripwire — EM-Side Awareness (PostToolUse hook)
#
# Purpose: Fires in the EM session. Self-throttled 5 min. Reads the EM's
#          dispatched-agents.txt, identifies any running subagent past its
#          model-specific runtime threshold, and emits an awareness
#          additionalContext naming each overrun dispatch.
#
# Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C3b
# Wiki: docs/wiki/runtime-tripwire.md (written in C5; path is stable)
#
# This is the EM-side complement to runtime-tripwire-advisory.sh (which fires
# inside the subagent). Together they give both parties awareness; the agent
# owns the wrap judgment, the EM holds authority (trust-but-verify).
#
# Discriminator: if HOOK_INPUT.session_id IS found under any
#   .git/coordinator-sessions/.agents/*/em-session-id.txt → this is a subagent
#   session; exit 0 and let the agent-side hook handle it. If NOT found → this
#   is the EM session; proceed.
#
# IMPORTANT — env-var discriminator is NOT used here:
#   $CLAUDE_CODE_SESSION_ID inherits the dispatching EM's id inside subagents
#   (confirmed: claude-code-platform-gotchas.md:33-50, probe 2026-05-23).
#   Only HOOK_INPUT.session_id is the firing session's distinct id and is
#   reliable as the subagent-vs-EM discriminator.
#
# C0 Classification (2026-06-08, EM-inline):
#   - HOOK_INPUT.session_id IS distinct between EM and subagent (platform
#     isolation confirmed by docs/wiki/claude-code-platform-gotchas.md:154-158).
#   - $CLAUDE_CODE_SESSION_ID inherits EM id in subagents — DO NOT use.
#
# Portability: bash 3.2 / BSD coreutils (no declare -A, no sed -i, no grep -P,
#   no date -d/%N, no realpath/readlink -f).

set -uo pipefail
# NOTE: -e deliberately omitted. Advisory hook; must fail-open. Critical
# sections use explicit || true guards. A blanket -e aborts on stat/jq/find
# non-zero, defeating fail-open discipline.

# --- Safe stdin read (Windows Git-Bash hang guard) ---
# GNU timeout is available in Git Bash via coreutils. Fall back to plain cat
# if somehow absent — PostToolUse is safer than UserPromptSubmit anyway.
if command -v timeout >/dev/null 2>&1; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat 2>/dev/null || true)
fi

# --- Extract session_id from HOOK_INPUT (prefer jq, fall back to sed) ---
if command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  TOOL_RESPONSE_AGENT_ID=$(echo "$HOOK_INPUT" | jq -r '.tool_response.agentId // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  # Anchored extraction: only look inside the tool_response block.
  _tr_tail="${HOOK_INPUT#*\"tool_response\":}"
  TOOL_RESPONSE_AGENT_ID=$(echo "$_tr_tail" | sed -n 's/.*"agentId"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fail-open: no session id means we cannot do anything useful.
[[ -z "$SESSION_ID" ]] && exit 0

# --- Git root + coordinator-sessions paths ---
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_DIR="$GIT_ROOT/.git/coordinator-sessions"
AGENTS_DIR="$SESSIONS_DIR/.agents"

# --- Subagent-detect inverse ---
# If HOOK_INPUT.session_id appears as a subagent agent-dir name (i.e., a
# .agents/<SESSION_ID>/em-session-id.txt file exists), this hook is firing
# inside a subagent's session. Exit — the agent-side hook handles that path.
# The EM's session id never appears as an .agents/<id> directory (the .agents/
# dirs are keyed on agentId, not em-session-id), so only a genuine subagent
# matches this check.
if [[ -f "$AGENTS_DIR/$SESSION_ID/em-session-id.txt" ]]; then
  exit 0
fi

# --- Self-throttle: 5 minutes (mirrors context-pressure-advisory.sh:100-115) ---
THROTTLE_SENTINEL="/tmp/runtime-tripwire-em-throttle-${SESSION_ID}"
THROTTLE_SECONDS=300

if [[ -f "$THROTTLE_SENTINEL" ]]; then
  if [[ "$OSTYPE" == darwin* ]]; then
    SENTINEL_MTIME=$(stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || echo 0)
  else
    SENTINEL_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || echo 0)
  fi
  NOW=$(date +%s)
  ELAPSED=$(( NOW - SENTINEL_MTIME ))
  if [[ "$ELAPSED" -lt "$THROTTLE_SECONDS" ]]; then
    exit 0
  fi
fi
# Throttle sentinel is written AFTER the dispatch loop, only if at least one
# nudge fired this pass (see end of file). Below-threshold passes do NOT
# consume the throttle, so the first threshold-crossing fires immediately
# instead of being delayed up to 5 min. This matters for Haiku (threshold 10
# vs HARD-RULE ceiling 15 = 5-min wrap buffer) and Sonnet (12 vs 15 = 3-min
# buffer) — the buffer is what gives the wrap-shape time to land before
# doctrine. Earlier versions of this hook wrote the sentinel unconditionally
# here; that consumed the buffer on every below-threshold scan.
# Recovered 2026-06-09 after Sonnet review F5 on commit fc1196e8.

# --- Source shared thresholds lib ---
LIB_DIR="$(dirname "${BASH_SOURCE[0]}")/lib"
# shellcheck source=lib/runtime-thresholds.sh
source "$LIB_DIR/runtime-thresholds.sh" 2>/dev/null || exit 0

# --- Locate dispatched-agents.txt for this EM session ---
DISPATCH_FILE="$SESSIONS_DIR/$SESSION_ID/dispatched-agents.txt"
[[ ! -f "$DISPATCH_FILE" ]] && exit 0

# --- Completion-log surface for skip-if-completed cross-reference ---
COMPLETION_LOG="$SESSIONS_DIR/logs/agent-audit.jsonl"

NOW=$(date +%s)
FIRST_FIRE_LIST=""
RESTAGE_LIST=""
RESTAGE_SECONDS="${RUNTIME_TRIPWIRE_RESTAGE_SECONDS:-300}"  # +5 min after first fire — single re-nudge, then silence (PM disposition 2026-06-08). Env-var override exists for testing.

# Max-age cap: dispatched-agents.txt is append-only with agentId-dedup but never
# ages out, so a dispatch whose completion record predates a skip-cross-ref
# schema fix (or whose audit-log entry was lost) lingers forever. Past
# MAX_TRACK_MINUTES, the dispatch has either completed (the common case) or
# hung long enough that the EM has already decided — either way, further
# nudges are noise.
#
# Why 90 min: the LAST scheduled nudge for any model fires at threshold +
# restage. The longest-lived case is Opus (25 + 5 = 30 min). 90 min thus sits
# 60 min past Opus's last fire, well clear of any legitimate tracking window.
# Sonnet (12 + 5 = 17) and Haiku (10 + 5 = 15) are even more conservative.
# Env-var override exists for testing.
#
# Empirical trigger 2026-06-09: pre-fix C1-C7 executors stayed visible in the
# tracker for hours after landing commits, because their completion-log
# entries predated the agentId-field fix (commit c268fb0f).
MAX_TRACK_MINUTES="${RUNTIME_TRIPWIRE_MAX_TRACK_MIN:-90}"

while IFS=$'\t' read -r agentId model subagent_type dispatched_at; do
  # Skip blank lines or lines with no agentId.
  [[ -z "$agentId" ]] && continue

  # Skip-if-returning (F9): if the triggering PostToolUse event carries
  # tool_response.agentId for the agent that just returned, skip it — it has
  # already wrapped by definition.
  if [[ -n "$TOOL_RESPONSE_AGENT_ID" && "$TOOL_RESPONSE_AGENT_ID" == "$agentId" ]]; then
    continue
  fi

  # Skip-if-completed: cross-reference against agent-audit.jsonl (best-effort).
  # Presence of a completion log entry keyed by agentId means the agent already
  # returned. agent-completion-log.sh writes agentId from .tool_response.agentId
  # at PostToolUse time — i.e. when the Agent tool returns, which IS completion.
  # (Earlier versions grepped for "name", which is .tool_input.name — the
  # optional addressable-teammate name, almost never set — so this skip never
  # matched and the hook re-fired on completed agents indefinitely. Fixed
  # 2026-06-09 after empirical false-positive on em-side-restage records.)
  #
  # Pattern requires BOTH quotes around the value: opener after the colon AND
  # closer after the agentId. Without the trailing quote, a shorter agentId
  # that is a prefix of a longer one would false-match. Pattern deliberately
  # does NOT match "agentId":null — agent-completion-log.sh emits null when
  # tool_response.agentId is absent (legacy/malformed responses); those are
  # NOT confirmed completions and should not trigger the skip.
  if [[ -f "$COMPLETION_LOG" ]] && grep -q "\"agentId\":[[:space:]]*\"${agentId}\"" "$COMPLETION_LOG" 2>/dev/null; then
    continue
  fi

  # Backward-compat: missing or non-numeric dispatched_at → legacy record.
  # Treat as unknown start time (0) and skip — do NOT fire on unknowns.
  [[ ! "$dispatched_at" =~ ^[0-9]+$ ]] && continue
  [[ "$dispatched_at" -eq 0 ]] && continue

  # Per-model threshold check.
  ELAPSED_MIN=$(( (NOW - dispatched_at) / 60 ))

  # Max-age cap (skip-if-too-old): safety backstop against append-only
  # dispatched-agents.txt + skip-if-completed false-negatives (lost or
  # schema-mismatched audit-log entries). See MAX_TRACK_MINUTES rationale
  # above. Skip silently — no fire-log entry, no nudge.
  [[ "$ELAPSED_MIN" -ge "$MAX_TRACK_MINUTES" ]] && continue

  THRESHOLD_MIN=$(runtime_threshold_minutes "$model")
  [[ "$ELAPSED_MIN" -lt "$THRESHOLD_MIN" ]] && continue

  # Bark-once + single re-nudge at +5 min (PM disposition 2026-06-08).
  # AGENT_SENTINEL marks the first fire; RESTAGE_SENTINEL marks the +5-min
  # re-nudge. Once RESTAGE_SENTINEL exists, the hook is silent for this
  # agentId — the third decision is intervene-or-accept.
  AGENT_SENTINEL="/tmp/runtime-tripwire-em-${agentId}"
  RESTAGE_SENTINEL="/tmp/runtime-tripwire-em-restage-${agentId}"

  # Fire-log setup — log written inside each branch to avoid FIRE_TYPE dependency
  # across the if/else gap. Review: code-reviewer — O_APPEND on single-row
  # payloads <PIPE_BUF (4KB) is atomic on POSIX: concurrent EM-session appends
  # interleave at row boundaries only (each printf row is well under PIPE_BUF).
  # Interleaved rows are acceptable for calibration accuracy — no locking needed.
  FIRE_LOG="$GIT_ROOT/state/runtime-tripwire-fire-log.tsv"
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true

  if [[ -f "$AGENT_SENTINEL" ]]; then
    # First fire already happened — check if it's time for the single re-nudge.
    [[ -f "$RESTAGE_SENTINEL" ]] && continue  # already re-nudged → silence
    if [[ "$OSTYPE" == darwin* ]]; then
      FIRST_FIRE_MTIME=$(stat -f %m "$AGENT_SENTINEL" 2>/dev/null || echo 0)
    else
      FIRST_FIRE_MTIME=$(stat -c %Y "$AGENT_SENTINEL" 2>/dev/null || echo 0)
    fi
    SINCE_FIRST=$(( NOW - FIRST_FIRE_MTIME ))
    [[ "$SINCE_FIRST" -lt "$RESTAGE_SECONDS" ]] && continue
    touch "$RESTAGE_SENTINEL"
    RESTAGE_LIST="${RESTAGE_LIST}  ${agentId} | ${model} | ${ELAPSED_MIN} min"$'\n'
    # Fire-log append (R3 / F10): one record per fire for calibration evidence.
    # Schema: timestamp TAB agentId TAB model TAB elapsed_min TAB fire_type
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$agentId" \
      "$model" \
      "$ELAPSED_MIN" \
      "em-side-restage" >> "$FIRE_LOG" 2>/dev/null || true
  else
    touch "$AGENT_SENTINEL"
    FIRST_FIRE_LIST="${FIRST_FIRE_LIST}  ${agentId} | ${model} | ${ELAPSED_MIN} min"$'\n'
    # Fire-log append (R3 / F10): one record per fire for calibration evidence.
    # Schema: timestamp TAB agentId TAB model TAB elapsed_min TAB fire_type
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$agentId" \
      "$model" \
      "$ELAPSED_MIN" \
      "em-side" >> "$FIRE_LOG" 2>/dev/null || true
  fi

done < "$DISPATCH_FILE"

# Throttle sentinel — write only if at least one nudge fired this pass.
# A below-threshold pass leaves the sentinel untouched so the next pass
# (when threshold is crossed) fires immediately. See the comment above the
# 5-min throttle gate at the top of the file for the wrap-buffer rationale.
if [[ -n "$FIRST_FIRE_LIST" || -n "$RESTAGE_LIST" ]]; then
  touch "$THROTTLE_SENTINEL"
fi

# Nothing to report — exit cleanly without emitting JSON.
[[ -z "$FIRST_FIRE_LIST" && -z "$RESTAGE_LIST" ]] && exit 0

# --- Emit awareness additionalContext ---
# Two possible sections, both can be present in the same fire if a fresh
# overrun lands in the same throttle window as a +5-min re-nudge for a
# different dispatch.
NUDGE=""

if [[ -n "$FIRST_FIRE_LIST" ]]; then
  NUDGE="RUNTIME TRIPWIRE — one or more dispatched agents are past their runtime threshold:

${FIRST_FIRE_LIST}
Each has received its own wrap-shape nudge (agent-side hook). Agent owns the wrap judgment; you (EM) hold authority (trust-but-verify). If an agent reports continued progress and you concur on visible disk artifacts, let it finish. Otherwise plan a successor dispatch or TaskStop."
fi

if [[ -n "$RESTAGE_LIST" ]]; then
  [[ -n "$NUDGE" ]] && NUDGE="${NUDGE}

"
  NUDGE="${NUDGE}RUNTIME TRIPWIRE — RE-NUDGE (your earlier wait judgment is now 5+ minutes stale):

${RESTAGE_LIST}
The 'few more minutes' window has expired. Reassess explicitly: TaskStop, plan successor, or accept the runaway. After this fire, the hook is silent for these dispatches — the next decision is yours."
fi

NUDGE="${NUDGE}

Reference: docs/wiki/runtime-tripwire.md"

jq -n --arg ctx "$NUDGE" \
  '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
exit 0
