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
// A CRLF checkout (core.autocrlf on Windows) must not break the multi-line anchors below.
const SOURCE = fs.readFileSync(WORKFLOW_PATH, 'utf8').replace(/\r\n/g, '\n');
const os = require('node:os');
const HAVE_PYTHON3 = require('node:child_process').spawnSync('python3', ['-V']).status === 0
  && require('node:child_process').spawnSync('bash', ['-c', 'true']).status === 0;

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

// The path classifier and its two constants, as Function-body source for the extracted functions that call it.
const CLASSIFIER_SRC = [
  `const TRIAGE_ONLY_DIRS = ${SOURCE.match(/const TRIAGE_ONLY_DIRS = (\[[^\]]*\])/)[1]}`,
  `const BUILTIN_INTAKE_ROOTS = ${SOURCE.match(/const BUILTIN_INTAKE_ROOTS = (\[[^\]]*\])/)[1]}`,
  ...['normArtifactPath', 'intakeRootOf', 'artifactClassOf'].map((n) => extractFunctionSource(SOURCE, n)),
].join('\n');

test('D1: workflow.js has no live await-import / import() call', () => {
  assert.doesNotMatch(LIVE_CODE, /await\s+import\s*\(/, 'live "await import(" found outside comments');
  assert.doesNotMatch(LIVE_CODE, /[^.\w]import\s*\(/, 'live "import(" call found outside comments');
});

test('empty-input-batches: guard halts before any scan dispatch and names the input file', () => {
  const m = SOURCE.match(/if \(!Array\.isArray\(BATCHES\) \|\| BATCHES\.length === 0\) \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'empty-batches guard not found');
  assert.ok(m[0].includes("halted: 'empty-input-batches'"));
  assert.ok(SOURCE.indexOf(m[0]) < SOURCE.indexOf('const SCAN_ATTEMPTS = '),
    'guard must precede the scan dispatch');
  const run = (RAW_ARGS_INPUT, BATCHES) =>
    new Function('RAW_ARGS_INPUT', 'BATCHES', 'loadStats', 'ADMISSION_REPORT', m[0])(RAW_ARGS_INPUT, BATCHES, () => ({}), {});
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
  return { slugifyTopic, consolidateClusters, findFuzzyWikiHome };
`)();

const { slugifyTopic, consolidateClusters } = extracted;

test('fuzzy homing: every word must stem-match; a shared leading word never homes an unrelated topic', () => {
  const idx = { 'portable-docs-source-boundary': 'docs/wiki/a.md', 'admissibility-gate': 'docs/wiki/b.md', 'reconciliation-ledger': 'docs/wiki/c.md' };
  assert.equal(extracted.findFuzzyWikiHome('portable-export', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('admission-gate', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('portable-docs-source-boundaries', idx), 'docs/wiki/a.md');
  assert.equal(extracted.findFuzzyWikiHome('reconciliations-ledgers', idx), 'docs/wiki/c.md');
});

test('fuzzy homing: a 2+-word slug that leads exactly one existing slug homes there; ambiguity or one word does not', () => {
  const idx = { 'entity-anchor-encoding-contract': 'docs/wiki/e.md', 'storage-backend-direction': 'docs/wiki/s1.md', 'storage-backend-chroma': 'docs/wiki/s2.md', 'windows-specific': 'docs/wiki/w.md' };
  assert.equal(extracted.findFuzzyWikiHome('entity-anchors', idx), 'docs/wiki/e.md');
  assert.equal(extracted.findFuzzyWikiHome('storage-backend', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('windows', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('anchor-encoding', idx), null);
});

test('fuzzy homing: an existing 2+-word slug that ends exactly one new slug homes it; ambiguity or one word does not', () => {
  const idx = { 'claim-identity': 'docs/wiki/c.md', 'band-health': 'docs/wiki/b1.md', 'probe-band-health': 'docs/wiki/b2.md', 'posture': 'docs/wiki/p.md' };
  assert.equal(extracted.findFuzzyWikiHome('fleet-claim-identities', idx), 'docs/wiki/c.md');
  assert.equal(extracted.findFuzzyWikiHome('live-probe-band-health', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('erasure-posture', idx), null);
  assert.equal(extracted.findFuzzyWikiHome('claim-identity-drift', idx), 'docs/wiki/c.md');
  assert.equal(extracted.findFuzzyWikiHome('band-health-probe', { 'band-health': 'docs/wiki/b1.md', 'health-probe': 'docs/wiki/h.md' }), null);
  assert.equal(extracted.findFuzzyWikiHome('text-embed-door-serving-shape', { 'text-embed-door': 'docs/wiki/t.md' }), 'docs/wiki/t.md');
});

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

const RELAY_TABLE_SRC = '';

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

test('empty-content batch: a batch with zero nuggets is a failed scan (every file owes a nugget)', () => {
  const scanResults = [{ batch_id: 'quiet-01', nuggets: [] }];
  const { emptyContentBatchIds, failedBatchIds } = runEmptyContentDetection(scanResults, ['quiet-01']);

  assert.deepEqual(emptyContentBatchIds, ['quiet-01'], 'run 12h10: nuggets=[] for 3 non-empty files was an unread batch');
  assert.deepEqual(failedBatchIds, ['quiet-01']);
});

test('empty scan: every batch failed halts empty-scan; zero nugget sources is never a clean join', () => {
  const i = LIVE_CODE.indexOf("halted: 'empty-scan'");
  assert.ok(i > LIVE_CODE.indexOf('const failedBatchIds = BATCHES'), 'halt follows the failed-batch fold');
  assert.ok(i < LIVE_CODE.indexOf('const sourceNormalization = normalizeNuggetSources('), 'halt precedes join-integrity');
  assert.match(LIVE_CODE, /distinctSourceCount === 0 && sourceNormalization\.batch_files > 0\s*\? 'failed'/);
});

test('scan brief keys nuggets_file by run id and a stale one is cleared', () => {
  assert.match(SOURCE, /\$\{RUN_ID\}-\$\{batch\.batchId\}-extraction\.md/);
  assert.match(LIVE_CODE, /!result\.nuggets_file\.includes\(String\(RUN_ID\)\)/);
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

test('AC9a: drop_cause conformance; bare-no-sibling is no longer a live cause, only a pre-fix fixture residue', () => {
  // Post-curation-fix enum: bare-tag no-sibling nuggets are kept at defaults, so the live
  // causes are placeholder and below-threshold. The 2026-08-06 fixture predates the fix and
  // still carries bare-no-sibling drops; they are tolerated here as fixture residue only.
  const LIVE_DROP_CAUSES = new Set(['placeholder', 'below-threshold']);
  const PRE_FIX_FIXTURE_RESIDUE = new Set(['bare-no-sibling']);

  for (const thr of ['auto', '1', '2', '3']) {
    const verdicts = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result.verdicts;
    for (const v of verdicts) {
      if (v.verdict === 'drop') {
        assert.ok(
          LIVE_DROP_CAUSES.has(v.drop_cause) || PRE_FIX_FIXTURE_RESIDUE.has(v.drop_cause),
          `threshold ${thr}: drop entry for ${v.tag} has invalid drop_cause: ${v.drop_cause}`
        );
      } else {
        assert.ok(
          v.drop_cause === null || v.drop_cause === undefined,
          `threshold ${thr}: drop_cause must be null/absent on non-drop verdict for ${v.tag} (${v.verdict}), got ${v.drop_cause}`
        );
      }
    }
  }

  // The count block must still reconcile with the verdict list, whatever causes it carries.
  for (const thr of ['1', '2', '3']) {
    const result = VERDICT_PAYLOAD.by_threshold[thr].curate_clusters_result;
    const byCause = result.counts.drop_by_cause;
    const tally = {};
    for (const v of result.verdicts) if (v.verdict === 'drop') tally[v.drop_cause] = (tally[v.drop_cause] || 0) + 1;
    for (const cause of Object.keys(byCause)) {
      assert.equal(byCause[cause], tally[cause] || 0, `threshold ${thr}: drop_by_cause[${cause}] must equal the verdict list tally`);
    }
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
    'phase', 'agent', 'parallel', 'log', 'COMMON', 'DISTILL_WRITER_TYPE',
    `
    const countedAgent = agent;
    return (async () => {
      let opusEscalation = { triggered: false, cross_cluster_candidates: crossClusterCandidates };
      ${escalationBlockSrc}
      return opusEscalation;
    })();
    `
  );
  return fn(
    totalUnresolvableContradictions, crossClusterCandidates, contradictionResults,
    () => {}, agentImpl, parallelImpl, () => {}, '', 'coordinator:distill-writer'
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

test('sequencing: the coverage-gate report precedes phase(\'judgment-mining\') in source order', () => {
  // Anchor on the code identifier the gate declares, not the prose comment above it.
  const mergeBackAnchor = 'const unsynthesizedTopicKeys = clusters';
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

function runDistillationLogRows({ scanResults, synthResults, BATCHES, failedBatchIds, CONTEXT_TERMS, clusters = [] }) {
  const start = SOURCE.indexOf('const fateByPath = new Map()');
  const end = SOURCE.indexOf('// Provenance completeness', start);
  assert.ok(start >= 0 && end > start, 'distillation-log row block not found in workflow.js');
  const fn = new Function(
    'scanResults', 'synthResults', 'BATCHES', 'failedBatchIds', 'CONTEXT_TERMS', 'clusters',
    `
    const unchangedResults = []
    const RESIDUE_NUGGET_IDS = new Set()
    const PREPARED = null
    ${extractFunctionSource(SOURCE, 'countWords')}
    ${extractFunctionSource(SOURCE, 'classifiedFilesOf')}
    ${SOURCE.slice(start, end)}
    return distillationLogRows;
    `
  );
  return fn(scanResults, synthResults, BATCHES, failedBatchIds, CONTEXT_TERMS, clusters);
}

test('log rows: an artifact whose nugget no landed op cites is SKIP, never EPHEMERAL; a cited one stays DISTILLED', () => {
  const scanResults = [{
    batch_id: 'b1',
    file_fates: [
      { path: 'p/deferred.md', fate_prose: 'Describes a retry rule for the ingest queue worth keeping in the guide.' },
      { path: 'p/cited.md', fate_prose: 'Describes a retry rule for the ingest queue worth keeping in the guide.' },
    ],
    nuggets: [
      { id: 'n-deferred', type: 'RULE', source: 'p/deferred.md', content: 'x' },
      { id: 'n-cited', type: 'RULE', source: 'p/cited.md', content: 'y' },
    ],
  }];
  const rows = runDistillationLogRows({
    scanResults,
    synthResults: [{ topic_key: 't', wiki_path: 'docs/wiki/t.md', dispositions: [{ nugget_id: 'n-cited', op: 'ADD_SECTION' }] }],
    BATCHES: [{ batchId: 'b1', files: ['p/deferred.md', 'p/cited.md'] }],
    failedBatchIds: [],
    CONTEXT_TERMS: [],
    clusters: [{ topicKey: 't', nuggets: [{ id: 'n-cited' }, { id: 'n-deferred' }] }],
  });
  const byPath = Object.fromEntries(rows.map((r) => [r.path, r.disposition]));
  assert.deepEqual(byPath, { 'p/deferred.md': 'SKIP', 'p/cited.md': 'DISTILLED' });
});

test('hand-back: every distillation_log_rows entry carries the path, disposition and fate keys across all dispositions', () => {
  const rows = runDistillationLogRows({
    scanResults: [{
      batch_id: 'b1',
      file_fates: [{ path: 'p/reviewed.md', fate_prose: 'Routine config file, nothing worth distilling here at all.' }],
      nuggets: [{ id: 'b1-001', type: 'EPHEMERAL', source: 'p/reviewed.md', content: 'routine config' }],
    }],
    synthResults: [],
    BATCHES: [{ batchId: 'b1', files: ['p/reviewed.md', 'p/omitted.md'] }, { batchId: 'b2', files: ['p/unscanned.md'] }],
    failedBatchIds: ['b2'],
    CONTEXT_TERMS: [],
  });
  assert.deepEqual(rows.map((r) => r.disposition).sort(), ['EPHEMERAL', 'SKIP', 'SKIP']);
  for (const row of rows) {
    for (const key of ['path', 'disposition', 'fate']) {
      assert.ok(typeof row[key] === 'string' && row[key] !== '', `row ${row.path} missing non-empty ${key}`);
    }
  }
});

// ---------------------------------------------------------------------------
// Hand-back completeness: provenance reasons, writer no-write reasons, re-entry edits, brief guard.
// ---------------------------------------------------------------------------

test('hand-back: scanBriefFor tells scanners to copy truncated-looking strings exactly and not complete words', () => {
  const body = extractBlockSource(SOURCE, 'const scanBriefFor = (batch) => COMMON', 'colleague who asked what it covered and whether it mattered.`');
  assert.match(body, /Copy truncated-looking strings exactly; do not\s+complete words/);
});

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

test('a fate line with zero nuggets is sent back (SKIP): deferring a file to a later pass is not a review', () => {
  const rows = runDistillationLogRows({
    scanResults: [{
      batch_id: 'b1',
      file_fates: [{ path: 'archive/daily-summaries/dense.md', fate_prose: 'Did not verify as captured, so it is left for a cluster-level pass.' }],
      nuggets: [],
    }],
    synthResults: [],
    BATCHES: [{ batchId: 'b1', files: ['archive/daily-summaries/dense.md'] }],
    failedBatchIds: [],
    CONTEXT_TERMS: [],
  });
  assert.equal(rows[0].disposition, 'SKIP');
});

test('scanBriefFor requires a nugget per file and forbids deferring to a later pass', () => {
  const body = extractBlockSource(SOURCE, 'const scanBriefFor = (batch) => COMMON', 'colleague who asked what it covered and whether it mattered.`');
  assert.match(body, /Every file yields at least one nugget/);
  assert.match(body, /No later pass reads this file/);
});

test('Finding 1: an artifact with only an EPHEMERAL nugget resolves EPHEMERAL (ordinary case not flipped)', () => {
  const rows = runDistillationLogRows({
    scanResults: [{
      batch_id: 'b1',
      file_fates: [{ path: 'path/reviewed-nothing-to-extract.md', fate_prose: 'Routine config file, nothing worth distilling here at all.' }],
      nuggets: [{ id: 'b1-001', type: 'EPHEMERAL', source: 'path/reviewed-nothing-to-extract.md', content: 'routine config' }],
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

test('a path carried by crossRepoDispositions is emitted once, as the cross-repo row', () => {
  const dup = 'state/cross-repo/archive/2026-07/m.md';
  const row = { artifact_path: dup, disposition: 'DELETE', reason: 'cross-repo settled', source_nugget_ids: [] };
  const result = runCrossRepoMerge({
    phase3d: { status: 'ran', deletions: [{ artifact_path: dup, disposition: 'PRESERVE', reason: 'agent', source_nugget_ids: [] }, { artifact_path: 'local/bar.md', disposition: 'DELETE', reason: 'x', source_nugget_ids: [] }] },
    CROSS_REPO_DISPOSITIONS: [row],
  });
  const forDup = result.deletions.filter((d) => d.artifact_path === dup);
  assert.equal(forDup.length, 1);
  assert.equal(forDup[0].reason, 'cross-repo settled');
  assert.equal(result.deletions.length, 2);
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
  // remaining 6 of allTouched carry only an EPHEMERAL nugget (exact path)

  const nuggets1 = [];
  const nuggets2 = [];
  nuggetFiles.forEach((filePath, idx) => {
    const source = idx < 8 ? filePath : filePath.split('/').pop(); // 8 exact-path, 6 bare-basename
    const nugget = { id: `b-nug-${String(idx + 1).padStart(2, '0')}`, type: 'KNOWLEDGE', source, content: 'x' };
    if (b1.includes(filePath)) nuggets1.push(nugget); else nuggets2.push(nugget);
  });
  allTouched.slice(14).forEach((filePath, idx) => {
    const nugget = { id: `b-eph-${idx + 1}`, type: 'EPHEMERAL', source: filePath, content: 'x' };
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

test('C1 Fixture B naive arm: join repair never run -> 8 DISTILLED / 6 EPHEMERAL / 9 SKIP (unjoined files are sent back, not mislabelled)', () => {
  const fixture = buildFixtureB(); // fresh — the repair span never runs against this copy
  const rows = runDistillationLogRows(fixture);

  assert.deepEqual(countDispositions(rows), { DISTILLED: 8, EPHEMERAL: 6, SKIP: 9 });
});

test('C1 Fixture B delta: exactly 6 artifacts flip DISTILLED -> SKIP when the join repair is absent', () => {
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
    if (row.disposition === 'DISTILLED' && naiveByPath.get(row.path) === 'SKIP') flips++;
  }

  assert.equal(flips, 6, 'the naive arm is not decoration — without it a repaired-but-unneeded pass would look identical to a real one');
});

// ---------------------------------------------------------------------------
// wiki-slugs-dropped guard
// ---------------------------------------------------------------------------


function runWikiSlugGuard(loadedInput, RAW_ARGS_INPUT) {
  const start = SOURCE.indexOf('const WIKI_SLUGS = ');
  const end = SOURCE.indexOf('// Fate-prose enforcement', start);
  const body = SOURCE.slice(start, end);
  const wikiDirsCandidate = (loadedInput && loadedInput.wikiDirs) || RAW_ARGS_INPUT.wikiDirs;
  return new Function('loadedInput', 'RAW_ARGS_INPUT', 'wikiDirsCandidate', 'loadStats', 'ADMISSION_REPORT', `${body}\nreturn undefined`)(loadedInput, RAW_ARGS_INPUT, wikiDirsCandidate, () => ({}), {});
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
  assert.ok(/!synthResults\.some\(\(r\) => sameTopic\(r\.topic_key, c\.topicKey\)\)/.test(SOURCE), 'unsynthesized topics must join by sameTopic');
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



test('renderFormatHints: string, non-empty object, empty object', () => {
  const render = new Function(`${extractFunctionSource(SOURCE, 'renderFormatHints')}\nreturn renderFormatHints;`)();
  assert.equal(render('plain'), 'plain');
  assert.equal(render({ k: 'v' }), '{"k":"v"}');
  assert.equal(render({}), 'none');
  assert.equal(render(undefined), 'none');
});

const SCAN_WIKI = { alpha: 'docs/wiki/alpha.md', beta: 'docs/wiki/beta.md', gamma: 'docs/wiki/gamma.md' };
const SCAN_ALL = 'alpha (docs/wiki/alpha.md), beta (docs/wiki/beta.md), gamma (docs/wiki/gamma.md)';


const schemaConst = (name) => new Function(
  `return ${LIVE_CODE.match(new RegExp(`const ${name} = \\{[\\s\\S]*?\\n\\}\\n`))[0].replace(`const ${name} = `, '')}`)();





test('SKIP rows carry a skip_cause; presettle words the SEND_BACK reason from it; only a failed batch reads "batch never scanned"', () => {
  const rows = runDistillationLogRows({
    scanResults: [{
      batch_id: 'b1',
      file_fates: [{ path: 'p/unharvested.md', fate_prose: 'Describes a retry rule for the ingest queue worth keeping in the guide.' }],
      nuggets: [{ id: 'n-1', type: 'RULE', source: 'p/unharvested.md', content: 'x' }],
    }],
    synthResults: [],
    BATCHES: [{ batchId: 'b1', files: ['p/unharvested.md', 'p/omitted.md'] }, { batchId: 'b2', files: ['p/failed.md'] }],
    failedBatchIds: ['b2'],
    CONTEXT_TERMS: [],
    clusters: [{ topicKey: 't', nuggets: [{ id: 'n-1' }] }],
  });
  const cause = Object.fromEntries(rows.map((r) => [r.path, r.skip_cause]));
  assert.deepEqual(cause, {
    'p/unharvested.md': 'nuggets-not-harvested',
    'p/omitted.md': 'no-nuggets-no-classification',
    'p/failed.md': 'batch-never-scanned',
  });
  const presettle = new Function(
    `${CLASSIFIER_SRC}
${extractFunctionSource(SOURCE, 'enforceIntakeAndClass')}\n${extractFunctionSource(SOURCE, 'presettleDeletionRows')}\nreturn presettleDeletionRows`)();
  const { settled } = presettle(rows.map((r) => ({ ...r, path: `archive/specs/2026-10/${r.path.slice(2)}` })), []);
  const reasonOf = Object.fromEntries(settled.map((d) => [d.artifact_path.split('/').pop(), d.reason]));
  assert.equal(reasonOf['failed.md'], 'batch never scanned');
  assert.ok(!/never scanned/.test(reasonOf['unharvested.md']));
  assert.ok(!/never scanned/.test(reasonOf['omitted.md']));
});

test('a classified file is never SKIP for a never-scanned batch (assignment, not wording)', () => {
  const start = SOURCE.indexOf('const fateByPath = new Map()');
  assert.ok(/const scanned = classified \|\| !failedBatchIds\.includes\(batch\.batchId\)/.test(SOURCE.slice(start)));
});

test('re-entry cap: BLOCKED reason names no rounds when none ran, and the real count otherwise', () => {
  const capFor = (reentryRoundsRun, SEND_BACK_REENTRY_CAP = 2) => {
    const body = LIVE_CODE.slice(LIVE_CODE.indexOf('currentDeletions = currentDeletions.map((d) => {\n  if (d.disposition !== \'SEND_BACK\') return d'));
    const src = body.slice(0, body.indexOf('if (cappedArtifactPaths.length > 0)'));
    return new Function('currentDeletions', 'reentryRoundsRun', 'SEND_BACK_REENTRY_CAP',
      `const cappedArtifactPaths = []\n${src}\nreturn currentDeletions`)(
      [{ artifact_path: 'a.md', disposition: 'SEND_BACK', reason: 'r' }], reentryRoundsRun, SEND_BACK_REENTRY_CAP)[0];
  };
  assert.equal(capFor(0).disposition, 'BLOCKED');
  assert.ok(!/round\(s\)/.test(capFor(0).reason), capFor(0).reason);
  assert.match(capFor(0).reason, /no send_back re-entry round ran/);
  assert.match(capFor(2).reason, /after 2 send_back re-entry round\(s\)/);
});

test('presettleDeletionRows: SKIP, intake and non-delete-class rows settle in code; handoffs drop; deletable rows stay open', () => {
  const presettle = new Function(
    `${CLASSIFIER_SRC}
${extractFunctionSource(SOURCE, 'enforceIntakeAndClass')}\n${extractFunctionSource(SOURCE, 'presettleDeletionRows')}\nreturn presettleDeletionRows`)();
  const rows = [
    { path: 'archive/week-changelogs/2026-05-15/WEEK-SUMMARY.md', disposition: 'DISTILLED' },
    { path: 'docs/research/x/synthesis.md', disposition: 'EPHEMERAL' },
    { path: 'archive/specs/2026-10/p.md', disposition: 'SKIP' },
    { path: 'archive/handoffs/h.md', disposition: 'DISTILLED' },
    { path: 'archive/completed/c.md', disposition: 'DISTILLED' },
    { path: 'archive/specs/2026-10/q.md', disposition: 'EPHEMERAL' },
  ];
  const { settled, open } = presettle(rows, []);
  assert.deepEqual(open.map((r) => r.path), ['archive/completed/c.md', 'archive/specs/2026-10/q.md']);
  assert.deepEqual(settled.map((d) => [d.artifact_path, d.disposition]), [
    ['archive/week-changelogs/2026-05-15/WEEK-SUMMARY.md', 'PRESERVE'],
    ['docs/research/x/synthesis.md', 'PRESERVE'],
    ['archive/specs/2026-10/p.md', 'SEND_BACK'],
  ]);
  assert.match(settled[0].reason, /^intake-root: archive\/week-changelogs/);
  assert.ok(!settled[0].reason.includes('was DELETE'));
  assert.equal(presettle([{ path: 'archive/daily-summaries/d.md', disposition: 'DISTILLED' }], []).open.length, 0);
});

test('phase-3d: no agent dispatch when every row settles mechanically; the brief carries only open rows', () => {
  assert.match(LIVE_CODE, /\.open\.length === 0\) \{\n  phase3d = \{ deletions: phase3dSplit\.settled, status: 'settled-mechanically' \}/);
  assert.match(LIVE_CODE, /\$\{JSON\.stringify\(phase3dSplit\.open, null, 2\)\}/);
  assert.match(LIVE_CODE, /deletions: \[\.\.\.phase3dSplit\.settled, \.\.\.guarded\.rows\], status: 'ran'/);
  assert.match(LIVE_CODE, /phase3d\.status !== 'ran' && phase3d\.status !== 'settled-mechanically'/);
});








test('scan brief: file list, source rule and file_fates rule still key on the original paths', () => {
  const code = stripComments(SOURCE);
  assert.match(code, /Files to read: \$\{JSON\.stringify\(batch\.files\)\}/);
  assert.match(code, /ONE entry per file in "Files to read" above/);
  assert.match(code, /\$\{EXISTING_WIKI_SLUG_NAMES\}/);
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

test('workflow source: the judgment call site stamps the cluster key', () => {
  const code = stripComments(SOURCE);
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
  assert.ok(call < LIVE_CODE.indexOf('const SCAN_ATTEMPTS = '));
  assert.ok(/return \{ \.\.\.listCountHalt, load_stats: loadStats\(\) \}/.test(LIVE_CODE));
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
  return new Function('RAW_ARGS_INPUT', 'loadStats', 'ADMISSION_REPORT', `${m[0]}\nreturn undefined`)(raw, () => ({}), {});
}


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

// The curated file is loaded schema-free through the slice-echo loader; these are the top-level
// fields the script may read off `loadedCurated`. A new read must be added here deliberately.
const CURATED_FILE_FIELDS = new Set(['verdicts', 'contradictionClusters', 'counts', 'contradictionClusterCount',
  'threshold_applied', 'threshold_auto', 'nugget_drop_share']);



// project-rag live run: 14 of 212 dict slices missed because readers counted sorted positions wrong
// (one key too many, one too few, a neighbour swapped in). Dict slices now name their key range and
// the head its keys; an over-inclusive echo is trimmed to that range before its digest check.

// A relay that rewrites a dict key (".../claude-klabauter-em-claude-klabauter-debash-..." -> "...claude-klabauter-em-debash-...") is caught by
// the digest line's key-list hash; a named key missing from an echo sends later rounds to a whole-dict ask.




// project-rag live run: curated.json writes its 400 KB "verdicts" array first, so head readers hit the
// Read cap before reaching the small fields; a file over 2000 lines gets their line ranges in the ask.

// project-rag live run: Haiku readers collapse space runs inside strings ("—   ChromaDB" -> "— ChromaDB")
// identically every round, so the digest folds runs of 2+ spaces on both sides.

// example-game-repo live run: distill.scope writes wikislugs entries in file order, so a sorted-range ask made the
// reader sort in its head and drop every out-of-order key. Slices name their exact keys; only a key list
// over 2000 bytes falls back to the range, and that ask warns the object is unsorted.




function makeOversizeHeadFixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'head-load-'));
  const digests = {};
  for (let i = 0; i < 120; i++) digests[`docs/plans/2026-07-${String(i).padStart(3, '0')}-some-long-plan-name.md`] = crypto.createHash('sha256').update(`d${i}`).digest('hex').slice(0, 16);
  const relevantGuides = [];
  for (let i = 0; i < 40; i++) relevantGuides.push({ path: `docs/guides/guide-${i}.md`, outline: `# Guide ${i} café \u{1F600}\n` + `## section-${i} orientation system-prompt…\n`.repeat(4) });
  const files = [];
  for (let i = 0; i < 60; i++) files.push(`state/some/long/path/segment-${i}/file-${'x'.repeat(30)}.md`);
  const doc = { batchId: 'b-9', digests, relevantGuides, emptyList: [], note: 'small', files };
  const text = JSON.stringify(doc, null, 2);
  const file = path.join(dir, 'batch-0001.json');
  fs.writeFileSync(file, text);
  return { dir, file, doc: JSON.parse(text) };
}




// LOAD_DIGEST_PY as the workflow ships it, evaluated from source so the test runs the real one-liner.
function extractLoadDigestPy() {
  return new Function(`${LOAD_CONSTS_SRC}\nreturn LOAD_DIGEST_PY;`)();
}

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

const drMint = new Function(`
  ${slugifyTopicSrc}
  ${extractFunctionSource(SOURCE, 'findFoldedDecisions')}
  return { findFoldedDecisions };
`)();

const dec = (id) => ({ id, type: 'DECISION', content: `decision ${id}` });
const know = (id) => ({ id, type: 'KNOWLEDGE', content: `knowledge ${id}` });

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
  assert.deepEqual(out[0].foldedNuggets.map((n) => n.id), ['a', 'g'], 'a CREATE_DR disposition is a record: finalize mints it');
  assert.equal(out[0].wikiPath, 'docs/wiki/topic-a.md');
});

test('findFoldedDecisions: a fleet-rule SKIP is not folded; the bare prefix without an owner and a different spelling still are', () => {
  const clusters = [{ topicKey: 'topic-a', nuggets: [dec('a'), dec('b'), dec('c')] }];
  const results = [{ topic_key: 'topic-a', wiki_path: 'w.md', dispositions: [
    { nugget_id: 'a', op: 'SKIP', reason: 'FLEET-RULE-OWNED-ELSEWHERE claude-klabauter bash-to-python rule' },
    { nugget_id: 'b', op: 'SKIP', reason: 'FLEET-RULE-OWNED-ELSEWHERE' },
    { nugget_id: 'c', op: 'SKIP', reason: 'fleet rule owned elsewhere' },
  ] }];
  const out = drMint.findFoldedDecisions(clusters, results);
  assert.deepEqual(out[0].foldedNuggets.map((n) => n.id), ['b', 'c']);
});

test('findFoldedDecisions: ignores non-DECISION nuggets and nuggets with no disposition', () => {
  const clusters = [{ topicKey: 'topic-a', nuggets: [know('k'), dec('x')] }];
  const results = [{ topic_key: 'topic-a', wiki_path: 'w.md', dispositions: [{ nugget_id: 'k', op: 'ADD_SECTION' }] }];
  assert.deepEqual(drMint.findFoldedDecisions(clusters, results), []);
});

test('coverage gate: a report only, no dispatch and no re-synth', () => {
  const gate = LIVE_CODE.slice(LIVE_CODE.indexOf("phase('coverage-gate')"), LIVE_CODE.indexOf("phase('promote')"));
  assert.ok(gate.length > 0);
  assert.equal((gate.match(/agent\(/g) || []).length, 0);
  assert.doesNotMatch(gate, /resynthWork|gapSynth/);
  assert.match(gate, /unsynthesizedTopicKeys/);
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

function runSkipBranch(clusters, dispositions, createDr = []) {
  const fn = new Function('clusters', 'synthResults', 'createDrDispositions', `
    ${skipBranchSrc}
    }
    return phase3b;
  `);
  return fn(clusters, [{ topic_key: 't', dispositions }], createDr);
}

const scriptBranchSrc = extractBlockSource(
  SOURCE,
  'const mergedByRecord = new Map()',
  "status: 'script',\n  }"
);

test('phase-3b: no model agent is dispatched; finalize DR-EXISTS skips and minted targets are reported by script', () => {
  const start = LIVE_CODE.indexOf("phase('phase-3b')");
  const end = LIVE_CODE.indexOf("phase('phase-3d')");
  assert.ok(start > 0 && end > start);
  const phase3bCode = LIVE_CODE.slice(start, end);
  assert.equal((phase3bCode.match(/agent\(/g) || []).length, 0);
  assert.doesNotMatch(LIVE_CODE, /label: 'dr-dedup'|DR_DEDUP_SCHEMA|drDedupBrief/);
  const run = (createDr, existing) => new Function('createDrDispositions', 'existingRecordSkips', 'log', `
    let phase3b
    ${scriptBranchSrc}
    return phase3b;
  `)(createDr, existing, () => {});
  const out = run(
    [{ nugget_id: 'd1', target: 'docs/decisions/DR-5-new.md' }],
    [{ nugget_id: 'd2', reason: 'DR-EXISTS docs/decisions/DR-2-old.md' }, { nugget_id: 'd3', reason: 'DR-EXISTS docs/decisions/DR-2-old.md' }]
  );
  assert.equal(out.status, 'script');
  assert.equal(out.failure, false);
  assert.deepEqual(out.dr_files_found, ['docs/decisions/DR-5-new.md']);
  assert.deepEqual(out.dr_dedup, [
    { canonical_id: 'docs/decisions/DR-5-new.md', duplicate_ids: [], merge_rationale: '' },
    { canonical_id: 'docs/decisions/DR-2-old.md', duplicate_ids: ['d2', 'd3'], merge_rationale: out.dr_dedup[1].merge_rationale },
  ]);
});

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

test('phase-3b skip branch: fleet-rule skips (alone or with DR-EXISTS) are not a failure and name the owner; a folded sibling still fails', () => {
  const fleet = { nugget_id: 'd1', op: 'SKIP', reason: 'FLEET-RULE-OWNED-ELSEWHERE coordinator-content-repo CLAUDE.md venv ban' };
  const alone = runSkipBranch([{ nuggets: [dec('d1')] }], [fleet]);
  assert.equal(alone.failure, false);
  assert.match(alone.failure_detail, /fleet rule owned by coordinator-content-repo CLAUDE\.md venv ban/);
  const mixed = runSkipBranch([{ nuggets: [dec('d1'), dec('d2')] }], [
    fleet,
    { nugget_id: 'd2', op: 'SKIP', reason: 'DR-EXISTS docs/decisions/DR-9-x.md' },
  ]);
  assert.equal(mixed.failure, false);
  assert.match(mixed.failure_detail, /DR-9-x\.md/);
  const folded = runSkipBranch([{ nuggets: [dec('d1'), dec('d2')] }], [
    fleet,
    { nugget_id: 'd2', op: 'ADD_SECTION' },
  ]);
  assert.equal(folded.failure, true);
  assert.match(folded.failure_detail, /1 of 2 DECISION/);
});

test('dr_minting: returned, and a found record no disposition names lands in unclaimed_files', () => {
  assert.match(LIVE_CODE, /dr_minting: drMinting,/);
  const drMintingSrc = extractBlockSource(SOURCE, 'const drTargets = createDrDispositions', 'unclaimed_files: (phase3b.dr_files_found || []).map(normDrPath).filter((p) => !drTargetsNorm.has(p)),\n}');
  const run = (phase3b) => new Function('createDrDispositions', 'phase3b', 'decisionNuggets', 'allDispositions', 'allocatorUnavailableCount', 'foldedUnresolved', 'reconcileDrTargets', `${drMintingSrc}; return drMinting;`)(
    [{ target: 'docs/decisions/DR-1-a.md' }], phase3b, [{ id: 'd1' }], [], 0, [], reconcileDrTargets);
  const ok = run({ status: 'ran', dr_files_found: ['docs/decisions/DR-1-a.md', 'docs\\decisions\\DR-2-b.md'] });
  assert.deepEqual(ok.unclaimed_files, ['docs/decisions/DR-2-b.md']);
  assert.deepEqual(ok.missing_files, []);
  const none = run({ status: 'script', dr_files_found: [] });
  assert.deepEqual(none.missing_files, ['docs/decisions/DR-1-a.md']);
  assert.deepEqual(none.unclaimed_files, []);
});

test('dr_minting.create_dr counts records minted: two CREATE_DR on one page naming one record count once', () => {
  const drMintingSrc = extractBlockSource(SOURCE, 'const drTargets = createDrDispositions', 'unclaimed_files: (phase3b.dr_files_found || []).map(normDrPath).filter((p) => !drTargetsNorm.has(p)),\n}');
  const run = (createDr) => new Function('createDrDispositions', 'phase3b', 'decisionNuggets', 'allDispositions', 'allocatorUnavailableCount', 'foldedUnresolved', 'reconcileDrTargets', `${drMintingSrc}; return drMinting;`)(
    createDr, { status: 'script', dr_files_found: [] }, [{ id: 'd1' }], [], 0, [], reconcileDrTargets);
  const twoOnePage = run([
    { nugget_id: 'a', target: 'docs/decisions/DR-1-a.md' },
    { nugget_id: 'b', target: 'docs\\decisions\\DR-1-a.md' },
    { nugget_id: 'c', target: 'docs/decisions/DR-2-b.md' },
  ]);
  assert.equal(twoOnePage.create_dr, 2);
  assert.equal(twoOnePage.create_dr_dispositions, 3);
  const distinct = run([
    { nugget_id: 'a', target: 'docs/decisions/DR-1-a.md' },
    { nugget_id: 'b', target: 'docs/decisions/DR-2-b.md' },
  ]);
  assert.equal(distinct.create_dr, 2);
});

test('re-entry cap log: reports rounds run, and says none ran when it is 0', () => {
  const src = extractBlockSource(SOURCE, 'if (cappedArtifactPaths.length > 0) {', "cappedArtifactPaths.join(', ')}`)\n}");
  const logsFor = (reentryRoundsRun) => {
    const lines = [];
    new Function('cappedArtifactPaths', 'reentryRoundsRun', 'SEND_BACK_REENTRY_CAP', 'log', src)(['a.md'], reentryRoundsRun, 2, (l) => lines.push(l));
    return lines.join('\n');
  };
  assert.match(logsFor(0), /no re-entry round ran/);
  assert.ok(!/after 2 round/.test(logsFor(0)), logsFor(0));
  assert.match(logsFor(1), /after 1 round\(s\)/);
  assert.ok(!/\(cap /.test(logsFor(0)), logsFor(0));
  assert.match(logsFor(1), /\(cap 2\)/);
});

test('coverage gate logs carry the full uncovered nugget ids and unsynthesized topic keys', () => {
  const src = extractBlockSource(SOURCE, 'const totalAssignedNuggets =', "`nugget(s) uncovered by any landed op or record — ` +\n    `${remainingGaps.map((g) => `${g.topicKey} [${g.uncoveredNuggets.map((n) => n.id).join(', ')}]`).join('; ')}`)\n}");
  const lines = [];
  const ids = Array.from({ length: 30 }, (_, i) => `n-${i}`);
  new Function('clusters', 'synthResults', 'findCoverageGaps', 'findFoldedDecisions', 'sameTopic', 'deferredTopics', 'deferredNuggetIds', 'log', `${src}`)(
    [{ topicKey: 't1', nuggets: ids.map((id) => ({ id })) }, { topicKey: 't2', nuggets: [] }, { topicKey: 't3', nuggets: [] }],
    [{ topic_key: 't1' }],
    () => [{ topicKey: 't1', uncoveredNuggets: ids.map((id) => ({ id })) }],
    () => [],
    (a, b) => a === b,
    [], [], (l) => lines.push(l));
  const text = lines.join('\n');
  for (const id of ids) assert.ok(text.includes(id), `missing ${id}`);
  assert.match(text, /without a synth entry \(t2, t3\)/);
});

test('findCoverageGaps: an unsent topic is a gap unless deferred or pointer-covered', () => {
  const findCoverageGaps = new Function(`const slugifyTopic = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'); ${extractFunctionSource(SOURCE, 'findCoverageGaps')}; return findCoverageGaps;`)();
  const clusters = [
    { topicKey: 'sent', nuggets: [{ id: 'a' }, { id: 'b' }] },
    { topicKey: 'unsent', nuggets: [{ id: 'c' }, { id: 'd' }] },
    { topicKey: 'deferred', nuggets: [{ id: 'e' }] },
    { topicKey: 'pointed', nuggets: [{ id: 'f' }], pointer_covered: ['f'] },
    { topicKey: 'half', nuggets: [{ id: 'g' }, { id: 'h' }], pointer_covered: ['g'] },
  ];
  const results = [{ topic_key: 'sent', wiki_path: 'w.md', dispositions: [{ nugget_id: 'a' }, { nugget_id: 'b' }] }];
  const gaps = findCoverageGaps(clusters, results, ['deferred']);
  assert.deepEqual(gaps.map((g) => [g.topicKey, g.uncoveredNuggets.map((n) => n.id)]),
    [['unsent', ['c', 'd']], ['half', ['h']]]);
  // Default deferred list: the deferred topic is no longer exempt.
  assert.ok(findCoverageGaps(clusters, results).some((g) => g.topicKey === 'deferred'));
  // A deferred judge batch names no cluster: its nugget ids exempt the unsent clusters' nuggets.
  assert.deepEqual(findCoverageGaps(clusters, results, ['deferred'], ['c', 'd', 'h']), []);
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
  assert.ok(before.slice(branch).split('agent(').length === 2, 'the scout is the first agent call after the branch');
});

const judgmentPrecheckSaysDispatch = new Function(`${extractFunctionSource(SOURCE, 'judgmentPrecheckSaysDispatch')}; return judgmentPrecheckSaysDispatch;`)();

test('2.5 scout: dispatched only when the prepared precheck says dispatch', () => {
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: true, distinct_eligible_plans: 3 }), true);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false, distinct_eligible_plans: 1 }), false);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: 'yes' }), false);
  assert.equal(judgmentPrecheckSaysDispatch({}), false);
  assert.equal(judgmentPrecheckSaysDispatch(undefined), false);
  assert.equal(judgmentPrecheckSaysDispatch(null), false);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false, distinct_eligible_plans: 2 }, 2), true);
  assert.equal(judgmentPrecheckSaysDispatch({ dispatch: false, distinct_eligible_plans: 2 }, 3), false);
});

test('2.5 scout: the precheck gate sits on the scout branch and a skip yields a zero-cluster ran result', () => {
  const src = stripComments(SOURCE);
  assert.ok(!/batchesNamePlan/.test(src), 'the plan-path heuristic is retired');
  assert.match(src, /!judgmentPrecheckSaysDispatch\(loadedInput && loadedInput\.judgmentPrecheck, MIN_CONVERGENCE\)\)\s*\{\s*const pc = loadedInput && loadedInput\.judgmentPrecheck\s*judgmentScout = \{ sidecars_seen: judgmentPrecheckSidecars\(pc\), clusters: \[\] \}/);
  const r = resolveJudgmentClusters([], { sidecars_seen: 0, clusters: [] });
  assert.equal(r.status, 'ran');
  assert.deepEqual(r.clusters, []);
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

test('wiki-slugs-dropped: args.wikiSlugCount is compared when an integer', () => {
  const li = { wikiSlugCount: 1, wikiSlugs: { a: 'x' } };
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 1 }), undefined);
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 2 }).halted, 'wiki-slugs-dropped');
  assert.equal(runWikiSlugGuard(li, { inputFile: '/x', wikiSlugCount: 'n/a' }), undefined);
});


// ---------------------------------------------------------------------------
// Agent-cap shard contract helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Shard application: filter, cap halt, ledger
// ---------------------------------------------------------------------------


const mkTopics = (n, chars = 2000) => Array.from({ length: n }, (_, i) => ({
  topicKey: `topic-${i}`, nuggets: [{ id: `n${i}`, content: 'x'.repeat(chars) }],
}));

// Runs the halt check as invocation `shard` would at its candidates step, with `calls` already spent.
function capHaltFor({ clusters, consolidated, shard, calls, prefix }) {
  const h = loadCapHalt({ clusters, consolidated, shard, calls, prefix });
  return h.agentCapHalt('candidates', clusters.reduce((s, c) => s + h.candidatePayloadBytes(c), 0));
}








// example-game-repo B: re-entry agents handed 35-39 artifacts read the "under ~10 minutes" preface as infeasible
// and returned every row SEND_BACK without a tool call; groups are capped at REENTRY_GROUP_MAX.


// DR ledger, link-depth and title guards: pure helpers extracted by text.
const drSynthResults = [
  { topic_key: 't1', wiki_path: 'docs/wiki/a.md', dispositions: [
    { nugget_id: 'd1', op: 'CREATE_DR', target: 'docs/decisions/DR-1-use-ledger.md' },
    { nugget_id: 'k1', op: 'ADD_SECTION' },
    { nugget_id: 'd2', op: 'CREATE_DR' },
  ] },
  { topic_key: 't2', wiki_path: 'docs/wiki/b.md', dispositions: [
    { nugget_id: 'd3', op: 'CREATE_DR', target: 'docs/decisions\\DR-2-split.md' },
    { nugget_id: 'd4', op: 'CREATE_DR', target: 'docs/decisions/DR-1-use-ledger.md' },
  ] },
];







// ---------------------------------------------------------------------------
// Admission: not_admitted / deferred lists
// ---------------------------------------------------------------------------

const NOT_ADMITTED_FX = [
  { path: 'docs/plans/a.md', cohort: 'c1', reason: 'no-signal' },
  { path: 'docs/plans/b.md', cohort: 'c1', reason: 'no-signal' },
];
const DEFERRED_FX = [{ path: 'docs/plans/c.md', cohort: 'c2' }];




// ---------------------------------------------------------------------------
// Plan triage: logs-first Haiku verdicts before the scan wave opens any plan
// ---------------------------------------------------------------------------

const triage = new Function(CLASSIFIER_SRC + '\n' +
  ['planPathsOf', 'resolveLogRoots', 'planTriageBrief', 'applyPlanTriage']
    .map((n) => extractFunctionSource(SOURCE, n)).join('\n') +
  '\nreturn { planPathsOf, resolveLogRoots, planTriageBrief, applyPlanTriage };')();

const TRIAGE_BATCHES = [
  { batchId: 'b1', files: ['docs/plans/2026-11/keep.md', 'docs/plans/2026-11/drop.md', 'state/handoffs/h.md'] },
  { batchId: 'b2', files: ['archive/plans/2026-10/drop2.md'] },
];

test('planTriage: only docs/plans and archive plan paths are candidates; non-plans are not', () => {
  assert.deepEqual(triage.planPathsOf(TRIAGE_BATCHES),
    ['archive/plans/2026-10/drop2.md', 'docs/plans/2026-11/drop.md', 'docs/plans/2026-11/keep.md']);
});

test('planTriage: a probably_not plan leaves every batch, non-plans pass through, kept/dropped are counted', () => {
  const paths = triage.planPathsOf(TRIAGE_BATCHES);
  const { batches, report } = triage.applyPlanTriage(TRIAGE_BATCHES, paths, { verdicts: [
    { path: 'docs/plans/2026-11/keep.md', verdict: 'moved_the_needle', cite: 'daily 11-10' },
    { path: 'docs/plans/2026-11/drop.md', verdict: 'probably_not', cite: 'no log mention' },
    { path: 'archive/plans/2026-10/drop2.md', verdict: 'probably_not', cite: 'no log mention' },
    { path: 'state/handoffs/h.md', verdict: 'probably_not', cite: 'not a candidate' },
  ] });
  assert.deepEqual(batches.map((b) => b.batchId), ['b1']);
  assert.deepEqual(batches[0].files, ['docs/plans/2026-11/keep.md', 'state/handoffs/h.md']);
  assert.equal(report.status, 'ok');
  assert.equal(report.kept, 1);
  assert.equal(report.dropped, 2);
  assert.equal(report.candidates, 3);
});

test('planTriage: a null or malformed result keeps every plan and reports agent-failed; unjudged plans are kept', () => {
  const paths = triage.planPathsOf(TRIAGE_BATCHES);
  for (const bad of [null, undefined, {}, { verdicts: 'x' }]) {
    const { batches, report } = triage.applyPlanTriage(TRIAGE_BATCHES, paths, bad);
    assert.equal(batches, TRIAGE_BATCHES);
    assert.equal(report.status, 'agent-failed');
    assert.equal(report.kept, 3);
    assert.equal(report.dropped, 0);
  }
  const partial = triage.applyPlanTriage(TRIAGE_BATCHES, paths, { verdicts: [] });
  assert.equal(partial.report.dropped, 0);
});

test('planTriage: brief names log roots and candidate plans and forbids opening a plan; logRoots are repo-relative with defaults', () => {
  const brief = triage.planTriageBrief('PROMPT Do NOT open', ['archive/daily-summaries'], ['docs/plans/a.md']);
  assert.match(brief, /- archive\/daily-summaries/);
  assert.match(brief, /Candidate plans \(do not open\):\n- docs\/plans\/a\.md/);
  assert.deepEqual(triage.resolveLogRoots(undefined), ['archive/daily-summaries', 'archive/release-notes']);
  assert.deepEqual(triage.resolveLogRoots(['archive/weekly']), ['archive/weekly']);
  for (const bad of [['/abs/logs'], ['C' + ':\\logs'], ['../logs'], [''], []]) {
    assert.deepEqual(triage.resolveLogRoots(bad), ['archive/daily-summaries', 'archive/release-notes']);
  }
});

test('planTriage: phase runs between load and scan with one haiku op-relay agent; prompt file exists', () => {
  const at = LIVE_CODE.indexOf("phase('plan-triage')");
  assert.ok(LIVE_CODE.indexOf("phase('load')") < at);
  assert.ok(at < LIVE_CODE.indexOf("phase('scan')"));
  const call = LIVE_CODE.slice(at, LIVE_CODE.indexOf("phase('scan')"));
  assert.equal((call.match(/agent\(/g) || []).length, 1);
  assert.match(call, /agentType: DISTILL_WRITER_TYPE[^}]*model: 'haiku'/);
  assert.match(call, /halted: 'all-plans-triaged-out'/);
  assert.ok((LIVE_CODE.match(/plan_triage: PLAN_TRIAGE_REPORT/g) || []).length >= 3, 'every return carries the triage report');
  assert.ok(fs.existsSync(path.join(__dirname, '..', 'agent-prompts', 'plan-triage.md')));
});

// ---------------------------------------------------------------------------
// Consolidation: one unit and one page per topic
// ---------------------------------------------------------------------------

test('consolidation: merged cross-file clusters consolidate to one unit per topic, disjoint wikiPaths', () => {
  // Six topics, each merged from nuggets of three source files (tag variants unified upstream).
  const topics = ['alpha-routing', 'bravo-caching', 'charlie-auth', 'delta-queues', 'echo-retries', 'foxtrot-logging'];
  const raw = topics.map((t) => ({
    topicKey: t,
    nuggets: ['f1', 'f2', 'f3'].map((f) => ({ id: `${t}-${f}`, type: 'RULE', source: `${f}.md` })),
    sourceBatches: ['b1', 'b2', 'b3'],
  }));
  const wikiSlugs = { 'charlie-auth': 'docs/wiki/charlie-auth.md' };
  const units = consolidateClusters(raw, wikiSlugs, { runId: 'r', wikiDirs: ['docs/wiki'] });
  assert.equal(units.length, topics.length, 'one unit per topic, not per source file');
  const paths = units.map((u) => u.wikiPath);
  assert.equal(new Set(paths).size, paths.length, 'disjoint wikiPath per staged page');
  assert.equal(units.find((u) => u.topicKey === 'charlie-auth').wikiPath, 'docs/wiki/charlie-auth.md', 'homed slug keeps its guide');
  assert.equal(units.reduce((n, u) => n + u.nuggets.length, 0), 18, 'no nugget lost');
});

// ---------------------------------------------------------------------------
// Engine-inlined launch args: `$chunked` wrappers flatten before the args-passed path reads them
// ---------------------------------------------------------------------------

function loadUnchunkArgs() {
  const m = SOURCE.match(/function unchunkArgs\(value\) \{[\s\S]*?\n\}\n/);
  assert.ok(m, 'unchunkArgs not found');
  return new Function(`${m[0]}\nreturn unchunkArgs`)();
}




// ---------------------------------------------------------------------------
// Phase 3d intake/class guard: a log/intake source or an unrecognised class is never DELETE
// ---------------------------------------------------------------------------

function loadIntakeGuard() {
  return new Function(`${CLASSIFIER_SRC}
${extractFunctionSource(SOURCE, 'enforceIntakeAndClass')}\nreturn enforceIntakeAndClass`)();
}

const delRow = (p) => ({ artifact_path: p, disposition: 'DELETE', reason: 'extracted' });

test('intake guard: DELETE under each built-in intake root lands PRESERVE with the root named', () => {
  const guard = loadIntakeGuard();
  const paths = [
    'archive/daily-summaries/2026-11-01.md',
    'archive/week-changelogs/2026-W44.md',
    'archive/release-notes/v1.md',
  ];
  const { rows, downgraded } = guard(paths.map(delRow), []);
  assert.equal(downgraded.length, 3);
  rows.forEach((r, i) => {
    assert.equal(r.disposition, 'PRESERVE');
    assert.match(r.reason, /^intake-root: /);
    assert.ok(r.reason.includes(paths[i].split('/').slice(0, 2).join('/')));
  });
});

test('intake guard: custom logRoots entries match with forward and backslash separators', () => {
  const guard = loadIntakeGuard();
  const { rows } = guard(
    [delRow('notes/intake/a.md'), delRow('notes\\intake\\b.md'), delRow('archive\\week-changelogs\\c.md')],
    ['notes/intake'],
  );
  assert.deepEqual(rows.map((r) => r.disposition), ['PRESERVE', 'PRESERVE', 'PRESERVE']);
  const win = guard([delRow('archive/completed/x.md')], ['archive\\completed\\']);
  assert.equal(win.rows[0].disposition, 'PRESERVE', 'a backslash/trailing-separator root normalises');
});

test('intake guard: an unrecognised class or empty path fails closed to PRESERVE', () => {
  const guard = loadIntakeGuard();
  const { rows, downgraded } = guard([delRow('docs/research/x.md'), delRow('tasks/foo/spec.md'), delRow('')], []);
  assert.deepEqual(rows.map((r) => r.disposition), ['PRESERVE', 'PRESERVE', 'PRESERVE']);
  rows.forEach((r) => assert.match(r.reason, /^unrecognised-class: /));
  assert.deepEqual(downgraded.map((d) => d.why), ['unrecognised-class', 'unrecognised-class', 'unrecognised-class']);
});

test('intake guard: completion, plan and cross-repo memo rows outside the roots keep DELETE; non-DELETE rows pass untouched', () => {
  const guard = loadIntakeGuard();
  const keep = ['archive/completed/a.md', 'archive/specs/b.md', 'cross-repo/archive/c.md', 'archive\\completed\\d.md'];
  const other = [
    { artifact_path: 'archive/daily-summaries/x.md', disposition: 'SEND_BACK', reason: 'r' },
    { artifact_path: 'docs/research/y.md', disposition: 'BLOCKED', reason: 'r' },
  ];
  const { rows, downgraded } = guard([...keep.map(delRow), ...other], ['archive/daily-summaries']);
  assert.deepEqual(downgraded, []);
  assert.deepEqual(rows.slice(0, 4).map((r) => r.disposition), ['DELETE', 'DELETE', 'DELETE', 'DELETE']);
  assert.deepEqual(rows.slice(4), other);
});

const CLASS_FIXTURES = {
  'docs/plans/2026-11/x.md': 'live-plan',
  'archive/2026-10/plans/n.md': 'live-plan',
  'archive/plans/2026-10/a.md': 'plan',
  'archive/specs/b.md': 'plan',
  'archive\\specs\\b2.md': 'plan',
  'archive/completed/c.md': 'completion',
  'cross-repo/archive/m.md': 'cross-repo memo',
  'state/cross-repo/archive/2026-07/m2.md': 'cross-repo memo',
  'archive/daily-summaries/d.md': 'intake',
  'archive/release-notes/v1.md': 'intake',
  'state/week-changelog/e.md': 'triage-only',
  'docs/daily-summaries/f.md': 'triage-only',
  'archive/handoffs/h.md': 'handoff',
  'docs/research/r.md': 'unrecognised',
  '': 'unrecognised',
};

test('artifactClassOf: one classifier gives each fixture path its class, and triage and 3d both call it', () => {
  const { artifactClassOf } = new Function(`${CLASSIFIER_SRC}\nreturn { artifactClassOf }`)();
  for (const [p, cls] of Object.entries(CLASS_FIXTURES)) assert.equal(artifactClassOf(p, []), cls, p);
  assert.equal(artifactClassOf('notes/intake/a.md', ['notes/intake']), 'intake');
  assert.equal(artifactClassOf('notes/intake/a.md', []), 'unrecognised');
  for (const name of ['planPathsOf', 'enforceIntakeAndClass', 'presettleDeletionRows']) {
    assert.match(extractFunctionSource(SOURCE, name), /artifactClassOf\(/, `${name} calls artifactClassOf`);
  }
});

test('artifactClassOf: planPathsOf (triage) and enforceIntakeAndClass (3d) agree on every fixture path', () => {
  const guard = loadIntakeGuard();
  const paths = Object.keys(CLASS_FIXTURES).filter((p) => p !== '');
  const planned = new Set(triage.planPathsOf([{ batchId: 'b', files: paths }]));
  for (const p of paths) {
    const isPlan = ['plan', 'live-plan'].includes(CLASS_FIXTURES[p]);
    assert.equal(planned.has(p), isPlan, `triage: ${p}`);
    const kept = guard([delRow(p)], []).rows[0].disposition === 'DELETE';
    assert.equal(kept, ['plan', 'completion', 'cross-repo memo'].includes(CLASS_FIXTURES[p]), `3d: ${p}`);
  }
  const live = guard([delRow('docs/plans/2026-11/x.md')], []);
  assert.equal(live.rows[0].disposition, 'PRESERVE', 'a live plan is triage input, never a delete cohort');
  assert.match(live.rows[0].reason, /^live-plan: /);
  assert.equal(live.downgraded[0].why, 'live-plan');
  assert.equal(guard([delRow('state/cross-repo/archive/2026-07/m.md')], []).rows[0].disposition, 'DELETE', 'a state/ cross-repo memo is delete-eligible');
  assert.equal(guard([delRow('docs/daily-summaries/f.md')], []).downgraded[0].why, 'triage-only');
});

test('artifactClassOf: the triage-only directory set equals distill_mechanical.py _TRIAGE_ONLY_DIRS', () => {
  const py = fs.readFileSync(path.join(__dirname, '..', 'distill_mechanical.py'), 'utf8');
  const pySet = [...py.match(/_TRIAGE_ONLY_DIRS = \{([^}]*)\}/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  const jsSet = JSON.parse(SOURCE.match(/const TRIAGE_ONLY_DIRS = (\[[^\]]*\])/)[1].replace(/'/g, '"')).sort();
  assert.deepEqual(jsSet, pySet);
});

test('plan triage report: all plans prepared reports skipped-all-prepared with the admitted count; no plans stays skipped-no-plans', () => {
  const src = extractBlockSource(SOURCE, 'const TRIAGE_LOG_ROOTS',
    "  : { status: 'skipped-no-plans', admitted: 0, candidates: 0, kept: 0, dropped: 0, dropped_plans: [] }");
  const run = (batches, prepared, mech) => new Function('RAW_ARGS_INPUT', 'BATCHES', 'PREPARED_CLUSTERS', 'MECHANICAL_FILES',
    'residueBatchesOf', 'planPathsOf', 'resolveLogRoots', `${src}\nreturn PLAN_TRIAGE_REPORT`)(
    {}, batches, prepared, new Set(mech), preparedHelpers.residueBatchesOf, triage.planPathsOf, triage.resolveLogRoots);
  const plans = [{ batchId: 'b1', files: ['docs/plans/a.md', 'docs/plans/b.md'] }];
  const allPrepared = run(plans, true, ['docs/plans/a.md', 'docs/plans/b.md']);
  assert.equal(allPrepared.status, 'skipped-all-prepared');
  assert.equal(allPrepared.admitted, 2);
  assert.equal(run([{ batchId: 'b1', files: ['notes/x.md'] }], true, ['notes/x.md']).status, 'skipped-no-plans');
  assert.equal(run(plans, false, []).admitted, 2);
});

test('2.5 scout: the no-dispatch branch carries the precheck sidecars_seen, 0 only when it carries none', () => {
  const fn = new Function(`${extractFunctionSource(SOURCE, 'judgmentPrecheckSidecars')}\nreturn judgmentPrecheckSidecars`)();
  assert.equal(fn({ sidecars_seen: 368, dispatch: false, distinct_eligible_plans: 1 }), 368);
  assert.equal(fn({ sidecars_seen: 0 }), 0);
  for (const bad of [undefined, null, {}, { sidecars_seen: '368' }, { sidecars_seen: 1.5 }]) assert.equal(fn(bad), 0);
});

test('re-entry BLOCKED: every BLOCKED row that never entered a round names that no round ran, at the final merge', () => {
  const fn = new Function(`${extractFunctionSource(SOURCE, 'wordBlockedByRounds')}\nreturn wordBlockedByRounds`)();
  const rows = [
    { artifact_path: 'a.md', disposition: 'BLOCKED', reason: 'active handoff reference' },
    { artifact_path: 'x/b.md', disposition: 'BLOCKED', reason: 'cross-repo artifact' },
    { artifact_path: 'c.md', disposition: 'BLOCKED', reason: 'agent said blocked' },
    { artifact_path: 'd.md', disposition: 'BLOCKED', reason: 'un-harvestable: no send_back re-entry round ran — original reason: r' },
    { artifact_path: 'e.md', disposition: 'BLOCKED', reason: 'un-harvestable after 2 send_back re-entry round(s) — r' },
    { artifact_path: 'f.md', disposition: 'DELETE', reason: 'extracted' },
  ];
  const out = fn(rows, new Set(['c.md']));
  assert.match(out[0].reason, /^active handoff reference \(no send_back re-entry round ran for this artifact\)$/);
  assert.match(out[1].reason, /no send_back re-entry round ran/);
  assert.equal(out[2].reason, 'agent said blocked');
  assert.equal(out[3].reason, rows[3].reason);
  assert.equal(out[4].reason, rows[4].reason);
  assert.equal(out[5].reason, 'extracted');
  const cap = LIVE_CODE.indexOf('const cappedArtifactPaths');
  const norm = LIVE_CODE.indexOf('currentDeletions = wordBlockedByRounds(currentDeletions, reentryEnteredPaths)');
  assert.ok(cap > 0 && norm > cap && norm < LIVE_CODE.indexOf('enforceIntakeAndClass(currentDeletions, LOG_ROOTS'), 'normaliser sits after the cap and before the final guard');
  assert.ok(LIVE_CODE.indexOf('reentryEnteredPaths.add(row.artifact_path)') > 0, 'rows entering a round are recorded');
});

test('intake guard: wired after the provenance downgrade at build and again on the final merged manifest', () => {
  const prov = LIVE_CODE.indexOf('const enforced = enforceProvenanceCitation(deletionManifestResult.deletions)');
  const build = LIVE_CODE.indexOf('enforceIntakeAndClass(enforced.rows, LOG_ROOTS');
  assert.ok(prov > 0 && build > prov, 'build-time guard follows enforceProvenanceCitation');
  assert.match(LIVE_CODE, /deletions: \[\.\.\.phase3dSplit\.settled, \.\.\.guarded\.rows\], status: 'ran'/);
  const merge = LIVE_CODE.indexOf('...CROSS_REPO_DISPOSITIONS]');
  const repoint = LIVE_CODE.indexOf("phase('citation-repoint')");
  const final = LIVE_CODE.indexOf('enforceIntakeAndClass(currentDeletions, LOG_ROOTS');
  assert.ok(merge > 0 && repoint > merge && final > repoint, 'final guard follows merge and repoint');
  assert.ok(LIVE_CODE.indexOf('currentDeletions = finalGuard.rows') > final);
  assert.ok(LIVE_CODE.indexOf('currentDeletions = finalGuard.rows') < LIVE_CODE.indexOf('phase3d = { ...phase3d, deletions: currentDeletions }'));
});
// ---------------------------------------------------------------------------
// Meaning-match homing: one batched model call over every homeless cluster with candidates.
// ---------------------------------------------------------------------------
const meaningExtracted = new Function(`
  const DR146_MIN_STEM_LEN = ${DR146_MIN_STEM_LEN};
  const STEM_PREFIX_LEN = ${STEM_PREFIX_LEN};
  const DR146_STRIP_SUFFIXES = ['-shape', '-design', '-v2'];
  const DR146_DATE_PREFIX_RE = /^\\d{4}-\\d{2}-\\d{2}-/;
  const MEANING_MATCH_MAX_CANDIDATES = ${readConstFromSource('MEANING_MATCH_MAX_CANDIDATES')};
  const MEANING_MATCH_NUGGET_SAMPLE = ${readConstFromSource('MEANING_MATCH_NUGGET_SAMPLE')};
  const MEANING_MATCH_NUGGET_CHARS = ${readConstFromSource('MEANING_MATCH_NUGGET_CHARS')};
  const MEANING_MATCH_HEAD_LINES = ${readConstFromSource('MEANING_MATCH_HEAD_LINES')};
  const MEANING_MATCH_BATCH_MAX_CHARS = ${readConstFromSource('MEANING_MATCH_BATCH_MAX_CHARS')};
  const MEANING_MATCH_CLUSTER_MARK = ${JSON.stringify(SOURCE.match(/const\s+MEANING_MATCH_CLUSTER_MARK\s*=\s*'([^']*)'/)[1])};
  const MEANING_MATCH_PREVIEW_HEADINGS = ${readConstFromSource('MEANING_MATCH_PREVIEW_HEADINGS')};
  const MEANING_MATCH_PREVIEW_LEADS = ${readConstFromSource('MEANING_MATCH_PREVIEW_LEADS')};
  const MEANING_MATCH_PREVIEW_LEAD_CHARS = ${readConstFromSource('MEANING_MATCH_PREVIEW_LEAD_CHARS')};
  const MEANING_MATCH_STOP_WORDS = new Set(['and', 'the', 'for', 'with', 'from', 'into', 'shape', 'design', 'v2']);
  ${slugifyTopicSrc}
  ${dr146NormalizeSrc}
  ${leadingStemSrc}
  ${findFuzzyWikiHomeSrc}
  ${consolidateClustersSrc}
  ${extractFunctionSource(SOURCE, 'meaningWords')}
  ${extractFunctionSource(SOURCE, 'meaningWordsMatch')}
  ${extractFunctionSource(SOURCE, 'meaningMatchCandidates')}
  ${extractFunctionSource(SOURCE, 'meaningMatchBrief')}
  ${extractFunctionSource(SOURCE, 'nuggetCitations')}
  ${extractFunctionSource(SOURCE, 'homelessClusters')}
  async ${extractFunctionSource(SOURCE, 'homeByMeaning')}
  return { consolidateClusters, meaningWords, meaningMatchCandidates, meaningMatchBrief, homeByMeaning };
`)();

// Most homing tests answer per cluster: this adapter splits the batched brief at its CLUSTER marks, asks the
// per-cluster mock once per cluster (label `homing-<slug>`, `-retry` on the retry call) and folds the replies
// into the batched {answers} shape. A mock reply of null or a non-object leaves that cluster without an entry.
const homeByMeaningBatched = meaningExtracted.homeByMeaning;
const perClusterAsk = (ask) => async (brief, label) => {
  const answers = [];
  for (const part of brief.split(/^=== CLUSTER /m).slice(1)) {
    const at = part.indexOf(' ===\n');
    const slug = part.slice(0, at);
    const reply = await ask(part.slice(at + 5).trim(), `homing-${slug}${/-retry$/.test(label) ? '-retry' : ''}`);
    if (reply && typeof reply === 'object') answers.push({ ...reply, slug });
  }
  return { answers };
};
meaningExtracted.homeByMeaning = (raw, wiki, dirs, ask, logFn, matches) => homeByMeaningBatched(raw, wiki, dirs, perClusterAsk(ask), logFn, matches);

const MEANING_WIKI = {
  'embedding-model-selection': 'docs/wiki/embedding-model-selection.md',
  'example-studio-claim-projection': 'docs/wiki/example-studio-claim-projection.md',
  'cross-repo-communication-project-rag-scoped': 'docs/wiki/cross-repo/cross-repo-communication-project-rag-scoped.md',
  'cross-repo-memos': 'docs/wiki/cross-repo/cross-repo-memos.md',
  'unrelated-topic': 'docs/wiki/unrelated-topic.md',
};
const meaningCluster = (topicKey) => ({ topicKey, nuggets: [{ id: `${topicKey}-1`, content: `nugget about ${topicKey}` }], sourceBatches: ['b0'] });

test('meaning candidates: slug stems and wiki directory names qualify; nothing else does', () => {
  const c = meaningExtracted.meaningMatchCandidates;
  assert.deepEqual(c('embed', MEANING_WIKI, ['docs/wiki']).map((x) => x.path), ['docs/wiki/embedding-model-selection.md']);
  assert.equal(c('coordination-claim-projection', MEANING_WIKI, ['docs/wiki'])[0].path, 'docs/wiki/example-studio-claim-projection.md', 'the page sharing the most words ranks first');
  const comms = c('cross-repo-comms', MEANING_WIKI, ['docs/wiki']).map((x) => x.path);
  assert.deepEqual(comms.sort(), ['docs/wiki/cross-repo/cross-repo-communication-project-rag-scoped.md', 'docs/wiki/cross-repo/cross-repo-memos.md']);
  assert.deepEqual(c('windows-install-surface', MEANING_WIKI, ['docs/wiki']), []);
  // a directory-name match alone qualifies the pages under it
  assert.deepEqual(c('repo-hygiene', { 'memo-index': 'docs/wiki/repo/memo-index.md' }, ['docs/wiki']).map((x) => x.path), ['docs/wiki/repo/memo-index.md']);
});

test('meaning candidates: capped, and the brief carries bounded previews, never whole bodies', () => {
  const many = Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`claim-page-${i}`, `docs/wiki/claim-page-${i}.md`]));
  assert.equal(meaningExtracted.meaningMatchCandidates('claim-thing', many, ['docs/wiki']).length, 8);
  const brief = meaningExtracted.meaningMatchBrief('embed', meaningCluster('embed'), [{ slug: 'x', path: 'docs/wiki/x.md' }]);
  assert.match(brief, /docs\/wiki\/x\.md/);
  assert.match(brief, /limit=12/);
  assert.doesNotMatch(brief, /headings:|bullets:/, 'no facts: path-only line');

  const pf = {
    'docs/wiki/x.md': {
      headings: Array.from({ length: 20 }, (_, i) => `Heading ${i}`),
      bullet_leads: Array.from({ length: 20 }, (_, i) => `lead${i} ` + 'w'.repeat(200)),
    },
  };
  const rich = meaningExtracted.meaningMatchBrief('embed', meaningCluster('embed'),
    [{ slug: 'x', path: 'docs/wiki/x.md' }, { slug: 'y', path: 'docs/wiki/y.md' }], pf);
  assert.match(rich, /headings: Heading 0 \| Heading 1/);
  assert.match(rich, /Heading 7\b/);
  assert.doesNotMatch(rich, /Heading 8\b/, 'headings capped');
  assert.match(rich, /lead7 /);
  assert.doesNotMatch(rich, /lead8 /, 'bullet leads capped');
  assert.doesNotMatch(rich, /w{61}/, 'each lead truncated');
  assert.match(rich, /- docs\/wiki\/y\.md\n/, 'a candidate without facts keeps the path-only line');
  assert.match(rich, /limit=12/, 'Read-head instruction kept for factless candidates');
});

const citedExtracted = new Function(`
  ${extractFunctionSource(SOURCE, 'nuggetCitations')}
  return { nuggetCitations };
`)();

const citedCluster = (nuggets) => ({ topicKey: 'topic', nuggets });

test('cited-record matcher: nuggetCitations collects sources, normalised DR refs and backticked spans', () => {
  const c = citedExtracted.nuggetCitations(citedCluster([
    { source: 'docs\\plans\\a.md', content: 'See docs/decisions/DR-0127-x.md and DR-0127, also DR-9; uses `foo_bar` and `a b`, not `x`.' },
    { source: 'docs/plans/a.md', content: 'again `foo_bar`' },
  ]));
  assert.deepEqual(c.sources, ['docs/plans/a.md']);
  assert.deepEqual(c.drRefs, ['docs/decisions/DR-0127-x.md', 'DR-127', 'DR-9']);
  assert.deepEqual(c.symbols, ['foo_bar', 'a b']);
});

// Runs WIKI_PAGE_FACTS_PY over real markdown files under <tmp>/wiki for one cluster's citations (slug 't');
// returns {hits, previews, stdout} parsed from the single FACTS line.
function pageMatchesOver(files, cluster, candidates = [], cap = '16000', sourcePages = '2') {
  const cited = citedExtracted.nuggetCitations(cluster);
  const spec = { t: { s: cited.sources, d: cited.drRefs, y: cited.symbols, c: candidates } };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'page-facts-'));
  try {
    for (const [rel, body] of Object.entries(files)) {
      fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
      fs.writeFileSync(path.join(dir, rel), body);
    }
    const py = new Function(`${SOURCE.match(/const WIKI_PAGE_FACTS_PY = \[[\s\S]*?\n\]\.join\('\\n'\)/)[0]}\nreturn WIKI_PAGE_FACTS_PY;`)();
    const r = cp.spawnSync('python3', ['-c', py, JSON.stringify(spec), '8', '8', '8', cap, sourcePages, 'wiki'], { cwd: dir, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    const lines = r.stdout.split('\n').filter(Boolean);
    assert.equal(lines.length, 1, 'one stdout line');
    const m = /^FACTS (\{.*\})$/.exec(lines[0]);
    assert.ok(m, r.stdout);
    const parsed = JSON.parse(m[1]);
    return { hits: parsed.h.t, previews: parsed.p, stdout: r.stdout };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
const mdPage = ({ prov, body = '' } = {}) => (prov ? `---\ntitle: T\nprovenance:\n  - archived_spec: ${prov}\n---\n` : '') + body;





test('meaning homing: a meaning-match reply homes the cluster to the existing page and no NEW page is minted', async () => {
  const calls = [];
  const raw = [meaningCluster('embed'), meaningCluster('coordination-claim-projection')];
  const { meaningHomes, calls: n } = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async (brief, label) => {
    calls.push(label);
    return { home: label === 'homing-embed' ? 'docs/wiki/embedding-model-selection.md' : 'NEW', reason: 'same subject' };
  }, () => {});
  assert.equal(n, 1, 'both clusters ride one batched call');
  assert.deepEqual(meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' });
  const result = meaningExtracted.consolidateClusters(raw, MEANING_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes });
  const byKey = Object.fromEntries(result.map((c) => [c.topicKey, c]));
  assert.equal(byKey.embed.bucket, 'homed');
  assert.equal(byKey.embed.wikiPath, 'docs/wiki/embedding-model-selection.md');
  assert.equal(byKey['coordination-claim-projection'].bucket, 'new', 'a declined match still mints as before');
});

test('meaning homing: no candidate or an existing slug home makes no call; a bad or throwing reply mints as before', async () => {
  let asked = 0;
  const ask = async () => { asked++; return { home: 'docs/wiki/not-a-candidate.md' }; };
  const none = await meaningExtracted.homeByMeaning([meaningCluster('windows-install-surface'), meaningCluster('unrelated-topic')], MEANING_WIKI, ['docs/wiki'], ask, () => {});
  assert.equal(asked, 0);
  assert.equal(none.calls, 0);
  const bad = await meaningExtracted.homeByMeaning([meaningCluster('embed')], MEANING_WIKI, ['docs/wiki'], ask, () => {});
  assert.equal(asked, 2, 'an unresolvable reply is retried once');
  assert.deepEqual(bad.meaningHomes, {}, 'a path outside the candidates is never trusted');
  assert.deepEqual(bad.failed.map((f) => f.slug), ['embed'], 'and reported as a failed check');
  const thrown = await meaningExtracted.homeByMeaning([meaningCluster('embed')], MEANING_WIKI, ['docs/wiki'], async () => { throw new Error('boom'); }, () => {});
  assert.deepEqual(thrown.meaningHomes, {});
});

const uncitedCluster = (topicKey, type = 'KNOWLEDGE', content = 'a plain lesson with no references') =>
  ({ topicKey, nuggets: [{ id: `${topicKey}-1`, type, source: 'docs/plans/x.md', content }], sourceBatches: ['b0'] });

test('meaning homing: an uncited all-KNOWLEDGE cluster is forced onto a candidate as a gotcha append, never minted', async () => {
  const briefs = [];
  const replies = [{ home: 'NEW' }, { home: 'docs/wiki/not-a-candidate.md' }, null];
  for (const reply of replies) {
    const raw = [uncitedCluster('embed')];
    const r = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async (brief) => {
      briefs.push(brief);
      if (reply === null) throw new Error('boom');
      return reply;
    }, () => {});
    assert.deepEqual(r.meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' });
    assert.deepEqual(r.gotcha, ['embed']);
    assert.equal(r.failed.length, reply && reply.home === 'NEW' ? 0 : 1, 'a failed check is reported even when forced');
    const merged = meaningExtracted.consolidateClusters(raw, MEANING_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes: r.meaningHomes, gotchaSlugs: r.gotcha });
    assert.equal(merged[0].bucket, 'homed');
    assert.deepEqual(merged[0].gotchaNuggetIds, ['embed-1']);
  }
  assert.match(briefs[0], /"NEW" is not an option/);
  assert.doesNotMatch(briefs[0], /return "NEW" in "home"/);
  const ok = await meaningExtracted.homeByMeaning([uncitedCluster('embed')], MEANING_WIKI, ['docs/wiki'],
    async () => ({ home: 'docs/wiki/embedding-model-selection.md' }), () => {});
  assert.deepEqual(ok.gotcha, ['embed'], 'a resolved reply is a gotcha append too');
});

test('meaning homing: a cited, mixed-kind or candidate-less cluster keeps its NEW option and mints', async () => {
  const ask = async (brief) => { askedBriefs.push(brief); return { home: 'NEW' }; };
  const askedBriefs = [];
  const cited = uncitedCluster('embed', 'KNOWLEDGE', 'uses `some_symbol` here');
  const decision = uncitedCluster('embed', 'DECISION');
  const mixed = { ...uncitedCluster('embed'), nuggets: [...uncitedCluster('embed').nuggets, ...uncitedCluster('embed', 'EPHEMERAL').nuggets] };
  for (const cluster of [cited, decision, mixed]) {
    const r = await meaningExtracted.homeByMeaning([cluster], MEANING_WIKI, ['docs/wiki'], ask, () => {});
    assert.deepEqual(r.meaningHomes, {});
    assert.deepEqual(r.gotcha, []);
  }
  assert.equal(askedBriefs.length, 3);
  for (const b of askedBriefs) assert.match(b, /return "NEW" in "home"/);
  const none = await meaningExtracted.homeByMeaning([uncitedCluster('windows-install-surface')], MEANING_WIKI, ['docs/wiki'], ask, () => {});
  assert.equal(askedBriefs.length, 3, 'no candidates: no call');
  assert.deepEqual(none.meaningHomes, {});
  assert.deepEqual(none.gotcha, []);
  const raw = [uncitedCluster('windows-install-surface')];
  assert.equal(meaningExtracted.consolidateClusters(raw, MEANING_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes: {}, gotchaSlugs: [] })[0].bucket, 'new');
});

test('meaning homing: N>1 jobs make exactly one ask; each cluster is resolved on its own entry', async () => {
  const wiki = Object.fromEntries(Array.from({ length: 5 }, (_, i) => [`claim-page-${i}`, `docs/wiki/claim-page-${i}.md`]));
  const raw = Array.from({ length: 11 }, (_, i) => meaningCluster(`claim-topic-${i}`));
  const briefs = [];
  const r = await homeByMeaningBatched(raw, wiki, ['docs/wiki'], async (brief, label) => {
    briefs.push({ brief, label });
    return { answers: raw.map((c, i) => ({ slug: c.topicKey, home: i % 2 ? 'NEW' : 'docs/wiki/claim-page-2.md', reason: 'r' })) };
  }, () => {});
  assert.equal(briefs.length, 1, 'one ask for 11 clusters');
  assert.equal(r.calls, 1);
  for (const c of raw) assert.ok(briefs[0].brief.includes(`=== CLUSTER ${c.topicKey} ===`), `${c.topicKey} is in the batched brief`);
  assert.deepEqual(Object.keys(r.meaningHomes).sort(), raw.filter((_, i) => i % 2 === 0).map((c) => c.topicKey).sort());
  assert.deepEqual(r.failed, []);
});

test('meaning homing: a missing or unresolvable entry fails only its own cluster, retried once with just the unresolved ones', async () => {
  const wiki = { 'claim-page': 'docs/wiki/claim-page.md' };
  const raw = ['claim-a', 'claim-b', 'claim-c'].map(meaningCluster);
  const asks = [];
  const r = await homeByMeaningBatched(raw, wiki, ['docs/wiki'], async (brief, label) => {
    asks.push({ brief, label });
    return { answers: [{ slug: 'claim-a', home: 'docs/wiki/claim-page.md' }, { slug: 'claim-b', home: 'docs/wiki/elsewhere.md' }] };
  }, () => {});
  assert.equal(asks.length, 2);
  assert.match(asks[1].label, /-retry$/);
  assert.ok(!asks[1].brief.includes('=== CLUSTER claim-a ==='), 'a resolved cluster is not re-asked');
  assert.ok(asks[1].brief.includes('=== CLUSTER claim-b ===') && asks[1].brief.includes('=== CLUSTER claim-c ==='));
  assert.deepEqual(r.meaningHomes, { 'claim-a': 'docs/wiki/claim-page.md' });
  assert.deepEqual(r.failed.map((f) => [f.slug, f.reason]), [['claim-b', "reply named 'docs/wiki/elsewhere.md', not a candidate"], ['claim-c', 'no entry in reply']]);
  const thrown = await homeByMeaningBatched(raw, wiki, ['docs/wiki'], async () => { throw new Error('boom'); }, () => {});
  assert.equal(thrown.calls, 2, 'a thrown batch is retried once as a whole');
  assert.deepEqual(thrown.failed.map((f) => f.slug), ['claim-a', 'claim-b', 'claim-c']);
});

test('meaning homing: forced clusters in a batch default to candidate 0 as gotcha, NEW stays withheld from their section only', async () => {
  const raw = [uncitedCluster('embed'), meaningCluster('coordination-claim-projection')];
  let brief = '';
  const r = await homeByMeaningBatched(raw, MEANING_WIKI, ['docs/wiki'], async (b) => { brief = b; return { answers: [] }; }, () => {});
  assert.deepEqual(r.meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' }, 'the forced cluster homes on candidate 0');
  assert.deepEqual(r.gotcha, ['embed']);
  assert.deepEqual(r.failed.map((f) => f.slug), ['embed', 'coordination-claim-projection']);
  const [forcedPart, freePart] = brief.split(/^=== CLUSTER /m).slice(1);
  assert.match(forcedPart, /"NEW" is not an option/);
  assert.doesNotMatch(forcedPart, /return "NEW" in "home"/);
  assert.match(freePart, /return "NEW" in "home"/);
});

test('meaning homing: briefs past the batch cap split into further calls, greedily in order', async () => {
  const cap = readConstFromSource('MEANING_MATCH_BATCH_MAX_CHARS');
  const wiki = { 'claim-page': 'docs/wiki/claim-page.md' };
  const cand = [{ slug: 'claim-page', path: 'docs/wiki/claim-page.md' }];
  const one = meaningExtracted.meaningMatchBrief('claim-topic-000', meaningCluster('claim-topic-000'), cand).length;
  const raw = Array.from({ length: Math.ceil(cap / one) + 5 }, (_, i) => meaningCluster(`claim-topic-${String(i).padStart(3, '0')}`));
  const briefs = [];
  const r = await homeByMeaningBatched(raw, wiki, ['docs/wiki'], async (brief, label) => {
    briefs.push({ brief, label });
    return { answers: [...brief.matchAll(/^=== CLUSTER (.+) ===$/gm)].map((m) => ({ slug: m[1], home: 'NEW' })) };
  }, () => {});
  assert.deepEqual(briefs.map((b) => b.label), ['homing-batch-1', 'homing-batch-2']);
  assert.ok(briefs.every((b) => b.brief.length <= cap + 1000), 'a batch stays near the cap');
  assert.equal(briefs.map((b) => (b.brief.match(/^=== CLUSTER /gm) || []).length).reduce((a, b) => a + b), raw.length, 'every cluster is asked exactly once');
  assert.equal(r.calls, 2);
  assert.deepEqual(r.failed, []);
});

test('meaning words: the singularizer keeps -us/-ss/-is words whole and still pairs plurals', () => {
  assert.deepEqual(meaningExtracted.meaningWords('status-claims-policies'), ['status', 'claim', 'policy']);
});

test('meaning homing is wired ahead of consolidateClusters with a modeled agent call', () => {
  const at = SOURCE.indexOf('await homeByMeaning(');
  assert.ok(at > 0 && at < SOURCE.indexOf('const allClusters = PREPARED_CLUSTERS'));
  assert.match(SOURCE.slice(at, at + 400), /agent\(brief, \{[\s\S]*model: 'haiku'/);
  assert.match(SOURCE, /meaningHomes: MEANING_HOMES/);
});

// R2 acceptance fixtures: duplicates whose existing page sits in a docs/wiki subdirectory.
const R2_WIKI = {
  'envelope-version': 'docs/wiki/mcp-tools/envelope-version.md',
  'encrypted-store-codec': 'docs/wiki/storage-backend/encrypted-store-codec.md',
  'er-suggestion': 'docs/wiki/er-suggestion.md',
  'zero-bash': 'docs/wiki/zero-bash.md',
  'unrelated-topic': 'docs/wiki/unrelated-topic.md',
};
const R2_PAIRS = [
  ['envelope-protocol', 'docs/wiki/mcp-tools/envelope-version.md'],
  ['encrypted-store', 'docs/wiki/storage-backend/encrypted-store-codec.md'],
  ['er-suggest', 'docs/wiki/er-suggestion.md'],
  ['debash-migration', 'docs/wiki/zero-bash.md'],
];

test('R2 pairs: each new slug gathers its subdirectory/near-name page as a candidate and homes there on a match', async () => {
  for (const [slug, path] of R2_PAIRS) {
    const cands = meaningExtracted.meaningMatchCandidates(slug, R2_WIKI, ['docs/wiki']).map((x) => x.path);
    assert.ok(cands.includes(path), `${slug} must gather ${path}, got ${cands}`);
    assert.ok(!cands.includes('docs/wiki/unrelated-topic.md'));
  }
  const raw = R2_PAIRS.map(([slug]) => meaningCluster(slug));
  const answers = Object.fromEntries(R2_PAIRS.map(([slug, path]) => [`homing-${slug}`, path]));
  const { meaningHomes, calls } = await meaningExtracted.homeByMeaning(raw, R2_WIKI, ['docs/wiki'], async (brief, label) => ({ home: answers[label], reason: 'same subject' }), () => {});
  // encrypted-store is already homed script-side by the leading-slug rule: no model call spent on it
  assert.equal(calls, 1);
  assert.deepEqual(meaningHomes, Object.fromEntries(R2_PAIRS.filter(([s]) => s !== 'encrypted-store')));
  const result = meaningExtracted.consolidateClusters(raw, R2_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes });
  for (const c of result) {
    assert.equal(c.bucket, 'homed', c.topicKey);
    assert.equal(c.wikiPath, Object.fromEntries(R2_PAIRS)[c.topicKey]);
  }
  // declined: the same four still mint NEW pages
  const declined = await meaningExtracted.homeByMeaning(raw, R2_WIKI, ['docs/wiki'], async () => ({ home: 'NEW' }), () => {});
  assert.deepEqual(declined.meaningHomes, {});
  const byKey = Object.fromEntries(meaningExtracted.consolidateClusters(raw, R2_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes: declined.meaningHomes }).map((c) => [c.topicKey, c.bucket]));
  assert.deepEqual(byKey, { 'envelope-protocol': 'new', 'encrypted-store': 'homed', 'er-suggest': 'new', 'debash-migration': 'new' });
});

test('synth brief: no pipeline, run or sha prose, additions only, restatements add nothing', () => {
  const brief = extractFunctionSource(SOURCE, 'synthBriefFor').replace(/`\s*\+\s*`/g, '').replace(/\s+/g, ' ');
  assert.match(brief, /no run, nugget or pipeline references, no commit shas/);
  assert.match(brief, /A nugget that restates a sentence the outline shows adds nothing/);
});

test('12h42: absolute or slug replies resolve; an empty reply is retried then reported; NEW declines without retry', async () => {
  const raw = [meaningCluster('embed')];
  const abs = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async () => ({ home: '/srv/x/repo/docs/wiki/embedding-model-selection.md' }), () => {});
  assert.deepEqual(abs.meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' });
  const bySlug = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async () => ({ home: 'embedding-model-selection' }), () => {});
  assert.deepEqual(bySlug.meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' });
  let n = 0;
  const empty = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async () => { n++; return { home: n === 1 ? '' : 'docs/wiki/embedding-model-selection.md' }; }, () => {});
  assert.equal(n, 2);
  assert.deepEqual(empty.meaningHomes, { embed: 'docs/wiki/embedding-model-selection.md' }, 'the retry answers');
  let m = 0;
  const declined = await meaningExtracted.homeByMeaning(raw, MEANING_WIKI, ['docs/wiki'], async () => { m++; return { home: 'NEW' }; }, () => {});
  assert.equal(m, 1);
  assert.deepEqual(declined.failed, []);
});

test('12h42: a rare shared word outranks a common one inside the cap; encryption pairs with encrypted', () => {
  const wiki = Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`step-${i}-migration`, `docs/wiki/step-${i}-migration.md`]));
  wiki['zero-bash'] = 'docs/wiki/zero-bash.md';
  const c = meaningExtracted.meaningMatchCandidates('de-bash-migration', wiki, ['docs/wiki']);
  assert.equal(c[0].path, 'docs/wiki/zero-bash.md');
  const enc = meaningExtracted.meaningMatchCandidates('encryption-at-rest', { 'encrypted-store-codec-scope': 'docs/wiki/storage-backend/encrypted-store-codec-scope.md' }, ['docs/wiki']);
  assert.deepEqual(enc.map((x) => x.path), ['docs/wiki/storage-backend/encrypted-store-codec-scope.md']);
});

test('synth brief: states the op contract, forbids tool use, and carries the decision-record and new-page rules', () => {
  const synthBriefFor = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; ${extractFunctionSource(SOURCE, 'synthBriefFor')}; return synthBriefFor;`)();
  const brief = synthBriefFor({ topics: [{ topic_key: 'alpha-topic', nuggets: [] }] }).replace(/\s+/g, ' ');
  for (const rule of [
    'You have no tools: do not read, search or run anything.',
    "action 'append' adds markdown under a heading already in the topic's outline; 'new_section' adds a heading.",
    'cites lists the ids of the nuggets the markdown rests on',
    'at most 120 lines of markdown per topic',
    'no "was once", "superseded" or was-X-now-Y prose',
    'an op naming a path absent there is rejected.',
    "is one of that topic's cite_ids",
    "no_ops_reason: 'nothing-new-vs-page'",
    "'all-nuggets-duplicate'",
    "'insufficient-substance'",
    'finalize scaffolds its title and nav',
    'finalize mints the record and allocates its number, never you',
    'Payload:',
  ]) assert.ok(brief.includes(rule), `brief lacks: ${rule}`);
});

test('synth: a stale-code-state return is counted as that reason, not unreasoned; the brief carries the stale rule', () => {
  const synthOutcomeOf = new Function(
    `${extractFunctionSource(SOURCE, 'slugifyTopic')}; ${extractFunctionSource(SOURCE, 'sameTopic')}; ` +
    `${extractFunctionSource(SOURCE, 'synthUnitsOf')}; ${extractFunctionSource(SOURCE, 'unitSlugOfCluster')}; ` +
    `${extractFunctionSource(SOURCE, 'synthOutcomeOf')}; return synthOutcomeOf;`)();
  const clusters = [{ topicKey: 'topic-0', nuggets: [{ id: 'n0' }] }];
  const payloads = [{ topics: [{ topic_key: 'topic-0', nuggets: [{ id: 'n0' }], cite_ids: ['n0'] }] }];
  const results = [{ topic_key: 'topic-0', op: 'skipped', dispositions: [] }];
  const stale = synthOutcomeOf(clusters, results, payloads, [{ topics: [{ topic_key: 'topic-0', ops: [], no_ops_reason: 'stale-code-state' }] }]);
  assert.equal(stale.no_ops_reasons['topic-0'], 'stale-code-state');
  const bad = synthOutcomeOf(clusters, results, payloads, [{ topics: [{ topic_key: 'topic-0', ops: [], no_ops_reason: 'stale' }] }]);
  assert.equal(bad.no_ops_reasons['topic-0'], 'unreasoned', 'an unlisted code is still refused');
  const synthBriefFor = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; ${extractFunctionSource(SOURCE, 'synthBriefFor')}; return synthBriefFor;`)();
  const brief = synthBriefFor({ topics: [{ topic_key: 'alpha-topic', nuggets: [] }] }).replace(/\s+/g, ' ');
  for (const rule of ['stale_code_state true', 'never as a present-tense claim about code', "no_ops_reason 'stale-code-state'"]) {
    assert.ok(brief.includes(rule), `brief lacks: ${rule}`);
  }
});

test('synth: the brief asks for nugget_reasons, and a JUDGED or uncited disposition never lands a nugget', () => {
  const synthBriefFor = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; ${extractFunctionSource(SOURCE, 'synthBriefFor')}; return synthBriefFor;`)();
  const brief = synthBriefFor({ topics: [{ topic_key: 'alpha-topic', nuggets: [] }] }).replace(/\s+/g, ' ');
  for (const rule of ['nugget_reasons[] entry', '{nugget_id, reason}', 'page_title']) {
    assert.ok(brief.includes(rule), `brief lacks: ${rule}`);
  }
  const derive = new Function(
    `${extractFunctionSource(SOURCE, 'slugifyTopic')}; ${extractFunctionSource(SOURCE, 'sameTopic')}; ` +
    `${extractFunctionSource(SOURCE, 'synthUnitsOf')}; ${extractFunctionSource(SOURCE, 'unitSlugOfCluster')}; ` +
    `${extractFunctionSource(SOURCE, 'deriveSynthResults')}; return deriveSynthResults;`)();
  const clusters = [{ topicKey: 'topic-0', wikiPath: 'w.md', nuggets: [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }] }];
  const returns = [{ topics: [{ topic_key: 'topic-0', ops: [{ cites: ['a', 'b', 'c', 'd'] }],
    nugget_reasons: [{ nugget_id: 'b', reason: 'stale-code-state' }] }] }];
  const out = derive(clusters, returns, [], 'r', (c) => c.wikiPath, {
    spliced: ['topic-0'],
    dispositions: [{ nugget_id: 'a', disposition: 'ADD_SECTION' }, { nugget_id: 'b', disposition: 'JUDGED:stale-code-state' },
      { nugget_id: 'c', disposition: 'uncited' }, { nugget_id: 'd', disposition: 'CREATE_DR' }],
  });
  assert.deepEqual(out[0].dispositions.map((d) => d.nugget_id), ['a', 'd']);
});

test('synth brief: a pinned-contract nugget is substance, a historical nugget lands only as a dated note', () => {
  const synthBriefFor = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; ${extractFunctionSource(SOURCE, 'synthBriefFor')}; return synthBriefFor;`)();
  const design = { id: 'n1', type: 'KNOWLEDGE', text: 'UNRESOLVED_INCLUDE_REASONS is a closed vocabulary (pkg/inc.py:41)', cite: 'p.md', historical: true };
  const brief = synthBriefFor({ topics: [{ topic_key: 'include-contract', wiki_path: 'docs/wiki/include-contract.md', nuggets: [design], cite_ids: ['n1'] }] }).replace(/\s+/g, ' ');
  assert.ok(brief.includes('UNRESOLVED_INCLUDE_REASONS'), 'the brief carries the pinned-contract example');
  assert.ok(brief.includes("is substance: write its rule, never 'insufficient-substance'"));
  assert.ok(brief.includes('A nugget with historical true'));
  assert.ok(brief.includes('never in present tense'));
  assert.ok(brief.includes('"historical":true'), 'the historical field rides the payload');
});

test('judgeOnlyPayload: a flagless nugget-* topic is judge-only; a plain topic keeps its page target', () => {
  const judgeOnlyPayload = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; return judgeOnlyPayload;`)();
  const out = judgeOnlyPayload({ topics: [
    { topic_key: 'nugget-batch-1-001-03', wiki_path: 'docs/wiki/nugget-batch-1-001-03.md', new_page: true, outline: { headings: [] }, nuggets: [{ id: 'a' }, { id: 'b' }], cite_ids: ['a', 'b'] },
    { topic_key: 'nugget-batch-1-004-01', per_nugget: true, wiki_path: 'w.md', nuggets: [{ id: 'c' }], cite_ids: ['c'] },
    { topic_key: 'alpha-topic', wiki_path: 'docs/wiki/alpha-topic.md', new_page: false, nuggets: [{ id: 'd' }], cite_ids: ['d'] },
  ] });
  for (const t of out.topics.slice(0, 2)) {
    assert.equal(t.judge_only, true);
    assert.ok(!('wiki_path' in t) && !('new_page' in t) && !('outline' in t) && !('per_nugget' in t));
  }
  assert.deepEqual(out.topics[0].cite_ids, ['a', 'b']);
  assert.equal(out.topics[2].wiki_path, 'docs/wiki/alpha-topic.md');
  assert.ok(!('judge_only' in out.topics[2]));
});

const synthUnitFns = () => [
  'slugifyTopic', 'sameTopic', 'synthUnitsOf', 'unitSlugOfCluster', 'deriveSynthResults', 'synthOutcomeOf', 'judgeOnlyPayload', 'synthBriefFor',
].map((name) => extractFunctionSource(SOURCE, name)).join('\n');
const synthUnitHarness = () => new Function(`${synthUnitFns()}; return { deriveSynthResults, synthOutcomeOf, judgeOnlyPayload, synthBriefFor };`)();

// r7b: prepare sent one batch-keyed judge-only topic holding 14 nuggets (13 per-nugget clusters behind it).
const r7bFixture = () => {
  const ids = Array.from({ length: 14 }, (_, i) => `batch-1-${String(Math.floor(i / 2) + 1).padStart(3, '0')}-0${(i % 2) + 1}`);
  const clusters = ids.map((id, i) => ({
    topicKey: `nugget-${id}`, per_nugget: true, wikiPath: `docs/wiki/${i}.md`, nuggets: [{ id }],
  }));
  clusters[1].nuggets.push({ id: 'batch-1-099-01' });
  const unitIds = [...ids, 'batch-1-099-01'].slice(0, 14);
  const payloads = [{ topics: [{ topic_key: 'nugget-batch-1', judge_only: true,
    nuggets: unitIds.map((id) => ({ id })), cite_ids: unitIds }] }];
  return { clusters, payloads, unitIds };
};

test('synth units: a prepared topic of N nuggets reaches synth as one topic with the same key, never per-nugget keys', () => {
  const { synthBriefFor, judgeOnlyPayload } = synthUnitHarness();
  const { payloads, unitIds } = r7bFixture();
  const out = judgeOnlyPayload(payloads[0]);
  assert.equal(out.topics.length, 1);
  assert.equal(out.topics[0].topic_key, 'nugget-batch-1');
  assert.equal(out.topics[0].judge_only, true);
  assert.deepEqual(out.topics[0].cite_ids, unitIds);
  const brief = synthBriefFor(payloads[0]);
  const sent = JSON.parse(brief.slice(brief.indexOf('Payload:\n') + 'Payload:\n'.length));
  assert.deepEqual(sent.topics.map((t) => t.topic_key), ['nugget-batch-1']);
  assert.ok(!/nugget-batch-\d+-\d{3}-\d{2}/.test(JSON.stringify(sent.topics.map((t) => t.topic_key))), 'no per-nugget topic_key in the brief');
});

test('synth units: reasons returned for the batch topic count against that one unit, not the 13 clusters behind it', () => {
  const { synthOutcomeOf } = synthUnitHarness();
  const { clusters, payloads, unitIds } = r7bFixture();
  const returns = [{ topics: [{ topic_key: 'nugget-batch-1', ops: [], nugget_reasons: unitIds.map((id) => ({ nugget_id: id, reason: 'nothing-new-vs-page' })) }] }];
  const out = synthOutcomeOf(clusters, [], payloads, returns);
  assert.equal(out.topics_sent, 1);
  assert.equal(out.assigned, 14);
});

test('synthOutcomeOf: topics_with_ops counts a topic only when a return carries an op or a decision record for it', () => {
  const { synthOutcomeOf } = synthUnitHarness();
  const { clusters, payloads } = r7bFixture();
  const none = synthOutcomeOf(clusters, [], payloads, [{ topics: [{ topic_key: 'nugget-batch-1', ops: [], no_ops_reason: 'insufficient-substance' }] }]);
  assert.equal(none.topics_with_ops, 0);
  assert.deepEqual(none.no_ops_topic_keys, ['nugget-batch-1']);
  assert.equal(none.no_ops_reasons['nugget-batch-1'], 'insufficient-substance');
  const unnamed = synthOutcomeOf(clusters, [], payloads, []);
  assert.equal(unnamed.topics_with_ops, 0);
  assert.equal(unnamed.no_ops_reasons['nugget-batch-1'], 'dropped');
  const op = { section_heading: 'H', action: 'append', markdown: 'm', cites: ['batch-1-001-01'] };
  assert.equal(synthOutcomeOf(clusters, [], payloads, [{ topics: [{ topic_key: 'nugget-batch-1', ops: [op] }] }]).topics_with_ops, 1);
  const dr = { nugget_id: 'batch-1-001-01', cites: ['batch-1-001-01'] };
  assert.equal(synthOutcomeOf(clusters, [], payloads, [{ topics: [{ topic_key: 'nugget-batch-1', ops: [], decision_records: [dr] }] }]).topics_with_ops, 1);
});

test('deriveSynthResults: a per-nugget cluster takes its disposition from the batch unit that carried it', () => {
  const { deriveSynthResults } = synthUnitHarness();
  const { clusters, payloads } = r7bFixture();
  const dr = { nugget_id: 'batch-1-001-01', cites: ['batch-1-001-01'] };
  const out = deriveSynthResults(clusters, [{ topics: [{ topic_key: 'nugget-batch-1', ops: [], decision_records: [dr] }] }],
    payloads, 'r', (c) => c.wikiPath, null);
  assert.equal(out.length, clusters.length);
  assert.deepEqual(out[0].dispositions.map((d) => d.nugget_id), ['batch-1-001-01']);
  assert.ok(out.slice(1).every((r) => r.dispositions.length === 0 && r.op === 'skipped'));
});

const CITED_WIKI = {
  'example-studio-claim-projection': 'docs/wiki/example-studio-claim-projection.md',
  'claim-routing': 'docs/wiki/claim-routing.md',
  'unrelated-topic': 'docs/wiki/unrelated-topic.md',
};
const citedRaw = (topicKey, nuggets) => ({ topicKey, nuggets, sourceBatches: ['b0'] });

test('cited-record homing: a single page hit homes with zero meaning-match calls', async () => {
  const raw = [citedRaw('coordination-claim-projection', [{ id: 'n1', source: 'docs/plans/a.md', content: 'see docs/decisions/DR-0042-x.md' }])];
  const pageFacts = { homes: { 'coordination-claim-projection': ['docs/wiki/example-studio-claim-projection.md'] }, previews: {} };
  const logs = [];
  let asked = 0;
  const r = await meaningExtracted.homeByMeaning(raw, CITED_WIKI, ['docs/wiki'], async () => { asked++; return { home: 'NEW' }; }, (l) => logs.push(l), pageFacts);
  assert.equal(asked, 0);
  assert.equal(r.calls, 0);
  assert.equal(r.cited, 1);
  assert.deepEqual(r.meaningHomes, { 'coordination-claim-projection': 'docs/wiki/example-studio-claim-projection.md' });
  assert.deepEqual(logs, ['homing: coordination-claim-projection -> docs/wiki/example-studio-claim-projection.md (cited record)']);
  const result = meaningExtracted.consolidateClusters(raw, CITED_WIKI, { runId: 'r', wikiDirs: ['docs/wiki'], meaningHomes: r.meaningHomes });
  assert.equal(result[0].bucket, 'homed');
});

test('cited-record homing: two page hits narrow the meaning-match candidates to those pages', async () => {
  const raw = [citedRaw('coordination-claim-projection', [{ id: 'n1', source: 'docs/plans/a.md', content: 'DR-42' }])];
  const pageFacts = {
    homes: { 'coordination-claim-projection': ['docs/wiki/unrelated-topic.md', 'docs/wiki/claim-routing.md'] },
    previews: { 'docs/wiki/claim-routing.md': { headings: ['Routing heads'], bullet_leads: ['route lead'] } },
  };
  const briefs = [];
  const r = await meaningExtracted.homeByMeaning(raw, CITED_WIKI, ['docs/wiki'], async (brief) => {
    briefs.push(brief);
    return { home: 'docs/wiki/unrelated-topic.md', reason: 'same subject' };
  }, () => {}, pageFacts);
  assert.equal(r.calls, 1);
  assert.equal(r.cited, 0);
  assert.equal(briefs.length, 1);
  assert.match(briefs[0], /docs\/wiki\/unrelated-topic\.md/);
  assert.match(briefs[0], /docs\/wiki\/claim-routing\.md/);
  assert.match(briefs[0], /headings: Routing heads/, 'a precomputed preview reaches the brief');
  assert.doesNotMatch(briefs[0], /docs\/wiki\/example-studio-claim-projection\.md/, 'a stem-sharing page without a cited record is not a candidate');
  assert.deepEqual(r.meaningHomes, { 'coordination-claim-projection': 'docs/wiki/unrelated-topic.md' });
});

test('cited-record homing: no page hit falls back to stem candidates, and empty pageFacts changes nothing', async () => {
  const raw = [citedRaw('coordination-claim-projection', [{ id: 'n1', source: 'docs/plans/z.md', content: 'DR-9' }])];
  const briefs = [];
  const ask = async (brief) => { briefs.push(brief); return { home: 'NEW' }; };
  const pageFacts = { homes: { 'coordination-claim-projection': [] }, previews: {} };
  const withFacts = await meaningExtracted.homeByMeaning(raw, CITED_WIKI, ['docs/wiki'], ask, () => {}, pageFacts);
  const without = await meaningExtracted.homeByMeaning(raw, CITED_WIKI, ['docs/wiki'], ask, () => {});
  assert.equal(withFacts.calls, 1);
  assert.equal(without.calls, 1);
  assert.equal(without.cited, 0);
  assert.equal(briefs[0], briefs[1]);
  assert.match(briefs[0], /example-studio-claim-projection/);
});

test('cited-record homing: a page hit is capped at the candidate limit', async () => {
  const many = Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`page-${i}`, `docs/wiki/page-${i}.md`]));
  const pageFacts = { homes: { 'new-topic': Object.values(many) }, previews: {} };
  let brief = '';
  await meaningExtracted.homeByMeaning([citedRaw('new-topic', [{ id: 'n', source: 's.md', content: 'DR-5' }])], many, ['docs/wiki'], async (b) => { brief = b; return { home: 'NEW' }; }, () => {}, pageFacts);
  assert.equal((brief.match(/^- docs\/wiki\/page-/gm) || []).length, 8);
});


// Executes the relay prompt's script in a temp repo with real python3, as the op-relay agent would.
async function runPageFactsLoader(files, rawClusters, wikiSlugs) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'page-facts-'));
  const prompts = [];
  const logs = [];
  try {
    for (const [rel, body] of Object.entries(files)) {
      fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
      fs.writeFileSync(path.join(dir, rel), body);
    }
    const agent = async (prompt) => {
      prompts.push(prompt);
      const r = cp.spawnSync('bash', ['-c', prompt.split('\n\n')[1]], { cwd: dir, encoding: 'utf8' });
      return { stdout: r.stdout, exit_status: r.status };
    };
    const matches = await makePageFactsLoader(agent)(rawClusters, wikiSlugs, ['wiki'], undefined, 'run', (l) => logs.push(l));
    return { matches, prompts, logs };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}



// The function-extraction tests never parse the whole script, so a broken meta string (an
// apostrophe closing a single-quoted `detail`) passed them and shipped unparseable. The runtime
// runs the body as an async function (top-level await and return are legal), so it is parsed that
// way: constructing the function parses it and runs nothing.
test('workflow script parses whole, meta included', () => {
  const src = fs.readFileSync(WORKFLOW_PATH, 'utf8').replace(/^export const meta\b/m, 'const meta');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  assert.doesNotThrow(() => new AsyncFunction(src), 'distill-harvest.workflow.js does not parse');
});

test('scan retry: a batch whose scan agent died or returned zero nuggets is scanned once more before it counts as failed', () => {
  assert.match(SOURCE, /const SCAN_ATTEMPTS = 2\n/);
  const loop = SOURCE.slice(SOURCE.indexOf('const SCAN_ATTEMPTS = '), SOURCE.indexOf('scanPending = retry'));
  assert.match(loop, /const read = r && Array\.isArray\(r\.nuggets\) && r\.nuggets\.length > 0/);
  assert.match(loop, /if \(read \|\| attempt === SCAN_ATTEMPTS\)/);
  assert.match(loop, /label: attempt === 1 \? batch\.batchId : `\$\{batch\.batchId\}-r\$\{attempt\}`/);
  assert.equal((loop.match(/ agent\(scanBriefFor/g) || []).length, 1, 'one scan call site, looped');
});

test('cross-page restatement: a same-source, same-wording nugget pair gets one owner page', () => {
  const crossPageRestatements = new Function(`${extractFunctionSource(SOURCE, 'crossPageRestatements')}; return crossPageRestatements;`)();
  const pathOf = (u) => u.wikiPath;
  const lesson = 'a guard asserting against its own fixture double stays green while production breaks';
  const units = [
    { wikiPath: 'docs/wiki/review-process.md', nuggets: [
      { id: 'n1', source: 'plan-a.md', content: `General rule: ${lesson}` },
      { id: 'n9', source: 'plan-b.md', content: 'reviews run on the diff only' },
      { id: 'n8', source: 'plan-a.md', content: 'unrelated note about naming review lenses' }] },
    { wikiPath: 'docs/wiki/tripwire-coverage.md', nuggets: [
      { id: 'n2', source: 'plan-a.md', content: `Gotcha: ${lesson} in production` }] },
    { wikiPath: 'docs/wiki/other.md', nuggets: [
      { id: 'n3', source: 'plan-z.md', content: lesson }] },
  ];
  const out = crossPageRestatements(units, pathOf);
  assert.deepEqual([...out.keys()], ['docs/wiki/review-process.md']);
  assert.deepEqual(out.get('docs/wiki/review-process.md'),
    [{ nugget_id: 'n1', owner_path: 'docs/wiki/tripwire-coverage.md', owner_nugget_id: 'n2' }]);
  assert.equal(out.get('docs/wiki/other.md'), undefined, 'a different source is never paired');
});


// ---------------------------------------------------------------------------
// Prepared clusters drive the run: the scan wave sees only the residue prepare did not classify.
// ---------------------------------------------------------------------------

const preparedHelpers = new Function(`
  ${['preparedClustersOf', 'mechanicalFilesOf', 'residueBatchesOf', 'mergeMechanicalScan'].map((n) => extractFunctionSource(SOURCE, n)).join('\n')}
  return { preparedClustersOf, mechanicalFilesOf, residueBatchesOf, mergeMechanicalScan };
`)();
const scanBlockSrc = extractBlockSource(SOURCE, 'const SCAN_ATTEMPTS = 2', 'const RESIDUE_NUGGET_IDS = new Set(RESIDUE_SCAN.nuggets.map((n) => n.id))');

function preparedFixture() {
  return {
    batches: [{ batchId: 'b1', files: ['a/one.md', 'a/two.md', 'a/three.md'] }],
    clusters: [{ topicKey: 'alpha', homed: false, wikiPath: 'docs/wiki/alpha.md',
      nuggets: [{ id: 'b1-001-01', type: 'KNOWLEDGE', source: 'a/one.md', content: 'x' }] }],
    dropped_nuggets: ['b1-002-01'],
  };
}

// Runs the real scan block with a recording agent; returns the dispatched briefs and the merged results.
async function runScanBlock(prepared, batches, agentImpl) {
  const dispatched = [];
  const agent = async (brief, opts) => { dispatched.push({ brief, opts }); return agentImpl(brief, opts); };
  const parallel = async (fns) => Promise.all(fns.map((f) => f()));
  const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
  const run = new AsyncFunction('PREPARED', 'BATCHES', 'agent', 'parallel', 'log', 'scanBriefFor', 'NUGGET_SCHEMA',
    'DISTILL_WRITER_TYPE', 'CONCURRENCY_CAP', 'PLAN_TRIAGE_REPORT', 'RUN_ID', 'helpers', `
    const { preparedClustersOf, mechanicalFilesOf, residueBatchesOf, mergeMechanicalScan } = helpers;
    const PREPARED_CLUSTERS = preparedClustersOf(PREPARED);
    const MECHANICAL_FILES = mechanicalFilesOf(PREPARED);
    ${scanBlockSrc}
    return { scanResults, RESIDUE_SCAN, RESIDUE_NUGGET_IDS };
  `);
  const out = await run(prepared, batches, agent, parallel, () => {}, (b) => `scan ${b.batchId}: ${b.files.join(',')}`,
    {}, 'coordinator:distill-writer', 16, {}, 'run1', preparedHelpers);
  return { ...out, dispatched };
}

test('prepared clusters: a prepared payload whose every file prepare classified dispatches zero scan agents', async () => {
  const prepared = preparedFixture();
  prepared.batches[0].files = ['a/one.md', 'a/two.md'];
  const r = await runScanBlock(prepared, prepared.batches, () => { throw new Error('no agent expected'); });
  assert.equal(r.dispatched.length, 0);
  assert.equal(r.scanResults.length, 1);
  const [res] = r.scanResults;
  assert.deepEqual(res.nuggets.map((n) => [n.id, n.type]), [['b1-001-01', 'KNOWLEDGE'], ['b1-002-01', 'EPHEMERAL']]);
  assert.equal(res.file_fates.length, 2);
  for (const f of res.file_fates) assert.ok(f.fate_prose.trim().split(/\s+/).length >= 8, `fate prose long enough: ${f.fate_prose}`);
  assert.match(res.file_fates[0].fate_prose, /topic\(s\) alpha/);
  assert.deepEqual(r.RESIDUE_SCAN, { files: 0, nuggets: [] });
});

test('prepared clusters: only the residue file is scanned, and its carry-forward nuggets ride residue_scan, not the clusters', async () => {
  const prepared = preparedFixture();
  const r = await runScanBlock(prepared, prepared.batches, (brief) => ({
    batch_id: 'b1', nuggets_file: null,
    nuggets: [{ id: 'b1-001', type: 'KNOWLEDGE', source: 'a/three.md', content: 'learned' },
      { id: 'b1-002', type: 'EPHEMERAL', source: 'a/three.md', content: 'noise' }],
    file_fates: [{ path: 'a/three.md', fate_prose: 'A residue file describing a standalone lesson about the scan leg.' }],
  }));
  assert.equal(r.dispatched.length, 1, 'one scan call, over the residue batch');
  assert.match(r.dispatched[0].brief, /a\/three\.md/);
  assert.doesNotMatch(r.dispatched[0].brief, /a\/one\.md|a\/two\.md/, 'a classified file is never sent to the scan');
  assert.equal(r.dispatched[0].opts.phase, 'scan');
  assert.deepEqual(r.RESIDUE_SCAN.nuggets.map((n) => n.id), ['b1-001']);
  assert.equal(r.RESIDUE_SCAN.files, 1);
  assert.ok(r.RESIDUE_NUGGET_IDS.has('b1-001'));
  const ids = r.scanResults[0].nuggets.map((n) => n.id);
  assert.deepEqual(ids, ['b1-001-01', 'b1-002-01', 'b1-001', 'b1-002']);
});

test('prepared clusters: without clusters (invocation A) every batch is scanned, as before', async () => {
  const batches = [{ batchId: 'b1', files: ['a/one.md'] }];
  const r = await runScanBlock({ batches }, batches, () => ({
    batch_id: 'b1', nuggets_file: null, nuggets: [{ id: 'b1-001', type: 'KNOWLEDGE', source: 'a/one.md', content: 'k' }], file_fates: [],
  }));
  assert.equal(r.dispatched.length, 1);
  assert.equal(r.scanResults.length, 1);
});

test('prepared clusters: a dead residue scan leaves the residue file untouched, never EPHEMERAL', async () => {
  const prepared = preparedFixture();
  const r = await runScanBlock(prepared, prepared.batches, () => null);
  assert.equal(r.dispatched.length, 2, 'the residue batch is scanned once more, then given up');
  const sources = r.scanResults[0].nuggets.map((n) => n.source);
  assert.ok(!sources.includes('a/three.md'), 'no nugget invented for the unscanned file');
});

test('prepared clusters: the clustering, curation and homing stages read args.prepared.clusters, not the scan results', () => {
  assert.match(LIVE_CODE, /const rawClusters = PREPARED_CLUSTERS \? PREPARED_CLUSTERS : clusterNuggets\(/);
  assert.match(LIVE_CODE, /if \(!CURATED_TAGS && !PREPARED_CLUSTERS\) \{/);
  assert.match(LIVE_CODE, /= PREPARED_CLUSTERS \? \{ meaningHomes: \{\}, calls: 0, failed: \[\], cited: 0, gotcha: \[\] \} : await homeByMeaning\(/);
  assert.match(LIVE_CODE, /const allClusters = PREPARED_CLUSTERS\s*\? rawClusters\.map\(/);
  assert.match(LIVE_CODE, /const unharvestedNuggetIds = new Set\(\[[\s\S]*\.\.\.RESIDUE_NUGGET_IDS/);
});

test('classifiedFiles: every file prepare classified leaves no residue batch, so no scan or plan-triage agent runs', async () => {
  const prepared = {
    batches: [{ batchId: 'b1', files: ['a/one.md', 'a/two.md', 'docs/plans/p.md'] }],
    clusters: [{ topicKey: 'alpha', nuggets: [{ id: 'b1-001-01', type: 'KNOWLEDGE', source: 'a/one.md', content: 'x' }] }],
    dropped_nuggets: [],
    classifiedFiles: ['a/one.md', 'a/two.md', 'docs/plans/p.md'],
    file_fates: [
      { path: 'a/two.md', fate: 'EPHEMERAL', fate_prose: 'two.md was classified by script in prepare as EPHEMERAL: nothing liftable; no scan agent read it.' },
      { path: 'docs/plans/p.md', fate: 'ALREADY_CAPTURED', fate_prose: 'p.md was classified by script in prepare as ALREADY_CAPTURED: its content is in the wiki; no scan agent read it.' },
    ],
  };
  const mech = preparedHelpers.mechanicalFilesOf(prepared);
  assert.deepEqual([...mech].sort(), ['a/one.md', 'a/two.md', 'docs/plans/p.md']);
  assert.deepEqual(preparedHelpers.residueBatchesOf(prepared.batches, mech), []);
  const r = await runScanBlock(prepared, prepared.batches, () => { throw new Error('no agent expected'); });
  assert.equal(r.dispatched.length, 0);
  const [res] = r.scanResults;
  assert.deepEqual(res.file_fates.map((f) => f.path).sort(), ['a/one.md', 'a/two.md', 'docs/plans/p.md']);
  assert.deepEqual(r.RESIDUE_SCAN, { files: 0, nuggets: [] });
  const partial = { ...prepared, classifiedFiles: ['a/one.md'] };
  assert.deepEqual(preparedHelpers.mechanicalFilesOf({ ...partial, file_fates: [] }).size, 1);
});

const { curatedMissingHalt } = new Function(`${extractFunctionSource(SOURCE, 'listSupplied')}\n${extractFunctionSource(SOURCE, 'curatedMissingHalt')}\nreturn { curatedMissingHalt };`)();
const assertListCountsFn = new Function(`${extractFunctionSource(SOURCE, 'assertRelayedListCounts')}\nreturn assertRelayedListCounts;`)();

test('curatedMissingHalt: a declared count with no list and no curated halts curated-missing naming prepare --verdicts', () => {
  const h = curatedMissingHalt({ batches: [] }, { contradictionClusterCount: 5 }, { batches: [] });
  assert.equal(h.halted, 'curated-missing');
  assert.equal(h.phase_reached, 'load');
  assert.match(h.detail, /prepare with --verdicts/);
});

test('curatedMissingHalt: curated present, a list supplied, or no/zero count never halts', () => {
  assert.equal(curatedMissingHalt({ curated: { verdicts: [] } }, { contradictionClusterCount: 5 }, {}), null);
  assert.equal(curatedMissingHalt({}, { contradictionClusterCount: 5, contradictionClusters: [] }, {}), null);
  assert.equal(curatedMissingHalt({}, { contradictionClusterCount: 5 }, { contradictionClusters: [1] }), null);
  assert.equal(curatedMissingHalt({}, {}, {}), null);
  assert.equal(curatedMissingHalt({}, { contradictionClusterCount: 0 }, {}), null);
});

test('prepared.curated: a payload carrying curated passes both count checks with contradictionClusterCount set', () => {
  const curated = { verdicts: [{ tag: 'a' }, { tag: 'b' }], counts: { total: 2 }, contradictionClusters: [1, 2, 3], contradictionClusterCount: 3 };
  assert.equal(curatedMissingHalt({ curated }, { contradictionClusterCount: 3 }, {}), null);
  const first = assertListCountsFn({ contradictionClusters: undefined },
    { args: { contradictionClusters: undefined }, file: {} }, true);
  assert.equal(first, null);
  const second = assertListCountsFn({ verdicts: curated.verdicts, contradictionClusters: curated.contradictionClusters },
    { args: { verdicts: 2, contradictionClusters: 3 }, file: { verdicts: 2, contradictionClusters: 3 } }, true);
  assert.equal(second, null);
  assert.match(LIVE_CODE, /const curatedMissing = curatedMissingHalt\(PREPARED, RAW_ARGS_INPUT, loadedInput\)\s*if \(curatedMissing\)[\s\S]*const listCountHalt = assertRelayedListCounts\(/);
});

test('leg 2 loads a prepare-shaped curated (counts derived beside the lists) and halts on one without', () => {
  const lists = { verdicts: [{ tag: 'a' }], contradictionClusters: [1, 2], judgmentClusters: [1] };
  const derived = { ...lists, counts: { total: 1 }, contradictionClusterCount: 2, judgmentClusterCount: 1 };
  const check = (c) => assertListCountsFn(
    { verdicts: c.verdicts, contradictionClusters: c.contradictionClusters },
    { args: {}, file: { verdicts: c.counts.total, contradictionClusters: c.contradictionClusterCount } }, true);
  assert.equal(check(derived), null);
  const { contradictionClusterCount, ...bare } = derived;
  assert.equal(check(bare).halted, 'input-count-mismatch');
});

test('invocation-A resume_hint names prepare --verdicts and no hand-set curated field', () => {
  const m = /resume_hint:\s*\n\s*`Run claude-klabauter distill\.curate_clusters[\s\S]*?'and will silently re-dispatch the whole scan wave\.',/.exec(SOURCE);
  assert.ok(m, 'invocation-A resume_hint found');
  assert.match(m[0], /prepare with --nuggets[\s\S]*--verdicts/);
  assert.match(m[0], /prepared\.curated/);
  assert.doesNotMatch(m[0], /curated` field set/);
});

test('prepared clusters: plan triage judges only the residue plans when clusters are prepared', () => {
  const batches = [{ batchId: 'b1', files: ['docs/plans/a.md', 'docs/plans/b.md'] }];
  const prepared = { batches, clusters: [{ topicKey: 't', nuggets: [{ id: 'b1-001-01', source: 'docs/plans/a.md' }] }], dropped_nuggets: [] };
  const mech = preparedHelpers.mechanicalFilesOf(prepared);
  assert.deepEqual([...mech], ['docs/plans/a.md']);
  assert.deepEqual(preparedHelpers.residueBatchesOf(batches, mech), [{ batchId: 'b1', files: ['docs/plans/b.md'] }]);
  assert.match(LIVE_CODE, /planPathsOf\(PREPARED_CLUSTERS \? residueBatchesOf\(BATCHES, MECHANICAL_FILES\) : BATCHES, TRIAGE_LOG_ROOTS\)/);
});

// ---------------------------------------------------------------------------
// Artifact re-entry: off the default path, tool-less ops through the finalize splice.
// ---------------------------------------------------------------------------

const reentryFns = new Function(
  `${CLASSIFIER_SRC}\n${['reentryPayloadsFor', 'settleReentryRows', 'buildPromoteManifest'].map((n) => extractFunctionSource(SOURCE, n)).join('\n')}\n` +
  'return { reentryPayloadsFor, settleReentryRows, buildPromoteManifest }'
)();

const REENTRY_PAYLOADS = [{
  topics: [
    { topic_key: 'alpha', wiki_path: 'docs/wiki/alpha.md', outline: { headings: ['A'] }, new_page: false,
      nuggets: [{ id: 'b-001-01', cite: 'docs/plans/x.md' }, { id: 'b-002-01', cite: 'docs/plans/y.md' }],
      cite_ids: ['b-001-01', 'b-002-01'] },
    { topic_key: 'nugget-b', judge_only: true, nuggets: [{ id: 'b-001-02', cite: 'docs/plans/x.md' }], cite_ids: ['b-001-02'] },
  ],
}, { topics: [{ topic_key: 'beta', nuggets: [{ id: 'c-001-01', cite: 'docs/plans/z.md' }], cite_ids: ['c-001-01'] }] }];

test('re-entry payloads: only page topics, only the SEND_BACK artifact nuggets, original payload index kept', () => {
  const out = reentryFns.reentryPayloadsFor(REENTRY_PAYLOADS, [{ artifact_path: 'docs/plans/x.md' }]);
  assert.equal(out.length, 1);
  assert.equal(out[0].index, 0);
  assert.deepEqual(out[0].payload.topics.map((t) => t.topic_key), ['alpha']);
  assert.deepEqual(out[0].payload.topics[0].cite_ids, ['b-001-01']);
  assert.equal(out[0].payload.topics[0].wiki_path, 'docs/wiki/alpha.md');
  assert.deepEqual(reentryFns.reentryPayloadsFor(REENTRY_PAYLOADS, [{ artifact_path: 'docs/plans/none.md' }]), []);
});

test('re-entry settle: a row with returned ops is BLOCKED pending finalize, never DELETE; a failed call leaves it SEND_BACK', () => {
  const rows = [{ artifact_path: 'docs/plans/x.md', reason: 'r' }, { artifact_path: 'docs/plans/z.md', reason: 'r' }, { artifact_path: 'docs/plans/none.md', reason: 'r' }];
  const entries = reentryFns.reentryPayloadsFor(REENTRY_PAYLOADS, rows);
  assert.equal(entries.length, 2);
  const returns = [{ topics: [{ topic_key: 'alpha', ops: [{ section_heading: 'A', action: 'append', markdown: 'm', cites: ['b-001-01'] }] }] }, null];
  const out = reentryFns.settleReentryRows(rows, entries, returns);
  assert.equal(out.get('docs/plans/x.md').disposition, 'BLOCKED');
  assert.match(out.get('docs/plans/x.md').reason, /pending finalize of reentry_manifest/);
  assert.deepEqual(out.get('docs/plans/x.md').source_nugget_ids, ['b-001-01']);
  assert.equal(out.has('docs/plans/z.md'), false, 'failed call: row stays SEND_BACK');
  assert.match(out.get('docs/plans/none.md').reason, /no page-topic nugget/);
  for (const v of out.values()) assert.notEqual(v.disposition, 'DELETE');
  const noop = reentryFns.settleReentryRows([rows[0]], [entries[0]], [{ topics: [{ topic_key: 'alpha', ops: [], no_ops_reason: 'nothing-new-vs-page' }] }]);
  assert.match(noop.get('docs/plans/x.md').reason, /returned no op/);
});

test('re-entry: gated on args.reentry === true; every dispatch is tool-less distill-synth with the synth brief', () => {
  assert.match(LIVE_CODE, /const REENTRY_ENABLED = RAW_ARGS_INPUT\.reentry === true/);
  assert.match(LIVE_CODE, /if \(REENTRY_ENABLED && phase3d\.status === 'ran'\)/);
  const loop = LIVE_CODE.slice(LIVE_CODE.indexOf('if (REENTRY_ENABLED && phase3d.status'), LIVE_CODE.indexOf('const reentryManifest'));
  assert.match(loop, /agentType: 'coordinator:distill-synth'/);
  assert.match(loop, /agent\(synthBriefFor\(e\.payload\)/);
  assert.doesNotMatch(loop, /coordinator:executor/);
  assert.doesNotMatch(loop, /Write\/Edit/);
  assert.doesNotMatch(LIVE_CODE.slice(LIVE_CODE.indexOf('function synthBriefFor')), /Write\/Edit direct|direct write with Write/);
  assert.equal((LIVE_CODE.match(/phase: 'artifact-reentry'/g) || []).length, 1);
});

test('re-entry off the default path: SEND_BACK rows resolve BLOCKED naming it, other rows untouched', () => {
  const src = extractBlockSource(SOURCE, 'const REENTRY_ENABLED = RAW_ARGS_INPUT.reentry === true', "offPaths.join(', ')}` : ''))\n}");
  const run = (reentry) => {
    const lines = [];
    const fn = new Function('RAW_ARGS_INPUT', 'currentDeletions', 'log', `${src}\nreturn currentDeletions`);
    const rows = [{ artifact_path: 'a.md', disposition: 'SEND_BACK', reason: 'r' }, { artifact_path: 'b.md', disposition: 'DELETE', reason: 'ok' }];
    return { rows: fn(reentry === undefined ? {} : { reentry }, rows, (l) => lines.push(l)), lines };
  };
  for (const off of [undefined, false, 'true', 1]) {
    const { rows, lines } = run(off);
    assert.equal(rows[0].disposition, 'BLOCKED');
    assert.match(rows[0].reason, /off the default path/);
    assert.equal(rows[1].disposition, 'DELETE');
    assert.match(lines.join('\n'), /off the default path \(args\.reentry unset\)/);
  }
  const on = run(true);
  assert.equal(on.rows[0].disposition, 'SEND_BACK');
});

test('reentry_manifest carries the promote manifest top-level keys and is returned with a finalize hint', () => {
  const m = reentryFns.buildPromoteManifest('r', [], [{ topics: [] }], {});
  assert.deepEqual(Object.keys(m).sort(), Object.keys(reentryFns.buildPromoteManifest('r', [], [], {})).sort());
  assert.match(LIVE_CODE, /reentry_manifest: \{ \.\.\.reentryManifest, wikiDirs: WIKI_DIRS \}/);
  assert.match(SOURCE, /finalize --manifest <reentry_manifest> --no-scratch --no-archive/);
});

test('synth brief asks a judge-only nugget stating a durable contract or root cause for home_suggestion', () => {
  const synthBriefFor = new Function(`${extractFunctionSource(SOURCE, 'judgeOnlyPayload')}; ${extractFunctionSource(SOURCE, 'synthBriefFor')}; return synthBriefFor;`)();
  const brief = synthBriefFor({ topics: [{ topic_key: 'nugget-b', judge_only: true, nuggets: [] }] }).replace(/\s+/g, ' ');
  assert.match(brief, /home_suggestion \{wiki_path, kind: 'durable-contract' \| 'root-cause'\}/);
  assert.match(brief, /never dropped as a bare no-op reason/);
});

test('restorePrepared rebuilds the cluster keys a slug fixes and leaves a prepared that is not clustersPacked alone', () => {
  const restorePrepared = new Function(['unpackWikiSlugs', 'restoreClusters', 'restorePrepared']
    .map((name) => extractFunctionSource(SOURCE, name)).join('\n') + '\nreturn restorePrepared;')();
  const nuggets = [{ id: 'n1', content: 'c', source: 's.md' }];
  // `odd=Other.md`: a slug whose page file is not `<slug>.md`.
  const packed = {
    clustersPacked: true,
    wikiDirs: ['docs/wiki', 'other'],
    wikiSlugsPacked: { 'docs/wiki': ['homed-topic', 'odd=Other.md'] },
    clusters: [
      { slug: 'homed-topic', nuggets },
      { slug: 'odd', nuggets },
      { slug: 'fresh-topic', nuggets },
      { slug: 'nugget-b-1', nuggets },
      { slug: 'nugget-topic', per_nugget: false, nuggets },
      { slug: 'kept', topicKey: 'Kept Key', wikiPath: 'elsewhere/kept.md', homed: false, per_nugget: true, nuggets },
      { nuggets },
    ],
  };
  const { clustersPacked, ...unflagged } = packed;
  assert.deepEqual(restorePrepared(unflagged), unflagged);
  const restored = restorePrepared(packed);
  assert.equal(restored.clustersPacked, undefined);
  assert.deepEqual(restored.clusters, [
    { slug: 'homed-topic', topicKey: 'homed-topic', homed: true, wikiPath: 'docs/wiki/homed-topic.md', nuggets },
    { slug: 'odd', topicKey: 'odd', homed: true, wikiPath: 'docs/wiki/Other.md', nuggets },
    { slug: 'fresh-topic', topicKey: 'fresh-topic', homed: false, wikiPath: 'docs/wiki/fresh-topic.md', nuggets },
    { slug: 'nugget-b-1', topicKey: 'nugget-b-1', homed: false, wikiPath: 'docs/wiki/nugget-b-1.md', per_nugget: true, nuggets },
    { slug: 'nugget-topic', topicKey: 'nugget-topic', homed: false, wikiPath: 'docs/wiki/nugget-topic.md', per_nugget: false, nuggets },
    { slug: 'kept', topicKey: 'Kept Key', wikiPath: 'elsewhere/kept.md', homed: false, per_nugget: true, nuggets },
    { nuggets },
  ]);
});

// ---------------------------------------------------------------------------
// Launch shards: prepared-NN.json carries launchShard {index, count, run_id}; index >= 1 is synth-only.
// ---------------------------------------------------------------------------

// Runs the whole script as the runtime does (top-level await and return legal) against recording stubs.
async function runWholeScript(preparedBody, agentImpl) {
  const src = fs.readFileSync(WORKFLOW_PATH, 'utf8').replace(/^export const meta\b/m, 'const meta');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const phases = [];
  const calls = [];
  const agent = async (brief, opts) => { calls.push(opts); return agentImpl(brief, opts); };
  const parallel = (thunks) => Promise.all(thunks.map((t) => t()));
  const run = new AsyncFunction('args', 'agent', 'parallel', 'phase', 'log', src);
  const result = await run({ prepared: preparedBody }, agent, parallel, (p) => phases.push(p), () => {});
  return { result, phases, calls };
}

function shardPrepared(shard) {
  return {
    runId: 'run-shard', repoRoot: '/repo', wikiDirs: ['docs/wiki'], wikiSlugs: {}, wikiSlugCount: 0,
    ...(shard ? { launchShard: shard, batch_count: 0, total_file_count: 0 } : {}),
    clusters: [{ topicKey: 'alpha', slug: 'alpha', homed: false, wikiPath: 'docs/wiki/alpha.md',
      nuggets: [{ id: 'b1-001-01', type: 'KNOWLEDGE', source: 'a/one.md', content: 'alpha body' }] }],
    sourceHashes: { alpha: { sha256: 'hash-alpha', unchanged: false } },
    candidates: [],
    synth: { schema: { type: 'object' }, deferred_topics: [], payloads: [{ topics: [
      { topic_key: 'alpha', wiki_path: 'docs/wiki/alpha.md', new_page: true, outline: { headings: [] },
        nuggets: [{ id: 'b1-001-01', text: 'alpha body', cite: 'a/one.md' }], cite_ids: ['b1-001-01'] }] }] },
  };
}

const synthReturnFor = () => ({ topics: [{ topic_key: 'alpha', ops: [
  { section_heading: 'Alpha', action: 'append', markdown: 'text', cites: ['b1-001-01'] }], decision_records: [] }] });

test('launch shard index 1: synth calls only, promote-ready with the shard on the manifest and no deletion manifest', async () => {
  const marker = { index: 1, count: 2, run_id: 'run-shard' };
  const { result, phases, calls } = await runWholeScript(shardPrepared(marker), async () => synthReturnFor());
  assert.equal(result.phase_reached, 'promote-ready');
  assert.deepEqual(result.promote_manifest.shard, marker);
  assert.equal(result.promote_manifest.run_id, 'run-shard');
  assert.equal(result.promote_manifest.synth_results.length, 1);
  assert.deepEqual(result.promote_manifest.hashes, { alpha: 'hash-alpha' });
  assert.deepEqual(calls.map((c) => [c.phase, c.agentType]), [['synth', 'coordinator:distill-synth']]);
  assert.deepEqual(phases, ['load', 'synth']);
  assert.equal(result.deletion_manifest, undefined);
  assert.equal(result.reentry_manifest, undefined);
});

test('launch shard index 1: a failed synth call halts synth-partial-failure and never reaches promote-ready', async () => {
  const marker = { index: 1, count: 2, run_id: 'run-shard' };
  const { result } = await runWholeScript(shardPrepared(marker), async () => null);
  assert.equal(result.halted, 'synth-partial-failure');
  assert.deepEqual(result.failed_synth_calls, ['synth-1']);
});

// Shard 0 runs the full scan path; its only cluster is unchanged, so it reaches promote with zero synth results.
function shard0Prepared(shard) {
  return {
    runId: 'run-shard', repoRoot: '/repo', wikiDirs: ['docs/wiki'], wikiSlugs: {}, wikiSlugCount: 0,
    launchShard: shard,
    batches: [{ batchId: 'b1', description: 'd', files: ['a/one.md'] }], batch_count: 1, total_file_count: 1,
    clusters: [{ topicKey: 'alpha', slug: 'alpha', homed: true, wikiPath: 'docs/wiki/alpha.md',
      nuggets: [{ id: 'b1-001-01', type: 'KNOWLEDGE', source: 'a/one.md', content: 'alpha body' }] }],
    sourceHashes: { alpha: { sha256: 'hash-alpha', unchanged: true } },
    candidates: [],
    curated: { verdicts: [], counts: { total: 0 } },
    synth: { schema: { type: 'object' }, deferred_topics: [], payloads: [] },
  };
}

test('launch shard index 0 of a sharded run stops at promote-ready even with no synth results', async () => {
  // Finalize's merge refuses a missing shard index, so shard 0 must always return its manifest.
  const marker = { index: 0, count: 2, run_id: 'run-shard' };
  const { result, phases, calls } = await runWholeScript(shard0Prepared(marker), async () => null);
  assert.equal(calls.length, 0);
  assert.equal(phases[phases.length - 1], 'promote');
  assert.equal(result.phase_reached, 'promote-ready');
  assert.deepEqual(result.promote_manifest.shard, marker);
  assert.equal(result.promote_manifest.synth_results.length, 0);
});

test('an unsharded run with no synth results continues past promote instead of stopping there', async () => {
  const { result, phases } = await runWholeScript(shard0Prepared({ index: 0, count: 1, run_id: 'run-shard' }), async () => null);
  assert.notEqual(result.phase_reached, 'promote-ready');
  assert.ok(phases.includes('promote'));
});

test('no launchShard: the unsharded path still demands batches, so a batch-less prepared halts empty-input-batches', async () => {
  const { result, calls } = await runWholeScript(shardPrepared(null), async () => synthReturnFor());
  assert.equal(result.halted, 'empty-input-batches');
  assert.equal(calls.length, 0);
});
