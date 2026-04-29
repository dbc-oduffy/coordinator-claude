# NotebookLM Best Practices — Reference

> Read by the EM at the start of Step 2 (scoping). These rules encode community research and published studies on NotebookLM usage. Follow them — they're the difference between shallow output and high-signal research.

---

## Source Strategy

- **10-25 focused sources per notebook.** This is the practical sweet spot for synthesis quality. Fewer than 10 may leave gaps; beyond 25, retrieval degrades.
- **One topic cluster per notebook.** Don't mix domains. TED Talks on behavioral science and TED Talks on time management belong in separate notebooks.
- **~250 pages total** is the practical ceiling before retrieval degrades. Break large documents into smaller focused chunks before ingestion.
- **Google Docs for evolving content** (real-time sync keeps the notebook current). **PDFs for stable reference** (immutable — good when you want a fixed snapshot).
- **Avoid Google Sheets** — tabular format is the worst RAG input; retrieval errors are common.
- **Avoid consolidating multiple PDFs into one "Megazord" PDF** — destroys citation precision and makes it impossible to attribute findings to specific sources.
- **Google Docs with multiple Tabs count as one source** — useful for packing more structured content per source slot.
- **Strip PII from research documents before ingestion.**
- **Verify ingestion.** Silent failures are common — YouTube with no captions, JS-rendered web pages, paywalled articles. Include a verification query in the question list.
- **YouTube URLs must be direct `youtube.com/watch?v=...` links.** NLM extracts transcripts from YouTube videos — this is one of its highest-value capabilities. But it ONLY works with direct YouTube URLs. Forum pages, Epic Dev Community pages, ClassCentral listings, and blog posts that *link* to videos give NLM only the page text (title, description, comments), not the video transcript. A forum thread about a GDC talk is NOT the talk. Scout agents must use `site:youtube.com` searches to find direct video URLs.
- **Medium and paywalled sites are effectively blocked.** Medium's bot protection and paywalls consistently prevent NLM ingestion. Pre-download content or find alternative sources.

---

## Query Engineering — Anti-Hallucination Rules

NotebookLM has a documented 13% hallucination rate on broad queries, dropping to near-zero on specific ones. Question design is the primary quality lever.

**Rule 1: Every query must require citations.**
Append "Quote the specific passage and name the source" to every research question. This forces retrieval over generation.

**Rule 2: Specificity forces grounding.**
"According to the uploaded sources, what are the enforcement mechanisms for X?" is dramatically more reliable than "Summarize X trends."

**Rule 3: Use the structured synthesis template for critical queries:**
> "What are the main findings on [X]? For each finding: TOPIC / DESCRIPTION (synthesis with context) / EVIDENCE (direct quote with source). If a topic appears in multiple sources, show evidence from each. If information is not found in sources, state: [NOT FOUND IN DOCUMENTS]."

**Rule 4: Include a source gap audit query:**
> "What topics in [area] are NOT covered by any uploaded source? Identify contradictions with direct citations. Suggest 3 follow-up research questions."

---

## High-Value Question Templates

| Pattern | Template |
|---------|----------|
| **Cross-source synthesis** | "Where do these sources agree and disagree about [X]? Quote both positions with source attribution." |
| **Contradiction extraction** | "Identify the biggest contradictions across these sources. For each: quote both sides with citations, explain why they disagree." |
| **Hidden connections** | "Explore the non-obvious connections between [A] and [B]. Quote relevant evidence, flag tensions, highlight unexpected combinations." |
| **Essential questions** | "Identify the 5 most important questions someone must answer to fully understand this material." |
| **Surprising insights** | "Identify the most surprising facts and non-obvious insights. For each, explain why it's noteworthy and include a direct quote." |
| **Decision memo** | "Prepare a decision memo. Organize under: User Evidence (direct pain points), Feasibility Checks (constraints mentioned), Blind Spots (information missing)." |

**Question formula:** role + context + output format. State who NLM should answer as, what the context is, and what shape the answer should take.

**Reverse-mode technique:** Ask NLM to generate questions *about* the sources rather than answer a question. This surfaces unstated assumptions and reveals what the sources are actually about. Useful when scoping is uncertain.

---

## Custom Notebook Instructions

Structure as:
1. **Role:** "You are a rigorous research analyst."
2. **Context:** "This notebook contains [description of source material]."
3. **Rules:** "Always include precise quotes. Identify contradictions. Clearly distinguish facts from inferences. When a claim is not supported by the uploaded sources, say so explicitly. Do not speculate beyond the source material."

Keep under 10,000 characters. These instructions cascade to ALL outputs: chat, audio overviews, study guides, slides, briefing docs, flashcards, quizzes — everything. Tailor to the specific topic and source types.

---

## What NLM Refuses

- Academic citation formatting (APA, MLA, Chicago) — it won't produce formatted bibliographies
- Creative generation beyond uploaded sources — it stays grounded
- Safety-flagged content — standard content policy applies

---

## Worker Count Decision

| Worker count | When to use |
|---|---|
| **1** | Focused single-topic question, free tier, PM provided specific sources, tight query budget |
| **2** | Moderate breadth (two angles or subtopics), Plus tier with budget to spare |
| **3** | Broad multi-angle investigation, Ultra tier, high source diversity expected |

**Decision factors:** topic breadth, available queries (tier budget minus used today), expected cross-referencing value, PM's time budget.

---

## Rate Limit Budgeting

| Tier | Queries/day | Workers | Questions/worker |
|------|------------|---------|-----------------|
| Free | 50 | 1 | 5-6 |
| Plus | 500 | 1-2 | 7-8 |
| Ultra | 5,000 | up to 3 | 8 |

If `queries_used_today` is known, subtract from the daily budget before sizing.

---

## Source Strategy Per Notebook — scout-provided vs research_start

- **scout-provided:** Scout does WebSearch + WebFetch to find and verify URLs. Worker ingests the scout's list. Best when topic has known high-quality YouTube/podcast sources, or when Google's search engine would outperform manual discovery on the specific topic.
- **research_start:** Worker uses NLM's built-in discovery (`research_start` MCP tool). Best for exploratory topics or "what's out there on X."

**PM-provided URLs:** Assign them to a named notebook, mark it scout-provided, and include the exact URLs in the scout search guidance. Scout does not need to search — it uses the provided URLs directly.

---

## Studio Output Guidance

Request only the artifacts the PM actually needs.

| Artifact | Best for |
|----------|----------|
| **Audio Overview** | Passive learning, commute consumption. Quality depends on source structure — well-structured sources produce better audio. |
| **Study Guide** | Exam prep, structured review with key concepts |
| **Slides** | Presentations — exportable to PPTX |
| **Briefing Doc** | Executive summary, quick orientation |
| **Flashcards / Quiz** | Active recall testing, knowledge verification |

**Multi-format sequence:** Written reports → audio overview → flashcards/quizzes. This order extracts maximum value from a single research session.
