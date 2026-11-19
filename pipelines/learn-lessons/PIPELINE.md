# learn-lessons — local flow pipeline

> Referenced by `coordinator/skills/learn-lessons/SKILL.md`. A pipeline definition, not an invocable skill.

Local mode runs `prepare -> triage workflow -> finalize -> bounded grind`. Only the triage workflow
and the grind spawn agents; prepare and finalize are `lessons_mechanical.py`, `agent_spawns: 0`.

| Leg | Component | Reads | Writes |
|---|---|---|---|
| prepare | `lessons_mechanical.py prepare --repo-root R [--run-dir D] [--dry-run] [--age-cutoff Y-M-D \| --age-days N]` (`--repo-root` is required, never cwd) | `R/state/lessons` | `D/prepared.json`, `D/synth-batch-NN.json`; closure moves under `R/archive/lessons` |
| triage | `lessons-triage.workflow.js`, args `{prepared, budget_tokens}` | `prepared` inline | returns `synth_results`, `budget_ledger` |
| finalize | `lessons_mechanical.py finalize --run-dir D [--budget-tokens N]` | `D/prepared.json`, `D/synth-results.json`, `D/budget-ledger.json` | `D/records/<id>.json`, `D/finalize-report.json`; an upheld `wiki-new`'s page, `_index.md` link and register row in `R` |
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
  missing or blank, or a row the engine names `unreadable`: reported in `prepared.malformed`, row untouched, never triaged, handed back by
  finalize), `discard` (whole body verbatim in an index-reachable wiki page) and `wiki-append`
  (body absent from an index-reachable wiki page the lesson names). A payload lesson carries no
  verdict or change-kind, and carries `homes`: at most `HOMES_MAX` index-reachable wiki pages, the
  only targets a `wiki-append` or `dedupe` verdict may name; with none fitting, triage proposes
  `wiki-new`. Rules: the wiki page below.
- A payload lesson body is capped at `LESSON_BODY_BYTES`. Each triage batch gets at most one refute
  call, over slim rows (title, a `REFUTE_EXCERPT_CHARS` excerpt, homes, verdict); it skips `wiki-new`
  and `wiki-append` verdicts, which finalize proves on disk, and records them upheld unchecked. A
  `wiki-new` naming a page this finalize already created, or an existing index-reachable page, appends to it. Only refute-upheld `discard`, `dedupe`, `wiki-append` and
  `wiki-new` verdicts apply. An overturned or unappliable verdict, or an unreadable row, is handed back
  to the EM (`handed_back`, with its `reason`), who rules it in `em-rulings.json` at no agent cost; only a
  refute-upheld code-edit verdict (hook, script, agent-prompt, snippet-sync, project-structural) reaches
  the grind, which needs a tool-using fixer. An unrefuted row,
or one the triage call returned no verdict for, stays open for the next triage run, never the grind; the
report lists it under `unrefuted`, and it is still owed. A `wiki-new`
  applies when its target is a new `.md` inside the repo under a directory with an index: an `_index.md`,
  else a table index already linking pages in that directory: `DIRECTORY_GUIDE.md` or `README.md` beside
  the page, then `docs/README.md` (index-reachability reads them all). Finalize writes the page
  (`## <title>` plus body), the index link (an `_index.md` list item, or a table row in name order with the
  title in its last cell) and the classified register row, then archives the lesson. A target that exists
  unindexed, escapes the repo, is not `.md` or has no index is `unappliable`. A `discard` that
  names no target closes the row; any other target must be an existing repo file. A `wiki-append`
  lands the body without any leading `---` frontmatter block (memory-rerouted rows carry one).
- A tool-less refute cannot know a later ruling. The EM records rulings in
  `<run_dir>/em-rulings.json`: `{lesson id: reason}` or `{kind: discard, reason}` closes the row as
  `discard` whatever triage said, and every `[[link]]` to it is dropped from written pages with its
  Related/See clause; `{kind: annotate, note}` keeps the triage verdict and appends the note as the
  page text's current status.
- A written page carries the lesson's title, or for a slug title its short frontmatter description or
  the slug in words; a `[[link]]` naming an existing wiki page becomes a relative markdown link.
- Budget is measured input plus output tokens. A call is admitted only while measured spend plus its
  projected cost fits `budget_tokens`; a refused call hands its rows back `budget-exhausted`.
- `finalize-report.json`: `residue_for_grind`, `unrefuted`, `budget_exhausted`, `handed_back`, `malformed`, `deferred`,
  `remaining_budget`, `agent_spawns`, `grind_seeds`, `unappliable`. `remaining_budget` is the grind's
  `budget_tokens`. `grind_seeds` holds one `{id, verdict, target, evidence, tests}` per refute-upheld
  residue row; the emitter may enter that row at fix with the seed as its verdict. Overturned rows carry
  none and take the full `lessons` graph.
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
