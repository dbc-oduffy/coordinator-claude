<!-- canonical source for plan-coverage-check-consumption — edit here, then run bin/verify-snippet-sync plan-coverage-check-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers plan-coverage-check-consumption -->

<!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->
## Plan Coverage Check Integration

If your dispatch prompt cites a **plan-coverage-check pre-flight** with a sidecar path (the engine-provisioned `.coordinator-local/plan-sidecars/<plan-stem>.plan-coverage-check.md` home, passed through unchanged), the plan has been mechanically checked for internal completeness across three lenses: does the fix slate cover the audit oracle, are deferrals architecturally justified, and do in-repo citations match disk? The EM folded any INCOMPLETE findings into the plan before dispatching you — you read the post-fold version.

**Three lenses, three sidecar sections:**

- **Coverage** — matches every audit/findings oracle item to the fix slate by shared file-path, symbol, or distinctive noun phrase. Items absent from the slate (and not Out-of-Scope with an architectural reason) surface as MISSED.
- **Hedge / Defer detection** — greps the plan body for appetite-based deferral language ("follow-up", "future work", "TBD", "defer to") lacking architectural justification. Considered-Alternatives, Risks, Out-of-Scope headings, and blockquotes are suppressed.
- **Substrate drift** — verifies cited in-repo paths, symbols, and constants exist on disk. Line-number drift alone is tolerated; a missing file or absent symbol is a finding.

**Sidecar buckets (audit trail):**

- **Missed audit items** — oracle items with no slate entry and no architectural OOS justification. The EM resolved each by **add-to-slate**, **architectural-OOS**, or **oracle-was-wrong**. Not yours to re-litigate; flag a NEW gap the lens missed.
- **Ambiguous audit items** — signal-partial matches. Informational, never gate INCOMPLETE; the EM has read them. Flag a finding only for a gap you independently identify.
- **Weak-OOS / hedges** — appetite-based deferrals the EM promoted to the slate or rewrote with an architectural reason; you read the post-rewrite plan.
- **Substrate-drift items** — drifted citations, amended or explained by the EM; not your concern once resolved.

**Verdict semantics:**

- **COMPLETE** — zero MISSED, zero weak-OOS, zero substrate-drift (AMBIGUOUS items do not affect it). Review on architecture alone.
- **INCOMPLETE** — findings existed and the EM folded them in. Do not re-litigate closed findings; flag any novel gap.

**INCOMPLETE sub-label** — the verdict line gains `INCOMPLETE — Mechanical: N, Judgment: M`. Mechanical = Substrate-drift count (Lens 3); Judgment = Missed + Weak-OOS + Hedges (Lens 1 + 2).

- **BLOCKED-SURFACE-TO-PM** — ≥20% of oracle items MISSED (MISSED alone, not MISSED+AMBIGUOUS), OR ≥3 substrate-drift findings suggesting a stale tree. The EM has PM authorization to proceed — verify the plan body documents it before approving.
- **SCOPE-MISMATCH** — no oracle table located; the lenses did not run. Review as if no pre-flight ran.
- **DEGRADED** — incomplete coverage (token cap, oracle parsing ambiguity). Treat as no signal; review as if no pre-flight ran.

**Fold-before-reviewer, unlike prior-art-checker.** Its WARN sidecar reaches you unfolded and you land the corrections yourself. Coverage gaps have three mechanical EM resolutions needing no reviewer judgment, so INCOMPLETE findings fold BEFORE you; the sidecar is audit trail, not open questions.

**The plan-coverage-checker is mechanical, not judgmental** — it can over-match and under-match. You supplement it, you do not ratify it; surface a MISSED finding the fold resolved incorrectly.

**When no plan-coverage-check pre-flight ran**, this integration is silent — proceed as normal.

### Coverage findings vs. your own findings

If you also identify a gap that overlaps a sidecar Missed or Ambiguous item, label it "reinforces plan-coverage-check [Missed/Ambiguous] item #N" — convergence between an independent reviewer and the mechanical lens is high-confidence signal for fix prioritization.
<!-- END plan-coverage-check-consumption -->
