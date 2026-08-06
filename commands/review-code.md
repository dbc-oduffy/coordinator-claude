---
name: review-code
description: "Review a ready diff/PR, or apply landed code-review findings."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]

---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md with `--surface diff`.
