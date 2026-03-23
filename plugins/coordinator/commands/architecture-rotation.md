---
description: Run the weekly architecture audit rotation — score systems, audit the highest-priority target, apply findings, and update the health ledger
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[system-name]"
---

# Architecture Rotation — Weekly System Audit

Selects the highest-priority system from the health ledger using a weighted rotation formula, dispatches domain reviewers against it, applies inline fixes, and updates the health ledger and atlas. Implements the weekly architecture audit pipeline as an invocable command.

Run this when the session-start prompt surfaces "Last full audit >7 days" or any time you want a targeted system review. When `$ARGUMENTS` names a system explicitly, that system is audited directly — skipping the rotation score calculation. Useful for targeted re-audits or when PM intuition overrides the formula.

**Announce at start:** _"I'm using /architecture-rotation to audit [system name]."_

---

## Arguments

`$ARGUMENTS` (optional) — name of the system to audit directly, e.g., `save-system` or `ui-core`.

- **Provided:** skip Step 1 score calculation; audit that system directly.
- **Omitted:** run Step 1 to calculate the rotation target from the health ledger.

---

## Step 1: Calculate Rotation Target

**Prerequisite check:** If `tasks/health-ledger.md` does NOT exist AND `tasks/architecture-atlas/systems-index.md` does NOT exist:

> _"No baseline exists. Run `/architecture-audit` first to bootstrap the atlas and health ledger."_

Stop here.

If a health ledger exists but no atlas, proceed normally — this audit predates the atlas feature.

**Atlas directory structure:**
```
tasks/architecture-atlas/
├── systems-index.md          # System inventory with grades and metadata
├── file-index.md             # File-to-system mapping (one line per file)
├── cross-system-map.md       # ASCII dependency diagram
├── connectivity-matrix.md    # System-to-system connection matrix
└── systems/                  # Per-system detail pages
    └── {system-name}.md      # Function inventory, flows, boundaries
```

**If `$ARGUMENTS` was provided:** skip score calculation; jump to Step 2 with that system as the target.

**Otherwise:** Read `tasks/health-ledger.md`. For each system in the index, calculate:

| Signal | Weight |
|--------|--------|
| CRITICAL status or open P0 | +15 |
| Never audited | +10 |
| >30 days since last audit | +5 |
| >14 days since last audit | +2 |
| Open P1 items | +3 each |
| Significant growth since last audit | +3 |
| Security-sensitive system | +2 |

Select the highest-scoring system. Report: _"Rotation target: [system] (score: N). Rationale: [top signals]."_

Note: These weights are initial estimates — adjust after 4 weeks based on whether rotation targets match intuition.

---

## Step 2: Review Existing Debt

Read `tasks/debt-backlog.md` for the target system. If open items exist:

1. Present them to PM for prioritization — before auditing for new issues
2. Prioritized debt items go through the full pipeline: plan → review → execute
3. This happens before or alongside the audit, not inline

---

## Step 2.5: Load Atlas Context

Check for `tasks/architecture-atlas/systems/{target-system}.md`.

- **Exists:** Include the atlas page in the reviewer's dispatch prompt as background context. This gives the reviewer structural knowledge (function inventory, flow diagrams, boundary catalog) so they focus on changes and quality assessment rather than rediscovery.
- **Does not exist:** Proceed without atlas context. Reviewer discovers the system from scratch.

---

## Step 3: Dispatch System Review (Size-Gated)

Check the system's **live file count** at dispatch time. Do not use the atlas file count — systems may have grown since discovery.

### Systems ≤10 files — Direct Opus Dispatch

1. Identify the system's domain:
   - Game dev / Unreal → Sid
   - Frontend / UI → Palí
   - ML / data → Camelia
   - Other / architecture → Patrik
2. Dispatch the domain reviewer with full system scope — all files in the system. Include the atlas page as context (per Step 2.5).
3. Reviewer grades the system and adds/updates the grade on the atlas page.
4. Backstop is mandatory: Patrik for domain reviewers (Sid/Palí/Camelia), Zolí for Patrik. Run backstop after applying domain reviewer findings.

### Systems >10 files — Haiku→Sonnet Pre-Digestion

0. **Generate run ID** — format: `YYYY-MM-DD-HHhMM`. Scratch directory: `tasks/scratch/weekly-architecture-audit/{run-id}/`

1. **Sub-chunk** the system into groups of 8-12 files, organized by concern (not alphabetical — group by what the files do together).

2. **Dispatch Haiku inventory agents (parallel)** — one per sub-chunk. Use the **Phase 1: Haiku Function-Level Inventory Prompt** from `~/.claude/plugins/oduffy-custom/coordinator/pipelines/deep-architecture-audit/agent-prompts.md`. These agents catalog what exists — no analysis. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md` as `[SCRATCH_PATH]`. Instruct each agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

   **Scratch verification:** Before dispatching Sonnet, verify all expected Haiku scratch files exist. Re-dispatch once on failure; skip that sub-chunk on second failure.

3. **Dispatch Sonnet analysis agents (parallel)** — one per system — reads ALL Haiku sub-chunk inventories from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase1-haiku.md`. Use the **Phase 2: Sonnet System Analysis Prompt (Audit variant, with grading)** from `~/.claude/plugins/oduffy-custom/coordinator/pipelines/deep-architecture-audit/agent-prompts.md`. Include the existing atlas page as context so Sonnet focuses on changes and quality assessment, not rediscovery. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md` as `[SCRATCH_PATH]`. Instruct each agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

   **Scratch verification:** Before dispatching Opus reviewer, verify Sonnet scratch files exist. Re-dispatch once on failure.

4. **Dispatch domain reviewer (Opus)** with summarized Sonnet findings (read from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase2-sonnet.md`). The reviewer brings judgment and cross-cutting insight — do NOT send raw files to the domain reviewer.

5. Reviewer grades the system and adds/updates the grade on the atlas page.

6. Backstop receives summarized Sonnet findings, not raw files. Backstop is mandatory: Patrik for domain reviewers, Zolí for Patrik.

---

## Step 4: Apply Inline Fixes

Route reviewer findings through the review-integrator:

- **Minor, mechanical findings** (naming, formatting, small corrections): apply inline
- **Structural, architectural findings** (refactors, module moves, interface changes): convert to debt backlog entries

The review-integrator's complexity threshold handles the triage automatically.

---

## Step 5: Update Debt Backlog

For findings that represent real debt, add entries to `tasks/debt-backlog.md`:

- **ID:** `WAA-{date}-{N}` (Weekly Architecture Audit prefix)
- **Source:** `weekly-audit/{reviewer}/{date}`
- **Status:** `open`

These go to PM for triage, then through the pipeline if prioritized.

**Concurrency note:** `debt-backlog.md` may be written by overlapping sessions (e.g., `/code-health` running concurrently). Always append new rows at the bottom of the table — never rewrite or reorganize existing rows. When updating an entry's status, match by ID column only. Update the `> Last triaged:` header line to today's date; do not remove or reorder any other header fields.

**Backlog overflow nag:** If the backlog exceeds 20 open items, say: _"Debt backlog has N open items (threshold: 20). Recommend running debt-triage before adding more."_

---

## Step 6: Update Health Ledger

1. Update the system's row: new grade, status, audit date, open issue counts
2. Update `Last full audit` date in the header
3. Calculate the next rotation target and update `Next rotation target` in the header
4. Commit:
   ```bash
   git add tasks/health-ledger.md tasks/debt-backlog.md
   git commit -m "weekly-audit: [system] audited, grade [X]→[Y]"
   ```

---

## Step 6.5: Update Atlas Page

If `tasks/architecture-atlas/systems/{target-system}.md` exists, patch it mechanically based on reviewer findings:

1. Add/remove functions mentioned in review findings
2. Update boundary entries if cross-system connections changed
3. Bump `last_mapped` date in the YAML frontmatter
4. Add `grade: [A-F]` and `health_status: [HEALTHY|WATCH|ACTION|CRITICAL]` fields to the YAML frontmatter, after the `dependencies` field

This is incremental maintenance — only update what the review explicitly found changed. If no atlas page exists, skip.

---

## Step 6.75: Triage Scratch Files

If the large-systems path was used (>10 files), delete all scratch files — Haiku/Sonnet output was fully consumed by the Opus reviewer:

```bash
rm -rf tasks/scratch/weekly-architecture-audit/{run-id}/
```

---

## Step 7: Report

```markdown
## Weekly Architecture Audit Complete

**System:** [name]
**Reviewer:** [name] at High effort (backstop: [name])
**Previous grade:** [X] | **New grade:** [Y]
**Findings:** N total (X applied inline, Y added to debt backlog)
**Next rotation target:** [system] (score: N)
```

---

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| No health ledger and no atlas | Fresh repo with no baseline | Run `/architecture-audit` first |
| Dispatching Opus reviewer with >10 files | Skipped size gate | Sub-chunk the system; use Haiku→Sonnet pre-digestion before Opus reviewer |
| Opus agent 529 overload | System too large for direct dispatch | Sub-chunk into 8-12 file groups; Haiku and Sonnet handle file reading |
| Sonnet findings lack depth | Sub-chunks too large (>12 files each) | Re-partition into smaller chunks; Sonnet performs better with focused scope |
| Reviewer misses structural detail the atlas has | Atlas page not included in Sonnet dispatch | Always include the atlas page in the Sonnet agent prompt as background context |

---

## Cost

**Small systems (≤10 files):** 1-2 Opus dispatches (reviewer + backstop) + review-integrator for inline fixes.

**Large systems (>10 files):** Haiku inventory agents (parallel, one per 8-12 file sub-chunk) + Sonnet analysis agents (parallel, one per sub-chunk) + 1-2 Opus dispatches (domain reviewer + backstop). Haiku and Sonnet costs are low; the Opus reviewer still dominates the total. Debt items are separate pipeline runs regardless of system size.

---

## Relationship to Other Commands

- **`/architecture-audit`** — the full deep-audit command that bootstraps the atlas and health ledger. Run this first on a new project before running `/architecture-rotation`.
- **`/review-dispatch`** — routes a single artifact through a reviewer. `/architecture-rotation` orchestrates the full rotation loop including review, inline fixes, debt tracking, and ledger updates — it is not a thin wrapper around `/review-dispatch`.
- **`pipelines/weekly-architecture-audit/PIPELINE.md`** — the pipeline definition this command executes. Contains the authoritative process specification; this command is the invocable surface for it.
- **`/architecture-audit`** — full system discovery and atlas construction. Use it when the atlas is stale or a system is entirely undocumented.
