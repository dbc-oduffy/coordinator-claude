# Deep Research Prompt Improvements — OSS Repo Analysis and Implementation

> **Date:** 2026-03-21 | **Pipeline:** A (Repo Research) — manual variant | **Repos studied:** [dzhng/deep-research](https://github.com/dzhng/deep-research) (TS), [open_deep_research](https://github.com/langchain-ai/open_deep_research) (Python/LangGraph) | **Validated against:** 5 priority improvements identified through training-knowledge synthesis on LLM deep research methods

## Executive Summary

Studied two leading open-source deep research implementations to validate five proposed improvements to our deep-research pipeline prompts. All five priorities were confirmed — neither repo implements adversarial search, explicit cross-pollination, or structured claim tables. Open_deep_research's multi-stage citation pipeline is the most mature pattern found; we adopted its compression-stage concept while going further with lead-with-citation format. Two bonus patterns were adopted: dzhng's `researchGoal` intent carrier and open_deep_research's think-tool forced reflection.

All changes implemented as additive edits to `plugins/coordinator/pipelines/deep-research/agent-prompts.md` and `plugins/coordinator/pipelines/deep-research/PIPELINE.md`. No existing template text was modified or deleted.

## Repos Studied

### dzhng/deep-research (877 lines, TypeScript)
- **Architecture:** Recursive depth-first search tree. `deepResearch()` generates SERP queries → fires Firecrawl searches → extracts learnings → recurses with halved breadth.
- **Key pattern:** `generateObject()` with Zod schemas at every LLM call — structured JSON output throughout. No free-form text extraction anywhere.
- **Convergence:** Pure numeric (depth decrement + breadth halving). No semantic convergence gate.
- **State:** Flat `learnings: string[]` accumulated across recursion, deduped via Set. No topic graph, no source metadata.

### open_deep_research (7090 lines, Python/LangGraph)
- **Architecture:** Three-tier supervisor stack. Supervisor dispatches `ConductResearch` → spawns isolated researcher subgraphs → compressed findings flow back → final report synthesis.
- **Key pattern:** Two-stage research output — raw notes → lossless compression (preserving all citations) → final report. The compression step is the citation quality gate.
- **Convergence:** Hard limits in both prompts AND code. Think-tool forces reflection after each search.
- **State:** Isolated sub-agent contexts — researchers receive only their topic, no cross-contamination.

## Findings by Priority

### Priority 1: Adversarial Search — CONFIRMED, IMPLEMENTED

**Neither repo implements this.** dzhng has a passive "contrarian ideas" instruction in its system prompt. Open_deep_research says "balanced, thorough analysis" as a writing instruction only. Neither generates queries targeting criticism, limitations, or opposing views.

**What we implemented:** Mandatory adversarial search requirement in Phase 1 Haiku templates (both Pipeline B and Pipeline C). At least one search must target criticism/limitations. Phase 2 Sonnet must flag absence of criticism as a coverage gap.

**Why this matters:** Premature convergence and echo chambers are the two highest-severity failure modes in agentic research. Adversarial search is the lowest-cost, highest-impact mitigation.

### Priority 2: Cross-Pollination — CONFIRMED, IMPLEMENTED

**dzhng:** Partial — accumulated learnings flow forward within a branch, but parallel branches at the same depth are independent.
**open_deep_research:** Not present by design — sub-agents are explicitly isolated ("sub-agents can't see other agents' work").

**What we implemented:** Phase 1.5b cross-pollination process in PIPELINE.md. After Phase 1 quality gate, coordinator reads all Phase 1 outputs and identifies cross-topic findings, shared search terms, and cross-topic contradictions. These are injected into Phase 2 dispatch prompts as "Cross-Pollination Context."

**Why this matters:** The pipeline already has Phase 1.5 as a coordinator checkpoint. Extending it to also cross-pollinate costs near-zero (coordinator already reads all Phase 1 outputs) while adding multi-hop capability that neither OSS repo achieves.

### Priority 3: Citation-First Synthesis — REFINED, IMPLEMENTED

**dzhng:** URLs appended as flat bibliography. Source provenance completely lost at the learning extraction step — by synthesis time, there's no mapping between learnings and source URLs.
**open_deep_research:** Strongest area. Multi-stage citation pipeline: per-search formatting → lossless compression with mandatory inline citations → final report with Title+URL inline citation format. Citations are appended/inline, not lead-with.

**What we implemented:** Two-part approach: (1) adopted open_deep_research's "preserve all citations through transformations" philosophy as a reinforcement to our Phase 2 template, (2) added lead-with-source format: "According to [Source], [claim]" rather than "[Claim] ([Source])". Neither repo leads with citations — this is a step beyond the state of the art in these implementations.

### Priority 4: Recency Enforcement — CONFIRMED, IMPLEMENTED

**Both repos:** Inject `Today's date is {date}` into every prompt. Neither filters by date, extracts publication dates, or rejects stale sources. dzhng's Firecrawl calls include no date range parameters. Open_deep_research's Tavily searches always use `topic="general"`.

**What we implemented:** Freshness rules in Phase 2 Sonnet template — sources older than 12 months require currency assessment; fast-moving topics use 6-month threshold; all-stale-sources findings require explicit flagging. Date field added to Phase 1 source format.

### Priority 5: Structured Claim Tables — CONFIRMED, IMPLEMENTED

**dzhng:** Zod schemas everywhere, but learnings are flat `string[]` with no metadata (no confidence, source URL, claim type, or date).
**open_deep_research:** No structured intermediate between research and synthesis. Compressed output is prose with inline citations.

**What we implemented:** Optional structured claims table in Phase 2 output for complex topics (5+ sources or contradictions present). Columns: Claim, Source, Date, Confidence, Corroborated By, Type (fact/limitation/opinion). Described in PIPELINE.md as a quality improvement for topics where source quality varies.

## Bonus Patterns Adopted

### Research Goal Intent Carrier (from dzhng)

dzhng's SERP query schema includes a `researchGoal` field: "First talk about the goal of the research... then go deeper into how to advance the research once the results are found." This goal text — not the raw query — bridges recursion levels.

**Applied as:** "Research intent per search" block in Phase 1 output format. Each search gets a Goal (why) and Outcome (what we actually found). Makes Phase 1.5 quality assessment easier.

### Forced Reflection (from open_deep_research)

open_deep_research's `think_tool` creates deliberate pauses in the ReAct loop. Both supervisor and researcher must call it after every search/delegation. Critical instruction: "Do not call think_tool with any other tools in parallel."

**Applied as:** Item 5 in Phase 2 task instructions: "After reading each recommended source, pause and assess: What changed about your understanding? Did this source confirm, contradict, or add nuance to prior sources?"

## What the Pipeline Already Does Well

Both repos validated several aspects of the existing pipeline:

1. **Three-tier model separation** — Both repos use multiple model tiers. Our Haiku-discovers, Sonnet-verifies, Opus-synthesizes is well-aligned with best practices.
2. **Anti-hallucination guards** — Our UNVERIFIED labels, contradiction handling, and "Haiku filters, Sonnet verifies" separation are more explicit than either repo.
3. **Topic-scoped agents** — One-agent-per-topic prevents scope creep. dzhng uses one recursive tree; open_deep_research uses supervisor-dispatched but with less explicit scoping.
4. **Sequential phase execution** — Phase 1→2→3 naturally implements reader/writer separation that reduces hallucination.

## Open Gaps: What Neither Repo (Nor We) Solve Well

1. **Semantic convergence** — All three systems use numeric limits, not semantic assessment of "have we learned enough?" Open_deep_research's think-tool comes closest but doesn't gate on novelty.
2. **Source quality scoring** — None of the three systems score sources by authority, recency, or type in a structured way. Our freshness enforcement is a step toward this.
3. **Contradiction resolution** — dzhng silently accumulates conflicting learnings. Open_deep_research's compression step deduplicates but doesn't explicitly resolve. Our "flag contradictions" instruction is better but still relies on agent judgment.

## Methodology

1. Cloned both repos and read all source files (prompt templates, orchestration logic, state management)
2. Extracted verbatim prompt text from each repo
3. Mapped each repo's capabilities against our 5 priority improvements
4. Identified additional patterns worth adopting
5. Implemented all changes as additive edits — no existing template text modified or deleted
6. Cross-referenced findings against a prior training-knowledge synthesis on LLM deep research methods
