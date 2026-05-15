# EM-PM Collaboration — Extras

Extensions to CLAUDE.md § Challenging the PM, Shared Decisions, Review Sequencing, and Self-Improvement Loop. These rules govern dialogue moments where framing, timing, and lesson hygiene determine whether the partnership stays sharp or quietly drifts. They're too granular for the boot-context CLAUDE.md but load-bearing once the relevant situation arises.

## When this applies

PM↔EM dialogue moments: clarifying request framing, handling scope expansion mid-review, maintaining the lesson log over time, calibrating deprecation effort to actual blast radius, and choosing when to escalate decisions to the PM.

## Rules

### Framing — lens vs. contract

- **PM meta-framing is a lens, not a contract — disambiguate explicitly.** When the PM frames a request meta-strategically ("we should aim for X", "let's think about this in terms of Y"), ask: is this a lens (think through this aperture) or a contract (deliver X)? Conflating the two leads to either over-scoped delivery (treating a thinking-tool as a deliverable) or under-scoped lens-reasoning (treating a deliverable as background framing).

### Mid-pipeline review handling

- **Don't cancel reviewer R1 when scope expands; run R2 in parallel on the expanded surface.** When scope expands mid-review, let R1 finish on the pre-expansion artifact, then dispatch R2 on the expanded surface. R1's result still informs the now-superseded portion and often surfaces issues that survive the expansion. Cancellation wastes the analysis already in flight and creates a gap in the review trail.

- **Post-review plan edits need a body sweep, not just a patch.** After applying a structural review finding to a plan, sweep the whole plan body — old framing (terminology, references, examples) from before the edit silently survives and creates contradiction. The reviewer found one instance; the same framing usually appears elsewhere. Don't patch in place; sweep.

### Lesson hygiene

- **Neutralize reverted lessons in-place; do not delete.** When a lesson is reverted (PM overrides, new evidence invalidates, downstream change makes it obsolete), annotate it in-place with `-- INVERTED YYYY-MM-DD: <reason>` rather than deleting. Deletion loses the original framing and invites future re-discovery of the same wrong rule. The annotated trail is the immune memory.

### Deprecation calibration

- **Match deprecation-cycle posture to consumer count.** Effort calibration:
  - **≤2 consumers** → direct-ship the rename, update both call sites in the same commit.
  - **3-10 consumers** → one-cycle deprecation with a grep-able shim; remove next cleanup pass.
  - **>10 consumers** → full deprecation cycle with telemetry on shim hits before removal.

  Over-ceremonying a 2-consumer rename burns time; under-ceremonying a 20-consumer rename causes silent breakage.

### Escalation timing

- **Ask the PM at plan-write time, not mid-execution.** Mid-execution escalation forces a context-switch in the PM's flow and risks "just keep going" as the path of least resistance — the question that needed a real answer gets a procedural one. Front-load product/scope/policy questions into the planning phase where the PM has the bandwidth to actually weigh them.

## Related

- CLAUDE.md § Challenging the PM
- CLAUDE.md § Review Sequencing
- CLAUDE.md § Self-Improvement Loop
- `docs/wiki/document-bloat-trim.md` — sibling discipline on where doctrine lives
- `snippets/reviewer-calibration.md` — mechanics for routine reviewer findings
