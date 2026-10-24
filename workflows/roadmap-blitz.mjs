/*
 * roadmap-blitz — background-Workflow encoding of one batched roadmap run.
 *
 * Spec backlink: coordinator/skills/roadmap-blitz/SKILL.md. Contract fixture:
 * coordinator/skills/roadmap-blitz/roadmap-blitz-contract.json. Doctrine:
 * coordinator/docs/wiki/planning/roadmap-blitz.md. Interactive twin: coordinator:roadmap-planning.
 *
 * WHAT ONE RUN COVERS: one XL sizing with `xl_exit: roadmap`, from its corpus to a frozen gate
 * report. Phases: Synthesize (roadmap-planning Phase 1), Substantiate (research + OVERVIEW +
 * peer-team asks), Review (unconditional), Approve (the single gate), Stage (the planner's
 * first step runs roadmap.blitz_stage, its second fills the staged stubs).
 *
 * Negative-spec — what this is NOT:
 *   - NOT a stager. roadmap.blitz_stage scaffolds, numbers, folds, audits, records the approval,
 *     stamps OVERVIEW, commits and freezes the gate report in one call; nothing here re-implements it.
 *   - NOT a committer. No leg here commits or stages; the only commits are the engine's own.
 *   - NOT a writer of approval.json. The engine op is its single writer.
 *   - NOT able to ask the PM. In hands-on mode the run returns `awaitingApproval`; the skill driver
 *     asks, records <trailDir>/approval.json, and re-fires with `approval`.
 *   - NOT a retirer of source plans. `owedRetirements` is reported; the driver surfaces it.
 *   - NOT a place where the EM gates mid-run (tripwire: A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ).
 *   - NOT plan-blitz. It carries no plan gate, XS dispatch or replan machinery.
 *   - NOT a stub sizer. A stub is never handed the roadmap sizing, and none is pre-marked ready.
 *
 * args contract (bound by workflow.bind_args or by warp; this script declares no top-level `args`):
 *   {
 *     repoRoot: string,             // ABSOLUTE. REQUIRED.
 *     sizing: string,               // repo-relative sizing path. REQUIRED.
 *     interactionMode: string,      // hands-on | pm | ceo. REQUIRED; approverFor maps it.
 *     trailDir: string,             // ABSOLUTE or repo-relative, under scratch/. REQUIRED. Review sidecars land here.
 *     approver: string,             // optional; when supplied it must equal approverFor(interactionMode).
 *     corpus: [string],             // repo-relative inputs. Default: the sizing, its baton, its premise evidence.
 *     runId: string,                // default derived from the sizing stem; ^[a-z0-9][a-z0-9-]*$
 *     approval: object,             // The hands-on resume: the recorded PM approval, bound inline by the emitter.
 *     pluginAgentsAvailable: bool,  // defaults true; only an explicit false disables coordinator:* types.
 *     chatty: bool,                 // with chattyReview: reviewers run as one concurrent wave.
 *     chattyReview: object,         // the engine's review-wave template; {BATON} is filled with runId.
 *     provisionSidecarCli: string,  // optional resolved `coordinator-doc-new` invocation.
 *     pluginRoot: string            // ABSOLUTE plugin root; emit-roadmap-fire.py binds it. The briefs
 *                                   // cite doctrine files under it, because a consumer repo has no
 *                                   // `coordinator/` directory. Absent: the briefs say to resolve it.
 *   }
 *
 * Returns: { gate_report_path, roadmapId, roadmapDir, approver, approval, awaitingApproval, stage,
 *            owedRetirements, incidents, trailDir } — gate_report_path is null on every path that
 *            did not stage.
 */

// No apostrophe in a `detail` string: the engine pairs quotes naively and a stray one hides every
// phase declared after it.
export const meta = {
  name: 'roadmap-blitz',
  description: 'One batched roadmap run: an Opus roadmap-planner synthesizes the corpus, haiku scouts research the clusters in batches, one reviewer per lens applies findings unconditionally, one approval gate clears by interaction mode, and the planner runs the one engine call that stages the stubs, then fills them.',
  phases: [
    { title: 'Synthesize', detail: 'One roadmap-planner over the corpus writes inventory, clusters, reconciliation and any resolutions into the roadmap directory.' },
    { title: 'Substantiate', detail: 'One haiku scout per batch of up to 4 KEEP or MERGE-target clusters, at most 8 scouts at once, then the planner authors OVERVIEW and peer-team asks.' },
    { title: 'Review', detail: 'Fires unconditionally. A staff or director reviewer and a domain reviewer when a flavor maps to one, in order, or as one concurrent chatty wave when args.chatty and args.chattyReview are set. Each applies its own findings.' },
    { title: 'Approve', detail: 'The single gate. The APM clears it for pm and ceo modes; hands-on returns awaitingApproval for the skill driver to ask the PM.' },
    { title: 'Stage', detail: 'The planner runs roadmap.blitz_stage, which records the approval, scaffolds, numbers, audits and freezes the gate report, then writes each staged stub summary and body from its OVERVIEW section, plus STUB-INDEX.' },
  ],
}

const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  throw new Error(
    'roadmap-blitz received no args object (got ' + String(parsedArgs) + '). See the args contract ' +
    'at the top of this file.'
  )
}

const INTERACTION_MODES = ['hands-on', 'pm', 'ceo']

// Who clears the approval gate. Agrees with the engine's approver_for on every valid mode; an
// unknown mode throws where the engine would fall through to apm, because a silent default routes
// a roadmap to the wrong approver.
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

// Balanced groups of at most `max`: ceil(n/max) groups, sizes differing by at most one.
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

// An agent outage manufactures verdicts rather than merely losing a run, so every dispatch is
// counted and rides the result as `incidents`. Rejections are re-thrown for the caller.
const agentIncidents = []

// A role that returned a payload without its `tldr` still wrote its own sidecar, which is the
// durable record; a restatement adds nothing a reader of that sidecar lacks, so the fallback is a
// WARN tldr built in code from the result in memory, anchored at the sidecar. It never flips
// `completed`; a result with no sidecar path yields null and counts as a missing-tldr incident.
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

// Paths in the roadmap directory and the trail are ASSIGNED, never chosen: two agents picking the
// obvious filename collide and the later write silently destroys the earlier.
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

// A doctrine file the briefs cite lives in the plugin tree, never under the consumer repo's root.
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

const COMMON = `${REPO_ROOT_RULE}\n${CLI_RESOLUTION_RULE}${PLUGIN_ROOT_RULE}${FRICTION_RULE}\n${MID_RUN_DIRECTION_RULE}`

// Chatty review wave (args.chatty and args.chattyReview): the roadmap reviewers run concurrently
// on one roster. Self-contained twin of plan-blitz's wave; workflow scripts import nothing.
const fillBaton = (value, batonId, slot) => {
  if (typeof value === 'string') return value.split(slot).join(batonId)
  if (Array.isArray(value)) return value.map((v) => fillBaton(v, batonId, slot))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fillBaton(v, batonId, slot)]))
  }
  return value
}
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

// The wave twin of the sequential review prompt. It must not repeat the sequential prompt's
// phrasing: the contract tests count those phrases in this file.
const chattyReviewBrief = (role) => `You are reviewing a roadmap authored inside one roadmap-blitz run. Read ${ROADMAP_DIR}/OVERVIEW.md,
peer-team-asks.md, clusters.md and reconciliation.md, plus the research files they cite. Peer reviewers
review these same files concurrently; the CHATTY RUN and REVIEW WAVE sections below govern every edit.

Judge the roadmap on its own merits: coverage of the sizing ${SIZING}, cluster boundaries, ordering,
and whether any cluster is a unit of dispatch masquerading as a unit of coverage. Then APPLY your
own findings to the roadmap files yourself, because nothing downstream reads a finding that is only
in your summary. Findings you cannot resolve go in OVERVIEW under the cluster's \`### Contested\`
heading. blitz_stage parses every id on a \`**blocked_by:**\` line in clusters.md as an edge, so that
line holds cluster ids or none, and a dependency note goes on a separate line. You never approve,
never stage, and never write outside ${ROADMAP_DIR}/ and your sidecar.

${SIDECAR_RULE(role)}
${COMMON}
${SIDECAR_HEREDOC_RULE(`review:${role}`)}
Also write a copy of your review record to EXACTLY this path, where the Approve gate reads it, and
return the provisioned findings sidecar path as \`sidecarPath\`:

    ${reviewPathFor(role)}`

async function chattyStage(label, prompt, schema) {
  try {
    return await agent(prompt, { model: 'opus', label: `chatty-stage:${label}`, phase: 'Review', schema })
  } catch (err) {
    agentIncidents.push({ role: label, kind: 'errored', detail: String((err && (err.message || err.error)) || err).slice(0, 500) })
    return null
  }
}

// Returns the settled review per reviewer (null where a reviewer returned nothing), or null when
// the wave does not apply (not chatty, more reviewers than slots, overseer failed): the caller then
// runs the sequential loop.
async function chattyReviewWave(reviewers) {
  const raw = parsedArgs.chatty === true ? parsedArgs.chattyReview : null
  if (!raw || typeof raw !== 'object' || !raw.roster || !Array.isArray(raw.roster.members)) return null
  const slots = raw.roster.members.map((m) => m.role).filter((r) => /^review-\d+$/.test(r))
  if (!reviewers.length || reviewers.length > slots.length) return null

  const wave = fillBaton(raw, RUN_ID, raw.batonSlot || '{BATON}')
  const peers = reviewers.map((r, i) => [slots[i], r])
  const brief = (i) => {
    const role = reviewers[i].split(':')[1]
    return chattyReviewBrief(role) + fillPeers(wave.memberBriefs[slots[i]], wave.peersSlot || '{PEERS}', peers)
  }
  const dispatch = (i, text) => trackAgent(`review:${reviewers[i].split(':')[1]}`, agent(text, {
    model: 'opus', ...withRole(reviewers[i]), label: `chatty-review:${reviewers[i].split(':')[1]}`, phase: 'Review', schema: REVIEW_SCHEMA,
  })).catch((err) => {
    agentIncidents.push({ role: `chatty-review:${reviewers[i].split(':')[1]}`, kind: 'errored', detail: String((err && (err.message || err.error)) || err).slice(0, 500) })
    return null
  })

  if (!(await chattyStage('chatty-overseer', wave.overseerPrompt, WAVE_STAGE_SCHEMA))) {
    agentIncidents.push({ role: 'chatty-overseer', kind: 'wave-unavailable', detail: 'the overseer returned nothing; the reviewers run sequentially' })
    return null
  }
  const settled = await parallel(reviewers.map((_, i) => () => dispatch(i, brief(i))))

  const survey = await chattyStage('chatty-survey', wave.surveyPrompt, SURVEY_SCHEMA)
  const owed = ((survey && survey.continuations) || [])
    .map((c) => slots.indexOf(c.role))
    .filter((i) => i >= 0 && i < reviewers.length)
  await parallel(owed.map((i) => async () => {
    const nonce = `${RUN_ID}-${slots[i]}-cont`
    const next = await dispatch(i, brief(i) + String(wave.continuationBriefs[slots[i]]).split(wave.nonceSlot || '{NONCE}').join(nonce))
    if (next) settled[i] = next
  }))

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

// ---------------------------------------------------------------------------
// Resume: a hands-on re-fire carries a recorded PM approval and skips phases 1-3, whose artifacts
// are already on disk.
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Synthesize + Substantiate + Review: skipped on a resume fire.
// ---------------------------------------------------------------------------

if (!approval) {
  // Every roadmap-planner call below is pinned model 'opus' at effort 'high' or 'medium', never
  // inherited and never low: an unpinned planner takes the firing session's setting, and the PM
  // ruled the roadmap-planner runs at medium or high.
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
    { model: 'opus', effort: 'high', ...withRole('coordinator:roadmap-planner'),
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
    { model: 'opus', effort: 'high', ...withRole('coordinator:roadmap-planner'),
      label: 'roadmap-planner:overview', phase: 'Substantiate', schema: OVERVIEW_SCHEMA },
  ))
  if (!overview) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'the roadmap-planner returned no OVERVIEW' }] })
  }

  // Review fires unconditionally: the EM is never asked whether a roadmap deserves a reviewer.
  const needsDirector = overview.peerTeamAsks > 0 || overview.crossesRepo || synth.crossesRepo
  const DOMAIN_REVIEWER = { data: 'coordinator:staff-data-sci', ux: 'coordinator:staff-ux', 'front-end': 'coordinator:senior-front-end' }
  const flavor = (overview.flavor || synth.flavor || '').toLowerCase()
  const reviewers = [needsDirector ? 'coordinator:eng-director' : 'coordinator:staff-eng']
  if (DOMAIN_REVIEWER[flavor]) reviewers.push(DOMAIN_REVIEWER[flavor])

  const missingReviews = []
  const blockedReviews = []
  // A settled wave drains `reviewers`, so the sequential loop below runs only when it did not.
  const waveReviews = await chattyReviewWave(reviewers)
  if (waveReviews) {
    reviewers.splice(0).forEach((reviewer, i) => {
      const role = reviewer.split(':')[1]
      if (!waveReviews[i]) missingReviews.push(role)
      else if (waveReviews[i].verdict === 'BLOCKED') blockedReviews.push(role)
    })
  }
  for (const reviewer of reviewers) {
    const role = reviewer.split(':')[1]
    const review = await trackAgent(`review:${role}`, agent(
      `You are reviewing a roadmap authored inside one roadmap-blitz run. Read ${ROADMAP_DIR}/OVERVIEW.md,
peer-team-asks.md, clusters.md and reconciliation.md, plus the research files they cite.

Judge the roadmap on its own merits: coverage of the sizing ${SIZING}, cluster boundaries, ordering,
and whether any cluster is a unit of dispatch masquerading as a unit of coverage. Then APPLY your
own findings to the roadmap files yourself, because nothing downstream reads a finding that is only
in your summary. Findings you cannot resolve go in OVERVIEW under the cluster's \`### Contested\`
heading. A \`**blocked_by:**\` line in clusters.md carries only cluster ids, or none: never a
parenthetical or prose, since blitz_stage parses every id on it as an edge. Put a review note about
a dependency on its own separate line. You never approve, never stage, and never write outside ${ROADMAP_DIR}/ and your sidecar.

${SIDECAR_RULE(role)}
${COMMON}
${SIDECAR_HEREDOC_RULE(`review:${role}`)}
Also write a copy of your review record to EXACTLY this path, where the Approve gate reads it, and
return the provisioned findings sidecar path as \`sidecarPath\`:

    ${reviewPathFor(role)}`,
      { model: 'opus', ...withRole(reviewer), label: `review:${role}`, phase: 'Review', schema: REVIEW_SCHEMA },
    ))
    if (!review) missingReviews.push(role)
    else if (review.verdict === 'BLOCKED') blockedReviews.push(role)
  }
  // A BLOCKED review is a halt: the Approve gate must never see a roadmap a reviewer refused.
  if (blockedReviews.length) {
    agentIncidents.push({ role: `review:${blockedReviews.join(',')}`, kind: 'review-blocked', detail: 'reviewer returned BLOCKED; the run halts before the approval gate' })
    return emptyResult({ owedRetirements, refused: [{ reason: 'review returned BLOCKED for ' + blockedReviews.join(', ') + '; nothing is approved or staged' }] })
  }
  if (missingReviews.length) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'review returned nothing for ' + missingReviews.join(', ') + '; the gate never clears an unreviewed roadmap' }] })
  }
}

// ---------------------------------------------------------------------------
// Approve: the single gate.
// ---------------------------------------------------------------------------

if (!approval) {
  if (APPROVER === 'pm') {
    // A Workflow cannot ask the PM. The skill driver asks once, records approval.json, re-fires.
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
${MID_RUN_DIRECTION_RULE}`,
    { model: 'opus', ...withRole('coordinator:apm'), label: 'apm:approve', phase: 'Approve', schema: APPROVAL_SCHEMA },
  ))
  if (!decision) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'the APM returned no verdict; nothing is staged' }] })
  }
  approval = { verdict: decision.verdict, approver: 'apm', ruling: decision.ruling, ruling_ref: decision.ruling_ref }
}

if (approval.verdict !== 'approved') {
  return emptyResult({ approval, owedRetirements, declined: true })
}

// ---------------------------------------------------------------------------
// Stage: the planner's step 1 is the one engine call; step 2 fills the stubs it names. The
// engine writes <trail_dir>/approval.json and stamps OVERVIEW itself; no agent here does.
// ---------------------------------------------------------------------------

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

A refusal from the op (for example a cluster with no \`loe:\`) is an incident, not something to fix:
set \`refused: true\`, put its message verbatim in \`refusal\`, and stop. Never edit clusters.md or
any roadmap file to get past a refusal, and never scaffold, number or audit a stub by hand. A reply
whose \`approval_record\` is null for this approved call is also a refusal: set \`refused: true\`,
say so in \`refusal\`, and fill no stub. Never write approval.json yourself; the op is its only writer.
${CLI_RESOLUTION_RULE}

STEP 2. Run roadmap-planning Step 2.2 and Step 2.3 over the stubs the reply from step 1 names (its
\`stubs\`, and its \`gate_report_path\` is the frozen gate report).

For each staged stub, read its OVERVIEW section (${ROADMAP_DIR}/OVERVIEW.md) and the research files
it cites, then write into the stub: a real \`summary:\` line, and the Step 2.2 body sections in order
(why-its-own-session paragraph; ## What this covers; ## Reference materials (read first); ##
Specification; ## Acceptance criteria; ## Recommended next steps for the picking-up EM; ## Anti-scope;
## Soft seams; ## Session Ledger; the trailing roadmap-baton comment). A stub's \`summary:\` and its
\`## What this covers\` are quoted as the PM brief of the plan built from it: a one-line stub is a
one-line brief. Then write ${ROADMAP_DIR}/STUB-INDEX.md as a query callout, not a hand table.

You edit stub bodies and \`summary:\` only. Never change a stub's frontmatter numbering, \`covers:\`,
\`blocked_by\`, loe or size fields, never hand the roadmap sizing to a stub, never mark one
ready, and never touch the frozen gate report.
${COMMON}
${SIDECAR_HEREDOC_RULE('roadmap-planner:fill-stubs')}
${RESUMING ? `Also return \`owedRetirements\`: the repo-relative docs/plans/ paths that ${ROADMAP_DIR}/inventory.md marks as live source plans (empty when there are none or the file is absent).\n` : ''}Return \`stageReply\` (step 1), \`paths\` (every repo-relative path you wrote in step 2) and \`filled\`
(the count of stubs filled). You never commit or stage.`,
  { model: 'opus', effort: 'medium', ...withRole('coordinator:roadmap-planner'),
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
