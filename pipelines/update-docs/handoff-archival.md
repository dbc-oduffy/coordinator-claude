---
name: handoff-archival
description: "Archive superseded handoffs (chain-aware) and PM-directed handoffs from state/handoffs/ to archive/handoffs/. This pipeline's Step 2 is the lineage-predecessor residual backstop — it archives a predecessor only when an active successor still references it (predecessor: frontmatter or Continuing from), never a general terminal sweep. Consumed-handoff archival at large is now handled natively by the boot sweep (fleet.archive_completed_handoffs / sweep-boot.py, fired unconditionally from session.boot_sweep at every SessionStart), which archives a consumed predecessor promptly once it has a live succession child (predecessor: / additional_predecessors:), excluding forked_from children; /workstream-complete Step 2.7 and /handoff chain-archival (fallback-only) also contribute. Deployment-axis archival (deployment_state: shipped) is handled by bin/sweep-shipped-handoffs.py invoked from /workday-start Step 1.47."
version: 3.2.0
---

# Handoff Archival

**Purpose under the split-pickup-archival lifecycle:** this pipeline serves two narrowed roles:

1. **Supersession archival** — chain-aware pass: when a successor handoff names a predecessor (via `predecessor:` frontmatter or a legacy `Continuing from` body reference), archive the predecessor.
2. **PM-direct archival** — when the PM explicitly names a handoff for archival.

Consumed-handoff archival is no longer this pipeline's responsibility. The surfaces that own it:
- **The boot sweep** (`fleet.archive_completed_handoffs` via `sweep-boot.py`, fired unconditionally from `session.boot_sweep` at every SessionStart): natively archives a `consumed` predecessor the moment it has a live succession child — named via `predecessor:` / `additional_predecessors:` on a live handoff — with no `--exclude` needed. `forked_from` children are exempt: a spinoff is a cadet branch and does not retire its origin. This is now the primary archiver for the common case; this pipeline's Step 2 covers only the residue it doesn't reach.
- **`/handoff` chain-archival — fallback only** (`skills/handoff/SKILL.md` Step 1, chain-archival paragraph): `/handoff` presumes the boot sweep wins and does not eagerly archive by default; the guarded `housekeeping.cycle --exclude` native call (direct `cc_invoke.route_mutation`, formerly `coordinator-handoff-archive.sh --exclude`) runs only on an install whose claude-klabauter seam is absent, where the boot sweep has no native route.
- **`/workstream-complete` Step 2.7** (`skills/workstream-complete/SKILL.md`): when a session ends without a successor handoff, Step 0 locates the consumed handoff via `claimed_by:` (the modern field, preferred) falling back to `consumed_by:` matching this session, and Step 2.7 stamps/archives it.
- **`/workday-start` Step 1.47 — deployment-axis sweep** (`bin/sweep-terminal-handoffs.py`; it subsumed the deleted `sweep-shipped-handoffs.py`): the on-demand drain, keyed on the DEPLOYMENT axis (`deployment_state: shipped` + resolvable `shipped_in:`), NOT the consumption axis the above surfaces use. Archives handoffs that have shipped but were never consumed through the standard lifecycle path. Emits a one-line summary; SHA-resolution failures are surfaced as warnings rather than silent drops.

**The cascade backstop is on-demand, and deliberately not in the list above.** `deliverable.cascade_backstop_sweep` (claude-klabauter, `coordinator_core/ops/cascade_backstop_sweep.py`) re-derives what the terminal cascade (fired by `plan-status-transition stamp-implemented`) would have produced for every terminal deliverable on disk, generalizing the trigger from "just stamped this run" to "terminal on disk, whenever that happened" — it is the diagnostic for a *missed* cascade event. It is report-only by ratification — the op's own module docstring cites the engine-side decision recording that choice and the sole trigger it may be reversed through and has **no composer, by design**: no ceremony, hook, or commit-path leg invokes it. An operator (or a ceremony that suspects a missed cascade) shells out to it and reads the divergence list; a divergence it finds is discharged by re-running the real trigger (`plan-status-transition stamp-implemented`, or the handoff-conclusion leg), never by the sweep. It is named here because this section is the archival-mechanism inventory and its absence from an inventory reads as an omission rather than a choice.

> **Negative-spec (v3.0.0):** This pipeline no longer reads or writes the `<!-- consumed: YYYY-MM-DD -->` marker — deprecated. This pipeline no longer surfaces `status: consumed` / `deployment_state: in_flight` as stuck-mid-pickup warnings — the boot sweep (`sweep-boot.py`) handles orphan recovery silently. This pipeline no longer gates on `pickup_ready: true` — the field is a positive pickup-authorized signal, not a veto. The consumption signal is `claimed_by:` (falls back to legacy `consumed_by:` for corpus predating the rename) populated in frontmatter; archival is confirmed by file presence in `archive/handoffs/`.

## Overview

Both directories are git-tracked:

- **Active handoffs:** `state/handoffs/*.md` — available for `/workstream-start` and `/pickup`
- **Archived handoffs:** `archive/handoffs/*.md` — post-pickup or post-supersession; paper trail

**Skip entirely if no handoff files exist.**

## Archival Policy

The two paths this pipeline handles:

1. **Supersession** — a successor handoff explicitly continues from a predecessor (chain-aware pass)
2. **PM direction** — the PM explicitly says to archive specific handoffs

**Not handled here:** pickup archival (atomic in `/pickup` itself); age-based archival (never — un-picked-up handoffs signal deferred work, not staleness); `/distill` deletion (separate pipeline).

## Steps

1. Check `state/handoffs/` for `.md` files

2. **Chain-aware archival (supersession pass) — lineage-predecessor residual backstop.**

   **Scope discipline: this step is the LINEAGE-PREDECESSOR backstop, not a general terminal sweep.** It archives a predecessor *only* when an active successor still references it (via `predecessor:` frontmatter or a legacy `Continuing from` body link) — i.e. it closes the narrow "successor absorbed this predecessor's context but the predecessor file is still sitting in `state/handoffs/`" gap. It does **not** attempt to catch terminal handoffs in general — handoffs with no active successor pointing back at them are out of this step's scope by design. That job belongs to `bin/sweep-terminal-handoffs.py`, invoked from `/workday-start` Step 1.47 — not to this pipeline. **The owner of the abandoned-session case is `/workday-complete`**, whose `reap-orphaned-in-flight-handoffs` + `handoff-housekeeping` pair reclaims dead-holder claims and archives everything terminal in one batch — Step 1.47 is the same job on demand. The boot sweep that used to also fire this class (`fleet.archive_completed_handoffs` via `session.boot_sweep`) was killed; `sweep-boot.py` now carries `never dispatches an op` as a negative spec, pinned by `test_sweep_boot.py`. Do not cite the boot sweep as owner, and do not author a new sweep on the belief that none exists.

   <!-- Negative-spec: do not re-file "Phase 8 missed ~27 terminal handoffs" against this step. Those handoffs had no active successor referencing them — by definition outside this lineage-predecessor step's scope, not a miss. They were sweep-shipped-handoffs.sh's job all along; the reason they lingered is that script's now-retired mtime veto (deleted under the archival-option-a-cutover, C1), not any gap here. -->

   Scan all active handoffs for a lineage reference to a predecessor via **either** signal: the **`predecessor:` frontmatter field** (the canonical modern signal — most current successors carry only this and no body preamble, so keying on `Continuing from` alone misses them) **or** the legacy `_Continuing from [filename]:` / `Continuing from [filename]` body pattern in the `## What Was Accomplished` section. If the referenced predecessor file is still in `state/handoffs/`, archive it via the canonical guarded archiver — `housekeeping.cycle` mode `stamp_shipped`, `exclude=[<successor>]`, `successor_path=<successor's own path>` (direct `cc_invoke.route_mutation` call, formerly `bin/coordinator-handoff-archive.sh <predecessor> --exclude <successor>`) — which runs `handoff-has-live-children.py` (so a predecessor still named by *another* live handoff as a fan-in/fan-out parent is correctly retained, not archived) and `--exclude`s the successor so it is not counted as its own predecessor's live child. The successor has absorbed both the predecessor's context (via the preamble/lineage) and its unresolved obligations (via the `## Carried Forward` section); the predecessor is fully superseded. **Policy, not procedure:** the SHA tagged onto this archival write genuinely belongs to the successor (`kind="successor"`), not a self-derivation from the predecessor's own scope — so the successor's own path is what this step hands the op, and `successor_path` is the op's own resolution of that path into a sha, never a `git log` this step's reader performs. When the successor genuinely has no resolvable commit yet (not committed to this worktree), that is the op's own honest no-op, surfaced in its own return payload — not a branch this step's reader evaluates. **This step is now only the residue backstop the boot sweep doesn't reach** — the boot sweep (`fleet.archive_completed_handoffs` via `sweep-boot.py`) fires unconditionally at every SessionStart and natively archives a consumed predecessor with a live succession child, no `--exclude` needed; what's left here is a `forked_from`-pinned parent (out of the boot sweep's heir-branch scope by design — a spinoff doesn't retire its origin) and installs without the claude-klabauter seam (see `skills/handoff/SKILL.md` Step 1).

   **Why this stays a DoE-authored doc-edit, not a claude-klabauter engine change.** The archival *operation* (the mechanical move, the sweep script, the mtime bookkeeping) is engine — claude-klabauter's surface — but *lineage policy* (which predecessor gets archived, on what reference signal, with what live-children guard) is contract — DoE's surface. This Phase 8 prose is lineage policy, so it is edited here, in DoE, not delegated to the engine repo.

   **Single-predecessor rule.** A successor names exactly one predecessor — the one it explicitly continues from. If you find a successor that names no predecessor, it has none; do not guess one for it from timestamp adjacency. If a `Continuing from` reference points at a handoff that is itself an active sibling rather than a true ancestor (e.g., concurrent workstream, different machine, no actual hand-off occurred), STOP and surface to the PM rather than archiving — adjacency is not ancestry. Combining two predecessors into one successor only happens by explicit PM direction at session start, and shows up as a successor that names *both* predecessors with the merge intent in its preamble.

3. **Report remaining handoffs:** List any handoffs still in `state/handoffs/` with their age and heading. Do not archive them — they remain active until consumed via `/pickup`, superseded, or the PM directs otherwise.

4. Do NOT delete archived handoffs — they are the paper trail. Deletion is `/distill`'s responsibility (Phase 4 of the lifecycle plan), gated by extraction-artifact guards.

## Orphan-Promotion Handoffs as Live Specs

Orphan-promotion handoffs (handoffs that promote in-flight work into a spec for another session to continue) function as **live specs** — concurrent execution can outpace commit cadence. Don't archive them on a "looks consumed" hunch; require an explicit consumption signal (successor's `Continuing from`, /pickup having moved them to `archive/handoffs/`, or PM direction). The `pickup_ready: true` veto above is the mechanical guard for fresh orphan-promotions.

## `.gitignore` Check

Verify that `tasks/` is NOT in `.gitignore`. If it is, warn the user — active handoffs must be tracked.
