<!-- canonical source for run-report-citizenship — edit here, then run bin/verify-snippet-sync run-report-citizenship --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.run-report-citizenship] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar, keyed by `subagent_type`. Consumed by the two -->
<!-- run-report-typed subagent_types (executor, review-integrator) per `report_type_map:`. -->
<!-- Not pasted by verify-snippet-sync. This is the THIRD contract_blocks artifact-type family, -->
<!-- alongside the G1 reviewer-persona family (sidecar-frontmatter-contract) and the G2 -->
<!-- pre-flight-emitter family (sidecar-emission-contract) — deliberately a separate block, not a -->
<!-- shoehorn onto either: sidecar-frontmatter-contract addresses the reviewer-persona scaffolds -->
<!-- (its shape-discriminator table maps `## Verdict`/`## Rationale`, `## Findings`, and -->
<!-- `## Questions` to their types, and names the run-report body sections only to exclude -->
<!-- them), and -->
<!-- sidecar-emission-contract's path convention is specific to the G2 plan-pipeline pre-flight -->
<!-- home (state/plan-sidecars/<plan-stem>.<lens>.md) — neither is the run-report shape. -->

## Run-Report Citizenship

Your dispatch is `report_type_map`-eligible for a `run-report`-typed sidecar, not a
`review-findings` or `assessment` one — the three artifact-type shapes are distinct and this
block describes yours specifically.

**Path convention.** `state/subagent-share/<session-id>/<provision_key>.md`, engine-computed —
never hand-assembled. Provided via a `sidecar_path:` dispatch-brief field (fan-out path), or
self-created as your first action when the brief carries `plan:`+`chunk:` without `sidecar_path:`
(ad-hoc plan-execution path), via the literal absolute `coordinator-doc-new` command the
dispatching EM injected into your brief (fallback: the settings-home forwarder,
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new"`).
A dispatch carrying neither `sidecar_path:` nor (`plan:`+`chunk:`) has no sidecar to maintain —
report via exit-report only.

**Frontmatter shape.** `status:`, `agent_type:`, `spawned_at:`, `dispatched_by:`, `divergence:`
(`{"diverged": false}` until you flip it), `commits: []`, `sidecar_schema: v1` — a superset shape
distinct from the reviewer-persona `kind:`/`reviewer:`/`verdict:`/`findings_count:`/`plan:` shape
and the G2 emitter shape.

**Status transitions.** `open` OR `dispatched` (writer-set at spawn — see below) → `in_flight` (you
set this as your first action after reading your brief) → `complete | blocked | thrashing` (you set
this at exit, matching your exit-report tag).

**Two writers, two spawn-time shapes — both correct.** Unique to the `run-report` type: which shape
you were handed depends on the provisioning path. The engine-side spawn-time writer
(`provision_report`) emits the SUBSET — `status: open`, `agent_type:`, `spawned_at:`,
`lead_session_id:`, `divergence:`, `commits: []`, `dispatch_feed:` — with no `plan:`/`chunk:`/
`dispatched_by:`/`sidecar_schema:`. The self-create path (`coordinator-doc-new`, the
`plan:`+`chunk:` ad-hoc case above) emits the full `run-report.schema.json` superset —
`agent_type:`, `spawned_at:`, `divergence:`, `commits:`, `dispatch_feed:`, `plan:`, `chunk:`,
`dispatched_by:`, `sidecar_schema:`, and `status: dispatched` — but never `lead_session_id:`. The
schema admits both initial states deliberately, which is
why the transition list above starts with either. Do not add the other writer's fields to the
scaffold you were handed to make the two match.

**Commits list stays EM-populated.** You never commit (this is unconditional for every run-report
citizen — see your own agent file's Commit Discipline section), so `commits:` stays
`[]` for the whole of your dispatch. The EM populates it after the EM-serial commit that lands
your edits, using the commit SHA from its own `git commit`.

**Free-form observations.** Append latent-bug notes, mid-flight decisions, and validation output
snippets under a `## Observations` heading in the sidecar body — this is your scratchpad, not a
formal deliverable shape. Write early, write often.

**Disambiguation — do not conflate with plan-body status.** Plan-body `**Status:**` is EM-owned
phase state; sidecar frontmatter `status:` is your own lifecycle state. These are distinct fields
on distinct artifacts — never cross-reference one to explain the other.

**Doctrine root:** `coordinator/agents/executor.md § Run-Report Sidecar`
