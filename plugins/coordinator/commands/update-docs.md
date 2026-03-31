---
description: Repo-wide documentation maintenance and sync
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--no-distill]"
---

# Update Documentation — Repo-Wide Maintenance

Ensure all documentation reflects the current state of the codebase.

## Instructions

When invoked, systematically update all documentation artifacts to match reality. This is a **repo-wide maintenance operation**, not scoped to any single session or agent. It syncs docs with the codebase as it currently exists, regardless of which agent(s) made the changes. This prevents documentation drift — the #1 cause of wasted context in LLM-driven development.

**Arguments:**
- `--no-distill` — Skip the artifact distillation check (Phase 12). Use when calling from overnight/unattended workflows (mise-en-place hibernate mode) or when you just want a fast doc sync.

**Execution model:** Phases 1–11 are mechanical maintenance work. Dispatch them to a **Sonnet agent** via the Agent tool (`model: "sonnet"`). The coordinator (you) handles Phase 0 (branch guard), Phase 12 (distillation check), Phase 13 (report), and any escalations. When the Sonnet agent encounters a skill invocation stub (Phases 5, 6, 8, 11), it executes that skill's content directly — it does not bounce back to the coordinator.

### What This Does

1. **Detects** project tracker and flags if missing (escalates to PM)
2. **Refreshes** source indexes / directory docs if source files changed
3. **Updates** plan documents to reflect completed/changed work
4. **Syncs** MEMORY.md with new patterns, decisions, or status changes
5. **Maintains** the unified project tracker (`tracker-maintenance` skill) — marks completion, archives shipped work, updates dependencies
6. **Trims** lessons files (`lessons-trim` skill)
7. **Updates** CLAUDE.md if architecture or conventions changed (rare)
8. **Archives** old handoffs (`handoff-archival` skill)
9. **Commits** all doc changes and verifies remote sync
10. **Refreshes** orientation cache if present
11. **Checks** changed files against architecture atlas (`atlas-integrity-check` skill)
12. **Distills** accumulated artifacts into wiki guides if thresholds are met (`/distill` pipeline, conditional)

### Execution Workflow

#### Phase 0: Quick-Save Before Docs

Commit everything before updating documentation — captures all uncommitted changes from any source.

1. **Branch guard:** If on `main`, create a work branch first (`work/{machine}/{date}`) and switch to it. Never commit directly to main — the repo's merge policy (PR + CI) is the only path to main.
2. `git add -A` and commit with a lightweight message: `"pre-docs quick-save"`
3. If nothing to commit, move on
4. Do not push yet — push happens in Phase 9 after all docs are updated

#### Phase 1: Detect Current State (Silent)

Determine the current state of the codebase — not "what happened this session" but "what does the repo look like now vs what docs describe."

1. **Project tracker check:**
   - Look for `docs/project-tracker.md`
   - If it does NOT exist: **set a `tracker_missing` flag** and include this in your output: `"ESCALATION: No project tracker found at docs/project-tracker.md. This needs a PM + EM conversation to establish workstreams before the tracker can be maintained. Skipping Phase 5."`
   - If it exists: read it and note current workstream count, any `[x]` items, and dependency markers
   - Also check for `archive/completed/` directory — create it if missing

2. **Source file inventory:**
   - Compare actual source files against any directory index / source map docs
   - Identify: files present but undocumented, files documented but missing, renamed files
   - Were any new directories created?

3. **Plan document status:**
   - Check plan doc locations in this order:
     1. `tasks/<feature>/todo.md` — feature-scoped plans (active work)
     2. `docs/plans/` — historical and reference plans
     3. `tasks/plans/` — session handoff plans (temporary)
   - Any plans with items that appear completed in code?
   - Any plans marked in-progress that are now done?

4. **Recent git context** (supplementary — shows what's happened since last push/docs update):
   ```
   git log --oneline -15
   git log --oneline origin/HEAD..HEAD 2>/dev/null  # committed but not pushed
   ```

5. **Session memory cross-reference** (if remember plugin is active):
   Read `memory/sessions/recent.md` from the project's memory directory (`~/.claude/projects/<slug>/memory/sessions/recent.md`) and cross-reference against the project tracker. Look for:
   - **Untracked work:** Activity in the temporal log that doesn't correspond to any tracked workstream — potential drift or ad-hoc work that should be captured
   - **Stale workstreams:** Tracker items with no corresponding activity in the temporal log — may need status updates or deprioritization
   - **Completed but unrecorded:** Work described as done in the temporal log but still marked in-progress in the tracker

   If mismatches are found, note them for Phase 5 (tracker maintenance). This is a cross-reference, not an action step — the tracker is updated in Phase 5.

#### Phase 2: Update Source Indexes (or Create Them)

**If no DIRECTORY.md (or equivalent source index) exists at all**, create one. A source index is the single highest-value documentation artifact for LLM-driven development — it eliminates most exploratory grepping and gives every agent immediate orientation.

**Creating a new DIRECTORY.md:**

Use subagents to parallelize the work. Each agent handles one top-level source directory:

1. Identify the project's source root(s) (e.g., `src/`, `Source/`, `lib/`, `app/`, `packages/`)
2. For each top-level directory, dispatch a subagent with this prompt:
   > Catalog all source files in `[directory]`. For each file, document:
   > - File name and path
   > - Primary class/module/component it defines
   > - One-line purpose
   > - Key exports or APIs (2-3 most important)
   > - Dependencies on other directories in this project
   >
   > Write a `DIRECTORY.md` in `[directory]/` with this information. Use a table or structured list. Include a file count and "Last refreshed: YYYY-MM-DD" timestamp.
3. After all agents complete, write a top-level `DIRECTORY.md` (at the source root) that:
   - Lists each directory with a one-line summary
   - Shows file counts per directory
   - Maps cross-directory dependency chains
   - Includes a "Last refreshed" timestamp

**Adapt to project conventions:** If the project uses a different index structure (README.md per folder, a single flat index, etc.), match that convention instead.

**Default location:** If no existing convention is apparent, create `DIRECTORY.md` at the project root. This is the most discoverable location and matches the convention used by this orchestration infrastructure.

**If a DIRECTORY.md already exists**, update it:

1. Compare actual source files against the documented index
2. Add entries for new files, remove entries for deleted files
3. Update any file counts, timestamps, or dependency references
4. If new directories were created, create per-directory indexes for them

**If no source files changed and indexes exist, skip this phase entirely.**

#### Phase 3: Update Plan Documents

For each plan doc that relates to work reflected in the current codebase:

1. Read the plan document
2. Check which items/phases are now implemented
3. Update status markers (e.g., checkbox completion, phase status)
4. If a plan is fully implemented, note the completion date
5. If implementation deviated from the plan, document what changed and why

#### Phase 4: Update Memory

Read the project's MEMORY.md (at `~/.claude/projects/<project-key>/memory/MEMORY.md`) and update if:

1. **Phase/milestone status changed** — e.g., a phase was completed
2. **New patterns established** — e.g., a new coding pattern was introduced
3. **New key files** — e.g., a new core utility was created
4. **New gotchas discovered** — e.g., a framework pitfall was encountered

**Do NOT update MEMORY.md for:**
- Session-specific details (what was discussed, temporary state)
- Speculative conclusions from reading a single file
- Information that duplicates CLAUDE.md

#### Phase 5: Maintain Project Tracker + Archive Completed Work

**If `tracker_missing` flag was set in Phase 1, skip this phase.**

Execute the `tracker-maintenance` skill. Read the skill at `${CLAUDE_PLUGIN_ROOT}/skills/tracker-maintenance/SKILL.md` and follow all steps exactly.

#### Phase 6: Trim Lessons Files

Execute the `lessons-trim` skill. Read the skill at `${CLAUDE_PLUGIN_ROOT}/skills/lessons-trim/SKILL.md` and follow all steps exactly.

#### Phase 7: Update CLAUDE.md (Rare)

Only update CLAUDE.md if:
- Source architecture section no longer matches reality
- New critical rules were established that apply project-wide
- Build system or workflow changed

**This should be rare** — most updates are to indexes and plan docs.

#### Phase 8: Archive Old Handoffs

Execute the `handoff-archival` skill. Read the skill at `${CLAUDE_PLUGIN_ROOT}/skills/handoff-archival/SKILL.md` and follow all steps exactly.

#### Phase 9: Commit + Verify Remote

1. `git add -A` and commit: `"docs maintenance"`
   (The post-commit hook will auto-push on work/feature branches.)
2. **Verify remote is synced:** `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`
   If unpushed commits remain, push explicitly.
3. If push fails, **warn the PM explicitly**

**Note:** This skill pushes to the current branch only. Getting changes onto main is the caller's responsibility (e.g., `/workday-complete` or `/merge-to-main`). If you're on main at this point, something went wrong in Phase 0.

#### Phase 10: Refresh Orientation Cache

If `tasks/orientation_cache.md` exists:
1. Re-derive cache content from the docs just updated (repomap, DIRECTORY, health files)
2. Update `generated_at` and `git_head_at_generation` to current HEAD
3. Include in the Phase 9 commit (or amend if already committed)

If no cache exists: skip. Project hasn't run `/workday-start` yet.

**Execution:** The Sonnet agent handles this as part of its mechanical work. Include the cache format spec in the dispatch prompt so the agent can write it directly.

#### Phase 11: Architecture Atlas Integrity Check

Execute the `atlas-integrity-check` skill. Read the skill at `${CLAUDE_PLUGIN_ROOT}/skills/atlas-integrity-check/SKILL.md` and follow all steps exactly.

#### Phase 12: Artifact Distillation (Conditional)

**Skip this phase if `--no-distill` was passed.**

Check whether accumulated artifacts warrant distillation into wiki documents:

1. **Count artifacts:**
   ```bash
   # Count across distillation source directories
   PLANS=$(find docs/plans/ .claude/plans/ -name "*.md" 2>/dev/null | wc -l)
   HANDOFFS=$(find archive/handoffs/ -name "*.md" 2>/dev/null | wc -l)
   COMPLETED=$(find archive/completed/ -name "*.md" 2>/dev/null | wc -l)
   TASKS=$(find tasks/ -mindepth 2 -name "*.md" -not -path "tasks/architecture-atlas/*" -not -name "lessons.md" -not -name "health-ledger.md" -not -name "bug-backlog.md" -not -name "debt-backlog.md" 2>/dev/null | wc -l)
   TOTAL=$((PLANS + HANDOFFS + COMPLETED + TASKS))
   ```

2. **Check recency:** Read `docs/guides/.distill-log.md` if it exists. Extract the most recent run date. Calculate days since last distillation.

3. **Threshold check — fire if EITHER condition is met:**
   - Total artifact count ≥ 50
   - Last distillation was >14 days ago (or no distillation log exists and artifact count ≥ 20)

4. **If threshold met:** Announce to the PM: *"Artifact count is [N] (threshold: 50) / last distillation was [N] days ago. Chaining into `/distill` to extract knowledge before pruning."* Then invoke `/distill` via the Skill tool. The PM gate in `/distill` Phase 4 provides the approval checkpoint.

5. **If threshold not met:** Note in the report: "Distillation: not needed (N artifacts, last run M days ago)."

#### Phase 13: Report

Present a concise summary:

```
## Documentation Update Summary

### Project Tracker
- [Maintained — N items archived, M remaining / No tracker found — NEEDS PM+EM SETUP / No changes needed]
- Active workstreams: [N] [⚠️ exceeds limit of 5 — consider consolidating]
- Dependencies resolved: [N] / Dead references: [list if any]
- Temporal memory cross-ref: [N untracked activities, M stale workstreams / aligned / session memory not active]

### Source Indexes
- [Created from scratch (N directories, M files) / Updated — N files added, M removed / No changes needed]

### Plan Documents
- [file]: [what was updated]

### Memory
- [Updated/No changes needed] — [what changed]

### Lessons
- [Trimmed N entries / Merged M / No changes needed]

### CLAUDE.md
- [Updated/No changes needed]

### Handoffs Archived
- [N moved from tasks/handoffs/ → archive/handoffs/ / No handoffs to clean up]

### Completion Archive
- [N items archived from tracker to archive/completed/YYYY-MM.md / No completed items to archive]
- [M ad-hoc items captured from git log / No untracked work found]

### Architecture Atlas
- [All changed files mapped / N unmapped files — potential new system detected: [directories] / Skipped — file-index.md not found]

### Distillation
- [Ran /distill — N guides created/updated, M artifacts deleted / Not needed (N artifacts, last run M days ago) / Skipped (--no-distill)]

### Pushed to Remote
- [yes — branch name / no — reason]
```

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

### Style Guidelines

- **Match existing style** — don't reformulate, just update
- **Be precise** — file paths, class names, line numbers where relevant
- **Be concise** — bullet points, not paragraphs
- **Preserve structure** — don't reorganize documents, just update content
- **Timestamp everything** — dates on refreshes, completion markers on plans

### When to Invoke

- **Periodically** — when docs have drifted from reality (not necessarily every session)
- **After major feature implementation** — when significant code was written by one or more agents
- **Before starting a new phase** — to ensure docs reflect the starting state
- **Explicitly** — when you want repo-wide maintenance. `/session-end` and `/handoff` now do lightweight orientation patches (cache, tracker, action items, plan docs) for what the session touched — but `/update-docs` is still the heavyweight pass that re-derives everything, trims lessons, archives handoffs, and runs integrity checks.
