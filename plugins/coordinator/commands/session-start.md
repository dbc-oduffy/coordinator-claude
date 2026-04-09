---
description: Orient session — preflight, load context, choose work
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[task-description]"
---

# Session Start — Preflight and Orientation

Orient this agent by verifying the environment, loading project context, and choosing work.

**Design note:** Multiple agents may be running concurrently on the same repo. This command orients ONE agent — it does not assume exclusive access to the codebase or the user's attention.

---

## Preflight

Safety and environment checks. Order matters — each depends on the one before it.

### Safety commit

Secure any uncommitted work before touching branches:

1. Run `git status` — if there are ANY uncommitted changes (staged, unstaged, or untracked), commit immediately:
   ```
   git add -A && git commit -m "session-start safety commit"
   ```
2. This is crash insurance. If a previous session died mid-work, this captures its state. The auto-push hook will push to the remote.
3. If nothing to commit, move on silently.

**Do not ask permission.** Non-negotiable safety measure.

### Branch detection

Get on the right branch:

1. **Push health check:** Run `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`.
   If unpushed commits exist, warn: _"Found N unpushed commits — auto-push may have failed. Check .git/push-failures.log."_

2. **If already on a non-main branch:** Report the branch name and continue. Don't switch.
   _"Resuming work on {branch} ({N} commits ahead of main)."_

3. **If on main:** Look for today's work branch to resume:
   - Check local: `git branch --list 'work/{machine}/*'`
   - Check remote: `git branch -r --list 'origin/work/{machine}/*'`
   - Cross-reference with any loaded handoff's `Branch:` field.

   If a branch exists for today (not yet merged):
   _"Found existing branch work/{machine}/{date}. Resuming."_
   `git checkout {branch}`

   If no branch for today (or today's was already merged):
   Create: `git checkout -b work/{machine}/{date}`
   If name collision: append suffix: `work/{machine}/{date}-2`

### Branch staleness

Check how long the branch has diverged from `main`:

1. Find the merge base: `git merge-base HEAD origin/main`
2. Get the date of that commit: `git log -1 --format=%ci <merge-base-hash>`
3. Calculate the age in days.

**If diverged more than 2 days:**

_"This branch has been diverged from main for {N} days (since {date}). Long-lived branches accumulate merge risk. I'd recommend merging before new work — want me to run `/merge-to-main`?"_

**Wait for the user's response.** Do not proceed until the user approves or declines.

**If 2 days or fewer:** Continue silently.

---

## Context Load

Load project state into context. These checks are independent of each other.

### Lessons

Read `tasks/lessons.md` (if it exists) — learned patterns from past corrections. Review every entry.

Note: Project `CLAUDE.md` and global `~/.claude/CLAUDE.md` are already in system context — don't re-read them.

**After reading:** Note the count. No need to recite principles — they're in CLAUDE.md.

### Handoffs

Check `tasks/handoffs/` for `.md` files (active handoffs). If handoffs exist:

1. **Read only filenames** (do NOT read file contents). Extract dates and session IDs from the filename pattern `YYYY-MM-DD_HHMMSS_sessionid.md`.
2. List each file with its date/time. To get the heading, read only line 1 of each file.
3. **Report what's available and stop:**
   _"Found {N} active handoff(s): {list with dates and headings}."_
4. **Do NOT load, summarize, or act on any handoff.** This applies even if there is only one handoff. One handoff is not implicit selection — the PM may not want to pick it up this session, or may have other priorities first.
5. **Do NOT set `HANDOFF_LOADED`.** That flag is set ONLY when the PM explicitly directs you to a handoff.

**When the PM indicates they want a handoff picked up** — by dropping a link, naming it, or saying "pick up that handoff" — read the full file into context. This — and only this — sets `HANDOFF_LOADED=true` for the Engage section. Alternatively, the PM may use `/pickup` which is purpose-built for handoff resumption and skips the general orientation ceremony.

**Archiving is handled by `/update-docs` only** (48-hour threshold). This ensures handoffs persist until the work they describe has had time to complete.

**Path convention:** Active handoffs in `tasks/handoffs/`, archived in `archive/handoffs/`. Both git-tracked.

**If `tasks/` or `archive/` is gitignored:** Warn the user — these directories must be tracked. `tasks/` contains handoffs and plan docs; `archive/` contains the completion history. `.claude/` contains only platform-managed files (settings, hooks) and need not be tracked.

### Session memory

The remember plugin's SessionStart hook automatically injects temporal memory (what was worked on recently) into the session context. This happens via hook output — no manual action needed here.

If session memory content appears in the hook output (marked with `=== SESSION MEMORY ===`), acknowledge it briefly: _"Session memory loaded — {N} days of history available."_

If no session memory appears, note: _"No session memory available — the remember plugin may not be active."_

### Action items and roadmap

**Conditional on workday-start:** If `tasks/.workday-start-marker` contains today's date, skip this section — workday-start already reviewed these. If no marker or stale marker, read them as a graceful fallback.

These are operational documents — they tell the EM what's immediately actionable and where the project is headed.

Read each if it exists (first match wins per row), skip silently if not:

| Document | Convention Paths |
|----------|-----------------|
| Action Items | `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md` |
| Roadmap | `ROADMAP.md`, `docs/roadmap.md`, `docs/ROADMAP.md` |

No summary needed — just load them into context. Their content speaks for itself.

### Project tracker

**Conditional on workday-start:** If `tasks/.workday-start-marker` contains today's date, skip this section — workday-start already reviewed the tracker. If no marker or stale marker, read as a graceful fallback.

Read `docs/project-tracker.md` (if it exists). This is the strategic tracker that `/update-docs` maintains — active workstreams, their statuses, dependencies, and blockers.

**If it exists:** Surface a brief summary:
```
## Project State
- Active workstreams: [N] — [list names with statuses]
- Blocked items: [N] — [brief description of blockers]
- Ready for execution: [list any items with status Ready/Executing]
```

This gives the EM visibility into what the project is working on before choosing work in the Engage section. The tracker also informs the work menu — surface tracker items as concrete options alongside the generic categories.

**If it doesn't exist:** Skip silently.

### Orientation check

The SessionStart hook already injected orientation context at boot (cache if fresh, pointers if stale). Do NOT re-read those files here — they're already in context.

If the hook reported no fresh cache, note: _"No orientation cache — run `/workday-start` or `/update-docs` to generate one."_ Otherwise, move on silently.

### Documentation index

Check if `docs/README.md` exists. If it does, note briefly: _"Documentation index at docs/README.md — [N] wiki guides, [N] research files, [N] plans."_ (Count by globbing each directory.) This tells the agent and PM that accumulated project knowledge is available.

If `docs/README.md` does not exist but `docs/guides/` or `docs/research/` does, note: _"Wiki content exists but no docs/README.md index — `/update-docs` will create one."_

If neither exists, skip silently — the project hasn't adopted the wiki system yet.

### Delegation context (game-dev projects)

**Conditional on project type:** Only for projects whose `project_type` list includes `unreal` or `game-docs` in `coordinator.local.md`. Skip silently if neither type is present.

The capability-catalog (injected at boot) carries the general delegation argument. This section loads the operational routing knowledge needed to delegate effectively in game-dev projects:

**Two-tier dispatch model:**

| Tier | When | How |
|------|------|-----|
| 1. Direct | Verification, quick fact-finding, simple one-off mutations | Use your 8 visible tools directly |
| 2. Dispatch | Any real work in a single domain | Agent(subagent_type='holodeck-control:ue-{domain}') |

For multi-domain or underspecified tasks, decompose and dispatch domain agents sequentially with verification between steps.

**Key constraints:**
- Blueprint graph operations (nodes, pins, functions) cannot be done via Python — only ue-asset-author can do them
- Domain agents have 40+ hidden tools with full schemas; your 8 are for oversight
- Python (`execute_python_code`) is the escape hatch for quick one-liners, not the primary work tool

After loading, note briefly: _"Loaded holodeck delegation context — Tier 2 (domain agents) is the default for real work."_

---

## Engage

Choose work and load task-specific context.

### Work selection

**CRITICAL — Handoff loaded?** Check whether the PM has directed you to pick up a handoff (by dropping a link, naming it, or saying to pick it up). Track this as a mental flag: `HANDOFF_LOADED=true`. If YES:

> **The handoff IS the work order.** Do NOT present a menu. Do NOT ask "what should this agent work on?" Do NOT list the handoff's action items and wait for the user to pick one. Do NOT ask "want me to proceed?"
>
> Instead: read any files the handoff references that aren't yet in context, then **immediately begin executing the first action item.** You're the next relay runner — the baton has been passed. Pick it up and run.
>
> If the handoff lists multiple next steps, execute them in order unless the PM redirects.

**If NO handoff was loaded** (PM hasn't directed you to one yet, or no handoffs exist), present options appropriate to the project:

**What should this agent work on?**

1. **Implementing a feature** — From plan docs or feature specs
2. **Fixing a bug** — From issue tracker, bug report, or failing tests
3. **Reviewing code** — Code review of recent changes
4. **Research / exploration** — No ceremony, just start
5. **Maintenance** — Daily health check, weekly audit, or debt triage
6. **Other** — Something else (describe it)

If `$ARGUMENTS` is provided, use it to identify the task directly and skip the menu.

**Adapt this menu to the project:** If the project tracker was loaded, surface its ready/executing items as concrete options. If project-specific plan docs or priority lists exist (check `docs/`, `tasks/`, `tasks/plans/`), surface those too. The menu should reflect what's actually available, not just generic categories.

### Load task context

**If continuing from a handoff:** Read any files the handoff references that aren't yet in context, then begin the first action item.

**If from the menu:** Based on the user's choice:

- **Implementing:** Find and read the relevant plan doc. Summarize the first implementation step.
- **Fixing a bug:** Identify the failing test, error, or reproduction steps. Read the relevant source.
- **Reviewing:** Identify what to review (recent commits, specific files, PR). Load review criteria.
- **Research:** Ask what to explore. No additional prep needed.
- **Other:** Ask the user to describe the task. Load relevant context.

### Status report

Briefly report:
- **Repo state:** `git status` summary — note that uncommitted changes may belong to other concurrent agents
- **Branch:** Current branch name

Keep this to 2 lines. This is orientation, not ownership.
