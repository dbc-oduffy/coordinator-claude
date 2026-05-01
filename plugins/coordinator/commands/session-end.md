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

### Step 0: Tier Usage Report

Before capturing lessons, emit the tier usage summary for this session. This closes the W3 telemetry loop — the PM sees whether the tiered-context-loading doctrine was followed.

```bash
SESSION_JSON=$(find "${HOME}/.claude/projects" -name "*.json" -path "*/tier-usage/*" 2>/dev/null | \
  xargs ls -t 2>/dev/null | head -1)
if [[ -n "$SESSION_JSON" && -f "$SESSION_JSON" ]]; then
  python3 -c "
import json, sys
data = json.load(open('${SESSION_JSON}'))
c = data.get('counts', {})
t4 = data.get('tier4_dispatches', [])
missing = sum(1 for d in t4 if not d.get('rationale_present', True))
print(f\"Tier usage this session: tier1={c.get('tier1',0)} tier2={c.get('tier2',0)} tier3={c.get('tier3',0)} tier4={c.get('tier4',0)} ({missing} tier-4 missing rationale)\")
" 2>/dev/null || true
fi
```

If the JSON file doesn't exist (first session, telemetry hook not yet active, or no tracked tools fired), skip silently — do not error.

### Step 1: Capture Lessons

Read `tasks/lessons.md` (if it exists). If anything was learned this session that isn't already captured, add it — but apply the intake filter first.

**Create on first use:** `tasks/lessons.md` is not scaffolded by `/project-onboarding` (it would be empty — no lessons exist on day 1). If lessons exist to capture AND the file does not exist yet, create it now using the template header:

```markdown
# Lessons — [Project Name]

Engineering patterns worth internalizing. Bold title + 1-2 sentence rule. Max 3 lines per entry.

<!-- This file is maintained by the EM. See CLAUDE.md § Self-Improvement Loop for conventions. -->
```

Then append the new entry. If there are no lessons to capture and the file doesn't exist, do not create it.

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

### Step 1.2: Lesson Classification

For each new lesson added in Step 1, ask the tier-1 question: **"If a different project type — UE / web / data / research — also used the coordinator pipeline, would this rule apply?"** This is autonomous self-classification; no separate review step is needed.

- **If yes (tier-1 / universal):** (a) tag the entry in `tasks/lessons.md` by appending `[universal]` on the same line as the bold title; (b) append a one-liner to the global queue at `~/.claude/tasks/coordinator-improvement-queue.md`:
  ```
  - YYYY-MM-DD | <source-repo> | <source-file>:<line> | <one-line summary> | proposed target: <coordinator file>
  ```
  Use the project repo name as `<source-repo>`, and `tasks/lessons.md:<line-number>` as `<source-file>:<line>`. If the same `<source-file>:<line>` already exists in the queue, skip — the queue is append-only and that pair is the dedup key.
- **If no (tier-2 / project-specific):** no action beyond the lesson already written.
- **If nothing new was added in Step 1:** skip this step entirely.

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
   - **Stale is not a skip condition — it's a refresh trigger.** If `generated_at` is older than today, or `git_head_at_generation` doesn't match current HEAD, or the SessionStart hook flagged the cache as stale, do a full refresh (re-derive Active Workstreams, Health Snapshot, Recent Work, Doc Freshness from current repo state) before concluding session-end. Leaving a stale cache in place means the next session boots on misleading orientation. The process owns freshness.

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

### Step 3.5: Archive Session Claim

Now that the final commit has landed and pushed, archive this session's claim directory so concurrent sessions don't see stale claims accumulating until the 24h reaper fires. `/session-end` is one of two session-exit pathways (the other being `/handoff`); both must clean up claims, otherwise sessions that wind down via `/session-end` leak claims that force the next concurrent EM into a 24h wait, `COORDINATOR_OVERRIDE_SCOPE=1`, or hand-archival.

Run:
```bash
sid=$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null) && \
  source ~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent — already-archived sessions return 0 silently (verified: a session archived by `/handoff` and re-archived here is a no-op). Failures are non-fatal (the 24h reaper is the safety net). Skip silently if the sentinel is missing or the lib is unavailable.

**Note on session_id source:** The sentinel is "last writer wins" across concurrent sessions. If `CLAUDE_SESSION_ID` is exported in your environment, prefer it over the sentinel — that's the session that actually owns this exit.

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
