---
description: Weekly release ceremony — validate, update docs, cut release notes, version bump, merge to main, archive
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Reads the week-changelog as the canonical record of what shipped — does NOT reconstruct the week from `git log`. Heavy steps dropped from `/workday-complete` live here: `/update-docs`, ShellCheck, optional Codex review (only if the `codex-review-gate` skill is installed), improvement-queue triage, scc, version bump, and merge.

**Design contract:** the week-changelog is the ledger. The weekly ceremony reads it, validates against it, and archives it. Release notes are drafted from it, not re-derived.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

Glob `tasks/week-changelog/*.md` (daily files, sorted by filename). Read HEADER.md and all daily files.

Surface to PM:

```
Week covers: D days (YYYY-MM-DD to YYYY-MM-DD)
Commits: N (range: <oldest-sha>..<newest-sha>)
Shipped workstreams: <list from Plans touched: shipped fields>
Blockers: <list or "none">
Priorities met: <from HEADER.md priorities vs. shipped plans>
```

Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_

**Wait for PM confirmation before continuing.** This is the single explicit PM gate before the irreversible steps.

---

## Step 2: Full Validation (blocking)

Run the complete validation stack:

```bash
python .github/scripts/run-all-checks.py
node --test ~/.claude/tests/plugins/run.js
```

Any blocking failure → stop and report. Fix before proceeding. Do not proceed to Step 3 on a failing validation.

---

## Step 3: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch.

Wait for completion before proceeding.

---

## Step 4: Improvement-Queue Triage

Read `~/.claude/tasks/coordinator-improvement-queue.md`. Count `- ` lines in `## Active queue`; note the oldest entry date.

**Triage triggers (either condition):** ≥ 5 active entries OR oldest entry is > 14 days ago.

If triggered:
1. Read the queue entries.
2. For each entry, dispatch a small executor per the entry's `proposed target` field.
3. Verify applied entries, then move them from `## Active queue` to `## Processed`.
4. If > 15 entries, treat as a `/staff-session`-style multi-executor sweep.

If not triggered: note in summary — _"Improvement queue: K entries, all ≤ 14 days — no triage needed."_

---

## Step 5: scc Snapshot

If `scc` is available (`which scc` or `~/bin/scc`):
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```

Record the compact summary (total lines, top 5 languages) in `tasks/code-stats-history.md` under a `## YYYY-MM-DD` heading (append; create the file if it doesn't exist). Weekly trend is the signal; daily delta is noise.

If `scc` is not installed: note in summary — _"scc not available — install for weekly code stats."_

---

## Step 6: ShellCheck Sweep

```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **Issues found:** report and offer to fix. Most findings are quick mechanical fixes; fix what's straightforward, flag behavior-changing items for PM review.
- **Clean:** report _"ShellCheck: all .sh files clean."_
- **Not installed:** note in summary.

---

## Step 7: Codex Review Gate (second-opinion, opt-in)

**Skip this entire step unless the `codex-review-gate` skill is installed.** The skill is an opt-in add-on (re-run `setup/install.sh --enable-codex` to add it). When the skill is absent, omit the `Codex review:` line from the Step 15 summary entirely — do not write _"skipped"_ or any other placeholder.

If the skill IS installed:

```bash
git diff --shortstat origin/main...HEAD
```

If no diff against main: _"Codex review gate: no diff against main — skipped."_

Otherwise invoke the `codex-review-gate` skill. Assess by exit code:
- **Exit 0:** include findings in summary. P0/P1 → flag to PM before merge. P2 → note and defer.
- **Non-zero (graceful fallback):** _"Codex review gate skipped: {reason}."_

Do not block the weekly on Codex failure — the daily reviews already provide strategic perspective.

---

## Step 8: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream that appears in the week's `Plans touched: shipped` fields, verify the tracker status is updated to reflect completion. Fix in place.

Report: _"Tracker reconciliation: N workstreams updated."_

---

## Step 9: Draft Release Notes — PM Review Gate

Draft release notes from two sources (do NOT re-author — surface and organise):
1. The week-changelog daily files: `Scope:`, `Decisions:`, `Plans touched: shipped` fields.
2. `archive/completed/YYYY-MM.md`: entries under the week's date range.

Write the draft to `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` (use today's date; version is a placeholder until Step 10 confirms it).

Present the draft to PM: _"Release notes drafted. Does this capture the week accurately?"_

**Wait for PM review.** The PM may request edits before proceeding.

---

## Step 10: Version Bump — PM Confirmation Gate

Propose a semver increment based on changelog content:
- **Major:** breaking change noted in any `Decisions:` field.
- **Minor:** new feature or new command shipped (`Plans touched: shipped` with new commands/skills).
- **Patch:** fixes, doc updates, refactors only.

Present to PM: _"Proposed: vX.Y.Z (rationale: [one line]). Confirm or adjust."_

**Wait for PM confirmation.** Update the release-notes filename and HEADER.md `Prior week released:` value to the confirmed version.

---

## Step 11: `/merge-to-main`

Invoke `/merge-to-main` only after PM has confirmed release notes (Step 9) and version (Step 10). Do NOT inline merge logic — the skill handles pre-merge test suite, PR creation, and merge.

---

## Step 12: Artifact Consolidation

Invoke `coordinator:artifact-consolidation` on shipped plans and consumed handoffs from this week. This moves finalised artifacts into archive and updates the docs index.

---

## Step 13: Health Survey

Run the full health survey if available (e.g., `/health` or equivalent). Record output in `tasks/health-ledger.md` under today's date.

---

## Step 14: Reset Week-Changelog

Archive and reset the week's state:

1. Determine the current `Week starting:` date from HEADER.md — this is the archive path key.
2. Create `archive/week-changelogs/<week-starting>/`.
3. Move all daily files (`tasks/week-changelog/YYYY-MM-DD-*.md`) to the archive path. HEADER.md is NOT moved — it gets rewritten in place.
4. Write a fresh HEADER.md with the released version and a cleared `Last /workweek-start:` line:

```markdown
# Week Changelog

<!-- Directory convention: [see HEADER.md comment block] -->

**Week starting:** (not yet set — run /workweek-start to initialise)
**Prior week released:** vX.Y.Z (commit <merge-sha>, YYYY-MM-DD)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):**
- [ ] (run /workweek-start to set priorities)
```

5. Commit everything:
```bash
git add -- tasks/week-changelog/ archive/week-changelogs/<week-starting>/
git commit -m "chore(workweek-complete): archive week <week-starting>, reset changelog vX.Y.Z"
git push origin $(git branch --show-current)
```

---

## Step 15: Final Summary

```
## Workweek Complete

**Week:** YYYY-MM-DD to YYYY-MM-DD (D days, N commits)
**Shipped:** [list of shipped workstreams]
**Version:** vX.Y.Z
**Release notes:** archive/release-notes/YYYY-MM-DD-vX.Y.Z.md
**Validation:** [pass / failures described]
**Docs updated:** [/update-docs completed]
**Improvement queue:** [K entries processed / no triage needed]
**Code stats:** [summary or "scc not available"]
**ShellCheck:** [clean / N issues fixed]
<!-- include only when codex-review-gate skill is installed -->
**Codex review:** [N findings / clean / skipped: reason]
**Tracker:** [N workstreams updated]
**Merged to main:** [yes — PR #N / blocked: reason]
**Week-changelog:** archived to archive/week-changelogs/<week-starting>/, HEADER.md reset
**Next:** run /workweek-start to set priorities for the new week
```

---

### What This Does NOT Do

- **Auto-fire.** This is PM-invoked. `/workday-complete` surfaces the staleness signal.
- **Re-author the week from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 11 delegates to `/merge-to-main` which handles the PR.
- **Delete release notes or handoffs.** Only daily changelog files are archived; release artifacts stay.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects the HEADER reset done in Step 14 and re-inits cleanly.
- **`/merge-to-main`** — invoked in Step 11; not duplicated.
- **`/update-docs`** — invoked in Step 3; not duplicated.
- **`bin/check-weekly-staleness.sh`** — the informational script surfaced by `/workday-complete` to nudge PM toward this command.
