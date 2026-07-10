---
title: Plan/Execute Session Split — Execution Defaults to a Fresh Handoff
created: 2026-07-09
type: doctrine
related:
  - plugins/coordinator/docs/wiki/workflow-orchestration.md
  - plugins/coordinator/skills/handoff/SKILL.md
  - plugins/coordinator/skills/execute-plan/SKILL.md
  - plugins/coordinator/skills/review/SKILL.md
  - plugins/coordinator/docs/wiki/review-integration-doctrine.md
---

<!--
Purpose: Canonical doctrine for the plan→execute session boundary. Names the reversal (default
same-session execution → default fresh-session execution via handoff), the empirical driver
(context-saturation tool-call instability, first captured here 2026-07-09), the pinned mechanism
(execution handoff + plan-frontmatter authorization stamp), the two sanctioned exceptions
(/autonomous, token-economics carve-out), and the anti-deferral reconciliation that keeps this
narrow rather than a general handoff-at-any-tidy-point license.
Negative-spec: NOT a rewrite of handoff/execute-plan/review mechanics (those skills own their own
procedures and cite this doctrine); NOT a license to hand off at any convenient stopping point —
the trigger is the `execution_authorized_at` stamp, not "felt like a good pause"; NOT the same
observation as workflow-orchestration.md's mid-execution compaction risk (see § Relationship to
workflow-orchestration.md below); NOT a bare-date stamp — `execution_authorized_sha` binds the
stamp to plan CONTENT and must be re-verified by every consumer, not just checked for presence.
Domain vocab: execution handoff, execution_authorized_by, execution_authorized_at,
execution_authorized_sha, execution_authorized_note, Plan to Execute, context saturation,
token-economics carve-out, plan-frontmatter authorization stamp, content-binding, write-bar.
-->

# Plan/Execute Session Split — Execution Defaults to a Fresh Handoff

## The rule

Planning through review-approval and review-integration stays in one session — that part of the
pipeline does not change. What changes is the tail: **after review-integration completes, the
default is no longer same-session `/execute-plan`.** Instead:

1. The EM asks the PM to approve execution.
2. On approval, the EM stamps the plan's YAML frontmatter with the authorization of record:
   ```yaml
   execution_authorized_by: PM
   execution_authorized_at: <YYYY-MM-DD>
   execution_authorized_sha: <hash>
   execution_authorized_note: "<verbatim PM utterance>"
   ```
   `execution_authorized_sha` binds the stamp to the plan's CONTENT at approval time, not merely a
   date (see § Content-binding below for the failure mode this closes and the exact recipe).
   `execution_authorized_note` is the self-attesting field — see § Write-bar below.
3. The EM writes an **execution handoff** — a `kind: session-handoff` handoff (no new `kind:`
   value, no new frontmatter enum) whose next action is `/execute-plan <plan-path>`, carrying
   `deployment_state: ready_to_fire` and a `## Plan to Execute` body section (see § Pinned
   conventions below).
4. The EM stops. A **fresh session** picks up the handoff and runs `/execute-plan`.

This reverses the prior default, in which after a plan cleared review the EM only paused to ask
the PM before invoking `/execute-plan` in the same conversation — a "yes" meant same-session
execution by default. That is now the exception, not the rule (§ Default vs. exceptions below).

## The empirical rationale

**This is the first capture of this observation in the repo — there is no prior doctrine stating
this failure mode.** Executing a plan in a session already saturated with the full planning +
review + doctrine context degrades model reliability: tool-call channel leaks and instability were
observed on 2026-07-09 in exactly this shape — a single session carrying plan authorship, review
dialogue, and integration all the way through into execution. The failure surfaces as corrupted or
dropped tool-call framing, not as an obviously-wrong answer, which makes it dangerous: a saturated
session doesn't announce degraded reliability, it just starts losing tool calls.

The fix is not "be more careful" — it's giving execution a context budget that hasn't already been
spent on the plan/review dialogue. A fresh session that picks up the handoff reads the plan and the
authorization stamp fresh, with a full context budget dedicated to execution alone. This is why the
fresh session is framed as the **superior** next action for execution, not a courtesy pause before
it — the empirical driver is a reliability argument, not a process nicety.

### Confidence and review trigger

**Honest confidence note:** the empirical driver above is a SINGLE observation — one session, one
day (2026-07-09), no reproducer, no frequency estimate. This doctrine reverses a repo-wide default
governing every plan execution on the strength of that one observation. The reversal is adopted on
a cheap-and-reversible basis: the mechanism (a handoff + a stamp) costs little to run and little to
undo, which is the right posture for acting on a strong-but-unproven signal — but n=1 is n=1, and
this note exists so it does not calcify into settled law without ever being re-examined.

**Falsification trigger:** re-evaluate this default if either holds — (a) fresh-session executions
picked up via the execution handoff exhibit comparable tool-call instability to what same-session
execution showed (i.e. the fix doesn't fix it), or (b) the saturation→instability link fails to
reproduce across a reasonable number of same-session execution-handoff cycles under instrumented
saturation (i.e. the failure mode this doctrine exists to prevent turns out not to recur). Either
result should trigger a revisit of the default, not a quiet dismissal of the trigger.

### Relationship to `workflow-orchestration.md`

`workflow-orchestration.md` is adjacent prior art on the general theme "EM context is the
instability risk," but it names a **different** failure and a **different** fix. That doctrine
addresses **mid-execution compaction**: an EM hand-orchestrating a multi-wave plan burns its own
context holding the wave-map, and compaction mid-run loses that state — the fix is a background
Workflow that keeps the orchestration out of the EM's context entirely. This doctrine addresses
**pre-execution saturation**: a session that is still context-fresh at the point `/execute-plan`
would start, but has already spent its budget on planning and review dialogue before execution
even begins — the fix is a session boundary, not an orchestration primitive. A plan can (and
routinely will) need both: a fresh execution-handoff session at the front, *and* a background
Workflow once that fresh session starts orchestrating multi-wave execution.

## Pinned conventions

These exact strings and shapes are the contract. Every surface that implements this doctrine
(review, handoff, execute-plan, pickup, autonomous, writing-plans) uses them byte-identical — do
not paraphrase.

- **Mechanism name: "execution handoff"** — a `kind: session-handoff` handoff whose next action is
  `/execute-plan <plan-path>`. No new `kind:` value, no new frontmatter enum is introduced by this
  doctrine. It carries `deployment_state: ready_to_fire` like any other pickup-ready continuation
  handoff.
- **Plan-frontmatter authorization stamp** — set in the plan document's YAML frontmatter
  (`docs/plans/*.md`):
  ```yaml
  execution_authorized_by: PM
  execution_authorized_at: <YYYY-MM-DD>
  execution_authorized_sha: <hash>
  execution_authorized_note: "<verbatim PM utterance>"
  ```
  The presence of `execution_authorized_at` with a date **is** the authorization of record. It
  replaces the old, weaker definition — "the PM said 'execute' somewhere in this chat" — with a
  disk-persisted fact a fresh session with zero chat history can read and verify. It is set by the
  reviewing session at the `coordinator:review` Exit gate, and only after the PM has approved
  execution — never speculatively, never before approval.

  **Write-bar (when the stamp may be written).** The stamp is written ONLY when the PM's message
  NAMES execution — "execute", "proceed to execute", "run it", "go ahead and execute".
  Plan-approval words ("looks good", "lgtm", "approved", "nice") authorize the PLAN, NOT its
  execution, and MUST NOT trigger the stamp. If in doubt, the stamp is not yet warranted.
  <!-- Review: code-reviewer — read for execution-naming INTENT, not keyword presence; e.g. "ship
       it" is colloquially ambiguous (can mean merge/ship a diff, not execute a plan) and was
       dropped from the keyword list for that reason. -->
  Read for execution-naming INTENT, not keyword presence — a phrase like "ship it" is
  colloquially ambiguous (it can mean merge/ship a diff rather than execute a plan) and should be
  judged in context, not pattern-matched.

  **`execution_authorized_note` — self-attesting.** Captures the PM's actual authorizing
  utterance verbatim (or a close paraphrase if the utterance is long), so a fresh session and any
  auditor can see exactly what was authorized rather than trusting that the stamp-writing session
  read the PM correctly. A stamp without a note that names execution is a signal the write-bar may
  not have been met.

  **`execution_authorized_sha` — content-binding.** A bare date stamp survives a post-approval
  amendment: PM approves → EM stamps → EM edits the plan body (adds a phase, changes a file
  target, alters scope) → a fresh session picks up the handoff, sees a valid stamp, and executes a
  plan the PM never approved in its amended form. `execution_authorized_sha` closes this hole by
  binding the stamp to the plan's executable BODY content, not just a timestamp.

  **Canonical hashing recipe** (byte-identical everywhere — every consumer cites this exact
  command, never re-derives it):
  ```
  awk '/^---[[:space:]]*$/{fm++; next} fm>=2{print}' <plan-path> | git hash-object --stdin
  ```
  This hashes the plan BODY — everything below the YAML frontmatter delimiters — so writing or
  reading the stamp fields in frontmatter never invalidates the hash; only a material change to
  the executable body does.
  <!-- Review: code-reviewer — recipe assumes LF line endings; a CRLF frontmatter delimiter line
       is not guaranteed to match `[[:space:]]*$` on every awk implementation and could fold the
       frontmatter into the body hash. -->
  This recipe assumes LF line endings — plan files must not be CRLF, since a CRLF frontmatter
  delimiter could fail to match and fold the frontmatter into the body hash.

  **Set:** at the `coordinator:review` Exit gate, when the stamp is written — after the plan body
  is final, computed against the approved body text.

  **Re-verified:** at BOTH `execute-plan` Phase 1 (the "Confirm authorization" step) AND `pickup`
  Step 3.4e — the consuming session recomputes the recipe against the plan file as it currently
  stands and compares the result to `execution_authorized_sha`.

  **Stale → surface to PM, do NOT execute.** If the recomputed hash differs from
  `execution_authorized_sha`, the plan body was materially amended after approval. This is a
  premise failure like any other unstamped-plan case: stop, surface the mismatch to the PM, and do
  not proceed to `/execute-plan` on the stale stamp.
- **Execution-handoff body section** — every execution handoff's body includes a `## Plan to
  Execute` section containing (a) the plan path, and (b) a line citing the plan's
  `execution_authorized_at` stamp (and, per the content-binding above, its
  `execution_authorized_sha`) as the premise the picking-up session must verify. That verification
  happens at `/pickup` Step 3.4e — the picking-up session confirms the stamp is present AND its
  `execution_authorized_sha` still matches the current plan body before invoking `/execute-plan`,
  rather than trusting the handoff prose alone.
- **Canonical doctrine home** — this file,
  `coordinator/docs/wiki/plan-execute-session-split.md`. Every other surface that touches this
  boundary (review, handoff, execute-plan, pickup, autonomous, writing-plans, and the CLAUDE.md
  layer) cross-references it by this exact path rather than re-deriving the rule locally.

## Default vs. exceptions

- **DEFAULT (interactive sessions).** Review-integration completes → the EM asks the PM to
  approve execution → on approval (only once the PM's message names execution — see the
  write-bar above), the EM (1) stamps the plan frontmatter `execution_authorized_by` /
  `execution_authorized_at` / `execution_authorized_sha` / `execution_authorized_note`, (2) writes
  an execution handoff via `/handoff`, (3) stops. A fresh session picks it up (`/pickup`) and runs
  `/execute-plan`, re-verifying `execution_authorized_sha` before proceeding.

- **EXCEPTION 1 — `/autonomous` mode.** No PM-ask, no handoff; execution continues same-session
  straight into `/execute-plan`. Autonomous mode already bypasses the review checkpoint (it isn't
  waiting on a PM approval to stamp) and exists specifically to run continuously through
  compaction rather than stop at session boundaries — the default-handoff behavior does not apply
  to it at all. **The stamp is intentionally ABSENT under `/autonomous`** — the review checkpoint
  was bypassed upstream, so there is nothing to stamp. The stamp is the authorization-of-record
  for the DEFAULT (handoff) path only; under `/autonomous` the sentinel
  (`/tmp/autonomous-run-${SESSION_ID}`) is the authorization. A future auditor or fresh session
  reading stamp-absence together with the autonomous sentinel must treat the run as
  authorized-by-autonomous, NOT as an unauthorized execution.

- **EXCEPTION 2 — token-economics carve-out.** Same-session execution is permitted, narrowly, only
  when ALL of the following countable conditions hold — "feels fine" / unmeasured judgment is
  explicitly disallowed, and if any of (a)-(c) fails, the default (handoff) applies:
  - (a) NO auto-compaction has occurred in this session yet, AND
  - (b) the plan's task-spine is ≤ 3 tasks (single-phase plans qualify), AND
  - (c) the EM logs the carve-out to the flight recorder with the measured plan-size and
    compaction-count.

  This is a rare carve-out, not a default-in-disguise — the bound exists because the actor judging
  "not saturated" is the same actor the empirical driver (§ The empirical rationale) says cannot
  reliably self-report saturation; a countable, externally-checkable bound closes that gap where
  self-assessment cannot. When this exception is taken, the EM still names it as a deliberate,
  justified choice, citing which of (a)-(c) it verified, rather than silently skipping the handoff
  step.

  **Enforcement — the session-freshness gate.** This carve-out is not merely documented, it is
  ENFORCED at `/execute-plan` Phase 1's session-freshness gate (`skills/execute-plan/SKILL.md`
  Phase 1 step 3), which runs after the "Confirm authorization" step and before any executor
  dispatch. The gate is the mechanical checkpoint that makes (a)-(c) above a checked artifact
  rather than an EM-self-graded honor system.

  **Fresh-vs-same-session discriminator.** The gate answers ONE factual question the EM can
  answer without introspecting context saturation: *did THIS session author/review this plan
  (same-session invocation), or did it pick the plan up fresh (fresh execution session — e.g.
  via `/pickup` of an execution handoff)?* This discriminator is the load-bearing fact that scopes
  the ≤3-task bound (condition (b) above) to the same-session carve-out ONLY — a fresh session
  executes plans of ANY size; the ≤3-task bound never applies to it. Conflating "fresh session"
  with "same session" and applying the ≤3-task bound universally would break the default path
  this doctrine exists to establish (§ The rule above).

## Anti-deferral reconciliation

`/handoff`'s anti-deferral core — "don't hand off when you could take the next action now" — stays
intact everywhere except this one boundary. It is tempting to read the plan→execute handoff as
exactly the tidy-pause deferral that rule forbids. It is not, for a specific, named reason: at this
boundary, the fresh session genuinely **is** the correct next action, because the empirical driver
above is about reliability degradation from context saturation, not about convenience or momentum.
Handing off here isn't punting work to "later" — it's routing the work to a session that can
actually execute it reliably.

This distinction is narrow on purpose. The plan→execute handoff is a **specific,
empirically-justified first-class trigger**, gated on the `execution_authorized_at` stamp existing
— it is not a general license to hand off at any tidy stopping point. An un-stamped "the plan
looks approved, this feels like a natural pause" moment is still exactly the deferral the NO-test
forbids: STOP-and-dispatch (or continue), not hand off. The stamp is the discriminator between the
sanctioned trigger and the general anti-deferral rule that still governs everywhere else.

## What does NOT change

- **Review-integration stays in-session.** The reversal only touches the boundary *after*
  review-integration completes — plan authorship, review dialogue, and integration remain one
  continuous session exactly as before.
- **`/spinoff` is still the wrong primitive here.** The execution handoff is a *continuation* of
  the same workstream's next phase (plan → execute), not a fork to a different workstream.
  `/spinoff` produces `kind: spinoff`, `predecessor: none` handoffs for genuinely different work;
  the plan→execute boundary is a `/handoff`-authored continuation, full stop.
- **`/autonomous` and the token-economics carve-out are the only exceptions.** Every other
  same-session execution shape is now non-default and needs the deliberate carve-out framing
  above, not silent inertia.
