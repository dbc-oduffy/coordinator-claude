---
name: remember
description: Quick-write a lightweight session note to memory/sessions/note.md. For full session wrap-up, use coordinator:session-end or /handoff.
allowed-tools: Write
---

Write a session note so the next session can continue cleanly. Use your knowledge of the current session — you were here. Write in first person ("I").

**Path:** Write to `tasks/session-note.md` in the project root. Overwrite any existing content.

Format:

```
# Session Note

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
- If nothing meaningful to save, write: "No active work."

Say "Saved." when done — nothing else.
