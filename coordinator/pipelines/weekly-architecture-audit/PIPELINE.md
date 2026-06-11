# Weekly Architecture Audit — Systematic System Rotation

> Referenced by `/architecture-audit`. This is a pipeline definition, not an invocable skill.

## Overview

Rotate through project systems ensuring complete coverage. Uses a weighted scoring formula to select the highest-priority audit target. **Discovers findings, never edits code** — findings are packaged as spinoff candidates down the EM disposition ladder (immediate executor for trivial+non-structural / bundled spinoff candidate / standalone-or-plan for large). Writes the `Last targeted audit` clock, not `Last full audit`.

**Announce at start:** "I'm using /architecture-audit to audit [system name]."

## When to Trigger

- Surfaced at workstream-start when `Last targeted audit` in health ledger is >10 days old
- Auto-folded by `/workweek-complete` Step 7.6 when `check-arch-audit-staleness.sh` returns STALE
- Available as maintenance menu option (Option 6 in workstream-start)
- Can be invoked directly any time

## The Process

### Step 1: Calculate Rotation Scores

**Prerequisite check:** If no health ledger exists (`state/health-ledger.md`) AND no atlas exists (`docs/architecture/systems-index.md`):

> _"No baseline exists. Use /architecture-survey first to bootstrap the atlas and health ledger."_

Stop here — the weekly audit needs a baseline to rotate through. If a health ledger exists but no atlas, proceed normally (the audit predates the atlas feature).

Read `state/health-ledger.md`. For each system in the index, calculate a rotation score:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| CRITICAL status or open P0 | +15 | Known-bad systems should never be deprioritized by staleness alone |
| Never audited | +10 | Unknown state is high risk — could be A or could be F |
| >30 days since audit | +5 | A month without inspection is too long for active code |
| >14 days since audit | +2 | Moderate staleness, adds up with other signals |
| Open P1 items | +3 each | Accumulated P1s compound — three P1s = one P0 in practice |
| Significant growth since last audit | +3 | New code = new risk, regardless of current grade |
| Security-sensitive system | +2 | Higher consequence of missed issues |

**Pre-rotation drift surface (run before accepting the rotation pick):** invoke `bin/check-atlas-watch-drift.sh` and surface any `DRIFT` / `MISSING` / `ERROR` / `MALFORMED` / `STALE` lines for systems that are rotation candidates. Drift on the proposed target system bumps it to the top of the rotation regardless of formula score — a stale baseline invalidates the audit. This is detection-leg coverage for atlases that have decayed mechanically between rotations.

Select the system with the highest score. Report: _"Rotation target: [system] (score: N). Rationale: [top signals]."_

**Note:** These weights are initial estimates — adjust after 4 weeks based on whether rotation targets match intuition.

### Step 2: Review Existing Debt

Read `state/debt-backlog.md` for the target system. If open items exist:

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
5. **Multi-reviewer is angle-motivated, not a mandatory backstop.** Dispatch a second reviewer ONLY when a distinct lens is load-bearing (e.g. `project-rag` → the Staff Engineer for architecture + the Data Science Reviewer for ML/retrieval). "Push back on lack of ambition" is ordinary EM remit — does not motivate a formal second reviewer on every audit.

**Systems >10 files — Haiku→Sonnet pre-digestion:**

0. **Generate run ID** — format: `YYYY-MM-DD-HHhMM`. Scratch directory: `tasks/scratch/weekly-architecture-audit/{run-id}/`
1. **Sub-chunk** the system into groups of 8-12 files, organized by concern (not alphabetical — group by what the files do together)
2. **Dispatch Haiku inventory agents (parallel)** — one per sub-chunk. Use the Phase 1: Haiku Function-Level Inventory Prompt from `deep-architecture-survey/agent-prompts.md`. These agents read files and catalog what exists — no analysis. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md` as `[SCRATCH_PATH]`. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)
   **Scratch verification:** Before dispatching Sonnet, verify all expected Haiku scratch files exist. Re-dispatch once on failure; skip that sub-chunk on second failure.
3. **Dispatch Sonnet analysis agents (parallel)** — one per system — reads ALL Haiku sub-chunk inventories from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase1-haiku.md`. Use the Phase 2: Sonnet System Analysis Prompt from `deep-architecture-survey/agent-prompts.md` (the variant with grading). Include the existing atlas page as context so Sonnet focuses on changes and quality assessment, not rediscovery. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md` as `[SCRATCH_PATH]`. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)
   **Scratch verification:** Before dispatching Opus reviewer, verify Sonnet scratch files exist. Re-dispatch once on failure.
4. **Dispatch domain reviewer (Opus)** with **summarized Sonnet findings (read from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase2-sonnet.md`)** — reviewer brings judgment and cross-cutting insight, not file-reading labor. Do NOT send raw files to the domain reviewer.
5. Reviewer grades the system and adds/updates the grade on the atlas page
6. **Multi-reviewer is angle-motivated, not a mandatory backstop** (see ≤10-files row 5). When a second angle is warranted, that reviewer reads the summarized Sonnet analysis, not raw files.

**Opus failure recovery:** If the domain reviewer fails to return a valid grade, re-dispatch once. If second failure, record `grade: ?` and `health_status: AUDIT_INCOMPLETE` in the atlas frontmatter. Log the failure in the Step 7 report. Do NOT silently skip the grade update. Apply the same recovery pattern to any angle-motivated second reviewer.

**Note:** Templates for Haiku and Sonnet agents are in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. Do not duplicate them here — reference that file directly when dispatching.

### Step 4: Package Findings as Spinoff Candidates (the audit NEVER edits code)

The audit pass **never edits code** — it reads, scores, and hands findings to the EM. There is no inline-fix step. The EM routes each finding down a disposition ladder (people over process):

- **Trivial / tradeoff-free AND non-structural** → EM dispatches an executor immediately (ordinary EM remit, no PM gate). **Guardrail:** any finding touching a module boundary, interface, or cross-system surface is ineligible regardless of line count — it routes to a spinoff candidate so it stays recorded.
- **Mid-size cluster** → EM groups into ONE bundled spinoff candidate.
- **Large / genuinely structural** → standalone spinoff candidate, or escalate to `/plan`.

Spinoff candidates surface as PM-gated `Candidate spinoff: <slug> — <topic>. Authorize?` prompts; the audit never auto-authors spinoff files (`/spinoff` Step 0). The immediate-executor path bypasses the gate by design.

### Step 5: (retired — no auto-debt-backlog write)

**D5 (PM 2026-05-24):** the audit no longer writes `state/debt-backlog.md` entries. The disposition ladder (Step 4) + spinoff-candidate pattern is the dedicated home for audit findings. `debt-backlog.md` remains only for items the EM/PM explicitly choose to **defer with a reason** (architectural OOS) — not the default sink for audit findings. The Step 4 guardrail keeps structural findings recorded as spinoff candidates so nothing goes dark.

### Step 6: Update Health Ledger

1. Update the system's row: new grade, status, audit date, open issue counts
2. Update the **`Last targeted audit`** date in the header — this rotational audit writes the targeted clock, NOT `Last full audit` (only `/architecture-survey` writes that; `check-arch-audit-staleness.sh` reads `Last targeted audit`).
3. Calculate the next rotation target and update `Next rotation target` in the header
4. **Stage** the health-ledger update — do NOT commit yet. The health-ledger commit is **deferred until Step 6.5 gate PASSes**. On gate FAIL the ledger commit does NOT land — this prevents `Last targeted audit` from advancing on an audit that closed against a stale atlas. The bundled close-out commit (atlas + ledger together, or sequenced atlas-then-ledger) lands after Step 6.5 gate PASS. Two-clock doctrine preserved: `Last targeted audit` only is touched; `Last full audit` is untouched (only `/architecture-survey` writes that clock).
   ```bash
   # Stage only — do NOT commit until after Step 6.5 gate PASS.
   git add state/health-ledger.md
   ```

### Step 6.5: Update Atlas Page (Pre-Commit Gate)

If `docs/architecture/systems/{target-system}.md` does not exist, skip this step entirely. Otherwise the atlas page MUST satisfy one of two branches before close-out commits land. The gate runs **before** `git commit` — it reads staged content and the intended commit message, NOT HEAD.

**Branch A (refresh inline):** if reviewer findings warrant changes:
1. Edit the atlas page body — add/remove functions mentioned in findings, update boundary entries if cross-system connections changed.
2. Bump `last_mapped` to the audit date in the YAML frontmatter.
3. Add/update `grade: [A-F]` and `health_status: [HEALTHY|WATCH|ACTION|CRITICAL]` fields in the YAML frontmatter, after the `dependencies` field.
4. Stage the atlas page alongside the health-ledger update from Step 6.

**Branch B (assert current):** if the atlas is already accurate and no body changes are warranted:
1. Bump `last_mapped` to the audit date only (no body diff).
2. Stage the atlas page alongside the health-ledger update.
3. Prepare a close-out commit message containing the literal token `atlas-current-as-of: <YYYY-MM-DD>` (the audit date).

**Run the gate (before `git commit`):**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/bin/verify-arch-audit-atlas-refresh.sh <AUDIT_DATE> <TARGET_SYSTEM> [<COMMIT_MSG_FILE>]
```

- On `PASS branch=A` or `PASS branch=B` → proceed to `git commit` (atlas + ledger together, or sequenced atlas-then-ledger).
- On `FAIL` → do NOT commit. Amend the working tree (Branch A: add the body diff that was missing) or the intended commit message (Branch B: add the `atlas-current-as-of:<date>` token), re-stage, and re-run the helper. The commit does NOT land until the gate returns PASS.

**Anti-scope (this gate ONLY):**
- The gate does NOT extend to `/architecture-survey` — `Last full audit` is exclusively that command's clock and this gate never touches it.
- The gate is NOT per-system hot-configurable (no per-system staleness window for the closeout gate).
- The gate does NOT opportunistically refresh non-target atlas pages — the weekly walk (`/workweek-complete` invocation of `check-atlas-watch-drift.sh`) surfaces drift on other pages; refresh of those is per-rotation EM judgment, not an inline side-effect of this audit.

### Step 6.75: Triage Scratch Files

If the large-systems path was used, delete all scratch files — Haiku/Sonnet output was fully consumed by the Opus reviewer.

```bash
rm -rf tasks/scratch/weekly-architecture-audit/{run-id}/
```

### Step 7: Report

**Precondition:** `bin/verify-arch-audit-atlas-refresh.sh` returned `PASS branch=A` or `PASS branch=B` on the last attempt. If it returned `FAIL`, do NOT proceed to Step 7 — fix per Branch A or Branch B in Step 6.5 and re-attempt. The verbatim failure message is the iron-law signal:

```
FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied for <TARGET_SYSTEM>.
Either (a) refresh docs/architecture/systems/<TARGET_SYSTEM>.md inline before closing,
or (b) declare atlas-current-as-of:<YYYY-MM-DD> in the closeout commit message.
```

```markdown
## Weekly Architecture Audit Complete

**System:** [name]
**Reviewer(s):** [name] at High effort [+ second-angle reviewer: [name] — angle: [reason], or "none — single angle sufficed"]
**Previous grade:** [X] | **New grade:** [Y]
**Findings:** N total — [X → immediate executor (trivial+non-structural), Y → spinoff candidate(s) surfaced to PM, Z → escalated to /plan]
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

**Small systems (≤10 files):** 1 Opus domain-reviewer dispatch; +1 only when a second angle is load-bearing (Step 3).

**Large systems (>10 files):** Haiku inventory agents (parallel, one per 8-12 file sub-chunk) + Sonnet analysis agents (parallel, one per sub-chunk) + 1 Opus domain reviewer (+1 angle-motivated reviewer only when warranted). Haiku and Sonnet costs are low; the Opus reviewer still dominates the total. Debt items are separate pipeline runs regardless of system size.
