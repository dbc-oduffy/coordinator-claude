'use strict';
/**
 * lessons-synth workflow: runs the real script body with an injected agent()/phase()/log() and
 * pins the budget_tokens hard stop, the MAX_SYNTH_CALLS cap, and verdict validation.
 *
 * Run: node --test coordinator/pipelines/learn-lessons/lessons-synth.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = fs.readFileSync(path.join(__dirname, 'lessons-synth.workflow.js'), 'utf8')
  .replace(/^export const meta\b/m, 'const meta');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// Executes the script body exactly as the Workflow runtime would: top-level await and return.
async function runWorkflow(args, agentImpl) {
  const calls = [];
  const agent = async (brief, opts) => {
    calls.push({ brief, opts });
    return agentImpl(calls.length - 1, brief, opts);
  };
  const run = new AsyncFunction('args', 'agent', 'phase', 'log', SOURCE);
  const result = await run(JSON.stringify(args), agent, () => {}, () => {});
  return { result, calls };
}

const lesson = (id) => ({ id, body: `body of ${id}` });
const payload = (ids, est) => ({ lessons: ids.map(lesson), est_tokens: est })
const SCHEMA = { type: 'object' };

function prepared(payloads, budget, extra = {}) {
  return {
    schema: 'lessons-prepared/1',
    closed: [],
    residue_ids: payloads.flatMap((p) => p.lessons.map((l) => l.id)),
    deferred_ids: [],
    synth: { payloads, schemas: payloads.map(() => SCHEMA), budget_tokens: budget },
    ...extra,
  };
}

// An agent that returns one valid wiki-append verdict per lesson id in its payload, plus usage.
function goodAgent(tokensPerCall) {
  return (i, brief, opts) => {
    const ids = [...brief.matchAll(/"id":\s*"([^"]+)"/g)].map((m) => m[1]);
    return {
      verdicts: ids.map((id) => ({
        id, verdict: 'wiki-append', target: 'docs/wiki/x.md', markdown: 'm', cites: ['docs/wiki/x.md:1'],
      })),
      usage: { total_tokens: tokensPerCall },
    };
  };
}

test('runs one single-turn lesson-synth call per payload and returns every verdict', async () => {
  const p = prepared([payload(['a', 'b'], 1000), payload(['c'], 1000)], 1000000);
  const { result, calls } = await runWorkflow({ prepared: p }, goodAgent(5000));
  assert.equal(calls.length, 2);
  for (const c of calls) {
    assert.equal(c.opts.agentType, 'coordinator:lesson-synth');
    assert.deepEqual(c.opts.schema, SCHEMA);
  }
  assert.equal(result.budget_stop, false);
  assert.deepEqual(result.unsent_ids, []);
  assert.deepEqual(result.verdicts.map((v) => v.id), ['a', 'b', 'c']);
  assert.equal(result.spent_tokens, 10000);
});

test('MAX_SYNTH_CALLS: a fourth payload is never sent and its ids are deferred', async () => {
  const p = prepared([payload(['a'], 10), payload(['b'], 10), payload(['c'], 10), payload(['d'], 10)], 1000000);
  const { result, calls } = await runWorkflow({ prepared: p }, goodAgent(100));
  assert.equal(calls.length, 3);
  assert.deepEqual(result.verdicts.map((v) => v.id), ['a', 'b', 'c']);
  assert.deepEqual(result.deferred_ids, ['d']);
  assert.equal(result.budget_stop, false);
});

test('budget_stop: stops before the call that would cross budget_tokens and returns unsent residue ids', async () => {
  // allowance 16000: call 1 fits (0 + 1000 + 16000 <= 60000); after spending 30000, call 2 would be
  // 30000 + 1000 + 16000 = 47000 <= 60000 and fits; after 55000 spent, call 3 would cross.
  const p = prepared([payload(['a'], 1000), payload(['b'], 1000), payload(['c', 'd'], 1000)], 60000);
  const spend = [30000, 25000, 5000];
  const { result, calls } = await runWorkflow({ prepared: p }, (i, brief, opts) => {
    const r = goodAgent(spend[i])(i, brief, opts);
    return r;
  });
  assert.equal(calls.length, 2);
  assert.equal(result.budget_stop, true);
  assert.deepEqual(result.unsent_ids, ['c', 'd']);
  assert.equal(result.spent_tokens, 55000);
  assert.deepEqual(result.verdicts.map((v) => v.id), ['a', 'b']);
});

test('budget_stop: spent accumulates the measured total, not the estimate', async () => {
  // Estimates are tiny; the first call measures 99000 (cached reads included). The second must not send.
  const p = prepared([payload(['a'], 10), payload(['b'], 10)], 100000);
  const { result, calls } = await runWorkflow({ prepared: p }, goodAgent(99000));
  assert.equal(calls.length, 1);
  assert.equal(result.budget_stop, true);
  assert.deepEqual(result.unsent_ids, ['b']);
  assert.equal(result.spent_tokens, 99000);
});

test('budget_stop: a budget below the first call sends nothing', async () => {
  const p = prepared([payload(['a'], 1000)], 500);
  const { result, calls } = await runWorkflow({ prepared: p }, goodAgent(1));
  assert.equal(calls.length, 0);
  assert.equal(result.budget_stop, true);
  assert.deepEqual(result.unsent_ids, ['a']);
});

test('args.budget_tokens overrides the prepared budget only downward', async () => {
  const p = prepared([payload(['a'], 1000)], 1000000);
  const { result, calls } = await runWorkflow({ prepared: p, budget_tokens: 500 }, goodAgent(1));
  assert.equal(calls.length, 0);
  assert.equal(result.budget_stop, true);
});

test('a call whose usage is unreadable is charged its estimate plus the output allowance', async () => {
  const p = prepared([payload(['a'], 1000), payload(['b'], 1000)], 30000);
  const { result, calls } = await runWorkflow({ prepared: p }, (i, brief) => ({
    verdicts: [{ id: 'a', verdict: 'discard', target: '', markdown: '', cites: ['x:1'] }],
  }));
  assert.equal(calls.length, 1, 'second call is refused because the first was charged conservatively');
  assert.equal(result.budget_stop, true);
  assert.equal(result.usage_unmeasured_calls, 1);
});

test('doctrine-edit and memory-pointer verdicts, unknown verdicts and empty cites are rejected, never kept', async () => {
  const p = prepared([payload(['a', 'b', 'c', 'd', 'e'], 1000)], 1000000);
  const { result } = await runWorkflow({ prepared: p }, () => ({
    verdicts: [
      { id: 'a', verdict: 'doctrine-edit', target: 't', markdown: '', cites: ['x:1'] },
      { id: 'b', verdict: 'memory-pointer', target: 't', markdown: '', cites: ['x:1'] },
      { id: 'c', verdict: 'made-up', target: 't', markdown: '', cites: ['x:1'] },
      { id: 'd', verdict: 'discard', target: '', markdown: '', cites: [] },
      { id: 'e', verdict: 'universal', target: '', markdown: '', cites: ['x:1'] },
    ],
    usage: { total_tokens: 10 },
  }));
  assert.deepEqual(result.verdicts.map((v) => v.id), ['e']);
  assert.deepEqual(result.rejected.map((r) => r.id).sort(), ['a', 'b', 'c', 'd']);
  assert.deepEqual(result.missing_ids, []);
});

test('a lesson id the synth call did not answer is reported missing', async () => {
  const p = prepared([payload(['a', 'b'], 1000)], 1000000);
  const { result } = await runWorkflow({ prepared: p }, () => ({
    verdicts: [{ id: 'a', verdict: 'discard', target: '', markdown: '', cites: ['x:1'] }],
    usage: { total_tokens: 10 },
  }));
  assert.deepEqual(result.missing_ids, ['b']);
});

test('a prepared block with no payloads or no schema halts, spawning nothing', async () => {
  const { result, calls } = await runWorkflow({ prepared: { schema: 'lessons-prepared/1', synth: {} } }, goodAgent(1));
  assert.equal(calls.length, 0);
  assert.equal(result.halted, 'prepared-synth-missing');
});

test('an empty payload list is a clean no-op, not a halt', async () => {
  const { result, calls } = await runWorkflow({ prepared: prepared([], 1000000) }, goodAgent(1));
  assert.equal(calls.length, 0);
  assert.equal(result.budget_stop, false);
  assert.deepEqual(result.verdicts, []);
});
