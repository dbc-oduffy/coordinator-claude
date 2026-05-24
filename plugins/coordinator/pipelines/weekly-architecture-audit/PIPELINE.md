# Weekly Architecture Audit — Systematic System Rotation

> Referenced by `/architecture-audit`. This is a pipeline definition, not an invocable skill.

## Overview

Rotate through project systems ensuring complete coverage. Uses a weighted scoring formula to select the highest-priority audit target. **Discovers findings, never edits code** — findings are packaged as spinoff candidates down the EM disposition ladder (immediate executor for trivial+non-structural / bundled spinoff candidate / standalone-or-plan for large). Writes the `Last targeted audit` clock, not `Last full audit`.

**Announce at start:** "I'm using /architecture-audit to audit [system name]."

## When to Trigger

- Surfaced at session-start when `Last targeted audit` in health ledger is >10 days old
- Auto-folded by `/workweek-complete` Step 7.6 when `check-arch-audit-staleness.sh` returns STALE
- Available as maintenance menu option (Option 6 in session-start)
- Can be invoked directly any time

## The Process

### Step 1: Calculate Rotation Scores

**Prerequisite check:** If no health ledger exists (`tasks/health-ledger.md`) AND no atlas exists (`docs/architecture/systems-index.md`):

> _"No baseline exists. Use /architecture-survey first to bootstrap the atlas and health ledger."_

Stop here — the weekly audit needs a baseline to rotate through. If a health ledger exists but no atlas, proceed normally (the audit predates the atlas feature).

Read `tasks/health-ledger.md`. For each system in the index, calculate a rotation score:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| CRITICAL status or open P0 | +15 | Known-bad systems should never be deprioritized by staleness alone |
| Never audited | +10 | Unknown state is high risk — could be A or could be F |
| >30 days since audit | +5 | A month without inspection is too long for active code |
| >14 days since audit | +2 | Moderate staleness, adds up with other signals |
| Open P1 items | +3 each | Accumulated P1s compound — three P1s = one P0 in practice |
| Significant growth since last audit | +3 | New code = new risk, regardless of current grade |
| Security-sensitive system | +2 | Higher consequence of missed issues |

Select the system with the highest score. Report: _"Rotation target: [system] (score: N). Rationale: [top signals]."_

**Note:** These weights are initial estimates — adjust after 4 weeks based on whether rotation targets match intuition.

### Step 2: Review Existing Debt

Read `tasks/debt-backlog.md` for the target system. If open items exist:

1. **Present them to PM for prioritization first** — before auditing for new issues
2. Prioritized debt items go through the full pipeline: plan → review → execute
3. This happens before or alongside the audit, not inline with it

### Step 2.5: Load Atlas Context

Before dispatching the reviewer, check for atlas context on the target system:

1. Check for `docs/architecture/systems/{target-system}.md`
2. **If it exists:** Include the atlas page content in the reviewer's dispatch prompt as background context. This gives the reviewer structural knowledge — function inventory, flow diagrams, boundary catalog — so they focus on changes since last mapping and quality assessment, not rediscovery.
3. **If it doesn't exist:** Proceed without atlas context. The reviewer discovers the system from scratch (pre-atlas behavior).

### Step 3: Dispatch System Review (Size-Gated)

Check the system's **live file count** at dispatch time — do not use the atlas file count, as systems may have grown since discovery.

**Systems ≤10 files — direct Opus dispatch:**

1. Identify the system's domain (game dev → the Game Dev Reviewer, frontend → the Front-End Reviewer, ML → the Data Science Reviewer, other → the Staff Engineer)
2. Dispatch reviewer with full system scope — all files in the system
3. Include the atlas page as context (if it exists, per Step 2.5)
4. Reviewer grades the system and adds/updates the grade on the atlas page
5. High effort means backstop is mandatory (the Staff Engineer for domain reviewers, the Director of Engineering for the Staff Engineer)

**Systems >10 files — Haiku→Sonnet pre-digestion:**

0. **Generate run ID** — format: `YYYY-MM-DD-HHhMM`. Scratch directory: `tasks/scratch/weekly-architecture-audit/{run-id}/`
1. **Sub-chunk** the system into groups of 8-12 files, organized by concern (not alphabetical — group by what the files do together)
2. **Dispatch Haiku inventory agents (parallel)** — one per sub-chunk. Use the Phase 1: Haiku Function-Level Inventory Prompt from `deep-architecture-survey/agent-prompts.md`. These agents read files and catalog what exists — no analysis. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md` as `[SCRATCH_PATH]`. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)
   **Scratch verification:** Before dispatching Sonnet, verify all expected Haiku scratch files exist. Re-dispatch once on failure; skip that sub-chunk on second failure.
3. **Dispatch Sonnet analysis agents (parallel)** — one per system — reads ALL Haiku sub-chunk inventories from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase1-haiku.md`. Use the Phase 2: Sonnet System Analysis Prompt from `deep-architecture-survey/agent-prompts.md` (the variant with grading). Include the existing atlas page as context so Sonnet focuses on changes and quality assessment, not rediscovery. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md` as `[SCRATCH_PATH]`. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)
   **Scratch verification:** Before dispatching Opus reviewer, verify Sonnet scratch files exist. Re-dispatch once on failure.
4. **Dispatch domain reviewer (Opus)** with **summarized Sonnet findings (read from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase2-sonnet.md`)** — reviewer brings judgment and cross-cutting insight, not file-reading labor. Do NOT send raw files to the domain reviewer.
5. Reviewer grades the system and adds/updates the grade on the atlas page
6. Backstop receives summarized Sonnet analysis findings, not raw files. Backstop is mandatory: the Staff Engineer (Opus) for domain reviewers; the Director of Engineering (Opus) for the Staff Engineer.

**Opus failure recovery:** If the domain reviewer fails to return a valid grade, re-dispatch once. If second failure, record `grade: ?` and `health_status: AUDIT_INCOMPLETE` in the atlas frontmatter. Log the failure in the Step 7 report. Do NOT silently skip the grade update. Apply the same recovery pattern to the backstop dispatch.

**Note:** Templates for Haiku and Sonnet agents are in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. Do not duplicate them here — reference that file directly when dispatching.

### Step 4: Package Findings as Spinoff Candidates (the audit NEVER edits code)

The audit pass **never edits code** — it reads, scores, and hands findings to the EM. There is no inline-fix step. The EM routes each finding down a disposition ladder (people over process):

- **Trivial / tradeoff-free AND non-structural** → EM dispatches an executor immediately (ordinary EM remit, no PM gate). **Guardrail:** any finding touching a module boundary, interface, or cross-system surface is ineligible regardless of line count — it routes to a spinoff candidate so it stays recorded.
- **Mid-size cluster** → EM groups into ONE bundled spinoff candidate.
- **Large / genuinely structural** → standalone spinoff candidate, or escalate to `/plan`.

Spinoff candidates surface as PM-gated `Candidate spinoff: <slug> — <topic>. Authorize?` prompts; the audit never auto-authors spinoff files (`/spinoff` Step 0). The immediate-executor path bypasses the gate by design.

### Step 5: (retired — no auto-debt-backlog write)

**D5 (PM 2026-05-24):** the audit no longer writes `tasks/debt-backlog.md` entries. The disposition ladder (Step 4) + spinoff-candidate pattern is the dedicated home for audit findings. `debt-backlog.md` remains only for items the EM/PM explicitly choose to **defer with a reason** (architectural OOS) — not the default sink for audit findings. The Step 4 guardrail keeps structural findings recorded as spinoff candidates so nothing goes dark.

### Step 6: Update Health Ledger

1. Update the system's row: new grade, status, audit date, open issue counts
2. Update the **`Last targeted audit`** date in the header — this rotational audit writes the targeted clock, NOT `Last full audit` (only `/architecture-survey` writes that; `check-arch-audit-staleness.sh` reads `Last targeted audit`).
3. Calculate the next rotation target and update `Next rotation target` in the header
4. Commit (health-ledger only — no debt-backlog write, no code edits):
   ```bash
   git add tasks/health-ledger.md
   git commit -m "arch-audit: [system] audited, grade [X]→[Y]; Last targeted audit bumped"
   ```

### Step 6.5: Update Atlas Page

If `docs/architecture/systems/{target-system}.md` exists, the coordinator (not the reviewer) reads the reviewer's findings and mechanically patches the atlas page:

1. Add/remove functions mentioned in review findings
2. Update boundary entries if cross-system connections changed
3. Bump the `last_mapped` date in the YAML frontmatter
4. Add `grade: [A-F]` and `health_status: [HEALTHY|WATCH|ACTION|CRITICAL]` fields to the YAML frontmatter, after the `dependencies` field.

This is incremental maintenance, not a full re-mapping. Keep it lightweight — only update what the review explicitly found changed. If no atlas page exists for the system, skip this step.

### Step 6.75: Triage Scratch Files

If the large-systems path was used, delete all scratch files — Haiku/Sonnet output was fully consumed by the Opus reviewer.

```bash
rm -rf tasks/scratch/weekly-architecture-audit/{run-id}/
```

### Step 7: Report

```markdown
## Weekly Architecture Audit Complete

**System:** [name]
**Reviewer:** [name] at High effort (backstop: [name])
**Previous grade:** [X] | **New grade:** [Y]
**Findings:** N total (X applied inline, Y added to debt backlog)
**Debt backlog:** [N] open items [⚠️ exceeds 20 — recommend /debt-triage]
**Next rotation target:** [system] (score: N)
```

## Key Principle

The audit *discovers* debt. It doesn't *fix* debt inline. Debt goes through the plan → review → execute pipeline like any other work. This keeps the audit focused on discovery and avoids sprawling refactor sessions.

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Dispatching Opus reviewer with >10 files for grading | Skipped size gate; used direct dispatch for a large system | Sub-chunk the system; use Haiku→Sonnet pre-digestion before Opus reviewer |
| Opus agent 529 overload | System too large for direct dispatch | Sub-chunk into 8-12 file groups; Haiku and Sonnet handle file reading |
| Sonnet findings lack depth | Sub-chunks too large (>12 files each) | Re-partition into smaller chunks; Sonnet performs better with focused scope |
| Reviewer grades a system the atlas already has context for, but misses structural detail | Atlas page not included in Sonnet dispatch | Always include the atlas page in the Sonnet agent prompt as background context |
| Opus domain reviewer 529/crash | Model overload or context limit during reviewer dispatch | Re-dispatch once after 60s with reduced context (Sonnet findings only, no atlas page). If second failure, present Sonnet analysis to PM as interim assessment; mark system as `BLOCKED — Opus review pending` in health ledger. |

## Rollback Option

If the health ledger or debt backlog becomes stale or corrupted, delete both files. The next weekly audit will rebuild the ledger from a fresh full-system scan, and the debt backlog starts clean.

## Cost

**Small systems (≤10 files):** 1-2 Opus dispatches (reviewer + backstop) + review-integrator for inline fixes.

**Large systems (>10 files):** Haiku inventory agents (parallel, one per 8-12 file sub-chunk) + Sonnet analysis agents (parallel, one per sub-chunk) + 1-2 Opus dispatches (domain reviewer + backstop). Haiku and Sonnet costs are low; the Opus reviewer still dominates the total. Debt items are separate pipeline runs regardless of system size.
