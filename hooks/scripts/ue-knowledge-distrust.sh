#!/usr/bin/env bash
# SessionStart hook: Detect UE projects, emit knowledge-distrust warning, and
# auto-bootstrap per-project UE plugin settings for next session.
#
# Only fires when a .uproject file is found in the working directory tree.
# Silent (no output) for non-UE projects.
#
# Rationale: LLM training data about Unreal Engine is broadly untrustworthy —
# not just recent versions. Function names, parameter signatures, class hierarchies,
# default behaviors, deprecation status — any of it may be wrong, stale, or
# hallucinated. The example-game-repo-docs MCP provides 333K+ verified doc chunks as
# ground truth.
#
# Per-project plugin gating: UE plugins (example-game-repo-control, example-game-repo-docs,
# example-game-repo, game-dev) are disabled globally and opt-in via per-project
# .claude/settings.json. This hook auto-writes the opt-in file so the next
# session picks up the UE plugins. The first session in a fresh UE repo still
# loads lean defaults — close and re-open Claude Code after this hook runs.
# See docs/wiki/per-project-plugin-gating.md for full details.

# Plugin root derived from script location (hooks/scripts/ → ../../).
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Shallow search — maxdepth 3 covers typical project layouts without scanning
# deep engine/plugin trees. -print -quit exits on first match for speed.
UPROJECT=$(find . -maxdepth 3 -name '*.uproject' -print -quit 2>/dev/null)

if [[ -z "$UPROJECT" ]]; then
  exit 0  # Not a UE project — silent exit
fi

PROJECT_NAME=$(basename "$UPROJECT" .uproject)

# NEW: auto-bootstrap per-project settings for next session.
SETTINGS="$(pwd)/.claude/settings.json"

# jq guard: required only for the merge path (existing settings.json present).
# If jq is absent and no settings.json exists, the bootstrap handles it with
# pure shell. If jq is absent and settings.json exists, we skip with a warning.
if [[ -f "$SETTINGS" ]] && ! command -v jq >/dev/null 2>&1; then
  echo "WARNING: jq not on PATH — UE bootstrap requires jq to merge with existing $SETTINGS" >&2
  echo "Install: choco install jq / scoop install jq / apt-get install jq" >&2
elif [[ -f "$SETTINGS" ]] && jq -e '.enabledPlugins["example-game-repo-control@example-game-workbench-repo"] == false' "$SETTINGS" >/dev/null 2>&1; then
  # Explicit false override: user deliberately disabled UE plugins in this project.
  # Do NOT overwrite — skip with a warning so the user knows why UE plugins are absent.
  echo "UE override SKIPPED — $SETTINGS explicitly disables UE plugins" >&2
  echo "To enable UE plugins in this project, run: ~/.claude/bin/claude-ue-bootstrap.sh $(pwd)" >&2
elif [[ ! -f "$SETTINGS" ]] || ! jq -e '.enabledPlugins["example-game-repo-control@example-game-workbench-repo"] == true' "$SETTINGS" >/dev/null 2>&1; then
  # Either no settings.json, or settings.json exists but lacks the UE override.
  # Run the bootstrap script to populate / merge the override.
  "${PLUGIN_ROOT}/bin/claude-ue-bootstrap.sh" "$(pwd)" >&2
  echo "UE override written — close and re-open Claude Code to load UE plugins (current session uses lean defaults)" >&2
fi

# Existing context-injection block (unchanged) — always emitted for UE projects.
cat <<EOF
UE PROJECT DETECTED ($PROJECT_NAME): LLM training data about Unreal Engine is broadly untrustworthy. Function names, parameter signatures, class hierarchies, default behaviors, deprecation status — any of it may be wrong, stale, or hallucinated. You have 333K+ indexed doc chunks and 73K verified API declarations via example-game-repo-docs MCP. Treat MCP tools as ground truth and training knowledge as unverified hypothesis. Use quick_ue_lookup before asserting any UE API usage.
EOF

exit 0
