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

### Successor-session framing is hedging when the gate-graph permits fan-out

- **"Pick this up tomorrow / in a successor session" is hedging when the dispatch-gate graph permits fan-out at executor-throughput speed.** Mid-execution on install-threshold-calibration, the EM framed remaining chunks C4/C5/C6 as deferred to a successor session — but the in-session executors had been 5-12 min wall-clock each on disjoint write surfaces, and the real cost to finish was 30-40 min of agent wall-clock, not an afternoon. The framing imported human-effort timelines into a setup where they don't fit. Discipline: read executor capacity (~5-15 min per coherent surface, parallel where gates allow), not human-day length. The test is the gate-graph, not the day boundary — and offering `/workstream-complete` while the plan is incomplete is poor form (the plan IS the workstream, the wave is a dispatch shape inside it). *(case: example-game-repo 2026-06-09)*

### Workstream-wide quality concern from the PM → audit, don't defend

- **When the PM raises a workstream-wide quality concern, dispatch a read-only structural audit before defending from memory.** During grow-corpus, the EM asserted "pure data authoring, no embedding model loads" from memory; PM pushed back; dispatching the Staff Engineer for a read-only audit of the full surface returned APPROVED_WITH_NOTES plus a uniform back-fix list (try/finally on six sqlite handles, embedder-plan scope carve-out). Workstream-wide concerns (resource leak, test coverage, security, schema parity) are structural questions the EM cannot answer honestly from memory — bounded cost, verifiable verdict, uniform back-fix list make the audit dispatch the default move, not the escalation. *(case: project-rag-ue-addon 2026-06-09)*

### Reviewer vs. PM intuition conflict surfacing

- **When a reviewer's recommendation contradicts the PM's stated intuition, surface the conflict — don't ratify either side without full information.** Bring the recommendation with its reasoning and let the PM decide from the complete picture. Performative agreement with the PM when the reviewer's argument is solid is a failure of the EM role, not deference.

*Source: example-game-repo `state/lessons.md` (example-game-repo-L77, central-promoted 2026-05-28).*

### PM owns workstream-complete determination

- **Authority to close a workstream belongs to the PM, not the EM.** The PM signals workstream closure by invoking `/workstream-complete`, `/handoff`, `/merge-to-main`, or commit-and-stop. The EM presenting a "Session Complete" header preempts that authority and tends to coincide with leaving real follow-ups unfinished. The EM's job at end-of-workstream is to report state honestly ("nothing left in this workstream that I can see") and wait for the PM to ratify or redirect.

### Implicit consent — name the inferred read

- **When the PM redirects past an open question without disputing the EM's recommendation, that is implicit consent — but silent assumption is risky.** Name the read explicitly in the next turn: *"Reading your X as implicit consent to Option Y — push back if I read that wrong."* This converts implicit into explicit before code lands and gives the PM an exit if the read is wrong. Pairs with the workstream-complete rule above: the EM does not unilaterally assume authority, but does surface inferred-authority reads aloud so the PM can ratify or correct them.

*Source: meta-repo `state/lessons.md` (central-promoted 2026-05-29).*

### PM revert of an EM "cleanup" beats the reviewer's recommendation

**When the PM reverts a file mid-session, that revert is ground truth — stop additive cleanup and roll back partial sibling edits to match.**

The failure shape: a reviewer (the Staff Engineer) recommends "promote sentinels to `_sentinels.py` when a third module consumes them"; the executor uses inline imports instead; the EM, mid-workstream, tries to honor the recommendation (creates `_sentinels.py`, rewires imports); PM reverts the primary file back to the executor's shape mid-edit.

**Why:** spec authority is the PM's, not the EM's — a reviewer's *recommendation* is not authority to deviate from what shipped. The PM's revert signals the desired shape; continuing to apply the reviewer's recommended direction after a revert actively diverges from the PM-authorized state.

**How to apply:** when a system-reminder reports a file the user just modified, treat that as ground-truth signal of the desired shape. Stop any additive cleanup against that file and roll back partial sibling edits that were building toward the now-rejected direction. A reviewer's recommendation is an input to the PM's authority, not a mandate that survives a PM override.

*Source: project-rag 2026-06-14, spinoff `install-divergence-classifier-decompose`.* [universal]

### Default to over-serializing integrators is a bias — split at the file-overlap boundary, not by reflex

**Integrators (and fan-out waves generally) *feel* like they must run serially to "avoid commit churn," but only the file-overlapping slices actually need ordering — disjoint slices can run NOW, in parallel.** The reflex to serialize is a cost the EM pays by default and the PM has to prompt against ("why do you need to wait?"). Before sequencing N integrators/executors, compute the file-overlap graph: slices that touch the same file gate each other; slices touching disjoint files (separate docs, a new fixture, a smoke test) run concurrently regardless of how "related" they feel. Splitting at the file-overlap boundary collapses serial waves into one parallel wave.

**Why:** an inbox-sweep code-review fold queued 3 integrators serially "to avoid churn"; only the CLI file overlapped between two of them — docs + smoke + new fixture were fully disjoint and could have run immediately. The PM's "why wait?" exposed the unexamined serialization bias. This is the EM-side bias the dispatch-gate taxonomy (file-overlap is the only unconditional serial gate) exists to correct — apply it to integrators, not just executors.

*Source: example-league-data-repo, inbox-sweep code-review fold (undated, central-pulled 2026-06-20).* [universal]

### Backlog-as-closure is the EM's most subtle laundering anti-pattern

**Surfaced decisions don't get "queued" by the EM.** After an audit / gap-list / inventory surfaces N items the audited author dropped, those N items ARE the deliverable — the EM's only honest dispositions are **Accept-and-action / Decline-with-architectural-reason / Surface-to-PM**. "Queue for later in the per-project backlog" is the same anti-pattern as `kind: ask` memo-laundering (`skills/pickup/SKILL.md` Memo Branch): it clears the bucket while silently making a *prioritization* call that belongs to the PM.

The failure shape (2026-06-15, UE+MCP campaign closeout in example-game-repo): the EM wrote "queued in the per-project backlog rather than enumerated here" for 15 absorption candidates the synthesis gap-audit had just surfaced. PM caught it: *"Backlog items are my decision, not yours. You're saying the workstream is complete without our having closed the gaps."* The reflex felt productive (the bucket clears) but it dressed a not-now prioritization call as routine EM disposition. Sister failure mode of appetite-based OOS framing (CLAUDE.md § Implementation Standards: "Not now / follow-up hedging = incomplete work").

**How to apply:** when the surfaced candidate list is feature-shaped (~1 day each, per-domain, sequenceable), the right move is a clean enumeration ready for PM sequencing — not a backlog write. Generalize beyond memos: the laundering rule (CLAUDE.md § Improvement Queue, "Queue is not a closure mechanism") applies to *any* decision-surface the EM produces, not just inbound asks.

*Source: example-game-repo `state/lessons.md` (example-game-repo-L47), central-pulled 2026-06-20.* [universal]

## Related

- CLAUDE.md § Challenging the PM
- CLAUDE.md § Review Sequencing
- CLAUDE.md § Self-Improvement Loop
- `docs/wiki/document-bloat-trim.md` — sibling discipline on where doctrine lives
- `snippets/reviewer-calibration.md` — mechanics for routine reviewer findings
