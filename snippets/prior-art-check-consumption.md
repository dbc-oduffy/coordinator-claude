<!-- canonical source for prior-art-check-consumption — edit here, then run bin/verify-snippet-sync prior-art-check-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers prior-art-check-consumption -->

<!-- BEGIN prior-art-check-consumption (synced from snippets/prior-art-check-consumption.md) -->
## Prior-Art Check Integration

If your dispatch prompt cites a **prior-art-check pre-flight** with a sidecar path (the engine-provisioned `state/plan-sidecars/<plan-stem>.prior-art-check.md` home, computed once by `provision_report` and passed through unchanged), the artifact has already been cross-referenced against the coordinator's accumulated internal doctrine and decision corpus. Use the pre-flight to focus your review on architecture, approach, and design rather than re-deriving lessons we've already captured.

**Prior art is current best-state, not eternal law.** A Conflict is *not* "plan must yield" — it's a direction-of-correction question with multiple valid resolutions: amend the plan, amend the wiki/registry/lessons, do both, or document a knowing divergence. Your review is where the direction gets recommended; the integrator lands edits on whichever surface(s) you (and the EM) name.

**Buckets:**

- **Conflicts** — prior art contradicts a plan claim. The sidecar quotes the prior-art passage verbatim and lists candidate directions for the EM (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). Your job per conflict: recommend a direction with one-sentence reasoning — default is *think about which surface is right now*, not "fold prior art into plan": the plan is often the more current artifact, but prior art often encodes an incident the plan author didn't live through. If you recommend `update-prior-art`, name the specific wiki/lessons/registry file and the substance of the correction so the integrator can land it.
- **Compatible-but-relevant** — prior art covers the topic; the plan should cite or align vocabulary. Informational, not blockers, but flag missing citations that would materially aid maintainability. Each entry carries a `subtype`: `cite` (prior art is current) or `wiki-may-be-outdated` (entry is >60 days old and the plan looks like an evolution — treat as a soft `update-prior-art` signal).
- **Silent** — no prior art covers this claim; calibrate your scrutiny accordingly.

**Verdict semantics:**

- **COMPATIBLE** — no conflicts; review on architecture alone.
- **WARN** — one or more conflicts surfaced; per conflict, recommend a direction with one-sentence reasoning, and the EM dispositions before the integrator runs. Disagree with a pre-marked direction? Surface it as a finding.
- **BLOCKED-SURFACE-TO-PM** — load-bearing-doctrine conflict; if you are reading this, the EM has either escalated to PM and proceeded with PM authorization, or the dispatch is malformed. Verify the plan documents PM authorization before approving.
- **DEGRADED** — incomplete coverage (claim cap hit, Stuck Detection fired, a corpus unreadable, or token cost exceeded 50K). Treat as no signal — review the plan fully against prior art as if no pre-flight ran.

**The prior-art-checker is mechanical, not judgmental** — it can over-match (false-flag a phrasing difference) and under-match (miss doctrine under different keywords). Your review supplements it, never ratifies it; a bogus-flagged conflict is worth saying so.

**When no prior-art-check pre-flight ran**, this integration is silent — proceed as before.

### Conflicts vs. your own findings

If you also identify a finding that overlaps a prior-art-check Conflict, label it "reinforces prior-art-check Conflict #N" — convergence between an independent reviewer and the corpus is high-confidence signal, and the integrator uses it for fix prioritization.

### Platform-capability bucket — "this plan builds infra a sibling hosts"

**Plan-mode only.** When the dispatch brief resolved a `fleet_capability_index:` at dispatch time, the sidecar may carry a 4th bucket — **Platform capability** — alongside Conflicts / Compatible-but-relevant / Silent. It fires when the plan proposes *constructing* infrastructure (a store, a query surface, an index, an embedding pipeline) a sibling repo already hosts and has declared in its capability manifest.

- **Offer-shape, never a violation flag.** An entry leads with the alternative — `"<sibling-repo> offers <capability>; consume via <real consume_seam>"` — not a bare "you're duplicating X" flag; the checker never auto-blocks or mutates the plan.
- **Polarity is mechanical, not inferred.** The bucket only ever offers consumer→host. A plan that proposes *producing into* an existing sibling store (append/write against a named existing seam) is the good shape and yields no entry — silence there is intentional, not a miss.
- **Maturity is fail-closed.** `maturity` (`live | stale | unverified | absent`) reflects whether the sibling's capability is confirmed reachable and current; downgrade confidence on `stale`/`unverified`.
- **Action:** treat it like a Compatible-but-relevant entry arguing for reuse — factor it into your review, and say so in findings if the plan should consume rather than build. The EM routes the cross-repo ask; you don't draft it.

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

