#!/bin/bash
# PreToolUse hook: Blocks coordinator:executor Edit/Write to docs/plans/**/*.md
# plan bodies. Other subagents (review-integrator, enricher, prior-art-checker,
# plan-coverage-checker, named reviewers, etc.) are allowed — applying findings
# to plan bodies is their canonical job.
#
# Spec backlink: docs/plans/2026-06-09-executor-sidecar-flight-recorder.md § C3a
#
# Problem: executors under the Write-Ahead Status protocol repeatedly stamp
# "Execution in progress / complete" into the plan body — even when the dispatch
# brief says not to. The impulse is structural (agent prompt MUST wins over brief
# text ~67% of observed cases). The fix is structural: make the plan body immutable
# to executors and give them their own surface (the per-chunk sidecar at
# tasks/<plan-slug>/flight/<chunk-id>.md).
#
# Doctrine inversion (2026-06-09 second pass): the original carve-out shape was an
# allowlist of sidecar suffixes (.prior-art-check.md, .patrik-review.md, …). That
# requires maintenance every time a new review-pipeline agent ships, and the
# 2026-06-09 integrator block exposed the design flaw — review-integrator amends
# plan BODIES, not sidecars, so suffix-allowlist could never have covered it.
# Inverted to a single-item blocklist keyed on subagent_type = coordinator:executor.
# Everything else falls through to allow.
#
# Fires on Write|Edit|MultiEdit|NotebookEdit when:
#   (1) the top-level `agent_id` field is present (i.e. a subagent is writing), AND
#   (2) the normalized file_path matches (^|/)docs/plans/.+\.md$, AND
#   (3) the subagent_type (looked up via agent_id → em-session-id → dispatched-agents.txt)
#       is `coordinator:executor`, AND
#   (4) the path is NOT the executor's sanctioned flight sidecar
#       (^|/)tasks/[^/]+/flight/.+\.md$.
#
# NOTE: archive/specs/** is NOT a deny target — older plans live there and are not
# the immutability target. This hook guards docs/plans/ only.
#
# Allow conditions (pass through):
#   (1) No agent_id (top-level EM write) → always allow.
#   (2) Path not under docs/plans/ → allow.
#   (3) subagent_type lookup fails (missing back-pointer, unreadable file) → allow
#       (PM-directed 2026-06-09: don't punish legitimate integrator/enricher work
#       on infra noise; the executor edge case where back-pointer is lost is the
#       accepted tradeoff).
#   (4) subagent_type is anything other than `coordinator:executor` → allow.
#   (5) subagent_type IS `coordinator:executor` AND path matches the flight sidecar
#       shape tasks/<plan-slug>/flight/<chunk-id>.md → allow.
#   (6) Override env COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY=1 → allow (rare-use;
#       e.g. an explicitly plan-authoring executor dispatch).
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (mirrors block-off-daily-branch.sh:262-277, NOT the monolith hook's
#    {"decision":"block"}→stderr→exit 1 shape which is documented as a non-blocking
#    failure mode in hook-best-practices.md:14-28).
#
# Tripwires registry: docs/wiki/coordinator-tripwires.md (EXECUTOR-PLAN-BODY-IMMUTABLE)

set -uo pipefail
# NOTE: -e deliberately omitted — deny hook must fail-open (allow) on unexpected error, never fail-closed.

# Safe stdin read — timeout prevents hang on Windows/Git-Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch first.
if [[ "${COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY:-0}" == "1" ]]; then
  exit 0
fi

# Single git root resolution — used for both the subagent_type lookup and the
# per-session log below. One call avoids a race window between two separate
# git rev-parse invocations in the same hook run.
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)

# Tool-name guard — defense-in-depth against best-effort matcher.
# Mirrors block-subagent-archive-write.sh tool-guard shape.
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
# absent on top-level EM fires. EM writes to docs/plans/ are legitimate (e.g.
# plan authoring via coordinator:plan, dispatch ledger updates); only subagent
# writes are the violation class this hook addresses.
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

# Parse file_path. NotebookEdit carries notebook_path (not file_path); fall back to it
# when file_path is empty. MultiEdit uses file_path and is covered by the primary extraction.
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
# Mirrors block-subagent-archive-write.sh:113-118.
FILE_PATH_NORM="${FILE_PATH//\\//}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done

# Fast exit: path not under docs/plans/ → allow.
# Anchor note: the `(^|/)` prefix is REQUIRED, not `^docs/plans/` — hook `file_path`
# inputs are frequently ABSOLUTE (e.g. C:/Users/.../.claude/docs/plans/... or
# /c/.../docs/plans/...). `^docs/plans/` would fail to match those and wrongly ALLOW
# subagent plan-body writes that are the exact violation class this hook addresses.
# The mid-path match this admits (e.g. tasks/docs/plans/...) is the accepted cost of
# absolute-path support; nothing legitimate writes that shape.
# Mirrors block-subagent-archive-write.sh:142-147 anchor-note discipline.
if ! [[ "$FILE_PATH_NORM" =~ (^|/)docs/plans/.+\.md$ ]]; then
  exit 0
fi

# Subagent-type lookup via back-pointer chain (recorded by track-dispatched-agents.sh):
#   .git/coordinator-sessions/.agents/<AGENT_ID>/em-session-id.txt → em_sid
#   .git/coordinator-sessions/<em_sid>/dispatched-agents.txt → tab-delimited,
#     columns: <agentId>\t<model>\t<subagent_type>\t<dispatched-at>
#
# Lookup-fail semantics (PM-directed 2026-06-09): allow. The executor edge case
# where the back-pointer is missing is the accepted tradeoff for not blocking
# legitimate integrator/enricher/reviewer writes on infra noise.
SUBAGENT_TYPE=""
if [[ -n "$GIT_ROOT" ]]; then
  _backptr="$GIT_ROOT/.git/coordinator-sessions/.agents/$AGENT_ID/em-session-id.txt"
  if [[ -r "$_backptr" ]]; then
    _em_sid=$(head -1 "$_backptr" 2>/dev/null | tr -d '[:space:]')
    # Format guard: back-pointer content must match UUID-style or test-fixture session ids.
    # Prevents path injection if a corrupted back-pointer contains traversal sequences.
    if [[ ! "$_em_sid" =~ ^[a-zA-Z0-9_-]{3,}$ ]]; then
      _em_sid=""
    fi
    if [[ -n "$_em_sid" ]]; then
      _dispatch_file="$GIT_ROOT/.git/coordinator-sessions/$_em_sid/dispatched-agents.txt"
      if [[ -r "$_dispatch_file" ]]; then
        # Column-exact awk match on field 1 — avoids invisible-tab fragility of grep -F
        # and eliminates false matches on shared-prefix agent ids.
        SUBAGENT_TYPE=$(awk -F'\t' -v id="$AGENT_ID" '$1 == id {print $3; exit}' "$_dispatch_file" 2>/dev/null)
      fi
    fi
  fi
fi

# Allow anything that is NOT coordinator:executor (including lookup failure).
if [[ "$SUBAGENT_TYPE" != "coordinator:executor" ]]; then
  exit 0
fi

# Executor confirmed. Flight sidecar carve-out — executor's sanctioned write surface.
# Scoped here (after lookup) so it only fires for coordinator:executor, not all subagents.
#
# Carve-out for paths that contain BOTH `/docs/plans/` (matched above, preventing early
# exit) AND `/tasks/.../flight/` — this hybrid shape occurs with absolute paths like
# `/home/user/docs/plans/tasks/<plan-slug>/flight/<chunk>.md`. Relative
# `tasks/.../flight/...` paths already exited at the docs/plans fast-exit above, so
# this guard exclusively covers the absolute-path edge case.
#
# Anchor note: same `(^|/)` anchor for absolute-path safety, mirroring the pattern above.
# <chunk-id> is a single filename component — `[^/]+` enforces that; no arbitrary depth.
if [[ "$FILE_PATH_NORM" =~ (^|/)tasks/[^/]+/flight/[^/]+\.md$ ]]; then
  exit 0
fi

# Executor confirmed — flight sidecar carve-out did not apply. Anything else under
# docs/plans/ → block.

# Parse session_id for log (best-effort).
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Per-session log (best-effort). GIT_ROOT already resolved near top of script.
if [[ -n "$SESSION_ID" && -n "$GIT_ROOT" ]]; then
  LOG_DIR="$GIT_ROOT/.git/coordinator-sessions/$SESSION_ID"
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  echo "${TS} | DENY | agent_id=${AGENT_ID} | path=${FILE_PATH}" \
    >> "$LOG_DIR/plan-body-write-block.log" 2>/dev/null || true
fi

# Security hardening: strip/replace newline and other control chars from FILE_PATH
# before it is interpolated into the deny-JSON reason, so a pathological path can't
# break the JSON envelope. (AGENT_ID is already format-guarded to lowercase hex above.)
# Mirrors block-subagent-archive-write.sh:183-185.
FILE_PATH_SAFE="${FILE_PATH//[$'\t\r\n\f\v']/ }"
# Collapse any remaining low control chars (0x00-0x1F) to a space. LC_ALL=C ensures
# BSD tr interprets the octal range consistently across locales.
FILE_PATH_SAFE=$(printf '%s' "$FILE_PATH_SAFE" | LC_ALL=C tr -d '\000-\037')

# Emit deny using hookSpecificOutput.permissionDecision → stdout → exit 0.
# Mirrors block-subagent-archive-write.sh:204-217.
REASON="BLOCKED: coordinator:executor subagent write to plan body."$'\n\n'
REASON+="  Subagent: ${AGENT_ID} (coordinator:executor)"$'\n'
REASON+="  Target:   ${FILE_PATH_SAFE}"$'\n\n'
REASON+="The executor's sanctioned write surface for execution state is the per-chunk"$'\n'
REASON+="flight-recorder sidecar — NOT the plan body (which is EM- and integrator-owned)."$'\n\n'
REASON+="Sanctioned executor surface:"$'\n'
REASON+="  tasks/<plan-slug>/flight/<chunk-id>.md  (per-chunk sidecar)"$'\n\n'
REASON+="Derive <plan-slug> from the plan filename without YYYY-MM-DD- prefix and .md suffix."$'\n'
REASON+="Derive <chunk-id> from the dispatch brief's chunk-id field."$'\n\n'
REASON+="(Other subagents — review-integrator, enricher, reviewers — write plan bodies freely;"$'\n'
REASON+="this hook only fires when subagent_type is coordinator:executor.)"$'\n\n'
REASON+="Override (rare-use — read the hook source before invoking):"$'\n'
REASON+="  COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY=1"

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
  esc="${esc//$'\r'/\\r}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
fi
exit 0
