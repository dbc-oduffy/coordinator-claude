/**
 * survey.workflow.js — background Workflow for the /architecture-survey (deep-architecture-survey)
 * Phase-1/2/3 orchestration.
 *
 * Purpose: replace the hand-fired parallel `Agent` dispatch that self-destructs at scale
 * (state/audits/2026-07-12-architecture-survey-dogfood-friction-log.md findings #6-#9, #13 — a
 * 21-agent first wave tripped an ACCOUNT-LEVEL rate limit, killed all 21, ZERO outputs landed,
 * and the resulting cooldown poisoned every later vehicle for minutes). This script owns the
 * WHOLE pipeline — chunking, Phase-1 inventory, Phase-2 analysis, Phase-3 synthesis — inside one
 * background Workflow so the EM's context never holds the wave-map (finding #13, the strongest
 * architectural argument for the rebuild).
 *
 * Shared Workflow-resume primitive (adopt the IDENTICAL shape as the twin
 * `distill-harvest.workflow.js`, coordinator/pipelines/artifact-distillation/ — do NOT diverge):
 *   - An expensive, journaled wave BEFORE a fragile synth wave.
 *   - Wave-1 returns STRUCTURED output (schema:) so clustering/joining happens in plain JS with
 *     zero agent cost — no LLM re-groups the chunk table.
 *   - Wave-2 is one-agent-owns-one-output-file (disjoint scratch paths — no write collisions).
 *   - resumeFromRunId is load-bearing: a rate-limit wipe of the analyst wave re-runs ONLY the
 *     failed analysts; the Phase-1 chunk-table wave returns from the journal for free.
 *   - The two waves are NEVER merged into one resumable unit (merging re-pays the expensive wave
 *     on every later wipe — see plan Anti-scope: "Do NOT collapse the deterministic-extraction
 *     wave into the agentic wave").
 *
 * Divergence from the distill twin (deliberate, per plan Cross-plan coordination): the ANALYST
 * fan-out here runs at a LOW hard cap (~4, sequential sub-batches, ramp), not
 * min(16, cores-2) — burst ARRIVAL-RATE is what trips the account cooldown (finding #8), not
 * merely wave size, so distill's wider cap is the wrong shape for this pipeline. See
 * § Concurrency below for the full rationale and the explicit backoff-on-429 this pipeline also
 * needs that distill's lane does not (distill relies on resumeFromRunId alone; survey needs
 * BOTH resumeFromRunId AND in-script backoff because the friction log shows the SAME account
 * cooldown can outlast the Workflow tool's own ~24s terminal-error retry — finding #9).
 *
 * Phase-0.5 consume-gate (C-integrate, claude-klabauter's naming, 2026-07-12; hoisted off the agent lane,
 * 2026-08-20 — coordinator/bin/survey-consume-gate.py). At the Phase 0->1 boundary this Workflow
 * consumes `INPUT.consumeGate`, the pre-run stdout of that EM-side, pure-stdlib Python script —
 * it evaluates the survey-side RAG-present predicate (single authority per
 * coordinator/docs/contracts/arch-engine-scripts.md § Single-authority RAG-present predicate:
 * "claude-klabauter cartography fires iff rag has NO NON-EMPTY INDEX for the repo"), and on RAG-absent
 * invokes the `cartography.*` ops directly in-process (a real filesystem/subprocess primitive,
 * unlike this Workflow script) and reads their JSON artifact back with a plain `json.load()` —
 * no windowed transport, because there is no agent reply to truncate. The Workflow itself does
 * NOT dispatch, invoke, or read anything for this phase; it only consumes the already-validated
 * payload and, when it is absent, malformed, or declined, falls back to the Phase-0 agentic
 * census wave below — the same disposition a declined op produced before the hoist. See
 * `coordinator/docs/wiki/coordinator-tripwires/workflow-agent-as-file-handle.md` for why this
 * work never belonged behind `agent()` in the first place. Chunk-K retirement (claude-klabauter
 * consume-contract, 2026-07-12): the untested inline bash at the (retired)
 * `coordinator/commands/architecture-survey.md:104-120` refresh churn/emergent-set pass is
 * replaced by `cartography.churn` for `mode === 'refresh'` runs, also run by the script and
 * consumed here as `INPUT.consumeGate.churn_result`.
 *
 * Spec backlink: docs/plans/2026-07-12-survey-rebuild-claude-klabauter-reliant.md § chunk C-integrate;
 * coordinator/docs/contracts/arch-engine-scripts.md (I/O contract, budget table, fail-loud invariants).
 *
 * Spec backlink: docs/plans/2026-07-12-survey-rebuild-claude-klabauter-reliant.md chunk C3.
 * Doctrine: coordinator/docs/wiki/em-operating-model/workflow-orchestration.md (vehicle-choice, chunking,
 * commit-discipline, model-selection rules — this script follows all of them).
 * Templates: coordinator/pipelines/deep-architecture-survey/agent-prompts.md (Phase 1/2/3
 * prompt bodies — this script inlines adapted copies scoped to schema-forced structured return;
 * C4's condense-analyst-pages helper and H2-anchor enforcement are invoked BY THE PHASE-3 OPUS
 * AGENT ITSELF, not by this Workflow script — see the CONDENSE_HOOK comment at the Phase-3
 * boundary below for why (no in-script filesystem primitive)).
 *
 * Negative-spec: this script does NOT hand-fire a wide Agent wave first (finding #9 — the first
 * burst poisons the well for every later vehicle) — even the Phase-0 census wave is sub-batched
 * at the SAME low cap as the analyst wave, because a wide FIRST wave is exactly what trips the
 * cooldown regardless of which phase it's in. Wave-2 (Phase-2 analyst) agents do NOT commit —
 * per workflow-orchestration.md § Commit discipline inside workflows, the EM commits from the
 * returned manifest after the run. Analysts Write incrementally (partial-work salvage, finding
 * #7) — a killed agent still leaves usable sections on disk.
 */

export const meta = {
  name: 'deep-architecture-survey',
  description: '/architecture-survey Phase 0-3: Phase-0.5 consume-gate (INPUT.consumeGate, script-produced) -> deterministic chunk census fallback -> EM-side symbols receipt (INPUT.symbolsReceipt) -> Sonnet analysis (LOW-cap sequential sub-batches + ramp + backoff) -> per-system Sonnet synthesis shards + one cross-system agent',
  phases: [
    { title: 'consume-gate', detail: 'consumes INPUT.consumeGate (EM-side script output: RAG-present predicate + cartography.* op results) — zero agent dispatch; falls back to the census wave when absent or declined' },
    { title: 'census', detail: 'LOW-cap sequential sub-batches: Haiku per directory-bucket returns structured file list (schema-forced, journaled) — costed fallback when cartography.* is unavailable' },
    { title: 'inventory', detail: 'consumes INPUT.symbolsReceipt written by the EM-side symbols step (preflight, cartography.symbols, whole-artifact coverage read) — zero agent dispatch, no agentic fallback on partial coverage' },
    { title: 'analysis', detail: 'LOW-cap sequential sub-batches: Sonnet per system, narrative analysis + boundary catalog (schema-forced)' },
    { title: 'synthesis', detail: 'LOW-cap Sonnet shard per system (systems/{name}.md), then one cross-system agent for the atlas-wide files' },
  ],
}


// args arrives as a JSON string even when the caller passes a JSON array/object — guard
// unconditionally.
const INPUT = typeof args === 'string' ? JSON.parse(args) : args


// INPUT arrives through the Workflow tool's `inputPath` (a JSON file the EM writes under the run's
// scratch directory), never inline in the invocation — the atlas and chunk table are large.
//   runId: 'YYYY-MM-DD-HHhMM',
//   repoRoot, mode, scaleTier, since, systemDirs, censusBuckets
//   existingAtlas: { <systemName>: { content } }   // refresh only; read from the inputPath file
//   consumeGate: <survey-consume-gate.py stdout> | absent
//   chunkTable: [...] | absent                     // leg 2 of the census-fallback flow
//   symbolsReceipt: <symbols-receipt.schema.json> | absent  // absent -> halt symbols-step-required
//   crossSystemModel, pluginRoot                   // optional overrides
// Results travel by path: manifests carry *_path fields and counts, never census, chunk-table or
// analysis payloads.

const RUN_ID = INPUT.runId
const REPO_ROOT = INPUT.repoRoot
const MODE = INPUT.mode || 'first-run'
const SCALE_TIER = INPUT.scaleTier || 'full'
const CENSUS_BUCKETS = INPUT.censusBuckets || []
const EXISTING_ATLAS = INPUT.existingAtlas || {}
const SYMBOLS_RECEIPT = INPUT.symbolsReceipt || null

const SCRATCH_DIR = `${REPO_ROOT}/state/scratch/deep-architecture-survey/${RUN_ID}`

// ---------------------------------------------------------------------------------------------
// Concurrency — LOW hard cap (~4), sequential sub-batches, ramp. (findings #6, #8, #9, #13)
// ---------------------------------------------------------------------------------------------
// Burst ARRIVAL-RATE is what trips the account-level cooldown, not merely wave width — a
// concurrency-cap OPTION passed to a single parallel() call does not bound arrival rate if the
// tool still fires all N `agent()` calls at once internally. This script therefore does the
// capping itself: split the work array into ramped sub-batches (sizes below) and `await` each
// sub-batch's `parallel()` call to completion before starting the next — batches are NEVER
// in flight concurrently. RAMP_SCHEDULE starts smaller than the steady-state cap and grows
// only after a batch fully succeeds, so a cold-account first batch never risks the full cap.
// RAMP_SCHEDULE is the one source of truth for the steady-state cap.
const RAMP_SCHEDULE = [2, 3, 4] // first batch=2, second=3, steady-state=4 thereafter

function rampSizeFor(batchIndex) {
  return RAMP_SCHEDULE[Math.min(batchIndex, RAMP_SCHEDULE.length - 1)]
}

function chunkArray(items, sizeFn) {
  const out = []
  let i = 0
  let batchIndex = 0
  while (i < items.length) {
    const size = sizeFn(batchIndex)
    out.push(items.slice(i, i + size))
    i += size
    batchIndex += 1
  }
  return out
}

// ---------------------------------------------------------------------------------------------
// Exponential-backoff-on-429 — deep enough to outlast a multi-minute account cooldown.
// ---------------------------------------------------------------------------------------------
// The friction log's empirical floor is an OBSERVED ~8-minute cooldown (finding #10: "After an
// 8-min cooldown, the sequential-sub-batch-of-4 Workflow drained all 17 remaining analysts, 0
// failures"). The Workflow tool's own default terminal-error retry exhausts in ~24s (finding
// #9) — far too shallow. This wrapper retries a sub-batch's `parallel()` call with exponential
// backoff whose CUMULATIVE wait exceeds 8 minutes before giving up, so a sub-batch that lands on
// an already-hot account rides out the cooldown instead of failing immediately.
//
// Backoff schedule (seconds): 30, 60, 120, 240, 300 (capped) — cumulative ~11.5 min > 8 min floor.
const BACKOFF_SCHEDULE_MS = [30_000, 60_000, 120_000, 240_000, 300_000]

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// Detect a rate-limit / throttle failure from a settled agent() result. A throttled agent
// typically returns null/undefined (per the `.filter(Boolean)` convention this pipeline shares
// with the distill twin) or an object explicitly flagging a provider throttle — check both
// shapes defensively since the exact throttle signal is provider-surfaced, not schema-owned.
function looksThrottled(result) {
  if (!result) return true
  if (result.rate_limited === true) return true
  if (typeof result.error === 'string' && /rate.?limit|429|temporarily limiting/i.test(result.error)) return true
  return false
}

// Runs one sub-batch of thunks via parallel(), retrying the WHOLE sub-batch under exponential
// backoff if every member looks throttled (a sub-batch where SOME agents succeeded and some
// merely failed for unrelated reasons is not re-run wholesale here — the caller's failed-id
// bookkeeping re-dispatches only the missing ones on the NEXT top-level Workflow resume via
// resumeFromRunId, per the shared primitive's contract).
async function runBatchWithBackoff(thunks, label) {
  let lastResults = []
  for (let attempt = 0; attempt <= BACKOFF_SCHEDULE_MS.length; attempt += 1) {
    // Preserve raw (pre-.filter(Boolean)) results so we can discriminate
    // "every failure looks like a provider throttle" from "some agents crashed for unrelated
    // reasons" before committing to a full ~11.5min backoff schedule. Wiring
    // looksThrottled here means a non-throttle failure (e.g. a schema violation) does not pay
    // the full backoff — only a sub-batch where EVERY settled result looks throttled does.
    const rawResults = await parallel(thunks)
    lastResults = rawResults.filter(Boolean)
    const allLookThrottled = thunks.length > 0 && rawResults.every((r) => looksThrottled(r))
    if (!allLookThrottled) return lastResults
    if (attempt === BACKOFF_SCHEDULE_MS.length) {
      log(`${label}: exhausted backoff schedule (cumulative ~${BACKOFF_SCHEDULE_MS.reduce((a, b) => a + b, 0) / 1000}s) — all agents still throttled, giving up on this sub-batch`)
      return lastResults
    }
    const waitMs = BACKOFF_SCHEDULE_MS[attempt]
    log(`${label}: sub-batch fully throttled (attempt ${attempt + 1}), backing off ${waitMs / 1000}s before retry`)
    await sleep(waitMs)
  }
  return lastResults
}

// Drains `items` through `thunkFor` in ramped, sequential, backoff-protected sub-batches. This
// is the single low-level primitive every phase below uses — it is what makes "never hand-fire
// a wide wave" (finding #9's anti-scope) structurally true rather than a convention someone has
// to remember.
async function drainLowCap(items, thunkFor, phaseLabel) {
  const batches = chunkArray(items, rampSizeFor)
  const allResults = []
  for (let b = 0; b < batches.length; b += 1) {
    const batch = batches[b]
    log(`${phaseLabel}: sub-batch ${b + 1}/${batches.length} (${batch.length} agents, ramp size ${rampSizeFor(b)})`)
    const thunks = batch.map((item) => () => thunkFor(item))
    const results = await runBatchWithBackoff(thunks, `${phaseLabel} sub-batch ${b + 1}`)
    allResults.push(...results)
  }
  return allResults
}

const COMMON = `Repo: ${REPO_ROOT}. Do NOT git commit (EM commits from the returned manifest). ` +
  `No out-of-scope edits — this pipeline is RESEARCH ONLY, do not modify source files. ` +
  `Keep your task under ~10 minutes; if bigger, do the core and report what remains.`

// ---------------------------------------------------------------------------------------------
// Phase "0.5" — the consume-gate (C-integrate; hoisted off the agent lane, 2026-08-20). Consumes
// `INPUT.consumeGate`, the stdout of `coordinator/bin/survey-consume-gate.py` — an EM-side,
// pure-stdlib script the caller runs BEFORE this Workflow is invoked and passes through as a
// pure pass-through (see coordinator/commands/architecture-survey.md § Phase 0). This Workflow
// dispatches zero agents for this phase: it only reads the already-validated payload and falls
// back to the Phase-0 agentic census wave when `INPUT.consumeGate` is absent, malformed, or
// declined (`{ok: false, declined_reason}`, per the script's failure contract) — the same
// disposition a declined op produced before the hoist. See
// coordinator/docs/wiki/coordinator-tripwires/workflow-agent-as-file-handle.md for why this work
// never belonged behind `agent()`.
//
// Chunk-K retirement (claude-klabauter consume-contract, 2026-07-12): the untested inline bash at the
// (retired) coordinator/commands/architecture-survey.md:104-120 refresh churn/emergent-set pass
// (churned-all.txt / catalogued.txt diff, with its collation / deleted-at-HEAD / source-dir-
// prefilter footguns) is replaced by `cartography.churn` for mode === 'refresh' runs, invoked by
// the script above and consumed here as `INPUT.consumeGate.churn_result`. Per the C5 contract's
// Decision-application-boundary invariant, that op returns computed sets ONLY — the chunk-K
// threshold decision (emergent non-empty OR churn > 50% of catalogued) is THIS pipeline's call,
// not the op's, and no code here applies it: `churn_result` is only ever reported into
// `consumeGateStatus.churn_result` below, a documented gate that does not fire, pre-existing and
// out of scope.
// ---------------------------------------------------------------------------------------------

function phaseZeroFiveConsumeGate() {
  phase('consume-gate')
  const consumeGate = INPUT.consumeGate

  let ragPresent = false
  let churnResult = null
  let chunkTablePayload = null
  if (consumeGate && typeof consumeGate === 'object') {
    ragPresent = !!consumeGate.rag_present
    churnResult = consumeGate.churn_result || null
    chunkTablePayload = consumeGate.chunk_table || null
  }

  let censusResults = null
  let cartographyUsed = false
  let cartographyOversizedSignal = 'unavailable'

  if (chunkTablePayload && chunkTablePayload.ok) {
    censusResults = chunkTablePayload.censusShapedResults
    cartographyUsed = true
    cartographyOversizedSignal = chunkTablePayload.oversizedSignalAvailable ? 'available' : 'unavailable'
    log(`consume-gate: consumed INPUT.consumeGate — cartography.chunk_table extraction succeeded (${censusResults.length} system(s), artifact at ${chunkTablePayload.chunkTablePath}, oversized signal ${cartographyOversizedSignal}) — skipping the agentic census wave entirely`)
  } else if (chunkTablePayload && !chunkTablePayload.ok) {
    log(`consume-gate: INPUT.consumeGate declined the cartography.chunk_table path (${chunkTablePayload.declined_reason}) — falling back to the agentic census wave`)
  } else if (!consumeGate || typeof consumeGate !== 'object') {
    log('consume-gate: INPUT.consumeGate absent or malformed — falling back to the agentic census wave')
  } else {
    log(`consume-gate: consumed INPUT.consumeGate — rag_present=${ragPresent}, no cartography extraction attempted this run — falling back to the agentic census wave`)
  }

  return { ragPresent, churnResult, censusResults, cartographyUsed, cartographyOversizedSignal }
}

// ---------------------------------------------------------------------------------------------
// Phase "census" — deterministic-shaped structural extraction (the costed agentic fallback when
// the consume-gate above reports RAG-absent but a cartography.* op is unavailable/declined, OR
// when the gate reports RAG-present — in which case the survey should already be reading via
// mcp__*project-rag*, and this wave's presence here is legacy pre-C-integrate behavior for a
// caller that hasn't wired that path yet). Returns a per-bucket file list + line counts as
// STRUCTURED data; clustering into the Phase-1 chunk table happens in plain JS below, zero
// agent cost, exactly matching the pattern the distill twin uses for nugget->topic clustering.
// ---------------------------------------------------------------------------------------------

const CENSUS_SCHEMA = {
  type: 'object',
  required: ['bucket_id', 'files'],
  properties: {
    bucket_id: { type: 'string' },
    files: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'loc'],
        properties: {
          path: { type: 'string' },
          loc: { type: 'number' },
          oversized: { type: 'boolean' }, // true when loc > 800 (C4's Read-pagination flag)
        },
      },
    },
    anomalies: { type: 'array', items: { type: 'string' } },
  },
}

function censusBriefFor(bucket) {
  return COMMON + `

You are a Haiku structural-census agent (Phase-0 of the /architecture-survey Workflow).

Your assigned bucket: ${bucket.bucketId} — ${bucket.description}
Directories/files to enumerate: ${JSON.stringify(bucket.dirs)}

List every SOURCE file under your assigned directories (use \`find\` / \`ls\` — do not read file
contents, this is enumeration only) and its line count (\`wc -l\`). Flag any file with loc > 800
as oversized: true (feeds the Phase-1 Read-pagination guard). Do NOT analyze, summarize, or
evaluate any file — this is mechanical enumeration, the same shape a deterministic claude-klabauter
\`arch-census\` op will eventually replace (coordinator/docs/contracts/arch-engine-scripts.md).

Return the structured object with your full file list, and also Write that same object as JSON to
${SCRATCH_DIR}/census/${bucket.bucketId}.json (create the directory if missing): the EM-side
symbols step reads the per-bucket files from there, not from your reply.`
}

async function phaseZeroCensus() {
  phase('census')
  if (CENSUS_BUCKETS.length === 0) {
    log('census: no censusBuckets provided — INPUT already carries a precomputed chunk table (e.g. a C-integrate-consumed cartography.* payload); skipping census wave')
    return []
  }
  const results = await drainLowCap(
    CENSUS_BUCKETS,
    (bucket) => agent(censusBriefFor(bucket), {
      schema: CENSUS_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'census',
      label: bucket.bucketId,
      model: 'haiku',
    }),
    'census'
  )
  return results
}

// Census oversized-set verification leg. One union invocation over every bucket's dirs: the agent
// is handed directories only and returns threshold-crossing paths plus one integer, so neither
// side can truncate and nothing the census claimed ever reaches it.
const CENSUS_OVERSIZED_THRESHOLD = 801 // matches CARTOGRAPHY_OVERSIZED_THRESHOLD

const CENSUS_REMEASURE_SCHEMA = {
  type: 'object',
  required: ['oversizedPaths', 'totalFiles'],
  properties: {
    oversizedPaths: { type: 'array', items: { type: 'string' } },
    totalFiles: { type: 'number' },
  },
}

function censusRemeasureBriefFor(dirs) {
  return COMMON + `

You are a mechanical command-runner (Phase-0 census verification of the /architecture-survey
Workflow). Do NOT judge, summarize, or analyze anything, and do NOT read file contents yourself.

Run exactly this command and capture its stdout. Copy it verbatim, including the quoted heredoc
delimiter (<<'PY') and the closing PY line:

  python3 - <<'PY'
import json, os
dirs = json.loads(r'''${JSON.stringify(dirs)}''')
skip = {".git", "node_modules", "__pycache__"}
paths = []
for d in dirs:
    if os.path.isfile(d):
        paths.append(d)
        continue
    for root, names, files in os.walk(d):
        names[:] = [n for n in names if n not in skip]
        for f in files:
            paths.append(os.path.join(root, f).replace(os.sep, "/"))
paths = sorted(set(paths))
over = []
for p in paths:
    try:
        with open(p, "rb") as fh:
            n = fh.read().count(b"\\n")
    except OSError:
        continue
    if n >= ${CENSUS_OVERSIZED_THRESHOLD}:
        over.append(p)
print(json.dumps({"oversizedPaths": over, "totalFiles": len(paths)}))
PY

Parse that stdout as JSON and return its two fields unchanged. On any non-zero exit, report the
failure and return no counts — do NOT estimate, infer, or reconstruct them by other means. Do not
write any output file.`
}

async function remeasureCensusOversized(dirs) {
  const results = await runBatchWithBackoff(
    [() => agent(censusRemeasureBriefFor(dirs), {
      schema: CENSUS_REMEASURE_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'census',
      label: 'census-oversized-remeasure',
      model: 'haiku',
    })],
    'census oversized-remeasure'
  )
  return results[0] || null
}

// Pure: overwrites each census file's `oversized` with membership in the measured set. Returns
// the corrected results and the paths whose flag flipped. No agent() call, no logging.
function reconcileCensusLoc(censusResults, measuredOversizedPaths) {
  const measured = new Set(measuredOversizedPaths || [])
  const divergences = []
  const corrected = censusResults.map((bucket) => ({
    ...bucket,
    files: (bucket.files || []).map((f) => {
      const truth = measured.has(f.path)
      if (!!f.oversized !== truth) divergences.push(f.path)
      return { ...f, oversized: truth }
    }),
  }))
  return { corrected, divergences }
}


// Deterministic in-JS clustering of census files into Phase-1 sub-chunks by directory/prefix,
// at zero agent cost.
function buildChunkTable(censusResults) {
  const SUBCHUNK_SIZE = 10 // midpoint of the 8-12-file sub-chunk rule
  const chunks = []
  for (const bucket of censusResults) {
    const files = (bucket.files || []).map((f) => f.path)
    const oversized = (bucket.files || []).filter((f) => f.oversized).map((f) => f.path)
    if (files.length === 0) continue
    const subChunkCount = Math.ceil(files.length / SUBCHUNK_SIZE)
    for (let i = 0; i < subChunkCount; i += 1) {
      const slice = files.slice(i * SUBCHUNK_SIZE, (i + 1) * SUBCHUNK_SIZE)
      const subChunkLabel = subChunkCount > 1 ? String.fromCharCode(65 + i) : '—' // A, B, C... or — for single-chunk systems
      chunks.push({
        systemName: bucket.bucket_id,
        subChunkLabel,
        files: slice,
        oversizedFiles: oversized.filter((p) => slice.includes(p)),
      })
    }
  }
  return chunks
}


// Groups Phase-1 chunks back up by systemName for the Phase-2 one-analyst-per-system dispatch.
function groupChunksBySystem(chunks) {
  const bySystem = new Map()
  for (const c of chunks) {
    if (!bySystem.has(c.systemName)) bySystem.set(c.systemName, [])
    bySystem.get(c.systemName).push(c)
  }
  return [...bySystem.entries()].map(([systemName, systemChunks]) => ({ systemName, chunks: systemChunks }))
}


// Receipt halts the EM-side symbols step (survey_symbols_step.py) may write; each is returned as
// this run's `halted` label verbatim. Schema: symbols-receipt.schema.json.
const RECEIPT_HALTS = [
  'symbol-extract-missing',
  'symbols-artifact-preexists',
  'symbols-producer-failed',
  'symbols-coverage-truncated',
  'symbols-extractor-unavailable',
]

// Deduped, request-ordered file list across every Phase-1 sub-chunk — the single
// `cartography.symbols` invocation's `files` param.
function buildSymbolsFileList(chunkTable) {
  const seen = new Set()
  const files = []
  for (const chunk of chunkTable) {
    for (const f of chunk.files) {
      if (!seen.has(f)) {
        seen.add(f)
        files.push(f)
      }
    }
  }
  return files
}

// Phase "inventory": consumes INPUT.symbolsReceipt, the receipt the EM-side symbols step
// (survey_symbols_step.py) wrote after running the preflight, the pre-existence check and
// `cartography.symbols`, and reading the artifact whole. No agent runs here: the Workflow has no
// filesystem or subprocess primitive, so a Haiku "file handle" for that work is the
// workflow-agent-as-file-handle tell. No agentic fallback on partial coverage either: a stop here
// writes no atlas rather than narrowing the tree silently. Unsupported extensions are the one
// narrowing that is allowed, because no producer claims them and nothing can be installed to fix it.
//
// Returns { halted, ... } (a distinct label, detail logged) or { symbolsArtifactPath, ... }.
function phaseOneSymbolsExtraction(chunkTable) {
  phase('inventory')
  const files = buildSymbolsFileList(chunkTable)

  const receipt = SYMBOLS_RECEIPT
  if (!receipt || typeof receipt !== 'object') {
    log('inventory: INPUT.symbolsReceipt absent — the EM-side symbols step has not run for this chunk table; halting so the caller runs it and re-invokes')
    return { halted: 'symbols-step-required' }
  }

  if (receipt.halt || receipt.ok !== true) {
    const label = RECEIPT_HALTS.includes(receipt.halt) ? receipt.halt : 'symbols-producer-failed'
    const sample = (receipt.unavailable_sample || []).map((u) => `${u.path} (${u.reason})`).join('; ')
    log(`inventory: symbols step halted with ${receipt.halt || 'no halt label on a not-ok receipt'}${label !== receipt.halt ? ` (reported as ${label})` : ''}${sample ? ` — affected: ${sample}` : ''}${receipt.coverage_note ? ` — coverage_note: ${receipt.coverage_note}` : ''}`)
    return { halted: label }
  }

  if (typeof receipt.total_files !== 'number' || receipt.total_files !== files.length) {
    log(`inventory: symbols artifact carries ${receipt.total_files} file entries, chunk table requests ${files.length} — truncation/containment fault, stopping (no agentic fallback)`)
    return { halted: 'symbols-coverage-truncated' }
  }

  // `unavailable` (a claimed extension whose extractor is absent) is a fixable install fault and
  // stops the run; `unsupported` (no producer claims the extension) narrows the inventory.
  if (receipt.unavailable_count > 0) {
    log(`inventory: ${receipt.unavailable_count} of ${files.length} requested file(s) could not be attempted by an extractor that claims them — stopping rather than narrowing the tree silently (no agentic fallback)`)
    return { halted: 'symbols-extractor-unavailable' }
  }

  const inventoriedCount = receipt.total_files - receipt.unsupported_count
  if (receipt.unsupported_count > 0) {
    const breakdown = (receipt.unsupported_extensions || []).map((e) => `${e.ext} x${e.count}`).join(', ')
    log(`inventory: NARROWED PASS — ${receipt.unsupported_count} of ${files.length} requested file(s) carry extensions no symbol producer claims and are excluded; ${inventoriedCount} file(s) are inventoried. Excluded by extension: ${breakdown}`)
  } else {
    log(`inventory: symbols step covered all ${receipt.total_files} requested file(s), artifact at ${receipt.artifact_path}`)
  }

  return {
    symbolsArtifactPath: receipt.artifact_path,
    chunkTablePath: receipt.chunk_table_path || null,
    totalFiles: receipt.total_files,
    inventoriedCount,
    excludedByExtension: receipt.unsupported_extensions || [],
  }
}

// ---------------------------------------------------------------------------------------------
// Phase "analysis" — Sonnet system analysis, one agent per system, reading ALL its sub-chunk
// inventories. Same LOW-cap sequential-sub-batch treatment as Phase-1 — this is exactly the
// wave that tripped the account-level rate limit in the friction log (21 Sonnet analysts fired
// at once, findings #6-#9).
// ---------------------------------------------------------------------------------------------

const CENSUS_DIR = `${SCRATCH_DIR}/census`

const ANALYSIS_SCHEMA = {
  type: 'object',
  required: ['analysis_path'],
  properties: {
    // market-intel signal #1 / AC3: RETURNED path is authoritative, not the suggested one.
    analysis_path: { type: 'string' },
    boundary_count: { type: 'number' },
    partial: { type: 'boolean' },
    anomalies: { type: 'array', items: { type: 'string' } },
  },
}

function analysisBriefFor(system, symbolsArtifactPath) {
  const suggestedPath = `${SCRATCH_DIR}/${system.systemName}-phase2-sonnet.md`
  const existingPage = EXISTING_ATLAS[system.systemName]
  const refreshNote = existingPage
    ? `\n\nThis is a REFRESH — existing atlas page below. Preserve unchanged sections verbatim; update only what the inventory shows changed.\n\n### Existing Atlas Page\n${existingPage.content}`
    : ''

  return COMMON + `

You are a Sonnet system-analysis agent (Phase-2 of the /architecture-survey Workflow).

System: ${system.systemName}
Scale tier: ${SCALE_TIER} (narrative tier: describe boundaries/roles in prose rather than
enumerate every symbol; full/hybrid tier: standard per-function analysis).

### Phase-1 Symbol Table
Read ${symbolsArtifactPath} directly (Read tool) — it is the \`{"files": [...]}\` envelope
\`cartography.symbols\` returns, one entry per file across the whole run. Filter it down to the
entries whose "path" is one of this system's files: ${JSON.stringify(system.files)}. Use those
entries as your function-level inventory (classes, functions, constants); determine caller/callee
and cross-subsystem relationships yourself by reading the source files directly where the symbol
table alone does not make a relationship explicit.
${refreshNote}

Produce the full system analysis per the Phase-2 Discovery template in
coordinator/pipelines/deep-architecture-survey/agent-prompts.md: System Narrative, Information
Flow Diagram (ASCII, max 100 chars wide), Boundary Catalog (exhaustive — every entry point and
boundary crossing you find), Key Architectural Observations (Strengths/Concerns/Notable
Patterns — no grade, this is discovery not audit), Summary (top 3-5 aspects).

**Enforce stable H2 section anchors** (##  System Narrative, ## Information Flow Diagram,
## Boundary Catalog, ## Key Architectural Observations, ## Summary) exactly as named — the
Phase-3 condense-analyst-pages helper (C4) extracts sections by matching these H2 headers
verbatim; a wrong header level or reworded heading breaks that extraction.

Write your complete analysis to: ${suggestedPath}. Return the real path as analysis_path. This
is RESEARCH ONLY — do not modify any source file.`
}

async function phaseTwoAnalysis(systems, symbolsArtifactPath) {
  phase('analysis')
  if (systems.length === 0) {
    log('analysis: no systems to dispatch — halting')
    return []
  }
  return drainLowCap(
    systems,
    (system) => agent(analysisBriefFor(system, symbolsArtifactPath), {
      schema: ANALYSIS_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'analysis',
      label: system.systemName,
      model: 'sonnet',
    }).then((r) => (r ? { ...r, system_name: system.systemName } : r)),
    'analysis'
  )
}

// ---------------------------------------------------------------------------------------------
// Phase "synthesis" — one Sonnet shard per system (each writes systems/{name}.md, drained at the
// LOW cap with backoff), then one cross-system agent for the atlas-wide files. One agent over all
// systems overflows its context at scale; the shard count is the system count.
//
// CONDENSE_HOOK (review-corrected, findings #6/#7): this Workflow script has NO in-script
// filesystem primitive (agent/parallel/phase/log is the whole API — see the file header docstring
// and workflow-orchestration.md) — it can never itself Read `analysis_path` off disk to inline
// real content. Every phase boundary in this script (see the identical pattern at the Phase-1 ->
// Phase-2 boundary above) therefore passes a PATH REFERENCE, not pasted content, and relies on
// the RECEIVING agent (which has Read access) to read the file itself. The Phase-3 synthesis
// brief below follows the SAME pattern deliberately: it passes analysis_path references, not
// pasted text, and instructs the Opus agent to Read each path directly and apply the
// condense-analyst-pages extraction (agent-prompts.md § Condense-Analyst-Pages Helper) itself
// when the combined analyst-page content is large. This is the actual, working flow — the C4
// helper's stated caller is this dispatch's Opus agent, not the Workflow script.
// ---------------------------------------------------------------------------------------------

const SYNTHESIS_SCHEMA = {
  type: 'object',
  required: ['artifacts_written', 'systems_count'],
  properties: {
    artifacts_written: { type: 'array', items: { type: 'string' } },
    systems_count: { type: 'number' },
    one_sided_connections: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const SHARD_MODEL = 'sonnet'
// The cross-system agent reads every system page and writes the atlas-wide files; its model is
// the one knob a caller may turn up for a large atlas.
const CROSS_SYSTEM_MODEL = INPUT.crossSystemModel || 'sonnet'
const PLUGIN_ROOT = INPUT.pluginRoot || `${REPO_ROOT}/coordinator`
const ANALYSIS_RESULTS_PATH = `${SCRATCH_DIR}/analysis-results.json`

const PATH_RULE = `Every path you write into the atlas (frontmatter and body alike) is repo-root-relative:
no leading \`/\`, no \`./\`, no drive letter, no home-directory prefix.`

const SYNTHESIS_CONDENSE = `If the analyst pages you Read are large (approaching ~80K tokens / ~300KB combined), apply the
condense-analyst-pages extraction in coordinator/pipelines/deep-architecture-survey/agent-prompts.md
§ Condense-Analyst-Pages Helper to each page: drop the \`## Information Flow Diagram\` H2 section,
keep everything else verbatim. This is text extraction only; do not re-author any analyst's judgment.`

// Shard: one system's atlas page. A shard writes exactly docs/architecture/systems/{name}.md.
function synthesisShardBriefFor(system) {
  return COMMON + `

You are a Sonnet system-page synthesis agent (Phase-3 shard of the /architecture-survey Workflow).
You are a LEAF agent — do NOT spawn further agents.

System: ${system.system_name}
Phase-2 analysis: ${system.analysis_path} — Read it directly (Read tool); the Workflow script that
dispatched you has no filesystem access.
${SYNTHESIS_CONDENSE}

Write ONE file: docs/architecture/systems/${system.system_name}.md, following the per-system page
template and YAML-frontmatter conventions in
coordinator/pipelines/deep-architecture-survey/agent-prompts.md § Phase 3 (last_mapped:, mode:,
entry_points:, cross_system_connections:, dependencies:). Mode: ${MODE}. last_attested is carried
forward from the existing page at that path if one exists and is never written by the survey. No
grade or status fields — this is discovery, not weekly-architecture-audit.

${PATH_RULE}

Do NOT write any other file, any code, or modify any source file. Return artifacts_written
listing the path you wrote, and systems_count 1.`
}

// Cross-system agent: the four atlas-wide files plus analysis-results.json, after the shards.
function synthesisCrossSystemBriefFor(systems) {
  const list = systems
    .map((s) => `- ${s.system_name}: analysis ${s.analysis_path}, page docs/architecture/systems/${s.system_name}.md`)
    .join('\n')
  return COMMON + `

You are the cross-system synthesis agent (Phase-3 of the /architecture-survey Workflow). You are a
LEAF agent — do NOT spawn further agents. The per-system pages already exist, one shard each.

Total systems: ${systems.length}
${list}

Read the system pages and analyses above directly (Read tool).
${SYNTHESIS_CONDENSE}

Write these files per coordinator/pipelines/deep-architecture-survey/agent-prompts.md § Phase 3:
docs/architecture/systems-index.md, docs/architecture/cross-system-map.md,
docs/architecture/connectivity-matrix.md, docs/architecture/file-index.md. Every system must appear
in systems-index.md. Every tracked file must appear in file-index.md. Validate cross-system
connections bidirectionally across the system pages.

Then run \`python3 ${PLUGIN_ROOT}/pipelines/deep-architecture-survey/atlas_anchor_reciprocity.py --repo-root ${REPO_ROOT}\`
and fix every one-sided pair or non-repo-root-relative path it lists in the system pages; record
any pair you cannot fix under one_sided_connections.

${PATH_RULE}

Finally write ${ANALYSIS_RESULTS_PATH} as JSON: [{system_name, analysis_path}] for the systems
above (the Workflow returns its path, never its content). Do NOT write code or modify source
files. Return artifacts_written listing every path you wrote, including that JSON file.`
}

const EMPTY_ARTIFACTS = (r) => !r || !Array.isArray(r.artifacts_written) || r.artifacts_written.length === 0

// Returns { shardResults, failedShards, emptyShards, crossSystem } or null when there is nothing
// to synthesize. Shards drain through the same LOW-cap ramp + backoff as analysis; the
// cross-system agent runs after every shard finished.
async function phaseThreeSynthesis(analysisResults) {
  phase('synthesis')
  if (analysisResults.length === 0) {
    log('synthesis: no analysis results to synthesize — halting')
    return null
  }
  const shardResults = await drainLowCap(
    analysisResults,
    (system) => agent(synthesisShardBriefFor(system), {
      schema: SYNTHESIS_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'synthesis',
      label: `synth-${system.system_name}`,
      model: SHARD_MODEL,
    }).then((r) => (r ? { ...r, system_name: system.system_name } : r)),
    'synthesis shards'
  )
  const failedShards = analysisResults
    .map((s) => s.system_name)
    .filter((name) => !shardResults.some((r) => r.system_name === name))
  const emptyShards = shardResults.filter(EMPTY_ARTIFACTS).map((r) => r.system_name)
  if (failedShards.length > 0 || emptyShards.length > 0) {
    return { shardResults, failedShards, emptyShards, crossSystem: null }
  }

  const crossResults = await runBatchWithBackoff(
    [() => agent(synthesisCrossSystemBriefFor(analysisResults), {
      schema: SYNTHESIS_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'synthesis',
      label: 'cross-system-synthesis',
      model: CROSS_SYSTEM_MODEL,
    })],
    'synthesis cross-system'
  )
  return { shardResults, failedShards, emptyShards, crossSystem: crossResults[0] || null }
}

// ---------------------------------------------------------------------------------------------
// Orchestration — anti-scope reminder: NEVER hand-fire a wide wave first (finding #9). Every
// wave below — including the consume-gate and census waves — goes through
// drainLowCap/runBatchWithBackoff.
// ---------------------------------------------------------------------------------------------

// existingAtlas coverage check — surfaced before any phase spends anything, per the INPUT
// contract note above. `--refresh` preserves unchanged sections only for systems present in
// existingAtlas (see analysisBriefFor's existingPage lookup); an absent, empty, or partial
// supply degrades those systems to full regeneration silently unless logged here.
if (MODE === 'refresh') {
  const suppliedSystemCount = Object.keys(EXISTING_ATLAS).length
  const expectedSystemCount = (INPUT.systemDirs || []).length
  if (suppliedSystemCount === 0 || (expectedSystemCount > 0 && suppliedSystemCount < expectedSystemCount)) {
    log(`consume-gate: existingAtlas supplied ${suppliedSystemCount} system(s), this refresh expects ${expectedSystemCount || 'an uncounted number of'} — preserve-unchanged-sections is OFF for the uncovered systems, every one of their pages will be regenerated from scratch`)
  }
}

// Phase-0.5 consume-gate (C-integrate; hoisted off the agent lane). Consumes INPUT.consumeGate,
// produced by coordinator/bin/survey-consume-gate.py before this Workflow was invoked. Absent,
// malformed, or declined -> the agentic census wave below runs unchanged, the same disposition a
// declined op produced before the hoist.
const gate = phaseZeroFiveConsumeGate()
const churnResult = gate.churnResult

let censusResults = gate.censusResults
let failedCensusBuckets = []
let cartographyUsed = gate.cartographyUsed
let cartographyOversizedSignal = gate.cartographyOversizedSignal

if (!cartographyUsed) {
  censusResults = await phaseZeroCensus()
  failedCensusBuckets = CENSUS_BUCKETS
    .map((b) => b.bucketId)
    .filter((id) => !censusResults.some((r) => r.bucket_id === id))

  // Ratified behaviour: correct-and-log. The census's self-reported `oversized` is overwritten by
  // the measured set and each flipped path is logged; only a failed measurement halts.
  if (censusResults.length > 0) {
    const unionDirs = [...new Set(CENSUS_BUCKETS.flatMap((b) => b.dirs || []))]
    const measured = await remeasureCensusOversized(unionDirs)
    const hasFiles = censusResults.some((r) => (r.files || []).length > 0)
    if (!measured || !Array.isArray(measured.oversizedPaths) || typeof measured.totalFiles !== 'number' || (measured.totalFiles === 0 && hasFiles)) {
      log('census: oversized-set re-measure failed to return a usable count — stopping (no agentic fallback)')
      return {
        phase_reached: 'census',
        halted: 'census-verification-failed',
        run_id: RUN_ID,
        census_dir: CENSUS_DIR,
        census_bucket_count: censusResults.length,
        failed_census_buckets: failedCensusBuckets,
      }
    }
    const reconciled = reconcileCensusLoc(censusResults, measured.oversizedPaths)
    censusResults = reconciled.corrected
    log(`census: re-measured ${measured.totalFiles} file(s), ${measured.oversizedPaths.length} oversized; corrected ${reconciled.divergences.length} divergent oversized flag(s)${reconciled.divergences.length ? ': ' + reconciled.divergences.join(', ') : ''}`)
  }
}

const chunkTable = censusResults.length > 0 ? buildChunkTable(censusResults) : (INPUT.chunkTable || [])

// Consume-gate observability, folded into every returned manifest below so a resumed/inspected
// run always shows whether cartography.* or the agentic fallback produced the chunk table.
const consumeGateStatus = {
  rag_present: gate.ragPresent,
  cartography_used: cartographyUsed,
  // Measured, never inferred from which branch ran: the deterministic path carries the signal
  // whenever the producer reply came back with an `oversized` list, and an older producer that
  // ignores `oversized_threshold` is the one case that still reports unavailable. Reporting which
  // branch fired instead of what the payload carried is what let a live capability read as a
  // producer gap for two weeks. Emitted on both branches rather than only when unavailable: a
  // missing key reads as "not checked", which is the ambiguity this exists to remove.
  oversized_signal: cartographyUsed ? cartographyOversizedSignal : 'available',
  churn_result: churnResult,
}

if (chunkTable.length === 0) {
  return {
    phase_reached: 'census',
    halted: 'empty-chunk-table',
    run_id: RUN_ID,
    ...consumeGateStatus,
    census_dir: CENSUS_DIR,
    census_bucket_count: censusResults.length,
    failed_census_buckets: failedCensusBuckets,
  }
}

const symbolsExtraction = phaseOneSymbolsExtraction(chunkTable)

// Pointer facts shared by every manifest from here on: counts and paths, never the payloads.
const chunkTablePath = (SYMBOLS_RECEIPT && SYMBOLS_RECEIPT.chunk_table_path) || null
const payloadPointers = {
  census_dir: CENSUS_DIR,
  chunk_table_path: chunkTablePath,
  chunk_table_size: chunkTable.length,
  census_bucket_count: censusResults.length,
}

if (symbolsExtraction.halted) {
  // 'symbols-step-required' is the census-fallback leg-1 end: the EM runs the symbols step over
  // census_dir and re-invokes with chunkTable + symbolsReceipt. Every other label is the receipt's
  // own halt, passed through verbatim.
  return {
    phase_reached: 'inventory',
    halted: symbolsExtraction.halted,
    run_id: RUN_ID,
    ...consumeGateStatus,
    ...payloadPointers,
    failed_census_buckets: failedCensusBuckets,
    symbols_receipt: SYMBOLS_RECEIPT
      ? { halt: SYMBOLS_RECEIPT.halt || null, artifact_path: SYMBOLS_RECEIPT.artifact_path || null, total_files: SYMBOLS_RECEIPT.total_files, requested_files: SYMBOLS_RECEIPT.requested_files, unavailable_count: SYMBOLS_RECEIPT.unavailable_count, unsupported_count: SYMBOLS_RECEIPT.unsupported_count }
      : null,
    resume_hint: 'No agentic fallback exists for this stop. symbols-step-required: run the EM-side symbols step (--census-dir for the census-fallback path) and re-invoke with symbolsReceipt in the inputPath file. Any other label: resolve the named producer/coverage gap, then re-run the symbols step.',
  }
}

// In-JS regroup — zero agent cost. Builds the per-system file-list bundle Phase-2 needs; the
// symbol table itself is read directly by each analysis agent from
// symbolsExtraction.symbolsArtifactPath, never pasted through this script.
const systemsGrouped = groupChunksBySystem(chunkTable)
const systemsWithFiles = systemsGrouped.map((s) => ({
  systemName: s.systemName,
  files: [...new Set(s.chunks.flatMap((c) => c.files))],
}))

const analysisResults = await phaseTwoAnalysis(systemsWithFiles, symbolsExtraction.symbolsArtifactPath)
const failedAnalysisSystems = systemsWithFiles
  .map((s) => s.systemName)
  .filter((name) => !analysisResults.some((r) => r.system_name === name))

if (analysisResults.length === 0) {
  return {
    phase_reached: 'analysis',
    halted: 'all-analysis-agents-failed',
    run_id: RUN_ID,
    ...consumeGateStatus,
    ...payloadPointers,
    symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
    symbols_inventoried_count: symbolsExtraction.inventoriedCount,
    symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
    failed_analysis_systems: failedAnalysisSystems,
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; only failed analysis agent()s re-run.',
  }
}

if (failedAnalysisSystems.length > 0) {
  // Partial analysis failure: report and let the caller resume rather than synthesizing an
  // incomplete atlas. Wave-1 (census) and completed Wave-2 (the symbols extraction + the
  // analysis agents that DID succeed) all replay from the journal for free on resume — only the
  // failed analysis agent()s re-run (the shared Workflow-resume primitive's load-bearing property).
  return {
    phase_reached: 'analysis',
    halted: 'analysis-partial-failure',
    run_id: RUN_ID,
    ...consumeGateStatus,
    ...payloadPointers,
    symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
    symbols_inventoried_count: symbolsExtraction.inventoriedCount,
    symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
    completed_analysis_systems: analysisResults.map((r) => r.system_name),
    failed_analysis_systems: failedAnalysisSystems,
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; only failed analysis agent()s re-run.',
  }
}

const synthesisResult = await phaseThreeSynthesis(analysisResults)
const synthesisPointers = {
  ...consumeGateStatus,
  ...payloadPointers,
  symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
  symbols_inventoried_count: symbolsExtraction.inventoriedCount,
  symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
  completed_analysis_systems: analysisResults.map((r) => r.system_name),
}

if (!synthesisResult || synthesisResult.failedShards.length > 0 || (synthesisResult.emptyShards.length === 0 && !synthesisResult.crossSystem)) {
  return {
    phase_reached: 'synthesis',
    halted: 'synthesis-agent-failed',
    run_id: RUN_ID,
    ...synthesisPointers,
    failed_synthesis_systems: synthesisResult ? synthesisResult.failedShards : analysisResults.map((r) => r.system_name),
    cross_system_ran: !!(synthesisResult && synthesisResult.crossSystem),
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; only the failed synthesis agent()s re-run.',
  }
}

// A synthesis agent that returns without naming a single artifact wrote nothing the EM can commit;
// reporting done:true over it would ship an empty atlas.
const emptySynthesis = [...synthesisResult.emptyShards, ...(synthesisResult.crossSystem && EMPTY_ARTIFACTS(synthesisResult.crossSystem) ? ['cross-system'] : [])]
if (emptySynthesis.length > 0) {
  return {
    phase_reached: 'synthesis',
    halted: 'synthesis-wrote-no-artifacts',
    run_id: RUN_ID,
    ...synthesisPointers,
    empty_synthesis_agents: emptySynthesis,
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; inspect the named synthesis agents before trusting a re-run.',
  }
}

const artifactsWritten = [
  ...synthesisResult.shardResults.flatMap((r) => r.artifacts_written),
  ...synthesisResult.crossSystem.artifacts_written,
]

return {
  done: true,
  run_id: RUN_ID,
  mode: MODE,
  scale_tier: SCALE_TIER,
  systems_count: analysisResults.length,
  ...synthesisPointers,
  failed_census_buckets: failedCensusBuckets,
  analysis_results_path: ANALYSIS_RESULTS_PATH,
  failed_analysis_systems: failedAnalysisSystems,
  synthesis: {
    artifacts_written: artifactsWritten,
    one_sided_connections: [
      ...synthesisResult.shardResults.flatMap((r) => r.one_sided_connections || []),
      ...(synthesisResult.crossSystem.one_sided_connections || []),
    ],
    notes: synthesisResult.crossSystem.notes || null,
  },
}
