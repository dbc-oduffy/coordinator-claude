# Anthropic's Multi-Agent Research System — Independent Validation

**Date:** 2026-04-01
**Source:** [Anthropic Engineering Blog — Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
**Context:** Discovered after our architecture was already built. We did not reference this during design — the convergence is independent.

## Summary

Anthropic's engineering team built a multi-agent research system for Claude.com that uses an orchestrator-worker pattern with Opus lead agents and Sonnet subagents. Their production system revealed the same architectural principles we arrived at independently in coordinator-claude. Their eval showed multi-agent Opus+Sonnet outperformed single-agent Opus by 90.2% on research tasks (relative improvement on an internal research eval).

## Where We Converged

| Principle | Anthropic's System | coordinator-claude |
|---|---|---|
| **Tiered model allocation** | Opus lead + Sonnet workers | Opus coordinator + Sonnet executors/specialists + Haiku scouts |
| **Orchestrator-worker separation** | Lead agent delegates, doesn't do the research itself | EM orchestrates, doesn't write code or read web pages directly |
| **Parallel subagent dispatch** | Lead spawns 3-5 subagents simultaneously | Agent Teams with concurrent specialists; wave-based parallel execution |
| **Effort scaling** | Explicit rules: 1 agent for simple, 10+ for complex | Tiered pipelines (lightweight single-reviewer to full staff session) |
| **Start wide, then narrow** | Broad queries first, progressive focusing | Iterative deepening in Pipeline A v2.2 — first team researches, gap analysis triggers optional second team |
| **Source attribution** | Dedicated CitationAgent processes findings | Structured claims extraction with source grading in Pipelines A and C |
| **Tool design matters** | "Agent-tool interfaces are as critical as human-computer interfaces" | Inverted capability delegation — thin coordinator tools, rich agent tools |
| **Prompt engineering via simulation** | Console simulations to observe step-by-step behavior | Controlled pipeline experiments validating prompt template changes |

## Where We Differ

### 1. Coordinator context preservation (our advantage)

Anthropic's lead agent waits synchronously for subagent completion, consuming its context window while workers run. Our system uses Agent Teams with task-based blocking — the EM dispatches a team and is freed. The team runs autonomously; results are written to disk. The EM's context window is preserved for judgment, not spent waiting.

**Why this matters:** Their article describes this explicitly — "Synchronous execution creates bottlenecks" — and flags asynchronous execution as future work that would "enable additional parallelism." We already operate asynchronously.

### 2. Cost efficiency via Haiku scouts (our advantage)

Anthropic uses Opus + Sonnet (two tiers). We add a third tier: Haiku scouts handle mechanical discovery work (source gathering, file inventory, query execution) before Sonnet specialists do the analytical work. This means the Sonnet specialists start from a pre-built corpus rather than doing their own source discovery — reducing both token cost and time.

**Their cost data:** Multi-agent uses ~15x more tokens than chat interactions (single-agent uses ~4x), so the multi-agent multiplier over single-agent is roughly 3.75x — not 15x. Our Haiku scout phase handles ~40% of the total work at ~1/20th the per-token cost of Sonnet, significantly reducing the multiplier further.

### 3. Prospective vs. checkpoint recovery

Anthropic handles stateful errors by resuming from checkpoints after failure. We use prospective handoff artifacts — structured state capture *before* compaction fires, not retrospective recovery after. Our research ([handoff vs. compaction](2026-03-21-handoff-artifacts-vs-compaction.md)) shows this preserves intent and forward direction better than reconstruction.

### 4. Adversarial peer dynamics (our addition)

Anthropic's subagents work independently and report back to the lead. Our Sonnet specialists in Pipelines A and C communicate laterally via messaging — challenging each other's claims, sharing cross-topic evidence (OVERLAP/SCHEMA_OVERLAP messages), and resolving contradictions before the synthesizer sees the findings. This is adversarial peer review, not just parallel execution.

### 5. Persona-based review (our addition)

Anthropic's system doesn't mention named personas or behavioral profiles for agents. Our reviewers (Patrik, Sid, Camelia, etc.) carry rich behavioral descriptions that shape their review lens. Research supports both the [persona mechanism](2026-03-19-named-persona-performance.md) and the multi-agent review gains.

### 6. Write-ahead status protocol (our addition)

Anthropic describes debugging non-deterministic multi-agent behavior as a major challenge. We address this with write-ahead status markers — every pipeline phase marks documents before starting work, creating unambiguous crash state. Their "rainbow deployments" solve a different problem (production traffic management) that doesn't apply to our CLI-based system.

## Their Findings That Validate Our Decisions

1. **"Token usage by itself explains 80% of the variance"** (in the BrowseComp evaluation specifically) — validates our decision to use Haiku for mechanical work and preserve Opus context for judgment.
2. **"Without effective mitigations, minor system failures can be catastrophic for agents"** — validates our write-ahead protocol and prospective handoff design.
3. **90.2% improvement** over single-agent — validates the multi-agent architecture generally, and our research pipeline design specifically.
4. **"Agent-tool interfaces are as critical as human-computer interfaces"** — validates our inverted capability delegation (thin coordinator tools, rich agent tools).
5. **Scale effort to complexity** — validates our tiered pipeline approach (not everything needs the full staff session).

## What We Could Learn From Them

1. **LLM-as-judge evaluation** — They use a single prompt scoring factual accuracy, citation accuracy, completeness, source quality, and tool efficiency (0.0-1.0). We could adopt a similar eval for our pipeline outputs.
2. **SEO content farm detection** — They found agents preferring SEO-optimized content over authoritative sources. Worth checking if our scouts have the same bias.
3. **Self-improvement loop** — They describe two flavors: (a) Claude diagnosing prompt failures and suggesting improvements to the orchestration prompts; and (b) a tool-testing agent that repeatedly uses flawed tools, then rewrites the tool descriptions based on observed failures — yielding a 40% decrease in task completion time. Our lessons.md system captures (a) manually; automating either flavor, especially (b), could be valuable.

## What We Adopted (2026-04-01)

Based on this analysis, we implemented the following improvements across Pipelines A, B, and D:

1. **SEO farm detection in scouts** — Mechanical flag for SEO content farm indicators (generic domains, clickbait titles, missing attribution), with specialists treating flagged sources as corroboration-only
2. **Broad-to-narrow search strategy** — Scouts now start with short broad queries before narrowing, avoiding the overly-specific-query failure mode Anthropic identified
3. **Parallel tool calling** — Specialists instructed to batch WebFetch/Read calls in parallel (3-5 per batch); NotebookLM workers can parallelize notebook_query (but not source_add)
4. **Extended thinking as scratchpad** — Specialists use thinking for structured post-source reflection; synthesizer uses thinking for cross-reference planning before writing
5. **Delegation clarity checklist** — EM scoping now requires specific objectives, boundaries, and output format per specialist/worker
6. **LLM-as-judge eval** — New `/eval-output` skill scores pipeline outputs on 5 criteria (factual accuracy, citation accuracy, completeness, source quality, source diversity) adapted from Anthropic's methodology

Items deferred:
- **Tool-testing agent** — Systematic testing of MCP tool descriptions. Valuable but large scope; tracked for future work.
- **End-state evaluation for executors** — Evaluating final state rather than process. Relevant to coordinator executors, not research pipelines.
- **Pipeline C (structured)** — Excluded from this round; its verifier agents have a different interaction model where these heuristics don't apply directly.
