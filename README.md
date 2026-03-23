# coordinator-claude — A Structured Workflow System for Claude Code

A plugin set that turns Claude Code into a small engineering team: a coordinator that delegates, persona-based specialists that review, and codified skills that encode best practices — with structured session handoffs that fight context loss. You play PM; Claude plays EM.

## What This Does

This combines all of Claude Code's extension primitives (hooks, subagents, skills, commands, Agent Teams, MCP servers) into one coherent workflow stack. The individual patterns — multi-agent orchestration, quality gates, model tiering — exist elsewhere in the ecosystem; what's unusual is the integration and what it's used for.

Five things are particularly distinctive, ordered by impact:

- **Agent Teams for research and planning, not just "build together."** Claude Code's [Agent Teams](https://code.claude.com/docs/en/agent-teams) (still experimental) enables multiple Claude sessions that communicate via messaging and coordinate via shared task lists. Most early adopters use it for collaborative coding — "you're a dev team, build this feature together." This system uses it differently: for **structured research** and **multi-perspective planning**. Three research pipelines (internet, repository, structured/schema-conforming) follow a tiered pattern — Haiku scouts gather sources cheaply, Sonnet specialists analyze and cross-pollinate findings via messaging, an Opus synthesizer produces the final document. **Staff sessions** use the same infrastructure for planning: persona-based debaters form independent positions, challenge each other, converge, and a synthesizer cross-references their positions into a consensus plan with noted dissent. In both cases, the coordinator scopes the work, spawns the team, and is freed — the team runs autonomously. This keeps research and planning work out of the coordinator's context window entirely, and we believe (though haven't yet proven) that specialist teams produce better research and plans than a single Claude session doing everything alone. We are [actively researching this question](docs/research/).

- **Layered project knowledge, not bulk injection.** Most AI coding tools solve codebase orientation with a repo map — a structural index injected at the start of every interaction. This system maintains five complementary knowledge layers (structure, architecture, activity, intent, state), none loaded in bulk. An 11-phase maintenance pipeline fights doc staleness automatically, and the resulting documentation doubles as "grep bait" — searchable surface area that makes even vague directives land hits across plans, archives, and trackers. See the [full breakdown below](#project-knowledge-layered-context-not-bulk-injection).

- **Prospective handoff artifacts for session continuity.** Long-running work in Claude Code faces a hard constraint: context compaction. When triggered, the model summarizes what it *believes* happened — a retrospective reconstruction that loses intent, momentum, and forward direction. This system takes a different approach: before compaction can fire, a `UserPromptSubmit` hook monitors estimated context usage and prompts the agent to create a structured **handoff artifact** — a *prospective* document that captures decisions made, state reached, and explicit next steps for the successor session. The handoff is a baton, not a police report. Each artifact carries forward unresolved items from its predecessor (cascade obligation) and opens with a synthesis of the prior handoff (anti-amnesia chain), making any single handoff a self-contained orientation point. A `PreCompact` hook provides a recovery bridge if the advisory is ignored. See our [handoff vs. compaction research](docs/research/2026-03-21-handoff-artifacts-vs-compaction.md) — the evidence from ACON benchmarks, Sourcegraph's production experience, and framework convergence (OpenAI, LangGraph, CrewAI) strongly favors structured handoffs over automatic summarization for chained agent work.

- **Inverted capability delegation.** Most multi-agent systems give subagents *fewer* tools than the orchestrator — scoped-down workers executing within the coordinator's capabilities. This system deliberately inverts that. The orchestrator sees only ~8 thin MCP tools; domain subagents access 40+ tools via a proxy with full schemas loaded in fresh context. The orchestrator is *intentionally less capable* than its delegates for domain work. This saves ~40K tokens of MCP schemas from the orchestrator's context window — tokens better spent on judgment than on tool definitions — and forces delegation by design, not just by convention. A `PreToolUse` hook nudges the orchestrator to delegate when it reaches for domain tools directly. Microsoft recommends [least-privilege for agent design](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/baseline-openai-e2e-chat#security); this system applies the same principle in the opposite direction — giving the *coordinator* the minimal toolset while delegates get the full capability surface. The holodeck-control plugin (an Unreal Engine editor MCP system, not included in this repo) is the reference implementation; the pattern is general and replicable with any large MCP toolset.

- **Persona-based sequential review.** Reviewer agents carry rich behavioral profiles (not just role labels like "code reviewer"), and the system enforces sequential review with mandatory fix gates — domain expert first, all findings applied, then generalist reviews a clean artifact. Research supports both the [persona mechanism](docs/research/2026-03-19-named-persona-performance.md) and the [multi-agent review gains](https://link.springer.com/article/10.1007/s10462-024-11097-3).

For a deeper assessment of all patterns, see the [novelty research doc](docs/research/2026-03-20-agent-orchestration-novelty-unified.md).

## The Organizational Metaphor

The system borrows from engineering management practice. You sit in the captain's chair:

| Role | Who | Responsibility |
|------|-----|---------------|
| **PM (Captain)** | You | Vision, priorities, judgment calls, design approval |
| **EM / Coordinator (First Officer)** | Claude (main session) | Orchestration, delegation, spec compliance, pipeline flow |
| **Executor** | Claude (subagent, Sonnet) | Faithful implementation of well-specified work |
| **Reviewers** | Claude (subagents, Opus) | Code quality, UX, domain expertise — each with a rich behavioral profile and adversarial framing |

This is the "First Officer Doctrine" — Claude operates as your EM (engineering manager), you operate as PM (product manager). The EM executes with ambition, counsels honestly when they disagree, and clarifies scope when it's ambiguous. Silent compliance into a bad outcome is a failure of the role. The boundary is explicit: the PM owns *what* to build and *whether* to ship; the EM owns *how* to build it and *whom* to delegate to.

## What Changes: From Manual Multiplexing to Structured Orchestration

Without a system like this, power users of AI coding tools tend to converge on the same pattern: multiple concurrent conversations, each doing a piece of the work, with the human acting as router, context carrier, and quality gate between them. Six Claude windows, alt-tabbing between planning in one, supervising execution in another, reviewing output in a third.

This system replaces that with structured orchestration. One coordinator session holds the full project context and dispatches typed agents with dependency chains — a staff session team debates and writes the plan autonomously, a code reviewer finds bugs independently, an enricher researches the codebase from a different angle. The cognitive load shifts from you to the task graph.

The practical difference: instead of managing six conversations and carrying context between them, you set direction in one conversation and the pipeline handles the rest. The staff session team is fully autonomous — persona-based engineers debate, write position docs, and converge on a plan without intervention. Meanwhile, independent review and enrichment agents run in parallel, often catching the same issues from different angles. You're still the PM making judgment calls — but the execution machinery no longer lives in your head.

## Plugins

| Plugin | Purpose | When to Enable |
|--------|---------|----------------|
| **[coordinator](plugins/coordinator/)** | Core orchestration pipeline, reviewers, all workflow skills | Always |
| **[game-dev](plugins/game-dev/)** | Unreal Engine specialist (architecture, C++/Blueprint) | Unreal Engine projects |
| **[web-dev](plugins/web-dev/)** | Front-end architecture review + UX flow review | Web projects |
| **[data-science](plugins/data-science/)** | ML, statistics, data modeling review | ML/data work |
| **[deep-research](plugins/deep-research/)** | Multi-agent research pipelines (internet, repo, structured) | Research tasks |
| **[notebooklm](plugins/notebooklm/)** | NotebookLM integration — YouTube, podcast, audio research via MCP | Media research (enable on demand) |

The coordinator plugin is always enabled. Domain plugins are toggled per-project via `.claude/coordinator.local.md`.

See [architecture.md](docs/architecture.md) for the full conceptual model — how agents interact, how the pipeline flows, and the design philosophy behind it.

## The Pipeline

A typical feature goes through these stages:

```
Brainstorm  →  Plan  →  Execute  →  Review  →  Ship
   (skill)    (skill     (executor    (domain       (finish
               or staff   agents)     → generalist   branch)
               session)               sequential)
```

The **Plan** stage has two paths:
- **EM writes plan** → single-reviewer dispatch (lightweight, existing flow)
- **Staff session** → parallel debate between persona-based staff engineers who craft the plan collaboratively via Agent Teams. The EM writes objectives; the team writes the blueprint.

Each stage is a codified skill or command. The coordinator orchestrates transitions between stages and verifies output at each checkpoint.

## Customization

The system is designed to be adapted, not just adopted:

- **Rename personas.** The reviewer names are labels; behavioral descriptions are the active ingredient. `bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"` renames display names across all plugin files.
- **Create your own domain reviewer.** The game-dev plugin is a reference implementation. Follow the same structure (agent file + routing fragment) to create a reviewer for any specialization — security, mobile, DevOps, etc.
- **Per-project configuration.** Create `.claude/coordinator.local.md` in your project root to set `project_type` (web, data-science, game) and control which reviewers activate.

See [docs/customization.md](docs/customization.md) for templates, the full persona registry, and instructions for adding skills and CI checks.

## Project Knowledge: Layered Context, Not Bulk Injection

Most AI coding tools solve the "large codebase" problem by building a repo map — a structural index of files, classes, and functions — and injecting it (or retrieving from it) at the start of every interaction. Aider pioneered this pattern; many tools have followed. It works, but it has a ceiling: a repo map tells you *what exists*, not *why it exists*, *what state it's in*, or *what to do next*.

This system takes a different approach. Instead of one large artifact, it maintains several complementary knowledge layers, each serving a different purpose:

| Layer | Artifact | What It Captures | How It's Maintained |
|-------|----------|-----------------|-------------------|
| **Structure** | `DIRECTORY.md` | File-by-file index with purpose annotations | Auto-generated, updated by `/update-docs` when source files change |
| **Architecture** | Architecture atlas (`tasks/architecture-atlas/`) | System boundaries, connectivity, health scores | Multi-agent audit pipeline; weekly rotation targets stalest system |
| **Activity** | Repo map (`.claude/repomap.md`) | Git-activity-ranked file list, fitted to token budget | Generated on demand; ranked by churn, not just existence |
| **Intent** | Project tracker, roadmaps, plan docs | What's being built, what's blocked, what shipped | PM-maintained with EM assistance; `/update-docs` syncs status |
| **State** | Health ledger, bug/debt backlogs | Known issues, sweep results, system health | Updated by sweeps and audits; surfaced at session start |

None of these are loaded in bulk. Instead, the system uses a **tiered context model**:

```
L1 (always in context)   CLAUDE.md + MEMORY.md + orientation cache (~60 lines)
L2 (on-demand)           DIRECTORY.md, atlas, repomap, tracker, backlogs
L3 (deep storage)        Codebase, git history — read by subagents, never bulk-loaded
```

The **orientation cache** is the key. Generated by `/workday-start`, it's a ~60-line ephemeral summary that distills L2 artifacts into a compact briefing: top-ranked files, directory structure at a glance, health snapshot, doc freshness, and pointers to every L2 artifact for drill-down. It's injected at session start via a `SessionStart` hook. The next session doesn't load the full repo map or the full atlas — it loads a summary that *knows they exist* and can pull them on demand.

**Fighting staleness.** The hard part of maintaining project documentation isn't generating it — it's keeping it current. `/update-docs` is an 11-phase maintenance pipeline that syncs all documentation artifacts against the codebase on every run: refreshing source indexes, archiving completed work, trimming lessons, checking the architecture atlas for unmapped files, and flagging drift. `/workday-start` surfaces staleness metrics at the top of each day — how many commits since the last doc sync, how many since the last bug sweep, which atlas systems are overdue for audit. The goal is that documentation is *trustworthy by default*, not aspirationally current.

**"Grep bait" as a design principle.** Copious, status-tagged documentation across wikis, plans, archives, and trackers creates a secondary benefit: even a vague PM directive like "finish up that blueprint graph handling" produces hits across multiple artifacts — each with dates, status, and context — making it easy for Claude to gather orientation without a guided tour. The documentation isn't just for reading; it's searchable surface area that makes the codebase self-describing.

## Version History

- [**v1.1.1**](https://github.com/oduffy-delphi/coordinator-claude/releases/tag/v1.1.1) — Staff sessions (Agent Teams for collaborative planning/review), README positioning rewrite
- [**v1.1.0**](https://github.com/oduffy-delphi/coordinator-claude/releases/tag/v1.1.0) — Agent Teams adoption for all research pipelines; deep-research extracted to standalone plugin; context pressure advisory hooks
- [**v1.0.0**](https://github.com/oduffy-delphi/coordinator-claude/releases/tag/v1.0.0) — Initial public release: 6 plugins, 24 agents, 38 skills, enrichment-review-execution pipeline

---

## Installation

### Prerequisites
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated
- [jq](https://jqlang.github.io/jq/) — used by hook scripts for JSON parsing (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`)

### Quick Start

```bash
git clone https://github.com/oduffy-delphi/coordinator-claude.git
cd coordinator-claude
bash setup/install.sh
```

The installer handles platform detection (macOS, Linux, Windows/Git Bash, WSL), interactive plugin selection, and all JSON registration. Use `--non-interactive` for unattended installs or `--plugins coordinator,game-dev` to specify an explicit list.

Restart Claude Code after installation. See [docs/getting-started.md](docs/getting-started.md) for the full walkthrough.

<details>
<summary>Manual Installation</summary>

If you prefer to install manually or the script doesn't work for your setup:

#### Step 1: Copy plugins

```bash
mkdir -p ~/.claude/plugins/coordinator-claude
cp -r plugins/* ~/.claude/plugins/coordinator-claude/
```

#### Step 2: Register the marketplace

Add to `~/.claude/plugins/known_marketplaces.json`:

```json
{
  "coordinator-claude": {
    "source": { "source": "directory", "path": "/home/{USERNAME}/.claude/plugins/coordinator-claude" },
    "installLocation": "/home/{USERNAME}/.claude/plugins/coordinator-claude"
  }
}
```

#### Step 3: Register plugins in installed_plugins.json

Add entries to `~/.claude/plugins/installed_plugins.json` — see [docs/getting-started.md](docs/getting-started.md) for the full JSON template with all plugin entries.

#### Step 4: Enable plugins in settings.json

```jsonc
// In ~/.claude/settings.json, add to "enabledPlugins":
"coordinator@coordinator-claude": true,
"deep-research@coordinator-claude": true,
"web-dev@coordinator-claude": true,       // or false
"data-science@coordinator-claude": true,   // or false
"game-dev@coordinator-claude": false,      // enable for Unreal Engine
"notebooklm@coordinator-claude": false     // enable on demand
```

#### Step 5: Restart Claude Code

Start a new session. Verify with `/reload-plugins`.

#### Plugin cache (development workflow)

If editing plugin source files directly, use junctions/symlinks so the cache reflects your edits instantly:

```bash
# macOS/Linux
ln -sf ~/.claude/plugins/coordinator-claude/{plugin} ~/.claude/plugins/cache/coordinator-claude/{plugin}/{version}

# Windows (Git Bash or cmd)
mklink /J plugins\cache\coordinator-claude\{plugin}\{version} plugins\coordinator-claude\{plugin}
```

</details>

## First Session

After installing, start a Claude Code session in any project directory:

1. Run `/session-start` — orients the session, loads context, surfaces pending work.
2. For a brand new project, run `/project-onboarding` to bootstrap tracking infrastructure (project tracker, tasks directory, archive).
3. Give Claude a task. The PM/EM dynamic activates naturally — Claude will plan, delegate, and review as the work requires.

See [docs/getting-started.md](docs/getting-started.md) for a full walkthrough of your first session.

## Directory Structure

```
coordinator-claude/
├── plugins/
│   ├── coordinator/            # Core orchestration (always enabled)
│   │   ├── .claude-plugin/plugin.json
│   │   ├── agents/             # enricher, executor, reviewers, review-integrator, eng-director
│   │   ├── commands/           # handoff, session-start, session-end, staff-session, etc.
│   │   ├── hooks/              # context pressure advisory, executor watchdog, delegation nudge, capability catalog
│   │   ├── pipelines/          # staff-session/ (team protocol + prompt templates)
│   │   └── skills/             # 38 workflow skills (brainstorming, TDD, debugging, etc.)
│   ├── game-dev/               # Unreal Engine specialist
│   ├── web-dev/                # Front-end + UX flow reviewers
│   ├── data-science/           # ML, statistics reviewer
│   ├── deep-research/          # Agent Teams research pipelines (A: web, B: repo, C: structured)
│   └── notebooklm/             # NotebookLM media research via Agent Teams
├── docs/                       # Architecture, customization, CI pipeline
├── setup/                      # Installer
└── assets/                     # Social preview card + generation template
```

## Troubleshooting

**Plugins not showing as skills/commands:**
- Check `enabledPlugins` in `~/.claude/settings.json` — must be `true`
- Check `~/.claude/plugins/installed_plugins.json` — must have entry with correct `installPath`
- Check `~/.claude/plugins/known_marketplaces.json` — must have marketplace entry
- Restart Claude Code (changes take effect on next session)
- The installer (`setup/install.sh`) manages all three files automatically

**Plugin cache not syncing after editing source:**
- Claude Code caches plugins by version. Run `bash setup/dev-sync.sh` to sync, or see the Manual Installation section above for junction/symlink setup.

**Per-project plugin selection:**
- Create `.claude/coordinator.local.md` with `project_type` field
- coordinator is always enabled; domain plugins activate per-project

**Plugin-scoped MCP server not starting (Windows):**
- Use `"command": "cmd", "args": ["/c", "your-command"]` in `.mcp.json` — bare command names may not resolve through the plugin loader's PATH

## Authors

[Dónal O'Duffy](https://github.com/oduffy-delphi) & Claude
