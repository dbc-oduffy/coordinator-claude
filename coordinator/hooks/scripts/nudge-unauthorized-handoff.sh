#!/bin/bash
# PostToolUse hook: when a new file is Written into state/handoffs/ or
# tasks/spinoffs/ WITHOUT an authoring skill active, surface an offer-shaped
# nudge — without blocking the write.
#
# Why PostToolUse + exit 2 (not PreToolUse deny):
#   The predecessor `block-unauthorized-handoff.sh` was a PreToolUse Form-A
#   JSON deny. It detected "skill active" by scraping the transcript for
#   <command-name> tags and /spinoff strings — a brittle proxy that twice
#   false-blocked a PM-authorized /spinoff (2026-05-28): the Skill tool emits
#   no <command-name>, and 100KB+ tool outputs buried the invocation past the
#   grep window. A *block* gated on an unreliable signal fails CLOSED — it
#   denies authorized work and trains the EM to reflexively reach for the
#   override. That is the mistrust-shape anti-pattern (design-as-offers).
#
#   The fix is not a more reliable signal — it is a cheaper CONSEQUENCE of an
#   unreliable one. The same best-effort scrape, used to SUPPRESS a
#   non-blocking nudge instead of to GATE a block, fails OPEN: at worst the EM
#   reads one extra line ("if deliberate, proceed") and proceeds. False
#   positive cost collapses from "blocks authorized work" to "one acknowled-
#   gement." That is the design-as-offers altitude the original missed.
#
#   Platform contract (docs/wiki/hook-best-practices.md § Friction-as-warning,
#   claude-code-platform-gotchas.md § PreToolUse deny):
#     - PreToolUse exit 2  -> BLOCKS the call (wrong altitude for a warn).
#     - exit 0 + stderr    -> goes to the user terminal, never the model.
#     - PostToolUse exit 2 -> tool already ran (cannot block); stderr is fed
#                             into the model's next turn. This is the ONLY
#                             warn-reaches-the-model-without-blocking channel.
#
# Fires on: PostToolUse Write where file_path is a NEW-ish file under
#   state/handoffs/ or tasks/spinoffs/. (The matcher is Write-only; /pickup
#   mutates existing handoffs via Edit, so it never reaches here.)
#
# Suppressed (silent exit 0 — no nudge):
#   - COORDINATOR_HANDOFF_NUDGE_OFF=1 in env (autonomous runs where the nudge
#     is noise the EM cannot act on interactively).
#   - The written file's frontmatter carries `kind: recovery` — a documented
#     legitimate direct write; suppressed via a FIRST-CLASS signal (the
#     artifact's own content), not the proxy scrape.
#   - Transcript shows an active authoring skill: /handoff, /workstream-complete,
#     /spinoff (best-effort scrape; failure is harmless — see header).
#   - Path is outside state/handoffs/ and tasks/spinoffs/.
#
# Nudged (exit 2 + stderr): any other new-file Write into those dirs. The
# message leads with the better alternative and explicitly says "if deliberate,
# proceed" — it never demands an override, because it never blocks.
#
# This hook has NO blocking override because it never blocks. The silence env
# var only quiets the nudge; it is not an authorization gate.

set -uo pipefail

# Silence switch for autonomous mode — the nudge targets an interactive EM.
if [[ "${COORDINATOR_HANDOFF_NUDGE_OFF:-0}" == "1" ]]; then
  exit 0
fi

# Safe stdin read — timeout prevents hang on Windows/Git Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Parse fields — prefer jq, fall back to python, then sed. CONTENT is the
# about-to-be-written body (Write.tool_input.content) — used only to read the
# leading frontmatter so a legitimate `kind: recovery` direct-write is suppressed.
CONTENT=""
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null | head -20 || true)
elif command -v python &>/dev/null || command -v python3 &>/dev/null; then
  PY=$(command -v python || command -v python3)
  # Field-per-line (NOT space-joined) — file_path/transcript_path can contain
  # spaces, which `read VAR1 VAR2 VAR3` would split across the wrong vars and
  # silently mis-route (the Staff Engineer P1, 2026-05-29). Paths never contain newlines,
  # so line-delimited is safe; read each field with its own `read -r`.
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
  CONTENT=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
  d = json.loads(sys.stdin.read())
  sys.stdout.write((d.get("tool_input", {}).get("content", "") or "")[:2000])
except Exception:
  pass
' | tr -d '\r' | head -20)
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  # CONTENT left empty in the sed path — frontmatter is multiline and not
  # reliably extractable without a JSON parser; recovery-suppression simply
  # doesn't fire here (fail-open: the EM gets a harmless nudge to proceed past).
fi

# Only Write creates files. (Matcher is Write-only; this is belt-and-braces.)
[[ "$TOOL_NAME" != "Write" ]] && exit 0
[[ -z "$FILE_PATH" ]] && exit 0

FILE_PATH_NORM="${FILE_PATH//\\//}"

# Only fire on state/handoffs/ and tasks/spinoffs/ paths.
case "$FILE_PATH_NORM" in
  */state/handoffs/*|*/tasks/spinoffs/*|state/handoffs/*|tasks/spinoffs/*)
    ;;
  *)
    exit 0
    ;;
esac

# First-class suppression: a recovery handoff (`kind: recovery`) is a documented
# legitimate DIRECT write (coordinator/CLAUDE.md § Handoff Lineage — "Concurrent
# crashed threads get separate handoffs"). Unlike the transcript-scrape below,
# this reads the artifact's OWN frontmatter — a reliable positive signal, not a
# proxy — so a recurring legitimate case doesn't desensitize the EM to the nudge
# (the Staff Engineer P2, 2026-05-29). Match `kind: recovery` in the leading frontmatter.
if printf '%s' "$CONTENT" | grep -qE '^kind:[[:space:]]*recovery[[:space:]]*$'; then
  exit 0
fi

# First-class suppression: an install-leg spinoff (`kind: spinoff` carrying
# `install_chain_order:`) is the one sanctioned non-/spinoff direct write — the
# operator authorized it at the install's pre-restart question (docs/wiki/
# spinoff-handoffs.md § Install-leg spinoffs; agent-install-contract.md §
# Install-spinoff layer). The install path seeds via `cp` (not the Write tool), so
# this hook already short-circuits at the Write check above; this guard is
# defense-in-depth for any future seed that does go through Write. Same
# OWN-frontmatter positive-signal basis as the recovery suppression, so it does not
# desensitize the EM to the steady-state nudge.
if printf '%s' "$CONTENT" | grep -qE '^kind:[[:space:]]*spinoff[[:space:]]*$' \
   && printf '%s' "$CONTENT" | grep -qE '^install_chain_order:[[:space:]]*[0-9]'; then
  exit 0
fi

# Best-effort: suppress the nudge when an authoring skill is active. This is a
# NOISE-REDUCER, not a gate — if it misses (Skill-tool invocation, buried past
# the window), the only cost is one extra nudge the EM reads and proceeds past.
# That fail-open posture is the whole point of the rework; do NOT "harden" this
# into a gate.
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  # (1) Most-recent <command-name> in the whole transcript is the active skill.
  # Safe direction: grep is the PRODUCER, tail the CONSUMER — tail -1 reads until
  # grep closes its write end, so grep never takes SIGPIPE. This is NOT the
  # `tail | grep -q` trap fixed in check (2); leaving it as a pipeline is correct.
  LAST_CMD=$(grep -oE '<command-name>[^<]*</command-name>' "$TRANSCRIPT_PATH" 2>/dev/null | tail -1)
  if echo "$LAST_CMD" | grep -qE '<command-name>/?(coordinator:)?(handoff|workstream-complete|spinoff)</command-name>'; then
    exit 0
  fi
  # (2) Generous-tail fallback for user-typed slash and Skill-tool invocations.
  # Read the tail into a variable and match via here-string — NOT `tail | grep -q`.
  # On a multi-MB transcript `grep -q` matches early and closes the pipe; `tail`
  # then dies with SIGPIPE (141), and `set -o pipefail` propagates that 141 as the
  # pipeline status, so the `if` evaluates FALSE *despite a match* and the nudge
  # fires anyway. That false-negative silently broke this entire suppression branch
  # on every real-sized session — the Skill-tool case (no <command-name> for check
  # (1) to catch) was nudged 100% of the time (repro 2026-05-30 d62f8fff: a
  # legitimate Skill(coordinator:handoff) on a 1.4MB transcript). A here-string
  # keeps `tail` out of the pipeline, so its exit status can't poison the `if`.
  #
  # Regex note: a Skill-tool invocation in the JSON transcript is `"name":"Skill",
  # "input":{"skill":"coordinator:handoff"}` — it is caught by the `coordinator:`
  # alternative (preceded by `"`, a `[^a-z:/]`), NOT by the `Skill\(...\)` branch.
  # The `Skill\(...\)` branch matches only a literal `Skill(coordinator:handoff)`
  # in prose/tool-output; kept as a cheap belt-and-braces, not the primary catch.
  RECENT_TAIL=$(tail -2000 "$TRANSCRIPT_PATH" 2>/dev/null || true)
  if grep -qE '(^|[^a-z])/(coordinator:)?(handoff|workstream-complete|spinoff)([^a-z]|$)|(^|[^a-z:/])coordinator:(handoff|workstream-complete|spinoff)([^a-z]|$)|Skill\((coordinator:)?(handoff|workstream-complete|spinoff)\)' <<< "$RECENT_TAIL"; then
    exit 0
  fi
fi

# No authoring skill detected — emit the offer-shaped nudge. exit 2 feeds this
# to the model's next turn WITHOUT blocking (the file is already on disk).
cat >&2 <<EOF
[nudge] You just created a file under $(dirname "$FILE_PATH_NORM")/ directly —
[nudge] no /handoff, /workstream-complete, or /spinoff was active. This is a nudge, not
[nudge] a block: the file is written and you may proceed if this was deliberate.
[nudge]
[nudge] If you reached for this because the work feels "done" or "tidy here":
[nudge]   handoffs are NOT tidy stopping points — /handoff passes an IN-FLIGHT
[nudge]   workstream. A DONE workstream is capped by /workstream-complete (or commit and
[nudge]   stop, or /workday-complete). (coordinator/CLAUDE.md § Handoff Lineage —
[nudge]   "/handoff and /workstream-complete are mutually exclusive.")
[nudge]
[nudge] If you are messaging another repo's EM:
[nudge]   use the cross-repo-memo CLI (writes into <receiver>/cross-repo/ and
[nudge]   prints a path for PM relay) — do NOT seed state/handoffs/ as a queue
[nudge]   for another repo. (coordinator/CLAUDE.md § Cross-repo writes.)
[nudge]
[nudge] If you genuinely mean to hand off or fork a topic:
[nudge]   /handoff and /spinoff carry the PM gate (spinoffs are PM-authorized).
[nudge]   Invoking the skill is the doctrine-correct path; a direct write skips
[nudge]   the Step-0 gate. (skills/spinoff Step 0, skills/handoff Step 0.)
[nudge]
[nudge] If this write was correct as-is (recovery handoff, /pickup rewrite,
[nudge] review-marker), ignore this — nothing is blocked.
[nudge]
[nudge] Silence in autonomous runs: COORDINATOR_HANDOFF_NUDGE_OFF=1.
EOF
exit 2
