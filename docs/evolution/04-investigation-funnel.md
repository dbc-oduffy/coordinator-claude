# 04 — Investigation Funnel

> Why we built tiered context loading and stopped reaching for Sonnet scouts as the default.

## The Sonnet-scout reflex

Early versions of this system treated dispatch-a-Sonnet-scout as the default move for any non-trivial codebase question. *"Where is X defined? Dispatch a scout. How does subsystem Y work? Dispatch a scout."* The reasoning was sound on its face — scouts have fresh context, the EM's context is scarce, offloading is good hygiene.

The reasoning had a hole. Scout dispatch is not free. Each dispatch costs (1) the prompt-construction tokens, (2) whatever the scout spends investigating, (3) the round-trip latency, and (4) the brief comes back into the EM's context anyway. If the question could have been answered by a one-line lookup against pre-existing artifacts, the scout dispatch is pure overhead.

The reflex was producing scout dispatches for questions like "what does this skill do" — questions where the skill file already existed at a known path and could be read in one Read call. The scout would investigate, report back a paraphrase of the file, and burn 5–10x the tokens of the direct read.

## The taxonomy that emerged

The fix was to tier investigation lookups by cost, with a hard rule: start at the cheapest tier, escalate one step at a time, never skip.

**Tier 0 — boot context.** `orientation_cache.md`, `lessons.md`, session memory. Loaded at session start; no tool call needed. If the question is answerable from this tier, no investigation happens at all.

**Tier 1 — curated narrative.** Architecture atlas, wiki guides, decision records, docs index. ≤8K tokens per fetch. Subsystem-shaped questions ("how does X work," "what decisions were made about Y") are answered here without code inspection.

**Tier 2 — structured query.** When project-RAG MCP tools are available, prefer them over grep for code-shaped lookups. `project_subsystem_profile`, `project_cpp_symbol`, `project_semantic_search`, `project_referencers` — each answers a different shape of question in one tool call. Stale RAG still beats fresh grep on structure.

**Tier 3 — targeted code/grep.** Read of a known path, Grep for a specific symbol, Glob for pattern discovery. ≤4K tokens per call. Use when tier 1–2 leave a specific gap.

**Tier 4 — Sonnet scout (last resort).** Dispatch only when tiers 1–3 have returned nothing useful for the question. Tier-4 dispatches must be preceded by an explicit rationale ("Tier 1-3 attempted: <what each returned>; insufficient because <reason>").

## What this changed in practice

The mechanical effect was a sharp drop in scout dispatch rate — orders of magnitude — for routine investigation. The structural effect was that the EM stopped *defaulting to* "dispatch a scout" and started *defaulting to* "what's the cheapest tier that could answer this?"

There's a hook (the tier-usage telemetry hook) that flags scout dispatches without rationale preambles. It's an honest mirror — when the rate of unflagged dispatches climbs, it usually means a doctrine slip and the EM has been reaching for scouts again. The hook doesn't punish; it surfaces.

## The "stale RAG beats grep" rule

The most counter-intuitive piece of the funnel. The reflex would say: *if the RAG index might be stale, surely grep is more reliable?*

Empirically, no. RAG indexes carry structural information — symbol-to-file maps, subsystem profiles, dependency graphs — that grep does not produce in any reasonable amount of work. A stale RAG returns the *structural skeleton* of the codebase as it was at index time, which is almost always still valid for questions about overall shape. Grep returns text matches with no structural framing. For a question like "what subsystem owns X," stale RAG answers correctly even if X has been refactored at line level since the index ran.

There are exceptions — questions where the answer is fundamentally about *recent* changes ("what was added this week"). Those route to git log or grep, not RAG. The doctrine carves the exception explicitly so the rule's authority isn't undermined.

## The exception list

The funnel allows direct-without-full-escalation in three cases:

- Reading a single known file before editing it.
- 1–2 call confirmation of a known symbol.
- Cases where dispatch overhead clearly exceeds the lookup.

These exceptions exist because rigid escalation would generate ceremony for trivial cases. The tier-4 rationale rule still applies whenever a scout *is* dispatched, regardless of whether tiers 1–3 were "attempted" — the rationale is the gate, not the count.

## What we'd revisit if the data changed

If RAG index quality degrades sharply (e.g., a project where the index is months out of date and code has churned heavily), the "stale RAG beats grep" rule would bend. We'd add a staleness check that flips the preference past some threshold. We haven't seen that case land yet; the rule holds in current practice.

If scout-dispatch overhead drops dramatically — faster spawn, smaller context cost — the cost-benefit on tier 4 shifts. The tiering would still matter for context discipline (the EM's context is scarce regardless of dispatch cost), but the bias against tier 4 would soften.

## The lesson the funnel was trying to teach

When a tool feels free, you reach for it reflexively. When you put it at the end of a tiered escalation with a mandatory rationale check, you reach for it deliberately. Neither version of "the EM has access to Sonnet scouts" is wrong; the second produces better outcomes because it forces the question *should this be a scout?* to be answered, not skipped.

The same principle applies to the rest of the system. Skills, hooks, plan mode, the staff session — all of them are tools that feel free and produce drift if used reflexively. The funnel is one instance of a larger pattern: *make the decision to use a tool an explicit step, not the default.*
