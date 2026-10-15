---
name: quick-wrap
description: "Short session close: commit, loose ends, stop. Not workstream-complete."
version: 1.0.0
allowed-tools: ["Read", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional context]"
---

# Quick Wrap — the Light End-of-Work Close

<!-- Purpose: names and discharges "commit-and-stop". -->
<!-- Negative-spec: NOT a cheaper workstream-complete. Reconciles no plan (bar the spec-dispatch
     micro-step), opens no review trail, writes no handoff or spinoff. A lesson does NOT
     disqualify. -->

Fallback only: an `emit-dispatch-workflow` run closes in-run.

The short checklist for a session whose work is finished, small, and unremarkable. The entry test
is a positive gate: fail one of the four and route to the named remedy, no negotiating. Every
computable condition names a single field read.

---

## Entry test — ALL four must hold

| # | Condition | Read | If it fails |
|---|---|---|---|
| 1 | **No governing plan** drove this session's work † | `close_gate.governing_plan` — `quick-wrap-assemble brief` | `/workstream-complete` |
| 2 | **Diff under the review brightline** — <500 novel LOC, <5 commits, <4 surfaces | `close_gate.diff` (session-scoped, carve-outs pre-applied) — `quick-wrap-assemble brief` | **Scoped review, then wrap** (below), not `/workstream-complete` |
| 3 | **What this session claimed is finished here** ‡ | `artifact.chain.ancestor_count` — `pickup-assemble brief <path>` for the artifact this session claimed; nothing claimed means nothing to read, test passes. Ancestors do not fail it; step 2 pays their legs | `/handoff`, if the claimed baton is not finished |
| 4 | **Work is finished** — nothing in-flight for a successor | judgment | `/handoff`, only if context pressure genuinely forces the stop |

**† `spec-dispatch`.** `close_gate.governing_plan.scope_mode == "spec-dispatch"` passes test 1 as a
deferred obligation, conditional on step 2's reconciliation micro-step running and step 4 reporting
it. `dispatch`-routed sessions carry `governing_plan.present: false` and pass as before.

**‡ A claimed baton closes here, with or without ancestors.** A chain-root baton (`predecessor:`
`none`/null, no `additional_predecessors`, no `forked_from`) is stamped terminal in step 2. A baton
with ancestors gets its Session Ledger row appended first (step 2), then the same stamp. Until
`artifact.ancestry` lands, read those three frontmatter fields off the same brief.

`close_gate.diff` already excludes relocated-without-modification lines and doc-only lines —
engine-applied, not an EM procedure. Report gross and novel counts in step 4 when the carve-out is
what drops the session under the line.

### The named routes past test 2

Test 2 failing means a review is owed, not that this ceremony is wrong. Route 1 is the default;
route 2 requires a named class member.

**1. Scoped review, then wrap (the default).** (1) register the reviewed file list with
`review-findings-ledger targets --add`, then dispatch a reviewer scoped to the risk surface —
`Skill(coordinator:review-code)` diff-shaped, or a direct `coordinator:code-reviewer` when scope
is narrow; (2) the reviewer applies and verifies its own ledger, applied never ratified back as a
list; (3) run the checklist below, verdict in step 4.

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**2. Successor-runs-review handoff — only when the owed review is genuinely un-runnable in this
session.** The class member that fires must be named per `coordinator/skills/handoff/SKILL.md`
§ Step 0 trigger 4; that trigger's own discharge (name the blocker and the event that clears it
in the successor's remit) governs. This route terminates in `/handoff`, never in `/execute-plan`'s
Phase-5 halt (`coordinator/skills/execute-plan/SKILL.md` § Phase 5 — native to that skill and
evidence-gated to scope-explosion). Never a lighter-weight substitute for dispatching a reviewer.

**Unlocks nothing else** — test 1, 3, or 4 failing still routes to its named sibling regardless
of review outcome.

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
operator (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § The door):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'`

POSIX-host form (Shape A/B) dials the same op through the bare `coordinator-invoke` door.

**Pass `session_id` explicitly — the op refuses without it** (`caller identity could not be established`): scope is "none", identity is never taken from the environment, and `cwd` only selects the tree scanned.

**Payload is one positional JSON string, not `k=v`** — `cwd=<repo> message="<subject>"` does not
parse. **Never pass `--repo`**: this op is scope "none" and refuses it (`-32603`). Add `"dry_run": true` to preview; omit it to commit.

**Do not ask whether to commit.** Run it, report what the op's `rendered` field says landed. `"message": "<subject>"` for one group, the
`groups` param (inline list of `{"paths": [...], "message": "..."}` objects) for several — mutually
exclusive with `message`. A path outside the computed safe pathspec is silently dropped, never
caller-widened.

**2. Close loose ends.** The judgment step — sweep what this session actually touched:

- A **queue entry** resolved this session: closure is a move, never in-place — `git mv state/<queue>/<slug>.yaml archive/<queue>/<YYYY-MM>/<slug>.yaml`, set
  `status: closed`, `closed_at:`, `closed_by:`.
- An **inbound cross-repo memo** actioned this session → resolve it.
- **A residual surfaced but not closed**, recorded only in prose: file it, one call each —
  `coordinator-queue-append --schema bug-backlog --status open --severity P0|P1|P2|P3 --title …
  --surface … --repro-steps … --evidence … --body …` (other queues: `--schema NAME --help`).
  Naming it in step 4 alone is dumping it.
- A `scope_mode: spec-dispatch` plan authored/executed this session: tick ACs, set `plan-tasks`
  dispositions; a met terminal judge stamps `status: implemented` inside `terminal_commit`
  ([terminal-judge](../../docs/wiki/reviewer-pipeline/terminal-judge.md)); verify, never restamp. Where it did not stamp, the `d-stamp-plan-implemented` directive owns it.
  `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.
  `[[the-deliverable-cascade-has-never-written-a-terminal-status]]`
- A plan this session executed whose `exit_criterion_met` is absent blocks the close — no
  directive can compute this. `asserted: false` is a legitimate, first-class outcome and does not
  block; it routes to `/handoff` or a Phase-5 halt instead (`coordinator/skills/execute-plan/SKILL.md`
  § Phase 5).
- **The baton this session claimed and finished.** If it has ancestors, first append the Session
  Ledger row through the `handoff.append_session_ledger` op, invoked through `coordinator-invoke`
  per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. Then, ancestors or not, stamp
  `deployment_state: shipped` + `shipped_in: <this session's commit>`; `status` stays `claimed`
  (the schema enum admits only `open`/`claimed`). Both keys, or the baton is stranded in `state/handoffs/` — `sweep-terminal-handoffs` walks past an unstamped record and nothing else catches it. The stamp makes it archivable; the drain below files it.
- **A `dispatch`-routed sizing that routed this session:** the close stamps it `shipped` (never one with `requirement_register`; its rollup ships it) when
  this session committed the sizing file and non-bookkeeping work; stamp by hand on a
  `j-dispatch-sizing-ship-failed` judgment point or when the sizing file was not in this session's commits. A second XS
  dispatched this session and left unfinished: flip it to `status: declined` before quick-wrap —
  the close reads "landed" per session, so an abandoned `sized`/`routed` sizing ships as a false positive.
- **Each sizing-object this session made terminal** (`shipped`/`declined`/`superseded`):
  `close_gate.terminal_sizings`
  archive with `coordinator-invoke fleet.archive_terminal_sizings
  '{"mode":"already-terminal","dry_run":false,"candidate_ids":["state/sizings/<slug>.yaml"]}'` —
  it moves each to `archive/sizings/<YYYY-MM>/` unmodified and commits the move itself (a hand
  `git mv` is refused by `safe_commit_offer` as unattributable). Other sessions' terminal sizings
  are not this close's work; `/workday-complete` archives the corpus. No `closed_at`/`closed_by` (schema disallows both). A record still at `sized`, `routed`, or `draft` is untouched no matter how
  finished it looks — only what a prior step already marked terminal moves.
  **A citation does not pin a record:** the sizing FK resolves live-then-archive (`resolve_sizing_citation`), so a value resolving only under `archive/` is correct.
- `coordinator-fold-execution-record` sidecars this session produced — a diverged sidecar's prose
  is already in the envelope (judgment point `j-diverged-sidecars`; a failed scan surfaces as
  `j-diverged-sidecars-degraded`), so settle that point, then delete. Never open sidecars to read.

**Completion entry and lessons, before the drain.** Write the completion entry with
`coordinator-complete-entry` (title, prose of eight sentences or fewer, nature) — once per session;
a run-less close has no run id, so the once-per-run-id invariant binds runs, not this close. Capture
any lesson through the `lesson` CLI here, not afterwards.

**Then drain — MANDATORY, and the last act of this step.** Run `sweep-terminal-handoffs` once,
after every stamp above is written. A record stamped archivable and left in `state/handoffs/` is an
unfinished close: until it moves, every surface that counts open batons reads it as *unstarted*. **The close
condition is checkable and you check it: `state/handoffs/` holds no record carrying a terminal
`deployment_state` when you report.** The drain is idempotent and a sub-second no-op when there is
nothing to move; it drains other sessions' terminal residue in the same pass, by design.
`[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`

Nothing to close is ordinary — say so; the drain still runs.

**3. Refresh.** `regenerate-orientation-cache --invoker quick-wrap` — batch into the same shell call as step 1's
`session.safe_commit_offer` dial when step 2 needed no separate CLI invocation of its own (no
dirty-tree/queue CLI ran between them); keep it a separate call only when step 2 actually ran one.

**4. Report.** Four lines: what landed (commit SHA), the completion entry path, what you closed,
what's deliberately open. Six for `scope_mode: spec-dispatch`: add the `code-reviewer` verdict + ledger verified + one
commit, and that the plan-reconciliation micro-step ran. Then stop.

---

## Anti-scope

- **Never deletes, force-pushes, or rewrites history.** No `reset --hard`, `checkout --` over
  another's hunk, branch deletion, rebase. Authorized: a scoped forward commit, a `git mv` of a
  queue entry or terminal sizing-object into archive, this session's own terminal-status write —
  on a sizing-object, or on the baton it claimed itself (ledger row appended first when it has
  ancestors).
- **Writes no handoff or spinoff.** The completion entry is the one record it writes.
- **Captures lessons only through the `lesson` CLI**, in step 2.
- **Runs no test suite.** `Skill(coordinator:validate)` is deliberately gone from step 1; do not
  re-add it or hand-roll `pytest`. Report evidence already produced as-is; a suite already
  known red fails the entry test.
- **Opens no review trail of its own.** Above the test-2 brightline, the scoped-review route runs
  *before* this checklist and never substitutes for the partitioned review a plan-driven or
  predecessor-consuming session owes — except `scope_mode: spec-dispatch`, discharged upstream.
- **Never closes a queue entry this session didn't resolve.**
- **Does not supersede the PM's closure authority.** Closing a *workstream* is the PM's call; this
  closes a *session* — never emits a "Session Complete" header.

## Discovery, test surface, see also

Surfaced at `/workday-start`; `/handoff`'s Step 0 NO-tests name it the "shipped, not handed-off"
destination.

- `skills/workstream-complete/SKILL.md` — the heavy close, for a test 1/3/4 failure.
- `skills/handoff/SKILL.md` — its Step 0 redirects here.
- `commands/workday-complete.md` — supersedes this one.
