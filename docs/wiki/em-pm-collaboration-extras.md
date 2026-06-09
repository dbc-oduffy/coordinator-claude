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

### PM permissive disposition is upper bound, not pick

When the PM dispositions an architectural question permissively — "ask the reviewer", "fine to add an X", "go ahead with whatever shape works" — the **reviewer's** pick is binding, not the PM's upper bound. The PM's "fine" is permission, not preference. A reviewer who comes back with "you don't need an X" overrides the PM's "fine to add an X" because the PM was answering an authority question (is this in-scope?), not a design question (is this the right move?). EM error mode is treating the permissive disposition as a *floor* the reviewer can build on, when it's actually a *ceiling* the reviewer can lower.

### Don't ask for engineering housekeeping — silent action with one-line notice

The "Don't ask for" doctrine in CLAUDE.md § Challenging the PM enumerates the categories. The noise-discriminator extension: default-Y prompts on commit timing, branch shape, internal naming, dispatch sequencing, midnight branch rename, post-commit auto-push, archival sweep timing are noise — converting them to silent action with a one-line notice (`Renamed work branch to today's date.`) costs the PM nothing and removes a class of meaningless ratification taps. The discriminator: if you'd answer Y on every prior instance regardless of session context, the prompt is housekeeping noise. If the answer genuinely depends on session state or PM intent, keep the prompt.

Sweep this pattern in any skill that gates engineering housekeeping behind a confirmation: `/workday-start`, `/workday-complete`, `/merge-to-main`, `/consolidate-git`, `/handoff`. The cost of a wrong silent action on housekeeping is bounded (`git reflog`, branch rename, etc.); the cost of a default-Y prompt is repeated across every session forever.

### Escalation timing

- **Ask the PM at plan-write time, not mid-execution.** Mid-execution escalation forces a context-switch in the PM's flow and risks "just keep going" as the path of least resistance — the question that needed a real answer gets a procedural one. Front-load product/scope/policy questions into the planning phase where the PM has the bandwidth to actually weigh them.

### Reviewer vs. PM intuition conflict surfacing

- **When a reviewer's recommendation contradicts the PM's stated intuition, surface the conflict — don't ratify either side without full information.** Bring the recommendation with its reasoning and let the PM decide from the complete picture. Performative agreement with the PM when the reviewer's argument is solid is a failure of the EM role, not deference.

*Source: holodeck `state/lessons.md` (holodeck-L77, central-promoted 2026-05-28).*

### PM owns workstream-complete determination

- **Authority to close a workstream belongs to the PM, not the EM.** The PM signals workstream closure by invoking `/workstream-complete`, `/handoff`, `/merge-to-main`, or commit-and-stop. The EM presenting a "Session Complete" header preempts that authority and tends to coincide with leaving real follow-ups unfinished. The EM's job at end-of-workstream is to report state honestly ("nothing left in this workstream that I can see") and wait for the PM to ratify or redirect.

### Implicit consent — name the inferred read

- **When the PM redirects past an open question without disputing the EM's recommendation, that is implicit consent — but silent assumption is risky.** Name the read explicitly in the next turn: *"Reading your X as implicit consent to Option Y — push back if I read that wrong."* This converts implicit into explicit before code lands and gives the PM an exit if the read is wrong. Pairs with the workstream-complete rule above: the EM does not unilaterally assume authority, but does surface inferred-authority reads aloud so the PM can ratify or correct them.

*Source: meta-repo `state/lessons.md` (central-promoted 2026-05-29).*

## Related

- CLAUDE.md § Challenging the PM
- CLAUDE.md § Review Sequencing
- CLAUDE.md § Self-Improvement Loop
- `docs/wiki/document-bloat-trim.md` — sibling discipline on where doctrine lives
- `snippets/reviewer-calibration.md` — mechanics for routine reviewer findings
