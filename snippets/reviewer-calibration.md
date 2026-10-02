<!-- canonical source for reviewer-calibration — edit here, then run bin/verify-snippet-sync reviewer-calibration --fix -->
<!-- consumers: see bin/snippet-registry list-consumers reviewer-calibration -->

## Confidence Calibration (1–10)

Every finding carries a confidence rating. Anchors:
- 10 — directly contradicts canonical doctrine (CLAUDE.md / coordinator CLAUDE.md / agreed-on style file). Auto-floor.
- 8–9 — high confidence: cited spec, reproducible test failure, or convergent with a separate signal.
- 6–7 — substantive concern; reasoning is clear but the rule isn't black-and-white.
- 5 — judgment call; reasonable engineers could disagree.
- < 5 — speculative, stylistic, or unverified. Do not surface inline. Place in a "Low-Confidence Appendix" at the bottom of the review; the EM reads it only if asked.

Bumps:
- +2 if a separate independent signal flags the same issue from a distinct entry point (convergence — threshold is independence + distinct entry points, not raw count).
- Auto-8 floor for any finding that contradicts canonical doctrine.

Calibration check: if every finding you flagged is 8+, you are miscalibrated. Reread your rubric.

**Word-delta calibration.** When the artifact under review is a small textual edit (≤ ~20 words changed, no structural change, no new doctrine), default-anchor confidences in the 5–7 band rather than 8+. The smaller the diff, the smaller the surface for high-confidence violations — sweeping 8s on a 12-word edit means the calibration is anchored on hypotheticals beyond the diff. Findings that genuinely contradict canonical doctrine still floor at 8 (the auto-8 floor); the rule is about the default, not the ceiling.

## Fix Classification (AUTO-FIX vs ASK)

Classify every finding:
- **AUTO-FIX** — a senior engineer would apply without discussion: wrong API name, wrong precedence, missing import, factual error, contradicts canonical doctrine.
- **ASK** — reasonable engineers could disagree: architectural direction, scope vs polish, cost vs value. Flag prominently; the EM may revert one via `review-findings-ledger reject`.

You apply both classes yourself, in place.

AUTO-FIX requires confidence ≥ 8; 5–7 defaults to ASK; < 5 is not surfaced.

**Math, algebra, precedence exception:** symbolic-reasoning findings are ASK regardless of confidence. If also P0/P1, the EM or a verifier confirms against current source before acting — sweep-agent claims there have a poor track record.

**Substrate re-verification before executor dispatch.** Even when a reviewer pre-resolves a substrate value via `@import` or a quoted constant, the executor `ls` / `Read`s the cited path first — it may have moved since review-time.

**Review-staleness pre-flight.** Findings age between write-time and apply-time. Before dispatching a reviewer, the EM re-verifies named paths and shape claims against current HEAD and briefs any drift; findings older than ~2 hours on a hot branch get a re-verification pass.

**SSOT claims have a scope.** They apply within-artifact, not cross-ecosystem, unless cited as cross-repo authority.

**False-positive patterns to suppress.**

- `try/except ImportError` blocks are seam-fallback idioms, not a bug — don't flag unless the fallback path is unsound.
- Privacy/contamination findings on structured artifacts (JSON, JSONL, YAML with explicit schema) are hypothesis until verified against the schema (`additionalProperties`, `properties`, declared fields); an off-schema-field claim the schema disproves is a false-positive.
