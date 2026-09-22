---
name: debt-triage
description: "EM-PM ceremony to review and prioritize the technical debt backlog."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

<!-- Schema: state/debt-backlog/*.yaml (YAML per entry); closure via git mv to archive/debt-backlog/<YYYY-MM>/. -->

# Debt Triage — Backlog Review and Prioritization

**Announce at start:** "I'm using the coordinator:debt-triage skill to review the debt backlog."

An **EM-PM conversation**, not a dispatched agent — the EM reads the backlog, applies judgment,
and presents recommendations. Trigger on demand, at >20 open items, or after a refactor that may
have resolved several. Rationale, clustering detail, structural-probe calibration: wiki.

**On a PowerShell host, every CLI below takes its `.exe` launcher through the call operator**
(Shape W), never the `${...}` POSIX-shell form shown. Ladder and shapes:
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

Run
`backlog-grind-assemble brief debt-triage` (per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
before Step 1 — it returns, over `state/debt-backlog/`, `state/bug-backlog/`,
and `state/improvement-queue/`: open items with severity breakdown, `bug-backlog`
cross-reference (exact `surface`-field match), improvement-queue entries with clustering
evidence, and a batched PM-gate. The improvement leg is emitted (Step 1); the debt-backlog
steps (2, 3, 6, and 6b's debt-backlog governance) stay EM-performed.

## Step 0: Surface prior rejections

Check `tasks/out-of-scope/*.md` (skip silently if absent). For any concept overlapping the
triage, surface: *"This is similar to `tasks/out-of-scope/<concept>.md` — we rejected this
because [reason]. Still feel the same?"* — confirm, reconsider (delete the file), or override.

## Step 1: Read current state

Take the `brief` output as-is. Broader file-path/description-similarity overlap beyond the
`surface`-field match stays an EM judgment pass over the same evidence, applied before
presenting overlaps to the PM for a dedup decision (populate `evidence:` on both entries).

**Improvement-queue triage is emitted, not EM classification.** Pick an appetite (`hunt`,
`standard` or `sweep` — values in `coordinator/queue-profiles/improvement.yaml`). Emit with
`emit-dispatch-workflow.py --queue state/improvement-queue --profile improvement --appetite <a>
--out state/scratch/debt-triage/{run-id}/improvement.workflow.mjs`, per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. There is no commit-readiness gate
to resolve for this leg. Fire with `Workflow({scriptPath})`, never `--fire` — firing authorizes
the in-run fixes and closes and the post-run hand-back (`coordinator/docs/wiki/queue-terminus-doctrine.md`
§ Emitted-workflow triage). The run's triage is the only triage — the EM works Steps 2–4 on the
debt backlog while it runs. An emit refusal is reported, not routed around.

## Step 2: Verify relevance (Haiku agents)

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

Debt-backlog rows only (the improvement leg's triage runs inside Step 1's emitted grind).
Dispatch Haiku agents, grouped by system, to mechanically re-confirm each open item against
current code: history since the finding's `created` date, the cited `file:line` still shows the
issue. Verdict per item — `still-open` / `already-fixed` / `partially-addressed`.
<!-- engine-gap: field=debt_triage.haiku_verify_dispatch producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
`already-fixed` → mark `no-longer-applicable`; `partially-addressed` → update the description
from the Haiku report. Haiku, not Sonnet — rationale: wiki.

## Step 3: Re-prioritize

Blocking other work → P0. In a D/F-graded system → P1. In a recently A/B-graded system → may
deprioritize to P2. >30 days with no activity → flag for PM attention.

Query historical `nature: tech-debt` completions
(`query-completions --where "nature=tech-debt" --since "90d" --sort "-loe.agent_dispatches" --format markdown-list`,
per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
before grouping: high-LoE areas in the last 90d indicate festering complexity — escalate open
items there.

**Never sort on `loe.tshirt`.** `--sort` compares non-numeric values as STRINGS, so descending
t-shirt order is `XXL, XS, XL, S, M, L` — the smallest tier ranks second. Rank on a numeric field.
Zero-activity areas may reflect avoidance — flag: *"We have carried this debt for N days without
touching it — is that intentional?"* Present a one-paragraph summary before Step 4; zero-row
case: `(no tech-debt completions logged in last 90d — hot-zone analysis unavailable)`.

## Step 4: Group for execution

```markdown
## Triage Results
### Closed (no longer applicable): N items
| ID | Reason |
### Recommended for immediate action: N items
| ID | System | Severity | Description | Effort |
### Can defer: N items
| ID | System | Severity | Reason to defer |
### Needs PM decision (YAGNI/scope): N items
| ID | System | Description | Question |
```

## Step 5: Present to PM

Ask for: (1) approval to close no-longer-applicable items; (2) YAGNI/scope calls; (3)
prioritization of immediate-action items; (4) agreement on deferral reasoning; (5) disposition of
the improvement leg's PM-bound hand-back types (`park`, `wont-do`, `yagni`,
`unclear-direction`, `needs-judgment`) — Step 6b consumes them after this authorization and does
not gate a second time. Engine-originated hand-back types (`budget-exhausted`, `verify-failed`,
and the rest) are reported by count; their rows stay open and are not presented here.

## Step 6: Update backlog

After PM decisions:
1. Close resolved items — stamp `status: closed`, `closed_at:`, `closed_by: <sha>`, then
   `mkdir -p archive/debt-backlog/<YYYY-MM>` and `git mv` the entry in. Never `rmdir
   state/debt-backlog/` even if it empties.
2. Update `severity` per PM direction.
3. Remove YAGNI items the same way as (1), `closed_by` referencing the PM decision.
4. For a **load-bearing rejection** (scope/doctrine conflict, cost-benefit, architectural veto —
   never a bug), write `tasks/out-of-scope/<concept>.md`, one file per concept (append "Prior
   requests" to an existing file rather than duplicating):

   ```markdown
   # Out of scope: <concept>
   **First raised:** YYYY-MM-DD
   **Status:** Rejected (open to reconsideration)
   ## What was proposed
   ## Why we rejected it
   ## Prior requests
   - YYYY-MM-DD: [how this came up]
   ## What would change our minds
   ```
5. Commit scoped, explicit-path: `git commit -m "debt-triage: reviewed N items, closed M, N
   remain open" -- <every touched path>`.

## Step 6b: Consume the improvement leg's hand-back

Runs over the improvement leg's PM-gated hand-back (Step 5 item 5), after the run. This does not
touch Step 2's `Dispatch Haiku agents` text, a different step that stays unedited. Items 1-2 below
do not govern debt-backlog rows today (debt-backlog stays on the current 6b, unedited); if 6b is
ever applied to debt-backlog rows, that governance still applies.

- `baton`: cluster per `coordinator/docs/wiki/queue-terminus-doctrine.md` § Clustering, then mint
  solo or themed batons to `coordinator/docs/wiki/baton-authoring-bar.md`'s bar, carrying
  triage's sizing evidence. There is no second gate. Close each source row.
- `route-to-learn-lessons`: run `coordinator-lesson-promote` once per row with `--title-file` and
  `--body-file` (the row's title and body), `--change-kind` (the row's), `--target-wiki unknown`
  (no row carries a target), and `--evidence` naming the archive destination path the closing
  rename lands at (or the row stem), never the pre-rename row path, which goes stale the instant
  the row is archived. Then close the source row with `closed_by` set to the settling commit sha
  (the outbox path goes in the commit message, not `closed_by`).
  - The step promotes only rows that later runs hand back. The `reconcile-343` plan promotes the
    existing central backlog once, via its C1 classification (ratified) and C4 execution, which
    produces the per-row disposition (including which rows already promoted to
    `state/lessons-outbox/`).
    This step's promote gates on that classification's output or its landed C4 — never on the
    `queue_scope: central` tag, which is evidence, not the disposition. Until reconcile-343's
    classification or C4 has landed, a `route-to-learn-lessons` hand-back is left open, untouched
    and unpromoted — no central-tagged row is promoted here, full stop — and Step 5's run summary
    reports it by count as "awaiting reconcile-343," never closed or presented to the PM.
  - A row whose change_kind the outbox enum refuses (exit 2) is left open and reported. It is
    never coerced.
- Park, won't-do and YAGNI keep their current rules and stamps, after Step 5.
- Source-row closure is an edit plus a plain rename to `archive/improvement-queue/<YYYY-MM>/`,
  with the committer staging both paths (A-PLAIN-MV-IS-THE-INTENDED-ROUTE-NOT-A-FALLBACK). The
  row-removal `--declared-revert` follows doe-claude-47's `/bug-blitz` post-run wording, so the
  two termini read the same.

**Commit shape:** batons, promotes and PM-gated closures are separate commits, each naming the
source ids. The run committed its own fixes and closes. Every hand closure here is followed by
`grind-row sweep` (`coordinator/docs/wiki/queue-terminus-doctrine.md` § Emitted-workflow triage).

Skip this step entirely if no project-specific entries survived Step 5.
