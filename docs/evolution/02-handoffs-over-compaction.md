# 02 — Handoffs Over Compaction

> Why we stopped trusting automatic summarization to preserve session state.

## The triggering observation

A session that took six hours to develop a plan, a partial implementation, and a rough understanding of which approach was wrong — would, after compaction, return a model that confidently described a *different* version of the work than had actually happened. Decisions that had been made and discarded would resurface as live options. Approaches we'd ruled out would re-enter the conversation as proposals. The model wasn't lying; it was reconstructing.

That was the problem. Compaction is retrospective summarization, and retrospective summarization is reconstruction. The model summarizes what it *thinks* happened, not what happened — and the closer to the present the summary gets, the more it relies on the model's own interpretation of fragmented evidence rather than ground truth.

You can feel this happen in real time if you watch for it: a session approaching the compaction threshold starts treating prior decisions with slightly less confidence. After compaction, prior decisions are gone — replaced by the model's best guess at what they were.

## The shape of the response

The fix was structural, not stylistic. Instead of asking the model to summarize better, we built a protocol that captures session state *before* the compaction window forces summarization. Structured handoffs — written prospectively, while context is still intact — preserve decisions, current state, and explicit next steps. They chain forward from a single named predecessor (no adjacency-inference, no implicit merging of unrelated handoffs).

A `PostToolUse` hook monitors context fill and prompts handoff generation when pressure rises. The handoff is the unit of session-to-session continuity — `/pickup <handoff>` opens the next session mid-context, with the prior decisions and state already loaded.

## The literature converged

The full survey is in the research artifact: [Structured Handoff Artifacts vs. Compaction for Agent Continuity](../research/2026-03-21-handoff-artifacts-vs-compaction.md). Short version of what it found:

- Empirical benchmarks show structured handoffs beat both raw history and automatic compaction for agent-to-agent task chains.
- Production frameworks (LangChain, xtrace, others) converge on the same conclusion: durable state must be separated from per-call views, and per-call views must be scoped to the minimum needed.
- The strongest single data point: Sourcegraph retired compaction in their Amp agent in favor of explicit handoffs, after measuring degradation.

The literature debate isn't *whether* to structure handoffs — it's *how*. We picked one shape, the system runs on it, and we revise as we hit edge cases (concurrent crashes, lineage ambiguity, recovery sessions).

## What this looks like in practice

Three places handoffs show up in normal use:

- **`/handoff`** — the user (or EM) explicitly captures state before stepping away. Used at end-of-day, before a deliberate break, or when the EM senses session pressure.
- **`/pickup <file>`** — opens a new session from a named handoff. The session lands mid-context with prior state loaded, no cold start.
- **`PostToolUse` context-pressure hook** — automatic nudge when context fill crosses a threshold. The EM is invited (not forced) to generate a handoff before compaction would otherwise fire.

A handoff has one predecessor — whatever file the session was opened with. "Most recent handoff" is not predecessor; adjacency is not ancestry. Concurrent crashed sessions get separate handoffs. These rules aren't aesthetic; they're the result of specific incidents where adjacency-inference buried a workstream.

## The honest residual

Handoffs aren't free. They cost author effort, they can drift from reality if written carelessly, and they have a failure mode where a vague handoff is worse than no handoff because it gives false confidence. The protocol fights this with structure — required sections for decisions, current state, next moves — but a sloppy handoff is still a sloppy handoff. The discipline matters as much as the format.

We've also seen handoffs that read well but don't actually load the recipient with the context they need. The "anti-amnesia chain" rule — every handoff opens with a synthesis of its predecessor — was a response to that specific pattern. Without the chain, a handoff series accumulates ambiguity instead of resolving it.

## What we'd revisit if the data changed

If a future compaction implementation produced demonstrably faithful summaries — not just better-sounding ones — the cost-benefit on handoffs would shift. We'd still keep structured handoffs for cross-session continuity (you can't compact across sessions), but the within-session pressure-point handoff would become optional rather than load-bearing.

We don't see that future arriving soon. The structural problem isn't summarization quality — it's that retrospective reconstruction from fragmentary evidence is a different operation than prospective state capture, and the latter has access to information the former doesn't.
