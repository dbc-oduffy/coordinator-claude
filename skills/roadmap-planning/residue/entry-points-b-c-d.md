### Entry Point B — Pickup from `kind: roadmap-seed` stub (goal-seeded)

(a) Run `coordinator-invoke baton.awaiting_gate_recheck '{}'`; for this seed's row, if `machine_condition_met` is true, route the seed or clear the gate.
(b) Read the seed's `origin_goal_id` goal file; the seed is PM-acked if a `goal_go` entry with `scope: goal` lists its `handoff_id`; an unlisted seed needs its own PM ack.
(c) A seed mixing gated and gate-free work: run `baton.seed_split {seed, gate_free: [items]}`; the new seed carries `split_from` and is `ready_to_fire`; the original keeps `awaiting_gate` with `split_into`.

1. Read `authoring_session` (goal artifact, problem-set, initiative); its boundaries are ratified.
2. Stub scope = Phase 1 cluster seed; Phase 1 refines it into sub-clusters.
3. `run-id` = the stub's `stub_id` (`rc-04` → `run-id: rc-04`).
4. The 5+ items floor does NOT apply. Proceed to Phase 1 with the stub's scope as corpus anchor.

Lifecycle: `deployment_state: in_flight` when Phase 1 begins; `shipped` (via `/workstream-complete`)
when Phase 2 completes and the baton stubs are committed.

**Multi-seed:** one goal minted several coupled seeds → one pass, one `run-id` set from the goal;
each seed is its own cluster seed; every baton's `covers:` traces to its seed stub id.

### Entry Point C — Chain from `/shape` (ratified problem-set, `estimated_horizon: week`)

1. The ratified problem-set (`docs/problems/<slug>.md`) arrives as `<input-corpus-path>`.
2. Each `## Problems` entry is a provisional Step 1.2 cluster; `## Out of scope` pre-populates DROP verdicts.
3. Phase 1.5 still applies; the plan frontmatter inherits `problem_set: docs/problems/<slug>.md`.
4. The 5+ items floor applies; fewer → likely plan-shaped, confirm with the PM first.

### Entry Point D — Conform intake from a sizing-object (roadmap-routed)

A `state/sizings/<id>.yaml` with `route: pm-decision` + `xl_exit: roadmap` (or legacy `route:
roadmap`). Optional: the sizing lobby never gates a `roadmap-planning` invocation.

1. Read `intent` (verbatim), `estimate`, `scout_evidence`, `appetite` if present (read defensively).
2. Extra Phase 1.1 inventory input, not a pre-built cluster set; Steps 1.1–1.4 run unchanged.
3. Cite its path in `OVERVIEW.md`'s framing prose (Step 1.5.2); no new frontmatter field.
4. If B or C also applies, take whichever of A/B/C matches the input shape; note the sizing-object alongside.

The same sizing run in the background, with one approval gate, is `coordinator:roadmap-blitz`.
