#!/bin/bash
# SessionStart hook: Detect UE projects and emit knowledge-distrust warning.
# Only fires when a .uproject file is found in the working directory tree.
# Silent (no output) for non-UE projects.
#
# Rationale: LLM training data about Unreal Engine is broadly untrustworthy —
# not just recent versions. Function names, parameter signatures, class hierarchies,
# default behaviors, deprecation status — any of it may be wrong, stale, or
# hallucinated. The holodeck-docs MCP provides 333K+ verified doc chunks as
# ground truth.

# Shallow search — maxdepth 3 covers typical project layouts without scanning
# deep engine/plugin trees. -print -quit exits on first match for speed.
UPROJECT=$(find . -maxdepth 3 -name '*.uproject' -print -quit 2>/dev/null)

if [[ -z "$UPROJECT" ]]; then
  exit 0  # Not a UE project — silent exit
fi

PROJECT_NAME=$(basename "$UPROJECT" .uproject)

cat <<EOF
UE PROJECT DETECTED ($PROJECT_NAME): LLM training data about Unreal Engine is broadly untrustworthy. Function names, parameter signatures, class hierarchies, default behaviors, deprecation status — any of it may be wrong, stale, or hallucinated. You have 333K+ indexed doc chunks and 73K verified API declarations via holodeck-docs MCP. Treat MCP tools as ground truth and training knowledge as unverified hypothesis. Use quick_ue_lookup before asserting any UE API usage.
EOF

exit 0
