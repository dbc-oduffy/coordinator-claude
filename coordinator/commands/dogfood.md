---
name: dogfood
description: "Smoke-driven fix-through loop — invoke a newly-built thing (skill, script, pipeline, install process) and fix bugs until it works or gets replanned. Binary outcome only: converge or switch gears."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: <target> [--narrow|--broad|--shakedown]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/dogfood/SKILL.md
