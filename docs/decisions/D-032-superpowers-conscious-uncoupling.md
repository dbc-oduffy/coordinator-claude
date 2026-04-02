# D-032: Superpowers Conscious Uncoupling

**Date:** 2026-04-02
**Status:** Decided
**Decision:** Remove superpowers (obra/superpowers) as a soft dependency. Coordinator-claude becomes fully independent.

## Background

When Claude Code plugins first shipped, superpowers was one of the earliest and most visible entries in the marketplace (131K GitHub stars at time of writing). The name and listed skills — TDD, systematic debugging, plan-before-code, verification-before-done — were exactly what we needed. We installed it immediately, before coordinator-claude existed as a formal plugin system.

Superpowers gave us a running start. Its core skills (TDD enforcement, systematic debugging with escalation, writing plans with placeholder scanning, verification before completion claims) became the behavioral floor we built everything else on top of. Several of those skills were absorbed into coordinator-claude's skill library, adapted with PM/EM terminology and integration points into our orchestration layer. We owe a genuine debt to the superpowers developers for establishing patterns that shaped our early thinking.

## Why We're Going Independent

Over time, the philosophical gap widened. Coordinator-claude evolved capabilities that superpowers doesn't attempt — named persona reviewers, multi-agent research pipelines (Agent Teams-based), session lifecycle management, context pressure hooks, chunk-enrich-review orchestration, autonomous operation modes. More importantly, we developed a fundamentally different trust model.

**Superpowers' model:** The agent is an optimization system that will find shortcuts under pressure. Every skill is hardened with Iron Law blocks, rationalization tables, red flags, and spirit-over-letter clauses. The frame is adversarial — "you WILL try to skip this."

**Coordinator-claude's model:** The agent is an Engineering Manager with defined authority and professional judgment. Structure exists to support good work, not to prevent bad behavior. Quality comes from reviewed plans, sequential review with mandatory fix gates, commit checkpoints, and context pressure hooks — safety nets, not straitjackets. The PM/EM division creates clear authority boundaries that make adversarial hardening less necessary: the EM knows what decisions are theirs to make, which reduces the temptation to rationalize skipping steps.

**Practical friction points:**

1. **Context budget.** Superpowers loads 14 skills + its `using-superpowers` meta-skill into every session. We override most of these with our own versions, paying context tokens for parallel instructions we don't follow.

2. **Delegation philosophy.** Superpowers' SDD (subagent-driven-development) enforces rigid dispatch-vs-inline gates. Our model lets the EM make that call based on task complexity, token efficiency, and professional judgment. A good EM does quick edits inline and delegates complex work — the judgment IS the job.

3. **Role identity.** Superpowers uses "your human partner" — deliberately vague about authority. Our PM/EM model is precise: the PM decides what to build, the EM decides how. This isn't terminology — it's a decision-making framework that eliminates ambiguity.

4. **Platform scope.** Superpowers supports 7 platforms. We're a Claude Code shop. The cross-platform abstractions are dead weight.

## What We Carry Forward

- **Rationalization resistance** (targeted, not blanket): Adding focused "check yourself" tables to our 3 highest-pressure skills, framed as professional discipline rather than adversarial control.
- **Brainstorming / design gate**: Building a PM/EM-native ideation-to-specification skill inspired by superpowers' HARD-GATE pattern.
- **CSO (Claude Search Optimization)**: Skill descriptions must list triggering conditions only, never summarize workflow — an empirically observed failure mode.
- **DONE_WITH_CONCERNS status**: Honest middle ground between "done" and "blocked" for executor reporting.
- **Plan header execution protocol**: Plans carry their own execution instructions for cold-start resumption.
- **Evidence-driven iteration**: Treating design decisions as hypotheses, documenting reversals with reasoning.

## What We Leave Behind

- Iron Law ceremony on every skill (verbose for our trust model)
- Multi-platform adapters and detection logic
- The `using-superpowers` meta-skill (we have our own capability-catalog + skill-discovery)
- `model: inherit` for reviewers (our explicit model selection is a real optimization)
- Monolithic plugin structure (our multi-plugin architecture enables per-project toggling)
- Visual brainstorming server (interesting but not our priority)

## Acknowledgment

Superpowers is excellent software. The anti-rationalization architecture is genuinely novel. The evidence-driven iteration culture (v5.0.6 removing a feature based on regression data across 5 versions x 5 trials) is rare discipline. The 94% PR rejection rate protecting behavioral scaffolding from agent-generated slop is admirable governance. We learned from all of it.

We're not leaving because superpowers is bad. We're leaving because we've grown into something different enough that the dependency creates more friction than value. Different trust models, different audiences, different ambitions. Time to spread our own wings.
