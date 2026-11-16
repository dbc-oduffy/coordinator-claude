/*
 * Grinds every fleet repo's state/cross-repo/inbox/ to zero: triage+verify+dispose in ~30-memo
 * shards, the first shard of each repo also running the assembler. Fired by the Group EM at entry;
 * the autofire hook (group-em-autofire.py) surfaces the exact invocation with `repos` filled in.
 *
 * args contract:
 *   {
 *     repos: [ "<absolute repo root>", ... ],
 *       // the fleet map's repos (machine-local repos.*), de-duplicated, each carrying
 *       // state/cross-repo/inbox. NEVER derived from live sessions: a repo with no EM is
 *       // in scope, and the inbox is the work, not the session.
 *     gem: { sessionId: "<holder sid>", name: "<holder SendMessage name or null>" },
 *     memo_lists: { "<repo root, as in repos>": { memos: ["<abs path>", ...],   // status open | in_progress
 *                                                 stamped: ["<abs path>", ...] } },  // any other status
 *       // emitted by the autofire; a repo listed here runs no enumerator. A repo absent from it
 *       // (inbox unreadable at emit) falls back to the enumerator. Keys are matched through norm().
 *     memo_counts: { "<repo root>": <memos.length> },  // informational; counts are derived from the list
 *   }
 *
 * The assembler (workday-start-inbox-blitz-assemble) has no --repo-root and resolves its repo
 * from CLAUDE_PROJECT_DIR, then git toplevel, then cwd. So every call sets BOTH `cd` and
 * CLAUDE_PROJECT_DIR; either alone reads the caller's own inbox and reports `skipped`.
 *
 * Per repo the memo and move-only lists come from args.memo_lists; one cheap haiku enumerator runs
 * the assembler only for a repo the args do not cover. A repo with neither list fires no shard.
 * Otherwise the sorted list is hash-sliced by shard index and
 * all shards fire in one parallel call, each planning disposal for its own slice only. Shard 1 also
 * owns the stamped-but-unmoved (move-only) memos and the late-arrival re-enumeration. No memo is
 * disposed by two shards.
 *
 * Every agent names its tier (a guard requires it): Sonnet for shards, haiku for the read-only enumerator.
 * Workers never mutate or commit in a fleet repo: block-subagent-commit refuses any subagent
 * `git commit`, and bump-foreign-repo-write walls a subagent's write into a repo other than the
 * launch repo. Each shard therefore returns one APPLY MANIFEST (moves, stamps, files to write,
 * memos to send, a scoped commit pathspec + subject). The Group EM applies and commits it itself
 * in a repo with no live EM, and memos it to the EM of a repo that has one, who applies and commits (skills/group-em/SKILL.md § Cross-repo commit authority,
 * § Fleet inbox grind). Runs no test suite.
 */

export const meta = {
  name: 'fleet-inbox-blitz',
  description: 'Group EM: grind every fleet repo cross-repo memo inbox to zero — triage+verify+dispose per shard (the first shard also assembles), one apply manifest per shard, memoed to that repo EM to execute and commit',
  phases: [
    { title: 'Triage', detail: '~30-memo shards; an enumerator assembles, triage + verify + disposal planning ride together' },
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

const SHARD_SIZE = 30
const ENUM = {type:'object',properties:{repo:{type:'string'},state:{type:'string'},open_count:{type:'number'},brief:{type:'string'},memos:{type:'array',items:{type:'string'}},stamped:{type:'array',items:{type:'string'}},notes:{type:'string'}},required:['repo','state','memos','stamped']}

// BEGIN PARTITION
// Pure: the same memo list always yields the same disjoint slices, so no shard needs another's list.
const hashPath = s => { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0 } return h }
const shardCountFor = n => Math.max(1, Math.ceil(n / SHARD_SIZE))
const sliceMemos = (memos, shardIndex, shardCount) => [...new Set(memos)].sort().filter(m => hashPath(m) % shardCount === shardIndex)
// END PARTITION

const norm = p => p.replace(/\\/g, '/').replace(/\/+$/, '')
const name = p => norm(p).split('/').pop()
const repoRoots = args.repos.map(norm)
const supplied = Object.fromEntries(Object.entries(args.memo_lists || {}).map(([k, v]) => [norm(k), v]))

// Per-shard scratch: shards of one run share the session scratchpad, and a shard once ran a peer's
// helper script found there. Each shard writes and runs only inside its own subdir.
const shardScratch = (root, n) => `SCRATCH ISOLATION: make and use ONLY the subdir inbox-blitz/${name(root)}-shard${n}/ under your sidecar/scratch directory. Write every file (manifest, helper script, body) there, and run only scripts you wrote there yourself; never read, run or edit a file another shard left elsewhere in the scratch directory.`

const VERIFY = `For EACH memo: read it, classify, and VERIFY in the same pass. Verify checks: (1) already-answered, not just accurate — glob state/cross-repo/archive/, state/memo-outbox/sent/, and git log on both sender and receiver repos for a later memo/commit that discharges the ask; (2) absence is only evidence from the right directory — name the directory you looked in. A memo whose ask is discharged is close-answered regardless of body. Verdicts: close-answered, close-fyi, close-stale, action-now-XS, bundle-XS-S, plan-weight, engine-claude-klabauter, needs-PM. Only use needs-PM for product-direction/irreversible/no-right-answer items (expect ~1 in 20 at most). Give a problem-space tag for plan-weight items.`

// BEGIN DISPOSE_PROC
const disposeProc = (repo, shardTag, extra) => `${MID_RUN_DIRECTION_RULE}\n\nPlan the disposal of repo ${repo}'s inbox memos named for you (${shardTag}) to zero as an APPLY MANIFEST using your verified triage verdicts. Plan disposal ONLY for your own memos: another shard of this repo owns every other memo, so never move, stamp, baton or close a memo you were not given.\n\nYou change NOTHING in ${repo}: no mv, no git add, no stamp, no file write, no commit. Write the manifest as JSON (shape: ${JSON.stringify(['repo','closed','left_open','batons','moves','stamps','writes','memos_to_send','guard','apply_rule','commit','needs_pm','friction'])}; moves are {from,to}, writes are {path,content}, guard is [{memo,lines}] (one entry per memo you stamp or send for: memo is its absolute path, lines are the exact stamps and memos_to_send lines that memo owns), apply_rule is the literal string "Before each stamp or memos_to_send line, re-read the memo's status named in guard; if it is not open/in_progress, drop that memo's lines." copied verbatim, so an EM applying the manifest by path carries the rule with it; commit is {pathspec,subject}) to a file under your sidecar/scratch directory, outside ${repo}, named for ${shardTag}; the Group EM applies it, or memos it to this repo's EM when one is live. Procedure (coordinator/docs/wiki/ceremony-calibration/workday-start-residue.md § Step 1.45a is authority — read it and the repo's own archive convention first):${extra}
- close-* : put the exact \`archive-stamp-cli resolve-memo <memo> --actioned-note "<close-* verdict and why>"\` line in stamps (resolve refuses without --actioned-note or --decision <accepted|partial|declined>) (read the memo's status first: \`resolve-memo\` for an open memo; \`action-memo <memo>\` only for a memo whose status is in_progress, and the CLI refuses it on an open memo; runnable lines only, notes to friction; it commits each stamp itself, so the applier squashes those per-stamp commits (see the squash rule below); apply order: ledger, writes, stamps, moves, memos_to_send; it does NOT move the file; --realized-by needs 'inline', a path containing /, or a hex SHA; forces decision=accepted even for stale/FYI), and the file move in moves (absolute from/to) in the repo's existing archive layout (if ANY state/cross-repo/archive/<YYYY-MM>/ folder exists, file each memo under the <YYYY-MM>/ of its own date, even when recent entries sit flat; flat archive/ only when no month folder exists at all).
- action-now-XS: plan it if it is a doctrine/doc/state edit inside this repo and clearly safe (full new file content in writes); otherwise bundle.
- ALL bundle-XS-S items + leftover XS: ONE baton for your shard (use the repo's baton/queue convention, with ${shardTag} in the baton filename so shards never collide; full file in writes, complete with the repo's handoff frontmatter and an empty \`## Session Ledger\` heading, because the emitter refuses a baton without them), then close the memos pointing to it. BATON SCHEMA CHECK (yours, at mint): a copied state/handoffs/ file gives the field names only, never the values (a copied stale enum value is how invalid batons spread). Write each baton to \`<your shard subdir>/lint/state/handoffs/<YYYY-MM>/<baton file name>\` and run \`lint-frontmatter --root <your shard subdir>/lint --file <that path>\`; put it in writes only when that exits 0. On exit 1, set each named field to a value its hint allows and re-run; if it still fails, mint no baton, leave its memos open, and put the violation in friction. Every baton's frontmatter \`branch:\` is the output of \`git -C ${repo} branch --show-current\` (the target repo's branch, never your own home's), and its \`summary:\` stays under 140 characters. If that output is empty (detached HEAD, e.g. a gate clone) REFUSE: write no baton, leave the memos that needed it open, and list the repo under needs_pm as "detached HEAD, no baton minted". A baton's \`deployment_state\` is never \`closed\` and its \`branch:\` is never empty.
- plan-weight: one baton per problem space (full file in writes, ${shardTag} in the filename), then close memos pointing at it.
- engine-claude-klabauter: put one runnable line per memo in memos_to_send: \`cross-repo-memo draft <topic-slug> --to claude-klabauter-em --kind fyi|bug --title "<line>" --summary "<=120 chars>" --body-file <path>\`, with the body (paths fully qualified) as a writes entry at that <path> under the repo's scratch/ (where --body-file is not yet published, the EM drafts without it, puts the body in the draft file, then runs \`cross-repo-memo send <topic-slug>\`). Address it to the receiver claude-klabauter-em (the only registered claude-klabauter receiver; never a session name such as -e3), then close.
- move-only: already stamped; put only its archive move in moves (no stamp), and count it closed.
- needs-PM: leave open, list it.
Every stamp and memos_to_send line MUST appear under exactly one guard entry: the apply step re-reads that memo's status immediately before running them and drops those lines when it is no longer open/in_progress (another action stamp landed since your snapshot).
commit.pathspec lists every file the apply touches as explicit file paths (both old and new path of each move, and every stamped memo; never a directory: it sweeps in peer-delivered files); commit.subject starts "inbox: G-EM blitz —".
APPLY COMMIT FORM (the applier's, never yours): \`git commit -- <pathspec>\` with the pathspec listed in commit.pathspec. Never \`git add <pathspec>\` then commit: git add fails on a removed move path and the deletion goes unstaged.
SQUASH RULE (the applier's): record \`git rev-parse HEAD\` as BASE before the first stamp. After the stamps, if \`git log --format=%s BASE..HEAD\` lists only archive-stamp-cli stamp commits, run \`git reset --mixed BASE\` so the one manifest commit picks up the stamped files; if any other commit sits in that range (a peer committed meanwhile), leave the stamp commits unsquashed and still make the manifest commit.
BATON LINT (the applier's): after the writes and before the first stamp, run \`lint-frontmatter --file <path>\` from ${repo} on every writes entry under state/handoffs/. Any exit 1 refuses the manifest: remove the files the writes created, run no stamp, move or send, and report the violation.
PENDING-MANIFEST LEDGER (the applier's): before the first apply step write \`<repo>/.coordinator-local/gem-inbox-pending/<manifest file name>.json\` as {"memos": [<absolute posix memo path of every memo this manifest closes, stamps or sends for>]}, and delete that file after the manifest commit lands. A produced-but-unapplied manifest keeps its memos off the re-entry list; an entry older than 6 hours is ignored.
Report counts (a flat object that includes untriaged_late_arrivals, 0 unless the designated shard found inbox memos it could not triage and disposition), batons, anything left open and why, and tool friction encountered in the manifest.`
// END DISPOSE_PROC

const FIRST_EXTRA = `\n- You are the DESIGNATED shard of this repo: you alone own the move-only memos and the late arrivals. After disposing your own memos, re-enumerate <repo>/state/cross-repo/inbox (every .md) and disposition any memo that arrived after the assembler snapshot, is not in the assembled list at all, or is missing a verdict (triage it yourself); the memos in the other shards' slices (every assembled memo not in your own list above) are theirs and are excluded from this pass. Every memo whose status is already stamped but whose file is still in the inbox gets verdict move-only. Report counts.untriaged_late_arrivals as the number of late-arrival memos you could not triage and disposition; a value above 0 fails the shard.`
const REST_EXTRA = `\n- You are NOT the designated shard: the first shard owns move-only memos and late-arrival re-enumeration. Do not re-enumerate the inbox or touch any memo outside your list.`

const results = await parallel(repoRoots.map(root => async () => {
  const sup = supplied[root]
  const en = sup && Array.isArray(sup.memos) ? {repo: root, state: 'emit-time', memos: sup.memos, stamped: Array.isArray(sup.stamped) ? sup.stamped : [], brief: ''} : await agent(`${COMMON}\n\nInbox enumeration ONLY, repo ${root}. Triage nothing and plan nothing. Run the inbox assembler FROM THAT REPO (it has no --repo-root; it reads CLAUDE_PROJECT_DIR, then cwd — set both): \`cd ${root} && CLAUDE_PROJECT_DIR=${root} ~/.coordinator-claude-settings/bin/workday-start-inbox-blitz-assemble\`. Verify the memo paths it returns are under ${root}/state/cross-repo/inbox (if not, or if the assembler returns nothing, enumerate that inbox directly: every .md with status open/in_progress). Separately list in stamped every .md still in ${root}/state/cross-repo/inbox whose status is NOT open/in_progress (stamped actioned/resolved but never moved; the assembler skips these) as absolute paths, and unreadable ones in notes. Return repo set to ${root} exactly, plus state, open_count, stamped, memos (the union of all dispatches[].memos as absolute paths, the FULL list) and brief (the first dispatch's brief verbatim; concatenate distinct briefs if they differ).`, {label:`enumerate:${name(root)}`, phase:'Triage', schema:ENUM, agentType:'coordinator:group-em-assistant', model:TIER.HAIKU})
  if (!en || !Array.isArray(en.memos)) { log(`${name(root)}: ENUMERATION RETURNED NOTHING for this repo`); return {repo:root, manifests:[]} }
  const stamped = en.stamped || []
  if (!en.memos.length && !stamped.length) { log(`${name(root)}: no open memos (${en.state}), 0 move-only; no shards fired`); return {repo:root, manifests:[]} }
  if (!en.memos.length) log(`${name(root)}: no open memos (${en.state}), ${stamped.length} move-only`)
  const count = shardCountFor(en.memos.length)
  const slices = Array.from({length: count}, (_, i) => sliceMemos(en.memos, i, count))
  const shards = slices.map((m, i) => ({n: i + 1, memos: m})).filter(sh => sh.n === 1 || sh.memos.length)
  const runShard = (sh, redo) => agent(pathSummary(`${COMMON}${redo || ''}\n\nInbox blitz triage+verify+dispose, repo ${root}, shard ${sh.n}/${count}${sh.n === 1 ? ' (designated)' : ''}. ${shardScratch(root, sh.n)} Brief (verbatim from assembler):\n${en.brief || '(none)'}\n\nYour memos (this is your whole list; the other shards hold disjoint slices of the same sorted list):\n${sh.memos.join('\n') || '(none)'}\n${sh.n === 1 ? `\nStamped-but-unmoved (move-only) memos, yours alone:\n${stamped.join('\n') || '(none)'}\n\nMemos owned by the other shards (never triage or dispose these in your late-arrival pass):\n${en.memos.filter(m => !sh.memos.includes(m)).join('\n') || '(none)'}\n` : ''}\n${VERIFY} Read-only: do not move or edit files.\n\n${disposeProc(root, `shard ${sh.n}`, sh.n === 1 ? FIRST_EXTRA : REST_EXTRA)}`), {label:`triage:${name(root)}#${sh.n}`, phase:'Triage', schema:PATH_SUMMARY_SCHEMA, agentType:'coordinator:group-em-assistant', model:TIER.SONNET})
  const lateOf = o => Number(o && o.counts && o.counts.untriaged_late_arrivals) || 0
  const REDO = `\n\nRE-DISPATCH: your previous attempt reported untriaged_late_arrivals > 0. Triage and disposition every late-arrival memo this time and report untriaged_late_arrivals 0.`
  const done = await parallel(shards.map(sh => async () => {
    const first = await runShard(sh)
    if (lateOf(first) <= 0) return first
    log(`${name(root)}: SHARD ${sh.n} reported untriaged_late_arrivals ${lateOf(first)}; re-dispatching once`)
    return runShard(sh, REDO)
  }))
  const incomplete = []
  done.forEach((o, i) => {
    if (!o) log(`${name(root)}: SHARD ${shards[i].n} RETURNED NOTHING; its memos are undisposed`)
    else if (lateOf(o) > 0) { incomplete.push(shards[i].n); log(`${name(root)}: SHARD ${shards[i].n} FAILED: untriaged_late_arrivals ${lateOf(o)} after re-dispatch; its manifest is withheld`) }
  })
  const manifests = done.map((o, i) => o && lateOf(o) <= 0 ? {shard:shards[i].n, path:o.path, summary:o.summary, counts:o.counts} : null).filter(Boolean)
  return {repo:root, manifests, incomplete}
}))
return results
