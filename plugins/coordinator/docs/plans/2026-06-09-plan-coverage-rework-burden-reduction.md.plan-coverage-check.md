---
title: Plan Coverage Check - 2026-06-09-plan-coverage-rework-burden-reduction
created: 2026-06-09
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md
---

## Plan Coverage Verification

**Plan:** plugins/coordinator/docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md
**Verdict:** COMPLETE
**Oracle items:** n/a (Lens-4-only run)
**Slate items:** n/a
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** n/a (skipped) | **AC-grammar:** 0

> **Lens-4-only run.** The plan carries a PM-ratified inline problem set (problem_set: inline, ratification blockquote confirmed at plan line 21) and a bindable Acceptance Criteria table with a Binding-Class column. The problem set describes root-cause narrative (P1/P2/P3) rather than a defect-item oracle suitable for Lens 1 cross-reference. The PM pre-assessed this as no audit oracle. Per Phase 1 control flow, Phases 2-4 (Lens 1-3) are skipped; Lens 4 runs alone and drives the verdict.

---

### Missed audit items (no slate entry, no architectural OOS)

None -- Lens 1 not applicable (Lens-4-only run).

---

### Ambiguous audit items (signal-partial -- informational only)

None -- Lens 1 not applicable (Lens-4-only run).

---

### Weak OOS / hedges (appetite-based deferrals)

None -- Lens 2 not applicable (Lens-4-only run).

---

### Substrate drift (in-repo paths/symbols cited that do not match disk)

Skipped -- Lens 3 not applicable for Lens-4-only runs per Phase 1 control flow.

---

### AC Test-cell grammar (gate-bound rows that do not parse against S1-S4 + per-prefix arg-shape)

**AC table location:** ## Acceptance Criteria section (lines 177-186 of plan). Columns present: ID, Criterion (prose), Test, Binding-Class, Status. All required columns confirmed.

**Gate-bound rows processed:** AC1, AC2, AC3, AC4, AC5. AC6 is reviewer-judgment -- skipped per protocol.

**Disk verification of path-side citations:**
- plugins/coordinator/hooks/hooks.json -- EXISTS
- plugins/coordinator/bin/check-acceptance-oracle.sh -- EXISTS
- plugins/coordinator/agents/plan-coverage-checker.md -- EXISTS
- plugins/coordinator/docs/wiki/writing-plans.md -- EXISTS
- plugins/coordinator/hooks/scripts/validate-ac-grammar.test.js -- MISSING (expected: Status is pending realization; C1 creates it; node: prefix not subject to cited: disk-existence checking)

**Per-row results:**

**AC1** Test cell (verbatim from plan table): backtick grep:validate-ac-grammar@plugins/coordinator/hooks/hooks.json backtick
- Shape: S3 whole-cell wrap (opening backtick, prefix:value, closing backtick, no trailing prose). VALID.
- Arg-shape (grep:): @ separator present; pattern = validate-ac-grammar; path = plugins/coordinator/hooks/hooks.json. Path exists on disk. VALID.

**AC2** Test cell (verbatim from plan table): backtick-node:-backtick plugins/coordinator/hooks/scripts/validate-ac-grammar.test.js
- Shape: S2 prefix-wrap (backtick node: backtick followed by space then selector). VALID.
- Arg-shape (node:): bare file path, no :: present. Valid <path> form. Referenced file does not yet exist -- expected for pending realization; node: prefix not subject to cited: disk-existence checking. VALID.

**AC3** Test cell (verbatim from plan table): backtick bash:plugins/coordinator/bin/check-acceptance-oracle.sh plugins/coordinator/templates/plans/plan.md.tmpl backtick
- Shape: S3 whole-cell wrap (opening backtick, bash:script args, closing backtick, no trailing prose). VALID.
- Arg-shape (bash:): script path is repo-relative, no leading /, no .. traversal. Trailing argument is valid [args...]. Script exists on disk. VALID.

**AC4** Test cell (verbatim from plan table): backtick grep:Mechanical:@plugins/coordinator/agents/plan-coverage-checker.md backtick
- Shape: S3 whole-cell wrap. VALID.
- Arg-shape (grep:): @ separator present; pattern = Mechanical:; path = plugins/coordinator/agents/plan-coverage-checker.md. Path exists on disk. VALID.

**AC5** Test cell (verbatim from plan table): backtick grep:three altitudes@plugins/coordinator/docs/wiki/writing-plans.md backtick
- Shape: S3 whole-cell wrap. VALID.
- Arg-shape (grep:): @ separator present; pattern = three altitudes (space in pattern is legal -- @ is the separator boundary); path = plugins/coordinator/docs/wiki/writing-plans.md. Path exists on disk. VALID.

**AC-grammar finding count: 0.** All five gate-bound rows parse cleanly against S1-S4 shapes and per-prefix arg-shapes.

---

### Self-audit advisory (informational -- body prose, outside Lens 4 AC-section scope)

The PM requested a self-audit signal: the plan proposes retiring Lens 4 and seeds three known-good AC rows in the C3 chunk body prose (lines 143-148), labeled by shape. Lens 4 lints only the ## Acceptance Criteria section; body-prose seed rows are outside its scope. One labeling inconsistency found -- reported here as advisory, not as an AC-grammar finding.

**Finding: Template seed AC1 label mismatch (C3 body prose, line 143 cell vs line 147 label).**

Plan body line 147 (explanatory parenthetical) labels seed AC1 as: AC1 is S1 bare grep:pattern@path

The Test cell at line 143 has opening and closing backticks framing the entire value -- that is S3 whole-cell wrap, not S1 bare. S1 bare has no outer backtick delimiters. A genuine S1 bare exemplar would contain just the bare prefix:value form (grep:validate-ac-grammar@...) with no surrounding backticks.

Both shapes are valid grammar; the issue is only in the label. The seed row itself passes the runtime grammar gate -- this is a documentation error in the explanatory comment, not a runtime grammar error.

**Impact on template goals:** C3 aims to demonstrate three distinct shapes (S1/S2/S3) so authors learn the grammar by mimicry. With the current seed content, seed AC1 and seed AC3 both demonstrate S3 whole-cell wrap, and S1 bare is never shown. The template loses one of its three distinct exemplar shapes.

**Suggested correction (EM decision -- not a grammar gate):**
- Option A: Rewrite seed AC1 Test cell to genuine S1 bare -- remove the outer backticks so the pipe-delimited cell contains just the bare prefix:value. Update the parenthetical label (the intent S1 bare was correct). This directly provides the missing S1 exemplar.
- Option B: Keep S3 cell, relabel the parenthetical from S1 bare to S3 whole-cell, add a separate S1 bare example row or comment.
- Option A is lower-friction and provides the missing S1 exemplar the template currently lacks.

---

### Verdict logic

**COMPLETE -- Lens-4-only.** Zero AC-grammar findings in the ## Acceptance Criteria section. All five gate-bound rows (AC1-AC5) parse cleanly against S1-S4 shapes and per-prefix arg-shapes. AC6 is reviewer-judgment, not subject to grammar linting.

The self-audit advisory (S1 vs S3 labeling inconsistency in C3 body prose) is informational and does not count toward INCOMPLETE -- Lens 4 gates only on the ## Acceptance Criteria section, not body prose. EM may correct the label or the cell before C3 dispatch at their discretion.

**Mechanical / Judgment breakdown:** 0 mechanical findings | 0 judgment findings (Lens 1-3 not run; Lens-4-only verdict).

---

**Cost estimate:** approx 3,800 tokens (1 plan read + 5 disk path verifications; Lens 1-3 skipped per Lens-4-only control flow)
