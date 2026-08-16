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

Run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" brief debt-triage`
before Step 1 — it returns a decision object over `state/debt-backlog/`, `state/bug-backlog/`,
and `state/improvement-queue/`: open items with severity breakdown, `bug-backlog`
cross-reference (exact `surface`-field match), improvement-queue entries with clustering
evidence, and a batched PM-gate. Steps 2, 3, 6, and 6b below stay EM-performed until the
debt-backlog terminus op ships.

## Step 0: Surface prior rejections

Check `tasks/out-of-scope/*.md` (skip silently if absent). For any concept overlapping the
triage, surface: *"This is similar to `tasks/out-of-scope/<concept>.md` — we rejected this
because [reason]. Still feel the same?"* — confirm, reconsider (delete the file), or override.

## Step 1: Read current state

Take the `brief` output as-is. Broader file-path/description-similarity overlap beyond the
`surface`-field match stays an EM judgment pass over the same evidence, applied before
presenting overlaps to the PM for a dedup decision (populate `evidence:` on both entries).

**Improvement-queue classification** (also from `brief`) is EM judgment, not a disk predicate:
- **Universal** — would apply to any coordinator-pipeline project → flag for `/learn-lessons`
  local-run routing; do NOT pull into the triage path.
- **Project-specific** — flows into the standard triage path, terminating in a Step 6b baton
  (never a migration into `state/debt-backlog/` — that disposition is retired).

Present: *"Improvement queue: N entries — M universal (flagged for lessons-outbox), K
project-specific (flowing into triage)."* Doctrine ref: `CLAUDE.md § Improvement Queue`.

## Step 2: Verify relevance (Haiku agents)

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
(`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --where
"nature=tech-debt" --since "90d" --sort "-loe.tshirt" --format markdown-list`) before grouping:
high-LoE areas in the last 90d indicate festering complexity — escalate open items there.
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
every surviving project-specific improvement-queue entry (Step 1) under the four Step 6b classes
— present the candidate list (class, clusters per the `brief`'s clustering evidence) here; Step
6b writes only after this authorization and does not gate a second time.

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

## Step 6b: Terminate surviving improvement-queue entries

A surviving project-specific entry (not closed, not YAGNI'd) lands in exactly one of four
classes — never a fifth, never a fallthrough; an unclear entry means Step 5's classification
isn't finished, return there. This step performs the write Step 5 item 5 already authorized —
it is not a second gate.

The `brief`'s clustering (`MIN_CLUSTER_SIZE=3`, `directory` signal suppressed) degrades to EM
judgment as a last resort only. Expect roughly half the proposed clusters to be noise —
split/merge/discard by judgment before Step 5. Degrade-order detail: wiki.

1. **Solo baton** — large enough to stand alone. Scaffold via `coordinator-doc-new`,
   `category: queue-derived-baton`, body authored from the source entry's own context. Close
   and archive the source entry (`git mv`, as Step 6).
2. **Themed baton** — N entries sharing a genuine thesis (not a shared keyword). Author the
   shared thesis, why they belong together, the picker-up's first move, every constituent
   id/path. ≤30 authoring-lines/item. Write `initiative` on the baton and every constituent row,
   bidirectionally, only on graduation. Close/archive constituents as class 1.
3. **Immediate dispatch** — resolvable now, in-session. Eligible only if the fix is BOTH
   tradeoff-free AND non-structural (touches no module boundary); anything else is a baton
   (class 1/2) regardless of size. Fire a Sonnet executor now; close the source entry with
   `closed_by` referencing the fix commit.
4. **Close, or explicit park** — won't-do closes as Step 6. A deliberate park to
   `state/debt-backlog/` is a distinct disposition (never a default sink for triage-didn't-reach
   entries): `status: deferred` with a mandatory `why_blocked` field (never `open`), via
   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema debt-backlog`.

Universal entries (Step 1) are not part of this disposition — they stay in
`state/improvement-queue/` until routed via `/learn-lessons`.

**Commit shape:** commit class-1/2 baton writes, class-3 fixes, and class-4 closures/parks
separately from Step 6's closure commit. Mirror Step 6's archive mechanics for each source entry
(`archive/improvement-queue/<YYYY-MM>/`, `git mv`, never `rmdir`), explicit-path `git add --
<archived-path> <baton-or-park-path>`, naming the source id and outcome class in the message.

Skip this step entirely if no project-specific entries survived Step 5.

## Notes

- The EM triages severity; only the PM removes items (YAGNI call).
- Items verified no-longer-applicable close without PM approval.
- This skill produces no code changes — it's a backlog management activity.
