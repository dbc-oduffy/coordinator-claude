---
description: Save session state for next session handoff
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

Capture the current session state so future sessions (or other agents) can pick up seamlessly.

## Instructions

When invoked, create a handoff document in `tasks/handoffs/` (git-tracked). Each session writes its own file (unique timestamp), so multiple concurrent sessions never overwrite each other.

**Path convention:**
- **Active handoffs:** `tasks/handoffs/*.md` — current, available for `/session-start` pickup
- **Archived handoffs:** `archive/handoffs/*.md` — consumed, kept as paper trail
- Both are git-tracked. `.claude/` must NOT be in `.gitignore` — it contains project configuration that travels with the repo.

**Design note:** Multiple agents may be running concurrently. This skill preserves ONE agent's work without assuming exclusive repo access.

**CRITICAL: Write the handoff file FIRST, before commits or anything else.** Handoffs are typically invoked when the session is near compaction. If you do git operations first, you risk losing the conversation context that makes the handoff valuable. Get the knowledge out of your head and onto disk immediately.

### Workflow

#### Step 1: Write the Handoff (IMMEDIATELY)

**Do this first. Do not run git commands, read files, or do anything else before writing the handoff.** You already have everything you need in your conversation context.

Generate a filename: `tasks/handoffs/{YYYY-MM-DD}_{HHMMSS}_{session-id}.md` where:
- `{YYYY-MM-DD}` is the current date
- `{HHMMSS}` is the current time in 24-hour format (e.g., 143052 for 2:30:52 PM)
- `{session-id}` is a short identifier (first 8 chars of session UUID if known, otherwise `manual`)

**Primary source: your conversation context.** You know what you worked on, what files you modified, what decisions were made. Use that — don't rely on git log to reconstruct your session.

Write the file with this structure:

```markdown
# Session Handoff — [DATE]

## What Was Accomplished

_Continuing from [previous handoff filename]: [what the prior session had completed and where it left off]. This session picked up at [entry point]._

- [Bullet list of completed work with file paths]

## Current State
- **Build status:** [compiles / unknown / broken + error]
- **Tests:** [all passing / N failing / not run]
- **Branch:** [branch name] — session-start uses this to find resumable branches
- **Remote synced:** [yes/no — check `git log origin/{branch}..HEAD`]
- **Uncommitted changes:** [yes/no — what]

## In-Progress Work
- [What was being worked on when the session ended]
- [Current step in the plan, if following a plan doc]
- [Plan doc path if applicable]

## Key Decisions Made

> Capture 2-5 decisions per session where the *reasoning* would save future context reconstruction. Not every decision — only those where knowing "why" matters more than knowing "what".

### Decision: [Short title]
- **Observed:** [What prompted this — the situation or constraint you saw]
- **Considered:** [Alternatives weighed — include rejected approaches briefly]
- **Chose:** [What was decided and the core reasoning]

[Repeat for each key decision]

## Blockers or Issues
- [Anything that's stuck or needs human intervention]

## Recommended Next Steps
1. [First thing the next session should do]
2. [Second thing]
3. [Third thing]

## Carried Forward
<!-- Items from the predecessor handoff that this session did NOT resolve. These cascade
     down the chain until completed or explicitly dismissed by the PM. If none, omit this section. -->
- [ ] [Unresolved item from predecessor] _(carried from [predecessor filename])_
- [ ] [Another unresolved item] _(carried from [predecessor filename])_

## Files Modified This Session
- [file path] — [one-line description of change]
```

**Anti-amnesia chain:** The `_Continuing from..._` preamble in `## What Was Accomplished` creates a chain — any single handoff is a self-contained orientation point, not just an incremental update. To populate it: read the most recent file in `tasks/handoffs/` by filename timestamp. If one exists, open with a 2-3 sentence synthesis of that prior state. If no prior handoff exists, omit the preamble. This takes seconds and prevents every future session from re-deriving context.

**Cascading unresolved items:** When reading the predecessor, check its `## Recommended Next Steps` and `## Carried Forward` sections for items this session did NOT complete. Any unresolved items **must** be carried forward into the new handoff's `## Carried Forward` section — they don't disappear just because a session ended. Each carried item retains its origin annotation (e.g., `_(carried from 2026-03-20_100000_abc123.md)_`) so the full lineage is visible. Items leave the cascade only when: (1) completed by a session (moved to `## What Was Accomplished`), or (2) explicitly dismissed by the PM. A session cannot silently drop a carried item.

**Chain archival:** Because the cascade ensures all unresolved obligations flow into the new handoff, the predecessor can always be safely archived after a continuation. Move the predecessor to `archive/handoffs/` (create the directory if needed). The new handoff is now the single source of truth — it contains both the context synthesis (preamble) and the obligation chain (carried forward items).

#### Step 2: Capture Lessons

Follow `/session-end` Step 1 (Capture Lessons) — same intake filter, same format requirements, same merge-over-add rules. Skip if compaction is imminent — the handoff file is the priority.

#### Step 2.5: Doc-Alignment Insurance

Follow `/session-end` Step 2.5 (Doc-Alignment Insurance) — verify status fields match reality for any chunk/stub docs and execution trackers worked on this session. Lightweight pass only — read what's in conversation context, don't re-read every file.

#### Step 2.6: Update Plan Documentation

Follow `/session-end` Step 2 (Update Plan Documentation) — including the active search across all plan locations (`tasks/<feature>/`, `tasks/plans/`, `docs/plans/`, `~/.claude/plans/`). Mark completed items, update status fields, add completion notes. Don't skip this because you don't recall opening a plan — search for one. Skip only if no plan docs exist for this session's work area.

#### Step 2.7: Archive Uncaptured Work

Follow `/session-end` Step 2.6 (Archive Uncaptured Work) — sweep session commits for completed work not yet in the project tracker or completion archive. Skip if the project hasn't adopted unified tracking (`archive/` and `docs/project-tracker.md` don't exist).

#### Step 2.8: Build/Test Awareness

If the project uses a compiled language with a running IDE or editor (e.g., Unreal Engine, Unity, Xcode):
- **Do NOT run builds or test suites during handoff** — they conflict with running editors and concurrent agents
- Instead, note in the handoff's "Current State" section whether changes need a rebuild, and what tests should be run next session

#### Step 2.9: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/session-start` and `/workday-start`. **Skip if compaction is imminent** — the handoff file is the priority; orientation docs are best-effort.

1. **Orientation cache** (`tasks/orientation_cache.md`): If it exists, patch sections affected by this session's work (Active Workstreams, Health Snapshot, Doc Freshness with current HEAD). Don't regenerate — just patch what changed. Skip if cache doesn't exist.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off.

**Same guidance as `/session-end` Step 2.7** — targeted patches to what this session touched, not regeneration. Concurrency-safe.

#### Step 3: Commit + Verify Remote

**Now** that the handoff is written, commit everything and verify remote sync.

1. `git add -A` — stage everything, don't try to separate workstreams
2. If there are staged changes, commit with a lightweight message:
   ```
   git commit -m "handoff quick-save"
   ```
3. **Pushing:** The post-commit hook handles pushing to branch automatically.
   Do NOT manually push. Just commit — the hook does the rest.
   If on main (shouldn't happen, but safety): do NOT push. Commits on main
   stay local until merged via PR.
4. **Verify remote is synced:** confirm no unpushed commits remain (`git log origin/$(git branch --show-current)..HEAD`). If auto-push failed, push explicitly and warn the PM.

#### Step 4: Confirm

Remind the user:
- "Handoff saved to `tasks/handoffs/`. Pick up with `/pickup` (relay-race resumption) or `/session-start` (general orientation)."
- "Run `/update-docs` if you want repo-wide documentation maintenance (directory sync, handoff archiving to `archive/handoffs/`)."

**Verify `.gitignore`:** Quickly check that `tasks/` is NOT gitignored. If it is, warn the user — handoffs in a gitignored directory will be invisible to other sessions and lost on clone.

### Notes

- Each session writes a NEW file with a unique timestamp — never overwrite other sessions' handoffs
- Keep it concise — aim for under 50 lines. The next session will also have MEMORY.md and project context.
- Focus on state that MEMORY.md doesn't capture: in-progress work, blockers, uncommitted changes
- If the user provides arguments (e.g., `/handoff focus on auth refactor`), incorporate that context
- **Cleanup:** During `/handoff`, archive the predecessor after carrying forward its unresolved items. General handoff archiving (48-hour sweep) is handled by `/update-docs` — no broader sweep here.
- **Active vs archived:** Active handoffs live in `tasks/handoffs/` (available for pickup). Archived handoffs live in `archive/handoffs/` (paper trail). Both are git-tracked.
- **User context:** If `$ARGUMENTS` is provided (e.g., `/handoff focus on auth refactor`), incorporate that context into the handoff's "In-Progress Work" and "Recommended Next Steps" sections.
