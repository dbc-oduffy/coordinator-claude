---
name: parallel-code-review
description: "Weekly pre-merge code-review gate — chunk reviewers, one verdict. /workweek-complete only."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--force] [--gate-mode strict|advisory]"
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/parallel-code-review/SKILL.md
