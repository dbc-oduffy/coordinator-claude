#!/usr/bin/env bash
# PostToolUse("") dispatcher — folds the two universal advisory hooks into one
# process, cutting one bash.exe spawn per tool call on Windows.
#
# Folded advisories (each defines a sourceable check_* function at file scope):
#   context-pressure-advisory.sh → check_context_pressure SESSION_ID TRANSCRIPT_PATH
#   runtime-tripwire-advisory.sh → check_runtime_tripwire SESSION_ID [AGENT_ID]
#
# This dispatcher fires on ALL PostToolUse events (matcher ""); it does NOT gate
# on tool_name — PostToolUse fires on every tool and both advisory checks are
# universal (not tool-name-scoped).
#
# A single PostToolUse hook process must emit at most ONE JSON object. When both
# advisories fire, their additionalContext texts are merged with a paragraph
# separator into one envelope. A single firing advisory passes through unchanged.
# Neither firing → no output.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md § Phase 3
#
# Contract:
#   stdin   — Claude Code PostToolUse JSON (session_id, transcript_path, agent_id, ...)
#   stdout  — hookSpecificOutput JSON with additionalContext when an advisory fires;
#             NOTHING otherwise
#   exit 0  — always (advisory dispatcher; must never block or return non-zero)
#
# CRLF-robustness: this file MUST stay LF-only. A \+CRLF line-continuation
# escapes the CR rather than the newline, splitting statements and crashing the
# hook. Pin via .gitattributes *.sh eol=lf.

# ---------------------------------------------------------------------------
# BASH_VERSINFO guard — FIRST, before set flags and any bash-4-only syntax.
# Stock macOS /bin/bash is 3.2; brew bash upgrades to 4+.
# On bash <4: exit 0 silently. This is an advisory dispatcher (no deny
# semantics) — there is no useful advisory to emit if bash-4 features are
# absent, and a noisy error from a bash-3.2 machine on every tool call would
# be worse than silence.
# This guard MUST PARSE on bash 3.2 (no bash-4-only syntax above this line).
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  exit 0
fi

# set -uo pipefail; deliberately NOT set -e.
# Advisory hooks must fail-open; set -e would abort the dispatcher on any
# subcommand non-zero (stat/jq/find inside advisory functions), defeating the
# contract. Critical sections use explicit || guards.
set -uo pipefail

# ---------------------------------------------------------------------------
# Read stdin ONCE.
# timeout 2 cat is the portable idiom used by the folded scripts. If timeout
# is absent the 2>/dev/null hides the "not found" error, the subshell exits
# non-zero, and || cat falls back to plain cat.
# ---------------------------------------------------------------------------
INPUT=$(timeout 2 cat 2>/dev/null || cat)
[ -z "$INPUT" ] && exit 0

# ---------------------------------------------------------------------------
# Parse session_id, transcript_path, agent_id ONCE from INPUT.
# jq preferred; sed fallback for environments where jq is absent.
# agent_id is present in named-teammate subagent payloads (absent on EM fires);
# transcript_path is used by the context-pressure advisory.
# ---------------------------------------------------------------------------
if command -v jq &>/dev/null; then
  session_id=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  transcript_path=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  agent_id=$(printf '%s' "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)
else
  session_id=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  transcript_path=$(printf '%s' "$INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  agent_id=$(printf '%s' "$INPUT" | sed -n 's/.*"agent_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# ---------------------------------------------------------------------------
# Source both advisory scripts — defines check_* functions only; no stdin read,
# no output, no sentinel/log writes happen at source time (both scripts are
# designed sourceable). Resolved relative to this file's own directory so the
# dispatcher works regardless of invoking cwd.
# runtime-tripwire-advisory.sh sources lib/runtime-thresholds.sh at its own
# file scope via its own BASH_SOURCE[0] — that path resolves correctly when
# sourced here because BASH_SOURCE[0] inside the sourced file is the sourced
# file's path, not the dispatcher's path.
# ---------------------------------------------------------------------------
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=context-pressure-advisory.sh
source "$_d/context-pressure-advisory.sh"
# shellcheck source=runtime-tripwire-advisory.sh
source "$_d/runtime-tripwire-advisory.sh"

# ---------------------------------------------------------------------------
# Run both advisories via subshell-capture.
# Each check_* runs in a command-substitution subshell. A crash inside one
# subshell (e.g. unbound variable under set -u) returns non-zero but cannot
# propagate to the dispatcher — the || assignment collapses it to empty and
# the other advisory still runs independently. This is the correct fail-open
# shape for advisory-only hooks.
# ---------------------------------------------------------------------------
cp_out=$(check_context_pressure "$session_id" "$transcript_path" 2>/dev/null) || cp_out=""
rt_out=$(check_runtime_tripwire "$session_id" "$agent_id" 2>/dev/null) || rt_out=""

# ---------------------------------------------------------------------------
# MERGE — a single PostToolUse hook process must emit at most ONE JSON object.
# (The harness behavior for multiple JSON objects from one command is
# undocumented; emitting two is unsafe.)
#
# For each non-empty output, extract its additionalContext text via jq. Then:
#   both texts present  → emit ONE merged JSON (cp_text + "\n\n" + rt_text)
#   exactly one present → pass that advisory's JSON through unchanged
#   neither             → emit nothing
# ---------------------------------------------------------------------------
cp_text=""
rt_text=""

if [[ -n "$cp_out" ]] && command -v jq &>/dev/null; then
  cp_text=$(printf '%s' "$cp_out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
fi
if [[ -n "$rt_out" ]] && command -v jq &>/dev/null; then
  rt_text=$(printf '%s' "$rt_out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
fi

if [[ -n "$cp_text" && -n "$rt_text" ]]; then
  # Both advisories fired — emit ONE JSON with both texts merged.
  # The $'\n\n' C-string inserts two literal newlines as a paragraph break.
  # jq --arg encodes them correctly as \n\n in the JSON string value.
  merged_text="${cp_text}"$'\n\n'"${rt_text}"
  jq -n --arg ctx "$merged_text" \
    '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
elif [[ -n "$cp_out" ]]; then
  # Only context-pressure fired — pass through unchanged.
  # Command substitution strips the trailing newline; re-add it for clean output.
  printf '%s\n' "$cp_out"
elif [[ -n "$rt_out" ]]; then
  # Only runtime-tripwire fired — pass through unchanged.
  printf '%s\n' "$rt_out"
fi
# Neither fired — emit nothing; Claude Code interprets no output as no advisory.

exit 0
