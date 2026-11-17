# learn-lessons — local flow pipeline

> Referenced by `coordinator/skills/learn-lessons/SKILL.md`. A pipeline definition, not an invocable skill.

Local mode runs `prepare -> triage workflow -> finalize -> bounded grind`. Only the triage workflow
and the grind spawn agents; prepare and finalize are `lessons_mechanical.py`, `agent_spawns: 0`.

| Leg | Component | Reads | Writes |
|---|---|---|---|
| prepare | `lessons_mechanical.py prepare --repo-root R [--run-dir D] [--dry-run] [--age-cutoff Y-M-D \| --age-days N]` (`--repo-root` is required, never cwd) | `R/state/lessons` | `D/prepared.json`, `D/synth-batch-NN.json`; closure moves under `R/archive/lessons` |
| triage | `lessons-triage.workflow.js`, args `{prepared, budget_tokens}` | `prepared` inline | returns `synth_results`, `budget_ledger` |
| finalize | `lessons_mechanical.py finalize --run-dir D [--budget-tokens N]` | `D/prepared.json`, `D/synth-results.json`, `D/budget-ledger.json` | `D/records/<id>.json`, `D/finalize-report.json` |
| grind | the `lessons` queue-grind profile, `budget_tokens` = `remaining_budget` | `residue_for_grind` | `D/records/` |

The caller saves the workflow's `synth_results` and `budget_ledger` as `D/synth-results.json` and
`D/budget-ledger.json` between triage and finalize.

## Contract

- Shared constants and `BudgetLedger`: `lessons_contract.py`. `DEFAULT_BUDGET` is the lessons slice of
  `whole_backlog_token_bar` in `coordinator/contract/ceremony-budget.json`.
- At most `MAX_SYNTH_CALLS` triage calls, each batch under `SYNTH_BATCH_BYTES`; overflow is
  `prepared.deferred`, handed back, never a further call.
- Prepare closes dedupe, retag and `target_wiki` discard/wiki-append through the engine
  `apply_mechanical` op, then the script rules over the remainder: `malformed` (a required field
  missing or blank: reported in `prepared.malformed`, row untouched, never triaged, handed back by
  finalize), `discard` (whole body verbatim in an index-reachable wiki page) and `wiki-append`
  (body absent from an index-reachable wiki page the lesson names). A payload lesson carries no
  verdict or change-kind. Rules: the wiki page below.
- Each triage batch gets one refute call. Only refute-upheld `discard`, `dedupe` and `wiki-append`
  verdicts apply; overturned, unrefuted and unappliable verdicts become residue. A `discard` that
  names no target closes the row; any other target must be an existing repo file.
- Budget is measured input plus output tokens. A call is admitted only while measured spend plus its
  projected cost fits `budget_tokens`; a refused call hands its rows back `budget-exhausted`.
- `finalize-report.json`: `residue_for_grind`, `budget_exhausted`, `handed_back`, `malformed`, `deferred`,
  `remaining_budget`, `agent_spawns`. `remaining_budget` is the grind's `budget_tokens`.
- Exit 0 ok, 1 a phase halted (the report names it), 2 unusable input.
- No call to the engine `learn_lessons_pipeline` brief or a roots op; discovery reads
  `R/state/lessons` directly.

Measurement: `lessons_bench.py --journal <run journal>` reports `total_tokens`, `agent_spawns` and
`unmeasured_agents` against the whole-backlog bar. A Workflow run directory's usage is read from
`agent-<agentId>.jsonl` beside the journal, deduped by `message.id`, cached reads counted; an agent
that ran with no readable usage forces `within_bar` false. `make_lesson_queue.py --repo R --count 148
--seed 7` writes a seeded, byte-stable lesson mix (duplicates, covered, tagged universals, malformed,
aged, residue) for the tests. Mechanical rules:
`coordinator/docs/wiki/lesson-triage/learn-lessons-mechanical-dispositions.md`.
