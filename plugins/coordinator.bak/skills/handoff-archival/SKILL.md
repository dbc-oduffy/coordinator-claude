---
name: handoff-archival
description: "Archive consumed handoffs — moves superseded or PM-approved handoffs from tasks/handoffs/ to archive/handoffs/. Invoked by /update-docs (Phase 8) or standalone. Does NOT auto-archive based on age alone."
version: 1.1.0
---

# Handoff Archival

## Overview

Move consumed handoffs from the active directory to the archive (both git-tracked — the archive is the paper trail):

- **Active handoffs:** `tasks/handoffs/*.md` — available for `/session-start` pickup
- **Archived handoffs:** `archive/handoffs/*.md` — consumed, kept for historical reference

**Skip entirely if no handoff files exist.**

## Archival Policy

Handoffs are only archived when there is a clear signal they've been consumed:

1. **Supersession** — a successor handoff explicitly continues from a predecessor (chain-aware pass)
2. **Pickup** — a session picked up the handoff via `/pickup`, which marks it consumed
3. **PM direction** — the PM explicitly says to archive specific handoffs
4. **`/distill`** — knowledge extraction pipeline, which may delete after PM approval

**Age alone is NOT a reason to archive.** A 2-week-old handoff that nobody picked up is a signal that work was deferred, not that the handoff is stale. Surfacing old handoffs is `/workday-start`'s job; archiving them requires a consumption signal.

## Steps

1. Check `tasks/handoffs/` for `.md` files
2. **Chain-aware archival (supersession pass):** Scan all active handoffs for `Continuing from` references (look for the pattern `_Continuing from [filename]:` or `Continuing from [filename]` in the `## What Was Accomplished` section). If the referenced predecessor file is still in `tasks/handoffs/`, archive it immediately — the successor has absorbed both the predecessor's context (via the preamble) and its unresolved obligations (via the `## Carried Forward` section). The predecessor is fully superseded.
3. **Pickup-consumed pass:** Check for handoffs marked as consumed by `/pickup`. Look for a `<!-- consumed: YYYY-MM-DD -->` comment in the file (added by `/pickup` when it loads a handoff). Archive these — the work has been picked up and continued.
4. **Report remaining handoffs:** List any handoffs still in `tasks/handoffs/` with their age and heading. Do not archive them — they remain active until consumed or the PM directs otherwise.
5. Do NOT delete archived handoffs — they are the paper trail for why things are written the way they are

## `.gitignore` Check

Verify that `tasks/` is NOT in `.gitignore`. If it is, warn the user — active handoffs must be tracked.
