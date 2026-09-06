/*
 * review-wave — background-Workflow encoding of the parallel-code-review gate contract.
 *
 * Spec backlink: coordinator/skills/parallel-code-review/SKILL.md (the /workweek-complete
 * Step 7 merge gate). This script is that gate's DISPATCH VEHICLE: the skill dispatches the
 * span through it, and hand-orchestrating N parallel dispatches is the fallback for when this
 * refuses, not a parallel path of equal standing. The skill remains the source of truth for
 * the contract; this script reproduces it faithfully (chunk reviewers, mechanical workers,
 * synthesizer, SKIP_CODE_SEMANTICS handling). Running the reviewers as one workflow is also
 * what keeps the gate automatic — a hand-dispatched span invites a pause between reviewers,
 * and a gate that waits to be told to continue is not a gate.
 *
 * Negative-spec: this is NOT a new gate, NOT a replacement for claude-klabauter
 * `coordinator_core/ops/verify_parallel_review_lens_orthogonality.py`, and NOT a
 * substitute for the skill's Snapshot/Chunking/Pre-Flight steps —
 * those still run EM-side (or caller-side) BEFORE invoking this Workflow. The Workflow starts
 * at "dispatch the reviewers" and ends at "return the synthesizer's verdict object"; it does
 * not freeze the diff, does not build the chunk manifest, and does not run the orthogonality
 * assertions — those are the caller's job per the skill.
 *
 * args contract:
 *   {
 *     findingsDir: string,        // e.g. "state/review-findings/20260712T120000Z"
 *                                   // ($FINDINGS_DIR from the skill's Snapshot step — where
 *                                   //  chunk/specialist findings and synthesis.json land)
 *     diffPatchPath: string,      // the frozen diff path from the skill's Snapshot step
 *                                   // ($DIFF_PATH from freeze-review-diff.py), e.g.
 *                                   // "state/review-trail/diffs/weekly-20260712T120000Z.diff".
 *                                   // The frozen head.sha sibling is derived by this script
 *                                   // (swap the ".diff" suffix for ".head.sha") and passed to
 *                                   // the synthesizer for head-drift comparison.
 *     chunks: [ { id: string, files: [string] } ],  // the chunk manifest, pre-built seam-first
 *                                                     // per the skill's Chunking section; empty
 *                                                     // array when skipCodeSemantics is true
 *     skipCodeSemantics: boolean, // Rule 2 (skip-code-semantics-on-doc-only) from the skill's
 *                                   // Gating Rules — when true, dispatch zero chunk reviewers
 *                                   // and run only the 3 mechanical specialist workers
 *     testOutputPath: string,     // caller-captured raw test-run stdout/stderr, analogous to
 *                                   // diffPatchPath: the caller runs the project test command
 *                                   // BEFORE invoking this Workflow and freezes its output to a
 *                                   // file, e.g. "state/review-trail/diffs/weekly-<TS>.test.log".
 *                                   // test-evidence-parser reads this path — it never runs the
 *                                   // suite itself (no Bash on its tool surface). Production of
 *                                   // this file, and pre-scaffolding $FINDINGS_DIR/tests.md as
 *                                   // an empty sentinel so the parser's Edit-only persistence
 *                                   // has a target to Edit, are both the caller's responsibility
 *                                   // (this Workflow has no fs/Bash primitive of its own) — not
 *                                   // yet wired into the skill's Snapshot step; known gap, same
 *                                   // shape as D2's dep-cve-auditor deferral.
 *   }
 *
 * Invocation:
 *   Workflow({
 *     scriptPath: "coordinator/workflows/review-wave.mjs",
 *     args: {
 *       findingsDir: "state/review-findings/20260712T120000Z",
 *       diffPatchPath: "state/review-trail/diffs/weekly-20260712T120000Z.diff",
 *       testOutputPath: "state/review-trail/diffs/weekly-20260712T120000Z.test.log",
 *       chunks: [
 *         { id: "chunk-1", files: ["path/a.ts", "path/b.ts"] },
 *         { id: "chunk-2", files: ["path/c.py"] }
 *       ],
 *       skipCodeSemantics: false
 *     }
 *   })
 *
 * Returns: the synthesizer's verdict object (schema: VERDICT_SCHEMA below), matching
 * `$FINDINGS_DIR/synthesis.json` as documented in agents/parallel-review-synthesizer.md.
 */

export const meta = {
  name: 'review-wave',
  description: 'Weekly parallel-code-review gate — N chunk reviewers + 3 mechanical workers, synthesized into one BLOCKED/WARN/OK verdict.',
  phases: [
    { title: 'Chunk review', detail: 'N Sonnet code-reviewer-weekly instances over disjoint file-scope chunks of the code-semantics scope (skipped entirely when skipCodeSemantics is true — doc-only week).' },
    { title: 'Mechanical', detail: 'security-audit-worker + dep-cve-auditor + test-evidence-parser over the full diff, in parallel with each other and with the chunk-review phase.' },
    { title: 'Synthesize', detail: 'parallel-review-synthesizer reads all findings from disk, applies the no-rewrite contract, and writes the structured verdict.' },
  ],
}

// Validated against agents/parallel-review-synthesizer.md § Output Schema.
const VERDICT_SCHEMA = {
  type: 'object',
  required: ['verdict', 'verdict_rationale', 'head_drift', 'convergent_findings', 'arch_tier_candidates', 'per_reviewer_findings', 'requires_em_resolution', 'lens_coverage'],
  properties: {
    verdict: { type: 'string', enum: ['BLOCKED', 'WARN', 'OK'] },
    verdict_rationale: { type: 'string' },
    head_drift: { type: 'boolean' },
    convergent_findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          reviewers: { type: 'array', items: { type: 'string' } },
          evidence_quotes: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    arch_tier_candidates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          source_chunk: { type: 'string' },
          file: { type: 'string' },
          line: { type: 'number' },
          evidence_quote: { type: 'string' },
        },
      },
    },
    per_reviewer_findings: { type: 'object' },
    requires_em_resolution: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          reviewer_a: { type: 'string' },
          claim_a: { type: 'string' },
          reviewer_b: { type: 'string' },
          claim_b: { type: 'string' },
        },
      },
    },
    lens_coverage: { type: 'object' },
  },
}

// Per skill § Parallel Dispatch: every reviewer dispatch prompt must include expected_branch.
// The Workflow harness does not expose the caller's branch name directly, so the chunk/worker
// prompts below instruct each agent to read it via `git branch --show-current` and pass it to
// coordinator-safe-commit-adjacent no-commit discipline — reviewers do not commit at all, they
// only need the branch name for the disk-first scoped-write verification the skill requires.
function chunkPrompt(chunk, diffPatchPath, findingsDir) {
  return [
    'You are a Sonnet code-reviewer-weekly instance dispatched as part of a review-wave Workflow.',
    'Per agents/code-reviewer-weekly.md: you have Write access to exactly ONE output path and no other.',
    '',
    'Assigned chunk: ' + chunk.id,
    'File-scope (disjoint partition — review ONLY these files): ' + chunk.files.join(', '),
    'Diff context: read ' + diffPatchPath + ' for the frozen diff at the merge boundary.',
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
    'agents/code-reviewer-weekly.md. When done, verify your file exists on disk (ls -la) before',
    'replying. Reply DONE: ' + findingsDir + '/' + chunk.id + '.md — nothing else.',
  ].join('\n')
}

// Generalized over the worker's INPUT ARTIFACT, not "the diff" — security-audit-worker and
// dep-cve-auditor take the full diff, but test-evidence-parser takes an EM-captured test-output
// path (it has no Bash on its tool surface and never runs the suite itself; see the args-contract
// note on testOutputPath above). Grouping all three under a diff-shaped call site is exactly the
// bug this generalizes away from — see the plan's F6 finding.
function mechanicalPrompt(worker, inputPath, inputDescription, findingsDir, outFile) {
  // test-evidence-parser carries no Bash post-2026-07-23 (bash-kill ruling) — it persists via a
  // single Edit on an EM-pre-scaffolded sentinel, and Edit's own fail-loud-if-absent behavior is
  // the verification; there is no `ls -la` for it to run. The other two workers keep Bash and
  // keep the disk-verify line.
  const canVerifyOnDisk = worker !== 'test-evidence-parser'
  return [
    'You are the ' + worker + ' dispatched as part of a review-wave Workflow, per',
    'coordinator/skills/parallel-code-review/SKILL.md § Parallel Dispatch.',
    '',
    inputDescription + ': ' + inputPath,
    '',
    'Write your findings ONLY to: ' + findingsDir + '/' + outFile,
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    '',
    ...(canVerifyOnDisk ? ['Verify your output file exists on disk (ls -la) before replying.'] : []),
    'Reply DONE: ' + findingsDir + '/' + outFile + ' — nothing else.',
  ].join('\n')
}

function synthPrompt(diffPatchPath, findingsDir) {
  const headShaPath = diffPatchPath.replace(/\.diff$/, '.head.sha')
  return [
    'You are the parallel-review-synthesizer dispatched as part of a review-wave Workflow, per',
    'agents/parallel-review-synthesizer.md.',
    '',
    'FINDINGS_DIR: ' + findingsDir,
    'HEAD_SHA_PATH (frozen head SHA from the Snapshot step): ' + headShaPath,
    '',
    'Read HEAD_SHA_PATH and compare against current HEAD (`git rev-parse HEAD`) for head-drift',
    'detection before anything else — see § Verdict Rules / Workflow step 1 in the agent file.',
    '',
    'Discover the chunk set by globbing ' + findingsDir + '/chunk-*.md (do not hardcode N).',
    'Read the 3 fixed specialist files: security.md, deps.md, tests.md.',
    'If zero chunk files are found, check for ' + findingsDir + '/code_semantics_skip.sentinel —',
    'its presence means intended-zero (doc-only week), its absence means failed_disk_read.',
    '',
    'Apply the no-rewrite contract: every evidence_quote must be byte-equal to a contiguous span',
    'of the normalized reviewer output. Never paraphrase. Never pick a winner on divergent claims',
    '(populate requires_em_resolution instead). Aggregate every escalate_to_architecture: true',
    'finding into arch_tier_candidates verbatim, without judgment — that bucket does NOT affect',
    'the verdict.',
    '',
    'Evaluate verdict rules in strict order (BLOCKED -> WARN -> OK) exactly as specified in',
    'agents/parallel-review-synthesizer.md § Verdict Rules.',
    '',
    'Write ' + findingsDir + '/synthesis.json per the exact Output Schema in that file, then',
    'verify it exists on disk (ls -la) before replying.',
    'Reply DONE: ' + findingsDir + '/synthesis.json — nothing else.',
  ].join('\n')
}

phase('Chunk review')
const chunkResults = args.skipCodeSemantics
  ? []
  : (await parallel(
      args.chunks.map(chunk => () =>
        agent(chunkPrompt(chunk, args.diffPatchPath, args.findingsDir), {
          agentType: 'coordinator:code-reviewer-weekly',
          model: 'sonnet',
          phase: 'Chunk review',
          label: 'chunk:' + chunk.id,
        })
      )
    )).filter(Boolean)

phase('Mechanical')

// An absent testOutputPath is the skill's RESOLVER_EXIT=2 week reaching this script: no
// resolver, so no captured test output and no pre-scaffolded tests.md sentinel for an
// Edit-only agent to write into. Dispatching anyway burns a slice that can only fail its
// disk read, and the synthesizer scores that as failed_disk_read rather than a clean skip.
const mechanicalThunks = [
  () => agent(mechanicalPrompt(
    'security-audit-worker', args.diffPatchPath,
    'Scan the full diff (not a chunked subset — each mechanical worker sees its own full input ' +
      'artifact, unlike the code-semantics chunk reviewers)',
    args.findingsDir, 'security.md'
  ), {
    agentType: 'coordinator:security-audit-worker',
    model: 'sonnet',
    phase: 'Mechanical',
    label: 'security-audit-worker',
  }),
  () => agent(mechanicalPrompt(
    'dep-cve-auditor', args.diffPatchPath,
    'Scan the full diff (not a chunked subset — each mechanical worker sees its own full input ' +
      'artifact, unlike the code-semantics chunk reviewers)',
    args.findingsDir, 'deps.md'
  ), {
    agentType: 'coordinator:dep-cve-auditor',
    model: 'sonnet',
    phase: 'Mechanical',
    label: 'dep-cve-auditor',
  }),
]

if (args.testOutputPath) {
  mechanicalThunks.push(() => agent(mechanicalPrompt(
    'test-evidence-parser', args.testOutputPath,
    'Read the EM-captured raw test-output (you do not run the test command yourself — Bash is ' +
      'not on your tool surface)',
    args.findingsDir, 'tests.md'
  ), {
    agentType: 'coordinator:test-evidence-parser',
    model: 'sonnet',
    phase: 'Mechanical',
    label: 'test-evidence-parser',
  }))
} else {
  log('test-evidence-parser SKIPPED: no testOutputPath supplied (unconfigured resolver). ' +
      'The synthesizer scores tests as an absent lens, not as a failed one.')
}

const mechanicalResults = (await parallel(mechanicalThunks)).filter(Boolean)

phase('Synthesize')
const verdict = await agent(synthPrompt(args.diffPatchPath, args.findingsDir), {
  agentType: 'coordinator:parallel-review-synthesizer',
  model: 'sonnet',
  phase: 'Synthesize',
  schema: VERDICT_SCHEMA,
})

log('review-wave complete: verdict=' + (verdict && verdict.verdict) + ' chunks=' + chunkResults.length + ' mechanical=' + mechanicalResults.length)

return verdict
