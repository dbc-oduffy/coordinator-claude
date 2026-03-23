# Structured Handoff Artifacts vs. Compaction for Agent Continuity

> **Migration note (2026-03-21):** This document references "TodoWrite" throughout. The flight recorder has since been migrated to the Tasks API (TaskCreate/TaskUpdate/TaskList/TaskGet). The analysis and conclusions remain valid — only the underlying tool changed.

**Date:** 2026-03-21
**Type:** Literature survey + practitioner evidence
**Trigger:** Evaluating whether our handoff artifact pattern is empirically supported vs. relying on compaction for cross-agent/cross-session continuity

---

## Research Question

Is there evidence that structured handoff artifacts (documents summarizing session state, decisions, and next steps) are a superior way to pass context between AI agents working sequentially on a task chain — specifically compared to automatic context compaction/compression?

## Executive Summary

The evidence strongly supports structured handoff artifacts over both raw history passing and automatic compaction. This conclusion converges from three independent directions: empirical benchmarks, production framework design choices, and practitioner experience. The most striking data point is Sourcegraph retiring compaction in their Amp agent system in favor of explicit handoffs after measuring degradation.

No serious counterargument exists in the current literature — the debate is about *how* to structure handoffs, not *whether* to structure them. The gap is the absence of a rigorous multi-agent handoff benchmark; that's a research opportunity, not a counterargument.

---

## Part 1: Structured Handoffs vs. Raw History

### The Core Problem: Why Raw History Fails

Multiple independent sources converge on the same failure mode:

- **xtrace.ai**: Either the full message history overwhelms the receiving agent with noise, or it gets summarized in ways that strip away evidence and reasoning. Neither approach preserves the structured relationships between decisions, artifacts, and facts that the receiving agent actually needs.
- **LangChain**: Context engineering "stops being prompt gymnastics and starts looking like systems engineering." The prescription is to separate durable state from per-call views, and to apply scope by default so every model call sees the *minimum* context required.
- **Microsoft Azure SRE Agent**: Identifies "context rot" — the gradual degradation of response quality as irrelevant history accumulates in the context window — as the primary failure mode in long-running agentic workflows.

### Empirical Evidence: ACON Benchmark (arXiv 2510.00615)

The most rigorous quantitative evidence comes from **ACON: Optimizing Context Compression for Long-horizon LLM Agents** (Kang et al., Oct 2025).

Key findings:
- On AppWorld: ACON reduces peak tokens by >25% while *preserving* accuracy at the no-compression upper bound. Naive baselines suffer severe degradation on medium and hard tasks.
- On OfficeBench: Peak context size drops ~30% with accuracy maintained above 74%.
- On 8-objective QA: ACON *surpasses* the no-compression baseline in EM/F1 while reducing peak tokens by 54.5% and context dependency by 61.5%.
- Structured compression enables smaller LMs to achieve 20-46% performance improvements as long-horizon agents.

Critical insight: **"The reasoning trace matters more than the raw data. The agent needs to remember what it decided, not necessarily the full output that informed the decision."**

### Framework Convergence

Every major production framework independently arrived at structured state transfer:

| Framework | Mechanism | Notes |
|-----------|-----------|-------|
| **OpenAI Agents SDK** | `input_filter` on handoffs + Pydantic-typed payloads | Explicit: no persistent state between calls, every handoff must include all needed context |
| **LangGraph** | Directed graph state with checkpointing | Explicitly discourages context-in-chat-text; state lives in typed objects |
| **CrewAI** | Structured task output artifacts | Each agent receives a curated brief, not a raw dump |
| **AutoGen** | Raw conversation history | The weakest approach — notably the one with the most context-scaling problems |

A practitioner comparison (mkbctrl, GitHub Gist) found that the "handoff" approach (transfer to specialized agent with curated context) consistently outperforms the "agent-as-tool" approach (sub-call with full parent context) for complex tasks, because specialization requires *isolation*, not inheritance.

### Lossy Compression: Curated Summary vs. Full History

Morph's analysis distinguishes two strategies:
- **Compaction**: Strips redundant information recoverable via tool calls (e.g., file contents) — safe
- **Summarization**: Uses an LLM to synthesize history — essential for decisions and reasoning that can't be reconstructed

**Not all context loss is equal.** Losing raw tool output is usually fine (re-fetchable). Losing *why a decision was made* is catastrophic for a downstream agent. Structured handoff documents preserve the latter by design.

Google ADK prescribes a hybrid: continuously shrink history into summaries and structured state (key facts, decisions, constraints), so the context window stays a small working set rather than an ever-growing log.

---

## Part 2: The Compaction Cascade Problem

### How Claude Code Compaction Works

Claude Code's auto-compact triggers at approximately 95% context capacity. The process is a 3-layer approach:
1. Layer 1: Trims tool outputs (oldest first)
2. Layer 2: Summarizes old messages into compressed summaries, preserving "key decisions and state"
3. Layer 3: CLAUDE.md is re-read from disk after every compact cycle

**What survives:** Recent messages, key code snippets, the gist of decisions. CLAUDE.md is reloaded from disk (the only officially compaction-proof mechanism).

**What doesn't:** Detailed instructions from early conversation, reasoning chains (Claude remembers "we chose approach B" but forgets *why* approach A failed), precise variable names, nuanced constraints, project-context.md contents.

### The Cascade Effect

Each compaction operates on already-compressed content. By the third cycle, you're working from "a summary of a summary of a summary." The specific casualties:
- Exact numbers and thresholds
- Reasoning chains and counterfactuals
- Carefully worded constraints
- The *why* behind decisions

This creates a degradation feedback loop: compacted context occupies an increasing fraction of the fresh agent's window, triggering earlier subsequent compactions, each of which further degrades signal quality.

### Industry Response: Sourcegraph Retires Compaction

**Sourcegraph's Amp agent system retired compaction in favor of explicit handoff.** They found that repeated compression made it harder for agents to maintain continuity across work phases. This is the strongest industry validation — a production agent system that tried compaction, measured the degradation, and switched to handoffs. (Covered by tessl.io.)

### Structural Critique

One source (Morph) raises a pointed observation: compaction-induced correction loops increase token consumption, and since Anthropic profits from token usage, there is a structural misalignment between the vendor's incentives and reliable long-session continuity. Speculative but present in community discourse.

---

## Part 3: TodoWrite as Continuity Mechanism

### Was TodoWrite Designed to Survive Compaction?

**No.** TodoWrite's compaction survival is a side effect of its JSON persistence pattern (writing to `~/.claude/todos/`), not an intentional continuity feature. No Anthropic engineer has publicly articulated a "survives compaction by design" rationale.

Anthropic subsequently built the Tasks API (Claude Code v2.1.16) with proper persistence, dependency tracking, and multi-session support — suggesting they recognized the gap and addressed it deliberately. The Tasks API is the "official" answer to the problem that TodoWrite accidentally partially solved.

### Community Practice

Several practitioners use TodoWrite and CLAUDE.md as continuity instruments:
- Writing "what was tried and why it failed" into CLAUDE.md to survive compaction
- Using TodoWrite's disk-persistence as a flight recorder
- Multi-session coordination via shared task stores

The consensus is that CLAUDE.md — not TodoWrite — is the reliable compaction-proof store. TodoWrite is complementary but not contractually guaranteed.

### Implication for Our Flight Recorder Pattern

Our mise-en-place flight recorder (which uses TodoWrite as a compaction-proof session state anchor) works but builds on implementation detail rather than contract. The pattern is sound in principle — encoding prospective state (what needs to happen next) in a compaction-surviving store — but the specific mechanism (TodoWrite disk persistence) is an accidental affordance rather than a designed API.

---

## Conceptual Framework

### Compaction vs. Handoff: Different Information Types

| Dimension | Compaction | Handoff Artifact |
|-----------|-----------|-----------------|
| **Orientation** | Backward-looking (what happened) | Forward-looking (what matters next) |
| **Optimization target** | Compression ratio | Downstream decision quality |
| **Degradation mode** | Cascade (summary of summary of summary) | None (each handoff is freshly curated) |
| **Context cost** | Grows with history | Fixed per handoff |
| **Decision preservation** | Incidental | Intentional |

The epistemological distinction: **compaction preserves beliefs about what happened; handoffs preserve intentions about what should happen next.** These are fundamentally different information types — historiography vs. planning. The cascade degrades because each summarization pass further detaches beliefs from original evidence. A handoff document doesn't have this problem because it was never trying to faithfully represent the past.

This maps to the distinction between *episodic memory* (what happened) and *prospective memory* (what I need to do). Compaction compresses episodic memory; handoffs encode prospective memory.

### The "Structured Briefing" Standard

The emerging consensus across sources (xtrace.ai, Factory.ai, Sourcegraph, LangChain) is that context should be treated as **structured state** (queryable, typed, purpose-built) rather than **compressed text** (lossy, backward-looking, undifferentiated). The handoff artifact pattern is the operationalization of this principle for sequential agent chains.

One important caveat from community discourse: "If the handoff is just 'summarize this session and paste into the next system prompt,' it isn't different — it's just autocompact with extra steps." True handoff requires structured, purpose-curated content where the *what matters next* is explicit, not implicit.

---

## Research Gaps

1. **No head-to-head multi-agent benchmark** comparing handoff document vs. raw history vs. naive summary vs. compaction as transfer mechanisms for sequential agent chains
2. **No systematic study of handoff field importance** — which fields (decisions vs. reasoning traces vs. artifacts vs. constraints) matter most to downstream agent quality
3. **No longitudinal measurement of compaction cascade degradation** — how many cycles before quality drops below a threshold, and does it vary by task type
4. **TodoWrite design intent is undocumented** — the reverse-engineering repos (Piebald-AI) are the closest to authoritative source material

---

## Sources

### Part 1: Handoffs vs. Raw History
- [AI Agent Handoff: Why Context Breaks & How Structured Memory Fixes It — xtrace.ai](https://xtrace.ai/blog/ai-agent-handoff-why-context-gets-lost-between-agents-and-how-to-fix-it)
- [AI Agent Handoff: Why Context Breaks & How to Fix It — xtrace.ai](https://xtrace.ai/blog/ai-agent-context-handoff)
- [ACON: Optimizing Context Compression for Long-horizon LLM Agents — arXiv 2510.00615](https://arxiv.org/abs/2510.00615)
- [Compaction vs Summarization: Agent Context Management Compared — Morph](https://www.morphllm.com/compaction-vs-summarization)
- [Context Engineering for Agents — LangChain Blog](https://blog.langchain.com/context-engineering-for-agents/)
- [Context Engineering Lessons from Building Azure SRE Agent — Microsoft Tech Community](https://techcommunity.microsoft.com/blog/appsonazureblog/context-engineering-lessons-from-building-azure-sre-agent/4481200/)
- [Handoffs — OpenAI Agents SDK](https://openai.github.io/openai-agents-python/handoffs/)
- [Orchestrating Agents: Routines and Handoffs — OpenAI Cookbook](https://cookbook.openai.com/examples/orchestrating_agents)
- [Evaluating Context Compression for AI Agents — Factory.ai](https://factory.ai/news/evaluating-compression)
- [Context Engineering for AI Agents: Part 2 — Phil Schmid](https://www.philschmid.de/context-engineering-part-2)
- [Choosing the Right Multi-Agent Architecture — LangChain Blog](https://blog.langchain.com/choosing-the-right-multi-agent-architecture/)
- [Architecting Efficient Context-Aware Multi-Agent Framework for Production — Google Developers Blog](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/)
- [Agent-as-Tools vs Handoff in Multi-Agent AI Systems — Medium (Xiaojian Yu)](https://medium.com/@yuxiaojian/agent-as-tools-vs-handoff-in-multi-agent-ai-systems-11f66a0342c4)
- [Handoff approaches in agent systems — GitHub Gist (mkbctrl)](https://gist.github.com/mkbctrl/555b84c8dd4a74720d2983ab4e75bbaa)
- [Context Compaction — Google ADK Docs](https://google.github.io/adk-docs/context/compaction/)

### Part 2: Compaction Cascade
- [Amp drops compaction for 'handoff' — tessl.io](https://tessl.io/blog/amp-retires-compaction-for-a-cleaner-handoff-in-the-coding-agent-context-race/)
- [Claude Code Auto-Compact: What It Loses — Morph](https://www.morphllm.com/claude-code-auto-compact)
- [Claude Code Compaction Keeps Destroying My Work — DEV Community](https://dev.to/gonewx/claude-code-compaction-keeps-destroying-my-work-heres-my-fix-9he)
- [Compaction — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [How Claude Code works — Claude Code Docs](https://code.claude.com/docs/en/how-claude-code-works)

### Part 3: TodoWrite and Continuity
- [claude-code-system-prompts — TodoWrite tool description (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-todowrite.md)
- [Claude Code Task Management: Native Multi-Session AI — claudefa.st](https://claudefa.st/blog/guide/development/task-management)
- [Claude Saves Tokens, Forgets Everything — Alexander Golev](https://golev.com/post/claude-saves-tokens-forgets-everything/)
- [Session Persistence in Claude Code — ruvnet/ruflo GitHub Wiki](https://github.com/ruvnet/ruflo/wiki/session-persistence)
- [Claude Code Todo Lists: Perfect Task Execution Guide — claudefa.st](https://claudefa.st/blog/guide/development/todo-workflows)

---

## Action Items

- [x] **Migrate from TodoWrite to Tasks API** — TodoWrite's compaction survival is an accidental affordance; the Tasks API (v2.1.16+) provides contractual persistence with dependency tracking and multi-session support. PM confirmed migration is in progress (2026-03-21). *(Achieved)*
- [ ] **Quantitative experiment: handoff artifacts vs. compaction-only continuity** — see Addendum below.

---

## Addendum: Planned Experiment — Handoff vs. Compaction Benchmark

**Goal:** Produce original quantitative evidence comparing structured handoff artifacts against compaction-reliant continuity for sequential agent work. This fills the primary research gap identified in the survey (no rigorous multi-agent handoff benchmark exists).

**Motivation:** The literature provides strong practitioner evidence and convergent framework design choices, but no controlled measurement of the degradation cascade. Our infrastructure (handoff skill, flight recorder, mise-en-place pipeline) gives us both a treatment condition and a baseline to compare against.

**Proposed design (preliminary):**
- **Condition A — Compaction-only:** Same task executed across N compaction events with no explicit handoff; continuity relies entirely on Claude Code's auto-compact mechanism.
- **Condition B — Structured handoff:** Same task, same breakpoints, but each segment receives a curated handoff artifact instead of compacted history.
- **Condition C (optional) — Hybrid:** Compaction + flight recorder (TodoWrite/Tasks API as compaction-proof anchor), representing our current operational pattern.
- **Measures:** Task completion quality (correctness, completeness), token cost, number of rework/correction loops, decision fidelity (does the agent remember *why* a choice was made, not just *that* it was made).
- **Control challenge:** Task variance — need repeatable tasks of sufficient complexity to trigger multiple compaction events. Candidate: multi-file refactors, multi-step enrichment pipelines, or similar structured work.

**Status:** Future goal for this repo. No timeline set. Tasks API migration is a prerequisite.
**Research context:** See survey above, particularly the ACON benchmark (arXiv 2510.00615), Sourcegraph/Amp's retirement of compaction, and the identified research gaps in § Research Gaps.
