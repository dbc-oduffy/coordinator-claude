---
name: session-start
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
   CLAUDE_INVOKING_COMMAND=session-start ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "chore: session-start sweep — pre-orientation capture"
   ```
2. This is crash insurance. If a previous session died mid-work, this captures its state. The auto-push hook will push to the remote.
3. If nothing to commit, move on silently.

**Do not ask permission.** Non-negotiable safety measure.

### Agent worktree check

Detect-and-warn only — no auto-reap. Salvage belongs in `/workday-start` Step 0.6 (runs once per day); session-start fires many times per day and shouldn't move commits between branches as a side-effect of orientation.

```bash
~/.claude/plugins/coordinator/bin/agent-worktree-sweep.sh --format text
```

If any line is emitted (i.e. at least one `<repo>/.claude/worktrees/agent-*` exists), surface a one-liner:

> _"{N} agent-isolation worktree(s) on disk — Claude Code auto-creates these for `Agent` dispatches and they persist locked until session deletion. Run `/workday-start` to sweep + salvage, or `bin/agent-worktree-sweep.sh --reap` to act now."_

If no output, skip silently — the common case.

### Branch detection

**main is read-only.** All work — including safety commits — must happen on a work branch. Never commit to main directly.

Get on the right branch:

1. **Push health check:** Run `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`.
   If unpushed commits exist, warn: _"Found N unpushed commits — auto-push may have failed. Check .git/push-failures.log."_

2. **If already on a non-main branch:** Report the branch name and continue. Don't switch.
   _"Resuming work on {branch} ({N} commits ahead of main)."_

3. **If on main — create a work branch immediately before doing anything else:**
   - Check local: `git branch --list 'work/{machine}/*'`
   - Check remote: `git branch -r --list 'origin/work/{machine}/*'`
   - Cross-reference with any loaded handoff's `Branch:` field.

   If a branch exists for today (not yet merged):
   _"Found existing branch work/{machine}/{date}. Resuming."_
   `git checkout {branch}`

   If no branch for today (or today's was already merged):
   Run sync-main invariant first:
   ```bash
   ~/.claude/plugins/coordinator/bin/sync-main.sh --quiet
   ```
   If it exits non-zero, report the divergence to the PM before creating the branch.
   Create: `git checkout -b work/{machine}/{date}`
   If name collision: append suffix: `work/{machine}/{date}-2`

   **Note:** `/workday-start` handles branch setup and open-branch consolidation at the start of each workday. If you're starting a new day and workday-start hasn't run yet, the session-start branch creation here is a safety fallback — recommend running `/workday-start` to also consolidate any open branches from previous days.

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

Read `CONTEXT.md` (if it exists at the project root) — domain glossary with canonical terms and `_Avoid_:` synonym lists. If absent, proceed silently — do not flag, suggest, or scaffold.

Note: Project `CLAUDE.md` and global `~/.claude/CLAUDE.md` are already in system context — don't re-read them.

**After reading:** Note the count. No need to recite principles — they're in CLAUDE.md.

### Addon health (RED only + bootstrap notice)

Plugins that ship a doctor skill may write a sentinel at `~/.claude/plugins/<plugin>/data/doctor-last-run.json`. Session-start surfaces RED verdicts only — stale-but-green is workday-start's beat, not every-session noise.

```bash
~/.claude/plugins/coordinator/bin/scan-addon-health.sh --red-only
~/.claude/plugins/coordinator/bin/scan-addon-health.sh --check-sentinel-presence
```

If any lines are emitted by either call, surface them verbatim under an **Addon Health** heading early in the orient output. The `--red-only` call flags active RED verdicts; the `--check-sentinel-presence` call emits a one-time bootstrap notice when plugins are installed but no doctor has been run yet (fresh install). The notice is silent on every subsequent session once any sentinel exists. If both calls produce empty output, skip the heading silently.

- RED verdict: the corresponding doctor skill is the remediation surface (e.g. `/project-rag-ue-addon:doctor`); the EM may dispatch it directly when surfaced.
- Bootstrap notice: prompts the operator to run `/coordinator:setup` and plugin doctors to establish a health baseline.

Schema and convention: `docs/wiki/addon-health-sentinel.md`.

### Coordinator / project-rag binding spot-check

**Conditional on project-rag plugin:** Only if `coordinator_whoami` is importable (i.e. the `coordinator-whoami` package was installed by `setup.sh`). Skip silently if the import fails.

```bash
python3 -m coordinator_whoami.project_rag --human 2>/dev/null | head -20 || true
```

This surfaces the live binding between coordinator and project-rag — registered project root, MCP server args, and addon-health verdict — without launching a full doctor run. Canonical full check: `docs/wiki/coordinator-doctor.md` probe P-6.

If the command emits nothing (package absent or project-rag not registered), skip silently — the addon-health block above already covers the sentinel-presence case.

### Handoffs

Run two `bin/query-records` calls — sub-second by construction, no file walks.

**Primary: actionable-now handoffs.**

```bash
bin/query-records --type handoff \
  --where "deployment_state=ready_to_fire AND status=active" \
  --sort "-created" --format markdown-list
```

Report: _"Found {N} actionable handoffs (deployment_state=ready_to_fire). Run `/pickup <file>` to resume one."_ If empty, say so.

**Gated handoffs (always surface count; list when stale).**

Two queries — first counts everything `awaiting_gate`, second lists the stale subset:

```bash
bin/query-records --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --sort "-created" --format markdown-list

bin/query-records --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --older-than 6d --format markdown-list
```

Reporting rules:

- **If any `awaiting_gate` exist:** surface the full list (titles + gate_dependency, not bodies). The PM may want to clear a gate, retarget, or pick one up even before staleness — silently filtering them is what buries actionable work.
- **If any are >6 days old:** additionally flag _"{M} handoffs awaiting_gate >6 days — gate may be stuck; consider triage or PM clear-gate."_
- **If none exist:** skip silently.

Rationale: the prior >14-day threshold + "only emit if stale" pattern hid gated handoffs that the PM needed visibility on for cross-workstream planning. Six days is roughly one working week — long enough that a gate that hasn't cleared is worth a glance, short enough to catch drift before it ossifies.

**Stale advisory / call-note markdowns are not pendency.** Files in `tasks/handoffs/`, `tasks/`, or `archive/` that look like live work-items (advisories, call-notes, "next-up.md", deferred-action markdowns) may already be addressed by commits that landed after the file was authored. Before treating any markdown's body as a live action item — even if `query-records` surfaces it — run `git log --oneline --since="<file-mtime>" -- <cited-paths>` for the paths it cites. If commits exist on the cited paths since the file's authoring date, the advisory is likely stale; read those commits before re-surfacing the advisory's prescription as live work. Surfacing un-verified stale advisories to the PM as actionable wastes a question.

**Do NOT load, summarize, or act on any handoff.** This applies even if there's only one. One handoff is not implicit selection — the PM may not want to pick it up this session, or may have other priorities first. **Do NOT set `HANDOFF_LOADED`.** That flag is set ONLY when the PM explicitly directs you to a handoff.

**When the PM indicates they want a handoff picked up** — by dropping a link, naming it, or saying "pick up that handoff" — read the full file into context. This — and only this — sets `HANDOFF_LOADED=true` for the Engage section. Alternatively, the PM may use `/pickup` which is purpose-built for handoff resumption and skips the general orientation ceremony.

**Archive lifecycle:** `/pickup` archives the handoff atomically (frontmatter mutation + `git mv` to `archive/handoffs/` + commit, in one operation). Supersession archival happens at `/update-docs` (chain-aware pass for explicit predecessors named via `Continuing from`).

**Path convention:** Active handoffs in `tasks/handoffs/`, archived in `archive/handoffs/`. Both git-tracked.

**Why query, not grep:** `deployment_state` filters out handoffs that aren't ready for execution — the prior per-file walk surfaced everything regardless of state, which is grep-shaped behavior. Sub-second queryability requires a clear filter; the stale-gate flag preserves the deferred-work signal for `awaiting_gate` items without forcing them through the primary list.

**If `tasks/` or `archive/` is gitignored:** Warn the user — these directories must be tracked. `tasks/` contains handoffs and plan docs; `archive/` contains the completion history. `.claude/` contains only platform-managed files (settings, hooks) and need not be tracked.

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

**Stale advisory markdowns ≠ pendency.** Before treating any `tasks/advisory/*.md`, `tasks/call-notes/*.md`, or similarly-named orientation note as a live work item: `git log --oneline -- <path>` to check authoring and last-touch dates. A markdown that hasn't been touched in >14 days is hypothesis until re-verified against current HEAD — it may describe a state already resolved by subsequent commits.

- **Last session-end review (informational):** if `tasks/review-trail/` has any records, surface the most recent one (`ls -t tasks/review-trail/*.json | head -1`) so the EM picks up the chain knowing what was reviewed and where the un-reviewed gap begins.

### Documentation index

Check if `docs/README.md` exists. If it does, note briefly: _"Documentation index at docs/README.md — [N] wiki guides, [N] research files, [N] plans."_ (Count by globbing each directory.) This tells the agent and PM that accumulated project knowledge is available.

If `docs/README.md` does not exist but `docs/guides/` or `docs/research/` does, note: _"Wiki content exists but no docs/README.md index — `/update-docs` will create one."_

If neither exists, skip silently — the project hasn't adopted the wiki system yet.

### Delegation context (game-dev projects)

**Conditional on project type:** Only for projects where `coordinator.local.md` declares `project_type: game-dev` AND `project_subtypes` contains `unreal`. Skip silently if either condition is absent.

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

### Project-RAG subsystem context

**Conditional on MCP availability:** Only if `project-rag` MCP tools are available (check via ToolSearch for `mcp__project-rag__project_subsystem_profile`). Skip silently if unavailable.

When available, call `project_subsystem_profile()` with no arguments (list mode) to discover the project's subsystem map. This returns subsystem names with file counts — enough for the EM to know what's available without loading full profiles.

Report briefly: _"Project subsystems: {N} available via project_subsystem_profile."_

**Key behavior change:** When you need to understand a subsystem before delegating work, call `project_subsystem_profile("<name>")` instead of dispatching an Explore agent. The profile returns C++ surface, BP surface, dependencies, and complexity signals — all deterministic SQL at <200ms, replacing 150-300K token Explore dispatches.

**Freshness nudge:** Also invoke the staleness-survey script. Resolve the plugin CLI path and project root from `~/.claude.json` (same resolution as `commands/workday-start.md` Step 3.6 — do not duplicate threshold logic):

```bash
# Resolve plugin CLI path and project root from ~/.claude.json MCP server args
_rag_cli=$(python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude.json'))); args=d['mcpServers']['project-rag']['args']; print(next(a for a in args if a.endswith('.py') or a.endswith('cli')))" 2>/dev/null)
_rag_root=$(python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude.json'))); args=d['mcpServers']['project-rag']['args']; print(args[-1])" 2>/dev/null)
python3 "$_rag_cli" staleness-survey --project-root "$_rag_root" --json
```

If verdict ≠ `current`, append one line to the orientation brief:

> _"Project-RAG last scanned {age}. Verdict: {verdict}. Recommend: {recommendation_command}."_

Skip silently if verdict is `current`, or if either path could not be resolved from `~/.claude.json`.

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
6. **Work the backlog** — Improvement queues, deferred items, recurring lessons. Central queue: `~/.claude/tasks/coordinator-improvement-queue.md`; local queue: `tasks/improvement-queue.md`. Surface current depth when framing this option (e.g., "Central: 17 entries, 3 with recurring ≥ 3. Local: 2 entries. Want to tackle some of these?"). Also check `tasks/bug-backlog.md` — if it exists and has ≥10 open items (P1 + P2 rows, excluding resolved), advocate `/bug-blitz` as a backlog-grinding option.
7. **Other** — Something else (describe it)

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
