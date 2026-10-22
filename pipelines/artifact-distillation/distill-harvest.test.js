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
