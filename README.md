# coordinator-claude

**A PM-native operating layer for AI engineering work.** An opinionated Claude Code plugin that turns product intent into scoped plans, delegated implementation, evidence, and ship/no-ship decisions. You're PM. Claude is EM. You stay technical enough to spot when something's wrong; the EM handles the rest.

## Who This Is For

You don't need to write code. You need to know enough to evaluate it — to spot when something smells wrong, to ask the right questions, to set direction. Amjad Masad (Replit's founder) [opined](https://youtu.be/PlDeqGQZ0CQ) that people who *don't* program may actually be better positioned for the LLM-coding world: they won't micromanage implementation. This plugin leans into that. It gives Claude standing authority to make engineering decisions — how to build, who to delegate to, when to refactor — while you hold product authority: what to build, what to cut, what ships. Just like an EM-PM dynamic.

What this system asks of the PM is altitude, not tactics. Architectural judgment, scope decisions, refactor-vs-patch calls, what-ships-and-what-doesn't. Slop is fought on the *plan* level — by treating each plan as an exhaustive software design document with named-reviewer pushback baked in, not by spot-checking commits afterward. The natural model defaults — act fast and move on, defer P2s into oblivion, size work in human-sprint timeframes — are the things this system is built to push back against. The PM sets direction; the EM and the named reviewers do the pushing.

This isn't a collection of prompt tricks. It's a **decision architecture**: routines (session orientation, plan review, multi-source code review, structured handoffs, daily flows) plus authority boundaries (EM owns implementation, PM owns scope/ship) plus reviewer personas that push back with fix-gates between them. Reviews are meaningful — blocking findings, not theatre. And the system actively reads its own accumulated wikis and lessons before drafting new plans (`prior-art-checker` pre-flight, `/learn-lessons` triage), so the scar tissue from past decisions informs the next one rather than sitting in a write-only memory file. It maps to how PM-EM collaboration actually feels in a real engineering team. The difference is that your "team" can work autonomously for hours, and you can review the output when you're ready.

## What This Is *Not*

- **Not another agent framework.** Claude Code already has subagents, plugins, skills, hooks, and MCP. This sits *on top of* that infrastructure — it doesn't compete with it.
- **Not a PRD-to-code pipeline.** Product intent is captured inside plan mode and acceptance criteria, not in a separate PRD funnel.
- **Not an autonomous coding agent.** The PM is in the loop on scope, tradeoffs, and ship decisions by design. Autonomous modes (`/mise-en-place`, `/autonomous`) exist for execution sprints, not for product authority.
- **Not a developer productivity tool.** The target user evaluates engineering work — they don't write it. If you want to be more productive at writing code yourself, you want vanilla Claude Code; this is for managing AI engineering work, not doing it.
- **Not aimed at the fully non-technical PM** (yet). The current sweet spot is a PM with technical altitude but not technical hands — someone who has architectural judgment, recognizes unwise plan-shape, and can spot when a plan, an architectural choice, or a tradeoff sounds wrong from how the EM describes it, without ever reading a diff. The PM does not review commits, does not perform code review, does not sign off on PRs. That altitude is the load-bearing constraint: code review and PR sign-off are delegated to AI peers and named-persona staff-tier reviewers (see below). Complex codebases require a PM who can tell when something looks wrong from the conversation, not from the patch.

🤖 Agents: start here → [AGENTS.md](AGENTS.md)

## Quick Start

You don't install this — your agent does. Open Claude Code in any project and paste:

```
Install coordinator-claude. The playbook is at
https://github.com/dbc-oduffy/coordinator-claude/blob/main/docs/agent-install.md
— read it, follow it, and queue /coordinator:repo-setup as the immediate
next step after I restart Claude Code.
```

Claude clones the repo, installs the plugins with the native `claude plugin` CLI (`claude plugin marketplace add dbc-oduffy/coordinator-claude` then `claude plugin install coordinator@coordinator-claude`), and tells you when to restart. (The marketplace is the public GitHub repo, not your clone, so the install lives entirely under `~/.claude` — delete or move the clone afterward and the plugins keep working.) After restart, `/coordinator:install` finishes the environment wiring and `/coordinator:repo-setup` bootstraps tracking infrastructure in your project.

**One hard dependency, not part of this install.** coordinator-claude declares a hard dependency
on the coordinator engine, which handles all durable work-state mutation. It is published as
[`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter) — **that publish is not yet
live**; until it is, the engine is available on request from the maintainer. Without it you keep
every pure-prompt flow (planning, review, personas, shaping) and lose the state machine (claiming
handoffs, memo resolution, coverage computation, terminal stamping). See "The engine underneath"
below for the detail.

**Auditing & uninstall** → [`docs/safety.md`](docs/safety.md) — what the install changes, what it does not do, audit commands, and exact uninstall steps.

**Why it's built this way** → [`MANIFESTO.md`](MANIFESTO.md) — why the system is split into a doctrine plugin and a separate engine, and what that split buys.

**What we actually measured** → [`docs/evidence.md`](docs/evidence.md) — the experiments behind the design, including the ones that reversed a position we'd already written down, and an explicit line between what was measured and what changed on a single observed failure.

**Updating** → `/coordinator-update` checks whether a newer version has been published, computes a classified delta against your live install, and advises a migration path that preserves your customizations by default (renamed reviewer personas, per-project config, any structural divergence) — it never blind-overwrites. It's PM-invoked and advisory only: it computes and recommends, it doesn't apply anything without your explicit say-so.

## Compatibility

| coordinator-claude | Claude Code | OS tested | Notes |
|--------------------|-------------|-----------|-------|
| v3.x | tested with Claude Code 2.1.186 (native `claude plugin` CLI install); minimum version not formally established | macOS, Linux, WSL, Windows (Git Bash) | Install: `claude plugin marketplace add dbc-oduffy/coordinator-claude` + `claude plugin install coordinator@coordinator-claude`, then `/coordinator:install` after restart. **Requires bash 4.3+** — coordinator's scripts use associative arrays (4.0+) and `coordinator-safe-commit` uses `local -n` namerefs (4.3+). macOS ships bash 3.2 as `/bin/bash`, so Mac users install [Homebrew](https://brew.sh) and `brew install bash` (put it first on PATH); `/coordinator:install` fails fast with this guidance under 4.3. Linux/WSL/Git Bash ship bash 4.3+. Windows: install a real `python3` (the Store App-Execution-Alias stub breaks it) — see [docs/agent-install.md](docs/agent-install.md) Prerequisites. |

## How a Session Works

Most tools hand you a bag of commands and wish you luck. This system has *routines* — woven into the session lifecycle so you don't have to remember them. Some fire automatically via lifecycle hooks (boot orientation, the context-pressure nudge); the rest are one-keystroke ceremonies the EM runs at the right moment. The distinction matters: *hooks* are what actually fire on their own; the slash commands below are invoked — by you, or by the EM on your behalf.

**Starting up.** When Claude opens a supported project, a `SessionStart` hook fires automatically — loading the current branch, pending handoffs, lessons from past sessions, project vitals, and an orientation cache. No cold start. Claude lands in the middle of the context window where performance is strongest, with forward-looking state already loaded. This is deliberate: research shows LLMs degrade toward the end of their context and, to a lesser extent, at the beginning ([Liu et al. 2023, "Lost in the Middle"](https://arxiv.org/abs/2307.03172)). The orientation hook front-loads context so the working session occupies the optimal window.

**Sizing, first.** Before anything gets planned, shaped, or dispatched, every ask passes through a sizing gate — a cheap t-shirt-size read against disk state that decides where it goes: a tiny fix is a direct edit, a vague or multi-subsystem ask routes to `/brainstorming` to converge on requirements, a shaped problem with real decision weight routes to `/plan`, and something needing PM-side scope alignment first routes to `/shape`. This is the EM's *first move* on a novel ask, not an optional pre-check — it's how a session begins, not a separate ceremony you invoke.

**Planning.** You describe what you want. Claude enters plan mode — but the plan isn't just written and executed. You review it. In a real dev team, the PM doesn't just say "build auth" and disappear; they review the spec, push back on scope, ask about edge cases. That's what happens here. The `coordinator:plan` skill is a decision-tree super-skill (triage → substrate → compose → exit) that mechanically binds the trigger word "plan" to the full pipeline: the prior-art-checker pre-flight cross-references the plan against accumulated wikis, lessons, and improvement queues to surface conflicts *before* an Opus reviewer touches it; the Staff Engineer then reviews; the integrator applies findings. For bigger decisions, `/staff-session` spawns role-based engineers who independently develop positions and debate to consensus — like pulling your tech lead and director of engineering into a room.

**Building.** Claude delegates to Sonnet subagents for implementation — cheaper, faster, fresh context. A `PreToolUse` hook nudges Claude away from doing implementation work directly, because the orchestrator's context is too valuable to spend on writing code. This is the same principle as a real EM: you don't want your engineering manager writing production code when they should be coordinating.

**Reviewing.** Code review comes from named personas with rich behavioral profiles — a domain expert reviews first (e.g., a web-dev specialist for front-end work, or a data-science specialist for ML pipelines), all findings are applied, then a generalist reviews the clean artifact. Sequential, with mandatory fix gates. Research supports both the persona mechanism (literature-backed for judgment-routing tasks; for mechanical bug-finding our own controlled experiment found no recall gain — that's why bug-sweeps use bare agents) and [multi-agent review gains](https://www.anthropic.com/engineering/multi-agent-research-system) (Anthropic's own eval showed 90.2% improvement over single-agent). Plan-review with personas — the system's main use of named reviewers — leans on industry-standard PRD/SDD review patterns; we have not separately benchmarked it.

**Staying coherent.** Long sessions hit a hard constraint: context compaction. When triggered, the model summarizes what it *thinks* happened — a retrospective reconstruction that loses intent. A `PostToolUse` hook monitors context pressure and prompts Claude to create a structured handoff *before* compaction fires: decisions made, state reached, explicit next steps. Each handoff chains forward from its predecessor. Research shows structured handoffs significantly outperform automatic summarization ([Kang et al. 2025, ACON](https://arxiv.org/abs/2510.00615); Sourcegraph [retired compaction](https://sourcegraph.com/blog) in their Amp agent in favor of explicit handoffs after measuring degradation).

**Navigating the codebase.** This system invests heavily in documentation-as-navigation. Claude's natural mode is grep-heavy — searching text, reading prose, following paper trails. An architecture atlas, project tracker, orientation caches, and structured comments throughout the codebase give Claude something to *find* when it searches. We call this "grep bait." It's why the doc maintenance pipeline and architecture atlas exist: not bureaucracy, but navigation infrastructure that lets Claude plan from 60 lines of orientation instead of reading 20 source files cold. Research artifacts, lessons files, and handoff documents all serve double duty — they record decisions *and* create searchable landmarks for future sessions.

**Wrapping up.** `/workstream-complete` captures lessons, updates documentation, and commits state. `/workday-complete` goes further: syncs docs, merges to main via PR, and optionally hibernates the machine. The cycle is continuous — each session starts where the last one left off.

**A tier above the workstream loop.** Everything above operates at the level of one ask, one plan, one merge. Goals/OKRs sit a level up: a per-repo goal artifact (`state/goals/<slug>.yaml`) records the strategic objective an initiative serves and tracks whether the fleet is winning against it — not "did this ship" but "did it move the number." `/roadmap-planning` shapes raw research or intent into a ratified, graphed roadmap of batons that later plans and workstreams draw from, so a session doesn't have to re-derive "why are we doing this" from memory. This altitude is PM-gated by design — direction lives with the PM, not something the EM infers from ticket volume.

## What You Need to Remember

The EM handles most of this on its own. Your key moves:

| Command | When | What It Does |
|---------|------|-------------|
| `/workstream-start` | Beginning of work | Deliberate orientation — triage handoffs, surface staleness, choose work. PM-invoked; *not* auto-fired. (Boot context loads automatically via a separate `SessionStart` hook; this command is the optional deeper orient.) |
| `/pickup` | Resuming work | Load a handoff artifact and continue where you left off |
| `/handoff` | Stepping away | Save session state for the next session |
| `/staff-session` | Big decisions | Multi-perspective planning or review from persona-based contributors |
| `/mise-en-place` | Heads-down time | Claude burns through the backlog autonomously — no input needed |
| `/autonomous` | Override | Suppress handoff nudges when you want Claude to push through compaction |

That's it for daily use. Everything else — delegation, review routing, doc maintenance — the EM drives as part of its workflow; context-pressure management is the one piece handled automatically, by a `PostToolUse` hook. You don't have to ask for any of it.

## Flows

Don't memorize commands; learn five flows. Most of what the system does, you'll touch through one of these.

**Flow 1 — Build a feature.** You describe intent → Claude enters plan mode and proposes acceptance criteria + scope mode → you review and approve → Claude delegates implementation → reviewers (domain expert first, generalist second) check the artifact with fix gates between → for user-visible work or patches that smell like they should be refactors, **the VP-Product Reviewer** (`coordinator:vp-product`) — scope challenger, naming optional via `/coordinator:install` Phase 6 — stress-tests the choice → `/merging-to-main` produces a ship verdict and you decide.

**Flow 2 — Fix a bug.** Reproduction first (don't trust the report) → root cause via the [systematic-debugging guide](docs/wiki/systematic-debugging.md) → scoped fix in production-patch mode (minimal diff, no opportunistic refactors) → regression check → reviewer → merge. For codebase-wide grinds, `/bug-blitz` autonomously works through the bug backlog with EM-serial commits at each wave gate.

**Flow 3 — Resume work.** The boot `SessionStart` hook automatically loads orientation, lessons, and pending handoffs into context → optionally run `/workstream-start` for a deeper triage → you pick up via `/pickup <handoff>` or pick from the menu → Claude lands mid-context and starts where the last session stopped.

**Flow 4 — Autonomous sprint.** `/mise-en-place` gathers ready work, builds a compaction-proof flight recorder, and executes through the backlog without stopping. `/autonomous` suppresses handoff nudges when you want it to push through context pressure.

**Flow 5 — Architecture change.** `/staff-session plan` (multi-perspective debate) → migration plan with rollback → architecture mode review → implementation → verification → architecture atlas update via `/update-docs`.

**Closing the day:** `/workday-complete` validates, syncs, runs the daily review, and merges. `/workweek-complete` is the larger weekly ceremony with version bump and release notes — and it's the only place `/parallel-code-review` runs. That command is the pre-merge gate: it chunks the week's diff across parallel reviewer dispatches instead of one reviewer reading everything serially, then folds their findings into a single ship/no-ship verdict. It's deliberately *not* available outside `/workweek-complete` — a weekly gate invoked ad-hoc stops being a gate.

## How heavy is the workflow?

The system scales — a typo fix is a two-word instruction; a system rewrite is a multi-agent pipeline. Here are three representative tiers:

| Tier | Skill / command | Reviewer | Wall time |
|------|-----------------|----------|-----------|
| **Tiny edit** (typo, constant, rename) | Direct EM edit — no plan | None required | < 5 min |
| **Feature** (new command, new skill) | `/execute-plan` after PM approves a plan | Domain reviewer → the Staff Engineer (`coordinator:staff-eng`) generalist; the Director of Engineering (`coordinator:eng-director`) as backstop at High effort (sequential) | 30 min – 2 hrs |
| **System rewrite** (multi-plugin overhaul) | `/staff-session plan` → `/execute-plan` (with executor dispatch per [`docs/wiki/delegate-execution.md`](docs/wiki/delegate-execution.md)) | Full sequential chain + PM ship verdict | Half day+ |

<details>
<summary><strong>All Commands (appendix)</strong></summary>

All 46 commands the plugin ships, grouped by where they sit in a session:

**Session cadence**

| Command | Purpose |
|---------|---------|
| `/workstream-start` | Orient session — preflight, load context, choose work |
| `/workstream-complete` | Wrap up finished work — capture lessons, update docs |
| `/workday-start` | Morning orient — triage handoffs, surface staleness, align priorities |
| `/workday-complete` | End-of-day wrap — validate, consolidate branches, review, changelog |
| `/workweek-start` | Weekly orient — review last week, set this week's priorities |
| `/workweek-complete` | Weekly release ceremony — validate, docs, release notes, merge |
| `/quick-wrap` | Short session close: commit, handle loose ends, stop — not `/workstream-complete` |
| `/pickup` | Resume from a handoff or action a cross-repo memo — grab the baton |
| `/handoff` | Mid-workstream save-state under context pressure — always a continuation |
| `/spinoff` | PM-gated: fork a mid-session topic into its own handoff |
| `/autonomous` | Toggle autonomous mode — suppresses handoff nudges near compaction |

**Intake — sizing, shaping, planning**

| Command | Purpose |
|---------|---------|
| `/brainstorming` | Shapes vague or multi-subsystem asks into requirements before planning |
| `/shape` | Converge with the PM on a problem's shape before any solutioning |
| `/plan` | Decision-weight planning: multi-file, abstraction, cross-system, agent scaffold, reversed prior |
| `/staff-session` | PM-gated: Agent Teams review for architecture calls (plan or review mode) |
| `/roadmap-planning` | PM-gated: shape research into a ratified, graphed roadmap of batons |
| `/research` | PM-gated deep research — web, repo, or structured |
| `/notebooklm-research` | PM-gated: NotebookLM research for video/audio sources |

**Execution**

| Command | Purpose |
|---------|---------|
| `/execute-plan` | Executes a PM-approved plan via dispatched per-chunk executor waves |
| `/enrich-and-review` | Runs the enrichment pipeline over plan chunk directories |
| `/mise-en-place` | Autonomous backlog run — flight-recorder prep, then run-through |
| `/dogfood` | Fix-through loop — invoke a new thing, fix bugs until it works |
| `/new-project` | Scaffolds and onboards a new repo (vs. `/repo-setup`'s onboard-existing) |
| `/repo-setup` | First-time setup for an existing repo, single or fleet-wide (`--batch`) |
| `/systematic-debugging` | Root-cause one known bug — reproduce, trace to source, fix, verify |

**Review and merge**

| Command | Purpose |
|---------|---------|
| `/review` | Review a plan/design doc or code diff — findings land on either one |
| `/review-code` | Review a ready diff/PR, or apply landed code-review findings |
| `/parallel-code-review` | Weekly pre-merge code-review gate — chunk reviewers, one verdict. `/workweek-complete` only |
| `/plan-delivery-audit` | Triangulate plan claims against code and reviews for delivery status |
| `/architecture-audit` | Rotational arch audit — score systems, audit the top, package spinoffs. Never edits code |
| `/architecture-survey` | Build or refresh the architecture atlas via scout, analyst, synth |
| `/merging-to-main` | Merges a ready branch to main — release notes, PR, CI wait, cleanup |
| `/finishing-a-development-branch` | Presents merge, PR, or cleanup options once tests pass |
| `/consolidate-git` | Cleans up branch sprawl — consolidates and prunes stale branches |
| `/validate` | Run the project's fast test command at a cadence gate |

**Backlog and health**

| Command | Purpose |
|---------|---------|
| `/bug-sweep` | Codebase bug hunt — find and fix AI-fixable bugs, defer the rest |
| `/bug-blitz` | Grind the bug backlog and tests; fix small, surface big items to PM |
| `/debt-triage` | EM-PM ceremony to review and prioritize the technical debt backlog |
| `/code-health` | Night-shift code review — dispatch reviewer, apply findings, track |
| `/cruft-sweep` | Scan for reclaimable scratch and orphans; apply only if confirmed |
| `/learn-lessons` | Processes lessons/ entries as doctrine change-requests, local or central |
| `/distill` | Distill session artifacts to wiki and decisions; archive specs, drop scratch |
| `/update-docs` | Sync all documentation artifacts to the current codebase state |

**Install and lifecycle**

| Command | Purpose |
|---------|---------|
| `/install` | Installs the coordinator plugin — checks prereqs, configures project |
| `/uninstall` | Reverses the coordinator install — full removal or revert to marketplace |
| `/percolate` | Dry-run, then confirm-publish files to a repo target, gated by CI |

That's 46. `/coordinator-update` (see [Updating](#quick-start) above) is a 47th, OSS-only skill delivered separately from this list — it isn't in `commands/`.

</details>

<details>
<summary><strong>How this maps to real teams</strong></summary>

| Real Team Practice | coordinator-claude Equivalent |
|--------------------|-------------------------------|
| **Daily standup** | `/workstream-start` — what happened, what's blocked, what's next |
| **Sprint planning** | `/staff-session plan` — persona-based engineers debate approach |
| **Spec review** | Plan mode with PM sign-off — Claude proposes, you approve |
| **Code review** | `/review-code` — domain expert first, generalist second, fix gates between |
| **Tech lead gut-check** | Any reviewer can be dispatched ad-hoc for a quick assessment |
| **Retrospective** | `/workstream-complete` — capture lessons, update docs |
| **Heads-down sprint** | `/mise-en-place` — autonomous execution through the backlog |
| **Handoff between shifts** | `/handoff` — structured state capture, not "check the git log" |

The one role we don't have deeply embedded in workflows: **designer.** Meatspace designers are still better at that, and their judgment is going to remain difficult for LLMs to replicate. There's a vibe-design functionality, but it's not gonna rock your world.

</details>

<details>
<summary><strong>Under the hood — architecture details</strong></summary>

**Inverted capability delegation.** The coordinator sees ~8 thin MCP tools; domain agents access 40+ via proxy with full schemas. This saves ~40K tokens from the coordinator's context and forces delegation by design. A `PreToolUse` hook nudges the coordinator when it reaches for domain tools directly.

**Proactive artifact generation.** Before compaction fires, a hook prompts structured handoff creation — a prospective document capturing decisions, state, and next steps. Each artifact chains from its predecessor (cascade obligation) and opens with a synthesis of the prior handoff (anti-amnesia chain).

**Role-based sequential review.** Reviewers carry rich behavioral profiles — not just "code reviewer" but distinct roles with expertise domains and review lenses. Sequential review with mandatory fix gates means each reviewer sees a clean artifact. Role labels ship as defaults; an optional naming flow lets users bind personal names to roles if that aids their cognitive ease.

**6-layer project knowledge.** Structure, architecture, activity, temporal, intent, state — none bulk-loaded. A tiered context model loads a ~60-line orientation cache at L1, pulls detailed artifacts on demand at L2, and reserves L3 for deep storage read by subagents. An 11-phase maintenance pipeline fights doc staleness automatically.

**Agent Teams for planning.** Claude Code's [Agent Teams](https://docs.anthropic.com/en/docs/claude-code/agent-teams) enables multiple Claude sessions that communicate and coordinate. This system uses it for multi-perspective planning: persona-based debaters form independent positions, challenge each other, and a synthesizer cross-references into consensus. The same machinery backs the bundled `/research` pipelines (internet, repo, structured, NotebookLM).

**The artifact-shape contract.** Coordinator's on-disk state — handoffs, plans, decisions, review-trail entries, backlog queues — isn't a pile of prose for grep to stumble over. Each artifact type is a registered, versioned JSON Schema (published under `schemas/` and `cockpit-contract/schema/`), so a consumer can query "what's LIVE / BLOCKED / DONE" against the schema's own liveness mapping instead of re-deriving parsing logic per artifact type per consumer. That's the difference between a substrate you can query and one you can only grep.

**Cross-model delegation.** Haiku for mechanical checks, Sonnet for most execution, Opus for judgment and synthesis — routed by task weight, not one model doing everything.

**The engine underneath.** Most skills issue their state-mutating operations (plan-tasks, roadmap emission, review-trail writes, percolate/release) through `coordinator_core`, a command-type op-registry engine published as a separate companion repository, [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter), rather than inside this plugin. **That publish is not yet live** — until it is, the engine is available on request from the maintainer, the same access model already used for `project-rag`. coordinator-claude declares a hard dependency on it, and most of the 36 bundled skills call into it, directly or through a settings-home forwarder. Skills degrade gracefully without it — the plan-review, brainstorming, and shape flows are pure-prompt and need nothing beyond this plugin — but ceremony-cadence skills that read/write on-disk state (goals/roadmap, review-trail, percolate) expect it on the machine-local registry.

See [docs/wiki/](docs/wiki/) for the doctrine pages that ship with this release — including the testable claims about what each agent role promises and which hook or script enforces each promise.

This system's design responds directly to known failure modes: false completion, silent scope expansion, test theater, review laundering, context amnesia, integration blindness, and a dozen others.

</details>

## Plugins

A single **coordinator** plugin, at the repo root — core orchestration, all named reviewer personas, and every workflow skill, with domain and research capabilities bundled in rather than installed separately:

| Capability | Purpose | When It Activates |
|--------|---------|----------------|
| **Core orchestration** | Plan-enrich-chunk-review pipeline, session continuity, fan-out dispatch, all workflow skills | Always |
| **Front-end review** (web-dev) | Front-end architecture review + UX flow review | Web projects |
| **Data-science review** (data-science) | ML, statistics, data modeling review | ML/data work |
| **Research pipelines** (deep-research) | Internet, repo, structured, and NotebookLM research pipelines | On demand (`/coordinator:research`) |

Domain reviewers activate per-project via `.claude/coordinator.local.md` (`project_type`); there is nothing separate to install or enable.

## Customization

- **Name your reviewers (optional).** Role labels ship as the default — bind chosen names to role labels in `/coordinator:install` Phase 6 (Persona Customization), or hand-edit them across the plugin files.
- **Create your own domain reviewer.** The bundled domain reviewer agents are the reference pattern: `agents/senior-front-end.md` (Front-end Reviewer), `agents/staff-ux.md` (UX Reviewer), `agents/staff-data-sci.md` (Data Science Reviewer, ML/statistics). Each is a single agent prompt file with a behavioral profile and routing rules — copy one as a starting point for your own specialization, then activate it per-project via `.claude/coordinator.local.md`'s `project_type`.
- **Per-project configuration.** Create `.claude/coordinator.local.md` with `project_type` to control which reviewers activate.

## Companion Plugins

- **[clangd-lsp](https://github.com/anthropics/claude-code-plugins/tree/main/clangd-lsp)** — C++ code intelligence. Reviewer agents gain go-to-definition, find-references, and call hierarchy ‒ helpful for those (like us) using Claude Code with Unreal Engine.
- **[Context7](https://github.com/upstash/context7)** — External library documentation lookup.

All are optional. Coordinator works without them; relevant features degrade gracefully.

<details>
<summary><strong>Directory structure</strong></summary>

```
coordinator-claude/                 # flat Claude Code marketplace — single plugin at repo root
├── .claude-plugin/                 # marketplace.json (auto-discovery, one entry: coordinator) + plugin.json
├── agents/                         # enricher, executor, docs-checker, generalist + domain reviewers
│                                    #   (senior-front-end, staff-ux, staff-data-sci), eng-director, research agents
├── bin/                            # executable helper scripts behind commands/ and hooks/
├── commands/                       # 46 workflow commands (hook/ceremony auto-runners)
├── hooks/                          # context pressure, orientation, commit validation, tier-usage instrumentation (local only)
├── lib/                            # shared shell/python helpers behind bin/ and hooks/
├── skills/                         # planning, sizing, goals/OKR, review, debugging, TDD, etc.
├── snippets/                       # shared prompt fragments consumed by skills/agents/commands
├── whoami/                         # plugin identity + health-sentinel package
├── cockpit-contract/schema/        # published slice of the artifact-shape contract
├── schemas/                        # goal/spike/registry JSON Schemas for the tracked artifact types
├── templates/                      # scaffolds: CLAUDE.md, .gitignore, machine-local registry, CI snippet
└── docs/
    ├── install/                    # install manifest + playbook internals
    ├── wiki/                       # curated doctrine excerpts (sizing, goals/OKR, delegate-execution, ...)
    └── agent-install.md            # the install playbook entry point
```

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

**Plugins not loading:**
- Check `enabledPlugins` in `~/.claude/settings.json` — must be `true`
- Check `~/.claude/plugins/installed_plugins.json` — must have entry with correct `installPath`
- Restart Claude Code (changes take effect on next session)
- `/coordinator:install` (run after restart) manages all config files automatically

**Plugin cache not syncing after editing source:**
- Claude Code caches plugins by version. Re-run `claude plugin install coordinator@coordinator-claude` to pick up a newer published version; contributors editing plugin source locally, see [CONTRIBUTING.md](CONTRIBUTING.md).

**Per-project reviewer selection:**
- Create `.claude/coordinator.local.md` with `project_type` field
- Coordinator is always enabled; the bundled domain reviewers activate per-project based on `project_type`

</details>

---

[Dónal O'Duffy](https://github.com/dbc-oduffy) & Claude
