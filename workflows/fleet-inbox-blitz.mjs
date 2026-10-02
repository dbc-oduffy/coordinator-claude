/*
 * Grinds every fleet repo's state/cross-repo/inbox/ to zero: assemble, triage+verify in
 * ~30-memo shards, then one disposing agent per repo. Fired by the Group EM at entry; the
 * autofire hook (group-em-autofire.py) surfaces the exact invocation with `repos` filled in.
 *
 * args contract:
 *   {
 *     repos: [ "<absolute repo root>", ... ],
 *       // the fleet map's repos (machine-local repos.*), de-duplicated, each carrying
 *       // state/cross-repo/inbox. NEVER derived from live sessions: a repo with no EM is
 *       // in scope, and the inbox is the work, not the session.
 *     gem: { sessionId: "<holder sid>", name: "<holder SendMessage name or null>" },
 *   }
 *
 * The assembler (workday-start-inbox-blitz-assemble) has no --repo-root and resolves its repo
 * from CLAUDE_PROJECT_DIR, then git toplevel, then cwd. So every call sets BOTH `cd` and
 * CLAUDE_PROJECT_DIR; either alone reads the caller's own inbox and reports `skipped`.
 *
 * Every agent is Sonnet: a guard requires the tier on a workflow worker.
 * Commits: scoped pathspecs in each repo, authority inherent to the Group EM role
 * (skills/group-em/SKILL.md § Cross-repo commit authority). Runs no test suite.
 */

export const meta = {
  name: 'fleet-inbox-blitz',
  description: 'Group EM: grind every fleet repo cross-repo memo inbox to zero — triage+verify per shard, dispose and commit scoped per repo',
  phases: [
    { title: 'Assemble', detail: 'run the inbox-blitz assembler from each repo' },
    { title: 'Triage', detail: '~30-memo shards, triage + verify ride together' },
    { title: 'Dispose', detail: 'one agent per repo: close/route/bundle, scoped commit' },
  ],
}

if (!args || !Array.isArray(args.repos) || !args.repos.length) {
  throw new Error('fleet-inbox-blitz: args.repos is required (absolute repo roots from the fleet map)')
}
const gem = args.gem || {}
const GEM = `the Group EM session ${gem.sessionId || '(unknown)'}${gem.name ? ` (${gem.name})` : ''}`
const COMMON = `You act for ${GEM}. Cross-repo commit authority is inherent to the Group EM role and is presumed: commit in whichever fleet repo you are working. Rules: other EM sessions may be LIVE in these repos — scoped pathspec commits only (never git add -A / . / commit -a), no destructive git ops, never touch files outside state/cross-repo/ and the state/ queue/baton dirs you create. DO NOT run any test suite — the box is memory-contended and peers are queued on tests. Engine-plane friction (coordinator_core, klabauter bins) is claude-klabauter's: note it, don't fix it.`

const ASSEMBLE = {type:'object',properties:{repo:{type:'string'},state:{type:'string'},open_count:{type:'number'},brief:{type:'string'},memos:{type:'array',items:{type:'string'}},notes:{type:'string'}},required:['repo','state','memos']}
const TRIAGE = {type:'object',properties:{results:{type:'array',items:{type:'object',properties:{memo:{type:'string'},verdict:{type:'string',enum:['close-answered','close-fyi','close-stale','action-now-XS','bundle-XS-S','plan-weight','engine-claude-klabauter','needs-PM']},space:{type:'string'},evidence:{type:'string'},action:{type:'string'}},required:['memo','verdict','evidence']}}},required:['results']}
const DISPOSE = {type:'object',properties:{repo:{type:'string'},closed:{type:'number'},left_open:{type:'array',items:{type:'string'}},batons:{type:'array',items:{type:'string'}},commits:{type:'array',items:{type:'string'}},needs_pm:{type:'array',items:{type:'string'}},friction:{type:'array',items:{type:'string'}}},required:['repo','closed','left_open','commits']}

const chunk = (a,n) => { const o=[]; for (let i=0;i<a.length;i+=n) o.push(a.slice(i,i+n)); return o }
const norm = p => p.replace(/\\/g, '/').replace(/\/+$/, '')
const name = p => norm(p).split('/').pop()

const results = await pipeline(args.repos.map(norm),
  root => agent(`${COMMON}\n\nRepo: ${root}. Run the inbox assembler FROM THAT REPO (it has no --repo-root; it reads CLAUDE_PROJECT_DIR, then cwd — set both): \`cd ${root} && CLAUDE_PROJECT_DIR=${root} ~/.coordinator-claude-settings/bin/workday-start-inbox-blitz-assemble\`. Verify the memo paths it returns are under ${root}/state/cross-repo/inbox (if not, enumerate that inbox directly: every .md with status open/in_progress, plus list non-open/unreadable ones in notes). Return state, open_count, the union of all dispatches[].memos as absolute paths, and the first dispatch's brief verbatim (concatenate distinct briefs if they differ).`, {label:`assemble:${name(root)}`, phase:'Assemble', schema:ASSEMBLE, agentType:'coordinator:group-em-assistant', model:'sonnet', effort:'low'}),
  async (asm, root) => {
    if (!asm || !asm.memos.length) { log(`${name(root)}: inbox empty (${asm && asm.state})`); return {repo:root, asm, triage:[]} }
    const shards = chunk(asm.memos, 30)
    const tri = await parallel(shards.map((m,i) => () => agent(`${COMMON}\n\nInbox blitz triage+verify, repo ${root}, shard ${i+1}/${shards.length}. Brief (verbatim from assembler):\n${asm.brief||'(none)'}\n\nMemos:\n${m.join('\n')}\n\nFor EACH memo: read it, classify, and VERIFY in the same pass. Verify checks: (1) already-answered, not just accurate — glob state/cross-repo/archive/, state/memo-outbox/sent/, and git log on both sender and receiver repos for a later memo/commit that discharges the ask; (2) absence is only evidence from the right directory — name the directory you looked in. A memo whose ask is discharged is close-answered regardless of body. Only use needs-PM for product-direction/irreversible/no-right-answer items (expect ~1 in 20 at most). Give a problem-space tag for plan-weight items. Read-only: do not move or edit files.`, {label:`triage:${name(root)}#${i+1}`, phase:'Triage', schema:TRIAGE, agentType:'coordinator:group-em-assistant', model:'sonnet'})))
    return {repo:root, asm, triage: tri.filter(Boolean).flatMap(t => t.results)}
  },
  r => r.triage.length ? agent(`${COMMON}\n\nDispose of repo ${r.repo}'s inbox to zero using these verified triage verdicts:\n${JSON.stringify(r.triage)}\n\nProcedure (coordinator/commands/workday-start.md §1.45a is authority — read it and the repo's own archive convention first):\n- First re-enumerate ${r.repo}/state/cross-repo/inbox (every .md) and disposition any memo that arrived after the snapshot or is missing a verdict (triage it yourself); the verdict list is a snapshot, never the whole inbox.
- close-* : stamp with \`archive-stamp-cli resolve-memo\` (it only stamps and auto-commits once per memo; it does NOT move the file; --realized-by needs 'inline', a path containing /, or a hex SHA; it forces decision=accepted even for stale/FYI closes), then move the file to the repo's existing archive layout (state/cross-repo/archive/<YYYY-MM>/ only if that layout exists; many repos are flat). The move is manual: subagent guards may block \`git mv\`, so use plain mv then \`git add\` of the explicit old and new paths. Write helper scripts to the scratchpad via the Write tool (long heredocs and shared $TEMP files break).\n- action-now-XS: do it if it is a doctrine/doc/state edit inside this repo and clearly safe; otherwise bundle.\n- ALL bundle-XS-S items + leftover XS: ONE baton for this blitz (use the repo's baton/queue convention), then close the memos pointing to it.\n- plan-weight: one baton per problem space, then close memos pointing at it.\n- engine-claude-klabauter: write a memo via the repo's memo-send path (cross-repo-memo draft --kind fyi|bug, summary <=120 chars, body paths fully qualified) addressed to the receiver claude-klabauter-em (the only registered claude-klabauter receiver; never a session name such as -e3), then close.\n- needs-PM: leave open, list it.\nCommit in small scoped commits with explicit pathspecs, message prefix "inbox: G-EM blitz —". Re-run git status before each commit and commit with \`git commit -- <explicit file paths>\` (never a directory pathspec: it sweeps in peer-delivered files). Report counts, commits (sha+subject), batons, anything left open and why, and tool friction encountered.`, {label:`dispose:${name(r.repo)}`, phase:'Dispose', schema:DISPOSE, agentType:'general-purpose', model:'sonnet'}) : {repo:r.repo, closed:0, left_open:[], commits:[]}
)
return results
