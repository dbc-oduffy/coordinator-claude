---
description: Strategic daily review — inventory today's work, summarize what shipped, get architectural perspective
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: (no arguments needed)
---

# Daily Review — Strategic Work Summary and Architectural Check

Produce a daily work summary artifact and get a strategic architectural review. This replaces the old `/code-health` dispatch (detailed code-level review) at end-of-day — our review-heavy build pipeline (plan → enrich → chunk → review) already catches code-level issues. The daily review instead asks: did today's accumulated decisions create technical debt, lock us into patterns, or miss opportunities for the product's longer-term direction?

**Announce at start:** "I'm running /daily-review to summarize today's work and get a strategic check."

## Never Skip on a "Small" Day

The strongest predictor of a review that surfaces regressions is a small commit count, not a large one. When today's work touched one code path, the adjacent or sibling path is the highest-probability next bug — and a quiet day is exactly when the EM and PM are most tempted to skip ("only 8 commits, nothing worth reviewing"). Empirically, that's where the architectural drift and silent regressions hide.

**Run this review on every committed day, regardless of commit count.** The cost is ~7-11 minutes; the asymmetry strongly favors running it. A quiet day's review catches the regression a single fix introduced on a parallel handler. Skipping because the day felt small means the next session inherits the surprise.

The only valid skip: **zero new commits today AND no agent-driven changes outside commits.** Anything else — one commit, one file — run the review.

## Output Artifact

`archive/daily-summaries/YYYY-MM-DD.md` — a reusable daily summary that feeds:
- `/update-docs` (enriches project tracker and orientation cache)
- `/distill` (provides pre-digested context for knowledge extraction)
- Completed work register (richer than terse commit logs, less verbose than handoffs)
- Next morning's `/session-start` and `/workday-start` (strategic context)

---

## Phase A: Inventory Generation

Generate a deterministic structured inventory of today's work using the `standup.sh` script.

1. **Create directory:**
   ```bash
   mkdir -p tasks/daily-review-scratch
   ```

2. **Run standup.sh and capture inventory:**
   ```bash
   bash plugins/coordinator-claude/coordinator/bin/standup.sh > tasks/daily-review-scratch/inventory.md
   ```

The script emits:
   - `> Baseline: <sha> (<ISO-timestamp>)` — parsed by Phase B for git diff baseline
   - Commit inventory
   - File change summary by directory
   - Touched handoff files
   - Touched todo files
   - Active handoff list

**Proceed to Phase B after inventory is written.**

---

## Phase B: Sonnet Work Summary

Dispatch a **Sonnet** agent (`model: "sonnet"`, `run_in_background: true`) to produce a narrative work summary.

### Analyst instructions

1. **Read** `tasks/daily-review-scratch/inventory.md` (the Phase A output).

2. **Extract baseline:** Parse the `> Baseline:` header line from the inventory to get the commit hash and timestamp. Example:
   ```bash
   BASELINE=$(grep '^> Baseline:' tasks/daily-review-scratch/inventory.md | sed 's/^> Baseline: //' | awk '{print $1}')
   ```

3. **Read the actual diffs** for architectural understanding:
   ```bash
   git diff <baseline>..HEAD
   ```
   If the diff exceeds ~3000 lines, focus on the files with the most changes (from the inventory's file change table). Use `git diff <baseline>..HEAD -- <path>` for targeted reads.

4. **Read commit messages in full** for context on intent:
   ```bash
   git log --since="<baseline>" --format="%H%n%s%n%b%n---"
   ```

5. **Read plan docs** referenced in the inventory (if any) for context on what was being built and why.

6. **Write the daily summary** to `archive/daily-summaries/YYYY-MM-DD.md`:

   ```markdown
   # Daily Summary — YYYY-MM-DD

   > Generated: YYYY-MM-DD HH:MM by /daily-review
   > Baseline: <commit-hash> (<date>)
   > Commits: N | Files changed: M

   ## Work Completed
   - **[Feature/system]** — [what changed and why] | commits: [hashes]
   - ...

   ## Systems Affected
   | System | Files Changed | Lines +/- | Nature of Change |
   |--------|--------------|-----------|-----------------|
   | ...    | ...          | ...       | ...             |

   ## Architectural Decisions (Explicit & Implicit)
   - [Decision description — e.g., "Player pawn hardcoded as drone class"]
     - **Rationale:** [why this was done, from commit messages/plan docs]
     - **Risk:** [what this locks in or limits]
   - ...

   _Strategic Review section will be appended by Phase C._
   ```

   **Create `archive/daily-summaries/` directory if it doesn't exist.**

7. **The "Architectural Decisions" section is the key value-add.** Don't just list what changed — identify decisions that were made (even implicitly) and their consequences. Examples:
   - "Added a direct dependency from module A to module B" — coupling risk
   - "Used a concrete class where an interface would allow future flexibility" — extensibility risk
   - "Hardcoded a configuration value that may need to vary" — flexibility risk
   - "Chose approach X over Y" — tradeoff documentation

Wait for the analyst to complete before proceeding to Phase C.

---

## Phase C: Persona Strategic Review

Route to a reviewer based on the dominant domain of today's work. Use the same routing logic as `/code-health`:

| Dominant change type | Reviewer |
|---|---|
| Game dev / Unreal Engine | the Game Dev Reviewer (`game-dev:staff-game-dev`) |
| Frontend / UI | the Front-End Reviewer (`web-dev:senior-front-end`) |
| Data / ML / science | the Data Science Reviewer (`data-science:staff-data-sci`) |
| Mixed, backend, or architecture | the Staff Engineer (`coordinator:staff-eng`) |

Dispatch the selected reviewer as a **Sonnet** agent (this is a strategic check, not a deep code review — Sonnet is sufficient).

### Reviewer instructions

The reviewer reads the work summary and project strategic documents, then provides an architectural perspective. **This is NOT a code review.** No inline code fixes.

1. **Read** `archive/daily-summaries/YYYY-MM-DD.md` (the Phase B output).

2. **Read project strategic documents** (check each, skip silently if missing):
   - `ROADMAP.md`, `docs/roadmap.md`, or `docs/ROADMAP.md`
   - `VISION.md` or `docs/vision.md`
   - `docs/project-tracker.md`

3. **Assess** today's work against the strategic direction. Focus on:
   - **Alignment:** Does today's work advance the roadmap? Does anything conflict?
   - **Lock-in:** Do any decisions create accidental constraints that the roadmap/vision would want to avoid?
   - **Bridging opportunities:** Are there low-cost opportunities to make today's code more ready for planned future capabilities?
   - **Debt patterns:** Is technical debt accumulating in a direction that should be documented?

4. **Append** findings to the daily summary file as a new section:

   ```markdown
   ## Strategic Review (by {reviewer-name})

   > Reviewer read: [list which strategic docs were found and read]

   ### Alignment Assessment
   - [Where today's work advances the roadmap]
   - [Where today's work diverges or creates friction]

   ### Technical Debt Identified
   - [Debt item — what, why it matters, suggested future action]
   - ...

   ### Bridging Opportunities
   - [Things that could be done to better connect current state to vision]
   - ...
   ```

   If no strategic docs exist, note that and focus purely on architectural principles (SOLID, coupling, extensibility).

5. **Debt backlog entries:** For any finding that warrants tracking, add a row to `tasks/debt-backlog.md` (create from template if it doesn't exist — same template as `/code-health` Step 5):
   - ID: `DSR-{date}-{N}` (Daily Strategic Review prefix)
   - Source: `daily-review/{reviewer}/{date}`
   - Status: `open`

---

## Phase D: Health Ledger Update

After Phase C completes:

1. Read `tasks/health-ledger.md`. If it doesn't exist, create from the standard template (see `/code-health` Step 6).
2. Update `Last daily check` to today's date.
3. If Phase C findings warrant grade changes for any system, update the relevant rows.
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited).

---

## Phase E: Commit and Report

1. Commit all artifacts:
   ```bash
   git add archive/daily-summaries/ tasks/daily-review-scratch/ tasks/health-ledger.md tasks/debt-backlog.md
   git commit -m "daily-review: strategic review of work since <baseline-date>"
   ```
   The post-commit hook pushes automatically.

2. **Clean up scratch:** Delete `tasks/daily-review-scratch/` — the inventory served its purpose and the durable artifact is the daily summary.

3. **Report** to the coordinator:
   ```
   Daily review complete.
   - Work summary: archive/daily-summaries/YYYY-MM-DD.md
   - Reviewer: {reviewer-name}
   - Strategic findings: N (M added to debt backlog)
   - Systems touched: [list]
   - Health ledger: updated
   ```

---

## Failure Modes

| Situation | Action |
|---|---|
| No commits since baseline | Write a minimal daily summary noting "no work today", skip Phases B-C |
| `standup.sh` exits non-zero | Fall back: EM runs git commands directly, writes inventory manually, proceed to Phase B |
| Analyst dispatch fails | Fall back: EM writes a minimal work summary from the inventory, proceed to Phase C |
| Reviewer dispatch fails | Skip Phase C, note "strategic review skipped" in the daily summary |
| No strategic docs exist | Reviewer focuses on pure architectural principles instead of roadmap alignment |
| Debt backlog doesn't exist | Create from template before adding entries |

---

## Cost

1 deterministic shell script (`standup.sh`, sub-second) + 1 Sonnet agent (analyst, ~3-5 min) + 1 Sonnet agent (reviewer, ~3-5 min). Total: ~6-10 minutes. Phase A no longer dispatches an agent.

---

## Relationship to Other Commands

- **`/workday-complete`** — primary trigger; runs this as part of its end-of-day pipeline (Step 3)
- **`/code-health`** — still available for on-demand detailed code-level review. Not redundant — different focus (code correctness vs. strategic alignment)
- **`/session-start`** — reads `archive/daily-summaries/` for context
- **`/workday-start`** — reads most recent daily summary for orientation cache
- **`/update-docs`** — can use daily summaries to enrich project tracker
- **`/distill`** — daily summaries are pre-digested input for knowledge extraction
