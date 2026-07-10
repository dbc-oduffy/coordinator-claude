#!/usr/bin/env bash
# PostToolUse hook (matcher: Agent): records agentIds dispatched by the EM,
# enabling later coordinator-safe-commit invocations to union the executors'
# touched-file lists into scope.
#
# Per archive/specs/2026-05-05-issue-a-agent-id-linkage.md (Issue A, the Staff Engineer
# APPROVED_WITH_NOTES v3 2026-05-06).
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 1 — extends record shape with model and subagent_type columns.
#
# Mechanism:
#   - Agent-id extraction: three-pass cascade anchored to tool_response.
#     (a)  Primary: camelCase "agentId" (unnamed/background agents, Probe 0.3).
#     (a)  Fallback: snake_case "agent_id" (named Agent-Teams teammates,
#          harness 2.1.185; value arrives as "<name>@session-<short-sid>").
#     (a2) Last-resort: text regex over tool_response substring; bounded char
#          class [A-Za-z0-9_.@-] stops at JSON backslash-escape boundary.
#   - model: tool_response.resolvedModel → tool_response.model →
#     tool_input.model → "unknown". The harness places the actual resolved
#     model in tool_response; tool_input.model is set only for explicit
#     caller overrides (absent for most teammate / background dispatches).
#   - subagent_type extracted from tool_input (unchanged location).
#     Graceful-degrade to "unknown" if absent (conservative default).
#   Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C1
#   - Write two files:
#       <git_root>/.git/coordinator-sessions/<em_sid>/dispatched-agents.txt
#       <git_root>/.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt
#     The em-session-id.txt back-pointer is the durable linkage that makes
#     the read path sentinel-independent (helper enumerates .agents/* and
#     matches against the candidate em-sid set built from cs_live_session_ids).
#   - Record shape (tab-delimited, newline-terminated):
#       <agentId>\t<model>\t<subagent_type>\t<dispatched-at>
#     where <dispatched-at> is Unix epoch seconds at write time ($(date +%s)).
#     Legacy 3-column records (no 4th column) still parse: readers treat
#     missing dispatched-at column as 0 (sentinel meaning "unknown start time").
#     Legacy 1-column records (bare agentId, no tabs) still parse: Chunk 2's
#     read helper treats missing model column as "unknown" (Sonnet for LoE
#     purposes — conservative default per plan line 79).
#
#     Spec backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md
#     § C3a — extends record shape with dispatched-at column for runtime-tripwire hooks.
#   - Dedup / collision guard compares column 1 (cut -f1 | grep -qxF).
#     Same subagent_type → silent idempotent dedup. Different subagent_type
#     for the same canonical id → detect-then-fail-loud: writes AMBIGUOUS
#     sentinel into the EXISTING row's subagent_type column so C9's lookup
#     returns AMBIGUOUS → fail-closed for both colliding dispatches (AC14).
#     (the Staff Engineer F1/F11: old grep -qxF on full line always mismatched tab-
#     delimited records, causing unbounded re-append.)
#   - Atomic temp+rename for the back-pointer (the Staff Engineer v2 finding 3).
#   - Always exits 0 — advisory bookkeeping, never blocks tool calls.
#
# Architectural note — PostToolUse fires at Agent RETURN time, not dispatch time:
#   This hook fires on PostToolUse: Agent, meaning it runs when the Agent tool
#   returns to the EM — which is RETURN time, not the moment the dispatch was
#   issued. The `dispatched-at` timestamp recorded is therefore the Agent-tool
#   return time.
#
#   For BACKGROUND dispatches (run_in_background: true): the Agent tool returns
#   immediately at dispatch time (background agents are fire-and-forget from the
#   tool's perspective). In this case `dispatched-at` is the actual dispatch
#   time, and the runtime-tripwire elapsed-time math is correct.
#
#   For FOREGROUND dispatches (blocking): the Agent tool returns only after the
#   subagent completes, so `dispatched-at` records the agent-completion time —
#   not the dispatch time. However, for a foreground dispatch the EM is blocked
#   on the call and cannot act on a runtime nudge anyway, making the timing
#   inaccuracy irrelevant in practice.
#
#   Conclusion: the system is correctly designed for the background-dispatch use
#   case, which is the primary use case for the runtime-tripwire. Foreground
#   dispatches degrade gracefully (no false alarm; EM couldn't act anyway).

if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi
[[ -z "$INPUT" ]] && exit 0

# Filter to Agent tool calls only.
[[ "$INPUT" != *'"tool_name":"Agent"'* ]] && exit 0

# Extract session_id (firing session — the EM). Top-level field; floating
# match on first occurrence is correct because session_id appears at top
# level before tool_response in observed payloads.
[[ "$INPUT" != *'"session_id"'* ]] && exit 0
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0

# Anchor all id and model extraction to tool_response.
[[ "$INPUT" != *'"tool_response"'* ]] && exit 0
_tail="${INPUT#*\"tool_response\":}"

# Extract agent id from tool_response — three-pass cascade:
# (a)  Primary: camelCase "agentId" (unnamed/background agents, Probe 0.3).
# (a)  Fallback: snake_case "agent_id" (named Agent-Teams teammates, harness
#      2.1.185; value arrives as "<name>@session-<short-sid>").
# (a2) Last-resort: text regex over tool_response substring — bounded char
#      class [A-Za-z0-9_.@-] stops at the JSON backslash-escape boundary and
#      does not over-capture the following "name:" field.
# Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C1(a/a2)
AGENT_ID=""
if [[ "$_tail" == *'"agentId"'* ]]; then
  _tmp="${_tail#*\"agentId\":\"}"
  AGENT_ID="${_tmp%%\"*}"
fi
if [[ -z "$AGENT_ID" ]] && [[ "$_tail" == *'"agent_id"'* ]]; then
  _tmp="${_tail#*\"agent_id\":\"}"
  AGENT_ID="${_tmp%%\"*}"
fi
if [[ -z "$AGENT_ID" ]]; then
  # bash =~ regex; no external tools needed for bounded char-class match.
  if [[ "$_tail" =~ agent_?id:[[:space:]]*\"?([A-Za-z0-9_.@-]+) ]]; then
    AGENT_ID="${BASH_REMATCH[1]}"
  fi
fi

# (b) Format guard — accept bare lowercase hex (≥12 chars, unnamed agents) OR
# teammate canonical id (<name>@session-<short>) from the harness. Reject
# anything else fail-closed (AC5).
# Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C1(b)
[[ -z "$AGENT_ID" ]] && exit 0
if [[ ! "$AGENT_ID" =~ ^[a-f0-9]{12,}$ ]] && \
   [[ ! "$AGENT_ID" =~ ^[A-Za-z0-9_.-]+@session-[a-z0-9-]+$ ]]; then
  exit 0
fi

# (c) Model — three-source precedence:
#   1. tool_response.resolvedModel  (harness-resolved actual model string, e.g.
#      "claude-opus-4-8[1m]"; absent when tool_response carries no model info)
#   2. tool_response.model          (secondary field in tool_response)
#   3. tool_input.model             (caller override; absent for most teammate /
#      background dispatches that do not specify a model explicitly)
#   4. "unknown"                    (graceful degrade for legacy/future payloads)
# Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C1(c)
MODEL="unknown"
SUBAGENT_TYPE="unknown"

# Source 1: tool_response.resolvedModel (reuse _tail already anchored above)
if [[ "$_tail" == *'"resolvedModel"'* ]]; then
  _tmp="${_tail#*\"resolvedModel\":\"}"
  MODEL="${_tmp%%\"*}"
  [[ -z "$MODEL" ]] && MODEL="unknown"
fi
# Source 2: tool_response.model
if [[ "$MODEL" == "unknown" ]] && [[ "$_tail" == *'"model"'* ]]; then
  _tmp="${_tail#*\"model\":\"}"
  MODEL="${_tmp%%\"*}"
  [[ -z "$MODEL" ]] && MODEL="unknown"
fi
# Source 3+4: tool_input.model / "unknown"; subagent_type lives in tool_input
if [[ "$INPUT" == *'"tool_input"'* ]]; then
  _ti="${INPUT#*\"tool_input\":}"
  if [[ "$MODEL" == "unknown" ]] && [[ "$_ti" == *'"model"'* ]]; then
    _tmp="${_ti#*\"model\":\"}"
    MODEL="${_tmp%%\"*}"
    [[ -z "$MODEL" ]] && MODEL="unknown"
  fi
  # Extract subagent_type from tool_input (confirmed location per Phase 2 Chunk 1 probe)
  if [[ "$_ti" == *'"subagent_type"'* ]]; then
    _tmp="${_ti#*\"subagent_type\":\"}"
    SUBAGENT_TYPE="${_tmp%%\"*}"
    [[ -z "$SUBAGENT_TYPE" ]] && SUBAGENT_TYPE="unknown"
  fi
fi

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_BASE="${GIT_ROOT}/.git/coordinator-sessions"
SESSION_DIR="${SESSIONS_BASE}/${SESSION_ID}"
AGENT_DIR="${SESSIONS_BASE}/.agents/${AGENT_ID}"
DISPATCHED="${SESSION_DIR}/dispatched-agents.txt"
EM_BACKPOINTER="${AGENT_DIR}/em-session-id.txt"

# Resolve coordinator root once for library fallback lookups (soft-degrade: _cc_root=""
# on .doe-root miss — hook always exits 0, never hard-fails on missing libs).
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# --- example-orchestration-hub --advisory fast-path: hooks.track_dispatched_agents ---
# Class A bookkeeping (op-specific builder): params built from pre-resolved local scalars
# (AGENT_ID / MODEL / SUBAGENT_TYPE) — NOT the generic advisory_flatten_params.
# Degrade-silent: if the C0 helper is absent, the client is down, or jq is unavailable,
# the local write logic below always runs regardless.
# Spec backlink: cross-repo/inbox/2026-07-05-strang-05-advisory-hook-wiring-spec.md
_AFC="${_cc_root:+$_cc_root/hooks/scripts/lib/advisory-flatten-call.sh}"
[ -n "$_AFC" ] && [ -f "$_AFC" ] && . "$_AFC"
# Init session-dir if missing (slow path mirrors track-touched-files.sh).
if [[ ! -d "$SESSION_DIR" ]]; then
  LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
  [[ ! -f "$LIB_PATH" && -n "$_cc_root" ]] && LIB_PATH="${_cc_root}/lib/coordinator-session.sh"
  if [[ -f "$LIB_PATH" ]]; then
    # shellcheck source=/dev/null
    source "$LIB_PATH"
    cs_init "$SESSION_ID" 2>/dev/null || true
  else
    mkdir -p "$SESSION_DIR" 2>/dev/null
  fi
fi

# Init agent-dir + write back-pointer atomically (the Staff Engineer v2 finding 3).
# `-s` test: file exists AND is non-empty. Empty back-pointers (partial-write
# survivors) trigger re-write. The temp+rename pattern means a concurrent
# fire either succeeds-second-or-cleans-up — no orphan temp files.
mkdir -p "$AGENT_DIR" 2>/dev/null
if [[ ! -s "$EM_BACKPOINTER" ]]; then
  TMP_BP="${EM_BACKPOINTER}.tmp.$$"
  if echo "$SESSION_ID" > "$TMP_BP" 2>/dev/null; then
    mv "$TMP_BP" "$EM_BACKPOINTER" 2>/dev/null || rm -f "$TMP_BP" 2>/dev/null
  else
    rm -f "$TMP_BP" 2>/dev/null
  fi
fi

# (e) Dedup / collision detect-then-fail-loud.
# Column-1 comparison is type-agnostic (handles bare-hex AND teammate ids).
# When a matching column-1 exists:
#   - same subagent_type  → idempotent dedup (same dispatch shape), silent exit.
#   - different subagent_type → short-sid collision: mark EXISTING row's
#     subagent_type as AMBIGUOUS so C9's lookup returns AMBIGUOUS → fail-closed
#     for both colliding dispatches (AC14 / detect-then-fail-loud).
#     Suffixed-row approach NOT used: the subagent-side resolver reconstructs
#     only the unsuffixed canonical id — a suffixed row is dead data and leaves
#     the exploit open.
# Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C1(e)
[[ -f "$DISPATCHED" ]] || touch "$DISPATCHED" 2>/dev/null
if cut -f1 "$DISPATCHED" 2>/dev/null | grep -qxF "$AGENT_ID"; then
  EXISTING_TYPE=$(awk -F'\t' -v id="$AGENT_ID" '$1==id{print $3; exit}' \
    "$DISPATCHED" 2>/dev/null)
  if [[ "$EXISTING_TYPE" == "$SUBAGENT_TYPE" ]]; then
    exit 0  # idempotent — same dispatch shape
  fi
  # Collision: mark EXISTING row AMBIGUOUS (portable temp+rename; no GNU sed -i).
  # Tolerated TOCTOU: a concurrent append between `awk > tmp` (read) and
  # `mv tmp dispatched` (replace) is silently dropped.  Advisory bookkeeping
  # only; low-probability same-id concurrent fire makes this acceptable.
  _TMP_DA="${DISPATCHED}.tmp.$$"
  awk -F'\t' -v id="$AGENT_ID" 'BEGIN{OFS="\t"} $1==id{$3="AMBIGUOUS"} {print}' \
    "$DISPATCHED" > "$_TMP_DA" 2>/dev/null \
    && mv "$_TMP_DA" "$DISPATCHED" 2>/dev/null \
    || rm -f "$_TMP_DA" 2>/dev/null
  exit 0
fi
printf '%s\t%s\t%s\t%s\n' "$AGENT_ID" "$MODEL" "$SUBAGENT_TYPE" "$(date +%s)" >> "$DISPATCHED"
# async-detached fire-and-forget: off the hook's critical path; local dedup-append above is authoritative.
if declare -f advisory_call >/dev/null 2>&1; then
  (
    # Review: code-reviewer F3 — compute snake form (hyphens→underscores) to match agent-completion-log's approach
    _AIDS="${AGENT_ID//-/_}"
    _PARAMS="$(jq -nc \
      --arg aid "$AGENT_ID" \
      --arg aids "$_AIDS" \
      --arg m "$MODEL" \
      --arg sid "$SESSION_ID" \
      --arg st "$SUBAGENT_TYPE" \
      '{session_id:$sid,dispatched_agent_id:$aid,dispatched_agent_id_snake:$aids,dispatched_model:$m,subagent_type:$st}' \
      2>/dev/null || echo '{}')"
    advisory_call "hooks.track_dispatched_agents" "$_PARAMS" >/dev/null 2>&1 || true
  ) &
  disown 2>/dev/null || true
fi
exit 0
