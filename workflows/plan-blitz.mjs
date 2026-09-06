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
 *       planPath: string|null // an existing plan, when the baton already has one. Non-null
 *                             //  means this wave REVISES rather than authors.
 *     } ]
 *   }
 *
 * Invocation:
 *   Workflow({
 *     scriptPath: "coordinator/workflows/plan-blitz.mjs",
 *     args: {
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

export const meta = {
  name: 'plan-blitz',
  description: 'One planning wave: sonnet scouts size the batons, an Opus EM finalises, Opus planners write, plans are reviewed and integrated unconditionally, and the EM gates readiness at the end.',
  phases: [
    { title: 'Size', detail: 'One sonnet sizing-scout per unsized baton — substrate read, touchpoint inventory, prior art, and a proposed t-shirt with its evidence. Skipped for a baton that already cites a sizing-object.' },
    { title: 'Size review', detail: 'One Opus blitz-em over the whole wave. Interrogates every proposed size (revising down by default), finalises the route via sizing-assemble, and emits the per-baton dispatch spec the Plan phase reads.' },
    { title: 'Plan', detail: 'One Opus planner per baton, on every route and at every size — authoring is not a lane the wave economises on. Writes the plan doc through coordinator:plan / scaffold-plan; never hand-authors frontmatter.' },
    { title: 'Premise check', detail: 'One check per baton, dispatched after the plan\'s path is trusted and before any reviewer fires: does the plan\'s premise hold against the tree right now (cited paths, symbols, refs, and instrument-can-report-red), riding the same REVIEW_SCHEMA and BLOCKED/PIVOT routing a reviewer uses. A premise miss is BLOCKED, not PIVOT, unless it is a class-5 semantic finding with no writable fix.' },
    { title: 'Review', detail: 'Reviewers resolved per baton from the EM dispatch spec, never prescribed in the plan file. Fires unconditionally — the EM is not consulted about whether a plan deserves review.' },
    { title: 'Integrate', detail: 'review-integrator per plan, also unconditional, including on a clean OK. Applies findings and escalates ASKs. A PIVOT from any reviewer suspends integration for the whole plan, with every sidecar still triaged so no co-reviewer findings are lost.' },
    { title: 'Resolve escalations', detail: 'Conditional: fires only when a plan\'s integration escalated at least one ASK. Re-invokes the Plan phase\'s own planner/prompt in its revising branch, picking ONLY among alternatives a reviewer already enumerated (review-integrator.md:199) — never authoring a third option. Records every pick via `choicesMade` so the trail carries the resolution, not just the question.' },
    { title: 'Dispatch', detail: 'One executor per XS/dispatch baton whose EXECUTION gate is open. Runs AFTER planning so the wave plans against a stable tree and the only mutating phase is last. Bounded to the remit the baton itself states — an XS that grows is a sizing defect, not a bigger job.' },
    { title: 'Readiness gate', detail: 'One Opus blitz-em over the durable trail. Per plan: ready, pulled, or replan. A PIVOT routes to a replan baton for a later wave rather than halting this one, and is reconciled mechanically rather than left to the gate.' },
  ],
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
    // `RESOLVE_SCHEMA` below) — never by an ordinary authoring or revising call. Control-flow-inert,
    // the same shape as `blockedReason` above: its only consumer is the trail renderer, which is
    // why it is a discriminant field rather than prose. One entry per escalated ASK the resolve
    // pass acted on; `chosen` and each `rejected` entry are option identifiers drawn from that
    // ASK's own stated option list (review-integrator.md:199), never invented text.
    choicesMade: {
      type: 'array',
      items: {
        type: 'object',
        required: ['escalationId', 'chosen', 'rejected'],
        properties: {
          escalationId: { type: 'string' },
          chosen: { type: 'string' },
          rejected: { type: 'array', items: { type: 'string' } },
        },
      },
    },
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

const PLUGIN_AGENTS = args.pluginAgentsAvailable === true

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
// Probed 2026-09-06: verify-snippet-sync pastes a snippet's raw HTML-comment sentinels and
// markdown body verbatim at the target path with no language awareness. Against a synthetic
// `.mjs` consumer entry, `--fix` appended the sentinel-delimited markdown block as bare top-level
// text — a syntax error in JavaScript outside a string/template literal (confirmed by direct
// `verify-snippet-sync instrument-can-report-red --fix` probe against a scratch registry entry
// pointing at this file; reverted after the probe). The tool therefore does not meaningfully
// support a non-markdown paste target — it does not crash, but it does not produce valid output
// either. Falling back per this chunk's stated contingency: a hand-synced module-level constant,
// kept honest by one containment assertion in test_plan_blitz_contract.py, not a sentinel-synced
// paste. Re-copy verbatim from the two `.md` sources on edit; do not paraphrase.
//
// Escaping rule: both source texts contain no `${}` sequence (verified at authoring time), so
// every backtick in the pasted text below is escaped as \` and no other transformation is
// needed. If either source ever grows a `${}` sequence, re-escape it the same way before pasting.
const PREMISE_CHECK_CONTRACT = `## Premise Check Contract

A premise check asks one question, in five classes, over a plan's cited paths, symbols, refs and
in-repo behaviour claims: **does this plan's premise actually hold against the tree right now?**
It is written to be INLINED into a dispatch brief, never dispatched as its own agent — the
\`PLUGIN_AGENTS\` default-off constraint means an \`agentType\` the harness cannot resolve silently
degrades to a generic agent wearing the role's label, which reuses the persona and loses the
check. Whatever consumes this text must inline it directly.

**Classes 1 and 2 — paths and symbols (mechanical).** For every cited in-repo path: does it
exist? For every cited \`file:line\` / \`file:symbol\` claim: does the symbol exist in that file? This
is the same check plan-coverage-checker's Lens 3 already runs (\`ls\`-check cited paths,
\`Read\`-verify cited claims, grep backtick-quoted in-repo constants) — it is not re-derived here.

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
owner of the standing blitz-conversion re-measurement effort re-checks the trigger against a
class-5 firing log (every class-5 finding, with whether the subsequent symbol read confirmed or
refuted the plan's claim) before the PROVISIONAL mark comes off. Until then, a class-5 finding
carries the same weight as any other finding — only the TRIGGER is under review, not the finding's
validity.

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
or degraded result — a class-5 miss with no forbidding surface and no defect vocabulary is
reported as "class 5 not applicable, degrades to reviewer judgment," not withheld.`

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
const REVIEW_SIDECAR_RULE = (pointerPath) => `
Write your findings sidecar to YOUR OWN PROVISIONED SIDECAR under
\`<machinery_root>/subagent-share/<your session id>/\`, and return its absolute path verbatim as
\`sidecarPath\`. Do NOT write your findings into the wave trail: \`append-integrator-dispositions\`
refuses any path without \`subagent-share\` as a path segment, and a findings sidecar it cannot
open is a review whose dispositions are never recorded.

Then write a POINTER file at EXACTLY this path, containing the one absolute path above and
nothing else:

    ${pointerPath}

The pointer is how the readiness gate finds you. A findings sidecar with no pointer is a review
the gate cannot see, and a pointer with no sidecar is worse — it reads as a review that ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the EM's readiness gate will never see.`

const NO_EXECUTION_RULE = `
You do not execute. No code changes, no "quick fix while I'm here", no chunk work. A defect you
spot in the tree is something you report, not something you do.`

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
  // only when integration on this baton escalated at least one ASK, and `baton.planPath` is
  // guaranteed set by then (the plan was written or revised earlier in this same wave).
  const resolveBrief = escalation
    ? `
RESOLVE PASS — not authoring, and not an ordinary revision. Integration on this plan escalated
${escalation.escalated.length} ASK(s) too consequential to apply silently. Full findings:
${escalation.reportPath}.

Escalated ASKs, numbered for reference:
${escalation.escalated.map((e, i) => `  escalation-${i + 1}: ${e}`).join('\n')}

For each one, pick ONLY among the concrete options its reviewer already enumerated —
\`review-integrator.md:199\` fixes the requirement that every escalated ASK carries "two-or-more
concrete options"; that enumerated set is what you choose among. Never invent a third option, and
never author a fix that is not one of the alternatives already stated for that ASK. If an ASK's
option list is genuinely unusable (fewer than two options, or none apply), say so in your returned
summary and leave that ASK unresolved rather than guessing.

Edit the plan body to reflect the picks you make, then return \`choicesMade\`: one entry per
escalation you resolved, \`{ escalationId, chosen, rejected }\`, where \`escalationId\` is the
\`escalation-N\` label above and \`chosen\`/each \`rejected\` entry is an option identifier drawn
from that escalation's own stated option list — never invented text. This is REQUIRED on your
return: it is the only record of what was picked and what was not, and the trail renders it next
to the escalation it resolves.
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
its body.` : PLUGIN_AGENTS ? `Invoke the coordinator:plan skill and follow it. Two rules from it that a fan-out is most likely
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
docs/plans/<YYYY-MM-DD>-<slug>.md. Frontmatter, exactly these keys and nothing invented:

    ---
    title: "<title>"
    created: <YYYY-MM-DD>
    status: draft
    author: plan-blitz
    deliverable_id: "<the baton's own deliverable_id, copied verbatim from its record>"
    sizing_object: ${sizingFm}
    ---

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
${NO_EXECUTION_RULE}
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
// Phase 4 — Review
// ---------------------------------------------------------------------------

function reviewerAgent(baton, decision, planResult, reviewer, trailDir) {
  return agent(
    `${ROLE_CONTRACTS.reviewer}

Review the plan at ${planResult.planPath} for baton ${baton.id} ("${baton.title}").

Finalised size: ${decision.tshirt}, route: ${decision.route}.
Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}

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
// Phase 3.5 — Premise check
// ---------------------------------------------------------------------------
//
// Dispatched once per baton, after the plan's `planPath` is trusted and stable (past the
// looksLikeTrail correction) and before any reviewer fires — the one place in the pipeline
// where a false premise can be caught before it costs a reviewer's read. Rides REVIEW_SCHEMA
// and the same sidecar/pointer machinery as a reviewer so the rest of the pipeline (resolveVerdict,
// integrator, the trail, the readiness gate) needs no premise-check-specific branch: a premise
// miss is just another entry in `kept`.
//
// Role name is contract: `premise-check` must not collide with plan / planning-report /
// review-*/ review-integration (sidecarFor's role-name uniqueness rule, see its own comment).
function premiseCheckAgent(baton, decision, planResult, trailDir) {
  return agent(
    `You are the premise check for baton ${baton.id} ("${baton.title}")'s plan at
${planResult.planPath}.

Stated prime exit criterion: ${planResult.exitCriterion || '(none stated — that is itself a finding)'}

${PREMISE_CHECK_CONTRACT}

${INSTRUMENT_CAN_REPORT_RED_CONTRACT}

Apply the premise-check contract above to this plan's cited paths, symbols, refs and in-repo
behaviour claims, and apply the instrument check above to any falsifier, gate, or verification
instrument the plan itself introduces or names. Report both under the same verdict — this pass
never claims plan correctness; it reports what it checked and what it found.

Verdict routing rides the SAME schema and the SAME two routes a plan reviewer uses — do not invent
a third:

  - BLOCKED — the DIRECTION holds; a repairable premise miss (an unresolved cited path, symbol or
    ref; an instrument whose verdict is computed but not wired to its exit path) is BLOCKED,
    however many findings there are. Populate \`premiseFailure\` with what you found.
  - PIVOT — reserved for a class-5 semantic failure where NO fix is writable from the finding
    alone. PIVOT requires BOTH a class-5 finding AND that no fix is writable — class 5 is
    necessary but not sufficient. Where a fix IS writable, return BLOCKED even for a class-5
    finding. When you are between them, return BLOCKED: this is the existing tripwire
    \`coordinator/docs/wiki/coordinator-tripwires/a-blocked-review-is-not-a-pivot.md\` — "the
    separating test is: write the fix… When you are between them, return BLOCKED" — cite it in
    your sidecar rather than re-deriving the rule.
${NO_EXECUTION_RULE}
${REVIEW_SIDECAR_RULE(sidecarFor(trailDir, baton.id, 'premise-check'))}`,
    withRole('coordinator:plan-coverage-checker', {
      label: `premise-check:${baton.id}`,
      phase: 'Premise check',
      model: 'sonnet',
      schema: REVIEW_SCHEMA,
    }),
  )
}

// ---------------------------------------------------------------------------
// Phase 5 — Integrate
// ---------------------------------------------------------------------------

function integrator(baton, planResult, reviews, trailDir) {
  // The verdict shown is the RESOLVED one. A sidecar whose own text says REJECTED is
  // labelled with what that resolved to, so the file and this list cannot look like
  // two different reviews.
  const sidecars = reviews
    .map((r) => `  - ${r.reviewer}: ${r.verdict}${r.aliased ? ` (sidecar says ${r.raw}; ${r.aliased})` : ''} -> ${r.sidecarPath}`)
    .join('\n')

  return agent(
    `${ROLE_CONTRACTS['review-integrator']}

Integrate the review findings for baton ${baton.id} into ${planResult.planPath}.

Reviewer sidecars on disk:
${sidecars}

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
// Wave body
// ---------------------------------------------------------------------------

const waveIndex = args.waveIndex
const trailDir = args.trailDir
const batons = args.batons || []

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

The gate report this wave was resolved from: ${args.gateReportPath}. Read it. A baton here may
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
${TRAIL_RULE(sidecarFor(trailDir, `wave-${waveIndex}`, 'em-size-review'))}`,
  withRole('coordinator:blitz-em', {
    label: `size-review:wave-${waveIndex}`,
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

const decisions = (dispatch && dispatch.decisions) || []
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
    reason: DISPATCHABLE_ROUTES.has(d.route)
      ? 'XS/dispatch, but its EXECUTION gate is shut — blockers planned, not coded'
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

    // Phase 3.5 — Premise check. Dispatched here, before any reviewer resolves or fires: this
    // is the one place `plan` is trusted and stable (past the looksLikeTrail correction above)
    // and no reviewer has fired yet.
    const premiseCheckResult = await premiseCheckAgent(baton, decision, plan, trailDir)

    const { reviewers, substitutions } = resolveReviewers(decision.reviewers)
    const reviews = await parallel(
      reviewers.map((reviewer) => () => reviewerAgent(baton, decision, plan, reviewer, trailDir)),
    )
    // Resolved ONCE, here, at the seam where the reviewers' words arrive. Everything
    // downstream — integration, the trail, the gate, the landing — reads the resolved
    // route and never re-interprets the word. The premise check rides the same resolution: it
    // is just another REVIEW_SCHEMA entry, so a premise miss reaches the integrator's ASK bar
    // and the readiness gate exactly the way a reviewer's BLOCKED does.
    const kept = [premiseCheckResult, ...reviews].filter(Boolean).map(resolveVerdict)
    // Integration is unconditional — including on an all-OK review set, and including on a
    // PIVOTed one (where the integrator applies nothing and triages every sidecar's
    // findings as suspended, so the co-reviewers' work reaches the replan).
    const integration = await integrator(baton, plan, kept, trailDir)

    // Phase 5a — Resolve escalations. Conditional, and the only new call site this pipeline
    // gains: fires exactly when integration escalated at least one ASK on a plan that is not
    // already blocked. A PIVOT never reaches here — the integrator applies and escalates
    // nothing on a suspended plan, so `escalated` is empty and this step is a no-op for it.
    let resolvedPlan = plan
    if (integration && integration.escalated && integration.escalated.length && plan.status !== 'blocked') {
      const resolution = await planner(baton, decision, waveIndex, trailDir, {
        escalated: integration.escalated,
        reportPath: integration.reportPath,
      })
      if (resolution) {
        resolvedPlan = { ...plan, choicesMade: resolution.choicesMade || [] }
      }
    }
    return { decision, baton, plan: resolvedPlan, reviews: kept, integration, substitutions }
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
  .map(({ decision, baton, plan, reviews, integration, substitutions }) => {
    // Every reviewer is named with their OWN resolved verdict. A collapsed
    // "the review said X" is how a wave loses the review that disagreed.
    const verdicts = reviews.map((r) => `${r.reviewer}=${r.verdict}`).join(', ') || 'none ran'
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
      reviews: ${verdicts}${pivots.length ? `  <-- PIVOT (${pivots.map((r) => r.reviewer).join(', ')})` : ''}${blockers.length && !pivots.length ? '  <-- BLOCKED, fixable' : ''}${mixed}${aliases.length ? `\n      alias resolved: ${aliases.map((r) => `${r.reviewer}: ${r.aliased}`).join('; ')}` : ''}
      ${reviews.map((r) => `sidecar: ${r.sidecarPath}${r.premiseFailure ? ` premise-failure: ${r.premiseFailure}` : ''}${r.alternativesConsidered ? ` alternatives: ${r.alternativesConsidered}` : ''}`).join('\n      ')}
      integration: ${integration ? `${integration.applied} applied, ${(integration.escalated || []).length} escalated -> ${integration.reportPath}` : '(did not run)'}
      escalated ASKs: ${integration && integration.escalated && integration.escalated.length ? integration.escalated.map((e, i) => `escalation-${i + 1}: ${e}`).join('; ') : 'none'}${plan && plan.choicesMade && plan.choicesMade.length ? `
      resolutions (Resolve escalations, planner revising): ${plan.choicesMade.map((c) => `${c.escalationId} -> chosen: ${c.chosen}${c.rejected && c.rejected.length ? `; rejected: ${c.rejected.join(', ')}` : ''}`).join(' | ')}` : ''}`
  })
  .join('\n')

const readiness = await agent(
  `phase: readiness-gate

${ROLE_CONTRACTS['blitz-em']}

You are the blitz-em for plan-blitz wave ${waveIndex}, at its terminal gate. Every plan below was
written, reviewed and integrated without consulting you — that is by design. Your job is to pull
items OUT, over the trail.

Trail directory: ${trailDir}
Gate report this wave was resolved from: ${args.gateReportPath}

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
carry a resolution line beneath them — \`resolutions (Resolve escalations, planner revising)\` —
from a post-integration pass that picked among the reviewer's own enumerated options. Read that
resolution with the SAME priority you give an unresolved ASK: it tells you what was picked and
what was not, not that the question is settled. A \`chosen\` outside the ASK's own stated option
list, or one that does not actually match the plan body, is a finding of its own.

Open the sidecars. A summary line saying OK is not evidence anyone checked — a reviewer can
confirm an author's prose without opening the code that would falsify it. Spot-check one
substantive claim per plan against the tree.

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
const routeById = new Map(decisions.map((d) => [d.batonId, d.route]))
const reviewsById = new Map(chains.filter(Boolean).map(({ baton, reviews }) => [baton.id, reviews]))

// A PIVOT routes MECHANICALLY. The gate brief already says an EM may not override one,
// and a rule only a prompt enforces is discharged by nobody — least of all by the one
// reader with a standing incentive to call a pivoted plan ready, since `ready` is the
// verdict that makes a wave look productive. So the route is reconciled here, over the
// structured review output the wave already holds, and the override is RECORDED rather
// than quiet: `pivotOverride` carries the EM's own verdict into the trail so a
// disagreement stays visible instead of being erased by the thing that corrects it.
const verdicts = ((readiness && readiness.verdicts) || []).map((v) => {
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
return {
  waveIndex,
  trailDir,
  ready: verdicts.filter((v) => v.verdict === 'ready'),
  pulled: verdicts.filter((v) => v.verdict === 'pulled'),
  replan: verdicts.filter((v) => v.verdict === 'replan'),
  surfacedToPm,
  // XS work this wave actually finished, rather than handing back.
  dispatched,
  // Sized and routed, but neither planned nor dispatchable here — including an
  // XS whose EXECUTION gate is shut. Each names the room it belongs in.
  routedElsewhere,
}
