---
title: Prior-Art Check — plan-coverage-rework-burden-reduction
created: 2026-06-09
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md`
**Verdict:** WARN
**Claims checked:** 16
**Conflicts:** 1 | **Compatible-but-relevant:** 8 | **Silent:** 7

> Sidecar written EM-side 2026-06-09 because the prior-art-checker subagent was blocked by `block-subagent-plan-body-write.sh` over-catching `.prior-art-check.md` suffix. Subagent returned findings as inline text; EM verified Claim #8 against the precedent (refuted) and ratified the remaining buckets. Hook over-catch is a separate workstream — surfaced to improvement queue.

### Conflicts (plan contradicts prior art)

- **Claim #10 — hook WARN-default vs. calibration-not-sufficient doctrine (LEAN: both / update-plan).** Plan ships WARN-default hook with strict opt-in via `COORDINATOR_AC_GRAMMAR_STRICT=1`. `writing-plans.md` lines 444-446 (calibration-not-sufficient): *"Ship the enforcement layer (the hard gate, the hook that fails loud, the validator) in the same plan, not as a deferred follow-up."* Surface tension: plan ships calibration-only (WARN) at authoring time. **Resolution:** the three-altitude design (hook → oracle [Lens 4 retiring] → runtime gate) already has enforcement at the bottom — the runtime gate at workstream-complete Step 3.8 IS the enforcement layer. The plan should cite the *"Teeth at the backstop license carrots upstream"* passage explicitly in C1 hard constraints to anchor the WARN-default choice. Action: update plan body to cite the doctrine pair and resolve the apparent conflict.

### Compatible-but-relevant (cite or align)

- **Claim #5 (HIGH) — snippet-sync gap.** `snippets/plan-coverage-check-consumption.md` (broadcast to all Opus reviewer prompts via `verify-plan-coverage-sync.sh --fix`) describes the sidecar header schema and references Lens 4 / AC-grammar bucket in 6 places (lines 8, 13, 21, 27, 29, 30). C2 (sidecar header) and C4 (Lens 4 retirement) both mutate surface this snippet describes. C4 must explicitly scope: (a) update snippet to drop Lens 4 / AC-grammar references; (b) update snippet to describe Mechanical/Judgment roll-up; (c) run `verify-plan-coverage-sync.sh --fix` to propagate to reviewer prompts.
- **Claim #7 (HIGH) — TEMPLATE concrete-paths fabrication-vector.** `writing-plans.md` lines 162-163: *"TEMPLATE blocks with substrate-divergent specifics are worse than no TEMPLATE."* The seed AC rows in C3 cite paths that are deliverables of this plan (not on disk at template-author time). Action: rewrite the seed AC rows to use clearly-illustrative paths that demonstrate grammar without asserting substrate (e.g. canonical `pytest:tests/test_foo.py::test_bar` shape rather than naming `validate-ac-grammar.test.js`).
- **Claim #4 — trigger-table update on Lens 4 retirement.** `docs/wiki/plan-coverage-checker.md` carries a trigger row "Plan contains a bindable AC table but NO oracle → Run — Lens 4 alone (sidecar marked Lens-4-only)." After Lens 4 retires, this row needs updating. Add to C4 surface list.
- **Claim #2 — cite `eager-agent-calibration.md` in § Problem set, not only in C4.** The offer-shape doctrine basis for the design choice should appear inline in the problem framing, not only in the doctrine-update chunk.
- **Claim #3 — cite the offer-vs-friction-as-warning fork in C1.** `eager-agent-calibration.md` lines 95-103 give the principled fork between offer-shape (this hook) and friction-as-warning. C1 should cite to anchor the design decision.
- **Claim #1 — cite `hook-best-practices.md` for JSON-shape over exit-code.** C1 hard constraints already imply this; the doc citation makes it auditable.
- **Claim #6 — cite plan-coverage-checker quality-loop doctrine in C3.** `plan-coverage-checker.md` lines 154-158 establish the plan-template-as-quality-loop output. C3 is the artifact of that loop; cite it.
- **Claim #8 — REFUTED.** Prior-art-checker conflated SessionStart hook envelope (additionalContext NOT honored without deny) with PreToolUse hook envelope (additionalContext IS honored without deny — precedent at `validate-frontmatter-schema.js:264-269, 300-305, 364-366`). PreToolUse + additionalContext + no deny is the established shape. False positive; no action.

### Silent areas

Claims #9, #11, #12, #13, #14, #15, #16 — no prior art found. Acceptable for new structural surfaces.

### Verdict logic

**WARN** — one conflict (Claim #10) resolvable by citing the backstop-license-carrots passage; three high-priority compatible-but-relevant items (Claims #5, #7, plus the snippet-sync gap which materially expands C4 scope). Integrate before the Staff Engineer dispatch.

**Cost estimate:** ~8K tokens
