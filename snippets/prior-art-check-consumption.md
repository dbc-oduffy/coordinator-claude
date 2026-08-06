<!-- canonical source for prior-art-check-consumption — edit here, then run bin/verify-snippet-sync prior-art-check-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers prior-art-check-consumption -->

<!-- BEGIN prior-art-check-consumption (synced from snippets/prior-art-check-consumption.md) -->
## Prior-Art Check Integration

If your dispatch prompt cites a **prior-art-check pre-flight** with a sidecar path (the engine-provisioned `state/plan-sidecars/<plan-stem>.prior-art-check.md` home, computed once by `provision_report` and passed through unchanged), the artifact has already been cross-referenced against the coordinator's accumulated prior art — project wikis, global wikis, the coordinator doctrine wiki, `state/lessons/`, decision records, and the central improvement queue. Use the pre-flight to focus your review on architecture, approach, and design rather than re-deriving lessons we've already captured.

**Prior art is current best-state, not eternal law.** A Conflict is *not* "plan must yield." It is a direction-of-correction question with multiple valid resolutions: amend the plan, amend the wiki/registry/lessons, do both, or document a knowing divergence. Your review is where the direction gets recommended — the integrator lands edits on whichever surface(s) you (and the EM) name. Treating prior art as immutable freezes the corpus; treating it as advisory keeps it honest.

**Buckets:**

- **Conflicts** — prior art contradicts a plan claim. The sidecar quotes the prior-art passage verbatim and lists candidate directions for the EM (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). Your job per conflict: recommend a direction with one-sentence reasoning. Default isn't "fold prior art into plan" — default is *think about which surface is right now*. The plan is often the more current artifact; the wiki was written months ago. Conversely, prior art often encodes an incident the plan author didn't live through. Use your architectural judgment to pick. If you recommend `update-prior-art`, name the specific wiki/lessons/registry file and the substance of the correction so the integrator can land it.
- **Compatible-but-relevant** — prior art covers the topic; the plan should cite or align vocabulary. These are informational, not blockers, but a plan that ignores established conventions makes future readers re-derive context. Flag missing citations in your findings if they would materially aid maintainability. Each entry carries a `subtype` field: `cite` (prior art is current — plan should reference it) or `wiki-may-be-outdated` (entry is >60 days old and the plan looks like an evolution; the wiki itself likely needs revision — treat as a soft `update-prior-art` signal).
- **Silent** — no prior art covers this claim. Means you are reviewing new ground; calibrate your scrutiny accordingly.

**Verdict semantics:**

- **COMPATIBLE** — no conflicts; the plan aligns with established prior art. You are reviewing on architecture alone.
- **WARN** — one or more conflicts surfaced. Per conflict, recommend a direction-of-correction (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`) with one-sentence reasoning. The EM dispositions before the integrator runs. If you disagree with any direction the EM has pre-marked in the dispatch brief, surface as a finding — your architectural judgment trumps the prior-art-checker's mechanical match and is the primary input to the EM's call.
- **BLOCKED-SURFACE-TO-PM** — load-bearing-doctrine conflict; if you are reading this, the EM has either escalated to PM and proceeded with PM authorization, or the dispatch is malformed. Verify the plan documents PM authorization before approving.
- **DEGRADED** — the agent ran with incomplete coverage (Phase 1 claim cap hit, Stuck Detection fired ≥1 time, a corpus was unreadable, or estimated token cost exceeded 50K). Treat as no signal — review the plan fully against prior art as if no pre-flight ran.

**The prior-art-checker is mechanical, not judgmental.** It can over-match (false-flag a phrasing difference as conflict) and under-match (miss a doctrine that applies but uses different keywords). Your review supplements it; you don't ratify it. If the sidecar flags a conflict you think is bogus, say so — the prior-art-checker becomes a feedback loop on wiki quality, and your dissent is signal.

**When no prior-art-check pre-flight ran**, this integration is silent — your review proceeds as before. The pre-flight is additive; it does not change your standards, only the division of labor on prior-art recall.

### Conflicts vs. your own findings

If you also identify a finding that overlaps a prior-art-check Conflict, label your finding "reinforces prior-art-check Conflict #N" — convergence between an independent reviewer and the corpus is high-confidence signal. The integrator uses this for fix prioritization.

### Platform-capability bucket — "this plan builds infra a sibling hosts"

**Plan-mode only.** When the dispatch brief resolved a `fleet_capability_index:` at dispatch time, the sidecar may carry a 4th bucket — **Platform capability** — alongside Conflicts / Compatible-but-relevant / Silent. This bucket fires when the plan proposes *constructing* structured infrastructure (a store, a query surface, an index, an embedding pipeline) that a sibling repo already hosts as a platform capability and has declared in its authored capability manifest.

- **Offer-shape, never a violation flag.** An entry leads with the alternative — `"<sibling-repo> offers <capability>; consume via <real consume_seam>"` — not a bare "you're duplicating X" flag. Treat it as architectural input to weigh, not a blocker; the checker never auto-blocks and never mutates the plan.
- **Polarity is mechanical, not inferred.** The bucket only ever offers consumer→host (this plan's repo is the consumer proposing to build; the sibling is the host already offering). A plan that proposes *producing into* an existing sibling store (append/write against a named existing seam) is the good shape and yields no entry in this bucket — silence on that shape is intentional, not a miss.
- **Maturity is fail-closed.** An entry's `maturity` (`live | stale | unverified | absent`) reflects whether the sibling's capability is confirmed reachable and current; downgrade your confidence on `stale`/`unverified` entries accordingly.
- **Action on a Platform-capability entry:** treat it like a Compatible-but-relevant entry that argues for reuse — factor it into your architectural review, and if you agree the plan should consume rather than build, say so in your findings. The EM routes the follow-up cross-repo ask; you are not asked to draft it.

<!-- END prior-art-check-consumption -->

<!-- AUTHORING NOTES — deliberately placed AFTER the END sentinel. Everything between
     BEGIN and END is injected verbatim into the dispatch prompt (header_style
     sentinel-embedded has no header-skip step), so an authoring note inside the span is
     paid on every dispatch to all 6 carriers. Guarded by
     coordinator/tests/test_injected_blocks_carry_no_authoring_comment.py. -->

<!-- Corpus-staleness note: the list above is a restatement, not the source of truth. `agents/prior-art-checker.md` § Bootstrap: corpus inventory is authoritative for which corpora the checker actually consults — if that list gains or drops a corpus kind, update this line (and its 4 synced consumers via `bin/verify-snippet-sync prior-art-check-consumption --fix`) to match. -->

<!-- Negative-spec: this is the PLAN-mode Platform-capability bucket (fleet-capability-index-fed).
     It is distinct from the research-mode 4th bucket ("Existing corpus — read before researching")
     documented in agents/prior-art-checker.md, which intentionally stays OUT of this snippet
     (see prior-art-checker.md:32). Do not conflate the two "4th buckets" — they belong to different
     modes and neither licenses adding the other here. -->

