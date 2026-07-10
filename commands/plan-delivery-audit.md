---
name: plan-delivery-audit
description: "Triangulate plan-claim / code-reality / review oracles to classify each plan into DELIVERED+REVIEWED / DELIVERED-UNREVIEWED / PARTIAL / IN-FLIGHT / ABANDONED. Run after any crash or 'did we actually finish what we think we finished?' moment."
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: [plan-glob — default: docs/plans/*.md]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/plan-delivery-audit/SKILL.md
