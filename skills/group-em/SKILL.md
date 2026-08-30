---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent"]
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

## Open design question — not resolved here

Whether PM-gating belongs at skill **entry** (this file's prefix convention) or at the **send**
itself (a later nudge/message to a peer session) is left open. A read-only pass that only observes
peer state is harmless regardless of gating granularity; the send is where an
`ask-before-external-action`-shaped question actually lives. That granularity call belongs to
whoever specifies the send path, not to this container.

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

- This skill does not implement the send/nudge mechanism to a peer session — that is a later
  addition to this body, built once its own PM gate clears.
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
