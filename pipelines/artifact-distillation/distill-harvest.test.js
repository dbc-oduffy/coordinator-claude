'use strict';
/**
 * distill-harvest synth topic_key join — proves synth records join their dispatched cluster on
 * topic_key through stampKey/sameTopic, and that a broken join is detected.
 *
 * Source under test: distill-harvest.workflow.js (a Workflow-sandbox file with top-level await,
 * so the functions are extracted by text, not require()d).
 * Run: node coordinator/pipelines/artifact-distillation/distill-harvest.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = fs.readFileSync(path.join(__dirname, 'distill-harvest.workflow.js'), 'utf8');

function extractFunctionSource(src, name) {
  const m = src.match(new RegExp(`function\\s+${name}\\s*\\([^)]*\\)\\s*\\{`));
  if (!m) throw new Error(`could not locate function ${name}`);
  let depth = 0;
  for (let i = m.index + m[0].length - 1; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}' && --depth === 0) return src.slice(m.index, i + 1);
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

const { stampKey, sameTopic } = new Function(`
  ${extractFunctionSource(SOURCE, 'slugifyTopic')}
  ${extractFunctionSource(SOURCE, 'stampKey')}
  ${extractFunctionSource(SOURCE, 'sameTopic')}
  return { stampKey, sameTopic };
`)();

// Mirrors the workflow's failedTopicKeys computation; `join` is injected so the test can swap
// in a broken (exact-equality) join and watch the assertion fail.
const failedKeys = (clusters, synthResults, join) =>
  clusters.map((c) => c.topicKey).filter((k) => !synthResults.some((r) => join(r.topic_key, k)));

const CLUSTERS = [{ topicKey: 'structural-index-resolution' }, { topicKey: 'retrieval-tuning' }];

test('synth topic_key join: snake_case echo and stamped key both join their cluster (stampKey/sameTopic)', () => {
  const echoed = [
    { topic_key: 'structural_index_resolution' },
    { topic_key: 'Retrieval Tuning' },
  ];
  assert.deepEqual(failedKeys(CLUSTERS, echoed, sameTopic), [], 'sameTopic tolerates agent echo drift');

  const stamped = [
    stampKey({ topic_key: 'structural_index_resolution' }, 'topic_key', 'structural-index-resolution'),
    stampKey({ topic_key: 'wrong' }, 'topic_key', 'retrieval-tuning'),
  ];
  assert.deepEqual(stamped.map((r) => r.topic_key), CLUSTERS.map((c) => c.topicKey));
  assert.deepEqual(failedKeys(CLUSTERS, stamped, (a, b) => a === b), [], 'stamped keys join even by exact equality');

  assert.deepEqual(
    failedKeys(CLUSTERS, [{ topic_key: 'structural_index_resolution' }], sameTopic),
    ['retrieval-tuning'],
    'a genuinely missing synth result still fails',
  );
});

test('synth topic_key join: a broken join (exact equality, no stamp) is detected', () => {
  const echoed = [{ topic_key: 'structural_index_resolution' }, { topic_key: 'retrieval_tuning' }];
  const broken = failedKeys(CLUSTERS, echoed, (a, b) => a === b);
  assert.deepEqual(broken, ['structural-index-resolution', 'retrieval-tuning']);
  assert.notDeepEqual(broken, failedKeys(CLUSTERS, echoed, sameTopic));
});

test('synth topic_key join: the workflow joins synth returns to clusters through sameTopic', () => {
  assert.ok(/!synthResults\.some\(\(r\) => sameTopic\(r\.topic_key, c\.topicKey\)\)/.test(SOURCE), 'unsynthesized topics join by sameTopic');
  assert.ok(/slugifyTopic\(t\.topic_key\)/.test(extractFunctionSource(SOURCE, 'deriveSynthResults')), 'returns key by canonical slug');
});

const loadHelpers = new Function(`
  ${extractFunctionSource(SOURCE, 'slugifyTopic')}
  ${extractFunctionSource(SOURCE, 'sameTopic')}
  ${extractFunctionSource(SOURCE, 'listSupplied')}
  ${extractFunctionSource(SOURCE, 'assertRelayedListCounts')}
  ${extractFunctionSource(SOURCE, 'assertRelayedCounts')}
  ${extractFunctionSource(SOURCE, 'buildLoadStats')}
  ${extractFunctionSource(SOURCE, 'buildCandidatesByTopic')}
  return { listSupplied, assertRelayedListCounts, assertRelayedCounts, buildLoadStats, buildCandidatesByTopic };
`)();

test('contradictionClusters: [] is a supplied list; absent is not', () => {
  const { listSupplied, assertRelayedListCounts } = loadHelpers;
  assert.equal(listSupplied([], undefined), true);
  assert.equal(listSupplied(undefined, []), true);
  assert.equal(listSupplied(undefined, undefined), false);
  assert.equal(listSupplied(null, undefined), false);
  // [] with a curatedFile: the args count is checked against length 0, not skipped.
  const lists = { contradictionClusters: [] };
  assert.equal(assertRelayedListCounts(lists, { args: { contradictionClusters: 0 }, file: {} }, true), null);
  const halt = assertRelayedListCounts(lists, { args: { contradictionClusters: 3 }, file: {} }, true);
  assert.equal(halt.halted, 'input-count-mismatch');
  assert.ok(/!listSupplied\(loadedInput && loadedInput\.contradictionClusters, RAW_ARGS_INPUT\.contradictionClusters\)/.test(SOURCE));
});

test('contradiction detection: no clusters in the run reports status none, never unavailable', () => {
  assert.ok(/let contradictionStatus = 'none'/.test(SOURCE));
  assert.ok(/contradictionStatus = 'ran'/.test(SOURCE), 'a run with clusters still reports ran');
  assert.ok(!/contradiction-detection: no contradictionClusters provided/.test(SOURCE) && !/contradictionStatus = 'unavailable'/.test(SOURCE));
});

test('curated verdicts arrive inline at args.prepared.curated; the retired file channel halts', () => {
  assert.ok(/loadedCurated = PREPARED\.curated/.test(SOURCE));
  assert.ok(/halted: 'curated-file-retired'/.test(SOURCE));
  assert.ok(/halted: 'curated-input-ambiguous'/.test(SOURCE));
  assert.ok(!/curatedFileSha256|parseVerifiedCurated|sha256Hex/.test(SOURCE), 'no relay-integrity hashing remains');
});

test('candidates phase: prepared records feed the per-topic map; a missing record degrades to empty, no agent runs', () => {
  const { buildCandidatesByTopic } = loadHelpers;
  const phaseSrc = SOURCE.slice(SOURCE.indexOf("phase('candidates')"), SOURCE.indexOf("phase('synth')"));
  assert.equal((phaseSrc.match(/agent\(/g) || []).length, 0, 'no agent dispatch in the candidates phase');
  assert.ok(/PREPARED\.candidates/.test(phaseSrc));

  const logs = [];
  const clusters = [{ topicKey: 'topic-0', wikiPath: 'docs/wiki/topic-0.md' }, { topicKey: 'topic-1' }];
  const map = buildCandidatesByTopic(
    [{ topic_key: 'topic-0', wiki_path: 'docs/wiki/topic-0.md', candidate_restatements: [{ line: 3, excerpt: 'x' }] }],
    clusters, {}, ['docs/wiki'], (m) => logs.push(m));
  assert.deepEqual(map.get('topic-0'), [{ line: 3, excerpt: 'x' }]);
  assert.deepEqual(map.get('topic-1') || [], [], 'a topic with no prepared record reads as no candidates');
  assert.equal(logs.length, 0);
});

test('relay sites are gone: no op-relay agent type, exactly three haiku sites (plan triage, the nugget scan, the meaning-match homing)', () => {
  assert.ok(!/coordinator:op-relay/.test(SOURCE));
  assert.equal((SOURCE.match(/model: 'haiku'/g) || []).length, 3);
  const scan = SOURCE.slice(SOURCE.indexOf('agent(scanBriefFor(batch)'), SOURCE.indexOf("model: 'haiku'", SOURCE.indexOf('agent(scanBriefFor(batch)')) + 20);
  assert.ok(/phase: 'scan'/.test(scan), 'the scan wave is a haiku site');
  assert.ok(/phase: 'plan-triage'/.test(SOURCE.slice(SOURCE.indexOf("phase('plan-triage')"), SOURCE.indexOf("phase('scan')"))), 'plan triage is a haiku site');
  const homing = SOURCE.slice(SOURCE.indexOf('(brief, label) => agent(brief, {'), SOURCE.indexOf("phase('homing')") + 900);
  assert.ok(/MEANING_MATCH_SCHEMA/.test(homing) && /phase: 'homing'/.test(homing), 'the homing wave is a haiku site');
  assert.ok(!/distill-promote-staged\.py"/.test(SOURCE) && !/distill-candidates-batch\.py"/.test(SOURCE),
    'no script is dispatched through an agent');
  assert.equal((SOURCE.match(/judgment-keeper:/g) || []).length, 13, 'every remaining agent() site is a marked keeper');
});

test('inline prepared payload: declared counts are asserted against what arrived (relay-load guard)', () => {
  const { assertRelayedCounts, buildLoadStats } = loadHelpers;
  const batches = [{ batchId: 'b1', files: ['a', 'b'] }, { batchId: 'b2', files: ['c'] }];
  const ok = { args: {}, file: { batch_count: 2, total_file_count: 3 } };
  assert.equal(assertRelayedCounts(batches, ok, true), null);
  const short = assertRelayedCounts(batches.slice(0, 1), ok, true);
  assert.equal(short.halted, 'input-count-mismatch');
  assert.equal(assertRelayedCounts(batches, { args: {}, file: {} }, true).halted, 'input-count-mismatch', 'prepared without counts halts');
  assert.deepEqual(buildLoadStats(batches, { x: 'y' }), { agents: 0, batch_count: 2, total_file_count: 3, wikiSlugCount: 1 });
  assert.ok(/loadedInput = PREPARED/.test(SOURCE) && /loadedInput !== null/.test(SOURCE), 'prepared input is checked as relayed');
  assert.ok(/args\.inputFile="\$\{RAW_ARGS_INPUT\.inputFile\}" is not loaded in-workflow/.test(SOURCE), 'inputFile without prepared is refused');
});

const constOf = (name) => {
  const m = SOURCE.match(new RegExp(`^const ${name} = (\\d+)\\s*$`, 'm'));
  if (!m) throw new Error(`could not locate numeric const ${name}`);
  return Number(m[1]);
};

const synthHelpers = new Function(`
  const MAX_SYNTH_CALLS = ${constOf('MAX_SYNTH_CALLS')}
  ${extractFunctionSource(SOURCE, 'slugifyTopic')}
  ${extractFunctionSource(SOURCE, 'sameTopic')}
  ${extractFunctionSource(SOURCE, 'synthPayloadsOf')}
  ${extractFunctionSource(SOURCE, 'synthSchemaFor')}
  ${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}
  ${extractFunctionSource(SOURCE, 'synthBriefFor')}
  ${extractFunctionSource(SOURCE, 'synthUnitsOf')}
  ${extractFunctionSource(SOURCE, 'unitSlugOfCluster')}
  ${extractFunctionSource(SOURCE, 'deriveSynthResults')}
  ${extractFunctionSource(SOURCE, 'synthOutcomeOf')}
  ${extractFunctionSource(SOURCE, 'classifiedFilesOf')}
  ${extractFunctionSource(SOURCE, 'buildPromoteManifest')}
  return { MAX_SYNTH_CALLS, synthPayloadsOf, synthSchemaFor, synthBriefFor, deriveSynthResults, synthOutcomeOf, classifiedFilesOf, buildPromoteManifest };
`)();

const mkClusters = (n, type = 'RULE') =>
  Array.from({ length: n }, (_, i) => ({ topicKey: `topic-${i}`, nuggets: [{ id: `n${i}`, type }] }));
const mkPayload = (i) => ({ topics: [{ topic_key: `topic-${i}`, wiki_path: `docs/wiki/topic-${i}.md`, new_page: i === 1,
  outline: { headings: ['# T'], gotchas: [] }, nuggets: [{ id: `n${i}`, text: `fact ${i}`, cite: `src/f${i}.md`, type: 'RULE' }] }] });
const SYNTH_SCHEMA_STUB = { type: 'object', required: ['topics'] };
const mkPrepared = (n) => ({ synth: { schema: SYNTH_SCHEMA_STUB, payloads: Array.from({ length: n }, (_, i) => mkPayload(i)),
  batches: Array.from({ length: n }, (_, i) => `run/synth-batch-0${i + 1}.json`), deferred_topics: ['late-topic'] } });

test('synth: a 5-batch prepared payload dispatches exactly 3 single-turn calls, each brief embedding one payload and no file path', () => {
  const { synthPayloadsOf, synthBriefFor, MAX_SYNTH_CALLS } = synthHelpers;
  assert.equal(MAX_SYNTH_CALLS, 3);
  const prepared = mkPrepared(5);
  const payloads = synthPayloadsOf(prepared);
  assert.equal(payloads.length, 3);
  const briefs = payloads.map(synthBriefFor);
  briefs.forEach((brief, i) => {
    assert.ok(brief.includes(JSON.stringify(prepared.synth.payloads[i])), 'the brief embeds its own payload inline');
    for (const other of [0, 1, 2].filter((k) => k !== i)) assert.ok(!brief.includes(`fact ${other}`), 'and no other payload');
    for (const file of prepared.synth.batches) assert.ok(!brief.includes(file), 'no batch file path in the brief');
    assert.ok(/no tools/.test(brief) && /never something to open/.test(brief));
  });
  assert.equal(synthPayloadsOf({ synth: { payloads: [], schema: SYNTH_SCHEMA_STUB } }).length, 0, 'zero payloads: no call');
  assert.equal(synthPayloadsOf({ synth: { payloads: [mkPayload(0)] } }), null, 'no schema: a pre-payload prepare');
  assert.equal(synthPayloadsOf({}), null);
  const site = SOURCE.slice(SOURCE.indexOf('SYNTH_PAYLOADS.map('), SOURCE.indexOf('const failedSynthCalls'));
  assert.equal((site.match(/agent\(/g) || []).length, 1, 'one synth agent() site');
  assert.ok(/schema: synthSchemaFor\(PREPARED\.synth, i\)/.test(site) && /agentType: SYNTH_AGENT_TYPE/.test(site));
  assert.ok(/phase: 'synth'/.test(site) && /model: SYNTH_MODEL/.test(site) && /label: `synth-\$\{i \+ 1\}`/.test(site));
  // Two sites: synth, and opt-in re-entry, which returns ops through the same tool-less synth agent.
  assert.equal((SOURCE.match(/model: SYNTH_MODEL/g) || []).length, 2);
  assert.ok(/const SYNTH_AGENT_TYPE = 'coordinator:distill-synth'/.test(SOURCE));
  assert.ok(/const SYNTH_MODEL = .*\|\| 'sonnet'/.test(SOURCE));
  for (const gone of ['synthBatchBriefFor', 'WRITER_BUDGET', 'SYNTH_RETRY_ROUNDS', 'gapSynthBriefFor', 'writerTypeFor']) {
    assert.ok(!SOURCE.includes(gone), `${gone} is gone`);
  }
});

test('synth results: cites derive dispositions mechanically; finalize\'s splice report overrides them', () => {
  const { deriveSynthResults } = synthHelpers;
  const clusters = [
    { topicKey: 'topic-0', wikiPath: 'docs/wiki/topic-0.md', nuggets: [{ id: 'a', type: 'RULE' }, { id: 'b', type: 'DECISION' }, { id: 'c', type: 'RULE' }] },
    { topicKey: 'topic-1', wikiPath: 'docs/wiki/topic-1.md', nuggets: [{ id: 'd', type: 'RULE' }] },
    { topicKey: 'topic-2', wikiPath: 'docs/wiki/topic-2.md', nuggets: [{ id: 'e', type: 'RULE' }] },
  ];
  const returns = [{ topics: [
    { topic_key: 'Topic_0', ops: [{ section_heading: 'H', action: 'append', markdown: 'x', cites: ['a', 'zzz'] }],
      decision_records: [{ nugget_id: 'b', title: 't', decision: 'd', cites: ['b'] }] },
    { topic_key: 'topic-1', ops: [] },
  ] }];
  const wikiPathFor = (c) => c.wikiPath;
  const out = deriveSynthResults(clusters, returns, [mkPayload(0), mkPayload(1)], 'run1', wikiPathFor, null);
  assert.deepEqual(out.map((r) => [r.topic_key, r.op]), [['topic-0', 'updated'], ['topic-1', 'skipped']], 'topic-2 has no entry, so no result');
  assert.deepEqual(out[0].dispositions, [{ nugget_id: 'a', op: 'ADD_SECTION' }, { nugget_id: 'b', op: 'CREATE_DR' }],
    'an unknown cite and an uncited nugget carry no disposition');
  assert.equal(out[0].provenance.run_id, 'run1');
  assert.equal(out[0].wiki_path, 'docs/wiki/topic-0.md');

  const spliced = deriveSynthResults(clusters, returns, [], 'run1', wikiPathFor, {
    spliced: ['topic-0'],
    dispositions: [{ topic_key: 'topic-0', nugget_id: 'a', disposition: 'uncovered' }, { topic_key: 'topic-0', nugget_id: 'b', disposition: 'CREATE_DR' }],
    decision_records: [{ nugget_id: 'b', path: 'docs/decisions/DR-9-t.md' }],
  });
  assert.deepEqual(spliced[0].dispositions, [{ nugget_id: 'b', op: 'CREATE_DR', target: 'docs/decisions/DR-9-t.md' }],
    'a rejected cite stays uncovered and a minted record names its path');
  assert.equal(spliced[1].op, 'skipped', 'a topic finalize did not splice has no page');
  const created = deriveSynthResults(clusters.slice(1), [{ topics: [{ topic_key: 'topic-1', ops: [{ cites: ['d'] }] }] }], [mkPayload(1)], 'r', wikiPathFor, null);
  assert.equal(created[0].op, 'created', 'a new_page payload topic reads as created');
});

test('synth results: a nugget two records cite keeps its own record path, so dr_minting and the minted file name one DR', () => {
  const { deriveSynthResults } = synthHelpers;
  const clusters = [{ topicKey: 'topic-0', wikiPath: 'docs/wiki/topic-0.md',
    nuggets: [{ id: 'x', type: 'DECISION' }, { id: 'y', type: 'DECISION' }] }];
  const returns = [{ topics: [{ topic_key: 'topic-0', ops: [], decision_records: [
    { nugget_id: 'x', title: 'tx', decision: 'd', cites: ['x'] },
    { nugget_id: 'y', title: 'ty', decision: 'd', cites: ['y', 'x'] },
  ] }] }];
  const splice = { spliced: [], dispositions: [{ nugget_id: 'x', disposition: 'CREATE_DR' }, { nugget_id: 'y', disposition: 'CREATE_DR' }],
    decision_records: [{ nugget_id: 'x', path: 'docs/decisions/DR-4701-x.md' }, { nugget_id: 'y', path: 'docs/decisions/DR-4702-y.md' }] };
  const out = deriveSynthResults(clusters, returns, [], 'r', (c) => c.wikiPath, splice);
  const target = Object.fromEntries(out[0].dispositions.map((d) => [d.nugget_id, d.target]));
  assert.deepEqual(target, { x: 'docs/decisions/DR-4701-x.md', y: 'docs/decisions/DR-4702-y.md' });
  const cite = deriveSynthResults(clusters, returns, [], 'r', (c) => c.wikiPath, null);
  assert.deepEqual(cite[0].dispositions.map((d) => d.op), ['CREATE_DR', 'CREATE_DR']);
});

test('synth outcome: topics that returned nothing to land are counted and named, deferred ones are not', () => {
  const { synthOutcomeOf, deriveSynthResults } = synthHelpers;
  const clusters = [...mkClusters(3), { topicKey: 'deferred', nuggets: [{ id: 'z', type: 'RULE' }] }]
    .map((c) => ({ ...c, wikiPath: `docs/wiki/${c.topicKey}.md` }));
  const payloads = [mkPayload(0), mkPayload(1), mkPayload(2)];
  const returns = [{ topics: [
    { topic_key: 'topic-0', ops: [{ cites: ['n0'] }] },
    { topic_key: 'topic-1', ops: [] },
  ] }];
  const results = deriveSynthResults(clusters, returns, payloads, 'r', (c) => c.wikiPath, null);
  assert.deepEqual(synthOutcomeOf(clusters, results, payloads, returns),
    { topics_sent: 3, topics_with_ops: 1, no_ops_topics: 2, no_ops_topic_keys: ['topic-1', 'topic-2'],
      covered: 1, assigned: 3, no_ops_reasons: { 'topic-1': 'unreasoned', 'topic-2': 'dropped' } },
    'an empty entry and an unnamed topic both count; the deferred topic was never sent');
  const recordReturns = [{ topics: [{ topic_key: 'topic-0', ops: [],
    decision_records: [{ nugget_id: 'n0', cites: ['n0'] }] }] }];
  const record = deriveSynthResults(clusters.slice(0, 1), recordReturns, payloads.slice(0, 1), 'r', (c) => c.wikiPath, null);
  // Landing is read off the raw returns, so the record-only return must be passed for it to count.
  assert.equal(synthOutcomeOf(clusters.slice(0, 1), record, payloads.slice(0, 1), recordReturns).no_ops_topics, 0,
    'a record-only topic landed something');
  assert.ok(/synth_outcome: synthOutcome/.test(SOURCE.slice(SOURCE.indexOf("phase_reached: 'promote-ready'"), SOURCE.indexOf('resume_hint', SOURCE.indexOf("phase_reached: 'promote-ready'")))));
  assert.ok(/clusters_synthesized: synthResults\.length,\s*synth_outcome: synthOutcome/.test(SOURCE), 'the final result reports it too');
});

test('synth: call i gets its own schema, the shared one when schemas is absent; outcome carries coverage and reason codes', () => {
  const { synthSchemaFor, synthOutcomeOf, deriveSynthResults } = synthHelpers;
  const shared = { shared: true };
  const own = [{ own: 0 }, { own: 1 }];
  assert.deepEqual(synthSchemaFor({ schema: shared, schemas: own }, 1), { own: 1 });
  assert.equal(synthSchemaFor({ schema: shared, schemas: own }, 2), shared, 'no schemas[i]: the shared fallback');
  assert.equal(synthSchemaFor({ schema: shared }, 0), shared);
  const clusters = mkClusters(3).map((c) => ({ ...c, wikiPath: `docs/wiki/${c.topicKey}.md` }));
  const payloads = [mkPayload(0), mkPayload(1), mkPayload(2)];
  const returns = [{ topics: [
    { topic_key: 'topic-0', ops: [{ cites: ['n0'] }] },
    { topic_key: 'topic_1', ops: [], no_ops_reason: 'all-nuggets-duplicate' },
  ] }];
  const results = deriveSynthResults(clusters, returns, payloads, 'r', (c) => c.wikiPath, null);
  const out = synthOutcomeOf(clusters, results, payloads, returns);
  assert.deepEqual(out.no_ops_reasons, { 'topic-1': 'all-nuggets-duplicate', 'topic-2': 'dropped' },
    'a named empty topic carries its code (slug-joined); a sent topic the synth never named is dropped');
  assert.equal(out.covered, 1);
  assert.equal(out.assigned, 3);
  const bad = synthOutcomeOf(clusters, results, payloads, [{ topics: [{ topic_key: 'topic-1', ops: [], no_ops_reason: 'because' }] }]);
  assert.equal(bad.no_ops_reasons['topic-1'], 'unreasoned', 'an invalid code is not accepted');
});

test('3d: a file prepare classified is scanned, whatever its batch or its nuggets', () => {
  const { classifiedFilesOf } = synthHelpers;
  assert.deepEqual([...classifiedFilesOf({ classifiedFiles: ['a.md', '', 7, 'b.md'] })], ['a.md', 'b.md']);
  assert.equal(classifiedFilesOf({}).size, 0);
  const loop = SOURCE.slice(SOURCE.indexOf('const CLASSIFIED_FILES = classifiedFilesOf(PREPARED)'), SOURCE.indexOf('let fate\n'));
  assert.ok(/const scanned = classified \|\| !failedBatchIds\.includes\(batch\.batchId\)/.test(loop));
  assert.ok(/const touched = classified \|\|/.test(loop));
});

test('phase-3b: no dr-dedup agent is dispatched; the dedup is finalize\'s drIndex match', () => {
  assert.ok(!/label: 'dr-dedup'/.test(SOURCE));
  assert.ok(!/drDedupBrief|DR_DEDUP_SCHEMA/.test(SOURCE));
  const phase3b = SOURCE.slice(SOURCE.indexOf("phase('phase-3b')"), SOURCE.indexOf("phase('phase-3d')"));
  assert.ok(!/\bagent\(/.test(phase3b), 'phase-3b dispatches no agent');
  assert.ok(/status: 'script'/.test(phase3b));
});

test('synth: a deferred or uncovered nugget keeps its artifact SKIP, never EPHEMERAL', () => {
  assert.ok(/const unharvestedNuggetIds = new Set\(/.test(SOURCE));
  assert.ok(/\.some\(\(id\) => unharvestedNuggetIds\.has\(id\)\)/.test(SOURCE));
  assert.ok(/: unharvested\s*\? 'SKIP'\s*: 'EPHEMERAL'/.test(SOURCE));
});

test('synth: the workflow NO_OPS_REASONS list equals the distill_mechanical tuple', () => {
  const py = fs.readFileSync(path.join(__dirname, 'distill_mechanical.py'), 'utf8');
  const pyTuple = /^NO_OPS_REASONS = \(([^)]*)\)/m.exec(py)[1].match(/"([^"]+)"/g).map((x) => x.slice(1, -1));
  const js = /const NO_OPS_REASONS = \[([^\]]*)\]/.exec(SOURCE)[1].match(/'([^']+)'/g).map((x) => x.slice(1, -1));
  assert.deepEqual(js, pyTuple);
});

test('synth: a call that returned nothing halts with resume; deferred topics are reported, not halted on', () => {
  assert.ok(/failedSynthCalls\.length > 0/.test(SOURCE) && /halted: 'synth-partial-failure'/.test(SOURCE));
  assert.ok(/halted: 'prepared-synth-missing'/.test(SOURCE));
  assert.ok(/deferred_topics: deferredTopics/.test(SOURCE));
});

test('scan retry: a dead or zero-nugget batch is scanned once more under a new label before it counts as failed', () => {
  assert.equal(constOf('SCAN_ATTEMPTS'), 2);
  assert.ok(/label: attempt === 1 \? batch\.batchId : `\$\{batch\.batchId\}-r\$\{attempt\}`/.test(SOURCE));
  assert.ok(/r && Array\.isArray\(r\.nuggets\) && r\.nuggets\.length > 0/.test(SOURCE), 'zero nuggets counts as unread');
});

test('judgment corpus scout is skipped, no dispatch, unless the prepared precheck says dispatch', () => {
  const { judgmentPrecheckSaysDispatch } = new Function(`${extractFunctionSource(SOURCE, 'judgmentPrecheckSaysDispatch')}; return { judgmentPrecheckSaysDispatch };`)();
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: true }), true);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false }), false);
  assert.equal(judgmentPrecheckSaysDispatch({}), false);
  assert.equal(judgmentPrecheckSaysDispatch(undefined), false);
  assert.equal(judgmentPrecheckSaysDispatch(null), false);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false, distinct_eligible_plans: 2 }, 2), true);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false, distinct_eligible_plans: 2 }, 3), false);
  assert.ok(/!judgmentPrecheckSaysDispatch\(loadedInput && loadedInput\.judgmentPrecheck, MIN_CONVERGENCE\)/.test(SOURCE), 'the scout dispatch is gated on it');
  assert.ok(!/batchesNamePlan/.test(SOURCE), 'the plan-path heuristic is retired');
});

test('a dropped topic has no result: echoed keys join, an unnamed topic is absent', () => {
  const { deriveSynthResults } = synthHelpers;
  const clusters = mkClusters(3).map((c) => ({ ...c, wikiPath: `docs/wiki/${c.topicKey}.md` }));
  const out = deriveSynthResults(clusters,
    [{ topics: [{ topic_key: 'topic_0', ops: [{ cites: ['n0'] }] }, { topic_key: 'TOPIC 2', ops: [{ cites: ['n2'] }] }] }, null],
    [], 'r', (c) => c.wikiPath, null);
  assert.deepEqual(out.map((r) => r.topic_key), ['topic-0', 'topic-2']);
  assert.deepEqual(deriveSynthResults(clusters, [], [], 'r', (c) => c.wikiPath, null), []);
});

test('agent ceiling: the synth call count above args.agentCeiling halts before the candidates dispatch', () => {
  assert.ok(/const dispatchEstimate = SYNTH_PAYLOADS\.length/.test(SOURCE), 'the estimate is the payload count, at most 3');
  assert.ok(/const AGENT_CEILING = .*\n?.*agentCeiling[\s\S]{0,60}: 40/.test(SOURCE), 'default ceiling is 40');
  const halt = SOURCE.indexOf("halted: 'agent-ceiling-exceeded'");
  assert.ok(halt > 0 && halt < SOURCE.indexOf("phase('source-hash')"));
  assert.ok(halt < SOURCE.indexOf("phase('candidates')"));
});

test('skip-unchanged: only a topic the script marks unchanged is dropped from the synth set', () => {
  assert.ok(/\(sourceHashes\[c\.topicKey\] \|\| \{\}\)\.unchanged === true/.test(SOURCE));
  assert.ok(/const clusters = allClusters\.filter\(\(c\) => !unchangedClusters\.includes\(c\)\)/.test(SOURCE));
  assert.ok(/prior_harvest: true/.test(SOURCE), 'unchanged topics still count as harvested in the log rows');
});

test('promote: the manifest carries the raw synth returns for finalize\'s splice, one promote call follows the coverage gate', () => {
  const { buildPromoteManifest } = synthHelpers;
  const results = [{ topic_key: 'topic-0', op: 'updated' }, { topic_key: 'topic-1', op: 'skipped' }, { topic_key: 'topic-2', op: 'created' }];
  const returns = [mkPayload(0), { topics: [] }];
  const man = buildPromoteManifest('r1', results, returns, { 'topic-0': 'abc', 'topic-1': 'def' });
  assert.deepEqual(man.files, [], 'finalize appends the spliced pages itself');
  assert.equal(man.synth_results, returns, 'promote_manifest.synth_results is the inline returns');
  assert.deepEqual(man.hashes, { 'topic-0': 'abc' }, 'only a topic that produced a page stores its source hash');
  assert.equal(man.run_id, 'r1');
  assert.ok(!/STAGED_DIR/.test(SOURCE), 'the workflow stages nothing');
  const promote = SOURCE.indexOf("phase('promote')");
  assert.ok(promote > SOURCE.indexOf("phase('coverage-gate')"));
  assert.ok(promote < SOURCE.indexOf("phase('judgment-mining-2-5')"));
  const promoteSrc = SOURCE.slice(promote, SOURCE.indexOf("phase('judgment-mining-2-5')"));
  assert.equal((promoteSrc.match(/agent\(/g) || []).length, 0, 'no agent runs the promote');
  assert.ok(/phase_reached: 'promote-ready'/.test(promoteSrc) && /promote_manifest:/.test(promoteSrc));
  assert.ok(/promoteManifest\.synth_results\.length > 0 && !promotedByDriver/.test(promoteSrc), 'promote-ready is skipped once args.promoted is set');
  assert.ok(/promote_manifest: \{ \.\.\.promoteManifest/.test(promoteSrc), 'the promote-ready return carries promote_manifest.synth_results');
  assert.ok(!/halted: 'promote-failed'/.test(SOURCE), 'a failed promote halts in the driver, not here');
});

test('escalation stays Opus on the distill-writer type', () => {
  const m = SOURCE.match(/agent\(escalationBrief, \{[^}]*\}/);
  assert.ok(m);
  assert.ok(/agentType: DISTILL_WRITER_TYPE/.test(m[0]));
  assert.ok(/model: 'opus'/.test(m[0]));
});

const provHelpers = new Function(`
  ${extractFunctionSource(SOURCE, 'enforceProvenanceCitation')}
  return { enforceProvenanceCitation };
`)();

test('3d provenance: DELETE stands only with a written wiki/decision citation, else SEND_BACK', () => {
  const { enforceProvenanceCitation } = provHelpers;
  const { rows, downgraded } = enforceProvenanceCitation([
    { artifact_path: 'a.md', disposition: 'DELETE', reason: 'r', citation_target: 'docs/wiki/x.md', citation_written: true },
    { artifact_path: 'b.md', disposition: 'DELETE', reason: 'r' },
    { artifact_path: 'c.md', disposition: 'DELETE', reason: 'r', citation_target: 'src/x.md', citation_written: true },
    { artifact_path: 'd.md', disposition: 'BLOCKED', reason: 'r' },
  ]);
  assert.deepEqual(rows.map((r) => r.disposition), ['DELETE', 'SEND_BACK', 'SEND_BACK', 'BLOCKED']);
  assert.deepEqual(downgraded, ['b.md', 'c.md']);
});

test('3d provenance: the on-disk citation check is the driver\'s, fed by the returned finalize_manifest', () => {
  assert.ok(!/verifyCitationsOnDisk/.test(SOURCE));
  assert.ok(/const enforced = enforceProvenanceCitation\(deletionManifestResult\.deletions\)/.test(SOURCE));
  const ret = SOURCE.slice(SOURCE.lastIndexOf('finalize_manifest: {'));
  assert.ok(/d\.disposition === 'DELETE' && d\.citation_target/.test(ret));
  assert.ok(/citation_target: d\.citation_target/.test(ret));
});

test('no Phase 4 PM deletion gate remains in the workflow or PIPELINE', () => {
  assert.ok(!/Phase 4 PM gate/.test(SOURCE));
  const pipeline = require('fs').readFileSync(require('path').join(__dirname, 'PIPELINE.md'), 'utf8');
  assert.ok(!/Wait for explicit approval/.test(pipeline));
  assert.ok(/## Phase 4: Summary and Atlas Advisory/.test(pipeline));
});
