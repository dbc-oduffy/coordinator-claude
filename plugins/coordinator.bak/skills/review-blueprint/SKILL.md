---
name: review-blueprint
description: LLM-powered Blueprint review with RAG grounding. Entry point for the /coordinator:review-blueprint command pipeline. Sub-skill rag-fetch.md handles domain classification and RAG retrieval.
type: skill
---

# review-blueprint

Blueprint review skill — invoked via the `/coordinator:review-blueprint` command (see `commands/review-blueprint.md`).

This skill directory contains support documents for the review pipeline:

- **`rag-fetch.md`** — Domain classification + RAG fetch for a `manage_review.prepare` payload. Called after obtaining the raw payload from holodeck-control MCP.

## When invoked

Use `/coordinator:review-blueprint <bp-asset-path>` to trigger the full pipeline:
1. `manage_review.prepare` (holodeck-control MCP) — builds the payload
2. `rag-fetch.md` — classifies domain, fetches RAG context
3. Sid review dispatch (with optional Patrik escalation for architecture-heavy BPs)

See `commands/review-blueprint.md` for the full command specification.
