'use strict';
/**
 * distill-harvest.test.js — regression tests for the distill-harvest Workflow's D1/D3 fixes.
 *
 * Purpose: (1) D1 static guard — the workflow.js source must never regress to a live
 * `import(...)` / `require(...)` call inside a Workflow script (throws "import() is not
 * available in workflow scripts" and kills the run at init — the 2026-07-19 crash this
 * fix set addresses), and CONCURRENCY_CAP must stay a static literal, not a runtime-derived
 * value (`os.cpus`, `Date.now`, `Math.random`). (2) D3 consolidation ceiling + conservation —
 * exercises the ACTUAL landed `consolidateClusters`/`slugifyTopic` functions (extracted by
 * text from workflow.js, since the script is a Workflow-sandbox file with top-level `await`
 * and undefined runtime globals and is therefore not `require()`-able) against a synthetic
 * ~300-singleton-topic input, asserting the new-file count stays under the documented cap
 * and no nugget is ever dropped.
 *
 * Source under test: coordinator/pipelines/artifact-distillation/distill-harvest.workflow.js
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node coordinator/pipelines/artifact-distillation/tests/distill-harvest.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const WORKFLOW_PATH = path.join(__dirname, '..', 'distill-harvest.workflow.js');
const SOURCE = fs.readFileSync(WORKFLOW_PATH, 'utf8');

// ---------------------------------------------------------------------------
// D1 static guard
// ---------------------------------------------------------------------------

// Strip full-line `//` comments and multi-line JSDoc/block comments before scanning for the
// live crash pattern — the source legitimately mentions `import('node:os')` inside a NOTE
// Strip full-line `//` comments and multi-line JSDoc/block comments before scanning for the
// live crash pattern — the source legitimately mentions `import('node:os')` inside a NOTE
// comment (explaining WHY the static CONCURRENCY_CAP exists); we must assert on live code,
// not comment prose.
// not comment prose.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '') // block comments (incl. the file-top JSDoc)
    .split('\n')
    .map((line) => line.replace(/\/\/.*$/, ''))
    .join('\n');
}

const LIVE_CODE = stripComments(SOURCE);

test('D1: workflow.js has no live await-import / import() call', () => {
  assert.doesNotMatch(LIVE_CODE, /await\s+import\s*\(/, 'live "await import(" found outside comments');
  assert.doesNotMatch(LIVE_CODE, /[^.\w]import\s*\(/, 'live "import(" call found outside comments');
});

test('empty-input-batches: guard halts before any scan dispatch and names the input file', () => {
  const m = SOURCE.match(/if \(!Array\.isArray\(BATCHES\) \|\| BATCHES\.length === 0\) \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'empty-batches guard not found');
  assert.ok(m[0].includes("halted: 'empty-input-batches'"));
  assert.ok(SOURCE.indexOf(m[0]) < SOURCE.indexOf('const scanResults = (await parallel('),
    'guard must precede the scan dispatch');
  const run = (RAW_ARGS_INPUT, BATCHES) =>
    new Function('RAW_ARGS_INPUT', 'BATCHES', 'loadStats', m[0])(RAW_ARGS_INPUT, BATCHES, () => ({}));
  for (const b of [undefined, null, []]) {
    const r = run({ inputFile: '/x/input.json' }, b);
    assert.equal(r.halted, 'empty-input-batches');
    assert.match(r.detail, /\/x\/input\.json/);
  }
  assert.equal(run({}, [{ batchId: 'b1' }]), undefined);
});

test('D1: workflow.js has no live require()/node: runtime call', () => {
  assert.doesNotMatch(LIVE_CODE, /[^.\w]require\s*\(/, 'live "require(" call found outside comments');
  assert.doesNotMatch(LIVE_CODE, /require\(\s*['"]node:/, 'live "require(\'node:...\')" found outside comments');
});

test('D1: CONCURRENCY_CAP is a static literal, not a runtime-derived value', () => {
  const m = LIVE_CODE.match(/const\s+CONCURRENCY_CAP\s*=\s*([^\n;]+);?/);
  assert.ok(m, 'CONCURRENCY_CAP declaration not found in live code');
  const rhs = m[1].trim();
  assert.match(rhs, /^\d+$/, `CONCURRENCY_CAP must be a static numeric literal, got: ${rhs}`);
  assert.doesNotMatch(LIVE_CODE, /os\.cpus/, 'os.cpus() reference found in live code');
  assert.doesNotMatch(LIVE_CODE, /Date\.now/, 'Date.now() reference found in live code');
  assert.doesNotMatch(LIVE_CODE, /Math\.random/, 'Math.random() reference found in live code');
});

// ---------------------------------------------------------------------------
// D3 extraction — pull the pure functions out of the Workflow-sandbox script by text so the
// test runs the REAL landed algorithm, not a re-implementation. workflow.js is not
// require()-able (top-level await + undefined runtime globals like `phase`/`agent`/`parallel`/
// `log`/`args`), so we locate each `function <name>(...) {...}` declaration by brace-matching
// and evaluate the extracted source via `new Function`.
// ---------------------------------------------------------------------------

function extractFunctionSource(src, functionName) {
  const startMatch = src.match(new RegExp(`function\\s+${functionName}\\s*\\([^)]*\\)\\s*\\{`));
  if (!startMatch) {
    throw new Error(`extractFunctionSource: could not locate "function ${functionName}(" in workflow.js`);
  }
  const openBraceIdx = startMatch.index + startMatch[0].length - 1;
  let depth = 0;
  for (let i = openBraceIdx; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) {
        return src.slice(startMatch.index, i + 1);
      }
    }
  }
  throw new Error(`extractFunctionSource: unbalanced braces extracting "${functionName}"`);
}

// consolidateClusters's real dependency graph, post-curation-move-upstream
// (docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md, chunk C4): slugifyTopic,
// dr146Normalize, leadingStem, findFuzzyWikiHome — all must be extracted and in scope
// together, or consolidateClusters throws a ReferenceError at call time. The former
// shrapnel-consolidation dependencies (buildSegmentTrie, longestSharedPrefixKey) are GONE —
// C4 retired consolidateClusters's Steps 2-5 (coarsen/fold/cap/misc-bucket-emission) because
// that per-cluster triage question ("does this shrapnel earn its own file?") is now answered
// upstream of clustering, by claude-klabauter's `distill.curate_clusters` verdict, before a nugget is
// ever grouped. consolidateClusters now only partitions homed vs. homeless (Step 1) and mints
// every homeless cluster its own `bucket: 'new'` file, unconditionally.
const slugifyTopicSrc = extractFunctionSource(SOURCE, 'slugifyTopic');
const dr146NormalizeSrc = extractFunctionSource(SOURCE, 'dr146Normalize');
const leadingStemSrc = extractFunctionSource(SOURCE, 'leadingStem');
const findFuzzyWikiHomeSrc = extractFunctionSource(SOURCE, 'findFuzzyWikiHome');
const consolidateClustersSrc = extractFunctionSource(SOURCE, 'consolidateClusters');

// Config constants read from source (not re-guessed) so the test tracks the real tunables.
function readConstFromSource(name) {
  const m = SOURCE.match(new RegExp(`const\\s+${name}\\s*=\\s*(\\d+)`));
  if (!m) throw new Error(`readConstFromSource: could not find const ${name} in workflow.js`);
  return Number(m[1]);
}

// SINGLETON_FLOOR/NEW_FILE_CAP were RETIRED FOR REAL by chunk C4b (docs/plans/2026-08-06-
// distill-curation-moves-to-claude-klabauter.md) — deleted as live code from workflow.js, not merely held
// unwired as under C4. The harness no longer reads them via readConstFromSource; do not re-add
// the call. The minting policy they encoded now lives entirely in claude-klabauter's
// `distill.curate_clusters` gate.
const DR146_MIN_STEM_LEN = readConstFromSource('DR146_MIN_STEM_LEN');
const STEM_PREFIX_LEN = readConstFromSource('STEM_PREFIX_LEN');

// DR146_MIN_STEM_LEN/STEM_PREFIX_LEN are referenced as free module-scope consts by the
// extracted function bodies (not passed through config) — declare them as literals in the
// evaluated scope under their real names so the extracted source resolves them unmodified.
const extracted = new Function(`
  const DR146_MIN_STEM_LEN = ${DR146_MIN_STEM_LEN};
  const STEM_PREFIX_LEN = ${STEM_PREFIX_LEN};
  const DR146_STRIP_SUFFIXES = ['-shape', '-design', '-v2'];
  const DR146_DATE_PREFIX_RE = /^\\d{4}-\\d{2}-\\d{2}-/;
  ${slugifyTopicSrc}
  ${dr146NormalizeSrc}
  ${leadingStemSrc}
  ${findFuzzyWikiHomeSrc}
  ${consolidateClustersSrc}
  return { slugifyTopic, consolidateClusters };
`)();

const { slugifyTopic, consolidateClusters } = extracted;

assert.equal(typeof slugifyTopic, 'function', 'slugifyTopic extraction failed');
assert.equal(typeof consolidateClusters, 'function', 'consolidateClusters extraction failed');

// ---------------------------------------------------------------------------
// D3: consolidation ceiling + conservation
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// D3: retired coverage — docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md, chunk C4.
//
// Four tests previously lived here, exercising the shrapnel-consolidation policy
// (`MISC_MAX_NUGGET_SHARE`, `MIN_SHARED_SEGMENTS`, `buildSegmentTrie`, `longestSharedPrefixKey`,
// and `consolidateClusters` Steps 2-5, incl. the `misc-harvest-<run>` emission and its
// `miscOverflow` verdict): "~300 distinct singleton topics consolidate under NEW_FILE_CAP with
// zero nugget loss", "cold-start misc overflow reports resolved:false when NEW_FILE_CAP binds
// before the share cap is met", "misc overflow resolves under the share cap when NEW_FILE_CAP
// leaves enough headroom to promote", and "NEW_FILE_CAP is enforced even when clusters are
// large enough to survive the SINGLETON_FLOOR fold". C4 deleted the machinery they exercised —
// curation now happens upstream of clustering (claude-klabauter's `distill.curate_clusters` verdict,
// wired in C2/C3), so the per-cluster triage question these tests asserted no longer exists for
// consolidateClusters to answer. Not repairable; the behaviour they pinned was deliberately
// removed. See "D3: homeless clusters get their own file, unconditionally" and
// "D3: no misc-shaped path is ever emitted" below for the coverage that replaces them.
// ---------------------------------------------------------------------------

function makeSingletonCluster(i) {
  return {
    topicKey: `singleton${i}-topic-distinct-subject`,
    nuggets: [{ id: `n-${i}`, type: 'KNOWLEDGE', system_tag: `singleton${i}-topic-distinct-subject`, content: `nugget ${i}` }],
    sourceBatches: [`b${i}`],
  };
}

test('D3: homeless clusters get their own file, unconditionally, one per input cluster', () => {
  const N = 300;
  const raw = [];
  for (let i = 0; i < N; i++) raw.push(makeSingletonCluster(i));

  const totalInputNuggets = raw.reduce((n, c) => n + c.nuggets.length, 0);
  assert.equal(totalInputNuggets, N);

  const result = consolidateClusters(raw, {}, {
    runId: '2026-08-06-test-homeless-to-new',
    wikiDirs: ['docs/wiki'],
  });

  const homed = result.filter((c) => c.bucket === 'homed');
  const newClusters = result.filter((c) => c.bucket === 'new');

  assert.equal(homed.length, 0, 'no wiki slugs were supplied — nothing should be homed');
  assert.equal(newClusters.length, N, 'every homeless cluster must mint its own new-bucket file, no merging or folding');
  assert.deepEqual(
    newClusters.map((c) => c.topicKey).sort(),
    raw.map((c) => c.topicKey).sort(),
    'each input topicKey must survive to exactly one output cluster'
  );

  const totalOutputNuggets = result.reduce((n, c) => n + c.nuggets.length, 0);
  assert.equal(totalOutputNuggets, totalInputNuggets, 'nugget conservation violated: input/output counts differ');
});

test('D3: no misc-shaped path is ever emitted, even for a cold-start run of many small homeless singletons', () => {
  // Many small homeless singletons against an EMPTY wikiSlugs index is exactly the shape that
  // previously triggered the misc-harvest fold under the retired policy. AC4's teeth: no code
  // path in consolidateClusters can produce a misc-shaped topicKey or wikiPath any more.
  const N = 300;
  const raw = [];
  for (let i = 0; i < N; i++) raw.push(makeSingletonCluster(i));

  const result = consolidateClusters(raw, {}, {
    runId: '2026-08-06-test-no-misc-bucket',
    wikiDirs: ['docs/wiki'],
  });

  for (const cluster of result) {
    assert.doesNotMatch(cluster.topicKey, /misc-harvest/, `cluster topicKey must never be misc-shaped: ${cluster.topicKey}`);
    assert.doesNotMatch(cluster.wikiPath, /misc-harvest/, `cluster wikiPath must never be misc-shaped: ${cluster.wikiPath}`);
    assert.notEqual(cluster.bucket, 'misc', 'no cluster may carry a misc bucket any more');
  }
});

// ---------------------------------------------------------------------------
// D3: existing-wiki-slug pass-through (homed clusters are not shrapnel and are not capped)
// ---------------------------------------------------------------------------

test('D3: topicKeys matching an existing wikiSlugs entry pass through as homed; every homeless cluster mints unconditionally (no cap, retired C4b)', () => {
  const homedTopic = 'workflow-orchestration-caps';
  const homedSlug = slugifyTopic(homedTopic);
  const existingPath = 'docs/wiki/workflow-orchestration-caps.md';

  const raw = [
    {
      topicKey: homedTopic,
      nuggets: [
        { id: 'h-1', type: 'KNOWLEDGE', system_tag: homedTopic, content: 'homed nugget 1' },
        { id: 'h-2', type: 'KNOWLEDGE', system_tag: homedTopic, content: 'homed nugget 2' },
      ],
      sourceBatches: ['b-homed'],
    },
  ];
  // Fill out 30 distinct new-file candidates so the cap is actually exercised alongside the homed one.
  for (let i = 0; i < 30; i++) {
    raw.push({
      topicKey: `newtopic${i}-distinct-subject`,
      nuggets: [
        { id: `nt-${i}-a`, type: 'KNOWLEDGE', system_tag: `newtopic${i}-distinct-subject`, content: `a${i}` },
        { id: `nt-${i}-b`, type: 'KNOWLEDGE', system_tag: `newtopic${i}-distinct-subject`, content: `b${i}` },
      ],
      sourceBatches: [`b${i}`],
    });
  }

  const wikiSlugs = { [homedSlug]: existingPath };
  const totalInputNuggets = raw.reduce((n, c) => n + c.nuggets.length, 0);

  const result = consolidateClusters(raw, wikiSlugs, {
    runId: '2026-07-19-test-homed',
    wikiDirs: ['docs/wiki'],
  });

  const homed = result.filter((c) => c.bucket === 'homed');
  const newClusters = result.filter((c) => c.bucket === 'new');

  assert.equal(homed.length, 1, 'exactly the one wikiSlugs-matching cluster should be homed');
  assert.equal(homed[0].topicKey, homedTopic);
  assert.equal(homed[0].wikiPath, existingPath, 'homed cluster must target the existing wiki path, not a new file');
  assert.equal(homed[0].nuggets.length, 2, 'homed cluster nuggets must pass through unchanged');

  // NEW_FILE_CAP was RETIRED FOR REAL by chunk C4b (deleted, not merely held per C4) — every
  // homeless input cluster mints its own new-bucket file, so the count below is 30, not
  // capped at 25.
  assert.equal(newClusters.length, 30, 'every homeless cluster must mint its own new-bucket file, unconditionally');
  assert.ok(newClusters.every((c) => c.topicKey !== homedTopic), 'homed cluster must not also appear as a new-file candidate');

  const totalOutputNuggets = result.reduce((n, c) => n + c.nuggets.length, 0);
  assert.equal(totalOutputNuggets, totalInputNuggets, 'nugget conservation violated with a mixed homed/new input');
});

// ---------------------------------------------------------------------------
// Empty-content nugget defence (2026-08-06, example-market-data-repo-em memo): a scan agent could
// previously return structurally valid, schema-passing, semantically empty nuggets (right
// count, correctly typed and sourced, no content) and the batch counted as a scan success.
// (1) asserts the schema layer now rejects it at the source; (2) exercises the ACTUAL landed
// empty-content-batch detection block (extracted by text, same pattern as the D3 functions
// above) so the defence-in-depth path is proven against the real code, not a re-implementation.
// ---------------------------------------------------------------------------

test('schema: nugget content is required and non-empty (minLength 1)', () => {
  const schemaMatch = SOURCE.match(/const\s+NUGGET_SCHEMA\s*=\s*(\{[\s\S]*?\n\})\n/);
  assert.ok(schemaMatch, 'NUGGET_SCHEMA declaration not found in workflow.js');
  const NUGGET_SCHEMA = new Function(`return (${schemaMatch[1]});`)();

  const nuggetItemSchema = NUGGET_SCHEMA.properties.nuggets.items;
  assert.ok(nuggetItemSchema.required.includes('content'), 'nugget item schema must require `content`');
  assert.equal(nuggetItemSchema.properties.content.minLength, 1, 'nugget `content` must carry minLength: 1');
  assert.ok(nuggetItemSchema.required.includes('source'), 'nugget item schema must require `source`');
  assert.equal(nuggetItemSchema.properties.source.minLength, 1, 'nugget `source` must carry minLength: 1');
});

// The empty-content-batch detection block lives inline at module scope in the Workflow script
// (not a named function — it runs once, directly against scanResults/BATCHES/log), so it is
// extracted by its own start/end anchor comments, the same brace-free extraction shape the file
// already uses for its schema/config constants.
function extractBlockSource(src, startAnchor, endAnchor) {
  const startIdx = src.indexOf(startAnchor);
  if (startIdx === -1) throw new Error(`extractBlockSource: start anchor not found: ${startAnchor}`);
  const endIdx = src.indexOf(endAnchor, startIdx);
  if (endIdx === -1) throw new Error(`extractBlockSource: end anchor not found: ${endAnchor}`);
  return src.slice(startIdx, endIdx + endAnchor.length);
}

const emptyContentBlockSrc = extractBlockSource(
  SOURCE,
  'const emptyContentBatchIds = []',
  'empty-content batches counted as scan failures (defence in depth): ${emptyContentBatchIds.join(\', \')}`)\n}'
);

function runEmptyContentDetection(scanResults, batchIds) {
  const logs = [];
  const fn = new Function('scanResults', 'BATCHES', 'log', `
    ${emptyContentBlockSrc}
    const malformedTagBatchIds = [];
    const failedBatchIds = BATCHES
      .map((b) => b.batchId)
      .filter((id) => !scanResults.some((r) => r.batch_id === id) || emptyContentBatchIds.includes(id) || malformedTagBatchIds.includes(id));
    return { emptyContentBatchIds, failedBatchIds };
  `);
  return fn(scanResults, batchIds.map((batchId) => ({ batchId })), (msg) => logs.push(msg));
}

test('empty-content batch: a batch whose every nugget is empty is folded into failedBatchIds', () => {
  const scanResults = [
    { batch_id: 'xrep-06', nuggets: Array.from({ length: 52 }, (_, i) => ({ id: `xrep-06-${i}`, content: '' })) },
    { batch_id: 'hand-04', nuggets: Array.from({ length: 5 }, (_, i) => ({ id: `hand-04-${i}`, content: '   ' })) },
  ];
  const { emptyContentBatchIds, failedBatchIds } = runEmptyContentDetection(scanResults, ['xrep-06', 'hand-04']);

  assert.deepEqual(emptyContentBatchIds.sort(), ['hand-04', 'xrep-06'], 'both all-empty batches must be detected');
  assert.deepEqual(failedBatchIds.sort(), ['hand-04', 'xrep-06'], 'all-empty batches must count as failed batches, not scan successes');
});

test('empty-content batch: a batch with a genuine mix of empty and non-empty content is NOT counted as failed', () => {
  const scanResults = [
    { batch_id: 'mixed-01', nuggets: [{ id: 'm-1', content: 'real extracted content' }, { id: 'm-2', content: '' }] },
  ];
  const { emptyContentBatchIds, failedBatchIds } = runEmptyContentDetection(scanResults, ['mixed-01']);

  assert.deepEqual(emptyContentBatchIds, [], 'a batch with at least one real nugget must not be treated as all-empty');
  assert.deepEqual(failedBatchIds, [], 'a mixed batch must not be folded into failedBatchIds');
});

test('empty-content batch: a batch with zero nuggets (legitimately nothing extractable) is NOT counted as failed', () => {
  const scanResults = [{ batch_id: 'quiet-01', nuggets: [] }];
  const { emptyContentBatchIds, failedBatchIds } = runEmptyContentDetection(scanResults, ['quiet-01']);

  assert.deepEqual(emptyContentBatchIds, [], 'zero nuggets is a legitimate "nothing extractable" result, distinct from the empty-content defect');
  assert.deepEqual(failedBatchIds, [], 'a batch that legitimately found nothing must not be marked failed');
});

// ---------------------------------------------------------------------------
// BUG-1 (2026-08-06, state/bug-backlog/2026-08-06-distill-scan-wave-haiku-returns-comma-jo-
// 5f766cbc9920.yaml): a live invocation-A run returned a comma-joined system_tag ("guard_design,
// test_design") — Wave 1 Haiku put TWO tags in one string. clusterNuggets() treated it as a
// single valid tag key, and the curation gate normalized it into a slug with a comma in it that
// can never match a wiki home. The malformed-tag detection block is extracted by anchor the same
// way emptyContentBlockSrc is above, since it runs inline at module scope, not as a named
// function.
// ---------------------------------------------------------------------------

const malformedTagBlockSrc = extractBlockSource(
  SOURCE,
  'const MALFORMED_TAG_RE = /[,;|]|^\\s|\\s$/',
  '.filter((id) => !scanResults.some((r) => r.batch_id === id) || emptyContentBatchIds.includes(id) || malformedTagBatchIds.includes(id))'
);

function runMalformedTagDetection(scanResults, batchIds) {
  const logs = [];
  const fn = new Function('scanResults', 'BATCHES', 'log', `
    const emptyContentBatchIds = [];
    ${malformedTagBlockSrc}
    return { malformedTagBatchIds, malformedTagNuggetCount, failedBatchIds, scanResults };
  `);
  return fn(scanResults, batchIds.map((batchId) => ({ batchId })), (msg) => logs.push(msg));
}

test('BUG-1: a comma-joined system_tag does not produce a cluster keyed on it', () => {
  const scanResults = [
    {
      batch_id: 'wave-01',
      nuggets: [
        { id: 'wave-01-001', type: 'KNOWLEDGE', system_tag: 'guard_design, test_design', content: 'x' },
        { id: 'wave-01-002', type: 'KNOWLEDGE', system_tag: 'guard-design', content: 'y' },
      ],
    },
  ];
  const { malformedTagNuggetCount, scanResults: cleaned } = runMalformedTagDetection(scanResults, ['wave-01']);

  assert.equal(malformedTagNuggetCount, 1, 'exactly one nugget carries a malformed tag');
  const remainingTags = cleaned[0].nuggets.map((n) => n.system_tag);
  assert.ok(!remainingTags.includes('guard_design, test_design'), 'the comma-joined tag must not survive into clustering input');
  assert.deepEqual(remainingTags, ['guard-design'], 'the legitimately single-tagged nugget must survive untouched');
});

test('BUG-1: a batch with one malformed-tag nugget among otherwise-good nuggets is accounted for in telemetry but NOT failed outright', () => {
  const scanResults = [
    {
      batch_id: 'wave-02',
      nuggets: [
        { id: 'wave-02-001', type: 'KNOWLEDGE', system_tag: 'ops, incident', content: 'x' },
        { id: 'wave-02-002', type: 'DECISION', system_tag: 'ops-review', content: 'y' },
      ],
    },
  ];
  const { malformedTagBatchIds, malformedTagNuggetCount, failedBatchIds } = runMalformedTagDetection(scanResults, ['wave-02']);

  assert.equal(malformedTagNuggetCount, 1, 'the malformed nugget is counted in telemetry, not silently dropped');
  assert.deepEqual(malformedTagBatchIds, [], 'a batch with at least one good nugget must not be treated as wholly malformed');
  assert.deepEqual(failedBatchIds, [], 'a partially-malformed batch must not be folded into failedBatchIds');
});

test('BUG-1: a batch whose every carry-forward nugget has a malformed tag IS folded into failedBatchIds', () => {
  const scanResults = [
    {
      batch_id: 'wave-03',
      nuggets: [
        { id: 'wave-03-001', type: 'KNOWLEDGE', system_tag: 'a, b', content: 'x' },
        { id: 'wave-03-002', type: 'DECISION', system_tag: 'c; d', content: 'y' },
      ],
    },
  ];
  const { malformedTagBatchIds, failedBatchIds } = runMalformedTagDetection(scanResults, ['wave-03']);

  assert.deepEqual(malformedTagBatchIds, ['wave-03'], 'a batch with zero surviving carry-forward nuggets must be marked malformed');
  assert.deepEqual(failedBatchIds, ['wave-03'], 'a wholly-malformed batch must count as a scan failure, mirroring the empty-content precedent');
});

test('BUG-1: EPHEMERAL/ALREADY_CAPTURED/PRESERVE nuggets with a malformed-looking tag are not clustering candidates anyway, so are excluded from the carry-forward denominator', () => {
  const scanResults = [
    {
      batch_id: 'wave-04',
      nuggets: [
        { id: 'wave-04-001', type: 'EPHEMERAL', system_tag: 'a, b', content: 'x' },
        { id: 'wave-04-002', type: 'KNOWLEDGE', system_tag: 'legit-tag', content: 'y' },
      ],
    },
  ];
  const { malformedTagBatchIds, failedBatchIds } = runMalformedTagDetection(scanResults, ['wave-04']);

  assert.deepEqual(malformedTagBatchIds, [], 'an EPHEMERAL nugget never carries forward, so its tag shape must not affect batch disposition');
  assert.deepEqual(failedBatchIds, []);
});

test('BUG-1 detection rule: legitimate tags with hyphens, underscores, dots and slashes are NOT rejected', () => {
  const scanResults = [
    {
      batch_id: 'wave-05',
      nuggets: [
        { id: 'wave-05-001', type: 'KNOWLEDGE', system_tag: 'guard-design_v2', content: 'a' },
        { id: 'wave-05-002', type: 'KNOWLEDGE', system_tag: 'ops/incident.response', content: 'b' },
        { id: 'wave-05-003', type: 'DECISION', system_tag: 'cross_repo-memo.v1/draft', content: 'c' },
      ],
    },
  ];
  const { malformedTagNuggetCount, malformedTagBatchIds } = runMalformedTagDetection(scanResults, ['wave-05']);

  assert.equal(malformedTagNuggetCount, 0, 'hyphens/underscores/dots/slashes are legitimate single-tag characters');
  assert.deepEqual(malformedTagBatchIds, []);
});

test('BUG-1 detection rule: semicolon-joined and leading/trailing-whitespace tags are rejected as the same class of sloppiness', () => {
  const scanResults = [
    {
      batch_id: 'wave-06',
      nuggets: [
        { id: 'wave-06-001', type: 'KNOWLEDGE', system_tag: 'guard_design; test_design', content: 'a' },
        { id: 'wave-06-002', type: 'KNOWLEDGE', system_tag: ' leading-space', content: 'b' },
        { id: 'wave-06-003', type: 'KNOWLEDGE', system_tag: 'trailing-space ', content: 'c' },
      ],
    },
  ];
  const { malformedTagNuggetCount } = runMalformedTagDetection(scanResults, ['wave-06']);

  assert.equal(malformedTagNuggetCount, 3, 'semicolon-joined and leading/trailing-whitespace tags are all in the same defect class as the comma-joined case');
});

// ---------------------------------------------------------------------------
// Finding 3 (code-reviewer, coordinatorcode-reviewer-a309a85e.md): the Wave 1.5
// candidates-relay's fallback-on-failure path and Map-lookup default were unexercised by any
// test. `buildCandidatesByTopic` is extracted the same way as the D3 functions above so this
// exercises the ACTUAL landed logic (candidatesByTopic Map construction + wiki_path sanity
// check), not a re-implementation.
// ---------------------------------------------------------------------------

const sameTopicSrc = extractFunctionSource(SOURCE, 'sameTopic');
const buildCandidatesByTopicSrc = extractFunctionSource(SOURCE, 'buildCandidatesByTopic');
const candidatesExtracted = new Function(`
  ${slugifyTopicSrc}
  ${sameTopicSrc}
  ${buildCandidatesByTopicSrc}
  return { buildCandidatesByTopic };
`)();
const { buildCandidatesByTopic } = candidatesExtracted;

assert.equal(typeof buildCandidatesByTopic, 'function', 'buildCandidatesByTopic extraction failed');

test('candidates: Map-lookup default returns [] for a topic_key with no matching result (agent failure)', () => {
  const clusters = [
    { topicKey: 'topic-a', wikiPath: 'docs/wiki/topic-a.md' },
    { topicKey: 'topic-b', wikiPath: 'docs/wiki/topic-b.md' },
  ];
  // Only 'topic-a' returned a result — simulates a Wave 1.5 relay agent that errored/timed out
  // for 'topic-b' and was filtered out of candidatesResults by the `.filter(Boolean)` upstream.
  const candidatesResults = [
    { topic_key: 'topic-a', wiki_path: 'docs/wiki/topic-a.md', candidate_restatements: [{ line: 3, excerpt: 'x' }] },
  ];

  const logs = [];
  const map = buildCandidatesByTopic(candidatesResults, clusters, {}, ['docs/wiki'], (msg) => logs.push(msg));

  assert.deepEqual(map.get('topic-a'), [{ line: 3, excerpt: 'x' }], 'present result must be returned verbatim');
  assert.equal(map.get('topic-b'), undefined, 'a topic with no relay result has no Map entry at all');
  // The caller's own `candidatesByTopic.get(cluster.topicKey) || []` idiom (in synthBriefFor)
  // is what actually degrades the missing entry to an empty list — assert that idiom explicitly
  // so the fallback-on-failure contract is pinned, not just the Map's own `.get()` behavior.
  assert.deepEqual(map.get('topic-b') || [], [], 'fallback-on-failure must degrade to an empty list, never throw or block');
});

test('candidates: an empty candidate_restatements list is preserved, not conflated with a missing result', () => {
  const clusters = [{ topicKey: 'topic-c', wikiPath: 'docs/wiki/topic-c.md' }];
  const candidatesResults = [
    { topic_key: 'topic-c', wiki_path: 'docs/wiki/topic-c.md', candidate_restatements: [] },
  ];

  const logs = [];
  const map = buildCandidatesByTopic(candidatesResults, clusters, {}, ['docs/wiki'], (msg) => logs.push(msg));

  assert.ok(map.has('topic-c'), 'a present-and-empty result must still create a Map entry');
  assert.deepEqual(map.get('topic-c'), [], 'present-and-empty candidate_restatements must be preserved as []');
  assert.equal(logs.length, 0, 'no wiki_path mismatch should be logged when the agent echoed the correct path');
});

// ---------------------------------------------------------------------------------------------
// clusterNuggets — curated-path verdict rekeying (chunk C5b).
//
// Spec backlink: docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md, chunk C5 (AMENDED),
// contract confirmed by cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-four-
// answers-volume-is-weighted-but-not-a-floor.md. Exercises the ACTUAL landed `clusterNuggets`
// (chunk C3c, commit 810ffe46d), extracted by text like the D3 functions above.
//
// Contract under test: one verdict entry per RAW input tag. `verdict` in {keep, normalize,
// merge, drop}; `canonical_slug` is the tag's OWN slug (never a destination); `merge_target` is
// populated ONLY on merge, never null there, and null everywhere else. `reason` is non-empty on
// every drop. The drop set is a filter over the verdict list, not a separate top-level array —
// no fixture below supplies a `dropped:` key. `drop_cause`/`drop_by_cause` are explicitly
// not-yet-landed per the memo and are not referenced here.
// ---------------------------------------------------------------------------------------------

const clusterNuggetsSrc = extractFunctionSource(SOURCE, 'clusterNuggets');
const clusterNuggetsExtracted = new Function(`
  ${clusterNuggetsSrc}
  return { clusterNuggets };
`)();
const { clusterNuggets } = clusterNuggetsExtracted;

assert.equal(typeof clusterNuggets, 'function', 'clusterNuggets extraction failed');

function makeNugget(id, tag) {
  return { id, type: 'KNOWLEDGE', system_tag: tag, content: `content for ${id}` };
}

function makeResult(batchId, nuggets) {
  return { batch_id: batchId, nuggets };
}

test('clusterNuggets/verdict: keep with canonical_slug present keys under canonical_slug', () => {
  const curatedMap = { 'raw-tag-keep': { verdict: 'keep', canonical_slug: 'canonical-keep-slug', merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-keep')])];
  const drops = [];

  const clusters = clusterNuggets(results, curatedMap, drops);

  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].topicKey, 'canonical-keep-slug');
  assert.deepEqual(drops, []);
});

// A `keep` verdict with no canonical_slug fails loud (AC7 no-silent-degradation), same contract
// normalize/merge already enforce below.
test('clusterNuggets/fail-loud: keep entry with canonical_slug null throws', () => {
  const curatedMap = { 'raw-tag-keep-bare': { verdict: 'keep', canonical_slug: null, merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-keep-bare')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-keep-bare.*verdict 'keep' but no canonical_slug/,
    'must throw naming the tag and the missing canonical_slug on a keep verdict'
  );
});

test('clusterNuggets/verdict: normalize keys under canonical_slug', () => {
  const curatedMap = { 'raw-tag-norm': { verdict: 'normalize', canonical_slug: 'normalized-slug', merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-norm')])];
  const drops = [];

  const clusters = clusterNuggets(results, curatedMap, drops);

  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].topicKey, 'normalized-slug');
});

test('clusterNuggets/verdict: merge keys under merge_target, NOT canonical_slug, even when they differ', () => {
  // The distinction that shipped wrong once already: canonical_slug and merge_target are
  // deliberately DIFFERENT here so a regression that rekeys on canonical_slug is caught.
  const curatedMap = {
    'raw-tag-merge': { verdict: 'merge', canonical_slug: 'raw-tag-merge-own-slug', merge_target: 'destination-family-slug', reason: null },
  };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-merge')])];
  const drops = [];

  const clusters = clusterNuggets(results, curatedMap, drops);

  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].topicKey, 'destination-family-slug');
  assert.notEqual(clusters[0].topicKey, 'raw-tag-merge-own-slug');
});

test('clusterNuggets/verdict: drop is excluded from clusters and pushed onto drops with tag, nugget id, reason', () => {
  const curatedMap = {
    'raw-tag-drop': { verdict: 'drop', canonical_slug: null, merge_target: null, reason: 'family-total-below-keep_threshold' },
  };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-drop')])];
  const drops = [];

  const clusters = clusterNuggets(results, curatedMap, drops);

  assert.equal(clusters.length, 0, 'dropped tag must not produce a cluster');
  assert.equal(drops.length, 1);
  assert.equal(drops[0].tag, 'raw-tag-drop');
  assert.equal(drops[0].nugget_id, 'n1');
  assert.equal(drops[0].reason, 'family-total-below-keep_threshold');
});

// ---------------------------------------------------------------------------------------------
// clusterNuggets — fail-loud coverage (AC7: no silent degradation). Each case must throw and
// name the missing/offending field, not silently invent a bucket or pass the nugget through.
// ---------------------------------------------------------------------------------------------

test('clusterNuggets/fail-loud: tag absent from the curated map entirely throws', () => {
  const curatedMap = {}; // deliberately does not contain 'unknown-tag'
  const results = [makeResult('b1', [makeNugget('n1', 'unknown-tag')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /unknown-tag.*absent from the curated map/,
    'must throw naming the tag absent from the curated map'
  );
});

test('clusterNuggets/fail-loud: merge entry with merge_target null throws', () => {
  const curatedMap = { 'raw-tag-bad-merge': { verdict: 'merge', canonical_slug: 'x', merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-bad-merge')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-bad-merge.*merge_target/,
    'must throw naming the missing merge_target'
  );
});

test('clusterNuggets/fail-loud: merge entry with merge_target missing (undefined key) throws', () => {
  const curatedMap = { 'raw-tag-missing-merge-key': { verdict: 'merge', canonical_slug: 'x', reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-missing-merge-key')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-missing-merge-key.*merge_target/,
    'must throw naming the missing merge_target even when the key itself is absent'
  );
});

test('clusterNuggets/fail-loud: normalize entry with canonical_slug null throws', () => {
  const curatedMap = { 'raw-tag-bad-norm': { verdict: 'normalize', canonical_slug: null, merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-bad-norm')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-bad-norm.*canonical_slug/,
    'must throw naming the missing canonical_slug'
  );
});

test('clusterNuggets/fail-loud: normalize entry with canonical_slug missing (undefined key) throws', () => {
  const curatedMap = { 'raw-tag-missing-norm-key': { verdict: 'normalize', merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-missing-norm-key')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-missing-norm-key.*canonical_slug/,
    'must throw naming the missing canonical_slug even when the key itself is absent'
  );
});

test('clusterNuggets/fail-loud: unrecognized verdict string throws and names the verdict', () => {
  const curatedMap = { 'raw-tag-weird': { verdict: 'obliterate', canonical_slug: null, merge_target: null, reason: null } };
  const results = [makeResult('b1', [makeNugget('n1', 'raw-tag-weird')])];

  assert.throws(
    () => clusterNuggets(results, curatedMap, []),
    /raw-tag-weird.*unrecognized verdict.*obliterate/,
    'must throw naming the tag and the unrecognized verdict value'
  );
});

// ---------------------------------------------------------------------------------------------
// clusterNuggets — census mode (no curatedMap) is genuinely unchanged: invocation A's
// tag-census path keys on the raw system_tag || topic || 'uncategorized' fallback chain and
// must not inherit curated mode's fail-loud behavior.
// ---------------------------------------------------------------------------------------------

test('clusterNuggets/census: with no curated map, keys on raw system_tag and does not throw for any tag shape', () => {
  const results = [
    makeResult('b1', [
      makeNugget('n1', 'plain-system-tag'),
      { id: 'n2', type: 'KNOWLEDGE', topic: 'topic-only-no-system-tag', content: 'c2' },
      { id: 'n3', type: 'KNOWLEDGE', content: 'c3' }, // neither system_tag nor topic
    ]),
  ];

  const clusters = clusterNuggets(results, null, []);
  const topicKeys = clusters.map((c) => c.topicKey).sort();

  assert.deepEqual(topicKeys, ['plain-system-tag', 'topic-only-no-system-tag', 'uncategorized'].sort());
});

// ---------------------------------------------------------------------------------------------
// clusterNuggets — cold-start drop-rate baseline (RECORDED, not asserted absent). Per the plan's
// C5 amendment: build a cold-start-shaped fixture (empty wikiSlugs is irrelevant to
// clusterNuggets itself — the relevant cold-start shape here is a long count-1 tag tail) driven
// through the curated path with a verdict payload whose drops are shaped like a keep_threshold-
// driven drop set, and record the resulting numbers as a baseline.
//
// This fixture exercises OUR rekeying and drop-recording against a SYNTHETIC payload — it does
// not re-measure claude-klabauter's gate. The numbers below are a regression baseline for our code, not
// evidence about their judgment.
//
// Anchor for plausibility — claude-klabauter's measured census (state/audits/2026-08-06-curate-clusters-
// cold-start-drop-rate-census.md; their corpus, 433 nuggets / 249 distinct tags, deterministically
// subsampled, mean of 20 seeds):
//
//   | N nuggets | thr=2  | thr=1 |
//   |----------:|-------:|------:|
//   |        20 |  71.2% | 12.0% |
//   |        60 |  44.4% |  8.7% |
//   |       150 |  27.4% |  8.8% |
//   |   433 (full) | 17.1% | 8.1% |
//
// The finding that matters: at keep_threshold=1 the drop rate is FLAT (8-12%) across a 20x
// corpus-size range — the structural bare-token rule is corpus-size-invariant because it never
// consults corpus size. The cold-start degeneration is entirely keep_threshold. The plan's
// original blunt-tail prediction did NOT materialize.
// ---------------------------------------------------------------------------------------------

test('clusterNuggets/cold-start baseline: recorded drop count and per-reason breakdown for a keep_threshold=1-shaped fixture', () => {
  // 20-nugget cold-start-shaped corpus: a handful of multi-nugget "surviving" families plus a
  // long count-1 tail, mirroring claude-klabauter's N=20 subsample shape (their measured drop rate at
  // thr=1 for N=20 is 12.0% — a synthetic analogue, not a replay of their actual data).
  const nuggets = [];
  const curatedMap = {};

  // Two surviving families (kept as-is): one 3-nugget family, one 2-nugget family.
  curatedMap['survivor-family-a'] = { verdict: 'keep', canonical_slug: 'survivor-family-a', merge_target: null, reason: null };
  nuggets.push(makeNugget('sa-1', 'survivor-family-a'), makeNugget('sa-2', 'survivor-family-a'), makeNugget('sa-3', 'survivor-family-a'));

  curatedMap['survivor-family-b'] = { verdict: 'normalize', canonical_slug: 'survivor-family-b-normalized', merge_target: null, reason: null };
  nuggets.push(makeNugget('sb-1', 'survivor-family-b'), makeNugget('sb-2', 'survivor-family-b'));

  // One merge pair folding into the first survivor's family.
  curatedMap['merge-into-a'] = { verdict: 'merge', canonical_slug: 'merge-into-a', merge_target: 'survivor-family-a', reason: null };
  nuggets.push(makeNugget('ma-1', 'merge-into-a'));

  // Long count-1 tail, each below keep_threshold=1 is NOT how the drop is decided here — these
  // are pre-computed as 'drop' entries by the (synthetic) verdict payload, shaped as the
  // bare-token-with-no-compound-sibling path, mirroring cold-start's dominant drop cause.
  const DROP_TAIL_COUNT = 14;
  for (let i = 0; i < DROP_TAIL_COUNT; i++) {
    const tag = `bare-tail-tag-${i}`;
    curatedMap[tag] = { verdict: 'drop', canonical_slug: null, merge_target: null, reason: 'bare-token-with-no-compound-sibling' };
    nuggets.push(makeNugget(`bt-${i}`, tag));
  }

  const totalInputNuggets = nuggets.length;
  const results = [makeResult('cold-start-b1', nuggets)];
  const drops = [];

  const clusters = clusterNuggets(results, curatedMap, drops);

  // RECORDED BASELINE (not asserted-absent): with a 20-nugget cold-start-shaped corpus and this
  // synthetic keep_threshold=1-style verdict payload, exactly 14 of 20 nuggets drop (70%) and
  // all 14 carry the bare-token-with-no-compound-sibling reason. 70% sits above claude-klabauter's
  // measured N=20/thr=1 mean of 12.0% because this fixture's drop tail is deliberately
  // maximal (14 of 20) to exercise the recording path robustly, not calibrated to reproduce
  // their exact mean — see the file-level comment above for why a synthetic fixture cannot
  // stand in for a replay of their gate.
  assert.equal(totalInputNuggets, 20);
  assert.equal(drops.length, 14, 'recorded drop count baseline');
  assert.equal(clusters.reduce((n, c) => n + c.nuggets.length, 0), 6, 'recorded surviving nugget count baseline');

  const byReason = {};
  for (const d of drops) byReason[d.reason] = (byReason[d.reason] || 0) + 1;
  assert.deepEqual(byReason, { 'bare-token-with-no-compound-sibling': 14 }, 'recorded per-reason breakdown baseline');

  // Surviving clusters: the two keep/normalize families plus the merge target absorbing the
  // merged nugget (3 clusters total: survivor-family-a [now 4, incl. the merge], the normalized
  // survivor-family-b-normalized [2]).
  const topicKeys = clusters.map((c) => c.topicKey).sort();
  assert.deepEqual(topicKeys, ['survivor-family-a', 'survivor-family-b-normalized'], 'recorded surviving topicKey set baseline');
});

// ---------------------------------------------------------------------------------------------
// AC9a — replay claude-klabauter's pinned 2026-08-06 verdict payload through our curated `clusterNuggets`
// path (chunk C5c).
//
// The AC as written names "123 surviving topics" as the oracle. That number is a mis-specified
// oracle: the plan's Problem section measured OUR corpus at 549 tags / 1200 nuggets, of which
// ~426 were estimated droppable/mergeable/normalizable (549 - 426 = 123) — an approximate count
// of surviving TAGS on OUR corpus. The pinned payload below reports surviving DESTINATIONS on
// THEIR corpus (433 nuggets / 249 tags). Different corpus, different definition, approximate
// input — it cannot and should not reproduce, and this test does not chase it. What this test
// asserts instead is the AC's actual intent (the clause after the dash): a mechanical regression
// test proving our rekey logic agrees with claude-klabauter's own accounting of the same fixed input.
//
// Fixture: coordinator/pipelines/artifact-distillation/tests/fixtures/2026-08-06-curate-clusters-
// verdict-payload.json — a verbatim copy of claude-klabauter's pinned payload (commit
// 4d199f9a039b4e00c09241b53cddd43c91394747), state/audits/2026-08-06-curate-clusters-verdict-
// payload.json there. See cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-
// threshold-3-measured-and-payload-pinned.md.
// ---------------------------------------------------------------------------------------------

const VERDICT_PAYLOAD = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', '2026-08-06-curate-clusters-verdict-payload.json'), 'utf8')
);

// Build a curatedMap (raw tag -> verdict entry) and a synthetic one-nugget-per-tag input from a
// threshold's verdict list, in the shape clusterNuggets expects.
function curatedMapFromVerdicts(verdicts) {
  const curatedMap = {};
  for (const v of verdicts) {
    curatedMap[v.tag] = {
      verdict: v.verdict,
      canonical_slug: v.canonical_slug,
      merge_target: v.merge_target,
      reason: v.reason,
    };
  }
  return curatedMap;
}

function syntheticResultsFromVerdicts(verdicts) {
  const nuggets = verdicts.map((v, i) => makeNugget(`payload-n-${i}`, v.tag));
  return [makeResult('payload-b1', nuggets)];
}

test('AC9a: destination-count reproduction — our clusterNuggets rekeying agrees with claude-klabauter\'s surviving_topic_count at every pinned threshold', () => {
  const expected = { auto: 53, 1: 92, 2: 53, 3: 40 };

  for (const [thr, expectedSurviving] of Object.entries(expected)) {
    const entry = VERDICT_PAYLOAD.by_threshold[String(thr)];
    assert.ok(entry, `fixture missing by_threshold[${thr}]`);
    const verdicts = entry.curate_clusters_result.verdicts;
    assert.equal(entry.surviving_topic_count, expectedSurviving, `payload's own surviving_topic_count drifted for threshold ${thr}`);

    const curatedMap = curatedMapFromVerdicts(verdicts);
    const results = syntheticResultsFromVerdicts(verdicts);
    const drops = [];

    const clusters = clusterNuggets(results, curatedMap, drops);
    const distinctTopicKeys = new Set(clusters.map((c) => c.topicKey));

    assert.equal(
      distinctTopicKeys.size,
      expectedSurviving,
      `threshold ${thr}: our clusterNuggets rekeying produced ${distinctTopicKeys.size} distinct topics, claude-klabauter's payload reports ${expectedSurviving}`
    );
  }
});

test('AC9a: per-verdict field-level conformance over the real pinned payload (all four thresholds)', () => {
  for (const thr of ['auto', '1', '2', '3']) {
    const verdicts = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result.verdicts;
    const seenTags = new Set();

    for (const v of verdicts) {
      assert.ok(!seenTags.has(v.tag), `threshold ${thr}: duplicate verdict entry for tag ${v.tag}`);
      seenTags.add(v.tag);

      if (v.verdict === 'merge') {
        assert.ok(v.merge_target, `threshold ${thr}: merge entry for ${v.tag} must have a non-null merge_target`);
      } else {
        assert.equal(v.merge_target, null, `threshold ${thr}: merge_target must be null on non-merge verdict for ${v.tag} (${v.verdict})`);
      }

      if (v.verdict === 'drop') {
        assert.ok(v.reason && v.reason.length > 0, `threshold ${thr}: drop entry for ${v.tag} must carry a non-empty reason`);
      }
    }

    // Exactly one verdict entry per raw input tag: verdict count equals the payload's own
    // reported total (counts.total), and every distinct-tag entry accounted for above matches it.
    const total = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result.counts.total;
    assert.equal(verdicts.length, total, `threshold ${thr}: verdict list length must equal counts.total`);
    assert.equal(seenTags.size, total, `threshold ${thr}: one verdict entry per raw input tag required`);
  }
});

test('AC9a: drop_cause conformance and the bare-no-sibling threshold-invariant (flat at 25 for thresholds 1, 2, 3)', () => {
  const VALID_DROP_CAUSES = new Set(['placeholder', 'bare-no-sibling', 'below-threshold']);

  for (const thr of ['auto', '1', '2', '3']) {
    const verdicts = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result.verdicts;
    for (const v of verdicts) {
      if (v.verdict === 'drop') {
        assert.ok(VALID_DROP_CAUSES.has(v.drop_cause), `threshold ${thr}: drop entry for ${v.tag} has invalid drop_cause: ${v.drop_cause}`);
      } else {
        assert.ok(
          v.drop_cause === null || v.drop_cause === undefined,
          `threshold ${thr}: drop_cause must be null/absent on non-drop verdict for ${v.tag} (${v.verdict}), got ${v.drop_cause}`
        );
      }
    }
  }

  // The sharpest regression signal in the payload: bare-no-sibling is a structural rule that
  // never consults the threshold, so its count must be identical across thresholds 1, 2, 3.
  for (const thr of ['1', '2', '3']) {
    const dropByCause = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result.counts.drop_by_cause;
    assert.equal(dropByCause['bare-no-sibling'], 25, `threshold ${thr}: bare-no-sibling must be flat at 25 — if this moved, claude-klabauter's classifier changed`);
  }
});

test('candidates: wiki_path mismatch against the sanity-checked target is logged, not silently dropped', () => {
  const clusters = [{ topicKey: 'topic-d', wikiPath: 'docs/wiki/topic-d.md' }];
  // Relay agent echoed a stale/wrong wiki_path — the sanity check should log it while still
  // preserving the candidate_restatements payload keyed by topic_key.
  const candidatesResults = [
    { topic_key: 'topic-d', wiki_path: 'docs/wiki/WRONG-PATH.md', candidate_restatements: [{ line: 1, excerpt: 'y' }] },
  ];

  const logs = [];
  const map = buildCandidatesByTopic(candidatesResults, clusters, {}, ['docs/wiki'], (msg) => logs.push(msg));

  assert.deepEqual(map.get('topic-d'), [{ line: 1, excerpt: 'y' }], 'candidate_restatements must still be preserved despite the path mismatch');
  assert.equal(logs.length, 1, 'exactly one mismatch warning must be logged');
  assert.match(logs[0], /wiki_path sanity check failed/);
  assert.match(logs[0], /topic-d/);
});

// ---------------------------------------------------------------------------------------------
// C3e: applyHomingOverride must preserve canonical_slug, not just the verdict — chained through
// clusterNuggets to prove the fragmentation the bug reintroduces. See
// docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md chunk C3e.
// ---------------------------------------------------------------------------------------------

const applyHomingOverrideSrc = extractFunctionSource(SOURCE, 'applyHomingOverride');
const slugifyTopicSrcForOverride = extractFunctionSource(SOURCE, 'slugifyTopic');
const dr146NormalizeSrcForOverride = extractFunctionSource(SOURCE, 'dr146Normalize');
const findFuzzyWikiHomeSrcForOverride = extractFunctionSource(SOURCE, 'findFuzzyWikiHome');
const leadingStemSrcForOverride = extractFunctionSource(SOURCE, 'leadingStem');
const overrideExtracted = new Function(`
  const DR146_MIN_STEM_LEN = ${DR146_MIN_STEM_LEN};
  const STEM_PREFIX_LEN = ${STEM_PREFIX_LEN};
  const DR146_STRIP_SUFFIXES = ['-shape', '-design', '-v2'];
  const DR146_DATE_PREFIX_RE = /^\\d{4}-\\d{2}-\\d{2}-/;
  ${slugifyTopicSrcForOverride}
  ${dr146NormalizeSrcForOverride}
  ${leadingStemSrcForOverride}
  ${findFuzzyWikiHomeSrcForOverride}
  ${applyHomingOverrideSrc}
  return { applyHomingOverride };
`)();
const { applyHomingOverride } = overrideExtracted;

assert.equal(typeof applyHomingOverride, 'function', 'applyHomingOverride extraction failed');

test('C3e regression: two shape-variant tags overridden to the same canonical_slug must collapse into ONE cluster, not two', () => {
  const curatedMap = {
    'git_safety': { verdict: 'drop', canonical_slug: 'git-safety', merge_target: null, reason: 'family-total-below-keep_threshold' },
    'git.safety': { verdict: 'drop', canonical_slug: 'git-safety', merge_target: null, reason: 'family-total-below-keep_threshold' },
  };
  const wikiSlugs = { 'git-safety': 'docs/wiki/git-safety.md' };

  const { resolvedMap } = applyHomingOverride(curatedMap, wikiSlugs);

  const results = [
    makeResult('b1', [makeNugget('n1', 'git_safety')]),
    makeResult('b2', [makeNugget('n2', 'git.safety')]),
  ];
  const drops = [];
  const clusters = clusterNuggets(results, resolvedMap, drops);

  assert.equal(clusters.length, 1, 'both shape variants must collapse into a single cluster keyed by canonical_slug');
  assert.equal(clusters[0].topicKey, 'git-safety');
});

test('C3e: override preserves canonical_slug — an overridden tag keys under canonical_slug, not the raw tag', () => {
  // Raw tag's OWN slugified form ('git-safety') is what matches the wiki home (mirrors the
  // matching logic in applyHomingOverride); canonical_slug carries the same normalized value.
  // With the bug, the discarded canonical_slug means clusterNuggets falls back to the raw,
  // unnormalized tag string (still containing the underscore) instead.
  const curatedMap = {
    'git_safety': { verdict: 'drop', canonical_slug: 'git-safety', merge_target: null, reason: 'family-total-below-keep_threshold' },
  };
  const wikiSlugs = { 'git-safety': 'docs/wiki/git-safety.md' };

  const { resolvedMap, overrideCount } = applyHomingOverride(curatedMap, wikiSlugs);

  assert.equal(overrideCount, 1);
  assert.equal(resolvedMap['git_safety'].verdict, 'keep');
  assert.equal(resolvedMap['git_safety'].canonical_slug, 'git-safety');

  const results = [makeResult('b1', [makeNugget('n1', 'git_safety')])];
  const drops = [];
  const clusters = clusterNuggets(results, resolvedMap, drops);

  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].topicKey, 'git-safety', 'must key under canonical_slug, not the raw (unnormalized) tag');
});

test('C3e: override clears a stale merge_target — an entry overridden from merge to keep carries no residual merge_target', () => {
  const curatedMap = {
    'git_safety': { verdict: 'merge', canonical_slug: 'git-safety', merge_target: 'some-other-family-slug', reason: null },
  };
  const wikiSlugs = { 'git-safety': 'docs/wiki/git-safety.md' };

  const { resolvedMap } = applyHomingOverride(curatedMap, wikiSlugs);

  assert.equal(resolvedMap['git_safety'].verdict, 'keep');
  assert.equal(resolvedMap['git_safety'].merge_target, null, 'merge_target must be nulled out on override from merge to keep');
});

// The fixtures above give every `drop` a populated canonical_slug, which claude-klabauter's
// `distill.curate_clusters` never does — Pass 5 of coordinator_core/ops/distill_curate_clusters.py
// emits `canonical_slug: None` on EVERY drop, and `drop` is the dominant override input. Reported
// live by claude-klabauter-em (cross-repo/inbox/2026-08-27-claude-klabauter-em-distill-has-no-retain-
// disposition.md), hit on `strategic-self-description-generation`: the override manufactured a
// `keep` with no slug and clusterNuggets() fail-louded, halting the whole run. These two tests
// pin the real payload shape — do not "normalize" them to carry a slug.
test('drop-with-null-slug: an override on claude-klabauter\'s real drop payload derives a canonical_slug rather than manufacturing a slugless keep', () => {
  const curatedMap = {
    'strategic_self_description_generation': {
      verdict: 'drop', canonical_slug: null, merge_target: null,
      reason: 'family-total-below-keep_threshold', drop_cause: 'below-threshold',
    },
  };
  const wikiSlugs = { 'strategic-self-description-generation': 'docs/wiki/strategic-self-description-generation.md' };

  const { resolvedMap, overrideCount } = applyHomingOverride(curatedMap, wikiSlugs);

  assert.equal(overrideCount, 1);
  assert.equal(resolvedMap['strategic_self_description_generation'].verdict, 'keep');
  assert.equal(
    resolvedMap['strategic_self_description_generation'].canonical_slug,
    'strategic-self-description-generation',
    'promotion must derive the slug it matched the wiki home on'
  );
});

test('drop-with-null-slug: the promoted entry survives clusterNuggets instead of halting the run', () => {
  const curatedMap = {
    'strategic_self_description_generation': {
      verdict: 'drop', canonical_slug: null, merge_target: null,
      reason: 'family-total-below-keep_threshold', drop_cause: 'below-threshold',
    },
  };
  const wikiSlugs = { 'strategic-self-description-generation': 'docs/wiki/strategic-self-description-generation.md' };

  const { resolvedMap } = applyHomingOverride(curatedMap, wikiSlugs);
  const results = [makeResult('b1', [makeNugget('n1', 'strategic_self_description_generation')])];
  const drops = [];
  const clusters = clusterNuggets(results, resolvedMap, drops);

  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].topicKey, 'strategic-self-description-generation');
  assert.equal(drops.length, 0);
});

test('drop-with-null-slug: a drop with NO wiki home is left a drop — the override must not promote it', () => {
  const curatedMap = {
    'some_tag_with_no_home': {
      verdict: 'drop', canonical_slug: null, merge_target: null,
      reason: 'family-total-below-keep_threshold', drop_cause: 'below-threshold',
    },
  };

  const { resolvedMap, overrideCount } = applyHomingOverride(curatedMap, {});

  assert.equal(overrideCount, 0);
  assert.equal(resolvedMap['some_tag_with_no_home'].verdict, 'drop');
  assert.equal(resolvedMap['some_tag_with_no_home'].canonical_slug, null);
});

// Combines the two scenarios above (colliding
// shape-variant collapse + a stale merge_target that differs from the shared canonical_slug)
// into ONE fixture, chained through clusterNuggets. Defense-in-depth, not a live gap:
// applyHomingOverride unconditionally nulls merge_target on every override, so the "merge_target
// differs from canonical_slug post-override" condition is currently unreachable — this exists to
// catch a FUTURE change that stops unconditionally nulling it. Do not delete as redundant with
// the two tests above; this is the only place all three conditions land in one fixture.
// ---------------------------------------------------------------------------------------------
// dropSummary.by_reason / by_cause grouping — four parallel accumulation blocks (by-tag, by-reason, by-cause, top-10) with no
// prior targeted test. Extracted the same inline-module-scope way emptyContentBlockSrc/
// malformedTagBlockSrc above are, since the grouping runs at top level, not inside a named
// function. Asserts tag_count dedupes (a tag with multiple drops still counts once) while
// nugget_count accumulates per drop.
// ---------------------------------------------------------------------------------------------

const dropGroupingBlockSrc = extractBlockSource(
  SOURCE,
  'const dropsByReason = {}',
  'const dropsByCauseSummary = Object.fromEntries(\n  Object.entries(dropsByCause).map(([cause, bucket]) => [\n    cause,\n    { tag_count: bucket.tag_count, nugget_count: bucket.nugget_count, tags: [...bucket.tags] },\n  ])\n)'
);

function runDropGrouping(droppedTags) {
  const fn = new Function('droppedTags', `
    ${dropGroupingBlockSrc}
    return { dropsByReasonSummary, dropsByCauseSummary };
  `);
  return fn(droppedTags);
}

test('dropSummary grouping: multi-nugget dropped tag spanning two reasons/causes — tag_count dedupes, nugget_count accumulates', () => {
  const droppedTags = [
    { tag: 'flaky-tag', nugget_id: 'n1', reason: 'below-threshold', drop_cause: 'below-threshold' },
    { tag: 'flaky-tag', nugget_id: 'n2', reason: 'below-threshold', drop_cause: 'below-threshold' },
    { tag: 'flaky-tag', nugget_id: 'n3', reason: 'placeholder-shape', drop_cause: 'placeholder' },
    { tag: 'other-tag', nugget_id: 'n4', reason: 'below-threshold', drop_cause: 'below-threshold' },
  ];

  const { dropsByReasonSummary, dropsByCauseSummary } = runDropGrouping(droppedTags);

  // by_reason: 'below-threshold' groups flaky-tag(n1,n2) + other-tag(n4) — 2 distinct tags, 3 nuggets.
  assert.equal(dropsByReasonSummary['below-threshold'].tag_count, 2, 'tag_count must dedupe per tag');
  assert.equal(dropsByReasonSummary['below-threshold'].nugget_count, 3, 'nugget_count must accumulate per drop, not per tag');
  assert.equal(dropsByReasonSummary['placeholder-shape'].tag_count, 1);
  assert.equal(dropsByReasonSummary['placeholder-shape'].nugget_count, 1);

  // by_cause mirrors the same shape on drop_cause instead of reason.
  assert.equal(dropsByCauseSummary['below-threshold'].tag_count, 2);
  assert.equal(dropsByCauseSummary['below-threshold'].nugget_count, 3);
  assert.equal(dropsByCauseSummary['placeholder'].tag_count, 1);
  assert.equal(dropsByCauseSummary['placeholder'].nugget_count, 1);
});

test('C3e regression: shape-variant collapse AND a differing merge_target both survive override, chained through clusterNuggets', () => {
  const curatedMap = {
    'git_safety': { verdict: 'drop', canonical_slug: 'git-safety', merge_target: null, reason: 'family-total-below-keep_threshold' },
    'git.safety': { verdict: 'merge', canonical_slug: 'git-safety', merge_target: 'some-other-family-slug', reason: null },
  };
  const wikiSlugs = { 'git-safety': 'docs/wiki/git-safety.md' };

  const { resolvedMap } = applyHomingOverride(curatedMap, wikiSlugs);

  assert.equal(resolvedMap['git.safety'].verdict, 'keep');
  assert.equal(resolvedMap['git.safety'].merge_target, null, 'merge_target must be nulled out post-override even when it differed from canonical_slug');

  const results = [
    makeResult('b1', [makeNugget('n1', 'git_safety')]),
    makeResult('b2', [makeNugget('n2', 'git.safety')]),
  ];
  const drops = [];
  const clusters = clusterNuggets(results, resolvedMap, drops);

  assert.equal(clusters.length, 1, 'both shape variants must collapse into a single cluster keyed by canonical_slug');
  assert.equal(clusters[0].topicKey, 'git-safety');
});

// ---------------------------------------------------------------------------
// C1: Phase 3d manifest enum retirement — PRESERVE-survival pin
//
// Purpose: PRESERVE is a never-delete disposition class, unconditioned on
// extraction status (docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md
// chunk C1). This pin lands in the same commit as the SKIP->SEND_BACK/BLOCKED
// enum retirement so no window exists where the retired-enum prompt text is on
// disk with nothing asserting PRESERVE survived the edit.
// ---------------------------------------------------------------------------

const PHASE3D_PATH = path.join(__dirname, '..', 'agent-prompts', 'phase-3d.md');
const PHASE3D_SOURCE = fs.readFileSync(PHASE3D_PATH, 'utf8');

test('C1: Phase 3d manifest disposition enum is exactly DELETE/SEND_BACK/BLOCKED/PRESERVE, no SKIP', () => {
  assert.match(
    PHASE3D_SOURCE,
    /`disposition` MUST be one of: `DELETE`, `SEND_BACK`, `BLOCKED`, `PRESERVE`\./,
    'the canonical enum line must list exactly these four tokens'
  );
  // The retired manifest-disposition token must not appear as a bare disposition value
  // anywhere in the file. Phase 1 scanner CLASSIFICATION vocabulary
  // (NEW/ALREADY_CAPTURED/EPHEMERAL/SKIP/PRESERVE) legitimately reuses the SKIP token for a
  // different, unrelated vocabulary (negative spec, phase-3d.md's own Task step 1/5 and the
  // Phase-0-classified-SKIP citations) — this assertion targets the manifest `disposition:`
  // field specifically, not every occurrence of the substring "SKIP" in the file.
  assert.doesNotMatch(
    PHASE3D_SOURCE,
    /disposition:\s*SKIP\b/,
    'no manifest row may declare disposition: SKIP; the enum is retired'
  );
});

test('C1: PRESERVE is never rewritten to DELETE regardless of extraction status — pinned for research/NotebookLM/Pipeline-C paths', () => {
  assert.match(
    PHASE3D_SOURCE,
    /\*\*PRESERVE overrides all other classifications\.\*\*/,
    'PRESERVE must remain the overriding, never-delete disposition class'
  );
  assert.match(
    PHASE3D_SOURCE,
    /All research outputs \(`docs\/research\/`, `~\/docs\/research\/`, Pipeline A\/B\/C\/D outputs\)/,
    'research outputs must stay pinned to PRESERVE'
  );
  assert.match(
    PHASE3D_SOURCE,
    /All NotebookLM outputs \(`tasks\/notebooklm-\*\/`, any file with "notebooklm" in path\)/,
    'NotebookLM outputs must stay pinned to PRESERVE'
  );
  assert.match(
    PHASE3D_SOURCE,
    /Pipeline C structured outputs \(files containing `manifest_version:`\)/,
    'Pipeline C structured outputs must stay pinned to PRESERVE'
  );
  assert.match(
    PHASE3D_SOURCE,
    /\*\*PRESERVE\*\* — research outputs, NotebookLM artifacts, Pipeline C outputs\.\s*\n\s*NEVER delete these regardless of extraction status\./,
    'the disposition-assignment rule for PRESERVE must state it is never deleted regardless of extraction status'
  );
});

// ---------------------------------------------------------------------------
// C3: Phase 3d golden-fixture re-key + vocabulary-conformance pins
//
// Purpose: fixture-4's manifest previously carried a `disposition: SKIP` row in
// the retired vocabulary; it is now re-keyed to `BLOCKED` (docs/plans/
// 2026-08-27-distill-dispositions-and-tail-rollup.md chunk C3). These pins
// guard the two invariants that survive the re-key: the archived-handoff
// exclusion holds across every fixture manifest and every disposition value,
// and the manifest-disposition -> log-disposition mapping (C2,
// coordinator/schemas/distillation-log.schema.md) never lets SEND_BACK or
// BLOCKED leak into the log's `<disposition>` enum.
// ---------------------------------------------------------------------------

const PHASE3D_FIXTURES_DIR = path.join(__dirname, 'phase3d-fixtures');
const PHASE3D_FIXTURE_MANIFESTS = fs
  .readdirSync(PHASE3D_FIXTURES_DIR)
  .filter((entry) => fs.statSync(path.join(PHASE3D_FIXTURES_DIR, entry)).isDirectory())
  .map((entry) => path.join(PHASE3D_FIXTURES_DIR, entry, 'input', 'phase3d-deletion-manifest.md'))
  .filter((manifestPath) => fs.existsSync(manifestPath));

const DISTILLATION_LOG_SCHEMA_PATH = path.join(
  __dirname, '..', '..', '..', 'schemas', 'distillation-log.schema.md'
);
const DISTILLATION_LOG_SCHEMA_SOURCE = fs.readFileSync(DISTILLATION_LOG_SCHEMA_PATH, 'utf8');

test('C3: no archive/handoffs/** path appears in any Phase 3d fixture manifest under any disposition', () => {
  assert.ok(
    PHASE3D_FIXTURE_MANIFESTS.length > 0,
    'expected at least one fixture manifest under tests/phase3d-fixtures/*/input/'
  );
  for (const manifestPath of PHASE3D_FIXTURE_MANIFESTS) {
    const source = fs.readFileSync(manifestPath, 'utf8');
    assert.doesNotMatch(
      source,
      /archive\/handoffs\//,
      `${manifestPath} must not reference an archive/handoffs/** path under any disposition`
    );
  }
});

test('C3: fixture-4 re-keys its former SKIP row to BLOCKED, not left in the retired vocabulary', () => {
  const fixture4Path = path.join(
    PHASE3D_FIXTURES_DIR, 'fixture-4', 'input', 'phase3d-deletion-manifest.md'
  );
  const source = fs.readFileSync(fixture4Path, 'utf8');
  assert.doesNotMatch(
    source,
    /disposition:\s*SKIP\b/,
    'fixture-4 must not declare disposition: SKIP; the enum is retired'
  );
  assert.match(
    source,
    /disposition:\s*BLOCKED\b/,
    'fixture-4 must carry the re-keyed BLOCKED row (formerly the active-handoff-reference SKIP row)'
  );
});

test('C3: the manifest -> log disposition mapping never lets SEND_BACK or BLOCKED leak into the log <disposition> enum', () => {
  assert.match(
    DISTILLATION_LOG_SCHEMA_SOURCE,
    /A `SEND_BACK` manifest row logs as `SKIP`/,
    'schema must state the SEND_BACK -> SKIP log mapping'
  );
  assert.match(
    DISTILLATION_LOG_SCHEMA_SOURCE,
    /A `BLOCKED` manifest row logs as `SKIP`/,
    'schema must state the BLOCKED -> SKIP log mapping'
  );
  assert.match(
    DISTILLATION_LOG_SCHEMA_SOURCE,
    /Neither `SEND_BACK` nor `BLOCKED` may ever appear as a `<disposition>` log token\./,
    'schema must state the negative spec forbidding SEND_BACK/BLOCKED as a log <disposition> token'
  );
  // Parse the actual enum declaration line
  // (`**\`<disposition>\`** — enum, one of: ...`) instead of a phrase-shape heuristic
  // ("disposition" near "one of"), so a schema reformat that drops the words "one of" (a table
  // row, a bulleted list, `Allowed values:`) can't silently stop this half of the test from
  // enforcing anything while the two positive assert.match checks above keep passing.
  const enumLineMatch = DISTILLATION_LOG_SCHEMA_SOURCE.match(
    /\*\*`<disposition>`\*\* — enum, one of: (.+)\./
  );
  assert.ok(enumLineMatch, 'the <disposition> enum declaration line was not found in the schema');
  const enumTokens = enumLineMatch[1].match(/`([A-Z_]+)`/g).map((t) => t.replace(/`/g, ''));
  assert.ok(!enumTokens.includes('SEND_BACK'), 'the log <disposition> enum must not list SEND_BACK as a token');
  assert.ok(!enumTokens.includes('BLOCKED'), 'the log <disposition> enum must not list BLOCKED as a token');
  assert.deepEqual(
    enumTokens,
    ['DISTILLED', 'PROMOTE', 'EPHEMERAL', 'SKIP', 'PRESERVE'],
    'the log <disposition> enum must be exactly these five tokens, in this order'
  );
});

// ---------------------------------------------------------------------------------------------
// C7 — Phases 2.5-3d tail-rollup coverage (docs/plans/2026-08-27-distill-dispositions-and-tail-
// rollup.md, chunk C7). Same extraction discipline as the rest of this file: the MIN_CONVERGENCE
// derivation and the Opus-escalation guard condition are pulled out BY TEXT and evaluated with
// `new Function` against synthetic inputs, so this exercises the ACTUAL landed expressions, not a
// re-implementation. Strict phase sequencing is asserted structurally (textual ordering of the
// coverage-gate merge-back against `phase('judgment-mining-2-5')`), matching the source's own claim
// that the ordering is "structural by placement, not a runtime check."
// ---------------------------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 2.5: MIN_CONVERGENCE default + --min-convergence override
// ---------------------------------------------------------------------------

const MIN_CONVERGENCE_LINE_MATCH = SOURCE.match(
  /const\s+MIN_CONVERGENCE\s*=\s*([^\n;]+)/
);
assert.ok(MIN_CONVERGENCE_LINE_MATCH, 'MIN_CONVERGENCE declaration not found in workflow.js');
const MIN_CONVERGENCE_EXPR = MIN_CONVERGENCE_LINE_MATCH[1].trim();

function evalMinConvergence(loadedInput, rawArgsInput) {
  const fn = new Function('loadedInput', 'RAW_ARGS_INPUT', `
    const MIN_CONVERGENCE = ${MIN_CONVERGENCE_EXPR};
    return MIN_CONVERGENCE;
  `);
  return fn(loadedInput, rawArgsInput);
}

test('2.5: MIN_CONVERGENCE defaults to 3 when neither loadedInput nor RAW_ARGS_INPUT supplies one', () => {
  assert.equal(evalMinConvergence(null, {}), 3);
  assert.equal(evalMinConvergence({}, {}), 3);
});

test('2.5: MIN_CONVERGENCE honours --min-convergence via RAW_ARGS_INPUT.minConvergence', () => {
  assert.equal(evalMinConvergence(null, { minConvergence: 5 }), 5);
});

test('2.5: MIN_CONVERGENCE honours a loadedInput.minConvergence override, taking priority over RAW_ARGS_INPUT', () => {
  assert.equal(evalMinConvergence({ minConvergence: 7 }, { minConvergence: 5 }), 7);
});

test('2.5: MIN_CONVERGENCE reads null-tolerant (??) so an explicit 0 is honoured, not masked back to the default', () => {
  assert.equal(evalMinConvergence({ minConvergence: 0 }, {}), 0);
  assert.equal(evalMinConvergence(null, { minConvergence: 0 }), 0);
});

// ---------------------------------------------------------------------------
// 3a/3-Esc: Opus escalation stays conditional — zero unresolvable contradictions AND zero
// cross-cluster candidates means the escalation branch never constructs an agent.
//
// The guard's condition alone doesn't prove
// anything about the real `opusEscalation` reassignment further down the branch (dispatches an
// Opus agent, a fidelity-check agent, then conditionally rebuilds `opusEscalation`). Extract the
// ACTUAL if-block by anchor (same brace-free technique the other inline blocks in this file use)
// and run it against stubbed `agent`/`parallel`/`phase`/`log`/`COMMON`, so a regression in the
// real reassignment (e.g. `triggered` set unconditionally, or from the wrong source) is caught,
// not just a hand-rolled stand-in for the condition.
// ---------------------------------------------------------------------------

const escalationBlockSrc = extractBlockSource(
  SOURCE,
  "if (totalUnresolvableContradictions > 0 || crossClusterCandidates.length > 0) {",
  "  opusEscalation = {\n    triggered: true,\n    flagged_refs: flaggedRefs,\n    cross_cluster_candidates: crossClusterCandidates,\n    resolution: opusResult || null,\n    fidelity_verdict: fidelityResult,\n  }\n}"
);

// Runs the extracted real if-block. `agentImpl(brief, opts)` and `parallelImpl(thunks, opts)`
// are the only workflow-sandbox globals the block actually calls into (`phase`/`log` are no-ops
// here since they're side-effect-only); everything else (`flaggedRefs`, `opusEscalation`
// construction) is the real landed source.
function runEscalationGuard({ totalUnresolvableContradictions, crossClusterCandidates, contradictionResults, agentImpl, parallelImpl }) {
  const fn = new Function(
    'totalUnresolvableContradictions', 'crossClusterCandidates', 'contradictionResults',
    'phase', 'agent', 'parallel', 'log', 'COMMON',
    `
    return (async () => {
      let opusEscalation = { triggered: false, cross_cluster_candidates: crossClusterCandidates };
      ${escalationBlockSrc}
      return opusEscalation;
    })();
    `
  );
  return fn(
    totalUnresolvableContradictions, crossClusterCandidates, contradictionResults,
    () => {}, agentImpl, parallelImpl, () => {}, ''
  );
}

const defaultParallelImpl = (thunks) => Promise.all(thunks.map((t) => t()));

test('3-Esc: zero unresolvable contradictions and zero cross-cluster candidates means no escalation (agent never dispatched)', async () => {
  let agentCalls = 0;
  const opusEscalation = await runEscalationGuard({
    totalUnresolvableContradictions: 0,
    crossClusterCandidates: [],
    contradictionResults: [],
    agentImpl: () => { agentCalls++; return null; },
    parallelImpl: defaultParallelImpl,
  });
  assert.equal(opusEscalation.triggered, false);
  assert.equal(agentCalls, 0, 'the escalation agent must never be dispatched when both counts are zero');
});

test('3-Esc: a nonzero unresolvable-contradiction count triggers a real escalation and rebuilds opusEscalation from the agent responses', async () => {
  const opusEscalation = await runEscalationGuard({
    totalUnresolvableContradictions: 2,
    crossClusterCandidates: [],
    contradictionResults: [{ cluster_tag: 'c1', unresolvable_contradictions: 2, contradiction_refs: [{ claim_id: 'claim-1' }] }],
    agentImpl: (brief, opts) => {
      if (opts.label === 'opus-3esc') return { resolutions: [{ claim_id: 'claim-1', winner: 'src-a', rationale: 'temporal' }] };
      if (opts.label === 'opus-3esc-fidelity') return { fidelity_verdict: 'PASS' };
      throw new Error(`unexpected agent label: ${opts.label}`);
    },
    parallelImpl: defaultParallelImpl,
  });

  assert.equal(opusEscalation.triggered, true, 'the real reassignment must set triggered:true, not a hand-rolled stand-in');
  assert.equal(opusEscalation.resolution.resolutions[0].claim_id, 'claim-1');
  assert.equal(opusEscalation.fidelity_verdict.fidelity_verdict, 'PASS');
});

test('3-Esc: a nonzero cross-cluster candidate count alone triggers escalation, even with zero unresolvable contradictions', async () => {
  const opusEscalation = await runEscalationGuard({
    totalUnresolvableContradictions: 0,
    crossClusterCandidates: [{ claim_id: 'c1' }],
    contradictionResults: [],
    agentImpl: (brief, opts) => (opts.label === 'opus-3esc' ? { resolutions: [] } : { fidelity_verdict: 'PASS' }),
    parallelImpl: defaultParallelImpl,
  });
  assert.equal(opusEscalation.triggered, true);
});

test('3-Esc: the Opus resolution agent failing to return a result surfaces unresolved (resolution: null) rather than throwing', async () => {
  const opusEscalation = await runEscalationGuard({
    totalUnresolvableContradictions: 1,
    crossClusterCandidates: [],
    contradictionResults: [{ cluster_tag: 'c1', unresolvable_contradictions: 1, contradiction_refs: [] }],
    agentImpl: () => null,
    parallelImpl: defaultParallelImpl,
  });

  assert.equal(opusEscalation.triggered, true, 'the branch still ran and rebuilt opusEscalation even on agent failure');
  assert.equal(opusEscalation.resolution, null, 'a failed Opus dispatch must surface as resolution: null, not block the run');
  assert.equal(opusEscalation.fidelity_verdict, null, 'the fidelity check must never run when there is no Opus result to verify');
});

test('3-Esc: opusEscalation.triggered defaults to false ahead of the guard, so an untriggered run reports triggered:false rather than an absent field', () => {
  assert.match(
    SOURCE,
    /let\s+opusEscalation\s*=\s*\{\s*\n\s*triggered:\s*false,/,
    'opusEscalation must default-initialize triggered:false before the conditional escalation block'
  );
});

// ---------------------------------------------------------------------------
// Strict sequencing — the judgment-mining phase cannot start before the coverage gate's
// merge-back completes. Sequencing here is a plain top-to-bottom script, so the source's own
// claim ("structural by placement, not a runtime check") is verified as textual ordering: the
// coverage-gate merge-back statement must appear strictly before `phase('judgment-mining-2-5')`.
// ---------------------------------------------------------------------------

test('sequencing: the coverage-gate gap-synth merge-back precedes phase(\'judgment-mining\') in source order', () => {
  // Anchor on the code identifier the
  // merge-back loop actually declares, not the prose comment above it; a copy-edit to that
  // comment must not be able to break this test.
  const mergeBackAnchor = 'const synthResultsByTopic = new Map(synthResults.map((r) => [slugifyTopic(r.topic_key), r]))';
  const mergeBackIdx = SOURCE.indexOf(mergeBackAnchor);
  const judgmentMiningPhaseIdx = SOURCE.indexOf("phase('judgment-mining-2-5')");

  assert.notEqual(mergeBackIdx, -1, 'coverage-gate merge-back code anchor not found in workflow.js');
  assert.notEqual(judgmentMiningPhaseIdx, -1, "phase('judgment-mining-2-5') call not found in workflow.js");
  assert.ok(
    mergeBackIdx < judgmentMiningPhaseIdx,
    'the coverage-gate merge-back must complete before judgment-mining starts (structural-by-placement sequencing)'
  );
});

test('sequencing: phase(\'coverage-gate\') itself precedes phase(\'judgment-mining\') in source order', () => {
  const coverageGatePhaseIdx = SOURCE.indexOf("phase('coverage-gate')");
  const judgmentMiningPhaseIdx = SOURCE.indexOf("phase('judgment-mining-2-5')");

  assert.notEqual(coverageGatePhaseIdx, -1, "phase('coverage-gate') call not found in workflow.js");
  assert.notEqual(judgmentMiningPhaseIdx, -1, "phase('judgment-mining-2-5') call not found in workflow.js");
  assert.ok(coverageGatePhaseIdx < judgmentMiningPhaseIdx, 'phase(\'coverage-gate\') must run before phase(\'judgment-mining\')');
});

// ---------------------------------------------------------------------------
// Adversarial-review Finding 1 (2026-08-27): the un-harvested guard in the distillation-log-rows
// loop was BATCH-granular (`scanned`) against an ARTIFACT-granular claim — an artifact silently
// omitted by the scan agent (no fate line AND no nuggets) inside an otherwise-successful batch
// fell through to EPHEMERAL, which Phase 3d maps to DELETE. The block is extracted by anchor,
// the same brace-free shape emptyContentBlockSrc/malformedTagBlockSrc above use, since it runs
// inline at module scope, not as a named function.
// ---------------------------------------------------------------------------

const distillationLogRowsBlockSrc = extractBlockSource(
  SOURCE,
  'function countWords(s) {',
  'distillationLogRows.push({ path, disposition, fate })\n  }\n}'
);

function runDistillationLogRows({ scanResults, synthResults, BATCHES, failedBatchIds, CONTEXT_TERMS }) {
  const fn = new Function(
    'scanResults', 'synthResults', 'BATCHES', 'failedBatchIds', 'CONTEXT_TERMS',
    `
    ${distillationLogRowsBlockSrc}
    return distillationLogRows;
    `
  );
  return fn(scanResults, synthResults, BATCHES, failedBatchIds, CONTEXT_TERMS);
}

test('Finding 1: an artifact untouched by the scan agent in an otherwise-good batch gets SKIP, not EPHEMERAL', () => {
  const rows = runDistillationLogRows({
    scanResults: [{ batch_id: 'b1', file_fates: [], nuggets: [] }],
    synthResults: [],
    BATCHES: [{ batchId: 'b1', files: ['path/silently-omitted.md'] }],
    failedBatchIds: [],
    CONTEXT_TERMS: [],
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0].disposition, 'SKIP', 'no fate line AND no nuggets for this path means the scan agent never actually reviewed it, despite its batch succeeding');
});

test('Finding 1: an artifact WITH a fate line and zero nuggets still resolves EPHEMERAL (ordinary case not flipped)', () => {
  const rows = runDistillationLogRows({
    scanResults: [{
      batch_id: 'b1',
      file_fates: [{ path: 'path/reviewed-nothing-to-extract.md', fate_prose: 'Routine config file, nothing worth distilling here at all.' }],
      nuggets: [],
    }],
    synthResults: [],
    BATCHES: [{ batchId: 'b1', files: ['path/reviewed-nothing-to-extract.md'] }],
    failedBatchIds: [],
    CONTEXT_TERMS: [],
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0].disposition, 'EPHEMERAL', 'a fate line present means the scan agent DID review this artifact — the ordinary reviewed-nothing-to-carry case must not be flipped to SKIP');
});

// ---------------------------------------------------------------------------
// Adversarial-review Finding 3 (2026-08-27): the Cross-Repo Archive Specialist Branch's
// `crossRepoDispositions` had no code path into the Phase 3d deletion manifest. Pinned by
// extracting the merge block by anchor, the same shape the other inline blocks above use.
// ---------------------------------------------------------------------------

const crossRepoMergeBlockSrc = extractBlockSource(
  SOURCE,
  '// Cross-Repo Archive Specialist Branch merge',
  "log('phase-3d: no cross-repo disposition rows supplied — no-op.')\n}"
);

function runCrossRepoMerge({ phase3d, CROSS_REPO_DISPOSITIONS }) {
  const logs = [];
  const fn = new Function(
    'phase3d', 'CROSS_REPO_DISPOSITIONS', 'log',
    `
    ${crossRepoMergeBlockSrc}
    return phase3d;
    `
  );
  return fn(phase3d, CROSS_REPO_DISPOSITIONS, (msg) => logs.push(msg));
}

test('Finding 3: a supplied crossRepoDispositions row appears in the merged Phase 3d manifest', () => {
  const row = { artifact_path: 'other-repo/foo.md', disposition: 'DELETE', reason: 'cross-repo settled', source_nugget_ids: [] };
  const result = runCrossRepoMerge({
    phase3d: { status: 'ran', deletions: [{ artifact_path: 'local/bar.md', disposition: 'DELETE', reason: 'x', source_nugget_ids: [] }] },
    CROSS_REPO_DISPOSITIONS: [row],
  });

  assert.equal(result.deletions.length, 2);
  assert.ok(result.deletions.some((d) => d.artifact_path === 'other-repo/foo.md'), 'the cross-repo row must be spliced into the manifest');
});

test('Finding 3: an absent/empty crossRepoDispositions input is a clean no-op', () => {
  const original = { status: 'ran', deletions: [{ artifact_path: 'local/bar.md', disposition: 'DELETE', reason: 'x', source_nugget_ids: [] }] };
  const result = runCrossRepoMerge({ phase3d: original, CROSS_REPO_DISPOSITIONS: [] });

  assert.deepEqual(result.deletions, original.deletions, 'an empty crossRepoDispositions input must not alter the manifest');
});

// ---------------------------------------------------------------------------
// Reviewer P1 (2026-08-27, coordinatorcode-reviewer.a49f198a29393f4cf): cross-repo disposition
// rows were silently dropped whenever phase3d.status !== 'ran' (suppressed/skipped-empty/
// agent-failed). Merge is now unconditional on CROSS_REPO_DISPOSITIONS being non-empty, and a
// manifest merged without a Phase 3d run is flagged explicitly rather than returning empty.
// ---------------------------------------------------------------------------

test('P1 fix: a crossRepoDispositions row survives when phase3d is suppressed (never ran)', () => {
  const row = { artifact_path: 'other-repo/foo.md', disposition: 'DELETE', reason: 'cross-repo settled', source_nugget_ids: [] };
  const result = runCrossRepoMerge({
    phase3d: { status: 'suppressed', deletions: [] },
    CROSS_REPO_DISPOSITIONS: [row],
  });

  assert.equal(result.deletions.length, 1, 'the cross-repo row must not vanish when phase3d never ran');
  assert.ok(result.deletions.some((d) => d.artifact_path === 'other-repo/foo.md'));
  assert.equal(result.cross_repo_merged_without_manifest, true, 'a merge onto a never-ran manifest must be flagged explicitly');
});

test('P1 fix: a crossRepoDispositions row survives when phase3d agent-failed', () => {
  const row = { artifact_path: 'other-repo/bar.md', disposition: 'BLOCKED', reason: 'cross-repo blocked', source_nugget_ids: [] };
  const result = runCrossRepoMerge({
    phase3d: { status: 'agent-failed', deletions: [] },
    CROSS_REPO_DISPOSITIONS: [row],
  });

  assert.equal(result.deletions.length, 1);
  assert.equal(result.cross_repo_merged_without_manifest, true);
});

test('P1 fix: a normal ran-manifest merge does not set the without-manifest flag', () => {
  const row = { artifact_path: 'other-repo/baz.md', disposition: 'DELETE', reason: 'x', source_nugget_ids: [] };
  const result = runCrossRepoMerge({
    phase3d: { status: 'ran', deletions: [] },
    CROSS_REPO_DISPOSITIONS: [row],
  });

  assert.equal(result.cross_repo_merged_without_manifest, undefined);
});

// ---------------------------------------------------------------------------
// Distill durable-log correctness closeout (2026-09-11,
// docs/plans/2026-09-11-distill-durable-log-correctness-closeout.md, chunk C1).
//
// Fixture-fork ruling: the baton's regression AC
// (state/handoffs/2026-08-06-distill-next-run-quality.md) asked this oracle to replay run
// 2026-08-06-14h38's journal and reproduce 182 DISTILLED / 69 EPHEMERAL / 6 SKIP. That journal
// was never tracked on any ref — `state/scratch/` is .gitignore line 5, and
// `git log --all --diff-filter=A --name-only -- 'state/scratch/artifact-distillation/**'` returns
// zero hits. Recovery is not a fork arm; it is a dead end. This oracle therefore pins the JOIN
// SHAPE and the REPAIRED-VS-NAIVE DELTA instead — the actual content of the incident — against a
// synthetic fixture whose own counts are fixed by construction below. 182/69/6 remain the
// historical measurement of a corpus that no longer exists; they are never asserted here, and a
// future reader who wants to "restore" them is chasing an unjoinable source of their own.
//
// ONE new extraction spans the whole production chain the 2026-08-06 incident actually broke —
// `normalizeNuggetSources`, its call site, and the join-integrity verdict — so the repair call
// site sits INSIDE the evaluated block rather than being driven by hand from two stitched
// fragments.
// ---------------------------------------------------------------------------

const joinIntegritySpanSrc = extractBlockSource(
  SOURCE,
  'function normalizeNuggetSources(results) {',
  "(disposalSuppressed ? ` — DISPOSAL SUPPRESSED: ${disposalSuppressedReason}` : ''))"
);

const joinIntegrityThresholdMatch = SOURCE.match(/const\s+JOIN_INTEGRITY_MAX_UNJOINABLE_RATE\s*=\s*([\d.]+)/);
assert.ok(joinIntegrityThresholdMatch, 'JOIN_INTEGRITY_MAX_UNJOINABLE_RATE declaration not found in workflow.js');
const JOIN_INTEGRITY_THRESHOLD = Number(joinIntegrityThresholdMatch[1]);

function runJoinIntegrity({ BATCHES, scanResults, JOIN_INTEGRITY_MAX_UNJOINABLE_RATE }) {
  const logs = [];
  const fn = new Function(
    'BATCHES', 'scanResults', 'log', 'JOIN_INTEGRITY_MAX_UNJOINABLE_RATE',
    `
    ${joinIntegritySpanSrc}
    return { sourceNormalization, joinIntegrity, disposalSuppressed };
    `
  );
  return fn(BATCHES, scanResults, (msg) => logs.push(msg), JOIN_INTEGRITY_MAX_UNJOINABLE_RATE);
}

function countDispositions(rows) {
  return rows.reduce((acc, r) => {
    acc[r.disposition] = (acc[r.disposition] || 0) + 1;
    return acc;
  }, {});
}

// ---------------------------------------------------------------------------
// Fixture A — verdict tiers, driven end-to-end through the extracted span. Every batch file
// across Fixture A AND Fixture B carries a unique basename (normalizeNuggetSources maps a
// colliding basename to null, workflow.js:531, which would corrupt the rate arithmetic), and no
// unjoinable wsc-receipt id equals any batch file's basename either.
// ---------------------------------------------------------------------------

function fixtureABatches(arm) {
  const files = Array.from({ length: 20 }, (_, i) => `state/fixture-a/${arm}/a-${arm}-f${String(i + 1).padStart(2, '0')}.md`);
  return [{ batchId: `a-${arm}`, files }];
}

function fixtureACleanFactory() {
  const files = fixtureABatches('clean')[0].files;
  const nuggets = [];
  for (let i = 0; i < 14; i++) nuggets.push({ id: `a-clean-${i}`, type: 'KNOWLEDGE', source: files[i], content: 'x' });
  for (let i = 14; i < 20; i++) nuggets.push({ id: `a-clean-${i}`, type: 'KNOWLEDGE', source: files[i].split('/').pop(), content: 'x' });
  return { BATCHES: fixtureABatches('clean'), scanResults: [{ batch_id: 'a-clean', nuggets, file_fates: [] }] };
}

function fixtureAFindingFactory(k) {
  const files = fixtureABatches('finding')[0].files;
  const nuggets = [];
  for (let i = 0; i < 20 - k; i++) nuggets.push({ id: `a-finding-${i}`, type: 'KNOWLEDGE', source: files[i], content: 'x' });
  for (let i = 0; i < k; i++) nuggets.push({ id: `a-finding-u${i}`, type: 'KNOWLEDGE', source: `2026-07-09-wsc-finding-uuid-${i}`, content: 'x' });
  return { BATCHES: fixtureABatches('finding'), scanResults: [{ batch_id: 'a-finding', nuggets, file_fates: [] }] };
}

function fixtureAFailedFactory() {
  const files = fixtureABatches('failed')[0].files;
  const nuggets = [];
  for (let i = 0; i < 16; i++) nuggets.push({ id: `a-failed-${i}`, type: 'KNOWLEDGE', source: files[i], content: 'x' });
  for (let i = 0; i < 4; i++) nuggets.push({ id: `a-failed-u${i}`, type: 'KNOWLEDGE', source: `2026-07-09-wsc-failed-uuid-${i}`, content: 'x' });
  return { BATCHES: fixtureABatches('failed'), scanResults: [{ batch_id: 'a-failed', nuggets, file_fates: [] }] };
}

test('C1 Fixture A clean: 14 exact + 6 basename sources, 0 unjoinable -> verdict clean, repaired_joins 6, disposal not suppressed', () => {
  const { BATCHES, scanResults } = fixtureACleanFactory();
  const result = runJoinIntegrity({ BATCHES, scanResults, JOIN_INTEGRITY_MAX_UNJOINABLE_RATE: JOIN_INTEGRITY_THRESHOLD });

  assert.equal(result.joinIntegrity.verdict, 'clean', 'basename noise repaired by the join must never surface as unjoinable');
  assert.equal(result.sourceNormalization.repaired_joins, 6);
  assert.equal(result.sourceNormalization.unjoinable_sources.length, 0);
  assert.equal(result.disposalSuppressed, false);
});

test('C1 Fixture A finding (boundary): rate exactly at threshold does not suppress disposal', () => {
  const k = Math.round(JOIN_INTEGRITY_THRESHOLD * 20);
  assert.strictEqual(
    k, JOIN_INTEGRITY_THRESHOLD * 20,
    're-tune this fixture if JOIN_INTEGRITY_MAX_UNJOINABLE_RATE moves to a value 20 sources cannot hit exactly'
  );
  const { BATCHES, scanResults } = fixtureAFindingFactory(k);
  const result = runJoinIntegrity({ BATCHES, scanResults, JOIN_INTEGRITY_MAX_UNJOINABLE_RATE: JOIN_INTEGRITY_THRESHOLD });

  assert.equal(result.joinIntegrity.unjoinable_rate, JOIN_INTEGRITY_THRESHOLD);
  assert.equal(result.joinIntegrity.verdict, 'finding', 'a rate exactly at the threshold (<=) must be a finding, not failed');
  assert.equal(result.disposalSuppressed, false, 'a boundary rate must NOT suppress disposal');
});

test('C1 Fixture A failed: 16 exact + 4 unjoinable -> rate 0.20, verdict failed, disposal suppressed', () => {
  const { BATCHES, scanResults } = fixtureAFailedFactory();
  const result = runJoinIntegrity({ BATCHES, scanResults, JOIN_INTEGRITY_MAX_UNJOINABLE_RATE: JOIN_INTEGRITY_THRESHOLD });

  assert.equal(result.joinIntegrity.unjoinable_rate, 0.2);
  assert.equal(result.joinIntegrity.verdict, 'failed');
  assert.equal(result.disposalSuppressed, true);
  assert.equal(result.sourceNormalization.unjoinable_sources.length, 4);
  assert.deepEqual(
    result.sourceNormalization.unjoinable_sources.sort(),
    ['2026-07-09-wsc-failed-uuid-0', '2026-07-09-wsc-failed-uuid-1', '2026-07-09-wsc-failed-uuid-2', '2026-07-09-wsc-failed-uuid-3'],
    'unjoinable_sources must carry exactly the 4 unjoined ids, surfaced not dropped'
  );
});

// ---------------------------------------------------------------------------
// Fixture B — the repaired-vs-naive delta, the shape (not the magnitude) of the 2026-08-06
// incident. BATCHES: b1 = 12 files, b2 = 8 files, b3 = 3 files (23 total). b3 is a failedBatchId
// so its 3 files are SKIP in both arms. `synthResults` and `CONTEXT_TERMS` are stated explicitly:
// synthResults carries one non-SKIP ('INTEGRATE') disposition per nugget-bearing file
// (workflow.js:1625-1633, :1655-1659 — a nugget with no disposition entry resolves undefined and
// files EPHEMERAL, which would shrink BOTH arms' DISTILLED counts and hide the delta).
// CONTEXT_TERMS is deliberately [] so termOk is unconditionally true (workflow.js:1671) and every
// fate line passes on word count alone — this fixture is scoped to the join delta, not
// fate-prose enforcement, which already has its own arm in the 'unavailable' path.
// ---------------------------------------------------------------------------

function fixtureBBatches() {
  const b1 = Array.from({ length: 12 }, (_, i) => `state/fixture-b/b1/b-b1-f${String(i + 1).padStart(2, '0')}.md`);
  const b2 = Array.from({ length: 8 }, (_, i) => `state/fixture-b/b2/b-b2-f${String(i + 1).padStart(2, '0')}.md`);
  const b3 = Array.from({ length: 3 }, (_, i) => `state/fixture-b/b3/b-b3-f${String(i + 1).padStart(2, '0')}.md`);
  return {
    BATCHES: [
      { batchId: 'b1', files: b1 },
      { batchId: 'b2', files: b2 },
      { batchId: 'b3', files: b3 },
    ],
    b1, b2, b3,
  };
}

function fixtureBFateProse(i) {
  return `Fixture B fate line number ${i} describing genuinely reviewed artifact content in real detail.`;
}

// Every arm builds a FRESH fixture — normalizeNuggetSources mutates n.source in place, and a run
// that reused a prior run's already-normalized objects would be a false pass.
function buildFixtureB() {
  const { BATCHES, b1, b2, b3 } = fixtureBBatches();
  const allTouched = [...b1, ...b2]; // 20 scanned files
  const nuggetFiles = allTouched.slice(0, 14); // 14 carry a non-SKIP nugget
  // remaining 6 of allTouched carry only a fate line and no nuggets

  const nuggets1 = [];
  const nuggets2 = [];
  nuggetFiles.forEach((filePath, idx) => {
    const source = idx < 8 ? filePath : filePath.split('/').pop(); // 8 exact-path, 6 bare-basename
    const nugget = { id: `b-nug-${String(idx + 1).padStart(2, '0')}`, type: 'KNOWLEDGE', source, content: 'x' };
    if (b1.includes(filePath)) nuggets1.push(nugget); else nuggets2.push(nugget);
  });

  const fates1 = b1.map((p, idx) => ({ path: p, fate_prose: fixtureBFateProse(idx) }));
  const fates2 = b2.map((p, idx) => ({ path: p, fate_prose: fixtureBFateProse(100 + idx) }));

  const scanResults = [
    { batch_id: 'b1', nuggets: nuggets1, file_fates: fates1 },
    { batch_id: 'b2', nuggets: nuggets2, file_fates: fates2 },
  ];
  const synthResults = [{
    dispositions: nuggetFiles.map((_, idx) => ({ nugget_id: `b-nug-${String(idx + 1).padStart(2, '0')}`, op: 'INTEGRATE' })),
  }];

  return { BATCHES, scanResults, synthResults, failedBatchIds: ['b3'], CONTEXT_TERMS: [] };
}

test('C1 Fixture B repaired arm: join repair run first -> verdict clean, 14 DISTILLED / 6 EPHEMERAL / 3 SKIP', () => {
  const fixture = buildFixtureB();
  const { joinIntegrity } = runJoinIntegrity({
    BATCHES: fixture.BATCHES,
    scanResults: fixture.scanResults,
    JOIN_INTEGRITY_MAX_UNJOINABLE_RATE: JOIN_INTEGRITY_THRESHOLD,
  });
  const rows = runDistillationLogRows(fixture);

  assert.equal(joinIntegrity.verdict, 'clean');
  assert.deepEqual(countDispositions(rows), { DISTILLED: 14, EPHEMERAL: 6, SKIP: 3 });
});

test('C1 Fixture B naive arm: join repair never run -> 8 DISTILLED / 12 EPHEMERAL / 3 SKIP', () => {
  const fixture = buildFixtureB(); // fresh — the repair span never runs against this copy
  const rows = runDistillationLogRows(fixture);

  assert.deepEqual(countDispositions(rows), { DISTILLED: 8, EPHEMERAL: 12, SKIP: 3 });
});

test('C1 Fixture B delta: exactly 6 artifacts flip DISTILLED -> EPHEMERAL when the join repair is absent', () => {
  const repairedFixture = buildFixtureB();
  runJoinIntegrity({
    BATCHES: repairedFixture.BATCHES,
    scanResults: repairedFixture.scanResults,
    JOIN_INTEGRITY_MAX_UNJOINABLE_RATE: JOIN_INTEGRITY_THRESHOLD,
  });
  const repairedRows = runDistillationLogRows(repairedFixture);

  const naiveFixture = buildFixtureB(); // fresh, unrepaired
  const naiveRows = runDistillationLogRows(naiveFixture);

  const naiveByPath = new Map(naiveRows.map((r) => [r.path, r.disposition]));
  let flips = 0;
  for (const row of repairedRows) {
    if (row.disposition === 'DISTILLED' && naiveByPath.get(row.path) === 'EPHEMERAL') flips++;
  }

  assert.equal(flips, 6, 'the naive arm is not decoration — without it a repaired-but-unneeded pass would look identical to a real one');
});

// ---------------------------------------------------------------------------
// wiki-slugs-dropped guard, INPUT_FILE_SCHEMA typing
// ---------------------------------------------------------------------------

test('SLUG_SHARD_SCHEMA types entries as a string-valued map; INPUT_FILE_SCHEMA declares wikiSlugCount', () => {
  const m = SOURCE.match(/const INPUT_FILE_SCHEMA = (\{[\s\S]*?\n\})\n/);
  assert.ok(m, 'INPUT_FILE_SCHEMA not found');
  const schema = new Function(`return ${m[1]}`)();
  const sm = SOURCE.match(/const SLUG_SHARD_SCHEMA = (\{[\s\S]*?\n\})\n/);
  assert.ok(sm, 'SLUG_SHARD_SCHEMA not found');
  const shardSchema = new Function(`return ${sm[1]}`)();
  assert.deepEqual(shardSchema.properties.entries, { type: 'object', additionalProperties: { type: 'string' } });
  assert.equal(schema.properties.wikiSlugCount.type, 'integer');
  for (const [k, v] of Object.entries(schema.properties)) {
    assert.ok(v.type !== 'object' || v.additionalProperties || v.properties, `${k} is an untyped object`);
    assert.ok(v.type !== 'array' || v.items, `${k} is an untyped array`);
  }
});

function runWikiSlugGuard(loadedInput, RAW_ARGS_INPUT) {
  const start = SOURCE.indexOf('const WIKI_SLUGS = ');
  const end = SOURCE.indexOf('// Fate-prose enforcement', start);
  const body = SOURCE.slice(start, end);
  const wikiDirsCandidate = (loadedInput && loadedInput.wikiDirs) || RAW_ARGS_INPUT.wikiDirs;
  return new Function('loadedInput', 'RAW_ARGS_INPUT', 'wikiDirsCandidate', 'loadStats', `${body}\nreturn undefined`)(loadedInput, RAW_ARGS_INPUT, wikiDirsCandidate, () => ({}));
}

test('wiki-slugs-dropped: empty slugs with wikiDirs present halts; count mismatch halts; matching count passes', () => {
  const raw = { inputFile: '/x/in.json' };
  assert.equal(runWikiSlugGuard({ wikiDirs: ['docs/wiki'], wikiSlugs: {} }, raw).halted, 'wiki-slugs-dropped');
  assert.equal(runWikiSlugGuard({ wikiDirs: ['docs/wiki'], wikiSlugCount: 2, wikiSlugs: { a: 'x' } }, raw).halted, 'wiki-slugs-dropped');
  assert.equal(runWikiSlugGuard({ wikiDirs: ['docs/wiki'], wikiSlugCount: 1, wikiSlugs: { a: 'x' } }, raw), undefined);
  assert.equal(runWikiSlugGuard({ wikiSlugs: { a: 'x' } }, raw), undefined);
  assert.equal(runWikiSlugGuard(null, {}), undefined, 'non-inputFile modes are not guarded');
});

test('topic_key joins: underscore-echoed key matches hyphenated cluster key (synth-partial-failure regression)', () => {
  const { sameTopic, buildCandidatesByTopic: b } = new Function(`
    ${slugifyTopicSrc}
    ${sameTopicSrc}
    ${buildCandidatesByTopicSrc}
    return { sameTopic, buildCandidatesByTopic };
  `)();
  assert.ok(sameTopic('retrieval-tuning', 'retrieval_tuning'));
  assert.ok(sameTopic('Retrieval Tuning', 'retrieval-tuning'));
  assert.ok(!sameTopic('retrieval-tuning', 'retrieval-index'));
  const map = b([{ topic_key: 'retrieval_tuning', wiki_path: 'docs/wiki/retrieval-tuning.md', candidate_restatements: [1] }],
    [{ topicKey: 'retrieval-tuning' }], {}, ['docs/wiki'], () => {});
  assert.deepEqual(map.get('retrieval-tuning'), [1]);
  assert.ok(/!synthResults\.some\(\(r\) => sameTopic\(r\.topic_key, topicKey\)\)/.test(SOURCE), 'failedTopicKeys must use sameTopic');
});

// ---------------------------------------------------------------------------
// input-count-mismatch: relayed batch/file counts vs declared counts
// ---------------------------------------------------------------------------

const assertRelayedCounts = new Function(`${extractFunctionSource(SOURCE, 'assertRelayedCounts')}\nreturn assertRelayedCounts;`)();
const TABLE = [{ batchId: 'b1', files: ['a', 'b'] }, { batchId: 'b2', files: ['c'] }];
const ch = (batch_count, total_file_count) => ({ batch_count, total_file_count });
const NONE = {};

test('assertRelayedCounts: matching counts -> null', () => {
  assert.equal(assertRelayedCounts(TABLE, { args: ch(2, 3), file: ch(2, 3) }, true), null);
});

test('assertRelayedCounts: batch shortfall halts', () => {
  const r = assertRelayedCounts(TABLE, { args: NONE, file: ch(3, 3) }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.equal(r.phase_reached, 'load');
  assert.match(r.detail, /batch_count=3/);
});

test('assertRelayedCounts: file shortfall with equal batches halts', () => {
  const r = assertRelayedCounts(TABLE, { args: NONE, file: ch(2, 5) }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /total_file_count=5/);
});

test('assertRelayedCounts: not relayed with counts absent -> null', () => {
  assert.equal(assertRelayedCounts(TABLE, { args: NONE, file: NONE }, false), null);
});

test('assertRelayedCounts: relayed with no channel present halts', () => {
  const r = assertRelayedCounts(TABLE, { args: NONE, file: NONE }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /distill\.workflow_input/);
});

test('assertRelayedCounts: relayed with one count absent from a present channel halts', () => {
  const r = assertRelayedCounts(TABLE, { args: NONE, file: { batch_count: 2 } }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /file channel field total_file_count/);
  const r2 = assertRelayedCounts(TABLE, { args: ch(2, '3'), file: NONE }, true);
  assert.match(r2.detail, /args channel field total_file_count/);
});

test('assertRelayedCounts: file agrees with truncated table while args declares more -> halt naming args', () => {
  const truncated = [TABLE[0]];
  const r = assertRelayedCounts(truncated, { args: ch(2, 3), file: ch(1, 2) }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /^distill-harvest: args /);
});

test('assertRelayedCounts: relayed with only a matching args channel -> null', () => {
  assert.equal(assertRelayedCounts(TABLE, { args: ch(2, 3), file: NONE }, true), null);
});

test('input-count-mismatch: INPUT_FILE_SCHEMA lists both counts under properties, only the shard lists required', () => {
  const m = LIVE_CODE.match(/const INPUT_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'INPUT_FILE_SCHEMA not found');
  const schema = new Function(`return ${m[0].replace('const INPUT_FILE_SCHEMA = ', '')}`)();
  assert.deepEqual(schema.properties.batch_count, { type: 'integer' });
  assert.deepEqual(schema.properties.total_file_count, { type: 'integer' });
  assert.deepEqual(schema.required, ['batchFiles', 'slugShardFiles']);
  const bm = LIVE_CODE.match(/const BATCH_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  const batchSchema = new Function(`return ${bm[0].replace('const BATCH_FILE_SCHEMA = ', '')}`)();
  assert.deepEqual(batchSchema.properties.formatHints, { type: 'object' });
});

test('input-count-mismatch: call site precedes scan dispatch and its non-null result is returned', () => {
  const m = LIVE_CODE.match(/const countHalt = assertRelayedCounts\([\s\S]*?\nif \(countHalt\) \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'assertRelayedCounts call-site guard not found');
  assert.ok(LIVE_CODE.indexOf(m[0]) < LIVE_CODE.indexOf('const scanResults = (await parallel('));
  assert.ok(/return \{ \.\.\.countHalt, load_stats: loadStats\(\) \}/.test(m[0]));
  const run = (RAW_ARGS_INPUT, loadedInput, BATCHES) =>
    new Function('assertRelayedCounts', 'RAW_ARGS_INPUT', 'loadedInput', 'BATCHES', 'loadStats', `${m[0]}\nreturn undefined`)(
      assertRelayedCounts, RAW_ARGS_INPUT, loadedInput, BATCHES, () => ({}));
  assert.equal(run({ batch_count: 5, total_file_count: 9 }, { batches: TABLE }, TABLE).halted, 'input-count-mismatch');
  assert.equal(run({}, null, TABLE), undefined);
  assert.equal(run({ batch_count: 2, total_file_count: 3 }, { batches: TABLE }, TABLE), undefined);
});

test('renderFormatHints: string, non-empty object, empty object', () => {
  const render = new Function(`${extractFunctionSource(SOURCE, 'renderFormatHints')}\nreturn renderFormatHints;`)();
  assert.equal(render('plain'), 'plain');
  assert.equal(render({ k: 'v' }), '{"k":"v"}');
  assert.equal(render({}), 'none');
  assert.equal(render(undefined), 'none');
});

// ---------------------------------------------------------------------------
// Agent-echoed key trust: every synth-type call site stamps the key from the dispatching cluster;
// consolidation never leaves two clusters on one wikiPath.
// ---------------------------------------------------------------------------

const { stampKey } = new Function(`${extractFunctionSource(SOURCE, 'stampKey')}; return { stampKey };`)();

test('stampKey: overwrites an agent-echoed key and passes a null result through', () => {
  assert.deepEqual(
    stampKey({ topic_key: 'subagent-run-report', op: 'x' }, 'topic_key', 'subagent-tooling'),
    { topic_key: 'subagent-tooling', op: 'x' },
  );
  assert.equal(stampKey(null, 'topic_key', 'k'), null);
});

test('workflow source: synth, gap-synth, candidates and judgment call sites stamp the cluster key', () => {
  const code = stripComments(SOURCE);
  assert.equal((code.match(/stampKey\(r, 'topic_key', cluster\.topicKey\)/g) || []).length, 2, 'candidates + synth');
  assert.equal((code.match(/stampKey\(r, 'topic_key', gap\.topicKey\)/g) || []).length, 1, 'gap-synth');
  assert.equal((code.match(/stampKey\(r, 'topic_cluster', cluster\.topicCluster\)/g) || []).length, 1, 'judgment');
});

test('consolidateClusters: clusters homed to one wikiPath merge into one unit, all keys recorded', () => {
  const raw = [
    { topicKey: 'subagent-tooling', nuggets: [{ id: 'n1' }], sourceBatches: ['b1'] },
    { topicKey: 'other', nuggets: [{ id: 'n2' }], sourceBatches: ['b1'] },
    { topicKey: 'subagent-run-report', nuggets: [{ id: 'n3' }, { id: 'n4' }], sourceBatches: ['b2'] },
  ];
  const wikiSlugs = {
    'subagent-tooling': 'docs/wiki/subagent-run-report.md',
    'subagent-run-report': 'docs/wiki/subagent-run-report.md',
    other: 'docs/wiki/other.md',
  };
  const result = consolidateClusters(raw, wikiSlugs, { runId: 'r', wikiDirs: ['docs/wiki'] });
  const paths = result.map((c) => c.wikiPath);
  assert.equal(new Set(paths).size, paths.length, 'no two units share a path');
  const unit = result.find((c) => c.wikiPath === 'docs/wiki/subagent-run-report.md');
  assert.equal(unit.topicKey, 'subagent-tooling');
  assert.deepEqual(unit.mergedTopicKeys, ['subagent-tooling', 'subagent-run-report']);
  assert.deepEqual(unit.nuggets.map((n) => n.id), ['n1', 'n3', 'n4']);
  assert.deepEqual(unit.sourceBatches, ['b1', 'b2']);
});

// ---------------------------------------------------------------------------
// Cluster-list relayed counts and reader-versus-schema parity
// ---------------------------------------------------------------------------

const assertRelayedListCounts = new Function(`${extractFunctionSource(SOURCE, 'assertRelayedListCounts')}\nreturn assertRelayedListCounts;`)();
const THREE = [{ clusterTag: 'a' }, { clusterTag: 'b' }, { clusterTag: 'c' }];

test('assertRelayedListCounts: matching counts -> null', () => {
  assert.equal(assertRelayedListCounts(
    { judgmentClusters: THREE }, { args: {}, file: { judgmentClusters: 3 } }, true), null);
});

test('assertRelayedListCounts: truncated list against the args count halts naming args', () => {
  const r = assertRelayedListCounts(
    { contradictionClusters: THREE.slice(0, 2) },
    { args: { contradictionClusters: 3 }, file: { contradictionClusters: 2 } }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.equal(r.phase_reached, 'load');
  assert.match(r.detail, /args declares contradictionClusters count=3 but received 2/);
});

test('assertRelayedListCounts: list dropped entirely while args declares 3 halts', () => {
  const r = assertRelayedListCounts(
    { crossRepoDispositions: undefined }, { args: { crossRepoDispositions: 3 }, file: {} }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /received 0/);
});

test('assertRelayedListCounts: non-integer declared count halts', () => {
  const r = assertRelayedListCounts(
    { judgmentClusters: THREE }, { args: {}, file: { judgmentClusters: '3' } }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /not an integer/);
});

test('assertRelayedListCounts: relayed non-empty list with no count anywhere halts', () => {
  const r = assertRelayedListCounts({ judgmentClusters: THREE }, { args: {}, file: {} }, true);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /no count/);
});

test('assertRelayedListCounts: absent list with no count, and unrelayed with no counts -> null', () => {
  assert.equal(assertRelayedListCounts({ judgmentClusters: undefined }, { args: {}, file: {} }, true), null);
  assert.equal(assertRelayedListCounts({ judgmentClusters: THREE }, { args: {}, file: {} }, false), null);
});

test('assertRelayedListCounts: call site follows the batch-count guard and precedes scan dispatch', () => {
  const call = LIVE_CODE.indexOf('const listCountHalt = assertRelayedListCounts(');
  assert.ok(call > LIVE_CODE.indexOf('const countHalt = assertRelayedCounts('));
  assert.ok(call < LIVE_CODE.indexOf('const scanResults = (await parallel('));
  assert.ok(/return \{ \.\.\.listCountHalt, load_stats: loadStats\(\) \}/.test(LIVE_CODE));
});

// Built by mergeShardedInput from the batch files and slug shards, not read from the manifest.
const MERGED_INPUT_KEYS = new Set(['batches', 'wikiSlugs']);

function loadedInputReadsOutsideSchema(code, schemaKeys) {
  const names = new Set([...code.matchAll(/\bloadedInput\.([A-Za-z_]\w*)/g)].map((m) => m[1]));
  return [...names].filter((n) => !schemaKeys.has(n) && !MERGED_INPUT_KEYS.has(n));
}

function inputSchemaKeys() {
  const m = LIVE_CODE.match(/const INPUT_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'INPUT_FILE_SCHEMA not found');
  const schema = new Function(`return ${m[0].replace('const INPUT_FILE_SCHEMA = ', '')}`)();
  return new Set(Object.keys(schema.properties));
}

test('parity: every loadedInput.<name> the script reads is an INPUT_FILE_SCHEMA property', () => {
  assert.deepEqual(loadedInputReadsOutsideSchema(LIVE_CODE, inputSchemaKeys()), []);
});

test('parity: a read of a field outside the schema is detected', () => {
  const synthetic = 'const X = loadedInput.runId; const Y = loadedInput.notInSchema';
  assert.deepEqual(loadedInputReadsOutsideSchema(synthetic, inputSchemaKeys()), ['notInSchema']);
});

test('INPUT_FILE_SCHEMA admits the seven cluster keys with pinned types and requires the shard lists', () => {
  const m = LIVE_CODE.match(/const INPUT_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  const schema = new Function(`return ${m[0].replace('const INPUT_FILE_SCHEMA = ', '')}`)();
  for (const k of ['judgmentClusters', 'contradictionClusters', 'crossRepoDispositions']) {
    assert.equal(schema.properties[k].type, 'array', k);
  }
  for (const k of ['judgmentClusterCount', 'contradictionClusterCount', 'crossRepoDispositionCount', 'minConvergence']) {
    assert.deepEqual(schema.properties[k], { type: 'integer' }, k);
  }
  assert.deepEqual(schema.required, ['batchFiles', 'slugShardFiles']);
});

// ---------------------------------------------------------------------------
// Curated file channel (args.curatedFile) and the op's native verdict list
// ---------------------------------------------------------------------------

const liveCuratedMapFromVerdicts = new Function(`${extractFunctionSource(SOURCE, 'curatedMapFromVerdicts')}\nreturn curatedMapFromVerdicts;`)();
const OP_RESULT = VERDICT_PAYLOAD.by_threshold['1'].curate_clusters_result;

test('curatedMapFromVerdicts: one key per fixture verdict, and clusterNuggets accepts the map', () => {
  const map = liveCuratedMapFromVerdicts(OP_RESULT.verdicts);
  assert.equal(Object.keys(map).length, OP_RESULT.verdicts.length);
  assert.equal(Object.keys(map).length, OP_RESULT.counts.total);
  const results = [makeResult('b1', OP_RESULT.verdicts.map((v, i) => makeNugget(`n${i}`, v.tag)))];
  const drops = [];
  assert.doesNotThrow(() => clusterNuggets(results, map, drops));
  assert.equal(drops.length, OP_RESULT.counts.drop);
});

test('curatedMapFromVerdicts: duplicate tag throws naming the tag; missing tag throws', () => {
  assert.throws(
    () => liveCuratedMapFromVerdicts([{ tag: 'dup', verdict: 'keep' }, { tag: 'dup', verdict: 'drop' }]),
    /duplicate verdict for tag 'dup'/);
  assert.throws(() => liveCuratedMapFromVerdicts([{ verdict: 'keep' }]), /without a tag/);
});

function curatedAmbiguityGuard(raw) {
  const m = LIVE_CODE.match(/if \(RAW_ARGS_INPUT && RAW_ARGS_INPUT\.curatedFile && [\s\S]*?\n\}\n/);
  assert.ok(m, 'curated-input-ambiguous guard not found');
  return new Function('RAW_ARGS_INPUT', 'loadStats', `${m[0]}\nreturn undefined`)(raw, () => ({}));
}

test('curated-input-ambiguous: both curatedFile and curatedTags halt; either alone passes', () => {
  const r = curatedAmbiguityGuard({ curatedFile: '/x.json', curatedTags: {} });
  assert.equal(r.halted, 'curated-input-ambiguous');
  assert.equal(r.phase_reached, 'load');
  assert.equal(curatedAmbiguityGuard({ curatedFile: '/x.json' }), undefined);
  assert.equal(curatedAmbiguityGuard({ curatedTags: [] }), undefined);
  assert.ok(LIVE_CODE.indexOf("curatedFile && RAW_ARGS_INPUT.curatedTags") < LIVE_CODE.indexOf('agent(loadBrief'));
});

test('curated verdict count: a truncated verdict list against counts.total halts', () => {
  const full = OP_RESULT.verdicts;
  const check = (verdicts, args) => assertRelayedListCounts(
    { verdicts }, { args: { verdicts: args }, file: { verdicts: OP_RESULT.counts.total } }, true);
  assert.equal(check(full, OP_RESULT.counts.total), null);
  const r = check(full.slice(0, full.length - 1), undefined);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.match(r.detail, /file declares verdicts count=249 but received 248/);
  assert.equal(check(full, full.length - 1).halted, 'input-count-mismatch');
});

function loadedCuratedReadsOutsideSchema(code, schemaKeys) {
  const names = new Set([...code.matchAll(/\bloadedCurated\.([A-Za-z_]\w*)/g)].map((m) => m[1]));
  return [...names].filter((n) => !schemaKeys.has(n));
}

function curatedSchema() {
  const m = LIVE_CODE.match(/const CURATED_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'CURATED_FILE_SCHEMA not found');
  return new Function(`return ${m[0].replace('const CURATED_FILE_SCHEMA = ', '')}`)();
}

test('parity: every loadedCurated.<name> the script reads is a CURATED_FILE_SCHEMA property', () => {
  const schema = curatedSchema();
  assert.deepEqual(schema.required, ['verdicts']);
  assert.deepEqual(schema.properties.verdicts.items.required, ['tag', 'verdict']);
  assert.deepEqual(loadedCuratedReadsOutsideSchema(LIVE_CODE, new Set(Object.keys(schema.properties))), []);
  assert.deepEqual(
    loadedCuratedReadsOutsideSchema('const X = loadedCurated.verdicts; const Y = loadedCurated.notInSchema',
      new Set(Object.keys(schema.properties))),
    ['notInSchema']);
});

test('curated load: agent call sits after the scan wave and before the A/B branch, phase load, own path', () => {
  const call = LIVE_CODE.indexOf('schema: CURATED_FILE_SCHEMA');
  assert.ok(call > LIVE_CODE.indexOf('const scanResults = (await parallel('));
  assert.ok(call < LIVE_CODE.indexOf('if (!CURATED_TAGS)'));
  const opts = LIVE_CODE.slice(call, LIVE_CODE.indexOf('})', call));
  assert.match(opts, /phase: 'load'/);
  assert.match(opts, /label: 'curated-file'/);
  assert.match(LIVE_CODE, /Read the file at exactly this path: \$\{curatedFilePath\}/);
  assert.ok(!/curatedLoadBrief[\s\S]{0,1500}inputFilePath/.test(LIVE_CODE.slice(LIVE_CODE.indexOf('const curatedLoadBrief'), LIVE_CODE.indexOf('schema: CURATED_FILE_SCHEMA'))));
});

test('contradiction topicKeys: an entry matching no cluster is reported and never reaches an agent', () => {
  const m = LIVE_CODE.match(/const SUPPLIED_CONTRADICTION_CLUSTERS = [\s\S]*?\n\}\)\n/);
  assert.ok(m, 'contradiction-cluster resolution block not found');
  const run = (loadedCurated, loadedInput, RAW_ARGS_INPUT, clusters, HOMED_CURATED_TAGS) => new Function(
    'loadedCurated', 'loadedInput', 'RAW_ARGS_INPUT', 'clusters', 'HOMED_CURATED_TAGS',
    `${slugifyTopicSrc}\n${sameTopicSrc}\n${m[0]}\nreturn { CONTRADICTION_CLUSTERS, unmatchedTopicKeys }`)(
    loadedCurated, loadedInput, RAW_ARGS_INPUT, clusters, HOMED_CURATED_TAGS);
  const clusters = [{ topicKey: 'alpha-topic', mergedTopicKeys: ['alpha-topic', 'beta-topic'] }];
  const out = run({ contradictionClusters: [{ clusterTag: 't', topicKeys: ['Alpha Topic', 'beta-topic', 'ghost'] }] },
    { contradictionClusters: [{ clusterTag: 'ignored', topicKeys: ['x'] }] }, {}, clusters);
  assert.deepEqual(out.CONTRADICTION_CLUSTERS, [{ clusterTag: 't', topicKeys: ['Alpha Topic', 'beta-topic'] }]);
  assert.deepEqual(out.unmatchedTopicKeys, ['ghost']);
  const fromInput = run(null, { contradictionClusters: [{ clusterTag: 'i', topicKeys: ['alpha-topic'] }] }, {}, clusters);
  assert.equal(fromInput.CONTRADICTION_CLUSTERS[0].clusterTag, 'i');
  assert.ok(LIVE_CODE.indexOf('const SUPPLIED_CONTRADICTION_CLUSTERS') > LIVE_CODE.indexOf('if (!CURATED_TAGS)'));
  assert.match(LIVE_CODE, /unmatched_topic_keys: unmatchedTopicKeys/);
  const curated = {
    client_retry: { verdict: 'merge', merge_target: 'ingest-queue' },
    lost_tag: { verdict: 'merge', merge_target: 'no-such-cluster' },
  };
  const mergedAway = run({ contradictionClusters: [{ clusterTag: 'm', topicKeys: ['ingest-queue', 'client-retry', 'lost-tag'] }] },
    null, {}, [{ topicKey: 'ingest-queue' }], curated);
  assert.deepEqual(mergedAway.CONTRADICTION_CLUSTERS, [{ clusterTag: 'm', topicKeys: ['ingest-queue'] }]);
  assert.deepEqual(mergedAway.unmatchedTopicKeys, ['lost-tag']);
});

// ---------------------------------------------------------------------------
// DR minting: drMintingSectionFor, findFoldedDecisions, merge-back, gap brief
// ---------------------------------------------------------------------------

const drMintSrc = [
  extractFunctionSource(SOURCE, 'drMintingSectionFor'),
  extractFunctionSource(SOURCE, 'findFoldedDecisions'),
  extractFunctionSource(SOURCE, 'combineResynthWork'),
  extractFunctionSource(SOURCE, 'mergeGapDispositions'),
  extractFunctionSource(SOURCE, 'gapSynthBriefFor'),
].join('\n');
const drMint = new Function('candidatesByTopic', `
  const RUN_ID = 'run-xyz';
  const COMMON = '';
  ${slugifyTopicSrc}
  ${drMintSrc}
  return { drMintingSectionFor, findFoldedDecisions, combineResynthWork, mergeGapDispositions, gapSynthBriefFor };
`)(new Map());

const dec = (id) => ({ id, type: 'DECISION', content: `decision ${id}` });
const know = (id) => ({ id, type: 'KNOWLEDGE', content: `knowledge ${id}` });

test('drMintingSectionFor: empty for a KNOWLEDGE-only cluster', () => {
  assert.equal(drMint.drMintingSectionFor({ nuggets: [know('k1')] }), '');
});

test('drMintingSectionFor: names both DECISION ids, the scaffolder, the allocator-unavailable reason, the run stamp', () => {
  const out = drMint.drMintingSectionFor({ nuggets: [dec('d1'), know('k1'), dec('d2')] });
  assert.match(out, /d1, d2/);
  assert.doesNotMatch(out, /k1/);
  assert.match(out, /coordinator-doc-new --type decision/);
  assert.match(out, /DR-ALLOCATOR-UNAVAILABLE/);
  assert.match(out, /DR-EXISTS /);
  assert.match(out, /run_id: run-xyz/);
});

test('drMintingSectionFor: carries every ## heading of phase-2.md Decision Records template', () => {
  const prompt = fs.readFileSync(path.join(__dirname, '..', 'agent-prompts', 'phase-2.md'), 'utf8');
  const start = prompt.indexOf('## Decision Records');
  const end = prompt.indexOf('## Handling Ambiguous Items');
  assert.ok(start >= 0 && end > start);
  const headings = prompt.slice(start + '## Decision Records'.length, end).split('\n').map((l) => l.trimEnd()).filter((l) => l.startsWith('## '));
  assert.ok(headings.length >= 4, `expected the 4 template headings, got ${headings.length}`);
  const out = drMint.drMintingSectionFor({ nuggets: [dec('d1')] });
  for (const h of headings) assert.ok(out.includes(h), `section lacks "${h}"`);
});

test('synthBriefFor and gapSynthBriefFor interpolate drMintingSectionFor; SYNTH_SCHEMA carries target', () => {
  assert.match(LIVE_CODE, /\$\{drMintingSectionFor\(cluster\)\}/);
  assert.match(LIVE_CODE, /\$\{drMintingSectionFor\(\{ nuggets: gapNuggets \}\)\}/);
  assert.match(LIVE_CODE, /target: \{ type: 'string' \}/);
  assert.match(SOURCE, /agent-prompts\/phase-2\.md § Decision Records/);
});

test('findFoldedDecisions: flags folded DECISION nuggets, passes records and the two pinned skips', () => {
  const clusters = [{ topicKey: 'topic-a', nuggets: [dec('a'), dec('b'), dec('c'), dec('d'), dec('e'), dec('f'), dec('g')] }];
  const results = [{ topic_key: 'topic-a', wiki_path: 'docs/wiki/topic-a.md', dispositions: [
    { nugget_id: 'a', op: 'ADD_SECTION' },
    { nugget_id: 'b', op: 'CREATE_DR' },
    { nugget_id: 'c', op: 'CREATE_DR', target: 'docs/wiki/elsewhere.md' },
    { nugget_id: 'd', op: 'CREATE_DR', target: 'docs/decisions/DR-001-x.md' },
    { nugget_id: 'e', op: 'SKIP', reason: 'DR-ALLOCATOR-UNAVAILABLE: no launcher' },
    { nugget_id: 'f', op: 'SKIP', reason: 'DR-EXISTS docs/decisions/DR-002-y.md' },
    { nugget_id: 'g', op: 'SKIP', reason: 'EPHEMERAL at source' },
  ] }];
  const out = drMint.findFoldedDecisions(clusters, results);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].foldedNuggets.map((n) => n.id), ['a', 'b', 'c', 'g']);
  assert.equal(out[0].wikiPath, 'docs/wiki/topic-a.md');
});

test('findFoldedDecisions: ignores non-DECISION nuggets and nuggets with no disposition', () => {
  const clusters = [{ topicKey: 'topic-a', nuggets: [know('k'), dec('x')] }];
  const results = [{ topic_key: 'topic-a', wiki_path: 'w.md', dispositions: [{ nugget_id: 'k', op: 'ADD_SECTION' }] }];
  assert.deepEqual(drMint.findFoldedDecisions(clusters, results), []);
});

test('gap brief: a folded nugget carries the look-first instruction, an uncovered-only gap does not', () => {
  const folded = drMint.gapSynthBriefFor({ topicKey: 't', wikiPath: 'w.md', uncoveredNuggets: [], foldedNuggets: [dec('d1')] });
  assert.match(folded, /look\s+under docs\/decisions\/ for a record whose frontmatter `provenance` carries run_id run-xyz/);
  assert.match(folded, /coordinator-doc-new --type decision/);
  const plain = drMint.gapSynthBriefFor({ topicKey: 't', wikiPath: 'w.md', uncoveredNuggets: [know('k1')] });
  assert.doesNotMatch(plain, /look\s+under docs\/decisions/);
  assert.doesNotMatch(plain, /coordinator-doc-new/);
});

test('merge-back: a gap disposition replaces a folded one and only fills uncovered ids otherwise', () => {
  const original = [{ nugget_id: 'a', op: 'ADD_SECTION' }, { nugget_id: 'b', op: 'ADD_SECTION' }];
  const gap = [
    { nugget_id: 'a', op: 'CREATE_DR', target: 'docs/decisions/DR-001-x.md' },
    { nugget_id: 'b', op: 'SKIP', reason: 'should not replace' },
    { nugget_id: 'c', op: 'ADD_SECTION' },
  ];
  const out = drMint.mergeGapDispositions(original, gap, ['a']);
  assert.deepEqual(out.map((d) => [d.nugget_id, d.op]), [['a', 'CREATE_DR'], ['b', 'ADD_SECTION'], ['c', 'ADD_SECTION']]);
});

test('coverage gate: re-synth runs when folded work exists even with no coverage gaps', () => {
  assert.match(LIVE_CODE, /if \(resynthWork\.length > 0\) \{/);
  const work = drMint.combineResynthWork([], [{ topicKey: 't', wikiPath: 'w.md', foldedNuggets: [dec('d')] }]);
  assert.equal(work.length, 1);
  assert.deepEqual(work[0].uncoveredNuggets, []);
});

// C4 — dr_minting reconciliation and the phase-3b skip branch.
const reconcileDrTargets = new Function(`${extractFunctionSource(SOURCE, 'reconcileDrTargets')}; return reconcileDrTargets;`)();

test('reconcileDrTargets: all found, one missing, backslash form', () => {
  assert.deepEqual(reconcileDrTargets(['docs/decisions/DR-1-a.md'], ['docs/decisions/DR-1-a.md']), []);
  assert.deepEqual(reconcileDrTargets(['docs/decisions/DR-1-a.md', 'docs/decisions/DR-2-b.md'], ['docs/decisions/DR-1-a.md']), ['docs/decisions/DR-2-b.md']);
  assert.deepEqual(reconcileDrTargets(['docs/decisions/DR-1-a.md'], ['docs\\decisions\\DR-1-a.md']), []);
  assert.deepEqual(reconcileDrTargets(['docs/decisions/DR-1-a.md'], undefined), ['docs/decisions/DR-1-a.md']);
});

const skipBranchSrc = extractBlockSource(
  SOURCE,
  'const decisionNuggets = clusters.flatMap',
  '// END phase-3b skip branch'
);

function runSkipBranch(clusters, dispositions, createDr = [], judgment = []) {
  const fn = new Function('clusters', 'synthResults', 'createDrDispositions', 'judgmentDrCandidates', `
    ${skipBranchSrc}
    }
    return phase3b;
  `);
  return fn(clusters, [{ topic_key: 't', dispositions }], createDr, judgment);
}

test('phase-3b skip branch: no DECISION nuggets is not a failure', () => {
  const out = runSkipBranch([{ nuggets: [know('k1')] }], [{ nugget_id: 'k1', op: 'ADD_SECTION' }]);
  assert.equal(out.failure, false);
  assert.equal(out.status, 'skipped-empty');
  assert.match(out.failure_detail, /no decision-shaped content/);
});

test('phase-3b skip branch: a folded DECISION nugget keeps failure and names the count', () => {
  const out = runSkipBranch([{ nuggets: [dec('d1'), dec('d2')] }], [
    { nugget_id: 'd1', op: 'ADD_SECTION' },
    { nugget_id: 'd2', op: 'SKIP', reason: 'DR-EXISTS docs/decisions/DR-9-x.md' },
  ]);
  assert.equal(out.failure, true);
  assert.match(out.failure_detail, /1 of 2 DECISION/);
});

test('phase-3b skip branch: an allocator-skipped DECISION nugget keeps failure', () => {
  const out = runSkipBranch([{ nuggets: [dec('d1')] }], [
    { nugget_id: 'd1', op: 'SKIP', reason: 'DR-ALLOCATOR-UNAVAILABLE: no CLI' },
  ]);
  assert.equal(out.failure, true);
  assert.match(out.failure_detail, /1 of 1 DECISION/);
});

test('phase-3b skip branch: all DR-EXISTS skips is not a failure and names the records', () => {
  const out = runSkipBranch([{ nuggets: [dec('d1')] }], [
    { nugget_id: 'd1', op: 'SKIP', reason: 'DR-EXISTS docs/decisions/DR-9-x.md' },
  ]);
  assert.equal(out.failure, false);
  assert.match(out.failure_detail, /docs\/decisions\/DR-9-x\.md/);
});

test('dr_minting: returned, and a found record no disposition names lands in unclaimed_files', () => {
  assert.match(LIVE_CODE, /dr_minting: drMinting,/);
  assert.match(LIVE_CODE, /unclaimed_files: drAgentFailed \? \[\]/);
  const drMintingSrc = extractBlockSource(SOURCE, 'const drTargets = createDrDispositions', 'unclaimed_files: drAgentFailed ? [] : (phase3b.dr_files_found || []).map(normDrPath).filter((p) => !drTargetsNorm.has(p)),\n}');
  const run = (phase3b) => new Function('createDrDispositions', 'phase3b', 'decisionNuggets', 'allDispositions', 'allocatorUnavailableCount', 'foldedUnresolved', 'reconcileDrTargets', `${drMintingSrc}; return drMinting;`)(
    [{ target: 'docs/decisions/DR-1-a.md' }], phase3b, [{ id: 'd1' }], [], 0, [], reconcileDrTargets);
  const ok = run({ status: 'ran', dr_files_found: ['docs/decisions/DR-1-a.md', 'docs\\decisions\\DR-2-b.md'] });
  assert.deepEqual(ok.unclaimed_files, ['docs/decisions/DR-2-b.md']);
  assert.deepEqual(ok.missing_files, []);
  const failed = run({ status: 'agent-failed' });
  assert.deepEqual(failed.missing_files, ['docs/decisions/DR-1-a.md']);
  assert.deepEqual(failed.unclaimed_files, []);
  assert.match(SOURCE, /required: \['dr_dedup', 'dr_files_found', 'failure'\]/);
});

// ---------------------------------------------------------------------------
// 2.5: judgment-corpus scout — cluster resolution and gating.
// ---------------------------------------------------------------------------

const resolveJudgmentClusters = new Function(
  `${extractFunctionSource(SOURCE, 'resolveJudgmentClusters')}; return resolveJudgmentClusters;`
)();
const INPUT_CLUSTER = { topicCluster: 'a', verdictDirection: 'forbid', liveSidecarPaths: ['x.md'] };

test('2.5 scout: input clusters win over the scout result', () => {
  const r = resolveJudgmentClusters([INPUT_CLUSTER], { sidecars_seen: 9, clusters: [{ topicCluster: 'b' }] });
  assert.equal(r.cluster_source, 'input');
  assert.deepEqual(r.clusters, [INPUT_CLUSTER]);
  assert.equal(r.status, 'ran');
});

test('2.5 scout: scout clusters are used when input is empty', () => {
  const r = resolveJudgmentClusters([], { sidecars_seen: 4, clusters: [INPUT_CLUSTER] });
  assert.equal(r.cluster_source, 'in-run-scout');
  assert.equal(r.sidecars_seen, 4);
  assert.equal(r.clusters.length, 1);
  assert.equal(r.status, 'ran');
});

test('2.5 scout: zero scout clusters is status ran with sidecars_seen recorded', () => {
  const r = resolveJudgmentClusters([], { sidecars_seen: 12, clusters: [] });
  assert.equal(r.status, 'ran');
  assert.equal(r.cluster_source, 'in-run-scout');
  assert.equal(r.sidecars_seen, 12);
  assert.deepEqual(r.clusters, []);
});

test('2.5 scout: a failed scout with no input is unavailable', () => {
  for (const scout of [null, undefined, {}]) {
    const r = resolveJudgmentClusters([], scout);
    assert.equal(r.status, 'unavailable');
    assert.equal(r.cluster_source, 'none');
  }
});

test("2.5 scout: the 'judgment-corpus' agent call sits behind a branch on empty input clusters", () => {
  const src = stripComments(SOURCE);
  const matches = [...src.matchAll(/label:\s*'judgment-corpus'/g)];
  assert.equal(matches.length, 1);
  const before = src.slice(0, matches[0].index);
  const branch = before.lastIndexOf('if (!(Array.isArray(JUDGMENT_CLUSTERS)');
  assert.notEqual(branch, -1);
  assert.ok(before.slice(branch).split('agent(').length === 2, 'the scout is the first agent( after the branch');
});

// ---------------------------------------------------------------------------
// citation-repoint
// ---------------------------------------------------------------------------

const { isRepointableCitation, selectRepointCandidates, applyRepointResults } = new Function(
  ['isRepointableCitation', 'selectRepointCandidates', 'applyRepointResults']
    .map((n) => extractFunctionSource(SOURCE, n)).join('\n') +
  '; return { isRepointableCitation, selectRepointCandidates, applyRepointResults };'
)();

const RP_PATH = 'archive/specs/a.md';
const RP_WIKI = new Map([[RP_PATH, ['docs/wiki/x.md']]]);
const rpProbe = (over = {}) => [{
  artifact_path: RP_PATH, eligible: false, blocked_by: ['active-reference'], citing_paths: ['docs/guide.md'], ...over,
}];
const rpRow = (disposition) => [{ artifact_path: RP_PATH, disposition, reason: 'r' }];

test('citation-repoint: guard-blocked-by-docs-citation case is selected and resolves to DELETE when the guard clears', () => {
  for (const disp of ['BLOCKED', 'DELETE']) {
    const rows = rpRow(disp);
    const cands = selectRepointCandidates(rows, rpProbe(), RP_WIKI);
    assert.deepEqual(cands, [{ artifact_path: RP_PATH, citing_paths: ['docs/guide.md'], wiki_paths: ['docs/wiki/x.md'] }]);
    const out = applyRepointResults(rows, cands, [
      { artifact_path: RP_PATH, repointed_files: ['docs/guide.md'], eligible: true, blocked_by: [] },
    ]);
    assert.equal(out.deletions[0].disposition, 'DELETE');
    assert.match(out.deletions[0].reason, /docs\/guide\.md/);
    assert.match(out.deletions[0].reason, /docs\/wiki\/x\.md/);
    assert.deepEqual(out.repointed, [RP_PATH]);
  }
});

test('citation-repoint: rows are not selected when a citing path is unrepointable, another guard blocks, or no wiki absorbed', () => {
  for (const bad of ['state/handoffs/h.md', 'archive/specs/a.md', 'docs/plans/p.md']) {
    assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe({ citing_paths: ['docs/guide.md', bad] }), RP_WIKI), []);
  }
  assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe({ blocked_by: ['active-reference', 'open-commitment'] }), RP_WIKI), []);
  assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe({ blocked_by: ['open-commitment'] }), RP_WIKI), []);
  assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe({ citing_paths: [] }), RP_WIKI), []);
  assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe({ eligible: undefined }), RP_WIKI), []);
  assert.deepEqual(selectRepointCandidates(rpRow('BLOCKED'), rpProbe(), new Map()), []);
});

test('citation-repoint: a still-blocked or malformed post-repoint result keeps the disposition and names the guards', () => {
  const cands = selectRepointCandidates(rpRow('BLOCKED'), rpProbe(), RP_WIKI);
  const still = applyRepointResults(rpRow('BLOCKED'), cands, [
    { artifact_path: RP_PATH, repointed_files: ['docs/guide.md'], eligible: false, blocked_by: ['active-reference'] },
  ]);
  assert.equal(still.deletions[0].disposition, 'BLOCKED');
  assert.deepEqual(still.still_blocked, [{ artifact_path: RP_PATH, blocked_by: ['active-reference'] }]);
  const missing = applyRepointResults(rpRow('DELETE'), cands, [{ artifact_path: RP_PATH, repointed_files: ['docs/guide.md'] }]);
  assert.equal(missing.deletions[0].disposition, 'DELETE');
  assert.equal(missing.deletions[0].reason, 'r');
  assert.equal(missing.still_blocked.length, 1);
  assert.equal(applyRepointResults(rpRow('BLOCKED'), cands, []).deletions[0].disposition, 'BLOCKED');
});

test('citation-repoint: isRepointableCitation', () => {
  for (const p of ['docs/wiki/x.md', 'docs\\guide.md', 'tasks/t/spec.md']) assert.equal(isRepointableCitation(p), true, p);
  for (const p of ['docs/plans/p.md', 'state/handoffs/h.md', 'archive/specs/a.md', 'src/x.js']) assert.equal(isRepointableCitation(p), false, p);
});

test("citation-repoint: phase sits after the cross-repo merge and before artifact-reentry", () => {
  const merge = SOURCE.indexOf("no cross-repo disposition rows supplied");
  const cr = SOURCE.indexOf("phase('citation-repoint')");
  const re = SOURCE.indexOf("phase('artifact-reentry')");
  assert.ok(merge !== -1 && merge < cr && cr < re);
});

// ---------------------------------------------------------------------------
// Sharded load: shardPathFor, mergeShardedInput, load_stats, load-block shape
// ---------------------------------------------------------------------------

const shardedLoad = new Function(
  `${['shardPathFor', 'mergeShardedInput', 'buildLoadStats']
    .map((n) => extractFunctionSource(SOURCE, n)).join('\n')}\n` +
  'return { shardPathFor, mergeShardedInput, buildLoadStats };')();

const SHARDED_DIR = path.join(__dirname, 'fixtures', 'sharded-input');
const readShard = (name) => JSON.parse(fs.readFileSync(path.join(SHARDED_DIR, name), 'utf8'));
const shardedFixture = () => {
  const manifest = readShard('workflow-input.json');
  return {
    manifest,
    batchResults: manifest.batchFiles.map(readShard),
    shardResults: manifest.slugShardFiles.map(readShard),
    files: { batchFiles: manifest.batchFiles, slugShardFiles: manifest.slugShardFiles },
  };
};

test('shardPathFor: Windows drive path, POSIX path, and a bare filename', () => {
  const { shardPathFor: f } = shardedLoad;
  const win = (...p) => ['C:', ...p].join('\\');
  const mixed = (...p) => ['C:', ...p].join('/');
  const posix = (...p) => ['', 'var', ...p].join('/');
  assert.equal(f(win('scratch', 'run-1', 'workflow-input.json'), 'batch-0001.json'), win('scratch', 'run-1', 'batch-0001.json'));
  assert.equal(f(mixed('scratch', 'run-1', 'workflow-input.json'), 'batch-0001.json'), mixed('scratch', 'run-1', 'batch-0001.json'));
  assert.equal(f(posix('scratch', 'run-1', 'workflow-input.json'), 'sub/wikislugs-0002.json'), posix('scratch', 'run-1', 'sub', 'wikislugs-0002.json'));
  assert.equal(f(win('scratch', 'workflow-input.json'), 'sub/x.json'), win('scratch', 'sub', 'x.json'));
  assert.equal(f('workflow-input.json', 'batch-0001.json'), 'batch-0001.json');
});

test('sharded fixture: no drive letter, merges to the declared counts', () => {
  for (const name of fs.readdirSync(SHARDED_DIR)) {
    assert.doesNotMatch(fs.readFileSync(path.join(SHARDED_DIR, name), 'utf8'), /[A-Za-z]:[\\/]/, name);
  }
  const { manifest, batchResults, shardResults, files } = shardedFixture();
  const r = shardedLoad.mergeShardedInput(manifest, batchResults, shardResults, files);
  assert.ok(r.loadedInput, JSON.stringify(r));
  const li = r.loadedInput;
  assert.equal(li.batches.length, manifest.batch_count);
  assert.equal(li.batches.reduce((n, b) => n + b.files.length, 0), manifest.total_file_count);
  assert.equal(Object.keys(li.wikiSlugs).length, manifest.wikiSlugCount);
  assert.equal(li.batchFiles, undefined);
  assert.equal(li.slugShardFiles, undefined);
  assert.equal(li.batches[0].file_count, undefined);
  assert.equal(li.runId, manifest.runId);
  assert.equal(assertRelayedCounts(li.batches, { args: {}, file: li }, true), null);
  assert.equal(runWikiSlugGuard(li, {}), undefined);
});

test('mergeShardedInput: a batch file whose file_count != files.length halts naming it', () => {
  const { manifest, batchResults, shardResults, files } = shardedFixture();
  batchResults[1] = { ...batchResults[1], file_count: 5 };
  const r = shardedLoad.mergeShardedInput(manifest, batchResults, shardResults, files);
  assert.equal(r.halted, 'input-count-mismatch');
  assert.equal(r.phase_reached, 'load');
  assert.match(r.detail, /batch-0002\.json/);
});

test('mergeShardedInput: a slug shard whose slug_count is off halts wiki-slugs-dropped naming it', () => {
  const { manifest, batchResults, shardResults, files } = shardedFixture();
  shardResults[0] = { ...shardResults[0], slug_count: 3 };
  const r = shardedLoad.mergeShardedInput(manifest, batchResults, shardResults, files);
  assert.equal(r.halted, 'wiki-slugs-dropped');
  assert.match(r.detail, /wikislugs-0001\.json/);
});

test('mergeShardedInput: a duplicate slug across shards passes the merge and trips the wikiSlugCount guard', () => {
  const { manifest, batchResults, shardResults, files } = shardedFixture();
  shardResults[1] = { shard: 2, slug_count: 1, entries: { 'alpha-guide': 'docs/wiki/alpha-guide.md' } };
  const r = shardedLoad.mergeShardedInput(manifest, batchResults, shardResults, files);
  assert.ok(r.loadedInput);
  assert.equal(Object.keys(r.loadedInput.wikiSlugs).length, 2);
  assert.equal(runWikiSlugGuard(r.loadedInput, {}).halted, 'wiki-slugs-dropped');
});

test('mergeShardedInput: a null position throws naming the file', () => {
  const { manifest, batchResults, shardResults, files } = shardedFixture();
  assert.throws(() => shardedLoad.mergeShardedInput(manifest, [batchResults[0], null], shardResults, files), /batch-0002\.json/);
  assert.throws(() => shardedLoad.mergeShardedInput(manifest, batchResults, [null, shardResults[1]], files), /wikislugs-0001\.json/);
});

test('single-file relay retired: manifest schema requires the shard lists and carries no inline table', () => {
  const m = LIVE_CODE.match(/const INPUT_FILE_SCHEMA = \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'INPUT_FILE_SCHEMA not found');
  assert.match(m[0], /required: \['batchFiles', 'slugShardFiles'\]/);
  assert.doesNotMatch(m[0], /^    batches:/m);
  assert.doesNotMatch(m[0], /^    wikiSlugs:/m);
  assert.doesNotMatch(LIVE_CODE, /input-shape-ambiguous/);
  assert.doesNotMatch(LIVE_CODE, /inputShapeAmbiguousHalt/);
  assert.match(LIVE_CODE, /is not a manifest \(batchFiles and /);
});

test('shardPathFor: absolute, drive-anchored and ".." shard paths throw', () => {
  for (const rel of ['/etc/x.json', '\\x.json', ['C:', 'x.json'].join('\\'), '../x.json', 'a/../../x.json']) {
    assert.throws(() => shardedLoad.shardPathFor('/var/run/workflow-input.json', rel), /inside the manifest/, rel);
  }
});

test('wiki-slugs-dropped: args.wikiSlugCount is compared when an integer', () => {
  const li = { wikiSlugCount: 1, wikiSlugs: { a: 'x' } };
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 1 }), undefined);
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 2 }).halted, 'wiki-slugs-dropped');
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 'n/a' }), undefined);
});

test('buildLoadStats: agent count, merged counts and the largest relay', () => {
  const s = shardedLoad.buildLoadStats([10, 900, 40], [{ files: ['a', 'b'] }, { files: ['c'] }], { x: 'p', y: 'q' });
  assert.deepEqual(s, { agents: 3, batch_count: 2, total_file_count: 3, wikiSlugCount: 2, max_relay_bytes: 900 });
  assert.deepEqual(shardedLoad.buildLoadStats([], null, null),
    { agents: 0, batch_count: 0, total_file_count: 0, wikiSlugCount: 0, max_relay_bytes: 0 });
});

test('sharded load block: every load agent carries phase and model, shard dispatch precedes scan, no .filter(Boolean) on shard results', () => {
  const start = LIVE_CODE.indexOf('if (RAW_ARGS_INPUT && RAW_ARGS_INPUT.inputFile) {');
  const end = LIVE_CODE.indexOf('const RUN_ID = ');
  const block = LIVE_CODE.slice(start, end);
  const calls = [...block.matchAll(/agent\(/g)].length;
  assert.equal(calls, 3);
  assert.equal([...block.matchAll(/phase: 'load'/g)].length, calls);
  assert.equal([...block.matchAll(/model: 'haiku'/g)].length, calls);
  assert.ok(end < LIVE_CODE.indexOf('const scanResults = (await parallel('));
  assert.match(block, /label: `batch-\$\{/);
  assert.match(block, /label: `wikislugs-\$\{/);
  assert.match(block, /concurrency: CONCURRENCY_CAP/);
  assert.doesNotMatch(block.slice(block.indexOf('const batchResults')), /\.filter\(Boolean\)/);
  assert.ok(LIVE_CODE.indexOf('const CONCURRENCY_CAP') < start, 'CONCURRENCY_CAP must be initialised before the load block');
  assert.match(LIVE_CODE, /load_stats: buildLoadStats\(loadAgentBytes, BATCHES, WIKI_SLUGS\)/);
});
