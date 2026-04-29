---
name: project-onboarding
description: "Use when starting work in a new project repository, when /update-docs reports tracker_missing, or when a marketplace user runs the coordinator plugin for the first time."
version: 1.0.0
---

# Project Onboarding

## When to Use

- Starting work in a new project repository for the first time
- `/update-docs` reports `tracker_missing` — the project lacks coordination infrastructure
- PM asks to set up project tracking in an existing repo
- **Marketplace first-run** — new coordinator plugin user setting up their first project

## Prerequisites

- You are in the project's working directory (not `~/.claude`)
- PM is available for 3 questions (Step 2)

## Phases

### Phase 1: DETECT — Survey Existing State

Before scaffolding, check what already exists. **Never overwrite existing files.**

Check for each of these and record status (exists / missing / incomplete):

```
├── CLAUDE.md                           — project conventions
├── docs/README.md                      — documentation index (wikis, research, specs, reference)
├── docs/project-tracker.md             — workstream tracking
├── docs/wiki/                          — wiki guides (LAZY — created by coordinator:distill on first guide extraction)
├── docs/wiki/DIRECTORY_GUIDE.md        — guide index with decision record mapping
├── docs/plans/                         — implementation plans (LAZY — created when first plan is copied from ~/.claude/plans/)
├── docs/research/                      — research outputs (LAZY — created by coordinator:deep-research on first run)
├── tasks/lessons.md                    — engineering patterns (LAZY — created by coordinator:session-end on first lesson)
├── archive/completed/                  — completion archive (LAZY — created by coordinator:session-end on first completion)
├── tasks/handoffs/                     — session continuity (LAZY — created by coordinator:handoff on first handoff)
├── CONTEXT.md                          — domain glossary (LAZY — never scaffold; produced when first term is resolved)
├── DIRECTORY.md                        — source index
└── .gitignore                          — check for .claude/settings.local.json entry
```

**If `docs/project-tracker.md` already exists:** This skill becomes a health check — verify the format matches the standard template, flag deviations, and skip to Phase 4 (REPORT).

**Global detection:** Check if `~/.claude/CLAUDE.md` exists. If yes, the generated CLAUDE.md will include an "extends global" reference. If not, the template is fully self-contained — no dependency on global config.

**Distribution repo detection:** Check if `.gitignore` excludes session infrastructure directories (`tasks/`, `archive/`, `tasks/handoffs/`). If 2+ of these are gitignored, this is likely a **distribution repo** — a public/shared repo where session artifacts are intentionally excluded from version control (e.g., an open-source release, a template repo, a package).

**If distribution repo detected: STOP.** Do not proceed to Phase 2. Report:

> _"This looks like a distribution repo — `.gitignore` excludes session directories (`tasks/`, `archive/`, `tasks/handoffs/`). Onboarding infrastructure doesn't belong here — it's a product, not a workspace. Track work on this repo from your parent project's tracker instead."_

This is the correct exit — a distribution repo's CLAUDE.md is a template for downstream users, its .gitignore intentionally excludes session artifacts, and its workstreams belong in the tracker of whoever maintains it.

Report what exists and what needs to be created before proceeding.

### Phase 2: ASK — PM Input (3 Questions)

Present all three questions together to minimize back-and-forth:

> I need three things to set up this project:
>
> **1. Project name** — short name for headers and references (e.g., "Geneva MVP", "DroneSim")
>
> **2. Project type** — controls which domain agents and conventions are included:
>    - `game-dev` — Unreal Engine, Blueprint/C++, Sid reviewer
>    - `web-dev` — Web frameworks, Palí + Fru reviewers
>    - `data-science` — Notebooks, pipelines, Camelia reviewer
>    - `general` — Standard conventions only
>
> **3. Initial workstreams** (1-3) — what are you working on? For each:
>    - Name (short noun-phrase)
>    - 2-3 immediate deliverables
>    - (Optional: dependencies, blockers)
>
> If you're not sure about workstreams yet, say "stubs" and I'll create placeholder sections you can fill in later.

Wait for PM response before proceeding.

### Phase 3: GENERATE — Create Missing Files

Create only what's missing. Use the templates in this skill's `templates/` directory as the base.

#### Lazy-creation discipline

Only scaffold files that have **meaningful day-1 content**. A file that is nothing but a header and a comment on day 1 is not load-bearing — it is a placeholder that will sit empty and train agents to ignore it. Empty scaffolding has zero signal value. Inspired by the lazy-file-creation principle from the mattpocock/skills audit (2026-04-29): create files and directories only when there is a real artifact to write.

**Audit verdict — Phase 3 scaffold items:**

| Item | Verdict | Reasoning |
|------|---------|-----------|
| `CLAUDE.md` | EAGER | Project conventions apply immediately; filled in Phase 2 |
| `docs/project-tracker.md` | EAGER | Workstreams established in Phase 2; real content on day 1 |
| `docs/README.md` | EAGER | Structural index with project name, pointers to plans/research/wikis |
| `.gitignore` entry | EAGER | Prevents accidental credential commits from first commit onwards |
| Post-commit hook | EAGER | Auto-push crash insurance is needed from the very first commit |
| `tasks/lessons.md` | LAZY | Header + comment only; no lessons exist until first session runs |
| `tasks/handoffs/` dir | LAZY | No handoffs until first session ends via `/handoff` |
| `archive/completed/` dir | LAZY | No completed work until first work item ships |
| `docs/wiki/` dir | LAZY | Wiki guides come from `/distill` after artifacts accumulate |
| `docs/plans/` dir | LAZY | Plans come from plan mode; none exist on day 1 |
| `docs/research/` dir | LAZY | Research outputs come from `/deep-research` pipelines |

LAZY items are NOT created here. Each has a designated "create on first use" owner noted in its section below.

#### 3a. CLAUDE.md (if missing)

Use `templates/CLAUDE.md.template`. Process conditionals:

1. Replace `[PROJECT_NAME]` with the PM's project name
2. Replace `{{PROJECT_TYPE}}` with the PM's project type
3. **Include** blocks for all selected project types (remove the `{{IF type}}` / `{{/IF type}}` markers). A project can have multiple types (e.g., `unreal` + `data-science`). For `general` type: no conditional block exists in the template — skip steps 3 and 4.
4. **Remove** blocks for project types not in the list
5. **If global `~/.claude/CLAUDE.md` exists:** Keep the `{{IF_GLOBAL}}` content (remove markers). This tells the EM that global principles apply.
6. **If no global exists:** Remove the `{{IF_GLOBAL}}` line entirely. The template is self-contained.

Write the processed template to `CLAUDE.md` at the project root.

**Important:** The template has `<!-- Fill in -->` comments — these are prompts for the PM to complete, not for the skill to guess at. Leave them as-is.

#### 3b. docs/project-tracker.md (if missing)

Use `templates/tracker.md.template`:

1. Replace `[PROJECT_NAME]`, `[DATE]` (today), `[YEAR]`, `[MONTH]`
2. Replace `[WORKSTREAMS]` with formatted workstream blocks from PM input:

For each workstream the PM provided:
```markdown
### N. [Workstream Name]
**Status:** Ready
**Specs:** <!-- link when spec is written -->

- [ ] [Deliverable 1]
- [ ] [Deliverable 2]
- [ ] [Deliverable 3]
```

If PM said "stubs": create one placeholder workstream:
```markdown
### 1. [Define workstreams]
**Status:** Ready

- [ ] _PM: Define initial workstreams and deliverables_
```

#### 3c. tasks/lessons.md — SKIP (lazy)

Do NOT create this file during onboarding. It has no meaningful day-1 content — it is a header and a comment until the first real lesson is captured. Creating it empty trains agents to ignore the directory.

**Create on first use:** `coordinator:session-end` creates `tasks/lessons.md` (using `templates/lessons.md.template`) the first time a lesson is captured, if the file does not already exist. `coordinator:lessons-trim` also skips gracefully when the file is absent.

#### 3d. docs/README.md (if missing)

Create a documentation index at `docs/README.md`. This is the top-level entry point for all project documentation — the first thing any agent or human should find when looking for docs.

Use the project name and type from Phase 2 to populate the initial structure:

```markdown
# [Project Name] — Documentation Index

Central entry point for all project documentation. Maintained by `/update-docs`.

---

## Wikis and Guides

Living technical reference — distilled from session artifacts by `/distill`.

→ **[`docs/wiki/DIRECTORY_GUIDE.md`](guides/DIRECTORY_GUIDE.md)** — full guide index

_No guides yet. Guides are created by `/distill` as knowledge accumulates from session artifacts._

---

## Plans

Implementation and design plans. Plans start in `~/.claude/plans/` during plan mode, then are copied here as the canonical location.

→ [`docs/plans/`](plans/)

---

## Research

Timestamped research outputs from `/deep-research` pipelines. Preserved permanently; key findings extracted into guides by `/distill`.

→ [`docs/research/`](research/)

---

## Reference Documentation

| Doc | Purpose |
|-----|---------|
| [project-tracker.md](project-tracker.md) | Active workstreams and priorities |

---

*Last updated: [DATE]. Maintained by `/update-docs`.*
```

Replace `[Project Name]` and `[DATE]` with the appropriate values.

#### 3e. Directories

Only create directories that have real day-1 content or that are referenced by files being written in this phase:

```bash
mkdir -p docs   # for project-tracker.md (3b) and README.md (3d)
mkdir -p tasks  # for feature work; lessons.md is lazy (see 3c)
```

**Do NOT pre-create** `tasks/handoffs/`, `archive/completed/`, `docs/wiki/`, `docs/plans/`, or `docs/research/` with `.gitkeep` files. These are lazy directories — created by the skill that first writes to them:

- `tasks/handoffs/` — created by `coordinator:handoff` on first session hand-off
- `archive/completed/` — created by `coordinator:session-end` on first archived completion
- `docs/wiki/` — created by `coordinator:distill` when the first guide is extracted
- `docs/plans/` — created when the first plan is copied from `~/.claude/plans/`
- `docs/research/` — created by `coordinator:deep-research` on first research run

Empty `.gitkeep` scaffolding has zero signal value and trains agents to ignore the directory (they see it exists but empty, rather than understanding it is built lazily).

#### 3f. .gitignore handling

Check if `.gitignore` exists and contains an entry for `.claude/settings.local.json`:

1. **If `.gitignore` exists but lacks the entry:** Append:
   ```
   # Machine-specific Claude settings (do not commit)
   .claude/settings.local.json
   ```

2. **If `.gitignore` doesn't exist:** Create it with:
   ```
   # Machine-specific Claude settings (do not commit)
   .claude/settings.local.json
   ```

3. **If the entry already exists:** Skip silently.

**Warning check:** If `.gitignore` contains a line that would ignore all of `.claude/` (like `.claude/` or `.claude/*`), warn: "Your .gitignore ignores the entire .claude/ directory. Only `.claude/settings.local.json` needs to be ignored — the rest of `.claude/` contains platform settings that are safe to track or ignore as you prefer."

#### 3f.5. Auto-push post-commit hook

Check for `.git/hooks/post-commit`. If absent, install one that delegates to the canonical helper so SSH remotes on Windows route through PowerShell (1Password agent compatibility) and HTTPS remotes go straight through git:

```bash
cat > .git/hooks/post-commit <<'HOOK'
#!/bin/bash
# Auto-push to remote on work/* or feature/* branches — crash insurance.
# Delegates to coordinator-auto-push helper.
exec "$HOME/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-auto-push"
HOOK
chmod +x .git/hooks/post-commit
```

If the repo already has a post-commit hook (e.g. Git LFS prefix), preserve the existing block(s) and append the helper invocation backgrounded:

```bash
# === Auto-push (crash insurance) ===
( "$HOME/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-auto-push" ) &
exit 0
```

Skip if a custom auto-push hook already exists and the PM has signed off on it.

#### 3g. DIRECTORY.md

Do NOT create this file directly. It requires source file analysis that `/update-docs` Phase 2 handles. Instead, note in the report that the PM should run `/update-docs` to generate the source index.

### Phase 4: REPORT

Present what was done:

```
## Onboarding Complete — [Project Name]

### Created
- [list each file/directory created]

### Already Existed (untouched)
- [list each file that was skipped]

### Needs Attention
- [any warnings — .gitignore issues, incomplete CLAUDE.md sections to fill in]

### Next Steps
1. **Fill in CLAUDE.md** — the `<!-- Fill in -->` sections need project-specific details
2. **Run `/update-docs`** — generates DIRECTORY.md source index, refreshes docs/README.md, and creates orientation cache
3. **Run `/session-start`** — verifies everything is wired up correctly

### Documentation System
The documentation index is live at `docs/README.md`. Subdirectories are created lazily as artifacts accumulate:
- **`docs/wiki/`** — created by `/distill` when first guide is extracted
- **`docs/plans/`** — created when first plan is written in plan mode
- **`docs/research/`** — created by `/deep-research` on first run
- `/update-docs` maintains docs/README.md; `/distill` creates wiki guides from session artifacts
```

## Onboarding Bug Fixes — Three-Layer Rule

When an onboarding or install failure is discovered and fixed, a single fix is not enough. A cohort of users already hit the failure and won't re-install. Any onboarding bug fix that doesn't ship all three layers will recur:

**Layer 1 — Prevention:** Fix the install/setup script so future runs don't hit the failure. This is the obvious fix; it's necessary but not sufficient on its own.

**Layer 2 — Reactive repair:** A `doctor`-style standalone script that:
- **By default:** diagnoses the environment and reports what's wrong (non-destructive)
- **With a flag** (e.g., `--fix`): applies the repair in place

Users who already hit the failure won't re-run the full installer. They need a targeted recovery path that works against their existing broken state.

**Layer 3 — Searchable docs:** A row in the troubleshooting table (or a new table if none exists) keyed on the **literal error text** the user would see. Search-reflex users paste the error into a search or into the docs — they need to land on the fix immediately.

```markdown
| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'X'` | Y was not installed | Run `doctor --fix` or `pip install X` |
```

**When onboarding flags a new failure:** Before closing the fix, verify all three layers exist. If a layer is missing, create it as part of the same fix — not a follow-up task.

## Notes

- This skill creates the **skeleton**. The tracker-maintenance skill (invoked by `/update-docs`) handles ongoing maintenance.
- The project tracker format is defined in the tracker-maintenance skill — this skill uses the same format for consistency.
- Handoffs live at `tasks/handoffs/` (git-tracked). `.claude/` contains only platform settings; `settings.local.json` should be in `.gitignore`.
- **Template architecture:** One base CLAUDE.md template with conditional blocks per project type — NOT 4 separate files. Easier to maintain, stays under the 12-file ceiling.
- **Self-contained design:** The CLAUDE.md template works standalone for marketplace users. If global `~/.claude/CLAUDE.md` exists, the DETECT phase adds an "extends global" reference. If not, the template is complete on its own.
