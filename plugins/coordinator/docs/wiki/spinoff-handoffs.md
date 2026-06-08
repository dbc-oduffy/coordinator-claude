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

Source: `archive/specs/2026-05-07-handoff-no-successor-gate.md` (status: complete, 2026-05-07).

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

When an operator installs coordinator as the root of a multi-repo setup, each *additional* repo they want (deep-research, or downstream repos) is materialized as a **spinoff** by that repo's installer — not by an EM typing `/spinoff`. The baton is a normal `kind: spinoff` file in the standard `~/.claude/state/handoffs/` folder (the same place `/spinoff` writes), distinguished from the coordinator onboarding handoff by an `install_chain_order:` tag, and carrying `authoring_session:` naming the install + the operator's opt-in (the audit-trail field this schema requires of every spinoff). It is seeded via `cp`/`sed`, not the Write tool, so it does not trip the unauthorized-handoff nudge. This is legitimate because **the authorization is captured at the install's pre-restart question** ("what else do you want to install?"). The operator selecting a leg there *is* the human authorizing that fork — the same authorization `/spinoff` captures, captured at a different but equally explicit moment.

The gate is not eroded:

- **A human still authorizes every leg.** A spinoff never appears unless the operator chose it at the pre-restart question. The installer materializes a choice the human already made; it does not invent a fork. The EM driving the install is not self-initiating spinoffs — it is stitching operator-authorized ones.
- **Scope is narrow.** This applies only to install-time leg-seeding, where the human's selection is the gate. It does not license script- or EM-created spinoffs in any steady-state workstream — there, the `Candidate spinoff: … Authorize?` block still holds.
- **`predecessor: none` is native.** These legs are genuine forks of different install topics, not continuations of coordinator onboarding (which is the handoff). The spinoff frame fits without a lineage exception.

Mechanics and the seed/drive role split live in `agent-install-contract.md` § Install-spinoff layer; the install-chain spine that tracks the legs is `coordinator/templates/plans/install-chain-tracking.md`.

## Frontmatter schema

```yaml
kind: spinoff
status: active
predecessor: none           # always — spinoffs have no continuity ancestor
authoring_session: <one-line description>   # replaces predecessor link as audit trail back to origin
workstream: <slug>          # required, so /pickup can group them
```

`predecessor: none` is load-bearing. The "Single Predecessor, No Adjacency-Inference" rule (in coordinator/CLAUDE.md) requires every handoff to have a single named predecessor or `none`. Spinoffs are always `none`; the audit trail back to origin lives in `authoring_session`.

### `supersedes:` on a live baton — optional field, distinct from `status: superseded`

`supersedes:` is an **optional** field on a `kind: spinoff` baton used by the orientation-supersession convention (see `docs/wiki/agent-install-contract.md` § Orientation-supersession). It asserts a spine-build-time preference — "when building the orientation spine, prefer this baton over the one it names." It is **not** a lifecycle terminator and does not mark any baton as dead.

This is **distinct** from the `status: superseded` lifecycle state, which is terminal: a baton with `status: superseded` is dead and will not be picked up. The `supersedes:` field on a *live* baton does none of that.

Canonical contrast (verbatim, also in `docs/wiki/cross-repo-communication.md` § Grandfather cutoff note):

> "`supersedes:` on a memo = terminal (paired with `superseded_by:` + `status: superseded`, wired in the `CROSS_FIELD_RULES` memo block); `supersedes:` on a live baton = conditional+live, a spine-build-time preference (never flips status, no back-pointer, wired in the `CROSS_FIELD_RULES` handoff block)."

Cross-reference: `docs/wiki/cross-repo-communication.md` § Grandfather cutoff carries the matching note disambiguating the memo-side `supersedes:` meaning from this baton-side meaning.

## Pickup-side and workday-start handling

- **`/pickup` with `kind: spinoff`** prepends a one-line banner: *"This is a spinoff workstream — predecessor is none; treat the handoff body as ground-truth spec and proceed."*
- **`/workday-start`** lists spinoffs separately from active handoffs in the orientation cache.
- **Stale spinoff nudge:** a spinoff that hasn't been picked up after N days (default 14) gets a heads-up nudge in `/workday-start`.

## Why this exists as a formal pattern

Three pre-formalization signals motivated it (see [DR-013](#dr-013)):

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

**Status:** accepted
**Decision:** Spinoffs never carry a predecessor link — they are forks, not continuations. The `authoring_session` field carries the audit trail back to origin.
**Consequences:** `/pickup` banner can be deterministic; lineage rules treat spinoffs as roots.

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

`kind: spinoff` and `kind: spinoff-roadmap` have `predecessor: none` by design. A missing continuity ancestor is NOT a premise failure for these kinds — it is the correct structural shape. Verify the `authoring_session:` audit trail instead (confirms the spinoff origin context is still readable, not that a predecessor existed).

### When to surface to PM

- Premise drift on a load-bearing claim → surface before mutation; do not proceed silently.
- Routine path-rename with clear mapping → fix forward and note in pickup report.
- Scope pathspec returns empty glob → STOP, surface to PM; do not mutate.

### Verify semantic fit of handoff-named target files before writing

When a handoff names a target file (e.g., "extend `docs/wiki/X.md`"), `Read` that file and confirm the topic and section actually fit before writing. Stale handoff-named targets accumulate when the wiki has been refactored between handoff-author time and pickup time — the file may still exist but now cover a different scope, or the relevant section may have moved to a sibling file. Source: 2026-05-15 project-rag-ue-addon pickup.

### Parked-tracker rows: framing is hypothesis, substrate is ground truth

When resuming work that names "parked" tracker rows, project-board items, or backlog entries with framing like "Y is blocked on X" or "this is parked pending Z", verify the substrate before accepting the parking framing. Stale advisory/call-note markdowns and project-tracker rows accumulate over weeks; the parking premise may have been overtaken (the blocker shipped, the scope was rolled in elsewhere, the row references files that have moved). Run a git-log spot-check on the cited paths before treating the parked state as live work. Source: 2026-05-16 claude-unreal-holodeck resume.

### Empirical baseline

Expect 30–60% of inherited items to be already closed (pickup SKILL Step 3 empirical note). Premise decay compounds on top of this: a 24h-old handoff may have 1–2 stale file assertions; a 7d-old handoff routinely has more. Treat unverified premises as blocking gaps, not deferrals.

## Deployment_state lifecycle for spinoffs

> Cross-reference: coordinator CLAUDE.md § Handoff Lineage (deployment_state enum).

### Initial state at authoring

- `/spinoff` sets `deployment_state: ready_to_fire` for stubs intended for immediate pickup.
- `roadmap-planning` sets `deployment_state: awaiting_gate` for stubs with `gate_dependency:` (sequenced stubs that must not be picked up until a predecessor ships).

### Lifecycle table

> Column states refer to `deployment_state:` frontmatter, NOT `status:`. The `status:` enum is `active | consumed | superseded` (per coordinator CLAUDE.md § Handoff Lineage); `shipped` is not a valid `status:` value — use `consumed` + `shipped_in:` instead.

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

## Crash-recovery handoffs are one-per-workstream

`kind: recovery` handoffs are scoped by **incident**, not by size of the recovered work. When a session crashes or is killed mid-flight, write one recovery handoff per surviving workstream — regardless of whether the recovered slice is "trivial" or "big." Judging "this is too small for a handoff" silently overrides the directive that recovery handoffs exist to make crash-loss boundaries discoverable; the cost of an extra small handoff is a few minutes, the cost of a missed one is the successor session re-discovering the crash boundary by stepping on it.

Commit-granularity is incident-scoped, not workstream-scoped: if two concurrent workstreams both crashed, that's two recovery handoffs (separate `predecessor:` pointers to each crashed handoff's SHA), not one merged "we crashed" handoff. Each successor picking up either workstream needs its own framing of what was in flight, what got committed pre-crash, and what didn't.

## query-records handoff-archived type

`bin/query-records` supports a `handoff-archived` type (distinct from `handoff`) that maps to `archive/handoffs/*.md`. Same schema applies, or relaxed-schema sibling `schemas/handoff-archived.yaml` where `deployment_state:` is not required. Use `--older-than Nd` (inverse of `--since Nd`) to enumerate archived handoffs older than N days. Note: `--where "created<14d"` uses non-ISO comparand and returns garbage — use `--older-than 14d` instead. Used by `/distill` for archive enumeration.

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

The roadmap-planning skill writes `pm-gates.md` listing each product-coupled question, the sprint it gates, and the disposition format. Schema: `| sprint | tc_id | gate question | disposition format | resolved? |`

Validator rule: any stub with `gate_dependency:` text that starts "PM " OR contains "decision needed" / "approval needed" / "policy" / "scope" / "user-facing" MUST have a corresponding row in `pm-gates.md`. A gated stub with no matching pm-gates row blocks Phase 3 entry.

## See also

- `skills/pickup/SKILL.md` — premise check (Step 3.4e) and awaiting_gate aging (Step 3.4d) consumers.
- `skills/roadmap-planning/SKILL.md` — wave/sprint distinction, soft-seams body section, and Phase 2 exit gate consumers.
- `skills/spinoff/SKILL.md` (if present) — initial-state authoring for `kind: spinoff`.
- Coordinator CLAUDE.md § Handoff Lineage — deployment_state enum, predecessor rules (canonical tripwire form).
