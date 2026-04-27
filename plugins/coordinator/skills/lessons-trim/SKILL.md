---
name: lessons-trim
description: "Periodic maintenance of lessons files — trims stale entries, merges duplicates, and deletes exhausted feature-scoped files. Implements the 'Periodic trim' rule from CLAUDE.md's Self-Improvement Loop. This skill should be used when lessons.md is getting long, when a feature is complete and its lessons file should be cleaned up, or when periodic housekeeping is needed. Invoked by /update-docs (Phase 6) or standalone."
version: 1.0.0
---

# Lessons Trim

## Overview

Review `tasks/lessons.md` (global) and any `tasks/<feature>/lessons.md` files. This is the periodic safety net described in the Self-Improvement Loop guidelines in CLAUDE.md.

**Discovery:** Find feature-scoped lessons files via `tasks/*/lessons.md` (glob). Each match is a feature-scoped file. Global lessons live at `tasks/lessons.md` (no subdirectory).

**Skip if no lessons files exist.**

## Steps

**For each lessons file:**

1. Read the file and count entries/lines
2. **Classify** each entry — for every entry that shouldn't stay in `lessons.md`, find it a home rather than discarding it:
   - **Migrate to wiki guide** — if the entry describes a system behavior, gotcha, or implementation pattern, find (or create) the appropriate `docs/wiki/*.md` and add it there under a `## Gotchas` or `## Key Patterns` section. These are battle stories — losing the ability to grep for them is a real cost.
   - **Migrate to CLAUDE.md / MEMORY.md** — if the entry is a workflow or collaboration norm that's now redundant because it was encoded in those files, confirm it's actually there before removing from lessons.
   - **Discard** only if the entry is pure ephemeral task state (e.g., "fixed bug in session X") with no extractable pattern and no natural wiki home.
3. **Merge** entries that cover the same topic into a single tighter entry
4. **Preserve** entries that are still actively saving time or preventing repeated mistakes — keep them in `lessons.md` for fast session-start access
5. If a feature-scoped lessons file (`tasks/<feature>/lessons.md`) relates to completed work and all entries are either migrated or preserved in the global file, delete it

**"Remind agent X to do Y" entries are NOT lessons — they are agent-prompt updates.** If a candidate lesson reads "remind reviewer/agent Y to check Z" or "prompt agent X to always do Y," the correct fix is to add Z directly to Y's agent definition. `lessons.md` is loaded by the EM, not by Y — storing a behavioral rule for Y in `lessons.md` is dead weight that never reaches the agent it's meant for.

During trim, reclassify any such entry:
1. Find the relevant agent file (e.g., `plugins/coordinator-claude/coordinator/agents/<agent-name>.md`)
2. Add the substance of the lesson to that agent's prompt — in the appropriate behavioral section
3. Delete the lesson entry from `lessons.md` entirely (do not migrate to wiki; this is a routing correction, not a battle story)

If the agent file cannot be located or is read-only, escalate to the EM rather than leaving the lesson in place.

**Migration mechanics:** When migrating an entry to a wiki guide, use the existing `docs/wiki/` structure. If no guide exists for the relevant system, create one or add a `## Gotchas` section to the closest existing guide. Update `docs/wiki/DIRECTORY_GUIDE.md` if you create a new guide.

**Judgment call:** When in doubt, migrate rather than discard — the cost of a slightly long wiki page is lower than losing a hard-won implementation insight. But be honest: pure task-state entries with no pattern content should be discarded, not padded into artificial wiki prose.
