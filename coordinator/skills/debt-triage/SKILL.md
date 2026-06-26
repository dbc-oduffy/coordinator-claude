---
name: debt-triage
description: "EM-PM conversation to review and prioritize the technical debt backlog. Triggers on demand or when open item count exceeds 20."
version: 1.0.0
---

<!-- Schema: state/debt-backlog/*.yaml (YAML per entry); closure via git mv to archive/debt-backlog/<YYYY-MM>/. The pre-C10 markdown table format is retired (swept by tc-2/C7). -->

# Debt Triage — Backlog Review and Prioritization

## Overview

Review the debt backlog, verify items are still relevant, re-prioritize based on current state, close resolved items, and present recommendations to the PM.

**Announce at start:** "I'm using the coordinator:debt-triage skill to review the debt backlog."

## When to Trigger

- On demand (PM or EM invocation)
- When debt backlog exceeds 20 open items (surfaced by weekly-architecture-audit with escalating insistence — mild concern at >20, visible the Staff Engineer disappointment at >30, coffee-down intervention at >40 — and by workstream-start)
- After a major refactor that may have resolved multiple debt items

## The Process

This is an **EM-PM conversation**, not a dispatched agent. The EM reads the backlog, applies judgment, and presents recommendations.

### Step 0: Surface Prior Rejections

Before reading the backlog, check `tasks/out-of-scope/*.md` (if the directory exists — skip silently if absent). For each file present, note the concept and rejection reason. During triage, when any incoming item or discussion overlaps a known rejection, surface it:

> "This is similar to `tasks/out-of-scope/<concept>.md` — we rejected this because [reason]. Still feel the same?"

The maintainer can:
- **Confirm** — append the new instance under "Prior requests" in the file
- **Reconsider** — delete the file and proceed to evaluate normally
- **Override** — proceed with implementation despite the prior rejection

### Step 1: Read Current State

1. Read `state/debt-backlog/` entries via `bin/query-records.js --type debt` (each entry is an individual YAML file with `severity`, `status`, and related frontmatter fields per `docs/wiki/debt-backlog-schema.md` — identity key is the filename `<date>-<slug>.yaml` — no `id:` field)
<!-- Review: code-reviewer slice-C F3/F7 — D2 dropped the id field (filename is the handle); fixed query-records extension .sh→.js -->
2. Summarize: total open items, breakdown by severity (P0/P1/P2), breakdown by system
3. Identify the oldest open items (stalest debt)

### Step 1b: Cross-reference bug backlog

Also read `state/bug-backlog/*.yaml` via `bin/query-records.js --type bug` (each entry is a YAML file with `severity`, `status`, etc. as frontmatter — identity key is the filename `<date>-<slug>.yaml` — no `id:` field).
<!-- Review: code-reviewer slice-C F3/F7 — D2 dropped the id field; fixed query-records extension .sh→.js --> Flag any BS-* entries that overlap with open DCH-*/WAA-* items by file path or description similarity. When overlap is found, populate the `evidence:` field on both entries (e.g., `evidence: ["BS-2026-03-18-1"]` on the debt YAML, `evidence: ["WAA-2026-03-19-1"]` on the bug YAML). Present overlaps to PM for deduplication decision.
<!-- Review: code-reviewer slice-C F2 — cross_ref: was tombstoned in D1 (renamed to evidence:); fixed instruction and both illustrative examples; BS-/WAA- handle values survive as prose strings in the evidence value per D2 -->

### Pre-Dispatch: Verify Backlog Against Current Code (geneva T1.1, single landing across 3 files)

Before dispatching any Haiku verification agents, do a quick staleness pre-check on the full item list.

For each item in `state/debt-backlog/`, note its cited file path and the date it was logged (`created` field in frontmatter). Items where `git log --since="<finding-date>" -- <file-path>` shows relevant commits are candidates for `already-fixed` status and should be confirmed first.

This pre-check prevents dispatching agents to verify debt that has already been resolved. In one measured run, 11 of 20 backlog items were already fixed before dispatch — the same failure mode applies to debt backlogs that drift behind active development.

**Why pre-dispatch rather than during Step 2:** Step 2 Haiku agents do the full per-line verification; this pre-check is the EM's own lightweight scan (date + git log) that prunes obviously-stale items before agent dispatch, reducing cost.

### Step 1c: Analyst brief — structural probes

When evaluating whether a debt item or proposed enhancement is worth acting on, the debt-triage analyst may apply two concrete structural probes:

**Deletion test.** Imagine deleting the module, class, or abstraction in question. If complexity vanishes (callers simplify, the code reads more directly), the abstraction was a pass-through — it was not earning its keep. If complexity reappears across N callers (each must now handle what the module was hiding), the abstraction was load-bearing. Use this as a single-sentence verdict: "Deletion test: complexity would [vanish / reappear at N callers]."

**One-adapter / two-adapter rule.** One adapter is a hypothetical seam. Two adapters is a real seam that pays its abstraction cost. A single adapter wrapping one concrete implementation is usually premature — the deletion test confirms this. Two independent adapters in production justify the interface.

These probes apply when evaluating YAGNI calls, scope-change proposals, and deepening candidates. Pair any deletion-test finding with the convergence rule (≥2 independent agents before acting on a "shallow module" verdict) — single-agent subjective verdicts have elevated false-positive rates.

### Step 1d: Read Improvement Queue

Also read `state/improvement-queue/` entries via `bin/query-records.js --type improvement`
<!-- Review: code-reviewer slice-C F7 — fixed query-records extension .sh→.js --> (if the directory exists — skip silently if absent). For each entry, classify scope:

- **Universal** — would apply if a different project type used the coordinator pipeline? → routing note: _"should be in lessons-outbox — surface to next `/learn-lessons` local run."_ Do NOT pull these into the debt triage path; flag them for the EM to route at the end of this session.
- **Project-specific** — structural or implementation debt scoped to this repo → flow into the standard triage path alongside `state/debt-backlog/` entries. These are candidates for migration to `state/debt-backlog/` at Step 6b.

Present the classification summary to the PM before proceeding:
> "Improvement queue: N entries total — M universal (flagged for lessons-outbox routing), K project-specific (flowing into triage)."

If the queue is absent or empty, note this and proceed without block.

**Doctrine refs:** `CLAUDE.md § Improvement Queue` (admission rule + routing contract); `docs/wiki/lessons-outbox-schema.md` (universal entry routing schema).

### Step 2: Verify Relevance (Haiku agents)

**Dispatch Haiku agents** to verify each open item against the current code. This is mechanical read-and-confirm work — no judgment needed. Group items by system for efficient dispatch (one Haiku per system).

Each Haiku agent receives a list of items for its system and:
1. Checks if the referenced code has changed since the finding was logged
   ```bash
   git log --since="<finding-date>" -- <file-path>
   ```
2. Reads the cited file:line to confirm the issue still exists
3. Returns a verdict per item: `still-open` / `already-fixed` / `partially-addressed`

The coordinator then categorizes:
- Items the Haiku marked `already-fixed`: mark as `no-longer-applicable`
- Items marked `still-open`: item remains open
- Items marked `partially-addressed`: update the description based on Haiku's report

**Why Haiku:** 12 of 16 items in the 2026-03-19 triage were already fixed. Haiku verification costs minutes; dispatching Sonnet executors on ghost debt costs significantly more.

### Step 3: Re-Prioritize

Based on current state:
- Items blocking other work → escalate to P0
- Items in systems with grade D/F → escalate to P1
- Items in systems recently audited as A/B → may deprioritize to P2
- Items >30 days old with no activity → flag for PM attention

### Step 3b: LoE-weighted hot-zone identification

Before grouping items, query the completion log for historical `nature: tech-debt` entries to surface which areas have consumed significant effort recently versus which have been avoided:

```bash
query-completions.sh --where "nature=tech-debt" --since "90d" --sort "-loe.tshirt" --format markdown-list
```

Interpret the output with two lenses:

- **High-LoE areas (L/XL entries in last 90d):** Repeated large tech-debt sessions in the same subsystem indicate festering complexity — the root cause was not resolved, only managed. Escalate any open backlog items in this area: they are likely blocking or near-blocking.
- **Zero-activity areas:** Backlog items that cite a subsystem with no recent `nature: tech-debt` completions may reflect avoidance. Flag these for PM attention: "We have carried this debt for N days without touching it — is that intentional?"

Present a one-paragraph hot-zone summary to the PM before the Step 4 grouping. Example framing:

> "The completion log shows three XL tech-debt sessions in `src/indexer/` over the last 90 days — that area is festering. Two open backlog items cite it; I'm escalating both. `src/cache/` has two open items but no recent debt sessions — possible avoidance."

**Zero-row rendering:** If the query returns no results (fresh repo or no tech-debt completions logged yet), render: `(no tech-debt completions logged in last 90d — hot-zone analysis unavailable)` and proceed without escalating.

### Step 4: Group for Execution

Group remaining items by system for efficient batch execution:

```markdown
## Triage Results

### Closed (no longer applicable): N items
| ID | Reason |
|----|--------|

### Recommended for immediate action: N items
| ID | System | Severity | Description | Effort |
|----|--------|----------|-------------|--------|

### Can defer: N items
| ID | System | Severity | Reason to defer |
|----|--------|----------|----------------|

### Needs PM decision (YAGNI/scope): N items
| ID | System | Description | Question |
|----|--------|-------------|----------|
```

### Step 5: Present to PM

Present the triage results and ask for:
1. Approval to close no-longer-applicable items
2. YAGNI/scope decisions on flagged items
3. Prioritization of immediate-action items
4. Agreement on deferral reasoning

### Step 6: Update Backlog

After PM decisions:
1. Close resolved items: for each item to close, stamp `status: closed`, `closed_at: <ISO date>`, and `closed_by: <commit-sha>` in the entry's YAML frontmatter, then archive it:
   ```bash
   # For each closed entry:
   mkdir -p archive/debt-backlog/<YYYY-MM>
   git mv state/debt-backlog/<id>.yaml archive/debt-backlog/<YYYY-MM>/<id>.yaml
   # After all archive moves, clean up an empty source dir if it becomes empty:
   rmdir state/debt-backlog/ 2>/dev/null || true
   ```
2. Update priorities per PM direction (edit `severity` field in the relevant YAML files)
3. Remove items PM declares YAGNI (archive via `git mv` as above, with `status: closed` and a `closed_by` referencing PM decision)
4. For any item rejected with a **load-bearing reason** (scope conflict, doctrine conflict, cost-benefit rejection, architectural veto): write `tasks/out-of-scope/<concept>.md` using the template below. One file per *concept*, not per item — if a matching file already exists, append a new entry under "Prior requests" instead of creating a duplicate. **Bugs do NOT go to `.out-of-scope/`** — only enhancement rejections. Create the directory on first use; never scaffold it empty.

   ```markdown
   # Out of scope: <concept>

   **First raised:** YYYY-MM-DD
   **Status:** Rejected (open to reconsideration)

   ## What was proposed
   [One sentence describing the enhancement.]

   ## Why we rejected it
   [Load-bearing reason. Cost, scope, doctrine conflict, etc.]

   ## Prior requests
   - YYYY-MM-DD: [Brief description of how this came up]

   ## What would change our minds
   [Conditions under which this should be reconsidered. Optional but useful.]
   ```

5. Commit:
   ```bash
   git add archive/debt-backlog/ state/debt-backlog/ tasks/out-of-scope/
   git commit -m "debt-triage: reviewed N items, closed M, N remain open"
   ```

### Step 6b: Migrate project-specific improvement-queue entries

After the Step 6 commit, migrate any project-specific entries identified in Step 1d from `state/improvement-queue/` into `state/debt-backlog/`:

1. For each project-specific entry from Step 1d that survived triage (not YAGNI'd):
   - Capture a new debt-backlog entry via `coordinator-queue-append --schema debt-backlog` (mechanical capture using the CLI — do not manually author YAML). The CLI writes a new `state/debt-backlog/<id>.yaml` file.
   - Close the source improvement-queue YAML by stamping `status: closed`, `closed_at: <ISO date>`, and `closed_by: <migrated-to-debt-backlog>` in its frontmatter, then archive via `git mv`:
     ```bash
     mkdir -p archive/improvement-queue/<YYYY-MM>
     git mv state/improvement-queue/<source-id>.yaml archive/improvement-queue/<YYYY-MM>/<source-id>.yaml
     rmdir state/improvement-queue/ 2>/dev/null || true
     ```
2. Commit the new debt-backlog entries and the improvement-queue archive moves in **two dedicated commits** (do not bundle with Step 6 closure commits):
   ```bash
   git add state/debt-backlog/
   git commit -m "debt-triage: migrate N improvement-queue entries to debt-backlog"
   git add archive/improvement-queue/ state/improvement-queue/
   git commit -m "debt-triage: archive migrated improvement-queue entries"
   ```
3. Universal entries flagged in Step 1d are NOT migrated to `state/debt-backlog/` — they stay in `state/improvement-queue/` until the EM routes them via `/learn-lessons` local run (see `docs/wiki/lessons-outbox-schema.md`). Only project-specific entries migrate.

If no project-specific entries were identified in Step 1d, skip this step entirely.

## Notes

- The EM triages severity; only the PM removes items (YAGNI call)
- Items verified as no-longer-applicable can be closed by EM without PM approval
- This skill produces no code changes — it's a backlog management activity
