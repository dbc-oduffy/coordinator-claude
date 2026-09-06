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
 * Spec backlink: /private/tmp/claude-501/-Users-example-operator-X-DoE-claude/792aee5f-e00d-4d98-a3e6-e4705ec5d010/scratchpad/distill-harvest-fix-design.md
 * § "Regression test" + § "D3 design".
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
// comment (explaining WHY the static CONCURRENCY_CAP exists); we must assert on live code,
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

const buildCandidatesByTopicSrc = extractFunctionSource(SOURCE, 'buildCandidatesByTopic');
const candidatesExtracted = new Function(`
  ${slugifyTopicSrc}
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

// Review: code-reviewer (pipeline-code slice, Finding 1) — a `keep` verdict with no
// canonical_slug now fails loud (AC7 no-silent-degradation), same contract normalize/merge
// already enforce below. This test used to assert the overturned lenient fallback.
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

// Review: code-reviewer (tests slice, Finding 1) — combines the two scenarios above (colliding
// shape-variant collapse + a stale merge_target that differs from the shared canonical_slug)
// into ONE fixture, chained through clusterNuggets. Defense-in-depth, not a live gap:
// applyHomingOverride unconditionally nulls merge_target on every override, so the "merge_target
// differs from canonical_slug post-override" condition is currently unreachable — this exists to
// catch a FUTURE change that stops unconditionally nulling it. Do not delete as redundant with
// the two tests above; this is the only place all three conditions land in one fixture.
// ---------------------------------------------------------------------------------------------
// dropSummary.by_reason / by_cause grouping (Review: code-reviewer, pipeline-code slice,
// Finding 4) — four parallel accumulation blocks (by-tag, by-reason, by-cause, top-10) with no
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
  // Review: code-reviewer (tests slice, Finding 5) — parse the actual enum declaration line
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
// Review: code-reviewer (tests slice, Finding 1) — the guard's condition alone doesn't prove
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
  // Review: code-reviewer (tests slice, Finding 2) — anchor on the code identifier the
  // merge-back loop actually declares, not the prose comment above it; a copy-edit to that
  // comment must not be able to break this test.
  const mergeBackAnchor = 'const synthResultsByTopic = new Map(synthResults.map((r) => [r.topic_key, r]))';
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
