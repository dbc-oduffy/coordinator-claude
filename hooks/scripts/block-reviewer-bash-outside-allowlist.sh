#!/usr/bin/env bash
# PreToolUse(Bash) hook: Confines findings-agent subagents to running
# ONLY the sidecar-scaffolder command (coordinator-doc-new --type review-findings).
#
# Spec backlink: docs/plans/2026-07-01-findings-agents-self-persist.md § D2 (bash-guard)
#
# Problem: confined findings-agent subagents are granted Bash access so they can
# scaffold their own findings sidecar via coordinator-doc-new. Without a guard,
# nothing prevents a findings-agent under context pressure from running arbitrary
# shell commands — violating read-only discipline.
#
# Design: effective type is resolved via an OR over two resolvers:
#   Primary:   agent_type (top-level payload field, present at Bash-call time for
#              UNNAMED/foreground dispatch — the back-pointer is absent for those)
#   Secondary: subagent_type via the dispatched-agents back-pointer chain
#              (covers NAMED/teammate dispatch where agent_type is the teammate name)
#   The confined set is the SSOT helper _cs_is_confined_findings_agent in lib/coordinator-session.sh.
# When the effective type is in the confined set, the command is checked against a strict allowlist:
#   - Must invoke coordinator-doc-new (optionally path-prefixed or via bash)
#   - Must include --type review-findings
#   - Must contain NO shell-chaining metacharacters (; && || | ` $( > < & newline)
# Everything else is denied, fail-closed, with a design-as-offers reason.
#
# Allow conditions (pass through):
#   (1) tool_name != Bash → exit 0 (defense-in-depth; matcher already filters)
#   (2) No agent_id in payload → top-level EM → exit 0
#   (3) agent_id present, both resolvers fail → fail-open (infra noise tradeoff;
#       preserves executor/enricher/integrator Bash freedom)
#   (4) effective type not in confined set → exit 0 (executors, enrichers, etc.)
#   (5) confined findings-agent + command is clean coordinator-doc-new --type review-findings → exit 0
#
# Deny conditions:
#   confined findings-agent + command is anything else → deny, fail-closed
#
# Confined findings-agent set: see _cs_is_confined_findings_agent in lib/coordinator-session.sh.
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (mirrors block-reviewer-write-outside-sidecar.sh; the {"decision":"block"}→stderr→exit 1
#    shape is documented as non-blocking in hook-best-practices.md)
#
# Tripwires registry: docs/wiki/coordinator-tripwires.md (REVIEWER-BASH-ALLOWLIST)

set -uo pipefail
# NOTE: -e deliberately omitted — deny hook must fail-open (allow) on unexpected error,
# never fail-closed. Non-zero exit from a subshell must not silently abort the guard
# and skip the deny path.

# ---------------------------------------------------------------------------
# Safe stdin read — timeout prevents hang on Windows/Git-Bash.
# Mirrors block-reviewer-write-outside-sidecar.sh:35-40.
# ---------------------------------------------------------------------------
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# ---------------------------------------------------------------------------
# 1. Tool-name guard — defense-in-depth against best-effort matcher.
#    Mirrors block-subagent-plan-body-write.sh:77-85.
# ---------------------------------------------------------------------------
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[[ "$TOOL_NAME" != "Bash" ]] && exit 0

# ---------------------------------------------------------------------------
# 2. No agent_id → top-level EM Bash call → allow.
#    The overwhelmingly common case exits here without paying lib-source cost.
# ---------------------------------------------------------------------------
[[ "$INPUT" != *'"agent_id"'* ]] && exit 0

# ---------------------------------------------------------------------------
# 3. Identity resolution via shared resolver.
#    Handles bare-hex (unnamed agents) and a<name>-<16hex> (named teammates).
#    Mirrors block-subagent-plan-body-write.sh:93-137.
# ---------------------------------------------------------------------------
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
if [[ ! -f "$LIB_PATH" ]]; then
  _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
  if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
    coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
  else
    _cc_root=''
  fi
  [ -d "$_cc_root" ] || _cc_root=""
  LIB_PATH="$_cc_root/lib/coordinator-session.sh"
fi
# shellcheck source=/dev/null
[[ -f "$LIB_PATH" ]] && source "$LIB_PATH"

_raw_agent_id=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp_agent="${INPUT#*\"agent_id\":\"}"
  _raw_agent_id="${_tmp_agent%%\"*}"
fi

_input_session_id=""
if command -v jq &>/dev/null; then
  _input_session_id=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  _input_session_id=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

AGENT_ID=""
if declare -f resolve_subagent_identity &>/dev/null; then
  AGENT_ID="$(resolve_subagent_identity "$_raw_agent_id" "$_input_session_id")"
elif [[ "$_raw_agent_id" =~ ^[a-f0-9]{12,}$ ]]; then
  AGENT_ID="$_raw_agent_id"
fi

# Empty AGENT_ID → no subagent or unrecognised shape → allow (fail-open).
[[ -z "$AGENT_ID" ]] && exit 0

# ---------------------------------------------------------------------------
# 4. Extract agent_type (PRIMARY resolver — top-level field, present at Bash-call
#    time for UNNAMED/foreground dispatch where the back-pointer is absent).
#    For NAMED/teammate dispatch: agent_type is the teammate NAME (not subagent_type).
#    Mirrors agent_id extraction above (jq primary, no-jq fallback).
# ---------------------------------------------------------------------------
AGENT_TYPE=""
if command -v jq &>/dev/null; then
  AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null || true)
elif [[ "$INPUT" == *'"agent_type"'* ]]; then
  # Field-present guard mirrors the agent_id extraction pattern (bash guard step 3).
  # Absent field → skip extraction entirely; AGENT_TYPE stays empty.
  _tmp_atype="${INPUT#*\"agent_type\":\"}"
  AGENT_TYPE="${_tmp_atype%%\"*}"
fi

# ---------------------------------------------------------------------------
# 5. Subagent-type lookup via back-pointer chain (SECONDARY resolver).
#    .git/coordinator-sessions/.agents/<AGENT_ID>/em-session-id.txt → em_sid
#    .git/coordinator-sessions/<em_sid>/dispatched-agents.txt → tab-delimited:
#      <agentId>\t<model>\t<subagent_type>\t<dispatched-at>
#    Fail-open on any lookup failure (infra noise tradeoff; same as plan-body-write).
#    Secondary resolver covers NAMED/teammate dispatch where agent_type is the name;
#    the back-pointer IS present for teammates (spawn Agent-call returned before Bash fires).
# ---------------------------------------------------------------------------
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)

SUBAGENT_TYPE=""
if [[ -n "$GIT_ROOT" ]]; then
  _backptr="$GIT_ROOT/.git/coordinator-sessions/.agents/$AGENT_ID/em-session-id.txt"
  if [[ -r "$_backptr" ]]; then
    _em_sid=$(head -1 "$_backptr" 2>/dev/null | tr -d '[:space:]')
    # Format guard: prevents path injection from a corrupted back-pointer.
    if [[ "$_em_sid" =~ ^[a-zA-Z0-9_-]{3,}$ ]]; then
      _dispatch_file="$GIT_ROOT/.git/coordinator-sessions/$_em_sid/dispatched-agents.txt"
      if [[ -r "$_dispatch_file" ]]; then
        # Column-exact awk match on field 1 — avoids tab-fragility of grep -F.
        SUBAGENT_TYPE=$(awk -F'\t' -v id="$AGENT_ID" '$1 == id {print $3; exit}' \
          "$_dispatch_file" 2>/dev/null || true)
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 6. OR-resolver: determine effective confined-set membership.
#    Primary:   agent_type → _cs_is_confined_findings_agent
#    Secondary: SUBAGENT_TYPE (back-pointer) → _cs_is_confined_findings_agent
#    Fail-open for non-confined agents (branch 4 of the 4-branch table):
#    executors/enrichers/integrators MUST keep their Bash freedom.
# ---------------------------------------------------------------------------
_is_confined_findings_agent() {
  if declare -f _cs_is_confined_findings_agent >/dev/null 2>&1; then
    _cs_is_confined_findings_agent "${1:-}"
  else
    # Lib failed to load — inline fallback (coordinator:code-reviewer ONLY).
    # Review personas were removed 2026-07-01; see lib/coordinator-session.sh for rationale.
    case "${1:-}" in
      coordinator:code-reviewer)
        return 0 ;;
      *) return 1 ;;
    esac
  fi
}

_is_confined=0
if _is_confined_findings_agent "$AGENT_TYPE"; then
  _is_confined=1
elif _is_confined_findings_agent "$SUBAGENT_TYPE"; then
  _is_confined=1
fi

# Not in confined set → exit 0 (executors, enrichers, integrators etc. are unconfined).
[[ "$_is_confined" -eq 0 ]] && exit 0

# Resolve the most informative type label for the deny message.
_EFFECTIVE_TYPE="$AGENT_TYPE"
_is_confined_findings_agent "$AGENT_TYPE" || _EFFECTIVE_TYPE="$SUBAGENT_TYPE"

# ---------------------------------------------------------------------------
# 7. Confined findings-agent confirmed. Extract and validate the command.
#    ALLOW iff ALL of:
#      (a) No shell-chaining metacharacters (; && || | ` $( > newline)
#      (b) First significant token is (path-prefixed) coordinator-doc-new
#      (c) Command contains --type review-findings
#    DENY on ANY ambiguity (unparseable / metacharacter / wrong token).
# ---------------------------------------------------------------------------
CMD=""
if command -v jq &>/dev/null; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  # Scope to tool_input — avoids 'command' fields elsewhere in the payload.
  # Mirrors preuse-bash-dispatch.sh:77 extraction shape.
  _after_ti="${INPUT#*\"tool_input\"}"
  CMD=$(echo "$_after_ti" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Strip CRLF artifacts — Windows/Git-Bash jq emits CR+LF in text mode.
CMD="${CMD//$'\r'/}"

_DENY=0
_DENY_REASON=""

# Empty command → can't validate → deny fail-closed.
if [[ -z "$CMD" ]]; then
  _DENY=1
  _DENY_REASON="command could not be parsed from the PreToolUse payload"
fi

# (a) Chaining metacharacter check.
# This is the security-critical gate — deny on ANY of: ; && || | ` $( > < & newline.
# NOTE: || checked as a substring (catches it as well as bare |; both are banned).
# Checking '|' alone subsumes '||', but explicit '||' makes intent unambiguous.
# & (bare background fork) and < (stdin redirect) are banned to close the full
# metacharacter surface even though neither enables arbitrary-command-execution via
# coordinator-doc-new alone — the guard's stated invariant is "no shell metacharacters".
# && is already covered by the '&&' check; adding '&' is OR logic, order irrelevant.
# Review: code-reviewer-selfpersist — F4 missing < and bare & from banned metacharacter set
if [[ "$_DENY" -eq 0 ]]; then
  if [[ "$CMD" == *';'*   || "$CMD" == *'&&'*  || "$CMD" == *'||'*  ||
        "$CMD" == *'|'*   || "$CMD" == *'`'*   || "$CMD" == *'$('*  ||
        "$CMD" == *'>'*   || "$CMD" == *'<'*   || "$CMD" == *'&'*   ||
        "$CMD" == *$'\n'* ]]; then
    _DENY=1
    _DENY_REASON="shell-chaining metacharacter detected (; && || | \` \$( > < & or newline)"
  fi
fi

# (b) First significant token must end with coordinator-doc-new.
#     Accepted leading forms:
#       coordinator-doc-new ...                (direct)
#       bin/coordinator-doc-new ...            (path-prefixed)
#       /abs/path/coordinator-doc-new ...      (absolute path)
#       bash /abs/path/coordinator-doc-new ... (via bash)
if [[ "$_DENY" -eq 0 ]]; then
  _check_cmd="$CMD"
  # Strip optional leading "bash " to expose the real binary path.
  if [[ "$_check_cmd" == bash\ * ]]; then
    _check_cmd="${_check_cmd#bash }"
    # Collapse any extra spaces after bash.
    while [[ "$_check_cmd" == ' '* ]]; do _check_cmd="${_check_cmd# }"; done
  fi
  # First token (up to first space, or whole string if no space).
  _first_token="${_check_cmd%% *}"
  # Token must end with /coordinator-doc-new or be exactly coordinator-doc-new.
  if [[ "$_first_token" != *coordinator-doc-new ]]; then
    _DENY=1
    _DENY_REASON="first command token is not coordinator-doc-new (got: ${_first_token:-empty})"
  fi
fi

# (c) --type review-findings must be present as a complete word (not a prefix of a longer type).
# Substring match *'--type review-findings'* would allow --type review-findingsXYZ.
# Word-boundary check: the type value must end at end-of-command or be followed by a space.
# Review: code-reviewer-selfpersist — F5 --type arg check is substring-only; tighten to word-boundary
if [[ "$_DENY" -eq 0 ]]; then
  if [[ "$CMD" != *'--type review-findings' && "$CMD" != *'--type review-findings '* ]]; then
    _DENY=1
    _DENY_REASON="missing required argument: --type review-findings (exact type value required)"
  fi
fi

# All checks passed → allow.
[[ "$_DENY" -eq 0 ]] && exit 0

# ---------------------------------------------------------------------------
# Deny — fail-closed with design-as-offers reason naming the one allowed form.
# ---------------------------------------------------------------------------

# Sanitize CMD for safe interpolation — strip control chars and truncate.
CMD_SAFE="${CMD//[$'\t\r\n\f\v']/ }"
CMD_SAFE=$(printf '%s' "$CMD_SAFE" | LC_ALL=C tr -d '\000-\037')
if [[ "${#CMD_SAFE}" -gt 200 ]]; then
  CMD_SAFE="${CMD_SAFE:0:200}..."
fi
[[ -z "$CMD_SAFE" ]] && CMD_SAFE="(empty/unparseable)"

REASON="BLOCKED: confined findings-agent Bash invocation outside the scaffolder allowlist."$'\n\n'
REASON+="  Subagent: ${AGENT_ID} (${_EFFECTIVE_TYPE})"$'\n'
REASON+="  Command:  ${CMD_SAFE}"$'\n'
[[ -n "$_DENY_REASON" ]] && REASON+="  Reason:   ${_DENY_REASON}"$'\n'
REASON+=$'\n'
REASON+="Confined findings-agent subagents are confined to exactly one Bash command —"$'\n'
REASON+="scaffolding their own findings sidecar:"$'\n\n'
REASON+="  coordinator-doc-new --type review-findings [--plan <path>] [--chunk <id>] ..."$'\n\n'
REASON+="Accepted invocation forms:"$'\n'
REASON+="  coordinator-doc-new --type review-findings ..."$'\n'
REASON+="  bin/coordinator-doc-new --type review-findings ..."$'\n'
REASON+="  /abs/path/to/coordinator-doc-new --type review-findings ..."$'\n'
REASON+="  bash /abs/path/to/coordinator-doc-new --type review-findings ..."$'\n\n'
REASON+="Denied: any other command, or any command containing shell-chaining"$'\n'
REASON+="  metacharacters (; && || | \` \$( > < & newline)."$'\n\n'
REASON+="This guard preserves read-only findings-agent discipline. Findings agents read"$'\n'
REASON+="code and write findings to their pre-scaffolded sidecar only — they do not"$'\n'
REASON+="run arbitrary shell commands."$'\n\n'
REASON+="If this findings agent legitimately needs to run another command, dispatch a"$'\n'
REASON+="separate non-confined executor for that step."

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
