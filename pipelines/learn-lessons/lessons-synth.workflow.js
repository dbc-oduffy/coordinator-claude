/**
 * lessons-synth.workflow.js — the single-turn synth leg of the script-first /learn-lessons path.
 *
 * `lessons_mechanical.py prepare` closes what a script can and writes `prepared.json`
 * (`lessons-prepared/1`, see PIPELINE.md); this Workflow sends at most MAX_SYNTH_CALLS tool-less
 * `coordinator:lesson-synth` calls, one per payload, in order, under a `budget_tokens` hard stop;
 * `lessons_mechanical.py finalize` applies the returned verdicts. Nothing here reads or writes a file.
 *
 * Args: { prepared: <prepared.json>, budget_tokens?: <integer> }. `budget_tokens` defaults to
 * prepared.synth.budget_tokens and an arg may only lower it.
 */

export const meta = {
  name: 'lessons-synth',
  description: '/learn-lessons residue synth: at most 3 single-turn no-tool coordinator:lesson-synth calls over prepared payloads, budget_tokens hard stop',
  phases: [
    { title: 'load', detail: 'no agent: args.prepared supplies the payloads, per-call schemas and budget_tokens' },
    { title: 'synth', detail: 'sequential single-turn no-tool coordinator:lesson-synth calls, one per payload, at most 3; before each call spent + estimate + output allowance over budget_tokens stops the run and returns the unsent residue ids' },
  ],
}

const INPUT = typeof args === 'string' ? JSON.parse(args) : args

const MAX_SYNTH_CALLS = 3
const SYNTH_MODEL = (INPUT && INPUT.synthModel) || 'sonnet'
const SYNTH_AGENT_TYPE = 'coordinator:lesson-synth'
// Output tokens one call may add beyond its measured input; the guard reserves it before every send.
const SYNTH_OUTPUT_ALLOWANCE = 16000

// Mirror of verdicts: in coordinator/queue-profiles/lessons.yaml, minus the two a lesson never takes.
const VERDICTS = [
  'discard', 'wiki-append', 'wiki-new', 'dedupe', 'agent-prompt-edit', 'hook-edit', 'script-edit',
  'snippet-sync-update', 'project-structural', 'universal', 'doe-escalation', 'direction-call', 'malformed',
]
const FORBIDDEN_VERDICTS = ['doctrine-edit', 'memory-pointer']

// Pure: estimated input tokens of one payload (its own est_tokens, else ~4 bytes per token).
function estimatePayload(payload) {
  if (payload && Number.isFinite(payload.est_tokens) && payload.est_tokens >= 0) return payload.est_tokens
  return Math.ceil(JSON.stringify(payload || {}).length / 4)
}

// Pure: true when sending one more call would cross the budget.
function wouldCrossBudget(spent, estimate, budget) {
  return spent + estimate + SYNTH_OUTPUT_ALLOWANCE > budget
}

// Pure: the measured total tokens an agent() return carries (cached reads and writes included), or
// null when it carries none.
function measuredTokensOf(ret) {
  if (!ret || typeof ret !== 'object') return null
  const u = ret.usage && typeof ret.usage === 'object' ? ret.usage : ret
  for (const k of ['total_tokens', 'tokens']) {
    if (Number.isFinite(u[k])) return u[k]
  }
  const classes = ['input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens']
  if (classes.some((k) => Number.isFinite(u[k]))) return classes.reduce((n, k) => n + (Number.isFinite(u[k]) ? u[k] : 0), 0)
  return null
}

// Pure: the verdict records of one return (verdicts | records | results array, or a bare array).
function recordsOf(ret) {
  if (Array.isArray(ret)) return ret
  if (!ret || typeof ret !== 'object') return []
  for (const k of ['verdicts', 'records', 'results']) if (Array.isArray(ret[k])) return ret[k]
  return []
}

// Pure: splits one call's records into kept and rejected; a record for an id outside the payload is
// rejected, and a payload id with no kept or rejected record is missing.
function validateRecords(records, ids) {
  const idSet = new Set(ids)
  const kept = []
  const rejected = []
  const answered = new Set()
  for (const r of records) {
    const id = r && typeof r.id === 'string' ? r.id : ''
    let reason = ''
    if (!idSet.has(id)) reason = 'id-not-in-payload'
    else if (FORBIDDEN_VERDICTS.includes(r.verdict)) reason = `forbidden-verdict:${r.verdict}`
    else if (!VERDICTS.includes(r.verdict)) reason = `unknown-verdict:${r.verdict}`
    else if (!Array.isArray(r.cites) || r.cites.length === 0 || r.cites.some((c) => typeof c !== 'string' || c === '')) reason = 'cites-required'
    if (id) answered.add(id)
    if (reason) rejected.push({ id, verdict: r && r.verdict, reason })
    else if (!kept.some((k) => k.id === id)) kept.push({ id, verdict: r.verdict, target: r.target || '', markdown: r.markdown || '', cites: r.cites })
  }
  return { kept, rejected, missing: ids.filter((id) => !answered.has(id)) }
}

function briefFor(payload) {
  return 'Judge each lesson below once, from this prompt alone (no tools, no file read). Return one record per lesson id ' +
    'under `verdicts`, each {id, verdict, target, markdown, cites}; the verdict is one of: ' + VERDICTS.join(', ') +
    '. Never doctrine-edit or memory-pointer. `cites` is required (path:line). A universal row returns `universal`.\n\n' +
    JSON.stringify(payload, null, 2)
}

phase('load')
const PREPARED = INPUT && INPUT.prepared
const SYNTH = PREPARED && PREPARED.synth
if (!SYNTH || !Array.isArray(SYNTH.payloads) || (SYNTH.payloads.length > 0 && !Array.isArray(SYNTH.schemas))) {
  return {
    phase_reached: 'load',
    halted: 'prepared-synth-missing',
    detail: 'lessons-synth: args.prepared.synth carries no payloads or schemas; re-run `lessons_mechanical.py prepare` and pass its prepared.json as args.prepared',
  }
}

const PREPARED_BUDGET = Number.isFinite(SYNTH.budget_tokens) ? SYNTH.budget_tokens : Infinity
const BUDGET = Number.isFinite(INPUT.budget_tokens) ? Math.min(INPUT.budget_tokens, PREPARED_BUDGET) : PREPARED_BUDGET
const idsOf = (payload) => (Array.isArray(payload.lessons) ? payload.lessons : []).map((l) => l.id)
const SENT_PAYLOADS = SYNTH.payloads.slice(0, MAX_SYNTH_CALLS)
const OVERFLOW_IDS = SYNTH.payloads.slice(MAX_SYNTH_CALLS).flatMap(idsOf)

phase('synth')
let spent = 0
let budgetStop = false
let unmeasured = 0
let callsSent = 0
const verdicts = []
const rejected = []
const missingIds = []
const failedCalls = []
const unsentIds = []
for (let i = 0; i < SENT_PAYLOADS.length; i++) {
  const payload = SENT_PAYLOADS[i]
  if (budgetStop || wouldCrossBudget(spent, estimatePayload(payload), BUDGET)) {
    budgetStop = true
    unsentIds.push(...idsOf(payload))
    continue
  }
  callsSent += 1
  const ret = await agent(briefFor(payload), {
    schema: SYNTH.schemas[i],
    agentType: SYNTH_AGENT_TYPE,
    phase: 'synth',
    label: `lesson-synth-${i + 1}`,
    model: SYNTH_MODEL,
  })
  const measured = measuredTokensOf(ret)
  if (measured === null) {
    unmeasured += 1
    spent += estimatePayload(payload) + SYNTH_OUTPUT_ALLOWANCE
  } else {
    spent += measured
  }
  if (!ret) {
    failedCalls.push(`lesson-synth-${i + 1}`)
    missingIds.push(...idsOf(payload))
    continue
  }
  const checked = validateRecords(recordsOf(ret), idsOf(payload))
  verdicts.push(...checked.kept)
  rejected.push(...checked.rejected)
  missingIds.push(...checked.missing)
}

return {
  phase_reached: 'synth',
  budget_stop: budgetStop,
  budget_tokens: Number.isFinite(BUDGET) ? BUDGET : null,
  spent_tokens: spent,
  usage_unmeasured_calls: unmeasured,
  calls_sent: callsSent,
  verdicts,
  rejected,
  missing_ids: missingIds,
  failed_calls: failedCalls,
  unsent_ids: unsentIds,
  deferred_ids: [...(Array.isArray(PREPARED.deferred_ids) ? PREPARED.deferred_ids : []), ...OVERFLOW_IDS],
}
