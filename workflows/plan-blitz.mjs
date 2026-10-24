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
 *                             //  Every agent writes its sidecar HERE, and the wave's later
 *                             //  readers open them from disk. Caller scaffolds it before firing;
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
 *                             //  plan that declared no falsifier, so later readers reasoned about
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
 *     readyOp: {              // OPTIONAL. {op, params}: one more engine op the LAST reviewer runs
 *       op, params, schema?,  //  once for a plan the readiness op proved ready, its reply returned
 *     },                      //  verbatim as `readyOpReply` on that ready entry. `params` omits
 *                             //  plan_path; `schema` types the reply. Contract: claude-klabauter
 *                             //  coordinator_core/contract/plan-blitz-ready-op-contract.md.
 *                             //  Absent means plan-blitz behaves unchanged.
 *     batons: [ {
 *       id: string,           // stub_id or handoff_id — the id `blocked_by` edges name it by
 *       path: string,         // repo-relative path to the baton record
 *       title: string,
 *       sized: boolean,       // true when the baton already cites a sizing-object. A sized
 *                             //  baton SKIPS the scout (its size was decided upstream) but
 *                             //  still passes through the blitz-em, which may revise it.
 *       planPath: string|null,// an existing plan, when the baton already has one. Non-null
 *                             //  means this wave REVISES rather than authors.
 *       sizingBaton: string|null, // OPTIONAL. The cited sizing's on-disk `baton:` value. An XS whose
 *                             //  value equals this baton's `path` needs no em echo to be handed
 *                             //  to the driver as an `xsRuns` entry.
 *       executionOpen: boolean// REQUIRED, from `roadmap.plan_gate`'s `execution_gate.open`
 *                             //  for this baton. An XS is handed to the driver
 *                             //  (`xsRuns`) only when its EXECUTION gate is open — blockers
 *                             //  coded, not merely planned. Omit it and every XS fails the
 *                             //  `=== true` test, so none is handed off, none is closed, and
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
 * Returns: { waveIndex, ready, pulled, replan, surfacedToPm, adjudicated, xsRuns, trailDir }
 * (`surfacedToPm` is the PM residue: only entries an adjudicator marked `pm_only`, each carrying
 * its `adjudication`; `adjudicated` holds the PM-bound entries an adjudicator ruled on; `xsRuns`
 * is one `{ batonId, record, sizingObject, deliverableId }` per execution-open, sized XS, handed
 * to the driver to run as an ask run closed by dispatch.land_run — the wave executes no XS,
 * and `dispatched` stays `[]`.) — see WAVE RESULT below.
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
  description: 'One planning wave: sonnet scouts size the batons, an Opus EM finalises, Opus planners write, a sonnet pass resolves each plan\'s citations against the tree, resolved reviewers run over each plan, in sequence or as one chatty wave when the run enables it, each applying and verifying its own findings, and the readiness op\'s verdict, mapped in the script, decides each plan.',
  phases: [
    { title: 'Size', detail: 'One sonnet sizing-scout per unsized baton — substrate read, touchpoint inventory, prior art, and a proposed t-shirt with its evidence. Skipped for a baton that already cites a sizing-object. Then one Opus blitz-em over the whole wave interrogates every proposed size (revising down by default), finalises the route via sizing-assemble, and emits the per-baton dispatch spec the Plan phase reads; it is skipped in single-plan mode and when every baton already carries an accepted sizing.' },
    { title: 'Plan', detail: 'One Opus planner per baton, on every route and at every size — authoring is not a lane the wave economises on. Writes the plan doc through coordinator:plan / scaffold-plan; never hand-authors frontmatter. In single-plan mode the prior-art pre-flight starts beside the planner and is awaited before the premise check.' },
    { title: 'Premise check', detail: 'One sonnet pass per drafted L-or-above plan (below L it does not fire), dispatched once its plan path is trusted and before any reviewer fires. Resolves the load-bearing citations in that plan against the tree — paths, symbols, refs, whether its falsifier can report red, and whether a named thing means what the plan says. It reports per-class ROWS and never a plan-level verdict; the seam after it translates those rows onto REVIEW_SCHEMA so they reach the reviewers that already apply every finding themselves. A premise miss routes BLOCKED; the class-5 rows with no writable fix are NAMED for the reviewers, who own the separating test.' },
    { title: 'Review', detail: 'Reviewers resolved per baton from the EM dispatch spec, never prescribed in the plan file, then fixed by the finalised size ladder: XS/S one sonnet plan-reviewer, M and L staff-eng alone on opus, XL and above adds apm and eng-director; a domain signal replaces staff-eng. No persona runs on sonnet; the overengineering lens reviews shipped code, never a plan. Fires unconditionally — the EM is not consulted about whether a plan deserves review. Same plan, two paths. Sequential: each reviewer applies its own findings in place and runs `review-findings-ledger verify` on its own sidecar before the next reviewer starts. Chatty wave (args.chatty with args.chattyReview, reviewers within the roster slots): an overseer registers, every reviewer runs concurrently claiming regions by mail, then a survey, one continuation per slot with unread mail, and a summary. A PIVOT/REJECTED verdict applies nothing and suspends every finding under it, with co-reviewer findings still logged. The last reviewer runs plan.readiness_verdict (a dedicated host after the wave does on the chatty path); a prep-gate enricher runs concurrently with other plans reviewers, only when that reply names mechanical_repairs, none came back, or its only failure is census-unscreenable, repairs what the engine marks mechanical plus the Mechanical rows of the plan-coverage pre-flight, and re-asks the op once. A judgment verdict with no BLOCKED reviewer buys one opus plan-author resolver and one op re-ask; the plan is ready only if the re-ask is, and a BLOCKED reviewer or a failed resolve pulls with a reason leading "<n> blocking, <m> advisory". The script maps the standing op verdict to ready, pulled or replan, and a PIVOT routes to a replan baton rather than halting the wave. Host availability on the executing box is never a pull reason.' },
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
          sizingBaton: { type: ['string', 'null'] },
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
    // Only the last reviewer of a plan fills these (readinessStep): the op's reply verbatim, the
    // reviews it was computed over, or the one-line failure.
    readinessVerdict: {
      type: 'object',
      properties: {
        plan: { type: 'string' },
        verdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
        pull_class: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
        mechanical_repairs: { type: 'array', items: { type: 'object' } },
        prep_gate: { type: 'object' },
        reason: { type: 'string' },
        // The premise-row keys the op counted as blocking; compared across pulls by the Ask composer.
        blocking: { type: 'array', items: { type: 'string' } },
        // The op's own finding counts; a host that trims the reply to its schema keys drops them and findingCounts falls back to the wave.
        blocking_findings: { type: 'integer' },
        advisory_findings: { type: 'integer' },
      },
      // honouredReadiness drops a reply without prep_gate, and a host that trims the "verbatim"
      // reply to its headline keys loses a ready plan as unusable; the schema makes it unskippable.
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
    // How many times the host ran the op (2 when the retry also failed).
    readinessAttempts: { type: 'integer' },
    // The ready-op reply verbatim, typed by readyOp.schema when given, and its one-line failure.
    readyOpReply: READY_OP_REPLY_SCHEMA,
    readyOpError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// PRE-FLIGHT SCHEMAS — the L+ pre-review dispatch is one premise-checker agent; in single-plan
// mode it also returns the plan-coverage verdict (`PRE_REVIEW_SCHEMA`). Both are report-only
// (never edit, never refuse): the wave reads their verdict and rows the same way it reads a
// reviewer's, through `planCoverageAsReview` below for the coverage one. Kept loose on purpose,
// same rung as PREMISE_SCHEMA — an agent whose structured-output call
// is forced into a narrower shape than its own report format degrades its answer to fit the field.
const PREP_GATE_REVISE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'before', 'after', 'tldr'],
  properties: {
    batonId: { type: 'string' },
    before: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    after: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    repaired: { type: 'array', items: { type: 'string' } },
    coverageRepaired: { type: 'array', items: { type: 'string' } },
    // Filled only on the op-driven path: the post-repair plan.readiness_verdict reply's verdict
    // and pull_class. Absent means the re-run did not answer, and the script reads that as no reply.
    afterVerdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
    afterPullClass: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
    afterReason: { type: 'string' },
    afterBlocking: { type: 'array', items: { type: 'string' } },
    // The post-repair op's own output, verbatim, when it failed twice. Absent when it answered.
    afterError: { type: 'string' },
    gateReport: { type: 'string' },
    // The ready op, run by this loop when its re-run is ready: the reviewer's ready op skipped a
    // repaired plan, so without these a repaired-ready plan reaches the caller with no reply.
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
    // Each spine row id and frontmatter key the resolver edited; [] = nothing that carries a citation.
    touched: { type: 'array', items: { type: 'string' } },
    // Filled from the one re-ask of plan.readiness_verdict. Absent with `afterError` set means the
    // re-ask failed twice; the script stands the plan as `errored`, never as a failed resolve.
    afterVerdict: { type: 'string', enum: ['ready', 'pulled', 'judgment'] },
    afterPullClass: { type: 'string', enum: ['none', 'mechanical', 'substantive'] },
    afterReason: { type: 'string' },
    afterBlocking: { type: 'array', items: { type: 'string' } },
    afterError: { type: 'string' },
    // The re-ask reply's `prep_gate.verdict`. The ready op is gated on PREPPED here exactly as
    // readinessStep gates it (honouredReadiness rejects a ready reply whose gate is not PREPPED).
    afterPrepGate: { type: 'string', enum: ['PREPPED', 'NOT-PREPPED', 'REFUSED', 'ENGINE-ERROR'] },
    // The ready op, run by this leg when its re-ask is the final ready call: the reviewer's ready op
    // skipped a judgment plan, so without these a resolved-ready plan reaches the caller with no reply.
    readyOpReply: READY_OP_REPLY_SCHEMA,
    readyOpError: { type: 'string' },
    tldr: RETURN_TLDR_SCHEMA,
  },
}

// The re-check leg's return: the fresh rows for the citations the resolver's edit touched, the prior
// citations the plan no longer carries, and the one op re-ask over the merged rows.
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

// The merged L+ pre-review dispatch's schema in single-plan mode: the premise result stays the
// top-level shape and the plan-coverage verdict rides as `coverage`. The top-level `tldr` serves both.
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


// CODE TLDR FALLBACK. Every role schema requires `tldr`; a result that skipped it still carries
// its own sidecar (the durable record — § TRAIL_RULE / REVIEW_SIDECAR_RULE). The fallback is a
// pure function over that in-memory result: a WARN `return-tldr` anchored at the sidecar. No agent
// restates it, because a restatement adds nothing a reader of the sidecar lacks. It lives in
// `trackAgent` because every dispatch funnels through it. A recovered fallback never flips the
// wave's `completed` (a lost summary line, not a lost dispatch); only a result with no
// `sidecarPath` yields `tldr: null` and a `missing-tldr` incident.
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


//   - a baton never ends with zero reviewers — a substitution DEGRADES the


const REVIEWER_ROSTER = new Set([
  'coordinator:plan-reviewer',
  'coordinator:staff-eng',
  'coordinator:apm',
  'coordinator:eng-director',
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
])

const DEFAULT_REVIEWER = 'coordinator:staff-eng'

const SIGNAL_ROSTER = new Set(Object.values(SIGNAL_REVIEWERS))

// The plan-stage reviewer set is a pure function of the finalised t-shirt and the plan's signals.
// Dispatch order is review order; each row's first slot is the one a domain signal replaces.
// An unknown size takes the XL row: under-reviewing an unrecognised size is the worse error.
const PLAN_REVIEW_LADDER = {
  XS: ['coordinator:plan-reviewer'],
  S: ['coordinator:plan-reviewer'],
  M: ['coordinator:staff-eng'],
  L: ['coordinator:staff-eng'],
  XL: ['coordinator:staff-eng', 'coordinator:apm', 'coordinator:eng-director'],
  XXL: ['coordinator:staff-eng', 'coordinator:apm', 'coordinator:eng-director'],
}

function ladderRow(tshirt) {
  return Object.prototype.hasOwnProperty.call(PLAN_REVIEW_LADDER, tshirt)
    ? PLAN_REVIEW_LADDER[tshirt]
    : PLAN_REVIEW_LADDER.XL
}

// The premise check and the plan-coverage pre-flight fire only for L and XL+ plans, where the
// citation count is largest. An unknown size counts as XL, as in `ladderRow`.
const PRE_REVIEW_CHECKER_SIZES = new Set(['L', 'XL', 'XXL'])

function preReviewCheckersOwed(tshirt) {
  return PRE_REVIEW_CHECKER_SIZES.has(tshirt) || !Object.prototype.hasOwnProperty.call(PLAN_REVIEW_LADDER, tshirt)
}

// XS/S ignore signals. At M and above a domain signal replaces the staff-eng slot; a
// cross-repo-seam signal or an EM-named eng-director replaces it when the row has no
// eng-director of its own. The count never exceeds the row's length.
function planReviewers(tshirt, resolved, signals) {
  const row = [...ladderRow(tshirt)]
  const sigs = Array.isArray(signals) ? signals : []
  if (row[0] !== 'coordinator:plan-reviewer') {
    const domain = sigs
      .map((sig) => SIGNAL_REVIEWERS[sig])
      .find((r) => r && r !== 'coordinator:eng-director' && resolved.includes(r))
    const boundary = !row.includes('coordinator:eng-director') && resolved.includes('coordinator:eng-director')
    if (domain) row[0] = domain
    else if (boundary) row[0] = 'coordinator:eng-director'
  }
  const reviewers = [...new Set(row)]
  return { reviewers, dropped: resolved.filter((r) => !reviewers.includes(r)) }
}

// Only the plan-reviewer runs on sonnet; a persona is Opus-only by contract.
function reviewerModel(reviewer) {
  return reviewer === 'coordinator:plan-reviewer' ? 'sonnet' : 'opus'
}

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
// the two `.md` sources on edit; do not paraphrase. Trap: PREMISE_BRIEF_VERSION hashes this
// constant, so re-copying a snippet edit changes the version and every plan's next refire becomes
// a first pass (plan.premise_scope / plan.premise_record).
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

// The premiseChecker brief's class list, held once so the hash and the brief read one copy.
// `${ARMING_CHECK_CLI}` stays an unsubstituted placeholder here: it varies per host, and hashing
// the rendered text would make every box a first pass.
const PREMISE_CLASS_LIST = `Five question classes. Answer each for every load-bearing citation:

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
     \`\${ARMING_CHECK_CLI} <instrument> --json\` and carry its verdict
     into \`falsifierVerdict\` VERBATIM. Do not restate its predicate in your own words and do not
     write your own version: it is one surface with several readers. Its \`UNCHECKABLE\` means the
     file could not be read, which is not a pass. If the plan names no falsifier, say so.
     Class 4 compares the falsifier's \`baseline_output\` against the tree at its \`baseline_ref\`,
     never at HEAD: read a read-shaped \`how\` with \`git show <baseline_ref>:<path>\`; a \`how\` that
     needs a checkout, build or test run at that ref is \`UNCHECKABLE\`. Every class-4 row carries
     \`baseline_ref\`, the value it read against.
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
UNCHECKABLE (nothing in this tree settles it).`

// 32-bit FNV-1a over UTF-16 code units, 8 lower-case hex digits. Pure JS: no process spawn.
function fnv1a32Hex(text) {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
}

// Computed, never hand-bumped: carried premise verdicts are trusted only under the brief that
// produced them. Trap: re-copying an edit of either hand-synced contract above changes this
// value, and every plan's next refire becomes a first pass.
const PREMISE_BRIEF_VERSION = fnv1a32Hex(
  [PREMISE_CLASS_LIST, PREMISE_CHECK_CONTRACT, INSTRUMENT_CAN_REPORT_RED_CONTRACT].join('\n'),
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

  'plan-coverage-checker': `Inside this dispatch, after the premise rows are recorded, you also run the
plan-coverage lenses for single-plan mode. Read \`agents/plan-coverage-checker.md\` in full and follow
its protocol exactly — this line names the role, it does not restate the eight lenses. Every lens is report-only: no inline plan edits, no
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
// transposed character, in the agent's own structured result. A later reader opened a
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

The pointer is how the wave finds you. A findings sidecar with no pointer is a review the
wave cannot see, and a pointer with no sidecar is worse — it reads as a review that ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the wave's reader will never see.
${SIDECAR_HEREDOC_RULE(pointerPath)}`

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

const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

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

\`status: draft\` is not a placeholder to improve on — it is the correct value. Only the landing,
on a ready verdict, advances a plan past draft, and a planner that writes \`approved\` has forged the
gate this whole pipeline exists to hold.

Body: the problem in one paragraph; file scope; acceptance criteria that can each be checked as
true or false against the tree; the test surface; and an explicit Anti-scope naming what this
plan does NOT do.`

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
${MID_RUN_DIRECTION_RULE}
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
      // Low, not higher: the planner is authoring against a size and a route the
      // blitz-em already interrogated, over substrate a scout already inventoried.
      // The judgment it owes is the plan's shape, not a re-derivation of the wave's
      // decisions — and an unpinned planner inherits whatever the invoking session
      // was set to, which makes the wave's authoring depth an accident of who fired it.
      effort: 'low',
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

function premiseChecker(baton, planResult, trailDir, withCoverage) {
  // Function-form replacement: a `$` in the CLI path must not be read as a replacement pattern.
  const renderedClassList = PREMISE_CLASS_LIST.split('${ARMING_CHECK_CLI}').join(ARMING_CHECK_CLI)
  return trackAgent('planner', agent(
    `phase: premise-check

Resolve the load-bearing citations in the plan at ${planResult.planPath} (baton ${baton.id}) against
this tree. A citation is load-bearing when the work changes if it does not resolve.

Report the CLASS you checked. You are not reviewing the plan, and you never report that it is
correct, sound or ready — a plan whose every citation resolves can still be wrong, and a clean
table read as an approval is worse than no table.

You never refuse and never edit. A defect you find is something you report.

REFIRE CARRY. This brief's version is \`${PREMISE_BRIEF_VERSION}\`. Before the full pass below,
ask the engine what moved since the last recorded pass.

${CLI_RESOLUTION_RULE}

  (a) Run \`coordinator-invoke plan.premise_scope\` with one JSON argument
      \`{"plan": "${planResult.planPath}", "brief_version": "${PREMISE_BRIEF_VERSION}"}\`.
  (b) Reply \`first_pass: true\` → run the full pass below, unchanged.
  (c) Otherwise check ONLY the citations on the reply's \`changed_lines\` lines plus every
      \`recheck\` row's citation. Return a fresh row, or a \`retired\` entry carrying the citation
      verbatim, for every \`recheck\` citation; never drop one. Do not re-check \`carried\` rows.
  (d) Every fresh row carries \`line\`: the 1-based plan line carrying its citation.
  (e) On EVERY pass, then run \`coordinator-invoke plan.premise_record\` with one JSON argument
      \`{"plan", "brief_version", "rows", "retired", "citations_skipped"}\` — the wire key is
      snake_case \`citations_skipped\`; the engine refuses any unknown key. Return the reply's
      \`rows\` VERBATIM as \`rows\` (the op already merged the carried rows; do not merge them
      yourself), plus \`carry: {"firstPass": <scope first_pass>, "carried": <reply carried>,
      "fresh": <reply fresh>}\`.
  (f) Fail open. If either op fails (non-zero exit, no JSON reply, or an \`error\` envelope), make
      sure a full pass has run and return its rows with NO \`carry\`. Scope op failed: run the full
      pass and skip the record op. Record op failed after a first pass: the full-pass rows are in
      hand. Record op failed after a scoped pass: run the full pass. Never retry an op.

${renderedClassList}

A CONTRADICTED row whose citation matches an entry on the plan's \`corrects:\` list says so in
its evidence (\`on corrects: -> <fixed_by>\`) and still reports CONTRADICTED: the readiness op
decides cover.

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

${MID_RUN_DIRECTION_RULE}

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
cleared this phase, two reviewers, integration and the readiness verdict, landed approved, and was
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
    )}${withCoverage ? `

COVERAGE. This dispatch also owes the plan-coverage verdict for the same plan, so you run both
checks in this one context. Order: record the premise rows first, then run the coverage lenses.
"Do not read the plan's acceptance criteria" above governs the premise rows only.

${ROLE_CONTRACTS['plan-coverage-checker']}

Run every lens of \`agents/plan-coverage-checker.md\` over ${planResult.planPath} exactly as that file
states it. Lens 3 (substrate drift) may be answered from the class 1-3 rows you already opened,
applying Lens 3's own match rule (within 50 lines, the excerpt, or a \`§ Heading\`); report the result
in the coverage sidecar's Substrate-drift count.

Return the verdict as the \`coverage\` object (\`verdict\`, \`sidecarPath\`, \`mechanicalFindings\`,
\`judgmentFindings\`). The coverage sidecar is a second sidecar: its path is \`coverage.sidecarPath\`,
and the top-level \`sidecarPath\` stays the premise one provisioned above.
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'plan-coverage-check')).replace('return it verbatim as \`sidecarPath\`', 'return it verbatim as \`coverage.sidecarPath\`')}` : ''}`,
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
      schema: withCoverage ? PRE_REVIEW_SCHEMA : PREMISE_SCHEMA,
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

// The key the op files a premise row under: contract § 3 spells it `premise-check: <VERDICT>
// <citation[:200]>`, sliced by code point (Python), so the slice here is by code point too.
function premiseKey(row) {
  return `premise-check: ${row.verdict} ${Array.from(String(row.citation || '')).slice(0, 200).join('')}`
}

// The UNRESOLVED/CONTRADICTED rows that block. With an honoured reply carrying `blocking`, only the
// rows the op counted; the op alone decides cover and staleness, so no other row is exempted here.
function premiseBlockingRows(rows, reply) {
  const flagged = rows.filter((r) => PREMISE_FINDING_VERDICTS.includes(r.verdict))
  if (!reply || !Array.isArray(reply.blocking)) return flagged
  const counted = new Set(reply.blocking)
  return flagged.filter((r) => counted.has(premiseKey(r)))
}

// The premise rows that stand after a revision: a fresh row replaces the prior row with the same
// citation, a retired citation is dropped, other fresh rows are appended, untouched rows are kept.
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

function premiseAsReview(baton, premise, reply) {
  if (!premise) return null
  const rows = premise.rows || []
  const findings = premiseBlockingRows(rows, reply)
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
    // `pivotCandidates` — that field is a non-routing class-5 PIVOT candidate signal, and reusing it for
    // "nothing was checked" would misread as one.
    citationsChecked: rows.length,
    // The op-counted citations that made this BLOCKED; the one source the trail and digest name.
    blockingCitations: findings.map((r) => `${r.verdict} ${r.citation}`),
    // Non-routing: no consumer may route on it, and UNCHECKABLE rows never block.
    pivotCandidates: unwritable.length
      ? `class-5 rows with no fix writable from the finding alone — PIVOT candidates for a `
        + `reviewer to run the separating test against, not a route this pass took: `
        + unwritable.map((r) => `${r.verdict} ${r.citation}`).join('; ')
      : undefined,
  }
}

const PLAN_COVERAGE_REVIEWER = 'plan-coverage-check'

// The seam for the second single-plan pre-flight — same shape as `premiseAsReview` above, so the
// wave's trail and its `reviews` reconciliation read it through the one channel every
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

// ---------------------------------------------------------------------------
// Phase 4 — Review
// ---------------------------------------------------------------------------

// The readiness op rides on the LAST reviewer of a plan: the one agent that has already run, after
// every other reviewer's edits and its own verified ledger, so the op reads the plan as reviewed.
// `host` is null for every other reviewer. The op's reply is the op's: this brief carries it back
// verbatim and the script never recomputes a verdict from it.
// The op's params without the host's own entry. One builder for the rendered command and the
// `readinessParams` an errored entry carries, so the two cannot drift. Keys are only those the op
// admits (plan, coverage, premise, reviews).
function readinessParams(planPath, host) {
  return {
    plan: planPath,
    ...(host.coverage ? { coverage: host.coverage } : {}),
    ...(host.premise ? { premise: host.premise } : {}),
    reviews: host.reviews,
  }
}

function readinessStep(host, planPath, reviewer, readyOp) {
  if (!host) return ''
  const readyOpStep = readyOp ? `
READY OP (only after the readiness op above, and only on ITS reply): if the reply's \`verdict\` is
"ready", its \`mechanical_repairs\` is empty and its \`prep_gate.verdict\` is "PREPPED", run, exactly
once, with this JSON as the single argument (quote it for your shell):

    coordinator-invoke ${readyOp.op} '${JSON.stringify({ ...readyOp.params, plan_path: planPath }).split("'").join("'\\''")}'

and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
one-line failure in \`readyOpError\`. In any other case run nothing and return neither field.
` : ''
  const params = JSON.stringify(readinessParams(planPath, host))
  return `
READINESS VERDICT (the last thing you do, after your ledger verifies): you are the last reviewer on
this plan, so the readiness op rides on your run. If your verdict is PIVOT (or a REJECTED you
resolve to PIVOT), skip this step entirely. Otherwise run, with this JSON as the single argument
(quote it for your shell) and your own entry appended as the LAST element of \`reviews\`, spelled
{"reviewer":"${reviewer}","verdict":"<your verdict exactly as you return it>","ledger":"<your sidecarPath>"}:

    coordinator-invoke plan.readiness_verdict '${params}'

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

// The op's reply is honoured only when the host passed it exactly the reviews this script resolved
// itself (same reviewers, verdicts and order), did not pivot, reported no error, and the reply is
// internally coherent. Anything else is no reply, and no reply reproduces the unconditional spawns.
// Provenance is NOT attested: the reply is the reviewer agent's self-report of the op's output, so a
// fabricated coherent `ready` is honoured; these checks bound shape and inputs only.
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

// `ledger` is the reviewer's findings-ledger sidecar: the op reads a WARN/BLOCKED as clear only when
// that ledger is stamped and every row verified, so an entry without one stays `judgment`.
const opReviewList = (entries) => entries.filter(Boolean).map((r) => ({
  reviewer: r.reviewer,
  verdict: r.verdict,
  ...(typeof r.sidecarPath === 'string' && r.sidecarPath ? { ledger: r.sidecarPath } : {}),
}))
// The premise checker's rows ride as the op's own `premise.rows`, never as a `premise-check`
// reviews entry (the op refuses that pairing). Null when no premise check ran.
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

function reviewerAgent(baton, decision, planResult, reviewer, trailDir, premise, priorReviewers, hostReadiness, priorArt, chattyBrief) {
  const priorArtBlock = priorArt
    ? `\nPrior-art pre-flight over this baton's sizing intent: ${priorArt.verdict}, ${priorArt.conflicts || 0} conflict(s), sidecar ${priorArt.sidecarPath}. The planner may not have seen it: open it, and treat a CONFLICT bucket as a finding against the plan.\n`
    : ''
  const sequencing = chattyBrief
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

  return trackAgent('reviewer', agent(
    `${ROLE_CONTRACTS.reviewer}

Review the plan at ${planResult.planPath} for baton ${baton.id} ("${baton.title}").

Finalised size: ${decision.tshirt}, route: ${decision.route}.
Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}
${sequencing}${priorArtBlock}
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
the op verdict's reader sees that, and a plan wrongly kept is recoverable in a way a plan wrongly discarded is not.

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
${readinessStep(hostReadiness, planResult.planPath, reviewer, READY_OP)}${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, `review-${reviewer}-pointer`), reviewer)}${chattyBrief || ''}`,
    { model: reviewerModel(reviewer), ...withRole(reviewer),
      label: `review:${baton.id}:${reviewer}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    },
  ))
}

// Chatty review wave: the template travels in `chattyReview`; `{BATON}` scopes one baton's roster,
// mail and nonces, `{PEERS}` lists a member's peers.
function fillBaton(value, batonId, slot) {
  if (typeof value === 'string') return value.split(slot).join(batonId)
  if (Array.isArray(value)) return value.map((v) => fillBaton(v, batonId, slot))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fillBaton(v, batonId, slot)]))
  }
  return value
}

// `{BATON}` is filled with `<baton id>-<pass tag>`, never the bare id: a baton reviewed twice
// (first pass, plan-revise re-pass) must not put one nonce in two workflow transcripts, or the
// overseer and summary cannot self-identify. The tag counts this invocation's passes per baton;
// no clock or random source is available to a workflow script.
function chattyPassId(batonId) {
  chattyPassId.counts = chattyPassId.counts || {}
  chattyPassId.counts[batonId] = (chattyPassId.counts[batonId] || 0) + 1
  return `${batonId}-r${chattyPassId.counts[batonId]}`
}

function fillPeers(brief, slotTypes, peersSlot = '{PEERS}') {
  return brief.split(peersSlot).join(slotTypes.map(([slot, type]) => `${slot} = ${type}`).join('\n'))
}

// `wave` is true only when chatty review is armed and every reviewer has a roster review slot;
// otherwise `note` (set only on an armed run that fell back) goes to the trail.
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

// One baton's reviewers as a wave: overseer, concurrent reviewers, survey, continuations, the
// readiness host, summary. Returns the resolved reviews in reviewer order; the caller owns the rest.
// Returns null when the overseer returned nothing: no reviewer ran, and the caller runs the
// sequential loop.
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
      { model: reviewerModel(reviewer), ...withRole(reviewer), label: `review-continuation:${baton.id}:${slot}`, ...phase, schema: REVIEW_SCHEMA },
    ))
    if (!result) return prior
    checkSidecarPath(baton.id, `review-${reviewer}`, result.sidecarPath)
    return resolveVerdict({ ...result, reviewer })
  }))
  const reviews = resolved.filter(Boolean)

  // The readiness op needs a settled plan: a PIVOT sends it to replan, and a last reviewer that
  // returned nothing leaves no entry to host the op for, as in the sequential loop.
  let hostParams = null
  const last = reviews[reviews.length - 1]
  if (last && last.reviewer === reviewers[reviewers.length - 1] && !reviews.some((r) => r.pivot)) {
    const hostInput = { reviews: opReviewList(reviews.slice(0, -1)), premise: premiseForOp(premise), coverage: coverageForOp(coverage) }
    hostParams = readinessParams(plan.planPath, hostInput)
    const hosted = await trackAgent('readiness-host', agent(
      `phase: readiness

The reviewers of baton ${baton.id} ("${baton.title}") have all returned and their ledgers are verified.
You review nothing and edit nothing: you only run the readiness step below for them. Where it says "you"
or "your", read the last reviewer, ${last.reviewer}: its verdict is ${last.raw}, its ledger ${last.sidecarPath},
and its entry is {"reviewer":"${last.reviewer}","verdict":"${last.raw}","ledger":"${last.sidecarPath}"}. Return only the
readiness fields.
${readinessStep(hostInput, plan.planPath, last.reviewer, READY_OP)}${REPO_ROOT_RULE}`,
      { model: 'sonnet', label: `readiness-host:${baton.id}`, ...phase, schema: READINESS_HOST_SCHEMA },
    ))
    if (hosted) {
      for (const key of Object.keys(READINESS_HOST_SCHEMA.properties)) {
        if (key !== 'tldr' && hosted[key] !== undefined) last[key] = hosted[key]
      }
    }
  }

  await trackAgent('chatty-summary', agent(
    `${cfg.summaryPrompt}${REPO_ROOT_RULE}`,
    { model: 'sonnet', label: `chatty-summary:${baton.id}`, ...phase },
  ))
  return { reviews, hostParams }
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
  const errored = input.verdict === 'errored'
  // The vendored digest enum has no `errored`; the error rides on decision_required.
  const outcome = !errored && ['ready', 'pulled', 'replan', 'surfaced'].includes(input.verdict)
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
      (errored ? `plan.readiness_verdict errored: ${input.opError || '(no error text)'}` : null)
      || input.surfacedQuestion || (decisions.length ? decisions[0].item : null) || null,
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
        // The execute stage, not a vehicle: in session the EM runs /execute-plan on plan_path;
        // a chained fire's driver reads only params.plan_path and runs it headless.
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

// SINGLE-PLAN MODE or a wave whose every baton already carries an accepted sizing (ALL_ACCEPTED)
// gates off THIS phase (§ Pinned interfaces / body item 2): the sizing scout is already skipped
// above by the `unsized` filter. Each baton already states its decision — a blitz-em
// interrogating a sizing already resolved (single mode: `emit-wave-fire --from-sizing`; roadmap
// route: blitz_stage's sized stubs) would re-litigate an accepted decision, not gate a fresh one.
// A wave holding any baton without an accepted sizing still fires the blitz-em.
const ALL_ACCEPTED = batons.length > 0
  && batons.every((b) => b && b.sized === true && b.sizingObject && b.tshirt && b.route)
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
        reviewers: ladderRow(b.tshirt),
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

Per baton emit: the final t-shirt, the route (from sizing-assemble, never hand-derived), a
rationale naming what you changed and why, and which reviewers this plan needs.

You do not choose the planner's model. Every plan in this wave is authored at opus, on every
route and at every size; sonnet's place here is the sizing scouts above you. Do not propose a cheaper planner for a small baton — the wave's cost is set by how many
batons you let into it, not by how thinly you staff the authoring of one.

  - sizingObject: for every baton on a PLANNABLE route ('plan' or 'spec-dispatch') and on the
    'dispatch' route (an XS needs one: the driver's ask run is composed from it), scaffold the
    sizing record your decision just made and return its path. Two commands per baton, through the
    bin ladder: \`sizing-assemble --tshirt <T>\` for the route/detents, then \`coordinator-doc-new
    --type sizing-object\`, populated from what you already hold — intent (the baton's ask, not your
    restatement of the substrate), estimate, route, detents, fork, xl_exit, premise, and
    \`status: routed\`. Do NOT hand-write the file; the generator owns the id and the frontmatter.
    For any other route return null.

    BATON KEY. The sizing you return for a baton on the 'dispatch' route MUST carry a top-level
    \`baton:\` key whose value is that baton's record path exactly as listed in "Batons in this
    wave" above (the bracketed path). Set it in the scaffold, or with Edit on an already-sized
    baton's cited sizing-object when it lacks the key. When the baton already has a sizing match,
    run \`sizing-link-baton --baton <record> --write\` instead: it stamps the sizing's \`baton:\` and
    the baton's sizing citation (a dry run without \`--write\`). \`emit-dispatch-workflow --sizing <sizing>
    --baton <record>\` refuses a pair where neither the baton's \`sizing_object\` nor the sizing's
    \`baton:\` names the other, and the baton's own \`sizing_object\` may name an older sizing. Echo
    the path you wrote in the decision's \`sizingBaton\`.

    **A NULL ON A PLANNABLE OR DISPATCH BATON IS A FAILURE REPORT, AND IT NEEDS ITS REASON IN
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

    The finalised size fixes the reviewer set (XS/S one sonnet plan-reviewer, M and L staff-eng,
    XL and above adds apm and eng-director), so name reviewers only to steer within it. These two
    strings are the ONLY legal values. It is a closed set, not a set of examples:
      'coordinator:staff-eng'                 general engineering rigour
      'coordinator:eng-director'              the baton crosses a repo or team boundary
    A domain reviewer (data-science, front-end, ux) is never yours to name: the plan's own
    \`review_signals\` add it once the plan is written.

    Emit these EXACT strings. This repo's own docs may name reviewers by persona first name
    ("add the Game Dev Reviewer or the Data Science Reviewer", "have the Staff Engineer look at it") — that is human shorthand and it is NOT an
    agent type. Never pass a persona name through, and never invent 'coordinator:<firstname>':
    no such type exists, and a name off this list is substituted for staff-eng with the downgrade
    printed in the trail, so the plan gets reviewed by someone other than whom you chose.
    If a baton genuinely needs expertise outside these two, say so in \`rationale\` and pick the
    closest of the two — the gap is a thing for the EM to read, not a string for you to coin.

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
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, waveSlot, 'em-size-review'))}`,
  { model: 'opus', ...withRole('coordinator:blitz-em'),
    label: `size-review:${waveSlot}`,
    phase: 'Size',
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

// `dispatch` is the XS lane: real work, just not plan-shaped work. It does not leave the wave
// with everything else that was not plannable — if small work falls out of the pipeline, an EM
// who wants it done has structural pressure to size it M so it does not, and sizing that bends
// toward its downstream route is corrupted sizing. The wave does not execute it either: an
// execution-open, sized XS leaves as an `xsRuns` entry the driver runs and closes through
// land_run.
const DISPATCHABLE_ROUTES = new Set(['dispatch'])

// Why each excluded route leaves the wave, so a reader does not have to infer it
// from the route name. `dispatch` is work, just not plan-shaped work — it is the
// one exclusion that is a HANDOFF (to the driver, as `xsRuns`) rather than a stop.
const ROUTE_EXITS = {
  dispatch: 'XS/dispatch — routes to a driver-run ask run and has no plan',
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
// is planned twice or handed to the driver twice. Measured on example-market-data-repo wave 0 fire 2: two XS batons
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
// An execution-open XS is handed to the driver only when it carries a sizing object: the ask
// run that reaches `land_run` is composed from one. The decision's own citation wins over
// the baton arg's.
const xsSizingFor = (d) => repoRelativeCitation(d.sizingObject || batonFor(d).sizingObject) || null
// emit-dispatch-workflow refuses a pair whose sizing `baton:` and baton `sizing_object:` name
// neither the other, so an XS leaves as an xsRun only when this baton's record path is attested:
// by the em's `sizingBaton` echo, by the args baton's `sizingBaton` (the cited sizing's on-disk
// `baton:` value, carried by the caller), or by the in-wave link pass below.
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
// The link pass below appends to `xsRuns` and `xsRunIds`; routedElsewhere reads both after it.
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

// An execution-open XS whose cited sizing lacks the `baton:` echo is linked in this wave rather
// than routed away to wait for a later wave to re-size it. A failed link falls through to
// `routedElsewhere`, which still names the missing echo.
function xsLinker(d) {
  const baton = batonFor(d)
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
        // A rejected link agent leaves the baton out of xsRuns; routedElsewhere then names the missing echo.
        () => {},
      ),
    ),
)
const UNSIZED_XS_REASON = 'XS/dispatch, but no sizing object — the ask run that reaches land_run needs one'
// Routed somewhere other than a plan. NOT dropped: a baton that vanishes between
// waves is one nobody notices, so each leaves the wave carrying the reason.
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
    // An absent `executionOpen` and a false one are different values and must not
    // report as the same sentence. `false` is the two-gate split doing its job.
    // `undefined` is the CALLER not carrying the field at all — every XS then fails
    // `=== true`, none dispatches, and each recycles into the next wave while this
    // line tells the reader their blockers are uncoded. A wrong cause is worse than
    // no cause: it sends the reader to the roadmap when the defect is in the fire.
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

// SINGLE-PLAN MODE's first pre-flight: started beside `planner()` and never awaited before it, so
// the planner does not wait on it. Awaited in the second pipeline stage, before the premise check.
// The no-op catch stops a rejection going unobserved while the planner runs; the real handling is
// the await.
const priorArtPromise = SINGLE_MODE && plannable.length
  ? priorArtPreflight(batons[0], waveIndex, trailDir)
  : null
if (priorArtPromise) priorArtPromise.catch(() => {})

// Phases 3-5 — plan, review, integrate, per baton, PIPELINED. No barrier between the stages: a
// baton whose plan lands first starts its review while its siblings are still planning. The
// wave's wall-clock is then the slowest single baton's chain, not the sum of three barriers.
const chains = await pipeline(
  plannable,
  (decision) => {
    const baton = batons.find((b) => b.id === decision.batonId)
    // An em decision can name a baton the wave never carried; `planner()` dereferences the baton,
    // so that case is a blocked entry here, not a pipeline failure.
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
    const singleContext = SINGLE_MODE
      ? {
          exitCriterionStatement: baton.exitCriterion,
          sizingPath: SINGLE_SIZING_PATH,
          priorArtSidecarPath: priorArtPromise ? sidecarFor(trailDir, baton.id, 'prior-art-check') : null,
        }
      : null
    return planner(baton, decision, waveIndex, trailDir, singleContext).then((plan) => ({ decision, baton, plan }))
  },
  async ({ decision, baton, plan }) => {
    if (!plan || plan.status === 'blocked') {
      // A planner that could not write a plan is carried to the verdict mapping as a blocked
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
    // In single-plan mode the same dispatch also runs the plan-coverage lenses and returns their
    // verdict as `coverage` (`premiseChecker`'s `withCoverage`); prior-art still starts beside the
    // planner and is awaited here.
    //
    // The dispatch is gated to L and above (`preReviewCheckersOwed`): below L it does not fire and
    // `premise` and `coverage` are null, which every consumer tolerates; `checkersSkipped` lets the
    // trail's premise-check line render the skip distinctly from "did not run" (the coverage
    // result has no trail line of its own).
    const priorArt = priorArtPromise ? await priorArtPromise : null
    const checkersOwed = preReviewCheckersOwed(decision.tshirt)
    const checkersSkipped = !checkersOwed
    const preReview = checkersOwed ? await premiseChecker(baton, plan, trailDir, SINGLE_MODE) : null
    const { coverage = null, ...premiseOnly } = preReview ?? {}
    const premise = preReview ? premiseOnly : null
    if (SINGLE_MODE && checkersOwed && !coverage) {
      agentIncidents.push({
        role: 'premise',
        kind: 'missing-coverage',
        detail: preReview
          ? 'the merged pre-review dispatch returned no coverage object'
          : 'the merged pre-review dispatch returned nothing, so no coverage verdict exists',
      })
    }
    // The seam. Rows in, one REVIEW_SCHEMA entry out, so the report reaches every reviewer
    // through the channel they already read. The checker took no route; this did.
    if (premise) checkSidecarPath(baton.id, PREMISE_REVIEWER, premise.sidecarPath)
    let premiseCheckResult = premiseAsReview(baton, premise)
    let premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    // No checkSidecarPath for coverage: it is report-only and briefed onto the trail (TRAIL_RULE),
    // so it has no findings ledger to verify and a trail path is correct, not unreachable.
    const coverageResult = planCoverageAsReview(baton, coverage)
    const coverageVerdict = coverageResult ? resolveVerdict(coverageResult) : null

    const { reviewers: resolvedReviewers, substitutions } = resolveReviewers(decision.reviewers, plan.reviewSignals)
    const laddered = planReviewers(decision.tshirt, resolvedReviewers, plan.reviewSignals)
    const ladderReviewers = laddered.reviewers
    const chattyPick = chattyWavePick(ladderReviewers)
    // The sequential loop below iterates `reviewers`: empty on the wave path, which runs after it.
    let reviewers = chattyPick.wave ? [] : ladderReviewers
    let reviewNote = chattyPick.note
    for (const dropped of laddered.dropped) {
      substitutions.push(`${dropped} -> (not dispatched: a ${decision.tshirt} plan's reviewer set is fixed by the size ladder)`)
    }
    // Only the LAST reviewer hosts the readiness op; its inputs are the reviews resolved so far.
    // `hostParams` keeps the op params the host was handed, for an errored entry to carry.
    let hostParams = null
    const hostFor = (reviewer) => {
      if (reviewer !== reviewers[reviewers.length - 1]) return null
      const input = { reviews: opReviewList(reviews), premise: premiseForOp(premise), coverage: coverageForOp(coverage) }
      hostParams = readinessParams(plan.planPath, input)
      return input
    }
    // SEQUENTIAL, never parallel — § Design decisions 2. Two reviewers editing one artifact would
    // race, so this baton's reviewers apply and verify one at a time, each reading the ones before
    // it. `pipeline()` with one stage IS a sequential loop; used here (not `parallel()`) because
    // the review AFTER a PIVOT/REJECTED-resolved-to-PIVOT must apply nothing, which the loop
    // below enforces by not dispatching it.
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
      if (pivoted) {
        // Nothing dispatches after a PIVOT: the plan is going to a replan, and a later reviewer
        // applying findings to a plan about to be discarded produces a document that looks
        // maintained and is not. The pivoting reviewer's own findings, and every prior reviewer's,
        // are already on disk and verified.
        break
      }
      const result = await reviewerAgent(baton, decision, plan, reviewer, trailDir, premise, reviews, hostFor(reviewer), priorArt)
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
    if (wave) {
      reviews.push(...wave.reviews)
      hostParams = wave.hostParams
    }
    // The op's reply, honoured only from the last reviewer and only when it was computed over the
    // reviews this script resolved itself. `opReviews` is the list the op saw (and is carried on
    // every verdict entry); the coverage pre-flight rides separately as the op's `coverage`.
    const opReviews = opReviewList(reviews)
    const host = reviews[reviews.length - 1]
    const readinessReply = host && host.reviewer === ladderReviewers[ladderReviewers.length - 1]
      ? honouredReadiness(host, opReviewList(reviews.slice(0, -1)))
      : null
    // The reviewers above saw every premise row; the count that rides the review set is the op's.
    if (readinessReply) {
      premiseCheckResult = premiseAsReview(baton, premise, readinessReply)
      premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    }
    // An op error counts only from the last, non-pivoted reviewer that was handed the op. The params
    // carry the host's own entry as its brief told it to append it, so a re-run needs nothing else;
    // they are kept whether or not the host's op failed, because a failed post-repair run also
    // surfaces as errored and must preserve the same review set.
    const hostIsLast = host && host.reviewer === ladderReviewers[ladderReviewers.length - 1] && !host.pivot
    const readinessError = hostIsLast && typeof host.readinessError === 'string' && host.readinessError.trim()
      ? host.readinessError
      : null
    const readinessParamsOut = hostIsLast && hostParams
      ? { ...hostParams, reviews: [...hostParams.reviews, { reviewer: host.reviewer, verdict: host.raw, ledger: host.sidecarPath }] }
      : null
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
      ...(reviewNote ? { reviewNote } : {}),
    }
  },
)

// Phase 5b — Dispatch hands each XS to the driver (`xsRuns`, built above) and executes none:
// a Workflow agent may never commit, so the driver runs the ask run that ends in
// `dispatch.land_run`.

// Each reviewer applies and verifies its own findings now, so there is no separate integration
// pass to render — a reviewer's own line already carries its verdict and sidecar, and the trail
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

// Phase 5c — prep-gate revise-in-place. This script cannot run the mise-prep bar (no fs/CLI
// primitive here), so one sonnet agent per authored plan measures it, applies ONLY the
// findings the engine marks `mechanical` by following their `repair`, and re-gates ONCE. One loop,
// never two: a plan still NOT-PREPPED after it is pulled with the gate report attached.
// The plan-coverage pre-flight's Mechanical rows ride the same loop: they are applied here, before
// the re-gate, so a plan is not pulled for a frontmatter fix.
function coverageRepairStep(coverage) {
  if (!coverage || !coverage.sidecarPath || !(coverage.mechanicalFindings > 0)) return ''
  return `
COVERAGE REPAIRS (before step 1): the plan-coverage pre-flight reported ${coverage.mechanicalFindings}
Mechanical finding(s) at ${coverage.sidecarPath}. Open that sidecar and apply each Mechanical finding
to the plan in place, as written: the classes are Substrate-drift, Malformed-rows, Missing-writes,
Unregistered-hooks, Scope-writes-gap and Register-citations. Leave every Judgment finding untouched
and touch nothing else in the plan. List each one you applied in \`coverageRepaired\`. This is part
of the same single revise pass, not a second loop.
`
}

// The op-driven brief: the readiness op already measured the plan and named the repairs, so this
// applies exactly those (the coverage Mechanical rows are folded into them) and re-asks the op ONCE.
function opRepairSteps(plan, reply, coverage) {
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
2. Run \`coordinator-invoke plan.readiness_verdict '{"plan":"${plan.planPath}"}'\`, the plan alone.
   Record its \`prep_gate.verdict\` as \`after\`, its \`verdict\` as \`afterVerdict\`, its
   \`pull_class\` as \`afterPullClass\` and its \`reason\` as \`afterReason\`, and its \`blocking\` array
   verbatim as \`afterBlocking\` when the reply carries one. If it fails (non-zero
   exit, no JSON reply, or an \`error\` envelope), run the identical command exactly once more. If
   that fails too, leave \`afterVerdict\` empty and put that run's own output VERBATIM (stderr, else
   stdout, prefixed \`exit <n>: \`, never summarised) in \`afterError\`. Never repair a second time,
   whatever it says.
3. If \`after\` is not PREPPED, put \`prep_gate.message\` and the remaining findings in \`gateReport\`.
${readyOpRepairStep(plan.planPath)}`
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

// The repair loop's ready-op step, built here rather than nested in its caller's template.
function readyOpRepairStep(planPath) {
  if (!READY_OP) return ''
  return `4. If \`afterVerdict\` is "ready" and \`after\` is PREPPED, run exactly once, with this JSON as the
   single argument (quote it for your shell):

       coordinator-invoke ${READY_OP.op} '${JSON.stringify({ ...READY_OP.params, plan_path: planPath }).split("'").join("'\\''")}'

   and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
   one-line failure in \`readyOpError\`. Otherwise run nothing and return neither field.
`
}

// The resolver's ready-op step. With a premise re-check owed the re-check's re-ask is the standing
// answer, so the resolver's ready is not final and the op must not stage a plan the re-check may pull.
function readyOpResolveStep(planPath, premiseRan) {
  if (!READY_OP) return ''
  return `4. If \`afterVerdict\` is "ready", \`afterPrepGate\` is "PREPPED" and \`unresolved\` is empty${premiseRan ? ' and \`touched\` is empty' : ''}, run exactly once, with this JSON as the
   single argument (quote it for your shell):

       coordinator-invoke ${READY_OP.op} '${JSON.stringify({ ...READY_OP.params, plan_path: planPath }).split("'").join("'\\''")}'

   and return its reply verbatim as \`readyOpReply\`. If it fails, omit \`readyOpReply\` and put the
   one-line failure in \`readyOpError\`. Otherwise run nothing and return neither field.
`
}

function prepGateRevise(baton, plan, trailDir, coverage, reply) {
  const steps = reply ? opRepairSteps(plan, reply, coverage) : `${coverageRepairStep(coverage)}
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
`
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
    // Enricher, not executor: block_subagent_plan_body_write denies an executor every plan-body
    // edit, which would leave this loop able to name a mechanical repair but never apply it.
    { model: 'sonnet', ...withRole('coordinator:enricher'),
      label: `prep-gate:${baton.id}`,
      phase: 'Review',
      schema: PREP_GATE_REVISE_SCHEMA,
    },
  ))
}

// census-unscreenable carries no engine repair, but the authoring bar names its rewrite: a pull whose
// only failure is that class is the enricher's to rewrite in its one revise pass.
function censusRewriteOwed(reply) {
  if (!reply || reply.verdict !== 'pulled' || reply.pull_class !== 'substantive') return false
  const classes = reply.prep_gate && reply.prep_gate.classes
  if (!classes || !classes.CENSUS || classes.CENSUS.kind !== 'census-unscreenable') return false
  return Object.entries(classes).every(([name, c]) => name === 'CENSUS' || (c && c.status === 'PASS'))
}

// The enricher is owed when there is no honoured op reply (fail closed: today's spawn), the reply
// names mechanical repairs, or its only failure is census-unscreenable. A ready or judgment reply with none owes it nothing.
const enricherOwed = (readinessReply) => !readinessReply || readinessReply.mechanical_repairs.length > 0
  || censusRewriteOwed(readinessReply)

const prepGateById = new Map()
await Promise.all(
  chains
    .filter(Boolean)
    .filter(({ plan }) => plan && plan.status !== 'blocked' && plan.planPath)
    .filter(({ readinessReply }) => enricherOwed(readinessReply))
    .map(async ({ baton, plan, coverage, readinessReply }) => {
      const result = await prepGateRevise(baton, plan, trailDir, coverage, readinessReply)
      if (result) prepGateById.set(baton.id, result)
    }),
)

// The op verdict that stands for a plan once the enricher (if owed) has run: the reply itself when
// nothing was repaired, the post-repair re-run when something was. null = no usable answer, which
// stands as `errored` (stage no-usable-reply) when the op was handed a review set, and pulls the
// plan as unusable only when it never was. An op that was called and failed stands as `errored`.
// The op's verdict is consumed, never recomputed or normalised here.
function opStanding(chain) {
  const reply = chain.readinessReply
  if (!reply) {
    // The op was called and failed: its own error, not a review verdict. The enricher's post-repair
    // run carries no reviews, so it never promotes this plan; the landing re-runs the op.
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

// Phase 5d — judgment resolve. A `judgment` standing verdict with no blocking input buys ONE
// plan-author pass that edits the plan in place and re-asks the op ONCE; the plan is `ready` only if
// that re-ask is. Counts come from the op's reply; a reply without them is counted from the review
// set the wave holds (it cannot see ledger clearance, so it over-counts a cleared review, and
// counts already-applied WARN findings as advisory).
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
    else if (r.verdict !== 'OK') blocking += n
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

// May the wave buy a resolver for this plan. `{ ok: false, reason }` names the refusal.
function judgmentResolvable(chain, standing, counts) {
  if (!standing || standing.verdict !== 'judgment') return { ok: false, reason: 'the standing op verdict is not judgment' }
  if (!chain.plan || chain.plan.status === 'blocked' || !chain.plan.planPath) return { ok: false, reason: 'no authored plan to resolve' }
  if ((chain.reviews || []).some((r) => r.pivot)) return { ok: false, reason: 'a reviewer returned PIVOT' }
  if (counts.blocking > 0) return { ok: false, reason: `${counts.blocking} blocking finding(s) are not the resolver's to resolve` }
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
  return trackAgent('judgment-resolve', agent(
    `Resolve the judgment findings still open on one reviewed plan, then re-ask the readiness op once.

Baton: ${baton.id} — "${baton.title}"
Plan: ${plan.planPath}

The readiness op answered \`judgment\` with this reason, verbatim:

    ${standing.reason}
${covBlock}${reviewBlock}
${CLI_RESOLUTION_RULE}
1. Edit the plan in place to resolve each finding above. Never scaffold, move or rename the plan,
   and touch nothing no finding names. List each finding you settled in \`resolved\` and each you
   could not settle, with why, in \`unresolved\`. List each spine row id and each frontmatter key you
   edited in \`touched\` (\`[]\` when you edited nothing that carries a citation).
2. Run \`coordinator-invoke plan.readiness_verdict\` ONCE with this JSON as the single argument
   (quote it for your shell), never the bare plan path: the op judges only the coverage, reviews and
   premise it is handed, so a bare re-ask returns ready on the prep gate alone:

       ${JSON.stringify(reaskParams)}

   Change it only so (the op trusts these inputs; dropping a review you did not settle makes the ready false): send ${coverageRule}; drop from \`reviews\` only a WARN review every one of whose
   uncleared ledger rows you list in \`resolved\`; leave \`premise\` and every other \`reviews\` entry
   as shown. A premise row the reason above lists as an "intended correction the resolver may take"
   (covered by the plan's \`corrects:\`/\`fixed_by\`) is yours to take: settle it in the plan and list
   it in \`resolved\`. It is not a blocking finding.
3. Record the reply's \`verdict\` as \`afterVerdict\`, its \`pull_class\` as \`afterPullClass\`, its
   \`reason\` as \`afterReason\` and its \`prep_gate.verdict\` as \`afterPrepGate\`, and its \`blocking\`
   array verbatim as \`afterBlocking\` when the reply carries one. If it fails (non-zero exit, no JSON reply, or an \`error\` envelope),
   run the identical command exactly once more. If that fails too, leave \`afterVerdict\` empty and
   put that run's own output VERBATIM (stderr, else stdout, prefixed \`exit <n>: \`, never summarised)
   in \`afterError\`. Never resolve or re-ask a second time, whatever it says.
${readyOpResolveStep(plan.planPath, premiseRan)}${REPO_ROOT_RULE}
${MID_RUN_DIRECTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'judgment-resolve'))}`,
    // Plan-author, not enricher: the enricher role is barred from authoring judgment.
    { model: 'opus', ...withRole('coordinator:plan-author'),
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

// Phase 5d, after the resolver: the plan was revised, so the premise rows it touched are re-judged
// before the plan is decided. This leg is a premise check that hosts the one op re-ask its fresh rows
// need; the op is never asked on the pre-revision rows. Owed only when the premise check ran (L and
// above), the resolver answered, and it edited something that carries a citation.
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
1. Check every load-bearing citation INSIDE the touched rows and keys above, and every prior row whose
   citation text occurs in them. Citations elsewhere in the plan are not yours: leave their rows alone.
   Return the fresh verdicts in \`rows\`, each with its \`questionClass\`, the citation verbatim, a
   verdict and its evidence. Return in \`retired\` each prior citation the plan no longer carries.
   You never refuse and never edit; you do not review the plan and never report it correct or ready.
   Five question classes: 1 paths exist · 2 symbols exist and are reachable the way the plan assumes ·
   3 branches, tags and commits exist · 4 falsifier arming (\`${ARMING_CHECK_CLI} <instrument> --json\`,
   its verdict carried into \`falsifierVerdict\` verbatim) · 5 asserted semantics (the named thing means
   what the plan says it means; \`UNCHECKABLE\` where no surface in this tree settles it). Row verdicts:
   RESOLVES · UNRESOLVED (absent) · CONTRADICTED (present, and the tree says otherwise) · UNCHECKABLE.
   Class 4 compares the falsifier's \`baseline_output\` against the tree at its \`baseline_ref\`,
   never at HEAD: read a read-shaped \`how\` with \`git show <baseline_ref>:<path>\`; a \`how\` that
   needs a checkout, build or test run at that ref is \`UNCHECKABLE\`. Every class-4 row carries
   \`baseline_ref\`, the value it read against.
   A CONTRADICTED row whose citation matches an entry on the plan's \`corrects:\` list says so in
   its evidence (\`on corrects: -> <fixed_by>\`) and still reports CONTRADICTED: the readiness op
   decides cover.

${PREMISE_CHECK_CONTRACT}

${INSTRUMENT_CAN_REPORT_RED_CONTRACT}

2. Run \`coordinator-invoke plan.readiness_verdict\` ONCE with this JSON as the single argument (quote
   it for your shell), never the bare plan path. Its \`premise.rows\` are the prior rows; replace them
   by the merged set: a row of yours replaces the prior row with the same citation, a citation in
   \`retired\` is dropped, any other row of yours is appended, and every prior row outside what you
   checked stays exactly as shown (send each row as \`verdict\`, \`citation\`, \`questionClass\`,
   \`evidence\` and, on class 4, \`baseline_ref\`). Change \`reviews\` and \`coverage\` only so: send
   ${coverageRule}; drop from \`reviews\` only a WARN review every one of whose uncleared ledger rows
   the resolver listed as settled above; leave every other \`reviews\` entry as shown:

       ${JSON.stringify(reaskParams)}

3. Record the reply's \`verdict\` as \`afterVerdict\`, its \`pull_class\` as \`afterPullClass\`, its
   \`reason\` as \`afterReason\`, and its \`blocking\` array verbatim as \`afterBlocking\` when the reply
   carries one. If it fails (non-zero exit, no JSON reply, or an \`error\` envelope), run the identical
   command exactly once more. If that fails too, leave \`afterVerdict\` empty and put that run's own
   output VERBATIM (stderr, else stdout, prefixed \`exit <n>: \`, never summarised) in \`afterError\`.
   Never re-check or re-ask a second time, whatever it says.
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

// The premise a verdict entry carries: the rows as merged after a re-check, else the checker's own.
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
  // A ready re-ask whose gate the resolver reported as anything but PREPPED is not ready, as
  // honouredReadiness treats the reviewer's reply; an absent gate (the re-check leg) is not a refusal.
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
  // A resolver re-ask that answered is the standing reply, so its set replaces the first reply's.
  const { blocking: _firstSet, ...unset } = carried
  const standingSet = ans.afterVerdict
    ? (Array.isArray(ans.afterBlocking) ? { blocking: ans.afterBlocking } : {})
    : (Array.isArray(_firstSet) ? { blocking: _firstSet } : {})
  return { ...unset, ...standingSet, judgmentResolve: { state: 'failed', cause, unresolved } }
}

// A ready entry's ready-op outcome, from whichever leg made the ready call: the last reviewer for an
// unrepaired plan, the repair loop for a repaired one. An entry with neither field is a fault the
// caller cannot tell from a skipped op, so a missing reply under a configured op becomes an error.
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

// Phase 6 — the per-baton trail, attached to each verdict entry as `trail`: the reviewers' own
// verdicts and sidecars, the premise rows, the op line and the ledgers.
const trailById = new Map(fireChains.map((chain) => {
    const { decision, baton, plan, reviews, premiseCheckVerdict, checkersSkipped, substitutions } = chain
    // Every reviewer is named with their OWN resolved verdict. A collapsed
    // "the review said X" is how a wave loses the review that disagreed.
    const verdicts = reviews.map((r) => `${r.reviewer}=${r.verdict}`).join(', ') || 'none ran'
    // Explicit row so "premise check ran and found nothing" and "premise check did not run"
    // (null/malformed return, dropped upstream) render as visibly different states, never as the
    // same silence. An `OK` with zero citations examined must not render like an `OK` that checked
    // everything; `citationsChecked` carries that count.
    const premiseCheckLine = premiseCheckVerdict
      ? `${premiseCheckVerdict.verdict}${premiseCheckVerdict.citationsChecked === 0 ? ' (0 citations examined — UNATTEMPTED, not a clean pass)' : ''}${(premiseCheckVerdict.blockingCitations || []).length ? ` blocking: ${premiseCheckVerdict.blockingCitations.join('; ')}` : ''}${premiseCheckVerdict.pivotCandidates ? ` pivot candidates (a reviewer's call, not a route): ${premiseCheckVerdict.pivotCandidates}` : ''}`
      : checkersSkipped
        ? `skipped: ${decision.tshirt} below L — the premise check fires at L and above only; citations UNCHECKED, not clean`
        : 'DID NOT RUN — no premise-check verdict reached the trail for this baton'
    const pivots = reviews.filter((r) => r.pivot)
    const blockers = reviews.filter((r) => r.verdict === 'BLOCKED')
    // A mixed set is called out by name rather than left for a reader to notice. It is
    // the case a fast read most reliably flattens: seeing one PIVOT, a reader stops
    // reading, and the co-reviewer's fixable findings — the replan's actual inputs —
    // never reach the brief.
    const mixed = pivots.length && reviews.length > pivots.length
      ? `\n      MIXED SET: ${pivots.map((r) => r.reviewer).join(', ')} pivoted; `
        + `${reviews.filter((r) => !r.pivot).map((r) => `${r.reviewer}=${r.verdict}`).join(', ')} did not. `
        + `Both survive — the pivot decides the ROUTE, the rest are the replan's inputs.`
      : ''
    const aliases = reviews.filter((r) => r.aliased)
    return [baton.id, `  - ${baton.id} "${baton.title}" [${decision.tshirt}, ${decision.route}]
      plan: ${plan ? plan.planPath : '(not written)'}${plan && plan.status === 'blocked' ? ` — BLOCKED: ${plan.blockedReason}` : ''}${plan && plan.planPathCorrected ? `\n      planPath CORRECTED: planner returned ${plan.planPathCorrected} (a trail sidecar); the baton's own plan path was used instead` : ''}${substitutions && substitutions.length ? `\n      reviewer substitution: ${substitutions.join('; ')}  <-- the plan was NOT reviewed by whom the em named` : ''}${chain.reviewNote ? `\n      review path: ${chain.reviewNote}` : ''}${chain.chattyWave ? '\n      review path: one chatty wave (concurrent reviewers; a dedicated host ran the readiness op)' : ''}
      premise-check: ${premiseCheckLine}
      reviews: ${verdicts}${pivots.length ? `  <-- PIVOT (${pivots.map((r) => r.reviewer).join(', ')})` : ''}${blockers.length && !pivots.length ? '  <-- BLOCKED, fixable' : ''}${mixed}${aliases.length ? `\n      alias resolved: ${aliases.map((r) => `${r.reviewer}: ${r.aliased}`).join('; ')}` : ''}
      ${reviews.map((r) => `sidecar: ${r.sidecarPath}${r.premiseFailure ? ` premise-failure: ${r.premiseFailure}` : ''}${r.alternativesConsidered ? ` alternatives: ${r.alternativesConsidered}` : ''}`).join('\n      ')}
      premise rows: ${premiseLines(standingPremise(chain)).split('\n').join('\n      ')}
      readiness op: ${readinessOpLine(chain)}${chain.readyOpError ? `\n      readyOp error: ${chain.readyOpError}` : ''}${chain.readyOpDishonoured ? '\n      readyOp ran on a dishonoured reply' : ''}
      findings ledgers: ${ledgerLine(plan, reviews)}${prepGateLine(baton.id) ? `\n      prep gate (after reviewers, one revise-in-place loop): ${prepGateLine(baton.id)}` : ''}`]
}))

// HOST AVAILABILITY is never a pull reason and is deliberately NOT reconciled here: this script
// has no filesystem primitive to read a plan's declared `external_gate`, and every reconciliation
// below makes a verdict STRICTER, so promoting a host-grounded pull back to `ready` would run
// against that direction. The op decides it from the plan
// (THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON).

// One verdict per chain, from data the wave already holds; the first matching rule decides. The
// op's standing verdict is mapped, never recomputed; a `judgment` standing that reaches here was
// already offered its one resolve and is a pull. The spine, review-ran and prep-gate
// reconciliations below only make an entry stricter.
function pivotReplanBrief(reviews) {
  return `Reconciled from the review set.\n`
    + reviews
      .map((r) => `${r.reviewer} [${r.verdict}]: ${r.premiseFailure
        || (Array.isArray(r.blockingCitations) && r.blockingCitations.length ? `blocking: ${r.blockingCitations.join('; ')}` : '')
        || `${r.findingCount || 0} finding(s), see ${r.sidecarPath}`}${r.alternativesConsidered ? ` | alternatives: ${r.alternativesConsidered}` : ''}`)
      .join('\n')
}

const OP_ERROR_CAP = 4000
// Verbatim up to the cap; a longer error says so rather than ending mid-sentence unmarked.
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
  chains.filter(Boolean).map((chain) => [chain.baton.id, standingPremise(chain)]),
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
// refuses the row outright without it ("verdict carries no planPath"): measured on claude-klabauter,
// a fire landed 0/0/0 with four refusals after 31 agents, every plan on disk and every verdict
// sound. The path is knowable here without asking anyone.
const planPathById = new Map(
  chains
    .filter(Boolean)
    .map(({ baton, plan }) => [baton.id, (plan && plan.planPath) || baton.planPath || null])
    .filter(([, p]) => p),
)

// A PIVOT routes MECHANICALLY: `opVerdictFor` maps any PIVOT in a chain's review set to `replan`
// before the standing op verdict is read, so no `ready` can reach the landing on a pivoted plan.
const coverageById = new Map(fireChains.map((c) => [c.baton.id, coverageForOp(c.coverage)]))
const opReviewsById = new Map(fireChains.map((c) => [c.baton.id, c.opReviews || []]))

// A reconciled-to-pulled entry carries no readyOpReply: the reply belongs to a ready entry only.
const notReady = ({ readyOpReply, ...rest }) => rest

const verdicts = fireChains
  .map(opVerdictFor)
  .map((v) => {
  const reviews = reviewsById.get(v.batonId) || []
  const entry = {
    ...v,
    route: routeById.get(v.batonId) || null,
    trail: trailById.get(v.batonId) || null,
    // Recorded repo-relative whatever spelling the planner echoed: its brief names a new plan by
    // absolute path so the agent resolves it against the right checkout, and that host path is
    // then committed state no other box can open. This fire's own record of the plan is the only
    // source; `roadmap.blitz_land` refuses a row without it.
    planPath: repoRelativeCitation(planPathById.get(v.batonId)) || null,
    // Carried so the LANDING can refuse independently. `roadmap.blitz_land` re-checks
    // this and will not stamp a plan a reviewer pivoted, whatever this workflow decided
    // — two enforcement points, because the one in a file an agent edits is the one
    // that goes missing.
    reviewVerdicts: reviews.map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
    // The op's own param shapes, so a revise block passes them straight back to
    // plan.readiness_verdict: coverage {verdict, mechanicalFindings, judgmentFindings} or null, and
    // reviews [{reviewer, verdict}] (the premise check and every loop reviewer).
    coverage: coverageById.get(v.batonId) || null,
    reviews: opReviewsById.get(v.batonId) || [],
    premise: premiseForOp(premiseById.get(v.batonId)),
  }
  // SPINE, reconciled mechanically for the same reason the pivot is: a plan with no
  // `plan-tasks` block declares no work a run can schedule, the planner brief says so, and
  // nothing between authoring and the mise-prep gate checks it. Measured 2026-09-10: a
  // 869-line plan with zero fenced blocks passed premise-check, two reviewers, integration,
  // escalation resolution and the old readiness gate, landed `approved`, and was refused a
  // ceremony later with SPINE/spine-absent. The premise pass reports it and the
  // reconciliation happens here.
  const premiseRow = premiseById.get(v.batonId)
  if (premiseRow && premiseRow.spinePresent === false && entry.verdict === 'ready') {
    return {
      ...notReady(entry),
      verdict: 'pulled',
      // Names its SOURCE, not just its claim. The old wording was a flat assertion about the
      // document ("the plan carries no plan-tasks spine"), which reads as a finding rather than
      // as one reader's report — so a driver had no way to tell a measurement from a guess, and
      // the field behind it appears in no sidecar. Whoever reads this next can now re-run the
      // one check that produced it.
      spineOverride:
        'The op verdict was ready; the premise check reported plan-spine-check NO-SPINE for this plan. '
        + 'Reconciled to pulled. VERIFY BEFORE ACTING ON IT: re-run plan-spine-check against the '
        + 'plan, and if it reports VALID this override is wrong and the op verdict stood.',
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
      ...notReady(entry),
      verdict: 'pulled',
      reviewOverride:
        'The op verdict was ready; the plan was written and no reviewer ran over it, so no finding is '
        + 'known to have been applied. Reconciled to pulled.',
      reason: `${entry.reason} [reconciled: no reviewer ran over a plan that exists]`,
    }
  }

  // PREP GATE, reconciled mechanically: the re-gate verdict decides. Only a measured non-PREPPED
  // `after` pulls; a plan with no prep-gate row (blocked, not authored this fire) is untouched.
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
${MID_RUN_DIRECTION_RULE}
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
  ready: verdicts.filter((v) => v.verdict === 'ready'),
  pulled: verdicts.filter((v) => v.verdict === 'pulled'),
  replan: verdicts.filter((v) => v.verdict === 'replan'),
  // The readiness op was called and failed after one retry. Each entry carries the op's error and
  // its exact params; the landing re-runs only the op over them (land-wave --errored-only), and
  // nothing here promotes one to ready.
  errored: verdicts.filter((v) => v.verdict === 'errored'),
  // PM residue only: entries an adjudicator marked `pm_only` (or that named an irreversible gate,
  // or whose adjudicator returned nothing). Every entry carries its `adjudication`.
  surfacedToPm: residueSurfacedToPm,
  // PM-bound entries an adjudicator ruled on, each carrying `adjudication` and the `pm_ruling` it
  // wrote on the baton. The PM reads these at the receipt; nothing re-asks them.
  adjudicated,
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
  // Always empty: this wave executes no XS. Kept so a reader of an old and a new result sees
  // the same keys; a frozen fire's own executor may still fill it.
  dispatched: [],
  // Execution-open, sized XS batons handed to the driver, one ask run each, which closes them
  // through `dispatch.land_run`: { batonId, record, sizingObject, deliverableId }.
  xsRuns,
  // Sized and routed, but neither planned nor handed off as an XS run — including an
  // XS whose EXECUTION gate is shut or that has no sizing object. Each names the room it belongs in.
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
  // wired here — after the op verdict is mapped for this baton — so it renders what the wave
  // actually decided rather than re-deriving it. Wave mode assembles no digest (§ body item 7
  // reserves that for a caller iterating every baton).
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
