<!-- canonical source for plan-coverage-check-consumption — edit here, then run bin/verify-snippet-sync plan-coverage-check-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers plan-coverage-check-consumption -->

<!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->
## Plan Coverage Check Integration

If your dispatch prompt cites a **plan-coverage-check pre-flight** with a sidecar path (the engine-provisioned `.coordinator-local/plan-sidecars/<plan-stem>.plan-coverage-check.md` home, computed once by `provision_report` and passed through unchanged), the plan has been mechanically checked for internal completeness across three lenses: does the fix slate cover the audit oracle, are deferrals architecturally justified, and do in-repo citations match disk? The EM has folded any INCOMPLETE findings into the plan before dispatching you — you are reading the post-fold version.

**Three lenses, three sidecar sections:**

- **Coverage** — cross-references every audit/findings oracle item against the fix slate, matched by shared file-path, symbol, or distinctive noun phrase. Oracle items absent from the slate (and not marked Out-of-Scope with an architectural reason) surface as MISSED findings.
- **Hedge / Defer detection** — greps the plan body for appetite-based deferral language ("follow-up", "future work", "TBD", "defer to", etc.) lacking architectural justification. False-positives in Considered-Alternatives, Risks, Out-of-Scope headings, and blockquotes are suppressed.
- **Substrate drift** — verifies in-repo paths, symbols, and constants cited in the plan still exist on disk. Line-number drift alone is tolerated; a missing file or absent symbol is a real finding.

**Sidecar bucket vocabulary (for audit-trail reading):**

- **Missed audit items** — oracle items with no slate entry and no architectural OOS justification. The EM resolves each by one of three mechanical paths: **add-to-slate**, **architectural-OOS** (documented, hard constraint), or **oracle-was-wrong** (audit table amended). Not yours to re-litigate; flag a NEW gap the lens missed as a finding.
- **Ambiguous audit items** — signal-partial matches (stopword-only overlap, or a consolidating slate chunk not enumerating covered items). Informational only, do NOT gate INCOMPLETE, and the EM has read them. Flag a finding only if you independently identify a gap within this set.
- **Weak-OOS / hedges** — appetite-based deferrals ("not now", "follow-up") the EM has promoted to the slate or rewritten with an architectural reason. You are reading the post-rewrite plan.
- **Substrate-drift items** — in-repo citations flagged as drifted (file/symbol absent), amended or explained by the EM; not your concern once resolved.

**Verdict semantics:**

- **COMPLETE** — zero MISSED, zero weak-OOS, zero substrate-drift. AMBIGUOUS items may appear in the sidecar for EM read-through but do not affect this verdict. Review on architecture alone.
- **INCOMPLETE** — findings existed and the EM has folded them in; you are reading the amended version. Do not re-litigate closed findings; flag any novel gap you independently identify.

**INCOMPLETE sub-label** — the sidecar's verdict line gains `INCOMPLETE — Mechanical: N, Judgment: M`. Mechanical = Substrate-drift count (Lens 3); Judgment = Missed + Weak-OOS + Hedges (Lens 1 + 2) — the EM's at-a-glance gauge of rework altitude.

- **BLOCKED-SURFACE-TO-PM** — ≥20% of oracle items were MISSED (MISSED count alone, not MISSED+AMBIGUOUS), OR ≥3 substrate-drift findings suggested a stale tree. If you are reading this, the EM has obtained PM authorization to proceed — verify the plan body documents it before approving.
- **SCOPE-MISMATCH** — no oracle table was located; the lenses did not run in a meaningful sense. Review as if no pre-flight ran.
- **DEGRADED** — incomplete coverage (token cap, oracle parsing ambiguity, etc.). Treat as no signal; review coverage fully as if no pre-flight ran.

**Fold-before-reviewer model — how this differs from prior-art-checker.** The prior-art-checker's WARN sidecar travels through to the named reviewer unintegrated; you recommend a direction-of-correction per Conflict, and the integrator lands edits after your review. Plan-coverage-checker INCOMPLETE findings fold BEFORE you — coverage gaps have three EM-mechanical resolutions that don't require reviewer judgment, so you are always reading a post-fold plan; the sidecar is audit trail, not open questions for you to resolve.

**The plan-coverage-checker is mechanical, not judgmental** — it can over-match (flag a slate item the lens couldn't match by topic) and under-match (miss a gap requiring semantic understanding). Your review supplements it, never ratifies it; if a MISSED finding was incorrectly resolved in the fold, surface that as a finding.

**When no plan-coverage-check pre-flight ran**, this integration is silent — proceed as normal.

### Coverage findings vs. your own findings

If you also identify a gap that overlaps a sidecar Missed or Ambiguous item, label it "reinforces plan-coverage-check [Missed/Ambiguous] item #N" — convergence between an independent reviewer and the mechanical lens is high-confidence signal, and the integrator uses it for fix prioritization.
<!-- END plan-coverage-check-consumption -->
