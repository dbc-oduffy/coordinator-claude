# Phase 3d Specialist Assembler Prompt

Standing Sonnet worker that turns the Cross-Repo Archive Specialist Branch's
`cross_repo_dispositions:` scratch output into Phase 3d-shaped deletion-manifest rows.
Codifies the mechanism `agent-prompts/cross-repo-archive-specialist.md` §
"Consumption downstream" and `PIPELINE.md § Phase 3d` claim exists — without this
template nothing mechanical performs that step, and the parse of scratch files into
manifest rows falls back to a hand-written ad-hoc brief. This is the standing template,
same as every other phase in this pipeline.

**Model:** Sonnet. **Dispatch:** Single agent (or sharded to match however many
Cross-Repo Archive Specialist shards ran this pass — see `cross-repo-archive-specialist.md`
§ Sharding; one assembler instance per specialist shard, or one assembler reading all
shard outputs at once for a small shard count — coordinator's call, same threshold logic
as the specialist's own sharding gate). **Runs:** after the Cross-Repo Archive Specialist
Branch completes, before or in parallel with Phase 3d's own dispatch — its output is
one more scratch-path input Phase 3d folds in, exactly like a Phase 1 scanner output.
**Dispatched only when the Cross-Repo Archive Specialist Branch ran this pass** — omit
entirely on a run without `cross-repo/archive/` cohort activity.

## Dispatch prompt

```
You are the Phase 3d specialist assembler for an artifact-distillation run. Your job
is to read the Cross-Repo Archive Specialist Branch's classified output and turn it
into Phase 3d deletion-manifest rows — the same YAML shape `agent-prompts/phase-3d.md`
produces, so Phase 3d can splice your rows in verbatim without re-deriving anything.

**Your assigned specialist scratch files:** ([ASSIGNED_COUNT] total memo entries across
all files — this is your ground truth for the integrity check in step 3 below)
[SPECIALIST_SCRATCH_PATHS — full paths to cross-repo-archive-specialist scratch output,
one per shard if the specialist branch was sharded]

## Task

1. **Read every assigned specialist scratch file in full.** Each opens with a
   `schema_version: 1` frontmatter block carrying `assigned_count:`,
   `cross_repo_dispositions:` (a list of `{memo_path, classification, commitment_ledger_ref,
   extraction_target, reason}` entries), and `dropped_memos:` (entries the specialist
   itself could not classify — see step 4). Read the schema in
   `agent-prompts/cross-repo-archive-specialist.md` § Output schema if anything here is
   ambiguous; do not guess at field names.
2. **Classify each `cross_repo_dispositions:` entry into exactly one bucket.**
   **Legal `classification:` values — exactly these three, no others:**
   `ROUTINE` | `COMMITMENT_OPEN` | `BOUNDARY_RATIFICATION`. If a scratch file's
   `classification:` field reads anything other than one of these three literal
   strings, that is not a fourth bucket to invent a home for — treat it exactly like
   the schema-violation case in the Rules section below (add it to `unresolved:` with
   the literal value you saw; do not guess, do not paraphrase it into one of the three).
   - `classification: ROUTINE` → emit a Phase 3d `deletions:` row:
     ```yaml
     - artifact_path: <memo_path>
       disposition: DELETE
       reason: <the entry's reason: field, verbatim>
       source_nugget_ids: []
     ```
     Do not paraphrase or improve the specialist's `reason:` — carry it through unchanged
     (it is the audit trail a PM reviews at Phase 4).
   - `classification: COMMITMENT_OPEN` → do NOT emit a `deletions:` row. Instead, add
     `<memo_path>` to a top-level `excluded_memo_paths:` list — this is the exclusion set
     Phase 5's exclusion-set integrity check (`PIPELINE.md § Phase 5` step 5,
     `cross_repo_dispositions:` expansion) cross-references against the final deletion
     set. An open commitment is never a deletion row, regardless of how the specialist's
     `reason:` reads.
   - `classification: BOUNDARY_RATIFICATION` → do NOT emit a `deletions:` row (these are
     not Phase 3d's concern — they route to Phase 3c/Phase 5 apply-agents per
     `cross-repo-archive-specialist.md` § Consumption downstream). Add `<memo_path>` to a
     top-level `boundary_ratification_paths:` list purely so the integrity check in step 3
     can account for it without emitting a phantom deletion.
3. **Self set-diff (mandatory, before you write anything).** Sum `assigned_count:` across
   every specialist scratch file you read. This total MUST equal:
   `(rows emitted to deletions:) + (entries in excluded_memo_paths:) +
   (entries in boundary_ratification_paths:) + (entries you are forced to carry forward
   as unresolved, per step 4)`.
   - Match → proceed to Output Location below.
   - Mismatch → do NOT return short or silently drop the discrepancy. Recount by hand,
     find the missing entry, and either place it in the correct bucket or — if a specific
     entry's classification is genuinely ambiguous from the scratch file content — write
     it to an `unresolved:` list at the top level with the memo_path and the reason you
     could not place it, and say so plainly in your summary. A memo silently disappearing
     between the specialist's output and yours is a second-order version of the exact
     failure class the specialist's own self set-diff (its Task step 4) exists to prevent
     — do not reintroduce it one hop downstream.
4. **Carry forward the specialist's own `dropped_memos:` (if any) unchanged** — do not
   attempt to classify a memo the specialist itself flagged as unclassifiable. Echo each
   dropped-memo path and reason into your own output's `dropped_memos:` list verbatim, and
   include its count in the integrity total in step 3 (a dropped memo is neither a deletion
   row nor an exclusion — it is its own accounted-for bucket).

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with the
fenced YAML block from § Output schema below, written to: [SCRATCH_PATH]

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <the fenced YAML
block per § Output schema>)`. Prose commentary around the fenced block is fine; the
fenced block itself is the deliverable. Returning your classifications inline in your
reply — as prose, as a table, or as anything other than the exact fenced `---`-delimited
YAML shape in § Output schema — is **not a stylistic variation; it is a failed return**,
identical in effect to not writing the file at all. The coordinator reads the fenced
block from disk, not your conversational reply.

Then return a brief summary (3-5 lines) confirming: file written, total entries consumed
(sum of assigned_count across your inputs) vs. rows emitted vs. excluded vs.
boundary-noted vs. dropped/unresolved — these must sum to the total, per the integrity
check in step 3 — and name any `unresolved:`/`dropped_memos:` entries.

The coordinator reads your full output from disk. Do NOT return it in conversation.

## Output schema

```yaml
---
schema_version: 1
total_entries_consumed: <int — sum of assigned_count across every specialist scratch
                          file you read; this is the integrity-check denominator>
deletions:
  - artifact_path: cross-repo/archive/<date>-<example-memo>.md
    disposition: DELETE
    reason: <specialist's reason:, verbatim>
    source_nugget_ids: []
excluded_memo_paths:
  - cross-repo/archive/<date>-<open-commitment-memo>.md
boundary_ratification_paths:
  - cross-repo/archive/<date>-<boundary-decision-memo>.md
dropped_memos: []   # carried forward verbatim from any specialist scratch file's own
                     # dropped_memos: list — never re-attempted, never silently omitted
unresolved: []       # non-empty only if this assembler itself could not place a
                     # classified entry into one of the three buckets above; each entry
                     # is {memo_path, reason}
---
```

`total_entries_consumed` MUST equal `len(deletions) + len(excluded_memo_paths) +
len(boundary_ratification_paths) + len(dropped_memos) + len(unresolved)` — this is the
mechanical check the coordinator runs without re-summing every specialist shard's
`assigned_count:` by hand.

## Rules

- **Never re-derive a classification.** The specialist already did the commitment-closure
  and boundary-ratification judgment work; your job is mechanical translation into Phase
  3d's row shape, not a second opinion. If a `classification:` value is anything other than
  `ROUTINE`/`COMMITMENT_OPEN`/`BOUNDARY_RATIFICATION`, that is a specialist-schema violation
  — do not guess a bucket, add it to `unresolved:` with the literal value you saw.
- **`reason:` fields pass through unchanged.** Do not summarize, shorten, or "clean up" the
  specialist's prose — it is the PM-facing audit trail at the Phase 4 gate.
- **Do not touch `deletion_groups:`.** This assembler only ever emits per-memo `deletions:`
  rows — cross-repo archive memos are never large enough a cohort to warrant the
  grouped-by-reference shape Phase 3d uses for bulk EPHEMERAL clusters (`agent-prompts/phase-3d.md`
  § Output-budget self-check). If a future run's cohort grows large enough to need grouping,
  that is a plan-level change to this prompt, not an in-flight agent decision.
- **Never delete, move, or edit `cross-repo/archive/*.md` files, or the specialist's own
  scratch files.** Read-only on both; your only write is [SCRATCH_PATH].
- **Never open, close, or edit `cross-repo-commitments` ledger entries.** Same boundary the
  specialist itself observes — flagging is upstream of you; closing commitments is not this
  pipeline's job at all.

## Out-of-scope actions (this assembler)

Inherits the pipeline-wide "Out-of-scope actions for all dispatched agents" block
(`commands/distill.md` § top-of-file). No `gh pr create`/`gh pr merge`/`git push origin
main`/`gh release create`, no direct commit to `main`, no further dispatch.
```

## Consumption downstream

Phase 3d's main dispatch (`agent-prompts/phase-3d.md`) receives this assembler's
`[SCRATCH_PATH]` as its `[CROSS_REPO_DISPOSITIONS_PATH]` fill-in (`PIPELINE.md § Phase 3d`
dispatch bullet list). Because this assembler already emits rows in Phase 3d's own
`deletions:` shape, Phase 3d's agent splices them into its own manifest verbatim — it does
not re-parse the raw specialist `cross_repo_dispositions:` YAML at all. `excluded_memo_paths:`
and `boundary_ratification_paths:` are not deletion rows and are not spliced in; they exist
so the assembler's own integrity check (step 3 above) and Phase 5's exclusion-set
cross-check (`PIPELINE.md § Phase 5` step 5) have a name for every entry the assembler
accounted for.
