---
name: handoff-archival
description: "Archive consumed handoffs — moves tasks/handoffs/*.md files older than 48 hours to archive/handoffs/ and checks .gitignore safety. This skill should be used when cleaning up old handoffs, when the handoffs directory is cluttered, or as part of periodic maintenance. Invoked by /update-docs (Phase 8) or standalone."
---

# Handoff Archival

## Overview

Move consumed handoffs from the active directory to the archive (both git-tracked — the archive is the paper trail):

- **Active handoffs:** `tasks/handoffs/*.md` — available for `/session-start` pickup
- **Archived handoffs:** `archive/handoffs/*.md` — consumed, kept for historical reference

**Skip entirely if no handoff files exist.**

## Steps

1. Check `tasks/handoffs/` for `.md` files
2. **Chain-aware archival (supersession pass):** Before the time-based sweep, scan all active handoffs for `Continuing from` references (look for the pattern `_Continuing from [filename]:` or `Continuing from [filename]` in the `## What Was Accomplished` section). If the referenced predecessor file is still in `tasks/handoffs/`, archive it immediately — the successor has absorbed both the predecessor's context (via the preamble) and its unresolved obligations (via the `## Carried Forward` section). The predecessor is fully superseded. This pass runs regardless of age.
3. **Move old handoffs to archive:** Any handoff in `tasks/handoffs/` older than 48 hours is a candidate for archival. Before moving, apply the branch-activity check:
   - Extract the branch name from the handoff (look for a `Branch:` field or inline branch reference)
   - If a branch is found, check for commits newer than the handoff file's modification timestamp: `git log <branch> --since="<file-mtime>" --oneline -1`
   - **If recent commits exist:** keep the handoff in `tasks/handoffs/` and note: "Kept [filename] — branch [branch-name] has activity since handoff was written"
   - **If no branch is referenced, or the branch has no recent commits:** move to `archive/handoffs/` (create directory if needed)
   - The 48-hour window ensures multi-session work retains its handoff context — `/session-start` no longer archives on read, so this is the only archival path. Still concurrent-agent-safe.
4. Do NOT delete archived handoffs — they are the paper trail for why things are written the way they are

## `.gitignore` Check

Verify that `tasks/` is NOT in `.gitignore`. If it is, warn the user — active handoffs must be tracked.
