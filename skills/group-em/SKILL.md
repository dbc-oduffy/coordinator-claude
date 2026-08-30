---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

Invoking `/group-em` switches this session into monitoring the other sessions running in the same
repo and moving them along. It is a **mode a session enters, not an operation on a target** — the
same shape as `/autonomous`'s toggle-a-disposition naming, borrowed for the name only (see
Anti-Scope below; the sentinel-file mechanism does not transfer).

**PM-GATED. Only invoke when the PM explicitly asks for it, never EM-initiated on its own
judgment.** This is a description-prefix convention, matching `staff-session`, `spinoff`, and
`roadmap-planning` — there is no hook or lib that enforces PM-gating anywhere in this repo
(`grep -rln "PM-GATED|pm_gated" coordinator/hooks/scripts coordinator/lib` returns nothing). The
gate is honoured by disposition, not by a guard, until something else supplies enforcement.

**Dispatch authorization — invoking this skill IS the request, for the approvability-judge
dispatch specifically.** The approvability-judge dispatch in § Delegated approve-for-execution
procedure below is a constitutive step of that procedure, not a separate thing to get cleared:
invoking a skill requests the actions that skill performs. This is a narrow grant, not a general
dispatch grant for this skill — it covers spawning the named Opus persona under this session's own
authority for that one procedure, nothing else. It does not touch the peer-session send/nudge
mechanism (`gem-14`, gated separately, and not yet built) — that remains outside this paragraph's
scope; see the Anti-scope carve-out below for how the two are distinguished. Tripwire:
`UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## What this skill does and does not do

**Does NOT plan — never plan or author on anyone's behalf.** Reading peer state and nudging a
stuck session is never authoring roadmap or plan content for the sessions it watches. A
`/group-em` session never writes plan bodies, stub content, or roadmap decisions on their behalf —
that stays each session's own.

**DOES coordinate execution waves and cross-session sequencing.** The affirmative half of the same
boundary: noticing a wave is stalled, a session is blocked on a dependency that has since cleared,
or two sessions are about to collide on the same file, and nudging accordingly.

## No registration ceremony, no persistence

Nothing is written to disk on invoke. Nothing is cleaned up on exit. No roster, address, or
reachability fact for any peer session is persisted anywhere — not in this repo's state
directories, not in a scratch file, not in a sentinel. Every fact this skill acts on is re-derived
live, every time, from the tools available at invocation (`Read`, `Bash`, `Glob`, `Grep` against
this repo's own working state).

**One carve-out, by name: the send log.** `send_pass.record_offer` appends to
`state/subagent-share/<this-session-id>/group-em-send-log.jsonl` — a record of **this session's own
offers**, which is what the per-peer cooldown throttles against. It is not a peer fact: no peer
state, address, or reachability is written, and nothing about a peer is read back out of it. It
follows the existing per-session bookkeeping convention beside
`advisory-fire-counts.jsonl`, and it is session-scoped, so a new Group EM starts with an empty
cooldown — the same lifetime the DACI ruling above gives the Driver role.

## DACI is a frame, not a registry

A `/group-em` session invoked by the PM in a repo **is** that repo's Driver for the sessions it
coordinates, for exactly as long as it keeps running. That role is instantiated by invocation —
never declared in advance, never persisted. When the session exits, the Driver role ends with it;
nothing records that it ever held it. Do not build a Driver registry, roster file, or any standing
record of who is coordinating whom.

## Stale-read discipline

Peer state must be re-read immediately before acting on it, never from a snapshot taken earlier in
the same turn. A peer session's status can change between one tool call and the next; treating an
earlier read as still current is exactly the failure mode this clause exists to prevent. Every
nudge or wave decision re-reads first.

## Collision check — discharged, cited not re-run

The platform-vocabulary collision check on the name `group-em` (plan skill scaffold checklist item
6, `coordinator/skills/plan/residue/plan-corpus.md:53`) is **already discharged clean** — no
`claude` CLI subcommand or flag, no bundled-skill shadow-set collision, no PascalCase hook token,
no existing coordinator skill/command/agent, and no hit anywhere under
`~/.claude/plugins|skills|commands|workflows` (`state/roadmap/gem-2026-08-14/research-corpus/group-em-skill-scaffold.md`
§ "The outstanding collision check"). This citation is the record of that discharge; nothing above
re-runs it.

## Gating granularity — entry AND per send, resolved by `gem-14`

Both, at different strengths, and the send gate is the load-bearing one.

**Entry stays PM-gated** by this file's prefix convention, unchanged — that gate is about who may
put a session into this mode at all.

**The send is gated separately, per send, and entry-gating never satisfies it.** A read-only pass
is harmless whatever the entry gate says; the send is where the
`ask-before-external-action`-shaped question actually lives, and it is where the PM's own bar
applies: *is this worth tapping the busy engineer on the shoulder and saying "stop what you're
doing and listen to me"* — an interrupt is justified by its **cost to the receiver**, never by the
sender's convenience or the topic's importance. Because that bar is receiver-relative it must be
re-asked for every message; one clearance at invocation cannot stand in for it, and receiver state
goes stale on the minute scale in any case.

## Read pass (gem-13)

The enumerate-and-classify ladder referenced in the Anti-scope entry below lives in
`read_pass.py`, beside this file — not inlined here. It composes `gem-11`'s
`coordinator/lib/receiver_state_reader.py` reader over `receiver-state.json` with a
`claude agents --json` fallback into a bounded, read-only candidate roster:
`build_candidate_roster(repo_root)`. It excludes the caller's
own session, never writes or sends anything, and never adjudicates whether a paused peer
"shouldn't" be paused — see that file's module docstring for the full ladder and the measured
reader/fallback split. The send/nudge mechanism that later plugs into this roster is `gem-14`,
gated separately.

## Send pass (gem-14)

`send_pass.py`, beside this file, takes `read_pass.build_candidate_roster`'s output and emits **one
digest per invocation** (`build_send_digest`). It selects and throttles; **it does not send.** There
is no per-peer entry point, so the per-peer-per-tick firehose is unreachable from the API, not
merely discouraged.

**The roster is not the population.** `receiver-state.json` is written at the peer's Stop seam, so
nearly every classifiable peer reads `PAUSED` (8 of 10 measured, against a read pass sized for ~6 of
30). The send pass narrows by intersecting the verdict with an **undischarged obligation** in the
peer's own next-move ledger — opened and closed only by concrete PostToolUse observations, never by
elapsed time. A peer with no ledger is ineligible: absence of evidence is never a trigger. An empty
digest is the expected steady state. Rationale and measurements:
`docs/decisions/DR-group-em-send-narrows-on-the-obligation-ledger.md`.

**Procedure, per invocation:**

1. Build the roster, then the digest. Re-read both immediately before acting — the stale-read
   discipline above governs here too.
2. Present it. `suppressed` says why each roster peer was held; `truncated` means the rate ceiling
   bit and the rest were held, not dropped.
3. **For each entry you intend to message, declare both gates in prose before sending.** Entries
   arrive with `gate1`/`gate2` unset and no code resolves them:
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or is
     this a settled ask? Converging on the shape of an ask is coupled; MAKING the ask is not. A
     settled ask is a memo.
   - **GATE 2 (receiver).** Is this cheaper to them now than later — blocked and waiting, about to
     ship something this would change, or an agreed synchronous window? **GATE 2 has no
     instrument.** `peer_roster.status` is negative-spec'd (1465 s stale measured, unbounded to
     6.9 h), and the obligation ledger answers a different question. GATE 2 rests on what you
     already know about that peer, never on anything you read this turn.
   - **Either gate unclear → the memo channel.** Not a degraded mode. The named anti-pattern is
     sending live *because the channel is open*.
4. Send, then `record_offer(...)`. Record it even when you decide against sending — the cooldown is
   on the offer, so a peer you considered and passed on does not resurface every tick.

**A `PAUSED:away` peer is never offered**, by name and by allow-list. (`away` was unobserved in the
2026-08-30 window, so that exclusion is structural and untested against live `away` traffic.)

**The digest never claims a peer is stuck**, or that it "shouldn't" be paused — that population is
unmeasurable by PM ruling. An undischarged obligation says the peer resolved a next move and has not
invoked it. Nothing more. And grade your own accuracy with suspicion: a supervisor's instrument is
measurably wrong in its own favour, and a Group EM has no outside party with standing to contradict
its read. Tripwire: `A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## Delegated approve-for-execution procedure

Ordered procedure for the Group EM's rubric-gated execution-authorization stamp: the Group EM may
take the PM's execute-plan turn on one named condition — the plan is reversibility-eligible and a
rubric-scored judgment against the plan's own prime exit criterion clears a locked threshold
(8 of 8, no dimension scoring 0). This is a *dispatch* path (step 4 below
spawns the judge under this session's own authority) — distinct from the `gem-14` peer-session
*send* mechanism named in § Read pass (gem-13) above, which is gated separately and not built yet.
Do not read the judge dispatch below as a send capability against a peer session.

1. Resolve the Group EM nomination for this repo (`coordinator/bin/group-em-nomination.py who
   --repo <root> --json`) and confirm it names this session.
2. Run `coordinator/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). Ineligible
   (`eligible: false`) → escalate per the threshold page's escalate shape, stop, do not dispatch.
   This CLI is the single source of truth for eligibility — do not restate the six D4 rules in
   prose as a substitute for running it.
3. Confirm the plan's recorded falsifier baseline shows the prime exit criterion false. Absent, or
   already true → escalate, stop.
4. Dispatch the named Opus persona (the PM's chosen reviewer, at the PM's chosen effort) with the
   plan path and the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing
   else. Authorship blinding is a hard constraint on the dispatch brief — the judge never receives
   the authoring session's context or identity.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`);
   validate it with C9's `--validate-record` mode (verbatim-substring check on every non-zero
   dimension's evidence) before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value — a
   plan the PM already authorized needs no delegated approval, and `--append-note` would otherwise
   leave the PM's own note appended under a Group-EM attribution. Otherwise stamp with
   `review-exec-auth-stamp stamp <plan-path> --by "GROUP-EM:<session-id>" --append-note
   "<record-path>"`. On `escalate`, emit the decision to the PM per the threshold page's escalate
   shape — do not stamp.

## Anti-scope

- This skill does not **auto-send** to a peer session. `send_pass.py` selects and throttles a
  nudge population; it holds no transport and messages nobody. Every send is an explicit per-send
  act under § Send pass (gem-14), with both gates declared. Building an unattended sender, a loop
  that messages each digest entry without a per-send gate declaration, or any `Stop`-registered
  trigger, is out of scope and re-derives the stood-down watcher.
- This skill does not implement the read-pass ladder or receiver-state consumption logic that
  supplies the peer-state facts this body's stale-read discipline governs — that is supplied by a
  separate stub and integrated here by reference, not merged into this file.
- **Carve-out, stated by name, not a reversal of the rule below:** the general anti-scope clause's
  stated reason is that `/group-em` messages **peer sessions** in their own windows, an
  `ask-before-external-action` question that clause does not dissolve. Spawning the
  approvability-judge persona under this session's own authority (§ Delegated approve-for-execution
  procedure, step 4) is the *contrasted* case the clause itself names in the bullet below, not the
  prohibited one — so it is carved out here by name rather than left as a silent exception. This
  clarifies the existing ruling; it does not overturn it.
- This skill does not otherwise carry a dispatch-authorization paragraph ("invoking this skill IS
  the request") of the general kind used by skills that dispatch subagents (`plan`, `execute-plan`,
  `review`, `shape`, `sizing`, `workstream-complete`) — the one dispatch-authorization paragraph it
  does carry, above, is scoped to the approvability-judge dispatch only, not a general grant. Those
  skills spawn subagents under the invoking session's own authority; `/group-em` otherwise messages
  **peer sessions** in their own windows, which is an `ask-before-external-action` question that
  paragraph does not dissolve.
- `/autonomous` supplies the mode-shaped naming precedent only. Its `/tmp` sentinel mechanism is
  durable state and is not borrowed — the no-ceremony ruling above forbids durable state.
