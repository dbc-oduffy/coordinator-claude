# Synthesis Discipline

<!-- Purpose: Extended doctrine for synthesizer-role constraints and gap-audit mechanics. The one-liner contract ("Synthesizers assess, fill, and frame — never re-author specialist content") is enforced directly in `coordinator/agents/parallel-review-synthesizer.md` and `coordinator/agents/research-synthesizer.md`; this wiki carries refinements and application rules. -->

**Synthesizers assess, fill, and frame — never re-author specialist content.** Output reading like condensed specialist prose = pipeline failure. Enforced at dispatch in the synthesizer agent prompts — `parallel-review-synthesizer.md`, `research-synthesizer.md`.

---

## Tier-drift / gap-audit — surface the threshold, don't reverse the bucket

**When a gap-audit or tier-drift check identifies a threshold mismatch, the fix surfaces the threshold VALUE inside the artifact, not a bucket-assignment reversal.**

A synthesis gap-audit compares a finding's bucket assignment (e.g. "P2", "Tier-2 covered", "compatible-but-relevant") against the auditor's threshold model. When the bucket looks wrong, the temptation is to simply re-assign it to the "correct" bucket and move on. That reversal hides the threshold that drove the original assignment — the next reader of the artifact can't tell whether the bucket is authoritative or a correction, and the next gap-audit will re-flag the same item because the threshold is still invisible.

**Correct shape:** when a threshold mismatch is found, add a one-line annotation to the artifact itself stating the threshold value that resolves the ambiguity (e.g. `<!-- gap-audit: covered by §4b at 80% threshold; residual 20% is the append-empty-string edge case, tracked in #X -->`). The bucket assignment stays stable; the threshold is now greppable and reviewable. If the threshold genuinely indicates the wrong bucket was assigned, the fix is to surface the threshold AND update the bucket together, citing the threshold as the rationale — not a silent re-assignment.

Apply at: any synthesizer pass that includes a tier-drift check, a coverage-audit, or a gap-audit step. *Source: central-improvement-queue #101.*

---

## Related

- `coordinator/agents/parallel-review-synthesizer.md` / `coordinator/agents/research-synthesizer.md` — canonical one-liner contract, enforced directly in prompt.
- `docs/wiki/dispatching-parallel-agents.md` — synthesizer dispatch mechanics (reads specialist output from disk, does not re-author).
- `docs/wiki/review-integration-doctrine.md` — integrator-side analogue (integrators assess findings, do not rewrite the review).
