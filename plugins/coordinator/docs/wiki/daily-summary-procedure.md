---
name: daily-summary-procedure
status: canonical
spec_backlink: docs/plans/2026-05-09-skill-consolidation-pass.md
---

# Daily Summary Procedure

> Reference wiki for `/workday-complete` Step 4. Heavy-weight artifacts extracted here to keep the
> command body under 200 lines. Step 4 walks these sections inline — do not skip them.
>
> Spec backlink: `docs/plans/2026-05-09-skill-consolidation-pass.md` § T1

---

## Daily Reviewer — Sonnet Observer, No Persona Routing

The daily strategic review is dispatched as an **unnamed Sonnet worker** (`general-purpose`,
`model: "sonnet"`). There is **no domain→persona routing** at daily cadence — that was the old
shape and it was wrong. Personas (the Game Dev Reviewer / the Front-End Reviewer / the Data Science Reviewer / the Staff Engineer) are Opus-only; routing a *daily*
ceremony to one puts Opus persona-judgment on the cheapest, most frequent gate we have. The fix
mirrors Sonnet-tier code review moving off personas onto `code-reviewer`.

**Role: observer, not judge.** The daily worker leaves a **paper trail for future-the Staff Engineer** —
alignment notes, debt candidates, architectural-risk *flags*. It renders no final architectural
verdict. The **weekly** Opus the Staff Engineer arch pass (`/workweek-complete` Step 7.5) consumes the week's
accumulated daily trail (the `## Strategic Review (Sonnet daily observer)` sections + DSR rows
tagged `for-weekly-arch-review`) and adjudicates. Domain still matters only for *vocabulary* — a
UE-heavy day's observer should speak UE — but the dispatch is one Sonnet worker regardless, never
a named persona.

---

## Sonnet Analyst Prompt Template

Use this verbatim when dispatching the Phase 4b analyst agent
(`model: "sonnet"`, `run_in_background: true`).

---

**Analyst instructions:**

1. **Read** `tasks/daily-review-scratch/inventory.md` (the Step 4a output).

2. **Extract baseline:** Parse the `> Baseline:` header line from the inventory to get the commit
   hash and timestamp. Example:
   ```bash
   BASELINE=$(grep '^> Baseline:' tasks/daily-review-scratch/inventory.md \
     | sed 's/^> Baseline: //' | awk '{print $1}')
   ```

3. **Read the actual diffs** for architectural understanding:
   ```bash
   git diff <baseline>..HEAD
   ```
   If the diff exceeds ~3000 lines, focus on the files with the most changes (from the inventory's
   file change table). Use `git diff <baseline>..HEAD -- <path>` for targeted reads.

4. **Read commit messages in full** for context on intent:
   ```bash
   git log --since="<baseline>" --format="%H%n%s%n%b%n---"
   ```

5. **Read plan docs** referenced in the inventory (if any) for context on what was being built
   and why.

6. **Write the daily summary** to `archive/daily-summaries/YYYY-MM-DD.md`:

   ```markdown
   # Daily Summary — YYYY-MM-DD

   > Generated: YYYY-MM-DD HH:MM by /workday-complete Step 4
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

   _Strategic Review section will be appended by the reviewer agent._
   ```

   **Create `archive/daily-summaries/` directory if it doesn't exist.**

7. **The "Architectural Decisions" section is the key value-add.** Don't just list what changed —
   identify decisions that were made (even implicitly) and their consequences. Examples:
   - "Added a direct dependency from module A to module B" — coupling risk
   - "Used a concrete class where an interface would allow future flexibility" — extensibility risk
   - "Hardcoded a configuration value that may need to vary" — flexibility risk
   - "Chose approach X over Y" — tradeoff documentation

---

## Daily Strategic Observer Prompt Template

Dispatch after the analyst completes, as an **unnamed Sonnet worker** (`general-purpose`,
`model: "sonnet"`) — **never a named persona** (see § Daily Reviewer above for why). The worker is
an **observer leaving a paper trail for future-the Staff Engineer**, not a judge. It flags candidates; the
weekly Opus the Staff Engineer arch pass adjudicates.

---

**Daily observer instructions:**

You are an unnamed Sonnet strategic observer for the daily wrap. Read the work summary and project
strategic documents and leave a **paper trail** — alignment notes, debt candidates, and
architectural-risk *flags* for the weekly Opus arch pass to adjudicate. **Render no final
architectural verdict** and do **not** claim a persona identity. **This is NOT a code review** — no
inline code fixes.

1. **Read** `archive/daily-summaries/YYYY-MM-DD.md` (the analyst output).

2. **Read project strategic documents** (check each, skip silently if missing):
   - `ROADMAP.md`, `docs/roadmap.md`, or `docs/ROADMAP.md`
   - `VISION.md` or `docs/vision.md`
   - `docs/project-tracker.md`

3. **Assess** today's work against the strategic direction. Focus on:
   - **Alignment:** Does today's work advance the roadmap? Does anything conflict?
   - **Lock-in:** Do any decisions create accidental constraints that the roadmap/vision would
     want to avoid?
   - **Bridging opportunities:** Are there low-cost opportunities to make today's code more ready
     for planned future capabilities?
   - **Debt patterns:** Is technical debt accumulating in a direction that should be documented?

4. **Append** findings to the daily summary file as a new section:

   ```markdown
   ## Strategic Review (Sonnet daily observer)

   > Observer read: [list which strategic docs were found and read]

   ### Alignment Assessment
   - [Where today's work advances the roadmap]
   - [Where today's work diverges or creates friction]

   ### Technical Debt Identified
   - [Debt item — what, why it matters, suggested future action]
   - ...

   ### Architectural-Risk Flags (for future-the Staff Engineer / weekly arch pass)
   - [Candidate concern — flagged, NOT adjudicated. State what to look at and why it might matter.]
   - ...

   ### Bridging Opportunities
   - [Things that could be done to better connect current state to vision]
   - ...
   ```

   If no strategic docs exist, note that and focus purely on architectural principles
   (SOLID, coupling, extensibility).

5. **Debt backlog entries:** For any finding that warrants tracking, add a row to
   `state/debt-backlog.md` (create from template if it doesn't exist):
   - ID: `DSR-{date}-{N}` (Daily Strategic Review prefix)
   - Source: `workday-complete/step4/sonnet-observer/{date}`
   - Status: `open`
   - **Tag any architectural-risk flag `for-weekly-arch-review`** so the weekly the Staff Engineer arch pass
     (`/workweek-complete` Step 7.5) picks it up as accumulated daily signal.

---

## Health Ledger Entry Schema

After the reviewer agent completes, update `state/health-ledger.md`:

1. If it doesn't exist, create it with this shape (two audit clocks above a per-system table —
   the schema established by the 2026-05-23 weekly-gate/arch-survey restructure; do **not**
   conflate the clocks):
   ```markdown
   # Health Ledger

   **Last full audit:** (none — run /architecture-survey)
   **Last targeted audit:** <date or none>
   **Next rotation target:** <system>

   | System | Grade | Last Audited | Notes |
   |--------|-------|-------------|-------|
   ```

2. If a system was touched by today's commits but has no row yet, add it with grade `?` (unaudited).

3. Do **NOT** update grades or the two audit clocks from the daily wrap. `Last full audit` is written
   only by a PM-invoked `/architecture-survey`; `Last targeted audit` only by `/architecture-audit`.
   The daily Sonnet observer renders no grades — it flags candidates as `state/debt-backlog.md` DSR
   rows (`for-weekly-arch-review`) for the weekly the Staff Engineer arch pass to adjudicate. Grade changes are
   an audit output, never a daily-wrap side effect.

---

## Debt Backlog DSR-ID Format

Entries added by the daily strategic reviewer use this ID format:

```
DSR-{YYYY-MM-DD}-{N}
```

Where `{N}` is a 1-based sequential integer for that day (DSR-2026-05-09-1, DSR-2026-05-09-2, …).

Full row schema for `state/debt-backlog.md`:

```markdown
| DSR-{date}-{N} | {one-line description} | workday-complete/step4/{reviewer}/{date} | open |
```

---

## Failure Mode Table

| Situation | Action |
|---|---|
| No commits since baseline | Write a minimal daily summary noting "no work today"; skip analyst and reviewer dispatch |
| `standup.sh` exits non-zero | Fall back: EM runs git commands directly, writes inventory manually; proceed to analyst dispatch |
| Analyst dispatch fails | Fall back: EM writes a minimal work summary from the inventory; proceed to reviewer dispatch |
| Reviewer dispatch fails | Skip reviewer, note "strategic review skipped" in the daily summary |
| No strategic docs exist | Reviewer focuses on pure architectural principles instead of roadmap alignment |
| Debt backlog doesn't exist | Create from template before adding entries (see schema above) |

---

## Skip Condition

The only valid skip: **zero new commits today AND no agent-driven changes outside commits.**
Anything else — one commit, one file — run the review. The strongest predictor of a review
that surfaces regressions is a small commit count, not a large one.
