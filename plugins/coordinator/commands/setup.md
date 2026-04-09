---
description: Set up the coordinator plugin — check prerequisites, verify environment, configure project. Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only]"
---

# Coordinator Setup

Environment and project setup for the coordinator plugin. Checks prerequisites, verifies configuration, and initializes what's missing. Safe to re-run — skips anything already configured.

If `$ARGUMENTS` contains `--check-only`, report status without making changes.

**Scope distinction:** This command sets up the coordinator *environment* (plugins, env vars, tools). For per-project scaffolding (CLAUDE.md, tracker, workstreams), use `/project-onboarding` after this.

---

## 1. Environment Prerequisites

Run all checks and collect results for the status table.

### 1a. Git repository

```bash
git rev-parse --show-toplevel 2>/dev/null
```

- If not a git repo: warn that branch management, commits, and handoffs require git. Setup continues.
- If a git repo: note the repo root path.

### 1b. Agent Teams env var

```bash
echo "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-not_set}"
```

- If `1`: ready.
- If not set: **required for staff sessions and all research pipelines.** If not `--check-only`, offer to add it:

Read `~/.claude/settings.json`. If an `env` block exists, check for the key. If missing, add it:

```json
"env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }
```

Note: this takes effect on next Claude Code restart.

### 1c. Session memory (remember plugin)

Check the conversation context for the `=== SESSION MEMORY ===` marker injected by the remember plugin's SessionStart hook.

- If present: ready.
- If absent: note that the remember plugin provides temporal session memory (what was worked on recently). Optional but recommended. If the user wants it, they can install it from the plugin marketplace.

### 1d. Code statistics tool (scc)

```bash
command -v scc 2>/dev/null || command -v "$HOME/bin/scc" 2>/dev/null || echo "not_found"
```

- If found: ready. Used by the orientation hook for code stats.
- If not found: optional. Note that `scc` provides code statistics in the session orientation. Install from https://github.com/boyter/scc if desired.

### 1e. Deep research plugin

Check if the deep-research plugin is installed:

```bash
ls ~/.claude/plugins/coordinator-claude/deep-research/commands/web.md 2>/dev/null || \
ls ~/.claude/plugins/cache/*/deep-research/*/commands/web.md 2>/dev/null || \
echo "not_found"
```

- If found: ready. Note which pipelines are available.
- If not found: optional. The deep-research plugin adds multi-agent research pipelines (internet, repo, structured). Available from the plugin marketplace or https://github.com/oduffy-delphi/deep-research-claude.

**If deep-research IS found,** also check:
- Agent Teams env var (already checked above — if missing, flag it as **required** here, not just recommended)
- NotebookLM sub-plugin: check for `notebooklm/.mcp.json` in the deep-research plugin directory. If present, note that Pipeline D (media research) requires the `notebooklm-mcp-cli` package and Google authentication (`nlm login`).

### 1f. Global CLAUDE.md integration

Read `~/.claude/CLAUDE.md` and check if it contains an `@` import of the coordinator doctrine:

```
grep -c "coordinator.*CLAUDE.md" ~/.claude/CLAUDE.md 2>/dev/null || echo "0"
```

- If found: ready — the coordinator operating doctrine is being imported.
- If not found: recommend adding the import. The coordinator CLAUDE.md contains operating norms (session orientation, plan-first workflow, review sequencing, etc.) that improve how Claude works with the coordinator. Suggest adding this line to their global `~/.claude/CLAUDE.md`:
  ```
  @~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md
  ```
  Or, if installed from marketplace cache, point to the cache path.

---

## 2. Project Configuration

### 2a. coordinator.local.md

Check if `coordinator.local.md` exists at the repo root:

```bash
test -f coordinator.local.md && echo "exists" || echo "missing"
```

**If it exists:** Read it and report the current `project_type`. No changes.

**If missing and not `--check-only`:** Ask the user what kind of project this is:

> What type of project is this? This controls which domain specialists are available for routing.
>
> - **general** — Software project (Patrik for code review, standard workflow)
> - **unreal** — Unreal Engine project (adds Sid, Blueprint agents, holodeck tools)
> - **web** — Web project (adds Palí for front-end review, Fru for UX)
> - **data-science** — ML/data project (adds Camelia for data science review)
> - **meta** — Coordinator infrastructure itself (full EM delegation model)
> - **Custom** — Specify your own (comma-separated for multiple types, e.g. "unreal, data-science")

Create `coordinator.local.md` based on their answer. Single type:

```markdown
---
project_type: {type}
---
```

Multiple types (list format):

```markdown
---
project_type:
  - {type1}
  - {type2}
---
```

### 2b. Directory structure

Create the directories the coordinator expects (skip any that exist):

```bash
mkdir -p tasks/handoffs archive/handoffs
```

### 2c. Lessons file

Check if `tasks/lessons.md` exists. If not, create it:

```markdown
# Lessons

> Engineering patterns worth remembering. Bold title + 1-2 sentence rule. Max 3 lines per entry.
> Review at session start. Trim when exceeding ~50 entries.
```

---

## 3. Optional: Persona Customization

After the core setup, ask once:

> The coordinator includes named reviewer personas (Patrik, Sid, Camelia, Palí, Fru, Zolí). Would you like to customize their names?
>
> - **Keep defaults** — Use the built-in persona names
> - **Customize** — Choose your own names for the reviewers

If the user wants to customize, note that they can run the rename script:

```bash
bash ~/.claude/plugins/coordinator-claude/setup/rename-personas.sh OldName "NewName"
```

Or from the repo clone:

```bash
bash setup/rename-personas.sh --dry-run Patrik "Alex" Sid "Jordan"
```

This is a one-time cosmetic choice. Skip if `--check-only`.

---

## 4. Status Report

Present a summary table:

```
## Coordinator Setup

| Check                       | Status |
|-----------------------------|--------|
| Git repository              | ... |
| Agent Teams env var         | ... |
| Session memory (remember)   | ... (optional) |
| Code stats (scc)            | ... (optional) |
| Deep research plugin        | ... (optional) |
| NotebookLM (Pipeline D)     | ... (optional) |
| Global CLAUDE.md import     | ... |
| coordinator.local.md        | ... |
| tasks/ directory            | ... |
| tasks/lessons.md            | ... |

### Available commands

- `/session-start` — Orient session, load context, choose work
- `/session-end` — Wrap up, capture lessons
- `/handoff` — Save state for next session
- `/review-dispatch` — Route artifacts to reviewers
- `/update-docs` — Refresh project documentation, maintain docs/README.md index
- `/distill` — Extract knowledge from session artifacts into wiki guides
- `/project-onboarding` — Full project scaffolding (CLAUDE.md, tracker, docs/README.md, wiki structure)
```

If any **required** items are missing (git), note them prominently.
If any **recommended** items are missing (Agent Teams, CLAUDE.md import), list concrete next steps.

End with: _"Run `/session-start` to begin, or `/project-onboarding` if this is a new project."_

If `--check-only`, show the table but note what *would* be created/configured without the flag.
