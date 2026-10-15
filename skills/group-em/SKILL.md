---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo; never plan or author for them."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em` switches this session into monitoring the other sessions in the same repo and moving
them along. A **mode a session enters, not an operation on a target**.

**THIS BODY IS A SNAPSHOT, FROZEN WHEN YOU ENTERED, CARRYING NO VERSION.** Before citing it as
authority for anything MECHANICAL — a signature, a module path, a flag, a refusal vocabulary —
read that passage from disk.

**PM-GATED — only on an explicit PM ask, never EM-initiated.** A description-prefix convention
(as `staff-session`, `spinoff`, `roadmap-planning`); no hook enforces it.

**Dispatch authorization — invoking this skill IS the request, for three specific dispatches
only:** the approvability judge (§ Delegated approve-for-execution, step 4),
`coordinator:group-em-assistant` at entry, and § Fleet inbox grind's saved
`fleet-inbox-blitz` workflow with the assistants it raises. Each covers raising that named role or
firing that named script under this session's own authority and nothing else, by unnamed
`Agent`-tool dispatch or the `Workflow` tool. **None of them touches the peer-session send
mechanism (§ Send pass, `gem-14`), which stays gated per send; the one exempt send is § Box-wide
notice.**
Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## Entry — already done by the time you read this

**Typing `/group-em` fires entry.** `hooks/scripts/group-em-autofire.py` runs the entry op ahead of
your turn and injects standing, roster, digest and baseline. **If that context is absent, entry did
not happen** — the hook fails open, so silence proves nothing. Run `<plugin-root>/bin/group-em-enter.py --repo <root>
--session-id <your sid>` and find out why. **`--session-id` is not optional** — it defaults to
`$CLAUDE_SESSION_ID`, unset in many shells; without it the op refuses (exit 2). (Every
`<plugin-root>/bin/` CLI here is plugin-local with no settings-home launcher — resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, never cwd-relative.)

The op shims the engine's `groupem.enter` in-process. **Exit 5 means a refused standing** — a live or unaccounted-for incumbent holds the role;
`roster`/`digest`/`baseline`/`teammates` are absent from the payload, not empty. **Exit 2 means no
resolvable session id.** Payload shape: `coordinator_core/ops/group_em_enter.py`'s module docstring.

Do not import `read_pass` / `send_pass` directly. They are the op's collaborators.

**Standing first, last writer wins.** Whoever invokes most recently holds the role; entry never
refuses over an incumbent and there is no override flag. Re-entry by the holder is a refresh.

### Owed sends, all exempt from § Send pass's gates

**A displaced holder that is still running is OWED a message this turn.** `displaced_holder` and
`displaced_holder_live` arrive in the entry context. Not live means nobody to tell.

**The owed message also tells it to release its watch, which the crown does not hold:** TaskStop its watch shell, then confirm the subprocess is gone. It must not
re-arm under the lost role.

**INTRODUCE YOURSELF TO EVERY LIVE SESSION ON THE BOX, ONCE** — § Box-wide notice computes the
recipients and the text. Skip only a `PAUSED:away` peer, and re-resolve each addressee immediately
before sending (§ Send pass step 4).
Rationale for the five constraints below: `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing.md` § Owed introductions.

1. **Say four things and stop:** who you are (name and session id); that you hold the Group EM
   standing for this repo; what to route to you; and **that no reply is wanted**, stated
   explicitly.
2. **Never ask peers to route their PM reports through you.** "The PM is typing into that session"
   is unobservable from here. Key it to something CHECKABLE: **a session answering a question just
   asked in this exchange** has a direct channel.
3. **It is an introduction, not a nudge, and the difference is enforced by content: it asks
   nothing.** No question mark anywhere.
4. **It arms no cooldown and is not an offer.** Only `build_send_digest` emitting an entry arms a
   peer's throttle.
5. **Once per PEER, not once per wake, tracked by session id AND name** — either can change
   under the other; on ambiguity re-introduce. The introduced set is durable: `_record_introduction`
   in `coordinator/bin/group-em-box-notice.py` appends a cooldown-ignored row to the send log
   (`.coordinator-local/subagent-share/<this-session-id>/group-em-send-log.jsonl`).

## Box-wide notice

**The standing is box-wide: every live named session, in any repo, is told when it begins and when
it ends.** `group-em-autofire.py` cannot send (`SendMessage` is a model tool), so it does the
mechanical part and prints it in the entry context as `BOX NOTICE OWED`: one text and the exact
recipient list from `claude agents --json`, de-duplicated, you excluded, `PAUSED:away` peers
skipped, peers you already introduced skipped. **Send that text to each, this turn.** It follows
the introduction content rules above: it asks nothing, says no reply is wanted, and carries your
name, session id and `SendMessage` address. The displaced holder's owed message is separate and still owed.

**Before this session ends, run `<plugin-root>/bin/group-em-box-notice.py --kind ended --repo
<root> --session-id <your sid>`.** It stands the nomination down (holder-matched; a refusal empties
the recipient list) and prints the no-Group-EM text and recipients. Send it. No `SessionEnd` hook
can message peers; a holder that dies without this step leaves the box unannounced until the
next entry. Tripwire:
`A-GROUP-EM-STANDING-THE-BOX-WAS-NEVER-TOLD-ABOUT`.

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** — never plan bodies, stub content, or roadmap
decisions for the sessions it watches. **DOES coordinate execution waves and cross-session
sequencing**.

## Entry dispatches both standing watchers

**ENTRY DISPATCHES BOTH STANDING WATCHERS — `group-em-assistant` AND THE WATCH IT ARMS ARE
MANDATORY.** **Raise the
pair yourself, from this session**: a watcher belongs to whoever raised it, so one raised by
another session leaves you watching while believing you were relieved.

**"Entry" here means you, on entering the mode — not the entry op.** `group-em-enter.py` assembles
and dispatches nobody, and the autofire hook is silent either way. Nothing re-runs entry. In this order, as your first act:

1. **`coordinator:group-em-assistant`** — dispatch it, unnamed. Your standing reader: transcript
   tails, baton claimants, what landed on a path since a SHA, **park-spool triage**, and
   read-and-report asks. It arms nothing and holds no timer. Full remit:
   `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md`.

   **DISPATCH `group-em-assistant` WITHOUT A `name`.** A named `Agent` call spawns an in-process
   teammate, and a teammate is never re-invoked by a `Monitor` it armed. Unnamed, it wakes on your `SendMessage`. Tripwire:
   `A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

2. **The watch and its background run — yours, launched from this main conversation.** A subagent
   cannot hold the watch: it missed 4 of 4 expiries, holding no timer. Arm the watch by running, through the Bash tool with
   `run_in_background: true`:

       "$COORDINATOR_SETTINGS_HOME/bin/group-em-watch" --repo-root <root> --group-em-session-id <your sid> --until-event --tick-interval-seconds 30

   The run's completion is the wake. Its wire is filtering `PARKED|WAITING|GONE|POLL-ERROR`, the only lines
   it prints (drop nothing it matches: A-TURN-ENDED-IS-THE-WAKE-NOT-NOISE), then exits 0; any failure
   exit also completes it, so a failure wakes you too. After acting, read the fleet (`--status`)
   for anything that moved, then relaunch the same command. Never wrap it in a `Monitor`.
   **`--group-em-session-id` is passed explicitly, never defaulted** — a separate id from
   `--caller-session-id`. The watch emits one line per peer entering a parked state (per
   `read_pass.classify_peer`), silent while that peer's cooldown is armed. The `--until-event` run
   never refuses; the owed send handles displacement (§ Owed sends). Never hand-edit the record.
   `--status` answers "is a watch alive here?" (0 alive, 1 not running, 2 unknown — never green);
   `--once` fires a single poll.

3. **Events wake you; no cron tick exists.** Your wakes are: the background watch run's
   completion; peer `SendMessage`s; `notify_when_idle` one-shots (main conversation only); and
   the **memory governor** `Monitor` (`<plugin-root>/bin/group-em-memory-governor.py`). At
   `CRITICAL` kernel pressure it suspends the youngest heavy command, never a deploy or language
   server, and resumes it when the box calms. On a PAUSED line, tell its owner. You send no hold
   or clear messages: `WARN` and swap-out hold nothing. Admit a heavy command when its declared
   whole-tree peak + 8 GiB <= kernel-available; a GO names peak, launch gate, 8 GiB stop floor. Tripwire:
   `A-BOX-MEMORY-IS-THE-KERNEL-VERDICT-NOT-A-FREE-PAGES-FLOOR`. The GPU is one slot: embedding writes
   and UE GPU work never overlap. Tripwire: `A-GPU-IS-ONE-SLOT-EMBED-SIDECARS-AND-UE-GPU-WORK-NEVER-OVERLAP`. A `CronCreate` poll over an event surface is a poll where an event exists. Tripwire: `A-CRON-TICK-IS-A-POLL-WHEN-EVENTS-EXIST`.

   **You sequence box capacity.** Contended work (test suites, builds, reindexes, UE
   editor/cook runs, large workflows, memory-heavy agents) and any queue where peers take
   turns (a suite mutex, a shared-tree merge, a publish) is yours to order. Peers ask you for a
   slot; you release them in order as headroom allows. **Cap what agents run,
   not how many agents run:** GO terms name the command classes (unscoped vitest and watch
   modes, `tsc` beyond one per session, builds, `pnpm -r`, long-lived shells) and **never** a
   workflow's width, concurrent rows or agent count, even if a peer proposes one. A GO never restates width, test scope or flags: the engine's emitted script owns them. Tripwire: `A-BOX-CAP-COUNTS-COMMANDS-NOT-AGENTS`.
   A slot is occupied only by a live PID: a "build running" report names the PID from
   the process table, and you confirm it is alive before holding anyone back.
   Tripwire: `A-RUNNING-CLAIM-CARRIES-A-LIVE-PID`.
   **A deploy slot names its commit set, never `HEAD`:** before the GO, list
   `<live-sha>..<target-sha>`. A deploy builds only from committed shas. A range carrying others'
   commits is yours to rule on from a per-feature release note of what a visitor sees. Tripwire: `A-DEPLOY-THAT-BUILDS-FROM-DISK-SHIPS-PEERS-UNCOMMITTED-EDITS`.

**YOU ARE WHERE "UP" ENDS.** Every gate a peer surfaces up lands on you and is decided by you,
under the PM's delegation:
- a slot, a prod write, a deploy, a release, a publish;
- a ruling, a doctrine-adjacent call.

"Publish", "release" and "merge" in the global external-facing list name what is gated, not who
holds the gate; while you hold the standing, you hold it. Never hand one to the PM, even
bundled with another PM act. A direction call you cannot make goes to the APM.
The PM gets only an act that needs the human's own hands, such as an interactive login, stated
as the act (`! firebase login --reauth`), never as "needs you". Tripwire:
`A-GROUP-EM-IS-WHERE-UP-ENDS`.

### Arming the watch — every refusal and every false green

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.**

- Prefer the trampoline; confirm the subprocess started rather than trusting its silence.
- **Arm within the entry lease:** an entry that never arms is a crown with no watch.
- **Verification is a background task id you can name plus `--status`** fresh with
  `tick_source: cron` and `subscribed_peers` above zero. The record reads stale between a
  completion and the relaunch.
- **`--status` saying ALIVE is not verification** — check `subscribed_peers`.
- **The engine must be importable**, which it is not from the repo you are Group EM for — use
  `$COORDINATOR_SETTINGS_HOME/bin/group-em-watch` (`.exe` on Windows; on PowerShell, `&` + forward slashes).

Mechanics: `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md`
§ Arming the watch.

### The wires — who arms what, and how fast you would know

**THE WATCH RUN IS YOURS: THE HOLDER RELAUNCHES THE BACKGROUND RUN ON EACH COMPLETION; NEVER WRAP THE WATCH IN A `MONITOR`.** Tripwire:
`A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

**The `notify_when_idle` one-shot cannot be delegated either** — main conversation only; it
fires once per peer, so re-arm per peer.

**You act on the watch's events yourself;** `group-em-assistant` is the reader you ask: park-spool
triage, transcript tails, claimants. **The park spool is its surface, not yours:**
ask it for the spool before the file. **It triages and reports; it never nudges
a peer** — nudging is the Group EM's own.

**Verify the wire's holder:** a nameable shell task id and `--status` ALIVE with `subscribed_peers` > 0.
Worked case: `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-entry-teammates.md`.

### Liveness instruments — two sanctioned, one banned, and you read the banned one constantly

**`ListAgents`' `busy`/`idle` IS the harness registry's `status`, banned as an input to any
liveness, reachability, or claim verdict.** `idle` means unknown, never quiet. Tripwire: `LISTAGENTS-BUSY-IS-A-BANNED-LIVENESS-INPUT`.

**Sanctioned, exhaustively: the oracle's verdict, and `last_tick_at` age in
`state/group-em-watch.json`**, compared against the record's own `next_expected_by` rather than a
fixed threshold. Do not shape this as a process-table check. **Resource-usage proxies (CPU,
memory, I/O) are banned too.** Rationale: `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § Liveness.

**A PM-reported dead watcher is never confirmed from the session list.** Answer from `last_tick_at` age and name the
instrument.

### Every wake declines in writing, and stamps it to disk

**Each wake records a DECLINATION for every roster entry it does not message** — which gate failed
and why.

**And each wake STAMPS them to disk** via the engine's `coordinator_core/group_em/watch_heartbeat.py
:: stamp` — not this skill's local `watch_heartbeat.stamp`; the signatures differ and the local shape
raises against the engine copy. Signature and argument rules:
`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § Stamping the heartbeat.

**The wake has a producer; you arm nothing for it.** `state/group-em-watch-spool.jsonl` gets one
record per park, appended by every session's own `Stop`
(`coordinator/hooks/scripts/group-em-park-spool.py`). The spool retains at least the last 30
minutes of parks.

A Group EM who looks only when the PM asks has made the PM the watcher.

**What the watch is FOR:** sessions asking permission for EM-autonomous acts they already
recommended; break-class defects handed up as "worth your eye"; a session idling on a peer repo
while holding a repo-agnostic fallback it found. **Not** finding sessions something to do.

**Run the altitude test on the way OUT of a turn, not only when deciding to intervene.** *"This
session has been idle 35 minutes, do you want it doing something?"* is the EM's call.

## The drive loop — what you are driving peers TOWARD

The Group EM owns four of these five steps; **step 4's clear is the PM's act**.

1. **Drive to execute.** A reviewed plan sitting on execution authorization is yours to release.
2. **Drive to workstream-complete.** Toward the close, not merely away from idleness.
3. **Troubleshoot alongside them until the primary exit criterion is met** — a different act from
   nudging. Stays inside the no-authoring boundary.
4. **When the ceremony completes, the PM clears them.** Only a successfully completed ceremony
   establishes out-of-work — a peer's own "I'm done" does not. `/clear` is a human act you cannot
   issue to a peer. A session at this point is **done and awaiting clear**, never your failure —
   say so plainly.
5. **Assign something new from the daily priority set.** PM-owned and per-day; ask for it if you
   do not have one.

**No step here is discharged by an artifact, and your own report cannot show the gap** — re-read
this section deliberately. Worked cases: the standing wiki page. Tripwire: `A-SELF-REPORTED-CLOSE-IS-NOT-A-COMPLETED-CEREMONY`.

## No registration ceremony, no persistence

Nothing is written on invoke or cleaned up on exit. No roster, address, or reachability fact for
any peer is persisted; every fact is re-derived live.

**One carve-out: the send log.** `build_send_digest` appends to
`.coordinator-local/subagent-share/<this-session-id>/group-em-send-log.jsonl` — session-scoped, so a new Group EM
starts with an empty cooldown.

## DACI is a frame, not a registry

A `/group-em` session **is** that repo's Driver for as long as it runs. Do not build a Driver
registry or roster.

## Stale-read discipline

Peer state is re-read immediately before acting on it, never from an earlier snapshot, and
**never** by calling the entry op a second time inside one wake (§ Send pass step 1).

## Gating granularity — entry AND per send

**Entry stays PM-gated** by this file's prefix convention: who may enter the mode at all.

**The send is gated separately, per send, and entry-gating never satisfies it.** The send is where
the `ask-before-external-action` question lives, justified by **cost to the receiver**, never the
sender's convenience.

### Standing check

**Confirm this session still holds the nomination**: `<plugin-root>/bin/group-em-nomination.py who
--repo <root> --json` (read-only). Never re-run `group-em-enter.py` to answer this — it re-claims
and re-arms the send digest's cooldowns (§ Send pass step 1).

## Read pass (gem-13)

The enumerate-and-classify ladder lives in `read_pass.py` beside this file, invoked through §
Entry's op rather than imported. `build_roster(repo_root)` for the classified population,
`build_candidate_roster(repo_root)` for the paused-only shortlist. Full ladder: that file's module docstring.

## Send pass (gem-14)

`send_pass.py` turns `build_roster`'s **full** population into **one digest per invocation**
(`build_send_digest`). It selects and throttles; **it does not send.**
**`roster` IS NOT THE POPULATION — it is the shortlist**, `build_candidate_roster`'s output. A
human adjudicates it. `undischarged_obligations: None` means no ledger exists, never that the peer
owes nothing.

**Compare `roster_considered` — the enumerated count entry reports top-level — against the room,
never `len(roster)`.** A `roster` smaller than `roster_considered` is NORMAL; a `roster_considered`
smaller than the sessions you know are running is `unknown`, never quiet. Worked case:
`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § The roster is not the population.

Two settling reads: `claude agents --json`, and `python3 -m coordinator_core.group_em.idle_report
--repo-root <root> --group-em-session-id <your sid>`. Pass `--group-em-session-id` even though the
CLI accepts its omission silently — omitting it degrades offer-log suppression rather than erroring.

**Ledger rows can arrive from the engine plane** via
`state/subagent-share/<sid>/obligations-inbound.jsonl`; this plane is the ledger's sole writer. Contract:
`coordinator/docs/wiki/cross-repo-communication/obligations-inbound-intake.md`. Tripwire:
`A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op already built both plus a `baseline` delta. **Act on that payload — do not re-run
   the entry op to refresh it**, since `build_send_digest` arms cooldowns as it emits.
2. Present it (`suppressed`: why a peer was held; `truncated`: re-evaluated next wake;
   `unrecorded`: the cooldown write failed).
3. **Per entry you intend to message, declare both gates in prose before sending:**
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or is
     this a settled ask? A settled ask is a memo.
   - **GATE 2 (receiver).** Cheaper to them now than later? **GATE 2 has no instrument** — it rests
     on what you already know about that peer.
   - **Either gate unclear → the memo channel.** Not a degraded mode.
4. **Re-resolve the address from the SESSION ID immediately before sending, and treat a refusal as
   a refusal.** The engine's `coordinator_core.group_em.send_pass.resolve_addressee(repo_root,
   peer_session_id)` (import it with the engine root on the path) returns the name that session
   answers to right now, or `None` — do not send on `None`. **`repo_root` is the PEER's repo, not
   yours:** the roster it reads is scoped to that root, so a peer in another repo resolves `None`
   against yours.

   **Resolve from the id, never validate the name.** Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

**Never loop over `entries` sending.** `SendMessage` is in `allowed-tools`; the gate is this
paragraph.

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason`. Tripwire:
`A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## The escalation screen — a claimed PM item is presumed yours until it survives

**When a session says it has something for the PM, it is wrong about 19 times in 20** — the PM's
own measured prior. Treat "this needs the PM" as a claim to test, never routing already done.

- **"Next: review."** The next step in a procedure the session owns. Push it — unless the plan is
  small enough that review is not a step at that size, in which case name the actual next step
  instead. Do not grant a permission the session already holds.
- **"Variable `x` or `xy`?"** Engineering, decided by whoever holds the file. Push it — do not
  answer it either.
- **"Do I execute?"** The one with a real question, answerable by you — below.
- **"This is irreversible."** Only a publish to a server the fleet does not own is; push a local write back as the session's own (`A-LOCAL-WRITE-IS-RECOVERABLE-ONLY-PUBLISHING-IS-IRREVERSIBLE`).

**Peers bring you a second opinion before asking the PM.** Answer engineering calls
yourself, or dispatch `coordinator:staff-eng` for a viability read. Route scope and direction to the
APM. Pass the PM only what survives this screen, in plain words: what happens, to which server, why it cannot be undone.

**This is a model disposition, not a peer failing.** Say so when you push, and push anyway.

### Push, do not nudge

**"Do you need anything?" is a failure, not a gentler success.** It hands the decision back to the
session that already froze on it. Same for "want me to...?", "let me know if...".

A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark,
no offer, no conditional; one clause of reason.

You are not pushing anyone past a gate their own skill names — a gate is a considered refusal with
a named reason; hesitation is the absence of one. Push the second, never the first.

### "Do I execute?" — yours to answer, with a viability read

The PM has delegated this call. **Do not read the plan into your own context.** Dispatch
`coordinator:staff-eng` for a viability read.

**This does NOT route around the rubric.** Where a plan needs the formal `execution_authorized_by`
stamp, § Delegated approve-for-execution is the only path. This lighter call answers *"should I get
on with it"* for work that does not need that stamp.

## Delegated approve-for-execution procedure

The Group EM may take the PM's execute-plan turn on one condition: the plan is
reversibility-eligible and a rubric-scored judgment against its own prime exit criterion clears a
locked threshold (8 of 8, no dimension scoring 0).

1. **Standing check** (§ Standing check).
2. Run `<plugin-root>/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). `eligible:
   false` → escalate per the threshold page's shape, stop, do not dispatch. This CLI is the single
   source of truth.
3. Confirm the plan's falsifier baseline shows the prime exit criterion false **and that a blinded
   `coordinator:exit-criterion-falsifier` authored it**:
   - **Content.** Absent or already true → escalate, stop.
   - **Provenance.** A self-authored baseline voids the guarantee. Provenance lives in the plan BODY, a prior
     `state/review-trail/approvability/` record, or this session's own dispatch of the falsifier.
     **If none of the three establishes it, treat it exactly as a missing baseline and dispatch.**
   - **Instrument soundness.** A FALSE baseline proves the criterion false, never the instrument
     sound. Ask: **what would have to be true for this to print TRUE, and is any of it reachable in
     the world the fixture builds?** Unreachable → escalate with that reason named.
   Tripwires: `A-SELF-AUTHORED-FALSIFIER-SATISFIES-THE-CHECK-AND-VOIDS-IT`,
   `A-FALSE-BASELINE-PROVES-THE-CRITERION-FALSE-NOT-THE-INSTRUMENT-SOUND`,
   `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
4. Dispatch the named Opus persona (the PM's chosen reviewer, at the PM's chosen effort) with the
   plan path and the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing else.
   Authorship blinding is a hard constraint.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`) and
   validate it with C9's `--validate-record` before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value — a
   plan the PM already authorized needs no delegated approval. Otherwise `review-exec-auth-stamp
   stamp <plan-path> --by "GROUP-EM:<session-id>" --append-note "<record-path>"`. On `escalate`,
   emit per the threshold page's shape — do not stamp.
7. **The stamp carries a standing offer: you produce criterion evidence the plan's author should
   not.** When a plan's terminal evidence is a live act rather than a test run, offer to perform it
   as the Group EM and let the author verify. Where the separation is not free, say so and let it
   go. Tripwire: `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.

## Fleet inbox grind

**On entry, when `coordinator.feature.cross_repo_memos` is on for the box, firing the saved
workflow is part of the request — not a decision.** The autofire hook prints the exact
invocation as `FLEET INBOX GRIND, FIRE NOW`:

    Workflow({scriptPath: "<plugin-root>/workflows/fleet-inbox-blitz.mjs", args: {repos: [...], gem: {...}}})

Fire it as your first act after arming the watch, unattended. `repos` is the fleet map
(`machine-local get repos.*`, de-duplicated, git repos carrying `state/cross-repo/inbox`) — every
repo, whether or not an EM is live in it. Disposition rules: `workday-start.md` §1.45a. **Do not hand-author a variant.** If the
entry context carries no invocation, check the flag, and fire with `repos` read from the fleet map. Tripwire: `A-GROUP-EM-HAND-AUTHORING-THE-INBOX-WORKFLOW`.

## Cross-repo commit authority

**Committing in any fleet repo is presumed and inherent to this role** while this session holds
the standing (`group-em-nomination.py who --self`); it needs no per-session PM assent. Guardrails,
unchanged from the retired-grant rule: scoped pathspec commits only (never `git add -A`/`.`/`commit
-a`), no destructive git ops, never leave a sibling's tests red. Engine-subject work stays
the engine repo's: memo it, do not author it. The grant ends when the standing does.

## Anti-scope

- **No auto-send.** `send_pass.py` selects and throttles; it holds no transport. Every send is an
  explicit per-send act with both gates declared. An unattended sender, a loop that messages each
  digest entry, or any `Stop`-registered trigger is out of scope.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** A nudge on an
  observed registry transition is preserved; a tick that messages everyone it can see is forbidden.
  A timing predicate re-derives `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down.
- **That ban is about AUTOMATION, never attentiveness.** A holder re-deriving the roster each turn
  and judging it is what the ban preserves.
- **The three dispatch grants at the top are scoped to their own named dispatch.** Messaging
  **peer sessions in their own windows** stays an `ask-before-external-action` question no
  dispatch grant dissolves.
- `/autonomous` is a naming precedent only; its `/tmp` sentinel is not borrowed.
