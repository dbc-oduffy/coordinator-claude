---
name: debt-triage
description: "Use when the technical debt backlog needs review and prioritization, on demand, or when the backlog exceeds 20 open items. This is an EM-PM conversation, not a dispatched agent — the EM reads the backlog, applies judgment, and presents recommendations. Note: weekly-architecture-audit will increasingly insist as the count grows — mild concern at >20, visible disappointment at >30, and a full coffee-down stare-down at >40."
version: 1.0.0
---

# Debt Triage — Backlog Review and Prioritization

## Overview

Review the debt backlog, verify items are still relevant, re-prioritize based on current state, close resolved items, and present recommendations to the PM.

**Announce at start:** "I'm using the coordinator:debt-triage skill to review the debt backlog."

## When to Trigger

- On demand (PM or EM invocation)
- When debt backlog exceeds 20 open items (surfaced by weekly-architecture-audit with escalating insistence — mild concern at >20, visible Patrik disappointment at >30, coffee-down intervention at >40 — and by session-start)
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

1. Read `tasks/debt-backlog.md`
2. Summarize: total open items, breakdown by severity (P0/P1/P2), breakdown by system
3. Identify the oldest open items (stalest debt)

### Step 1b: Cross-reference bug backlog

Also read `tasks/bug-backlog.md` (if it exists). Flag any BS-* entries that overlap with open DCH-*/WAA-* items by file path or description similarity. When overlap is found, populate the `Cross-ref` field on both entries (e.g., `Cross-ref: BS-2026-03-18-1` on the debt item, `Cross-ref: WAA-2026-03-19-1` on the bug item). Present overlaps to PM for deduplication decision.

### Pre-Dispatch: Verify Backlog Against Current Code (geneva T1.1, single landing across 3 files)

Before dispatching any Haiku verification agents, do a quick staleness pre-check on the full item list.

For each item in `tasks/debt-backlog.md`, note its cited file path and the date it was logged. Items where `git log --since="<finding-date>" -- <file-path>` shows relevant commits are candidates for `already-fixed` status and should be confirmed first.

This pre-check prevents dispatching agents to verify debt that has already been resolved. In one measured run, 11 of 20 backlog items were already fixed before dispatch — the same failure mode applies to debt backlogs that drift behind active development.

**Why pre-dispatch rather than during Step 2:** Step 2 Haiku agents do the full per-line verification; this pre-check is the EM's own lightweight scan (date + git log) that prunes obviously-stale items before agent dispatch, reducing cost.

### Step 1c: Analyst brief — structural probes

When evaluating whether a debt item or proposed enhancement is worth acting on, the debt-triage analyst may apply two concrete structural probes:

**Deletion test.** Imagine deleting the module, class, or abstraction in question. If complexity vanishes (callers simplify, the code reads more directly), the abstraction was a pass-through — it was not earning its keep. If complexity reappears across N callers (each must now handle what the module was hiding), the abstraction was load-bearing. Use this as a single-sentence verdict: "Deletion test: complexity would [vanish / reappear at N callers]."

**One-adapter / two-adapter rule.** One adapter is a hypothetical seam. Two adapters is a real seam that pays its abstraction cost. A single adapter wrapping one concrete implementation is usually premature — the deletion test confirms this. Two independent adapters in production justify the interface.

These probes apply when evaluating YAGNI calls, scope-change proposals, and deepening candidates. Pair any deletion-test finding with the convergence rule (≥2 independent agents before acting on a "shallow module" verdict) — single-agent subjective verdicts have elevated false-positive rates.

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
1. Close resolved items (status: `closed — [reason]`)
2. Update priorities per PM direction
3. Remove items PM declares YAGNI
4. Update header counts
5. For any item rejected with a **load-bearing reason** (scope conflict, doctrine conflict, cost-benefit rejection, architectural veto): write `tasks/out-of-scope/<concept>.md` using the template below. One file per *concept*, not per item — if a matching file already exists, append a new entry under "Prior requests" instead of creating a duplicate. **Bugs do NOT go to `.out-of-scope/`** — only enhancement rejections. Create the directory on first use; never scaffold it empty.

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

6. Commit:
   ```bash
   git add tasks/debt-backlog.md tasks/out-of-scope/
   git commit -m "debt-triage: reviewed N items, closed M, N remain open"
   ```

## Notes

- The EM triages severity; only the PM removes items (YAGNI call)
- Items verified as no-longer-applicable can be closed by EM without PM approval
- This skill produces no code changes — it's a backlog management activity
