<!-- canonical source for reviewer-calibration — edit here, then run bin/verify-snippet-sync reviewer-calibration --fix -->
<!-- consumers: see bin/snippet-registry list-consumers reviewer-calibration -->

## Confidence Calibration (1–10)

Every finding carries a confidence rating. Anchors:
- 10 — directly contradicts canonical doctrine (CLAUDE.md / coordinator CLAUDE.md / agreed-on style file). Auto-floor.
- 8–9 — high confidence: cited spec, reproducible test failure, or convergent with a separate signal.
- 6–7 — substantive concern; reasoning is clear but the rule isn't black-and-white.
- 5 — judgment call; reasonable engineers could disagree.
- < 5 — speculative, stylistic, or unverified. Do not surface inline. Place in a "Low-Confidence Appendix" at the bottom of the review; the integrator filters it out unless the EM asks.

Bumps:
- +2 if a separate independent signal flags the same issue from a distinct entry point (convergence — threshold is independence + distinct entry points, not raw count).
- Auto-8 floor for any finding that contradicts canonical doctrine.

Calibration check: if every finding you flagged is 8+, you are miscalibrated. Reread your rubric.

**Word-delta calibration.** When the artifact under review is a small textual edit (≤ ~20 words changed, no structural change, no new doctrine), default-anchor confidences in the 5–7 band rather than 8+. The smaller the diff, the smaller the surface for high-confidence violations — sweeping 8s on a 12-word edit means the calibration is anchored on hypotheticals beyond the diff. Findings that genuinely contradict canonical doctrine still floor at 8 (the auto-8 floor); the rule is about the default, not the ceiling.

## Fix Classification (AUTO-FIX vs ASK)

Classify every finding:
- **AUTO-FIX** — a senior engineer would apply without discussion: wrong API name, wrong precedence, missing import, factual error, contradicts canonical doctrine. The integrator silently applies these and reports a one-line summary.
- **ASK** — reasonable engineers could disagree: architectural direction, scope vs polish, cost vs value tradeoff. The integrator surfaces these to the EM for routing.

Default rule: AUTO-FIX requires confidence ≥ 8. Findings 5–7 default to ASK. Findings < 5 are not surfaced.

**Math, algebra, precedence exception:** any finding involving symbolic reasoning is ASK regardless of confidence. If also rated P0/P1, the P0/P1 verification gate applies too — those claims from sweep agents have a poor track record, so the EM or a verifier confirms against current source before acting, not the agent's paraphrase.

**Substrate re-verification before executor dispatch.** Even when a reviewer pre-resolves a substrate value via `@import` or by quoting a constant, the executor MUST `ls` / `Read` the cited path before proceeding — the file may have moved or churned since review-time.

**Review-staleness pre-flight.** Findings age between write-time and integrator-apply in concurrent-EM environments. Before integrator dispatch, the EM re-verifies named paths and shape claims against current HEAD and briefs any drift explicitly. Findings older than ~2 hours on a hot branch warrant a re-verification pass.

**SSOT claims have a scope.** Reviewer SSOT claims apply within-artifact, not cross-ecosystem, unless explicitly cited as cross-repo authority.

**False-positive patterns to suppress.**

- `try/except ImportError` blocks are seam-fallback idioms, not a bug — don't flag unless the fallback path is unsound.
- Privacy/contamination findings on structured artifacts (JSON, JSONL, YAML with explicit schema) are hypothesis until verified against the schema (`additionalProperties`, `properties`, declared fields); an off-schema-field claim the schema disproves is a false-positive.
