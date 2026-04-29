#!/bin/bash
# SessionStart hook: Detect UE projects and emit knowledge-distrust warning.
# Only fires when a .uproject file is found in the working directory tree.
# Silent (no output) for non-UE projects.
#
# Rationale: LLM training data about Unreal Engine is broadly untrustworthy —
# not just recent versions. Function names, parameter signatures, class hierarchies,
# default behaviors, deprecation status — any of it may be wrong, stale, or
# hallucinated. The holodeck-docs MCP provides 421,935 verified vectors as ground
# truth (73K API declarations + 197K structural-index symbols).

# Shallow search — maxdepth 3 covers typical project layouts without scanning
# deep engine/plugin trees. -print -quit exits on first match for speed.
UPROJECT=$(find . -maxdepth 3 -name '*.uproject' -print -quit 2>/dev/null)

if [[ -z "$UPROJECT" ]]; then
  exit 0  # Not a UE project — silent exit
fi

PROJECT_NAME=$(basename "$UPROJECT" .uproject)

cat <<EOF
UE PROJECT DETECTED ($PROJECT_NAME): LLM training data for Unreal Engine is broadly untrustworthy — function names, signatures, class hierarchies, deprecation status, and newer 5.x APIs are frequently hallucinated. Treat training knowledge as unverified hypothesis.
Verified counts: 421,935 indexed vectors, 73K API declarations, 197K structural-index symbols.
Verified tools: quick_ue_lookup, lookup_ue_class, check_ue_patterns, find_symbol, search_symbols.
Known hallucination risk categories: UPROPERTY/UFUNCTION specifiers; Build.cs dependencies; GAS internals; UE 5.7 accessor tightening; Blueprint pin types (PC_Real vs PC_Float); BT subnodes (AddSubNode).
EOF

exit 0
