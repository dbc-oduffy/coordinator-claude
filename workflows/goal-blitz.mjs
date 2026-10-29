/*
 * goal-blitz — background-Workflow encoding of one batched goal-setting run.
 *
 * Spec: coordinator/skills/goal-blitz/SKILL.md; fixture: coordinator/skills/goal-blitz/goal-blitz-contract.json.
 *
 * Every seed in `args.seeds`, one fire: the VP-Product Reviewer (`coordinator:vp-product`) drafts the OKR into the
 * trail, the APM (`coordinator:apm`) critiques unconditionally, the VP-Product Reviewer integrates, one blitz-em gates
 * readiness, a terminal Ratify phase returns ready drafts in `awaitingRatification`.
 *
 * NOT a goal store writer (the skill's lander writes after a recorded the VP-Product Reviewer ratification), NOT the
 * ratifier (the driver dispatches the VP-Product Reviewer once over the set and records <trailDir>/ratification.json;
 * the VP-Product Reviewer's version is what lands), NOT an EM-gated wave (A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ),
 * NOT plan-blitz.
 *
 * args (bound by workflow.bind_args): repoRoot (ABSOLUTE, REQUIRED; briefs anchor paths here),
 * trailDir (ABSOLUTE, REQUIRED), provisionSidecarCli (ABSOLUTE `coordinator-doc-new`, REQUIRED),
 * interactionMode (hands-on|pm|ceo; ratifierFor derives approver `vp-product`; other values throw),
 * pluginAgentsAvailable (default true), seeds: [{ id, path, kind: 'goal-seed'|'sizing', intent }].
 * scriptPath resolves through `${CLAUDE_PLUGIN_ROOT}/workflows/goal-blitz.mjs`, never a repo-relative prefix.
 *
 * Returns: { ready, pulled, rework, awaitingRatification, ratified, approver, incidents, trailDir }
 */

// No apostrophe in a `detail` string: the engine pairs quotes naively and a stray one hides every
// phase declared after it.
export const meta = {
  name: 'goal-blitz',
  description: 'One batched goal-setting run: the VP-Product Reviewer authors each OKR, the APM critiques every draft, the VP-Product Reviewer integrates, a sonnet agent gates readiness, a terminal Ratify phase hands ready drafts to the VP-Product Reviewer.',
  phases: [
    { title: 'Draft', detail: 'One the VP-Product Reviewer author per seed writes the Objective and Key Results into the trail, never the goal store.' },
    { title: 'Critique', detail: 'One APM pass per draft, unconditional. Per-element PASS, FLAG or REJECT; set verdict GO, REVISE or REFRAME.' },
    { title: 'Integrate', detail: 'the VP-Product Reviewer applies the REJECT and FLAG rewrites, or accepts a FLAG with a written rationale.' },
    { title: 'Readiness gate', detail: 'One sonnet agent over the trail. Per draft: ready, pulled with a reason, or rework.' },
    { title: 'Ratify', detail: 'Terminal gate. Returns ready drafts in awaitingRatification; ratifies nothing.' },
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

// The Workflow tool's `args` declares no type, so a JSON object can arrive as its serialized
// text. Bound under its own name: a module-scope redeclaration of `args` is a SyntaxError on any
// host that binds it lexically.
const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  throw new Error(
    'goal-blitz received no args object (got ' + String(parsedArgs) + '). See the args contract ' +
    'at the top of this file; the caller binds args with emit-goal-fire.py.'
  )
}

const INTERACTION_MODES = ['hands-on', 'pm', 'ceo']

// Every valid mode maps to `vp-product`; an unknown mode throws (a silent default misroutes the goal).
function ratifierFor(interactionMode) {
  if (!INTERACTION_MODES.includes(interactionMode)) {
    throw new Error(
      'goal-blitz: interactionMode ' + JSON.stringify(interactionMode) + ' is not one of ' +
      INTERACTION_MODES.join(' | ')
    )
  }
  return 'vp-product'
}

const APPROVER = ratifierFor(parsedArgs.interactionMode)

const REPO_ROOT =
  typeof parsedArgs.repoRoot === 'string' && parsedArgs.repoRoot.trim() ? parsedArgs.repoRoot.trim() : null
const TRAIL_DIR =
  typeof parsedArgs.trailDir === 'string' && parsedArgs.trailDir.trim() ? parsedArgs.trailDir.trim() : null
const PROVISION_SIDECAR_CLI =
  typeof parsedArgs.provisionSidecarCli === 'string' && parsedArgs.provisionSidecarCli.trim()
    ? parsedArgs.provisionSidecarCli.trim()
    : null
const seeds = Array.isArray(parsedArgs.seeds) ? parsedArgs.seeds.filter((s) => s && s.id) : []

// Defaults true (emit-goal-fire.py); an unresolvable agentType silently yields a generic agent.
const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable !== false

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

const DRAFT_SCHEMA = {
  type: 'object',
  required: ['seedId', 'draftPath', 'status', 'tldr'],
  properties: {
    seedId: { type: 'string' },
    draftPath: { type: 'string' },
    status: { type: 'string', enum: ['drafted', 'blocked'] },
    blockedReason: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const CRITIQUE_SCHEMA = {
  type: 'object',
  required: ['seedId', 'setVerdict', 'critiquePath', 'sidecarPath', 'tldr'],
  properties: {
    seedId: { type: 'string' },
    setVerdict: { type: 'string', enum: ['GO', 'REVISE', 'REFRAME'] },
    rejectCount: { type: 'integer' },
    flagCount: { type: 'integer' },
    critiquePath: { type: 'string' },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const INTEGRATE_SCHEMA = {
  type: 'object',
  required: ['seedId', 'draftPath', 'unresolvedRejects', 'sidecarPath', 'tldr'],
  properties: {
    seedId: { type: 'string' },
    draftPath: { type: 'string' },
    unresolvedRejects: { type: 'integer' },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const READINESS_SCHEMA = {
  type: 'object',
  required: ['verdicts', 'tldr'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['seedId', 'verdict', 'reason'],
        properties: {
          seedId: { type: 'string' },
          verdict: { type: 'string', enum: ['ready', 'pulled', 'rework'] },
          reason: { type: 'string' },
        },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// Failures ride the result as `incidents`; rejections are re-thrown.
const agentIncidents = []

// No tldr: code-built WARN tldr pointing at the sidecar; never flips completion. No sidecar path: null plus an incident.
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
        const path = typeof result.sidecarPath === 'string' ? result.sidecarPath
          : typeof result.draftPath === 'string' ? result.draftPath : null
        const fallbackTldr = tldrFallback(label, path)
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr` and named no sidecar to point a code tldr at',
          })
        }
        return { ...result, tldr: fallbackTldr, assembled_by: 'code-fallback' }
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

// Trail paths are ASSIGNED, never chosen: agents picking the same filename destroy each other's write.
const draftPathFor = (seedId) => `${TRAIL_DIR}/${slug(seedId)}.goal-draft.yaml`
const critiquePathFor = (seedId) => `${TRAIL_DIR}/${slug(seedId)}.critique.md`
const integratePathFor = (seedId) => `${TRAIL_DIR}/${slug(seedId)}.integrate.md`
const readinessPathFor = () => `${TRAIL_DIR}/readiness.md`

const REPO_ROOT_RULE = REPO_ROOT ? `
Every repo-relative path in this brief is relative to THIS repo root, and nothing else:

    ${REPO_ROOT}

Resolve them there, and change into it before you run anything. Do NOT resolve against your own
working directory: you inherited it from the process that dispatched you, it is not necessarily
this repo. If a path you were given does not exist under that root, say so; never search for a
plausible substitute elsewhere on the box.` : ''

const NO_GOAL_WRITE_RULE = `
A draft is not a goal. You never scaffold a goal artifact, never run any goal-emitting CLI, and
never write anywhere outside the trail directory named in this brief. Ratification happens after
this run; the lander writes the goal store, not you.`

const TRAIL_RULE = (path) => `
Write your record to EXACTLY this path and return it verbatim:

    ${path}

Do not choose your own filename. The readiness gate reads the trail from disk, and a finding that
exists only in your returned summary is one it never sees.`

const MID_RUN_DIRECTION_RULE = `
RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

const PROVISION_CLI_RULE = `Get your findings sidecar path by running this EXACT resolved invocation, and do not
construct one by hand:

    ${PROVISION_SIDECAR_CLI} --type review-findings --agent-type apm

It prints the repo-relative sidecar path on stdout. Use what it prints and return it verbatim as
\`sidecarPath\`. On failure, report the failure verbatim and stop; never invent a path.`

const ROLE_CONTRACTS = {
  'yk-author': `You are the VP-Product Reviewer (VP of Product, they/them), setting the OKR inside one goal-blitz run. You
author the Objective and Key Results from one seed's context; the OKR you set is what is scaffolded.
If the seed already states an objective you may refine it, and your version is what lands. In this
pass you are the author, not the critic and not the ratifier. A real Objective is qualitative and direction-setting; a Key Result is a measurable
outcome an agent or the PM can see move this week.`,

  'blitz-em': `You are the blitz-em: the engineering-manager judgment inside one goal-blitz run.
You read the durable trail and gate readiness; you never author a draft, never ratify, and never
resolve a decision that belongs to the VP-Product Reviewer. Your characteristic move is the stricter reading: a
draft with an unresolved REJECT, or a REFRAME set verdict, is rework, not ready.`,
}

// Critic brief: goal-setting Step 2 text, adapted: the critic is the APM, reading the VP-Product Reviewer's draft.
const CRITIC_BRIEF = `You are a general-purpose agent taking the APM (Assistant Product Manager) lens, critiquing an OKR set the VP-Product Reviewer (VP of Product) authored.
You are reviewing the draft OKR set for strategic rigor.
Your job is to act as a full OKR critic, not a rubber-stamp.

Assess: (1) Is the Objective a real Objective — qualitative, direction-setting, not a metric or
tactic in disguise? (2) Are the KRs real Key Results — measurable outcomes, not activity/output
proxies? (3) Is the SET reasonable — ≤5 KRs; more means the Objective is unfocused? (4)
Weekly-perceptibility per KR — can an agent or PM observe it move this week? If not, flag as a
later-impact aspiration with a weekly-perceptible rewrite, or note the PM should defer it.
(5) Exemptions against seeds, in this same pass: every KR clause that exempts, carves out or
excludes something is cross-checked against the draft's goal_seeds and roadmap_seeds. Flag a seed
that reintroduces what a KR or the Objective bans, and an exemption no seed honours. List the
findings per KR, so the set ratifies in one round.

Return: verdict per element (PASS/FLAG/REJECT), specific rewrite suggestions for
flagged/rejected elements, a SET-level verdict (GO/REVISE/REFRAME). Give the author the
material to revise it — do not rewrite the whole OKR yourself.`

function emptyResult(extra) {
  return {
    ready: [],
    pulled: [],
    rework: [],
    awaitingRatification: [],
    ratified: [],
    approver: APPROVER,
    incidents: [],
    trailDir: TRAIL_DIR,
    ...extra,
  }
}

if (!REPO_ROOT) {
  return emptyResult({
    refused: [{ reason: 'no repoRoot supplied: every brief would resolve its repo-relative paths against the dispatching shell, which is not necessarily this repo' }],
  })
}
if (!TRAIL_DIR) {
  return emptyResult({
    refused: [{ reason: 'no trailDir supplied: drafts, critiques and the readiness record have nowhere durable to land' }],
  })
}
if (!PROVISION_SIDECAR_CLI) {
  return emptyResult({
    refused: [{ reason: 'no provisionSidecarCli supplied: refusing rather than letting the critic invent a sidecar root its record is then lost under' }],
  })
}
if (seeds.length === 0) {
  return emptyResult({ empty: true })
}

// Draft, Critique, Integrate: one chain per seed, in parallel; a failed chain is rework for that seed alone.

async function runSeed(seed) {
  const seedId = seed.id
  const draftPath = draftPathFor(seedId)

  // the VP-Product Reviewer is pinned model 'opus', effort 'high', never inherited or low. Rationale: docs/wiki/planning/goal-blitz.md.
  const drafted = await trackAgent(`vp-product:draft:${seedId}`, agent(
    `${ROLE_CONTRACTS['yk-author']}

Set one OKR from this seed's context.

Seed id: ${seedId}
Seed kind: ${seed.kind}
Seed record: ${seed.path}
Intent: ${seed.intent}

Read the seed record in full; the Intent line may state an objective, which you may refine. Write the draft as a YAML file with exactly these keys:

    objective: <qualitative, ambitious statement>
    key_results: [<at most 5 measurable results, each perceptible within a week>]
    period: <one of day | week | repo | quarter | year>
    period_value: <e.g. Q4-2026>
    roadmap_seeds: [<titles of roadmap-seed stubs this goal spawns>]
    goal_seeds: [<titles of deferred vision-slice goal-seed stubs>]
    parent_goal_id: <the goal or seed id this OKR refines, when it is a sibling or child of one; else omit>
    critique_ref: ${critiquePathFor(seedId)}
    ratification: null

Leave \`ratification\` null; only the recorded ratification fills it, after this run.
${NO_GOAL_WRITE_RULE}
${MID_RUN_DIRECTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(draftPath)}`,
    { model: 'opus', effort: 'high', /* opus-justified: the VP-Product Reviewer authors and integrates the OKR; opus-ruling: G-EM-2026-10-27-R3 */ ...withRole('coordinator:vp-product'),
      label: `vp-product:draft:${seedId}`,
      phase: 'Draft',
      schema: DRAFT_SCHEMA,
    },
  ))
  if (!drafted || drafted.status !== 'drafted') {
    return { seedId, verdict: 'rework', reason: (drafted && drafted.blockedReason) || 'the VP-Product Reviewer returned no draft' }
  }

  // Fires unconditionally: the EM is not asked whether a draft deserves a critic.
  const critique = await trackAgent(`apm:critique:${seedId}`, agent(
    `${CRITIC_BRIEF}

The draft under review is at: ${drafted.draftPath}

Write your full critique to the trail path below and ALSO your findings sidecar as described.
Do not edit the draft.
${PROVISION_CLI_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(critiquePathFor(seedId))}`,
    { model: 'sonnet', ...withRole('general-purpose'),
      label: `apm:critique:${seedId}`,
      phase: 'Critique',
      schema: CRITIQUE_SCHEMA,
    },
  ))
  if (!critique) {
    return { seedId, verdict: 'rework', reason: 'the critic returned nothing; an uncritiqued draft is never ready' }
  }

  const integrated = await trackAgent(`vp-product:integrate:${seedId}`, agent(
    `${ROLE_CONTRACTS['yk-author']}

Integrate the critic's findings into your draft. This is goal-setting's integration step; the VP-Product Reviewer
ratifies later, at the terminal Ratify phase.

Draft: ${drafted.draftPath}
Critique: ${critique.critiquePath}

REJECT items are rewritten or dropped. FLAG items are rewritten, or accepted with a stated
rationale. Weekly-perceptibility notes are rewritten, or deferred to an entry under
\`goal_seeds\`. After fixing a flagged exemption, re-read every seed against it. Edit the draft in place and keep its key shape and \`ratification: null\`.
Record each disposition, with your rationale for every accepted FLAG, in the record below.
Return \`unresolvedRejects\`: the count of REJECT items you could not resolve.
${NO_GOAL_WRITE_RULE}
${MID_RUN_DIRECTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(integratePathFor(seedId))}`,
    { model: 'opus', effort: 'high', /* opus-justified: the VP-Product Reviewer authors and integrates the OKR; opus-ruling: G-EM-2026-10-27-R3 */ ...withRole('coordinator:vp-product'),
      label: `vp-product:integrate:${seedId}`,
      phase: 'Integrate',
      schema: INTEGRATE_SCHEMA,
    },
  ))
  if (!integrated) {
    return { seedId, verdict: 'rework', reason: 'the VP-Product Reviewer returned nothing at integration' }
  }

  return { seedId, draftPath: drafted.draftPath, critique, integrated }
}

const chains = await parallel(
  seeds.map((seed) => () => runSeed(seed).catch((err) => ({
    seedId: seed.id,
    verdict: 'rework',
    reason: 'the chain errored: ' + String((err && (err.message || err.error)) || err).slice(0, 300),
  }))),
)

const settled = chains.filter(Boolean)
const failedChains = settled.filter((c) => c.verdict === 'rework')
const gated = settled.filter((c) => c.verdict !== 'rework')

// Readiness gate: one Sonnet group-em-assistant over the whole trail.

let verdicts = []
if (gated.length) {
  const gateResult = await trackAgent('blitz-em:readiness', agent(
    `${ROLE_CONTRACTS['blitz-em']}

Gate readiness over this goal-blitz trail. For each draft below, read the draft, its critique and
its integration record from disk, then return exactly one verdict:

  ready   the draft integrates the critique and is fit to put in front of the VP-Product Reviewer for ratification
  pulled  not ready for a reason you state; it waits for a later run
  rework  the set verdict was REFRAME, or a REJECT is unresolved

Drafts:
${gated.map((c) => `  - ${c.seedId}
      draft:     ${c.draftPath}
      critique:  ${c.critique.critiquePath} (set verdict ${c.critique.setVerdict})
      integrate: ${integratePathFor(c.seedId)} (unresolved REJECTs ${c.integrated.unresolvedRejects})`).join('\n')}

You gate readiness only. You never ratify: ratification is the VP-Product Reviewer's, after this run. You never edit
a draft. A draft is never ready while a REJECT is unresolved or its set verdict is REFRAME; that is
also enforced after you answer, and your disagreement is recorded rather than acted on.
${REPO_ROOT_RULE}
${TRAIL_RULE(readinessPathFor())}`,
    // Sonnet wearing the blitz-em ROLE_CONTRACT (blitz-em is Opus-only); REJECT/REFRAME readies are overridden after.
    { model: 'sonnet', ...withRole('coordinator:group-em-assistant'),
      label: 'readiness:goal-blitz',
      phase: 'Readiness gate',
      schema: READINESS_SCHEMA,
    },
  ))
  verdicts = (gateResult && gateResult.verdicts) || []
}

// Reconciliation only makes a verdict stricter: never promote a REFRAME or unresolved REJECT to ready.
const verdictById = new Map(verdicts.map((v) => [v.seedId, v]))
const ready = []
const pulled = []
const rework = failedChains.map((c) => ({ seed_id: c.seedId, reason: c.reason }))

for (const c of gated) {
  const v = verdictById.get(c.seedId)
  if (!v) {
    pulled.push({ seed_id: c.seedId, reason: 'the readiness gate returned no verdict for this draft' })
  } else if (c.critique.setVerdict === 'REFRAME' || c.integrated.unresolvedRejects > 0) {
    rework.push({
      seed_id: c.seedId,
      reason: c.critique.setVerdict === 'REFRAME'
        ? 'the critic set verdict is REFRAME'
        : `${c.integrated.unresolvedRejects} REJECT item(s) unresolved after integration`,
    })
  } else if (v.verdict === 'ready') {
    ready.push(c.seedId)
  } else if (v.verdict === 'rework') {
    rework.push({ seed_id: c.seedId, reason: v.reason })
  } else {
    pulled.push({ seed_id: c.seedId, reason: v.reason })
  }
}

// Ratify: terminal gate; nothing is ratified here, ready drafts go to the driver.

return {
  ready,
  pulled,
  rework,
  awaitingRatification: [...ready],
  ratified: [],
  approver: APPROVER,
  incidents: agentIncidents,
  trailDir: TRAIL_DIR,
}
