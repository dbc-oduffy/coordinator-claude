---
name: percolate
description: "Dry-run then confirm publish of files from a working source tree to a named publish-repo target. Wraps publish.sh with gate + CI smoke."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: <target>
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/percolate/SKILL.md
