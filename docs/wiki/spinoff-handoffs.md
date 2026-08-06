---
kind: wiki
title: Spinoff Handoffs — Mid-session Forks vs Continuations
status: active
created: 2026-05-06
tags: [spinoff-handoffs]
---

# Spinoff Handoffs

A **spinoff** is mid-session fork: *"I'm working on X, but topic Y came up that deserves its own session — here's a self-contained spec for Y, written so you can pick it up cold without my context."* It is distinct from a continuation handoff, a plan, and a queue entry.

The metaphor is the TV-series sense: same universe, separate series. The word reads naturally as both noun and verb.

## Handoff No-Successor Gate — Step 0

Before writing ANY handoff (spinoff or continuation), run Step 0: the successor-work check. The gate is binary.

**NO-tests — any one of these → STOP, do not write a handoff:**

1. The workstream's next action is `/merge-to-main`, or the terminal PR is already merged with no follow-up commits expected.
2. Work is described in your head as "shipped," "complete on branch ready for merge," or "ready for the merge gate." That phrasing IS the disqualifier — write a commit message, not a handoff.
3. All in-flight chunks of the active plan have landed and the plan doc is marked complete.

**YES-tests** (only consulted if ALL NO-tests fail):
- In-progress edits not yet at a stopping point, AND a successor session must resume them
- A plan in flight with remaining unexecuted chunks (not chunks that just landed in this session)

**When to write a commit-and-stop instead of a handoff:**
"Shipped" work that needs no successor → `/workday-complete` week-changelog or commit-and-stop. A completed workstream does not need a `state/handoffs/` entry.

### Born terminal vs becomes terminal in place

Handoffs are for work continuance — a baton someone must pick up. A settled finding was never a baton, no matter how valuable the finding is. Before authoring anything into the live handoffs location, ask whether the artifact is **born terminal**: already resolved, with nothing left to continue, at the moment it is written. If it is, it does not belong in the live handoffs queue at all — it belongs wherever resolved/archived records live, alongside every other already-closed handoff.

This is a **different failure mode** from a handoff that becomes terminal in place: a normal baton that starts genuinely open, sits in the live queue, and later gets consumed or ships — that is the ordinary lifecycle, and it is correct for it to be terminal *inside* the live location pending the routine archival sweep. Conflating the two reads as a contradiction where none exists: "don't author a terminal artifact into the live queue" and "a live-queue entry may legitimately end its life there before being swept" are orthogonal rules about two different moments — authoring time versus end-of-life.

The reasoning: fusing a permanent record (the evidence itself) with an ephemeral routing intent (a baton for someone to pick up) into one live-queue entry means the ephemeral half's eventual expiry stands the permanent half in the pickup queue as a zombie — something no one ever intends to act on, but that keeps costing a look at every pickup pass until someone notices it was never really a baton. The fix is upstream of the sweep: never author the terminal artifact into the live location in the first place. A record of something already finished is a record, not a handoff, and it should be filed as one from the start — the resolved/archived home for handoffs is exactly the right place for it, not a narrowing of that home's schema to reject it, and not a special case invented for this one artifact.

**How to apply:** before writing anything into the live handoffs location, ask "is there a successor action here, or am I just recording that something already happened?" If the latter, write it directly as a resolved/archived-shaped record instead — do not write it live and plan to archive it later, and do not treat the archived location as somehow less legitimate a destination than the live one for content that was never going to be picked up.

## When to spinoff

Three signals indicate a spinoff is the right shape:

1. The current session's bandwidth is already spent on its primary mandate.
2. The new topic deserves a full session of attention rather than being squeezed into a tail.
3. The PM observes the same need and asks (or you anticipate they would).

Continuing a session past the point where focus has split empirically produces neither workstream cleanly. Spinning off both gets a fresh context.

## Spinoff vs handoff vs plan vs queue entry

| Artifact | Timing | Predecessor | Purpose |
|---|---|---|---|
| `/handoff` | end-of-current-session | the just-finished session | continuation |
| `/spinoff` | mid-session | none (fork) | self-contained spec for a different workstream |
| plan (`docs/plans/`) | pre-execution | n/a | EM's design for work the EM intends to dispatch |
| queue entry | non-urgent | n/a | one-line pointer awaiting triage |

A spinoff matches a real handoff in detail: load-bearing context, references, acceptance criteria, anti-scope. It is **not** a one-line queue entry — it must be pickup-able cold.

## Install-leg spinoffs — the one sanctioned non-`/spinoff` creation path

> Spinoffs are normally PM-authorized and keyword-gated: the EM surfaces `Candidate spinoff: <slug> — <topic>. Authorize?` and blocks; paraphrase is not authorization; only `/spinoff` (or `coordinator:roadmap-planning`) creates one. This carve-out names the **single** exception and explains why it does not erode the gate.

When an operator installs coordinator as the root of a multi-repo setup, each *additional* dependency repo they want is materialized as a **spinoff** by that repo's installer — not by an EM typing `/spinoff`. The baton is a normal `kind: spinoff` file in the install-baton rendezvous — a per-machine settings-home folder (`$(coordinator-settings-home)/state/handoffs/`, with bash inline fallback `${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/state/handoffs`) — distinguished from the coordinator onboarding handoff by an `install_chain_order:` tag, and carrying `authoring_session:` naming the install + the operator's opt-in (the audit-trail field this schema requires of every spinoff). It is seeded via `cp`/`sed`, not the Write tool, so it does not trip the unauthorized-handoff nudge. This is legitimate because **the authorization is captured at the install's pre-restart question** ("what else do you want to install?"). The operator selecting a leg there *is* the human authorizing that fork — the same authorization `/spinoff` captures, captured at a different but equally explicit moment.

The gate is not eroded:

- **A human still authorizes every leg.** A spinoff never appears unless the operator chose it at the pre-restart question. The installer materializes a choice the human already made; it does not invent a fork. The EM driving the install is not self-initiating spinoffs — it is stitching operator-authorized ones.
- **Scope is narrow.** This applies only to install-time leg-seeding, where the human's selection is the gate. It does not license script- or EM-created spinoffs in any steady-state workstream — there, the `Candidate spinoff: … Authorize?` block still holds.
- **`predecessor: none` is native.** These legs are genuine forks of different install topics, not continuations of coordinator onboarding (which is the handoff). The spinoff frame fits without a lineage exception.

### Restart / onboarding prose must point cwd at the baton's repo

`/workday-start` and a bare-relative `/pickup` resolve handoffs against the **cwd's git root**. Any leg / restart / onboarding prose that precedes one of these commands must therefore either say `cd <repo>` first or hand an absolute baton path — otherwise the command resolves against whatever repo the operator happens to be sitting in and either finds nothing or picks up the wrong repo's batons. Handing an absolute `/pickup <path>` removes the coupling entirely: the lifecycle bookkeeping (claim, frontmatter mutation, archival) then routes through the baton's own repo regardless of cwd. This matters most in install-chain and multi-repo restart flows, where the operator's cwd after a Claude Code restart is not guaranteed to be the repo whose baton is next.

## Frontmatter schema

```yaml
kind: spinoff
status: active
predecessor: none           # always — spinoffs have no continuity ancestor
authoring_session: <one-line description>   # replaces predecessor link as audit trail back to origin
workstream: <slug>          # required, so /pickup can group them
```

`predecessor: none` is load-bearing on the **primary spine**: the "Single Predecessor, No Adjacency-Inference" rule (in `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Handoff Lineage") requires every handoff to have a single named predecessor or `none`. Spinoffs are always `none`; the audit trail back to origin lives in `authoring_session`.

Three optional fields extend or annotate the primary spine — **do not conflate them**:

- **`forked_from: <handoff-path>`** — DAG branch-point ancestry, **lineage/render-only**. The level-of-effort aggregator does NOT follow this edge (preserves effort-isolation for pure-fork spinoffs). The archival guard DOES follow it — archiving a live fork-point breaks the DAG render walk. Must be PM-directed; adjacency-inference ban applies (`coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Handoff Lineage").
- **`supersedes:`** — spine-build-time ordering preference ("when building the orientation spine, prefer this baton over the one it names"). No DAG graph semantics; does not affect level-of-effort or archival traversal. See § `` `supersedes:` on a live baton`` below.
- **`authoring_session:`** — origin prose only; no graph traversal. The required audit trail for every spinoff.

### `supersedes:` on a live baton — optional field, distinct from a retired `status: superseded` value

`supersedes:` is an **optional** field on a `kind: spinoff` baton used by an orientation-supersession convention. It asserts a spine-build-time preference — "when building the orientation spine, prefer this baton over the one it names." It is **not** a lifecycle terminator and does not mark any baton as dead.

This is **distinct** from a (now-retired) `status: superseded` handoff lifecycle value — a superseded handoff is instead expressed as `status: consumed` + `deployment_state: abandoned` (which keeps it out of every active list). The `supersedes:` FIELD itself is unaffected and remains live; it does not terminate the baton it's on.

Canonical contrast: `supersedes:` on a memo is terminal (paired with `superseded_by:` + `status: superseded`); `supersedes:` on a live baton is conditional+live — a spine-build-time preference that never flips status and carries no back-pointer. The same field name means two different things depending on artifact type; don't conflate the memo-side terminal meaning with this baton-side conditional one.

## Pickup-side and workday-start handling

- **`/pickup` with `kind: spinoff`** prepends a one-line banner: *"This is a spinoff workstream — predecessor is none; treat the handoff body as ground-truth spec and proceed."*
- **`/workday-start`** lists spinoffs separately from active handoffs in the orientation cache.
- **Stale spinoff nudge:** a spinoff that hasn't been picked up after N days (default 14) gets a heads-up nudge in `/workday-start`.

## Why this exists as a formal pattern

Three pre-formalization signals motivated it:

1. **Recurring pattern** — real instances were executed within 3 minutes of each other by concurrent EMs.
2. **Ad-hoc shape leaks** — the validator rejected an invalid ad-hoc status enum because the ersatz form leaked into a real frontmatter.
3. **PM friction** — verbal description was needed each time.

## Pickup-side premise check

> Consumed by: `skills/pickup/SKILL.md` Step 1 (Classify, Load, and Reconcile Against Reality).

Brief: handoff body is hypothesis; verify load-bearing premises before executing.

### What to verify

Check each of the following before treating any premise as ground truth:

- **Paths cited as "modified" or "needs editing":** `ls` / `Read` each one. Files move, get renamed, or get deleted between handoff-write and pickup.
- **Commit SHAs cited as "shipped" or "landed":** `git cat-file -e <sha>` to confirm reachable; `git branch --contains <sha>` to confirm landing claim. Cherry-picks and rebases invalidate SHA assertions across sessions.
- **Scope frontmatter pathspecs:** glob each pathspec. An empty glob means the workstream substrate has moved — surface to PM before mutation, do not proceed silently.
- **Declarative premises ("X is true" / "Y done"):** for each load-bearing claim, identify the witness (a file, a commit, a doc section) and confirm it. Premise drift is the dominant failure mode for >24h-old handoffs.

### Spinoff exemption

`kind: spinoff`, `kind: spinoff-roadmap`, `kind: spinoff-goal`, and `kind: spinoff-roadmap-creator` have `predecessor: none` by design. A missing continuity ancestor is NOT a premise failure for these kinds — it is the correct structural shape. Verify the `authoring_session:` audit trail instead (confirms the spinoff origin context is still readable, not that a predecessor existed).

### When to surface to PM

- Premise drift on a load-bearing claim → surface before mutation; do not proceed silently.
- Routine path-rename with clear mapping → fix forward and note in pickup report.
- Scope pathspec returns empty glob → STOP, surface to PM; do not mutate.

### Verify semantic fit of handoff-named target files before writing

When a handoff names a target file (e.g., "extend `docs/wiki/X.md`"), `Read` that file and confirm the topic and section actually fit before writing. Stale handoff-named targets accumulate when the wiki has been refactored between handoff-author time and pickup time — the file may still exist but now cover a different scope, or the relevant section may have moved to a sibling file.

### Parked-tracker rows: framing is hypothesis, substrate is ground truth

When resuming work that names "parked" tracker rows, project-board items, or backlog entries with framing like "Y is blocked on X" or "this is parked pending Z", verify the substrate before accepting the parking framing. Stale advisory/call-note markdowns and project-tracker rows accumulate over weeks; the parking premise may have been overtaken (the blocker shipped, the scope was rolled in elsewhere, the row references files that have moved). Run a git-log spot-check on the cited paths before treating the parked state as live work.

### Empirical baseline

Expect 30–60% of inherited items to be already closed (pickup SKILL Step 1, Classify, Load, and Reconcile Against Reality, empirical note). Premise decay compounds on top of this: a 24h-old handoff may have 1–2 stale file assertions; a 7d-old handoff routinely has more. Treat unverified premises as blocking gaps, not deferrals.

## Deployment_state lifecycle for spinoffs

> Cross-reference: `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off,
> "Handoff Lineage" (deployment_state enum).

### Initial state at authoring

- `/spinoff` sets `deployment_state: ready_to_fire` for stubs intended for immediate pickup.
- `roadmap-planning` sets `deployment_state: awaiting_gate` for stubs with `gate_dependency:` (sequenced stubs that must not be picked up until a predecessor ships).

### Lifecycle table

> Column states refer to `deployment_state:` frontmatter, NOT `status:`. The `status:` enum is `active | consumed` — write path; the schema has since widened to also accept `open | claimed`, corpus mixed on disk, read both; `shipped` is not a valid `status:` value — use `consumed`/`claimed` + `shipped_in:` instead. (A retired `superseded` value is now expressed via `deployment_state: abandoned` + lineage fields instead.)

| Event | From → To | Skill responsible |
|---|---|---|
| author spinoff | (n/a) → ready_to_fire \| awaiting_gate | /spinoff or roadmap-planning |
| /pickup grabs | ready_to_fire → in_flight | /pickup Step 2 (Mutate and Commit) |
| gate clears | awaiting_gate → ready_to_fire | /handoff or /workstream-complete (gate-meaningfulness audit) |
| session ships | in_flight → shipped (+ shipped_in) | /handoff or /workstream-complete |
| session pauses | in_flight → ready_to_fire | /handoff |
| abandoned | any → abandoned | PM-authorized only |

### Stand-down notice — spinoffs whose deliverable is a cross-repo memo

If the spinoff's deliverable **was** a cross-repo memo to a named receiver, hand-authoring
`deployment_state: closed` isn't the finish line on its own — send the stand-down notice to
that receiver in the same close, via the cross-repo-memo forwarder. Skipping this leaves the
receiving repo's own baton waiting on a memo that is never coming, with no signal that the
sender stood down — the receiver eventually notices the silence and burns real time working
around a gap that a one-line stand-down notice would have closed immediately. One check
against the spinoff's own frontmatter (a named receiver in the body or a `superseded_by`/
lineage field) tells you whether this applies before you close.

### Concurrent-pickup interaction

`/pickup` mutates frontmatter in place with a claim gate; a second EM observing `consumed_by:` (or its renamed successor `claimed_by:` — corpus mixed, check both) populated after `git fetch` fails loud (pickup SKILL Step 2, Mutate and Commit, pre-mutation gate). No silent double-claim — the detecting session exits non-zero and surfaces to PM.

The same fail-loud-on-live-peer guarantee extends to **plan execution**: a sibling claim primitive gates `execute-plan` Phase 1.5 and `workstream-complete`. A second live session attempting to drive the same plan fails loud at the claim boundary — before any tokens are spent on duplicate reconcile or ceremony work.

## Claim liveness — PPID-authoritative model

Session liveness (used by claim-takeover, reaper, and memo-sweep) uses a two-layer model, behind
a single liveness check so every consumer sees the same answer — no divergence across callers.

**Layer 1 — PPID-authoritative (when a stable-pid identifier is present).** At session init,
capture the hook's parent PID — the long-lived harness session process, not the short-lived hook
subshell that invoked the check — as the stable identifier, after verifying its process name
actually matches the expected harness process (comm-check). Also capture that process's start
time for PID-recycling defense: an OS can reuse a PID after the original process exits, so a
liveness check on PID alone can false-positive against an unrelated process that now holds the
same number. At liveness-query time, re-read the current start time for that PID: process alive
with a matching start time → **LIVE**, regardless of recency of last activity; process gone or
start time changed → **DEAD** within seconds of session exit or kill. Recency is NOT consulted
when the stable identifier is present and valid — this is what "liveness-first" means.

**Layer 2 — recency fallback (when no stable identifier is present).** When Layer 1 can't be
established (non-harness run, comm-check mismatch, legacy state), fall back to a time-window
recency rule (e.g., no activity in N minutes) — unchanged, zero-regression behavior on those
paths.

**Why this is NOT the forbidden "current-process-PID-as-liveness" gate.** The naive version of
this pattern — using the current process's own PID (or the hook subshell's PID) as the liveness
key — is a well-known trap: that process is dead within seconds of every tool call by
construction, making every session appear dead moments after it acts. The fix is to key liveness
on the stable **parent** process, not the transient child that happens to be running the check,
and to combine it with the start-time guard so a recycled PID can't be mistaken for the original
holder.

**Accepted residual / worst-case bound.** An abandoned-but-alive session (machine left on,
unattended) holds its claim until the parent process actually exits. This is bounded by: (a) the
liveness check detects exit within seconds, including on crash; and (b) an absolute-inactivity
reaper backstop that fires on any session regardless of stable-identifier state. This is NOT an
unbounded leak — it realizes the design intent that a session genuinely still running should be
presumed to retain its holds until it ends.

## Soft-seams discipline

> Consumed by: `skills/roadmap-planning/SKILL.md` Step 2.1 (gate_dependency soft/hard rule) + Step 2.2 (body sections) + Phase 2 exit gate.

### Hard vs soft seams

- **HARD seams** (machine-read, drive tooling behavior):
  - Frontmatter `scope:` — pathspec consumed by `/pickup` safety-commit staging
  - Frontmatter `blocks:` / `blocked_by:` — tc-id graph edges consumed by wave-derivation topo-sort
  - Frontmatter `gate_dependency:` — consumed by `/handoff` gate-meaningfulness audit and `/pickup` gating logic
- **SOFT seams** (human-read, advisory):
  - Body `## Soft seams` section — consumed by the sequencing EM when ordering parallel waves; no tooling dependency

### Why a separate section

Frontmatter pollution with advisory text causes false "still gated" reports (roadmap SKILL § Field semantics — `gate_dependency:` for HARD gates only). Inline-in-Notes loses greppability. A dedicated `## Soft seams` heading is greppable (`Grep "## Soft seams"`) and structurally separable from specification content.

### Format

One bullet per seam, each naming:
- The peer (workstream slug / PR ref / tc-id)
- The overlap nature (file-region, schema-shape, timing, semantic)

Example: `- roadmap-run-abc/tc-4 — shares the `bin/lint-frontmatter.py` cross-field rules surface; coordinate on rule-ordering if both stubs edit the same array.`

### Empty is allowed, but the section must be present

Explicit `- None identified at authoring time.` is preferred over an absent section. Absence triggers Phase 2 exit-gate failure. An empty section is structurally correct and signals deliberate authoring-time triage, not accidental omission.

## Gate-dependency authoring discipline — calendarable observable or it's backlog

`awaiting_gate` on an **event-gate that isn't on the calendar** ("next time we do X," "when we eventually touch Y," "once someone revisits Z") is backlog disguised as a spinoff. The `deployment_state: awaiting_gate` state is reserved for work that is genuinely sequenced behind a *forthcoming, observable* event — not work parked behind a vague future intention.

**At handoff/spinoff-write time, `gate_dependency:` MUST name a calendarable observable** — something a recheck can mechanically test for:

- a **PR URL** (gate clears when it merges),
- a **flag name** (gate clears when the flag flips / ships),
- a **stub path** (gate clears when that stub is consumed/shipped),
- a dated milestone or a named artifact whose existence is checkable.

If the gate is an **indefinite event-gate** with no calendarable observable, it does NOT belong as `awaiting_gate` — **demote it to backlog** (improvement-queue entry or operational-doc fold-in) rather than parking it in the handoff/spinoff queue where the aging-reconcile machinery (§ Awaiting_gate aging) will repeatedly re-check a gate that can never mechanically clear. The aging machinery can catch gate-text drift on a *real* gate; it cannot rescue a gate that was never observable in the first place. The distinction is: a real gate has a witness you can name now; backlog has only an intention.

This pairs with the § Awaiting_gate aging recheck: authoring discipline (name a calendarable observable) prevents the un-clearable-gate from entering the queue; aging discipline catches the gate whose text drifted after entry. Both fire on `gate_dependency:`; the authoring check is the upstream floor.

## Awaiting_gate aging

This predicate is consumed per-handoff at pickup time as supplementary calendar evidence for the
gate judgment point — a judgment point already asked for *every* `awaiting_gate` handoff on every
pickup, regardless of what this predicate says. It is deliberately NOT run as a separate
standalone morning batch nag: a resolver that already surfaces every `awaiting_gate` handoff
needing a human look (on any non-empty blocking note or prose gate description, unconditionally
of calendar age) makes a calendar-only batch nag pure duplication for most of the corpus. The one
case the resolver deliberately does NOT surface — a real, still-open structured dependency edge
with nothing wrong — is intentionally quiet, not a gap for this aging predicate to re-litigate
with a competing calendar override.

### Why aging matters (pickup-side evidence, not a standalone nag)

Gates clear silently; gate text drifts in meaning over time. A gate-meaningfulness audit fires on
the `awaiting_gate → ready_to_fire` transition — but it cannot catch the aging-without-unblock
case, where the gate text now misnames the blocker without anyone having triggered a transition.
The per-handoff pickup-time judgment point is where a human now looks at this — not a separate
morning batch pass.

### Thresholds

Force a re-check when ALL THREE conditions hold:
1. `now − created:` ≥ 14 days
2. `deployment_state: awaiting_gate`
3. No `last_gate_recheck:` field present, OR `last_gate_recheck:` is ≥7 days ago

**Threshold derivation:** 14d matches the existing spinoff stale-nudge threshold (§ "Pickup-side and workday-start handling" above). The 7d recheck cadence matches a roughly-weekly recheck cadence used elsewhere in the doctrine corpus for similarly-shaped triage queues.

### Recheck mechanics

1. Read the gate witness named in `gate_dependency:`.
2. **Gate cleared:** flip `deployment_state: ready_to_fire`; write `last_gate_recheck: <ISO date>` in mutation pass.
3. **Gate still closed, text still accurate:** write `last_gate_recheck: <ISO date>` in mutation pass; surface gate status to PM.
4. **Gate still closed, text now misnames the blocker** (e.g., named sibling stub archived without shipping, named PR abandoned): surface to PM with the discrepancy — do NOT silently retain the stale gate text.

### Frontmatter field — `last_gate_recheck:`

ISO date (e.g., `2026-05-14`). Written by `/pickup` Step 2 (Mutate and Commit) mutation pass when the aging-reconcile clause fires. Absent on freshly-authored spinoffs; `/pickup` adds it at first aging-triggered recheck.

### `awaiting_gate` standdown requires substrate read, not literal-string gate match

**Rule.** Picking up a `kind: spinoff` handoff with `deployment_state: awaiting_gate` is NOT satisfied by reading the frontmatter `gate_dependency:` string + scanning `git log` for SHA matches. The gate predicate is a *pointer to substrate* — the handoff body cites empirical artifacts (spike reports, reproducers, disposition memos) whose contents define whether the gate has fired. A frontmatter-and-log glance produces standdown recommendations on incomplete evidence; the PM rightly pushes back, you re-read the substrate, and the cycle costs more than the read time it "saved."

*Case, compressed.* A standdown recommendation was authored after reading only the handoff body + `git log`. The PM challenged it ("you can't make that determination after a casual glance"). Reading the substrate the handoff actually named — a reshape proposal, a reviewer's findings, an empirical spike falsification, and a disposition memo — showed the gate's underlying failure predicate had already fired in *latent* form, suppressed only by a stopgap the disposition memo had explicitly warned was aging into load-bearing. The cheaper-alternative framing offered as a substitute was directionally true but not equivalent — it addressed one symptom without providing the fault containment the gate actually existed for.

**Discipline.** Before recommending standdown OR proceed on an `awaiting_gate` handoff: (1) Read every substrate file the handoff cites end-to-end, not just the handoff body. (2) Empirical artifacts (spike reports, reproducers, disposition memos) take precedence over frontmatter strings — when an empirical artifact shows the gate predicate fired in latent form, the gate has cleared regardless of frontmatter phrasing. (3) Name the load-bearing scope-boundary uncertainty whose wrong guess would invalidate the recommendation BEFORE making it, not after. Composes with § Pickup-side premise check (premise drift on load-bearing claims surfaces to PM before mutation, not after a casual-glance disposition).

## Gated destructive-removal handoffs — reconcile the destructive precondition against disk before firing

*[universal]*

A restart-gated or otherwise-gated **"destructive rm"** spinoff can be overtaken by upstream events between authoring and pickup. The scary framing — `BLOCK-DESTRUCTIVE-RM`, a rollback tarball, a restart-gate — describes the state *at authoring time*, not necessarily the state on disk at pickup.

**Rule.** On pickup of any gated destructive handoff, verify the destructive precondition **STILL NEEDS DOING against current disk** before treating the framing as live. The `deployment_state: ready_to_fire` flag says the *gate* cleared; it does NOT say the *work* remains — an upstream cutover, plugin-refresh, or sibling recovery may have already performed the dangerous op, leaving the rm moot.

*Case (C7 v3-cutover cleanup):* a restart-gated destructive-rm spinoff was picked up as `ready_to_fire`, but disk reconcile showed the dangerous op had **already happened** via the upstream cutover/plugin-refresh — the vestigial tree was gone, the cache gone, the marketplace deregistered, cold-resolution already `rc=0`. What actually remained was reversible bookkeeping (dead registry keys + a dead test skip), not a destructive removal at all. Firing the rm as framed would have been a no-op at best and a re-derivation of the crash boundary at worst.

This is the destructive-op corollary of § `awaiting_gate` standdown requires substrate read: there, substrate reconcile decides whether the gate *fired*; here, it decides whether the destructive action was *already performed by an upstream event*. Both refuse to act on the frontmatter framing alone.

## Wave vs sprint

> Consumed by: `skills/roadmap-planning/SKILL.md` Step 2.1 wave-vs-sprint clarification.

### Wave

Single-dispatch parallel fan-out within a sprint. All wave-N stubs are file-disjoint by construction and dispatched concurrently in one EM session. Cost: one EM-session of dispatch + sync overhead. Risk: bounded — failure of one wave-N stub does not invalidate sibling stubs.

### Sprint

Multi-session time-box. Wave-N+1 stubs gate on all-of-wave-N completing; `/handoff` bridges between sessions. Cost: multi-day, multi-session. Risk: compound — a sprint-N architectural finding can invalidate sprint-N+M stubs authored against a now-wrong assumption.

### Smell-tests

- **1 stub per wave across many waves:** probably should be sequential stubs within one wave, not separate waves — `wave:` is for parallelism, not serial ordering.
- **>5 stubs in one wave:** file-disjointness is suspect; audit `scope:` overlaps before dispatch. If two stubs share any pathspec, they are NOT safe to run in parallel.
- **20 stubs as 4 sprints × 5 waves of 1 stub each:** using `wave:` for time-boxing. Correct shape: 4 sprints × 1 wave × 5 sequential stubs, OR (if genuinely parallel) 4 sprints × 1 wave × 5 parallel stubs with verified disjoint `scope:` blocks.

For the dependency-order invariant that governs how stub numbers and `(sprint, wave)` execution slots must align with `blocks`/`blocked_by` edges — including the enforcement surfaces (`audit-roadmap.py` Audit 5, `coordinator_core.roadmap.graph`) and the scope-honesty note on undeclared edges — see `roadmap-numbering.md`.

## Crash-recovery handoffs are one-per-workstream

`kind: recovery` handoffs are scoped by **incident**, not by size of the recovered work. When a session crashes or is killed mid-flight, write one recovery handoff per surviving workstream — regardless of whether the recovered slice is "trivial" or "big." Judging "this is too small for a handoff" silently overrides the directive that recovery handoffs exist to make crash-loss boundaries discoverable; the cost of an extra small handoff is a few minutes, the cost of a missed one is the successor session re-discovering the crash boundary by stepping on it.

Commit-granularity is incident-scoped, not workstream-scoped: if two concurrent workstreams both crashed, that's two recovery handoffs (separate `predecessor:` pointers to each crashed handoff's SHA), not one merged "we crashed" handoff. Each successor picking up either workstream needs its own framing of what was in flight, what got committed pre-crash, and what didn't.

## Recovery-pickup hygiene — untracked-files and diagnostic decay

Recovery pickups produce a noisier working tree than ordinary pickups: pre-crash partial writes survive as untracked files, and the crashed session's diagnostic notes age fast.

- **Untracked files at recovery pickup are evidence, not noise.** Before staging or committing on a recovery handoff, list every untracked path and diff it against the crashed session's intended scope (`git status --porcelain=v2 -uall` over `scope:` pathspecs). An untracked `.tmp.<pid>.<nanos>` file is an Edit-tool atomic-write crash — diff against its target before deletion. An untracked source file not in the recovery scope is out-of-scope work from a sibling session — surface to PM rather than absorb silently.
- **Handoff diagnostics decay.** A crash handoff's "what was in flight" framing is hypothesis at pickup time: cited file:line offsets may have moved, cited SHAs may have been rebased, cited test failures may have been fixed by a sibling recovery. Re-run the cited failing test on HEAD before treating it as live; `git log --oneline -- <cited-paths>` since the crash report timestamp before treating the crash boundary as the current boundary.
- **One recovery handoff per surviving workstream still holds** — the hygiene rules here are per-handoff, not per-incident. Two concurrent crashed workstreams produce two recovery handoffs, each with its own untracked-files audit.

## predecessor: in practice — almost always `none`

Doctrine describes lineage chains via `predecessor:`; empirical observation across active repos in 2026-06 shows only ONE live handoff in any tracked repo carrying a real predecessor path. The dominant `predecessor:` value is `none` (spinoff frame) or absent.

This is **not** a bug. Continuation chains tend to be in-session (one EM threads through several handoffs in a single thread) where the `/pickup` → `/handoff` cycle implicitly carries lineage via session memory rather than the file field. Long-form cross-session ancestry is rare because (a) most workstreams complete in 1–2 sessions, (b) spinoffs (`predecessor: none` by schema) account for the majority of new handoffs, and (c) `kind: recovery` is the only kind that routinely back-points to a non-handoff SHA.

**Operational implication:** Treat `predecessor:` as a low-signal lineage field at query time. The high-signal lineage fields in practice are `authoring_session:` (spinoff origin), `shipped_in:` (terminal commit/PR), `consumed_by:`/`claimed_by:` (pickup-session UUID, see below). Don't infer adjacency from `predecessor:` being populated on one of several timestamp-adjacent handoffs — the rule in `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Handoff Lineage" is exactly this caveat.

## consumed_by:/claimed_by: is a session UUID, filename SHA is different

`consumed_by:` is populated by `/pickup` Step 2 (Mutate and Commit) with the **picking session's UUID** (a Claude-Code session identifier). The handoff filename's discriminator suffix, by contrast, is an 8-hex **session-SHA** of the authoring session — a different identifier space derived at write time. (A later schema revision renames this field `claimed_by:` — the successor vocabulary; the write path has not cut over as of this writing, but the schema already accepts both and the on-disk corpus is mixed, so read-side logic must check both fields.)

Practical consequences:

- Do not assume the 8-hex in a filename equals the UUID prefix in `consumed_by:`/`claimed_by:`. They are different identifier classes and will not collide.
- A handoff with `consumed_by:` or `claimed_by:` populated is **claimed** — it must not be re-picked. `/pickup` enforces this via an EEXIST-style single-machine claim lock and, cross-machine, a `git fetch` + non-empty-field check. See `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Handoff Lineage" — Concurrent `/pickup` is fail-loud.
- Closing a handoff (`status: consumed`/`claimed`) is a separate write from claiming it (`consumed_by:`/`claimed_by:` populated). The two fields move together at `/workstream-complete`'s terminal-archival step, but auditing should treat them as a pair, not synonyms.

## Frontmatter format drift — `created:` and `pickup_ready:`

Two normalization gaps observed across recent handoffs in the same repo, same week:

- **`created:` date format mixed.** Bare `YYYY-MM-DD` and full ISO-8601 (`2026-06-14T08:31:17Z`) both appear. Trackers that do string-comparison aging (`now − created`) mis-handle the mixed shapes — a strict ISO parser rejects bare-date entries, and a strict bare-date parser truncates ISO-8601. **Normalize to bare `YYYY-MM-DD`** at write time — the canonical form the contract declares; the scaffolder tool already emits bare date, so templates should match it rather than diverge to ISO-8601. (`created` is a creation-DAY; the date-time instant lives in the `## Session Ledger` body, kept separate.) Pickup-side aging logic should still parse both shapes defensively for legacy records.
- **`pickup_ready:` boolean type drift.** YAML `true` (unquoted boolean) vs `"true"` (quoted string) coexist. Strict YAML-bool consumers mis-handle the string variant as truthy-non-bool. **Normalize to unquoted YAML boolean** at write time; the frontmatter linter should reject quoted-boolean forms.

These are mechanical cleanups, not doctrinal conflicts — every writer should canonicalize to one shape. The query tooling parses both shapes today to absorb legacy entries; new writes should not perpetuate the drift.

## Archive-path inconsistency — two coexisting locations

A repo that migrated its archival taxonomy at some point (e.g. adopting a top-level `archive/` convention where an older layout nested archives under `tasks/`) may carry a grandfathered legacy path in one specific repo, alongside the current convention used everywhere else and by every archival writer. An in-place migration of the old path would invalidate live provenance backlinks pointing at it — so the fix is not to migrate it, but to treat the old path as read-only legacy substrate going forward, with every new archival write going to the current top-level location.

**Query-time implication:** a query tool scoped to the current convention's path won't surface entries still sitting at a legacy path without an explicit opt-in flag for that legacy location. Know which convention your query surface reads before concluding an archive is empty.

## Handoff archival mechanisms — five moving surfaces

Five distinct surfaces perform `git mv` from `state/handoffs/` (live) → `archive/handoffs/` (archived). They are **not redundant** — they cover different lifecycle events:

1. **`/handoff` chain-archival** — when the new handoff names a chain predecessor as `consumed`/`claimed`, the predecessor moves at the same commit as the new handoff lands.
2. **`/workstream-complete`'s terminal-archival directive** — terminal archival when a workstream ships. Marks `status: consumed`/`claimed`, populates `shipped_in:`, performs the `git mv` in the workstream-complete commit.
3. **SessionStart-hook orphan boot-sweep** — at session boot, any `state/handoffs/*.md` with `status: consumed`/`claimed` (or a retired-but-tolerated legacy `status: superseded`) AND no corresponding `live → archive` git-mv on its own branch is swept. Handles the case where a session crashed between status-flip and `git mv`. Never write the retired status on new handoffs; the sweep stays tolerant of it only for historical/external records.
4. **`/distill` archive enumeration** — does NOT perform the move itself, but reads `archive/handoffs/` and (under the three-condition safety guard in § /distill delete safety guards) may delete entries after knowledge extraction.
5. **A daily deployment-axis sweep**, engine-resident — keyed on the **DEPLOYMENT axis** (`deployment_state: shipped` + resolvable `shipped_in:`), distinct from the CONSUMPTION axis all four surfaces above use. Archives handoffs that have shipped but were never consumed through the standard lifecycle path (e.g. workstreams that shipped via direct commit without a `/workstream-complete` ceremony).

The five surfaces compose: every consumed/superseded handoff ends up in `archive/handoffs/` eventually, regardless of which session's ceremony triggered the move. Hard-deleting a `state/handoffs/` entry without going through one of these five surfaces is a tripwire — see `coordinator-tripwires.md` § Handoff lifecycle.

## Roadmap-only frontmatter fields (`kind: spinoff-roadmap`)

The roadmap-planning pipeline introduces frontmatter fields that are **exclusive** to `kind: spinoff-roadmap` — the schema validator rejects them on `kind: handoff` or `kind: spinoff` (non-roadmap):

- `blocks:` — list of `stub_id` strings this stub blocks
- `blocked_by:` — list of `stub_id` strings this stub depends on
- `roadmap_id:` — slug identifying the parent roadmap
- `stub_id:` — globally-unique stub code; `<slug>-<N>` where `<slug>` derives from `roadmap_id` (e.g. `example-initiative-3`, `ccos-1`)
- `sprint:` — sprint number within the roadmap
- `wave:` — wave number within the sprint (parallel fan-out unit; see § Wave vs sprint)
- `cost:` — appetite/budget hint (open-text; not validator-enforced)

These fields drive the STUB-INDEX query callout, the `blocked_by` topo-sort that derives wave order, and the pm-gates.md validator. They are **NOT** used by ordinary handoffs today — the ticket vocabulary is roadmap-pipeline-only.

**Validator consequence:** Mixing roadmap-only fields into a `kind: handoff` frontmatter fails the frontmatter linter. If a regular handoff genuinely needs to reference a roadmap stub, link via body prose (e.g., `Implements example-initiative-7`), not frontmatter.

## PM-authorization capture variance across repos

A `authorized_by_pm:` / `priority:` structured frontmatter pair and a body-narrative "Authorization" section (a quoted PM message, no structured field) are both valid ways to capture PM authorization on a spinoff — neither field is required for `kind: spinoff`. Different repos in a fleet tend to converge on one form or the other, which complicates cross-fleet auditing:

- A structured-only auditor misses spinoffs that captured authorization as body narrative entirely.
- A body-narrative auditor cannot mechanically verify authorization at all.

**Operational stance:** no forced normalization. The structured form is preferred for new spinoffs (cheaper audit, queryable), but body-narrative authorization is grandfathered where it already exists. If a structured cross-fleet audit ever needs to fire, scope it to the structured-field shape and surface body-narrative spinoffs as "manual-review-needed" rather than failing them.

## query-records handoff-archived type

`bin/query-records` supports a `handoff-archived` type (distinct from `handoff`) that maps to `archive/handoffs/*.md`. Same schema applies, or relaxed-schema sibling `schemas/handoff-archived.schema.json` where `deployment_state:` is not required. Use `--older-than Nd` (inverse of `--since Nd`) to enumerate archived handoffs older than N days. Note: `--where "created<14d"` uses non-ISO comparand and returns garbage — use `--older-than 14d` instead. Used by `/distill` for archive enumeration.

## query-records engine — schema and record types

`bin/query-records` (Node, importable as library) is the canonical frontmatter-indexed query CLI. Record types it indexes:

- `handoff` — `state/handoffs/*.md` (live)
- `handoff-archived` — `archive/handoffs/*.md` (archived; see § query-records handoff-archived type for `--older-than` quirk)
- `plan` — `docs/plans/*.md`
- `decision` — `docs/decisions/DR-*.md`
- `lesson` — `state/lessons/*.yaml` entries (post-triage, structured)
- `completion` — `state/completions/*.md` (per-month buckets)
- `memo` — `cross-repo/inbox/*.md` and `cross-repo/archive/*.md` (cross-repo communication)

**Preference:** `bin/query-records` is the preferred lookup over static-list grep for any of these record types. Stale-index beats grep-on-prose for structure queries.

**Filter syntax:** `--type <type> --where "<key>=<val>"` supports a single equality clause. Multi-condition `where=` works ONLY from CLI; inside `<!-- query-callout:start -->` blocks it is tokenized on whitespace and silently drops conditions after the first (see § Roadmap-planning pipeline — STUB-INDEX query callout constraint).

## No standing per-repo handoff tracker — by design

No tracked repo carries a standing markdown tracker / index of handoffs. The closest surfaces — an ephemeral orientation-cache file (rewritten each morning) and the `state/handoffs/` folder itself — are either short-lived or directory-shaped rather than narrative.

This is **intentional**, not a gap:

- `bin/query-records --type handoff` is the canonical query surface. A hand-maintained tracker would drift; the query engine reads frontmatter directly.
- `/workday-start` builds the per-day orientation cache from query-records output, not from a tracker file.

If a "tracker is missing" instinct fires, the answer is almost always to run the query, not to author a tracker. Authoring a `state/handoff-tracker.md` reintroduces the drift problem and tripwires the state/tasks-split guard if mis-located.

## Six lineage mechanisms — unified vocabulary

Six distinct frontmatter fields express handoff/memo lineage and DAG edges, each with different semantics. None are unified into a single field, and the differences are load-bearing:

| Field | Direction | Semantics | Level-of-effort walk? | Archival guard? | Where used |
|---|---|---|---|---|---|
| `predecessor:` | ancestor → this | primary spine — "this handoff continues from that handoff" (single ancestor path or `none`) | yes | yes | every handoff |
| `additional_predecessors:` | ancestors → this | fan-in secondary edges — "this handoff also continues from these additional parents" (array of paths) | yes | yes | merge-point handoffs (PM-directed only) |
| `forked_from:` | branch-point → this | fan-out branch-point ancestry — lineage/render-only, NOT effort-aggregated | **no** | yes | spinoffs carrying branch-point ancestry (PM-directed only) |
| `coordinates_with:` | peer ↔ peer | "this handoff/memo operates in coordination with that sibling" (no continuity) | no | no | handoffs and cross-repo memos that need to name a coordinating peer without claiming continuity |
| `consumed_by:`/`claimed_by:` (a schema rename in progress; write path pending — read both) | this → claiming-session | "this handoff has been picked up by session UUID X" (populated at `/pickup`) | no | no | every handoff, populated at pickup time |
| `origin_*` (`origin_session`, `origin_handoff`, `origin_plan_id`, `origin_goal_id[]`) | originating-session → this | originating-session provenance axis — "what session/handoff/plan/goal spawned this fork" (nullable; backfill=null; no retroactive churn). `origin_handoff` is the sole handoff-DAG edge among the four; the other three are cross-entity refs served by a separate query projection, not this walker. `origin_session`/`origin_handoff`/`origin_plan_id` are scalar; `origin_goal_id` is an array (multi-goal forks are real). Distinct from `predecessor` (continuation), `forked_from` (branch-point), `deliverable_id` (level-of-effort grouping), and `initiative` (FK). | **no** | no | spinoff forks (`kind: spinoff`, `spinoff-roadmap`, `spinoff-goal`, `spinoff-roadmap-creator`); null for pre-existing/non-fork handoffs |

`predecessor:`, `additional_predecessors:`, `forked_from:`, `coordinates_with:`, and `origin_*` are authored at handoff-write time and assert lineage/sibling-ness. `consumed_by:`/`claimed_by:` is mutated at pickup time and asserts current claim state.

**Don't unify.** They answer different questions: "where did this come from?" (`predecessor`), "what other parents does this merge?" (`additional_predecessors`), "what thread did this fork from?" (`forked_from`), "what is this in conversation with?" (`coordinates_with`), "is this claimed right now?" (`consumed_by`/`claimed_by`), "what session/plan/goal spawned this fork?" (`origin_*`). A single field would either lose information or require sub-typing that defeats the point.

`origin_handoff` and `forked_from` both point at the spawning baton and usually carry the same value, but they are orthogonal axes (different kind-applicability, different archival-guard participation, different producer) — an enforced schema invariant requires them equal WHEN BOTH ARE SET, while permitting `origin_handoff` alone on fork kinds where `forked_from` is illegal.

**`forked_from` vs `additional_predecessors` semantics (load-bearing distinction):**
- `forked_from` records branch-point ancestry for render and archival-guard traversal. The level-of-effort aggregator does NOT follow it — a pure-fork spinoff's effort is isolated to its own thread. To accumulate level-of-effort across a fork, the rejoining handoff must name the fork-point via `additional_predecessors`.
- `additional_predecessors` participates in both level-of-effort accumulation (forward walk) and archival-guard traversal (reverse-membership check).

**Archival guard TOCTOU window (documented limitation, git-recoverable):** the "does this node have live children" check and the subsequent `git mv` archival are two separate operations — a concurrent EM session may author a new handoff naming the candidate node as a parent in the window between check and move. This is low-frequency and fully git-recoverable (the archived node reappears via `git log`), but a strict cross-platform atomic lock isn't available on every target shell. Mitigations: (a) fuse the check and move into a single call where possible; (b) an existing mkdir-style claim lock already protects the pickup gate.

**Querying lineage:** a full lineage graph requires all six fields above, plus `authoring_session:` (spinoff origin prose), `shipped_in:` (terminal SHA/PR), and `archived_handoff:` (extraction backlink in DRs/wikis).

## Handoff-scope language hazard

Handoff body phrasings of the form *"Out of scope for next session: Do NOT extend the plan, add new probes, or refactor adjacent install code. The single goal is X."* are well-meant scope-narrowing, but they routinely backfire at pickup.

The hazard: the picking session reads the negative list and treats every item on it as **proven-unnecessary** rather than **deferred-by-author**. When the pickup encounters substrate that legitimately needs the deferred work (e.g., an "adjacent install code" path that turns out to be the actual root-cause locus), the handoff text actively suppresses the right response.

**Better shape:** name the **positive** scope ("The single goal is X — land the fix at file:line"), and leave OOS implicit. If specific work must be deferred, frame it as *"deferred to follow-up handoff Y because Z"* — a named follow-up handoff, not a prohibition. A prohibition without a follow-up baton is appetite-hedged scope — OOS framing must be architectural, not a blanket "don't touch."

**Pickup-side mitigation:** if a handoff carries negative-list OOS framing, treat it as authoring-time hypothesis, not ground truth. The premise-check section (§ Pickup-side premise check) applies to OOS framing too — verify the deferred items truly are deferrable before treating them as off-limits.

## /distill delete safety guards for archived handoffs

Three conditions must ALL be met before `/distill` may delete an archived handoff:

1. `shipped_in:` frontmatter key is populated (git history is the permanent paper trail; without this, the archive entry is not auditable).
2. At least one extraction artifact (DR in `docs/decisions/` or wiki entry in `docs/wiki/`) was written referencing the source via the `archived_handoff:` provenance frontmatter key — a **top-level** key, NOT a sub-key under `provenance:` (which is a different schema: list-of-objects with `path` + `last_verbose_sha`). OR the handoff is empirically content-free.
3. Active-reference check: ripgrep `archive/handoffs/<basename>.md` across `docs/`, `tasks/`, `archive/specs/`, and plugin sources. Any live reference blocks deletion.

If `shipped_in:` is absent, surface to PM with "missing-paper-trail" diagnosis; do not delete.

## Roadmap-planning pipeline — STUB-INDEX query callout constraint

The STUB-INDEX uses a `bin/query-records` query callout, not a hand-maintained table:

```markdown
<!-- query-callout:start type=handoff where="roadmap_id=<id>" sort="sprint,wave" -->
<!-- query-callout:end -->
```

**Single-clause-only constraint:** `bin/refresh-queries.js` token-splits the BEGIN marker on `\s+`, so multi-condition `where=kind=spinoff-roadmap AND roadmap_id=<id>` gets tokenized into three tokens — only the first contributes, others are silently dropped. Multi-condition `where=` only works from the CLI, not inside query callouts. Workaround: use `where=roadmap_id=<id>` (single clause — the cross-field validator guarantees `roadmap_id` implies `kind: spinoff-roadmap`).

Wave order is derived from topological sort over `blocked_by`. Visualize: `bin/query-records --type handoff --where "kind=spinoff-roadmap AND roadmap_id=<id>" --format graph-dot | dot -Tsvg`.

## pm-gates.md — PM gate document

The roadmap-planning skill writes `pm-gates.md` listing each product-coupled question, the sprint it gates, and the disposition format. Schema: `| sprint | stub_id | gate question | disposition format | resolved? |`

Validator rule: any stub with `gate_dependency:` text that starts "PM " OR contains "decision needed" / "approval needed" / "policy" / "scope" / "user-facing" MUST have a corresponding row in `pm-gates.md`. A gated stub with no matching pm-gates row blocks Phase 3 entry.

## Spinoff Granularity — Bundle by Doctrine Class, Don't Fragment 1:1

**Synthesis-gap items shouldn't fragment 1:1 into spinoffs — bundle by doctrine class.**

When a gap-audit surfaces N items, each became its own spinoff in the documented failure case — defensive-architecture, error-classification, status-bar UX, MCP registry, etc. Each individual spinoff cost a pickup-cycle (frontmatter mutation commit + workstream-complete ceremony + archive-completed entry) that dwarfed the actual authoring work (≤50-line wiki + 1 lesson). PM at workstream-complete: *"so many unnecessary tiny spinoffs, so many of these could have been bundled."*

**How to apply:** when a gap-audit surfaces N items, bundle by *doctrine class* (defensive-architecture, error-handling, agent-UX) before authoring spinoffs — one spinoff per class, ACs enumerated as sub-items. The pickup-cycle cost is the dominant per-spinoff overhead; bundling amortizes it.

**Threshold heuristic:** ≤30-line authoring deliverables per item are bundling candidates, not standalone spinoff candidates.

Sister failure to backlog-as-closure (routes too few items forward) and `oos_lack_of_appetite` (routes items nowhere): both are routing failures at the audit→action seam. The 1:1 failure routes too many items forward at too-fine granularity — fragmentation that defeats the pickup economy.

Applies to: any synthesis/audit/gap-list that surfaces N>2 actionable items in one pass.

## Install Seed Loop — Only-If-Absent, Never Clobber Consumed Batons

A seed/scaffold loop that copies install batons into `state/handoffs/` MUST be **only-if-absent**: before copying, check the destination file's frontmatter `status:` and skip any baton whose status is `consumed`/`claimed` (schema mid-rename — the corpus is mixed, check both) or `superseded`.

**Why.** An unguarded seed loop unconditionally overwrites destination files. A baton already at `status: consumed` gets reset to `status: active` / `ready_to_fire`, losing its `consumed_by:` and `consumed_at:` fields (or their renamed successors `claimed_by:`/`claimed_at:`, once the write path cuts over). Effect: a finished install leg resurfaces as live work at the next `/pickup` or `/workday-start`. A template comment may claim "the seed is AUGMENT, not replace," but an unconditional `cp` replaces unconditionally.

**Empirical origin.** Running the install seed loop overwrote two already-`status: consumed` install batons back to `status: active` / `ready_to_fire`, dropping `consumed_by:`. It recurred overnight after a full-tree restore. Both finished install legs resurfaced as live work in `/pickup` and `/workday-start`.

**Rule.** A seed loop must guard each copy with a status check:

```bash
dest="$HANDOFF_DIR/$baton"
if [ -f "$dest" ]; then
    status=$(grep -m1 '^status:' "$dest" | awk '{print $2}')
    if [[ "$status" == "consumed" || "$status" == "claimed" || "$status" == "superseded" ]]; then
        continue   # skip — baton already closed
        # Note: "claimed" is the successor to "consumed" (corpus mixed — check both).
        # "superseded" is a retired-but-tolerated-for-legacy handoff status.
        # Keep the skip condition here for legacy/external records; never write "superseded" on new handoffs.
    fi
fi
cp "$src" "$dest"
```

The guard is idempotent: a not-yet-seeded baton passes through normally; a re-seeded baton whose destination file exists with a terminal status is skipped. The `authoring_session:` and `created:` fields in the source template do NOT override the lifecycle state of an already-consumed/claimed destination baton — the destination's frontmatter is the authority, not the template's.

*Pairs with § Frontmatter format drift (`created:` normalization) and the `consumed_by:`/`claimed_by:` claim-gate (§ Concurrent-pickup interaction) — both depend on frontmatter staying accurate after seeding.*

## See also

- `skills/pickup/SKILL.md` — premise check and awaiting_gate aging (both Step 1: Classify, Load, and Reconcile Against Reality) consumers.
- `skills/roadmap-planning/SKILL.md` — wave/sprint distinction, soft-seams body section, and Phase 2 exit gate consumers.
- `skills/spinoff/SKILL.md` (if present) — initial-state authoring for `kind: spinoff`.
- `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Handoff Lineage" — deployment_state enum, predecessor rules (canonical tripwire form).
