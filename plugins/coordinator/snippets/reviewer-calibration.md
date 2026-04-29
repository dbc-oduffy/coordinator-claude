<!-- canonical source for reviewer-calibration — edit here, then run bin/verify-calibration-sync.sh --fix -->

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

## Fix Classification (AUTO-FIX vs ASK)

Classify every finding:
- **AUTO-FIX** — a senior engineer would apply without discussion. Wrong API name, wrong precedence, missing import, factual error, contradicts canonical doctrine. The integrator silently applies these and reports a one-line summary.
- **ASK** — reasonable engineers could disagree. Architectural direction, scope vs polish, cost vs value tradeoff. The integrator surfaces these to the EM for routing.

Default rule: AUTO-FIX requires confidence ≥ 8. Findings 5–7 default to ASK. Findings < 5 are not surfaced.

**Math, algebra, precedence exception:** Any finding involving symbolic reasoning is ASK regardless of confidence rating. If also rated P0/P1, the verification gate in `coordinator/CLAUDE.md` ("P0/P1 Verification Gate") applies in addition — the two gates compose.
