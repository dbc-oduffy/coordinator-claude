/*
 * post-blitz-triage — dispatches the three post-plan-blitz follow-up categories a plan-blitz wave's
 * readiness gate produces: items surfaced to the PM, plans pulled for a named fixable defect, and
 * XS/dispatch batons whose execution gate is open.
 *
 * WHY THIS EXISTS: a plan-blitz sweep's readiness gate sorts every baton into ready / pulled / replan
 * / surfacedToPm / routedElsewhere (see workflows/plan-blitz.mjs). ready and replan feed back into
 * roadmap.blitz_land automatically. The other three categories are where a human — or, per this
 * script, a persona doing the human's first pass — has to actually look. This script is that look,
 * batched.
 *
 * args contract:
 *   {
 *     vpProductItems: [ { id, title, path, question, slug } ],
 *       // one per baton surfacedToPm during a blitz wave. `question` is the blitz-em's original
 *       // surfacedQuestion verbatim; `slug` is a filesystem-safe stem for the output file
 *       // (state/pm-recommendations/<slug>.md) — derive from the baton id/title, caller's choice.
 *     staffEngItems: [ { id, title, path, defect, slug } ],
 *       // one per baton pulled for a named, fixable defect (not XS/dispatch, not a PM question).
 *       // `defect` is the specific defect description from whatever review/gate found it.
 *     executorItems: [ { id, title, path } ],
 *       // one per XS/dispatch baton whose execution gate the caller has ALREADY confirmed is open
 *       // (routedElsewhere entries with a shut execution gate do not belong here — re-check
 *       // roadmap.plan_gate before populating this list, not just the original wave's snapshot).
 *   }
 *
 * Before firing: cross-check every item against a FRESH roadmap.plan_gate read, not the gate-report
 * snapshot the items were originally sorted from — a concurrent plan-blitz run (this repo has had
 * more than one running at once) can resolve, re-plan, or close any of these out from under a stale
 * list. Every persona prompt below re-checks current state itself as a second layer, but a stale
 * caller-side list still wastes a dispatch on work already done elsewhere.
 *
 * Output: writes to disk only (state/pm-recommendations/, plan edits, baton work) — commits nothing.
 * The invoking session reviews the diff and commits, same as landing a plan-blitz wave.
 */

export const meta = {
  name: 'post-blitz-triage',
  description: 'vp-product recommendations on PM-surfaced items, staff-eng investigate + sonnet apply on needs-fix items, executor dispatch on XS items',
  phases: [
    { title: 'VP-Product' },
    { title: 'Staff-Eng Investigate' },
    { title: 'Apply Fix' },
    { title: 'Executor' },
  ],
}

// Model-tier discipline (coordinator-claude/docs/wiki/delegate-execution.md § Model Selection
// Rubric, and staff-eng.md/vp-product.md's own "Do Not Commit"/Tools Policy sections):
//   - Judgment/review personas (vp-product, staff-eng) run OPUS, but their write access is for
//     their OWN findings/recommendation artifact only -- staff-eng.md is explicit: "never change
//     source under review; fixes are the review-integrator's and Executor's job."
//   - Anything that WRITES THE FIX ITSELF runs SONNET, always -- "Dispatched executors are always
//     Sonnet. No exceptions." (delegate-execution.md). So staff-eng INVESTIGATES and reports what
//     needs to change; a separate sonnet pass applies it. Same reasoning nearly makes a two-step
//     out of the XS executor phase too, but those are single-baton direct-dispatch work with no
//     separate reviewer in the loop to begin with, so one sonnet executor per item is correct as is.

const VP_PRODUCT_PREAMBLE = `You are acting as the vp-product persona (coordinator-claude/agents/vp-product.md) —
the VP of Product, software-engineering background. Core question: "Why are we doing this the easy
way instead of the right way?" You stress-test shape, ask the dumb questions, weigh patch-vs-refactor,
and name alternative shapes. Normally your alternatives are "not a winner-pick — the EM/PM choose",
but for THIS dispatch the PM explicitly asked for an actual recommendation they can pick from (not
just neutral alternatives) — end with a clear "I would go with X, because Y" line in addition to the
honest alternatives list.

The PM also told you plainly: "for anything surfaced to me, I'm not sure what's truly my tier to
resolve." So your FIRST job, before any recommendation, is to say whether this genuinely needs a
PM/business-tier call (competing product directions, no engineering-derivable answer, a real tradeoff
between things only the PM values differently) or whether it was over-escalated and is actually an
EM/engineering-tier call — in which case say so plainly AND just make the call yourself rather than
bouncing it back.

You never execute and never commit — you write your recommendation to disk and stop there.`

const staffEngInvestigatePreamble = (slug) => `You are acting as the staff-eng persona (coordinator-claude/agents/staff-eng.md,
nicknamed "Patrik") — uncompromising staff-engineer review. Assume defects exist. For THIS dispatch you
are checking a SPECIFIC previously-identified defect against the CURRENT state of the tree (which may
have changed since it was identified — another concurrent session may have already fixed it, or the
plan may have been superseded).

Per your own doctrine, you INVESTIGATE AND REPORT ONLY — you never edit the plan or artifact under
review yourself; applying a fix is a separate sonnet-tier pass, done after your findings. Write your
findings to state/pm-recommendations/${slug}.staff-eng-findings.md: state plainly whether the defect is
(a) still real and needs the exact fix you'd specify, (b) already resolved/superseded — say by what, or
(c) was never real to begin with. If (a), write the fix precisely enough that a sonnet-tier pass can
apply it verbatim without further judgment calls.`

const APPLY_FIX_PREAMBLE = `You are applying a specific, already-decided fix to a plan document — a typist
task, not a judgment call. A staff-eng review already investigated this and told you exactly what
needs to change. Read its findings file first. If it says the defect is already resolved or was never
real, do nothing and report that. If it specifies a fix, apply EXACTLY that fix to the plan document —
no improvising, no additional changes. You never commit — edit the file, then stop.`

const EXECUTOR_PREAMBLE = `You are acting as the executor persona (coordinator-claude/agents/executor.md) —
"the typist, not the architect." You implement exactly what a baton/spec asks, no inventing, no
improvising. You NEVER commit or stage (git add/commit) — that is the EM's job, done after you finish.
If the baton's execution gate is not actually open, or the work is a "confirm-and-close" with nothing
to change, that is a legitimate complete outcome: verify, record what you verified, and say so rather
than inventing a change to look substantial.`

function vpProduct(item) {
  return agent(
    `${VP_PRODUCT_PREAMBLE}

Baton: ${item.id} — "${item.title}"
Record: ${item.path}
Original PM question raised by the blitz-em: ${item.question}

First, read the baton record AND check whether it's still open — a concurrent plan-blitz run may have
already resolved, re-planned, or closed this baton since the question was raised (check for a
governing_plan, deployment_state, or a newer plan under docs/plans/ dated after this baton's last
update). If it's already resolved, say so plainly and stop — do not manufacture a recommendation for a
question nobody is asking anymore.

Write your findings to state/pm-recommendations/${item.slug}.md (create the directory if needed): a
one-paragraph summary, the PM-tier-vs-EM-tier call stated first, then (if genuinely PM-tier) your
recommendation stated plainly, then the alternatives considered and your reasoning.`,
    { label: `vp-product:${item.id}`, phase: 'VP-Product', model: 'opus', effort: 'low' },
  )
}

function staffEngInvestigate(item) {
  return agent(
    `${staffEngInvestigatePreamble(item.slug)}

Baton: ${item.id} — "${item.title}"
Record: ${item.path}
Previously identified defect: ${item.defect}

Read the plan and the baton's current state first. A concurrent plan-blitz run may have already
superseded or re-planned this baton since the defect was found.`,
    { label: `staff-eng-investigate:${item.id}`, phase: 'Staff-Eng Investigate', model: 'opus', effort: 'low' },
  )
}

function applyFix(item, findingsPath) {
  return agent(
    `${APPLY_FIX_PREAMBLE}

Baton: ${item.id} — "${item.title}"
Staff-eng findings: ${findingsPath}`,
    { label: `apply-fix:${item.id}`, phase: 'Apply Fix', model: 'sonnet', effort: 'low' },
  )
}

function executor(item) {
  return agent(
    `${EXECUTOR_PREAMBLE}

Baton: ${item.id} — "${item.title}"
Record: ${item.path}

Read the baton record in full. It was sized XS/dispatch by a recent plan-blitz sweep — direct work,
no plan needed. Before doing anything, verify its EXECUTION gate is actually open (its blockers are
coded, not just planned) and that it hasn't already been closed by a concurrent session since the
sweep — if either is false, report that plainly and stop rather than inventing work.

If it's genuinely still open: do exactly what the baton asks, nothing more. Report what you changed
(or, for a confirm-and-close baton, what you verified). Do NOT commit or stage anything — the EM
commits after you're done.`,
    { label: `executor:${item.id}`, phase: 'Executor', model: 'sonnet', effort: 'low' },
  )
}

const vpProductItems = args.vpProductItems || []
const staffEngItems = args.staffEngItems || []
const executorItems = args.executorItems || []

log(`post-blitz triage: ${vpProductItems.length} vp-product, ${staffEngItems.length} staff-eng, ${executorItems.length} executor`)

const vpResults = await parallel(vpProductItems.map((item) => () => vpProduct(item).then((r) => ({ item, result: r }))))

// Investigate (Opus, parallel, read-only) -> Apply (Sonnet, per-item, only when a real fix was found).
// Pipelined per item since Investigate must finish before that item's Apply can read its findings,
// but different items are independent, so pipeline() (not a barrier) lets item A's Apply start while
// item B is still investigating.
const staffEngResults = await pipeline(
  staffEngItems,
  (item) => staffEngInvestigate(item).then((r) => ({ item, investigation: r })),
  async ({ item, investigation }) => {
    const findingsPath = `state/pm-recommendations/${item.slug}.staff-eng-findings.md`
    const applied = await applyFix(item, findingsPath)
    return { item, investigation, applied }
  },
)

// Executor phase is PIPELINED (sequential, one at a time) rather than parallel: these agents mutate
// the shared working tree, and running them concurrently risks two agents editing overlapping files
// or racing on the same directories with no isolation.
const executorResults = []
for (const item of executorItems) {
  const r = await executor(item)
  executorResults.push({ item, result: r })
}

return { vpResults, staffEngResults, executorResults }
