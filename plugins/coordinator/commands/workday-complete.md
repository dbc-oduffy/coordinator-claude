---
description: End-of-day orchestration — validate, consolidate branches, daily review, append to week-changelog
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Lightweight daily wrap: validate, consolidate branches, run the strategic daily review, append to the week-changelog, and surface staleness signals. **Does NOT merge to main.** Heavy ceremony (docs sweep, ShellCheck, Codex, improvement-queue triage) is weekly — see `/workweek-complete`.

## Design Rationale

Daily is a branch wrap, not a release ceremony. Handoffs archive at their natural trigger; the tracker is touched when the work touches it. The changelog append converts "weekly EM does archaeology" into "weekly EM reads a structured ledger."

---

## Step 1: `/validate` (blocking gate)

```bash
python .github/scripts/run-all-checks.py
```

Capture the exit code — it populates `Validation:` in the changelog block.

- **Build failure:** stop and fix.
- **Non-build failure:** fix what's quick, flag the rest, proceed.

---

## Step 2: RAG Staleness Nudge (informational)

If `ToolSearch` finds any `mcp__project-rag__*` tool, run the staleness survey. Surface in the final summary only if verdict is `stale` or `very-stale`. Skip silently otherwise.

---

## Step 3: Branch Consolidation

0. `~/.claude/plugins/coordinator-claude/coordinator/bin/sync-main.sh` — non-zero exit → report and stop.
1. Discover today's branches: `git branch --list "work/$MACHINE/$TODAY*"` (local + remote).
2. Merge siblings into current branch. Non-trivial conflicts → report and halt.
3. Rebase on `origin/main`; fall back to merge if rebase fails with non-trivial conflicts.
4. `git push origin $(git branch --show-current) --force-with-lease` — on rejection, fetch-rebase-retry once; second failure → report to PM.
5. Delete merged sibling branches: `git branch --merged | grep "work/$MACHINE/$TODAY" | grep -v "$(git branch --show-current)" | xargs -r git branch -d`

Feature branches are excluded — they are intentionally long-lived.

---

## Step 4: Strategic Daily Review

Run `/daily-review`. Produces `archive/daily-summaries/YYYY-MM-DD.md` — feeds the changelog append and the weekly ceremony.

```bash
git push origin $(git branch --show-current)
```

---

## Step 5: Plugin Validation Suite (blocking gate)

```bash
node --test ~/.claude/tests/plugins/run.js
```

Capture exit code for the changelog `Validation:` field.

- **Hook-behavior failures:** blocking — stop and fix.
- **Non-hook failures:** report in summary, flag for morning, do not block git steps.
- **Calibration-sync sentinel:** informational unless Borrow #5 has fully landed.

---

## Step 6: Completed Archive Audit

1. `git log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59"` — gather today's commits.
2. Read `archive/completed/YYYY-MM.md`; find entries under today's heading.
3. Reconcile: add missing entries, fix inaccurate ones, skip trivial commits.
4. If `docs/project-tracker.md` exists, verify completed workstreams have updated status.
5. Report: _"Archive audit: N entries verified, M added, K corrected."_

---

## Step 7: Tier Usage Report

```bash
find "${HOME}/.claude/projects" -name "*.json" -path "*/tier-usage/*" 2>/dev/null | \
while read -r f; do cat "$f"; done | \
python3 -c "
import json, sys
totals = {'tier1': 0, 'tier2': 0, 'tier3': 0, 'tier4': 0}
missing_rationale = 0; sessions = 0
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        data = json.loads(line)
        c = data.get('counts', {})
        for k in totals: totals[k] += c.get(k, 0)
        missing_rationale += sum(1 for d in data.get('tier4_dispatches', []) if not d.get('rationale_present', True))
        sessions += 1
    except Exception: pass
if sessions > 0:
    print(f'Tier usage today ({sessions} sessions): tier1={totals[\"tier1\"]} tier2={totals[\"tier2\"]} tier3={totals[\"tier3\"]} tier4={totals[\"tier4\"]} ({missing_rationale} tier-4 missing rationale)')
" 2>/dev/null || true
```

Skip silently if no tier-usage files exist.

---

## Step 8: Improvement-Queue Depth Nudge (read-only)

Read `~/.claude/tasks/coordinator-improvement-queue.md`. Count `- ` lines in `## Active queue`.

- **≥ 5 entries:** emit in final summary: _"Coordinator-improvement queue: K entries (oldest: YYYY-MM-DD) — consider `/workweek-complete` to triage."_
- **Otherwise:** skip silently.

No triage action at daily cadence — triage is weekly.

---

## Step 9: Append to Week-Changelog

```bash
MACHINE=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
TODAY=$(date +%Y-%m-%d)
CHANGELOG_FILE="tasks/week-changelog/$TODAY-$MACHINE.md"
```

**Staleness guard:** read `tasks/week-changelog/HEADER.md`. If `Week starting:` is set and today is >14 days past it, emit a hard warning and skip the append:
> "WARN: HEADER.md is stale (week started >14 days ago). Was `/workweek-complete` skipped?"

**Synthesise the block** from today's handoffs (`tasks/handoffs/YYYY-MM-DD-*.md`) and the `/daily-review` summary (`archive/daily-summaries/YYYY-MM-DD.md`). Extract `Decisions:` and `Blockers:` from handoff content — do NOT re-author them. `Validation:` is auto-filled from Steps 1 and 5 exit codes — it is not LLM-authored prose.

```markdown
## YYYY-MM-DD — {hostname}

**Branch:** work/{hostname}/YYYY-MM-DD
**Commits:** N (range: <oldest-sha>..<newest-sha>)
**Scope:** <one-line summary from $ARGUMENTS or derived from commit subjects>
**Plans touched:** docs/plans/YYYY-MM-DD-foo.md (status: in-progress|shipped|reverted)
**Handoffs:** tasks/handoffs/YYYY-MM-DD-foo.md
**Decisions:** <extracted from today's handoffs — not re-authored>
**Blockers:** <extracted from handoffs, or "none">
**Validation:** validate=<exit-code-step-1> plugin-suite=<exit-code-step-5>
**Links:** archive/daily-summaries/YYYY-MM-DD.md, archive/completed/YYYY-MM.md
```

Commit and push:
```bash
git add -- "$CHANGELOG_FILE"
git commit -m "chore(week-changelog): daily block $TODAY $MACHINE"
git push origin $(git branch --show-current)
```

---

## Step 10: Weekly Staleness Check

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/check-weekly-staleness.sh
```

- **STALE:** _"Weekly is stale: D days, N commits since last `/workweek-complete`. Run it when ready."_
- **MILD:** _"Weekly cadence: mild staleness. Consider `/workweek-complete` soon."_
- **FRESH / UNKNOWN:** skip silently.

---

## Step 11: Final Summary

```
## Workday Complete

**Validation:** [N checks passed / N failed]
**Branches consolidated:** [N merged into current]
**Branch state:** [branch name], rebased on main, pushed
**Daily review:** [produced archive/daily-summaries/YYYY-MM-DD.md]
**Plugin validation:** [N tests passed / N failures]
**Archive audit:** [N verified, M added, K corrected]
**Week-changelog:** [appended YYYY-MM-DD-{hostname}.md / skipped: reason]
**Weekly staleness:** [STALE / MILD / FRESH]
**NOT merged to main** — use `/merge-to-main` when ready
```

If `$ARGUMENTS` is provided, include as a top line: _"Day summary: {arguments}"_

---

### What This Does NOT Do

- **Merge to main.** Use `/merge-to-main` — it runs the test suite first.
- **Run `/update-docs`.** Weekly cadence only — via `/workweek-complete`.
- **Triage the improvement queue.** Daily depth nudge only; triage is weekly.
- **Run ShellCheck, Codex review, or scc stats.** All moved to `/workweek-complete`.
- **Delete the work branch.** Stays alive for morning review.
- **Delete handoffs.** Never deleted — archived only after `/distill` with PM approval.

### Concurrent Session Safety

Per-machine files under `tasks/week-changelog/` eliminate concurrent-write conflicts. HEADER.md is touched only by the two weekly commands (PM-invoked, serial). Health files are global — workday-complete is the single daily writer.

> **Force-with-lease rejection (Step 3):** fetch-rebase-retry once. Second failure → report to PM.

### Relationship to Other Commands

- **`/merge-to-main`** — deliberate supervised merge; run in the morning.
- **`/daily-review`** — invoked in Step 4; its output feeds Step 9.
- **`/workweek-complete`** — weekly release ceremony: docs sweep, ShellCheck, Codex, triage, version bump, merge.
- **`/workweek-start`** — PM-facing weekly orient; sets priorities in HEADER.md.
