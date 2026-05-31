#!/bin/bash
# PreToolUse hook: When the EM appends a new entry to an improvement queue
# (central or per-project), surface a four-question friction prompt before the
# write lands. Goal: make "just queue it" more expensive than "just fix it."
#
# Motivation: empirically, the queue is a laundromat for reflexive deferral —
# the EM hits a small structural issue mid-flight, types a queue entry, and
# moves on. Doctrine alone hasn't held (cf. 2026-05-16 self lesson "PM-brought
# improvement with a known fix-locus is an action, not a queue entry"). This
# hook adds tool-boundary friction: every queue-append must justify itself
# against the four laziness traps.
#
# Fires on: Write or Edit where file_path matches *improvement-queue.md.
#
# Skipped (silent pass):
#   - File path doesn't match a queue file.
#   - Edit with no new "- YYYY-MM-DD" entry line in new_string (pruning,
#     reformat, or non-append edits).
#   - Transcript tail shows an active legitimate-author skill:
#     /learn-lessons, /workweek-complete, /workday-complete, /distill,
#     /session-end (these surfaces own queue maintenance).
#   - Authorized override: COORDINATOR_QUEUE_PUNT="<reason>" in env. The
#     reason MUST be non-empty and is logged so the EM can't reuse "1" or
#     "ok" — it has to name what's being punted.
#
# Blocked: any other queue-append. Block message lists the four questions and
# the two ways to proceed (fix it / set COORDINATOR_QUEUE_PUNT="<reason>").
#
# Implementation note: this is a "block to nudge" not a "block to forbid" —
# the override is one env var away. The friction is the cognitive load of
# reading the four questions and writing a plain-English reason, not the
# difficulty of bypassing.

set -uo pipefail

if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch — but require a non-trivial reason. "1", "true", empty,
# "ok", "y", "yes" don't count: the EM has to type a sentence.
PUNT_REASON="${COORDINATOR_QUEUE_PUNT:-}"
if [[ -n "$PUNT_REASON" ]]; then
  PUNT_LOWER=$(printf '%s' "$PUNT_REASON" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
  case "$PUNT_LOWER" in
    1|true|yes|y|ok|okay|sure|fine|""|"-"|"x")
      # Reject trivial reasons — fall through to block path with extra hint.
      TRIVIAL_REASON=1
      ;;
    *)
      # Per Sonnet P3 (2026-05-17): apply threshold to original (non-stripped)
      # form so a sentence like "needs a plan" (12 chars with space) passes,
      # while "fix" / "lazy" / "later" still reject. Stripped-form threshold
      # was harsher than the source comment read.
      if [[ ${#PUNT_REASON} -ge 12 ]]; then
        exit 0
      else
        TRIVIAL_REASON=1
      fi
      ;;
  esac
fi

if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty' 2>/dev/null || true)
  OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null || true)
elif command -v python &>/dev/null || command -v python3 &>/dev/null; then
  PY=$(command -v python || command -v python3)
  # Field-per-line (NOT space-joined) — file_path/transcript_path can contain
  # spaces (e.g. a Windows path under "C:\Users\First Last\"), which the old
  # `read -r A B C` form split across the wrong vars and silently mis-routed.
  # Mirrors the fix already in nudge-unauthorized-handoff.sh (the Staff Engineer P1,
  # 2026-05-29). Paths never contain newlines, so line-delimited is safe; each
  # field is read with its own `IFS= read -r`, and an empty field is an empty
  # line (no `_` sentinel needed).
  PARSED=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
  d = json.loads(sys.stdin.read())
  ti = d.get("tool_input", {}) or {}
  for v in (ti.get("file_path", ""), d.get("transcript_path", ""), d.get("tool_name", "")):
    sys.stdout.write((v or "") + "\n")
except Exception:
  sys.stdout.write("\n\n\n")
' | tr -d '\r')
  { IFS= read -r FILE_PATH; IFS= read -r TRANSCRIPT_PATH; IFS= read -r TOOL_NAME; } <<< "$PARSED"
  # Strip CR consistently with the three-field block above — Windows text-mode
  # converts \n to \r\n even on sys.stdout.write. Per lessons.md (2026-05-17).
  NEW_STRING=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
  d = json.loads(sys.stdin.read()).get("tool_input", {})
  sys.stdout.write(d.get("new_string", d.get("content", "")) or "")
except Exception:
  pass
' | tr -d '\r')
  OLD_STRING=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
  d = json.loads(sys.stdin.read()).get("tool_input", {})
  sys.stdout.write(d.get("old_string", "") or "")
except Exception:
  pass
' | tr -d '\r')
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  # Without jq or python we cannot reliably extract multiline new_string/old_string.
  # Conservative default: assume Edits are pruning (pass through), Writes nudge.
  NEW_STRING=""
  OLD_STRING=""
  if [[ "$TOOL_NAME" == "Edit" ]]; then
    exit 0
  fi
fi

[[ -z "$FILE_PATH" ]] && exit 0
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "MultiEdit" ]] && exit 0
# MultiEdit doesn't expose a single new_string for entry-line counting; treat
# like Write (any MultiEdit to a queue file gets the nudge).
if [[ "$TOOL_NAME" == "MultiEdit" ]]; then
  TOOL_NAME="Write"
fi

FILE_PATH_NORM="${FILE_PATH//\\//}"

# Only fire on improvement-queue files (central + per-project both end in this).
case "$FILE_PATH_NORM" in
  *improvement-queue.md)
    ;;
  *)
    exit 0
    ;;
esac

# For Edit: only fire if the new_string introduces an entry line that the
# old_string didn't carry. Match the queue main-line schema "- YYYY-MM-DD".
# This lets pruning edits, recurrence bumps, and reformat passes through silently.
if [[ "$TOOL_NAME" == "Edit" ]]; then
  # Count entry lines on both sides; if new doesn't add any, skip (covers
  # pruning, reformat, recurrence-bump-only, and any edit that doesn't grow
  # the entry count).
  NEW_ENTRIES=$(printf '%s' "$NEW_STRING" | grep -cE '^- [0-9]{4}-[0-9]{2}-[0-9]{2} \|' 2>/dev/null || echo 0)
  OLD_ENTRIES=$(printf '%s' "$OLD_STRING" | grep -cE '^- [0-9]{4}-[0-9]{2}-[0-9]{2} \|' 2>/dev/null || echo 0)
  NEW_ENTRIES=$(printf '%s' "$NEW_ENTRIES" | tr -d '\r\n ')
  OLD_ENTRIES=$(printf '%s' "$OLD_ENTRIES" | tr -d '\r\n ')
  if [[ "${NEW_ENTRIES:-0}" -le "${OLD_ENTRIES:-0}" ]]; then
    exit 0
  fi
fi

# Skip when an authoring skill that owns queue maintenance is active. These
# surfaces have already passed the "should this be queued?" gate as part of
# their procedure.
#
# Read the tail into a variable and match via here-string — NOT `tail | grep -q`.
# Under `set -o pipefail`, `grep -q` matches early and closes the pipe, `tail`
# dies with SIGPIPE (141), and pipefail propagates 141 as the pipeline status, so
# the `if` evaluates FALSE *despite a match* and the nudge fires anyway. On a
# multi-MB transcript that false-negative breaks this suppression branch 100% of
# the time (same defect found in nudge-unauthorized-handoff.sh, 2026-05-30). The
# here-string runs `tail` standalone in command substitution (its SIGPIPE/exit
# swallowed by `|| true`) and feeds `grep` from the variable, so `tail`'s status
# can never reach the `if`.
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  RECENT_TAIL=$(tail -500 "$TRANSCRIPT_PATH" 2>/dev/null || true)
  if grep -qE '(^|[^a-z])/(learn-lessons|workweek-complete|workday-complete|distill|session-end|update-docs|bug-blitz|mise-en-place)([^a-z]|$)|coordinator:(learn-lessons|workweek-complete|workday-complete|distill|session-end|update-docs|bug-blitz|mise-en-place)|<command-name>(learn-lessons|workweek-complete|workday-complete|distill|session-end|update-docs|bug-blitz|mise-en-place)</command-name>' <<< "$RECENT_TAIL"; then
    exit 0
  fi
fi

# Build the friction message.
QUEUE_LABEL="improvement queue"
case "$FILE_PATH_NORM" in
  *coordinator-improvement-queue.md) QUEUE_LABEL="CENTRAL improvement queue (universal patterns)" ;;
  *) QUEUE_LABEL="per-project improvement queue" ;;
esac

TRIVIAL_HINT=""
if [[ "${TRIVIAL_REASON:-0}" == "1" ]]; then
  TRIVIAL_HINT=$(cat <<'EOT'

[hook] COORDINATOR_QUEUE_PUNT was set but the value was trivial ("1", "ok",
[hook] "yes", or under 12 chars). The override exists to force you to name
[hook] what you're punting and why — not to give you a one-keystroke bypass.
[hook] Re-set it with an actual reason, e.g.:
[hook]   COORDINATOR_QUEUE_PUNT="genuinely cross-cutting, fix needs separate plan"
EOT
)
fi

REASON=$(cat <<EOF
Hold on — you're about to append to the $QUEUE_LABEL.

The queue is for items that are (a) universal patterns worth promoting, or
(b) genuinely-not-this-session deferrals with an architectural reason. It is
NOT a laundromat for "I noticed a thing, moving on."

Before this write lands, answer the four questions out loud:

  1. CAN I FIX IT NOW?
     A quick dispatch is almost always faster than queueing + triage + a
     future session re-loading context. If the fix-locus is named and the
     scope is bounded, the queue is the wrong tool — dispatch an executor
     or do it inline.

  2. SHOULD I FLAG IT TO THE PM?
     If it's a real tradeoff, a product call, or something that changes
     user-visible behavior — that's a PM conversation, not a queue entry.
     Queueing it routes it to nobody.

  3. AM I BEING LAZY?
     Honestly. "Annoying to fix right now" is not an architectural reason.
     If the answer is "I could, but I'd rather not" — fix it.

  4. AM I DECIDING SCOPE?
     "Out of scope for this session" is sometimes a PM call dressed up as
     an EM call. If you're deferring something the PM might want done now,
     ask — don't queue around them.

If after those four questions you still believe queueing is right
(legitimate cases: cross-cutting universal pattern noticed mid-other-work,
genuinely needs its own plan, depends on something not yet built):

  Set COORDINATOR_QUEUE_PUNT="<one-sentence reason>" and re-run the write.

The override deliberately requires a typed reason — not because the hook
will read it, but because YOU have to read it. If writing the sentence
feels harder than just fixing the thing, that's the signal.

File: $FILE_PATH_NORM$TRIVIAL_HINT
EOF
)

# Form A deny: JSON to STDOUT + exit 0. This is a "block to nudge" — the
# COORDINATOR_QUEUE_PUNT override (above) is the escape hatch. The prior
# Form B (exit 1 + stderr) was silently swallowed, so neither the block nor
# the override had any effect. See docs/wiki/hook-best-practices.md
# § "PreToolUse deny: JSON output, not exit 2" and § "Friction-as-warning".
if command -v jq &>/dev/null; then
  jq -nc --arg reason "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
else
  REASON_JSON=$(printf '%s' "$REASON" | python -c 'import json,sys; sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null \
    || printf '"%s"' "$(printf '%s' "$REASON" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n')")
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$REASON_JSON"
fi
exit 0
