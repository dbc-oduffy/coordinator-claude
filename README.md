# coordinator-claude

A plugin system that turns Claude Code into a structured engineering team — you're PM, Claude's EM.

- **8 plugins, 24 agents, 32 skills** — a coherent orchestration stack built on every Claude Code extension primitive (hooks, subagents, skills, commands, Agent Teams, MCP)
- **Agent Teams for research and planning** — tiered pipelines (Haiku scouts → Sonnet specialists → Opus synthesizer) that run autonomously; staff sessions where persona-based engineers debate and converge on plans without intervention
- **Prospective handoff artifacts** — structured baton-passing before compaction fires, not retrospective summarization after. [Research](docs/research/2026-03-21-handoff-artifacts-vs-compaction.md) shows this beats automatic summarization for chained agent work
- **Inverted capability delegation** — the coordinator sees ~8 thin tools; domain agents access 40+ via proxy. The orchestrator is intentionally *less capable* than its delegates, saving ~40K tokens for judgment instead of tool schemas
- **Sequential persona-based review** — domain expert first, all fixes applied, then generalist reviews a clean artifact. [Research supports](docs/research/2026-03-19-named-persona-performance.md) both the persona mechanism and multi-agent review gains
- **5-layer project knowledge** — structure, architecture, activity, intent, state — none bulk-loaded, all maintained by an 11-phase doc pipeline that fights staleness automatically

## Quick Start

```bash
git clone https://github.com/oduffy-delphi/coordinator-claude.git
cd coordinator-claude
bash setup/install.sh
```

Restart Claude Code, then run `/session-start`. See [docs/getting-started.md](docs/getting-started.md) for the full walkthrough.

## How It Works

You sit in the captain's chair:

| Role | Who | Responsibility |
|------|-----|---------------|
| **PM (Captain)** | You | Vision, priorities, judgment calls, design approval |
| **EM (First Officer)** | Claude (main session) | Orchestration, delegation, spec compliance, pipeline flow |
| **Executor** | Claude (subagent, Sonnet) | Faithful implementation of well-specified work |
| **Reviewers** | Claude (subagents, Opus) | Code quality, UX, domain expertise — each with a rich behavioral profile |

A typical feature flows through:

```
Brainstorm  →  Plan  →  Execute  →  Review  →  Ship
   (skill)    (skill     (executor    (domain       (finish
               or staff   agents)     → generalist   branch)
               session)               sequential)
```

See [docs/architecture.md](docs/architecture.md) for the full model — agent roles, pipeline checkpoints, review routing, and the design philosophy behind it.

<details>
<summary><strong>Agent Teams for research and planning</strong> — not just "build together"</summary>

Claude Code's [Agent Teams](https://code.claude.com/docs/en/agent-teams) (still experimental) enables multiple Claude sessions that communicate via messaging and coordinate via shared task lists. Most early adopters use it for collaborative coding. This system uses it differently: for **structured research** and **multi-perspective planning**. Three research pipelines (internet, repository, structured/schema-conforming) follow a tiered pattern — Haiku scouts gather sources cheaply, Sonnet specialists analyze and cross-pollinate findings via messaging, an Opus synthesizer produces the final document. **Staff sessions** use the same infrastructure for planning: persona-based debaters form independent positions, challenge each other, and a synthesizer cross-references into a consensus plan. The coordinator scopes the work, spawns the team, and is freed — the team runs autonomously.

</details>

<details>
<summary><strong>Prospective handoff artifacts</strong> — structured baton-passing that beats compaction</summary>

Long-running work in Claude Code faces a hard constraint: context compaction. When triggered, the model summarizes what it *believes* happened — a retrospective reconstruction that loses intent and forward direction. This system takes a different approach: before compaction can fire, a `UserPromptSubmit` hook monitors estimated context usage and prompts the agent to create a **structured handoff artifact** — a *prospective* document that captures decisions made, state reached, and explicit next steps. Each artifact carries forward unresolved items from its predecessor (cascade obligation) and opens with a synthesis of the prior handoff (anti-amnesia chain). See our [handoff vs. compaction research](docs/research/2026-03-21-handoff-artifacts-vs-compaction.md).

</details>

<details>
<summary><strong>Inverted capability delegation</strong> — the coordinator sees less, delegates see more</summary>

Most multi-agent systems give subagents *fewer* tools than the orchestrator. This system deliberately inverts that. The orchestrator sees only ~8 thin MCP tools; domain subagents access 40+ tools via a proxy with full schemas loaded in fresh context. This saves ~40K tokens of MCP schemas from the orchestrator's context window and forces delegation by design. A `PreToolUse` hook nudges the orchestrator to delegate when it reaches for domain tools directly. Microsoft recommends [least-privilege for agent design](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/baseline-openai-e2e-chat#security); this applies the same principle in the opposite direction.

</details>

<details>
<summary><strong>Persona-based sequential review</strong> — not just role labels</summary>

Reviewer agents carry rich behavioral profiles, and the system enforces sequential review with mandatory fix gates — domain expert first, all findings applied, then generalist reviews a clean artifact. Research supports both the [persona mechanism](docs/research/2026-03-19-named-persona-performance.md) and the [multi-agent review gains](https://link.springer.com/article/10.1007/s10462-024-11097-3). See the [full persona registry](docs/customization.md) for all six reviewers.

</details>

<details>
<summary><strong>5-layer project knowledge</strong> — layered context, not bulk injection</summary>

Instead of one large repo map injected at the start of every interaction, the system maintains five complementary knowledge layers (structure, architecture, activity, intent, state), none loaded in bulk. A tiered context model loads a ~60-line orientation cache at L1, pulls detailed artifacts on demand at L2, and reserves L3 for deep storage read by subagents. An 11-phase maintenance pipeline fights doc staleness automatically. See [docs/architecture.md](docs/architecture.md#project-knowledge-layered-context-not-bulk-injection) for the full breakdown.

</details>

For a deeper assessment of all patterns, see the [novelty research doc](docs/research/2026-03-20-agent-orchestration-novelty-unified.md). For an accessible video introduction to *why* hierarchical agent architectures matter, Martin Keen's [Hierarchical AI Agents](https://www.youtube.com/watch?v=wh489_XT5TI) covers context dilution, tool overload, and task decomposition — the core problems this system solves.

## Plugins

| Plugin | Purpose | When to Enable |
|--------|---------|----------------|
| **[coordinator](plugins/coordinator/)** | Core orchestration pipeline, reviewers, all workflow skills | Always |
| **[game-dev](plugins/game-dev/)** | Unreal Engine specialist (architecture, C++/Blueprint) | Unreal Engine projects |
| **[web-dev](plugins/web-dev/)** | Front-end architecture review + UX flow review | Web projects |
| **[data-science](plugins/data-science/)** | ML, statistics, data modeling review | ML/data work |
| **[deep-research](plugins/deep-research/)** | Multi-agent research pipelines (internet, repo, structured) | Research tasks |
| **[notebooklm](plugins/notebooklm/)** | NotebookLM integration — YouTube, podcast, audio research via MCP | Media research |

The coordinator plugin is always enabled. Domain plugins are toggled per-project via `.claude/coordinator.local.md`.

## Customization

- **Rename personas.** `bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"` renames display names across all plugin files.
- **Create your own domain reviewer.** The game-dev plugin is a reference implementation — same structure (agent file + routing fragment) for any specialization.
- **Per-project configuration.** Create `.claude/coordinator.local.md` with `project_type` to control which reviewers activate.

See [docs/customization.md](docs/customization.md) for templates, the full persona registry, and instructions for adding skills and CI checks.

## Recommended Companion Plugin

Install [superpowers](https://github.com/obra/superpowers) for the full development discipline layer. Coordinator builds on superpowers' skills for TDD, debugging, planning, verification, and git workflows — adding orchestration capabilities like review routing, staff sessions, and execution delegation.

Coordinator works without superpowers, but references to `superpowers:*` skills won't resolve.

## Directory Structure

```
coordinator-claude/
├── plugins/
│   ├── coordinator/            # Core orchestration (always enabled)
│   │   ├── .claude-plugin/plugin.json
│   │   ├── agents/             # enricher, executor, reviewers, review-integrator, eng-director
│   │   ├── commands/           # handoff, session-start, session-end, staff-session, etc.
│   │   ├── hooks/              # context pressure advisory, executor watchdog, delegation nudge
│   │   ├── pipelines/          # staff-session/ (team protocol + prompt templates)
│   │   └── skills/             # 18 coordinator skills (planning, code review, staff sessions, etc.)
│   ├── game-dev/               # Unreal Engine specialist
│   ├── web-dev/                # Front-end + UX flow reviewers
│   ├── data-science/           # ML, statistics reviewer
│   ├── deep-research/          # Agent Teams research pipelines (A: web, B: repo, C: structured)
│   └── notebooklm/             # NotebookLM media research via Agent Teams
├── docs/                       # Architecture, customization, CI pipeline
├── setup/                      # Installer
└── assets/                     # Social preview card + generation template
```

<details>
<summary><strong>Troubleshooting</strong></summary>

**Plugins not showing as skills/commands:**
- Check `enabledPlugins` in `~/.claude/settings.json` — must be `true`
- Check `~/.claude/plugins/installed_plugins.json` — must have entry with correct `installPath`
- Check `~/.claude/plugins/known_marketplaces.json` — must have marketplace entry
- Restart Claude Code (changes take effect on next session)
- The installer (`setup/install.sh`) manages all three files automatically

**Plugin cache not syncing after editing source:**
- Claude Code caches plugins by version. Run `bash setup/dev-sync.sh` to sync, or use junctions/symlinks — see [docs/getting-started.md](docs/getting-started.md).

**Per-project plugin selection:**
- Create `.claude/coordinator.local.md` with `project_type` field
- coordinator is always enabled; domain plugins activate per-project

**Plugin-scoped MCP server not starting (Windows):**
- Use `"command": "cmd", "args": ["/c", "your-command"]` in `.mcp.json`

</details>

---

[Dónal O'Duffy](https://github.com/oduffy-delphi) & Claude
