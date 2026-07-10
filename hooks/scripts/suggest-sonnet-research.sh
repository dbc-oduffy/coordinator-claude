#!/usr/bin/env bash
# PreToolUse hook: nudge the EM to delegate web research to dedicated skills/agents.
# Uses "allow" — never blocks, just injects a nudge into Claude's context.
# Single URL from the user = proceed directly. Everything else = delegate.
#
# Suppression: when this hook fires from inside a subagent (scout, executor, researcher),
# the EM has ALREADY authorized that dispatch — re-emitting the "delegate to a scout"
# advisory at scout-altitude is doctrine-incorrect and noisy (empirical: 6× misfires
# in a single sanctioned solo-scout dispatch, 2026-06-09). Detect via the top-level
# `agent_id` field, which Claude Code emits on subagent fires only (same convention
# documented in block-subagent-archive-write.sh:76-90 and track-touched-files.sh:72-85).
# Format-guard fails → AGENT_ID empty → nudge fires (safe direction for an advisory).
#
# Query-specific offer (strang-06b): extracts tool_input.url (WebFetch) or
# tool_input.query (WebSearch) and folds a ready-to-paste Agent(...) dispatch brief
# into additionalContext, parameterised by the actual URL/query. The EM copy-pastes
# the brief rather than composing a dispatch from scratch.
#
# NOTE: Full auto-spawn (example-orchestration-hub-native routing that fires the Agent tool without EM
# action) is deferred to strang-06c — depends on strang-05 (example-orchestration-hub advisory routing)
# which is NOT yet landed. This hook emits the OFFER; the EM dispatches manually.

INPUT=$(cat 2>/dev/null || true)

# Subagent fire → caller is already a delegated researcher → suppress the nudge.
# Suppress on agent_id KEY PRESENCE (parity with nudge-em-code-dispatch.js:219):
# named-teammate IDs carry the format a<name>-<16hex> (e.g. arscout-deadbeef123456ab),
# which the old bare-hex regex ^[a-f0-9]{12,}$ does not match — causing AGENT_ID to be
# cleared and the nudge to mis-fire at scout altitude. Key presence is the correct and
# sufficient signal; format validation adds no safety here.
# Review: code-reviewer (F6) — key-presence guard replaces format-validation guard
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  exit 0
fi

# Extract URL (WebFetch) or query (WebSearch) from tool_input.
# jq primary, sed fallback — matching the extraction pattern used in peer hooks
# (nudge-improvement-queue-write.sh, track-touched-files.sh).
TOOL_URL=""
TOOL_QUERY=""
if command -v jq >/dev/null 2>&1; then
  TOOL_URL=$(printf '%s' "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null || true)
  TOOL_QUERY=$(printf '%s' "$INPUT" | jq -r '.tool_input.query // empty' 2>/dev/null || true)
else
  # Security: scope extraction to the tool_input object to avoid matching
  # a decoy "url"/"query" field elsewhere in the payload. WebFetch/WebSearch
  # tool_input objects are flat (no nested {}), so [^{}]* safely bounds the match.
  # Review: security-audit (strang-06C) — greedy .* matched last "url" anywhere in payload
  TOOL_INPUT_STR=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_input"[[:space:]]*:[[:space:]]*{\([^{}]*\)}.*/\1/p')
  TOOL_URL=$(printf '%s' "$TOOL_INPUT_STR" | sed -n 's/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TOOL_QUERY=$(printf '%s' "$TOOL_INPUT_STR" | sed -n 's/.*"query"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Determine the subject for the dispatch brief — URL wins when both fields are present.
SUBJECT=""
SUBJECT_KIND=""
if [[ -n "$TOOL_URL" ]]; then
  SUBJECT="$TOOL_URL"
  SUBJECT_KIND="url"
elif [[ -n "$TOOL_QUERY" ]]; then
  SUBJECT="$TOOL_QUERY"
  SUBJECT_KIND="query"
fi

# Build the research pipeline suggestions
RESEARCH_SUGGESTIONS="- Internet research (web sources) → /coordinator:research --mode=web <topic>\n- Codebase / repo research → /coordinator:research --mode=repo <path> [--deepest]\n- Structured batch research (N subjects, schema output) → /coordinator:research --mode=structured <spec-path>\n- Quick codebase exploration → Agent with subagent_type='Explore'\n- Enriching specs with codebase facts → Agent with subagent_type='coordinator:enricher'\n- YouTube / podcast / audio research → /notebooklm-research"

# DR is bundled into coordinator (2026-07-04 full-merge) — availability == coordinator present == this hook firing; no probe, always emit.

# Build the ready-to-paste dispatch brief when we have an extracted subject.
# Escape SUBJECT for safe embedding in a JSON string value: backslashes first,
# then double-quotes (order matters — escaping quotes before backslashes double-escapes).
DISPATCH_SUFFIX=""
if [[ -n "$SUBJECT" ]]; then
  # Strip ASCII control chars (0x00-0x1F) before JSON-escaping: raw newline, CR, tab,
  # or any other control char in the extracted URL/query produces malformed JSON in the
  # additionalContext string value. tr -d '\000-\037' removes the entire U+0000-U+001F
  # range; backslash and double-quote are outside this range and handled by sed after.
  # Review: code-reviewer (F5) — control-char strip prevents malformed JSON
  SUBJECT_SAFE=$(printf '%s' "$SUBJECT" | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')
  if [[ "$SUBJECT_KIND" == "url" ]]; then
    DISPATCH_SUFFIX="\n\nREADY-TO-PASTE DISPATCH (use this Agent call instead of the WebFetch):\n\n  Agent(\n    subagent_type='coordinator:research-scout',\n    prompt='Fetch and summarise the content at: ${SUBJECT_SAFE}\\nReturn key findings as structured notes.',\n    run_in_background=True\n  )"
  else
    DISPATCH_SUFFIX="\n\nREADY-TO-PASTE DISPATCH (use this Agent call instead of the WebSearch):\n\n  Agent(\n    subagent_type='coordinator:research-scout',\n    prompt='Research query: ${SUBJECT_SAFE}\\nFind authoritative sources, summarise key findings, and return structured notes.',\n    run_in_background=True\n  )"
  fi
fi

cat << HOOK_OUTPUT
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "DELEGATION REQUIRED: You are about to do web research as Opus. The EM orchestrates — researchers execute. Use the dedicated research infrastructure, not ad-hoc agent dispatch:\n\n${RESEARCH_SUGGESTIONS}\n\nOnly proceed with direct web calls if: (1) the user pasted you a specific URL and asked you to read it — one fetch, no research, or (2) you are verifying a single fact mid-conversation where dispatching an agent is pure overhead.\n\nDo NOT spin up a generic Agent(prompt='go search for...') — that discards tested guardrails (phase separation, quality gates, Haiku grounding). Opus tokens are for judgment, not for reading web pages.${DISPATCH_SUFFIX}"
  }
}
HOOK_OUTPUT
