Part of [`PIPELINE.md`](PIPELINE.md); phases still run in its strict sequence.

## Phase 3d: Deletion Manifest (folded into the Workflow — Sonnet, single)

**Model:** Sonnet. **Dispatch:** Single agent, dispatched directly by `distill-harvest.workflow.js`'s `phase-3d` phase. **Runs after:** Phase 3b (structural by placement in the script — does not consume Phase 3b's output, so the two could in principle overlap, but the script runs them in sequence).

**Input, in-memory, not scratch files:** the Workflow's own mechanically-computed `distillation_log_rows` (one row per source artifact — path, mechanical disposition `DISTILLED`/`EPHEMERAL`/`SKIP`, fate prose — computed earlier in the same run, § "Distillation-log rows" in the script) plus the Opus escalation resolution when Phase 3a triggered one. The agent's job is resolving those three mechanical dispositions into the final `DELETE`/`SEND_BACK`/`BLOCKED`/`PRESERVE` verdict by reading real external state (active `state/handoffs/`, open commitments, research/NotebookLM PRESERVE classes) that the mechanical pass has no visibility into — it never re-reads Phase 1/1.5/2 scratch files.

**[engine-reliant] Resolve delete-eligibility for candidate rows via `bin/distill-delete-guard.py`,
not LLM manual guard-checking.** Per the C8 contract (`docs/contracts/distill-engine-scripts.md`
§ 5): `bin/distill-delete-guard.py <candidate-path> ... [--repo-root <path>] [--basis-ref <ref> ...]`
mechanically runs all 5 delete-safety guards (`shipped_in` present, `status: actioned`,
active-reference, commitment-closure against `state/cross-repo-commitments/`, `realized_by`
resolves-on-disk — including the #12 memory-pointer exclusion) and returns
`{"eligible": bool, "blocked_by": [...guard-names...], "path"}` per candidate. Run this over the
Cross-Repo Archive Specialist Branch's `ROUTINE` cross-repo-memo candidates (§ above) before
splicing their pre-converted rows into this phase's manifest — an `eligible: false` result names
its `blocked_by` guard(s) as the `SEND_BACK`/`BLOCKED` reason instead of the agent re-deriving it
by hand. `archive/handoffs/**` stays out of this manifest per the pipeline-wide rule below
regardless of guard output. **Fail-loud on malformed op output:** a response missing
`eligible`/`blocked_by`/`path` is treated as script-unavailable, not a soft pass. **Agentic-path
fallback if the engine repo declines / the script is unavailable:** revert to the LLM manually checking
each of the 5 guard conditions per candidate — degraded (prone to reintroducing the #12
memory-pointer hole and the short-SHA scientific-notation trap this script exists to close), not
broken.

**Suppressed, not dispatched, on join-integrity failure.** When the Workflow's `join_integrity.verdict` is `failed` (§ "Join-integrity verdict" in the script), this phase does not dispatch at all — the source→nugget join is unsafe to trust for disposal purposes, the same suppression the mechanical `distillation_log_rows` pass is already subject to. Never a partial manifest built on an untrustworthy join.

**Either harvested or not — never a middle disposition.** `SKIP` rows (a batch that never scanned) resolve to `SEND_BACK`, naming "batch never scanned" as the reason — never `DELETE` and never a bare "retain"/"no citation found" row that reads as settled. An artifact whose knowledge is not fully extracted is `SEND_BACK` or `BLOCKED`, both of which route it back for completion at Phase 4/5, not into the delete set.

**Cross-Repo Archive Specialist Branch input.** The Cross-Repo Archive Specialist Branch (§ above) still runs alongside Phase 1/1.5 on its own disjoint cohort and still converges at Phase 3d consumption — that convergence is unaffected by this phase's fold into the Workflow. Its pre-converted rows are passed to `distill-harvest.workflow.js` as the optional `crossRepoDispositions` Workflow input (same input-plumbing shape as the script's other optional inputs, e.g. `contextTerms`) and are spliced into the Phase 3d deletion manifest in-script, immediately after the deletion-manifest agent returns and before the artifact re-entry loop — so re-entry covers them like any other row. An absent or empty `crossRepoDispositions` input is a logged no-op.

**`archive/handoffs/**` is never eligible for any disposition** — omitted from the manifest entirely, per the pipeline-wide rule (§ Phase 0 step 1, § Baton Fate).

---

**Phase 3 produces (combined across 3a–3d):**
1. Cross-reference consistency report — contradictions flagged and resolved (3a + optional Opus, folded into the Workflow)
2. Deduplicated decision records (3b, folded into the Workflow)
3. `DIRECTORY_GUIDE.md` preview (3c, coordinator-mechanical, consumes the Workflow's returned `phase_3b_dr_dedup`/`synth_results` rather than Phase 2 scratch frontmatter when the Workflow vehicle ran this pass)
4. **Deletion manifest** — every source artifact resolved to `DELETE`, `SEND_BACK`, `BLOCKED`, or `PRESERVE` with reason (3d, folded into the Workflow)

**Retired: "Phase 3d fanout assembly" (Workflow-fanout mode only).** A prior revision of this
pipeline gated Phase 3d on `N > 500` total deletion-eligible candidates, flipping to a
per-cluster fanout mode with a canonical-manifest assembly step and a pre-deletion sentinel
against partial assembly. This retires the whole tiered scope-gate: the background
Workflow (`commands/distill.md` § Workflow) is now the vehicle unconditionally, so the
single-Sonnet-vs-fanout mode distinction the assembly step existed to bridge no longer applies
— there is one Phase 3d shape regardless of corpus size.
