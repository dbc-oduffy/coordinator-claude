/**
 * distill-harvest.workflow.js — background Workflow for the /distill knowledge-harvest fan-out.
 *
 * Purpose: replace the hand-orchestrated Phase 1/2 Agent dispatch with a resumable, two-wave
 * background Workflow. Wave 1 (Haiku xN scan) is journaled by the Workflow runtime; Wave 2
 * (Sonnet synth) is cheap to re-run. A rate-limit wipeout of Wave 2 costs only the failed
 * synths — Wave 1's structured scan results replay from the journal for free via
 * `resumeFromRunId`. This is the load-bearing property project-rag-em's 188-spec drain proved
 * across two rate-limit wipeouts (cross-repo/inbox/2026-07-12-project-rag-em-distill-workflow-
 * fanout-pattern.md) and the shared primitive this script's twin
 * (`survey-pipeline-rebuild`'s analyst-fanout Workflow) adopts identically — do NOT diverge
 * the shape between them.
 *
 * Spec backlink: docs/plans/2026-07-12-distill-rebuild-claude-klabauter-reliant.md chunk C6.
 * Doctrine: coordinator/docs/wiki/workflow-orchestration.md (vehicle-choice, chunking,
 * commit-discipline, model-selection rules — this script follows all of them).
 *
 * Negative-spec: the two waves are NEVER merged into one resumable unit — merging re-pays the
 * expensive Wave-1 scan on every Wave-2 wipe (see plan Anti-scope: "Do NOT collapse the two
 * waves into one resumable unit"). Wave-2 agents do NOT commit — per
 * workflow-orchestration.md § Commit discipline inside workflows, the EM commits from each
 * agent's returned manifest after the run. Wave-2 agents are additive+provenance-only; the
 * plan's PM-gate-shift (Decisions for PM #1) restricts the PM gate to DELETIONS, so this
 * script writes docs/wiki/<topic>.md directly rather than staging to scratch for a manual
 * apply step — no Phase-5-style apply agent exists downstream of this Workflow.
 */

export const meta = {
  name: 'distill-harvest',
  description: '/distill knowledge harvest: Haiku scan wave (journaled) -> JS cluster -> Sonnet one-file-per-topic synth wave (direct write)',
  phases: [
    { title: 'load', detail: 'optional (args.inputFile only): single Haiku agent() reads the file and returns its parsed content verbatim (schema-forced) — avoids authoring a large batches table inline in args' },
    { title: 'scan', detail: 'parallel Haiku xN: read assigned batch, return structured nuggets (schema-forced, journaled)' },
    { title: 'candidates', detail: 'parallel Haiku xM: one agent per cluster relays C1\'s learn-lessons-reconcile-candidates CLI against the cluster\'s target wiki path, returns candidate_restatements (schema-forced) — an LLM-mediated relay run ahead of synth, not a deterministic assembler call; failure/fabrication degrades silently to an empty list, indistinguishable on disk from "genuinely no candidates" (see Wave 1.5 comment below)' },
    { title: 'synth', detail: 'parallel Sonnet xM: one agent owns one docs/wiki/<topic>.md, additive+provenance direct write, amends/coexists against pre-computed candidate_restatements' },
    { title: 'coverage-gate', detail: 'in-process set-diff of dispositions[] nugget ids vs. assigned nugget ids per cluster; any gap re-dispatches a targeted Sonnet re-synth for the uncovered subset only' },
    { title: 'judgment-mining-2-5', detail: 'parallel Sonnet xM (one per topic-cluster, folded-in Phase 2.5): mines live reviewer sidecars for cross-spec convergence, emits judgment-proposals (schema-forced) for Phase 3b review and wiki promotion into docs/wiki/codebase-judgment/ — read-only orchestrator boundary, no nested sub-agents; runs only once Phase 2 and the Coverage Gate above are fully complete' },
    { title: 'contradiction-detection-3a', detail: 'parallel Sonnet xM (one per cluster, folded-in Phase 3a): reuses Phase 2.5\'s clusterTag grouping of Phase-2 topics to compare synthesized wiki content within each cluster for contradictions (schema-forced), plus an in-process mechanical cross-cluster contradiction check (no subagent dispatch) over every cluster\'s returned contradiction_refs' },
    { title: 'contradiction-escalation', detail: 'conditional (fires only when any cluster reports unresolvable_contradictions > 0 or the cross-cluster check finds a candidate): single Opus agent resolves the flagged contradictions, followed by a single Sonnet fidelity-check agent verifying every flagged source id was cited — never an unconditional stage' },
    { title: 'phase-3b', detail: 'single Sonnet agent (folded-in Phase 3b): decision-record dedup over this run\'s CREATE_DR dispositions and judgment-mining new-entry proposals — reads the real docs/decisions/*.md files Wave 2 already wrote (no Phase 2 scratch files to re-read); skipped entirely (no dispatch) when nothing DR-shaped exists this run, per its own CRITICAL FAILURE MODE contract' },
    { title: 'phase-3d', detail: 'single Sonnet agent (folded-in Phase 3d): resolves this Workflow\'s own mechanically-computed distillation_log_rows (DISTILLED/EPHEMERAL/SKIP) into the final DELETE/SEND_BACK/BLOCKED/PRESERVE deletion manifest — suppressed (no dispatch) when join_integrity verdict is failed, same suppression the mechanical pass is already subject to' },
    { title: 'artifact-reentry', detail: 'findCoverageGaps\' shape lifted from nugget level to artifact level: one re-harvest Sonnet agent per SEND_BACK cluster (grouped by originating batch), re-evaluating the delete guards on return; bounded to SEND_BACK_REENTRY_CAP rounds, a re-harvest failure is caught and logged (never run-blocking), and any artifact still SEND_BACK after the cap becomes BLOCKED with the cap named as the reason — a run never ends with a non-empty SEND_BACK set' },
  ],
}

// ---------------------------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------------------------
// `args` arrives as a JSON string even when the caller passes a JSON array/object
// (state/lessons/2026-07-09-workflow-args-arrives-as-a-json-string — guard unconditionally).
const INPUT = typeof args === 'string' ? JSON.parse(args) : args

// Expected INPUT shape (produced by the /distill skill's Phase 0):
// {
//   runId: 'YYYY-MM-DD-HHhMM',
//   repoRoot: '/absolute/path/to/repo',
//   batches: [ { batchId: 'b1', description: '...', files: ['path1', ...], formatHints: '...' }, ... ],
//   wikiDirs:  ['docs/wiki', 'coordinator/docs/wiki'],   // ordered; [0] is the default/primary NEW-file home.
//                                                        // Whatever wiki trees the repo has (may be just ['docs/wiki']).
//   wikiSlugs: { '<slug>': '<repo-relative-path>', ... }, // flat index: slugified filename-stem -> existing file
//                                                          // path, union across every dir in wikiDirs.
//   resumeFromRunId: '<prior-run-id>' | null,  // caller-supplied; the Workflow tool itself
//                                               // consumes this at invocation time, not in-script
//   inputFile: '/absolute/path/to/input.json' | undefined,  // see § Three input modes below
// }
//
// Three input modes, in precedence order (highest wins):
//   1. args.inputFile (NEW) — args carries `inputFile: '<absolute path>'` alongside the small
//      fields (runId, repoRoot, wikiDirs, wikiSlugs); the (potentially large) `batches` table
//      lives in a JSON file on disk instead of being authored inline into `args`. Workflow
//      scripts have no filesystem access (no `import('node:fs')` — same restriction as the
//      `import('node:os')` note on CONCURRENCY_CAP below), so the first action when this is set
//      is a single Haiku agent() call whose ONLY job is to Read that file and return its parsed
//      content verbatim as structured output (schema-forced — no summarizing, no truncation).
//      Fields present in the file win over the same field in `args`; fields the file omits fall
//      back to `args`. Fails loud (throws) if the file is missing/unreadable/malformed rather
//      than silently falling back to (2)/(3) — a silent fallback here would run a stale or wrong
//      batch table with no signal that it happened.
//   2. args-passed input (existing, unchanged) — the caller passes the full INPUT JSON (object,
//      or JSON-stringified — see the args-arrives-as-a-JSON-string guard immediately below)
//      inline, including `batches`. Fine for small runs; a large batch table burns EM context to
//      author inline, which is exactly what (1) exists to avoid.
//   3. embedded INPUT default (existing, unchanged) — historically, forking this canonical
//      script with a literal `const INPUT = {...}` hardcoded in place of this line (what the
//      2026-07-22-23h55 dogfood run did to route around (2)'s context cost for a 306-file/~25KB
//      batch table). No longer necessary once (1) exists, but this script does not forbid it —
//      a forked copy with a literal INPUT still runs unchanged.
// (2) and (3) keep working exactly as before; (1) is resolved first, per-field, and wins.
const RAW_ARGS_INPUT = INPUT
const INPUT_FILE_SCHEMA = {
  type: 'object',
  required: ['batches'],
  properties: {
    runId: { type: 'string' },
    repoRoot: { type: 'string' },
    batches: {
      type: 'array',
      items: {
        type: 'object',
        required: ['batchId', 'files'],
        properties: {
          batchId: { type: 'string' },
          description: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          formatHints: { type: 'string' },
        },
      },
    },
    wikiDirs: { type: 'array', items: { type: 'string' } },
    wikiSlugs: { type: 'object' },
    contextTerms: { type: 'array', items: { type: 'string' } },
  },
}

let loadedInput = null
if (RAW_ARGS_INPUT && RAW_ARGS_INPUT.inputFile) {
  phase('load')
  const inputFilePath = RAW_ARGS_INPUT.inputFile
  const loadBrief =
    `Repo: ${RAW_ARGS_INPUT.repoRoot || '(unspecified)'}. Do NOT git commit. No out-of-scope edits.\n\n` +
    `You are a Haiku input-file loader (Wave 0 of the /distill harvest Workflow).\n\n` +
    `Read the file at exactly this path: ${inputFilePath}\n\n` +
    `Parse its contents as JSON and return the parsed content VERBATIM as your structured ` +
    `output, matching the required schema exactly — field-for-field, with no summarizing, no ` +
    `truncation, and no paraphrasing of any string value (e.g. file paths, descriptions). If ` +
    `the file does not exist, cannot be read, or is not valid JSON matching the schema, do NOT ` +
    `guess or fabricate a substitute — that is a hard failure condition for this task.`

  const loadResults = (await parallel(
    [() => agent(loadBrief, {
      schema: INPUT_FILE_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'load',
      label: 'input-file',
      model: 'haiku',
    })],
    { concurrency: 1 }
  )).filter(Boolean)
  loadedInput = loadResults[0]

  if (!loadedInput) {
    throw new Error(
      `distill-harvest: args.inputFile="${inputFilePath}" was set but the load agent failed to ` +
      `return a schema-valid payload (file missing, unreadable, or malformed JSON) — fix the ` +
      `file and re-run rather than falling back silently to args-passed/embedded input.`
    )
  }
}

const RUN_ID = (loadedInput && loadedInput.runId) || RAW_ARGS_INPUT.runId
const REPO_ROOT = (loadedInput && loadedInput.repoRoot) || RAW_ARGS_INPUT.repoRoot
const BATCHES = (loadedInput && loadedInput.batches) || RAW_ARGS_INPUT.batches
// D2 (2026-07-19 fix): wikiInventory (topicKey-keyed, guessed at Phase-0 build time before
// topicKeys exist) is superseded by wikiDirs/wikiSlugs (disk-resolved, slug-keyed). Back-compat:
// tolerate a caller still passing the legacy wikiInventory shape — don't crash, just derive an
// empty slug index (no disk-resolved targeting, same behavior as a fresh repo with no wiki yet).
// Review: code-reviewer (Finding 2) — `[]` is truthy, so `INPUT.wikiDirs: []` would leave
// WIKI_DIRS empty (WIKI_DIRS[0] === undefined -> broken "undefined/<slug>.md" paths downstream)
// without this explicit length guard.
const wikiDirsCandidate = (loadedInput && loadedInput.wikiDirs) || RAW_ARGS_INPUT.wikiDirs
const WIKI_DIRS = (wikiDirsCandidate && wikiDirsCandidate.length) ? wikiDirsCandidate : ['docs/wiki']
const WIKI_SLUGS = (loadedInput && loadedInput.wikiSlugs) || RAW_ARGS_INPUT.wikiSlugs || {}
// Fate-prose enforcement's context-term check (§ Distillation-log rows below) is opt-in: absent
// input, the check does not silently pass ("looked at nothing" != "found nothing" — see that
// section for why a silent-pass gate here would be the same defect this file exists to kill).
const CONTEXT_TERMS = (loadedInput && loadedInput.contextTerms) || RAW_ARGS_INPUT.contextTerms || []
// Cross-Repo Archive Specialist Branch (PIPELINE.md § "Cross-Repo Archive Specialist Branch")
// pre-converted dispositions — OPTIONAL, same absent-is-no-op convention as CONTEXT_TERMS above.
// Rows here are already in deletion-manifest row shape (artifact_path, disposition, reason,
// source_nugget_ids) and are merged into the Phase 3d manifest before the artifact re-entry loop
// so re-entry covers them like any other row (§ "Phase 3d" below).
const CROSS_REPO_DISPOSITIONS = (loadedInput && loadedInput.crossRepoDispositions) || RAW_ARGS_INPUT.crossRepoDispositions || []
// Phase 2.5 (judgment mining) inputs — PIPELINE.md:604-612. `judgmentClusters` is OPTIONAL: this
// script has no filesystem access to assemble the live-sidecar corpus itself (same restriction
// documented at CONCURRENCY_CAP below), so a caller that has not wired Phase-0 sidecar-corpus
// collection into this field yet gets the judgment-mining phase reporting 'unavailable' further
// down, never a silent zero-proposals pass. Each entry:
//   { topicCluster: '<claim-topic noun>', verdictDirection: 'forbid'|'require'|'prefer'|'avoid',
//     liveSidecarPaths: ['<plan>.<reviewer>-rN.md', ...], existingJudgmentEntry: '<path>'|null }
// `minConvergence` is the `/distill --min-convergence=N` flag (PIPELINE.md:604-612,
// agent-prompts/phase-2-5-judgment-mining.md § Convergence threshold) — MUST keep working through
// this Workflow; defaults to 3, read null-tolerant (`??`) since 0 would otherwise be masked by `||`.
const JUDGMENT_CLUSTERS = (loadedInput && loadedInput.judgmentClusters) || RAW_ARGS_INPUT.judgmentClusters || []
const MIN_CONVERGENCE = (loadedInput && loadedInput.minConvergence) ?? RAW_ARGS_INPUT.minConvergence ?? 3
// Phase 3a (contradiction detection) inputs — PIPELINE.md:616-658, docs/plans/2026-08-27-distill-
// dispositions-and-tail-rollup.md chunk C6a. `contradictionClusters` REUSES Phase 2.5's shape-match
// clustering apparatus (PIPELINE.md:620 "Reuses Phase 2.5's shape-match clustering apparatus") — the
// grouping of Phase-2 topic keys into 3-5 coarse clusters by claim-topic affinity is a caller-side
// judgment call this script cannot make itself (no semantic clustering in plain JS, same
// restriction that makes JUDGMENT_CLUSTERS caller-supplied above), so the caller passes the SAME
// clusterTag groupings 2.5 already computed rather than this script re-deriving a second, possibly
// inconsistent clustering. Per docs/wiki/distill-harvest-pipeline-defects.md D3, cluster on coarse
// topic domains, never exact topic-string equality — a caller passing one cluster per topicKey
// (i.e. skipping the coarse grouping) reproduces D3's over-fragmentation here, one 3a agent per
// singleton, so this script does not second-guess the grouping it's handed. Each entry:
//   { clusterTag: '<cluster label>', topicKeys: ['<Phase-2 topic key>', ...] }
const CONTRADICTION_CLUSTERS = (loadedInput && loadedInput.contradictionClusters) ||
  RAW_ARGS_INPUT.contradictionClusters || []
// resumeFromRunId intentionally not destructured — see comment above; the Workflow tool
// itself consumes it at invocation time, not in-script.
//
// curatedTags — invocation A/B discriminator (docs/plans/2026-08-06-distill-curation-moves-to-
// claude-klabauter.md, chunk C2/AC2). Read off the already-parsed INPUT (never off `args` directly, and
// never re-parsed here): `args` arrives as a JSON *string* even when the caller passes an object
// (state/lessons/2026-07-09-workflow-args-arrives-as-a-json-string), and the unconditional guard
// at the top of this file (`typeof args === 'string' ? JSON.parse(args) : args`) is the only
// place that string ever gets parsed — a second ad hoc check on `args` here would silently take
// the invocation-A path on a string-arrived invocation-B call, which is exactly the failure mode
// the probe (see plan "## Probe: single-script resume-replay") hit live. `curatedTags` is not
// part of the `inputFile` payload (INPUT_FILE_SCHEMA above has no such field) — it is always a
// caller-supplied top-level arg, same as `resumeFromRunId`.
const CURATED_TAGS = INPUT.curatedTags
// Passthrough-only, result-level fields off claude-klabauter's curated payload (landed commit 67b7061f6,
// cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-threshold-3-measured-and-payload-
// pinned.md) — the threshold claude-klabauter actually APPLIED, whether it was auto-derived, and the
// resulting nugget-drop share. Read null-tolerant (`??`, not `||` — 0/false are real values, e.g.
// threshold_auto: false or nugget_drop_share: 0). Surfaced as received, never recomputed and
// never used to override our own `recommended_keep_threshold` (what WE recommended, a separate
// fact from what the op applied — a mismatch between the two is diagnostic, not an error).
const CURATED_THRESHOLD_APPLIED = INPUT.threshold_applied ?? null
const CURATED_THRESHOLD_AUTO = INPUT.threshold_auto ?? null
const CURATED_NUGGET_DROP_SHARE = INPUT.nugget_drop_share ?? null

// ---------------------------------------------------------------------------------------------
// D3 consolidation config — tunable, named constants (no magic numbers in consolidateClusters).
// ---------------------------------------------------------------------------------------------
// SINGLETON_FLOOR and NEW_FILE_CAP — RETIRED FOR REAL as of docs/plans/2026-08-06-distill-
// curation-moves-to-claude-klabauter.md chunk C4b (AC4 fully discharged; C4 only held them unwired pending
// evidence). The minting policy they encoded now lives in exactly one place — claude-klabauter's
// `distill.curate_clusters` gate — parameterized by `recommended_keep_threshold` below, a fact WE
// own (corpus maturity), per cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-four-
// answers-volume-is-weighted-but-not-a-floor.md items 3-4. See that derivation for the evidence
// and the honest limitation this leaves (2-nugget families still mint).
//
// Below this length a bare leading-word stem is too ambiguous/generic to safely (a) fuzzy-match
// an unrelated existing guide via findFuzzyWikiHome(), or (b) mint its own single-segment NEW
// file (Step 3 below) — 'op'/'test'/'wsc'/'claude-klabauter' are generic/abbreviated single words, not
// real standalone topics, whereas a longer single word like 'percolate' or 'kubernetes' may
// legitimately stand alone. Ports DR-146's existing "shorter stem >= 8 chars" floor
// (PIPELINE.md § Filename-stem overlap check) rather than inventing a new number — same
// rationale, one threshold serving both guards.
const DR146_MIN_STEM_LEN = 8
// Truncation length for the fuzzy stem comparison in findFuzzyWikiHome() — e.g. 'percolate'
// and 'percolation' both truncate to 'percol' and are treated as the same topic.
const STEM_PREFIX_LEN = 6

// Join-integrity gate (§ Source normalization below): the distinct-nugget-source unjoinable
// rate above which Phase 5c's disposition join is unsafe to trust for disposal purposes. Run
// 2026-08-06-14h38 measured 43/245 = 0.176, correctly `failed` at this threshold — that run's
// 43 residue were `2026-07-09-wsc-<uuid>` receipt IDs cited as if they were paths, a real
// anomaly, not basename-shortening noise (basename noise is fully repaired by the exact/
// basename fallback below and never counts toward this rate).
const JOIN_INTEGRITY_MAX_UNJOINABLE_RATE = 0.10

// Concurrency cap: min(16, cores-2) per the shared Workflow-resume primitive (distill-harvest
// lane). This is NOT the survey-analyst-fanout cap (LOW ~4 + ramp) — the two pipelines have
// different burst-arrival-rate risk profiles; do not conflate the two caps.
// NOTE: workflow scripts have NO Node API access — `import('node:os')` throws
// "import() is not available in workflow scripts" and kills the run at init (0 agents).
// The runtime already clamps concurrency to min(16, cores-2) per the parallel() barrier, so
// we pass a nominal ceiling (16) and let the runtime apply the real cores-derived cap.
const CONCURRENCY_CAP = 16

const COMMON = `Repo: ${REPO_ROOT}. Do NOT git commit (EM commits from your returned manifest). ` +
  `No out-of-scope edits. Keep your task under ~10 minutes; if bigger, do the core and report what remains.`

// ---------------------------------------------------------------------------------------------
// Wave 1 — Haiku xN scan, forced structured (schema:) nugget return, journaled by the runtime.
// ---------------------------------------------------------------------------------------------

const NUGGET_SCHEMA = {
  type: 'object',
  required: ['batch_id', 'nuggets_file', 'nuggets', 'file_fates'],
  properties: {
    batch_id: { type: 'string' },
    // AC3 / market-intel signal #1: the RETURNED nuggets_file path is authoritative in the
    // sense that the agent chooses it (may ignore the caller-suggested scratch path and
    // prefer its own session scratchpad) — but it is a debug/audit trail only, NOT consumed
    // downstream. Review: code-reviewer (Finding 1) — clustering reads the schema-validated
    // `nuggets[]` array below directly; it never opens `nuggets_file`. Do not add a read of
    // this path — that would double-source the same data from two places.
    nuggets_file: { type: 'string' },
    files_processed: { type: 'number' },
    nuggets: {
      type: 'array',
      items: {
        type: 'object',
        // content is required + non-empty: a structurally valid nugget with an empty content
        // string is not a real extraction — it is the shape of success with none of the
        // substance, and it silently passed this gate before this fix (2026-08-06,
        // example-market-data-repo-em: 159/642 nuggets, 5 whole batches, empty content, all counted
        // as scan successes). Forcing schema-level minLength turns an empty return into an
        // ordinary retry, the same mechanism that already handles a malformed one.
        // `source` also carries minLength — the join-integrity repair below already treats an
        // empty/absent source as unjoinable, so this only converts a silent unjoinable-source
        // anomaly into an earlier, cheaper retry. `topic`/`system_tag` are deliberately left
        // optional here: they carry real clustering semantics only for KNOWLEDGE/DECISION
        // nuggets (per their own field comments) — EPHEMERAL/ALREADY_CAPTURED/AMBIGUOUS/
        // PRESERVE nuggets legitimately have no topic, and forcing one would make agents invent
        // a meaningless clustering key rather than surface a real defect.
        required: ['id', 'type', 'source', 'content'],
        properties: {
          id: { type: 'string' },           // canonical Phase-1 id, e.g. "b3-007"
          type: {
            type: 'string',
            enum: ['DECISION', 'SUPERSEDED', 'KNOWLEDGE', 'EPHEMERAL', 'ALREADY_CAPTURED', 'AMBIGUOUS', 'PRESERVE'],
          },
          system_tag: { type: 'string' },   // topic/system this nugget clusters under (KNOWLEDGE/DECISION);
                                             // EXACTLY ONE tag — never a comma/semicolon-joined list of
                                             // several (BUG-1, 2026-08-06: a live run returned "guard_design,
                                             // test_design" in one string; ingestion now defends against this
                                             // too, see malformedTagBatchIds below, but the schema description
                                             // is the cheap first line of defence)
          topic: { type: 'string' },
          content: { type: 'string', minLength: 1 },
          // MUST be copied verbatim from this batch's `files[]` — the full repo-relative path,
          // never a bare basename. Phase 5c derives each artifact's distillation-log disposition
          // from "did this source produce nuggets?", joining on this string; a shortened value
          // fails the join and files a harvested artifact as EPHEMERAL ("nothing worth
          // promoting"). That mislabel is self-perpetuating — harvest debt is computed as cohort
          // minus rows logged DISTILLED/PROMOTE, so the artifact is re-scanned and re-mislabelled
          // every subsequent run. Measured 2026-08-06 (run 2026-08-06-14h38): 127 of 245 sources
          // came back as basenames; 72 artifacts (28% of the corpus) would have been permanently
          // mislabelled. `normalizeNuggetSources` below repairs what slips through — this
          // description exists so fewer do.
          source: { type: 'string', minLength: 1 },
          date: { type: 'string' },
          reason: { type: 'string' },       // required semantics for EPHEMERAL/ALREADY_CAPTURED/AMBIGUOUS grouped forms
        },
      },
    },
    anomalies: { type: 'array', items: { type: 'string' } },
    // One entry per file in this batch — including a file that yielded zero nuggets, which
    // still needs a fate line (a mechanically-derived "harvested N nugget(s) on X, Y" reads as
    // index-bait, not domain prose — see § Distillation-log rows below for the enforcement this
    // feeds). Do NOT omit a file just because it produced nothing extractable.
    file_fates: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'fate_prose'],
        properties: {
          // Same pinning language as nugget `source` above: verbatim repo-relative path as
          // given in this batch's `files[]`, never a bare basename — joined the same way.
          path: { type: 'string' },
          fate_prose: { type: 'string' },
        },
      },
    },
  },
}

phase('scan')
// D2: real, disk-resolved slug names (not a topicKey-keyed guess) so Haiku can mark
// ALREADY_CAPTURED against files that genuinely exist, not a Phase-0 guess.
// Review: code-reviewer (Finding 4) — pass slug + path (not bare slugs) so the scan agent has
// a concrete path it could open and read the guide content against, rather than only being
// able to string-match its own tag against an opaque slug label.
const EXISTING_WIKI_SLUG_NAMES = Object.entries(WIKI_SLUGS)
  .map(([slug, p]) => `${slug} (${p})`)
  .sort()
  .join(', ') || 'none'
const scanBriefFor = (batch) => COMMON + `

You are a Haiku artifact scanner (Wave 1 of the /distill harvest Workflow).

Your assigned batch: ${batch.batchId} — ${batch.description}
Files to read: ${JSON.stringify(batch.files)}
Format hints: ${batch.formatHints || 'none'}

Read every file in your batch and extract structured knowledge nuggets. Classify each
piece of extractable knowledge as one of: DECISION, SUPERSEDED, KNOWLEDGE (with a
system_tag naming the topic it clusters under), EPHEMERAL, ALREADY_CAPTURED, AMBIGUOUS,
PRESERVE. \`system_tag\` MUST be exactly ONE tag — never a comma- or semicolon-joined list of
multiple topics (e.g. "guard_design, test_design" is wrong). If a nugget genuinely spans two
topics, pick the single primary one it belongs under; do not invent a combined tag.
Assign canonical nugget IDs as <batch_id>-<seq> (zero-padded, e.g. ${batch.batchId}-001).
Extract, do not synthesize — you are a cataloger, not an analyst. Include exact quotes for
decisions; do not paraphrase reasoning. A nugget must NOT be classified ALREADY_CAPTURED on
the basis of a ~/.claude memory pointer — that is not durable capture; only an in-repo home
(docs/decisions/, docs/wiki/, state/cross-repo-commitments/, or a canonical plan/spec) counts.
Existing wiki guides (slug and path — open the path to check content before deciding):
${EXISTING_WIKI_SLUG_NAMES}. Mark a nugget ALREADY_CAPTURED only
if its knowledge is already in one of these guides.

Every nugget's \`source\` MUST be one of the exact strings in the "Files to read" list above,
copied verbatim — the full repo-relative path, NEVER a bare basename. Downstream bookkeeping
joins on this string; a shortened path silently files a harvested artifact as "nothing worth
promoting" and makes it get re-scanned forever.

Write your full nugget extraction to a scratch file of your choosing (your own session
scratchpad is fine) and return the schema-required fields — in particular return the REAL
path you wrote to as nuggets_file, accurately, not any brief-specified path. This is a
debug/audit trail only: clustering uses your returned structured nuggets[] array, not this
file — the file exists so a human can inspect your full extraction after the fact.

Also return \`file_fates\`: ONE entry per file in "Files to read" above, every file, including
any file that yielded zero nuggets — that file still needs a fate line. Each entry's \`path\`
must be copied verbatim from "Files to read" (same rule as nugget \`source\`: full
repo-relative path, never a bare basename). Each entry's \`fate_prose\` is ONE sentence of
domain prose, at least 8 words, describing what the artifact was actually about and what
became of its content — NOT a process tag like "scaffolding" or a mechanical restatement of
counts ("harvested 2 nuggets on X, Y"). Write it the way you'd describe the artifact to a
colleague who asked what it covered and whether it mattered.`

const scanResults = (await parallel(
  BATCHES.map((batch) => () =>
    agent(scanBriefFor(batch), {
      schema: NUGGET_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'scan',
      label: batch.batchId,
      model: 'haiku',
    })
  ),
  // Review: code-reviewer (Finding 2) — concurrency is a parallel() barrier option only;
  // agent() has no concurrency knob, so the per-agent field was dropped as redundant/dead.
  { concurrency: CONCURRENCY_CAP }
)).filter(Boolean)

if (scanResults.length === 0) {
  return { phase_reached: 'scan', halted: 'all-scan-agents-failed', concurrency_cap: CONCURRENCY_CAP }
}

// ---------------------------------------------------------------------------------------------
// Empty-content defence in depth (2026-08-06, example-market-data-repo-em): the schema above now
// requires non-empty `content`, but a batch that returns an all-empty-content result some other
// way (a lenient schema implementation, a future schema loosening, nuggets[] all trivially
// whitespace) must not silently pass as a scan success — an empty-content nugget carries no
// extracted knowledge, and the disposal gate reasons over "did this source produce nuggets?" as
// evidence of "already harvested". Logged per-batch regardless of outcome (no-silent-caps), and
// any batch whose EVERY nugget is empty is folded into `failedBatchIds` below, which the
// negative-spec disposition logic further down already treats as SKIP, not EPHEMERAL — the same
// "never looked at" semantics that failedBatchIds carries for a batch that never returned at
// all.
const emptyContentBatchIds = []
for (const result of scanResults) {
  const nuggets = result.nuggets || []
  const emptyCount = nuggets.filter((n) => !n.content || n.content.trim() === '').length
  if (emptyCount > 0) {
    log(`${result.batch_id}: ${nuggets.length} nugget(s), ${emptyCount} empty`)
  }
  if (nuggets.length > 0 && emptyCount === nuggets.length) {
    emptyContentBatchIds.push(result.batch_id)
  }
}
if (emptyContentBatchIds.length > 0) {
  log(`empty-content batches counted as scan failures (defence in depth): ${emptyContentBatchIds.join(', ')}`)
}

// ---------------------------------------------------------------------------------------------
// Malformed multi-tag detection (BUG-1, 2026-08-06, state/bug-backlog/2026-08-06-distill-scan-
// wave-haiku-returns-comma-jo-5f766cbc9920.yaml): a live invocation-A run returned a `tag_counts`
// key of `guard_design, test_design` — Wave 1 Haiku put TWO tags in one `system_tag` string. The
// curation gate then faithfully normalized it into `canonical_slug: guard-design,-test-design`,
// a slug that can never match a wiki home and reaches synth as one bogus topic that is really
// two. Detection is deliberately narrow: only a separator character (comma, semicolon, pipe) or
// leading/trailing whitespace marks a tag as malformed — the same class of "the model joined
// multiple things into one string" sloppiness as the observed case. Hyphens, underscores, dots
// and slashes are legitimate WITHIN a single tag (e.g. "guard-design", "ops/incident.response",
// "cross_repo-memo.v1/draft") and must never trip this check — over-reaching here would reject
// real tags, not just malformed ones.
// `\s` in JS regex matches the full unicode whitespace class (space, tab, newline, non-breaking
// space, etc.), not just ASCII — this rule is not narrower than it looks; a future maintainer
// extending it can rely on `\s` catching non-breaking/unicode whitespace variants too.
const MALFORMED_TAG_RE = /[,;|]|^\s|\s$/

// Ingestion decision (BUG-1): drop the offending NUGGET, not the whole batch, unless every one of
// a batch's carry-forward nuggets is malformed. The brief's own precedent framing ("route it
// exactly like empty-content") and its named tension point the same direction once read
// carefully: empty-content's top-level rule ISN'T "any defect fails the batch" — it is "fail the
// batch only when EVERY relevant nugget is bad" (see emptyContentBatchIds above, `nuggets.length
// > 0 && emptyCount === nuggets.length`). A malformed tag is a narrower defect than empty
// content: unlike an empty-content nugget, a malformed-tag nugget still carries a perfectly good
// extraction — only its clustering key is broken — so there is no reason to discard sound
// siblings in the same batch over one Haiku's sloppy tag. Splitting the tag ourselves is
// explicitly out of scope (invents structure the model never committed to), so a malformed-tag
// nugget is simply excluded from clustering input entirely, the same disposition a 'drop'
// verdict gets in clusterNuggets() below — never silently vanished, always counted, so a run can
// tell "no malformed tags" apart from "malformed tags silently swallowed".
const malformedTagBatchIds = []
let malformedTagNuggetCount = 0
for (const result of scanResults) {
  const nuggets = result.nuggets || []
  const carryForward = nuggets.filter((n) => !['EPHEMERAL', 'ALREADY_CAPTURED', 'PRESERVE'].includes(n.type))
  const malformed = carryForward.filter((n) => n.system_tag && MALFORMED_TAG_RE.test(n.system_tag))
  if (malformed.length > 0) {
    malformedTagNuggetCount += malformed.length
    log(`${result.batch_id}: ${malformed.length} nugget(s) with malformed system_tag dropped: ${malformed.map((n) => n.id).join(', ')}`)
    result.nuggets = nuggets.filter((n) => !(n.system_tag && MALFORMED_TAG_RE.test(n.system_tag)))
    if (malformed.length === carryForward.length) {
      malformedTagBatchIds.push(result.batch_id)
    }
  }
}
if (malformedTagBatchIds.length > 0) {
  log(`malformed-tag batches counted as scan failures (defence in depth): ${malformedTagBatchIds.join(', ')}`)
}

const failedBatchIds = BATCHES
  .map((b) => b.batchId)
  .filter((id) => !scanResults.some((r) => r.batch_id === id) || emptyContentBatchIds.includes(id) || malformedTagBatchIds.includes(id))

// ---------------------------------------------------------------------------------------------
// Source normalization — repair basename-shortened nugget sources against the batch file list.
//
// The schema and scan brief both pin `source` to the verbatim repo-relative path, but roughly
// half of Wave 1 shortened it to a basename on run 2026-08-06-14h38 (127 of 245 distinct
// sources). Prompt-level pinning reduces that rate; it cannot guarantee it, and the failure is
// silent — an unjoined source yields zero nuggets for its artifact, which Phase 5c then records
// as EPHEMERAL. So the join is repaired here, deterministically, rather than trusted.
//
// Negative-spec: do NOT "fix" this by having Phase 5c fall back to a basename join on its own.
// The repair belongs at the boundary where the batch file list is still in scope; downstream
// consumers must be able to treat `source` as an exact path. `unjoinable_sources` is surfaced in
// the return value rather than dropped — a source matching no batch file is a real anomaly
// (2026-08-06 saw 43 wsc receipt IDs cited as if they were paths) and silence would hide it.
// ---------------------------------------------------------------------------------------------

function normalizeNuggetSources(results) {
  const byBasename = new Map()
  const exact = new Set()
  let batchFiles = 0
  for (const b of BATCHES) {
    for (const f of b.files) {
      batchFiles++
      exact.add(f)
      const base = f.split('/').pop()
      // A basename colliding across two batch files is unrepairable by this route — record it as
      // ambiguous so the join is never silently made against the wrong artifact.
      byBasename.set(base, byBasename.has(base) ? null : f)
    }
  }

  let repaired = 0
  const distinctSources = new Set()
  const exactJoins = new Set()
  const repairedJoins = new Set()
  const unjoinable = new Set()
  for (const result of results) {
    for (const n of result.nuggets || []) {
      if (!n.source) continue
      distinctSources.add(n.source)
      if (exact.has(n.source)) { exactJoins.add(n.source); continue }
      const originalSource = n.source
      const hit = byBasename.get(n.source.split('/').pop())
      if (hit) { n.source = hit; repaired++; repairedJoins.add(originalSource) } else { unjoinable.add(n.source) }
    }
    // file_fates[].path is pinned identically to nugget `source` and joined the same way —
    // repair it silently here (it is not part of the join-integrity accounting below, which is
    // scoped to nugget sources only, per the disposal-gating contract).
    for (const f of result.file_fates || []) {
      if (!f.path || exact.has(f.path)) continue
      const hit = byBasename.get(f.path.split('/').pop())
      if (hit) f.path = hit
    }
  }
  if (repaired > 0) log(`source normalization: repaired ${repaired} basename-shortened nugget source(s)`)
  if (unjoinable.size > 0) log(`source normalization: ${unjoinable.size} nugget source(s) match no batch file — surfaced, not dropped`)
  return {
    batch_files: batchFiles,
    distinct_nugget_sources: distinctSources.size,
    exact_joins: exactJoins.size,
    repaired_joins: repairedJoins.size,
    unjoinable_sources: [...unjoinable],
  }
}

const sourceNormalization = normalizeNuggetSources(scanResults)

// ---------------------------------------------------------------------------------------------
// Join-integrity verdict — turns the normalization pass above into a gating run result rather
// than a log line nobody reads. `unjoinable_sources` matching no batch file at all (not
// basename-repaired — the repair above already absorbed that noise) is the residue that can
// silently mislabel a harvested artifact as EPHEMERAL downstream (Phase 5c joins on `source`).
// A `failed` verdict suppresses the disposal manifest ONLY — the additive tier (wiki/DR writes)
// already happened above and is never rolled back or hidden; disposal is the destructive leg
// this gate exists to protect, mirroring how a Pre-Phase-4 scan-success gate suppresses
// disposal on total scan failure elsewhere in this pipeline family.
// ---------------------------------------------------------------------------------------------
const unjoinableCount = sourceNormalization.unjoinable_sources.length
const distinctSourceCount = sourceNormalization.distinct_nugget_sources
const unjoinableRate = distinctSourceCount > 0 ? unjoinableCount / distinctSourceCount : 0
const joinVerdict = unjoinableRate === 0
  ? 'clean'
  : unjoinableRate <= JOIN_INTEGRITY_MAX_UNJOINABLE_RATE
    ? 'finding'
    : 'failed'

const joinIntegrity = {
  batch_files: sourceNormalization.batch_files,
  distinct_nugget_sources: distinctSourceCount,
  exact_joins: sourceNormalization.exact_joins,
  repaired_joins: sourceNormalization.repaired_joins,
  unjoinable_sources: sourceNormalization.unjoinable_sources,
  unjoinable_rate: unjoinableRate,
  threshold: JOIN_INTEGRITY_MAX_UNJOINABLE_RATE,
  verdict: joinVerdict,
}

const disposalSuppressed = joinVerdict === 'failed'
const disposalSuppressedReason = disposalSuppressed
  ? `join integrity unjoinable rate ${(unjoinableRate * 100).toFixed(1)}% ` +
    `(${unjoinableCount}/${distinctSourceCount}) exceeds threshold ` +
    `${(JOIN_INTEGRITY_MAX_UNJOINABLE_RATE * 100).toFixed(0)}% — disposal manifest suppressed`
  : null

log(`join integrity: ${joinVerdict} — ${unjoinableCount}/${distinctSourceCount} distinct ` +
  `nugget source(s) unjoinable (rate ${unjoinableRate.toFixed(3)}, threshold ` +
  `${JOIN_INTEGRITY_MAX_UNJOINABLE_RATE})` +
  (disposalSuppressed ? ` — DISPOSAL SUPPRESSED: ${disposalSuppressedReason}` : ''))

// ---------------------------------------------------------------------------------------------
// Curation early return (Invocation A) — docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md
// chunk C2/AC2. Absent `curatedTags` (see CURATED_TAGS above — read off parsed INPUT, never off
// `args` directly), this run IS invocation A: stop here and hand the caller a tag census plus the
// two gate inputs it needs to run claude-klabauter's `distill.curate_clusters` op out-of-band. The caller
// re-invokes this SAME script as invocation B with `curatedTags` set — the scan wave and source
// normalization above then replay from the Workflow runtime's cache instead of re-dispatching
// (probe-confirmed, see plan "## Probe: single-script resume-replay"), and join_integrity is
// recomputed (not transcribed) from the replayed scanResults by the unconditional code above, on
// every invocation alike.
//
// NEGATIVE-SPEC — `resumeFromRunId` is NOT `run_id`. Two different identifiers, and passing the
// wrong one fails silently by re-dispatching the entire (expensive) scan wave instead of
// replaying it:
//   * `run_id` below is this pipeline's own distillation slug (`YYYY-MM-DD-HHhMM`), supplied by
//     the caller in INPUT and used for scratch paths and journal correlation.
//   * `resumeFromRunId` is the Workflow *tool's* harness-assigned run id (`wf_...`), which exists
//     only in invocation A's Workflow tool RESULT — this script cannot see or return it.
// So invocation B passes `resumeFromRunId: <the wf_... id from invocation A's tool result>` and
// `runId: <the same distillation slug>`. See `resume_hint` in the returned object.
//
// `failed_batch_ids` is the RAW INPUT to the scan-success gate, never the verdict — that gate is
// an EM/Phase-0 computation over this run's per-batch journal (coordinator/commands/distill.md:
// 284,290), not computed in this script. `join_integrity` IS inline-computed above; that
// asymmetry with failed_batch_ids is deliberate, per the same doc.
//
// `recommended_keep_threshold` (chunk C4b) is returned alongside `tag_counts` — curation's
// minting policy now lives entirely on claude-klabauter's side of the seam, as the `keep_threshold` value
// WE pass into their gate call, not as a constant kept on our side (see the derivation comment
// immediately below this one).
//
// `tag_counts` reuses clusterNuggets()'s own topicKey derivation below (a plain read of its
// grouping, hoisted function declaration — not the rekeying-onto-the-curated-map work, which is
// chunk C3 and runs only in invocation B, after curation resolves the map): "the counts first
// exist at clusterNuggets()" per the plan's Problem section, matching the measured
// 549-tags-over-1200-nuggets figure at that same call site.
//
// `recommended_keep_threshold` (chunk C4b) — claude-klabauter's `distill.curate_clusters` gate compares
// `keep_threshold` against a cluster's FAMILY total (summed across every tag folded into it), so
// the threshold is the one knob that decides cold-start survival vs. steady-state floor
// semantics; their memo (see the file header cite above) is explicit that shipping their bare
// default (2) unconditionally is wrong for a young corpus. Derivation uses ONLY their two
// measured points (mean-of-20-seeds drop rate over a 433-nugget/249-tag census):
//   thr=2: 20n->71.2%, 60n->44.4%, 150n->27.4%, 433n(full)->17.1%
//   thr=1: 20n->12.0%, 60n->8.7%,  150n->8.8%,  433n(full)->8.1% (flat 8-12% across a 20x range)
// Cold-start -> 1: fires when WIKI_SLUGS is empty (virgin wiki tree) OR the carry-forward nugget
// count is below 150 — at 150 nuggets thr=2 still discards 27.4% of the corpus, which is not a
// tail, it is the harvest. Mature -> 2 (their measured 17.1%-drop default) otherwise.
// Deliberately NOT 3: pure floor semantics ("a 1-2-nugget cluster doesn't earn its own file")
// would want it, but nobody has measured its drop rate on any corpus — shipping an unmeasured
// number because it matches a retired constant's intent is exactly the assumption-shipping this
// plan has already refused twice. What would settle it: a drop-rate measurement at threshold 3.
//
// Honest limitation (measured-boundary gap, not an oversight): at threshold 2, only 1-nugget
// families are suppressed — a 2-nugget family still mints its own file. The retired
// SINGLETON_FLOOR's stated job ("a 1-2-nugget cluster doesn't earn its own new file") is thus
// only PARTLY discharged by this derivation, and stays that way until a threshold-3 measurement
// lands.
// ---------------------------------------------------------------------------------------------
if (!CURATED_TAGS) {
  const tagCensusClusters = clusterNuggets(scanResults)
  const tagCounts = {}
  let carryForwardNuggetCount = 0
  for (const cluster of tagCensusClusters) {
    tagCounts[cluster.topicKey] = cluster.nuggets.length
    carryForwardNuggetCount += cluster.nuggets.length
  }
  const wikiSlugCount = Object.keys(WIKI_SLUGS).length
  const isColdStart = wikiSlugCount === 0 || carryForwardNuggetCount < 150
  const recommendedKeepThreshold = isColdStart ? 1 : 2
  const recommendedKeepThresholdReason = isColdStart
    ? `cold-start (nugget_count=${carryForwardNuggetCount}, wiki_slug_count=${wikiSlugCount}) — ` +
      'threshold=2 measured at 27.4% drop even at the 150-nugget boundary; threshold=1 holds flat 8-12%'
    : `mature (nugget_count=${carryForwardNuggetCount}, wiki_slug_count=${wikiSlugCount}) — ` +
      "claude-klabauter's default threshold=2 measured at 17.1% drop on the full 433-nugget census"

  return {
    phase_reached: 'join-integrity',
    run_id: RUN_ID,
    tag_counts: tagCounts,
    recommended_keep_threshold: recommendedKeepThreshold,
    recommended_keep_threshold_reason: recommendedKeepThresholdReason,
    join_integrity: joinIntegrity,
    failed_batch_ids: failedBatchIds,
    resume_hint:
      `Run claude-klabauter distill.curate_clusters over tag_counts with keep_threshold=${recommendedKeepThreshold} ` +
      `(${recommendedKeepThresholdReason}), then re-invoke this SAME script with ` +
      'curatedTags set, runId set to run_id above, and resumeFromRunId set to the wf_... runId ' +
      "from THIS invocation's Workflow tool result — NOT to run_id, which is a distillation slug " +
      'and will silently re-dispatch the whole scan wave.',
  }
}

// ---------------------------------------------------------------------------------------------
// In-JS clustering — free join, zero agent cost. Nugget -> topic, keyed by system_tag/topic.
// ---------------------------------------------------------------------------------------------

// clusterNuggets — TWO modes, the distinction is load-bearing (docs/plans/2026-08-06-distill-
// curation-moves-to-claude-klabauter.md, chunk C3/AC3):
//
// CENSUS mode (curatedMap absent — invocation A only, called from the early-return above with a
// single argument). Behaviour is UNCHANGED from before C3, including the `|| 'uncategorized'`
// fallback: this path exists solely to build the `{tag: count}` census that claude-klabauter's
// `distill.curate_clusters` op is about to verdict on. A nugget with no `system_tag` is a real
// member of our corpus; dropping it from the census would only make it fail loud in invocation B,
// so it is counted under `uncategorized` and claude-klabauter gets to rule on that tag like any other.
//
// CURATED mode (curatedMap present — invocation B, after homing-override resolution). The
// `|| 'uncategorized'` fallback is GONE. Each nugget's raw tag is resolved through curatedMap.
// Contract confirmed against a direct read of claude-klabauter's `distill_curate_clusters.py` (see
// cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-four-answers-volume-is-weighted-but-not-a-floor.md) —
// a verdict entry carries TWO distinct fields, both present:
//   - `canonical_slug`  -> that tag's OWN normalized slug (not a destination)
//   - `merge_target`    -> the destination slug the tag folds INTO; populated ONLY on
//                          verdict 'merge', null on keep/normalize/drop by contract
//   - verdict `keep`      -> `canonical_slug` (fail loud if absent — same AC7 no-silent-
//                            degradation contract as normalize/merge below; a `keep` payload
//                            missing its canonical_slug is a seam break, not a case to paper
//                            over by falling back to the raw tag)
//   - verdict `normalize` -> `canonical_slug` (fail loud if absent — a normalize verdict with
//                            nothing to normalize to is a broken payload; do NOT fall back to
//                            `merge_target`, which is null by contract on this verdict)
//   - verdict `merge`     -> `merge_target` (fail loud if absent/null — refusing to guess a
//                            merge target)
//   - verdict `drop`      -> excluded from synth, pushed onto `drops` (caller-supplied
//                            accumulator) with tag/nugget id/reason, never silently vanished
//   - tag absent from curatedMap entirely -> FAIL LOUD, stop the run. The map and the corpus
//     disagree; that is a bug in the seam, not a case to invent a bucket for (AC7's
//     no-silent-degradation requirement at its most concrete point).
//
// Two contract facts recorded here, NOT coded against (same memo):
//   1. The drop set is a filter over the verdict list, not a separate key — one verdict entry
//      per raw input tag, always. There is no top-level `dropped: [...]` key.
//   2. `drop_cause` (a three-value enum: 'placeholder'/'bare-no-sibling'/'below-threshold', null
//      on non-drops) and a `drop_by_cause` count block have LANDED on claude-klabauter's side, commit
//      67b7061f6 (cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-threshold-3-
//      measured-and-payload-pinned.md) — drop logging below keys on the enum where present,
//      null-tolerant throughout for a payload from before the landing.
//
// `drops`, when supplied, is mutated in place (push) rather than returned, so this function's
// return type stays a plain cluster array in both modes — the census-mode call site above keeps
// working untouched, and the D3/consolidateClusters extraction harness downstream is unaffected.
function clusterNuggets(results, curatedMap, drops) {
  const topics = new Map() // topicKey -> { nuggets: [...], sources: Set }

  for (const result of results) {
    for (const nugget of result.nuggets || []) {
      // Only KNOWLEDGE/DECISION/SUPERSEDED/AMBIGUOUS nuggets carry forward to synth; EPHEMERAL/
      // ALREADY_CAPTURED/PRESERVE are terminal at Wave 1 (mirrors PIPELINE.md Phase 1 rules —
      // this script performs the same downstream-carry decision mechanically, in JS).
      if (['EPHEMERAL', 'ALREADY_CAPTURED', 'PRESERVE'].includes(nugget.type)) continue

      const rawTag = nugget.system_tag || nugget.topic || 'uncategorized'
      let topicKey

      if (!curatedMap) {
        topicKey = rawTag
      } else {
        const entry = curatedMap[rawTag]
        if (!entry) {
          throw new Error(
            `clusterNuggets: tag '${rawTag}' is absent from the curated map — the map and the ` +
            'corpus disagree (bug in the curation seam), refusing to invent a bucket'
          )
        }
        if (entry.verdict === 'keep') {
          if (!entry.canonical_slug) {
            throw new Error(
              `clusterNuggets: tag '${rawTag}' has verdict 'keep' but no canonical_slug key — ` +
              'refusing to silently fall back to the raw tag'
            )
          }
          topicKey = entry.canonical_slug
        } else if (entry.verdict === 'normalize') {
          if (!entry.canonical_slug) {
            throw new Error(
              `clusterNuggets: tag '${rawTag}' has verdict 'normalize' but no canonical_slug key — ` +
              'refusing to guess a normalized slug'
            )
          }
          topicKey = entry.canonical_slug
        } else if (entry.verdict === 'merge') {
          if (!entry.merge_target) {
            throw new Error(
              `clusterNuggets: tag '${rawTag}' has verdict 'merge' but no merge_target key — ` +
              'refusing to guess a merge target'
            )
          }
          topicKey = entry.merge_target
        } else if (entry.verdict === 'drop') {
          if (drops) {
            // drop_cause (landed claude-klabauter commit 67b7061f6, see the comment block above) is read
            // null-tolerant — an older payload without the field must not throw, and its absence
            // (undefined) is normalized to null the same as claude-klabauter's own `None` on non-drops.
            drops.push({
              tag: rawTag,
              nugget_id: nugget.id,
              reason: entry.reason || null,
              drop_cause: entry.drop_cause != null ? entry.drop_cause : null,
            })
          }
          continue
        } else {
          throw new Error(`clusterNuggets: tag '${rawTag}' has unrecognized verdict '${entry.verdict}'`)
        }
      }

      if (!topics.has(topicKey)) {
        topics.set(topicKey, { topicKey, nuggets: [], sourceBatches: new Set() })
      }
      const cluster = topics.get(topicKey)
      cluster.nuggets.push(nugget)
      cluster.sourceBatches.add(result.batch_id)
    }
  }

  return [...topics.values()].map((c) => ({
    topicKey: c.topicKey,
    nuggets: c.nuggets,
    sourceBatches: [...c.sourceBatches],
  }))
}

// ---------------------------------------------------------------------------------------------
// D3 consolidation pass — pure, deterministic, free (no agent cost). Runs between
// clusterNuggets() and Wave-2. Fragmentation defense: clusterNuggets() keys on Haiku's exact
// free-form system_tag/topic string, which at scale (~400 artifacts) produces hundreds of
// near-duplicate singleton clusters -> one NEW wiki file per cluster (shrapnel). Consolidation
// pressure applies ONLY where the shrapnel is (clusters with no existing wiki home) — clusters
// that map to an existing guide flow through unchanged (an additive merge into a real guide is
// not shrapnel, however small).
//
// MUST be a pure function with zero dependency on workflow-runtime globals (no agent/parallel/
// phase/log, no top-level await) so the D3 regression test can extract and exercise it in
// isolation. Takes everything via params, returns a plain array of cluster objects.
//
// NO NUGGET MAY BE DROPPED: total input nugget count across rawClusters must equal total output
// nugget count across the returned array — this is the correctness invariant, enforced by a hard
// assert (not a soft log) because a silent drop here is data loss that would only surface as a
// missing knowledge nugget weeks later.
// ---------------------------------------------------------------------------------------------

// ---------------------------------------------------------------------------------------------
// DR-146 stem-normalization (PIPELINE.md § Filename-stem overlap check) — ported/reused, not
// reinvented — giving Step 1/Step 2 below a fuzzy fallback when exact wikiSlugs lookup misses a
// genuine existing home (e.g. cluster slug 'percolate' vs existing 'percolation-engine.md' —
// same topic, divergent surface form). Exact-slug match is always tried first; this only fires
// on a miss, and only returns a home when both sides clear DR146_MIN_STEM_LEN — it never invents
// a match on short/generic words.
// ---------------------------------------------------------------------------------------------

const DR146_STRIP_SUFFIXES = ['-shape', '-design', '-v2']
const DR146_DATE_PREFIX_RE = /^\d{4}-\d{2}-\d{2}-/

function dr146Normalize(slug) {
  let s = slug.toLowerCase().replace(DR146_DATE_PREFIX_RE, '')
  for (const suffix of DR146_STRIP_SUFFIXES) {
    if (s.endsWith(suffix)) {
      s = s.slice(0, -suffix.length)
      break
    }
  }
  if (s.endsWith('s') && !s.endsWith('ss')) s = s.slice(0, -1) // de-pluralize
  return s
}

// Leading-word + truncated-stem pair for a slug, per DR146_STRIP_SUFFIXES/STEM_PREFIX_LEN above.
function leadingStem(slug) {
  const word = dr146Normalize(slug).split('-')[0]
  return { word, stem: word.slice(0, STEM_PREFIX_LEN) }
}

// Fuzzy fallback for Step 1/Step 2's exact `wikiSlugs[slug]` lookup below: matches when the
// candidate slug's and an existing wikiSlugs key's leading word both clear DR146_MIN_STEM_LEN
// and truncate to the same STEM_PREFIX_LEN stem. Returns the existing path, or null when no
// confident match exists (caller keeps treating the cluster as homeless).
function findFuzzyWikiHome(slug, wikiSlugsIndex) {
  const candidate = leadingStem(slug)
  if (candidate.word.length < DR146_MIN_STEM_LEN) return null
  for (const [existingSlug, path] of Object.entries(wikiSlugsIndex)) {
    const existing = leadingStem(existingSlug)
    if (existing.word.length < DR146_MIN_STEM_LEN) continue
    if (existing.stem === candidate.stem) return path
  }
  return null
}

// ---------------------------------------------------------------------------------------------
// Homing override (AC12, docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md chunk C3) —
// HOMING, not a second curation policy. Claude-klabauter's `distill.curate_clusters` verdict is home-blind:
// it sees only `{system_tag: count}`, never our wiki tree. The retired consolidateClusters()
// Step 1 was home-CONDITIONAL by design ("clusters that map to an existing guide flow through
// unchanged"), so without this override a 1-nugget tag that already has a wiki file could be
// dropped or merged away by a verdict that never knew the home existed — and C3's fail-loud does
// NOT catch that, because a dropped tag is still present in the curated map.
//
// Runs BEFORE clustering, after curation resolves the map, over every tag key in curatedMap: any
// tag whose slug exact-matches a WIKI_SLUGS key, or that clears findFuzzyWikiHome(slug,
// wikiSlugsIndex), is restored to `keep` under its OWN key, regardless of claude-klabauter's verdict.
// claude-klabauter owns whether a tag is a real TOPIC; this repo owns whether that tag already has a HOME
// on disk, and an existing home outranks a shape verdict. Deliberately does NOT feed our wiki
// slugs into claude-klabauter's op as a keep-protected hint instead — a memo has already told them their
// contract does not depend on our disk.
//
// C3e: the override touches the VERDICT ONLY — every other field the curation op returned
// (`canonical_slug` above all) is preserved, not discarded. Discarding canonical_slug used to
// re-fragment exactly what curation normalized: two shape variants of one canonical slug
// (`git_safety` / `git.safety`, both normalizing to `git-safety`) would both match the same wiki
// home, both get overridden, and then each key clusterNuggets under its OWN raw tag instead of
// the shared canonical_slug — two clusters, two synth agents, two writes aimed at one wiki file.
// `merge_target` is nulled out deliberately: claude-klabauter's contract holds `merge_target` non-null
// exactly on verdict `merge`; an entry overridden from `merge` to `keep` that kept a stale
// `merge_target` would violate that invariant for every downstream reader.
//
// Returns a NEW map (curatedMap is not mutated) plus the override count for the run's return
// value.
function applyHomingOverride(curatedMap, wikiSlugsIndex) {
  const resolved = {}
  let overrideCount = 0

  for (const [tag, entry] of Object.entries(curatedMap)) {
    // Slugify before matching — WIKI_SLUGS is keyed by slugified filename-stem, and a raw tag
    // carries spaces/case/punctuation that would never match one. This mirrors the lookup
    // consolidateClusters() Step 1 has always done (`slugifyTopic(topicKey)` then exact-or-fuzzy);
    // matching the raw tag instead would silently miss the home on exactly the tags AC12 exists
    // to protect, and the miss is invisible — the tag just keeps claude-klabauter's drop/merge verdict.
    //
    // MUST slugify the same value clusterNuggets() will actually key the cluster's topicKey
    // under, not the raw tag alone: clusterNuggets()'s 'keep' branch keys topicKey on
    // `entry.canonical_slug` and FAIL-LOUDS when it is absent, and
    // consolidateClusters() Step 1 re-derives the home from THAT topicKey, not from the raw tag.
    // If this override matched on `slugifyTopic(tag)` alone, an entry whose canonical_slug
    // diverges from the raw tag's own slug (plausible — claude-klabauter's canonicalization and this
    // repo's crude slugifyTopic are two independent implementations) would match a home here
    // that Step 1 then fails to re-find, silently landing the cluster in `homeless` instead of
    // the existing wiki file this override exists to protect. Matching on the same resolved
    // value keeps the two lookups in agreement by construction — do not re-split them.
    const slug = slugifyTopic(entry.canonical_slug || tag)
    const hasExactHome = Object.prototype.hasOwnProperty.call(wikiSlugsIndex, slug)
    const hasFuzzyHome = !hasExactHome && findFuzzyWikiHome(slug, wikiSlugsIndex) !== null

    // Promotion MUST carry a canonical_slug. Claude-klabauter's `distill.curate_clusters` emits
    // `canonical_slug: null` on every `drop` by contract (coordinator_core/ops/
    // distill_curate_clusters.py Pass 5), and `drop` is the dominant override input — spreading
    // the entry unchanged manufactures a `keep` with no slug, which clusterNuggets() then
    // fail-louds on, halting the whole run on any dropped tag that has a wiki home. Derive it
    // from the same resolved value the home lookup matched on, so consolidateClusters() Step 1
    // re-finds that home from the topicKey.
    if ((hasExactHome || hasFuzzyHome) && entry.verdict !== 'keep') {
      resolved[tag] = { ...entry, verdict: 'keep', canonical_slug: entry.canonical_slug || slug, merge_target: null }
      overrideCount += 1
    } else {
      resolved[tag] = entry
    }
  }

  return { resolvedMap: resolved, overrideCount }
}

function consolidateClusters(rawClusters, wikiSlugs, config) {
  // consolidateClusters is extracted by TEXT into an isolated `new Function(...)` eval scope by
  // the D3 regression test (no closure over this file's module-level consts survives that
  // extraction) — every value this function needs arrives via `config`, never a bare module-level
  // reference. SINGLETON_FLOOR/NEW_FILE_CAP are DELETED (chunk C4b — see the retirement comment
  // near DR146_MIN_STEM_LEN's declaration) and are not part of this config shape.
  const { runId, wikiDirs } = config
  const totalInputNuggets = rawClusters.reduce((n, c) => n + c.nuggets.length, 0)

  // Step 1 — partition by disk reality: `homed` (slug matches an existing wiki file, passes
  // through unchanged — an additive merge, not shrapnel) vs `homeless` (no existing home,
  // candidate for coarsen/fold/cap below).
  const homed = []
  const homeless = []
  for (const cluster of rawClusters) {
    const slug = slugifyTopic(cluster.topicKey)
    const existingPath = wikiSlugs[slug] || findFuzzyWikiHome(slug, wikiSlugs)
    if (existingPath) {
      homed.push({ ...cluster, wikiPath: existingPath, bucket: 'homed' })
    } else {
      homeless.push(cluster)
    }
  }

  // Steps 2-5 (coarsen/fold/cap/misc-bucket-emission) are RETIRED as of
  // docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md chunk C4 — they triaged the
  // homeless bucket after the fact, deciding per-cluster whether shrapnel earned its own file.
  // That question is now answered UPSTREAM of clustering: claude-klabauter's `distill.curate_clusters`
  // verdict decides per-tag, before a nugget is ever grouped, whether the tag survives at all
  // (C2/C3). Every cluster that reaches this point already cleared that bar, so every homeless
  // cluster earns its own file, unconditionally — "either shit deserves a home or it doesn't"
  // is no longer a question this function answers.
  const newClusters = homeless.map((c) => ({
    ...c,
    wikiPath: `${wikiDirs[0]}/${slugifyTopic(c.topicKey)}.md`,
    bucket: 'new',
  }))
  const result = [...homed, ...newClusters]

  const totalOutputNuggets = result.reduce((n, c) => n + c.nuggets.length, 0)
  if (totalOutputNuggets !== totalInputNuggets) {
    throw new Error(
      `consolidateClusters: nugget count not conserved (in=${totalInputNuggets}, out=${totalOutputNuggets})`
    )
  }

  return result
}

// Curated-map resolution (C3/AC3) + homing override (C3/AC12) — only reached in invocation B
// (invocation A already returned above), where CURATED_TAGS is guaranteed set.
const { resolvedMap: HOMED_CURATED_TAGS, overrideCount: homingOverrideCount } =
  applyHomingOverride(CURATED_TAGS, WIKI_SLUGS)
const droppedTags = []
const rawClusters = clusterNuggets(scanResults, HOMED_CURATED_TAGS, droppedTags)

// C3b (docs/plans/2026-08-06-distill-curation-moves-to-claude-klabauter.md) — visibility layer over C3's
// `droppedTags` recording. C3 records the drop; this renders it, so "a bucket nobody reads" isn't
// traded for "a drop nobody sees" (claude-klabauter's own framing, PM-ratified 2026-08-06).
//
// Visibility tripwire, not a policy gate — this script never halts on it. 25% is a first guess:
// claude-klabauter owes us a cold-start census measurement to replace it with an evidence-backed number.
const DROP_SHARE_WARNING_THRESHOLD = 0.25

const curationVerdictCounts = Object.values(HOMED_CURATED_TAGS).reduce((acc, entry) => {
  const key = entry.verdict === 'normalize'
    ? 'normalized'
    : entry.verdict === 'merge'
      ? 'merged'
      : entry.verdict === 'drop'
        ? 'dropped'
        : 'kept'
  acc[key] = (acc[key] || 0) + 1
  return acc
}, { kept: 0, normalized: 0, merged: 0, dropped: 0 })

// Pre-curation corpus = every carry-forward nugget clusterNuggets() saw, whether it survived into
// a cluster or was dropped — the denominator for "share of the corpus discarded".
const preCurationNuggetCount =
  rawClusters.reduce((n, c) => n + c.nuggets.length, 0) + droppedTags.length
const droppedNuggetShare = preCurationNuggetCount > 0
  ? droppedTags.length / preCurationNuggetCount
  : 0

const dropsByReason = {}
for (const drop of droppedTags) {
  const reasonKey = drop.reason || '(no reason given)'
  if (!dropsByReason[reasonKey]) {
    dropsByReason[reasonKey] = { tag_count: 0, nugget_count: 0, tags: new Set() }
  }
  const bucket = dropsByReason[reasonKey]
  bucket.nugget_count += 1
  if (!bucket.tags.has(drop.tag)) {
    bucket.tag_count += 1
    bucket.tags.add(drop.tag)
  }
}
const dropsByReasonSummary = Object.fromEntries(
  Object.entries(dropsByReason).map(([reason, bucket]) => [
    reason,
    { tag_count: bucket.tag_count, nugget_count: bucket.nugget_count, tags: [...bucket.tags] },
  ])
)

// Machine-readable grouping alongside the prose-keyed one above — stable across wording changes
// to claude-klabauter's `reason` prose (per cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-
// threshold-3-measured-and-payload-pinned.md). `drop_cause` is null-tolerant per-drop (see
// clusterNuggets above); a drop lacking it groups under '(no drop_cause)' rather than being lost.
const dropsByCause = {}
for (const drop of droppedTags) {
  const causeKey = drop.drop_cause != null ? drop.drop_cause : '(no drop_cause)'
  if (!dropsByCause[causeKey]) {
    dropsByCause[causeKey] = { tag_count: 0, nugget_count: 0, tags: new Set() }
  }
  const bucket = dropsByCause[causeKey]
  bucket.nugget_count += 1
  if (!bucket.tags.has(drop.tag)) {
    bucket.tag_count += 1
    bucket.tags.add(drop.tag)
  }
}
const dropsByCauseSummary = Object.fromEntries(
  Object.entries(dropsByCause).map(([cause, bucket]) => [
    cause,
    { tag_count: bucket.tag_count, nugget_count: bucket.nugget_count, tags: [...bucket.tags] },
  ])
)
const anyDropCausePresent = droppedTags.some((d) => d.drop_cause != null)

const droppedNuggetCountByTag = {}
const droppedReasonByTag = {}
for (const drop of droppedTags) {
  droppedNuggetCountByTag[drop.tag] = (droppedNuggetCountByTag[drop.tag] || 0) + 1
  droppedReasonByTag[drop.tag] = drop.reason || null
}
const topDroppedTags = Object.entries(droppedNuggetCountByTag)
  .sort(([, aCount], [, bCount]) => bCount - aCount)
  .slice(0, 10)
  .map(([tag, nuggetCount]) => ({ tag, nugget_count: nuggetCount, reason: droppedReasonByTag[tag] }))

const dropSummary = {
  verdict_counts: curationVerdictCounts,
  homing_override_count: homingOverrideCount,
  dropped_nugget_count: droppedTags.length,
  pre_curation_nugget_count: preCurationNuggetCount,
  dropped_nugget_share: droppedNuggetShare,
  by_reason: dropsByReasonSummary,
  by_cause: dropsByCauseSummary,
}

// Cause-keyed summary line when drop_cause is present on any drop (machine-readable, stable
// across prose wording changes); falls back to today's prose-only behaviour when it is absent
// entirely (older payload, pre-67b7061f6).
const dropCauseLogFragment = anyDropCausePresent
  ? ' — by cause: ' + Object.entries(dropsByCauseSummary)
      .map(([cause, bucket]) => `${cause}: ${bucket.nugget_count}`)
      .join(', ')
  : ''

log(`curation: ${curationVerdictCounts.kept} kept, ${curationVerdictCounts.normalized} normalized, ` +
  `${curationVerdictCounts.merged} merged, ${curationVerdictCounts.dropped} dropped ` +
  `(${homingOverrideCount} homing override(s)) — dropped ${droppedTags.length}/${preCurationNuggetCount} ` +
  `nugget(s) (${(droppedNuggetShare * 100).toFixed(1)}% of pre-curation corpus)${dropCauseLogFragment}`)

if (topDroppedTags.length > 0) {
  log(`curation: top dropped tag(s) by nugget volume — ` +
    topDroppedTags.map((t) => `${t.tag} (${t.nugget_count}, reason: ${t.reason || '(none)'})`).join('; '))
}

if (droppedNuggetShare > DROP_SHARE_WARNING_THRESHOLD) {
  log(`WARNING: curation dropped ${(droppedNuggetShare * 100).toFixed(1)}% of the pre-curation ` +
    `nugget corpus (threshold ${(DROP_SHARE_WARNING_THRESHOLD * 100).toFixed(0)}%) — see drop_summary`)
}

const clusters = consolidateClusters(rawClusters, WIKI_SLUGS, {
  runId: RUN_ID,
  wikiDirs: WIKI_DIRS,
})
const homedCount = clusters.filter((c) => c.bucket === 'homed').length
const newCount = clusters.filter((c) => c.bucket === 'new').length
log(`consolidation: ${rawClusters.length} raw -> ${homedCount} homed + ${newCount} new ` +
  `(no-misc: curation already decided upstream which tags survive, per plan chunk C4)`)

if (clusters.length === 0) {
  return {
    phase_reached: 'scan',
    halted: 'zero-clusters-after-scan',
    scan_results: scanResults,
    failed_batch_ids: failedBatchIds,
    empty_content_batch_ids: emptyContentBatchIds,
    malformed_tag_batch_ids: malformedTagBatchIds,
    malformed_tag_nugget_count: malformedTagNuggetCount,
  }
}

// ---------------------------------------------------------------------------------------------
// Wave 2 — Sonnet xM, one-agent-owns-one docs/wiki/<topic>.md. Additive + provenance direct
// write. resumeFromRunId re-runs only the synths that failed on a prior attempt (the Workflow
// runtime resumes cached-successful phases/agents automatically on `resumeFromRunId`; each
// agent() call here is independently cacheable per the tool's same-script+same-args contract).
// ---------------------------------------------------------------------------------------------

function slugifyTopic(topicKey) {
  return topicKey
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

// ---------------------------------------------------------------------------------------------
// Provenance schema (§ distill.md § 5b) — the AC requires machine-readable YAML frontmatter on
// disk, not the HTML-comment spec-backlink alone. Run 2026-08-06's 25 Wave-2 files all landed
// `<!-- PROVENANCE: ... -->` comments with no frontmatter: human-readable lineage survived,
// `git show <last_verbose_sha>:<original_path>` did not, because the SHA never reached a
// parseable field. `run_id` is the only hard-required field (always knowable, never fabricated);
// the other four are each individually optional PROVIDED a matching `omitted_reasons` entry
// explains why — a fabricated SHA is worse than an absent one; it fails only at the moment
// someone needs the retrieval recipe to actually work. Do NOT relax `run_id` to optional too —
// unlike the archived-spec fields, the agent always knows which run it is.
// ---------------------------------------------------------------------------------------------
const PROVENANCE_SCHEMA = {
  type: 'object',
  required: ['run_id'],
  properties: {
    run_id: { type: 'string' },
    archived_spec: { type: 'string' },
    original_path: { type: 'string' },
    last_verbose_sha: { type: 'string' },
    distilled: { type: 'string' },
    // Keyed by the field name omitted (one of the four optional fields above) -> a stated
    // reason ("no archived-spec source for this nugget", "SHA not resolvable from evidence at
    // hand", etc). NEVER a substitute for guessing a plausible-looking value into the field
    // itself — omission-with-reason is the only correct response to thin evidence.
    omitted_reasons: { type: 'object' },
  },
}

const SYNTH_SCHEMA = {
  type: 'object',
  required: ['topic_key', 'wiki_path', 'op', 'provenance'],
  properties: {
    topic_key: { type: 'string' },
    wiki_path: { type: 'string' },
    op: { type: 'string', enum: ['created', 'updated', 'skipped'] },
    dispositions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['nugget_id', 'op'],
        properties: {
          nugget_id: { type: 'string' },
          op: { type: 'string', enum: ['ADD_SECTION', 'UPDATE_SECTION', 'REMOVE_SECTION', 'CREATE_DR', 'SKIP'] },
          reason: { type: 'string' },
        },
      },
    },
    provenance: PROVENANCE_SCHEMA,
    reason: { type: 'string' }, // required when op === 'skipped'
  },
}

// ---------------------------------------------------------------------------------------------
// Candidate-restatement check (Wave 1.5) — one Haiku agent() per cluster, dispatched to relay
// C1's `learn-lessons-reconcile-candidates` CLI via Bash and hand back its result verbatim,
// forced-schema return. This threads `candidate_restatements` into the Wave-2 synth brief below
// as a field computed AHEAD OF the synth agent — the CLI is invoked by this relay wave, never
// by the Wave-2 synth agent itself (push-not-pull: the CLI survives only as a bulk/backfill
// accelerator and as the thing an EMITTER calls in-process; the acting synth agent reads the
// field, it never runs a command to obtain it).
//
// NOT a deterministic assembler call, despite the "computed ahead" framing above: the relay is
// an LLM agent, not in-process code — it depends on the dispatched Haiku correctly writing the
// scratch file, correctly invoking the CLI as literal text, and correctly relaying the printed
// JSON verbatim rather than fabricating a plausible-looking result. Nothing here audits that the
// CLI was actually invoked. A relay agent that errors, times out, or fabricates degrades to the
// exact same empty-list shape as "the target genuinely has no overlapping candidates" (see the
// `|| []` fallback below) — those two states are indistinguishable on disk once collapsed into
// the routing record.
//
// Runs for every cluster, new-guide or existing-guide alike — the CLI itself returns
// ok/empty-candidates for a target that doesn't exist yet, so calling it unconditionally is safe
// and keeps the synth brief's shape uniform.
// ---------------------------------------------------------------------------------------------

const CANDIDATES_SCHEMA = {
  type: 'object',
  required: ['topic_key', 'wiki_path', 'candidate_restatements'],
  properties: {
    topic_key: { type: 'string' },
    wiki_path: { type: 'string' },
    // Pinned field shape (do not vary): candidate_restatements: [{line, excerpt}]. The CLI's
    // own candidate objects also carry a `signal` ("phrase-overlap"|"heading-duplicate") — the
    // routing record does not carry it; the candidates agent below drops it on the way in.
    candidate_restatements: {
      type: 'array',
      items: {
        type: 'object',
        required: ['line', 'excerpt'],
        properties: {
          line: { type: 'number' },
          excerpt: { type: 'string' },
        },
      },
    },
  },
}

phase('candidates')
const candidatesBriefFor = (cluster) => {
  const slug = slugifyTopic(cluster.topicKey)
  const existingPath = WIKI_SLUGS[slug]
  const wikiPath = cluster.wikiPath || existingPath || `${WIKI_DIRS[0]}/${slug}.md`
  const incomingText = cluster.nuggets.map((n) => n.content || '').filter(Boolean).join('\n\n')

  return COMMON + `

You are a Haiku candidate-restatement scout (Wave 1.5 of the /distill harvest Workflow). You
are a mechanical relay, not a judge — run the CLI below and hand back its result verbatim.

Target wiki path: ${wikiPath}
Incoming content (the nuggets about to be synthesized into that file):
${JSON.stringify(incomingText)}

Write the incoming content above to
state/scratch/artifact-distillation/${RUN_ID}/candidates-${slugifyTopic(cluster.topicKey)}.txt,
then run:
  learn-lessons-reconcile-candidates ${wikiPath} --text-file <the scratch file path above>
(If the bareword isn't on PATH, resolve it via
"\${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/learn-lessons-reconcile-candidates".)
Exit 0 is the normal/ok outcome, including when the target file doesn't exist yet — do not
treat that as a failure.

Parse the printed decision-object JSON from stdout. Its candidate list rides on the "gates"
key (it may be the array itself, or nested at gates.candidates — inspect the actual returned
JSON and use whichever shape is present); each candidate carries {line, excerpt, signal}. An
empty list is a normal, valid result. Return topic_key '${cluster.topicKey}', wiki_path
'${wikiPath}', and candidate_restatements as those candidates mapped to exactly {line, excerpt}
pairs — drop the signal field, it is not part of the routing record.`
}

const candidatesResults = (await parallel(
  clusters.map((cluster) => () =>
    agent(candidatesBriefFor(cluster), {
      schema: CANDIDATES_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'candidates',
      label: `cand-${slugifyTopic(cluster.topicKey)}`,
      model: 'haiku',
    })
  ),
  { concurrency: CONCURRENCY_CAP }
)).filter(Boolean)

// A candidates-agent failure degrades to an empty candidate list for that cluster (via the
// Map lookup's `|| []` fallback inside buildCandidatesByTopic below) — never a block, and never
// a reason for the Wave-2 synth agent to run the CLI itself to backfill the gap. Pulled out to
// a named function (rather than left inline) so this fallback/sanity-check logic is
// unit-testable independent of the Workflow-sandbox `agent()`/`parallel()` runtime calls above
// it — see `tests/distill-harvest.test.js` § Finding-3 fallback-path coverage.
//
// `wiki_path` rides in the schema alongside `topic_key`/`candidate_restatements` but is never
// itself consumed downstream — used here only as a sanity cross-check against the target this
// wave itself computed for the same cluster, to catch a relay agent that echoed a stale or
// hallucinated path rather than the one it was actually told to run against.
function buildCandidatesByTopic(candidatesResultsIn, clustersIn, wikiSlugsIn, wikiDirsIn, logFn) {
  return new Map(
    candidatesResultsIn.map((r) => {
      const matchingCluster = clustersIn.find((c) => c.topicKey === r.topic_key)
      if (matchingCluster) {
        const slug = slugifyTopic(matchingCluster.topicKey)
        const expectedWikiPath = matchingCluster.wikiPath || wikiSlugsIn[slug] || `${wikiDirsIn[0]}/${slug}.md`
        if (r.wiki_path !== expectedWikiPath) {
          logFn(`candidates: wiki_path sanity check failed for topic_key='${r.topic_key}' — agent ` +
            `returned '${r.wiki_path}', expected '${expectedWikiPath}'. candidate_restatements ` +
            `below are keyed by topic_key regardless, but this mismatch may indicate the relay ` +
            `ran the CLI against the wrong target.`)
        }
      }
      return [r.topic_key, r.candidate_restatements || []]
    })
  )
}

const candidatesByTopic = buildCandidatesByTopic(candidatesResults, clusters, WIKI_SLUGS, WIKI_DIRS, log)

phase('synth')
const synthBriefFor = (cluster) => {
  // D2: target resolved from disk reality (WIKI_SLUGS), not a topicKey-keyed Phase-0 guess.
  // D3: honor a target the consolidation pass already set (homed merges, the misc bucket) —
  // only fall back to fresh disk-resolution for a genuinely new cluster.
  const slug = slugifyTopic(cluster.topicKey)
  const existingPath = WIKI_SLUGS[slug]
  const wikiPath = cluster.wikiPath || existingPath || `${WIKI_DIRS[0]}/${slug}.md`
  const existing = Boolean(existingPath)
  const candidates = candidatesByTopic.get(cluster.topicKey) || []

  return COMMON + `

You are a Sonnet knowledge-synthesis agent (Wave 2 of the /distill harvest Workflow).

You own EXACTLY ONE output file: ${wikiPath}. This is a disjoint-file assignment — no other
agent in this run touches this path; do not touch any other docs/wiki/*.md file.

Your topic: ${cluster.topicKey}
Nuggets assigned to you (canonical Phase-1 ids, carry every id through to your disposition
manifest — do not drop any):
${JSON.stringify(cluster.nuggets, null, 2)}

${existing
  ? `This guide already exists at ${wikiPath}. Read it first. MERGE ADDITIVELY: only add or ` +
    `update sections where these nuggets provide genuine new information; do not rewrite ` +
    `unchanged sections (guide-drift is a known failure mode). Preserve reasoning behind ` +
    `existing decisions.`
  : `This is a NEW guide. Produce a complete document: H1 title, Overview, Architecture, Key ` +
    `Patterns, Gotchas, Reference sections as applicable to the nuggets you were given.`}

The routing record already carries candidate_restatements for ${wikiPath} — computed ahead of
this brief, nothing for you to run: ${JSON.stringify(candidates)}. ${candidates.length > 0
    ? `For each candidate, either amend the existing statement in place (if one of your nuggets ` +
      `restates it) or record in that nugget's disposition reason why both must coexist as ` +
      `separate statements — do not silently add a duplicate.`
    : `No restatement candidates were found against this target — proceed with normal additive ` +
      `synthesis.`}

Stamp PROVENANCE on every section you add or update, TWO ways, both required:
1. The human-readable spec-backlink comment as before: \`<!-- PROVENANCE: run ${RUN_ID},
   derived from <nugget id(s)> -->\`, per docs/wiki/rag-bait-conventions.md.
2. Machine-readable YAML frontmatter at the TOP of ${wikiPath} (add it if the file has none;
   merge into it if it already has frontmatter — never duplicate the block), per
   docs/wiki/rag-bait-conventions.md § 5b:
     provenance:
       - archived_spec: <path, if this nugget traces to an archived spec>
         original_path: <pre-move path, if applicable>
         last_verbose_sha: <a REAL sha you resolved from git, never guessed>
         distilled: <today's date>
         run_id: ${RUN_ID}
   If you cannot resolve a field from real evidence (no archived-spec source, no resolvable
   SHA), OMIT that field from the entry rather than filling in a plausible-looking value — a
   fabricated retrieval recipe is worse than an absent one; it fails only when someone actually
   needs it. This applies per-field, not all-or-nothing.

This is a direct write — write straight to ${wikiPath} with the Write/Edit tool (additive
knowledge writes are not staged for a manual apply step in this pipeline; only deletions are
PM-gated, and this Workflow performs no deletions).

Do NOT git commit — the EM commits from your returned manifest after this run completes.

Return the schema-required fields, including a dispositions[] entry for every nugget_id you
were assigned (op ADD_SECTION/UPDATE_SECTION/REMOVE_SECTION/CREATE_DR/SKIP, with a reason for
any SKIP — e.g. "EPHEMERAL at source", "SUPERSEDED at source", "AMBIGUOUS — folded into
existing section X, or still unclassifiable at synth time"). Set op: 'skipped' at the top
level only if you produced no file changes at all (rare — note why in reason).

Also return \`provenance\`: an object with \`run_id: '${RUN_ID}'\` (always required) plus
whichever of \`archived_spec\`/\`original_path\`/\`last_verbose_sha\`/\`distilled\` you resolved
from real evidence for this file's frontmatter block above. For any of those four you omitted
from the frontmatter, include a matching entry in \`omitted_reasons\` (keyed by field name)
stating why — never guess a value here either.`
}

const synthResults = (await parallel(
  clusters.map((cluster) => () =>
    agent(synthBriefFor(cluster), {
      schema: SYNTH_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'synth',
      label: slugifyTopic(cluster.topicKey),
      model: 'sonnet',
    })
  ),
  { concurrency: CONCURRENCY_CAP }
)).filter(Boolean)

const failedTopicKeys = clusters
  .map((c) => c.topicKey)
  .filter((topicKey) => !synthResults.some((r) => r.topic_key === topicKey))

if (failedTopicKeys.length > 0) {
  // A partial failure here is expected to be handled by re-invoking this Workflow with
  // resumeFromRunId set to THIS invocation's Workflow-tool run id (`wf_...`, from the tool
  // result) — not to `run_id` below, which is this pipeline's own distillation slug and is not a
  // valid resume handle. Wave 1 (scan) then replays from the journal for free; only the failed
  // synth agent()s above re-run. Do NOT merge this halt into a re-scan.
  return {
    phase_reached: 'synth',
    halted: 'synth-partial-failure',
    run_id: RUN_ID,
    concurrency_cap: CONCURRENCY_CAP,
    scan_results: scanResults,
    failed_batch_ids: failedBatchIds,
    empty_content_batch_ids: emptyContentBatchIds,
    malformed_tag_batch_ids: malformedTagBatchIds,
    malformed_tag_nugget_count: malformedTagNuggetCount,
    clusters_attempted: clusters.length,
    synth_results: synthResults,
    failed_topic_keys: failedTopicKeys,
    resume_hint:
      "Re-invoke this Workflow with resumeFromRunId set to this invocation's Workflow-tool " +
      'runId (wf_...), NOT to run_id above; only failed synth agent()s re-run.',
  }
}

// ---------------------------------------------------------------------------------------------
// Coverage gate — mechanical set-diff, no dispatch. Retires the former Phase 2.7-QG Haiku
// ×M-per-cluster wave (distill.md / PIPELINE.md): the check is pure set membership (each
// cluster's dispositions[] nugget_ids vs. its assigned nugget IDs), which the 2026-07-22-23h55
// dogfood run computed in ~20 lines of Python from journal.jsonl (259/262 covered, 3 uncovered)
// — dispatching agents to do a set-diff was waste and a source of nondeterminism. Runs here,
// in-process, immediately after Wave 2 succeeds.
// ---------------------------------------------------------------------------------------------

function findCoverageGaps(clusters, results) {
  const resultsByTopic = new Map(results.map((r) => [r.topic_key, r]))
  const gaps = []
  for (const cluster of clusters) {
    const result = resultsByTopic.get(cluster.topicKey)
    if (!result) continue // failed synth — already reported via failedTopicKeys above
    const coveredIds = new Set((result.dispositions || []).map((d) => d.nugget_id))
    const uncoveredNuggets = cluster.nuggets.filter((n) => !coveredIds.has(n.id))
    if (uncoveredNuggets.length > 0) {
      gaps.push({ topicKey: cluster.topicKey, wikiPath: result.wiki_path, uncoveredNuggets })
    }
  }
  return gaps
}

phase('coverage-gate')
const totalAssignedNuggets = clusters.reduce((n, c) => n + c.nuggets.length, 0)
const coverageGaps = findCoverageGaps(clusters, synthResults)
const totalUncoveredNuggets = coverageGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0)
log(`coverage gate: ${totalAssignedNuggets - totalUncoveredNuggets}/${totalAssignedNuggets} ` +
  `nuggets covered (${coverageGaps.length} gap cluster(s)` +
  `${coverageGaps.length ? ': ' + coverageGaps.map((g) => g.topicKey).join(', ') : ''})`)

let gapSynthResults = []
if (coverageGaps.length > 0) {
  const gapSynthBriefFor = (gap) => {
    const gapCandidates = candidatesByTopic.get(gap.topicKey) || []
    return COMMON + `

You are a Sonnet knowledge-synthesis agent (coverage-gate re-synth, Wave 2 follow-up of the
/distill harvest Workflow).

A prior synth pass on ${gap.wikiPath} did not carry every nugget it was assigned into its
returned dispositions[] manifest. Re-open ${gap.wikiPath} and additively integrate ONLY the
following previously-uncovered nuggets — do not touch or re-derive content covering any other
nugget id, and do not rewrite unchanged sections:
${JSON.stringify(gap.uncoveredNuggets, null, 2)}

The routing record already carries candidate_restatements for ${gap.wikiPath} — computed ahead
of this brief, nothing for you to run: ${JSON.stringify(gapCandidates)}. ${gapCandidates.length > 0
      ? `For each candidate, either amend the existing statement in place (if one of the nuggets ` +
        `above restates it) or record in that nugget's disposition reason why both must coexist ` +
        `as separate statements.`
      : `No restatement candidates were found against this target — proceed with normal ` +
        `additive integration.`}

Stamp PROVENANCE on every section you add or update, TWO ways, both required — same as the
main synth pass:
1. The human-readable spec-backlink comment: \`<!-- PROVENANCE: run ${RUN_ID}, derived from
   <nugget id(s)> -->\`, per docs/wiki/rag-bait-conventions.md.
2. Machine-readable YAML frontmatter at the TOP of ${gap.wikiPath} (add it if none exists;
   merge into existing frontmatter — never duplicate the block), per
   docs/wiki/rag-bait-conventions.md § 5b (\`archived_spec\`/\`original_path\`/
   \`last_verbose_sha\`/\`distilled\`/\`run_id\`). Omit any of the four optional fields you
   cannot resolve from real evidence rather than guessing a plausible value.

Direct write to ${gap.wikiPath} with the Write/Edit tool. Do NOT git commit — the EM commits from
your returned manifest after this run completes.

Set topic_key to exactly '${gap.topicKey}' and wiki_path to exactly '${gap.wikiPath}' in your
return. Return a dispositions[] entry for every nugget_id listed above (op
ADD_SECTION/UPDATE_SECTION/REMOVE_SECTION/CREATE_DR/SKIP, with a reason for any SKIP).

Also return \`provenance\`: an object with \`run_id: '${RUN_ID}'\` (always required) plus
whichever of \`archived_spec\`/\`original_path\`/\`last_verbose_sha\`/\`distilled\` you resolved
for this file's frontmatter block. For any omitted, include a matching \`omitted_reasons\` entry
stating why.`
  }

  gapSynthResults = (await parallel(
    coverageGaps.map((gap) => () =>
      agent(gapSynthBriefFor(gap), {
        schema: SYNTH_SCHEMA,
        agentType: 'coordinator:executor',
        phase: 'coverage-gate',
        label: `gap-${slugifyTopic(gap.topicKey)}`,
        model: 'sonnet',
      })
    ),
    { concurrency: CONCURRENCY_CAP }
  )).filter(Boolean)

  // Merge gap-synth dispositions back into the owning cluster's original synth result — union by
  // nugget_id, gap-synth entries fill only ids the original result was missing.
  const synthResultsByTopic = new Map(synthResults.map((r) => [r.topic_key, r]))
  for (const gapResult of gapSynthResults) {
    const original = synthResultsByTopic.get(gapResult.topic_key)
    if (!original) continue
    const existingIds = new Set((original.dispositions || []).map((d) => d.nugget_id))
    const newDispositions = (gapResult.dispositions || []).filter((d) => !existingIds.has(d.nugget_id))
    original.dispositions = [...(original.dispositions || []), ...newDispositions]
  }
}

const failedGapTopicKeys = coverageGaps
  .map((g) => g.topicKey)
  .filter((topicKey) => !gapSynthResults.some((r) => r.topic_key === topicKey))
const remainingGaps = findCoverageGaps(clusters, synthResults)
if (remainingGaps.length > 0) {
  log(`coverage gate: ${remainingGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0)} ` +
    `nugget(s) still uncovered after gap re-synth (gap agent failure) — ` +
    `${remainingGaps.map((g) => g.topicKey).join(', ')}`)
}

// ---------------------------------------------------------------------------------------------
// Distillation-log rows — the Workflow becomes the named producer of Phase 5c's per-artifact
// disposition log instead of leaving it to EM-side hand-assembly from the journal. Computed
// here, after the coverage-gate merge-back, so gap-synth dispositions (folded into each
// original synth result's `dispositions[]` in place, above) count toward DISTILLED.
//
// Negative-spec: a file whose batch never scanned (failedBatchIds) gets `SKIP`, never
// `EPHEMERAL` — "never reviewed" and "reviewed, found routine" are different verdicts, and
// collapsing them is the exact mislabeling this whole change exists to stop.
//
// Negative-spec (artifact-level): the guard above is batch-granular, but the claim it backs is
// artifact-granular. A batch can report success while the scan agent silently omits one of its
// files — no fate line in `fateByPath` AND no nuggets in `nuggetIdsBySource` for that path. That
// artifact was never actually reviewed even though its batch was, so it gets `SKIP`, not
// `EPHEMERAL` — collapsing "batch succeeded" into "this artifact was reviewed" lets an
// un-reviewed artifact fall through to EPHEMERAL and then Phase 3d's DELETE mapping. An artifact
// WITH a fate line and zero nuggets stays EPHEMERAL — only the no-fate-AND-no-nuggets case flips.
// ---------------------------------------------------------------------------------------------
function countWords(s) {
  return (s || '').trim().split(/\s+/).filter(Boolean).length
}

const fateByPath = new Map()
for (const result of scanResults) {
  for (const f of result.file_fates || []) {
    if (f.path) fateByPath.set(f.path, f.fate_prose || '')
  }
}

const nuggetIdsBySource = new Map()
for (const result of scanResults) {
  for (const n of result.nuggets || []) {
    if (!n.source || !n.id) continue
    if (!nuggetIdsBySource.has(n.source)) nuggetIdsBySource.set(n.source, [])
    nuggetIdsBySource.get(n.source).push(n.id)
  }
}

const dispositionOpByNuggetId = new Map()
for (const r of synthResults) {
  for (const d of r.dispositions || []) {
    // Non-SKIP wins: a nugget carried by two dispositions is harvested if either one kept it,
    // and last-write-wins would let an incidental SKIP mask a real integration.
    const prior = dispositionOpByNuggetId.get(d.nugget_id)
    if (prior && prior !== 'SKIP') continue
    dispositionOpByNuggetId.set(d.nugget_id, d.op)
  }
}

// ---------------------------------------------------------------------------------------------
// Fate-prose enforcement — the AC (>= 8 words, a CONTEXT.md term where terms are supplied) was
// asserted in the scan brief and never mechanically checked; the 2026-08-06 rows were
// mechanically-derived index-bait despite the prompt asking for domain prose. `context_terms`
// reads 'unavailable' rather than a silently-passing 0 when `contextTerms` is empty — a gate
// that reports clean because it had no input to check is the same defect as the unchecked join
// this file exists to fix ("found nothing" and "looked at nothing" are different verdicts).
// ---------------------------------------------------------------------------------------------
const distillationLogRows = []
const shortProse = []
const missingContextTerm = []
let fatePassing = 0

for (const batch of BATCHES) {
  const scanned = !failedBatchIds.includes(batch.batchId)
  for (const path of batch.files) {
    const touched = fateByPath.has(path) || (nuggetIdsBySource.get(path) || []).length > 0
    const disposition = (!scanned || !touched)
      ? 'SKIP'
      : (nuggetIdsBySource.get(path) || []).some((id) => {
          const op = dispositionOpByNuggetId.get(id)
          return op && op !== 'SKIP'
        })
        ? 'DISTILLED'
        : 'EPHEMERAL'

    let fate
    if (!fateByPath.has(path)) {
      fate = 'FATE-PROSE-MISSING: no fate line returned by scan agent'
    } else {
      const prose = fateByPath.get(path)
      const words = countWords(prose)
      const wordsOk = words >= 8
      const termOk = CONTEXT_TERMS.length === 0
        || CONTEXT_TERMS.some((t) => prose.toLowerCase().includes(String(t).toLowerCase()))
      if (!wordsOk) shortProse.push(path)
      if (CONTEXT_TERMS.length > 0 && !termOk) missingContextTerm.push(path)
      if (wordsOk && termOk) {
        fatePassing++
        fate = prose
      } else {
        const reasons = []
        if (!wordsOk) reasons.push(`only ${words} word(s), need >= 8`)
        if (CONTEXT_TERMS.length > 0 && !termOk) reasons.push('no CONTEXT.md term present')
        // The rejected prose rides along: without it the EM has nothing to repair the row from
        // short of re-reading the artifact, which defeats the point of the scan agent writing it.
        fate = `FATE-PROSE-INVALID (${reasons.join('; ')}): ${prose}`
      }
    }

    distillationLogRows.push({ path, disposition, fate })
  }
}

const fateProseEnforcement = {
  rows: distillationLogRows.length,
  passing: fatePassing,
  short_prose: shortProse,
  missing_context_term: missingContextTerm,
  context_terms: CONTEXT_TERMS.length > 0 ? CONTEXT_TERMS.length : 'unavailable',
}

// ---------------------------------------------------------------------------------------------
// Provenance completeness — validates the RETURNED provenance objects only (schema-shape and
// per-field omitted-vs-present bookkeeping over synthResults[]). It does NOT prove the YAML
// frontmatter this describes actually landed on disk in ${wiki_path} — that a returned object
// matches the schema is not evidence the agent wrote it there rather than merely describing what
// it intended. Confirming disk-truth is an EM-side check (grep the wiki file for the
// `provenance:` key); this is a reporting aid over the agent's own claim, not a disk gate, and
// it never suppresses or blocks anything downstream (contrast join_integrity above, which does).
// ---------------------------------------------------------------------------------------------
const PROVENANCE_OPTIONAL_FIELDS = ['archived_spec', 'original_path', 'last_verbose_sha', 'distilled']

function computeProvenanceCompleteness(results) {
  const missingFieldsEntries = []
  const omittedWithReason = []
  let complete = 0
  for (const r of results) {
    const prov = r.provenance
    if (!prov || !prov.run_id) {
      missingFieldsEntries.push({ wiki_path: r.wiki_path, fields: ['run_id'] })
      continue
    }
    const reasons = prov.omitted_reasons || {}
    const missing = []
    for (const field of PROVENANCE_OPTIONAL_FIELDS) {
      if (prov[field] !== undefined && prov[field] !== null && prov[field] !== '') continue
      if (Object.prototype.hasOwnProperty.call(reasons, field)) {
        omittedWithReason.push({ wiki_path: r.wiki_path, field, reason: reasons[field] })
      } else {
        missing.push(field)
      }
    }
    if (missing.length > 0) {
      missingFieldsEntries.push({ wiki_path: r.wiki_path, fields: missing })
    } else {
      complete++
    }
  }
  return {
    files: results.length,
    complete,
    missing_fields: missingFieldsEntries,
    omitted_with_reason: omittedWithReason,
  }
}

const provenanceCompleteness = computeProvenanceCompleteness(synthResults)
log(`provenance completeness: ${provenanceCompleteness.complete}/${provenanceCompleteness.files} ` +
  `file(s) carry complete provenance (returned-object check only — does not prove the ` +
  `frontmatter reached disk)` +
  (provenanceCompleteness.missing_fields.length
    ? `; ${provenanceCompleteness.missing_fields.length} file(s) missing required field(s) with no stated reason`
    : ''))

// ---------------------------------------------------------------------------------------------
// Phase 2.5 — Judgment mining (Sonnet, one agent per topic-cluster, all simultaneous), folded
// into this Workflow per docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md chunk C5,
// replacing the hand-orchestrated Phase 2.5 (PIPELINE.md § "Phase 2.5: Judgment Mining",
// agent-prompts/phase-2-5-judgment-mining.md, agent-prompts/phase-2-5.md). Mines the run's
// reviewer sidecars for cross-spec convergence and emits judgment-proposals for Phase 3b review
// and wiki promotion into docs/wiki/codebase-judgment/ — this phase never writes there itself;
// that promotion write, and its on-disk frontmatter shape (`judgment_provenance:`, consulted by
// prior-art-checker on every plan check — do not change it), stay Phase 3b's job.
//
// PIPELINE.md:604-612 constraints, carried verbatim:
//   - Read-only orchestrator boundary: this Workflow dispatches mining agents directly; no
//     mining agent is permitted to dispatch a nested sub-agent of its own (same
//     agentType: 'coordinator:executor' read-only-orchestrator role every other wave here uses).
//   - Strict sequencing: Phase 2 AND its in-Workflow Coverage Gate (immediately above) are fully
//     complete before this section runs — structural by placement, not a runtime check.
//   - Convergence threshold defaults to 3, overridable via /distill --min-convergence=N
//     (MIN_CONVERGENCE above) — the flag keeps working through this Workflow unchanged.
//
// Concurrency: reuses CONCURRENCY_CAP (already a literal const per the D1 fix documented at its
// declaration above) — this phase introduces no new concurrency/parallelism constant of its own,
// per docs/wiki/distill-harvest-pipeline-defects.md D1 (no `await import('node:os')`, ever).
// ---------------------------------------------------------------------------------------------
phase('judgment-mining-2-5')

const JUDGMENT_SCRATCH_PATH = `state/scratch/artifact-distillation/${RUN_ID}/judgment-proposals.md`

const JUDGMENT_SCHEMA = {
  type: 'object',
  required: ['topic_cluster', 'action'],
  properties: {
    topic_cluster: { type: 'string' },
    topic: { type: 'string' },
    verdict_direction: { type: 'string', enum: ['forbid', 'require', 'prefer', 'avoid'] },
    convergence_count: { type: 'number' },
    action: { type: 'string', enum: ['new-entry', 'increment-existing', 'no-convergence', 'no-change'] },
    source_findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['sidecar', 'plan'],
        properties: {
          sidecar: { type: 'string' },
          plan: { type: 'string' },
          reviewer: { type: 'string' },
          finding_id: { type: 'string' },
          sha: { type: 'string' },
        },
      },
    },
    proposed_wiki_content: { type: 'string' },
  },
}

const judgmentBriefFor = (cluster) => COMMON + `

You are a Sonnet judgment-mining agent (Phase 2.5 of the /distill harvest Workflow, folded into
this Workflow per PIPELINE.md § "Phase 2.5: Judgment Mining"). Read-only orchestrator boundary:
you dispatch no nested sub-agents of your own.

Your assigned topic cluster: ${cluster.topicCluster}
Verdict direction: ${cluster.verdictDirection}
Live sidecar files to read: ${JSON.stringify(cluster.liveSidecarPaths || [])}
Existing judgment entry (or NONE): ${cluster.existingJudgmentEntry || 'NONE'}
Convergence threshold (MIN_CONVERGENCE): ${MIN_CONVERGENCE}
Run ID: ${RUN_ID}

Read every file in "Live sidecar files to read". Extract only ELIGIBLE findings: architectural
recommendations, recurring design constraints, anti-pattern prohibitions, structural
requirements flagged as pattern-level. Exclude unconditionally: mechanical/formatting findings,
and docs-checker-class findings (wrong import, stale signature, incorrect function name).

Then apply the integrator's dispositions. They are NOT on the findings — review-integrator is
forbidden to annotate findings inline (agents/review-integrator.md, Sidecar Disposition
Annotation: no \`disposition\` fields on finding objects, no \`**Disposition:**\` lines, body
preserved verbatim). They arrive as ONE bulk \`## Integrator Dispositions\` block appended at the
end of the sidecar, keyed by bucket, not by finding:

    ## Integrator Dispositions
    \`\`\`yaml
    schema_version: 1
    applied: [A-F1, A-F2]
    escalated-disagree: [A-F3]
    escalated-ask: []
    escalated-p0: []
    deferred: []
    verified-no-action: [A-F4]
    \`\`\`

Find that heading, parse the fenced yaml under it, invert to finding-id -> bucket. If more than
one block is present the LAST one wins — the block is append-only and never edited, so a
correction arrives as a later block superseding an earlier one. Then:
  - applied / escalated-ask / escalated-p0 / deferred -> ELIGIBLE
  - escalated-disagree -> INELIGIBLE, skip
  - verified-no-action -> INELIGIBLE, skip
  - a finding in no bucket, or a sidecar with no \`## Integrator Dispositions\` heading at all
    -> ELIGIBLE (predates the annotation)

Do NOT look for a per-finding \`disposition:\` field. Nothing writes one. A read keyed on it
finds nothing, excludes nothing, and silently counts every rejected verdict as convergence
evidence — the exact outcome this exclusion exists to prevent.

A finding shape-matches this cluster iff its claim-topic noun is semantically equivalent to
"${cluster.topicCluster}" AND its verdict-direction matches "${cluster.verdictDirection}" — read
with judgment, this is semantic equivalence, not lexical matching. Each PLAN contributes at most
ONE count toward convergence regardless of how many of its findings match.

If the existing judgment entry above is NONE (new topic): emit a new-entry proposal when the
count of distinct contributing plans is >= ${MIN_CONVERGENCE}; otherwise emit a no-convergence
entry. If an existing judgment entry path is given (existing topic): read it for its current
convergence_count and source_findings; any single new live finding that shape-matches triggers
an increment-existing proposal (append to source_findings, convergence_count + 1); no matching
new finding triggers a no-change entry. Do NOT re-\`git show\` the existing entry's prior
source_findings[*].sha to re-mine it — the topic key is the join, not re-shape-matched.

Read ${JUDGMENT_SCRATCH_PATH} first — it may already carry proposals from sibling agents running
in this same fan-out. Append (never overwrite) your proposal in this format:

## Proposal: ${cluster.topicCluster}

**Topic:** <claim-topic noun>
**Verdict direction:** ${cluster.verdictDirection}
**Convergence count:** N
**Action:** new-entry | increment-existing | no-convergence | no-change

### Source findings

| Sidecar | Plan | Reviewer | Finding ID | SHA |
|---------|------|----------|------------|-----|

### Proposed wiki content

<!-- For new-entry: the full proposed docs/wiki/codebase-judgment/<topic-slug>.md body,
     including \`judgment_provenance:\` frontmatter (NEVER \`provenance:\` — that key is reserved
     by Phase 5b's archived-spec schema, an incompatible list-of-objects shape). For
     increment-existing: a one-line note ("Increment convergence_count to N; append <sidecar> to
     source_findings."). For no-convergence/no-change: a brief explanation. -->

Do NOT write to docs/wiki/codebase-judgment/ yourself — promotion is Phase 3b's job, gated on
this proposal, never yours to perform. Do NOT git commit.

Set topic_cluster in your return to exactly '${cluster.topicCluster}'. Return every
source_findings[] entry you cited (never drop one you counted) and proposed_wiki_content
carrying exactly what you appended under "### Proposed wiki content" above.`

let judgmentResults = []
if (JUDGMENT_CLUSTERS.length > 0) {
  judgmentResults = (await parallel(
    JUDGMENT_CLUSTERS.map((cluster) => () =>
      agent(judgmentBriefFor(cluster), {
        schema: JUDGMENT_SCHEMA,
        agentType: 'coordinator:executor',
        phase: 'judgment-mining-2-5',
        label: `judgment-${slugifyTopic(cluster.topicCluster)}`,
        model: 'sonnet',
      })
    ),
    { concurrency: CONCURRENCY_CAP }
  )).filter(Boolean)

  const failedJudgmentClusters = JUDGMENT_CLUSTERS
    .map((c) => c.topicCluster)
    .filter((topicCluster) => !judgmentResults.some((r) => r.topic_cluster === topicCluster))
  if (failedJudgmentClusters.length > 0) {
    log(`judgment-mining: ${failedJudgmentClusters.length}/${JUDGMENT_CLUSTERS.length} cluster(s) ` +
      `failed to return a result: ${failedJudgmentClusters.join(', ')}`)
  }
  log(`judgment-mining: ${judgmentResults.length}/${JUDGMENT_CLUSTERS.length} cluster(s) reported ` +
    `(min_convergence=${MIN_CONVERGENCE}) — ` +
    `${judgmentResults.filter((r) => r.action === 'new-entry').length} new-entry, ` +
    `${judgmentResults.filter((r) => r.action === 'increment-existing').length} increment-existing, ` +
    `${judgmentResults.filter((r) => r.action === 'no-convergence' || r.action === 'no-change').length} no-op`)
} else {
  log('judgment-mining: no judgmentClusters provided — phase reports unavailable, not zero-proposals ' +
    '("looked at nothing" != "found nothing")')
}

const judgmentMining = {
  min_convergence: MIN_CONVERGENCE,
  clusters_processed: JUDGMENT_CLUSTERS.length,
  scratch_path: JUDGMENT_SCRATCH_PATH,
  proposals: judgmentResults,
  status: JUDGMENT_CLUSTERS.length > 0 ? 'ran' : 'unavailable',
}

// ---------------------------------------------------------------------------------------------
// Phase 3a — Contradiction detection (Sonnet, parallel by cluster) plus the mechanical
// cross-cluster check and the conditional Opus escalation, folded into this Workflow per
// docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md chunk C6a, replacing the
// hand-orchestrated Phase 3a (PIPELINE.md § "Phase 3a: Contradiction Detection",
// agent-prompts/phase-3a.md, agent-prompts/phase-3-esc.md). Compares the Phase-2 synthesized
// wiki content within each caller-supplied cluster for contradictions, escalating only the
// genuinely unresolvable ones.
//
// PIPELINE.md:616-658 constraints, carried verbatim:
//   - Sharding: one Sonnet agent per cluster, all simultaneous — each agent compares only the
//     topics inside its own cluster (intra-cluster). Cross-cluster contradictions are NOT this
//     agent's job (see the mechanical check below).
//   - Single-topic cluster exemption: a cluster with < 2 topicKeys cannot have an intra-cluster
//     contradiction by definition — no agent is dispatched for it; it is folded in as a
//     zero-contradiction result directly.
//   - The cross-cluster check is MECHANICAL (plain JS over the returned contradiction_refs), not
//     a subagent dispatch — "the coordinator reads the 3a scratch files directly" (PIPELINE.md:642),
//     here the in-memory schema-forced results standing in for those scratch files per the same
//     folding this Workflow already applied to Phase 2.5.
//   - Opus escalation is CONDITIONAL, never unconditional: it fires only when the total
//     unresolvable-contradiction count across clusters is > 0 OR the cross-cluster check finds at
//     least one candidate (PIPELINE.md:648). Zero of either -> proceed with no escalation.
//
// D3 (docs/wiki/distill-harvest-pipeline-defects.md): this phase does not compute its own
// clustering — it trusts the clusterTag groupings threaded through `contradictionClusters` above,
// which is the same reuse of Phase 2.5's coarse-domain apparatus PIPELINE.md:620 calls for. A
// caller that hands this phase one cluster per topicKey reproduces D3's fragmentation; this
// script has no way to detect that from inside a single cluster's agent dispatch, so it is a
// caller-side responsibility, named here rather than silently assumed.
//
// Concurrency: reuses CONCURRENCY_CAP, same as every other wave in this file — no new
// concurrency/parallelism constant (docs/wiki/distill-harvest-pipeline-defects.md D1).
// ---------------------------------------------------------------------------------------------
phase('contradiction-detection-3a')

const CONTRADICTION_SCHEMA = {
  type: 'object',
  required: ['cluster_tag', 'unresolvable_contradictions'],
  properties: {
    cluster_tag: { type: 'string' },
    topics_compared: { type: 'array', items: { type: 'string' } },
    unresolvable_contradictions: { type: 'number' },
    contradiction_refs: {
      type: 'array',
      items: {
        type: 'object',
        required: ['topic_a', 'topic_b', 'claim_id'],
        properties: {
          topic_a: { type: 'string' },
          topic_b: { type: 'string' },
          claim_id: { type: 'string' },
          topic_a_claim: { type: 'string' },
          topic_b_claim: { type: 'string' },
          why_unresolvable: { type: 'string' },
        },
      },
    },
    analysis: { type: 'string' },
  },
}

function resolveTopicWikiPath(topicKey) {
  const synthed = synthResults.find((r) => r.topic_key === topicKey)
  if (synthed) return synthed.wiki_path
  const matchingCluster = clusters.find((c) => c.topicKey === topicKey)
  const slug = slugifyTopic(topicKey)
  return (matchingCluster && matchingCluster.wikiPath) || WIKI_SLUGS[slug] || `${WIKI_DIRS[0]}/${slug}.md`
}

function topicPairsFor(topicKeys) {
  const pairs = []
  for (let i = 0; i < topicKeys.length; i++) {
    for (let j = i + 1; j < topicKeys.length; j++) {
      pairs.push([topicKeys[i], topicKeys[j]])
    }
  }
  return pairs
}

const contradictionBriefFor = (cluster) => {
  const topicKeys = cluster.topicKeys || []
  const pairs = topicPairsFor(topicKeys)
  const wikiPaths = topicKeys.map((t) => ({ topic: t, wiki_path: resolveTopicWikiPath(t) }))

  return COMMON + `

You are a Sonnet contradiction-detection agent (Phase 3a of the /distill harvest Workflow,
folded into this Workflow per PIPELINE.md § "Phase 3a: Contradiction Detection"). Compare the
Phase-2 synthesized wiki content for your assigned cluster and identify contradictions between
topics WITHIN this cluster only — cross-cluster contradictions are handled separately, not your
job.

Your assigned cluster: ${cluster.clusterTag}
Topics in this cluster and their wiki files (Read each one): ${JSON.stringify(wikiPaths)}
Topic pairs to compare: ${JSON.stringify(pairs)}

For each pair, read both wiki files and look for:
- Same system/component described with different behaviours
- Same configuration value stated differently
- Mutually exclusive design patterns both described as recommended
- A decision in one topic's file that contradicts a knowledge claim in another

Classify each contradiction found:
- **Resolvable** — temporal ordering settles it (a later-dated source/provenance wins). Do NOT
  report resolvable contradictions in contradiction_refs — resolve them yourself and move on.
- **Unresolvable** — same logical level, ambiguous dates, or genuinely conflicting authoritative
  claims. Only these go into contradiction_refs.

Set unresolvable_contradictions to the integer count of unresolvable contradictions found (0 if
none). For each one, append a contradiction_refs entry: topic_a, topic_b, a short lowercase
hyphenated claim_id slug unique within your return (e.g. "retry-timeout-value"), plus
topic_a_claim/topic_b_claim (what each file actually says) and why_unresolvable. Set
topics_compared to exactly ${JSON.stringify(topicKeys)}. Set cluster_tag to exactly
'${cluster.clusterTag}'. Put your full prose analysis (including resolved contradictions and
their resolution) in the analysis field.`
}

let contradictionResults = []
let contradictionStatus = 'unavailable'
if (CONTRADICTION_CLUSTERS.length > 0) {
  const multiTopicClusters = CONTRADICTION_CLUSTERS.filter((c) => (c.topicKeys || []).length >= 2)
  const singleTopicClusters = CONTRADICTION_CLUSTERS.filter((c) => (c.topicKeys || []).length < 2)

  const dispatchedResults = (await parallel(
    multiTopicClusters.map((cluster) => () =>
      agent(contradictionBriefFor(cluster), {
        schema: CONTRADICTION_SCHEMA,
        agentType: 'coordinator:executor',
        phase: 'contradiction-detection-3a',
        label: `3a-${slugifyTopic(cluster.clusterTag)}`,
        model: 'sonnet',
      })
    ),
    { concurrency: CONCURRENCY_CAP }
  )).filter(Boolean)

  // Single-topic cluster exemption (PIPELINE.md:622) — no within-cluster pairwise comparison is
  // possible with one topic, so no agent is dispatched; fold in a zero-contradiction result
  // directly rather than silently omitting the cluster from the manifest.
  const singleTopicResults = singleTopicClusters.map((cluster) => ({
    cluster_tag: cluster.clusterTag,
    topics_compared: cluster.topicKeys || [],
    unresolvable_contradictions: 0,
    contradiction_refs: [],
  }))

  contradictionResults = [...dispatchedResults, ...singleTopicResults]
  contradictionStatus = 'ran'

  const failedClusterTags = multiTopicClusters
    .map((c) => c.clusterTag)
    .filter((tag) => !dispatchedResults.some((r) => r.cluster_tag === tag))
  if (failedClusterTags.length > 0) {
    log(`contradiction-detection: ${failedClusterTags.length}/${multiTopicClusters.length} ` +
      `cluster(s) failed to return a result: ${failedClusterTags.join(', ')}`)
  }
  log(`contradiction-detection: ${contradictionResults.length}/${CONTRADICTION_CLUSTERS.length} ` +
    `cluster(s) reported (${singleTopicClusters.length} single-topic exempt) — ` +
    `${contradictionResults.reduce((n, r) => n + (r.unresolvable_contradictions || 0), 0)} ` +
    `unresolvable contradiction(s) total`)
} else {
  log('contradiction-detection: no contradictionClusters provided — phase reports unavailable, ' +
    'not zero-contradictions ("looked at nothing" != "found nothing")')
}

// Coordinator cross-cluster check (mechanical, post-3a) — PIPELINE.md:634-642. No subagent
// dispatch: a plain enumeration over every returned contradiction_refs entry, flagging any
// claim_id that recurs across ≥2 DIFFERENT clusters with a differing topic pair (the same claim
// being contradicted by different topics in different clusters — the blind spot no single
// per-cluster agent can see, since each only reads its own cluster's wiki files).
function findCrossClusterContradictions(results) {
  const firstSeenByClaimId = new Map()
  const candidates = []
  for (const result of results) {
    for (const ref of (result.contradiction_refs || [])) {
      const prior = firstSeenByClaimId.get(ref.claim_id)
      if (prior) {
        const differs = prior.cluster_tag !== result.cluster_tag &&
          (prior.topic_a !== ref.topic_a || prior.topic_b !== ref.topic_b)
        if (differs) {
          candidates.push({
            claim_id: ref.claim_id,
            clusters: [prior.cluster_tag, result.cluster_tag],
            topic_pairs: [[prior.topic_a, prior.topic_b], [ref.topic_a, ref.topic_b]],
          })
        }
      } else {
        firstSeenByClaimId.set(ref.claim_id, { cluster_tag: result.cluster_tag, topic_a: ref.topic_a, topic_b: ref.topic_b })
      }
    }
  }
  return candidates
}

const crossClusterCandidates = findCrossClusterContradictions(contradictionResults)
log(`contradiction-detection: cross-cluster check found ${crossClusterCandidates.length} ` +
  `candidate(s) across ${contradictionResults.length} cluster result(s)`)

const totalUnresolvableContradictions = contradictionResults
  .reduce((n, r) => n + (r.unresolvable_contradictions || 0), 0)

// Opus escalation (conditional, auto-dispatch) — PIPELINE.md:644-658. Fires ONLY when there is
// something to resolve; a zero/zero result proceeds with no escalation at all. Never promoted to
// an unconditional stage per this chunk's brief.
let opusEscalation = {
  triggered: false,
  cross_cluster_candidates: crossClusterCandidates,
}

if (totalUnresolvableContradictions > 0 || crossClusterCandidates.length > 0) {
  phase('contradiction-escalation')

  const flaggedRefs = contradictionResults.flatMap((r) =>
    (r.contradiction_refs || []).map((ref) => ({ ...ref, cluster_tag: r.cluster_tag }))
  )

  const ESCALATION_SCHEMA = {
    type: 'object',
    required: ['resolutions'],
    properties: {
      resolutions: {
        type: 'array',
        items: {
          type: 'object',
          required: ['claim_id', 'rationale'],
          properties: {
            claim_id: { type: 'string' },
            winner: { type: 'string' },
            synthesis: { type: 'string' },
            sources: { type: 'array', items: { type: 'string' } },
            unresolvable: { type: 'boolean' },
            rationale: { type: 'string' },
          },
        },
      },
    },
  }

  const escalationBrief = COMMON + `

You are an Opus contradiction-resolution agent (Phase 3-Esc, escalated only because Phase 3a
reported unresolvable contradictions and/or the cross-cluster check found candidates). This is a
NARROW escalation dispatch — resolve ONLY the flagged contradictions below, nothing else.

Flagged intra-cluster contradiction_refs (with their originating cluster_tag):
${JSON.stringify(flaggedRefs, null, 2)}

Cross-cluster contradiction candidates (the same claim_id contradicted differently across
clusters — PIPELINE.md's cross-cluster blind spot):
${JSON.stringify(crossClusterCandidates, null, 2)}

For each claim_id above, apply: temporal ordering (later-dated source wins), architectural
hierarchy (a decision record outranks an informal note), scope specificity (a narrower claim
overrides a broader one on the same topic). Return one resolutions[] entry per claim_id, each
citing EVERY source id involved — either \`winner\` (a single authoritative id) or \`sources\`
(≥2 ids, when a genuinely new synthesis is required — pair with \`synthesis\`), or
\`unresolvable: true\` with \`sources\` still listing every id if you cannot resolve it even with
this bounded context. \`rationale\` is required on every entry. Do NOT guess — an honest
unresolvable entry surfaces to the PM at Phase 4; a fabricated resolution does not.`

  const [opusResult] = (await parallel(
    [() => agent(escalationBrief, {
      schema: ESCALATION_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'contradiction-escalation',
      label: 'opus-3esc',
      model: 'opus',
    })],
    { concurrency: 1 }
  )).filter(Boolean)

  let fidelityResult = null
  if (opusResult) {
    const expectedClaimIds = [
      ...flaggedRefs.map((r) => r.claim_id),
      ...crossClusterCandidates.map((c) => c.claim_id),
    ]

    const FIDELITY_SCHEMA = {
      type: 'object',
      required: ['fidelity_verdict'],
      properties: {
        fidelity_verdict: { type: 'string', enum: ['PASS', 'FAIL'] },
        dropped_claim_ids: { type: 'array', items: { type: 'string' } },
        detail: { type: 'string' },
      },
    }

    const fidelityBrief = COMMON + `

You are a Sonnet fidelity-check agent (disk-first verification of the Phase 3-Esc Opus
contradiction-resolution output). You do NOT re-resolve anything — you only verify every flagged
claim_id was addressed with a cited source.

Expected claim_ids (every one MUST appear in the resolutions below, each with either \`winner\`
or a non-empty \`sources\` list, and \`rationale\` present): ${JSON.stringify(expectedClaimIds)}

Opus resolutions to verify: ${JSON.stringify(opusResult.resolutions || [], null, 2)}

Return fidelity_verdict: 'PASS' if every expected claim_id has a matching resolutions[] entry
carrying \`winner\` or a non-empty \`sources\` array plus \`rationale\`. Otherwise 'FAIL', with
dropped_claim_ids listing every expected claim_id missing a valid entry, and detail explaining
the first violation found.`

    const [fidelity] = (await parallel(
      [() => agent(fidelityBrief, {
        schema: FIDELITY_SCHEMA,
        agentType: 'coordinator:executor',
        phase: 'contradiction-escalation',
        label: 'opus-3esc-fidelity',
        model: 'sonnet',
      })],
      { concurrency: 1 }
    )).filter(Boolean)
    fidelityResult = fidelity || null

    if (fidelityResult && fidelityResult.fidelity_verdict === 'FAIL') {
      log(`contradiction-escalation: fidelity check FAILED — dropped claim_ids: ` +
        `${(fidelityResult.dropped_claim_ids || []).join(', ')}. ${fidelityResult.detail || ''}`)
    }
  } else {
    log('contradiction-escalation: Opus resolution agent failed to return a result — surfacing ' +
      'unresolved to Phase 4 PM gate per PIPELINE.md:658 rather than blocking the run.')
  }

  opusEscalation = {
    triggered: true,
    flagged_refs: flaggedRefs,
    cross_cluster_candidates: crossClusterCandidates,
    resolution: opusResult || null,
    fidelity_verdict: fidelityResult,
  }
}

const contradictionDetection = {
  clusters_processed: CONTRADICTION_CLUSTERS.length,
  results: contradictionResults,
  status: contradictionStatus,
  total_unresolvable_contradictions: totalUnresolvableContradictions,
  cross_cluster_candidates: crossClusterCandidates,
}

// ---------------------------------------------------------------------------------------------
// Phase 3b — Decision-record dedup (Sonnet, single), folded into this Workflow per
// docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md chunk C6b, replacing the
// hand-orchestrated Phase 3b (PIPELINE.md § "Phase 3b: Decision-Record Dedup",
// agent-prompts/phase-3b.md). Consumes C6a's in-memory resolved clusters/synth results directly
// — never re-reads Phase 2 scratch files from disk, the same in-memory-over-scratch-file
// substitution this Workflow already applies to Phase 2.5/3a. Runs after Phase 3a, the
// cross-cluster check, and the conditional Opus escalation above (structural by placement).
//
// CRITICAL FAILURE MODE (agent-prompts/phase-3b.md): an empty canonical DR set is always a
// pipeline error, never a valid outcome. Surfaced here as `failure`/`failure_detail` on the
// returned result rather than thrown — a single failed dedup pass this late in the run should
// not halt the whole Workflow (the same log-and-surface-to-Phase-4 handling this file already
// gives an Opus-escalation agent failure, never a throw).
// ---------------------------------------------------------------------------------------------
phase('phase-3b')

const DR_DEDUP_SCHEMA = {
  type: 'object',
  required: ['dr_dedup', 'failure'],
  properties: {
    dr_dedup: {
      type: 'array',
      items: {
        type: 'object',
        required: ['canonical_id', 'duplicate_ids', 'merge_rationale'],
        properties: {
          canonical_id: { type: 'string' },
          duplicate_ids: { type: 'array', items: { type: 'string' } },
          merge_rationale: { type: 'string' },
        },
      },
    },
    failure: { type: 'boolean' },
    failure_detail: { type: 'string' },
  },
}

// CREATE_DR dispositions are the load-bearing signal that Wave 2 actually drafted a decision
// record for a nugget (op enum includes CREATE_DR alongside ADD_SECTION/UPDATE_SECTION/
// REMOVE_SECTION/SKIP) — synth agents wrote those DRs DIRECTLY to docs/decisions/*.md as part of
// their additive write, the same direct-write contract wiki guides get; this Workflow performs
// no staged-apply step for either. judgment-mining new-entry proposals are a separate namespace
// (docs/wiki/codebase-judgment/, never docs/decisions/) and are passed to the dedup agent only
// as cross-reference context, never merged into a DR by this script.
const createDrDispositions = synthResults.flatMap((r) =>
  (r.dispositions || [])
    .filter((d) => d.op === 'CREATE_DR')
    .map((d) => ({ nugget_id: d.nugget_id, reason: d.reason || null, topic_key: r.topic_key, wiki_path: r.wiki_path }))
)
const judgmentDrCandidates = judgmentResults.filter((r) => r.action === 'new-entry')

let phase3b = { dr_dedup: [], failure: false, failure_detail: null, status: 'skipped' }
if (createDrDispositions.length === 0 && judgmentDrCandidates.length === 0) {
  phase3b = {
    dr_dedup: [],
    failure: true,
    failure_detail: 'Zero CREATE_DR dispositions across all synth results and zero new-entry ' +
      'judgment proposals — Phase 2 did not produce any decision-record-shaped content this run.',
    status: 'skipped-empty',
  }
  log(`phase-3b: SKIPPED (no dispatch) — ${phase3b.failure_detail}`)
} else {
  const drDedupBrief = COMMON + `

You are a Sonnet decision-record deduplication agent (Phase 3b of the /distill harvest
Workflow, folded into this Workflow per PIPELINE.md § "Phase 3b: Decision-Record Dedup").
Wave-2 synth agents wrote decision records DIRECTLY to docs/decisions/*.md as part of their
additive write (this Workflow performs no staged-apply step for DRs, same as wiki guides) — you
are not reading Phase 2 scratch files, you are reading the real DR files those agents just
wrote.

Run ID: ${RUN_ID}
CREATE_DR dispositions from this run's synth pass (nugget_id, topic, wiki_path each DR
originated from): ${JSON.stringify(createDrDispositions, null, 2)}
Judgment-mining new-entry proposals (DECISION-shaped content promoted to
docs/wiki/codebase-judgment/, a SEPARATE namespace from docs/decisions/ — cross-reference only
if genuinely the same underlying decision, never merge one into the other):
${JSON.stringify(judgmentDrCandidates, null, 2)}
${opusEscalation.triggered
      ? `Phase 3-Esc ran and resolved contradictions — its resolutions supersede any conflicting ` +
        `DR content: ${JSON.stringify(opusEscalation.resolution, null, 2)}`
      : 'Phase 3-Esc did not run this pass — no contradiction resolutions to integrate.'}

Read docs/decisions/*.md and find every DR file stamped with run_id: ${RUN_ID} in its
provenance (the DRs the CREATE_DR dispositions above just produced). Compare Problem + Decision
fields across all of them, and against any pre-existing DR one might duplicate: two DRs
describe the same decision if they address the same underlying choice, even if phrased
differently. Keep the one with more context/reasoning as canonical; the other becomes a
duplicate entry. Temporal ordering is the tiebreaker when reasoning quality is equivalent
(later-dated DR wins).

Return dr_dedup: one entry per canonical DR (canonical_id, duplicate_ids — [] if none,
merge_rationale — "" if none). Set failure: true ONLY if you find genuinely zero decision
records despite the CREATE_DR dispositions listed above (a real pipeline inconsistency, not a
normal outcome) and explain in failure_detail; otherwise failure: false. Do NOT delete or merge
files yourself — this is a reporting pass only; do NOT git commit.`

  const [drDedupResult] = (await parallel(
    [() => agent(drDedupBrief, {
      schema: DR_DEDUP_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'phase-3b',
      label: 'dr-dedup',
      model: 'sonnet',
    })],
    { concurrency: 1 }
  )).filter(Boolean)

  if (!drDedupResult) {
    phase3b = {
      dr_dedup: [],
      failure: true,
      failure_detail: 'Phase 3b dedup agent failed to return a result.',
      status: 'agent-failed',
    }
    log('phase-3b: dedup agent failed to return a result — surfacing to Phase 4 PM gate rather than halting the run.')
  } else {
    phase3b = { ...drDedupResult, status: drDedupResult.failure ? 'failed' : 'ran' }
    if (drDedupResult.failure) {
      log(`phase-3b: CRITICAL FAILURE MODE — ${drDedupResult.failure_detail || '(no detail given)'}`)
    } else {
      log(`phase-3b: ${drDedupResult.dr_dedup.length} canonical DR(s), ` +
        `${drDedupResult.dr_dedup.reduce((n, d) => n + (d.duplicate_ids || []).length, 0)} duplicate(s) merged`)
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Phase 3d — Deletion manifest (Sonnet, single), folded into this Workflow per
// docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md chunk C6b, replacing the
// hand-orchestrated Phase 3d (PIPELINE.md § "Phase 3d: Deletion Manifest",
// agent-prompts/phase-3d.md). Consumes this Workflow's own mechanically-computed
// `distillation_log_rows` (DISTILLED/EPHEMERAL/SKIP, § "Distillation-log rows" above) as its
// starting classification — never re-reads Phase 1/1.5/2 scratch files from disk, the same
// in-memory substitution 2.5/3a/3b already apply. The agent's job here is the part the
// mechanical pass above cannot do: resolving DISTILLED/EPHEMERAL/SKIP into the final
// DELETE/SEND_BACK/BLOCKED/PRESERVE disposition by reading real external state (active
// handoffs, open commitments, research/NotebookLM PRESERVE classes) neither this script nor
// distillation_log_rows has visibility into.
//
// Suppressed by join-integrity failure (disposalSuppressed above) — the same suppression the
// mechanical distillation-log-rows pass is already subject to; a `failed` join verdict means the
// source->nugget join is unsafe to trust for disposal purposes, so this phase does not dispatch
// at all in that case (never a partial/best-effort manifest built on an untrustworthy join).
//
// Negative-spec (this chunk's own exit criterion): either an artifact was harvested or it
// wasn't — the brief below refuses a disposition that records an un-harvested artifact as
// settled. A SKIP row (batch never scanned) resolves to SEND_BACK, never DELETE and never a
// bare "retain".
// ---------------------------------------------------------------------------------------------
phase('phase-3d')

const DELETION_MANIFEST_SCHEMA = {
  type: 'object',
  required: ['deletions'],
  properties: {
    deletions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['artifact_path', 'disposition', 'reason'],
        properties: {
          artifact_path: { type: 'string' },
          disposition: { type: 'string', enum: ['DELETE', 'SEND_BACK', 'BLOCKED', 'PRESERVE'] },
          reason: { type: 'string' },
          source_nugget_ids: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

let phase3d = { deletions: [], status: 'suppressed' }
if (disposalSuppressed) {
  log(`phase-3d: SUPPRESSED (no dispatch) — ${disposalSuppressedReason}`)
} else if (distillationLogRows.length === 0) {
  phase3d = { deletions: [], status: 'skipped-empty' }
  log('phase-3d: SKIPPED (no dispatch) — zero distillation_log_rows to classify.')
} else {
  const deletionManifestBrief = COMMON + `

You are a Sonnet deletion-manifest agent (Phase 3d of the /distill harvest Workflow, folded
into this Workflow per PIPELINE.md § "Phase 3d: Deletion Manifest"). This Workflow already
mechanically classified every source artifact as DISTILLED (nuggets carried into a non-SKIP
disposition), EPHEMERAL (scanned, nothing carried forward), or SKIP (batch never scanned) — see
distillation_log_rows below. Your job is resolving each row into its FINAL disposition: DELETE,
SEND_BACK, BLOCKED, or PRESERVE.

Run ID: ${RUN_ID}
distillation_log_rows (path, mechanical disposition, fate prose):
${JSON.stringify(distillationLogRows, null, 2)}
${opusEscalation.triggered
      ? `Phase 3-Esc ran — artifacts whose contradictions were resolved there are fully extracted: ` +
        `${JSON.stringify(opusEscalation.resolution, null, 2)}`
      : 'Phase 3-Esc did not run this pass.'}

Resolve each row:
- **DISTILLED -> DELETE** — all non-ephemeral knowledge extracted; no active references; not
  otherwise PRESERVE/BLOCKED below.
- **EPHEMERAL -> DELETE** — nothing to extract; not otherwise PRESERVE/BLOCKED below.
- **SKIP -> SEND_BACK** — this artifact's batch never scanned; the run's own incompleteness,
  never treated as settled. Name "batch never scanned" as the reason.
- **SEND_BACK** (override DISTILLED/EPHEMERAL) — delete-guard failed (no docs/wiki or
  docs/decisions citation found for this artifact's extracted knowledge), or unresolved
  synthesis ambiguity left extraction incomplete. Name what is missing.
- **BLOCKED** (override DISTILLED/EPHEMERAL) — a real EXTERNAL condition, not run
  incompleteness: actively referenced by a live state/handoffs/*.md file or in-progress task
  (Read state/handoffs/ to check — name the referencing file); a linked
  state/cross-repo-commitments/ entry is status: open; an accepted/partial memo has an
  absent/unverifiable realized_by; or the artifact is an in-progress/unapproved design spec.
- **PRESERVE** (overrides everything) — research outputs (docs/research/, ~/docs/research/,
  Pipeline A/B/C/D outputs), NotebookLM outputs, Pipeline C outputs (manifest_version: files).
  Never DELETE these regardless of extraction status.
- **archive/handoffs/** paths are NEVER eligible for any disposition — omit any such path from
  the manifest entirely if one appears in the rows above (they are not a distillation cohort).

Either an artifact was harvested or it wasn't — do NOT emit a disposition that records an
un-harvested artifact as settled. An artifact whose knowledge is not fully extracted is
SEND_BACK or BLOCKED, never DELETE and never a bare "retain".

For each artifact_path, include reason (explicit — name the missing citation, the blocking
reference, or the extracted nugget ids) and source_nugget_ids (nugget IDs actually cited in
this row's mechanical disposition — [] for SEND_BACK/BLOCKED/PRESERVE). Every row above must
appear exactly once in your returned deletions[] (minus any archive/handoffs/ rows, which you
omit per the rule above). Do NOT git commit — this is a reporting pass; Phase 4 (PM gate) and
Phase 5 (apply) are downstream of this Workflow.`

  const [deletionManifestResult] = (await parallel(
    [() => agent(deletionManifestBrief, {
      schema: DELETION_MANIFEST_SCHEMA,
      agentType: 'coordinator:executor',
      phase: 'phase-3d',
      label: 'deletion-manifest',
      model: 'sonnet',
    })],
    { concurrency: 1 }
  )).filter(Boolean)

  if (!deletionManifestResult) {
    phase3d = { deletions: [], status: 'agent-failed' }
    log('phase-3d: deletion-manifest agent failed to return a result — surfacing to Phase 4 PM gate rather than halting the run.')
  } else {
    phase3d = { ...deletionManifestResult, status: 'ran' }
    const dispositionCounts = phase3d.deletions.reduce((acc, d) => {
      acc[d.disposition] = (acc[d.disposition] || 0) + 1
      return acc
    }, {})
    log(`phase-3d: ${phase3d.deletions.length} row(s) — ` +
      Object.entries(dispositionCounts).map(([k, v]) => `${k}: ${v}`).join(', '))
  }
}

// Cross-Repo Archive Specialist Branch merge — pre-converted crossRepoDispositions rows are
// spliced into the Phase 3d deletion manifest here. Absent/empty input is a clean no-op, logged
// the same way as the script's other covered/total lines rather than silently capped.
// Review: code-reviewer (P1) — these rows originate from the Cross-Repo Archive Specialist
// Branch, not from the Phase 3d deletion-manifest agent, so they must not be dropped merely
// because phase3d itself is 'suppressed'/'skipped-empty'/'agent-failed'. Merged unconditionally;
// when phase3d never actually ran, `cross_repo_merged_without_manifest` flags the manifest as
// cross-repo-only rather than silently returning an empty deletions list.
const crossRepoPaths = new Set(CROSS_REPO_DISPOSITIONS.map((r) => r.artifact_path))
if (CROSS_REPO_DISPOSITIONS.length > 0) {
  const mergedWithoutManifest = phase3d.status !== 'ran'
  phase3d = {
    ...phase3d,
    deletions: [...(phase3d.deletions || []), ...CROSS_REPO_DISPOSITIONS],
    ...(mergedWithoutManifest ? { cross_repo_merged_without_manifest: true } : {}),
  }
  log(`phase-3d: merged ${CROSS_REPO_DISPOSITIONS.length} cross-repo disposition row(s) into the ` +
    `deletion manifest (${phase3d.deletions.length} row(s) total after merge)` +
    (mergedWithoutManifest
      ? ` — phase-3d status was '${phase3d.status}', not 'ran'; merged anyway (manifest is cross-repo-only).`
      : '.'))
} else {
  log('phase-3d: no cross-repo disposition rows supplied — no-op.')
}

// ---------------------------------------------------------------------------------------------
// Artifact-level send_back re-entry — findCoverageGaps' shape lifted from nugget level to
// artifact level (docs/plans/2026-08-27-distill-dispositions-and-tail-rollup.md chunk C4,
// RATIFIED 2026-08-27, "build it, no defer"). Phase 3d above resolves DISTILLED/EPHEMERAL/SKIP
// into DELETE/SEND_BACK/BLOCKED/PRESERVE, but a SEND_BACK row is Phase 3d saying "not settled
// yet" — left as-is, it is the exact un-harvested-recorded-as-settled defect this chunk exists
// to close (see the PM's own words in the plan Problem section: "Either they were harvested or
// they weren't."). This gate re-dispatches one re-harvest agent per SEND_BACK cluster (grouped
// by originating batch, the natural unit here since an artifact belongs to exactly one batch —
// the artifact-level analogue of the nugget gate's one-cluster-one-topic grouping), re-evaluates
// the delete guards on return, and — mirroring the nugget gate's three required properties
// (PIPELINE.md / this chunk's brief) — logs covered/total every round unconditionally, never
// halts the run on a re-harvest agent failure, and is bounded: an artifact that survives
// SEND_BACK_REENTRY_CAP rounds becomes BLOCKED with the cap named as the reason, never a silent
// SEND_BACK carried to the next run.
// ---------------------------------------------------------------------------------------------
phase('artifact-reentry')
const SEND_BACK_REENTRY_CAP = 2

const REENTRY_SCHEMA = {
  type: 'object',
  required: ['batch_id', 'resolutions'],
  properties: {
    batch_id: { type: 'string' },
    resolutions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['artifact_path', 'disposition', 'reason'],
        properties: {
          artifact_path: { type: 'string' },
          disposition: { type: 'string', enum: ['DELETE', 'SEND_BACK', 'BLOCKED'] },
          reason: { type: 'string' },
          source_nugget_ids: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const pathToBatchId = new Map()
for (const b of BATCHES) {
  for (const f of b.files) pathToBatchId.set(f, b.batchId)
}

let reentryRoundsRun = 0
let currentDeletions = phase3d.deletions || []
const reentryLog = []

// Review: code-reviewer (F3) / EM direction — a cross-repo-originated row never enters this
// repo's re-entry loop, regardless of phase3d.status: the loop's whole action is "re-open this
// file and integrate it into docs/wiki," a same-repo harvest, and a cross-repo artifact is not
// this run's to re-harvest. Resolved to BLOCKED here, before the loop, naming the actual external
// condition — never the reentry cap, since it never ran a round. One rule, not one keyed on
// phase3d.status (that dependency was the F1/F3 defect: same row, same repo, different terminus
// depending on whether the local Phase 3d agent happened to run).
const crossRepoBlockedPaths = []
currentDeletions = currentDeletions.map((d) => {
  if (d.disposition !== 'SEND_BACK' || !crossRepoPaths.has(d.artifact_path)) return d
  crossRepoBlockedPaths.push(d.artifact_path)
  return {
    ...d,
    disposition: 'BLOCKED',
    reason: `cross-repo artifact — belongs to another repo; this run cannot harvest it ` +
      `(original reason: ${d.reason})`,
  }
})
if (crossRepoBlockedPaths.length > 0) {
  log(`artifact re-entry: ${crossRepoBlockedPaths.length} cross-repo SEND_BACK row(s) resolved to ` +
    `BLOCKED without entering the local re-entry loop: ${crossRepoBlockedPaths.join(', ')}`)
}

if (phase3d.status === 'ran') {
  while (reentryRoundsRun < SEND_BACK_REENTRY_CAP) {
    const sendBackRows = currentDeletions.filter((d) => d.disposition === 'SEND_BACK')
    const totalRows = currentDeletions.length
    log(`artifact re-entry round ${reentryRoundsRun + 1}: ${totalRows - sendBackRows.length}/${totalRows} ` +
      `artifact(s) settled (${sendBackRows.length} SEND_BACK remaining)`)
    if (sendBackRows.length === 0) break

    const byBatch = new Map()
    for (const row of sendBackRows) {
      const batchId = pathToBatchId.get(row.artifact_path) || '(unmapped)'
      if (!byBatch.has(batchId)) byBatch.set(batchId, [])
      byBatch.get(batchId).push(row)
    }

    const reentryBriefFor = (batchId, rows) => COMMON + `

You are a Sonnet re-harvest agent (artifact-level send_back re-entry, round ${reentryRoundsRun + 1}
of the /distill harvest Workflow). A prior Phase 3d pass marked the following artifact(s) from
batch ${batchId} as SEND_BACK — not yet harvested, not settled:
${JSON.stringify(rows, null, 2)}

For each artifact_path, re-open the file and complete the extraction Phase 3d found missing (the
reason field above names what was missing — typically no docs/wiki or docs/decisions citation for
the artifact's knowledge, or unresolved synthesis ambiguity). Extract and additively integrate any
remaining knowledge into the relevant docs/wiki/<topic>.md guide (create one if none exists), or a
docs/decisions/ record for decision-shaped content, direct write with Write/Edit. Stamp
PROVENANCE the same two ways as the main synth pass (spec-backlink comment + YAML frontmatter,
docs/wiki/rag-bait-conventions.md).

Then resolve EACH artifact_path to exactly one of:
- **DELETE** — extraction now complete, citation exists, no active reference blocks it.
- **BLOCKED** — a real EXTERNAL condition prevents harvest (active handoff/commitment reference,
  in-progress spec) — name it.
- **SEND_BACK** — still genuinely incomplete after this attempt (name what remains missing). Use
  this ONLY if real work remains; do not default to it.

Either the artifact was harvested or it wasn't — do not resolve to DELETE without a real
docs/wiki or docs/decisions citation for its knowledge. Return one resolutions[] entry per
artifact_path above, with reason and source_nugget_ids ([] for BLOCKED/SEND_BACK). Do NOT git
commit — the EM commits from the returned manifest after this run completes.`

    const reentryResults = (await parallel(
      [...byBatch.entries()].map(([batchId, rows]) => () =>
        agent(reentryBriefFor(batchId, rows), {
          schema: REENTRY_SCHEMA,
          agentType: 'coordinator:executor',
          phase: 'artifact-reentry',
          label: `reentry-r${reentryRoundsRun + 1}-${batchId}`,
          model: 'sonnet',
        })
      ),
      { concurrency: CONCURRENCY_CAP }
    )).filter(Boolean)

    const failedReentryBatchIds = [...byBatch.keys()]
      .filter((batchId) => !reentryResults.some((r) => r.batch_id === batchId))
    if (failedReentryBatchIds.length > 0) {
      log(`artifact re-entry round ${reentryRoundsRun + 1}: re-harvest agent failure for ` +
        `batch(es) ${failedReentryBatchIds.join(', ')} — caught, not run-blocking; ` +
        `artifact(s) remain SEND_BACK this round`)
    }

    const resolutionByPath = new Map()
    for (const r of reentryResults) {
      for (const res of r.resolutions || []) resolutionByPath.set(res.artifact_path, res)
    }
    currentDeletions = currentDeletions.map((d) => resolutionByPath.get(d.artifact_path) || d)
    reentryLog.push({
      round: reentryRoundsRun + 1,
      send_back_in: sendBackRows.length,
      resolved: sendBackRows.filter((d) => resolutionByPath.has(d.artifact_path)).length,
      failed_batch_ids: failedReentryBatchIds,
    })
    reentryRoundsRun++
  }
}

// Bounded re-entry — an artifact still SEND_BACK after the cap becomes BLOCKED with the cap
// named as the reason, never a silent SEND_BACK carried to the next run (this chunk's own
// completion condition, echoed in PIPELINE.md).
const cappedArtifactPaths = []
currentDeletions = currentDeletions.map((d) => {
  if (d.disposition !== 'SEND_BACK') return d
  cappedArtifactPaths.push(d.artifact_path)
  return {
    ...d,
    disposition: 'BLOCKED',
    reason: `un-harvestable after ${SEND_BACK_REENTRY_CAP} send_back re-entry round(s) — ` +
      `original reason: ${d.reason}`,
  }
})
if (cappedArtifactPaths.length > 0) {
  log(`artifact re-entry: ${cappedArtifactPaths.length} artifact(s) capped to BLOCKED after ` +
    `${SEND_BACK_REENTRY_CAP} round(s): ${cappedArtifactPaths.join(', ')}`)
}
phase3d = { ...phase3d, deletions: currentDeletions }

const artifactReentry = {
  rounds_run: reentryRoundsRun,
  cap: SEND_BACK_REENTRY_CAP,
  rounds: reentryLog,
  // Review: code-reviewer (P2) — `final_send_back_count` was dead code: computed after the
  // cap-conversion above already flips every remaining SEND_BACK to BLOCKED, so it could never
  // read non-zero. `capped_to_blocked.length` already carries the equivalent signal.
  capped_to_blocked: cappedArtifactPaths,
}

return {
  done: true,
  run_id: RUN_ID,
  concurrency_cap: CONCURRENCY_CAP,
  batches_scanned: scanResults.length,
  failed_batch_ids: failedBatchIds,
  empty_content_batch_ids: emptyContentBatchIds,
  malformed_tag_batch_ids: malformedTagBatchIds,
  malformed_tag_nugget_count: malformedTagNuggetCount,
  join_integrity: joinIntegrity,
  // C4 — misc_overflow (the retired coarsen/fold/cap/misc-bucket telemetry) is replaced by these
  // two counts: every homeless cluster becomes its own `new` file unconditionally now that
  // curation decides per-tag, upstream of clustering, which tags survive at all (C2/C3).
  consolidation: { homed: homedCount, new: newCount },
  // C3/AC12 — count of tags whose claude-klabauter verdict was overridden to `keep` because the tag
  // already has a wiki home (exact or fuzzy). C3/AC3 — dropped tags survive here as data (tag,
  // nugget id, claude-klabauter's drop reason) so the distillation log can file them EPHEMERAL-with-reason
  // rather than letting them disappear; C3b renders this, C3 only guarantees it is complete.
  homing_override_count: homingOverrideCount,
  dropped_tags: droppedTags,
  drop_summary: dropSummary,
  // Passthrough of claude-klabauter's curated-payload result-level fields (see CURATED_THRESHOLD_APPLIED
  // etc. above) — surfaced as received, never recomputed, never overriding
  // `recommended_keep_threshold` (invocation A's own recommendation, returned separately above).
  threshold_applied: CURATED_THRESHOLD_APPLIED,
  threshold_auto: CURATED_THRESHOLD_AUTO,
  nugget_drop_share: CURATED_NUGGET_DROP_SHARE,
  ...(disposalSuppressed ? { disposal_suppressed: true, disposal_suppressed_reason: disposalSuppressedReason } : {}),
  // Finding-4 fix: an agent-failed Phase 3d also returns deletions: [] — without an equivalent
  // explicit flag, that is indistinguishable from disposalSuppressed's "nothing to delete" for a
  // downstream Phase-4 reader. Same shape as the disposal_suppressed pair above, distinct reason.
  ...(phase3d.status === 'agent-failed'
    ? { manifest_incomplete: true, manifest_incomplete_reason: 'phase-3d deletion-manifest agent failed to return a result' }
    : {}),
  clusters_synthesized: synthResults.length,
  scan_results: scanResults,
  synth_results: synthResults,
  distillation_log_rows: distillationLogRows,
  fate_prose_enforcement: fateProseEnforcement,
  provenance_completeness: provenanceCompleteness,
  coverage: {
    total_assigned_nuggets: totalAssignedNuggets,
    total_covered_nuggets: totalAssignedNuggets - remainingGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0),
    gap_clusters: coverageGaps.map((g) => g.topicKey),
    failed_gap_topic_keys: failedGapTopicKeys,
    unresolved_gap_clusters: remainingGaps.map((g) => g.topicKey),
  },
  judgment_mining: judgmentMining,
  contradiction_detection: contradictionDetection,
  opus_escalation: opusEscalation,
  phase_3b_dr_dedup: phase3b,
  phase_3d_deletion_manifest: phase3d,
  artifact_reentry: artifactReentry,
}
