---
description: End-of-day orchestration — update docs, consolidate branches, run health survey
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Update docs, consolidate work branches, and run a health survey. **Does NOT merge to main.** Merging is a deliberate, supervised act via `/merge-to-main`.

## Design Rationale

Main never changes unsupervised or overnight. No live customers are affected by branch state — the splash damage of waiting for the morning is zero. This builds the right habit for when colleagues exist: main is always clean, always supervised.

## Instructions

When invoked, run the full end-of-day sequence. If any step fails, stop and report — don't proceed to later steps on a broken foundation.

### Step 1: Run `/update-docs`

Invoke `/update-docs` for full repo-wide maintenance. This commits and pushes to the current branch.

Wait for it to complete before proceeding.

### Step 1.5: Run `/validate`

Run the local CI validation suite to catch issues before branch consolidation:

```bash
python .github/scripts/run-all-checks.py
```

This discovers and runs all `validate-*.py` and `check-*.py` scripts by convention. Projects add their own build checks here (e.g., `check-ue-build.py`, `check-npm-build.py`, `check-pnpm-build.py`) — the runner finds them automatically.

- **If all checks pass:** Proceed to Step 2.
- **If checks fail:** Report the failures. For build failures, stop and fix — don't push broken code. For non-build failures (linting, file sizes), use judgment: fix what's quick, flag the rest in the final summary.

### Project-RAG Staleness (conditional)

If `ToolSearch` finds any `mcp__holodeck-project-rag__*` tool, run the
staleness-survey script (same invocation as workday-start Step 3.6). If the
verdict is `stale` or `very-stale`, surface it in the evening report:

> **Project-RAG:** {verdict} — last scanned {age}, {code_commits} commits since.
> Suggest running `{recommendation_command}` before tomorrow's first session.

Skip silently if the gate fails or verdict is `current`/`mild`. Evening surfacing
is for sessions that need a reindex *before* tomorrow starts; mild staleness can
wait for morning.

### Step 2: Branch Consolidation

Consolidate all of today's work branches for this machine into one clean branch.

1. **Discover branches:**
   ```bash
   MACHINE=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
   TODAY=$(date +%Y-%m-%d)

   # Local branches for today
   git branch --list "work/$MACHINE/$TODAY*"

   # Remote branches for today
   git branch -r --list "origin/work/$MACHINE/$TODAY*"
   ```

2. **If multiple branches exist:** Merge them into the current branch:
   ```bash
   # For each other branch:
   git merge <other-branch> -m "consolidate: merge <other-branch> into $(git branch --show-current)"
   ```
   If merge conflicts occur: resolve them. If conflicts are non-trivial, report to PM and halt.

3. **Rebase on main:**
   ```bash
   git fetch origin main
   git rebase origin/main
   ```
   If rebase conflicts occur: resolve them. This ensures the consolidated branch is up-to-date with main and ready for morning review.

   If rebase fails with non-trivial conflicts:
   ```bash
   git rebase --abort
   ```
   Fall back to merge:
   ```bash
   git merge origin/main -m "merge main into work branch for consolidation"
   ```

4. **Push the consolidated branch:**
   ```bash
   git push origin $(git branch --show-current) --force-with-lease
   ```
   Force-with-lease protects against concurrent pushes. If it rejects (another session pushed since our last fetch):
   ```bash
   git fetch origin
   git rebase origin/$(git branch --show-current)
   git push origin $(git branch --show-current) --force-with-lease
   ```
   If the second attempt also fails, report the conflict to the PM — do not force-push without `--force-with-lease`.

5. **Clean up merged branches:**
   Delete local branches that were merged into the current branch (except the current branch itself):
   ```bash
   git branch --merged | grep "work/$MACHINE/$TODAY" | grep -v "$(git branch --show-current)" | while read -r branch; do git branch -d "$branch"; done
   ```

**Feature branches are excluded** — they are intentionally long-lived and not part of end-of-day cleanup.

### Step 3: Strategic Daily Review

Run the strategic daily review of today's work. This produces a daily summary artifact and gets an architectural perspective on the day's decisions — checking for lock-in, missed bridging opportunities, and roadmap alignment.

1. Run `/daily-review`
2. The command handles: inventory (Haiku scout), work summary (Sonnet analyst), strategic review (Sonnet persona), health ledger update, and committing all artifacts
3. The daily summary is written to `archive/daily-summaries/YYYY-MM-DD.md` — this feeds `/update-docs`, `/distill`, and the next morning's orientation
4. Push to remote after daily review completes — results are safe even if machine shuts down:
   ```bash
   git push origin $(git branch --show-current)
   ```

**Note:** `/code-health` (detailed code-level review) is still available on-demand but is no longer the default end-of-day check. Our review-heavy build pipeline already catches code-level issues; end-of-day focuses on strategic alignment.

### Step 3.4: Plugin Validation Suite

Run the plugin infrastructure test suite to catch marketplace registration errors, missing files, broken hooks, and invalid frontmatter before they cause boot failures:

```bash
node --test ~/.claude/tests/plugins/run.js
```

- **If all tests pass:** Report: _"Plugin validation: N tests passed across M plugins."_
- **If tests fail:** Report failures in summary. These are structural issues that will cause boot errors — flag as actionable for morning.
- **Does not block** subsequent workday-complete steps — plugin issues don't affect git operations.

### Step 3.5: Refresh Code Statistics

If `scc` is available (check `scc` then `~/bin/scc`), run a fresh count:
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```
Include the compact summary (total lines, top 5 languages) in the final summary. This establishes a daily snapshot of project scale. If not installed, note in summary: _"scc not available — install for code stats."_

### Step 3.6: Completed Archive Audit

Verify that `archive/completed/YYYY-MM.md` accurately reflects what shipped today. Session-end writes individual entries, but sessions may skip `/session-end`, entries may be vague, or ad-hoc work may slip through.

1. **Gather the day's activity from all sources:**

   **Git commits:**
   ```bash
   TODAY=$(date +%Y-%m-%d)
   git log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59"
   ```

   **Session memory:** If the remember plugin is active, read the day's compressed log for richer context than commit messages alone. Memory files live under the project's memory directory:
   ```bash
   TODAY=$(date +%Y-%m-%d)
   SLUG=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
   # Today's daily summary (most useful — grouped by time block)
   # Read: ~/.claude/projects/<slug>/memory/sessions/daily/YYYY-MM-DD.md
   # Current session buffer (not yet compressed)
   # Read: ~/.claude/projects/<slug>/memory/sessions/current.md
   ```
   Use the Read tool to load these files. They contain Haiku-summarized records of every session's activity — including exploration, debugging, and research that doesn't produce commits. Use them to enrich archive entries beyond what git log alone captures, and to catch work that was done but not committed (e.g., research sessions, failed approaches that informed later work).

2. **Read the current month's archive:** `archive/completed/YYYY-MM.md`. Find entries under today's `## YYYY-MM-DD` heading.

3. **Reconcile commits → archive:** Group related commits into logical work items (same feature/fix = one item). For each work item:
   - **Present in archive:** Verify the description is accurate and the commit hash is correct. Fix inaccuracies in place.
   - **Missing from archive:** Append an entry. Use the same format: `- **[Past-tense description]** — [category] | commit: [hash]`
   - **Trivial commits** (formatting, typos, merge commits, quick-saves): skip — the archive records *what shipped*, not every keystroke.

4. **Reconcile archive → commits:** Check each archive entry for today against the commit log. Flag any entry that doesn't correspond to a real commit — this catches copy-paste errors or entries from a session that was abandoned before committing.

5. **Check tracker alignment:** If `docs/project-tracker.md` exists, verify that any workstream marked as completed today in the archive also has its tracker status updated. Fix mismatches in place.

6. **Report:** Include in the Final Summary:
   - _"Archive audit: N entries verified, M added, K corrected."_
   - Or: _"Archive audit: no commits today."_

**Why at end-of-day:** Individual sessions write entries via `/session-end`, but this is the backstop — one authoritative pass across the full day's work. It catches sessions that crashed, skipped session-end, or wrote incomplete entries.

### Step 3.7: ShellCheck Sweep

If `shellcheck` is available, run it across all tracked `.sh` files in the repo:
```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **If issues found:** Report them and offer to fix. Most shellcheck findings are quick mechanical fixes (quoting, unused variables, POSIX pitfalls). Fix what's straightforward; flag anything that changes behavior for PM review.
- **If clean:** Report: _"ShellCheck: all .sh files clean."_
- **If shellcheck not installed:** Note in summary: _"shellcheck not available — install for shell script linting."_

This is end-of-day cleanup — a good time to catch lint that accumulated during rapid development.

### Step 3.8: Codex Review Gate (second-opinion)

Run a Codex review of the day's diff against main as an independent-model second opinion on code quality. This is **on by default** — Codex (GPT-5.4) provides a different model family's perspective on the same changes that the daily review covered. Blind spots may be correlated within a model family; Codex mitigates this by providing an independent sample.

1. **Check diff exists:**
   ```bash
   git diff --shortstat origin/main...HEAD
   ```
   If no changes exist against main, skip: _"Codex review gate: no diff against main — skipped."_

2. **Run Codex review:**
   Invoke the `codex-review-gate` skill (reads scope and base from context).

3. **Assess result by exit code:**

   **Exit code 0 (success):** Include Codex findings in the Final Summary. If Codex found issues:
   - P0/P1 findings: flag to PM in the summary — these should be addressed before merging to main
   - P2 findings: note in summary, defer to next session
   - Clean verdict: note in summary as confirmation

   **Non-zero exit code (graceful fallback):** This is expected when Codex credits are limited or the CLI isn't set up. Report the skip reason and continue — the daily review from Step 3 is sufficient on its own:
   - _"Codex review gate skipped: {reason}. Daily review from Step 3 stands as the sole review."_

4. **Do not block end-of-day on Codex failure.** The daily review already provides strategic and code-level perspective. Codex is additive — a different model family's perspective — not a replacement.

### Step 4: Final Summary

```
## Workday Complete

**Docs updated:** [yes/no, what changed]
**Validation:** [N checks passed / N failed — describe failures]
**Branches consolidated:** [N branches merged into current]
**Branch state:** [branch name], rebased on main, pushed to remote
**Health survey:** [N findings / clean / skipped]
**Plugin validation:** [N tests passed / N failures — describe]
**Code stats:** [total lines / top language breakdown, or "scc not available — install for code stats"]
**Archive audit:** [N entries verified, M added, K corrected / no commits today]
**Shell lint:** [N issues found and fixed / clean / shellcheck not available — install for linting]
**Codex review gate:** [N findings (X P0/P1, Y P2) / clean / skipped: {reason}]
**Orientation cache:** [refreshed by /update-docs / not present]
**NOT merged to main** — use `/merge-to-main` when ready (runs test suite first)
```

If `$ARGUMENTS` is provided, include it as a summary line at the top: _"Day summary: {arguments}"_

### What This Does NOT Do

- **Merge to main.** Use `/merge-to-main` for that — it runs the test suite first.
- **Delete the work branch.** It stays alive for morning review.
- **Auto-push to main.** Main is supervised-only.
- **Delete handoffs.** Handoffs are archived (moved to `archive/handoffs/`) by `/update-docs`, but never deleted. Only `/distill` may delete handoffs after careful knowledge extraction and PM approval.

### Concurrent Session Safety

Health files (`tasks/health-ledger.md`, `tasks/health-summary.md`, `tasks/debt-backlog.md`) are global to the project. Only one session should write them — the workday-complete session is inherently single-writer (runs at end of day). Session-start health surface is read-only.

> **Force-with-lease rejection:** Branch consolidation (Step 2) uses `--force-with-lease` which will safely reject if another session pushed to the same branch after our last fetch. If rejection occurs, fetch-rebase-retry once. If that also fails, report to PM.

### Relationship to Other Commands

- **`/merge-to-main`** is the separate, deliberate merge skill. Run it in the morning after reviewing the branch.
- **`/update-docs`** is invoked as Step 1 of this command.
- **`/daily-review`** is invoked as Step 3 for the strategic daily review.
- **`/code-health`** is available on-demand for detailed code-level review but no longer the default end-of-day check.
- **`/codex:review`** is invoked in Step 3.8 for independent-model code review. Graceful fallback if Codex is unavailable or credits are exhausted.
