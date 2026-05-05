---
description: Weekly strategic orient — surface last week's results, set this week's priorities, update HEADER.md
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: ""
---

# Workweek Start — Weekly Strategic Orient

PM-facing weekly bookend. Sets the week's context, surfaces carryover, and writes priorities into `tasks/week-changelog/HEADER.md`. Distinct from `/workday-start` (tactical daily orient) — this is the workstream-boundary ceremony.

**Design contract:** handoffs are the atom; HEADER.md is the weekly index header. This command reads existing artifacts (changelog, tracker, handoffs) — it does not reconstruct or re-author them.

---

## Step 0: Bootstrap HEADER.md (first-run only)

If `tasks/week-changelog/HEADER.md` does not exist, create it with the seed template below before proceeding. This lets the command run on a fresh project without manual setup.

```markdown
# Week Changelog

<!-- Directory convention:
     tasks/week-changelog/ holds the current week's changelog state.
     HEADER.md (this file) is written by /workweek-complete on reset and by
     /workweek-start on re-run. It is the only shared file in this directory
     — all other files are per-machine daily blocks (YYYY-MM-DD-{hostname}.md)
     written by /workday-complete, which avoids concurrent-write conflicts.

     On /workweek-complete, the full directory (daily files + old HEADER) is
     archived to archive/week-changelogs/<week-start>/ before HEADER is rewritten.
     bin/check-weekly-staleness.sh reads this file to compute the staleness signal.
-->

**Week starting:** (run /workweek-start to initialise)
**Prior week released:** (run /workweek-complete to record)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):**
- [ ] (run /workweek-start to set priorities)
```

Step 5 will populate `Week starting:` and `Last /workweek-start:` with today's date and write the priorities the PM sets. `Prior week released:` stays as the placeholder until the first `/workweek-complete` runs.

If the file already exists, skip this step silently — do not overwrite an existing HEADER.

## Step 1: Read Week-Changelog (prior week)

Glob `tasks/week-changelog/*.md` excluding HEADER.md. Sort by filename (date-then-hostname order). Read each daily file.

Surface a brief prior-week digest:
- **Days covered:** count unique dates across daily files.
- **Shipped:** list plans with status `shipped` across all `Plans touched:` fields.
- **Blockers carried over:** any `Blockers:` fields that weren't cleared by end of week.
- **Priorities met vs. missed:** read `HEADER.md` `Priorities` section; for each, indicate met (plan shipped or handoff closed) or missed.

If no daily files exist, skip this step: _"No prior-week changelog found — this may be the first run."_

---

## Step 2: Read Tracker — Stalled Workstreams

If `docs/project-tracker.md` exists, read it. Identify workstreams whose referenced branches have had no commits in >7 days:

```bash
# For each branch referenced in the tracker:
git log --oneline --since="7 days ago" -- <branch> 2>/dev/null | wc -l
```

Surface stalled workstreams (zero recent commits) as a bulleted list. This gives the PM a concrete picture of what needs attention vs. what's moving.

---

## Step 3: Orphan Sweep

Scan for aging artefacts that may need pruning or deferral:

1. **Stale handoffs:** `tasks/handoffs/*.md` older than 7 days (by filename date). List filenames.
2. **Draft plans without recent commits:** `docs/plans/*.md` with `status: draft` (grep frontmatter or body) and no commits to their referenced paths in >14 days.

Surface as a brief list for PM awareness. No archival action — this command is read-and-surface only.

---

## Step 4: Surface Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md` and any analogous `tasks/*-recheck-due-*.md` files. For files whose date component falls within the coming 7 days, read the first few lines and surface the recheck item.

If none found, skip silently.

---

## Step 5: PM Dialogue — Set Priorities

Present the digest from Steps 1–4, then ask:

> "Given last week's results and current state, what are 1–3 priorities for this week?"

**Wait for the PM's response.** Write the answer verbatim (as a checklist) to `tasks/week-changelog/HEADER.md` in the `Priorities` section. Mirror to `docs/project-tracker.md` if it exists (append under a `## Week of YYYY-MM-DD` heading or update an existing one). HEADER.md is canonical; the tracker copy is for visibility.

---

## Step 6: Reset-or-Update Decision

This is the critical branch in the command. Read `tasks/week-changelog/HEADER.md`:

```
**Last /workweek-start:** YYYY-MM-DD  (or "(none)")
**Prior week released:** vX.Y.Z (commit abc1234, YYYY-MM-DD)
```

**Decision logic:**

If `Last /workweek-start:` is `(none)` OR `Prior week released:` commit is newer than the `Last /workweek-start:` date — a `/workweek-complete` has occurred since the last `/workweek-start`, meaning we are starting a genuinely new week:

→ **Full reset:**
1. Read `Week starting:` from HEADER.md to get the prior week's start date for the archive path.
2. Create `archive/week-changelogs/<prior-week-start>/` and move all daily files (`tasks/week-changelog/YYYY-MM-DD-*.md`) there. Do NOT move HEADER.md.
3. Write a fresh HEADER.md:
   ```markdown
   # Week Changelog

   **Week starting:** YYYY-MM-DD  (today's date)
   **Prior week released:** <version> (commit <sha>, <date>)  (from the prior HEADER)
   **Last /workweek-start:** YYYY-MM-DD  (today's date)
   **Priorities (from /workweek-start):**
   - [ ] <priority 1 from PM>
   - [ ] <priority 2 from PM>
   - [ ] <priority 3 from PM>
   ```

If `Last /workweek-start:` is set AND no `/workweek-complete` has occurred since (i.e., `Prior week released:` commit predates `Last /workweek-start:`) — this is a mid-week re-run:

→ **Update in place:**
1. Update the `Priorities` section with the new priorities from Step 5.
2. Update `Last /workweek-start:` to today's date.
3. Leave daily files untouched.

**In both cases,** commit the HEADER.md change:
```bash
git add -- tasks/week-changelog/HEADER.md
git commit -m "chore(workweek-start): set week priorities $(date +%Y-%m-%d)"
git push origin $(git branch --show-current)
```

If a full reset moved daily files, include them in the same commit:
```bash
git add -- tasks/week-changelog/ archive/week-changelogs/<prior-week-start>/
git commit -m "chore(workweek-start): archive prior week, reset changelog $(date +%Y-%m-%d)"
git push origin $(git branch --show-current)
```

---

## Output

After completing all steps, emit a brief summary:

```
## Workweek Start

**Prior week:** [D days, N shipped, K blockers carried over — or "no prior record"]
**Stalled workstreams:** [list or "none"]
**Stale handoffs:** [list or "none"]
**Upcoming rechecks:** [list or "none"]
**This week's priorities:**
  - [ ] Priority 1
  - [ ] Priority 2
  - [ ] Priority 3
**HEADER.md:** [reset (archived prior week) / updated in place]
```

---

### Relationship to Other Commands

- **`/workday-start`** — tactical daily orient. Not the same ceremony.
- **`/workweek-complete`** — the weekly close; it resets HEADER.md and archives daily files as part of its Step 14. `/workweek-start` detects that reset and does a full re-init.
- **`/pickup`** — gains a "while you were away" surface from the week-changelog; reads HEADER.md to determine week bounds.
