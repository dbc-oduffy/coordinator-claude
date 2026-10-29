/*
 * Dispatches the three post-plan-blitz follow-up categories a plan-blitz wave verdict produces: items
 * surfaced to the PM, plans pulled for a named fixable defect, and XS/dispatch batons whose
 * execution gate is open. `ready` and `replan` batons feed back into roadmap.blitz_land
 * automatically; these three categories need a human (or a persona doing the human's first pass)
 * to actually look.
 *
 * args contract:
 *   {
 *     vpProductItems: [ { id, title, path, question, slug } ],
 *       // one per baton surfacedToPm during a blitz wave. `question` is the blitz-em's original
 *       // surfacedQuestion verbatim; `slug` is a filesystem-safe stem for the output file
 *       // (state/pm-recommendations/<slug>.md).
 *     staffEngItems: [ { id, title, path, defect, slug } ],
 *       // one per baton pulled for a named, fixable defect (not XS/dispatch, not a PM question).
 *     executorItems: [ { id, title, path } ],
 *       // one per XS/dispatch baton whose execution gate the caller has already confirmed is
 *       // open (routedElsewhere entries with a shut execution gate do not belong here).
 *   }
 *
 * Before firing: cross-check every item against a fresh roadmap.plan_gate read, not the
 * gate-report snapshot the items were originally sorted from -- a concurrent plan-blitz run can
 * resolve, re-plan, or close any of these out from under a stale list. Every persona prompt below
 * re-checks current state itself as a second layer, but a stale caller-side list still wastes a
 * dispatch on work already done elsewhere.
 *
 * Output: writes to disk only (state/pm-recommendations/, plan edits, baton work) -- commits
 * nothing. The invoking session reviews the diff and commits.
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


// Model-tier discipline (coordinator/docs/wiki/dispatching-parallel-agents/delegate-execution.md § Model Selection
// Rubric, and staff-eng.md/vp-product.md's own "Do Not Commit"/Tools Policy sections):
//   - Judgment/review personas (vp-product, staff-eng) run SONNET, and their write access is for
//     their OWN findings/recommendation artifact only -- staff-eng.md is explicit: "never change
//     source under review; fixes are the Executor's job."
//   - Anything that WRITES THE FIX ITSELF runs SONNET, always -- "Dispatched executors are always
//     Sonnet. No exceptions." (delegate-execution.md). So staff-eng INVESTIGATES and reports what
//     needs to change; a separate sonnet pass applies it. Same reasoning nearly makes a two-step
//     out of the XS executor phase too, but those are single-baton direct-dispatch work with no
//     separate reviewer in the loop to begin with, so one sequential sonnet executor covers them all.
// Items are batched per agent (JUDGMENT_BATCH for the judgment legs); every agent returns PATH_SUMMARY.


const VP_PRODUCT_PREAMBLE = `You are acting as the vp-product persona (coordinator/agents/vp-product.md) —
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

const staffEngInvestigatePreamble = (slug) => `You are acting as the staff-eng persona (coordinator/agents/staff-eng.md,
nicknamed "the Staff Engineer") — uncompromising staff-engineer review. Assume defects exist. For THIS dispatch you
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

const EXECUTOR_PREAMBLE = `You are acting as the executor persona (coordinator/agents/executor.md) —
"the typist, not the architect." You implement exactly what a baton/spec asks, no inventing, no
improvising. You NEVER commit or stage (git add/commit) — that is the EM's job, done after you finish.
If the baton's execution gate is not actually open, or the work is a "confirm-and-close" with nothing
to change, that is a legitimate complete outcome: verify, record what you verified, and say so rather
than inventing a change to look substantial.`

const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

const OBJECTIVE_RULE = `When state/warp/<run_id>/objective.json exists, read it first and carry its axes; never report "unknown".`

const JUDGMENT_BATCH = 5

const itemList = (items, fmt) => items.map((it, i) => `${i + 1}. ${fmt(it)}`).join('\n')

// One agent per batch of PM-surfaced items; each item's recommendation still lands in its own file.
function vpProductBatch(batch, n) {
  return agent(
    pathSummary(`${VP_PRODUCT_PREAMBLE}

${MID_RUN_DIRECTION_RULE}
${OBJECTIVE_RULE}

You have ${batch.length} independent batons. Handle each in turn, in full, as its own recommendation.

${itemList(batch, (item) => `Baton: ${item.id} — "${item.title}"
   Record: ${item.path}
   Original PM question raised by the blitz-em: ${item.question}
   Output file: state/pm-recommendations/${item.slug}.md`)}

For each: first read the baton record AND check whether it's still open — a concurrent plan-blitz run may have
already resolved, re-planned, or closed this baton since the question was raised (check for a
governing_plan, deployment_state, or a newer plan under docs/plans/ dated after this baton's last
update). If it's already resolved, say so plainly and stop on that item — do not manufacture a recommendation for a
question nobody is asking anymore.

Write each baton's findings to its output file (create the directory if needed): a
one-paragraph summary, the PM-tier-vs-EM-tier call stated first, then (if genuinely PM-tier) your
recommendation stated plainly, then the alternatives considered and your reasoning.
Your returned path is an index file listing each baton id with its output file; counts carries pmTier, emTier, resolved.`),
    { label: `vp-product:${n}`, phase: 'VP-Product', model: TIER.SONNET, effort: 'low', schema: PATH_SUMMARY_SCHEMA },
  )
}

// One agent per batch of defects. Findings stay one file per item (the Apply pass reads them).
function staffEngInvestigateBatch(batch, n) {
  return agent(
    pathSummary(`${staffEngInvestigatePreamble('<slug>')}

(Substitute each item's own slug below for <slug> in the findings path.)

${MID_RUN_DIRECTION_RULE}
${OBJECTIVE_RULE}

You have ${batch.length} independent batons. Investigate each in turn.

${itemList(batch, (item) => `Baton: ${item.id} — "${item.title}"
   Record: ${item.path}
   Previously identified defect: ${item.defect}
   Findings file: state/pm-recommendations/${item.slug}.staff-eng-findings.md`)}

Read the plan and each baton's current state first. A concurrent plan-blitz run may have already
superseded or re-planned a baton since the defect was found.
Your returned path is an index file listing each baton id with its findings file and verdict (a/b/c);
counts carries needsFix (verdict a), resolved, neverReal.`),
    { label: `staff-eng-investigate:${n}`, phase: 'Staff-Eng Investigate', model: TIER.SONNET, effort: 'low', schema: PATH_SUMMARY_SCHEMA },
  )
}

// Only fires for a batch whose investigation reported at least one finding that names a fix.
function applyFixBatch(batch, indexPath, n) {
  return agent(
    pathSummary(`${APPLY_FIX_PREAMBLE}

${MID_RUN_DIRECTION_RULE}
${OBJECTIVE_RULE}

Investigation index: ${indexPath}
Apply a fix ONLY to batons whose findings file specifies one; skip the rest without comment.

${itemList(batch, (item) => `Baton: ${item.id} — "${item.title}"
   Staff-eng findings: state/pm-recommendations/${item.slug}.staff-eng-findings.md`)}

Your returned path is an index of what you applied; counts carries applied, skipped.`),
    { label: `apply-fix:${n}`, phase: 'Apply Fix', model: TIER.SONNET, effort: 'low', schema: PATH_SUMMARY_SCHEMA },
  )
}

// One sequential agent per batch of XS batons (batches also run one after another): the batons mutate
// the shared tree, so they never run concurrently.
function executorBatch(items, n) {
  return agent(
    pathSummary(`${EXECUTOR_PREAMBLE}

${MID_RUN_DIRECTION_RULE}
${OBJECTIVE_RULE}

You have ${items.length} batons. Work them strictly ONE AT A TIME, in order, finishing each before the next.

${itemList(items, (item) => `Baton: ${item.id} — "${item.title}"
   Record: ${item.path}`)}

Each was sized XS/dispatch by a recent plan-blitz sweep — direct work,
no plan needed. Before doing anything on a baton, verify its EXECUTION gate is actually open (its blockers are
coded, not just planned) and that it hasn't already been closed by a concurrent session since the
sweep — if either is false, record that plainly and move on rather than inventing work.

If it's genuinely still open: do exactly what the baton asks, nothing more. Record what you changed
(or, for a confirm-and-close baton, what you verified). Do NOT commit or stage anything — the EM
commits after you're done.
Your returned path is a report file with one section per baton; counts carries done, confirmedClosed, skipped.`),
    { label: `executor:${n}`, phase: 'Executor', model: TIER.SONNET, effort: 'low', schema: PATH_SUMMARY_SCHEMA },
  )
}

const vpProductItems = args.vpProductItems || []
const staffEngItems = args.staffEngItems || []
const executorItems = args.executorItems || []

log(`post-blitz triage: ${vpProductItems.length} vp-product, ${staffEngItems.length} staff-eng, ${executorItems.length} executor`)

const vpResults = await parallel(
  batchItems(vpProductItems, { maxPerAgent: JUDGMENT_BATCH }).map((batch, i) => () =>
    vpProductBatch(batch, i + 1).then((r) => ({ items: batch, result: r }))),
)

// Investigate (Sonnet, parallel, read-only) -> Apply (Sonnet), pipelined per batch. Apply runs only when the
// batch's investigation counted at least one finding that names a fix.
const staffEngResults = await pipeline(
  batchItems(staffEngItems, { maxPerAgent: JUDGMENT_BATCH }).map((batch, i) => ({ batch, n: i + 1 })),
  ({ batch, n }) => staffEngInvestigateBatch(batch, n).then((r) => ({ batch, n, investigation: r })),
  async ({ batch, n, investigation }) => {
    const needsFix = investigation && investigation.counts ? investigation.counts.needsFix : undefined
    if (!investigation || !investigation.path || needsFix === 0) return { items: batch, investigation, applied: null }
    const applied = await applyFixBatch(batch, investigation && investigation.path, n)
    return { items: batch, investigation, applied }
  },
)

// Executor phase is sequential, at most 10 batons per agent: the batons mutate the shared working
// tree, and concurrent agents risk editing overlapping files with no isolation.
const executorResults = []
for (const [i, batch] of batchItems(executorItems).entries()) executorResults.push(await executorBatch(batch, i + 1))

return { vpResults, staffEngResults, executorResults }
