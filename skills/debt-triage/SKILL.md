---
name: debt-triage
description: "EM-PM ceremony to review and prioritize the technical debt backlog."
version: 1.0.0
---

<!-- Schema: state/debt-backlog/*.yaml (YAML per entry); closure via git mv to archive/debt-backlog/<YYYY-MM>/. -->

# Debt Triage — Backlog Review and Prioritization

## Overview

Review the debt backlog, verify items are still relevant, re-prioritize based on current state, close resolved items, and present recommendations to the PM.

**Announce at start:** "I'm using the coordinator:debt-triage skill to review the debt backlog."

The read half of this skill is computed. Run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" brief debt-triage`
before Step 1 — it returns a decision object over `state/debt-backlog/`, `state/bug-backlog/`, and
`state/improvement-queue/`, packaged as one batched judgment point mirroring Step 5's own gate. No
mutation directive ships yet for this cadence (the debt-backlog terminus op doesn't exist on disk)
— Steps 2, 3, 6, and 6b below stay EM-performed until it does.

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

The assembler `brief` (see § Overview) returns: open `debt-backlog` items with a severity
breakdown; open `bug-backlog` items cross-referenced against them on an **exact** `surface`-field
match; open `improvement-queue` items; and clustering evidence for the latter (§ Clustering,
Step 6b). Exact-`surface` overlap is the mechanical subset of Step 1b's cross-reference — broader
file-path/description-similarity overlap stays an EM judgment pass over the same evidence, applied
before presenting overlaps to the PM for a deduplication decision (populate `evidence:` on both
YAML entries, e.g. `evidence: ["BS-2026-03-18-1"]`).

### Pre-Dispatch: Verify Backlog Against Current Code

Before dispatching any Haiku verification agents, do a quick staleness pre-check on the full item
list: for each `state/debt-backlog/` item, `git log --since="<finding-date>" -- <file-path>`
(`created` field) — a non-empty result is a candidate for `already-fixed` status, confirm before
dispatch. This stays an EM-side check (a per-item history walk doesn't belong on the assembler's
hot path); it isn't reproduced by `brief`.

### Step 1c: Analyst brief — structural probes

When evaluating whether a debt item or proposed enhancement is worth acting on, the debt-triage analyst may apply two concrete structural probes:

**Deletion test.** Imagine deleting the module, class, or abstraction in question. If complexity vanishes (callers simplify, the code reads more directly), the abstraction was a pass-through — it was not earning its keep. If complexity reappears across N callers (each must now handle what the module was hiding), the abstraction was load-bearing. Use this as a single-sentence verdict: "Deletion test: complexity would [vanish / reappear at N callers]."

**One-adapter / two-adapter rule.** One adapter is a hypothetical seam. Two adapters is a real seam that pays its abstraction cost. A single adapter wrapping one concrete implementation is usually premature — the deletion test confirms this. Two independent adapters in production justify the interface.

These probes apply when evaluating YAGNI calls, scope-change proposals, and deepening candidates. Pair any deletion-test finding with the convergence rule (≥2 independent agents before acting on a "shallow module" verdict) — single-agent subjective verdicts have elevated false-positive rates.

### Step 1d: Read Improvement Queue

The assembler `brief` also surfaces every open `state/improvement-queue/` entry as evidence (if
the directory is absent or empty, it reports so). Classifying each entry's scope is EM judgment,
not a disk predicate:

- **Universal** — would apply if a different project type used the coordinator pipeline? → routing note: _"should be in lessons-outbox — surface to next `/learn-lessons` local run."_ Do NOT pull these into the debt triage path; flag them for the EM to route at the end of this session.
- **Project-specific** — structural or implementation debt scoped to this repo → flow into the standard triage path alongside `state/debt-backlog/` entries. These terminate in a baton (solo/themed/immediate-dispatch/close-or-park) at Step 6b — not a migration into `state/debt-backlog/`.

Present the classification summary to the PM before proceeding:
> "Improvement queue: N entries total — M universal (flagged for lessons-outbox routing), K project-specific (flowing into triage)."

**Doctrine refs:** `CLAUDE.md § Improvement Queue` (admission rule + routing contract).

### Step 2: Verify Relevance (Haiku agents)

**Dispatch Haiku agents** to verify each open item against the current code — mechanical read-and-confirm, grouped by system. Each agent: checks `git log --since="<finding-date>" -- <file-path>` for changes since the finding was logged, reads the cited `file:line` to confirm the issue still exists, and returns a verdict — `still-open` / `already-fixed` / `partially-addressed`.

The coordinator then categorizes:
- Items the Haiku marked `already-fixed`: mark as `no-longer-applicable`
- Items marked `still-open`: item remains open
- Items marked `partially-addressed`: update the description based on Haiku's report

**Why Haiku:** 12 of 16 items in one prior triage were already fixed. Haiku verification costs minutes; dispatching Sonnet executors on ghost debt costs significantly more.

### Step 3: Re-Prioritize

Based on current state:
- Items blocking other work → escalate to P0
- Items in systems with grade D/F → escalate to P1
- Items in systems recently audited as A/B → may deprioritize to P2
- Items >30 days old with no activity → flag for PM attention

### Step 3b: LoE-weighted hot-zone identification

Before grouping items, query the completion log for historical `nature: tech-debt` entries via
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions"
--where "nature=tech-debt" --since "90d" --sort "-loe.tshirt" --format markdown-list`, to surface
which areas have consumed significant effort recently versus which have been avoided.

Interpret with two lenses:

- **High-LoE areas (L/XL entries in last 90d):** Repeated large tech-debt sessions in the same subsystem indicate festering complexity — the root cause was not resolved, only managed. Escalate any open backlog items in this area.
- **Zero-activity areas:** Backlog items citing a subsystem with no recent `nature: tech-debt` completions may reflect avoidance. Flag for PM attention: "We have carried this debt for N days without touching it — is that intentional?"

Present a one-paragraph hot-zone summary to the PM before the Step 4 grouping. Zero-row rendering: `(no tech-debt completions logged in last 90d — hot-zone analysis unavailable)`, proceed without escalating.

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
5. Disposition of surviving project-specific improvement-queue entries (Step 1d) under the
   four queue-terminus outcome classes — solo baton / themed baton / immediate dispatch /
   close-or-park (defined in full at Step 6b below). Present the candidate list
   (proposed class per entry, proposed clusters for themed-baton candidates, per § Clustering
   below) here; Step 6b writes only after this authorization. This is the terminus's PM gate —
   Step 6b does not introduce a second one (DEC-7).

### Step 6: Update Backlog

After PM decisions:
1. Close resolved items: for each item to close, stamp `status: closed`, `closed_at: <ISO date>`, and `closed_by: <commit-sha>` in the entry's YAML frontmatter, then archive it — create the dated archive directory (`mkdir -p archive/debt-backlog/<YYYY-MM>`) and move the entry into it (`git mv state/debt-backlog/<id>.yaml archive/debt-backlog/<YYYY-MM>/<id>.yaml`).
   Do NOT `rmdir state/debt-backlog/` even if it becomes empty — the queue directory MUST NOT
   be deleted.
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

5. Commit — scoped, explicit-path (`git commit -m "debt-triage: reviewed N items, closed M, N
   remain open" -- <every touched path>`), per `docs/wiki/scoped-safety-commits.md § Unambiguous-command-class PreToolUse blocks skip the Phase-5 soak gate`.

### Step 6b: Terminate surviving improvement-queue entries in work-units, not row moves

Project-specific `state/improvement-queue/` entries from Step 1d that survived Step 5 (not
closed, not YAGNI'd) do **not** migrate into `state/debt-backlog/` as a default disposition —
that migration-terminus shape is retired — the debt-backlog migration was never independently
reasoned; it was simply the path of least resistance, not a considered decision, so retiring it
reverses nothing. They terminate in exactly one of the four outcome classes enumerated below.
**This step performs the write the PM already authorized at Step 5 item 5 —
it does not add a second gate (DEC-7).**

<!-- Negative-spec: no fallthrough. Every surviving entry lands in exactly one of the four
     classes below. An entry with no clear class is not evidence for a fifth disposition —
     Step 5's classification isn't finished; return to Step 5, don't invent a sink here. -->

**Clustering, ahead of the Step 5 presentation.** The assembler's `brief` clusters surviving
project-specific improvement-queue entries before Step 5 is presented (`MIN_CLUSTER_SIZE=3`)
and folds the result into Step 5's batched judgment point as evidence. The clustering mechanism
itself degrades in order: (1) a registered engine op, once the claude-klabauter-side op work lands; (2) the
shipped `detect-initiative-candidates` CLI in `claude-klabauter`, invoked directly; (3) EM judgment,
only if the CLI itself is unreachable — the fallback of last resort, not the default degrade
target. A terminus must never carry the clustering algorithm itself as inline prose. The only
project-local tuning retained here: the
`directory` signal is suppressed (on a single-project-queue corpus it returns one cluster
containing everything, structurally useless for triage). The detector proposes, the EM disposes:
expect roughly half the proposed clusters to be noise (a shared keyword, not a shared thesis) —
split, merge, or discard each by judgment before presenting the Step 5 candidate list — see the
themed-baton delta named under class 2 below.

1. **Solo baton** — an entry large enough to justify its own pickup, alone. Scaffold via
   `coordinator-doc-new`, hand-editing the emitted frontmatter to `category: queue-derived-baton`.
   Author the body from the source entry's own context — a scaffolded placeholder is not a baton. Close
   the source `state/improvement-queue/<id>.yaml` (`status: closed`, `closed_at:`,
   `closed_by: <baton-path>`) and archive it via the same `git mv` mechanics as Step 6, with
   an explicit-path `git add`.
2. **Themed baton** — a cluster of N entries sharing a genuine thesis, not merely a detector
   keyword (see the clustering note above). Author the baton's multi-item delta: the shared
   thesis, why these belong together, the picker-up's first move, and every constituent row's
   id/path. Bound by the existing bundling threshold (≤30 authoring-lines per
   item) — do not invent a second threshold. On graduation, write the theme as an
   `initiative` value on the baton and on every constituent row (bidirectionally, so the theme
   is traceable both from a row to the baton it graduated into and from the baton back to every
   row it summarizes) — this is the only point in
   this step that writes `initiative`, and only for graduated clusters, never as a bulk pass.
   Scaffold and close the constituent source entries as in class 1.
3. **Immediate dispatch** — resolvable now, during this triage session. Apply the terminus
   discriminator (adopted verbatim from
   `coordinator/skills/architecture-audit/SKILL.md:196`, PM ruling D5): eligible only if the
   fix is BOTH tradeoff-free AND non-structural (touches no module boundary) — anything else,
   however small, is a baton (class 1 or 2), never an in-triage edit. Fire a Sonnet executor
   now; close the source entry once the fix lands, with `closed_by` referencing the fix
   commit.
4. **Close, or explicit park** — won't-do entries close via the same mechanics as Step 6
   (`status: closed`, archived). A deliberate park to the holding tier
   (`state/debt-backlog/`) is a distinct, named disposition, never a default sink for
   entries triage didn't reach: stamp `status: deferred` with a mandatory `why_blocked`
   field (never `open`) and capture
   via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema debt-backlog`. The park decision is covered by this
   step's own PM gate (Step 5 item 5) and needs no separate PM authorization.

Universal entries flagged in Step 1d are NOT part of this disposition — they stay in
`state/improvement-queue/` until the EM routes them via `/learn-lessons` local run.

**Commit shape.** Commit class-1/2 baton writes, class-3 executor fixes, and class-4
closures/parks separately from Step 6's closure commit — do not bundle. For each source
entry archived out of `state/improvement-queue/` under this step, mirror Step 6's archive
mechanics (create the dated `archive/improvement-queue/<YYYY-MM>/` directory, `git mv` the
source file into it — never `rmdir state/improvement-queue/` even if it empties, per the
"MUST NOT be deleted" rule that applies to every
structured queue directory, not only `debt-backlog/`) with an explicit-path `git add -- <archived-path> <baton-or-park-path>`
per `docs/wiki/scoped-safety-commits.md § Unambiguous-command-class PreToolUse blocks skip the Phase-5 soak gate`, naming every touched file. Name the source id and the
outcome class it landed in in the commit message.

If no project-specific entries survived Step 5, skip this step entirely.

## Notes

- The EM triages severity; only the PM removes items (YAGNI call)
- Items verified as no-longer-applicable can be closed by EM without PM approval
- This skill produces no code changes — it's a backlog management activity
