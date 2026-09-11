---
name: review-code
description: "Review a code diff/PR, or apply landed findings — findings land on the artifact."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: ""
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md with `--surface diff`.
