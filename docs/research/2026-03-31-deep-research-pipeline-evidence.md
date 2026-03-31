# Deep Research Pipeline — Evidence Base

> Design decisions in the deep research pipelines are backed by published research, controlled experiments, and iterative testing. This document traces each major design choice to its evidence source.
>
> **Last updated:** 2026-03-31

---

## Why This Matters

Most multi-agent orchestration systems are designed from intuition. The deep research pipelines in this project are designed from evidence — published guidance from OpenAI, Perplexity, Google, Anthropic, and academic research (STORM, Baz), validated through controlled pipeline runs. This doesn't make them perfect, but it means every non-obvious design choice has a traceable rationale.

---

## Pipeline A (Internet Research) — v2.1

### Consolidator removal

**Decision:** Drop the Sonnet consolidator from the pipeline. Specialists send structured output directly to the Opus sweep.

**Evidence:**
- **Empirical observation (2026-03-31):** In a full Pipeline A v2.0 test run, the consolidator finished 4+ minutes after the Opus sweep had already completed independently. The sweep produced a complete document from the scout corpus and its own research without needing the consolidator's merged output.
- **Architecture analysis:** The consolidator performed mechanical deduplication — work that Opus can do as part of its judgment pass. Dedicating 1 of 7 team slots to mechanical merging wastes capacity that could be a 5th specialist.
- **Agent Teams constraint:** `blockedBy` is a status gate, not an event trigger. The blocking chain (specialists → consolidator → sweep) created a timing vulnerability where the sweep could run before the consolidator finished if unblock timing was ambiguous.

### Adversarial specialist interaction

**Decision:** Specialists are expected to challenge each other's claims, not just share findings. Unresolved challenges produce `[CONTESTED]` claims.

**Evidence:**
- **STORM framework (Stanford):** Perspective-guided question asking — cognitive diversity through assigned viewpoints produces higher-quality synthesis than homogeneous research.
- **Anthropic's multi-agent research system (2025):** Adversarial reviewer patterns improve output quality by catching assumptions that go unchallenged in cooperative-only setups.
- **Pipeline A v2.1 test run (2026-03-31):** 4 specialists produced 59 claims, actively challenged each other post-convergence, marked contested items, and flagged unverified claims for the sweep. The adversarial protocol surfaced contradictions (e.g., Plus tier source limit: 100 vs. 300) that cooperative sharing would have averaged into a vague "varies by plan."

### Structured claims output

**Decision:** Specialists produce dual output — `{letter}-claims.json` (structured) + `{letter}-summary.md` (readable).

**Evidence:**
- **Perplexity's citation-first architecture:** Structured intermediate representations preserve detail through multi-stage pipelines better than prose summaries.
- **Coverage gap analysis (2026-03-28):** Solo Opus outperformed Agent Teams v1 on coverage, with the gap widening for difficult claims (surface: 0pp, moderate: 7-18pp, deep: 20-33pp). Root cause: synthesis compression in prose-only intermediate outputs. Structured claims with confidence ratings and source URLs resist this compression.
- **Uncertainty propagation (published guidance, multiple sources):** Hallucinations at the specialist level get synthesized as established fact downstream. Explicit confidence fields in the claims JSON make uncertainty visible to the sweep agent.

### Sweep phased discipline

**Decision:** The Opus sweep runs three explicit sequential phases: Assess → Fill → Frame.

**Evidence:**
- **Patrik review (2026-03-31):** Staff engineer review flagged sweep overload risk — three responsibilities (adversarial check, gap research, framing) could blur if not sequenced. Phase separation ensures the gap report exists as an artifact before gap-filling research begins.
- **Negative-space framing (OpenAI, Google, Anthropic guidance):** The sweep should look for "what's missing," not "summarize what's there." Phase 1 (Assess) produces a written gap report that makes the negative space explicit before Phase 2 (Fill) does targeted research.

### EM scoping checklist

**Decision:** The EM reviews a quality checklist before dispatching the team.

**Evidence:**
- **Sub-question decomposition (OpenAI, STORM, Anthropic):** The most consistently recommended practice across all published guidance. Generate sub-questions explicitly before dispatching, not during.
- **Effort budgets (Anthropic agent framework):** Specifying expected depth per topic helps specialists calibrate research effort.
- **Adversarial queries (Perplexity, Google):** Including criticism/limitation queries is necessary because absence of criticism in sources ≠ absence of real limitations.
- **Falsifiability test (multiple sources):** Each sub-question should have a concrete answer that evidence can confirm or deny — "what is the best X?" without criteria is not falsifiable.

---

## Pipeline B (Repo Research)

### Structural orientation pass

**Decision:** The EM answers four structural questions about the repo before defining specialist chunks.

**Evidence:**
- **Baz five-phase model:** Context Mapping → Intent Inference → Socratic Questioning → Targeted Investigation → Reflection & Consolidation. The orientation pass implements Context Mapping — understanding the structural skeleton before defining what to investigate.
- **aider's repo map approach:** Building structural understanding (entry points, key directories, dependency graph) before analysis improves specialist targeting and reduces hallucination.
- **LLM context file discovery (arXiv 2511.12884, Agent READMEs):** Repositories increasingly include files designed to orient LLM agents (CONTEXT.md, CLAUDE.md, .cursorrules). Surfacing these to specialists provides high-signal context that the repo author specifically prepared.

### Execution-trace framing

**Decision:** Focus questions use execution-trace framing ("trace the request from entry to exit") instead of structural description ("describe the architecture of X").

**Evidence:**
- **Practitioner consensus (Claude Code best practices, Cursor docs, Baz):** Execution-trace questions produce more accurate results than structural questions because they force the agent to follow actual code paths rather than inferring structure from file organization.
- **Hallucination mitigation:** Structural descriptions invite plausible-sounding but fabricated claims about how modules relate. Execution traces require the agent to cite specific function calls and data flows, making unsupported claims immediately visible.

### file:line citation requirement

**Decision:** Specialists must cite `file:line` for every claim. Uncited claims are flagged as the "primary hallucination vector."

**Evidence:**
- **arXiv 2404.00971 (Beyond Functional Correctness):** LLMs hallucinate API paths, wrong module names, and fabricated function signatures at measurable rates in code generation tasks. The same failure modes apply to code analysis.
- **arXiv 2512.12117 (Citation-Grounded Code Comprehension):** Requiring citation grounding significantly reduces hallucinated code references.
- **Baz's agentic code review (2025):** Their production system requires every finding to cite specific file locations — findings without citations are treated as unverified.

### Independent-analysis-first comparison

**Decision:** In comparison mode, analyze each codebase independently against the same questions, then compare answers — not compare code directly.

**Evidence:**
- **Anchoring bias mitigation:** Direct comparison creates anchoring — the first codebase read becomes the reference frame, biasing assessment of the second. Independent analysis with a shared rubric controls for this.
- **Baz Socratic Questioning phase:** Generate risk hypotheses ("does Codebase B maintain schema consistency that Codebase A enforces?"), then dispatch sub-agents to prove/disprove each hypothesis independently. This maps to our specialist focus questions.

---

## Research Sources

The full research documents behind these decisions:

| Document | Focus |
|----------|-------|
| `docs/research/2026-03-31-deep-research-prompting-guide.md`* | Web research prompting best practices (15 sources: OpenAI, Perplexity, Google, STORM, Anthropic) |
| `docs/research/2026-03-31-repo-analysis-prompting-guide.md`* | Repo/codebase analysis prompting (28 sources: Claude Code, Cursor, aider, Baz, academic papers) |
| `docs/research/2026-03-31-notebooklm-best-practices.md`* | Pipeline A v2.1 validation run output (35+ sources, 59 specialist claims) |

*These documents live in the experiments repo (`X:/experiments/docs/research/`) and are referenced here for provenance. The evidence they contain is distilled into this document and into the pipeline prompts themselves.

### External references

- OpenAI: [Introducing Deep Research](https://openai.com/index/introducing-deep-research/) (Feb 2025)
- OpenAI Forum: [Three Tips for Better AI-Assisted Inquiry](https://forum.openai.com/public/blogs/exploring-deep-research-three-tips-for-better-ai-assisted-inquiry-2025-04-28) (Apr 2025)
- Perplexity: [Official Prompt Guide](https://docs.perplexity.ai/guides/prompt-guide) (2025)
- Google: [6 Tips for Gemini Deep Research](https://blog.google/products/gemini/tips-how-to-use-deep-research/) (Mar 2025)
- Anthropic: [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) (2025)
- Anthropic: [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) (2025)
- Stanford STORM: [github.com/stanford-oval/storm](https://github.com/stanford-oval/storm) (2024)
- Baz: [Architecture of Agentic Code Review](https://baz.co/resources/engineering-intuition-at-scale-the-architecture-of-agentic-code-review) (2025)
- aider: [Repository Map Documentation](https://aider.chat/docs/repomap.html) (2025)
- arXiv 2404.00971: Beyond Functional Correctness — Hallucinations in LLM-Generated Code (2024)
- arXiv 2512.12117: Citation-Grounded Code Comprehension (2025)
- arXiv 2511.12884: Agent READMEs — Context Files for Agentic Coding (2025)
