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
 *     stageFamilyBinding: string, // optional, opt-in per run: the path of coordinator/pipelines/
 *                                   // stage-family-binding.yaml. Present, one extra leg reviews the full
 *                                   // diff through coordinator:family-stage-runner on the bound review
 *                                   // family and lands its report (or the Claude fallback's) at
 *                                   // findingsDir/chunk-family-review.md, which weekly-gate-synthesize.py
 *                                   // collects; a BLOCKED/FAILED/unusable/unlanded runner result reruns
 *                                   // that leg on Claude. Absent, or with skipCodeSemantics true, the
 *                                   // dispatch is exactly the Claude-only one.
 *     reviewFamily: string,       // optional with stageFamilyBinding: this run's review family; it
 *                                   // overrides the binding's roles.review (default "codex"), so a
 *                                   // run can put any family on the review stage
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
 * Returns: { findingsDir, chunks, results } — the reviewer results; with stageFamilyBinding, also
 * familyReview: { family, binding, runner, fallback, fallbackUsed } where `runner` is the family
 * runner's own record and `fallback` the Claude rerun's (null unless fallbackUsed); the fallback is
 * never reported as the family's result. No verdict: the schema
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

const ESCALATE_LINES = [
  'Mark any finding whose right disposition is architectural (would need Opus-tier judgment,',
  'not a localized fix) with escalate_to_architecture: true. Most findings carry',
  'escalate_to_architecture: false or omit the field (absent means false).',
]

// weekly-gate-synthesize.py globs findingsDir/chunk-*.md; every chunk findings path must match it.
const chunkFileName = (chunk) => {
  const id = String(chunk.id)
  return (id.startsWith('chunk-') ? id : 'chunk-' + id) + '.md'
}

function chunkPrompt(chunk, diffPatchPath, findingsDir) {
  const chunkOut = findingsDir + '/' + chunkFileName(chunk)
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
    'Write your findings ONLY to: ' + chunkOut,
    'Write incrementally as you go (re-write the full file each time; Write is full-file, not Edit).',
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    '',
    ...ESCALATE_LINES,
    '',
    'Use the standard severity scale (P0/P1/P2/nit) and structured findings format from',
    pluginPath('agents/code-reviewer-weekly.md') + '. When done, verify your file exists on disk (ls -la) before',
    'replying. Reply DONE: ' + chunkOut + ' — nothing else.',
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

const FAMILY_BINDING = (typeof args.stageFamilyBinding === 'string' && args.stageFamilyBinding.trim()) ? args.stageFamilyBinding.trim() : ''
const REVIEW_FAMILY = (typeof args.reviewFamily === 'string' && args.reviewFamily.trim()) ? args.reviewFamily.trim() : 'codex'
const FAMILY_LEG_ID = 'family-review'

// weekly-gate-synthesize.py collects findingsDir/chunk-*.md; the family leg's report lands under
// that glob so its findings are scored.
const FAMILY_OUT = (findingsDir) => findingsDir + '/chunk-' + FAMILY_LEG_ID + '.md'

const familyScratch = (findingsDir) =>
  'scratch/review-wave-family/' + (String(findingsDir).split(/[\\/]+/).filter((s) => s && s !== '.' && s !== '..').pop() || 'run')
const FAMILY_EXPECTED_REPORT = (findingsDir) => familyScratch(findingsDir) + '/review.out.md'

// The runner's output_path must satisfy family-stage-result.schema.json (^scratch/(?!.*\.\.), max 300)
// and be this run's own review.out.md; backslashes are normalised so Windows and POSIX runs both match.
function familyOutputPathError(outputPath, findingsDir) {
  const norm = String(outputPath).replace(/\\/g, '/')
  if (!/^scratch\/(?!.*\.\.)/.test(norm) || norm.length > 300) return 'runner output_path fails the family-stage-result pattern: ' + norm.slice(0, 200)
  const expected = FAMILY_EXPECTED_REPORT(findingsDir)
  if (norm !== expected) return 'runner output_path is ' + norm.slice(0, 200) + ', expected ' + expected
  return ''
}

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// The land step's only accepted reply: LANDED: <out> <N> bytes, N a positive integer.
const familyLandAckOk = (reply, out) => new RegExp('^LANDED: ' + escapeRegExp(out) + ' ([1-9][0-9]*) bytes$').test(String(reply).trim())

const familyFallbackAckOk = (reply, out) => new RegExp('^DONE:\\s*' + escapeRegExp(out) + '\\s*\\.?$').test(String(reply).trim())

function familyRunnerPrompt(binding, family, diffPatchPath, findingsDir) {
  const scratch = familyScratch(findingsDir)
  return [
    'You are coordinator:family-stage-runner dispatched as the opt-in family review leg of a review-wave Workflow,',
    'per ' + pluginPath('agents/family-stage-runner.md') + '.',
    OBJECTIVE_RULE,
    '',
    'Stage binding: ' + binding + ' — its roles.review is the default; the Family below is this run\'s choice and wins.',
    'Family: ' + family,
    'Stage: review',
    'Scratch dir: ' + scratch,
    'Stage prompt: review the frozen diff at ' + diffPatchPath + ' in full (not a chunked subset) for correctness,',
    'integrity and portability defects. Use the severity scale (P0/P1/P2/nit) and the structured findings format of',
    pluginPath('agents/code-reviewer-weekly.md') + '\'s sections and finding structure. Read-only: change no repo file.',
    'Emit the full findings report as your stdout response itself. Never write a findings file and never answer with',
    'a DONE pointer: the report body on stdout is what gets captured as the stage output.',
    ...ESCALATE_LINES,
    '',
    'Return the family-stage-result JSON record and nothing else.',
  ].join('\n')
}

function familyLandPrompt(outputPath, findingsDir) {
  const out = FAMILY_OUT(findingsDir)
  return [
    'You are a relay dispatched by a review-wave Workflow. Do NOT review anything.',
    'Copy the file ' + outputPath + ' (a findings report produced by another reviewer) byte for byte to exactly ONE path: ' + out,
    'Use a shell copy, not a re-typed Write: cp "' + outputPath + '" "' + out + '", then cmp "' + outputPath + '" "' + out + '".',
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    'If the source file is missing or empty, or cmp reports a difference, reply BLOCKED: <reason>.',
    'Otherwise take the byte count N from wc -c < "' + out + '" and reply exactly:',
    'LANDED: ' + out + ' N bytes',
    'with N replaced by that number — nothing else.',
  ].join('\n')
}

function familyFallbackPrompt(diffPatchPath, findingsDir, family) {
  const out = FAMILY_OUT(findingsDir)
  return [
    'You are a Sonnet code-reviewer-weekly instance dispatched as the Claude fallback for the ' + family + ' family review leg of a review-wave Workflow.',
    'Per ' + pluginPath('agents/code-reviewer-weekly.md') + ': you have Write access to exactly ONE output path and no other.',
    OBJECTIVE_RULE,
    '',
    'Review scope: the full frozen diff at ' + diffPatchPath + ' (not a chunked subset).',
    '',
    'Write your findings ONLY to: ' + out,
    'Write incrementally as you go (re-write the full file each time; Write is full-file, not Edit).',
    'Do NOT write to any other path. Do NOT commit, stage, or push. Do NOT invoke any other agent.',
    '',
    ...ESCALATE_LINES,
    '',
    'Use the standard severity scale (P0/P1/P2/nit) and structured findings format from',
    pluginPath('agents/code-reviewer-weekly.md') + '. When done, verify your file exists on disk (ls -la) before',
    'replying. Reply DONE: ' + out + ' — nothing else.',
  ].join('\n')
}

const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

// End index of the brace-balanced span starting at s (string-literal aware), or -1.
function balancedEnd(raw, s) {
  let depth = 0
  let inStr = false
  for (let i = s; i < raw.length; i++) {
    const c = raw[i]
    if (inStr) {
      if (c === '\\') i++
      else if (c === '"') inStr = false
    } else if (c === '"') inStr = true
    else if (c === '{') depth++
    else if (c === '}' && --depth === 0) return i
  }
  return -1
}

// A reply may wrap the record in prose that itself holds braces: take every balanced span that parses
// to a plain object, preferring the last one carrying a verdict.
function parseRunnerRecord(raw) {
  if (isPlainObject(raw)) return raw
  if (typeof raw !== 'string') return null
  const found = []
  for (let s = raw.indexOf('{'); s >= 0; s = raw.indexOf('{', s + 1)) {
    const e = balancedEnd(raw, s)
    if (e < 0) continue
    try {
      const v = JSON.parse(raw.slice(s, e + 1))
      if (isPlainObject(v)) { found.push(v); s = e }
    } catch (_) { /* prose braces, not a record */ }
  }
  return found.filter((v) => 'verdict' in v).pop() || found.pop() || null
}

// The family's own result is only an OK/WARN record from the bound family. A BLOCKED or FAILED
// record, an unusable reply, or a record from another family is a miss that reruns on Claude.
function familyMiss(record, family) {
  if (!record) return 'runner reply absent or not a JSON record'
  if (record.verdict === 'BLOCKED' || record.verdict === 'FAILED') return String(record.verdict)
  if (record.verdict !== 'OK' && record.verdict !== 'WARN') return 'runner verdict unusable: ' + String(record.verdict)
  if (record.family !== family) return 'runner record names family ' + String(record.family) + ', not ' + family
  return ''
}

let familyReview = null

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

const familyThunks = FAMILY_BINDING && !args.skipCodeSemantics
  ? [async () => {
      let raw = null
      try {
        raw = await agent(familyRunnerPrompt(FAMILY_BINDING, REVIEW_FAMILY, args.diffPatchPath, args.findingsDir), {
          agentType: 'coordinator:family-stage-runner',
          model: 'sonnet',
          phase: 'Review',
          label: 'chunk:' + FAMILY_LEG_ID,
        })
      } catch (_) { raw = null }
      const parsed = parseRunnerRecord(raw)
      const miss = familyMiss(parsed, REVIEW_FAMILY)
      const runner = { family: REVIEW_FAMILY, record: parsed, raw: parsed ? null : (raw == null ? null : String(raw)) }
      let landError = ''
      if (!miss) {
        const outputPath = parsed && typeof parsed.output_path === 'string' ? parsed.output_path : ''
        if (!outputPath) landError = 'runner record carries no output_path'
        else if ((landError = familyOutputPathError(outputPath, args.findingsDir)) === '') {
          try {
            // the land step runs cp/cmp/wc, so it needs a shell; code-reviewer-weekly has none
            const landed = await agent(familyLandPrompt(FAMILY_EXPECTED_REPORT(args.findingsDir), args.findingsDir), {
              agentType: 'general-purpose',
              model: 'sonnet',
              phase: 'Review',
              label: 'chunk:' + FAMILY_LEG_ID + '-land',
            })
            if (!familyLandAckOk(landed, FAMILY_OUT(args.findingsDir))) landError = 'land reply: ' + String(landed).slice(0, 200)
          } catch (err) { landError = 'land agent threw: ' + String(err && err.message || err) }
        }
        if (!landError) {
          familyReview = { family: REVIEW_FAMILY, binding: FAMILY_BINDING, runner, fallback: null, fallbackUsed: false, landedAt: FAMILY_OUT(args.findingsDir) }
          return null
        }
      }
      runner.miss = miss || ('family output not landed in findingsDir: ' + landError)
      let fallbackRaw = null
      let fallbackError = ''
      try {
        fallbackRaw = await agent(familyFallbackPrompt(args.diffPatchPath, args.findingsDir, REVIEW_FAMILY), {
          agentType: 'coordinator:code-reviewer-weekly',
          model: 'sonnet',
          phase: 'Review',
          label: 'chunk:' + FAMILY_LEG_ID + '-claude-fallback',
        })
      } catch (err) { fallbackRaw = null; fallbackError = String(err && err.message || err) }
      if (!fallbackError) {
        const text = fallbackRaw == null ? '' : (typeof fallbackRaw === 'string' ? fallbackRaw : JSON.stringify(fallbackRaw))
        if (!familyFallbackAckOk(text, FAMILY_OUT(args.findingsDir))) {
          fallbackError = fallbackRaw == null ? 'fallback reply was null' : (text.trim() ? text.slice(0, 200) : 'fallback reply was empty')
        }
      }
      familyReview = {
        family: REVIEW_FAMILY, binding: FAMILY_BINDING, runner,
        fallback: { family: 'claude', result: fallbackRaw == null ? null : fallbackRaw, ...(fallbackError ? { error: fallbackError } : {}) },
        fallbackUsed: true,
        fallbackFailed: !!fallbackError,
      }
      return null
    }]
  : []

const reviewResults = (await parallel([...chunkThunks, securityThunk, ...familyThunks])).filter(Boolean)

log('review-wave complete: reviewers=' + reviewResults.length + ' (chunks=' + chunkThunks.length + ' + security). ' +
    (familyReview ? 'Family review leg (' + REVIEW_FAMILY + '): ' + (familyReview.fallbackUsed ? (familyReview.fallbackFailed ? 'fell back to claude, and the fallback failed (' + familyReview.fallback.error + '). ' : 'fell back to claude. ') : 'ok. ') : '') +
    'Verdict: run weekly-gate-synthesize.py over ' + args.findingsDir)

return familyReview
  ? { findingsDir: args.findingsDir, chunks: chunkThunks.length, results: reviewResults, familyReview }
  : { findingsDir: args.findingsDir, chunks: chunkThunks.length, results: reviewResults }
