---
name: handoff-archival
description: "Archive consumed handoffs — moves superseded or PM-approved handoffs from tasks/handoffs/ to archive/handoffs/. Invoked by /update-docs (Phase 8) or standalone. Does NOT auto-archive based on age alone."
version: 1.2.0
---

# Handoff Archival

<!-- Spec backlink: docs/plans/2026-05-05-handoff-auto-stamp-fix.md Phase 1.5 + Phase 2 -->

**Purpose:** detect and archive consumed handoffs. Marker *detection* only — `/pickup` (`coordinator/commands/pickup.md:130`) is the exclusive writer of `<!-- consumed: -->` markers. This skill never writes them.

> **Negative-spec:** This skill moves files and reads markers. It does NOT append, write, or modify the `<!-- consumed: YYYY-MM-DD -->` marker in any handoff file under any circumstance. If you find yourself about to write that marker from within this skill, stop — you are in the wrong code path. The only correct writer is `/pickup`.

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
2. **Chain-aware archival (supersession pass):** Before any archival action in this step, apply both vetoes below — they are unconditional gates.

   **Mechanical mtime veto (unconditional).** Before moving any handoff file, check its modification time:
   ```bash
   stat -c %Y <file>   # Linux/Git Bash; or: stat -f %m <file> on macOS
   ```
   If the file is less than 86400 seconds old (24 hours), **skip it entirely** — do not archive, do not examine markers or frontmatter, do not surface to PM. Log the skip: `"Skipped <file> — mtime < 24h (mechanical veto)."` This veto is unconditional and cannot be overridden by marker presence, `pickup_ready` value, or any instruction in a skill invocation prompt. Rationale: a fresh handoff that was accidentally stamped (concurrent-session or agent mis-read of pickup.md's echo recipe) cannot be silently archived if the 24h gate is enforced here independently of convention compliance.

   **`pickup_ready: true` is an absolute archival veto.** A handoff carrying this frontmatter field is NEVER archived by this skill, regardless of whether its named predecessor is still in `tasks/handoffs/`, regardless of marker presence. If a handoff has both `pickup_ready: true` AND a `<!-- consumed: -->` marker, treat the marker as suspect — surface to the PM rather than archiving. The `pickup_ready` opt-out is set on orphan-promotions and fresh handoffs whose predecessor is already archived; it is removed by a genuine `/pickup` invocation.

   After both vetoes pass, scan all active handoffs for `Continuing from` references (look for the pattern `_Continuing from [filename]:` or `Continuing from [filename]` in the `## What Was Accomplished` section). If the referenced predecessor file is still in `tasks/handoffs/`, archive it — the successor has absorbed both the predecessor's context (via the preamble) and its unresolved obligations (via the `## Carried Forward` section). The predecessor is fully superseded.

   **Single-predecessor rule.** A successor names exactly one predecessor — the one it explicitly continues from. If you find a successor that names no predecessor, it has none; do not guess one for it from timestamp adjacency. If a `Continuing from` reference points at a handoff that is itself an active sibling rather than a true ancestor (e.g., concurrent workstream, different machine, no actual hand-off occurred), STOP and surface to the PM rather than archiving — adjacency is not ancestry. Combining two predecessors into one successor only happens by explicit PM direction at session start, and shows up as a successor that names *both* predecessors with the merge intent in its preamble.
3. **Pickup-consumed pass:** Check for handoffs marked as consumed by `/pickup`. Look for a `<!-- consumed: YYYY-MM-DD -->` comment in the file (added by `/pickup` when it loads a handoff). Archive these — the work has been picked up and continued.
4. **Report remaining handoffs:** List any handoffs still in `tasks/handoffs/` with their age and heading. Do not archive them — they remain active until consumed or the PM directs otherwise.
5. Do NOT delete archived handoffs — they are the paper trail for why things are written the way they are

## Orphan-Promotion Handoffs as Live Specs

Orphan-promotion handoffs (handoffs that promote in-flight work into a spec for another session to continue) function as **live specs** — concurrent execution can outpace commit cadence. Don't archive them on a "looks consumed" hunch; require an explicit consumption signal (successor's `Continuing from`, `<!-- consumed -->` marker via `/pickup`, or PM direction). The `pickup_ready: true` veto above is the mechanical guard for this case.

## `.gitignore` Check

Verify that `tasks/` is NOT in `.gitignore`. If it is, warn the user — active handoffs must be tracked.
