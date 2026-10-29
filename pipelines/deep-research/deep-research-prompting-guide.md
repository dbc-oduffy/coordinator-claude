# Deep-Research Prompting Guide

> Read by the `brief-author` stage after the pipeline's own guide. Rules for writing a brief that a vendor deep-research product or a multi-agent research run can execute. Source: `docs/research/2026-10-28-what-does-openai-officially-publish-on-how-to/digest.md` (research run pipeline-research-20261028T004739-0c6b80). Items marked (practitioner) are untested advice from secondary articles; items marked (secondary) are vendor statements seen only through a summarizer.

## Write a fully formed prompt

- **State the question, the desired outcome and the constraints.** OpenAI's API deep-research model expects a fully formed prompt up front, has no built-in clarification step and will not ask for more context. Clarifier and rewriter steps are optional additions in front of it; a sufficiently detailed brief needs neither.
- **Do not invent unstated details.** Preserve what the requester said; mark necessary but unstated dimensions as open-ended rather than guessing them.
- **Replace vague verbs with concrete criteria** (practitioner): "discuss competitors" becomes a list of comparison factors.
- **State the objective, not the steps** (OpenAI forum, community): over-instructing hurts as much as under-instructing; revise the prompt after seeing results.

## Scope, sources, output shape

- **Scope line** (practitioner): include these topics, exclude those.
- **Source line** (practitioner): prefer these source types, avoid those (for example forums and SEO round-ups). Write source-quality heuristics into the brief: Anthropic reports early agents picked SEO content farms over authoritative sources until the prompts said to prefer primary sources.
- **Output shape:** name the format (report with headers, table for comparisons), and require visible, clickable inline citations for factual claims.
- **Flag the unconfirmed** (practitioner): end with a section listing claims that could not be confirmed.

## Subagent and specialist assignments

- **Each assignment carries four things** (Anthropic multi-agent research post): an objective, an output format, guidance on tools and sources, and clear task boundaries. One-line assignments such as "research the semiconductor shortage" made subagents misread the task or repeat each other's searches.
- **Scale effort to the question.** Anthropic's examples: simple fact-finding, one agent with 3-10 tool calls; direct comparisons, 2-4 agents with 10-15 calls each; complex research, more than 10 agents with divided responsibilities. State the effort in the brief so specialists do not overinvest.
- **Give success criteria and ask for source verification across several sources**; for complex questions, competing hypotheses with tracked confidence.

## Product-specific notes

- **OpenAI API:** file search takes `type` and `vector_store_ids` (at most two stores); a remote MCP server must implement `search` and `fetch`. Output format and source types belong in the prompt. Model IDs are slated for replacement (secondary; unconfirmed).
- **Gemini Deep Research:** start with a simple prompt, review the research plan it shows, change it with Edit plan before starting; follow-up questions after the report are encouraged.
- **NotebookLM:** a specific question locates the relevant passages; answers come only from the notebook's sources. Pipeline-specific rules live in `notebooklm-best-practices.md`.
- **Plan review:** OpenAI's ChatGPT product lets the user review the plan and interrupt to refocus. Review the plan before the run when the product offers it.

## Known gaps (unsourced)

- OpenAI's ChatGPT Deep Research help page was unreadable (403); product-side OpenAI statements above come through secondary articles.
- No source addressed falsifiable sub-questions or reshaping a brief after a survey pass. The survey-then-brief ordering rests on the PM's direction, not a cited source.
- No official Google guidance on NotebookLM custom instructions or report formats was found.
