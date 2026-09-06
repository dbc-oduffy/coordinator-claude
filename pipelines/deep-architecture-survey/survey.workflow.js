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
 * Doctrine: coordinator/docs/wiki/workflow-orchestration.md (vehicle-choice, chunking,
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
  description: '/architecture-survey Phase 0-3: Phase-0.5 consume-gate (INPUT.consumeGate, script-produced) -> deterministic chunk census fallback -> Haiku inventory -> Sonnet analysis (LOW-cap sequential sub-batches + ramp + backoff) -> Opus synthesis',
  phases: [
    { title: 'consume-gate', detail: 'consumes INPUT.consumeGate (EM-side script output: RAG-present predicate + cartography.* op results) — zero agent dispatch; falls back to the census wave when absent or declined' },
    { title: 'census', detail: 'LOW-cap sequential sub-batches: Haiku per directory-bucket returns structured file list (schema-forced, journaled) — costed fallback when cartography.* is unavailable' },
    { title: 'inventory', detail: 'one cartography.symbols invocation for the whole run, artifact-path consumed with a read-back coverage gate — no agentic fallback on partial coverage' },
    { title: 'analysis', detail: 'LOW-cap sequential sub-batches: Sonnet per system, narrative analysis + boundary catalog (schema-forced)' },
    { title: 'synthesis', detail: 'single Opus leaf: cross-system atlas artifacts' },
  ],
}

// ---------------------------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------------------------
// `args` arrives as a JSON string even when the caller passes a JSON array/object
// (state/lessons/2026-07-09-workflow-args-arrives-as-a-json-string — guard unconditionally).
const INPUT = typeof args === 'string' ? JSON.parse(args) : args

// Expected INPUT shape (produced by the /architecture-survey skill's Phase 0 preface — repo
// detection, mode selection, scale-tier selection per C2 all happen BEFORE this Workflow is
// invoked; this script owns dispatch+poll+condense+synthesize only, not mode/tier selection):
// {
//   runId: 'YYYY-MM-DD-HHhMM',
//   repoRoot: '/absolute/path/to/repo',
//   mode: 'first-run' | 'refresh' | 'targeted',
//   scaleTier: 'narrative' | 'full' | 'hybrid',
//   censusBuckets: [ { bucketId: 'bin-cli', description: '...', dirs: ['coordinator/bin', ...] }, ... ],
//   existingAtlas: { systemName: { path: 'docs/architecture/systems/<name>.md', content: '...' }, ... } | {},
//     Full page bodies do not survive above the tool-call arg budget — a 486 KB atlas already
//     forced one caller to pass {}. The honest options above that ceiling are supplying a subset
//     of systems (accepting regeneration for the rest) or accepting full regeneration outright;
//     there is no shape that carries a large atlas whole. A caller under the ceiling should
//     always supply the full map — see the coverage check at the top of Orchestration below,
//     which surfaces the tradeoff loudly on '--refresh' the moment it is made, not after the spend.
//   resumeFromRunId: '<prior-run-id>' | null,  // caller-supplied; the Workflow tool itself
//                                               // consumes this at invocation time, not in-script
//   since: 'YYYY-MM-DD' | null,        // no longer read by this script — duplicated onto
//                                       // coordinator/bin/survey-consume-gate.py's own stdin
//                                       // config, which invokes cartography.churn itself
//   systemDirs: ['<dir>', ...] | null, // RETAINED here (not moved off INPUT): the existingAtlas
//                                       // coverage check below consumes it independently of the
//                                       // consume-gate script's own duplicated copy
//   excludedDirs: ['<dir>', ...] | null, // no longer read by this script — duplicated onto the
//                                         // consume-gate script's own stdin config, same as `since`
//   consumeGate: { rag_present, rag_predicate, chunk_table, churn_result } | null, // stdout of
//     coordinator/bin/survey-consume-gate.py, passed through by the caller as a pure pass-through
//     (Phase 0 does not branch on it). chunk_table is either null (rag_present true, no
//     cartography extraction attempted), { ok: false, declined_reason } (a declined
//     consumer-side check), or { ok: true, censusShapedResults, chunkTablePath, counts,
//     oversizedSignalAvailable, oversizedCount } on success. Absent, malformed, or declined ->
//     this Workflow falls back to the agentic census wave — see phaseZeroFiveConsumeGate().
// }
const RUN_ID = INPUT.runId
const REPO_ROOT = INPUT.repoRoot
const MODE = INPUT.mode || 'first-run'
const SCALE_TIER = INPUT.scaleTier || 'full'
const CENSUS_BUCKETS = INPUT.censusBuckets || []
const EXISTING_ATLAS = INPUT.existingAtlas || {}
// Absolute path to a claude-klabauter checkout — required transport for Phase 1's
// `cartography.symbols` invocation below (coordinator_core is only importable from inside that
// checkout). The Phase-0.5 cartography.* op invocations moved to
// coordinator/bin/survey-consume-gate.py and no longer read this; `invokeSymbolsExtraction`
// (Phase 1) is this constant's sole remaining consumer. Caller-supplied, no default, no
// filesystem inference: see invokeSymbolsExtraction's fail-loud check.
const CLAUDE_KLABAUTER_ROOT = INPUT.claude_klabauterRoot
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
// Review: code-reviewer — RAMP_SCHEDULE is the one source of truth for the steady-state cap;
// the formerly-separate BATCH_SIZE constant was unused and misleadingly named (finding #5).
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
    // Review: code-reviewer — preserve raw (pre-.filter(Boolean)) results so we can discriminate
    // "every failure looks like a provider throttle" from "some agents crashed for unrelated
    // reasons" before committing to a full ~11.5min backoff schedule (finding #4). Wiring
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

Return the structured object with your full file list. Do not write any output file — return
the data directly in your structured response.`
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

// In-JS clustering — group census files into 8-12-file Phase-1 sub-chunks by directory/prefix,
// mirroring the skill's current manual bucketing (coordinator/commands/architecture-survey.md
// § Phase 0 step 3) but computed deterministically instead of by hand. Zero agent cost.
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

// ---------------------------------------------------------------------------------------------
// Phase "inventory" — deterministic `cartography.symbols` consumer (replaces the Phase-1 Haiku
// per-sub-chunk inventory wave). One op invocation for the whole run: the invoking command's own
// stdout redirect writes the symbol table straight to an artifact file — never through an
// agent() return, which is the transport that truncated a ~515 KB cartography.tree reply to `{}`
// with `ok: true` (see coordinator/bin/survey-consume-gate.py's `_run_cartography_extraction`,
// the former truncation this consumer avoids) and would carry
// 5,815,908 bytes for a 1,931-file TypeScript tree (the plan's own verified measurement: one
// invocation, 10,967 symbols, exit 0, 9.1 s — superseding the ~14.9 MB draft figure, which was a
// linear extrapolation from a body-heavy 25-file sample and overshot by 2.5x). This consumer reads
// the artifact back to cross-check coverage before any downstream phase spends anything.
//
// PM-ratified degrade policy, binding: NO agentic fallback. A file the producer does not claim
// (coordinator_core/ops/cartography_symbols.py's three-way partition: `.py` -> the AST path, a
// claimed extension -> the foreign_symbols adapter, everything else -> an in-band
// `{"unsupported": true}` marker) or a file the adapter could not attempt (`symbol_extract` not
// installed -> an in-band `{"unavailable": true}` marker plus a top-level `coverage_note`) means
// the run STOPS loudly, naming the uncovered files, and writes no atlas. There is no Haiku wave
// left to fall back to.
//
// A file returning an EMPTY symbol list is NOT uncovered — cartography_symbols.py returns a real
// (if empty) entry for a file it successfully parsed but that declares no top-level symbols
// (type-only modules, re-export barrels: 266 of 1,931 files in the verified run). Only
// `unsupported`/`unavailable` — the op's own in-band non-coverage markers — gate the stop below.
//
// Spec backlink: archive/specs/2026-08/2026-08-19-survey-phase1-consumes-cartography-symbols.md
// § chunk C3 (delivered and archived; the measurement above is its § verification table).
// ---------------------------------------------------------------------------------------------

const SYMBOLS_EXTRACTION_SCHEMA = {
  type: 'object',
  required: ['ok', 'exitCode', 'artifactPath'],
  properties: {
    ok: { type: 'boolean' },
    exitCode: { type: 'number' },
    artifactPath: { type: 'string' },
    byteCount: { type: 'number' },
    error: { type: 'string' },
  },
}

function symbolsExtractionBriefFor(files, paramsPath, artifactPath) {
  const paramsJson = JSON.stringify({ target_root: REPO_ROOT, files })
  return COMMON + `

You are a mechanical op-invocation agent (Phase-1 consumer of the /architecture-survey Workflow).
Do NOT judge, summarize, or analyze anything, and do NOT read or paste the op's payload into your
reply — the whole point of this step is that the symbol table travels via disk, never through you.

Step 1: Check whether ${artifactPath} already exists (e.g. \`test -e\` or \`ls\`). RUN_ID makes
this path unique per run, so its pre-existence means something is already wrong — a stale artifact
from a killed prior attempt, or a resumed run about to read it as if it were fresh. Do NOT delete,
overwrite silently, or consume it: stop here, report ok: false with error naming the pre-existing
path, and do NOT proceed to Step 2.

Step 2: Write this exact JSON to ${paramsPath} (create parent directories if they do not exist):
${paramsJson}

Step 3: Run exactly this command. Note it uses PYTHONPATH, not \`cd\` — this makes
\`coordinator_core\` importable without changing your working directory:

  PYTHONPATH="${CLAUDE_KLABAUTER_ROOT}" python3 -m coordinator_core.invoke cartography.symbols --params-file "${paramsPath}" --bare > "${artifactPath}"

Step 4: report the process exit code, and the byte size of ${artifactPath} (e.g. \`wc -c\` or
\`stat\`). Do NOT open, Read, or summarize ${artifactPath}'s content.

Return: ok (true iff exit code is 0), exitCode, artifactPath ("${artifactPath}"), byteCount, and
error (the command's stderr, only when ok is false).`
}

async function invokeSymbolsExtraction(files) {
  if (!CLAUDE_KLABAUTER_ROOT) {
    throw new Error(
      'invokeSymbolsExtraction: INPUT.claude_klabauterRoot is required — the cartography.symbols ' +
      'invocation needs PYTHONPATH set to a claude-klabauter checkout for `coordinator_core` to ' +
      'be importable. Pass the absolute path to a claude-klabauter checkout as INPUT.claude_klabauterRoot.'
    )
  }
  const paramsPath = `${SCRATCH_DIR}/cartography-symbols-params-${RUN_ID}.json`
  const artifactPath = `${SCRATCH_DIR}/cartography-symbols-${RUN_ID}.json`
  const results = await runBatchWithBackoff(
    [() => agent(symbolsExtractionBriefFor(files, paramsPath, artifactPath), {
      schema: SYMBOLS_EXTRACTION_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'inventory',
      label: 'cartography.symbols',
      model: 'haiku',
    })],
    'inventory cartography.symbols'
  )
  const result = results[0]
  if (!result || !result.ok) {
    log(`inventory: cartography.symbols invocation failed or unavailable (${result ? result.error : 'no result'}, exitCode=${result ? result.exitCode : 'n/a'})`)
    return null
  }
  return result
}

// Header-only read-back — mirrors the chunk_table consume-gate's decomposition (never pull the
// whole symbol payload, most of it whole function bodies per this plan's own measurement, back
// through an agent() return). Reports just enough to cross-check completeness and coverage: the
// count of `files[]` entries the artifact actually carries, and every entry this op marked
// `unsupported`/`unavailable` (its own in-band non-coverage signal — see the block comment above).
const SYMBOLS_HEADER_SCHEMA = {
  type: 'object',
  required: ['total_files', 'unavailable_count', 'unsupported_count'],
  properties: {
    total_files: { type: 'number' },
    unavailable_count: { type: 'number' },
    unsupported_count: { type: 'number' },
    unavailable_sample: {
      type: 'array',
      items: {
        type: 'object',
        properties: { path: { type: 'string' }, reason: { type: 'string' } },
      },
    },
    unsupported_extensions: {
      type: 'array',
      items: {
        type: 'object',
        properties: { ext: { type: 'string' }, count: { type: 'number' } },
      },
    },
    coverage_note: { type: 'string' },
  },
}

function symbolsHeaderBriefFor(artifactPath) {
  return COMMON + `

You are a mechanical command-runner (Phase-1 consumer of the /architecture-survey Workflow). Do
NOT judge, summarize, or analyze anything, and do NOT open the artifact yourself — it routinely
exceeds 5 MB, so reading it into your context would truncate the very count you are asked for.

Run exactly this command and capture its stdout. Copy it verbatim, including the quoted heredoc
delimiter (<<'PY') and the closing PY line:

  python3 - <<'PY'
import json, os, collections
d = json.load(open(r"${artifactPath}", encoding="utf-8"))
files = d.get("files") or []
unavailable = [f for f in files if f.get("unavailable") is True]
unsupported = [f for f in files if f.get("unsupported") is True]
ext = collections.Counter(os.path.splitext(f.get("path") or "")[1].lower() for f in unsupported)
out = {
    "total_files": len(files),
    "unavailable_count": len(unavailable),
    "unsupported_count": len(unsupported),
    "unavailable_sample": [
        {"path": f.get("path"), "reason": f.get("detail") or ""} for f in unavailable[:50]
    ],
    "unsupported_extensions": [{"ext": e or "(none)", "count": n} for e, n in ext.most_common()],
}
note = d.get("coverage_note")
if note:
    out["coverage_note"] = note
print(json.dumps(out))
PY

An "uncovered" file is one the op flagged in-band as unclaimable or unattempted. A file that
parsed successfully with an EMPTY symbol list carries neither key and is NOT uncovered — the
command above already encodes that distinction; do not second-guess it.

Parse that stdout as JSON and return its fields unchanged: total_files, unavailable_count,
unsupported_count, unavailable_sample, unsupported_extensions, and coverage_note when the command
emitted one. On any non-zero exit, report the failure and return no counts — do NOT estimate,
infer, or reconstruct them by other means. Do not write any output file.`
}

async function readSymbolsArtifactHeader(artifactPath) {
  const results = await runBatchWithBackoff(
    [() => agent(symbolsHeaderBriefFor(artifactPath), {
      schema: SYMBOLS_HEADER_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'inventory',
      label: 'symbols-header-readback',
      model: 'haiku',
    })],
    'inventory symbols-header-readback'
  )
  return results[0] || null
}

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

// Runs the deterministic `cartography.symbols` consumer in place of the Phase-1 Haiku inventory
// wave. Returns { symbolsArtifactPath, totalFiles } on full coverage, or null with the reason
// already logged — the caller halts the run rather than substituting any agentic fallback
// (PM-ratified, binding: no agentic fallback — see the block comment above).
async function phaseOneSymbolsExtraction(chunkTable) {
  phase('inventory')
  const files = buildSymbolsFileList(chunkTable)
  if (files.length === 0) {
    log('inventory: empty chunk table — no files to extract symbols for, halting')
    return null
  }

  const receipt = await invokeSymbolsExtraction(files)
  if (!receipt) return null

  const header = await readSymbolsArtifactHeader(receipt.artifactPath)
  if (!header) {
    log('inventory: cartography.symbols artifact header readback failed to return — stopping (no agentic fallback)')
    return null
  }

  if (typeof header.total_files !== 'number' || header.total_files !== files.length) {
    log(`inventory: cartography.symbols artifact carries ${header.total_files} file entries, requested ${files.length} — truncation/containment fault, stopping (no agentic fallback)`)
    return null
  }

  // The op reports two distinct coverage failures and they are NOT the same condition. A file the
  // producer COULD claim but did not attempt (`unavailable` — symbol_extract absent, an optional
  // extra) is a fixable install fault: the deterministic path exists and is simply not reachable
  // here, so proceeding would silently narrow a tree that is supposed to be fully covered. A file
  // whose extension NO producer claims (`unsupported`) is not fixable by any action — there is no
  // extra to install and nothing to compute — so halting on it offers the operator no remedy and
  // costs the whole atlas over files that were never inventoriable. Neither branch fires an agent,
  // which is the constraint that actually binds.
  if (header.unavailable_count > 0) {
    const sample = (header.unavailable_sample || []).map((u) => `${u.path} (${u.reason})`).join('; ')
    log(`inventory: cartography.symbols could not attempt ${header.unavailable_count} of ${files.length} requested file(s) whose extensions it DOES claim — the deterministic producer is reachable in principle but unavailable here, so this run stops and writes no atlas rather than narrowing a tree silently (no agentic fallback). Install the missing extractor and re-run. Affected: ${sample}${header.coverage_note ? ` — coverage_note: ${header.coverage_note}` : ''}`)
    return null
  }

  // Disjointness of unavailable/unsupported per file is a verified producer-side invariant, not
  // re-derived here: claude-klabauter's coordinator_core/ops/cartography_symbols.py partitions the
  // request into disjoint py_files/other_files/unsupported_files sets up front and each branch
  // ASSIGNS a fresh dict into entries_by_rel[rel] (~lines 277, 309, 347) rather than merging flags
  // onto an existing entry, so no file can carry both. Combined with the early return above on
  // unavailable_count > 0, this arithmetic only runs when unavailable_count === 0.
  const inventoriedCount = header.total_files - header.unsupported_count
  if (header.unsupported_count > 0) {
    const breakdown = (header.unsupported_extensions || []).map((e) => `${e.ext} x${e.count}`).join(', ')
    log(`inventory: NARROWED PASS — ${header.unsupported_count} of ${files.length} requested file(s) carry extensions no symbol producer claims, so they are outside the deterministic inventory and are excluded from it; ${inventoriedCount} file(s) are inventoried. No model derived symbols for the excluded set and none will. Excluded by extension: ${breakdown}`)
  } else {
    log(`inventory: cartography.symbols covered all ${header.total_files} requested file(s), artifact at ${receipt.artifactPath}`)
  }

  return {
    symbolsArtifactPath: receipt.artifactPath,
    totalFiles: header.total_files,
    inventoriedCount,
    excludedByExtension: header.unsupported_extensions || [],
  }
}

// ---------------------------------------------------------------------------------------------
// Phase "analysis" — Sonnet system analysis, one agent per system, reading ALL its sub-chunk
// inventories. Same LOW-cap sequential-sub-batch treatment as Phase-1 — this is exactly the
// wave that tripped the account-level rate limit in the friction log (21 Sonnet analysts fired
// at once, findings #6-#9).
// ---------------------------------------------------------------------------------------------

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
    }).then((r) => ({ ...r, system_name: system.systemName })),
    'analysis'
  )
}

// ---------------------------------------------------------------------------------------------
// Phase "synthesis" — single Opus leaf agent. Not sub-batched (it's exactly one agent) but it
// DOES benefit from the same backoff wrapper in case the account is still cooling from the
// analysis wave.
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

function synthesisBriefFor(analysisText, systemCount) {
  return COMMON + `

You are the Opus cross-system synthesis agent (Phase-3 of the /architecture-survey Workflow).
You are a LEAF agent — do NOT spawn further agents.

Total systems: ${systemCount}

### Phase-2 System Analysis Reports (all systems)
${analysisText}

**Read each analysis_path above directly (Read tool) — the Workflow script that dispatched you
has no filesystem access and could not paste the content itself; you must read it yourself.**
If the COMBINED size of all analyst pages you Read is large (approaching or exceeding ~80K
tokens / ~300KB), apply the condense-analyst-pages extraction defined in
coordinator/pipelines/deep-architecture-survey/agent-prompts.md § Condense-Analyst-Pages Helper
(Phase-3 Overflow Guard) to EACH page before using its content: drop the \`## Information Flow
Diagram\` H2 section (from its header up to, but not including, the next H2 header), keep
everything else verbatim (System Narrative, Boundary Catalog, Key Architectural Observations,
Summary). This is a pure text-extraction step — do not re-summarize or re-author any analyst's
judgment; synthesis discipline forbids that regardless of context pressure.

Produce the complete architecture atlas per the Phase-3 template in
coordinator/pipelines/deep-architecture-survey/agent-prompts.md: validate cross-system
connections bidirectionally (flag one-sided ones), then write systems-index.md,
cross-system-map.md, connectivity-matrix.md, file-index.md, and one systems/{name}.md per
system, all under docs/architecture/. Follow the YAML-frontmatter conventions in that template
exactly (last_mapped:, mode:, per-system last_attested:/entry_points:/cross_system_connections:/
dependencies:). No grade or status fields — this is discovery, not weekly-architecture-audit.

Every system must appear in systems-index.md and have a per-system file. Every tracked file must
appear in file-index.md. Do NOT write any code or modify any source files — produce markdown
atlas artifacts only. Return the structured object listing every artifact path you wrote.`
}

async function phaseThreeSynthesis(analysisResults) {
  phase('synthesis')
  if (analysisResults.length === 0) {
    log('synthesis: no analysis results to synthesize — halting')
    return null
  }
  const analysisText = analysisResults
    .map((r) => `\n\n---\n### System: ${r.system_name} (${r.analysis_path})\n[content at ${r.analysis_path} — read by the synthesis agent directly]`)
    .join('')

  const results = await runBatchWithBackoff(
    [() => agent(synthesisBriefFor(analysisText, analysisResults.length), {
      schema: SYNTHESIS_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'synthesis',
      label: 'opus-synthesis',
      model: 'opus',
    })],
    'synthesis'
  )
  return results[0] || null
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
    census_results: censusResults,
    failed_census_buckets: failedCensusBuckets,
  }
}

const symbolsExtraction = await phaseOneSymbolsExtraction(chunkTable)

if (!symbolsExtraction) {
  return {
    phase_reached: 'inventory',
    halted: 'symbols-extraction-incomplete',
    run_id: RUN_ID,
    ...consumeGateStatus,
    census_results: censusResults,
    chunk_table: chunkTable,
    resume_hint: 'cartography.symbols failed, returned incomplete, or did not cover every in-scope file — see the logged uncovered-file detail. No agentic fallback exists for this stop; the underlying producer/coverage gap must be resolved before re-running.',
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
    census_results: censusResults,
    chunk_table: chunkTable,
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
    census_results: censusResults,
    chunk_table: chunkTable,
    symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
    symbols_inventoried_count: symbolsExtraction.inventoriedCount,
    symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
    analysis_results: analysisResults,
    failed_analysis_systems: failedAnalysisSystems,
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; only failed analysis agent()s re-run.',
  }
}

const synthesisResult = await phaseThreeSynthesis(analysisResults)

if (!synthesisResult) {
  return {
    phase_reached: 'synthesis',
    halted: 'synthesis-agent-failed',
    run_id: RUN_ID,
    ...consumeGateStatus,
    census_results: censusResults,
    chunk_table: chunkTable,
    symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
    symbols_inventoried_count: symbolsExtraction.inventoriedCount,
    symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
    analysis_results: analysisResults,
    resume_hint: 'Re-invoke this Workflow with resumeFromRunId set to run_id above; only the synthesis agent() re-runs.',
  }
}

return {
  done: true,
  run_id: RUN_ID,
  mode: MODE,
  scale_tier: SCALE_TIER,
  systems_count: analysisResults.length,
  ...consumeGateStatus,
  census_results: censusResults,
  failed_census_buckets: failedCensusBuckets,
  chunk_table_size: chunkTable.length,
  symbols_artifact_path: symbolsExtraction.symbolsArtifactPath,
  symbols_inventoried_count: symbolsExtraction.inventoriedCount,
  symbols_excluded_by_extension: symbolsExtraction.excludedByExtension,
  failed_analysis_systems: failedAnalysisSystems,
  synthesis: synthesisResult,
}
