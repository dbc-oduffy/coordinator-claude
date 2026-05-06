<!-- canonical source for prior-art-check-consumption — edit here, then run bin/verify-prior-art-sync.sh --fix -->

## Prior-Art Check Integration

If your dispatch prompt cites a **prior-art-check pre-flight** with a sidecar path (typically `<plan-path>.prior-art-check.md`), the artifact has already been cross-referenced against the coordinator's accumulated prior art — project wikis, global wikis, `tasks/lessons.md`, and the central improvement queue. Use the pre-flight to focus your review on architecture, approach, and design rather than re-deriving lessons we've already captured.

**Buckets:**

- **Conflicts** — prior art contradicts a plan claim. The sidecar quotes the prior-art passage verbatim and suggests an EM action (PM input / fold-in / override-and-document). Treat conflicts as load-bearing context for your review: if the plan's "Considered alternatives" does not address a flagged conflict, that itself is a finding. If the plan correctly diverges from prior art, the divergence should be documented.
- **Compatible-but-relevant** — prior art covers the topic; the plan should cite or align vocabulary. These are informational, not blockers, but a plan that ignores established conventions makes future readers re-derive context. Flag missing citations in your findings if they would materially aid maintainability. Each entry carries a `subtype` field: `cite` (prior art is current — plan should reference it) or `wiki-may-be-outdated` (entry is >60 days old and the plan looks like an evolution; the wiki itself may need revision).
- **Silent** — no prior art covers this claim. Means you are reviewing new ground; calibrate your scrutiny accordingly.

**Verdict semantics:**

- **COMPATIBLE** — no conflicts; the plan aligns with established prior art. You are reviewing on architecture alone.
- **WARN** — one or more conflicts surfaced; the EM has dispositioned them before dispatching you. Read the sidecar to see what was overridden and on what grounds. If you disagree with an override, surface as a finding — your architectural judgment trumps the prior-art-checker's mechanical match.
- **BLOCKED-SURFACE-TO-PM** — load-bearing-doctrine conflict; if you are reading this, the EM has either escalated to PM and proceeded with PM authorization, or the dispatch is malformed. Verify the plan documents PM authorization before approving.
- **DEGRADED** — the agent ran with incomplete coverage (Phase 1 claim cap hit, Stuck Detection fired ≥1 time, a corpus was unreadable, or estimated token cost exceeded 50K). Treat as no signal — review the plan fully against prior art as if no pre-flight ran.

**The prior-art-checker is mechanical, not judgmental.** It can over-match (false-flag a phrasing difference as conflict) and under-match (miss a doctrine that applies but uses different keywords). Your review supplements it; you don't ratify it. If the sidecar flags a conflict you think is bogus, say so — the prior-art-checker becomes a feedback loop on wiki quality, and your dissent is signal.

**When no prior-art-check pre-flight ran**, this integration is silent — your review proceeds as before. The pre-flight is additive; it does not change your standards, only the division of labor on prior-art recall.

### Conflicts vs. your own findings

If you also identify a finding that overlaps a prior-art-check Conflict, label your finding "reinforces prior-art-check Conflict #N" — convergence between an independent reviewer and the corpus is high-confidence signal. The integrator uses this for fix prioritization.
