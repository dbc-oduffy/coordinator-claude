---
name: strategic-self-description-refresh
description: "Reconcile a self-description draft against the ratified one; never auto-commits."
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
---

# Strategic Self-Description Refresh

> Schema: `coordinator/schemas/strategic-self-description.schema.json`.

## Purpose

Reconciles the per-repo canonical strategic self-description
(`state/strategic/self-description.yaml`) against a generated draft
(`state/strategic/self-description.draft.yaml`), when present, through a human ceremony gate.
Generation SEEDS curation — it never auto-commits over human-ratified content. This skill is the
ceremony gate itself: a generated observable-field draft either gets ratified into the canonical
file (per-field, provenance-marked) or is left for the human to curate directly.

## When to Use

- Nudged from `/workweek-complete` (weekly cadence seam) — a prompt, not a trigger; see § Cadence.
- PM or EM directly invokes it ("refresh/reconcile/ratify the strategic self-description").
- A draft file appears on disk (e.g. after an engine generation run) and the EM notices it
  unreconciled.

## Out of scope

- **Does not build the generator that produces the draft.** Consumes a draft already emitted;
  does not compute version highlights or competitor deltas itself.
  <!-- Negative-spec: no generation logic here even if convenient — the seam is the draft file. -->
- Does not build a query surface or consolidation/harvest index — per-repo emission only.
- **Does not author handoffs, spinoffs, or any `kind:` stub.** Artifact surface is exactly
  `state/strategic/self-description.yaml` (write) and `self-description.draft.yaml` (read,
  post-ratify archive/clear).
- **Not a scheduler or cron** — no background job fires this skill; the human running the
  ceremony IS the gate. Reaching for `CronCreate`/`RemoteTrigger` to automate this is a scope
  violation — stop.
- Does not write the canonical file with unreconciled generated output (§ Non-clobber invariant).
- Operates only on the repo it runs in — never a sibling repo's own self-description.

## Destructive-action prohibition

Write-capable on both the canonical and draft files. Observe:

- **NEVER overwrite `self-description.yaml` with draft content the human has not seen and
  confirmed field-by-field this session.** Field-level diff-and-confirm (Step 3) is mandatory —
  no bulk `cp draft canonical`, no silent merge.
- **NEVER mark a field `provenance: curated` or `asserted` without an explicit human decision
  this session.** Only `provenance: generated` may carry forward from the draft unconfirmed, and
  only into a field the human hasn't overridden.
- **NEVER delete or truncate `self-description.yaml`.** If absent, create fresh via Shape W
  (`snippets/resolve-coordinator-bin.md`):
  `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.exe" --type strategic-self-description` —
  never treat a missing canonical file as license to bulk-write unreviewed content.
- **The draft may be archived/cleared ONLY after its fields are reconciled into the canonical
  file (or explicitly rejected) this same session.** Deleting an unreconciled draft destroys the
  generator's signal with no compensating write.
- **Never run unattended.** No human able to answer the Step 3 prompts → stop, report `blocked`.

## Non-clobber invariant

The human ratify gate writes the canonical file; the generated draft never does, and the
direction never reverses.

- The draft is generator-owned, `provenance: generated` observable fields ONLY
  (`version_highlights`, competitor-signal candidates). The generator never writes the canonical
  file, and never writes the human-curated `competitors[].relationship` (a judgment field) even
  inside the draft.
- This skill proposes each `provenance: generated` field as a diff-against-canonical; only a
  human "yes, ratify" turns it into a canonical write.
- A human-typed value (override or hand-authored) becomes `curated` (editorial judgment) or
  `asserted` (a bare factual claim, no observable signal, no judgment — e.g. a version label) —
  never `generated`, which is reserved for values that survived unedited from a generated draft.

## Steps

1. **Locate the canonical file** (`state/strategic/self-description.yaml`); scaffold via the
   `coordinator-doc-new --type strategic-self-description` command above if absent — schema-
   validated on write, never hand-authored.
2. **Locate the draft** (`self-description.draft.yaml`). Present → Step 3. Absent → prompt the
   human directly for curation over the canonical file's existing fields; nothing to reconcile.
3. **Per-field diff-and-confirm.** For each `provenance: generated` draft field differing from
   canonical: show old value, new value, semantic role. Ask ratify (write draft value,
   `generated`) / override (human types replacement, `curated` or `asserted`) / skip (leave
   untouched). Human-curated-only fields (`competitors[].relationship`, `vision`) are NEVER
   auto-proposed even if present in the draft by mistake — flag and skip.
<!-- engine-gap: field=strategic_self_description.draft_diff producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
4. **Write the canonical file** with the reconciled set, each field's resolved provenance marker,
   schema-validated at write time via the authoring surface — never a raw file write outside it.
5. **Archive or clear the draft** now that its fields are reconciled (`.archived` suffix or
   delete, per repo convention) — never left in place to be re-proposed stale next cycle.
6. **Report** which fields were ratified/overridden/skipped and the resulting provenance
   breakdown (counts of curated/generated/asserted) — the ceremony's audit trail.

## Cadence semantics

`/workweek-complete`'s mention is a prompt to the EM, not a trigger — it does not invoke this
skill programmatically or gate its own completion on it, and nothing fires it automatically. The
human decides whether to run it that week, including whether to open the gate at all.

## Discovery-surface integration

Referenced from `coordinator/commands/workweek-complete.md` (Chunk C5) as the weekly nudge.
