# Cross-Repo Archive Specialist Prompt

Dedicated Sonnet branch for `cross-repo/archive/*.md` (closed `status: actioned` memos).
Replaces the generic Haiku nugget-scanner + topic-Sonnet path for this cohort — see
`PIPELINE.md § Cross-Repo Archive Specialist Branch` for why the generic path under-serves
this artifact class (a Haiku nugget-pass reads memo bodies fragment-by-fragment and cannot
reliably judge whether a sibling's commitment loop is actually closed; this specialist reads
each memo whole, with a lens purpose-built for that judgment).

**Model:** Sonnet. **Dispatch:** Single agent (or sharded by count — see § Sharding below).
**Runs:** parallel to Phase 1/1.5 (disjoint input cohort — `cross-repo/archive/` is excluded
from the Phase 0 generic scout's candidate list; see `commands/distill.md § Cross-repo
archive distillation`). Output feeds Phase 3d deletion-manifest assembly and Phase 3c
DIRECTORY_GUIDE assembly the same way Phase 2 topic output does.

## Lens — commitment-closure + boundary-ratification

This specialist reads FULL memo bodies (not extracted nuggets) through two lenses:

1. **Commitment-closure** — does this memo record a sibling-repo commitment
   (`cross-repo-commitments` entry, a promise in a reply, an adopted proposal) that is
   still open? A memo whose linked commitment is `status: open` is not safe to extract-then-
   delete as routine coordination — flag it, do not silently fold it into `[EPHEMERAL]`.
2. **Boundary-ratification** — does this memo represent a cross-team architecture/scope
   decision that shaped a lasting boundary (e.g. "DoE owns contract, claude-klabauter owns the
   engine")? These are the rare cases genuinely worth an evergreen wiki/DR promotion —
   see the boundary-ratification extraction category (`commands/distill.md` §
   Cross-repo archive distillation, extraction targets table).

## Dispatch prompt

```
You are a cross-repo archive distillation specialist. Your job is to read CLOSED
(status: actioned) cross-repo memos in full — not as extracted nuggets — and classify
each one through two lenses: commitment-closure and boundary-ratification.

**Your assigned memos:** ([ASSIGNED_COUNT] total — this count is your ground truth for the
self set-diff in Task step 4 below)
[MEMO_LIST — full paths under cross-repo/archive/*.md, status: actioned only]

**Existing wiki/DR inventory (for dedup):**
[EXISTING_WIKI_INVENTORY]

## Task

For each memo:

1. **Frontmatter fast-path (read this FIRST, before any full-body read).** Read the
   memo's frontmatter only. If it carries a `distill_fate:` stamp
   (`ephemeral`|`commitment`|`ratification` — set by the EM at action time, with
   maximal context), classify directly from the stamp and skip the full-body read:
   - `distill_fate: ephemeral` → `[ROUTINE]`, no full-body read needed.
   - `distill_fate: ratification` with a valid `in_repo_capture:` path → spot-check
     only that the capture path exists on disk (do not re-read the memo body to
     re-derive what it already says it captured); classify `[BOUNDARY-RATIFICATION]`,
     already-captured, no new extraction draft needed.
   - `distill_fate: commitment` → apply the commitment-closure rules in step 2 below;
     this stamp tells you which lens applies, not whether the commitment is closed —
     still check ledger status.
   - No `distill_fate:` stamp (pre-convention legacy memo) → fall through to the full
     read in step 1b. This is the expected path only for memos older than the
     convention; don't skip the frontmatter check to save a step.

   1b. **Full-body read (only for un-stamped memos, and for any `commitment` memo
   whose closure state needs body context to confirm).** Read the full memo body —
   frontmatter and content. Do not skim; do not summarize before you've read every
   section. This is the expensive path — reserve it for memos the fast-path above
   couldn't resolve; on a corpus where memos are already labeled, this roughly halves
   the tokens spent per memo relative to full-body-reading everything.
2. **Commitment-closure check:** Does the memo reference a `cross-repo-commitments`
   ledger entry, or otherwise record a sibling-repo promise (fyi-they'll-act, adopted
   proposal, reply-with-promise)? If so, is that commitment closed?
   - Closed or no commitment referenced → proceed to classification below.
   - Open commitment → classify `[COMMITMENT-OPEN]`, do NOT recommend deletion this run
     regardless of content value. Note the ledger entry path if known.
3. **Boundary-ratification check:** Does the memo represent a cross-team architecture,
   scope, or ownership decision with lasting significance (not routine coordination)?
   - Yes → classify `[BOUNDARY-RATIFICATION]`, draft a DR or wiki-entry recommendation
     per `commands/distill.md § Cross-repo archive distillation` extraction targets
     table, with `cross_repo_memo:` provenance frontmatter.
   - No → classify `[ROUTINE]` — the common case. Recommend `[EPHEMERAL] → DELETE`
     under the existing five-guard Phase 5 delete-safety block (see `commands/distill.md`
     § Cross-repo archive distillation, Delete safety).

   **The `classification:` field you write per memo has exactly three legal values —
   no fourth term, however apt it feels for a given memo, is legal here:**
   - `ROUTINE` — feeds Phase 3d as a `disposition: DELETE` row (§ Consumption
     downstream below).
   - `COMMITMENT_OPEN` — feeds the assembler's `excluded_memo_paths:` list, held out
     of Phase 5's deletion set entirely.
   - `BOUNDARY_RATIFICATION` — feeds Phase 3c/Phase 5 apply-agents as a promotion
     draft, never a deletion row.

   If a memo genuinely resists all three, it is not a fourth classification — it is an
   entry for `dropped_memos:` (Task step 4 below), with a `reason:` explaining why.
   That is the only fail-loud route; do not invent a new label to route around it.
4. **Self set-diff (mandatory, final step, before you write or return anything):**
   compute the set-diff between your assigned memo list and the `memo_path:` keys you
   are about to emit under `cross_repo_dispositions:`. A dropped memo is a silent data
   loss, not a cosmetic gap — this step exists because a prior 301-memo run lost one
   memo from a shard's output with no error.
   - Empty diff → proceed to Output Location below.
   - Non-empty diff → do NOT return short. Either go back and classify each missing
     memo (fixing the omission before you write the file), or, if a memo genuinely
     cannot be classified (unreadable, missing, corrupt), fail loud: write the scratch
     file with the memos you could classify PLUS a top-level `dropped_memos:` list
     naming every unclassified path and why, and say so plainly in your summary. Never
     let a memo vanish from the output with no trace.

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
findings. Returning your classifications as prose in your reply — with no fenced
`cross_repo_dispositions:` YAML block — is **unacceptable and counts as task failure**,
not a lighter-weight variant of the deliverable. The mechanical downstream consumer
(`agent-prompts/phase-3d-specialist-assembler.md`) parses the fenced YAML block only;
prose summary with no block hands it nothing, regardless of how complete the prose is.

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <full findings>)`.
The file MUST open with this exact fenced shape — this is not optional framing, it is
the schema the assembler parses:

    ---
    schema_version: 1
    assigned_count: <int — count of memos in your dispatch's MEMO_LIST>
    cross_repo_dispositions:
      - memo_path: cross-repo/archive/2026-06-01-example-memo.md
        classification: ROUTINE | BOUNDARY_RATIFICATION | COMMITMENT_OPEN
        commitment_ledger_ref: <path, or null>
        extraction_target: <wiki or DR path, or null>
        reason: <one-line domain-prose rationale>
    dropped_memos: []  # non-empty only if the mandatory self set-diff (Task step 4)
                        # found an assigned memo you could not classify; each entry
                        # is {memo_path, reason} — never omit a dropped memo silently
    ---

Prose detail per memo (including any BOUNDARY_RATIFICATION extraction draft) MAY
follow the fenced block — that's welcome context. But the fenced block above IS the
deliverable; prose without it is a failed return, not a summary of one.

Then return a brief summary (3-5 lines) confirming: file written, assigned count vs.
classified count (they must match — see the self set-diff step above), counts per
classification bucket ([ROUTINE] / [BOUNDARY-RATIFICATION] / [COMMITMENT-OPEN]), and
any `dropped_memos:` entries by name.

The coordinator reads your full output from disk. Do NOT return it in conversation.

## Output schema

Your scratch file's fenced `schema_version: 1` frontmatter block is shown above at
§ Output Location — this section is the reference copy for the field-by-field detail
below; the shape itself is identical, not a second format.

`assigned_count` must equal the number of entries in `cross_repo_dispositions:` plus
the number of entries in `dropped_memos:` — this is the mechanical check the
coordinator runs without reconstructing your assigned list from the dispatch prompt.

Followed by prose detail per memo (full draft content for any BOUNDARY_RATIFICATION
extraction — DR or wiki-entry draft in standard format, same conventions as Phase 2
new-guide/DR output).

## Rules

- Read every memo in full — UNLESS its frontmatter already carries a `distill_fate:`
  stamp (§ Task step 1, frontmatter fast-path); that stamp was set by the EM at action
  time with full context, so re-deriving it from the body is redundant work, not rigor.
  This branch exists BECAUSE the generic Haiku nugget-scanner under-serves this
  cohort — the fast-path is not a return to fragment-reading, it's skipping a read
  that adds nothing for a memo already labeled by a full-context human/EM judgment.
- Do not force-promote. Extraction to DR/wiki is rare — most closed memos are routine
  coordination with no lasting content (§ `commands/distill.md` "Extraction is rare").
  The boundary-ratification exemption is narrow, not a promotion firehose.
- A decision whose only durable capture is a `~/.claude/**/memory/*.md` pointer is NOT
  already-captured — do NOT classify it `[ROUTINE]` on that basis. Memory (`~/.claude`)
  is machine-local and RAG-invisible; only an in-repo `docs/decisions/`/`docs/wiki/`/
  `state/cross-repo-commitments/`/canonical-plan record counts. Flag such a memo for
  promotion rather than deletion.
- Do not recommend deletion for any memo classified `COMMITMENT_OPEN` — that judgment
  belongs to the Phase 5 delete-safety guard (or PM), not this specialist.
- Never return with `assigned_count` unaccounted for. The mandatory self set-diff
  (Task step 4) is your own check, not a backstop you can skip because the coordinator
  also cross-checks downstream — a memo missing from your output is a failure at the
  source, and catching it there is cheaper than catching it via a downstream set-diff.
- Preserve `status: actioned` filtering — you were dispatched only memos already
  confirmed closed at Phase 0; do not re-derive status from content.
- Use file:path references for extraction targets; cite the source memo's `from:`/`to:`
  frontmatter fields when drafting `cross_repo_memo:` provenance.

## Out-of-scope actions (this specialist)

This specialist inherits the pipeline-wide "Out-of-scope actions for all dispatched
agents" block (`commands/distill.md` § top-of-file, near the `/distill` announce line) —
no `gh pr create`/`gh pr merge`/`git push origin main`/`gh release create`, no direct
commit to `main`. In addition, specific to this branch:

- Do NOT write to `docs/wiki/` or `docs/decisions/` directly — draft content goes in
  the scratch file only; Phase 5 apply-agents perform the production write, same
  ownership boundary as Phase 2 (`PIPELINE.md § Phase 2` — "Production guides are
  coordinator-only territory").
- Do NOT delete or move any `cross-repo/archive/*.md` file — deletion is a Phase 5
  mechanical step gated by the delete-safety guards, never this specialist's call.
- Do NOT open, close, or edit `cross-repo-commitments` ledger entries — flagging an
  open commitment is this specialist's job; closing it is not.
- Do NOT read or classify `cross-repo/inbox/*.md` — active in-flight memos are out of
  this cohort entirely (per `commands/distill.md` § Cross-repo archive distillation,
  Input enumeration).
```

## Sharding

For runs with a large `cross-repo/archive/` cohort (heuristic: >30 memos), shard by
chronological window the same way Phase 1 batches — one specialist agent per shard,
all dispatched in parallel, each writing to its own `[SCRATCH_PATH]`. Below that count,
single-agent dispatch is canonical (same threshold logic as Phase 0's lightweight-mode
gate, scaled down for this narrower cohort).

## Consumption downstream

- **The mechanical consumer is `agent-prompts/phase-3d-specialist-assembler.md`, a standing
  Sonnet worker — not Phase 3d's own agent reading this branch's output directly.** The
  coordinator dispatches the assembler against this specialist's scratch file(s) whenever
  the Cross-Repo Archive Specialist Branch ran this pass; the assembler parses the
  `cross_repo_dispositions:` YAML documented above (including `assigned_count:` and
  `dropped_memos:`) and emits Phase 3d-shaped `deletions:` rows for `ROUTINE` entries
  (`disposition: DELETE`, `reason:` inherited verbatim from the entry's `reason:` field,
  `artifact_path:` from `memo_path:`), an `excluded_memo_paths:` list for `COMMITMENT_OPEN`
  entries (excluded from the deletion set entirely), and a `boundary_ratification_paths:`
  list so `BOUNDARY_RATIFICATION` entries are accounted for without becoming deletion rows.
  Phase 3d's main dispatch then receives the assembler's output path as its
  `[CROSS_REPO_DISPOSITIONS_PATH]` fill-in and splices the pre-formed rows in verbatim —
  see `agent-prompts/phase-3d-specialist-assembler.md` § Consumption downstream and
  `PIPELINE.md § Phase 3d` for the full wiring. (Prior to this assembler existing, this
  section claimed Phase 3d read the raw specialist output directly — nothing mechanical
  did that; a 2026-07-22-23h55 run had to hand-brief an ad-hoc agent to bridge the gap.)
- Phase 3c (DIRECTORY_GUIDE assembly) and Phase 5 apply-agents treat any
  `BOUNDARY_RATIFICATION` draft the same as a Phase 2 new-guide/DR output — same
  provenance-frontmatter and apply-agent mechanics, keyed off `cross_repo_memo:`
  instead of `provenance:`/`archived_handoff:`.
