# learn-lessons script-first pipeline

> Referenced by `/learn-lessons` local mode. A pipeline definition, not an invocable skill.

`lessons_mechanical.py prepare --repo R` closes every row a script can, packs the residue into at
most 3 payloads and writes `prepared.json`; the `lessons-synth` Workflow runs at most 3 single-turn,
no-tool `coordinator:lesson-synth` calls under a `budget_tokens` hard stop; `lessons_mechanical.py
finalize --repo R` applies the returned verdicts. `--repo` is required; nothing resolves from cwd.
Closing rules: `docs/wiki/lesson-triage/learn-lessons-mechanical-dispositions.md`. The script never
guesses: `prepare` assigns no change-kind.

## prepared.json (`lessons-prepared/1`)

```json
{
  "schema": "lessons-prepared/1",
  "closed": [{"id": "<lesson stem>", "disposition": "<see below>", "evidence": "<path[:line] or rule>"}],
  "residue_ids": ["<lesson stem>"],
  "deferred_ids": ["<residue id past the third payload>"],
  "synth": {
    "payloads": [{"lessons": [{"id": "...", "body": "...", "...": "..."}], "est_tokens": 0}],
    "schemas": [{"...": "per-call JSON schema, one per payload"}],
    "budget_tokens": 1000000
  }
}
```

- `closed[].disposition` is one of `malformed`, `dedupe`, `discard`, `retag-local`, `wiki-append`,
  `age-sweep`. `evidence` names the citing path (`discard`, `wiki-append`), the surviving row
  (`dedupe`) or the schema field (`malformed`).
- `residue_ids` lists every row not closed, including deferred ones. `synth.payloads` holds at most
  3 entries; a payload never exceeds `SYNTH_PAYLOAD_TOKENS` estimated tokens. Residue that fits no
  payload is listed in `deferred_ids`, never dropped, and is cleared by a further run.
- `budget_tokens` is the `whole_backlog_token_bar` of `coordinator/contract/ceremony-budget.json`.
  The workflow stops before any call that would cross it and returns `budget_stop: true`.
- `prepare` writes nothing under `state/lessons/` beyond closure moves.

## Synth result

One record per lesson id in the synth payloads:

```json
{"id": "<lesson stem>", "verdict": "<lessons.yaml verdict>", "target": "<path or ''>",
 "markdown": "<text to land, or ''>", "cites": ["path:line"]}
```

- `verdict` is a value of `verdicts:` in `coordinator/queue-profiles/lessons.yaml`; never
  `doctrine-edit` or `memory-pointer` (route `doe-escalation`).
- `cites` is required and names the evidence the verdict rests on; a universal row returns
  `universal` for route-to-central.
- The workflow result adds `budget_stop` (bool), `deferred_ids` and `unsent_ids`.

## Fixture and bench

- `make_lesson_queue.py --repo R --count 148 --seed 7` writes a seeded, byte-stable mix under
  `R/state/lessons`: duplicates, covered rules (verbatim in a wiki page the generator also writes
  and indexes), domain-tagged and untagged universals, malformed rows, aged rows, genuine residue.
  It feeds the tests; it is never the measurement.
- `lessons_bench.py --queue-size N --journal J [--journal J2 ...]` prints `{total_tokens, spawns,
  budget_stop, deferred, queued, queue_size, runs, bar, unmeasured_agents, under_bar}`.
  `total_tokens` is the `total` class (cached reads counted with uncached) summed over every
  journal passed; a Workflow run dir's usage is read from `agent-<agentId>.jsonl` beside
  `journal.jsonl`, deduped by `message.id`. `deferred` is the last journal's value; `under_bar`
  needs `total_tokens` under the bar, no budget stop, `deferred` 0 and `unmeasured_agents` 0 (an
  agent that ran with no readable usage).
- `distill_bench.py` (artifact-distillation) has the same journal-only reader blind spot; it is
  outside this plan's footprint.
