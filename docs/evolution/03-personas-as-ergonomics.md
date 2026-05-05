# 03 — Personas as Ergonomics

> The honest version of the persona story. Detailed reviewer profiles didn't improve recall and increased false positives. Calibration blocks, not character depth, are what actually move the needle.

## What we wanted to be true

The intuition was tempting: a richer reviewer prompt — "Patrik is a Slovak staff engineer with 15 years of C++ experience and exacting standards" — should produce better reviews than a bare "review this code for bugs." The model should *role-play* expertise and find things a generic reviewer would miss.

We ran a controlled experiment to test this. 400 paired observations across 10 TypeScript/JavaScript files with 32 seeded defects, scored mechanically against ground truth. The full results are in [the persona experiment artifact](../research/2026-03-26-persona-experiment-results.md).

## What was actually true

The detailed prompt (34 lines, with domain checklists, structured multi-pass review process, "assume the code has defects" framing) produced **the same true-positive rate as the bare 2-line prompt**, and generated **1–2 extra false positives per file**.

That was not the result we expected. We thought richer prompting should help. It didn't.

## Why we kept the personas anyway

Two reasons.

**First, ergonomics for the human user.** "Patrik flagged this" is more memorable and parseable than "the staff engineer review of this artifact returned the following findings." The PM remembers Patrik. The PM does not remember the staff engineer. When seven reviewers exist (Patrik, Sid, Camelia, Palí, Fru, Zolí, YK), names are how the human keeps them straight. The personas earn their keep on the human-comprehension side, not the reviewer-quality side.

**Second, the personas don't *cost* anything that the calibration block doesn't fix.** The false-positive bump in the experiment came from over-aggressive prompting — "assume the code has defects, a review finding no issues is almost certainly incomplete." We replaced that pressure with a confidence calibration scale (1–10) and an AUTO-FIX/ASK fix classification, applied to every finding. The integrator filters low-confidence findings out before they reach the EM. That mechanism — not the persona richness — is what controls false positives.

If you removed the personas tomorrow and replaced them with anonymized "reviewer-1, reviewer-2, reviewer-3," the technical quality of reviews would be unchanged. The PM ergonomics would degrade.

## What the calibration block does

Every reviewer carries a synced block (`<!-- BEGIN reviewer-calibration -->`) that does the actual work:

- Each finding gets a confidence score 1–10 with explicit anchors.
- Findings under 5 are not surfaced inline — they go in a low-confidence appendix the integrator filters out.
- Each finding is classified AUTO-FIX or ASK. AUTO-FIX requires confidence ≥ 8.
- Math/algebra/precedence findings are always ASK regardless of confidence (they require independent verification).
- Cross-agent convergence (≥2 independent agents flagging the same issue from different entry points) bumps confidence by 2.

This is the structural answer to "how do we get more signal and less noise." It's not glamorous. It works.

## The "false positives + AUTO-FIX = silent damage" trap we avoided

If detailed prompts raise false positives, *and* the system silently applies low-confidence findings via AUTO-FIX, the result is bad fixes shipped without review. The calibration block fixes both halves of that trap: false positives below 5 don't surface, and AUTO-FIX is gated at confidence ≥ 8. The math/algebra exception is the further catch — even high-confidence symbolic-reasoning findings require independent verification.

We didn't get this right immediately. The early version applied findings more aggressively. The convergence rule, the AUTO-FIX threshold, and the math/algebra exception all entered the doctrine after specific incidents where the early version mis-applied a low-confidence finding.

## What this means for new reviewers

When a new reviewer is added (YK, the most recent), the contract is:

1. Carry the calibration block verbatim, synced from `snippets/reviewer-calibration.md`.
2. Have a clearly bounded scope — what this reviewer *is for* and what they *aren't for*. Overlap with existing reviewers wastes cycles.
3. Have a verdict format consistent with the others (APPROVED / APPROVED_WITH_NOTES / REQUIRES_CHANGES / REJECTED).
4. Output a JSON block with `reviewer`, `verdict`, `summary`, and `findings` arrays. Reviewer-specific fields (e.g., YK's `shape_assessment` and `refactor_recommendation`) are additive.

The persona — name, voice, character description — is the *least* important part of the reviewer file. It's there for human ergonomics. The calibration block, the scope statement, and the JSON output format are what make the reviewer load-bearing.

## What we'd revisit if the data changed

If a future experiment found a regime where character depth materially improved recall — perhaps very long artifacts where the reviewer benefits from sustained role-immersion — we'd update this chapter and probably enrich the persona prompts. The current data does not support that, and "richer prompts work better" is not a hypothesis we should privilege without evidence.

The honest version of the persona story is: the ergonomics are real, the rigor lives elsewhere, and we'd rather say that explicitly than let the persona aesthetic carry weight it can't bear.
