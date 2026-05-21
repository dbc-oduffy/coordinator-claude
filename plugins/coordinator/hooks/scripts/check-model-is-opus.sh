#!/bin/bash
# SessionStart hook: warn if recent assistant turns ran on a non-Opus model.
#
# Background: settings.json `model: opus` is the declared default, but the
# runtime model can silently drift to Sonnet (e.g. after /model, or because
# of plan-mode swap, fast-mode toggle, or harness defaulting). Drift is
# invisible in the UI — a full workday on the wrong model wastes hours.
#
# Detection strategy:
#   1. Read transcript_path from SessionStart hook input JSON.
#   2. If the current transcript has assistant turns (compact/resume), grep
#      the most-recent .message.model line. Warn if not opus.
#   3. If current transcript is empty (fresh startup/clear), fall back to the
#      most-recently-modified OTHER .jsonl in the same project dir — that's
#      the previous session. Warn if that one ran non-Opus, since the
#      runtime default may carry forward.
#
# This is a belt; the suspenders is the EM-side self-check rule in
# coordinator CLAUDE.md (the EM's own system prompt is the only authoritative
# source for the *current* session's model at startup, before any turn).
#
# Always exits 0 — never blocks session start. Output (raw text) becomes
# additionalContext injected into the session.

# --- Safe stdin read with timeout (mirror existing hook pattern) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# --- Extract transcript_path ---
TRANSCRIPT=""
if command -v jq &>/dev/null; then
  TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
else
  if [[ "$INPUT" == *'"transcript_path"'* ]]; then
    _tmp="${INPUT#*\"transcript_path\":\"}"
    TRANSCRIPT="${_tmp%%\"*}"
    # Un-escape backslashes (Windows paths land double-escaped in JSON)
    TRANSCRIPT="${TRANSCRIPT//\\\\/\\}"
  fi
fi

[[ -z "$TRANSCRIPT" ]] && exit 0

# --- Helper: extract the most-recent assistant model from a transcript ---
# Each line is a JSON record; assistant messages carry .message.model.
# We tail-read to avoid scanning long transcripts.
latest_model() {
  local file="$1"
  [[ ! -f "$file" ]] && return
  # Reverse-scan up to 200 lines for the last model field
  tac "$file" 2>/dev/null | head -200 \
    | grep -o '"model":"[^"]*"' \
    | head -1 \
    | sed 's/"model":"//; s/"$//'
}

CURRENT_MODEL=$(latest_model "$TRANSCRIPT")
SOURCE="current-session"

# Fallback: previous session in same project dir
if [[ -z "$CURRENT_MODEL" ]]; then
  PROJECT_DIR=$(dirname "$TRANSCRIPT")
  CURRENT_BASENAME=$(basename "$TRANSCRIPT")
  if [[ -d "$PROJECT_DIR" ]]; then
    # Most-recent .jsonl that isn't the current transcript
    PREV=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | grep -v "/${CURRENT_BASENAME}$" | head -1)
    if [[ -n "$PREV" ]]; then
      CURRENT_MODEL=$(latest_model "$PREV")
      SOURCE="previous-session"
    fi
  fi
fi

[[ -z "$CURRENT_MODEL" ]] && exit 0

# --- Verdict: Opus is OK, anything else warns ---
case "$CURRENT_MODEL" in
  *opus*)
    # Quiet on Opus — no need to nag. Exit silently.
    exit 0
    ;;
esac

# --- Non-Opus: emit a loud banner via additionalContext ---
if [[ "$SOURCE" == "current-session" ]]; then
  cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  ⚠  MODEL DRIFT WARNING — current session running on ${CURRENT_MODEL}
║  Expected: claude-opus-4-7 (or later opus). Settings.json default is opus.
║  Action: emit a visible WARN to the PM as your first message,
║  recommend toggling back to Opus via /model before proceeding with
║  load-bearing work. Sonnet/Haiku at EM altitude breaks the workflow.
╚══════════════════════════════════════════════════════════════════╝

EOF
else
  cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  ⚠  MODEL DRIFT WARNING — previous session ran on ${CURRENT_MODEL}
║  This session may have inherited the same runtime default.
║  Action: verify your system prompt declares Opus. If it doesn't,
║  WARN the PM at the start of your first response and recommend /model.
╚══════════════════════════════════════════════════════════════════╝

EOF
fi

exit 0
