---
name: group-em
description: "PM-GATED. Box-wide: monitor peers; never plan or author for them."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke from the group-em home to take box-wide G-EM standing]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em`, run from the machine-local group-em home, switches this session into box-wide G-EM
standing: monitoring other sessions and moving them along; a **mode, not an operation**. Cockpit contract:
`coordinator/docs/wiki/cross-repo-communication/gem-cockpit-contract.md`.

**Outside the home, `/group-em` renders NOT ENTERED** (`group-em-home ensure`).

**THIS BODY IS A SNAPSHOT, FROZEN WHEN YOU ENTERED, CARRYING NO VERSION.** Before citing it as
authority for anything MECHANICAL (a signature, module path, flag, refusal vocabulary), read that
passage from disk.

**PM-GATED, never EM-initiated:** the PM types `/group-em` or starts a session in the home
(`A-SESSION-STARTED-IN-THE-GROUP-EM-HOME-ENTERS-GROUP-EM`).

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
not happen** — the hook fails open. Run `<plugin-root>/bin/group-em-enter.py --repo <root>
--session-id <your sid>` and find out why. **`--session-id` is not optional**; without it the op
refuses (exit 2). (Every `<plugin-root>/bin/` CLI here is plugin-local — resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, never cwd-relative.)

**Exit 5 means a refused standing** — a live or unaccounted-for incumbent holds the role;
`roster`/`digest`/`baseline`/`teammates` are absent from the payload. **Exit 2: no resolvable
session id.** Payload shape: `coordinator_core/ops/group_em_enter.py`'s module docstring.

Do not import `read_pass` / `send_pass` directly. They are the op's collaborators.

**Last writer wins.** The most recent invoker holds the role; entry never refuses over an incumbent (no override flag); re-entry by the holder is a refresh.

### Owed sends, all exempt from § Send pass's gates

**A displaced holder that is still running is OWED a message this turn.** `displaced_holder` and
`displaced_holder_live` arrive in the entry context; not live means nobody to tell.

**The owed message also tells it to release its watch:** TaskStop its watch shell, confirm the
subprocess is gone, and never re-arm under the lost role.

**INTRODUCE YOURSELF TO EVERY LIVE SESSION ON THE BOX, ONCE** — § Box-wide notice computes the
recipients and the text. Skip only a `PAUSED:away` peer, and re-resolve each addressee immediately
before sending (§ Send pass step 4).

1. **Say four things and stop:** who you are (name and session id); that you hold the Group EM
   standing for this repo; what to route to you; and **that no reply is wanted**, stated
   explicitly.
2. **Never ask peers to route their PM reports through you.** "The PM is typing into that session"
   is unobservable from here; key it to something CHECKABLE, such as **a session answering a
   question just asked in this exchange**.
3. **It asks nothing.** No question mark anywhere.
4. **It arms no cooldown and is not an offer.** Only `build_send_digest` emitting an entry arms a
   peer's throttle.
5. **Once per PEER, not once per wake, tracked by session id AND name**; on ambiguity
   re-introduce. `_record_introduction` in `coordinator/bin/group-em-box-notice.py` makes the set
   durable in the send log
   (`.coordinator-local/subagent-share/<this-session-id>/group-em-send-log.jsonl`).

## Box-wide notice

**Every live named session, in any repo, is told when the standing begins and when it ends.**
`group-em-autofire.py` cannot send, so it prints `BOX NOTICE OWED` in the entry context: one text
and the exact recipient list (from `claude agents --json`; you, `PAUSED:away` and
already-introduced peers excluded). **Send that text to each, this turn.** It follows the
introduction rules above. The displaced holder's owed message is separate and still owed.

**Before this session ends, run `<plugin-root>/bin/group-em-box-notice.py --kind ended --repo
<root> --session-id <your sid>`.** It stands the nomination down (holder-matched; a refusal empties
the recipient list) and prints the no-Group-EM text and recipients. Send it; no `SessionEnd` hook
can. Tripwire:
`A-GROUP-EM-STANDING-THE-BOX-WAS-NEVER-TOLD-ABOUT`.

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** — no plan bodies, stub content, or roadmap
decisions for watched sessions. **DOES coordinate execution waves and cross-session sequencing**.

## Entry dispatches both standing watchers

**ENTRY DISPATCHES BOTH STANDING WATCHERS — `group-em-assistant` AND THE WATCH IT ARMS ARE
MANDATORY.** **Raise the pair yourself, from this session**: a watcher belongs to whoever raised
it.

**"Entry" here means you, on entering the mode — not the entry op:** `group-em-enter.py` dispatches
nobody and nothing re-runs entry. In this order, as your first act:

1. **`coordinator:group-em-assistant`** — dispatch it, unnamed. Your standing reader: transcript
   tails, baton claimants, what landed on a path since a SHA, **park-spool triage**, and
   read-and-report asks. It arms nothing and holds no timer. Full remit:
   `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md`.
   **DISPATCH `group-em-assistant` WITHOUT A `name`:** a named `Agent` call spawns an in-process teammate, and a
   teammate is never re-invoked by a `Monitor` it armed. Unnamed, it wakes on your `SendMessage`. Tripwire:
   `A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

2. **The watch and its background run — yours, launched from this main conversation.** A subagent
   cannot hold the watch: it missed 4 of 4 expiries. Arm it by running, through the Bash tool with
   `run_in_background: true`:

       "$COORDINATOR_SETTINGS_HOME/bin/group-em-watch" --repo-root <root> --group-em-session-id <your sid> --until-event --tick-interval-seconds 30

   The run's completion is the wake. Its wire is filtering `PARKED|WAITING|GONE|POLL-ERROR`, the only lines
   it prints (drop nothing it matches: A-TURN-ENDED-IS-THE-WAKE-NOT-NOISE), then exits 0; any failure
   exit also completes it. After acting, read the fleet (`--status`) for anything that moved, then
   relaunch the same command. Never wrap it in a `Monitor`.
   **`--group-em-session-id` is passed explicitly, never defaulted** — a separate id from
   `--caller-session-id`. The watch emits one line per peer entering a parked state (per
   `read_pass.classify_peer`), silent while that peer's cooldown is armed. The `--until-event` run
   never refuses. Never hand-edit the record.
   `--status` answers "is a watch alive here?" (0 alive, 1 not running, 2 unknown — never green); `--once` fires a single poll.

3. **Events wake you; no cron tick exists.** Your wakes are: the background watch run's
   completion; peer `SendMessage`s; `notify_when_idle` one-shots (main conversation only); and
   the **memory governor**. Run `python -u <plugin-root>/bin/group-em-memory-governor.py >>
   <home>/scratch/governor.log 2>&1` once, `run_in_background`, for the whole standing; the wake is a
   second background run, `<plugin-root>/bin/group-em-memory-governor-wait.py <that log>`, which
   exits on the first new line. Relaunch only the waiter; never filter its line, never wrap either in
   a `Monitor`. On a PAUSED line, tell its owner. You send no hold or clear messages: `WARN` and swap-out hold nothing. Admit a heavy command when peak + min(25% of peak, 8 GiB) <= kernel-available AND commit + peak <= commit limit:
   `<plugin-root>/bin/box-memory-snapshot.py --admit-peak <GiB>` (HOLD is exit 4); floor 2.5 GiB. Also on demand:
   `trim-file-cache` (the PM runs it elevated; the governor's `GOVERNOR CACHE-TRIM-HINT` line prints it),
   `box-memory-trim-ws`, `box-memory-tree`, `box-memory-wait-pid`. Copies: queued `robocopy /J`. Tripwire:
   `A-BOX-MEMORY-IS-THE-KERNEL-VERDICT-NOT-A-FREE-PAGES-FLOOR`. The GPU is one slot: embedding writes
   and UE GPU work never overlap (`A-GPU-IS-ONE-SLOT-EMBED-SIDECARS-AND-UE-GPU-WORK-NEVER-OVERLAP`).
   A `CronCreate` poll over an event surface is a poll where an event exists
   (`A-CRON-TICK-IS-A-POLL-WHEN-EVENTS-EXIST`).

   **You sequence box capacity.** Contended work (test suites, builds, reindexes, UE
   editor/cook runs, large workflows, memory-heavy agents) and any queue where peers take
   turns (a suite mutex, a shared-tree merge, a publish) is yours to order: peers ask for a
   slot; you release them in order as headroom allows. **Cap what agents run,
   not how many agents run:** GO terms name the command classes (unscoped vitest and watch
   modes, `tsc` beyond one per session, builds, `pnpm -r`, long-lived shells) and **never** a
   workflow's width, concurrent rows or agent count. Tripwire: `A-BOX-CAP-COUNTS-COMMANDS-NOT-AGENTS`.
   A slot is occupied only by a live PID: a "build running" report names the PID, and you confirm
   it is alive before holding anyone back. Tripwire: `A-RUNNING-CLAIM-CARRIES-A-LIVE-PID`.
   **A deploy slot names its commit set, never `HEAD`:** before the GO, list
   `<live-sha>..<target-sha>`; rule on others' commits in that range from a release note.
   Tripwire: `A-DEPLOY-THAT-BUILDS-FROM-DISK-SHIPS-PEERS-UNCOMMITTED-EDITS`.
   **A prod-migrate GO names every migration the command applies:** list
   `<ledger-tail>..<pending-head>`, and check a constraint-replacing migration against the
   deployed revision's writers. Tripwire: `A-PROD-MIGRATE-GO-NAMES-LESS-THAN-THE-COMMAND-APPLIES`.
   **An install rewriting live plugin/config state needs your GO:**
   `A-FULL-INSTALL-SUBSTRATE-RUN-FOR-ONE-FORWARDER-HAS-MACHINE-WIDE-BLAST-RADIUS`.

**YOU ARE WHERE "UP" ENDS.** Every gate a peer surfaces up (a slot, a prod write, a deploy, a
release, a publish, a ruling, a doctrine-adjacent call) lands on you and is decided by you, under
the PM's delegation. "Publish", "release" and "merge" in the global external-facing list name what
is gated, not who holds the gate. Never hand one to the PM, even bundled with another PM act. A
direction call you cannot make goes to the APM. The PM gets only an act that needs the human's own
hands, such as an interactive login, stated as the act (`! firebase login --reauth`). Tripwire:
`A-GROUP-EM-IS-WHERE-UP-ENDS`.

### Arming the watch — every refusal and every false green

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.**

- Confirm the subprocess started rather than trusting its silence.
- **Arm within the entry lease:** an entry that never arms is a crown with no watch.
- **Verify with a nameable background task id plus `--status`** fresh, `tick_source: cron`,
  `subscribed_peers` above zero (ALIVE alone is not).
- Use `$COORDINATOR_SETTINGS_HOME/bin/group-em-watch` (`.exe` on Windows), never an engine import.

Mechanics: `group-em-assistant-remit.md` § Arming the watch.

### The wires

The watch run is yours (`A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`). `notify_when_idle` is
main-conversation only, once per peer. The park spool is `group-em-assistant`'s surface: ask it
first; it never nudges. Worked case: wiki `group-em-entry-teammates.md`.

### Liveness instruments

**`ListAgents`' `busy`/`idle` is banned as an input to any liveness, reachability, or claim
verdict.** `idle` means unknown, never quiet. Tripwire: `LISTAGENTS-BUSY-IS-A-BANNED-LIVENESS-INPUT`.

**Sanctioned, exhaustively: the oracle's verdict, and `last_tick_at` age in
`state/group-em-watch.json`**, compared against the record's own `next_expected_by`. Process-table
checks and resource-usage proxies (CPU, memory, I/O) are banned. Rationale:
`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § Liveness.

A PM-reported dead watcher is confirmed by `last_tick_at` age, never the session list.

### Every wake declines in writing, and stamps it to disk

**Each wake records a DECLINATION for every roster entry it does not message** — which gate failed
and why — **and STAMPS them to disk** via the engine's `coordinator_core/group_em/watch_heartbeat.py
:: stamp`, not this skill's local `watch_heartbeat.stamp` (the signatures differ). Argument rules:
`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § Stamping the heartbeat.

**The wake has a producer; you arm nothing for it.** `state/group-em-watch-spool.jsonl` gets one
record per park, appended by every session's own `Stop`
(`coordinator/hooks/scripts/group-em-park-spool.py`), retained at least 30 minutes.

**What the watch is FOR:** sessions asking permission for EM-autonomous acts they already
recommended; break-class defects handed up as "worth your eye"; a session idling on a peer repo
while holding a repo-agnostic fallback. **Not** finding sessions something to do.

## The drive loop — what you are driving peers TOWARD

You own four of five steps; **step 4's clear is the PM's act**.

1. **Drive to execute.** A reviewed plan sitting on execution authorization is yours to release.
2. **Drive to workstream-complete.** Toward the close, not merely away from idleness.
3. **Troubleshoot alongside them until the primary exit criterion is met**, inside the
   no-authoring boundary.
4. **When the ceremony completes, the PM clears them.** Only a successfully completed ceremony
   establishes out-of-work — a peer's own "I'm done" does not. `/clear` is a human act. A session
   here is **done and awaiting clear**, never your failure — say so plainly.
5. **Assign something new from the daily priority set.** PM-owned and per-day; ask for it.

**No step here is discharged by an artifact, and your own report cannot show the gap.** Tripwire: `A-SELF-REPORTED-CLOSE-IS-NOT-A-COMPLETED-CEREMONY`.

## Persistence, Driver frame, stale reads

Nothing is written on invoke or cleaned up on exit; no peer roster or reachability fact is
persisted. Two carve-outs: the send log (`build_send_digest` appends to
`.coordinator-local/subagent-share/<this-session-id>/group-em-send-log.jsonl`, session-scoped, so
a new Group EM starts with an empty cooldown), and the engine's box holder record: relaying the
PM's word (`[PM via G-EM <name> <sid8> <ISO>]`, record first) and clearing a needs-PM flag
(`gem-triage-turn-intent`); contract page §§ 2–4. Tripwire: `A-PM-VIA-G-EM-RELAY-QUOTES-AND-POINTS`.

A `/group-em` session **is** that repo's Driver while it runs; build no registry.

Peer state is re-read immediately before acting on it, and **never** by calling the entry op a
second time inside one wake (§ Send pass step 1).

## Gating granularity — entry AND per send

**Entry stays PM-gated** by this file's prefix convention. **The send is gated separately, per
send:** the `ask-before-external-action` question lives there, justified by **cost to the
receiver**, never the sender's convenience.

### Standing check

**Confirm this session still holds the nomination**: `<plugin-root>/bin/group-em-nomination.py who
--repo <root> --json` (read-only). Never re-run `group-em-enter.py` to answer this — it re-claims
and re-arms the send digest's cooldowns.

## Read pass (gem-13)

The enumerate-and-classify ladder lives in `read_pass.py` beside this file (module docstring),
invoked through § Entry's op: `build_roster(repo_root)` for the classified population,
`build_candidate_roster(repo_root)` for the paused-only shortlist.

## Send pass (gem-14)

`send_pass.py` turns `build_roster`'s **full** population into **one digest per invocation**
(`build_send_digest`). It selects and throttles; **it does not send.**
**`roster` IS NOT THE POPULATION — it is the shortlist**, `build_candidate_roster`'s output.
`undischarged_obligations: None` means no ledger exists, never that the peer owes nothing.

**Compare `roster_considered` (entry's top-level enumerated count) against the room, never
`len(roster)`.** A `roster_considered` smaller than the sessions you know are running is
`unknown`, never quiet. Worked case:
`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md` § The roster is not the population.

Two settling reads: `claude agents --json`, and `python3 -m coordinator_core.group_em.idle_report
--repo-root <root> --group-em-session-id <your sid>` (omitting the id degrades offer-log
suppression silently).

**Ledger rows can arrive from the engine plane** via
`state/subagent-share/<sid>/obligations-inbound.jsonl`; this plane is the ledger's sole writer. Contract:
`coordinator/docs/wiki/cross-repo-communication/obligations-inbound-intake.md`. Tripwire:
`A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op already built both plus a `baseline` delta. **Act on that payload — never re-run
   the entry op to refresh it**; `build_send_digest` arms cooldowns as it emits.
2. Present it (`suppressed`: peer held; `truncated`: re-evaluated next wake; `unrecorded`:
   cooldown write failed).
3. **Per entry you intend to message, declare both gates in prose before sending:**
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or a
     settled ask? A settled ask is a memo.
   - **GATE 2 (receiver).** Cheaper to them now than later? It has no instrument; it rests on what
     you know about that peer.
   - **Either gate unclear → the memo channel.**
4. **Re-resolve the address from the SESSION ID immediately before sending, and treat a refusal as
   a refusal.** The engine's `coordinator_core.group_em.send_pass.resolve_addressee(repo_root,
   peer_session_id)` (import it with the engine root on the path) returns the name that session
   answers to right now, or `None` — do not send on `None`. **`repo_root` is the PEER's repo, not
   yours:** the roster it reads is scoped to that root, so a peer in another repo resolves `None`
   against yours.

   Resolve from the id, never validate the name. Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

**Never loop over `entries` sending.** `SendMessage` is in `allowed-tools`; the gate is this
paragraph.

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason`. Tripwire:
`A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## The escalation screen — a claimed PM item is presumed yours until it survives

**A session claiming something for the PM is wrong about 19 times in 20** (the PM's measured
prior). Test the claim; it is never routing already done.

- **"Next: review."** The next step in a procedure the session owns. Push it (or name the actual
  next step if review is not a step at that size). Do not grant a permission the session holds.
- **"Variable `x` or `xy`?"** Engineering, decided by whoever holds the file. Push it.
- **"Do I execute?"** The one with a real question, answerable by you — below.
- **"This is irreversible."** Only a publish to a server the fleet does not own is; push a local write back as the session's own (`A-LOCAL-WRITE-IS-RECOVERABLE-ONLY-PUBLISHING-IS-IRREVERSIBLE`).

Run the altitude test on the way out of a turn too: an idle peer is not a reason to message.

**Answer engineering calls yourself**, or dispatch `coordinator:staff-eng` for a viability read.
Route scope and direction to the APM. Pass the PM only what survives this screen, in plain words: what happens, to which server, why it cannot be undone.

### Push, do not nudge

**"Do you need anything?" is a failure, not a gentler success** ("want me to...?", "let me know
if..." likewise): it hands the decision back to the session that froze on it.

A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark,
offer or conditional; one clause of reason.

Never push a peer past a gate its own skill names — a gate is a considered refusal with a named
reason; hesitation is the absence of one.

### "Do I execute?" — yours to answer, with a viability read

The PM has delegated this call. **Do not read the plan into your own context.** Dispatch
`coordinator:staff-eng` for a viability read. Where a plan needs the formal
`execution_authorized_by` stamp, § Delegated approve-for-execution is the only path; this lighter
call is for work that does not need that stamp.

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
     `state/review-trail/approvability/` record, or this session's own dispatch of the falsifier;
     if none establishes it, treat it as a missing baseline and dispatch.
   - **Instrument soundness.** A FALSE baseline proves the criterion false, never the instrument
     sound. Ask: **what would have to be true for this to print TRUE, and is any of it reachable in
     the world the fixture builds?** Unreachable → escalate, reason named.
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
7. **Standing offer:** when a plan's terminal evidence is a live act rather than a test run, offer
   to perform it as the Group EM and let the author verify. Where the separation is not free, say so and let it go. Tripwire:
   `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.

## Fleet inbox grind

**On entry, with `coordinator.feature.cross_repo_memos` on, fire the saved workflow — not a
decision.** The autofire hook prints `FLEET INBOX GRIND, FIRE NOW`:

    Workflow({scriptPath: "<plugin-root>/workflows/fleet-inbox-blitz.mjs", args: {repos: [...], gem: {...}}})

Fire it first after arming the watch, unattended. `repos` is the fleet map (`machine-local get
repos.*`, repos with `state/cross-repo/inbox`). **Do not hand-author a variant.** Save each
returned manifest to `<home>/state/inbox-blitz-<date>/<repo>.json` and memo that path to the
repo's EM, who applies and commits it. Tripwires: `A-GROUP-EM-HAND-AUTHORING-THE-INBOX-WORKFLOW`,
`A-GROUP-EM-SENDS-MEMOS-AND-NEVER-RECEIVES-THEM`.

## Cross-repo commit authority

**With the standing and `coordinator.feature.gem_cross_repo_commit` on, commit in any
fleet repo without PM assent:** scoped commits, no destructive git ops, never leave a sibling red,
memo engine work. Off: ask that repo's EM in its own session (same `--plugin-dir`), else memo. Tripwires: `GEM-CROSS-REPO-COMMIT-IS-A-BOX-SETTING`,
`A-BARE-CLAUDE-BG-SPAWN-LOADS-THE-WRONG-PLUGIN-TREE`.

**Doctrine is yours to change either way; no fleet fan-out:**
`GEM-MAY-CHANGE-DOCTRINE`.

## Anti-scope

- **No auto-send.** `send_pass.py` holds no transport. Every send is an explicit per-send act with
  both gates declared. An unattended sender, a loop that messages each digest entry, or any
  `Stop`-registered trigger is out of scope.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** A nudge on an observed registry
  transition is preserved; a tick that messages everyone it can see is forbidden, and a timing
  predicate re-derives `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down. The ban is on
  AUTOMATION: a holder re-deriving and judging the roster each turn is preserved.
- **The three dispatch grants cover only their own named dispatch.** Messaging **peer sessions**
  stays an `ask-before-external-action` question no grant dissolves.
- `/autonomous` is a naming precedent only; its `/tmp` sentinel is not borrowed.
