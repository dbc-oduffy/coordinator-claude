---
kind: wiki
title: Spinoff Handoffs — Mid-session Forks vs Continuations
status: active
created: 2026-05-06
sources:
  - archive/handoffs/2026-05-05_104957_spinoff-formalization.md
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

Source: `archive/specs/2026-05/2026-05-07-handoff-no-successor-gate.md` (status: complete, 2026-05-07).

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

> Added 2026-06-01. Spinoffs are normally PM-authorized and keyword-gated: the EM surfaces `Candidate spinoff: <slug> — <topic>. Authorize?` and blocks; paraphrase is not authorization; only `/spinoff` (or `coordinator:roadmap-planning`) creates one. This carve-out names the **single** exception and explains why it does not erode the gate.

When an operator installs coordinator as the root of a multi-repo setup, each *additional* repo they want (example-orchestration-hub-repo, or downstream repos) is materialized as a **spinoff** by that repo's installer — not by an EM typing `/spinoff`. (deep-research is NOT such a leg — it is folded into the coordinator bundle for everyone; the former deep-research-claude repo is archived read-only, carries no opt-in, and seeds no baton.) The baton is a normal `kind: spinoff` file in the install-baton rendezvous — a per-machine settings-home folder (`$(coordinator-settings-home)/state/handoffs/`, with bash inline fallback `${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/state/handoffs`), **distinct from the example-orchestration-hub-central handoffs folder `/spinoff` writes to** (see `state-placement-law.md` taxonomy row) — distinguished from the coordinator onboarding handoff by an `install_chain_order:` tag, and carrying `authoring_session:` naming the install + the operator's opt-in (the audit-trail field this schema requires of every spinoff). It is seeded via `cp`/`sed`, not the Write tool, so it does not trip the unauthorized-handoff nudge. This is legitimate because **the authorization is captured at the install's pre-restart question** ("what else do you want to install?"). The operator selecting a leg there *is* the human authorizing that fork — the same authorization `/spinoff` captures, captured at a different but equally explicit moment.

The gate is not eroded:

- **A human still authorizes every leg.** A spinoff never appears unless the operator chose it at the pre-restart question. The installer materializes a choice the human already made; it does not invent a fork. The EM driving the install is not self-initiating spinoffs — it is stitching operator-authorized ones.
- **Scope is narrow.** This applies only to install-time leg-seeding, where the human's selection is the gate. It does not license script- or EM-created spinoffs in any steady-state workstream — there, the `Candidate spinoff: … Authorize?` block still holds.
- **`predecessor: none` is native.** These legs are genuine forks of different install topics, not continuations of coordinator onboarding (which is the handoff). The spinoff frame fits without a lineage exception.

Mechanics and the seed/drive role split live in `agent-install-contract.md` § Install-spinoff layer; the install-chain spine that tracks the legs is `templates/plans/install-chain-tracking.md`.

### Restart / onboarding prose must point cwd at the baton's repo

`/workday-start` and a bare-relative `/pickup` resolve handoffs against the **cwd's git root**. Any leg / restart / onboarding prose that precedes one of these commands must therefore either say `cd <repo>` first or hand an absolute baton path — otherwise the command resolves against whatever repo the operator happens to be sitting in and either finds nothing or picks up the wrong repo's batons. Handing an absolute `/pickup <path>` removes the coupling entirely: the lifecycle bookkeeping (claim, frontmatter mutation, archival) then routes through the baton's own repo regardless of cwd. This matters most in install-chain and multi-repo restart flows, where the operator's cwd after a Claude Code restart is not guaranteed to be the repo whose baton is next. Source: project-rag-ue-addon.

## Frontmatter schema

```yaml
kind: spinoff
status: active
predecessor: none           # always — spinoffs have no continuity ancestor
authoring_session: <one-line description>   # replaces predecessor link as audit trail back to origin
workstream: <slug>          # required, so /pickup can group them
```

`predecessor: none` is load-bearing on the **primary spine**: the "Single Predecessor, No Adjacency-Inference" rule (in coordinator/CLAUDE.md) requires every handoff to have a single named predecessor or `none`. Spinoffs are always `none`; the audit trail back to origin lives in `authoring_session`.

Three optional fields extend or annotate the primary spine — **do not conflate them**:

- **`forked_from: <handoff-path>`** — DAG branch-point ancestry, **lineage/render-only**. The LoE aggregator does NOT follow this edge (preserves DR-014 effort-isolation for pure-fork spinoffs; DR-015). The archival guard DOES follow it — archiving a live fork-point breaks the DAG render walk. Must be PM-directed; adjacency-inference ban applies (coordinator CLAUDE.md § Handoff Lineage).
- **`supersedes:`** — spine-build-time ordering preference ("when building the orientation spine, prefer this baton over the one it names"). No DAG graph semantics; does not affect LoE or archival traversal. See § `` `supersedes:` on a live baton`` below.
- **`authoring_session:`** — origin prose only; no graph traversal. The required audit trail for every spinoff.

### `supersedes:` on a live baton — optional field, distinct from the now-retired `status: superseded`

`supersedes:` is an **optional** field on a `kind: spinoff` baton used by the orientation-supersession convention (see `docs/wiki/agent-install-contract.md` § Orientation-supersession). It asserts a spine-build-time preference — "when building the orientation spine, prefer this baton over the one it names." It is **not** a lifecycle terminator and does not mark any baton as dead.

This is **distinct** from the (now-retired) `status: superseded` handoff lifecycle value. As of 2026-06-26, the handoff `status: superseded` VALUE is retired — a superseded handoff is expressed as `status: consumed` + `deployment_state: abandoned` (which keeps it out of every active list). The `supersedes:` FIELD itself is unaffected and remains live. The `supersedes:` field on a *live* baton does not terminate it.

Canonical contrast (verbatim, also in `docs/wiki/cross-repo-communication.md` § Grandfather cutoff note):

> "`supersedes:` on a memo = terminal (paired with `superseded_by:` + `status: superseded`, wired in the `CROSS_FIELD_RULES` memo block); `supersedes:` on a live baton = conditional+live, a spine-build-time preference (never flips status, no back-pointer, wired in the `CROSS_FIELD_RULES` handoff block)."

Cross-reference: `docs/wiki/cross-repo-communication.md` § Grandfather cutoff carries the matching note disambiguating the memo-side `supersedes:` meaning from this baton-side meaning.

## Pickup-side and workday-start handling

- **`/pickup` with `kind: spinoff`** prepends a one-line banner: *"This is a spinoff workstream — predecessor is none; treat the handoff body as ground-truth spec and proceed."*
- **`/workday-start`** lists spinoffs separately from active handoffs in the orientation cache.
- **Stale spinoff nudge:** a spinoff that hasn't been picked up after N days (default 14) gets a heads-up nudge in `/workday-start`.

## Why this exists as a formal pattern

Three pre-formalization signals motivated it (see [DR-013](#dr-013--formalize-the-pattern-as-coordinatorspinoff-skill)):

1. **Recurring pattern** — real instances were executed within 3 minutes of each other by concurrent EMs.
2. **Ad-hoc shape leaks** — the validator rejected `status: orphan-promotion` as an invalid enum because the ersatz form leaked into a real frontmatter.
3. **PM friction** — verbal description was needed each time.

## Decision Records

### DR-013 — Formalize the pattern as `coordinator:spinoff` skill

**Status:** accepted
**Decision:** Replace ad-hoc "ersatz-handoff" / "orphan-promotion handoff" naming with `kind: spinoff`; ship a skill that drafts the spec.
**Consequences:** Validator enum gains `spinoff`; pickup banner; workday-start segregation; stale nudge.
**Source:** `archive/handoffs/2026-05-05_104957_spinoff-formalization.md`

### DR-014 — `predecessor: none` always, audit trail in `authoring_session`

**Status:** accepted _(lineage-root consequence superseded by DR-015)_
**Decision:** Spinoffs never carry a predecessor link — they are forks, not continuations. The `authoring_session` field carries the audit trail back to origin.
**Consequences:** `/pickup` banner can be deterministic; lineage rules treat spinoffs as roots on the primary spine.

### DR-015 — `forked_from` for spinoff branch-point ancestry (supersedes DR-014 lineage-root consequence)

**Status:** accepted, PM-authorized 2026-06-29
**Decision:** Spinoffs carry `predecessor: none` on the primary spine (DR-014 core rule unchanged) but MAY carry `forked_from: <handoff-path>` to record the branch-point handoff in the lineage DAG as **lineage/render-only**. The LoE aggregator does NOT follow `forked_from` edges, preserving DR-014's effort-isolation intent for pure-fork spinoffs. LoE accumulation across a fork requires explicit remerge via `additional_predecessors` on the rejoining handoff.
**Consequences:** Spinoffs are DAG roots on the primary spine but may carry branch-point ancestry for render and archival-guard purposes. The "lineage rules treat spinoffs as roots" consequence of DR-014 is superseded for the DAG render/archival axis only; DR-014's `predecessor: none` + `authoring_session:` audit trail requirements are otherwise unchanged.

## Pickup-side premise check

> Consumed by: `skills/pickup/SKILL.md` Step 3.4e.

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

When a handoff names a target file (e.g., "extend `docs/wiki/X.md`"), `Read` that file and confirm the topic and section actually fit before writing. Stale handoff-named targets accumulate when the wiki has been refactored between handoff-author time and pickup time — the file may still exist but now cover a different scope, or the relevant section may have moved to a sibling file. Source: 2026-05-15 project-rag-ue-addon pickup.

### Parked-tracker rows: framing is hypothesis, substrate is ground truth

When resuming work that names "parked" tracker rows, project-board items, or backlog entries with framing like "Y is blocked on X" or "this is parked pending Z", verify the substrate before accepting the parking framing. Stale advisory/call-note markdowns and project-tracker rows accumulate over weeks; the parking premise may have been overtaken (the blocker shipped, the scope was rolled in elsewhere, the row references files that have moved). Run a git-log spot-check on the cited paths before treating the parked state as live work. Source: 2026-05-16 example-game-workbench-repo resume.

### Empirical baseline

Expect 30–60% of inherited items to be already closed (pickup SKILL Step 3 empirical note). Premise decay compounds on top of this: a 24h-old handoff may have 1–2 stale file assertions; a 7d-old handoff routinely has more. Treat unverified premises as blocking gaps, not deferrals.

## Deployment_state lifecycle for spinoffs

> Cross-reference: coordinator CLAUDE.md § Handoff Lineage (deployment_state enum).

### Initial state at authoring

- `/spinoff` sets `deployment_state: ready_to_fire` for stubs intended for immediate pickup.
- `roadmap-planning` sets `deployment_state: awaiting_gate` for stubs with `gate_dependency:` (sequenced stubs that must not be picked up until a predecessor ships).

### Lifecycle table

> Column states refer to `deployment_state:` frontmatter, NOT `status:`. The `status:` enum is `active | consumed` (per coordinator CLAUDE.md § Handoff Lineage); `shipped` is not a valid `status:` value — use `consumed` + `shipped_in:` instead. (`superseded` was retired 2026-06-26; supersession is now expressed via `deployment_state: abandoned` + lineage fields.)

| Event | From → To | Skill responsible |
|---|---|---|
| author spinoff | (n/a) → ready_to_fire \| awaiting_gate | /spinoff or roadmap-planning |
| /pickup grabs | ready_to_fire → in_flight | /pickup Step 5 |
| gate clears | awaiting_gate → ready_to_fire | /handoff or /workstream-complete (gate-meaningfulness audit) |
| session ships | in_flight → shipped (+ shipped_in) | /handoff or /workstream-complete |
| session pauses | in_flight → ready_to_fire | /handoff |
| abandoned | any → abandoned | PM-authorized only |

### Concurrent-pickup interaction

`/pickup` mutates frontmatter in place with the `cs_claim_handoff` gate; a second EM observing `consumed_by:` populated after `git fetch` fails loud (pickup SKILL Step 5 pre-mutation gate). No silent double-claim — the detecting session exits non-zero and surfaces to PM.

The same fail-loud-on-live-peer guarantee extends to **plan execution**: `cs_claim_plan` (the third sibling claim primitive, added 2026-06-26) gates `execute-plan` Phase 1.5 and `workstream-complete`. A second live session attempting to drive the same plan fails loud at the claim boundary — before any tokens are spent on duplicate reconcile or ceremony work. See `docs/wiki/cross-repo-communication.md` § Claim-at-pickup parity with handoffs (`plan` class paragraph) for the full lifecycle.

## Claim liveness — PPID-authoritative model (shipped 2026-06-27)

> Spec: `docs/plans/2026-06-27-liveness-first-claim-staleness.md`. Code: `lib/coordinator-session.sh`.

Session liveness (used by claim-takeover, reaper, and memo-sweep) uses a two-layer model. All
consumers route through `_cs_claim_holder_live` → `_cs_session_live` (function `_cs_session_live()`, ~line 949) — single liveness
key, no divergence across callers.

**Layer 1 — PPID-authoritative (when `stable_pid` is present in meta.json).**
`cs_init` (function `cs_init()`, ~line 306) captures the hook's `$PPID` — the long-lived `claude` session process, not
the short-lived hook subshell — as `stable_pid`, after comm-verifying it with
`ps -p $PPID -o comm=` exactly matching `claude` (Guard 1). It also captures `stable_pid_lstart`
(process start time) for PID-recycling defense (Guard 2). At liveness query time,
`_cs_stable_pid_alive` (function `_cs_stable_pid_alive()`, ~line 114) reads the current `ps -o lstart=` for `stable_pid`:
process alive with matching lstart → **LIVE**, regardless of `last_activity` recency;
process gone or lstart changed → **DEAD** within seconds of session exit or kill.
Recency is NOT consulted when `stable_pid` is present — this is what "liveness-first" means.

**Layer 2 — recency fallback (when `stable_pid` is absent).**
When Guard 1 misses (non-harness run, comm ≠ `claude`, legacy meta.json), `stable_pid` is left
empty and `_cs_is_session_live` (function `_cs_is_session_live()`, ~line 927) applies the pre-existing 30-min `last_activity`
recency rule — unchanged behavior, zero regression on those paths.

**Why this is NOT the forbidden `$$`-as-liveness gate.**
The 2026-06-23 hardening (specs: `archive/completed/2026-06/2026-06-23-claim-liveness-hardening-r2-df68c4.md`
and `archive/completed/2026-06/2026-06-23-claim-lock-pid-death-false-positive-63c418.md`) removed
`$$` because that is the hook subshell — dead within seconds of every tool call, making every
session appear dead. `stable_pid` is the PARENT pid (`$PPID`), a separate field that survives the
entire session. The `_cs_pid_alive` helper on the `pid`/`$$` field remains prohibited for liveness;
`_cs_stable_pid_alive` on the `stable_pid`/`$PPID` field is the legitimate path (see the comment
at coordinator-session.sh:67–72 distinguishing the two).

**Accepted residual / worst-case bound.**
An abandoned-but-alive session (machine left on, unattended) holds its claim until the `claude`
process exits. This is bounded by: (a) `kill -0` / `ps` detects exit within seconds, including on
crash; and (b) the 24h absolute-inactivity reaper backstop (`cs_reap_stale` (function `cs_reap_stale()`, ~line 720)) which fires
on any session regardless of `stable_pid` state. This is NOT an unbounded leak — it realizes the
PM directive: "a session that is genuinely still running should be presumed to retain its holds
until it ends."

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

Example: `- roadmap-run-abc/tc-4 — shares the `bin/lint-frontmatter.js` cross-field rules surface; coordinate on rule-ordering if both stubs edit the same array.`

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

> Consumed by: `skills/pickup/SKILL.md` Step 3.4d aging-reconcile clause.

### Why aging matters

Gates clear silently; gate text drifts in meaning over time. The gate-meaningfulness audit in roadmap SKILL Step 3.2 fires on the `awaiting_gate → ready_to_fire` transition — but it cannot catch the aging-without-unblock case, where the gate text now misnames the blocker without anyone having triggered a transition.

### Thresholds

Force a re-check when ALL THREE conditions hold:
1. `now − created:` ≥ 14 days
2. `deployment_state: awaiting_gate`
3. No `last_gate_recheck:` field present, OR `last_gate_recheck:` is ≥7 days ago

**Threshold derivation:** 14d matches the existing spinoff stale-nudge threshold (wiki § "Pickup-side and workday-start handling", L73). The 7d recheck cadence matches the lesson-triage recheck shape (`state/lesson-triage-recheck-due-*.md` pattern, ~weekly cadence per coordinator CLAUDE.md § Triage cadence).

### Recheck mechanics

1. Read the gate witness named in `gate_dependency:`.
2. **Gate cleared:** flip `deployment_state: ready_to_fire`; write `last_gate_recheck: <ISO date>` in mutation pass.
3. **Gate still closed, text still accurate:** write `last_gate_recheck: <ISO date>` in mutation pass; surface gate status to PM.
4. **Gate still closed, text now misnames the blocker** (e.g., named sibling stub archived without shipping, named PR abandoned): surface to PM with the discrepancy — do NOT silently retain the stale gate text.

### Frontmatter field — `last_gate_recheck:`

ISO date (e.g., `2026-05-14`). Written by `/pickup` Step 5 mutation pass when the aging-reconcile clause fires. Absent on freshly-authored spinoffs; `/pickup` adds it at first aging-triggered recheck.

### `awaiting_gate` standdown requires substrate read, not literal-string gate match

*Source: project-rag, 2026-06-14 — undated. [universal]*

**Rule.** Picking up a `kind: spinoff` handoff with `deployment_state: awaiting_gate` is NOT satisfied by reading the frontmatter `gate_dependency:` string + scanning `git log` for SHA matches. The gate predicate is a *pointer to substrate* — the handoff body cites empirical artifacts (spike reports, reproducers, disposition memos) whose contents define whether the gate has fired. A frontmatter-and-log glance produces standdown recommendations on incomplete evidence; the PM rightly pushes back, you re-read the substrate, and the cycle costs more than the read time it "saved."

*Case.* A standdown recommendation on `2026-06-09_210603_sub-daemon-slices-2-3.md` was authored after reading only the handoff body + `git log`. PM challenged ("you can't make that determination after a casual glance"). Reading the substrate the handoff actually named — `em-proposal.md`'s reshape banner, `the Staff Engineer-review.md`'s 12 findings, `segment-lru-spike.md`'s empirical falsification, the addon-EM disposition memo — showed the gate's "addon misbehavior takes down host" predicate had already fired in *latent* form: the C-reproduce 2.913 GiB crash was that class of failure, suppressed only by the 3.5 GiB stopgap the disposition memo explicitly warned was aging into load-bearing. The cheaper-alternative framing ("host-side per-band routing in flight") was directionally true but not equivalent — it bounded RSS without providing fault containment. (case: project-rag 2026-06-14 — undated)

**Discipline.** Before recommending standdown OR proceed on an `awaiting_gate` handoff: (1) Read every `tasks/<workstream>/*` substrate file the handoff cites end-to-end, not just the handoff body. (2) Empirical artifacts (spike reports, reproducers, disposition memos) take precedence over frontmatter strings — when an empirical artifact shows the gate predicate fired in latent form, the gate has cleared regardless of frontmatter phrasing. (3) The forced-articulation doubt-check (`coordinator:plan` Branch B.0) applies BEFORE the standdown recommendation, not after — name the load-bearing scope-boundary uncertainty whose wrong guess would invalidate the rec. Composes with § Pickup-side premise check (premise drift on load-bearing claims surfaces to PM before mutation, not after a casual-glance disposition).

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

For the dependency-order invariant that governs how stub numbers and `(sprint, wave)` execution slots must align with `blocks`/`blocked_by` edges — including the enforcement surfaces (`audit-roadmap.sh` Audit 5, `roadmap-graph.js`) and the scope-honesty note on undeclared edges — see [`roadmap-numbering.md`](roadmap-numbering.md).

## Crash-recovery handoffs are one-per-workstream

`kind: recovery` handoffs are scoped by **incident**, not by size of the recovered work. When a session crashes or is killed mid-flight, write one recovery handoff per surviving workstream — regardless of whether the recovered slice is "trivial" or "big." Judging "this is too small for a handoff" silently overrides the directive that recovery handoffs exist to make crash-loss boundaries discoverable; the cost of an extra small handoff is a few minutes, the cost of a missed one is the successor session re-discovering the crash boundary by stepping on it.

Commit-granularity is incident-scoped, not workstream-scoped: if two concurrent workstreams both crashed, that's two recovery handoffs (separate `predecessor:` pointers to each crashed handoff's SHA), not one merged "we crashed" handoff. Each successor picking up either workstream needs its own framing of what was in flight, what got committed pre-crash, and what didn't.

## Recovery-pickup hygiene — untracked-files and diagnostic decay

Recovery pickups produce a noisier working tree than ordinary pickups: pre-crash partial writes survive as untracked files, and the crashed session's diagnostic notes age fast.

- **Untracked files at recovery pickup are evidence, not noise.** Before staging or committing on a recovery handoff, list every untracked path and diff it against the crashed session's intended scope (`git status --porcelain=v2 -uall` over `scope:` pathspecs). An untracked `.tmp.<pid>.<nanos>` file is an Edit-tool atomic-write crash — diff against its target before deletion. An untracked source file not in the recovery scope is out-of-scope work from a sibling session — surface to PM rather than absorb silently.
- **Handoff diagnostics decay.** A crash handoff's "what was in flight" framing is hypothesis at pickup time: cited file:line offsets may have moved, cited SHAs may have been rebased, cited test failures may have been fixed by a sibling recovery. Re-run the cited failing test on HEAD before treating it as live; `git log --oneline -- <cited-paths>` since the crash report timestamp before treating the crash boundary as the current boundary.
- **One recovery handoff per surviving workstream still holds** — the hygiene rules here are per-handoff, not per-incident. Two concurrent crashed workstreams produce two recovery handoffs, each with its own untracked-files audit.

Source: 2026-05-26 recovery-pickup post-mortem; cross-reference `verification-discipline.md` § Crash recovery: artifact-survey-first across peer repos.

## predecessor: in practice — almost always `none`

Doctrine describes lineage chains via `predecessor:`; empirical observation across active repos in 2026-06 shows only ONE live handoff in any tracked repo carrying a real predecessor path. The dominant `predecessor:` value is `none` (spinoff frame) or absent.

This is **not** a bug. Continuation chains tend to be in-session (one EM threads through several handoffs in a single thread) where the `/pickup` → `/handoff` cycle implicitly carries lineage via session memory rather than the file field. Long-form cross-session ancestry is rare because (a) most workstreams complete in 1–2 sessions, (b) spinoffs (`predecessor: none` by schema) account for the majority of new handoffs, and (c) `kind: recovery` is the only kind that routinely back-points to a non-handoff SHA.

**Operational implication:** Treat `predecessor:` as a low-signal lineage field at query time. The high-signal lineage fields in practice are `authoring_session:` (spinoff origin), `shipped_in:` (terminal commit/PR), `consumed_by:` (pickup-session UUID, see below). Don't infer adjacency from `predecessor:` being populated on one of several timestamp-adjacent handoffs — the rule in coordinator CLAUDE.md (§ Handoff Lineage — Single Predecessor, No Adjacency-Inference) is exactly this caveat.

Source: 2026-06 batch-3 substrate audit across example-game-repo, project-rag, coordinator repos.

## consumed_by: is a session UUID, filename SHA is different

`consumed_by:` is populated by `/pickup` Step 5 with the **picking session's UUID** (a Claude-Code session identifier). The handoff filename's discriminator suffix, by contrast, is an 8-hex **session-SHA** of the authoring session — a different identifier space derived at write time.

Practical consequences:

- Do not assume the 8-hex in a filename equals the UUID prefix in `consumed_by:`. They are different identifier classes and will not collide.
- A handoff with `consumed_by:` populated is **claimed** — it must not be re-picked. `/pickup` enforces this via `cs_claim_handoff` EEXIST (single-machine) and `git fetch` + `consumed_by:` non-empty check (cross-machine). See coordinator CLAUDE.md § Handoff Lineage — Concurrent `/pickup` is fail-loud.
- Closing a handoff (`status: consumed`) is a separate write from claiming it (`consumed_by:` populated). The two fields move together at `/workstream-complete` Step 2.7, but auditing should treat them as a pair, not synonyms.

Source: 2026-06 batch-3 frontmatter audit; cross-reference DR-110 (concurrent-pickup fail-loud).

## Frontmatter format drift — `created:` and `pickup_ready:`

Two normalization gaps observed across recent handoffs in the same repo, same week:

- **`created:` date format mixed.** Bare `YYYY-MM-DD` and full ISO-8601 (`2026-06-14T08:31:17Z`) both appear. Trackers that do string-comparison aging (`now − created`) mis-handle the mixed shapes — a strict ISO parser rejects bare-date entries, and a strict bare-date parser truncates ISO-8601. **Normalize to bare `YYYY-MM-DD`** at write time — the canonical form the contract declares (`schemas/handoff.schema.json` `created: iso-date` → `format: date`); the scaffolder (`coordinator-doc-new`) already emits bare date, so templates should match it rather than diverge to ISO-8601. (`created` is a creation-DAY; the date-time instant lives in the `## Session Ledger` body, kept separate.) Pickup-side aging logic should still parse both shapes defensively for legacy records. <!-- Amended 2026-06-26 by datetime-handling-coherence (C-Z2): flipped ISO-8601→bare-date to align with the contract's created: iso-date declaration. -->
- **`pickup_ready:` boolean type drift.** YAML `true` (unquoted boolean) vs `"true"` (quoted string) coexist. Strict YAML-bool consumers mis-handle the string variant as truthy-non-bool. **Normalize to unquoted YAML boolean** at write time; validator `bin/lint-frontmatter.js` should reject quoted-boolean forms.

These are mechanical cleanups, not doctrinal conflicts — every writer should canonicalize to one shape. The trackers and `bin/query-records` parse both shapes today to absorb legacy entries; new writes should not perpetuate the drift.

Source: 2026-06 batch-3 frontmatter audit (example-game-repo + project-rag repos, mid-2026-06 week).

## Archive-path inconsistency — two coexisting locations

Archived handoffs land in two parallel locations across the fleet:

- `tasks/handoffs/archive/*.md` — older convention, observed only in example-game-repo repo (predates the state/tasks split).
- `archive/handoffs/*.md` — current convention (top-level archive), used by every other repo and by all five archival writers (`/handoff` chain-archival, `/workstream-complete` Step 2.7, `session-init.sh` orphan boot-sweep, `/distill` archive enumeration, `bin/sweep-shipped-handoffs.sh` deployment-axis sweep).

example-game-repo's older path is grandfathered: an in-place migration would invalidate live `archived_handoff:` provenance backlinks (see § /distill delete safety guards). Treat the older path as read-only legacy substrate; new archival writes always go to the top-level location.

**Query-time implication:** `bin/query-records --type handoff-archived` reads `archive/handoffs/*.md` only. example-game-repo-archived entries from the older path do not surface in distill enumeration without an explicit `--legacy-path tasks/handoffs/archive/` flag (not yet implemented; surface to PM if a example-game-repo archive sweep is ever needed).

Source: 2026-06 batch-3 archive-path audit across all tracked repos.

## Handoff archival mechanisms — five moving surfaces

Five distinct surfaces perform `git mv` from `state/handoffs/` (live) → `archive/handoffs/` (archived). They are **not redundant** — they cover different lifecycle events:

1. **`/handoff` chain-archival** — when the new handoff names a chain predecessor as `consumed`, the predecessor moves at the same commit as the new handoff lands.
2. **`/workstream-complete` Step 2.7** — terminal archival when a workstream ships. Marks `status: consumed`, populates `shipped_in:`, performs the `git mv` in the workstream-complete commit. (2026-06-15 stamping mechanism: plan `archive/completed/2026-06/2026-06-15-shipped-in-archive-stamping-a62b94.md`)
3. **`session-init.sh` orphan boot-sweep** — at session boot, any `state/handoffs/*.md` with `status: consumed` or `status: superseded` AND no corresponding `live → archive` git-mv on its own branch is swept. Handles the case where a session crashed between status-flip and `git mv`. (`status: superseded` is a retired-but-tolerated-for-legacy handoff status as of 2026-06-26 — the sweep stays tolerant of it for historical/external records; never write it on new handoffs.)
4. **`/distill` archive enumeration** — does NOT perform the move itself, but reads `archive/handoffs/` and (under the three-condition safety guard in § /distill delete safety guards) may delete entries after knowledge extraction.
5. **`/workday-start` Step 1.47 deployment-axis sweep** (`bin/sweep-shipped-handoffs.sh`) — daily sweep keyed on the **DEPLOYMENT axis** (`deployment_state: shipped` + resolvable `shipped_in:`), distinct from the CONSUMPTION axis all four surfaces above use. Archives handoffs that have shipped but were never consumed through the standard lifecycle path (e.g. workstreams that shipped via direct commit without a `/workstream-complete` ceremony).

The five surfaces compose: every consumed/superseded handoff ends up in `archive/handoffs/` eventually, regardless of which session's ceremony triggered the move. Hard-deleting a `state/handoffs/` entry without going through one of these five surfaces is a tripwire — see `coordinator-tripwires.md` § Handoff lifecycle.

Source: 2026-06 batch-3 archival-mechanism inventory.

## Roadmap-only frontmatter fields (`kind: spinoff-roadmap`)

The roadmap-planning pipeline introduces frontmatter fields that are **exclusive** to `kind: spinoff-roadmap` — the schema validator rejects them on `kind: handoff` or `kind: spinoff` (non-roadmap):

- `blocks:` — list of `stub_id` strings this stub blocks
- `blocked_by:` — list of `stub_id` strings this stub depends on
- `roadmap_id:` — slug identifying the parent roadmap
- `stub_id:` — globally-unique stub code; `<slug>-<N>` where `<slug>` derives from `roadmap_id` (e.g. `example-initiative-3`, `ccos-1`)
- `sprint:` — sprint number within the roadmap
- `wave:` — wave number within the sprint (parallel fan-out unit; see § Wave vs sprint)
- `cost:` — appetite/budget hint (open-text; not validator-enforced)

These fields drive the STUB-INDEX query callout, the `blocked_by` topo-sort that derives wave order, and the pm-gates.md validator. They are **NOT** used by example-game-repo or project-rag handoffs today — the ticket vocabulary is roadmap-pipeline-only.

**Validator consequence:** Mixing roadmap-only fields into a `kind: handoff` frontmatter fails `bin/lint-frontmatter.js`. If a regular handoff genuinely needs to reference a roadmap stub, link via body prose (e.g., `Implements example-initiative-7`), not frontmatter.

Source: 2026-06 batch-3 cross-repo memo-lifecycle audit; cross-reference DR-108 (`kind: spinoff-roadmap` third valid kind).

## PM-authorization capture variance across repos

`authorized_by_pm:` and `priority:` frontmatter fields appear consistently only in `project-rag` spinoffs. Addon spinoffs (project-rag-ue-addon) record PM authorization in **body narrative** — typically a quoted PM message in the spinoff's "Authorization" section — without a structured frontmatter field.

Both forms are valid under the current schema (neither field is required for `kind: spinoff`), but the variance complicates auditing:

- A structured-only auditor (e.g., `bin/query-records --where "authorized_by_pm=*"`) misses addon spinoffs entirely.
- A body-narrative auditor cannot mechanically verify authorization across the fleet.

**Operational stance for 2026-06:** No forced normalization. The structured form is preferred for new spinoffs (cheaper audit, queryable), but body-narrative authorization in addon spinoffs is grandfathered. If a structured cross-fleet audit ever needs to fire, scope it to the structured-field shape and surface body-narrative spinoffs as "manual-review-needed" rather than failing them.

Source: 2026-06 batch-3 cross-repo memo-lifecycle audit.

## query-records handoff-archived type

`bin/query-records` supports a `handoff-archived` type (distinct from `handoff`) that maps to `archive/handoffs/*.md`. Same schema applies, or relaxed-schema sibling `schemas/handoff-archived.schema.json` where `deployment_state:` is not required. Use `--older-than Nd` (inverse of `--since Nd`) to enumerate archived handoffs older than N days. Note: `--where "created<14d"` uses non-ISO comparand and returns garbage — use `--older-than 14d` instead. Used by `/distill` for archive enumeration.

## query-records engine — schema and record types

`bin/query-records` (Node, importable as library; located at `plugins/coordinator/bin/query-records.js`) is the canonical frontmatter-indexed query CLI. Record types it indexes:

- `handoff` — `state/handoffs/*.md` (live)
- `handoff-archived` — `archive/handoffs/*.md` (archived; see § query-records handoff-archived type for `--older-than` quirk)
- `plan` — `docs/plans/*.md`
- `decision` — `docs/decisions/DR-*.md`
- `lesson` — `state/lessons.md` entries (post-triage, structured)
- `completion` — `state/completions/*.md` (per-month buckets; see DR-064)
- `memo` — `cross-repo/inbox/*.md` and `cross-repo/archive/*.md` (cross-repo communication)

**Tier 2 preference (per coordinator CLAUDE.md § Codebase Investigation):** `bin/query-records` is the preferred lookup over static-list grep for any of these record types. Stale-index beats grep-on-prose for structure queries.

**Filter syntax:** `--type <type> --where "<key>=<val>"` supports a single equality clause. Multi-condition `where=` works ONLY from CLI; inside `<!-- query-callout:start -->` blocks it is tokenized on whitespace and silently drops conditions after the first (see § Roadmap-planning pipeline — STUB-INDEX query callout constraint).

Source: 2026-06 batch-3 query-records engine inventory.

## No standing per-repo handoff tracker — by design

No tracked repo carries a standing markdown tracker / index of handoffs. The closest surfaces — `state/orientation_cache.md` (ephemeral, rewritten by `/workday-start` Step 5.5) and the `state/handoffs/` folder itself — are either short-lived or directory-shaped rather than narrative.

This is **intentional**, not a gap:

- `bin/query-records --type handoff` is the canonical query surface. A hand-maintained tracker would drift; the query engine reads frontmatter directly.
- `/workday-start` builds the per-day orientation cache from query-records output, not from a tracker file.
- The PM-personal list (per DR-042) is hand-maintained outside the repo (`tasks/repo-registry.md` is the cross-machine sibling), not as a per-repo handoff tracker.

If a "tracker is missing" instinct fires, the answer is almost always to run the query, not to author a tracker. Authoring a `state/handoff-tracker.md` reintroduces the drift problem and tripwires `tasks-state-folder-split` if mis-located.

Source: 2026-06 batch-3 tracker-gap inventory across all tracked repos; reinforced by 2026-06 ground-truth audit (b1g-067).

## Six lineage mechanisms — unified vocabulary
<!-- Review: code-reviewer (F7) — heading updated from "Five" to "Six" to match the section body ("Six distinct frontmatter fields") and the table row count (six rows after origin_* addition) -->

Six distinct frontmatter fields express handoff/memo lineage and DAG edges, each with different semantics. None are unified into a single field, and the differences are load-bearing:

| Field | Direction | Semantics | LoE walk? | Archival guard? | Where used |
|---|---|---|---|---|---|
| `predecessor:` | ancestor → this | primary spine — "this handoff continues from that handoff" (single ancestor path or `none`) | yes | yes | every handoff (example-game-repo, project-rag, coordinator) |
| `additional_predecessors:` | ancestors → this | fan-in secondary edges — "this handoff also continues from these additional parents" (array of paths) | yes | yes | merge-point handoffs (PM-directed only) |
| `forked_from:` | branch-point → this | fan-out branch-point ancestry — lineage/render-only, NOT LoE-aggregated (DR-015) | **no** | yes | spinoffs carrying branch-point ancestry (PM-directed only) |
| `coordinates_with:` | peer ↔ peer | "this handoff/memo operates in coordination with that sibling" (no continuity) | no | no | project-rag handoffs; cross-repo memos |
| `consumed_by:` | this → claiming-session | "this handoff has been picked up by session UUID X" (populated at `/pickup`) | no | no | every handoff, populated at pickup time |
| `origin_*` (`origin_session`, `origin_handoff`, `origin_plan_id`, `origin_goal_id[]`) | originating-session → this | originating-session provenance axis — "what session/handoff/plan/goal spawned this fork" (nullable; backfill=null; no retroactive churn). `origin_handoff` is the sole handoff-DAG edge (separate `EDGE_KIND_META` namespace, never in default `edgeKinds`); `origin_session`/`origin_plan_id`/`origin_goal_id` are cross-entity refs served by rag's `origin_edges` projection, NOT this walker. `origin_session`/`origin_handoff`/`origin_plan_id` are scalar; `origin_goal_id` is an array (multi-goal forks are real). cockpit renders origin-less records as root/orphan nodes. Distinct from `predecessor` (continuation), `forked_from` (branch-point), `deliverable_id` (LoE grouping), and `initiative` (FK). | **no** | no | spinoff forks (`kind: spinoff`, `spinoff-roadmap`, `spinoff-goal`, `spinoff-roadmap-creator`); null for pre-existing/non-fork handoffs |

`predecessor:`, `additional_predecessors:`, `forked_from:`, `coordinates_with:`, and `origin_*` are authored at handoff-write time and assert lineage/sibling-ness. `consumed_by:` is mutated at pickup time and asserts current claim state.

**Don't unify.** They answer different questions: "where did this come from?" (`predecessor`), "what other parents does this merge?" (`additional_predecessors`), "what thread did this fork from?" (`forked_from`), "what is this in conversation with?" (`coordinates_with`), "is this claimed right now?" (`consumed_by`), "what session/plan/goal spawned this fork?" (`origin_*`). A single field would either lose information or require sub-typing that defeats the point.

`origin_handoff` and `forked_from` both point at the spawning baton and usually carry the same value, but they are orthogonal axes (different kind-applicability, different archival-guard participation, different producer) — an enforced invariant (schema.js Rule C2-5) requires them equal WHEN BOTH ARE SET, while permitting `origin_handoff` alone on fork kinds where `forked_from` is illegal.

**`forked_from` vs `additional_predecessors` semantics (load-bearing distinction):**
- `forked_from` records branch-point ancestry for render and archival-guard traversal. The LoE aggregator does NOT follow it — a pure-fork spinoff's effort is isolated to its own thread (DR-015). To accumulate LoE across a fork, the rejoining handoff must name the fork-point via `additional_predecessors`.
- `additional_predecessors` participates in both LoE accumulation (forward walk) and archival-guard traversal (reverse-membership check).

**Archival guard TOCTOU window (documented limitation, git-recoverable):** The `handoff-has-live-children.sh` check and the subsequent `git mv` archival are two separate operations — a concurrent EM session may author a new handoff naming the candidate node as a parent in the window between check and move. This is low-frequency and fully git-recoverable (the archived node reappears via `git log`), but `flock` is unavailable on Git Bash (`docs/wiki/bash-on-windows-gotchas.md:185`), so a strict atomic lock is not achievable cross-platform. Mitigations: (a) fuse the check and move into a single bash call where possible (H9 single-bash-call fusion pattern — `docs/wiki/concurrent-em-hazards.md`); (b) the `cs_claim_handoff` mkdir-lock already protects the pickup gate.

**Querying lineage:** A full lineage graph requires all six fields above, plus `authoring_session:` (spinoff origin prose), `shipped_in:` (terminal SHA/PR), and `archived_handoff:` (extraction backlink in DRs/wikis). For durable transitive `origin_*` queries ("everything spawned under goal/plan/session X"), use rag's `origin_subtree` endpoint over its `origin_edges` CQRS projection — the flat frontmatter fields fan into that read model at ingest.

Source: 2026-06 batch-3 lineage-mechanism inventory; extended 2026-06-29 (DR-015, fan-in/fan-out edges); extended 2026-07-07 (origin_* originating-session provenance axis, plan pln-structured-originating-session-8b505c).

## Handoff-scope language hazard

Handoff body phrasings of the form *"Out of scope for next session: Do NOT extend the plan, add new probes, or refactor adjacent install code. The single goal is X."* are well-meant scope-narrowing, but they routinely backfire at pickup.

The hazard: the picking session reads the negative list and treats every item on it as **proven-unnecessary** rather than **deferred-by-author**. When the pickup encounters substrate that legitimately needs the deferred work (e.g., an "adjacent install code" path that turns out to be the actual root-cause locus), the handoff text actively suppresses the right response.

**Better shape:** name the **positive** scope ("The single goal is X — land the fix at file:line"), and leave OOS implicit. If specific work must be deferred, frame it as *"deferred to follow-up handoff Y because Z"* — a named follow-up handoff, not a prohibition. A prohibition without a follow-up baton is appetite-hedged scope (see coordinator CLAUDE.md § Implementation Standards — OOS framing must be architectural).

**Pickup-side mitigation:** if a handoff carries negative-list OOS framing, treat it as authoring-time hypothesis, not ground truth. The premise-check section (§ Pickup-side premise check) applies to OOS framing too — verify the deferred items truly are deferrable before treating them as off-limits.

Source: 2026-06 batch-3 dogfood-loop-structure observations.

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

*Source: example-game-repo 2026-06-15 (UE+MCP peer-comparison S4 gap-audit spinoff fragmentation).* [universal]

## Install Seed Loop — Only-If-Absent, Never Clobber Consumed Batons

A seed/scaffold loop that copies install batons into `state/handoffs/` MUST be **only-if-absent**: before copying, check the destination file's frontmatter `status:` and skip any baton whose status is `consumed` or `superseded`.

**Why.** Running `setup.sh` (the Phase 0e seed loop over `templates/handoffs/*.md`) unconditionally overwrites destination files. A baton already at `status: consumed` gets reset to `status: active` / `ready_to_fire`, losing its `consumed_by:` and `consumed_at:` fields. Effect: a finished install leg resurfaces as live work at the next `/pickup` or `/workday-start`. The template comment may claim "the seed is AUGMENT, not replace," but an unconditional `cp` replaces unconditionally.

**Empirical origin (2026-06-17/18, ue-addon install dogfood).** Running `setup.sh` overwrote `install-project-rag-ue-addon.md` and `install-project-rag.md` — both already `status: consumed` — back to `status: active` / `ready_to_fire`, dropping `consumed_by:`. It recurred overnight (re-dated `created: 2026-06-18`) after a `git checkout HEAD` restore. Both finished install legs resurfaced as live work in `/pickup` and `/workday-start`.

**Rule.** A seed loop must guard each copy with a status check:

```bash
dest="$HANDOFF_DIR/$baton"
if [ -f "$dest" ]; then
    status=$(grep -m1 '^status:' "$dest" | awk '{print $2}')
    if [[ "$status" == "consumed" || "$status" == "superseded" ]]; then
        continue   # skip — baton already closed
        # Note: "superseded" is a retired-but-tolerated-for-legacy handoff status (2026-06-26).
        # Keep the skip condition here for legacy/external records; never write "superseded" on new handoffs.
    fi
fi
cp "$src" "$dest"
```

The guard is idempotent: a not-yet-seeded baton passes through normally; a re-seeded baton whose destination file exists with a terminal status is skipped. The `authoring_session:` and `created:` fields in the source template do NOT override the lifecycle state of an already-consumed destination baton — the destination's frontmatter is the authority, not the template's.

*Pairs with § Frontmatter format drift (`created:` normalization) and the `consumed_by:` claim-gate (§ Concurrent-pickup interaction) — both depend on frontmatter staying accurate after seeding.*

## See also

- `skills/pickup/SKILL.md` — premise check (Step 3.4e) and awaiting_gate aging (Step 3.4d) consumers.
- `skills/roadmap-planning/SKILL.md` — wave/sprint distinction, soft-seams body section, and Phase 2 exit gate consumers.
- `skills/spinoff/SKILL.md` (if present) — initial-state authoring for `kind: spinoff`.
- Coordinator CLAUDE.md § Handoff Lineage — deployment_state enum, predecessor rules (canonical tripwire form).
