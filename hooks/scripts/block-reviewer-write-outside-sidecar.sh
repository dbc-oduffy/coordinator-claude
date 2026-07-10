#!/usr/bin/env bash
# PreToolUse hook: Confines findings-agent subagents to their allowed write surfaces.
#
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
#
# Problem: a self-persisting findings-agent subagent must write its findings to exactly one
# self-scaffolded sidecar under state/review-trail/findings/.  Without a guard, nothing
# stops it from writing arbitrary paths under context pressure, composing richer responses,
# or mishandling a stale prompt that names a different path.
#
# Confinement mechanism — OR-resolver, fail-closed within the confined set:
#   Effective type is determined via an OR over TWO resolvers (neither alone is sufficient):
#     Primary:   agent_type field (top-level in payload, present at write-time for UNNAMED/foreground)
#     Secondary: back-pointer-resolved subagent_type (covers NAMED/teammate dispatch where
#                agent_type is the teammate name, NOT the subagent_type)
#   An agent is in the confined set iff:
#     _cs_is_confined_findings_agent(agent_type) OR _cs_is_confined_findings_agent(SUBAGENT_TYPE)
#   NEVER short-circuit to ALLOW on agent_type alone — in-set agents must still pass the
#   target-path check.
#
# Mode A — type-keyed directory prefix (the sole confinement mechanism):
#   Agents whose effective type is in the confined findings-agent SET
#   (see _cs_is_confined_findings_agent in lib/coordinator-session.sh)
#   are confined to state/review-trail/findings/ by type alone.  The agent
#   self-scaffolds its sidecar under that directory via coordinator-doc-new and
#   returns the path; no EM-written marker is needed.
#
# Branch table (OR-resolver):
#   1. effective type ∈ SET AND target under state/review-trail/findings/ → ALLOW
#   2. effective type ∈ SET AND target NOT under state/review-trail/findings/ → DENY
#   3. agent_type not in SET → consult back-pointer; if resolves to SET → apply branches 1/2
#   4. agent_type absent/unreadable → consult back-pointer; if resolves to SET → apply branches 1/2;
#      else → ALLOW (fail-open; preserves executor/enricher/integrator write freedom)
#
# Allow conditions (pass through):
#   (1) tool_name not in {Write, Edit, MultiEdit} → allow (non-intercepted tool).
#   (2) No top-level agent_id in payload → allow (top-level EM write).
#   (3) agent_id present, FILE_PATH unparseable → allow (fail-open on parse error).
#   (4) effective type ∈ confined set AND target is under state/review-trail/findings/ → allow.
#   (5) agent_id present, effective type NOT in confined set →
#       allow (unconfined non-findings-agent subagent).
#
# Deny conditions (fail-closed):
#   (4-deny) effective type ∈ confined set AND target NOT under state/review-trail/findings/.
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (mirrors block-subagent-archive-write.sh; the {"decision":"block"}→stderr→exit 1
#    shape is documented as non-blocking in hook-best-practices.md.)

set -uo pipefail

# Safe stdin read — timeout prevents hang on Windows/Git-Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# Tool-name guard — only intercept Write/Edit/MultiEdit.
# Mirrors block-subagent-archive-write.sh:59-67.
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
case "$TOOL_NAME" in
  # MultiEdit carries a single top-level tool_input.file_path (one file, many edits) —
  # same extraction path as Edit; verified by the unit suite's MultiEdit cases.
  Write|Edit|MultiEdit) : ;;
  *) exit 0 ;;
esac

# No agent_id → top-level EM write → allow, before paying any lib-source cost.
# The overwhelmingly common case (EM edits) exits here without sourcing the lib.
[[ "$INPUT" != *'"agent_id"'* ]] && exit 0

# Source the shared format predicate (CS_CANONICAL_AGENT_ID_RE + _cs_canonical_agent_id_format_ok).
# Keeps the agent_id format check as a single source of truth in lib/coordinator-session.sh.
# Same source pattern as block-subagent-plan-body-write.sh:97-100.
_GUARD_LIB="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
if [[ ! -f "$_GUARD_LIB" ]]; then
  _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
  if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
    coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
  else
    _cc_root=''
  fi
  [ -d "$_cc_root" ] || _cc_root=""
  _GUARD_LIB="$_cc_root/lib/coordinator-session.sh"
fi
# shellcheck source=/dev/null
[[ -f "$_GUARD_LIB" ]] && source "$_GUARD_LIB"

# Extract agent_id using the same resolve_subagent_identity approach as
# block-reviewer-bash-outside-allowlist.sh (its steps 3–4).  Handles both
# bare-hex unnamed agents AND aNAME-<16hex> named teammates.
#
# Negative-spec: the old _cs_canonical_agent_id_format_ok check only accepted
# ^[a-f0-9]{12,}$ — named dispatch agent_ids (aNAME-<16hex>) failed the format
# guard, clearing AGENT_ID → early exit 0 → ALLOW before agent_type or back-pointer
# lookup was reached.  That was the D3 P0.2 gap (Case 3).  Fixed by mirroring the
# bash guard's resolve_subagent_identity call, which accepts both forms.
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
  # When resolve returns "" for a named form that had no session_id in the payload,
  # fall back to the raw id — the back-pointer dir is keyed on the raw aNAME-<16hex>
  # form when session_id is absent.  Pattern mirrors resolve_subagent_identity path (b).
  if [[ -z "$AGENT_ID" && "$_raw_agent_id" =~ ^a.+-[a-f0-9]{16}$ ]]; then
    AGENT_ID="$_raw_agent_id"
  fi
elif [[ "$_raw_agent_id" =~ ^[a-f0-9]{12,}$ ]]; then
  # Lib not loaded — inline bare-hex fallback (mirrors bash guard's elif).
  AGENT_ID="$_raw_agent_id"
fi
# No recognizable agent id → treat as EM write → allow (fail-open).
[[ -z "$AGENT_ID" ]] && exit 0

# Resolve git root — needed for back-pointer lookup, marker lookup, and path normalization.
# Primary: _cs_git_root (same helper used by cs_write_review_claim, so guard and
# marker-writer agree on the root). Falls back to git rev-parse --show-toplevel.
GIT_ROOT=""
if declare -f _cs_git_root >/dev/null 2>&1; then
  GIT_ROOT=$(_cs_git_root 2>/dev/null || true)
fi
[[ -z "$GIT_ROOT" ]] && GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$GIT_ROOT" ]]; then
  # Deliberate fail-open: without a repo root the guard cannot locate the marker to
  # determine whether the agent is even confined. Failing closed here would over-block
  # every unmarked non-reviewer subagent. The window is minimised by the dual resolver
  # above; fail-open is the lesser evil only as a last resort.
  exit 0
fi

# ---------------------------------------------------------------------------
# Extract agent_type (top-level field, distinct from agent_id).
# For UNNAMED dispatch: agent_type = the subagent_type (e.g. coordinator:code-reviewer).
# For NAMED/teammate dispatch: agent_type = the teammate name (e.g. ProbeGP) — NOT the
# subagent_type. The OR-resolver handles this: primary leg checks agent_type; secondary
# leg checks the back-pointer-resolved subagent_type so named-dispatch confined agents
# are caught via the back-pointer (which IS present for teammates, since the spawn
# Agent-call has already returned when the subagent's Edit fires).
# Extraction mirrors agent_id extraction above (jq primary, no-jq fallback).
# ---------------------------------------------------------------------------
AGENT_TYPE=""
if command -v jq &>/dev/null; then
  AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null || true)
elif [[ "$INPUT" == *'"agent_type"'* ]]; then
  # Field-present guard mirrors the agent_id extraction pattern above.
  # Absent field → skip extraction entirely; AGENT_TYPE stays empty.
  _tmp_atype="${INPUT#*\"agent_type\":\"}"
  AGENT_TYPE="${_tmp_atype%%\"*}"
fi

# ---------------------------------------------------------------------------
# Subagent-type lookup via back-pointer chain (SECONDARY resolver).
# Mirrors block-subagent-plan-body-write.sh:183-202.
# Used as the secondary leg of the OR-resolver — covers NAMED/teammate dispatch
# where agent_type is the teammate name, not the subagent_type.
# Back-pointer IS present for teammates (the spawn Agent-call returned before the
# subagent's Edit fires). Lookup-fail → SUBAGENT_TYPE="" → secondary leg is absent;
# only primary (agent_type) contributes.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# OR-resolver: determine whether this agent is in the confined findings-agent set.
# Uses _cs_is_confined_findings_agent from lib/coordinator-session.sh (sourced above).
# Primary leg:   agent_type (write-time-present, covers UNNAMED foreground dispatch)
# Secondary leg: SUBAGENT_TYPE (back-pointer, covers NAMED/teammate dispatch)
# Fail-closed within the set; fail-open for non-confined agents.
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

# Resolve effective in-set membership via the OR.
IN_CONFINED_SET=0
if _is_confined_findings_agent "$AGENT_TYPE"; then
  IN_CONFINED_SET=1
elif _is_confined_findings_agent "$SUBAGENT_TYPE"; then
  IN_CONFINED_SET=1
fi

# ---------------------------------------------------------------------------
# Extract and normalize file_path.
# Hoisted before the marker check so both Mode A (selfpersist) and Mode B
# (marker-keyed) share a single normalization pass.
# ---------------------------------------------------------------------------
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  # Scope the extraction to tool_input to avoid picking up earlier file_path fields.
  # Mirrors block-subagent-archive-write.sh:94-101.
  _after_ti="${INPUT#*\"tool_input\"}"
  FILE_PATH=$(echo "$_after_ti" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# No file_path → can't determine target → fail-open on parse error.
[[ -z "$FILE_PATH" ]] && exit 0

# Normalize path: backslash → forward slash, collapse double-slashes.
# Mirrors block-subagent-archive-write.sh:107-110 and block-consumed-handoff-edit.sh:80-83.
# Leading // (Windows UNC paths e.g. //server/share) is preserved by stripping it
# before the collapse loop and re-prepending afterward.
FILE_PATH_NORM="${FILE_PATH//\\//}"
_fp_unc_prefix=""
[[ "$FILE_PATH_NORM" == //* ]] && _fp_unc_prefix="//" && FILE_PATH_NORM="${FILE_PATH_NORM:2}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done
FILE_PATH_NORM="${_fp_unc_prefix}${FILE_PATH_NORM}"

# Convert absolute path to repo-relative.
# Strategy mirrors cs_touch (lib/coordinator-session.sh ~495-524):
#   1. Try git ls-files --full-name (works for tracked/staged files).
#   2. Fall back to prefix strip against GIT_ROOT (for untracked files).
#
# Windows/Git-Bash caveat: mktemp returns POSIX paths (/tmp/...) while
# git rev-parse --show-toplevel returns Windows forward-slash paths
# (C:/Users/.../AppData/Local/Temp/...). Normalize the incoming path to
# Windows format via cygpath before prefix-stripping so the comparison works.
if [[ "$FILE_PATH_NORM" == /* || "$FILE_PATH_NORM" == [A-Za-z]:* ]]; then
  REL=$(git ls-files --full-name -- "$FILE_PATH_NORM" 2>/dev/null | head -1)
  if [[ -z "$REL" ]]; then
    # Untracked file: strip GIT_ROOT prefix.
    # Preserve leading // (UNC paths) before collapsing internal double-slashes.
    GIT_ROOT_NORM="${GIT_ROOT//\\//}"
    _gr_unc_prefix=""
    [[ "$GIT_ROOT_NORM" == //* ]] && _gr_unc_prefix="//" && GIT_ROOT_NORM="${GIT_ROOT_NORM:2}"
    while [[ "$GIT_ROOT_NORM" == *//* ]]; do
      GIT_ROOT_NORM="${GIT_ROOT_NORM//\/\///}"
    done
    GIT_ROOT_NORM="${_gr_unc_prefix}${GIT_ROOT_NORM}"
    # On Windows/Git-Bash, POSIX paths from mktemp differ from Windows paths
    # returned by git. Convert via cygpath when available to unify the format.
    if command -v cygpath &>/dev/null; then
      _cyg=$(cygpath -m "$FILE_PATH_NORM" 2>/dev/null || true)
      [[ -n "$_cyg" ]] && FILE_PATH_NORM="$_cyg"
    fi
    if [[ "$FILE_PATH_NORM" == "$GIT_ROOT_NORM/"* ]]; then
      REL="${FILE_PATH_NORM#"$GIT_ROOT_NORM/"}"
    else
      # Path outside repo or normalization failed — keep as-is; compare will fail-closed.
      REL="$FILE_PATH_NORM"
    fi
  fi
  FILE_PATH_NORM="$REL"
fi

# ---------------------------------------------------------------------------
# Path-traversal rejection — deny .. as a path component (fail-closed).
# Normalization above collapses // and backslashes but does NOT resolve ..
# components. A path like state/review-trail/findings/../../../hooks/scripts/evil.sh
# would match the Mode A prefix regex while resolving outside the allowed directory.
# This check fires BEFORE both Mode A and Mode B comparisons so neither branch
# can be bypassed via traversal.
# Review: code-reviewer-selfpersist — F1 path-traversal bypass in Mode A prefix check
# ---------------------------------------------------------------------------
if [[ "$FILE_PATH_NORM" =~ (^|/)\.\.(\/|$) ]]; then
  # .. as a full path component detected (matches leading ../, embedded /../,
  # or a bare/trailing ..). Does NOT match foo..bar.md (the .. there is not
  # preceded by / or ^ and not followed by / or $).
  FILE_PATH_SAFE="${FILE_PATH//[$'\t\r\n\f\v']/ }"
  FILE_PATH_SAFE=$(printf '%s' "$FILE_PATH_SAFE" | tr -d '\000-\037')
  REASON="BLOCKED: path contains a '..' component — write denied (path-traversal protection)."$'\n\n'
  REASON+="  Subagent agent_id: ${AGENT_ID}"$'\n'
  REASON+="  Attempted target:  ${FILE_PATH_SAFE}"$'\n\n'
  REASON+="Path traversal via '..' is not permitted. Use the canonical path returned by"$'\n'
  REASON+="your coordinator-doc-new scaffold call (or the SIDECAR_PATH in your dispatch brief)."
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
fi

# ---------------------------------------------------------------------------
# Mode A: Confined findings-agent branch (OR-resolver result).
# IN_CONFINED_SET=1 means the agent is in the confined findings-agent set.
# These agents have NO EM-written marker; confinement is by effective type.
# Checked BEFORE the marker fast-exit so they are caught here rather than
# being silently allowed by the no-marker exit below.
# ---------------------------------------------------------------------------
if [[ "$IN_CONFINED_SET" -eq 1 ]]; then
  if [[ "$FILE_PATH_NORM" =~ (^|/)state/review-trail/findings/ ]]; then
    exit 0  # Within allowed directory prefix → allow.
  fi
  # Outside allowed directory → deny (fail-closed, design-as-offers).
  # Sanitize FILE_PATH for safe interpolation into the reason string.
  FILE_PATH_SAFE="${FILE_PATH//[$'\t\r\n\f\v']/ }"
  FILE_PATH_SAFE=$(printf '%s' "$FILE_PATH_SAFE" | tr -d '\000-\037')
  # Show the most informative type identifier (prefer agent_type if it's in the set,
  # else SUBAGENT_TYPE from the back-pointer).
  _EFFECTIVE_TYPE="$AGENT_TYPE"
  _is_confined_findings_agent "$AGENT_TYPE" || _EFFECTIVE_TYPE="$SUBAGENT_TYPE"
  REASON="BLOCKED: confined findings-agent subagent write outside allowed directory."$'\n\n'
  REASON+="  Subagent type:     ${_EFFECTIVE_TYPE}"$'\n'
  REASON+="  Subagent agent_id: ${AGENT_ID}"$'\n'
  REASON+="  Attempted target:  ${FILE_PATH_SAFE}"$'\n\n'
  REASON+="This findings-agent type is confined to: state/review-trail/findings/"$'\n'
  REASON+="Write your findings sidecar under that directory. The sidecar is"$'\n'
  REASON+="scaffolded at state/review-trail/findings/<date>-<slug>.md either by"$'\n'
  REASON+="your own coordinator-doc-new call (naked dispatch) or by the EM before"$'\n'
  REASON+="dispatch. Use the path returned by your coordinator-doc-new scaffold"$'\n'
  REASON+="call (or the SIDECAR_PATH in your dispatch brief if one was injected)."
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
fi

# Non-confined subagent → allow (fail-open; preserves executor/enricher/integrator write freedom).
exit 0
