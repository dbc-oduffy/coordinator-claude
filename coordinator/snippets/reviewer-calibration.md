<!-- canonical source for reviewer-calibration — edit here, then run verify-calibration-sync.sh --fix -->
<!-- consumers: see bin/snippet-registry list-consumers reviewer-calibration -->

## Confidence Calibration (1–10)

Every finding carries a confidence rating. Anchors:
- 10 — directly contradicts canonical doctrine (CLAUDE.md / coordinator CLAUDE.md / agreed-on style file). Auto-floor.
- 8–9 — high confidence: cited spec, reproducible test failure, or convergent with a separate signal.
- 6–7 — substantive concern; reasoning is clear but the rule isn't black-and-white.
- 5 — judgment call; reasonable engineers could disagree.
- < 5 — speculative, stylistic, or unverified. Do not surface inline. Place in a "Low-Confidence Appendix" at the bottom of the review; the integrator filters it out unless the EM asks.

Bumps:
- +2 if a separate independent signal flags the same issue (convergence per `coordinator/CLAUDE.md` "Convergence as Confidence").
- Auto-8 floor for any finding that contradicts canonical doctrine.

Calibration check: if every finding you flagged is 8+, you are miscalibrated. Reread your rubric.

**Word-delta calibration.** When the artifact under review is a small textual edit (≤ ~20 words changed, no structural change, no new doctrine), default-anchor confidences in the 5–7 band rather than 8+. The smaller the diff, the smaller the surface for high-confidence violations — sweeping 8s on a 12-word edit means the calibration is anchored on hypotheticals beyond the diff. Findings that genuinely contradict canonical doctrine still floor at 8 (the auto-8 floor); the rule is about the default, not the ceiling.

## Fix Classification (AUTO-FIX vs ASK)

Classify every finding:
- **AUTO-FIX** — a senior engineer would apply without discussion. Wrong API name, wrong precedence, missing import, factual error, contradicts canonical doctrine. The integrator silently applies these and reports a one-line summary.
- **ASK** — reasonable engineers could disagree. Architectural direction, scope vs polish, cost vs value tradeoff. The integrator surfaces these to the EM for routing.

Default rule: AUTO-FIX requires confidence ≥ 8. Findings 5–7 default to ASK. Findings < 5 are not surfaced.

**Math, algebra, precedence exception:** Any finding involving symbolic reasoning is ASK regardless of confidence rating. If also rated P0/P1, the verification gate in `coordinator/CLAUDE.md` ("P0/P1 Verification Gate") applies in addition — the two gates compose.

**Substrate re-verification before executor dispatch.** Even when a reviewer pre-resolves a substrate value via `@import` or by quoting a constant from disk, the executor MUST `ls` / `Read` the cited path before proceeding — defense-in-depth, the cited file may have moved or churned between review-time and dispatch-time.

**Review-staleness pre-flight.** Reviewer findings age between write-time and integrator-apply in concurrent-EM environments. Before integrator dispatch, the EM re-verifies named paths and shape claims against current HEAD; if substrate has shifted, brief the drift in the integrator dispatch prompt explicitly. Findings older than ~2 hours on a hot branch warrant a re-verification pass.

**SSOT claims have a scope.** Reviewer single-source-of-truth claims apply within-artifact, not cross-ecosystem. If a reviewer asserts "X is the SSOT for Y," the EM verifies the scope of the claim — does it cover this artifact only, or does it claim cross-repo authority? Cross-ecosystem SSOT claims need explicit citation; otherwise treat as within-artifact.

**False-positive patterns to suppress.**

- `try/except ImportError` blocks are seam-fallback idioms (graceful runtime degrade between optional dependencies), not a bug. Reviewers should not flag these unless the fallback path is unsound.
- Reviewer privacy/contamination findings on structured artifacts (JSON, JSONL, YAML with explicit schema) are hypothesis until verified against the schema (`additionalProperties`, `properties`, declared field list). If the schema constrains the surface, a "privacy leak" claim asserting an off-schema field exists is a false-positive. Verify the schema before scoping fix work.
