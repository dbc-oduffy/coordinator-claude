# Multi-Session Crash Recovery

> **Purpose:** playbook for reconstructing and recovering many Claude Code sessions killed at once by a
> host-level event (Windows Terminal crash, unexpected shutdown, bugcheck, OOM). Turns "a dozen sessions
> just died" into a per-session recovery slate: own-repo recovery handoffs + cross-repo memos to sibling EMs.
> Dogfooded at scale: 18 sessions across 5 repos, killed by a Windows Terminal AV crash.
>
> **When to run:** the PM reports that multiple sessions died simultaneously, or you return to a machine
> and find several repos' sessions gone. Candidate for skill-ification (`/crash-recovery`) if recurrence
> reaches ~2×/month — this wiki is the validated procedure a skill would wrap.

## The shape of the job

A host event kills every live `node.exe` (Claude Code) process at essentially the same instant. Each session's
work-in-flight is lost from *context* but — crucially — **whether it is lost from *disk* depends on the cause**:

- **Process-tree kill (Terminal crash, `taskkill`, logoff)** — machine stays up, filesystem intact. Uncommitted
  work survives on disk; you are reconstructing *conversational context*, not recovering lost writes. (This was
  the 2026-07-01 case.)
- **Power loss / bugcheck / hard reboot** — dirty pages may not have flushed; treat uncommitted work as
  suspect and verify every file against `git` before trusting it.

Determining which happened is Step 2 and it changes how aggressively you must preserve dirty trees.

## Step 1 — Pin the crash moment (mtime clustering)

Session transcripts live at `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`. A host event flushes/kills
every live process together, so the **last-write mtime of every in-flight transcript clusters to one sub-second
window**. That cluster is the crash signature *and* the candidate casualty set.

```bash
cd ~/.claude/projects/
for d in <encoded-repo-dirs>; do
  echo "=== $d ==="
  ls -lt --time-style=full-iso "$d"/*.jsonl 2>/dev/null | head -8
done
```

Read off the shared timestamp, then filter the exact crash-window set per repo (grep the ISO string — epoch math
trips on timezone):

```bash
ls -l --time-style=full-iso "$d"/*.jsonl | grep -E '<YYYY-MM-DD> 12:02:(4[0-9]|5[0-9])|<YYYY-MM-DD> 12:03:0'
```

- Encoded-cwd dir naming: `X:\project-rag` → `X--project-rag`; `C:\Users\oduffy\.claude` → `C--Users-example-operator--claude`. <!-- foreign-path-ok: illustrating the harness's own path-encoding scheme, the subject of this bullet -->
  (Historic `-Users-example-operator-X-…` forms also exist; prefer the current `X--` / `C--` scheme.)
- Sessions written *after* the cluster are restarts/new sessions — exclude them (the recovery session itself is one).
- Tiny transcripts (a few KB) in the cluster are usually near-empty `/clear` shells — classify fast, low priority.

## Step 2 — Fan out one forensic investigator per repo (+ one crash-cause agent)

Fan-out is the default shape. One `general-purpose` (Sonnet) investigator per affected repo, **backgrounded**,
each writing to `state/recovery/<date>-crash/<repo>-findings.md`. Plus one crash-cause agent in parallel.

### Transcript forensics technique (put verbatim in every investigator brief)

`.jsonl` = one JSON object per line, large — **never `Read` whole; parse with node/jq**. Field guide:
- `type`: `user`/`assistant` = conversation; `summary`/`system`/`queue-operation`/`permission-mode`/`file-history-snapshot`
  = metadata (ignore for content). **A crashed transcript's trailing lines are often bulk-appended metadata, not the
  last real turn** — parse, don't `tail`.
- `message.role` + `message.content[]` (items `.type`: text/tool_use/tool_result; `.text`/`.name`/`.input`).
- `isSidechain: true` = a subagent turn. A transcript that is *mostly* sidechain IS a subagent sidechain, not a main
  EM session → it does NOT need its own recovery handoff (note its parent workstream, drop it).
- `cwd`, `gitBranch`, `timestamp` ride on turns. FIRST user turn usually holds the opening task or a `/pickup`.

Extraction one-liner (dump text/tool turns, mark sidechain):
```bash
node -e 'const fs=require("fs"),ls=fs.readFileSync(process.argv[1],"utf8").split("\n").filter(Boolean);for(const l of ls){let o;try{o=JSON.parse(l)}catch{continue}; if(o.type!=="user"&&o.type!=="assistant")continue; const c=(o.message&&o.message.content)||[]; const t=Array.isArray(c)?c.map(x=>x.type==="text"?x.text:x.type==="tool_use"?("[TOOL "+x.name+" "+JSON.stringify(x.input).slice(0,200)+"]"):"").filter(Boolean).join(" "):c; if(t&&t.trim())console.log((o.isSidechain?"[SIDE] ":"")+o.message.role+": "+t.replace(/\s+/g," ").slice(0,400))}' <file>
```
Focus each investigator: FIRST few turns (the goal) + LAST ~15 turns (in-flight at crash). Check `TodoWrite` calls
(todo state) and the last `tool_use` before death.

### Per-session findings the investigator returns (six fields)

1. EM session vs subagent sidechain.
2. Session goal / workstream.
3. Git branch + cwd.
4. **What was in flight at crash** — last request, last action, last tool call, pending todos.
5. Governing handoff/plan — cross-ref `state/handoffs/*.md` + `docs/plans/*.md` (grep keywords, read frontmatter:
   status, deployment_state, predecessor).
6. Recovery need — what a successor handoff must capture (next actions, uncommitted-state risk, gates not cleared).

Plus per repo: `git -C <repo> log --oneline -20` + `git -C <repo> status` — what committed near crash time vs what
the crash left dirty. **Uncommitted work is the real loss surface** — enumerate and attribute it to a session.

### Crash-cause agent (Windows)

Runs in parallel; answers "what killed us." Git-Bash can call PowerShell: `powershell.exe -NoProfile -Command '…'`.
- **Unexpected shutdown / power:** `Get-WinEvent` System log IDs **41** (Kernel-Power unexpected), **6008**
  (unexpected shutdown), **1074** (initiated), **6005/6006** (log start/stop).
- **BugCheck / BSOD:** System log ID **1001** (BugCheck).
- **Application crash (Terminal/node):** Application log IDs **1000/1002** — a **WindowsTerminal.exe** faulting-app
  event with exception `0xc0000005` in `Microsoft.Terminal.Control.dll` is the process-tree-kill signature.
- **OOM:** `Microsoft-Windows-Resource-Exhaustion-Detector` (Event **2004**).
- **Reboot boundary:** `(Get-CimInstance Win32_OperatingSystem).LastBootUpTime` — if there's no boot event *after*
  the crash, the machine stayed up (→ disk intact).
- **Our own signals:** correlate `state/runtime-tripwire-fire-log.tsv` (RSS/OOM tripwire) and any `state/` sentinel
  modified that day.
Correlate the event timestamp against the transcript-death mtime — a match within event-log granularity is the cause.
For deeper attribution when the event log is ambiguous (crash dump analysis), escalate to `windows-crash-forensics.md`
(cdb.exe + `!analyze -v`, trusted over event-log attribution). For shared-tree hazards the recovery itself can trigger,
see `concurrent-em-hazards.md`.

## Step 3 — Synthesize + deliver the recovery slate

- **Own repo:** author `kind: recovery` handoffs directly into `state/handoffs/` — one per genuine in-flight
  workstream. Scaffold with `coordinator-doc-new --type recovery --recovers-session <uuid>`, which lays the
  canonical frontmatter down for you.
  Frontmatter: `status: open` (the handoff schema's enum is `open`/`claimed` — `active` fails validation),
  `kind: recovery`, `predecessor:` → the crash-time SHA (the last commit
  before the cluster; `none`/`null` permitted for concurrent crashed threads per `spinoff-handoffs.md`),
  `deployment_state: ready_to_fire` (only `ready_to_fire` surfaces in start ceremonies), `pickup_ready: true`.
  Body: crash context, what was in flight, current disk state, NUMBERED successor next-actions, gates. A successor
  must be able to `/pickup` it and resume without re-reading transcripts. Skip a handoff for trivial sessions
  (zero work written — just re-pickup the memo/task).
- **Sibling repos:** route via claude-klabauter `coordinator/bin/cross-repo-memo` **+ PM relay** (a recovery action on
  another repo's surface is not a direct write — see `cross-repo-communication.md`). One memo per sibling EM,
  self-contained: crash context, per-session state, exact next-actions, and pointers to the governing
  handoffs/plans/SHAs already on *their* disk. Lead with a **dirty-tree preservation / commit-scoping warning** for
  any repo that has uncommitted work at risk. Hand the PM each receiver inbox path for relay.
  Invoked per the precedence ladder in `coordinator/snippets/resolve-coordinator-bin.md` — rung 0 /
  Shape W on a PowerShell host:
  ```
  & "$env:COORDINATOR_SETTINGS_HOME\bin\cross-repo-memo.exe" --to <em> --topic crash-recovery --title "…" --kind fyi --body-file <buffer>
  # (do NOT put the body in %TEMP%/tasks/ — the CLI owns its outbox buffer; --body-file or stdin only)
  ```

### Dirty-tree disposition (own repo)

The crash leaves attributable uncommitted work in the shared tree. Preserve it with **scoped safety-commits**
via `ceremony.commit_v2` (claude-klabauter) — explicit paths, never `git add -A` — so a repeat
crash can't re-lose it and commits auto-push as insurance. The op selects the safe mechanism whether or
not the crash-recovery scan left partial hunks staged, so there's no TOCTOU shape to reason about here
(→ `scoped-safety-commits.md § SC-DR-015`). A safety
commit is preservation, not blessing; note verification status in the message and let the successor re-run gates.
**Attribute each dirty file to a session** and group commits by workstream — two crashed sessions' work must not be
swept into one commit (the concurrent-EM blanket-commit hazard, seen more than once). Delete obvious crash
garbage (0-byte files with mangled names from a botched heredoc/redirect).

### Reconcile before re-doing — a crash-time handoff can be closed-by-drift AND co-consumed by a peer

Before authoring a recovery handoff (or re-doing the in-flight work) for a crashed session, reconcile its baton against what actually happened on disk while it was down. Two independent things can be true at once for a single pre-crash handoff:

- **Closed-by-drift** — its items were all closed or superseded by concurrent commits landing after it was written. A 2-day-old handoff's whole slate was overtaken by 100+ concurrent commits.
- **Co-consumed by a peer** — a concurrent session independently `/pickup`'d the SAME baton (skipping the claim-lock is what let it), and its work turned out *complementary*, not duplicated — the peer even credited this session's SHAs in its memo action.

So the reconcile step is: `git log --all` for peer commits touching the handoff's surfaces, **and read the peer's successor handoff**, before assuming either duplication or lost work. Re-doing work a peer already shipped (or authoring a recovery handoff for a slate that drifted closed) is the failure this check prevents.

### the Game Dev Reviewer rotation across a crash/compaction breaks wsc auto-resolution

A session's `sid` rotates when it restarts after a crash **or** compacts mid-workstream. `wsc_resolve` then greps `consumed_by:`/`claimed_by:` (DR-084 renamed the field, corpus mixed, check both) / commit attribution by the **new** sid and reports single-session + `diff_loc 0` — even though the session consumed a handoff and shipped many commits (some authored by workflow agents under yet other sids). **Do not drive `wsc_commit` off that hollow auto-resolution** during recovery close-out: stamp the predecessor handoff by hand and run the review/commit close-out directly, rather than trusting the sid-keyed auto-resolution to have found the real workstream. (Universal — applies to any post-crash or post-compaction `/workstream-complete`.)

## `~/.claude.json` torn-write recovery

`~/.claude.json` is Claude Code's single per-user runtime config, shared by every concurrent session. When sessions
die mid-write (e.g. a WT crash), the file can be torn (corrupt JSON). Claude Code factory-resets it on the next
launch, silently dropping `mcpServers`, history prefs, and auth.

**Symptom:** Claude Code launches after the crash but no MCP tools are available. Check `~/.claude.json` — if it is
a near-empty `{}` or missing the `mcpServers` key, it was factory-reset by the torn-write.

**Restore the key, never the file.** Re-declare `mcpServers` (`claude mcp add`, or merge that one key with
every session closed), then relaunch. Auth must not be restored; history and prefs regenerate.

**Never restore a whole-file snapshot, and do not back one up at session close.** Every concurrent session
rewrites this file, so a snapshot is stale when taken; writing it back clobbers everything recorded since and
races live writers. A silently-reverted config loses more than a visible factory reset. The backup this
section used to mandate was never once written on any machine — the discharge test failing in plain sight.

**The trigger is the symptom, not the crash.** A crash that left the file intact — the normal case, and the
case on 2026-08-23 — is a reason to leave it alone.

Source: `state/recovery/2026-07-01-claude-json-crash-investigation.md`.

## Prevention

- **Split sessions across separate Windows Terminal *windows* (`wt.exe --new-window`), not tabs.** Every tab
  in one `WindowsTerminal.exe` shares its fate; heavy fan-out streaming is the trigger. Keep Terminal patched.
- **`/handoff` before heavy fan-out waves.** Turns recovery into a `/pickup` instead of a cold reconstruction.

## Two things the second run learned

**Sweep every repo whose sessions died, not the ones named.** A list of affected repos is what someone
remembers, never a boundary. On 2026-08-23 two unnamed repos were swept anyway; one held genuinely
orphaned work and got a baton, the other honestly needed none. Manufacturing a baton to justify a
dispatch is the opposite failure — say "no baton needed" and why.

**A peer's blanket `safety` commit will land before you finish.** Expect a bare, undifferentiated sweep
of the whole crash-dirty tree — 69 files in one claude-klabauter commit, 485 in ue-addon's — landing days later
with no per-session attribution. The work is preserved, not lost, so every baton must say which of its
own work sits inside that commit. A baton that says "re-do this" against work already on disk is worse
than no baton.

Prior runs: `state/recovery/2026-07-01-crash/` (18 sessions, Terminal `0xc0000005`, cause attributed),
`state/recovery/2026-08-23-crash/` (~65 transcripts, six repos, no OS-logged fault).
