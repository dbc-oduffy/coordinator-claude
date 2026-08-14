### Entry Point B — Pickup from `kind: roadmap-seed` stub (goal-seeded)

When a `kind: roadmap-seed` stub is actioned via `/pickup`, the stub's `authoring_session` path contains the goal-setting context that spawned it (the goal artifact, upstream problem-set, and any KRs the goal-setting session produced). The stub represents a pre-scoped slice of work whose roadmap boundaries were already ratified during goal-setting.

**On pickup:**
1. Read the stub's `authoring_session` path to load upstream context (goal artifact, problem-set, initiative).
2. Use the stub body's scope description as the Phase 1 cluster seed — the stub is the single cluster that was already scoped; Phase 1 Synthesize refines it into sub-clusters.
3. Set `run-id` from the stub's `stub_id` (e.g. a stub `roadmap-seed` with `stub_id: rc-04` → `run-id: rc-04`).
4. The 5+ items precondition does NOT apply — a single roadmap-seed stub is a valid entry even if it describes a narrowly scoped roadmap.
5. Proceed to Phase 1 (Synthesize) with the stub's scope as the input corpus anchor, then continue the normal pipeline.

**Stub lifecycle:** set `deployment_state: in_flight` on the roadmap-seed stub when Phase 1 begins; set `deployment_state: shipped` (via the normal `/workstream-complete` path) when Phase 2 completes and the resulting roadmap-baton stubs are committed.

### Entry Point C — Chain from `/shape` (ratified problem-set, `estimated_horizon: week`)

When `/shape` ratifies a problem-set whose `estimated_horizon` field is `week`, it routes here instead of `coordinator:plan`. The ratified problem-set (`docs/problems/<slug>.md`) is the oracle that replaces the research corpus as the cluster seed.

**On chain-from-shape:**
1. The ratified problem-set (`docs/problems/<slug>.md`) arrives as the `<input-corpus-path>` argument (or is cited explicitly in the invocation).
2. Treat each problem listed under `## Problems` in the problem-set as a provisional cluster for Phase 1 Step 1.2. The problem-set's `## Out of scope` block pre-populates DROP verdicts.
3. Phase 1.5 research corpus still applies — each KEEP cluster still needs a research-corpus scout to ground the OVERVIEW in primary sources, not just the problem-set prose.
4. The plan's frontmatter inherits the problem-set reference: `problem_set: docs/problems/<slug>.md`.
5. The 5+ items precondition applies to this path — if the problem-set has fewer than 5 items, the work is likely plan-shaped, not roadmap-shaped; confirm with the PM before proceeding (the `/shape` router routes here because `estimated_horizon: week` was set at ratification — the 5+ items check is this skill's own precondition, not a `/shape` filter; if the problem-set is genuinely week-sized but shallow, it may warrant a single `coordinator:plan` call instead).

**Routing note (from `/shape`):** `/shape` sets `estimated_horizon: week` on the problem-set frontmatter at ratification. The EM confirms the routing at the fork (detect-then-confirm, never silent guess) before invoking this skill. See `coordinator/skills/shape/SKILL.md § Transition` for the router's outbound logic.

### Entry Point D — Conform intake from a sizing-object (roadmap-routed)

The sizing lobby (`coordinator:sizing`) resolves initiative-scale asks to the PM-decision route with an `xl_exit: roadmap` pick, or — on an older sizing-object — directly to `route: roadmap`, and hands roadmap-planning a `state/sizings/<id>.yaml` sizing-object as an optional entry contract either way. This is a conform intake, not a replacement for Entry Points A/B/C above — no sizing-object present means this skill's YAML-DAG/topo-numbering mechanics and Phase 1–3 pipeline run exactly as today; the sizing lobby never gates or refuses a `roadmap-planning` invocation absent one, by explicit anti-scope ruling ("do not build a wall").

Recognize the roadmap signal in either shape: `route: pm-decision` with `xl_exit: roadmap` (the PM chose the roadmap exit at the XL decision point — the current shape), or the legacy `route: roadmap` (sizing-objects already on disk in this shape remain valid — accept both, do not require migrating one to the other).

**On sizing-routed entry:**
1. Read the sizing-object's `intent` (the PM's ask, verbatim), `estimate`, `scout_evidence`, and `appetite` if present — `appetite` is optional and usually absent (it is not collected before sizing), so read it defensively and carry on when it is missing; never treat its absence as an incomplete artifact.
2. The sizing-object seeds Phase 1 the same way Entry Point A's `<input-corpus-path>` does — it supplies the routing rationale and any `scout_evidence` pointers as additional Phase 1.1 inventory input, not a pre-built cluster set. Phase 1 Synthesize (Steps 1.1–1.4) still runs unchanged.
3. Cite the sizing-object's path in `OVERVIEW.md`'s framing prose (Step 1.5.2) alongside the other Phase 1 outputs, for audit-trail continuity — no new frontmatter field is added; the schema is unchanged.
4. If Entry Point B or C also applies (a goal-seeded stub or a `/shape` chain), the sizing-object is additional provenance context layered on top, not a competing entry — resolve to whichever of A/B/C matches the actual input shape, then note the sizing-object alongside it.
