/*
 * goal-blitz — background-Workflow encoding of one batched goal-setting run.
 *
 * Spec backlink: coordinator/skills/goal-blitz/SKILL.md. Contract fixture:
 * coordinator/skills/goal-blitz/goal-blitz-contract.json. The skill stays the source of truth; this
 * script is its dispatch vehicle.
 *
 * WHAT ONE RUN COVERS: every seed in `args.seeds`, in one fire. Per seed: the VP-Product Reviewer (the
 * `coordinator:vp-product` agent) authors the Objective and Key Results from the seed's context into
 * the trail, a second the VP-Product Reviewer pass critiques the draft unconditionally, the VP-Product Reviewer integrates the critique, and
 * one blitz-em reads the trail for readiness. The run ends at a terminal Ratify phase that returns
 * ready drafts in `awaitingRatification` and ratifies nothing.
 *
 * Negative-spec — what this is NOT:
 *   - NOT a goal store writer. A draft lives in the trail; it becomes a goal only when the
 *     skill's lander runs over a recorded the VP-Product Reviewer ratification. No goal-store write happens here.
 *   - NOT the ratifier. The VP-Product Reviewer ratifies an OKR; the skill driver dispatches the VP-Product Reviewer once over the whole set
 *     and records each answer in <trailDir>/ratification.json. A seed's stated objective is input
 *     the VP-Product Reviewer may refine; the VP-Product Reviewer's version is what lands.
 *   - NOT a place where the EM gates mid-run. Critique and integration fire unconditionally
 *     (tripwire: A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ).
 *   - NOT plan-blitz. It carries no plan gate, XS dispatch, premise check or replan machinery.
 *
 * args contract (bound by workflow.bind_args; this script declares no top-level `args`):
 *   {
 *     repoRoot: string,             // ABSOLUTE. REQUIRED; the run refuses without it. Every brief
 *                                   //  anchors repo-relative paths here, because an agent
 *                                   //  otherwise resolves them against the driver shell cwd.
 *     trailDir: string,             // ABSOLUTE. REQUIRED. Drafts, critiques and the readiness
 *                                   //  record are written here; the caller scaffolds it.
 *     provisionSidecarCli: string,  // ABSOLUTE resolved `coordinator-doc-new` invocation. REQUIRED;
 *                                   //  the run refuses without it, so the critic never invents
 *                                   //  a sidecar root.
 *     interactionMode: string,      // hands-on | pm | ceo. Bound as-is; ratifierFor derives the
 *                                   //  `approver` the result reports (always `vp-product`). Any
 *                                   //  other value throws.
 *     pluginAgentsAvailable: bool,  // whether coordinator:* agent types resolve. Defaults true;
 *                                   //  only an explicit false disables them.
 *     seeds: [ { id, path, kind: 'goal-seed' | 'sizing', intent } ]
 *   }
 *
 * Invocation (scriptPath resolves through the plugin root, never a repo-relative prefix):
 *   Workflow({
 *     scriptPath: `${CLAUDE_PLUGIN_ROOT}/workflows/goal-blitz.mjs`,
 *     args: { repoRoot: "/abs/repo", trailDir: "/abs/repo/state/scratch/goal-blitz/<stamp>",
 *             provisionSidecarCli: "/abs/settings-home/bin/coordinator-doc-new",
 *             interactionMode: "hands-on", pluginAgentsAvailable: true,
 *             seeds: [ { id: "...", path: "state/handoffs/...md", kind: "goal-seed", intent: "..." } ] }
 *   })
 *
 * Returns: { ready, pulled, rework, awaitingRatification, ratified, approver, incidents, trailDir }
 */

// No apostrophe in a `detail` string: the engine pairs quotes naively and a stray one hides every
// phase declared after it.
export const meta = {
  name: 'goal-blitz',
  description: 'One batched goal-setting run: the VP-Product Reviewer authors each OKR, a second the VP-Product Reviewer pass critiques every draft unconditionally, the VP-Product Reviewer integrates, a blitz-em gates readiness, and one terminal Ratify phase hands ready drafts to the VP-Product Reviewer for ratification.',
  phases: [
    { title: 'Draft', detail: 'One the VP-Product Reviewer author per seed. Sets the Objective and Key Results from the seed context and writes the draft into the trail, never into the goal store.' },
    { title: 'Critique', detail: 'One further the VP-Product Reviewer pass per draft, fired unconditionally. Per-element PASS, FLAG or REJECT and a set verdict of GO, REVISE or REFRAME.' },
    { title: 'Integrate', detail: 'the VP-Product Reviewer applies the REJECT and FLAG rewrites to the draft, or accepts a FLAG with a written rationale.' },
    { title: 'Readiness gate', detail: 'One Opus blitz-em over the trail. Per draft: ready, pulled with a reason, or rework.' },
    { title: 'Ratify', detail: 'Terminal gate. Returns ready drafts in awaitingRatification and ratifies nothing; the VP-Product Reviewer ratifies once over the whole set.' },
  ],
}

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

// The single place the ratifier is derived. The VP-Product Reviewer (the VP Product agent) sets and ratifies every OKR,
// so every valid mode maps to `vp-product`. An unknown mode throws rather than defaulting: a
// silent default would route a goal to the wrong confirmer.
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

// `pluginAgentsAvailable` defaults true, matching emit-goal-fire.py; only an explicit false turns it
// off. An unresolvable agentType yields a generic agent wearing the role label, and nothing reports
// the substitution.
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

// An agent outage manufactures verdicts rather than merely losing a run, so every dispatch is
// counted: a rejected call, a null resolution and an unrecoverable missing tldr all land here and
// ride the result as `incidents`. Rejections are re-thrown so each caller keeps its own handling.
const agentIncidents = []

// Deliberately not wrapped in trackAgent: trackAgent calls this, and wrapping it would recurse. A
// failure degrades to a null tldr, a lost summary line and never a lost dispatch.
async function tldrFallback(label, sidecarPath) {
  if (!sidecarPath) return null
  return Promise.resolve(agent(`Read the file this agent already wrote, at exactly this path,
and change nothing about it: ${sidecarPath}

Return ONLY a \`return-tldr\` summary of what it already says: \`verdict\` (its own verdict word,
mapped onto OK/WARN/BLOCKED/PIVOT/FAILED), up to 5 \`decisions\` ({item, anchor}) naming its most
load-bearing findings or calls, \`counts\` of whatever it enumerates, and \`sidecar\` set to the
path above. Do not re-run the check, do not open anything else, and do not edit the file.
${REPO_ROOT_RULE}`,
    { label: `tldr-fallback:${label}`, model: 'haiku', effort: 'low', schema: RETURN_TLDR_SCHEMA },
  )).catch(() => null)
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
        const fallbackTldr = await tldrFallback(label, path)
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr`, and the Haiku fallback over its record also failed',
          })
        }
        return { ...result, tldr: fallbackTldr, assembled_by: 'fallback' }
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

// Paths in the trail are ASSIGNED, never chosen: two agents picking the obvious filename collide
// and the later write silently destroys the earlier.
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

const PROVISION_CLI_RULE = `Get your findings sidecar path by running this EXACT resolved invocation, and do not
construct one by hand:

    ${PROVISION_SIDECAR_CLI} --type review-findings --agent-type vp-product

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

// Critic brief: goal-setting Step 2 text, adapted: the critic is a separate the VP-Product Reviewer pass over the VP-Product Reviewer's draft.
const CRITIC_BRIEF = `You are the VP-Product Reviewer (VP of Product, they/them), in a separate critic pass over an OKR set the VP-Product Reviewer authored.
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

// ---------------------------------------------------------------------------
// Draft, Critique, Integrate: one chain per seed, seeds in parallel.
// A chain that fails or blocks is recorded as rework for that seed alone and never halts a peer.
// ---------------------------------------------------------------------------

async function runSeed(seed) {
  const seedId = seed.id
  const draftPath = draftPathFor(seedId)

  // the VP-Product Reviewer is pinned model 'opus' at effort 'high', never inherited and never low: an unpinned author
  // takes whatever the firing session was set to, and the VP-Product Reviewer owes the OKR's shape, the one artifact
  // everything downstream judges. Pin rationale: docs/wiki/planning/goal-blitz.md.
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
${REPO_ROOT_RULE}
${TRAIL_RULE(draftPath)}`,
    { model: 'opus', effort: 'high', ...withRole('coordinator:vp-product'),
      label: `vp-product:draft:${seedId}`,
      phase: 'Draft',
      schema: DRAFT_SCHEMA,
    },
  ))
  if (!drafted || drafted.status !== 'drafted') {
    return { seedId, verdict: 'rework', reason: (drafted && drafted.blockedReason) || 'the VP-Product Reviewer returned no draft' }
  }

  // Fires unconditionally: the EM is not asked whether a draft deserves a critic.
  const critique = await trackAgent(`vp-product:critique:${seedId}`, agent(
    `${CRITIC_BRIEF}

The draft under review is at: ${drafted.draftPath}

Write your full critique to the trail path below and ALSO your findings sidecar as described.
Do not edit the draft.
${PROVISION_CLI_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(critiquePathFor(seedId))}`,
    { model: 'opus', effort: 'high', ...withRole('coordinator:vp-product'),
      label: `vp-product:critique:${seedId}`,
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
${REPO_ROOT_RULE}
${TRAIL_RULE(integratePathFor(seedId))}`,
    { model: 'opus', effort: 'high', ...withRole('coordinator:vp-product'),
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

// ---------------------------------------------------------------------------
// Readiness gate: one blitz-em over the whole trail.
// ---------------------------------------------------------------------------

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
    { model: 'opus', ...withRole('coordinator:blitz-em'),
      label: 'readiness:goal-blitz',
      phase: 'Readiness gate',
      schema: READINESS_SCHEMA,
    },
  ))
  verdicts = (gateResult && gateResult.verdicts) || []
}

// Mechanical reconciliation only ever makes a verdict stricter: a gate that favours its own
// output must not be able to promote a REFRAME or an unresolved REJECT to ready.
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

// ---------------------------------------------------------------------------
// Ratify: the terminal gate and the only one. Nothing is ratified here; ready drafts are handed
// to the skill driver, which dispatches the ratifier named by `approver` once over the whole set.
// ---------------------------------------------------------------------------

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
