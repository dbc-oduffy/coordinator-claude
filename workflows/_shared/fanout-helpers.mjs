// Canonical fan-out helpers. Workflow scripts cannot import, so this block is spliced into each
// in-scope script by coordinator/bin/workflow-shared-sync.py. Edit it HERE only.
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
