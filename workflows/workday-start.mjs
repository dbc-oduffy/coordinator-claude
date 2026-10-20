/*
 * Ceremony-neutral template for the engine's `<ceremony>-run launch|finish` runners. The engine
 * binds it (workflow.bind_args prepends the `args` binding {digest, repoRoot}) for workday-start,
 * workday-complete and workweek-start alike, so it enumerates no group id: it runs
 * args.digest.agent_work.groups in ascending `phase` and dispatches each entry on its own fields
 * (`agent`, `ruling_agent`, `argv`, `brief`, `inputs`). The last phase writes the collected results
 * to <repoRoot>/scratch/ceremony-runs/<run_id>/agent-results.json and runs digest.finish_argv with
 * `--agent-results` itself, so no EM-held step sits between the agents and finish.
 *
 * Ordering: an entry whose inputs.depends_on names another entry key in its group is dispatched
 * only after that entry settles (needs-ruling pass included); if the predecessor failed, the
 * dependant is recorded failed ("dependency <key> did not complete") and never dispatched. A
 * depends_on naming no entry in the group, or forming a cycle, is logged and ignored. Independent
 * entries and separate chains run in parallel.
 *
 * Disposal: an entry with inputs.memos and no predecessor roots a chain (it and its transitive
 * dependants). Staged entries (inputs.stage) get no inbox rules and never edit a memo. When every
 * entry of the chain settles non-failed, one `dispose:` agent disposes the root's memos from the
 * verified report and returns what it closed; those merge into the root's result `memos`. No
 * result key is added beyond the digest's entry keys.
 *
 * Contract: coordinator_core/contract/ceremony-run-digest.schema.json. digest.chained is not run
 * here; the log notes its presence.
 *
 * Every agent carries model: (a guard requires the tier on a workflow worker).
 */

export const meta = {
  name: 'workday-start',
  description: 'Ceremony run: dispatch each digest agent group by its fields, collect results, run finish',
  phases: [
    { title: 'Work', detail: 'one agent per digest entry, groups in ascending phase' },
    { title: 'Rule', detail: 'needs-ruling results go to the group ruling_agent' },
    { title: 'Finish', detail: 'write agent-results.json and run digest.finish_argv' },
  ],
}

const digest = args && args.digest
if (!digest || !digest.agent_work || !Array.isArray(digest.agent_work.groups) || !digest.run_id || !Array.isArray(digest.finish_argv)) {
  throw new Error('workday-start: args.digest (run_id, finish_argv, agent_work.groups) is required')
}
const norm = p => String(p).replace(/\\/g, '/').replace(/\/+$/, '')
if (!args.repoRoot && !digest.repo_root) {
  throw new Error('workday-start: args.repoRoot or digest.repo_root is required')
}
const repoRoot = norm(args.repoRoot || digest.repo_root)

const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

const LAUNCHER = 'Run every coordinator CLI through its settings-home launcher by absolute path, never as a bareword: on a POSIX shell "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/<cli>"; on PowerShell first `if (-not $env:COORDINATOR_SETTINGS_HOME) { $env:COORDINATOR_SETTINGS_HOME = Join-Path ($env:CLAUDE_HOME ?? $HOME) ".coordinator-claude-settings" }` then `& "$env:COORDINATOR_SETTINGS_HOME\\bin\\<cli>.exe"`.'

const COMMON = `You are one worker in a ceremony run (${digest.ceremony || 'ceremony'}, run ${digest.run_id}) in the repo at ${repoRoot}. Work from that directory. ${LAUNCHER} Commits: scoped explicit-file pathspecs only (never git add -A / . / commit -a), no destructive git ops, and run no test suite. Return exactly one result object for the entry you were given, with its key verbatim.`

const WORK_COMMON = `${COMMON}\n\n${MID_RUN_DIRECTION_RULE}`

const DECISION_RULE = `Result contract: outcome is a short word for what happened. When the entry's inputs carry a judgment point record with offered dispositions, set decision to {disposition, rationale} with disposition exactly one of the offered values; surface_to_pm and pm_reviews_manually are refused by the schema, never use them. When you cannot decide, return outcome "needs-ruling" with question and options (the group's ruling agent answers); never hand a decision to a person.`

const INBOX_RULES = `Inbox rules (the entry lists memos in its inputs). Every open memo is triaged, verified and disposed of in this run, however many steps that takes; disposal means closed, or routed into a baton and then closed. A baton is a disposal, not a deferral. Verify with two checks on top of the brief: (1) already-answered, not just accurate: glob state/cross-repo/archive/, state/memo-outbox/sent/ and the completions record, and git log on sender and receiver repos, for a later memo, resend or commit that discharges the ask; a discharged ask is closed whatever its body says. (2) absence is only evidence from the right directory: name the directory you looked in before reporting anything missing; a manifest is a snapshot, so re-enumerate the inbox directory before disposing and take memos that arrived after it. Disposal mechanics: \`archive-stamp-cli resolve-memo <memo> --decision accepted --decision-note "<why>" --realized-by "<baton or inline or sha>" --in-repo-capture "<baton>"\` takes exactly ONE memo per call (a list is refused or silently resolves the first), stamps and commits in place, and never moves the file; --realized-by needs 'inline', a path containing /, or a hex SHA. Then move the file into the repo's existing archive layout (state/cross-repo/archive/<YYYY-MM>/ only if that layout exists; many repos are flat) with plain mv, then git add the explicit old and new paths and commit with explicit file pathspecs, never a directory. Helper scripts go to the scratchpad via the Write tool. Routing: anything inside an active handoff's scope gets a routing note ("## Routed from inbox triage (<date>)") appended and committed, then is closed; all XS/S items from this run bundle into ONE baton, never one each; plan-weight items get one baton per problem space; engine items go by memo (cross-repo-memo draft) to the engine repo's EM, then close. Tripwires: SMALL-BLITZ-ITEMS-BUNDLE-INTO-ONE-BATON, AN-ANSWERED-ASK-IS-CLOSED-WHATEVER-ITS-BODY-SAYS, A-VERIFY-PASS-THAT-SKIPS-THE-ARCHIVE-CONFIRMS-A-DEAD-ASK, A-BLITZ-THAT-LEAVES-MEMOS-UNTRIAGED-DID-NOT-RUN. Your result MUST list in memos every memo path you closed out.`

const RESULT = {
  type: 'object',
  properties: {
    key: { type: 'string' },
    outcome: { type: 'string' },
    commit: { type: ['string', 'null'] },
    decision: {
      anyOf: [
        { type: 'null' },
        { type: 'object', properties: { disposition: { type: 'string' }, rationale: { type: 'string' }, payload: { type: ['object', 'null'] } }, required: ['disposition', 'rationale'] },
      ],
    },
    question: { type: ['string', 'null'] },
    options: { type: ['array', 'null'], items: { type: 'string' } },
    memos: { type: ['array', 'null'], items: { type: 'string' } },
  },
  required: ['key', 'outcome'],
}
const FINISH = {
  type: 'object',
  properties: { finish_exit: { type: 'number' }, stdout: { type: 'string' } },
  required: ['finish_exit', 'stdout'],
}

const hasMemos = e => !!(e.inputs && Array.isArray(e.inputs.memos) && e.inputs.memos.length)
const entryBlock = (g, e) => `Group ${g.id}. Group inputs:\n${JSON.stringify(g.inputs || {})}\n\nEntry key: ${e.key}\nEntry inputs:\n${JSON.stringify(e.inputs || {})}`

const dispatch = (g, e) => {
  if (g.agent && e.brief) {
    return agent(`${WORK_COMMON}\n\n${DECISION_RULE}${hasMemos(e) && !(e.inputs && e.inputs.stage) ? `\n\n${INBOX_RULES}` : ''}\n\nBrief (verbatim):\n${e.brief}\n\n${entryBlock(g, e)}`, { label: `work:${g.id}:${e.key}`, phase: 'Work', schema: RESULT, agentType: g.agent, model: 'sonnet' })
  }
  if (Array.isArray(e.argv) && e.argv.length) {
    return agent(`${COMMON}\n\nRun this argv verbatim through the launcher for its first element (the CLI), with the remaining elements as its arguments, from the repo root:\n${JSON.stringify(e.argv)}\n\nReturn outcome "ok" when it exits 0, otherwise "failed" with the exit code and the last lines of its output in question.\n\n${entryBlock(g, e)}`, { label: `run-argv:${g.id}:${e.key}`, phase: 'Work', schema: RESULT, model: 'sonnet' })
  }
  return agent(`${COMMON}\n\nRead the files named in the entry inputs and report what they show in one short outcome string; change nothing.\n\n${entryBlock(g, e)}`, { label: `report:${g.id}:${e.key}`, phase: 'Work', schema: RESULT, model: 'sonnet' })
}

const rule = (g, e, r) => agent(`${WORK_COMMON}\n\n${DECISION_RULE}\n\nA worker returned needs-ruling for this entry. Decide it yourself and return the entry's final result (same key), with decision set from the offered options; never return needs-ruling again and never defer to a person.\n\nWorker result:\n${JSON.stringify(r)}\n\n${entryBlock(g, e)}`, { label: `rule:${g.id}:${e.key}`, phase: 'Rule', schema: RESULT, agentType: g.ruling_agent, model: 'sonnet' })

const dispose = (g, root, chain) => agent(`${WORK_COMMON}\n\n${DECISION_RULE}\n\n${INBOX_RULES}\n\nDispose step. The triage and verify agents of this memo chain have settled and none of them may edit a memo; you are the only stage that disposes. Dispose each memo in the entry's inputs.memos per the verified report at inputs.report_path (read it first, and the chain's settled results below), re-enumerate the inbox directory before you finish, and return in memos every memo path you closed. Return the root entry's key verbatim.\n\nChain results:\n${JSON.stringify(chain)}\n\n${entryBlock(g, root)}`, { label: `dispose:${g.id}:${root.key}`, phase: 'Work', schema: RESULT, agentType: g.agent, model: 'sonnet' })

const settleEntry = async (g, e) => {
  const r = await dispatch(g, e)
  const ruled = r && r.outcome === 'needs-ruling' && g.ruling_agent ? await rule(g, e, r) : r
  return { outcome: 'failed', ...(ruled || {}), key: e.key }
}

const runGroup = async g => {
  const entries = g.entries || []
  const byKey = new Map(entries.map(e => [e.key, e]))
  const waitsOn = new Map()
  for (const e of entries) {
    const d = e.inputs && e.inputs.depends_on
    if (d === undefined || d === null) continue
    let cur = d, hops = 0
    while (cur && cur !== e.key && byKey.has(cur) && hops++ <= entries.length) {
      const n = byKey.get(cur).inputs && byKey.get(cur).inputs.depends_on
      cur = typeof n === 'string' ? n : null
    }
    if (typeof d === 'string' && byKey.has(d) && d !== e.key && cur !== e.key) waitsOn.set(e.key, d)
    else log(`depends_on ${JSON.stringify(d)} of ${e.key} names no usable entry in group ${g.id}; dispatching it with no predecessor`)
  }
  const runs = new Map()
  const run = e => {
    if (!runs.has(e.key)) {
      runs.set(e.key, (async () => {
        const p = waitsOn.get(e.key)
        if (p) {
          const pr = await run(byKey.get(p))
          if (!pr || pr.outcome === 'failed') return { key: e.key, outcome: 'failed', question: `dependency ${p} did not complete` }
        }
        return settleEntry(g, e)
      })())
    }
    return runs.get(e.key)
  }
  const chainOf = root => {
    const members = [root]
    for (const m of members) for (const e of entries) if (waitsOn.get(e.key) === m.key && !members.includes(e)) members.push(e)
    return members
  }
  const roots = entries.filter(e => hasMemos(e) && !waitsOn.has(e.key))
  const closedBy = new Map()
  const disposeChain = async root => {
    const members = chainOf(root)
    const results = await Promise.all(members.map(run))
    if (results.some(r => !r || r.outcome === 'failed')) { log(`chain ${root.key} in group ${g.id} has a failed member; its memos are not disposed`); return }
    const d = await dispose(g, root, results)
    if (d && d.outcome !== 'failed' && Array.isArray(d.memos)) closedBy.set(root.key, d.memos)
    else log(`dispose of chain ${root.key} in group ${g.id} closed no memos`)
  }
  await parallel([...entries.map(e => () => run(e)), ...roots.map(r => () => disposeChain(r))])
  const settled = await Promise.all(entries.map(run))
  return settled.map(r => {
    const closed = closedBy.get(r.key)
    return closed ? { ...r, memos: [...new Set([...(r.memos || []), ...closed])] } : r
  })
}

const collected = {}
const groups = [...digest.agent_work.groups].sort((a, b) => a.phase - b.phase)
for (const g of groups) collected[g.id] = await runGroup(g)
if (digest.chained) log('digest.chained present; the template does not run it')

const resultsPath = `${repoRoot}/scratch/ceremony-runs/${digest.run_id}/agent-results.json`
const fin = await agent(`${COMMON}\n\nFinish phase. (1) With the Write tool, write this JSON to ${resultsPath} exactly (create the directory first if absent):\n${JSON.stringify({ groups: collected })}\n\n(2) Run the finish argv through the launcher for its first element (the CLI), with the remaining elements as arguments, followed by --agent-results ${resultsPath}, from the repo root. finish_argv:\n${JSON.stringify(digest.finish_argv)}\n\nReturn finish_exit (its exit code) and stdout (its standard output verbatim, the briefing).`, { label: 'finish:run', phase: 'Finish', schema: FINISH, model: 'sonnet' })

return { run_id: digest.run_id, finish_exit: fin ? fin.finish_exit : null, briefing: fin ? fin.stdout : null }
