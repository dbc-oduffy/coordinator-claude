# How Novel Is This? — Agent Orchestration Patterns Research

> **Date:** 2026-03-20
> **Method:** Deep Research Pipeline B (Internet Research) — Haiku discovery → Sonnet verification → Opus synthesis
> **Scope:** 9 architectural patterns assessed against AI agent frameworks, coding tools, academic literature, and industry practice
> **Sources verified:** 55+ (main run) + warm RAM research pending
> **Purpose:** Inform open-source release positioning — assess patterns against established prior art and position the system's contributions accurately

---

## The System Under Assessment

A Claude Code plugin system (coordinator-claude) with 6 plugins, 23 agents, 18 commands, 22 skills, and 8 pipeline definitions. Built as a PM/EM collaborative development environment where the human (PM) sets direction and the AI (EM) orchestrates a team of specialist agents.

The key architectural patterns assessed:

1. **Cognitive tiering** — Haiku verifies, Sonnet executes, Opus judges (different cognitive work per tier, not same work at different capability)
2. **Sequential multi-persona review with fix gates** — domain expert reviews, ALL fixes applied, then generalist reviews clean artifacts
3. **PM/EM authority partitioning (First Officer Doctrine)** — standing, domain-scoped authority boundaries that persist across sessions
4. **Selective tool withholding** — MCP tools deliberately withheld from the orchestrator, forcing delegation
5. **Named reviewer personas (Character Personas)** — Patrik, Sid, Camelia, Fru, Pali, Zoli — not role labels but named characters with expertise profiles
6. **Plugin-based capability composition** — modular packages injecting agents, skills, commands, hooks with per-project scoping
7. **Tiered context injection (warm RAM)** — ephemeral orientation cache with L1/L2/L3 context hierarchy
8. **Dispatch-not-absorb** — commands as dispatch stubs, pipeline intelligence lives in branded orchestrator agents
9. **Session boot context injection** — health snapshots, capability catalogs loaded via SessionStart hooks

---

## Positioning Verdict

This system should be positioned as an opinionated integration of existing patterns, not as proof of several first-of-their-kind orchestration inventions. The repo combines official Claude Code primitives, including hooks, subagents, and agent teams, with a strong workflow layer for delegation, review, and session continuity. That is a real contribution, but it is mostly a contribution in process design, prompt design, and packaging.

Where the system appears strongest is in its operational coherence: the same repo ties together plugin packaging, workflow commands, specialized agents, and team-based research patterns. Anthropic's official plugin structure and Claude Code feature set support that framing directly.

Where the prior memo overreached was in moving from "I did not find a public example" to "there is no documented prior art." That jump is too strong. Multi-agent specialization, staged review, human-AI role partitioning, and team coordination all have substantial precedent in public frameworks and literature. AutoGen documents role-specialized group-chat and coordination patterns, and the National Academies discuss role differentiation, function allocation, and non-equal authority in human-AI teams.

### Pattern Assessments

#### 1. Cognitive Tiering
**Classification:** Established pattern, customized implementation.

Different workers can already have different roles, contexts, and tool access; this repo's contribution is the specific Anthropic model-to-role mapping and surrounding workflow discipline.

**What it is:** Assigning fundamentally different cognitive *work types* to different model tiers — Haiku grounds/verifies (template checks, compile checks), Sonnet executes (code writing, analysis), Opus judges (synthesis, planning, triage).

**Prior art context:** The field has extensive work on model cascading (FrugalGPT 2023, ICLR 2025 unified routing, 2026 survey). The 2026 survey (arxiv 2603.04445) identifies multi-stage agent-loop cascading as an area for further research. Our system operates in this space with a specific model-to-role mapping.

**Evidence strength:** HIGH — verified against 9 academic papers and 3 infrastructure implementations.

#### 2. Sequential Multi-Persona Review with Mandatory Fix Gates
**Classification:** Established pattern, uncommon workflow choice.

The repo's review order may be more structured than mainstream product defaults, but staged review and iterative critique loops are already part of the broader agent-systems landscape.

**What it is:** Domain expert reviews first (e.g., Sid for game code), ALL findings applied to the artifact, then generalist reviews (Patrik) the clean version. Each reviewer sees corrected work, not drafts with known issues stapled on.

**Prior art context:** Most surveyed tools use parallel+aggregate (Anthropic's own March 2026 code review, CodeRabbit, Qodo) or single-pass (GitHub Copilot). ChatDev's "communicative dehallucination" uses intra-phase negotiation. GitHub's own Copilot code review now describes an agentic review architecture.

**Evidence strength:** HIGH — verified across all major code review tools and frameworks.

#### 3. PM/EM Authority Partitioning (First Officer Doctrine)
**Classification:** Operational framing.

The PM/EM metaphor is useful, but the underlying idea of differentiated human-AI roles and function allocation is already well established in human-AI teaming literature.

**What it is:** Standing role-level domain authority boundaries between human and AI that persist across sessions. The PM (human) holds product authority — what to build, priorities, scope. The EM (AI) holds engineering authority — how to build, delegation, implementation choices.

**Prior art context:** The National Academies discuss role differentiation, function allocation, and non-equal authority in human-AI teams. MetaGPT and ChatDev use role-based org simulations. The human-AI teaming literature treats role allocation and differentiated authority as core issues.

**Nearest analogs:**
- PMC's Human-Machine Teaming model — requires persistence and shared mental models
- arXiv "Reversing the Paradigm" (2025) — proposes AI-first with human guidance
- Azure Group Chat human participant — advisory participation

**Evidence strength:** HIGH — verified against academic HAT/HMT literature, all major frameworks, and the National Academies.

---

### Established Patterns, Customized Implementations

#### 4. Selective Tool Withholding
**What it is:** MCP tools exist but are deliberately NOT given to the top-level orchestrator. WebSearch removed from Opus orchestrators — only available to Haiku/Sonnet workers. Forces delegation rather than self-execution.

**Prior art:** Manager-worker hierarchies are well-established. Microsoft recommends "principle of least privilege" for agent design (Azure Architecture Center, Feb 2026). AutoGen's SelectorGroupChat is tool-free by architecture (structural necessity, not design principle). No framework enforces tool withholding as a deliberate design principle.

**Our addition:** Explicit cost-tier rationale + deliberate capability allocation as a design principle, not just a structural artifact.

**Evidence strength:** HIGH.

#### 5. Character Personas in Engineering Review
**Classification:** Prompt-design choice. Persona-based specialization is established; the specific reviewer cast and prompt styles are local implementation choices.

**What it is:** Named characters with backstory and expertise profiles (Patrik the exacting senior engineer, Camelia the data scientist), not functional role labels (Engineer, QA). The academic taxonomy (2404.18231) classifies these as "Character Personas" (tier 2).

**PM note:** The *naming* of personas is primarily for the human's cognitive convenience — easier to say "dispatch Patrik" than "dispatch the code-quality-review-agent." The *persona depth* (specific expertise profile, review style, domain knowledge) is what produces better review output. Prior research confirmed Character Personas lead to better results.

**Prior art:** MetaGPT and ChatDev use functional roles (tier 1). DennisKennedy's Operational Protocol Method uses named character personas as single-user personal advisors. paperreview.ai uses "epistemic reviewer personas" for academic paper review. Persona-based specialization is well-established across the field.

**Evidence strength:** HIGH.

#### 6. Plugin-Based Capability Composition
**What it is:** Modular packages that bundle agents + skills + commands + hooks + MCP config into deployable units, with per-project capability scoping via `coordinator.local.md`.

**Prior art:** Individual primitives (MCP, hooks, skills, commands) are Claude Code platform features. The opinionated composition and per-project scoping appear undocumented in public sources.

**Evidence strength:** HIGH.

---

### Potentially Distinctive Integrations

#### 7. Tiered Context Injection (Warm RAM)

**Classification:** Potentially distinctive integration. This is the best candidate for saying "our exact packaging appears unusual," but it should still be framed as a custom context-management pattern built from Claude Code hooks and session artifacts, not as a proven invention.

**What it is:** An ephemeral daily cache that provides session orientation without bulk-loading or cold-starting:
- **L1 (always loaded, ~200 lines):** CLAUDE.md + MEMORY.md + orientation cache — what matters and where to look
- **L2 (on-demand):** Full artifacts on disk (DIRECTORY.md, health ledger, repomap, atlas) — loaded when a task needs them
- **L3 (deep storage):** Codebase, git history, pipeline docs — read by subagents, never bulk-loaded into coordinator

The orientation cache is generated by `update-docs` and loaded at session start via a `SessionStart` hook. It contains repo structure summary, health grades, recent work, and self-invalidating metadata (`generated_at`, `git_head_at_generation`). Every L1 entry points to an L2 artifact — enough to route correctly without burning context on raw data.

**Prior art status:** Potentially distinctive integration — 87 sources surveyed, 15 deep-read. Each constituent idea exists (tiered memory, session summaries, pointer indirection, cache invalidation). The five-property combination (proactive generation, non-destructive pointers, self-invalidating via VCS metadata, explicit L1-to-L2 pointer contract, ephemeral lifecycle) appears uncommon but should be framed as a custom context-management pattern, not a proven invention. Closest parallels: Anthropic's context engineering blog (principle without implementation), Pichay "Missing Memory Hierarchy" (L1-L4 naming but reactive/destructive), MemGPT/Letta (structural analog but persistent/mutable). Claude Code community independently requesting this capability (issues #11455, #18417). See Appendix for full findings.

#### 8. Dispatch-Not-Absorb
**What it is:** Commands are thin dispatch stubs (~30 lines) that fire branded orchestrator agents. Pipeline intelligence lives in the agent definitions and pipeline docs on disk, not in the command content. The EM never sees phase-by-phase instructions — it dispatches and monitors.

**Prior art:** This is an application of control plane / data plane separation to agent orchestration. The principle is well-established in systems design; the specific application to LLM agent command architecture appears undocumented.

**Note:** This pattern was identified and implemented *during this research session* after the EM absorbed a 336-line pipeline document and started manually driving phases instead of delegating. The fix was structural: extract pipeline orchestrators as branded agents, reduce commands to dispatch stubs.

#### 9. Session Boot Context Injection
**What it is:** Health snapshots, capability catalogs, and orientation caches loaded at session start via `SessionStart` hooks.

**Prior art:** Hook-based initialization is a known pattern. The specific content (health grades, capability catalogs, orientation summaries) is implementation-level.

**Evidence strength:** MEDIUM.

---

## Pattern Classification Matrix

| # | Pattern | Classification | Notes | Evidence |
|---|---------|---------------|-------|----------|
| 1 | Cognitive tiering | **Established pattern, customized implementation** | Different workers can already have different roles, contexts, and tool access; contribution is the specific Anthropic model-to-role mapping and workflow discipline | HIGH |
| 2 | Sequential review with fix gates | **Established pattern, uncommon workflow choice** | More structured than mainstream defaults, but staged review and iterative critique loops exist in broader agent-systems landscape | HIGH |
| 3 | PM/EM authority partitioning | **Operational framing** | PM/EM metaphor is useful; differentiated human-AI roles and function allocation already well established in human-AI teaming literature | HIGH |
| 4 | Selective tool withholding | **Established pattern, customized implementation** | Microsoft recommends least-privilege for agent design; contribution is deliberate capability allocation as a design principle | HIGH |
| 5 | Character Personas in review | **Prompt-design choice** | Persona-based specialization is established; specific reviewer cast and prompt styles are local implementation choices | HIGH |
| 6 | Plugin capability composition | **Established pattern, customized implementation** | Primitives are platform features; opinionated bundling and per-project scoping is our contribution | HIGH |
| 7 | Tiered context injection (warm RAM) | **Potentially distinctive integration** | Best candidate for "our exact packaging appears unusual," but should be framed as custom context-management built from Claude Code hooks and session artifacts | HIGH |
| 8 | Dispatch-not-absorb | **Operational framing** | Control/data plane separation applied to agent commands; principle well-established in systems design | MEDIUM |
| 9 | Session boot injection | **Established pattern, customized implementation** | Hook-based init is known; specific content is implementation-level | MEDIUM |

---

## Positioning Recommendations

This project should be presented as a sophisticated Claude Code workflow system built from current platform primitives and established multi-agent patterns, rather than as proof of several wholly new orchestration inventions. Claude Code already supports hooks, subagents, agent teams, and plugin packaging; the repo's contribution is to combine those capabilities into a disciplined model for delegation, staged review, session continuity, and research coordination. The strongest claims here are about operational design and integration quality, not about the absence of prior art.

### Emphasize (operational design, high confidence)
1. **Cognitive tiering** — name it explicitly, position as a customized implementation of established multi-agent specialization patterns with a specific Anthropic model-to-role mapping
2. **Sequential fix-gate review** — describe as an uncommon workflow choice; contrast with the parallel+aggregate default, explain the compounding insight rationale
3. **First Officer Doctrine** — position as an operational framing of ideas already established in Human-Machine Teaming literature

### Credit the Integration
4. **Deliberate capability allocation** (tool withholding) — cite Microsoft's least-privilege as institutional backing
5. **Character Personas in engineering review** — prompt-design choices with measurable review quality impact
6. **Plugin architecture** — honest about platform primitives; claim the opinionated composition and per-project scoping

### Be Honest About
7. **"Orchestrator never writes code"** is prompt-enforced, not architecturally guaranteed. Document as a design convention. Technical audiences will respect the honesty.
8. **Manager-worker hierarchies** are well-established. Don't overclaim the architecture; claim the process design.

---

## Open Questions

- Cursor Auto mode routing criteria — permanently opaque
- Devin 2.0 internal architecture — not publicly documented
- Whether named persona review exists in private enterprise configurations
- Empirical comparison: sequential fix-gate review vs. parallel+aggregate effectiveness
- CascadeFlow's agent-loop embedding as potential infrastructure improvement
- LangGraph supervisor tool access specifics — primary source redirected

---

## Source Bibliography

### Primary Sources (Official Documentation)
- [OpenAI Agents SDK — Multi-agent](https://openai.github.io/openai-agents-python/multi_agent/)
- [OpenAI Agents SDK — Running Agents](https://openai.github.io/openai-agents-python/running_agents/)
- [AutoGen AgentChat — Selector Group Chat](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html)
- [Microsoft Azure AI Agent Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) (Feb 2026)
- [Agency Swarm — GitHub](https://github.com/VRSEN/agency-swarm)
- [MCP Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [GitHub Copilot Code Review Changelog](https://github.blog/changelog/2026-03-05-copilot-code-review-now-runs-on-an-agentic-architecture/) (March 2026)
- [Cognition Devin 2.0 Blog](https://cognition.ai/blog/devin-2)

### Academic Papers
- [FrugalGPT (2023)](https://arxiv.org/abs/2305.05176) — LLM cascade formalization
- [Unified Routing and Cascading (ICLR 2025)](https://arxiv.org/abs/2410.10347)
- [Faster Cascades via Speculative Decoding (ICLR 2025)](https://arxiv.org/abs/2405.19261)
- [Dynamic Model Routing and Cascading Survey (2026)](https://arxiv.org/html/2603.04445) — identifies our domain as research gap
- [Select-then-Route (EMNLP 2025)](https://aclanthology.org/2025.emnlp-industry.28/)
- [From Persona to Personalization (2024)](https://arxiv.org/html/2404.18231v2) — three-tier persona taxonomy
- [Multi-Agent Collaboration Mechanisms Survey (2025)](https://arxiv.org/html/2501.06322v1)
- [ChatDev (2023)](https://arxiv.org/abs/2307.07924)
- [OpenHands Software Agent SDK (2025)](https://arxiv.org/html/2511.03690v1)
- [Building AI Coding Agents for the Terminal (2026)](https://arxiv.org/html/2603.05344v1)
- [Reversing the Paradigm: AI-First Systems (2025)](https://arxiv.org/html/2506.12245v1)
- [Human Control of AI Systems: Supervision to Teaming](https://pmc.ncbi.nlm.nih.gov/articles/PMC12058881/)
- [National Academies: Human-AI Teaming](https://nap.nationalacademies.org/read/26355/chapter/4)

### Industry Analysis
- [Arize: Orchestrator-Worker Comparison](https://arize.com/blog/orchestrator-worker-agents-a-practical-comparison-of-common-agent-frameworks/)
- [ByteByteGo: How Cursor Shipped Its Agent](https://blog.bytebytego.com/p/how-cursor-shipped-its-coding-agent)
- [IBM MCP ContextForge — GitHub](https://github.com/IBM/mcp-context-forge)
- [CascadeFlow — GitHub](https://github.com/lemony-ai/cascadeflow)
- [OpenRouter Auto Router](https://openrouter.ai/docs/guides/routing/routers/auto-router)
- [DennisKennedy: Operational Protocol Method](https://www.denniskennedy.com/blog/2025/08/the-operational-protocol-method-systematic-llm-specialization-through-collaborative-persona-engineering-and-agent-coordination/)
- [MorphLLM: Claude Code Skills vs MCP vs Plugins](https://www.morphllm.com/claude-code-skills-mcp-plugins)
- [awesome-claude-code — GitHub](https://github.com/hesreallyhim/awesome-claude-code)

### Secondary Sources
- [Vercel Agent Skills Framework — DeepWiki](https://deepwiki.com/vercel-labs/agent-skills/3.1-framework-architecture)
- [Cursor Forum: Auto Mode Discussion](https://forum.cursor.com/t/what-does-the-auto-model-switcher-actually-do/128635)
- [DEV Community: Cursor Auto Mode Test](https://dev.to/nedcodes/i-tested-whether-cursors-auto-mode-actually-picks-the-right-model-20ml)
- [MetaGPT — IBM](https://www.ibm.com/think/topics/metagpt)
- [ChatDev — IBM](https://www.ibm.com/think/topics/chatdev)
- [paperreview.ai Tech Overview](https://paperreview.ai/tech-overview)

---

## Appendix: Warm RAM / Tiered Context Injection Research

> **Additional research run:** 6 agents (3 Haiku + 3 Sonnet), 87 sources surveyed, 15 deep-read

### Verdict: Potentially Distinctive Integration

Each constituent idea exists independently — tiered memory (MemGPT 2023, H-MEM 2025), session summaries (OpenAI, Factory.ai), pointer indirection (H-MEM positional indices), cache invalidation (standard practice). The specific five-property combination appears uncommon across the 87 surveyed sources, but this should be framed as a custom context-management pattern built from Claude Code hooks and session artifacts, not as a proven invention:

1. **Proactive generation at rest** — every surveyed summary system is triggered by context overflow. Our cache is generated by the update-docs pipeline *between sessions*, when no context pressure exists. Inverts the trigger from "context is full, compress" to "session is starting, orient."

2. **Non-destructive pointers to intact artifacts** — Pichay's summaries replace content (lossy). OpenAI's SummarizingSession replaces history. Our L1 entries are pointers to L2 artifacts that remain on disk intact. No information is lost.

3. **Self-invalidating via version-control metadata** — `generated_at` + `git_head_at_generation` make staleness visible at first glance. No surveyed paper or tool uses VCS metadata as a cache invalidation signal for LLM context. Entirely undocumented.

4. **Explicit L1-to-L2 pointer contract** — every L1 entry names the L2 artifact it summarizes. Bidirectional traceability not formalized in any surveyed system (though H-MEM's positional indices are structurally similar for a different purpose).

5. **Ephemeral lifecycle by design** — regenerated each session, never edited in place, never accumulated, never drifted. MemGPT/Letta blocks persist and drift as the agent edits them. Ours is guaranteed fresh by construction.

### Closest Parallels

| Source | Similarity | Difference |
|--------|-----------|------------|
| Anthropic "Context Engineering" blog | Describes L1/L2/L3 principle, cites Claude Code | Describes reactive discovery, not proactive injection |
| Pichay "Missing Memory Hierarchy" (2026) | L1-L4 naming for application-level context | Reactive demand-paging, destructive summarization |
| MemGPT/Letta memory blocks | In-context pinned blocks (closest structural analog) | Persistent + agent-mutable; ours is ephemeral + pipeline-generated |
| Aider repo map | Compact orientation artifact per request | Stateless (regenerated per request), no system state, no pointers |
| H-MEM upper layers | Pointer hierarchy (position indices to deeper layers) | Applied to long-term persistent memory, not ephemeral orientation |
| Factory.ai incremental merge | Validates token-efficiency philosophy | Within-session compaction, not cross-session orientation |

### Landscape Comparison

| Tool | Session-start orientation? | Tiered context? | Self-invalidating? | Summary-to-artifact pointers? |
|------|---------------------------|-----------------|-------------------|-------------------------------|
| Aider | No — per-request repo map | No — flat | No | No |
| Cursor | No — auto-includes open files | No documented tiers | No | No |
| Claude Code (native) | No — cold start (requested in issues #11455, #18417) | No | No | No |
| Continuous-Claude-v3 | No — DB-backed regeneration | Partial (YAML + DB + FAISS) | No | Partial (file_claims) |
| Factory.ai | No — rolling persistent summary | No — single summary | No | No |
| **Our system** | **Yes** | **Yes** (L1 + L2 + L3) | **Yes** (git HEAD metadata) | **Yes** (every L1 entry -> L2) |

### Community Signal

Claude Code issues #11455 and #18417 describe exactly what our system already implements — hook-based SessionStart/SessionEnd patterns, handoff conventions, archive rotation. The community is independently requesting this capability. No Anthropic response exists on either issue.

### Recommended Positioning

Frame as a **custom context-management pattern** — a practical configuration of known techniques optimized for cross-session orientation of AI coding agents, built from Claude Code hooks and session artifacts. The contribution is in the integration and packaging, not in the individual components.

The pattern can be named **"proactive orientation cache"** for convenience — but the framing should emphasize operational design, not invention.

### Additional Sources (Warm RAM Research)

**Academic:**
- [MemGPT (2023)](https://arxiv.org/abs/2310.08560) — OS-inspired Core/Recall/Archival tiers
- [Pichay: Missing Memory Hierarchy (2026)](https://arxiv.org/html/2603.09023) — L1-L4 context hierarchy, demand paging
- [H-MEM (2025)](https://arxiv.org/abs/2507.22925) — 4-layer hierarchy with positional indices
- [A-MEM (2025)](https://arxiv.org/abs/2502.12110) — Zettelkasten graph memory
- [Pancake (2026)](https://arxiv.org/html/2602.21477v1) — Hierarchical vector memory

**Official docs:**
- [Anthropic: Context Engineering for AI Agents](https://anthropic.com/engineering/effective-context-engineering-for-ai-agents) — three-tier loading
- [Letta memory blocks](https://docs.letta.com/core-concepts/) — attached/detached distinction
- [OpenAI Agents SDK Session Memory](https://developers.openai.com/cookbook/examples/agents_sdk/session_memory)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)

**Tools & community:**
- [Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) — YAML handoffs + PostgreSQL + FAISS
- [Claude Code Issue #11455](https://github.com/anthropics/claude-code/issues/11455) — session handoff request
- [Claude Code Issue #18417](https://github.com/anthropics/claude-code/issues/18417) — session continuity request
- [Factory.ai: Compressing Context](https://factory.ai/news/compressing-context) — incremental merge benchmarks
