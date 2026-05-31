#!/bin/bash
# PreToolUse hook: Blocks subagent writes to archive/** outside the sanctioned
# archive/completed/YYYY-MM/<entry>.md per-entry fallback shape.
#
# Spec backlink: archive/specs/2026-05-27-cqcs-cluster1-delegate-constraint-adherence.md § E5 / § Structural Mechanism
#
# Problem: executors under wrap-up pressure repeatedly self-log completion into
# archive/ (recurred 2-of-4 dispatches) even when the dispatch brief says not to.
# Per-dispatch prose is insufficient — the baseline rule in agents/executor.md §
# Key Constraints is the calibration layer; this hook is the fail-closed safety-net
# layer (per tasks/lessons.md:81 "calibration alone is insufficient — the safety-net
# layer is what makes the system actually work").
#
# Fires on Write|Edit|MultiEdit|NotebookEdit when:
#   (1) the top-level `agent_id` field is present in the hook input (i.e. a subagent
#       is writing, not the top-level EM), AND
#   (2) the normalized file_path matches (^|/)archive/ (any path under archive/), AND
#   (3) the path is NOT the sanctioned archive/completed/YYYY-MM/<entry>.md per-entry
#       fallback shape (executor.md:277 mandates this write; it is NOT a violation).
#
# Allow conditions (pass through):
#   (1) No agent_id (top-level EM write) → always allow.
#   (2) Path not under archive/ → allow.
#   (3) Path IS the sanctioned archive/completed/YYYY-MM/<entry>.md per-entry fallback
#       shape → allow (P0-1 carve-out; mirrors block-completion-monolith-write.sh
#       sub-path discrimination at lines 87-95 of that hook).
#   (3b) Path IS archive/daily-summaries/YYYY-MM-DD.md → allow (daily-summary carve-out;
#        the /workday-complete Step 4b analyst + Step 4c Sonnet observer are dispatched to
#        write/append it — sanctioned, not a violation). Tightly scoped to the dated file.
#   (4) Override env COORDINATOR_OVERRIDE_SUBAGENT_ARCHIVE=1 → allow (rare-use; e.g.
#       an explicitly archive-authoring executor dispatch).
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (mirrors block-off-daily-branch.sh:262-277, NOT the monolith hook's
#    {"decision":"block"}→stderr→exit 1 shape which is documented as a non-blocking
#    failure mode in hook-best-practices.md:14-28).
#
# Override env vars named in deny message:
#   COORDINATOR_OVERRIDE_SUBAGENT_ARCHIVE=1  — this hook
#   COORDINATOR_OVERRIDE_COMPLETION_MONOLITH=1 — monolith hook (if path is that shape)
#
# Bug-backlog note (P0-2 / Conflict #2, out-of-scope to fix here):
#   block-completion-monolith-write.sh uses the {"decision":"block"}→stderr→exit 1
#   deny shape that hook-best-practices.md:14-28 documents as silently non-blocking.
#   EM should dogfood that hook and fix its deny mechanism if it does not block.
#
# Tripwires registry: docs/wiki/coordinator-tripwires.md

set -uo pipefail
# NOTE: -e deliberately omitted — deny hook must fail-open (allow) on unexpected error, never fail-closed.

# Safe stdin read — timeout prevents hang on Windows/Git-Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch first.
if [[ "${COORDINATOR_OVERRIDE_SUBAGENT_ARCHIVE:-0}" == "1" ]]; then
  exit 0
fi

# Tool-name guard — defense-in-depth against best-effort matcher.
# Mirrors block-completion-monolith-write.sh:54-57.
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
case "$TOOL_NAME" in
  Write|Edit|NotebookEdit|MultiEdit) : ;;
  *) exit 0 ;;
esac

# Extract agent_id (snake_case, top-level — subagent fires only).
# Documented at track-touched-files.sh:72-85: present on subagent fires only;
# absent on top-level EM fires. EM writes to archive/ are legitimate (e.g.
# /session-end, /distill, EM-serial commit sweeps); only subagent writes are
# the violation class this hook addresses.
# Format guard: lowercase hex, 12+ chars (Probe 0.1 captured 17-char hex).
AGENT_ID=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp_agent="${INPUT#*\"agent_id\":\"}"
  AGENT_ID="${_tmp_agent%%\"*}"
  if [[ ! "$AGENT_ID" =~ ^[a-f0-9]{12,}$ ]]; then
    AGENT_ID=""
  fi
fi
# Format-guard fail → AGENT_ID empty → allow (safe fail-open direction for a deny hook).

# No agent_id → top-level EM write → allow.
[[ -z "$AGENT_ID" ]] && exit 0

# Parse file_path. F14: NotebookEdit carries notebook_path (not file_path), so fall
# back to it when file_path is empty. MultiEdit DOES carry tool_input.file_path → already
# covered by the primary extraction.
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null || true)
else
  # F1: scope the sed extraction to the tool_input object — strip everything up to the
  # first "tool_input" occurrence so a file_path appearing earlier in tool_response/context
  # fields can't be picked up by the whole-payload scan.
  _after_ti="${INPUT#*\"tool_input\"}"
  FILE_PATH=$(echo "$_after_ti" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  if [[ -z "$FILE_PATH" ]]; then
    FILE_PATH=$(echo "$_after_ti" | sed -n 's/.*"notebook_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi
fi

[[ -z "$FILE_PATH" ]] && exit 0

# Normalize path: backslash → forward slash, collapse double-slashes.
# Mirrors block-completion-monolith-write.sh:78-81.
FILE_PATH_NORM="${FILE_PATH//\\//}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done

# Fast exit: path not under archive/ → allow.
if ! [[ "$FILE_PATH_NORM" =~ (^|/)archive/ ]]; then
  exit 0
fi

# P0-1 carve-out: the sanctioned archive/completed/YYYY-MM/<entry>.md per-entry
# fallback shape (executor.md:277 mandates this write; it is NOT a violation).
# Pattern: any path segment sequence ending in archive/completed/YYYY-MM/<file>.md
# where YYYY = 4 digits, MM = 2 digits, and <file> is any non-empty name ending .md.
# This is the per-entry form — NOT the monolith archive/completed/YYYY-MM.md (which
# has no intermediate path segment and is caught by the sibling monolith hook).
if [[ "$FILE_PATH_NORM" =~ (^|/)archive/completed/[0-9]{4}-[0-9]{2}/.+\.md$ ]]; then
  exit 0
fi

# Daily-summary carve-out: the /workday-complete Step 4b analyst and Step 4c Sonnet
# strategic observer are EXPLICITLY dispatched to write/append archive/daily-summaries/
# YYYY-MM-DD.md. That is a sanctioned subagent write path, exactly like the per-entry
# completion fallback above — without this carve-out the daily wrap requires a manual
# COORDINATOR_OVERRIDE_SUBAGENT_ARCHIVE=1 on every run (the fight-the-hook anti-pattern).
# Tightly scoped to the dated summary file only (YYYY-MM-DD.md) — a subagent writing any
# OTHER file under archive/daily-summaries/ is still blocked.
# Anchor note: the `(^|/)` prefix is REQUIRED, not `^` — hook `file_path` inputs are
# frequently ABSOLUTE (e.g. C:/Users/.../.claude/archive/daily-summaries/... or
# /c/.../archive/...). `^archive/` would fail to match those and wrongly DENY legitimate
# daily writes. The mid-path match this admits (e.g. tasks/archive/daily-summaries/...) is
# the accepted cost of absolute-path support and mirrors the per-entry carve-out + entry
# guard above; nothing legitimate writes that shape, and it is not the real archive/.
# Spec backlink: commands/workday-complete.md Step 4b/4c; docs/wiki/daily-summary-procedure.md.
if [[ "$FILE_PATH_NORM" =~ (^|/)archive/daily-summaries/[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$ ]]; then
  exit 0
fi

# Subagent writing under archive/ outside the sanctioned per-entry fallback → block.
# Determine if path also matches the monolith shape (double-block) so deny message
# can name both override vars.
EXTRA_OVERRIDE=""
if [[ "$FILE_PATH_NORM" =~ (^|/)archive/completed/[0-9]{4}-[0-9]{2}\.md$ ]]; then
  EXTRA_OVERRIDE=" OR COORDINATOR_OVERRIDE_COMPLETION_MONOLITH=1 (monolith-write override)"
fi

# Parse session_id for log (best-effort).
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Per-session log (best-effort).
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -n "$SESSION_ID" && -n "$GIT_ROOT" ]]; then
  LOG_DIR="$GIT_ROOT/.git/coordinator-sessions/$SESSION_ID"
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  echo "${TS} | DENY | agent_id=${AGENT_ID} | path=${FILE_PATH}" \
    >> "$LOG_DIR/archive-write-block.log" 2>/dev/null || true
fi

# Security hardening (security-audit note): strip/replace newline and other control
# chars from FILE_PATH before it is interpolated into the deny-JSON reason, so a
# pathological path can't break the JSON envelope. (AGENT_ID is already format-guarded to
# lowercase hex above.) The jq branch encodes safely on its own, but the sed/printf
# fallback only escapes backslash + quote + newline — a raw control char would still leak.
FILE_PATH_SAFE="${FILE_PATH//[$'\t\r\n\f\v']/ }"
# Collapse any remaining low control chars (0x00-0x1F) to a space.
FILE_PATH_SAFE=$(printf '%s' "$FILE_PATH_SAFE" | tr -d '\000-\010\013\014\016-\037')

# Emit deny using hookSpecificOutput.permissionDecision → stdout → exit 0.
# Mirrors block-off-daily-branch.sh:262-277.
REASON="BLOCKED: subagent write to archive/ outside the sanctioned fallback path."$'\n\n'
REASON+="  Subagent: ${AGENT_ID}"$'\n'
REASON+="  Target:   ${FILE_PATH_SAFE}"$'\n\n'
REASON+="Executors under wrap-up pressure repeatedly self-log completion into archive/;"$'\n'
REASON+="this hook is the fail-closed backstop for agents/executor.md § Key Constraints."$'\n\n'
REASON+="Sanctioned subagent writes under archive/ are:"$'\n'
REASON+="  1. archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md"$'\n'
REASON+="     (the per-entry completion fallback — ONLY when no tracker path was given), and"$'\n'
REASON+="  2. archive/daily-summaries/YYYY-MM-DD.md"$'\n'
REASON+="     (the /workday-complete Step 4b/4c daily summary)."$'\n\n'
REASON+="If this is the sanctioned fallback write, ensure the path matches:"$'\n'
REASON+="  archive/completed/<YYYY-MM>/<filename>.md  (per-entry, NOT the monolith root)"$'\n\n'
REASON+="Override (rare-use — read the hook source before invoking):"$'\n'
REASON+="  COORDINATOR_OVERRIDE_SUBAGENT_ARCHIVE=1${EXTRA_OVERRIDE}"

if command -v jq &>/dev/null; then
  jq -nc --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
else
  esc="${REASON//\\/\\\\}"
  esc="${esc//\"/\\\"}"
  esc="${esc//$'\n'/\\n}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
fi
exit 0
