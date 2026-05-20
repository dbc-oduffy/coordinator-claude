---
name: handoff-archival
description: "Archive superseded handoffs (chain-aware) and PM-directed handoffs from tasks/handoffs/ to archive/handoffs/. Defense-in-depth 24h mtime backstop only. Consumed-handoff archival is handled by /handoff chain-archival, /session-end Step 2.7, and session-init.sh boot sweep."
version: 3.0.0
---

# Handoff Archival

<!-- Spec backlink: tasks/split-pickup-archival/plan.md § Edit 8 (v3.0.0; reverses archive-on-pickup half of docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md Phase 2d) -->

**Purpose under the split-pickup-archival lifecycle:** this pipeline serves two narrowed roles:

1. **Supersession archival** — chain-aware pass: when a successor handoff names a predecessor via `Continuing from`, archive the predecessor.
2. **PM-direct archival** — when the PM explicitly names a handoff for archival.

Consumed-handoff archival is no longer this pipeline's responsibility. The three surfaces that own it:
- **`/handoff` chain-archival** (`skills/handoff/SKILL.md` Step 1, chain-archival paragraph): when a session writes a successor handoff, the explicit predecessor is moved to `archive/handoffs/`.
- **`/session-end` Step 2.7** (`skills/session-end/SKILL.md`): when a session ends without a successor handoff, Step 2.7 archives any handoff whose `consumed_by:` matches this session.
- **`session-init.sh` boot sweep** (`hooks/scripts/session-init.sh`): at every session boot, consumed handoffs whose authoring session is dead are quietly archived — covering crash/restart/cross-machine orphans.

> **Negative-spec (v3.0.0):** This pipeline no longer reads or writes the `<!-- consumed: YYYY-MM-DD -->` marker — deprecated. This pipeline no longer surfaces `status: consumed` / `deployment_state: in_flight` as stuck-mid-pickup warnings — `session-init.sh` handles orphan recovery silently. This pipeline no longer gates on `pickup_ready: true` — the field is a positive pickup-authorized signal, not a veto. The new consumption signal is `consumed_by:` populated in frontmatter; archival is confirmed by file presence in `archive/handoffs/`.

## Overview

Both directories are git-tracked:

- **Active handoffs:** `tasks/handoffs/*.md` — available for `/session-start` and `/pickup`
- **Archived handoffs:** `archive/handoffs/*.md` — post-pickup or post-supersession; paper trail

**Skip entirely if no handoff files exist.**

## Archival Policy

The two paths this pipeline handles:

1. **Supersession** — a successor handoff explicitly continues from a predecessor (chain-aware pass)
2. **PM direction** — the PM explicitly says to archive specific handoffs

**Not handled here:** pickup archival (atomic in `/pickup` itself); age-based archival (never — un-picked-up handoffs signal deferred work, not staleness); `/distill` deletion (separate pipeline).

## Steps

1. Check `tasks/handoffs/` for `.md` files

2. **Chain-aware archival (supersession pass):** Before archiving any handoff, apply the defense-in-depth mtime veto below.

   **Mechanical mtime veto (unconditional, defense-in-depth).** Before moving any handoff file, check its modification time:
   ```bash
   stat -c %Y <file>   # Linux/Git Bash; or: stat -f %m <file> on macOS
   ```
   If the file is less than 86400 seconds old (24 hours), **skip it entirely** — do not archive, do not surface to PM. Log the skip: `"Skipped <file> — mtime < 24h (mechanical veto)."` This veto is unconditional and cannot be overridden by frontmatter or instruction. **Rationale:** defends against non-pickup paths (concurrent sessions, scripted moves, future skills) that might otherwise silently archive a fresh handoff. This backstop catches the paths that bypass the primary archival surfaces (`/handoff`, `/session-end`, `session-init.sh`).

   After the veto passes, scan all active handoffs for `Continuing from` references (look for the pattern `_Continuing from [filename]:` or `Continuing from [filename]` in the `## What Was Accomplished` section). If the referenced predecessor file is still in `tasks/handoffs/`, archive it — the successor has absorbed both the predecessor's context (via the preamble) and its unresolved obligations (via the `## Carried Forward` section). The predecessor is fully superseded.

   **Single-predecessor rule.** A successor names exactly one predecessor — the one it explicitly continues from. If you find a successor that names no predecessor, it has none; do not guess one for it from timestamp adjacency. If a `Continuing from` reference points at a handoff that is itself an active sibling rather than a true ancestor (e.g., concurrent workstream, different machine, no actual hand-off occurred), STOP and surface to the PM rather than archiving — adjacency is not ancestry. Combining two predecessors into one successor only happens by explicit PM direction at session start, and shows up as a successor that names *both* predecessors with the merge intent in its preamble.

3. **Report remaining handoffs:** List any handoffs still in `tasks/handoffs/` with their age and heading. Do not archive them — they remain active until consumed via `/pickup`, superseded, or the PM directs otherwise.

4. Do NOT delete archived handoffs — they are the paper trail. Deletion is `/distill`'s responsibility (Phase 4 of the lifecycle plan), gated by extraction-artifact guards.

## Orphan-Promotion Handoffs as Live Specs

Orphan-promotion handoffs (handoffs that promote in-flight work into a spec for another session to continue) function as **live specs** — concurrent execution can outpace commit cadence. Don't archive them on a "looks consumed" hunch; require an explicit consumption signal (successor's `Continuing from`, /pickup having moved them to `archive/handoffs/`, or PM direction). The `pickup_ready: true` veto above is the mechanical guard for fresh orphan-promotions.

## `.gitignore` Check

Verify that `tasks/` is NOT in `.gitignore`. If it is, warn the user — active handoffs must be tracked.
