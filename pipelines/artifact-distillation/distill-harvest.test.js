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

test('synth topic_key join: workflow joins through sameTopic and stamps at every dispatch site', () => {
  assert.ok(/!synthResults\.some\(\(r\) => sameTopic\(r\.topic_key, topicKey\)\)/.test(SOURCE), 'failedTopicKeys uses sameTopic');
  assert.ok(/!gapSynthResults\.some\(\(r\) => sameTopic\(r\.topic_key, topicKey\)\)/.test(SOURCE), 'failedGapTopicKeys uses sameTopic');
  assert.ok(/stampKey\(r, 'topic_key', cluster\.topicKey\)/.test(SOURCE), 'synth stamps cluster key');
  assert.ok(/stampKey\(r, 'topic_key', gap\.topicKey\)/.test(SOURCE), 'gap-synth stamps gap key');
});

const loadHelpers = new Function(`
  ${extractFunctionSource(SOURCE, 'slugifyTopic')}
  ${extractFunctionSource(SOURCE, 'listSupplied')}
  ${extractFunctionSource(SOURCE, 'assertRelayedListCounts')}
  ${extractFunctionSource(SOURCE, 'candidatesBatchEntries')}
  ${extractFunctionSource(SOURCE, 'candidatesBatchBrief')}
  ${extractFunctionSource(SOURCE, 'parseCandidatesBatch')}
  return { listSupplied, assertRelayedListCounts, candidatesBatchEntries, candidatesBatchBrief, parseCandidatesBatch };
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

const curatedHelpers = new Function(`
  ${extractFunctionSource(SOURCE, 'sha256Hex')}
  ${extractFunctionSource(SOURCE, 'parseVerifiedCurated')}
  return { sha256Hex, parseVerifiedCurated };
`)();

test('curated loader: relayed text is accepted only when it hashes to the launcher sha256', () => {
  const { sha256Hex, parseVerifiedCurated } = curatedHelpers;
  const crypto = require('node:crypto');
  const text = JSON.stringify({ verdicts: [{ tag: 'caf\u00e9 \u{1F600}', verdict: 'keep' }] }, null, 2) + '\n';
  const want = crypto.createHash('sha256').update(text, 'utf8').digest('hex');
  assert.equal(sha256Hex(text), want);
  assert.equal(sha256Hex('x'.repeat(200)), crypto.createHash('sha256').update('x'.repeat(200)).digest('hex'));
  assert.deepEqual(parseVerifiedCurated({ stdout: text }, want).verdicts[0].verdict, 'keep');
  assert.ok(parseVerifiedCurated({ stdout: text.trimEnd() }, want), 'trimmed trailing newline restored');
  assert.equal(parseVerifiedCurated({ stdout: text.replace('keep', 'drop') }, want), null, 'altered text refused');
  assert.equal(parseVerifiedCurated(null, want), null);
  const m = SOURCE.match(/agent\(curatedLoadBrief, \{[^}]*\}/);
  assert.ok(m && /agentType: 'coordinator:op-relay'/.test(m[0]) && /SCRIPT_RELAY_SCHEMA/.test(m[0]));
  assert.ok(/halted: 'curated-hash-missing'/.test(SOURCE));
});

test('candidates phase: one dispatch for N clusters; failed topics degrade to empty', () => {
  const { candidatesBatchEntries, candidatesBatchBrief, parseCandidatesBatch } = loadHelpers;
  const clusters = Array.from({ length: 12 }, (_, i) => ({
    topicKey: `topic-${i}`,
    nuggets: [{ content: `body ${i}` }],
  }));
  const entries = candidatesBatchEntries(clusters, { 'topic-1': 'docs/wiki/topic-1.md' }, ['docs/wiki'], 'state/scratch/x');
  assert.equal(entries.length, 12);
  assert.equal(entries[1].wiki_path, 'docs/wiki/topic-1.md');
  assert.equal(entries[0].wiki_path, 'docs/wiki/topic-0.md');
  const brief = candidatesBatchBrief(entries, 'state/scratch/x');
  assert.equal(typeof brief, 'string');
  assert.ok(brief.includes('distill-candidates-batch.py'));
  for (const e of entries) assert.ok(brief.includes(`'${e.text_file}'`));

  const phaseSrc = SOURCE.slice(SOURCE.indexOf("phase('candidates')"), SOURCE.indexOf("phase('synth')"));
  assert.equal((phaseSrc.match(/await agent\(/g) || []).length, 1, 'exactly one agent dispatch in the candidates phase');
  assert.ok(!/clusters\.map\(\(cluster\) => \(\) =>\s*agent\(/.test(phaseSrc));

  const logs = [];
  const stdout = JSON.stringify({
    'topic-0': { status: 'ok', wiki_path: 'docs/wiki/topic-0.md', candidate_restatements: [{ line: 3, excerpt: 'x' }] },
    'topic-1': { status: 'error', error: 'exit 1', wiki_path: 'docs/wiki/topic-1.md', candidate_restatements: [] },
  });
  const parsed = parseCandidatesBatch({ exit_status: 1, stdout }, (m) => logs.push(m));
  assert.deepEqual(parsed.map((r) => r.topic_key), ['topic-0']);
  assert.equal(logs.length, 1);
  assert.deepEqual(parseCandidatesBatch({ exit_status: 2, stdout: 'not json' }, (m) => logs.push(m)), []);
  assert.deepEqual(parseCandidatesBatch(null, (m) => logs.push(m)), []);
});

const synthHelpers = new Function(`
  const TOPICS_PER_AGENT = 15
  const DISTILL_WRITER_TYPE = 'coordinator:distill-writer'
  ${extractFunctionSource(SOURCE, 'slugifyTopic')}
  ${extractFunctionSource(SOURCE, 'stampKey')}
  ${extractFunctionSource(SOURCE, 'sameTopic')}
  ${extractFunctionSource(SOURCE, 'chunkClusters')}
  ${extractFunctionSource(SOURCE, 'estimateDispatches')}
  ${extractFunctionSource(SOURCE, 'writerTypeFor')}
  ${extractFunctionSource(SOURCE, 'stagedPathFor')}
  ${extractFunctionSource(SOURCE, 'joinBatchResults')}
  ${extractFunctionSource(SOURCE, 'buildPromoteManifest')}
  return { TOPICS_PER_AGENT, chunkClusters, estimateDispatches, writerTypeFor, stagedPathFor, joinBatchResults, buildPromoteManifest };
`)();

const mkClusters = (n, type = 'RULE') =>
  Array.from({ length: n }, (_, i) => ({ topicKey: `topic-${i}`, nuggets: [{ id: `n${i}`, type }] }));

test('synth batching: 45 clusters dispatch 3 distill-writer agents; a DECISION batch needs the executor', () => {
  const { chunkClusters, writerTypeFor, TOPICS_PER_AGENT } = synthHelpers;
  const batches = chunkClusters(mkClusters(45), TOPICS_PER_AGENT);
  assert.equal(batches.length, Math.ceil(45 / 15));
  assert.deepEqual(batches.map((b) => b.length), [15, 15, 15]);
  assert.ok(batches.every((b) => writerTypeFor(b) === 'coordinator:distill-writer'));
  assert.equal(writerTypeFor(chunkClusters(mkClusters(3, 'DECISION'), 15)[0]), 'coordinator:executor');
  const m = SOURCE.match(/agent\(synthBatchBriefFor\(batch\), \{[^}]*\}/);
  assert.ok(m, 'batched synth dispatch located');
  assert.ok(/agentType: writerTypeFor\(batch\)/.test(m[0]));
  assert.ok(!/agent\(synthBriefFor\(/.test(SOURCE), 'no per-cluster synth dispatch remains');
});

test('batched return joins per topic via stampKey/sameTopic; a dropped topic has no result', () => {
  const { joinBatchResults } = synthHelpers;
  const batch = mkClusters(3);
  const joined = joinBatchResults(batch, { results: [{ topic_key: 'topic_0', op: 'created' }, { topic_key: 'TOPIC 2', op: 'updated' }] });
  assert.deepEqual(joined.map((r) => r.topic_key), ['topic-0', 'topic-2']);
  assert.deepEqual(joinBatchResults(batch, null), []);
});

test('agent ceiling: estimate above args.agentCeiling halts before the candidates dispatch', () => {
  const { estimateDispatches } = synthHelpers;
  assert.ok(estimateDispatches(45, 15) <= 40);
  assert.ok(estimateDispatches(800, 15) > 40);
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

test('staged promote: synth writes land under staged/, one promote call follows the coverage gate', () => {
  const { stagedPathFor, buildPromoteManifest } = synthHelpers;
  assert.equal(stagedPathFor('state/scratch/x/staged', 'docs/wiki/a.md'), 'state/scratch/x/staged/docs/wiki/a.md');
  const clusters = mkClusters(2);
  const results = [{ topic_key: 'topic-0', op: 'created' }, { topic_key: 'topic-1', op: 'skipped' }];
  const man = buildPromoteManifest('r1', clusters, results, 'S', (c) => `docs/wiki/${c.topicKey}.md`, { 'topic-0': 'abc', 'topic-1': 'def' });
  assert.deepEqual(man.files, [{ staged: 'S/docs/wiki/topic-0.md', target: 'docs/wiki/topic-0.md' }]);
  assert.deepEqual(man.hashes, { 'topic-0': 'abc' });
  assert.ok(/const STAGED_DIR = `state\/scratch\/artifact-distillation\/\$\{RUN_ID\}\/staged`/.test(SOURCE));
  assert.ok(/never write \$\{wikiPath\} itself/.test(SOURCE), 'brief forbids writing the target');
  const promote = SOURCE.indexOf("phase('promote')");
  assert.ok(promote > SOURCE.indexOf("phase('coverage-gate')"));
  assert.ok(promote < SOURCE.indexOf("phase('judgment-mining-2-5')"));
  assert.equal((SOURCE.match(/distill-promote-staged\.py" promote/g) || []).length, 1, 'exactly one promote call');
  assert.ok(/halted: 'promote-failed'/.test(SOURCE));
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

test('3d provenance: citation claims are verified on disk by the script before enforcement', () => {
  assert.ok(/distill-promote-staged\.py" verify-citations/.test(SOURCE));
  assert.ok(/const verified = await verifyCitationsOnDisk\(deletionManifestResult\.deletions\)\s*\n\s*const enforced = enforceProvenanceCitation\(verified\)/.test(SOURCE));
  assert.ok(/confirmed\[d\.artifact_path\] !== true \? \{ \.\.\.d, citation_written: false \}/.test(SOURCE));
});

test('no Phase 4 PM deletion gate remains in the workflow or PIPELINE', () => {
  assert.ok(!/Phase 4 PM gate/.test(SOURCE));
  const pipeline = require('fs').readFileSync(require('path').join(__dirname, 'PIPELINE.md'), 'utf8');
  assert.ok(!/Wait for explicit approval/.test(pipeline));
  assert.ok(/## Phase 4: Summary and Atlas Advisory/.test(pipeline));
});
