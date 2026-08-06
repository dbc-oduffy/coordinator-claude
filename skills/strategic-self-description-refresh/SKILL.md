---
name: strategic-self-description-refresh
description: "Reconcile a claude-klabauter self-description draft against the ratified one; never auto-commits."
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
---

# Strategic Self-Description Refresh

> **Reference surfaces.** Schema: `coordinator/schemas/strategic-self-description.schema.json`.

## Purpose

Reconciles the per-repo canonical strategic self-description
(`state/strategic/self-description.yaml`) against a machine-generated draft
(`state/strategic/self-description.draft.yaml`), when one is present, through a human ceremony gate.
Generation SEEDS curation — it never auto-commits over human-ratified content. This skill is the
**ceremony gate itself**: the point where a generated observable-field draft either gets ratified
into the canonical file (per-field, provenance-marked) or is left for the human to curate directly.

## When to Use

- **Nudged from `/workweek-complete`** (DEC-6 cadence seam) — the weekly ceremony PROMPTS the EM to
  run this skill; it does not fire itself. See § Cadence semantics below.
- PM or EM directly invokes it — "refresh the strategic self-description", "reconcile the strategic
  draft", "ratify the strategic self-description".
- A draft file (`state/strategic/self-description.draft.yaml`) appears on disk (e.g. after a claude-klabauter
  generation run) and the EM notices it unreconciled.

## Non-goals — Out of scope

- **Does not build claude-klabauter's generators.** This skill *consumes* a draft claude-klabauter already emitted at
  `state/strategic/self-description.draft.yaml`; it does not compute version highlights from commit
  history, competitor deltas from example-market-data-repo signals, or any other observable-field
  derivation. That is claude-klabauter's leg (plan `Out of scope` § claude-klabauter leg).
  <!-- Negative-spec: do not add generation logic here even if it would be convenient — the seam is
  the draft file, not a shared library or in-skill heuristic. -->
- **Does not build the rag query surface** or any consolidation/harvest index over this file. Per-repo
  emission only, per the Fleet Producer Contract.
- **Does not author handoffs, spinoffs, or any `kind:` stub.** No spinoff-schema applies here — this
  skill's artifact surface is exactly `state/strategic/self-description.yaml` (write) and
  `state/strategic/self-description.draft.yaml` (read, and post-ratify archive/clear — see § Steps).
- **Not a scheduler or cron.** `/workweek-complete` mentions this skill as a nudge (a discovery-surface
  cross-reference), not a trigger mechanism. There is no background job, no `CronCreate` entry, no
  automated firing anywhere in this skill's design — the human running the ceremony IS the gate. If
  you find yourself reaching for `CronCreate`/`RemoteTrigger` to "automate" this skill, that is a scope
  violation of DEC-6; stop.
- **Does not write the canonical file with unreconciled machine output.** See § Non-clobber invariant.
- **Does not touch cockpit's or claude-klabauter's own repos.** This skill operates only on the repo it runs in
  (per-repo emission, per DEC-1).

## Destructive-action prohibition

This skill is **write-capable** on `state/strategic/self-description.yaml` (the canonical,
human-ratified artifact) and on `state/strategic/self-description.draft.yaml` (the generated,
disposable draft). Observe:

- **NEVER overwrite `self-description.yaml` with draft content the human has not seen and confirmed
  field-by-field in this session.** A field-level diff-and-confirm step (§ Steps, Step 3) is mandatory
  before any write to the canonical file — no bulk `cp draft canonical`, no silent merge.
- **NEVER mark a field `provenance: curated` or `provenance: asserted` without an explicit human
  decision in this session.** Only `provenance: generated` may be carried forward from the draft
  without a human utterance, and only into a field the human has not chosen to override.
- **NEVER delete or truncate `self-description.yaml`.** If the canonical file does not yet exist,
  this skill creates it fresh (via the C3 authoring surface / `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type
  strategic-self-description`) — it does not fabricate a canonical file's absence as license to
  bulk-write unreviewed content.
- **The draft file may be archived or cleared ONLY after its fields have been reconciled into the
  canonical file (or explicitly rejected by the human) in this same session.** Do not delete an
  unreconciled draft — that destroys claude-klabauter's signal with no compensating write.
- **Never run this skill non-interactively / unattended.** If invoked in a context with no human able
  to answer the Step 3 diff-and-confirm prompts (e.g. a fully autonomous batch run), stop and report
  `blocked` rather than guessing at field dispositions.

## Non-clobber invariant

**The human ratify gate writes the canonical file. The generation draft never does, and the direction
never reverses.** Concretely:

- `state/strategic/self-description.draft.yaml` is claude-klabauter-owned content, `provenance: generated`
  observable fields ONLY (proposal-scoped: things like `version_highlights`, competitor-signal
  candidates). Claude-Klabauter **never** writes the canonical file, and **never** writes the human-curated
  `competitors[].relationship` enum value (a judgment field, not an observable one) — even inside the
  draft, that field is absent or left for human curation.
- This skill reads the draft, proposes each `provenance: generated` field to the human as a
  diff-against-canonical, and only a human "yes, ratify" turns that proposal into a canonical write.
- If the human instead types a new value at the ceremony (overriding or hand-authoring), that field's
  provenance in the canonical file becomes `curated` (an editorial judgment was exercised) or
  `asserted` (a bare factual claim with no observable signal and no editorial judgment — e.g. a
  version label), never `generated` — `generated` is reserved for values that survived to the
  canonical file unedited from a machine draft.

## Draft-present-triggers-consume

1. Check for `state/strategic/self-description.draft.yaml` at session start.
2. **If present:** this is the primary path — walk § Steps below, reconciling the draft's
   `provenance: generated` fields against the canonical file one field at a time.
3. **If absent:** prompt the human directly for curation — walk the canonical file's existing fields
   (or scaffold a fresh one via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type strategic-self-description` if none
   exists yet) and ask the human what changed since the last refresh. There is nothing to reconcile;
   this is a direct curation pass.

## Steps

1. **Locate the canonical file.** `state/strategic/self-description.yaml`. If absent, scaffold via
   the C3 authoring surface (`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type strategic-self-description`) before
   proceeding — do not hand-author a bespoke skeleton here; the scaffold is schema-validated on write.
2. **Locate the draft (if any).** `state/strategic/self-description.draft.yaml`. Branch per
   § Draft-present-triggers-consume.
3. **Per-field diff-and-confirm (draft path).** For each `provenance: generated` field in the draft
   that differs from the canonical file's current value:
   - Show the human the old value, the new (draft) value, and the field's semantic role.
   - Ask: ratify (write the draft value, `provenance: generated`), override (human types a
     replacement, `provenance: curated` or `asserted` per § Non-clobber invariant), or skip (leave
     canonical value untouched this cycle).
   - Human-curated-only fields (e.g. `competitors[].relationship`, `vision`) are NEVER auto-proposed
     from the draft even if present there by mistake — flag and skip, do not silently ratify.
4. **Write the canonical file** with the reconciled field set, each field carrying its resolved
   provenance marker. Validate against `strategic-self-description.schema.json` before considering
   the write complete (schema validation is enforced at write time by the C3 authoring/validation
   surface — do not bypass it with a raw file write outside that path where avoidable).
5. **Archive or clear the draft** now that its fields are reconciled (moved to
   `state/strategic/self-description.draft.yaml.archived` or deleted, per repo convention — never
   left in place to be re-proposed stale next cycle).
6. **Report** which fields were ratified, overridden, or skipped, and the resulting provenance
   breakdown (counts of curated / generated / asserted) — this is the ceremony's audit trail.

## Cadence semantics — nudge, not scheduler (DEC-6)

`/workweek-complete` carries a discovery-surface mention pointing at this skill as the weekly refresh
seam. That mention is a **prompt to the EM**, not a trigger: workweek-complete does not invoke this
skill programmatically, does not gate its own completion on this skill running, and no cron/scheduler
anywhere fires this skill automatically. The human (PM or EM, at the ceremony) decides whether to run
it that week. This matches the generated-draft → human-ceremony-gate → curated design end to end: the
human is the gate at every step, including the step of deciding *whether to open the gate at all*.

## Discovery-surface integration

- Referenced from `coordinator/commands/workweek-complete.md` (Chunk C5) as the weekly nudge.

## Platform-vocabulary collision check

The invokable verb space here is "refresh" / "reconcile" / "ratify". Checked against existing
coordinator surfaces: `coordinator-doc-new` uses "scaffold"/"create"; `/update-docs` uses
"sync"/"maintain" for a different (docs-wide) surface; `/learn-lessons` uses "process"/"promote"; no
existing skill or CLI verb collides with "refresh the strategic self-description" or "reconcile the
strategic draft". No rename required.
