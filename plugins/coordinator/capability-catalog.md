<!-- Maintenance: update when plugins change. Version: 1.3.2 | Last reviewed: 2026-03-25 -->

# Specialists — Route, Don't Execute

## Why Delegation Is Superior, Not Just Correct

The EM sees 8 thin MCP tools; domain agents access 61 hidden tools via the `execute_domain_tool` proxy with full schemas loaded in fresh context. This isn't organizational hierarchy — it's a capability gap. Delegates have:
- **Tool access:** Hidden tools with typed parameters and validation the EM would need to ToolSearch for
- **Loaded knowledge:** Pre-baked domain patterns, verification protocols, and operational skills in their system prompts
- **Context efficiency:** Fresh Sonnet context dedicated to one task vs. Opus context juggling orchestration state

This design saves ~40K tokens of MCP schemas from the EM's context window — tokens better spent on orchestration judgment than tool definitions.

Before using a tool yourself, ask: would a specialist produce better results? The answer is almost always yes for multi-step work.

When a reviewer returns findings, **accept their expertise** — implement ALL items, including P2s, nitpicks, and suggestions to defer. Every finding is an opportunity to meet or exceed their quality bar. The only exceptions: escalate to the PM when findings change scope, or push back if you believe the reviewer is genuinely wrong (state why explicitly).

**Patrik** — architecture + code review. Use /review-dispatch.
**Enricher/Executor** — codebase research + implementation. Use /enrich-and-review, /delegate-execution.

**Camelia** — ML, statistics, RAG eval, training. Route: any AI/data pipeline work.

**Sid** — UE architecture + C++/BP design (has RAG access + production knowledge base). Route: "should I use X?" design questions. Superior to you on UE idiom judgment.
**Blueprint Inspector** — automated BP documentation extraction. Route: "document all BPs."

**UE Editor** — 4 domain agents + 1 planner, with typed tools you cannot access directly:
- **ue-project-orchestrator** (Opus, read-only) — for underspecified, cross-domain, or large-scope tasks. Inspects current editor state, decomposes into precise per-agent specs, returns a structured execution plan. **Cannot dispatch agents or mutate state** — you execute its plan by dispatching domain agents yourself.
- **ue-world-builder** (Sonnet) — lighting, terrain, landscape, nav, PCG, instancing, collision, volumes, splines
- **ue-asset-author** (Sonnet) — **BP graph ops (Python CANNOT do this)**, materials, textures, widgets, sequences, movie render, media, data assets/tables
- **ue-gameplay-engineer** (Sonnet) — actors, combat, AI, GAS, inventory, VFX, input, checkpoints, quests, demo replay
- **ue-infra-engineer** (Sonnet) — perf, tests, networking, audio, game framework, scalability, accessibility, modding, build
- Blueprint graph operations (nodes, pins, functions) are impossible via Python — only ue-asset-author can do them.
- **Single-domain tasks:** dispatch the domain agent directly. **Multi-domain tasks:** dispatch ue-project-orchestrator for a plan, then dispatch domain agents sequentially per its specs, verifying between steps. **Underspecified tasks:** always use the orchestrator — don't guess at decomposition.
- Use /dispatch or the ue-editor-control skill. execute_python_code is the escape hatch for simple one-liners, not the default.

**ue-docs-researcher** — multi-source RAG synthesis (333K+ vectors). Route: multi-step UE lookups. Single lookups: quick_ue_lookup directly.

**NotebookLM** — break-glass for YouTube/podcasts/audio Claude can't access. Use /notebooklm-research. NOT for normal web research.

**Palí** (senior-front-end) — front-end review (tokens, design system, CSS). **Fru** — UX flow review (trust, clarity). Use /review-dispatch.

**eng-director** (Zolí) — staff session synthesizer. Spawned by /staff-session. Reads all debater positions, resolves contested findings with an ambition-calibrated lens, and writes the final plan or review synthesis. Never dispatched directly.

**Agent Teams** — collaborative multi-agent work with messaging and shared task coordination:
- `/staff-session --mode plan` — domain experts debate (Patrik, Sid, Camelia, etc.), Zolí (eng-director) synthesizes with ambition lens. Use `coordinator:requesting-staff-session` to choose tier and composition.
- `/staff-session --mode review` — same debate structure for critiquing existing artifacts. Zolí synthesizes findings. Lightweight tier falls through to `/review-dispatch`.
- `/deep-research web` — Pipeline A: internet research (scout → specialists → synthesizer)
- `/deep-research repo` — Pipeline B: repository analysis (scouts → specialists → synthesizer)
- `/structured-research` — Pipeline C: schema-conforming batch research
- `/notebooklm-research` — Pipeline D: media research via NotebookLM MCP

When to use teams vs. subagents: teams when agents need to **communicate** (cross-pollinate, resolve contradictions, share discoveries); subagents when tasks are **independent** (no cross-agent value). Teams are fire-and-forget — the EM scopes, spawns, and is freed.

**Pipeline orchestrators** (dispatch via commands, not directly):
- **deep-research-orchestrator** — /deep-research dispatches this (lives in the deep-research plugin). Reads PIPELINE.md, runs Haiku→Sonnet→Opus.
- **bug-sweep-orchestrator** — /bug-sweep dispatches this. Scans→analyzes→triages→fixes.
- **architecture-audit-orchestrator** — /architecture-audit dispatches this. Inventories→analyzes→synthesizes atlas.
