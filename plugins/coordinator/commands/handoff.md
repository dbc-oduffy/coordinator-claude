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
- Both are git-tracked. `tasks/` and `archive/` must NOT be in `.gitignore` — they contain session continuity data that travels with the repo. `.claude/` contains only platform settings and does not need to be tracked.

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
---
workstream: <workstream-slug>      # short slug, e.g., scoped-safety-commits
scope:                              # git pathspec syntax — files this workstream owns
  - path/to/file.md
  - dir/with/files/**
---

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
<!-- Durability: describe what is happening, not how to continue it. Path references here are OK — you're describing state, not prescribing steps. -->
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
<!-- Durability: name subsystems and concepts, not file paths or line numbers. Each step = behavioral outcome (what to accomplish), not procedure (how to do it). Include an "Out of scope" line to prevent gold-plating. -->
1. [First thing the next session should do — behavioral outcome, verifiable]
2. [Second thing]
3. [Third thing]

**Out of scope for next session:** [explicitly name what the next session should NOT do or expand into]

## Carried Forward
<!-- Items from the predecessor handoff that this session did NOT resolve. These cascade
     down the chain until completed or explicitly dismissed by the PM. If none, omit this section. -->
- [ ] [Unresolved item from predecessor] _(carried from [predecessor filename])_
- [ ] [Another unresolved item] _(carried from [predecessor filename])_

## Files Modified This Session
- [file path] — [one-line description of change]
```

### Durability Rules for Next-Steps and In-Progress Sections

These four rules apply specifically to `## Recommended Next Steps` and `## In-Progress Work`. They do **not** apply to `## Current State` or `## Files Modified This Session` — those sections legitimately carry procedural detail and file paths because they are *describing what is*, not *prescribing what to do*.

1. **No file paths or line numbers in next-steps prose.** They go stale within hours — a renamed file or merged diff makes the step wrong before the next session even opens it. Reference subsystems, components, and concepts instead. _Exception:_ when the path IS the artifact (e.g., "the plan at `docs/plans/X.md`"), that's an identifier, not a procedural step — fine to include.

2. **Behavioral, not procedural.** Describe *what* the next session needs to accomplish, not *how* to accomplish it. The "how" goes stale; the "what" is durable. Bad: "run `npm test` and fix the three failures in `src/auth/token.ts:142`." Good: "get the auth token tests green — they are failing against the new expiry contract."

3. **Each next step is independently verifiable.** The picker should be able to confirm "done" without reading this handoff again. If a step can't be verified on its own, break it down or add an acceptance signal.

4. **Explicit out-of-scope line.** Every `## Recommended Next Steps` section should end with an "Out of scope for next session" line naming what the next session should NOT expand into. This prevents a fresh-eyed picker from gold-plating or drifting.

**Anti-amnesia chain:** The `_Continuing from..._` preamble in `## What Was Accomplished` creates a chain — any single handoff is a self-contained orientation point, not just an incremental update. **The predecessor is whatever handoff this session was opened with — period.** Identify it from a positive opening signal:

1. **Session was started with `/pickup <handoff>`** — the file passed to `/pickup` is the predecessor. This is the canonical signal. If `/pickup` was used, you already know the answer.
2. **The PM explicitly named a handoff at session start** — e.g., "continue from yesterday's auth handoff." (Combining two predecessors into one handoff requires explicit PM direction at session start — the EM does not collapse the chain on its own.)
3. **Neither?** Then this handoff has **no predecessor**. Omit the `Continuing from` preamble entirely and write a standalone handoff.

**"Most recent file in `tasks/handoffs/`" is a facile signal — do not use it.** Concurrent sessions across machines routinely produce adjacent handoffs that have nothing to do with each other. Adjacency is not ancestry. Picking the most recent timestamp corrupts the audit trail and incorrectly archives active work belonging to other workstreams. If you didn't open this session with a specific handoff, you have no predecessor.

**Cascading unresolved items (only when there IS a predecessor):** When this session genuinely continues a predecessor, check its `## Recommended Next Steps` and `## Carried Forward` sections for items this session did NOT complete. Any unresolved items **must** be carried forward into the new handoff's `## Carried Forward` section — they don't disappear just because a session ended. Each carried item retains its origin annotation (e.g., `_(carried from 2026-03-20_100000_abc123.md)_`) so the full lineage is visible. Items leave the cascade only when: (1) completed by a session (moved to `## What Was Accomplished`), or (2) explicitly dismissed by the PM. A session cannot silently drop a carried item.

**Chain archival (only the explicit predecessor):** Because the cascade ensures all unresolved obligations flow into the new handoff, the **explicit** predecessor can be safely archived after a continuation. Move *only* that predecessor to `archive/handoffs/` (create the directory if needed). Do not sweep other adjacent handoffs in `tasks/handoffs/` — they belong to other workstreams or other sessions and are not yours to archive.

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

1. **Stage only paths this workstream touched — never `git add -A`.** With concurrent EMs active on the same branch, `git add -A` sweeps up another session's staged/modified files and silently re-attributes them. Instead:
   - Make a mental (or explicit) list of the files this workstream edited this session (typically small: the handoff doc itself, `tasks/` files, and any late-session work).
   - `git add <path1> <path2> ...` — name each path explicitly.
   - If `git status` shows unfamiliar unstaged files you didn't touch, **leave them alone** — they belong to a concurrent session.
2. If there are staged changes, commit using the scoped helper — it reads `workstream:` and `scope:` from the handoff doc's frontmatter and stages only the declared paths:
   ```
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit --scope-from <handoff-doc-path> "handoff quick-save: <workstream>"
   ```
   where `<workstream>` is the slug from the handoff doc's `workstream:` frontmatter field (e.g., `handoff quick-save: scoped-safety-commits`). The `--scope-from` flag reads `scope:` as git pathspec entries and stages only those paths — keeping concurrent sessions isolated. The pathspec format follows standard git pathspec syntax (e.g., `path/to/file.md`, `dir/with/files/**`).
3. **Pushing:** The post-commit hook handles pushing to branch automatically.
   Do NOT manually push. Just commit — the hook does the rest.
   If on main (shouldn't happen, but safety): do NOT push. Commits on main
   stay local until merged via PR.
4. **Verify remote is synced:** confirm no unpushed commits remain (`git log origin/$(git branch --show-current)..HEAD`). If auto-push failed, push explicitly and warn the PM.

#### Step 3.5: Archive Session Claim

Now that the final commit has landed and pushed, archive this session's claim directory so concurrent sessions don't see stale claims accumulating until the 24h reaper fires. Without this, `coordinator-safe-commit --scope-from` in concurrent sessions repeatedly trips on dead-PID claims that touched the same scope files — forcing the next EM to either wait 24h, set `COORDINATOR_OVERRIDE_SCOPE=1` (which masks the gap), or manually `cs_archive` each defunct session by hand.

Run:
```bash
sid=$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null) && \
  source ~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent — already-archived sessions return 0 silently. Failures are non-fatal (the 24h reaper is the safety net). Skip silently if the sentinel is missing or the lib is unavailable.

**Note on session_id source:** The sentinel is "last writer wins" across concurrent sessions. If `CLAUDE_SESSION_ID` is exported in your environment, prefer it over the sentinel — that's the session that actually owns this handoff.

#### Step 4: Confirm

Remind the user:
- "Handoff saved to `tasks/handoffs/`. Pick up with `/pickup` (relay-race resumption) or `/session-start` (general orientation)."
- "Run `/update-docs` if you want repo-wide documentation maintenance (directory sync, handoff archiving to `archive/handoffs/`)."

**Verify `.gitignore`:** Quickly check that `tasks/` is NOT gitignored. If it is, warn the user — handoffs in a gitignored directory will be invisible to other sessions and lost on clone.

### Notes

- **A Claude Code restart is a session boundary, not a step within a session.** If your workflow needs an MCP-bridge restart, a runtime artifact rebuild, or a `/reload-plugins` between code-edit and verification, run `/handoff` BEFORE the restart, not after. Splitting code+build from runtime-verify across two sessions is cleaner than trying to span the restart — context is lost in the gap, and the post-restart session that picks up has no context unless a handoff exists. Symptom that you should have handed off: you find yourself saying "let me just wait through this restart and then verify" — stop, hand off, the next session verifies.
- Each session writes a NEW file with a unique timestamp — never overwrite other sessions' handoffs
- Keep it concise — aim for under 50 lines. The next session will also have MEMORY.md and project context.
- Focus on state that MEMORY.md doesn't capture: in-progress work, blockers, uncommitted changes
- If the user provides arguments (e.g., `/handoff focus on auth refactor`), incorporate that context
- **Cleanup:** During `/handoff`, archive the predecessor after carrying forward its unresolved items. General handoff archiving (48-hour sweep) is handled by `/update-docs` — no broader sweep here.
- **Active vs archived:** Active handoffs live in `tasks/handoffs/` (available for pickup). Archived handoffs live in `archive/handoffs/` (paper trail). Both are git-tracked.
- **User context:** If `$ARGUMENTS` is provided (e.g., `/handoff focus on auth refactor`), incorporate that context into the handoff's "In-Progress Work" and "Recommended Next Steps" sections.
