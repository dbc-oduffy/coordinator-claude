#!/usr/bin/env bash
# Context Pressure Advisory — PostToolUse hook
#
# Moved from UserPromptSubmit (2026-03-28): UserPromptSubmit hooks block
# before the model generates ANY response. On Windows/Git Bash, timeout
# enforcement is unreliable — a hung stdin read on every message killed
# all sessions. PostToolUse is safer: fires after a tool completes, so a
# hang only delays the next tool step rather than freezing the terminal.
#
# Phase 1: Post-compaction orientation (sentinel bridge) — checked every
#          invocation (cheap stat call, no throttle)
# Phase 2: Threshold-based warnings — self-throttled to run every 5 min
#
# Hook execution is serial within a session — no TOCTOU risk on sentinel
# check-then-delete.
#
# Sourceable: when sourced, only check_context_pressure() is defined.
# No stdin read, no output, no side effects at source time.
# Dispatcher calls: check_context_pressure "$session_id" "$transcript_path"
set -uo pipefail
# NOTE: -e deliberately omitted. This is an advisory hook and must fail-open;
# critical sections use explicit `|| true` guards. A blanket -e would abort
# the hook on any subcommand non-zero (e.g., stat/jq/find), defeating that.

# ---------------------------------------------------------------------------
# check_context_pressure SESSION_ID TRANSCRIPT_PATH
#
# Advisory-only: prints the advisory JSON to stdout and returns 0 when a
# threshold fires; prints nothing and returns 0 otherwise. Never blocks.
# Must NOT read stdin. All state lives in /tmp sentinels (side effects
# preserved verbatim from the original top-level implementation).
# ---------------------------------------------------------------------------
check_context_pressure() {
  local session_id="$1"
  local transcript_path="$2"

  if [[ -z "$session_id" ]]; then
    return 0  # fail-open
  fi

  # --- Phase 1: Post-compaction sentinel bridge ---
  # PreCompact writes /tmp/compaction-occurred-{SESSION_ID} as a side-effect,
  # plus /tmp/compaction-state-{SESSION_ID}.md with session state snapshot.
  # We detect the sentinel here, read the state, and emit both. Delete-on-read.
  # No throttle — compaction recovery should fire on the first tool use after.
  local compaction_sentinel="/tmp/compaction-occurred-${session_id}"
  local compaction_state="/tmp/compaction-state-${session_id}.md"

  if [[ -f "$compaction_sentinel" ]]; then
    # Read pre-compaction transcript size recorded by precompact hook, then
    # delete the sentinel.
    local pre_size
    pre_size=$(head -1 "$compaction_sentinel" 2>/dev/null | tr -d '[:space:]' || true)
    rm -f "$compaction_sentinel"

    # False-positive guard: Claude Code fires PreCompact in scenarios that don't
    # actually shrink the parent transcript meaningfully (notably subagent-result
    # integration on 1M-context models). If the transcript size hasn't dropped
    # at least 15% since precompact fired, treat as a false alarm: clean up state
    # and exit silently rather than emitting a misleading orientation prompt.
    if [[ -n "$pre_size" && "$pre_size" =~ ^[0-9]+$ && -n "$transcript_path" && -f "$transcript_path" ]]; then
      local post_size
      post_size=$(stat -c '%s' "$transcript_path" 2>/dev/null || stat -f '%z' "$transcript_path" 2>/dev/null || echo "$pre_size")
      # Threshold: post must be < pre * 0.85 (i.e., >=15% shrink) to count as real.
      local threshold=$(( pre_size * 85 / 100 ))
      if [[ "$post_size" -ge "$threshold" ]]; then
        # No meaningful shrink — silently consume associated state and exit.
        rm -f "$compaction_state"
        return 0
      fi
    fi

    local state_content=""
    if [[ -f "$compaction_state" ]]; then
      state_content=$(cat "$compaction_state" 2>/dev/null || true)
      rm -f "$compaction_state"
    fi

    if [[ -n "$state_content" ]]; then
      local preamble="COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything.\n\n--- PRE-COMPACTION STATE SNAPSHOT ---\n"
      local postamble="\n--- END SNAPSHOT ---"
      jq -n \
        --arg preamble "$preamble" \
        --arg state "$state_content" \
        --arg postamble "$postamble" \
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ($preamble + $state + $postamble)}}'
    else
      cat <<'JSONEOF'
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything."}}
JSONEOF
    fi
    return 0
  fi

  # --- Phase 2: Threshold-based context pressure warnings ---
  # Self-throttle: only run the expensive transcript size check every 5 minutes.
  # The sentinel file's mtime is the clock. On every other invocation we exit
  # immediately — this keeps PostToolUse overhead near zero.
  local throttle_sentinel="/tmp/context-pressure-throttle-${session_id}"
  local throttle_seconds=300  # 5 minutes

  if [[ -f "$throttle_sentinel" ]]; then
    # Check age of throttle sentinel
    local sentinel_mtime
    if [[ "$OSTYPE" == darwin* ]]; then
      sentinel_mtime=$(stat -f %m "$throttle_sentinel" 2>/dev/null || echo 0)
    else
      sentinel_mtime=$(stat -c %Y "$throttle_sentinel" 2>/dev/null || echo 0)
    fi
    local now elapsed
    now=$(date +%s)
    elapsed=$(( now - sentinel_mtime ))
    if [[ "$elapsed" -lt "$throttle_seconds" ]]; then
      return 0  # fast path — checked recently, skip
    fi
  fi

  # Update throttle timestamp (touch even if we end up not emitting anything)
  touch "$throttle_sentinel"

  # Calibration (2026-05-18, observed on Opus 1M): auto-compaction now fires at
  # ~60% of context window (e.g. 600K on a 1M window). Earlier research had it
  # at ~83.5% on a 200K window; treat 60% as the new global trigger until we
  # observe per-model divergence. Override via CONTEXT_*_THRESHOLD env vars.
  # We can't know exact token count — file size in bytes is a ROUGH proxy.
  # Read-heavy EM sessions (markdown/substrate/JSON) run 6-8 bytes/token; prose ~4-5.
  # 7 is mid-band, biased to the read-heavy case this hook front-loads on.
  # Recalibrated 2026-05-27 (queue 2026-05-26): prior value 5 over-counted tokens
  # on read-heavy transcripts and fired HIGH at a real ~55% byte-of-window with
  # runway left. CRITICAL_PCT is HELD at 50 (ratio-only recalibration, PM decision
  # 2026-05-27): the BPT 5→7 change shifts the trip ~40% later in bytes, addressing
  # the premature-firing report without stacking a percentage-gate raise.

  if [[ -z "$transcript_path" || ! -f "$transcript_path" ]]; then
    return 0  # fail-open: no transcript to measure
  fi

  # --- Model detection — robust, format- and preamble-agnostic ---
  # Two prior bugs (fixed here, 2026-05-26): (1) the jq path read top-level
  # `.model`, but Claude Code nests it at `.message.model`, so it never matched;
  # (2) the sed fallback was capped at `head -n 20`, but preamble-heavy sessions
  # (pickup handoffs, attachments, queue-ops, system reminders) push the first
  # assistant line — the first one carrying a model ID — well past line 20. The
  # net effect was MODEL_ID="" on exactly the read-heavy sessions an EM front-loads
  # context on, defaulting CONTEXT_WINDOW to 200K and firing a false CRITICAL at
  # ~500KB (~11% of a real 1M Opus window). Grep the first literal
  # `"model":"claude-..."` instead: -m1 stops at the first matching LINE (cost
  # bounded by the first model-bearing line, not transcript size), the `claude-`
  # anchor disambiguates from any other "model" key in tool output, and it is
  # agnostic to JSON nesting. The `[^"]*` character class (no embedded quote) is
  # load-bearing twice: it terminates the ID at the closing quote, AND it
  # guarantees MODEL_ID can never contain a `"` that would break the unquoted JSON
  # heredocs below — do not widen it without re-checking those heredocs. The
  # trailing `head -1` defends against a minified line carrying multiple matches.
  local model_id
  model_id=$(grep -m1 -oE '"model"[[:space:]]*:[[:space:]]*"claude-[^"]*"' "$transcript_path" 2>/dev/null \
    | grep -oE 'claude-[^"]*' | head -1 || true)
  # Detection-failure diagnostic (stderr only — never touches the JSON stdout the
  # hook consumer parses). Surfaces the silent case Finding 7 flagged: an
  # undetected model assumes the 1M default below, which on a genuinely-200K setup
  # means warnings fire too late (or never). Rare given the robust detection above.
  if [[ -z "$model_id" ]]; then
    echo "context-pressure-advisory: model detection failed; assuming 1M-token window (pin via COORDINATOR_DEFAULT_CONTEXT_WINDOW for 200K setups)" >&2
  fi

  # --- Context window size by model (tokens) ---
  # Note: Anthropic encodes 1M-context variants with a "[1m]" suffix on the model ID
  # (e.g., "claude-opus-4-7[1m]"). Match that suffix explicitly before the bare model
  # pattern so a plain ID falls through to the 200K default.
  local context_window
  case "$model_id" in
    # Explicit 1M-context variants — must match before the bare family arms below.
    # Anthropic encodes 1M-context variants with a "[1m]" suffix (e.g.
    # "claude-opus-4-7[1m]"); some ID shapes use a "-1m" infix.
    # Matching here prevents a 1M-context Sonnet from falling into the *sonnet*
    # arm and producing false-positive handoff nudges at ~200K bytes.
    # NB: no bare `*1m*` arm — it would false-match a date/version token (e.g.
    # a hypothetical "claude-sonnet-4-10m") and assign a 200K model the 1M window.
    *\[1m\]*)       context_window=1000000 ;;  # Explicit "[1m]" suffix
    *-1m*)          context_window=1000000 ;;  # "-1m" infix variant
    # Explicit 200K overrides for Opus variants known to ship without the 1M window
    # (add specific model IDs here as they appear).
    # Generic family fallbacks — any Opus is presumed 1M, any Sonnet/Haiku 200K,
    # unless an override above caught it first.
    # Family-fallback patterns survive minor version bumps; pinned arms break.
    *opus*)         context_window=1000000 ;;  # Opus family default: 1M
    *sonnet*)       context_window=200000  ;;  # Sonnet family default: 200K
    *haiku*)        context_window=200000  ;;  # Haiku family default: 200K
    # Unknown model OR detection failure (empty model_id): with robust detection
    # above this arm is now rarely reached, but it is also the error-recovery path
    # (grep failure / transcript race), so do not delete it as "only for unknown
    # models". Default to Opus/1M — Opus is the EM's primary system, and a too-large window
    # only delays warnings (it never fires a false CRITICAL), which is the safer
    # failure direction than the prior 200K default's premature-handoff churn.
    # Sonnet-only setups can pin the conservative window via the override.
    *)              context_window=${COORDINATOR_DEFAULT_CONTEXT_WINDOW:-1000000} ;;
  esac

  # --- Threshold percentages ---
  # Auto-compaction trigger observed at ~60% of context window (2026-05-18).
  # CRITICAL at 50% gives ~10% headroom before compaction — enough for a handoff
  # to execute (several tool calls). ADVISORY at 40% is the "start wrapping up"
  # signal. Previous values (57/50) fired too late and sessions hit compaction
  # before the handoff could complete.
  # CRITICAL_PCT HELD at 50 (PM decision 2026-05-27, ratio-only): the BYTES_PER_TOKEN 5→7
  # change alone shifts the trip ~40% later in bytes, addressing the premature-firing report
  # without stacking a percentage-gate raise that would erode compaction headroom on
  # prose-light sessions. ~10% headroom below the ~60% observed compaction point is preserved.
  local advisory_pct=40
  local critical_pct=50

  # --- Convert to file size thresholds (bytes) ---
  # Read-heavy EM sessions (markdown/substrate/JSON) run 6-8 bytes/token; prose ~4-5.
  # 5 (prior value) over-counted tokens on read-heavy transcripts and fired HIGH at a
  # real ~55% byte-of-window with runway left (queue 2026-05-26). 7 is mid-band, biased
  # to the read-heavy case this hook front-loads on. Still a ROUGH proxy — see message text.
  local bytes_per_token=7
  local advisory_bytes=$(( context_window * advisory_pct * bytes_per_token / 100 ))
  local critical_bytes=$(( context_window * critical_pct * bytes_per_token / 100 ))

  # --- Env var overrides for testing/recalibration ---
  advisory_bytes=${CONTEXT_ADVISORY_THRESHOLD:-$advisory_bytes}
  critical_bytes=${CONTEXT_CRITICAL_THRESHOLD:-$critical_bytes}

  # --- Get transcript file size (cross-platform) ---
  local file_size
  if [[ "$OSTYPE" == darwin* ]]; then
    file_size=$(stat -f %z "$transcript_path" 2>/dev/null || echo 0)
  else
    file_size=$(stat -c %s "$transcript_path" 2>/dev/null || echo 0)
  fi

  if [[ "$file_size" -eq 0 ]]; then
    return 0  # fail-open
  fi

  # --- Bark-once sentinels (scoped to transcript path hash) ---
  local transcript_hash
  if command -v md5sum &>/dev/null; then
    transcript_hash=$(echo -n "$transcript_path" | md5sum | cut -d' ' -f1)
  elif command -v md5 &>/dev/null; then
    transcript_hash=$(echo -n "$transcript_path" | md5 -q)
  elif command -v cksum &>/dev/null; then
    transcript_hash=$(echo -n "$transcript_path" | cksum | awk '{print $1}')
  else
    transcript_hash="$session_id"
  fi

  # Stale sentinel cleanup (>24h old) — scope to this session only.
  # Previously this matched all sessions' sentinels, so session A's cleanup
  # would delete session B's live sentinels. SESSION_ID is guaranteed non-empty
  # here (we exit early above when it's blank), but guard defensively.
  if [[ -n "${session_id:-}" ]]; then
    find /tmp -maxdepth 1 \( -name "context-pressure-*${session_id}*" -o -name "autonomous-run-*${session_id}*" \) -mmin +1440 -delete 2>/dev/null || true
  fi

  # --- Autonomous run detection ---
  local autonomous_sentinel="/tmp/autonomous-run-${session_id}"
  local autonomous_run=false
  if [[ -f "$autonomous_sentinel" ]]; then
    autonomous_run=true
  fi

  local advisory_sentinel="/tmp/context-pressure-advisory-${transcript_hash}"
  local critical_sentinel="/tmp/context-pressure-critical-${transcript_hash}"

  # Critical check first (higher priority)
  if [[ "$file_size" -ge "$critical_bytes" && ! -f "$critical_sentinel" ]]; then
    touch "$advisory_sentinel" "$critical_sentinel"
    local est_pct=$(( file_size * 100 / (context_window * bytes_per_token) ))
    if [[ "$autonomous_run" == true ]]; then
      jq -n \
        --arg ctx "CONTEXT PRESSURE — HIGH (${model_id:-unknown}): est. ~${est_pct}% of window used — a ROUGH byte-based proxy (~${bytes_per_token} bytes/token), not a measured token count. Compaction is close (~60%). Autonomous run active — continuing per PM instruction. Verify all progress is in TaskList and committed to disk. Compaction will compress context but tasks persist. The estimate runs hot on read-heavy sessions. (Transcript: ${file_size} bytes vs ${context_window}-token window)" \
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
    else
      jq -n \
        --arg ctx "CONTEXT PRESSURE — HIGH (${model_id:-unknown}): est. ~${est_pct}% of window used — a ROUGH byte-based proxy (~${bytes_per_token} bytes/token), not a measured token count, so treat it as a soft signal. Auto-compaction is observed near ~60%. If this estimate looks right for the work you've done, consider running /handoff soon — the handoff itself consumes context, so leave headroom. If you front-loaded large reads (the estimate runs hot on read-heavy sessions), you likely have more runway than this suggests. (Transcript: ${file_size} bytes vs ${context_window}-token window)" \
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
    fi
    return 0
  fi

  # Advisory check
  if [[ "$file_size" -ge "$advisory_bytes" && ! -f "$advisory_sentinel" ]]; then
    touch "$advisory_sentinel"
    local est_pct=$(( file_size * 100 / (context_window * bytes_per_token) ))
    if [[ "$autonomous_run" == true ]]; then
      jq -n \
        --arg ctx "CONTEXT PRESSURE — ADVISORY (${model_id:-unknown}): est. ~${est_pct}% of window used — a ROUGH byte-based proxy (~${bytes_per_token} bytes/token), not a measured token count. Context usage is getting heavy. Autonomous run: checkpoint state to disk at the next natural boundary so the run is resumable. The estimate runs hot on read-heavy sessions. (Transcript: ${file_size} bytes vs ${context_window}-token window)" \
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
    else
      jq -n \
        --arg ctx "CONTEXT PRESSURE — ADVISORY (${model_id:-unknown}): est. ~${est_pct}% of window used — a ROUGH byte-based proxy (~${bytes_per_token} bytes/token), not a measured token count. Context usage is getting heavy. Consider completing the current task unit, then running /handoff. This is informational — no action required yet, and the estimate runs hot on read-heavy sessions. (Transcript: ${file_size} bytes vs ${context_window}-token window)" \
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
    fi
    return 0
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Main guard — runs only when executed directly (not when sourced).
# Reads stdin once, extracts session_id + transcript_path, calls the function.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # --- Safe stdin read (the fix for the Windows hang) ---
  # GNU timeout is available in Git Bash via coreutils. If somehow missing,
  # fall back to plain cat — the PostToolUse hook is far less dangerous than
  # UserPromptSubmit even without the timeout wrapper.
  if command -v timeout &>/dev/null; then
    HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    HOOK_INPUT=$(cat)
  fi

  # Extract fields — prefer jq, fall back to sed
  if command -v jq &>/dev/null; then
    session_id=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
    transcript_path=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  else
    # BSD sed treats \s as literal 's' (DR-148 portability audit, 2026-07-10) —
    # [[:space:]] is portable.
    session_id=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    transcript_path=$(echo "$HOOK_INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  check_context_pressure "$session_id" "$transcript_path"
  exit 0
fi
