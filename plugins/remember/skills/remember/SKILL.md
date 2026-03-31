---
name: remember
description: Save session state for clean continuation next session.
allowed-tools: Write
---

Write a handoff note so the next session can continue cleanly. Use your knowledge of the current session — you were here. Write in first person ("I").

**Path:** Write to the `memory/sessions/handoff.md` file inside the Claude Code project memory directory. The exact path is:
`~/.claude/projects/<project-slug>/memory/sessions/handoff.md`

where `<project-slug>` is the current project's slug (visible in the session directory path). Overwrite any existing content.

Format:

```
# Handoff

## State
{What's done, what's not. Files, MRs, decisions. 2-4 lines max.}

## Next
{What to pick up. Priority order. 1-3 items.}

## Context
{Non-obvious gotchas, blockers, preferences from this session. Skip if nothing.}
```

Rules:

- Under 20 lines total
- Specific: file paths, MR numbers, branch names
- Forward-looking — the next session doesn't care about the journey
- If nothing meaningful to hand off, write: "No active work."

Say "Saved." when done — nothing else.
