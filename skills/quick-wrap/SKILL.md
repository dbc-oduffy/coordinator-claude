---
name: quick-wrap
description: "Short session close: commit, loose ends, stop. Not workstream-complete."
version: 1.0.0
allowed-tools: ["Read", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional context]"
---

# Quick Wrap — the Light End-of-Work Close

<!-- Negative-spec: NOT a cheaper workstream-complete. Reconciles no plan (bar the spec-dispatch
     micro-step), opens no review trail, writes no handoff or spinoff. A lesson does NOT
     disqualify. -->

Fallback only: an `emit-dispatch-workflow` run closes in-run.


The short checklist for a session whose work is finished, small, and unremarkable. Fail one of the
four entry conditions and route to the named remedy, no negotiating.

---

## Entry test — ALL four must hold

| # | Condition | Read | If it fails |
|---|---|---|---|
| 1 | **No governing plan** drove this session's work † | `close_gate.governing_plan` — `quick-wrap-assemble brief` | `/workstream-complete` |
| 2 | **Diff under the review brightline** — <500 novel LOC, <5 commits, <4 surfaces | `close_gate.diff` (session-scoped, carve-outs pre-applied) — `quick-wrap-assemble brief` | **Scoped review, then wrap** (below), not `/workstream-complete` |
| 3 | **What this session claimed is finished here** ‡ | `artifact.chain.ancestor_count` — `pickup-assemble brief <path>`; nothing claimed, test passes. Ancestors do not fail it; step 2 pays their legs | `/handoff`, if the claimed baton is not finished |
| 4 | **Work is finished** — nothing in-flight for a successor | judgment | `/handoff`, only if context pressure genuinely forces the stop |

**† `spec-dispatch`.** `close_gate.governing_plan.scope_mode == "spec-dispatch"` passes test 1 as a
deferred obligation, conditional on step 2's reconciliation micro-step running and step 5 reporting
it. `dispatch`-routed sessions carry `governing_plan.present: false` and pass as before.

**‡ A claimed baton closes here, with or without ancestors.** A chain-root baton (`predecessor:`
`none`/null, no `additional_predecessors`, no `forked_from`) is stamped terminal in step 2; one
with ancestors gets its Session Ledger row appended first.

`close_gate.diff` already excludes relocated and doc-only lines; report gross and novel counts in
step 5 when the carve-out drops the session under the line.

### The named routes past test 2

Test 2 failing means a review is owed. Route 1 is the default.

**1. Scoped review, then wrap (the default).** (1) register the reviewed file list with
`review-findings-ledger targets --add`, then dispatch a reviewer scoped to the risk surface —
`Skill(coordinator:review-code)` diff-shaped, or a direct `coordinator:code-reviewer` when scope
is narrow; (2) the reviewer applies and verifies its own ledger; (3) run the checklist below, verdict in step 5.

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**2. Successor-runs-review handoff — only when the owed review is genuinely un-runnable in this
session.** Name the class member per `coordinator/skills/handoff/SKILL.md` § Step 0 trigger 4; that
trigger's discharge (name the blocker and the event that clears it in the successor's remit)
governs. This route terminates in `/handoff`, never in `/execute-plan`'s Phase-5 halt
(`coordinator/skills/execute-plan/SKILL.md` § Phase 5). Never a lighter substitute for dispatching a reviewer.

**Unlocks nothing else** — test 1, 3, or 4 failing still routes to its named sibling.

**A lesson is not a disqualifier** — capture through the `lesson` CLI, then wrap.

- **Branch ready to ship** → `/merging-to-main`; quick-wrap ends a session, never a branch.
- **End of the working day** → `/workday-complete`; never run both.

**Mutual exclusion.** `/quick-wrap`, `/workstream-complete`, and `/handoff` are exclusive — one
session, one closing ceremony; two different workstreams close separately, named which.

---

## The checklist

Five steps; longer than a few minutes means the entry test was wrong.

**1. Commit.** Run the safe-commit mechanism — it computes this session's safe pathspec from its
touch-list (minus anything a live peer also claims) and commits — publishing is the separate
cadence checkpoint below, not part of this call:

<!-- VERBATIM -->
On a PowerShell host, invoke the `coordinator-invoke.exe` door by absolute path through the call
operator (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § The door):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" session.safe_commit_offer '{"cwd":"<repo-root>","session_id":"<this session's id>"}'`

POSIX: the bare `coordinator-invoke` door.

**Pass `session_id` explicitly — the op refuses without it** (`caller identity could not be established`); `cwd` only selects the tree scanned.

**Payload is one positional JSON string, not `k=v`.** **Never pass `--repo`**: this op is scope "none" and refuses it (`-32603`). Add `"dry_run": true` to preview; omit it to commit.

**Do not ask whether to commit.** Run it, report what the op's `rendered` field says landed. `"message": "<subject>"` for one group, the
`groups` param (list of `{"paths": [...], "message": "..."}`) for several — mutually
exclusive with `message`. Paths outside the safe pathspec drop silently.

**2. Close loose ends.** The judgment step — sweep what this session actually touched:

- A **queue entry** resolved this session: closure is a move, never in-place — `git mv state/<queue>/<slug>.yaml archive/<queue>/<YYYY-MM>/<slug>.yaml`, set
  `status: closed`, `closed_at:`, `closed_by:`.
- An **inbound cross-repo memo** actioned this session → resolve it.
- **An unclosed residual** in prose only: file it, one call each —
  `coordinator-queue-append --schema bug-backlog --status open --severity P0|P1|P2|P3 --title …
  --surface … --repro-steps … --evidence … --body …` (other queues: `--schema NAME --help`).
  Naming it in step 5 alone is dumping it.
- A `scope_mode: spec-dispatch` plan authored/executed this session: tick ACs, set `plan-tasks`
  dispositions; a met terminal judge stamps `status: implemented` inside `terminal_commit`
  ([terminal-judge](../../docs/wiki/reviewer-pipeline/terminal-judge.md)); verify, never restamp. Where it did not stamp, the `d-stamp-plan-implemented` directive owns it.
  `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.
- A plan this session executed whose `exit_criterion_met` is absent blocks the close.
  `asserted: false` does not block; it routes to `/handoff` or a
  Phase-5 halt (`coordinator/skills/execute-plan/SKILL.md` § Phase 5).
- **The baton this session claimed and finished.** If it has ancestors, first append the Session
  Ledger row through `coordinator-invoke handoff.append_session_ledger`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`). Then, ancestors or not, stamp
  `deployment_state: shipped` + `shipped_in: <this session's commit>`; `status` stays `claimed`
  (the enum admits only `open`/`claimed`). Both keys, or the baton is stranded in `state/handoffs/` — `sweep-terminal-handoffs` walks past an unstamped record. The drain below files it.
- **A `dispatch`-routed sizing that routed this session:** the close stamps it `shipped` (never one with `requirement_register`; its rollup ships it) when
  this session committed the sizing file and non-bookkeeping work; otherwise stamp by hand
  (`j-dispatch-sizing-ship-failed`). A second XS dispatched and left unfinished: flip it to
  `status: declined` first, or it ships as a false positive.
- **Each sizing-object this session made terminal** (`shipped`/`declined`/`superseded`,
  `close_gate.terminal_sizings`): archive with `coordinator-invoke fleet.archive_terminal_sizings
  '{"mode":"already-terminal","dry_run":false,"candidate_ids":["state/sizings/<slug>.yaml"]}'` —
  it moves and commits itself (a hand `git mv` is refused by `safe_commit_offer`). Other sessions'
  terminal sizings are not this close's work. No `closed_at`/`closed_by`. A record still at `sized`,
  `routed`, or `draft` is untouched. A sizing FK resolving only under `archive/` is correct.
- `coordinator-fold-execution-record` sidecars this session produced — a diverged sidecar's prose
  is already in the envelope (judgment point `j-diverged-sidecars`, or `-degraded` on a failed
  scan): settle that point, then delete. Never open sidecars to read.

**Completion entry and lessons, before the drain.** Write the completion entry with
`coordinator-complete-entry` (title, prose of eight sentences or fewer, nature) — once per session.
Capture lessons (`lesson` CLI) here.

**Then drain — MANDATORY, and the last act of this step.** Run `sweep-terminal-handoffs` once,
after every stamp above is written. **The close condition is checkable and you check it: `state/handoffs/` holds no
record carrying a terminal `deployment_state` when you report.** Idempotent; it drains other sessions'
residue too.
`[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`

**3. Refresh.** `regenerate-orientation-cache --invoker quick-wrap`.

**4. Changelog.** `& "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-step9-append-changelog.exe" --no-push` (POSIX `$COORDINATOR_SETTINGS_HOME/bin/workday-complete-step9-append-changelog --no-push`). Rerun-safe.

**5. Report.** Four lines: what landed (commit SHA), the completion entry path, what you closed,
what's deliberately open. Six for `scope_mode: spec-dispatch`: add the `code-reviewer` verdict + ledger verified + one
commit, and that the plan-reconciliation ran. Then stop.

---

## Anti-scope

- **Never deletes, force-pushes, or rewrites history.** No `reset --hard`, `checkout --` over
  another's hunk, branch deletion, rebase. Authorized: a scoped forward commit, a `git mv` of a
  queue entry or terminal sizing-object into archive, this session's own terminal-status write on a
  sizing-object or the baton it claimed.
- **Writes no handoff or spinoff**; the completion entry is its one record.
- **Captures lessons only through the `lesson` CLI.**
- **Runs no test suite.** Do not add `Skill(coordinator:validate)` or hand-roll `pytest`. Report
  evidence already produced as-is; a suite already known red fails the entry test.
- **Opens no review trail of its own.** The scoped-review route runs *before* this checklist and
  never substitutes for the partitioned review a plan-driven or predecessor-consuming session
  owes — except `scope_mode: spec-dispatch`, discharged upstream.
- **Never closes a queue entry it didn't resolve.**
- **Does not supersede the PM's closure authority.** This closes a *session*, never a *workstream*
  — never emits a "Session Complete" header.

## See also

`skills/workstream-complete/SKILL.md` (the heavy close), `skills/handoff/SKILL.md` (its Step 0
redirects here), `commands/workday-complete.md` (supersedes this one).
