---
name: strategic-self-description-refresh
description: Reconcile a self-description draft against the ratified one.
version: 1.1.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
---

# Strategic Self-Description Refresh

> Schema: `coordinator/schemas/strategic-self-description.schema.json`.

## Purpose

Reconciles the canonical `state/strategic/self-description.yaml` against a generated draft
(`state/strategic/self-description.draft.yaml`) through a human ceremony gate. Generation SEEDS
curation — it never auto-commits over human-ratified content. Draft fields are ratified
per-field with provenance, or left for the human to curate.

## When to Use

- Nudged from `/workweek-complete` — a prompt, not a trigger; see § Cadence.
- PM or EM invokes it directly.
- A draft file appears on disk unreconciled.

## Out of scope

- **Does not build the generator.** Consumes an emitted draft; computes no version highlights or
  competitor deltas.
- No query surface or harvest index — per-repo emission only.
- **Authors no handoffs, spinoffs, or `kind:` stub.** Artifact surface is exactly
  `self-description.yaml` (write) and `self-description.draft.yaml` (read, post-ratify
  archive/clear).
- **Not a scheduler** — the human running the ceremony IS the gate. Reaching for
  `CronCreate`/`RemoteTrigger` is a scope violation — stop.
- Never writes the canonical file with unreconciled generated output (§ Non-clobber invariant).
- Operates only on this repo, never a sibling's self-description.

## Destructive-action prohibition

Write-capable on both the canonical and draft files. Observe:

- **NEVER overwrite `self-description.yaml` with draft content the human has not seen and
  confirmed field-by-field this session.** Field-level diff-and-confirm (Step 3) is mandatory —
  no bulk `cp draft canonical`, no silent merge.
- **NEVER mark a field `provenance: curated` or `asserted` without an explicit human decision
  this session.** Only `provenance: generated` may carry forward from the draft unconfirmed, and
  only into a field the human hasn't overridden.
- **NEVER delete or truncate `self-description.yaml`.** If absent, create fresh via Shape W
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
  `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.exe" --type strategic-self-description` —
  never treat a missing canonical file as license to bulk-write unreviewed content.
- **Archive/clear the draft ONLY after its fields are reconciled (or explicitly rejected) this
  same session.**
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
<!-- engine-gap: field=strategic_self_description.draft_diff producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
4. **Write the canonical file** with the reconciled set, each field's resolved provenance marker,
   schema-validated at write time via the authoring surface — never a raw file write outside it.
5. **Archive or clear the draft** now that its fields are reconciled (`.archived` suffix or
   delete, per repo convention) — never left in place to be re-proposed stale next cycle.
6. **Report** which fields were ratified/overridden/skipped and the resulting provenance
   breakdown (counts of curated/generated/asserted) — the ceremony's audit trail.

## Cadence semantics

**Weekly, at `/workweek-complete` Step 5, as a named line item** — not an advisory result. The
trigger is elapsed time, not judgment: newest `version_highlights[].date` older than 14d means
this skill runs that ceremony. Skipping is legal and needs a recorded reason on the spine;
silence is not a disposition.

That schedules the gate — it does not displace it. Nothing fires this skill automatically or
writes the canonical file without the Step 3 ratify pass. No human available: `blocked`,
recorded, not a generated write.

Known residual: detection is coupled to `/workweek-complete`; a repo whose ceremony skips weeks
gets no nudge.
