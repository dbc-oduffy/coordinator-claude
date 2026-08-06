---
name: staff-session
description: "PM-GATED, never from a subagent. Agent Teams review for architecture calls."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: --mode plan|review --tier standard|full [--members \"the Staff Engineer,the Director of Engineering,...\"] <input>
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/staff-session/SKILL.md
