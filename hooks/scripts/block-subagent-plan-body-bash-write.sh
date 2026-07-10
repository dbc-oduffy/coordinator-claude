#!/usr/bin/env bash
# PreToolUse(Bash) hook: denies coordinator:executor Bash commands that
# UNAMBIGUOUSLY write to docs/plans/**/*.md — the Bash escape from the
# Write/Edit/MultiEdit-only deny in the sibling hook
# block-subagent-plan-body-write.sh.
#
# Spec backlink: docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md
#   § D-BASH, AC4, chunk C-BASH.
#
# Problem: the shipped block-subagent-plan-body-write.sh fires ONLY on
# Write|Edit|MultiEdit|NotebookEdit. A coordinator:executor can still mutate
# a plan body via Bash — `sed -i ... docs/plans/x.md`, `tee ... >>`,
# `> docs/plans/x.md`, `cp`/`mv`/`dd`, or a heredoc redirect. This hook closes
# the common-idiom subset of that escape.
#
# NOT an extension of block-reviewer-bash-outside-allowlist.sh — that hook is
# a scaffold-only ALLOWLIST for reviewers (a narrow, enumerable legitimate
# surface). Executors run a broad, unenumerable legitimate Bash surface, so an
# allowlist shape cannot port. This hook is instead a DENYLIST-of-a-specific-
# target sibling of block-subagent-plan-body-write.sh, reusing that hook's
# identity resolver verbatim.
#
# TWO INDEPENDENT AXES — do not conflate (the Staff Engineer Finding 1):
#
#   (a) IDENTITY axis — mirrors block-subagent-plan-body-write.sh EXACTLY,
#       including its AMBIGUOUS-canonical-id -> fail-CLOSED (deny) semantics,
#       with NO carve-out (see that hook's line ~227). If SUBAGENT_TYPE cannot
#       be unambiguously resolved to coordinator:executor (or something else),
#       this axis defers to that hook's collision-resistant posture — it is
#       inherited, not re-litigated here.
#
#   (b) TARGET-DETECTION axis — once identity resolves cleanly to
#       coordinator:executor, scan the Bash command for an UNAMBIGUOUS write
#       to docs/plans/*.md via the enumerated match-set (the Staff Engineer Finding 2,
#       expanded not deferred): `>`, `>>`, `sed -i ... docs/plans/..`,
#       `tee ... docs/plans/..`, `cp`/`mv`/`dd` targeting docs/plans/*.md, and
#       heredoc redirects (`cat > docs/plans/x.md <<EOF`). On ANY doubt
#       whether the command writes a plan path, fail OPEN (allow) — a
#       false-negative Bash escape is the pre-existing status quo (asymmetric
#       risk vs. a false-positive that breaks a legitimate executor command).
#       Reads (grep/cat without redirect) ALLOW.
#
# AC4 is framed honestly: this denies the enumerated COMMON write idioms; it
# does not categorically close the Bash escape (an unlisted idiom — e.g. a
# scripting-language one-liner that opens the file handle itself and writes
# to it directly — still passes). It raises the cost of the common case.
#
# Deny mechanism: hookSpecificOutput.permissionDecision -> stdout -> exit 0
#   (Form-A deny shape, mirroring block-subagent-plan-body-write.sh).
#
# Tripwires registry: docs/wiki/coordinator-tripwires.md
#   (EXECUTOR-PLAN-BODY-IMMUTABLE — this hook extends that family to Bash)

set -uo pipefail
# NOTE: -e deliberately omitted — deny hook must fail-open (allow) on unexpected error, never fail-closed.

# Safe stdin read — timeout prevents hang on Windows/Git-Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor the same escape hatch as the sibling Write/Edit hook.
if [[ "${COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY:-0}" == "1" ]]; then
  exit 0
fi

# Single git root resolution — used for both the subagent_type lookup and the
# per-session log below.
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)

# Resolve coordinator content root for flat-path fallbacks (maximalist-cutover migration).
# Fail-open: deny hook must fail-open (allow) on unexpected error, never fail-closed.
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# Tool-name guard — this hook fires on Bash only.
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
case "$TOOL_NAME" in
  Bash) : ;;
  *) exit 0 ;;
esac

# ---------------------------------------------------------------------------
# IDENTITY AXIS — verbatim mirror of block-subagent-plan-body-write.sh.
# ---------------------------------------------------------------------------

# Source the identity resolver lib.
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" ]] && LIB_PATH="$_cc_root/lib/coordinator-session.sh"
# shellcheck source=/dev/null
[[ -f "$LIB_PATH" ]] && source "$LIB_PATH"

# Extract raw agent_id (top-level, snake_case).
_raw_agent_id=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp_agent="${INPUT#*\"agent_id\":\"}"
  _raw_agent_id="${_tmp_agent%%\"*}"
fi

# Extract top-level session_id (needed by the resolver's named-teammate path).
_input_session_id=""
if command -v jq &>/dev/null; then
  _input_session_id=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  _input_session_id=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Resolve canonical agent id via shared identity resolver.
AGENT_ID=""
if declare -f resolve_subagent_identity &>/dev/null; then
  AGENT_ID="$(resolve_subagent_identity "$_raw_agent_id" "$_input_session_id")"
elif [[ "$_raw_agent_id" =~ ^[a-f0-9]{12,}$ ]]; then
  AGENT_ID="$_raw_agent_id"
fi

# Empty AGENT_ID -> no subagent or unrecognised shape -> allow.
[[ -z "$AGENT_ID" ]] && exit 0

# Extract the Bash command string.
if command -v jq &>/dev/null; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  _after_ti="${INPUT#*\"tool_input\"}"
  CMD=$(echo "$_after_ti" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' | head -1)
fi

[[ -z "$CMD" ]] && exit 0

# Subagent-type lookup via back-pointer chain (identical to the sibling hook).
SUBAGENT_TYPE=""
if [[ -n "$GIT_ROOT" ]]; then
  _backptr="$GIT_ROOT/.git/coordinator-sessions/.agents/$AGENT_ID/em-session-id.txt"
  if [[ -r "$_backptr" ]]; then
    _em_sid=$(head -1 "$_backptr" 2>/dev/null | tr -d '[:space:]')
    if [[ ! "$_em_sid" =~ ^[a-zA-Z0-9_-]{3,}$ ]]; then
      _em_sid=""
    fi
    if [[ -n "$_em_sid" ]]; then
      _dispatch_file="$GIT_ROOT/.git/coordinator-sessions/$_em_sid/dispatched-agents.txt"
      if [[ -r "$_dispatch_file" ]]; then
        SUBAGENT_TYPE=$(awk -F'\t' -v id="$AGENT_ID" '$1 == id {print $3; exit}' "$_dispatch_file" 2>/dev/null)
      fi
    fi
  fi
fi

# Block when SUBAGENT_TYPE is coordinator:executor OR AMBIGUOUS (fail-closed,
# no carve-out — mirrors block-subagent-plan-body-write.sh:224-228 exactly).
# All other types — including empty / lookup-failure — allow.
if [[ "$SUBAGENT_TYPE" == "AMBIGUOUS" ]]; then
  : # Fall through to target-detection (collision -> unconditional deny below).
elif [[ "$SUBAGENT_TYPE" != "coordinator:executor" ]]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# TARGET-DETECTION AXIS — independent of identity. Only reached once identity
# has resolved to coordinator:executor (or AMBIGUOUS, which denies
# unconditionally regardless of target — mirroring the sibling hook's
# no-carve-out collision semantics: for AMBIGUOUS we skip target-detection
# doubt-analysis and deny directly, since AMBIGUOUS has no allow path at all).
# ---------------------------------------------------------------------------

if [[ "$SUBAGENT_TYPE" == "AMBIGUOUS" ]]; then
  UNAMBIGUOUS_WRITE=1
else
  # Normalize CRLF -> LF (Windows/Git-Bash jq.exe text-mode quirk — mirrors
  # block-destructive-git-orphan.sh's CRLF-robustness note).
  CMD_NORM="${CMD//$'\r'/}"

  # docs/plans/*.md path-shape fragment, tolerant of a leading path prefix
  # (absolute or relative) before `docs/plans/`.
  PLAN_PATH_RE='([A-Za-z0-9_./-]*/)?docs/plans/[A-Za-z0-9_.-]+\.md'

  UNAMBIGUOUS_WRITE=0

  # Quote-free, separator-free gap between a write-verb and its own argument
  # — requires the plan-path to be the verb's own argument (same simple
  # command), not merely co-occurring anywhere in the command string. A bare
  # word like "tee"/"cp" appearing inside another command's quoted argument
  # (e.g. `echo "run tee docs/plans/z.md"`) does NOT match, because the verb
  # is not command-position-anchored in that shape (Review: code-reviewer —
  # Finding 2/3, word-anywhere matching false-positived on unrelated
  # echo/grep commands that merely mention a write-verb token and a
  # plan-path-shaped string without either being the other's argument).
  _NO_SEP_NO_QUOTE='[^;&|'$'\n''"'"'"']*'

  # (1) Plain redirect: `> docs/plans/x.md` or `>> docs/plans/x.md`.
  #     Matches `cmd > path`, `cmd >> path`, with optional space around `>`.
  if [[ "$CMD_NORM" =~ \>\>?[[:space:]]*$PLAN_PATH_RE ]]; then
    UNAMBIGUOUS_WRITE=1
  fi

  # (2) sed -i ... docs/plans/x.md — in-place edit is a write. Verb must be
  #     command-position-anchored (start of string or after a ;/&/| command
  #     separator) with the plan-path as its own argument. Matches both the
  #     short-option (`-i`) and GNU long-option (`--in-place`, with or
  #     without a `=SUFFIX` backup-extension argument) forms (Review:
  #     code-reviewer — Finding 4: the reviewer's own trace speculated
  #     `--in-place` "likely already matches" via a literal `-i` substring —
  #     verified false; the short-option-only regex requires `-i` as its own
  #     space-delimited token, which `--in-place=bak` never satisfies).
  _SED_VERB_RE='sed[[:space:]]+((-[A-Za-z]*|--[A-Za-z-]+(=[^[:space:]]*)?)[[:space:]]+)*(-i|--in-place(=[^[:space:]]*)?)'
  if [[ "$UNAMBIGUOUS_WRITE" -eq 0 ]] && \
     [[ "$CMD_NORM" =~ (^|[[:space:]]*[\;\&\|][[:space:]]*)$_SED_VERB_RE[[:space:]=]$_NO_SEP_NO_QUOTE$PLAN_PATH_RE ]]; then
    UNAMBIGUOUS_WRITE=1
  fi

  # (3) tee ... docs/plans/x.md — tee always writes its filename args.
  #     Verb command-position-anchored, plan-path as its own argument
  #     (Review: code-reviewer — Finding 3, added the same prefix guard idiom
  #     4 already had, closing the inconsistency between the two idioms).
  if [[ "$UNAMBIGUOUS_WRITE" -eq 0 ]] && \
     [[ "$CMD_NORM" =~ (^|[[:space:]]*[\;\&\|][[:space:]]*)tee[[:space:]]$_NO_SEP_NO_QUOTE$PLAN_PATH_RE ]]; then
    UNAMBIGUOUS_WRITE=1
  fi

  # (4) cp / mv / dd targeting docs/plans/*.md (as a destination — best-effort:
  #     verb command-position-anchored, plan-path as its own argument, per
  #     D-BASH's enumerated set).
  if [[ "$UNAMBIGUOUS_WRITE" -eq 0 ]] && \
     [[ "$CMD_NORM" =~ (^|[[:space:]]*[\;\&\|][[:space:]]*)(cp|mv|dd)[[:space:]]$_NO_SEP_NO_QUOTE$PLAN_PATH_RE ]]; then
    UNAMBIGUOUS_WRITE=1
  fi

  # (5) Heredoc redirect: `cat > docs/plans/x.md <<EOF` (and similar,
  #     `<<-EOF`, `<<'EOF'`) is intentionally NOT re-checked separately here
  #     (Review: code-reviewer — Finding 1, idiom 5 removed as dead code: its
  #     own final condition requires a plain `>` redirect to a plan path,
  #     which idiom 1 above already matches and sets UNAMBIGUOUS_WRITE=1
  #     before idiom 5 is ever reached — no command shape could satisfy
  #     idiom 5's guard `UNAMBIGUOUS_WRITE -eq 0` while also satisfying its
  #     own body condition).
fi

# Any doubt -> fail OPEN (allow). Only an unambiguous match denies.
[[ "$UNAMBIGUOUS_WRITE" -eq 0 ]] && exit 0

# session_id already extracted early in the identity-resolver block.
SESSION_ID="$_input_session_id"

# Per-session log (best-effort).
if [[ -n "$SESSION_ID" && -n "$GIT_ROOT" ]]; then
  LOG_DIR="$GIT_ROOT/.git/coordinator-sessions/$SESSION_ID"
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  echo "${TS} | DENY | agent_id=${AGENT_ID} | bash-command-plan-write" \
    >> "$LOG_DIR/plan-body-bash-write-block.log" 2>/dev/null || true
fi

# Security hardening: strip/replace newline and other control chars from CMD
# before it is interpolated into the deny-JSON reason.
CMD_SAFE="${CMD//[$'\t\r\n\f\v']/ }"
CMD_SAFE=$(printf '%s' "$CMD_SAFE" | LC_ALL=C tr -d '\000-\037')

if [[ "$SUBAGENT_TYPE" == "AMBIGUOUS" ]]; then
  REASON="BLOCKED: ambiguous agent identity (canonical-id collision) — failing closed."$'\n\n'
  REASON+="  Canonical id: ${AGENT_ID}"$'\n'
  REASON+="  Recorded type: AMBIGUOUS (collision sentinel in dispatched-agents.txt)"$'\n'
  REASON+="  Command:       ${CMD_SAFE}"$'\n\n'
  REASON+="Two dispatches sharing the same canonical id arrived with DIFFERENT subagent_types."$'\n'
  REASON+="The writer (track-dispatched-agents.sh) marked the row AMBIGUOUS to prevent the"$'\n'
  REASON+="wrong type being resolved — both colliding dispatches are blocked unconditionally."$'\n\n'
  REASON+="Override (rare-use — read the hook source before invoking):"$'\n'
  REASON+="  COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY=1"
else
  REASON="BLOCKED: coordinator:executor may not write the plan body via Bash."$'\n\n'
  REASON+="  Subagent: ${AGENT_ID} (coordinator:executor)"$'\n'
  REASON+="  Command:  ${CMD_SAFE}"$'\n\n'
  REASON+="This command appears to write to a docs/plans/*.md path. Your surface is the"$'\n'
  REASON+="per-chunk flight sidecar — tasks/<plan-slug>/flight/<chunk-id>.md — not the"$'\n'
  REASON+="plan body. Derive <plan-slug> from the plan filename minus the YYYY-MM-DD-"$'\n'
  REASON+="prefix and .md suffix; <chunk-id> from the dispatch brief's chunk field."$'\n\n'
  REASON+="If amending the plan body WAS your deliverable, you are the wrong agent type"$'\n'
  REASON+="for this work — plan-body edits route to EM-inline / coordinator:enricher /"$'\n'
  REASON+="coordinator:review-integrator. The dispatching EM should re-route this chunk."$'\n\n'
  REASON+="Override (rare-use — read the hook source before invoking):"$'\n'
  REASON+="  COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY=1"
fi

if command -v jq &>/dev/null; then
  EMIT=$(jq -nc --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }')
else
  esc="${REASON//\\/\\\\}"
  esc="${esc//\"/\\\"}"
  esc="${esc//$'\n'/\\n}"
  esc="${esc//$'\r'/\\r}"
  EMIT=$(printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$esc")
fi

printf '%s\n' "$EMIT"
exit 0
