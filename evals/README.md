# Evals

Eval infrastructure for `coordinator-claude` lives in a private workstream
(`X:/experiments`). The framework includes 4 task types (localized bugfix,
feature with tests, refactor with hidden coupling, docs+handoff), a scoring
rubric (completed behavior, regressions, tests passing, manual interventions,
defects caught, false positives, diff quality, elapsed turns, token cost), and
baseline-vs-coordinator comparison runs.

Results land here as they stabilize. See `docs/evolution/05-failure-modes.md`
for the qualitative evidence ledger that complements the eval program.
