---
name: tracker-maintenance
description: "Maintain the unified project tracker at docs/project-tracker.md — marks completion, archives shipped work, updates dependencies, and sweeps for untracked commits. This skill should be used when the user asks to clean up or update the project tracker, archive completed work, check for untracked commits, or resolve stale dependencies. Invoked by /update-docs (Phase 5) or standalone."
version: 1.0.0
---

# Tracker Maintenance

## Prerequisites

- `docs/project-tracker.md` must exist. If the caller signals a `tracker_missing` flag, **skip this skill entirely** — the tracker needs a PM + EM conversation to establish before it can be maintained.
- Check for `archive/completed/` directory — create it if missing.

## Two-Altitude Model

Projects may have two trackers:

- **Strategic tracker:** `docs/project-tracker.md` — workstream-level, maintained by this skill
- **Tactical tracker:** e.g., `docs/plans/consolidated-execution-tracker.md` — chunk-level detail, file conflicts, wave scheduling; maintained by executor agents during execution

This skill **reads** the execution tracker to detect tactical completions, then **cascades them upward** to the strategic tracker. This is the Jira-style auto-roll-up: chunk completions in the execution tracker become workstream progress in the project tracker.

## Steps

### Step 1: Identify Completed Items

**From the strategic tracker:** Read `docs/project-tracker.md`. Find all items marked `[x]` (completed checkboxes) in any section.

**From the execution tracker (cascade):** If a tactical execution tracker exists (check `docs/plans/` for files matching `*-execution-tracker.md` or `*-tracker.md`; if multiple match, use the most recently modified), read it and identify chunks/items marked complete that represent progress on strategic workstreams. For each tactical completion that maps to a strategic item, ensure the strategic tracker reflects that progress — either by checking off a strategic item if all its constituent chunks are done, or by updating the workstream status note.

For each completed item, record:
- The item text
- Which workstream it belongs to (the `### Workstream Name` heading it falls under)
- Any spec/plan file it links to
- Today's date as the completion date

### Step 2: Archive Completed Items

Open (or create) `archive/completed/YYYY-MM.md` where YYYY-MM is the current month.

**If creating a new file**, use this template:
```markdown
# Completed Work — [Month Year]
```

**For each completed item**, append an entry under a date heading:
```markdown
## YYYY-MM-DD
- **[Concise past-tense description]** — spec: [path/to/spec.md] | workstream: [Name]
```

Rules for the archived description:
- Rewrite the description to **concise past-tense** (e.g., "Implement nav mesh v2" becomes "Implemented nav mesh v2")
- Strip planning detail — the archive is a record of what shipped, not how it was planned
- Always include the spec link if one exists in the tracker item
- Always include the workstream name

If today's date heading already exists in the file (from a prior run today), append under it rather than creating a duplicate heading.

### Step 3: Prune Completed Items from Tracker

Remove completed items from `docs/project-tracker.md` according to these rules, applied **in order**:

1. **Prior-month rule:** If any `[x]` item has an archive timestamp from a previous month (i.e., it was already in the tracker as completed from before this month), remove it unconditionally. On the 1st of any month, this means all prior completed items are cleaned out.

2. **Current-month, dependency rule:** If a completed `[x]` item from this month has other tracker items that reference it in a `**depends on:**` or `**blocked by:**` annotation, **keep it** in the tracker (struck through: `- [x] ~~Description~~ → archived YYYY-MM`). It serves as evidence that the dependency is resolved.

3. **Current-month, no dependency:** If a completed `[x]` item from this month has NO downstream items depending on it, remove it from the tracker.

4. **Length check:** After pruning, if the tracker still has more than 8 completed `[x]` items visible, prune further — keep only those that unblock downstream work. Archive the rest.

### Step 4: Update Workstream Statuses

For each workstream section (`### Workstream Name`):

1. Read the **Status:** field
2. If all items in the workstream are now `[x]`, update status to `Complete` and add a completion date
3. If the workstream has a mix of `[x]` and `[ ]`, leave status as-is (the existing status like "Executing" or "Enrichment" reflects pipeline position, which is a PM/EM call — don't change it)
4. If a workstream is marked `Complete` and has no remaining items, leave it for one `/update-docs` cycle, then remove it on the next run (moving it entirely to the archive)

### Step 5: Check Dependency Freshness

Scan all `**depends on:**` and `**blocked by:**` annotations in pending `[ ]` items:

1. If the referenced item/spec is now completed (appears in `[x]` items or in the archive), **remove the dependency annotation** — the blocker is resolved
2. If the referenced item is still pending, leave the annotation
3. If the reference points to something that doesn't exist (dead link), flag in your output: `"WARNING: Dead dependency reference in tracker: [item] depends on [missing ref]"`

### Step 6: Sweep for Untracked Completed Work

Safety net: catch work that completed without ever entering the tracker or archive. This happens with bug fixes, ad-hoc requests, and tasks dispatched for speed without formal specs.

1. **Scan recent commits:** `git log --oneline` since the last `/update-docs` run (or last 50 commits if no prior run is detectable)
2. **Compare against tracker + archive:** For each substantive commit, check if the work appears in either `docs/project-tracker.md` (as `[x]`) or in `archive/completed/YYYY-MM.md`
3. **Append orphaned work to archive:** For commits representing real work not captured anywhere:
   ```
   - **[Concise past-tense description]** — ad-hoc [bug fix|task|refactor] | commit: [hash]
   ```
4. **Group related commits** into single archive entries. Skip doc-only commits, merge commits, and quick-saves. The archive records what shipped, not every keystroke.

This step is deliberately last — it runs after tracker maintenance so it doesn't double-count items that were just archived from the tracker.

### Step 7: Workstream Count Check

Count active workstreams (those with status other than `Complete`).

- If count > 5: flag in your output: `"NOTE: {N} active workstreams — exceeds recommended limit of 5. Consider moving least-active workstream to Backlog."`
- This is informational only — do not reorganize workstreams yourself

## Project Tracker Format Reference

The unified project tracker at `docs/project-tracker.md` follows this structure. This is the format this skill expects to parse — if a project's tracker deviates, normalize it.

```markdown
# Project Tracker — [Project Name]
**Last updated:** YYYY-MM-DD
**Overall status:** [one-line summary of project state]

## Active Workstreams

### 1. [Workstream Name]
**Status:** Executing | Enrichment | Review | Blocked | Ready
**Specs:** path/to/spec.md, path/to/other-spec.md

- [ ] Engineering deliverable — **depends on:** [item or blocker]
- [ ] Another deliverable — **spec:** path/to/spec.md
- [ ] _PM: Non-engineering action item_ ← italic, lightweight stub
- [x] ~~Completed thing~~ → archived YYYY-MM

### 2. [Workstream Name]
...

(max ~5 active workstreams)

## Backlog
Items that are real but not imminently actionable.
- Future item — brief context
- Another future item

## Archive Pointer
→ Completed work: archive/completed/
→ Latest: archive/completed/YYYY-MM.md
```

**Conventions:**
- **Engineering items** are the primary content — detailed enough to orient an agent
- **PM items** are italic stubs prefixed with `_PM:_` — just enough to show dependency relationships, no detail needed
- **Dependencies** use `**depends on:**` or `**blocked by:**` inline annotations
- **Spec links** use `**spec:**` inline annotations
- **Workstream limit:** ~5 active. More than 5 triggers a warning in the report.
- **Status values** reflect pipeline position: `Ready` → `Enrichment` → `Review` → `Executing` → `Complete`
