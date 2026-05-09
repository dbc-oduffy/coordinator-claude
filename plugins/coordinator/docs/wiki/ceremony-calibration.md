# Ceremony Calibration

> When to invoke heavyweight ceremony (plan-pipeline, brainstorm, sizing pass, skill extraction, retirement) vs lightweight action (direct dispatch, in-place patch, demote-don't-retire, wait-for-instance-3). The pipeline (enrichment → review → execution → integration) is cheap relative to shipping broken work, but applying it to *every* decision is its own waste. Calibrate process weight to actual decision weight.

This wiki synthesizes nine recurring patterns into a single calibration vocabulary. None of the rules are novel; the leverage is in having one place to point when a sibling EM (or a future you) is choosing process weight.

## TL;DR — the calibration axis

For any candidate action, three questions decide the ceremony level:

1. **Is the decision novel, or a surgical follow-up to a decision already made?** Novel → ceremony. Surgical → direct dispatch.
2. **Does the entry have an established occupancy pattern, or is it instance #1?** Pattern with ≥3 instances → extract / promote / refactor. Single instance → wait.
3. **Is the framing concrete enough to enter the plan-write pipeline, or vague enough to need brainstorming first?** Concrete → plan. Vague → brainstorm.

The default failure mode is over-ceremony on surgical work and under-ceremony on novel work — both produce drag, both are visible in retrospect, neither is visible at decision time without this rubric.

## Plan-vs-direct-dispatch

**Plans default to decisions, not questions.** Reviewer-questions in a plan body indicate undelegated decisions the plan author had context to make. If the plan reads "should X or Y?", the plan isn't done — answer it. The decision-tree skill (`coordinator:plan` Branch C) codifies this: questions in the plan body are a doctrine violation, not a feature.

**Cluster execution = full ceremony on the novel item, direct dispatch on surgical follow-ups** with explicit file-scope partitioning. The first item in a cluster typically introduces the pattern; subsequent items apply it to adjacent files. Running the full enrichment pipeline on the novel item earns the ceremony; running it on the follow-ups doesn't — direct dispatch with the file-scope partitioning declared up front is sufficient. Failure mode: re-running ceremony on follow-ups buries genuinely novel reviews under serial process noise.

## Vague-vs-concrete framing

**`/brainstorming` is for vague requirements, not well-scoped follow-ups.** When the PM says "build X and the way is clear," skip brainstorm — go straight to plan. When the PM says "we should probably do something about Y" with multiple plausible shapes, brainstorm. The signal is whether the action's *shape* is contested, not whether it's hard. Hard-but-clear → plan. Easy-but-shape-unknown → brainstorm.

## Pattern-extraction calibration

**Wait for instance #3 before extracting a pattern into a skill.** One-off looks like noise. Two might be coincidence. Three is a pattern. The cost of premature extraction is a skill that codifies the wrong invariant — and once codified, the wrong invariant is harder to correct than the original ad-hoc behavior. Hold instance-#1 and instance-#2 in `tasks/lessons.md` with a `recurring:` count; promote on the third surfacing. (Codified in `coordinator/CLAUDE.md` § Self-Improvement Loop.)

**Null-result audits fold the rule into the producer skill, not just the report.** When an audit finds "this didn't happen because X," the producer-side surface (the skill that should have made X happen) is where the rule belongs — the audit report itself is read once and dies. Audit reports without producer-side fixes are observation theater.

## Retirement calibration

**Demote-don't-retire beats empirical retirement criteria for legacy surfaces.** Three-tier gating — *active* / *demoted* / *retired* — terminates the deprecation question without indefinite limbo. Empirical retirement criteria ("when usage drops below N") sound disciplined but trap the surface in perpetual review-cycle limbo when usage is non-zero but minor. Demote first, retire later, never leave open-ended.

**Pair with: calibrate deprecation-cycle posture to consumer count, not general best-practice.** At two consumers, direct ship. The general "deprecation cycle" rubric is for surfaces with diffuse external consumers; in-tree surfaces with N≤2 known consumers can be migrated in one commit. Don't import enterprise deprecation pacing into a setup where the consumers are visible in `git grep`.

## Authorial-latitude conventions

**Bind sub-disciplines at the latitude site, not in separate stanzas.** When a convention says "executor decides X but must follow Y," the Y constraints belong on the same line as the X latitude — separating them lets executors read the latitude and miss the binding. Pattern: "Authorial latitude on phrasing; vocabulary stays disciplined per `CONTEXT.md`" beats "Authorial latitude on phrasing." (later) "Vocabulary stays disciplined." A sub-discipline two stanzas away from the freedom it constrains is an unenforced rule.

## Sizing-pass calibration (deep-research)

**Sizing pass before deep research:** parallel Sonnet sizing scouts (~30 min each) decide per-repo depth before committing Pipeline B. The sizing pass is itself a calibration step — it answers "is this worth the full pipeline, or does a stub-and-prod read suffice?" Skipping it commits the heavyweight pipeline on every entry, which is the same failure mode as running plan-ceremony on surgical follow-ups: ceremony applied uniformly is ceremony wasted.

**Asymmetric defaults + override conditions in scope.md produce sharper synthesis than balanced surveys.** Declare per-layer defaults explicitly: "Layer 1 = exhaustive, Layer 2 = targeted, Layer 3 = bypass unless trigger Z fires." Balanced surveys produce balanced (= mediocre) synthesis because every layer gets equal attention regardless of relevance. The asymmetry is the signal.

## Session-end-as-defer is hedging in disguise

Mid-session offering to defer non-blocking work to a future session — "want me to session-end and pick this up next time?" — is the anti-ambition tell. When findings are applicable now, apply them; reserve `session-end` for genuine completion or PM redirect. The "we could do less" framing rationalizes the heaviest ceremony available (close out, write a handoff, restart) for what's actually a tradeoff between two minutes of work and an hour of context-loss next time. Default: keep going. Only invoke session-end when it's the *cheapest* remaining action, not the easiest *to ask permission for*.

## Negative space — what doesn't earn ceremony

- **Naming, formatting, file location** — implementation discretion, EM acts.
- **Tradeoff-free reviewer fixes** — apply via integrator, surface to PM only on real tradeoffs (`coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify).
- **Tool choice within an established pattern** — direct dispatch unless cost/risk shifts materially.
- **Whether to commit/branch/stash** — never ask.

## Companion doctrine

- `docs/wiki/writing-plans.md` — plan-pipeline mechanics
- `docs/wiki/writing-skills.md` — skill-extraction mechanics
- `docs/wiki/document-bloat-trim.md` — when CLAUDE.md vs wiki is the right surface
- `coordinator/CLAUDE.md` § Self-Improvement Loop — instance-#3 rule, lessons cadence
- `coordinator/CLAUDE.md` § Plan-First Workflow — plan-skill invocation discipline
- `coordinator/CLAUDE.md` § Challenging the PM — what to ask vs what to act on
