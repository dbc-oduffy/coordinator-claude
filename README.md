# coordinator-claude

A Claude Code plugin that runs your projects like a real dev team — you're PM, Claude is EM.

## Who This Is For

You don't need to write code. You need to know enough to evaluate it — to spot when something smells wrong, to ask the right questions, to set direction. Amjad Masad (Replit's founder) [opined](https://youtu.be/PlDeqGQZ0CQ) that people who *don't* program may actually be better positioned for the LLM-coding world: they won't micromanage implementation. This plugin leans into that. It gives Claude standing authority to make engineering decisions — how to build, who to delegate to, when to refactor — while you hold product authority: what to build, what to cut, what ships. Just like an EM-PM dynamic.

This isn't a collection of prompt tricks. It's a trust model with routines — session orientation, plan review, multi-source code review, structured handoffs, daily flows — that map to how real engineering teams operate. The difference is that your "team" can work autonomously for hours, and you can review the output when you're ready.

## Quick Start

You don't install this. Your agent does. Open Claude Code in any project and paste:

```
Install coordinator-claude. The playbook is at
https://github.com/dbc-oduffy/coordinator-claude/blob/main/docs/agent-install.md
— read it, follow it, and queue /project-onboarding as the immediate next step
after I restart Claude Code.
```

Claude clones the repo, runs the installer, validates the result, and tells you when to restart. After restart, `/project-onboarding` bootstraps tracking infrastructure in your project.

## How a Session Works

Most tools hand you a bag of commands and wish you luck. This system has *routines* — things that happen automatically because they should always happen, woven into the session lifecycle so you don't have to remember them.

**Starting up.** When Claude opens a supported project, a `SessionStart` hook fires automatically — loading the current branch, pending handoffs, lessons from past sessions, project vitals, and an orientation cache. No cold start. Claude lands in the middle of the context window where performance is strongest, with forward-looking state already loaded. This is deliberate: research shows LLMs degrade toward the end of their context and, to a lesser extent, at the beginning ([Liu et al. 2023, "Lost in the Middle"](https://arxiv.org/abs/2307.03172)). The orientation hook front-loads context so the working session occupies the optimal window.

**Planning.** You describe what you want. Claude enters plan mode — but the plan isn't just written and executed. You review it. In a real dev team, the PM doesn't just say "build auth" and disappear; they review the spec, push back on scope, ask about edge cases. That's what happens here. For bigger decisions, `/staff-session` spawns persona-based engineers who independently develop positions and debate to consensus — like pulling your tech lead and director of engineering into a room.

**Building.** Claude delegates to Sonnet subagents for implementation — cheaper, faster, fresh context. A `PreToolUse` hook nudges Claude away from doing implementation work directly, because the orchestrator's context is too valuable to spend on writing code. This is the same principle as a real EM: you don't want your engineering manager writing production code when they should be coordinating.

**Reviewing.** Code review comes from named personas with rich behavioral profiles — a domain expert reviews first (e.g., a game-dev specialist for Unreal code), all findings are applied, then a generalist reviews the clean artifact. Sequential, with mandatory fix gates. Research supports both the [persona mechanism](docs/research/2026-03-19-named-persona-performance.md) and [multi-agent review gains](https://www.anthropic.com/engineering/multi-agent-research-system) (Anthropic's own eval showed 90.2% improvement over single-agent).

**Staying coherent.** Long sessions hit a hard constraint: context compaction. When triggered, the model summarizes what it *thinks* happened — a retrospective reconstruction that loses intent. A `PostToolUse` hook monitors context pressure and prompts Claude to create a structured handoff *before* compaction fires: decisions made, state reached, explicit next steps. Each handoff chains forward from its predecessor. Research shows structured handoffs significantly outperform automatic summarization ([Kang et al. 2025, ACON](https://arxiv.org/abs/2510.00615); Sourcegraph [retired compaction](https://sourcegraph.com/blog) in their Amp agent in favor of explicit handoffs after measuring degradation).

**Navigating the codebase.** This system invests heavily in documentation-as-navigation. Claude's natural mode is grep-heavy — searching text, reading prose, following paper trails. An architecture atlas, project tracker, orientation caches, and structured comments throughout the codebase give Claude something to *find* when it searches. We call this "grep bait." It's why the doc maintenance pipeline and architecture atlas exist: not bureaucracy, but navigation infrastructure that lets Claude plan from 60 lines of orientation instead of reading 20 source files cold. Research artifacts, lessons files, and handoff documents all serve double duty — they record decisions *and* create searchable landmarks for future sessions.

**Wrapping up.** `/session-end` captures lessons, updates documentation, and commits state. `/workday-complete` goes further: syncs docs, merges to main via PR, and optionally hibernates the machine. The cycle is continuous — each session starts where the last one left off.

## What You Need to Remember

The EM handles most of this automatically. Your key moves:

| Command | When | What It Does |
|---------|------|-------------|
| `/session-start` | Beginning of work | Orient Claude to your project (also auto-fires via hooks) |
| `/pickup` | Resuming work | Load a handoff artifact and continue where you left off |
| `/handoff` | Stepping away | Save session state for the next session |
| `/staff-session` | Big decisions | Multi-perspective planning or review from persona-based contributors |
| `/mise-en-place` | Heads-down time | Claude burns through the backlog autonomously — no input needed |
| `/autonomous` | Override | Suppress handoff nudges when you want Claude to push through compaction |

That's it for daily use. Everything else — delegation, review routing, doc maintenance, context pressure management — either happens automatically or is suggested for your use.

## All Commands

| Command | Purpose | Why It Exists |
|---------|---------|---------------|
| `/session-start` | Orient to project, load context, choose work | Eliminate cold starts; position key context optimally |
| `/session-end` | Capture lessons, update docs, commit | Preserve institutional knowledge between sessions |
| `/pickup` | Resume from a handoff artifact | Structured continuity beats re-reading git log |
| `/handoff` | Save state before stepping away | Prospective capture > retrospective reconstruction |
| `/staff-session` | Multi-perspective planning or review | Debate surfaces tradeoffs a solo agent misses |
| `/mise-en-place` | Autonomous backlog execution | Front-load all context, then execute without interruption |
| `/autonomous` | Toggle autonomous mode | Trust escalation — suppress handoff nudges |
| `/workday-start` | Morning orientation and triage | Surface staleness, align priorities, suggest work |
| `/workday-complete` | End-of-day wrap-up | Update docs, merge to main, optionally hibernate |
| `/review-dispatch` | Route an artifact to the right reviewer | Domain expert → generalist, sequential with fix gates |
| `/execute-plan` | Execute a PM-approved plan | Direct implementation without re-planning |
| `/delegate-execution` | Dispatch enriched stubs to executor agents | Parallel agent execution for chunked work |
| `/update-docs` | Repo-wide documentation maintenance | 11-phase pipeline that fights doc staleness |
| `/daily-review` | Strategic daily review | Inventory today's work, get architectural perspective |
| `/bug-sweep` | Systematic codebase bug hunt | Find and fix all AI-fixable bugs in-session |
| `/code-health` | Night-shift code health review | Scan today's commits, dispatch reviewer, apply findings |
| `/architecture-audit` | Deep architecture analysis | Multi-phase agent pipeline for system health |
| `/generate-repomap` | Generate ranked repo map | Context injection for LLM navigation |
| `/distill` | Extract knowledge from session artifacts | Turn plans and handoffs into evergreen wiki docs |

<details>
<summary><strong>How this maps to real teams</strong></summary>

| Real Team Practice | coordinator-claude Equivalent |
|--------------------|-------------------------------|
| **Daily standup** | `/session-start` — what happened, what's blocked, what's next |
| **Sprint planning** | `/staff-session plan` — persona-based engineers debate approach |
| **Spec review** | Plan mode with PM sign-off — Claude proposes, you approve |
| **Code review** | `/review-dispatch` — domain expert first, generalist second, fix gates between |
| **Tech lead gut-check** | Any reviewer can be dispatched ad-hoc for a quick assessment |
| **Retrospective** | `/session-end` — capture lessons, update docs |
| **Heads-down sprint** | `/mise-en-place` — autonomous execution through the backlog |
| **Handoff between shifts** | `/handoff` — structured state capture, not "check the git log" |

The one role we don't have deeply embedded in workflows: **designer.** Meatspace designers are still better at that, and their judgment is going to remain difficult for LLMs to replicate. There's a vibe-design functionality, but it's not gonna rock your world.

</details>

<details>
<summary><strong>Under the hood — architecture details</strong></summary>

**Inverted capability delegation.** The coordinator sees ~8 thin MCP tools; domain agents access 40+ via proxy with full schemas. This saves ~40K tokens from the coordinator's context and forces delegation by design. A `PreToolUse` hook nudges the coordinator when it reaches for domain tools directly.

**Proactive artifact generation.** Before compaction fires, a hook prompts structured handoff creation — a prospective document capturing decisions, state, and next steps. Each artifact chains from its predecessor (cascade obligation) and opens with a synthesis of the prior handoff (anti-amnesia chain). See our [handoff vs. compaction research](docs/research/2026-03-21-handoff-artifacts-vs-compaction.md).

**Persona-based sequential review.** Reviewers carry rich behavioral profiles — not just "code reviewer" but characters with expertise domains and review lenses. Sequential review with mandatory fix gates means each reviewer sees a clean artifact. See the [persona research](docs/research/2026-03-19-named-persona-performance.md) and [experiment results](docs/research/2026-03-26-persona-experiment-results.md). They have names for the human user's cognitive ease, while the rest of the persona prompt maps to human-world professional roles and agendas.

**6-layer project knowledge.** Structure, architecture, activity, temporal, intent, state — none bulk-loaded. A tiered context model loads a ~60-line orientation cache at L1, pulls detailed artifacts on demand at L2, and reserves L3 for deep storage read by subagents. An 11-phase maintenance pipeline fights doc staleness automatically.

**Agent Teams for planning.** Claude Code's [Agent Teams](https://docs.anthropic.com/en/docs/claude-code/agent-teams) enables multiple Claude sessions that communicate and coordinate. This system uses it for multi-perspective planning: persona-based debaters form independent positions, challenge each other, and a synthesizer cross-references into consensus. Also powers the [deep-research pipelines](https://github.com/dbc-oduffy/deep-research-claude).

**Cross-model delegation.** Haiku for mechanical checks, Sonnet for most execution, Opus for judgment and synthesis. Codex CLI runs as a parallel execution runtime via `codex:*` skills — a second-opinion channel and independent implementation path.

See [docs/architecture.md](docs/architecture.md) for the full model. For broader context, the [novelty research](docs/research/2026-03-20-agent-orchestration-novelty-unified.md) assesses all patterns against published prior art.

</details>

## Plugins

| Plugin | Purpose | When to Enable |
|--------|---------|----------------|
| **[coordinator](plugins/coordinator/)** | Core orchestration, reviewers, all workflow skills | Always |
| **[game-dev](plugins/game-dev/)** | Unreal Engine specialist (architecture, C++/Blueprint) | Unreal Engine projects |
| **[web-dev](plugins/web-dev/)** | Front-end architecture review + UX flow review | Web projects |
| **[data-science](plugins/data-science/)** | ML, statistics, data modeling review | ML/data work |

The coordinator plugin is always enabled. Domain plugins are toggled per-project via `.claude/coordinator.local.md`.

## Customization

- **Rename personas.** `bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"` renames display names across all plugin files.
- **Create your own domain reviewer.** The game-dev plugin is a reference implementation — same structure for any specialization.
- **Per-project configuration.** Create `.claude/coordinator.local.md` with `project_type` to control which reviewers activate.

See [docs/customization.md](docs/customization.md) for templates, the full persona registry, and instructions for adding skills and CI checks.

## Companion Plugins

- **[deep-research](https://github.com/dbc-oduffy/deep-research-claude)** — Multi-agent research pipelines (internet, repo analysis, structured research, NotebookLM). The coordinator auto-suggests these via a `PreToolUse` hook when Claude reaches for ad-hoc web search.
- **[clangd-lsp](https://github.com/anthropics/claude-code-plugins/tree/main/clangd-lsp)** — C++ code intelligence. Reviewer agents gain go-to-definition, find-references, and call hierarchy ‒ helpful for those (like us) using Claude Code with Unreal Engine.
- **[codex-plugin-cc](https://github.com/openai/codex-plugin-cc)** — Codex CLI integration for parallel execution and second-opinion reviews.
- **[Context7](https://github.com/upstash/context7)** — External library documentation lookup.

All are optional. Coordinator works without them; relevant features degrade gracefully.

<details>
<summary><strong>Directory structure</strong></summary>

```
coordinator-claude/
├── plugins/
│   ├── coordinator/            # Core orchestration (always enabled)
│   │   ├── .claude-plugin/plugin.json
│   │   ├── agents/             # enricher, executor, docs-checker, reviewers, eng-director
│   │   ├── commands/           # 22 workflow commands
│   │   ├── hooks/              # context pressure, orientation, commit validation
│   │   ├── pipelines/          # staff-session team protocol + prompt templates
│   │   └── skills/             # 25 skills (planning, review, debugging, TDD, etc.)
│   ├── game-dev/               # Unreal Engine specialist
│   ├── web-dev/                # Front-end + UX flow reviewers
│   ├── data-science/           # ML, statistics reviewer
│   └── remember/               # Temporal session memory
├── docs/                       # Architecture, customization, research
├── setup/                      # Installer
└── assets/                     # Social preview
```

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

**Plugins not loading:**
- Check `enabledPlugins` in `~/.claude/settings.json` — must be `true`
- Check `~/.claude/plugins/installed_plugins.json` — must have entry with correct `installPath`
- Restart Claude Code (changes take effect on next session)
- The installer (`setup/install.sh`) manages all config files automatically

**Plugin cache not syncing after editing source:**
- Claude Code caches plugins by version. Run `bash setup/dev-sync.sh` to sync.

**Per-project plugin selection:**
- Create `.claude/coordinator.local.md` with `project_type` field
- Coordinator is always enabled; domain plugins activate per-project

</details>

## Research

This system's design is informed by published research and validated through controlled experiments:

- [Handoff artifacts vs. compaction](docs/research/2026-03-21-handoff-artifacts-vs-compaction.md) — why structured baton-passing beats automatic summarization
- [Named persona performance](docs/research/2026-03-19-named-persona-performance.md) — evidence that named behavioral profiles improve review quality
- [Agent orchestration novelty assessment](docs/research/2026-03-20-agent-orchestration-novelty-unified.md) — honest assessment of all patterns against prior art
- [Anthropic multi-agent alignment](docs/research/2026-04-01-anthropic-multi-agent-alignment.md) — independent convergence with Anthropic's production research system

---

[Dónal O'Duffy](https://github.com/dbc-oduffy) & Claude
