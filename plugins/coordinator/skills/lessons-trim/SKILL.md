---
name: lessons-trim
description: "Periodic maintenance of lessons files — trims stale entries, merges duplicates, and deletes exhausted feature-scoped files. Implements the 'Periodic trim' rule from CLAUDE.md's Self-Improvement Loop. This skill should be used when lessons.md is getting long, when a feature is complete and its lessons file should be cleaned up, or when periodic housekeeping is needed. Invoked by /update-docs (Phase 6) or standalone."
---

# Lessons Trim

## Overview

Review `tasks/lessons.md` (global) and any `tasks/<feature>/lessons.md` files. This is the periodic safety net described in the Self-Improvement Loop guidelines in CLAUDE.md.

**Discovery:** Find feature-scoped lessons files via `tasks/*/lessons.md` (glob). Each match is a feature-scoped file. Global lessons live at `tasks/lessons.md` (no subdirectory).

**Skip if no lessons files exist.**

## Steps

**For each lessons file:**

1. Read the file and count entries/lines
2. **Remove** entries that:
   - Were specific to a completed phase or one-off bug (no future recurrence)
   - Are now encoded in code, scripts, CLAUDE.md, or MEMORY.md (redundant)
   - Haven't been relevant in 2+ weeks (stale)
   - Document "what happened" rather than a reusable pattern
3. **Merge** entries that cover the same topic into a single tighter entry
4. **Preserve** entries that are still actively saving time or preventing repeated mistakes
5. If a feature-scoped lessons file (`tasks/<feature>/lessons.md`) relates to completed work and all entries are either stale or promoted to the global file, delete it

**Judgment call:** When in doubt, keep the entry. The cost of a slightly long file is lower than losing a lesson that would have prevented a future mistake. But be honest — most one-off debugging notes don't belong here.
