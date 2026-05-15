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

### 1c. Code statistics tool (scc)

```bash
command -v scc 2>/dev/null || command -v "$HOME/bin/scc" 2>/dev/null || echo "not_found"
```

- If found: ready. Used by the orientation hook for code stats.
- If not found: optional. Note that `scc` provides code statistics in the session orientation. Install from https://github.com/boyter/scc if desired.

### 1d. Deep research plugin

Check if the deep-research plugin is installed:

```bash
ls ~/.claude/plugins/coordinator-claude/deep-research/commands/web.md 2>/dev/null || \
ls ~/.claude/plugins/cache/*/deep-research/*/commands/web.md 2>/dev/null || \
echo "not_found"
```

- If found: ready. Note which pipelines are available.
- If not found: optional. The deep-research plugin adds multi-agent research pipelines (internet, repo, structured). Available from the plugin marketplace or https://github.com/dbc-oduffy/deep-research-claude.

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

**If it exists:** Read it and report the current `project_type` (and `project_subtypes` if present). Check for legacy values — if `project_type` is `unreal`, `meta`, or bare `web`, emit a one-line warning:

> ⚠ Legacy project_type detected: `{value}`. Suggested migration: set `project_type: game-dev` + `project_subtypes: [unreal]` (or `project_type: general` for `meta`, `project_type: web-dev` for `web`). Edit `coordinator.local.md` manually — this command does not auto-rewrite.

No other changes when file exists.

**If missing and not `--check-only`:** Ask the user what kind of project this is:

> What type of project is this? This controls which domain specialists are available for routing.
>
> - **general** — Software project (the Staff Engineer for code review, standard workflow)
> - **game-dev** — Game development project (adds the Game Dev Reviewer reviewer, game-dev domain agents)
> - **web-dev** — Web project (adds Palí for front-end review, the UX Reviewer for UX)
> - **data-science** — ML/data project (adds the Data Science Reviewer for data science review)

Then ask:

> Any subtypes? These are free-form advisory tags — no validation, no controlled vocabulary. Downstream routing does best-effort matching; mismatches simply don't trigger subtype-specific blocks. Examples: `unreal`, `unity` under game-dev; `react`, `nextjs` under web-dev. Comma-separated, or leave blank.

Create `coordinator.local.md` based on their answers:

```markdown
---
project_type: {type}
---
```

When subtypes were provided, include the `project_subtypes` field:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]
---
```

---

## 3. Optional: Persona Customization

After the core setup, ask once:

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, Palí, the UX Reviewer, Zolí). Would you like to customize their names?
>
> - **Keep defaults** — Use the built-in persona names
> - **Customize** — Choose your own names for the reviewers

If the user wants to customize, note that they can run the rename script:

```bash
bash ~/.claude/plugins/coordinator-claude/setup/rename-personas.sh OldName "NewName"
```

Or from the repo clone:

```bash
bash setup/rename-personas.sh --dry-run the Staff Engineer "Alex" the Game Dev Reviewer "Jordan"
```

This is a one-time cosmetic choice. Skip if `--check-only`.

---

## 3.5. Percolation Setup (if applicable)

Detect whether this repo is a *source* repo for percolation — i.e., a repo that publishes plugin content to a separate publish-repo target.

```bash
test -f setup/publish.sh && echo "percolation_source" || echo "not_applicable"
```

**If `setup/publish.sh` is absent:** skip this phase silently. This repo is not a percolation source.

**If `setup/publish.sh` is present:** check whether any publish targets are registered:

```bash
bash -c '
  [[ -f setup/publish-targets.sh ]] || { echo "MISSING_TARGETS"; exit 0; }
  source setup/publish-targets.sh
  echo "TARGET_COUNT:${#TARGETS[@]}"
'
```

- **`MISSING_TARGETS` or `TARGET_COUNT:0`:** No targets registered. Walk `docs/wiki/percolate-setup.md` (plugin-relative path) inline — specifically Steps 1 and 2 to register a target, then Steps 3–4 to scaffold `.percolate-ignore` and hook directories. This is an interactive procedure; do not skip.
- **Targets registered and all configured** (each target has a `.percolate-ignore` and hook dirs): report status in the summary table as `Percolation: N target(s) configured`.
- **Targets registered but partially configured** (missing `.percolate-ignore` or hook dirs on any target): surface the gap and offer to run the setup procedure for the unconfigured target(s).

If `--check-only`, report the percolation state in the summary table without creating anything.

Add a `Percolation` row to the status table in Phase 4.

---

## 4. Status Report

Present a summary table:

```
## Coordinator Setup

| Check                       | Status |
|-----------------------------|--------|
| Git repository              | ... |
| Agent Teams env var         | ... |
| Code stats (scc)            | ... (optional) |
| Deep research plugin        | ... (optional) |
| NotebookLM (Pipeline D)     | ... (optional) |
| Global CLAUDE.md import     | ... |
| coordinator.local.md        | ... |
| Percolation                 | ... (n/a if not a percolation source) |
| Project scaffolding         | Run `/project-onboarding` — it owns lazy directory creation, lessons file, and tracker |

### Available commands

- `/session-start` — Orient session, load context, choose work
- `/session-end` — Wrap up, capture lessons
- `/handoff` — Save state for next session
- `/review` (plans) and `/review-code` (diffs) — Self-contained review skills with inline routing; shared phases in `docs/wiki/reviewer-pipeline.md`
- `/update-docs` — Refresh project documentation, maintain docs/README.md index
- `/distill` — Extract knowledge from session artifacts into wiki guides
- `/project-onboarding` — Full project scaffolding (CLAUDE.md, tracker, docs/README.md, wiki structure)
- `/percolate` — Publish to a registered target; first-run setup walks `docs/wiki/percolate-setup.md` automatically (also walked by `/setup` percolation phase)
```

### Plugin-bundled doctrine wikis

After install, the coordinator plugin ships its operating doctrine as wiki guides at `<plugin-install-path>/docs/wiki/`. Skim a few to see how the EM operates:

- `delegate-execution.md` — how the EM dispatches Sonnet executors against enriched specs.
- `receiving-code-review.md` — how the EM processes review feedback (no performative agreement; triage tables; verify-then-implement).
- `daily-branch-discipline.md` — one branch per machine per day, never branch off main mid-session.
- `tiered-context-loading.md` — how the EM picks between Tier 1 (curated) ↔ Tier 4 (Sonnet scout) for codebase questions.

These wikis are referenced from plugin files (CLAUDE.md, skills, commands) and travel with the plugin install — they update atomically with `claude plugin update coordinator`.

If any **required** items are missing (git), note them prominently.
If any **recommended** items are missing (Agent Teams, CLAUDE.md import), list concrete next steps.

End with: _"`/setup` is environment-only. Run `/project-onboarding` to scaffold a new project (CLAUDE.md, tracker, sessions directory, lessons file). Then run `/session-start` to begin work."_

If `--check-only`, show the table but note what *would* be created/configured without the flag.
