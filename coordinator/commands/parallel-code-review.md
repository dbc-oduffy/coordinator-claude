---
name: parallel-code-review
description: "Pre-merge weekly code-review gate — N code-semantics chunk reviewers (Sonnet) + 3 mechanical specialist workers + no-rewrite synthesizer (BLOCKED/WARN/OK). The Staff Engineer runs a separate post-gate architecture pass, not the gate itself. Invoked only from /workweek-complete."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--force] [--gate-mode strict|advisory]"
---

Read and follow the instructions in ${CLAUDE_PLUGIN_ROOT}/skills/parallel-code-review/SKILL.md
