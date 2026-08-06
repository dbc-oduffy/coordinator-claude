---
name: dogfood
description: "Fix-through loop — invoke a new thing, fix bugs until it works."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: <target> [--narrow|--broad|--shakedown]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/dogfood/SKILL.md
