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
 *   - NOT a PM proxy. `route: pm-decision` and XL exits leave the wave in `surfacedToPm` rather
 *     than being resolved inside it.
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
 *     trailDir: string,       // e.g. "state/plan-blitz/20260905T120000Z" — the durable trail.
 *                             //  Every agent writes its sidecar HERE, and the EM's readiness
 *                             //  gate reads them from disk. Caller scaffolds it before firing;
 *                             //  this script has no fs primitive of its own.
 *     gateReportPath: string, // the frozen `roadmap.plan_gate` JSON this wave was resolved from.
 *                             //  Passed to the blitz-em so its judgment reads the same gate
 *                             //  state the wave was planned against, not a re-derived one.
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
 * REPAIR MODE — a distinct invocation shape, never mixed with the args above:
 *   {
 *     mode: 'repair',
 *     trailDir: string,
 *     repairBatons: [ {
 *       batonId: string,
 *       planPath: string,        // the plan already on disk. No plan on record -> refused.
 *       reviews: [ {             // the structured pointer records already read off disk by
 *                                 //  the CALLER (this script has no fs primitive of its own —
 *                                 //  see WORKFLOW-AGENT-AS-FILE-HANDLE). Each is fed verbatim
 *                                 //  through the existing resolveVerdict(), never reconstructed.
 *         reviewer: string,
 *         sidecarPath: string,
 *         verdict: string,       // the reviewer's own word, exactly as REVIEW_SCHEMA carries it
 *         premiseFailure: string | null,
 *       } ],
 *       unresolvedPointers: [ { pointerPath: string, error: string } ], // present -> refused
 *     } ]
 *   }
 * Returns: { mode: 'repair', repaired: [...], refused: [...] } — see Repair mode below.
 *
 * Invocation:
 *   Workflow({
 *     scriptPath: "coordinator/workflows/plan-blitz.mjs",
 *     args: {
 *       repoRoot: "/abs/path/to/the/repo",
 *       waveIndex: 0,
 *       trailDir: "state/plan-blitz/20260905T120000Z",
 *       gateReportPath: "state/plan-blitz/20260905T120000Z/gate-report.json",
 *       batons: [ { id: "pcore-03", path: "state/handoffs/...md", title: "...",
 *                   sized: false, planPath: null } ]
 *     }
 *   })
 *
 * Returns: { waveIndex, ready, pulled, replan, surfacedToPm, trailDir } — see WAVE RESULT below.
 */

// `phases` is a DECLARATION LIST, not the schedule. Its order is what a reader sees in the run's
// progress; what actually orders a phase is the data it consumes — the premise check needs a
// written plan, the reviewers read its report, the mutating phase runs after everything read the
// tree. A phase inserted or moved here changes the display and nothing else, so a later author
// reordering this pipeline reorders the CALLS and keeps this list's membership in step (the
// contract test asserts set-equality both directions, never position).
//
// No apostrophe in a `detail` string. The engine's `_workflow_contract.meta_phase_titles` pairs
// quotes naively, so one `\'` shifts the pairing and every phase declared after it goes missing
// from what the checker believes was declared — reported as a WARN about a phase that is right
// there. An even number happens to cancel, which is why this passes until it does not.
export const meta = {
  name: 'plan-blitz',
  description: 'One planning wave: sonnet scouts size the batons, an Opus EM finalises, Opus planners write, a sonnet pass resolves each plan\'s citations against the tree, plans are reviewed and integrated unconditionally, and the EM gates readiness at the end.',
  phases: [
    { title: 'Size', detail: 'One sonnet sizing-scout per unsized baton — substrate read, touchpoint inventory, prior art, and a proposed t-shirt with its evidence. Skipped for a baton that already cites a sizing-object.' },
    { title: 'Size review', detail: 'One Opus blitz-em over the whole wave. Interrogates every proposed size (revising down by default), finalises the route via sizing-assemble, and emits the per-baton dispatch spec the Plan phase reads.' },
    { title: 'Plan', detail: 'One Opus planner per baton, on every route and at every size — authoring is not a lane the wave economises on. Writes the plan doc through coordinator:plan / scaffold-plan; never hand-authors frontmatter.' },
    { title: 'Premise check', detail: 'One sonnet pass per drafted plan, dispatched once its plan path is trusted and before any reviewer fires. Resolves the load-bearing citations in that plan against the tree — paths, symbols, refs, whether its falsifier can report red, and whether a named thing means what the plan says. It reports per-class ROWS and never a plan-level verdict; the seam after it translates those rows onto REVIEW_SCHEMA so they reach the integrator that already applies every finding. A premise miss routes BLOCKED; the class-5 rows with no writable fix are NAMED for the reviewers, who own the separating test.' },
    { title: 'Review', detail: 'Reviewers resolved per baton from the EM dispatch spec, never prescribed in the plan file. Fires unconditionally — the EM is not consulted about whether a plan deserves review.' },
    { title: 'Integrate', detail: 'review-integrator per plan, also unconditional, including on a clean OK. Applies findings and escalates ASKs. A PIVOT from any reviewer suspends integration for the whole plan, with every sidecar still triaged so no co-reviewer findings are lost.' },
    { title: 'Resolve escalations', detail: 'Conditional: fires only where integration escalated an ASK carrying two or more REVIEWER-ATTRIBUTED alternatives. Re-invokes the Plan phase planner itself, in its revising branch — no new actor — picking ONLY among catalogued option ids, never authoring a third. `choicesMade` is required, and what was NOT chosen is computed from the catalogue rather than taken from the pick. Skipped whole on a PIVOT and where nothing is choice-shaped.' },
    { title: 'Dispatch', detail: 'One executor per XS/dispatch baton whose EXECUTION gate is open. Runs AFTER planning so the wave plans against a stable tree and the only mutating phase is last. Bounded to the remit the baton itself states — an XS that grows is a sizing defect, not a bigger job.' },
    { title: 'Readiness gate', detail: 'One Opus blitz-em over the durable trail. Per plan: ready, pulled, or replan. A PIVOT routes to a replan baton for a later wave rather than halting this one, and is reconciled mechanically rather than left to the gate.' },
  ],
}

// ---------------------------------------------------------------------------
// Args intake — the harness may hand `args` over as a STRING
// ---------------------------------------------------------------------------
//
// The Workflow tool's `args` input declares no type, so a caller passing a JSON
// object can have it arrive here as the SERIALIZED TEXT of that object. Every
// `parsedArgs.<key>` read below then resolves `undefined` against a string,
// `batons` comes back empty, and the run takes the legitimate empty-wave exit:
// it returns `{ empty: true }` having dispatched nothing. Measured on a fire
// carrying seven batons — 154ms, zero agents, no error raised anywhere. That is
// the worst shape this failure can take, because an empty wave is a REAL state
// the caller is told to RECORD rather than investigate, so the fire reads as
// "nothing left to plan" while every baton in it returns as a candidate in the
// next gate read. Identical coercion, and identical reason, to
// `wsc-review-partition.mjs :: parsedArgs`, which met this first.
//
// Bound under its own name rather than shadowing `args`: the runtime owns how
// that name is bound, and a module-scope redeclaration of it is a SyntaxError
// on any host that binds it lexically.
const parsedArgs = (typeof args === 'string') ? JSON.parse(args) : args
if (!parsedArgs || typeof parsedArgs !== 'object') {
  // Separates "the caller built no payload" from "the wave found nothing to do".
  // Both reach the same exit shape otherwise, and only one of them is a defect.
  throw new Error(
    'plan-blitz received no args object (got ' + String(parsedArgs) + '). The caller resolves ' +
    'the wave with roadmap.plan_gate, freezes that report to disk, and passes waveIndex, ' +
    'trailDir, gateReportPath and batons — see the args contract at the top of this file.'
  )
}

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

const SIZING_SCHEMA = {
  type: 'object',
  required: ['batonId', 'tshirt', 'evidence', 'sidecarPath'],
  properties: {
    batonId: { type: 'string' },
    tshirt: { type: 'string', enum: ['XS', 'S', 'M', 'L', 'XL', 'XXL'] },
    // Free text, deliberately: the blitz-em interrogates the REASONING, and a scout forced into
    // an enum of pre-named risk categories reports the nearest category rather than what it saw.
    evidence: { type: 'string' },
    touchpoints: { type: 'array', items: { type: 'string' } },
    // Separated from `touchpoints` on purpose — a count of files is breadth, and breadth is not a
    // notch. Keeping them in one field is how a scout talks itself from 6 files into an L.
    unknownMechanisms: { type: 'array', items: { type: 'string' } },
    priorArt: { type: 'array', items: { type: 'string' } },
    crossTeamDependency: { type: 'string' },
    sidecarPath: { type: 'string' },
  },
}

const WAVE_DISPATCH_SCHEMA = {
  type: 'object',
  required: ['decisions'],
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
          // What the EM CHANGED and why. A rationale that does not name a change is the EM
          // agreeing with the scout, which is a legitimate outcome that still has to be said.
          rationale: { type: 'string' },
          // The `state/sizings/<id>.yaml` this baton's sizing was scaffolded into, or null
          // when the route produces no plan. A plannable baton with null here cannot cite
          // anything, and the plan it produces fails the sizing-citation gate.
          sizingObject: { type: ['string', 'null'] },
          reviewers: { type: 'array', items: { type: 'string' } },
          // True when this baton leaves the wave instead of being planned in it: a
          // pm-decision route, an XL exit, or a size that revealed a scope defect.
          surfacedToPm: { type: 'boolean' },
          surfacedQuestion: { type: 'string' },
        },
      },
    },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['batonId', 'planPath', 'status'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },
    status: { type: 'string', enum: ['drafted', 'blocked'] },
    // Populated on status: blocked — a planner that could not write a plan says why, and the
    // wave carries that to the readiness gate instead of dropping the baton silently.
    blockedReason: { type: 'string' },
    exitCriterion: { type: 'string' },
    // Populated only by the Resolve-escalations pass (see `planner`'s `escalation` argument and
    // `RESOLVE_SCHEMA` below) — never by an ordinary authoring or revising call.
    //
    // Review note (overengineering-reviewer, 2026-09-06): the `blockedReason` precedent
    // originally cited to justify this field was checked and REFUTED — `blockedReason` is the
    // explanatory partner of `status: 'blocked'`, which IS read as control flow at the plan
    // status branch above and by the readiness gate, so that pair is live and only one half is
    // inert. `choicesMade` has no such live half in the plan body's own control flow, and the
    // resolve pass at :707 already edits the plan body with its picks — that argument does not
    // survive and is not the reason this field stays.
    //
    // The field stays for a different, verifiable reason: the readiness gate is a separate Opus
    // agent that reads the RENDERED TRAIL, not the plan body (see the `trailLines` / gate prompt
    // below), and that gate prompt is written to read a resolution with the SAME priority it
    // gives an unresolved escalation. `choicesMade` is what feeds that render — without it,
    // resolving an ASK in-wave would silently empty the gate's highest-signal input. One entry
    // per escalated ASK the resolve pass acted on; `escalationId` and `chosen` are ids the wave
    // itself minted into the catalogue the pass was handed (`convergenceCatalogue`), never
    // invented text — the requirement that every escalated ASK carries two-or-more attributed
    // options is `review-integrator.md` § ASK Options Carry Their Source.
    choicesMade: {
      type: 'array',
      items: {
        type: 'object',
        // `rejected` is deliberately NOT required, and any value reported here is not read.
        // What was not chosen is COMPUTED from the catalogue by `reconcilePicks` — it is the one
        // field the actor that chose has an incentive to shorten, and the catalogue already
        // knows it. Requiring it would teach the pass that its own copy is authoritative.
        required: ['escalationId', 'chosen'],
        properties: {
          escalationId: { type: 'string' },
          chosen: { type: 'string' },
          rejected: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

// A premise check answers CLASSES, and its output is deliberately not a verdict on the plan.
// There is no `ok`/`sound`/`ready` field and no place to put one: the moment a schema offers a
// plan-level judgment, a downstream reader treats a clean citation table as an approval, and a
// pass built to catch one class starts standing in for correctness. Counts and rows only.
//
// `UNCHECKABLE` is a first-class row value rather than an omission, because the semantic class
// (5) is only sometimes mechanically decidable — the repo has to carry a surface that forbids the
// assumption. A row silently dropped when nothing settled it is indistinguishable from a row that
// resolved, which would convert this pass's honest gap into a false clean.
const PREMISE_SCHEMA = {
  type: 'object',
  required: ['batonId', 'planPath', 'rows', 'sidecarPath'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },
    rows: {
      type: 'array',
      items: {
        type: 'object',
        required: ['questionClass', 'citation', 'verdict'],
        properties: {
          // 1 paths · 2 symbols · 3 refs · 4 falsifier arming · 5 asserted semantics.
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
    // Carried verbatim from `instrument-can-report-red.py` rather than restated. A paraphrase of
    // that surface's verdict is a second implementation of its predicate wearing a shorter name.
    falsifierVerdict: { type: 'string' },
    citationsSkipped: { type: 'integer' },
    sidecarPath: { type: 'string' },
  },
}

// The Resolve-escalations pass's own return contract. Same shape as PLAN_SCHEMA, but
// `choicesMade` is REQUIRED here — a resolve pass that has nothing to record has not actually
// resolved anything, so leaving the field optional on this call buys the gate nothing (the
// reasoning `overengineering-reviewer` accepted for cutting it, applied instead to un-optionalling
// it). Never used for the ordinary authoring/revising `planner()` call.
const RESOLVE_SCHEMA = {
  ...PLAN_SCHEMA,
  required: [...PLAN_SCHEMA.required, 'choicesMade'],
}

// The verdict vocabulary is a ROUTE, not a severity ladder. BLOCKED and PIVOT are not
// adjacent rungs on one scale — they answer different questions, and the wave does
// different things with them:
//
//   BLOCKED — "this plan is wrong until you fix these". The DIRECTION holds; the
//             findings are the work. Integration applies them, the plan reaches the
//             gate, and a fixed plan can be approved in this same wave.
//   PIVOT   — "do not think about this plan; this direction cannot proceed". No set of
//             findings repairs it. Routes the baton to a replan.
//
// PIVOT is deliberately NOT the top of the severity ladder, because a reviewer reaching
// for the strongest word available must not land on the route that discards the plan.
// It is reached by judging DIRECTION, and `premiseFailure` is the field that carries
// that judgment.
//
// REJECTED is accepted on input and never taught. It is the strongest severity in the
// FLEET-WIDE reviewer enum (`coordinator/agents/staff-eng.md`: APPROVED /
// APPROVED_WITH_NOTES / REQUIRES_CHANGES / REJECTED), so a reviewer carrying that
// vocabulary in will reach for it, and dropping it from this enum would fail the whole
// review's schema and lose the sidecar — the exact loss this vocabulary exists to stop.
// `resolveVerdict` resolves it by evidence and says so; it is never mapped silently.
const REVIEW_SCHEMA = {
  type: 'object',
  required: ['batonId', 'reviewer', 'verdict', 'sidecarPath'],
  properties: {
    batonId: { type: 'string' },
    reviewer: { type: 'string' },
    verdict: { type: 'string', enum: ['OK', 'WARN', 'BLOCKED', 'PIVOT', 'REJECTED'] },
    sidecarPath: { type: 'string' },
    findingCount: { type: 'integer' },
    // The discriminant, not decoration. A PIVOT is a claim about direction and this is
    // where the claim is stated; `resolveVerdict` reads it to resolve the REJECTED
    // alias, so an absent one costs that review the pivot route.
    premiseFailure: { type: 'string' },
    alternativesConsidered: { type: 'string' },
  },
}

const INTEGRATION_SCHEMA = {
  type: 'object',
  required: ['batonId', 'planPath', 'applied', 'escalated'],
  properties: {
    batonId: { type: 'string' },
    planPath: { type: 'string' },
    applied: { type: 'integer' },
    escalated: { type: 'array', items: { type: 'string' } },
    // The same escalations as `escalated`, carrying the one thing a picker needs: WHO
    // enumerated each alternative. Nothing here widens what the integrator may apply on its
    // own — the integrator's contract ALREADY requires an ASK to carry two-or-more concrete
    // options and the recommendation it would make if forced. This is that material, structured,
    // with each option attributed. `escalated` stays the prose list the gate has always read.
    //
    // `options[].source` is a REVIEWER NAME and the catalogue drops any option whose source is
    // not a reviewer that actually reviewed this baton. That is where "only a reviewer-enumerated
    // alternative may be picked" is enforced in code rather than in prompt text: an option the
    // integrator composed itself is attributed to the integrator, does not survive the filter,
    // and is therefore not choosable.
    escalations: {
      type: 'array',
      items: {
        type: 'object',
        required: ['summary', 'options'],
        properties: {
          summary: { type: 'string' },
          options: {
            type: 'array',
            items: {
              type: 'object',
              required: ['source', 'text'],
              properties: {
                // The reviewer who wrote this alternative, or the integrator's own name when
                // the integrator composed it. Unattributed is treated as the integrator's.
                source: { type: 'string' },
                // The reviewer's words, verbatim. A paraphrase is a second thing to keep true,
                // and the chooser picks by reading these.
                text: { type: 'string' },
              },
            },
          },
          recommendation: { type: 'string' },
          // Anti-dodge field (4) from the integrator's own contract, carried rather than
          // restated: it is the APPLICABILITY axis stated per escalation — why this finding
          // names a change nobody can make without choosing. Verdict severity is not a proxy
          // for it and is deliberately absent here.
          whyItExceedsDiscretion: { type: 'string' },
        },
      },
    },
    rejected: { type: 'boolean' },
    reportPath: { type: 'string' },
  },
}

const DISPATCH_SCHEMA = {
  type: 'object',
  required: ['batonId', 'completed', 'summary'],
  properties: {
    batonId: { type: 'string' },
    completed: { type: 'boolean' },
    summary: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    // Populated when `completed` is false. An executor that could not finish says
    // why rather than reporting a partial as done — a half-done XS left looking
    // finished is worse than one left plainly open.
    blockedReason: { type: 'string' },
  },
}

const READINESS_SCHEMA = {
  type: 'object',
  required: ['verdicts'],
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
          // Present on verdict: replan. Written for a session that will not have this
          // context — the baton it becomes may be picked up several waves later.
          replanBrief: { type: 'string' },
        },
      },
    },
  },
}

// ---------------------------------------------------------------------------
// Role resolution — agentType is an ENRICHMENT, never the contract
// ---------------------------------------------------------------------------
//
// `args.pluginAgentsAvailable` says whether `coordinator:*` agent types resolve
// on this machine. It exists because this pipeline must fire in two environments
// that differ in exactly one way: whether the coordinator plugin is installed.
// It defaults to FALSE — the safe direction, because the failure it guards is
// silent and the cost of being wrong the other way is only a thinner agent.
//
// An `agentType` naming an agent the harness cannot resolve does NOT fail the
// dispatch — it yields a generic agent wearing that role's label. That is the
// worst outcome available: the trail records "staff-eng reviewed this" for a
// review no reviewer performed, and nothing anywhere reports the substitution.
// Measured: a cloud container with no plugin install resolves none of the
// `coordinator:*` types this pipeline names.
//
// So every brief below carries its role contract INLINE and is correct with no
// agentType at all. Passing one adds the full persona on a machine that has it;
// omitting it costs the persona's depth and nothing else. A caller that cannot
// tell whether the plugin is installed should omit it — a thinner reviewer is
// recoverable, a mislabelled one is not.

const PLUGIN_AGENTS = parsedArgs.pluginAgentsAvailable === true

function withRole(agentType, opts) {
  return PLUGIN_AGENTS && agentType ? { ...opts, agentType } : opts
}

// ---------------------------------------------------------------------------
// Reviewer roster — a CLOSED set, resolved BEFORE dispatch
// ---------------------------------------------------------------------------
//
// The blitz-em picks reviewers from a brief. A repo whose own CLAUDE.md names
// reviewers by PERSONA FIRST NAME ("add the Game Dev Reviewer or the Data Science Reviewer") supplies that vocabulary
// too, and the em emits what it read: `coordinator:the Data Science Reviewer`, `coordinator:sid`.
// Neither is an agent type. Measured: both hard-failed at dispatch, and one baton
// — an irreversible corpus republish — came back with NO reviewer, NO sidecar, and
// a readiness gate correctly refusing to gate over an empty trail. The wave slot
// was spent and the plan went unreviewed.
//
// So an unresolvable reviewer is resolved HERE, never passed through to dispatch.
// Two properties matter and they are not the same one:
//   - a name that does not resolve never reaches the harness, so the chain cannot
//     hard-fail on it, and
//   - a baton never ends with zero reviewers — a substitution DEGRADES the
//     reviewer, it does not delete the review.
// The substitution is recorded on the chain and printed in the trail. A silent
// downgrade is the same defect wearing a quieter failure mode.
const REVIEWER_ROSTER = new Set([
  'coordinator:staff-eng',
  'coordinator:eng-director',
  'coordinator:overengineering-reviewer',
])

// Persona first names are how humans and repo docs refer to these agents, so they
// are the exact strings that arrive when a brief is read literally. Mapping them
// costs less than forbidding them. A persona living in ANOTHER plugin's namespace
// is deliberately absent: this pipeline cannot assume a sibling plugin is
// installed, and emitting a type that might not resolve is the defect being fixed.
const REVIEWER_ALIASES = new Map([
  ['patrik', 'coordinator:staff-eng'],
  ['zoli', 'coordinator:eng-director'],
  ['kira', 'coordinator:overengineering-reviewer'],
  ['waste', 'coordinator:overengineering-reviewer'],
])

const DEFAULT_REVIEWER = 'coordinator:staff-eng'

// Returns { reviewers, substitutions }. `reviewers` is never empty.
function resolveReviewers(named) {
  const wanted = Array.isArray(named) && named.length ? named : [DEFAULT_REVIEWER]
  const substitutions = []
  const resolved = []

  for (const raw of wanted) {
    const text = String(raw || '').trim()
    if (REVIEWER_ROSTER.has(text)) {
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

// Hand-synced from coordinator/snippets/premise-check-contract.md (C1) and
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
It is written to be INLINED into a dispatch brief, never dispatched as its own agent — the
\`PLUGIN_AGENTS\` default-off constraint means an \`agentType\` the harness cannot resolve silently
degrades to a generic agent wearing the role's label, which reuses the persona and loses the
check. Whatever consumes this text must inline it directly.

**Classes 1 and 2 — paths and symbols (mechanical).** For every cited in-repo path: does it
exist? For every cited \`file:line\` / \`file:symbol\` claim: does the symbol exist in that file? This
is the same check plan-coverage-checker's Lens 3 already runs (\`ls\`-check cited paths,
\`Read\`-verify cited claims, grep backtick-quoted in-repo constants) — it is not re-derived here.

**Why \`ls\`/\`Read\`/\`grep\` and not the symbol-graph tools.** \`project_referencers\` and
\`project_symbol_callers\` would answer classes 1 and 2 more precisely, and they are deliberately not
used: this text is INLINED into a dispatch brief inside a workflow, and an MCP tool surface is not
guaranteed to be present for the agent that receives it — a check that silently degrades when a tool
is missing is worse than one built from primitives that are always there. The project-rag index is
also a projection that can lag the tree (1494 commits behind at the time this shipped), and a premise
check that reads a stale projection would report the tree as it was, which is the exact failure it
exists to catch. Existing checker agents ARE reused: this contract carries plan-coverage-checker's
Lens 3 calibration over verbatim rather than re-deriving it, and Lens 3 consumes this same text.

**Tolerance rule, carried over verbatim, do not recalibrate:** same-file line-number drift alone
(same file, same symbol, shifted line number) is tolerated and is NOT a finding; a missing file or
an absent symbol is a real finding.

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
precision — each row sourced from a wave's per-baton \`*.premise-check.md\` sidecar under that
wave's trail directory (\`sidecarFor(trailDir, batonId, 'premise-check')\` in \`plan-blitz.mjs\`).
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
rests on is actually true of this tree right now.`,

  'review-integrator': `You are the review-integrator: a precise applier of reviewer decisions, not
a persona with opinions about quality. Apply every finding — filtering happened upstream. You are
UNCONDITIONAL on verdict: an OK does not skip integration. Annotate each change inline with
"Review: <reviewer> — <reasoning>". Never rewrite, re-order, or edit the reviewer's own words;
disagreement goes in YOUR report. Escalate ASKs rather than guessing.`,
}

// ---------------------------------------------------------------------------
// Brief fragments
// ---------------------------------------------------------------------------

// Sidecar paths are ASSIGNED, never chosen. Two reviewers on the same baton pick
// the same obvious filename — measured: on wave 1 both wrote
// `<baton>.plan-review.md`, the second overwrote the first, and a BLOCKED review
// was destroyed with nothing reporting it. The readiness gate noticed a sidecar
// was missing and read it as a routing defect rather than an overwrite, which is
// the more dangerous failure: a lost review looks like a review that never ran.
const slug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

// A ROLE NAME IS PART OF THE CONTRACT, not a label. The planner's sidecar role was
// `plan`, which rendered `<baton>.plan.md` — a file named exactly like the thing the
// planner's OTHER output is. Handed two paths and asked for `planPath`, a planner
// returned the one whose name said "plan", and the reviewer and integrator were both
// aimed at it. `planning-report` is deliberate: no role here may render a filename
// that reads like the artifact the agent also produces.
const sidecarFor = (trailDir, batonId, role) => `${trailDir}/${slug(batonId)}.${slug(role)}.md`

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
// `append-integrator-dispositions` refuses any target without `subagent-share` as a whole
// path segment (coordinator_core/ops/append_integrator_dispositions.py) — a deliberate
// scope check, so the op can only ever write into agent sidecar space. A wave that
// assigned trail paths therefore produced reviews the integrator could read but never
// disposition, and every plan landed with its disposition block missing.
//
// The collision this replaces the assignment with is not reintroduced: assigned names
// existed because two reviewers in ONE shared directory both picked `<baton>.plan-review.md`
// and the second destroyed the first. Provisioned sidecars are per-agent-session, so two
// reviewers on one plan cannot land on the same file no matter what they name it.
//
// The trail still gets an entry — a POINTER at the assigned path, naming where the real
// sidecar went. The readiness gate reads the trail; it must not go blind to a review just
// because the review now lives somewhere else.
// PRECONDITION for repair mode (see below): the pointer is a STRUCTURED RECORD, not a bare
// path. A bare path loses `verdict`/`premiseFailure` — the only durable trace of a PIVOT — so a
// repair pass reading an old-shape pointer would resolve REJECTED-without-premise to BLOCKED and
// integrate findings a live wave correctly suspended. `verdict` and `premiseFailure` in the
// pointer are the SAME claim the agent also returns in its own JSON schema output below, stated
// twice, never two sources of truth.
// A COORDINATOR CLI IS NAMED WITH ITS RESOLUTION, NEVER AS A BAREWORD. This file names
// `append-integrator-dispositions`, `sizing-assemble` and `coordinator-doc-new` in briefs, and
// until now named them bare, gesturing at "the bin ladder" once without ever giving its shape.
// `snippets/resolve-coordinator-bin.md` is explicit that no coordinator CLI is reliably on PATH,
// so a bareword exits 127 unrecoverably — and an agent that gets 127 concludes the TOOL IS ABSENT
// rather than that the path was unresolved, which is the more expensive of the two wrong readings.
//
// Measured: two consecutive waves came back reporting `append-integrator-dispositions` "absent
// from the wave's tool surface", so no reviewer disposition was written to any provisioned sidecar
// and the review trail was incomplete by TOOLING on both. The integrator brief had told it not to
// hand-author around a refusal — correctly — while never telling it how to invoke the op at all.
//
// Both host shapes are given because this fleet is multi-OS P0 and a POSIX-only literal would
// simply move the breakage to Windows. The agent picks the rung its host takes, which is what the
// canonical snippet already instructs; what it could not do before was pick from nothing.
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

const REVIEW_SIDECAR_RULE = (pointerPath) => `
Write your findings sidecar to YOUR OWN PROVISIONED SIDECAR under
\`<machinery_root>/subagent-share/<your session id>/\`, and return its absolute path verbatim as
\`sidecarPath\`. Do NOT write your findings into the wave trail: \`append-integrator-dispositions\`
refuses any path without \`subagent-share\` as a path segment, and a findings sidecar it cannot
open is a review whose dispositions are never recorded.

Then write a POINTER file at EXACTLY this path, containing a SHORT STRUCTURED RECORD as one JSON
object and nothing else — not a bare path:

    ${pointerPath}

\`\`\`json
{"sidecarPath": "<the absolute sidecar path above>", "verdict": "<your verdict, exactly as you return it below>", "premiseFailure": "<your premiseFailure verbatim, or null if you did not state one>"}
\`\`\`

The pointer is how the readiness gate finds you, and it is also how a REPAIR run finds you later
with no reviewer re-dispatched: a repair pass reads this record and feeds it through the same
\`resolveVerdict()\` a live wave uses, so a sidecar saying REJECTED resolves by the same evidence
rule whether the wave is live or repaired. A findings sidecar with no pointer is a review the gate
cannot see, and a pointer with no sidecar is worse — it reads as a review that ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the EM's readiness gate will never see.`

// EVERY BRIEF IS ANCHORED, because nothing else anchors it. A dispatched agent inherits the
// driver's shell cwd, not the repo the wave is about — the two coincide only by the driver's
// habit, and this file has no filesystem primitive with which to notice they have diverged.
// `trailDir` and `gateReportPath` are absolute by the skill's own instruction, so a sidecar
// survives the divergence; a baton record and a hand-authored plan path do not. The measured
// shape: on a cloud container the session's directory was the PARENT of five sibling clones, so
// `docs/plans/<date>-<slug>.md` resolved to a directory in no repo at all, and the wave would
// have reported every plan written. Loud beats clever here — the rule is stated in the brief
// rather than inferred, because an agent that guesses right eight times and wrong once has
// produced the failure this whole file is written to prevent.
const REPO_ROOT =
  typeof parsedArgs.repoRoot === 'string' && parsedArgs.repoRoot.trim()
    ? parsedArgs.repoRoot.trim()
    : null

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

  3. \`external_gate[].requires:\` ON EVERY UNCLEARED GATE. A blocker owned by another repo is a
     declared gate, never a sentence in the body. \`requires: landed-work\` means wait for them —
     the row is withheld and the plan still certifies. \`requires: commit-in-owner-repo\` means
     write into their tree — which needs per-session PM assent a hands-off run cannot obtain, so
     it refuses the whole plan. The two read identically in prose and route oppositely, which is
     why the field exists. A row whose declared paths leave this repo and carries no gate at all
     is refused.

  4. \`prime_exit_criterion:\` AT EVERY SIZE, S and XS included — \`statement\` plus
     \`derived_from\`. It answers the one question a driver cannot answer against a task list:
     how do I know this is finished. A \`falsifier\` sub-object stays proportional to size and is
     not required here.

Declare what is true. A \`census: []\` on a plan that counted something, or a gate omitted because
naming it looked like extra work, is a false claim in a machine-checked field — worse than the
absence, because it certifies.`

// ---------------------------------------------------------------------------
// Phase 1 — Size
// ---------------------------------------------------------------------------

function sizingScout(baton, waveIndex, trailDir) {
  return agent(
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
  )
}

// ---------------------------------------------------------------------------
// Phase 3 — Plan
// ---------------------------------------------------------------------------

function planner(baton, decision, waveIndex, trailDir, escalation) {
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

  // The Resolve-escalations pass: SAME actor, SAME prompt, SAME revising branch above — the
  // only addition is this brief, appended below the ordinary revising instruction. It fires
  // only when integration on this baton escalated at least one ASK. The caller passes a baton
  // whose `planPath` is this wave's authored plan -- the field on the real baton is set only from
  // a prior wave's trail, so it is null exactly when this pass matters most.
  const resolveBrief = escalation
    ? `
RESOLVE PASS — not authoring, and not an ordinary revision. Integration on this plan escalated
${escalation.escalationCount} ASK(s) too consequential to apply silently. Full findings:
${escalation.reportPath}.

The CATALOGUE below is the closed set you may settle. It is not the integrator's escalation list
verbatim: every option on it was written by a reviewer who actually reviewed this baton, and an
option the integrator composed itself has already been dropped — an integrator that composes an
option and then has it chosen has laundered its own judgment through you. Each option carries the
id you pick by and the reviewer who wrote it.

${escalation.menu}
${escalation.notConvergeable.length ? `
NOT settleable here, and you leave them alone — they reach the readiness gate escalated exactly as
they would have without this pass:
${escalation.notConvergeable.map((n) => `  ${n.id}: ${n.summary} — ${n.reason}`).join('\n')}
` : ''}
Pick at most one option id per catalogue entry, against the BATON'S OWN REMIT: which option leaves
the plan doing the job the baton asks for, at the size it was routed at. Not which is safest, not
which is largest, not which the integrator leaned toward — its recommendation is one input and
carries no weight of its own. Read the reviewer sidecars the options came from first: the texts
above are quotations, and a quotation read without its finding is how the wrong one gets picked
confidently.

**You may pick nothing else.** An id that is not in the catalogue above is refused before anything
reads it, and the refusal is printed in the trail beside this plan. If the right answer is a third
thing nobody wrote down, DO NOT EDIT THE PLAN FOR IT — leave that escalation unresolved and name
the third thing in your summary. The gate reads it, and a plan that pulls carrying a named third
option is a better pull than a plan whose body was edited toward an option no reviewer wrote and
whose record says REFUSED.

Leave an escalation unresolved whenever picking would take a fact you do not have. That costs the
wave nothing it was not already paying: the escalation reaches the readiness gate as it would have.

Edit the plan body to reflect the picks you make, then return \`choicesMade\`: one entry per
escalation you settled, \`{ escalationId, chosen }\`, both ids drawn from the catalogue above.
\`choicesMade\` is REQUIRED — a resolve pass with nothing to record has not resolved anything. What
you did NOT choose is computed from the catalogue rather than read from your return, so a short
reason is the only thing you can shorten: say in your summary why each option you took beats the
ones you left.
`
    : ''

  return agent(
    `Write the implementation plan for ONE roadmap baton, in plan-blitz wave ${waveIndex}.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}
Finalised size: ${decision.tshirt}, route: ${decision.route}
EM's sizing rationale: ${decision.rationale}

${revising}
${resolveBrief}
${baton.planPath ? `You are revising, so the file already exists and the generator has no part in this: the
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
     citation that looks connected.` : `The coordinator plan tooling is NOT installed on this machine, so hand-author the plan file at
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
      derived_from: "<the baton, ruling or AC the statement is read off>"
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
dispatchable however good its prose is.

\`depends_on\` is only for the two gates a wave-builder CANNOT derive:
\`output-consumption-runtime\` (the predecessor's artifact must exist at runtime when this row
runs) and \`epistemic-premise\` (the predecessor decides whether this row should exist at all).
Ordering that follows from two rows touching the same file is computed from \`writes:\` and must
NOT be restated here. Omit the key when neither gate applies — a bare string in this array is a
spine that fails to read, which refuses the whole plan rather than the row.

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
plan does NOT do.`}

The size above is FINAL for this wave. It was already interrogated by the EM. Do not re-litigate
it — if the substrate contradicts it once you are in the body, say so in your returned summary
and keep planning to the size you were given; re-sizing mid-plan is how a wave loses its
comparability.

TWO FILES, AND THEY ARE NOT THE SAME FILE. You produce the PLAN DOCUMENT under \`docs/plans/\`,
and separately a run sidecar in the wave trail. \`planPath\` is the plan document — ALWAYS. It is
never your sidecar, never anything under the trail directory, and never anything under
\`subagent-share/\`. Return the path the generator actually wrote the plan to; if you did not
write a plan, return \`status: blocked\` with the reason rather than a path to something else.

Getting this wrong does not fail loudly on your side: the reviewer and the integrator are both
aimed at whatever you return here, so a sidecar path sends two more agents at a file that is not
the plan, and the baton spends a wave slot producing nothing.
${MISE_PREP_RULE}
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'planning-report'))}`,
    withRole('coordinator:plan-author', {
      label: escalation ? `resolve:${baton.id}` : `plan:${baton.id}`,
      phase: escalation ? 'Resolve escalations' : 'Plan',
      // Planning is opus on EVERY route, and the wave does not offer a knob to
      // lower it. Sonnet's place in this pipeline is research (the sizing scouts)
      // and execution (the XS dispatch lane) — both bounded work with the judgment
      // already made. Authoring is where the judgment IS: a plan is what the
      // executor is held to, and on `spec-dispatch` it is stamped
      // `execution_authorized_*` and read by nobody in between. The unconditional
      // reviewer is not a backstop for a cheap planner — an opus review that
      // BLOCKS a sonnet plan has already outspent authoring it at opus, and costs
      // the wave a replan on top. The Resolve pass inherits the same reasoning: it
      // is choosing among a reviewer's own alternatives, not a cheaper act than authoring.
      model: 'opus',
      // Medium, not high: the planner is authoring against a size and a route the
      // blitz-em already interrogated, over substrate a scout already inventoried.
      // The judgment it owes is the plan's shape, not a re-derivation of the wave's
      // decisions — and an unpinned planner inherits whatever the invoking session
      // was set to, which makes the wave's authoring depth an accident of who fired it.
      effort: 'medium',
      schema: escalation ? RESOLVE_SCHEMA : PLAN_SCHEMA,
    }),
  )
}

// ---------------------------------------------------------------------------
// Premise check — between a written plan and the reviewers who read it
// ---------------------------------------------------------------------------
//
// WHAT THIS BUYS. Nothing between authoring and review resolves a plan's claims against the
// tree, so the first reader to notice a path that does not exist, a symbol that means something
// else, a branch nobody pushed, or a falsifier that cannot go red is an OPUS reviewer — and the
// discovery costs that reviewer, an integrator, and a wave slot. Peer-reported, and NOT a DoE
// measurement: across an eight-wave sweep in one sibling repo and five waves in another, the
// plans that reached execution-ready were a minority, and nearly every pull was this one shape.
// The same series shows the ready rate having no relationship to plumbing state in either
// direction across the whole eight waves, which is why this is a missing stage rather than an
// unreliable one.
//
// IT REPORTS. It does not refuse, does not gate, and does not edit. The semantic class is only
// mechanically decidable where the repo carries a surface that forbids the assumption, so on the
// occasions it is guessing a hard refusal would convert a recoverable authoring slip into a
// pulled plan — the exact cost this exists to remove. Its output goes to the reviewers (who then
// spend their pass on judgment rather than on resolving citations) and to the integrator (which
// is what already edits the plan body, so a premise finding is repaired in-wave through a phase
// that exists rather than a second pass that does not).
//
// IT IS NOT A CORRECTNESS CLAIM, and the schema above has nowhere to make one.
//
// ORDERING. This runs where it does because of DATA, not position: it needs a written plan, and
// the reviewers read what it returns. Nothing here reads a phase index or assumes what runs on
// either side of it.

function premiseChecker(baton, planResult, trailDir) {
  return agent(
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
     \`coordinator/bin/instrument-can-report-red.py <instrument> --json\` and carry its verdict
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
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, 'premise-check'))}`,
    withRole('coordinator:premise-checker', {
      label: `premise:${baton.id}`,
      phase: 'Premise check',
      // Sonnet, pinned rather than inherited, and the pass's whole economic premise: these are
      // questions with mechanical answers, priced against a discovery cost today of an opus
      // reviewer plus an integrator plus a wave slot. An opus premise checker would cost more
      // than the reader it is meant to spare.
      model: 'sonnet',
      // Low. The judgment is "did I open the thing", not "is this a good plan" — and raising it
      // invites exactly the plan-level opinion the schema refuses to carry.
      effort: 'low',
      schema: PREMISE_SCHEMA,
    }),
  )
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

// Rendered for the reviewer and the integrator from the structured rows, so both read the same
// summary and neither has to re-derive it. Unresolved and contradicted rows lead: a table whose
// interesting rows are buried among resolved ones is read as clean.
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

// THE SEAM. The checker emits rows and no verdict — that is a ruling, and the schema above has
// nowhere to record one. Delivery is a separate problem and it is solved HERE, in code, by
// translating those rows onto REVIEW_SCHEMA: the premise report then reaches the review-integrator
// through the channel a reviewer already uses, and the integrator — the only actor that edits the
// plan body, already contracted to apply every finding unconditionally — repairs a false citation
// in-wave. Nothing about that needs a parallel applier, and a checker that reported to a channel
// nobody applies from was reporting to nobody.
//
// The translation is what routes; the checker never does. That is the whole point of putting it
// here. A verdict this function computes is a lookup over row verdicts that a reader can audit in
// one screen, priced at nothing; a verdict the checker computes is a Sonnet-low authority, which
// is what the ruling priced out.
//
// BLOCKED OR OK, NEVER PIVOT. A premise miss names its own repair — the path that is absent, the
// symbol that moved, the ref nobody pushed, the falsifier that cannot go red — so it is BLOCKED,
// however many rows there are. The one shape that does not name a repair is a class-5 row the tree
// contradicts or leaves unsettled: no fix is writable from the finding alone, which is the
// separating test for PIVOT. This function NAMES those rows in `premiseFailure` and takes no
// route on them, because the separating test is "write the fix" and nothing here has written one
// — `a-blocked-review-is-not-a-pivot.md`: when you are between them, return BLOCKED. The
// reviewers read the same rows and hold the pivot; a wave that let a Sonnet-low pass discard a
// plan through a table lookup would have rebuilt the refusing checker the ruling refused.
const PREMISE_REVIEWER = 'premise-check'
const PREMISE_FINDING_VERDICTS = ['UNRESOLVED', 'CONTRADICTED']

// XS work the Dispatch phase FINISHED, shaped into the verdict rows the LANDING can close.
//
// `roadmap.blitz_land` iterates `ready` alone, and its third lane branches on
// `route === 'dispatch'` to call `close_dispatched` — the terminal stamp an XS is owed, having
// no plan to approve. Reporting a finished XS only under the wave result's top-level
// `dispatched` key put it somewhere the landing never reads, so that lane was unreachable and
// no XS baton was ever closed. An unclosed baton is not terminal, so it stays a candidate and
// comes back in the NEXT wave's gate read to be re-sized and re-planned from scratch. That is
// the recycling defect: a wave whose XS work all succeeded still lands zero approved, trips the
// wave-lands-zero-approved stop condition, and hands the next wave its own batons back.
//
// `completed` is the whole predicate. An INCOMPLETE executor return is NOT closed: the gate
// brief already asks the em to report it as a sizing defect, and stamping a baton whose work
// did not finish is the same silent-success shape `close_dispatched` exists to prevent,
// reached from the other side.
//
// A baton the em ALREADY returned a verdict for is skipped. Its judgment is the one that
// stands, and a synthetic row beside it would hand the landing the same baton twice.
function closableDispatched(dispatched, verdicts, waveIndex) {
  const gated = new Set((verdicts || []).map((v) => v.batonId))
  return (dispatched || [])
    .filter((d) => d && d.completed && !gated.has(d.batonId))
    .map((d) => ({
      batonId: d.batonId,
      verdict: 'ready',
      route: 'dispatch',
      // An XS carries no plan. The landing resolves `planPath` only off the lanes that have
      // one, so this is null by contract rather than by omission.
      planPath: null,
      // No reviewer runs on an XS. Declared-empty, never absent: `pivoting_reviewers` reads
      // this at the landing, and "nobody reviewed" must not arrive as the same value as
      // "the review set was not carried".
      reviewVerdicts: [],
      reason: `XS dispatched in wave ${waveIndex} and reported completed: ${d.summary}`,
    }))
}

function premiseAsReview(baton, premise) {
  if (!premise) return null
  const rows = premise.rows || []
  const findings = rows.filter((r) => PREMISE_FINDING_VERDICTS.includes(r.verdict))
  // Class 5, not resolved: the rows where no fix is writable from the finding alone, which is
  // the second half of the PIVOT conjunction. Named, never routed.
  const unwritable = rows.filter(
    (r) => Number(r.questionClass) === 5 && r.verdict !== 'RESOLVES',
  )
  return {
    batonId: baton.id,
    reviewer: PREMISE_REVIEWER,
    verdict: findings.length ? 'BLOCKED' : 'OK',
    sidecarPath: premise.sidecarPath,
    findingCount: findings.length,
    // Review: code-reviewer (premise-check.md Finding 3, MAJOR, routed here — same artifact) —
    // `rows: []` (zero citations examined) and a fully-checked, all-RESOLVES `rows` both produce
    // bare `verdict: 'OK'` with no way to tell them apart downstream. `premiseLines`/`classCoverage`
    // already render an empty class correctly ("c{n}:none — UNATTEMPTED, never clean"), but that
    // distinction was lost the moment it collapsed to this machine-legible verdict. Carried as an
    // explicit count rather than folded into `premiseFailure` — that field is a class-5 PIVOT
    // candidate signal, and reusing it for "nothing was checked" would misread as one.
    citationsChecked: rows.length,
    premiseFailure: unwritable.length
      ? `class-5 rows with no fix writable from the finding alone — PIVOT candidates for a `
        + `reviewer to run the separating test against, not a route this pass took: `
        + unwritable.map((r) => `${r.verdict} ${r.citation}`).join('; ')
      : undefined,
  }
}

// ---------------------------------------------------------------------------
// Phase 4 — Review
// ---------------------------------------------------------------------------

function reviewerAgent(baton, decision, planResult, reviewer, trailDir, premise) {
  return agent(
    `${ROLE_CONTRACTS.reviewer}

Review the plan at ${planResult.planPath} for baton ${baton.id} ("${baton.title}").

Finalised size: ${decision.tshirt}, route: ${decision.route}.
Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}

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
    "this plan must not execute until these are fixed" — however severe, however many. An
    integrator applies your findings and the fixed plan can be approved in this same wave. Almost
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

Do not soften a PIVOT into a BLOCKED to be helpful: a premise failure filed as a finding gets
"fixed" by an integrator who cannot fix it. Do not inflate a BLOCKED into a PIVOT to be
emphatic either: that discards a repairable plan and costs the baton a whole wave. If you are
between them, return BLOCKED and say in your sidecar why you considered a pivot — the readiness
gate reads that, and a plan wrongly kept is recoverable in a way a plan wrongly discarded is not.

If you find yourself reaching for REJECTED out of the fleet-wide reviewer enum, that word is
accepted here but is not this pipeline's vocabulary: it resolves to PIVOT only when you have
stated a \`premiseFailure\`, and to BLOCKED otherwise. Say what you mean with PIVOT or BLOCKED
instead of leaving the resolution to a field you might not fill.

You are one of possibly several reviewers on this plan, each writing to their own sidecar. Do not
assume your verdict is the wave's verdict, and do not defer to an imagined co-reviewer: a BLOCKED
alongside someone else's PIVOT is not redundant — your findings become inputs to the replan.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, `review-${reviewer}-pointer`))}`,
    withRole(reviewer, {
      label: `review:${baton.id}:${reviewer}`,
      phase: 'Review',
      model: 'opus',
      schema: REVIEW_SCHEMA,
    }),
  )
}

// ---------------------------------------------------------------------------
// Phase 5 — Integrate
// ---------------------------------------------------------------------------

function integrator(baton, planResult, reviews, trailDir, premise) {
  // The verdict shown is the RESOLVED one. A sidecar whose own text says REJECTED is
  // labelled with what that resolved to, so the file and this list cannot look like
  // two different reviews.
  // Review: code-reviewer (premise-check.md Finding 3, routed via resolve-escalations.md) — same
  // axis as the trail's `premiseCheckLine`: an `OK` this list shows for `premise-check` must not
  // read like a clean, fully-checked pass when `citationsChecked` is 0. Undefined on every real
  // reviewer entry, so this only ever fires for the premise-check row.
  const sidecars = reviews
    .map((r) => `  - ${r.reviewer}: ${r.verdict}${r.citationsChecked === 0 ? ' (0 citations examined — UNATTEMPTED, not a clean pass)' : ''}${r.aliased ? ` (sidecar says ${r.raw}; ${r.aliased})` : ''} -> ${r.sidecarPath}`)
    .join('\n')

  return agent(
    `${ROLE_CONTRACTS['review-integrator']}

Integrate the review findings for baton ${baton.id} into ${planResult.planPath}.

Reviewer sidecars on disk:
${sidecars}

Premise check on this plan's own citations, run before the reviewers:
${premiseLines(premise)}

Treat an UNRESOLVED or CONTRADICTED row as a finding like any other — it is a false statement the
plan makes about this tree, and repairing it is ordinary integration, not a judgment call. An
UNCHECKABLE row is NOT a finding and must not be "fixed" — nothing established it either way, so
carry it into your report and let the gate read it.

The \`premise-check\` entry in the sidecar list above is those same rows, routed: the checker
itself returns no verdict on the plan, and the wave translates its rows onto the review channel so
they reach you rather than a reader with no edit to make. It routes BLOCKED or OK and never PIVOT.
Where it states a \`premiseFailure\`, that is a class-5 row nothing in the tree settles — a PIVOT
candidate a REVIEWER may act on, never a route the checker took and never one you take.

Those paths are the reviewers' OWN PROVISIONED sidecars under \`subagent-share/\`, which is what
\`append-integrator-dispositions\` requires — so the disposition write your contract mandates will
go through on every one of them. If the op still refuses a path, report the refusal verbatim and
escalate it; do NOT hand-author a disposition block to route around it. A hand-written block
satisfies the reader and leaves the tool's refusal undiagnosed, which is how this stayed broken
for two waves. Your own run-report sidecar is NOT a disposition target — never pass it.

Apply every finding — filtering happened upstream. You are unconditional on verdict: an OK does
not skip integration. A reviewer handed an author's prose can confirm it without opening the code
that would falsify it, and gating integration on WARN/BLOCKED gives the cheapest-to-produce
verdict the least scrutiny. A clean review costs you one empty triage table.

If ANY sidecar above carries verdict: PIVOT, the plan is going to a replan and integration of
the WHOLE plan is suspended — including the findings from co-reviewers who returned OK, WARN or
BLOCKED. Apply nothing to the plan file: repairing a plan that is about to be discarded produces
a document that looks maintained and is not, and it makes the replan harder by hiding what the
plan actually said when it was reviewed. Treat PIVOT exactly as your own contract's REJECTED
handling, with one addition that matters more than the rest:

  Every finding from EVERY sidecar still appears in your triage table, disposition
  \`Suspended (PIVOT)\`, attributed to the reviewer who wrote it. A BLOCKED review sitting beside a
  PIVOT is not made irrelevant by it — those findings are the replan's inputs, and a triage table
  that lists only the pivoting reviewer's material silently destroys the other review. Name the
  pivoting reviewer and their premise failure at the top; list everyone else's findings below it.

Do not route around a PIVOT, and do not treat the EM's absence from this wave as license to
override it: no EM is watching this phase by design, and an override needs explicit PM agreement
recorded verbatim beforehand, which cannot happen here.

Escalate ASKs rather than guessing. Your escalated list is the highest-signal item the EM reads at
the readiness gate — an empty ASK list on a plan carrying P0/P1 findings is itself a finding.

Return each escalation twice: in \`escalated\` as prose, as you always have, and in
\`escalations\` with its alternatives ATTRIBUTED. Per option: \`source\` is the reviewer who
wrote it and \`text\` is their words verbatim; an option you composed yourself carries YOUR name.
Your own contract already requires two-or-more concrete options and the pick you would make if
forced — this is where they go, and \`whyItExceedsDiscretion\` is that contract's fourth
anti-dodge field, stated per escalation.

Attribution is load-bearing, not bookkeeping. The phase after you may pick ONLY a
reviewer-sourced option; an option attributed to you, or to nobody, is dropped from what it may
consider, and an escalation left with fewer than two reviewer-sourced options is not settled in
this wave at all. So do not launder your own option into a reviewer's name to give the choice
more to work with — that converts your judgment into theirs, silently, which is the thing your
ASK routing exists to prevent.
${REPO_ROOT_RULE}
${CLI_RESOLUTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'review-integration'))}`,
    withRole('coordinator:review-integrator', {
      label: `integrate:${baton.id}`,
      phase: 'Integrate',
      // Integration is always low-effort sonnet. It is a SAFETY NET, not a seat of
      // judgment: its job is that no finding is silently lost, and escalating is the
      // correct output whenever applying would take judgment — not a failure to
      // exercise it. A long escalated list is the net working. Raising its effort
      // would invite it to adjudicate findings instead of routing them, so this is
      // pinned rather than inherited from the invoking session.
      model: 'sonnet',
      effort: 'low',
      schema: INTEGRATION_SCHEMA,
    }),
  )
}

// ---------------------------------------------------------------------------
// Resolve escalations — the one place a choice can be made while an edit is still possible
// ---------------------------------------------------------------------------
//
// The PHASE is `Resolve escalations`; the mechanism inside it is the convergence catalogue, and
// the functions keep that name because the catalogue is what they are.
//
// WHAT THIS BUYS. Before this phase, the wave's only actor with judgment over an escalation was
// the readiness gate, and the gate runs after the only actor that edits the plan body. Both
// points existed, in that order, with no path back — so a plan whose defect needed a CHOICE was
// structurally unable to converge in-wave however good it was, and the pull was not evidence of
// anything about the plan. Peer-reported and NOT a DoE measurement: one sibling repo relayed 2 of
// 16 plans reaching ready across five waves, with most pulls citing unapplied or escalated
// findings — a ratio they have since downgraded to directional. The ORDERING is the checkable
// claim and it was checked here, against this file.
//
// NO NEW ACTOR. The pass is the Plan phase's own planner, in its revising branch, with the
// catalogue appended to the brief it already carries — one dispatch, at a price the wave already
// pays, by the one agent contracted to edit a plan body. A separate chooser would have bought a
// clean split between deciding and editing and cost a second Opus seat plus an applier to relay
// its picks; the split is not worth two dispatches per escalated plan.
//
// WHAT IT DELIBERATELY IS NOT. It is not a second review, not a re-plan, and not a widening of
// what the integrator may apply on its own. The integrator's refusal to settle an ASK is correct
// and is untouched: silent application of a judgment call is worse than a pull.
//
// TWO BOUNDS, EACH ENFORCED IN CODE RATHER THAN IN A BRIEF:
//   1. Only a reviewer-enumerated alternative is choosable. `convergenceCatalogue` drops every
//      option whose source is not a reviewer that reviewed this baton, and `reconcilePicks`
//      refuses an id the catalogue does not hold.
//   2. The rejected set is COMPUTED from the catalogue rather than reported by the pass, so "what
//      was not chosen" cannot be under-reported by the actor that chose.
//
// WHAT REUSING THE PLANNER COSTS, stated rather than glossed: the actor that picks is the actor
// that edits, so a refused pick is refused AFTER the body was edited. That is why a refusal is
// rendered in the trail as a plan-body warning and not as a silent drop — the brief tells the
// pass not to edit for an option it cannot name a catalogue id for, and the trail says plainly
// when it did anyway.
//
// ORDERING. Like the premise check, this runs where it does because of DATA: it needs the
// integration report, and its picks are made by the pass that edits. Nothing here reads a phase
// index.

// A single option is a recommendation, not a choice. Two is the floor at which picking is
// selection rather than assent, and it is the same floor the integrator's own contract already
// holds an ASK to.
const MIN_ENUMERATED_OPTIONS = 2

// Returns { escalations, notConvergeable }. `escalations` is the CLOSED set of things that may be
// decided in this wave; everything else keeps the behaviour it had before this phase existed.
function convergenceCatalogue(integration, reviews) {
  // Review: code-reviewer (resolve-escalations.md Finding 1, BLOCKER) — the wave folds
  // `premiseAsReview`'s pseudo-reviewer into `kept` unconditionally (`[premiseCheckResult,
  // ...reviews]`), so `reviewerNames` built straight off `reviews` always contained
  // `'premise-check'`, and the attribution filter below treated it as a real reviewer that had
  // enumerated an alternative. `PREMISE_SCHEMA` has no options/alternatives field at all — the
  // checker's own contract is "report, do not refuse, do not ratify" — so an option attributed to
  // `premise-check` is, by construction, never something a reviewer wrote. Excluding it here is
  // where "only a reviewer-enumerated alternative may be picked" is actually enforced; leaving it
  // in let an integrator launder its own composed option through a name guaranteed present on
  // every baton. Confirmed with a `node` repro before this fix: the two invented options in
  // Finding 1's concrete failing input both survived to a convergeable escalation.
  const reviewerNames = new Set(
    (reviews || []).map((r) => String(r.reviewer)).filter((name) => name !== PREMISE_REVIEWER),
  )
  const escalations = []
  const notConvergeable = []

  const raw = (integration && integration.escalations) || []
  raw.forEach((esc, index) => {
    const id = `E${index + 1}`
    const summary = String((esc && esc.summary) || '(no summary)')
    const enumerated = ((esc && esc.options) || [])
      .filter((o) => o && reviewerNames.has(String(o.source)))
      .map((o, j) => ({ id: `${id}.o${j + 1}`, source: String(o.source), text: String(o.text) }))

    if (enumerated.length < MIN_ENUMERATED_OPTIONS) {
      notConvergeable.push({
        id,
        summary,
        reason: enumerated.length
          ? 'one reviewer-enumerated option only — a single option is a recommendation, not a choice'
          : 'no reviewer enumerated an alternative; any options on it are the integrator\'s own',
      })
      return
    }
    escalations.push({
      id,
      summary,
      options: enumerated,
      recommendation: String((esc && esc.recommendation) || ''),
      whyItExceedsDiscretion: String((esc && esc.whyItExceedsDiscretion) || ''),
    })
  })

  return { escalations, notConvergeable }
}

// Renders the catalogue for the resolve brief. One function so the ids the pass picks by and the
// ids `reconcilePicks` refuses against are read off the same object.
function convergenceMenu(catalogue) {
  return catalogue.escalations
    .map((e) => {
      const options = e.options
        .map((o) => `      ${o.id} — enumerated by ${o.source}: ${o.text}`)
        .join('\n')
      return `  ${e.id}: ${e.summary}
${options}
      integrator's recommendation if forced: ${e.recommendation || '(none stated)'}
      why it exceeded the integrator's discretion: ${e.whyItExceedsDiscretion || '(not stated)'}`
    })
    .join('\n')
}

// Returns { picks, refused, deferred } over the resolve pass's `choicesMade`. Every refusal is
// NAMED — a pick dropped quietly is indistinguishable from a pick nobody made, and the difference
// is exactly what this phase is being measured on. The pass edits the plan body itself, so a
// refusal here is also the only signal that the body may carry an edit no catalogued option
// authorised; `convergenceLines` prints it as that.
function reconcilePicks(catalogue, choice) {
  const byId = new Map(catalogue.escalations.map((e) => [e.id, e]))
  const picks = []
  const refused = []
  const settled = new Set()

  for (const pick of (choice && choice.choicesMade) || []) {
    const wantedId = String((pick && pick.escalationId) || '')
    const escalation = byId.get(wantedId)
    if (!escalation) {
      refused.push(`${wantedId || '(unnamed)'}: no such escalation in this plan's catalogue`)
      continue
    }
    if (settled.has(escalation.id)) {
      refused.push(`${escalation.id}: a second pick on an escalation already settled`)
      continue
    }
    const chosen = escalation.options.find((o) => o.id === String(pick.chosen))
    if (!chosen) {
      // The bound that matters. An id off the catalogue is the shape an invented option arrives
      // in, and it is refused here rather than caught by a reader downstream. RESOLVE_SCHEMA
      // cannot refuse it — `chosen` is a string and a plan body is free text — so this is where
      // "only a reviewer-enumerated alternative may be picked" is actually held.
      refused.push(
        `${escalation.id}/${String(pick.chosen)}: not an option any reviewer enumerated`,
      )
      continue
    }
    settled.add(escalation.id)
    picks.push({
      escalationId: escalation.id,
      summary: escalation.summary,
      chosen,
      // COMPUTED, never taken from the pass. "What was not chosen" reported by the actor that
      // chose is the one field it has an incentive to shorten, and the catalogue already knows.
      rejected: escalation.options.filter((o) => o.id !== chosen.id),
    })
  }

  const deferred = catalogue.escalations
    .filter((e) => !settled.has(e.id))
    .map((e) => ({
      escalationId: e.id,
      summary: e.summary,
      reason: 'not settled by the resolve pass; carried to the gate escalated',
    }))

  return { picks, refused, deferred }
}

// Runs the whole phase for one plan, or explains in one string why it did not. Always returns a
// record: a phase that skipped silently is indistinguishable from one that found nothing, and the
// difference between those two is this baton's entire measurement. `plan` on the returned record
// is what the rest of the wave reads — unchanged when the phase did not run.
async function resolveEscalations(baton, decision, waveIndex, plan, reviews, integration, trailDir) {
  const empty = {
    escalationCount: 0,
    convergeable: 0,
    picks: [],
    refused: [],
    deferred: [],
    notConvergeable: [],
    plan,
  }

  if (reviews.some((r) => r.pivot)) {
    return { ...empty, skipped: 'PIVOT — the plan routes to a replan; resolving it would produce a document that looks maintained and is not' }
  }
  // Review: code-reviewer (resolve-escalations.md Finding 4, minor) — unreachable from this
  // function's single current call site: the pipeline's earlier stage already returns before
  // `resolveEscalations` is invoked whenever `!plan || plan.status === 'blocked'`. Kept, not
  // deleted — it is the precondition a second call site (repair mode, per this file's own
  // "Resolve pass inherits the same reasoning" note) would need, and removing it would silently
  // drop that guard for whoever adds one. Documented here so it does not read as currently live.
  if (plan && plan.status === 'blocked') {
    return { ...empty, skipped: 'the plan is blocked; there is no body to resolve an escalation into' }
  }
  // Review: code-reviewer (resolve-escalations.md Finding 5, minor) — "no integration report" was
  // also the message when a report existed but `integration.rejected` was true, which sends a
  // trail reader looking for a missing artifact when `reportPath` names one on disk. Split so each
  // branch states the fact it actually observed.
  if (!integration) {
    return { ...empty, skipped: 'no integration report to resolve over' }
  }
  if (integration.rejected) {
    return { ...empty, skipped: `integration report at ${integration.reportPath || '(no reportPath)'} was rejected; nothing to resolve over` }
  }

  const catalogue = convergenceCatalogue(integration, reviews)
  const escalationCount = (integration.escalations || []).length
  const base = { ...empty, escalationCount, convergeable: catalogue.escalations.length, notConvergeable: catalogue.notConvergeable }

  if (!catalogue.escalations.length) {
    // Three different nothings, and the gate has to be able to tell them apart. An integrator
    // that escalated in prose but returned no structured `escalations` is not a quiet wave — it
    // is an escalation this phase could not see, which is a defect in the integration, not in
    // the plan.
    const prose = ((integration.escalated || []).length)
    return { ...base, skipped: escalationCount
      ? 'nothing on this plan is choice-shaped — every escalation reaches the gate as it did before'
      : prose
        ? `${prose} escalation(s) in prose and none structured — the integration returned no `
          + '`escalations` array, so nothing here was choosable; read the integration report'
        : 'the integration escalated nothing' }
  }

  // `baton.planPath` is set only from a PRIOR wave's trail and is never written back during this
  // wave, so for the modal baton — one planned for the first time here — it is null and
  // `planner`'s revising branch would render "No plan exists yet. Author one." underneath a brief
  // telling it to edit the plan body. Aim it at the plan this wave actually authored instead;
  // that is what makes the revise-in-place branch and its do-not-scaffold guard fire.
  const resolution = await planner(
    { ...baton, planPath: plan.planPath },
    decision,
    waveIndex,
    trailDir,
    {
      escalationCount,
      reportPath: integration.reportPath,
      menu: convergenceMenu(catalogue),
      notConvergeable: catalogue.notConvergeable,
    },
  )
  const reconciled = reconcilePicks(catalogue, resolution)
  const withPicks = { ...base, ...reconciled }

  if (!resolution) {
    // Review: code-reviewer (resolve-escalations.md Finding 2, MAJOR) — `reconcilePicks(catalogue,
    // null)` iterates zero `choicesMade` entries by construction, so `refused` is always `[]` on
    // this path and `convergenceLines`'s per-REFUSED trail warning never fires — even though
    // `planner` is a live, Edit-capable agent that may already have edited the plan body (per its
    // own brief) before its final structured-output call exhausted retries to `null`. The second
    // mitigation this phase relies on ("a refused pick warns the trail an unauthorised edit may
    // have landed") depends on `refused` being non-empty; a null return is exactly the case it
    // must not go quiet on, so a synthetic entry carries the same warning here.
    return {
      ...withPicks,
      refused: [
        ...withPicks.refused,
        'resolve pass returned nothing (exhausted retries) after a planner Edit call may already '
          + 'have landed — check the plan body for a change no catalogued option authorised',
      ],
      skipped: 'the resolve pass returned nothing; every escalation stays escalated',
    }
  }

  // Carry the resolve pass's own verdict rather than only its picks: RESOLVE_SCHEMA spreads
  // PLAN_SCHEMA, so a resolve can come back `blocked`, and dropping that reported the plan as
  // drafted while the gate never learned the resolution failed. A revised `exitCriterion` rides
  // back the same way — the pass was told to edit the plan body, so the criterion it returns can
  // legally have moved, and the trail would otherwise show the gate a stale one.
  //
  // `choicesMade` is the RECONCILED set, never the returned one: a pick the catalogue refused is
  // not a resolution, and the gate must not read one as though it were.
  const resolvedPlan = {
    ...plan,
    choicesMade: reconciled.picks.map((p) => ({
      escalationId: p.escalationId,
      chosen: p.chosen.id,
      rejected: p.rejected.map((o) => o.id),
    })),
    ...(resolution.exitCriterion ? { exitCriterion: resolution.exitCriterion } : {}),
    ...(resolution.status === 'blocked'
      ? { status: 'blocked', blockedReason: resolution.blockedReason || 'resolve pass returned blocked' }
      : {}),
  }

  return { ...withPicks, plan: resolvedPlan }
}

// Rendered once, for the trail and the readiness gate, so both read the same account of what was
// decided — and, in the same lines, what was NOT.
function convergenceLines(convergence) {
  if (!convergence) return '(the Resolve-escalations phase did not run for this plan)'
  const parts = [
    `${convergence.escalationCount} escalation(s), ${convergence.convergeable} choice-shaped, `
      + `${convergence.picks.length} settled, ${convergence.deferred.length} left escalated`
      + `${convergence.refused.length ? `, ${convergence.refused.length} REFUSED` : ''}`
      + `${convergence.skipped ? ` — skipped: ${convergence.skipped}` : ''}`,
  ]
  for (const p of convergence.picks) {
    parts.push(`  ${p.escalationId} CHOSE ${p.chosen.id} (${p.chosen.source}): ${p.chosen.text}`)
    parts.push(`  ${p.escalationId} did NOT choose: ${p.rejected.map((o) => `${o.id} (${o.source}): ${o.text}`).join(' | ') || '(none)'}`)
  }
  for (const d of convergence.deferred) parts.push(`  ${d.escalationId} STILL ESCALATED: ${d.reason}`)
  for (const n of convergence.notConvergeable) parts.push(`  ${n.id} not choice-shaped: ${n.reason}`)
  // The resolve pass edits the plan body before anything reconciles its picks, so a refusal is
  // also a warning about the FILE: read the plan before calling it ready.
  for (const r of convergence.refused) {
    parts.push(`  REFUSED ${r}  <-- the resolve pass edited the plan body; check it for a change no catalogued option authorised`)
  }
  return parts.join('\n')
}

// ---------------------------------------------------------------------------
// Phase 5b — Dispatch (XS only)
// ---------------------------------------------------------------------------

function executor(baton, decision, waveIndex, trailDir) {
  return agent(
    `Do the work this baton asks for. It is an XS: the EM sized it, and the size is final.

Baton: ${baton.id} — "${baton.title}"
Record: ${baton.path}
EM's sizing rationale: ${decision.rationale}

An XS routes to dispatch and has no plan — there is nothing to write a plan against and nothing
to review. Read the baton, do exactly what it asks, and report what you changed.

**Bounded to the baton's own remit.** If the work turns out larger than XS, STOP and report it
with \`completed: false\` and a \`blockedReason\` — do not grow into it. An XS that expands under
an executor is a sizing defect the EM needs to see, and finishing it quietly is how a wave
launders a mis-size into a fait accompli.

**Some XS work is a closure, not a change.** Confirm-and-close is a legitimate complete outcome:
verify the thing the baton asserts, record what you verified, and say so. Do not invent a code
change to make the work look substantial, and do not add a guard or a regression test for a
surface that no longer exists.

Report honestly. \`completed: false\` with a reason is a first-class outcome and costs nothing;
a partial reported as done costs whoever reads the trail next.
${REPO_ROOT_RULE}
${TRAIL_RULE(sidecarFor(trailDir, baton.id, 'execution'))}`,
    withRole('coordinator:executor', {
      label: `dispatch:${baton.id}`,
      phase: 'Dispatch',
      model: 'sonnet',
      schema: DISPATCH_SCHEMA,
    }),
  )
}

// ---------------------------------------------------------------------------
// Repair mode — SKILL.md § Three modes -> Repair. Re-dispositions an already-
// reviewed plan from what is already on disk: no sizingScout, no planner, no
// reviewerAgent. The caller has already read the plan's structured pointer
// records (this script has no fs primitive — WORKFLOW-AGENT-AS-FILE-HANDLE)
// and hands them in on `args.repairBatons`; this function does the one thing a
// live wave does after review fires — resolveVerdict + integrator — and
// nothing a fresh judgment would require.
//
// REFUSE LOUDLY, never integrate nothing. A repair run that finds no findings
// and reports success is worse than the pull it replaces: it looks like the
// plan was re-dispositioned and cleared. A missing plan, an empty review set,
// or any unresolved pointer refuses THIS baton by name rather than silently
// producing an empty integration for it.
// ---------------------------------------------------------------------------

async function repairBaton(entry, trailDir) {
  const { batonId, planPath, reviews, unresolvedPointers } = entry || {}
  const refuse = (reason) => ({ batonId, planPath: planPath || null, repaired: false, reason })

  if (!planPath) {
    return refuse(`no plan on record for ${batonId} — nothing to repair`)
  }
  if (Array.isArray(unresolvedPointers) && unresolvedPointers.length) {
    return refuse(
      `${unresolvedPointers.length} unresolved pointer(s) for ${batonId}: `
        + unresolvedPointers.map((p) => `${p.pointerPath} (${p.error})`).join('; '),
    )
  }
  if (!Array.isArray(reviews) || reviews.length === 0) {
    return refuse(`no review sidecars on record for ${batonId} — nothing to disposition`)
  }
  // A pointer record carrying no `verdict` is the OLD bare-path shape wearing the new
  // record's clothes (:590-594 names the same hazard one layer in). resolveVerdict()
  // passes an empty verdict straight through, so without this the findings integrate
  // under a verdict nobody wrote — the silent-success the loud refusal exists to prevent.
  const verdictless = reviews.filter((r) => !r || !r.verdict)
  if (verdictless.length) {
    return refuse(
      `${verdictless.length} pointer record(s) for ${batonId} carry no verdict: `
        + verdictless.map((r) => (r && r.sidecarPath) || '(no sidecarPath)').join('; ')
        + ' — pre-pointer-contract sidecars are not repairable input',
    )
  }

  // Resolved through the SAME resolveVerdict() a live review uses — a repair pass
  // does not reconstruct `verdict`/`premiseFailure` by any other means. This is
  // what makes a REJECTED-with-premiseFailure pointer resolve to PIVOT here exactly
  // as it would in a live wave, instead of silently falling back to BLOCKED.
  const kept = reviews.map(resolveVerdict)

  // The EXISTING integrator(), unforked. A minimal baton stand-in: integrator()
  // consumes only `baton.id` from it.
  // Review: overengineering-reviewer (F2) — integrator() returns agent(...) unconditionally
  // and the live wave's identical call site carries no such guard; this was defending a
  // return shape the shared callee cannot produce.
  const integration = await integrator({ id: batonId }, { planPath }, kept, trailDir)
  return { batonId, planPath, repaired: true, integration }
}

if (parsedArgs.mode === 'repair') {
  const repairBatons = parsedArgs.repairBatons || []
  if (repairBatons.length === 0) {
    return { mode: 'repair', repaired: [], refused: [], empty: true }
  }
  if (!REPO_ROOT) {
    // `integrator()` edits the plan at `planPath`, which is repo-relative. With no root to
    // resolve it against, the edit either misses or lands in another tree — and a repair run
    // that quietly dispositioned nothing is indistinguishable from one that worked.
    return {
      mode: 'repair',
      repaired: [],
      refused: repairBatons.map((e) => ({
        batonId: (e && e.batonId) || null,
        planPath: (e && e.planPath) || null,
        repaired: false,
        reason: 'no repoRoot supplied — refusing rather than resolving the plan path against the dispatching shell\'s working directory',
      })),
    }
  }
  if (!parsedArgs.trailDir) {
    // Unvalidated, this renders `undefined/<baton>.review-integration.md` into the
    // integrator's TRAIL_RULE and loses the trail sidecar with no error anywhere.
    return {
      mode: 'repair',
      repaired: [],
      refused: repairBatons.map((e) => ({
        batonId: (e && e.batonId) || null,
        planPath: (e && e.planPath) || null,
        repaired: false,
        reason: 'no trailDir supplied to repair mode — refusing rather than writing the trail sidecar to an undefined path',
      })),
    }
  }
  // Review: coordinator:code-reviewer close (nitpick) -- pipeline() processes each entry
  // independently with no dedup, so two entries citing the same batonId with different
  // planPaths both run against the plan and the result array does not surface the collision.
  // Refuse both rather than pick a winner: nothing here can tell which entry is authoritative.
  const idCounts = new Map()
  for (const e of repairBatons) {
    const id = e && e.batonId
    if (id == null) continue
    idCounts.set(id, (idCounts.get(id) || 0) + 1)
  }
  const duplicateIds = new Set([...idCounts.entries()].filter(([, n]) => n > 1).map(([id]) => id))
  const runnable = duplicateIds.size
    ? repairBatons.filter((e) => !e || !duplicateIds.has(e.batonId))
    : repairBatons
  const duplicateRefusals = duplicateIds.size
    ? repairBatons
      .filter((e) => e && duplicateIds.has(e.batonId))
      .map((e) => ({
        batonId: e.batonId,
        planPath: e.planPath || null,
        repaired: false,
        reason: `duplicate batonId "${e.batonId}" across repairBatons entries -- refusing `
          + 'both/all rather than integrating two conflicting runs against the same plan',
      }))
    : []
  const results = await pipeline(runnable, (entry) => repairBaton(entry, parsedArgs.trailDir))
  return {
    mode: 'repair',
    repaired: results.filter((r) => r && r.repaired),
    refused: [...duplicateRefusals, ...results.filter((r) => r && !r.repaired)],
  }
}

// ---------------------------------------------------------------------------
// Wave body
// ---------------------------------------------------------------------------

const waveIndex = parsedArgs.waveIndex
const trailDir = parsedArgs.trailDir
const batons = parsedArgs.batons || []

// A WAVE INDEX IS NOT A FIRE IDENTITY. The skill caps a fire at 8 batons, so any wave with more
// than that is drained by SEVERAL fires that all carry the same `waveIndex` — and the one
// wave-scoped sidecar this script writes, `wave-<n>.em-size-review.md`, is the same path in every
// one of them. Each later fire silently overwrote the earlier fire's size review, which is the
// per-baton overwrite `slug`'s own comment documents, one level up and correspondingly quieter:
// the wave's decisions live in memory and are unaffected, so nothing fails — only the durable
// trail loses the record of how N-8 batons were sized.
//
// `fireId` discriminates on the fire's own baton set, so it is stable across a resume (which must
// land on the same sidecar) and distinct between two fires of one wave (which must not). Derived,
// never an arg: a caller that had to pass it would forget, and the failure is invisible.
const fireId = (() => {
  const key = batons.map((b) => String(b && b.id)).sort().join('\u0000')
  let h = 0x811c9dc5
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
})()

//: The wave-scoped sidecar's baton-slot, `wave-<index>-<fireId>`. One name, computed once, so the
//: write site cannot drift from anything that later resolves the same record.
const waveSlot = `wave-${waveIndex}-${fireId}`

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

const dispatch = await agent(
  `phase: size-review

${ROLE_CONTRACTS['blitz-em']}

You are the blitz-em for plan-blitz wave ${waveIndex}. Interrogate and finalise the sizing for
every baton below, then emit the dispatch spec the planning phase will read.

The gate report this wave was resolved from: ${parsedArgs.gateReportPath}. Read it. A baton here may
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

    Emit these EXACT strings. This repo's own docs may name reviewers by persona first name
    ("add the Game Dev Reviewer or the Data Science Reviewer", "have the Staff Engineer look at it") — that is human shorthand and it is NOT an
    agent type. Never pass a persona name through, and never invent 'coordinator:<firstname>':
    no such type exists, and a name off this list is substituted for staff-eng with the downgrade
    printed in the trail, so the plan gets reviewed by someone other than whom you chose.
    If a baton genuinely needs expertise outside these three, say so in \`rationale\` and pick the
    closest of the three — the gap is a thing for the EM to read, not a string for you to coin.

Anything that is the PM's call — route: pm-decision, or an XL exit — set surfacedToPm: true with
the question stated in the PM's register, and give it no reviewers. You are an EM proxy, never a
PM proxy.
${NO_EXECUTION_RULE}
${REPO_ROOT_RULE}
${CLI_RESOLUTION_RULE}
${TRAIL_RULE(sidecarFor(trailDir, waveSlot, 'em-size-review'))}`,
  withRole('coordinator:blitz-em', {
    label: `size-review:${waveSlot}`,
    phase: 'Size review',
    model: 'opus',
    schema: WAVE_DISPATCH_SCHEMA,
  }),
)

// Plannability follows the ROUTE, not a boolean. Only `plan` and `spec-dispatch`
// produce a plan document; every other route is a different room, and sending
// one to a planner writes an artifact doctrine says should not exist.
//
// Measured on the first live wave: an XS baton the EM correctly routed
// `dispatch` was planned, reviewed and integrated anyway — four surplus agent
// dispatches for a confirm-and-close — because this filter tested
// `surfacedToPm` alone. The resulting plan was good, which is exactly why the
// defect was invisible in the output: quality does not reveal surplus.
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
  const root = REPO_ROOT.replace(/[/\\]+$/, '')
  for (const sep of ['/', '\\']) {
    const prefix = root + sep
    if (text.startsWith(prefix)) return text.slice(prefix.length).replace(/\\/g, '/')
  }
  // Absolute but NOT under this repo: left exactly as it is. The read-side gate refusing a
  // citation that resolves nowhere is the correct outcome; quietly rewriting it into something
  // that looks local would hide a real defect behind a plausible path.
  return text
}

const decisions = ((dispatch && dispatch.decisions) || []).map((d) =>
  d && typeof d === 'object' && d.sizingObject
    ? { ...d, sizingObject: repoRelativeCitation(d.sizingObject) }
    : d,
)
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

// Phases 3-5 — plan, review, integrate, per baton, PIPELINED. No barrier between the stages: a
// baton whose plan lands first starts its review while its siblings are still planning. The
// wave's wall-clock is then the slowest single baton's chain, not the sum of three barriers.
const chains = await pipeline(
  plannable,
  (decision) => {
    const baton = batons.find((b) => b.id === decision.batonId)
    return planner(baton, decision, waveIndex, trailDir).then((plan) => ({ decision, baton, plan }))
  },
  async ({ decision, baton, plan }) => {
    if (!plan || plan.status === 'blocked') {
      // A planner that could not write a plan is carried to the readiness gate as a blocked
      // entry rather than dropped. A baton that vanishes between waves is one nobody notices.
      return { decision, baton, plan, reviews: [], integration: null }
    }
    // The planner's own `planPath` is a CLAIM, not a fact, and both the reviewer and the
    // integrator are pointed at it. Measured: one planner returned its wave TRAIL SIDECAR
    // here instead of the plan it had written under `docs/plans/`. The reviewer found the
    // real document anyway and its findings cited it; the integrator, named on the sidecar,
    // correctly declined to edit a file it was not named on — so every finding on that plan,
    // an AUTO-FIX among them, was dropped while the chain reported success. Sibling batons in
    // the same wave got the real path, which is why it read as inconsistency rather than a bug.
    //
    // A path inside the trail directory or anywhere under `subagent-share/` is never a plan.
    // Prefer the baton's own recorded plan when it has one — that path came from the repo, not
    // from an agent — and otherwise carry the chain as blocked rather than aiming two more
    // agents at a file that is not the artifact.
    const claimed = String(plan.planPath || '')
    const looksLikeTrail =
      claimed.includes('subagent-share') ||
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
              `a reviewer and an integrator at a file that is not the plan`,
          },
          reviews: [],
          integration: null,
        }
      }
    }

    // Phase 3.5 — Premise check. Dispatched here, before any reviewer resolves or fires: this is
    // the one place `plan` is trusted and stable (past the looksLikeTrail correction above) and
    // no reviewer has fired yet. Sequenced rather than run alongside the reviewers on purpose —
    // the whole saving is that they do not spend their pass resolving citations, and a check
    // racing them arrives too late to buy that.
    const premise = await premiseChecker(baton, plan, trailDir)
    // The seam. Rows in, one REVIEW_SCHEMA entry out, so the report reaches the integrator
    // through the channel a reviewer already uses. The checker took no route; this did.
    const premiseCheckResult = premiseAsReview(baton, premise)

    const { reviewers, substitutions } = resolveReviewers(decision.reviewers)
    // Review: code-reviewer (resolve-escalations.md Finding 6, minor) — `REVIEW_SCHEMA.reviewer`
    // is filled in by the dispatched agent's own structured-output call, and nothing forced it to
    // agree with the identity it was actually dispatched under. `convergenceCatalogue`'s
    // attribution bound is "is this string a member of the reviewer-name set", so an unverified
    // set membership is a softer version of Finding 1's class. `reviewer` here is the
    // harness-resolved dispatch identity (`resolveReviewers`'s own output, the same value
    // `withRole(reviewer, ...)` dispatches under) — overwrite the self-report with it rather than
    // trust it.
    const reviews = await parallel(
      reviewers.map((reviewer) => async () => {
        const result = await reviewerAgent(baton, decision, plan, reviewer, trailDir, premise)
        return result ? { ...result, reviewer } : result
      }),
    )
    // Resolved ONCE, here, at the seam where the reviewers' words arrive. Everything
    // downstream — integration, the trail, the gate, the landing — reads the resolved
    // route and never re-interprets the word. The premise check rides the same resolution: it
    // is just another REVIEW_SCHEMA entry, so a premise miss reaches the integrator's ASK bar
    // and the readiness gate exactly the way a reviewer's BLOCKED does.
    //
    // Review: coordinator:code-reviewer — kept separately so a null/malformed premise-check
    // return is visible in the trail as an explicit "did not run" row rather than vanishing
    // into `.filter(Boolean)` indistinguishably from a clean pass. The premise check is the
    // ONLY instance of its kind per baton, so its silent drop left zero premise verification
    // on the baton with no trace anywhere the readiness gate could notice.
    const premiseCheckVerdict = premiseCheckResult ? resolveVerdict(premiseCheckResult) : null
    const kept = [premiseCheckResult, ...reviews].filter(Boolean).map(resolveVerdict)
    // Integration is unconditional — including on an all-OK review set, and including on a
    // PIVOTed one (where the integrator applies nothing and triages every sidecar's
    // findings as suspended, so the co-reviewers' work reaches the replan).
    const integration = await integrator(baton, plan, kept, trailDir, premise)

    // Phase 5a — Resolve escalations. Conditional: `resolveEscalations` fires the planner only
    // where the integration escalated something choice-shaped, and returns a record either way,
    // so a plan that skipped it and a plan that found nothing are different rows in the trail.
    const convergence = await resolveEscalations(
      baton, decision, waveIndex, plan, kept, integration, trailDir,
    )
    return {
      decision,
      baton,
      plan: convergence.plan,
      reviews: kept,
      premiseCheckVerdict,
      integration,
      substitutions,
      premise,
      convergence,
    }
  },
)

// Phase 5b — XS work, executed. LAST, deliberately: planning is read-mostly and this
// phase mutates, so running it after the pipeline means every planner in this wave read a
// tree no sibling was changing underneath it.
const dispatched = (
  await pipeline(dispatchable, (decision) =>
    executor(batonFor(decision), decision, waveIndex, trailDir),
  )
).filter(Boolean)

// Phase 6 — the EM's terminal gate, over the trail rather than over the agents' summaries.
const trailLines = chains
  .filter(Boolean)
  .map(({ decision, baton, plan, reviews, premiseCheckVerdict, integration, substitutions, premise, convergence }) => {
    // Every reviewer is named with their OWN resolved verdict. A collapsed
    // "the review said X" is how a wave loses the review that disagreed.
    const verdicts = reviews.map((r) => `${r.reviewer}=${r.verdict}`).join(', ') || 'none ran'
    // Review: coordinator:code-reviewer — explicit row so "premise check ran and found
    // nothing" and "premise check did not run" (null/malformed return, dropped upstream)
    // render as visibly different states, never as the same silence.
    // Review: code-reviewer (premise-check.md Finding 3, routed via resolve-escalations.md) — an
    // `OK` reached with zero citations examined must not render like an `OK` that checked
    // everything and found nothing; `citationsChecked` is the count `premiseAsReview` now carries
    // for exactly this.
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
      integration: ${integration ? `${integration.applied} applied, ${(integration.escalated || []).length} escalated -> ${integration.reportPath}` : '(did not run)'}
      escalated ASKs: ${integration && integration.escalated && integration.escalated.length ? integration.escalated.map((e, i) => `E${i + 1}: ${e}`).join('; ') : 'none'}
      resolve escalations: ${convergenceLines(convergence).split('\n').join('\n      ')}`
  })
  .join('\n')

const readiness = await agent(
  `phase: readiness-gate

${ROLE_CONTRACTS['blitz-em']}

You are the blitz-em for plan-blitz wave ${waveIndex}, at its terminal gate. Every plan below was
written, reviewed and integrated without consulting you — that is by design. Your job is to pull
items OUT, over the trail.

Trail directory: ${trailDir}
Gate report this wave was resolved from: ${parsedArgs.gateReportPath}

THE TRAIL DIRECTORY IS SHARED, AND YOUR MANDATE IS THE LIST BELOW — NOT THE DIRECTORY. A wave
larger than one fire is drained by SEVERAL fires at this same waveIndex, all writing into that one
trail, and they may be running CONCURRENTLY. So the trail holds sidecars for batons that are not
yours: some belong to a fire that already landed, some to a fire that is still authoring its plans
right now. Judge EXACTLY the batons enumerated below and no others. Read another baton's sidecar
if it informs one of yours — that costs nothing — but never return a verdict for it. A verdict on
a baton outside this fire either overrides a landing that already happened or stamps a plan whose
author has not finished writing it, and both read as ordinary output.

${trailLines}

${dispatched.length ? `XS batons DISPATCHED in this wave (no plan, work already done):
${dispatched.map((d) => `  - ${d.batonId}: ${d.completed ? 'completed' : 'INCOMPLETE'} — ${d.summary}${d.blockedReason ? ` [blocked: ${d.blockedReason}]` : ''}
      files: ${(d.filesChanged || []).join(', ') || '(none — a closure, not a change)'}`).join('\n')}

For each of these the question is different: did it do what the baton asked, and is the baton now
closable? An INCOMPLETE one, or one that grew past XS, is a sizing defect to report — say so.` : ''}

One question per plan: is it ready to execute? Answer ready, pulled, or replan — and give a reason
that names the evidence. "Looks off" is not a disposition.

Read the escalated ASKs first. They are the findings judged too consequential to apply silently,
which makes them the highest-signal line in the trail and the one a fast read skips. Some of them
were settled beneath, under \`resolve escalations\`, by a post-integration pass that picked among
the reviewers' own enumerated options. Read a resolution with the SAME priority you give an
unresolved ASK: it tells you what was picked and what was not, never that the question is settled.

Open the sidecars. A summary line saying OK is not evidence anyone checked — a reviewer can
confirm an author's prose without opening the code that would falsify it. Spot-check one
substantive claim per plan against the tree.

The premise check makes no claim about the plan. The \`premise-check\` verdict on the reviews line
is the wave's routing of its rows, not the checker's opinion: BLOCKED means citations did not
resolve, and a clean table says one class of false premise is absent — never that the plan is
right, and never a reason to shorten your read. The \`premise rows\` block is where the signal is.
Its UNCHECKABLE rows are assumptions nothing in this tree settled, carried forward openly rather
than passed; a class its coverage line renders "none" was never attempted — a hole, not a pass;
and its falsifier-arming line is the highest-value entry, because a plan whose instrument cannot
report red has no evidence behind whatever it claims that instrument will show.

The \`resolve escalations\` lines are a RECORD, not an approval. A settled escalation was decided
by the planner picking among alternatives a reviewer wrote down, and both halves are printed —
what was chosen and what was not, computed from the catalogue rather than reported by the pass.
Judge the pick like any other change to the plan: it is yours to disagree with, and disagreeing is
a pull with a reason, not an override. A REFUSED line is the stronger signal — the pass named
something no reviewer enumerated, the wave declined it, and the plan body was already edited by
then, so open the file. STILL ESCALATED means nobody settled it: it reaches you exactly as an
escalation always has.

BLOCKED and PIVOT are different questions, and the trail above keeps them apart per reviewer.

A BLOCKED review is not a reason to withhold ready. It says the plan was wrong until the findings
were fixed; the integrator has fixed them. Judge the INTEGRATED plan — check that the findings
were actually applied, and if they were, a plan whose every review was BLOCKED is a normal ready.

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
  withRole('coordinator:blitz-em', {
    label: `readiness:wave-${waveIndex}`,
    phase: 'Readiness gate',
    model: 'opus',
    schema: READINESS_SCHEMA,
  }),
)

// WAVE RESULT — the caller stamps `ready` plans to `approved` (which is what opens the NEXT
// wave's planning gates), mints a baton per `replan` entry, and re-queues both `pulled` and
// `replan` for a later wave. `surfacedToPm` never re-queues on its own: it needs a PM answer
// first, and a wave that silently retried it would be answering for them.
// Each verdict carries the ROUTE its baton was finalised at, joined here rather
// than asked of the EM: the landing branches on it (spec-dispatch parks a spec and
// stamps execution-ready; everything else takes the ordinary approval), and asking
// an agent to restate data the wave already holds is how the two copies drift.
const converged = chains.filter(Boolean).map(({ baton, convergence }) => ({
  batonId: baton.id,
  escalations: convergence ? convergence.escalationCount : 0,
  convergeable: convergence ? convergence.convergeable : 0,
  settled: convergence ? convergence.picks.length : 0,
  deferred: convergence ? convergence.deferred.length : 0,
  refused: convergence ? convergence.refused.length : 0,
  skipped: (convergence && convergence.skipped) || null,
}))

const routeById = new Map(decisions.map((d) => [d.batonId, d.route]))
const reviewsById = new Map(chains.filter(Boolean).map(({ baton, reviews }) => [baton.id, reviews]))

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

const verdicts = ((readiness && readiness.verdicts) || []).filter((v) => fireBatonIds.has(v.batonId)).map((v) => {
  const reviews = reviewsById.get(v.batonId) || []
  const entry = {
    ...v,
    route: routeById.get(v.batonId) || null,
    // Carried so the LANDING can refuse independently. `roadmap.blitz_land` re-checks
    // this and will not stamp a plan a reviewer pivoted, whatever this workflow decided
    // — two enforcement points, because the one in a file an agent edits is the one
    // that goes missing.
    reviewVerdicts: reviews.map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
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

return {
  waveIndex,
  trailDir,
  ready: [...verdicts.filter((v) => v.verdict === 'ready'), ...closable],
  pulled: verdicts.filter((v) => v.verdict === 'pulled'),
  replan: verdicts.filter((v) => v.verdict === 'replan'),
  surfacedToPm,
  // Verdicts this fire's gate returned for batons that are not its own, dropped before they
  // could reach the landing. Non-empty means the gate over-reached its fire — usually because a
  // concurrent fire is writing into the same shared trail. Carried so the caller can see what
  // was declined rather than discovering it as a silent absence.
  foreignVerdicts,
  // XS work this wave actually finished, rather than handing back.
  dispatched,
  // Sized and routed, but neither planned nor dispatchable here — including an
  // XS whose EXECUTION gate is shut. Each names the room it belongs in.
  routedElsewhere,
  // The conversion instrument. `convergeable` is the count of escalations that, before this
  // phase existed, could not have been repaired in-wave at all — so the rate this baton claims
  // to move is countable from wave one, over these rows joined to `ready`/`pulled`, with no
  // before-and-after and no peer figure standing in for a DoE measurement.
  // Method: coordinator/docs/wiki/blitz-convergence.md § Re-measurement.
  converged,
}
