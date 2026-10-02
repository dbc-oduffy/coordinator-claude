/*
 * roadmap-blitz — background-Workflow encoding of one batched roadmap run.
 *
 * Spec backlink: coordinator/skills/roadmap-blitz/SKILL.md. Contract fixture:
 * coordinator/skills/roadmap-blitz/roadmap-blitz-contract.json. Doctrine:
 * coordinator/docs/wiki/planning/roadmap-blitz.md. Interactive twin: coordinator:roadmap-planning.
 *
 * WHAT ONE RUN COVERS: one XL sizing with `xl_exit: roadmap`, from its corpus to a frozen gate
 * report. Phases: Synthesize (roadmap-planning Phase 1), Substantiate (research + OVERVIEW +
 * peer-team asks), Review (unconditional), Approve (the single gate), Stage (one engine call,
 * roadmap.blitz_stage), Fill stubs (the staged stubs get their bodies).
 *
 * Negative-spec — what this is NOT:
 *   - NOT a stager. roadmap.blitz_stage scaffolds, numbers, folds, audits, commits and freezes the
 *     gate report in one call; nothing here re-implements any of it.
 *   - NOT able to ask the PM. In hands-on mode the run returns `awaitingApproval`; the skill driver
 *     asks, records <trailDir>/approval.json, and re-fires with `approvalPath`.
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
 *     trailDir: string,             // ABSOLUTE. REQUIRED. Approval record and review sidecars land here.
 *     approver: string,             // optional; when supplied it must equal approverFor(interactionMode).
 *     corpus: [string],             // repo-relative inputs. Default: the sizing, its baton, its premise evidence.
 *     runId: string,                // default derived from the sizing stem; ^[a-z0-9][a-z0-9-]*$
 *     approvalPath: string,         // ABSOLUTE. The hands-on resume: a recorded PM approval.
 *     pluginAgentsAvailable: bool,  // defaults true; only an explicit false disables coordinator:* types.
 *     provisionSidecarCli: string   // optional resolved `coordinator-doc-new` invocation.
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
  description: 'One batched roadmap run: an Opus roadmap-planner synthesizes the corpus, scouts research each cluster, reviewers apply findings unconditionally, one approval gate clears by interaction mode, one engine call stages the stubs, and the planner fills them.',
  phases: [
    { title: 'Synthesize', detail: 'One roadmap-planner over the corpus writes inventory, clusters, reconciliation and any resolutions into the roadmap directory.' },
    { title: 'Substantiate', detail: 'One scout per KEEP or MERGE-target cluster, at most 8 at once, then the planner authors OVERVIEW and peer-team asks.' },
    { title: 'Review', detail: 'Fires unconditionally. Staff or director reviewer, then a domain reviewer when a flavor maps to one. Each applies its own findings.' },
    { title: 'Approve', detail: 'The single gate. The APM clears it for pm and ceo modes; hands-on returns awaitingApproval for the skill driver to ask the PM.' },
    { title: 'Stage', detail: 'One executor commits the roadmap directory and runs roadmap.blitz_stage, which scaffolds, numbers, audits and freezes the gate report.' },
    { title: 'Fill stubs', detail: 'The planner writes each staged stub summary and body from its OVERVIEW section, plus STUB-INDEX.' },
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
const APPROVAL_PATH = str(parsedArgs.approvalPath)
const PROVISION_SIDECAR_CLI = str(parsedArgs.provisionSidecarCli)
const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable !== false
const SCOUT_CAP = 8

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
  required: ['clusterId', 'corpusPath', 'tldr'],
  properties: { clusterId: { type: 'string' }, corpusPath: { type: 'string' }, tldr: RETURN_TLDR_SCHEMA },
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
  required: ['verdict', 'utterance', 'tldr'],
  properties: {
    verdict: { type: 'string', enum: ['approved', 'declined'] },
    utterance: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const RECORD_SCHEMA = {
  type: 'object',
  required: ['recordPath', 'tldr'],
  properties: { recordPath: { type: 'string' }, recordedAt: { type: 'string' }, tldr: RETURN_TLDR_SCHEMA },
}

const RESUME_SCHEMA = {
  type: 'object',
  required: ['found', 'overviewPresent'],
  properties: {
    found: { type: 'boolean' },
    overviewPresent: { type: 'boolean' },
    approval: {
      type: 'object',
      properties: {
        verdict: { type: 'string' },
        approver: { type: 'string' },
        utterance: { type: 'string' },
        recorded_at: { type: 'string' },
      },
    },
    owedRetirements: { type: 'array', items: { type: 'string' } },
  },
}

const STAGE_SCHEMA = {
  type: 'object',
  required: ['committed', 'refused', 'tldr'],
  properties: {
    committed: { type: 'boolean' },
    refused: { type: 'boolean' },
    refusal: { type: 'string' },
    reply: { type: 'object' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const FILL_SCHEMA = {
  type: 'object',
  required: ['filled', 'paths', 'tldr'],
  properties: { filled: { type: 'integer' }, paths: { type: 'array', items: { type: 'string' } }, tldr: RETURN_TLDR_SCHEMA },
}

const COMMIT_SCHEMA = {
  type: 'object',
  required: ['committed', 'tldr'],
  properties: { committed: { type: 'boolean' }, tldr: RETURN_TLDR_SCHEMA },
}

// An agent outage manufactures verdicts rather than merely losing a run, so every dispatch is
// counted and rides the result as `incidents`. Rejections are re-thrown for the caller.
const agentIncidents = []

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
        const path = ['sidecarPath', 'overviewPath', 'recordPath', 'corpusPath']
          .map((k) => result[k]).find((v) => typeof v === 'string') || null
        const fallbackTldr = await tldrFallback(label, path)
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr`, and the Haiku fallback over its record also failed',
          })
        }
        return fallbackTldr === null ? { ...result, tldr: null } : { ...result, tldr: fallbackTldr, assembled_by: 'fallback' }
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
const reviewPathFor = (role) => `${TRAIL_DIR}/review-${slug(role)}.md`
const approvalRecordPath = () => `${TRAIL_DIR}/approval.json`

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

const SIDECAR_RULE = (agentType) => PROVISION_SIDECAR_CLI
  ? `Get your findings sidecar path by running this EXACT resolved invocation, and do not construct
one by hand:

    ${PROVISION_SIDECAR_CLI} --type review-findings --agent-type ${agentType}

It prints the repo-relative sidecar path on stdout. Use what it prints; on failure, report the
failure verbatim and stop.`
  : `Provision your findings sidecar with the resolved \`coordinator-doc-new --type review-findings
--agent-type ${agentType}\` (resolution rule above) and use the path it prints; never invent a path.`

const WRITE_SCOPE_RULE = `
Write only inside the roadmap directory and the trail named in this brief, and the one record this
brief assigns you. Never scaffold a stub, number one, run any stub-emitting CLI, or write a plan,
baton, sizing or goal artifact: staging belongs to the Stage phase's single engine call.`

const ROLE_CONTRACTS = {
  planner: `You are the roadmap-planner inside one roadmap-blitz run: you author the roadmap-planning
artifacts for ONE roadmap and nothing else. You never size, approve, stage or execute, and you
never dispatch another agent. The interactive PM rounds are replaced by this run's single Approve
gate after review; do not stop to ask the PM or the EM.`,
  scout: `You are a research scout inside one roadmap-blitz run. You research exactly one cluster and
write one corpus file. You never edit any roadmap artifact other than that file.`,
}

const COMMON = `${REPO_ROOT_RULE}\n${CLI_RESOLUTION_RULE}`

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
if (!TRAIL_DIR) return emptyResult({ refused: [{ reason: 'no trailDir supplied: the approval record and review sidecars have nowhere durable to land' }] })
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

if (APPROVAL_PATH) {
  if (APPROVER !== 'pm') {
    return emptyResult({ refused: [{ reason: 'approvalPath supplied but interactionMode ' + parsedArgs.interactionMode + ' clears at apm: only a hands-on run resumes from a recorded approval' }] })
  }
  const resumed = await trackAgent('resume:read-approval', agent(
    `Read three things and change nothing.

1. The recorded approval at exactly this path: ${APPROVAL_PATH}
   Return \`found: true\` with its fields (verdict, approver, utterance, recorded_at) copied
   verbatim, or \`found: false\` when the file is absent or is not valid JSON.
2. Whether ${ROADMAP_DIR}/OVERVIEW.md exists: return \`overviewPresent\`.
3. If ${ROADMAP_DIR}/inventory.md exists, return \`owedRetirements\`: the repo-relative paths of the
   live plans under docs/plans/ it marks as source plans. Empty when none.
${REPO_ROOT_RULE}`,
    { model: 'sonnet', effort: 'low', ...withRole('coordinator:executor'), label: 'resume:read-approval', phase: 'Approve', schema: RESUME_SCHEMA },
  ))
  if (!resumed || !resumed.found || !resumed.approval) {
    return emptyResult({ refused: [{ reason: 'approvalPath ' + APPROVAL_PATH + ' holds no readable approval record' }] })
  }
  if (!resumed.overviewPresent) {
    return emptyResult({ refused: [{ reason: ROADMAP_DIR + '/OVERVIEW.md is absent: a resume fire skips phases 1-3 and needs their artifacts on disk' }] })
  }
  if (resumed.approval.approver !== 'pm') {
    return emptyResult({ approval: resumed.approval, refused: [{ reason: 'the recorded approval names approver ' + JSON.stringify(resumed.approval.approver) + ', not pm' }] })
  }
  if (resumed.approval.verdict !== 'approved') {
    return emptyResult({ approval: resumed.approval, refused: [{ reason: 'the recorded PM verdict is ' + JSON.stringify(resumed.approval.verdict) + ', not approved; nothing is staged' }] })
  }
  approval = resumed.approval
  owedRetirements = resumed.owedRetirements || []
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
Read coordinator/skills/roadmap-planning/SKILL.md § Phase 1 and follow it. The accepted sizing is ${SIZING}.

${CORPUS_RULE}

Write exactly these files:
  - ${ROADMAP_DIR}/inventory.md. The inventory row MARKS each input that is a live plan under docs/plans/.
  - ${ROADMAP_DIR}/clusters.md. Each cluster is a \`## <id> — <title>\` heading carrying a \`**loe:**\`
    line (the whole-baton t-shirt read), a \`**blocked_by:**\` line (cluster ids, or none), and an
    \`**external:**\` yes or no line: yes only when answering the cluster needs the web, no when the
    repo itself is the research. blitz_stage parses these lines and refuses a cluster without loe.
  - ${ROADMAP_DIR}/reconciliation.md. One verdict per cluster (MERGE, DEFER, KEEP, DROP, MOVE); the
    verdict count equals the cluster count.
  - ${ROADMAP_DIR}/COORDINATOR-RESOLUTIONS.md only when inputs conflict.

Return \`clusters\` (id, title, verdict, external for every cluster), \`ownedRetirements\` (the live
plans the inventory marked), and \`conflicts\` (count).
${WRITE_SCOPE_RULE}
${COMMON}`,
    { model: 'opus', effort: 'high', ...withRole('coordinator:roadmap-planner'),
      label: 'roadmap-planner:synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA },
  ))
  if (!synth || synth.status !== 'synthesized') {
    return emptyResult({ refused: [{ reason: (synth && synth.blockedReason) || 'the roadmap-planner returned no synthesis' }] })
  }
  owedRetirements = synth.ownedRetirements || []

  const researchable = synth.clusters.filter((c) => c.verdict === 'KEEP' || c.verdict === 'MERGE')
  const scouts = []
  for (let i = 0; i < researchable.length; i += SCOUT_CAP) {
    const batch = researchable.slice(i, i + SCOUT_CAP)
    const done = await parallel(batch.map((c) => () => trackAgent(`scout:${c.id}`, agent(
      `${ROLE_CONTRACTS.scout}

Research cluster ${c.id} (${c.title}) for the roadmap at ${ROADMAP_DIR}/. Read ${ROADMAP_DIR}/clusters.md
for the cluster, and the corpus files it cites.
${c.external
  ? 'This cluster is marked external: yes. Research it on the web and cite each source by URL.'
  : 'This cluster is marked external: no. The repo is the research: read the code, plans and wikis it touches and cite each by repo-relative path. Do not search the web.'}

Write one file with what a stub author needs: current state, constraints, prior art, open questions.
${COMMON}
Write your record to EXACTLY this path and return it verbatim as \`corpusPath\`:

    ${corpusPathFor(c.id)}`,
      { model: 'sonnet', ...withRole(c.external ? 'coordinator:research-scout' : 'coordinator:repo-scout'),
        label: `scout:${c.id}`, phase: 'Substantiate', schema: SCOUT_SCHEMA },
    )).catch(() => null)))
    scouts.push(...done)
  }
  const missingScouts = researchable.filter((c, i) => !scouts[i]).map((c) => c.id)

  overview = await trackAgent('roadmap-planner:overview', agent(
    `${ROLE_CONTRACTS.planner}

Run roadmap-planning Phase 1.5, Steps 2 and 3. The corpus is in ${ROADMAP_DIR}/research-corpus/.
${missingScouts.length ? `These clusters have no research file because their scout failed; say so in their Contested section rather than inventing research: ${missingScouts.join(', ')}.` : ''}

Write:
  - ${ROADMAP_DIR}/OVERVIEW.md: one section per KEEP cluster, headed by NAME and never by number,
    each with a \`### Contested\` subsection. Frontmatter \`status: shape-draft\`; the Approve phase
    stamps the final status, not you.
  - ${ROADMAP_DIR}/peer-team-asks.md: present even when empty, as \`- None identified at authoring time.\`
    Template: coordinator/skills/roadmap-planning/residue/peer-team-ask-format.md.

Return \`peerTeamAsks\` (the count of asks), \`crossesRepo\` (true when any cluster crosses a repo
boundary), and \`flavor\` (a domain flavor such as data, ux or front-end when one reviewer should read
the roadmap, else an empty string).
${WRITE_SCOPE_RULE}
${COMMON}`,
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
  for (const reviewer of reviewers) {
    const role = reviewer.split(':')[1]
    const review = await trackAgent(`review:${role}`, agent(
      `You are reviewing a roadmap authored inside one roadmap-blitz run. Read ${ROADMAP_DIR}/OVERVIEW.md,
peer-team-asks.md, clusters.md and reconciliation.md, plus the research files they cite.

Judge the roadmap on its own merits: coverage of the sizing ${SIZING}, cluster boundaries, ordering,
and whether any cluster is a unit of dispatch masquerading as a unit of coverage. Then APPLY your
own findings to the roadmap files yourself, because nothing downstream reads a finding that is only
in your summary. Findings you cannot resolve go in OVERVIEW under the cluster's \`### Contested\`
heading. You never approve, never stage, and never write outside ${ROADMAP_DIR}/ and your sidecar.

${SIDECAR_RULE(role)}
${COMMON}
Also write a copy of your review record to EXACTLY this path, where the Approve gate reads it, and
return the provisioned findings sidecar path as \`sidecarPath\`:

    ${reviewPathFor(role)}`,
      { model: 'opus', ...withRole(reviewer), label: `review:${role}`, phase: 'Review', schema: REVIEW_SCHEMA },
    ))
    if (!review) missingReviews.push(role)
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
review finding is left open that a stub author would trip on; return \`declined\` otherwise. Give
your verdict as one utterance in your own words, which is recorded verbatim. This is a decision on
the roadmap's shape and its reviews: you do not edit the roadmap.
${REPO_ROOT_RULE}`,
    { model: 'opus', ...withRole('coordinator:apm'), label: 'apm:approve', phase: 'Approve', schema: APPROVAL_SCHEMA },
  ))
  if (!decision) {
    return emptyResult({ owedRetirements, refused: [{ reason: 'the APM returned no verdict; nothing is staged' }] })
  }
  approval = { verdict: decision.verdict, approver: 'apm', utterance: decision.utterance, recorded_at: null }

  // Workflow scripts have no clock, so the recording agent stamps recorded_at.
  const recorded = await trackAgent('record:approval', agent(
    `Record an approval decision. Write this JSON to ${approvalRecordPath()}, replacing the null
\`recorded_at\` with the current UTC time as an ISO-8601 string and changing nothing else:

${JSON.stringify(approval, null, 2)}
${approval.verdict === 'approved'
  ? `
Then edit ${ROADMAP_DIR}/OVERVIEW.md frontmatter to \`status: final-approved\`, adding \`approver: apm\` and
\`approval_utterance:\` set to the utterance above as a quoted string. Change nothing else.`
  : `
Do not touch OVERVIEW.md: the roadmap was declined.`}
${REPO_ROOT_RULE}
Return the path you wrote as \`recordPath\` and the timestamp you stamped as \`recordedAt\`.`,
    { model: 'sonnet', effort: 'low', ...withRole('coordinator:executor'), label: 'record:approval', phase: 'Approve', schema: RECORD_SCHEMA },
  ))
  if (!recorded || !recorded.recordedAt) {
    return emptyResult({ approval, owedRetirements, refused: [{ reason: 'the approval record was not written to ' + approvalRecordPath() + '; nothing is staged without a durable approval' }] })
  }
  approval.recorded_at = recorded.recordedAt
}

if (approval.verdict !== 'approved') {
  return emptyResult({ approval, owedRetirements, declined: true })
}

// ---------------------------------------------------------------------------
// Stage: one engine call.
// ---------------------------------------------------------------------------

const staged = await trackAgent('executor:stage', agent(
  `Stage the approved roadmap ${ROADMAP_DIR}/ in two steps, in order.

1. Commit the directory with explicit paths: \`git add\` each file under ${ROADMAP_DIR}/ by name (never
   \`-A\`, \`.\` or a directory sweep), then commit with the message "roadmap-blitz: ${RUN_ID} roadmap
   artifacts". If nothing under it is uncommitted, that is not an error.
2. Run the engine op and return its JSON reply verbatim as \`reply\`:

       <resolved coordinator-invoke> roadmap.blitz_stage '{"roadmap": "${ROADMAP_DIR}"}'

A refusal from the op (for example a cluster with no \`loe:\`) is an incident, not something to fix:
set \`refused: true\`, put its message verbatim in \`refusal\`, and stop. Never edit clusters.md or
any roadmap file to get past a refusal, and never scaffold, number or audit a stub by hand.
${CLI_RESOLUTION_RULE}
${REPO_ROOT_RULE}`,
  { model: 'sonnet', ...withRole('coordinator:executor'), label: 'executor:stage', phase: 'Stage', schema: STAGE_SCHEMA },
))

const stageReply = staged && !staged.refused && staged.reply ? staged.reply : null
if (!stageReply || !stageReply.gate_report_path) {
  if (staged && staged.refused) {
    agentIncidents.push({ role: 'executor:stage', kind: 'stage-refused', detail: String(staged.refusal || '').slice(0, 500) })
  }
  return emptyResult({ approval, owedRetirements, stage: stageReply, staged: false })
}

// ---------------------------------------------------------------------------
// Fill stubs: the staged stubs get their bodies. The frozen gate report is not touched.
// ---------------------------------------------------------------------------

const stubPaths = (Array.isArray(stageReply.stubs) ? stageReply.stubs : [])
  .map((s) => (s && typeof s === 'object' ? s.path || s.stub_path || s.file : s))
  .filter((p) => typeof p === 'string')

const fill = await trackAgent('roadmap-planner:fill-stubs', agent(
  `${ROLE_CONTRACTS.planner}

Run roadmap-planning Step 2.2 and Step 2.3 over the stubs roadmap.blitz_stage just scaffolded. Its
reply, verbatim:

${JSON.stringify(stageReply, null, 2)}

For each staged stub, read its OVERVIEW section (${ROADMAP_DIR}/OVERVIEW.md) and the research files
it cites, then write into the stub: a real \`summary:\` line, and the Step 2.2 body sections in order
(why-its-own-session paragraph; ## What this covers; ## Reference materials (read first); ##
Specification; ## Acceptance criteria; ## Recommended next steps for the picking-up EM; ## Anti-scope;
## Soft seams; ## Session Ledger; the trailing roadmap-baton comment). A stub's \`summary:\` and its
\`## What this covers\` are quoted as the PM brief of the plan built from it: a one-line stub is a
one-line brief. Then write ${ROADMAP_DIR}/STUB-INDEX.md as a query callout, not a hand table.

You edit stub bodies and \`summary:\` only. Never change a stub's frontmatter numbering, \`covers:\`,
\`blocked_by\`, loe or size fields, never hand the roadmap sizing to a stub, never mark one
ready, and never touch the frozen gate report (${stageReply.gate_report_path}).
${stubPaths.length ? `Staged stub paths:\n${stubPaths.map((p) => `  - ${p}`).join('\n')}` : 'Find the staged stubs through the paths in the reply above.'}
${COMMON}
Return \`paths\`: every repo-relative path you wrote, and \`filled\`: the count of stubs filled.`,
  { model: 'opus', effort: 'medium', ...withRole('coordinator:roadmap-planner'),
    label: 'roadmap-planner:fill-stubs', phase: 'Fill stubs', schema: FILL_SCHEMA },
))

if (fill && fill.paths && fill.paths.length) {
  await trackAgent('executor:commit-fill', agent(
    `Commit exactly these paths and nothing else, with explicit \`git add\` per path (never \`-A\`, \`.\`
or a sweep) and the message "roadmap-blitz: ${RUN_ID} stub bodies":

${fill.paths.map((p) => `  - ${p}`).join('\n')}

Never include ${stageReply.gate_report_path}. Return \`committed: true\` only when the commit landed.
${REPO_ROOT_RULE}`,
    { model: 'sonnet', effort: 'low', ...withRole('coordinator:executor'), label: 'executor:commit-fill', phase: 'Fill stubs', schema: COMMIT_SCHEMA },
  ))
} else {
  agentIncidents.push({ role: 'roadmap-planner:fill-stubs', kind: 'no-fill', detail: 'the planner returned no written paths; the staged stubs stay skeletal' })
}

return {
  gate_report_path: stageReply.gate_report_path,
  roadmapId: stageReply.roadmap_id || RUN_ID,
  roadmapDir: ROADMAP_DIR,
  approver: APPROVER,
  approval,
  awaitingApproval: false,
  stage: stageReply,
  owedRetirements,
  incidents: agentIncidents,
  trailDir: TRAIL_DIR,
}
