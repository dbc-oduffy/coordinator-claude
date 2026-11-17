/**
 * lessons-triage.workflow.js — the learn-lessons triage leg: at most MAX_SYNTH_CALLS single-turn,
 * no-tool triage calls over `lessons_mechanical.py prepare` payloads, each followed by one refute
 * call, under a measured hard token budget.
 *
 * The stop is pre-admission: a single admitted call whose real usage exceeds its projection can end
 * spend over budget_tokens by that overrun; the next admit() then refuses everything after it.
 * Every call passes the admit() gate first: measured spend plus the call's projected cost must fit
 * args.budget_tokens, else the call is not made and its rows are handed back `budget-exhausted`.
 * Spend is the call's reported usage input+output; a result without usage is charged twice its
 * projection and flagged unmeasured, never zero. The two mechanical legs (prepare, finalize) run
 * outside; this script only returns `synth_results` and `budget_ledger` for the driver to save as
 * <run_dir>/synth-results.json and <run_dir>/budget-ledger.json.
 *
 * Mirrors lessons_contract.BudgetLedger and TRIAGE_SCHEMA (the schema arrives in args.prepared.synth).
 */

export const meta = {
  name: 'lessons-triage',
  description: '/learn-lessons triage: <=3 single-turn no-tool Sonnet triage calls, each followed by one refute call, under a measured hard token budget',
  phases: [
    { title: 'load', detail: 'no agent: args.prepared (the inline payload `lessons_mechanical.py prepare` writes) supplies synth.payloads and synth.schema; args.budget_tokens (default 600000) is the hard cap' },
    { title: 'triage', detail: 'one single-turn no-tool Sonnet call per payload in sequence, each admitted only while measured spend + projected cost <= budget_tokens' },
    { title: 'refute', detail: 'one single-turn no-tool Sonnet call per admitted triage batch, same ledger and admit() gate; a batch whose refute is refused hands its rows back budget-exhausted' },
  ],
}

const INPUT = typeof args === 'string' ? JSON.parse(args) : args
const PREPARED = (INPUT && INPUT.prepared) || null

const MAX_SYNTH_CALLS = 3
const DEFAULT_BUDGET = 600000
const CHECKPOINT_PERCENTS = [25, 50, 75]
const TRIAGE_OUTPUT_TOKENS_PER_LESSON = 250
const REFUTE_OUTPUT_TOKENS_PER_LESSON = 120
const MODEL = 'sonnet'
const AGENT_TYPE = 'coordinator:distill-synth'

const REFUTE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'verdict', 'reason'],
        properties: {
          id: { type: 'string', minLength: 1 },
          verdict: { type: 'string', enum: ['upheld', 'overturned'] },
          reason: { type: 'string' },
        },
      },
    },
  },
}

// Pure: 4 bytes per token, rounded up; text is measured as UTF-8 bytes.
function estimateTokens(text) {
  const s = typeof text === 'string' ? text : JSON.stringify(text)
  let bytes = 0
  for (const ch of s) {
    const c = ch.codePointAt(0)
    bytes += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4
  }
  return Math.ceil(bytes / 4)
}

// Pure: the measured input+output of a usage block, or null when either side is absent.
function measuredTotal(usage) {
  if (!usage || typeof usage !== 'object') return null
  const side = (snake, camel) => {
    const v = usage[snake] !== undefined ? usage[snake] : usage[camel]
    return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null
  }
  const input = side('input_tokens', 'inputTokens')
  const output = side('output_tokens', 'outputTokens')
  return input === null || output === null ? null : input + output
}

// Pure: splits an agent() return into its schema value and usage. The schemas forbid extra keys, so a
// `usage` key is never model data.
function unwrap(ret) {
  if (ret && typeof ret === 'object' && !Array.isArray(ret) && 'usage' in ret) {
    const { usage, result, ...rest } = ret
    return { usage, value: result !== undefined ? result : rest }
  }
  return { usage: null, value: ret }
}

// Hard token stop: admit() refuses a call whose projected cost would push measured spend past the budget.
class BudgetLedger {
  constructor(budgetTokens) {
    this.budget_tokens = budgetTokens
    this.spent = 0
    this.calls = 0
    this.unmeasured = 0
    this.checkpoints = []
    this.checkpoint_lines = []
    this.refused = []
  }
  get remaining() { return Math.max(this.budget_tokens - this.spent, 0) }
  admit(projected, label) {
    const ok = this.spent + projected <= this.budget_tokens
    if (!ok) this.refused.push({ label, projected, spent: this.spent })
    return ok
  }
  record(usage, projected) {
    let total = measuredTotal(usage)
    if (total === null) {
      total = 2 * projected
      this.unmeasured += 1
    }
    this.spent += total
    this.calls += 1
    if (this.budget_tokens > 0) {
      const pct = (100 * this.spent) / this.budget_tokens
      for (const mark of CHECKPOINT_PERCENTS) {
        if (pct >= mark && !this.checkpoints.includes(mark)) {
          this.checkpoints.push(mark)
          this.checkpoint_lines.push(`${mark}% checkpoint: ${this.spent}/${this.budget_tokens} tokens spent after ${this.calls} call(s)`)
        }
      }
    }
    return total
  }
  toDict() {
    return {
      budget_tokens: this.budget_tokens,
      spent: this.spent,
      remaining: this.remaining,
      calls: this.calls,
      unmeasured_calls: this.unmeasured,
      checkpoints: [...this.checkpoints],
      checkpoint_lines: [...this.checkpoint_lines],
      refused: [...this.refused],
    }
  }
}

// Pure: the lesson ids a payload carries, in order.
function payloadIds(payload) {
  const rows = payload && (Array.isArray(payload.lessons) ? payload.lessons : Array.isArray(payload.rows) ? payload.rows : null)
  if (rows) return rows.map((r) => (r && typeof r === 'object' ? r.id : r)).filter((id) => typeof id === 'string' && id)
  return Array.isArray(payload && payload.ids) ? payload.ids.filter((id) => typeof id === 'string' && id) : []
}

function triageBriefFor(payload) {
  return `You are the single-turn triage step of /learn-lessons. You have no tools: do not read, ` +
    `search or run anything. Everything you may use is in the payload below; any path in it is a ` +
    `citation, never something to open.

Return the schema object: exactly one verdicts[] entry per lesson id in the payload, id copied ` +
    `exactly, verdict one of the schema's enum, target the wiki page or file the verdict acts on ('' ` +
    `when none), evidence one sentence citing the payload, tests the test names a code-edit verdict ` +
    `needs ([] otherwise). A lesson you cannot judge from the payload is left out of verdicts, never guessed.

Payload:
${JSON.stringify(payload)}
`
}

function refuteBriefFor(payload, verdicts) {
  return `You are the single-turn refute step of /learn-lessons, the adversarial check on a triage. ` +
    `You have no tools: do not read, search or run anything. For each verdict below, try to refute it ` +
    `from its lesson's text in the payload: a verdict the lesson does not support, a target the lesson ` +
    `does not name, or a close the evidence does not justify is 'overturned'; otherwise 'upheld'.

Return the schema object: exactly one verdicts[] entry {id, verdict, reason} per verdict below, id ` +
    `copied exactly.

Lessons:
${JSON.stringify(payload)}

Verdicts to refute:
${JSON.stringify(verdicts)}
`
}

function haltOf(halted, detail) {
  return { phase_reached: 'load', halted, detail }
}

const rawBudget = INPUT && INPUT.budget_tokens !== undefined ? INPUT.budget_tokens : PREPARED && PREPARED.budget_tokens
const BUDGET = rawBudget === undefined || rawBudget === null ? DEFAULT_BUDGET : rawBudget

if (!PREPARED || typeof PREPARED !== 'object' || Array.isArray(PREPARED)) {
  return haltOf('prepared-missing', 'lessons-triage: args.prepared must be the parsed prepared.json object')
}
if (typeof BUDGET !== 'number' || !Number.isFinite(BUDGET) || BUDGET < 0) {
  return haltOf('invalid-budget', `lessons-triage: budget_tokens must be a non-negative number, got ${JSON.stringify(BUDGET)}`)
}
phase('load')
const SYNTH = PREPARED.synth
if (!SYNTH || !Array.isArray(SYNTH.payloads) || !SYNTH.schema) {
  return haltOf('synth-payloads-missing', 'lessons-triage: args.prepared.synth needs payloads[] and schema')
}

const ledger = new BudgetLedger(Math.floor(BUDGET))
const PAYLOADS = SYNTH.payloads.slice(0, MAX_SYNTH_CALLS)
const handedBack = []
const synthResults = []
const handBack = (ids, reason) => { for (const id of ids) handedBack.push({ id, reason }) }

for (const overflow of SYNTH.payloads.slice(MAX_SYNTH_CALLS)) handBack(payloadIds(overflow), 'deferred-over-cap')

let exhausted = false
for (let i = 0; i < PAYLOADS.length; i++) {
  const payload = PAYLOADS[i]
  const ids = payloadIds(payload)
  const batchId = (payload && payload.batch_id) || `batch-${String(i + 1).padStart(2, '0')}`
  if (exhausted) {
    handBack(ids, 'budget-exhausted')
    synthResults.push({ batch_id: batchId, ids, status: 'budget-exhausted', triage: null, refute: null })
    continue
  }

  phase('triage')
  const triageBrief = triageBriefFor(payload)
  const triageProjected = estimateTokens(triageBrief) + TRIAGE_OUTPUT_TOKENS_PER_LESSON * ids.length
  if (!ledger.admit(triageProjected, `triage-${i + 1}`)) {
    exhausted = true
    log(`triage-${i + 1}: refused, projected ${triageProjected} tokens would pass budget ${ledger.budget_tokens} (spent ${ledger.spent})`)
    handBack(ids, 'budget-exhausted')
    synthResults.push({ batch_id: batchId, ids, status: 'budget-exhausted', triage: null, refute: null })
    continue
  }
  const triageRet = await agent(triageBrief, {
    schema: SYNTH.schema, agentType: AGENT_TYPE, phase: 'triage', label: `triage-${i + 1}`, model: MODEL,
  })
  const triage = unwrap(triageRet)
  ledger.record(triage.usage, triageProjected)
  if (!triage.value || !Array.isArray(triage.value.verdicts)) {
    handBack(ids, 'triage-failed')
    synthResults.push({ batch_id: batchId, ids, status: 'triage-failed', triage: null, refute: null })
    continue
  }

  phase('refute')
  const refuteBrief = refuteBriefFor(payload, triage.value.verdicts)
  const refuteProjected = estimateTokens(refuteBrief) + REFUTE_OUTPUT_TOKENS_PER_LESSON * triage.value.verdicts.length
  if (!ledger.admit(refuteProjected, `refute-${i + 1}`)) {
    exhausted = true
    log(`refute-${i + 1}: refused, projected ${refuteProjected} tokens would pass budget ${ledger.budget_tokens} (spent ${ledger.spent})`)
    handBack(ids, 'budget-exhausted')
    synthResults.push({ batch_id: batchId, ids, status: 'budget-exhausted', triage: triage.value, refute: null })
    continue
  }
  const refuteRet = await agent(refuteBrief, {
    schema: REFUTE_SCHEMA, agentType: AGENT_TYPE, phase: 'refute', label: `refute-${i + 1}`, model: MODEL,
  })
  const refute = unwrap(refuteRet)
  ledger.record(refute.usage, refuteProjected)
  if (!refute.value || !Array.isArray(refute.value.verdicts)) {
    handBack(ids, 'refute-failed')
    synthResults.push({ batch_id: batchId, ids, status: 'refute-failed', triage: triage.value, refute: null })
    continue
  }
  synthResults.push({ batch_id: batchId, ids, status: 'refuted', triage: triage.value, refute: refute.value })
}

for (const line of ledger.checkpoint_lines) log(line)
for (const d of Array.isArray(PREPARED.deferred) ? PREPARED.deferred : []) {
  const id = d && typeof d === 'object' ? d.id : d
  if (typeof id === 'string' && id) handedBack.push({ id, reason: 'deferred' })
}

return {
  phase_reached: 'triage-complete',
  run_id: PREPARED.runId || (INPUT && INPUT.runId) || null,
  synth_results: synthResults,
  handed_back: handedBack,
  budget_ledger: ledger.toDict(),
  calls: ledger.calls,
}
