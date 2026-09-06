# Daily Code Health — Catch Issues Before They Accumulate

> Referenced by `/code-health`. This is a pipeline definition, not an invocable skill.

## Overview

The "night shift colleague" — reviews today's commits, dispatches a reviewer for any issues, applies findings via review-integrator, and updates health tracking. Results are ready for the next morning's workstream-start.

**Announce at start:** "I'm using /code-health to review recent commits."

## When to Trigger

- **End-of-day (primary):** `/workday-complete` runs this as part of its health survey phase
- **On-demand:** Available in the workstream-start maintenance menu (Option 6)
- **NOT auto-triggered at workstream-start.** The PM runs 30+ sessions/day; automatic health checks would be friction, not value

## The Process

### Step 1: Find New Commits

Determine the scope of commits to review:

1. Check for a last-check timestamp:
   - Read `state/health-ledger.md` header for `Last daily check:` date
   - If no health ledger exists: this is the first run. Use the last 24 hours of commits as scope.
2. Get commits since last check:
   ```bash
   git log --since="<last-check-date>" --oneline --stat
   ```
3. **If no new commits:** Update timestamp, report "No new commits since last health check," and exit.

### Step 2: Generate Diff Scope

```bash
# Get the full diff for review
git diff <last-check-commit>..HEAD
```

Summarize the scope: which files changed, how many insertions/deletions, which systems are affected.

### Step 3: Dispatch the Sonnet Reviewer (non-persona)

The nightly health pass dispatches the **Sonnet `code-reviewer`** (`agents/code-reviewer.md`) — **NOT** a named persona. This is recurring Sonnet-tier code review, which by doctrine uses `code-reviewer`, never a persona (personas are Opus-only and reserved for the weekly arch pass, the merge gate, and explicit architectural decisions). Routing a *nightly* health check to an Opus persona is the same daily-cadence miscalibration `/workday-complete` Step 4c was corrected for.

Domain still matters — but for **vocabulary and emphasis**, not reviewer identity. State the dominant change type in the brief so the Sonnet reviewer knows what to scrutinize:

| Dominant change type | Tell the reviewer to weight… |
|---|---|
| Game dev / Unreal Engine | UE idioms, engine-lifecycle/ownership, Blueprint/C++ seams |
| Frontend / UI | component/token reuse, state flow, accessibility |
| Data / ML / science | numeric correctness, data contracts, reproducibility |
| Mixed, backend, or architecture | coupling, error paths, interface seams |

If multiple domains are present, weight toward the dominant one (most files changed / most critical path). A finding that genuinely needs persona/Opus judgment is **flagged for the weekly arch pass** (`/workweek-complete` Step 7.5), not escalated to an Opus dispatch here.

**Unattended review flow:** `coordinator:code-reviewer` self-persists by default — no pre-scaffold or claim marker required. The reviewer scaffolds its own sidecar in `state/review-trail/findings/` and returns a pointer+verdict line.

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED — no `name:` param), `run_in_background: true`, `--problems-only`. The reviewer scaffolds its own sidecar in `state/review-trail/findings/` via `coordinator-doc-new --type review-findings`, writes its findings there, and returns: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. Read the returned path; no EM pre-scaffold or claim marker.

### Step 4: Apply Findings

If the reviewer returns findings:

1. Dispatch `coordinator:review-integrator` pointing at the **on-disk sidecar path** (not inline findings — `agents/review-integrator.md` § Intake precondition hard-stops on inline-relayed findings). Pass the sidecar path and affected file paths.
2. Review-integrator applies inline fixes and annotations.
3. Complex findings (3+ interacting files, new abstractions) go to the debt backlog instead.

If no findings: skip to Step 6.

### Step 5: Update Debt Backlog

For any findings not fixed inline, record each as its own entry in `state/debt-backlog/` (directory of per-entry YAML — one file per finding, no markdown table):

1. Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema debt-backlog --surface <system> --severity <P0|P1|P2> --status open --title "<title>" --body "<description>"` for each deferred finding. This creates `state/debt-backlog/<date>-<slug>.yaml`.
2. Use:
   - ID/filename slug: `DCH-{date}-{N}` (Daily Code Health prefix)
   - Source: `daily-health/{reviewer}/{date}`
   - Status: `open`

**Concurrency note:** `state/debt-backlog/` may be written by overlapping sessions (e.g., `/architecture-audit` running concurrently). Each finding is its own file, so concurrent appends never collide — never rewrite or reorganize another session's entry file. When updating an entry's status, edit only that entry's own YAML file.

### Step 6: Update Health Ledger

1. Check for `state/health-ledger.md`. If it doesn't exist, create it from template:

   ```markdown
   # System Health Ledger

   > Last daily check: YYYY-MM-DD | Last full audit: never

   **Last full audit:** (none — run /architecture-survey)
   **Last targeted audit:** (none — folds into /workweek-complete when >10 days)

   > Next rotation target: [pending first audit]

   ## System Index

   | System | Grade | Status | Last Audited | Open P0 | Open P1 | Open P2 | Lines | Notes |
   |--------|-------|--------|-------------|---------|---------|---------|-------|-------|
   ```

   **Grading anchors:**
   - **A/A+**: No open P0/P1, test coverage >80%, documented architecture, no files >500 lines
   - **B**: No open P0, ≤2 open P1, adequate test coverage, no files >800 lines
   - **C**: Has open P1s OR files approaching size limits OR documented architectural concerns
   - **D**: Has open P0s OR severe debt OR blocks other work
   - **F**: Broken, unmaintainable, or security-critical issues unresolved

   **Status definitions:**
   - **HEALTHY** — No open P0/P1, grade A-B
   - **WATCH** — Has open P2s or grade B-C
   - **ACTION** — Has open P0/P1s
   - **CRITICAL** — Blocks other work, security/correctness issues, or grade D-F

2. Update the `Last daily check` date in the header
3. If findings changed system grades, update the relevant rows
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited)

**Grade synchronization:** The health ledger is the single source of truth for system grades. `/architecture-audit` also updates grades here after weekly audits. When updating a row, read the existing grade first — only change it if the daily review's findings explicitly warrant a grade change. Do not downgrade a system that was just upgraded by a recent `/architecture-audit` run unless new P0/P1 findings justify it.

### Step 7: Write Health Summary

Write results to `state/health/${DATE}-health-summary.md` — this is what workstream-start reads the next morning:

```markdown
# Health Summary

> Generated: YYYY-MM-DD HH:MM by daily-code-health

## Commits Reviewed
- **Period:** [last check] to [now]
- **Commits:** N
- **Files changed:** M
- **Domains covered:** [list] | **Domains skipped (minority):** [list or none]

## Findings
- **Total:** N (X applied, Y deferred to debt backlog)
- **By severity:** P0: A, P1: B, P2: C

## Systems Affected
| System | Grade Change | Notes |
|--------|-------------|-------|
| [system] | B → B | No issues found |
| [system] | B → C | 2 new P1 findings |

## Action Items for Next Session
- [List any P0/P1 items that need attention]
- [List any deferred findings that should be prioritized]
```

### Step 8: Commit and Update Timestamp

Stage only the files this run wrote — the ledger, today's health summary, and the specific new `state/debt-backlog/<date>-<slug>.yaml` entry file(s) if findings were deferred (never a `state/debt-backlog/*.yaml` glob — that would sweep in entries other sessions wrote):

```bash
git add state/health-ledger.md state/health/${DATE}-health-summary.md state/debt-backlog/<date>-<slug>.yaml
```

Then commit — no pathspec needed here since the staged set is already scoped to exactly those files:

```bash
git commit -m "daily-code-health: review of commits since [date]"
```

## Cost

1 Sonnet `code-reviewer` dispatch (with `--problems-only`) + 1 Sonnet `review-integrator` dispatch if findings exist. No persona, no Opus at this nightly cadence. ~5-10 min for a typical day's commits.

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| No new commits since last check | All work landed before the last check timestamp | Update timestamp, report "No new commits since last health check," and exit gracefully. Do not treat as an error. |
| Reviewer dispatch fails (529 overload or crash) | Model overload during Step 3 dispatch | Re-dispatch once after 60s with reduced scope (summary of changed files only, no full diff). If second failure, log `SKIPPED — reviewer dispatch failed` in health-summary and proceed to Step 6 with no findings applied. |
| Review-integrator fails (Step 4) | Agent crash or context limit after reviewer returns findings | Defer all reviewer findings to debt-backlog as unreviewed entries (source: `daily-health/integrator-failure/{date}`). Log in health-summary: "Integrator failed — N findings deferred unreviewed." |
