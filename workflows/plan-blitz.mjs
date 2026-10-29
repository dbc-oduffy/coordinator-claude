/*
 * plan-blitz — background-Workflow encoding of ONE planning wave: the DISPATCH VEHICLE of
 * coordinator/skills/plan-blitz/SKILL.md (doctrine: coordinator/docs/wiki/plan-blitz.md).
 *
 * One run = one wave as computed by `roadmap.plan_gate` (tripwire: A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE).
 * Not a roadmap author, not an executor, not the gate resolver, not the PM; the EM's only gate is
 * terminal (tripwire: A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ). `route: pm-decision` and XL exits go
 * to an adjudicator; only a `pm_only` ruling stays in `surfacedToPm`.
 *
 * args contract:
 *   repoRoot: string          ABSOLUTE, REQUIRED; every brief anchors repo-relative paths here.
 *   waveIndex: number         0 is the ungated wave.
 *   trailDir: string          ABSOLUTE; every agent writes its sidecar here.
 *   provisionSidecarCli: string  REQUIRED; resolved absolute `provision-sidecar` invocation.
 *   parallelReview: object    OPTIONAL {models, tiers, revise:{agent, model}} from the plan_review block
 *                             of contract/review-roster-fragment.json; absent, a roster-reader reads it.
 *   availablePlugins: string[]  OPTIONAL installed plugin names. Absent, each plan's `plan-prep-gate` host also
 *                             runs lib/plugin_review_signals.py attach (scan plus the plan's attached signals)
 *                             and the first reply supplies the plugin names plus the contributed signals; a
 *                             non-coordinator signal reviewer whose plugin is not listed degrades to the
 *                             default reviewer.
 *   contributedSignals: object[]  OPTIONAL signals plugins contribute ({id, plugin, selects, model?}); passed
 *                             with availablePlugins it replaces the scan. availablePlugins alone also skips
 *                             the scan, so no plugin signal is contributed and the host runs no attach.
 *     spineCheckCli: string,  // OPTIONAL resolved absolute CLI (plugin-local).
 *     armingCheckCli: string,  // OPTIONAL resolved absolute CLI (plugin-local).
 *   gateReportPath: string    the frozen `roadmap.plan_gate` JSON this wave was resolved from.
 *   pluginAgentsAvailable: boolean  defaults FALSE (see Role resolution below).
 *   engineRef: { repoRoot, workflowPath, head, workflowSha, dirty, reason }  OPTIONAL, echoed, unread.
 *   readyOp: { op, params, schema? }  OPTIONAL; one more engine op the LAST reviewer runs for a ready plan.
 *   batons: [ { id, path, title, sized, planPath|null, sizingBaton|null, executionOpen } ]
 *             executionOpen is REQUIRED (from `execution_gate.open`); an XS is handed to the driver
 *             as an `xsRuns` entry only when it is true.
 *
 * REPAIR MODE IS RETIRED: re-fire a targeted wave over the args contract above.
 *
 * Invocation (scriptPath is `${CLAUDE_PLUGIN_ROOT}`-resolved; tripwire
 * A-MISSING-WORKFLOW-SCRIPT-IS-AN-UNRESOLVED-PLUGIN-ROOT):
 *   Workflow({
 *     scriptPath: `${CLAUDE_PLUGIN_ROOT}/workflows/plan-blitz.mjs`,
 *     args: {
 *       repoRoot: "/abs/path/to/the/repo",
 *       waveIndex: 0,
 *       trailDir: "/abs/path/to/the/repo/state/plan-blitz/20260905T120000Z",
 *       gateReportPath: "/abs/path/to/the/repo/state/plan-blitz/20260905T120000Z/gate-report.json",
 *       provisionSidecarCli: "/abs/settings-home/bin/provision-sidecar",
 *       pluginAgentsAvailable: false,
 *       batons: [ { id: "pcore-03", path: "state/handoffs/...md", title: "...",
 *                   sized: false, planPath: null, executionOpen: true } ]
 *     }
 *   })
 *
 * Returns: { waveIndex, ready, pulled, replan, surfacedToPm, adjudicated, xsRuns, trailDir } — see WAVE RESULT below.
 */

// `phases` is a declaration list, not the schedule; data dependencies order the phases.

export const meta = {
  name: 'plan-blitz',
  description: 'One planning wave: sonnet scouts size the batons, an Opus EM finalises, Opus planners write, a sonnet pass resolves each plan\'s citations against the tree, the plan_review block\'s reviewers run over each plan as one parallel wave (or one chatty wave when the run enables it) each applying its own findings, and the readiness op\'s verdict, mapped in the script, decides each plan.',
  phases: [
    { title: 'Size', detail: 'One sonnet sizing-scout per unsized baton — substrate read, touchpoint inventory, prior art, and a proposed t-shirt with its evidence. Skipped for a baton that already cites a sizing-object. Then one Opus blitz-em over the whole wave interrogates every proposed size (revising down by default), finalises the route via sizing-assemble, and emits the per-baton dispatch spec the Plan phase reads; it is skipped in single-plan mode and when every baton already carries an accepted sizing.' },
    { title: 'Plan', detail: 'One Opus planner per baton, on every route and at every size — authoring is not a lane the wave economises on. Writes the plan doc through coordinator:plan / scaffold-plan; never hand-authors frontmatter. In single-plan mode the prior-art pre-flight starts beside the planner and is awaited before the premise check. Once the plan path is trusted, a haiku host runs plan.prep_gate over it and the script reads the verdict: a plan that is not PREPPED goes back to the planner with the gate findings quoted, up to three repairs, and a plan still refused after that is blocked with a "prep-gate:" reason before any checker or reviewer reads it. A host that cannot answer is an incident, never a pull reason.' },
    { title: 'Premise check', detail: 'One sonnet pass per drafted L-or-above plan (below L it does not fire), dispatched once its plan path is trusted and before any reviewer fires. Resolves the load-bearing citations in that plan against the tree — paths, symbols, refs, whether its falsifier can report red, and whether a named thing means what the plan says. It reports per-class ROWS and never a plan-level verdict; the seam after it translates those rows onto REVIEW_SCHEMA so they reach the reviewers that already apply every finding themselves. A premise miss routes BLOCKED; the class-5 rows with no writable fix are NAMED for the reviewers, who own the separating test.' },
    { title: 'Review', detail: 'Reviewers resolved per baton from the EM dispatch spec and the plan_review block (the `parallelReview` arg, else coordinator/contract/review-roster-fragment.json), then fixed by the finalised size. Fires unconditionally. Default: every tier reviewer runs in ONE parallel wave and applies its own findings by exact-text Edit, a post-wave ledger verify re-dispatches any row whose after text is absent, and a readiness host runs the op. Sequential and chatty-wave fallbacks exist. A PIVOT/REJECTED verdict applies nothing and routes to a replan baton. A prep-gate enricher repairs what the engine marks mechanical; a judgment verdict buys one sonnet resolver and one op re-ask. The script maps the op verdict to ready, pulled or replan. Host availability on the executing box is never a pull reason.' },
    { title: 'Adjudicate', detail: 'ONE sonnet agent rules every entry of the wave that would reach the PM (`surfacedToPm`, `routedElsewhere` with route pm-decision), writing a `pm_ruling:` line on each baton. A plan-weight matter is spun out as its own baton, not ruled. Only an entry it marks `pm_only` (important AND urgent AND no clear right answer, or an external or irreversible action) stays in `surfacedToPm`; the rest move to `adjudicated`. An entry it returns no ruling for fails closed.' },
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


// Trap: `args` can arrive as the serialized text of the object; uncoerced, `batons` reads empty
const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  throw new Error(
    'plan-blitz received no args object (got ' + String(parsedArgs) + '). The caller resolves ' +
    'the wave with roadmap.plan_gate, freezes that report to disk, and passes waveIndex, ' +
    'trailDir, gateReportPath and batons — see the args contract at the top of this file.'
  )
}

const READY_OP_CONTRACT = 'claude-klabauter coordinator_core/contract/plan-blitz-ready-op-contract.md'
const readyOpArg = parsedArgs.readyOp
if (readyOpArg !== undefined && readyOpArg !== null) {
  const plain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
  if (!plain(readyOpArg)
    || typeof readyOpArg.op !== 'string'
    || !/^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$/.test(readyOpArg.op)
    || !plain(readyOpArg.params)
    || Object.prototype.hasOwnProperty.call(readyOpArg.params, 'plan_path')
    || (readyOpArg.schema !== undefined && !plain(readyOpArg.schema))) {
    throw new Error(
      'plan-blitz received a malformed readyOp arg: it must be {op: dotted.lower_case.identifier, ' +
      'params: plain object without plan_path, schema?: plain object} — see ' + READY_OP_CONTRACT + '.'
    )
  }
}
const READY_OP = (readyOpArg === undefined || readyOpArg === null) ? null : readyOpArg
// The caller's reply schema types `readyOpReply`; untyped, a relaying agent can drop row fields.
const READY_OP_REPLY_SCHEMA = (READY_OP && READY_OP.schema) || {}


// Byte-for-byte mirror of `coordinator/schemas/return-tldr.schema.json`; re-copy verbatim on edit.
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

const SIZING_SCHEMA = {
  type: 'object',
  required: ['verdict', 'sidecarPath', 'counts', 'tldr'],
  properties: {
    // The scout's t-shirt read. Evidence, touchpoints, unknown mechanisms, prior art and the
    // cross-team dependency live in the sidecar; the blitz-em reads them from sidecarPath.
    verdict: { type: 'string', enum: ['XS', 'S', 'M', 'L', 'XL', 'XXL'] },
    sidecarPath: { type: 'string' },
    counts: {
      type: 'object',
      properties: {
        touchpoints: { type: 'integer' },
        unknownMechanisms: { type: 'integer' },
        priorArt: { type: 'integer' },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const WAVE_DISPATCH_SCHEMA = {
  type: 'object',
  required: ['decisions', 'tldr'],
  properties: {
    decisions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['batonId', 'tshirt', 'route', 'rationale', 'reviewers'],
        properties: {
          batonId: { type: 'string' },
          tshirt: { type: 'string', enum: ['XS', 'S', 'M', 'L', 'XL', 'XXL'] },
          route: { type: 'string' },
          
          
          rationale: { type: 'string' },
          
          
          sizingObject: { type: ['string', 'null'] },
          
          
          sizingObjectAbsence: { type: 'string' },
          sizingBaton: { type: ['string', 'null'] },
          reviewers: { type: 'array', items: { type: 'string' } },
          
          
          surfacedToPm: { type: 'boolean' },
          surfacedQuestion: { type: 'string' },
        },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['batonId', 'planPath', 'status', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },
    status: { type: 'string', enum: ['drafted', 'blocked'] },
    blockedReason: { type: 'string' },
    exitCriterion: { type: 'string' },
    reviewSignals: { type: 'array', items: { type: 'string' } },
    tldr: RETURN_TLDR_SCHEMA,
  },
}


// `UNCHECKABLE` is a first-class row value, not an omission: it marks a semantic-class citation
// whose truth no check could settle; it never blocks.
const PREMISE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'planPath', 'rows', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },
    spinePresent: { type: 'boolean' },
    rows: {
      type: 'array',
      items: {
        type: 'object',
        required: ['questionClass', 'citation', 'verdict'],
        properties: {
          questionClass: { type: 'integer' },
          citation: { type: 'string' },
          verdict: {
            type: 'string',
            enum: ['RESOLVES', 'UNRESOLVED', 'CONTRADICTED', 'UNCHECKABLE'],
          },
          evidence: { type: 'string' },
          // Class 4 only: the falsifier `baseline_ref` the row was read against.
          baseline_ref: { type: 'string' },
          // The 1-based plan line carrying the citation.
          line: { type: 'integer' },
        },
      },
    },
    falsifierVerdict: { type: 'string' },
    citationsSkipped: { type: 'integer' },
    carry: {
      type: 'object',
      properties: {
        firstPass: { type: 'boolean' },
        carried: { type: 'integer' },
        fresh: { type: 'integer' },
      },
    },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['batonId', 'reviewer', 'verdict', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    reviewer: { type: 'string' },
    verdict: { type: 'string', enum: ['APPROVED', 'WARN', 'BLOCKED', 'PIVOT', 'REJECTED'] },
    // Who holds the answer to an unfixable BLOCKED (the APM or a domain reviewer, never the EM).
    heldBy: { type: 'string' },
    sidecarPath: { type: 'string' },
    findingCount: { type: 'integer' },
    // A self-applying reviewer fills both: whether it edited the plan, and one row per finding.
    planEdited: { type: 'boolean' },
    dispositions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'disposition'],
        properties: { id: { type: 'string' }, disposition: { type: 'string', enum: ['applied', 'declined'] }, reason: { type: 'string' } },
      },
    },

    // where the claim is stated; `resolveVerdict` reads it to resolve the REJECTED

    premiseFailure: { type: 'string' },
    alternativesConsidered: { type: 'string' },
    // Filled only by a plan's last reviewer (readinessStep).
    readinessVerdict: {
      type: 'object',
      properties: {
        plan: { type: 'string' },
        verdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
        pull_class: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
        mechanical_repairs: { type: 'array', items: { type: 'object' } },
        prep_gate: { type: 'object' },
        reason: { type: 'string' },
        blocking: { type: 'array', items: { type: 'string' } },
        blocking_findings: { type: 'integer' },
        advisory_findings: { type: 'integer' },
      },
      // Trap: honouredReadiness drops a reply without prep_gate; `required` stops a host trimming it.
      required: ['verdict', 'pull_class', 'mechanical_repairs', 'prep_gate'],
    },
    readinessReviews: {
      type: 'array',
      items: {
        type: 'object',
        properties: { reviewer: { type: 'string' }, verdict: { type: 'string' } },
      },
    },
    readinessError: { type: 'string' },
    readinessAttempts: { type: 'integer' },
    readyOpReply: READY_OP_REPLY_SCHEMA,
    readyOpError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PLAN_PREP_GATE_SCHEMA = {
  type: 'object',
  required: ['verdict', 'findings', 'message', 'tldr'],
  properties: {
    verdict: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    findings: { type: 'array', items: { type: 'string' } },
    message: { type: 'string' },
    availablePlugins: { type: 'array', items: { type: 'string' } },
    signals: { type: 'array', items: { type: 'object' } },
    attached: { type: 'array', items: { type: 'string' } },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PLAN_STAGE_PREP_GATE_ROUNDS = 3

const PREP_GATE_REVISE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'before', 'after', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    before: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    after: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    repaired: { type: 'array', items: { type: 'string' } },
    coverageRepaired: { type: 'array', items: { type: 'string' } },
    // Op-driven path only; absent `after*` means the re-run did not answer (read as no reply).
    afterVerdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
    afterPullClass: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
    afterReason: { type: 'string' },
    afterBlocking: { type: 'array', items: { type: 'string' } },
    afterError: { type: 'string' },
    gateReport: { type: 'string' },
    readyOpReply: READY_OP_REPLY_SCHEMA,
    readyOpError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const JUDGMENT_RESOLVE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'resolved', 'unresolved', 'touched', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    resolved: { type: 'array', items: { type: 'string' } },
    unresolved: { type: 'array', items: { type: 'string' } },
    touched: { type: 'array', items: { type: 'string' } },
    // Absent with `afterError` set: the re-ask failed twice and the plan stands `errored`.
    afterVerdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
    afterPullClass: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
    afterReason: { type: 'string' },
    afterBlocking: { type: 'array', items: { type: 'string' } },
    afterError: { type: 'string' },
    afterPrepGate: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    readyOpReply: READY_OP_REPLY_SCHEMA,
    readyOpError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PREMISE_RECHECK_SCHEMA = {
  type: 'object',
  required: ['batonId', 'rows', 'retired', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    rows: PREMISE_SCHEMA.properties.rows,
    retired: { type: 'array', items: { type: 'string' } },
    afterVerdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
    afterPullClass: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
    afterReason: { type: 'string' },
    afterBlocking: { type: 'array', items: { type: 'string' } },
    afterError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PRIOR_ART_SCHEMA = {
  type: 'object',
  required: ['verdict', 'sidecarPath', 'tldr'],
  properties: {
    verdict: { type: 'string', enum: ['COMPATIBLE', 'WARN', 'BLOCKED-SURFACE-TO-PM', 'DEGRADED'] },
    sidecarPath: { type: 'string' },
    claimsChecked: { type: 'integer' },
    conflicts: { type: 'integer' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const ADJUDICATION_SCHEMA = {
  type: 'object',
  required: ['batonId', 'verdict', 'pmOnly', 'ruling', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    verdict: { type: 'string', enum: ['ruled', 'pm-only'] },
    pmOnly: { type: 'boolean' },
    pmOnlyGround: { type: 'string', enum: ['important-urgent-no-clear-answer', 'external-or-irreversible'] },
    ruling: { type: 'string' },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const PLAN_COVERAGE_SCHEMA = {
  type: 'object',
  required: ['verdict', 'sidecarPath', 'tldr'],
  properties: {
    verdict: { type: 'string', enum: ['COMPLETE', 'INCOMPLETE', 'BLOCKED-SURFACE-TO-PM', 'SCOPE-MISMATCH', 'DEGRADED'] },
    sidecarPath: { type: 'string' },
    mechanicalFindings: { type: 'integer' },
    judgmentFindings: { type: 'integer' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// Single-plan mode: premise result at top level, plan-coverage verdict as `coverage`.
const PRE_REVIEW_SCHEMA = {
  ...PREMISE_SCHEMA,
  required: [...PREMISE_SCHEMA.required, 'coverage'],
  properties: {
    ...PREMISE_SCHEMA.properties,
    coverage: {
      type: 'object',
      required: PLAN_COVERAGE_SCHEMA.required.filter((k) => k !== 'tldr'),
      properties: Object.fromEntries(
        Object.entries(PLAN_COVERAGE_SCHEMA.properties).filter(([k]) => k !== 'tldr'),
      ),
    },
  },
}


const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable === true

function withRole(agentType) {
  return PLUGIN_AGENTS && agentType ? { agentType } : {}
}


const agentIncidents = []

// A result that skipped `tldr` gets a code WARN anchored at its sidecar; a recovered fallback never
// reads as an OK.
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
          detail: 'the agent returned nothing — its structured-output call exhausted its retries',
        })
        return result
      }
      if (typeof result === 'object' && !result.tldr) {
        const fallbackTldr = tldrFallback(
          label,
          typeof result.sidecarPath === 'string' ? result.sidecarPath : null,
        )
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr` and no `sidecarPath` to anchor a code tldr',
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


const REVIEWER_ROSTER = new Set([
  'coordinator:plan-reviewer',
  'coordinator:staff-eng',
  'coordinator:apm',
  'coordinator:eng-director',
])

// Reachable only through a plan's `review_signals` (single-sourced in contract/review-signals.json),
// never as a default reviewer.
const SIGNAL_REVIEWERS = {
  'data-science': 'coordinator:staff-data-sci',
  'front-end': 'coordinator:senior-front-end',
  'ux-flow': 'coordinator:staff-ux',
  'cross-repo-seam': 'coordinator:eng-director',
}

// Signals an installed plugin contributes (its shipped review-signals.json, via
// lib/plugin_review_signals.py). Registered into SIGNAL_REVIEWERS/SIGNAL_ROSTER at run time; DoE names
// no plugin agent, and a coordinator signal id is never overwritten.
const CONTRIBUTED_MODELS = {}

const REVIEWER_ALIASES = new Map([
  ['patrik', 'coordinator:staff-eng'],
  ['zoli', 'coordinator:eng-director'],
])

const DEFAULT_REVIEWER = 'coordinator:staff-eng'

const SIGNAL_ROSTER = new Set(Object.values(SIGNAL_REVIEWERS))

function registerContributedSignals(contributed) {
  const registered = []
  for (const s of Array.isArray(contributed) ? contributed : []) {
    if (!s || typeof s.id !== 'string' || typeof s.selects !== 'string' || !s.selects.includes(':')) continue
    if (Object.prototype.hasOwnProperty.call(SIGNAL_REVIEWERS, s.id)) continue
    SIGNAL_REVIEWERS[s.id] = s.selects
    SIGNAL_ROSTER.add(s.selects)
    if (typeof s.model === 'string' && s.model) CONTRIBUTED_MODELS[s.selects] = s.model
    registered.push(s.id)
  }
  return registered
}

const PLAN_SIZES = new Set(['XS', 'S', 'M', 'L', 'XL', 'XXL'])

// `block`: the fragment's plan_review block or null; `forwarded`: the `parallelReview` arg or null.
function buildRoster(block, forwarded) {
  const fwd = forwarded && typeof forwarded === 'object' ? forwarded : null
  const fwdModels = (fwd && fwd.models && typeof fwd.models === 'object') ? fwd.models : {}
  const fwdTiers = (fwd && fwd.tiers && typeof fwd.tiers === 'object') ? fwd.tiers : null
  const blockNamesReviewer = !!(block && block.tiers && typeof block.tiers === 'object'
    && Object.values(block.tiers).some((s) => s && Array.isArray(s.reviewers) && s.reviewers.length > 0))
  let specs = blockNamesReviewer ? block.tiers : null
  if (!specs && fwdTiers) {
    specs = {}
    for (const [agentType, names] of Object.entries(fwdTiers)) {
      for (const tier of Array.isArray(names) ? names : []) {
        if (!specs[tier]) specs[tier] = { reviewers: [] }
        specs[tier].reviewers.push({ agentType })
      }
    }
  }
  if (!specs) return null
  const models = {}
  const tiers = {}
  for (const [tier, spec] of Object.entries(specs)) {
    tiers[tier] = []
    for (const e of (spec && Array.isArray(spec.reviewers)) ? spec.reviewers : []) {
      if (fwdTiers && !(Array.isArray(fwdTiers[e.agentType]) && fwdTiers[e.agentType].includes(tier))) continue
      const model = fwdModels[e.agentType] || e.model
      if (model) models[e.agentType] = model
      tiers[tier].push({
        agentType: e.agentType, model,
        ...(e.role ? { role: e.role } : {}),
        ...(e.brief ? { brief: e.brief } : {}),
      })
    }
  }
  for (const s of Object.values((block && block.signal_reviewers) || {})) {
    const model = fwdModels[s.agentType] || s.model
    if (model) models[s.agentType] = model
  }
  for (const [agentType, model] of Object.entries(fwdModels)) {
    if (!models[agentType]) models[agentType] = model
  }
  const revise = fwd && fwd.revise && typeof fwd.revise.agent === 'string' && fwd.revise.agent
    ? { agent: fwd.revise.agent, model: fwd.revise.model }
    : { agent: 'coordinator:plan-author', model: undefined }
  return { tiers, models, revise }
}

function ladderRow(tshirt, roster) {
  return Object.prototype.hasOwnProperty.call(roster.tiers, tshirt) ? roster.tiers[tshirt] : (roster.tiers.XL || [])
}

const PRE_REVIEW_CHECKER_SIZES = new Set(['L', 'XL', 'XXL'])

function preReviewCheckersOwed(tshirt) {
  return PRE_REVIEW_CHECKER_SIZES.has(tshirt) || !PLAN_SIZES.has(tshirt)
}

function planReviewers(tshirt, resolved, signals, roster) {
  const row = [...ladderRow(tshirt, roster)]
  const sigs = Array.isArray(signals) ? signals : []
  if (row.length && row[0].agentType !== 'coordinator:plan-reviewer') {
    const domain = sigs
      .map((sig) => SIGNAL_REVIEWERS[sig])
      .find((r) => r && r !== 'coordinator:eng-director' && resolved.includes(r))
    const boundary = !row.some((e) => e.agentType === 'coordinator:eng-director') && resolved.includes('coordinator:eng-director')
    const swap = domain || (boundary ? 'coordinator:eng-director' : null)
    if (swap) row[0] = { agentType: swap, model: roster.models[swap] || CONTRIBUTED_MODELS[swap] }
  }
  const seen = new Set()
  const entries = row.filter((e) => {
    const key = `${e.agentType}|${e.role || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  const reviewers = entries.map((e) => e.agentType)
  return { reviewers, entries, dropped: resolved.filter((r) => !reviewers.includes(r)) }
}

// Set once for each review stage before any reviewer dispatches; `reviewModel` is its only reader.
let REVIEW_ROSTER = null

function reviewModel(agentType) {
  const model = (REVIEW_ROSTER && REVIEW_ROSTER.models[agentType]) || CONTRIBUTED_MODELS[agentType]
  if (!model) throw new Error(`the plan_review block names no model for ${agentType}`)
  return model
}

// `availablePlugins`: a Set of installed plugin names from the `availablePlugins` arg, or null when
// the arg was not passed. Only `coordinator` is assumed present; any other plugin's reviewer needs
// the arg to name its plugin, else it degrades to DEFAULT_REVIEWER.
function resolveReviewers(named, signals, availablePlugins) {
  const signalled = (Array.isArray(signals) ? signals : []).map((sig) => SIGNAL_REVIEWERS[sig]).filter(Boolean)
  const base = Array.isArray(named) && named.length ? named : [DEFAULT_REVIEWER]
  const wanted = [...base, ...signalled]
  const substitutions = []
  const resolved = []

  for (const raw of wanted) {
    const text = String(raw || '').trim()
    if (REVIEWER_ROSTER.has(text) || SIGNAL_ROSTER.has(text)) {
      const plugin = text.split(':')[0]
      if (plugin !== 'coordinator' && !(availablePlugins && availablePlugins.has(plugin))) {
        substitutions.push(
          `${text} -> ${DEFAULT_REVIEWER} (${plugin} plugin not installed; review downgraded, not skipped)`,
        )
        resolved.push(DEFAULT_REVIEWER)
        continue
      }
      resolved.push(text)
      continue
    }
    const bare = text.replace(/^[a-z-]+:/i, '').toLowerCase()
    const aliased = REVIEWER_ALIASES.get(bare)
    if (aliased) {
      substitutions.push(`${text} -> ${aliased} (persona name resolved)`)
      resolved.push(aliased)
      continue
    }
    substitutions.push(
      `${text} -> ${DEFAULT_REVIEWER} (NOT ON THE ROSTER; review downgraded, not skipped)`,
    )
    resolved.push(DEFAULT_REVIEWER)
  }

  return { reviewers: [...new Set(resolved)], substitutions }
}

const PREMISE_SNIPPET_DIGEST = '3fc9589b41f7a50a7d2a8a90a0664378635e006548f22507b9ac1c3102c0413c'

const PREMISE_CHECK_CONTRACT = `## Premise Check Contract

Read \`snippets/premise-check-contract.md\` (classes 1-3) and \`snippets/premise-check-class-5-semantics.md\`
(class 5) in full, under the coordinator plugin root beside \`agents/\`, before you check anything. They are
the calibration for the classes: the tolerance rule, the \`<repo>@<ref>\` requirement, class 5's two firing
conditions, and the rule that an absence is evidence only if the instrument could have seen presence.`

const INSTRUMENT_CAN_REPORT_RED_CONTRACT = `## Can This Instrument Report Red?

Read \`snippets/instrument-can-report-red.md\` in full, under the coordinator plugin root beside \`agents/\`: the
tell an unarmed falsifier shows, and how to trace its verdict to an exit path.`

// `${ARMING_CHECK_CLI}` stays an unsubstituted placeholder here; premiseChecker() renders it per host.
const PREMISE_CLASS_LIST = `Five question classes. Answer each for every load-bearing citation. Read
\`agents/premise-checker.md\` § The five question classes and § Verdicts in full (under the coordinator
plugin root beside \`snippets/\`): paths, symbols, refs, falsifier arming and asserted semantics, with the
row verdicts RESOLVES · UNRESOLVED · CONTRADICTED · UNCHECKABLE.
Class 4 on this host: run \`\${ARMING_CHECK_CLI} <instrument> --json\` (use this invocation, not the one that
section shows) and carry its verdict into \`falsifierVerdict\` VERBATIM. Class 4 compares the falsifier's
\`baseline_output\` against the tree at its \`baseline_ref\`, never at HEAD.`

function fnv1a32Hex(text) {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
}

const PREMISE_BRIEF_VERSION = fnv1a32Hex(
  PREMISE_SNIPPET_DIGEST,
)

const ROLE_CONTRACTS = {
  'blitz-em': `You are the blitz-em: the engineering-manager judgment inside one plan-blitz wave.
You size and route; you never execute, never author roadmap batons, and never resolve a
decision that belongs to the PM. Your characteristic move when reviewing a size is revising DOWN —
a scout reading unfamiliar substrate reads large, counting touchpoints as depth. Revising UP is the
signal that matters most and requires you to NAME the mechanism the scout missed.`,

  'reviewer': `You are a staff-level reviewer with exacting standards. Assume defects exist — a
review finding none is almost certainly incomplete. Hold LLM-assisted work to a HIGHER bar. Your
lenses: correctness, scope honesty, sequencing, testability, and whether any premise the artifact
rests on is actually true of this tree right now. Apply every finding you log yourself, in place,
in the artifact under review — filtering does not happen upstream any more, and there is no
one behind you to apply what you found. You are UNCONDITIONAL on verdict: an APPROVED does not
skip applying. Never write attribution ("Review: <you>", a finding number, your name) into the
reviewed artifact — the findings ledger in your own sidecar is the attribution record.`,

  // Single-plan pre-flights: `withRole` attaches no agentType without plugin agents, so the role's
  // brief must name its agent file by path.
  'prior-art-checker': `You are the prior-art-checker pre-flight for single-plan mode. Read
\`agents/prior-art-checker.md\` in full and follow its protocol exactly — this line names your
role, it does not restate the protocol. You are a recall agent, not a reviewer: cross-reference the
sizing intent's claims against wikis, decisions and lessons, and report Conflict /
Compatible-but-relevant / Silent per its § Verification Protocol. You never edit the plan, never
refuse it, and never judge architecture — report, and let the planner and reviewers act on it.`,

  'plan-coverage-checker': `Inside this dispatch, after the premise rows are recorded, you also run the
plan-coverage lenses for single-plan mode. Read \`agents/plan-coverage-checker.md\` in full and follow
its protocol exactly — this line names the role, it does not restate the eight lenses. Every lens is report-only: no inline plan edits, no
auto-fix, no auto-block — the EM and reviewers own every disposition. Report clean if clean; a
review finding none is not itself suspicious the way an under-inspected human review would be,
because your checks are mechanical.`,
}

const slug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

const sidecarFor = (trailDir, batonId, role) => `${trailDir}/${waveSlot}/${slug(batonId)}.${slug(role)}.md`
// Op params files: the argv of a reviewer-run op carries only this path, never inline JSON.
const paramsFileFor = (trailDir, batonId, role) => sidecarFor(trailDir, batonId, role).replace(/\.md$/, '.json')
const paramsFilesFor = (trailDir, batonId) => ({ readiness: paramsFileFor(trailDir, batonId, 'readiness-params'), readyOp: paramsFileFor(trailDir, batonId, 'ready-op-params') })

const unreachableSidecars = []
const sidecarHolders = []
function checkSidecarPath(batonId, role, returned) {
  const claimed = typeof returned === 'string' ? returned.trim() : ''
  if (!claimed) return returned
  const segments = claimed.split(/[\\/]+/)
  const at = segments.indexOf('subagent-share')
  if (at === -1) {
    unreachableSidecars.push({ batonId, role, returned: claimed })
    return returned
  }
  if (segments[at + 1]) sidecarHolders.push({ batonId, role, holder: segments[at + 1], returned: claimed })
  return returned
}

// The minority holder spellings, or `[]`; silent when there is no majority to be an outlier of.
function divergentSidecarHolders() {
  const counts = new Map()
  for (const { holder } of sidecarHolders) counts.set(holder, (counts.get(holder) || 0) + 1)
  if (counts.size < 2) return []
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const [modal, modalCount] = ranked[0]
  if (modalCount <= ranked[1][1]) return []
  return sidecarHolders
    .filter((entry) => entry.holder !== modal)
    .map((entry) => ({ ...entry, agreedHolder: modal, agreedBy: modalCount }))
}

// Verdict resolution: an inbound verdict word becomes a wave route here, once; `raw` keeps the
// inbound word.
const PIVOT = 'PIVOT'

function resolveVerdict(review) {
  const raw = String(review.verdict || '').toUpperCase()
  const premise = String(review.premiseFailure || '').trim()
  let verdict = raw
  let aliased = null
  if (raw === 'REJECTED') {
    verdict = premise ? PIVOT : 'BLOCKED'
    aliased = `REJECTED -> ${verdict} (premiseFailure ${premise ? 'stated' : 'absent'})`
  }
  return { ...review, verdict, raw, aliased, pivot: verdict === PIVOT }
}

const SIDECAR_HEREDOC_RULE = (pathForLabel) => {
  const runKey = String(parsedArgs.trailDir || '').replace(/\\/g, '/').replace(/\/+$/, '').split('/').pop() || '<run>'
  const label = String(pathForLabel || '').replace(/\\/g, '/').split('/').pop().replace(/\.md$/, '') || '<label>'
  return `
Your sidecar dir is \`.coordinator-local/workflow-sidecars/plan-blitz/${runKey}/${label}/\` (create it with
\`mkdir -p\`; run notes go there). If the harness denies the Write tool on a path this brief declares
("Subagents should return findings as text"), write that path with a quoted Bash heredoc,
\`cat > <path> <<'EOF'\`, never skip it, and name the path in your report. A path the Write tool has
already written stays on Write/Edit: a heredoc overwrite is refused at commit as blob drift.`
}

const TRAIL_RULE = (sidecarPath) => `
Write your sidecar to EXACTLY this path and return it verbatim as \`sidecarPath\`:

    ${sidecarPath}

Do not choose your own filename. Peers in this wave write beside you, and a name you pick because
it is the obvious one is the same name they pick for the same reason — the later write silently
destroys the earlier, and a lost sidecar is indistinguishable from a review that never ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the wave's reader will never see.
${SIDECAR_HEREDOC_RULE(sidecarPath)}`

const CLI_RESOLUTION_RULE = `
Every coordinator CLI named in this brief is invoked BY ABSOLUTE PATH through the settings home,
never as a bareword — no coordinator CLI is reliably on PATH, and a bareword exits 127. On a POSIX
host:

    "\${COORDINATOR_SETTINGS_HOME:-\${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>"

On a PowerShell host, guard first (nothing exports the variable, so unset is the DEFAULT state of
a fresh shell) and then call the \`.exe\`:

    if (-not $env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME = Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings" }
    & "$env:COORDINATOR_SETTINGS_HOME\\bin\\<cli>.exe" <args>

Canonical rule: \`snippets/resolve-coordinator-bin.md\`. If a CLI still does not run after
resolving it this way, report the failure verbatim — command-not-found after this means the CLI is
genuinely absent, which is a finding. It never means invent a substitute or hand-author the record
the CLI would have written.`

const PROVISION_CLI_RULE = (agentType) => parsedArgs.provisionSidecarCli
  ? `Get that path by running this EXACT resolved invocation, and do not construct one by hand:

    ${parsedArgs.provisionSidecarCli} --agent-type ${agentType.includes(':') ? agentType : `coordinator:${agentType}`}

It prints the repo-relative sidecar path on stdout and exits 0; on any failure it names the
precondition that failed and exits non-zero. Use what it prints.

`
  : `This brief was fired without \`provisionSidecarCli\`, so no resolved invocation is available
and \`<machinery_root>\` is a placeholder you cannot resolve from in here. The wave REFUSES on
that arg before it dispatches anyone, so reading this at all is a defect: report it as a CALLER
defect (the wave was fired without \`provisionSidecarCli\`) and stop. Do NOT invent a path — a
plausible invention (\`.subagent-share/\` at the repo root, say) is refused by
\`review-findings-ledger\`, read by nothing else, and it fails SILENTLY, which is the whole reason
the refusal is upstream of you rather than a warning in here.

`

// Two vocabularies, not one: `provision-sidecar --agent-type` takes an agent identity, the
// sidecar's `type:` a doc type; the two coincide only for some agents.
const REVIEW_SIDECAR_RULE = (pointerPath, agentType, docType = agentType) => `
Read \`snippets/plan-blitz-review-sidecar-rule.md\` (under the coordinator plugin root, beside
\`agents/\`) in full and follow it: your findings sidecar is YOUR OWN PROVISIONED SIDECAR under
\`<machinery_root>/subagent-share/<your session id>/\`, never the wave trail.

${PROVISION_CLI_RULE(agentType)}Its frontmatter carries this key at column zero:

    agent_type: ${docType}

Your POINTER file goes at EXACTLY this path:

    ${pointerPath}
${SIDECAR_HEREDOC_RULE(pointerPath)}`

const REPO_ROOT =
  typeof parsedArgs.repoRoot === 'string' && parsedArgs.repoRoot.trim()
    ? parsedArgs.repoRoot.trim()
    : null

// The caller supplies the resolver (`A-SIDECAR-THE-DISPOSITION-OP-REFUSES-LOSES-ONLY-THE-RECORD`).
const PROVISION_SIDECAR_CLI =
  typeof parsedArgs.provisionSidecarCli === 'string' && parsedArgs.provisionSidecarCli.trim()
    ? parsedArgs.provisionSidecarCli.trim()
    : null

// `instrument-can-report-red` is plugin-local like the spine checker; the fallback is a repo path.
const ARMING_CHECK_CLI =
  (typeof parsedArgs.armingCheckCli === 'string' ? parsedArgs.armingCheckCli : '').trim() ||
  `python3 ${REPO_ROOT || '<repoRoot>'}/coordinator/bin/instrument-can-report-red.py`

const SPINE_CHECK_CLI =
  typeof parsedArgs.spineCheckCli === 'string' && parsedArgs.spineCheckCli.trim()
    ? parsedArgs.spineCheckCli.trim()
    : null

const SPINE_CHECK_RULE = (planPath) => SPINE_CHECK_CLI
  ? `    ${SPINE_CHECK_CLI} ${planPath}`
  : `    (this wave was fired without \`spineCheckCli\`, so no resolved invocation is available.
    Report that the spine could not be validated and name it a CALLER defect — the wave was
    fired without \`spineCheckCli\`. Do NOT substitute a repo-relative path: the checker lives
    in the plugin root, which this script cannot resolve.)`

const REPO_ROOT_RULE = REPO_ROOT ? `
Every repo-relative path in this brief — the baton record, the plan, a spine row's \`writes:\`,
anything you read or create — is relative to THIS repo root, and nothing else:

    ${REPO_ROOT}

Resolve them there, and change into it before you run anything. Do NOT resolve against your own
working directory: you inherited it from the process that dispatched you, it is not necessarily
this repo, and a path that silently resolves somewhere else produces work that looks done and is
not. If a path you were given does not exist under that root, say so — never search for a
plausible substitute elsewhere on the box.` : ''

const NO_EXECUTION_RULE = `
You do not execute. No code changes, no "quick fix while I'm here", no chunk work. A defect you
spot in the tree is something you report, not something you do.`

const MISE_PREP_RULE = `
Read \`snippets/plan-blitz-mise-prep-rule.md\` (under the coordinator plugin root, beside \`agents/\`) in
full and follow it: FOUR DECLARATIONS (\`writes:\`, \`census:\`, \`external_gate[].requires:\`,
\`prime_exit_criterion:\`) plus \`anchor_premises:\` and \`register_claims:\`, because the next
ceremony is gated on them.`

const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

// Copy, never paraphrase: `resolve()` in `coordinator/bin/lib/pm_brief.py` treats the baton's
// verbatim as data; a paraphrase would drift from the PM's words.
const PM_BRIEF_RULE = `
Read \`snippets/plan-blitz-pm-brief-rule.md\` (under the coordinator plugin root, beside \`agents/\`) in
full and follow it: the PM's verbatims or the baton's ask into a \`## PM brief\`, and a
\`traces_to_brief\` on every spine row. The spine checker that enforces the trace is
${SPINE_CHECK_RULE('<your plan path>')}`


function sizingScout(baton, waveIndex, trailDir) {
  return trackAgent('sizing-scout', agent(
    `You are a sizing scout for plan-blitz wave ${waveIndex}. Size ONE roadmap baton.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}

Read the baton record, then read the substrate it names. Produce a t-shirt read (XS-XXL) of
ENGINEERING COMPLEXITY ONLY. You are not being asked what it is worth, how urgent it is, or how
long anyone wants to spend — only how complex the work is.

Read \`agents/sizing-scout.md\` (under the coordinator plugin root, beside \`snippets/\`): its Rubric and
"Plan-blitz wave sizing" sections govern this read, including the ABSENT rule (check
\`git log --all --diff-filter=A\` before calling any artifact missing). Report touchpoints,
unknownMechanisms, priorArt and crossTeamDependency separately, unblended.

Write the full read — evidence (free text: the blitz-em interrogates the REASONING), touchpoints,
unknownMechanisms, priorArt, crossTeamDependency — into your sidecar. Return only \`verdict\` (the
t-shirt), \`sidecarPath\`, \`counts\` (touchpoints, unknownMechanisms, priorArt as integers) and \`tldr\`.

Your read will be interrogated by an EM who revises down by default. Do not pre-inflate against
that, and do not hedge: give the number you actually believe and the evidence that produced it.
An honest S that survives is worth more than a defensive L that gets cut.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'sizing'))}`,
    {
      label: `size:${baton.id}`,
      phase: 'Size',
      model: 'sonnet',
      schema: SIZING_SCHEMA,
    },
  ))
}

// Phase 3 — Plan
function planner(baton, decision, waveIndex, trailDir, singleContext, prepGateFindings) {
  const existingPlanPath = prepGateFindings ? prepGateFindings.planPath : baton.planPath
  const sizingFm = decision.sizingObject ? `"${decision.sizingObject}"` : 'null'

  const prepGateBlock = prepGateFindings ? `

PREP GATE REFUSAL. The stage ran \`plan.prep_gate\` over this plan and it is not PREPPED. Gate
message and findings, quoted verbatim:

${prepGateFindings.message || '(no message)'}
${(prepGateFindings.findings || []).map((f) => `  - ${f}`).join('\n')}

Repair exactly these, as the section above directs, and return the same \`planPath\`.` : ''

  const revising = existingPlanPath
    ? `A plan already exists at ${existingPlanPath}. Read \`agents/plan-author.md\` (under the coordinator
plugin root) § Plan-blitz wave briefs / Revising in place in full and follow it.${prepGateBlock}`
    : `No plan exists yet. Author one.`

  const sizingAbsenceNote = decision.sizingObjectAbsence ? `

     WHY THERE IS NONE, from the EM that sized you: ${decision.sizingObjectAbsence}
     Carry that sentence into your summary verbatim. Without it the missing artifact surfaces later
     as a schema refusal on \`prime_exit_criterion.derived_from\` — a field nobody mis-authored — and
     the reader has no way back to what actually failed. Do NOT reach for the baton's handoff to
     fill \`derived_from\` instead: \`plan.schema.json\` does not admit it, deliberately, because the
     bar means "someone sized this" rather than "this plan came from somewhere".` : ''

  const authoringBrief = existingPlanPath ? `You are revising, so the generator has no part in this. Bring the plan up to the mise-prep
bar (the FOUR DECLARATIONS below and the task spine), not only the prose you were sent for.` : PLUGIN_AGENTS ? `Invoke the coordinator:plan skill and follow it; your charter owns the scaffold rule.
Sizing-object that routed you here, cited with the scaffold's sizing flag, used EXACTLY:
\`${decision.sizingObject || '(none emitted)'}\`. If none was emitted, write \`sizing_object: null\` and
say so in your summary; never invent a path.${sizingAbsenceNote}` : `The coordinator plan tooling is NOT installed on this machine, so hand-author the plan file at
${REPO_ROOT || '<repoRoot>'}/docs/plans/<YYYY-MM-DD>-<slug>.md, with \`sizing_object: ${sizingFm}\`. Read
\`agents/plan-author.md\` (under the coordinator plugin root) § Plan-blitz wave briefs / Hand-authoring
without the scaffold in full and follow it: its exact frontmatter keys and its task spine.

VALIDATE THE SPINE BEFORE YOU RETURN; exit 0 is required:

${SPINE_CHECK_RULE('<your plan path>')}`

  const priorArtNote = singleContext && singleContext.priorArtSidecarPath ? `
A prior-art pre-flight runs alongside you over this baton's sizing intent and writes its sidecar at
${singleContext.priorArtSidecarPath}. If the file exists when you are about to write, read it; if
not, write without it. Its CONFLICT bucket is prior art the plan must reconcile with, and every
reviewer is handed its verdict, so a conflict you did not see is still reconciled before any verdict.` : ''

  const singleContextBlock = singleContext ? `
SINGLE-PLAN MODE (§ Pinned interfaces / C4 body item 3). \`prime_exit_criterion.statement\` is the
sizing's own \`exit_criterion\` verbatim: "${singleContext.exitCriterionStatement || '(the sizing carries none)'}".
Set \`derived_from\` to the sizing path, \`${singleContext.sizingPath || '(no sizing path)'}\` — never the
baton's handoff. Refine the statement ONLY when the sizing carries none at all; do not rephrase one
that is already there, even to make it read better — the accepted wording is the PM's touchpoint,
not yours to improve.
${priorArtNote}` : ''

  return trackAgent('planner', agent(
    `Write the implementation plan for ONE roadmap baton, in plan-blitz wave ${waveIndex}.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}
Finalised size: ${decision.tshirt}, route: ${decision.route}
EM's sizing rationale: ${decision.rationale}

${revising}
${authoringBrief}

Read \`agents/plan-author.md\` § Plan-blitz wave briefs / Authoring in a wave: the size above is
FINAL, and \`planPath\` is the plan document, never your sidecar.
${singleContextBlock}
Return \`reviewSignals\`: the \`review_signals\` ids you declared in the plan's frontmatter (empty when
none). They select the plan's domain reviewers; the roadmap's own OVERVIEW.md frontmatter
(\`approver\`, \`approval_utterance\`) is the PM's Approve record — read it before writing that none exists.
${MISE_PREP_RULE}
${PM_BRIEF_RULE}
${MID_RUN_DIRECTION_RULE}
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'planning-report'))}`,
    // opus-ruling: G-EM-2026-10-27-R3
    // opus-justified: authoring a plan is the judgment leg; one agent per baton is one item of real work (ALLOWED_PER_ITEM `plan:`).
    { model: 'opus', ...withRole('coordinator:plan-author'),
      label: `plan:${baton.id}`,
      phase: 'Plan',
      effort: 'low',
      schema: PLAN_SCHEMA,
    },
  ))
}

function premiseChecker(baton, planResult, trailDir, withCoverage) {
  // Function-form replacement: a `$` in the CLI path must not be read as a replacement pattern.
  const renderedClassList = PREMISE_CLASS_LIST.split('${ARMING_CHECK_CLI}').join(ARMING_CHECK_CLI)
  const refireBrief = `phase: premise-check

Resolve the load-bearing citations in the plan at ${planResult.planPath} (baton ${baton.id}) against
this tree. Read \`agents/premise-checker.md\` (under the coordinator plugin root) § Plan-blitz wave
passes / Premise-check pass and § Refire carry in full and follow them. You report the CLASS you
checked; you never refuse, never edit, and never report the plan correct, sound or ready.

This brief's version is \`${PREMISE_BRIEF_VERSION}\`.

${CLI_RESOLUTION_RULE}

  (a) Run \`coordinator-invoke plan.premise_scope\` with one JSON argument
      \`{"plan": "${planResult.planPath}", "brief_version": "${PREMISE_BRIEF_VERSION}"}\`.
  (e) On EVERY pass, then run \`coordinator-invoke plan.premise_record\` with one JSON argument
      \`{"plan", "brief_version", "rows", "retired", "citations_skipped"}\`. Return the reply's
      \`rows\` VERBATIM as \`rows\`, plus \`carry: {"firstPass": <scope first_pass>, "carried": <reply
      carried>, "fresh": <reply fresh>}\`.

Cap at 40 citations, in plan order; put the number you left in \`citationsSkipped\`.`
  const coverageBlock = withCoverage ? `

COVERAGE. This dispatch also owes the plan-coverage verdict for ${planResult.planPath}: record the
premise rows first, then follow \`agents/premise-checker.md\` § Plan-coverage lenses.

${ROLE_CONTRACTS['plan-coverage-checker']}

The coverage sidecar is a second sidecar: its path is \`coverage.sidecarPath\`, and the top-level
\`sidecarPath\` stays the premise one provisioned above.
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'plan-coverage-check')).replace('return it verbatim as \`sidecarPath\`', 'return it verbatim as \`coverage.sidecarPath\`')}` : ''
  return trackAgent('planner', agent(
    `${refireBrief}

${renderedClassList}

${PREMISE_CHECK_CONTRACT}

${INSTRUMENT_CAN_REPORT_RED_CONTRACT}

**Also return \`spinePresent\`, and RUN THE CHECKER for it — never answer it by eye:**

${SPINE_CHECK_RULE(planResult.planPath)}

Read the verdict token off its stdout. \`NO-SPINE\` → \`spinePresent: false\`. Any other token
(\`VALID\`, or a shape complaint) → \`spinePresent: true\`: the block IS there and something about it
is wrong, which is a different fact and not yours to report. **If no resolved invocation was
supplied above, or the checker did not run, OMIT \`spinePresent\`**: omission reads as "not
established"; a guessed \`false\` parks a plan that was ready. Quote the token you saw. A \`false\`
is not a finding against the plan's content — it says there is nothing to schedule.
${NO_EXECUTION_RULE}
${MID_RUN_DIRECTION_RULE}
${REPO_ROOT_RULE}
${REVIEW_SIDECAR_RULE(
      sidecarFor(trailDir, baton.id, 'review-premise-check-pointer'),
      'coordinator:premise-checker',
      'review-findings',
    )}${coverageBlock}`,
    { model: 'sonnet', ...withRole('coordinator:premise-checker'),
      label: `premise:${baton.id}`,
      phase: 'Premise check',
      effort: 'low',
      schema: withCoverage ? PRE_REVIEW_SCHEMA : PREMISE_SCHEMA,
    },
  ))
}

const CITATION_CLASSES = [1, 2, 3, 4, 5]

// Per-class coverage: a class never attempted and a class that resolved clean look the same in
// the verdict list; the coverage string tells them apart.
function classCoverage(rows) {
  return CITATION_CLASSES.map((klass) => {
    const inClass = rows.filter((r) => Number(r.questionClass) === klass)
    if (!inClass.length) return `c${klass}:none`
    const unsettled = inClass.filter((r) => r.verdict === 'UNCHECKABLE').length
    return `c${klass}:${inClass.length}${unsettled ? `/${unsettled} unsettled` : ''}`
  }).join(' ')
}


function premiseLines(premise) {
  if (!premise) return '(no premise check ran for this plan — the citation classes are UNCHECKED, not clean)'
  const rows = premise.rows || []
  const flagged = rows.filter((r) => r.verdict === 'UNRESOLVED' || r.verdict === 'CONTRADICTED')
  const unsettled = rows.filter((r) => r.verdict === 'UNCHECKABLE')
  const parts = [
    `${rows.length} citation(s) checked, ${flagged.length} unresolved/contradicted, `
      + `${unsettled.length} unsettled${premise.citationsSkipped ? `, ${premise.citationsSkipped} beyond the cap` : ''}.`,
    ...(premise.carry ? [`carried ${premise.carry.carried}, fresh ${premise.carry.fresh}`] : []),
    `class coverage: ${classCoverage(rows)} — "none" is UNATTEMPTED, never clean`,
    `falsifier arming: ${premise.falsifierVerdict || '(no falsifier named)'}`,
    `sidecar: ${premise.sidecarPath}`,
  ]
  for (const row of flagged.concat(unsettled)) {
    parts.push(`  [class ${row.questionClass}] ${row.verdict}: ${row.citation}${row.evidence ? ` — ${row.evidence}` : ''}`)
  }
  return parts.join('\n')
}


const PREMISE_REVIEWER = 'premise-check'
const PREMISE_FINDING_VERDICTS = ['UNRESOLVED', 'CONTRADICTED']

// The op's key is `premise-check: <VERDICT> <citation[:200]>`, sliced by code point (Python).
function premiseKey(row) {
  return `premise-check: ${row.verdict} ${Array.from(String(row.citation || '')).slice(0, 200).join('')}`
}

// With an honoured reply carrying `blocking`, only the rows the op counted; the op alone decides
// what blocks; without a reply, every flagged row.
function premiseBlockingRows(rows, reply) {
  const flagged = rows.filter((r) => PREMISE_FINDING_VERDICTS.includes(r.verdict))
  if (!reply || !Array.isArray(reply.blocking)) return flagged
  const counted = new Set(reply.blocking)
  return flagged.filter((r) => counted.has(premiseKey(r)))
}

function mergePremiseRows(priorRows, freshRows, retired) {
  const fresh = new Map((freshRows || []).map((r) => [r.citation, r]))
  const gone = new Set(retired || [])
  const merged = []
  const seen = new Set()
  for (const row of priorRows || []) {
    if (gone.has(row.citation)) continue
    seen.add(row.citation)
    merged.push(fresh.has(row.citation) ? fresh.get(row.citation) : row)
  }
  for (const row of freshRows || []) {
    if (!seen.has(row.citation) && !gone.has(row.citation)) {
      seen.add(row.citation)
      merged.push(row)
    }
  }
  return merged
}

// Routes BLOCKED, never PIVOT: coordinator/docs/wiki/coordinator-tripwires/a-blocked-review-is-not-a-pivot.md
function premiseAsReview(baton, premise, reply) {
  if (!premise) return null
  const rows = premise.rows || []
  const findings = premiseBlockingRows(rows, reply)
  // Class-5 rows where no fix is writable from the finding alone: named, never routed
  const unwritable = rows.filter(
    (r) => Number(r.questionClass) === 5 && r.verdict !== 'RESOLVES',
  )
  return {
    batonId: baton.id,
    reviewer: PREMISE_REVIEWER,
    verdict: findings.length ? 'BLOCKED' : 'OK',
    sidecarPath: premise.sidecarPath,
    findingCount: findings.length,
    // Zero citations examined and all-RESOLVES both yield `OK`; the count tells them apart.
    citationsChecked: rows.length,
    blockingCitations: findings.map((r) => `${r.verdict} ${r.citation}`),
    // Non-routing; UNCHECKABLE rows never block (`a-blocked-review-is-not-a-pivot.md`).
    pivotCandidates: unwritable.length
      ? `class-5 rows with no fix writable from the finding alone — PIVOT candidates for a `
        + `reviewer to run the separating test against, not a route this pass took: `
        + unwritable.map((r) => `${r.verdict} ${r.citation}`).join('; ')
      : undefined,
  }
}

const PLAN_COVERAGE_REVIEWER = 'plan-coverage-check'

// Same seam shape as `premiseAsReview`; plan-coverage-checker is report-only.
function planCoverageAsReview(baton, coverage) {
  if (!coverage) return null
  const verdictMap = {
    COMPLETE: 'OK',
    // WARN, not OK: OK would hide a scope mismatch from `deviations`.
    'SCOPE-MISMATCH': 'WARN',
    DEGRADED: 'WARN',
    INCOMPLETE: 'WARN',
    'BLOCKED-SURFACE-TO-PM': 'BLOCKED',
  }
  const findingCount = (coverage.mechanicalFindings || 0) + (coverage.judgmentFindings || 0)
  return {
    batonId: baton.id,
    reviewer: PLAN_COVERAGE_REVIEWER,
    verdict: verdictMap[coverage.verdict] || 'WARN',
    sidecarPath: coverage.sidecarPath,
    findingCount,
    premiseFailure: coverage.verdict === 'BLOCKED-SURFACE-TO-PM'
      ? `plan-coverage-checker: ${coverage.verdict} — mechanical:${coverage.mechanicalFindings || 0} `
        + `judgment:${coverage.judgmentFindings || 0}`
      : undefined,
  }
}

function priorArtPreflight(baton, waveIndex, trailDir) {
  return trackAgent('prior-art-checker', agent(
    `phase: prior-art-preflight

${ROLE_CONTRACTS['prior-art-checker']}

Single-plan mode, wave ${waveIndex}. Cross-reference this baton's sizing intent and exit criterion
against prior art BEFORE the planner writes anything, so a conflict is visible in the planner's own
brief rather than discovered by a reviewer four stages later.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}
Sizing object: ${baton.sizingObject || '(none)'}
Exit criterion: ${baton.exitCriterion || '(none stated on the baton)'}
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'prior-art-check'))}`,
    { model: 'sonnet', ...withRole('coordinator:prior-art-checker'),
      label: `prior-art:${baton.id}`,
      phase: 'Plan',
      effort: 'low',
      schema: PRIOR_ART_SCHEMA,
    },
  ))
}

// Phase 4 — Review

// The readiness op rides on the LAST reviewer of a plan (`host` is null for the rest), so the op
// reads the plan as reviewed.
function readinessParams(planPath, host) {
  return {
    plan: planPath,
    ...(host.coverage ? { coverage: host.coverage } : {}),
    ...(host.premise ? { premise: host.premise } : {}),
    reviews: host.reviews,
  }
}

function readinessStep(host, planPath, reviewer, readyOp, files = {}) {
  if (!host) return ''
  const readinessFile = files.readiness || '<scratch dir>/readiness-params.json'
  const readyOpFile = files.readyOp || '<scratch dir>/ready-op-params.json'
  const readyOpStep = readyOp ? `
READY OP (only after the readiness op above, and only on ITS reply): if the reply's \`verdict\` is
"ready", its \`mechanical_repairs\` is empty and its \`prep_gate.verdict\` is "PREPPED", run, exactly
once: write exactly this JSON to \`${readyOpFile}\` with your write tool (if your role bars it, \`cat > <path> <<'EOF'\` through Bash with the delimiter quoted), then run, with no inline JSON on the command line:

    ${JSON.stringify({ ...readyOp.params, plan_path: planPath })}

    coordinator-invoke ${readyOp.op} --params-file ${readyOpFile}

and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
one-line failure in \`readyOpError\`. In any other case run nothing and return neither field.
` : ''
  const params = JSON.stringify(readinessParams(planPath, host))
  return `
READINESS VERDICT (the last thing you do, after your ledger verifies): you are the last reviewer on
this plan, so the readiness op rides on your run. If your verdict is PIVOT (or a REJECTED you
resolve to PIVOT), skip this step entirely. Otherwise write this JSON to \`${readinessFile}\` with your
write tool (if your role bars it, \`cat > <path> <<'EOF'\` through Bash with the delimiter quoted), with your own entry appended as the LAST element of \`reviews\`, spelled
{"reviewer":"${reviewer}","verdict":"<your verdict exactly as you return it>","ledger":"<your sidecarPath>"},
and run, with no inline JSON on the command line:

    ${params}

    coordinator-invoke plan.readiness_verdict --params-file ${readinessFile}

Run the op exactly as written, with no pipe, head, tail or truncation of any kind, and return its reply JSON whole.
Return the op's reply object verbatim as \`readinessVerdict\`, and the \`reviews\` array you actually
passed (yours included) as \`readinessReviews\`. Do not edit the plan to change what the op says, do
not adjust a verdict or a count. If the op fails (non-zero exit, no JSON reply, or an \`error\`
envelope), run the identical command exactly once more. If that fails too, omit \`readinessVerdict\`,
put that run's own output VERBATIM (stderr, else stdout, prefixed \`exit <n>: \`, never summarised) in
\`readinessError\`, and set \`readinessAttempts\` to the number of runs (2) — that is a correct result.
A reply that comes back is never retried.
${readyOpStep}`
}

const OP_VERDICTS = ['ready', 'pulled', 'judgment']
const OP_PULL_CLASSES = ['none', 'mechanical', 'substantive']

// Honoured only when the host passed the op exactly the reviews this script resolved, did not
// pivot, and the reply parses; anything else reads as no reply.
function honouredReadiness(resolved, priorForOp) {
  if (!resolved || resolved.pivot || resolved.readinessError) return null
  const reply = resolved.readinessVerdict
  if (!reply || !OP_VERDICTS.includes(reply.verdict) || !OP_PULL_CLASSES.includes(reply.pull_class)) return null
  if (!Array.isArray(reply.mechanical_repairs) || !reply.prep_gate) return null
  if ((reply.mechanical_repairs.length > 0) !== (reply.pull_class === 'mechanical')) return null
  if (reply.verdict === 'ready' && (reply.mechanical_repairs.length > 0 || reply.prep_gate.verdict !== 'PREPPED')) return null
  const passed = resolved.readinessReviews
  const expected = [...priorForOp, { reviewer: resolved.reviewer, verdict: resolved.raw }]
  if (!Array.isArray(passed) || passed.length !== expected.length) return null
  const same = expected.every((e, i) => passed[i]
    && passed[i].reviewer === e.reviewer
    && String(passed[i].verdict || '').toUpperCase() === String(e.verdict || '').toUpperCase())
  if (!same) return null
  // A malformed `blocking` reads as absent, never as a refusal of an otherwise coherent reply.
  const { blocking, ...rest } = reply
  return Array.isArray(blocking) && blocking.every((k) => typeof k === 'string') ? reply : rest
}

// `ledger`: the op reads a BLOCKED as clear only when that ledger is stamped and verified.
const opReviewList = (entries) => entries.filter(Boolean).map((r) => ({
  reviewer: r.reviewer,
  verdict: r.verdict,
  ...(typeof r.sidecarPath === 'string' && r.sidecarPath ? { ledger: r.sidecarPath } : {}),
}))
// Rows ride as `premise.rows`, never as a `premise-check` reviews entry (the op refuses that).
const premiseForOp = (p) => (p
  ? { rows: (p.rows || []).map((r) => ({
    verdict: r.verdict,
    citation: r.citation,
    ...(r.questionClass !== undefined ? { questionClass: r.questionClass } : {}),
    ...(r.evidence ? { evidence: r.evidence } : {}),
    ...(typeof r.baseline_ref === 'string' && r.baseline_ref ? { baseline_ref: r.baseline_ref } : {}),
  })) }
  : null)
const coverageForOp = (c) => (c
  ? { verdict: c.verdict, mechanicalFindings: c.mechanicalFindings || 0, judgmentFindings: c.judgmentFindings || 0 }
  : null)

// The self-applying reviewer's audit trail: a reviewer that edited the plan owes a sidecar and one
// disposition per finding. Returns the refusal text, or null when the trail holds.
function selfApplyViolation(result) {
  if (!result || result.planEdited !== true) return null
  const sidecar = typeof result.sidecarPath === 'string' ? result.sidecarPath.trim() : ''
  const rows = Array.isArray(result.dispositions) ? result.dispositions : []
  if (sidecar && rows.length && rows.length >= (result.findingCount || 0)) return null
  return `${result.reviewer} edited the plan but wrote no findings list (sidecar ${sidecar || 'none'}, ${rows.length} disposition(s) for ${result.findingCount || 0} finding(s))`
}

// `entry` is set only by the parallel wave (concurrent, independent members); its `role` tags every finding.
function reviewerAgent(baton, decision, planResult, reviewer, trailDir, premise, priorReviewers, hostReadiness, priorArt, chattyBrief, entry) {
  const priorArtBlock = priorArt
    ? `\nPrior-art pre-flight over this baton's sizing intent: ${priorArt.verdict}, ${priorArt.conflicts || 0} conflict(s), sidecar ${priorArt.sidecarPath}. The planner may not have seen it: open it, and treat a CONFLICT bucket as a finding against the plan.\n`
    : ''
  const parallelMember = Boolean(entry)
  const roleTag = entry && entry.role
  const sequencing = parallelMember
    ? `\nYou are one reviewer in a parallel wave: you work independently and do not wait on or read any
other reviewer's findings or sidecar. Peers edit this plan concurrently; re-read the span before each
Edit, and when a \`before\` no longer matches it is a peer's edit, so re-derive the fix against the
new text.${roleTag
    ? `\nYou are the \`${roleTag}\` pass: a second, independent read of this plan on the lead's brief, and the
lead's output is withheld from you. Open every finding in your sidecar with \`[${roleTag}]\` and put
\`"role": "${roleTag}"\` on every row of your ledger.` : ''}\n`
    : chattyBrief
    ? `\nSame plan, but this baton's reviewers run CONCURRENTLY: peers are editing it while you review.
Apply by exact-text Edit. Claim a region by mail before editing it and never edit a region a peer
holds (the CHATTY RUN brief closing this prompt carries the full rule). Mail ground shifts before
applying them.\n`
    : priorReviewers && priorReviewers.length
    ? `\nSame plan, so this baton's reviewers run SEQUENTIALLY, never in parallel — you are not the
first. ${priorReviewers.map((r) => `${r.reviewer} ran before you, returned ${r.verdict}, and its
findings are already applied and verified in the plan on disk.`).join(' ')} Read their sidecar(s)
before you start: a finding you would raise that they already applied is settled, not yours to
re-log, and an edit of theirs that removed text a later finding of YOURS needs is a conflict to
name in your own findings rather than silently work around.\n`
    : `\nYou are the first (or only) reviewer to run on this plan in this wave.\n`

  const applyBlock = `**APPLY YOUR OWN FINDINGS** to ${planResult.planPath} itself (§ Plan-blitz review wave / Applying your own findings). Ledger row, in your OWN sidecar:

    {"id": "finding-<N>", "file": "<repo-relative/forward-slash>", "before": "<exact text replaced, or empty for an insertion>", "after": "<exact text now present, or empty for a deletion>"${roleTag ? `, "role": "${roleTag}"` : ''}}

Also write a \`## Dispositions\` heading in that sidecar: one line per finding, \`applied\` or
\`declined: <reason>\`, beside the edit diff its ledger row carries. Return \`planEdited\` (true when
you edited the plan at all) and \`dispositions\` ({id, disposition, reason}) too. A plan you edited
with no findings list written fails the stage.

Then run:

${CLI_RESOLUTION_RULE}

    review-findings-ledger verify --sidecar <your sidecar path>
`
  const roleSuffix = roleTag ? `-${roleTag}` : ''
  return trackAgent('reviewer', agent(
    `${ROLE_CONTRACTS.reviewer}

Review the plan at ${planResult.planPath} for baton ${baton.id} ("${baton.title}").

Finalised size: ${decision.tshirt}, route: ${decision.route}.
Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}
${sequencing}${priorArtBlock}
Premise check, run against the tree before you:
${premiseLines(premise)}

Read \`agents/plan-reviewer.md\` (under the coordinator plugin root) § Plan-blitz review wave in full
and follow it: how to consume the premise report above, the APPROVED / BLOCKED / PIVOT routes, and how
your findings are applied. Return APPROVED when every finding is applied and verified; return BLOCKED
only for what you cannot fix, with \`heldBy\` naming who holds the answer (the APM or a domain reviewer,
never the EM).

${applyBlock}${readinessStep(hostReadiness, planResult.planPath, reviewer, READY_OP, paramsFilesFor(trailDir, baton.id))}${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, `review-${reviewer}-pointer`), reviewer)}${chattyBrief || ''}`,
    { model: reviewModel(reviewer), ...withRole(reviewer),
      label: `review:${baton.id}:${reviewer}${roleSuffix}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    },
  ))
}

// Chatty review wave: the template travels in `chattyReview`; `{BATON}` scopes one baton's roster,
// mail and nonces, `{PEERS}` lists a member's peers. `fillBaton` comes from the shared block.

// `{BATON}` is `<baton id>-<pass tag>`, never the bare id: a baton reviewed twice must not put one
// pass's mail or nonces in the other's roster.
function chattyPassId(batonId) {
  chattyPassId.counts = chattyPassId.counts || {}
  chattyPassId.counts[batonId] = (chattyPassId.counts[batonId] || 0) + 1
  return `${batonId}-r${chattyPassId.counts[batonId]}`
}

function fillPeers(brief, slotTypes, peersSlot = '{PEERS}') {
  return brief.split(peersSlot).join(slotTypes.map(([slot, type]) => `${slot} = ${type}`).join('\n'))
}

// `wave` is true only when chatty review is armed and every reviewer has a roster review slot;
function chattyWavePick(reviewerList) {
  if (parsedArgs.chatty !== true || !parsedArgs.chattyReview) return { wave: false, note: null }
  const roster = parsedArgs.chattyReview.roster
  const slots = ((roster && roster.members) || []).map((m) => m.role).filter((r) => /^review-\d+$/.test(r))
  if (reviewerList.length <= slots.length) return { wave: true, note: null }
  return {
    wave: false,
    note: `chatty review armed but ${reviewerList.length} reviewers exceed the ${slots.length} roster review slot(s): fell back to the sequential loop`,
  }
}

const SURVEY_SCHEMA = {
  type: 'object',
  required: ['continuations', 'tldr'],
  properties: {
    continuations: {
      type: 'array',
      items: { type: 'object', required: ['role'], properties: { role: { type: 'string' }, agent_id: { type: 'string' } } },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const READINESS_HOST_SCHEMA = {
  type: 'object',
  properties: Object.fromEntries(
    ['readinessVerdict', 'readinessReviews', 'readinessError', 'readinessAttempts', 'readyOpReply', 'readyOpError']
      .map((k) => [k, REVIEW_SCHEMA.properties[k]]),
  ),
}
READINESS_HOST_SCHEMA.properties.tldr = RETURN_TLDR_SCHEMA
READINESS_HOST_SCHEMA.required = ['tldr']

// An engine-op result the caller supplied in `args.opResults.<key>`: keyed by baton id, or the bare
// result when the fire carries exactly one baton and `leafKey` shows the value is a result.
function suppliedOp(key, batonId, leafKey) {
  const all = parsedArgs.opResults
  const v = all && typeof all === 'object' ? all[key] : null
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  if (v[batonId] && typeof v[batonId] === 'object') return v[batonId]
  return (parsedArgs.batons || []).length === 1 && v[leafKey] !== undefined ? v : null
}

async function runReadinessHost({ baton, plan, reviews, reviewers, premise, coverage }) {
  const last = reviews[reviews.length - 1]
  if (!last || last.reviewer !== reviewers[reviewers.length - 1] || reviews.some((r) => r.pivot)) return null
  const hostInput = { reviews: opReviewList(reviews.slice(0, -1)), premise: premiseForOp(premise), coverage: coverageForOp(coverage) }
  const hostParams = readinessParams(plan.planPath, hostInput)
  // Remove this fallback once plan.readiness_verdict is published and every caller supplies opResults.readiness.
  const supplied = suppliedOp('readiness', baton.id, 'verdict')
  const readyOpOwed = Boolean(READY_OP) && supplied && supplied.verdict === 'ready'
  if (supplied && !readyOpOwed) {
    last.readinessVerdict = supplied
    last.readinessReviews = [...hostInput.reviews, { reviewer: last.reviewer, verdict: last.raw, ledger: last.sidecarPath }]
    return hostParams
  }
  const hosted = await trackAgent('readiness-host', agent(
    `phase: readiness

The reviewers of baton ${baton.id} ("${baton.title}") have all returned and their ledgers are verified.
You review nothing and edit nothing: you only run the readiness step below for them. Where it says "you"
or "your", read the last reviewer, ${last.reviewer}: its verdict is ${last.raw}, its ledger ${last.sidecarPath},
and its entry is {"reviewer":"${last.reviewer}","verdict":"${last.raw}","ledger":"${last.sidecarPath}"}. Return only the
readiness fields.
${readinessStep(hostInput, plan.planPath, last.reviewer, READY_OP, paramsFilesFor(trailDir, baton.id))}${REPO_ROOT_RULE}`,
    { model: 'sonnet', label: `readiness-host:${baton.id}`, phase: 'Review', schema: READINESS_HOST_SCHEMA },
  ))
  if (hosted) {
    for (const key of Object.keys(READINESS_HOST_SCHEMA.properties)) {
      if (key !== 'tldr' && hosted[key] !== undefined) last[key] = hosted[key]
    }
  }
  return hostParams
}

// Returns the resolved reviews in reviewer order, or null when the overseer returned nothing (no
// roster member reported), so the caller falls back to the parallel wave.
async function chattyReviewWave({ baton, decision, plan, trailDir, premise, priorArt, coverage, reviewers }) {
  const template = parsedArgs.chattyReview
  const passId = chattyPassId(baton.id)
  const cfg = fillBaton(template, passId, template.batonSlot || '{BATON}')
  const peersSlot = cfg.peersSlot || '{PEERS}'
  const slotOf = (i) => `review-${i + 1}`
  const slotTypes = reviewers.map((r, i) => [slotOf(i), r])
  const phase = { phase: 'Review' }

  const overseer = await trackAgent('chatty-overseer', agent(
    `${cfg.overseerPrompt}${REPO_ROOT_RULE}`,
    { model: 'sonnet', label: `chatty-overseer:${baton.id}`, ...phase },
  ))
  if (!overseer) {
    agentIncidents.push({ role: `chatty-overseer:${baton.id}`, kind: 'wave-unavailable', detail: 'the overseer returned nothing; the reviewers run sequentially' })
    return null
  }

  const settled = await Promise.all(reviewers.map(async (member, i) => {
    const slot = slotOf(i)
    const brief = fillPeers(cfg.memberBriefs[slot], slotTypes.filter(([s]) => s !== slot), peersSlot)
    const result = await reviewerAgent(baton, decision, plan, member, trailDir, premise, null, null, priorArt, brief)
    if (result) checkSidecarPath(baton.id, `review-${member}`, result.sidecarPath)
    return result ? resolveVerdict({ ...result, reviewer: member }) : null
  }))

  const survey = await trackAgent('chatty-survey', agent(
    `${cfg.surveyPrompt}${REPO_ROOT_RULE}`,
    { model: 'sonnet', label: `chatty-survey:${baton.id}`, ...phase, schema: SURVEY_SCHEMA },
  ))
  const owed = new Set(((survey && survey.continuations) || []).map((c) => c.role))
  const resolved = await Promise.all(reviewers.map(async (reviewer, i) => {
    const prior = settled[i]
    const slot = slotOf(i)
    if (!prior || !owed.has(slot)) return prior
    const brief = fillBaton(cfg.continuationBriefs[slot], `${passId}-${slot}-cont`, cfg.nonceSlot || '{NONCE}')
    const result = await trackAgent('reviewer', agent(
      `${ROLE_CONTRACTS.reviewer}

You continue the review of the plan at ${plan.planPath} for baton ${baton.id} ("${baton.title}"): the
mail your predecessor left unread is yours to act on. Keep its findings ledger ${prior.sidecarPath}, apply
what the mail requires by exact-text Edit, verify the ledger with \`review-findings-ledger verify\`, and
return the same structured result as a reviewer, with sidecarPath ${prior.sidecarPath}.
${CLI_RESOLUTION_RULE}${REPO_ROOT_RULE}${brief}`,
      { model: reviewModel(reviewer), ...withRole(reviewer), label: `review-continuation:${baton.id}:${slot}`, ...phase, schema: REVIEW_SCHEMA },
    ))
    if (!result) return prior
    checkSidecarPath(baton.id, `review-${reviewer}`, result.sidecarPath)
    return resolveVerdict({ ...result, reviewer })
  }))
  const reviews = resolved.filter(Boolean)

  const hostParams = await runReadinessHost({ baton, plan, reviews, reviewers, premise, coverage })

  await trackAgent('chatty-summary', agent(
    `${cfg.summaryPrompt}${REPO_ROOT_RULE}`,
    { model: 'sonnet', label: `chatty-summary:${baton.id}`, ...phase },
  ))
  return { reviews, hostParams }
}

// Parallel review wave: the plan_review block's reviewers in one wave, each applying its own findings.
const PARALLEL_REVIEW = parsedArgs.parallelReview && typeof parsedArgs.parallelReview === 'object'
  ? parsedArgs.parallelReview
  : null

let AVAILABLE_PLUGINS = Array.isArray(parsedArgs.availablePlugins)
  ? new Set(parsedArgs.availablePlugins.map((p) => String(p).trim()).filter(Boolean))
  : null
const SUPPLIED_CONTRIBUTIONS = Array.isArray(parsedArgs.contributedSignals)
registerContributedSignals(parsedArgs.contributedSignals)
const CONTRIBUTED_IDS = new Set(SUPPLIED_CONTRIBUTIONS ? parsedArgs.contributedSignals.map((s) => s && s.id).filter(Boolean) : [])

// Intake rides the plan-prep-gate host: its reply carries `plugin_review_signals.py attach` output
// (availablePlugins, signals, attached). Arg-supplied availablePlugins skips the scan; with no supplied
// contributedSignals either, no contributed signal can fire and the host runs no attach.
const PLUGINS_FROM_ARG = AVAILABLE_PLUGINS !== null
const PLUGIN_ATTACH_OWED = !PLUGINS_FROM_ARG || CONTRIBUTED_IDS.size > 0

const PLUGIN_SIGNALS_CLI_RULE = `
\`plugin_review_signals.py\` lives at lib/plugin_review_signals.py under the coordinator plugin root (the
directory holding agents/plan-reviewer.md; \`$CLAUDE_PLUGIN_ROOT\` names it). Run it with python3 (python on
Windows); its stdout is one JSON object.`

// planPath -> the last plan-prep-gate host reply, set by planPrepGateHost.
const PLAN_HOST_REPLIES = new Map()

// The plan's declared `review_signals` plus the contributed signals attached to its writes, read from
// the plan's last plan-prep-gate host reply. A reply without the plugin fields (a supplied planPrepGate
// reply, or a host that skipped the call) records `plugins-unreadable` and keeps the declared signals.
function signalsFor(plan) {
  const declared = Array.isArray(plan.reviewSignals) ? plan.reviewSignals : []
  if (!PLUGIN_ATTACH_OWED) return declared
  const reply = PLAN_HOST_REPLIES.get(plan.planPath)
  const readable = reply && Array.isArray(reply.attached) && (PLUGINS_FROM_ARG || Array.isArray(reply.availablePlugins))
  if (!readable) {
    agentIncidents.push({
      role: 'plan-prep-gate', kind: 'plugins-unreadable',
      detail: 'the plan-prep-gate host reply carried no plugin scan; plugin-contributed signals are absent and non-coordinator reviewers degrade to the default',
    })
    return declared
  }
  if (!AVAILABLE_PLUGINS) {
    AVAILABLE_PLUGINS = new Set(reply.availablePlugins.map((p) => String(p).trim()).filter(Boolean))
    for (const id of registerContributedSignals(reply.signals)) CONTRIBUTED_IDS.add(id)
  }
  const attached = reply.attached.filter((id) => CONTRIBUTED_IDS.has(id))
  return [...new Set([...declared, ...attached])]
}

const ROSTER_BLOCK_SCHEMA = {
  type: 'object',
  required: ['tiers', 'signal_reviewers', 'tldr'],
  properties: {
    tiers: { type: 'object' },
    signal_reviewers: { type: 'object' },
    revise: { type: 'object' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const LEDGER_VERIFY_SCHEMA = {
  type: 'object',
  required: ['entries', 'tldr'],
  properties: {
    entries: {
      type: 'array',
      items: {
        type: 'object',
        required: ['sidecarPath', 'unapplied'],
        properties: { sidecarPath: { type: 'string' }, unapplied: { type: 'array', items: { type: 'string' } } },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const LEDGER_REAPPLY_SCHEMA = {
  type: 'object',
  required: ['unapplied', 'tldr'],
  properties: {
    unapplied: { type: 'array', items: { type: 'string' } },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// The `plan_review` block is read by one agent (no fs primitive here).
async function readRosterBlock(read) {
  let state = 'unparseable'
  for (let attempt = 0; attempt < 2; attempt++) {
    const got = await read()
    // Same predicate as buildRoster's `blockNamesReviewer` (tests evaluate buildRoster alone).
    if (got && got.tiers && typeof got.tiers === 'object'
      && Object.values(got.tiers).some((s) => s && Array.isArray(s.reviewers) && s.reviewers.length > 0)) return { block: got, state: 'ok' }
    state = got ? 'empty' : 'unparseable'
  }
  return { block: null, state }
}

let rosterPromise = null
function reviewRoster() {
  if (!rosterPromise) {
    rosterPromise = (async () => {
      // A supplied `args.plan_review` dispatches no agent; an invalid one takes the degrade path below.
      const supplied = parsedArgs.plan_review && typeof parsedArgs.plan_review === 'object' ? parsedArgs.plan_review : null
      const { block, state } = await readRosterBlock(supplied ? async () => supplied : () => trackAgent('roster-reader', agent(
          `Read the file coordinator/contract/review-roster-fragment.json and return its \`plan_review\` object
exactly as written: \`tiers\`, \`signal_reviewers\` and \`revise\` copied verbatim, every entry's keys
kept (agentType, model, role, brief). You change nothing and judge nothing.${REPO_ROOT_RULE}`,
          {
            model: 'sonnet',
            label: 'roster-reader',
            effort: 'low',
            phase: 'Review',
            schema: ROSTER_BLOCK_SCHEMA,
          },
        )))
      if (!block) {
        const what = state === 'empty' ? 'the plan_review block named no reviewer' : 'the plan_review block was unparseable'
        agentIncidents.push({
          role: 'roster-reader', kind: 'roster-unreadable',
          detail: PARALLEL_REVIEW ? `${what}; tiers and models come from the parallelReview arg alone` : `${what} and no parallelReview arg was passed`,
        })
      }
      return buildRoster(block, PARALLEL_REVIEW)
    })()
  }
  return rosterPromise
}

function entryTag(entry) {
  return entry.role ? `${entry.agentType}-${entry.role}` : entry.agentType
}

// Concurrent exact-text Edits on one plan file can lose an update, so a host re-verifies every
// member ledger after the wave; `unapplied` names the rows whose `after` text is absent.
function verifyWaveLedgers({ baton, plan, trailDir, reviews }) {
  const sidecars = reviews.filter((r) => r.sidecarPath).map((r) => `  - ${r.sidecarPath}`).join('\n')
  return trackAgent('ledger-verify', agent(
    `The reviewers of baton ${baton.id} ("${baton.title}") edited ${plan.planPath} concurrently and have returned.
You review nothing and edit nothing. Run, for EACH findings-ledger sidecar below,

    review-findings-ledger verify --sidecar <sidecar path>

${sidecars}

${CLI_RESOLUTION_RULE}
Return one entry per sidecar: its path as \`sidecarPath\`, and in \`unapplied\` the id of every ledger row the
verify reports as not landed (its \`after\` text is absent from the plan). Report what the verify says;
never judge a row yourself and never count an unverified row as applied.
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'ledger-verify'))}`,
    { model: 'sonnet', label: `ledger-verify:${baton.id}`, phase: 'Review', schema: LEDGER_VERIFY_SCHEMA },
  ))
}

function reapplyOwedRows({ baton, plan, entry, review, unapplied }) {
  return trackAgent('reviewer', agent(
    `${ROLE_CONTRACTS.reviewer}

A concurrent peer edit lost ${unapplied.length} of your applied findings on ${plan.planPath} for baton ${baton.id}:
ledger rows ${unapplied.join(', ')} in ${review.sidecarPath}. Re-read each row's span in the plan as it stands
now, re-derive the fix against the current text, apply it by exact-text Edit, and run

    review-findings-ledger verify --sidecar ${review.sidecarPath}

Return in \`unapplied\` the ids of any row that still did not land after that (empty when all landed).
${CLI_RESOLUTION_RULE}${REPO_ROOT_RULE}`,
    { model: entry.model, ...withRole(entry.agentType), label: `reapply:${baton.id}:${entryTag(entry)}`, phase: 'Review', schema: LEDGER_REAPPLY_SCHEMA },
  ))
}

// Concurrent members each apply their own findings; a post-wave ledger verify re-dispatches any
// owed row to its reviewer, then the readiness host runs.
async function parallelReviewWave({ baton, decision, plan, trailDir, premise, priorArt, coverage, entries }) {
  const entryOf = new Map()
  const settled = await Promise.all(entries.map(async (entry) => {
    const result = await reviewerAgent(baton, decision, plan, entry.agentType, trailDir, premise, null, null, priorArt, undefined, entry)
    if (result) checkSidecarPath(baton.id, `review-${entryTag(entry)}`, result.sidecarPath)
    if (!result) return null
    const review = resolveVerdict({ ...result, reviewer: entry.agentType, ...(entry.role ? { role: entry.role } : {}) })
    entryOf.set(review, entry)
    return review
  }))
  const reviews = settled.filter(Boolean)
  if (!reviews.length || reviews.some((r) => r.pivot)) return { reviews, hostParams: null, verified: null }
  const verified = await verifyWaveLedgers({ baton, plan, trailDir, reviews })
  if (!verified) {
    agentIncidents.push({ role: `ledger-verify:${baton.id}`, kind: 'wave-unavailable', detail: 'the post-wave ledger verify returned nothing; each member\'s own verify stands' })
  } else {
    await Promise.all(reviews.map(async (review) => {
      const owed = (verified.entries || []).find((e) => e.sidecarPath === review.sidecarPath)
      const unapplied = owed && Array.isArray(owed.unapplied) ? owed.unapplied : []
      if (!unapplied.length) return
      const again = await reapplyOwedRows({ baton, plan, entry: entryOf.get(review), review, unapplied })
      const still = again && Array.isArray(again.unapplied) ? again.unapplied : unapplied
      if (!still.length) return
      // Never APPROVED: WARN keeps the uncleared rows in the judgment resolver's remit.
      review.verdict = 'WARN'
      review.raw = 'WARN'
      review.unappliedRows = still
    }))
  }
  const hostParams = await runReadinessHost({ baton, plan, reviews, reviewers: entries.map((e) => e.agentType), premise, coverage })
  return { reviews, hostParams, verified }
}

// A wave index is not a fire identity: several fires drain one wave under the same `waveIndex`,
// so the fire id is a hash of the baton ids it carries.
const fireIdFor = (ids) => {
  const key = ids.map((id) => String(id)).sort().join('\u0000')
  let h = 0x811c9dc5
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
}

const waveSlot = `wave-${parsedArgs.waveIndex}-${fireIdFor((parsedArgs.batons || []).map((b) => b && b.id))}`

function capString(value, max) {
  if (value === null || value === undefined) return null
  const text = String(value)
  return text.length > max ? text.slice(0, max) : text
}

function planDigest(input) {
  const reviews = Array.isArray(input.reviews) ? input.reviews : []
  const errored = input.verdict === 'errored'
  // The digest enum has no `errored`; the error rides on decision_required.
  const outcome = !errored && ['ready', 'pulled', 'replan', 'surfaced'].includes(input.verdict)
    ? input.verdict
    : 'surfaced'

  // A PIVOT/BLOCKED reviewer or a surfaced baton is a decision handed to the wake reader.
  const decisionSources = []
  if (input.surfacedQuestion) {
    decisionSources.push({
      item: input.surfacedQuestion,
      anchor: input.sizingObject || input.planPath || input.batonId || '(no anchor)',
    })
  }
  for (const r of reviews) {
    if (r && (r.verdict === 'PIVOT' || r.verdict === 'BLOCKED')) {
      decisionSources.push({
        item: Array.isArray(r.blockingCitations) && r.blockingCitations.length
          ? `premise-check BLOCKED on: ${r.blockingCitations.join('; ')}`
          : r.premiseFailure || `${r.reviewer}: ${r.verdict}`,
        anchor: r.sidecarPath || input.planPath || input.batonId || '(no anchor)',
      })
    }
  }
  const decisions = decisionSources.slice(0, 5).map((d) => ({
    item: capString(d.item, 200),
    anchor: capString(d.anchor, 300),
  }))

  // Not pivot/block reviews: those are already decisions above (no double-count).
  const emSources = reviews.filter(
    (r) => r && r.alternativesConsidered && r.verdict !== 'PIVOT' && r.verdict !== 'BLOCKED',
  )
  const overflow = Math.max(0, emSources.length - 10)
  const em_may_think_differently = emSources.slice(0, 10).map((r) => ({
    line: capString(`${r.reviewer}: ${r.alternativesConsidered}`, 200),
    anchor: capString(r.sidecarPath || input.planPath || input.batonId || '(no anchor)', 300),
  }))

  const deviations = reviews
    .filter((r) => r && r.verdict === 'WARN')
    .slice(0, 10)
    .map((r) => ({
      line: capString(`${r.reviewer}: ${r.findingCount || 0} finding(s)`, 200),
      anchor: capString(r.sidecarPath || input.planPath || input.batonId || '(no anchor)', 300),
    }))

  const counts = {
    reviewers: reviews.length,
    findings_applied: reviews.reduce((n, r) => n + ((r && r.findingCount) || 0), 0),
    escalations: decisions.length,
    preflight_findings: (input.premiseCheckVerdict && input.premiseCheckVerdict.findingCount) || 0,
  }

  const usedFallback =
    input.assembledByFallback === true ||
    reviews.some((r) => r && r.assembled_by === 'code-fallback') ||
    (input.premiseCheckVerdict && input.premiseCheckVerdict.assembled_by === 'code-fallback')

  return {
    schema: 'doe-wake-digest',
    version: 1,
    kind: 'plan',
    plan: {
      path: capString(input.planPath, 300),
      deliverable_id: capString(input.deliverableId, 200),
    },
    outcome,
    // A plan digest never claims the criterion was RUN.
    criterion: {
      status: 'not_run',
      observation: capString(input.exitCriterionStatement, 300),
      sidecar: capString(
        (input.premiseCheckVerdict && input.premiseCheckVerdict.sidecarPath) || null,
        300,
      ),
    },
    // The schema's one scalar slot for `decisions`: surfaced question, else the first decision.
    decision_required: capString(
      (errored ? `plan.readiness_verdict errored: ${input.opError || '(no error text)'}` : null)
      || input.surfacedQuestion || (decisions.length ? decisions[0].item : null) || null,
      300,
    ),
    em_may_think_differently,
    overflow,
    deviations,
    counts,
    assembled_by: usedFallback ? 'fallback' : 'code',
    next_action: outcome === 'ready'
      ? {
        kind: 'execute',
        // Not a vehicle: a chained fire's driver reads only params.plan_path.
        op: 'execute-plan',
        params: {
          plan_path: input.planPath || null,
          sizing_object: input.sizingObject || null,
          deliverable_id: input.deliverableId || null,
        },
      }
      : { kind: 'none', op: null, params: null },
  }
}

// Wave body
const waveIndex = parsedArgs.waveIndex
const trailDir = parsedArgs.trailDir
const batons = parsedArgs.batons || []

const MODE = typeof parsedArgs.mode === 'string' && parsedArgs.mode.trim() ? parsedArgs.mode.trim() : 'wave'
if (!['wave', 'single', 'repair'].includes(MODE)) {
  return {
    waveIndex,
    trailDir,
    ready: [],
    pulled: [],
    replan: [],
    surfacedToPm: [],
    refused: [{ batonId: null, reason: `mode "${MODE}" is not one of wave | single | repair` }],
  }
}
const SINGLE_MODE = MODE === 'single'

// `single` needs exactly one sized baton with a sizing-object (the `emit-wave-fire --from-sizing`
if (SINGLE_MODE) {
  const eligible = batons.filter(
    (b) => b && b.sized === true && b.sizingObject && b.tshirt && b.route,
  )
  if (batons.length !== 1 || eligible.length !== 1) {
    return {
      waveIndex,
      trailDir,
      ready: [],
      pulled: [],
      replan: [],
      surfacedToPm: [],
      refused: (batons.length ? batons : [null]).map((b) => ({
        batonId: (b && b.id) || null,
        reason: `mode "single" requires exactly one baton, sized: true, and carrying sizingObject, `
          + `tshirt and route — this fire carried ${batons.length} baton(s), ${eligible.length} eligible`,
      })),
    }
  }
}
// Stands in for `gateReportPath` in single mode, which has no gate report.
const SINGLE_SIZING_PATH = SINGLE_MODE ? batons[0].sizingObject : null
const GATE_REPORT_LABEL = SINGLE_MODE
  ? `${SINGLE_SIZING_PATH} (single-plan mode — no gate report; this IS the resolving record)`
  : parsedArgs.gateReportPath

// Refused before the empty-wave check: a missing `repoRoot` violates the contract either way.
if (!REPO_ROOT) {
  return {
    waveIndex,
    ready: [],
    pulled: [],
    replan: [],
    surfacedToPm: [],
    trailDir,
    refused: batons.map((b) => ({
      batonId: (b && b.id) || null,
      reason: 'no repoRoot supplied — every brief in this wave would resolve its repo-relative paths against the dispatching shell\'s working directory, which is not necessarily this repo',
    })),
  }
}

// Refused, not warned: without a resolver every review runs but `review-findings-ledger` refuses
// every unverifiable sidecar after the fact.
if (!PROVISION_SIDECAR_CLI) {
  return {
    waveIndex,
    ready: [],
    pulled: [],
    replan: [],
    surfacedToPm: [],
    trailDir,
    refused: batons.map((b) => ({
      batonId: (b && b.id) || null,
      reason: 'no provisionSidecarCli supplied — refusing rather than briefing the premise check and every reviewer to invent the machinery root their findings sidecar is provisioned under, where the disposition op refuses every one of them for the missing `subagent-share` path segment',
    })),
  }
}

if (batons.length === 0) {
  // A real state, not a failure: the wave's batons were claimed or planned between gate read and fire.
  return { waveIndex, ready: [], pulled: [], replan: [], surfacedToPm: [], trailDir, empty: true }
}

// Phase 1 — scouts, one per unsized baton (a sized one has a decision; a second number competes).
const unsized = batons.filter((b) => !b.sized)
const scoutResults = await parallel(
  unsized.map((baton) => async () => {
    const r = await sizingScout(baton, waveIndex, trailDir)
    return r ? { ...r, batonId: baton.id } : r
  }),
)
const sizings = scoutResults.filter(Boolean)

// Phase 2 — ONE EM pass over the whole wave: its useful judgment is comparative across batons.
const sizingLines = batons
  .map((b) => {
    const found = sizings.find((s) => s.batonId === b.id)
    if (!found) {
      return `  - ${b.id} "${b.title}" [${b.path}] — already sized upstream; read its sizing-object`
    }
    return `  - ${b.id} "${b.title}" [${b.path}] — scout says ${found.verdict}
      counts: ${JSON.stringify(found.counts || {})}
      scout sidecar (READ it for the evidence, touchpoints, unknown mechanisms, prior art and cross-team dependency): ${found.sidecarPath}`
  })
  .join('\n')

const ALL_ACCEPTED = batons.length > 0
  && batons.every((b) => b && b.sized === true && b.sizingObject && b.tshirt && b.route)
const dispatchRoster = SINGLE_MODE || ALL_ACCEPTED ? await reviewRoster() : null
const dispatch = SINGLE_MODE || ALL_ACCEPTED
  ? {
      decisions: batons.map((b) => ({
        batonId: b.id,
        tshirt: b.tshirt,
        route: b.route,
        rationale:
          'accepted sizing: tshirt and route are the accepted sizing object\'s own values, not '
          + 're-interrogated by a size-review blitz-em (that phase is gated off).',
        sizingObject: b.sizingObject,
        reviewers: dispatchRoster ? ladderRow(b.tshirt, dispatchRoster).map((e) => e.agentType) : [],
      })),
    }
  : await trackAgent('dispatch', agent(
  `phase: size-review

${ROLE_CONTRACTS['blitz-em']}

You are the blitz-em for plan-blitz wave ${waveIndex}. Interrogate and finalise the sizing for
every baton below, then emit the dispatch spec the planning phase will read.

The gate report this wave was resolved from: ${GATE_REPORT_LABEL}. Read it. A baton here may
have a blocker whose plan is already approved — that blocker's decisions are published, and a
scout that re-derived them as unknowns has over-read the size.

Batons in this wave:
${sizingLines}

Read \`agents/blitz-em.md\` (under the coordinator plugin root) § Plan-blitz in full and follow it:
the per-baton emit, the sizingObject scaffold and its BATON KEY, reviewers, and surfacedToPm.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${CLI_RESOLUTION_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, waveSlot, 'em-size-review'))}`,
  // opus-ruling: G-EM-2026-10-27-R3
  // opus-justified: one agent per wave interrogates every sizing and routes each baton; a routing judgment, not per-item work.
  { model: 'opus', ...withRole('coordinator:blitz-em'),
    label: `size-review:${waveSlot}`,
    phase: 'Size',
    schema: WAVE_DISPATCH_SCHEMA,
  },
))

// A sizing-object absence naming a GUARD REFUSAL (about the dispatch identity, so every stage
// would hit it too).
const DENIAL_SHAPED = /\b(guard:|denied|refused|blocked by|not on (the )?(coordinator\x27?s? )?(enumerated )?(agent )?roster|confined)\b/i

// Denials about WHO dispatched, not WHAT one agent ran: a command-shape refusal (a scout's
// own Bash) is not an identity denial.
const IDENTITY_SHAPED = /\b(not on (the )?(coordinator\x27?s? )?(enumerated )?(agent )?roster|confined|workflow-subagent|subagent_type)\b/i

const PLANNABLE_ROUTES = new Set(['plan', 'spec-dispatch'])

// The XS lane: real work, not plan-shaped. Trap: dropping it with the other non-plannable routes
// would lose it.
const DISPATCHABLE_ROUTES = new Set(['dispatch'])

// Why each excluded route leaves the wave; `dispatch` is the one HANDOFF (to the driver).
const ROUTE_EXITS = {
  dispatch: 'XS/dispatch — routes to a driver-run ask run and has no plan',
  shape: 'route: shape — the problem is not converged; coordinator:shape is the room',
  roadmap: 'route: roadmap — spans workstreams; coordinator:roadmap-planning is the room',
  'pm-decision': 'route: pm-decision — the exit is the PM\'s to pick, not this wave\'s',
  'goal-setting': 'XXL/goal-setting — too large to be one baton; coordinator:goal-setting is the room',
}

// A citation is committed state and never carries a host path: `coordinator-doc-new` prints an
// absolute path, so it is rewritten repo-relative here.
function repoRelativeCitation(value) {
  if (typeof value !== 'string' || !value.trim()) return value
  const text = value.trim()
  if (!REPO_ROOT) return text
  // Folded on both sides (an agent may respell a Windows root); drive letters compare case-insensitively.
  const fold = (s) => s.replace(/\\/g, '/')
  const root = fold(REPO_ROOT).replace(/[/]+$/, '') + '/'
  const folded = fold(text)
  const drive = /^[A-Za-z]:/.test(root)
  const head = drive ? folded.slice(0, root.length).toLowerCase() : folded.slice(0, root.length)
  if (head === (drive ? root.toLowerCase() : root)) return folded.slice(root.length)
  // Absolute but outside this repo: left as is, so the read-side gate refuses it.
  return text
}

// One decision per baton, enforced here: nothing downstream dedups, so a twice-decided baton would
// be planned twice; the later decision is dropped and reported.
const duplicateDecisions = []
const decidedById = new Map()
const decisions = ((dispatch && dispatch.decisions) || []).map((d) =>
  d && typeof d === 'object' && d.sizingObject
    ? { ...d, sizingObject: repoRelativeCitation(d.sizingObject) }
    : d,
).map((d) =>
  // The baton arg's `route` is the effective one: a pm-decision the PM already resolved is a plan.
  d && d.route === 'pm-decision' && batonFor(d) && batonFor(d).route === 'plan'
    ? { ...d, route: 'plan', surfacedToPm: false }
    : d,
).filter((d) => {
  const kept = d && decidedById.get(d.batonId)
  if (kept) {
    duplicateDecisions.push({ batonId: d.batonId, keptRoute: kept.route, droppedRoute: d.route })
    return false
  }
  if (d && d.batonId) decidedById.set(d.batonId, d)
  return true
})
const surfacedToPm = decisions.filter((d) => d.surfacedToPm)
const plannable = decisions.filter(
  (d) => !d.surfacedToPm && PLANNABLE_ROUTES.has(d.route),
)
// An XS runs only when its EXECUTION gate is open (blockers coded); the planning gate is no substitute.
const dispatchable = decisions.filter(
  (d) =>
    !d.surfacedToPm &&
    DISPATCHABLE_ROUTES.has(d.route) &&
    batonFor(d) &&
    batonFor(d).executionOpen === true,
)
// The ask run that reaches `land_run` is composed from a sizing object; the decision's citation wins.
const xsSizingFor = (d) => repoRelativeCitation(d.sizingObject || batonFor(d).sizingObject) || null
// emit-dispatch-workflow refuses a pair neither side names, so an XS leaves as an xsRun only when
// this baton's record path is attested by a `baton:` echo.
const xsBatonStamped = (d) => {
  const record = repoRelativeCitation(batonFor(d).path)
  return [d.sizingBaton, batonFor(d).sizingBaton].some((v) => !!v && repoRelativeCitation(v) === record)
}
const xsRunOf = (d) => ({
  batonId: d.batonId,
  record: repoRelativeCitation(batonFor(d).path),
  sizingObject: xsSizingFor(d),
  deliverableId: batonFor(d).deliverableId || null,
})
const xsRuns = dispatchable
  .filter((d) => xsSizingFor(d) && xsBatonStamped(d))
  .map(xsRunOf)
// The link pass below appends to both; routedElsewhere reads them after it.
const xsRunIds = new Set(xsRuns.map((r) => r.batonId))

const XS_LINK_SCHEMA = {
  type: 'object',
  required: ['batonId', 'linked', 'sizingBaton', 'sidecarPath'],
  properties: {
    batonId: { type: 'string' },
    linked: { type: 'boolean' },
    sizingBaton: { type: ['string', 'null'] },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

function xsLinker(d) {
  const baton = batonFor(d)
  const supplied = suppliedOp('xsLink', d.batonId, 'linked')
  if (supplied) return Promise.resolve(supplied)
  return trackAgent(`xs-link:${d.batonId}`, agent(
    `phase: xs-baton-link

${ROLE_CONTRACTS['blitz-em']}

Baton ${baton.id} — "${baton.title}" is an execution-open XS routed \`dispatch\`. Its sizing object
${xsSizingFor(d)} carries no \`baton:\` key naming the record ${baton.path}, and
\`emit-dispatch-workflow --sizing <sizing> --baton <record>\` refuses a pair neither side names.

${CLI_RESOLUTION_RULE}
1. Run \`sizing-link-baton --baton ${baton.path} --write\`. It stamps the sizing's \`baton:\` and the baton's
   sizing citation. If it refuses or finds no match, Edit ONLY the sizing object above so its top-level
   \`baton:\` is exactly \`${baton.path}\`. Touch nothing else.
2. Return \`linked\` true and \`sizingBaton\` as the \`baton:\` value now on disk in ${xsSizingFor(d)}; if you could
   not link it, \`linked\` false, \`sizingBaton\` null, and the refusal text in your sidecar.
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, d.batonId, 'xs-baton-link'))}`,
    { model: 'sonnet', ...withRole('coordinator:blitz-em'),
      label: `xs-link:${d.batonId}`,
      phase: 'Size',
      effort: 'low',
      schema: XS_LINK_SCHEMA,
    },
  ))
}

await Promise.all(
  dispatchable
    .filter((d) => xsSizingFor(d) && !xsBatonStamped(d))
    .map((d) =>
      xsLinker(d).then(
        (r) => {
          if (r && r.linked === true && r.sizingBaton
            && repoRelativeCitation(r.sizingBaton) === repoRelativeCitation(batonFor(d).path)) {
            d.sizingBaton = r.sizingBaton
            xsRuns.push(xsRunOf(d))
            xsRunIds.add(d.batonId)
          }
        },
        () => {},
      ),
    ),
)
const UNSIZED_XS_REASON = 'XS/dispatch, but no sizing object — the ask run that reaches land_run needs one'
// Routed somewhere other than a plan; never dropped, each carries its reason.
const routedElsewhere = decisions
  .filter(
    (d) =>
      !d.surfacedToPm &&
      !PLANNABLE_ROUTES.has(d.route) &&
      !xsRunIds.has(d.batonId),
  )
  .map((d) => ({
    batonId: d.batonId,
    tshirt: d.tshirt,
    route: d.route,
    // Trap: an absent `executionOpen` (caller defect; every XS recycles) must not read as a
    // closed execution gate.
    reason: DISPATCHABLE_ROUTES.has(d.route)
      ? (batonFor(d) && batonFor(d).executionOpen === true
        ? (xsSizingFor(d)
          ? 'XS/dispatch, sized, but the sizing object carries no `baton:` echo naming this record — '
            + 'emit-dispatch-workflow would refuse the pair'
          : `${UNSIZED_XS_REASON}${d.sizingObjectAbsence ? ` — em: ${d.sizingObjectAbsence}` : ''}`)
        : batonFor(d) && batonFor(d).executionOpen === undefined
        ? 'XS/dispatch, but the caller carried no `executionOpen` on this baton — '
          + 'the args contract requires it (from `roadmap.plan_gate`\'s '
          + '`execution_gate.open`). NOT a shut gate: nothing was asked. Fix the fire '
          + 'and re-run; leaving it makes every XS recycle forever.'
        : 'XS/dispatch, but its EXECUTION gate is shut — blockers planned, not coded')
      : ROUTE_EXITS[d.route] || `route: ${d.route} — not a planning route`,
    rationale: d.rationale,
  }))

function batonFor(decision) {
  return batons.find((b) => b.id === decision.batonId)
}

// A denied scaffold fails here, not four stages later: a guard denial says this dispatch identity
// cannot run any stage.
const scaffoldDenials = plannable.filter((d) => DENIAL_SHAPED.test(String(d.sizingObjectAbsence || '')))
const identityDenied = !PLUGIN_AGENTS
  || scaffoldDenials.every((d) => IDENTITY_SHAPED.test(String(d.sizingObjectAbsence || '')))
if (plannable.length && scaffoldDenials.length === plannable.length && identityDenied) {
  return {
    waveIndex,
    trailDir,
    ...(parsedArgs.engineRef ? { engineRef: parsedArgs.engineRef } : {}),
    trailSlotDir: `${trailDir}/${waveSlot}`,
    completed: false,
    incompleteReason:
      `HALTED AFTER SIZING: all ${plannable.length} plannable baton(s) had their sizing-object `
      + 'scaffold DENIED BY A GUARD, not merely left unwritten. A denial is a fact about the '
      + 'dispatch identity, so the planner, premise-check and reviewer below would be refused '
      + 'identically — the wave was stopped rather than spending them to prove it. The '
      + 'usual cause is an agentType the roster does not carry: check `pluginAgentsAvailable` in '
      + 'this fire\'s bound args and re-emit with it resolved (`emit-wave-fire` detects it). '
      + 'Tripwire: A-WORKFLOW-DISPATCH-WITHOUT-WITHROLE-IS-CONFINED.',
    agentErrors: 0,
    scaffoldDenials: scaffoldDenials.map((d) => ({ batonId: d.batonId, route: d.route, reason: d.sizingObjectAbsence })),
    // Lanes stay present and empty so the shape matches a normal result.
    ready: [],
    pulled: [],
    replan: [],
    surfacedToPm,
    adjudicated: [],
    routedElsewhere,
    duplicateDecisions,
    sizingObjectAbsences: scaffoldDenials.map((d) => ({
      batonId: d.batonId, route: d.route, reason: d.sizingObjectAbsence,
    })),
  }
}

// Single-plan pre-flight: started beside `planner()`, awaited in the second stage. The no-op catch
// keeps an early rejection from surfacing unhandled before the await.
const priorArtPromise = SINGLE_MODE && plannable.length
  ? priorArtPreflight(batons[0], waveIndex, trailDir)
  : null
if (priorArtPromise) priorArtPromise.catch(() => {})

// Phases 3-5, per baton, pipelined: no barrier between the stages.
const chains = await pipeline(
  plannable,
  (decision) => {
    const baton = batons.find((b) => b.id === decision.batonId)
    // An em decision can name a baton the wave never carried: a blocked entry, not a failure.
    if (!baton) {
      return Promise.resolve({
        decision,
        baton: { id: String(decision.batonId || '(no baton id)'), title: '(baton not in the args)', path: null },
        plan: {
          status: 'blocked',
          blockedReason: `the em decided baton "${decision.batonId}", which is not among this wave's args batons; nothing was planned`,
        },
      })
    }
    const singleContext = singleContextFor(baton, trailDir)
    return planner(baton, decision, waveIndex, trailDir, singleContext).then((plan) => ({ decision, baton, plan }))
  },
  async ({ decision, baton, plan }) => {
    if (!plan || plan.status === 'blocked') {
      return { decision, baton, plan, reviews: [] }
    }
    // The planner's `planPath` is a claim: one planner returned its trail sidecar, so every finding
    // would land on a trail sidecar, not a plan.
    const claimed = String(plan.planPath || '')
    // A path SEGMENT, never a substring (`retire-the-legacy-subagent-share-root.md` is a plan).
    const looksLikeTrail =
      claimed.split(/[\\/]/).includes('subagent-share') ||
      claimed.startsWith(trailDir) ||
      /\.(plan-review|em-size-review|review-integration|review-[a-z0-9-]*pointer)\.md$/.test(claimed)

    if (looksLikeTrail) {
      if (baton.planPath) {
        plan = { ...plan, planPath: baton.planPath, planPathCorrected: claimed }
      } else {
        return {
          decision,
          baton,
          plan: {
            ...plan,
            status: 'blocked',
            blockedReason:
              `planner returned a trail/sidecar path as planPath (${claimed}); refusing to point ` +
              `a reviewer at a file that is not the plan`,
          },
          reviews: [],
        }
      }
    }

    // Phase 3.4 — prep gate as code: the draft must be PREPPED before any checker or reviewer reads it.
    const settled = await settlePlanPrepGate(baton, decision, waveIndex, trailDir, singleContextFor(baton, trailDir), plan)
    plan = settled.plan
    if (settled.exhausted) {
      return {
        decision,
        baton,
        plan: {
          ...plan,
          status: 'blocked',
          blockedReason:
            `prep-gate: plan.prep_gate still refuses ${plan.planPath} after ${PLAN_STAGE_PREP_GATE_ROUNDS} author repairs. ` +
            `${settled.exhausted.message} ${settled.exhausted.findings.join(' | ')}`.trim() +
            (plan.blockedReason ? ` Planner said: ${String(plan.blockedReason).slice(0, 500)}` : ''),
        },
        reviews: [],
      }
    }

    // Phase 3.5 — premise check, sequenced before the reviewers (a racing check arrives too late
    // for a reviewer to read).
    const priorArt = priorArtPromise ? await priorArtPromise : null
    const checkersOwed = preReviewCheckersOwed(decision.tshirt)
    const checkersSkipped = !checkersOwed
    const preReview = checkersOwed ? await premiseChecker(baton, plan, trailDir, true) : null
    const { coverage = null, ...premiseOnly } = preReview ?? {}
    const premise = preReview ? premiseOnly : null
    if (checkersOwed && !coverage) {
      agentIncidents.push({
        role: 'premise',
        kind: 'missing-coverage',
        detail: preReview
          ? 'the merged pre-review dispatch returned no coverage object'
          : 'the merged pre-review dispatch returned nothing, so no coverage verdict exists',
      })
    }
    if (premise) checkSidecarPath(baton.id, PREMISE_REVIEWER, premise.sidecarPath)
    let premiseCheckResult = premiseAsReview(baton, premise)
    let premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    // No checkSidecarPath for coverage: it is report-only on the trail, with no ledger to verify.
    const coverageResult = planCoverageAsReview(baton, coverage)
    const coverageVerdict = coverageResult ? resolveVerdict(coverageResult) : null

    const reviewSignals = await signalsFor(plan)
    const { reviewers: resolvedReviewers, substitutions } = resolveReviewers(decision.reviewers, reviewSignals, AVAILABLE_PLUGINS)
    const roster = await reviewRoster()
    const laddered = roster ? planReviewers(decision.tshirt, resolvedReviewers, reviewSignals, roster) : null
    const unmodelled = laddered ? laddered.entries.filter((e) => !e.model) : []
    if (!laddered || !laddered.entries.length || unmodelled.length) {
      return {
        decision,
        baton,
        plan: {
          ...plan,
          status: 'blocked',
          blockedReason: !laddered
            ? 'the plan_review block was unreadable and no parallelReview arg named a roster: no reviewer set to dispatch'
            : `the plan_review block names no reviewer or model for ${unmodelled.map((e) => e.agentType).join(', ') || `a ${decision.tshirt} plan`}`,
        },
        reviews: [],
      }
    }
    REVIEW_ROSTER = roster
    const ladderReviewers = laddered.reviewers
    const chattyPick = chattyWavePick(ladderReviewers)
    // The sequential loop iterates `reviewers`: empty on the wave paths.
    let reviewers = chattyPick.wave ? [] : ladderReviewers
    let reviewNote = chattyPick.note
    for (const dropped of laddered.dropped) {
      substitutions.push(`${dropped} -> (not dispatched: a ${decision.tshirt} plan's reviewer set is fixed by the size ladder)`)
    }
    // Only the LAST reviewer hosts the readiness op; `hostParams` is kept for an errored entry.
    let hostParams = null
    const hostFor = (reviewer) => {
      if (reviewer !== reviewers[reviewers.length - 1]) return null
      const input = { reviews: opReviewList(reviews), premise: premiseForOp(premise), coverage: coverageForOp(coverage) }
      hostParams = readinessParams(plan.planPath, input)
      return input
    }
    // Default: one parallel wave of self-applying reviewers. The sequential loop runs only
        // The sequential loop runs for a single-reviewer ladder, or when the chatty pick carries a note (a degrade reason).
    // A single-reviewer ladder (M, L) has no race for merged revise to avoid: that reviewer takes the loop and hosts the op.
    const parallelRun = !chattyPick.wave && chattyPick.note === null && ladderReviewers.length > 1
    if (parallelRun) reviewers = []
    let wave = null
    if (chattyPick.wave) {
      wave = await chattyReviewWave({ baton, decision, plan, trailDir, premise, priorArt, coverage, reviewers: ladderReviewers })
      if (!wave) {
        reviewers = ladderReviewers
        reviewNote = 'chatty overseer returned nothing; fell back to the sequential loop'
      }
    }
    const reviews = []
    let pivoted = null
    for (const reviewer of reviewers) {
      // Nothing dispatches after a PIVOT: a later reviewer would apply findings to a plan about
      // to be replanned.
      if (pivoted) break
      const result = await reviewerAgent(baton, decision, plan, reviewer, trailDir, premise, reviews, hostFor(reviewer), priorArt)
      if (result) checkSidecarPath(baton.id, `review-${reviewer}`, result.sidecarPath)
      const violation = ladderReviewers.length === 1 ? selfApplyViolation(result && { ...result, reviewer }) : null
      if (violation) {
        return {
          decision,
          baton,
          plan: { ...plan, status: 'blocked', blockedReason: violation },
          reviews: [],
        }
      }
      // `reviewer` is the harness-resolved identity: it overwrites the agent's self-report.
      const resolved = result ? resolveVerdict({ ...result, reviewer }) : null
      if (resolved) {
        reviews.push(resolved)
        if (resolved.pivot) pivoted = resolved
      }
    }
    if (wave) {
      reviews.push(...wave.reviews)
      hostParams = wave.hostParams
    }
    let parallelWave = null
    if (parallelRun) {
      parallelWave = await parallelReviewWave({ baton, decision, plan, trailDir, premise, priorArt, coverage, entries: laddered.entries })
      reviews.push(...parallelWave.reviews)
      hostParams = parallelWave.hostParams
    }
    // Honoured only from the last reviewer; `opReviews` is the list the op saw.
    const opReviews = opReviewList(reviews)
    const host = reviews[reviews.length - 1]
    const readinessReply = host && host.reviewer === ladderReviewers[ladderReviewers.length - 1]
      ? honouredReadiness(host, opReviewList(reviews.slice(0, -1)))
      : null
    // The reviewers saw every premise row; the count that rides the review set is the op's.
    if (readinessReply) {
      premiseCheckResult = premiseAsReview(baton, premise, readinessReply)
      premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    }
    // An op error counts only from the last, non-pivoted reviewer handed the op; the params keep
    // the host's review set whether or not its op failed.
    const hostIsLast = host && host.reviewer === ladderReviewers[ladderReviewers.length - 1] && !host.pivot
    const readinessError = hostIsLast && typeof host.readinessError === 'string' && host.readinessError.trim()
      ? host.readinessError
      : null
    const readinessParamsOut = hostIsLast && hostParams
      ? { ...hostParams, reviews: [...hostParams.reviews, { reviewer: host.reviewer, verdict: host.raw, ledger: host.sidecarPath }] }
      : null
    if (coverageVerdict) reviews.push(coverageVerdict)
    // Re-resolving is a no-op for resolved reviews; it resolves the premise-check pseudo-reviewer.
    const kept = [premiseCheckResult, ...reviews].filter(Boolean).map(resolveVerdict)
    return {
      decision,
      baton,
      plan,
      reviews: kept,
      premiseCheckVerdict,
      checkersSkipped,
      coverageVerdict,
      substitutions,
      premise,
      coverage,
      readinessReply,
      readinessError,
      readinessAttempts: readinessError ? (host.readinessAttempts || 2) : null,
      readinessParams: readinessParamsOut,
      readyOpReply: readinessReply ? host.readyOpReply : undefined,
      readyOpError: host ? host.readyOpError : undefined,
      readyOpDishonoured: Boolean(host && host.readyOpReply !== undefined && !readinessReply),
      opReviews,
      ...(wave ? { chattyWave: true } : {}),
      ...(parallelWave ? { parallelWave: true } : {}),
      ...(reviewNote ? { reviewNote } : {}),
    }
  },
)

// Phase 5b: each XS is handed to the driver (`xsRuns`); a Workflow agent may never commit.
function ledgerLine(plan, reviews) {
  if (!plan || plan.status === 'blocked') {
    return '(no plan was written — nothing for a reviewer to apply findings to; expected, not a defect)'
  }
  if (!reviews.length) {
    return 'NO REVIEWER RAN over a plan that EXISTS — nothing is known to have been applied. '
      + 'This is NOT a quiet review set: it is the absence of the pass that would report one. '
      + 'Reconciled to pulled if the verdict is ready.'
  }
  return reviews
    .map((r) => `${r.reviewer}: ${r.findingCount || 0} finding(s)${r.pivot ? ' — Suspended (PIVOT)' : ''} -> ${r.sidecarPath}`)
    .join('; ')
}

// Phase 5c — prep-gate revise-in-place: one agent per plan applies only engine-marked `mechanical`
function coverageRepairStep(coverage) {
  if (!coverage || !coverage.sidecarPath || !(coverage.mechanicalFindings > 0)) return ''
  return `
COVERAGE REPAIRS (before step 1): the plan-coverage pre-flight reported ${coverage.mechanicalFindings}
Mechanical finding(s) at ${coverage.sidecarPath}. Open that sidecar and apply each Mechanical finding
to the plan in place, as written: the classes are Substrate-drift, Malformed-rows, Missing-writes,
Unregistered-hooks, and Scope-writes-gap. Leave every Judgment finding untouched
and touch nothing else in the plan. List each one you applied in \`coverageRepaired\`. This is part
of the same single revise pass, not a second loop.
`
}

// The op already named the repairs; apply exactly those and re-ask the op ONCE.
function opRepairSteps(plan, reply, coverage, files) {
  const covNote = coverage && coverage.sidecarPath
    ? `\nA repair of kind \`coverage-finding\` refers to a Mechanical finding in the plan-coverage sidecar at\n${coverage.sidecarPath}; open it to see the finding. List those you applied in \`coverageRepaired\` too.\n`
    : ''
  return `The readiness op already ran over this plan (verdict ${reply.verdict}, pull_class ${reply.pull_class}) and
returned these mechanical repairs, as {kind, target, instruction}:

${JSON.stringify(reply.mechanical_repairs, null, 2)}
${covNote}
1. Record \`before\` as ${reply.prep_gate.verdict}. Apply each repair to the plan in place, following
   its \`instruction\` at its \`target\` and nothing else; touch no other part of the plan. List what
   you changed in \`repaired\`. Do not run \`plan.prep_gate\` yourself.${censusRewriteOwed(reply) ? censusRewriteItem(reply) : ''}
2. Write \`{"plan":"${plan.planPath}"}\` (the plan alone) to \`${files.readiness}\` with your write tool, then run
   \`coordinator-invoke plan.readiness_verdict --params-file ${files.readiness}\`
   exactly as written, with no pipe, head, tail or truncation of any kind.
   Record its \`prep_gate.verdict\` as \`after\`, its \`verdict\` as \`afterVerdict\`, its
   \`pull_class\` as \`afterPullClass\` and its \`reason\` as \`afterReason\`, and its \`blocking\` array
   verbatim as \`afterBlocking\` when the reply carries one. If it fails (non-zero
   exit, no JSON reply, or an \`error\` envelope), run the identical command exactly once more. If
   that fails too, leave \`afterVerdict\` empty and put that run's own output VERBATIM (stderr, else
   stdout, prefixed \`exit <n>: \`, never summarised) in \`afterError\`. Never repair a second time,
   whatever it says.
3. If \`after\` is not PREPPED, put \`prep_gate.message\` and the remaining findings in \`gateReport\`.
${readyOpRepairStep(plan.planPath, files.readyOp)}`
}

function censusRewriteItem(reply) {
  return `
   CENSUS REWRITE. The gate refused census entries it cannot screen:

   ${String(reply.prep_gate.classes.CENSUS.detail).split('\n').join('\n   ')}

   - Rewrite each named entry's \`command\` to the allowed form, keeping its \`question\`.
   - Common cases: \`python -c ...\` becomes a grep/jq pipeline or \`python <tracked script>\`, and
     \`a | xargs grep\` becomes \`git grep --all-match\`.
   - Run the new command and set \`result\` to its output with \`at <short HEAD sha>\`.
   - An entry no allowed form can re-ask stays exactly as it is and is listed in \`gateReport\`.
   - Never delete an entry and never empty \`census\`.
   List each rewrite in \`repaired\`.`
}

function readyOpRepairStep(planPath, paramsFile) {
  if (!READY_OP) return ''
  return `4. If \`afterVerdict\` is "ready" and \`after\` is PREPPED, run exactly once: write exactly this JSON to
   \`${paramsFile}\` with your write tool, then run, with no inline JSON on the command line:

       ${JSON.stringify({ ...READY_OP.params, plan_path: planPath })}

       coordinator-invoke ${READY_OP.op} --params-file ${paramsFile}

   and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
   one-line failure in \`readyOpError\`. Otherwise run nothing and return neither field.
`
}

// With a premise re-check owed its re-ask is the standing answer, so the resolver's ready is not
// the standing answer.
function readyOpResolveStep(planPath, premiseRan, paramsFile) {
  if (!READY_OP) return ''
  return `4. If \`afterVerdict\` is "ready", \`afterPrepGate\` is "PREPPED" and \`unresolved\` is empty${premiseRan ? ' and \`touched\` is empty' : ''}, run exactly once: write exactly this JSON to
   \`${paramsFile}\` with your write tool, then run, with no inline JSON on the command line:

       ${JSON.stringify({ ...READY_OP.params, plan_path: planPath })}

       coordinator-invoke ${READY_OP.op} --params-file ${paramsFile}

   and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
   one-line failure in \`readyOpError\`. Otherwise run nothing and return neither field.
`
}

function singleContextFor(baton, trailDir) {
  return SINGLE_MODE
    ? {
        exitCriterionStatement: baton.exitCriterion,
        sizingPath: SINGLE_SIZING_PATH,
        priorArtSidecarPath: priorArtPromise ? sidecarFor(trailDir, baton.id, 'prior-art-check') : null,
      }
    : null
}

// Hosting only: runs plan.prep_gate and returns the reply untouched; the script reads the verdict. When
// plugin intake is owed it also relays `plugin_review_signals.py attach` for the plan.
async function planPrepGateHost(baton, plan, trailDir) {
  const root = REPO_ROOT || '<repo root>'
  const attachStep = PLUGIN_ATTACH_OWED ? `
4. Run \`python3 <coordinator plugin root>/lib/plugin_review_signals.py attach --repo-root ${root} --plan ${plan.planPath}\`.
   Return its \`availablePlugins\` (plugin names), \`signals\` (each entry verbatim: id, plugin, selects, model,
   prose_terms, write_triggers) and \`attached\` (signal ids) as it printed them. If it fails to run, omit those
   three fields; that never changes the verdict.${PLUGIN_SIGNALS_CLI_RULE}` : ''
  const reply = await trackAgent('plan-prep-gate-host', agent(
    `You review nothing and edit nothing: you only run the plan.prep_gate op for baton ${baton.id} ("${baton.title}") and relay its reply${PLUGIN_ATTACH_OWED ? ', then relay one plugin-signal CLI call' : ''}.

${CLI_RESOLUTION_RULE}
1. Run \`coordinator-invoke --repo ${root} plan.prep_gate '{"repo_root":"${root}","plan":"${plan.planPath}"}'\`.
2. Return its \`verdict\` (PREPPED | NOT-PREPPED | REFUSED) and its \`message\` verbatim. Return in
   \`findings\` one string per finding across every class, as \`<CLASS>/<kind>: <detail>\`, quoting the
   gate's words; \`findings\` is empty when PREPPED.
3. If the CLI fails to run, return verdict \`ENGINE-ERROR\` with the one-line failure in \`message\`
   and empty \`findings\`. Never retry, repair, or run the gate any other way.${attachStep}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'plan-prep-gate'))}`,
    { model: 'haiku', label: `plan-prep-gate:${baton.id}`, phase: 'Plan', schema: PLAN_PREP_GATE_SCHEMA },
  ))
  if (reply) PLAN_HOST_REPLIES.set(plan.planPath, reply)
  return reply
}

// NOT-PREPPED re-dispatches the planner, up to PLAN_STAGE_PREP_GATE_ROUNDS times. Returns {plan}
// with the final gate state; a still-NOT-PREPPED plan stays as the reconciliation reads it.
async function settlePlanPrepGate(baton, decision, waveIndex, trailDir, singleContext, drafted) {
  let current = drafted
  let findings = []
  for (let round = 0; ; round++) {
    const supplied = round === 0 ? suppliedOp('planPrepGate', baton.id, 'verdict') : null
    const reply = supplied || await planPrepGateHost(baton, current, trailDir)
    if (!reply || !['PREPPED', 'NOT-PREPPED'].includes(reply.verdict)) {
      agentIncidents.push({
        role: 'plan-prep-gate',
        kind: 'gate-unavailable',
        detail: reply ? `plan.prep_gate answered ${reply.verdict}: ${String(reply.message || '').slice(0, 300)}` : 'the plan.prep_gate host returned nothing',
      })
      return { plan: current }
    }
    if (reply.verdict === 'PREPPED') return { plan: current }
    findings = reply.findings || []
    if (round >= PLAN_STAGE_PREP_GATE_ROUNDS) {
      return { plan: current, exhausted: { message: reply.message || '', findings } }
    }
    const revised = await planner(baton, decision, waveIndex, trailDir, singleContext, {
      planPath: current.planPath,
      findings,
      message: reply.message || '',
    })
    if (!revised || revised.status === 'blocked') {
      return { plan: revised ? { ...revised, planPath: current.planPath } : current, exhausted: { message: reply.message || '', findings } }
    }
    current = { ...revised, planPath: current.planPath }
  }
}

function prepGateRevise(baton, plan, trailDir, coverage, reply, residue) {
  const residueScope = residue && residue.length ? `
SCOPE. A deterministic pass already applied every mechanical repair to this plan. Handle ONLY these
non-mechanical items and touch nothing else:

${JSON.stringify(residue, null, 2)}
` : ''
  const steps = residueScope + (reply ? opRepairSteps(plan, reply, coverage, paramsFilesFor(trailDir, baton.id)) : `${coverageRepairStep(coverage)}
1. Run \`coordinator-invoke plan.prep_gate '{"repo_root":"<repo root>","plan":"${plan.planPath}"}'\`.
   Its reply carries \`verdict\` (PREPPED | NOT-PREPPED | REFUSED) and \`classes\`, each class
   holding findings with \`mechanical\` and \`repair\`. Record the verdict as \`before\`.
2. PREPPED: change nothing; \`after\` is the same verdict.
3. NOT-PREPPED: edit the plan in place for every finding with \`mechanical: true\`, following its
   \`repair\` text and nothing else. A finding with \`mechanical: false\` is an authoring judgment
   you do not make: leave it, and do not touch any other part of the plan. List what you changed in
   \`repaired\`.
4. Run the gate exactly ONCE more and record that verdict as \`after\`. Never repair a second time,
   whatever the re-gate says.
5. If \`after\` is not PREPPED, put the gate's \`message\` and the remaining findings (class, kind,
   detail) in \`gateReport\`.
`)
  return trackAgent('prep-gate-revise', agent(
    `Run the mise-prep gate over one authored plan and repair what is mechanically repairable.

Baton: ${baton.id} — "${baton.title}"
Plan: ${plan.planPath}

${CLI_RESOLUTION_RULE}
${steps}
REFUSED or a CLI failure of \`plan.prep_gate\` is reported as such in \`before\`/\`after\`; do not retry or work around it.
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'prep-gate-revise'))}`,
    // Enricher, not executor: block_subagent_plan_body_write denies an executor plan-body edits.
    { model: 'sonnet', ...withRole('coordinator:enricher'),
      label: `prep-gate:${baton.id}`,
      phase: 'Review',
      schema: PREP_GATE_REVISE_SCHEMA,
    },
  ))
}

// census-unscreenable carries no engine repair, but a pull whose only failure is that class is
// the enricher's to rewrite.
function censusRewriteOwed(reply) {
  if (!reply || reply.verdict !== 'pulled' || reply.pull_class !== 'substantive') return false
  const classes = reply.prep_gate && reply.prep_gate.classes
  if (!classes || !classes.CENSUS || classes.CENSUS.kind !== 'census-unscreenable') return false
  return Object.entries(classes).every(([name, c]) => name === 'CENSUS' || (c && c.status === 'PASS'))
}

// Owed when there is no honoured reply (fail closed), the reply names mechanical repairs, or its
// only failure is a census rewrite.
const enricherOwed = (readinessReply) => !readinessReply || readinessReply.mechanical_repairs.length > 0
  || censusRewriteOwed(readinessReply)

const prepGateById = new Map()
await Promise.all(
  chains
    .filter(Boolean)
    .filter(({ plan }) => plan && plan.status !== 'blocked' && plan.planPath)
    .filter(({ readinessReply }) => enricherOwed(readinessReply))
    .map(async ({ baton, plan, coverage, readinessReply }) => {
      const supplied = suppliedOp('prepGate', baton.id, 'after')
      const residue = supplied && Array.isArray(supplied.nonMechanical) ? supplied.nonMechanical : []
      if (supplied && !residue.length) {
        const { nonMechanical, ...done } = supplied
        prepGateById.set(baton.id, { batonId: baton.id, ...done })
        return
      }
      const result = await prepGateRevise(baton, plan, trailDir, coverage, readinessReply, residue)
      if (result) prepGateById.set(baton.id, result)
    }),
)

// The op verdict that stands for a plan once the enricher (if owed) has run: the reply itself, or
// the post-repair re-run. null = no usable answer; the op's verdict is consumed, never recomputed.
function opStanding(chain) {
  const reply = chain.readinessReply
  if (!reply) {
    // The op was called and failed: the post-repair run carries no reviews, so it never promotes
    // a plan to ready.
    return chain.readinessError
      ? { verdict: 'errored', error: chain.readinessError, stage: 'review-host', attempts: chain.readinessAttempts || 2, params: chain.readinessParams }
      : null
  }
  if (reply.mechanical_repairs.length === 0 && !enricherOwed(reply)) {
    return {
      verdict: reply.verdict, pullClass: reply.pull_class, reason: reply.reason, message: reply.prep_gate.message,
      ...(Array.isArray(reply.blocking) ? { blocking: reply.blocking } : {}),
    }
  }
  const repaired = prepGateById.get(chain.baton.id)
  if (repaired && !repaired.afterVerdict && repaired.afterError) {
    return { verdict: 'errored', error: repaired.afterError, stage: 'post-repair', attempts: 2, params: chain.readinessParams || { plan: chain.plan.planPath } }
  }
  if (!repaired || !repaired.afterVerdict) return null
  if (repaired.afterVerdict === 'ready' && repaired.after !== 'PREPPED') return null
  return {
    verdict: repaired.afterVerdict,
    pullClass: repaired.afterPullClass || 'none',
    reason: repaired.afterReason || reply.reason,
    message: repaired.gateReport || reply.prep_gate.message,
    ...(Array.isArray(repaired.afterBlocking) ? { blocking: repaired.afterBlocking } : {}),
  }
}

function findingCounts(chain, reply) {
  if (reply && Number.isInteger(reply.blocking_findings) && Number.isInteger(reply.advisory_findings)
    && reply.blocking_findings >= 0 && reply.advisory_findings >= 0) {
    return { blocking: reply.blocking_findings, advisory: reply.advisory_findings, source: 'op' }
  }
  let blocking = 0
  let advisory = 0
  for (const r of chain.reviews || []) {
    if (r.reviewer === PREMISE_REVIEWER || r.reviewer === PLAN_COVERAGE_REVIEWER) continue
    const n = r.findingCount || 1
    if (r.verdict === 'WARN') advisory += n
    else if (r.verdict !== 'APPROVED') blocking += n
  }
  const pRows = (chain.premise && chain.premise.rows) || []
  blocking += premiseBlockingRows(pRows, reply).length
  for (const k of (reply && Array.isArray(reply.blocking)) ? reply.blocking : []) {
    if (typeof k === 'string' && (k.startsWith('anchor-premise') || k.startsWith('anchor-premises-'))) blocking += 1
  }
  const cov = chain.coverage
  if (cov) {
    const judged = cov.judgmentFindings || 0
    if (cov.verdict === 'BLOCKED-SURFACE-TO-PM') blocking += judged || 1
    else advisory += judged
  }
  return { blocking, advisory, source: 'wave' }
}

// `{ ok: false, reason }` names the refusal.
function judgmentResolvable(chain, standing, counts) {
  if (!standing || standing.verdict !== 'judgment') return { ok: false, reason: 'the standing op verdict is not judgment' }
  if (!chain.plan || chain.plan.status === 'blocked' || !chain.plan.planPath) return { ok: false, reason: 'no authored plan to resolve' }
  if ((chain.reviews || []).some((r) => r.pivot)) return { ok: false, reason: 'a reviewer returned PIVOT' }
  if (counts.blocking > 0) return { ok: false, reason: `${counts.blocking} blocking finding(s) are not the resolver's to resolve` }
  // Only the op's counts see ledger clearance (or every plan reviewer returned APPROVED). `ready` is
  // granted only with zero advisory findings and no mechanical repair owed.
  const reply = chain.readinessReply
  const planReviews = (chain.reviews || []).filter((r) => r.reviewer !== PREMISE_REVIEWER && r.reviewer !== PLAN_COVERAGE_REVIEWER)
  const allOk = planReviews.length > 0 && planReviews.every((r) => r.verdict === 'APPROVED')
  if (((counts.source === 'op' && counts.advisory === 0) || (allOk && counts.advisory === 0)) && reply && (reply.mechanical_repairs || []).length === 0
    && reply.prep_gate && reply.prep_gate.verdict === 'PREPPED') {
    return { ok: false, cleared: true, reason: 'every reviewer ledger verified and every logged finding is applied — no resolver pass owed' }
  }
  return { ok: true, reason: null }
}

function judgmentReaskParams(chain) {
  return {
    plan: chain.plan.planPath,
    coverage: chain.coverage ? coverageForOp(chain.coverage) : null,
    ...(chain.premise ? { premise: premiseForOp(chain.premise) } : {}),
    reviews: chain.opReviews || [],
  }
}

function judgmentResolve(baton, plan, trailDir, coverage, reviews, standing, reaskParams, premiseRan) {
  const warns = (reviews || []).filter((r) => r.verdict === 'WARN' && r.reviewer !== PLAN_COVERAGE_REVIEWER && r.sidecarPath)
  const covBlock = coverage && coverage.sidecarPath
    ? `\nPlan-coverage sidecar: ${coverage.sidecarPath} (${coverage.judgmentFindings || 0} Judgment finding(s)). Resolve its Judgment findings in the plan; leave its Mechanical rows alone.\n`
    : ''
  const reviewBlock = warns.length
    ? `\nWARN reviewers' findings-ledger sidecars (resolve each row that is not applied and verified):\n${warns.map((r) => `  - ${r.reviewer}: ${r.sidecarPath}`).join('\n')}\n`
    : ''
  const coverageRule = coverage
    ? `\`coverage\` with \`mechanicalFindings\` set to 0 and \`judgmentFindings\` set to the number of coverage items you list in \`unresolved\` (its \`verdict\` stays as shown)`
    : '`coverage` as `null`, exactly as shown'
  const reaskRule = `Change it only so (the op trusts these inputs; dropping a review you did not settle makes the ready false): send ${coverageRule}; drop from \`reviews\` only a WARN review every one of whose
   uncleared ledger rows you list in \`resolved\`; leave \`premise\` and every other \`reviews\` entry
   as shown. A premise row the reason above lists as an "intended correction the resolver may take"
   (covered by the plan's \`corrects:\`/\`fixed_by\`) is yours to take: settle it in the plan and list
   it in \`resolved\`. It is not a blocking finding.`
  return trackAgent('judgment-resolve', agent(
    `Resolve the judgment findings still open on one reviewed plan, then re-ask the readiness op once.

Baton: ${baton.id} — "${baton.title}"
Plan: ${plan.planPath}

The readiness op answered \`judgment\` with this reason, verbatim:

    ${standing.reason}
${covBlock}${reviewBlock}
${CLI_RESOLUTION_RULE}
Judgment resolve (follow exactly): edit the plan in place to resolve each finding listed here; never
scaffold, move or rename it, and touch nothing no finding names; write no attribution (reviewer names,
finding numbers) into the plan. List each finding settled in \`resolved\`, each not settled with why in
\`unresolved\`, and each spine row id and frontmatter key you edited in \`touched\` (\`[]\` when none
carries a citation). Then write the JSON below to \`${paramsFileFor(trailDir, baton.id, 'reask-params')}\` with your write tool and run
\`coordinator-invoke plan.readiness_verdict --params-file ${paramsFileFor(trailDir, baton.id, 'reask-params')}\` ONCE, with no inline JSON on the command line. Record the reply's \`verdict\` as
\`afterVerdict\`, \`pull_class\` as \`afterPullClass\`, \`reason\` as \`afterReason\`, \`prep_gate.verdict\`
as \`afterPrepGate\`, and its \`blocking\` array verbatim as \`afterBlocking\` when present. If the op fails
(non-zero exit, no JSON reply, or an \`error\` envelope) run the identical command once more; if that
fails too, leave \`afterVerdict\` empty and put that run's output VERBATIM (stderr, else stdout,
prefixed \`exit <n>: \`) in \`afterError\`. Never resolve or re-ask a second time.

The params file of the one \`plan.readiness_verdict\` re-ask holds:

       ${JSON.stringify(reaskParams)}

${reaskRule}
${readyOpResolveStep(plan.planPath, premiseRan, paramsFileFor(trailDir, baton.id, 'ready-op-params'))}${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'judgment-resolve'))}`,
    // Brief inlines plan-author.md § Judgment resolve; no persona load.
    { model: 'sonnet', ...withRole('general-purpose'),
      label: `judgment-resolve:${baton.id}`,
      phase: 'Review',
      schema: JUDGMENT_RESOLVE_SCHEMA,
    },
  ))
}

function judgmentResolveOwed(chain) {
  const standing = opStanding(chain)
  return judgmentResolvable(chain, standing, findingCounts(chain, chain.readinessReply)).ok
}

const judgmentResolveById = new Map()
await Promise.all(
  chains
    .filter(Boolean)
    .filter(judgmentResolveOwed)
    .map(async (chain) => {
      const result = await judgmentResolve(
        chain.baton, chain.plan, trailDir, chain.coverage, chain.reviews, opStanding(chain), judgmentReaskParams(chain),
        Boolean(chain.premise),
      )
      if (result) judgmentResolveById.set(chain.baton.id, result)
    }),
)

// Phase 5d, after the resolver: the touched premise rows are re-judged and this leg hosts the one op
// re-ask over the revised rows.
function premiseRecheckOwed(chain, res) {
  return Boolean(chain.premise && res && res.afterVerdict
    && Array.isArray(res.touched) && res.touched.length > 0)
}

function premiseRecheck(baton, plan, trailDir, priorPremise, touched, reaskParams, res) {
  const prior = ((priorPremise && priorPremise.rows) || []).map((r) => ({
    class: r.questionClass, verdict: r.verdict, citation: r.citation,
  }))
  const coverageRule = reaskParams.coverage
    ? `\`coverage\` with \`mechanicalFindings\` set to 0 and \`judgmentFindings\` set to ${(res.unresolved || []).length} (the resolver's unresolved count; its \`verdict\` stays as shown)`
    : '`coverage` as `null`, exactly as shown'
  return trackAgent('premise-recheck', agent(
    `phase: premise-check

A plan-author pass just revised one plan. Re-judge the premise rows its edit touched, then re-ask the
readiness op ONCE over the rows that now stand.

Baton: ${baton.id} — "${baton.title}"
Plan: ${plan.planPath}

The resolver edited these spine rows and frontmatter keys: ${touched.join(', ')}.
It settled: ${(res.resolved || []).join('; ') || '(none)'}. It left unresolved: ${(res.unresolved || []).join('; ') || '(none)'}.

Prior premise rows, as the op was last shown them (class, verdict, citation):

${JSON.stringify(prior)}

${CLI_RESOLUTION_RULE}
Read \`agents/premise-checker.md\` (under the coordinator plugin root) § Plan-blitz wave passes /
Premise recheck in full and follow it. Class 4 on this host: \`${ARMING_CHECK_CLI} <instrument> --json\`.

${PREMISE_CHECK_CONTRACT}

${INSTRUMENT_CAN_REPORT_RED_CONTRACT}

The params file of its one \`plan.readiness_verdict\` re-ask (write it to \`${paramsFileFor(trailDir, baton.id, 'reask-params')}\` with your write tool; run \`coordinator-invoke plan.readiness_verdict --params-file\` on that path, no inline JSON) holds:

       ${JSON.stringify(reaskParams)}

Change \`reviews\` and \`coverage\` only so: send ${coverageRule}.
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'premise-recheck'))}`,
    { model: 'sonnet', ...withRole('coordinator:premise-checker'),
      label: `premise-recheck:${baton.id}`,
      phase: 'Review',
      effort: 'low',
      schema: PREMISE_RECHECK_SCHEMA,
    },
  ))
}

const premiseRecheckById = new Map()
await Promise.all(
  chains
    .filter(Boolean)
    .filter((chain) => premiseRecheckOwed(chain, judgmentResolveById.get(chain.baton.id)))
    .map(async (chain) => {
      const res = judgmentResolveById.get(chain.baton.id)
      const result = await premiseRecheck(
        chain.baton, chain.plan, trailDir, chain.premise, res.touched, judgmentReaskParams(chain), res,
      )
      if (result) premiseRecheckById.set(chain.baton.id, result)
    }),
)

function standingPremise(chain) {
  const rc = premiseRecheckById.get(chain.baton.id)
  if (!chain.premise || !rc) return chain.premise || null
  return { ...chain.premise, rows: mergePremiseRows(chain.premise.rows, rc.rows, rc.retired) }
}

function standingReadiness(chain) {
  const base = opStanding(chain)
  if (!base || base.verdict !== 'judgment') return base
  const counts = findingCounts(chain, chain.readinessReply)
  const carried = {
    ...base,
    blockingFindings: counts.blocking,
    advisoryFindings: counts.advisory,
    findingCountSource: counts.source,
  }
  const gate = judgmentResolvable(chain, base, counts)
  if (gate.cleared) {
    return {
      ...carried,
      verdict: 'ready',
      pullClass: 'none',
      reason: `${base.reason} [no resolver owed: ${gate.reason}]`,
      judgmentResolve: { state: 'not-attempted', reason: gate.reason },
    }
  }
  if (!gate.ok) return { ...carried, judgmentResolve: { state: 'not-attempted', reason: gate.reason } }
  const res = judgmentResolveById.get(chain.baton.id)
  if (!res) return { ...carried, judgmentResolve: { state: 'failed', cause: 'the resolver returned nothing' } }
  if (!res.afterVerdict && res.afterError) {
    return {
      verdict: 'errored', error: res.afterError, stage: 'judgment-resolve', attempts: 2,
      params: judgmentReaskParams(chain),
    }
  }
  // A re-check's re-ask ran over the revised rows, so its answer supersedes the resolver's.
  const rc = premiseRecheckById.get(chain.baton.id)
  if (rc && !rc.afterVerdict && rc.afterError) {
    return {
      verdict: 'errored', error: rc.afterError, stage: 'premise-recheck', attempts: 2,
      params: { ...judgmentReaskParams(chain), premise: premiseForOp(standingPremise(chain)) },
    }
  }
  const ans = rc || res
  const unresolved = res.unresolved || []
  // A ready re-ask whose gate is not PREPPED is not ready (as in honouredReadiness); an absent
  // gate reading is held (the re-ask did not measure it).
  const gateHeld = ans.afterPrepGate === undefined || ans.afterPrepGate === 'PREPPED'
  if (unresolved.length === 0 && ans.afterVerdict === 'ready' && gateHeld) {
    const { blocking: _staleSet, ...carriedNoSet } = carried
    return {
      ...carriedNoSet,
      ...(Array.isArray(ans.afterBlocking) ? { blocking: ans.afterBlocking } : {}),
      verdict: 'ready',
      pullClass: ans.afterPullClass || 'none',
      reason: `${base.reason} [resolved: one plan-author pass settled ${(res.resolved || []).length} finding(s); the op re-ask answered ready${rc ? ' over the re-checked premise rows' : ''}]`,
      judgmentResolve: { state: 'resolved', resolved: res.resolved || [] },
    }
  }
  const cause = unresolved.length
    ? `the resolver left ${unresolved.length} finding(s) unresolved`
    : !gateHeld && ans.afterVerdict === 'ready'
      ? `the op re-ask answered ready but plan.prep_gate was ${ans.afterPrepGate}`
      : `the op re-ask answered ${ans.afterVerdict || 'nothing'}${ans.afterReason ? `: ${ans.afterReason}` : ''}`
  // An answered re-ask is the standing reply: its set replaces the first reply's.
  const { blocking: _firstSet, ...unset } = carried
  const standingSet = ans.afterVerdict
    ? (Array.isArray(ans.afterBlocking) ? { blocking: ans.afterBlocking } : {})
    : (Array.isArray(_firstSet) ? { blocking: _firstSet } : {})
  return { ...unset, ...standingSet, judgmentResolve: { state: 'failed', cause, unresolved } }
}

// The ready-op outcome from whichever leg made the ready call. Trap: neither field would read as a
// clean "no ready op" and silently drop the error.
function readyOpFields(src) {
  if (!READY_OP) return {}
  if (src && src.readyOpReply !== undefined) return { readyOpReply: src.readyOpReply }
  return { readyOpError: (src && src.readyOpError) || 'ready op did not run on the leg that made the ready call' }
}

const fireChains = chains.filter(Boolean)
const standingById = new Map(fireChains.map((c) => [c.baton.id, standingReadiness(c)]))

function readinessOpLine(chain) {
  const standing = standingById.get(chain.baton.id)
  const reply = chain.readinessReply
  const firstLine = (text) => String(text || '').split('\n')[0]
  const op = standing && standing.verdict === 'errored'
    ? `errored after ${standing.attempts} attempt(s) (${standing.stage}): ${firstLine(standing.error)}`
    : reply
    ? `${reply.verdict}/${reply.pull_class}${standing && reply.mechanical_repairs.length ? ` -> ${standing.verdict}/${standing.pullClass} after repair` : ''}`
    : 'no usable reply'
  const enricher = !chain.plan || chain.plan.status === 'blocked' || !chain.plan.planPath
    ? 'n/a (no plan)'
    : enricherOwed(reply)
      ? `spawned (${reply ? `${reply.mechanical_repairs.length} mechanical repair(s)` : 'no usable reply'})`
      : `skipped (${reply.verdict}, no mechanical repairs)`
  const jr = standing && standing.judgmentResolve
  const resolver = !jr
    ? ''
    : jr.state === 'resolved'
      ? '; judgment resolver spawned: ready'
      : jr.state === 'failed'
        ? `; judgment resolver spawned: failed: ${firstLine(jr.cause)}`
        : `; judgment resolver not attempted: ${firstLine(jr.reason)}`
  return `${op}; prep-gate enricher ${enricher}${resolver}`
}

function prepGateLine(batonId) {
  const r = prepGateById.get(batonId)
  if (!r) return null
  const repaired = (r.repaired || []).length ? ` repaired: ${r.repaired.join('; ')}` : ''
  const covRepaired = (r.coverageRepaired || []).length ? ` coverageRepaired: ${r.coverageRepaired.join('; ')}` : ''
  const report = r.after !== 'PREPPED' && r.gateReport ? `\n      gate report: ${r.gateReport}` : ''
  return `${r.before} -> ${r.after}${repaired}${covRepaired}${report}`
}

// Phase 6 — the per-baton trail, attached to each verdict entry as `trail`.
const trailById = new Map(fireChains.map((chain) => {
    const { decision, baton, plan, reviews, premiseCheckVerdict, checkersSkipped, substitutions } = chain
    // Each reviewer with its OWN verdict: a collapsed "the review said X" loses the dissenter.
    const verdicts = reviews.map((r) => `${r.reviewer}=${r.verdict}`).join(', ') || 'none ran'
    // "Ran and found nothing", "checked nothing" and "did not run" must render as different states.
    const premiseCheckLine = premiseCheckVerdict
      ? `${premiseCheckVerdict.verdict}${premiseCheckVerdict.citationsChecked === 0 ? ' (0 citations examined — UNATTEMPTED, not a clean pass)' : ''}${(premiseCheckVerdict.blockingCitations || []).length ? ` blocking: ${premiseCheckVerdict.blockingCitations.join('; ')}` : ''}${premiseCheckVerdict.pivotCandidates ? ` pivot candidates (a reviewer's call, not a route): ${premiseCheckVerdict.pivotCandidates}` : ''}`
      : checkersSkipped
        ? `skipped: ${decision.tshirt} below L — the premise check fires at L and above only; citations UNCHECKED, not clean`
        : 'DID NOT RUN — no premise-check verdict reached the trail for this baton'
    const pivots = reviews.filter((r) => r.pivot)
    const blockers = reviews.filter((r) => r.verdict === 'BLOCKED')
    // A mixed set is named: a reader seeing one PIVOT stops reading, and the co-reviewer's findings
    // go unread.
    const mixed = pivots.length && reviews.length > pivots.length
      ? `\n      MIXED SET: ${pivots.map((r) => r.reviewer).join(', ')} pivoted; `
        + `${reviews.filter((r) => !r.pivot).map((r) => `${r.reviewer}=${r.verdict}`).join(', ')} did not. `
        + `Both survive — the pivot decides the ROUTE, the rest are the replan's inputs.`
      : ''
    const aliases = reviews.filter((r) => r.aliased)
    return [baton.id, `  - ${baton.id} "${baton.title}" [${decision.tshirt}, ${decision.route}]
      plan: ${plan ? plan.planPath : '(not written)'}${plan && plan.status === 'blocked' ? ` — BLOCKED: ${plan.blockedReason}` : ''}${plan && plan.planPathCorrected ? `\n      planPath CORRECTED: planner returned ${plan.planPathCorrected} (a trail sidecar); the baton's own plan path was used instead` : ''}${substitutions && substitutions.length ? `\n      reviewer substitution: ${substitutions.join('; ')}  <-- the plan was NOT reviewed by whom the em named` : ''}${chain.reviewNote ? `\n      review path: ${chain.reviewNote}` : ''}${chain.chattyWave ? '\n      review path: one chatty wave (concurrent reviewers; a dedicated host ran the readiness op)' : ''}${chain.parallelWave ? '\n      review path: one parallel wave (each reviewer applied its own findings), a post-wave ledger verify, a dedicated host ran the readiness op' : ''}
      premise-check: ${premiseCheckLine}
      reviews: ${verdicts}${pivots.length ? `  <-- PIVOT (${pivots.map((r) => r.reviewer).join(', ')})` : ''}${blockers.length && !pivots.length ? `  <-- BLOCKED, held by ${blockers.map((r) => r.heldBy || 'unnamed').join(', ')}` : ''}${mixed}${aliases.length ? `\n      alias resolved: ${aliases.map((r) => `${r.reviewer}: ${r.aliased}`).join('; ')}` : ''}
      ${reviews.map((r) => `sidecar: ${r.sidecarPath}${r.premiseFailure ? ` premise-failure: ${r.premiseFailure}` : ''}${r.alternativesConsidered ? ` alternatives: ${r.alternativesConsidered}` : ''}`).join('\n      ')}
      premise rows: ${premiseLines(standingPremise(chain)).split('\n').join('\n      ')}
      readiness op: ${readinessOpLine(chain)}${chain.readyOpError ? `\n      readyOp error: ${chain.readyOpError}` : ''}${chain.readyOpDishonoured ? '\n      readyOp ran on a dishonoured reply' : ''}
      findings ledgers: ${ledgerLine(plan, reviews)}${prepGateLine(baton.id) ? `\n      prep gate (after reviewers, one revise-in-place loop): ${prepGateLine(baton.id)}` : ''}`]
}))

// HOST AVAILABILITY is never a pull reason and is not reconciled here: this script has
// no filesystem primitive to read a plan's `external_gate`, and every reconciliation below makes a
// verdict STRICTER. The op decides it from the plan (THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON).
function pivotReplanBrief(reviews) {
  return `Reconciled from the review set.\n`
    + reviews
      .map((r) => `${r.reviewer} [${r.verdict}]: ${r.premiseFailure
        || (Array.isArray(r.blockingCitations) && r.blockingCitations.length ? `blocking: ${r.blockingCitations.join('; ')}` : '')
        || `${r.findingCount || 0} finding(s), see ${r.sidecarPath}`}${r.alternativesConsidered ? ` | alternatives: ${r.alternativesConsidered}` : ''}`)
      .join('\n')
}

const OP_ERROR_CAP = 4000
function capOpError(error) {
  const text = String(error || '')
  return text.length > OP_ERROR_CAP
    ? `${text.slice(0, OP_ERROR_CAP)}\n[truncated: ${text.length - OP_ERROR_CAP} more chars]`
    : text
}

function opVerdictFor(chain) {
  const { baton, plan, reviews } = chain
  const base = { batonId: baton.id }
  if (!plan || plan.status === 'blocked') {
    return {
      ...base,
      verdict: 'pulled',
      reason: plan ? (plan.blockedReason || 'the planner returned blocked') : 'the planner returned no plan',
    }
  }
  const pivots = reviews.filter((r) => r.pivot)
  if (pivots.length) {
    const who = pivots.map((r) => r.reviewer).join(', ')
    return { ...base, verdict: 'replan', reason: `${who} returned PIVOT`, replanBrief: pivotReplanBrief(reviews) + (chain.chattyWave ? '\nThe plan is peer-edited: concurrent reviewers may have applied edits before the PIVOT landed, and nothing reverts them.' : '') }
  }
  const standing = standingById.get(baton.id)
  if (standing && standing.verdict === 'errored') {
    return {
      ...base,
      verdict: 'errored',
      reason: 'plan.readiness_verdict failed after one in-wave retry; the review set is preserved',
      opError: capOpError(standing.error),
      opErrorStage: standing.stage,
      readinessAttempts: standing.attempts,
      readinessParams: standing.params,
    }
  }
  if (!standing) {
    if (chain.readinessParams && !chain.readinessReply) {
      return {
        ...base,
        verdict: 'errored',
        reason: 'no usable plan.readiness_verdict reply stood for this plan; the review set is preserved for a re-run',
        opError: 'no honoured plan.readiness_verdict reply (absent, input mismatch, or incoherent) and no op error',
        opErrorStage: 'no-usable-reply',
        readinessAttempts: chain.readinessAttempts || 1,
        readinessParams: chain.readinessParams,
      }
    }
    return { ...base, verdict: 'pulled', pullClass: 'unusable', reason: 'no usable plan.readiness_verdict reply stood for this plan' }
  }
  if (standing.verdict === 'ready') {
    const unrepaired = chain.readinessReply && chain.readinessReply.mechanical_repairs.length === 0
    const resolverFinal = standing.judgmentResolve && standing.judgmentResolve.state === 'resolved'
      && !premiseRecheckById.has(baton.id)
    const readyOpSource = resolverFinal
      ? judgmentResolveById.get(baton.id)
      : (unrepaired ? chain : prepGateById.get(baton.id))
    return {
      ...base, verdict: 'ready', reason: standing.reason, pullClass: standing.pullClass,
      ...(standing.judgmentResolve ? { judgmentResolve: standing.judgmentResolve } : {}),
      ...readyOpFields(readyOpSource),
    }
  }
  if (standing.verdict === 'judgment') {
    const blocking = standing.blockingFindings || 0
    const advisory = standing.advisoryFindings || 0
    return {
      ...base,
      verdict: 'pulled',
      reason: `${blocking} blocking, ${advisory} advisory: ${standing.reason}`,
      pullClass: standing.pullClass,
      blockingFindings: blocking,
      advisoryFindings: advisory,
      findingCountSource: standing.findingCountSource || 'wave',
      ...(Array.isArray(standing.blocking) ? { blocking: standing.blocking } : {}),
      judgmentResolve: standing.judgmentResolve || { state: 'not-attempted', reason: 'no resolver state reached the verdict' },
    }
  }
  return {
    ...base,
    verdict: 'pulled',
    reason: standing.reason,
    pullClass: standing.pullClass,
    ...(Array.isArray(standing.blocking) ? { blocking: standing.blocking } : {}),
    ...(standing.verdict === 'pulled' ? { prepGateReport: standing.message || null } : {}),
  }
}


// WAVE RESULT: the caller stamps `ready` to `approved`, mints a baton per `replan`, and re-queues
// every `pulled`.
const routeById = new Map(decisions.map((d) => [d.batonId, d.route]))
const reviewsById = new Map(chains.filter(Boolean).map(({ baton, reviews }) => [baton.id, reviews]))
const premiseById = new Map(
  chains.filter(Boolean).map((chain) => [chain.baton.id, standingPremise(chain)]),
)
// `ran` and `planWritten` are two different silences (no plan to review vs a review pass missing
// over a plan that exists).
const reviewedById = new Map(
  chains.filter(Boolean).map(({ baton, plan, reviews }) => [baton.id, {
    ran: (reviews || []).some((r) => r.reviewer !== PREMISE_REVIEWER),
    planWritten: Boolean(plan && plan.status !== 'blocked'),
  }]),
)

// The plan this fire authored, per baton: `roadmap.blitz_land` refuses a plan-carrying row without it.
const planPathById = new Map(
  chains
    .filter(Boolean)
    .map(({ baton, plan }) => [baton.id, (plan && plan.planPath) || baton.planPath || null])
    .filter(([, p]) => p),
)

const coverageById = new Map(fireChains.map((c) => [c.baton.id, coverageForOp(c.coverage)]))
const opReviewsById = new Map(fireChains.map((c) => [c.baton.id, c.opReviews || []]))

// A reconciled-to-pulled entry carries no readyOpReply (it belongs to a ready entry only).
const notReady = ({ readyOpReply, ...rest }) => rest

const verdicts = fireChains
  .map(opVerdictFor)
  .map((v) => {
  const reviews = reviewsById.get(v.batonId) || []
  const entry = {
    ...v,
    route: routeById.get(v.batonId) || null,
    trail: trailById.get(v.batonId) || null,
    // Repo-relative whatever spelling the planner echoed: a host path is committed state.
    planPath: repoRelativeCitation(planPathById.get(v.batonId)) || null,
    // Carried so the LANDING can refuse a pivoted plan independently (two enforcement points).
    reviewVerdicts: reviews.map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
    // The op's own param shapes, so a revise block passes them straight back to plan.readiness_verdict.
    coverage: coverageById.get(v.batonId) || null,
    reviews: opReviewsById.get(v.batonId) || [],
    premise: premiseForOp(premiseById.get(v.batonId)),
  }
  // SPINE, reconciled mechanically: a plan with no `plan-tasks` block declares no schedulable
  // work. Measured: an 869-line plan with zero fenced blocks passed every gate, landed `approved`,
  // and was refused a ceremony later with SPINE/spine-absent; the premise pass reports it, here it pulls.
  const premiseRow = premiseById.get(v.batonId)
  if (premiseRow && premiseRow.spinePresent === false && entry.verdict === 'ready') {
    return {
      ...notReady(entry),
      verdict: 'pulled',
      // Names its source so a driver can re-run the one check that produced it.
      spineOverride:
        'The op verdict was ready; the premise check reported plan-spine-check NO-SPINE for this plan. '
        + 'Reconciled to pulled. VERIFY BEFORE ACTING ON IT: re-run plan-spine-check against the '
        + 'plan, and if it reports VALID this override is wrong and the op verdict stood.',
      spinePresentSource: premiseRow.sidecarPath || null,
      reason: `${entry.reason} [reconciled: premise check reported no plan-tasks spine — nothing to schedule]`,
    }
  }

  // REVIEW, reconciled mechanically: a missing review pass is INDISTINGUISHABLE AT THE RETURN from
  // a review that ran and found nothing. A plan never written is not this case (it rides blocked);
  // `planWritten` tells the two apart.
  const reviewRow = reviewedById.get(v.batonId)
  if (reviewRow && reviewRow.planWritten && entry.verdict === 'ready' && !reviewRow.ran) {
    return {
      ...notReady(entry),
      verdict: 'pulled',
      reviewOverride:
        'The op verdict was ready; the plan was written and no reviewer ran over it, so no finding is '
        + 'known to have been applied. Reconciled to pulled.',
      reason: `${entry.reason} [reconciled: no reviewer ran over a plan that exists]`,
    }
  }

  // PREP GATE, reconciled mechanically: only a measured non-PREPPED `after` pulls.
  const prepRow = prepGateById.get(v.batonId)
  if (prepRow && prepRow.after !== 'PREPPED' && entry.verdict === 'ready') {
    return {
      ...notReady(entry),
      verdict: 'pulled',
      prepGateOverride:
        `The op verdict was ready; plan.prep_gate was ${prepRow.before} before and ${prepRow.after} after `
        + 'the one revise-in-place loop. Reconciled to pulled.',
      prepGateReport: prepRow.gateReport || null,
      reason: `${entry.reason} [reconciled: prep gate ${prepRow.after} after revise — ${prepRow.gateReport || 'see gate report'}]`,
    }
  }

  return entry
})

// Phase 7 — Adjudicate: nothing reaches the PM without a ruling. ONE sonnet call rules every
// PM-bound entry of the wave. Trap: a per-entry persona agent re-pays the full boot (CLAUDE.md,
// role, repo read) on every entry, and a wave of Opus adjudicators costs more than the wave's
// plans. A plan-weight matter is not ruled here; it is spun out as its own baton.
const ADJUDICATOR = 'general-purpose'

// An entry naming an irreversible or external-facing gate stays `pm_only` whatever the ruling.
const IRREVERSIBLE_GATE = /\b(merge[ds]? (to|into) main|push(ed|ing)? to main|force-push|publish(ed|ing)?|release|cross-repo commit|branch deletion|history rewrite|rewrite history)\b/i

const ADJUDICATION_BATCH_SCHEMA = {
  type: 'object',
  required: ['rulings', 'sidecarPath', 'tldr'],
  properties: {
    rulings: { type: 'array', items: ADJUDICATION_SCHEMA },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// Resolves to Map<batonId, { agentType, verdict, error }>. An entry the batch omits, or a batch
// that throws, gets verdict null, which fails closed in settleAdjudication.
async function adjudicateAll(pmBound) {
  if (!pmBound.length) return new Map()
  const matters = pmBound.map(({ entry, kind }) => {
    const baton = batonFor(entry)
    const question = entry.surfacedQuestion || entry.rationale || entry.reason || '(no question stated)'
    return `- Baton: ${entry.batonId}${baton ? ` — "${baton.title}" (${baton.path})` : ''}
  Route: ${entry.route}   Size: ${entry.tshirt}   Surfaced as: ${kind}
  Question: ${question}
  Blitz-em rationale: ${entry.rationale || '(none)'}`
  }).join('\n')
  let rulings = []
  let error = null
  try {
    const v = await trackAgent('adjudicator:wave', agent(
      `phase: adjudicate

You are the PM's delegate for this plan-blitz wave's PM-bound matters. Nobody escalates to the
human here. Rule each one; do not re-ask it. Keep it brief: read only what a matter cites.

${matters}

For each matter:
  1. Decide the question with what is on disk.
  2. Write one line on the baton record: \`pm_ruling: "apm (PM-delegated) <your ruling>"\`.
  3. Return a rulings[] entry with its batonId, verdict 'ruled' and pmOnly false.

A matter that needs a plan of its own to answer is plan-weight: rule "spin out as its own baton"
and do not work it here. Return pmOnly true (verdict 'pm-only', with pmOnlyGround) ONLY when the
matter is important AND urgent AND has no clear right answer, or needs an external or irreversible
action (merge, publish, push to main, cross-repo commit assent). Being unsure is not a ground.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, `wave-${waveIndex}`, 'pm-adjudication'))}`,
      { model: 'sonnet', ...withRole(ADJUDICATOR),
        label: 'adjudicate:wave',
        phase: 'Adjudicate',
        schema: ADJUDICATION_BATCH_SCHEMA,
      },
    ))
    rulings = (v && Array.isArray(v.rulings)) ? v.rulings : []
  } catch (err) {
    error = String((err && (err.message || err.error)) || err).slice(0, 500)
  }
  const byId = new Map(rulings.map((r) => [r.batonId, r]))
  return new Map(pmBound.map(({ entry }) => [entry.batonId, {
    agentType: ADJUDICATOR,
    verdict: byId.get(entry.batonId) || null,
    error: byId.has(entry.batonId) ? null : (error || 'no ruling returned for this baton'),
  }]))
}

// A missing verdict fails closed (stays PM-bound as `unavailable`); an irreversible gate overrides
// any adjudicator ruling.
function settleAdjudication(entry, outcome) {
  const v = outcome.verdict
  const text = [entry.surfacedQuestion, entry.rationale, entry.reason, v && v.ruling].join(' ')
  const gated = IRREVERSIBLE_GATE.test(text)
  const pmOnly = !v || v.pmOnly === true || gated
  return {
    ...entry,
    adjudication: {
      adjudicator: outcome.agentType,
      verdict: v ? v.verdict : 'unavailable',
      ...(!v && outcome.error ? { error: outcome.error } : {}),
      pmOnly,
      ...(v && v.pmOnlyGround ? { pmOnlyGround: v.pmOnlyGround } : {}),
      ...(gated && !(v && v.pmOnly === true) ? { pmOnlyGround: 'external-or-irreversible' } : {}),
      ruling: v ? v.ruling : null,
      sidecarPath: v ? v.sidecarPath : null,
    },
  }
}

const pmBound = [
  ...surfacedToPm.map((d) => ({ entry: d, kind: 'surfacedToPm' })),
  ...routedElsewhere.filter((r) => r.route === 'pm-decision').map((r) => ({ entry: r, kind: 'routedElsewhere' })),
]
const outcomes = await adjudicateAll(pmBound)
const settled = pmBound.map(({ entry, kind }) => ({
  kind,
  entry: settleAdjudication(entry, outcomes.get(entry.batonId)),
}))
const settledIds = new Set(settled.map((x) => x.entry.batonId))
const residueSurfacedToPm = settled.filter((x) => x.entry.adjudication.pmOnly).map((x) => x.entry)
const adjudicated = settled.filter((x) => !x.entry.adjudication.pmOnly).map((x) => x.entry)
const residueRoutedElsewhere = routedElsewhere.filter((r) => !settledIds.has(r.batonId))

return {
  waveIndex,
  trailDir,
  // Echoed verbatim from the emitter's stamp (a fire is a frozen copy of this file); absence is
  // not an error.
  ...(parsedArgs.engineRef ? { engineRef: parsedArgs.engineRef } : {}),
  // Declared from the incident log, never inferred from empty lanes; the landing refuses on
  // a declared incomplete wave.
  ...(agentIncidents.length
    ? {
      completed: false,
      agentErrors: agentIncidents.length,
      incompleteReason:
        `${agentIncidents.length} agent(s) did not complete: `
        + agentIncidents.map((i) => `${i.role} (${i.kind})`).join(', ')
        + '. Every lane below is a PARTIAL result, and a verdict in it may have been reached '
        + 'without the pass that would have changed it — an integration that never ran reads '
        + 'exactly like an integration that found nothing. Re-run or resume before landing.',
      agentIncidents,
    }
    : {}),
  // The trail is shared, so the caller needs this fire's own leaf.
  trailSlotDir: `${trailDir}/${waveSlot}`,
  ready: verdicts.filter((v) => v.verdict === 'ready'),
  pulled: verdicts.filter((v) => v.verdict === 'pulled'),
  replan: verdicts.filter((v) => v.verdict === 'replan'),
  // The op failed after one retry; the landing re-runs only the op over each entry's params.
  errored: verdicts.filter((v) => v.verdict === 'errored'),
  // PM residue only: `pm_only` entries (or naming an irreversible gate, or no adjudicator verdict).
  surfacedToPm: residueSurfacedToPm,
  // PM-bound entries an adjudicator ruled on; nothing re-asks them.
  adjudicated,
  // Later decisions for an already-decided baton, dropped before planning or dispatch.
  duplicateDecisions,
  // Plannable batons with no sizing object. Top-level because the refusal otherwise arrives a
  // stage late.
  sizingObjectAbsences: decisions
    .filter((d) => d && !d.sizingObject && PLANNABLE_ROUTES.has(String(d.route)))
    .map((d) => ({
      batonId: d.batonId,
      route: d.route,
      // An unstated reason is itself the finding.
      reason: d.sizingObjectAbsence || '(NOT STATED — the em returned a bare null on a plannable '
        + 'route, so it is unknown whether no sizing was owed or a scaffold was refused)',
    })),
  // Always empty (this wave executes no XS); kept so old and new results share keys.
  dispatched: [],
  // Execution-open, sized XS batons for the driver: { batonId, record, sizingObject, deliverableId }.
  xsRuns,
  // Neither planned nor handed off as an XS run; each names the room it belongs in.
  routedElsewhere: residueRoutedElsewhere,
  // Sidecar paths with no `subagent-share` segment: their ledgers cannot verify, and nothing else says so.
  unreachableSidecars,
  // Sidecars whose holder segment disagrees with the rest of the fire (a mistyped agent path).
  divergentSidecars: divergentSidecarHolders(),
  // Single-plan mode's `kind: plan` wake digest; wave mode assembles none.
  ...(SINGLE_MODE
    ? {
      digest: planDigest({
        verdict: (verdicts[0] && verdicts[0].verdict) || 'surfaced',
        reviews: reviewsById.get(batons[0].id) || [],
        premiseCheckVerdict: resolveVerdict(
          premiseAsReview(
            batons[0], premiseById.get(batons[0].id),
            (fireChains.find((c) => c.baton.id === batons[0].id) || {}).readinessReply,
          ) || {},
        ),
        surfacedQuestion:
          (surfacedToPm.find((d) => d.batonId === batons[0].id) || {}).surfacedQuestion || null,
        planPath: planPathById.get(batons[0].id) || null,
        deliverableId: batons[0].deliverableId || null,
        exitCriterionStatement: batons[0].exitCriterion || null,
        sizingObject: batons[0].sizingObject || null,
        batonId: batons[0].id,
        opError: (verdicts[0] && verdicts[0].opError) || null,
      }),
    }
    : {}),
}
