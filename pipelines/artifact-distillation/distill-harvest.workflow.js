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
 * Doctrine: coordinator/docs/wiki/em-operating-model/workflow-orchestration.md (vehicle-choice, chunking,
 * commit-discipline, model-selection rules — this script follows all of them).
 *
 * Negative-spec: the two waves are NEVER merged into one resumable unit — merging re-pays the
 * expensive Wave-1 scan on every Wave-2 wipe (see plan Anti-scope: "Do NOT collapse the two
 * waves into one resumable unit"). Wave-2 agents do NOT commit — per
 * workflow-orchestration.md § Commit discipline inside workflows, the EM commits from each
 * agent's returned manifest after the run. Wave-2 agents are additive+provenance-only; the
 * deletion gate is the delete guards plus the Phase 3d provenance citation, not a PM wait. Synth output is
 * staged under state/scratch/artifact-distillation/<runId>/staged/ and moved into docs/wiki/ by
 * one atomic promote script call (bin/distill-promote-staged.py) after every return validates.
 */

export const meta = {
  name: 'distill-harvest',
  description: '/distill knowledge harvest: Haiku scan wave (journaled) -> JS cluster -> Sonnet one-file-per-topic synth wave (direct write)',
  phases: [
    { title: 'load', detail: 'no agent: args.prepared (the inline payload `distill_mechanical.py prepare` writes) supplies batches, wikiSlugs, counts and optional curated verdicts; declared counts are asserted against what arrived' },
    { title: 'plan-triage', detail: 'conditional (fires only when a docs/plans or archive plan sits in the files to scan: with args.prepared.clusters, only the residue prepare did not classify): one Haiku coordinator:distill-writer reads the run logs only and drops every probably_not plan before the scan wave' },
    { title: 'scan', detail: 'with args.prepared.clusters: no agent for a file prepare classified; parallel Haiku xN over the residue files only (no Work Completed / Decisions / Systems bullets), whose nuggets return as residue_scan for `prepare --nuggets`; without clusters (invocation A): xN over every batch (schema-forced, journaled; a dead or zero-nugget batch is scanned once more)' },
    { title: 'homing', detail: 'skipped with args.prepared.clusters (prepare homed them and cut the synth payloads against that home); otherwise a cluster whose cited records one page holds (args.prepared.pageFacts, optional) homes there with no call; otherwise ONE batched Haiku meaning-match call over the homeless clusters that share a stem with an existing page (no candidate, no call); uncited KNOWLEDGE-only clusters are appended to the nearest page as one gotcha' },
    { title: 'candidates', detail: 'no agent: candidate_restatements per topic come from args.prepared.candidates (the driver ran bin/distill-candidates-batch.py); a topic with no record degrades to an empty candidate list and is logged' },
    { title: 'source-hash', detail: 'no agent: args.prepared.sourceHashes (the driver ran bin/distill-promote-staged.py check) decides which topics are skipped; no stored hash is never skipped' },
    { title: 'synth', detail: 'at most 3 single-turn no-tool coordinator:distill-synth calls, one per args.prepared.synth.payloads entry (curated nuggets plus page outline inline, no file read); each returns per-topic ops {section_heading, action, markdown, cites} and decision_records under args.prepared.synth.schema' },
    { title: 'coverage-gate', detail: 'no agent: in-process report of nugget ids no landed op or record cites, DECISION nuggets folded into a page, and topics without a synth entry (deferred topics ride the next run); a nugget left uncovered keeps its artifact SKIP' },
    { title: 'promote', detail: 'no agent: the run returns phase_reached promote-ready with a promote_manifest carrying the raw synth_results; the EM runs `distill_mechanical.py finalize` (cite-checked splice, decision records minted, atomic swap with rollback, source hashes stored) and re-invokes with args.promoted and args.spliceReport to continue' },
    { title: 'judgment-mining-2-5', detail: 'parallel Sonnet xM (one per topic-cluster, folded-in Phase 2.5): mines live reviewer sidecars for cross-spec convergence, emits judgment-proposals (schema-forced) for Phase 3b review and wiki promotion into docs/wiki/codebase-judgment/ — read-only orchestrator boundary, no nested sub-agents; runs only once Phase 2 and the Coverage Gate above are fully complete' },
    { title: 'contradiction-detection-3a', detail: 'parallel Sonnet xM (one per cluster, folded-in Phase 3a): reuses Phase 2.5\'s clusterTag grouping of Phase-2 topics to compare synthesized wiki content within each cluster for contradictions (schema-forced), plus an in-process mechanical cross-cluster contradiction check (no subagent dispatch) over every cluster\'s returned contradiction_refs' },
    { title: 'contradiction-escalation', detail: 'conditional (fires only when any cluster reports unresolvable_contradictions > 0 or the cross-cluster check finds a candidate): single Opus agent resolves the flagged contradictions, followed by a single Sonnet fidelity-check agent verifying every flagged source id was cited — never an unconditional stage' },
    { title: 'phase-3b', detail: 'no agent: decision-record dedup is finalize\'s title/slug match against args.prepared.drIndex (a matching record is not minted and reads DR-EXISTS); this phase reports the CREATE_DR targets and DR-EXISTS skips into phase_3b_dr_dedup and dr_minting, and a run with zero DECISION nuggets is not a failure' },
    { title: 'phase-3d', detail: 'single Sonnet agent (folded-in Phase 3d): resolves this Workflow\'s own mechanically-computed distillation_log_rows (DISTILLED/EPHEMERAL/SKIP) into the final DELETE/SEND_BACK/BLOCKED/PRESERVE deletion manifest — suppressed (no dispatch) when join_integrity verdict is failed, same suppression the mechanical pass is already subject to' },
    { title: 'citation-repoint', detail: 'Sonnet probe runs distill-delete-guard over DISTILLED DELETE/BLOCKED rows; rows blocked only by docs/ or tasks/ citations get an apply agent that repoints the citations at the absorbing wiki page and re-runs the guard' },
    { title: 'artifact-reentry', detail: 'off the default path: runs only with args.reentry true; otherwise every SEND_BACK artifact resolves BLOCKED naming that. Enabled, one tool-less distill-synth call per synth payload holding a SEND_BACK artifact nuggets return ops and decision records; they come back as `reentry_manifest` (promote-manifest shape) for `distill_mechanical.py finalize`, the only page writer. No re-entry row resolves DELETE in-run; bounded to SEND_BACK_REENTRY_CAP rounds, a call failure is caught and logged (never run-blocking), and any artifact still SEND_BACK after the cap becomes BLOCKED with the cap named as the reason' },
  ],
}


// `args` arrives as a JSON string even when the caller passes a JSON array/object -- guard
// unconditionally.
const INPUT = typeof args === 'string' ? JSON.parse(args) : args

// Expected INPUT shape:
// {
//   runId: 'YYYY-MM-DD-HHhMM',
//   repoRoot: '/absolute/path/to/repo',
//   batches: [ { batchId: 'b1', description: '...', files: ['path1', ...], formatHints: { ... } }, ... ],
//   batch_count: <integer>, total_file_count: <integer>,  // declared counts; asserted against the received table
//   wikiDirs:  ['docs/wiki', 'coordinator/docs/wiki'],   // ordered; [0] is the default/primary NEW-file home.
//   wikiSlugs: { '<slug>': '<repo-relative-path>', ... }, // flat index: slugified filename-stem -> existing file
//                                                          // path, union across every dir in wikiDirs.
//   judgmentClusters / contradictionClusters / crossRepoDispositions: [ ... ] (optional) with
//   judgmentClusterCount / contradictionClusterCount / crossRepoDispositionCount: <integer>,
//   minConvergence: <integer>  // optional; each list is checked against its count
//   resumeFromRunId: '<prior-run-id>' | null,
//   prepared: { ... } | undefined,  // see § Input modes below
//   promoted: ['<target path>', ...] | undefined,  // finalize's promoted list; set on the post-promote re-invocation
// }
//
// Workflow scripts have no filesystem or exec access, so nothing mechanical runs in here: the
// bookkeeping around the judgment phases is `distill_mechanical.py` (prepare before, finalize
// after). This script reads the driver's output as inline JSON and spawns an agent only at a
// judgment site, each marked `judgment-keeper` below.
//
// Input modes, in precedence order (highest wins):
//   1. args.prepared — the `prepared.json` `distill_mechanical.py prepare` wrote, passed inline:
//      batches, wikiSlugs, declared counts, wikiDirs, optional judgment/contradiction/cross-repo
//      lists, `curated` (the saved distill.curate_clusters return), `sourceHashes` and
//      `candidates` keyed by topic. Fields present in it win over the same field in `args`; fields
//      it omits fall back to `args`. Its declared counts are asserted against what arrived.
//   2. args-passed input — the caller passes the full INPUT JSON inline, including `batches`.
//   3. embedded INPUT default — a forked copy of this script with a literal `const INPUT = {...}`
//      still runs unchanged.
// args.inputFile is refused: pass the prepare output as args.prepared.
const RAW_ARGS_INPUT = INPUT
// Pure: the `load_stats` block. Loading spawns no agent, so `agents` is always 0.
// prepare packs the slug->path index by parent dir to fit the launch under the Workflow script cap:
// `{dir: ['slug' | 'slug=<basename>']}`. Mirror of distill_mechanical.unpack_wiki_slugs.
function unpackWikiSlugs(packed) {
  const slugs = {}
  for (const [parent, entries] of Object.entries(packed || {})) {
    for (const entry of entries) {
      const eq = entry.indexOf('=')
      const slug = eq < 0 ? entry : entry.slice(0, eq)
      const base = eq < 0 ? `${slug}.md` : entry.slice(eq + 1)
      slugs[slug] = parent ? `${parent}/${base}` : base
    }
  }
  return slugs
}

function buildLoadStats(batches, wikiSlugs) {
  const list = Array.isArray(batches) ? batches : []
  return {
    agents: 0,
    batch_count: list.length,
    total_file_count: list.reduce((n, b) => n + ((b && b.files) ? b.files.length : 0), 0),
    wikiSlugCount: wikiSlugs ? Object.keys(wikiSlugs).length : 0,
  }
}

// Pure: compares each received cluster list to every declared count channel. `lists` maps a list
// name to the received array (or undefined); `declared` is `{args: {<name>: count}, file:
// {<name>: count}}`. Returns a halt object or null.
function assertRelayedListCounts(lists, declared, relayed) {
  const halt = (detail) => ({ phase_reached: 'load', halted: 'input-count-mismatch', detail })
  for (const name of Object.keys(lists)) {
    const received = Array.isArray(lists[name]) ? lists[name].length : 0
    const present = []
    for (const channel of ['args', 'file']) {
      const count = (declared[channel] || {})[name]
      if (count !== undefined) present.push([channel, count])
    }
    for (const [channel, count] of present) {
      if (!Number.isInteger(count)) {
        return halt(`distill-harvest: ${channel} channel count for ${name} is not an integer (${JSON.stringify(count)})`)
      }
      if (count !== received) {
        return halt(`distill-harvest: ${channel} declares ${name} count=${count} but received ${received} entr${received === 1 ? 'y' : 'ies'}`)
      }
    }
    if (relayed && received > 0 && present.length === 0) {
      return halt(`distill-harvest: relayed ${name} carries ${received} entr${received === 1 ? 'y' : 'ies'} but no count in the file or args`)
    }
  }
  return null
}

// A list channel is "supplied" when it is an array, however short: `[]` is a real, count-0 list
// (truthiness would treat it as present everywhere else and still skip this carve-out).
function listSupplied(...channels) {
  return channels.some((c) => Array.isArray(c))
}

// Pure: a declared contradictionClusterCount above zero with no list in the input, args or
// prepared.curated names the missing curated channel instead of a bare count mismatch.
function curatedMissingHalt(prepared, rawArgs, loadedInput) {
  const count = rawArgs && rawArgs.contradictionClusterCount
  if (!Number.isInteger(count) || count <= 0) return null
  if (prepared && prepared.curated) return null
  if (listSupplied(loadedInput && loadedInput.contradictionClusters, rawArgs.contradictionClusters)) return null
  return {
    phase_reached: 'load',
    halted: 'curated-missing',
    detail: `distill-harvest: args declares contradictionClusterCount=${count} but no contradictionClusters list and no args.prepared.curated arrived — ` +
      're-run distill_mechanical.py prepare with --verdicts <the saved distill.curate_clusters return> and launch with the resulting prepared.json',
  }
}

// Pure: turns the op's verdict list into the tag-keyed map the clustering consumes. Throws naming
// the tag on a duplicate or a missing `tag`.
function curatedMapFromVerdicts(verdicts) {
  const map = {}
  for (const entry of verdicts) {
    if (!entry || typeof entry.tag !== 'string' || entry.tag === '') {
      throw new Error(`curatedMapFromVerdicts: verdict entry without a tag: ${JSON.stringify(entry)}`)
    }
    if (Object.prototype.hasOwnProperty.call(map, entry.tag)) {
      throw new Error(`curatedMapFromVerdicts: duplicate verdict for tag '${entry.tag}'`)
    }
    map[entry.tag] = entry
  }
  return map
}

// Pure: compares the received batch table to every declared count channel. `declared.args` is the
// pair the launcher passed; `declared.file` is the pair the load agent returned. `relayed` is true
// when the input came through the load agent. Returns a halt object or null.
function assertRelayedCounts(batches, declared, relayed) {
  const halt = (detail) => ({ phase_reached: 'load', halted: 'input-count-mismatch', detail })
  const receivedBatches = batches.length
  const receivedFiles = batches.reduce((n, b) => n + ((b && b.files) ? b.files.length : 0), 0)
  const present = []
  for (const name of ['args', 'file']) {
    const ch = declared[name]
    if (ch.batch_count !== undefined || ch.total_file_count !== undefined) present.push([name, ch])
  }
  if (present.length === 0) {
    return relayed
      ? halt('distill-harvest: relayed input carries no batch_count/total_file_count — the file is not a ' +
          'distill.workflow_input payload and no counts were passed in args')
      : null
  }
  for (const [name, ch] of present) {
    for (const field of ['batch_count', 'total_file_count']) {
      if (!Number.isInteger(ch[field])) {
        return halt(`distill-harvest: ${name} channel field ${field} is absent or not an integer (${JSON.stringify(ch[field])})`)
      }
    }
  }
  for (const [name, ch] of present) {
    if (ch.batch_count !== receivedBatches) {
      return halt(`distill-harvest: ${name} declares batch_count=${ch.batch_count} but received ${receivedBatches} batch(es)`)
    }
    if (ch.total_file_count !== receivedFiles) {
      return halt(`distill-harvest: ${name} declares total_file_count=${ch.total_file_count} but received ${receivedFiles} file(s)`)
    }
  }
  return null
}

// Concurrency cap: min(16, cores-2) per the shared Workflow-resume primitive (distill-harvest
// lane). This is NOT the survey-analyst-fanout cap (LOW ~4 + ramp) — the two pipelines have
// different burst-arrival-rate risk profiles; do not conflate the two caps.
// NOTE: workflow scripts have NO Node API access — `import('node:os')` throws
// "import() is not available in workflow scripts" and kills the run at init (0 agents).
// The runtime already clamps concurrency to min(16, cores-2) per the parallel() barrier, so
// we pass a nominal ceiling (16) and let the runtime apply the real cores-derived cap.
const CONCURRENCY_CAP = 16

// Synth: one single-turn, no-tool schema call per prepared payload, at most MAX_SYNTH_CALLS per run.
const MAX_SYNTH_CALLS = 3
const AGENT_CEILING = (RAW_ARGS_INPUT && Number.isFinite(RAW_ARGS_INPUT.agentCeiling))
  ? RAW_ARGS_INPUT.agentCeiling
  : 40
const SYNTH_MODEL = (RAW_ARGS_INPUT && RAW_ARGS_INPUT.synthModel) || 'sonnet'
const SYNTH_AGENT_TYPE = 'coordinator:distill-synth'
const DISTILL_WRITER_TYPE = 'coordinator:distill-writer'

// Directory names whose files are read-only intake; equal to distill_mechanical.py _TRIAGE_ONLY_DIRS.
const TRIAGE_ONLY_DIRS = ['daily-summaries', 'week-changelogs', 'week-changelog']
const BUILTIN_INTAKE_ROOTS = ['archive/daily-summaries', 'archive/week-changelogs', 'archive/release-notes']

// Pure: a repo path in comparison form (forward slashes, no leading ./ or trailing /, lower case).
function normArtifactPath(p) {
  return String(p == null ? '' : p).replace(/\\/g, '/').replace(/^(\.\/)+/, '').replace(/\/+$/, '').toLowerCase()
}

// Pure: the log/intake root (built-in or logRoots) holding the path, else ''.
function intakeRootOf(path, logRoots) {
  const p = normArtifactPath(path)
  const roots = [...new Set([...BUILTIN_INTAKE_ROOTS, ...(Array.isArray(logRoots) ? logRoots : [])]
    .map(normArtifactPath).filter((r) => r !== ''))]
  return roots.find((r) => p === r || p.startsWith(`${r}/`)) || ''
}

// Pure: the one class of an artifact path, shared by plan triage and Phase 3d: intake | triage-only |
// handoff | completion | cross-repo memo | plan | live-plan | unrecognised. `logRoots` is resolveLogRoots(args.logRoots).
function artifactClassOf(path, logRoots) {
  const p = normArtifactPath(path)
  if (intakeRootOf(p, logRoots) !== '') return 'intake'
  if (TRIAGE_ONLY_DIRS.some((d) => p.split('/').slice(0, -1).includes(d))) return 'triage-only'
  if (p.startsWith('archive/handoffs/')) return 'handoff'
  if (p.startsWith('archive/completed/')) return 'completion'
  if (p.startsWith('cross-repo/archive/') || p.startsWith('archive/cross-repo/') || p.startsWith('state/cross-repo/archive/')) return 'cross-repo memo'
  if (p.startsWith('archive/plans/') || p.startsWith('archive/specs/')) return 'plan'
  // Triage input but never a delete cohort: only a top-level archived plan or spec is delete-eligible.
  if (/(^|\/)(docs\/plans|archive\/(?:[^/]+\/)*(?:plans|specs))\//.test(p)) return 'live-plan'
  return 'unrecognised'
}

// Pure: the distinct plan-class .md paths across the batches, in sorted order so the triage brief is
// byte-stable across shard invocations (cache replay).
function planPathsOf(batches, logRoots) {
  const seen = new Set()
  for (const b of Array.isArray(batches) ? batches : []) {
    for (const f of (b && Array.isArray(b.files)) ? b.files : []) {
      if (typeof f === 'string' && /\.md$/i.test(f) && ['plan', 'live-plan'].includes(artifactClassOf(f, logRoots))) seen.add(f)
    }
  }
  return [...seen].sort()
}

// Pure: the one-agent triage brief. Names the log roots and the candidate plan paths; never asks the
// agent to open a plan.
function planTriageBrief(promptText, logRoots, planPaths) {
  return `${promptText}\n\nLog roots (read these only):\n${logRoots.map((r) => `- ${r}`).join('\n')}\n\n` +
    `Candidate plans (do not open):\n${planPaths.map((p) => `- ${p}`).join('\n')}\n`
}

// Pure: drops every plan the triage judged probably_not from the batches (a batch left empty is
// dropped; non-plan files pass through) and builds the `plan_triage` report. A null or malformed
// result keeps every plan and reports 'agent-failed'; a plan the agent did not judge is kept.
function applyPlanTriage(batches, planPaths, result) {
  const norm = (p) => String(p).replace(/\\/g, '/')
  const verdicts = result && Array.isArray(result.verdicts) ? result.verdicts : null
  if (!verdicts) {
    return { batches, report: { status: 'agent-failed', candidates: planPaths.length, kept: planPaths.length, dropped: 0, dropped_plans: [] } }
  }
  const candidates = new Set(planPaths.map(norm))
  const dropped = new Map()
  for (const v of verdicts) {
    if (v && v.verdict === 'probably_not' && typeof v.path === 'string' && candidates.has(norm(v.path))) {
      dropped.set(norm(v.path), typeof v.cite === 'string' ? v.cite : '')
    }
  }
  const out = []
  for (const b of batches) {
    if (!b || !Array.isArray(b.files)) { out.push(b); continue }
    const files = b.files.filter((f) => !dropped.has(norm(f)))
    if (files.length === b.files.length) { out.push(b); continue }
    if (files.length > 0) out.push({ ...b, files })
  }
  return {
    batches: out,
    report: {
      status: 'ok',
      candidates: planPaths.length,
      kept: planPaths.length - dropped.size,
      dropped: dropped.size,
      dropped_plans: [...dropped].map(([path, cite]) => ({ path, cite })),
    },
  }
}

// The prepared payloads one run sends to synth: the first MAX_SYNTH_CALLS of args.prepared.synth.payloads;
// null when the prepared block carries no payloads or no schema (a pre-payload prepare).
function synthPayloadsOf(prepared) {
  const synth = prepared && prepared.synth
  if (!synth || !Array.isArray(synth.payloads) || !synth.schema) return null
  return synth.payloads.slice(0, MAX_SYNTH_CALLS)
}

// The clusters `distill_mechanical.py prepare` built (lifted nuggets, curation and homing applied); null
// when the prepared block carries none, which is the invocation-A route that still needs the scan wave.
function preparedClustersOf(prepared) {
  return prepared && Array.isArray(prepared.clusters) && prepared.clusters.length > 0 ? prepared.clusters : null
}

// The files prepare classified itself: a source of a clustered nugget, plus the file of every nugget
// curation dropped (a lifted id is <batch>-<1-based file index, 3 digits>-<seq>, indexed into the prepared
// batches). Every other file is the residue only a model reading can classify.
function mechanicalFilesOf(prepared) {
  const covered = new Set()
  for (const c of preparedClustersOf(prepared) || []) {
    for (const n of c.nuggets || []) if (n && n.source) covered.add(n.source)
  }
  const byId = new Map((Array.isArray(prepared && prepared.batches) ? prepared.batches : []).map((b) => [b.batchId, b]))
  for (const id of Array.isArray(prepared && prepared.dropped_nuggets) ? prepared.dropped_nuggets : []) {
    const m = /^(.+)-(\d{3})-\d{2}$/.exec(String(id))
    const batch = m && byId.get(m[1])
    const file = batch && Array.isArray(batch.files) ? batch.files[Number(m[2]) - 1] : undefined
    if (file) covered.add(file)
  }
  for (const f of Array.isArray(prepared && prepared.classifiedFiles) ? prepared.classifiedFiles : []) {
    if (typeof f === 'string' && f) covered.add(f)
  }
  return covered
}

// The files prepare read and classified: each one was reviewed by script, whatever its batch's scan did.
function classifiedFilesOf(prepared) {
  return new Set((Array.isArray(prepared && prepared.classifiedFiles) ? prepared.classifiedFiles : [])
    .filter((f) => typeof f === 'string' && f))
}

// Pure: the batches narrowed to the files prepare did not classify; a batch left empty is dropped.
function residueBatchesOf(batches, mechanicalFiles) {
  const out = []
  for (const b of batches) {
    const files = (b.files || []).filter((f) => !mechanicalFiles.has(f))
    if (files.length > 0) out.push({ ...b, files })
  }
  return out
}

// Pure: one scan-shaped result per batch from the prepared nuggets (no agent), merged with that batch's
// residue scan result when it has one. A nugget curation dropped rides as an EPHEMERAL stub so its file
// still counts as reviewed; a batch with neither a prepared nugget nor a residue result yields no result.
function mergeMechanicalScan(batches, prepared, residueResults) {
  const topicOf = new Map()
  const nuggetsBySource = new Map()
  const add = (src, n) => {
    if (!nuggetsBySource.has(src)) nuggetsBySource.set(src, [])
    nuggetsBySource.get(src).push(n)
  }
  for (const c of preparedClustersOf(prepared) || []) {
    for (const n of c.nuggets || []) {
      if (!n || !n.source) continue
      topicOf.set(n.id, c.topicKey)
      add(n.source, n)
    }
  }
  const preparedBatches = new Map((Array.isArray(prepared && prepared.batches) ? prepared.batches : []).map((b) => [b.batchId, b]))
  for (const id of Array.isArray(prepared && prepared.dropped_nuggets) ? prepared.dropped_nuggets : []) {
    const m = /^(.+)-(\d{3})-\d{2}$/.exec(String(id))
    const batch = m && preparedBatches.get(m[1])
    const file = batch && Array.isArray(batch.files) ? batch.files[Number(m[2]) - 1] : undefined
    if (file) add(file, { id, type: 'EPHEMERAL', source: file, content: 'dropped by curation in prepare', dropped: true })
  }
  const preparedFates = new Map()
  for (const f of Array.isArray(prepared && prepared.file_fates) ? prepared.file_fates : []) {
    if (f && f.path && !preparedFates.has(f.path)) preparedFates.set(f.path, f)
  }
  const out = []
  for (const batch of batches) {
    const nuggets = []
    const file_fates = []
    for (const path of batch.files || []) {
      const ns = nuggetsBySource.get(path)
      if (!ns) {
        if (preparedFates.has(path)) file_fates.push(preparedFates.get(path))
        continue
      }
      nuggets.push(...ns)
      const base = path.split('/').pop()
      const kept = ns.filter((n) => !n.dropped)
      const topics = [...new Set(kept.map((n) => topicOf.get(n.id)).filter(Boolean))]
      file_fates.push({
        path,
        fate_prose: kept.length > 0
          ? `Lifted ${kept.length} nugget(s) from ${base} by script into topic(s) ${topics.join(', ')}; no scan agent read it.`
          : `Every nugget lifted from ${base} was dropped by curation as not worth a wiki page; no scan agent read it.`,
      })
    }
    const scan = residueResults.find((r) => r && r.batch_id === batch.batchId)
    if (nuggets.length === 0 && file_fates.length === 0 && !scan) continue
    out.push({
      ...(scan || {}),
      batch_id: batch.batchId,
      nuggets_file: scan ? scan.nuggets_file : null,
      nuggets: [...nuggets, ...(scan ? scan.nuggets || [] : [])],
      file_fates: [...file_fates, ...(scan ? scan.file_fates || [] : [])],
    })
  }
  return out
}

// Pure: a per-nugget topic reaches synth judge-only — its page target (wiki_path, outline, new_page) is
// dropped, since finalize rejects every op a per-nugget topic lands without a content title. A topic_key
// starting `nugget-` is per-nugget whatever its flag says: a scan tag shared by several nuggets clusters
// into a flagless `nugget-*` topic (distill_mechanical.cluster_nuggets keys groups on the raw tag).
function judgeOnlyPayload(payload) {
  if (!payload || !Array.isArray(payload.topics)) return payload
  return {
    ...payload,
    topics: payload.topics.map((t) => {
      if (!t || t.judge_only || !(t.per_nugget || (typeof t.topic_key === 'string' && t.topic_key.startsWith('nugget-')))) return t
      const { wiki_path, new_page, outline, per_nugget, ...rest } = t
      return { ...rest, judge_only: true }
    }),
  }
}

// One synth call's brief: the op contract and exactly one prepared payload, inline. The call has no
// tools, so the brief names no path to open; a path inside the payload is a citation only.
function synthBriefFor(rawPayload) {
  const payload = judgeOnlyPayload(rawPayload)
  return `You are the single-turn synthesis step of the /distill harvest. You have no tools: do not read, ` +
    `search or run anything. Everything you may use is in the payload below; any path in it is a ` +
    `citation, never something to open.

Return the schema object: one entry per topic in the payload, topic_key copied exactly. Each entry's ` +
    `ops[] holds {section_heading, action, markdown, cites}:
- action 'append' adds markdown under a heading already in the topic's outline; 'new_section' adds a heading.
- cites lists the ids of the nuggets the markdown rests on (at least one, from that topic's nuggets). A claim ` +
    `with no nugget behind it is left out; nothing is written from memory.
- Output additions only, at most 120 lines of markdown per topic. A nugget that restates a sentence the ` +
    `outline shows adds nothing.
- State each rule as it stands: no "was once", "superseded" or was-X-now-Y prose, no run, nugget or ` +
    `pipeline references, no commit shas. A backticked repo path is checked against HEAD and an op naming a ` +
    `path absent there is rejected.
- A page with new_page true does not exist yet: give section ops only; finalize scaffolds its title and nav.
- A DECISION nugget goes in the topic's decision_records[] {nugget_id, title, problem, decision, alternatives, ` +
    `implementation, cites}; finalize mints the record and allocates its number, never you.
- Every cite and every decision-record nugget_id is one of that topic's cite_ids; the schema refuses any other.
- A topic you cannot synthesize gets empty ops, no records and a no_ops_reason: 'nothing-new-vs-page' (the ` +
    `page already states it), 'all-nuggets-duplicate' (the nuggets restate each other), ` +
    `'insufficient-substance' (too thin to write a rule from) or 'stale-code-state' (every nugget is stale).
- A nugget with stale_code_state true cites code that changed after its date: land it only as a dated ` +
    `historical note naming that date, never as a present-tense claim about code; if it cannot land that way, ` +
    `skip it with no_ops_reason 'stale-code-state'.
- Every cite_id that no op or decision record of the entry cites gets a nugget_reasons[] entry ` +
    `{nugget_id, reason} with the same four reason codes, so no nugget leaves the entry unaccounted for.
- A nugget with historical true is a plan's Problem or Background of work already shipped: land it only as a ` +
    `dated historical note naming its date, never in present tense; if it cannot land that way, skip it.
- A pinned interface, a closed vocabulary (an enum such as UNRESOLVED_INCLUDE_REASONS) or a contract with ` +
    `file:line evidence is substance: write its rule, never 'insufficient-substance'.
- A topic with judge_only true has no page: its topic_key only names the entry. Return empty ops, no ` +
    `page_title and a nugget_reasons[] entry per cite_id; a DECISION nugget in it still goes in decision_records[].
- A nugget_reasons[] entry for a nugget stating a durable contract or a root cause carries home_suggestion ` +
    `{wiki_path, kind: 'durable-contract' | 'root-cause'} naming the wiki page that should hold it; such a nugget ` +
    `is never dropped as a bare no-op reason.

Payload:
${JSON.stringify(payload)}
`
}

// Pure: the synth units a run sends, exactly as prepare shaped them: topic slug -> {key, ids}, one entry per
// payload topic_key (a key split across parts merges). A unit is never cut finer than the payload cut it.
function synthUnitsOf(payloads) {
  const units = new Map()
  for (const p of payloads || []) {
    for (const t of (p && p.topics) || []) {
      if (!t || !t.topic_key) continue
      const slug = slugifyTopic(t.topic_key)
      const unit = units.get(slug) || { key: t.topic_key, ids: new Set() }
      for (const n of t.nuggets || []) if (n && n.id) unit.ids.add(n.id)
      for (const id of t.cite_ids || []) unit.ids.add(id)
      units.set(slug, unit)
    }
  }
  return units
}

// Pure: the slug of the unit that carries a cluster: its own topic key when a payload topic bears it, else the
// unit holding its first nugget (a per-nugget cluster rides inside its batch's judge-only unit).
function unitSlugOfCluster(cluster, units) {
  const own = slugifyTopic(cluster.topicKey)
  if (units.has(own)) return own
  const first = (cluster.nuggets || []).find((n) => n && n.id)
  if (first) for (const [slug, unit] of units) if (unit.ids.has(first.id)) return slug
  return own
}

// Mechanical per-topic results from the raw synth returns (Pure). A nugget is covered when a landed
// op cites it (ADD_SECTION) or a decision record does (CREATE_DR); with finalize's synth-splice report
// (`spliceReport`) its dispositions and minted record paths replace the cite-derived ones. A topic the
// returns never named has no result; one with no page op is op 'skipped'.
function deriveSynthResults(clustersIn, returns, payloads, runId, wikiPathFor, spliceReport) {
  const byTopic = new Map()
  for (const ret of returns) {
    for (const t of (ret && Array.isArray(ret.topics)) ? ret.topics : []) {
      if (!t || typeof t.topic_key !== 'string') continue
      const key = slugifyTopic(t.topic_key)
      if (!byTopic.has(key)) byTopic.set(key, { ops: [], records: [] })
      const entry = byTopic.get(key)
      entry.ops.push(...(Array.isArray(t.ops) ? t.ops : []))
      entry.records.push(...(Array.isArray(t.decision_records) ? t.decision_records : []))
    }
  }
  const newPages = new Set()
  for (const p of payloads || []) {
    for (const t of (p && p.topics) || []) if (t && t.new_page) newPages.add(slugifyTopic(t.topic_key))
  }
  const landed = (spliceReport && Array.isArray(spliceReport.dispositions))
    ? new Map(spliceReport.dispositions.filter((d) => !['uncited', 'uncovered'].includes(d.disposition) && !String(d.disposition).startsWith('JUDGED:')).map((d) => [d.nugget_id, d.disposition]))
    : null
  const spliced = (spliceReport && Array.isArray(spliceReport.spliced)) ? spliceReport.spliced : null
  const recordPath = new Map(((spliceReport && spliceReport.decision_records) || [])
    .filter((r) => r && r.path).map((r) => [r.nugget_id, r.path]))
  const omitted = 'single-turn synth: not resolvable from the prepared payload'
  const units = synthUnitsOf(payloads)
  const out = []
  for (const cluster of clustersIn) {
    const slug = slugifyTopic(cluster.topicKey)
    const entry = byTopic.get(unitSlugOfCluster(cluster, units))
    if (!entry) continue
    const ids = new Set(cluster.nuggets.map((n) => n.id))
    const cited = new Map()
    for (const op of entry.ops) for (const c of (op && op.cites) || []) if (ids.has(c)) cited.set(c, { op: 'ADD_SECTION' })
    // A record's own nugget names the record's path; a nugget another record merely cites keeps the first
    // record that cited it, never the last, so dr_minting and the minted file name one number.
    for (const r of entry.records) {
      for (const c of (r && r.cites) || []) {
        if (!ids.has(c)) continue
        const own = recordPath.get(c)
        const prior = cited.get(c)
        if (own || !prior || prior.op !== 'CREATE_DR') cited.set(c, { op: 'CREATE_DR', target: own || recordPath.get(r.nugget_id) })
      }
    }
    const dispositions = []
    for (const [id, d] of cited) {
      if (landed && !landed.has(id)) continue
      dispositions.push({ nugget_id: id, op: landed ? landed.get(id) : d.op, ...(d.target ? { target: d.target } : {}) })
    }
    const hasPage = spliced ? spliced.some((k) => sameTopic(k, cluster.topicKey)) : entry.ops.length > 0
    out.push({
      topic_key: cluster.topicKey,
      wiki_path: wikiPathFor(cluster),
      op: hasPage ? (newPages.has(slug) ? 'created' : 'updated') : 'skipped',
      ...(hasPage ? {} : { reason: 'no-page-ops' }),
      dispositions,
      provenance: {
        run_id: runId,
        omitted_reasons: { archived_spec: omitted, original_path: omitted, last_verbose_sha: omitted, distilled: omitted },
      },
    })
  }
  return out
}

// Pure: the schema for synth call i — its own per-payload schema (topic_key and cites enums), else the shared one.
function synthSchemaFor(synth, i) {
  return (synth && Array.isArray(synth.schemas) && synth.schemas[i]) || (synth && synth.schema)
}

// Pure: how many of the topics sent to synth came back with nothing to land (an op-less entry, a record-less
// one, or no entry at all); the keys are named so a run that wrote nothing is never read as a quiet success.
// `returns` (the raw synth returns) supplies each empty topic's no_ops_reason: the model's own code,
// 'dropped' when it never named the topic, 'unreasoned' when it named it without a valid code.
// assigned = nuggets of the sent topics; covered = those with a disposition.
function synthOutcomeOf(clustersIn, results, payloads, returns) {
  const NO_OPS_REASONS = ['nothing-new-vs-page', 'all-nuggets-duplicate', 'insufficient-substance', 'stale-code-state']
  const units = synthUnitsOf(payloads)
  const named = new Map()
  const landing = new Set()
  for (const ret of returns || []) {
    for (const t of (ret && Array.isArray(ret.topics)) ? ret.topics : []) {
      if (!t || typeof t.topic_key !== 'string') continue
      const slug = slugifyTopic(t.topic_key)
      if (!named.has(slug) || NO_OPS_REASONS.includes(t.no_ops_reason)) named.set(slug, t.no_ops_reason)
      if ((Array.isArray(t.ops) && t.ops.length > 0) || (Array.isArray(t.decision_records) && t.decision_records.length > 0)) landing.add(slug)
    }
  }
  const noOps = []
  const reasons = {}
  let assigned = 0
  let covered = 0
  for (const cluster of clustersIn) {
    const unit = units.get(unitSlugOfCluster(cluster, units))
    if (!unit) continue
    if (unit.ids.size === 0) assigned += (cluster.nuggets || []).length
    const r = results.find((x) => sameTopic(x.topic_key, cluster.topicKey))
    covered += r ? (r.dispositions || []).length : 0
  }
  for (const [slug, unit] of units) {
    assigned += unit.ids.size
    if (landing.has(slug)) continue
    noOps.push(unit.key)
    reasons[unit.key] = !named.has(slug) ? 'dropped' : (NO_OPS_REASONS.includes(named.get(slug)) ? named.get(slug) : 'unreasoned')
  }
  return {
    topics_sent: units.size, topics_with_ops: units.size - noOps.length, no_ops_topics: noOps.length, no_ops_topic_keys: noOps,
    covered, assigned, no_ops_reasons: reasons,
  }
}

// The promote manifest: no staged files of its own (finalize splices the inline synth returns into
// staged pages and appends them), the raw returns for the cite-checked splice, and the source hashes of
// the topics that produced a page.
function buildPromoteManifest(runId, results, synthReturns, hashes) {
  const topicHashes = {}
  for (const r of results) {
    const harvested = r.op !== 'skipped' || (r.dispositions || []).length > 0 // a record-only topic mints a DR, no page op
    if (harvested && hashes && hashes[r.topic_key]) topicHashes[r.topic_key] = hashes[r.topic_key]
  }
  return { run_id: runId, files: [], synth_results: synthReturns, hashes: topicHashes }
}

// Pure: the synth payloads re-entry sends for SEND_BACK rows. Each is one original payload cut down to its
// page topics holding a nugget cited from a wanted artifact, with only those nuggets; a judge-only or
// per-nugget topic has no page to land ops on and is left out. `index` is the original payload's position, so
// the call reuses its schema.
function reentryPayloadsFor(payloads, rows) {
  const want = new Set((rows || []).map((r) => normArtifactPath(r.artifact_path)))
  const out = []
  ;(payloads || []).forEach((p, index) => {
    const topics = []
    const paths = new Set()
    for (const t of (p && p.topics) || []) {
      if (!t || t.judge_only || t.per_nugget || String(t.topic_key).startsWith('nugget-')) continue
      const nuggets = (t.nuggets || []).filter((n) => n && want.has(normArtifactPath(n.cite)))
      if (nuggets.length === 0) continue
      for (const n of nuggets) paths.add(normArtifactPath(n.cite))
      topics.push({ ...t, nuggets, cite_ids: nuggets.map((n) => n.id) })
    }
    if (topics.length > 0) out.push({ index, payload: { ...p, topics }, paths })
  })
  return out
}

// Pure: where each SEND_BACK row stands after a re-entry round. `entries` is reentryPayloadsFor's output;
// `returns` is aligned with it (null for an agent that failed). A row whose every call failed is absent
// from the result and stays SEND_BACK for the next round. No row resolves DELETE: the returned ops land only
// when `distill_mechanical.py finalize` splices the reentry manifest.
function settleReentryRows(rows, entries, returns) {
  const out = new Map()
  for (const row of rows || []) {
    const key = normArtifactPath(row.artifact_path)
    const mine = (entries || []).map((e, i) => ({ e, ret: returns[i] })).filter(({ e }) => e.paths.has(key))
    if (mine.length === 0) {
      out.set(row.artifact_path, {
        disposition: 'BLOCKED',
        reason: 're-entry found no page-topic nugget of this artifact to re-synthesize ' +
          `(original reason: ${row.reason})`,
        source_nugget_ids: [],
      })
      continue
    }
    const answered = mine.filter(({ ret }) => ret)
    if (answered.length === 0) continue
    const ids = new Set()
    for (const { e } of mine) {
      for (const t of e.payload.topics) for (const n of t.nuggets) if (normArtifactPath(n.cite) === key) ids.add(n.id)
    }
    const cited = new Set()
    for (const { ret } of answered) {
      for (const t of Array.isArray(ret.topics) ? ret.topics : []) {
        for (const op of Array.isArray(t.ops) ? t.ops : []) for (const c of op.cites || []) cited.add(c)
        for (const dr of Array.isArray(t.decision_records) ? t.decision_records : []) for (const c of dr.cites || []) cited.add(c)
      }
    }
    const landed = [...ids].filter((id) => cited.has(id))
    out.set(row.artifact_path, {
      disposition: 'BLOCKED',
      reason: landed.length > 0
        ? `pending finalize of reentry_manifest (${landed.length} nugget(s) of this artifact carry returned ops)`
        : 're-entry returned no op for this artifact\'s nuggets; nothing to finalize',
      source_nugget_ids: landed,
    })
  }
  return out
}

// `loadedInput` is the inline args.prepared payload (null for a plain args-passed run); a non-null
// value is "relayed" for the count assertions below.
let loadedInput = null
const loadStats = () => buildLoadStats(loadedInput && loadedInput.batches, loadedInput && loadedInput.wikiSlugs)
const PREPARED = RAW_ARGS_INPUT && RAW_ARGS_INPUT.prepared

if (RAW_ARGS_INPUT && RAW_ARGS_INPUT.curatedFile) {
  return {
    phase_reached: 'load',
    halted: 'curated-file-retired',
    detail: 'distill-harvest: args.curatedFile is no longer loaded in-workflow — put the saved distill.curate_clusters return at args.prepared.curated, or pass curatedTags inline',
    load_stats: loadStats(),
  }
}
if (PREPARED && PREPARED.curated && RAW_ARGS_INPUT.curatedTags != null) {
  return {
    phase_reached: 'load',
    halted: 'curated-input-ambiguous',
    detail: 'distill-harvest: args carries both prepared.curated and curatedTags — pass exactly one curated channel',
    load_stats: loadStats(),
  }
}

if (RAW_ARGS_INPUT && RAW_ARGS_INPUT.inputFile && !PREPARED) {
  throw new Error(
    `distill-harvest: args.inputFile="${RAW_ARGS_INPUT.inputFile}" is not loaded in-workflow — run ` +
    `distill_mechanical.py prepare over it and pass the resulting prepared.json as args.prepared.`
  )
}
if (PREPARED) {
  if (typeof PREPARED !== 'object' || Array.isArray(PREPARED)) {
    throw new Error('distill-harvest: args.prepared must be the parsed prepared.json object')
  }
  phase('load')
  loadedInput = PREPARED.wikiSlugsPacked
    ? { ...PREPARED, wikiSlugs: unpackWikiSlugs(PREPARED.wikiSlugsPacked) }
    : PREPARED
}

const RUN_ID = (loadedInput && loadedInput.runId) || RAW_ARGS_INPUT.runId
const REPO_ROOT = (loadedInput && loadedInput.repoRoot) || RAW_ARGS_INPUT.repoRoot
let BATCHES = (loadedInput && loadedInput.batches) || RAW_ARGS_INPUT.batches
if (!Array.isArray(BATCHES) || BATCHES.length === 0) {
  return {
    phase_reached: 'load',
    halted: 'empty-input-batches',
    detail: `distill-harvest: input has empty or missing "batches"` +
      (RAW_ARGS_INPUT.inputFile ? ` (args.inputFile="${RAW_ARGS_INPUT.inputFile}" — run distill_mechanical.py prepare and pass its prepared.json as args.prepared)` : ' (args-passed input)'),
    load_stats: loadStats(),
  }
}
const countHalt = assertRelayedCounts(
  BATCHES,
  {
    args: { batch_count: RAW_ARGS_INPUT.batch_count, total_file_count: RAW_ARGS_INPUT.total_file_count },
    file: loadedInput
      ? { batch_count: loadedInput.batch_count, total_file_count: loadedInput.total_file_count }
      : {},
  },
  loadedInput !== null
)
if (countHalt) {
  return { ...countHalt, load_stats: loadStats() }
}
const curatedMissing = curatedMissingHalt(PREPARED, RAW_ARGS_INPUT, loadedInput)
if (curatedMissing) {
  return { ...curatedMissing, load_stats: loadStats() }
}
const listCountHalt = assertRelayedListCounts(
  {
    judgmentClusters: (loadedInput && loadedInput.judgmentClusters) || RAW_ARGS_INPUT.judgmentClusters,
    contradictionClusters: (loadedInput && loadedInput.contradictionClusters) || RAW_ARGS_INPUT.contradictionClusters,
    crossRepoDispositions: (loadedInput && loadedInput.crossRepoDispositions) || RAW_ARGS_INPUT.crossRepoDispositions,
  },
  {
    args: {
      judgmentClusters: RAW_ARGS_INPUT.judgmentClusterCount,
      // With a curated return and no list in the input file or args, the list arrives through the
      // curated return and the count is checked there.
      contradictionClusters: (PREPARED && PREPARED.curated) &&
        !listSupplied(loadedInput && loadedInput.contradictionClusters, RAW_ARGS_INPUT.contradictionClusters)
        ? undefined
        : RAW_ARGS_INPUT.contradictionClusterCount,
      crossRepoDispositions: RAW_ARGS_INPUT.crossRepoDispositionCount,
    },
    file: loadedInput
      ? {
          judgmentClusters: loadedInput.judgmentClusterCount,
          contradictionClusters: loadedInput.contradictionClusterCount,
          crossRepoDispositions: loadedInput.crossRepoDispositionCount,
        }
      : {},
  },
  loadedInput !== null
)
if (listCountHalt) {
  return { ...listCountHalt, load_stats: loadStats() }
}
// D2 (2026-07-19 fix): wikiInventory (topicKey-keyed, guessed at Phase-0 build time before
// topicKeys exist) is superseded by wikiDirs/wikiSlugs (disk-resolved, slug-keyed). Back-compat:
// tolerate a caller still passing the legacy wikiInventory shape — don't crash, just derive an
// empty slug index (no disk-resolved targeting, same behavior as a fresh repo with no wiki yet).
// `[]` is truthy, so `INPUT.wikiDirs: []` would leave
// WIKI_DIRS empty (WIKI_DIRS[0] === undefined -> broken "undefined/<slug>.md" paths downstream)
// without this explicit length guard.
const wikiDirsCandidate = (loadedInput && loadedInput.wikiDirs) || RAW_ARGS_INPUT.wikiDirs
const WIKI_DIRS = (wikiDirsCandidate && wikiDirsCandidate.length) ? wikiDirsCandidate : ['docs/wiki']
const WIKI_SLUGS = (loadedInput && loadedInput.wikiSlugs) || RAW_ARGS_INPUT.wikiSlugs || {}
// Fail-loud: a schema-forced loader that drops wikiSlugs makes consolidation mint duplicate guides.
const wikiSlugLoadedCount = Object.keys(WIKI_SLUGS).length
const wikiSlugDeclaredCount = loadedInput ? loadedInput.wikiSlugCount : undefined
const wikiSlugArgsCount = Number.isInteger(RAW_ARGS_INPUT.wikiSlugCount) ? RAW_ARGS_INPUT.wikiSlugCount : undefined
if ((loadedInput && (
  (typeof wikiSlugDeclaredCount === 'number' && wikiSlugDeclaredCount !== wikiSlugLoadedCount) ||
  (wikiSlugDeclaredCount === undefined && wikiSlugLoadedCount === 0 && wikiDirsCandidate && wikiDirsCandidate.length)
)) || (wikiSlugArgsCount !== undefined && wikiSlugArgsCount !== wikiSlugLoadedCount)) {
  return {
    phase_reached: 'load',
    halted: 'wiki-slugs-dropped',
    detail: `distill-harvest: loaded wikiSlugs count=${wikiSlugLoadedCount} but ` +
      (typeof wikiSlugDeclaredCount === 'number' && wikiSlugDeclaredCount !== wikiSlugLoadedCount
        ? `input declares wikiSlugCount=${wikiSlugDeclaredCount}`
        : wikiSlugArgsCount !== undefined && wikiSlugArgsCount !== wikiSlugLoadedCount
          ? `args declares wikiSlugCount=${wikiSlugArgsCount}`
          : `wikiDirs=${JSON.stringify(wikiDirsCandidate)} are present`) +
      ` (args.inputFile="${RAW_ARGS_INPUT.inputFile}") — the input loader dropped the slug index; re-run rather than minting duplicate wiki guides.`,
    load_stats: loadStats(),
  }
}
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
// Phase 2.5 (judgment mining) inputs — PIPELINE.md:604-612. The producer of judgment clusters is
// the in-run 'judgment-corpus' scout inside judgment-mining-2-5; `judgmentClusters` supplied by
// file or args is OPTIONAL, and when present it wins over the scout. Each entry:
//   { topicCluster: '<claim-topic noun>', verdictDirection: 'forbid'|'require'|'prefer'|'avoid',
//     liveSidecarPaths: ['<reviewer sidecar path>', ...], existingJudgmentEntry: '<path>'|null }
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
// CONTRADICTION_CLUSTERS and CURATED_TAGS resolve after the curated-file load, below the scan wave.
// resumeFromRunId intentionally not destructured — the Workflow tool itself consumes it at
// invocation time, not in-script.

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
    // downstream. Clustering reads the schema-validated
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

// Logs-first plan triage (agent-prompts/plan-triage.md): one Haiku relay reads the run logs only and
// judges which cited plans moved the needle; a probably_not plan never reaches the scan wave.
const PLAN_TRIAGE_SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'verdict', 'cite'],
        properties: {
          path: { type: 'string' },
          verdict: { type: 'string', enum: ['moved_the_needle', 'probably_not'] },
          cite: { type: 'string' },
        },
      },
    },
  },
}
const PLAN_TRIAGE_PROMPT = `You are a plan-triage relay. Decide, from the run logs alone, which of the candidate plans
moved the needle. Do NOT open, cat, head or grep any file named under "Candidate plans" —
the point of this step is to avoid reading them.

Read only the files under the log roots (list and read them with your file tools). A plan moved the needle
when a log entry shows it shipped, changed a decision, fixed a defect, or was cited as the
reason for later work. A plan no log mentions, or one a log mentions only as scheduled,
deferred or abandoned, is probably_not.

Return one verdict per candidate plan path, verbatim as given:
  { path, verdict: "moved_the_needle" | "probably_not", cite }
\`cite\` is the log file and a short quote or heading that justifies the verdict; for
probably_not with no mention, write "no log mention". When unsure, answer moved_the_needle:
a wrong probably_not drops a plan from the run.`
phase('plan-triage')
// With prepared clusters the plans prepare lifted are already clustered; triage judges only the residue.
const PREPARED_CLUSTERS = preparedClustersOf(PREPARED)
const MECHANICAL_FILES = mechanicalFilesOf(PREPARED)
const TRIAGE_LOG_ROOTS = resolveLogRoots(RAW_ARGS_INPUT && RAW_ARGS_INPUT.logRoots)
const TRIAGE_PLAN_PATHS = planPathsOf(PREPARED_CLUSTERS ? residueBatchesOf(BATCHES, MECHANICAL_FILES) : BATCHES, TRIAGE_LOG_ROOTS)
const ADMITTED_PLAN_COUNT = planPathsOf(BATCHES, TRIAGE_LOG_ROOTS).length
let PLAN_TRIAGE_REPORT = ADMITTED_PLAN_COUNT > 0
  ? { status: 'skipped-all-prepared', admitted: ADMITTED_PLAN_COUNT, candidates: 0, kept: 0, dropped: 0, dropped_plans: [] }
  : { status: 'skipped-no-plans', admitted: 0, candidates: 0, kept: 0, dropped: 0, dropped_plans: [] }
if (TRIAGE_PLAN_PATHS.length > 0) {
  // judgment-keeper: plan triage (haiku) — judging from the run logs which cited plans moved the needle.
  const triageResult = await agent(
    planTriageBrief(PLAN_TRIAGE_PROMPT, TRIAGE_LOG_ROOTS, TRIAGE_PLAN_PATHS),
    { schema: PLAN_TRIAGE_SCHEMA, agentType: DISTILL_WRITER_TYPE, phase: 'plan-triage', label: 'plan-triage', model: 'haiku' }
  )
  const triaged = applyPlanTriage(BATCHES, TRIAGE_PLAN_PATHS, triageResult)
  BATCHES = triaged.batches
  PLAN_TRIAGE_REPORT = triaged.report
  if (BATCHES.length === 0) {
    return {
      phase_reached: 'plan-triage',
      halted: 'all-plans-triaged-out',
      detail: 'distill-harvest: the plan triage judged every file in the run probably_not; nothing to scan',
      plan_triage: PLAN_TRIAGE_REPORT,
    }
  }
}

phase('scan')
// D2: real, disk-resolved slug names (not a topicKey-keyed guess) so Haiku can mark
// ALREADY_CAPTURED against files that genuinely exist, not a Phase-0 guess.
// Pass slug + path (not bare slugs) so the scan agent has
// a concrete path it could open and read the guide content against, rather than only being
// able to string-match its own tag against an opaque slug label.
const EXISTING_WIKI_SLUG_NAMES = Object.entries(WIKI_SLUGS)
  .map(([slug, p]) => `${slug} (${p})`)
  .sort()
  .join(', ') || 'none'
function renderFormatHints(h) {
  if (typeof h === 'string' && h !== '') return h
  if (h && typeof h === 'object' && Object.keys(h).length > 0) return JSON.stringify(h)
  return 'none'
}
const scanBriefFor = (batch) => COMMON + `

You are a Haiku artifact scanner (Wave 1 of the /distill harvest Workflow).

Your assigned batch: ${batch.batchId} — ${batch.description}
Files to read: ${JSON.stringify(batch.files)}
Format hints: ${renderFormatHints(batch.formatHints)}

Read every file in your batch and extract structured knowledge nuggets. Classify each
piece of extractable knowledge as one of: DECISION, SUPERSEDED, KNOWLEDGE (with a
system_tag naming the topic it clusters under), EPHEMERAL, ALREADY_CAPTURED, AMBIGUOUS,
PRESERVE. \`system_tag\` MUST be exactly ONE tag — never a comma- or semicolon-joined list of
multiple topics (e.g. "guard_design, test_design" is wrong). If a nugget genuinely spans two
topics, pick the single primary one it belongs under; do not invent a combined tag.
Assign canonical nugget IDs as <batch_id>-<seq> (zero-padded, e.g. ${batch.batchId}-001).
Extract, do not synthesize — you are a cataloger, not an analyst. Include exact quotes for
decisions; do not paraphrase reasoning. Copy truncated-looking strings exactly; do not
complete words. A nugget must NOT be classified ALREADY_CAPTURED on
the basis of a ~/.claude memory pointer — that is not durable capture; only an in-repo home
(docs/decisions/, docs/wiki/, state/cross-repo-commitments/, or a canonical plan/spec) counts.
Existing wiki guides (slug and path — open the path to check content before deciding):
${EXISTING_WIKI_SLUG_NAMES}. Mark a nugget ALREADY_CAPTURED only
if its knowledge is already in one of these guides.

Every nugget's \`source\` MUST be one of the exact strings in the "Files to read" list above,
copied verbatim — the full repo-relative path, NEVER a bare basename. Downstream bookkeeping
joins on this string; a shortened path silently files a harvested artifact as "nothing worth
promoting" and makes it get re-scanned forever.

Write your full nugget extraction to a NEW file in your own session scratchpad named
\`${RUN_ID}-${batch.batchId}-extraction.md\`; never reuse or append to an existing file. Return
the schema-required fields, with the REAL path you wrote to as nuggets_file. This is a
debug/audit trail only: clustering uses your returned structured nuggets[] array, not this
file — the file exists so a human can inspect your full extraction after the fact.

Every file yields at least one nugget. A file with nothing new gets an EPHEMERAL nugget, or an
ALREADY_CAPTURED one naming the page that holds its content. No later pass reads this file:
never leave it, or any part of it, for one. A file with no nugget is scanned again next run.

Also return \`file_fates\`: ONE entry per file in "Files to read" above, every file. Each entry's \`path\`
must be copied verbatim from "Files to read" (same rule as nugget \`source\`: full
repo-relative path, never a bare basename). Each entry's \`fate_prose\` is ONE sentence of
domain prose, at least 8 words, describing what the artifact was actually about and what
became of its content — NOT a process tag like "scaffolding" or a mechanical restatement of
counts ("harvested 2 nuggets on X, Y"). Write it the way you'd describe the artifact to a
colleague who asked what it covered and whether it mattered.`

// judgment-keeper: nugget scan and fate prose (haiku) — reading artifacts and writing domain prose.
// A batch whose scan agent died or returned zero nuggets is scanned once more before it counts as a
// failure: the Haiku scanner is nondeterministic on identical input (slice 16h56 returned 0 nuggets,
// the unchanged re-run 16h57 returned 8), and an all-failed scan halts the run.
const SCAN_ATTEMPTS = 2
const scanResults = []
// Prepared clusters carry every file prepare classified: the scan sees only the residue, none when empty.
const SCAN_BATCHES = PREPARED_CLUSTERS ? residueBatchesOf(BATCHES, MECHANICAL_FILES) : BATCHES
if (PREPARED_CLUSTERS) {
  log(`scan: ${MECHANICAL_FILES.size} file(s) classified by prepare, ${SCAN_BATCHES.reduce((n, b) => n + b.files.length, 0)} residue file(s) in ${SCAN_BATCHES.length} batch(es) to scan`)
}
let scanPending = SCAN_BATCHES
for (let attempt = 1; attempt <= SCAN_ATTEMPTS && scanPending.length > 0; attempt++) {
  const got = await parallel(
    scanPending.map((batch) => () =>
      agent(scanBriefFor(batch), {
        schema: NUGGET_SCHEMA,
        agentType: DISTILL_WRITER_TYPE,
        phase: 'scan',
        label: attempt === 1 ? batch.batchId : `${batch.batchId}-r${attempt}`,
        model: 'haiku',
      })
    ),
    // concurrency is a parallel() barrier option only; agent() has no concurrency knob, so a
    // per-agent field here would be redundant/dead.
    { concurrency: CONCURRENCY_CAP }
  )
  const retry = []
  scanPending.forEach((batch, i) => {
    const r = got[i]
    const read = r && Array.isArray(r.nuggets) && r.nuggets.length > 0
    if (read || attempt === SCAN_ATTEMPTS) {
      if (r) scanResults.push(r)
    } else {
      log(`${batch.batchId}: scan ${r ? 'returned zero nuggets' : 'agent failed'} — scanning once more`)
      retry.push(batch)
    }
  })
  scanPending = retry
}

if (scanResults.length === 0 && SCAN_BATCHES.length > 0 && !PREPARED_CLUSTERS) {
  return { phase_reached: 'scan', halted: 'all-scan-agents-failed', plan_triage: PLAN_TRIAGE_REPORT, concurrency_cap: CONCURRENCY_CAP }
}
// The residue scan nuggets stay outside the prepared clusters: they ride the return for the driver to hand
// back to `prepare --nuggets`, and their files stay SKIP until a later run harvests them.
const RESIDUE_SCAN = { files: PREPARED_CLUSTERS ? SCAN_BATCHES.reduce((n, b) => n + b.files.length, 0) : 0, nuggets: [] }
if (PREPARED_CLUSTERS) {
  RESIDUE_SCAN.nuggets = scanResults.flatMap((r) => (r.nuggets || []).filter((n) => !['EPHEMERAL', 'ALREADY_CAPTURED', 'PRESERVE'].includes(n.type)))
  scanResults.splice(0, scanResults.length, ...mergeMechanicalScan(BATCHES, PREPARED, scanResults))
}
const RESIDUE_NUGGET_IDS = new Set(RESIDUE_SCAN.nuggets.map((n) => n.id))

// nuggets_file is the audit trail; one not keyed by this run id is another run's file and is
// never evidence for this one, so it is cleared rather than reported.
for (const result of scanResults) {
  if (typeof result.nuggets_file === 'string' && !result.nuggets_file.includes(String(RUN_ID))) {
    log(`${result.batch_id}: nuggets_file ${result.nuggets_file} is not keyed by run ${RUN_ID} — cleared as stale`)
    result.nuggets_file = null
  }
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
  // Zero nuggets is a failed scan, not "nothing extractable": every file owes at least one
  // nugget, so an empty return means the batch was never read.
  if (emptyCount === nuggets.length) {
    if (nuggets.length === 0) log(`${result.batch_id}: returned zero nuggets — counted as a scan failure`)
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

// Every batch failed or came back empty: nothing was read, so no later phase has evidence to
// act on. Halt rather than let join-integrity call an empty join clean.
if (failedBatchIds.length === BATCHES.length) {
  return { phase_reached: 'scan', halted: 'empty-scan', failed_batch_ids: failedBatchIds, plan_triage: PLAN_TRIAGE_REPORT, concurrency_cap: CONCURRENCY_CAP }
}

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
// No nugget source at all against a non-empty batch list is an empty scan, never a clean join.
const joinVerdict = distinctSourceCount === 0 && sourceNormalization.batch_files > 0
  ? 'failed'
  : unjoinableRate === 0
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
const disposalSuppressedReason = disposalSuppressed && distinctSourceCount === 0
  ? `empty scan: 0 nugget sources across ${sourceNormalization.batch_files} batch file(s) — disposal manifest suppressed`
  : disposalSuppressed
  ? `join integrity unjoinable rate ${(unjoinableRate * 100).toFixed(1)}% ` +
    `(${unjoinableCount}/${distinctSourceCount}) exceeds threshold ` +
    `${(JOIN_INTEGRITY_MAX_UNJOINABLE_RATE * 100).toFixed(0)}% — disposal manifest suppressed`
  : null

log(`join integrity: ${joinVerdict} — ${unjoinableCount}/${distinctSourceCount} distinct ` +
  `nugget source(s) unjoinable (rate ${unjoinableRate.toFixed(3)}, threshold ` +
  `${JOIN_INTEGRITY_MAX_UNJOINABLE_RATE})` +
  (disposalSuppressed ? ` — DISPOSAL SUPPRESSED: ${disposalSuppressedReason}` : ''))

// Curated verdicts reach the script through one of two inline channels:
//   - args.prepared.curated: the saved `distill.curate_clusters` return, verbatim. Its list is
//     checked against `counts.total` and args.curatedVerdictCount.
//   - args.curatedTags: the tag-keyed `{tag: verdict}` map, or the verdict list (normalised
//     through curatedMapFromVerdicts).
// Invocation B is "curatedTags or prepared.curated present in args". `args` arrives as a JSON
// string (state/lessons/2026-07-09-workflow-args-arrives-as-a-json-string); INPUT is its one parse.
let loadedCurated = null
if (PREPARED && PREPARED.curated) {
  loadedCurated = PREPARED.curated
  if (typeof loadedCurated !== 'object' || !Array.isArray(loadedCurated.verdicts)) {
    throw new Error('distill-harvest: args.prepared.curated must be the saved distill.curate_clusters return (an object with a verdicts list)')
  }
  const curatedCountHalt = assertRelayedListCounts(
    {
      verdicts: loadedCurated.verdicts,
      contradictionClusters: loadedCurated.contradictionClusters,
    },
    {
      args: {
        verdicts: RAW_ARGS_INPUT.curatedVerdictCount,
        contradictionClusters: listSupplied(loadedInput && loadedInput.contradictionClusters, RAW_ARGS_INPUT.contradictionClusters)
          ? undefined
          : RAW_ARGS_INPUT.contradictionClusterCount,
      },
      file: {
        verdicts: loadedCurated.counts ? loadedCurated.counts.total : undefined,
        contradictionClusters: loadedCurated.contradictionClusterCount,
      },
    },
    true
  )
  if (curatedCountHalt) {
    return curatedCountHalt
  }
}
const CURATED_TAGS = loadedCurated
  ? curatedMapFromVerdicts(loadedCurated.verdicts)
  : Array.isArray(INPUT.curatedTags)
    ? curatedMapFromVerdicts(INPUT.curatedTags)
    : INPUT.curatedTags
// Passthrough-only, result-level fields off claude-klabauter's curated payload — the threshold claude-klabauter
// actually APPLIED, whether it was auto-derived, and the resulting nugget-drop share. The curated
// file wins, then INPUT; read null-tolerant (`??`, not `||` — 0/false are real values). Surfaced
// as received, never recomputed and never used to override `recommended_keep_threshold`.
const CURATED_THRESHOLD_APPLIED = (loadedCurated && loadedCurated.threshold_applied) ?? INPUT.threshold_applied ?? null
const CURATED_THRESHOLD_AUTO = (loadedCurated && loadedCurated.threshold_auto) ?? INPUT.threshold_auto ?? null
const CURATED_NUGGET_DROP_SHARE = (loadedCurated && loadedCurated.nugget_drop_share) ?? INPUT.nugget_drop_share ?? null

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
// an EM/Phase-0 computation over this run's per-batch journal, not computed in this script.
// `join_integrity` IS inline-computed above; that asymmetry with failed_batch_ids is deliberate.
//
// `recommended_keep_threshold` is returned alongside `tag_counts` — curation's minting policy
// lives entirely on claude-klabauter's side of the seam, as the `keep_threshold` value we pass into their
// gate call, not as a constant kept on our side.
//
// `tag_counts` reuses clusterNuggets()'s own topicKey derivation below (a plain read of its
// grouping).
//
// `recommended_keep_threshold` — claude-klabauter's `distill.curate_clusters` gate compares
// `keep_threshold` against a cluster's FAMILY total (summed across every tag folded into it), so
// the threshold is the one knob that decides cold-start survival vs. steady-state floor
// semantics. Derivation uses only claude-klabauter's two measured points (mean-of-20-seeds drop rate over
// a 433-nugget/249-tag census):
//   thr=2: 20n->71.2%, 60n->44.4%, 150n->27.4%, 433n(full)->17.1%
//   thr=1: 20n->12.0%, 60n->8.7%,  150n->8.8%,  433n(full)->8.1% (flat 8-12% across a 20x range)
//
// Cold-start -> 1: fires when WIKI_SLUGS is empty (virgin wiki tree) OR the carry-forward nugget
// count is below 150 — at 150 nuggets thr=2 still discards 27.4% of the corpus, which is not a
// tail, it is the harvest. Mature -> 2 (the measured 17.1%-drop default) otherwise.
// Deliberately NOT 3: pure floor semantics ("a 1-2-nugget cluster doesn't earn its own file")
// would want it, but nobody has measured its drop rate on any corpus.
//
// Honest limitation (measured-boundary gap): at threshold 2, only 1-nugget families are
// suppressed — a 2-nugget family still mints its own file.
// SINGLETON_FLOOR's stated job ("a 1-2-nugget cluster doesn't earn its own new file") is thus
// only partly discharged by this derivation, and stays that way until a threshold-3 measurement
// lands.
if (!CURATED_TAGS && !PREPARED_CLUSTERS) {
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
    plan_triage: PLAN_TRIAGE_REPORT,
    load_stats: buildLoadStats(BATCHES, WIKI_SLUGS),
    // The carry-forward nuggets, each tagged with its raw cluster key: the input of
    // `distill_mechanical.py prepare --nuggets`, which clusters them, hashes their sources and runs
    // the candidates batch.
    scan_nuggets: tagCensusClusters.flatMap((c) => c.nuggets.map((n) => ({ ...n, tag: c.topicKey }))),
    resume_hint:
      `Run claude-klabauter distill.curate_clusters over tag_counts with keep_threshold=${recommendedKeepThreshold} ` +
      `(${recommendedKeepThresholdReason}); run distill_mechanical.py prepare with --nuggets (scan_nuggets) ` +
      'and --verdicts (the saved op return, which prepare inlines at prepared.curated); then re-invoke this SAME script with args.prepared set to ' +
      'that prepared.json unedited and curatedVerdictCount set to its curated.counts.total, or with curatedTags set to the inline {tag: verdict} map; ' +
      'runId set to run_id above, and resumeFromRunId set to the wf_... runId ' +
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
//   2. `drop_cause` (a two-value enum: 'placeholder'/'below-threshold', null
//      on non-drops; bare-tag no-sibling nuggets are kept, not dropped) and a `drop_by_cause` count block have LANDED on claude-klabauter's side, commit
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
// Every word must match in order, plural-insensitive, not a shared prefix stem: a leading-stem
// match homed portable-export into portable-docs-source-boundary and admission-gate into
// admissibility-gate, overwriting unrelated pages.
function findFuzzyWikiHome(slug, wikiSlugsIndex) {
  const stems = (s) => dr146Normalize(s).split('-').filter(Boolean).map((w) => w.replace(/ies?$/, 'y').replace(/s$/, ''))
  const want = stems(slug)
  // A two-plus-word slug that is the whole leading run of exactly one existing slug homes there
  // (entity-anchor -> entity-anchor-encoding-contract); two candidates are ambiguous, no home.
  // Whole words carry the safety, so this runs before the single-word stem floor below.
  if (want.length >= 2) {
    const homes = Object.entries(wikiSlugsIndex).filter(([existingSlug]) => {
      const have = stems(existingSlug)
      return have.length > want.length && want.every((st, i) => st === have[i])
    })
    if (homes.length === 1) return homes[0][1]
  }
  // Mirror case: an existing 2+-word slug that is the whole leading or trailing run of the new
  // slug, for exactly one existing slug (fleet-claim-identity -> claim-identity,
  // text-embed-door-serving-shape -> text-embed-door); the extra words narrow the same subject.
  const within = Object.entries(wikiSlugsIndex).filter(([existingSlug]) => {
    const have = stems(existingSlug)
    const off = want.length - have.length
    if (have.length < 2 || off <= 0) return false
    return have.every((st, i) => st === want[i]) || have.every((st, i) => st === want[off + i])
  })
  if (within.length === 1) return within[0][1]
  const candidate = leadingStem(slug)
  if (candidate.word.length < DR146_MIN_STEM_LEN) return null
  for (const [existingSlug, path] of Object.entries(wikiSlugsIndex)) {
    const existing = leadingStem(existingSlug)
    if (existing.word.length < DR146_MIN_STEM_LEN) continue
    const have = stems(existingSlug)
    if (have.length === want.length && have.every((st, i) => st === want[i])) return path
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

// ---------------------------------------------------------------------------------------------
// Meaning-match homing: findFuzzyWikiHome above matches slug words only, so a synonym or
// meaning match (embed vs embedding-model-selection) mints a duplicate page. Before a NEW page is
// minted, a homeless cluster whose slug shares a stem with an existing page slug or wiki directory
// name is put to ONE batched forced-schema model call over those candidates' titles and first
// lines; a cluster with no stem-sharing candidate makes no call. The answer reaches
// consolidateClusters as `config.meaningHomes` (slug -> existing path), since that function runs
// in an isolated scope.
// ---------------------------------------------------------------------------------------------

const MEANING_MATCH_MAX_CANDIDATES = 8
const MEANING_MATCH_NUGGET_SAMPLE = 4
const MEANING_MATCH_NUGGET_CHARS = 200
const MEANING_MATCH_HEAD_LINES = 12
// Characters of per-cluster briefs one batched call carries; a larger set splits greedily so no
// single reply must answer more than this much context.
const MEANING_MATCH_BATCH_MAX_CHARS = 60000
const MEANING_MATCH_PREVIEW_HEADINGS = 8
const MEANING_MATCH_PREVIEW_LEADS = 8
const MEANING_MATCH_PREVIEW_LEAD_CHARS = 60
const MEANING_MATCH_STOP_WORDS = new Set(['and', 'the', 'for', 'with', 'from', 'into', 'shape', 'design', 'v2'])

const MEANING_MATCH_SCHEMA = {
  type: 'object',
  required: ['answers'],
  properties: {
    answers: {
      type: 'array',
      items: {
        type: 'object',
        required: ['slug', 'home'],
        properties: {
          slug: { type: 'string' }, // the cluster's topic slug, verbatim from its CLUSTER line
          home: { type: 'string' }, // one candidate path verbatim, or 'NEW' when no candidate is the same subject
          reason: { type: 'string' },
        },
      },
    },
  },
}

const MEANING_MATCH_CLUSTER_MARK = '=== CLUSTER '

function meaningWords(s) {
  return String(s).toLowerCase().replace(/^\d{4}-\d{2}-\d{2}-/, '').split(/[^a-z0-9]+/)
    .map((w) => w.replace(/ies$/, 'y').replace(/(?<![su])s$/, ''))
    .filter((w) => w.length >= 3 && !MEANING_MATCH_STOP_WORDS.has(w))
}

// Two words share a stem when equal, when one is a 4+-character substring of the other
// (embed/embedding, bash/debash), or when they open with the same 6+ characters
// (encryption/encrypted); the model call decides whether the subjects truly match.
function meaningWordsMatch(a, b) {
  if (a === b) return true
  const [short, long] = a.length <= b.length ? [a, b] : [b, a]
  if (short.length >= 4 && long.includes(short)) return true
  let p = 0
  while (p < short.length && short[p] === long[p]) p++
  return p >= 6
}

// Existing pages whose slug or wiki-directory name shares a stem with `slug`, best first, capped.
// A directory-name match qualifies every page under that directory. Rank weights each shared
// word by its rarity across the wiki, so a common word (migration) never crowds the one page
// sharing a rare word (bash) out of the cap.
function meaningMatchCandidates(slug, wikiSlugs, wikiDirs) {
  const want = meaningWords(slug)
  if (want.length === 0) return []
  const dirs = (wikiDirs || []).map((d) => String(d).replace(/\/+$/, ''))
  const pages = []
  for (const [existingSlug, path] of Object.entries(wikiSlugs)) {
    if (typeof path !== 'string' || existingSlug === slug) continue
    const root = dirs.find((d) => path.startsWith(`${d}/`))
    const dirSegments = root ? path.slice(root.length + 1).split('/').slice(0, -1) : []
    const have = [...meaningWords(existingSlug), ...dirSegments.flatMap(meaningWords)]
    const hits = want.filter((w) => have.some((h) => meaningWordsMatch(w, h)))
    if (hits.length > 0) pages.push({ slug: existingSlug, path, hits })
  }
  const df = new Map(want.map((w) => [w, pages.filter((pg) => pg.hits.includes(w)).length]))
  const scored = pages.map((pg) => ({ ...pg, shared: pg.hits.reduce((n, w) => n + 1 / df.get(w), 0) }))
  scored.sort((a, b) => (b.shared - a.shared) || (b.hits.length - a.hits.length) || (a.path < b.path ? -1 : a.path > b.path ? 1 : 0))
  return scored.slice(0, MEANING_MATCH_MAX_CANDIDATES).map(({ slug: s, path }) => ({ slug: s, path }))
}

// What a cluster's nuggets cite: source paths, decision records (docs/decisions paths and DR-<n>
// ids, ids zero-stripped) and backticked spans. Pure; deduped in first-seen order.
function nuggetCitations(cluster) {
  const sources = []
  const drRefs = []
  const symbols = []
  const add = (list, v) => { if (v && !list.includes(v)) list.push(v) }
  for (const n of (cluster && cluster.nuggets) || []) {
    add(sources, String(n.source || '').replace(/\\/g, '/').replace(/^\.\//, ''))
    const text = String(n.content || '')
    for (const m of text.matchAll(/docs\/decisions\/[\w./-]+?\.md/g)) add(drRefs, m[0])
    for (const m of text.matchAll(/\bDR-0*(\d+)\b/g)) add(drRefs, `DR-${m[1]}`)
    for (const m of text.matchAll(/`([^`\n]{3,80})`/g)) add(symbols, m[1].trim())
  }
  return { sources, drRefs, symbols }
}

// The clusters no wiki page is named for, one per slug in first-seen order: the ones cited-record and meaning
// homing work on.
function homelessClusters(rawClusters, wikiSlugs) {
  const seen = new Set()
  const out = []
  for (const cluster of rawClusters) {
    const slug = slugifyTopic(cluster.topicKey)
    if (seen.has(slug)) continue
    seen.add(slug)
    if (wikiSlugs[slug] || findFuzzyWikiHome(slug, wikiSlugs)) continue
    out.push({ slug, cluster })
  }
  return out
}

// A candidate with facts lists capped headings and bullet lead-ins under its path; one without keeps the path-only line.
function meaningMatchBrief(slug, cluster, candidates, pageFacts = {}, forced = false) {
  const preview = (c) => {
    const f = (pageFacts && pageFacts[c.path]) || {}
    const clean = (s, n) => String(s).replace(/\s+/g, ' ').trim().slice(0, n)
    const heads = (f.headings || []).slice(0, MEANING_MATCH_PREVIEW_HEADINGS).map((h) => clean(h, MEANING_MATCH_PREVIEW_LEAD_CHARS * 2)).filter(Boolean)
    const leads = (f.bullet_leads || []).slice(0, MEANING_MATCH_PREVIEW_LEADS).map((l) => clean(l, MEANING_MATCH_PREVIEW_LEAD_CHARS)).filter(Boolean)
    return `- ${c.path}` +
      (heads.length ? `\n  headings: ${heads.join(' | ')}` : '') +
      (leads.length ? `\n  bullets: ${leads.join(' | ')}` : '')
  }
  const sample = (cluster.nuggets || []).slice(0, MEANING_MATCH_NUGGET_SAMPLE)
    .map((n) => `- ${String(n.content || '').replace(/\s+/g, ' ').slice(0, MEANING_MATCH_NUGGET_CHARS)}`).join('\n')
  return `Decide whether a new wiki page is a duplicate of an existing one.

New page topic: ${slug}
Sample of its knowledge nuggets:
${sample}

Candidate existing pages (their path shares a word with the topic):
${candidates.map(preview).join('\n')}

Where a candidate lists headings or bullets above, judge from those. For a candidate with only its path, Read ONLY its first ${MEANING_MATCH_HEAD_LINES} lines (Read with limit=${MEANING_MATCH_HEAD_LINES}): title and lead, never the whole page. If the new topic is the same subject as exactly one candidate, so its nuggets belong on that page rather than a page of their own, return that candidate's path verbatim, exactly as listed above, in "home". ${forced
    ? 'These nuggets cite no record or symbol, so they are lesson-shaped and are appended as one gotcha on an existing page, never a page of their own. "NEW" is not an option: return the one candidate whose subject is nearest.'
    : 'If none is the same subject, or two fit equally, return "NEW" in "home".'} A shared word alone is not a match; the subject must be the same. Put one sentence of why in "reason".`
}

// One batched call holds every homeless cluster that has candidates (split only past MEANING_MATCH_BATCH_MAX_CHARS of briefs);
// `ask(brief, label)` returns the forced-schema reply {answers: [{slug, home, reason}]}, each cluster's entry resolved
// and validated on its own. Returns {meaningHomes: {slug: path}, calls}. A throwing reply, or a cluster whose entry is
// missing, invalid or outside its candidates, is retried once (the still-unresolved clusters together, one more call) and then
// leaves that cluster homeless (it mints as before); a returned path outside the candidates is
// never trusted. Ahead of the stem search, `matches` (args.prepared.pageFacts: {homes: {slug: ranked paths},
// previews: {path: {headings, bullet_leads}}}) homes a cluster whose cited records exactly one page holds
// with no call (`cited` counts these), and several such pages
// become that cluster's candidates (capped) instead of the stem-sharing ones. A cluster of only
// KNOWLEDGE nuggets that cites no record or symbol and has candidates is forced: its brief withholds
// NEW and a NEW, failed or unresolvable reply homes on the first candidate; its slug is listed in
// `gotcha`, so the writer appends its nuggets as a gotcha.
async function homeByMeaning(rawClusters, wikiSlugs, wikiDirs, ask, logFn, matches = {}) {
  const meaningHomes = {}
  const jobs = []
  let cited = 0
  const gotcha = []
  const slugOfPath = Object.fromEntries(Object.entries(wikiSlugs).map(([s, p]) => [p, s]))
  const pageHits = (matches && matches.homes) || {}
  const previews = (matches && matches.previews) || {}
  for (const { slug, cluster } of homelessClusters(rawClusters, wikiSlugs)) {
    const hits = pageHits[slug] || []
    if (hits.length === 1) {
      meaningHomes[slug] = hits[0]
      cited++
      logFn(`homing: ${slug} -> ${hits[0]} (cited record)`)
      continue
    }
    const candidates = hits.length > 1
      ? hits.slice(0, MEANING_MATCH_MAX_CANDIDATES).map((path) => ({ slug: slugOfPath[path] || path.replace(/^.*\//, '').replace(/\.md$/, ''), path }))
      : meaningMatchCandidates(slug, wikiSlugs, wikiDirs)
    const nuggets = cluster.nuggets || []
    const refs = nuggetCitations(cluster)
    const forced = hits.length === 0 && nuggets.length > 0 && nuggets.every((n) => n.type === 'KNOWLEDGE') &&
      refs.drRefs.length === 0 && refs.symbols.length === 0
    if (candidates.length > 0) jobs.push({ slug, cluster, candidates, forced })
  }
  // A reply naming a candidate by absolute path, repo-relative path or slug resolves to it.
  const resolve = (home, candidates) => {
    const h = home.replace(/\\/g, '/').replace(/\.md$/, '')
    return candidates.find((c) => {
      const p = c.path.replace(/\.md$/, '')
      return h === p || h.endsWith(`/${p}`) || h === c.slug
    })
  }
  const failed = []
  const forceHome = ({ slug, candidates }, why) => {
    meaningHomes[slug] = candidates[0].path
    gotcha.push(slug)
    logFn(`homing: ${slug} -> ${candidates[0].path} (uncited knowledge, gotcha append: ${why})`)
  }
  const blocks = new Map(jobs.map((j) => [j, `${MEANING_MATCH_CLUSTER_MARK}${j.slug} ===\n${meaningMatchBrief(j.slug, j.cluster, j.candidates, previews, j.forced)}`]))
  const batchBrief = (batch) =>
    `Answer each cluster below on its own. Reply with one entry per cluster in "answers": {"slug": the slug on its CLUSTER line, verbatim, "home": ..., "reason": ...}. Each cluster has its own instructions.\n\n` +
    batch.map((j) => blocks.get(j)).join('\n\n')
  const batches = []
  for (const job of jobs) {
    const last = batches[batches.length - 1]
    if (last && last.chars + blocks.get(job).length <= MEANING_MATCH_BATCH_MAX_CHARS) {
      last.jobs.push(job)
      last.chars += blocks.get(job).length
    } else batches.push({ jobs: [job], chars: blocks.get(job).length })
  }
  let calls = 0
  for (const [b, batch] of batches.entries()) {
    let pending = batch.jobs
    const why = new Map()
    // An empty, thrown, missing or unresolvable entry is a failed check, never a "no match": the unresolved
    // clusters are retried once together, then reported in `failed` and minted as a new page.
    for (let attempt = 0; attempt < 2 && pending.length > 0; attempt++) {
      let reply = null
      calls++
      try {
        reply = await ask(batchBrief(pending), `homing-batch${batches.length > 1 ? `-${b + 1}` : ''}${attempt === 0 ? '' : '-retry'}`)
      } catch (e) {
        for (const j of pending) why.set(j, `call failed (${e && e.message})`)
        continue
      }
      const answers = new Map()
      for (const a of (reply && Array.isArray(reply.answers) ? reply.answers : [])) {
        if (a && typeof a.slug === 'string' && !answers.has(a.slug.trim())) answers.set(a.slug.trim(), a)
      }
      const unresolved = []
      for (const job of pending) {
        const { slug, candidates, forced } = job
        const entry = answers.get(slug)
        const home = entry && typeof entry.home === 'string' ? entry.home.trim() : ''
        if (home.toUpperCase() === 'NEW') {
          if (forced) forceHome(job, 'reply was NEW')
          continue
        }
        const hit = home && resolve(home, candidates)
        if (hit) {
          meaningHomes[slug] = hit.path
          if (forced) gotcha.push(slug)
          logFn(`homing: ${slug} -> ${hit.path} (${entry.reason || 'meaning match'})`)
          continue
        }
        why.set(job, !entry ? 'no entry in reply' : home ? `reply named '${home}', not a candidate` : 'empty reply')
        unresolved.push(job)
      }
      pending = unresolved
    }
    for (const job of pending) {
      const reason = why.get(job)
      failed.push({ slug: job.slug, reason })
      if (job.forced) forceHome(job, reason)
      else logFn(`homing: ${job.slug}: meaning-match check failed twice (${reason}) — mints as a new page`)
    }
  }
  return { meaningHomes, calls, failed, cited, gotcha }
}

function consolidateClusters(rawClusters, wikiSlugs, config) {
  // consolidateClusters is extracted by TEXT into an isolated `new Function(...)` eval scope by
  // the D3 regression test (no closure over this file's module-level consts survives that
  // extraction) — every value this function needs arrives via `config`, never a bare module-level
  // reference. SINGLETON_FLOOR/NEW_FILE_CAP are DELETED (chunk C4b — see the retirement comment
  // near DR146_MIN_STEM_LEN's declaration) and are not part of this config shape.
  const { runId, wikiDirs } = config
  const meaningHomes = config.meaningHomes || {}
  const gotchaSlugs = config.gotchaSlugs || []
  const totalInputNuggets = rawClusters.reduce((n, c) => n + c.nuggets.length, 0)

  // Step 1 — partition by disk reality: `homed` (slug matches an existing wiki file, passes
  // through unchanged — an additive merge, not shrapnel) vs `homeless` (no existing home,
  // candidate for coarsen/fold/cap below).
  const homed = []
  const homeless = []
  for (const cluster of rawClusters) {
    const slug = slugifyTopic(cluster.topicKey)
    const existingPath = wikiSlugs[slug] || findFuzzyWikiHome(slug, wikiSlugs) || meaningHomes[slug]
    if (existingPath) {
      const gotchaIds = !wikiSlugs[slug] && !findFuzzyWikiHome(slug, wikiSlugs) && gotchaSlugs.includes(slug)
        ? cluster.nuggets.map((n) => n.id) : []
      homed.push({ ...cluster, wikiPath: existingPath, bucket: 'homed', gotchaNuggetIds: gotchaIds })
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
  // Disjoint-file invariant: clusters homed to one wikiPath collapse into a single synth unit
  // (first cluster's topicKey is the unit key; mergedTopicKeys records every key it absorbed).
  const byPath = new Map()
  for (const c of [...homed, ...newClusters]) {
    const unit = byPath.get(c.wikiPath)
    if (!unit) {
      byPath.set(c.wikiPath, { ...c, mergedTopicKeys: [c.topicKey] })
      continue
    }
    unit.nuggets = [...unit.nuggets, ...c.nuggets]
    unit.sourceBatches = [...new Set([...(unit.sourceBatches || []), ...(c.sourceBatches || [])])]
    unit.mergedTopicKeys.push(c.topicKey)
    if (c.gotchaNuggetIds && c.gotchaNuggetIds.length) unit.gotchaNuggetIds = [...(unit.gotchaNuggetIds || []), ...c.gotchaNuggetIds]
  }
  const result = [...byPath.values()]

  const totalOutputNuggets = result.reduce((n, c) => n + c.nuggets.length, 0)
  if (totalOutputNuggets !== totalInputNuggets) {
    throw new Error(
      `consolidateClusters: nugget count not conserved (in=${totalInputNuggets}, out=${totalOutputNuggets})`
    )
  }

  return result
}

// One lesson, one page: a same-source, overlapping-wording nugget pair spread over two pages gets one
// owner page (fewer nuggets, ties by path); the other page links to it. A false pair costs only a hint.
// Pure, config-free: the test extracts it by text.
function crossPageRestatements(units, pathOf) {
  const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'is', 'are', 'be',
    'it', 'its', 'that', 'this', 'with', 'as', 'by', 'at', 'from', 'not', 'no', 'when', 'while'])
  const words = (s) => new Set(String(s).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2 && !STOP.has(w)))
  const bySource = new Map()
  units.forEach((u, ui) => {
    for (const n of u.nuggets || []) {
      if (!n || !n.source) continue
      if (!bySource.has(n.source)) bySource.set(n.source, [])
      bySource.get(n.source).push({ ui, id: n.id, w: words(n.content) })
    }
  })
  const rank = (ui) => [(units[ui].nuggets || []).length, pathOf(units[ui])]
  const owns = (a, b) => { const [x, y] = [rank(a), rank(b)]; return x[0] !== y[0] ? x[0] < y[0] : x[1] < y[1] }
  const out = new Map()
  for (const list of bySource.values()) {
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const [a, b] = [list[i], list[j]]
        if (a.ui === b.ui || pathOf(units[a.ui]) === pathOf(units[b.ui])) continue
        let shared = 0
        for (const w of a.w) if (b.w.has(w)) shared++
        const union = a.w.size + b.w.size - shared
        if (shared < 4 || union === 0 || shared / union < 0.3) continue
        const [owner, other] = owns(a.ui, b.ui) ? [a, b] : [b, a]
        const key = pathOf(units[other.ui])
        if (!out.has(key)) out.set(key, [])
        const rows = out.get(key)
        if (!rows.some((r) => r.nugget_id === other.id)) {
          rows.push({ nugget_id: other.id, owner_path: pathOf(units[owner.ui]), owner_nugget_id: owner.id })
        }
      }
    }
  }
  return out
}

// Curated-map resolution (C3/AC3) + homing override (C3/AC12) — only reached in invocation B
// (invocation A already returned above), where CURATED_TAGS is guaranteed set.
const { resolvedMap: HOMED_CURATED_TAGS, overrideCount: homingOverrideCount } = PREPARED_CLUSTERS
  ? { resolvedMap: {}, overrideCount: 0 }
  : applyHomingOverride(CURATED_TAGS, WIKI_SLUGS)
const droppedTags = []
// Prepared clusters already carry curation and homing, and their topic keys are the ones the synth
// payloads and apply_synth join on; they are never re-clustered here.
if (PREPARED_CLUSTERS) {
  for (const id of Array.isArray(PREPARED.dropped_nuggets) ? PREPARED.dropped_nuggets : []) {
    droppedTags.push({ tag: '(dropped in prepare)', id, reason: 'curation applied by prepare', drop_cause: null })
  }
}
const rawClusters = PREPARED_CLUSTERS ? PREPARED_CLUSTERS : clusterNuggets(scanResults, HOMED_CURATED_TAGS, droppedTags)

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

phase('homing')
const PAGE_FACTS = (loadedInput && loadedInput.pageFacts && typeof loadedInput.pageFacts === 'object') ? loadedInput.pageFacts : {}
const { meaningHomes: MEANING_HOMES, calls: meaningCalls, failed: MEANING_FAILED, cited: citedHomes, gotcha: GOTCHA_SLUGS } = PREPARED_CLUSTERS ? { meaningHomes: {}, calls: 0, failed: [], cited: 0, gotcha: [] } : await homeByMeaning(
  rawClusters, WIKI_SLUGS, WIKI_DIRS,
  // judgment-keeper: meaning-match homing — whether two page subjects are the same is a reading judgment.
  (brief, label) => agent(brief, {
    schema: MEANING_MATCH_SCHEMA,
    agentType: DISTILL_WRITER_TYPE,
    phase: 'homing',
    label,
    model: 'haiku',
  }),
  log, PAGE_FACTS)
log(`homing: ${citedHomes} homed by cited record, ${meaningCalls} meaning-match call(s), ${Object.keys(MEANING_HOMES).length} homed in all, ` +
  `${MEANING_FAILED.length} failed${MEANING_FAILED.length ? ` (${MEANING_FAILED.map((f) => f.slug).join(', ')})` : ''}`)
// A prepared cluster is already a synth unit: prepare homed it (wikiPath, homed) and the payloads were cut
// against that home, so no meaning-match call or consolidation may move it.
const allClusters = PREPARED_CLUSTERS
  ? rawClusters.map((c) => ({ ...c, bucket: c.homed ? 'homed' : 'new', mergedTopicKeys: [c.topicKey] }))
  : consolidateClusters(rawClusters, WIKI_SLUGS, {
      runId: RUN_ID,
      wikiDirs: WIKI_DIRS,
      meaningHomes: MEANING_HOMES,
      gotchaSlugs: GOTCHA_SLUGS,
    })
const homedCount = allClusters.filter((c) => c.bucket === 'homed').length
const newCount = allClusters.filter((c) => c.bucket === 'new').length
log(`consolidation: ${rawClusters.length} raw -> ${homedCount} homed + ${newCount} new ` +
  `(no-misc: curation already decided upstream which tags survive, per plan chunk C4)`)

if (allClusters.length === 0) {
  return {
    phase_reached: 'scan',
    halted: 'zero-clusters-after-scan',
    scan_results: scanResults,
    failed_batch_ids: failedBatchIds,
    plan_triage: PLAN_TRIAGE_REPORT,
    empty_content_batch_ids: emptyContentBatchIds,
    malformed_tag_batch_ids: malformedTagBatchIds,
    malformed_tag_nugget_count: malformedTagNuggetCount,
  }
}

// Pre-fire ceiling: the dispatch estimate is computed from the cluster count alone, before the
// first post-scan dispatch (source-hash, candidates, synth).
const SYNTH_PAYLOADS = synthPayloadsOf(PREPARED)
if (SYNTH_PAYLOADS === null) {
  return {
    phase_reached: 'consolidate',
    halted: 'prepared-synth-missing',
    run_id: RUN_ID,
    detail: 'distill-harvest: args.prepared.synth carries no payloads or schema — re-run distill_mechanical.py prepare and pass its prepared.json as args.prepared',
  }
}
const dispatchEstimate = SYNTH_PAYLOADS.length
if (dispatchEstimate > AGENT_CEILING) {
  return {
    phase_reached: 'consolidate',
    halted: 'agent-ceiling-exceeded',
    run_id: RUN_ID,
    dispatch_estimate: dispatchEstimate,
    agent_ceiling: AGENT_CEILING,
    clusters_total: allClusters.length,
    resume_hint: 'Re-invoke with args.agentCeiling >= dispatch_estimate, or narrow the scope.',
  }
}

// Skip-unchanged: the driver hashed every cluster's source files against the hashes the last
// promote stored (args.prepared.sourceHashes, keyed by topic); a topic with no hash is never skipped.
phase('source-hash')
const sourceHashes = (PREPARED && PREPARED.sourceHashes && typeof PREPARED.sourceHashes === 'object') ? PREPARED.sourceHashes : {}
const unhashedTopics = allClusters.filter((c) => !sourceHashes[c.topicKey]).map((c) => c.topicKey)
if (unhashedTopics.length > 0) {
  log(`source-hash: ${unhashedTopics.length} of ${allClusters.length} topic(s) have no prepared hash — none of them is skipped as unchanged`)
}
const unchangedClusters = allClusters.filter((c) => (sourceHashes[c.topicKey] || {}).unchanged === true)
const clusters = allClusters.filter((c) => !unchangedClusters.includes(c))
const topicSourceHashes = Object.fromEntries(
  allClusters.map((c) => [c.topicKey, (sourceHashes[c.topicKey] || {}).sha256 || null]))
if (unchangedClusters.length > 0) {
  log(`source-hash: ${unchangedClusters.length} topic(s) unchanged since their last promote — skipped: ` +
    unchangedClusters.map((c) => c.topicKey).join(', '))
}
// Unchanged topics were harvested by an earlier run; their nuggets count as harvested.
const unchangedResults = unchangedClusters.map((c) => ({
  topic_key: c.topicKey,
  wiki_path: c.wikiPath || '',
  op: 'skipped',
  reason: 'unchanged-source-hash',
  dispositions: (c.nuggets || []).map((n) => ({ nugget_id: n.id, op: 'SKIP', reason: 'unchanged-source-hash', prior_harvest: true })),
}))

// ---------------------------------------------------------------------------------------------
// Wave 2 — batched distill-writer agents, each owning a disjoint set of docs/wiki/<topic>.md
// targets, written as staged copies. resumeFromRunId re-runs only the synths that failed on a prior attempt (the Workflow
// runtime resumes cached-successful phases/agents automatically on `resumeFromRunId`; each
// agent() call here is independently cacheable per the tool's same-script+same-args contract).
// ---------------------------------------------------------------------------------------------

function slugifyTopic(topicKey) {
  return topicKey
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

// Agent-echoed topic_key joins compare canonical slugs: Sonnet may echo `a_b` for `a-b`.
// Stamps the dispatching key onto an agent result so joins never trust an agent-echoed key.
function stampKey(result, field, key) {
  return result ? { ...result, [field]: key } : result
}

function sameTopic(a, b) {
  return slugifyTopic(String(a)) === slugifyTopic(String(b))
}

// ---------------------------------------------------------------------------------------------
// Candidate-restatement check — computed AHEAD OF the synth agent by the driver
// (`distill_mechanical.py prepare` runs bin/distill-candidates-batch.py) and handed in as
// args.prepared.candidates. The Wave-2 synth agent reads the field; it never runs a command to
// obtain it. Records: [{topic_key, wiki_path, candidate_restatements: [{line, excerpt}]}].
// ---------------------------------------------------------------------------------------------

phase('candidates')
const candidatesResults = (PREPARED && Array.isArray(PREPARED.candidates)) ? PREPARED.candidates : []
if (candidatesResults.length === 0) {
  log('candidates: no prepared candidates — every cluster degrades to an empty candidate list' +
    (PREPARED && PREPARED.candidates_status ? ` (driver status: ${PREPARED.candidates_status})` : ''))
}

// A topic with no prepared record degrades to an empty candidate list for that cluster (via the
// Map lookup's `|| []` fallback inside buildCandidatesByTopic below) — never a block, and never
// a reason for the Wave-2 synth agent to run the CLI itself to backfill the gap. A named
// function so this fallback/sanity-check logic is unit-testable outside the Workflow sandbox.
//
// `wiki_path` rides beside `topic_key`/`candidate_restatements` but is never itself consumed
// downstream — used here only as a sanity cross-check against the target this wave computed for
// the same cluster, to catch a record prepared against a stale or different target.
function buildCandidatesByTopic(candidatesResultsIn, clustersIn, wikiSlugsIn, wikiDirsIn, logFn) {
  return new Map(
    candidatesResultsIn.map((r) => {
      const matchingCluster = clustersIn.find((c) => sameTopic(c.topicKey, r.topic_key))
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
      return [slugifyTopic(r.topic_key), r.candidate_restatements || []]
    })
  )
}

const candidatesByTopic = buildCandidatesByTopic(candidatesResults, clusters, WIKI_SLUGS, WIKI_DIRS, log)

phase('synth')

// D2: target resolved from disk reality (WIKI_SLUGS), not a topicKey-keyed Phase-0 guess.
// D3: honor a target the consolidation pass already set (homed merges, the misc bucket) —
// only fall back to fresh disk-resolution for a genuinely new cluster.
const wikiPathOf = (cluster) =>
  cluster.wikiPath || WIKI_SLUGS[slugifyTopic(cluster.topicKey)] || `${WIKI_DIRS[0]}/${slugifyTopic(cluster.topicKey)}.md`

// judgment-keeper: single-turn synth — merges the prepared nuggets into page ops; no tools.
const synthReturns = (await parallel(
  SYNTH_PAYLOADS.map((payload, i) => () =>
    agent(synthBriefFor(payload), {
      schema: synthSchemaFor(PREPARED.synth, i),
      agentType: SYNTH_AGENT_TYPE,
      phase: 'synth',
      label: `synth-${i + 1}`,
      model: SYNTH_MODEL,
    })
  ),
  { concurrency: CONCURRENCY_CAP }
))
const failedSynthCalls = synthReturns.map((ret, i) => (ret ? null : `synth-${i + 1}`)).filter(Boolean)
const synthResults = deriveSynthResults(
  clusters, synthReturns.filter(Boolean), SYNTH_PAYLOADS, RUN_ID, wikiPathOf,
  RAW_ARGS_INPUT.spliceReport && typeof RAW_ARGS_INPUT.spliceReport === 'object' ? RAW_ARGS_INPUT.spliceReport : null)
const deferredTopics = (PREPARED.synth.deferred_topics || [])
const synthOutcome = synthOutcomeOf(clusters, synthResults, SYNTH_PAYLOADS, synthReturns.filter(Boolean))
log(`synth: ${synthOutcome.topics_with_ops}/${synthOutcome.topics_sent} topic(s) returned ops or records, ` +
  `${synthOutcome.no_ops_topics} returned no ops${synthOutcome.no_ops_topics ? ` (${synthOutcome.no_ops_topic_keys.map((k) => `${k}: ${synthOutcome.no_ops_reasons[k]}`).join(', ')})` : ''}; ` +
  `${synthOutcome.covered}/${synthOutcome.assigned} nuggets covered`)

if (failedSynthCalls.length > 0) {
  // A call that returned nothing is handled by re-invoking this Workflow with resumeFromRunId set to
  // THIS invocation's Workflow-tool run id (`wf_...`, from the tool result): the scan replays from the
  // journal and only the failed synth call re-runs.
  return {
    phase_reached: 'synth',
    halted: 'synth-partial-failure',
    run_id: RUN_ID,
    concurrency_cap: CONCURRENCY_CAP,
    scan_results: scanResults,
    failed_batch_ids: failedBatchIds,
    plan_triage: PLAN_TRIAGE_REPORT,
    empty_content_batch_ids: emptyContentBatchIds,
    malformed_tag_batch_ids: malformedTagBatchIds,
    malformed_tag_nugget_count: malformedTagNuggetCount,
    clusters_attempted: clusters.length,
    synth_results: synthResults,
    failed_synth_calls: failedSynthCalls,
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
  const resultsByTopic = new Map(results.map((r) => [slugifyTopic(r.topic_key), r]))
  const gaps = []
  for (const cluster of clusters) {
    const result = resultsByTopic.get(slugifyTopic(cluster.topicKey))
    if (!result) continue // failed synth — already reported via failedTopicKeys above
    const coveredIds = new Set((result.dispositions || []).map((d) => d.nugget_id))
    const uncoveredNuggets = cluster.nuggets.filter((n) => !coveredIds.has(n.id))
    if (uncoveredNuggets.length > 0) {
      gaps.push({ topicKey: cluster.topicKey, wikiPath: result.wiki_path, uncoveredNuggets })
    }
  }
  return gaps
}

// DECISION nuggets that have a disposition but ended somewhere other than a decision record
// (nuggets with no disposition at all are findCoverageGaps' business).
function findFoldedDecisions(clusters, results) {
  const resultsByTopic = new Map(results.map((r) => [slugifyTopic(r.topic_key), r]))
  const isRecord = (d) => d.op === 'CREATE_DR'
  const isLegalSkip = (d) => d.op === 'SKIP' && typeof d.reason === 'string' &&
    (d.reason.startsWith('DR-ALLOCATOR-UNAVAILABLE') || d.reason.startsWith('DR-EXISTS ') ||
      d.reason.startsWith('FLEET-RULE-OWNED-ELSEWHERE '))
  const folded = []
  for (const cluster of clusters) {
    const result = resultsByTopic.get(slugifyTopic(cluster.topicKey))
    if (!result) continue
    const byId = new Map((result.dispositions || []).map((d) => [d.nugget_id, d]))
    const foldedNuggets = cluster.nuggets.filter((n) => {
      if (n.type !== 'DECISION') return false
      const d = byId.get(n.id)
      return d !== undefined && !isRecord(d) && !isLegalSkip(d)
    })
    if (foldedNuggets.length > 0) {
      folded.push({ topicKey: cluster.topicKey, wikiPath: result.wiki_path, foldedNuggets })
    }
  }
  return folded
}

phase('coverage-gate')
const totalAssignedNuggets = clusters.reduce((n, c) => n + c.nuggets.length, 0)
const coverageGaps = findCoverageGaps(clusters, synthResults)
const foldedDecisions = findFoldedDecisions(clusters, synthResults)
const totalUncoveredNuggets = coverageGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0)
const unsynthesizedTopicKeys = clusters
  .filter((c) => !synthResults.some((r) => sameTopic(r.topic_key, c.topicKey)))
  .map((c) => c.topicKey)
log(`coverage gate: ${totalAssignedNuggets - totalUncoveredNuggets}/${totalAssignedNuggets} ` +
  `nuggets covered (${coverageGaps.length} gap cluster(s)` +
  `${coverageGaps.length ? ': ' + coverageGaps.map((g) => `${g.topicKey} [${g.uncoveredNuggets.map((n) => n.id).join(', ')}]`).join('; ') : ''}); ` +
  `${foldedDecisions.reduce((n, f) => n + f.foldedNuggets.length, 0)} DECISION nugget(s) folded; ` +
  `${unsynthesizedTopicKeys.length} topic(s) without a synth entry` +
  `${unsynthesizedTopicKeys.length ? ' (' + unsynthesizedTopicKeys.join(', ') + ')' : ''} ` +
  `(${deferredTopics.length} deferred to the next run)`)

const remainingGaps = coverageGaps
const foldedUnresolved = foldedDecisions
if (foldedUnresolved.length > 0) {
  log(`coverage gate: DECISION nugget(s) still folded after re-synth — ` +
    foldedUnresolved.flatMap((f) => f.foldedNuggets.map((n) => n.id)).join(', '))
}
if (remainingGaps.length > 0) {
  log(`coverage gate: ${remainingGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0)} ` +
    `nugget(s) uncovered by any landed op or record — ` +
    `${remainingGaps.map((g) => `${g.topicKey} [${g.uncoveredNuggets.map((n) => n.id).join(', ')}]`).join('; ')}`)
}

// ---------------------------------------------------------------------------------------------
// Staged promote — the Workflow cannot exec, so it stops here with the promote manifest, whose
// synth_results are the raw synth returns. The EM runs
// `distill_mechanical.py finalize --manifest <promote_manifest> --no-scratch --no-archive`
// (cite-checked splice into staged pages, collision check, then an atomic swap with rollback or an
// untouched tree) and re-invokes this script with args.promoted set to the promoted target list and
// args.spliceReport set to the report's phases['synth-splice']. Later phases read the promoted pages
// and the 3d citation writes land on them, so promotion must precede them.
// ---------------------------------------------------------------------------------------------
phase('promote')
const promoteManifest = buildPromoteManifest(RUN_ID, synthResults, synthReturns.filter(Boolean), topicSourceHashes)
const promotedByDriver = Array.isArray(RAW_ARGS_INPUT.promoted)
if (promoteManifest.synth_results.length > 0 && !promotedByDriver) {
  return {
    phase_reached: 'promote-ready',
    run_id: RUN_ID,
    promote_manifest: { ...promoteManifest, wikiDirs: WIKI_DIRS },
    synth_results: synthResults,
    synth_outcome: synthOutcome,
    deferred_topics: deferredTopics,
    skipped_unchanged: unchangedClusters.map((c) => c.topicKey),
    residue_scan: RESIDUE_SCAN,
    resume_hint: 'Run distill_mechanical.py finalize --manifest <promote_manifest> --no-scratch --no-archive; on exit 0 finalize has written promoted.json and splice-report.json (finalize-report leg2.promoted_path, leg2.splice_report_path); the EM commits finalize-report commit_paths (promoted pages plus the promoted run watermark); run claude-klabauter distill.launch_args with {leg: 2, run_id, repo_root, promoted_path, splice_report_path} and re-invoke this SAME script from the launch-args-leg2.json it writes (it carries args.promoted and args.spliceReport), with resumeFromRunId set to this Workflow-tool runId (wf_...). On a halt the working tree is untouched and staged files remain under the run dir staged/.',
  }
}
const promoteResult = { status: 'ok', promoted: promotedByDriver ? RAW_ARGS_INPUT.promoted : [], error: '' }
log(`promote: ${promoteResult.promoted.length} staged file(s) moved into place; ${unchangedClusters.length} unchanged topic(s) skipped`)

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
for (const r of [...synthResults, ...unchangedResults]) {
  for (const d of r.dispositions || []) {
    // Non-SKIP wins: a nugget carried by two dispositions is harvested if either one kept it,
    // and last-write-wins would let an incidental SKIP mask a real integration.
    const prior = dispositionOpByNuggetId.get(d.nugget_id)
    if (prior && prior !== 'SKIP') continue
    dispositionOpByNuggetId.set(d.nugget_id, d.prior_harvest ? 'PRIOR_HARVEST' : d.op)
  }
}
// A nugget no landed op or record cites (deferred topic, unsynthesized topic, rejected cite) was never
// harvested: its artifact is SKIP, never EPHEMERAL, so the deletion pass cannot take it.
const unharvestedNuggetIds = new Set([
  ...clusters.flatMap((c) => c.nuggets.map((n) => n.id)).filter((id) => !dispositionOpByNuggetId.has(id)),
  ...RESIDUE_NUGGET_IDS,
])

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

const CLASSIFIED_FILES = classifiedFilesOf(PREPARED)
for (const batch of BATCHES) {
  for (const path of batch.files) {
    // A scanner's fate line alone is not a review: one that defers a dense file "to a later pass"
    // returns prose and no nuggets, and no later pass exists. Only a nugget of any type settles it.
    // A file prepare classified is reviewed: its nuggets or its recorded fate settle it.
    const classified = CLASSIFIED_FILES.has(path)
    const scanned = classified || !failedBatchIds.includes(batch.batchId)
    const touched = classified || (nuggetIdsBySource.get(path) || []).length > 0
    const unharvested = (nuggetIdsBySource.get(path) || []).some((id) => unharvestedNuggetIds.has(id))
    const disposition = (!scanned || !touched)
      ? 'SKIP'
      : (nuggetIdsBySource.get(path) || []).some((id) => {
          const op = dispositionOpByNuggetId.get(id)
          return op && op !== 'SKIP'
        })
        ? 'DISTILLED'
        : unharvested
          ? 'SKIP'
          : 'EPHEMERAL'
    // Why a SKIP row is SKIP: only the first cause is a batch that never scanned.
    const skipCause = disposition !== 'SKIP'
      ? undefined
      : !scanned
        ? 'batch-never-scanned'
        : !touched
          ? 'no-nuggets-no-classification'
          : 'nuggets-not-harvested'

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

    distillationLogRows.push(skipCause ? { path, disposition, skip_cause: skipCause, fate } : { path, disposition, fate })
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
//     DISTILL_WRITER_TYPE role every other non-Bash wave here uses).
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

Then apply the reviewer's own ledger dispositions. The sidecar's \`findings_ledger:\` frontmatter
key is only a one-line summary ({rows, applied, em_rejected, suspended, verified_at}); the
per-finding rows are the JSON array under the sidecar body's \`## Findings Ledger\` heading, keyed
by finding id (verified by \`review-findings-ledger verify\`, claude-klabauter
coordinator_core/ops/review_findings_ledger.py). Read that array and index it by id. Then:
  - a row with no \`status\` key -> ELIGIBLE (applied and verified)
  - \`status: em-rejected\` (carries a \`reason\`) -> INELIGIBLE, skip
  - \`status: suspended\` -> INELIGIBLE, skip
  - a finding in no row, or a sidecar with no \`## Findings Ledger\` array
    -> ELIGIBLE (predates the ledger, or verify has not yet run)

Do NOT look for a \`## Integrator Dispositions\` block or a per-finding \`disposition:\` field.
Nothing writes either any more. A read keyed on them finds nothing, excludes nothing, and
silently counts every rejected verdict as convergence evidence — the exact outcome this
exclusion exists to prevent.

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

const JUDGMENT_CORPUS_SCHEMA = {
  type: 'object',
  required: ['sidecars_seen', 'clusters'],
  properties: {
    sidecars_seen: { type: 'integer' },
    clusters: {
      type: 'array',
      items: {
        type: 'object',
        required: ['topicCluster', 'verdictDirection', 'liveSidecarPaths'],
        properties: {
          topicCluster: { type: 'string' },
          verdictDirection: { type: 'string', enum: ['forbid', 'require', 'prefer', 'avoid'] },
          liveSidecarPaths: { type: 'array', items: { type: 'string' } },
          existingJudgmentEntry: { type: ['string', 'null'] },
        },
      },
    },
  },
}

// Input clusters win; else the scout's. A scout that returned (zero clusters included) is 'ran';
// no input and no scout result is 'unavailable'.
function resolveJudgmentClusters(inputClusters, scoutResult) {
  if (Array.isArray(inputClusters) && inputClusters.length > 0) {
    return { clusters: inputClusters, cluster_source: 'input', sidecars_seen: 0, status: 'ran' }
  }
  if (scoutResult && Array.isArray(scoutResult.clusters)) {
    return {
      clusters: scoutResult.clusters,
      cluster_source: 'in-run-scout',
      sidecars_seen: Number.isInteger(scoutResult.sidecars_seen) ? scoutResult.sidecars_seen : 0,
      status: 'ran',
    }
  }
  return { clusters: [], cluster_source: 'none', sidecars_seen: 0, status: 'unavailable' }
}

const judgmentCorpusBrief = () => COMMON + `

You are a Sonnet judgment-corpus scout (Phase 2.5 of the /distill harvest Workflow). Read-only:
write nothing, dispatch no nested sub-agents.

Plans in this run's batch files: ${JSON.stringify(BATCHES.flatMap((b) => (b && b.files) || []))}

1. Locate reviewer sidecars by content, never by filename: files whose frontmatter carries a
   \`findings_ledger:\` key, under .coordinator-local/subagent-share/ (one directory per session),
   .coordinator-local/plan-sidecars/, docs/plans/ (and its YYYY-MM/ shards) and archive/specs/, plus any the repo keeps
   beside a plan. Count them all as sidecars_seen.
2. Join a sidecar to a plan by its \`target_plan:\` or \`plan:\` frontmatter, compared on the plan's
   filename stem (an archived plan's sidecar still names its docs/plans/ path). A sidecar naming
   no plan counts in sidecars_seen and contributes to no cluster.
3. List docs/wiki/codebase-judgment/*.md for existing entries.
4. Per-finding status lives in the JSON array under the sidecar's \`## Findings Ledger\` heading: a
   row with no \`status\` key is applied; \`em-rejected\` and \`suspended\` rows are ineligible.
   Exclude mechanical/formatting and docs-checker-class findings.
5. Group eligible architectural findings by claim-topic and verdict direction. Return one cluster
   per group: topicCluster (claim-topic noun), verdictDirection (forbid|require|prefer|avoid),
   liveSidecarPaths (the sidecars contributing), existingJudgmentEntry (matching entry path or
   null). Return {sidecars_seen, clusters}.`

// The scout dispatches only when prepare's mechanical precheck (distill_mechanical.py
// judgment_precheck) says a proposal is possible; an absent precheck is no evidence, so no dispatch.
// `threshold` is the run's effective MIN_CONVERGENCE: prepare only sees the input file's value, so a
// --min-convergence flag lower than the precheck's own threshold is re-applied to its plan count.
function judgmentPrecheckSaysDispatch(precheck, threshold) {
  if (!precheck || typeof precheck !== 'object') return false
  if (precheck.dispatch === true) return true
  return Number.isInteger(threshold) && threshold > 0 && precheck.distinct_eligible_plans >= threshold
}

// The sidecar count prepare's mechanical precheck found; 0 when the precheck is absent or carries none.
function judgmentPrecheckSidecars(precheck) {
  return precheck && typeof precheck === 'object' && Number.isInteger(precheck.sidecars_seen) ? precheck.sidecars_seen : 0
}

let judgmentScout = null
if (!(Array.isArray(JUDGMENT_CLUSTERS) && JUDGMENT_CLUSTERS.length > 0) &&
    !judgmentPrecheckSaysDispatch(loadedInput && loadedInput.judgmentPrecheck, MIN_CONVERGENCE)) {
  const pc = loadedInput && loadedInput.judgmentPrecheck
  judgmentScout = { sidecars_seen: judgmentPrecheckSidecars(pc), clusters: [] }
  log('judgment-mining: scout skipped (no dispatch) — ' + (pc && typeof pc === 'object'
    ? `precheck found ${pc.distinct_eligible_plans} eligible plan(s) < min_convergence=${MIN_CONVERGENCE} and no existing entry to increment`
    : 'no judgmentPrecheck in the prepared input'))
}
if (!(Array.isArray(JUDGMENT_CLUSTERS) && JUDGMENT_CLUSTERS.length > 0) && judgmentScout === null) {
  // judgment-keeper: judgment corpus scout — groups live reviewer sidecars by claim topic.
  judgmentScout = (await parallel(
    [() => agent(judgmentCorpusBrief(), {
      schema: JUDGMENT_CORPUS_SCHEMA,
      agentType: DISTILL_WRITER_TYPE,
      phase: 'judgment-mining-2-5',
      label: 'judgment-corpus',
      model: 'sonnet',
    })],
    { concurrency: 1 }
  )).filter(Boolean)[0] || null
}
const judgmentResolved = resolveJudgmentClusters(JUDGMENT_CLUSTERS, judgmentScout)
const JUDGMENT_RUN_CLUSTERS = judgmentResolved.clusters

let judgmentResults = []
if (JUDGMENT_RUN_CLUSTERS.length > 0) {
  // judgment-keeper: per-cluster judgment mining — cross-spec convergence is a reading judgment.
  judgmentResults = (await parallel(
    JUDGMENT_RUN_CLUSTERS.map((cluster) => () =>
      agent(judgmentBriefFor(cluster), {
        schema: JUDGMENT_SCHEMA,
        agentType: DISTILL_WRITER_TYPE,
        phase: 'judgment-mining-2-5',
        label: `judgment-${slugifyTopic(cluster.topicCluster)}`,
        model: 'sonnet',
      }).then((r) => stampKey(r, 'topic_cluster', cluster.topicCluster))
    ),
    { concurrency: CONCURRENCY_CAP }
  )).filter(Boolean)

  const failedJudgmentClusters = JUDGMENT_RUN_CLUSTERS
    .map((c) => c.topicCluster)
    .filter((topicCluster) => !judgmentResults.some((r) => r.topic_cluster === topicCluster))
  if (failedJudgmentClusters.length > 0) {
    log(`judgment-mining: ${failedJudgmentClusters.length}/${JUDGMENT_RUN_CLUSTERS.length} cluster(s) ` +
      `failed to return a result: ${failedJudgmentClusters.join(', ')}`)
  }
  log(`judgment-mining: ${judgmentResults.length}/${JUDGMENT_RUN_CLUSTERS.length} cluster(s) reported ` +
    `(min_convergence=${MIN_CONVERGENCE}) — ` +
    `${judgmentResults.filter((r) => r.action === 'new-entry').length} new-entry, ` +
    `${judgmentResults.filter((r) => r.action === 'increment-existing').length} increment-existing, ` +
    `${judgmentResults.filter((r) => r.action === 'no-convergence' || r.action === 'no-change').length} no-op`)
} else if (judgmentResolved.status === 'unavailable') {
  log('judgment-mining: no judgmentClusters supplied and the judgment-corpus scout returned nothing — ' +
    'phase reports unavailable, not zero-proposals ("looked at nothing" != "found nothing")')
} else {
  log(`judgment-mining: ${judgmentResolved.cluster_source} produced zero clusters ` +
    `(sidecars_seen=${judgmentResolved.sidecars_seen}) — nothing to mine`)
}

const judgmentMining = {
  min_convergence: MIN_CONVERGENCE,
  clusters_processed: JUDGMENT_RUN_CLUSTERS.length,
  cluster_source: judgmentResolved.cluster_source,
  sidecars_seen: judgmentResolved.sidecars_seen,
  scratch_path: JUDGMENT_SCRATCH_PATH,
  proposals: judgmentResults,
  status: judgmentResolved.status,
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

// Precedence: curated file, then input file, then args. A `topicKeys` entry matching no cluster of
// this run is dropped and reported: it would send a 3a agent to a wiki path nothing wrote.
const SUPPLIED_CONTRADICTION_CLUSTERS = (loadedCurated && loadedCurated.contradictionClusters) ||
  (loadedInput && loadedInput.contradictionClusters) ||
  RAW_ARGS_INPUT.contradictionClusters || []
const unmatchedTopicKeys = []
const CONTRADICTION_CLUSTERS = SUPPLIED_CONTRADICTION_CLUSTERS.map((c) => {
  const kept = []
  const inRun = (key) => clusters.some((cl) =>
    sameTopic(key, cl.topicKey) || (cl.mergedTopicKeys || []).some((mk) => sameTopic(key, mk)))
  for (const key of c.topicKeys || []) {
    // A tag the curation merged away has no cluster of its own; it stands for its merge target.
    const merged = Object.entries(HOMED_CURATED_TAGS || {}).find(([tag, v]) =>
      v && v.verdict === 'merge' && v.merge_target && sameTopic(key, tag))
    const resolved = inRun(key) ? key : (merged && inRun(merged[1].merge_target) ? merged[1].merge_target : null)
    if (resolved === null) unmatchedTopicKeys.push(key)
    else if (!kept.some((k) => sameTopic(k, resolved))) kept.push(resolved)
  }
  return { ...c, topicKeys: kept }
})

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
  const synthed = synthResults.find((r) => sameTopic(r.topic_key, topicKey))
  if (synthed) return synthed.wiki_path
  const matchingCluster = clusters.find((c) => sameTopic(c.topicKey, topicKey))
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
let contradictionStatus = 'none'
if (CONTRADICTION_CLUSTERS.length > 0) {
  const multiTopicClusters = CONTRADICTION_CLUSTERS.filter((c) => (c.topicKeys || []).length >= 2)
  const singleTopicClusters = CONTRADICTION_CLUSTERS.filter((c) => (c.topicKeys || []).length < 2)

  // judgment-keeper: contradiction detection — comparing prose claims for conflict.
  const dispatchedResults = (await parallel(
    multiTopicClusters.map((cluster) => () =>
      agent(contradictionBriefFor(cluster), {
        schema: CONTRADICTION_SCHEMA,
        agentType: DISTILL_WRITER_TYPE,
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
  log('contradiction-detection: no contradiction clusters in this run — status none, nothing to compare')
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
unresolvable entry surfaces in the returned opus_escalation object; a fabricated resolution does not.`

  // judgment-keeper: escalation — resolving an unresolvable contradiction.
  const [opusResult] = (await parallel(
    [() => agent(escalationBrief, {
      schema: ESCALATION_SCHEMA,
      agentType: DISTILL_WRITER_TYPE,
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

    // judgment-keeper: fidelity check — verifies the resolution cited every flagged source.
    const [fidelity] = (await parallel(
      [() => agent(fidelityBrief, {
        schema: FIDELITY_SCHEMA,
        agentType: DISTILL_WRITER_TYPE,
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
      'unresolved in the returned object rather than blocking the run.')
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
  unmatched_topic_keys: unmatchedTopicKeys,
  results: contradictionResults,
  status: contradictionStatus,
  total_unresolvable_contradictions: totalUnresolvableContradictions,
  cross_cluster_candidates: crossClusterCandidates,
}

// ---------------------------------------------------------------------------------------------
// Phase 3b — Decision-record dedup, no dispatch. Finalize (distill_mechanical.py apply_synth)
// matches each decision record's title and slug against args.prepared.drIndex: a match is not
// minted and its nuggets read DR-EXISTS in the splice report this run's dispositions come from.
// This phase reports the minted targets and the DR-EXISTS skips; it never throws.
//
// CRITICAL FAILURE MODE (PIPELINE.md § Phase 3b): DECISION nuggets that ended without a
// record, a DR-EXISTS skip or a fleet-rule skip is `failure`/`failure_detail` on the returned
// result, surfaced to Phase 4 and never a halt.
// ---------------------------------------------------------------------------------------------
phase('phase-3b')

// Targets absent from the paths finalize minted; separators compared as '/'.
function reconcileDrTargets(targets, drFilesFound) {
  const norm = (p) => String(p).replace(/\\/g, '/')
  const found = new Set((drFilesFound || []).map(norm))
  return (targets || []).filter((t) => !found.has(norm(t)))
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
    .map((d) => ({ nugget_id: d.nugget_id, reason: d.reason || null, target: typeof d.target === 'string' ? d.target : null, topic_key: r.topic_key, wiki_path: r.wiki_path }))
)

const decisionNuggets = clusters.flatMap((c) => c.nuggets.filter((n) => n.type === 'DECISION'))
const allDispositions = synthResults.flatMap((r) => r.dispositions || [])
const dispositionByNuggetId = new Map(allDispositions.map((d) => [d.nugget_id, d]))
const isSkipWith = (d, prefix) => d !== undefined && d.op === 'SKIP' && typeof d.reason === 'string' && d.reason.startsWith(prefix)
const allocatorUnavailableCount = allDispositions.filter((d) => isSkipWith(d, 'DR-ALLOCATOR-UNAVAILABLE')).length
const existingRecordSkips = decisionNuggets
  .map((n) => dispositionByNuggetId.get(n.id))
  .filter((d) => isSkipWith(d, 'DR-EXISTS '))
const fleetRuleSkips = decisionNuggets
  .map((n) => dispositionByNuggetId.get(n.id))
  .filter((d) => isSkipWith(d, 'FLEET-RULE-OWNED-ELSEWHERE '))
const unrecordedDecisionCount = decisionNuggets.length - existingRecordSkips.length - fleetRuleSkips.length

let phase3b = { dr_dedup: [], failure: false, failure_detail: null, status: 'skipped' }
// BEGIN phase-3b skip branch
if (createDrDispositions.length === 0) {
  if (decisionNuggets.length === 0) {
    phase3b = {
      dr_dedup: [],
      failure: false,
      failure_detail: 'This run held no decision-shaped content: zero DECISION nuggets and zero CREATE_DR ' +
        'dispositions.',
      status: 'skipped-empty',
    }
  } else if (unrecordedDecisionCount === 0) {
    phase3b = {
      dr_dedup: [],
      failure: false,
      failure_detail: `All ${decisionNuggets.length} DECISION nugget(s) are recorded or owned elsewhere: ` +
        [
          ...existingRecordSkips.map((d) => d.reason.slice('DR-EXISTS '.length).trim()),
          ...fleetRuleSkips.map((d) => `fleet rule owned by ${d.reason.slice('FLEET-RULE-OWNED-ELSEWHERE '.length).trim()}`),
        ].join(', '),
      status: 'skipped-empty',
    }
  } else {
    phase3b = {
      dr_dedup: [],
      failure: true,
      failure_detail: `${unrecordedDecisionCount} of ${decisionNuggets.length} DECISION nugget(s) ended without a ` +
        'decision record (folded, allocator-skipped, or undisposed) and no CREATE_DR disposition exists this run.',
      status: 'skipped-empty',
    }
  }
// END phase-3b skip branch
  log(`phase-3b: SKIPPED (no dispatch) — ${phase3b.failure_detail}`)
} else {
  const mergedByRecord = new Map()
  for (const d of existingRecordSkips) {
    const path = d.reason.slice('DR-EXISTS '.length).trim()
    mergedByRecord.set(path, [...(mergedByRecord.get(path) || []), d.nugget_id])
  }
  phase3b = {
    dr_dedup: [
      ...createDrDispositions.map((d) => ({ canonical_id: d.target || d.nugget_id, duplicate_ids: [], merge_rationale: '' })),
      ...[...mergedByRecord].map(([path, ids]) => ({
        canonical_id: path,
        duplicate_ids: ids,
        merge_rationale: 'finalize title/slug match against the prepared drIndex; no record minted',
      })),
    ],
    dr_files_found: createDrDispositions.map((d) => d.target).filter((t) => typeof t === 'string'),
    failure: false,
    failure_detail: null,
    status: 'script',
  }
  log(`phase-3b: no dispatch — ${createDrDispositions.length} minted DR(s), ` +
    `${existingRecordSkips.length} nugget(s) matched an existing record (finalize dedup)`)
}

const drTargets = createDrDispositions.map((d) => d.target).filter((t) => typeof t === 'string')
const normDrPath = (p) => String(p).replace(/\\/g, '/')
const drTargetsNorm = new Set(drTargets.map(normDrPath))
const drMinting = {
  status: decisionNuggets.length === 0 ? 'no-decision-nuggets' : 'ran',
  decision_nuggets: decisionNuggets.length,
  create_dr: drTargetsNorm.size,
  create_dr_dispositions: createDrDispositions.length,
  skipped: allDispositions.filter((d) => d.op === 'SKIP').length,
  allocator_unavailable: allocatorUnavailableCount,
  folded_unresolved: foldedUnresolved.flatMap((f) => f.foldedNuggets.map((n) => n.id)),
  targets: drTargets,
  missing_files: reconcileDrTargets(drTargets, phase3b.dr_files_found),
  unclaimed_files: (phase3b.dr_files_found || []).map(normDrPath).filter((p) => !drTargetsNorm.has(p)),
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
          citation_target: { type: 'string' },
          citation_written: { type: 'boolean' },
        },
      },
    },
  },
}

// A DELETE verdict stands only with an on-disk citation of the artifact's full repo-relative path
// inside the wiki/decision page that absorbed it (the delete guard's harvest-provenance reads it).
function enforceProvenanceCitation(deletions) {
  const downgraded = []
  const rows = (deletions || []).map((d) => {
    if (d.disposition !== 'DELETE') return d
    const ok = d.citation_written === true && typeof d.citation_target === 'string' &&
      /^docs\/(wiki|decisions)\//.test(d.citation_target.replace(/\\/g, '/'))
    if (ok) return d
    downgraded.push(d.artifact_path)
    return { ...d, disposition: 'SEND_BACK', reason: `no guard-visible provenance citation written (${d.reason})` }
  })
  return { rows, downgraded }
}

// The agent's citation claim is checked on disk by the driver, not here: the returned
// `finalize_manifest.deletions` lists each DELETE row's citation_target, and
// `distill_mechanical.py finalize` runs verify-citations over them. A row it reports
// unconfirmed lands in the report's `send_back` and makes finalize exit 1 (halted
// `unconfirmed-citation`); no delete may be applied for those rows.

// Pure: args.logRoots when it is a non-empty array of repo-relative strings, else the defaults.
function resolveLogRoots(raw) {
  const dflt = ['archive/daily-summaries', 'archive/release-notes']
  if (!Array.isArray(raw) || raw.length === 0) return dflt
  const ok = raw.every((r) => typeof r === 'string' && r !== '' && !/^([A-Za-z]:|[\\/])/.test(r) && !r.split(/[\\/]/).includes('..'))
  return ok ? raw : dflt
}
const LOG_ROOTS = resolveLogRoots(RAW_ARGS_INPUT && RAW_ARGS_INPUT.logRoots)

// A DELETE verdict stands only for a recognised delete class (completion record, archived plan,
// cross-repo memo, read off the artifact path) outside every log/intake root. Anything else lands
// PRESERVE with the reason named: a log/intake source is read-only intake, never a delete cohort,
// and an absent or unknown class fails closed. Pure; `logRoots` is resolveLogRoots(args.logRoots).
function enforceIntakeAndClass(deletions, logRoots) {
  const downgraded = []
  const rows = (deletions || []).map((d) => {
    if (d.disposition !== 'DELETE') return d
    const cls = artifactClassOf(d.artifact_path, logRoots)
    if (cls === 'intake') {
      downgraded.push({ path: d.artifact_path, why: 'intake-root' })
      return { ...d, disposition: 'PRESERVE', reason: `intake-root: ${intakeRootOf(d.artifact_path, logRoots)} is read-only log/intake, never a delete cohort (was DELETE: ${d.reason})` }
    }
    if (cls === 'triage-only') {
      downgraded.push({ path: d.artifact_path, why: 'triage-only' })
      return { ...d, disposition: 'PRESERVE', reason: `triage-only: a daily-summary or week-changelog is read-only intake, never a delete cohort (was DELETE: ${d.reason})` }
    }
    if (cls === 'live-plan') {
      downgraded.push({ path: d.artifact_path, why: 'live-plan' })
      return { ...d, disposition: 'PRESERVE', reason: `live-plan: a live or non-top-level plan or spec is triage input, never a delete cohort; only archive/plans/ and archive/specs/ are delete-eligible (was DELETE: ${d.reason})` }
    }
    if (cls === 'unrecognised' || cls === 'handoff') {
      downgraded.push({ path: d.artifact_path, why: 'unrecognised-class' })
      return { ...d, disposition: 'PRESERVE', reason: `unrecognised-class: not a completion, plan or cross-repo memo source, fails closed (was DELETE: ${d.reason})` }
    }
    return d
  })
  return { rows, downgraded }
}

// Pure: splits distillation_log_rows into rows whose final disposition is mechanical and rows
// that need the deletion-manifest agent's judgment. Mechanical: archive/handoffs/ (omitted, not a
// cohort), SKIP (SEND_BACK), and any path enforceIntakeAndClass would refuse to DELETE (PRESERVE).
// An agent shown only mechanical rows decides nothing, so with no open row it is not dispatched.
function presettleDeletionRows(rows, logRoots) {
  const settled = []
  const open = []
  for (const r of rows || []) {
    if (artifactClassOf(r.path, logRoots) === 'handoff') continue
    if (r.disposition === 'SKIP') {
      const reason = r.skip_cause === 'nuggets-not-harvested'
        ? 'scanned, but its nuggets landed in no wiki op'
        : r.skip_cause === 'no-nuggets-no-classification'
          ? 'scanned batch returned no nuggets for this artifact'
          : 'batch never scanned'
      settled.push({ artifact_path: r.path, disposition: 'SEND_BACK', reason, source_nugget_ids: [] })
      continue
    }
    const probe = enforceIntakeAndClass([{ artifact_path: r.path, disposition: 'DELETE', reason: 'mechanical pre-settle' }], logRoots)
    if (probe.downgraded.length > 0) {
      settled.push({ ...probe.rows[0], reason: probe.rows[0].reason.replace(/ \(was DELETE: mechanical pre-settle\)$/, ''), source_nugget_ids: [] })
    } else {
      open.push(r)
    }
  }
  return { settled, open }
}

let phase3d = { deletions: [], status: 'suppressed' }
let phase3dSplit = { settled: [], open: [] }
if (disposalSuppressed) {
  log(`phase-3d: SUPPRESSED (no dispatch) — ${disposalSuppressedReason}`)
} else if (distillationLogRows.length === 0) {
  phase3d = { deletions: [], status: 'skipped-empty' }
  log('phase-3d: SKIPPED (no dispatch) — zero distillation_log_rows to classify.')
} else if ((phase3dSplit = presettleDeletionRows(distillationLogRows, LOG_ROOTS)).open.length === 0) {
  phase3d = { deletions: phase3dSplit.settled, status: 'settled-mechanically' }
  log(`phase-3d: SETTLED (no dispatch) — all ${phase3dSplit.settled.length} row(s) are SKIP, log/intake or non-delete-class.`)
} else {
  const deletionManifestBrief = COMMON + `

You are a Sonnet deletion-manifest agent (Phase 3d of the /distill harvest Workflow, folded
into this Workflow per PIPELINE.md § "Phase 3d: Deletion Manifest"). This Workflow already
mechanically classified every source artifact as DISTILLED (nuggets carried into a non-SKIP
disposition), EPHEMERAL (scanned, nothing carried forward), or SKIP (not harvested; skip_cause names why) — see
distillation_log_rows below. Your job is resolving each row into its FINAL disposition: DELETE,
SEND_BACK, BLOCKED, or PRESERVE.

Run ID: ${RUN_ID}
distillation_log_rows (path, mechanical disposition, fate prose). The Workflow already settled
every SKIP, log/intake and non-delete-class row in code; these are the rest:
${JSON.stringify(phase3dSplit.open, null, 2)}
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
  incompleteness: actively referenced by a live state/handoffs/*.md or state/handoffs/YYYY-MM/*.md file or in-progress task
  (Read state/handoffs/ to check — name the referencing file); a linked
  state/cross-repo-commitments/ entry is status: open; an accepted/partial memo has an
  absent/unverifiable realized_by; or the artifact is an in-progress/unapproved design spec.
- **PRESERVE** (overrides everything) — research outputs (docs/research/, ~/docs/research/,
  Pipeline A/B/C/D outputs), NotebookLM outputs, Pipeline C outputs (manifest_version: files).
  Never DELETE these regardless of extraction status.
- **Log/intake roots** (archive/daily-summaries/, archive/week-changelogs/, archive/release-notes/)
  and any source that is not a completion record (archive/completed/), archived plan
  (archive/specs/, archive/plans/) or cross-repo memo (state/cross-repo/archive/, cross-repo/archive/) are NEVER DELETE:
  return PRESERVE naming the root or class. The Workflow downgrades any such DELETE regardless.
- **archive/handoffs/** paths are NEVER eligible for any disposition — omit any such path from
  the manifest entirely if one appears in the rows above (they are not a distillation cohort).

Either an artifact was harvested or it wasn't — do NOT emit a disposition that records an
un-harvested artifact as settled. An artifact whose knowledge is not fully extracted is
SEND_BACK or BLOCKED, never DELETE and never a bare "retain".

**Provenance write (required for every DELETE).** Before you return DELETE for an artifact,
make its capture guard-visible on disk: Grep docs/wiki/ and docs/decisions/ for the artifact's
full repo-relative path. If a page already cites it, set citation_target to that page. If none
does, open the wiki page or decision record that absorbed its nuggets and add the artifact's
full repo-relative path to that page's frontmatter provenance block (a source_artifacts list,
additive, no other edit), then set citation_target to that page. Return citation_written: true
only after the citation is on disk. Cannot write it: return SEND_BACK, never DELETE. This
verdict is final — no PM approval step follows it; the delete guards decide at apply time.

For each artifact_path, include reason (explicit — name the missing citation, the blocking
reference, or the extracted nugget ids) and source_nugget_ids (nugget IDs actually cited in
this row's mechanical disposition — [] for SEND_BACK/BLOCKED/PRESERVE). Every row above must
appear exactly once in your returned deletions[] (minus any archive/handoffs/ rows, which you
omit per the rule above). Do NOT git commit — the EM commits; Phase 5 (apply) is downstream of
this Workflow.`

  // judgment-keeper: Phase 3d deletion manifest — final DELETE/SEND_BACK/BLOCKED/PRESERVE verdicts.
  const [deletionManifestResult] = (await parallel(
    [() => agent(deletionManifestBrief, {
      schema: DELETION_MANIFEST_SCHEMA,
      agentType: DISTILL_WRITER_TYPE,
      phase: 'phase-3d',
      label: 'deletion-manifest',
      model: 'sonnet',
    })],
    { concurrency: 1 }
  )).filter(Boolean)

  if (!deletionManifestResult) {
    phase3d = { deletions: phase3dSplit.settled, status: 'agent-failed' }
    log('phase-3d: deletion-manifest agent failed to return a result — surfacing in the returned manifest rather than halting the run.')
  } else {
    const enforced = enforceProvenanceCitation(deletionManifestResult.deletions)
    if (enforced.downgraded.length > 0) {
      log(`phase-3d: ${enforced.downgraded.length} DELETE row(s) without a written provenance citation downgraded to SEND_BACK`)
    }
    const guarded = enforceIntakeAndClass(enforced.rows, LOG_ROOTS)
    if (guarded.downgraded.length > 0) {
      log(`phase-3d: ${guarded.downgraded.length} DELETE row(s) under a log/intake root or of an unrecognised class downgraded to PRESERVE`)
    }
    phase3d = { ...deletionManifestResult, deletions: [...phase3dSplit.settled, ...guarded.rows], status: 'ran' }
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
// These rows originate from the Cross-Repo Archive Specialist
// Branch, not from the Phase 3d deletion-manifest agent, so they must not be dropped merely
// because phase3d itself is 'suppressed'/'skipped-empty'/'agent-failed'. Merged unconditionally;
// when phase3d never actually ran, `cross_repo_merged_without_manifest` flags the manifest as
// cross-repo-only rather than silently returning an empty deletions list.
const crossRepoPaths = new Set(CROSS_REPO_DISPOSITIONS.map((r) => r.artifact_path))
if (CROSS_REPO_DISPOSITIONS.length > 0) {
  const mergedWithoutManifest = phase3d.status !== 'ran' && phase3d.status !== 'settled-mechanically'
  phase3d = {
    ...phase3d,
    deletions: [...(phase3d.deletions || []).filter((d) => !crossRepoPaths.has(d.artifact_path)), ...CROSS_REPO_DISPOSITIONS],
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

// Citation repoint — a record cited only from docs/ or tasks/ is refused by distill-delete-guard
// at apply time though 3d resolved it DELETE; the apply agent repoints those citations at the
// wiki page that absorbed the content, then re-runs the guard.
function isRepointableCitation(p) {
  const n = String(p).replace(/\\/g, '/')
  return (n.startsWith('docs/') && !n.startsWith('docs/plans/')) || n.startsWith('tasks/')
}

function selectRepointCandidates(deletions, probes, absorbingByPath) {
  const probeByPath = new Map((probes || []).map((p) => [p.artifact_path, p]))
  const out = []
  for (const d of deletions || []) {
    const probe = probeByPath.get(d.artifact_path)
    if (!probe || probe.eligible !== false) continue
    const blockedBy = probe.blocked_by
    if (!Array.isArray(blockedBy) || blockedBy.length !== 1 || blockedBy[0] !== 'active-reference') continue
    const citing = Array.isArray(probe.citing_paths) ? probe.citing_paths : []
    if (citing.length === 0 || !citing.every(isRepointableCitation)) continue
    const wikiPaths = absorbingByPath.get(d.artifact_path) || []
    if (wikiPaths.length === 0) continue
    out.push({ artifact_path: d.artifact_path, citing_paths: citing, wiki_paths: wikiPaths })
  }
  return out
}

function applyRepointResults(deletions, candidates, results) {
  const candidatePaths = new Set(candidates.map((c) => c.artifact_path))
  const resultByPath = new Map((results || []).map((r) => [r.artifact_path, r]))
  const wikiByPath = new Map(candidates.map((c) => [c.artifact_path, c.wiki_paths]))
  const repointed = []
  const stillBlocked = []
  const next = (deletions || []).map((d) => {
    if (!candidatePaths.has(d.artifact_path)) return d
    const r = resultByPath.get(d.artifact_path)
    if (r && r.eligible === true) {
      repointed.push(d.artifact_path)
      const files = Array.isArray(r.repointed_files) ? r.repointed_files.join(', ') : ''
      const reason = `citations repointed (${files}) to ${(wikiByPath.get(d.artifact_path) || []).join(', ')}; delete-guard now eligible`
      return { ...d, disposition: 'DELETE', reason: d.disposition === 'DELETE' ? `${d.reason}; ${reason}` : reason }
    }
    stillBlocked.push({
      artifact_path: d.artifact_path,
      blocked_by: r && Array.isArray(r.blocked_by) ? r.blocked_by : [],
    })
    return d
  })
  return { deletions: next, repointed, still_blocked: stillBlocked }
}

const REPOINT_PROBE_SCHEMA = {
  type: 'object',
  required: ['probes'],
  properties: {
    probes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['artifact_path'],
        properties: {
          artifact_path: { type: 'string' },
          eligible: { type: 'boolean' },
          blocked_by: { type: 'array', items: { type: 'string' } },
          citing_paths: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const REPOINT_APPLY_SCHEMA = {
  type: 'object',
  required: ['results'],
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: ['artifact_path', 'repointed_files'],
        properties: {
          artifact_path: { type: 'string' },
          repointed_files: { type: 'array', items: { type: 'string' } },
          eligible: { type: 'boolean' },
          blocked_by: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

phase('citation-repoint')
let citationRepoint = { status: 'suppressed', probed: 0, candidates: 0, repointed: [], edited_files: [], still_blocked: [] }
if (disposalSuppressed || phase3d.status !== 'ran') {
  log(`citation-repoint: SUPPRESSED (no dispatch) — ${disposalSuppressed ? disposalSuppressedReason : `phase-3d status '${phase3d.status}'`}`)
} else {
  const distilledPaths = new Set(distillationLogRows.filter((r) => r.disposition === 'DISTILLED').map((r) => r.path))
  const probeRows = (phase3d.deletions || []).filter((d) =>
    (d.disposition === 'DELETE' || d.disposition === 'BLOCKED') &&
    distilledPaths.has(d.artifact_path) && !crossRepoPaths.has(d.artifact_path))
  if (probeRows.length === 0) {
    citationRepoint = { ...citationRepoint, status: 'skipped-empty' }
    log('citation-repoint: SKIPPED (no dispatch) — no DISTILLED DELETE/BLOCKED row to probe.')
  } else {
    // judgment-keeper: citation probe — runs the delete guard and classifies what blocks a row.
    const [probeResult] = (await parallel(
      [() => agent(COMMON + `

You are a Sonnet citation-probe agent (citation-repoint phase of the /distill harvest Workflow). You edit nothing.

Run \`distill-delete-guard\` (bareword; else \${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/distill-delete-guard) over these artifact paths, at most 5 paths per invocation:
${JSON.stringify(probeRows.map((d) => d.artifact_path), null, 2)}

For each path return artifact_path, and copy \`eligible\` and \`blocked_by\` from the guard's JSON exactly. If the guard's response lacks \`eligible\` or \`blocked_by\` for a path, omit that field — never fill it in. For a path whose blocked_by includes 'active-reference', list as citing_paths every file under docs/, tasks/, archive/ and state/handoffs/ that contains that path's repo-relative path.`, {
        schema: REPOINT_PROBE_SCHEMA,
        // executor-keeper: shells out to the engine-owned distill-delete-guard CLI; the writer type has no Bash.
        agentType: 'coordinator:executor',
        phase: 'citation-repoint',
        label: 'repoint-probe',
        model: 'sonnet',
      })],
      { concurrency: 1 }
    )).filter(Boolean)

    const probes = probeResult ? probeResult.probes || [] : []
    if (!probeResult) {
      citationRepoint = { ...citationRepoint, status: 'agent-failed', probed: probeRows.length }
      log('citation-repoint: probe agent failed to return a result — rows untouched.')
    } else {
      const idsByWiki = new Map()
      for (const r of synthResults) {
        for (const d of r.dispositions || []) {
          if (d.op === 'SKIP' || !d.nugget_id) continue
          if (!idsByWiki.has(d.nugget_id)) idsByWiki.set(d.nugget_id, new Set())
          idsByWiki.get(d.nugget_id).add(r.wiki_path)
        }
      }
      const absorbingByPath = new Map()
      for (const d of probeRows) {
        const wikis = new Set()
        for (const id of nuggetIdsBySource.get(d.artifact_path) || []) {
          for (const w of idsByWiki.get(id) || []) wikis.add(w)
        }
        absorbingByPath.set(d.artifact_path, [...wikis])
      }
      const candidates = selectRepointCandidates(probeRows, probes, absorbingByPath)
      if (candidates.length === 0) {
        citationRepoint = { ...citationRepoint, status: 'skipped-empty', probed: probeRows.length }
        log(`citation-repoint: ${probeRows.length} probed, 0 candidates — no apply dispatch.`)
      } else {
        // judgment-keeper: citation-repoint apply — rewrites citations at the absorbing page.
        const [applyResult] = (await parallel(
          [() => agent(COMMON + `

You are a Sonnet citation-repoint agent (citation-repoint phase of the /distill harvest Workflow). Do NOT git commit.

For each candidate below, edit each citing file so the citation names the wiki page that absorbed the cited content (choose among wiki_paths by reading them). Never leave or add the record's full path in an edited file. Then re-run \`distill-delete-guard\` on the record and copy its \`eligible\` and \`blocked_by\` exactly (omit a field the guard did not return). Return repointed_files per candidate: every file you changed.

Candidates:
${JSON.stringify(candidates, null, 2)}`, {
            schema: REPOINT_APPLY_SCHEMA,
            // executor-keeper: edits citing files across the repo and re-runs the delete guard (Bash).
            agentType: 'coordinator:executor',
            phase: 'citation-repoint',
            label: 'repoint-apply',
            model: 'sonnet',
          })],
          { concurrency: 1 }
        )).filter(Boolean)

        if (!applyResult) {
          citationRepoint = { ...citationRepoint, status: 'agent-failed', probed: probeRows.length, candidates: candidates.length }
          log('citation-repoint: apply agent failed — rows untouched. Inspect uncommitted changes under docs/ and tasks/: a failed agent may have edited before it died.')
        } else {
          const applied = applyRepointResults(phase3d.deletions, candidates, applyResult.results || [])
          phase3d = { ...phase3d, deletions: applied.deletions }
          const edited = [...new Set((applyResult.results || []).flatMap((r) => r.repointed_files || []))]
          citationRepoint = {
            status: 'ran',
            probed: probeRows.length,
            candidates: candidates.length,
            repointed: applied.repointed,
            edited_files: edited,
            still_blocked: applied.still_blocked,
          }
          log(`citation-repoint: ${probeRows.length} probed, ${candidates.length} candidate(s), ${applied.repointed.length} repointed, ${applied.still_blocked.length} still blocked, ${edited.length} file(s) edited.`)
        }
      }
    }
  }
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

let reentryRoundsRun = 0
const reentryEnteredPaths = new Set()
let currentDeletions = phase3d.deletions || []
const reentryLog = []

// A cross-repo-originated row never enters this
// repo's re-entry loop, regardless of phase3d.status: the loop's whole action is "re-open this
// file and integrate it into docs/wiki," a same-repo harvest, and a cross-repo artifact is not
// this run's to re-harvest. Resolved to BLOCKED here, before the loop, naming the actual external
// condition — never the reentry cap, since it never ran a round. One rule, not one keyed on
// phase3d.status (keying on it would give the same row, same repo, a different terminus
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

// Artifact re-entry is off the default path: only args.reentry === true pays for it. Off, every
// SEND_BACK row resolves BLOCKED naming that, before any round could run.
const REENTRY_ENABLED = RAW_ARGS_INPUT.reentry === true
if (!REENTRY_ENABLED) {
  const offPaths = []
  currentDeletions = currentDeletions.map((d) => {
    if (d.disposition !== 'SEND_BACK') return d
    offPaths.push(d.artifact_path)
    return {
      ...d,
      disposition: 'BLOCKED',
      reason: `un-harvestable: artifact re-entry is off the default path (args.reentry is not true; ` +
        `no send_back re-entry round ran) — original reason: ${d.reason}`,
    }
  })
  log(`artifact re-entry: off the default path (args.reentry unset)` +
    (offPaths.length > 0 ? `; ${offPaths.length} SEND_BACK row(s) resolved to BLOCKED: ${offPaths.join(', ')}` : ''))
}

// Re-entry ops: one tool-less distill-synth call per original synth payload holding a SEND_BACK row's
// nuggets. The returns are synth returns for `distill_mechanical.py finalize`, the only page writer.
const reentryReturns = []
if (REENTRY_ENABLED && phase3d.status === 'ran') {
  while (reentryRoundsRun < SEND_BACK_REENTRY_CAP) {
    const sendBackRows = currentDeletions.filter((d) => d.disposition === 'SEND_BACK')
    const totalRows = currentDeletions.length
    log(`artifact re-entry round ${reentryRoundsRun + 1}: ${totalRows - sendBackRows.length}/${totalRows} ` +
      `artifact(s) settled (${sendBackRows.length} SEND_BACK remaining)`)
    if (sendBackRows.length === 0) break
    for (const row of sendBackRows) reentryEnteredPaths.add(row.artifact_path)

    const entries = reentryPayloadsFor(SYNTH_PAYLOADS, sendBackRows)
    // judgment-keeper: artifact re-entry — re-synthesizes SEND_BACK artifacts' nuggets as ops.
    const roundReturns = await parallel(
      entries.map((e) => () =>
        agent(synthBriefFor(e.payload), {
          schema: synthSchemaFor(PREPARED.synth, e.index),
          agentType: 'coordinator:distill-synth',
          phase: 'artifact-reentry',
          label: `reentry-r${reentryRoundsRun + 1}-synth-${e.index + 1}`,
          model: SYNTH_MODEL,
        })
      ),
      { concurrency: CONCURRENCY_CAP }
    )
    const failedReentryBatchIds = entries.filter((_, i) => !roundReturns[i]).map((e) => `synth-${e.index + 1}`)
    if (failedReentryBatchIds.length > 0) {
      log(`artifact re-entry round ${reentryRoundsRun + 1}: re-synthesis call failure for ` +
        `${failedReentryBatchIds.join(', ')} — caught, not run-blocking; ` +
        `artifact(s) remain SEND_BACK this round`)
    }
    reentryReturns.push(...roundReturns.filter(Boolean))

    const resolutionByPath = settleReentryRows(sendBackRows, entries, roundReturns)
    currentDeletions = currentDeletions.map((d) =>
      resolutionByPath.has(d.artifact_path) ? { ...d, ...resolutionByPath.get(d.artifact_path) } : d)
    reentryLog.push({
      round: reentryRoundsRun + 1,
      send_back_in: sendBackRows.length,
      resolved: sendBackRows.filter((d) => resolutionByPath.has(d.artifact_path)).length,
      failed_batch_ids: failedReentryBatchIds,
    })
    reentryRoundsRun++
  }
}
// Same top-level keys as promote_manifest; no staged files and no source hashes, so finalize splices
// the returns and stores nothing for them.
const reentryManifest = reentryReturns.length > 0 ? buildPromoteManifest(RUN_ID, [], reentryReturns, {}) : null

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
    reason: (reentryRoundsRun === 0
      ? 'un-harvestable: no send_back re-entry round ran — '
      : `un-harvestable after ${reentryRoundsRun} send_back re-entry round(s) — `) +
      `original reason: ${d.reason}`,
  }
})
if (cappedArtifactPaths.length > 0) {
  log(`artifact re-entry: ${cappedArtifactPaths.length} artifact(s) capped to BLOCKED after ` +
    (reentryRoundsRun === 0 ? 'no re-entry round ran' : `${reentryRoundsRun} round(s)`) +
    (reentryRoundsRun === 0 ? '' : ` (cap ${SEND_BACK_REENTRY_CAP})`) +
    `: ${cappedArtifactPaths.join(', ')}`)
}
// Pure: every BLOCKED row that never entered a re-entry round names that no round ran for it, whichever
// site produced it (the Phase 3d agent, a cross-repo row, a mechanical settle); a row already naming
// rounds keeps its reason.
function wordBlockedByRounds(deletions, enteredPaths) {
  return (deletions || []).map((d) => {
    if (d.disposition !== 'BLOCKED' || enteredPaths.has(d.artifact_path) || /send_back re-entry round/.test(String(d.reason))) return d
    return { ...d, reason: `${d.reason} (no send_back re-entry round ran for this artifact)` }
  })
}
currentDeletions = wordBlockedByRounds(currentDeletions, reentryEnteredPaths)
// Final merged manifest (after crossRepoDispositions merge, citation-repoint, re-entry): the
// guard runs once more so no DELETE on an intake path or unrecognised class reaches Phase 5.
const finalGuard = enforceIntakeAndClass(currentDeletions, LOG_ROOTS)
if (finalGuard.downgraded.length > 0) {
  log(`phase-3d (final manifest): ${finalGuard.downgraded.length} DELETE row(s) under a log/intake root or of an unrecognised class downgraded to PRESERVE`)
}
currentDeletions = finalGuard.rows
phase3d = { ...phase3d, deletions: currentDeletions }

const artifactReentry = {
  rounds_run: reentryRoundsRun,
  cap: SEND_BACK_REENTRY_CAP,
  rounds: reentryLog,
  // No final send-back count: the cap-conversion above flips every remaining SEND_BACK to
  // BLOCKED, so it would always read zero. `capped_to_blocked.length` carries the signal.
  capped_to_blocked: cappedArtifactPaths,
}

return {
  done: true,
  run_id: RUN_ID,
  concurrency_cap: CONCURRENCY_CAP,
  load_stats: buildLoadStats(BATCHES, WIKI_SLUGS),
  // Hand-off to `distill_mechanical.py finalize`: the DELETE rows' citations for verify-citations
  // (and, on the post-promote pass, the archive, scratch and index legs). `files` is empty here: the
  // pages were promoted before the judgment phases, by the first finalize call.
  finalize_manifest: {
    run_id: RUN_ID,
    wikiDirs: WIKI_DIRS,
    files: [],
    hashes: {},
    deletions: (phase3d.deletions || [])
      .filter((d) => d.disposition === 'DELETE' && d.citation_target)
      .map((d) => ({ artifact_path: d.artifact_path, citation_target: d.citation_target })),
    archive: [],
  },
  batches_scanned: scanResults.length,
  failed_batch_ids: failedBatchIds,
  plan_triage: PLAN_TRIAGE_REPORT,
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
  synth_outcome: synthOutcome,
  synth_calls: SYNTH_PAYLOADS.length,
  deferred_topics: deferredTopics,
  unsynthesized_topic_keys: unsynthesizedTopicKeys,
  dispatch_estimate: dispatchEstimate,
  agent_ceiling: AGENT_CEILING,
  skipped_unchanged: unchangedClusters.map((c) => c.topicKey),
  promoted_files: promoteResult.promoted,
  residue_scan: RESIDUE_SCAN,
  scan_results: scanResults,
  synth_results: synthResults,
  distillation_log_rows: distillationLogRows,
  fate_prose_enforcement: fateProseEnforcement,
  provenance_completeness: provenanceCompleteness,
  coverage: {
    total_assigned_nuggets: totalAssignedNuggets,
    total_covered_nuggets: totalAssignedNuggets - remainingGaps.reduce((n, g) => n + g.uncoveredNuggets.length, 0),
    gap_clusters: coverageGaps.map((g) => g.topicKey),
    unresolved_gap_clusters: remainingGaps.map((g) => g.topicKey),
  },
  judgment_mining: judgmentMining,
  contradiction_detection: contradictionDetection,
  opus_escalation: opusEscalation,
  phase_3b_dr_dedup: phase3b,
  dr_minting: drMinting,
  phase_3d_deletion_manifest: phase3d,
  artifact_reentry: artifactReentry,
  ...(reentryManifest
    ? {
        reentry_manifest: { ...reentryManifest, wikiDirs: WIKI_DIRS },
        reentry_resume_hint: 'Run distill_mechanical.py finalize --manifest <reentry_manifest> --no-scratch --no-archive; the returned ops land through the same cite-checked splice as the promote manifest, and no re-entry row is DELETE until a later run settles it.',
      }
    : {}),
  citation_repoint: citationRepoint,
}
