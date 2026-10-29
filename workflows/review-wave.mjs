/*
 * review-wave — background-Workflow encoding of the parallel-code-review gate contract.
 *
 * Spec backlink: coordinator/skills/parallel-code-review/SKILL.md (the /workweek-complete
 * Step 7 merge gate). This script is that gate's DISPATCH VEHICLE: the skill dispatches the
 * span through it, and hand-orchestrating N parallel dispatches is the fallback for when this
 * refuses, not a parallel path of equal standing. The skill remains the source of truth for
 * the contract; this script reproduces its agent legs (chunk reviewers, security worker,
 * SKIP_CODE_SEMANTICS handling). Running the reviewers as one workflow is also
 * what keeps the gate automatic — a hand-dispatched span invites a pause between reviewers,
 * and a gate that waits to be told to continue is not a gate.
 *
 * Negative-spec: this is NOT a new gate, NOT a replacement for claude-klabauter
 * `coordinator_core/ops/verify_parallel_review_lens_orthogonality.py`, and NOT a
 * substitute for the skill's Snapshot/Chunking/Pre-Flight steps —
 * those still run EM-side (or caller-side) BEFORE invoking this Workflow. The Workflow starts
 * at "dispatch the reviewers" and ends at "return the reviewer results"; it does not freeze the
 * diff, build the chunk manifest, run the orthogonality assertions, run weekly-gate-deps.py or
 * weekly-gate-tests.py, or compute the verdict (weekly-gate-synthesize.py writes synthesis.json
 * after the Workflow) — those are the caller's job per the skill.
 *
 * args contract:
 *   {
 *     findingsDir: string,        // e.g. "state/review-findings/20260712T120000Z"
 *                                   // ($FINDINGS_DIR from the skill's Snapshot step — where
 *                                   //  chunk/specialist findings and synthesis.json land)
 *     diffPatchPath: string,      // the frozen diff path from the skill's Snapshot step
 *                                   // ($DIFF_PATH from freeze-review-diff.py), e.g.
 *                                   // "state/review-trail/diffs/weekly-20260712T120000Z.diff".
 *     chunks: [ { id: string, files: [string], callers?: [string], anchors?: [string] } ],
 *                                                     // optional callers/anchors go to the chunk
 *                                                     // reviewer verbatim; the manifest is pre-built seam-first
 *                                                     // per the skill's Chunking section; empty
 *                                                     // array when skipCodeSemantics is true
 *     skipCodeSemantics: boolean, // Rule 2 (skip-code-semantics-on-doc-only) from the skill's
 *                                   // Gating Rules — when true, dispatch zero chunk reviewers
 *                                   // and run only security-audit-worker
 *     pluginRoot: string,         // optional ABSOLUTE coordinator plugin root. The briefs cite the
 *                                   // plugin's skill and agent files under it, because a consumer
 *                                   // repo has no `coordinator/` directory. Absent, they say
 *                                   // `<plugin-root>/...`, and the agent resolves the root itself.
 *   }
 *   A caller still passing testOutputPath is ignored: tests run in weekly-gate-tests.py.
 *
 * Invocation:
 *   Workflow({
 *     scriptPath: `${CLAUDE_PLUGIN_ROOT}/workflows/review-wave.mjs`,
 *     args: {
 *       findingsDir: "state/review-findings/20260712T120000Z",
 *       pluginRoot: CLAUDE_PLUGIN_ROOT (resolved, absolute),
 *       diffPatchPath: "state/review-trail/diffs/weekly-20260712T120000Z.diff",
 *       chunks: [
 *         { id: "chunk-1", files: ["path/a.ts", "path/b.ts"] },
 *         { id: "chunk-2", files: ["path/c.py"] }
 *       ],
 *       skipCodeSemantics: false
 *     }
 *   })
 *
 * Returns: { findingsDir, chunks, results } — the reviewer results. No verdict: the schema
 * (weekly_gate.VERDICT_SCHEMA) and synthesis.json are owned by weekly-gate-synthesize.py.
 */

export const meta = {
  name: 'review-wave',
  description: 'Weekly parallel-code-review gate — N chunk reviewers + security-audit-worker in one parallel(); deps, tests and the verdict are scripts the driver runs outside the Workflow.',
  phases: [
    { title: 'Review', detail: 'N Sonnet code-reviewer-weekly instances over disjoint file-scope chunks (none when skipCodeSemantics is true — doc-only week) plus security-audit-worker over the full diff, all in one parallel().' },
  ],
}


const PLUGIN_ROOT = (typeof args.pluginRoot === 'string' && args.pluginRoot.trim()) ? args.pluginRoot.trim() : '<plugin-root>'
const pluginPath = (rel) => PLUGIN_ROOT + '/' + rel
const OBJECTIVE_RULE = 'When state/warp/<run_id>/objective.json exists, read it first and carry its axes; never report "unknown".'

// No brief here reads a sizing, plan or handoff (inputs are a frozen diff, chunk lists, findings
// and test output), so the sibling scripts' MID_RUN_DIRECTION_RULE is deliberately absent. A brief
// that starts reading one must carry it; test_workflow_mid_run_direction_rule.py pins the count.
// A chunk may carry `callers` (paths or path:line of the changed symbols' callers) and `anchors`
// (excerpts of the surrounding code), both caller-supplied; the reviewer reads them rather than
// re-deriving them. Absent, the brief is unchanged.
function handedContext(chunk) {
  const lines = []
  if (Array.isArray(chunk.callers) && chunk.callers.length) {
    lines.push('Callers of the changed symbols (handed to you; read these instead of re-grepping): ' + chunk.callers.join(', '))
  }
  if (Array.isArray(chunk.anchors) && chunk.anchors.length) {
    lines.push('Anchor excerpts (handed to you):', ...chunk.anchors.map((a) => '  ' + String(a).split('\n').join('\n  ')))
  }
  return lines
}

function chunkPrompt(chunk, diffPatchPath, findingsDir) {
  return [
    'You are a Sonnet code-reviewer-weekly instance dispatched as part of a review-wave Workflow.',
    'Per ' + pluginPath('agents/code-reviewer-weekly.md') + ': you have Write access to exactly ONE output path and no other.',
    OBJECTIVE_RULE,
    '',
    'Assigned chunk: ' + chunk.id,
    'File-scope (disjoint partition — review ONLY these files): ' + chunk.files.join(', '),
    'Diff context: read ' + diffPatchPath + ' for the frozen diff at the merge boundary.',
    ...handedContext(chunk),
    '',
    'Write your findings ONLY to: ' + findingsDir + '/' + chunk.id + '.md',
    'Write incrementally as you go (re-write the full file each time; Write is full-file, not Edit).',
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    '',
    'Mark any finding whose right disposition is architectural (would need Opus-tier judgment,',
    'not a localized fix) with escalate_to_architecture: true. Most findings carry',
    'escalate_to_architecture: false or omit the field (absent means false).',
    '',
    'Use the standard severity scale (P0/P1/P2/nit) and structured findings format from',
    pluginPath('agents/code-reviewer-weekly.md') + '. When done, verify your file exists on disk (ls -la) before',
    'replying. Reply DONE: ' + findingsDir + '/' + chunk.id + '.md — nothing else.',
  ].join('\n')
}

function securityWorkerPrompt(worker, inputPath, inputDescription, findingsDir, outFile) {
  return [
    'You are the ' + worker + ' dispatched as part of a review-wave Workflow, per',
    pluginPath('skills/parallel-code-review/SKILL.md') + ' § Parallel Dispatch.',
    '',
    OBJECTIVE_RULE,
    '',
    inputDescription + ': ' + inputPath,
    '',
    'Write your findings ONLY to: ' + findingsDir + '/' + outFile,
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    '',
    'Verify your output file exists on disk (ls -la) before replying.',
    'Reply DONE: ' + findingsDir + '/' + outFile + ' — nothing else.',
  ].join('\n')
}

phase('Review')

const chunkThunks = args.skipCodeSemantics
  ? []
  : args.chunks.map(chunk => () =>
      agent(chunkPrompt(chunk, args.diffPatchPath, args.findingsDir), {
        agentType: 'coordinator:code-reviewer-weekly',
        model: 'sonnet',
        phase: 'Review',
        label: 'chunk:' + chunk.id,
      })
    )

const securityThunk = () => agent(securityWorkerPrompt(
  'security-audit-worker', args.diffPatchPath,
  'Scan the full diff (not a chunked subset — the security worker sees its full input ' +
    'artifact, unlike the code-semantics chunk reviewers)',
  args.findingsDir, 'security.md'
), {
  agentType: 'coordinator:security-audit-worker',
  model: 'sonnet',
  phase: 'Review',
  label: 'security-audit-worker',
})

const reviewResults = (await parallel([...chunkThunks, securityThunk])).filter(Boolean)

log('review-wave complete: reviewers=' + reviewResults.length + ' (chunks=' + chunkThunks.length + ' + security). ' +
    'Verdict: run weekly-gate-synthesize.py over ' + args.findingsDir)

return { findingsDir: args.findingsDir, chunks: chunkThunks.length, results: reviewResults }
