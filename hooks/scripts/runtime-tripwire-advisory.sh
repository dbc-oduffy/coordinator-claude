#!/usr/bin/env bash
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
#
# SOURCEABLE DESIGN
# =================
# This file may be sourced by a dispatcher that wants check_runtime_tripwire().
# When sourced: only defines the function + sources side-effect-free libs.
# No stdin read, no output, no sentinel/log writes happen at source time.
# The bottom main-guard (BASH_SOURCE[0] == 0) handles standalone execution.

# NOTE: -e deliberately omitted. This is an advisory hook and must fail-open;
# critical sections use explicit || true guards. A blanket -e would abort on
# any subcommand non-zero (stat/jq/find), defeating the fail-open contract.
set -uo pipefail

# --- Source side-effect-free libs at file scope (safe when this file is sourced) ---
# Both libs only DEFINE functions; no side effects at source time.
_rttw_self_dir="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib/runtime-thresholds.sh
source "${_rttw_self_dir}/lib/runtime-thresholds.sh" 2>/dev/null || true
# shellcheck source=../../lib/coordinator-state-root.sh
# Source state-root seam (defines coordinator_state_root used in check_runtime_tripwire).
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4/AC4
source "${_rttw_self_dir}/../../lib/coordinator-state-root.sh" 2>/dev/null || true

# Resolve coordinator content root for flat-path fallbacks (maximalist-cutover migration).
# Fail-open: advisory PostToolUse hook must never hard-exit on infra absence; empty _cc_root
# is safe because all consumers guard with [[ -f … ]] before sourcing.
# Deviation from standard exit-1 guard: this hook's contract is fail-open (see -e omission note).
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "${_rttw_self_dir}/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# coordinator-session.sh is sourced lazily inside check_runtime_tripwire() only
# when the resolver-based fallback is needed — kept lazy to avoid the load cost
# on the common path and because it's optional (absent = graceful degrade).

# ---------------------------------------------------------------------------
# check_runtime_tripwire SESSION_ID [AGENT_ID]
#
# Advisory check: if the subagent identified by SESSION_ID has exceeded its
# model-specific runtime threshold, prints the additionalContext JSON nudge to
# stdout and returns 0. Prints nothing and returns 0 on any early-exit path.
# NEVER blocks (advisory-only hook contract).
#
# $1 — session_id (required; empty → return 0 immediately)
# $2 — agent_id   (optional; may be empty; used for resolver-based fallback)
# ---------------------------------------------------------------------------
check_runtime_tripwire() {
  local SESSION_ID="${1:-}"
  local AGENT_ID="${2:-}"

  # Fail-open: can't discriminate without a session_id
  [[ -z "$SESSION_ID" ]] && return 0

  # Security: reject session ids containing path-traversal characters (notably '/' and '..')
  # before any path construction. Canonical charset: [A-Za-z0-9_@-]. An id with
  # '/' or '..' could escape /tmp via the bark-once SENTINEL path construction.
  # Treat as absent — return 0 (silent no-op), same behaviour as the empty-SESSION_ID
  # guard above. Mirrors the OWN_AGENT_ID guard below (strang-06 B commit 19d0991).
  if [[ ! "$SESSION_ID" =~ ^[A-Za-z0-9_@-]+$ ]]; then
    return 0
  fi

  # --- Subagent-detect: is THIS firing session_id a subagent's? ---
  # Each subagent session_id is recorded as a subdirectory under .agents/.
  # If SESSION_ID exists there, we're inside a subagent — proceed.
  # If not found, this is the EM session — return 0 (EM-side hook handles that half).
  local GIT_ROOT
  GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
  [[ -z "$GIT_ROOT" ]] && return 0

  local AGENTS_DIR="$GIT_ROOT/.git/coordinator-sessions/.agents"
  [[ ! -d "$AGENTS_DIR" ]] && return 0

  local OWN_AGENT_ID=""
  if [[ -d "$AGENTS_DIR/$SESSION_ID" ]]; then
    OWN_AGENT_ID="$SESSION_ID"
  fi

  # Resolver-based fallback: named teammates carry a<name>-<16hex> as top-level
  # agent_id; their .agents/ dir is keyed on the canonical id (name@session-<short>),
  # NOT the bare SESSION_ID. If SESSION_ID detection missed AND agent_id is present,
  # resolve and test the canonical path.
  #
  # PRESERVE invariant: the SESSION_ID path above is the primary path — it catches ALL
  # unnamed subagent events including non-edit PostToolUse where agent_id is absent.
  # Replacing it with the resolver would regress unnamed subagent detection on non-edit
  # events. This is an ADDITIVE fallback only entered when SESSION_ID detection missed.
  #
  # Stale-dir degrade: if the canonical dir exists but em-session-id.txt is absent →
  # OWN_AGENT_ID is set to the canonical id → the EM_SID_FILE check below catches it
  # and returns 0 (fail-open, same behaviour as the SESSION_ID stale-dir path).
  # Review: code-reviewer — F4: updated stale "L82" line reference to "at L122".
  # Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C11
  if [[ -z "$OWN_AGENT_ID" && -n "$AGENT_ID" ]]; then
    if ! declare -f resolve_subagent_identity >/dev/null 2>&1; then
      local _adv_lib="${_rttw_self_dir}/../../lib/coordinator-session.sh"
      [[ ! -f "$_adv_lib" ]] && _adv_lib="$_cc_root/lib/coordinator-session.sh"
      # shellcheck source=/dev/null
      [[ -f "$_adv_lib" ]] && source "$_adv_lib" 2>/dev/null || true
    fi
    if declare -f resolve_subagent_identity >/dev/null 2>&1; then
      local _adv_canonical
      _adv_canonical="$(resolve_subagent_identity "$AGENT_ID" "$SESSION_ID")"
      if [[ -n "$_adv_canonical" && -d "$AGENTS_DIR/$_adv_canonical" ]]; then
        OWN_AGENT_ID="$_adv_canonical"
      fi
    fi
  fi

  # Security: reject ids containing path-traversal characters (notably '/' and '..')
  # before any path construction. Canonical charset: [A-Za-z0-9_@-]. An id with
  # '/' or '..' could escape the intended AGENTS_DIR subtree via path concatenation.
  # Treat as absent — the [[ -z ]] guard below returns 0 (silent no-op), same
  # behaviour as the agent-dir-absent / stale-dir paths.
  if [[ -n "$OWN_AGENT_ID" && ! "$OWN_AGENT_ID" =~ ^[A-Za-z0-9_@-]+$ ]]; then
    OWN_AGENT_ID=""
  fi

  # Not a subagent — let the EM-side hook handle it.
  # Review: code-reviewer — stale-dir degrade note: stale .agents/<id>/ dirs from
  # crashed prior sessions that reused a session_id would match the directory
  # check above and reach the EM_SID_FILE check. If the back-pointer file is
  # absent (no em-session-id.txt), the hook returns 0 — this is
  # fail-open (silent), not a false alarm. Real subagents always have the
  # back-pointer written; the absence is the degrade signal.
  [[ -z "$OWN_AGENT_ID" ]] && return 0

  # --- Find EM session id from back-pointer ---
  local EM_SID_FILE="$AGENTS_DIR/$OWN_AGENT_ID/em-session-id.txt"
  [[ ! -f "$EM_SID_FILE" ]] && return 0
  local EM_SID
  EM_SID=$(head -1 "$EM_SID_FILE" 2>/dev/null | tr -d '[:space:]' || true)
  [[ -z "$EM_SID" ]] && return 0

  # --- Read own dispatched-at + model from EM's dispatched-agents.txt ---
  # Record shape (as of 2026-06-08): agentId\tmodel\tsubagent_type\tdispatched-at
  local DISPATCH_FILE="$GIT_ROOT/.git/coordinator-sessions/$EM_SID/dispatched-agents.txt"
  [[ ! -f "$DISPATCH_FILE" ]] && return 0

  # Match on field 1 exactly via awk — guards against a longer agentId that has
  # OWN_AGENT_ID as a substring. Random hex makes collisions astronomically
  # unlikely but `awk $1 == id` makes the invariant explicit and survives any
  # future ID-format change.
  local OWN_ROW
  OWN_ROW=$(awk -F'\t' -v id="$OWN_AGENT_ID" '$1 == id { print; exit }' "$DISPATCH_FILE" 2>/dev/null || true)
  [[ -z "$OWN_ROW" ]] && return 0

  local MODEL DISPATCHED_AT
  MODEL=$(echo "$OWN_ROW" | cut -f2)
  DISPATCHED_AT=$(echo "$OWN_ROW" | cut -f4)

  # Backward-compat: legacy 3-col records have no col 4 — skip timing check
  [[ ! "$DISPATCHED_AT" =~ ^[0-9]+$ ]] && return 0
  [[ "$DISPATCHED_AT" -eq 0 ]] && return 0

  # --- Compute elapsed minutes ---
  local NOW ELAPSED_SEC ELAPSED_MIN
  NOW=$(date +%s)
  ELAPSED_SEC=$(( NOW - DISPATCHED_AT ))
  ELAPSED_MIN=$(( ELAPSED_SEC / 60 ))

  # --- Always compute threshold — needed by WRAP_TEXT on both emit paths ---
  local THRESHOLD_MIN
  THRESHOLD_MIN=$(runtime_threshold_minutes "$MODEL")

  # --- Cross-hook wrap-signal: EM first-fire writes this artifact when agent dir exists ---
  # Fires deterministically regardless of this session's elapsed time, closing the idle-EM
  # blindspot: the EM's additionalContext nudge is only visible when the EM is active; this
  # artifact lands the nudge inside the agent session on its next tool call unconditionally.
  # Artifact cleared before emitting — one-shot semantics; concurrent hook fires degrade
  # silently (rm idempotent). Sentinel is still checked after (prevents double-nudge if the
  # threshold path already fired this session). Primary use case: EM detects overrun before
  # the agent's own threshold fires (e.g. EM at 9 min, agent threshold at 12 min).
  # Spec backlink: cross-repo/inbox/2026-07-06-strang-06-nag-to-action-hook-conversions.md
  local WRAP_SIGNAL_FILE="$AGENTS_DIR/$OWN_AGENT_ID/wrap-requested.txt"
  local _wrap_signal_active=false
  local _fire_type="agent-side"
  if [[ -f "$WRAP_SIGNAL_FILE" ]]; then
    rm -f "$WRAP_SIGNAL_FILE" 2>/dev/null || true
    _wrap_signal_active=true
    _fire_type="agent-side-wrap-signal"
  fi

  if [[ "$_wrap_signal_active" != true ]]; then
    # --- Threshold check (normal threshold-based path only) ---
    [[ "$ELAPSED_MIN" -lt "$THRESHOLD_MIN" ]] && return 0
  fi

  # --- Bark-once sentinel (both paths: one nudge per dispatch per session) ---
  # The sentinel applies to both the threshold path and the wrap-signal path:
  # if the threshold path already fired this session, the agent has its nudge;
  # a concurrent wrap-signal would be redundant. The primary value of the wrap-signal
  # is firing BEFORE the agent's own threshold (e.g. EM detects overrun at 9 min,
  # agent's threshold is 12 min) — in that case the sentinel is not yet set.
  local SENTINEL="/tmp/runtime-tripwire-agent-${SESSION_ID}"
  [[ -f "$SENTINEL" ]] && return 0
  touch "$SENTINEL"

  # --- Autonomous-run detection (soften language slightly per compaction-advisory pattern) ---
  local AUTONOMOUS=false
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
  # Resolve state root via seam so fire-log lands in example-orchestration-hub when cwd is the meta-repo.
  # Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4/AC4
  local _csr_rtw
  if declare -f coordinator_state_root >/dev/null 2>&1; then
    _csr_rtw="$(coordinator_state_root 2>/dev/null)" || _csr_rtw="${GIT_ROOT}/state"
  else
    _csr_rtw="${GIT_ROOT}/state"
  fi
  local FIRE_LOG="${_csr_rtw}/runtime-tripwire-fire-log.tsv"
  mkdir -p "$(dirname "$FIRE_LOG")" 2>/dev/null || true
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
    "$OWN_AGENT_ID" \
    "$MODEL" \
    "$ELAPSED_MIN" \
    "$_fire_type" >> "$FIRE_LOG" 2>/dev/null || true

  # --- Emit additionalContext with WRAP-SHAPE prescription ---
  # CANONICAL TEXT — DO NOT REWORD without updating docs/wiki/runtime-tripwire.md §3
  # AC5 grep targets are embedded verbatim in the WRAP_TEXT strings below.
  local WRAP_TEXT
  # Review: code-reviewer — F4: wrap-signal path needs a distinct message. The threshold-path
  # text ("past the ~X min runtime tripwire") is factually wrong when the EM fires an early-wrap
  # before the agent's own threshold is reached (e.g. EM at 9 min, Sonnet threshold 12 min).
  # Wrap-signal path and threshold path now produce distinct strings; AC5 grep targets preserved
  # in both ("stop starting new work", "persist any partial state to disk",
  # "write a successor-handoff stub", "return").
  if [[ "$_wrap_signal_active" == true ]]; then
    if [[ "$AUTONOMOUS" == true ]]; then
      WRAP_TEXT="EM-requested early wrap: you've been running ~${ELAPSED_MIN} min; threshold for ${MODEL} is ~${THRESHOLD_MIN} min, but the EM flagged an early-wrap signal. Autonomous run active. Trust-but-verify with the EM as authority: form your own judgment, but assume the EM will evaluate it. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
    else
      WRAP_TEXT="EM-requested early wrap: you've been running ~${ELAPSED_MIN} min; threshold for ${MODEL} is ~${THRESHOLD_MIN} min, but the EM flagged an early-wrap signal. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
    fi
  elif [[ "$AUTONOMOUS" == true ]]; then
    WRAP_TEXT="RUNTIME TRIPWIRE — you've been running ~${ELAPSED_MIN} minutes (past the ~${THRESHOLD_MIN} min runtime tripwire for ${MODEL}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. Autonomous run active. Trust-but-verify with the EM as authority: form your own judgment, but assume the EM will evaluate it. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
  else
    WRAP_TEXT="RUNTIME TRIPWIRE — you've been running ~${ELAPSED_MIN} minutes (past the ~${THRESHOLD_MIN} min runtime tripwire for ${MODEL}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. Trust-but-verify with the EM as authority: form your own judgment, but assume the EM will evaluate it. Wrap shape (the default): stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return. If you judge yourself genuinely close to a clean return (≤2-3 min): say so explicitly in your return so the EM can decide whether to wait."
  fi

  jq -n --arg ctx "$WRAP_TEXT" \
    '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
  return 0
}

# ---------------------------------------------------------------------------
# Bottom main-guard — standalone execution path only
# When sourced by a dispatcher: none of this runs; only check_runtime_tripwire
# is defined (+ libs sourced at file scope above).
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # --- Safe stdin read (timeout-guarded; matches context-pressure-advisory.sh:25-29) ---
  if command -v timeout >/dev/null 2>&1; then
    HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    HOOK_INPUT=$(cat)
  fi

  # --- Extract session_id (jq preferred, sed fallback per :32-38) ---
  # transcript_path not needed here — timing uses dispatched-agents.txt, not transcript mtime
  if command -v jq >/dev/null 2>&1; then
    session_id=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  else
    session_id=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  # Fail-open: can't discriminate without a session_id
  [[ -z "$session_id" ]] && exit 0

  # --- Extract top-level agent_id (present in named-teammate subagent payloads) ---
  # Absent on top-level EM fires. Used for resolver-based subagent-detection fallback.
  # Named-teammate payloads carry this as a<name>-<16hex> (subagent-side grammar,
  # probe-confirmed harness 2.1.185). See C11 in the identity-linkage reconciliation plan.
  # Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C11
  agent_id=""
  if command -v jq >/dev/null 2>&1; then
    agent_id=$(echo "$HOOK_INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)
  else
    agent_id=$(echo "$HOOK_INPUT" | sed -n 's/.*"agent_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  check_runtime_tripwire "$session_id" "$agent_id"; exit 0
fi
