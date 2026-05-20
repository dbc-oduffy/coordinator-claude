# Evals

Synthetic public benchmarks are not currently a development priority for `coordinator-claude`. Token budget and opportunity cost rank below shipping the projects that exercise this system in real conditions. The evidence we lean on is named below.

## Evidence threads

Three peer artifacts — no hierarchy implied:

**Controlled experiment with a negative result:**
[`docs/research/2026-03-26-persona-experiment-results.md`](../docs/research/2026-03-26-persona-experiment-results.md) — 400 paired observations, mechanically scored. Shows where named personas add signal (plan/architecture review) and where they don't (mechanical bug detection, where bare Sonnet agents perform at least as well). The negative result is part of the point — it was measured and published, not suppressed. This is the reproducible empirical artifact that addresses the question "did you test this?"

**Productivity-proof corpus:**
[`docs/research/2026-05-08-built-with-coordinator.md`](../docs/research/2026-05-08-built-with-coordinator.md) — six projects shipped or progressed under this workflow in 17 weeks; one PM, no code typed by the PM since December 2025. Production deployments, Steam-packaged game software, a 789-question benchmark at 97.6% accuracy. This addresses the question "does this workflow actually help ship things?"

**Qualitative evidence ledger:**
[`docs/evolution/05-failure-modes.md`](../docs/evolution/05-failure-modes.md) — operational scar tissue from real coordinator-claude sessions, organized by failure-mode taxonomy. False completion, silent scope expansion, test theater, review laundering, context amnesia, integration blindness. The system was designed around these failure modes; this document names them and describes the design responses.

## Benchmark infrastructure

`experiments/` (top-level, not this directory) is the staging ground for benchmark harnesses when budget exists. Current state: two full rigs scaffolded (handoff-vs-compaction, research-pipeline-benchmark) with v1 + v2 implementations and a persistent results database. Harnesses are built; most runs are pending dedicated execution budget. Numbers from unfinished runs are not cited in this document.

If and when benchmark results stabilize, they will land here.
