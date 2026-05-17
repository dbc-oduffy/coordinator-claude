# Peer-Repo Research Triage

> How to filter peer-repo prior-art lookups when scanning `~/.claude/tasks/repo-registry.md` for relevant references.

## Filter ordering

Filters are applied in order of signal-to-noise. Always exhaust content-shape filters before falling back to transport-shape.

1. **Topic match** — `stack_tags` overlap with the plan's domain (e.g. `rag`, `unreal`, `pytest`).
2. **Vocabulary match** — repo wiki uses the same domain nouns/verbs as the plan claim.
3. **Author/lineage match** — peer repo was authored by the same operator or forked from a shared ancestor.
4. **Transport shape** (HTTP / gRPC / CLI / MCP) — **filter of last resort**.

## The transport-shape trap

Transport-shape filters (HTTP, gRPC, CLI surface) are cheap to evaluate but noisy: two repos sharing "exposes an HTTP API" overlap on framing only, not on the underlying problem. Use transport-shape filters ONLY when topic / vocabulary / author filters return no candidates — and treat the resulting hits as candidates needing manual review, not as confirmed prior art.

## Practical recipe

For each plan claim:
- Grep `repo-registry.md` for topic tags first.
- If zero hits, broaden to vocabulary terms.
- If still zero, *then* consider transport-shape — and degrade the prior-art-checker verdict to `DEGRADED` per `prior-art-checker.md`.

Transport-shape hits without topic/vocabulary corroboration are noise; surface them in the sidecar as `Compatible-but-relevant` at most, never as `Conflicts`.

## Sizing scouts before Pipeline B

**Run a sizing pass before deep research.** For first-time evaluation of upstream alternatives, dispatch parallel sizing scouts (Sonnet `general-purpose`, ~30 min each) producing structured briefs *before* committing to full Pipeline B. The sizing pass converts "unknown depth" into "decided depth per repo" cheaply, and routes each candidate to its right intervention shape:

- **catalog** — small scout deliverable, no follow-up. The repo's relevant content is enumerable in the scout's output.
- **prototype** — quick proof-of-concept against the repo's API/pattern. No full deep-research run needed.
- **port** — full Pipeline B is justified; the repo carries enough doctrine/architecture/pattern depth to warrant a structured campaign.
- **skip** — off-domain. The scout's brief documents why; no further investment.

**Failure mode the sizing pass prevents.** Pipeline B is heavyweight (multiple analyst-tier dispatches, synthesis pass, structured artifact). Running it on every candidate without prior sizing burns hours on repos that catalog-shape would have resolved in 30 minutes, and produces uniformly mediocre output across the batch because every repo gets equal investigation depth regardless of fit. The sizing pass is the calibration step: it answers *"is this worth the full pipeline, or does a stub-and-prod read suffice?"* before the heavyweight machinery starts.

**Practical recipe.** Before `/deep-research --pipeline=repo` on a multi-candidate batch:

1. Dispatch one Sonnet `general-purpose` sizing scout per candidate. Each scout's brief: "Read the repo's README, top-level docs, and 2-3 representative files. Classify as catalog / prototype / port / skip. ~30 min budget. Return a structured brief naming the classification and ≤3 sentences of rationale."
2. Review the briefs together. Fire deep research **only on the `port` classifications**.
3. Catalog/prototype outcomes feed downstream work directly from the scout brief.
4. Skip outcomes get one-line entries in `~/.claude/tasks/repo-registry.md` so future passes don't re-investigate.

Companion to `docs/wiki/ceremony-calibration.md` § Sizing-pass calibration — the calibration there explains *why*; this section explains *how* in the peer-repo research case specifically.
