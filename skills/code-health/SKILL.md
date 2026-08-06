---
name: code-health
description: "Night-shift code review — dispatch reviewer, apply findings, track."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: (no arguments needed)
---

# Code Health — Night Shift Commit Review

The "night shift colleague." Queries today's completion entries to identify the surfaces that saw recorded work, dispatches a domain-appropriate reviewer with `--problems-only`, applies findings inline via review-integrator, defers complex findings to the debt backlog, updates the health ledger with current grades, and writes a morning-ready summary. Results are waiting at the next workstream-start.

**Announce at start:** "I'm using /code-health to review recent commits."

---

## Never Skip on a "Small" Day

The strongest predictor of a bug-filled review is a small commit count, not a large one. When today's fixes touched one code path, the adjacent or sibling path is the highest-probability next bug — and a small commit count is exactly when reviewers and EMs are most tempted to skip ("only 8 commits, nothing to see"). That's where the regressions hide.

**Run this review on every committed day, regardless of commit count.** The cost-benefit is asymmetric: a 5-minute review on a quiet day catches the silent regression a fix introduced on a parallel handler; skipping a busy day misses bugs the next session will trip on.

The only valid skip condition is the one already in the Failure Modes table: **zero new commits since last check** (on the git-log fallback path) or **zero completion entries today with no fallback commits either.** Anything else — even a single completion entry or commit — run the review.

---

## Step 1: Identify Surfaces from Today's Completion Entries

Determine the scope of surfaces to review from today's completion log, not from raw commit history:

1. Query today's completion entries:
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --where "created=<YYYY-MM-DD>" --format json
   ```
   Substitute today's date for `<YYYY-MM-DD>`.
2. Extract the file paths or subsystem names mentioned in the entries' `title`, `description`, and any `files` fields.
3. **If no entries for today:** Read `state/health-ledger.md` header for the `Last daily check:` date and fall back to `git log --since="<last-check-date>" --oneline --stat`. Update the `Last daily check` timestamp in the health ledger, report "No completion entries for today — fell back to git log scope," and continue with the commit-based surface list.

The completion-entry approach reduces tokens spent re-reviewing unchanged code by scoping the review to only the surfaces that saw recorded work today.

---

## Step 2: Generate Diff Scope

Scope the diff to the surfaces identified in Step 1 (`git diff HEAD -- <file1> <file2> ...`).

If Step 1 yielded a subsystem or directory name rather than individual files, use the directory prefix (e.g., `skills/code-health/`). If the fallback git-log path was taken, diff from the last-check commit instead (`git diff <last-check-commit>..HEAD`).

Summarize scope: which files changed, how many insertions/deletions, which systems are affected. This summary drives the Sonnet reviewer's emphasis (vocabulary/what-to-weight) in Step 3 — not reviewer selection (that's always `code-reviewer`).

---

## Step 3: Dispatch the Sonnet Reviewer (non-persona)

The nightly health pass dispatches the **Sonnet `code-reviewer`** (`agents/code-reviewer.md`) — **NOT** a named persona. This is recurring Sonnet-tier code review, which by doctrine uses `code-reviewer`, never a persona (personas are Opus-only and reserved for the weekly arch pass, the merge gate, and explicit architectural decisions). Routing a *nightly* health check to an Opus persona is the same daily-cadence miscalibration `/workday-complete` Step 4c was corrected for.

Domain still matters — but for **vocabulary and emphasis**, not reviewer identity. State the dominant change type in the brief so the Sonnet reviewer knows what to scrutinize:

| Dominant change type | Tell the reviewer to weight… |
|---|---|
| Game dev / Unreal Engine | UE idioms, engine-lifecycle/ownership, Blueprint/C++ seams |
| Frontend / UI | component/token reuse, state flow, accessibility |
| Data / ML / science | numeric correctness, data contracts, reproducibility |
| Mixed, backend, or architecture | coupling, error paths, interface seams |

If multiple domains are present, weight toward the dominant one (most files changed / most critical path). A finding that genuinely needs persona/Opus judgment is **flagged for the weekly arch pass** (`/workweek-complete` Step 7.5), not escalated to an Opus dispatch here.

**Dispatch (unattended — required):** `coordinator:code-reviewer` writes to its spawn-provisioned sidecar; no EM ceremony needed.

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED — no `name:` param), `run_in_background: true`, `--problems-only`. The sidecar is spawn-provisioned before the reviewer runs (`report_sidecar:`-eligible in `subagent-sandbox-policy.yaml`, provisioned by the `enforce-agent-dispatch-mode.py` hook) and arrives in the brief as `sidecar_path:` at the standard session-keyed home `state/subagent-share/<session-id>/<provision_key>.md`. The reviewer fills it with findings and returns `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. There is no EM pre-scaffold and no reviewer self-scaffold — a "no sidecar path in my brief" return is a provisioning defect for the EM to fix, not a gap to route around.
2. Read the returned `DONE: <path>` line when notified of completion. Pass that path to the integrator in Step 4.

---

## Step 4: Apply Findings

If the reviewer returns findings:

1. Dispatch `coordinator:review-integrator` pointing at the **on-disk sidecar path** (not inline findings — `agents/review-integrator.md` § Intake precondition hard-stops on inline-relayed findings). Pass the sidecar path and affected file paths.
2. Review-integrator applies inline fixes and annotations.
3. **Complex findings** — those requiring 3+ interacting files or new abstractions — go to the debt backlog (Step 5) instead of inline application.

If no findings: skip to Step 6.

---

## Step 5: Update Debt Backlog

For any findings not fixed inline, record each as a debt-backlog YAML entry using `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema debt-backlog`. This writes `state/debt-backlog/<date>-<slug>.yaml` (one file per finding; no markdown table).

Required fields per entry:
- **`title`** — one-line noun-phrase summary of the finding
- **`body`** — multi-line prose: what was observed, the structural gap, context (`body: |` block scalar)
- **`source`** — provenance: `daily-health/code-reviewer/{date}`
- **`risk`** — consequence of leaving the debt unaddressed
- **`proposed_action`** — what the EM or a future executor should do
- **`status`** — `open`
- **`created`** — today's date (YYYY-MM-DD)

Stage each resulting YAML file: `git add state/debt-backlog/<date>-<slug>.yaml`

---

## Step 6: Update Health Ledger

1. Check for `state/health-ledger.md`. If it doesn't exist, create it from this template:

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

2. Update `Last daily check` in the header to today's date.
3. If findings changed system grades, update the relevant rows.
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited).

**Grade synchronization:** The health ledger is the single source of truth for system grades. `/architecture-audit` also updates grades here after weekly audits. When updating a row, read the existing grade first — only change it if the daily review's findings explicitly warrant a grade change. Do not downgrade a system that was just upgraded by a recent `/architecture-audit` run unless new P0/P1 findings justify it.

**Grading anchors:**

| Grade | Criteria |
|---|---|
| A / A+ | No open P0/P1, test coverage >80%, documented architecture, no files >500 lines |
| B | No open P0, ≤2 open P1, adequate test coverage, no files >800 lines |
| C | Has open P1s OR files approaching size limits OR documented architectural concerns |
| D | Has open P0s OR severe debt OR blocks other work |
| F | Broken, unmaintainable, or security-critical issues unresolved |

**Status definitions:**

| Status | Trigger |
|---|---|
| HEALTHY | Grade A-B, no open P0/P1 |
| WATCH | Has open P2s, grade B-C |
| ACTION | Has open P0/P1s |
| CRITICAL | Blocks other work, security/correctness issues, grade D-F |

---

## Step 7: Write Health Summary

Scaffold a conformant health-status record, then fill the posture and body from the day's findings:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type health-status --title "Health Summary"
```

Then, via Edit, fill:
- `health:` posture axis — one of `HEALTHY | WATCH | ACTION | CRITICAL` (see Status definitions above)
- `summary:` narrative — one-line overview of the session's health finding
- Body sections (`## Systems Graded`, `## Findings Summary`, `## Action Items for Next Session`) with the day's grading output

Example filled body:

```markdown
## Systems Graded

| System | Grade | Health | Notes |
|--------|-------|--------|-------|
| coordinator-pipeline | B | HEALTHY | No new P0/P1 |
| coordinator-skills | B | WATCH | 2 open P2s |

## Findings Summary

- **Total:** 3 (2 applied inline, 1 deferred to debt backlog)
- **By severity:** P0: 0, P1: 0, P2: 2, P3: 1

## Action Items for Next Session

- Review deferred P2: [finding summary]
```

---

## Step 8: Commit and Update Timestamp

Stage only the ledger and today's health summary — nothing else this run touched:

```bash
git add state/health-ledger.md "state/health/<YYYY-MM-DD>-health-summary.md"
```

Then commit; the staged set is already exactly these two files, so no pathspec is needed:

```bash
git commit -m "daily-code-health: review of surfaces from completion entries [date]"
```

The post-commit hook pushes automatically.

---

## Failure Modes

| Situation | Action |
|---|---|
| No health ledger on first run | Create from template, use last 24 hours as scope |
| No completion entries for today | Fall back to `git log --since=<last-check>` scope; report fallback in health summary |
| `query-completions` CLI not found | Fall back to git-log scope; note missing binary in health summary |
| No new commits since last check (fallback path) | Update timestamp, report, and exit — no reviewer dispatch |
| Reviewer returns no findings | Skip Steps 4-5, proceed directly to Step 6 |
| Debt backlog doesn't exist | Create from template before adding entries |
| Complex finding can't be fixed inline | Add to debt backlog with severity and effort estimate |
| Git commands fail (no commits, detached HEAD) | Report the error and stop — do not attempt to guess the diff |
| review-integrator unavailable | Log findings to `state/health/<date>-health-summary.md` body manually, note as deferred |

---

## Cost

1 Sonnet `code-reviewer` dispatch (with `--problems-only`) + 1 Sonnet `review-integrator` dispatch if findings exist. No persona, no Opus at this nightly cadence. Approximately 5-10 minutes for a typical day's commits. If no findings, the reviewer dispatch is the only cost.

---

## Relationship to Other Commands

- **`/workday-complete`** — primary trigger for this command; runs code-health as part of its end-of-day health survey phase. The normal path is to let `/workday-complete` invoke this, not to run it standalone.
- **`/workstream-start`** — the cockpit snapshot (produced by claude-klabauter's `artifact.emit`, the sole production emitter; `bin/emit-cockpit-snapshot.py` is a thin native entry that dispatches the op via `cc_invoke.route_mutation()`, no bash) and record queries (`query-records`) read `state/health/*.md` to surface overnight findings at the top of the next session. The nested path `state/health/<date>-health-summary.md` is the conformant target (not a flat `state/health-summary.md` — that path is stale and does not exist).
- **`/review-code`** — this command dispatches a reviewer directly with `--problems-only` for targeted code health assessment; it does not go through the full `/review-code` feature-review workflow. Don't substitute one for the other.
- **`pipelines/daily-code-health/PIPELINE.md`** — the pipeline definition this command executes. If you need to customize routing or scope, read it directly.
