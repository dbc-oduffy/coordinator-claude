---
name: debt-triage
description: EM-PM ceremony to prioritize the debt backlog.
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

<!-- Schema: state/debt-backlog/*.yaml (YAML per entry); closure via git mv to archive/debt-backlog/<YYYY-MM>/. -->

# Debt Triage — Backlog Review and Prioritization

**Announce at start:** "I'm using the coordinator:debt-triage skill to review the debt backlog."

An **EM-PM conversation**, not a dispatched agent: the EM reads the backlog and recommends. Trigger
on demand, at >20 open items, or after a refactor that may have resolved several.

On a PowerShell host every CLI below takes its `.exe` launcher through the call operator (Shape W).
Ladder: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

Run `backlog-grind-assemble brief debt-triage` before Step 1. Over `state/debt-backlog/`,
`state/bug-backlog/` and `state/improvement-queue/` it returns open items with severity breakdown,
`bug-backlog` cross-reference (exact `surface`-field match), improvement-queue clustering
evidence, and a batched PM-gate. The improvement leg is emitted (Step 1); the debt-backlog steps
(2, 3, 6, and 6b's debt-backlog governance) stay EM-performed.

## Step 0: Surface prior rejections

Check `tasks/out-of-scope/*.md` (skip silently if absent). For any concept overlapping the
triage, surface: *"This is similar to `tasks/out-of-scope/<concept>.md` — we rejected this
because [reason]. Still feel the same?"* — confirm, reconsider (delete the file), or override.

## Step 1: Read current state

Take the `brief` output as-is. Overlap beyond the `surface`-field match is an EM judgment pass
before presenting overlaps to the PM for a dedup decision (populate `evidence:` on both entries).

**Improvement-queue triage is emitted, not EM classification.** Pick an appetite (`hunt`,
`standard` or `sweep` — values in `coordinator/queue-profiles/improvement.yaml`). Emit with
`emit-dispatch-workflow --queue state/improvement-queue --profile improvement --appetite <a>
--out state/scratch/debt-triage/{run-id}/improvement.workflow.mjs --repo-root <abs repo root>`.
No commit-readiness gate applies. Fire with `Workflow({scriptPath})`, never `--fire` — firing
authorizes the in-run fixes and closes and the post-run hand-back
(`coordinator/docs/wiki/ceremony-calibration/queue-terminus-doctrine.md` § Emitted-workflow
triage). The run's triage is the only triage; the EM works Steps 2–4 meanwhile. An emit refusal is
reported, not routed around. A `/bug-blitz` in the same tree takes its Phase 0.7 suite baseline
before this grind fires or after it finishes, never across it.

## Step 2: Verify relevance (emitted)

> **Do not ask whether to fire** — invoking this skill IS the request for the run this step
> names; it dissolves no gate this skill's own body names.

Debt-backlog rows only, emitted as in Step 1: `emit-dispatch-workflow --queue state/debt-backlog
--profile debt --appetite <a> --out state/scratch/debt-triage/{run-id}/debt.workflow.mjs
--repo-root <abs repo root>`, fired with `Workflow({scriptPath})`. Never hand-dispatch verifiers.
Relevance and evidence rules live in `coordinator/queue-profiles/debt.yaml` (`relevance_first`,
`defer_requires_evidence`). A row whose cited surface moved to another repo comes back as
`cross-repo`: route it by cross-repo memo, then close it here once delivered. Code that moved is
not code that was fixed. Hand-back types feed Step 5 as the improvement leg's do.

## Step 3: Re-prioritize

Blocking other work → P0. In a D/F-graded system → P1. In a recently A/B-graded system → may
deprioritize to P2. >30 days with no activity → flag for PM attention.

Before grouping, query historical `nature: tech-debt` completions
(`query-completions --where "nature=tech-debt" --since "90d" --format json`, ranked descending on
`frontmatter.loe.agent_dispatches` as a number — the reader takes no `--sort`): high-LoE areas
indicate festering complexity — escalate open items there. **Never rank on `loe.tshirt`**.
Zero-activity areas — flag: *"We have carried this debt for N days without touching it — is that
intentional?"* Present a one-paragraph summary before Step 4; zero rows:
`(no tech-debt completions logged in last 90d — hot-zone analysis unavailable)`.

## Step 4: Group for execution

"System" is the brief's `debt-backlog groups` evidence: the first path cited in `surface`,
else in title/body, cut to two directories. Never group on the row's free-text `system` field.

Present `## Triage Results` with four `###` tables headed `<label>: N items` (Closed, Recommended
for immediate action, Can defer, Needs PM decision); columns in the residue page.

## Step 5: Present to PM

Ask for: (1) approval to close no-longer-applicable items; (2) YAGNI/scope calls; (3)
prioritization of immediate-action items; (4) agreement on deferral reasoning; (5) goes to
`coordinator:apm`, not the PM: the improvement leg's hand-back types (`park`, `wont-do`, `yagni`,
`unclear-direction`, `needs-judgment`) are dispositioned by the APM (a code matter by
`coordinator:staff-eng`), which writes `pm_ruling: "<agent> (PM-delegated) ..."` on the row. Step
6b consumes it; the PM sees the receipt. Only a `pm_only` matter (important, urgent, no clear
answer, or irreversible) reaches the PM. Engine-originated hand-back types (`budget-exhausted`,
`verify-failed`, the rest) are reported by count; their rows stay open, not presented here.

## Step 6: Update backlog

After PM decisions:
1. Close resolved items — stamp `status: closed`, `closed_at:`, `closed_by: <sha>`, then
   `mkdir -p archive/debt-backlog/<YYYY-MM>` and `git mv` the entry in. Never `rmdir
   state/debt-backlog/` even if it empties.
2. Update `severity` per PM direction.
3. Remove YAGNI items the same way as (1), `closed_by` referencing the PM decision.
4. For a **load-bearing rejection** (scope/doctrine conflict, cost-benefit, architectural veto —
   never a bug), write `tasks/out-of-scope/<concept>.md`, one file per concept (append "Prior
   requests" to an existing file); template in the residue page.
5. Commit scoped, explicit-path: `git commit -m "debt-triage: reviewed N items, closed M, N
   remain open" -- <every touched path>`.

## Step 6b: Consume the improvement leg's hand-back

Runs over both emitted legs' APM-dispositioned hand-back (Step 5 item 5), after the runs; a
debt-leg `cross-repo` hand-back follows Step 2's memo-then-close route.

- `baton`: cluster per `coordinator/docs/wiki/ceremony-calibration/queue-terminus-doctrine.md`
  § Clustering, then mint solo or themed batons to
  `coordinator/docs/wiki/baton-lifecycle/baton-authoring-bar.md`'s bar; no second gate. Stamp
  `initiative` on a themed baton and its member rows; scaffold with `coordinator-doc-new`. Close
  each source row.
- `route-to-learn-lessons`: `coordinator-lesson-promote` once per row (flags and evidence rules:
  residue page § Lesson-promote recipe), then close the source row with `closed_by` = the settling
  commit sha. Promote only rows later runs hand back; a hand-back awaiting `reconcile-343` stays
  open and unpromoted, reported by count as "awaiting reconcile-343," never closed or presented to
  the PM. A row whose change_kind the outbox enum refuses (exit 2) is left open and reported.
- Park, won't-do and YAGNI keep their current rules and stamps, after Step 5.
- Source-row closure is an edit plus a plain rename to `archive/improvement-queue/<YYYY-MM>/`,
  the committer staging both paths.

**Commit shape:** batons, promotes and PM-gated closures are separate commits, each naming the
source ids; each hand closure is followed by `backlog-grind-assemble grind-row sweep`. Skip this
step if no project-specific entries survived Step 5.

## Autonomous runs

No PM is present. The APM's ruling is written as in Step 5 — `pm_ruling: "apm (PM-delegated) ..."`,
never as the PM's own word. For each row:

1. Act on a ruling only where this skill already permits EM-autonomous action (closing a
   verified-resolved row, Step 2's `cross-repo` memo-then-close, re-prioritizing).
2. A `pm_only` matter gets `apm_recommendation` on the row and stays open.
3. Continue; a pending recommendation never stops the run.

End with ONE batched PM-confirmation list: each row with an unconfirmed `apm_recommendation` as
row id, recommendation, one-line reason. The PM's confirmation writes `pm_ruling` (no
`(PM-delegated)` label) for Step 6b.
