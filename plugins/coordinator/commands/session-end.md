---
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session End — Wrap Up Completed Work

Close out a finished vein of work: capture lessons and update documentation to reflect completion. No handoff — this is for work that's *done*, not being passed forward.

## Instructions

When invoked, capture lessons and update plan/project documentation to reflect completion status. If work is incomplete and needs to be picked up later, use `/handoff` instead.

**Design note:** Multiple agents may be running concurrently. This skill closes out ONE agent's session without heavy repo-wide operations that could conflict with other agents.

### Step 1: Capture Lessons

Read `tasks/lessons.md` (if it exists). If anything was learned this session that isn't already captured, add it — but apply the intake filter first:

**Feature scope:** `<feature>` is derived from the current work context:
- If a feature-scoped plan exists at `tasks/<feature>/todo.md`, use that feature name
- If on a `feature/<name>` branch, use `<name>`
- Otherwise, use `tasks/lessons.md` (global)

**What qualifies:**
- Corrections from the user (preferences, workflow, conventions)
- Surprising API behavior or tooling gotchas
- Patterns that worked well or failed
- Debugging insights that would save future sessions time

**What doesn't qualify:** One-off bug fixes, details specific to a single script/pipeline run, or anything already encoded in the code, CLAUDE.md, or MEMORY.md. Before adding, ask: *"Will this save time in the next 4 weeks, or is it just documenting what happened?"*

Add new entries in the established format (bold title + 1-2 sentence rule, max 3 lines). Prefer merging with an existing entry over adding a new one. Skip if nothing new.

### Step 1.5: Final Session Save

Trigger a final memory save to capture the tail end of this session that hasn't been auto-saved. This ensures the session's last work is recorded even if the JSONL delta hadn't reached the auto-save threshold.

Run: `node ~/.claude/plugins/coordinator-claude/remember/lib/pipeline.js save --force`

If the command fails (node not found, plugin not installed), skip silently — session memory is best-effort, not a blocker.

### Step 2: Update Plan Documentation

Find and update relevant plan/task documentation to reflect what was completed:

1. **Find the plan docs — actively search, don't wait to recall.** Check these locations in order:
   - Any plan document referenced or opened during this session (you have it in context)
   - `tasks/<feature>/todo.md` — feature-scoped plans for current work
   - `tasks/plans/` — session handoff plans and tactical trackers
   - `docs/plans/` — historical and reference plans
   - `~/.claude/plans/` — plans written in plan mode (may need copying to canonical location)
   - `tasks/todo.md`, `tasks/plan.md` — legacy flat locations
   If a plan exists for the work this session touched, read it and update it. Don't rely on having opened it earlier — sessions that start from handoffs or dive straight into code often never explicitly open the plan.
2. **Mark completed items:** Check off finished tasks, update status fields, add completion notes where appropriate.
3. **Add a review section** (if not already present) summarizing outcomes — what was built, key decisions, anything notable about the result.
4. **Update other pertinent docs:** If the work affected README files, architecture docs, or other project documentation that should reflect the new state, update those too. Use judgment — only touch docs that are clearly stale as a result of this session's work.

### Step 2.5: Doc-Alignment Insurance

End of session is the last chance to ensure status fields match reality. This catches work that completed but whose status wasn't updated — common after compaction or rapid context shifts.

1. **Check active chunk/stub docs:** If this session worked on chunk stubs (files with `**Status:**` fields in `docs/active/`, `docs/plans/`, or similar), verify their status reflects what actually happened:
   - If the work is complete but status says "in progress" → update to complete
   - If the work is blocked but status says "in progress" → update to blocked with reason
   - If the status is already correct, skip
2. **Check execution tracker:** If a tactical execution tracker exists (e.g., `docs/plans/consolidated-execution-tracker.md`), verify that chunks worked on this session have accurate status entries
3. **Lightweight pass only.** Read what's in your conversation context — don't re-read every file in the project. If you have no memory of working on tracked chunks, skip this step entirely.

### Step 2.6: Archive Uncaptured Work

Sweep the session's commits for completed work that isn't already in the project tracker (`docs/project-tracker.md`) or the completion archive (`archive/completed/YYYY-MM.md`). This catches bug fixes, ad-hoc requests, and quick tasks that bypassed the spec pipeline.

1. **Scan session commits:** `git log --oneline` for commits since the session started (or since the last `/session-end`/`/update-docs`)
2. **Check against tracker + archive:** For each substantive commit (skip merge commits, doc-only commits, quick-saves), check if the work is already represented in either the tracker or the current month's archive
3. **Append missing entries:** For any untracked completed work, append to `archive/completed/YYYY-MM.md`:
   ```
   ## YYYY-MM-DD
   - **[Concise past-tense description]** — ad-hoc [bug fix|task|refactor] | commit: [hash]
   ```
4. **Judgment filter:** Not every commit is a work item. Group related commits into a single archive entry. Skip trivial commits (typo fixes, formatting). The archive records *what shipped*, not every keystroke.

**Skip if** no `archive/` directory exists and no `docs/project-tracker.md` exists — the project hasn't adopted unified tracking yet.

### Step 2.7: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/session-start` and `/workday-start`. These are lightweight, targeted patches based on what THIS session accomplished, not a full regeneration.

1. **Orientation cache** (`tasks/orientation_cache.md`): If it exists, patch sections affected by this session's work:
   - Update `Active Workstreams` if workstreams completed or progressed
   - Update `Health Snapshot` if bugs were fixed, debt resolved, or issues closed
   - Update `Doc Freshness` — set `git_head_at_generation` to current HEAD, update last-run dates for any commands invoked this session
   - Don't regenerate from scratch — that's `/workday-start`'s job. Patch what changed.
   - If the cache doesn't exist, skip — the project hasn't run `/workday-start` yet.
   - **Do not claim the cache is absent based on intuition.** If the SessionStart orientation hook failed to inject output (a known past failure mode), you may have no in-context evidence of the cache. Before asserting "no orientation cache in this repo," run `ls tasks/orientation_cache.md` and read the result. Assertions about existence require a verification step, not a recollection.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows. Only touch rows this session affected — don't re-derive the whole tracker.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off or remove them per the file's existing conventions.

4. **Documentation index** (`docs/README.md`): If it exists and this session created new guides, added research files, or completed plan documents, patch the relevant table. Only touch rows this session affected.

**Concurrency note:** These are targeted patches to specific rows/sections based on this session's work — safe with concurrent agents, as long as agents work on different items (which they should by design).

### Step 3: Commit + Verify Remote

1. **Stage only paths this session touched — never `git add -A`.** With concurrent EMs active on the same branch, `git add -A` sweeps up another session's staged/modified files and silently re-attributes them. Instead:
   - Make a mental (or explicit) list of the files you edited during Steps 1/2/2.5/2.6/2.7 (typically a small set: `tasks/lessons.md`, `archive/completed/YYYY-MM.md`, `docs/project-tracker.md`, action-items file, `docs/README.md`).
   - `git add <path1> <path2> ...` — name each path explicitly.
   - If you also edited files earlier in the session that are still unstaged, stage those by path too — but only ones you know you authored this session.
   - If `git status` shows unfamiliar unstaged files you didn't touch, **leave them alone** — they belong to a concurrent session.
2. Commit with a lightweight message: `"session-end quick-save"`. (The post-commit hook will auto-push on work/feature branches.)
3. If nothing to commit, check for unpushed commits: `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`
4. **Verify remote is synced:** confirm no unpushed commits remain. If auto-push failed, push explicitly and warn the PM.
5. If on main (shouldn't happen, but safety): push explicitly — `git push origin main`
6. If push fails (auth, network, conflicts), **warn the PM explicitly** — this is a critical failure

### Step 4: Final Summary

Present a brief end-of-session summary:
```
## Session Complete

**Work done:** [1-2 sentence summary]
**Lessons captured:** [N new / none]
**Work archived:** [N items added to archive/completed/YYYY-MM.md / none needed / project not using unified tracking]
**Docs updated:** [list of updated files]
**Orientation refreshed:** [orientation cache patched / tracker updated / action items checked off / nothing to update / no orientation docs exist]
**Pushed to remote:** [yes — branch name / no — reason]
```

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

**Reminder:** Run `/update-docs` periodically for repo-wide documentation maintenance — it doesn't need to happen every session.

If `$ARGUMENTS` is provided, use it as context for what was accomplished this session.
