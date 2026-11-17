'use strict';
/**
 * lessons-triage workflow: runs the real script text under stubbed Workflow globals and pins the
 * measured hard budget stop, the single-turn no-tool call shape, and the triage-then-refute pairing.
 *
 * Run: node --test coordinator/pipelines/learn-lessons/tests/lessons-triage.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'lessons-triage.workflow.js'), 'utf8');
const CONTRACT = fs.readFileSync(path.join(__dirname, '..', 'lessons_contract.py'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const RUNNABLE = SOURCE.replace(/^export const meta/m, 'const meta');
const SCHEMA = { type: 'object', title: 'TRIAGE_SCHEMA stand-in' };

function lessons(prefix, n, pad = 400) {
  return Array.from({ length: n }, (_, i) => ({ id: `${prefix}-${i + 1}`, body: 'x'.repeat(pad) }));
}

function payloads(count, perBatch = 4, pad = 400) {
  return Array.from({ length: count }, (_, i) => ({
    batch_id: `b${i + 1}`,
    lessons: lessons(`l${i + 1}`, perBatch, pad),
  }));
}

// A stub agent: records every call; usage(call) supplies the reported usage (or undefined for none).
// Honest usage: input is the brief's own size, output is 100 tokens per lesson id, both under the workflow's projection.
const honestUsage = (call) => ({
  input_tokens: Math.ceil(Buffer.byteLength(call.brief, 'utf8') / 4),
  output_tokens: 100 * new Set([...call.brief.matchAll(/"id":"([^"]+)"/g)].map((m) => m[1])).size,
});

async function run({ budget, batches = payloads(3), usage = honestUsage, prepared = {}, rawArgs = {} }) {
  const calls = [];
  const reported = [];
  const logs = [];
  const agent = async (brief, opts) => {
    const call = { brief, opts, n: calls.length + 1 };
    calls.push(call);
    const ids = [...brief.matchAll(/"id":"([^"]+)"/g)].map((m) => m[1]);
    const unique = [...new Set(ids)];
    const body = opts.label.startsWith('triage')
      ? { verdicts: unique.map((id) => ({ id, verdict: 'discard', target: '', evidence: 'e', tests: [] })) }
      : { verdicts: unique.map((id) => ({ id, verdict: 'upheld', reason: 'r' })) };
    const u = usage(call);
    if (u !== undefined) reported.push(u.input_tokens + u.output_tokens);
    return u === undefined ? body : { ...body, usage: u };
  };
  const input = {
    ...(budget === undefined ? {} : { budget_tokens: budget }),
    ...rawArgs,
    prepared: { runId: 'r1', synth: { payloads: batches, schema: SCHEMA }, ...prepared },
  };
  const fn = new AsyncFunction('args', 'agent', 'phase', 'log', 'parallel', RUNNABLE);
  const result = await fn(JSON.stringify(input), agent, () => {}, (m) => logs.push(m), async () => {
    throw new Error('the workflow must not fan out: admission depends on measured spend');
  });
  return { result, calls, logs, reported };
}

test('budget stop: a run given budget_tokens N ends with measured spend <= N and hands the rest back budget-exhausted', async () => {
  for (const budget of [500, 3000, 5000, 6000, 9000, 14000, 20000]) {
    const { result, reported } = await run({ budget });
    const ledger = result.budget_ledger;
    assert.ok(ledger.spent <= budget, `budget ${budget}: spent ${ledger.spent}`);
    assert.equal(ledger.spent, reported.reduce((a, b) => a + b, 0), 'spend is the reported input+output, summed');
    assert.equal(ledger.budget_tokens, budget);
    const ids = payloads(3).flatMap((p) => p.lessons.map((l) => l.id));
    const handed = new Set(result.handed_back.map((h) => h.id));
    const refuted = new Set(result.synth_results.filter((r) => r.status === 'refuted').flatMap((r) => r.ids));
    assert.deepEqual([...ids].sort(), [...new Set([...handed, ...refuted])].sort(), 'every lesson is refuted or handed back');
    assert.ok(result.handed_back.every((h) => h.reason === 'budget-exhausted'));
    if (budget <= 3000) assert.ok(result.handed_back.length > 0, `budget ${budget} cannot clear the queue`);
  }
});

test('budget stop: once a call is refused, no later batch is admitted even if it would fit', async () => {
  const batches = [payloads(1, 2, 100)[0], payloads(1, 6, 4000)[0], payloads(1, 1, 10)[0]];
  const full = await run({ budget: 600000, batches: [batches[0]] });
  const budget = full.result.budget_ledger.spent + 800;
  const { result, calls } = await run({ budget, batches });
  assert.deepEqual(calls.map((c) => c.opts.label), ['triage-1', 'refute-1'], 'batch 1 fits and is refuted; the big batch 2 is refused and the tiny batch 3 is never tried');
  assert.deepEqual(result.synth_results.map((r) => r.status), ['refuted', 'budget-exhausted', 'budget-exhausted']);
  assert.equal(result.handed_back.length, 7);
  assert.equal(result.budget_ledger.refused.length, 1);
});

test('budget stop: budget 0 admits no call', async () => {
  const { result, calls } = await run({ budget: 0 });
  assert.equal(calls.length, 0);
  assert.equal(result.budget_ledger.spent, 0);
  assert.equal(result.handed_back.length, 12);
});

test('budget stop: an underestimated triage call that overspends makes the refute refused, never an unrefuted close', async () => {
  const { result, calls } = await run({
    budget: 9000,
    batches: payloads(2),
    usage: (c) => (c.opts.label === 'triage-1' ? { input_tokens: 8800, output_tokens: 100 } : { input_tokens: 10, output_tokens: 10 }),
  });
  assert.deepEqual(calls.map((c) => c.opts.label), ['triage-1']);
  const first = result.synth_results[0];
  assert.equal(first.status, 'budget-exhausted');
  assert.equal(first.refute, null);
  assert.ok(first.triage, 'the triage verdicts are kept for the record');
  const handed = result.handed_back.filter((h) => h.reason === 'budget-exhausted').map((h) => h.id);
  assert.ok(first.ids.every((id) => handed.includes(id)), 'the batch whose refute was refused is handed back');
  assert.ok(result.budget_ledger.spent <= 9000);
});

test('every admitted triage call is followed by its refute call; calls are single-turn, no-tool, sonnet, schema-forced', async () => {
  const { result, calls } = await run({ budget: 600000 });
  assert.deepEqual(calls.map((c) => c.opts.label), ['triage-1', 'refute-1', 'triage-2', 'refute-2', 'triage-3', 'refute-3']);
  for (const c of calls) {
    assert.equal(c.opts.model, 'sonnet');
    assert.equal(c.opts.agentType, 'coordinator:distill-synth');
    assert.ok(c.opts.schema, 'schema passed');
    assert.ok(/You have no tools/.test(c.brief));
  }
  assert.deepEqual(calls[0].opts.schema, SCHEMA, 'triage uses the prepared TRIAGE_SCHEMA');
  const refuteEnum = calls[1].opts.schema.properties.verdicts.items.properties.verdict.enum;
  assert.deepEqual(refuteEnum, ['upheld', 'overturned']);
  assert.ok(calls[1].brief.includes('"verdict":"discard"'), 'the refute call sees the triage verdicts');
  assert.ok(calls[1].brief.includes('l1-1'), 'and that batch lesson bodies');
  assert.ok(!calls[1].brief.includes('l2-1'), 'but not another batch');
  assert.ok(result.synth_results.every((r) => r.status === 'refuted' && r.triage && r.refute));
  assert.equal(result.handed_back.length, 0);
});

test('calls never exceed 2 x MAX_SYNTH_CALLS; payloads past the cap are handed back deferred-over-cap', async () => {
  const { result, calls } = await run({ budget: 600000, batches: payloads(5, 2) });
  assert.equal(calls.length, 6);
  assert.equal(result.synth_results.length, 3);
  assert.deepEqual(
    result.handed_back.map((h) => [h.id, h.reason]),
    [['l4-1', 'deferred-over-cap'], ['l4-2', 'deferred-over-cap'], ['l5-1', 'deferred-over-cap'], ['l5-2', 'deferred-over-cap']],
  );
});

test('a result with no usage is charged twice its projection and flagged unmeasured, never zero', async () => {
  const { result, calls } = await run({ budget: 600000, batches: payloads(1), usage: () => undefined });
  assert.equal(calls.length, 2);
  const ledger = result.budget_ledger;
  assert.equal(ledger.unmeasured_calls, 2);
  assert.ok(ledger.spent > 0);
  const expected = calls.reduce((n, c) => n + 2 * (Math.ceil(Buffer.byteLength(c.brief, 'utf8') / 4) + (c.opts.label.startsWith('triage') ? 250 : 120) * 4), 0);
  assert.equal(ledger.spent, expected);
});

test('a usage block missing one side is unmeasured, camelCase usage is measured', async () => {
  const partial = await run({ budget: 600000, batches: payloads(1), usage: () => ({ input_tokens: 100 }) });
  assert.equal(partial.result.budget_ledger.unmeasured_calls, 2);
  const camel = await run({ budget: 600000, batches: payloads(1), usage: () => ({ inputTokens: 100, outputTokens: 50 }) });
  assert.equal(camel.result.budget_ledger.unmeasured_calls, 0);
  assert.equal(camel.result.budget_ledger.spent, 300);
});

test('25/50/75 percent checkpoint lines are written to the ledger and logged', async () => {
  const { result, logs } = await run({ budget: 16000, batches: payloads(3, 1, 50), usage: () => ({ input_tokens: 1800, output_tokens: 200 }) });
  const ledger = result.budget_ledger;
  assert.deepEqual(ledger.checkpoints, [25, 50, 75]);
  assert.equal(ledger.checkpoint_lines.length, 3);
  assert.ok(/^25% checkpoint/.test(ledger.checkpoint_lines[0]));
  for (const line of ledger.checkpoint_lines) assert.ok(logs.includes(line));
});

test('a failed triage call is charged and its rows handed back triage-failed; deferred rows ride through', async () => {
  const agentNull = async () => null;
  const fn = new AsyncFunction('args', 'agent', 'phase', 'log', 'parallel', RUNNABLE);
  const result = await fn(JSON.stringify({
    budget_tokens: 600000,
    prepared: { runId: 'r2', synth: { payloads: payloads(1, 2), schema: SCHEMA }, deferred: [{ id: 'd-1' }, 'd-2'] },
  }), agentNull, () => {}, () => {}, async () => []);
  assert.deepEqual(result.handed_back.map((h) => [h.id, h.reason]), [['l1-1', 'triage-failed'], ['l1-2', 'triage-failed'], ['d-1', 'deferred'], ['d-2', 'deferred']]);
  assert.equal(result.budget_ledger.unmeasured_calls, 1);
  assert.ok(result.budget_ledger.spent > 0);
});

test('halts: missing prepared, missing payloads and a negative or non-numeric budget make no call', async () => {
  const fn = (a) => new AsyncFunction('args', 'agent', 'phase', 'log', 'parallel', RUNNABLE)(
    JSON.stringify(a), async () => { throw new Error('no call expected'); }, () => {}, () => {}, async () => []);
  assert.equal((await fn({})).halted, 'prepared-missing');
  assert.equal((await fn({ prepared: { synth: { schema: SCHEMA } } })).halted, 'synth-payloads-missing');
  assert.equal((await fn({ budget_tokens: -1, prepared: { synth: { payloads: [], schema: SCHEMA } } })).halted, 'invalid-budget');
  assert.equal((await fn({ budget_tokens: '250k', prepared: { synth: { payloads: [], schema: SCHEMA } } })).halted, 'invalid-budget');
});

test('default budget and call cap match lessons_contract.py', () => {
  const py = (name) => Number(new RegExp(`^${name} = (\\d+)`, 'm').exec(CONTRACT)[1]);
  assert.equal(Number(/const MAX_SYNTH_CALLS = (\d+)/.exec(SOURCE)[1]), py('MAX_SYNTH_CALLS'));
  assert.equal(Number(/const DEFAULT_BUDGET = (\d+)/.exec(SOURCE)[1]), py('LESSONS_SLICE_TOKENS'));
  assert.deepEqual(/const CHECKPOINT_PERCENTS = \[([^\]]+)\]/.exec(SOURCE)[1].split(',').map(Number), /CHECKPOINT_PERCENTS = \(([^)]+)\)/.exec(CONTRACT)[1].split(',').map(Number));
});

test('the script touches no engine op, filesystem or process: no brief, roots, require or import()', () => {
  assert.ok(!/learn_lessons_pipeline|learn_lessons_roots|learn-lessons-roots/.test(SOURCE.replace(/\/\*[\s\S]*?\*\//, '')));
  assert.ok(!/\brequire\(|\bimport\(|child_process|node:fs/.test(SOURCE));
  const code = SOURCE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.equal((code.match(/\bagent\(/g) || []).length, 2, 'two agent() sites: triage and refute');
});
