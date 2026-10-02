### Entry Point B — Pickup from `kind: roadmap-seed` stub (goal-seeded)

The stub's `authoring_session` path holds the goal-setting context; its roadmap boundaries were
already ratified.

1. Read `authoring_session` (goal artifact, problem-set, initiative).
2. The stub body's scope is the Phase 1 cluster seed; Phase 1 refines it into sub-clusters.
3. `run-id` = the stub's `stub_id` (`rc-04` → `run-id: rc-04`).
4. The 5+ items floor does NOT apply.
5. Proceed to Phase 1 with the stub's scope as corpus anchor.

Lifecycle: `deployment_state: in_flight` when Phase 1 begins; `shipped` (via `/workstream-complete`)
when Phase 2 completes and the baton stubs are committed.

**Multi-seed:** one goal minted several coupled seeds → one pass, one `run-id` set from the goal;
each seed is its own cluster seed; every baton's `covers:` traces to its seed stub id; lifecycle per
seed.

### Entry Point C — Chain from `/shape` (ratified problem-set, `estimated_horizon: week`)

1. The ratified problem-set (`docs/problems/<slug>.md`) arrives as `<input-corpus-path>`.
2. Each problem under `## Problems` is a provisional Step 1.2 cluster; `## Out of scope` pre-populates
   DROP verdicts.
3. Phase 1.5 still applies: each KEEP cluster still needs a research-corpus scout.
4. The plan frontmatter inherits `problem_set: docs/problems/<slug>.md`.
5. The 5+ items floor applies; fewer → likely plan-shaped, confirm with the PM first.

### Entry Point D — Conform intake from a sizing-object (roadmap-routed)

A `state/sizings/<id>.yaml` with `route: pm-decision` + `xl_exit: roadmap` (or legacy `route:
roadmap` — accept both). Optional: with none present this skill runs exactly as today, and the
sizing lobby never gates or refuses a `roadmap-planning` invocation absent one.

1. Read `intent` (verbatim), `estimate`, `scout_evidence`, and `appetite` if present (usually
   absent — read defensively; absence is not an incomplete artifact).
2. It is extra Phase 1.1 inventory input, not a pre-built cluster set; Steps 1.1–1.4 run unchanged.
3. Cite its path in `OVERVIEW.md`'s framing prose (Step 1.5.2); no new frontmatter field.
4. If B or C also applies, resolve to whichever of A/B/C matches the input shape and note the
   sizing-object alongside.

Detail and routing rationale: wiki `roadmap-planning-residue.md` § Entry Points B, C, D.
