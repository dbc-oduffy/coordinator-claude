---
name: quick-wrap
description: "Short session close: commit, handle loose ends, stop. Not workstream-complete."
version: 1.0.0
allowed-tools: ["Read", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional context]"
---

# Quick Wrap — the Light End-of-Work Close

<!-- Purpose: names and discharges "commit-and-stop", the end-of-work exit coordinator doctrine
     has cited for months without ever providing an artifact for it. -->
<!-- Negative-spec: this is NOT a cheaper workstream-complete. It writes no completion entry,
     reconciles no plan, opens no review trail, and terminates no handoff chain. A session that
     produced any of those is not a quick-wrap session — see the entry test. A surfaced lesson is
     the one thing that does NOT disqualify it. -->

Doctrine has named this exit for months without providing it. `skills/handoff/SKILL.md` says
*"Workstreams end via `/workday-complete`, `/merge-to-main`, or commit-and-stop"*, and several
sibling surfaces repeat the same three-way choice. Every one of those citations pointed at a
ceremony that did not exist — so "commit-and-stop" meant *improvise it*, and the improvisation was
usually reaching for a heavier ceremony that fit worse. This skill is that missing artifact: the
short checklist for a session whose work is finished, small, and unremarkable.

**It is deliberately not a cheaper `/workstream-complete`.** The entry test below is a positive
gate, not a matter of taste, precisely because a light exit that is easy to reach becomes the
default — and every session that takes it is a session that wrote no completion entry and
reconciled no plan. If you are reading the entry test looking for a way past it, the answer is
already no — with one exception, and it is written into the test rather than reasoned around it:
test 2 names a review debt, and paying that debt directly is a supported route, not an override.
Every other failure routes to the named sibling.

---

## Entry test — ALL four must hold

Fail any one and this is not the room. Route to the named remedy instead and do not negotiate
with the test; it is cheap to discharge the debt the test names and expensive to lose the capture.

**The four tests measure two independent debts.** Tests 1, 3, and 4 ask *is continuity substrate
owed* — a plan reconciliation, a consumed predecessor, a successor baton. Test 2 asks *is a review
owed*. A session can owe a review and owe no continuity artifact at all; that is why test 2 has
its own remedy and does not route to `/workstream-complete`. Routing it there conscripted a
ceremony with no plan to reconcile and no predecessor to account for in order to deliver a review.

| # | Condition | If it fails |
|---|---|---|
| 1 | **No governing plan** drove this session's work | `/workstream-complete` — a plan needs reconciling against what shipped |
| 2 | **Diff is under the review brightline** — under 500 novel LOC, under 5 commits, under 4 distinct surfaces | **Scoped review, then wrap** — the named route below. Not `/workstream-complete`. |
| 3 | **No predecessor consumed** — this session picked up no baton | `/workstream-complete` — a session that consumed a predecessor owes a coverage gate |
| 4 | **Work is finished** — nothing in-flight for a successor | `/handoff` — and only if context pressure is genuinely forcing the stop |

### Sizing test 2 — novel LOC, code LOC

The brightline counts **novel code lines**, not gross diff lines. Two carve-outs, both explicit
so they are applied deliberately rather than argued for case by case:

- **Relocation does not count.** Lines moved without modification — a forward-port, a revert, a
  file move, un-stranding previously-reviewed work, a vendored-content move — were already
  reviewed where they were authored, and relocating them adds no review surface. What *is* review
  surface in a relocation is the **seams**: dropped content, a regression leaking across, a stale
  citation left pointing at the old locus. Size on the seams and scope any review to them.
  Modified-in-transit lines are novel and do count.
- **Doc-only lines do not count.** Test 2 gates a *code* review; a decision record, forensics
  writeup, wiki page, or handoff body is not code-review surface. This is a ruling, not an
  oversight — a session that lands an investigation plus a decision record should not trip a
  code-review brightline on prose. Doc quality is reviewed at the distillation and docs
  ceremonies, not here.

If applying the carve-outs is what drops you under the line, say so in the step-4 report with the
gross and novel counts. A carve-out claimed silently is indistinguishable from talking yourself
through the gate.

### The named route — scoped review, then wrap

Test 2 failing means a review is owed, not that this ceremony is wrong. Discharge it directly:

1. **Dispatch a reviewer scoped to the actual risk surface** — the seams for a relocation, the
   novel hunks otherwise. `Skill(coordinator:review-code)` for a diff-shaped review; a direct
   `coordinator:code-reviewer` dispatch when the scope is narrow and named.
2. **Integrate the findings** via the review-integrator, per standing doctrine — findings are
   applied, never ratified back to the PM as a list.
3. **Then run the checklist below**, reporting the review verdict and what it found in step 4.

This is the only route past test 2. It is not a lighter option — it is the same review debt paid
directly instead of through a ceremony that also demanded continuity artifacts the session did not
owe. **It does not unlock the other three tests:** a session that fails test 1, 3, or 4 still
routes to its named sibling regardless of how its review resolved.

**A lesson is not a disqualifier.** A surfaced lesson used to be test 2 and is deliberately gone:
capture is already discharged by the `lesson` CLI, the backlog is deep enough that one more entry
is not worth a heavier ceremony, and routing on it sent single-memo sessions to a workstream close
they had no workstream for. Capture the lesson through the CLI and wrap.

Two further redirects that are not size questions at all:

- **Branch is ready to ship** → `/merging-to-main`. Quick-wrap ends a session, never a branch.
- **End of the working day, not just this session** → `/workday-complete`. It supersedes this;
  never run both.

**Mutual exclusion.** `/quick-wrap` and `/workstream-complete` are exclusive, the same way
`/handoff` and `/workstream-complete` already are. One session, one closing ceremony — closing
ceremony here means the session terminators (`ceremony-calibration.md` § Session terminators:
`/workstream-complete`, `/handoff`, `/workday-complete`). If you have two workstreams and genuinely
different dispositions, close each separately and name which is which.

---

## The checklist

Four steps. If it is taking longer than a few minutes, the entry test was wrong.

**1. Commit.** Run the safe-commit mechanism — it computes this session's own safe pathspec from
its touch-list (minus anything a live peer session also claims) and commits + pushes it:

<!-- VERBATIM -->
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/safe-commit-offer"
```

**Do not ask whether to commit** — by explicit PM ruling, being asked was itself the defect. Run
it, then report what landed. Prefer authored grouping over the mechanical default when this
session did describable work: `--message "<subject>"` for one coherent group, or
`--groups-json <file>` for several. Any path you name that is not in the computed safe pathspec is
silently dropped — the boundary is computed, never caller-widened.

**2. Close the loose ends.** This is the judgment step, and it is yours — nothing computes it.
Sweep what this session actually touched and finish what it left open. The recurring shapes:

- A **bug or improvement queue entry** this session resolved. Closure is a move, never an in-place
  edit: `git mv state/<queue>/<slug>.yaml archive/<queue>/<YYYY-MM>/<slug>.yaml`, then set
  `status: closed`, `closed_at: <YYYY-MM-DD>`, and `closed_by:` in the archived file. An entry
  marked closed but still sitting in `state/` is the failure mode this shape prevents.
- An **inbound cross-repo memo** this session actioned → resolve it rather than leaving it in the
  inbox. Inbox depth is not a backlog.
- A **stale marker or tracker row** this session invalidated.
- **Scratch this session authored** that nobody needs tomorrow.
- A **residual this session surfaced and did not close**, recorded so far only in prose — a plan
  body, a commit message, your own step-4 report. Prose is not a home. Route it via
  `coordinator-queue-append --schema bug-backlog|debt-backlog|improvement-queue`; naming an open
  item in step 4 and filing nothing is dumping it, not carrying it forward.

Nothing to close is a perfectly ordinary outcome — say so and move on. Do not manufacture a loose
end to make the step feel earned.

**3. Refresh orientation.** `regenerate-orientation-cache` — so the next session boots on what is
now true rather than what was true this morning.

**4. Report.** Three lines, no ceremony: what landed (with the commit SHA), what you closed, and
what is deliberately still open. Then stop.

---

## Anti-scope

- **Never deletes, force-pushes, or rewrites history.** No `git reset --hard`, no
  `git checkout --` over someone else's hunk, no branch deletion, no rebase. The only mutation
  this skill authorizes is a scoped forward commit and a `git mv` of a queue entry into the
  archive. Anything irreversible is out of scope, including behind a flag.
- **Writes no continuity artifact.** No handoff, no spinoff, no completion entry. If the session
  needs one, the entry test already routed you elsewhere — a quick-wrap that writes a handoff is
  a `/handoff` wearing a disguise.
- **Captures no lesson itself.** A lesson does not disqualify the session (see the entry test), but
  this ceremony is not where it lands — write it through the `lesson` CLI, then wrap.
- **Runs no test suite.** By explicit PM ruling, the "fast" tier is neither fast nor cheap, and
  paying for it at every light close was the defect — `Skill(coordinator:validate)` was step 1 and
  is deliberately gone. Do not re-add it, and do not substitute a hand-rolled `pytest` invocation
  for it. Test evidence this session *already* produced is reported as-is; a suite already known
  red is not wrapped over — that session fails the entry test and belongs in
  `/workstream-complete`. The heavier ceremonies keep their validate gates; this one does not have
  one to skip.
- **Opens no review trail of its own.** Entry test 2 bounds the diff below the scale where a
  review is owed; above it, the scoped-review route runs *before* this checklist and reports its
  verdict into step 4. The checklist itself never dispatches a reviewer, and a scoped review is
  never a substitute for the partitioned review a plan-driven or predecessor-consuming session owes.
- **Never closes a queue entry this session did not actually resolve.** Step 2 is a sweep of your
  own work, not a backlog-grooming pass. Closing on a hunch is worse than leaving it open.
- **Does not supersede the PM's closure authority.** Authority to close a *workstream* belongs to
  the PM, signalled by their invoking a closing ceremony (a session terminator — see
  `ceremony-calibration.md` § Session terminators). This skill closes a *session* —
  reporting state honestly and stopping. It does not declare a workstream complete, and it never
  emits a "Session Complete" header, which preempts that authority and tends to coincide with
  leaving real follow-ups unfinished.

## Discovery

Surfaced at `/workday-start` alongside the other closing ceremonies, and named in `/handoff`'s
Step 0 NO-tests as the concrete destination for the "shipped, not handed-off" redirect — the
citation that previously dead-ended on "commit-and-stop" with nowhere to go.

## Test surface

No runtime test for the body — a skill body is prose-doctrine, not executable code, the same
rationale `skills/plan/SKILL.md` § Test Surface records for its own. The applicable automated
checks are skill-body lint and frontmatter validation. The entry test's four conditions are the
reviewable surface; they are stated as a table specifically so drift in them is greppable.

## See also

- `skills/workstream-complete/SKILL.md` — the heavy close, for an entry-test failure on tests 1,
  3, or 4. Test 2 takes the scoped-review route instead.
- `skills/handoff/SKILL.md` — in-flight work under context pressure; its Step 0 redirects here.
- `commands/workday-complete.md` — the day-level close, which supersedes this one.
