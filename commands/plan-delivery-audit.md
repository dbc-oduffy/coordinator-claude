---
name: plan-delivery-audit
description: "Triangulate plan claims against code and reviews for delivery status."
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: [plan-glob — default: docs/plans/*.md]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/plan-delivery-audit/SKILL.md
