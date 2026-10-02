<!-- canonical source for prior-art-check-consumption — edit here, then run bin/verify-snippet-sync prior-art-check-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers prior-art-check-consumption -->

<!-- BEGIN prior-art-check-consumption (synced from snippets/prior-art-check-consumption.md) -->
## Prior-Art Check Integration

If your dispatch prompt cites a **prior-art-check pre-flight** with a sidecar path (the engine-provisioned `.coordinator-local/plan-sidecars/<plan-stem>.prior-art-check.md` home, passed through unchanged), the artifact has already been cross-referenced against the coordinator's accumulated internal doctrine and decision corpus. Focus your review on architecture, approach, and design rather than re-deriving captured lessons.

**Prior art is current best-state, not eternal law.** A Conflict is a direction-of-correction question, not "plan must yield": amend the plan, amend the wiki/registry/lessons, do both, or document a knowing divergence. You recommend the direction and land the edits yourself on whichever surface(s) you and the EM name.

**Buckets:**

- **Conflicts** — prior art contradicts a plan claim. The sidecar quotes the passage verbatim and lists candidate directions (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). Per conflict, recommend a direction with one-sentence reasoning: the plan is often more current, but prior art often encodes an incident the plan author didn't live through. For `update-prior-art`, name the file and the correction, and land it yourself.
- **Compatible-but-relevant** — prior art covers the topic; the plan should cite or align vocabulary. Informational; flag missing citations that would aid maintainability. A `subtype` of `cite` means prior art is current; `wiki-may-be-outdated` (entry >60 days old, plan looks like an evolution) is a soft `update-prior-art` signal.
- **Silent** — no prior art covers this claim; calibrate your scrutiny accordingly.

**Verdict semantics:**

- **COMPATIBLE** — no conflicts; review on architecture alone.
- **WARN** — one or more conflicts surfaced; the EM dispositions each conflict before you apply it. Disagree with a pre-marked direction? Surface it as a finding.
- **BLOCKED-SURFACE-TO-PM** — load-bearing-doctrine conflict; the EM has PM authorization or the dispatch is malformed. Verify the plan documents it before approving.
- **DEGRADED** — incomplete coverage (claim cap hit, Stuck Detection fired, a corpus unreadable, or cost over 50K tokens). Treat as no signal and review as if no pre-flight ran.

**The prior-art-checker is mechanical, not judgmental** — it can over-match and under-match. You supplement it, you do not ratify it; say so when a conflict is bogus.

**When no prior-art-check pre-flight ran**, this integration is silent — proceed as before.

### Conflicts vs. your own findings

If you also identify a finding that overlaps a prior-art-check Conflict, label it "reinforces prior-art-check Conflict #N" — convergence between an independent reviewer and the corpus is high-confidence signal for fix prioritization.

### Platform-capability bucket — "this plan builds infra a sibling hosts"

**Plan-mode only.** When the dispatch brief resolved a `fleet_capability_index:`, the sidecar may carry a 4th bucket, **Platform capability**: the plan *constructs* infrastructure (a store, query surface, index, embedding pipeline) a sibling repo already hosts and declares in its capability manifest.

- **Offer-shape, never a violation flag.** Entries read `"<sibling-repo> offers <capability>; consume via <real consume_seam>"`; the checker never blocks or mutates the plan.
- **Polarity is mechanical.** Only consumer→host. A plan *producing into* an existing sibling seam yields no entry — silence is intentional.
- **Maturity is fail-closed.** `maturity` (`live | stale | unverified | absent`) says whether the capability is confirmed reachable and current; downgrade confidence on `stale`/`unverified`.
- **Action:** treat it as a Compatible-but-relevant entry arguing for reuse, and say so if the plan should consume rather than build. The EM routes the cross-repo ask.

### Platform-capability copy-out bucket — "a sibling already solved this shape"

**Plan-mode only.** A second section beside the consume bucket: the plan constructs infrastructure or tooling (environment, harness, gate, test pattern, pipeline) matching a shape a repo declared in its manifest `shapes[]`.

- **No polarity.** The source may be any repo; only a source equal to the plan's own repo suppresses the entry.
- **Offer-shape.** `"<source_repo> has already solved <shape_label>; lift from <exemplar_path>"`. A `copy_posture: ask-the-owner` entry is a coordination prompt to the owner, never a lift instruction.
- **Maturity is fail-closed**, with "confirm exemplar before lifting" on `stale`/`unverified`.
- **Action:** as for the consume bucket.

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

