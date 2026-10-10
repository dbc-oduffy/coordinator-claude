/*
 * plan-blitz — background-Workflow encoding of ONE planning wave.
 *
 * Spec backlink: coordinator/skills/plan-blitz/SKILL.md. Doctrine and argument:
 * coordinator/docs/wiki/plan-blitz.md. This script is the skill's DISPATCH VEHICLE — the skill
 * remains the source of truth for the contract, and hand-orchestrating the wave is the fallback
 * for when this refuses, not a parallel path of equal standing.
 *
 * WHAT ONE RUN COVERS: exactly one planning wave, as computed by claude-klabauter's
 * `roadmap.plan_gate` op. The caller resolves the wave, freezes the gate report to disk, and
 * invokes this script with that wave's batons. Wave N+1 is a SEPARATE invocation, fired after
 * wave N's plans reach `approved` — because that approval is what opens wave N+1's planning
 * gates (tripwire: A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE). One script per wave, deliberately:
 * a script spanning all waves would have to re-read disk mid-run to learn whether the previous
 * wave's plans were approved, and a Workflow script has no filesystem primitive to do it with.
 *
 * Negative-spec — what this is NOT:
 *   - NOT a roadmap author. Batons arrive from /roadmap-planning; this consumes a graph.
 *   - NOT an executor. It stops at "ready to execute". Execution is /execute-plan, governed by
 *     the EXECUTION gate, which this wave never opens.
 *   - NOT the gate resolver. It does not derive planning waves, does not read `blocked_by`, and
 *     does not decide which batons are eligible — `roadmap.plan_gate` did all of that before
 *     this script was invoked, and its frozen report is an INPUT.
 *   - NOT the PM. `route: pm-decision` and XL exits go to an adjudicator agent (APM for scope,
 *     direction and priority; staff-eng or the domain reviewer for code); only a `pm_only` ruling
 *     stays in `surfacedToPm`, the rest are reported in `adjudicated`.
 *   - NOT a place where the EM gates mid-wave. Review and integration fire unconditionally; the
 *     EM's only gate is terminal (tripwire: A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ).
 *
 * args contract:
 *   {
 *     repoRoot: string,       // ABSOLUTE path to the repo this wave plans for. REQUIRED, and
 *                             //  refused when absent. Every brief anchors its repo-relative
 *                             //  paths here. Without it an agent resolves them against whatever
 *                             //  directory the DRIVER'S SHELL happened to hold when it spawned,
 *                             //  which is not necessarily this repo and on a fresh cloud
 *                             //  container is not a repo at all. The failure is silent in the
 *                             //  worst place: a hand-authored plan lands under another tree, the
 *                             //  wave reports it written, and the gate never sees a file to read.
 *     waveIndex: number,      // which planning wave this run covers; 0 is the ungated wave.
 *                             //  Carried into every brief so a sidecar names its own wave.
 *     trailDir: string,       // ABSOLUTE, e.g. "/abs/repo/state/plan-blitz/20260905T120000Z"
 *                             //  — the durable trail. Absolute for the reason repoRoot is:
 *                             //  an agent resolving a repo-relative trail path against its own
 *                             //  spawn directory writes the sidecar somewhere else and reports
 *                             //  it written.
 *                             //  Every agent writes its sidecar HERE, and the EM's readiness
 *                             //  gate reads them from disk. Caller scaffolds it before firing;
 *                             //  this script has no fs primitive of its own.
 *     provisionSidecarCli: string, // REQUIRED, and the wave refuses when it is absent. Same
 *                             //  rung as every other coordinator CLI this file names: a reviewer
 *                             //  with no resolver writes a real review to an invented path and
 *                             //  the wave reports success anyway.
 *                             //  The resolved absolute invocation of `provision-sidecar`, which
 *                             //  exists precisely for "a vehicle that does not traverse the
 *                             //  spawn-time provisioning hook (e.g. a Workflow script's agent()
 *                             //  call)" — this one. Without it a reviewer brief can only name
 *                             //  `<machinery_root>/subagent-share/<session>/` as a PLACEHOLDER,
 *                             //  and a reviewer has no way to resolve `<machinery_root>` from
 *                             //  inside its own dispatch. It invents one. The invented path is
 *                             //  plausible and wrong — measured 2026-09-10: three sidecars in one
 *                             //  wave landed under a `.subagent-share/` directory created at the
 *                             //  REPO ROOT, where the disposition op refuses them (no
 *                             //  `subagent-share` path segment of the shape it checks) and where
 *                             //  nothing else looks. The review still ran; only its disposition
 *                             //  record was lost, silently, which is this op's whole failure mode.
 *     spineCheckCli: string,  // OPTIONAL. Resolved absolute invocation of `plan-spine-check`,
 *                             //  which is PLUGIN-LOCAL — it ships in the coordinator plugin's own
 *                             //  bin/, never in the repo being planned. The brief that calls it
 *                             //  "a runnable check, not advice" interpolated `<repoRoot>/`, so it
 *                             //  resolved to nothing in every repo except the plugin's own source
 *                             //  tree and the check had never run anywhere else. Absent, both
 *                             //  briefs say so and name it a caller defect instead of
 *                             //  substituting a repo-relative guess.
 *     armingCheckCli: string, // OPTIONAL, same rung. `instrument-can-report-red`, cited worse — a
 *                             //  BARE RELATIVE path, resolving against the planner's cwd. The
 *                             //  falsifier-arming line then read `N/A`, indistinguishable from a
 *                             //  plan that declared no falsifier, so readiness gates reasoned about
 *                             //  a property of the PLAN that was really a property of the path.
 *     gateReportPath: string, // the frozen `roadmap.plan_gate` JSON this wave was resolved from.
 *                             //  Passed to the blitz-em so its judgment reads the same gate
 *                             //  state the wave was planned against, not a re-derived one.
 *     pluginAgentsAvailable: boolean, // whether `coordinator:*` agent types resolve on this
 *                             //  machine. Defaults FALSE, which is the safe direction: an
 *                             //  unresolvable agentType does not fail the dispatch, it yields
 *                             //  a generic agent wearing that role's LABEL, and nothing
 *                             //  reports the substitution. Omitting it on a machine that HAS
 *                             //  the plugin costs every persona in the wave and says so
 *                             //  nowhere. Full argument at § Role resolution below.
 *     engineRef: {            // OPTIONAL, emitter-stamped. What code this fire is a frozen copy
 *       repoRoot,             //  of: the CHECKOUT it came from, this file's resolved path, repo
 *       workflowPath,         //  HEAD, a sha1 over its own bytes, and whether those bytes were
 *       head, workflowSha,    //  uncommitted. The tree is carried because a sha from another
 *       dirty, reason,        //  checkout is INCOMPARABLE, not merely different — the doctrine
 *     },                      //  and published-engine planes each hold files the other lacks.
 *                             //  Echoed into the wave result and read by nothing here. A fire
 *                             //  binds its args into a STANDALONE
 *                             //  script, so a wave fired an hour ago runs the workflow as it
 *                             //  stood an hour ago; without this, two waves of one run can
 *                             //  differ with nothing about the batons changing and no result
 *                             //  saying which code ran. Absent on a fire emitted before the
 *                             //  field existed — which is itself the version signal.
 *     batons: [ {
 *       id: string,           // stub_id or handoff_id — the id `blocked_by` edges name it by
 *       path: string,         // repo-relative path to the baton record
 *       title: string,
 *       sized: boolean,       // true when the baton already cites a sizing-object. A sized
 *                             //  baton SKIPS the scout (its size was decided upstream) but
 *                             //  still passes through the blitz-em, which may revise it.
 *       planPath: string|null,// an existing plan, when the baton already has one. Non-null
 *                             //  means this wave REVISES rather than authors.
 *       executionOpen: boolean// REQUIRED, from `roadmap.plan_gate`'s `execution_gate.open`
 *                             //  for this baton. An XS may be DONE in this wave only when
 *                             //  its EXECUTION gate is open — blockers coded, not merely
 *                             //  planned. Omit it and every XS fails the `=== true` test,
 *                             //  so none dispatches, none is closed at the landing, and
 *                             //  each returns as a candidate in the next wave's gate read.
 *                             //  That is the recycling defect, and it is silent: the wave
 *                             //  still reports the batons under `routedElsewhere`.
 *     } ]
 *   }
 *
 * REPAIR MODE IS RETIRED — plan-blitz has no `mode: 'repair'` invocation shape any more. A
 * plan whose review ran but whose ledger does not verify is re-fired as a targeted wave over
 * the args contract above, the same as any other unfinished plan.
 *
 * Invocation — every field below is present because a caller COPIES this block. An example
 * that omits a required field teaches the omission, which is how `executionOpen` reached a
 * live wave missing (see the args contract's own note on the recycling defect). The
 * scriptPath is `${CLAUDE_PLUGIN_ROOT}`-resolved rather than repo-relative for the same
 * reason: a `coordinator/workflows/...` prefix resolves only under the DoE source tree and
 * elsewhere fails as a MISSING FILE, which reads as "the vehicle does not exist" — tripwire
 * A-MISSING-WORKFLOW-SCRIPT-IS-AN-UNRESOLVED-PLUGIN-ROOT, whose discharge is this line.
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
 * Returns: { waveIndex, ready, pulled, replan, surfacedToPm, adjudicated, trailDir }
 * (`surfacedToPm` is the PM residue: only entries an adjudicator marked `pm_only`, each carrying
 * its `adjudication`; `adjudicated` holds the PM-bound entries an adjudicator ruled on.) — see WAVE RESULT below.
 */

// `phases` is a DECLARATION LIST, not the schedule. Its order is what a reader sees in the run's
// progress; what actually orders a phase is the data it consumes. A phase inserted or moved here
// changes the display and nothing else -- the contract test asserts set-equality both directions,
// never position.
//
// No apostrophe in a `detail` string. The engine's phase-title pairing logic pairs quotes
// naively, so one `\'` shifts the pairing and every phase declared after it goes missing from
// what the checker believes was declared -- reported as a WARN about a phase that is right there.
// An even number happens to cancel, which is why this passes until it does not.

export const meta = {
  name: 'plan-blitz',
  description: 'One planning wave: sonnet scouts size the batons, an Opus EM finalises, Opus planners write, a sonnet pass resolves each plan\'s citations against the tree, resolved reviewers run in sequence over each plan applying and verifying their own findings, and the EM gates readiness at the end.',
  phases: [
    { title: 'Size', detail: 'One sonnet sizing-scout per unsized baton — substrate read, touchpoint inventory, prior art, and a proposed t-shirt with its evidence. Skipped for a baton that already cites a sizing-object.' },
    { title: 'Size review', detail: 'One Opus blitz-em over the whole wave. Interrogates every proposed size (revising down by default), finalises the route via sizing-assemble, and emits the per-baton dispatch spec the Plan phase reads.' },
    { title: 'Plan', detail: 'One Opus planner per baton, on every route and at every size — authoring is not a lane the wave economises on. Writes the plan doc through coordinator:plan / scaffold-plan; never hand-authors frontmatter.' },
    { title: 'Premise check', detail: 'One sonnet pass per drafted plan, dispatched once its plan path is trusted and before any reviewer fires. Resolves the load-bearing citations in that plan against the tree — paths, symbols, refs, whether its falsifier can report red, and whether a named thing means what the plan says. It reports per-class ROWS and never a plan-level verdict; the seam after it translates those rows onto REVIEW_SCHEMA so they reach the reviewers that already apply every finding themselves. A premise miss routes BLOCKED; the class-5 rows with no writable fix are NAMED for the reviewers, who own the separating test.' },
    { title: 'Review', detail: 'Reviewers resolved per baton from the EM dispatch spec, never prescribed in the plan file. Fires unconditionally — the EM is not consulted about whether a plan deserves review. Same plan means sequential: each reviewer applies its own findings in place and runs `review-findings-ledger verify` on its own sidecar before the next reviewer starts. A PIVOT/REJECTED verdict applies nothing and suspends every finding under it, with co-reviewer findings still logged.' },
    { title: 'Dispatch', detail: 'One executor per XS/dispatch baton whose EXECUTION gate is open. Runs AFTER planning so the wave plans against a stable tree and the only mutating phase is last. Bounded to the remit the baton itself states — an XS that grows is a sizing defect, not a bigger job.' },
    { title: 'Prep gate', detail: 'One sonnet agent per authored plan, after the reviewers and before the readiness gate. Runs plan.prep_gate, repairs only findings the engine marks mechanical, re-gates exactly once; the re-gate verdict decides, and a plan still NOT-PREPPED is pulled with the gate report attached.' },
    { title: 'Readiness gate', detail: 'One Opus blitz-em over the durable trail. Per plan: ready, pulled, or replan. A PIVOT routes to a replan baton for a later wave rather than halting this one, and is reconciled mechanically rather than left to the gate. Host availability on the executing box is never a pull reason and is stated in the brief, never reconciled: every mechanical reconciliation here makes a verdict stricter, and promoting one would run with the incentive the gate already has rather than against it.' },
    { title: 'Adjudicate', detail: 'One agent per entry that would reach the PM (`surfacedToPm`, `routedElsewhere` with route pm-decision). coordinator:apm rules scope, direction and priority; coordinator:staff-eng (or the domain reviewer the baton calls for) rules code. The adjudicator writes a `pm_ruling:` line on the baton and returns a verdict. Only an entry it marks `pm_only` — important AND urgent AND no clear right answer, or an external or irreversible action — stays in `surfacedToPm`; the rest move to `adjudicated`.' },
  ],
}


// The Workflow tool's `args` input declares no type, so a caller passing a JSON
// object can have it arrive here as the SERIALIZED TEXT of that object. Without the coercion
// below, `parsedArgs.<key>` reads resolve `undefined` against a string, `batons` comes back
// empty, and the run takes the legitimate empty-wave exit: it returns `{ empty: true }` having
// dispatched nothing -- a REAL state the caller is told to RECORD rather than investigate, so
// the fire reads as "nothing left to plan" while every baton in it returns as a candidate in the
// next gate read. Bound under its own name rather than shadowing `args`: a module-scope
// redeclaration of it is a SyntaxError on any host that binds it lexically.
const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  // Separates "the caller built no payload" from "the wave found nothing to do". Both reach the
  // same exit shape otherwise, and only one of them is a defect.
  throw new Error(
    'plan-blitz received no args object (got ' + String(parsedArgs) + '). The caller resolves ' +
    'the wave with roadmap.plan_gate, freezes that report to disk, and passes waveIndex, ' +
    'trailDir, gateReportPath and batons — see the args contract at the top of this file.'
  )
}


// `return-tldr` — pinned by § Pinned interfaces (C1 authors the standalone JSON schema this
// mirrors byte-for-byte; C4 inlines it here as a strict-JSON literal because every `agent()` call
// in this file reads it as a plain JS object, not a file it can `Read`). Re-copy verbatim from
// `coordinator/schemas/return-tldr.schema.json` on edit; do not paraphrase.
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
  required: ['batonId', 'tshirt', 'evidence', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    tshirt: { type: 'string', enum: ['XS', 'S', 'M', 'L', 'XL', 'XXL'] },
    // Free text, deliberately: the blitz-em interrogates the REASONING, and a scout forced into

    evidence: { type: 'string' },
    touchpoints: { type: 'array', items: { type: 'string' } },


    unknownMechanisms: { type: 'array', items: { type: 'string' } },
    priorArt: { type: 'array', items: { type: 'string' } },
    crossTeamDependency: { type: 'string' },
    sidecarPath: { type: 'string' },
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
          reviewers: { type: 'array', items: { type: 'string' } },
          
          
          surfacedToPm: { type: 'boolean' },
          surfacedQuestion: { type: 'string' },
          adjudicatorClass: { type: 'string', enum: ['scope', 'code', 'data-science', 'front-end', 'ux'] },
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


// `UNCHECKABLE` is a first-class row value rather than an omission, because the semantic class


const PREMISE_SCHEMA = {
  type: 'object',
  
  
  required: ['batonId', 'planPath', 'rows', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },


    //: (WORKFLOW-AGENT-AS-FILE-HANDLE). A plan with no spine declares no schedulable work, so

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
        },
      },
    },


    falsifierVerdict: { type: 'string' },
    citationsSkipped: { type: 'integer' },
    sidecarPath: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

//   BLOCKED — "this plan is wrong until you fix these". The DIRECTION holds; the


// It is reached by judging DIRECTION, and `premiseFailure` is the field that carries


// REJECTED is accepted on input and never taught. It is the strongest severity in the
// FLEET-WIDE reviewer enum (`coordinator/agents/staff-eng.md`: APPROVED /
// APPROVED_WITH_NOTES / REQUIRES_CHANGES / REJECTED), so a reviewer carrying that


const REVIEW_SCHEMA = {
  type: 'object',
  required: ['batonId', 'reviewer', 'verdict', 'sidecarPath', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    reviewer: { type: 'string' },
    verdict: { type: 'string', enum: ['OK', 'WARN', 'BLOCKED', 'PIVOT', 'REJECTED'] },
    sidecarPath: { type: 'string' },
    findingCount: { type: 'integer' },

    // where the claim is stated; `resolveVerdict` reads it to resolve the REJECTED

    premiseFailure: { type: 'string' },
    alternativesConsidered: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

const DISPATCH_SCHEMA = {
  type: 'object',
  required: ['batonId', 'completed', 'summary', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    completed: { type: 'boolean' },
    summary: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },


    blockedReason: { type: 'string' },


    priorShippedIn: { type: 'string' },
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
        required: ['batonId', 'verdict', 'reason'],
        properties: {
          batonId: { type: 'string' },
          verdict: { type: 'string', enum: ['ready', 'pulled', 'replan'] },
          reason: { type: 'string' },
          planPath: { type: 'string' },


          replanBrief: { type: 'string' },
        },
      },
    },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// PRE-FLIGHT SCHEMAS — single-plan mode's two pre-flights (§ Pinned interfaces / C4 body item 2).
// Both are report-only checkers (never edit, never refuse): the wave reads their verdict and
// rows the same way it reads a reviewer's, through `planCoverageAsReview` below for the second
// one. Kept loose on purpose, same rung as PREMISE_SCHEMA — an agent whose structured-output call
// is forced into a narrower shape than its own report format degrades its answer to fit the field.
const PREP_GATE_REVISE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'before', 'after', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    before: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    after: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    repaired: { type: 'array', items: { type: 'string' } },
    gateReport: { type: 'string' },
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


// Role resolution — agentType is an ENRICHMENT, never the contract


// NEITHER DIRECTION IS SAFE, and the emitter therefore DETECTS it rather than


// A-WORKFLOW-DISPATCH-WITHOUT-WITHROLE-IS-CONFINED.


const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable === true

function withRole(agentType) {
  return PLUGIN_AGENTS && agentType ? { agentType } : {}
}


// AN OUTAGE DOES NOT MERELY LOSE A WAVE; IT MANUFACTURES VERDICTS. When agents die mid-wave — a


// AN-UNFINISHED-WAVE-IS-NOT-A-WAVE-THAT-OPENED-NOTHING teaches the driver to read failure text at


// same three fires to completion three times and watched the VERDICTS MOVE. One baton was `pulled`


const agentIncidents = []

// Every agent dispatch in this file goes through here. Two failure shapes, both counted: a REJECTED


// that produced nothing — and a NULL RESOLUTION, where the agent ran but its structured-output call


// Rejections are RE-THROWN, never swallowed. Every existing catch and null-guard downstream keeps


// HAIKU FALLBACK (§ Pinned interfaces / C4 body item 6). Every role schema now requires `tldr`,
// so a result missing one is a role that returned a structured payload the schema otherwise
// accepted but skipped the one field nothing downstream computes for it. Rather than refuse the
// whole dispatch over a missing summary, one cheap Haiku pass reads the agent's OWN sidecar (the
// durable record — § TRAIL_RULE / REVIEW_SIDECAR_RULE) and produces a `return-tldr` over it. This
// lives in `trackAgent` because every dispatch in the file already funnels through it, so the
// fallback fires uniformly rather than at whichever call sites remembered to add it.
// The one dispatch in this file NOT wrapped in `trackAgent` — deliberately: `trackAgent` is what
// CALLS this on a missing-tldr incident, and wrapping this call in it too would recurse the moment
// a `return-tldr`-shaped result (verdict/decisions/counts/sidecar, no nested `tldr` field of its
// own) reads as "missing tldr" a second time. A failure here degrades to `tldr: null` on the
// caller's result rather than propagating — a lost summary line, never a lost dispatch.
async function tldrFallback(label, sidecarPath) {
  if (!sidecarPath) return null
  return Promise.resolve(agent(`Read the sidecar this agent already wrote, at exactly this path,
and change nothing about it: ${sidecarPath}

Return ONLY a \`return-tldr\` summary of what it already says: \`verdict\` (its own verdict word,
mapped onto OK/WARN/BLOCKED/PIVOT/FAILED), up to 5 \`decisions\` ({item, anchor}) naming its most
load-bearing findings or calls, \`counts\` of whatever it enumerates, and \`sidecar\` set to the
path above. Do not re-run the check, do not open anything else, and do not edit the sidecar.
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
          detail: 'the agent returned nothing — its structured-output call exhausted its retries',
        })
        return result
      }
      if (typeof result === 'object' && !result.tldr) {
        const fallbackTldr = await tldrFallback(
          label,
          typeof result.sidecarPath === 'string' ? result.sidecarPath : null,
        )
        // A recovered fallback is a lost summary line, never a lost dispatch (see comment above):
        // it must not flip the wave's `completed` to false. Only an unrecoverable fallback (no
        // sidecarPath, or the Haiku pass itself failing) counts as an incident.
        if (fallbackTldr === null) {
          agentIncidents.push({
            role: label,
            kind: 'missing-tldr',
            detail: 'the agent returned no parsable `tldr`, and the Haiku fallback over its sidecar also failed',
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


//   - a baton never ends with zero reviewers — a substitution DEGRADES the


const REVIEWER_ROSTER = new Set([
  'coordinator:staff-eng',
  'coordinator:eng-director',
  'coordinator:overengineering-reviewer',
])

// A plan's own `review_signals` select the domain reviewer; these are reachable only through a
// signal, never named by the size-review EM, so they sit outside REVIEWER_ROSTER. architecture,
// backend and security resolve to the default staff-eng; the vocabulary is single-sourced in
// contract/review-signals.json.
const SIGNAL_REVIEWERS = {
  'data-science': 'coordinator:staff-data-sci',
  'front-end': 'coordinator:senior-front-end',
  'ux-flow': 'coordinator:staff-ux',
  'cross-repo-seam': 'coordinator:eng-director',
}


const REVIEWER_ALIASES = new Map([
  ['patrik', 'coordinator:staff-eng'],
  ['zoli', 'coordinator:eng-director'],
  ['kira', 'coordinator:overengineering-reviewer'],
  ['waste', 'coordinator:overengineering-reviewer'],
])

const DEFAULT_REVIEWER = 'coordinator:staff-eng'

// SINGLE-PLAN REVIEWERS (§ Pinned interfaces). Name mapping only, same as `resolveReviewers`
// below reads any other decision's `reviewers` array — single-plan mode synthesises this instead
// of asking a size-review blitz-em to choose it, since that phase is the one gated off in single
// mode (§ Phase gating).
const SINGLE_PLAN_REVIEWERS = {
  M: ['coordinator:staff-eng', 'coordinator:overengineering-reviewer'],
  L: ['coordinator:staff-eng', 'coordinator:eng-director', 'coordinator:overengineering-reviewer'],
  XL: ['coordinator:staff-eng', 'coordinator:eng-director', 'coordinator:overengineering-reviewer'],
}


const SIGNAL_ROSTER = new Set(Object.values(SIGNAL_REVIEWERS))

function resolveReviewers(named, signals) {
  const signalled = (Array.isArray(signals) ? signals : []).map((sig) => SIGNAL_REVIEWERS[sig]).filter(Boolean)
  const base = Array.isArray(named) && named.length ? named : [DEFAULT_REVIEWER]
  const wanted = [...base, ...signalled]
  const substitutions = []
  const resolved = []

  for (const raw of wanted) {
    const text = String(raw || '').trim()
    if (REVIEWER_ROSTER.has(text) || SIGNAL_ROSTER.has(text)) {
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

// Hand-synced from coordinator/snippets/premise-check-contract.md (C1, classes 1-3),
// coordinator/snippets/premise-check-class-5-semantics.md (C1, class 5 — split out of that
// contract, and this file is its only live consumer) and
// coordinator/snippets/instrument-can-report-red.md (C2) — NOT verify-snippet-sync-governed.
// See tripwire `verify-snippet-sync-has-no-language-awareness.md` for why: this file is a `.mjs`
// paste target the sync tool cannot produce valid output against. Falling back per this chunk's
// stated contingency: a hand-synced module-level constant, kept honest by one containment
// assertion in test_plan_blitz_contract.py, not a sentinel-synced paste. Re-copy verbatim from
// the two `.md` sources on edit; do not paraphrase.
//
// Escaping rule: both source texts contain no `${}` sequence (verified at authoring time), so
// every backtick in the pasted text below is escaped as \` and no other transformation is
// needed. If either source ever grows a `${}` sequence, re-escape it the same way before pasting.
const PREMISE_CHECK_CONTRACT = `## Premise Check Contract

A premise check asks one question, over a plan's cited paths, symbols, refs, and in-repo
behaviour claims: **does this plan's premise actually hold against the tree right now?** (Its
sibling snippet, \`instrument-can-report-red.md\`, asks the companion question for a falsifier
itself: is its verdict wired to its exit path?)
INLINE it into a dispatch brief; never dispatch it as its own agent (an unresolvable \`agentType\`
silently degrades to a generic agent and loses the check).

**Classes 1 and 2 — paths and symbols (mechanical).** For every cited in-repo path: does it
exist? For every cited \`file:line\` / \`file:symbol\` claim: does the symbol exist in that file? This
is the same check plan-coverage-checker's Lens 3 already runs (\`ls\`-check cited paths,
\`Read\`-verify cited claims, grep backtick-quoted in-repo constants) — it is not re-derived here.

**Primitives only — \`ls\`/\`Read\`/\`grep\`, never the symbol-graph tools** (an MCP surface may be
absent where this is inlined, and the index can lag the tree). Rationale:
\`docs/wiki/planning/plan-blitz.md\` § Premise-check instrument choice.

**Tolerance rule, carried over verbatim, do not recalibrate:** same-file line-number drift alone
(same file, same symbol, shifted line number) is tolerated and is NOT a finding; a missing file or
an absent symbol is a real finding.

**AN ABSENCE IS EVIDENCE ONLY IF THE INSTRUMENT COULD HAVE SEEN PRESENCE.** \`find\`, \`ls\`,
\`test -f\` and a failed Read answer the worktree of this box. Before recording an absence the plan
rests on, name what would have made the thing visible and check THAT: a sparse cone hides tracked
paths (\`git ls-files\`), a blobless clone hides contents (\`git show HEAD:<path>\`), \`.gitignore\`
hides build output whose build target is tracked (\`git check-ignore -v\`, then find the build), and
a registry on another machine hides a whole repo (say UNDECIDABLE-HERE and name the host). Record
the command you actually ran. Re-running the author's \`find\` endorses the author's blind spot:
two parties running one wrong instrument agree with each other. Tripwire:
\`AN-ABSENCE-IS-EVIDENCE-ONLY-IF-THE-INSTRUMENT-COULD-HAVE-SEEN-PRESENCE\`.

**Class 3 — refs (mechanical, new).** A cited branch, commit or tag is checked with
\`git branch -r\` / \`git rev-parse --verify\`. A peer-repo ref MUST be cited \`<repo>@<ref>\` — a bare
"verified against HEAD" cannot distinguish \`main\` from someone's unmerged branch, and the failure
is silent in both directions. See tripwire \`VERIFIED-AGAINST-HEAD-DOES-NOT-NAME-A-BRANCH\`.

**Class 5 — semantics (judgment, new).** A claim that code EXISTS is not a claim it BEHAVES as
described. This class fires on either of two conditions:

1. The repo carries a surface that FORBIDS the plan's assumption — a wiki page that says so, or a
   sanctioned resolver that raises instead of defaulting.
2. Defect vocabulary (wrong, broken, fails, silently, unsafely) appears in the plan's description
   of in-repo behaviour — the cheaper, second firing condition.

On either trigger, open the cited symbol and compare its actual behaviour against the plan's claim
before trusting it — a substrate pre-flight verifies existence, not described behaviour, so a
claim that code EXISTS is never treated as a claim it BEHAVES as described. Where NEITHER surface
fires, class 5 degrades to reviewer judgment and the verdict must say so plainly rather than
guessing — this asymmetry is why the pass reports and does not refuse.

**Class 5 is PROVISIONAL.** Classes 1-3 generalize from a measured corpus; class 5's second firing
condition (defect vocabulary) generalizes from ONE incident (2026-07-27: a plan claimed a model
resolver's default was defective when it was in fact a PM-ratified asymmetry, caught only because
a defect-vocabulary trigger like this one would have flagged it for a symbol read). That is
enough to ship it as an acceptance criterion and not enough to call the trigger calibrated. The
mark comes off once a later session has counted enough real firings, in
\`state/audits/2026-09-06-blitz-conversion-re-measurement.md\`'s Arm C table, to say the trigger's
precision — each row sourced from a wave's per-baton \`*.review-premise-check-pointer.md\` pointer
under that wave's trail directory (\`sidecarFor(trailDir, batonId, 'review-premise-check-pointer')\`
in \`plan-blitz.mjs\`).
Until a wave has actually run this check, that table is empty and the PROVISIONAL mark stands —
an empty table is not evidence the trigger is miscalibrated, only that it has not fired yet. Until
the mark comes off, a class-5 finding carries the same weight as any other finding — only the
TRIGGER is under review, not the finding's validity.

**Mechanical vs. judgment split, carried over verbatim.** Classes 1, 2 and 3 are mechanical:
existence either holds or does not. Class 5 is judgment: it requires reading a symbol's actual
behaviour and comparing it to a claim. A verdict that mixes the two without labeling which is
which loses the distinction that lets a reader gauge rework altitude at a glance.

**Reporting, never refusing.** State plainly, in every verdict, which class(es) were checked and
what was found — name the check in words (path, symbol, ref, semantic, instrument), never a bare
class number: a number alone reads as more precise than the taxonomy underneath it actually is.
**A premise check never claims plan correctness.** It catches a class of false premise; a plan
whose every citation resolves against the tree can still be wrong. This pass reports what it
checked and what it found; it does not ratify the plan, and it does not refuse to report a partial
or degraded result — a semantic-check miss with no forbidding surface and no defect vocabulary is
reported as "semantic check not applicable, degrades to reviewer judgment," not withheld.`

const INSTRUMENT_CAN_REPORT_RED_CONTRACT = `## Can This Instrument Report Red?

One check, over any falsifier, gate, or verification instrument: **is the instrument's verdict
wired to its exit path, or only computed?**

The tell, stated without reference to what a given falsifier is *for*: a verdict variable is
computed somewhere in the instrument, but the code path that decides pass/fail — the exit code,
the return value, the raised exception — does not read it. An instrument that cannot fail this way
cannot report red under any input, which makes every green result from it unfalsifiable rather
than earned.

Trace it concretely: find where the verdict is computed, then find every path out of the
instrument (return statements, \`sys.exit\` calls, thrown exceptions, a CI step's exit code) and
confirm at least one of them branches on that verdict. A verdict computed and then logged, stored,
or discarded without ever gating an exit path fails this check regardless of how sound the
computation itself is.

Two sightings motivate this as a standing check, not a one-off: \`inst-07\` injects a token into its
own fixture and reports green regardless of the injection outcome; example-game-repo's release-gates
falsifier computes a shim verdict it never feeds into its exit code. Both are the same tell — a
computed-but-unwired verdict — not two different defects.`

const ROLE_CONTRACTS = {
  'blitz-em': `You are the blitz-em: the engineering-manager judgment inside one plan-blitz wave.
You size and route and gate; you never execute, never author roadmap batons, and never resolve a
decision that belongs to the PM. Your characteristic move when reviewing a size is revising DOWN —
a scout reading unfamiliar substrate reads large, counting touchpoints as depth. Revising UP is the
signal that matters most and requires you to NAME the mechanism the scout missed.`,

  'reviewer': `You are a staff-level reviewer with exacting standards. Assume defects exist — a
review finding none is almost certainly incomplete. Hold LLM-assisted work to a HIGHER bar. Your
lenses: correctness, scope honesty, sequencing, testability, and whether any premise the artifact
rests on is actually true of this tree right now. Apply every finding you log yourself, in place,
in the artifact under review — filtering does not happen upstream any more, and there is no
one behind you to apply what you found. You are UNCONDITIONAL on verdict: an OK does not
skip applying. Never write attribution ("Review: <you>", a finding number, your name) into the
reviewed artifact — the findings ledger in your own sidecar is the attribution record.`,

  // Single-plan mode's two pre-flights (§ Pinned interfaces / C4 body item 2). `withRole` attaches
  // no `agentType` when `pluginAgentsAvailable` is false, and without an inlined contract HERE the
  // dispatch degrades to a generic agent with nothing telling it what a prior-art or coverage
  // check even is — the role's protocol has to travel WITH the brief, not be named and left
  // unread.
  'prior-art-checker': `You are the prior-art-checker pre-flight for single-plan mode. Read
\`agents/prior-art-checker.md\` in full and follow its protocol exactly — this line names your
role, it does not restate the protocol. You are a recall agent, not a reviewer: cross-reference the
sizing intent's claims against wikis, decisions and lessons, and report Conflict /
Compatible-but-relevant / Silent per its § Verification Protocol. You never edit the plan, never
refuse it, and never judge architecture — report, and let the planner and reviewers act on it.`,

  'plan-coverage-checker': `You are the plan-coverage-checker pre-flight for single-plan mode. Read
\`agents/plan-coverage-checker.md\` in full and follow its protocol exactly — this line names your
role, it does not restate the eight lenses. Every lens is report-only: no inline plan edits, no
auto-fix, no auto-block — the EM and reviewers own every disposition. Report clean if clean; a
review finding none is not itself suspicious the way an under-inspected human review would be,
because your checks are mechanical.`,
}


// Sidecar paths are ASSIGNED, never chosen. Two reviewers on the same baton pick


const slug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

// A ROLE NAME IS PART OF THE CONTRACT, not a label. The planner's sidecar role was


// warning anywhere. Measured on run 20260910T113045Z over project-rag-ue-addon: `cpr-23` and


// DIRECTORY discriminates. That is deliberate: `skills/plan-blitz/recycle-check.py` is the one


const sidecarFor = (trailDir, batonId, role) => `${trailDir}/${waveSlot}/${slug(batonId)}.${slug(role)}.md`

// A FINDINGS SIDECAR IS THE AGENT'S OWN PROVISIONED ONE — `provision-sidecar` resolves it, not
// this script and not the agent — but the ONE fact about it the wave can check is checkable here:
// `review-findings-ledger` refuses any target without `subagent-share` as a whole path
// segment, so a returned path lacking that segment is a review whose ledger can never be
// verified. That is the quiet failure: the review runs, and only the record is lost. Measured
// 2026-09-10 — a reviewer that resolved its own root wrote to a plausible `.subagent-share/` at
// the repo root, and the refusal surfaced after the review had already run. Reported as a wave
// finding rather than repaired: this script has no filesystem primitive, so it can check the
// SHAPE of what came back and nothing else.
const unreachableSidecars = []
// A RETURNED PATH IS A CLAIM, NOT A LOCATION, and the next agent is told to open it verbatim.
// Measured by claude-klabauter-80 on their run: a premise-checker returned its own sidecar under
// session `...-8ded-430d-8ecd-df045a9efa22` where the live session is `...-8ebd-...` — one
// transposed character, in the agent's own structured result. The readiness gate opened a
// directory that does not exist, found three other plans' premise-checks beside it, and
// correctly refused to invent a verdict. Nothing anywhere said the path was wrong: the review
// ran, the file existed, and only the record was lost — the same quiet failure the segment check
// above catches a different cause of.
//
// This script has no filesystem primitive, so it cannot ask whether a path exists. It does not
// need one: every provisioned sidecar in one fire sits under the SAME session directory, so the
// holder segment is checkable against its own peers. Eleven agreeing spellings and one outlier is
// a typo, and that is decidable from the returned strings alone.
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

// The minority spellings of the holder segment, or `[]`. Deliberately silent on a fire whose
// sidecars all agree and on one with no majority to be an outlier of: a two-sidecar disagreement
// names no culprit, and guessing one costs more than the miss.
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

// ---------------------------------------------------------------------------
// Verdict resolution — one place, and it reports rather than applies silently
// ---------------------------------------------------------------------------
//
// An inbound verdict word becomes a wave ROUTE here, once. The returned object keeps
// the reviewer's own word in `raw` alongside the resolved `verdict`, so nothing
// downstream has to trust that the two are the same.
const PIVOT = 'PIVOT'

function resolveVerdict(review) {
  const raw = String(review.verdict || '').toUpperCase()
  const premise = String(review.premiseFailure || '').trim()
  let verdict = raw
  let aliased = null
  if (raw === 'REJECTED') {
    // Resolved by EVIDENCE, never by the word. Fleet-wide REJECTED means "fundamental
    // issues; not acceptable in its current state" — a severity. PIVOT means "this
    // direction cannot proceed" — a route. A reviewer who stated a premise failure made
    // the direction claim and earns the pivot; one who did not made a severity claim,
    // and their findings are applied rather than suspended. Mapping the word either way
    // unconditionally would silently upgrade half of these and downgrade the other half.
    verdict = premise ? PIVOT : 'BLOCKED'
    aliased = `REJECTED -> ${verdict} (premiseFailure ${premise ? 'stated' : 'absent'})`
  }
  return { ...review, verdict, raw, aliased, pivot: verdict === PIVOT }
}

const TRAIL_RULE = (sidecarPath) => `
Write your sidecar to EXACTLY this path and return it verbatim as \`sidecarPath\`:

    ${sidecarPath}

Do not choose your own filename. Peers in this wave write beside you, and a name you pick because
it is the obvious one is the same name they pick for the same reason — the later write silently
destroys the earlier, and a lost sidecar is indistinguishable from a review that never ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the EM's readiness gate will never see.`

// A REVIEWER's sidecar cannot live in the trail, and this is not a naming preference.

// A COORDINATOR CLI IS NAMED WITH ITS RESOLUTION, NEVER AS A BAREWORD. This file names


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

// A PLACEHOLDER A DISPATCHED AGENT CANNOT RESOLVE IS A PATH IT WILL INVENT. `<machinery_root>` is


// provision-sidecar refuses a bare identity: a bare reviewer name is qualified here, once.
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

// TWO VOCABULARIES, NOT ONE, and collapsing them into a single parameter was a live defect.
// `provision-sidecar --agent-type` takes an agent IDENTITY and refuses anything not


// _REVIEWER_DOC_TYPE_TOKENS`: "the two vocabularies answer different questions on purpose (agent
// IDENTITY vs. document TYPE) ... never meant to converge on one spelling").


const REVIEW_SIDECAR_RULE = (pointerPath, agentType, docType = agentType) => `
Write your findings sidecar to YOUR OWN PROVISIONED SIDECAR under
\`<machinery_root>/subagent-share/<your session id>/\`, and return its absolute path verbatim as
\`sidecarPath\`.

${PROVISION_CLI_RULE(agentType)}Do NOT write your findings into the wave trail: \`review-findings-ledger\`
refuses any path without \`subagent-share\` as a path segment, and a findings sidecar it cannot
open is a review whose ledger is never recorded.

That sidecar MUST open with YAML frontmatter carrying this key at column zero:

    agent_type: ${docType}

The same op checks the agent type as well as the path, and refuses a sidecar carrying neither an
allowlisted reviewer type nor the \`review-findings\` doc token. The refusal is the quiet one: your
review still runs, but nothing else verifies it applied, and nothing in the wave reports that the
block is missing. Measured 2026-09-10 on a live five-fire wave: 24 of 25 findings sidecars carried
no \`agent_type\` at all, and the whole wave's ledgers went unrecorded.

**The BODY needs one heading, spelled exactly \`## Findings Ledger\`, holding exactly one fenced
\`\`\`json array — one row per finding, per § Contract.** Then write a POINTER file at EXACTLY this
path, containing a SHORT STRUCTURED RECORD as one JSON object and nothing else — not a bare path:

    ${pointerPath}

\`\`\`json
{"sidecarPath": "<the absolute sidecar path above>", "verdict": "<your verdict, exactly as you return it below>", "premiseFailure": "<your premiseFailure verbatim, or null if you did not state one>"}
\`\`\`

The pointer is how the readiness gate finds you. A findings sidecar with no pointer is a review the
gate cannot see, and a pointer with no sidecar is worse — it reads as a review that ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the EM's readiness gate will never see.`

// EVERY BRIEF IS ANCHORED, because nothing else anchors it. A dispatched agent inherits the


const REPO_ROOT =
  typeof parsedArgs.repoRoot === 'string' && parsedArgs.repoRoot.trim()
    ? parsedArgs.repoRoot.trim()
    : null

// THE FINDINGS SIDECAR'S RESOLVER IS THE CALLER'S TO SUPPLY, on the same rung as


// `A-SIDECAR-THE-DISPOSITION-OP-REFUSES-LOSES-ONLY-THE-RECORD`.
const PROVISION_SIDECAR_CLI =
  typeof parsedArgs.provisionSidecarCli === 'string' && parsedArgs.provisionSidecarCli.trim()
    ? parsedArgs.provisionSidecarCli.trim()
    : null

//: `instrument-can-report-red` is PLUGIN-LOCAL like the spine checker below — it ships in the

//: — a BARE RELATIVE path, so it resolved against the planner's cwd, i.e. the repo being planned.


const ARMING_CHECK_CLI =
  (typeof parsedArgs.armingCheckCli === 'string' ? parsedArgs.armingCheckCli : '').trim() ||
  `python3 ${REPO_ROOT || '<repoRoot>'}/coordinator/bin/instrument-can-report-red.py`

// THE SPINE CHECKER LIVES IN THE PLUGIN ROOT, NOT THE REPO BEING PLANNED, and that is why it
// is the caller's to resolve on the same rung as the two CLIs above. Both briefs below used to
// interpolate `${REPO_ROOT}/coordinator/bin/plan-spine-check.py`, which resolves ONLY when the
// repo under plan happens to be coordinator-content-repo — the tree where the plugin root and the repo root
// coincide. Firing the same wave against claude-klabauter made every spine validation a MISSING
// FILE, and a missing file reads as "there is no such check" rather than "the path was not
// resolved", so the plan-author and the reviewer both returned having validated nothing and
// said so about a tool, not about a path. Measured 2026-09-10, claude-klabauter wave 0: a wave
// reported that its plan's task spine "has never been mechanically validated in any pass".
// Tripwire: `A-PLACEHOLDER-A-DISPATCHED-AGENT-CANNOT-RESOLVE-IS-A-CALLER-DEFECT`.
const SPINE_CHECK_CLI =
  typeof parsedArgs.spineCheckCli === 'string' && parsedArgs.spineCheckCli.trim()
    ? parsedArgs.spineCheckCli.trim()
    : null

// The runnable invocation, or an explicit statement that the caller supplied none. Never a
// repo-relative guess: a brief that names a path the agent cannot resolve gets a path the agent
// invents, and an invented spine check that exits non-zero for the wrong reason is worse than a
// declared absence.
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

// THIS SKILL'S EXIT IS THE NEXT CEREMONY'S ENTRY. A wave lands a plan at `approved`, and the
// hands-off run that fires it is gated on `plan.prep_gate` — the mise-prep authoring bar, whose
// four declarations are exactly the judgment calls a driver would otherwise have to ask a human
// about. A plan authored without them is NOT-PREPPED by construction, so every plan a wave
// produces buys a manual repair pass before anything can execute it. Measured on project-rag:
// 323 of 329 plans on disk, 6 PREPPED.
//
// Declaring them is authoring work, not certification work — the bar asks the author what only
// the author knows, and asks it while the plan is being written rather than weeks later from a
// gate verdict. The wave still stamps nothing: `mise_prepped_*` is written by
// `plan.stamp_prepped`, outside this skill, and SKILL.md's "`approved` is not `mise-prepped`"
// rule is unchanged.
const MISE_PREP_RULE = `
FOUR DECLARATIONS, because the next ceremony is gated on them. The plan you write is fired by a
hands-off run with no human in the loop, and its entry gate refuses a plan that leaves any of
these undeclared. "Nothing to declare" is itself a declaration — an EMPTY value is a claim a
reader can check; an ABSENT key is one nobody can see. Declare all four:

  1. \`writes:\` ON EVERY SPINE ROW. The wave-builder decides what can run in parallel from the
     rows' write sets, and cannot decide it for a row that declares none. A row that writes
     nothing declares \`writes: []\`.

  2. \`census:\` IN FRONTMATTER — every COUNTED premise the plan rests on, as
     \`question\` + \`command\` + \`result\`. The command is the point: a count in prose can only
     be believed or not, while a count with the query that produced it can be re-asked of HEAD at
     fire time, which is what an undercount needs in a world where planning runs waves ahead of
     execution. Do not restate the spine's own file count here. A plan resting on no counted
     premise declares \`census: []\`.
     The prep gate refuses any \`command\` outside this form, quoted from the engine: one pipeline of read-only commands (grep, rg, find, ls, wc, sed, awk, jq, git <read>, ...) joined by | && || ; -- \`python <script>\` / \`python -m <module>\` only when the target is a literal git-tracked file of this repo (no $VAR, no glob, no untracked or site-packages target); no \`python -c\`, no \`$( )\` or backticks, no \`for\`/\`while\` loops, no redirect except to /dev/null; a loop over N things is N census entries, or one \`grep -c\`/\`find | wc -l\` over all of them.
     So no \`node -e\`, \`tsx\` or \`pnpm exec\` either: a count that needs a program is a tracked
     read-only script the command names by path.

  3. \`external_gate[].requires:\` ON EVERY UNCLEARED GATE. A blocker owned by another repo is a
     declared gate, never a sentence in the body. \`requires: landed-work\` means wait for them —
     the row is withheld and the plan still certifies. \`requires: commit-in-owner-repo\` means
     write into their tree — a commit dispatched under per-session PM assent, as its own act; that
     row is withheld too and the plan still certifies. The two read identically in prose and are
     released by different acts, which is why the field exists. A row whose declared paths leave
     this repo and carries no gate at all is refused.

  4. \`prime_exit_criterion:\` AT EVERY SIZE, S and XS included — \`statement\` plus
     \`derived_from\`. It answers the one question a driver cannot answer against a task list:
     how do I know this is finished. A \`falsifier\` sub-object stays proportional to size and is
     not required here.
     When present it nests UNDER \`prime_exit_criterion\` (never a top-level \`falsifier:\`), and
     its \`baseline_ref\` is a bare commit sha — no branch, date, or prose around it.

     WHICH FILE \`derived_from\` NAMES, when this wave sized you: the wave's
     \`em-size-review.md\`, NOT the baton's \`.sizing.md\`, whenever a review exists. The
     \`.sizing.md\` is the scout's PROPOSAL. Where the EM overrode it, that file states the size
     and the reasoning that were overturned, in its opening lines, with nothing in it saying so —
     so a reader who follows it gets a confident answer that is the opposite of your plan's
     premise. Both are openable and the schema admits both; only this rule tells them apart.

Declare what is true. A \`census: []\` on a plan that counted something, or a gate omitted because
naming it looked like extra work, is a false claim in a machine-checked field — worse than the
absence, because it certifies.`

// PLAN-BLITZ IS THE ONLY AUTHOR ON THIS ROUTE THAT EVER HOLDS A SINGLE PM UTTERANCE, so it is the
// one place the baton's originating ask can be copied into the plan rather than lost before the
// first dispatch brief is ever written. Copy, never paraphrase: `resolve()` in
// `coordinator/bin/lib/pm_brief.py` treats the baton's `summary:` line plus its
// `## What this covers` section as the plan's own words the moment the plan carries no better
// source, and a paraphrase there is a silent edit of the PM's ask.
const PM_BRIEF_RULE = `
PM VERBATIMS FIRST. When the sizing that routed this baton carries \`pm_verbatims\`, the PM's own
words are already captured: Read the sizing and paste each \`pm_verbatims[].text\` VERBATIM, in
the order stored (newest first), as the \`## PM brief\` blockquote, one \`> \` block per turn
separated by a bare \`>\` line. No tool step: a shell read of \`state/sizings/\` trips the
doctrine-surface write guard. Then set frontmatter
\`pm_brief: {source: pm-verbatim, ref: "<repo-relative sizing path>"}\`. Do not re-extract, trim, or
paraphrase them. When the sizing carries no \`pm_verbatims\`, the baton rule below applies unchanged.

CARRY THE BATON'S ASK INTO THE PLAN'S OWN BRIEF. Absent sizing \`pm_verbatims\`, this baton record is
the only PM utterance behind this plan, and nothing downstream of you reads the baton again — the emitter and every reviewer
read the PLAN, not this record. Copy the baton's \`summary:\` frontmatter line, a blank line, then
its \`## What this covers\` section (when present), VERBATIM — never paraphrased, trimmed, or
summarised — into a \`## PM brief\` section in the plan body, as a blockquote. Set frontmatter
\`pm_brief: {source: baton-originating-ask, ref: "<repo-relative path to this baton record>"}\`.

Give EVERY spine row a \`traces_to_brief\`: a short phrase, quoted verbatim from the \`## PM brief\`
text, naming which part of the PM's ask that row serves. A row that can quote nothing from the
brief is scope growth on this baton — say so in your summary rather than inventing a quote to fill
the field. ${SPINE_CHECK_RULE('<your plan path>')} already reports a STRUCTURAL finding for any
non-deferred row with a missing or paraphrased trace once the plan carries a \`## PM brief\`
section, so this is enforced mechanically and not left to review.`


function sizingScout(baton, waveIndex, trailDir) {
  return trackAgent('sizing-scout', agent(
    `You are a sizing scout for plan-blitz wave ${waveIndex}. Size ONE roadmap baton.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}

Read the baton record, then read the substrate it names. Produce a t-shirt read (XS-XXL) of
ENGINEERING COMPLEXITY ONLY. You are not being asked what it is worth, how urgent it is, or how
long anyone wants to spend — only how complex the work is.

Report these separately, and do not blend them:
  - touchpoints: the files and surfaces the work touches. This is BREADTH. N files touched
    uniformly is not depth and must not raise your notch on its own.
  - unknownMechanisms: things that are not merely unfamiliar but genuinely unproven — where you
    cannot say from the tree whether the approach works. This is DEPTH, and it is what a size
    is actually made of.
  - priorArt: existing implementations of the same shape in this repo or a sibling. Prior art
    LOWERS a size; a job somebody has already done once here is not novel.
  - crossTeamDependency: a named coordination cost, if any, and whether the shared contract is
    itself still being negotiated (that is in the notch) or merely needs a memo (that is a gate,
    not a size).

**Never call an artifact ABSENT from a live-tree grep alone.** These repos reap and archive on a
schedule, so a memo that landed and was later distilled away looks exactly like one nobody ever
wrote. Before asserting that anything — a memo, an ack, a decision record, a counterparty's
surface — does not exist, check the history:

    git log --all --diff-filter=A -- '<path glob>'

Empty there too, and it was never written; a hit means it existed and went somewhere, so say
that instead. Measured: a scout reported three memos ABSENT and a counterparty door "never
built", from the live tree only. All three had landed and been reaped by an approved distill
run, and the door shipped that same day. That wrong premise escalated a settled baton to the PM
as a cross-team blocker, and undoing it cost an Opus adjudication. A \`crossTeamDependency\` you
are about to call unnegotiated is exactly the claim this check exists for.

Your read will be interrogated by an EM who revises down by default. Do not pre-inflate against
that, and do not hedge: give the number you actually believe and the evidence that produced it.
An honest S that survives is worth more than a defensive L that gets cut.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'sizing'))}`,
    {
      label: `size:${baton.id}`,
      phase: 'Size',
      model: 'sonnet',
      schema: SIZING_SCHEMA,
    },
  ))
}

// ---------------------------------------------------------------------------
// Phase 3 — Plan
// ---------------------------------------------------------------------------

function planner(baton, decision, waveIndex, trailDir, singleContext) {
  // Rendered rather than described: the hand-author branch lists frontmatter keys as literal
  // text, and a planner told to "put the sizing path here if there is one" fills it with a
  // plausible invention when there is not. `null` is the sanctioned absence and passes the gate.
  const sizingFm = decision.sizingObject ? `"${decision.sizingObject}"` : 'null'

  const revising = baton.planPath
    ? `A plan already exists at ${baton.planPath}. REVISE it IN PLACE with Edit. Do not scaffold,
do not author a second plan for the same baton, and do not rewrite its frontmatter — a duplicate
plan is two sources of truth for one piece of work, and a re-emitted frontmatter block silently
drops the \`created\` date, the \`deliverable_id\` edge the gate resolves through, and the
\`sizing_object\` citation the existing plan already carries. Those keys are already correct;
leave them alone. Change the BODY to answer what the reviews raised, and leave \`status\` where
you found it.`
    : `No plan exists yet. Author one.`

  const sizingAbsenceNote = decision.sizingObjectAbsence ? `

     WHY THERE IS NONE, from the EM that sized you: ${decision.sizingObjectAbsence}
     Carry that sentence into your summary verbatim. Without it the missing artifact surfaces later
     as a schema refusal on \`prime_exit_criterion.derived_from\` — a field nobody mis-authored — and
     the reader has no way back to what actually failed. Do NOT reach for the baton's handoff to
     fill \`derived_from\` instead: \`plan.schema.json\` does not admit it, deliberately, because the
     bar means "someone sized this" rather than "this plan came from somewhere".` : ''

  const authoringBrief = baton.planPath ? `You are revising, so the file already exists and the generator has no part in this: the
scaffold step below is for a plan being authored from nothing, and running it here is what
produces the duplicate you were just told not to create. Read the existing plan first, then edit
its body.

A plan authored before the mise-prep bar will be missing the FOUR DECLARATIONS below, and
frequently the task spine with them — most of the corpus predates all of it. Revising means
bringing the plan up to the bar, not only editing the prose you were sent here for: add the
frontmatter keys and the spine if they are absent. Leaving a revised plan below the bar hands the
next ceremony a plan it must refuse, and the revision reads as complete.` : PLUGIN_AGENTS ? `Invoke the coordinator:plan skill and follow it. Two rules from it that a fan-out is most likely
to skip, restated because skipping them here is invisible until much later:

  1. The plan file is produced through scaffold-plan / coordinator-doc-new, never hand-authored.
     The generator owns frontmatter emission and the write-time commit. Hand-authored frontmatter
     is invalid frontmatter that happens to parse.
  2. Cite the sizing-object that routed you here: \`${decision.sizingObject || '(none emitted — see below)'}\`.
     The flag also writes the reverse edge onto the sizing; omit it and the sizing never learns it
     was routed. Use that path EXACTLY. If it reads "(none emitted)", the EM did not scaffold one:
     write \`sizing_object: null\` and say so in your summary. An explicit null is sanctioned and
     passes the gate; a path you invent to fill the field does not, and fails as a DANGLING
     citation that looks connected.${sizingAbsenceNote}` : `The coordinator plan tooling is NOT installed on this machine, so hand-author the plan file at
${REPO_ROOT || '<repoRoot>'}/docs/plans/<YYYY-MM-DD>-<slug>.md. Frontmatter, exactly these keys and nothing invented:

    ---
    title: "<title>"
    created: <YYYY-MM-DD>
    status: draft
    author: plan-blitz
    deliverable_id: "<the baton's own deliverable_id, copied verbatim from its record>"
    sizing_object: ${sizingFm}
    census: []            # or a list of {question, command, result} — see FOUR DECLARATIONS
    prime_exit_criterion:
      statement: "<what makes this plan finished, checkable against the tree>"
      derived_from: "<this wave's em-size-review.md if one exists, else the baton's .sizing.md — never the handoff, which the schema does not admit>"
      # derived_from takes the BARE PATH and nothing after it. The schema pattern is anchored,
      # so "<path> (the EM's override of the scout's S)" fails the write. Say that on a
      # comment line instead — the rationale is worth keeping, just not inside the value.
    external_gate: []     # or a list of gates, each carrying requires:
    ---

and a task spine in the body, which is the thing the run schedules — a fenced
\`\`\`yaml plan-tasks block under \`## Tasks\`, one row per unit of work:

    \`\`\`yaml plan-tasks
    - id: C1
      title: "<one line>"
      change_kind: code-edit        # or verification, doc-edit, test-edit, ...
      surface: <subsystem or path>
      writes:
        - <repo-relative path this row writes>
      disposition: open
    - id: C2
      title: "<one line>"
      change_kind: test-edit
      surface: <subsystem or path>
      writes: []
      depends_on:                   # OPTIONAL, and an OBJECT per predecessor, never a bare id
        - chunk: C1
          gate_kind: output-consumption-runtime   # or epistemic-premise; those two only
      disposition: open
    \`\`\`

A plan with no spine declares no work the run can schedule, so it is not
dispatchable however good its prose is. The heading is matched LITERALLY — both its level
and its text — so write exactly \`## Tasks\` and nothing else:

  - \`### Tasks\` locates as NOTHING and every consumer reads the plan as spine-less.
    Measured 2026-09-10 on this repo's most-linked plan.
  - \`## Task spine\` is the near-miss that actually keeps happening, because it reads
    better and the fence under it is perfectly good. It locates MALFORMED, and the
    certification gate reports \`SPINE/SpineReadError\` — which sends the reader to debug
    the rows rather than the one word above them. Measured three times: twice in a single
    wave on 2026-09-10, and once in the run before it.

Neither is a formatting nit. A right-looking heading is exactly why the failure survives
review: the spine is correct and unreachable.

VALIDATE THE SPINE BEFORE YOU RETURN, and fix what it reports — this is a runnable check, not
advice:

${SPINE_CHECK_RULE('<your plan path>')}

Exit 0 is required. \`LEGACY\` is exit 0 and needs nothing from you. \`INVALID\` means the schema
does not admit the spine you just wrote, so the dispatch emitter, the wave-builder and
\`/execute-plan\` all refuse it and the plan produces nothing.

The two fields planners actually get wrong, both measured on this run across four independent
fires — prose saying so was already in this brief and did not stop it, which is why there is now
a command:

  - **\`gate_kind\` is a CLOSED two-value enum.** \`output-consumption-runtime\` and
    \`epistemic-premise\`. Not \`file-contention\`, not \`shared-vocabulary\`, not
    \`output-consumption-authoring\`, not \`file-existence\` — every one of those was invented by a
    planner on this run and every one makes the row unreadable. If the gate you mean is not one of
    the two, the honest home is the row's own body prose, and absence of \`depends_on\` is how a row
    declares no gate. A wave-builder derives write-overlap ordering itself; you do not declare it.
  - **\`external_gate\` is an ARRAY of objects, never a label.** \`external_gate: EG1\` and
    \`external_gate: gate-claude-klabauter-engine-half\` are both type errors. Each entry needs \`owner_repo\`
    and \`condition\`, plus \`requires\` when the gate is uncleared. Naming a gate you defined in
    prose elsewhere in the plan does not connect it to the row.

\`depends_on\` is only for the two gates a wave-builder CANNOT derive:
\`output-consumption-runtime\` (the predecessor's artifact must exist at runtime when this row
runs) and \`epistemic-premise\` (the predecessor decides whether this row should exist at all).
Ordering that follows from two rows touching the same file is computed from \`writes:\` and must
NOT be restated here. Omit the key when neither gate applies — a bare string in this array is a
spine that fails to read, which refuses the whole plan rather than the row.

**A \`depends_on\` edge is a CLOSED key set: \`chunk\`, \`gate_kind\`, \`note\`, nothing else.** The row
around it is open, which is the trap — a key you add to the ROW is tolerated, the same key on the
EDGE refuses the plan. Conditional dependencies are the recurring case: a reviewer asks for
arm-conditionality or a guard the driver can read, there is no field for it, and an invented
\`condition:\` looks like the honest answer. It is not — put the condition in \`note\`, which exists
for exactly this ("what specifically must exist, or be decided, before this row runs"), and carry
the machine-readable half on a ROW field. Measured 2026-09-10: a planner answering a reviewer's
arm-conditionality finding wrote \`condition: "arm == B"\` on an edge; the plan authored, reviewed,
integrated and landed fine, and was then refused at the mise-prep gate with SPINE
MalformedDependencyEdgeError — the whole plan uncertifiable for one key. Tripwire:
\`A-CLOSED-SCHEMA-TURNS-AN-INVENTED-KEY-INTO-A-LOST-ARTIFACT\`.

**\`deliverable_id\` is load-bearing, not bookkeeping.** It is the only edge that links this plan
back to its baton, and \`roadmap.plan_gate\` resolves the link through it. A plan without it is
INVISIBLE to the gate: the baton reads \`needs_plan: true\` forever, gets re-planned by every
later sweep, and its approval never opens the planning gate of anything blocked on it. Open the
baton record, copy its \`deliverable_id:\` value exactly, and do not invent one — a fabricated id
links to nothing and is worse than an absent one, because it looks connected.

\`status: draft\` is not a placeholder to improve on — it is the correct value. Only the EM's
readiness gate advances a plan past draft, and a planner that writes \`approved\` has forged the
gate this whole pipeline exists to hold.

Body: the problem in one paragraph; file scope; acceptance criteria that can each be checked as
true or false against the tree; the test surface; and an explicit Anti-scope naming what this
plan does NOT do.`

  const priorArtNote = singleContext && singleContext.priorArtSidecarPath ? `
A prior-art pre-flight already ran over this baton's sizing intent, before you started. Read its
sidecar before you write: ${singleContext.priorArtSidecarPath}
A CONFLICT bucket there is prior art the plan must reconcile with, not information to skim past.` : ''

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

The size above is FINAL for this wave. It was already interrogated by the EM. Do not re-litigate
it — if the substrate contradicts it once you are in the body, say so in your returned summary
and keep planning to the size you were given; re-sizing mid-plan is how a wave loses its
comparability.

TWO FILES, AND THEY ARE NOT THE SAME FILE. You produce the PLAN DOCUMENT under \`docs/plans/\`,
and separately a run sidecar in the wave trail. \`planPath\` is the plan document — ALWAYS. It is
never your sidecar, never anything under the trail directory, and never anything under
\`subagent-share/\`. Return the path the generator actually wrote the plan to; if you did not
write a plan, return \`status: blocked\` with the reason rather than a path to something else.

Getting this wrong does not fail loudly on your side: every reviewer is aimed at whatever you
return here, so a sidecar path sends more agents at a file that is not the plan, and the baton
spends a wave slot producing nothing.
${singleContextBlock}
Return \`reviewSignals\`: the \`review_signals\` ids you declared in the plan's frontmatter (empty when
none). They select the plan's domain reviewers; the roadmap's own OVERVIEW.md frontmatter
(\`approver\`, \`approval_utterance\`) is the PM's Approve record — read it before writing that none exists.
${MISE_PREP_RULE}
${PM_BRIEF_RULE}
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'planning-report'))}`,
    { model: 'opus', ...withRole('coordinator:plan-author'),
      label: `plan:${baton.id}`,
      phase: 'Plan',
      // Planning is opus on EVERY route, and the wave does not offer a knob to
      // lower it. Sonnet's place in this pipeline is research (the sizing scouts)
      // and execution (the XS dispatch lane) — both bounded work with the judgment
      // already made. Authoring is where the judgment IS: a plan is what the
      // executor is held to, and on `spec-dispatch` it is stamped
      // `execution_authorized_*` and read by nobody in between. Reviewers apply
      // their own findings now, so the planner is never re-invoked to resolve one.
      // Medium, not high: the planner is authoring against a size and a route the
      // blitz-em already interrogated, over substrate a scout already inventoried.
      // The judgment it owes is the plan's shape, not a re-derivation of the wave's
      // decisions — and an unpinned planner inherits whatever the invoking session
      // was set to, which makes the wave's authoring depth an accident of who fired it.
      effort: 'medium',
      schema: PLAN_SCHEMA,
    },
  ))
}

// ---------------------------------------------------------------------------
// Premise check — between a written plan and the reviewers who read it
// ---------------------------------------------------------------------------
//
// WHAT THIS BUYS. Nothing between authoring and review resolves a plan's claims against the
// tree, so the first reader to notice a path that does not exist, a symbol that means something
// else, a branch nobody pushed, or a falsifier that cannot go red is an OPUS reviewer — and the
// discovery costs that reviewer and a wave slot. Peer-reported, and NOT a DoE
// measurement: across an eight-wave sweep in one sibling repo and five waves in another, the
// plans that reached execution-ready were a minority, and nearly every pull was this one shape.
// The same series shows the ready rate having no relationship to plumbing state in either
// direction across the whole eight waves, which is why this is a missing stage rather than an
// unreliable one.
//
// IT REPORTS. It does not refuse, does not gate, and does not edit. The semantic class is only
// mechanically decidable where the repo carries a surface that forbids the assumption, so on the
// occasions it is guessing a hard refusal would convert a recoverable authoring slip into a
// pulled plan — the exact cost this exists to remove. Its output goes to the reviewers, who then
// spend their pass on judgment rather than on resolving citations and apply a premise finding
// to the plan body in-wave.
//
// IT IS NOT A CORRECTNESS CLAIM, and the schema above has nowhere to make one.
//
// ORDERING. This runs where it does because of DATA, not position: it needs a written plan, and
// the reviewers read what it returns. Nothing here reads a phase index or assumes what runs on
// either side of it.

function premiseChecker(baton, planResult, trailDir) {
  return trackAgent('planner', agent(
    `phase: premise-check

Resolve the load-bearing citations in the plan at ${planResult.planPath} (baton ${baton.id}) against
this tree. A citation is load-bearing when the work changes if it does not resolve.

Report the CLASS you checked. You are not reviewing the plan, and you never report that it is
correct, sound or ready — a plan whose every citation resolves can still be wrong, and a clean
table read as an approval is worse than no table.

You never refuse and never edit. A defect you find is something you report.

Five question classes. Answer each for every load-bearing citation:

  1. PATHS — does each cited file, directory or artifact exist? The plan's own frontmatter counts:
     a literal scaffold placeholder left in \`plan_id\` or \`deliverable_id\` is an unresolved
     citation, not a formatting slip.
  2. SYMBOLS — does each cited function, constant, op or CLI exist, and is it reachable the way
     the plan assumes? Where \`project_referencers\` / \`project_symbol_callers\` / \`project_file\`
     resolve on this machine, use them; otherwise grep for the definition site. Say which route
     answered — an absent tool is a thinner check, not a resolved citation.
  3. REFS — does each cited branch, tag or commit exist? ONE batched \`git branch -r\` plus
     \`git rev-parse --verify\` per plan, never one process per citation.
  4. FALSIFIER ARMING — can this plan's own falsifier report red? Run
     \`${ARMING_CHECK_CLI} <instrument> --json\` and carry its verdict
     into \`falsifierVerdict\` VERBATIM. Do not restate its predicate in your own words and do not
     write your own version: it is one surface with several readers. Its \`UNCHECKABLE\` means the
     file could not be read, which is not a pass. If the plan names no falsifier, say so.
  5. ASSERTED SEMANTICS — does the named thing MEAN what the plan says it means? This is the class
     an existence check misses: the path resolves, the symbol resolves, and the plan still assigns
     the wrong ROLE to something that is really there. It is decidable exactly where this repo
     carries a surface that forbids the assumption. So for every substrate the plan gives a role
     to — a drive, a root, a volume, a directory, a store — grep the wiki and \`state/lessons/\`
     for that noun plus prohibition vocabulary, and read any resolver the plan routes through to
     see whether it raises rather than defaulting. Where no such surface exists, the row is
     \`UNCHECKABLE\`: name the assumption you could not settle. Never upgrade a silence to
     \`RESOLVES\`.

Row verdicts: RESOLVES · UNRESOLVED (absent) · CONTRADICTED (present, and the tree says otherwise
— a docstring describing a different job, a wiki page forbidding it, a resolver that raises) ·
UNCHECKABLE (nothing in this tree settles it).

\`UNCHECKABLE\` costs you nothing and is the honest answer often. \`RESOLVES\` on a citation you did
not open is the failure this pass exists to stop, moved one stage earlier.

Cap at 40 citations, in plan order; put the number you left in \`citationsSkipped\`.

Do not read the plan's acceptance criteria to decide what to check. Check what it CITES — a
checker steered by the plan's own account of done inherits the plan's blind spot.

The two contracts below are the calibration for those classes — the tolerance rule, the
\`<repo>@<ref>\` requirement, class 5's two firing conditions, and the tell an unarmed instrument
shows. They are inlined rather than left to the role file because a role the harness cannot
resolve degrades to a generic agent silently, and the contract would go with it. Read them as the
detail behind the classes above, not as a second taxonomy.

${PREMISE_CHECK_CONTRACT}

${INSTRUMENT_CAN_REPORT_RED_CONTRACT}

Where those contracts say "report, do not refuse", the ROW VERDICTS above are how you report:
"semantic check not applicable, degrades to reviewer judgment" is a class-5 \`UNCHECKABLE\` row
naming the assumption, never a withheld row and never a \`RESOLVES\`. Where they say to name the
check in words rather than a bare class number, the number goes in \`questionClass\` and the words
go in \`evidence\`. You have no field for a verdict on the plan, and that is deliberate.

**Also return \`spinePresent\`, and RUN THE CHECKER for it — never answer it by eye:**

${SPINE_CHECK_RULE(planResult.planPath)}

Read the verdict token off its stdout. \`NO-SPINE\` → \`spinePresent: false\`. Any other token
(\`VALID\`, or a shape complaint) → \`spinePresent: true\`: those say the block IS there and
something about it is wrong, which is a different fact and not yours to report here. **If no
resolved invocation was supplied above, or the checker did not run for any reason, OMIT
\`spinePresent\` entirely.** Omission reads as "not established" and changes nothing downstream;
a guessed \`false\` reverses the EM's verdict and parks a plan that was ready.

Why it is not an eyeball question: this field is the ONE input that can overturn the blitz-em's
\`ready\`, and three other readers in this system answer it with a regex. Measured 2026-09-11 on
Example-cockpit-repo — a plan carrying ten spine rows at \`## Tasks\` was reported spine-absent here,
landed \`pulled\` against an EM reason reading "Executable as it stands", and cost the wave. The
opposite error is cheap by comparison: a false \`true\` schedules an empty plan and is caught at
dispatch, while a false \`false\` parks a cleared plan and re-fires the same baton into the same
coin-flip every wave after. Quote the token you saw in your summary so the boolean is auditable.

The check this exists for is real: measured 2026-09-10, an 869-line plan with zero fenced blocks
cleared this phase, two reviewers, integration and the readiness gate, landed approved, and was
refused a ceremony later with SPINE/spine-absent. A \`false\` is not a finding against the plan's
content — it says there is nothing to schedule.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${REVIEW_SIDECAR_RULE(
      
      
      // 20260925T121401Z: all 4 premise-check dispatches provisioned and wrote sidecars, and none
      
      sidecarFor(trailDir, baton.id, 'review-premise-check-pointer'),
      // The provisioner takes an agent IDENTITY. This used to pass the doc-TYPE token
      
      
      'coordinator:premise-checker',
      
      // gate accepts for a non-persona sidecar (`_REVIEWER_DOC_TYPE_TOKENS`). Passing the
      
      // `coordinator:premise-checker` is not in `_REVIEWER_AGENT_TYPES`, and widening that
      
      'review-findings',
    )}`,
    { model: 'sonnet', ...withRole('coordinator:premise-checker'),
      label: `premise:${baton.id}`,
      phase: 'Premise check',
      // Sonnet, pinned rather than inherited, and the pass's whole economic premise: these are
      // questions with mechanical answers, priced against a discovery cost today of an opus
      // reviewer plus a wave slot. An opus premise checker would cost more
      // than the reader it is meant to spare.
      // Low. The judgment is "did I open the thing", not "is this a good plan" — and raising it
      // invites exactly the plan-level opinion the schema refuses to carry.
      effort: 'low',
      schema: PREMISE_SCHEMA,
    },
  ))
}

// The classes a premise check answers, enumerated so a class with NO row renders as a hole rather
// than as an absence. 1 paths · 2 symbols · 3 refs · 4 falsifier arming · 5 asserted semantics.
const CITATION_CLASSES = [1, 2, 3, 4, 5]

// Per-class coverage, rendered in the headline rather than left derivable from the rows below.
// The consumption contract states the distinction one level up — where no report ran, the class
// is unchecked, not clean — and the same distinction exists per class: a plan that gave no
// substrate a class-5 role never attempted class 5, and a plan whose class-5 rows all resolved
// attempted it and came back clean. Counting unsettled rows cannot tell those apart, so the count
// is carried per class instead of asked of the reader.
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

// XS work the Dispatch phase FINISHED, shaped into the verdict rows the LANDING can close.


// `completed` is the whole predicate. An INCOMPLETE executor return is NOT closed: the gate


function closableDispatched(dispatched, verdicts, waveIndex) {
  const gated = new Set((verdicts || []).map((v) => v.batonId))
  return (dispatched || [])
    .filter((d) => d && d.completed && !gated.has(d.batonId))
    .map((d) => ({
      batonId: d.batonId,
      verdict: 'ready',
      route: 'dispatch',
      
      
      planPath: null,
      
      
      reviewVerdicts: [],
      reason: `XS dispatched in wave ${waveIndex} and reported completed: ${d.summary}`,
      // Verbatim, unvalidated: the landing owns the check and falls back to its own SHA.
      priorShippedIn: d.priorShippedIn,
    }))
}

function premiseAsReview(baton, premise) {
  if (!premise) return null
  const rows = premise.rows || []
  const findings = rows.filter((r) => PREMISE_FINDING_VERDICTS.includes(r.verdict))
  // Class 5, not resolved: the rows where no fix is writable from the finding alone, which is
  // the second half of the PIVOT conjunction. Named, never routed — this seam has no verdict to
  // gate and has written no fix, so `a-blocked-review-is-not-a-pivot.md`'s "when you are between
  // them, return BLOCKED" applies to it by construction.
  const unwritable = rows.filter(
    (r) => Number(r.questionClass) === 5 && r.verdict !== 'RESOLVES',
  )
  return {
    batonId: baton.id,
    reviewer: PREMISE_REVIEWER,
    verdict: findings.length ? 'BLOCKED' : 'OK',
    sidecarPath: premise.sidecarPath,
    findingCount: findings.length,
    // `rows: []` (zero citations examined) and a fully-checked, all-RESOLVES `rows` both produce
    // bare `verdict: 'OK'`; the explicit count tells them apart downstream. Kept separate from
    // `premiseFailure` — that field is a class-5 PIVOT candidate signal, and reusing it for
    // "nothing was checked" would misread as one.
    citationsChecked: rows.length,
    premiseFailure: unwritable.length
      ? `class-5 rows with no fix writable from the finding alone — PIVOT candidates for a `
        + `reviewer to run the separating test against, not a route this pass took: `
        + unwritable.map((r) => `${r.verdict} ${r.citation}`).join('; ')
      : undefined,
  }
}

const PLAN_COVERAGE_REVIEWER = 'plan-coverage-check'

// The seam for the second single-plan pre-flight — same shape as `premiseAsReview` above, so the
// wave's readiness brief and its `reviews` reconciliation read it through the one channel every
// other reviewer already goes through. plan-coverage-checker is report-only (§ ROLE_CONTRACTS),
// so this never applies a fix; it only routes the verdict.
function planCoverageAsReview(baton, coverage) {
  if (!coverage) return null
  const verdictMap = {
    COMPLETE: 'OK',
    // A scope mismatch is a departure worth naming to the wake reader, not a clean pass —
    // mapped to WARN (a deviation) rather than OK, which would hide it from `deviations`.
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
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'prior-art-check'))}`,
    { model: 'sonnet', ...withRole('coordinator:prior-art-checker'),
      label: `prior-art:${baton.id}`,
      phase: 'Plan',
      effort: 'low',
      schema: PRIOR_ART_SCHEMA,
    },
  ))
}

function planCoveragePreflight(baton, planResult, trailDir) {
  return trackAgent('plan-coverage-checker', agent(
    `phase: plan-coverage-preflight

${ROLE_CONTRACTS['plan-coverage-checker']}

Run your eight lenses over the plan at ${planResult.planPath} (baton ${baton.id}), in the same pass
as this plan's premise check — you never gate on it and it never gates on you, you just both read
the same freshly-written plan.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'plan-coverage-check'))}`,
    { model: 'sonnet', ...withRole('coordinator:plan-coverage-checker'),
      label: `plan-coverage:${baton.id}`,
      phase: 'Premise check',
      effort: 'low',
      schema: PLAN_COVERAGE_SCHEMA,
    },
  ))
}

// ---------------------------------------------------------------------------
// Phase 4 — Review
// ---------------------------------------------------------------------------

function reviewerAgent(baton, decision, planResult, reviewer, trailDir, premise, priorReviewers) {
  const sequencing = priorReviewers && priorReviewers.length
    ? `\nSame plan, so this baton's reviewers run SEQUENTIALLY, never in parallel — you are not the
first. ${priorReviewers.map((r) => `${r.reviewer} ran before you, returned ${r.verdict}, and its
findings are already applied and verified in the plan on disk.`).join(' ')} Read their sidecar(s)
before you start: a finding you would raise that they already applied is settled, not yours to
re-log, and an edit of theirs that removed text a later finding of YOURS needs is a conflict to
name in your own findings rather than silently work around.\n`
    : `\nYou are the first (or only) reviewer to run on this plan in this wave.\n`

  return trackAgent('reviewer', agent(
    `${ROLE_CONTRACTS.reviewer}

Review the plan at ${planResult.planPath} for baton ${baton.id} ("${baton.title}").

Finalised size: ${decision.tshirt}, route: ${decision.route}.
Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}
${sequencing}
Premise check, run against the tree before you:
${premiseLines(premise)}

Read it as work already done on ONE class, never as an approval. A citation reported RESOLVES has
been opened — do not spend your pass re-opening it. A row reported UNRESOLVED or CONTRADICTED is a
premise failure someone else found for you, and it is yours to weigh, not to re-derive. A row
reported UNCHECKABLE is UNCHECKED: nothing in this tree settled it, so the assumption is live and
it is exactly where your judgment is worth its price. A class rendered "none" was never attempted
at all — that is a hole, not a clean class, and no row will tell you about it. Consumption contract:
\`coordinator/snippets/premise-check-consumption.md\`.

A clean premise report narrows nothing else. A plan whose every citation resolves can still be
solving the wrong problem, and that judgment was never this pass's to make.

**The premise check routes BLOCKED, never PIVOT, and its class-5 rows are why you are here.** A
missing path names its own repair; a class-5 row the tree contradicts or leaves unsettled names
none, and the separating test — write the fix; if you cannot, the direction is what is wrong — is
a test only a reviewer runs. Run it on those rows before you pick a verdict. You are the actor
that may PIVOT on them.

Review the PLAN, not the code it proposes. The questions that matter: does the stated problem
match the baton's actual job; do the acceptance criteria falsify anything; is the scope the size
it claims to be; does the sequencing hold; and is any premise it rests on actually true of this
tree right now.

Verdicts. These are ROUTES, not rungs on a severity ladder — the question each answers is
different, and picking by "how bad is it" picks wrong:

  - OK / WARN / BLOCKED — the DIRECTION holds; what is wrong is fixable IN this plan. BLOCKED is
    "this plan must not execute until these are fixed" — however severe, however many. You apply
    every finding yourself (below), and the fixed plan can be approved in this same wave. Almost
    every real objection is one of these.
  - PIVOT — "do not think about this plan; this direction cannot proceed and must be rethought."
    Not a stronger BLOCKED. The plan is solving a problem that is not the problem, or rests on a
    mechanism that does not exist, and no set of findings repairs it. PIVOT does not halt
    anything: it routes this baton to a REPLAN with your rationale as the brief.

The test that separates them: write the fix. If you can name what a competent author changes in
this plan to make it right, it is BLOCKED however large that change is. If the answer is "start
from the requirement again", it is PIVOT.

A PIVOT must carry \`premiseFailure\` — the false premise stated precisely — and
\`alternativesConsidered\`. A pivot with neither is a mood, and it leaves the replan session
nothing to steer by.

Do not soften a PIVOT into a BLOCKED to be helpful: a premise failure filed as a finding is one
you would then apply as though it had an in-plan fix, and it does not. Do not inflate a BLOCKED
into a PIVOT to be emphatic either: that discards a repairable plan and costs the baton a whole
wave. If you are between them, return BLOCKED and say in your sidecar why you considered a pivot —
the readiness gate reads that, and a plan wrongly kept is recoverable in a way a plan wrongly discarded is not.

If you find yourself reaching for REJECTED out of the fleet-wide reviewer enum, that word is
accepted here but is not this pipeline's vocabulary: it resolves to PIVOT only when you have
stated a \`premiseFailure\`, and to BLOCKED otherwise. Say what you mean with PIVOT or BLOCKED
instead of leaving the resolution to a field you might not fill.

You are one of possibly several reviewers on this plan, each writing to their own sidecar. Do not
assume your verdict is the wave's verdict, and do not defer to an imagined co-reviewer: a BLOCKED
alongside someone else's PIVOT is not redundant — your findings become inputs to the replan.

**APPLY YOUR OWN FINDINGS.** There is no integrator behind you. Every finding you log is yours to
apply in place, with Edit, to ${planResult.planPath} itself, before you return — nits included.
A frontmatter field you correct keeps its schema type: a dead \`branch:\` becomes the branch you are on, never \`null\`.
Filtering does not happen upstream: you are UNCONDITIONAL on verdict, and an OK does not skip
applying anything you found. On PIVOT, or a REJECTED you resolve to PIVOT yourself, apply nothing —
the plan is going to a replan, and repairing a plan about to be discarded produces a document that
looks maintained and is not; log every finding under that verdict as \`"status": "suspended"\`
instead. Never write attribution — no \`Review: <you>\`, no finding number, no your name — into the
plan itself: the ledger below is the attribution record, not the file.

Then write a \`## Findings Ledger\` heading in your OWN sidecar (the one this brief has you
provision below), holding exactly one fenced \`\`\`json array with one row per finding you logged:

    {"id": "finding-<N>", "file": "<repo-relative/forward-slash>", "before": "<exact text replaced, or empty for an insertion>", "after": "<exact text now present, or empty for a deletion>"}

Then run:

${CLI_RESOLUTION_RULE}

    review-findings-ledger verify --sidecar <your sidecar path>

Exit 0 is done. Non-zero names the failing rows: fix them and re-run before you return — a ledger
that does not verify is a review whose findings the wave cannot confirm were actually applied. Do
NOT hand-author around a refusal: report it verbatim in your summary if it persists.

Only the EM runs \`review-findings-ledger reject\` or \`targets\` — both are refused when invoked
from inside your own dispatch. If you believe a finding should NOT have been applied after all, say
so in your summary; you do not revert your own edit outside the ledger's own record.
${REPO_ROOT_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, `review-${reviewer}-pointer`), reviewer)}`,
    { model: 'opus', ...withRole(reviewer),
      label: `review:${baton.id}:${reviewer}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    },
  ))
}

// ---------------------------------------------------------------------------
// Retired — the review-integrator, its escalation catalogue and the resolve-escalations lane
// ---------------------------------------------------------------------------
// Deleted with the integrator: the convergence catalogue, the escalation/recommendation lanes,
// and the resolve-escalations pass that re-invoked the planner to arbitrate them. A finding is
// now applied (or declined, EM-only, via `review-findings-ledger reject`) by the reviewer that
// logged it — see reviewerAgent() above and § Contract in the retire-review-integrator plan.
// ---------------------------------------------------------------------------
// Phase 5b — Dispatch (XS only)
// ---------------------------------------------------------------------------

// A HUMAN-ONLY OR OTHER-HOST PULL IS A CLAIM ABOUT THIS HOST, AND A CLAIM IS PROVED BY A COMMAND.
// Tripwire A-HUMAN-ONLY-PULL-CARRIES-ITS-PROBE. Shared by the executor brief and the readiness gate
// so both ends hold the same bar. Measured on example-stats-repo (run 20261007T231156Z): two XS batons were
// pulled "needs human / needs the Windows box" while running on the Windows box.
const HUMAN_ONLY_PULL_RULE = `**A human-only, second-person, or other-host reason is valid only with its probe.** Before a
\`blockedReason\` (or a pull) says a step needs a human, a second person, or a different host, name
(a) the specific capability missing on THIS host and (b) the command whose output proved it is
missing. Prose such as "human eyeball" or "a second person" is not a gate: an independent agent
driving the browser (chrome-devtools or equivalent) is the second person unless your probe shows
that capability absent. An open question the EM owns is decided by the EM, never pulled; state
your recommendation instead. A reason with no probe is invalid and is treated as a missing
capability claim that was never checked.`

function executor(baton, decision, trailDir) {
  return trackAgent('executor', agent(
    `Do the work this baton asks for. It is an XS: the EM sized it, and the size is final.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}
EM's sizing rationale: ${decision.rationale}

An XS routes to dispatch and has no plan — there is nothing to write a plan against. The workflow
reviews your changes after you return. Read the baton, do exactly what it asks, and report what you changed.

**Bounded to the baton's own remit.** If the work turns out larger than XS, STOP and report it
with \`completed: false\` and a \`blockedReason\` — do not grow into it. An XS that expands under
an executor is a sizing defect the EM needs to see, and finishing it quietly is how a wave
launders a mis-size into a fait accompli.

**Some XS work is a closure, not a change.** Confirm-and-close is a legitimate complete outcome:
verify the thing the baton asserts, record what you verified, and say so. Do not invent a code
change to make the work look substantial, and do not add a guard or a regression test for a
surface that no longer exists.

**A confirm-and-close touches the record's frontmatter only — never its body, and never its
lifecycle fields (next paragraph).** The record is dead once the landing closes it, so filling its
empty sections (spec, acceptance criteria, anti-scope, ledger) is prose nobody reads. What you
verified goes in your execution record and your report.

**Never stamp the baton's lifecycle frontmatter** — \`status\`, \`deployment_state\`,
\`closed_reason\`, \`shipped_in\`, \`pickup_ready\`. The landing owns them: it closes an XS after the
wave's work is committed, stamping \`shipped\` and the \`shipped_in\` SHA together. A baton you
already marked \`shipped\` reads as terminal there, so the SHA is never written and the record can
never archive; a \`shipped_in\` you wrote yourself is overwritten by the SHA the landing is given.
Work you did records its disposition in the baton's body and your report; a closure records it in
your report alone. **Schema-legal is not the test here** — a live run wrote
\`deployment_state: closed\` + \`closed_reason: stale\`, the wave's readiness note called it
schema-legal and matching intent, and it was neither: the landing writes a DIFFERENT terminal,
\`shipped\` plus the wave's SHA. The close refused, and the baton now reads closed rather than
shipped, so nothing links it to the commit carrying its work.

**Work that already shipped names its commit in your report, never on the record.** When a
confirm-and-close finds the baton's work landed in an earlier commit, name that commit in your
execution record and return it as \`priorShippedIn\`: the full 40-hex SHA — run
\`git rev-parse <sha>\` if you only have an abbreviation. The landing stamps it in place of its own.
Omit the field on every other outcome, and never guess one: a SHA you cannot resolve is left out
and named in your summary.

Report honestly. \`completed: false\` with a reason is a first-class outcome and costs nothing;
a partial reported as done costs whoever reads the trail next.

${HUMAN_ONLY_PULL_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'execution'))}`,
    { model: 'sonnet', ...withRole('coordinator:executor'),
      label: `dispatch:${baton.id}`,
      phase: 'Dispatch',
      schema: DISPATCH_SCHEMA,
    },
  ))
}

// ---------------------------------------------------------------------------
// Trail slot — the leaf directory every trail record of THIS invocation is written into
// ---------------------------------------------------------------------------
//
// A WAVE INDEX IS NOT A FIRE IDENTITY. The skill caps a fire at 8 batons, so any wave with more
// than that is drained by SEVERAL fires that all carry the same `waveIndex` — and the one
// wave-scoped sidecar this script writes, `wave-<n>.em-size-review.md`, was the same path in
// every one of them. Each later fire silently overwrote the earlier fire's size review, which is
// the per-baton overwrite `sidecarFor`'s own comment documents, one level up and correspondingly
// quieter: the wave's decisions live in memory and are unaffected, so nothing fails — only the
// durable trail loses the record of how N-8 batons were sized.
//
// `fireId` discriminates on the fire's own baton set, so it is stable across a resume (which must
// land on the same sidecar) and distinct between two fires of one wave (which must not). Derived,
// never an arg: a caller that had to pass it would forget, and the failure is invisible.
const fireIdFor = (ids) => {
  const key = ids.map((id) => String(id)).sort().join('\u0000')
  let h = 0x811c9dc5
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
}

// The trail's baton-slot for this invocation. Repair mode is retired (see the docblock above):
// there is only one shape now, `wave-<index>-<fireId>`.
const waveSlot = `wave-${parsedArgs.waveIndex}-${fireIdFor((parsedArgs.batons || []).map((b) => b && b.id))}`

// ---------------------------------------------------------------------------
// planDigest — DoE wake-digest assembly, pure code over structured results
// ---------------------------------------------------------------------------
//
// Schema: `coordinator/schemas/doe-wake-digest.schema.json` (`kind: plan`). This function never
// dispatches anything and reads nothing off disk — every input is a value the wave already holds
// in memory, which is what makes it testable without a fixture that spins up an agent. It never
// claims plan correctness, the same posture the premise check and every reviewer already hold:
// it renders what the wave decided, not a fresh judgment of its own.
function capString(value, max) {
  if (value === null || value === undefined) return null
  const text = String(value)
  return text.length > max ? text.slice(0, max) : text
}

function planDigest(input) {
  const reviews = Array.isArray(input.reviews) ? input.reviews : []
  const outcome = ['ready', 'pulled', 'replan', 'surfaced'].includes(input.verdict)
    ? input.verdict
    : 'surfaced'

  // decisions: integration's escalations and recommendations — a reviewer that PIVOTed or
  // BLOCKED, or a baton this wave surfaced to the PM, is a decision the wake reader is handed
  // rather than one this function resolves. Every line carries its sidecar anchor (§ body item 5).
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
        item: r.premiseFailure || `${r.reviewer}: ${r.verdict}`,
        anchor: r.sidecarPath || input.planPath || input.batonId || '(no anchor)',
      })
    }
  }
  const decisions = decisionSources.slice(0, 5).map((d) => ({
    item: capString(d.item, 200),
    anchor: capString(d.anchor, 300),
  }))

  // em_may_think_differently: reviewer-routed judgment calls — an `alternativesConsidered` line
  // on a review that did NOT pivot or block, since those already became a `decision` above and a
  // line appearing in both buckets would double-count the same signal.
  const emSources = reviews.filter(
    (r) => r && r.alternativesConsidered && r.verdict !== 'PIVOT' && r.verdict !== 'BLOCKED',
  )
  const overflow = Math.max(0, emSources.length - 10)
  const em_may_think_differently = emSources.slice(0, 10).map((r) => ({
    line: capString(`${r.reviewer}: ${r.alternativesConsidered}`, 200),
    anchor: capString(r.sidecarPath || input.planPath || input.batonId || '(no anchor)', 300),
  }))

  // deviations: a WARN carries a departure from what was asked without rising to a decision the
  // wake reader must adjudicate — a workaround worth naming, not one worth escalating.
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
    reviews.some((r) => r && r.assembled_by === 'fallback') ||
    (input.premiseCheckVerdict && input.premiseCheckVerdict.assembled_by === 'fallback')

  return {
    schema: 'doe-wake-digest',
    version: 1,
    kind: 'plan',
    plan: {
      path: capString(input.planPath, 300),
      deliverable_id: capString(input.deliverableId, 200),
    },
    outcome,
    // `plan` digests never claim a criterion was RUN — the exit criterion is the sizing's own
    // statement, carried at `status: not_run` per § Pinned interfaces.
    criterion: {
      status: 'not_run',
      observation: capString(input.exitCriterionStatement, 300),
      sidecar: capString(
        (input.premiseCheckVerdict && input.premiseCheckVerdict.sidecarPath) || null,
        300,
      ),
    },
    // `decision_required` is the schema's ONE scalar slot for what `decisions` above collects —
    // the doe-wake-digest schema (already landed) carries no separate `decisions` array, so the
    // most load-bearing escalation is what surfaces here: the `surfaced` case's own question when
    // there is one, else the highest-priority collected decision, else nothing to decide.
    decision_required: capString(
      input.surfacedQuestion || (decisions.length ? decisions[0].item : null) || null,
      300,
    ),
    em_may_think_differently,
    overflow,
    deviations,
    counts,
    assembled_by: usedFallback ? 'fallback' : 'code',
    // The driver reads `interaction_mode` from the sizing object; it is not threaded here.
    next_action: outcome === 'ready'
      ? {
        kind: 'execute',
        op: 'plan_chain.run',
        params: {
          plan_path: input.planPath || null,
          sizing_object: input.sizingObject || null,
          deliverable_id: input.deliverableId || null,
        },
      }
      : { kind: 'none', op: null, params: null },
  }
}

// ---------------------------------------------------------------------------
// Wave body
// ---------------------------------------------------------------------------

const waveIndex = parsedArgs.waveIndex
const trailDir = parsedArgs.trailDir
const batons = parsedArgs.batons || []

// Mode contract (§ Pinned interfaces / C4 body item 1). `wave` is the default when the key is
// absent; `single` and `repair` are the only other legal values. Repair mode was already fully
// retired before this chunk (see the docblock's "REPAIR MODE IS RETIRED" note): there is no
// separate Repair block left in this file for a `repair` fire to diverge into, so accepting the
// word here and routing it through the ordinary wave path IS "keeping its existing branches'
// precedence unchanged" — there is nothing left to disturb.
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

// `single` requires exactly one baton, already sized and carrying a sizing-object — the shape
// `emit-wave-fire --from-sizing` (C5) emits. Refused here, before any dispatch, rather than
// letting the size-review gating below silently do the wrong thing over zero or several batons.
if (SINGLE_MODE) {
  // `tshirt` and `route` are checked here too — both are read straight off the baton at
  // dispatch (§ Pinned interfaces), unasked of any agent in single mode, so a baton missing
  // either would otherwise brief the planner "Finalised size: undefined, route: undefined"
  // instead of refusing up front.
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
// The one baton's sizing-object path, substituted for `gateReportPath` wherever a single-mode
// brief would otherwise interpolate it — there is no gate report in single-plan mode, and the
// sizing IS the record that resolved this fire (§ body item 1).
const SINGLE_SIZING_PATH = SINGLE_MODE ? batons[0].sizingObject : null
const GATE_REPORT_LABEL = SINGLE_MODE
  ? `${SINGLE_SIZING_PATH} (single-plan mode — no gate report; this IS the resolving record)`
  : parsedArgs.gateReportPath

// Refused BEFORE the empty-wave check, deliberately: a caller that omitted `repoRoot` has
// violated the contract whether or not this particular wave had batons in it, and learning that
// on an empty wave costs nothing while learning it on a full one costs the wave.
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

// Refused on the same ground and in the same place, and REFUSED rather than warned about. A
// brief-level warning is read by the only actor that cannot act on it: the reviewer is already
// dispatched, the caller that could pass the arg is not in the room, and the instruction it can
// follow ("find a `subagent-share` directory and write beside it") is a guess wearing a
// procedure. What follows is not a lost path but a lost RECORD —
// `review-findings-ledger` refuses any target without a `subagent-share` path segment, so a wave
// fired without this runs every review, reads every finding, and verifies not one ledger, with
// nothing anywhere reporting it. Measured 2026-09-10: 0 of 22 findings dispositionable across the
// fire, against the retired dispositions op this replaces — the same refusal shape.
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
  // An empty wave is a real state, not a failure: the caller resolved a wave whose batons were
  // all claimed or planned between the gate read and the fire. Returning the shape the caller
  // expects lets it record an empty wave rather than crash on a missing field.
  return { waveIndex, ready: [], pulled: [], replan: [], surfacedToPm: [], trailDir, empty: true }
}

// Phase 1 — scouts, one per UNSIZED baton. A baton that already cites a sizing-object had its
// size decided upstream against real substrate; re-scouting it would produce a second, competing
// number for the EM to reconcile, which is worse than no second opinion.
const unsized = batons.filter((b) => !b.sized)
const scoutResults = await parallel(
  unsized.map((baton) => () => sizingScout(baton, waveIndex, trailDir)),
)
const sizings = scoutResults.filter(Boolean)

// Phase 2 — one EM pass over the whole wave. Deliberately ONE dispatch rather than one per
// baton: the EM's most useful judgment is comparative ("these three are the same job at three
// different sizes"), and a per-baton dispatch cannot see across the wave to make it.
const sizingLines = batons
  .map((b) => {
    const found = sizings.find((s) => s.batonId === b.id)
    if (!found) {
      return `  - ${b.id} "${b.title}" [${b.path}] — already sized upstream; read its sizing-object`
    }
    return `  - ${b.id} "${b.title}" [${b.path}] — scout says ${found.tshirt}
      evidence: ${found.evidence}
      touchpoints (${(found.touchpoints || []).length}): ${(found.touchpoints || []).join(', ')}
      unknown mechanisms: ${(found.unknownMechanisms || []).join(', ') || 'none named'}
      prior art: ${(found.priorArt || []).join(', ') || 'none found'}
      cross-team: ${found.crossTeamDependency || 'none'}
      sidecar: ${found.sidecarPath}`
  })
  .join('\n')

// SINGLE-PLAN MODE gates only THIS phase (§ Pinned interfaces / body item 2): the sizing scout is
// already skipped above by the `unsized` filter, since a single-mode fire's one baton is always
// `sized: true`. There is exactly one decision to make and the baton already states it — a
// blitz-em interrogating a sizing this fire's own `emit-wave-fire --from-sizing` (C5) already
// resolved would be re-litigating an accepted decision, not gating a fresh one.
const dispatch = SINGLE_MODE
  ? {
      decisions: [{
        batonId: batons[0].id,
        tshirt: batons[0].tshirt,
        route: batons[0].route,
        rationale:
          'single-plan mode: tshirt and route are the accepted sizing object\'s own values, not '
          + 're-interrogated by a size-review blitz-em (§ Phase gating — that phase is gated off).',
        sizingObject: batons[0].sizingObject,
        // Unknown/XS/S/XXL tshirt: fall back to the LARGER (L/XL) reviewer set, never M — an
        // unrecognised size under-reviewing is worse than one over-reviewing.
        reviewers: SINGLE_PLAN_REVIEWERS[batons[0].tshirt] || SINGLE_PLAN_REVIEWERS.L,
      }],
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

Per baton emit: the final t-shirt, the route (from sizing-assemble, never hand-derived), a
rationale naming what you changed and why, and which reviewers this plan needs.

You do not choose the planner's model. Every plan in this wave is authored at opus, on every
route and at every size; sonnet's place here is the sizing scouts above you and the XS executors
below. Do not propose a cheaper planner for a small baton — the wave's cost is set by how many
batons you let into it, not by how thinly you staff the authoring of one.

  - sizingObject: for every baton on a PLANNABLE route ('plan' or 'spec-dispatch'), scaffold the
    sizing record your decision just made and return its path. Two commands per baton, through the
    bin ladder: \`sizing-assemble --tshirt <T>\` for the route/detents, then \`coordinator-doc-new
    --type sizing-object\`, populated from what you already hold — intent (the baton's ask, not your
    restatement of the substrate), estimate, route, detents, fork, xl_exit, premise, and
    \`status: routed\`. Do NOT hand-write the file; the generator owns the id and the frontmatter.
    For a non-plannable route return null.

    **A NULL ON A PLANNABLE BATON IS A FAILURE REPORT, AND IT NEEDS ITS REASON IN
    \`sizingObjectAbsence\`.** Returning a bare null there says "this route owes no sizing object",
    which is false, and the cost lands two phases away: the planner reaches for the only provenance
    pointer left, usually the predecessor handoff, and \`plan.schema.json\` refuses THAT — naming a
    field nobody mis-authored, on a plan that is otherwise finished. Nothing in that refusal points
    back at your scaffold. So say what happened: the CLI was denied, the generator refused the
    write, the baton's ask could not be stated without inventing an estimate. Name the command and
    the refusal text. A null with no reason is the one shape that leaves the next reader guessing at
    which of two opposite things occurred.

    A scaffolder or any other write-path CLI runs only to make a write this brief assigns. Never
    invoke one to probe it: a probe is a real write, it leaves an orphan file, and removing that
    file is a destructive rm the guard denies. To learn its flags, read its source or its \`--help\`.

    Its top-level key set is CLOSED (\`additionalProperties: false\`), so a key you invent is not
    ignored — the generator REFUSES the write and the baton gets no plan at all. Measured: an em
    filed its size-review note under a top-level \`em_review\` and the baton lost its plan outright.
    Written analysis goes under \`em_analysis\`, which exists for exactly this and is topic-keyed —
    a few words naming the topic, reused rather than re-coined. An undecided question is
    \`surfaced_to_pm\` instead; executed verification is \`premise.evidence\`. If your content fits
    nothing that already exists, say so in \`rationale\` — never mint a top-level key.

    \`em_analysis\` is optional, and its absence is a CLAIM: that your size review settled nothing
    about this baton. So where it settled something — a revision and the mechanism you named for
    it, a tradeoff you resolved, a consequence you drew from the premise — that goes here, on this
    baton's own object. Your wave sidecar is not a substitute: it is one shared working record for
    the whole wave, while this object is what the planner reads and what the next sizing of this
    baton inherits. Analysis that exists only in the sidecar leaves the object asserting none was
    written. Empty is right only when the scout's sizing stood and you added nothing to it.

    This is not bookkeeping. \`plan.schema.json\` pins \`sizing_object\` to a resolving
    \`state/sizings/*.yaml\`, and claude-klabauter's read-side gate fails a plan that cites a path which does
    not exist just as hard as one that cites nothing. A wave that skips this produces plans that
    are individually fine and collectively unlandable — and the planner, told to "cite the
    sizing-object that routed you here", will invent a plausible path when none exists, which is
    the worse of the two failures because it looks connected.
  - reviewers: resolve per baton from what the plan will actually need. Do NOT put the same
    reviewer on all of them — a reviewer named on every plan is a reviewer nobody chose.

    These three strings are the ONLY legal values. It is a closed set, not a set of examples:
      'coordinator:staff-eng'                 general engineering rigour
      'coordinator:eng-director'              the baton crosses a repo or team boundary
      'coordinator:overengineering-reviewer'  the size came down and you want the plan held to it
    A domain reviewer (data-science, front-end, ux) is never yours to name: the plan's own
    \`review_signals\` add it once the plan is written.

    Emit these EXACT strings. This repo's own docs may name reviewers by persona first name
    ("add the Game Dev Reviewer or the Data Science Reviewer", "have the Staff Engineer look at it") — that is human shorthand and it is NOT an
    agent type. Never pass a persona name through, and never invent 'coordinator:<firstname>':
    no such type exists, and a name off this list is substituted for staff-eng with the downgrade
    printed in the trail, so the plan gets reviewed by someone other than whom you chose.
    If a baton genuinely needs expertise outside these three, say so in \`rationale\` and pick the
    closest of the three — the gap is a thing for the EM to read, not a string for you to coin.

Anything that is the PM's call — route: pm-decision, or an XL exit — set surfacedToPm: true with
the question stated in the PM's register, name its \`adjudicatorClass\` (scope for scope, direction and priority; code, data-science, front-end or ux for a code matter), and give it no reviewers. The wave adjudicates it after the gate; the PM sees only what the adjudicator marks \`pm_only\`. You are an EM proxy, never a
PM proxy.

**The test is the QUESTION, not the baton's shape.** Before you set the flag, write the question
out and ask whether an EM could settle it with what is already on disk. If it could, it is an EM
call however the sizing looks — "an S on a roadmap baton is a sizing defect" describes a defect to
fix, not a decision to escalate. Surfacing binds: nothing re-queues a surfacedToPm row without a PM
answer, so a question the EM was meant to decide is not deferred by this flag, it is stranded.
Measured on project-rag-ue-addon: two rows were surfaced on baton shape, the session's own stop
guard refused them because neither question stated itself in the PM's nouns, and the EM settled
both in minutes. A question that needs DIRECTION nobody has given — which exit, what it is worth,
whose priority wins — is the PM's, and only that.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${CLI_RESOLUTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, waveSlot, 'em-size-review'))}`,
  { model: 'opus', ...withRole('coordinator:blitz-em'),
    label: `size-review:${waveSlot}`,
    phase: 'Size review',
    schema: WAVE_DISPATCH_SCHEMA,
  },
))

// Plannability follows the ROUTE, not a boolean. Only `plan` and `spec-dispatch`
// produce a plan document; every other route is a different room, and sending
// one to a planner writes an artifact doctrine says should not exist.
//
// Measured on the first live wave: an XS baton the EM correctly routed
// `dispatch` was planned, reviewed and integrated anyway — four surplus agent
// dispatches for a confirm-and-close — because this filter tested
// `surfacedToPm` alone. The resulting plan was good, which is exactly why the
// defect was invisible in the output: quality does not reveal surplus.
// A sizing-object absence that names a GUARD REFUSAL, as distinct from one that says no sizing was
// owed. The difference decides whether the wave may continue: "the route owed none" is about this
// baton, "a guard refused the write" is about the dispatch identity and therefore about every
// stage below. Matched on the vocabulary the guards and the em actually use — `Guard:` is the
// literal prefix every write guard's refusal carries, and the roster/confined wording is the
// identity case specifically.
//
// Deliberately NOT matched: a bare "could not", "missing", "unavailable" or "n/a". Those are the
// merit cases, and reading one as a denial would halt a wave that should run. The bias is toward
// under-matching: a missed denial costs what it always cost, while a false denial stops good work.
const DENIAL_SHAPED = /\b(guard:|denied|refused|blocked by|not on (the )?(coordinator\x27?s? )?(enumerated )?(agent )?roster|confined)\b/i

// The subset of denials that are about WHO dispatched, as distinct from WHAT one agent ran. A
// command-shape refusal — measured on example-market-data-repo: a sizing scout's read-only
// `grep ... | xargs grep` refused as an indirection wrapper — is one agent's choice of command, and
// a planner running different commands would not meet it. Only an identity denial predicts that
// every stage below is refused too.
const IDENTITY_SHAPED = /\b(not on (the )?(coordinator\x27?s? )?(enumerated )?(agent )?roster|confined|workflow-subagent|subagent_type)\b/i

const PLANNABLE_ROUTES = new Set(['plan', 'spec-dispatch'])

// `dispatch` is the XS lane: real work, just not plan-shaped work. It used to
// leave the wave with everything else that was not plannable, and that was a
// design error with a measurable cost — if small work falls out of the pipeline,
// an EM who wants it done has structural pressure to size it M so it does not.
// Sizing that bends toward its downstream route is corrupted sizing. So XS
// terminates in work here, and the EM can call an XS an XS.
const DISPATCHABLE_ROUTES = new Set(['dispatch'])

// Why each excluded route leaves the wave, so a reader does not have to infer it
// from the route name. `dispatch` is work, just not plan-shaped work — it is the
// one exclusion that is a HANDOFF rather than a stop.
const ROUTE_EXITS = {
  dispatch: 'XS/dispatch — routes to a direct dispatch brief and has no plan',
  shape: 'route: shape — the problem is not converged; coordinator:shape is the room',
  roadmap: 'route: roadmap — spans workstreams; coordinator:roadmap-planning is the room',
  'pm-decision': 'route: pm-decision — the exit is the PM\'s to pick, not this wave\'s',
  'goal-setting': 'XXL/goal-setting — too large to be one baton; coordinator:goal-setting is the room',
}

// A CITATION IS COMMITTED STATE, so it never carries a host path. `coordinator-doc-new` prints
// the sizing object's ABSOLUTE path, the em returns what it was printed, and both consumers take
// it verbatim — `sizingFm` writes it into the plan's frontmatter and the planner brief says "Use
// that path EXACTLY". Measured on project-rag-ue-addon: 4 of 88 plans citing a sizing object
// carry `/home/<user>/<repo>/state/sizings/...`, every one of them authored by plan-blitz.
//
// Such a plan is green on the box that wrote it and dangling everywhere else. `plan.schema.json`
// pins `sizing_object` to a RESOLVING `state/sizings/*.yaml`, so the read-side gate passes
// locally and fails on a clean checkout — the one failure ordering that gets a defect committed
// rather than caught. Portability is first-class: nothing we emit may encode a host path.
//
// Normalised HERE, at the one seam both consumers read, rather than asked of the em in its brief:
// an instruction to an LLM is not a mechanism, and two sites free to disagree eventually do.
// Separators are folded to forward slashes because repo-relative identity is forward-slash by
// rule, not by whichever host wrote the citation.
function repoRelativeCitation(value) {
  if (typeof value !== 'string' || !value.trim()) return value
  const text = value.trim()
  if (!REPO_ROOT) return text
  // Compared with separators folded on BOTH sides: an agent echoing a Windows root may respell
  // it with forward slashes, which no suffix appended to the bound root matches. A drive letter
  // compares case-insensitively, since `x:` and `X:` name one volume.
  const fold = (s) => s.replace(/\\/g, '/')
  const root = fold(REPO_ROOT).replace(/[/]+$/, '') + '/'
  const folded = fold(text)
  const drive = /^[A-Za-z]:/.test(root)
  const head = drive ? folded.slice(0, root.length).toLowerCase() : folded.slice(0, root.length)
  if (head === (drive ? root.toLowerCase() : root)) return folded.slice(root.length)
  // Absolute but NOT under this repo: left exactly as it is. The read-side gate refusing a
  // citation that resolves nowhere is the correct outcome; quietly rewriting it into something
  // that looks local would hide a real defect behind a plausible path.
  return text
}

// ONE DECISION PER BATON, enforced here rather than trusted to the em's output. Nothing downstream
// dedups: `plannable` and `dispatchable` are filters over this list, so a baton the em decided twice
// is planned twice or executed twice. Measured on example-market-data-repo wave 0 fire 2: two XS batons
// each dispatched twice into one slot, and only the second executor's care and the memo tool's
// collision guard kept that from being a double cross-repo send. First decision wins; every
// dropped one is reported, never discarded silently, because a disagreeing duplicate is the em
// contradicting itself and the reader should see which route lost.
const duplicateDecisions = []
const decidedById = new Map()
const decisions = ((dispatch && dispatch.decisions) || []).map((d) =>
  d && typeof d === 'object' && d.sizingObject
    ? { ...d, sizingObject: repoRelativeCitation(d.sizingObject) }
    : d,
).map((d) =>
  // The baton arg's `route` is the effective route: a recorded `xl_exit: accept_multi_session`
  // reads `plan` there. A pm-decision the PM already resolved is a plan, not an adjudication.
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
// An XS may be DONE in this wave only when its EXECUTION gate is open — its
// blockers coded, not merely planned. The planning gate is not sufficient and
// substituting it is the exact confusion the two-gate split exists to prevent:
// a dependent's code calls its blocker's code, which has to exist.
const dispatchable = decisions.filter(
  (d) =>
    !d.surfacedToPm &&
    DISPATCHABLE_ROUTES.has(d.route) &&
    batonFor(d) &&
    batonFor(d).executionOpen === true,
)
// Routed somewhere other than a plan. NOT dropped: a baton that vanishes between
// waves is one nobody notices, so each leaves the wave carrying the reason.
const dispatchableIds = new Set(dispatchable.map((d) => d.batonId))
const routedElsewhere = decisions
  .filter(
    (d) =>
      !d.surfacedToPm &&
      !PLANNABLE_ROUTES.has(d.route) &&
      !dispatchableIds.has(d.batonId),
  )
  .map((d) => ({
    batonId: d.batonId,
    tshirt: d.tshirt,
    route: d.route,
    // An absent `executionOpen` and a false one are different values and must not
    // report as the same sentence. `false` is the two-gate split doing its job.
    // `undefined` is the CALLER not carrying the field at all — every XS then fails
    // `=== true`, none dispatches, and each recycles into the next wave while this
    // line tells the reader their blockers are uncoded. A wrong cause is worse than
    // no cause: it sends the reader to the roadmap when the defect is in the fire.
    reason: DISPATCHABLE_ROUTES.has(d.route)
      ? (batonFor(d) && batonFor(d).executionOpen === undefined
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

// ---------------------------------------------------------------------------
// A DENIED SCAFFOLD FAILS HERE, NOT FOUR STAGES LATER
// ---------------------------------------------------------------------------
//
// A guard DENIAL is categorically different from a scaffold that failed on its merits: it says
// THIS DISPATCH IDENTITY MAY NOT DO THIS JOB, which is equally true of every stage below and does
// not improve by proceeding. Sizing is where it first becomes observable, so it is where the wave
// must stop.
//
// Measured 2026-09-11, which is why this exists. Six fires were emitted without
// `pluginAgentsAvailable`, so every dispatch was stamped `workflow-subagent` — a non-empty type on
// no roster — and the write guards confined it. The `blitz-em` had its sizing-object scaffold
// denied and RECORDED IT AS A BLOCKING DEFECT in its own size review. The wave wrote
// `sizing_object: null` and ran planning, premise-check, review and integration to completion
// anyway: 98 agents, ~8.3M tokens, and not one plan on disk, because the same guard refused every
// plan body too. Every later stage behaved WELL and reported honestly — that is precisely what
// made it expensive. Nothing halted, and the whole cost was paid before any of it was readable.
//
// Scoped to a TOTAL denial across plannable batons, never a partial one. One baton's scaffold can
// be refused for a path-specific reason that says nothing about the others; a clean sweep is the
// identity signature. Under-halting is the safe direction here — a partial denial still lands the
// batons that worked, and `sizingObjectAbsences` still reports every one of them.
//
// And scoped to an IDENTITY denial. With declared agent identities (`PLUGIN_AGENTS`) the roster
// cause is ruled out by construction, so a total sweep of plain denials is a coincidence of command
// choices — at one plannable baton, a single scout's `xargs` — and halting on it stops a wave whose
// planner would have run. Undeclared, any denial can be the confinement, and every one halts.
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
    // The lanes stay present and EMPTY rather than absent: a reader diffing this against a normal
    // result should see zero verdicts, not a missing shape they have to account for.
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

// SINGLE-PLAN MODE's first pre-flight (§ Pinned interfaces / body item 2): dispatched before
// `planner()`, over the sizing intent and exit criterion, once — single mode carries exactly one
// plannable baton, so there is nothing to fan out over.
const priorArtPreflightResult = SINGLE_MODE && plannable.length
  ? await priorArtPreflight(batons[0], waveIndex, trailDir)
  : null

// Phases 3-5 — plan, review, integrate, per baton, PIPELINED. No barrier between the stages: a
// baton whose plan lands first starts its review while its siblings are still planning. The
// wave's wall-clock is then the slowest single baton's chain, not the sum of three barriers.
const chains = await pipeline(
  plannable,
  (decision) => {
    const baton = batons.find((b) => b.id === decision.batonId)
    const singleContext = SINGLE_MODE
      ? {
          exitCriterionStatement: baton.exitCriterion,
          sizingPath: SINGLE_SIZING_PATH,
          priorArtSidecarPath: priorArtPreflightResult ? priorArtPreflightResult.sidecarPath : null,
        }
      : null
    return planner(baton, decision, waveIndex, trailDir, singleContext).then((plan) => ({ decision, baton, plan }))
  },
  async ({ decision, baton, plan }) => {
    if (!plan || plan.status === 'blocked') {
      // A planner that could not write a plan is carried to the readiness gate as a blocked
      // entry rather than dropped. A baton that vanishes between waves is one nobody notices.
      return { decision, baton, plan, reviews: [] }
    }
    // The planner's own `planPath` is a CLAIM, not a fact, and every reviewer is pointed at it.
    // Measured: one planner returned its wave TRAIL SIDECAR here instead of the plan it had
    // written under `docs/plans/`. The reviewer found the real document anyway and its findings
    // cited it, but nothing was named on the sidecar to apply them to — so every finding on that
    // plan, an AUTO-FIX among them, was dropped while the chain reported success. Sibling batons
    // in the same wave got the real path, which is why it read as inconsistency rather than a bug.
    //
    // A path inside the trail directory or anywhere under `subagent-share/` is never a plan.
    // Prefer the baton's own recorded plan when it has one — that path came from the repo, not
    // from an agent — and otherwise carry the chain as blocked rather than aiming two more
    // agents at a file that is not the artifact.
    const claimed = String(plan.planPath || '')
    // A path SEGMENT, never a substring: a plan whose slug names the directory
    // (`retire-the-legacy-subagent-share-root.md`) is still a plan.
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

    // Phase 3.5 — Premise check. Dispatched here, before any reviewer resolves or fires: this is
    // the one place `plan` is trusted and stable (past the looksLikeTrail correction above) and
    // no reviewer has fired yet. Sequenced rather than run alongside the reviewers on purpose —
    // the whole saving is that they do not spend their pass resolving citations, and a check
    // racing them arrives too late to buy that.
    //
    // SINGLE-PLAN MODE's second pre-flight (§ Pinned interfaces / body item 2) runs in the SAME
    // `parallel()` as the premise check, the way `premiseChecker()` and `plan-coverage-checker`
    // are told to here — the two read one freshly-written plan and neither gates the other.
    // Dispatched CONCURRENTLY, never sequenced: the coverage preflight is fired first, without
    // awaiting it, so it runs alongside the premise check the way § Pinned interfaces asks for —
    // "the same `parallel()`" — rather than after it.
    const coveragePreflightPromise = SINGLE_MODE ? planCoveragePreflight(baton, plan, trailDir) : null
    // Attach a handler at creation, not at the `await` below: a rejection surfacing while the
    // premise check is still in flight would otherwise be unhandled for that whole span, and
    // Node's default policy can kill the process on it. The real handling (the throw) still
    // happens at the `await` — this no-op catch only stops it from being unobserved meanwhile.
    if (coveragePreflightPromise) coveragePreflightPromise.catch(() => {})
    const premise = await premiseChecker(baton, plan, trailDir)
    const coverage = coveragePreflightPromise ? await coveragePreflightPromise : null
    // The seam. Rows in, one REVIEW_SCHEMA entry out, so the report reaches every reviewer
    // through the channel they already read. The checker took no route; this did.
    if (premise) checkSidecarPath(baton.id, PREMISE_REVIEWER, premise.sidecarPath)
    const premiseCheckResult = premiseAsReview(baton, premise)
    const premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    if (coverage) checkSidecarPath(baton.id, PLAN_COVERAGE_REVIEWER, coverage.sidecarPath)
    const coverageResult = planCoverageAsReview(baton, coverage)
    const coverageVerdict = coverageResult ? resolveVerdict(coverageResult) : null

    const { reviewers, substitutions } = resolveReviewers(decision.reviewers, plan.reviewSignals)
    // SEQUENTIAL, never parallel — § Design decisions 2. Two reviewers editing one artifact would
    // race, so this baton's reviewers apply and verify one at a time, each reading the ones before
    // it. `pipeline()` with one stage IS a sequential loop; used here (not `parallel()`) because
    // the review AFTER a PIVOT/REJECTED-resolved-to-PIVOT must apply nothing, which the loop
    // below enforces by not dispatching it.
    const reviews = []
    let pivoted = null
    for (const reviewer of reviewers) {
      if (pivoted) {
        // Nothing dispatches after a PIVOT: the plan is going to a replan, and a later reviewer
        // applying findings to a plan about to be discarded produces a document that looks
        // maintained and is not. The pivoting reviewer's own findings, and every prior reviewer's,
        // are already on disk and verified.
        break
      }
      const result = await reviewerAgent(baton, decision, plan, reviewer, trailDir, premise, reviews)
      // The returned path propagates — the sidecar is the agent's own provisioned one and
      // nothing here can resolve it — but it is CHECKED on the way through: a path with no
      // `subagent-share` segment is one `review-findings-ledger` will refuse.
      if (result) checkSidecarPath(baton.id, `review-${reviewer}`, result.sidecarPath)
      // `reviewer` here is the harness-resolved dispatch identity (`resolveReviewers`'s own
      // output, the same value `withRole(reviewer, ...)` dispatches under) — overwrite the
      // agent's self-report with it rather than trust an unverified structured-output field.
      const resolved = result ? resolveVerdict({ ...result, reviewer }) : null
      if (resolved) {
        reviews.push(resolved)
        if (resolved.pivot) pivoted = resolved
      }
    }
    // The plan-coverage pre-flight is appended to `reviews` here, not spliced into the `kept`
    // array below — that array's literal shape is pinned (test_plan_blitz_contract.py) to
    // `[premiseCheckResult, ...reviews]` so a reader can see the premise-check seam without
    // tracing every pseudo-reviewer added since. Appending to `reviews` is not a route-preserving
    // no-op the way the per-reviewer entries already are: this one is resolved on ITS OWN way in,
    // since it never passed through the sequential loop above.
    if (coverageVerdict) reviews.push(coverageVerdict)
    // `reviews` entries are already resolved above (the loop needs their `.pivot` to decide
    // whether to keep dispatching); re-resolving here is a no-op for them and is what resolves
    // the premise-check pseudo-reviewer, which never went through the loop.
    const kept = [premiseCheckResult, ...reviews].filter(Boolean).map(resolveVerdict)
    return {
      decision,
      baton,
      plan,
      reviews: kept,
      premiseCheckVerdict,
      coverageVerdict,
      substitutions,
      premise,
    }
  },
)

// Phase 5b — XS work, executed. LAST, deliberately: planning is read-mostly and this
// phase mutates, so running it after the pipeline means every planner in this wave read a
// tree no sibling was changing underneath it.
// A completed XS lane lands only after `executeReview` ran over its touched files and returned no
// blocking verdict. Every other outcome rewrites the lane to `completed: false`, the one field
// `closableDispatched` and the verdict reconciliation read, so a failed gate never reaches a
// shipped stamp. There is no skip: a missing `executeReview` is itself a failure.
// Failing values of `verdict` per `schemas/review-stage.schema.json`: slice-review-result
// (BLOCKED; WARN is not failing), whole-diff-review-result (REQUIRES_CHANGES, REJECTED) and
// delivery-verdict (FAIL). The prep verdicts are partition advice, and the integration result
// carries no verdict: it fails on confinement_violations or brief_conformance.unmet.
const BLOCKING_REVIEW_VERDICTS = new Set(['BLOCKED', 'REJECTED', 'REQUIRES_CHANGES', 'FAIL'])

function reviewBlockers(result) {
  const wave = (result && result.wave) || []
  const integration = result && result.integration
  const missing = wave.filter((leg) => !leg).length
  const blocked = wave.filter(
    (leg) => leg && BLOCKING_REVIEW_VERDICTS.has(String(leg.verdict || '').toUpperCase()),
  )
  if (integration) {
    const unmet = Number((integration.brief_conformance || {}).unmet || 0)
    if (Number(integration.confinement_violations || 0) > 0 || unmet > 0) {
      blocked.push({
        verdict: 'FAIL',
        summary: `integration: ${integration.confinement_violations || 0} confinement violation(s), ${unmet} unmet brief item(s)`,
      })
    }
  }
  return { missing, blocked }
}

async function reviewedDispatch(decision) {
  const baton = batonFor(decision)
  const lane = await executor(baton, decision, trailDir)
  if (!lane || !lane.completed) return lane
  const failClosed = (reviewGate) => ({
    ...lane,
    completed: false,
    reviewGate,
    blockedReason: `XS review gate failed closed: ${reviewGate}`,
  })
  const touchedFiles = lane.filesChanged || []
  // A confirm-and-close that cites its shipped commit lands no code: nothing to review.
  if (!touchedFiles.length && lane.priorShippedIn) return lane
  if (!touchedFiles.length) {
    return failClosed('executor reported no touched files, so nothing landed and no review ran')
  }
  if (typeof executeReview !== 'function') {
    return failClosed('executeReview is not defined in this fire, so the XS lane cannot be reviewed')
  }
  let result
  try {
    result = await executeReview({ batonId: baton.id, declaredPaths: touchedFiles })
  } catch (err) {
    return failClosed(`executeReview threw: ${(err && err.message) || String(err)}`)
  }
  const { missing, blocked } = reviewBlockers(result)
  if (!result || missing) {
    return failClosed(`${missing || 'all'} review leg(s) returned nothing, so the review did not complete`)
  }
  if (blocked.length) {
    return failClosed(`review verdict failing: ${blocked.map((b) => `${b.verdict} ${b.summary || b.reviewer || 'unnamed leg'}`).join('; ')}`)
  }
  return lane
}

const dispatched = (await pipeline(dispatchable, reviewedDispatch)).filter(Boolean)

// Each reviewer applies and verifies its own findings now, so there is no separate integration
// pass to render — a reviewer's own line already carries its verdict and sidecar, and the gate
// reads "did the ledger verify" off the reviewer, not off a downstream applier.
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

// Phase 5c — prep-gate revise-in-place. The readiness gate cannot run the mise-prep bar (no
// fs/CLI primitive here), so one sonnet agent per authored plan measures it, applies ONLY the
// findings the engine marks `mechanical` by following their `repair`, and re-gates ONCE. One loop,
// never two: a plan still NOT-PREPPED after it is pulled with the gate report attached.
function prepGateRevise(baton, plan, trailDir) {
  return trackAgent('prep-gate-revise', agent(
    `Run the mise-prep gate over one authored plan and repair what is mechanically repairable.

Baton: ${baton.id} — "${baton.title}"
Plan: ${plan.planPath}

${CLI_RESOLUTION_RULE}

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

REFUSED or a CLI failure is reported as such in \`before\`/\`after\`; do not retry or work around it.
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'prep-gate-revise'))}`,
    // Enricher, not executor: block_subagent_plan_body_write denies an executor every plan-body
    // edit, which would leave this loop able to name a mechanical repair but never apply it.
    { model: 'sonnet', ...withRole('coordinator:enricher'),
      label: `prep-gate:${baton.id}`,
      phase: 'Prep gate',
      schema: PREP_GATE_REVISE_SCHEMA,
    },
  ))
}

const prepGateById = new Map()
await Promise.all(
  chains
    .filter(Boolean)
    .filter(({ plan }) => plan && plan.status !== 'blocked' && plan.planPath)
    .map(async ({ baton, plan }) => {
      const result = await prepGateRevise(baton, plan, trailDir)
      if (result) prepGateById.set(baton.id, result)
    }),
)

function prepGateLine(batonId) {
  const r = prepGateById.get(batonId)
  if (!r) return null
  const repaired = (r.repaired || []).length ? ` repaired: ${r.repaired.join('; ')}` : ''
  const report = r.after !== 'PREPPED' && r.gateReport ? `\n      gate report: ${r.gateReport}` : ''
  return `${r.before} -> ${r.after}${repaired}${report}`
}

// Phase 6 — the EM's terminal gate, over the trail rather than over the agents' summaries.
const trailLines = chains
  .filter(Boolean)
  .map(({ decision, baton, plan, reviews, premiseCheckVerdict, substitutions, premise }) => {
    // Every reviewer is named with their OWN resolved verdict. A collapsed
    // "the review said X" is how a wave loses the review that disagreed.
    const verdicts = reviews.map((r) => `${r.reviewer}=${r.verdict}`).join(', ') || 'none ran'
    // Explicit row so "premise check ran and found nothing" and "premise check did not run"
    // (null/malformed return, dropped upstream) render as visibly different states, never as the
    // same silence. An `OK` with zero citations examined must not render like an `OK` that checked
    // everything; `citationsChecked` carries that count.
    const premiseCheckLine = premiseCheckVerdict
      ? `${premiseCheckVerdict.verdict}${premiseCheckVerdict.citationsChecked === 0 ? ' (0 citations examined — UNATTEMPTED, not a clean pass)' : ''}${premiseCheckVerdict.premiseFailure ? ` premise-failure: ${premiseCheckVerdict.premiseFailure}` : ''}`
      : 'DID NOT RUN — no premise-check verdict reached the trail for this baton'
    const pivots = reviews.filter((r) => r.pivot)
    const blockers = reviews.filter((r) => r.verdict === 'BLOCKED')
    // A mixed set is called out by name rather than left for the gate to notice. It is
    // the case a fast read most reliably flattens: seeing one PIVOT, a reader stops
    // reading, and the co-reviewer's fixable findings — the replan's actual inputs —
    // never reach the brief.
    const mixed = pivots.length && reviews.length > pivots.length
      ? `\n      MIXED SET: ${pivots.map((r) => r.reviewer).join(', ')} pivoted; `
        + `${reviews.filter((r) => !r.pivot).map((r) => `${r.reviewer}=${r.verdict}`).join(', ')} did not. `
        + `Both survive — the pivot decides the ROUTE, the rest are the replan's inputs.`
      : ''
    const aliases = reviews.filter((r) => r.aliased)
    return `  - ${baton.id} "${baton.title}" [${decision.tshirt}, ${decision.route}]
      plan: ${plan ? plan.planPath : '(not written)'}${plan && plan.status === 'blocked' ? ` — BLOCKED: ${plan.blockedReason}` : ''}${plan && plan.planPathCorrected ? `\n      planPath CORRECTED: planner returned ${plan.planPathCorrected} (a trail sidecar); the baton's own plan path was used instead` : ''}${substitutions && substitutions.length ? `\n      reviewer substitution: ${substitutions.join('; ')}  <-- the plan was NOT reviewed by whom the em named` : ''}
      premise-check: ${premiseCheckLine}
      reviews: ${verdicts}${pivots.length ? `  <-- PIVOT (${pivots.map((r) => r.reviewer).join(', ')})` : ''}${blockers.length && !pivots.length ? '  <-- BLOCKED, fixable' : ''}${mixed}${aliases.length ? `\n      alias resolved: ${aliases.map((r) => `${r.reviewer}: ${r.aliased}`).join('; ')}` : ''}
      ${reviews.map((r) => `sidecar: ${r.sidecarPath}${r.premiseFailure ? ` premise-failure: ${r.premiseFailure}` : ''}${r.alternativesConsidered ? ` alternatives: ${r.alternativesConsidered}` : ''}`).join('\n      ')}
      premise rows: ${premiseLines(premise).split('\n').join('\n      ')}
      findings ledgers: ${ledgerLine(plan, reviews)}${prepGateLine(baton.id) ? `\n      prep gate (after reviewers, one revise-in-place loop): ${prepGateLine(baton.id)}` : ''}`
  })
  .join('\n')

const dispatchedRows = dispatched.map((d) => `  - ${d.batonId}: ${d.completed ? 'completed' : 'INCOMPLETE'} — ${d.summary}${d.blockedReason ? ` [blocked: ${d.blockedReason}]` : ''}
      files: ${(d.filesChanged || []).join(', ') || '(none — a closure, not a change)'}`).join('\n')
const dispatchedSection = dispatched.length ? `XS batons DISPATCHED in this wave (no plan, work already done):
${dispatchedRows}

For each of these the question is different: did it do what the baton asked, and is the baton now
closable? An INCOMPLETE one, or one that grew past XS, is a sizing defect to report — say so.

**The word for a closable dispatch is \`ready\`, and only that word closes it.** There is no fourth
verdict meaning "done" — the three below are the whole vocabulary, and \`ready\` on a \`dispatch\`
route does not mean "ready to execute later", it means LAND IT: \`blitz_land\` stamps the baton
\`shipped\` with the wave's \`shipped_in\` SHA, which is what makes it terminal (§ Three lanes).
\`pulled\` on a completed dispatch is the recycling defect wearing a verdict: landing leaves the
baton where it is, the gate returns it as a candidate, and the next wave re-scouts work that is
already on disk. Measured 2026-09-10, wave 0 of run 20260910T000000Z: five dispatched batons came
back \`pulled\` with reasons that each read "Complete and closable", and the landing closed none of
them. If your reason says the baton is closable, the verdict is \`ready\`. Reserve \`pulled\` for a
dispatch that did NOT finish its remit, and \`replan\` for one whose remit was wrong.` : ''

// HOST AVAILABILITY is deliberately NOT reconciled below, and the absence is a decision rather
// than an oversight. Two reasons, both structural:
//
//   1. NO FILESYSTEM. Whether a plan's withheld rows sit behind a DECLARED `external_gate` naming
//      a host is a fact in the plan file, and this script has no fs primitive
//      (WORKFLOW-AGENT-AS-FILE-HANDLE). The premise pass could be asked to report it, the way it
//      reports `spinePresent` — but that only supplies the predicate, not the verdict.
//   2. THE DIRECTION IS WRONG. Every reconciliation in this file makes a verdict STRICTER: ready
//      to pulled, ready to replan. That is what makes them safe to run over the one reader with a
//      standing incentive to call a plan ready. Reconciling a host-grounded pull back UP to
//      `ready` would run WITH that incentive, and it would have to decide it from the EM's own
//      free-text `reason` — keyword-matching prose to promote a verdict. A plan wrongly pulled
//      comes back next wave; a plan wrongly promoted is stamped `approved` and dispatched.
//
// So the brief below carries it in as many words instead. Measured 2026-09-10 on project-rag wave
// 1: `dlv-windows-hosted-corpus-reindex-and-cross-h-4a1c73` was pulled because the executing box
// was Linux while its own declared `external_gate` withheld 8 of 13 rows for the Windows corpus
// host, and `cq-17` was pulled for serialising behind it. Both plans were ready to execute on the
// host they name. Tripwire: THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON.
//
// The inverse claim is bounded the same way: a pull (or a dispatched baton's `blockedReason`)
// that says human-only, second person, or other host must carry the missing capability on THIS
// host and the command that proved it (HUMAN_ONLY_PULL_RULE). The brief states that an unprobed
// reason is invalid; like the rest of this block it is a brief rule, not a keyword reconciliation
// over free text.

const readiness = await trackAgent('readiness-gate', agent(
  `phase: readiness-gate

${ROLE_CONTRACTS['blitz-em']}

You are the blitz-em for plan-blitz wave ${waveIndex}, at its terminal gate. Every plan below was
written, reviewed and integrated without consulting you — that is by design. Your job is to pull
items OUT, over the trail.

Trail directory: ${trailDir}
This fire's own records: ${trailDir}/${waveSlot}
Gate report this wave was resolved from: ${GATE_REPORT_LABEL}

THE TRAIL DIRECTORY IS SHARED, AND YOUR MANDATE IS THE LIST BELOW — NOT THE DIRECTORY. A wave
larger than one fire is drained by SEVERAL fires at this same waveIndex, all writing into that one
trail, and they may be running CONCURRENTLY. So the trail holds sidecars for batons that are not
yours: some belong to a fire that already landed, some to a fire that is still authoring its plans
right now. Each fire's records sit in ITS OWN subdirectory of the trail, named above for yours, so
a baton this fire re-plans does not overwrite what an earlier wave recorded about it — search the
trail RECURSIVELY, and a second directory holding the same baton is an earlier wave's verdict, not
a duplicate to reconcile. Judge EXACTLY the batons enumerated below and no others. Read another baton's sidecar
if it informs one of yours — that costs nothing — but never return a verdict for it. A verdict on
a baton outside this fire either overrides a landing that already happened or stamps a plan whose
author has not finished writing it, and both read as ordinary output.

${trailLines}

${dispatchedSection}

One question per plan: is it ready to execute? Answer ready, pulled, or replan — and give a reason
that names the evidence. "Looks off" is not a disposition. (A dispatched XS baton is not a plan and
that is not its question — see the block above for the one it does answer.)

**Ready to execute means ready for whoever runs it, NOT runnable here, now, by you.** This is a
PLANNING gate; the execution gate is a different question asked later, by a different surface —
tripwire A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE. **Host and platform availability on this box is
therefore never a pull reason.** A plan whose rows are withheld behind a declared \`external_gate\`
for a host this box is not IS READY, and you say so: those withheld rows are a schedule fact, the
same way a non-empty \`mise_prepped_findings\` is a schedule fact and never a failure. You do not
need a Windows box to plan for Windows any more than you need POSIX to plan for POSIX. A plan
pulled for the box it was planned on is a plan re-planned identically next wave, on a box that is
just as likely to be the wrong one.

**\`external_gate\` is a SPINE-ROW field, and on a BATON it is inert.** Do not tell anyone to
declare one on a baton record so the gate stops re-offering it: \`roadmap.plan_gate\` never reads
the key — candidacy is \`live\`, \`baton_role\`, \`status\` and \`deployment_state\`, and its scanner
declares every baton key it reads, so one absent from that set reads as absent from the record.
The write produces well-formed frontmatter, changes nothing, and leaves the baton recycling with an
apparent fix in place, which is worse than the open defect: the next wave's EM reads the field and
concludes the question is settled. Measured by example-game-workbench-repo-b8, who was given this
no-op by two independent wave EMs. What suppresses a baton is a HOLD —
\`plan_blitz_hold_reason\`, which the gate reads and reports under \`held\`. A \`blocked_by\` edge
is not the alternative: an edge is a DISCOVERED dependency, and one the gate cannot resolve fails
the baton closed forever. See the skill's § Read the gate.

Pull for properties of the PLAN: a finding a reviewer logged but did not apply, a ledger that does
not verify, acceptance criteria that contradict each other or the baton.
"The rows cannot execute on this box" is a property of the box, and the plan already declared it.

${HUMAN_ONLY_PULL_RULE}
Apply it to your own reasons and to every dispatched baton's \`blockedReason\` above: a human-only,
second-person, or other-host reason that names no missing capability on this host and no probe
command is an INVALID pull. Treat that baton on its merits instead — an EM-owned open question is
decided here, and a verification an agent can drive is not a human gate.

**Records sharing a \`deliverable_id\` are a continued lineage, not a duplicate.** The id is the
thread tying every stage of one deliverable together, so each successor keeps its predecessor's —
that is the whole point of the field, and the engine's own resolvers key on the id alone with no
lineage awareness, so reading them without knowing this lands exactly here. Before you call it a
record defect, check what the other holders ARE: archived, \`deployment_state: continued\` stages
are the expected shape and the resolver picked correctly.

**Report a record anomaly; never prescribe its repair, and never one that edits an identity
field.** The observation costs a reader a minute. The prescription is the hazard: it arrives
inside the strongest-sounding verdict a gate can write ("break-class record defect confirmed
against the tree"), and a second claim resting on it — that some gate reopens once the fix lands —
turns a remark into an instruction with a payoff attached. The engine's one instrument in this
territory, \`coordinator_core/ops/deliverable_fork_detect.py\`, is deliberately built to report and
not resolve: it emits a family and its evidence paths with no \`winner\` field and no
\`superseded_by\` slot, so a shape with nowhere to put a winner cannot silently grow one. Match
that posture. Measured on project-rag-ue-addon wave 1, baton cpr-22, where the gate recommended
deduplicating a healthy lineage — and the second file it named did not even carry the contested
id.

The \`prep gate\` line on a plan is the mise-prep bar measured AFTER the reviewers, with its
mechanical findings already repaired once. \`after\` is the verdict that decides: a plan whose
\`after\` is not PREPPED is pulled, with the gate report attached to your reason. It is mechanically
enforced after you answer (a \`ready\` on it is rewritten to \`pulled\`), and there is no second loop.

Open the sidecars. A summary line saying OK is not evidence anyone checked — a reviewer can
confirm an author's prose without opening the code that would falsify it. Spot-check one
substantive claim per plan against the tree.

**Cross-plan seams are yours; no reviewer sees across plans.** Over this wave's plans and their
approved blockers, check two things: every export one plan needs from another is promised by that
other plan, and no two plans' spine \`writes:\` collide (nor does a plan write a file a sibling
declares without declaring it). A hit is a pull naming both plans, the file or export, and the
one-line repair; the pulled plan is revised in place, not rewritten.

The premise check makes no claim about the plan. The \`premise-check\` verdict on the reviews line
is the wave's routing of its rows, not the checker's opinion: BLOCKED means citations did not
resolve, and a clean table says one class of false premise is absent — never that the plan is
right, and never a reason to shorten your read. The \`premise rows\` block is where the signal is.
Its UNCHECKABLE rows are assumptions nothing in this tree settled, carried forward openly rather
than passed; a class its coverage line renders "none" was never attempted — a hole, not a pass;
and its falsifier-arming line is the highest-value entry, because a plan whose instrument cannot
report red has no evidence behind whatever it claims that instrument will show.

The \`findings ledgers\` line is a RECORD, not an approval. Each reviewer applied its own findings
in place and verified its own ledger — there is no separate integration pass, and no escalation
lane behind it. Judge the applied edits like any other change to the plan: open the sidecar,
check the ledger's before/after rows against what is actually in the plan now, and pull with a
reason if an edit reads wrong. A reviewer that suspended its findings under PIVOT is a signal to
read alongside the pivot itself, not a separate concern.

BLOCKED and PIVOT are different questions, and the trail above keeps them apart per reviewer.

A BLOCKED review is not a reason to withhold ready. It says the plan was wrong until the findings
were fixed; the reviewer that found them has already fixed them, in place. Judge the plan AS
REVISED — check that the findings were actually applied, and if they were, a plan whose every
review was BLOCKED is a normal ready.

Any plan whose review set contains a PIVOT: verdict replan. It is not yours to override here — an
override needs explicit PM agreement recorded verbatim beforehand, and there is no PM in this
wave. This is also enforced mechanically after you answer: a \`ready\` on a pivoted plan is
rewritten to \`replan\` and your disagreement is recorded in the trail rather than acted on. Spend
your attention on the replanBrief instead of on the route.

Write the replanBrief for a session that will NOT have this context: what the baton was trying to
achieve, the pivoting reviewer's premise-failure rationale verbatim, their alternatives, and the
question a replan has to answer differently.

On a MIXED SET — one reviewer pivoted, another returned OK/WARN/BLOCKED — the brief must carry
BOTH. The co-reviewer's findings were suspended, not answered, and they are the most concrete
thing the replan inherits: a brief holding only the pivot rationale throws away a whole review
that nobody will run again. Name each surviving finding and its reviewer.
${REPO_ROOT_RULE}
${NO_EXECUTION_RULE}`,
  { model: 'opus', ...withRole('coordinator:blitz-em'),
    label: `readiness:wave-${waveIndex}`,
    phase: 'Readiness gate',
    schema: READINESS_SCHEMA,
  },
))

// WAVE RESULT — the caller stamps `ready` plans to `approved` (which is what opens the NEXT
// wave's planning gates), mints a baton per `replan` entry, and re-queues both `pulled` and
// `replan` for a later wave. `surfacedToPm` never re-queues on its own: it needs a PM answer
// first, and a wave that silently retried it would be answering for them.
// Each verdict carries the ROUTE its baton was finalised at, joined here rather
// than asked of the EM: the landing branches on it (spec-dispatch parks a spec and
// stamps execution-ready; everything else takes the ordinary approval), and asking
// an agent to restate data the wave already holds is how the two copies drift.
const routeById = new Map(decisions.map((d) => [d.batonId, d.route]))
const reviewsById = new Map(chains.filter(Boolean).map(({ baton, reviews }) => [baton.id, reviews]))
const premiseById = new Map(
  chains.filter(Boolean).map(({ baton, premise }) => [baton.id, premise || null]),
)
// Whether a reviewer ran for this baton, and — where none did — whether a plan existed for one to
// run over. The two are stored apart because they are two different silences: no plan is the
// chain declaring it had nothing to review, while a plan with no reviewer is the pass going
// missing over a document that exists. Keyed off `chains`, so a baton that never entered the
// planning pipeline (an XS, a baton this fire did not hold) is ABSENT from this map and untouched
// by the reconciliation below, rather than defaulting to either silence. `reviews` excludes the
// premise-check pseudo-reviewer, which never applies findings.
const reviewedById = new Map(
  chains.filter(Boolean).map(({ baton, plan, reviews }) => [baton.id, {
    ran: (reviews || []).some((r) => r.reviewer !== PREMISE_REVIEWER),
    planWritten: Boolean(plan && plan.status !== 'blocked'),
  }]),
)

// The plan this fire actually authored, per baton -- the only reader of `planPath` that is not a
// prose-driven agent. `roadmap.blitz_land` resolves every plan-carrying lane through this field and
// refuses the row outright without it ("verdict carries no planPath"), so a gate that narrates its
// verdict and forgets to echo the path costs the whole fire: measured on claude-klabauter, a fire
// landed 0/0/0 with four refusals after 31 agents, every plan on disk and every verdict sound. The
// path is knowable here without asking anyone, so it is written here rather than gated on recall.
const planPathById = new Map(
  chains
    .filter(Boolean)
    .map(({ baton, plan }) => [baton.id, (plan && plan.planPath) || baton.planPath || null])
    .filter(([, p]) => p),
)

// A PIVOT routes MECHANICALLY. The gate brief already says an EM may not override one,
// and a rule only a prompt enforces is discharged by nobody — least of all by the one
// reader with a standing incentive to call a pivoted plan ready, since `ready` is the
// verdict that makes a wave look productive. So the route is reconciled here, over the
// structured review output the wave already holds, and the override is RECORDED rather
// than quiet: `pivotOverride` carries the EM's own verdict into the trail so a
// disagreement stays visible instead of being erased by the thing that corrects it.
// THE RULE ABOVE IS ENFORCED HERE, not left to the brief. A shared trail plus concurrent fires
// means the gate can see, and has returned, verdicts for batons belonging to other fires.
// Measured on this repo: one fire's gate returned `ready` for a baton a PREVIOUS fire had pulled,
// and `replan` for two batons a CONCURRENT fire was still authoring plans for — landing that
// verbatim would have minted replan batons against live work and reversed a completed landing.
// Dropped rather than trusted, and reported rather than dropped silently: `foreignVerdicts` puts
// them in the wave result so the caller sees what this fire declined to judge.
const fireBatonIds = new Set(batons.map((b) => b.id))
const foreignVerdicts = ((readiness && readiness.verdicts) || [])
  .filter((v) => !fireBatonIds.has(v.batonId))
  .map((v) => ({ batonId: v.batonId, verdict: v.verdict, droppedBecause: 'not a member of this fire' }))

// The dispatched XS work, by baton, so a verdict row can carry the one field only the DISPATCH
// knows. `closableDispatched` synthesises a row for every completed XS the gate did NOT judge and
// puts `priorShippedIn` on it; when the gate DOES return a verdict for one — which it routinely
// does, since the trail shows it the dispatch — that row is built here instead and the field was
// silently absent from it. `blitz_land` reads `priorShippedIn` off the READY row, so all three of
// this run's fire-0-14 confirm-and-close batons were refused for want of a SHA each one was
// carrying. Two paths to one row, one of them lossy: the same shape as every other defect this
// file has been repaired for today.
const dispatchedById = new Map(
  (dispatched || []).filter((d) => d && d.batonId).map((d) => [d.batonId, d]),
)

const verdicts = ((readiness && readiness.verdicts) || []).filter((v) => fireBatonIds.has(v.batonId)).map((v) => {
  const reviews = reviewsById.get(v.batonId) || []
  const dispatchRow = dispatchedById.get(v.batonId)
  const entry = {
    ...v,
    route: routeById.get(v.batonId) || null,
    // Verbatim, unvalidated, and only where the dispatch actually completed — the landing owns the
    // check and falls back to its own SHA. An incomplete dispatch has no commit to cite and must
    // not acquire one here.
    ...(dispatchRow && dispatchRow.completed && dispatchRow.priorShippedIn
      ? { priorShippedIn: dispatchRow.priorShippedIn }
      : {}),
    // This fire's own record of the plan wins over the gate's echo of it. An XS carries none and
    // stays null; a gate that named a DIFFERENT path than the one the planner wrote was naming a
    // plan this fire did not author. Recorded repo-relative whatever spelling the planner echoed:
    // its brief names a new plan by absolute path so the agent resolves it against the right
    // checkout, and that host path is then committed state no other box can open.
    planPath: repoRelativeCitation(planPathById.get(v.batonId) || v.planPath) || null,
    // Carried so the LANDING can refuse independently. `roadmap.blitz_land` re-checks
    // this and will not stamp a plan a reviewer pivoted, whatever this workflow decided
    // — two enforcement points, because the one in a file an agent edits is the one
    // that goes missing.
    reviewVerdicts: reviews.map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
  }
  // A lane whose review gate failed closed is never `ready`, whatever the gate agent concluded.
  if (dispatchRow && dispatchRow.reviewGate && entry.verdict === 'ready') {
    return {
      ...entry,
      verdict: 'pulled',
      reviewOverride: `XS review gate failed closed: ${dispatchRow.reviewGate}. Reconciled to pulled.`,
      reason: `${entry.reason} [reconciled: XS review gate failed closed]`,
    }
  }

  // SPINE, reconciled mechanically for the same reason the pivot is: a plan with no
  // `plan-tasks` block declares no work a run can schedule, the planner brief says so, and
  // nothing between authoring and the mise-prep gate checks it. Measured 2026-09-10: a
  // 869-line plan with zero fenced blocks passed premise-check, two reviewers, integration,
  // escalation resolution and the readiness gate, landed `approved`, and was refused a
  // ceremony later with SPINE/spine-absent. The gate is the wrong reader for this — it is the
  // one with a standing incentive to call a plan ready — so the premise pass reports it and
  // the reconciliation happens here.
  const premiseRow = premiseById.get(v.batonId)
  if (premiseRow && premiseRow.spinePresent === false && entry.verdict === 'ready') {
    return {
      ...entry,
      verdict: 'pulled',
      // Names its SOURCE, not just its claim. The old wording was a flat assertion about the
      // document ("the plan carries no plan-tasks spine"), which reads as a finding rather than
      // as one reader's report — so a driver had no way to tell a measurement from a guess, and
      // the field behind it appears in no sidecar. Whoever reads this next can now re-run the
      // one check that produced it.
      spineOverride:
        'EM returned ready; the premise check reported plan-spine-check NO-SPINE for this plan. '
        + 'Reconciled to pulled. VERIFY BEFORE ACTING ON IT: re-run plan-spine-check against the '
        + 'plan, and if it reports VALID this override is wrong and the EM verdict stood.',
      spinePresentSource: premiseRow.sidecarPath || null,
      reason: `${entry.reason} [reconciled: premise check reported no plan-tasks spine — nothing to schedule]`,
    }
  }

  // REVIEW, reconciled mechanically for the same reason every other reconciliation here exists: a
  // missing review pass is INDISTINGUISHABLE AT THE RETURN from a review that ran and found
  // nothing, so whichever default the reading lane happens to hold becomes the verdict. Each
  // reviewer now applies its own findings, so "did the pass run" is simply "did a reviewer run
  // over this plan" — no separate report to go missing between the review and a later applier.
  //
  // A plan the planner never wrote is NOT this case — the chain carries it blocked, with nothing
  // for a reviewer to open, and `planWritten` is how the two are told apart rather than folded
  // into one silence.
  const reviewRow = reviewedById.get(v.batonId)
  if (reviewRow && reviewRow.planWritten && entry.verdict === 'ready' && !reviewRow.ran) {
    return {
      ...entry,
      verdict: 'pulled',
      reviewOverride:
        'EM returned ready; the plan was written and no reviewer ran over it, so no finding is '
        + 'known to have been applied. Reconciled to pulled.',
      reason: `${entry.reason} [reconciled: no reviewer ran over a plan that exists]`,
    }
  }

  // PREP GATE, reconciled mechanically: the re-gate verdict decides. Only a measured non-PREPPED
  // `after` pulls; a plan with no prep-gate row (blocked, not authored this fire) is untouched.
  const prepRow = prepGateById.get(v.batonId)
  if (prepRow && prepRow.after !== 'PREPPED' && entry.verdict === 'ready' && !reviews.some((r) => r.pivot)) {
    return {
      ...entry,
      verdict: 'pulled',
      prepGateOverride:
        `EM returned ready; plan.prep_gate was ${prepRow.before} before and ${prepRow.after} after `
        + 'the one revise-in-place loop. Reconciled to pulled.',
      prepGateReport: prepRow.gateReport || null,
      reason: `${entry.reason} [reconciled: prep gate ${prepRow.after} after revise — ${prepRow.gateReport || 'see gate report'}]`,
    }
  }

  const pivots = reviews.filter((r) => r.pivot)
  if (!pivots.length || entry.verdict !== 'ready') return entry
  const who = pivots.map((r) => r.reviewer).join(', ')
  return {
    ...entry,
    verdict: 'replan',
    pivotOverride: `EM returned ready; ${who} returned PIVOT. Route reconciled to replan.`,
    reason: `${entry.reason} [reconciled: ${who} pivoted]`,
    // The EM wrote no brief for a plan it thought was ready, so one is synthesised from
    // the review set — EVERY review, not only the pivoting one, because the co-reviewers'
    // findings are what the replan inherits.
    replanBrief:
      entry.replanBrief ||
      `Reconciled from a ready verdict the review set contradicts.\n`
        + reviews
          .map((r) => `${r.reviewer} [${r.verdict}]: ${r.premiseFailure
            || `${r.findingCount || 0} finding(s), see ${r.sidecarPath}`}${r.alternativesConsidered ? ` | alternatives: ${r.alternativesConsidered}` : ''}`)
          .join('\n'),
  }
})
const closable = closableDispatched(dispatched, verdicts, waveIndex)

// ---------------------------------------------------------------------------
// Phase 7 — Adjudicate: nothing reaches the PM without an adjudicator's verdict
// ---------------------------------------------------------------------------

const ADJUDICATORS = {
  scope: 'coordinator:apm',
  code: 'coordinator:staff-eng',
  'data-science': 'coordinator:staff-data-sci',
  'front-end': 'coordinator:senior-front-end',
  ux: 'coordinator:staff-ux',
}

// Named irreversible or external-facing gates. An entry whose text names one stays `pm_only` whatever
// the adjudicator's verdict says: a ruling clears a decision, never a merge, publish or push to main.
const IRREVERSIBLE_GATE = /\b(merge[ds]? (to|into) main|push(ed|ing)? to main|force-push|publish(ed|ing)?|release|cross-repo commit|branch deletion|history rewrite|rewrite history)\b/i

function adjudicate(entry, kindLabel) {
  const baton = batonFor(entry)
  const agentType = ADJUDICATORS[entry.adjudicatorClass] || ADJUDICATORS.scope
  const question = entry.surfacedQuestion || entry.rationale || entry.reason || '(no question stated)'
  return trackAgent(`adjudicator:${entry.batonId}`, agent(
    `phase: adjudicate

You are the PM's delegate for one matter in a plan-blitz wave. Nobody escalates to the human here:
a scope, direction or priority matter is yours as the APM, a code matter is yours as the domain
reviewer. Rule it, do not re-ask it.

Baton: ${entry.batonId}${baton ? ` — "${baton.title}" (${baton.path})` : ''}
Route: ${entry.route}   Size: ${entry.tshirt}   Surfaced as: ${kindLabel}
Question: ${question}
Blitz-em rationale: ${entry.rationale || '(none)'}

Do this:
  1. Read the baton and what it cites. Decide the question with what is on disk.
  2. Write one line on the baton record: \`pm_ruling: "${agentType.replace('coordinator:', '')} (PM-delegated) <your ruling>"\`.
  3. Return verdict 'ruled' and pmOnly false.

Return pmOnly true (verdict 'pm-only', with pmOnlyGround) ONLY when the matter is important AND urgent
AND has no clear right answer, or needs an external or irreversible action (merge, publish, push to
main, cross-repo commit assent). Being unsure is not a ground. Nobody confirms a right answer; the PM
reads the ruling at the receipt.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, entry.batonId, 'pm-adjudication'))}`,
    { model: 'opus', ...withRole(agentType),
      label: `adjudicate:${entry.batonId}`,
      phase: 'Adjudicate',
      schema: ADJUDICATION_SCHEMA,
    },
  )).then(
    (v) => ({ agentType, verdict: v, error: null }),
    (err) => ({ agentType, verdict: null, error: String((err && (err.message || err.error)) || err).slice(0, 500) }),
  )
}

// A PM-bound entry leaves the wave as `pm_only` only. A missing verdict fails closed (the entry
// stays PM-bound, carrying `verdict: 'unavailable'` and the failure's message as `error`), and a
// named irreversible gate overrides a `pmOnly: false` ruling.
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
const settled = await Promise.all(
  pmBound.map(async ({ entry, kind }) => ({
    kind,
    entry: settleAdjudication(entry, await adjudicate(entry, kind)),
  })),
)
const settledIds = new Set(settled.map((x) => x.entry.batonId))
const residueSurfacedToPm = settled.filter((x) => x.entry.adjudication.pmOnly).map((x) => x.entry)
const adjudicated = settled.filter((x) => !x.entry.adjudication.pmOnly).map((x) => x.entry)
const residueRoutedElsewhere = routedElsewhere.filter((r) => !settledIds.has(r.batonId))

return {
  waveIndex,
  trailDir,
  // The code this wave ran, echoed back verbatim from what the emitter stamped. A fire is a FROZEN
  // COPY of this file with its args bound in, so two waves of one run can behave differently with
  // nothing about the batons changing — and before this, nothing in either result said so. Written
  // by `emit-wave-fire :: _engine_ref` because the emitter is the only actor here that can see
  // a repo: this script has no filesystem primitive and could not compute it if it wanted to.
  // Absent on a fire emitted before this field existed, which is itself the version signal — and
  // is why it is echoed rather than defaulted to a plausible-looking unknown.
  ...(parsedArgs.engineRef ? { engineRef: parsedArgs.engineRef } : {}),
  // Declared, never inferred. `completed: false` plus a reason is what the landing refuses on, and
  // it is set from the incident log rather than from any lane being empty — a wave can finish
  // cleanly and legitimately open nothing, and that one must still land. Omitted entirely on a
  // clean run, so a result carrying no claim is treated as complete.
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
      // The rows themselves: the count says the wave is unlandable, the detail says which role to
      // look at first.
      agentIncidents,
    }
    : {}),
  // The leaf of `trailDir` this fire's own trail records were written into. Reported because the
  // trail is shared: a caller handed only `trailDir` cannot tell this fire's planning report for
  // a baton from the one an earlier wave wrote for the same baton.
  trailSlotDir: `${trailDir}/${waveSlot}`,
  ready: [...verdicts.filter((v) => v.verdict === 'ready'), ...closable],
  pulled: verdicts.filter((v) => v.verdict === 'pulled'),
  replan: verdicts.filter((v) => v.verdict === 'replan'),
  // PM residue only: entries an adjudicator marked `pm_only` (or that named an irreversible gate,
  // or whose adjudicator returned nothing). Every entry carries its `adjudication`.
  surfacedToPm: residueSurfacedToPm,
  // PM-bound entries an adjudicator ruled on, each carrying `adjudication` and the `pm_ruling` it
  // wrote on the baton. The PM reads these at the receipt; nothing re-asks them.
  adjudicated,
  // Verdicts this fire's gate returned for batons that are not its own, dropped before they
  // could reach the landing. Non-empty means the gate over-reached its fire — usually because a
  // concurrent fire is writing into the same shared trail. Carried so the caller can see what
  // was declined rather than discovering it as a silent absence.
  foreignVerdicts,
  // Second and later decisions the em returned for a baton it had already decided, dropped before
  // planning or dispatch. Non-empty means one baton would otherwise have run twice in this slot.
  duplicateDecisions,
  // Plannable batons the wave could not scaffold a sizing object for, each with the reason the em
  // gave. Reported at the top level because the consequence is NOT in this wave: the plan lands
  // fine, and the refusal arrives a ceremony later from the prep gate, against
  // `prime_exit_criterion.derived_from`, naming a field nobody mis-authored. A driver reading this
  // row knows the plan is uncertifiable before mise-prep tells them, and knows why.
  sizingObjectAbsences: decisions
    .filter((d) => d && !d.sizingObject && PLANNABLE_ROUTES.has(String(d.route)))
    .map((d) => ({
      batonId: d.batonId,
      route: d.route,
      // An unstated reason is itself the finding: it means the wave recorded an absence and
      // nobody can tell whether the route owed no sizing or a tool refused to write one.
      reason: d.sizingObjectAbsence || '(NOT STATED — the em returned a bare null on a plannable '
        + 'route, so it is unknown whether no sizing was owed or a scaffold was refused)',
    })),
  // XS work this wave actually finished, rather than handing back.
  dispatched,
  // Sized and routed, but neither planned nor dispatchable here — including an
  // XS whose EXECUTION gate is shut. Each names the room it belongs in.
  routedElsewhere: residueRoutedElsewhere,
  // Every phase whose returned `sidecarPath` carries no `subagent-share` segment. Not a lost
  // review — the findings are there — but a review whose ledger `review-findings-ledger` will
  // refuse to verify, so nothing else reports that.
  unreachableSidecars,
  // Sidecars whose holder segment disagrees with what the rest of this fire returned — a
  // mistyped path in an agent's own structured result, which the next agent is handed verbatim
  // and opens as a directory that does not exist. Same loss as above and the same silence: the
  // review ran and its file is on disk under the true holder, and only the disposition is gone.
  divergentSidecars: divergentSidecarHolders(),
  // SINGLE-PLAN MODE's `kind: plan` DoE wake digest (§ Pinned interfaces / C4 body item 5),
  // wired here — after the gate has resolved this baton's verdict — so it renders what the wave
  // actually decided rather than re-deriving it. Wave mode assembles no digest (§ body item 7
  // reserves that for a caller iterating every baton).
  ...(SINGLE_MODE
    ? {
      digest: planDigest({
        verdict: (verdicts[0] && verdicts[0].verdict) || 'surfaced',
        reviews: reviewsById.get(batons[0].id) || [],
        premiseCheckVerdict: resolveVerdict(
          premiseAsReview(batons[0], premiseById.get(batons[0].id)) || {},
        ),
        surfacedQuestion:
          (surfacedToPm.find((d) => d.batonId === batons[0].id) || {}).surfacedQuestion || null,
        planPath: planPathById.get(batons[0].id) || null,
        deliverableId: batons[0].deliverableId || null,
        exitCriterionStatement: batons[0].exitCriterion || null,
        sizingObject: batons[0].sizingObject || null,
        batonId: batons[0].id,
      }),
    }
    : {}),
}
