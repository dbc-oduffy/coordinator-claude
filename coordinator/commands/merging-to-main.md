---
name: merging-to-main
description: "Use when a branch is ready to merge to main. Drafts release notes, creates PR, waits for CI, merges, cleans up."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: [--force]
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/merging-to-main/SKILL.md
