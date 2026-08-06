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
(context-saturation tool-call instability, first captured here), the pinned mechanism
(execution handoff + plan-frontmatter authorization stamp), the three sanctioned exceptions
(/autonomous, token-economics carve-out, `/mise` invocation), and the anti-deferral reconciliation
that keeps this narrow rather than a general handoff-at-any-tidy-point license.
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
day, no reproducer, no frequency estimate. This doctrine reverses a repo-wide default
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
  NAMES execution — "execute", "proceed to execute", "run it", "go ahead and execute", or an
  unambiguous captain's-order "go" idiom ("make it so", "engage", "hit it", "let's fly").
  Plan-approval words ("looks good", "lgtm", "approved", "nice") authorize the PLAN, NOT its
  execution, and MUST NOT trigger the stamp. If in doubt, the stamp is not yet warranted.
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
  This recipe assumes LF line endings — plan files must not be CRLF, since a CRLF frontmatter
  delimiter could fail to match and fold the frontmatter into the body hash.

  **Set:** at the `coordinator:review` Exit gate, when the stamp is written — after the plan body
  is final, computed against the approved body text.

  **Ordering — the stamp is the LAST write of the approval commit.** The approval step naturally
  does body bookkeeping alongside the stamp: on a LEGACY plan (no `grouping_approvals`
  frontmatter block), ratifying deferred task rows via the read-tolerated per-row
  `pm_approved: true` bool — a `plan-tasks` body-fence edit; either way, also updating the
  plan-header `Status:` line and folding a final integration note. Every one of those is a BODY
  edit and therefore invalidates a hash computed before them. On a GOVERNED plan, by contrast,
  landing a grouping's `status: approved`/`pm_utterance`/`digest` fields for whichever of
  `do`/`defer`/`ruled_out` the approval covers is a **frontmatter** edit and does NOT invalidate
  the hash — the recipe excludes frontmatter by construction (see above). Therefore: land ALL
  plan-body edits the approval entails FIRST, then compute the recipe, then write the frontmatter
  stamp fields (which, on a governed plan, now includes the grouping-approval fields alongside
  `execution_authorized_sha`/`_note`). The stamp write must be the last body-affecting operation
  of the approval commit — and since the recipe excludes frontmatter, writing the stamp itself is
  safe by construction. A hash computed before the same-commit body edits describes a body state
  that ceased to exist the instant it was recorded — the gate is then stale at birth, and every
  downstream reader gets a STALE verdict that means nothing. If a body edit is unavoidable AFTER
  the stamp lands (a `Status:` line pointing at an execution baton that does not exist until the
  handoff is written), re-stamp in that same follow-up commit rather than leaving the binding
  stale — carry the reason in `execution_authorized_note`. This is exactly the ordering bug a
  grouping's membership digest is built to make detectable on a GOVERNED plan: the digest covers
  the sorted (row id, disposition) set for that grouping, so flipping a row's disposition after
  computing it changes the set the digest describes, and a subsequent recompute-and-compare
  surfaces the mismatch rather than silently trusting a stale approval.

  **Re-verified:** at BOTH `execute-plan` Phase 1 (the "Confirm authorization" step) AND `pickup`
  Step 3.4e — the consuming session recomputes the recipe against the plan file as it currently
  stands and compares the result to `execution_authorized_sha`.

  **Stale → triage the delta, then re-stamp or halt. Never wave through, never halt reflexively.**
  A STALE verdict does not by itself mean the PM's approval was invalidated — it means the body
  changed; whether that change matters is a separate question the reader must answer, not skip.

  1. Diff the plan body across the stamp commit to see what actually changed:
     `git log --oneline -S"execution_authorized_sha: <stamped-hash>" -- <plan-path>` to find the
     stamp commit, then `git diff <stamp-commit>..HEAD -- <plan-path>`.
  2. Classify the delta. **Authorization bookkeeping** — a `grouping_approvals` block landing on a
     GOVERNED plan (or, on a LEGACY plan, the read-tolerated per-row `pm_approved:` flip), the
     plan-header `Status:` line, review-integration notes, typo/formatting — is not a change to
     what the PM approved. **Substantive** — a new chunk or task-spine row, a changed file target,
     altered scope or acceptance criteria, a reversed decision, or a row moving between groupings
     without the corresponding grouping's `digest` being recomputed — is.
  3. Bookkeeping-only → re-stamp to the current body and record why in
     `execution_authorized_note`, via the re-stamp CLI's `--append-note <text>` flag — do not
     overwrite the PM's verbatim utterance. `--append-note` appends `<text>` onto whatever the field
     already holds (onto an absent or empty note it behaves as a plain set — no leading separator);
     `--note` is the sibling flag and still REPLACES the field wholesale, which is correct for the
     FIRST stamp at the review Exit gate (nothing to preserve yet) and wrong on a re-stamp, where it
     would destroy the PM's verbatim authorizing words. The two are mutually exclusive — passing both
     is a usage error. The separator between the existing note and the appended text is a literal
     two-character `\n` (the characters backslash-n, not an actual newline byte) — deliberate, since
     a real line break would break the single-line-per-field frontmatter primitives this tree uses.
     Re-running an identical `--append-note` is a genuine no-op: the convergence check asks whether
     the existing note already *ends with* the given text, not whether it equals it, so a repeated
     re-stamp cannot grow the field without bound. (Rewriting the note is safe under either flag, and
     so is repairing one by hand: `execution_authorized_note` is frontmatter, which sits outside the
     body hash the stamp binds to per the canonical hashing recipe above, so editing it does not
     re-stale the stamp.)
     Then proceed. This leaves a real binding for the next reader instead of a known-broken one.
  4. Substantive → surface the specific delta to the PM and STOP. Do not execute on a body the PM
     did not approve. This is the case the gate exists for.
  5. Cannot classify confidently → treat as substantive and surface. The asymmetry is deliberate: a
     needless PM ask is cheap, executing an unapproved amendment is not.

  This triage is doctrine, not EM improvisation, for a mechanism-level reason: a gate that reports
  STALE routinely gets waved through routinely, so the failure mode is desensitisation, not
  obstruction — the triage exists to keep a STALE verdict meaningful.

  **Post-execution body amendment — a third case, distinct from bookkeeping/substantive above.**
  The bookkeeping/substantive ladder above is a **PRE-execution** remedy: it assumes execution
  hasn't happened yet, so re-stamping (bookkeeping) or halting-to-ask (substantive) both still make
  sense as next actions. A plan already `status: implemented` that later needs its body corrected
  (a post-hoc doc fix, a correction discovered after execution) has no "before proceeding" left to
  gate — proceeding already happened. Re-stamping such a plan would falsely assert the PM
  authorized the corrected text, when they only ever saw the pre-amendment body. The convention:
  record the amendment explicitly instead of re-stamping —
  ```yaml
  body_amended_post_execution: true
  body_amendment_note: "<what changed, and why the stamp is deliberately not recomputed>"
  ```
  Deliberately do **not** re-stamp `execution_authorized_sha` in this case. A future re-verification
  (`execute-plan`/`pickup`, or any computed-skills pass that happens to touch an implemented plan)
  reporting this plan STALE against the pre-amendment sha is **expected and correct, not a defect**
  — the STALE verdict is telling the truth: the current body diverges from what was authorized, and
  the divergence is documented, not accidental. This case is orthogonal to the bookkeeping/
  substantive ladder above — don't fold a post-execution amendment into "bookkeeping → re-stamp"
  just because it superficially looks like tidy paperwork; the ladder's re-stamp path is a
  pre-execution remedy and doesn't apply once execution has already occurred.
- **Execution-handoff body section** — every execution handoff's body includes a `## Plan to
  Execute` section containing (a) the plan path, and (b) a line citing the plan's
  `execution_authorized_at` stamp (and, per the content-binding above, its
  `execution_authorized_sha`) as the premise the picking-up session must verify. That verification
  happens at `/pickup` Step 1 (Classify, Load, and Reconcile Against Reality) — the picking-up session confirms the stamp is present AND its
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
  (`/tmp/autonomous-run-${SESSION_ID}`) is the authorization — but the sentinel path is now shared
  with EXCEPTION 3 below, both writing the same path with different content.
  A future auditor or fresh session reading stamp-absence together with the sentinel must read the
  sentinel's CONTENT, not merely its presence: only content `autonomous` supports treating the run
  as authorized-by-autonomous; content `mise-en-place` means EXCEPTION 3 applies instead. Bare
  presence is no longer sufficient to conclude "authorized-by-autonomous" — see EXCEPTION 3 for the
  sibling case.

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

  **Background-Workflow vehicle breaks the ≤3-task bound (PM-directed).** The ≤3-task bound in
  condition (b) is a *proxy* for "the EM's context won't saturate during execution." That proxy
  assumes the executor's tool-output lands in the EM's window. A **background Workflow breaks that
  assumption**: executor tool-output stays out of the EM window entirely (the same property that
  makes a Workflow the default multi-wave vehicle — see `workflow-orchestration.md`), so the
  saturation the ≤3-task bound guards against no longer applies. Therefore, when the PM *explicitly*
  directs same-session execution of a plan larger than 3 tasks, honoring that direction by running
  it via a background Workflow is legitimate — the ≤3-task proxy is moot because the mechanism it
  proxies for is absent. The EM honors the PM direction AND notes the mitigation (Workflow vehicle)
  as the reason the freshness bound does not bite. This is not a general relaxation of condition (b)
  for interactive same-session execution — it is specific to the out-of-window Workflow vehicle
  under explicit PM direction.

- **EXCEPTION 3 — `/mise` invocation.** No PM-ask, no handoff, no stamp — parallel to EXCEPTION 1,
  content-sensitive on the shared sentinel. A sentinel whose content reads `mise-en-place` is the
  authorization-of-record for a `/mise` run (basis: `mise-en-place.md:10` — "PM authorization is
  implicit in invocation"). The run's `state/mise-inventory/<run-id>.md` record — which carries the
  run's authorization basis (which plans/items the PM named at invocation, and when), not merely
  the chunk table — is CORROBORATING DETAIL, not the sole trace; the sentinel content is the
  primary, machine-written authorization-of-record. Sentinel-content `mise-en-place` vs
  `autonomous` distinguishes the two authorization bases: an auditor who finds stamp-absence plus a
  sentinel must read the sentinel's CONTENT to know which basis applies, and must not treat
  sentinel-absence-under-mise as unauthorized either (the sentinel is Phase-5-to-Phase-6 scoped,
  not a permanent record — the inventory record above is the durable trace).

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
- **`/autonomous`, the token-economics carve-out, and `/mise` invocation are the only exceptions.** Every other
  same-session execution shape is now non-default and needs the deliberate carve-out framing
  above, not silent inertia.

## Key Patterns for Multi-Plan / Multi-Workstream Execution

### Parallel execution for multi-plan dispatch

When executing multiple plans concurrently, resolve real write-sets first, then partition into
disjoint tracks plus a serial tail for any collisions. Observed pattern: resolving write-sets
across several plans found exactly one collision (16 files) — the response was three disjoint
parallel tracks running concurrently, with the colliding work handled as a serial tail after the
parallel tracks landed. This mirrors the general fan-out discipline (disjoint scopes, serial
commit for anything that overlaps) applied at plan-execution granularity rather than
task-dispatch granularity.

### Spawn-parallelization once foundation lands

PM directive: once a foundational tier is in, independent workstreams on disjoint
scripts are cleared to run as 2-3 concurrent build waves rather than serially — e.g. once a T0
foundation tranche landed, several dependent tranches proceeded as concurrent tracks. The only
hard gate is file-write-overlap on the shared tree, not a general serialization requirement —
the same disjoint-scope discipline as the multi-plan pattern above, stated as a standing
directive rather than a one-off observation.

## Where This Doctrine Is Wired (implementation reference)

This doctrine touches eight surfaces (E1-E8), useful as a map of where execution-model doctrine is
enforced or referenced:

- **E1** — this file (`coordinator/docs/wiki/plan-execute-session-split.md`): the canonical
  doctrine home; all other surfaces cross-reference it by path.
- **E2** — `coordinator/skills/review/SKILL.md`: exit-gate cites this wiki.
- **E3** — `handoff/SKILL.md`: trigger-gate, NO-test handling, `## Plan to Execute` section.
- **E4** — `execute-plan/SKILL.md`: authorization defined as the frontmatter stamp, Phase 1
  read/confirm step, upstream entry points via `/handoff` + `/pickup`.
- **E5** — `pickup/SKILL.md` + `autonomous/SKILL.md`: Step 1 stamp-verification, `/autonomous`
  exemption.
- **E6** — global `CLAUDE.md` § Implementation Standards — Extensions (the EM-only clauses this
  once cited under `coordinator/snippets/em-operating-doctrine.md` no longer have a surviving
  heading there — the content lives only at the global-CLAUDE.md location now).
- **E7** — `writing-plans.md`: execution-mode reorder — fresh session is the DEFAULT, with the
  same-session carve-out documented as the exception.
- **E8** — `coordinator/commands/mise-en-place.md`: Phase 5/6 sentinel write, and
  `mise-en-place.md:10`'s "PM authorization is implicit in invocation" as EXCEPTION 3's
  authorization basis.

