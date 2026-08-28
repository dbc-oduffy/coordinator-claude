---
name: quick-wrap
description: "Short session close: commit, handle loose ends, stop. Not workstream-complete."
version: 1.0.0
allowed-tools: ["Read", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional context]"
---

# Quick Wrap — the Light End-of-Work Close

<!-- Purpose: names and discharges "commit-and-stop". -->
<!-- Negative-spec: NOT a cheaper workstream-complete. Writes no completion entry, reconciles no
     plan, opens no review trail, terminates no handoff chain with ancestors. A lesson does NOT
     disqualify. -->

The short checklist for a session whose work is finished, small, and unremarkable. The entry test
is a positive gate: fail one of the four and this is not the room — route to the named remedy, no
negotiating. Every computable condition names a single field read
— never a procedure the EM runs and interprets.

---

## Entry test — ALL four must hold

| # | Condition | Read | If it fails |
|---|---|---|---|
| 1 | **No governing plan** drove this session's work † | `close_gate.governing_plan` — `quick-wrap-assemble brief` <!-- engine-gap: field=close_gate.governing_plan producer=unknown memo=2026-08-14-doe-claude-em-quick-wrap-has-no-assembler-at-all.md --> | `/workstream-complete` |
| 2 | **Diff under the review brightline** — <500 novel LOC, <5 commits, <4 surfaces | `close_gate.diff` (session-scoped, carve-outs pre-applied) — `quick-wrap-assemble brief` <!-- engine-gap: field=close_gate.diff producer=unknown memo=2026-08-14-doe-claude-em-quick-wrap-has-no-assembler-at-all.md --> | **Scoped review, then wrap** (below), not `/workstream-complete` |
| 3 | **What this session claimed has no ancestors** ‡ | `artifact.chain.ancestor_count == 0` — `pickup-assemble brief <path>` for the artifact this session claimed; nothing claimed means nothing to read, test passes | `/workstream-complete` — a chain that accumulated history owes a coverage gate |
| 4 | **Work is finished** — nothing in-flight for a successor | judgment | `/handoff`, only if context pressure genuinely forces the stop |

**† `spec-dispatch`.** `close_gate.governing_plan.scope_mode == "spec-dispatch"` passes test 1 as a
deferred obligation, conditional on step 2's reconciliation micro-step running and step 4 reporting
it. `dispatch`-routed sessions carry `governing_plan.present: false` and pass as before.

**‡ A pickup is not itself the disqualifier — ancestry is.** A chain-root baton (`predecessor:`
`none`/null, no `additional_predecessors`, no `forked_from`) carries no prior session's scope to
account for, so claiming one and finishing it leaves no coverage gate owed. Until
`artifact.ancestry` lands, read those three frontmatter fields off the same brief. It closes here:
step 2 stamps its terminal disposition.

`close_gate.diff` already excludes relocated-without-modification lines and doc-only lines —
engine-applied, not an EM procedure. Report gross and novel counts in step 4 when the carve-out is
what drops the session under the line.

### The named route — scoped review, then wrap

Test 2 failing means a review is owed, not that this ceremony is wrong: (1) dispatch a reviewer
scoped to the risk surface — `Skill(coordinator:review-code)` diff-shaped, or a direct
`coordinator:code-reviewer` when scope is narrow; (2) integrate findings via the review-integrator,
applied never ratified back as a list; (3) run the checklist below, verdict in step 4. The only
route past test 2. **Unlocks nothing else** — test 1, 3, or 4 failing still routes to its named
sibling regardless of review outcome.

**A lesson is not a disqualifier** — capture through the `lesson` CLI, then wrap.

- **Branch ready to ship** → `/merging-to-main`. Quick-wrap ends a session, never a branch.
- **End of the working day** → `/workday-complete`, which supersedes this; never run both.

**Mutual exclusion.** `/quick-wrap`, `/workstream-complete`, and `/handoff` are exclusive — one
session, one closing ceremony. Two genuinely different workstreams close separately, named which.

---

## The checklist

Four steps. Longer than a few minutes means the entry test was wrong.

**1. Commit.** Run the safe-commit mechanism — it computes this session's safe pathspec from its
touch-list (minus anything a live peer also claims) and commits — publishing is the separate
cadence checkpoint below, not part of this call:

<!-- VERBATIM -->
On a PowerShell host, invoke the `coordinator-invoke.exe` door by absolute path through the call
operator (Shape W, `snippets/resolve-coordinator-bin.md` § The door):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'`

POSIX-host form (Shape A/B) dials the same op through the bare `coordinator-invoke` door.

**Pass `session_id` explicitly — the op refuses without it.** Scope is "none", so identity is
never taken from the environment, and `cwd` does not supply it either: `cwd` selects which tree is
scanned, nothing more. With no explicit `params.session_id` and no carried identity on the wire the
op returns `caller identity could not be established`, rather than falling back to the environment
of whoever spawned the warm server and committing one session's paths under another's claim. Both
params are required in practice: `cwd` for the tree, `session_id` for the identity.

**Payload is one positional JSON string, not `k=v`** — `cwd=<repo> message="<subject>"` does not
parse. **Never pass `--repo`**: this op is scope "none" and refuses it (`-32603`), unlike the
`push.outstanding` call just below. Add `"dry_run": true` to preview; omit it to commit.

**Do not ask whether to commit** — being asked was itself the defect, by explicit PM ruling. Run
it, report what the op's `rendered` field says landed. `"message": "<subject>"` for one group, the
`groups` param (inline list of `{"paths": [...], "message": "..."}` objects) for several — mutually
exclusive with `message`. A path outside the computed safe pathspec is silently dropped, never
caller-widened.

**Push checkpoint — `push.outstanding`.** The safe-commit mechanism does not publish; push runs
on a cadence, and `/quick-wrap` is one of its named checkpoints. Once the commit has landed, call
the primitive once and block on it (~150ms, synchronous — no detach or background wrapper):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" push.outstanding '{}' --repo "<repo-root>"`

Shape W above (PowerShell host); Shape A/B on a POSIX host — `snippets/resolve-coordinator-bin.md`.
`skipped: push:nothing-outstanding` is the ordinary no-op result, not a failure. The op owns the
branch-gate refusal, the protected-branch policy, the retry ladder, and the LFS-range predicate —
never hand-roll a `git push` beside it.

**2. Close loose ends.** The judgment step — sweep what this session actually touched:

- A **queue entry** (bug/debt/improvement) resolved this session: closure is a move, never
  in-place — `git mv state/<queue>/<slug>.yaml archive/<queue>/<YYYY-MM>/<slug>.yaml`, set
  `status: closed`, `closed_at:`, `closed_by:`.
- An **inbound cross-repo memo** actioned this session → resolve, don't leave inboxed.
- **A residual surfaced but not closed**, recorded only in prose: file via
  `coordinator-queue-append --schema bug-backlog|debt-backlog|improvement-queue` — naming it in
  step 4 and filing nothing is dumping it.
- A `scope_mode: spec-dispatch` plan authored/executed this session: tick ACs, set `plan-tasks`
  dispositions; `status: implemented` is `d-stamp-plan-implemented`'s write, fired by the
  full-plan-shipped close-out — read the sizing status back to confirm it landed, never edit the
  field directly.
  `[[the-deliverable-cascade-has-never-written-a-terminal-status]]`
- A plan this session executed whose `exit_criterion_met` is absent blocks the close — no
  directive can compute this. `asserted: false` is a legitimate, first-class outcome and does not
  block; it routes to `/handoff` or a Phase-5 halt instead.
- **The chain-root baton this session claimed and finished** (the only kind test 3 admits): stamp
  `deployment_state: shipped` + `shipped_in: <this session's commit>`; `status` stays `claimed`
  (the schema enum admits only `open`/`claimed`). Same first-hand-observer ground as the
  `dispatch`-routed sizing below — the session that did the work observes its own completion.
  Leaving it unstamped strands a claim no successor will ever release, and
  `sweep-shipped-handoffs` never archives it.
- **A `dispatch`-routed sizing that routed this session**, work done: write `status: shipped`
  directly — no plan means this is its only write path.
- **Every terminal sizing-object THAT NO PLAN CITES** (`shipped`/`declined`/`superseded`):
  `close_gate.terminal_sizings` <!-- engine-gap: field=close_gate.terminal_sizings producer=unknown memo=2026-08-14-doe-claude-em-quick-wrap-has-no-assembler-at-all.md -->
  `git mv` each to `archive/sizings/<YYYY-MM>/` unmodified — no `closed_at`/`closed_by` (schema
  disallows both). A record still at `sized`, `routed`, or `draft` is untouched no matter how
  finished it looks — only what a prior step already marked terminal moves.
  **A cited sizing-object stays in `state/sizings/`, terminal or not.** `plan.schema.json`
  constrains `sizing_object` to `^state/sizings/.+\.yaml$`, so the plan cannot be repointed at an
  archived path; leaving the citation behind instead makes `assert-plan-sizing-citation` report
  DANGLING. Archiving it is unlandable either way — in practice only a `route: dispatch` sizing,
  which has no plan by construction, is ever movable here.
- `coordinator-fold-execution-record` sidecars this session produced — read each `divergence`
  block (surface any crashed-executor marker), then delete.

Nothing to close is an ordinary outcome — say so and move on.

**3. Refresh.** `regenerate-orientation-cache` — batch into the same shell call as step 1's
`session.safe_commit_offer` dial when step 2 needed no separate CLI invocation of its own (no
dirty-tree/queue CLI ran between them); keep it a separate call only when step 2 actually ran one.

**4. Report.** Three lines: what landed (commit SHA), what you closed, what's deliberately open.
Five for `scope_mode: spec-dispatch`: add the `code-reviewer` verdict + integration commit, and
that the plan-reconciliation micro-step ran. Then stop.

---

## Anti-scope

- **Never deletes, force-pushes, or rewrites history.** No `reset --hard`, `checkout --` over
  another's hunk, branch deletion, rebase. Authorized: a scoped forward commit, a `git mv` of a
  queue entry or terminal sizing-object into archive, this session's own terminal-status write —
  on a sizing-object, or on the chain-root baton it claimed itself. **Never on a baton with
  ancestors** — that chain's termination belongs to `/workstream-complete`.
- **Writes no continuity artifact** — no handoff, spinoff, completion entry; the entry test
  already routed you elsewhere if one was owed.
- **Captures no lesson itself** — via the `lesson` CLI, then wrap.
- **Runs no test suite.** `Skill(coordinator:validate)` is deliberately gone from step 1 — the
  "fast" tier is neither fast nor cheap, and paying for it at every light close was the defect. Do
  not re-add it or hand-roll `pytest`. Report evidence already produced as-is; a suite already
  known red fails the entry test.
- **Opens no review trail of its own.** Above the test-2 brightline, the scoped-review route runs
  *before* this checklist and never substitutes for the partitioned review a plan-driven or
  predecessor-consuming session owes — except `scope_mode: spec-dispatch`, discharged upstream.
- **Never closes a queue entry this session didn't resolve** — closing on a hunch is worse than
  leaving it open.
- **Does not supersede the PM's closure authority.** Closing a *workstream* is the PM's call; this
  closes a *session* — never emits a "Session Complete" header.

## Discovery, test surface, see also

Surfaced at `/workday-start`; named in `/handoff`'s Step 0 NO-tests as the "shipped, not
handed-off" destination. No runtime test for the body — prose doctrine, not code; checks are
skill-body lint and frontmatter validation. The entry test is a table so drift stays greppable.

- `skills/workstream-complete/SKILL.md` — the heavy close, for a test 1/3/4 failure.
- `skills/handoff/SKILL.md` — its Step 0 redirects here.
- `commands/workday-complete.md` — supersedes this one.
