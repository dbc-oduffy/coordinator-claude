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
 * Workers never mutate or commit in a fleet repo: block-subagent-commit refuses any subagent
 * `git commit`, and bump-foreign-repo-write walls a subagent's write into a repo other than the
 * launch repo. The Dispose phase therefore returns one APPLY MANIFEST per repo (moves, stamps,
 * files to write, memos to send, a scoped commit pathspec + subject); the Group EM memos each to that
 * repo's EM, who applies it and commits (skills/group-em/SKILL.md § Cross-repo commit authority,
 * § Fleet inbox grind). Runs no test suite.
 */

export const meta = {
  name: 'fleet-inbox-blitz',
  description: 'Group EM: grind every fleet repo cross-repo memo inbox to zero — triage+verify per shard, then one apply manifest per repo, memoed to that repo EM to execute and commit',
  phases: [
    { title: 'Assemble', detail: 'run the inbox-blitz assembler from each repo' },
    { title: 'Triage', detail: '~30-memo shards, triage + verify ride together' },
    { title: 'Dispose', detail: 'one read-only agent per repo: close/route/bundle as an apply manifest' },
  ],
}

if (!args || !Array.isArray(args.repos) || !args.repos.length) {
  throw new Error('fleet-inbox-blitz: args.repos is required (absolute repo roots from the fleet map)')
}
const gem = args.gem || {}
const GEM = `the Group EM session ${gem.sessionId || '(unknown)'}${gem.name ? ` (${gem.name})` : ''}`
const COMMON = `You act for ${GEM}. You are a READ-ONLY worker in these repos: never write, move, stage or commit there — the guards refuse a subagent's commit and its write into a foreign repo, and the Group EM applies your output itself. Other EM sessions may be LIVE in these repos, so plan scoped explicit-file pathspecs only (never git add -A / . / a directory), no destructive git ops, nothing outside state/cross-repo/ and the state/ queue/baton dirs the plan creates. DO NOT run any test suite — the box is memory-contended and peers are queued on tests. Engine-plane friction (coordinator_core, klabauter bins) is claude-klabauter's: note it, don't fix it.`
const MID_RUN_DIRECTION_RULE = `RE-READ BEFORE YOU WRITE. The PM delivers direction to a running workflow by editing its
artifacts, never by stopping it, and SendMessage cannot reach you. Immediately before you write
your output, re-read every sizing, plan and handoff this brief names or that you read or write.
A \`## PM direction\` section in a plan or handoff, or a \`requirement_register\` row in a sizing,
that was absent from your first read and that you did not write yourself was added after your
dispatch: it is binding. Apply it over
this brief and over anything you read earlier, and name it in your return.`

const ASSEMBLE = {type:'object',properties:{repo:{type:'string'},state:{type:'string'},open_count:{type:'number'},brief:{type:'string'},memos:{type:'array',items:{type:'string'}},stamped:{type:'array',items:{type:'string'}},notes:{type:'string'}},required:['repo','state','memos','stamped']}
const TRIAGE = {type:'object',properties:{results:{type:'array',items:{type:'object',properties:{memo:{type:'string'},verdict:{type:'string',enum:['close-answered','close-fyi','close-stale','action-now-XS','bundle-XS-S','plan-weight','engine-claude-klabauter','needs-PM']},space:{type:'string'},evidence:{type:'string'},action:{type:'string'}},required:['memo','verdict','evidence']}}},required:['results']}
const DISPOSE = {type:'object',properties:{repo:{type:'string'},closed:{type:'number'},left_open:{type:'array',items:{type:'string'}},batons:{type:'array',items:{type:'string'}},moves:{type:'array',items:{type:'object',properties:{from:{type:'string'},to:{type:'string'}},required:['from','to']}},stamps:{type:'array',items:{type:'string'}},writes:{type:'array',items:{type:'object',properties:{path:{type:'string'},content:{type:'string'}},required:['path','content']}},memos_to_send:{type:'array',items:{type:'string'}},commit:{type:'object',properties:{pathspec:{type:'array',items:{type:'string'}},subject:{type:'string'}},required:['pathspec','subject']},needs_pm:{type:'array',items:{type:'string'}},friction:{type:'array',items:{type:'string'}}},required:['repo','closed','left_open','commit','moves']}

const chunk = (a,n) => { const o=[]; for (let i=0;i<a.length;i+=n) o.push(a.slice(i,i+n)); return o }
const norm = p => p.replace(/\\/g, '/').replace(/\/+$/, '')
const name = p => norm(p).split('/').pop()

const results = await pipeline(args.repos.map(norm),
  root => agent(`${COMMON}\n\nRepo: ${root}. Run the inbox assembler FROM THAT REPO (it has no --repo-root; it reads CLAUDE_PROJECT_DIR, then cwd — set both): \`cd ${root} && CLAUDE_PROJECT_DIR=${root} ~/.coordinator-claude-settings/bin/workday-start-inbox-blitz-assemble\`. Verify the memo paths it returns are under ${root}/state/cross-repo/inbox (if not, enumerate that inbox directly: every .md with status open/in_progress, ). Separately list in stamped every .md still in ${root}/state/cross-repo/inbox whose status is NOT open/in_progress (stamped actioned/resolved but never moved; the assembler skips these) as absolute paths, and unreadable ones in notes. Return state, open_count, stamped, the union of all dispatches[].memos as absolute paths, and the first dispatch's brief verbatim (concatenate distinct briefs if they differ).`, {label:`assemble:${name(root)}`, phase:'Assemble', schema:ASSEMBLE, agentType:'coordinator:group-em-assistant', model:'sonnet', effort:'low'}),
  async (asm, root) => {
    // A memo stamped closed but still in the inbox is not disposed: it owes its archive move.
    const moveOnly = ((asm && asm.stamped) || []).map(m => ({memo:m, verdict:'move-only', evidence:'status already stamped; file still in inbox'}))
    if (!asm || !asm.memos.length) { log(`${name(root)}: no open memos (${asm && asm.state}), ${moveOnly.length} move-only`); return {repo:root, asm, triage:moveOnly} }
    const shards = chunk(asm.memos, 30)
    const tri = await parallel(shards.map((m,i) => () => agent(`${COMMON}\n\nInbox blitz triage+verify, repo ${root}, shard ${i+1}/${shards.length}. Brief (verbatim from assembler):\n${asm.brief||'(none)'}\n\nMemos:\n${m.join('\n')}\n\nFor EACH memo: read it, classify, and VERIFY in the same pass. Verify checks: (1) already-answered, not just accurate — glob state/cross-repo/archive/, state/memo-outbox/sent/, and git log on both sender and receiver repos for a later memo/commit that discharges the ask; (2) absence is only evidence from the right directory — name the directory you looked in. A memo whose ask is discharged is close-answered regardless of body. Only use needs-PM for product-direction/irreversible/no-right-answer items (expect ~1 in 20 at most). Give a problem-space tag for plan-weight items. Read-only: do not move or edit files.`, {label:`triage:${name(root)}#${i+1}`, phase:'Triage', schema:TRIAGE, agentType:'coordinator:group-em-assistant', model:'sonnet'})))
    return {repo:root, asm, triage: tri.filter(Boolean).flatMap(t => t.results).concat(moveOnly)}
  },
  r => r.triage.length ? agent(`${COMMON}\n\n${MID_RUN_DIRECTION_RULE}\n\nPlan the disposal of repo ${r.repo}'s inbox to zero as an APPLY MANIFEST using these verified triage verdicts:\n${JSON.stringify(r.triage)}\n\nYou change NOTHING in ${r.repo}: no mv, no git add, no stamp, no file write, no commit. Return the manifest; the Group EM memos it to this repo's EM, who executes and commits it. Procedure (coordinator/docs/wiki/ceremony-calibration/workday-start-residue.md § Step 1.45a is authority — read it and the repo's own archive convention first):\n- First re-enumerate ${r.repo}/state/cross-repo/inbox (every .md) and disposition any memo that arrived after the snapshot or is missing a verdict (triage it yourself); the verdict list is a snapshot, never the whole inbox.\n- close-* : put the exact \`archive-stamp-cli resolve-memo\` command line in stamps (stamps holds runnable command lines only — every note goes to friction; it only stamps, and commits that stamp on its own once per memo, so the stamp never rides the scoped commit; stamps run before the moves; it does NOT move the file; --realized-by needs 'inline', a path containing /, or a hex SHA; it forces decision=accepted even for stale/FYI closes), and the file move in moves (absolute from/to) in the repo's existing archive layout (state/cross-repo/archive/<YYYY-MM>/ only if that layout exists; many repos are flat).\n- action-now-XS: plan it if it is a doctrine/doc/state edit inside this repo and clearly safe (full new file content in writes); otherwise bundle.\n- ALL bundle-XS-S items + leftover XS: ONE baton for this blitz (use the repo's baton/queue convention; full file in writes), then close the memos pointing to it.\n- plan-weight: one baton per problem space (full file in writes), then close memos pointing at it.\n- engine-claude-klabauter: put one runnable line per memo in memos_to_send: \`cross-repo-memo draft <topic-slug> --to claude-klabauter-em --kind fyi|bug --title "<line>" --summary "<=120 chars>" --body-file <path>\`, with the body (paths fully qualified) as a writes entry at that <path> under the repo's scratch/ (where --body-file is not yet published, the EM drafts without it, puts the body in the draft file, then runs \`cross-repo-memo send <topic-slug>\`). Address it to the receiver claude-klabauter-em (the only registered claude-klabauter receiver; never a session name such as -e3), then close.\n- move-only: already stamped; put only its archive move in moves (no stamp), and count it closed.\n- needs-PM: leave open, list it.\ncommit.pathspec lists every file the apply touches as explicit file paths (both old and new path of each move; never a directory: it sweeps in peer-delivered files); commit.subject starts "inbox: G-EM blitz —". Report counts, batons, anything left open and why, and tool friction encountered.`, {label:`dispose:${name(r.repo)}`, phase:'Dispose', schema:DISPOSE, agentType:'coordinator:group-em-assistant', model:'sonnet'}) : {repo:r.repo, closed:0, left_open:[], moves:[], commit:{pathspec:[], subject:''}}
)
return results
