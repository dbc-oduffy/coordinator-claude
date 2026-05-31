<!-- canonical source for plan-coverage-check-consumption — edit here, then run verify-plan-coverage-sync.sh --fix -->

<!-- BEGIN plan-coverage-check-consumption (synced from snippets/plan-coverage-check-consumption.md) -->
## Plan Coverage Check Integration

If your dispatch prompt cites a **plan-coverage-check pre-flight** with a sidecar path (typically `<plan-path>.plan-coverage-check.md`), the plan has been mechanically checked for internal completeness across three lenses: does the fix slate cover the audit oracle, are deferrals architecturally justified, and do in-repo citations match disk? The EM has consumed the sidecar and folded any INCOMPLETE findings into the plan before dispatching you. You are reading the post-fold version.

**Three lenses, three sidecar sections:**

- **Coverage** — cross-references every item in the plan's audit/findings oracle against the fix slate. Items must be explicitly matched by shared file-path, shared symbol, or shared distinctive noun phrase. Items present in the oracle but absent from the slate (and not explicitly marked Out-of-Scope with an architectural reason) surface as MISSED findings.
- **Hedge / Defer detection** — greps the plan body for appetite-based deferral language ("follow-up", "future work", "TBD", "defer to", etc.) and flags cases where the token appears in body prose without an architectural justification. False-positives in Considered-Alternatives, Risks, Out-of-Scope headings, and blockquotes are suppressed at classification stage.
- **Substrate drift** — verifies that in-repo paths, symbols, and constants cited in the plan still exist on disk. Line-number drift alone (same file, same symbol, shifted line number) is tolerated; a missing file or absent symbol is a real finding.

**Sidecar bucket vocabulary (for audit-trail reading):**

- **Missed audit items** — oracle items with no slate entry and no architectural OOS justification. The EM has resolved each by one of three EM-mechanical paths: (1) **add-to-slate** — item was real work, slate row added; (2) **architectural-OOS** — item has a hard constraint (irreversibility, dependency, security boundary), documented in the OOS section; (3) **oracle-was-wrong** — audit item turned out not to be a real issue, audit table amended with explanatory note. These resolutions are mechanical; they are not yours to re-litigate. If you spot a NEW gap the lens missed, flag it as a finding.
- **Ambiguous audit items** — oracle items with signal-partial matches (stopword-only overlap, or a consolidating slate chunk that does not explicitly enumerate covered oracle items). These are informational only; they did NOT gate INCOMPLETE. The EM has read them. Flag a finding only if you independently identify a coverage gap within this set.
- **Weak-OOS / hedges** — appetite-based deferrals ("not now", "follow-up") that the EM has either promoted to the slate or rewritten with an architectural reason. You are reading the post-rewrite plan.
- **Substrate-drift items** — in-repo citations the lens flagged as drifted (file absent, symbol absent). The EM has amended the plan citations or explained the drift. If a drift finding was resolved by amending the plan, the substrate change itself is not your concern here.

**Verdict semantics:**

- **COMPLETE** — zero MISSED, zero weak-OOS, zero substrate-drift. AMBIGUOUS items may appear in the sidecar for EM read-through but do not affect this verdict. Review on architecture alone.
- **INCOMPLETE** — findings existed and the EM has folded them in. The plan you are reading is the amended version. Do not re-litigate the closed findings; flag any novel gap you independently identify.
- **BLOCKED-SURFACE-TO-PM** — ≥20% of oracle items were MISSED (MISSED count alone, not MISSED+AMBIGUOUS), or ≥3 substrate-drift findings suggested the plan was written against a stale tree. If you are reading this, the EM has obtained PM authorization to proceed — verify the plan body documents that authorization before approving.<!-- Review: code-reviewer — clarified that the 20% threshold is computed from MISSED only, not MISSED+AMBIGUOUS, to match the sidecar format section definition. -->
- **SCOPE-MISMATCH** — no oracle table was located in the plan. The lens did not run in a meaningful sense. Review as if no pre-flight ran.
- **DEGRADED** — the agent ran with incomplete coverage (token cap, oracle parsing ambiguity, etc.). Treat as no signal; review the plan's coverage fully as if no pre-flight ran.

**Fold-before-reviewer model — how this differs from prior-art-checker.** The prior-art-checker's WARN sidecar travels through to the named reviewer unintegrated; you recommend a direction-of-correction (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`) per Conflict, and the integrator lands edits after your review. Plan-coverage-checker INCOMPLETE findings fold BEFORE you — coverage gaps have three EM-mechanical resolutions (add-to-slate / architectural-OOS / oracle-was-wrong) that don't require reviewer judgment. You are therefore always reading a post-fold plan. The sidecar is included as audit trail, not as a set of open questions for you to resolve.

**The plan-coverage-checker is mechanical, not judgmental.** It can over-match (flag a slate item the lens couldn't match by topic) and under-match (miss a coverage gap requiring semantic understanding). Your review supplements it; you do not ratify it. If you believe a MISSED finding was incorrectly resolved in the fold, surface that as a finding — your architectural judgment is the primary input, and the sidecar is there to support it, not override it.

**When no plan-coverage-check pre-flight ran**, this integration is silent — your review proceeds as normal. The pre-flight is additive; it does not change your standards, only the division of labor on coverage recall.

### Coverage findings vs. your own findings

If you also identify a gap that overlaps a sidecar Missed or Ambiguous item, label your finding "reinforces plan-coverage-check [Missed/Ambiguous] item #N" — convergence between an independent reviewer and the mechanical lens is high-confidence signal. The integrator uses this for fix prioritization.
<!-- END plan-coverage-check-consumption -->
