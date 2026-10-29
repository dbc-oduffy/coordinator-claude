/*
 * roadmap-blitz — background-Workflow encoding of one batched roadmap run.
 *
 * Spec: coordinator/skills/roadmap-blitz/SKILL.md (+ roadmap-blitz-contract.json); doctrine:
 * coordinator/docs/wiki/planning/roadmap-blitz.md.
 *
 * One XL sizing (`xl_exit: roadmap`), corpus to frozen gate report: Synthesize, Substantiate,
 * Review, Approve (the single gate), Stage. NOT a stager, committer, approval.json writer, PM-asker
 * (hands-on returns `awaitingApproval`), retirer, EM-gated wave
 * (A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ), plan-blitz, or stub sizer.
 *
 * args: repoRoot (ABSOLUTE), sizing, interactionMode (hands-on|pm|ceo), trailDir REQUIRED; approver,
 * corpus, runId (^[a-z0-9][a-z0-9-]*$), approval (hands-on resume), pluginAgentsAvailable,
 * chatty + chattyReview, provisionSidecarCli, pluginRoot (ABSOLUTE; briefs cite doctrine under it).
 *
 * Returns: { gate_report_path, roadmapId, roadmapDir, approver, approval, awaitingApproval, stage,
 *            owedRetirements, incidents, trailDir } — gate_report_path is null on every path that
 *            did not stage.
 */

// No apostrophe in a `detail` string: the engine pairs quotes naively and a stray one hides every
// phase declared after it.
export const meta = {
  name: 'roadmap-blitz',
  description: 'One batched roadmap run: planner synthesizes, haiku scouts research, reviewers apply findings, one approval gate, then the planner stages and fills the stubs.',
  phases: [
    { title: 'Synthesize', detail: 'One roadmap-planner writes inventory, clusters, reconciliation and any resolutions.' },
    { title: 'Substantiate', detail: 'Haiku scouts (batches of 4 clusters, at most 8 at once), then the planner authors OVERVIEW and peer-team asks.' },
    { title: 'Review', detail: 'Fires unconditionally; sequential, or one chatty wave when args.chatty and args.chattyReview are set. Each reviewer applies its own findings.' },
    { title: 'Approve', detail: 'The single gate. The APM clears pm and ceo modes; hands-on returns awaitingApproval.' },
    { title: 'Stage', detail: 'The planner runs roadmap.blitz_stage, then fills each staged stub and STUB-INDEX.' },
  ],
}

// BEGIN workflow-shared (synced from workflows/_shared/fanout-helpers.mjs)
// Model tiers. Sonnet is the default; haiku only for schema-bound read-only legs on the leg-register
// floor; opus is PM-gated and every opus site carries an `opus-ruling: <ruling ref>` and an `opus-justified: <reason>` comment.
const TIER = {HAIKU: 'haiku', SONNET: 'sonnet', OPUS: 'opus'}
// Split items into batches of at most maxPerAgent (default 10); one batch is one agent's work.
const batchItems = (items, {maxPerAgent = 10} = {}) => {
  const n = Math.max(1, Math.floor(maxPerAgent)), out = []
  for (let i = 0; i < items.length; i += n) out.push(items.slice(i, i + n))
  return out
}
// A fanned-out agent returns a pointer, never its payload.
const PATH_SUMMARY_SCHEMA = {type: 'object', properties: {path: {type: 'string'}, summary: {type: 'string', maxLength: 400}, counts: {type: 'object', additionalProperties: {type: 'number'}}}, required: ['path', 'summary']}
// Append to a prompt: instructs the agent to write its payload to a file and return path + summary.
const pathSummary = prompt => `${prompt}\n\nWrite your full payload to a file under your sidecar/scratch directory and return ONLY {path, summary, counts}: path is that file, summary is at most 400 characters, counts is a flat object of numbers. Never inline the payload in your reply.`
// Replace every occurrence of slot with batonId through a string, array or plain-object tree.
const fillBaton = (value, batonId, slot) => {
  if (typeof value === 'string') return value.split(slot).join(batonId)
  if (Array.isArray(value)) return value.map((v) => fillBaton(v, batonId, slot))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fillBaton(v, batonId, slot)]))
  }
  return value
}
// END workflow-shared

const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  throw new Error(
    'roadmap-blitz received no args object (got ' + String(parsedArgs) + '). See the args contract ' +
    'at the top of this file.'
  )
}

const INTERACTION_MODES = ['hands-on', 'pm', 'ceo']

// Agrees with the engine's approver_for; an unknown mode throws (a silent default misroutes approval).
function approverFor(interactionMode) {
  if (!INTERACTION_MODES.includes(interactionMode)) {
    throw new Error(
      'roadmap-blitz: interactionMode ' + JSON.stringify(interactionMode) + ' is not one of ' +
      INTERACTION_MODES.join(' | ')
    )
  }
  return interactionMode === 'hands-on' ? 'pm' : 'apm'
}

const APPROVER = approverFor(parsedArgs.interactionMode)
if (typeof parsedArgs.approver === 'string' && parsedArgs.approver.trim() && parsedArgs.approver.trim() !== APPROVER) {
  throw new Error(
    'roadmap-blitz: supplied approver ' + JSON.stringify(parsedArgs.approver) + ' disagrees with ' +
    'approverFor(' + parsedArgs.interactionMode + ') = ' + APPROVER
  )
}

const str = (v) => (typeof v === 'string' && v.trim() ? v.trim() : null)
const REPO_ROOT = str(parsedArgs.repoRoot)
const SIZING = str(parsedArgs.sizing)
const TRAIL_DIR = str(parsedArgs.trailDir)
const PROVISION_SIDECAR_CLI = str(parsedArgs.provisionSidecarCli)
const PLUGIN_ROOT = str(parsedArgs.pluginRoot)
const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable !== false
const SCOUT_CAP = 8
const SCOUT_BATCH = 4

function balancedGroups(items, max) {
  if (!items.length) return []
  const k = Math.ceil(items.length / max)
  const base = Math.floor(items.length / k)
  const extra = items.length % k
  const out = []
  let at = 0
  for (let g = 0; g < k; g++) {
    const size = base + (g < extra ? 1 : 0)
    out.push(items.slice(at, at + size))
    at += size
  }
  return out
}

const RUN_ID = str(parsedArgs.runId) ||
  (SIZING ? SIZING.split('/').pop().replace(/\.ya?ml$/, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') : null)
const RUN_ID_OK = !!RUN_ID && /^[a-z0-9][a-z0-9-]*$/.test(RUN_ID)
const ROADMAP_DIR = `state/roadmap/${RUN_ID}`

function withRole(agentType) {
  return PLUGIN_AGENTS && agentType ? { agentType } : {}
}

/* BEGIN RETURN_TLDR_SCHEMA */
const RETURN_TLDR_SCHEMA = {"type":"object","additionalProperties":false,
 "required":["verdict","decisions","counts","sidecar"],
 "properties":{
  "verdict":{"type":"string","enum":["OK","WARN","BLOCKED","PIVOT","FAILED"]},
  "decisions":{"type":"array","maxItems":5,"items":{"type":"object","additionalProperties":false,
    "required":["item","anchor"],
    "properties":{"item":{"type":"string","maxLength":200},"anchor":{"type":"string","maxLength":240}}}},
  "counts":{"type":"object","maxProperties":12,"additionalProperties":{"type":"integer","minimum":0}},
  "sidecar":{"type":["string","null"],"maxLength":240}}}
/* END RETURN_TLDR_SCHEMA */

const SYNTH_SCHEMA = {
  type: 'object',
  required: ['status', 'clusters', 'ownedRetirements', 'conflicts', 'tldr'],
  properties: {
    status: { type: 'string', enum: ['synthesized', 'blocked'] },
    blockedReason: { type: 'string' },
    clusters: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'title', 'verdict', 'external'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          verdict: { type: 'string', enum: ['KEEP', 'MERGE', 'DEFER', 'DROP', 'MOVE'] },
          external: { type: 'boolean' },
        },
      },
    },
    ownedRetirements: { type: 'array', items: { type: 'string' } },
    conflicts: { type: 'integer' },
    crossesRepo: { type: 'boolean' },
    flavor: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const SCOUT_SCHEMA = {
  type: 'object',
  required: ['corpusPaths', 'tldr'],
  properties: {
    corpusPaths: {
      type: 'array',
      items: {
        type: 'object',
        required: ['clusterId', 'path'],
        properties: { clusterId: { type: 'string' }, path: { type: 'string' } },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const OVERVIEW_SCHEMA = {
  type: 'object',
  required: ['overviewPath', 'peerTeamAsks', 'crossesRepo', 'tldr'],
  properties: {
    overviewPath: { type: 'string' },
    peerTeamAsks: { type: 'integer' },
    crossesRepo: { type: 'boolean' },
    flavor: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['sidecarPath', 'verdict', 'tldr'],
  properties: { sidecarPath: { type: 'string' }, verdict: { type: 'string' }, tldr: RETURN_TLDR_SCHEMA },
}

const APPROVAL_SCHEMA = {
  type: 'object',
  required: ['verdict', 'approver', 'ruling', 'ruling_ref', 'tldr'],
  properties: {
    verdict: { type: 'string', enum: ['approved', 'declined'] },
    approver: { type: 'string', enum: ['apm'] },
    ruling: { type: 'string' },
    ruling_ref: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const FILL_SCHEMA = {
  type: 'object',
  required: ['tldr'],
  properties: {
    stageReply: { type: 'object' },
    refused: { type: 'boolean' },
    refusal: { type: 'string' },
    filled: { type: 'integer' },
    paths: { type: 'array', items: { type: 'string' } },
    owedRetirements: { type: 'array', items: { type: 'string' } },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// Every dispatch is counted and rides the result as `incidents`; rejections are re-thrown.
const agentIncidents = []

// Missing `tldr`: fall back to a WARN tldr built in code, anchored at the sidecar. Never flips
// `completed`; no sidecar path yields null and a missing-tldr incident.
function tldrFallback(label, sidecarPath) {
  if (!sidecarPath) return null
  return {
    verdict: 'WARN',
    decisions: [{
      item: `${label} returned no tldr; read its sidecar`.slice(0, 200),
      anchor: String(sidecarPath).slice(0, 240),
    }],
    counts: {},
    sidecar: sidecarPath,
  }
}

function trackAgent(label, call) {
  return Promise.resolve(call).then(
    async (result) => {
      if (result === null || result === undefined) {
        agentIncidents.push({
          role: label,
          kind: 'null-return',
          detail: 'the agent returned nothing, its structured-output call exhausted its retries',
        })
        return result
      }
      if (typeof result === 'object' && !result.tldr) {
        const path = ['sidecarPath', 'overviewPath']
          .map((k) => result[k]).find((v) => typeof v === 'string') || null
        const fallbackTldr = tldrFallback(label, path)
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr` and no sidecar path to anchor a code tldr',
          })
        }
        return fallbackTldr === null ? { ...result, tldr: null } : { ...result, tldr: fallbackTldr, assembled_by: 'code-fallback' }
      }
      return result
    },
    (err) => {
      agentIncidents.push({
        role: label,
        kind: 'errored',
        detail: String((err && (err.message || err.error)) || err).slice(0, 500),
      })
      throw err
    },
  )
}

const slug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

// Paths are ASSIGNED, never chosen: agents picking the same filename destroy each other's write.
const corpusPathFor = (clusterId) => `${ROADMAP_DIR}/research-corpus/${slug(clusterId)}.md`
const reviewPathFor = (role) => `${TRAIL_REL}/review-${slug(role)}.md`

const SIDECAR_HEREDOC_RULE = (label) => `
Your sidecar dir is \`.coordinator-local/workflow-sidecars/roadmap-blitz/${RUN_ID}/${slug(label)}/\` (create it with
\`mkdir -p\`; run notes go there). If the harness denies the Write tool on a path this brief declares
("Subagents should return findings as text"), write that path with a quoted Bash heredoc,
\`cat > <path> <<'EOF'\`, never skip it, and name the path in your report. A path the Write tool has
already written stays on Write/Edit: a heredoc overwrite is refused at commit as blob drift.`

const REPO_ROOT_RULE = REPO_ROOT ? `
Every repo-relative path in this brief is relative to THIS repo root, and nothing else:

    ${REPO_ROOT}

Resolve them there, and change into it before you run anything. Do NOT resolve against your own
working directory: you inherited it from the process that dispatched you, it is not necessarily
this repo. If a path you were given does not exist under that root, say so; never search for a
plausible substitute elsewhere on the box.` : ''

const CLI_RESOLUTION_RULE = `
Every coordinator CLI named in this brief is invoked BY ABSOLUTE PATH through the settings home,
never as a bareword, because no coordinator CLI is reliably on PATH. On a POSIX host:

    "\${COORDINATOR_SETTINGS_HOME:-\${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>"

On a PowerShell host, guard first (unset is the DEFAULT state of a fresh shell) and call the \`.exe\`:

    if (-not $env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME = Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings" }
    & "$env:COORDINATOR_SETTINGS_HOME\\bin\\<cli>.exe" <args>

Canonical rule: \`snippets/resolve-coordinator-bin.md\`. A CLI that still does not run after
resolving it this way is a finding: report the failure verbatim, never invent a substitute or
hand-author the record the CLI would have written.`

// provision-sidecar refuses a bare role: --agent-type must be the plugin-qualified identity.
const qualifyAgentType = (t) => (t.includes(':') ? t : `coordinator:${t}`)

const SIDECAR_RULE = (role) => PROVISION_SIDECAR_CLI
  ? `Get your findings sidecar path by running this EXACT resolved invocation, and do not construct
one by hand:

    ${PROVISION_SIDECAR_CLI} --type review-findings --agent-type ${qualifyAgentType(role)}

It prints the repo-relative sidecar path on stdout. Use what it prints; on failure, report the
failure verbatim and stop.`
  : `Provision your findings sidecar with the resolved \`coordinator-doc-new --type review-findings
--agent-type ${qualifyAgentType(role)}\` (resolution rule above) and use the path it prints; never invent a path.`

const WRITE_SCOPE_RULE = `
Write only inside the roadmap directory and the trail named in this brief, and the one record this
brief assigns you. Never scaffold a stub, number one, run any stub-emitting CLI, or write a plan,
baton, sizing or goal artifact: staging belongs to the one engine call the Stage planner runs.`

const ROLE_CONTRACTS = {
  planner: `You are the roadmap-planner inside one roadmap-blitz run: you author the roadmap-planning
artifacts for ONE roadmap and nothing else. You never size, approve, stage or execute, and you
never dispatch another agent. The interactive PM rounds are replaced by this run's single Approve
gate after review; do not stop to ask the PM or the EM.`,
  scout: `You are a research scout inside one roadmap-blitz run. You research the clusters of one
batch and write one corpus file per cluster. You never edit any roadmap artifact other than those files.`,
}

// Doctrine files live in the plugin tree, never under the consumer repo.
const pluginPath = (rel) => `${PLUGIN_ROOT || '<plugin-root>'}/${rel}`

const PLUGIN_ROOT_RULE = PLUGIN_ROOT ? '' : `
No \`pluginRoot\` was bound: a path written \`<plugin-root>/...\` in this brief is under the
coordinator plugin root, which \`snippets/resolve-coordinator-bin.md\` explains how to resolve. A
repo-relative \`coordinator/...\` path does not exist in a consumer repo; never read one.`

const FRICTION_RULE = `
Close the record you write with one line \`Friction: <what this brief should have told you>\` (\`none\` is a fine answer).`

const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

const OBJECTIVE_RULE = `When state/warp/<run_id>/objective.json exists, read it first and carry its axes; never report "unknown".`

const COMMON = `${REPO_ROOT_RULE}\n${CLI_RESOLUTION_RULE}${PLUGIN_ROOT_RULE}${FRICTION_RULE}\n${MID_RUN_DIRECTION_RULE}\n${OBJECTIVE_RULE}`

// Chatty review wave (args.chatty and args.chattyReview): the roadmap reviewers run concurrently
// on one roster. fillBaton comes from the shared block above.
const fillPeers = (brief, peersSlot, slotTypes) =>
  brief.split(peersSlot).join(slotTypes.map(([slot, type]) => `${slot} = ${type}`).join('\n'))

const WAVE_STAGE_SCHEMA = { type: 'object', properties: { done: { type: 'boolean' } } }
const SURVEY_SCHEMA = {
  type: 'object',
  required: ['continuations'],
  properties: {
    continuations: {
      type: 'array',
      items: {
        type: 'object',
        required: ['role'],
        properties: { role: { type: 'string' }, agent_id: { type: ['string', 'null'] } },
      },
    },
  },
}

// One sonnet call reviews the whole wave: every lens in turn, one review record per role.
const batchedReviewBrief = (reviewers) => {
  const roles = reviewers.map((r) => r.split(':')[1])
  return `You are reviewing a roadmap authored inside one roadmap-blitz run. Read ${ROADMAP_DIR}/OVERVIEW.md,
peer-team-asks.md, clusters.md and reconciliation.md, plus the research files they cite.

You carry ${roles.length} review lens${roles.length > 1 ? 'es' : ''}, one after another: ${roles.join(', ')}. For each lens, read
${reviewers.map((r) => pluginPath(`agents/${r.split(':')[1]}.md`)).join(', ')} (its own file) and judge as that role would.

Judge the roadmap on its own merits: coverage of the sizing ${SIZING}, cluster boundaries, ordering,
and whether any cluster is a unit of dispatch masquerading as a unit of coverage. Then APPLY your
own findings to the roadmap files yourself, because nothing downstream reads a finding that is only
in your summary. Findings you cannot resolve go in OVERVIEW under the cluster's \`### Contested\`
heading. A \`**blocked_by:**\` line in clusters.md carries only cluster ids, or none: never a
parenthetical or prose, since blitz_stage parses every id on it as an edge. Put a review note about
a dependency on its own separate line. You never approve, never stage, and never write outside ${ROADMAP_DIR}/ and your sidecar.

${SIDECAR_RULE(roles[0])}
${COMMON}
${SIDECAR_HEREDOC_RULE(`review:${roles[0]}`)}
Write one review record per lens to EXACTLY these paths, where the Approve gate reads them, and
return the provisioned findings sidecar path as \`sidecarPath\`. Return verdict BLOCKED if any lens
blocks the roadmap:

${roles.map((role) => `    ${reviewPathFor(role)}`).join('\n')}`
}

async function chattyStage(label, prompt, schema) {
  try {
    return await agent(prompt, { model: 'sonnet', label: `chatty-stage:${label}`, phase: 'Review', schema })
  } catch (err) {
    agentIncidents.push({ role: label, kind: 'errored', detail: String((err && (err.message || err.error)) || err).slice(0, 500) })
    return null
  }
}

async function chattyReviewWave(reviewers) {
  const raw = parsedArgs.chatty === true ? parsedArgs.chattyReview : null
  if (!raw || typeof raw !== 'object' || !raw.roster || !Array.isArray(raw.roster.members)) return null
  const slots = raw.roster.members.map((m) => m.role).filter((r) => /^review-\d+$/.test(r))
  if (!reviewers.length || reviewers.length > slots.length) return null

  const wave = fillBaton(raw, RUN_ID, raw.batonSlot || '{BATON}')
  const brief = () => batchedReviewBrief(reviewers) + fillPeers(wave.memberBriefs[slots[0]], wave.peersSlot || '{PEERS}', [[slots[0], 'general-purpose']])
  const lenses = reviewers.map((r) => r.split(':')[1]).join('+')
  const dispatch = (text) => trackAgent(`review:${lenses}`, agent(text, {
    model: 'sonnet', ...withRole('general-purpose'), label: `chatty-review:${lenses}`, phase: 'Review', schema: REVIEW_SCHEMA,
  })).catch((err) => {
    agentIncidents.push({ role: `chatty-review:${lenses}`, kind: 'errored', detail: String((err && (err.message || err.error)) || err).slice(0, 500) })
    return null
  })

  if (!(await chattyStage('chatty-overseer', wave.overseerPrompt, WAVE_STAGE_SCHEMA))) {
    agentIncidents.push({ role: 'chatty-overseer', kind: 'wave-unavailable', detail: 'the overseer returned nothing; the reviewers run sequentially' })
    return null
  }
  let settled = await dispatch(brief())

  // The survey reads every settled review, so the two fan-outs are a true barrier, not a pipeline.
  const survey = await agent(wave.surveyPrompt, { model: 'sonnet', label: 'chatty-stage:chatty-survey', phase: 'Review', schema: SURVEY_SCHEMA })
    .catch((err) => {
      agentIncidents.push({ role: 'chatty-survey', kind: 'errored', detail: String((err && (err.message || err.error)) || err).slice(0, 500) })
      return null
    })
  if (((survey && survey.continuations) || []).some((c) => c.role === slots[0])) {
    const nonce = `${RUN_ID}-${slots[0]}-cont`
    const next = await dispatch(brief() + String(wave.continuationBriefs[slots[0]]).split(wave.nonceSlot || '{NONCE}').join(nonce))
    if (next) settled = next
  }

  await chattyStage('chatty-summary', wave.summaryPrompt, WAVE_STAGE_SCHEMA)
  return settled
}

function emptyResult(extra) {
  return {
    gate_report_path: null,
    roadmapId: RUN_ID,
    roadmapDir: RUN_ID ? ROADMAP_DIR : null,
    approver: APPROVER,
    approval: null,
    awaitingApproval: false,
    stage: null,
    owedRetirements: [],
    incidents: agentIncidents,
    trailDir: TRAIL_DIR,
    ...extra,
  }
}

if (!REPO_ROOT) return emptyResult({ refused: [{ reason: 'no repoRoot supplied: every brief would resolve its repo-relative paths against the dispatching shell' }] })
if (!SIZING) return emptyResult({ refused: [{ reason: 'no sizing supplied: the roadmap has no accepted sizing to run from' }] })
if (!TRAIL_DIR) return emptyResult({ refused: [{ reason: 'no trailDir supplied: the review sidecars have nowhere durable to land' }] })
const TRAIL_ROOT = REPO_ROOT.replace(/\\/g, '/').replace(/\/+$/, '')
const TRAIL_ABS = TRAIL_DIR.replace(/\\/g, '/')
const TRAIL_REL = (TRAIL_ABS.startsWith(TRAIL_ROOT + '/') ? TRAIL_ABS.slice(TRAIL_ROOT.length + 1) : TRAIL_ABS).replace(/\/+$/, '')
if (!TRAIL_REL.startsWith('scratch/') || TRAIL_REL.split('/').includes('..')) {
  return emptyResult({ refused: [{ reason: 'trailDir ' + JSON.stringify(TRAIL_DIR) + ' does not resolve to a repo-relative path under scratch/' }] })
}
if (!RUN_ID_OK) return emptyResult({ refused: [{ reason: 'runId ' + JSON.stringify(RUN_ID) + ' does not match ^[a-z0-9][a-z0-9-]*$' }] })

const CORPUS = Array.isArray(parsedArgs.corpus) && parsedArgs.corpus.length
  ? parsedArgs.corpus.filter((p) => typeof p === 'string' && p.trim())
  : null
const CORPUS_RULE = CORPUS
  ? `The input corpus, one repo-relative path each:\n${CORPUS.map((p) => `  - ${p}`).join('\n')}`
  : `The input corpus is the sizing ${SIZING}, the baton its \`baton:\` field names, and every path its
\`premise.evidence\` cites. Read the sizing first and derive the list; never widen it by sweeping the repo.`


let synth = null
let overview = null
let approval = null
let owedRetirements = []

const RESUME_APPROVAL = parsedArgs.approval === undefined || parsedArgs.approval === null ? null : parsedArgs.approval
const RESUMING = RESUME_APPROVAL !== null
if (RESUMING) {
  if (APPROVER !== 'pm') {
    return emptyResult({ refused: [{ reason: 'approval supplied but interactionMode ' + parsedArgs.interactionMode + ' clears at apm: only a hands-on run resumes from a recorded approval' }] })
  }
  if (typeof RESUME_APPROVAL !== 'object' || Array.isArray(RESUME_APPROVAL)) {
    return emptyResult({ refused: [{ reason: 'approval supplied but holds no readable approval record' }] })
  }
  // The emitter refuses a resume with no OVERVIEW.md before binding the approval.
  if (RESUME_APPROVAL.approver !== 'pm') {
    return emptyResult({ approval: RESUME_APPROVAL, refused: [{ reason: 'the recorded approval names approver ' + JSON.stringify(RESUME_APPROVAL.approver) + ', not pm' }] })
  }
  if (RESUME_APPROVAL.verdict !== 'approved') {
    return emptyResult({ approval: RESUME_APPROVAL, refused: [{ reason: 'the recorded PM verdict is ' + JSON.stringify(RESUME_APPROVAL.verdict) + ', not approved; nothing is staged' }] })
  }
  approval = RESUME_APPROVAL
}


if (!approval) {
  // Every roadmap-planner call below is pinned model 'opus', effort 'high' or 'medium', never inherited or low.
  synth = await trackAgent('roadmap-planner:synthesize', agent(
    `${ROLE_CONTRACTS.planner}

Run roadmap-planning Phase 1, Steps 1 through 4, over the corpus below, into ${ROADMAP_DIR}/.
Read ${pluginPath('skills/roadmap-planning/SKILL.md')} § Phase 1 and follow it. The accepted sizing is ${SIZING}.

${CORPUS_RULE}

Write exactly these files:
  - ${ROADMAP_DIR}/inventory.md. The inventory row MARKS each input that is a live plan under docs/plans/.
  - ${ROADMAP_DIR}/clusters.md. Each cluster is a \`## <id> — <title>\` heading carrying a \`**loe:**\`
    line (the whole-baton t-shirt read), a \`**blocked_by:**\` line (only cluster ids, or none: no parentheticals or prose, because
    blitz_stage parses every id on it as an edge; a note goes on its own separate line), and an
    \`**external:**\` yes or no line: yes only when answering the cluster needs the web, no when the
    repo itself is the research. blitz_stage parses these lines and refuses a cluster without loe.
  - ${ROADMAP_DIR}/reconciliation.md. One verdict per cluster (MERGE, DEFER, KEEP, DROP, MOVE); the
    verdict count equals the cluster count.
  - ${ROADMAP_DIR}/COORDINATOR-RESOLUTIONS.md only when inputs conflict.

Return \`clusters\` (id, title, verdict, external for every cluster), \`ownedRetirements\` (the live
plans the inventory marked), and \`conflicts\` (count).
${WRITE_SCOPE_RULE}
${COMMON}
${SIDECAR_HEREDOC_RULE('roadmap-planner:synthesize')}`,
    { model: 'opus', effort: 'high', /* opus-justified: roadmap-planner authors the roadmap; opus-ruling: G-EM-2026-10-27-R3 */ ...withRole('coordinator:roadmap-planner'),
      label: 'roadmap-planner:synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA },
  ))
  if (!synth || synth.status !== 'synthesized') {
    return emptyResult({ refused: [{ reason: (synth && synth.blockedReason) || 'the roadmap-planner returned no synthesis' }] })
  }
  owedRetirements = synth.ownedRetirements || []

  const researchable = synth.clusters.filter((c) => c.verdict === 'KEEP' || c.verdict === 'MERGE')
  // External and repo clusters never share a scout: the two research differently.
  const groups = [
    ...balancedGroups(researchable.filter((c) => c.external), SCOUT_BATCH),
    ...balancedGroups(researchable.filter((c) => !c.external), SCOUT_BATCH),
  ]
  const scouts = []
  for (let i = 0; i < groups.length; i += SCOUT_CAP) {
    const wave = groups.slice(i, i + SCOUT_CAP)
    const done = await parallel(wave.map((group) => () => trackAgent(`scout:${group[0].id}+${group.length}`, agent(
      `${ROLE_CONTRACTS.scout}

Research these ${group.length} cluster(s) for the roadmap at ${ROADMAP_DIR}/. Read ${ROADMAP_DIR}/clusters.md
for each cluster, and the corpus files it cites.
${group[0].external
  ? 'These clusters are marked external: yes. Research them on the web and cite each source by URL.'
  : 'These clusters are marked external: no. The repo is the research: read the code, plans and wikis each touches and cite each by repo-relative path. Do not search the web.'}

Clusters and the EXACT path each one's record is written to:
${group.map((c) => `  - ${c.id} (${c.title}) -> ${corpusPathFor(c.id)}`).join('\n')}

Write one file per cluster with what a stub author needs: current state, constraints, prior art, open questions.
${COMMON}
${SIDECAR_HEREDOC_RULE(`scout:${group[0].id}+${group.length}`)}
Return \`corpusPaths\`: one {clusterId, path} per cluster you wrote, the path verbatim as assigned above.`,
      { model: 'haiku', ...withRole(group[0].external ? 'coordinator:research-scout' : 'coordinator:repo-scout'),
        label: `scout:${group[0].id}+${group.length}`, phase: 'Substantiate', schema: SCOUT_SCHEMA },
    )).catch(() => null)))
    scouts.push(...done)
  }
  const gotPaths = new Set(scouts.filter(Boolean).flatMap((s) => (s.corpusPaths || []).map((p) => p.clusterId)))
  const missingScouts = researchable.filter((c) => !gotPaths.has(c.id)).map((c) => c.id)

  overview = await trackAgent('roadmap-planner:overview', agent(
    `${ROLE_CONTRACTS.planner}

Run roadmap-planning Phase 1.5, Steps 2 and 3. The corpus is in ${ROADMAP_DIR}/research-corpus/.
${missingScouts.length ? `These clusters have no research file because their scout failed; say so in their Contested section rather than inventing research: ${missingScouts.join(', ')}.` : ''}

Write:
  - ${ROADMAP_DIR}/OVERVIEW.md: one section per KEEP cluster, headed by NAME and never by number,
    each with a \`### Contested\` subsection. Frontmatter \`status: draft\`; the Approve phase
    stamps the final status, not you.
  - ${ROADMAP_DIR}/peer-team-asks.md: present even when empty, as \`- None identified at authoring time.\`
    Template: ${pluginPath('skills/roadmap-planning/residue/peer-team-ask-format.md')}.

Return \`peerTeamAsks\` (the count of asks), \`crossesRepo\` (true when any cluster crosses a repo
boundary), and \`flavor\` (a domain flavor such as data, ux or front-end when one reviewer should read
the roadmap, else an empty string).
${WRITE_SCOPE_RULE}
${COMMON}
${SIDECAR_HEREDOC_RULE('roadmap-planner:overview')}`,
    { model: 'opus', effort: 'high', /* opus-justified: roadmap-planner authors the roadmap; opus-ruling: G-EM-2026-10-27-R3 */ ...withRole('coordinator:roadmap-planner'),
      label: 'roadmap-planner:overview', phase: 'Substantiate', schema: OVERVIEW_SCHEMA },
  ))
  if (!overview) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'the roadmap-planner returned no OVERVIEW' }] })
  }

  const needsDirector = overview.peerTeamAsks > 0 || overview.crossesRepo || synth.crossesRepo
  const DOMAIN_REVIEWER = { data: 'coordinator:staff-data-sci', ux: 'coordinator:staff-ux', 'front-end': 'coordinator:senior-front-end' }
  const flavor = (overview.flavor || synth.flavor || '').toLowerCase()
  const reviewers = [needsDirector ? 'coordinator:eng-director' : 'coordinator:staff-eng']
  if (DOMAIN_REVIEWER[flavor]) reviewers.push(DOMAIN_REVIEWER[flavor])

  const missingReviews = []
  const blockedReviews = []
  const roles = reviewers.map((r) => r.split(':')[1])
  const waveReview = await chattyReviewWave(reviewers)
  const review = waveReview || await trackAgent(`review:${roles.join('+')}`, agent(
    batchedReviewBrief(reviewers),
    { model: 'sonnet', ...withRole('general-purpose'), label: `review:${roles.join('+')}`, phase: 'Review', schema: REVIEW_SCHEMA },
  ))
  if (!review) missingReviews.push(...roles)
  else if (review.verdict === 'BLOCKED') blockedReviews.push(...roles)
  // A BLOCKED review halts before Approve.
  if (blockedReviews.length) {
    agentIncidents.push({ role: `review:${blockedReviews.join(',')}`, kind: 'review-blocked', detail: 'reviewer returned BLOCKED; the run halts before the approval gate' })
    return emptyResult({ owedRetirements, refused: [{ reason: 'review returned BLOCKED for ' + blockedReviews.join(', ') + '; nothing is approved or staged' }] })
  }
  if (missingReviews.length) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'review returned nothing for ' + missingReviews.join(', ') + '; the gate never clears an unreviewed roadmap' }] })
  }
}


if (!approval) {
  if (APPROVER === 'pm') {
    return emptyResult({
      awaitingApproval: true,
      owedRetirements,
      roadmapOverview: `${ROADMAP_DIR}/OVERVIEW.md`,
    })
  }

  const decision = await trackAgent('apm:approve', agent(
    `You are the APM, clearing the single approval gate of one roadmap-blitz run for the PM.

Read ${ROADMAP_DIR}/OVERVIEW.md, ${ROADMAP_DIR}/peer-team-asks.md and the review records under
${TRAIL_DIR}/. Return \`approved\` when the roadmap is coherent, its contested items are named, and no
review finding is left open that a stub author would trip on; return \`declined\` otherwise. Return
\`approver: "apm"\`, \`ruling\` (your verdict as one statement in your own words, recorded verbatim) and
\`ruling_ref\` (the repo-relative path of the record the ruling rests on, such as the review record you
weighed most). This is a decision on the roadmap's shape and its reviews: you do not edit the roadmap
and you write no record; the engine records the approval.
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${OBJECTIVE_RULE}`,
    { model: 'opus', /* opus-justified: approval gate clears or refuses the roadmap; opus-ruling: G-EM-2026-10-27-R3 */ ...withRole('coordinator:apm'), label: 'apm:approve', phase: 'Approve', schema: APPROVAL_SCHEMA },
  ))
  if (!decision) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'the APM returned no verdict; nothing is staged' }] })
  }
  approval = { verdict: decision.verdict, approver: 'apm', ruling: decision.ruling, ruling_ref: decision.ruling_ref }
}

if (approval.verdict !== 'approved') {
  return emptyResult({ approval, owedRetirements, declined: true })
}


const stageApproval = approval.approver === 'pm'
  ? { verdict: approval.verdict, approver: 'pm', utterance: approval.utterance }
  : { verdict: approval.verdict, approver: approval.approver, ruling: approval.ruling, ruling_ref: approval.ruling_ref }
const stageCall = { roadmap: ROADMAP_DIR, approval: stageApproval, trail_dir: TRAIL_REL, interaction_mode: parsedArgs.interactionMode }

const fill = await trackAgent('roadmap-planner:fill-stubs', agent(
  `${ROLE_CONTRACTS.planner}

Two steps, in order.

STEP 1. Run the engine op with exactly this request (roadmap, approval, trail_dir, interaction_mode) and return its JSON reply verbatim as
\`stageReply\` (the op may reply bare or wrapped as { result: {...} }; return the payload):

    <resolved coordinator-invoke> roadmap.blitz_stage '${JSON.stringify(stageCall)}'

An op refusal, or a reply whose \`approval_record\` is null, is an incident: set \`refused: true\`,
put the message in \`refusal\`, fill no stub (see "Fill-stubs brief" in the roadmap-planner definition).
${CLI_RESOLUTION_RULE}

STEP 2. Follow the "Fill-stubs brief" section of ${pluginPath('agents/roadmap-planner.md')} over the
stubs the reply from step 1 names. OVERVIEW: ${ROADMAP_DIR}/OVERVIEW.md; index: ${ROADMAP_DIR}/STUB-INDEX.md.
${COMMON}
${SIDECAR_HEREDOC_RULE('roadmap-planner:fill-stubs')}
${RESUMING ? `Also return \`owedRetirements\`: the repo-relative docs/plans/ paths that ${ROADMAP_DIR}/inventory.md marks as live source plans (empty when there are none or the file is absent).\n` : ''}Return \`stageReply\` (step 1), \`paths\` (every repo-relative path you wrote in step 2) and \`filled\`
(the count of stubs filled). You never commit or stage.`,
  { model: 'sonnet', effort: 'medium', ...withRole('coordinator:roadmap-planner'),
    label: 'roadmap-planner:fill-stubs', phase: 'Stage', schema: FILL_SCHEMA },
))

if (RESUMING && fill && Array.isArray(fill.owedRetirements)) owedRetirements = fill.owedRetirements
else if (RESUMING && fill) agentIncidents.push({
  role: 'roadmap-planner:fill-stubs',
  kind: 'missing-owed-retirements',
  detail: 'resume fill returned no owedRetirements array; owed retirements are unreported',
})

// The op may reply bare or wrapped as { result: {...} }; the staged fields live in the payload.
const rawStageReply = fill && !fill.refused && fill.stageReply ? fill.stageReply : null
const wrapped = rawStageReply && rawStageReply.gate_report_path === undefined ? fill.stageReply.result : null
const stageReply = wrapped && typeof wrapped === 'object' ? wrapped : rawStageReply
if (!stageReply || !stageReply.gate_report_path) {
  if (fill && fill.refused) {
    agentIncidents.push({ role: 'roadmap-planner:fill-stubs', kind: 'stage-refused', detail: String(fill.refusal || '').slice(0, 500) })
  }
  return emptyResult({ approval, owedRetirements, stage: stageReply, staged: false })
}
// Nothing is staged without a durable approval: a null approval_record means the engine did not record it.
if (!stageReply.approval_record) {
  agentIncidents.push({ role: 'roadmap-planner:fill-stubs', kind: 'stage-refused', detail: 'the stage reply carries approval_record: null for an approved call; no stub was filled' })
  return emptyResult({ approval, owedRetirements, stage: stageReply, staged: false, refused: [{ reason: 'the stage reply carries approval_record: null; nothing is staged without a durable approval' }] })
}
if (!(fill.paths && fill.paths.length)) {
  agentIncidents.push({ role: 'roadmap-planner:fill-stubs', kind: 'no-fill', detail: 'the planner returned no written paths; the staged stubs stay skeletal' })
}

return {
  gate_report_path: stageReply.gate_report_path,
  staged: true,
  roadmapId: stageReply.roadmap_id || RUN_ID,
  roadmapDir: ROADMAP_DIR,
  approver: APPROVER,
  approval,
  awaitingApproval: false,
  stage: stageReply,
  uncommitted: fill.paths || [],
  owedRetirements,
  incidents: agentIncidents,
  trailDir: TRAIL_DIR,
}
